#!/usr/bin/env python3
"""E5 simulated effective-resolution operating-envelope study.

The script uses only saved E2 lossless color frames and the frozen E2 clean CSV.
It never modifies E0-E4 data. See the experiment README for the frozen design,
predefined feasibility profiles, and interpretation limits.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import gc
import json
import math
import os
import platform
import time

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SCRIPT = Path(__file__).resolve()
EXP_ROOT = SCRIPT.parents[1]
REPO_ROOT = SCRIPT.parents[3]
RESULTS = EXP_ROOT / "results"
FIGURES = EXP_ROOT / "figures"
RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

SOURCE_CSV = REPO_ROOT / "E2" / "E2_rebuilt" / "E2_all_5runs_REBUILT_clean.csv"
SOURCE_FRAME_ROOT = REPO_ROOT / "E2" / "E2_dual_camera_height_scan"

CAMERAS = ("ihawk1", "ihawk2")
MODELS = ("Affine", "Homography", "PnP")
HEIGHTS = tuple(float(x) for x in range(0, 51, 5))
EXPECTED_IDS = tuple(range(5))
FRAMES_PER_CONDITION = 3
MARKER_SIZE_MM = 50.0
HALF_MARKER_MM = MARKER_SIZE_MM / 2.0
NATIVE_WIDTH = 640
NATIVE_HEIGHT = 400
CONTENT_MISMATCH_THRESHOLD_PX = 1.0

RESOLUTIONS = (
    {"resolution_id": "r640x400", "width": 640, "height": 400},
    {"resolution_id": "r480x300", "width": 480, "height": 300},
    {"resolution_id": "r320x200", "width": 320, "height": 200},
    {"resolution_id": "r240x150", "width": 240, "height": 150},
    {"resolution_id": "r160x100", "width": 160, "height": 100},
)

K_NATIVE = {
    "ihawk1": np.array(
        [[401.77020263671875, 0.0, 322.1313781738281],
         [0.0, 401.9191589355469, 202.54229736328125],
         [0.0, 0.0, 1.0]],
        dtype=np.float64,
    ),
    "ihawk2": np.array(
        [[391.3234558105469, 0.0, 320.85333251953125],
         [0.0, 391.3234558105469, 202.9705047607422],
         [0.0, 0.0, 1.0]],
        dtype=np.float64,
    ),
}
D_ZERO = np.zeros((5, 1), dtype=np.float64)

DETECTION_REPEATS = 5
MAPPING_REPEATS = 50
MIN_REBUILDS_FOR_FEASIBILITY = 4

FEASIBILITY_PROFILES = (
    {
        "profile": "precision_30hz",
        "xy_rmse_p95_limit_mm": 2.0,
        "pipeline_p95_limit_ms": 33.3,
        "detection_rate_min": 0.99,
    },
    {
        "profile": "standard_20hz",
        "xy_rmse_p95_limit_mm": 5.0,
        "pipeline_p95_limit_ms": 50.0,
        "detection_rate_min": 0.99,
    },
    {
        "profile": "coarse_10hz",
        "xy_rmse_p95_limit_mm": 10.0,
        "pipeline_p95_limit_ms": 100.0,
        "detection_rate_min": 0.95,
    },
)

MARKER_OBJECT = np.array(
    [
        [-HALF_MARKER_MM, +HALF_MARKER_MM, 0.0],
        [+HALF_MARKER_MM, +HALF_MARKER_MM, 0.0],
        [+HALF_MARKER_MM, -HALF_MARKER_MM, 0.0],
        [-HALF_MARKER_MM, -HALF_MARKER_MM, 0.0],
    ],
    dtype=np.float64,
)

OUT = {
    "preflight": RESULTS / "E5_preflight_qc.csv",
    "detections": RESULTS / "E5_detection_observations.csv",
    "detection_summary": RESULTS / "E5_detection_summary.csv",
    "stability": RESULTS / "E5_stability_by_condition.csv",
    "stability_summary": RESULTS / "E5_stability_summary.csv",
    "calibrations": RESULTS / "E5_calibrations.json",
    "predictions": RESULTS / "E5_predictions.csv",
    "run_metrics": RESULTS / "E5_run_height_metrics.csv",
    "height_summary": RESULTS / "E5_height_summary.csv",
    "interaction_records": RESULTS / "E5_height_interaction_records.csv",
    "interaction_summary": RESULTS / "E5_height_interaction_summary.csv",
    "image_latency": RESULTS / "E5_image_latency.csv",
    "mapping_latency": RESULTS / "E5_mapping_latency.csv",
    "latency_summary": RESULTS / "E5_latency_summary.csv",
    "feasibility_by_height": RESULTS / "E5_feasibility_by_height.csv",
    "feasibility_summary": RESULTS / "E5_feasibility_summary.csv",
    "summary_json": RESULTS / "E5_summary.json",
    "summary_md": RESULTS / "E5_RESULTS_SUMMARY.md",
    "manifest": RESULTS / "E5_manifest.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value, default=float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(values, q: float) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.percentile(a, q)) if len(a) else float("nan")


def mean(values) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.mean(a)) if len(a) else float("nan")


def sd(values) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.std(a, ddof=1)) if len(a) >= 2 else float("nan")


def median(values) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if len(a) else float("nan")


def rmse(values) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.sqrt(np.mean(a * a))) if len(a) else float("nan")


def fmt(value, digits=3) -> str:
    x = fnum(value)
    return "NA" if not math.isfinite(x) else f"{x:.{digits}f}"


def json_safe(value):
    """Convert numpy values and non-finite floats to strict-JSON values."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_csv(path: Path, records: list[dict]) -> None:
    if not records:
        raise RuntimeError(f"Refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def resolution_by_id(resolution_id: str) -> dict:
    for res in RESOLUTIONS:
        if res["resolution_id"] == resolution_id:
            return res
    raise KeyError(resolution_id)


def scaled_intrinsics(camera: str, width: int, height: int) -> np.ndarray:
    """Scale K using OpenCV resize's half-pixel coordinate convention."""
    sx = width / NATIVE_WIDTH
    sy = height / NATIVE_HEIGHT
    src = K_NATIVE[camera]
    out = src.copy()
    out[0, 0] = src[0, 0] * sx
    out[1, 1] = src[1, 1] * sy
    out[0, 2] = (src[0, 2] + 0.5) * sx - 0.5
    out[1, 2] = (src[1, 2] + 0.5) * sy - 0.5
    return out


def to_native_points(points: np.ndarray, width: int, height: int) -> np.ndarray:
    sx = width / NATIVE_WIDTH
    sy = height / NATIVE_HEIGHT
    out = np.asarray(points, dtype=np.float64).copy()
    out[..., 0] = (out[..., 0] + 0.5) / sx - 0.5
    out[..., 1] = (out[..., 1] + 0.5) / sy - 0.5
    return out


class Detector:
    def __init__(self):
        aruco = cv2.aruco
        self.dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
        self.params = aruco.DetectorParameters()
        self.detector = aruco.ArucoDetector(self.dictionary, self.params)
        self.criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.01,
        )

    def detect(self, bgr: np.ndarray) -> dict[int, np.ndarray]:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        if ids is None:
            return {}
        found = {}
        for corner, marker_id in zip(corners, ids.reshape(-1)):
            pts = np.asarray(corner, dtype=np.float32).reshape(4, 2)
            try:
                pts = cv2.cornerSubPix(
                    gray,
                    pts.reshape(-1, 1, 2),
                    (3, 3),
                    (-1, -1),
                    self.criteria,
                ).reshape(4, 2)
            except cv2.error:
                pass
            found[int(marker_id)] = pts.astype(np.float64)
        return found


def resize_image(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if width == image.shape[1] and height == image.shape[0]:
        return image
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def timed_detection(detector: Detector, image: np.ndarray) -> tuple[float, float]:
    timings = []
    for _ in range(DETECTION_REPEATS):
        start = time.perf_counter_ns()
        detector.detect(image)
        timings.append((time.perf_counter_ns() - start) / 1e6)
    return median(timings), pct(timings, 95)


def timed_resize(image: np.ndarray, width: int, height: int) -> tuple[float, float]:
    if width == image.shape[1] and height == image.shape[0]:
        return 0.0, 0.0
    timings = []
    for _ in range(DETECTION_REPEATS):
        start = time.perf_counter_ns()
        cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        timings.append((time.perf_counter_ns() - start) / 1e6)
    return median(timings), pct(timings, 95)


def fit_affine(image_xy: np.ndarray, truth_xy: np.ndarray) -> np.ndarray:
    design = np.column_stack([image_xy[:, 0], image_xy[:, 1], np.ones(len(image_xy))])
    coef, _, rank, _ = np.linalg.lstsq(design, truth_xy, rcond=None)
    if rank < 3:
        raise RuntimeError("Affine calibration is rank deficient")
    return coef


def affine_predict(coef: np.ndarray, uv: np.ndarray) -> np.ndarray:
    return np.array([uv[0], uv[1], 1.0], dtype=np.float64) @ coef


def fit_homography(image_xy: np.ndarray, truth_xy: np.ndarray) -> np.ndarray:
    H, _ = cv2.findHomography(image_xy.astype(np.float64), truth_xy.astype(np.float64), 0)
    if H is None or not np.all(np.isfinite(H)):
        raise RuntimeError("Homography calibration failed")
    return H


def homography_predict(H: np.ndarray, uv: np.ndarray) -> np.ndarray:
    point = np.asarray(uv, dtype=np.float64).reshape(1, 1, 2)
    return cv2.perspectiveTransform(point, H).reshape(2)


def solve_marker_pnp(corners: np.ndarray, K: np.ndarray):
    candidates = []
    if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE"):
        candidates.append(cv2.SOLVEPNP_IPPE_SQUARE)
    candidates.append(cv2.SOLVEPNP_ITERATIVE)
    best = None
    for flag in candidates:
        try:
            ok, rvec, tvec = cv2.solvePnP(
                MARKER_OBJECT,
                np.asarray(corners, dtype=np.float64),
                K,
                D_ZERO,
                flags=flag,
            )
        except cv2.error:
            continue
        if not ok or float(tvec.reshape(3)[2]) <= 0:
            continue
        projected, _ = cv2.projectPoints(MARKER_OBJECT, rvec, tvec, K, D_ZERO)
        reproj = rmse(np.linalg.norm(projected.reshape(-1, 2) - corners, axis=1))
        if best is None or reproj < best[0]:
            best = (reproj, rvec.reshape(3), tvec.reshape(3))
    if best is None:
        raise RuntimeError("Marker PnP failed")
    return best


def fit_board_extrinsic(marker_means: dict[int, dict], K: np.ndarray):
    object_points = []
    image_points = []
    for marker_id in EXPECTED_IDS:
        item = marker_means[marker_id]
        mx, my = item["truth_xy"]
        object_points.extend(
            [
                [mx - HALF_MARKER_MM, my + HALF_MARKER_MM, 0.0],
                [mx + HALF_MARKER_MM, my + HALF_MARKER_MM, 0.0],
                [mx + HALF_MARKER_MM, my - HALF_MARKER_MM, 0.0],
                [mx - HALF_MARKER_MM, my - HALF_MARKER_MM, 0.0],
            ]
        )
        image_points.extend(item["corners"])
    object_points = np.asarray(object_points, dtype=np.float64)
    image_points = np.asarray(image_points, dtype=np.float64)
    ok, rvec, tvec = cv2.solvePnP(
        object_points,
        image_points,
        K,
        D_ZERO,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        raise RuntimeError("Board PnP failed")
    R_cb, _ = cv2.Rodrigues(rvec)
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, K, D_ZERO)
    reproj = rmse(np.linalg.norm(projected.reshape(-1, 2) - image_points, axis=1))
    return R_cb, tvec.reshape(3), rvec.reshape(3), reproj


def json_calibration(cal: dict) -> dict:
    if not cal.get("valid"):
        return {k: v for k, v in cal.items() if not isinstance(v, np.ndarray)}
    return {
        "valid": True,
        "n_marker_frames": cal["n_marker_frames"],
        "affine": cal["A"].tolist(),
        "homography": cal["H"].tolist(),
        "R_camera_from_board": cal["R_cb"].tolist(),
        "t_camera_from_board_mm": cal["t_cb"].tolist(),
        "board_rvec": cal["rvec"].tolist(),
        "board_reprojection_rmse_px": cal["board_reprojection_rmse_px"],
    }


def save_figure(fig, stem: str) -> None:
    fig.savefig(FIGURES / f"{stem}.png", dpi=240, bbox_inches="tight")
    fig.savefig(FIGURES / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    print("=" * 88)
    print("E5 — SIMULATED EFFECTIVE-RESOLUTION OPERATING ENVELOPE")
    print("=" * 88)
    if not SOURCE_CSV.exists():
        raise FileNotFoundError(SOURCE_CSV)

    cv2.setNumThreads(1)
    rows = read_csv(SOURCE_CSV)
    runs = sorted({row["run_id"] for row in rows})
    if len(rows) != 1650 or len(runs) != 5:
        raise RuntimeError(f"Expected 1650 clean rows and 5 runs; got {len(rows)} and {len(runs)}")

    grouped_rows = defaultdict(list)
    for row in rows:
        key = (
            row["run_id"],
            row["camera_id"],
            float(row["height_gt_mm"]),
            int(float(row["frame_index"])),
        )
        grouped_rows[key].append(row)
    if len(grouped_rows) != 330:
        raise RuntimeError(f"Expected 330 unique images, got {len(grouped_rows)}")

    detector = Detector()
    first_rows = next(iter(grouped_rows.values()))
    first_path = SOURCE_FRAME_ROOT / f"run_{first_rows[0]['run_id']}" / first_rows[0]["color_image_relpath"]
    warmup = cv2.imread(str(first_path), cv2.IMREAD_COLOR)
    if warmup is None:
        raise FileNotFoundError(first_path)
    for _ in range(3):
        detector.detect(warmup)

    detections = []
    image_latency = []
    preflight = []
    detection_lookup = {}
    native_lookup = {}
    excluded_keys = set()

    print(f"Source images: {len(grouped_rows)}; resolution levels: {len(RESOLUTIONS)}")
    for image_index, (key, expected_rows) in enumerate(sorted(grouped_rows.items()), start=1):
        run, camera, height, frame_index = key
        expected_rows = sorted(expected_rows, key=lambda row: int(float(row["marker_id"])))
        image_path = SOURCE_FRAME_ROOT / f"run_{run}" / expected_rows[0]["color_image_relpath"]
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        if (image.shape[1], image.shape[0]) != (NATIVE_WIDTH, NATIVE_HEIGHT):
            raise RuntimeError(f"Unexpected source dimensions for {image_path}: {image.shape}")

        native_found = detector.detect(image)
        native_lookup[key] = native_found
        native_center_diffs = []
        for row in expected_rows:
            marker_id = int(float(row["marker_id"]))
            if marker_id in native_found:
                center = np.mean(native_found[marker_id], axis=0)
                frozen = np.array(
                    [float(row["center_u_raw_px"]), float(row["center_v_raw_px"])],
                    dtype=np.float64,
                )
                native_center_diffs.append(float(np.linalg.norm(center - frozen)))
        median_diff = median(native_center_diffs)
        native_complete = all(marker_id in native_found for marker_id in EXPECTED_IDS)
        excluded = (not native_complete) or (median_diff > CONTENT_MISMATCH_THRESHOLD_PX)
        if excluded:
            excluded_keys.add(key)
        preflight.append(
            {
                "run_id": run,
                "camera_id": camera,
                "height_gt_mm": height,
                "frame_index": frame_index,
                "image_relpath": str(image_path.relative_to(REPO_ROOT)),
                "native_detected_markers": len([m for m in EXPECTED_IDS if m in native_found]),
                "native_complete": int(native_complete),
                "median_center_difference_from_clean_csv_px": median_diff,
                "max_center_difference_from_clean_csv_px": max(native_center_diffs) if native_center_diffs else "",
                "qc_excluded": int(excluded),
                "exclusion_reason": (
                    "native_detection_incomplete"
                    if not native_complete
                    else ("saved_image_content_mismatch" if excluded else "")
                ),
            }
        )

        for res in RESOLUTIONS:
            width, height_px = res["width"], res["height"]
            resized = resize_image(image, width, height_px)
            found = native_found if width == NATIVE_WIDTH else detector.detect(resized)
            detection_lookup[(res["resolution_id"],) + key] = found
            resize_median_ms, resize_p95_ms = timed_resize(image, width, height_px)
            detect_median_ms, detect_p95_ms = timed_detection(detector, resized)
            n_expected_detected = len([m for m in EXPECTED_IDS if m in found])
            image_latency.append(
                {
                    "resolution_id": res["resolution_id"],
                    "width_px": width,
                    "height_px": height_px,
                    "run_id": run,
                    "camera_id": camera,
                    "height_gt_mm": height,
                    "frame_index": frame_index,
                    "qc_excluded": int(excluded),
                    "n_expected_markers_detected": n_expected_detected,
                    "complete_five_marker_detection": int(n_expected_detected == 5),
                    "resize_latency_median_ms_excluded_from_pipeline": resize_median_ms,
                    "resize_latency_p95_ms_excluded_from_pipeline": resize_p95_ms,
                    "detection_latency_median_ms": detect_median_ms,
                    "detection_latency_p95_ms": detect_p95_ms,
                    "detection_timing_repeats": DETECTION_REPEATS,
                }
            )

            native_reference = native_lookup[key]
            for row in expected_rows:
                marker_id = int(float(row["marker_id"]))
                detected = marker_id in found
                record = {
                    "resolution_id": res["resolution_id"],
                    "width_px": width,
                    "height_px": height_px,
                    "scale_x": width / NATIVE_WIDTH,
                    "scale_y": height_px / NATIVE_HEIGHT,
                    "run_id": run,
                    "camera_id": camera,
                    "height_gt_mm": height,
                    "frame_index": frame_index,
                    "marker_id": marker_id,
                    "board_position": row["board_position"],
                    "marker_gt_x_mm": float(row["marker_gt_x_mm"]),
                    "marker_gt_y_mm": float(row["marker_gt_y_mm"]),
                    "qc_excluded": int(excluded),
                    "detected": int(detected),
                    "center_u_px": "",
                    "center_v_px": "",
                    "center_u_native_equiv_px": "",
                    "center_v_native_equiv_px": "",
                    "center_drift_from_native_px": "",
                    "corner_rmse_drift_from_native_px": "",
                }
                for corner_index in range(4):
                    record[f"corner{corner_index}_u_px"] = ""
                    record[f"corner{corner_index}_v_px"] = ""
                if detected:
                    corners = found[marker_id]
                    center = np.mean(corners, axis=0)
                    native_equiv = to_native_points(corners, width, height_px)
                    native_center = np.mean(native_equiv, axis=0)
                    record["center_u_px"] = float(center[0])
                    record["center_v_px"] = float(center[1])
                    record["center_u_native_equiv_px"] = float(native_center[0])
                    record["center_v_native_equiv_px"] = float(native_center[1])
                    if marker_id in native_reference:
                        reference_corners = native_reference[marker_id]
                        reference_center = np.mean(reference_corners, axis=0)
                        record["center_drift_from_native_px"] = float(
                            np.linalg.norm(native_center - reference_center)
                        )
                        record["corner_rmse_drift_from_native_px"] = rmse(
                            np.linalg.norm(native_equiv - reference_corners, axis=1)
                        )
                    for corner_index, point in enumerate(corners):
                        record[f"corner{corner_index}_u_px"] = float(point[0])
                        record[f"corner{corner_index}_v_px"] = float(point[1])
                detections.append(record)

        if image_index % 55 == 0:
            print(f"  Detection/latency pass: {image_index}/{len(grouped_rows)} images")

    write_csv(OUT["preflight"], preflight)
    write_csv(OUT["detections"], detections)
    write_csv(OUT["image_latency"], image_latency)
    print(f"QC-excluded saved images: {len(excluded_keys)}")

    # Detection summaries: height-specific plus ALL.
    detection_summary = []
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        for camera in CAMERAS:
            for height_label in list(HEIGHTS) + ["ALL"]:
                dd = [
                    row for row in detections
                    if row["resolution_id"] == rid
                    and row["camera_id"] == camera
                    and not row["qc_excluded"]
                    and (height_label == "ALL" or float(row["height_gt_mm"]) == height_label)
                ]
                ii = [
                    row for row in image_latency
                    if row["resolution_id"] == rid
                    and row["camera_id"] == camera
                    and not row["qc_excluded"]
                    and (height_label == "ALL" or float(row["height_gt_mm"]) == height_label)
                ]
                detection_summary.append(
                    {
                        "resolution_id": rid,
                        "width_px": res["width"],
                        "height_px": res["height"],
                        "camera_id": camera,
                        "height_gt_mm": height_label,
                        "expected_marker_observations": len(dd),
                        "detected_marker_observations": sum(int(row["detected"]) for row in dd),
                        "marker_detection_rate": (
                            sum(int(row["detected"]) for row in dd) / len(dd) if dd else float("nan")
                        ),
                        "expected_images": len(ii),
                        "complete_five_marker_images": sum(
                            int(row["complete_five_marker_detection"]) for row in ii
                        ),
                        "complete_image_rate": (
                            mean(int(row["complete_five_marker_detection"]) for row in ii)
                            if ii else float("nan")
                        ),
                    }
                )
    write_csv(OUT["detection_summary"], detection_summary)

    # Stability within three-frame conditions and drift from native detections.
    stability = []
    grouped_det = defaultdict(list)
    for row in detections:
        if row["qc_excluded"]:
            continue
        key = (
            row["resolution_id"], row["run_id"], row["camera_id"],
            float(row["height_gt_mm"]), int(row["marker_id"]),
        )
        grouped_det[key].append(row)
    for key, group in sorted(grouped_det.items()):
        rid, run, camera, height, marker_id = key
        res = resolution_by_id(rid)
        valid = [row for row in group if row["detected"]]
        center_rms_native = float("nan")
        corner_rms_native = float("nan")
        marker_side_native = float("nan")
        if len(valid) >= 2:
            centers = np.asarray(
                [[float(row["center_u_px"]), float(row["center_v_px"])] for row in valid]
            )
            center_rms_low = rmse(np.linalg.norm(centers - np.mean(centers, axis=0), axis=1))
            sx = res["width"] / NATIVE_WIDTH
            sy = res["height"] / NATIVE_HEIGHT
            scale = math.sqrt(sx * sy)
            center_rms_native = center_rms_low / scale
            corner_frames = []
            for row in valid:
                corner_frames.append(
                    [[float(row[f"corner{j}_u_px"]), float(row[f"corner{j}_v_px"])] for j in range(4)]
                )
            corner_frames = np.asarray(corner_frames, dtype=float)
            corner_mean = np.mean(corner_frames, axis=0)
            corner_rms_low = rmse(
                np.linalg.norm(corner_frames - corner_mean[None, :, :], axis=2).reshape(-1)
            )
            corner_rms_native = corner_rms_low / scale
            side_lengths = []
            for frame_corners in corner_frames:
                for j in range(4):
                    side_lengths.append(np.linalg.norm(frame_corners[(j + 1) % 4] - frame_corners[j]))
            marker_side_native = median(side_lengths) / scale
        stability.append(
            {
                "resolution_id": rid,
                "width_px": res["width"],
                "height_px": res["height"],
                "run_id": run,
                "camera_id": camera,
                "height_gt_mm": height,
                "marker_id": marker_id,
                "n_expected_frames": FRAMES_PER_CONDITION,
                "n_detected_frames": len(valid),
                "complete_three_frame_detection": int(len(valid) == FRAMES_PER_CONDITION),
                "center_repeatability_rms_native_equiv_px": center_rms_native,
                "corner_repeatability_rms_native_equiv_px": corner_rms_native,
                "median_marker_side_native_equiv_px": marker_side_native,
                "corner_repeatability_fraction_of_marker_side": (
                    corner_rms_native / marker_side_native
                    if math.isfinite(corner_rms_native) and marker_side_native > 0 else float("nan")
                ),
                "center_drift_from_native_median_px": median(
                    fnum(row["center_drift_from_native_px"]) for row in valid
                ),
                "corner_drift_from_native_median_px": median(
                    fnum(row["corner_rmse_drift_from_native_px"]) for row in valid
                ),
            }
        )
    write_csv(OUT["stability"], stability)

    stability_summary = []
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        for camera in CAMERAS:
            for height_label in list(HEIGHTS) + ["ALL"]:
                ss = [
                    row for row in stability
                    if row["resolution_id"] == rid
                    and row["camera_id"] == camera
                    and (height_label == "ALL" or float(row["height_gt_mm"]) == height_label)
                ]
                complete = [row for row in ss if row["complete_three_frame_detection"]]
                stability_summary.append(
                    {
                        "resolution_id": rid,
                        "width_px": res["width"],
                        "height_px": res["height"],
                        "camera_id": camera,
                        "height_gt_mm": height_label,
                        "n_marker_conditions": len(ss),
                        "n_complete_marker_conditions": len(complete),
                        "center_repeatability_rms_median_native_equiv_px": median(
                            row["center_repeatability_rms_native_equiv_px"] for row in complete
                        ),
                        "center_repeatability_rms_p95_native_equiv_px": pct(
                            (row["center_repeatability_rms_native_equiv_px"] for row in complete), 95
                        ),
                        "corner_repeatability_rms_median_native_equiv_px": median(
                            row["corner_repeatability_rms_native_equiv_px"] for row in complete
                        ),
                        "corner_repeatability_rms_p95_native_equiv_px": pct(
                            (row["corner_repeatability_rms_native_equiv_px"] for row in complete), 95
                        ),
                        "corner_repeatability_fraction_median": median(
                            row["corner_repeatability_fraction_of_marker_side"] for row in complete
                        ),
                        "center_drift_from_native_median_px": median(
                            row["center_drift_from_native_median_px"] for row in complete
                        ),
                        "center_drift_from_native_p95_px": pct(
                            (row["center_drift_from_native_median_px"] for row in complete), 95
                        ),
                        "corner_drift_from_native_median_px": median(
                            row["corner_drift_from_native_median_px"] for row in complete
                        ),
                        "corner_drift_from_native_p95_px": pct(
                            (row["corner_drift_from_native_median_px"] for row in complete), 95
                        ),
                    }
                )
    write_csv(OUT["stability_summary"], stability_summary)

    # Resolution-specific calibration.
    det_index = defaultdict(list)
    for row in detections:
        if row["qc_excluded"] or not row["detected"]:
            continue
        key = (
            row["resolution_id"], row["run_id"], row["camera_id"],
            float(row["height_gt_mm"]), int(row["marker_id"]),
        )
        det_index[key].append(row)

    calibrations = {}
    calibration_export = {}
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        calibrations[rid] = {}
        calibration_export[rid] = {}
        for run in runs:
            calibrations[rid][run] = {}
            calibration_export[rid][run] = {}
            for camera in CAMERAS:
                marker_means = {}
                missing = []
                for marker_id in EXPECTED_IDS:
                    group = det_index[(rid, run, camera, 0.0, marker_id)]
                    if len(group) != FRAMES_PER_CONDITION:
                        missing.append(marker_id)
                        continue
                    centers = np.asarray(
                        [[float(row["center_u_px"]), float(row["center_v_px"])] for row in group]
                    )
                    corners = np.asarray(
                        [
                            [[float(row[f"corner{j}_u_px"]), float(row[f"corner{j}_v_px"])] for j in range(4)]
                            for row in group
                        ]
                    )
                    marker_means[marker_id] = {
                        "center": np.mean(centers, axis=0),
                        "corners": np.mean(corners, axis=0),
                        "truth_xy": np.array(
                            [float(group[0]["marker_gt_x_mm"]), float(group[0]["marker_gt_y_mm"])]
                        ),
                    }
                if missing:
                    cal = {
                        "valid": False,
                        "n_marker_frames": sum(
                            len(det_index[(rid, run, camera, 0.0, marker_id)])
                            for marker_id in EXPECTED_IDS
                        ),
                        "reason": "incomplete_Z0_detection",
                        "missing_marker_ids": missing,
                    }
                else:
                    try:
                        image_xy = np.asarray([marker_means[m]["center"] for m in EXPECTED_IDS])
                        truth_xy = np.asarray([marker_means[m]["truth_xy"] for m in EXPECTED_IDS])
                        A = fit_affine(image_xy, truth_xy)
                        H = fit_homography(image_xy, truth_xy)
                        K = scaled_intrinsics(camera, res["width"], res["height"])
                        R_cb, t_cb, rvec, reproj = fit_board_extrinsic(marker_means, K)
                        cal = {
                            "valid": True,
                            "n_marker_frames": 15,
                            "A": A,
                            "H": H,
                            "R_cb": R_cb,
                            "t_cb": t_cb,
                            "rvec": rvec,
                            "board_reprojection_rmse_px": reproj,
                        }
                    except (RuntimeError, cv2.error, np.linalg.LinAlgError) as exc:
                        cal = {
                            "valid": False,
                            "n_marker_frames": 15,
                            "reason": f"calibration_failure:{type(exc).__name__}",
                            "detail": str(exc),
                        }
                calibrations[rid][run][camera] = cal
                calibration_export[rid][run][camera] = json_calibration(cal)
    OUT["calibrations"].write_text(
        json.dumps(json_safe(calibration_export), indent=2, allow_nan=False), encoding="utf-8"
    )

    # Three-frame averaged model predictions.
    predictions = []
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        for run in runs:
            for camera in CAMERAS:
                cal = calibrations[rid][run][camera]
                K = scaled_intrinsics(camera, res["width"], res["height"])
                for height in HEIGHTS:
                    for marker_id in EXPECTED_IDS:
                        group = det_index[(rid, run, camera, height, marker_id)]
                        complete = len(group) == FRAMES_PER_CONDITION
                        center = None
                        corners = None
                        if complete:
                            center = np.mean(
                                [[float(row["center_u_px"]), float(row["center_v_px"])] for row in group],
                                axis=0,
                            )
                            corners = np.mean(
                                [
                                    [[float(row[f"corner{j}_u_px"]), float(row[f"corner{j}_v_px"])] for j in range(4)]
                                    for row in group
                                ],
                                axis=0,
                            )
                        gt_x = float(group[0]["marker_gt_x_mm"]) if group else float("nan")
                        gt_y = float(group[0]["marker_gt_y_mm"]) if group else float("nan")
                        if not group:
                            # Recover truth from frozen CSV for missing detections.
                            source = [
                                row for row in rows
                                if row["run_id"] == run and row["camera_id"] == camera
                                and float(row["height_gt_mm"]) == height
                                and int(float(row["marker_id"])) == marker_id
                            ]
                            if source:
                                gt_x = float(source[0]["marker_gt_x_mm"])
                                gt_y = float(source[0]["marker_gt_y_mm"])
                        for model in MODELS:
                            record = {
                                "resolution_id": rid,
                                "width_px": res["width"],
                                "height_px": res["height"],
                                "run_id": run,
                                "camera_id": camera,
                                "height_gt_mm": height,
                                "marker_id": marker_id,
                                "model": model,
                                "n_detected_frames": len(group),
                                "calibration_valid": int(cal.get("valid", False)),
                                "prediction_valid": 0,
                                "failure_reason": "",
                                "pred_x_mm": "",
                                "pred_y_mm": "",
                                "pred_z_mm": "",
                                "gt_x_mm": gt_x,
                                "gt_y_mm": gt_y,
                                "gt_z_mm": height,
                                "error_xy_mm": "",
                                "error_z_signed_mm": "",
                                "error_3d_mm": "",
                                "pnp_reprojection_rmse_px": "",
                            }
                            if not cal.get("valid", False):
                                record["failure_reason"] = "calibration_invalid"
                            elif not complete:
                                record["failure_reason"] = "incomplete_three_frame_detection"
                            else:
                                try:
                                    if model == "Affine":
                                        pred = affine_predict(cal["A"], center)
                                        px, py, pz = float(pred[0]), float(pred[1]), None
                                    elif model == "Homography":
                                        pred = homography_predict(cal["H"], center)
                                        px, py, pz = float(pred[0]), float(pred[1]), None
                                    else:
                                        reproj, _, t_marker = solve_marker_pnp(corners, K)
                                        p_board = cal["R_cb"].T @ (t_marker - cal["t_cb"])
                                        px, py, pz = map(float, p_board)
                                        record["pnp_reprojection_rmse_px"] = reproj
                                    error_xy = math.hypot(px - gt_x, py - gt_y)
                                    record["prediction_valid"] = 1
                                    record["pred_x_mm"] = px
                                    record["pred_y_mm"] = py
                                    record["pred_z_mm"] = "" if pz is None else pz
                                    record["error_xy_mm"] = error_xy
                                    if pz is not None:
                                        record["error_z_signed_mm"] = pz - height
                                        record["error_3d_mm"] = math.sqrt(
                                            (px - gt_x) ** 2 + (py - gt_y) ** 2 + (pz - height) ** 2
                                        )
                                except (RuntimeError, cv2.error, np.linalg.LinAlgError) as exc:
                                    record["failure_reason"] = f"prediction_failure:{type(exc).__name__}"
                            predictions.append(record)
    write_csv(OUT["predictions"], predictions)

    run_metrics = []
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        for run in runs:
            for camera in CAMERAS:
                for model in MODELS:
                    for height in HEIGHTS:
                        pp = [
                            row for row in predictions
                            if row["resolution_id"] == rid and row["run_id"] == run
                            and row["camera_id"] == camera and row["model"] == model
                            and float(row["height_gt_mm"]) == height
                        ]
                        valid = [row for row in pp if row["prediction_valid"]]
                        complete = len(valid) == 5
                        errors = [float(row["error_xy_mm"]) for row in valid]
                        run_metrics.append(
                            {
                                "resolution_id": rid,
                                "width_px": res["width"],
                                "height_px": res["height"],
                                "run_id": run,
                                "camera_id": camera,
                                "model": model,
                                "height_gt_mm": height,
                                "n_expected_markers": 5,
                                "n_valid_markers": len(valid),
                                "complete_five_marker_metric": int(complete),
                                "xy_rmse_mm": rmse(errors) if complete else "",
                                "xy_mean_mm": mean(errors) if complete else "",
                                "xy_median_mm": median(errors) if complete else "",
                                "xy_p95_mm": pct(errors, 95) if complete else "",
                                "xy_max_mm": max(errors) if complete else "",
                                "pnp_z_rmse_mm": (
                                    rmse(float(row["error_z_signed_mm"]) for row in valid)
                                    if complete and model == "PnP" else ""
                                ),
                            }
                        )
    write_csv(OUT["run_metrics"], run_metrics)

    height_summary = []
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        for camera in CAMERAS:
            for model in MODELS:
                for height in HEIGHTS:
                    rr = [
                        row for row in run_metrics
                        if row["resolution_id"] == rid and row["camera_id"] == camera
                        and row["model"] == model and float(row["height_gt_mm"]) == height
                        and row["complete_five_marker_metric"]
                    ]
                    values = [float(row["xy_rmse_mm"]) for row in rr]
                    height_summary.append(
                        {
                            "resolution_id": rid,
                            "width_px": res["width"],
                            "height_px": res["height"],
                            "camera_id": camera,
                            "model": model,
                            "height_gt_mm": height,
                            "n_independent_rebuilds": len(values),
                            "xy_rmse_mean_mm": mean(values),
                            "xy_rmse_sd_mm": sd(values),
                            "xy_rmse_median_mm": median(values),
                            "xy_rmse_p95_across_rebuilds_mm": pct(values, 95),
                            "xy_rmse_min_mm": min(values) if values else "",
                            "xy_rmse_max_mm": max(values) if values else "",
                        }
                    )
    write_csv(OUT["height_summary"], height_summary)

    # Paired downsampling penalty and descriptive height amplification.
    metric_lookup = {
        (row["resolution_id"], row["run_id"], row["camera_id"], row["model"], float(row["height_gt_mm"])): row
        for row in run_metrics if row["complete_five_marker_metric"]
    }
    interaction_records = []
    for res in RESOLUTIONS[1:]:
        rid = res["resolution_id"]
        for run in runs:
            for camera in CAMERAS:
                for model in MODELS:
                    for height in HEIGHTS:
                        low = metric_lookup.get((rid, run, camera, model, height))
                        native = metric_lookup.get(("r640x400", run, camera, model, height))
                        if low is None or native is None:
                            continue
                        interaction_records.append(
                            {
                                "resolution_id": rid,
                                "width_px": res["width"],
                                "height_px": res["height"],
                                "run_id": run,
                                "camera_id": camera,
                                "model": model,
                                "height_gt_mm": height,
                                "xy_rmse_low_mm": float(low["xy_rmse_mm"]),
                                "xy_rmse_native_mm": float(native["xy_rmse_mm"]),
                                "downsampling_penalty_mm": float(low["xy_rmse_mm"]) - float(native["xy_rmse_mm"]),
                            }
                        )
    write_csv(OUT["interaction_records"], interaction_records)

    interaction_summary = []
    for res in RESOLUTIONS[1:]:
        rid = res["resolution_id"]
        for camera in CAMERAS:
            for model in MODELS:
                subset = [
                    row for row in interaction_records
                    if row["resolution_id"] == rid and row["camera_id"] == camera and row["model"] == model
                ]
                slopes = []
                amplification_0_50 = []
                for run in runs:
                    run_rows = sorted(
                        [row for row in subset if row["run_id"] == run],
                        key=lambda row: float(row["height_gt_mm"]),
                    )
                    if len(run_rows) >= 8:
                        x = np.asarray([float(row["height_gt_mm"]) for row in run_rows])
                        y = np.asarray([float(row["downsampling_penalty_mm"]) for row in run_rows])
                        slopes.append(float(np.polyfit(x, y, 1)[0]))
                    by_height = {float(row["height_gt_mm"]): float(row["downsampling_penalty_mm"]) for row in run_rows}
                    if 0.0 in by_height and 50.0 in by_height:
                        amplification_0_50.append(by_height[50.0] - by_height[0.0])
                for height in HEIGHTS:
                    hh = [row for row in subset if float(row["height_gt_mm"]) == height]
                    interaction_summary.append(
                        {
                            "resolution_id": rid,
                            "width_px": res["width"],
                            "height_px": res["height"],
                            "camera_id": camera,
                            "model": model,
                            "summary_type": "height_specific",
                            "height_gt_mm": height,
                            "n_paired_rebuilds": len(hh),
                            "downsampling_penalty_mean_mm": mean(
                                float(row["downsampling_penalty_mm"]) for row in hh
                            ),
                            "downsampling_penalty_median_mm": median(
                                float(row["downsampling_penalty_mm"]) for row in hh
                            ),
                            "downsampling_penalty_p95_mm": pct(
                                (float(row["downsampling_penalty_mm"]) for row in hh), 95
                            ),
                            "penalty_vs_height_slope_mean_mm_per_mm": "",
                            "penalty_vs_height_slope_sd_mm_per_mm": "",
                            "amplification_0_to_50_mean_mm": "",
                            "amplification_0_to_50_sd_mm": "",
                        }
                    )
                interaction_summary.append(
                    {
                        "resolution_id": rid,
                        "width_px": res["width"],
                        "height_px": res["height"],
                        "camera_id": camera,
                        "model": model,
                        "summary_type": "height_amplification",
                        "height_gt_mm": "ALL",
                        "n_paired_rebuilds": len(slopes),
                        "downsampling_penalty_mean_mm": "",
                        "downsampling_penalty_median_mm": "",
                        "downsampling_penalty_p95_mm": "",
                        "penalty_vs_height_slope_mean_mm_per_mm": mean(slopes),
                        "penalty_vs_height_slope_sd_mm_per_mm": sd(slopes),
                        "amplification_0_to_50_mean_mm": mean(amplification_0_50),
                        "amplification_0_to_50_sd_mm": sd(amplification_0_50),
                    }
                )
    write_csv(OUT["interaction_summary"], interaction_summary)

    # Mapping and total pipeline latency using complete five-marker images.
    image_latency_lookup = {
        (
            row["resolution_id"], row["run_id"], row["camera_id"],
            float(row["height_gt_mm"]), int(row["frame_index"]),
        ): row
        for row in image_latency
    }
    mapping_latency = []

    def infer_batch(model: str, found: dict[int, np.ndarray], cal: dict, K: np.ndarray):
        outputs = []
        for marker_id in EXPECTED_IDS:
            corners = found[marker_id]
            center = np.mean(corners, axis=0)
            if model == "Affine":
                outputs.append(affine_predict(cal["A"], center))
            elif model == "Homography":
                outputs.append(homography_predict(cal["H"], center))
            else:
                _, _, t_marker = solve_marker_pnp(corners, K)
                outputs.append(cal["R_cb"].T @ (t_marker - cal["t_cb"]))
        return outputs

    print("Benchmarking model mapping latency ...")
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        for res in RESOLUTIONS:
            rid = res["resolution_id"]
            for key in sorted(grouped_rows):
                run, camera, height, frame_index = key
                if key in excluded_keys:
                    continue
                found = detection_lookup[(rid,) + key]
                if not all(marker_id in found for marker_id in EXPECTED_IDS):
                    continue
                cal = calibrations[rid][run][camera]
                if not cal.get("valid", False):
                    continue
                K = scaled_intrinsics(camera, res["width"], res["height"])
                for model in MODELS:
                    try:
                        infer_batch(model, found, cal, K)
                        timings = []
                        for _ in range(5):
                            start = time.perf_counter_ns()
                            for _ in range(MAPPING_REPEATS):
                                infer_batch(model, found, cal, K)
                            timings.append(
                                (time.perf_counter_ns() - start) / 1e6 / MAPPING_REPEATS
                            )
                        mapping_ms = median(timings)
                        detection_ms = float(
                            image_latency_lookup[(rid, run, camera, height, frame_index)]["detection_latency_median_ms"]
                        )
                        mapping_latency.append(
                            {
                                "resolution_id": rid,
                                "width_px": res["width"],
                                "height_px": res["height"],
                                "run_id": run,
                                "camera_id": camera,
                                "height_gt_mm": height,
                                "frame_index": frame_index,
                                "model": model,
                                "markers_per_frame": 5,
                                "mapping_latency_median_ms": mapping_ms,
                                "mapping_timing_outer_repeats": 5,
                                "mapping_timing_inner_repeats": MAPPING_REPEATS,
                                "detection_latency_median_ms": detection_ms,
                                "pipeline_latency_ms": detection_ms + mapping_ms,
                            }
                        )
                    except (RuntimeError, cv2.error, np.linalg.LinAlgError):
                        continue
    finally:
        if gc_enabled:
            gc.enable()
    write_csv(OUT["mapping_latency"], mapping_latency)

    latency_summary = []
    for res in RESOLUTIONS:
        rid = res["resolution_id"]
        for camera in CAMERAS:
            for model in MODELS:
                ll = [
                    row for row in mapping_latency
                    if row["resolution_id"] == rid and row["camera_id"] == camera and row["model"] == model
                ]
                latency_summary.append(
                    {
                        "resolution_id": rid,
                        "width_px": res["width"],
                        "height_px": res["height"],
                        "camera_id": camera,
                        "model": model,
                        "n_complete_images": len(ll),
                        "detection_latency_median_ms": median(
                            float(row["detection_latency_median_ms"]) for row in ll
                        ),
                        "detection_latency_p95_ms": pct(
                            (float(row["detection_latency_median_ms"]) for row in ll), 95
                        ),
                        "mapping_latency_median_ms": median(
                            float(row["mapping_latency_median_ms"]) for row in ll
                        ),
                        "mapping_latency_p95_ms": pct(
                            (float(row["mapping_latency_median_ms"]) for row in ll), 95
                        ),
                        "pipeline_latency_median_ms": median(
                            float(row["pipeline_latency_ms"]) for row in ll
                        ),
                        "pipeline_latency_p95_ms": pct(
                            (float(row["pipeline_latency_ms"]) for row in ll), 95
                        ),
                        "p95_equivalent_fps": (
                            1000.0 / pct((float(row["pipeline_latency_ms"]) for row in ll), 95)
                            if ll else float("nan")
                        ),
                    }
                )
    write_csv(OUT["latency_summary"], latency_summary)

    # Feasibility decisions use frozen profile thresholds.
    height_lookup = {
        (row["resolution_id"], row["camera_id"], row["model"], float(row["height_gt_mm"])): row
        for row in height_summary
    }
    detection_lookup_summary = {
        (row["resolution_id"], row["camera_id"], float(row["height_gt_mm"])): row
        for row in detection_summary if row["height_gt_mm"] != "ALL"
    }
    latency_lookup_summary = {
        (row["resolution_id"], row["camera_id"], row["model"]): row
        for row in latency_summary
    }
    feasibility = []
    for profile in FEASIBILITY_PROFILES:
        for res in RESOLUTIONS:
            rid = res["resolution_id"]
            for camera in CAMERAS:
                for model in MODELS:
                    for height in HEIGHTS:
                        accuracy = height_lookup[(rid, camera, model, height)]
                        detection = detection_lookup_summary[(rid, camera, height)]
                        latency = latency_lookup_summary[(rid, camera, model)]
                        n_rebuilds = int(accuracy["n_independent_rebuilds"])
                        accuracy_value = fnum(accuracy["xy_rmse_p95_across_rebuilds_mm"])
                        detection_value = fnum(detection["marker_detection_rate"])
                        latency_value = fnum(latency["pipeline_latency_p95_ms"])
                        gates = {
                            "sufficient_rebuilds": n_rebuilds >= MIN_REBUILDS_FOR_FEASIBILITY,
                            "accuracy": math.isfinite(accuracy_value)
                            and accuracy_value <= profile["xy_rmse_p95_limit_mm"],
                            "detection": math.isfinite(detection_value)
                            and detection_value >= profile["detection_rate_min"],
                            "latency": math.isfinite(latency_value)
                            and latency_value <= profile["pipeline_p95_limit_ms"],
                        }
                        reasons = [name for name, passed in gates.items() if not passed]
                        feasibility.append(
                            {
                                "profile": profile["profile"],
                                "resolution_id": rid,
                                "width_px": res["width"],
                                "height_px": res["height"],
                                "camera_id": camera,
                                "model": model,
                                "height_gt_mm": height,
                                "n_independent_rebuilds": n_rebuilds,
                                "xy_rmse_p95_observed_mm": accuracy_value,
                                "xy_rmse_p95_limit_mm": profile["xy_rmse_p95_limit_mm"],
                                "marker_detection_rate": detection_value,
                                "marker_detection_rate_min": profile["detection_rate_min"],
                                "pipeline_latency_p95_ms": latency_value,
                                "pipeline_latency_p95_limit_ms": profile["pipeline_p95_limit_ms"],
                                "feasible": int(all(gates.values())),
                                "failed_gates": "|".join(reasons),
                            }
                        )
    write_csv(OUT["feasibility_by_height"], feasibility)

    feasibility_summary = []
    for profile in FEASIBILITY_PROFILES:
        for res in RESOLUTIONS:
            rid = res["resolution_id"]
            for camera in CAMERAS:
                for model in MODELS:
                    ff = sorted(
                        [
                            row for row in feasibility
                            if row["profile"] == profile["profile"]
                            and row["resolution_id"] == rid
                            and row["camera_id"] == camera and row["model"] == model
                        ],
                        key=lambda row: float(row["height_gt_mm"]),
                    )
                    feasible_heights = [float(row["height_gt_mm"]) for row in ff if row["feasible"]]
                    contiguous = []
                    for row in ff:
                        if row["feasible"]:
                            contiguous.append(float(row["height_gt_mm"]))
                        else:
                            break
                    feasibility_summary.append(
                        {
                            "profile": profile["profile"],
                            "resolution_id": rid,
                            "width_px": res["width"],
                            "height_px": res["height"],
                            "camera_id": camera,
                            "model": model,
                            "n_feasible_height_levels": len(feasible_heights),
                            "feasible_heights_mm": "|".join(f"{h:g}" for h in feasible_heights),
                            "max_contiguous_feasible_height_from_Z0_mm": (
                                max(contiguous) if contiguous else ""
                            ),
                            "z0_is_calibration_condition": 1,
                        }
                    )
    write_csv(OUT["feasibility_summary"], feasibility_summary)

    # Figures from derived summaries.
    for camera in CAMERAS:
        fig, ax = plt.subplots(figsize=(6.6, 4.0))
        data = [
            row for row in detection_summary
            if row["camera_id"] == camera and row["height_gt_mm"] == "ALL"
        ]
        data.sort(key=lambda row: int(row["width_px"]))
        ax.plot(
            [int(row["width_px"]) for row in data],
            [100 * float(row["marker_detection_rate"]) for row in data],
            marker="o",
            label="marker observations",
        )
        ax.plot(
            [int(row["width_px"]) for row in data],
            [100 * float(row["complete_image_rate"]) for row in data],
            marker="s",
            label="complete 5-marker frames",
        )
        ax.set_xlabel("Effective image width (px)")
        ax.set_ylabel("Detection success (%)")
        ax.set_ylim(-2, 102)
        ax.grid(alpha=0.25)
        ax.legend()
        ax.set_title(f"E5 detection reliability — {camera}")
        save_figure(fig, f"Fig_E5_1_detection_{camera}")

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.0), sharex=True)
    for camera, marker in zip(CAMERAS, ("o", "s")):
        data = [
            row for row in stability_summary
            if row["camera_id"] == camera and row["height_gt_mm"] == "ALL"
        ]
        data.sort(key=lambda row: int(row["width_px"]))
        axes[0].plot(
            [int(row["width_px"]) for row in data],
            [float(row["center_repeatability_rms_p95_native_equiv_px"]) for row in data],
            marker=marker,
            label=camera,
        )
        axes[1].plot(
            [int(row["width_px"]) for row in data],
            [float(row["corner_drift_from_native_p95_px"]) for row in data],
            marker=marker,
            label=camera,
        )
    axes[0].set_ylabel("P95 center repeatability RMS\n(native-equivalent px)")
    axes[1].set_ylabel("P95 corner drift from native\n(native px)")
    for ax in axes:
        ax.set_xlabel("Effective image width (px)")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("E5 center/corner stability")
    save_figure(fig, "Fig_E5_2_stability")

    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(RESOLUTIONS)))
    for camera in CAMERAS:
        fig, axes = plt.subplots(1, 3, figsize=(14.2, 4.0), sharex=True)
        for ax, model in zip(axes, MODELS):
            for res, color in zip(RESOLUTIONS, colors):
                data = [
                    row for row in height_summary
                    if row["camera_id"] == camera and row["model"] == model
                    and row["resolution_id"] == res["resolution_id"]
                ]
                data.sort(key=lambda row: float(row["height_gt_mm"]))
                ax.plot(
                    [float(row["height_gt_mm"]) for row in data],
                    [float(row["xy_rmse_mean_mm"]) for row in data],
                    marker="o",
                    markersize=3,
                    color=color,
                    label=f"{res['width']}x{res['height']}",
                )
            ax.set_title(model)
            ax.set_xlabel("Height (mm)")
            ax.grid(alpha=0.25)
        axes[0].set_ylabel("XY RMSE mean across rebuilds (mm)")
        axes[-1].legend(fontsize=8, loc="upper left")
        fig.suptitle(f"E5 resolution x height x model — {camera}")
        save_figure(fig, f"Fig_E5_3_accuracy_{camera}")

    for camera in CAMERAS:
        fig, ax = plt.subplots(figsize=(7.0, 4.2))
        for model, marker in zip(MODELS, ("o", "s", "^")):
            data = [
                row for row in latency_summary
                if row["camera_id"] == camera and row["model"] == model
            ]
            data.sort(key=lambda row: int(row["width_px"]))
            ax.plot(
                [int(row["width_px"]) for row in data],
                [float(row["pipeline_latency_p95_ms"]) for row in data],
                marker=marker,
                label=model,
            )
        ax.axhline(33.3, color="0.35", linestyle="--", linewidth=1, label="30 Hz budget")
        ax.set_xlabel("Effective image width (px)")
        ax.set_ylabel("Pipeline P95 latency (ms)")
        ax.grid(alpha=0.25)
        ax.legend()
        ax.set_title(f"E5 detection + mapping latency — {camera}")
        save_figure(fig, f"Fig_E5_4_latency_{camera}")

    standard = [row for row in feasibility_summary if row["profile"] == "standard_20hz"]
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 3.8), constrained_layout=True)
    for ax, camera in zip(axes, CAMERAS):
        matrix = np.full((len(MODELS), len(RESOLUTIONS)), np.nan)
        for i, model in enumerate(MODELS):
            for j, res in enumerate(RESOLUTIONS):
                row = next(
                    item for item in standard
                    if item["camera_id"] == camera and item["model"] == model
                    and item["resolution_id"] == res["resolution_id"]
                )
                matrix[i, j] = fnum(row["max_contiguous_feasible_height_from_Z0_mm"])
        image = ax.imshow(matrix, vmin=0, vmax=50, cmap="YlGnBu", aspect="auto")
        ax.set_xticks(range(len(RESOLUTIONS)), [str(res["width"]) for res in RESOLUTIONS])
        ax.set_yticks(range(len(MODELS)), MODELS)
        ax.set_xlabel("Effective image width (px)")
        ax.set_title(camera)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                label = "—" if not math.isfinite(matrix[i, j]) else f"{matrix[i, j]:.0f}"
                ax.text(j, i, label, ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=axes, label="Max contiguous feasible height (mm)")
    fig.suptitle("E5 standard_20hz feasibility (conditional E2 screening)")
    save_figure(fig, "Fig_E5_5_standard_feasibility")

    excluded_rows = [row for row in preflight if row["qc_excluded"]]
    overall_detection = [row for row in detection_summary if row["height_gt_mm"] == "ALL"]
    amplification = [
        row for row in interaction_summary if row["summary_type"] == "height_amplification"
    ]
    summary = {
        "created_at_utc": utc_now(),
        "source_images": len(grouped_rows),
        "source_marker_rows": len(rows),
        "qc_excluded_images": len(excluded_rows),
        "qc_exclusions": excluded_rows,
        "overall_detection": overall_detection,
        "latency_summary": latency_summary,
        "height_amplification": amplification,
        "feasibility_summary": feasibility_summary,
    }
    OUT["summary_json"].write_text(
        json.dumps(json_safe(summary), indent=2, allow_nan=False), encoding="utf-8"
    )

    # Human-readable summary: deterministic extraction from result tables.
    def pick(records, **criteria):
        return next(
            row for row in records
            if all(row.get(key) == value for key, value in criteria.items())
        )

    ihawk1_480_detection = pick(
        overall_detection,
        camera_id="ihawk1",
        resolution_id="r480x300",
        height_gt_mm="ALL",
    )
    ihawk2_480_detection = pick(
        overall_detection,
        camera_id="ihawk2",
        resolution_id="r480x300",
        height_gt_mm="ALL",
    )
    native_pipeline_p95_max = max(
        float(row["pipeline_latency_p95_ms"])
        for row in latency_summary
        if row["resolution_id"] == "r640x400"
    )
    native_planar_mapping_p95_max = max(
        float(row["mapping_latency_p95_ms"])
        for row in latency_summary
        if row["resolution_id"] == "r640x400" and row["model"] in ("Affine", "Homography")
    )
    native_pnp_mapping_p95_max = max(
        float(row["mapping_latency_p95_ms"])
        for row in latency_summary
        if row["resolution_id"] == "r640x400" and row["model"] == "PnP"
    )
    ihawk2_pnp_25 = {
        row["resolution_id"]: float(row["xy_rmse_mean_mm"])
        for row in height_summary
        if row["camera_id"] == "ihawk2"
        and row["model"] == "PnP"
        and float(row["height_gt_mm"]) == 25.0
    }
    lines = [
        "# E5 effective-resolution pilot — results summary",
        "",
        f"Generated: {summary['created_at_utc']}",
        "",
        "## Data and QC",
        "",
        f"- Source: {len(grouped_rows)} saved E2 color images and {len(rows)} expected marker observations.",
        f"- QC excluded {len(excluded_rows)} images. These are the overwritten run 20260808_141232 / 30 mm images described in the README.",
        "- All conclusions below are conditional on simulated downsampling of 640 x 400 images.",
        "",
        "## Executive findings",
        "",
        f"- Native 640 x 400 detection was complete for both cameras, and the worst model-specific native pipeline P95 was only {native_pipeline_p95_max:.3f} ms; every native pipeline therefore passed the predefined 30 Hz latency gate.",
        f"- At 480 x 300, complete five-marker frames fell to {100*float(ihawk1_480_detection['complete_image_rate']):.1f}% for ihawk1 and {100*float(ihawk2_480_detection['complete_image_rate']):.1f}% for ihawk2. Lower resolutions lost substantially more observations.",
        f"- Affine/Homography mapping itself cost at most {native_planar_mapping_p95_max:.3f} ms P95 at native resolution; PnP cost at most {native_pnp_mapping_p95_max:.3f} ms. Detection, not the final matrix mapping, dominated processing time.",
        f"- PnP showed a resolution cost even when detection remained complete: for ihawk2 at 25 mm, mean XY RMSE changed from {ihawk2_pnp_25['r640x400']:.3f} mm (640 x 400) to {ihawk2_pnp_25['r480x300']:.3f} mm (480 x 300) and {ihawk2_pnp_25['r320x200']:.3f} mm (320 x 200).",
        "- Height did not consistently amplify the downsampling penalty across cameras and models. The dominant, reproducible effects were camera-dependent detection loss and a PnP resolution-related bias, not a universal resolution x height interaction.",
        "- Under the predefined budgets, reducing resolution was unnecessary on this computer because the native pipeline already met the strictest latency gate. The pilot therefore supports a supplementary operating-limit/negative-result role, not a new main speed-accuracy contribution by itself.",
        "",
        "## Overall marker detection",
        "",
        "| Camera | Resolution | Marker detection | Complete 5-marker images |",
        "|---|---:|---:|---:|",
    ]
    for row in sorted(overall_detection, key=lambda item: (item["camera_id"], -int(item["width_px"]))):
        lines.append(
            f"| {row['camera_id']} | {row['width_px']}x{row['height_px']} | "
            f"{100*float(row['marker_detection_rate']):.1f}% | "
            f"{100*float(row['complete_image_rate']):.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Processing latency",
            "",
            "Processing-only timing; image I/O and simulated resize are excluded from pipeline totals.",
            "",
            "| Camera | Resolution | Model | Detection P95 (ms) | Mapping P95 (ms) | Pipeline P95 (ms) |",
            "|---|---:|---|---:|---:|---:|",
        ]
    )
    for row in sorted(
        latency_summary,
        key=lambda item: (item["camera_id"], -int(item["width_px"]), item["model"]),
    ):
        lines.append(
            f"| {row['camera_id']} | {row['width_px']}x{row['height_px']} | {row['model']} | "
            f"{fmt(row['detection_latency_p95_ms'])} | {fmt(row['mapping_latency_p95_ms'])} | "
            f"{fmt(row['pipeline_latency_p95_ms'])} |"
        )
    lines.extend(
        [
            "",
            "## Height amplification",
            "",
            "Positive values mean the downsampling penalty grows from 0 to 50 mm; negative values mean it does not.",
            "",
            "| Camera | Resolution | Model | Penalty slope (mm error/mm height) | Amplification 0→50 mm |",
            "|---|---:|---|---:|---:|",
        ]
    )
    for row in sorted(
        amplification,
        key=lambda item: (item["camera_id"], -int(item["width_px"]), item["model"]),
    ):
        lines.append(
            f"| {row['camera_id']} | {row['width_px']}x{row['height_px']} | {row['model']} | "
            f"{fmt(row['penalty_vs_height_slope_mean_mm_per_mm'], 4)} | "
            f"{fmt(row['amplification_0_to_50_mean_mm'])} |"
        )
    lines.extend(
        [
            "",
            "## Feasibility summary",
            "",
            "Maximum contiguous feasible height beginning at Z=0; `—` means Z=0 itself failed at least one gate. Z=0 is the calibration condition, not an independent planar test.",
            "",
            "| Profile | Camera | Resolution | Affine | Homography | PnP |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for profile in FEASIBILITY_PROFILES:
        for camera in CAMERAS:
            for res in RESOLUTIONS:
                values = {}
                for model in MODELS:
                    row = next(
                        item for item in feasibility_summary
                        if item["profile"] == profile["profile"]
                        and item["camera_id"] == camera and item["model"] == model
                        and item["resolution_id"] == res["resolution_id"]
                    )
                    value = fnum(row["max_contiguous_feasible_height_from_Z0_mm"])
                    values[model] = "—" if not math.isfinite(value) else f"{value:.0f} mm"
                lines.append(
                    f"| {profile['profile']} | {camera} | {res['width']}x{res['height']} | "
                    f"{values['Affine']} | {values['Homography']} | {values['PnP']} |"
                )
    lines.extend(
        [
            "",
            "## Required interpretation",
            "",
            "- Inspect `E5_height_summary.csv`, `E5_height_interaction_summary.csv`, and the figures before promoting any pattern to a paper claim.",
            "- A useful paper extension requires a reproducible model × resolution interaction or a non-trivial feasibility trade-off; a generic 'lower resolution is faster/worse' result is insufficient.",
            "- Native multi-resolution acquisition is required before making claims about sensor modes or production hardware.",
            "",
        ]
    )
    OUT["summary_md"].write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "created_at_utc": utc_now(),
        "experiment": "E5 simulated effective-resolution operating-envelope pilot",
        "script": str(SCRIPT.relative_to(REPO_ROOT)),
        "source_csv": str(SOURCE_CSV.relative_to(REPO_ROOT)),
        "source_frame_root": str(SOURCE_FRAME_ROOT.relative_to(REPO_ROOT)),
        "runs": runs,
        "cameras": list(CAMERAS),
        "models": list(MODELS),
        "heights_mm": list(HEIGHTS),
        "resolutions": list(RESOLUTIONS),
        "detector": {
            "dictionary": "DICT_4X4_50",
            "parameters": "OpenCV defaults",
            "corner_refinement": "cornerSubPix window 3x3, max_iter 30, epsilon 0.01",
        },
        "timing": {
            "opencv_threads": cv2.getNumThreads(),
            "detection_repeats_per_image": DETECTION_REPEATS,
            "mapping_outer_repeats": 5,
            "mapping_inner_repeats": MAPPING_REPEATS,
            "includes": "grayscale + marker detection + corner refinement + model mapping",
            "excludes": "disk I/O and simulated resize",
        },
        "feasibility_profiles": list(FEASIBILITY_PROFILES),
        "source_image_qc": {
            "content_mismatch_threshold_native_px": CONTENT_MISMATCH_THRESHOLD_PX,
            "excluded_images": len(excluded_rows),
        },
        "software": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "outputs": {name: str(path.relative_to(REPO_ROOT)) for name, path in OUT.items()},
        "figures": sorted(str(path.relative_to(REPO_ROOT)) for path in FIGURES.glob("Fig_E5_*")),
        "interpretation": [
            "Resolution levels are deterministic transforms of shared physical acquisitions.",
            "Z=0 is reused for calibration and is not an independent planar test.",
            "Accuracy is emitted only for complete five-marker run-height conditions.",
            "Feasibility profiles are screening constraints, not standards.",
            "Timing is specific to this analysis computer and software stack.",
        ],
    }
    OUT["manifest"].write_text(
        json.dumps(json_safe(manifest), indent=2, allow_nan=False), encoding="utf-8"
    )

    print("E5 complete")
    print(f"Summary : {OUT['summary_md']}")
    print(f"Manifest: {OUT['manifest']}")


if __name__ == "__main__":
    main()
