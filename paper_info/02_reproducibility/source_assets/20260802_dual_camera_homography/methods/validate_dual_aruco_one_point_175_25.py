#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
One-point dual-camera validation at board coordinate (175, 25) mm.

Marker convention:
- ArUco dictionary: DICT_4X4_50
- Target marker ID: 0
- The physical marker size is NOT required because this script uses only
  the detected image center, not pose estimation.

Per camera:
1. Read the latest Color_*.bmp from validation_points.
2. Detect marker ID 0 and compute its center in raw pixels.
3. Undistort that center with K, D and P=K.
4. Apply H_undistorted_pixel_to_board.
5. Compare predicted board coordinate against (175, 25) mm.

This is a one-point sanity check, not a full precision characterization.
"""

import json
import math
from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(r"C:\BerxelWork\calibration\eyetohand_dual_0802")

ARUCO_DICT_NAME = "DICT_4X4_50"
TARGET_ID = 0
TARGET_BOARD_MM = np.array([175.0, 25.0], dtype=np.float64)

CAMERAS = {
    "camera_overhead_B242": {
        "role": "overhead",
        "serial_number": "HK100QB5311M2B242",
        "validation_dir": (
            BASE_DIR
            / "camera_overhead_B242"
            / "validation_points"
        ),
        "calibration_json": (
            BASE_DIR
            / "camera_overhead_B242"
            / "final_homography_output"
            / "camera_final_homography.json"
        ),
        "output_dir": (
            BASE_DIR
            / "camera_overhead_B242"
            / "validation_output"
        ),
    },
    "camera_side_B479": {
        "role": "side",
        "serial_number": "HK100QB6513M2B479",
        "validation_dir": (
            BASE_DIR
            / "camera_side_B479"
            / "validation_points"
        ),
        "calibration_json": (
            BASE_DIR
            / "camera_side_B479"
            / "final_homography_output"
            / "camera_final_homography.json"
        ),
        "output_dir": (
            BASE_DIR
            / "camera_side_B479"
            / "validation_output"
        ),
    },
}


def latest_color(folder: Path) -> Path:
    files = sorted(
        [
            path
            for path in folder.glob("Color_*.bmp")
            if path.is_file()
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            f"No Color_*.bmp found in {folder}"
        )

    return files[0]


def get_aruco_dictionary():
    if not hasattr(cv2, "aruco"):
        raise RuntimeError(
            "cv2.aruco is unavailable. Install/use OpenCV contrib."
        )

    dictionary_id = getattr(cv2.aruco, ARUCO_DICT_NAME)
    return cv2.aruco.getPredefinedDictionary(dictionary_id)


def detect_aruco_center(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dictionary = get_aruco_dictionary()

    if hasattr(cv2.aruco, "ArucoDetector"):
        parameters = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(
            dictionary,
            parameters,
        )
        corners, ids, rejected = detector.detectMarkers(gray)
    else:
        parameters = cv2.aruco.DetectorParameters_create()
        corners, ids, rejected = cv2.aruco.detectMarkers(
            gray,
            dictionary,
            parameters=parameters,
        )

    if ids is None or len(ids) == 0:
        raise RuntimeError(
            f"No ArUco marker detected; expected ID {TARGET_ID}."
        )

    candidates = []

    for marker_corners, marker_id in zip(
        corners,
        ids.reshape(-1),
    ):
        if int(marker_id) != TARGET_ID:
            continue

        points = marker_corners.reshape(4, 2).astype(
            np.float64
        )

        center = points.mean(axis=0)
        area = abs(cv2.contourArea(points.astype(np.float32)))

        candidates.append({
            "center": center,
            "points": points,
            "area": float(area),
        })

    if not candidates:
        detected_ids = [int(value) for value in ids.reshape(-1)]
        raise RuntimeError(
            f"Marker ID {TARGET_ID} was not detected. "
            f"Detected IDs: {detected_ids}"
        )

    best = max(
        candidates,
        key=lambda item: item["area"],
    )

    return best, ids.reshape(-1).tolist(), rejected


def undistort_pixel(raw_pixel, K, D):
    point = np.asarray(
        raw_pixel,
        dtype=np.float32,
    ).reshape(1, 1, 2)

    undistorted = cv2.undistortPoints(
        point,
        K,
        D,
        P=K,
    )

    return undistorted.reshape(2).astype(np.float64)


def pixel_to_board(undistorted_pixel, H):
    point = np.asarray(
        undistorted_pixel,
        dtype=np.float64,
    ).reshape(1, 1, 2)

    board = cv2.perspectiveTransform(
        point,
        H,
    )

    return board.reshape(2)


def annotate(
    image,
    marker_points,
    raw_center,
    undistorted_center,
    predicted_board,
    error_mm,
    output_path,
):
    vis = image.copy()

    polygon = marker_points.astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(
        vis,
        [polygon],
        True,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    center_tuple = (
        round(float(raw_center[0])),
        round(float(raw_center[1])),
    )

    cv2.circle(
        vis,
        center_tuple,
        6,
        (0, 0, 255),
        -1,
    )

    lines = [
        f"ArUco ID {TARGET_ID}",
        (
            f"raw center=({raw_center[0]:.2f}, "
            f"{raw_center[1]:.2f}) px"
        ),
        (
            f"und center=({undistorted_center[0]:.2f}, "
            f"{undistorted_center[1]:.2f}) px"
        ),
        (
            f"board=({predicted_board[0]:.2f}, "
            f"{predicted_board[1]:.2f}) mm"
        ),
        (
            f"target=({TARGET_BOARD_MM[0]:.1f}, "
            f"{TARGET_BOARD_MM[1]:.1f}) mm"
        ),
        f"error={error_mm:.2f} mm",
    ]

    y = 25
    for line in lines:
        cv2.putText(
            vis,
            line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        y += 23

    cv2.imwrite(str(output_path), vis)


def process_camera(camera_name, info):
    validation_dir = Path(info["validation_dir"])
    calibration_path = Path(info["calibration_json"])
    output_dir = Path(info["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    image_path = latest_color(validation_dir)

    calibration = json.loads(
        calibration_path.read_text(encoding="utf-8")
    )

    K = np.asarray(
        calibration["camera_matrix_K"],
        dtype=np.float64,
    )

    D = np.asarray(
        calibration["distortion_coefficients_D"],
        dtype=np.float64,
    ).reshape(-1, 1)

    H = np.asarray(
        calibration[
            "formal_undistorted_mapping"
        ]["H_undistorted_pixel_to_board"],
        dtype=np.float64,
    )

    image = cv2.imread(str(image_path))

    if image is None:
        raise RuntimeError(
            f"OpenCV could not read {image_path}"
        )

    detection, detected_ids, rejected = detect_aruco_center(
        image
    )

    raw_center = detection["center"]
    marker_points = detection["points"]

    undistorted_center = undistort_pixel(
        raw_center,
        K,
        D,
    )

    predicted_board = pixel_to_board(
        undistorted_center,
        H,
    )

    error_vector = (
        predicted_board - TARGET_BOARD_MM
    )

    error_mm = float(
        np.linalg.norm(error_vector)
    )

    annotated_path = (
        output_dir
        / "aruco_one_point_validation.png"
    )

    annotate(
        image,
        marker_points,
        raw_center,
        undistorted_center,
        predicted_board,
        error_mm,
        annotated_path,
    )

    result = {
        "camera_name": camera_name,
        "camera_role": info["role"],
        "serial_number": info["serial_number"],
        "image_path": str(image_path),
        "aruco_dictionary": ARUCO_DICT_NAME,
        "target_marker_id": TARGET_ID,
        "detected_ids": [
            int(value) for value in detected_ids
        ],
        "marker_area_px2": detection["area"],
        "raw_marker_center_px": raw_center.tolist(),
        "undistorted_marker_center_px": (
            undistorted_center.tolist()
        ),
        "target_board_mm": TARGET_BOARD_MM.tolist(),
        "predicted_board_mm": predicted_board.tolist(),
        "error_vector_mm": error_vector.tolist(),
        "euclidean_error_mm": error_mm,
        "calibration_json": str(calibration_path),
        "annotated_image": str(annotated_path),
        "note": (
            "One-point manually placed sanity check. "
            "Placement uncertainty is included in this error."
        ),
    }

    result_path = (
        output_dir
        / "aruco_one_point_validation.json"
    )

    result_path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 78)
    print(f"Camera: {camera_name}")
    print(f"Role:   {info['role']}")
    print(f"SN:     {info['serial_number']}")
    print(f"Image:  {image_path}")
    print("=" * 78)
    print(
        f"Raw center:         "
        f"({raw_center[0]:.3f}, {raw_center[1]:.3f}) px"
    )
    print(
        f"Undistorted center: "
        f"({undistorted_center[0]:.3f}, "
        f"{undistorted_center[1]:.3f}) px"
    )
    print(
        f"Predicted board:    "
        f"({predicted_board[0]:.3f}, "
        f"{predicted_board[1]:.3f}) mm"
    )
    print(
        f"Target board:       "
        f"({TARGET_BOARD_MM[0]:.3f}, "
        f"{TARGET_BOARD_MM[1]:.3f}) mm"
    )
    print(
        f"Error vector:       "
        f"({error_vector[0]:+.3f}, "
        f"{error_vector[1]:+.3f}) mm"
    )
    print(f"Euclidean error:    {error_mm:.3f} mm")
    print("[SAVED]")
    print(result_path)
    print(annotated_path)

    return result


def main():
    print("=" * 78)
    print("Dual-Camera ArUco One-Point Board Validation")
    print(
        f"Dictionary={ARUCO_DICT_NAME}, "
        f"ID={TARGET_ID}, "
        f"target=({TARGET_BOARD_MM[0]:.1f}, "
        f"{TARGET_BOARD_MM[1]:.1f}) mm"
    )
    print("=" * 78)

    results = {}
    all_ok = True

    for camera_name, info in CAMERAS.items():
        try:
            results[camera_name] = process_camera(
                camera_name,
                info,
            )
        except Exception as exc:
            all_ok = False
            results[camera_name] = {
                "error": f"{type(exc).__name__}: {exc}"
            }
            print(
                f"\n[ERROR] {camera_name}: "
                f"{type(exc).__name__}: {exc}"
            )

    if all(
        "predicted_board_mm" in result
        for result in results.values()
    ):
        overhead = np.asarray(
            results[
                "camera_overhead_B242"
            ]["predicted_board_mm"],
            dtype=np.float64,
        )

        side = np.asarray(
            results[
                "camera_side_B479"
            ]["predicted_board_mm"],
            dtype=np.float64,
        )

        disagreement_vector = side - overhead
        disagreement_mm = float(
            np.linalg.norm(disagreement_vector)
        )

        print()
        print("=" * 78)
        print("[DUAL-CAMERA AGREEMENT]")
        print(
            f"side - overhead: "
            f"({disagreement_vector[0]:+.3f}, "
            f"{disagreement_vector[1]:+.3f}) mm"
        )
        print(
            f"Euclidean disagreement: "
            f"{disagreement_mm:.3f} mm"
        )

        results["dual_camera_agreement"] = {
            "side_minus_overhead_mm": (
                disagreement_vector.tolist()
            ),
            "euclidean_disagreement_mm": (
                disagreement_mm
            ),
        }

    summary_dir = BASE_DIR / "calibration_summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    summary_path = (
        summary_dir
        / "dual_aruco_one_point_validation_175_25.json"
    )

    summary_path.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 78)
    print(
        "[ALL DONE] One-point validation completed."
        if all_ok
        else "[PARTIAL/FAILED] At least one camera failed."
    )
    print("[SUMMARY]")
    print(summary_path)
    print("=" * 78)


if __name__ == "__main__":
    main()
