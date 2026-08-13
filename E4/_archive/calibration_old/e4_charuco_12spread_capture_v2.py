#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 ChArUco 12-spread camera->paper calibration collector
=========================================================

Board / physical geometry (FROZEN)
----------------------------------
ChArUco:
  squaresX       = 9
  squaresY       = 7
  squareLength   = 25.00 mm
  markerLength   = 18.00 mm
  dictionary     = DICT_4X4_50
  board size     = 225 x 175 mm
  internal ChArUco corners = 8 x 6 = 48

Paper-frame coordinates of the OUTER printed board corners:
  TL = (-116, -92) mm
  TR = (+109, -92) mm
  BR = (+109, +83) mm
  BL = (-116, +83) mm

NOTE:
The user's fourth coordinate was typed as (-116,-92), which duplicates TL.
This script assumes the intended BL is (-116,+83), because that gives exactly
225 x 175 mm.

Formal calibration budget
-------------------------
Use exactly 12 pre-frozen spread ChArUco corners:
  4 spread columns x 3 spread rows

The script:
1) subscribes to one color Image topic for ihawk1 and ihawk2;
2) detects ArUco + interpolated ChArUco corners;
3) applies explicit sub-pixel refinement;
4) saves the first good raw + annotated frame for each camera;
5) collects multiple valid frames (default 20 per camera);
6) saves ALL 48 physical ChArUco corner geometry;
7) saves per-frame measurements of the fixed 12 formal corners;
8) aggregates each formal corner by median pixel location;
9) writes one formal CSV containing 12 correspondences per camera.

This script DOES NOT:
- move the robot
- use robot coordinates to define calibration GT
- fit Affine / Homography / PnP yet
- use RANSAC
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


# ============================================================================
# FROZEN BOARD GEOMETRY
# ============================================================================

SQUARES_X = 9
SQUARES_Y = 7
SQUARE_LENGTH_MM = 25.0
MARKER_LENGTH_MM = 18.0

# Printed outer board corners in paper_frame [mm].
PAPER_TL = np.array([-116.0, -92.0], dtype=np.float64)
PAPER_TR = np.array([+109.0, -92.0], dtype=np.float64)
PAPER_BR = np.array([+109.0, +83.0], dtype=np.float64)
PAPER_BL = np.array([-116.0, +83.0], dtype=np.float64)

# Formal 12-spread geometry:
# 8 internal columns -> select indices 0,2,5,7
# 6 internal rows    -> select top/mid/bottom indices 0,2,5
FORMAL_X_PAPER_MM = [-91.0, -41.0, +34.0, +84.0]
FORMAL_Y_PAPER_MM = [-67.0, -17.0, +58.0]

# Camera intrinsics already used in this project.
CAMERA_K = {
    "ihawk1": np.array([
        [401.77020263671875, 0.0, 322.1313781738281],
        [0.0, 401.9191589355469, 202.54229736328125],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64),

    "ihawk2": np.array([
        [391.3234558105469, 0.0, 320.85333251953125],
        [0.0, 391.3234558105469, 202.9705047607422],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64),
}

# Current formal pipeline uses undistorted/rectified pixel coordinates with D=0.
CAMERA_D = {
    "ihawk1": np.zeros((5, 1), dtype=np.float64),
    "ihawk2": np.zeros((5, 1), dtype=np.float64),
}


def get_dictionary():
    # OpenCV 4.5.x compatibility
    if hasattr(cv2.aruco, "Dictionary_get"):
        return cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def make_board(dictionary):
    # OpenCV 4.5.x compatibility first
    if hasattr(cv2.aruco, "CharucoBoard_create"):
        return cv2.aruco.CharucoBoard_create(
            SQUARES_X,
            SQUARES_Y,
            SQUARE_LENGTH_MM,
            MARKER_LENGTH_MM,
            dictionary,
        )

    # Newer API fallback
    return cv2.aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y),
        SQUARE_LENGTH_MM,
        MARKER_LENGTH_MM,
        dictionary,
    )


def make_detector_parameters():
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        p = cv2.aruco.DetectorParameters_create()
    else:
        p = cv2.aruco.DetectorParameters()

    # Refine ArUco marker corners.
    if hasattr(cv2.aruco, "CORNER_REFINE_SUBPIX"):
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    if hasattr(p, "cornerRefinementWinSize"):
        p.cornerRefinementWinSize = 5
    if hasattr(p, "cornerRefinementMaxIterations"):
        p.cornerRefinementMaxIterations = 50
    if hasattr(p, "cornerRefinementMinAccuracy"):
        p.cornerRefinementMinAccuracy = 0.01

    return p


def get_board_chessboard_corners(board) -> np.ndarray:
    if hasattr(board, "chessboardCorners"):
        pts = np.asarray(board.chessboardCorners, dtype=np.float64)
    elif hasattr(board, "getChessboardCorners"):
        pts = np.asarray(board.getChessboardCorners(), dtype=np.float64)
    else:
        raise RuntimeError("Cannot access ChArUco chessboard corners from OpenCV.")

    return pts.reshape(-1, 3)


def board_xyz_to_paper_xy(board_xyz: np.ndarray) -> np.ndarray:
    """
    OpenCV ChArUco board coordinates are measured from the printed board's
    top-left outer corner:
      board +X -> right
      board +Y -> down

    Frozen physical placement:
      TL=(-116,-92), TR=(109,-92), BR=(109,83), BL=(-116,83)

    paper_frame uses the same physical directions over this board:
      paper +X -> right
      paper +Y -> down

    Therefore:
      paper_x = TL_x + board_x
      paper_y = TL_y + board_y
    """
    bx = float(board_xyz[0])
    by = float(board_xyz[1])

    px = float(PAPER_TL[0] + bx)
    py = float(PAPER_TL[1] + by)
    return np.array([px, py], dtype=np.float64)


def build_geometry(board):
    obj = get_board_chessboard_corners(board)

    if len(obj) != 48:
        raise RuntimeError(
            f"Expected 48 ChArUco corners, got {len(obj)}. "
            "Check board definition."
        )

    geometry = {}
    for cid, xyz in enumerate(obj):
        pxy = board_xyz_to_paper_xy(xyz)
        geometry[cid] = {
            "charuco_id": cid,
            "board_x_mm": float(xyz[0]),
            "board_y_mm": float(xyz[1]),
            "board_z_mm": float(xyz[2]),
            "paper_x_mm": float(pxy[0]),
            "paper_y_mm": float(pxy[1]),
            "paper_z_mm": 0.0,
        }

    return geometry


def choose_formal_ids(geometry: Dict[int, dict]) -> List[int]:
    """
    Freeze exactly 12 spread points by physical paper coordinates, not by
    observed calibration error.

    This avoids relying on any guessed ChArUco-ID ordering.
    """
    desired = [
        (x, y)
        for y in FORMAL_Y_PAPER_MM
        for x in FORMAL_X_PAPER_MM
    ]

    selected = []
    used = set()

    for tx, ty in desired:
        best_id = None
        best_dist = float("inf")

        for cid, g in geometry.items():
            if cid in used:
                continue

            dx = g["paper_x_mm"] - tx
            dy = g["paper_y_mm"] - ty
            d = math.hypot(dx, dy)

            if d < best_dist:
                best_dist = d
                best_id = cid

        if best_id is None or best_dist > 1e-6:
            raise RuntimeError(
                f"Could not find exact ChArUco corner at ({tx},{ty}) mm. "
                f"Nearest distance={best_dist}"
            )

        used.add(best_id)
        selected.append(best_id)

    if len(selected) != 12 or len(set(selected)) != 12:
        raise RuntimeError("Formal point selection did not produce 12 unique IDs.")

    return selected


def ros_stamp_to_float(msg: Image) -> float:
    return float(msg.header.stamp.sec) + 1e-9 * float(msg.header.stamp.nanosec)


def robust_stats(values):
    a = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "sd": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        "min": float(np.min(a)),
        "max": float(np.max(a)),
        "n": int(len(a)),
    }


class CharucoCollector(Node):
    def __init__(self, args):
        super().__init__("e4_charuco_12spread_collector")
        self.args = args
        self.bridge = CvBridge()

        self.dictionary = get_dictionary()
        self.board = make_board(self.dictionary)
        self.detector_params = make_detector_parameters()

        self.geometry = build_geometry(self.board)
        self.formal_ids = choose_formal_ids(self.geometry)
        self.formal_id_set = set(self.formal_ids)

        self.output_dir = Path(args.out_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.accepted_count = {"ihawk1": 0, "ihawk2": 0}
        self.done = {"ihawk1": False, "ihawk2": False}

        self.raw_rows = []
        self.measurements = {
            "ihawk1": defaultdict(lambda: {"u_raw": [], "v_raw": [], "u_und": [], "v_und": []}),
            "ihawk2": defaultdict(lambda: {"u_raw": [], "v_raw": [], "u_und": [], "v_und": []}),
        }

        self.saved_first_good = {"ihawk1": False, "ihawk2": False}

        self.topic1 = args.topic1
        self.topic2 = args.topic2

        if not self.topic1 or not self.topic2:
            self.get_logger().info("Discovering camera color Image topics...")
            time.sleep(1.0)
            self.topic1 = self.topic1 or self.auto_find_image_topic("ihawk1")
            self.topic2 = self.topic2 or self.auto_find_image_topic("ihawk2")

        print("=" * 88)
        print("E4 CHARUCO 12-SPREAD CAMERA->PAPER CALIBRATION")
        print("=" * 88)
        print(f"OpenCV version: {cv2.__version__}")
        print(f"Output: {self.output_dir}")
        print(f"Frames required per camera: {args.frames}")
        print(f"ihawk1 topic: {self.topic1}")
        print(f"ihawk2 topic: {self.topic2}")
        print()
        print("Printed board outer corners in paper_frame [mm]:")
        print(f"  TL = {tuple(PAPER_TL)}")
        print(f"  TR = {tuple(PAPER_TR)}")
        print(f"  BR = {tuple(PAPER_BR)}")
        print(f"  BL = {tuple(PAPER_BL)}")
        print()
        print("Frozen 12-spread ChArUco points:")
        for cid in self.formal_ids:
            g = self.geometry[cid]
            print(
                f"  id={cid:2d} "
                f"paper=({g['paper_x_mm']:+7.1f},{g['paper_y_mm']:+7.1f}) mm "
                f"board=({g['board_x_mm']:6.1f},{g['board_y_mm']:6.1f}) mm"
            )
        print("=" * 88)

        self.write_geometry_csv()

        self.sub1 = self.create_subscription(
            Image, self.topic1,
            lambda msg: self.on_image("ihawk1", msg),
            10,
        )
        self.sub2 = self.create_subscription(
            Image, self.topic2,
            lambda msg: self.on_image("ihawk2", msg),
            10,
        )

    def auto_find_image_topic(self, camera_name: str) -> str:
        topics = self.get_topic_names_and_types()

        candidates = []
        for name, types in topics:
            if camera_name not in name:
                continue
            if "sensor_msgs/msg/Image" not in types:
                continue

            lname = name.lower()
            if "depth" in lname or "ir" in lname or "infra" in lname:
                continue

            score = 0
            if "color" in lname:
                score += 100
            if "rgb" in lname:
                score += 80
            if "image" in lname:
                score += 20
            if "raw" in lname:
                score += 10

            candidates.append((score, name))

        if not candidates:
            known = [
                (name, types)
                for name, types in topics
                if camera_name in name
            ]
            raise RuntimeError(
                f"Could not auto-find a color sensor_msgs/Image topic for {camera_name}.\n"
                f"Topics containing '{camera_name}': {known}\n"
                f"Run `ros2 topic list -t` and pass --topic1/--topic2 explicitly."
            )

        candidates.sort(reverse=True)
        return candidates[0][1]

    def write_geometry_csv(self):
        path = self.output_dir / "E4_charuco_all48_geometry.csv"

        fields = [
            "charuco_id",
            "is_formal_12spread",
            "board_x_mm",
            "board_y_mm",
            "board_z_mm",
            "paper_x_mm",
            "paper_y_mm",
            "paper_z_mm",
        ]

        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()

            for cid in sorted(self.geometry):
                row = dict(self.geometry[cid])
                row["is_formal_12spread"] = int(cid in self.formal_id_set)
                w.writerow({k: row[k] for k in fields})

    def detect_charuco(self, camera: str, bgr: np.ndarray):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        marker_corners, marker_ids, _ = cv2.aruco.detectMarkers(
            gray,
            self.dictionary,
            parameters=self.detector_params,
        )

        if marker_ids is None or len(marker_ids) == 0:
            return None

        K = CAMERA_K[camera]
        D = CAMERA_D[camera]

        try:
            retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                marker_corners,
                marker_ids,
                gray,
                self.board,
                cameraMatrix=K,
                distCoeffs=D,
            )
        except TypeError:
            # Fallback for Python bindings where keyword arguments differ.
            retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                marker_corners,
                marker_ids,
                gray,
                self.board,
            )

        if (
            charuco_ids is None
            or charuco_corners is None
            or int(retval) < 4
        ):
            return None

        ids = charuco_ids.reshape(-1).astype(int)
        corners = charuco_corners.reshape(-1, 2).astype(np.float32)

        # Explicit ChArUco cornerSubPix refinement.
        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            50,
            0.001,
        )

        refined = corners.copy().reshape(-1, 1, 2)
        h, w = gray.shape[:2]

        # cornerSubPix expects all points to be inside a safe image margin.
        safe_mask = (
            (corners[:, 0] >= 6)
            & (corners[:, 0] < w - 6)
            & (corners[:, 1] >= 6)
            & (corners[:, 1] < h - 6)
        )

        if np.all(safe_mask):
            cv2.cornerSubPix(
                gray,
                refined,
                (5, 5),
                (-1, -1),
                criteria,
            )
            corners = refined.reshape(-1, 2)

        raw_by_id = {
            int(cid): corners[i].astype(np.float64)
            for i, cid in enumerate(ids)
        }

        # Same formal convention as previous experiments:
        # explicit undistortPoints with P=K. With D=0 this preserves pixels.
        pts = corners.reshape(-1, 1, 2).astype(np.float64)
        und = cv2.undistortPoints(pts, K, D, P=K).reshape(-1, 2)

        und_by_id = {
            int(cid): und[i].astype(np.float64)
            for i, cid in enumerate(ids)
        }

        return {
            "gray": gray,
            "marker_corners": marker_corners,
            "marker_ids": marker_ids,
            "charuco_ids": ids,
            "charuco_corners": corners,
            "raw_by_id": raw_by_id,
            "und_by_id": und_by_id,
        }

    def make_annotated(self, bgr, det, camera):
        out = bgr.copy()

        cv2.aruco.drawDetectedMarkers(
            out,
            det["marker_corners"],
            det["marker_ids"],
        )

        ids_col = det["charuco_ids"].reshape(-1, 1).astype(np.int32)
        corners = det["charuco_corners"].reshape(-1, 1, 2).astype(np.float32)

        try:
            cv2.aruco.drawDetectedCornersCharuco(
                out,
                corners,
                ids_col,
            )
        except Exception:
            pass

        # Highlight the 12 frozen formal points.
        for cid in self.formal_ids:
            if cid not in det["raw_by_id"]:
                continue

            u, v = det["raw_by_id"][cid]
            p = (int(round(u)), int(round(v)))

            cv2.circle(out, p, 7, (0, 0, 255), 2)
            cv2.putText(
                out,
                f"F{cid}",
                (p[0] + 7, p[1] - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )

        cv2.putText(
            out,
            f"{camera}: formal 12-spread in RED",
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        return out

    def on_image(self, camera: str, msg: Image):
        if self.done[camera]:
            return

        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as e:
            self.get_logger().error(f"{camera}: cv_bridge failed: {e}")
            return

        det = self.detect_charuco(camera, bgr)
        if det is None:
            return

        detected_set = set(int(x) for x in det["charuco_ids"])
        missing_formal = sorted(self.formal_id_set - detected_set)

        # Formal frame is accepted only when all fixed 12 points are visible.
        if missing_formal:
            return

        idx = self.accepted_count[camera] + 1
        self.accepted_count[camera] = idx

        stamp = ros_stamp_to_float(msg)

        for cid in self.formal_ids:
            raw = det["raw_by_id"][cid]
            und = det["und_by_id"][cid]
            g = self.geometry[cid]

            self.measurements[camera][cid]["u_raw"].append(float(raw[0]))
            self.measurements[camera][cid]["v_raw"].append(float(raw[1]))
            self.measurements[camera][cid]["u_und"].append(float(und[0]))
            self.measurements[camera][cid]["v_und"].append(float(und[1]))

            self.raw_rows.append({
                "camera": camera,
                "frame_index": idx,
                "timestamp": stamp,
                "charuco_id": cid,
                "paper_x_mm": g["paper_x_mm"],
                "paper_y_mm": g["paper_y_mm"],
                "paper_z_mm": 0.0,
                "u_raw_px": float(raw[0]),
                "v_raw_px": float(raw[1]),
                "u_undist_px": float(und[0]),
                "v_undist_px": float(und[1]),
                "detected_aruco_markers": int(len(det["marker_ids"])),
                "detected_charuco_corners": int(len(det["charuco_ids"])),
            })

        if not self.saved_first_good[camera]:
            raw_path = self.output_dir / f"{camera}_first_good_raw.png"
            ann_path = self.output_dir / f"{camera}_first_good_annotated.png"

            cv2.imwrite(str(raw_path), bgr)
            cv2.imwrite(str(ann_path), self.make_annotated(bgr, det, camera))
            self.saved_first_good[camera] = True

            print(
                f"\n[{camera}] first good frame saved: "
                f"{len(det['marker_ids'])} ArUco markers, "
                f"{len(det['charuco_ids'])} ChArUco corners"
            )

        print(
            f"\r{camera}: accepted {idx:02d}/{self.args.frames} "
            f"(markers={len(det['marker_ids'])}, "
            f"charuco={len(det['charuco_ids'])})",
            end="",
            flush=True,
        )

        if idx >= self.args.frames:
            self.done[camera] = True
            print(f"\n[{camera}] DONE.")

        if all(self.done.values()):
            self.finalize()
            rclpy.shutdown()

    def finalize(self):
        raw_path = self.output_dir / "E4_charuco_12spread_per_frame.csv"
        formal_path = self.output_dir / "E4_calibration_12spread.csv"
        summary_path = self.output_dir / "summary.json"

        raw_fields = [
            "camera",
            "frame_index",
            "timestamp",
            "charuco_id",
            "paper_x_mm",
            "paper_y_mm",
            "paper_z_mm",
            "u_raw_px",
            "v_raw_px",
            "u_undist_px",
            "v_undist_px",
            "detected_aruco_markers",
            "detected_charuco_corners",
        ]

        with raw_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=raw_fields)
            w.writeheader()
            w.writerows(self.raw_rows)

        formal_rows = []

        for camera in ("ihawk1", "ihawk2"):
            for cid in self.formal_ids:
                g = self.geometry[cid]
                m = self.measurements[camera][cid]

                su = robust_stats(m["u_raw"])
                sv = robust_stats(m["v_raw"])
                suu = robust_stats(m["u_und"])
                svv = robust_stats(m["v_und"])

                formal_rows.append({
                    "camera": camera,
                    "charuco_id": cid,
                    "paper_x_mm": g["paper_x_mm"],
                    "paper_y_mm": g["paper_y_mm"],
                    "paper_z_mm": 0.0,

                    "u_raw_median_px": su["median"],
                    "v_raw_median_px": sv["median"],
                    "u_raw_mean_px": su["mean"],
                    "v_raw_mean_px": sv["mean"],
                    "u_raw_sd_px": su["sd"],
                    "v_raw_sd_px": sv["sd"],

                    "u_undist_median_px": suu["median"],
                    "v_undist_median_px": svv["median"],
                    "u_undist_mean_px": suu["mean"],
                    "v_undist_mean_px": svv["mean"],
                    "u_undist_sd_px": suu["sd"],
                    "v_undist_sd_px": svv["sd"],

                    "n_frames": suu["n"],
                })

        formal_fields = list(formal_rows[0].keys())

        with formal_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=formal_fields)
            w.writeheader()
            w.writerows(formal_rows)

        max_sd_by_camera = {}
        for camera in ("ihawk1", "ihawk2"):
            rows = [r for r in formal_rows if r["camera"] == camera]
            max_sd_by_camera[camera] = {
                "max_u_undist_sd_px": max(r["u_undist_sd_px"] for r in rows),
                "max_v_undist_sd_px": max(r["v_undist_sd_px"] for r in rows),
                "mean_u_undist_sd_px": float(np.mean([r["u_undist_sd_px"] for r in rows])),
                "mean_v_undist_sd_px": float(np.mean([r["v_undist_sd_px"] for r in rows])),
            }

        summary = {
            "board": {
                "squares_x": SQUARES_X,
                "squares_y": SQUARES_Y,
                "square_length_mm": SQUARE_LENGTH_MM,
                "marker_length_mm": MARKER_LENGTH_MM,
                "dictionary": "DICT_4X4_50",
                "outer_board_size_mm": [225.0, 175.0],
                "outer_paper_corners_mm": {
                    "TL": PAPER_TL.tolist(),
                    "TR": PAPER_TR.tolist(),
                    "BR": PAPER_BR.tolist(),
                    "BL": PAPER_BL.tolist(),
                },
                "charuco_corner_count": 48,
            },
            "formal_calibration": {
                "distribution": "12-spread",
                "formal_charuco_ids": self.formal_ids,
                "formal_points": [
                    self.geometry[cid] for cid in self.formal_ids
                ],
                "aggregation": "median across accepted frames",
                "frames_per_camera": self.args.frames,
                "model_fitting_done": False,
            },
            "camera_topics": {
                "ihawk1": self.topic1,
                "ihawk2": self.topic2,
            },
            "pixel_repeatability": max_sd_by_camera,
            "files": {
                "all48_geometry": str(self.output_dir / "E4_charuco_all48_geometry.csv"),
                "per_frame": str(raw_path),
                "formal_12spread": str(formal_path),
                "summary": str(summary_path),
            },
        }

        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n" + "=" * 88)
        print("CALIBRATION DATASET COMPLETE")
        print("=" * 88)
        print(f"Formal CSV: {formal_path}")
        print(f"Per-frame: {raw_path}")
        print()
        for camera in ("ihawk1", "ihawk2"):
            s = max_sd_by_camera[camera]
            print(
                f"{camera}: "
                f"mean SD(u,v)=({s['mean_u_undist_sd_px']:.4f},"
                f"{s['mean_v_undist_sd_px']:.4f}) px | "
                f"max SD(u,v)=({s['max_u_undist_sd_px']:.4f},"
                f"{s['max_v_undist_sd_px']:.4f}) px"
            )
        print()
        print("IMPORTANT:")
        print("- This CSV is the frozen image<->paper correspondence dataset.")
        print("- Robot coordinates were NOT used to define calibration GT.")
        print("- Next step is fitting Affine / Homography / PnP from this SAME CSV.")
        print("=" * 88)


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument(
        "--topic1",
        default=None,
        help="ihawk1 color sensor_msgs/Image topic. Auto-discovered if omitted.",
    )
    p.add_argument(
        "--topic2",
        default=None,
        help="ihawk2 color sensor_msgs/Image topic. Auto-discovered if omitted.",
    )
    p.add_argument(
        "--frames",
        type=int,
        default=20,
        help="Accepted frames per camera. Default: 20.",
    )
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_charuco_calibration",
    )

    return p.parse_args()


def main():
    args = parse_args()

    # Geometry sanity check before ROS starts.
    width_top = np.linalg.norm(PAPER_TR - PAPER_TL)
    width_bottom = np.linalg.norm(PAPER_BR - PAPER_BL)
    height_left = np.linalg.norm(PAPER_BL - PAPER_TL)
    height_right = np.linalg.norm(PAPER_BR - PAPER_TR)

    if not (
        abs(width_top - 225.0) < 1e-9
        and abs(width_bottom - 225.0) < 1e-9
        and abs(height_left - 175.0) < 1e-9
        and abs(height_right - 175.0) < 1e-9
    ):
        raise RuntimeError(
            "Physical outer board coordinates do not form a 225x175 mm rectangle."
        )

    rclpy.init()

    node = None
    try:
        node = CharucoCollector(args)
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] No formal dataset is frozen unless both cameras completed.")
    finally:
        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
