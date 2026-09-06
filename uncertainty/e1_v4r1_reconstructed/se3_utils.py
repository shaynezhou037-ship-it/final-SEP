"""Small, dependency-free SO(3)/SE(3) utilities.

Conventions:
- transforms map local coordinates into parent coordinates;
- twists are [rho_x, rho_y, rho_z, omega_x, omega_y, omega_z];
- perturbations are right perturbations: T_tilde = T @ Exp(xi).
"""

from __future__ import annotations

import numpy as np


def skew(v: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(v, dtype=float).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def unskew(M: np.ndarray) -> np.ndarray:
    M = np.asarray(M, dtype=float)
    return np.array([M[2, 1], M[0, 2], M[1, 0]])


def so3_exp(w: np.ndarray) -> np.ndarray:
    w = np.asarray(w, dtype=float).reshape(3)
    theta = float(np.linalg.norm(w))
    W = skew(w)
    if theta < 1e-10:
        return np.eye(3) + W + 0.5 * (W @ W)
    a = np.sin(theta) / theta
    b = (1.0 - np.cos(theta)) / (theta * theta)
    return np.eye(3) + a * W + b * (W @ W)


def so3_log(R: np.ndarray) -> np.ndarray:
    R = np.asarray(R, dtype=float)
    c = float(np.clip((np.trace(R) - 1.0) * 0.5, -1.0, 1.0))
    theta = float(np.arccos(c))
    if theta < 1e-10:
        return 0.5 * unskew(R - R.T)
    return (theta / (2.0 * np.sin(theta))) * unskew(R - R.T)


def _left_jacobian_so3(w: np.ndarray) -> np.ndarray:
    w = np.asarray(w, dtype=float).reshape(3)
    theta = float(np.linalg.norm(w))
    W = skew(w)
    if theta < 1e-8:
        return np.eye(3) + 0.5 * W + (1.0 / 6.0) * (W @ W)
    a = (1.0 - np.cos(theta)) / (theta * theta)
    b = (theta - np.sin(theta)) / (theta**3)
    return np.eye(3) + a * W + b * (W @ W)


def _left_jacobian_so3_inv(w: np.ndarray) -> np.ndarray:
    w = np.asarray(w, dtype=float).reshape(3)
    theta = float(np.linalg.norm(w))
    W = skew(w)
    if theta < 1e-8:
        return np.eye(3) - 0.5 * W + (1.0 / 12.0) * (W @ W)
    a = (1.0 / (theta * theta)) - ((1.0 + np.cos(theta)) / (2.0 * theta * np.sin(theta)))
    return np.eye(3) - 0.5 * W + a * (W @ W)


def se3_exp(xi: np.ndarray) -> np.ndarray:
    xi = np.asarray(xi, dtype=float).reshape(6)
    rho, w = xi[:3], xi[3:]
    T = np.eye(4)
    T[:3, :3] = so3_exp(w)
    T[:3, 3] = _left_jacobian_so3(w) @ rho
    return T


def se3_log(T: np.ndarray) -> np.ndarray:
    T = np.asarray(T, dtype=float)
    w = so3_log(T[:3, :3])
    rho = _left_jacobian_so3_inv(w) @ T[:3, 3]
    return np.r_[rho, w]


def inv_transform(T: np.ndarray) -> np.ndarray:
    T = np.asarray(T, dtype=float)
    out = np.eye(4)
    out[:3, :3] = T[:3, :3].T
    out[:3, 3] = -out[:3, :3] @ T[:3, 3]
    return out


def adjoint(T: np.ndarray) -> np.ndarray:
    """Adjoint for [translation, rotation] twists."""
    T = np.asarray(T, dtype=float)
    R, t = T[:3, :3], T[:3, 3]
    A = np.zeros((6, 6))
    A[:3, :3] = R
    A[:3, 3:] = skew(t) @ R
    A[3:, 3:] = R
    return A


def transform(R: np.ndarray | None = None, t: np.ndarray | None = None) -> np.ndarray:
    T = np.eye(4)
    if R is not None:
        T[:3, :3] = np.asarray(R, dtype=float).reshape(3, 3)
    if t is not None:
        T[:3, 3] = np.asarray(t, dtype=float).reshape(3)
    return T


def numerical_jacobian(fun, x0: np.ndarray, steps: np.ndarray | float) -> np.ndarray:
    """Central-difference Jacobian with a scalar or per-coordinate step."""
    x0 = np.asarray(x0, dtype=float).reshape(-1)
    h = np.full_like(x0, float(steps)) if np.isscalar(steps) else np.asarray(steps, dtype=float)
    y0 = np.asarray(fun(x0), dtype=float).reshape(-1)
    J = np.empty((len(y0), len(x0)))
    for k, hk in enumerate(h):
        xp, xm = x0.copy(), x0.copy()
        xp[k] += hk
        xm[k] -= hk
        J[:, k] = (np.asarray(fun(xp)).reshape(-1) - np.asarray(fun(xm)).reshape(-1)) / (2.0 * hk)
    return J


def orthonormal_basis(A: np.ndarray, rtol: float = 1e-10) -> tuple[np.ndarray, np.ndarray]:
    A = np.asarray(A, dtype=float)
    if A.size == 0:
        return np.zeros((A.shape[0], 0)), np.array([])
    U, s, _ = np.linalg.svd(A, full_matrices=False)
    if len(s) == 0 or s[0] == 0.0:
        return np.zeros((A.shape[0], 0)), s
    rank = int(np.sum(s > rtol * s[0]))
    return U[:, :rank], s


def rotation_from_look_at(camera_position: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Return R_BC whose camera +z looks at target and +y is approximately down."""
    p = np.asarray(camera_position, dtype=float)
    z = np.asarray(target, dtype=float) - p
    z /= np.linalg.norm(z)
    up = np.array([0.0, 0.0, 1.0])
    x = np.cross(z, up)
    if np.linalg.norm(x) < 1e-8:
        up = np.array([0.0, 1.0, 0.0])
        x = np.cross(z, up)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    y /= np.linalg.norm(y)
    return np.column_stack([x, y, z])
