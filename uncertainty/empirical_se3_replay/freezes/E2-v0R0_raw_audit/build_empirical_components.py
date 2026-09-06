#!/usr/bin/env python3
"""Build empirical pixel and SE(3) uncertainty components from E0-A/E4/E2 raw.

No model is tuned or fitted beyond per-frame PnP reconstruction that is needed
to express the raw observations as rigid transforms.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "results"

E0_RAW = ROOT / "E0" / "E0_A_camera_static" / "raw"
E2_ROOT = ROOT / "E2" / "E2_dual_camera_height_scan"
E2_MANIFEST = ROOT / "E2" / "E2_rebuilt" / "E2_REBUILD_MANIFEST.json"
E4_CALIB_RAW = (
    ROOT / "E4" / "E4_charuco_calibration_v4" / "20260811_191758"
    / "E4_charuco_12spread_per_frame.csv"
)
E4_HELDOUT_RAW = (
    ROOT / "E4" / "E4_model_freeze_v1" / "20260811_192958"
    / "E4_heldout_9points_per_frame.csv"
)

K = {
    "ihawk1": np.array(
        [[401.77020263671875, 0.0, 322.1313781738281],
         [0.0, 401.9191589355469, 202.54229736328125],
         [0.0, 0.0, 1.0]], dtype=np.float64),
    "ihawk2": np.array(
        [[391.3234558105469, 0.0, 320.85333251953125],
         [0.0, 391.3234558105469, 202.9705047607422],
         [0.0, 0.0, 1.0]], dtype=np.float64),
}
D = np.zeros((5, 1), dtype=np.float64)
HALF_MARKER_MM = 25.0
XI_NAMES = ["rho_x_mm", "rho_y_mm", "rho_z_mm", "omega_x_rad", "omega_y_rad", "omega_z_rad"]
PIXEL_COV_NAMES = ["cov_uu_px2", "cov_uv_px2", "cov_vu_px2", "cov_vv_px2"]
SE3_COV_NAMES = [f"cov_{a}_{b}" for a in XI_NAMES for b in XI_NAMES]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def skew(v: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(v, dtype=float).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def so3_exp(phi: np.ndarray) -> np.ndarray:
    return cv2.Rodrigues(np.asarray(phi, dtype=np.float64).reshape(3, 1))[0]


def so3_log(R: np.ndarray) -> np.ndarray:
    return cv2.Rodrigues(np.asarray(R, dtype=np.float64))[0].reshape(3)


def se3_exp(xi: np.ndarray) -> np.ndarray:
    rho = np.asarray(xi[:3], dtype=float)
    phi = np.asarray(xi[3:], dtype=float)
    theta = float(np.linalg.norm(phi))
    Omega = skew(phi)
    if theta < 1e-8:
        V = np.eye(3) + 0.5 * Omega + (1.0 / 6.0) * (Omega @ Omega)
    else:
        V = (
            np.eye(3)
            + ((1.0 - math.cos(theta)) / theta**2) * Omega
            + ((theta - math.sin(theta)) / theta**3) * (Omega @ Omega)
        )
    T = np.eye(4)
    T[:3, :3] = so3_exp(phi)
    T[:3, 3] = V @ rho
    return T


def se3_log(T: np.ndarray) -> np.ndarray:
    phi = so3_log(T[:3, :3])
    theta = float(np.linalg.norm(phi))
    Omega = skew(phi)
    if theta < 1e-8:
        V_inv = np.eye(3) - 0.5 * Omega + (1.0 / 12.0) * (Omega @ Omega)
    else:
        # Numerically stable equivalent of
        # 1/theta^2 - (1+cos(theta))/(2 theta sin(theta)).
        a = (1.0 / theta**2) - ((1.0 + math.cos(theta)) / (2.0 * theta * math.sin(theta)))
        V_inv = np.eye(3) - 0.5 * Omega + a * (Omega @ Omega)
    return np.r_[V_inv @ T[:3, 3], phi]


def inv_T(T: np.ndarray) -> np.ndarray:
    out = np.eye(4)
    out[:3, :3] = T[:3, :3].T
    out[:3, 3] = -out[:3, :3] @ T[:3, 3]
    return out


def make_T(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = so3_exp(np.asarray(rvec).reshape(3))
    T[:3, 3] = np.asarray(tvec).reshape(3)
    return T


def translation_T(x: float, y: float, z: float) -> np.ndarray:
    T = np.eye(4)
    T[:3, 3] = [x, y, z]
    return T


def se3_mean(transforms: list[np.ndarray], tol: float = 1e-12, max_iter: int = 100) -> np.ndarray:
    if not transforms:
        raise ValueError("SE(3) mean requires observations")
    mean = np.array(transforms[0], dtype=float, copy=True)
    for _ in range(max_iter):
        delta = np.mean([se3_log(inv_T(mean) @ T) for T in transforms], axis=0)
        mean = mean @ se3_exp(delta)
        if np.linalg.norm(delta) < tol:
            return mean
    raise RuntimeError("SE(3) Frechet mean did not converge")


def sample_cov(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or len(x) < 2:
        return np.full((x.shape[1], x.shape[1]), np.nan)
    return np.cov(x, rowvar=False, ddof=1)


def covariance_about_mean(transforms: list[np.ndarray], mean: np.ndarray | None = None):
    mean = se3_mean(transforms) if mean is None else mean
    xi = np.vstack([se3_log(inv_T(mean) @ T) for T in transforms])
    return mean, xi, sample_cov(xi)


def flatten_cov(cov: np.ndarray, names: list[str]) -> dict[str, float]:
    return {name: float(value) for name, value in zip(names, cov.reshape(-1))}


def transform_fields(T: np.ndarray) -> dict[str, float]:
    rv = so3_log(T[:3, :3])
    return {
        "mean_t_x_mm": float(T[0, 3]), "mean_t_y_mm": float(T[1, 3]), "mean_t_z_mm": float(T[2, 3]),
        "mean_rotvec_x_rad": float(rv[0]), "mean_rotvec_y_rad": float(rv[1]), "mean_rotvec_z_rad": float(rv[2]),
    }


def xi_fields(xi: np.ndarray, prefix: str = "") -> dict[str, float]:
    return {prefix + name: float(value) for name, value in zip(XI_NAMES, xi)}


def sigma_fields(cov: np.ndarray) -> dict[str, float]:
    d = np.diag(cov)
    return {"sigma_" + name: float(math.sqrt(max(0.0, v))) if np.isfinite(v) else float("nan") for name, v in zip(XI_NAMES, d)}


def pixel_row(dataset: str, camera: str, pose: str, height, run: str, feature: str, landmark: str,
              points: list[list[float]], source: str) -> dict:
    a = np.asarray(points, dtype=float)
    cov = sample_cov(a)
    return {
        "dataset": dataset, "camera": camera, "pose_key": pose, "height_mm": height,
        "run_id": run, "feature": feature, "landmark_id": landmark, "n": len(a),
        "mean_u_px": float(a[:, 0].mean()), "mean_v_px": float(a[:, 1].mean()),
        "sigma_u_px": float(np.sqrt(cov[0, 0])), "sigma_v_px": float(np.sqrt(cov[1, 1])),
        **flatten_cov(cov, PIXEL_COV_NAMES), "source_file": source,
    }


def pnp_row(dataset: str, camera: str, pose: str, height, run: str,
            transforms: list[np.ndarray], source: str, note: str = "") -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    mean, xi, cov = covariance_about_mean(transforms)
    row = {
        "dataset": dataset, "camera": camera, "pose_key": pose, "height_mm": height,
        "run_id": run, "n": len(transforms), "covariance_rank": int(np.linalg.matrix_rank(cov)),
        **transform_fields(mean), **sigma_fields(cov),
        **flatten_cov(cov, SE3_COV_NAMES), "source_file": source, "note": note,
    }
    return row, mean, cov, xi


def select_e0_complete_runs() -> tuple[list[Path], list[Path]]:
    pattern = re.compile(r"^E0A_formal_(center|left|right|near|far)_(\d{8}_\d{6})\.csv$")
    complete: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    rejected = []
    for path in E0_RAW.glob("E0A_formal_*.csv"):
        m = pattern.match(path.name)
        if not m:
            continue
        rows = read_csv(path)
        counts = {cam: sum(r["camera_id"] == cam for r in rows) for cam in K}
        if counts == {"ihawk1": 50, "ihawk2": 50}:
            complete[m.group(1)].append((m.group(2), path))
        else:
            rejected.append(path)
    selected = [max(complete[p])[1] for p in ("center", "left", "right", "near", "far")]
    return selected, rejected


def load_e2_raw() -> tuple[list[dict[str, str]], list[Path]]:
    manifest = json.loads(E2_MANIFEST.read_text(encoding="utf-8"))
    all_rows = []
    sources = []
    for run in manifest["formal_runs"]:
        path = E2_ROOT / f"run_{run}" / "raw" / f"E2_dual_height_raw_{run}.csv"
        sources.append(path)
        retained = {int(v) for v in manifest["retained_height_steps"][run].values()}
        rows = [r for r in read_csv(path) if int(float(r["height_step_index"])) in retained]
        if len(rows) != 330:
            raise RuntimeError(f"{run}: expected 330 retained raw rows, found {len(rows)}")
        all_rows.extend(rows)
    if len(all_rows) != 1650:
        raise RuntimeError(f"E2: expected 1650 retained raw rows, found {len(all_rows)}")
    return all_rows, sources


MARKER_OBJECT = np.array([
    [-HALF_MARKER_MM, +HALF_MARKER_MM, 0.0],
    [+HALF_MARKER_MM, +HALF_MARKER_MM, 0.0],
    [+HALF_MARKER_MM, -HALF_MARKER_MM, 0.0],
    [-HALF_MARKER_MM, -HALF_MARKER_MM, 0.0],
], dtype=np.float64)


def solve_marker(corners: np.ndarray, camera: str) -> tuple[np.ndarray, float]:
    # Match the frozen acquisition implementation exactly: IPPE_SQUARE is the
    # first successful solver, with ITERATIVE used only as a fallback. Do not
    # choose between solvers post hoc by residual because that would alter the
    # already-frozen observation rule.
    for flag in (cv2.SOLVEPNP_IPPE_SQUARE, cv2.SOLVEPNP_ITERATIVE):
        try:
            ok, rvec, tvec = cv2.solvePnP(MARKER_OBJECT, corners, K[camera], D, flags=flag)
        except cv2.error:
            continue
        if not ok or tvec.reshape(3)[2] <= 0:
            continue
        projected, _ = cv2.projectPoints(MARKER_OBJECT, rvec, tvec, K[camera], D)
        rmse = float(np.sqrt(np.mean(np.sum((projected.reshape(-1, 2) - corners) ** 2, axis=1))))
        return make_T(rvec, tvec), rmse
    raise RuntimeError(f"{camera}: marker PnP failed")


def analyze_e0(pixel_rows: list[dict], selected: list[Path]) -> None:
    for path in selected:
        rows = read_csv(path)
        run = path.stem.rsplit("_", 2)[-2] + "_" + path.stem.rsplit("_", 1)[-1]
        position = rows[0]["position"]
        for camera in K:
            rr = [r for r in rows if r["camera_id"] == camera]
            pixel_rows.append(pixel_row(
                "E0-A", camera, position, "", run, "marker_center", str(rr[0]["marker_id"]),
                [[float(r["u_px"]), float(r["v_px"])] for r in rr], str(path.relative_to(ROOT))))


def analyze_e4(pixel_rows: list[dict], pnp_rows: list[dict], pnp_residual_rows: list[dict]) -> dict:
    specs = [
        {
            "path": E4_CALIB_RAW, "run": "20260811_191758", "pose": "board_static",
            "x": "paper_x_mm", "y": "paper_y_mm", "min_points": 8,
        },
        {
            "path": E4_HELDOUT_RAW, "run": "20260811_192958", "pose": "board_static",
            "x": "paper_x_gt_mm", "y": "paper_y_gt_mm", "min_points": 6,
        },
    ]
    audit = {}
    pose_means = defaultdict(list)
    for spec in specs:
        rows = read_csv(spec["path"])
        by_point = defaultdict(list)
        by_frame = defaultdict(list)
        for r in rows:
            by_point[(r["camera"], r["charuco_id"])].append(r)
            by_frame[(r["camera"], r["ros_frame_count"])].append(r)
        source = str(spec["path"].relative_to(ROOT))
        for (camera, cid), rr in sorted(by_point.items()):
            pixel_rows.append(pixel_row(
                "E4", camera, spec["pose"], 0.0, spec["run"], "charuco_corner", cid,
                [[float(r["u_undist_px"]), float(r["v_undist_px"])] for r in rr], source))

        used_counts = {}
        reproj = {}
        for camera in K:
            transforms = []
            errors = []
            counts = []
            for (cam, _frame), rr in by_frame.items():
                if cam != camera or len(rr) < spec["min_points"]:
                    continue
                obj = np.array([[float(r[spec["x"]]), float(r[spec["y"]]), 0.0] for r in rr], dtype=float)
                img = np.array([[float(r["u_undist_px"]), float(r["v_undist_px"])] for r in rr], dtype=float)
                if np.linalg.matrix_rank(obj[:, :2] - obj[:, :2].mean(axis=0)) < 2:
                    continue
                ok, rvec, tvec = cv2.solvePnP(obj, img, K[camera], D, flags=cv2.SOLVEPNP_IPPE)
                if not ok:
                    continue
                proj, _ = cv2.projectPoints(obj, rvec, tvec, K[camera], D)
                errors.append(float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img) ** 2, axis=1)))))
                counts.append(len(rr))
                transforms.append(make_T(rvec, tvec))
            row, mean, _, residuals = pnp_row(
                "E4", camera, spec["pose"], 0.0, spec["run"], transforms, source,
                f"Per-frame SOLVEPNP_IPPE; frames require >={spec['min_points']} non-collinear ChArUco points")
            pnp_rows.append(row)
            pose_means[camera].append((spec["run"], mean))
            for index, xi in enumerate(residuals, start=1):
                pnp_residual_rows.append({
                    "dataset": "E4", "camera": camera, "pose_key": spec["pose"], "height_mm": 0.0,
                    "run_id": spec["run"], "sample_id": index, **xi_fields(xi),
                    "definition": "Log(inv(T_bar_group) @ T_sample)",
                })
            used_counts[camera] = counts
            reproj[camera] = errors
        audit[spec["run"]] = {"points_per_used_frame": used_counts, "reprojection_rmse_px": reproj}
    run_bias_rows = []
    for camera, run_means in sorted(pose_means.items()):
        grand = se3_mean([T for _, T in run_means])
        for run, T in sorted(run_means):
            b = se3_log(inv_T(grand) @ T)
            run_bias_rows.append({
                "dataset": "E4", "camera": camera, "pose_key": "board_static", "height_mm": 0.0,
                "run_id": run, "n_runs_for_condition": len(run_means), **xi_fields(b, "b_"),
                "definition": "Log(inv(T_bar_pose_height) @ T_bar_pose_height_run)",
            })
    return audit, run_bias_rows


def analyze_e2(pixel_rows: list[dict], pnp_rows: list[dict], pnp_residual_rows: list[dict],
               raw_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    groups = defaultdict(list)
    for r in raw_rows:
        if str(r["detection_valid"]).lower() not in {"1", "true"} or str(r["pnp_valid"]).lower() not in {"1", "true"}:
            continue
        key = (r["camera_id"], float(r["height_gt_mm"]), int(float(r["marker_id"])), r["run_id"])
        groups[key].append(r)

    means = {}
    transforms_by_group = {}
    stored_delta = []
    board_normalized_samples = {}
    for (camera, height, marker, run), rr in sorted(groups.items()):
        rr.sort(key=lambda r: int(float(r["frame_index"])))
        pose = f"marker_{marker}_{rr[0]['board_position']}"
        source = str((E2_ROOT / f"run_{run}" / "raw" / f"E2_dual_height_raw_{run}.csv").relative_to(ROOT))
        feature_specs = [("marker_center", "center_u_undist_px", "center_v_undist_px")]
        feature_specs += [(f"corner{j}", f"corner{j}_u_undist_px", f"corner{j}_v_undist_px") for j in range(4)]
        for feature, ukey, vkey in feature_specs:
            pixel_rows.append(pixel_row(
                "E2", camera, pose, height, run, feature, str(marker),
                [[float(r[ukey]), float(r[vkey])] for r in rr], source))

        transforms = []
        normalized = []
        x = float(rr[0]["marker_gt_x_mm"])
        y = float(rr[0]["marker_gt_y_mm"])
        nominal = translation_T(x, y, height)
        for r in rr:
            corners = np.array([[float(r[f"corner{j}_u_undist_px"]), float(r[f"corner{j}_v_undist_px"])] for j in range(4)])
            T, _ = solve_marker(corners, camera)
            stored = make_T(
                np.array([float(r["pnp_rvec_x"]), float(r["pnp_rvec_y"]), float(r["pnp_rvec_z"])]),
                np.array([float(r["pnp_tx_camera_mm"]), float(r["pnp_ty_camera_mm"]), float(r["pnp_tz_camera_mm"])]))
            stored_delta.append(se3_log(inv_T(stored) @ T))
            transforms.append(T)
            normalized.append(T @ inv_T(nominal))
        row, mean, _, residuals = pnp_row("E2", camera, pose, height, run, transforms, source, "PnP recomputed from raw four corners")
        pnp_rows.append(row)
        for r, xi in zip(rr, residuals):
            pnp_residual_rows.append({
                "dataset": "E2", "camera": camera, "pose_key": pose, "height_mm": height,
                "run_id": run, "sample_id": int(float(r["frame_index"])), **xi_fields(xi),
                "definition": "Log(inv(T_bar_group) @ T_sample)",
            })
        key = (camera, height, marker, run)
        means[key] = mean
        transforms_by_group[key] = transforms
        board_normalized_samples[key] = normalized

    # Exact requested b(p,r) = Log(inv(T_bar_p) T_bar_p,r), for each camera,
    # height and marker pose across the five physical runs.
    run_bias_rows = []
    condition_groups = defaultdict(list)
    for (camera, height, marker, run), mean in means.items():
        condition_groups[(camera, height, marker)].append((run, mean))
    for (camera, height, marker), run_means in sorted(condition_groups.items()):
        grand = se3_mean([T for _, T in run_means])
        for run, T in sorted(run_means):
            b = se3_log(inv_T(grand) @ T)
            run_bias_rows.append({
                "dataset": "E2", "camera": camera, "pose_key": f"marker_{marker}", "height_mm": height,
                "run_id": run, "n_runs_for_condition": len(run_means), **xi_fields(b, "b_"),
                "definition": "Log(inv(T_bar_pose_height) @ T_bar_pose_height_run)",
            })

    # Board-normalized balanced hierarchy. Marker nominal XYZ is removed before
    # comparing poses, so nominal marker separation is not counted as drift.
    component_rows = []
    hierarchy_vector_rows = []
    diagnostics = {}
    for camera in K:
        for height in sorted({k[1] for k in board_normalized_samples if k[0] == camera}):
            keys = [k for k in board_normalized_samples if k[0] == camera and k[1] == height]
            runs = sorted({k[3] for k in keys})
            run_centres = {}
            pose_centres = {}
            within_xi = []
            for key in keys:
                centre, residuals, _ = covariance_about_mean(board_normalized_samples[key])
                pose_centres[key] = centre
                within_xi.extend(residuals)
                for sample_index, xi in enumerate(residuals, start=1):
                    hierarchy_vector_rows.append({
                        "dataset": "E2", "camera": camera, "height_mm": height,
                        "component": "within_pose", "run_id": key[3], "pose_key": f"marker_{key[2]}",
                        "sample_id": sample_index, **xi_fields(xi),
                        "coordinate": "right-invariant board-normalized SE(3) log",
                    })
            for run in runs:
                rr = [pose_centres[k] for k in keys if k[3] == run]
                run_centres[run] = se3_mean(rr)
            grand = se3_mean(list(run_centres.values()))
            between_xi = np.vstack([se3_log(inv_T(grand) @ run_centres[run]) for run in runs])
            for run, xi in zip(runs, between_xi):
                hierarchy_vector_rows.append({
                    "dataset": "E2", "camera": camera, "height_mm": height,
                    "component": "between_run", "run_id": run, "pose_key": "all_poses",
                    "sample_id": "", **xi_fields(xi),
                    "coordinate": "right-invariant board-normalized SE(3) log",
                })
            cross_xi = []
            for key, centre in pose_centres.items():
                xi = se3_log(inv_T(run_centres[key[3]]) @ centre)
                cross_xi.append(xi)
                hierarchy_vector_rows.append({
                    "dataset": "E2", "camera": camera, "height_mm": height,
                    "component": "cross_pose", "run_id": key[3], "pose_key": f"marker_{key[2]}",
                    "sample_id": "", **xi_fields(xi),
                    "coordinate": "right-invariant board-normalized SE(3) log",
                })
            arrays = {
                "within_pose": np.asarray(within_xi),
                "between_run": between_xi,
                "cross_pose": np.asarray(cross_xi),
            }
            covs = {name: sample_cov(values) for name, values in arrays.items()}
            covs["total_sum"] = covs["within_pose"] + covs["between_run"] + covs["cross_pose"]
            for name in ("within_pose", "between_run", "cross_pose", "total_sum"):
                cov = covs[name]
                component_rows.append({
                    "dataset": "E2", "camera": camera, "height_mm": height, "component": name,
                    "n_vectors": len(arrays[name]) if name in arrays else "",
                    "covariance_rank": int(np.linalg.matrix_rank(cov)),
                    **sigma_fields(cov), **flatten_cov(cov, SE3_COV_NAMES),
                    "coordinate": "right-invariant board-normalized SE(3) log",
                })
            diagnostics[f"{camera}/{height:g}"] = {
                "groups": len(keys), "runs": len(runs), "poses_per_run": len(keys) // len(runs),
                "within_vectors": len(within_xi), "cross_pose_vectors": len(cross_xi),
            }
    delta = np.vstack(stored_delta)
    audit = {
        "recomputed_vs_stored_pnp_log_abs_max": dict(zip(XI_NAMES, np.max(np.abs(delta), axis=0).tolist())),
        "hierarchy": diagnostics,
    }
    return run_bias_rows, component_rows, hierarchy_vector_rows, audit


def compact_summary(pixel_rows, pnp_rows, run_bias_rows, component_rows, e4_audit) -> str:
    e0 = [r for r in pixel_rows if r["dataset"] == "E0-A"]
    e4 = [r for r in pnp_rows if r["dataset"] == "E4"]
    e2 = [r for r in pnp_rows if r["dataset"] == "E2"]
    lines = [
        "# Empirical SE(3) component summary", "",
        "## Coverage", "",
        f"- E0-A pixel groups: {len(e0)} (5 poses x 2 cameras; 50 samples each).",
        f"- E4 PnP groups: {len(e4)} (two acquisition stages per camera in one frozen physical setup).",
        f"- E2 PnP groups: {len(e2)} (2 cameras x 11 heights x 5 marker poses x 5 runs; 3 frames each).",
        f"- E2 run-bias vectors: {sum(r['dataset'] == 'E2' for r in run_bias_rows)}; E4 temporal-stage bias vectors: {sum(r['dataset'] == 'E4' for r in run_bias_rows)}.",
        f"- E2 hierarchical component rows: {len(component_rows)}.", "",
        "## Selected numerical checks", "",
    ]
    for r in e4:
        sig_t = [r[f"sigma_{n}"] for n in XI_NAMES[:3]]
        sig_w = [r[f"sigma_{n}"] for n in XI_NAMES[3:]]
        lines.append(f"- E4 {r['camera']} board PnP, stage={r['run_id']}, n={r['n']}: sigma-rho mm = " + "/".join(f"{v:.4f}" for v in sig_t) + ", sigma-omega rad = " + "/".join(f"{v:.6f}" for v in sig_w) + ".")
    lines += ["", "E2 within-group covariance diagnostics (RSS of the six marginal sigmas, summarized across 275 pose/height/run groups per camera):", ""]
    for camera in K:
        rr = [r for r in e2 if r["camera"] == camera]
        rho = np.array([math.sqrt(sum(r[f"sigma_{n}"] ** 2 for n in XI_NAMES[:3])) for r in rr])
        omega = np.array([math.sqrt(sum(r[f"sigma_{n}"] ** 2 for n in XI_NAMES[3:])) for r in rr])
        rq = np.quantile(rho, [0.5, 0.9, 1.0])
        oq = np.quantile(omega, [0.5, 0.9, 1.0])
        lines.append(f"- {camera}: sigma-rho RSS median/P90/max = {rq[0]:.3f}/{rq[1]:.3f}/{rq[2]:.3f} mm; sigma-omega RSS = {oq[0]:.5f}/{oq[1]:.5f}/{oq[2]:.5f} rad.")
    lines += ["", "E2 direct between-run bias magnitudes across pose/height conditions:", ""]
    for camera in K:
        rr = [r for r in run_bias_rows if r["dataset"] == "E2" and r["camera"] == camera]
        rho = np.array([np.linalg.norm([r["b_" + n] for n in XI_NAMES[:3]]) for r in rr])
        omega = np.array([np.linalg.norm([r["b_" + n] for n in XI_NAMES[3:]]) for r in rr])
        rq = np.quantile(rho, [0.5, 0.9, 1.0])
        oq = np.quantile(omega, [0.5, 0.9, 1.0])
        lines.append(f"- {camera}: |b_rho| median/P90/max = {rq[0]:.3f}/{rq[1]:.3f}/{rq[2]:.3f} mm; |b_omega| = {oq[0]:.5f}/{oq[1]:.5f}/{oq[2]:.5f} rad.")
    lines += ["", "E4 calibration-to-held-out temporal-stage bias magnitude (two captures, not independent physical rebuilds):", ""]
    for camera in K:
        rr = [r for r in run_bias_rows if r["dataset"] == "E4" and r["camera"] == camera]
        # With two observations around their group mean the two magnitudes are
        # effectively symmetric; report both to avoid implying a larger n.
        rho = [np.linalg.norm([r["b_" + n] for n in XI_NAMES[:3]]) for r in rr]
        omega = [np.linalg.norm([r["b_" + n] for n in XI_NAMES[3:]]) for r in rr]
        lines.append(f"- {camera}: |b_rho| = {rho[0]:.4f}/{rho[1]:.4f} mm; |b_omega| = {omega[0]:.6f}/{omega[1]:.6f} rad.")
    lines += ["", "For E2, the following are total covariance sums (within + between-run + cross-pose):", ""]
    total = [r for r in component_rows if r["component"] == "total_sum"]
    for r in total:
        sig_t = [r[f"sigma_{n}"] for n in XI_NAMES[:3]]
        sig_w = [r[f"sigma_{n}"] for n in XI_NAMES[3:]]
        lines.append(f"- {r['camera']}, h={float(r['height_mm']):g} mm: sigma-rho mm = " + "/".join(f"{v:.3f}" for v in sig_t) + ", sigma-omega rad = " + "/".join(f"{v:.5f}" for v in sig_w) + ".")
    lines += [
        "", "## Boundary", "",
        "Every E2 group has n=3, so each unregularized 6-D within covariance has rank 2. Several ihawk1 groups contain large planar-PnP solution changes; they are retained in the empirical vector bank rather than clipped or Gaussianized.", "",
        "E0-A has no recoverable 6-D pose observation, E4 has no repeated physical run, and the repository has no E1-v4 replay artifact or definition of `d_min,emp^cross`. No replacement E1 model was fitted.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pixel_rows: list[dict] = []
    pnp_rows: list[dict] = []
    pnp_residual_rows: list[dict] = []

    e0_selected, e0_rejected = select_e0_complete_runs()
    analyze_e0(pixel_rows, e0_selected)
    e4_audit, e4_run_bias_rows = analyze_e4(pixel_rows, pnp_rows, pnp_residual_rows)
    e2_rows, e2_sources = load_e2_raw()
    e2_run_bias_rows, component_rows, hierarchy_vector_rows, e2_audit = analyze_e2(
        pixel_rows, pnp_rows, pnp_residual_rows, e2_rows)
    run_bias_rows = e4_run_bias_rows + e2_run_bias_rows

    write_csv(OUT / "pixel_within.csv", pixel_rows)
    write_csv(OUT / "pnp_within_se3.csv", pnp_rows)
    write_csv(OUT / "pnp_within_residuals_se3.csv", pnp_residual_rows)
    write_csv(OUT / "run_bias_se3.csv", run_bias_rows)
    write_csv(OUT / "e2_hierarchical_components_se3.csv", component_rows)
    write_csv(OUT / "e2_hierarchical_vectors_se3.csv", hierarchy_vector_rows)

    sources = e0_selected + [E4_CALIB_RAW, E4_HELDOUT_RAW, E2_MANIFEST] + e2_sources
    manifest = {
        "analysis": "empirical pixel and SE(3) covariance components",
        "se3_convention": {
            "transform": "X_camera = T_camera_from_object X_object",
            "residual": "xi_i = Log(inv(T_bar) @ T_i)",
            "xi_order": XI_NAMES,
            "translation_note": "rho is the SE(3)-log translation coordinate, not raw tvec subtraction",
            "mean": "iterative right-invariant Frechet/Karcher mean",
            "covariance": "sample covariance, ddof=1",
        },
        "inclusion": {
            "E0-A": "latest complete formal run (50 rows/camera) per position",
            "E4": "all calibration and held-out point samples for pixel covariance; calibration PnP frames require >=8 and held-out frames >=6 non-collinear ChArUco points",
            "E2": "original raw CSV rows whose height_step_index is retained by E2_REBUILD_MANIFEST",
        },
        "identifiability": {
            "E0-A_pnp": "not identifiable: no four corners or pose fields",
            "E4_between_run": "only a two-stage temporal contrast is identifiable; both stages share one frozen physical setup and are not independent physical rebuilds",
            "E2_hierarchy": "identified: 5 formal physical runs, 5 poses, 11 heights, 3 within-pose frames",
            "E2_group_covariance": "rank <= 2 because each 6-D pose/height/run group has n=3; do not invert as a full-rank Gaussian",
            "planar_pnp": "may be multi-modal; empirical residual vectors are retained for replay",
            "E1_v4_replay": "blocked: no E1-v4 artifact or d_min,emp^cross definition exists in repository",
        },
        "no_refit_statement": "No E1 model was loaded, modified, fitted, or tuned.",
        "e0_rejected_incomplete_files": [str(p.relative_to(ROOT)) for p in e0_rejected],
        "e4_pnp_audit": e4_audit,
        "e2_pnp_audit": e2_audit,
        "source_files": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p)} for p in sources],
        "outputs": ["pixel_within.csv", "pnp_within_se3.csv", "pnp_within_residuals_se3.csv", "run_bias_se3.csv", "e2_hierarchical_components_se3.csv", "e2_hierarchical_vectors_se3.csv", "RESULTS_SUMMARY.md"],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "RESULTS_SUMMARY.md").write_text(
        compact_summary(pixel_rows, pnp_rows, run_bias_rows, component_rows, e4_audit), encoding="utf-8")
    print(f"Wrote empirical components to {OUT}")


if __name__ == "__main__":
    main()
