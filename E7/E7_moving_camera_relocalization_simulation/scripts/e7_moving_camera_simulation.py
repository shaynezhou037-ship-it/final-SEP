#!/usr/bin/env python3
"""E7 simulation: frozen calibration versus per-frame camera relocalization."""

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

CALIBRATIONS_JSON = REPO_ROOT / "E2" / "E2_rebuilt" / "model_comparison" / "E2_calibration_models.json"

CAMERAS = ("ihawk1", "ihawk2")
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
D_ZERO = np.zeros((5, 1), dtype=np.float64)
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 400

MARKER_SIZE_MM = 50.0
HALF = MARKER_SIZE_MM / 2.0
MARKER_OBJECT = np.array(
    [[-HALF, +HALF, 0.0], [+HALF, +HALF, 0.0],
     [+HALF, -HALF, 0.0], [-HALF, -HALF, 0.0]], dtype=np.float64
)

# Four outer E2 marker centers are fixed relocalization landmarks. The synthetic
# target uses five non-overlapping interior positions.
LANDMARK_CENTERS = np.array(
    [[-70.0, 113.5], [70.0, 113.5], [-70.0, -113.5], [70.0, -113.5]],
    dtype=np.float64,
)
TARGET_CENTERS = np.array(
    [[-30.0, 50.0], [30.0, 50.0], [0.0, 0.0], [-30.0, -50.0], [30.0, -50.0]],
    dtype=np.float64,
)
HEIGHTS = (0.0, 10.0, 25.0, 50.0)
MOTIONS = (
    {"tier": 0, "name": "S0_nominal", "translation_mm": 0.0, "rotation_deg": 0.0},
    {"tier": 1, "name": "S1_small", "translation_mm": 5.0, "rotation_deg": 0.5},
    {"tier": 2, "name": "S2_moderate", "translation_mm": 15.0, "rotation_deg": 2.0},
    {"tier": 3, "name": "S3_large", "translation_mm": 30.0, "rotation_deg": 5.0},
)
PIXEL_NOISE_SIGMAS = (0.1, 0.5, 1.0)
TRIALS = 50
RANDOM_SEED = 20260814
METHODS = (
    "FrozenHomography",
    "DynamicHomography",
    "FrozenExtrinsicPnP",
    "RelocalizedPnP",
    "OracleMotionAwarePnP",
)
XY_P95_BUDGETS_MM = (2.0, 5.0, 10.0)
MIN_SUCCESS_RATE = 0.99

OUT = {
    "config": RESULTS / "E7_configuration_metrics.csv",
    "overall": RESULTS / "E7_overall_summary.csv",
    "envelope": RESULTS / "E7_operating_envelope.csv",
    "summary": RESULTS / "E7_RESULTS_SUMMARY.md",
    "summary_json": RESULTS / "E7_summary.json",
    "manifest": RESULTS / "E7_manifest.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(path: Path, records: list[dict]) -> None:
    if not records:
        raise RuntimeError(f"Refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


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


def fmt(value, digits=3) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{x:.{digits}f}" if math.isfinite(x) else "NA"


def random_unit_vector(rng: np.random.Generator) -> np.ndarray:
    while True:
        vector = rng.normal(size=3)
        norm = np.linalg.norm(vector)
        if norm > 1e-12:
            return vector / norm


def move_camera_pose(R_cw: np.ndarray, t_cw: np.ndarray, motion: dict,
                     rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Perturb camera-to-world pose, then return world-to-camera R,t."""
    if motion["tier"] == 0:
        return R_cw.copy(), t_cw.copy()
    R_wc = R_cw.T
    camera_center = -R_wc @ t_cw
    translation = random_unit_vector(rng) * motion["translation_mm"]
    rotation_axis = random_unit_vector(rng)
    rotation_rvec = rotation_axis * math.radians(motion["rotation_deg"])
    R_delta, _ = cv2.Rodrigues(rotation_rvec.reshape(3, 1))
    moved_R_wc = R_delta @ R_wc
    moved_center = camera_center + translation
    moved_R_cw = moved_R_wc.T
    moved_t_cw = -moved_R_cw @ moved_center
    return moved_R_cw, moved_t_cw


def world_marker_corners(x: float, y: float, z: float) -> np.ndarray:
    corners = MARKER_OBJECT.copy()
    corners[:, 0] += x
    corners[:, 1] += y
    corners[:, 2] += z
    return corners


LANDMARK_OBJECT = np.vstack(
    [world_marker_corners(x, y, 0.0) for x, y in LANDMARK_CENTERS]
)


def project(points_world: np.ndarray, R_cw: np.ndarray, t_cw: np.ndarray,
            camera: str) -> np.ndarray:
    rvec, _ = cv2.Rodrigues(R_cw)
    image, _ = cv2.projectPoints(
        points_world, rvec, t_cw.reshape(3, 1), K[camera], D_ZERO
    )
    return image.reshape(-1, 2)


def in_image(points: np.ndarray) -> bool:
    return bool(
        np.all(points[:, 0] >= 0.0) and np.all(points[:, 0] < IMAGE_WIDTH)
        and np.all(points[:, 1] >= 0.0) and np.all(points[:, 1] < IMAGE_HEIGHT)
    )


def homography_predict(H: np.ndarray, uv: np.ndarray) -> np.ndarray:
    point = np.asarray(uv, dtype=np.float64).reshape(1, 1, 2)
    return cv2.perspectiveTransform(point, H).reshape(2)


def solve_target_pnp(corners: np.ndarray, camera: str):
    candidates = []
    if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE"):
        candidates.append(cv2.SOLVEPNP_IPPE_SQUARE)
    candidates.append(cv2.SOLVEPNP_ITERATIVE)
    best = None
    for flag in candidates:
        try:
            ok, rvec, tvec = cv2.solvePnP(
                MARKER_OBJECT, corners, K[camera], D_ZERO, flags=flag
            )
        except cv2.error:
            continue
        if not ok or float(tvec.reshape(3)[2]) <= 0:
            continue
        projected, _ = cv2.projectPoints(
            MARKER_OBJECT, rvec, tvec, K[camera], D_ZERO
        )
        reprojection = float(np.sqrt(np.mean(np.sum(
            (projected.reshape(-1, 2) - corners) ** 2, axis=1
        ))))
        if best is None or reprojection < best[0]:
            best = (reprojection, tvec.reshape(3))
    return best


def solve_camera_pose(landmark_image: np.ndarray, camera: str):
    try:
        ok, rvec, tvec = cv2.solvePnP(
            LANDMARK_OBJECT, landmark_image, K[camera], D_ZERO,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
    except cv2.error:
        return None
    if not ok:
        return None
    R_cw, _ = cv2.Rodrigues(rvec)
    return R_cw, tvec.reshape(3)


def new_bucket() -> dict:
    return {"planned": 0, "success": 0, "xy": [], "z": [], "d3": []}


def add_result(bucket: dict, prediction, truth: np.ndarray) -> None:
    bucket["planned"] += 1
    if prediction is None:
        return
    prediction = np.asarray(prediction, dtype=float).reshape(3)
    if not np.all(np.isfinite(prediction)):
        return
    delta = prediction - truth
    bucket["success"] += 1
    bucket["xy"].append(float(np.linalg.norm(delta[:2])))
    bucket["z"].append(float(abs(delta[2])))
    bucket["d3"].append(float(np.linalg.norm(delta)))


def metrics(bucket: dict) -> dict:
    def stat(values, name):
        array = np.asarray(values, dtype=float)
        if len(array) == 0:
            return float("nan")
        if name == "mean":
            return float(np.mean(array))
        if name == "rmse":
            return float(np.sqrt(np.mean(array * array)))
        if name == "median":
            return float(np.median(array))
        if name == "p95":
            return float(np.percentile(array, 95))
        raise KeyError(name)

    return {
        "n_planned": bucket["planned"],
        "n_success": bucket["success"],
        "success_rate": bucket["success"] / bucket["planned"] if bucket["planned"] else 0.0,
        "xy_mean_mm": stat(bucket["xy"], "mean"),
        "xy_rmse_mm": stat(bucket["xy"], "rmse"),
        "xy_median_mm": stat(bucket["xy"], "median"),
        "xy_p95_mm": stat(bucket["xy"], "p95"),
        "z_rmse_mm": stat(bucket["z"], "rmse"),
        "error_3d_rmse_mm": stat(bucket["d3"], "rmse"),
    }


def save_figure(fig, stem: str) -> None:
    fig.savefig(FIGURES / f"{stem}.png", dpi=240, bbox_inches="tight")
    fig.savefig(FIGURES / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def draw_information_flow() -> None:
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("E7: camera motion changes which calibration information remains valid", fontsize=20)

    def box(x, y, w, h, text, color):
        patch = FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.08", facecolor=color,
            edgecolor="black", linewidth=1.4,
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=11)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=15, linewidth=1.4))

    box(0.4, 5.7, 2.2, 1.1, "Nominal calibration\n(fixed pose)", "#d9eaf7")
    box(0.4, 1.2, 2.2, 1.1, "Fixed landmarks\nin current frame", "#d9f2df")
    box(3.4, 5.7, 2.5, 1.1, "Frozen mapping or\nfrozen extrinsic", "#f7d9d9")
    box(3.4, 1.2, 2.5, 1.1, "Per-frame H or\ncamera-pose PnP", "#fff0c7")
    box(6.8, 3.45, 2.1, 1.1, "Target pixels /\ntarget-marker PnP", "#e4dcf7")
    box(10.0, 5.7, 2.3, 1.1, "Frozen world\nestimate", "#f7d9d9")
    box(10.0, 1.2, 2.3, 1.1, "Relocalized world\nestimate", "#d9f2df")
    box(13.0, 3.45, 1.5, 1.1, "XY(Z)\nerror", "#eeeeee")
    arrow(2.6, 6.25, 3.4, 6.25)
    arrow(2.6, 1.75, 3.4, 1.75)
    arrow(5.9, 6.25, 10.0, 6.25)
    arrow(5.9, 1.75, 10.0, 1.75)
    arrow(8.9, 4.0, 10.0, 6.0)
    arrow(8.9, 4.0, 10.0, 2.0)
    arrow(12.3, 6.25, 13.3, 4.55)
    arrow(12.3, 1.75, 13.3, 3.45)
    ax.text(7.5, 7.25, "Camera moves", fontsize=14, weight="bold", color="#b22222")
    ax.annotate("", xy=(9.0, 7.15), xytext=(6.3, 7.15),
                arrowprops=dict(arrowstyle="<->", linewidth=2, color="#b22222"))
    ax.text(7.5, 0.45,
            "Key comparison: stale calibration versus calibration updated from current visual evidence",
            ha="center", fontsize=12)
    fig.tight_layout()
    save_figure(fig, "Fig_E7_1_information_flow")


def main() -> None:
    print("=" * 84)
    print("E7 - MOVING-CAMERA RELOCALIZATION SIMULATION")
    print("=" * 84)
    calibrations = json.loads(CALIBRATIONS_JSON.read_text(encoding="utf-8"))
    runs = sorted(calibrations)
    if len(runs) != 5:
        raise RuntimeError(f"Expected five E2 rebuilds, got {len(runs)}")

    rng = np.random.default_rng(RANDOM_SEED)
    config_buckets = defaultdict(new_bucket)
    overall_buckets = defaultdict(new_bucket)
    geometric_visibility = {"planned": 0, "inside": 0}

    for run in runs:
        for camera in CAMERAS:
            calibration = calibrations[run][camera]
            R_nominal = np.asarray(calibration["R_camera_from_board"], dtype=np.float64)
            t_nominal = np.asarray(calibration["t_camera_from_board_mm"], dtype=np.float64)
            nominal_landmark_centers_image = project(
                np.column_stack([LANDMARK_CENTERS, np.zeros(len(LANDMARK_CENTERS))]),
                R_nominal, t_nominal, camera,
            )
            H_nominal, _ = cv2.findHomography(
                nominal_landmark_centers_image, LANDMARK_CENTERS, method=0
            )
            if H_nominal is None:
                raise RuntimeError(f"Nominal homography failed for {run}/{camera}")

            for motion in MOTIONS:
                for sigma in PIXEL_NOISE_SIGMAS:
                    for _trial in range(TRIALS):
                        R_current, t_current = move_camera_pose(
                            R_nominal, t_nominal, motion, rng
                        )
                        landmark_image_true = project(
                            LANDMARK_OBJECT, R_current, t_current, camera
                        )
                        landmark_image = landmark_image_true + rng.normal(
                            0.0, sigma, landmark_image_true.shape
                        )
                        landmark_centers_image = landmark_image.reshape(-1, 4, 2).mean(axis=1)
                        H_current, _ = cv2.findHomography(
                            landmark_centers_image, LANDMARK_CENTERS, method=0
                        )
                        camera_pose = solve_camera_pose(landmark_image, camera)

                        for height in HEIGHTS:
                            for target_x, target_y in TARGET_CENTERS:
                                truth = np.array([target_x, target_y, height], dtype=float)
                                target_world = world_marker_corners(target_x, target_y, height)
                                target_image_true = project(
                                    target_world, R_current, t_current, camera
                                )
                                geometric_visibility["planned"] += 1
                                if in_image(landmark_image_true) and in_image(target_image_true):
                                    geometric_visibility["inside"] += 1
                                target_image = target_image_true + rng.normal(
                                    0.0, sigma, target_image_true.shape
                                )
                                target_center_image = target_image.mean(axis=0)
                                target_pose = solve_target_pnp(target_image, camera)

                                predictions = {}
                                xy = homography_predict(H_nominal, target_center_image)
                                predictions["FrozenHomography"] = np.array([xy[0], xy[1], 0.0])
                                if H_current is None:
                                    predictions["DynamicHomography"] = None
                                else:
                                    xy = homography_predict(H_current, target_center_image)
                                    predictions["DynamicHomography"] = np.array([xy[0], xy[1], 0.0])

                                if target_pose is None:
                                    predictions["FrozenExtrinsicPnP"] = None
                                    predictions["RelocalizedPnP"] = None
                                    predictions["OracleMotionAwarePnP"] = None
                                else:
                                    target_t_camera = target_pose[1]
                                    predictions["FrozenExtrinsicPnP"] = (
                                        R_nominal.T @ (target_t_camera - t_nominal)
                                    )
                                    predictions["OracleMotionAwarePnP"] = (
                                        R_current.T @ (target_t_camera - t_current)
                                    )
                                    if camera_pose is None:
                                        predictions["RelocalizedPnP"] = None
                                    else:
                                        R_estimated, t_estimated = camera_pose
                                        predictions["RelocalizedPnP"] = (
                                            R_estimated.T @ (target_t_camera - t_estimated)
                                        )

                                for method in METHODS:
                                    config_key = (
                                        run, camera, motion["name"], sigma, height, method
                                    )
                                    overall_key = (motion["name"], sigma, height, method)
                                    add_result(config_buckets[config_key], predictions[method], truth)
                                    add_result(overall_buckets[overall_key], predictions[method], truth)

    config_records = []
    for key in sorted(config_buckets):
        run, camera, motion_name, sigma, height, method = key
        motion = next(item for item in MOTIONS if item["name"] == motion_name)
        config_records.append({
            "run_id": run,
            "camera_id": camera,
            "motion_tier": motion["tier"],
            "motion_scenario": motion_name,
            "translation_mm": motion["translation_mm"],
            "rotation_deg": motion["rotation_deg"],
            "pixel_noise_sigma_px": sigma,
            "height_gt_mm": height,
            "method": method,
            **metrics(config_buckets[key]),
        })

    overall_records = []
    for motion in MOTIONS:
        for sigma in PIXEL_NOISE_SIGMAS:
            for height in HEIGHTS:
                for method in METHODS:
                    key = (motion["name"], sigma, height, method)
                    overall_records.append({
                        "motion_tier": motion["tier"],
                        "motion_scenario": motion["name"],
                        "translation_mm": motion["translation_mm"],
                        "rotation_deg": motion["rotation_deg"],
                        "pixel_noise_sigma_px": sigma,
                        "height_gt_mm": height,
                        "method": method,
                        **metrics(overall_buckets[key]),
                    })

    overall_index = {
        (row["motion_scenario"], row["pixel_noise_sigma_px"],
         row["height_gt_mm"], row["method"]): row
        for row in overall_records
    }
    envelope_records = []
    for method in METHODS:
        for sigma in PIXEL_NOISE_SIGMAS:
            for height in HEIGHTS:
                for budget in XY_P95_BUDGETS_MM:
                    feasible_prefix = []
                    for motion in MOTIONS:
                        row = overall_index[(motion["name"], sigma, height, method)]
                        feasible = (
                            row["success_rate"] >= MIN_SUCCESS_RATE
                            and row["xy_p95_mm"] <= budget
                        )
                        if feasible and len(feasible_prefix) == motion["tier"]:
                            feasible_prefix.append(motion)
                        else:
                            break
                    highest = feasible_prefix[-1] if feasible_prefix else None
                    envelope_records.append({
                        "method": method,
                        "pixel_noise_sigma_px": sigma,
                        "height_gt_mm": height,
                        "xy_p95_budget_mm": budget,
                        "minimum_success_rate": MIN_SUCCESS_RATE,
                        "max_feasible_motion_tier": highest["tier"] if highest else -1,
                        "max_feasible_motion_scenario": highest["name"] if highest else "none",
                        "max_translation_mm": highest["translation_mm"] if highest else float("nan"),
                        "max_rotation_deg": highest["rotation_deg"] if highest else float("nan"),
                    })

    write_csv(OUT["config"], config_records)
    write_csv(OUT["overall"], overall_records)
    write_csv(OUT["envelope"], envelope_records)

    # Figures.
    draw_information_flow()
    colors = {
        "FrozenHomography": "#1f77b4",
        "DynamicHomography": "#17becf",
        "FrozenExtrinsicPnP": "#d62728",
        "RelocalizedPnP": "#2ca02c",
        "OracleMotionAwarePnP": "#111111",
    }
    labels = {
        "FrozenHomography": "Frozen H",
        "DynamicHomography": "Per-frame H",
        "FrozenExtrinsicPnP": "PnP + frozen extrinsic",
        "RelocalizedPnP": "PnP + relocalization",
        "OracleMotionAwarePnP": "Oracle pose + PnP",
    }

    fig, axes = plt.subplots(1, 2, figsize=(15, 6), sharex=True)
    for ax, height in zip(axes, (0.0, 25.0)):
        for method in METHODS:
            rows = [overall_index[(m["name"], 0.5, height, method)] for m in MOTIONS]
            ax.plot([m["tier"] for m in MOTIONS], [r["xy_rmse_mm"] for r in rows],
                    marker="o", linewidth=2, color=colors[method], label=labels[method])
        ax.set_title(f"Target height {height:.0f} mm")
        ax.set_xticks(range(4), ["Nominal", "5 mm/0.5°", "15 mm/2°", "30 mm/5°"])
        ax.tick_params(axis="x", rotation=18)
        ax.set_ylabel("XY RMSE (mm)")
        ax.grid(True, alpha=0.3)
    axes[1].legend(fontsize=9)
    fig.suptitle("E7 movement sensitivity at 0.5 px corner noise", fontsize=19)
    fig.tight_layout()
    save_figure(fig, "Fig_E7_2_movement_sensitivity")

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, scenario in zip(axes, ("S0_nominal", "S2_moderate")):
        for method in METHODS:
            rows = [overall_index[(scenario, 0.5, h, method)] for h in HEIGHTS]
            ax.plot(HEIGHTS, [r["xy_rmse_mm"] for r in rows], marker="o", linewidth=2,
                    color=colors[method], label=labels[method])
        ax.set_title(scenario.replace("_", " "))
        ax.set_xlabel("Target height (mm)")
        ax.set_ylabel("XY RMSE (mm)")
        ax.grid(True, alpha=0.3)
    axes[1].legend(fontsize=9)
    fig.suptitle("E7 height × camera-motion interaction (0.5 px noise)", fontsize=19)
    fig.tight_layout()
    save_figure(fig, "Fig_E7_3_height_motion_interaction")

    envelope_index = {
        (row["method"], row["pixel_noise_sigma_px"], row["height_gt_mm"],
         row["xy_p95_budget_mm"]): row
        for row in envelope_records
    }
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharey=True)
    for ax, sigma in zip(axes, PIXEL_NOISE_SIGMAS):
        matrix = np.array([
            [envelope_index[(method, sigma, height, 5.0)]["max_feasible_motion_tier"]
             for height in HEIGHTS]
            for method in METHODS
        ], dtype=float)
        image = ax.imshow(matrix, vmin=-1, vmax=3, cmap="viridis", aspect="auto")
        ax.set_title(f"noise σ={sigma:.1f} px")
        ax.set_xticks(range(len(HEIGHTS)), [f"{h:.0f}" for h in HEIGHTS])
        ax.set_xlabel("Height (mm)")
        for i in range(len(METHODS)):
            for j in range(len(HEIGHTS)):
                ax.text(j, i, f"{int(matrix[i, j])}", ha="center", va="center",
                        color="white" if matrix[i, j] < 1.5 else "black", fontsize=9)
    axes[0].set_yticks(range(len(METHODS)), [labels[m] for m in METHODS])
    colorbar = fig.colorbar(image, ax=axes, shrink=0.8)
    colorbar.set_ticks([-1, 0, 1, 2, 3])
    colorbar.set_ticklabels(["none", "nominal", "small", "moderate", "large"])
    fig.suptitle("Maximum feasible motion tier: XY P95 ≤5 mm and success ≥99%", fontsize=18)
    fig.subplots_adjust(top=0.84, bottom=0.14, left=0.18, right=0.9, wspace=0.2)
    save_figure(fig, "Fig_E7_4_operating_envelope")

    headline = {
        method: {
            motion["name"]: overall_index[(motion["name"], 0.5, 25.0, method)]
            for motion in MOTIONS
        }
        for method in METHODS
    }
    summary_data = {
        "generated_utc": utc_now(),
        "evidence_class": "simulation_only",
        "random_seed": RANDOM_SEED,
        "trials_per_pose_motion_noise": TRIALS,
        "nominal_pose_count": len(runs) * len(CAMERAS),
        "geometric_visibility_rate": geometric_visibility["inside"] / geometric_visibility["planned"],
        "headline_noise_sigma_px": 0.5,
        "headline_height_mm": 25.0,
        "headline": headline,
    }
    OUT["summary_json"].write_text(
        json.dumps(json_safe(summary_data), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# E7 moving-camera relocalization simulation — results",
        "",
        f"Generated: {summary_data['generated_utc']}",
        "",
        "## Executive findings",
        "",
        "- E7 is simulation-only. It does not yet show real moving-camera performance.",
        "- PnP is not opposed to a moving-camera algorithm: `RelocalizedPnP` uses PnP both to recover the current camera pose from fixed landmarks and to recover the target marker pose.",
        "- Frozen mappings become stale after camera motion. Per-frame relocalization is the relevant comparison.",
        "- Per-frame Homography can compensate camera motion for planar targets, but its planar assumption remains invalid at nonzero target height.",
        "- At Z=0 and 0.5 px noise, per-frame Homography stayed near 0.87 mm XY RMSE from nominal through the largest motion, while frozen Homography grew from 1.21 to 68.54 mm.",
        "- At Z=25 mm, per-frame Homography stayed near 35 mm because it repaired camera motion but not the violated planar assumption.",
        "- At Z=25 mm, frozen-extrinsic PnP grew from 6.84 to 40.61 mm; relocalized PnP remained 6.62-6.85 mm and was close to the oracle (6.59-6.84 mm). Camera motion itself was not the limiting error after relocalization.",
        "",
        "## Headline XY results: 25 mm target height, 0.5 px corner noise",
        "",
        "| Method | Nominal RMSE/P95 | Small RMSE/P95 | Moderate RMSE/P95 | Large RMSE/P95 |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        cells = []
        for motion in MOTIONS:
            row = headline[method][motion["name"]]
            cells.append(f"{fmt(row['xy_rmse_mm'])}/{fmt(row['xy_p95_mm'])}")
        lines.append(f"| {method} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "All values are millimetres. Each cell pools five E2 rebuilds × two cameras × five target positions × 50 Monte Carlo trials.",
        "",
        "## Interpretation boundary",
        "",
        "- The Monte Carlo trials are simulated perturbations, not independent physical repeats.",
        "- The detector is represented only by Gaussian corner noise; missed detections, motion blur, occlusion, vibration, rolling shutter, and timing are absent.",
        "- The four motion tiers combine translation and rotation, so this pilot does not independently identify their effects.",
        "- A physical E7 acquisition is required before using moving-camera claims as central paper evidence.",
    ]
    OUT["summary"].write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest = {
        "generated_utc": summary_data["generated_utc"],
        "script": str(SCRIPT.relative_to(REPO_ROOT)),
        "input": str(CALIBRATIONS_JSON.relative_to(REPO_ROOT)),
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "random_seed": RANDOM_SEED,
        "trials": TRIALS,
        "motion_scenarios": MOTIONS,
        "pixel_noise_sigmas_px": PIXEL_NOISE_SIGMAS,
        "target_heights_mm": HEIGHTS,
        "methods": METHODS,
        "xy_p95_budgets_mm": XY_P95_BUDGETS_MM,
        "minimum_success_rate": MIN_SUCCESS_RATE,
        "detector_failure_model": "none; Gaussian corner noise only",
        "outputs": [str(path.relative_to(REPO_ROOT)) for path in OUT.values()],
    }
    OUT["manifest"].write_text(
        json.dumps(json_safe(manifest), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("E7 complete")
    print(OUT["summary"])


if __name__ == "__main__":
    main()
