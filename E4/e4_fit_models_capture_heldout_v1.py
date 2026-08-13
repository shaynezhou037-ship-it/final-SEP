#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 Model Freeze + 9 Held-out Vision Validation
==============================================

THIS SCRIPT DOES NOT MOVE THE ROBOT.

It performs the next E4 stage after the frozen 12-spread ChArUco calibration:

1) Read the frozen 12-point calibration CSV.
2) Fit, once and identically for each camera:
     - Affine: ordinary least squares
     - Homography: cv2.findHomography(..., method=0), NO RANSAC
     - PnP: cv2.solvePnP(..., SOLVEPNP_IPPE), K fixed, D=0
3) Pre-freeze 9 NEW ChArUco held-out points that are not in the 12 calibration points.
4) Capture 20 detections per held-out point per camera using the same robust V4 detector.
5) Aggregate each held-out pixel by median.
6) Evaluate Affine / Homography / PnP on exactly the same 9 GT points.
7) Save model JSON files + held-out CSVs + summary.

FROZEN PAPER FRAME
------------------
+X = physical RIGHT
+Y = physical UP

Physical board corners:
  left-bottom  = (-116, -92) mm
  right-bottom = (+109, -92) mm
  right-top    = (+109, +83) mm
  left-top     = (-116, +83) mm

OpenCV ChArUco board B00 is physically left-top:
  paper_x = -116 + board_x
  paper_y =  +83 - board_y

FROZEN 12 calibration points:
  IDs 0,2,5,7,24,26,29,31,40,42,45,47

PRE-FROZEN 9 held-out points:
  IDs 9,11,14,
      17,19,22,
      33,35,38

These form a 3 x 3 interior spread grid:
  (-66,+33)  (-16,+33)  (+59,+33)
  (-66, +8)  (-16, +8)  (+59, +8)
  (-66,-42)  (-16,-42)  (+59,-42)

They are selected geometrically BEFORE looking at their model errors.
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
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


# =============================================================================
# FROZEN GEOMETRY / METHOD CONFIG
# =============================================================================

SQUARES_X = 9
SQUARES_Y = 7
SQUARE_LENGTH_MM = 25.0
MARKER_LENGTH_MM = 18.0
DETECTION_SCALE = 3.0

CALIB_IDS = [0, 2, 5, 7, 24, 26, 29, 31, 40, 42, 45, 47]
HELDOUT_IDS = [9, 11, 14, 17, 19, 22, 33, 35, 38]

EXPECTED_HELDOUT_PAPER = {
    9:  (-66.0, +33.0),
    11: (-16.0, +33.0),
    14: (+59.0, +33.0),
    17: (-66.0,  +8.0),
    19: (-16.0,  +8.0),
    22: (+59.0,  +8.0),
    33: (-66.0, -42.0),
    35: (-16.0, -42.0),
    38: (+59.0, -42.0),
}

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

CAMERA_D = {
    "ihawk1": np.zeros((5, 1), dtype=np.float64),
    "ihawk2": np.zeros((5, 1), dtype=np.float64),
}

# Current frozen paper -> robot registration.
# Used ONLY to preview future robot targets. It is not involved in vision fitting.
PAPER_TO_ROBOT = {
    "robot_x": [-0.074105303, +0.992259200, +187.854293495],
    "robot_y": [-0.986716324, -0.006933251,   -4.851741339],
    "robot_z": [+0.001405397, +0.006345201, -118.909081155],
}

SAFE_HOVER_MM = 40.0


# =============================================================================
# CHArUCO DETECTION — SAME V4 PRINCIPLE
# =============================================================================

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
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        p = cv2.aruco.DetectorParameters_create()
    else:
        p = cv2.aruco.DetectorParameters()

    # Marker-corner subpixel refinement OFF before ChArUco interpolation.
    if hasattr(cv2.aruco, "CORNER_REFINE_NONE"):
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE

    if hasattr(p, "adaptiveThreshWinSizeMin"):
        p.adaptiveThreshWinSizeMin = 3
    if hasattr(p, "adaptiveThreshWinSizeMax"):
        p.adaptiveThreshWinSizeMax = 63
    if hasattr(p, "adaptiveThreshWinSizeStep"):
        p.adaptiveThreshWinSizeStep = 4
    if hasattr(p, "adaptiveThreshConstant"):
        p.adaptiveThreshConstant = 7
    if hasattr(p, "perspectiveRemovePixelPerCell"):
        p.perspectiveRemovePixelPerCell = 8
    if hasattr(p, "minMarkerPerimeterRate"):
        p.minMarkerPerimeterRate = 0.015

    return p


def robust_detect_charuco(bgr, dictionary, board, params):
    gray0 = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    scale = float(DETECTION_SCALE)
    gray = cv2.resize(
        gray0, None,
        fx=scale, fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )

    marker_corners, marker_ids, rejected = cv2.aruco.detectMarkers(
        gray,
        dictionary,
        parameters=params,
    )

    if marker_ids is None or len(marker_ids) == 0:
        return None

    try:
        refined = cv2.aruco.refineDetectedMarkers(
            gray,
            board,
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
        pass

    if marker_ids is None or len(marker_ids) == 0:
        return None

    retval, cc, ids = cv2.aruco.interpolateCornersCharuco(
        marker_corners,
        marker_ids,
        gray,
        board,
    )

    if ids is None or cc is None or int(retval) <= 0:
        return None

    ids = ids.reshape(-1).astype(int)
    corners_up = cc.reshape(-1, 2).astype(np.float32)

    h, w = gray.shape[:2]
    safe = (
        (corners_up[:, 0] >= 8)
        & (corners_up[:, 0] < w - 8)
        & (corners_up[:, 1] >= 8)
        & (corners_up[:, 1] < h - 8)
    )

    if np.all(safe):
        tmp = corners_up.reshape(-1, 1, 2).copy()
        cv2.cornerSubPix(
            gray,
            tmp,
            (7, 7),
            (-1, -1),
            (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                60,
                0.001,
            ),
        )
        corners_up = tmp.reshape(-1, 2)

    corners = (corners_up / scale).astype(np.float64)

    by_id = {
        int(cid): corners[i]
        for i, cid in enumerate(ids)
    }

    marker_corners_orig = [
        np.asarray(c, dtype=np.float32) / scale
        for c in marker_corners
    ]

    return {
        "marker_corners": marker_corners_orig,
        "marker_ids": marker_ids,
        "ids": ids,
        "corners": corners,
        "by_id": by_id,
    }


# =============================================================================
# FILE / DATA HELPERS
# =============================================================================

def read_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def percentile95(vals):
    return float(np.percentile(np.asarray(vals, dtype=np.float64), 95))


def metric_summary(errors):
    a = np.asarray(errors, dtype=np.float64)
    return {
        "n": int(len(a)),
        "mean_mm": float(np.mean(a)),
        "rmse_mm": float(np.sqrt(np.mean(a * a))),
        "median_mm": float(np.median(a)),
        "sd_mm": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        "p95_mm": percentile95(a),
        "max_mm": float(np.max(a)),
    }


def pixel_stats(values):
    a = np.asarray(values, dtype=np.float64)
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "sd": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        "min": float(np.min(a)),
        "max": float(np.max(a)),
    }


def paper_to_robot(px, py):
    def f(c):
        return c[0] * px + c[1] * py + c[2]

    return (
        f(PAPER_TO_ROBOT["robot_x"]),
        f(PAPER_TO_ROBOT["robot_y"]),
        f(PAPER_TO_ROBOT["robot_z"]),
    )


# =============================================================================
# MODEL FITTING
# =============================================================================

def fit_affine(img_uv: np.ndarray, paper_xy: np.ndarray):
    # [u v 1] @ B = [X Y]
    A = np.column_stack([
        img_uv[:, 0],
        img_uv[:, 1],
        np.ones(len(img_uv)),
    ])
    B, residuals, rank, s = np.linalg.lstsq(A, paper_xy, rcond=None)

    # Save as conventional 2x3 matrix:
    # [X]   [a b c] [u]
    # [Y] = [d e f] [v]
    #                 [1]
    M = B.T
    pred = A @ B
    return M, pred, int(rank)


def affine_predict(M, uv):
    uv = np.asarray(uv, dtype=np.float64).reshape(2)
    return M @ np.array([uv[0], uv[1], 1.0], dtype=np.float64)


def fit_homography(img_uv: np.ndarray, paper_xy: np.ndarray):
    H, mask = cv2.findHomography(
        img_uv.astype(np.float64),
        paper_xy.astype(np.float64),
        method=0,
    )
    if H is None:
        raise RuntimeError("cv2.findHomography(method=0) failed.")

    pred = cv2.perspectiveTransform(
        img_uv.reshape(-1, 1, 2).astype(np.float64),
        H,
    ).reshape(-1, 2)

    return H, pred


def homography_predict(H, uv):
    p = np.asarray(uv, dtype=np.float64).reshape(1, 1, 2)
    return cv2.perspectiveTransform(p, H).reshape(2)


def fit_pnp_ippe(camera, img_uv, paper_xy):
    K = CAMERA_K[camera]
    D = CAMERA_D[camera]

    obj = np.column_stack([
        paper_xy[:, 0],
        paper_xy[:, 1],
        np.zeros(len(paper_xy)),
    ]).astype(np.float64)

    ok, rvec, tvec = cv2.solvePnP(
        obj,
        img_uv.astype(np.float64),
        K,
        D,
        flags=cv2.SOLVEPNP_IPPE,
    )

    if not ok:
        raise RuntimeError(f"{camera}: SOLVEPNP_IPPE failed.")

    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
    proj = proj.reshape(-1, 2)
    reproj = np.linalg.norm(proj - img_uv, axis=1)

    paper_pred = np.vstack([
        pnp_ray_plane_predict(camera, rvec, tvec, uv)
        for uv in img_uv
    ])

    return rvec, tvec, paper_pred, reproj


def pnp_ray_plane_predict(camera, rvec, tvec, uv):
    """
    solvePnP gives:
        X_cam = R * X_paper + t

    Convert image ray to paper frame and intersect paper Z=0.
    """
    K = CAMERA_K[camera]
    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))

    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    C_paper = -R.T @ t

    uv1 = np.array([float(uv[0]), float(uv[1]), 1.0], dtype=np.float64)
    ray_cam = np.linalg.inv(K) @ uv1
    ray_paper = R.T @ ray_cam

    if abs(ray_paper[2]) < 1e-12:
        raise RuntimeError("PnP ray is parallel to paper plane.")

    lam = -C_paper[2] / ray_paper[2]
    P = C_paper + lam * ray_paper
    return P[:2]


def fit_all_models(calib_rows, output_dir):
    models = {}
    training_summary = {}

    for camera in ("ihawk1", "ihawk2"):
        rr = [r for r in calib_rows if r["camera"] == camera]

        if len(rr) != 12:
            raise RuntimeError(
                f"{camera}: expected 12 formal calibration rows, got {len(rr)}."
            )

        ids = [int(r["charuco_id"]) for r in rr]
        if set(ids) != set(CALIB_IDS):
            raise RuntimeError(
                f"{camera}: calibration IDs differ from frozen set.\n"
                f"Found={sorted(ids)}"
            )

        # Stable row order.
        rr = sorted(rr, key=lambda r: CALIB_IDS.index(int(r["charuco_id"])))

        img = np.array([
            [
                float(r["u_undist_median_px"]),
                float(r["v_undist_median_px"]),
            ]
            for r in rr
        ], dtype=np.float64)

        paper = np.array([
            [
                float(r["paper_x_mm"]),
                float(r["paper_y_mm"]),
            ]
            for r in rr
        ], dtype=np.float64)

        # Affine OLS
        M, pred_A, affine_rank = fit_affine(img, paper)
        err_A = np.linalg.norm(pred_A - paper, axis=1)

        # Homography, direct, no RANSAC
        H, pred_H = fit_homography(img, paper)
        err_H = np.linalg.norm(pred_H - paper, axis=1)

        # PnP IPPE
        rvec, tvec, pred_P, reproj_P = fit_pnp_ippe(camera, img, paper)
        err_P = np.linalg.norm(pred_P - paper, axis=1)

        camera_model = {
            "camera": camera,
            "input_pixel": "u_undist_median_px, v_undist_median_px",
            "distortion_used_for_fit": [0, 0, 0, 0, 0],
            "camera_matrix": CAMERA_K[camera].tolist(),

            "affine": {
                "method": "ordinary least squares",
                "ransac": False,
                "matrix_2x3_image_to_paper": M.tolist(),
                "rank": affine_rank,
            },

            "homography": {
                "method": "cv2.findHomography(method=0)",
                "ransac": False,
                "matrix_3x3_image_to_paper": H.tolist(),
            },

            "pnp": {
                "method": "cv2.solvePnP",
                "solver": "SOLVEPNP_IPPE",
                "object_frame": "paper_frame, Z=0 mm",
                "rvec_paper_to_camera": rvec.reshape(3).tolist(),
                "tvec_paper_to_camera_mm": tvec.reshape(3).tolist(),
                "prediction": "camera ray intersect paper Z=0",
            },

            "calibration_charuco_ids": CALIB_IDS,
            "n_calibration_points": 12,
        }

        model_path = output_dir / f"{camera}_E4_frozen_models.json"
        model_path.write_text(
            json.dumps(camera_model, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        models[camera] = {
            "affine_M": M,
            "homography_H": H,
            "pnp_rvec": rvec,
            "pnp_tvec": tvec,
        }

        training_summary[camera] = {
            "affine": metric_summary(err_A),
            "homography": metric_summary(err_H),
            "pnp_plane_xy": metric_summary(err_P),
            "pnp_reprojection_px": {
                "mean_px": float(np.mean(reproj_P)),
                "rmse_px": float(np.sqrt(np.mean(reproj_P ** 2))),
                "max_px": float(np.max(reproj_P)),
            },
            "model_file": str(model_path),
        }

    return models, training_summary


# =============================================================================
# TARGET SELECTION / VALIDATION
# =============================================================================

def validate_geometry(geometry_rows):
    g = {int(r["charuco_id"]): r for r in geometry_rows}

    for cid in CALIB_IDS + HELDOUT_IDS:
        if cid not in g:
            raise RuntimeError(f"Geometry missing ChArUco id {cid}.")

    # Held-out IDs must not overlap calibration.
    overlap = set(CALIB_IDS) & set(HELDOUT_IDS)
    if overlap:
        raise RuntimeError(f"Calibration/heldout overlap: {overlap}")

    for cid in HELDOUT_IDS:
        r = g[cid]
        got = (float(r["paper_x_mm"]), float(r["paper_y_mm"]))
        exp = EXPECTED_HELDOUT_PAPER[cid]
        if not (
            abs(got[0] - exp[0]) < 1e-9
            and abs(got[1] - exp[1]) < 1e-9
        ):
            raise RuntimeError(
                f"Heldout geometry mismatch for id {cid}: "
                f"got {got}, expected {exp}"
            )

        if int(float(r["is_formal_12spread"])) != 0:
            raise RuntimeError(
                f"Heldout id {cid} is marked as a calibration point."
            )

    return g


def make_target_rows(geometry_by_id):
    rows = []
    for i, cid in enumerate(HELDOUT_IDS, start=1):
        g = geometry_by_id[cid]
        px = float(g["paper_x_mm"])
        py = float(g["paper_y_mm"])
        rx, ry, rz = paper_to_robot(px, py)

        rows.append({
            "target_id": f"T{i:02d}",
            "charuco_id": cid,
            "paper_x_mm": px,
            "paper_y_mm": py,
            "paper_z_mm": 0.0,

            "robot_surface_x_mm_preview": rx,
            "robot_surface_y_mm_preview": ry,
            "robot_surface_z_mm_preview": rz,

            "robot_high_x_mm_preview": rx,
            "robot_high_y_mm_preview": ry,
            "robot_high_z_mm_preview": rz + SAFE_HOVER_MM,

            "status": "PRE_FROZEN_HELDOUT_NOT_USED_FOR_FIT",
        })

    return rows


# =============================================================================
# ROS HELD-OUT CAPTURE
# =============================================================================

class HeldoutCapture(Node):
    def __init__(
        self,
        args,
        geometry_by_id,
        models,
        training_summary,
        output_dir,
        target_rows,
    ):
        super().__init__("e4_heldout_vision_capture")
        self.args = args
        self.geometry = geometry_by_id
        self.models = models
        self.training_summary = training_summary
        self.output_dir = output_dir
        self.target_rows = target_rows

        self.bridge = CvBridge()
        self.dictionary = get_dictionary()
        self.board = make_board(self.dictionary)
        self.params = make_detector_parameters()

        self.samples = {
            cam: defaultdict(lambda: {"u": [], "v": []})
            for cam in ("ihawk1", "ihawk2")
        }

        self.per_frame_rows = []
        self.done = {"ihawk1": False, "ihawk2": False}
        self.best_seen = {"ihawk1": -1, "ihawk2": -1}
        self.frame_count = {"ihawk1": 0, "ihawk2": 0}
        self.finalized = False
        self.start_time = time.time()

        print("\n" + "=" * 92, flush=True)
        print("PRE-FROZEN 9 HELD-OUT TARGETS — NOT USED FOR MODEL FIT", flush=True)
        print("=" * 92, flush=True)
        for r in target_rows:
            print(
                f"{r['target_id']}  id={r['charuco_id']:2d}  "
                f"paper=({r['paper_x_mm']:+6.1f},{r['paper_y_mm']:+6.1f}) mm  "
                f"robot_surface≈("
                f"{r['robot_surface_x_mm_preview']:.1f},"
                f"{r['robot_surface_y_mm_preview']:.1f},"
                f"{r['robot_surface_z_mm_preview']:.1f}) mm",
                flush=True,
            )
        print("=" * 92, flush=True)

        confirm = input(
            "\nThese 9 IDs were selected BEFORE held-out errors were observed.\n"
            "Cameras and ChArUco board must still be in the SAME frozen pose.\n"
            "Type YES to capture held-out pixels: "
        ).strip().upper()

        if confirm != "YES":
            raise RuntimeError("Held-out capture aborted by user.")

        self.sub1 = self.create_subscription(
            Image,
            args.topic1,
            lambda msg: self.on_image("ihawk1", msg),
            10,
        )
        self.sub2 = self.create_subscription(
            Image,
            args.topic2,
            lambda msg: self.on_image("ihawk2", msg),
            10,
        )
        self.timer = self.create_timer(1.0, self.on_timer)

    def make_annotated(self, bgr, det, camera):
        out = bgr.copy()

        cv2.aruco.drawDetectedMarkers(
            out,
            det["marker_corners"],
            det["marker_ids"],
        )

        try:
            cv2.aruco.drawDetectedCornersCharuco(
                out,
                det["corners"].astype(np.float32).reshape(-1, 1, 2),
                det["ids"].reshape(-1, 1),
            )
        except Exception:
            pass

        for cid in HELDOUT_IDS:
            if cid not in det["by_id"]:
                continue

            u, v = det["by_id"][cid]
            p = (int(round(u)), int(round(v)))
            cv2.circle(out, p, 8, (0, 0, 255), 2)
            cv2.putText(
                out,
                f"H{cid}",
                (p[0] + 7, p[1] - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )

        cv2.putText(
            out,
            f"{camera}: red = 9 formal held-out points",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        return out

    def on_image(self, camera, msg):
        if self.finalized or self.done[camera]:
            return

        self.frame_count[camera] += 1

        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception:
            return

        det = robust_detect_charuco(
            bgr,
            self.dictionary,
            self.board,
            self.params,
        )
        if det is None:
            return

        visible = [cid for cid in HELDOUT_IDS if cid in det["by_id"]]

        if len(visible) > self.best_seen[camera]:
            self.best_seen[camera] = len(visible)
            cv2.imwrite(
                str(self.output_dir / f"{camera}_heldout_best_raw.png"),
                bgr,
            )
            cv2.imwrite(
                str(self.output_dir / f"{camera}_heldout_best_annotated.png"),
                self.make_annotated(bgr, det, camera),
            )

        for cid in visible:
            if len(self.samples[camera][cid]["u"]) >= self.args.samples:
                continue

            u, v = det["by_id"][cid]

            # D=0 formal convention: undistorted == refined original pixel.
            # Still run through undistortPoints explicitly for method traceability.
            K = CAMERA_K[camera]
            D = CAMERA_D[camera]
            und = cv2.undistortPoints(
                np.array([[[u, v]]], dtype=np.float64),
                K,
                D,
                P=K,
            ).reshape(2)

            self.samples[camera][cid]["u"].append(float(und[0]))
            self.samples[camera][cid]["v"].append(float(und[1]))

            g = self.geometry[cid]
            self.per_frame_rows.append({
                "camera": camera,
                "ros_frame_count": self.frame_count[camera],
                "charuco_id": cid,
                "paper_x_gt_mm": float(g["paper_x_mm"]),
                "paper_y_gt_mm": float(g["paper_y_mm"]),
                "u_undist_px": float(und[0]),
                "v_undist_px": float(und[1]),
                "detected_aruco_markers": int(len(det["marker_ids"])),
                "detected_charuco_corners": int(len(det["ids"])),
            })

        counts = [
            len(self.samples[camera][cid]["u"])
            for cid in HELDOUT_IDS
        ]

        if min(counts) >= self.args.samples:
            self.done[camera] = True
            print(
                f"\n[{camera}] HELD-OUT COMPLETE: "
                f"9/9 points × {self.args.samples}.",
                flush=True,
            )

        if all(self.done.values()):
            self.finalize(success=True)

    def on_timer(self):
        if self.finalized:
            return

        elapsed = time.time() - self.start_time

        parts = []
        for camera in ("ihawk1", "ihawk2"):
            counts = [
                len(self.samples[camera][cid]["u"])
                for cid in HELDOUT_IDS
            ]
            complete = sum(c >= self.args.samples for c in counts)
            parts.append(
                f"{camera}: min={min(counts):02d}, "
                f"complete={complete}/9, bestFrame={self.best_seen[camera]}"
            )

        print(
            f"[{elapsed:5.1f}s] " + " | ".join(parts),
            flush=True,
        )

        if elapsed >= self.args.max_seconds and not all(self.done.values()):
            self.finalize(success=False)

    def finalize(self, success):
        if self.finalized:
            return
        self.finalized = True

        write_csv(
            self.output_dir / "E4_heldout_9points_per_frame.csv",
            self.per_frame_rows,
        )

        if not success:
            print("\n" + "=" * 92, flush=True)
            print("HELD-OUT CAPTURE INCOMPLETE — DO NOT FREEZE RESULTS", flush=True)
            print("=" * 92, flush=True)

            for camera in ("ihawk1", "ihawk2"):
                print(camera, flush=True)
                for cid in HELDOUT_IDS:
                    print(
                        f"  id={cid:2d}: "
                        f"{len(self.samples[camera][cid]['u'])}/"
                        f"{self.args.samples}",
                        flush=True,
                    )

            if rclpy.ok():
                rclpy.shutdown()
            return

        heldout_pixel_rows = []
        result_rows = []

        for camera in ("ihawk1", "ihawk2"):
            model = self.models[camera]

            for target_index, cid in enumerate(HELDOUT_IDS, start=1):
                g = self.geometry[cid]
                px_gt = float(g["paper_x_mm"])
                py_gt = float(g["paper_y_mm"])

                su = pixel_stats(self.samples[camera][cid]["u"])
                sv = pixel_stats(self.samples[camera][cid]["v"])

                uv = np.array([su["median"], sv["median"]], dtype=np.float64)

                heldout_pixel_rows.append({
                    "camera": camera,
                    "target_id": f"T{target_index:02d}",
                    "charuco_id": cid,
                    "paper_x_gt_mm": px_gt,
                    "paper_y_gt_mm": py_gt,
                    "u_undist_median_px": su["median"],
                    "v_undist_median_px": sv["median"],
                    "u_undist_sd_px": su["sd"],
                    "v_undist_sd_px": sv["sd"],
                    "n_frames": su["n"],
                })

                predictions = {
                    "Affine": affine_predict(model["affine_M"], uv),
                    "Homography": homography_predict(
                        model["homography_H"], uv
                    ),
                    "PnP_IPPE": pnp_ray_plane_predict(
                        camera,
                        model["pnp_rvec"],
                        model["pnp_tvec"],
                        uv,
                    ),
                }

                for method, pred in predictions.items():
                    dx = float(pred[0] - px_gt)
                    dy = float(pred[1] - py_gt)
                    err = math.hypot(dx, dy)

                    result_rows.append({
                        "camera": camera,
                        "target_id": f"T{target_index:02d}",
                        "charuco_id": cid,
                        "method": method,

                        "paper_x_gt_mm": px_gt,
                        "paper_y_gt_mm": py_gt,

                        "u_undist_median_px": float(uv[0]),
                        "v_undist_median_px": float(uv[1]),

                        "paper_x_pred_mm": float(pred[0]),
                        "paper_y_pred_mm": float(pred[1]),

                        "dx_mm": dx,
                        "dy_mm": dy,
                        "xy_error_mm": err,
                    })

        pixels_path = self.output_dir / "E4_heldout_9points_pixels.csv"
        results_path = self.output_dir / "E4_heldout_model_results.csv"
        write_csv(pixels_path, heldout_pixel_rows)
        write_csv(results_path, result_rows)

        heldout_summary = {}
        for camera in ("ihawk1", "ihawk2"):
            heldout_summary[camera] = {}
            for method in ("Affine", "Homography", "PnP_IPPE"):
                errs = [
                    float(r["xy_error_mm"])
                    for r in result_rows
                    if r["camera"] == camera and r["method"] == method
                ]
                heldout_summary[camera][method] = metric_summary(errs)

        summary = {
            "status": "E4_VISION_MODELS_AND_9_HELDOUT_FROZEN",
            "formal_robot_trials_started": False,

            "method_freeze": {
                "Affine": "ordinary least-squares 2-D affine; no RANSAC",
                "Homography": "cv2.findHomography(method=0); no RANSAC",
                "PnP": (
                    "cv2.solvePnP SOLVEPNP_IPPE; fixed K; "
                    "undistorted pixels; D=0; ray-plane Z=0 prediction"
                ),
                "fairness": (
                    "same 12 calibration correspondences and same "
                    "held-out observations for all three models"
                ),
            },

            "calibration_ids": CALIB_IDS,
            "heldout_ids": HELDOUT_IDS,

            "training_sanity": self.training_summary,
            "heldout_vision_metrics": heldout_summary,

            "files": {
                "formal_targets": str(
                    self.output_dir / "E4_formal_9targets.csv"
                ),
                "heldout_pixels": str(pixels_path),
                "heldout_results": str(results_path),
                "heldout_per_frame": str(
                    self.output_dir / "E4_heldout_9points_per_frame.csv"
                ),
                "ihawk1_models": str(
                    self.output_dir / "ihawk1_E4_frozen_models.json"
                ),
                "ihawk2_models": str(
                    self.output_dir / "ihawk2_E4_frozen_models.json"
                ),
            },
        }

        summary_path = self.output_dir / "E4_model_freeze_summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n" + "=" * 92, flush=True)
        print("E4 VISION MODEL FREEZE + 9 HELD-OUT VALIDATION COMPLETE", flush=True)
        print("=" * 92, flush=True)

        print("\nTRAINING SANITY (not formal accuracy):", flush=True)
        for camera in ("ihawk1", "ihawk2"):
            s = self.training_summary[camera]
            print(
                f"{camera}: "
                f"Affine train mean={s['affine']['mean_mm']:.3f} mm | "
                f"H train mean={s['homography']['mean_mm']:.3f} mm | "
                f"PnP train mean={s['pnp_plane_xy']['mean_mm']:.3f} mm | "
                f"PnP reproj mean={s['pnp_reprojection_px']['mean_px']:.3f} px",
                flush=True,
            )

        print("\nFORMAL 9-POINT HELD-OUT VISION ERROR:", flush=True)
        for camera in ("ihawk1", "ihawk2"):
            print(f"\n{camera}", flush=True)
            for method in ("Affine", "Homography", "PnP_IPPE"):
                s = heldout_summary[camera][method]
                print(
                    f"  {method:<11} "
                    f"mean={s['mean_mm']:.3f} mm | "
                    f"RMSE={s['rmse_mm']:.3f} | "
                    f"P95={s['p95_mm']:.3f} | "
                    f"max={s['max_mm']:.3f}",
                    flush=True,
                )

        print(f"\nTargets: {self.output_dir / 'E4_formal_9targets.csv'}")
        print(f"Results: {results_path}")
        print(f"Summary: {summary_path}")
        print("=" * 92, flush=True)

        if rclpy.ok():
            rclpy.shutdown()


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument(
        "--calibration-csv",
        default=(
            "/mnt/c/Users/ASUS/Desktop/paper/E4/"
            "E4_charuco_calibration_v4/20260811_191758/"
            "E4_calibration_12spread.csv"
        ),
    )

    p.add_argument(
        "--geometry-csv",
        default=(
            "/mnt/c/Users/ASUS/Desktop/paper/E4/"
            "E4_charuco_calibration_v4/20260811_191758/"
            "E4_charuco_all48_geometry.csv"
        ),
    )

    p.add_argument("--topic1", default="/ihawk1/color/color_raw")
    p.add_argument("--topic2", default="/ihawk2/color/color_raw")
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--max-seconds", type=float, default=60.0)

    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_model_freeze_v1",
    )

    return p.parse_args()


def main():
    args = parse_args()

    calibration_csv = Path(args.calibration_csv)
    geometry_csv = Path(args.geometry_csv)

    if not calibration_csv.exists():
        raise FileNotFoundError(calibration_csv)
    if not geometry_csv.exists():
        raise FileNotFoundError(geometry_csv)

    calib_rows = read_csv(calibration_csv)
    geometry_rows = read_csv(geometry_csv)
    geometry_by_id = validate_geometry(geometry_rows)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.out_root) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    target_rows = make_target_rows(geometry_by_id)
    write_csv(output_dir / "E4_formal_9targets.csv", target_rows)

    models, training_summary = fit_all_models(
        calib_rows,
        output_dir,
    )

    preflight = {
        "calibration_csv": str(calibration_csv),
        "geometry_csv": str(geometry_csv),
        "opencv_version": cv2.__version__,
        "calibration_ids": CALIB_IDS,
        "heldout_ids": HELDOUT_IDS,
        "heldout_selection_rule": (
            "predefined 3x3 interior spread from remaining non-calibration "
            "ChArUco corners; selected before held-out model errors"
        ),
        "paper_to_robot_used_for_preview_only": PAPER_TO_ROBOT,
        "safe_hover_preview_mm": SAFE_HOVER_MM,
        "training_sanity": training_summary,
    }

    (output_dir / "preflight_model_fit.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 92)
    print("E4 MODEL FIT PREFLIGHT")
    print("=" * 92)
    print(f"Calibration CSV: {calibration_csv}")
    print(f"Geometry CSV:    {geometry_csv}")
    print(f"Output:          {output_dir}")
    print()
    print("METHODS:")
    print("  Affine     = ordinary least squares")
    print("  Homography = direct method=0, NO RANSAC")
    print("  PnP        = SOLVEPNP_IPPE, fixed K, D=0")
    print()

    for camera in ("ihawk1", "ihawk2"):
        s = training_summary[camera]
        print(
            f"{camera}: "
            f"Affine train mean={s['affine']['mean_mm']:.3f} mm | "
            f"H train mean={s['homography']['mean_mm']:.3f} mm | "
            f"PnP train mean={s['pnp_plane_xy']['mean_mm']:.3f} mm | "
            f"PnP reproj mean={s['pnp_reprojection_px']['mean_px']:.3f} px"
        )

    rclpy.init()
    node: Optional[HeldoutCapture] = None

    try:
        node = HeldoutCapture(
            args=args,
            geometry_by_id=geometry_by_id,
            models=models,
            training_summary=training_summary,
            output_dir=output_dir,
            target_rows=target_rows,
        )
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Held-out result not frozen.")
        if node is not None and not node.finalized:
            node.finalize(success=False)
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
