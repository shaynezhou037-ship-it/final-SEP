"""Whitening, fault-only severity scaling, then nuisance projection."""

from __future__ import annotations

import numpy as np

from se3_utils import orthonormal_basis


def whiten_scale_project(
    J_fault: np.ndarray,
    J_nuisance: np.ndarray,
    row_sigma: np.ndarray,
    severity_scales: np.ndarray,
    rtol: float = 1e-10,
) -> dict[str, np.ndarray | int]:
    row_sigma = np.asarray(row_sigma, dtype=float).reshape(-1)
    if np.any(row_sigma <= 0.0):
        raise ValueError("all measurement standard deviations must be positive")
    Jf_white = np.asarray(J_fault, dtype=float) / row_sigma[:, None]
    Jn_white = np.asarray(J_nuisance, dtype=float) / row_sigma[:, None]
    Jf_scaled = Jf_white @ np.diag(np.asarray(severity_scales, dtype=float))
    Qn, sn = orthonormal_basis(Jn_white, rtol=rtol)
    projected = Jf_scaled - Qn @ (Qn.T @ Jf_scaled)
    return {
        "J_fault_white": Jf_white,
        "J_nuisance_white": Jn_white,
        "J_fault_scaled": Jf_scaled,
        "J_projected": projected,
        "Q_nuisance": Qn,
        "nuisance_singular_values": sn,
        "nuisance_rank": Qn.shape[1],
    }
