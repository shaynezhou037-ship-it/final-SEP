"""Ideal UR5 (CB3) kinematics using Universal Robots' standard DH table."""

from __future__ import annotations

import numpy as np

from se3_utils import inv_transform, se3_log


# Universal Robots' published ideal UR5 parameters, SI units.
A = np.array([0.0, -0.425, -0.39225, 0.0, 0.0, 0.0])
D = np.array([0.089159, 0.0, 0.0, 0.10915, 0.09465, 0.0823])
ALPHA = np.array([np.pi / 2.0, 0.0, 0.0, np.pi / 2.0, -np.pi / 2.0, 0.0])


def dh_transform(theta: float, a: float, d: float, alpha: float) -> np.ndarray:
    ct, st = np.cos(theta), np.sin(theta)
    ca, sa = np.cos(alpha), np.sin(alpha)
    return np.array([
        [ct, -st * ca, st * sa, a * ct],
        [st, ct * ca, -ct * sa, a * st],
        [0.0, sa, ca, d],
        [0.0, 0.0, 0.0, 1.0],
    ])


def fk(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float).reshape(6)
    T = np.eye(4)
    for theta, a, d, alpha in zip(q, A, D, ALPHA):
        T = T @ dh_transform(theta, a, d, alpha)
    return T


def body_jacobian(q: np.ndarray, step: float = 1e-7) -> np.ndarray:
    q = np.asarray(q, dtype=float).reshape(6)
    T0 = fk(q)
    J = np.empty((6, 6))
    for k in range(6):
        qp, qm = q.copy(), q.copy()
        qp[k] += step
        qm[k] -= step
        J[:, k] = (
            se3_log(inv_transform(T0) @ fk(qp))
            - se3_log(inv_transform(T0) @ fk(qm))
        ) / (2.0 * step)
    return J


def solve_ik(target: np.ndarray, q0: np.ndarray, max_iter: int = 200) -> tuple[np.ndarray, float]:
    """Deterministic damped least-squares IK used only to build fixed task poses."""
    q = np.asarray(q0, dtype=float).copy()
    damping = 1e-5
    for _ in range(max_iter):
        err = se3_log(inv_transform(fk(q)) @ target)
        if np.linalg.norm(err) < 1e-10:
            break
        J = body_jacobian(q)
        dq = J.T @ np.linalg.solve(J @ J.T + damping * np.eye(6), err)
        max_abs = float(np.max(np.abs(dq)))
        if max_abs > 0.15:
            dq *= 0.15 / max_abs
        q += dq
    final = float(np.linalg.norm(se3_log(inv_transform(fk(q)) @ target)))
    return q, final
