"""Absolute localization evidence zL in the recovered first-order form."""

from __future__ import annotations

import numpy as np

from se3_utils import adjoint, inv_transform
from ur5_model import body_jacobian


def localization_evidence(q: np.ndarray, T_CM: np.ndarray, T_FM: np.ndarray, Bpose: np.ndarray) -> dict[str, np.ndarray]:
    """J_L=[Bpose, Ad(T_CM^-1), -I, Ad(T_FM^-1)J_b]."""
    J = np.zeros((6, 23))
    J[:, 0:5] = Bpose
    J[:, 5:11] = adjoint(inv_transform(T_CM))
    J[:, 11:17] = -np.eye(6)
    J[:, 17:23] = adjoint(inv_transform(T_FM)) @ body_jacobian(q)
    return {"J_fault": J, "J_nuisance": np.zeros((6, 12))}
