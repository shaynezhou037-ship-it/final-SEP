#!/usr/bin/env python3
"""Deterministic verification for the empirical SE(3) outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from build_empirical_components import OUT, XI_NAMES, inv_T, se3_exp, se3_log, se3_mean


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    # Algebra round trip and Karcher first-order condition.
    probes = [
        np.zeros(6),
        np.array([1.2, -0.4, 3.1, 0.01, -0.02, 0.03]),
        np.array([-4.0, 2.0, 0.5, -0.7, 0.2, 0.4]),
    ]
    for xi in probes:
        assert np.allclose(se3_log(se3_exp(xi)), xi, atol=1e-10)
        assert np.allclose(inv_T(se3_exp(xi)) @ se3_exp(xi), np.eye(4), atol=1e-10)
    Ts = [se3_exp(xi) for xi in probes]
    mean = se3_mean(Ts)
    assert np.linalg.norm(np.mean([se3_log(inv_T(mean) @ T) for T in Ts], axis=0)) < 1e-10

    pixel = rows("pixel_within.csv")
    pnp = rows("pnp_within_se3.csv")
    pnp_residuals = rows("pnp_within_residuals_se3.csv")
    bias = rows("run_bias_se3.csv")
    comp = rows("e2_hierarchical_components_se3.csv")
    vectors = rows("e2_hierarchical_vectors_se3.csv")
    assert len([r for r in pixel if r["dataset"] == "E0-A"]) == 10
    assert len([r for r in pixel if r["dataset"] == "E4"]) == 42
    assert len([r for r in pixel if r["dataset"] == "E2"]) == 2750
    assert len([r for r in pnp if r["dataset"] == "E4"]) == 4
    assert len([r for r in pnp if r["dataset"] == "E2"]) == 550
    assert len(bias) == 554
    assert len(comp) == 88
    assert len(pnp_residuals) == 1730
    assert len(vectors) == 2310
    assert {int(r["n"]) for r in pnp if r["dataset"] == "E2"} == {3}
    assert {int(r["n_runs_for_condition"]) for r in bias} == {2, 5}

    # Each 5-run condition has a near-zero tangent mean by construction.
    grouped = {}
    for r in bias:
        key = (r["camera"], r["pose_key"], r["height_mm"])
        grouped.setdefault(key, []).append([float(r["b_" + n]) for n in XI_NAMES])
    assert all(np.linalg.norm(np.mean(v, axis=0)) < 1e-8 for v in grouped.values())

    # The exported total is exactly the sum of the three named components.
    by = {(r["camera"], r["height_mm"], r["component"]): r for r in comp}
    cov_names = [f"cov_{a}_{b}" for a in XI_NAMES for b in XI_NAMES]
    for camera in ("ihawk1", "ihawk2"):
        for height in sorted({r["height_mm"] for r in comp if r["camera"] == camera}):
            total = np.array([float(by[(camera, height, "total_sum")][n]) for n in cov_names])
            parts = sum(np.array([float(by[(camera, height, c)][n]) for n in cov_names]) for c in ("within_pose", "between_run", "cross_pose"))
            assert np.allclose(total, parts, atol=1e-12)

    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    delta = manifest["e2_pnp_audit"]["recomputed_vs_stored_pnp_log_abs_max"]
    # Raw CSV corners/tvecs are decimal-serialized, so the reconstruction audit
    # is limited by source rounding at roughly 1e-5 mm.
    assert max(delta.values()) < 2e-5
    assert manifest["identifiability"]["E1_v4_replay"].startswith("blocked")
    print("PASS: empirical SE(3) component outputs verified")


if __name__ == "__main__":
    main()
