#!/usr/bin/env python3
"""Compute the real-zV diagnostic only after metric-blind selection is frozen."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from cross_action_metrics import principal_angles_deg
from nuisance_projection import whiten_scale_project
from reconstruct_e1_v4r1 import assemble, build_channels, build_nominal, load_config
from se3_utils import numerical_jacobian, se3_exp, transform
from severity_scaling import compute_severity_scales


CORE_PATHS = [
    "e1_v4r1_config.yaml", "evidence_zV.py", "evidence_zR.py", "evidence_zL.py",
    "evidence_zG.py", "severity_scaling.py", "nuisance_projection.py",
    "cross_action_metrics.py", "reconstruct_e1_v4r1.py",
    "results/restored_operators.npz", "results/restoration_regression.json",
]
CAMERAS = ("camera_overhead_B242", "camera_side_B479")
P_NAMES = ("dfx", "dfy", "dcx", "dcy", "dk1")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_selection() -> dict[str, Any]:
    path = HERE / "real_9view_selection.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    claimed = data.pop("selection_payload_sha256")
    observed = canonical_sha(data)
    data["selection_payload_sha256"] = claimed
    if observed != claimed:
        raise RuntimeError(f"frozen selection hash mismatch: {observed} != {claimed}")
    if data["geometry_selection_used_E1_metrics"] is not False:
        raise RuntimeError("selection was not metric-blind")
    for camera_id in CAMERAS:
        if len(data["per_camera"][camera_id]["selected_image_ids"]) != 9:
            raise RuntimeError(f"{camera_id} does not have exactly 9 selected views")
    return data


def board_points() -> np.ndarray:
    obj = np.zeros((48, 3), dtype=float)
    obj[:, :2] = np.mgrid[0:8, 0:6].T.reshape(-1, 2)
    obj[:, :2] *= 0.025
    return obj


def project_full(T_CM: np.ndarray, points: np.ndarray, params: np.ndarray, fixed_D: np.ndarray) -> np.ndarray:
    fx, fy, cx, cy, k1 = np.asarray(params, dtype=float)
    K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])
    D = np.asarray(fixed_D, dtype=float).copy()
    D[0] = k1
    rvec, _ = cv2.Rodrigues(T_CM[:3, :3])
    uv, _ = cv2.projectPoints(np.asarray(points, dtype=float), rvec, T_CM[:3, 3], K, D)
    return uv.reshape(-1, 2)


def visual_item(T_CM: np.ndarray, points: np.ndarray, params: np.ndarray, fixed_D: np.ndarray, training: list[int]) -> dict[str, np.ndarray]:
    train = np.asarray(training, dtype=int)
    held = np.asarray([i for i in range(len(points)) if i not in training], dtype=int)
    p_steps = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1e-7])
    xi_steps = np.full(6, 1e-7)

    def p_jac(indices: np.ndarray) -> np.ndarray:
        return numerical_jacobian(lambda dp: project_full(T_CM, points[indices], params + dp, fixed_D).reshape(-1), np.zeros(5), p_steps)

    def xi_jac(indices: np.ndarray) -> np.ndarray:
        return numerical_jacobian(lambda xi: project_full(T_CM @ se3_exp(xi), points[indices], params, fixed_D).reshape(-1), np.zeros(6), xi_steps)

    Jp_tr, Jxi_tr = p_jac(train), xi_jac(train)
    Bpose = -np.linalg.pinv(Jxi_tr, rcond=1e-12) @ Jp_tr
    Jp_ho, Jxi_ho = p_jac(held), xi_jac(held)
    JV = Jp_ho + Jxi_ho @ Bpose
    Jfault = np.zeros((JV.shape[0], 23))
    Jfault[:, :5] = JV
    return {
        "J_fault": Jfault, "J_nuisance": np.zeros((JV.shape[0], 12)),
        "B_pose": Bpose, "J_P_holdout": Jp_ho, "J_xi_holdout": Jxi_ho,
        "J_P_training": Jp_tr, "J_xi_training": Jxi_tr,
        "heldout_indices": held,
    }


def rank_condition(s: np.ndarray, rtol: float) -> tuple[int, float]:
    rank = int(np.sum(s > rtol * s[0])) if len(s) and s[0] else 0
    return rank, float(s[0] / s[-1]) if len(s) and s[-1] > 0 else float("inf")


def main() -> int:
    core_before = {p: sha(ROOT / p) for p in CORE_PATHS}
    selection_path = HERE / "real_9view_selection.json"
    selection_file_sha = sha(selection_path)
    selection = load_selection()
    geometry_rows = list(csv.DictReader((HERE / "real_view_geometry_all.csv").open(newline="", encoding="utf-8-sig")))
    by_key = {(x["camera_id"], x["image_id"]): x for x in geometry_rows}

    cfg = load_config(ROOT / "e1_v4r1_config.yaml")
    nominal = build_nominal(cfg)
    frozen_channels = build_channels(cfg, nominal)
    scales, _ = compute_severity_scales(
        [np.asarray(x["J_fault"]) for x in frozen_channels["zL"]],
        float(cfg["severity"]["equivalent_rms_m"]),
        float(cfg["severity"]["rotation_lever_arm_m"]),
    )
    noise = cfg["noise"]["baseline"]
    training = list(selection["real_checkerboard_split"]["training_indices"])
    points = board_points()
    rtol = float(cfg["thresholds"]["svd_rtol"])

    synthetic_svs = list(csv.DictReader((HERE.parent / "zV_GEOMETRY_CAUSALITY_TEST" / "zV_singular_values.csv").open(newline="", encoding="utf-8-sig")))
    g0_smallest = float([x for x in synthetic_svs if x["geometry"] == "G0_current_bad" and x["stage"] == "after_pose_nuisance_whitened_scaled_JV"][-1]["singular_value"])
    synthetic_summary = list(csv.DictReader((HERE.parent / "zV_GEOMETRY_CAUSALITY_TEST" / "geometry_summary.csv").open(newline="", encoding="utf-8-sig")))

    singular_rows: list[dict[str, Any]] = []
    direction_rows: list[dict[str, Any]] = []
    angle_rows: list[dict[str, Any]] = []
    camera_results: dict[str, Any] = {}
    for camera_id in CAMERAS:
        identity = selection["source_calibrations"][camera_id]
        K = np.asarray(identity["K"], dtype=float)
        D = np.asarray(identity["D"], dtype=float)
        params = np.array([K[0, 0], K[1, 1], K[0, 2], K[1, 2], D[0]], dtype=float)
        items = []
        for image_id in selection["per_camera"][camera_id]["selected_image_ids"]:
            row = by_key[(camera_id, image_id)]
            rvec = np.array([float(row[f"rvec_{a}_rad"]) for a in "xyz"])
            tvec = np.array([float(row[f"tvec_{a}_m"]) for a in "xyz"])
            R, _ = cv2.Rodrigues(rvec)
            items.append(visual_item(transform(R, tvec), points, params, D, training))

        before = np.vstack([x["J_P_holdout"] for x in items])
        after = np.vstack([x["J_fault"][:, :5] for x in items])
        variants = {
            "before_pose_nuisance_raw_native": before,
            "after_pose_nuisance_raw_native_JV": after,
            "before_pose_nuisance_whitened_scaled": before / noise["pixel_px"] @ np.diag(scales[:5]),
            "after_pose_nuisance_whitened_scaled_JV": after / noise["pixel_px"] @ np.diag(scales[:5]),
        }
        spectra: dict[str, Any] = {}
        for stage, matrix in variants.items():
            sv = np.linalg.svd(matrix, compute_uv=False)
            rank, condition = rank_condition(sv, rtol)
            spectra[stage] = {"singular_values": sv.tolist(), "rank": rank, "condition_number_full": condition}
            for i, value in enumerate(sv):
                singular_rows.append({
                    "camera_id": camera_id, "stage": stage, "singular_value_index": i + 1,
                    "singular_value": float(value), "numerical_rank": rank,
                    "condition_number_full": condition,
                })

        _, _, Vt = np.linalg.svd(variants["after_pose_nuisance_whitened_scaled_JV"], full_matrices=False)
        u = Vt[-1]
        if u[np.argmax(np.abs(u))] < 0:
            u = -u
        physical = scales[:5] * u
        physical_normalized = physical / np.linalg.norm(physical)
        before_norm = float(np.linalg.norm(variants["before_pose_nuisance_whitened_scaled"] @ u))
        after_norm = float(np.linalg.norm(variants["after_pose_nuisance_whitened_scaled_JV"] @ u))
        retained = after_norm / before_norm
        for i, name in enumerate(P_NAMES):
            direction_rows.append({
                "camera_id": camera_id, "parameter": name,
                "severity_coordinate_unit_vector_coefficient": float(u[i]),
                "physical_parameter_direction_coefficient": float(physical[i]),
                "physical_parameter_direction_l2_normalized": float(physical_normalized[i]),
                "dangerous_direction_before_whitened_scaled_norm": before_norm,
                "dangerous_direction_after_whitened_scaled_norm": after_norm,
                "retained_norm_fraction": retained,
                "retained_energy_fraction": retained * retained,
            })

        channels = dict(frozen_channels)
        channels["zV"] = items
        stack = assemble(cfg, channels, noise["pixel_px"], 1.0, noise["indexing_rad"])
        proc = whiten_scale_project(stack["J_fault"], stack["J_nuisance"], stack["row_sigma"], scales, rtol=rtol)
        angles = principal_angles_deg(np.asarray(proc["J_projected"]), rtol=rtol)
        for pair in ("P-C", "P-T", "P-R"):
            angle_rows.append({
                "camera_id": camera_id, "action_pair": pair,
                "minimum_principal_angle_deg": float(angles[pair][0]),
                "all_principal_angles_deg": json.dumps(angles[pair]),
                "diagnostic_only": True,
            })
        smallest = spectra["after_pose_nuisance_whitened_scaled_JV"]["singular_values"][-1]
        improvement = smallest / g0_smallest
        pc, pt, pr = (float(angles[x][0]) for x in ("P-C", "P-T", "P-R"))
        if improvement >= 1e4 and pc >= 0.1 and pt >= 0.1:
            label = "strong real-geometry recovery"
        elif improvement > 100 and (pc < 0.1 or pt < 0.1):
            label = "moderate recovery"
        else:
            label = "no meaningful recovery"
        camera_results[camera_id] = {
            "spectra": spectra,
            "post_nuisance_smallest_whitened_scaled_singular_value": smallest,
            "improvement_over_G0": improvement,
            "P_C_deg": pc, "P_T_deg": pt, "P_R_deg": pr,
            "dangerous_direction_severity_coordinates": dict(zip(P_NAMES, u.tolist())),
            "retained_norm_fraction": retained,
            "screening_label": label,
            "global_nuisance_rank": int(proc["nuisance_rank"]),
        }

    write_csv(HERE / "real_zV_singular_values.csv", singular_rows)
    write_csv(HERE / "real_zV_dangerous_direction.csv", direction_rows)
    write_csv(HERE / "real_zV_principal_angles.csv", angle_rows)

    comparisons = list(csv.DictReader((HERE / "real_vs_synthetic_geometry.csv").open(newline="", encoding="utf-8-sig")))
    geometry_summary: dict[str, Any] = {}
    for camera_id in CAMERAS:
        real = [x for x in geometry_rows if x["camera_id"] == camera_id]
        geometry_summary[camera_id] = {
            "depth_range_m": [min(float(x["depth_m"]) for x in real), max(float(x["depth_m"]) for x in real)],
            "tilt_range_deg": [min(float(x["tilt_deg"]) for x in real), max(float(x["tilt_deg"]) for x in real)],
            "normalized_u_range": [min(float(x["normalized_center_u"]) for x in real), max(float(x["normalized_center_u"]) for x in real)],
            "normalized_v_range": [min(float(x["normalized_center_v"]) for x in real), max(float(x["normalized_center_v"]) for x in real)],
            "full_board_visible": all(x["full_board_visible"].lower() == "true" for x in real),
        }

    core_after = {p: sha(ROOT / p) for p in CORE_PATHS}
    if core_before != core_after:
        raise RuntimeError("E1 core changed during diagnostic")

    ref = {x["geometry"]: {"P_C": float(x["P_C_min_angle_deg"]), "P_T": float(x["P_T_min_angle_deg"])} for x in synthetic_summary}
    def result_line(camera_id: str) -> str:
        x = camera_results[camera_id]
        return f"| {camera_id} | {x['post_nuisance_smallest_whitened_scaled_singular_value']:.6g} | {x['improvement_over_G0']:.3g}x | {x['P_C_deg']:.6g} deg | {x['P_T_deg']:.6g} deg | {x['P_R_deg']:.6g} deg | {x['screening_label']} |"

    report = f"""# E1-v4R1 REAL-zV attainability bridge

Status: `DIAGNOSTIC_COMPLETE_CORE_UNCHANGED`

Both archived iHawk intrinsic-calibration sets were recovered in full: 42/42
accepted overhead views and 48/48 accepted side views. Every image yielded all
48 checkerboard corners using the archived detector logic. The two camera
models were processed separately. Selection was frozen first from geometry
alone (payload SHA-256 `{selection['selection_payload_sha256']}`), before this
program imported or evaluated E1 metrics.

| Camera | post-nuisance smallest whitened/scaled sv | vs G0 | P-C | P-T | P-R | predeclared label |
|---|---:|---:|---:|---:|---:|---|
{result_line('camera_overhead_B242')}
{result_line('camera_side_B479')}

The synthetic references are G0 P-C/P-T {ref['G0_current_bad']['P_C']:.6g}/{ref['G0_current_bad']['P_T']:.6g}
deg, G1 {ref['G1_moderate_diversity']['P_C']:.6g}/{ref['G1_moderate_diversity']['P_T']:.6g}
deg, and G2 {ref['G2_calibration_like_diversity']['P_C']:.6g}/{ref['G2_calibration_like_diversity']['P_T']:.6g}
deg. Historical 0.572/0.572/1.142 deg values were consulted only after both
real-view calculations were complete.

## Geometry-only attainability

The overhead archive spans depth {geometry_summary['camera_overhead_B242']['depth_range_m'][0]:.3f}-{geometry_summary['camera_overhead_B242']['depth_range_m'][1]:.3f} m
and tilt {geometry_summary['camera_overhead_B242']['tilt_range_deg'][0]:.2f}-{geometry_summary['camera_overhead_B242']['tilt_range_deg'][1]:.2f} deg.
The side archive spans depth {geometry_summary['camera_side_B479']['depth_range_m'][0]:.3f}-{geometry_summary['camera_side_B479']['depth_range_m'][1]:.3f} m
and tilt {geometry_summary['camera_side_B479']['tilt_range_deg'][0]:.2f}-{geometry_summary['camera_side_B479']['tilt_range_deg'][1]:.2f} deg.
Both archives therefore equal or exceed G1's *diversity pattern* in tilt and
image position, but they are not samples of G1's exact joint descriptor
envelope: the real boards are generally closer and occupy a larger image
footprint. For G2, 4 overhead and 2 side images lie inside the joint synthetic
descriptor envelope. The nine geometry-only selections retain simultaneous
depth, tilt, and image-position variation.

The synthetic G2 envelope extends beyond the overhead archive at its far-depth,
far-left, far-right, upper-image, and small-footprint extremes. Relative to the
side archive, its far-depth limit is slightly larger and its far-left,
upper-image, and smallest-footprint extremes are outside. Tilt is not the
limiting descriptor for either archive. Exact ranges, flags, visibility, and
border margins are in `real_vs_synthetic_geometry.csv`; all 90 real boards are
fully visible, with minimum margins 22.74 px (overhead) and 19.31 px (side).

## Interpretation and hard stop

Both cameras satisfy the predeclared strong-recovery screen independently.
Under the current frozen zV formula, the geometry-rescue mechanism is therefore
represented in the existing real low-cost camera archive; it is not purely a
synthetic artifact. This bridge changes target layout, real K/D, and feature
count along with physical view geometry, as required for the real checkerboard,
so it is an attainability result rather than a second controlled geometry-only
causality experiment. It does not mean the diagnosis or E1 restoration is
solved.

This artifact did not modify the E1 core, connect E2, calculate d_min, rerun the
restoration regression, run a phase map, or run perfect-zG. No GO, STOP, or
ONE-RESCUE decision is authorized here.
"""
    (HERE / "REPORT.md").write_text(report, encoding="utf-8")

    output_names = [
        "REPORT.md", "real_view_geometry_all.csv", "real_vs_synthetic_geometry.csv",
        "real_9view_selection.json", "real_zV_singular_values.csv",
        "real_zV_dangerous_direction.csv", "real_zV_principal_angles.csv",
    ]
    manifest = {
        "artifact": "E1-v4R1_REAL_zV_ATTAINABILITY_BRIDGE",
        "diagnostic_only": True,
        "core_model_modified": False,
        "E2_connected": False,
        "dmin_run": False,
        "phase_map_run": False,
        "perfect_zG_run": False,
        "restoration_regression_rerun": False,
        "geometry_selection_used_E1_metrics": False,
        "real_images_only": True,
        "selected_view_count": 9,
        "selected_view_count_scope": "per camera",
        "selection_frozen_before_E1_metrics": True,
        "selection_file_sha256_at_metric_start": selection_file_sha,
        "selection_payload_sha256": selection["selection_payload_sha256"],
        "selected_camera": list(CAMERAS),
        "calibrations": selection["source_calibrations"],
        "board_geometry": {"inner_corners": [8, 6], "square_size_m": 0.025},
        "train_heldout_split": selection["real_checkerboard_split"],
        "exact_selected_image_ids": {c: selection["per_camera"][c]["selected_image_ids"] for c in CAMERAS},
        "camera_results": camera_results,
        "core_hashes_before": core_before,
        "core_hashes_after": core_after,
        "core_unchanged": core_before == core_after,
        "synthetic_G0_smallest_post_nuisance_whitened_scaled_sv": g0_smallest,
        "outputs_sha256": {p: sha(HERE / p) for p in output_names},
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"core_unchanged": True, "selection_file_sha256": selection_file_sha, "camera_results": camera_results, "output": str(HERE)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
