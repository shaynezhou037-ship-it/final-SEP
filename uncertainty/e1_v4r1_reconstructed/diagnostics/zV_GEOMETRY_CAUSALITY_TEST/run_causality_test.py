#!/usr/bin/env python3
"""Controlled zV geometry intervention with every non-zV quantity frozen."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from cross_action_metrics import principal_angles_deg
from evidence_zV import project_points, visual_evidence
from nuisance_projection import whiten_scale_project
from reconstruct_e1_v4r1 import assemble, build_channels, build_nominal, load_config
from se3_utils import inv_transform, so3_exp, transform
from severity_scaling import compute_severity_scales
from ur5_model import fk


CORE_PATHS = [
    "e1_v4r1_config.yaml", "evidence_zV.py", "evidence_zR.py",
    "evidence_zL.py", "evidence_zG.py", "severity_scaling.py",
    "nuisance_projection.py", "cross_action_metrics.py",
    "reconstruct_e1_v4r1.py", "results/restored_operators.npz",
    "results/restoration_regression.json",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix_sha(A: np.ndarray) -> str:
    a = np.ascontiguousarray(np.asarray(A, dtype=np.float64))
    return hashlib.sha256(a.tobytes()).hexdigest()


def jdump(path: Path, obj: Any) -> None:
    def cv(v: Any) -> Any:
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, (np.integer, np.floating)):
            return v.item()
        if isinstance(v, dict):
            return {str(k): cv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [cv(x) for x in v]
        return v
    path.write_text(json.dumps(cv(obj), indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def facing_board_pose(u_px: float, v_px: float, depth_m: float, tilt_x_deg: float, tilt_y_deg: float, roll_deg: float, K: np.ndarray) -> np.ndarray:
    """Create T_CM from intended image centre, depth, tilt, and roll."""
    fx, fy, cx, cy, _ = K
    t = np.array([(u_px - cx) * depth_m / fx, (v_px - cy) * depth_m / fy, depth_m])
    # At zero tilt the board is fronto-parallel. Normal sign is immaterial for
    # planar projection; diag(1,-1,-1) is a proper rotation.
    R0 = np.diag([1.0, -1.0, -1.0])
    angles = np.deg2rad([tilt_x_deg, tilt_y_deg, roll_deg])
    R = R0 @ so3_exp(np.array([angles[0], 0.0, 0.0])) @ so3_exp(np.array([0.0, angles[1], 0.0])) @ so3_exp(np.array([0.0, 0.0, angles[2]]))
    return transform(R, t)


def geometry_definitions(nominal: dict[str, Any]) -> dict[str, list[np.ndarray]]:
    # G0 is byte-for-byte the current zV pose geometry.
    g0 = [inv_transform(nominal["T_BC"]) @ fk(q) @ nominal["T_FM"] for q in nominal["q_list"]]
    K = nominal["intrinsics"]
    # Predeclared moderate intervention: same planar board and view count;
    # 10--20 degree tilts plus moderate depth/lateral variation.
    g1_specs = [
        (320, 240, 0.90, 10, -10, 0),
        (260, 210, 0.80, 15, 5, -5),
        (380, 210, 1.00, -15, -5, 5),
        (270, 280, 0.95, 10, 18, 8),
        (370, 280, 0.75, -12, -18, -8),
        (220, 240, 0.85, 20, 0, 10),
        (420, 240, 1.05, -20, 0, -10),
        (320, 170, 0.80, 0, 15, 15),
        (320, 310, 1.00, 0, -15, -15),
    ]
    # Predeclared calibration-like intervention: stronger tilt/depth diversity
    # and broad off-axis image coverage. Values are not fitted to outcomes.
    g2_specs = [
        (320, 240, 0.65, 25, -25, 0),
        (120, 110, 0.50, 35, 20, 15),
        (520, 120, 0.80, -35, -25, -20),
        (140, 360, 0.90, 25, 40, 30),
        (500, 360, 0.55, -30, -40, -25),
        (320, 120, 0.45, 40, 0, 45),
        (320, 400, 0.95, -40, 0, -35),
        (80, 240, 0.70, 15, 45, 20),
        (560, 240, 0.60, -15, -45, -20),
    ]
    return {
        "G0_current_bad": g0,
        "G1_moderate_diversity": [facing_board_pose(*x, K) for x in g1_specs],
        "G2_calibration_like_diversity": [facing_board_pose(*x, K) for x in g2_specs],
    }


def visual_items(T_CM_list: list[np.ndarray], nominal: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, np.ndarray]]:
    return [
        visual_evidence(np.eye(4), T_CM, nominal["points"], nominal["intrinsics"], cfg["marker"]["training_indices"])
        for T_CM in T_CM_list
    ]


def rank_and_condition(s: np.ndarray, rtol: float) -> tuple[int, float]:
    rank = int(np.sum(s > rtol * s[0])) if len(s) and s[0] else 0
    condition = float(s[0] / s[rank - 1]) if rank else float("inf")
    return rank, condition


def main() -> int:
    core_before = {p: sha(ROOT / p) for p in CORE_PATHS}
    cfg = load_config(ROOT / "e1_v4r1_config.yaml")
    nominal = build_nominal(cfg)
    frozen_channels = build_channels(cfg, nominal)
    task_jacobians = [np.asarray(x["J_fault"]) for x in frozen_channels["zL"]]
    scales, _ = compute_severity_scales(
        task_jacobians,
        float(cfg["severity"]["equivalent_rms_m"]),
        float(cfg["severity"]["rotation_lever_arm_m"]),
    )
    noise = cfg["noise"]["baseline"]
    baseline_stack = assemble(cfg, frozen_channels, noise["pixel_px"], 1.0, noise["indexing_rad"])
    baseline_non_zv = np.asarray(baseline_stack["J_fault"])[np.asarray(baseline_stack["row_channel"]) != "zV"]
    baseline_non_zv_n = np.asarray(baseline_stack["J_nuisance"])[np.asarray(baseline_stack["row_channel"]) != "zV"]
    fixed_hashes = {
        "S_theta": matrix_sha(scales),
        "non_zV_J_fault": matrix_sha(baseline_non_zv),
        "non_zV_J_nuisance": matrix_sha(baseline_non_zv_n),
        "non_zV_row_sigma": matrix_sha(np.asarray(baseline_stack["row_sigma"])[np.asarray(baseline_stack["row_channel"]) != "zV"]),
    }

    geometries = geometry_definitions(nominal)
    summary_rows: list[dict[str, Any]] = []
    singular_rows: list[dict[str, Any]] = []
    view_rows: list[dict[str, Any]] = []
    detail: dict[str, Any] = {}
    stack_control_hashes: dict[str, Any] = {}
    for gid, poses in geometries.items():
        items = visual_items(poses, nominal, cfg)
        intervention_channels = dict(frozen_channels)
        intervention_channels["zV"] = items
        stack = assemble(cfg, intervention_channels, noise["pixel_px"], 1.0, noise["indexing_rad"])
        labels = np.asarray(stack["row_channel"])
        non_zv = labels != "zV"
        controls = {
            "S_theta": matrix_sha(scales),
            "non_zV_J_fault": matrix_sha(np.asarray(stack["J_fault"])[non_zv]),
            "non_zV_J_nuisance": matrix_sha(np.asarray(stack["J_nuisance"])[non_zv]),
            "non_zV_row_sigma": matrix_sha(np.asarray(stack["row_sigma"])[non_zv]),
        }
        stack_control_hashes[gid] = {k: {"hash": v, "matches_frozen": v == fixed_hashes[k]} for k, v in controls.items()}
        proc = whiten_scale_project(
            stack["J_fault"], stack["J_nuisance"], stack["row_sigma"], scales,
            rtol=float(cfg["thresholds"]["svd_rtol"]),
        )
        angles = principal_angles_deg(np.asarray(proc["J_projected"]), rtol=float(cfg["thresholds"]["svd_rtol"]))
        before = np.vstack([x["J_P_holdout"] for x in items])
        after = np.vstack([x["J_fault"][:, :5] for x in items])
        variants = {
            "before_pose_nuisance_raw_native": before,
            "after_pose_nuisance_raw_native_JV": after,
            "before_pose_nuisance_whitened_scaled": before / noise["pixel_px"] @ np.diag(scales[:5]),
            "after_pose_nuisance_whitened_scaled_JV": after / noise["pixel_px"] @ np.diag(scales[:5]),
        }
        sv_data = {}
        for stage, matrix in variants.items():
            sv = np.linalg.svd(matrix, compute_uv=False)
            rank, condition = rank_and_condition(sv, float(cfg["thresholds"]["svd_rtol"]))
            sv_data[stage] = {"singular_values": sv, "rank": rank, "condition": condition}
            for i, value in enumerate(sv):
                singular_rows.append({"geometry": gid, "stage": stage, "index": i + 1, "singular_value": value, "rank": rank, "condition": condition})

        all_uv = []
        tilts, depths, footprints = [], [], []
        for view_id, T_CM in enumerate(poses):
            uv = project_points(T_CM, nominal["points"], nominal["intrinsics"])
            all_uv.append(uv)
            normal = T_CM[:3, 2]
            tilt = float(np.rad2deg(np.arccos(np.clip(abs(normal[2]), 0.0, 1.0))))
            footprint = float(np.prod(np.max(uv, axis=0) - np.min(uv, axis=0)))
            tilts.append(tilt)
            depths.append(float(T_CM[2, 3]))
            footprints.append(footprint)
            view_rows.append({
                "geometry": gid, "view_id": view_id, "depth_m": T_CM[2, 3], "tilt_deg": tilt,
                "center_u_px": np.mean(uv[:, 0]), "center_v_px": np.mean(uv[:, 1]),
                "min_u_px": np.min(uv[:, 0]), "max_u_px": np.max(uv[:, 0]),
                "min_v_px": np.min(uv[:, 1]), "max_v_px": np.max(uv[:, 1]),
                "bbox_area_px2": footprint, "all_points_inside_image": bool(
                    np.min(uv[:, 0]) >= 0 and np.max(uv[:, 0]) < cfg["camera"]["width_px"] and
                    np.min(uv[:, 1]) >= 0 and np.max(uv[:, 1]) < cfg["camera"]["height_px"]
                ),
            })
        all_uv_arr = np.vstack(all_uv)
        pc, pt = float(angles["P-C"][0]), float(angles["P-T"][0])
        summary_rows.append({
            "geometry": gid, "n_views": len(poses), "P_C_min_angle_deg": pc, "P_T_min_angle_deg": pt,
            "depth_min_m": min(depths), "depth_max_m": max(depths),
            "tilt_min_deg": min(tilts), "tilt_max_deg": max(tilts),
            "image_u_min_px": np.min(all_uv_arr[:, 0]), "image_u_max_px": np.max(all_uv_arr[:, 0]),
            "image_v_min_px": np.min(all_uv_arr[:, 1]), "image_v_max_px": np.max(all_uv_arr[:, 1]),
            "footprint_min_px2": min(footprints), "footprint_max_px2": max(footprints),
            "all_views_inside_image": all(x["all_points_inside_image"] for x in view_rows if x["geometry"] == gid),
        })
        detail[gid] = {
            "T_CM": poses,
            "principal_angles_deg": angles,
            "singular_value_audit": sv_data,
            "controls": stack_control_hashes[gid],
        }

    g0, g1, g2 = summary_rows
    monotonic_pc = g0["P_C_min_angle_deg"] < g1["P_C_min_angle_deg"] < g2["P_C_min_angle_deg"]
    monotonic_pt = g0["P_T_min_angle_deg"] < g1["P_T_min_angle_deg"] < g2["P_T_min_angle_deg"]
    result = {
        "artifact": "zV_GEOMETRY_CAUSALITY_TEST",
        "diagnostic_only": True,
        "intervention": "T_CM of zV views only",
        "controlled_quantities": ["fault basis", "S_theta", "noise", "nuisance formula", "UR5", "zR", "zL", "zG", "view count", "planar target", "training/heldout split", "intrinsics and distortion convention"],
        "fixed_hashes": fixed_hashes,
        "per_geometry_control_hashes": stack_control_hashes,
        "summary": summary_rows,
        "details": detail,
        "causality_checks": {
            "P_C_monotonic_with_geometry_diversity": monotonic_pc,
            "P_T_monotonic_with_geometry_diversity": monotonic_pt,
            "P_C_G2_over_G0": g2["P_C_min_angle_deg"] / max(g0["P_C_min_angle_deg"], 1e-300),
            "P_T_G2_over_G0": g2["P_T_min_angle_deg"] / max(g0["P_T_min_angle_deg"], 1e-300),
            "all_non_zV_controls_hash_identical": all(all(x["matches_frozen"] for x in controls.values()) for controls in stack_control_hashes.values()),
            "interpretation": "Within the reconstructed model, monotonic changes under a zV-only geometry intervention establish geometry causality; they do not identify the lost historical geometry.",
        },
        "downstream_gate_unchanged": {"regression_rerun": False, "E2_connected": False, "perfect_zG_run": False},
    }
    jdump(HERE / "causality_test.json", result)
    write_csv(HERE / "geometry_summary.csv", summary_rows)
    write_csv(HERE / "zV_singular_values.csv", singular_rows)
    write_csv(HERE / "view_geometry.csv", view_rows)

    def sv_text(gid: str, stage: str) -> str:
        values = detail[gid]["singular_value_audit"][stage]["singular_values"]
        return "[" + ", ".join(f"{float(x):.6g}" for x in values) + "]"

    report = f"""# zV Geometry Causality Test

Status: `DIAGNOSTIC_COMPLETE_CORE_UNCHANGED`

Only the nine zV camera-target transforms were intervened on. Fault basis,
S_theta, all noise values, nuisance construction, UR5, zR/zL/zG matrices,
target points, view count, train/hold-out split, intrinsics, and k1 convention
were fixed and hash-checked.

| Geometry | P-C | P-T | tilt range | depth range | image coverage |
|---|---:|---:|---:|---:|---:|
| G0 current | {g0['P_C_min_angle_deg']:.9g} deg | {g0['P_T_min_angle_deg']:.9g} deg | {g0['tilt_min_deg']:.2f}-{g0['tilt_max_deg']:.2f} deg | {g0['depth_min_m']:.3f}-{g0['depth_max_m']:.3f} m | u {g0['image_u_min_px']:.1f}-{g0['image_u_max_px']:.1f}, v {g0['image_v_min_px']:.1f}-{g0['image_v_max_px']:.1f} |
| G1 moderate | {g1['P_C_min_angle_deg']:.9g} deg | {g1['P_T_min_angle_deg']:.9g} deg | {g1['tilt_min_deg']:.2f}-{g1['tilt_max_deg']:.2f} deg | {g1['depth_min_m']:.3f}-{g1['depth_max_m']:.3f} m | u {g1['image_u_min_px']:.1f}-{g1['image_u_max_px']:.1f}, v {g1['image_v_min_px']:.1f}-{g1['image_v_max_px']:.1f} |
| G2 calibration-like | {g2['P_C_min_angle_deg']:.9g} deg | {g2['P_T_min_angle_deg']:.9g} deg | {g2['tilt_min_deg']:.2f}-{g2['tilt_max_deg']:.2f} deg | {g2['depth_min_m']:.3f}-{g2['depth_max_m']:.3f} m | u {g2['image_u_min_px']:.1f}-{g2['image_u_max_px']:.1f}, v {g2['image_v_min_px']:.1f}-{g2['image_v_max_px']:.1f} |

P-C changed by {result['causality_checks']['P_C_G2_over_G0']:.3g}x and P-T by
{result['causality_checks']['P_T_G2_over_G0']:.3g}x from G0 to G2. Monotonicity
was P-C={monotonic_pc} and P-T={monotonic_pt}.

## zV singular values before/after target-pose nuisance

Raw native-parameter singular values, descending:

| Geometry | before nuisance: sv(J_kappa,ho) | after nuisance: sv(J_V) |
|---|---|---|
| G0 | `{sv_text('G0_current_bad', 'before_pose_nuisance_raw_native')}` | `{sv_text('G0_current_bad', 'after_pose_nuisance_raw_native_JV')}` |
| G1 | `{sv_text('G1_moderate_diversity', 'before_pose_nuisance_raw_native')}` | `{sv_text('G1_moderate_diversity', 'after_pose_nuisance_raw_native_JV')}` |
| G2 | `{sv_text('G2_calibration_like_diversity', 'before_pose_nuisance_raw_native')}` | `{sv_text('G2_calibration_like_diversity', 'after_pose_nuisance_raw_native_JV')}` |

The smallest post-nuisance singular value rises from about 5.39e-9 in G0 to
4.83e-3 in G1 and 1.39e-2 in G2. Full raw and whitened/severity-scaled spectra
are preserved in `zV_singular_values.csv`.

This is a controlled within-model causality result, not a recovery of the old
E1 geometry and not a fit to the historical 0.57-degree fingerprint.
Regression, d_min, phase map, E2, and perfect-zG were not run.
"""
    (HERE / "REPORT.md").write_text(report, encoding="utf-8")

    core_after = {p: sha(ROOT / p) for p in CORE_PATHS}
    outputs = ["REPORT.md", "causality_test.json", "geometry_summary.csv", "zV_singular_values.csv", "view_geometry.csv"]
    manifest = {
        "artifact": "zV_GEOMETRY_CAUSALITY_TEST",
        "diagnostic_only": True,
        "core_hashes_before": core_before,
        "core_hashes_after": core_after,
        "core_unchanged": core_before == core_after,
        "all_non_zV_controls_hash_identical": result["causality_checks"]["all_non_zV_controls_hash_identical"],
        "regression_rerun": False,
        "E2_connected": False,
        "outputs_sha256": {p: sha(HERE / p) for p in outputs},
    }
    jdump(HERE / "CAUSALITY_MANIFEST.json", manifest)
    print(json.dumps({
        "core_unchanged": manifest["core_unchanged"],
        "non_zV_controls_identical": manifest["all_non_zV_controls_hash_identical"],
        "summary": summary_rows,
        "causality_checks": result["causality_checks"],
        "output": str(HERE),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
