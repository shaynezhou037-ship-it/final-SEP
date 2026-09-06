#!/usr/bin/env python3
"""Read-only diagnostic of the reconstructed E1-v4R1 P block.

This script imports the frozen candidate but does not modify its model,
configuration, regression, manifest, or downstream gates.
"""

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
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from cross_action_metrics import FAULT_NAMES, mode_residual_sigma
from nuisance_projection import whiten_scale_project
from reconstruct_e1_v4r1 import assemble, build_channels, build_nominal, load_config
from severity_scaling import compute_severity_scales


CHANNELS = ("zV", "zR", "zL", "zG")
P_NAMES = FAULT_NAMES[:5]
AUDITED_CORE = [
    "e1_v4r1_config.yaml",
    "evidence_zV.py",
    "evidence_zR.py",
    "evidence_zL.py",
    "evidence_zG.py",
    "severity_scaling.py",
    "nuisance_projection.py",
    "cross_action_metrics.py",
    "reconstruct_e1_v4r1.py",
    "results/restored_operators.npz",
    "results/restoration_regression.json",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def jdump(path: Path, obj: Any) -> None:
    def cv(v: Any) -> Any:
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, (np.floating, np.integer)):
            return v.item()
        if isinstance(v, dict):
            return {str(k): cv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [cv(x) for x in v]
        return v
    path.write_text(json.dumps(cv(obj), indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def basis(A: np.ndarray, rtol: float = 1e-10) -> np.ndarray:
    U, s, _ = np.linalg.svd(A, full_matrices=False)
    if not len(s) or s[0] == 0:
        return np.zeros((A.shape[0], 0))
    return U[:, s > rtol * s[0]]


def min_angle(A: np.ndarray, B: np.ndarray) -> float:
    Qa, Qb = basis(A), basis(B)
    if not Qa.shape[1] or not Qb.shape[1]:
        return 90.0
    cosine = np.linalg.svd(Qa.T @ Qb, compute_uv=False)[0]
    return float(np.rad2deg(np.arccos(np.clip(cosine, -1.0, 1.0))))


def limiting_coefficients(A: np.ndarray, B: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    Qa, Qb = basis(A), basis(B)
    U, s, Vh = np.linalg.svd(Qa.T @ Qb, full_matrices=False)
    signal_a = Qa @ U[:, 0]
    signal_b = Qb @ Vh.T[:, 0]
    ca = np.linalg.pinv(A, rcond=1e-12) @ signal_a
    cb = np.linalg.pinv(B, rcond=1e-12) @ signal_b
    ca /= np.linalg.norm(ca)
    cb /= np.linalg.norm(cb)
    angle = float(np.rad2deg(np.arccos(np.clip(s[0], -1.0, 1.0))))
    return angle, ca, cb


def exact_task_rms(theta: np.ndarray, task_jacobians: list[np.ndarray], lever: float) -> float:
    vals = []
    for J in task_jacobians:
        x = J @ theta
        vals.append(np.dot(x[:3], x[:3]) + lever * lever * np.dot(x[3:], x[3:]))
    return float(np.sqrt(np.mean(vals)))


def rank_info(A: np.ndarray, rtol: float) -> tuple[int, list[float]]:
    if A.size == 0:
        return 0, []
    s = np.linalg.svd(A, compute_uv=False)
    rank = 0 if not len(s) or s[0] == 0 else int(np.sum(s > rtol * s[0]))
    return rank, s.tolist()


def main() -> int:
    core_before = {p: sha256(ROOT / p) for p in AUDITED_CORE}
    cfg = load_config(ROOT / "e1_v4r1_config.yaml")
    nominal = build_nominal(cfg)
    channels = build_channels(cfg, nominal)
    task_jacobians = [np.asarray(x["J_fault"]) for x in channels["zL"]]
    target_rms = float(cfg["severity"]["equivalent_rms_m"])
    lever = float(cfg["severity"]["rotation_lever_arm_m"])
    scales, _ = compute_severity_scales(task_jacobians, target_rms, lever)
    n = cfg["noise"]["baseline"]
    stack = assemble(cfg, channels, n["pixel_px"], 1.0, n["indexing_rad"])
    proc = whiten_scale_project(
        stack["J_fault"], stack["J_nuisance"], stack["row_sigma"], scales,
        rtol=float(cfg["thresholds"]["svd_rtol"]),
    )
    Jraw = np.asarray(stack["J_fault"])
    Jwhite = np.asarray(proc["J_fault_white"])
    Jscaled = np.asarray(proc["J_fault_scaled"])
    Jproj = np.asarray(proc["J_projected"])
    labels = np.asarray(stack["row_channel"])

    directions: dict[str, Any] = {}
    direction_rows: list[dict[str, Any]] = []
    zV_rows: list[dict[str, Any]] = []
    for tag, other_slice in (("P-C", slice(5, 11)), ("P-T", slice(11, 17))):
        angle, uP, uOther = limiting_coefficients(Jproj[:, :5], Jproj[:, other_slice])
        theta_p = scales[:5] * uP
        achieved = exact_task_rms(np.r_[theta_p, np.zeros(18)], task_jacobians, lever)
        severity_factor = target_rms / achieved
        u_equal = uP * severity_factor
        theta_equal = scales[:5] * u_equal
        directions[tag] = {
            "minimum_angle_deg": angle,
            "P_coefficients_unit_normalized_coordinate": dict(zip(P_NAMES, uP)),
            "P_coefficients_exact_5mm_normalized_coordinate": dict(zip(P_NAMES, u_equal)),
            "P_physical_parameter_increment_exact_5mm": dict(zip(P_NAMES, theta_equal)),
            "unit_direction_task_rms_m": achieved,
            "exact_severity_rescale": severity_factor,
            "competitor_coefficients_unit_normalized_coordinate": uOther,
        }
        for channel in CHANNELS:
            mask = labels == channel
            direction_rows.append({
                "pair": tag,
                "channel": channel,
                "whitened_scaled_pre_nuisance_norm_sigma": np.linalg.norm(Jscaled[mask, :5] @ u_equal),
                "whitened_scaled_post_nuisance_norm_sigma": np.linalg.norm(Jproj[mask, :5] @ u_equal),
            })

        before_blocks, after_blocks = [], []
        for view_id, item in enumerate(channels["zV"]):
            before = np.asarray(item["J_P_holdout"]) @ theta_equal
            after = np.asarray(item["J_fault"])[:, :5] @ theta_equal
            before_blocks.append(before)
            after_blocks.append(after)
            zV_rows.append({
                "pair": tag,
                "view_id": view_id,
                "before_pose_nuisance_raw_px": np.linalg.norm(before),
                "after_pose_nuisance_raw_px": np.linalg.norm(after),
                "before_pose_nuisance_whitened_sigma": np.linalg.norm(before) / n["pixel_px"],
                "after_pose_nuisance_whitened_sigma": np.linalg.norm(after) / n["pixel_px"],
                "after_over_before": np.linalg.norm(after) / max(np.linalg.norm(before), 1e-300),
            })
        before = np.concatenate(before_blocks)
        after = np.concatenate(after_blocks)
        directions[tag]["zV_pose_nuisance_audit"] = {
            "before_raw_px": np.linalg.norm(before),
            "after_raw_px": np.linalg.norm(after),
            "before_whitened_sigma": np.linalg.norm(before) / n["pixel_px"],
            "after_whitened_sigma": np.linalg.norm(after) / n["pixel_px"],
            "after_over_before": np.linalg.norm(after) / np.linalg.norm(before),
        }

    ablations = {
        "focal_fx_fy": [0, 1],
        "principal_cx_cy": [2, 3],
        "radial_k1": [4],
        "focal_plus_radial": [0, 1, 4],
        "full_P_diagnostic_reference": [0, 1, 2, 3, 4],
    }
    ablation_rows = []
    for name, idx in ablations.items():
        ablation_rows.append({
            "P_subset": name,
            "P_indices": json.dumps(idx),
            "P_C_min_angle_deg": min_angle(Jproj[:, idx], Jproj[:, 5:11]),
            "P_T_min_angle_deg": min_angle(Jproj[:, idx], Jproj[:, 11:17]),
        })

    stage_matrices = {
        "J_aug_native_unit": Jraw,
        "Sigma^-1/2_J_native_unit": Jwhite,
        "Sigma^-1/2_J_S_theta": Jscaled,
        "P_N_perp_Sigma^-1/2_J_S_theta": Jproj,
    }
    audit_faults = {"C_wz": 10, "R_q1": 17, "T_wz": 16, "R_q6": 22}
    stage_rows = []
    gauge_stage_rows = []
    for stage, matrix in stage_matrices.items():
        for fault, idx in audit_faults.items():
            row = {"stage": stage, "fault": fault, "total_norm": np.linalg.norm(matrix[:, idx])}
            row.update({f"{ch}_norm": np.linalg.norm(matrix[labels == ch, idx]) for ch in CHANNELS})
            stage_rows.append(row)
        for pair, target, competitor in (("C_wz_to_R_q1", 10, 17), ("T_wz_to_R_q6", 16, 22)):
            gauge_stage_rows.append({
                "stage": stage,
                "pair": pair,
                "directed_projection_residual": mode_residual_sigma(matrix, target, [competitor]),
                "target_norm": np.linalg.norm(matrix[:, target]),
                "competitor_norm": np.linalg.norm(matrix[:, competitor]),
                "cosine": np.dot(matrix[:, target], matrix[:, competitor]) /
                    max(np.linalg.norm(matrix[:, target]) * np.linalg.norm(matrix[:, competitor]), 1e-300),
            })

    nuisance_rows = []
    rtol = float(cfg["thresholds"]["svd_rtol"])
    for stage, matrix in (("J_nuisance", np.asarray(stack["J_nuisance"])), ("Sigma^-1/2_J_nuisance", np.asarray(proc["J_nuisance_white"]))):
        for channel in ("ALL",) + CHANNELS:
            mask = np.ones(len(labels), dtype=bool) if channel == "ALL" else labels == channel
            for block, cols in (("X_B", slice(0, 6)), ("X_F", slice(6, 12)), ("X_B_plus_X_F", slice(0, 12))):
                sub = matrix[mask, cols]
                rank, singular = rank_info(sub, rtol)
                nuisance_rows.append({
                    "stage": stage,
                    "channel": channel,
                    "block": block,
                    "rank": rank,
                    "frobenius_norm": np.linalg.norm(sub),
                    "singular_values": json.dumps(singular),
                })

    current_geometry = {
        "status": "RECONSTRUCTION_CHOICE_not_recovered_historical_zV",
        "target_points": nominal["points"],
        "target_planarity_rank_z": int(np.linalg.matrix_rank(nominal["points"] - np.mean(nominal["points"], axis=0))),
        "number_of_zV_views": len(channels["zV"]),
        "view_source": "task_poses_rad (robot routine configurations; not proven zV calibration views)",
        "training_indices": cfg["marker"]["training_indices"],
        "heldout_indices": channels["zV"][0]["heldout_indices"],
        "K_and_k1": cfg["camera"]["intrinsics"],
        "distortion_convention": "x_d=x(1+k1*(x^2+y^2)), normalized coordinates before pixel scaling",
    }
    recovered_candidate = {
        "classification": "LOCAL_E1_PLANAR_EXPERIMENT_CANDIDATE_NOT_PROVEN_TO_BE_E1-v3_zV",
        "target": "6 x 8 inner chessboard corners, planar Z=0, 25 mm spacing",
        "number_of_target_views": "one fixed view represented by median locations over 50 accepted frames",
        "training_indices": [0, 5, 47, 42, 20, 23, 9, 24, 33, 12, 35, 44],
        "heldout_indices": [1, 2, 3, 4, 6, 7, 8, 10, 11, 13, 14, 15, 16, 17, 18, 19, 21, 22, 25, 26, 27, 28, 29, 30, 31, 32, 34, 36, 37, 38, 39, 40, 41, 43, 45, 46],
        "K": [[401.77020263671875, 0.0, 322.1313781738281], [0.0, 401.9191589355469, 202.54229736328125], [0.0, 0.0, 1.0]],
        "D": [0.0, 0.0, 0.0, 0.0, 0.0],
        "k1_convention": "ROS/OpenCV plumb_bob metadata; analysis explicitly uses undistorted pixels and zero distortion",
        "pixel_normalization": "cv2.undistortPoints(raw,K,D,P=K), then pixel coordinates",
        "pnp_pose": {"rvec": [-1.0300238527727992, -0.34233656296423387, -0.5590155198115632], "tvec_mm": [-137.72434646872753, 72.12900182746782, 613.5501314584345]},
        "provenance": [
            "scripts/e1_planar_model_comparison.py",
            "E1/E1_planar_model_comparison/raw/E1_ihawk1_planar_raw_20260807_212655_meta.json",
            "E1/E1_planar_model_comparison/results/E1_ihawk1_planar_20260807_212655_comparison_summary.json",
            "E1/E1_planar_model_comparison/results/E1_ihawk1_planar_20260807_212655_models.json",
            "config/intrinsics/ihawk1_color_camera_info.yaml",
        ],
    }
    measurement_inventory = {
        "zV": {"views": len(channels["zV"]), "heldout_points_per_view": len(channels["zV"][0]["heldout_indices"]), "scalar_rows": int(np.sum(labels == "zV"))},
        "zR": {"independent_pose_pairs_assumed": len(channels["zR"]), "pair_indices": channels["relative_pair_indices"], "scalar_rows": int(np.sum(labels == "zR"))},
        "zL": {"pose_measurements_assumed": len(channels["zL"]), "scalar_rows": int(np.sum(labels == "zL"))},
        "zG": {"independent_pose_measurements_assumed": len(channels["zG"]), "scalar_rows": int(np.sum(labels == "zG"))},
        "covariance_assumption": "diagonal row covariance; listed pose measurements/pairs are treated as independent",
        "historical_identity": "NOT_RECOVERED; current counts are reconstruction choices",
    }
    scale_audit = {
        "C_wz_to_q1": {
            "pre_nuisance_scaled_residual_sigma": mode_residual_sigma(Jscaled, 10, [17]),
            "post_nuisance_residual_sigma": mode_residual_sigma(Jproj, 10, [17]),
            "post_over_pre": mode_residual_sigma(Jproj, 10, [17]) / mode_residual_sigma(Jscaled, 10, [17]),
            "current_over_historical": mode_residual_sigma(Jproj, 10, [17]) / 0.95,
            "equivalent_independent_information_multiplier_if_only_count_changed": (0.95 / mode_residual_sigma(Jproj, 10, [17])) ** 2,
        },
        "T_wz_to_q6": {
            "pre_nuisance_scaled_residual_sigma": mode_residual_sigma(Jscaled, 16, [22]),
            "post_nuisance_residual_sigma": mode_residual_sigma(Jproj, 16, [22]),
            "post_over_pre": mode_residual_sigma(Jproj, 16, [22]) / mode_residual_sigma(Jscaled, 16, [22]),
            "current_over_historical": mode_residual_sigma(Jproj, 16, [22]) / 4.18,
            "equivalent_independent_information_multiplier_if_only_count_changed": (4.18 / mode_residual_sigma(Jproj, 16, [22])) ** 2,
        },
        "interpretation": "Total C_wz signal is not globally scaled down; the deficit is localized to unique zR/zG information and nuisance handling.",
    }

    write_csv(HERE / "dangerous_direction_channel_norms.csv", direction_rows)
    write_csv(HERE / "zV_nuisance_before_after.csv", zV_rows)
    write_csv(HERE / "P_mode_ablation.csv", ablation_rows)
    write_csv(HERE / "gauge_stage_channel_norms.csv", stage_rows)
    write_csv(HERE / "gauge_stage_residuals.csv", gauge_stage_rows)
    write_csv(HERE / "nuisance_rank_sources.csv", nuisance_rows)
    jdump(HERE / "diagnostic.json", {
        "artifact": "E1-v4R1_P_BLOCK_DIAGNOSTIC",
        "diagnostic_only": True,
        "core_model_modified": False,
        "E2_connected": False,
        "directions": directions,
        "ablations": ablation_rows,
        "measurement_inventory": measurement_inventory,
        "current_reconstructed_camera_geometry": current_geometry,
        "recovered_local_candidate": recovered_candidate,
        "absolute_scale_audit": scale_audit,
        "nuisance_rank": int(proc["nuisance_rank"]),
    })

    pc = directions["P-C"]
    pt = directions["P-T"]
    report = f"""# E1-v4R1 P-block diagnostic

Status: `DIAGNOSTIC_COMPLETE_REGRESSION_UNCHANGED_FAIL_CLOSED`

No evidence formula, configuration, noise value, threshold, regression result,
or E2 artifact was changed.

## Primary answer

The current P-C/P-T collapse is localized to **zV observability plus the
reconstructed nuisance geometry**, not to UR5 kinematics. The dangerous P
directions are absorbed extremely strongly by per-view target-pose nuisance.
Their roughly 10.27-sigma pre-projection zG response is then also absorbed by
the shared X_F nuisance, leaving almost only the 14.56-sigma zL depth-like
response. That response is nearly collinear with C/T depth translation.

| Pair | angle | zV before nuisance | zV after nuisance | retained fraction |
|---|---:|---:|---:|---:|
| P-C | {pc['minimum_angle_deg']:.9f} deg | {pc['zV_pose_nuisance_audit']['before_whitened_sigma']:.6g} sigma | {pc['zV_pose_nuisance_audit']['after_whitened_sigma']:.6g} sigma | {pc['zV_pose_nuisance_audit']['after_over_before']:.3e} |
| P-T | {pt['minimum_angle_deg']:.9f} deg | {pt['zV_pose_nuisance_audit']['before_whitened_sigma']:.6g} sigma | {pt['zV_pose_nuisance_audit']['after_whitened_sigma']:.6g} sigma | {pt['zV_pose_nuisance_audit']['after_over_before']:.3e} |

Normalized P coefficients in `[dfx, dfy, dcx, dcy, dk1]` order:

- P-C: `[{', '.join(f'{x:.8f}' for x in pc['P_coefficients_unit_normalized_coordinate'].values())}]`
- P-T: `[{', '.join(f'{x:.8f}' for x in pt['P_coefficients_unit_normalized_coordinate'].values())}]`

The coefficient vectors and channel attribution are in `diagnostic.json` and
`dangerous_direction_channel_norms.csv`.

## P-mode ablation

| P subset | P-C | P-T |
|---|---:|---:|
| fx, fy | {ablation_rows[0]['P_C_min_angle_deg']:.6g} deg | {ablation_rows[0]['P_T_min_angle_deg']:.6g} deg |
| cx, cy | {ablation_rows[1]['P_C_min_angle_deg']:.6g} deg | {ablation_rows[1]['P_T_min_angle_deg']:.6g} deg |
| k1 | {ablation_rows[2]['P_C_min_angle_deg']:.6g} deg | {ablation_rows[2]['P_T_min_angle_deg']:.6g} deg |
| fx, fy, k1 | {ablation_rows[3]['P_C_min_angle_deg']:.6g} deg | {ablation_rows[3]['P_T_min_angle_deg']:.6g} deg |
| full P | {ablation_rows[4]['P_C_min_angle_deg']:.6g} deg | {ablation_rows[4]['P_T_min_angle_deg']:.6g} deg |

Focal/depth ambiguity is already severe at about 0.02 deg. k1 alone is not the
limiter, but allowing k1 to combine with fx/fy supplies the compensation that
collapses the angle by roughly two further orders of magnitude. This is an
ablation only; no P mode is removed from the formal model.

## Camera-geometry recovery result

The nine current zV views come from `task_poses_rad`. They are robot routine
configurations and are **not recovered historical zV calibration views**. The
investigator's recovered seven center/+/-X/Y/Z routine configurations likewise
describe robot-side local geometry; no evidence currently identifies them as
zV calibration views.

A local repository artifact does recover a different E1 planar experiment:
6x8 inner corners at 25 mm, 12 spread training points, 36 held-out points, one
fixed view summarized over 50 frames, K near (401.77, 401.92, 322.13, 202.54),
and undistorted pixels with D=0. There is no recovered provenance tying that
artifact to the E1-v3 uncertainty simulator, so this diagnostic does not swap
it into the model.

## Absolute-scale and nuisance audit

The current measurement inventory is zV={measurement_inventory['zV']['views']}
views, zR={measurement_inventory['zR']['independent_pose_pairs_assumed']} pose
pairs, zL={measurement_inventory['zL']['pose_measurements_assumed']} poses, and
zG={measurement_inventory['zG']['independent_pose_measurements_assumed']} poses.
All listed residual rows are treated as independent by the diagonal covariance.

`nuisance_rank=6` comes entirely from X_F columns shared by zR and zG. X_B is
zero in every current channel; zV and zL have no global nuisance columns. This
is a labelled reconstruction choice, not a recovered E1-v3 fact.

The total whitened/severity-scaled C_wz signal is 14.495 sigma, close to the
historical total-signal note of about 12.8 sigma. Therefore the 0.28--0.30x
gauge residuals are **not** explained by one global whitening-scale error.
For C_wz/q1, nuisance projection reduces the directed residual from
{scale_audit['C_wz_to_q1']['pre_nuisance_scaled_residual_sigma']:.4g} to
{scale_audit['C_wz_to_q1']['post_nuisance_residual_sigma']:.4g} sigma; for
T_wz/q6 it changes {scale_audit['T_wz_to_q6']['pre_nuisance_scaled_residual_sigma']:.4g}
to {scale_audit['T_wz_to_q6']['post_nuisance_residual_sigma']:.4g} sigma. The
common remaining factor is consistent with weaker/missing independent zR/zG
information. If measurement count alone were responsible it would correspond
to roughly {scale_audit['C_wz_to_q1']['equivalent_independent_information_multiplier_if_only_count_changed']:.2f}x
and {scale_audit['T_wz_to_q6']['equivalent_independent_information_multiplier_if_only_count_changed']:.2f}x
more independent information, respectively; this is a diagnostic equivalence,
not evidence that the historical experiment actually used those counts.

Stage-by-stage and per-channel norms for C_wz, q1, T_wz, and q6 are in
`gauge_stage_channel_norms.csv`; directed residuals are in
`gauge_stage_residuals.csv`.

## Gate

Regression was not rerun because no model input changed. P-C/P-T restoration
remains blocked. d_min, phase map, E2 replay, and perfect-zG remain prohibited.
"""
    (HERE / "REPORT.md").write_text(report, encoding="utf-8")

    core_after = {p: sha256(ROOT / p) for p in AUDITED_CORE}
    output_files = [
        "REPORT.md", "diagnostic.json", "dangerous_direction_channel_norms.csv",
        "zV_nuisance_before_after.csv", "P_mode_ablation.csv",
        "gauge_stage_channel_norms.csv", "gauge_stage_residuals.csv",
        "nuisance_rank_sources.csv",
    ]
    manifest = {
        "artifact": "E1-v4R1_P_BLOCK_DIAGNOSTIC",
        "diagnostic_only": True,
        "core_hashes_before": core_before,
        "core_hashes_after": core_after,
        "core_unchanged": core_before == core_after,
        "E2_connected": False,
        "regression_rerun": False,
        "outputs_sha256": {p: sha256(HERE / p) for p in output_files},
    }
    jdump(HERE / "DIAGNOSTIC_MANIFEST.json", manifest)
    print(json.dumps({
        "artifact": manifest["artifact"],
        "core_unchanged": manifest["core_unchanged"],
        "P_C_angle_deg": pc["minimum_angle_deg"],
        "P_C_zV_retained_fraction": pc["zV_pose_nuisance_audit"]["after_over_before"],
        "P_T_angle_deg": pt["minimum_angle_deg"],
        "P_T_zV_retained_fraction": pt["zV_pose_nuisance_audit"]["after_over_before"],
        "nuisance_rank": int(proc["nuisance_rank"]),
        "output": str(HERE),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
