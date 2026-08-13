#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Align the side-camera homography to the common board coordinate frame.

Observed side-camera local coordinates are rotated 180 degrees relative to the
overhead/common board frame. Board extent:
    X: 0 ... 175 mm
    Y: 0 ... 125 mm

Coordinate conversion:
    x_common = 175 - x_side
    y_common = 125 - y_side

For a homography H_side mapping undistorted pixels to the side-local board
frame, the aligned homography is:
    H_common = T_180 @ H_side

where:
    T_180 = [[-1, 0, 175],
             [ 0,-1, 125],
             [ 0, 0,   1]]
"""

import copy
import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np


BASE = Path(r"C:\BerxelWork\calibration\eyetohand_dual_0802")
SIDE_JSON = (
    BASE
    / "camera_side_B479"
    / "final_homography_output"
    / "camera_final_homography.json"
)
SUMMARY_DIR = BASE / "calibration_summary"
SUMMARY_SIDE_JSON = SUMMARY_DIR / "side_B479_final_homography_25mm.json"
DUAL_SUMMARY_JSON = SUMMARY_DIR / "dual_final_homography_summary.json"
MANIFEST = SUMMARY_DIR / "final_color_calibration_manifest.txt"

BOARD_WIDTH_MM = 175.0
BOARD_HEIGHT_MM = 125.0

T_180 = np.array(
    [
        [-1.0, 0.0, BOARD_WIDTH_MM],
        [0.0, -1.0, BOARD_HEIGHT_MM],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)


def transform_homography(matrix):
    H = np.asarray(matrix, dtype=np.float64)
    if H.shape != (3, 3):
        raise ValueError(f"Expected 3x3 homography, got {H.shape}")
    return (T_180 @ H).tolist()


def patch_document(document):
    patched = copy.deepcopy(document)

    raw = patched.get("raw_baseline", {})
    if "H_raw_image_to_board" in raw:
        raw["H_raw_image_to_board"] = transform_homography(
            raw["H_raw_image_to_board"]
        )

    formal = patched.get("formal_undistorted_mapping", {})
    if "H_undistorted_pixel_to_board" in formal:
        formal["H_undistorted_pixel_to_board"] = transform_homography(
            formal["H_undistorted_pixel_to_board"]
        )

    if "H_train_only_for_validation" in formal:
        formal["H_train_only_for_validation"] = transform_homography(
            formal["H_train_only_for_validation"]
        )

    patched["coordinate_frame"] = "common_board"
    patched["common_board_alignment"] = {
        "applied": True,
        "reason": (
            "Side-camera checkerboard corner ordering was rotated 180 degrees "
            "relative to the overhead/common board frame."
        ),
        "source_frame": "side_camera_local_board",
        "target_frame": "common_board",
        "formula": {
            "x_common_mm": "175.0 - x_side_mm",
            "y_common_mm": "125.0 - y_side_mm",
        },
        "transform_matrix_T_180": T_180.tolist(),
        "board_extent_mm": {
            "x": [0.0, BOARD_WIDTH_MM],
            "y": [0.0, BOARD_HEIGHT_MM],
        },
        "distance_metrics_note": (
            "The transform is a rigid 180-degree planar rotation, so all "
            "existing millimetre error magnitudes remain unchanged."
        ),
    }

    patched["board_coordinate_definition"] = {
        "frame_name": "common_board",
        "origin": [0.0, 0.0],
        "x_axis_extent_mm": [0.0, BOARD_WIDTH_MM],
        "y_axis_extent_mm": [0.0, BOARD_HEIGHT_MM],
        "unit": "mm",
        "note": (
            "This document now maps side-camera pixels directly into the same "
            "board coordinate frame used by the overhead camera."
        ),
    }

    return patched


def main():
    if not SIDE_JSON.exists():
        raise FileNotFoundError(SIDE_JSON)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SIDE_JSON.with_name(
        f"camera_final_homography_before_common_alignment_{timestamp}.json"
    )
    shutil.copy2(SIDE_JSON, backup)

    document = json.loads(SIDE_JSON.read_text(encoding="utf-8"))

    if document.get("common_board_alignment", {}).get("applied"):
        print("[INFO] Side homography is already aligned; no second flip applied.")
        patched = document
    else:
        patched = patch_document(document)
        SIDE_JSON.write_text(
            json.dumps(patched, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("[PATCHED]")
        print(SIDE_JSON)

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_SIDE_JSON.write_text(
        json.dumps(patched, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("[UPDATED SUMMARY COPY]")
    print(SUMMARY_SIDE_JSON)

    if DUAL_SUMMARY_JSON.exists():
        dual = json.loads(DUAL_SUMMARY_JSON.read_text(encoding="utf-8"))
        if "camera_side_B479" in dual:
            dual["camera_side_B479"] = patched
            DUAL_SUMMARY_JSON.write_text(
                json.dumps(dual, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print("[UPDATED DUAL SUMMARY]")
            print(DUAL_SUMMARY_JSON)

    manifest_note = (
        "\nSide-camera common-frame alignment:\n"
        "x_common = 175.0 - x_side\n"
        "y_common = 125.0 - y_side\n"
        "Reason: 180-degree checkerboard corner-order ambiguity.\n"
    )

    if MANIFEST.exists():
        current = MANIFEST.read_text(encoding="utf-8")
        if "x_common = 175.0 - x_side" not in current:
            with MANIFEST.open("a", encoding="utf-8") as handle:
                handle.write(manifest_note)

    print("[BACKUP]")
    print(backup)
    print()
    print("Next command:")
    print(
        r'python "C:\BerxelWork\calibration\validate_dual_aruco_one_point_175_25.py"'
    )


if __name__ == "__main__":
    main()
