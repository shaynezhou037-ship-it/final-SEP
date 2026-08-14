#!/usr/bin/env python3
"""E6 single/dual-camera fusion, stereo, and view-geometry analysis."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import math
import platform

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np


SCRIPT = Path(__file__).resolve()
EXP_ROOT = SCRIPT.parents[1]
REPO_ROOT = SCRIPT.parents[3]
RESULTS = EXP_ROOT / "results"
FIGURES = EXP_ROOT / "figures"
RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

PREDICTIONS_CSV = REPO_ROOT / "E2" / "E2_rebuilt" / "model_comparison" / "E2_predictions.csv"
CLEAN_CSV = REPO_ROOT / "E2" / "E2_rebuilt" / "E2_all_5runs_REBUILT_clean.csv"
CALIBRATIONS_JSON = REPO_ROOT / "E2" / "E2_rebuilt" / "model_comparison" / "E2_calibration_models.json"

CAMERAS = ("ihawk1", "ihawk2")
MODELS = ("Affine", "Homography", "PnP")
FUSION_SOURCES = (
    "ihawk1",
    "ihawk2",
    "EqualFusion",
    "LOOWeightedFusion",
    "LOOWeightedGated",
)
HEIGHTS = tuple(float(x) for x in range(0, 51, 5))
MARKER_IDS = tuple(range(5))

K = {
    "ihawk1": np.array(
        [[401.77020263671875, 0.0, 322.1313781738281],
         [0.0, 401.9191589355469, 202.54229736328125],
         [0.0, 0.0, 1.0]], dtype=np.float64
    ),
    "ihawk2": np.array(
        [[391.3234558105469, 0.0, 320.85333251953125],
         [0.0, 391.3234558105469, 202.9705047607422],
         [0.0, 0.0, 1.0]], dtype=np.float64
    ),
}

OUT = {
    "weight_audit": RESULTS / "E6_leave_one_rebuild_weight_audit.csv",
    "fusion_predictions": RESULTS / "E6_fusion_predictions.csv",
    "fusion_run_metrics": RESULTS / "E6_fusion_run_height_metrics.csv",
    "fusion_height_summary": RESULTS / "E6_fusion_height_summary.csv",
    "fusion_gain_summary": RESULTS / "E6_fusion_gain_summary.csv",
    "stereo_predictions": RESULTS / "E6_stereo_predictions.csv",
    "stereo_run_metrics": RESULTS / "E6_stereo_run_height_metrics.csv",
    "stereo_height_summary": RESULTS / "E6_stereo_height_summary.csv",
    "camera_geometry": RESULTS / "E6_camera_geometry.csv",
    "pair_geometry": RESULTS / "E6_pair_geometry.csv",
    "angle_associations": RESULTS / "E6_angle_error_associations.csv",
    "angle_identifiability_json": RESULTS / "E6_angle_identifiability_audit.json",
    "angle_identifiability_md": RESULTS / "E6_ANGLE_IDENTIFIABILITY_AUDIT.md",
    "summary": RESULTS / "E6_RESULTS_SUMMARY.md",
    "summary_json": RESULTS / "E6_summary.json",
    "manifest": RESULTS / "E6_manifest.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, records: list[dict]) -> None:
    if not records:
        raise RuntimeError(f"Refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


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


def pct(values, q: float) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.percentile(a, q)) if len(a) else float("nan")


def rmse(values) -> float:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.sqrt(np.mean(a * a))) if len(a) else float("nan")


def fmt(value, digits=3) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{x:.{digits}f}" if math.isfinite(x) else "NA"


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def rankdata(values: list[float]) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0 + 1.0
        start = end
    return ranks


def correlation(x, y) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    pearson = float(np.corrcoef(x, y)[0, 1])
    spearman = float(np.corrcoef(rankdata(x.tolist()), rankdata(y.tolist()))[0, 1])
    return pearson, spearman


def polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def angle_deg(a: np.ndarray, b: np.ndarray, unsigned=False) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    if unsigned:
        cosine = abs(cosine)
    return math.degrees(math.acos(np.clip(cosine, -1.0, 1.0)))


def save_figure(fig, stem: str) -> None:
    fig.savefig(FIGURES / f"{stem}.png", dpi=240, bbox_inches="tight")
    fig.savefig(FIGURES / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    print("=" * 84)
    print("E6 — SINGLE/DUAL-CAMERA INFORMATION AND VIEW GEOMETRY")
    print("=" * 84)
    predictions = read_csv(PREDICTIONS_CSV)
    clean = read_csv(CLEAN_CSV)
    calibrations = json.loads(CALIBRATIONS_JSON.read_text(encoding="utf-8"))
    runs = sorted(calibrations)
    if len(predictions) != 1650 or len(clean) != 1650 or len(runs) != 5:
        raise RuntimeError("E2 input cardinality mismatch")
    if any(row["pair_sync_valid"] != "1" for row in clean):
        raise RuntimeError("E6 requires every retained E2 pair to pass the sync gate")

    pred_index = {
        (
            row["run_id"], float(row["height_gt_mm"]), int(row["marker_id"]),
            row["model"], row["camera_id"],
        ): row
        for row in predictions
    }

    # Leave-one-rebuild-out weights and disagreement gates from other runs at Z=0.
    weight_configs = {}
    weight_audit = []
    for held_out_run in runs:
        training_runs = [run for run in runs if run != held_out_run]
        weight_configs[held_out_run] = {}
        for model in MODELS:
            mse = {}
            disagreements = []
            for camera in CAMERAS:
                squared = []
                for run in training_runs:
                    for marker_id in MARKER_IDS:
                        row = pred_index[(run, 0.0, marker_id, model, camera)]
                        squared.append(float(row["error_xy_mm"]) ** 2)
                mse[camera] = mean(squared)
            for run in training_runs:
                for marker_id in MARKER_IDS:
                    p1 = pred_index[(run, 0.0, marker_id, model, "ihawk1")]
                    p2 = pred_index[(run, 0.0, marker_id, model, "ihawk2")]
                    xy1 = np.array([float(p1["pred_x_mm"]), float(p1["pred_y_mm"])])
                    xy2 = np.array([float(p2["pred_x_mm"]), float(p2["pred_y_mm"])])
                    disagreements.append(float(np.linalg.norm(xy1 - xy2)))
            inv1 = 1.0 / max(mse["ihawk1"], 1e-12)
            inv2 = 1.0 / max(mse["ihawk2"], 1e-12)
            weight1 = inv1 / (inv1 + inv2)
            weight2 = 1.0 - weight1
            gate = pct(disagreements, 95)
            config = {
                "weight_ihawk1": weight1,
                "weight_ihawk2": weight2,
                "disagreement_gate_mm": gate,
            }
            weight_configs[held_out_run][model] = config
            weight_audit.append(
                {
                    "held_out_run": held_out_run,
                    "model": model,
                    "training_runs": "|".join(training_runs),
                    "training_z0_mse_ihawk1_mm2": mse["ihawk1"],
                    "training_z0_mse_ihawk2_mm2": mse["ihawk2"],
                    "weight_ihawk1": weight1,
                    "weight_ihawk2": weight2,
                    "training_z0_disagreement_p95_gate_mm": gate,
                    "n_training_marker_pairs": len(disagreements),
                }
            )
    write_csv(OUT["weight_audit"], weight_audit)

    fusion_predictions = []
    for run in runs:
        for height in HEIGHTS:
            for marker_id in MARKER_IDS:
                for model in MODELS:
                    row1 = pred_index[(run, height, marker_id, model, "ihawk1")]
                    row2 = pred_index[(run, height, marker_id, model, "ihawk2")]
                    p1 = np.array([float(row1["pred_x_mm"]), float(row1["pred_y_mm"])])
                    p2 = np.array([float(row2["pred_x_mm"]), float(row2["pred_y_mm"])])
                    gt = np.array([float(row1["gt_x_mm"]), float(row1["gt_y_mm"])])
                    config = weight_configs[run][model]
                    disagreement = float(np.linalg.norm(p1 - p2))
                    weighted = config["weight_ihawk1"] * p1 + config["weight_ihawk2"] * p2
                    source_predictions = {
                        "ihawk1": (p1, True),
                        "ihawk2": (p2, True),
                        "EqualFusion": ((p1 + p2) / 2.0, True),
                        "LOOWeightedFusion": (weighted, True),
                        "LOOWeightedGated": (
                            weighted,
                            disagreement <= config["disagreement_gate_mm"],
                        ),
                    }
                    for source, (estimate, accepted) in source_predictions.items():
                        fusion_predictions.append(
                            {
                                "run_id": run,
                                "height_gt_mm": height,
                                "marker_id": marker_id,
                                "board_position": row1["board_position"],
                                "model": model,
                                "source": source,
                                "weight_ihawk1": config["weight_ihawk1"] if "Fusion" in source or "Gated" in source else "",
                                "weight_ihawk2": config["weight_ihawk2"] if "Fusion" in source or "Gated" in source else "",
                                "inter_camera_disagreement_mm": disagreement,
                                "disagreement_gate_mm": config["disagreement_gate_mm"] if source == "LOOWeightedGated" else "",
                                "accepted": int(accepted),
                                "pred_x_mm": float(estimate[0]) if accepted else "",
                                "pred_y_mm": float(estimate[1]) if accepted else "",
                                "gt_x_mm": float(gt[0]),
                                "gt_y_mm": float(gt[1]),
                                "error_xy_mm": float(np.linalg.norm(estimate - gt)) if accepted else "",
                            }
                        )
    write_csv(OUT["fusion_predictions"], fusion_predictions)

    fusion_run_metrics = []
    for run in runs:
        for height in HEIGHTS:
            for model in MODELS:
                for source in FUSION_SOURCES:
                    rr = [
                        row for row in fusion_predictions
                        if row["run_id"] == run and float(row["height_gt_mm"]) == height
                        and row["model"] == model and row["source"] == source
                    ]
                    accepted = [row for row in rr if row["accepted"]]
                    errors = [float(row["error_xy_mm"]) for row in accepted]
                    fusion_run_metrics.append(
                        {
                            "run_id": run,
                            "height_gt_mm": height,
                            "model": model,
                            "source": source,
                            "n_expected_markers": 5,
                            "n_accepted_markers": len(accepted),
                            "coverage": len(accepted) / 5.0,
                            "complete_five_marker_metric": int(len(accepted) == 5),
                            "xy_rmse_mm": rmse(errors),
                            "xy_mean_mm": mean(errors),
                            "xy_p95_mm": pct(errors, 95),
                            "inter_camera_disagreement_mean_mm": mean(
                                float(row["inter_camera_disagreement_mm"]) for row in rr
                            ),
                        }
                    )
    write_csv(OUT["fusion_run_metrics"], fusion_run_metrics)

    fusion_height_summary = []
    for height in HEIGHTS:
        for model in MODELS:
            for source in FUSION_SOURCES:
                rr = [
                    row for row in fusion_run_metrics
                    if float(row["height_gt_mm"]) == height
                    and row["model"] == model and row["source"] == source
                ]
                complete = [row for row in rr if row["complete_five_marker_metric"]]
                fusion_height_summary.append(
                    {
                        "height_gt_mm": height,
                        "model": model,
                        "source": source,
                        "n_independent_rebuilds": len(rr),
                        "n_complete_rebuilds": len(complete),
                        "mean_marker_coverage": mean(float(row["coverage"]) for row in rr),
                        "xy_rmse_mean_mm": mean(float(row["xy_rmse_mm"]) for row in rr),
                        "xy_rmse_sd_mm": sd(float(row["xy_rmse_mm"]) for row in rr),
                        "xy_rmse_p95_across_rebuilds_mm": pct(
                            (float(row["xy_rmse_mm"]) for row in rr), 95
                        ),
                        "inter_camera_disagreement_mean_mm": mean(
                            float(row["inter_camera_disagreement_mean_mm"]) for row in rr
                        ),
                        "conditional_error_warning": int(source == "LOOWeightedGated"),
                    }
                )
    write_csv(OUT["fusion_height_summary"], fusion_height_summary)

    fusion_gain_summary = []
    for height in HEIGHTS:
        for model in MODELS:
            camera_rows = {
                source: next(
                    row for row in fusion_height_summary
                    if float(row["height_gt_mm"]) == height
                    and row["model"] == model and row["source"] == source
                )
                for source in ("ihawk1", "ihawk2")
            }
            best_source = min(camera_rows, key=lambda s: float(camera_rows[s]["xy_rmse_mean_mm"]))
            best_error = float(camera_rows[best_source]["xy_rmse_mean_mm"])
            for source in ("EqualFusion", "LOOWeightedFusion", "LOOWeightedGated"):
                row = next(
                    item for item in fusion_height_summary
                    if float(item["height_gt_mm"]) == height
                    and item["model"] == model and item["source"] == source
                )
                error = float(row["xy_rmse_mean_mm"])
                fusion_gain_summary.append(
                    {
                        "height_gt_mm": height,
                        "model": model,
                        "fusion_source": source,
                        "best_single_camera": best_source,
                        "best_single_xy_rmse_mean_mm": best_error,
                        "fusion_xy_rmse_mean_mm": error,
                        "fusion_minus_best_single_mm": error - best_error,
                        "relative_change_vs_best_single_percent": 100.0 * (error - best_error) / best_error,
                        "mean_marker_coverage": float(row["mean_marker_coverage"]),
                    }
                )
    write_csv(OUT["fusion_gain_summary"], fusion_gain_summary)

    # True two-view triangulation from paired frame centers.
    clean_index = {
        (
            row["run_id"], float(row["height_gt_mm"]), int(float(row["marker_id"])),
            int(float(row["frame_index"])), row["camera_id"],
        ): row
        for row in clean
    }
    projection = {}
    camera_centers = {}
    for run in runs:
        projection[run] = {}
        camera_centers[run] = {}
        for camera in CAMERAS:
            cal = calibrations[run][camera]
            R = np.asarray(cal["R_camera_from_board"], dtype=float)
            t = np.asarray(cal["t_camera_from_board_mm"], dtype=float).reshape(3, 1)
            projection[run][camera] = K[camera] @ np.hstack([R, t])
            camera_centers[run][camera] = -R.T @ t.reshape(3)

    stereo_predictions = []
    pair_deltas = []
    for run in runs:
        for height in HEIGHTS:
            for marker_id in MARKER_IDS:
                frame_points = []
                frame_pair_deltas = []
                for frame_index in (1, 2, 3):
                    row1 = clean_index[(run, height, marker_id, frame_index, "ihawk1")]
                    row2 = clean_index[(run, height, marker_id, frame_index, "ihawk2")]
                    uv1 = np.array(
                        [[float(row1["center_u_undist_px"])], [float(row1["center_v_undist_px"])]]
                    )
                    uv2 = np.array(
                        [[float(row2["center_u_undist_px"])], [float(row2["center_v_undist_px"])]]
                    )
                    homogeneous = cv2.triangulatePoints(
                        projection[run]["ihawk1"], projection[run]["ihawk2"], uv1, uv2
                    )
                    point = (homogeneous[:3] / homogeneous[3]).reshape(3)
                    frame_points.append(point)
                    frame_pair_deltas.append(float(row1["pair_delta_ms"]))
                    pair_deltas.append(float(row1["pair_delta_ms"]))
                estimate = np.mean(frame_points, axis=0)
                truth_row = clean_index[(run, height, marker_id, 1, "ihawk1")]
                truth = np.array(
                    [float(truth_row["marker_gt_x_mm"]), float(truth_row["marker_gt_y_mm"]), height]
                )
                delta = estimate - truth
                stereo_predictions.append(
                    {
                        "run_id": run,
                        "height_gt_mm": height,
                        "marker_id": marker_id,
                        "board_position": truth_row["board_position"],
                        "n_paired_frames": 3,
                        "pair_delta_mean_ms": mean(frame_pair_deltas),
                        "pred_x_mm": float(estimate[0]),
                        "pred_y_mm": float(estimate[1]),
                        "pred_z_mm": float(estimate[2]),
                        "gt_x_mm": float(truth[0]),
                        "gt_y_mm": float(truth[1]),
                        "gt_z_mm": float(truth[2]),
                        "error_xy_mm": float(np.linalg.norm(delta[:2])),
                        "error_z_signed_mm": float(delta[2]),
                        "error_3d_mm": float(np.linalg.norm(delta)),
                    }
                )
    write_csv(OUT["stereo_predictions"], stereo_predictions)

    stereo_run_metrics = []
    for run in runs:
        for height in HEIGHTS:
            rr = [
                row for row in stereo_predictions
                if row["run_id"] == run and float(row["height_gt_mm"]) == height
            ]
            stereo_run_metrics.append(
                {
                    "run_id": run,
                    "height_gt_mm": height,
                    "n_markers": len(rr),
                    "xy_rmse_mm": rmse(float(row["error_xy_mm"]) for row in rr),
                    "z_rmse_mm": rmse(float(row["error_z_signed_mm"]) for row in rr),
                    "error3d_rmse_mm": rmse(float(row["error_3d_mm"]) for row in rr),
                }
            )
    write_csv(OUT["stereo_run_metrics"], stereo_run_metrics)

    stereo_height_summary = []
    for height in HEIGHTS:
        rr = [row for row in stereo_run_metrics if float(row["height_gt_mm"]) == height]
        stereo_height_summary.append(
            {
                "height_gt_mm": height,
                "n_independent_rebuilds": len(rr),
                "xy_rmse_mean_mm": mean(float(row["xy_rmse_mm"]) for row in rr),
                "xy_rmse_sd_mm": sd(float(row["xy_rmse_mm"]) for row in rr),
                "xy_rmse_p95_mm": pct((float(row["xy_rmse_mm"]) for row in rr), 95),
                "z_rmse_mean_mm": mean(float(row["z_rmse_mm"]) for row in rr),
                "z_rmse_sd_mm": sd(float(row["z_rmse_mm"]) for row in rr),
                "error3d_rmse_mean_mm": mean(float(row["error3d_rmse_mm"]) for row in rr),
                "error3d_rmse_sd_mm": sd(float(row["error3d_rmse_mm"]) for row in rr),
            }
        )
    write_csv(OUT["stereo_height_summary"], stereo_height_summary)

    # Camera and pair geometry diagnostics.
    camera_geometry = []
    for run in runs:
        for camera in CAMERAS:
            cal = calibrations[run][camera]
            R = np.asarray(cal["R_camera_from_board"], dtype=float)
            t = np.asarray(cal["t_camera_from_board_mm"], dtype=float)
            center = -R.T @ t
            optical_axis_board = R.T @ np.array([0.0, 0.0, 1.0])
            los_to_camera = center
            z0_rows = [
                row for row in clean
                if row["run_id"] == run and row["camera_id"] == camera
                and float(row["height_gt_mm"]) == 0.0
            ]
            areas = []
            sides = []
            for row in z0_rows:
                corners = np.array(
                    [[float(row[f"corner{j}_u_undist_px"]), float(row[f"corner{j}_v_undist_px"])] for j in range(4)]
                )
                areas.append(polygon_area(corners))
                sides.extend(
                    np.linalg.norm(corners[(j + 1) % 4] - corners[j]) for j in range(4)
                )
            camera_geometry.append(
                {
                    "run_id": run,
                    "camera_id": camera,
                    "camera_center_x_board_mm": float(center[0]),
                    "camera_center_y_board_mm": float(center[1]),
                    "camera_center_z_board_mm": float(center[2]),
                    "distance_to_board_center_mm": float(np.linalg.norm(center)),
                    "camera_center_azimuth_deg": math.degrees(math.atan2(center[1], center[0])),
                    "optical_axis_tilt_to_board_normal_deg": angle_deg(
                        optical_axis_board, np.array([0.0, 0.0, 1.0]), unsigned=True
                    ),
                    "line_of_sight_incidence_to_board_normal_deg": angle_deg(
                        los_to_camera, np.array([0.0, 0.0, 1.0]), unsigned=True
                    ),
                    "median_z0_marker_side_px": median(sides),
                    "median_z0_marker_footprint_px2": median(areas),
                    "board_pnp_reprojection_rmse_px": float(cal["board_pnp_reprojection_rmse_px"]),
                }
            )
    write_csv(OUT["camera_geometry"], camera_geometry)

    pair_geometry = []
    for run in runs:
        c1 = camera_centers[run]["ihawk1"]
        c2 = camera_centers[run]["ihawk2"]
        baseline = float(np.linalg.norm(c1 - c2))
        for height in HEIGHTS:
            target = np.array([0.0, 0.0, height])
            ray_angle = angle_deg(c1 - target, c2 - target)
            pair_geometry.append(
                {
                    "run_id": run,
                    "height_gt_mm": height,
                    "camera_baseline_mm": baseline,
                    "central_target_ray_convergence_deg": ray_angle,
                    "pair_delta_median_ms_all_markers_frames": median(pair_deltas),
                    "pair_delta_p95_ms_all_markers_frames": pct(pair_deltas, 95),
                    "pair_delta_max_ms_all_markers_frames": max(pair_deltas),
                }
            )
    write_csv(OUT["pair_geometry"], pair_geometry)

    geometry_index = {(row["run_id"], row["camera_id"]): row for row in camera_geometry}
    single_metric_index = {
        (row["run_id"], row["camera_id"], float(row["height_gt_mm"])): float(row["xy_rmse_mm"])
        for row in read_csv(
            REPO_ROOT / "E2" / "E2_rebuilt" / "model_comparison" / "E2_run_height_metrics.csv"
        )
        if row["model"] == "PnP"
    }
    variables = (
        "distance_to_board_center_mm",
        "optical_axis_tilt_to_board_normal_deg",
        "median_z0_marker_side_px",
        "median_z0_marker_footprint_px2",
    )
    angle_associations = []
    for height in HEIGHTS:
        units = [(run, camera) for run in runs for camera in CAMERAS]
        errors = [single_metric_index[(run, camera, height)] for run, camera in units]
        for variable in variables:
            values = [float(geometry_index[(run, camera)][variable]) for run, camera in units]
            pearson, spearman = correlation(values, errors)
            angle_associations.append(
                {
                    "height_gt_mm": height,
                    "geometry_variable": variable,
                    "n_run_camera_units": len(units),
                    "pearson_r_with_pnp_xy_rmse": pearson,
                    "spearman_rho_with_pnp_xy_rmse": spearman,
                    "descriptive_only": 1,
                    "camera_identity_and_geometry_confounded": 1,
                }
            )
    write_csv(OUT["angle_associations"], angle_associations)

    # The ten run-camera rows arise from only two fixed camera placements
    # repeated across five rebuilds. Quantify how much each geometry variable
    # is explained by camera identity before interpreting pooled correlations.
    camera_identity_audit = []
    for variable in variables:
        all_values = np.asarray([float(row[variable]) for row in camera_geometry], dtype=float)
        grand_mean = float(np.mean(all_values))
        ss_total = float(np.sum((all_values - grand_mean) ** 2))
        group_stats = {}
        ss_between = 0.0
        ranges = []
        within_variances = []
        within_dfs = 0
        for camera in CAMERAS:
            values = np.asarray(
                [float(row[variable]) for row in camera_geometry if row["camera_id"] == camera],
                dtype=float,
            )
            group_mean = float(np.mean(values))
            group_sd = float(np.std(values, ddof=1))
            group_stats[camera] = {
                "n_rebuilds": int(len(values)),
                "mean": group_mean,
                "sd": group_sd,
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }
            ss_between += len(values) * (group_mean - grand_mean) ** 2
            ranges.append((float(np.min(values)), float(np.max(values))))
            within_variances.append((len(values) - 1) * group_sd * group_sd)
            within_dfs += len(values) - 1
        pooled_within_sd = math.sqrt(sum(within_variances) / within_dfs)
        mean_difference = group_stats["ihawk2"]["mean"] - group_stats["ihawk1"]["mean"]
        camera_identity_audit.append(
            {
                "geometry_variable": variable,
                "camera_identity_eta_squared": ss_between / ss_total if ss_total else float("nan"),
                "ihawk2_minus_ihawk1_mean": mean_difference,
                "pooled_within_camera_sd": pooled_within_sd,
                "standardized_camera_separation": (
                    mean_difference / pooled_within_sd if pooled_within_sd else float("nan")
                ),
                "camera_ranges_overlap": bool(
                    max(ranges[0][0], ranges[1][0]) <= min(ranges[0][1], ranges[1][1])
                ),
                "by_camera": group_stats,
            }
        )

    geometry_pairwise_correlations = []
    for i, variable_a in enumerate(variables):
        for variable_b in variables[i + 1:]:
            values_a = [float(row[variable_a]) for row in camera_geometry]
            values_b = [float(row[variable_b]) for row in camera_geometry]
            pearson, spearman = correlation(values_a, values_b)
            geometry_pairwise_correlations.append(
                {
                    "variable_a": variable_a,
                    "variable_b": variable_b,
                    "pearson_r": pearson,
                    "spearman_rho": spearman,
                }
            )

    angle_error_diagnostics = []
    for height in HEIGHTS:
        pooled_values = []
        pooled_errors = []
        by_camera = {}
        for camera in CAMERAS:
            values = [
                float(geometry_index[(run, camera)]["optical_axis_tilt_to_board_normal_deg"])
                for run in runs
            ]
            errors = [single_metric_index[(run, camera, height)] for run in runs]
            pearson, spearman = correlation(values, errors)
            by_camera[camera] = {
                "n_rebuilds": len(runs),
                "tilt_range_deg": max(values) - min(values),
                "pearson_r": pearson,
                "spearman_rho": spearman,
            }
            pooled_values.extend(values)
            pooled_errors.extend(errors)
        pooled_pearson, pooled_spearman = correlation(pooled_values, pooled_errors)
        angle_error_diagnostics.append(
            {
                "height_gt_mm": height,
                "pooled_n_run_camera_rows": len(pooled_values),
                "effective_fixed_placements": len(CAMERAS),
                "pooled_pearson_r": pooled_pearson,
                "pooled_spearman_rho": pooled_spearman,
                "by_camera": by_camera,
            }
        )

    angle_identifiability = {
        "created_at_utc": utc_now(),
        "verdict": "not_identifiable_from_current_E6",
        "run_camera_rows": len(camera_geometry),
        "physical_rebuilds": len(runs),
        "effective_fixed_camera_placements": len(CAMERAS),
        "causal_angle_levels": 0,
        "reason": (
            "Angle was not independently manipulated. Camera identity, distance, azimuth, "
            "marker footprint, optics, and calibration changed together."
        ),
        "camera_identity_audit": camera_identity_audit,
        "geometry_pairwise_correlations": geometry_pairwise_correlations,
        "angle_error_diagnostics": angle_error_diagnostics,
        "allowed_use": (
            "Descriptive setup characterization and confounding audit; no causal angle effect, "
            "optimal-angle recommendation, or angle-generalization claim."
        ),
    }
    OUT["angle_identifiability_json"].write_text(
        json.dumps(json_safe(angle_identifiability), indent=2, allow_nan=False), encoding="utf-8"
    )

    audit_lines = [
        "# E6 camera-angle identifiability audit",
        "",
        f"Generated: {angle_identifiability['created_at_utc']}",
        "",
        "## Verdict",
        "",
        "The current E6 data do **not** identify a causal camera-angle effect. The ten run-camera rows are five rebuild repetitions of only two fixed placements, not ten independently selected angles. Camera identity, distance, azimuth, marker footprint, optics, and calibration change together.",
        "",
        "## Camera-identity separation",
        "",
        "`eta²` is the fraction of observed variation in each geometry variable explained by the two camera identities. A non-overlapping range means the two fixed placements can be separated perfectly by that variable in this dataset.",
        "",
        "| Geometry variable | ihawk1 mean [range] | ihawk2 mean [range] | Camera eta² | Standardized separation | Ranges overlap |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in camera_identity_audit:
        c1 = row["by_camera"]["ihawk1"]
        c2 = row["by_camera"]["ihawk2"]
        audit_lines.append(
            f"| {row['geometry_variable']} | {c1['mean']:.3f} [{c1['min']:.3f}, {c1['max']:.3f}] | "
            f"{c2['mean']:.3f} [{c2['min']:.3f}, {c2['max']:.3f}] | "
            f"{row['camera_identity_eta_squared']:.4f} | {row['standardized_camera_separation']:.2f} | "
            f"{'yes' if row['camera_ranges_overlap'] else 'no'} |"
        )
    audit_lines.extend(
        [
            "",
            "## Permitted interpretation",
            "",
            "- Report both cameras' placement geometry and marker footprint as descriptive setup information.",
            "- Report pooled correlations only as diagnostics demonstrating confounding, never as evidence that tilt caused the error difference.",
            "- Do not fit or publish an optimal-angle rule from these data. A controlled angle sweep would require new physical acquisition and is outside the no-rebuild plan.",
            "",
        ]
    )
    OUT["angle_identifiability_md"].write_text("\n".join(audit_lines), encoding="utf-8")

    # Information-flow diagram.
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.2))
    for ax in axes:
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 6)
        ax.axis("off")

    def box(ax, x, y, w, h, text, color):
        patch = FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.04", facecolor=color,
            edgecolor="0.25", linewidth=1.1
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9)

    def arrow(ax, x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="->", mutation_scale=12))

    ax = axes[0]
    ax.set_title("Single-camera information flow")
    box(ax, 0.4, 2.4, 1.7, 1.0, "One image", "#d9edf7")
    box(ax, 2.8, 2.4, 1.7, 1.0, "Marker\nobservation", "#dff0d8")
    box(ax, 5.2, 2.4, 1.7, 1.0, "Camera-specific\nmodel", "#fcf8e3")
    box(ax, 7.6, 2.4, 1.8, 1.0, "Board XY/XYZ", "#f2dede")
    for x1, x2 in ((2.1, 2.8), (4.5, 5.2), (6.9, 7.6)):
        arrow(ax, x1, 2.9, x2, 2.9)

    ax = axes[1]
    ax.set_title("Dual-camera information flow")
    box(ax, 0.2, 4.1, 1.6, 0.9, "Image 1", "#d9edf7")
    box(ax, 0.2, 1.0, 1.6, 0.9, "Image 2", "#d9edf7")
    box(ax, 2.3, 4.1, 1.7, 0.9, "Observation 1", "#dff0d8")
    box(ax, 2.3, 1.0, 1.7, 0.9, "Observation 2", "#dff0d8")
    box(ax, 4.7, 2.55, 1.8, 0.9, "Common board\ncoordinates", "#fcf8e3")
    box(ax, 7.0, 2.55, 1.3, 0.9, "Fuse or\ntriangulate", "#eadcf8")
    box(ax, 8.7, 2.55, 1.1, 0.9, "XY/XYZ", "#f2dede")
    arrow(ax, 1.8, 4.55, 2.3, 4.55)
    arrow(ax, 1.8, 1.45, 2.3, 1.45)
    arrow(ax, 4.0, 4.55, 4.7, 3.15)
    arrow(ax, 4.0, 1.45, 4.7, 2.85)
    arrow(ax, 6.5, 3.0, 7.0, 3.0)
    arrow(ax, 8.3, 3.0, 8.7, 3.0)
    save_figure(fig, "Fig_E6_1_information_flow")

    colors = {
        "ihawk1": "#1f77b4",
        "ihawk2": "#ff7f0e",
        "EqualFusion": "#2ca02c",
        "LOOWeightedFusion": "#9467bd",
    }
    fig, axes = plt.subplots(1, 3, figsize=(14.3, 4.1), sharex=True)
    for ax, model in zip(axes, MODELS):
        for source in colors:
            data = [
                row for row in fusion_height_summary
                if row["model"] == model and row["source"] == source
            ]
            data.sort(key=lambda row: float(row["height_gt_mm"]))
            ax.plot(
                [float(row["height_gt_mm"]) for row in data],
                [float(row["xy_rmse_mean_mm"]) for row in data],
                marker="o", markersize=3, label=source, color=colors[source]
            )
        ax.set_title(model)
        ax.set_xlabel("Height (mm)")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("XY RMSE mean across rebuilds (mm)")
    axes[-1].legend(fontsize=8)
    fig.suptitle("E6 single-camera versus estimate fusion")
    save_figure(fig, "Fig_E6_2_fusion_accuracy")

    pnp_single = {
        source: [
            row for row in fusion_height_summary
            if row["model"] == "PnP" and row["source"] == source
        ]
        for source in ("ihawk1", "ihawk2", "EqualFusion", "LOOWeightedFusion")
    }
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.1))
    for source, data in pnp_single.items():
        data.sort(key=lambda row: float(row["height_gt_mm"]))
        axes[0].plot(
            [float(row["height_gt_mm"]) for row in data],
            [float(row["xy_rmse_mean_mm"]) for row in data],
            marker="o", markersize=3, label=source
        )
    axes[0].plot(
        [float(row["height_gt_mm"]) for row in stereo_height_summary],
        [float(row["xy_rmse_mean_mm"]) for row in stereo_height_summary],
        marker="D", color="black", linewidth=2, label="StereoTriangulation"
    )
    axes[0].set_ylabel("XY RMSE mean (mm)")
    axes[0].set_xlabel("Height (mm)")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[0].set_title("XY localization")
    axes[1].plot(
        [float(row["height_gt_mm"]) for row in stereo_height_summary],
        [float(row["z_rmse_mean_mm"]) for row in stereo_height_summary],
        marker="o", label="Stereo Z RMSE"
    )
    axes[1].plot(
        [float(row["height_gt_mm"]) for row in stereo_height_summary],
        [float(row["error3d_rmse_mean_mm"]) for row in stereo_height_summary],
        marker="s", label="Stereo 3D RMSE"
    )
    axes[1].set_ylabel("RMSE mean (mm)")
    axes[1].set_xlabel("Height (mm)")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)
    axes[1].set_title("Stereo depth and 3-D")
    fig.suptitle("E6 independent PnP estimates versus true two-view geometry")
    save_figure(fig, "Fig_E6_3_stereo_comparison")

    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0))
    for camera, color in zip(CAMERAS, ("#1f77b4", "#ff7f0e")):
        data = [row for row in camera_geometry if row["camera_id"] == camera]
        axes[0].scatter(
            [float(row["distance_to_board_center_mm"]) for row in data],
            [float(row["median_z0_marker_footprint_px2"]) for row in data],
            label=camera, color=color
        )
        axes[1].scatter(
            [float(row["optical_axis_tilt_to_board_normal_deg"]) for row in data],
            [single_metric_index[(row["run_id"], camera, 25.0)] for row in data],
            label=camera, color=color
        )
    pair0 = [row for row in pair_geometry if float(row["height_gt_mm"]) == 0.0]
    axes[2].scatter(
        [float(row["camera_baseline_mm"]) for row in pair0],
        [float(row["central_target_ray_convergence_deg"]) for row in pair0],
        color="black"
    )
    axes[0].set_xlabel("Camera distance to board center (mm)")
    axes[0].set_ylabel("Median marker footprint at Z=0 (px²)")
    axes[1].set_xlabel("Optical-axis tilt to board normal (deg)")
    axes[1].set_ylabel("PnP XY RMSE at 25 mm (mm)")
    axes[2].set_xlabel("Stereo baseline (mm)")
    axes[2].set_ylabel("Central ray convergence (deg)")
    for ax in axes:
        ax.grid(alpha=0.25)
    axes[0].legend()
    axes[1].legend()
    fig.suptitle("E6 view-geometry diagnostics (descriptive)")
    save_figure(fig, "Fig_E6_4_view_geometry")

    # Concise summary.
    def fusion_row(height, model, source):
        return next(
            row for row in fusion_height_summary
            if float(row["height_gt_mm"]) == float(height)
            and row["model"] == model and row["source"] == source
        )

    def stereo_row(height):
        return next(row for row in stereo_height_summary if float(row["height_gt_mm"]) == float(height))

    geometry_means = {
        camera: {
            "distance": mean(
                float(row["distance_to_board_center_mm"])
                for row in camera_geometry if row["camera_id"] == camera
            ),
            "tilt": mean(
                float(row["optical_axis_tilt_to_board_normal_deg"])
                for row in camera_geometry if row["camera_id"] == camera
            ),
            "footprint": mean(
                float(row["median_z0_marker_footprint_px2"])
                for row in camera_geometry if row["camera_id"] == camera
            ),
        }
        for camera in CAMERAS
    }
    key_heights = (0, 5, 25, 50)
    summary_data = {
        "created_at_utc": utc_now(),
        "pair_delta_median_ms": median(pair_deltas),
        "pair_delta_p95_ms": pct(pair_deltas, 95),
        "pair_delta_max_ms": max(pair_deltas),
        "camera_geometry_means": geometry_means,
        "fusion_key_heights": {
            model: {
                str(height): {
                    source: float(fusion_row(height, model, source)["xy_rmse_mean_mm"])
                    for source in ("ihawk1", "ihawk2", "EqualFusion", "LOOWeightedFusion")
                }
                for height in key_heights
            }
            for model in MODELS
        },
        "stereo_key_heights": {str(height): stereo_row(height) for height in key_heights},
        "angle_identifiability": {
            "verdict": angle_identifiability["verdict"],
            "run_camera_rows": angle_identifiability["run_camera_rows"],
            "effective_fixed_camera_placements": angle_identifiability[
                "effective_fixed_camera_placements"
            ],
            "causal_angle_levels": angle_identifiability["causal_angle_levels"],
        },
    }
    OUT["summary_json"].write_text(
        json.dumps(json_safe(summary_data), indent=2, allow_nan=False), encoding="utf-8"
    )

    lines = [
        "# E6 single/dual-camera and view-geometry pilot — results",
        "",
        f"Generated: {summary_data['created_at_utc']}",
        "",
        "## Executive findings",
        "",
        f"- All retained pairs passed the acquisition sync gate; pair delta median/P95/max was {summary_data['pair_delta_median_ms']:.3f}/{summary_data['pair_delta_p95_ms']:.3f}/{summary_data['pair_delta_max_ms']:.3f} ms. The target was static.",
        f"- The cameras had similar oblique optical-axis tilt ({geometry_means['ihawk1']['tilt']:.1f}°/{geometry_means['ihawk2']['tilt']:.1f}°), but ihawk2 was closer and produced a larger Z=0 marker footprint ({geometry_means['ihawk1']['footprint']:.0f}/{geometry_means['ihawk2']['footprint']:.0f} px²). Camera identity and geometry remain confounded.",
        "- A dedicated identifiability audit confirmed that the ten run-camera rows represent only two fixed placements; angle was never independently manipulated. Pooled angle/error correlations therefore cannot support a causal angle claim.",
        f"- At 25 mm, equal PnP fusion had {float(fusion_row(25, 'PnP', 'EqualFusion')['xy_rmse_mean_mm']):.3f} mm XY RMSE versus {float(fusion_row(25, 'PnP', 'ihawk1')['xy_rmse_mean_mm']):.3f}/{float(fusion_row(25, 'PnP', 'ihawk2')['xy_rmse_mean_mm']):.3f} mm for ihawk1/ihawk2. Naive averaging therefore worsened the stronger camera.",
        f"- Leave-one-rebuild-out PnP weighting reduced the damage ({float(fusion_row(25, 'PnP', 'LOOWeightedFusion')['xy_rmse_mean_mm']):.3f} mm at 25 mm) but did not beat ihawk2 ({float(fusion_row(25, 'PnP', 'ihawk2')['xy_rmse_mean_mm']):.3f} mm). A second biased estimate is not automatically useful.",
        f"- Stereo triangulation was materially different: XY RMSE was {float(stereo_row(0)['xy_rmse_mean_mm']):.3f}, {float(stereo_row(5)['xy_rmse_mean_mm']):.3f}, {float(stereo_row(25)['xy_rmse_mean_mm']):.3f}, and {float(stereo_row(50)['xy_rmse_mean_mm']):.3f} mm at 0/5/25/50 mm. It outperformed ihawk1 PnP throughout and was competitive with or better than ihawk2 PnP over most tested heights.",
        "- The new defensible conclusion is not 'two cameras are always better.' It is that estimate averaging and two-view geometry are different information flows: averaging preserves systematic bias, while calibrated parallax can add genuine depth information.",
        "",
        "## Key XY RMSE results (mean across five rebuilds)",
        "",
        "| Model | Height | ihawk1 | ihawk2 | Equal fusion | LOO weighted |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        for height in key_heights:
            lines.append(
                f"| {model} | {height} mm | {fmt(fusion_row(height, model, 'ihawk1')['xy_rmse_mean_mm'])} | "
                f"{fmt(fusion_row(height, model, 'ihawk2')['xy_rmse_mean_mm'])} | "
                f"{fmt(fusion_row(height, model, 'EqualFusion')['xy_rmse_mean_mm'])} | "
                f"{fmt(fusion_row(height, model, 'LOOWeightedFusion')['xy_rmse_mean_mm'])} |"
            )
    lines.extend(
        [
            "",
            "## Stereo triangulation",
            "",
            "| Height | XY RMSE | Z RMSE | 3-D RMSE |",
            "|---:|---:|---:|---:|",
        ]
    )
    for height in key_heights:
        row = stereo_row(height)
        lines.append(
            f"| {height} mm | {fmt(row['xy_rmse_mean_mm'])} | {fmt(row['z_rmse_mean_mm'])} | "
            f"{fmt(row['error3d_rmse_mean_mm'])} |"
        )
    lines.extend(
        [
            "",
            "## Required interpretation",
            "",
            "- `LOOWeightedGated` errors are conditional on accepted markers and must always be read with coverage.",
            "- The angle analysis is descriptive because only two camera placements were tested and several geometric factors change together.",
            "- `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` quantifies this confounding; it does not estimate an optimal view angle.",
            "- Stereo uses Z=0-derived projection matrices and is not an independent metrology system.",
            "- No dual-camera result has been propagated through E4 robot endpoint execution.",
            "",
        ]
    )
    OUT["summary"].write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "created_at_utc": utc_now(),
        "experiment": "E6 single/dual-camera information and view-geometry pilot",
        "script": str(SCRIPT.relative_to(REPO_ROOT)),
        "inputs": [
            str(PREDICTIONS_CSV.relative_to(REPO_ROOT)),
            str(CLEAN_CSV.relative_to(REPO_ROOT)),
            str(CALIBRATIONS_JSON.relative_to(REPO_ROOT)),
        ],
        "runs": runs,
        "cameras": list(CAMERAS),
        "models": list(MODELS),
        "fusion_sources": list(FUSION_SOURCES),
        "heights_mm": list(HEIGHTS),
        "statistical_unit": "physical rebuild",
        "software": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
            "platform": platform.platform(),
        },
        "outputs": {name: str(path.relative_to(REPO_ROOT)) for name, path in OUT.items()},
        "figures": sorted(str(path.relative_to(REPO_ROOT)) for path in FIGURES.glob("Fig_E6_*")),
        "limitations": [
            "Static paired observations; not a dynamic-scene sync validation.",
            "Z=0 is the calibration condition.",
            "Only two confounded view geometries are available.",
            "Stereo projection matrices are derived from the same E2 board observations.",
            "No dual-camera E4 endpoint validation.",
        ],
    }
    OUT["manifest"].write_text(
        json.dumps(json_safe(manifest), indent=2, allow_nan=False), encoding="utf-8"
    )
    print("E6 complete")
    print(OUT["summary"])


if __name__ == "__main__":
    main()
