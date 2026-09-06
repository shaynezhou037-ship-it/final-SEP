#!/usr/bin/env python3
"""Recover real calibration-view geometry and freeze a metric-blind subset.

This phase intentionally has no imports from the E1 reconstruction.  It must
finish, including the selection hash, before compute_real_zv.py is run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
ARCHIVE = Path(r"C:\BerxelWork\calibration\eyetohand_dual_0802")
SYNTHETIC_GEOMETRY = HERE.parent / "zV_GEOMETRY_CAUSALITY_TEST" / "view_geometry.csv"
CAMERAS = ("camera_overhead_B242", "camera_side_B479")
BOARD_SIZE = (8, 6)
SQUARE_M = 0.025
DESCRIPTOR_NAMES = [
    "depth_m", "tilt_deg", "normalized_center_u", "normalized_center_v",
    "log_board_footprint_px2",
]
TRAINING_INDICES = [0, 5, 47, 42, 20, 23, 9, 24, 33, 12, 35, 44]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def object_points() -> np.ndarray:
    cols, rows = BOARD_SIZE
    obj = np.zeros((cols * rows, 3), dtype=np.float32)
    obj[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    obj[:, :2] *= SQUARE_M
    return obj


def find_corners(gray: np.ndarray) -> tuple[bool, np.ndarray | None, str]:
    if hasattr(cv2, "findChessboardCornersSB"):
        flags = cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
        found, corners = cv2.findChessboardCornersSB(gray, BOARD_SIZE, flags=flags)
        if found:
            return True, corners.astype(np.float32), "findChessboardCornersSB"
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(gray, BOARD_SIZE, flags)
    if not found:
        return False, None, "none"
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 50, 0.0005)
    corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1), criteria)
    return True, corners.astype(np.float32), "findChessboardCorners"


def recover_camera(camera_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = ARCHIVE / camera_id
    calibration_path = root / "intrinsic_output" / "camera_intrinsics.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    K = np.asarray(calibration["camera_matrix"], dtype=float)
    D = np.asarray(calibration["distortion_coefficients"], dtype=float)
    accepted = list(calibration["accepted_images"])
    image_dir = root / "intrinsic_images"
    obj = object_points()
    calibration_id = f"{camera_id}:{sha(calibration_path)}"
    archived_errors = {x["name"]: float(x["rmse_px"]) for x in calibration["per_image_reprojection_rmse_px"]}
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for image_id in accepted:
        path = image_dir / image_id
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            failures.append(f"{image_id}: unreadable")
            continue
        h, w = image.shape[:2]
        expected = calibration["image_size_px"]
        if (w, h) != (int(expected["width"]), int(expected["height"])):
            failures.append(f"{image_id}: size {w}x{h}")
            continue
        found, corners, detector = find_corners(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        if not found or corners is None or len(corners) != len(obj):
            failures.append(f"{image_id}: detected {0 if corners is None else len(corners)}")
            continue
        ok, rvec, tvec = cv2.solvePnP(obj, corners, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            failures.append(f"{image_id}: solvePnP failed")
            continue
        projected, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
        uv = corners.reshape(-1, 2).astype(float)
        predicted = projected.reshape(-1, 2)
        rmse = float(np.sqrt(np.mean(np.sum((uv - predicted) ** 2, axis=1))))
        R, _ = cv2.Rodrigues(rvec)
        rv = rvec.reshape(3)
        tv = tvec.reshape(3)
        tilt = float(np.rad2deg(np.arccos(np.clip(abs(R[2, 2]), 0.0, 1.0))))
        center_obj = np.mean(obj, axis=0).reshape(1, 3)
        center_uv, _ = cv2.projectPoints(center_obj, rvec, tvec, K, D)
        center_u, center_v = center_uv.reshape(2)
        u_min, v_min = np.min(uv, axis=0)
        u_max, v_max = np.max(uv, axis=0)
        footprint = float((u_max - u_min) * (v_max - v_min))
        margin = float(min(u_min, v_min, (w - 1) - u_max, (h - 1) - v_max))
        rows.append({
            "camera_id": camera_id,
            "calibration_id": calibration_id,
            "image_id": image_id,
            "rvec_x_rad": float(rv[0]), "rvec_y_rad": float(rv[1]), "rvec_z_rad": float(rv[2]),
            "tvec_x_m": float(tv[0]), "tvec_y_m": float(tv[1]), "tvec_z_m": float(tv[2]),
            "depth_m": float(tv[2]), "tilt_deg": tilt,
            "board_center_u_px": float(center_u), "board_center_v_px": float(center_v),
            "u_min_px": float(u_min), "u_max_px": float(u_max),
            "v_min_px": float(v_min), "v_max_px": float(v_max),
            "board_footprint_px2": footprint,
            "normalized_center_u": float(center_u / w), "normalized_center_v": float(center_v / h),
            "minimum_border_margin_px": margin,
            "detected_corner_count": int(len(corners)),
            "full_board_visible": bool(margin >= 0 and len(corners) == len(obj)),
            "reprojection_rmse_px": rmse,
            "archived_reprojection_rmse_px": archived_errors[image_id],
            "detector": detector,
            "image_width_px": w, "image_height_px": h,
            "image_sha256": sha(path),
        })
    if failures:
        raise RuntimeError(f"{camera_id} recovery failures: {failures}")
    if len(rows) != len(accepted):
        raise RuntimeError(f"{camera_id}: recovered {len(rows)} != accepted {len(accepted)}")
    identity = {
        "camera_id": camera_id,
        "calibration_id": calibration_id,
        "calibration_file": str(calibration_path),
        "calibration_file_sha256": sha(calibration_path),
        "image_directory": str(image_dir),
        "accepted_image_count": len(accepted),
        "accepted_image_ids": accepted,
        "K": calibration["camera_matrix"],
        "D": calibration["distortion_coefficients"],
        "image_resolution": [calibration["image_size_px"]["width"], calibration["image_size_px"]["height"]],
        "board_geometry": {"inner_corners": [8, 6], "square_size_m": SQUARE_M},
    }
    return rows, identity


def select_maximin(rows: list[dict[str, Any]], count: int = 9) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda x: x["image_id"])
    X = np.asarray([[r["depth_m"], r["tilt_deg"], r["normalized_center_u"], r["normalized_center_v"], math.log(r["board_footprint_px2"])] for r in ordered])
    means = X.mean(axis=0)
    stds = X.std(axis=0, ddof=0)
    if np.any(stds <= 0):
        raise RuntimeError("descriptor has zero standard deviation")
    Z = (X - means) / stds
    centroid_distance = np.linalg.norm(Z, axis=1)
    first = min(range(len(ordered)), key=lambda i: (centroid_distance[i], ordered[i]["image_id"]))
    selected = [first]
    trace = [{"step": 1, "image_id": ordered[first]["image_id"], "criterion": "closest_to_standardized_centroid", "score": float(centroid_distance[first])}]
    while len(selected) < count:
        candidates = [i for i in range(len(ordered)) if i not in selected]
        scores = {i: float(np.min(np.linalg.norm(Z[i] - Z[selected], axis=1))) for i in candidates}
        best = min(candidates, key=lambda i: (-scores[i], ordered[i]["image_id"]))
        selected.append(best)
        trace.append({"step": len(selected), "image_id": ordered[best]["image_id"], "criterion": "maximum_minimum_euclidean_distance", "score": scores[best]})
    return {
        "selected_image_ids": [ordered[i]["image_id"] for i in selected],
        "selection_algorithm": "deterministic standardized-descriptor farthest-point sampling; centroid-nearest start; lexical image_id tie-break",
        "descriptor_definition": DESCRIPTOR_NAMES,
        "normalization_definition": "per-camera population z-score over all accepted usable views (ddof=0); natural log footprint before standardization",
        "normalization_mean": dict(zip(DESCRIPTOR_NAMES, means.tolist())),
        "normalization_std": dict(zip(DESCRIPTOR_NAMES, stds.tolist())),
        "distance": "Euclidean in standardized descriptor space",
        "seed": None,
        "selection_trace": trace,
    }


def geometry_comparison(real_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with SYNTHETIC_GEOMETRY.open(newline="", encoding="utf-8-sig") as f:
        synthetic = list(csv.DictReader(f))
    groups = sorted(set(x["geometry"] for x in synthetic))
    output = []
    for camera_id in CAMERAS:
        real = [x for x in real_rows if x["camera_id"] == camera_id]
        for gid in groups:
            syn = [x for x in synthetic if x["geometry"] == gid]
            descriptors = {
                "depth_m": [float(x["depth_m"]) for x in syn],
                "tilt_deg": [float(x["tilt_deg"]) for x in syn],
                "normalized_center_u": [float(x["center_u_px"]) / 640.0 for x in syn],
                "normalized_center_v": [float(x["center_v_px"]) / 480.0 for x in syn],
                "footprint_fraction": [float(x["bbox_area_px2"]) / (640.0 * 480.0) for x in syn],
            }
            overlap_flags = []
            for rr in real:
                vals = {
                    "depth_m": rr["depth_m"], "tilt_deg": rr["tilt_deg"],
                    "normalized_center_u": rr["normalized_center_u"], "normalized_center_v": rr["normalized_center_v"],
                    "footprint_fraction": rr["board_footprint_px2"] / (rr["image_width_px"] * rr["image_height_px"]),
                }
                overlap_flags.append(all(min(descriptors[k]) <= vals[k] <= max(descriptors[k]) for k in descriptors))
            real_ranges = {
                "depth_m": [min(x["depth_m"] for x in real), max(x["depth_m"] for x in real)],
                "tilt_deg": [min(x["tilt_deg"] for x in real), max(x["tilt_deg"] for x in real)],
                "normalized_center_u": [min(x["normalized_center_u"] for x in real), max(x["normalized_center_u"] for x in real)],
                "normalized_center_v": [min(x["normalized_center_v"] for x in real), max(x["normalized_center_v"] for x in real)],
                "footprint_fraction": [
                    min(x["board_footprint_px2"] / (x["image_width_px"] * x["image_height_px"]) for x in real),
                    max(x["board_footprint_px2"] / (x["image_width_px"] * x["image_height_px"]) for x in real),
                ],
            }
            outside = []
            for key, values in descriptors.items():
                if min(values) < real_ranges[key][0]:
                    outside.append(f"{key}:synthetic_low")
                if max(values) > real_ranges[key][1]:
                    outside.append(f"{key}:synthetic_high")
            output.append({
                "camera_id": camera_id, "synthetic_geometry": gid,
                "real_view_count": len(real), "synthetic_view_count": len(syn),
                "real_depth_min_m": min(x["depth_m"] for x in real), "real_depth_max_m": max(x["depth_m"] for x in real),
                "synthetic_depth_min_m": min(descriptors["depth_m"]), "synthetic_depth_max_m": max(descriptors["depth_m"]),
                "real_tilt_min_deg": min(x["tilt_deg"] for x in real), "real_tilt_max_deg": max(x["tilt_deg"] for x in real),
                "synthetic_tilt_min_deg": min(descriptors["tilt_deg"]), "synthetic_tilt_max_deg": max(descriptors["tilt_deg"]),
                "real_center_u_min_norm": min(x["normalized_center_u"] for x in real), "real_center_u_max_norm": max(x["normalized_center_u"] for x in real),
                "synthetic_center_u_min_norm": min(descriptors["normalized_center_u"]), "synthetic_center_u_max_norm": max(descriptors["normalized_center_u"]),
                "real_center_v_min_norm": min(x["normalized_center_v"] for x in real), "real_center_v_max_norm": max(x["normalized_center_v"] for x in real),
                "synthetic_center_v_min_norm": min(descriptors["normalized_center_v"]), "synthetic_center_v_max_norm": max(descriptors["normalized_center_v"]),
                "real_footprint_fraction_min": min(x["board_footprint_px2"] / (x["image_width_px"] * x["image_height_px"]) for x in real),
                "real_footprint_fraction_max": max(x["board_footprint_px2"] / (x["image_width_px"] * x["image_height_px"]) for x in real),
                "synthetic_footprint_fraction_min": min(descriptors["footprint_fraction"]),
                "synthetic_footprint_fraction_max": max(descriptors["footprint_fraction"]),
                "real_border_margin_min_px": min(x["minimum_border_margin_px"] for x in real),
                "real_full_board_visible_count": sum(bool(x["full_board_visible"]) for x in real),
                "real_views_inside_joint_synthetic_descriptor_envelope": sum(overlap_flags),
                "synthetic_descriptors_outside_real_envelope": ";".join(outside),
                "classification_inputs": "geometry_only",
            })
    return output


def main() -> int:
    all_rows: list[dict[str, Any]] = []
    identities: dict[str, Any] = {}
    for camera_id in CAMERAS:
        rows, identity = recover_camera(camera_id)
        all_rows.extend(rows)
        identities[camera_id] = identity
    write_csv(HERE / "real_view_geometry_all.csv", all_rows)
    write_csv(HERE / "real_vs_synthetic_geometry.csv", geometry_comparison(all_rows))

    selection = {
        "artifact": "E1-v4R1_REAL_zV_ATTAINABILITY_BRIDGE_GEOMETRY_SELECTION",
        "selection_phase": "completed_before_any_real_zV_singular_value_or_principal_angle_calculation",
        "geometry_selection_used_E1_metrics": False,
        "selected_view_count_per_camera": 9,
        "real_checkerboard_split": {
            "declaration_timing": "frozen_with_geometry selection before any real E1 metric calculation",
            "indexing": "row-major 8 columns x 6 rows, zero-based",
            "training_indices": TRAINING_INDICES,
            "heldout_indices": [i for i in range(48) if i not in TRAINING_INDICES],
            "rule": "fixed index-based spatially distributed 12-point training set; complement held out; no outcome tuning",
        },
        "source_calibrations": identities,
        "per_camera": {},
    }
    for camera_id in CAMERAS:
        selection["per_camera"][camera_id] = select_maximin([x for x in all_rows if x["camera_id"] == camera_id])
    selection["selection_payload_sha256"] = canonical_sha(selection)
    (HERE / "real_9view_selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    print(json.dumps({
        "recovered_views": {c: sum(x["camera_id"] == c for x in all_rows) for c in CAMERAS},
        "selection_payload_sha256": selection["selection_payload_sha256"],
        "selection_file_sha256": sha(HERE / "real_9view_selection.json"),
        "selected": {c: selection["per_camera"][c]["selected_image_ids"] for c in CAMERAS},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
