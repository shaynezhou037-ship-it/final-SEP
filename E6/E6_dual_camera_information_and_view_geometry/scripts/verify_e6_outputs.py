#!/usr/bin/env python3
"""Verify E6 output cardinality, JSON validity, and headline invariants."""

from pathlib import Path
import csv
import json


SCRIPT = Path(__file__).resolve()
EXP_ROOT = SCRIPT.parents[1]
RESULTS = EXP_ROOT / "results"
FIGURES = EXP_ROOT / "figures"

EXPECTED_ROWS = {
    "E6_leave_one_rebuild_weight_audit.csv": 15,
    "E6_fusion_predictions.csv": 4125,
    "E6_fusion_run_height_metrics.csv": 825,
    "E6_fusion_height_summary.csv": 165,
    "E6_fusion_gain_summary.csv": 99,
    "E6_stereo_predictions.csv": 275,
    "E6_stereo_run_height_metrics.csv": 55,
    "E6_stereo_height_summary.csv": 11,
    "E6_camera_geometry.csv": 10,
    "E6_pair_geometry.csv": 55,
    "E6_angle_error_associations.csv": 44,
}


def load(name):
    with (RESULTS / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    for name, expected in EXPECTED_ROWS.items():
        actual = len(load(name))
        if actual != expected:
            raise RuntimeError(f"{name}: expected {expected}, got {actual}")
    for name in ("E6_summary.json", "E6_manifest.json", "E6_angle_identifiability_audit.json"):
        json.loads((RESULTS / name).read_text(encoding="utf-8"))
    angle_audit = json.loads(
        (RESULTS / "E6_angle_identifiability_audit.json").read_text(encoding="utf-8")
    )
    if angle_audit["verdict"] != "not_identifiable_from_current_E6":
        raise RuntimeError("Angle identifiability verdict changed unexpectedly")
    if angle_audit["effective_fixed_camera_placements"] != 2:
        raise RuntimeError("Angle audit must retain two fixed placements")
    if angle_audit["causal_angle_levels"] != 0:
        raise RuntimeError("Current E6 must not claim a controlled angle level")
    angle_md = RESULTS / "E6_ANGLE_IDENTIFIABILITY_AUDIT.md"
    if not angle_md.exists() or angle_md.stat().st_size == 0:
        raise RuntimeError("Missing angle-identifiability audit note")
    stereo = load("E6_stereo_height_summary.csv")
    at25 = next(row for row in stereo if float(row["height_gt_mm"]) == 25.0)
    if float(at25["xy_rmse_mean_mm"]) >= 4.0:
        raise RuntimeError("Stereo 25-mm headline invariant failed")
    fusion = load("E6_fusion_height_summary.csv")
    pnp25 = {
        row["source"]: float(row["xy_rmse_mean_mm"])
        for row in fusion
        if row["model"] == "PnP" and float(row["height_gt_mm"]) == 25.0
    }
    if not (pnp25["ihawk2"] < pnp25["LOOWeightedFusion"] < pnp25["EqualFusion"] < pnp25["ihawk1"]):
        raise RuntimeError("PnP fusion ordering invariant failed")
    expected_stems = {
        "Fig_E6_1_information_flow",
        "Fig_E6_2_fusion_accuracy",
        "Fig_E6_3_stereo_comparison",
        "Fig_E6_4_view_geometry",
    }
    for stem in expected_stems:
        for suffix in (".png", ".pdf"):
            path = FIGURES / f"{stem}{suffix}"
            if not path.exists() or path.stat().st_size == 0:
                raise RuntimeError(f"Missing figure: {path}")
    print("E6 output verification PASS")


if __name__ == "__main__":
    main()
