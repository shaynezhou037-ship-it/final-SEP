#!/usr/bin/env python3
"""
Aggregate E0-A formal camera static repeatability runs.

Expected input:
  .../paper/E0/E0_A_camera_static/raw/E0A_formal_<position>_<timestamp>.csv

The script:
1. Finds all formal runs for center/left/right/near/far.
2. Keeps only COMPLETE runs (50 rows for ihawk1 + 50 rows for ihawk2).
3. If multiple complete runs exist for one position, selects the latest timestamp.
4. Produces a summary CSV + JSON + three PNG plots.
"""

import csv
import json
import math
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path("/mnt/c/Users/ASUS/Desktop/paper/E0/E0_A_camera_static")
RAW_DIR = ROOT / "raw"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

POSITIONS = ["center", "left", "right", "near", "far"]
CAMERAS = ["ihawk1", "ihawk2"]
EXPECTED_PER_CAMERA = 50

PATTERN = re.compile(
    r"^E0A_formal_(center|left|right|near|far)_(\d{8}_\d{6})\.csv$"
)


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_complete(rows):
    counts = {cam: 0 for cam in CAMERAS}
    for r in rows:
        cam = r.get("camera_id")
        if cam in counts:
            counts[cam] += 1
    return (
        counts["ihawk1"] == EXPECTED_PER_CAMERA
        and counts["ihawk2"] == EXPECTED_PER_CAMERA
    ), counts


def fvals(rows, key):
    return np.array([float(r[key]) for r in rows], dtype=float)


def sample_sd(x):
    return float(np.std(x, ddof=1)) if len(x) > 1 else 0.0


def stats_for(rows):
    u = fvals(rows, "u_px")
    v = fvals(rows, "v_px")
    d = fvals(rows, "depth_median_raw")
    x = fvals(rows, "x_cam_raw")
    y = fvals(rows, "y_cam_raw")
    z = fvals(rows, "z_cam_raw")
    valid = fvals(rows, "depth_valid_ratio")
    dt = fvals(rows, "color_depth_dt_ms")

    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    radial = np.sqrt((x - x_mean) ** 2 + (y - y_mean) ** 2)

    return {
        "n": len(rows),
        "u_mean_px": float(np.mean(u)),
        "u_sd_px": sample_sd(u),
        "v_mean_px": float(np.mean(v)),
        "v_sd_px": sample_sd(v),
        "depth_mean_raw": float(np.mean(d)),
        "depth_sd_raw": sample_sd(d),
        "x_mean_raw": x_mean,
        "x_sd_raw": sample_sd(x),
        "y_mean_raw": y_mean,
        "y_sd_raw": sample_sd(y),
        "z_mean_raw": float(np.mean(z)),
        "z_sd_raw": sample_sd(z),
        "xy_radial_mean_raw": float(np.mean(radial)),
        "xy_radial_p95_raw": float(np.percentile(radial, 95)),
        "xy_radial_max_raw": float(np.max(radial)),
        "depth_valid_ratio_mean": float(np.mean(valid)),
        "rgb_depth_dt_mean_ms": float(np.mean(dt)),
        "rgb_depth_dt_p95_ms": float(np.percentile(dt, 95)),
    }


# Discover complete runs
candidates = {pos: [] for pos in POSITIONS}

for path in RAW_DIR.glob("E0A_formal_*.csv"):
    m = PATTERN.match(path.name)
    if not m:
        continue

    pos, stamp = m.group(1), m.group(2)
    rows = read_csv(path)
    complete, counts = is_complete(rows)

    candidates[pos].append(
        {
            "path": path,
            "stamp": stamp,
            "complete": complete,
            "counts": counts,
            "rows": rows,
        }
    )

selected = {}

for pos in POSITIONS:
    complete_runs = [r for r in candidates[pos] if r["complete"]]

    if not complete_runs:
        print(f"[ERROR] No complete formal run found for position: {pos}")
        if candidates[pos]:
            for r in sorted(candidates[pos], key=lambda x: x["stamp"]):
                print(
                    f"  incomplete: {r['path'].name} "
                    f"counts={r['counts']}"
                )
        raise SystemExit(2)

    complete_runs.sort(key=lambda x: x["stamp"])
    selected[pos] = complete_runs[-1]

    print(
        f"[SELECT] {pos:>6}: "
        f"{selected[pos]['path'].name}"
    )

# Build summary
summary_rows = []
summary_json = {
    "experiment": "E0-A Camera Static Repeatability",
    "selection_rule": (
        "latest complete formal run per position; "
        "complete = 50 ihawk1 + 50 ihawk2 rows"
    ),
    "selected_runs": {},
    "results": {},
}

for pos in POSITIONS:
    run = selected[pos]
    summary_json["selected_runs"][pos] = str(run["path"])
    summary_json["results"][pos] = {}

    for cam in CAMERAS:
        sub = [r for r in run["rows"] if r["camera_id"] == cam]
        s = stats_for(sub)
        summary_json["results"][pos][cam] = s

        summary_rows.append(
            {
                "position": pos,
                "camera_id": cam,
                "source_csv": run["path"].name,
                **s,
            }
        )

# Overall audit metrics
all_xy_p95 = [r["xy_radial_p95_raw"] for r in summary_rows]
all_valid = [r["depth_valid_ratio_mean"] for r in summary_rows]

summary_json["overall"] = {
    "positions": len(POSITIONS),
    "cameras": len(CAMERAS),
    "total_observations": len(POSITIONS) * len(CAMERAS) * EXPECTED_PER_CAMERA,
    "worst_xy_radial_p95_raw": float(max(all_xy_p95)),
    "median_xy_radial_p95_raw": float(np.median(all_xy_p95)),
    "minimum_mean_depth_valid_ratio": float(min(all_valid)),
}

# Write summary CSV
csv_out = RESULTS_DIR / "E0A_formal_5position_summary.csv"
fieldnames = list(summary_rows[0].keys())

with csv_out.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summary_rows)

# Write JSON
json_out = RESULTS_DIR / "E0A_formal_5position_summary.json"
with json_out.open("w", encoding="utf-8") as f:
    json.dump(summary_json, f, indent=2)

# Console table
print("\n=== E0-A FORMAL SUMMARY ===")
print(
    f"{'Position':<8} {'Camera':<7} "
    f"{'uSD(px)':>9} {'vSD(px)':>9} "
    f"{'DepthSD':>9} {'XY_P95':>9} "
    f"{'Valid':>8}"
)

for r in summary_rows:
    print(
        f"{r['position']:<8} {r['camera_id']:<7} "
        f"{r['u_sd_px']:>9.4f} "
        f"{r['v_sd_px']:>9.4f} "
        f"{r['depth_sd_raw']:>9.4f} "
        f"{r['xy_radial_p95_raw']:>9.4f} "
        f"{r['depth_valid_ratio_mean']:>8.3f}"
    )

print("\n=== OVERALL ===")
for k, v in summary_json["overall"].items():
    print(f"{k}: {v}")

# Plots
xpos = np.arange(len(POSITIONS))
width = 0.36

def values(cam, key):
    out = []
    for pos in POSITIONS:
        row = next(
            r for r in summary_rows
            if r["position"] == pos and r["camera_id"] == cam
        )
        out.append(row[key])
    return out

# 1. XY radial P95
plt.figure(figsize=(9, 5))
plt.bar(xpos - width/2, values("ihawk1", "xy_radial_p95_raw"),
        width, label="ihawk1")
plt.bar(xpos + width/2, values("ihawk2", "xy_radial_p95_raw"),
        width, label="ihawk2")
plt.xticks(xpos, POSITIONS)
plt.ylabel("XY radial P95 (raw depth unit)")
plt.xlabel("Workspace position")
plt.title("E0-A Static XY Repeatability")
plt.legend()
plt.tight_layout()
xy_plot = RESULTS_DIR / "E0A_xy_radial_p95_by_position.png"
plt.savefig(xy_plot, dpi=180)
plt.close()

# 2. Depth SD
plt.figure(figsize=(9, 5))
plt.bar(xpos - width/2, values("ihawk1", "depth_sd_raw"),
        width, label="ihawk1")
plt.bar(xpos + width/2, values("ihawk2", "depth_sd_raw"),
        width, label="ihawk2")
plt.xticks(xpos, POSITIONS)
plt.ylabel("Depth SD (raw depth unit)")
plt.xlabel("Workspace position")
plt.title("E0-A Depth Repeatability")
plt.legend()
plt.tight_layout()
depth_plot = RESULTS_DIR / "E0A_depth_sd_by_position.png"
plt.savefig(depth_plot, dpi=180)
plt.close()

# 3. Valid-depth ratio
plt.figure(figsize=(9, 5))
plt.bar(xpos - width/2, values("ihawk1", "depth_valid_ratio_mean"),
        width, label="ihawk1")
plt.bar(xpos + width/2, values("ihawk2", "depth_valid_ratio_mean"),
        width, label="ihawk2")
plt.xticks(xpos, POSITIONS)
plt.ylim(0, 1.05)
plt.ylabel("Mean valid-depth ratio")
plt.xlabel("Workspace position")
plt.title("E0-A Depth Validity")
plt.legend()
plt.tight_layout()
valid_plot = RESULTS_DIR / "E0A_depth_valid_ratio_by_position.png"
plt.savefig(valid_plot, dpi=180)
plt.close()

print("\nSaved:")
print(" ", csv_out)
print(" ", json_out)
print(" ", xy_plot)
print(" ", depth_plot)
print(" ", valid_plot)
