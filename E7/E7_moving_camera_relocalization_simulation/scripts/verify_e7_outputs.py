#!/usr/bin/env python3
"""Structural and headline verification for E7 outputs."""

from pathlib import Path
import csv
import json
import math


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"


def read_csv(name: str) -> list[dict]:
    with (RESULTS / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    config = read_csv("E7_configuration_metrics.csv")
    overall = read_csv("E7_overall_summary.csv")
    envelope = read_csv("E7_operating_envelope.csv")
    assert len(config) == 2400, len(config)
    assert len(overall) == 240, len(overall)
    assert len(envelope) == 180, len(envelope)
    assert (RESULTS / "E7_RESULTS_SUMMARY.md").stat().st_size > 1000
    manifest = json.loads((RESULTS / "E7_manifest.json").read_text(encoding="utf-8"))
    assert manifest["random_seed"] == 20260814
    assert manifest["detector_failure_model"].startswith("none")

    index = {
        (row["motion_scenario"], float(row["pixel_noise_sigma_px"]),
         float(row["height_gt_mm"]), row["method"]): row
        for row in overall
    }
    def value(scenario, height, method, field="xy_rmse_mm"):
        return float(index[(scenario, 0.5, height, method)][field])

    # A moved camera invalidates frozen calibration; current visual evidence must help.
    assert value("S3_large", 0.0, "DynamicHomography") < value("S3_large", 0.0, "FrozenHomography")
    assert value("S3_large", 25.0, "RelocalizedPnP") < value("S3_large", 25.0, "FrozenExtrinsicPnP")
    # Planar re-mapping is not a 3-D replacement at nonzero height.
    assert value("S2_moderate", 25.0, "RelocalizedPnP") < value("S2_moderate", 25.0, "DynamicHomography")
    # Every numeric metric must be finite and every row must have planned samples.
    for row in overall:
        assert int(row["n_planned"]) == 2500
        assert math.isfinite(float(row["xy_rmse_mm"]))
        assert 0.0 <= float(row["success_rate"]) <= 1.0

    for stem in (
        "Fig_E7_1_information_flow", "Fig_E7_2_movement_sensitivity",
        "Fig_E7_3_height_motion_interaction", "Fig_E7_4_operating_envelope",
    ):
        for extension in ("png", "pdf"):
            path = FIGURES / f"{stem}.{extension}"
            assert path.exists() and path.stat().st_size > 1000, path
    print("E7 output verification PASS")


if __name__ == "__main__":
    main()

