#!/usr/bin/env python3
"""E2-v1R0: corrected rigid-board PnP and clean hierarchical decomposition.

Primary measurement: one 20-corner rigid-board pose per camera/run/height/frame.
Single-marker IPPE is retained only as an untrimmed failure-mode comparator.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from build_empirical_components import (
    D,
    K,
    ROOT,
    XI_NAMES,
    flatten_cov,
    inv_T,
    make_T,
    read_csv,
    sample_cov,
    se3_exp,
    se3_log,
    se3_mean,
    sigma_fields,
    transform_fields,
    translation_T,
    write_csv,
    xi_fields,
)


HERE = Path(__file__).resolve().parent
OUT = HERE / "E2-v1R0_board_pose" / "results"
E2_ROOT = ROOT / "E2" / "E2_dual_camera_height_scan"
E2_MANIFEST = ROOT / "E2" / "E2_rebuilt" / "E2_REBUILD_MANIFEST.json"
MARKER_HALF_MM = 25.0
SE3_COV_NAMES = [f"cov_{a}_{b}" for a in XI_NAMES for b in XI_NAMES]

# Confirmed printed-board geometry: A4 210 x 297 mm, 50 mm markers, 10 mm
# margin from each outer marker edge to the paper edge.
ACTUAL_CENTRES = {
    "TL": (-70.0, +113.5),
    "TR": (+70.0, +113.5),
    "C": (0.0, 0.0),
    "BL": (-70.0, -113.5),
    "BR": (+70.0, -113.5),
}

# Incorrect acquisition-time assumption retained for the geometry audit only.
LOGGED_CENTRES = {
    "TL": (-80.0, +123.5),
    "TR": (+80.0, +123.5),
    "C": (0.0, 0.0),
    "BL": (-80.0, -123.5),
    "BR": (+80.0, -123.5),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def board_points(rows: list[dict[str, str]], centres: dict[str, tuple[float, float]]):
    obj, img = [], []
    ordered = sorted(rows, key=lambda r: int(float(r["marker_id"])))
    if len(ordered) != 5 or {r["board_position"] for r in ordered} != set(ACTUAL_CENTRES):
        raise RuntimeError("A board frame must contain exactly TL/TR/C/BL/BR")
    for r in ordered:
        x, y = centres[r["board_position"]]
        obj.extend([
            [x - MARKER_HALF_MM, y + MARKER_HALF_MM, 0.0],
            [x + MARKER_HALF_MM, y + MARKER_HALF_MM, 0.0],
            [x + MARKER_HALF_MM, y - MARKER_HALF_MM, 0.0],
            [x - MARKER_HALF_MM, y - MARKER_HALF_MM, 0.0],
        ])
        img.extend([
            [float(r[f"corner{j}_u_undist_px"]), float(r[f"corner{j}_v_undist_px"])]
            for j in range(4)
        ])
    return np.asarray(obj, dtype=np.float64), np.asarray(img, dtype=np.float64)


def marker_points(row: dict[str, str]):
    obj = np.array([
        [-MARKER_HALF_MM, +MARKER_HALF_MM, 0.0],
        [+MARKER_HALF_MM, +MARKER_HALF_MM, 0.0],
        [+MARKER_HALF_MM, -MARKER_HALF_MM, 0.0],
        [-MARKER_HALF_MM, -MARKER_HALF_MM, 0.0],
    ], dtype=np.float64)
    img = np.array([
        [float(row[f"corner{j}_u_undist_px"]), float(row[f"corner{j}_v_undist_px"])]
        for j in range(4)
    ], dtype=np.float64)
    return obj, img


def reprojection_rmse(obj, img, camera, rvec, tvec) -> float:
    pred, _ = cv2.projectPoints(obj, rvec, tvec, K[camera], D)
    return float(np.sqrt(np.mean(np.sum((pred.reshape(-1, 2) - img) ** 2, axis=1))))


def solve_planar_candidates(obj, img, camera, square: bool = False):
    flag = cv2.SOLVEPNP_IPPE_SQUARE if square else cv2.SOLVEPNP_IPPE
    result = cv2.solvePnPGeneric(obj, img, K[camera], D, flags=flag)
    if not result[0] or len(result[1]) == 0:
        raise RuntimeError(f"{camera}: planar PnP produced no solution")
    candidates = []
    for native_index, (rvec, tvec) in enumerate(zip(result[1], result[2])):
        candidates.append({
            "native_index": native_index,
            "rvec": np.asarray(rvec, dtype=float).reshape(3, 1),
            "tvec": np.asarray(tvec, dtype=float).reshape(3, 1),
            "T": make_T(rvec, tvec),
            "reprojection_rmse_px": reprojection_rmse(obj, img, camera, rvec, tvec),
            "positive_depth": bool(float(np.asarray(tvec).reshape(3)[2]) > 0.0),
        })
    candidates.sort(key=lambda c: (not c["positive_depth"], c["reprojection_rmse_px"]))
    return candidates


def refine_board_candidate(obj, img, camera, candidate):
    rvec, tvec = cv2.solvePnPRefineLM(
        obj, img, K[camera], D, candidate["rvec"].copy(), candidate["tvec"].copy())
    return make_T(rvec, tvec), reprojection_rmse(obj, img, camera, rvec, tvec)


def rotation_distance(Ta: np.ndarray, Tb: np.ndarray) -> float:
    return float(np.linalg.norm(se3_log(inv_T(Ta) @ Tb)[3:]))


def assign_consistent_branches(frame_candidates: list[list[dict]]) -> list[list[str]]:
    """Label each two-solution frame A/B consistently by rotation proximity."""
    if not frame_candidates or any(len(c) < 2 for c in frame_candidates):
        return [["A"] + [f"extra_{i}" for i in range(1, len(c))] for c in frame_candidates]
    ref_a, ref_b = frame_candidates[0][0]["T"], frame_candidates[0][1]["T"]
    labels = [["A", "B"]]
    for candidates in frame_candidates[1:]:
        direct = rotation_distance(ref_a, candidates[0]["T"]) + rotation_distance(ref_b, candidates[1]["T"])
        swapped = rotation_distance(ref_a, candidates[1]["T"]) + rotation_distance(ref_b, candidates[0]["T"])
        labels.append(["A", "B"] if direct <= swapped else ["B", "A"])
    return labels


def load_retained_raw():
    manifest = json.loads(E2_MANIFEST.read_text(encoding="utf-8"))
    rows, paths = [], []
    for run in manifest["formal_runs"]:
        path = E2_ROOT / f"run_{run}" / "raw" / f"E2_dual_height_raw_{run}.csv"
        keep = {int(v) for v in manifest["retained_height_steps"][run].values()}
        retained = [r for r in read_csv(path) if int(float(r["height_step_index"])) in keep]
        if len(retained) != 330:
            raise RuntimeError(f"{run}: expected 330 retained rows, found {len(retained)}")
        rows.extend(retained)
        paths.append(path)
    return rows, paths, manifest


def pooled_within_cov(residual_groups: list[np.ndarray]) -> tuple[np.ndarray, int]:
    dof = sum(len(x) - 1 for x in residual_groups)
    if dof <= 0:
        raise ValueError("No pooled within degrees of freedom")
    scatter = sum(x.T @ x for x in residual_groups)
    return scatter / dof, dof


def pairwise_max(transforms: list[np.ndarray]) -> tuple[float, float]:
    rho, omega = 0.0, 0.0
    for i in range(len(transforms)):
        for j in range(i + 1, len(transforms)):
            xi = se3_log(inv_T(transforms[i]) @ transforms[j])
            rho = max(rho, float(np.linalg.norm(xi[:3])))
            omega = max(omega, float(np.linalg.norm(xi[3:])))
    return rho, omega


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw, source_paths, source_manifest = load_retained_raw()

    frame_groups = defaultdict(list)
    marker_groups = defaultdict(list)
    for r in raw:
        frame_key = (r["camera_id"], r["run_id"], float(r["height_gt_mm"]), int(float(r["frame_index"])))
        marker_key = frame_key[:3] + (int(float(r["marker_id"])),)
        frame_groups[frame_key].append(r)
        marker_groups[marker_key].append(r)
    if len(frame_groups) != 330 or len(marker_groups) != 550:
        raise RuntimeError(f"Unexpected E2 grouping: frames={len(frame_groups)}, marker groups={len(marker_groups)}")

    geometry_rows = []
    frame_records = {}
    board_candidate_rows = []
    # First solve and retain both board-level planar candidates under both
    # geometry hypotheses. Only ACTUAL_CENTRES proceeds to the primary channel.
    for key, rows in sorted(frame_groups.items()):
        camera, run, height, frame = key
        for geometry_name, centres in (("actual_margin10", ACTUAL_CENTRES), ("logged_edge_aligned", LOGGED_CENTRES)):
            obj, img = board_points(rows, centres)
            candidates = solve_planar_candidates(obj, img, camera, square=False)
            geometry_rows.append({
                "camera": camera, "run_id": run, "height_mm": height, "frame_index": frame,
                "geometry": geometry_name, "best_reprojection_rmse_px": candidates[0]["reprojection_rmse_px"],
                "second_reprojection_rmse_px": candidates[1]["reprojection_rmse_px"] if len(candidates) > 1 else "",
                "n_board_corners": len(obj),
            })
            if geometry_name != "actual_margin10":
                continue
            primary_T, refined_rmse = refine_board_candidate(obj, img, camera, candidates[0])
            frame_records[key] = {
                "candidates": candidates, "primary_T": primary_T, "refined_rmse": refined_rmse,
                "branch_gap_px": (candidates[1]["reprojection_rmse_px"] - candidates[0]["reprojection_rmse_px"])
                if len(candidates) > 1 else float("nan"),
            }

    # Label candidate branches consistently inside each camera/run/height group.
    condition_frames = defaultdict(list)
    for key in frame_records:
        condition_frames[key[:3]].append(key)
    board_group_branch = {}
    for condition, keys in sorted(condition_frames.items()):
        keys.sort(key=lambda k: k[3])
        candidate_sets = [frame_records[k]["candidates"] for k in keys]
        labels = assign_consistent_branches(candidate_sets)
        selected_labels = []
        for key, candidates, frame_labels in zip(keys, candidate_sets, labels):
            frame_records[key]["selected_branch"] = frame_labels[0]
            selected_labels.append(frame_labels[0])
            for candidate, label in zip(candidates, frame_labels):
                board_candidate_rows.append({
                    "camera": key[0], "run_id": key[1], "height_mm": key[2], "frame_index": key[3],
                    "branch_label": label, "selected_by_reprojection": int(candidate is candidates[0]),
                    "native_solution_index": candidate["native_index"], "positive_depth": int(candidate["positive_depth"]),
                    "reprojection_rmse_px": candidate["reprojection_rmse_px"],
                    **transform_fields(candidate["T"]),
                })
        board_group_branch[condition] = {
            "sequence": "/".join(selected_labels),
            "switch": len(set(selected_labels)) > 1,
        }

    board_frame_rows = []
    board_within_rows = []
    board_residual_rows = []
    group_means = {}
    group_residuals = {}
    for condition, keys in sorted(condition_frames.items()):
        camera, run, height = condition
        keys.sort(key=lambda k: k[3])
        transforms = [frame_records[k]["primary_T"] for k in keys]
        mean = se3_mean(transforms)
        residuals = np.vstack([se3_log(inv_T(mean) @ T) for T in transforms])
        cov = sample_cov(residuals)
        group_means[condition] = mean
        group_residuals[condition] = residuals
        max_rho, max_omega = pairwise_max(transforms)
        branch = board_group_branch[condition]
        board_within_rows.append({
            "camera": camera, "run_id": run, "height_mm": height, "n_frames": len(keys),
            "covariance_rank": int(np.linalg.matrix_rank(cov)), "selected_branch_sequence": branch["sequence"],
            "branch_switch_flag": int(branch["switch"]), "max_pairwise_rho_mm": max_rho,
            "max_pairwise_omega_rad": max_omega, **transform_fields(mean), **sigma_fields(cov),
            **flatten_cov(cov, SE3_COV_NAMES),
        })
        for key, T, xi in zip(keys, transforms, residuals):
            rec = frame_records[key]
            board_frame_rows.append({
                "camera": camera, "run_id": run, "height_mm": height, "frame_index": key[3],
                "selected_branch": rec["selected_branch"], "group_branch_switch_flag": int(branch["switch"]),
                "branch_gap_px": rec["branch_gap_px"], "refined_reprojection_rmse_px": rec["refined_rmse"],
                **transform_fields(T),
            })
            board_residual_rows.append({
                "camera": camera, "run_id": run, "height_mm": height, "frame_index": key[3],
                **xi_fields(xi), "definition": "Log(inv(T_bar_camera_run_height) @ T_frame)",
            })

    # Pooled random measurement covariance. Residual scatter is divided by the
    # correct within-condition degrees of freedom sum_g(n_g-1), not N-1.
    pooled_rows = []
    for camera in K:
        for height in sorted({key[2] for key in group_residuals if key[0] == camera}):
            groups = [x for key, x in group_residuals.items() if key[0] == camera and key[2] == height]
            cov, dof = pooled_within_cov(groups)
            pooled_rows.append({
                "camera": camera, "height_mm": height, "n_runs": len(groups),
                "n_residual_vectors": sum(len(x) for x in groups), "within_dof": dof,
                "covariance_rank": int(np.linalg.matrix_rank(cov)), **sigma_fields(cov),
                **flatten_cov(cov, SE3_COV_NAMES),
                "semantics": "Sigma_within random board-pose measurement covariance only",
            })

    # Hierarchy:
    # E_run,h = inv(T_run,0 * Trans(0,0,h)) * T_bar_run,h
    # b_pose(h) is the across-run SE(3) mean of E_run,h.
    # b_run bank keeps baseline placement and condition residuals as empirical
    # vectors; no 6-D Gaussian is fitted to them.
    b_pose_rows = []
    b_run_rows = []
    for camera in K:
        runs = sorted({key[1] for key in group_means if key[0] == camera})
        baseline_means = [group_means[(camera, run, 0.0)] for run in runs]
        grand_baseline = se3_mean(baseline_means)
        for run in runs:
            xi = se3_log(inv_T(grand_baseline) @ group_means[(camera, run, 0.0)])
            b_run_rows.append({
                "camera": camera, "height_mm": 0.0, "run_id": run, "bias_kind": "baseline_placement",
                **xi_fields(xi, "b_run_"), "gaussian_fit": 0,
                "definition": "Log(inv(T_bar_camera_height0) @ T_bar_camera_run_height0)",
            })

        for height in sorted({key[2] for key in group_means if key[0] == camera}):
            errors = []
            for run in runs:
                expected = group_means[(camera, run, 0.0)] @ translation_T(0.0, 0.0, height)
                errors.append((run, inv_T(expected) @ group_means[(camera, run, height)]))
            pose_bias_T = se3_mean([T for _, T in errors])
            pose_bias_xi = se3_log(pose_bias_T)
            b_pose_rows.append({
                "camera": camera, "height_mm": height, "n_runs": len(errors),
                **xi_fields(pose_bias_xi, "b_pose_"),
                "definition": "SE3 mean across runs of inv(T_bar_run_0*Trans_z(height)) @ T_bar_run_height",
            })
            for run, error_T in errors:
                xi = se3_log(inv_T(pose_bias_T) @ error_T)
                b_run_rows.append({
                    "camera": camera, "height_mm": height, "run_id": run, "bias_kind": "condition_residual",
                    **xi_fields(xi, "b_run_"), "gaussian_fit": 0,
                    "definition": "Log(inv(Exp(b_pose_height)) @ E_run_height)",
                })

    # Single-marker IPPE failure-mode comparator, retaining both candidates and
    # exact selected-branch switching. No observation is clipped.
    single_rows = []
    single_candidate_rows = []
    for condition, rows in sorted(marker_groups.items()):
        camera, run, height, marker = condition
        rows.sort(key=lambda r: int(float(r["frame_index"])))
        candidate_sets = []
        stored_transforms = []
        for r in rows:
            obj, img = marker_points(r)
            candidates = solve_planar_candidates(obj, img, camera, square=True)
            candidate_sets.append(candidates)
            stored_transforms.append(make_T(
                np.array([float(r["pnp_rvec_x"]), float(r["pnp_rvec_y"]), float(r["pnp_rvec_z"])]),
                np.array([float(r["pnp_tx_camera_mm"]), float(r["pnp_ty_camera_mm"]), float(r["pnp_tz_camera_mm"])]),
            ))
        labels = assign_consistent_branches(candidate_sets)
        selected_labels = []
        for r, candidates, frame_labels, stored_T in zip(rows, candidate_sets, labels, stored_transforms):
            distances = [np.linalg.norm(se3_log(inv_T(c["T"]) @ stored_T)) for c in candidates]
            selected_index = int(np.argmin(distances))
            selected_labels.append(frame_labels[selected_index])
            for index, (candidate, label) in enumerate(zip(candidates, frame_labels)):
                single_candidate_rows.append({
                    "camera": camera, "run_id": run, "height_mm": height, "marker_id": marker,
                    "board_position": r["board_position"], "frame_index": int(float(r["frame_index"])),
                    "branch_label": label, "matches_acquisition_solution": int(index == selected_index),
                    "reprojection_rmse_px": candidate["reprojection_rmse_px"], **transform_fields(candidate["T"]),
                })
        mean = se3_mean(stored_transforms)
        residuals = np.vstack([se3_log(inv_T(mean) @ T) for T in stored_transforms])
        cov = sample_cov(residuals)
        max_rho, max_omega = pairwise_max(stored_transforms)
        single_rows.append({
            "camera": camera, "run_id": run, "height_mm": height, "marker_id": marker,
            "board_position": rows[0]["board_position"], "n_frames": len(rows),
            "selected_branch_sequence": "/".join(selected_labels),
            "branch_switch_flag": int(len(set(selected_labels)) > 1),
            "large_mode_jump_flag": int(max_omega > 0.25),
            "max_pairwise_rho_mm": max_rho, "max_pairwise_omega_rad": max_omega,
            "covariance_rank": int(np.linalg.matrix_rank(cov)), **sigma_fields(cov),
            "role": "failure_mode_comparator_not_primary_measurement",
        })

    write_csv(OUT / "geometry_hypothesis_audit.csv", geometry_rows)
    write_csv(OUT / "board_pose_candidates.csv", board_candidate_rows)
    write_csv(OUT / "board_pose_per_frame.csv", board_frame_rows)
    write_csv(OUT / "board_within_by_run_height_se3.csv", board_within_rows)
    write_csv(OUT / "board_within_residuals_se3.csv", board_residual_rows)
    write_csv(OUT / "Sigma_within_pooled_se3.csv", pooled_rows)
    write_csv(OUT / "b_pose_se3.csv", b_pose_rows)
    write_csv(OUT / "b_run_empirical_bank_se3.csv", b_run_rows)
    write_csv(OUT / "single_marker_ippe_failure_modes.csv", single_rows)
    write_csv(OUT / "single_marker_ippe_candidates.csv", single_candidate_rows)

    g = defaultdict(list)
    for r in geometry_rows:
        g[(r["geometry"], r["camera"])].append(float(r["best_reprojection_rmse_px"]))
    geometry_summary = {
        f"{geometry}/{camera}": {
            "n": len(values), "median_px": float(np.median(values)),
            "mean_px": float(np.mean(values)), "max_px": float(np.max(values)),
        }
        for (geometry, camera), values in sorted(g.items())
    }
    actual = {(r["camera"], r["run_id"], r["height_mm"], r["frame_index"]): float(r["best_reprojection_rmse_px"])
              for r in geometry_rows if r["geometry"] == "actual_margin10"}
    logged = {(r["camera"], r["run_id"], r["height_mm"], r["frame_index"]): float(r["best_reprojection_rmse_px"])
              for r in geometry_rows if r["geometry"] == "logged_edge_aligned"}
    geometry_summary["paired_result"] = {
        "actual_lower_n": sum(actual[k] < logged[k] for k in actual),
        "paired_frames_n": len(actual),
        "conclusion": "confirmed actual centres ±70,±113.5 mm; logged ±80,±123.5 mm rejected",
    }

    branch_board_n = sum(int(r["branch_switch_flag"]) for r in board_within_rows)
    branch_single_n = sum(int(r["branch_switch_flag"]) for r in single_rows)
    large_single_n = sum(int(r["large_mode_jump_flag"]) for r in single_rows)
    source_files = source_paths + [E2_MANIFEST, Path(__file__), HERE / "build_empirical_components.py"]
    manifest = {
        "analysis_id": "E2-v1R0_board_pose",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BOARD_LEVEL_PRIMARY_NO_TOTAL_SUM",
        "geometry": {
            "board_mm": [210.0, 297.0], "marker_mm": 50.0, "outer_margin_mm": 10.0,
            "actual_marker_centres_mm": ACTUAL_CENTRES,
            "acquisition_logged_centres_rejected_mm": LOGGED_CENTRES,
            "evidence": geometry_summary,
        },
        "primary_measurement": "20-corner rigid-board SOLVEPNP_IPPE best branch, followed by LM refinement",
        "single_marker_role": "unclipped IPPE_SQUARE failure-mode comparator only",
        "hierarchy": {
            "Sigma_within": "short-term random board-pose measurement residual covariance",
            "b_pose": "stable height-conditioned error mean after each run's height-0 baseline",
            "b_run": "empirical bank only; baseline placement and condition residual vectors; no Gaussian fit",
            "total_sum": "not produced and not authorized",
        },
        "branch_flags": {
            "board_groups_with_selected_branch_switch": branch_board_n,
            "board_groups_total": len(board_within_rows),
            "single_marker_groups_with_selected_branch_switch": branch_single_n,
            "single_marker_groups_with_large_mode_jump_gt_0p25rad": large_single_n,
            "single_marker_groups_total": len(single_rows),
            "clipped_observations": 0,
        },
        "se3": {
            "residual": "Log(inv(T_bar) @ T_i)", "xi_order": XI_NAMES,
            "covariance": "sample covariance; pooled within uses sum_g(n_g-1) denominator",
        },
        "source_files": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(p)} for p in source_files],
        "formal_e1_v4_input_status": "candidate camera-side input; E1-v4 executable artifact still must be recovered",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    def pooled(camera, height):
        return next(r for r in pooled_rows if r["camera"] == camera and r["height_mm"] == height)

    lines = [
        "# E2-v1R0 board-pose results", "", "## Geometry decision", "",
        "The printed geometry is confirmed as marker centres at `x=±70 mm`, `y=±113.5 mm`, with the centre marker at `(0,0)`.", "",
        f"- Correct geometry won in {geometry_summary['paired_result']['actual_lower_n']}/{geometry_summary['paired_result']['paired_frames_n']} paired raw frames.",
        f"- ihawk1 median reprojection RMSE: correct {geometry_summary['actual_margin10/ihawk1']['median_px']:.3f} px vs logged {geometry_summary['logged_edge_aligned/ihawk1']['median_px']:.3f} px.",
        f"- ihawk2 median reprojection RMSE: correct {geometry_summary['actual_margin10/ihawk2']['median_px']:.3f} px vs logged {geometry_summary['logged_edge_aligned/ihawk2']['median_px']:.3f} px.",
        "", "The acquisition metadata/raw geometry fields at ±80/±123.5 mm are provenance-preserved but rejected for board normalization.",
        "", "## Primary board measurement", "",
        f"- 330 board poses: 2 cameras × 5 runs × 11 heights × 3 frames; every pose uses all 20 marker corners.",
        f"- Board-level selected-branch switches: {branch_board_n}/{len(board_within_rows)} groups.",
        f"- Single-marker selected-branch switches: {branch_single_n}/{len(single_rows)} groups; large >0.25 rad mode jumps: {large_single_n}/{len(single_rows)}. None were clipped.",
        "", "Pooled `Sigma_within` examples (rho sigma mm / omega sigma rad):", "",
    ]
    for camera in K:
        for height in (0.0, 25.0, 50.0):
            r = pooled(camera, height)
            lines.append(
                f"- {camera}, h={height:g}: "
                + "/".join(f"{r['sigma_' + n]:.4f}" for n in XI_NAMES[:3])
                + " mm; " + "/".join(f"{r['sigma_' + n]:.6f}" for n in XI_NAMES[3:]) + " rad."
            )
    lines += [
        "", "## Replay semantics", "",
        "`Sigma_within`, `b_pose`, and `b_run` are separate. `b_run` is an empirical bank, not a fitted Gaussian. No `total_sum` is generated. E1-v4 replay remains blocked until the original executable metric artifact is recovered; this analysis does not redefine it.", "",
    ]
    (OUT / "RESULTS_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote E2-v1R0 board-level analysis to {OUT}")


if __name__ == "__main__":
    main()
