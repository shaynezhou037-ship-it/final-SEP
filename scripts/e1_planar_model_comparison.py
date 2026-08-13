#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E1 — Planar Model Comparison
Affine vs Homography vs PnP + camera extrinsic

Core fairness rules implemented here
------------------------------------
1. SAME camera frame / SAME detected chessboard corners for all models.
2. SAME undistorted pixel coordinates for all models.
3. SAME calibration-point subset for all models.
4. SAME held-out validation points for all models.
5. Ground truth is the known planar board geometry (Z=0), NOT robot feedback.
6. PnP estimates board->camera pose from the same calibration correspondences.
7. Dual-camera fusion is NOT part of this core E1 script.

Typical use
-----------
Collect one fixed-camera planar dataset:
  python3 e1_planar_model_comparison.py collect \
      --camera ihawk1 --cols 8 --rows 6 --square-mm 20 --frames 50

Analyse:
  python3 e1_planar_model_comparison.py analyze \
      --dataset <saved_csv> --n-calib 12

Repeat for ihawk2 after ihawk1 pipeline is validated.

Notes
-----
--cols and --rows are INNER chessboard corners, not square counts.
If your physical board is different, pass its real inner-corner dimensions and
square size on the command line.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np


DEFAULT_ROOT = Path(
    "/mnt/c/Users/ASUS/Desktop/paper/E1/E1_planar_model_comparison"
)


# ---------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def board_xy(cols: int, rows: int, square_mm: float) -> np.ndarray:
    pts = []
    for r in range(rows):
        for c in range(cols):
            pts.append([c * square_mm, r * square_mm])
    return np.asarray(pts, dtype=np.float64)


def board_xyz(cols: int, rows: int, square_mm: float) -> np.ndarray:
    xy = board_xy(cols, rows, square_mm)
    return np.column_stack([xy, np.zeros(len(xy), dtype=np.float64)])


def farthest_subset(xy: np.ndarray, n: int) -> List[int]:
    """Deterministic spatially spread subset."""
    N = len(xy)
    if not (4 <= n < N):
        raise ValueError(f"n_calib must satisfy 4 <= n_calib < {N}")

    # Start with points nearest the four bounding-box corners.
    xmin, ymin = np.min(xy, axis=0)
    xmax, ymax = np.max(xy, axis=0)
    anchors = np.array(
        [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]],
        dtype=np.float64,
    )

    selected: List[int] = []
    for a in anchors:
        idx = int(np.argmin(np.linalg.norm(xy - a, axis=1)))
        if idx not in selected:
            selected.append(idx)

    while len(selected) < n:
        min_d = np.full(N, np.inf)
        for j in selected:
            d = np.linalg.norm(xy - xy[j], axis=1)
            min_d = np.minimum(min_d, d)
        min_d[selected] = -1.0
        selected.append(int(np.argmax(min_d)))

    return selected[:n]


def affine_fit(uv: np.ndarray, xy: np.ndarray) -> np.ndarray:
    A = np.column_stack([uv, np.ones(len(uv))])
    # A @ B = XY, B shape 3x2
    B, *_ = np.linalg.lstsq(A, xy, rcond=None)
    return B


def affine_predict(B: np.ndarray, uv: np.ndarray) -> np.ndarray:
    A = np.column_stack([uv, np.ones(len(uv))])
    return A @ B


def homography_fit(uv: np.ndarray, xy: np.ndarray) -> np.ndarray:
    H, _ = cv2.findHomography(
        uv.astype(np.float32),
        xy.astype(np.float32),
        method=0,
    )
    if H is None:
        raise RuntimeError("cv2.findHomography failed")
    return H.astype(np.float64)


def homography_predict(H: np.ndarray, uv: np.ndarray) -> np.ndarray:
    src = uv.reshape(-1, 1, 2).astype(np.float32)
    dst = cv2.perspectiveTransform(src, H.astype(np.float32))
    return dst[:, 0, :].astype(np.float64)


def pnp_fit(
    xyz: np.ndarray,
    uv_undist: np.ndarray,
    K: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, str]:
    obj = xyz.astype(np.float64)
    img = uv_undist.astype(np.float64)

    # Coordinates are already undistorted, so use zero distortion.
    zeroD = np.zeros((5, 1), dtype=np.float64)

    attempts = []
    if hasattr(cv2, "SOLVEPNP_IPPE"):
        attempts.append(("IPPE", cv2.SOLVEPNP_IPPE))
    attempts.append(("ITERATIVE", cv2.SOLVEPNP_ITERATIVE))

    last = None
    for name, flag in attempts:
        try:
            ok, rvec, tvec = cv2.solvePnP(
                obj, img, K, zeroD, flags=flag
            )
            if ok:
                return rvec.reshape(3, 1), tvec.reshape(3, 1), name
        except cv2.error as exc:
            last = exc

    raise RuntimeError(f"solvePnP failed: {last}")


def pnp_pixel_to_plane(
    uv: np.ndarray,
    K: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
) -> np.ndarray:
    """
    Board->camera:
        Xc = R Xb + t

    For each undistorted pixel, create a camera ray and transform the ray into
    board coordinates, then intersect with board plane Z=0.
    """
    R, _ = cv2.Rodrigues(rvec)
    Rt = R.T
    Cb = (-Rt @ tvec).reshape(3)  # camera center in board frame
    Kinv = np.linalg.inv(K)

    out = []
    for u, v in uv:
        ray_c = Kinv @ np.array([u, v, 1.0], dtype=np.float64)
        ray_b = Rt @ ray_c

        if abs(ray_b[2]) < 1e-12:
            out.append([np.nan, np.nan])
            continue

        lam = -Cb[2] / ray_b[2]
        Xb = Cb + lam * ray_b
        out.append([Xb[0], Xb[1]])

    return np.asarray(out, dtype=np.float64)


def error_metrics(errors: np.ndarray) -> Dict[str, float]:
    errors = np.asarray(errors, dtype=np.float64)
    return {
        "n": int(len(errors)),
        "mean_mm": float(np.mean(errors)),
        "median_mm": float(np.median(errors)),
        "rmse_mm": float(np.sqrt(np.mean(errors ** 2))),
        "std_mm": float(np.std(errors, ddof=1)) if len(errors) > 1 else 0.0,
        "p95_mm": float(np.percentile(errors, 95)),
        "max_mm": float(np.max(errors)),
    }


# ---------------------------------------------------------------------
# ROS collection mode
# ---------------------------------------------------------------------

def image_msg_to_bgr(msg):
    h = int(msg.height)
    w = int(msg.width)
    enc = msg.encoding.lower()
    raw = np.frombuffer(msg.data, dtype=np.uint8)

    if enc in ("bgr8", "rgb8"):
        row = raw.reshape(h, int(msg.step))[:, : w * 3]
        arr = row.reshape(h, w, 3)
        if enc == "rgb8":
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return arr.copy()

    if enc in ("bgra8", "rgba8"):
        row = raw.reshape(h, int(msg.step))[:, : w * 4]
        arr = row.reshape(h, w, 4)
        if enc == "rgba8":
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)

    if enc in ("mono8", "8uc1"):
        row = raw.reshape(h, int(msg.step))[:, :w]
        return cv2.cvtColor(row, cv2.COLOR_GRAY2BGR)

    raise RuntimeError(f"Unsupported image encoding: {msg.encoding}")


def detect_chessboard(
    bgr: np.ndarray,
    cols: int,
    rows: int,
) -> Tuple[bool, np.ndarray]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    pattern = (cols, rows)

    if hasattr(cv2, "findChessboardCornersSB"):
        flags = (
            cv2.CALIB_CB_NORMALIZE_IMAGE
            | cv2.CALIB_CB_EXHAUSTIVE
            | cv2.CALIB_CB_ACCURACY
        )
        ok, corners = cv2.findChessboardCornersSB(gray, pattern, flags)
        if ok:
            return True, corners.reshape(-1, 2).astype(np.float64)

    flags = (
        cv2.CALIB_CB_ADAPTIVE_THRESH
        | cv2.CALIB_CB_NORMALIZE_IMAGE
    )
    ok, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if not ok:
        return False, np.empty((0, 2), dtype=np.float64)

    crit = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        40,
        0.001,
    )
    corners = cv2.cornerSubPix(
        gray,
        corners,
        (7, 7),
        (-1, -1),
        crit,
    )
    return True, corners.reshape(-1, 2).astype(np.float64)


def undistort_pixel_points(
    uv: np.ndarray,
    K: np.ndarray,
    D: np.ndarray,
) -> np.ndarray:
    pts = uv.reshape(-1, 1, 2).astype(np.float64)
    und = cv2.undistortPoints(pts, K, D, P=K)
    return und[:, 0, :].astype(np.float64)


def collect_mode(args) -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import CameraInfo, Image
    except Exception as exc:
        raise RuntimeError(
            "ROS2 Python packages unavailable. Run inside sourced ROS2 shell."
        ) from exc

    camera = args.camera
    image_topic = f"/{camera}/color/color_raw"
    info_topic = f"/{camera}/color/camera_info"

    class Collector(Node):
        def __init__(self):
            super().__init__(f"e1_{camera}_collector")
            self.frame = None
            self.info = None
            self.create_subscription(
                Image,
                image_topic,
                self.image_cb,
                5,
            )
            self.create_subscription(
                CameraInfo,
                info_topic,
                self.info_cb,
                5,
            )

        def image_cb(self, msg):
            self.frame = image_msg_to_bgr(msg)

        def info_cb(self, msg):
            self.info = msg

    root = Path(args.output_root)
    raw_dir = root / "raw"
    ensure_dir(raw_dir)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = raw_dir / f"E1_{camera}_planar_raw_{run_id}.csv"
    meta_path = raw_dir / f"E1_{camera}_planar_raw_{run_id}_meta.json"

    rclpy.init()
    node = Collector()

    try:
        print("============================================================")
        print("E1 PLANAR MODEL COMPARISON — DATA COLLECTION")
        print("============================================================")
        print(f"camera        : {camera}")
        print(f"image topic   : {image_topic}")
        print(f"pattern       : {args.cols} x {args.rows} INNER corners")
        print(f"square size   : {args.square_mm:.3f} mm")
        print(f"target frames : {args.frames}")
        print()
        print("FAIRNESS RULE: keep camera + board completely fixed.")
        print("No robot motion is needed for E1 collection.")
        print()

        deadline = time.time() + 12.0
        while time.time() < deadline and (node.frame is None or node.info is None):
            rclpy.spin_once(node, timeout_sec=0.1)

        if node.frame is None or node.info is None:
            raise RuntimeError("Timed out waiting for image/camera_info")

        info = node.info
        K = np.array(info.k, dtype=np.float64).reshape(3, 3)
        D = np.array(info.d, dtype=np.float64).reshape(-1, 1)

        fields = [
            "frame_index",
            "timestamp",
            "corner_index",
            "board_col",
            "board_row",
            "board_x_mm",
            "board_y_mm",
            "u_raw_px",
            "v_raw_px",
            "u_undist_px",
            "v_undist_px",
        ]

        accepted = 0
        attempted = 0

        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()

            while accepted < args.frames:
                rclpy.spin_once(node, timeout_sec=0.1)
                if node.frame is None:
                    continue

                attempted += 1
                frame = node.frame.copy()
                ok, uv_raw = detect_chessboard(
                    frame,
                    args.cols,
                    args.rows,
                )

                if not ok or len(uv_raw) != args.cols * args.rows:
                    if attempted % 10 == 0:
                        print(
                            f"[WAIT] accepted {accepted}/{args.frames}; "
                            "chessboard not fully detected"
                        )
                    continue

                uv_und = undistort_pixel_points(uv_raw, K, D)
                accepted += 1
                ts = datetime.now().isoformat(timespec="milliseconds")

                k = 0
                for rr in range(args.rows):
                    for cc in range(args.cols):
                        writer.writerow({
                            "frame_index": accepted,
                            "timestamp": ts,
                            "corner_index": k,
                            "board_col": cc,
                            "board_row": rr,
                            "board_x_mm": cc * args.square_mm,
                            "board_y_mm": rr * args.square_mm,
                            "u_raw_px": uv_raw[k, 0],
                            "v_raw_px": uv_raw[k, 1],
                            "u_undist_px": uv_und[k, 0],
                            "v_undist_px": uv_und[k, 1],
                        })
                        k += 1

                f.flush()
                print(f"[ACCEPT] frame {accepted}/{args.frames}")

        meta = {
            "experiment": "E1 planar model comparison",
            "camera": camera,
            "image_topic": image_topic,
            "camera_info_topic": info_topic,
            "cols_inner_corners": args.cols,
            "rows_inner_corners": args.rows,
            "square_mm": args.square_mm,
            "accepted_frames": accepted,
            "K": K.tolist(),
            "D": D.reshape(-1).tolist(),
            "distortion_model": info.distortion_model,
            "image_width": int(info.width),
            "image_height": int(info.height),
            "primary_input_for_all_models": "undistorted pixel coordinates",
            "ground_truth": "known planar board XY, Z=0",
        }

        meta_path.write_text(
            json.dumps(meta, indent=2),
            encoding="utf-8",
        )

        print()
        print("[PASS] E1 raw dataset saved")
        print(csv_path)
        print(meta_path)

    finally:
        node.destroy_node()
        rclpy.shutdown()


# ---------------------------------------------------------------------
# Analysis mode
# ---------------------------------------------------------------------

def analyze_mode(args) -> None:
    dataset = Path(args.dataset)
    if not dataset.exists():
        raise FileNotFoundError(dataset)

    meta_path = dataset.with_name(dataset.stem + "_meta.json")
    if not meta_path.exists():
        raise FileNotFoundError(
            f"Matching metadata file not found: {meta_path}"
        )

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    cols = int(meta["cols_inner_corners"])
    rows_n = int(meta["rows_inner_corners"])
    square_mm = float(meta["square_mm"])
    K = np.asarray(meta["K"], dtype=np.float64)

    by_frame: Dict[int, Dict[int, Tuple[float, float]]] = {}

    with dataset.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        fi = int(r["frame_index"])
        ci = int(r["corner_index"])
        uv = (float(r["u_undist_px"]), float(r["v_undist_px"]))
        by_frame.setdefault(fi, {})[ci] = uv

    expected = cols * rows_n
    good_frames = sorted(
        fi for fi, d in by_frame.items()
        if len(d) == expected
    )
    if not good_frames:
        raise RuntimeError("No complete frames in dataset")

    xy_gt = board_xy(cols, rows_n, square_mm)
    xyz_gt = board_xyz(cols, rows_n, square_mm)

    calib_idx = farthest_subset(xy_gt, args.n_calib)
    calib_set = set(calib_idx)
    valid_idx = [i for i in range(expected) if i not in calib_set]

    # Median point positions across all accepted frames -> frozen calibration.
    uv_stack = []
    for fi in good_frames:
        uv_stack.append(
            np.asarray(
                [by_frame[fi][i] for i in range(expected)],
                dtype=np.float64,
            )
        )
    uv_stack = np.stack(uv_stack, axis=0)
    uv_median = np.median(uv_stack, axis=0)

    uv_cal = uv_median[calib_idx]
    xy_cal = xy_gt[calib_idx]
    xyz_cal = xyz_gt[calib_idx]

    # Fit all three from EXACTLY same calibration points.
    A = affine_fit(uv_cal, xy_cal)
    H = homography_fit(uv_cal, xy_cal)
    rvec, tvec, pnp_method = pnp_fit(xyz_cal, uv_cal, K)

    # Primary held-out point accuracy on median pixel positions.
    model_preds_median = {
        "Affine": affine_predict(A, uv_median[valid_idx]),
        "Homography": homography_predict(H, uv_median[valid_idx]),
        "PnP": pnp_pixel_to_plane(
            uv_median[valid_idx], K, rvec, tvec
        ),
    }

    primary = {}
    for name, pred in model_preds_median.items():
        e_xy = pred - xy_gt[valid_idx]
        e = np.linalg.norm(e_xy, axis=1)
        primary[name] = error_metrics(e)

    # Frame-wise validation using FROZEN models.
    per_observation_rows = []
    all_errors = {"Affine": [], "Homography": [], "PnP": []}

    for fi in good_frames:
        uv = np.asarray(
            [by_frame[fi][i] for i in range(expected)],
            dtype=np.float64,
        )
        uv_v = uv[valid_idx]
        gt_v = xy_gt[valid_idx]

        preds = {
            "Affine": affine_predict(A, uv_v),
            "Homography": homography_predict(H, uv_v),
            "PnP": pnp_pixel_to_plane(uv_v, K, rvec, tvec),
        }

        for name, pred in preds.items():
            for local_j, corner_idx in enumerate(valid_idx):
                ex = float(pred[local_j, 0] - gt_v[local_j, 0])
                ey = float(pred[local_j, 1] - gt_v[local_j, 1])
                ee = math.hypot(ex, ey)

                all_errors[name].append(ee)

                per_observation_rows.append({
                    "frame_index": fi,
                    "model": name,
                    "corner_index": corner_idx,
                    "board_x_mm": gt_v[local_j, 0],
                    "board_y_mm": gt_v[local_j, 1],
                    "pred_x_mm": pred[local_j, 0],
                    "pred_y_mm": pred[local_j, 1],
                    "error_x_mm": ex,
                    "error_y_mm": ey,
                    "error_2d_mm": ee,
                })

    framewise = {
        name: error_metrics(np.asarray(vals, dtype=np.float64))
        for name, vals in all_errors.items()
    }

    root = Path(args.output_root)
    results_dir = root / "results"
    ensure_dir(results_dir)

    tag = dataset.stem.replace("_raw_", "_")
    summary_path = results_dir / f"{tag}_comparison_summary.json"
    obs_path = results_dir / f"{tag}_validation_observations.csv"
    models_path = results_dir / f"{tag}_models.json"

    fields = list(per_observation_rows[0].keys())
    with obs_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(per_observation_rows)

    summary = {
        "experiment": "E1 planar model comparison",
        "camera": meta["camera"],
        "fairness": {
            "same_undistorted_pixels": True,
            "same_calibration_indices": calib_idx,
            "same_validation_indices": valid_idx,
            "same_ground_truth": "known board XY, Z=0",
            "n_calibration_points": len(calib_idx),
            "n_validation_points": len(valid_idx),
            "accepted_frames": len(good_frames),
        },
        "primary_median_point_accuracy_mm": primary,
        "framewise_validation_error_mm": framewise,
        "pnp_solver": pnp_method,
        "interpretation": (
            "Primary comparison uses held-out board points. Models are fitted "
            "once from median undistorted calibration-point pixels across the "
            "accepted frames, then evaluated on the same held-out locations. "
            "Frame-wise statistics use the frozen models and quantify combined "
            "model + residual image-localization variation."
        ),
    }

    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    models = {
        "Affine_B_3x2": A.tolist(),
        "Homography_H_3x3": H.tolist(),
        "PnP_rvec": rvec.reshape(-1).tolist(),
        "PnP_tvec_mm": tvec.reshape(-1).tolist(),
        "PnP_solver": pnp_method,
        "K": K.tolist(),
        "calibration_indices": calib_idx,
    }
    models_path.write_text(
        json.dumps(models, indent=2),
        encoding="utf-8",
    )

    print("============================================================")
    print("E1 PLANAR MODEL COMPARISON — RESULTS")
    print("============================================================")
    print(f"camera             : {meta['camera']}")
    print(f"accepted frames    : {len(good_frames)}")
    print(f"calibration points : {len(calib_idx)}")
    print(f"validation points  : {len(valid_idx)}")
    print(f"PnP solver         : {pnp_method}")
    print()
    print("PRIMARY: held-out validation accuracy on median pixels")
    print("------------------------------------------------------")
    for name in ("Affine", "Homography", "PnP"):
        m = primary[name]
        print(
            f"{name:10s} "
            f"mean={m['mean_mm']:.3f} mm | "
            f"RMSE={m['rmse_mm']:.3f} mm | "
            f"P95={m['p95_mm']:.3f} mm | "
            f"max={m['max_mm']:.3f} mm"
        )

    print()
    print("FRAME-WISE frozen-model validation")
    print("----------------------------------")
    for name in ("Affine", "Homography", "PnP"):
        m = framewise[name]
        print(
            f"{name:10s} "
            f"mean={m['mean_mm']:.3f} mm | "
            f"RMSE={m['rmse_mm']:.3f} mm | "
            f"P95={m['p95_mm']:.3f} mm | "
            f"max={m['max_mm']:.3f} mm"
        )

    print()
    print("Saved:")
    print(summary_path)
    print(obs_path)
    print(models_path)


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        description="E1 fair planar comparison: Affine vs Homography vs PnP"
    )
    sub = p.add_subparsers(dest="mode", required=True)

    c = sub.add_parser("collect")
    c.add_argument(
        "--camera",
        choices=["ihawk1", "ihawk2"],
        required=True,
    )
    c.add_argument(
        "--cols",
        type=int,
        required=True,
        help="Number of INNER chessboard corners horizontally.",
    )
    c.add_argument(
        "--rows",
        type=int,
        required=True,
        help="Number of INNER chessboard corners vertically.",
    )
    c.add_argument(
        "--square-mm",
        type=float,
        required=True,
    )
    c.add_argument(
        "--frames",
        type=int,
        default=50,
    )
    c.add_argument(
        "--output-root",
        default=str(DEFAULT_ROOT),
    )

    a = sub.add_parser("analyze")
    a.add_argument(
        "--dataset",
        required=True,
    )
    a.add_argument(
        "--n-calib",
        type=int,
        default=12,
    )
    a.add_argument(
        "--output-root",
        default=str(DEFAULT_ROOT),
    )

    return p


def main():
    args = build_parser().parse_args()
    if args.mode == "collect":
        collect_mode(args)
    else:
        analyze_mode(args)


if __name__ == "__main__":
    main()
