"""Task-space severity normalization shared by every evidence channel."""

from __future__ import annotations

import numpy as np


def compute_severity_scales(
    task_jacobians: list[np.ndarray],
    target_equivalent_rms_m: float = 0.005,
    rotation_lever_arm_m: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Scale every individual mode to the same task-space RMS severity.

    Each 6x23 task Jacobian is in [m, rad]. The equivalent displacement is
    sqrt(||translation||^2 + ||L*rotation||^2). No evidence/noise quantity is
    used here, preventing pair-specific tuning.
    """
    effects = []
    for J in task_jacobians:
        J = np.asarray(J, dtype=float)
        equivalent_sq = np.sum(J[:3, :] ** 2, axis=0) + (rotation_lever_arm_m**2) * np.sum(J[3:, :] ** 2, axis=0)
        effects.append(equivalent_sq)
    rms = np.sqrt(np.mean(np.vstack(effects), axis=0))
    if np.any(rms < 1e-12):
        bad = np.flatnonzero(rms < 1e-12).tolist()
        raise ValueError(f"task severity is undefined for zero-effect modes {bad}")
    return target_equivalent_rms_m / rms, rms


def scaling_matrix(scales: np.ndarray) -> np.ndarray:
    return np.diag(np.asarray(scales, dtype=float))
