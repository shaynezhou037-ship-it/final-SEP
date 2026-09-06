#!/usr/bin/env python3
"""Verify E2-v1R0 board-pose outputs and hierarchy invariants."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from build_e2_board_pose_v1 import OUT
from build_empirical_components import XI_NAMES


def load(name):
    with (OUT / name).open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    geometry = load("geometry_hypothesis_audit.csv")
    frames = load("board_pose_per_frame.csv")
    candidates = load("board_pose_candidates.csv")
    within = load("board_within_by_run_height_se3.csv")
    residuals = load("board_within_residuals_se3.csv")
    pooled = load("Sigma_within_pooled_se3.csv")
    b_pose = load("b_pose_se3.csv")
    b_run = load("b_run_empirical_bank_se3.csv")
    single = load("single_marker_ippe_failure_modes.csv")
    single_candidates = load("single_marker_ippe_candidates.csv")

    assert len(geometry) == 660
    assert len(frames) == 330
    assert len(candidates) == 660
    assert len(within) == 110
    assert len(residuals) == 330
    assert len(pooled) == 22
    assert len(b_pose) == 22
    assert len(b_run) == 120  # 10 baseline + 110 height-condition vectors
    assert len(single) == 550
    assert len(single_candidates) == 3300
    assert {int(r["n_frames"]) for r in within} == {3}
    assert {int(r["covariance_rank"]) for r in within} == {2}
    assert {int(r["within_dof"]) for r in pooled} == {10}
    assert all(int(r["gaussian_fit"]) == 0 for r in b_run)

    actual = {(r["camera"], r["run_id"], r["height_mm"], r["frame_index"]): float(r["best_reprojection_rmse_px"])
              for r in geometry if r["geometry"] == "actual_margin10"}
    logged = {(r["camera"], r["run_id"], r["height_mm"], r["frame_index"]): float(r["best_reprojection_rmse_px"])
              for r in geometry if r["geometry"] == "logged_edge_aligned"}
    assert actual.keys() == logged.keys()
    assert all(actual[k] < logged[k] for k in actual)

    # Within residuals must sum to zero in tangent coordinates for every group.
    grouped = {}
    for r in residuals:
        key = (r["camera"], r["run_id"], r["height_mm"])
        grouped.setdefault(key, []).append([float(r[n]) for n in XI_NAMES])
    assert all(np.linalg.norm(np.mean(v, axis=0)) < 1e-9 for v in grouped.values())

    # h=0 pose bias is identity by construction (each run uses its own h=0 baseline).
    for r in b_pose:
        if float(r["height_mm"]) == 0.0:
            assert np.linalg.norm([float(r["b_pose_" + n]) for n in XI_NAMES]) < 1e-10

    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_id"] == "E2-v1R0_board_pose"
    assert manifest["hierarchy"]["total_sum"] == "not produced and not authorized"
    assert manifest["geometry"]["evidence"]["paired_result"]["actual_lower_n"] == 330
    assert manifest["branch_flags"]["clipped_observations"] == 0
    print("PASS: E2-v1R0 board-pose outputs verified")


if __name__ == "__main__":
    main()
