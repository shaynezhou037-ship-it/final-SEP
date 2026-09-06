"""Visual hold-out evidence zV with training-point pose nuisance absorption."""

from __future__ import annotations

import numpy as np

from se3_utils import inv_transform, numerical_jacobian, se3_exp


def project_points(T_CM: np.ndarray, points_M: np.ndarray, intrinsics: np.ndarray) -> np.ndarray:
    """Pinhole projection with first-order radial distortion."""
    fx, fy, cx, cy, k1 = np.asarray(intrinsics, dtype=float)
    points_M = np.asarray(points_M, dtype=float)
    p_C = (T_CM[:3, :3] @ points_M.T).T + T_CM[:3, 3]
    if np.any(p_C[:, 2] <= 1e-5):
        raise ValueError("marker point is behind or too close to the camera")
    x, y = p_C[:, 0] / p_C[:, 2], p_C[:, 1] / p_C[:, 2]
    radial = 1.0 + k1 * (x * x + y * y)
    return np.column_stack([fx * x * radial + cx, fy * y * radial + cy])


def marker_grid(shape: tuple[int, int], spacing_m: float) -> np.ndarray:
    ny, nx = shape
    xs = (np.arange(nx) - 0.5 * (nx - 1)) * spacing_m
    ys = (np.arange(ny) - 0.5 * (ny - 1)) * spacing_m
    return np.array([[x, y, 0.0] for y in ys for x in xs], dtype=float)


def pose_absorption_map(
    T_CM: np.ndarray,
    points_M: np.ndarray,
    intrinsics: np.ndarray,
    training_indices: list[int],
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Return B_pose=-J_xi,tr^+ J_P,tr and diagnostic Jacobians."""
    p_steps = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1e-7])
    xi_steps = np.r_[np.full(3, 1e-7), np.full(3, 1e-7)]
    train = np.asarray(training_indices, dtype=int)

    def fp(dp):
        return project_points(T_CM, points_M[train], intrinsics + dp).reshape(-1)

    def fxi(xi):
        return project_points(T_CM @ se3_exp(xi), points_M[train], intrinsics).reshape(-1)

    Jp_tr = numerical_jacobian(fp, np.zeros(5), p_steps)
    Jxi_tr = numerical_jacobian(fxi, np.zeros(6), xi_steps)
    Bpose = -np.linalg.pinv(Jxi_tr, rcond=1e-12) @ Jp_tr
    return Bpose, {"J_P_training": Jp_tr, "J_xi_training": Jxi_tr}


def visual_evidence(
    T_BC: np.ndarray,
    T_BM: np.ndarray,
    points_M: np.ndarray,
    intrinsics: np.ndarray,
    training_indices: list[int],
) -> dict[str, np.ndarray]:
    """Build zV rows and the per-pose P->SE(3) bias map."""
    T_CM = inv_transform(T_BC) @ T_BM
    Bpose, diag = pose_absorption_map(T_CM, points_M, intrinsics, training_indices)
    all_idx = np.arange(len(points_M))
    held = np.setdiff1d(all_idx, np.asarray(training_indices, dtype=int))
    p_steps = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1e-7])
    xi_steps = np.full(6, 1e-7)

    def fp(dp):
        return project_points(T_CM, points_M[held], intrinsics + dp).reshape(-1)

    def fxi(xi):
        return project_points(T_CM @ se3_exp(xi), points_M[held], intrinsics).reshape(-1)

    Jp_ho = numerical_jacobian(fp, np.zeros(5), p_steps)
    Jxi_ho = numerical_jacobian(fxi, np.zeros(6), xi_steps)
    JV = Jp_ho + Jxi_ho @ Bpose
    Jfault = np.zeros((JV.shape[0], 23))
    Jfault[:, :5] = JV
    return {
        "J_fault": Jfault,
        "J_nuisance": np.zeros((JV.shape[0], 12)),
        "B_pose": Bpose,
        "heldout_indices": held,
        **diag,
        "J_P_holdout": Jp_ho,
        "J_xi_holdout": Jxi_ho,
    }
