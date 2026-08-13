#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 formal ChArUco 12-spread camera->paper collector — V3

FROZEN physical paper_frame
---------------------------
paper +X = physical right
paper +Y = physical up

Physical board outer corners:
  LEFT-BOTTOM  = (-116, -92) mm
  RIGHT-BOTTOM = (+109, -92) mm
  RIGHT-TOP    = (+109, +83) mm
  LEFT-TOP     = (-116, +83) mm

FROZEN board placement used by this script:
  OpenCV ChArUco B00 (0,0)        -> physical LEFT-TOP  (-116,+83)
  OpenCV board +X                  -> physical RIGHT
  OpenCV board +Y                  -> physical DOWN

Therefore:
  paper_x = -116 + board_x
  paper_y =  +83 - board_y

IMPORTANT:
- The CAMERA IMAGE may look rotated/flipped relative to the robot/paper axes.
  That is fine. ChArUco IDs establish correspondence.
- This script never uses camera image "top-left/right" to define paper axes.
- This script does NOT move the robot and does NOT fit Affine/H/PnP.
- It only freezes the common image<->paper calibration correspondences.

Robust acquisition:
- 12 formal ChArUco corners are preselected geometrically (4 x 3 spread).
- A frame does NOT need to see all 12.
- Each formal corner is accumulated independently.
- Default target: 20 detections per corner, per camera.
- If incomplete after --max-seconds, a visibility report is saved but the
  formal dataset is NOT frozen.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


# ============================================================================
# FROZEN BOARD / PAPER GEOMETRY
# ============================================================================

SQUARES_X = 9
SQUARES_Y = 7
SQUARE_LENGTH_MM = 25.0
MARKER_LENGTH_MM = 18.0
BOARD_W_MM = 225.0
BOARD_H_MM = 175.0

DETECTION_SCALE = 3.0

PAPER_LEFT_BOTTOM  = np.array([-116.0, -92.0], dtype=np.float64)
PAPER_RIGHT_BOTTOM = np.array([+109.0, -92.0], dtype=np.float64)
PAPER_RIGHT_TOP    = np.array([+109.0, +83.0], dtype=np.float64)
PAPER_LEFT_TOP     = np.array([-116.0, +83.0], dtype=np.float64)

# Same 12 spread physical coordinates already planned earlier.
FORMAL_PAPER_X = [-91.0, -41.0, +34.0, +84.0]
FORMAL_PAPER_Y = [+58.0, -17.0, -67.0]

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

# Current E4 formal convention: undistorted coordinates; D=0.
CAMERA_D = {
    "ihawk1": np.zeros((5, 1), dtype=np.float64),
    "ihawk2": np.zeros((5, 1), dtype=np.float64),
}


def get_dictionary():
    if hasattr(cv2.aruco, "Dictionary_get"):
        return cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def make_board(dictionary):
    if hasattr(cv2.aruco, "CharucoBoard_create"):
        return cv2.aruco.CharucoBoard_create(
            SQUARES_X,
            SQUARES_Y,
            SQUARE_LENGTH_MM,
            MARKER_LENGTH_MM,
            dictionary,
        )
    return cv2.aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y),
        SQUARE_LENGTH_MM,
        MARKER_LENGTH_MM,
        dictionary,
    )


def make_detector_parameters():
    """
    Robust small-marker settings for the 640x400 Berxel color stream.

    Important for ChArUco + homography interpolation:
    OpenCV recommends NOT refining ArUco marker corners with SUBPIX before
    interpolateCornersCharuco(), because nearby chessboard edges can pull the
    marker corners. We therefore keep marker refinement OFF and refine the
    final ChArUco chessboard corners instead.
    """
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        p = cv2.aruco.DetectorParameters_create()
    else:
        p = cv2.aruco.DetectorParameters()

    if hasattr(cv2.aruco, "CORNER_REFINE_NONE"):
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE

    # Broader adaptive-threshold sweep than the OpenCV defaults.
    if hasattr(p, "adaptiveThreshWinSizeMin"):
        p.adaptiveThreshWinSizeMin = 3
    if hasattr(p, "adaptiveThreshWinSizeMax"):
        p.adaptiveThreshWinSizeMax = 63
    if hasattr(p, "adaptiveThreshWinSizeStep"):
        p.adaptiveThreshWinSizeStep = 4
    if hasattr(p, "adaptiveThreshConstant"):
        p.adaptiveThreshConstant = 7

    # Decode the canonical marker with more pixels per bit cell.
    if hasattr(p, "perspectiveRemovePixelPerCell"):
        p.perspectiveRemovePixelPerCell = 8

    # Slightly more permissive contour-size gate for small projected markers.
    if hasattr(p, "minMarkerPerimeterRate"):
        p.minMarkerPerimeterRate = 0.015

    return p


def get_board_charuco_corners(board):
    if hasattr(board, "chessboardCorners"):
        pts = np.asarray(board.chessboardCorners, dtype=np.float64)
    elif hasattr(board, "getChessboardCorners"):
        pts = np.asarray(board.getChessboardCorners(), dtype=np.float64)
    else:
        raise RuntimeError("Cannot access ChArUco chessboard corners.")
    return pts.reshape(-1, 3)


def board_to_paper(board_x_mm: float, board_y_mm: float):
    # B00 -> physical LEFT-TOP; board +Y points physically downward.
    paper_x = float(PAPER_LEFT_TOP[0] + board_x_mm)
    paper_y = float(PAPER_LEFT_TOP[1] - board_y_mm)
    return paper_x, paper_y


def build_geometry(board):
    obj = get_board_charuco_corners(board)
    if len(obj) != 48:
        raise RuntimeError(f"Expected 48 ChArUco corners, got {len(obj)}.")

    g = {}
    for cid, xyz in enumerate(obj):
        px, py = board_to_paper(float(xyz[0]), float(xyz[1]))
        g[int(cid)] = {
            "charuco_id": int(cid),
            "board_x_mm": float(xyz[0]),
            "board_y_mm": float(xyz[1]),
            "board_z_mm": float(xyz[2]),
            "paper_x_mm": px,
            "paper_y_mm": py,
            "paper_z_mm": 0.0,
        }
    return g


def choose_formal_ids(geometry):
    desired = [(x, y) for y in FORMAL_PAPER_Y for x in FORMAL_PAPER_X]
    selected = []

    for tx, ty in desired:
        best_id = None
        best_d = float("inf")
        for cid, g in geometry.items():
            d = math.hypot(g["paper_x_mm"] - tx, g["paper_y_mm"] - ty)
            if d < best_d:
                best_id, best_d = cid, d

        if best_id is None or best_d > 1e-6:
            raise RuntimeError(
                f"No exact ChArUco corner exists at paper ({tx},{ty}); "
                f"nearest distance={best_d}"
            )
        if best_id in selected:
            raise RuntimeError("Duplicate formal ChArUco ID selected.")
        selected.append(best_id)

    if len(selected) != 12:
        raise RuntimeError("Expected exactly 12 formal IDs.")
    return selected


def ros_stamp(msg):
    return float(msg.header.stamp.sec) + 1e-9 * float(msg.header.stamp.nanosec)


def stats(vals):
    a = np.asarray(vals, dtype=np.float64)
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "sd": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        "min": float(np.min(a)),
        "max": float(np.max(a)),
    }


class Collector(Node):
    def __init__(self, args):
        super().__init__("e4_charuco_12spread_collector_v3")
        self.args = args
        self.bridge = CvBridge()

        self.dictionary = get_dictionary()
        self.board = make_board(self.dictionary)
        self.params = make_detector_parameters()

        self.geometry = build_geometry(self.board)
        self.formal_ids = choose_formal_ids(self.geometry)
        self.formal_set = set(self.formal_ids)

        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = Path(args.out_root) / self.run_id
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.samples = {
            cam: defaultdict(lambda: {
                "u_raw": [], "v_raw": [],
                "u_und": [], "v_und": [],
            })
            for cam in ("ihawk1", "ihawk2")
        }

        self.per_frame_rows = []
        self.all_id_counts = {
            "ihawk1": defaultdict(int),
            "ihawk2": defaultdict(int),
        }
        self.frame_count = {"ihawk1": 0, "ihawk2": 0}
        self.best_formal_seen = {"ihawk1": -1, "ihawk2": -1}
        self.done = {"ihawk1": False, "ihawk2": False}
        self.finalized = False
        self.start_time = time.time()
        self.last_status_time = 0.0

        self._write_geometry()

        print("=" * 92, flush=True)
        print("E4 FORMAL CHARUCO 12-SPREAD COLLECTOR V4 — ROBUST DETECTION", flush=True)
        print("=" * 92, flush=True)
        print("PAPER FRAME (FROZEN):", flush=True)
        print("  +X = physical RIGHT", flush=True)
        print("  +Y = physical UP", flush=True)
        print("  physical LEFT-BOTTOM  = (-116,-92) mm", flush=True)
        print("  physical RIGHT-BOTTOM = (+109,-92) mm", flush=True)
        print("  physical RIGHT-TOP    = (+109,+83) mm", flush=True)
        print("  physical LEFT-TOP     = (-116,+83) mm", flush=True)
        print("", flush=True)
        print("BOARD->PAPER MAPPING USED:", flush=True)
        print("  B00 (0,0)       -> physical LEFT-TOP (-116,+83)", flush=True)
        print("  board +X        -> physical RIGHT", flush=True)
        print("  board +Y        -> physical DOWN", flush=True)
        print("  paper_x = -116 + board_x", flush=True)
        print("  paper_y =  +83 - board_y", flush=True)
        print("", flush=True)
        print("IMPORTANT: camera image orientation does NOT define paper axes.", flush=True)
        print("", flush=True)
        print("FROZEN 12-SPREAD POINTS:", flush=True)
        for cid in self.formal_ids:
            g = self.geometry[cid]
            print(
                f"  id={cid:2d}  "
                f"paper=({g['paper_x_mm']:+6.1f},{g['paper_y_mm']:+6.1f}) mm  "
                f"board=({g['board_x_mm']:5.1f},{g['board_y_mm']:5.1f}) mm",
                flush=True,
            )

        print("", flush=True)
        print(f"Detection processing scale: {DETECTION_SCALE:.1f}x", flush=True)
        print(f"Target detections: {args.samples} per formal corner, per camera", flush=True)
        print(f"Time limit: {args.max_seconds:.0f} s", flush=True)
        print(f"Output: {self.out_dir}", flush=True)
        print("=" * 92, flush=True)

        confirmation = input(
            "\nVERIFY PHYSICALLY: B00 is the board corner located at "
            "paper LEFT-TOP (-116,+83).\n"
            "Type YES to start acquisition: "
        ).strip().upper()

        if confirmation != "YES":
            raise RuntimeError("Orientation not confirmed; acquisition aborted.")

        self.sub1 = self.create_subscription(
            Image, args.topic1,
            lambda msg: self.on_image("ihawk1", msg),
            10,
        )
        self.sub2 = self.create_subscription(
            Image, args.topic2,
            lambda msg: self.on_image("ihawk2", msg),
            10,
        )

        self.timer = self.create_timer(1.0, self.on_timer)

    def _write_geometry(self):
        p = self.out_dir / "E4_charuco_all48_geometry.csv"
        fields = [
            "charuco_id", "is_formal_12spread",
            "board_x_mm", "board_y_mm", "board_z_mm",
            "paper_x_mm", "paper_y_mm", "paper_z_mm",
        ]
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for cid in sorted(self.geometry):
                row = dict(self.geometry[cid])
                row["is_formal_12spread"] = int(cid in self.formal_set)
                w.writerow({k: row[k] for k in fields})

    def detect(self, bgr):
        """
        Multi-stage robust ChArUco detection.

        1) grayscale
        2) 3x cubic upsample (helps small projected markers survive contour /
           threshold / code extraction; it does NOT create new optical detail)
        3) ArUco detection with broad adaptive-threshold windows
        4) board-aware refineDetectedMarkers() to recover rejected candidates
        5) ChArUco interpolation
        6) sub-pixel refinement of the FINAL ChArUco chessboard corners
        7) scale image coordinates back to the original 640x400 image
        """
        gray0 = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        scale = float(DETECTION_SCALE)
        gray = cv2.resize(
            gray0,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

        marker_corners, marker_ids, rejected = cv2.aruco.detectMarkers(
            gray,
            self.dictionary,
            parameters=self.params,
        )

        if marker_ids is None or len(marker_ids) == 0:
            return None

        # Recover likely board markers that failed the first decode pass.
        # Use board layout only (no model-specific camera pose fitting here).
        try:
            refined = cv2.aruco.refineDetectedMarkers(
                gray,
                self.board,
                marker_corners,
                marker_ids,
                rejected,
            )
            if refined is not None and len(refined) >= 2:
                marker_corners = refined[0]
                marker_ids = refined[1]
                if len(refined) >= 3:
                    rejected = refined[2]
        except Exception:
            # OpenCV Python bindings differ slightly across builds; the
            # collector remains usable even if this optional recovery fails.
            pass

        if marker_ids is None or len(marker_ids) == 0:
            return None

        # Homography-based ChArUco interpolation, common to all later models.
        retval, cc, ids = cv2.aruco.interpolateCornersCharuco(
            marker_corners,
            marker_ids,
            gray,
            self.board,
        )

        if ids is None or cc is None or int(retval) <= 0:
            return None

        ids = ids.reshape(-1).astype(int)
        corners_up = cc.reshape(-1, 2).astype(np.float32)

        # Refine FINAL ChArUco chessboard corners, not the ArUco marker corners.
        h, w = gray.shape[:2]
        safe = (
            (corners_up[:, 0] >= 8)
            & (corners_up[:, 0] < w - 8)
            & (corners_up[:, 1] >= 8)
            & (corners_up[:, 1] < h - 8)
        )

        if np.all(safe):
            refined_cc = corners_up.reshape(-1, 1, 2).copy()
            cv2.cornerSubPix(
                gray,
                refined_cc,
                (7, 7),
                (-1, -1),
                (
                    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                    60,
                    0.001,
                ),
            )
            corners_up = refined_cc.reshape(-1, 2)

        # Return coordinates in ORIGINAL camera pixel units.
        corners = (corners_up / scale).astype(np.float64)

        by_id = {
            int(cid): corners[i]
            for i, cid in enumerate(ids)
        }

        # Marker corners are only used for diagnostics/annotation; scale them
        # back to original pixel units as well.
        marker_corners_orig = [
            np.asarray(c, dtype=np.float32) / scale
            for c in marker_corners
        ]

        return {
            "gray": gray0,
            "marker_corners": marker_corners_orig,
            "marker_ids": marker_ids,
            "ids": ids,
            "corners": corners,
            "by_id": by_id,
        }

    def annotated(self, bgr, det, camera):
        out = bgr.copy()
        cv2.aruco.drawDetectedMarkers(
            out, det["marker_corners"], det["marker_ids"]
        )
        try:
            cv2.aruco.drawDetectedCornersCharuco(
                out,
                det["corners"].astype(np.float32).reshape(-1, 1, 2),
                det["ids"].reshape(-1, 1),
            )
        except Exception:
            pass

        for cid in self.formal_ids:
            if cid not in det["by_id"]:
                continue
            u, v = det["by_id"][cid]
            p = (int(round(u)), int(round(v)))
            cv2.circle(out, p, 7, (0, 0, 255), 2)
            cv2.putText(
                out, f"F{cid}", (p[0] + 7, p[1] - 7),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 255), 1, cv2.LINE_AA
            )

        cv2.putText(
            out,
            f"{camera}: red = frozen formal points visible in this frame",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
            (0, 0, 255), 2, cv2.LINE_AA
        )
        return out

    def on_image(self, camera, msg):
        if self.done[camera] or self.finalized:
            return

        self.frame_count[camera] += 1

        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception:
            return

        det = self.detect(bgr)
        if det is None:
            return

        for cid in det["ids"]:
            self.all_id_counts[camera][int(cid)] += 1

        formal_visible = [cid for cid in self.formal_ids if cid in det["by_id"]]

        # Save the best diagnostic frame seen so far.
        if len(formal_visible) > self.best_formal_seen[camera]:
            self.best_formal_seen[camera] = len(formal_visible)
            cv2.imwrite(
                str(self.out_dir / f"{camera}_best_raw.png"),
                bgr,
            )
            cv2.imwrite(
                str(self.out_dir / f"{camera}_best_annotated.png"),
                self.annotated(bgr, det, camera),
            )

        K = CAMERA_K[camera]
        D = CAMERA_D[camera]

        for cid in formal_visible:
            # Stop accumulating this point after target sample count.
            if len(self.samples[camera][cid]["u_raw"]) >= self.args.samples:
                continue

            uv = det["by_id"][cid]
            pts = np.asarray(uv, dtype=np.float64).reshape(1, 1, 2)
            und = cv2.undistortPoints(pts, K, D, P=K).reshape(2)

            self.samples[camera][cid]["u_raw"].append(float(uv[0]))
            self.samples[camera][cid]["v_raw"].append(float(uv[1]))
            self.samples[camera][cid]["u_und"].append(float(und[0]))
            self.samples[camera][cid]["v_und"].append(float(und[1]))

            g = self.geometry[cid]
            self.per_frame_rows.append({
                "camera": camera,
                "ros_frame_count": self.frame_count[camera],
                "timestamp": ros_stamp(msg),
                "charuco_id": cid,
                "paper_x_mm": g["paper_x_mm"],
                "paper_y_mm": g["paper_y_mm"],
                "paper_z_mm": 0.0,
                "u_raw_px": float(uv[0]),
                "v_raw_px": float(uv[1]),
                "u_undist_px": float(und[0]),
                "v_undist_px": float(und[1]),
                "detected_aruco_markers": int(len(det["marker_ids"])),
                "detected_charuco_corners": int(len(det["ids"])),
            })

        counts = [
            len(self.samples[camera][cid]["u_raw"])
            for cid in self.formal_ids
        ]
        if min(counts) >= self.args.samples:
            self.done[camera] = True
            print(f"\n[{camera}] COMPLETE: all 12 points reached {self.args.samples}.",
                  flush=True)

        if all(self.done.values()):
            self.finalize(success=True)

    def on_timer(self):
        if self.finalized:
            return

        elapsed = time.time() - self.start_time

        parts = []
        for camera in ("ihawk1", "ihawk2"):
            counts = [
                len(self.samples[camera][cid]["u_raw"])
                for cid in self.formal_ids
            ]
            n_complete = sum(c >= self.args.samples for c in counts)
            parts.append(
                f"{camera}: min={min(counts):02d}, "
                f"complete={n_complete}/12, bestFrame={self.best_formal_seen[camera]}"
            )

        print(
            f"[{elapsed:5.1f}s] " + " | ".join(parts),
            flush=True
        )

        if elapsed >= self.args.max_seconds and not all(self.done.values()):
            print("\n[TIME LIMIT] Formal dataset NOT frozen.", flush=True)
            self.finalize(success=False)

    def write_visibility_report(self):
        path = self.out_dir / "visibility_report.csv"
        fields = [
            "camera", "charuco_id", "is_formal_12spread",
            "paper_x_mm", "paper_y_mm",
            "all_detection_count",
            "formal_sample_count",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for camera in ("ihawk1", "ihawk2"):
                for cid in sorted(self.geometry):
                    g = self.geometry[cid]
                    w.writerow({
                        "camera": camera,
                        "charuco_id": cid,
                        "is_formal_12spread": int(cid in self.formal_set),
                        "paper_x_mm": g["paper_x_mm"],
                        "paper_y_mm": g["paper_y_mm"],
                        "all_detection_count":
                            self.all_id_counts[camera].get(cid, 0),
                        "formal_sample_count":
                            len(self.samples[camera][cid]["u_raw"])
                            if cid in self.formal_set else 0,
                    })
        return path

    def write_per_frame(self):
        path = self.out_dir / "E4_charuco_12spread_per_frame.csv"
        fields = [
            "camera", "ros_frame_count", "timestamp", "charuco_id",
            "paper_x_mm", "paper_y_mm", "paper_z_mm",
            "u_raw_px", "v_raw_px",
            "u_undist_px", "v_undist_px",
            "detected_aruco_markers", "detected_charuco_corners",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(self.per_frame_rows)
        return path

    def finalize(self, success: bool):
        if self.finalized:
            return
        self.finalized = True

        per_frame_path = self.write_per_frame()
        visibility_path = self.write_visibility_report()

        summary = {
            "success": bool(success),
            "formal_dataset_frozen": bool(success),
            "paper_frame": {
                "x_direction": "physical right",
                "y_direction": "physical up",
                "left_bottom_mm": PAPER_LEFT_BOTTOM.tolist(),
                "right_bottom_mm": PAPER_RIGHT_BOTTOM.tolist(),
                "right_top_mm": PAPER_RIGHT_TOP.tolist(),
                "left_top_mm": PAPER_LEFT_TOP.tolist(),
            },
            "board_to_paper": {
                "B00_board_mm": [0.0, 0.0],
                "B00_paper_mm": PAPER_LEFT_TOP.tolist(),
                "formula": [
                    "paper_x = -116 + board_x",
                    "paper_y = +83 - board_y",
                ],
            },
            "formal_ids": self.formal_ids,
            "formal_points": [self.geometry[cid] for cid in self.formal_ids],
            "target_samples_per_point": self.args.samples,
            "elapsed_seconds": time.time() - self.start_time,
            "camera_topics": {
                "ihawk1": self.args.topic1,
                "ihawk2": self.args.topic2,
            },
            "files": {
                "per_frame": str(per_frame_path),
                "visibility": str(visibility_path),
            },
        }

        if success:
            formal_path = self.out_dir / "E4_calibration_12spread.csv"
            rows = []

            for camera in ("ihawk1", "ihawk2"):
                for cid in self.formal_ids:
                    g = self.geometry[cid]
                    m = self.samples[camera][cid]

                    su = stats(m["u_raw"])
                    sv = stats(m["v_raw"])
                    suu = stats(m["u_und"])
                    svv = stats(m["v_und"])

                    rows.append({
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

            with formal_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

            summary["files"]["formal_12spread"] = str(formal_path)

            repeatability = {}
            for camera in ("ihawk1", "ihawk2"):
                cr = [r for r in rows if r["camera"] == camera]
                repeatability[camera] = {
                    "mean_u_sd_px": float(np.mean(
                        [r["u_undist_sd_px"] for r in cr]
                    )),
                    "mean_v_sd_px": float(np.mean(
                        [r["v_undist_sd_px"] for r in cr]
                    )),
                    "max_u_sd_px": float(np.max(
                        [r["u_undist_sd_px"] for r in cr]
                    )),
                    "max_v_sd_px": float(np.max(
                        [r["v_undist_sd_px"] for r in cr]
                    )),
                }
            summary["pixel_repeatability"] = repeatability

        summary_path = self.out_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n" + "=" * 92, flush=True)
        if success:
            print("FORMAL 12-SPREAD DATASET COMPLETE — FROZEN", flush=True)
            print("=" * 92, flush=True)
            print(
                f"Formal CSV: {summary['files']['formal_12spread']}",
                flush=True
            )
            for cam, s in summary["pixel_repeatability"].items():
                print(
                    f"{cam}: mean SD(u,v)=("
                    f"{s['mean_u_sd_px']:.4f},"
                    f"{s['mean_v_sd_px']:.4f}) px | "
                    f"max SD(u,v)=("
                    f"{s['max_u_sd_px']:.4f},"
                    f"{s['max_v_sd_px']:.4f}) px",
                    flush=True,
                )
        else:
            print("INCOMPLETE — DO NOT FREEZE CALIBRATION", flush=True)
            print("=" * 92, flush=True)
            print(
                "Some formal points did not reach the required sample count.",
                flush=True,
            )
            print(
                "Use visibility_report.csv to see exactly which IDs are missing.",
                flush=True,
            )

        print(f"Per-frame:  {per_frame_path}", flush=True)
        print(f"Visibility: {visibility_path}", flush=True)
        print(f"Summary:    {summary_path}", flush=True)
        print("=" * 92, flush=True)

        if rclpy.ok():
            rclpy.shutdown()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--topic1", default="/ihawk1/color/color_raw")
    p.add_argument("--topic2", default="/ihawk2/color/color_raw")
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--max-seconds", type=float, default=60.0)
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_charuco_calibration_v4",
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Physical rectangle sanity checks.
    assert np.isclose(
        np.linalg.norm(PAPER_RIGHT_BOTTOM - PAPER_LEFT_BOTTOM),
        BOARD_W_MM
    )
    assert np.isclose(
        np.linalg.norm(PAPER_LEFT_TOP - PAPER_LEFT_BOTTOM),
        BOARD_H_MM
    )

    rclpy.init()
    node: Optional[Collector] = None

    try:
        node = Collector(args)
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Dataset is not frozen.", flush=True)
        if node is not None and not node.finalized:
            node.finalize(success=False)
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
