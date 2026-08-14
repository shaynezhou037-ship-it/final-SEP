#!/usr/bin/env python3
"""Structural and headline-invariant checks for E5 derived outputs."""

from pathlib import Path
import csv
import json


SCRIPT = Path(__file__).resolve()
EXP_ROOT = SCRIPT.parents[1]
RESULTS = EXP_ROOT / "results"
FIGURES = EXP_ROOT / "figures"

EXPECTED_CSV_ROWS = {
    "E5_preflight_qc.csv": 330,
    "E5_detection_observations.csv": 8250,
    "E5_image_latency.csv": 1650,
    "E5_predictions.csv": 8250,
    "E5_run_height_metrics.csv": 1650,
    "E5_height_summary.csv": 330,
    "E5_latency_summary.csv": 30,
    "E5_feasibility_by_height.csv": 990,
    "E5_feasibility_summary.csv": 90,
}


def load_csv(name: str) -> list[dict]:
    with (RESULTS / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    for name, expected in EXPECTED_CSV_ROWS.items():
        actual = len(load_csv(name))
        if actual != expected:
            raise RuntimeError(f"{name}: expected {expected} rows, got {actual}")

    for name in ("E5_calibrations.json", "E5_summary.json", "E5_manifest.json"):
        json.loads((RESULTS / name).read_text(encoding="utf-8"))

    excluded = [
        row for row in load_csv("E5_preflight_qc.csv")
        if row["qc_excluded"] == "1"
    ]
    exclusion_keys = {
        (row["run_id"], row["camera_id"], row["height_gt_mm"], row["frame_index"])
        for row in excluded
    }
    expected_exclusions = {
        ("20260808_141232", camera, "30.0", str(frame))
        for camera in ("ihawk1", "ihawk2")
        for frame in (1, 2, 3)
    }
    if exclusion_keys != expected_exclusions:
        raise RuntimeError(f"Unexpected QC exclusions: {sorted(exclusion_keys)}")

    detection = load_csv("E5_detection_summary.csv")
    native = [
        row for row in detection
        if row["resolution_id"] == "r640x400" and row["height_gt_mm"] == "ALL"
    ]
    if len(native) != 2 or any(float(row["marker_detection_rate"]) != 1.0 for row in native):
        raise RuntimeError("Native detection invariant failed")

    latency = load_csv("E5_latency_summary.csv")
    native_latency = [row for row in latency if row["resolution_id"] == "r640x400"]
    if len(native_latency) != 6 or max(float(row["pipeline_latency_p95_ms"]) for row in native_latency) >= 33.3:
        raise RuntimeError("Native 30 Hz latency-gate invariant failed")

    expected_figure_stems = {
        "Fig_E5_1_detection_ihawk1",
        "Fig_E5_1_detection_ihawk2",
        "Fig_E5_2_stability",
        "Fig_E5_3_accuracy_ihawk1",
        "Fig_E5_3_accuracy_ihawk2",
        "Fig_E5_4_latency_ihawk1",
        "Fig_E5_4_latency_ihawk2",
        "Fig_E5_5_standard_feasibility",
    }
    for stem in expected_figure_stems:
        for suffix in (".png", ".pdf"):
            path = FIGURES / f"{stem}{suffix}"
            if not path.exists() or path.stat().st_size == 0:
                raise RuntimeError(f"Missing/empty figure: {path}")

    print("E5 output verification PASS")
    print(f"Checked {len(EXPECTED_CSV_ROWS)} row-count invariants, 3 JSON files, QC exclusions, headline gates, and 16 figures.")


if __name__ == "__main__":
    main()
