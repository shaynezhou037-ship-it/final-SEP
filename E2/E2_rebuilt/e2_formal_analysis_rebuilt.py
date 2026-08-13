#!/usr/bin/env python3

from pathlib import Path
import csv
import json
import math
import shutil
from datetime import datetime

import numpy as np
import cv2


# ============================================================
# PATHS
# ============================================================

ROOT = Path(
    "/mnt/c/Users/ASUS/Desktop/paper/E2/E2_rebuilt"
)

INPUT = ROOT / "E2_all_5runs_REBUILT_clean.csv"

OUT = ROOT / "model_comparison"

# Remove old derived results if script is rerun
if OUT.exists():
    shutil.rmtree(OUT)

OUT.mkdir(parents=True)

PRED_CSV = OUT / "E2_predictions.csv"
RUN_METRICS_CSV = OUT / "E2_run_height_metrics.csv"
HEIGHT_SUMMARY_CSV = OUT / "E2_height_summary.csv"
PNP_AUDIT_CSV = OUT / "E2_PnP_rebuild_audit.csv"
CALIBRATION_JSON = OUT / "E2_calibration_models.json"
MANIFEST_JSON = OUT / "E2_analysis_manifest.json"


# ============================================================
# CONSTANTS
# ============================================================

HEIGHTS = [
    0.0, 5.0, 10.0, 15.0, 20.0,
    25.0, 30.0, 35.0, 40.0, 45.0, 50.0
]

CAMERAS = ["ihawk1", "ihawk2"]
MODELS = ["Affine", "Homography", "PnP"]

MARKER_SIZE_MM = 50.0
HALF = MARKER_SIZE_MM / 2.0

K = {
    "ihawk1": np.array([
        [401.77020263671875, 0.0, 322.1313781738281],
        [0.0, 401.9191589355469, 202.54229736328125],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64),

    "ihawk2": np.array([
        [391.3234558105469, 0.0, 320.85333251953125],
        [0.0, 391.3234558105469, 202.9705047607422],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64),
}

# CSV points are already undistorted pixel coordinates
D = np.zeros((5, 1), dtype=np.float64)


# ============================================================
# LOAD
# ============================================================

if not INPUT.exists():
    raise FileNotFoundError(INPUT)

with INPUT.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

runs = sorted(set(r["run_id"] for r in rows))

print("=" * 86)
print("E2 REBUILT — FORMAL AFFINE / HOMOGRAPHY / PnP ANALYSIS")
print("=" * 86)
print("Input :", INPUT)
print("Rows  :", len(rows))
print("Runs  :", runs)
print()

if len(rows) != 1650:
    raise RuntimeError(
        f"Expected 1650 raw-clean rows, got {len(rows)}"
    )

if len(runs) != 5:
    raise RuntimeError(
        f"Expected 5 independent runs, got {len(runs)}"
    )


# ============================================================
# HELPERS
# ============================================================

def truthy(x):
    return str(x).strip().lower() in {
        "1", "true", "yes"
    }


def marker_group(run, cam, z, marker_id):
    return [
        r for r in rows
        if r["run_id"] == run
        and r["camera_id"] == cam
        and abs(float(r["height_gt_mm"]) - z) < 1e-9
        and int(float(r["marker_id"])) == marker_id
        and truthy(r["detection_valid"])
    ]


def mean_center(rr):
    return np.array([
        np.mean([
            float(r["center_u_undist_px"])
            for r in rr
        ]),
        np.mean([
            float(r["center_v_undist_px"])
            for r in rr
        ])
    ], dtype=np.float64)


def mean_corners(rr):

    pts = []

    for j in range(4):

        u = np.mean([
            float(r[f"corner{j}_u_undist_px"])
            for r in rr
        ])

        v = np.mean([
            float(r[f"corner{j}_v_undist_px"])
            for r in rr
        ])

        pts.append([u, v])

    return np.asarray(
        pts,
        dtype=np.float64
    )


def rmse(values):
    a = np.asarray(values, dtype=float)
    return float(
        np.sqrt(np.mean(a ** 2))
    )


# ============================================================
# AFFINE
# ============================================================

def fit_affine(img, xy):

    A = np.column_stack([
        img[:, 0],
        img[:, 1],
        np.ones(len(img))
    ])

    coef, _, _, _ = np.linalg.lstsq(
        A,
        xy,
        rcond=None
    )

    return coef


def affine_predict(coef, uv):

    p = np.array([
        uv[0],
        uv[1],
        1.0
    ])

    return p @ coef


# ============================================================
# HOMOGRAPHY
# ============================================================

def fit_homography(img, xy):

    H, _ = cv2.findHomography(
        img.astype(np.float64),
        xy.astype(np.float64),
        method=0
    )

    if H is None:
        raise RuntimeError(
            "Homography fit failed"
        )

    return H


def homography_predict(H, uv):

    p = np.array(
        [[[uv[0], uv[1]]]],
        dtype=np.float64
    )

    return cv2.perspectiveTransform(
        p,
        H
    ).reshape(2)


# ============================================================
# SINGLE-MARKER PnP
#
# ArUco corner order:
# TL, TR, BR, BL
# ============================================================

MARKER_OBJECT = np.array([
    [-HALF, +HALF, 0.0],
    [+HALF, +HALF, 0.0],
    [+HALF, -HALF, 0.0],
    [-HALF, -HALF, 0.0],
], dtype=np.float64)


def solve_marker_pnp(corners, cam):

    candidates = []

    if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE"):
        candidates.append(
            cv2.SOLVEPNP_IPPE_SQUARE
        )

    candidates.append(
        cv2.SOLVEPNP_ITERATIVE
    )

    best = None

    for flag in candidates:

        try:
            ok, rvec, tvec = cv2.solvePnP(
                MARKER_OBJECT,
                corners,
                K[cam],
                D,
                flags=flag
            )
        except cv2.error:
            continue

        if not ok:
            continue

        t = tvec.reshape(3)

        if t[2] <= 0:
            continue

        projected, _ = cv2.projectPoints(
            MARKER_OBJECT,
            rvec,
            tvec,
            K[cam],
            D
        )

        projected = projected.reshape(-1, 2)

        reproj = float(
            np.sqrt(
                np.mean(
                    np.sum(
                        (projected - corners) ** 2,
                        axis=1
                    )
                )
            )
        )

        if best is None or reproj < best[0]:
            best = (
                reproj,
                rvec.reshape(3),
                t
            )

    if best is None:
        raise RuntimeError(
            "Single-marker PnP failed"
        )

    return best


# ============================================================
# BOARD-LEVEL EXTRINSIC FROM Z=0
#
# Camera model:
# X_cam = R_cb * X_board + t_cb
#
# Inverse:
# X_board = R_cb.T * (X_cam - t_cb)
# ============================================================

def board_extrinsic(run, cam):

    object_points = []
    image_points = []

    for marker_id in range(5):

        rr = marker_group(
            run,
            cam,
            0.0,
            marker_id
        )

        if len(rr) != 3:
            raise RuntimeError(
                f"{run}/{cam}/ID{marker_id}: "
                f"expected 3 Z=0 rows, got {len(rr)}"
            )

        mx = float(
            rr[0]["marker_gt_x_mm"]
        )

        my = float(
            rr[0]["marker_gt_y_mm"]
        )

        corners = mean_corners(rr)

        physical = [
            [mx - HALF, my + HALF, 0.0],
            [mx + HALF, my + HALF, 0.0],
            [mx + HALF, my - HALF, 0.0],
            [mx - HALF, my - HALF, 0.0],
        ]

        object_points.extend(
            physical
        )

        image_points.extend(
            corners
        )

    object_points = np.asarray(
        object_points,
        dtype=np.float64
    )

    image_points = np.asarray(
        image_points,
        dtype=np.float64
    )

    ok, rvec, tvec = cv2.solvePnP(
        object_points,
        image_points,
        K[cam],
        D,
        flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not ok:
        raise RuntimeError(
            f"Board PnP failed: {run}/{cam}"
        )

    R_cb, _ = cv2.Rodrigues(
        rvec
    )

    projected, _ = cv2.projectPoints(
        object_points,
        rvec,
        tvec,
        K[cam],
        D
    )

    projected = projected.reshape(-1, 2)

    reproj = float(
        np.sqrt(
            np.mean(
                np.sum(
                    (projected - image_points) ** 2,
                    axis=1
                )
            )
        )
    )

    return {
        "R_cb": R_cb,
        "t_cb": tvec.reshape(3),
        "rvec": rvec.reshape(3),
        "reprojection_rmse_px": reproj
    }


# ============================================================
# CALIBRATION
#
# IMPORTANT:
# Every run/camera gets its own Z=0 calibration.
# That calibration is then frozen for Z=5...50.
# ============================================================

calibrations = {}
calibration_export = {}

for run in runs:

    calibrations[run] = {}
    calibration_export[run] = {}

    for cam in CAMERAS:

        img = []
        gt = []

        for marker_id in range(5):

            rr = marker_group(
                run,
                cam,
                0.0,
                marker_id
            )

            if len(rr) != 3:
                raise RuntimeError(
                    f"{run}/{cam}/ID{marker_id}: "
                    f"expected 3 rows"
                )

            img.append(
                mean_center(rr)
            )

            gt.append([
                float(rr[0]["marker_gt_x_mm"]),
                float(rr[0]["marker_gt_y_mm"])
            ])

        img = np.asarray(
            img,
            dtype=np.float64
        )

        gt = np.asarray(
            gt,
            dtype=np.float64
        )

        A = fit_affine(
            img,
            gt
        )

        H = fit_homography(
            img,
            gt
        )

        ext = board_extrinsic(
            run,
            cam
        )

        calibrations[run][cam] = {
            "A": A,
            "H": H,
            "R_cb": ext["R_cb"],
            "t_cb": ext["t_cb"],
        }

        calibration_export[run][cam] = {
            "affine":
                A.tolist(),

            "homography":
                H.tolist(),

            "R_camera_from_board":
                ext["R_cb"].tolist(),

            "t_camera_from_board_mm":
                ext["t_cb"].tolist(),

            "board_pnp_reprojection_rmse_px":
                ext["reprojection_rmse_px"]
        }


CALIBRATION_JSON.write_text(
    json.dumps(
        calibration_export,
        indent=2
    ),
    encoding="utf-8"
)


# ============================================================
# PREDICTIONS
#
# 3 video frames are averaged first.
#
# Statistical unit:
# independent physical rebuild.
# ============================================================

predictions = []

for run in runs:

    print(f"Processing {run} ...")

    for cam in CAMERAS:

        cal = calibrations[run][cam]

        for z in HEIGHTS:

            for marker_id in range(5):

                rr = marker_group(
                    run,
                    cam,
                    z,
                    marker_id
                )

                if len(rr) != 3:
                    raise RuntimeError(
                        f"{run}/{cam}/Z={z}/ID={marker_id}: "
                        f"expected 3 frames, got {len(rr)}"
                    )

                uv = mean_center(rr)
                corners = mean_corners(rr)

                gt_x = float(
                    rr[0]["marker_gt_x_mm"]
                )

                gt_y = float(
                    rr[0]["marker_gt_y_mm"]
                )

                gt_z = float(
                    rr[0]["height_gt_mm"]
                )

                board_position = (
                    rr[0]["board_position"]
                )

                # ============================================
                # AFFINE
                # ============================================

                pa = affine_predict(
                    cal["A"],
                    uv
                )

                ea = float(
                    math.hypot(
                        pa[0] - gt_x,
                        pa[1] - gt_y
                    )
                )

                predictions.append({
                    "run_id": run,
                    "camera_id": cam,
                    "height_gt_mm": z,
                    "marker_id": marker_id,
                    "board_position": board_position,
                    "model": "Affine",

                    "pred_x_mm": float(pa[0]),
                    "pred_y_mm": float(pa[1]),
                    "pred_z_mm": "",

                    "gt_x_mm": gt_x,
                    "gt_y_mm": gt_y,
                    "gt_z_mm": gt_z,

                    "error_xy_mm": ea,
                    "error_z_signed_mm": "",
                    "error_3d_mm": "",

                    "pnp_marker_reprojection_rmse_px": ""
                })

                # ============================================
                # HOMOGRAPHY
                # ============================================

                ph = homography_predict(
                    cal["H"],
                    uv
                )

                eh = float(
                    math.hypot(
                        ph[0] - gt_x,
                        ph[1] - gt_y
                    )
                )

                predictions.append({
                    "run_id": run,
                    "camera_id": cam,
                    "height_gt_mm": z,
                    "marker_id": marker_id,
                    "board_position": board_position,
                    "model": "Homography",

                    "pred_x_mm": float(ph[0]),
                    "pred_y_mm": float(ph[1]),
                    "pred_z_mm": "",

                    "gt_x_mm": gt_x,
                    "gt_y_mm": gt_y,
                    "gt_z_mm": gt_z,

                    "error_xy_mm": eh,
                    "error_z_signed_mm": "",
                    "error_3d_mm": "",

                    "pnp_marker_reprojection_rmse_px": ""
                })

                # ============================================
                # PnP
                # ============================================

                marker_reproj, _, t_marker_cam = (
                    solve_marker_pnp(
                        corners,
                        cam
                    )
                )

                p_board = (
                    cal["R_cb"].T @
                    (
                        t_marker_cam -
                        cal["t_cb"]
                    )
                )

                px = float(p_board[0])
                py = float(p_board[1])
                pz = float(p_board[2])

                exy = float(
                    math.hypot(
                        px - gt_x,
                        py - gt_y
                    )
                )

                ez = float(
                    pz - gt_z
                )

                e3d = float(
                    math.sqrt(
                        (px - gt_x) ** 2 +
                        (py - gt_y) ** 2 +
                        (pz - gt_z) ** 2
                    )
                )

                predictions.append({
                    "run_id": run,
                    "camera_id": cam,
                    "height_gt_mm": z,
                    "marker_id": marker_id,
                    "board_position": board_position,
                    "model": "PnP",

                    "pred_x_mm": px,
                    "pred_y_mm": py,
                    "pred_z_mm": pz,

                    "gt_x_mm": gt_x,
                    "gt_y_mm": gt_y,
                    "gt_z_mm": gt_z,

                    "error_xy_mm": exy,
                    "error_z_signed_mm": ez,
                    "error_3d_mm": e3d,

                    "pnp_marker_reprojection_rmse_px":
                        marker_reproj
                })


# ============================================================
# PREDICTION HARD QC
# ============================================================

expected_predictions = (
    5 * 2 * 11 * 5 * 3
)

if len(predictions) != expected_predictions:
    raise RuntimeError(
        f"Expected {expected_predictions} predictions, "
        f"got {len(predictions)}"
    )


prediction_fields = list(
    predictions[0].keys()
)

with PRED_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=prediction_fields
    )

    writer.writeheader()
    writer.writerows(predictions)


# ============================================================
# RUN × HEIGHT METRICS
# ============================================================

run_metrics = []

for run in runs:

    for cam in CAMERAS:

        for model in MODELS:

            for z in HEIGHTS:

                pp = [
                    p for p in predictions
                    if p["run_id"] == run
                    and p["camera_id"] == cam
                    and p["model"] == model
                    and float(
                        p["height_gt_mm"]
                    ) == z
                ]

                if len(pp) != 5:
                    raise RuntimeError(
                        f"{run}/{cam}/{model}/{z}: "
                        f"expected 5 markers, got {len(pp)}"
                    )

                xy = np.array([
                    float(p["error_xy_mm"])
                    for p in pp
                ])

                rec = {
                    "run_id": run,
                    "camera_id": cam,
                    "model": model,
                    "height_gt_mm": z,

                    "xy_mean_mm":
                        float(np.mean(xy)),

                    "xy_rmse_mm":
                        rmse(xy),

                    "xy_median_mm":
                        float(np.median(xy)),

                    "xy_p95_mm":
                        float(np.percentile(xy, 95)),

                    "xy_max_mm":
                        float(np.max(xy)),

                    "z_mae_mm": "",
                    "z_rmse_mm": "",
                    "error3d_rmse_mm": ""
                }

                if model == "PnP":

                    ez = np.array([
                        float(p["error_z_signed_mm"])
                        for p in pp
                    ])

                    e3d = np.array([
                        float(p["error_3d_mm"])
                        for p in pp
                    ])

                    rec["z_mae_mm"] = float(
                        np.mean(
                            np.abs(ez)
                        )
                    )

                    rec["z_rmse_mm"] = rmse(
                        ez
                    )

                    rec["error3d_rmse_mm"] = rmse(
                        e3d
                    )

                run_metrics.append(rec)


with RUN_METRICS_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    fields = list(
        run_metrics[0].keys()
    )

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()
    writer.writerows(run_metrics)


# ============================================================
# SUMMARY ACROSS FIVE INDEPENDENT REBUILDS
# ============================================================

summary = []

for cam in CAMERAS:

    for model in MODELS:

        for z in HEIGHTS:

            rr = [
                r for r in run_metrics
                if r["camera_id"] == cam
                and r["model"] == model
                and float(
                    r["height_gt_mm"]
                ) == z
            ]

            if len(rr) != 5:
                raise RuntimeError(
                    f"{cam}/{model}/{z}: "
                    f"expected 5 runs"
                )

            xy = np.array([
                float(r["xy_rmse_mm"])
                for r in rr
            ])

            record = {
                "camera_id": cam,
                "model": model,
                "height_gt_mm": z,
                "n_independent_runs": 5,

                "xy_rmse_mean_mm":
                    float(np.mean(xy)),

                "xy_rmse_sd_mm":
                    float(
                        np.std(
                            xy,
                            ddof=1
                        )
                    ),

                "xy_rmse_median_mm":
                    float(np.median(xy)),

                "xy_rmse_min_mm":
                    float(np.min(xy)),

                "xy_rmse_max_mm":
                    float(np.max(xy)),

                "pnp_z_rmse_mean_mm": "",
                "pnp_z_rmse_sd_mm": "",

                "pnp_3d_rmse_mean_mm": "",
                "pnp_3d_rmse_sd_mm": ""
            }

            if model == "PnP":

                zrmse = np.array([
                    float(r["z_rmse_mm"])
                    for r in rr
                ])

                d3 = np.array([
                    float(
                        r["error3d_rmse_mm"]
                    )
                    for r in rr
                ])

                record[
                    "pnp_z_rmse_mean_mm"
                ] = float(
                    np.mean(zrmse)
                )

                record[
                    "pnp_z_rmse_sd_mm"
                ] = float(
                    np.std(
                        zrmse,
                        ddof=1
                    )
                )

                record[
                    "pnp_3d_rmse_mean_mm"
                ] = float(
                    np.mean(d3)
                )

                record[
                    "pnp_3d_rmse_sd_mm"
                ] = float(
                    np.std(
                        d3,
                        ddof=1
                    )
                )

            summary.append(record)


with HEIGHT_SUMMARY_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    fields = list(
        summary[0].keys()
    )

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()
    writer.writerows(summary)


# ============================================================
# PnP REBUILD AUDIT
# ============================================================

pnp_audit = []

for cam in CAMERAS:

    for z in HEIGHTS:

        rr = [
            r for r in run_metrics
            if r["camera_id"] == cam
            and r["model"] == "PnP"
            and float(
                r["height_gt_mm"]
            ) == z
        ]

        for r in rr:

            pnp_audit.append({
                "camera_id": cam,
                "height_gt_mm": z,
                "run_id": r["run_id"],
                "xy_rmse_mm":
                    float(r["xy_rmse_mm"]),
                "z_rmse_mm":
                    float(r["z_rmse_mm"]),
                "error3d_rmse_mm":
                    float(r["error3d_rmse_mm"])
            })


with PNP_AUDIT_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    fields = list(
        pnp_audit[0].keys()
    )

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()
    writer.writerows(pnp_audit)


# ============================================================
# MANIFEST
# ============================================================

manifest = {
    "created_at":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "input":
        str(INPUT),

    "formal_runs":
        runs,

    "models": MODELS,

    "calibration":
        (
            "Each camera in each independent rebuild is "
            "calibrated only from its Z=0 data. The resulting "
            "model is frozen and applied to Z=5...50 mm."
        ),

    "frame_handling":
        (
            "Three frames belonging to one physical condition "
            "are averaged before prediction and are not treated "
            "as independent repeats."
        ),

    "statistical_unit":
        "independent physical rebuild",

    "n_independent_rebuilds":
        5,

    "primary_metric":
        "XY RMSE in millimetres",

    "important_note":
        (
            "Z=0 is the calibration condition, not a held-out "
            "independent validation condition."
        ),

    "outputs": {
        "predictions": str(PRED_CSV),
        "run_height_metrics": str(RUN_METRICS_CSV),
        "height_summary": str(HEIGHT_SUMMARY_CSV),
        "pnp_rebuild_audit": str(PNP_AUDIT_CSV),
        "calibration_models": str(CALIBRATION_JSON),
    }
}

MANIFEST_JSON.write_text(
    json.dumps(
        manifest,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)


# ============================================================
# TERMINAL RESULTS
# ============================================================

print()
print("=" * 86)
print("PRIMARY RESULT — XY RMSE, MEAN ± SD ACROSS 5 REBUILDS")
print("=" * 86)

for cam in CAMERAS:

    print()
    print(cam)

    print(
        "Height | Affine             "
        "Homography         "
        "PnP"
    )

    print("-" * 72)

    for z in HEIGHTS:

        cells = {}

        for model in MODELS:

            rec = next(
                r for r in summary
                if r["camera_id"] == cam
                and r["model"] == model
                and float(
                    r["height_gt_mm"]
                ) == z
            )

            cells[model] = (
                float(
                    rec["xy_rmse_mean_mm"]
                ),
                float(
                    rec["xy_rmse_sd_mm"]
                )
            )

        print(
            f"{z:5.0f}  | "
            f"{cells['Affine'][0]:6.2f}±{cells['Affine'][1]:5.2f}      "
            f"{cells['Homography'][0]:6.2f}±{cells['Homography'][1]:5.2f}      "
            f"{cells['PnP'][0]:6.2f}±{cells['PnP'][1]:5.2f}"
        )


# ============================================================
# DEGRADATION + LINEAR FIT
# ============================================================

print()
print("=" * 86)
print("HEIGHT DEGRADATION")
print("=" * 86)

for cam in CAMERAS:

    print()
    print(cam)

    for model in MODELS:

        yy = []

        for z in HEIGHTS:

            rec = next(
                r for r in summary
                if r["camera_id"] == cam
                and r["model"] == model
                and float(
                    r["height_gt_mm"]
                ) == z
            )

            yy.append(
                float(
                    rec["xy_rmse_mean_mm"]
                )
            )

        x = np.asarray(
            HEIGHTS,
            dtype=float
        )

        y = np.asarray(
            yy,
            dtype=float
        )

        slope, intercept = np.polyfit(
            x,
            y,
            1
        )

        yhat = slope * x + intercept

        ss_res = np.sum(
            (y - yhat) ** 2
        )

        ss_tot = np.sum(
            (y - np.mean(y)) ** 2
        )

        r2 = (
            1.0 - ss_res / ss_tot
            if ss_tot > 0
            else float("nan")
        )

        degradation = y[-1] - y[0]

        print(
            f"{model:10s} | "
            f"Z0->Z50 = {degradation:+7.3f} mm | "
            f"slope = {slope:+7.4f} mm/mm | "
            f"R2 = {r2:.4f}"
        )


# ============================================================
# PnP Z + 3D
# ============================================================

print()
print("=" * 86)
print("PnP SECONDARY METRICS")
print("=" * 86)

for cam in CAMERAS:

    print()
    print(cam)
    print(
        "Height | XY RMSE        Z RMSE         3D RMSE"
    )

    for z in HEIGHTS:

        rec = next(
            r for r in summary
            if r["camera_id"] == cam
            and r["model"] == "PnP"
            and float(
                r["height_gt_mm"]
            ) == z
        )

        print(
            f"{z:5.0f}  | "
            f"{float(rec['xy_rmse_mean_mm']):6.2f}±"
            f"{float(rec['xy_rmse_sd_mm']):5.2f}   "
            f"{float(rec['pnp_z_rmse_mean_mm']):6.2f}±"
            f"{float(rec['pnp_z_rmse_sd_mm']):5.2f}   "
            f"{float(rec['pnp_3d_rmse_mean_mm']):6.2f}±"
            f"{float(rec['pnp_3d_rmse_sd_mm']):5.2f}"
        )


print()
print("=" * 86)
print("[PASS] E2 REBUILT FORMAL ANALYSIS COMPLETE")
print("=" * 86)

print("Predictions:")
print(PRED_CSV)

print()
print("Run-height metrics:")
print(RUN_METRICS_CSV)

print()
print("Height summary:")
print(HEIGHT_SUMMARY_CSV)

print()
print("PnP rebuild audit:")
print(PNP_AUDIT_CSV)

print()
print("Calibration models:")
print(CALIBRATION_JSON)

print()
print("Manifest:")
print(MANIFEST_JSON)

