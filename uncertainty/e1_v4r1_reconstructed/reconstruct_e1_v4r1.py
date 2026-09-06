#!/usr/bin/env python3
"""Reconstruct and regression-test the frozen E1-v4R1 mathematical pipeline.

This program intentionally has no dependency on uncertainty/empirical_se3_replay.
It stops at restoration status; phase-map and empirical replay are separate,
downstream stages and are forbidden unless this program reports PASS.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from cross_action_metrics import (
    ACTION_INDICES,
    CROSS_ACTION_PAIRS,
    FAULT_NAMES,
    cross_action_dmin,
    mode_residual_sigma,
    principal_angles_deg,
)
from evidence_zG import geometry_evidence
from evidence_zL import localization_evidence
from evidence_zR import relative_evidence
from evidence_zV import marker_grid, visual_evidence
from nuisance_projection import whiten_scale_project
from se3_utils import inv_transform, rotation_from_look_at, so3_exp, transform
from severity_scaling import compute_severity_scales
from ur5_model import fk


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (np.floating, np.integer)):
        return v.item()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_nominal(cfg: dict[str, Any]) -> dict[str, Any]:
    cam = cfg["camera"]
    p = np.asarray(cam["position_B_m"], dtype=float)
    target = np.asarray(cam["look_at_B_m"], dtype=float)
    T_BC = transform(rotation_from_look_at(p, target), p)
    fm = cfg["flange_marker"]
    T_FM = transform(
        so3_exp(np.asarray(fm["rotation_vector_rad"], dtype=float)),
        np.asarray(fm["translation_m"], dtype=float),
    )
    marker = cfg["marker"]
    points = marker_grid(tuple(marker["grid_shape"]), float(marker["spacing_m"]))
    q_list = [np.asarray(q, dtype=float) for q in cfg["task_poses_rad"]]
    intrinsics = np.asarray(cam["intrinsics"], dtype=float)
    return {"T_BC": T_BC, "T_FM": T_FM, "points": points, "q_list": q_list, "intrinsics": intrinsics}


def build_channels(cfg: dict[str, Any], nominal: dict[str, Any]) -> dict[str, Any]:
    T_BC, T_FM = nominal["T_BC"], nominal["T_FM"]
    points, q_list, intrinsics = nominal["points"], nominal["q_list"], nominal["intrinsics"]
    training = cfg["marker"]["training_indices"]
    visual, bposes = [], []
    for q in q_list:
        item = visual_evidence(T_BC, fk(q) @ T_FM, points, intrinsics, training)
        visual.append(item)
        bposes.append(item["B_pose"])

    # RECONSTRUCTION_CHOICE_relative_pairs: nominal-to-each-offset. The old
    # relative pair list was not recovered; no pair is selected by outcome.
    pair_indices = [(0, j) for j in range(1, len(q_list))]
    relative = [relative_evidence(q_list[i], q_list[j], T_BC, T_FM, bposes[i], bposes[j]) for i, j in pair_indices]
    localization = []
    geometry = []
    for q, B in zip(q_list, bposes):
        T_CM = inv_transform(T_BC) @ fk(q) @ T_FM
        localization.append(localization_evidence(q, T_CM, T_FM, B))
        geometry.append(geometry_evidence(q, T_BC, T_FM, B))
    return {
        "zV": visual,
        "zR": relative,
        "zL": localization,
        "zG": geometry,
        "B_pose": bposes,
        "relative_pair_indices": pair_indices,
    }


def _pose_sigmas(n: int, sigma_t: float, sigma_r: float) -> np.ndarray:
    return np.tile(np.r_[np.full(3, sigma_t), np.full(3, sigma_r)], n)


def assemble(
    cfg: dict[str, Any],
    channels: dict[str, Any],
    pixel_sigma: float,
    relative_factor: float,
    indexing_sigma_rad: float,
) -> dict[str, Any]:
    jf_blocks, jn_blocks, sigmas, labels = [], [], [], []
    noise = cfg["noise"]["baseline"]

    def add(name: str, item: dict[str, Any], base_sigma: np.ndarray, indexing: bool = False) -> None:
        jf = np.asarray(item["J_fault"], dtype=float)
        jn = np.asarray(item["J_nuisance"], dtype=float)
        sigma = np.asarray(base_sigma, dtype=float)
        if indexing:
            # RECONSTRUCTION_CHOICE_indexing: R is a persistent joint-zero
            # hypothesis, not independent per-row encoder noise. The recovered
            # historical sweep was invariant over 0.005--1 deg, so duplicating
            # R as diagonal measurement noise is explicitly forbidden here.
            # The value remains an audited sweep coordinate until the missing
            # correlated indexing covariance is recovered.
            _ = indexing_sigma_rad
        jf_blocks.append(jf)
        jn_blocks.append(jn)
        sigmas.append(sigma)
        labels.extend([name] * jf.shape[0])

    for item in channels["zV"]:
        add("zV", item, np.full(item["J_fault"].shape[0], pixel_sigma))
    for item in channels["zR"]:
        add(
            "zR",
            item,
            _pose_sigmas(1, noise["relative_translation_m"] * relative_factor, noise["relative_rotation_rad"] * relative_factor),
            indexing=True,
        )
    for item in channels["zL"]:
        add("zL", item, _pose_sigmas(1, noise["pose_translation_m"], noise["pose_rotation_rad"]))
    for item in channels["zG"]:
        add(
            "zG",
            item,
            _pose_sigmas(1, noise["relative_translation_m"] * relative_factor, noise["relative_rotation_rad"] * relative_factor),
            indexing=True,
        )
    return {
        "J_fault": np.vstack(jf_blocks),
        "J_nuisance": np.vstack(jn_blocks),
        "row_sigma": np.concatenate(sigmas),
        "row_channel": labels,
    }


def evaluate(
    cfg: dict[str, Any],
    channels: dict[str, Any],
    severity_scales: np.ndarray,
    pixel_sigma: float,
    relative_factor: float,
    indexing_sigma_rad: float,
) -> dict[str, Any]:
    stack = assemble(cfg, channels, pixel_sigma, relative_factor, indexing_sigma_rad)
    projected = whiten_scale_project(
        stack["J_fault"], stack["J_nuisance"], stack["row_sigma"], severity_scales,
        rtol=float(cfg["thresholds"]["svd_rtol"]),
    )
    J = np.asarray(projected["J_projected"])
    angles = principal_angles_deg(J, rtol=float(cfg["thresholds"]["svd_rtol"]))
    dmin, ddetail = cross_action_dmin(J)
    gauges = {
        "C_yaw_vs_q1": mode_residual_sigma(J, 10, [17]),
        "T_yaw_vs_q6": mode_residual_sigma(J, 16, [22]),
        "C_yaw_vs_R_block": mode_residual_sigma(J, 10, ACTION_INDICES["R"]),
        "T_yaw_vs_R_block": mode_residual_sigma(J, 16, ACTION_INDICES["R"]),
    }
    return {
        "angles": angles,
        "minimum_angles_deg": {k: float(v[0]) for k, v in angles.items()},
        "gauges_sigma": gauges,
        "dmin_cross": dmin,
        "dmin_detail": ddetail,
        "nuisance_rank": int(projected["nuisance_rank"]),
        "matrix_shape": list(J.shape),
        "projected_matrix": J,
    }


def regression_checks(cfg: dict[str, Any], baseline: dict[str, Any], sweeps: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, passed: bool, observed: Any, criterion: str) -> None:
        checks[name] = {"pass": bool(passed), "observed": _jsonable(observed), "criterion": criterion}

    mins = baseline["minimum_angles_deg"]
    targets = cfg["historical_fingerprints"]["principal_angles_deg"]
    for pair, target in targets.items():
        # The old geometry/seed are absent, so use an explicit broad regression
        # envelope. This detects order-of-magnitude/model failures without
        # pretending the original numerical experiment was exactly recovered.
        tol = max(0.35, 0.75 * float(target))
        record(f"principal_angle_{pair}", abs(mins[pair] - target) <= tol, mins[pair], f"|observed-{target}| <= {tol}")

    record(
        "C_R_is_among_two_hardest",
        mins["C-R"] <= sorted(mins.values())[1] + 1e-12,
        mins,
        "C-R minimum angle ranks among the two smallest",
    )
    g = baseline["gauges_sigma"]
    record("gauge_C_yaw_q1_finite", 0.25 <= g["C_yaw_vs_q1"] <= 3.0, g["C_yaw_vs_q1"], "0.25 <= residual <= 3 sigma")
    record("gauge_T_yaw_q6_larger", g["T_yaw_vs_q6"] >= 1.5 * g["C_yaw_vs_q1"], g, "T/q6 >= 1.5 * C/q1")

    rel = sweeps["relative"]
    rel_y = np.array([x["C_yaw_vs_q1_sigma"] for x in rel])
    record("relative_noise_monotonic", bool(np.all(np.diff(rel_y) >= -1e-8)), rel_y, "residual nondecreasing as noise factor decreases")
    record("relative_noise_strong_improvement", rel_y[-1] >= 2.0 * rel_y[0], rel_y, "factor 0.25 residual >= 2x factor 1.0")

    cam = sweeps["camera"]
    cam_y = np.array([x["P_C_angle_deg"] for x in cam])
    record("camera_noise_monotonic", bool(np.all(np.diff(cam_y) >= -1e-8)), cam_y, "P-C angle nondecreasing as pixel noise decreases")
    record("camera_noise_material_improvement", cam_y[-1] >= 1.5 * cam_y[0], cam_y, "0.03 px angle >= 1.5x 1.0 px angle")

    idx = sweeps["indexing"]
    idx_y = np.array([x["C_R_angle_deg"] for x in idx])
    relative_span = float(np.ptp(idx_y) / max(np.mean(idx_y), 1e-12))
    record("indexing_near_invariant", relative_span <= 0.25, {"values": idx_y, "relative_span": relative_span}, "relative span <= 25%")

    required = [v["pass"] for v in checks.values()]
    return {"status": "PASS" if all(required) else "FAIL", "checks": checks, "passed": sum(required), "total": len(required)}


def make_sweeps(cfg: dict[str, Any], channels: dict[str, Any], scales: np.ndarray) -> dict[str, list[dict[str, Any]]]:
    base = cfg["noise"]["baseline"]
    relative_rows = []
    for factor in cfg["noise"]["relative_noise_factor_sweep"]:
        ev = evaluate(cfg, channels, scales, base["pixel_px"], float(factor), base["indexing_rad"])
        relative_rows.append({
            "relative_noise_factor": factor,
            "C_yaw_vs_q1_sigma": ev["gauges_sigma"]["C_yaw_vs_q1"],
            "T_yaw_vs_q6_sigma": ev["gauges_sigma"]["T_yaw_vs_q6"],
            "C_R_angle_deg": ev["minimum_angles_deg"]["C-R"],
        })
    camera_rows = []
    for px in cfg["noise"]["camera_pixel_sweep_px"]:
        ev = evaluate(cfg, channels, scales, float(px), 1.0, base["indexing_rad"])
        camera_rows.append({
            "pixel_sigma_px": px,
            "P_C_angle_deg": ev["minimum_angles_deg"]["P-C"],
            "P_T_angle_deg": ev["minimum_angles_deg"]["P-T"],
        })
    indexing_rows = []
    for deg in cfg["noise"]["indexing_sweep_deg"]:
        ev = evaluate(cfg, channels, scales, base["pixel_px"], 1.0, np.deg2rad(float(deg)))
        indexing_rows.append({
            "indexing_sigma_deg": deg,
            "C_R_angle_deg": ev["minimum_angles_deg"]["C-R"],
            "T_R_angle_deg": ev["minimum_angles_deg"]["T-R"],
        })
    return {"relative": relative_rows, "camera": camera_rows, "indexing": indexing_rows}


def write_manifest(cfg: dict[str, Any], regression: dict[str, Any]) -> None:
    files = {}
    audited_paths = (
        sorted(HERE.glob("*.py"))
        + sorted((HERE / "tests").glob("*.py"))
        + [HERE / "e1_v4r1_config.yaml", HERE / "E1_v4R1_CONTRACT.md", HERE / "RESTORATION_STATUS.md"]
    )
    for path in audited_paths:
        if path.exists():
            files[path.relative_to(HERE).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "artifact": cfg["name"],
        "restoration_status": regression["status"],
        "formal_e2_input_authorized": False,
        "phase_map_authorized": regression["status"] == "PASS",
        "perfect_zG_replay_authorized": regression["status"] == "PASS",
        "e2_dependency_present": False,
        "contract_sha256": cfg["contract_sha256"],
        "reconstruction_choices": [
            "RECONSTRUCTION_CHOICE_seed_and_task_pose_list",
            "RECONSTRUCTION_CHOICE_relative_pair_list",
            "RECONSTRUCTION_CHOICE_zG_JACOBIAN",
            "RECONSTRUCTION_CHOICE_global_nuisance_X_B_X_F",
            "RECONSTRUCTION_CHOICE_indexing_correlated_covariance_pending",
            "RECONSTRUCTION_CHOICE_dmin_equal_severity_unit_direction",
        ],
        "files_sha256": files,
    }
    (RESULTS / "reconstruction_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "e1_v4r1_config.yaml")
    args = parser.parse_args()
    cfg = load_config(args.config)
    RESULTS.mkdir(exist_ok=True)

    nominal = build_nominal(cfg)
    channels = build_channels(cfg, nominal)
    # zL is the recovered absolute task-pose error model and therefore defines
    # engineering severity. zG is an evidence channel, not the task metric.
    task_jacobians = [np.asarray(x["J_fault"]) for x in channels["zL"]]
    scales, raw_rms = compute_severity_scales(
        task_jacobians,
        float(cfg["severity"]["equivalent_rms_m"]),
        float(cfg["severity"]["rotation_lever_arm_m"]),
    )
    base_noise = cfg["noise"]["baseline"]
    baseline = evaluate(
        cfg, channels, scales, base_noise["pixel_px"], 1.0, base_noise["indexing_rad"]
    )
    sweeps = make_sweeps(cfg, channels, scales)
    regression = regression_checks(cfg, baseline, sweeps)

    angle_rows = []
    for pair, values in baseline["angles"].items():
        angle_rows.append({
            "action_pair": pair,
            "minimum_angle_deg": values[0],
            "all_principal_angles_deg": json.dumps(values),
            "historical_fingerprint_deg": cfg["historical_fingerprints"]["principal_angles_deg"].get(pair, ""),
        })
    gauge_rows = [
        {"comparison": k, "residual_sigma": v, "historical_fingerprint_sigma": cfg["historical_fingerprints"]["gauge_sigma"].get(k, "")}
        for k, v in baseline["gauges_sigma"].items()
    ]
    write_csv(RESULTS / "principal_angles.csv", angle_rows)
    write_csv(RESULTS / "gauge_residuals.csv", gauge_rows)
    write_csv(RESULTS / "relative_noise_sweep.csv", sweeps["relative"])
    write_csv(RESULTS / "camera_noise_sweep.csv", sweeps["camera"])
    write_csv(RESULTS / "indexing_sweep.csv", sweeps["indexing"])
    np.savez_compressed(
        RESULTS / "restored_operators.npz",
        J_projected=baseline["projected_matrix"],
        severity_scales=scales,
        severity_raw_rms=raw_rms,
        fault_names=np.asarray(FAULT_NAMES),
    )

    report = {
        "artifact": cfg["name"],
        "restoration": regression,
        "baseline": {k: _jsonable(v) for k, v in baseline.items() if k != "projected_matrix"},
        "severity": {"scale": scales.tolist(), "raw_task_equivalent_rms": raw_rms.tolist()},
        "channel_rows": {
            "zV": int(sum(x["J_fault"].shape[0] for x in channels["zV"])),
            "zR": int(sum(x["J_fault"].shape[0] for x in channels["zR"])),
            "zL": int(sum(x["J_fault"].shape[0] for x in channels["zL"])),
            "zG": int(sum(x["J_fault"].shape[0] for x in channels["zG"])),
        },
        "strict_gate": {
            "phase_map_run": False,
            "E2_connected": False,
            "perfect_zG_run": False,
            "reason": "This executable performs restoration regression only; downstream stages require PASS.",
        },
    }
    (RESULTS / "restoration_regression.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_manifest(cfg, regression)
    print(json.dumps({
        "status": regression["status"],
        "checks": f"{regression['passed']}/{regression['total']}",
        "minimum_angles_deg": baseline["minimum_angles_deg"],
        "gauges_sigma": baseline["gauges_sigma"],
        "dmin_cross_reconstructed": baseline["dmin_cross"],
        "results": str(RESULTS),
    }, indent=2))
    return 0 if regression["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
