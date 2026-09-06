"""Frozen action mapping and reconstructed cross-action metrics."""

from __future__ import annotations

import numpy as np

from se3_utils import orthonormal_basis


FAULT_NAMES = [
    "P_dfx", "P_dfy", "P_dcx", "P_dcy", "P_dk1",
    "C_tx", "C_ty", "C_tz", "C_wx", "C_wy", "C_wz",
    "T_tx", "T_ty", "T_tz", "T_wx", "T_wy", "T_wz",
    "R_q1", "R_q2", "R_q3", "R_q4", "R_q5", "R_q6",
]
ACTION_INDICES = {
    "P": list(range(0, 5)),
    "C": list(range(5, 11)),
    "T": list(range(11, 17)),
    "R": list(range(17, 23)),
}
CROSS_ACTION_PAIRS = [("P", "C"), ("P", "T"), ("P", "R"), ("C", "R"), ("T", "R")]


def principal_angles_deg(J: np.ndarray, rtol: float = 1e-10) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for a, b in CROSS_ACTION_PAIRS:
        Qa, _ = orthonormal_basis(J[:, ACTION_INDICES[a]], rtol=rtol)
        Qb, _ = orthonormal_basis(J[:, ACTION_INDICES[b]], rtol=rtol)
        if Qa.shape[1] == 0 or Qb.shape[1] == 0:
            vals = np.array([np.pi / 2.0])
        else:
            sv = np.linalg.svd(Qa.T @ Qb, compute_uv=False)
            vals = np.arccos(np.clip(sv, -1.0, 1.0))
        out[f"{a}-{b}"] = np.sort(np.rad2deg(vals)).tolist()
    return out


def mode_residual_sigma(J: np.ndarray, target_idx: int, competitor_indices: list[int]) -> float:
    """Unexplainable target signal after least-squares competing hypothesis."""
    y = J[:, target_idx]
    A = J[:, competitor_indices]
    return float(np.linalg.norm(y - A @ (np.linalg.pinv(A, rcond=1e-12) @ y)))


def _unit_sphere_pair_min(A: np.ndarray, B: np.ndarray, seed: int) -> tuple[float, np.ndarray, np.ndarray]:
    """Deterministic projected-gradient solve on ||u||=||v||=1."""
    rng = np.random.default_rng(seed)
    starts = []
    # Principal-vector start is natural for the closest subspace directions.
    Qa, _, Va = np.linalg.svd(A, full_matrices=False)
    Qb, _, Vb = np.linalg.svd(B, full_matrices=False)
    if Qa.shape[1] and Qb.shape[1]:
        Uc, _, Vct = np.linalg.svd(Qa.T @ Qb, full_matrices=False)
        starts.append((Va.T @ Uc[:, 0], Vb.T @ Vct.T[:, 0]))
    for _ in range(11):
        u, v = rng.normal(size=A.shape[1]), rng.normal(size=B.shape[1])
        starts.append((u / np.linalg.norm(u), v / np.linalg.norm(v)))
    lipschitz = 2.0 * max(np.linalg.norm(A, 2) ** 2, np.linalg.norm(B, 2) ** 2, 1.0)
    step = 0.25 / lipschitz
    best = (np.inf, None, None)
    for u0, v0 in starts:
        u, v = u0 / np.linalg.norm(u0), v0 / np.linalg.norm(v0)
        for _ in range(600):
            residual = A @ u - B @ v
            gu = 2.0 * A.T @ residual
            gv = -2.0 * B.T @ residual
            gu -= u * np.dot(u, gu)
            gv -= v * np.dot(v, gv)
            un = u - step * gu
            vn = v - step * gv
            un /= np.linalg.norm(un)
            vn /= np.linalg.norm(vn)
            if np.linalg.norm(un - u) + np.linalg.norm(vn - v) < 1e-11:
                u, v = un, vn
                break
            u, v = un, vn
        d = float(np.linalg.norm(A @ u - B @ v))
        if d < best[0]:
            best = (d, u.copy(), v.copy())
    return best  # type: ignore[return-value]


def cross_action_dmin(J: np.ndarray) -> tuple[float, dict[str, object]]:
    """RECONSTRUCTION_CHOICE_dmin with equal-severity unit directions.

    Each individual coordinate has already been task-severity normalized.
    Within every allowed action pair, both coefficient vectors are constrained
    to unit norm and may choose their most favourable directions.
    """
    best = (np.inf, None)
    per_action: dict[str, float] = {}
    for pair_number, (a, b) in enumerate(CROSS_ACTION_PAIRS):
        ia, ib = ACTION_INDICES[a], ACTION_INDICES[b]
        d, u, v = _unit_sphere_pair_min(J[:, ia], J[:, ib], 20260906 + pair_number)
        per_action[f"{a}-{b}"] = d
        if d < best[0]:
            best = (d, {
                "action_pair": f"{a}-{b}",
                "u_coefficients": dict(zip((FAULT_NAMES[i] for i in ia), u.tolist())),
                "v_coefficients": dict(zip((FAULT_NAMES[i] for i in ib), v.tolist())),
            })
    detail = dict(best[1] or {})
    detail["per_action_pair"] = per_action
    detail["definition"] = "RECONSTRUCTION_CHOICE_dmin_equal_severity_unit_direction"
    return float(best[0]), detail
