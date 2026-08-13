#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compute final dual-camera planar homographies after intrinsic calibration.

Workflow per camera:
1. Read latest Color_*.bmp from homography_final_input.
2. Load final K and D from intrinsic_output/camera_intrinsics.json.
3. Undistort the image using P=K, preserving 640x400 coordinates.
4. Detect the 8x6 inner chessboard corners.
5. Compute:
   - raw-image homography baseline,
   - undistorted-image homography for formal use,
   - all-point fitting and distributed hold-out errors.
6. Save JSON and annotated images.

Runtime mapping for a raw pixel (u, v):
    undistorted_pixel = cv2.undistortPoints(
        np.array([[[u, v]]], dtype=np.float32),
        K, D, P=K
    )
    board_xy = perspectiveTransform(undistorted_pixel, H_undistorted_to_board)
"""

import json
import math
from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(r"C:\BerxelWork\calibration\eyetohand_dual_0802")
CHESSBOARD_SIZE = (8, 6)  # inner corners: columns, rows
SQUARE_SIZE_MM = 25.0

CAMERAS = {
    "camera_overhead_B242": {
        "role": "overhead",
        "serial_number": "HK100QB5311M2B242",
        "capture_dir": BASE_DIR / "camera_overhead_B242" / "homography_final_input",
        "intrinsics": BASE_DIR / "camera_overhead_B242" / "intrinsic_output" / "camera_intrinsics.json",
        "output_dir": BASE_DIR / "camera_overhead_B242" / "final_homography_output",
    },
    "camera_side_B479": {
        "role": "side",
        "serial_number": "HK100QB6513M2B479",
        "capture_dir": BASE_DIR / "camera_side_B479" / "homography_final_input",
        "intrinsics": BASE_DIR / "camera_side_B479" / "intrinsic_output" / "camera_intrinsics.json",
        "output_dir": BASE_DIR / "camera_side_B479" / "final_homography_output",
    },
}


def latest_color(folder):
    files = sorted(
        [
            p for p in folder.glob("Color_*.bmp")
            if p.is_file()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No Color_*.bmp found in {folder}")
    return files[0]


def board_points():
    cols, rows = CHESSBOARD_SIZE
    return np.asarray(
        [
            [c * SQUARE_SIZE_MM, r * SQUARE_SIZE_MM]
            for r in range(rows)
            for c in range(cols)
        ],
        dtype=np.float32,
    )


def detect_corners(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if hasattr(cv2, "findChessboardCornersSB"):
        flags = (
            cv2.CALIB_CB_NORMALIZE_IMAGE
            | cv2.CALIB_CB_EXHAUSTIVE
            | cv2.CALIB_CB_ACCURACY
        )
        found, corners = cv2.findChessboardCornersSB(
            gray,
            CHESSBOARD_SIZE,
            flags=flags,
        )
        if found:
            return corners.reshape(-1, 2).astype(np.float32), "findChessboardCornersSB"

    flags = (
        cv2.CALIB_CB_ADAPTIVE_THRESH
        | cv2.CALIB_CB_NORMALIZE_IMAGE
    )
    found, corners = cv2.findChessboardCorners(
        gray,
        CHESSBOARD_SIZE,
        flags,
    )
    if not found:
        return None, "none"

    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
        50,
        0.0005,
    )
    corners = cv2.cornerSubPix(
        gray,
        corners,
        (5, 5),
        (-1, -1),
        criteria,
    )
    return corners.reshape(-1, 2).astype(np.float32), "findChessboardCorners"


def transform_points(H, points):
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def error_summary(predicted, expected):
    e = np.linalg.norm(
        np.asarray(predicted) - np.asarray(expected),
        axis=1,
    )
    return {
        "count": int(e.size),
        "mean": float(e.mean()),
        "rmse": float(math.sqrt(np.mean(e ** 2))),
        "median": float(np.median(e)),
        "max": float(e.max()),
    }


def split_indices():
    cols, rows = CHESSBOARD_SIZE
    train, holdout = [], []
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if r % 2 == 1 and c % 2 == 1:
                holdout.append(idx)
            else:
                train.append(idx)
    return train, holdout


def fit_and_evaluate(image_points, board_pts):
    H_all, _ = cv2.findHomography(
        image_points,
        board_pts,
        method=0,
    )
    if H_all is None:
        raise RuntimeError("All-point homography failed.")

    all_pred = transform_points(H_all, image_points)
    all_error = error_summary(all_pred, board_pts)

    train_idx, holdout_idx = split_indices()

    H_train, _ = cv2.findHomography(
        image_points[train_idx],
        board_pts[train_idx],
        method=0,
    )
    if H_train is None:
        raise RuntimeError("Hold-out homography failed.")

    holdout_pred = transform_points(
        H_train,
        image_points[holdout_idx],
    )
    holdout_error = error_summary(
        holdout_pred,
        board_pts[holdout_idx],
    )

    return {
        "H_all": H_all,
        "H_train": H_train,
        "all_point_error_mm": all_error,
        "holdout_error_mm": holdout_error,
        "train_count": len(train_idx),
        "holdout_count": len(holdout_idx),
    }


def annotate(image, corners, label, output_path):
    vis = image.copy()

    cv2.drawChessboardCorners(
        vis,
        CHESSBOARD_SIZE,
        corners.reshape(-1, 1, 2),
        True,
    )

    board_pts = board_points()
    for idx in [0, 7, 40, 47]:
        u, v = corners[idx]
        bx, by = board_pts[idx]
        p = (round(float(u)), round(float(v)))

        cv2.circle(vis, p, 6, (0, 0, 255), -1)
        cv2.putText(
            vis,
            f"{idx}: B({bx:.0f},{by:.0f})",
            (p[0] + 8, p[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        vis,
        label,
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 0, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.imwrite(str(output_path), vis)


def process_camera(name, info):
    capture_dir = Path(info["capture_dir"])
    output_dir = Path(info["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    image_path = latest_color(capture_dir)

    intrinsics = json.loads(
        Path(info["intrinsics"]).read_text(encoding="utf-8")
    )

    K = np.asarray(
        intrinsics["camera_matrix"],
        dtype=np.float64,
    )
    D = np.asarray(
        intrinsics["distortion_coefficients"],
        dtype=np.float64,
    ).reshape(-1, 1)

    raw = cv2.imread(str(image_path))
    if raw is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    height, width = raw.shape[:2]
    expected_size = intrinsics["image_size_px"]

    if (
        width != int(expected_size["width"])
        or height != int(expected_size["height"])
    ):
        raise RuntimeError(
            f"Image size {width}x{height} does not match "
            f"intrinsics {expected_size['width']}x{expected_size['height']}."
        )

    undistorted = cv2.undistort(
        raw,
        K,
        D,
        None,
        K,
    )

    raw_corners, raw_detector = detect_corners(raw)
    und_corners, und_detector = detect_corners(undistorted)

    if raw_corners is None:
        raise RuntimeError("Chessboard was not detected in raw image.")
    if und_corners is None:
        raise RuntimeError("Chessboard was not detected after undistortion.")

    board_pts = board_points()

    raw_result = fit_and_evaluate(
        raw_corners,
        board_pts,
    )
    und_result = fit_and_evaluate(
        und_corners,
        board_pts,
    )

    annotate(
        raw,
        raw_corners,
        "RAW IMAGE",
        output_dir / "chessboard_raw.png",
    )
    annotate(
        undistorted,
        und_corners,
        "UNDISTORTED IMAGE",
        output_dir / "chessboard_undistorted.png",
    )

    cv2.imwrite(
        str(output_dir / "undistorted_reference.png"),
        undistorted,
    )

    print()
    print("=" * 78)
    print(f"Camera: {name}")
    print(f"Role:   {info['role']}")
    print(f"SN:     {info['serial_number']}")
    print(f"Image:  {image_path}")
    print("=" * 78)

    print("[RAW HOLD-OUT]")
    print(
        f"mean={raw_result['holdout_error_mm']['mean']:.3f} mm, "
        f"rmse={raw_result['holdout_error_mm']['rmse']:.3f} mm, "
        f"max={raw_result['holdout_error_mm']['max']:.3f} mm"
    )

    print("[UNDISTORTED HOLD-OUT — FORMAL]")
    print(
        f"mean={und_result['holdout_error_mm']['mean']:.3f} mm, "
        f"rmse={und_result['holdout_error_mm']['rmse']:.3f} mm, "
        f"max={und_result['holdout_error_mm']['max']:.3f} mm"
    )

    result = {
        "camera_name": name,
        "camera_role": info["role"],
        "serial_number": info["serial_number"],
        "source_image": str(image_path),
        "image_size_px": {
            "width": width,
            "height": height,
        },
        "chessboard_inner_corners": {
            "columns": CHESSBOARD_SIZE[0],
            "rows": CHESSBOARD_SIZE[1],
        },
        "measured_square_size_mm": SQUARE_SIZE_MM,
        "intrinsics_source": str(info["intrinsics"]),
        "camera_matrix_K": K.tolist(),
        "distortion_coefficients_D": D.reshape(-1).tolist(),
        "raw_baseline": {
            "detector": raw_detector,
            "H_raw_image_to_board": raw_result["H_all"].tolist(),
            "all_point_error_mm": raw_result["all_point_error_mm"],
            "holdout_error_mm": raw_result["holdout_error_mm"],
        },
        "formal_undistorted_mapping": {
            "detector": und_detector,
            "undistortion_projection_matrix": "K",
            "H_undistorted_pixel_to_board": und_result["H_all"].tolist(),
            "H_train_only_for_validation": und_result["H_train"].tolist(),
            "all_point_error_mm": und_result["all_point_error_mm"],
            "holdout_error_mm": und_result["holdout_error_mm"],
        },
        "runtime_pixel_mapping": {
            "step_1": "Undistort raw pixel with cv2.undistortPoints(raw_pixel, K, D, P=K).",
            "step_2": "Apply H_undistorted_pixel_to_board to the undistorted pixel.",
        },
        "board_coordinate_definition": {
            "corner_0": [0.0, 0.0],
            "corner_7": [175.0, 0.0],
            "corner_40": [0.0, 125.0],
            "corner_47": [175.0, 125.0],
            "unit": "mm",
        },
    }

    json_path = output_dir / "camera_final_homography.json"
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("[SAVED]")
    print(json_path)
    print(output_dir / "chessboard_undistorted.png")

    return result


def main():
    print("=" * 78)
    print("Final Dual-Camera Undistorted Homography")
    print(
        f"Pattern: {CHESSBOARD_SIZE[0]}x{CHESSBOARD_SIZE[1]} inner corners, "
        f"square={SQUARE_SIZE_MM:.1f} mm"
    )
    print("=" * 78)

    results = {}
    all_ok = True

    for name, info in CAMERAS.items():
        try:
            results[name] = process_camera(name, info)
        except Exception as exc:
            all_ok = False
            results[name] = {
                "error": f"{type(exc).__name__}: {exc}"
            }
            print(
                f"\n[ERROR] {name}: "
                f"{type(exc).__name__}: {exc}"
            )

    summary_dir = BASE_DIR / "calibration_summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    summary_path = summary_dir / "dual_final_homography_summary.json"
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 78)
    print(
        "[ALL DONE] Both final homographies completed."
        if all_ok
        else "[PARTIAL/FAILED] At least one camera failed."
    )
    print("[SUMMARY]")
    print(summary_path)
    print("=" * 78)


if __name__ == "__main__":
    main()
