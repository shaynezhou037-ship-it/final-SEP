#!/usr/bin/env python3

from pathlib import Path
import csv
import json
import math
import shutil
from collections import defaultdict
from datetime import datetime

import numpy as np
import cv2


# ============================================================
# PATHS
# ============================================================

ROOT = Path("/mnt/c/Users/ASUS/Desktop/paper/E3")

SUBSET_META_CSV = (
    ROOT / "E3_subsets/E3_calibration_subsets.csv"
)

SUBSET_POINTS_CSV = (
    ROOT / "E3_subsets/E3_calibration_subset_points.csv"
)

VALIDATION_CSV = (
    ROOT / "E3_split/E3_fixed_validation_12points.csv"
)

OUT = ROOT / "E3_model_comparison"

if OUT.exists():
    shutil.rmtree(OUT)

OUT.mkdir(parents=True)

TRIAL_CSV = OUT / "E3_trial_results.csv"
SUMMARY_CSV = OUT / "E3_condition_summary.csv"
MANIFEST_JSON = OUT / "E3_analysis_manifest.json"


# ============================================================
# EXPERIMENT
# ============================================================

POINT_COUNTS = [4, 6, 8, 12, 16, 24]
DISTRIBUTIONS = ["clustered", "random", "spread"]
MODELS = ["Affine", "Homography", "PnP"]

# E1 / E3 uses ihawk1
K = np.array([
    [401.77020263671875, 0.0, 322.1313781738281],
    [0.0, 401.9191589355469, 202.54229736328125],
    [0.0, 0.0, 1.0]
], dtype=np.float64)

K_INV = np.linalg.inv(K)

# E3 uses undistorted pixel coordinates.
D = np.zeros((5, 1), dtype=np.float64)


# ============================================================
# LOAD
# ============================================================

def load_csv(path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


subset_meta = load_csv(SUBSET_META_CSV)
subset_point_rows = load_csv(SUBSET_POINTS_CSV)
validation_rows = load_csv(VALIDATION_CSV)

print("=" * 88)
print("E3-3 — CALIBRATION DESIGN MODEL EVALUATION")
print("=" * 88)

print("Subset trials :", len(subset_meta))
print("Subset points :", len(subset_point_rows))
print("Validation    :", len(validation_rows))
print()

if len(subset_meta) != 1800:
    raise RuntimeError(
        f"Expected 1800 subsets, got {len(subset_meta)}"
    )

if len(validation_rows) != 12:
    raise RuntimeError(
        f"Expected 12 validation points, got {len(validation_rows)}"
    )


# ============================================================
# INDEX SUBSETS
# ============================================================

meta_by_id = {
    r["subset_id"]: r
    for r in subset_meta
}

points_by_subset = defaultdict(list)

for r in subset_point_rows:
    points_by_subset[r["subset_id"]].append(r)

if len(points_by_subset) != 1800:
    raise RuntimeError(
        f"Expected 1800 subset groups, got {len(points_by_subset)}"
    )


# ============================================================
# DATA HELPERS
# ============================================================

def image_points(rr):
    return np.array([
        [
            float(r["u_undist_median_px"]),
            float(r["v_undist_median_px"])
        ]
        for r in rr
    ], dtype=np.float64)


def board_xy(rr):
    return np.array([
        [
            float(r["board_x_mm"]),
            float(r["board_y_mm"])
        ]
        for r in rr
    ], dtype=np.float64)


VAL_IMG = image_points(validation_rows)
VAL_XY = board_xy(validation_rows)


def calc_errors(predicted, gt):

    predicted = np.asarray(
        predicted,
        dtype=np.float64
    )

    gt = np.asarray(
        gt,
        dtype=np.float64
    )

    if predicted.shape != gt.shape:
        raise RuntimeError(
            f"Prediction shape mismatch: "
            f"{predicted.shape} vs {gt.shape}"
        )

    if not np.all(np.isfinite(predicted)):
        raise RuntimeError(
            "Prediction contains NaN/Inf"
        )

    errors = np.linalg.norm(
        predicted - gt,
        axis=1
    )

    return {
        "validation_rmse_mm":
            float(np.sqrt(np.mean(errors ** 2))),

        "validation_mae_mm":
            float(np.mean(errors)),

        "validation_median_mm":
            float(np.median(errors)),

        "validation_max_mm":
            float(np.max(errors)),
    }


# ============================================================
# AFFINE
# ============================================================

def fit_affine(img, xy):

    design = np.column_stack([
        img[:, 0],
        img[:, 1],
        np.ones(len(img))
    ])

    coef, _, rank, _ = np.linalg.lstsq(
        design,
        xy,
        rcond=None
    )

    if rank < 3:
        raise RuntimeError(
            "Affine calibration is rank deficient"
        )

    pred_cal = design @ coef

    cal_errors = np.linalg.norm(
        pred_cal - xy,
        axis=1
    )

    cal_rmse = float(
        np.sqrt(
            np.mean(cal_errors ** 2)
        )
    )

    return coef, cal_rmse


def predict_affine(coef, img):

    design = np.column_stack([
        img[:, 0],
        img[:, 1],
        np.ones(len(img))
    ])

    return design @ coef


# ============================================================
# HOMOGRAPHY
# ============================================================

def fit_homography(img, xy):

    H, _ = cv2.findHomography(
        img,
        xy,
        method=0
    )

    if H is None:
        raise RuntimeError(
            "cv2.findHomography returned None"
        )

    if not np.all(np.isfinite(H)):
        raise RuntimeError(
            "Homography contains NaN/Inf"
        )

    p = cv2.perspectiveTransform(
        img.reshape(-1, 1, 2),
        H
    ).reshape(-1, 2)

    if not np.all(np.isfinite(p)):
        raise RuntimeError(
            "Homography calibration prediction invalid"
        )

    errors = np.linalg.norm(
        p - xy,
        axis=1
    )

    cal_rmse = float(
        np.sqrt(
            np.mean(errors ** 2)
        )
    )

    return H, cal_rmse


def predict_homography(H, img):

    pred = cv2.perspectiveTransform(
        img.reshape(-1, 1, 2),
        H
    ).reshape(-1, 2)

    if not np.all(np.isfinite(pred)):
        raise RuntimeError(
            "Homography validation prediction invalid"
        )

    return pred


# ============================================================
# PnP
#
# Board plane:
# Z_board = 0
#
# X_camera = R * X_board + t
#
# Camera center in board coordinates:
# C_board = -R^T t
#
# A validation pixel defines a camera ray.
# Transform ray into board frame and intersect Z=0.
# ============================================================

def pnp_pose_candidates(obj, img):

    candidates = []

    # --------------------------------------------
    # IPPE: specifically designed for coplanar PnP
    # --------------------------------------------

    if hasattr(cv2, "SOLVEPNP_IPPE"):

        try:
            out = cv2.solvePnPGeneric(
                obj,
                img,
                K,
                D,
                flags=cv2.SOLVEPNP_IPPE
            )

            if len(out) >= 3:

                rvecs = out[1]
                tvecs = out[2]

                for rv, tv in zip(
                    rvecs,
                    tvecs
                ):
                    candidates.append(
                        (
                            np.asarray(
                                rv,
                                dtype=np.float64
                            ).reshape(3, 1),

                            np.asarray(
                                tv,
                                dtype=np.float64
                            ).reshape(3, 1)
                        )
                    )

        except cv2.error:
            pass

    # --------------------------------------------
    # ITERATIVE fallback / additional candidate
    # --------------------------------------------

    try:

        ok, rvec, tvec = cv2.solvePnP(
            obj,
            img,
            K,
            D,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if ok:
            candidates.append(
                (
                    rvec.reshape(3, 1),
                    tvec.reshape(3, 1)
                )
            )

    except cv2.error:
        pass

    return candidates


def fit_pnp(img, xy):

    obj = np.column_stack([
        xy,
        np.zeros(len(xy))
    ]).astype(np.float64)

    candidates = pnp_pose_candidates(
        obj,
        img
    )

    if not candidates:
        raise RuntimeError(
            "No valid PnP pose candidate"
        )

    best = None

    for rvec, tvec in candidates:

        R, _ = cv2.Rodrigues(rvec)

        camera_points = (
            (R @ obj.T).T
            +
            tvec.reshape(1, 3)
        )

        # All calibration points must lie
        # in front of the camera.
        if np.any(
            camera_points[:, 2] <= 0
        ):
            continue

        projected, _ = cv2.projectPoints(
            obj,
            rvec,
            tvec,
            K,
            D
        )

        projected = projected.reshape(-1, 2)

        reproj = np.linalg.norm(
            projected - img,
            axis=1
        )

        reproj_rmse = float(
            np.sqrt(
                np.mean(reproj ** 2)
            )
        )

        if (
            best is None
            or reproj_rmse < best[0]
        ):
            best = (
                reproj_rmse,
                R,
                tvec.reshape(3)
            )

    if best is None:
        raise RuntimeError(
            "PnP solutions failed positive-depth check"
        )

    return best[1], best[2], best[0]


def predict_plane_from_pose(
    R,
    t,
    img
):

    # Camera center in board frame.
    camera_center = (
        -R.T @ t
    )

    predicted = []

    for u, v in img:

        ray_camera = (
            K_INV @
            np.array(
                [u, v, 1.0],
                dtype=np.float64
            )
        )

        ray_board = (
            R.T @ ray_camera
        )

        if abs(ray_board[2]) < 1e-12:
            raise RuntimeError(
                "Ray is parallel to board plane"
            )

        lam = (
            -camera_center[2]
            /
            ray_board[2]
        )

        if not np.isfinite(lam):
            raise RuntimeError(
                "Invalid ray-plane intersection"
            )

        if lam <= 0:
            raise RuntimeError(
                "Board intersection lies behind camera"
            )

        point_board = (
            camera_center
            +
            lam * ray_board
        )

        predicted.append([
            point_board[0],
            point_board[1]
        ])

    return np.asarray(
        predicted,
        dtype=np.float64
    )


# ============================================================
# EVALUATE 1800 SUBSETS × 3 MODELS
# ============================================================

trial_results = []

processed = 0

for subset_id in sorted(meta_by_id):

    meta = meta_by_id[subset_id]
    cal_rows = points_by_subset[subset_id]

    n_points = int(meta["n_points"])
    distribution = meta["distribution"]
    trial_index = int(meta["trial_index"])

    if len(cal_rows) != n_points:
        raise RuntimeError(
            f"{subset_id}: expected {n_points} points, "
            f"got {len(cal_rows)}"
        )

    cal_img = image_points(cal_rows)
    cal_xy = board_xy(cal_rows)

    for model in MODELS:

        result = {
            "subset_id": subset_id,
            "n_points": n_points,
            "distribution": distribution,
            "trial_index": trial_index,
            "model": model,

            "spread_score":
                float(meta["spread_score"]),

            "hull_coverage":
                float(meta["hull_coverage"]),

            "mean_pairwise_distance_mm":
                float(
                    meta[
                        "mean_pairwise_distance_mm"
                    ]
                ),

            "valid": 0,
            "failure_reason": "",

            "validation_rmse_mm": "",
            "validation_mae_mm": "",
            "validation_median_mm": "",
            "validation_max_mm": "",

            "calibration_xy_rmse_mm": "",
            "pnp_calibration_reprojection_rmse_px": "",
        }

        try:

            # ========================================
            # AFFINE
            # ========================================

            if model == "Affine":

                coef, cal_rmse = (
                    fit_affine(
                        cal_img,
                        cal_xy
                    )
                )

                pred = predict_affine(
                    coef,
                    VAL_IMG
                )

                metrics = calc_errors(
                    pred,
                    VAL_XY
                )

                result.update(metrics)

                result[
                    "calibration_xy_rmse_mm"
                ] = cal_rmse

            # ========================================
            # HOMOGRAPHY
            # ========================================

            elif model == "Homography":

                H, cal_rmse = (
                    fit_homography(
                        cal_img,
                        cal_xy
                    )
                )

                pred = predict_homography(
                    H,
                    VAL_IMG
                )

                metrics = calc_errors(
                    pred,
                    VAL_XY
                )

                result.update(metrics)

                result[
                    "calibration_xy_rmse_mm"
                ] = cal_rmse

            # ========================================
            # PnP
            # ========================================

            elif model == "PnP":

                R, t, reproj = fit_pnp(
                    cal_img,
                    cal_xy
                )

                pred = predict_plane_from_pose(
                    R,
                    t,
                    VAL_IMG
                )

                metrics = calc_errors(
                    pred,
                    VAL_XY
                )

                result.update(metrics)

                result[
                    "pnp_calibration_reprojection_rmse_px"
                ] = reproj

            else:
                raise RuntimeError(
                    f"Unknown model {model}"
                )

            # Sanity cap only detects numerical explosions.
            # It does NOT remove large but finite errors.
            if (
                float(
                    result[
                        "validation_rmse_mm"
                    ]
                )
                > 1e6
            ):
                raise RuntimeError(
                    "Numerical explosion > 1e6 mm"
                )

            result["valid"] = 1

        except Exception as e:

            result["valid"] = 0
            result["failure_reason"] = (
                type(e).__name__
                + ": "
                + str(e)
            )

        trial_results.append(
            result
        )

    processed += 1

    if processed % 300 == 0:
        print(
            f"Processed {processed}/1800 subsets"
        )


# ============================================================
# HARD COUNT QC
# ============================================================

EXPECTED_RESULTS = (
    1800 * 3
)

if len(trial_results) != EXPECTED_RESULTS:
    raise RuntimeError(
        f"Expected {EXPECTED_RESULTS} model trials, "
        f"got {len(trial_results)}"
    )


# ============================================================
# WRITE TRIAL RESULTS
# ============================================================

with TRIAL_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    fields = list(
        trial_results[0].keys()
    )

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()
    writer.writerows(trial_results)


# ============================================================
# CONDITION SUMMARY
#
# Each condition contains 100 offline subset trials.
# Primary variable:
# held-out validation XY RMSE.
# ============================================================

condition_summary = []

for n_points in POINT_COUNTS:

    for distribution in DISTRIBUTIONS:

        for model in MODELS:

            rr = [
                r for r in trial_results
                if r["n_points"] == n_points
                and r["distribution"] == distribution
                and r["model"] == model
            ]

            if len(rr) != 100:
                raise RuntimeError(
                    f"{n_points}/{distribution}/{model}: "
                    f"expected 100 trials, got {len(rr)}"
                )

            valid = [
                r for r in rr
                if int(r["valid"]) == 1
            ]

            values = np.array([
                float(r["validation_rmse_mm"])
                for r in valid
            ], dtype=float)

            rec = {
                "n_points": n_points,
                "distribution": distribution,
                "model": model,

                "n_trials": len(rr),
                "n_valid": len(valid),
                "n_failed":
                    len(rr) - len(valid),

                "failure_rate":
                    (
                        (len(rr) - len(valid))
                        / len(rr)
                    ),

                "validation_rmse_mean_mm": "",
                "validation_rmse_sd_mm": "",
                "validation_rmse_median_mm": "",
                "validation_rmse_q25_mm": "",
                "validation_rmse_q75_mm": "",
                "validation_rmse_p95_mm": "",
                "validation_rmse_min_mm": "",
                "validation_rmse_max_mm": "",
            }

            if len(values) > 0:

                rec.update({
                    "validation_rmse_mean_mm":
                        float(np.mean(values)),

                    "validation_rmse_sd_mm":
                        float(
                            np.std(
                                values,
                                ddof=1
                            )
                        )
                        if len(values) > 1
                        else 0.0,

                    "validation_rmse_median_mm":
                        float(
                            np.median(values)
                        ),

                    "validation_rmse_q25_mm":
                        float(
                            np.percentile(
                                values,
                                25
                            )
                        ),

                    "validation_rmse_q75_mm":
                        float(
                            np.percentile(
                                values,
                                75
                            )
                        ),

                    "validation_rmse_p95_mm":
                        float(
                            np.percentile(
                                values,
                                95
                            )
                        ),

                    "validation_rmse_min_mm":
                        float(np.min(values)),

                    "validation_rmse_max_mm":
                        float(np.max(values)),
                })

            condition_summary.append(
                rec
            )


# ============================================================
# WRITE SUMMARY
# ============================================================

with SUMMARY_CSV.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    fields = list(
        condition_summary[0].keys()
    )

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()
    writer.writerows(condition_summary)


# ============================================================
# MANIFEST
# ============================================================

manifest = {
    "created_at":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "experiment":
        (
            "E3 calibration-point quantity "
            "and spatial-distribution sensitivity"
        ),

    "camera":
        "ihawk1",

    "models": MODELS,

    "point_counts":
        POINT_COUNTS,

    "distributions":
        DISTRIBUTIONS,

    "subsets_per_condition":
        100,

    "total_calibration_subsets":
        1800,

    "total_model_trials":
        len(trial_results),

    "validation":
        (
            "The same 12 fixed held-out chessboard "
            "points are used for every model and "
            "every calibration subset."
        ),

    "primary_metric":
        (
            "XY RMSE across the 12 fixed held-out "
            "validation points."
        ),

    "affine_method":
        (
            "Least-squares pixel-to-board XY affine "
            "mapping using the selected calibration subset."
        ),

    "homography_method":
        (
            "Projective pixel-to-board XY homography "
            "using the selected calibration subset."
        ),

    "pnp_method":
        (
            "Planar PnP using known ihawk1 intrinsics "
            "and selected board points. Held-out image "
            "rays are transformed into the estimated "
            "board frame and intersected with Z=0."
        ),

    "pixel_input":
        (
            "Median undistorted pixel coordinate from "
            "50 repeated observations per physical "
            "chessboard corner."
        ),

    "statistical_note":
        (
            "The 100 trials within each condition are "
            "offline calibration-subset resamples and "
            "are not independent physical experiments."
        ),

    "failure_policy":
        (
            "Numerical/model fitting failures are retained "
            "and reported through the condition failure "
            "rate. Large finite validation errors are not "
            "removed as outliers."
        ),

    "outputs": {
        "trial_results":
            str(TRIAL_CSV),

        "condition_summary":
            str(SUMMARY_CSV)
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
# TERMINAL SUMMARY
# ============================================================

print()
print("=" * 88)
print("E3 PRIMARY RESULT")
print("Held-out validation XY RMSE: mean ± SD across subset trials")
print("=" * 88)

for model in MODELS:

    print()
    print(model)

    print(
        "N  | Clustered          Random             Spread"
    )

    print("-" * 66)

    for n in POINT_COUNTS:

        cells = {}

        for dist in DISTRIBUTIONS:

            rec = next(
                r for r in condition_summary
                if r["n_points"] == n
                and r["distribution"] == dist
                and r["model"] == model
            )

            if rec["n_valid"] > 0:

                cells[dist] = (
                    f"{float(rec['validation_rmse_mean_mm']):6.3f}"
                    f"±"
                    f"{float(rec['validation_rmse_sd_mm']):6.3f}"
                )

            else:
                cells[dist] = "FAILED"

        print(
            f"{n:2d} | "
            f"{cells['clustered']:18s} "
            f"{cells['random']:18s} "
            f"{cells['spread']}"
        )


# ============================================================
# FAILURES
# ============================================================

print()
print("=" * 88)
print("MODEL FAILURE RATES")
print("=" * 88)

any_failure = False

for rec in condition_summary:

    if rec["n_failed"] > 0:

        any_failure = True

        print(
            f"N={rec['n_points']:2d} "
            f"{rec['distribution']:9s} "
            f"{rec['model']:10s} | "
            f"{rec['n_failed']}/"
            f"{rec['n_trials']} failed"
        )

if not any_failure:
    print("No model-fitting failures.")


# ============================================================
# SIMPLE EFFECT SUMMARY
# ============================================================

print()
print("=" * 88)
print("N=4 -> N=24 CHANGE IN MEAN VALIDATION RMSE")
print("=" * 88)

for model in MODELS:

    print()
    print(model)

    for dist in DISTRIBUTIONS:

        r4 = next(
            r for r in condition_summary
            if r["n_points"] == 4
            and r["distribution"] == dist
            and r["model"] == model
        )

        r24 = next(
            r for r in condition_summary
            if r["n_points"] == 24
            and r["distribution"] == dist
            and r["model"] == model
        )

        if (
            r4["validation_rmse_mean_mm"] != ""
            and
            r24["validation_rmse_mean_mm"] != ""
        ):

            a = float(
                r4[
                    "validation_rmse_mean_mm"
                ]
            )

            b = float(
                r24[
                    "validation_rmse_mean_mm"
                ]
            )

            print(
                f"{dist:9s}: "
                f"{a:.3f} -> {b:.3f} mm "
                f"(Δ={b-a:+.3f} mm)"
            )


print()
print("=" * 88)
print("[PASS] E3-3 MODEL EVALUATION COMPLETE")
print("=" * 88)

print()
print("Trial results:")
print(TRIAL_CSV)

print()
print("Condition summary:")
print(SUMMARY_CSV)

print()
print("Manifest:")
print(MANIFEST_JSON)

