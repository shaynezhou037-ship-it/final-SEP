#!/usr/bin/env python3

# ================================================================
# FINAL ANALYSIS LABEL
#
# E0-B — Robot Feedback vs Physical Endpoint Consistency
#
# Analysis:
# physical needle-paper displacement
# versus
# RoArm T105 Cartesian feedback displacement
#
# Main outputs:
# - axis correspondence
# - Pearson correlation
# - MAE
# - RMSE
# - residual error
#
# No causal explanation of the endpoint deviation is assumed.
# ================================================================

# -*- coding: utf-8 -*-

"""
Reclassify and re-analyse E0-B endpoint data without assigning a causal
interpretation to the varied-start protocol.

Input:
  E0B_robot_repeatability_20trials_20260807_204040.csv

Output folder:
  E0_B_endpoint_deviation_crosscheck/

Outputs:
  raw/      copied source CSV
  results/  trial-level crosscheck CSV + summary JSON
  docs/     README.md
  scripts/  copied acquisition script, if supplied

Core comparison:
  physical/manual displacement on paper
  versus
  RoArm T105 final-feedback displacement relative to Trial 1.

Candidate paper/robot axis mapping observed in this setup:
  paper X  ~ +robot Y
  paper Y  ~ -robot X
  paper Z  ~ +robot Z

The script reports correlations and errors, but does NOT conclude that the
observed deviations were caused by starting configuration.
"""

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from statistics import mean

import numpy as np


def f_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return float(s)


def pearson(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def metrics(actual, predicted):
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    e = a - p
    return {
        "n": int(len(a)),
        "pearson_r": pearson(a, p),
        "mae_mm": float(np.mean(np.abs(e))),
        "rmse_mm": float(np.sqrt(np.mean(e ** 2))),
        "bias_actual_minus_feedback_mm": float(np.mean(e)),
        "max_abs_error_mm": float(np.max(np.abs(e))),
    }


def linear_fit(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2 or np.std(x) == 0:
        return None
    A = np.column_stack([x, np.ones(len(x))])
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    pred = slope * x + intercept
    resid = y - pred
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return {
        "slope": float(slope),
        "intercept_mm": float(intercept),
        "r_squared": None if ss_tot == 0 else float(1 - ss_res / ss_tot),
        "residual_mae_mm": float(np.mean(np.abs(resid))),
        "residual_rmse_mm": float(np.sqrt(np.mean(resid ** 2))),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--script", default="")
    ap.add_argument(
        "--output-root",
        required=True,
    )
    args = ap.parse_args()

    src = Path(args.csv)
    out = Path(args.output_root)

    raw_dir = out / "raw"
    results_dir = out / "results"
    docs_dir = out / "docs"
    scripts_dir = out / "scripts"

    for d in (raw_dir, results_dir, docs_dir, scripts_dir):
        d.mkdir(parents=True, exist_ok=True)

    copied_csv = raw_dir / src.name
    shutil.copy2(src, copied_csv)

    if args.script:
        sp = Path(args.script)
        if sp.exists():
            shutil.copy2(
                sp,
                scripts_dir / "e0b_endpoint_deviation_acquisition.py",
            )

    with src.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise RuntimeError("CSV has no rows.")

    b = rows[0]
    bx = float(b["final_feedback_x_mm"])
    by = float(b["final_feedback_y_mm"])
    bz = float(b["final_feedback_z_mm"])

    processed = []

    for r in rows:
        fx = float(r["final_feedback_x_mm"])
        fy = float(r["final_feedback_y_mm"])
        fz = float(r["final_feedback_z_mm"])

        robot_dx = fx - bx
        robot_dy = fy - by
        robot_dz = fz - bz

        # Candidate mapping from robot frame into the physical/paper axes.
        # This is recorded as an observed axis correspondence, not as a
        # causal model.
        robot_as_physical_x = robot_dy
        robot_as_physical_y = -robot_dx
        robot_as_physical_z = robot_dz

        mx = f_or_none(r.get("manual_dx_mm"))
        my = f_or_none(r.get("manual_dy_mm"))
        mz = f_or_none(r.get("manual_dz_mm"))

        px_err = None if mx is None else mx - robot_as_physical_x
        py_err = None if my is None else my - robot_as_physical_y
        pz_err = None if mz is None else mz - robot_as_physical_z

        residual_3d = None
        if px_err is not None and py_err is not None and pz_err is not None:
            residual_3d = math.sqrt(
                px_err ** 2 + py_err ** 2 + pz_err ** 2
            )

        processed.append({
            "trial_index": int(r["trial_index"]),
            "measurement_class": r.get("measurement_class", ""),
            "physical_x_mm": mx,
            "physical_y_mm": my,
            "physical_z_mm": mz,
            "robot_feedback_dx_mm": robot_dx,
            "robot_feedback_dy_mm": robot_dy,
            "robot_feedback_dz_mm": robot_dz,
            "robot_mapped_to_physical_x_mm": robot_as_physical_x,
            "robot_mapped_to_physical_y_mm": robot_as_physical_y,
            "robot_mapped_to_physical_z_mm": robot_as_physical_z,
            "physical_minus_robot_x_mm": px_err,
            "physical_minus_robot_y_mm": py_err,
            "physical_minus_robot_z_mm": pz_err,
            "residual_3d_mm": residual_3d,
            "final_tracking_error_mm": f_or_none(
                r.get("final_tracking_error_mm")
            ),
            "random_base_rad": f_or_none(r.get("random_base_rad")),
            "random_shoulder_rad": f_or_none(r.get("random_shoulder_rad")),
            "random_elbow_rad": f_or_none(r.get("random_elbow_rad")),
            "random_wrist_rad": f_or_none(r.get("random_wrist_rad")),
            "random_roll_rad": f_or_none(r.get("random_roll_rad")),
            "notes": r.get("notes", ""),
        })

    # Exclude Trial 1 baseline and below-resolution rows from continuous
    # physical-vs-feedback correlation/error calculations.
    measurable = [
        r for r in processed
        if r["trial_index"] != 1
        and r["physical_x_mm"] is not None
        and r["physical_y_mm"] is not None
        and r["physical_z_mm"] is not None
    ]

    # Full correlation matrix: physical axes vs raw robot-feedback axes.
    corr_matrix = {}
    phys_axes = {
        "physical_x": [r["physical_x_mm"] for r in measurable],
        "physical_y": [r["physical_y_mm"] for r in measurable],
        "physical_z": [r["physical_z_mm"] for r in measurable],
    }
    robot_axes = {
        "robot_dx": [r["robot_feedback_dx_mm"] for r in measurable],
        "robot_dy": [r["robot_feedback_dy_mm"] for r in measurable],
        "robot_dz": [r["robot_feedback_dz_mm"] for r in measurable],
    }

    for pn, pv in phys_axes.items():
        corr_matrix[pn] = {}
        for rn, rv in robot_axes.items():
            corr_matrix[pn][rn] = pearson(pv, rv)

    x_actual = [r["physical_x_mm"] for r in measurable]
    y_actual = [r["physical_y_mm"] for r in measurable]
    z_actual = [r["physical_z_mm"] for r in measurable]

    x_robot = [
        r["robot_mapped_to_physical_x_mm"] for r in measurable
    ]
    y_robot = [
        r["robot_mapped_to_physical_y_mm"] for r in measurable
    ]
    z_robot = [
        r["robot_mapped_to_physical_z_mm"] for r in measurable
    ]

    x_metrics = metrics(x_actual, x_robot)
    y_metrics = metrics(y_actual, y_robot)
    z_metrics = metrics(z_actual, z_robot)

    residuals = [
        r["residual_3d_mm"]
        for r in measurable
        if r["residual_3d_mm"] is not None
    ]

    manual_radial = [
        math.hypot(r["physical_x_mm"], r["physical_y_mm"])
        for r in measurable
    ]
    robot_radial = [
        math.hypot(
            r["robot_mapped_to_physical_x_mm"],
            r["robot_mapped_to_physical_y_mm"],
        )
        for r in measurable
    ]

    summary = {
        "classification": {
            "experiment_id": "E0-B",
            "name": "Robot endpoint deviation / physical-feedback cross-check",
            "protocol_note": (
                "The acquisition protocol used varied high joint-space starts "
                "before returning to the same frozen Cartesian target."
            ),
            "causal_interpretation": (
                "No causal attribution is made here. The dataset is classified "
                "by what was directly measured: endpoint deviation and agreement "
                "between physical observation and T105 feedback."
            ),
        },
        "n_total_arrivals": len(processed),
        "n_comparison_arrivals": max(0, len(processed) - 1),
        "n_measurable_physical_rows_used_for_continuous_analysis": len(measurable),
        "candidate_axis_mapping": {
            "physical_x": "+robot_feedback_delta_y",
            "physical_y": "-robot_feedback_delta_x",
            "physical_z": "+robot_feedback_delta_z",
            "note": (
                "This mapping is strongly suggested by the observed data and "
                "should be physically verified before being treated as a formal "
                "coordinate-frame definition."
            ),
        },
        "correlation_matrix_physical_vs_raw_robot_feedback": corr_matrix,
        "mapped_axis_agreement": {
            "physical_x_vs_mapped_robot_x": x_metrics,
            "physical_y_vs_mapped_robot_y": y_metrics,
            "physical_z_vs_mapped_robot_z": z_metrics,
            "note_z": (
                "Physical/manual Z is constant at 0 in the measurable rows, "
                "so Pearson correlation for Z is undefined. The Z error metrics "
                "only indicate that robot-feedback Z deviations remained small "
                "relative to the ~1 mm manual resolution."
            ),
        },
        "xy_radial_agreement": metrics(manual_radial, robot_radial),
        "mapped_3d_residual": {
            "mean_residual_norm_mm": (
                float(np.mean(residuals)) if residuals else None
            ),
            "rms_residual_norm_mm": (
                float(np.sqrt(np.mean(np.asarray(residuals) ** 2)))
                if residuals else None
            ),
            "max_residual_norm_mm": (
                float(np.max(residuals)) if residuals else None
            ),
            "caution": (
                "The 3-D residual includes threshold-limited manual Y/Z readings "
                "and should not be interpreted as sub-mm ground-truth accuracy."
            ),
        },
        "diagnostic_linear_fit": {
            "physical_x_from_robot_dy": linear_fit(
                robot_axes["robot_dy"],
                x_actual,
            ),
            "physical_y_from_minus_robot_dx": linear_fit(
                [-v for v in robot_axes["robot_dx"]],
                y_actual,
            ),
            "note": (
                "Linear fits are diagnostic only; do not use them to redefine "
                "the ground-truth measurement."
            ),
        },
    }

    trial_csv = results_dir / "E0B_endpoint_physical_vs_feedback_trials.csv"
    fields = list(processed[0].keys())
    with trial_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(processed)

    summary_json = results_dir / "E0B_endpoint_physical_vs_feedback_summary.json"
    summary_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    readme = f"""# E0-B — Robot Endpoint Deviation / Physical–Feedback Cross-check

## What this dataset directly contains

This run contains 20 endpoint arrivals to the same frozen Cartesian target.

The acquisition protocol included different constrained high joint-space
starting poses. That is recorded as a protocol condition only. This archive
does **not** assign the observed endpoint deviations to a specific cause.

## Primary question for this re-analysis

Do the physically observed needle-paper endpoint displacements agree with the
RoArm T105 endpoint-feedback displacements?

## Candidate observed axis correspondence

- physical/paper X ≈ + robot feedback ΔY
- physical/paper Y ≈ - robot feedback ΔX
- physical/paper Z ≈ + robot feedback ΔZ

This correspondence should be physically checked before it is treated as a
formal coordinate-frame definition.

## Main analysis outputs

See:

- `results/E0B_endpoint_physical_vs_feedback_trials.csv`
- `results/E0B_endpoint_physical_vs_feedback_summary.json`

Continuous correlation/error statistics exclude the Trial-1 baseline and rows
whose physical displacement was only classified as below the ~1 mm manual
measurement resolution.

No causal interpretation is imposed by this archive.
"""
    (docs_dir / "README.md").write_text(readme, encoding="utf-8")

    print("============================================================")
    print("E0-B PHYSICAL vs ROBOT-FEEDBACK RE-ANALYSIS")
    print("============================================================")
    print(f"total arrivals                : {len(processed)}")
    print(f"measurable rows used          : {len(measurable)}")
    print()
    print("Candidate mapping:")
    print("  physical X <- + robot ΔY")
    print("  physical Y <- - robot ΔX")
    print("  physical Z <- + robot ΔZ")
    print()
    print("Mapped-axis agreement:")
    for name, m in [
        ("X", x_metrics),
        ("Y", y_metrics),
        ("Z", z_metrics),
    ]:
        r = m["pearson_r"]
        rtxt = "undefined" if r is None else f"{r:.4f}"
        print(
            f"  {name}: r={rtxt}, "
            f"MAE={m['mae_mm']:.3f} mm, "
            f"RMSE={m['rmse_mm']:.3f} mm, "
            f"max={m['max_abs_error_mm']:.3f} mm"
        )

    rm = summary["xy_radial_agreement"]
    print()
    print(
        f"XY radial: r={rm['pearson_r']:.4f}, "
        f"MAE={rm['mae_mm']:.3f} mm, "
        f"RMSE={rm['rmse_mm']:.3f} mm"
    )

    r3 = summary["mapped_3d_residual"]
    print(
        f"Mapped 3D residual norm mean/rms/max: "
        f"{r3['mean_residual_norm_mm']:.3f} / "
        f"{r3['rms_residual_norm_mm']:.3f} / "
        f"{r3['max_residual_norm_mm']:.3f} mm"
    )
    print()
    print("Saved:")
    print(f"  {trial_csv}")
    print(f"  {summary_json}")
    print(f"  {docs_dir / 'README.md'}")


if __name__ == "__main__":
    main()
