#!/usr/bin/env python3

from pathlib import Path
import csv
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

ROOT = Path(
    "/mnt/c/Users/ASUS/Desktop/paper/E2/E2_rebuilt"
)

MODEL_DIR = ROOT / "model_comparison"

SUMMARY_CSV = MODEL_DIR / "E2_height_summary.csv"
RUN_CSV = MODEL_DIR / "E2_run_height_metrics.csv"

OUT = ROOT / "figure_draft"
OUT.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOAD
# ============================================================

with SUMMARY_CSV.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as f:
    summary = list(csv.DictReader(f))

with RUN_CSV.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as f:
    run_rows = list(csv.DictReader(f))


CAMERAS = ["ihawk1", "ihawk2"]
MODELS = ["Affine", "Homography", "PnP"]
HEIGHTS = np.arange(0, 51, 5)


# ============================================================
# COMMON FORMAT
# ============================================================

def finish(ax):

    ax.set_xlabel("Target height above calibration plane (mm)")
    ax.grid(True, alpha=0.25)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.tick_params(direction="out")

    plt.tight_layout()


def save(fig, basename):

    png = OUT / f"{basename}.png"
    pdf = OUT / f"{basename}.pdf"

    fig.savefig(
        png,
        dpi=300,
        bbox_inches="tight"
    )

    fig.savefig(
        pdf,
        bbox_inches="tight"
    )

    plt.close(fig)

    print("[SAVED]", png)
    print("[SAVED]", pdf)


# ============================================================
# FIGURE 1
# XY RMSE vs HEIGHT
# mean ± SD across 5 independent rebuilds
# ============================================================

for cam in CAMERAS:

    fig, ax = plt.subplots(figsize=(7.2, 4.8))

    for model in MODELS:

        rr = sorted(
            [
                r for r in summary
                if r["camera_id"] == cam
                and r["model"] == model
            ],
            key=lambda r: float(r["height_gt_mm"])
        )

        x = np.array([
            float(r["height_gt_mm"])
            for r in rr
        ])

        y = np.array([
            float(r["xy_rmse_mean_mm"])
            for r in rr
        ])

        sd = np.array([
            float(r["xy_rmse_sd_mm"])
            for r in rr
        ])

        ax.errorbar(
            x,
            y,
            yerr=sd,
            marker="o",
            capsize=3,
            linewidth=1.6,
            label=model
        )

    ax.set_ylabel("XY localization RMSE (mm)")

    ax.set_title(
        f"E2 — Off-plane localization accuracy ({cam})"
    )

    ax.legend(frameon=False)

    finish(ax)

    save(
        fig,
        f"Fig_E2_1_XY_RMSE_vs_height_{cam}"
    )


# ============================================================
# FIGURE 2
# ΔXY RMSE RELATIVE TO Z=0
#
# IMPORTANT:
# Compute delta PER RUN first:
#
# delta(run,z) = RMSE(run,z) - RMSE(run,0)
#
# Then calculate mean ± SD across five runs.
# ============================================================

for cam in CAMERAS:

    fig, ax = plt.subplots(figsize=(7.2, 4.8))

    for model in MODELS:

        by_run = defaultdict(dict)

        for r in run_rows:

            if (
                r["camera_id"] == cam
                and r["model"] == model
            ):

                run = r["run_id"]
                z = float(r["height_gt_mm"])

                by_run[run][z] = float(
                    r["xy_rmse_mm"]
                )

        delta_mean = []
        delta_sd = []

        for z in HEIGHTS:

            deltas = []

            for run, values in by_run.items():

                if 0.0 not in values or z not in values:
                    raise RuntimeError(
                        f"Missing {run}/{cam}/{model}/Z={z}"
                    )

                deltas.append(
                    values[z] - values[0.0]
                )

            delta_mean.append(
                np.mean(deltas)
            )

            delta_sd.append(
                np.std(deltas, ddof=1)
            )

        ax.errorbar(
            HEIGHTS,
            delta_mean,
            yerr=delta_sd,
            marker="o",
            capsize=3,
            linewidth=1.6,
            label=model
        )

    ax.axhline(
        0,
        linewidth=1,
        linestyle="--"
    )

    ax.set_ylabel(
        "Increase in XY RMSE from Z=0 (mm)"
    )

    ax.set_title(
        f"E2 — Off-plane degradation ({cam})"
    )

    ax.legend(frameon=False)

    finish(ax)

    save(
        fig,
        f"Fig_E2_2_Delta_XY_RMSE_{cam}"
    )


# ============================================================
# FIGURE 3
# PnP XY / Z / 3D RMSE
# ============================================================

for cam in CAMERAS:

    rr = sorted(
        [
            r for r in summary
            if r["camera_id"] == cam
            and r["model"] == "PnP"
        ],
        key=lambda r: float(r["height_gt_mm"])
    )

    x = np.array([
        float(r["height_gt_mm"])
        for r in rr
    ])

    xy = np.array([
        float(r["xy_rmse_mean_mm"])
        for r in rr
    ])

    xy_sd = np.array([
        float(r["xy_rmse_sd_mm"])
        for r in rr
    ])

    z = np.array([
        float(r["pnp_z_rmse_mean_mm"])
        for r in rr
    ])

    z_sd = np.array([
        float(r["pnp_z_rmse_sd_mm"])
        for r in rr
    ])

    d3 = np.array([
        float(r["pnp_3d_rmse_mean_mm"])
        for r in rr
    ])

    d3_sd = np.array([
        float(r["pnp_3d_rmse_sd_mm"])
        for r in rr
    ])

    fig, ax = plt.subplots(figsize=(7.2, 4.8))

    ax.errorbar(
        x,
        xy,
        yerr=xy_sd,
        marker="o",
        capsize=3,
        label="XY RMSE"
    )

    ax.errorbar(
        x,
        z,
        yerr=z_sd,
        marker="s",
        capsize=3,
        label="Z RMSE"
    )

    ax.errorbar(
        x,
        d3,
        yerr=d3_sd,
        marker="^",
        capsize=3,
        label="3D RMSE"
    )

    ax.set_ylabel("Localization RMSE (mm)")

    ax.set_title(
        f"E2 — PnP 3D localization performance ({cam})"
    )

    ax.legend(frameon=False)

    finish(ax)

    save(
        fig,
        f"Fig_E2_3_PnP_XY_Z_3D_{cam}"
    )


# ============================================================
# FIGURE 4
# PnP FIVE INDEPENDENT REBUILD TRAJECTORIES
# ============================================================

for cam in CAMERAS:

    fig, ax = plt.subplots(figsize=(7.2, 4.8))

    runs = sorted(
        set(
            r["run_id"]
            for r in run_rows
            if r["camera_id"] == cam
        )
    )

    for run in runs:

        rr = sorted(
            [
                r for r in run_rows
                if r["camera_id"] == cam
                and r["model"] == "PnP"
                and r["run_id"] == run
            ],
            key=lambda r: float(r["height_gt_mm"])
        )

        x = [
            float(r["height_gt_mm"])
            for r in rr
        ]

        y = [
            float(r["xy_rmse_mm"])
            for r in rr
        ]

        ax.plot(
            x,
            y,
            marker="o",
            linewidth=1.2,
            label=run[-6:]
        )

    ax.set_ylabel("PnP XY RMSE (mm)")

    ax.set_title(
        f"E2 — PnP rebuild variability ({cam})"
    )

    ax.legend(
        title="Run",
        frameon=False,
        fontsize=8
    )

    finish(ax)

    save(
        fig,
        f"Fig_E2_4_PnP_rebuilds_{cam}"
    )


# ============================================================
# DONE
# ============================================================

print()
print("=" * 72)
print("[PASS] E2 FIGURE GENERATION COMPLETE")
print("=" * 72)
print("Output directory:")
print(OUT)

