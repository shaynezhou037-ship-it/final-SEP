"""Relative-motion evidence zR using the recovered E1 first-order equation."""

from __future__ import annotations

import numpy as np

from se3_utils import adjoint, inv_transform
from ur5_model import body_jacobian, fk


def relative_evidence(
    q_i: np.ndarray,
    q_j: np.ndarray,
    T_BC: np.ndarray,
    T_FM: np.ndarray,
    B_i: np.ndarray,
    B_j: np.ndarray,
) -> dict[str, np.ndarray]:
    del T_BC  # The recovered relative equation is camera-extrinsic invariant.
    T_CM_i = inv_transform(np.eye(4)) @ fk(q_i) @ T_FM
    T_CM_j = inv_transform(np.eye(4)) @ fk(q_j) @ T_FM
    Aij = inv_transform(T_CM_i) @ T_CM_j
    Ad_A = adjoint(Aij)
    Ad_A_inv = adjoint(inv_transform(Aij))
    Ad_X = adjoint(T_FM)
    Ad_X_inv = adjoint(inv_transform(T_FM))

    # delta_xi_CM,i = Bpose_i delta_kappa + Ad_X^-1 J_i^b delta_q0
    pose_fault_i = np.zeros((6, 23))
    pose_fault_j = np.zeros((6, 23))
    pose_fault_i[:, :5] = B_i
    pose_fault_j[:, :5] = B_j
    pose_fault_i[:, 17:23] = Ad_X_inv @ body_jacobian(q_i)
    pose_fault_j[:, 17:23] = Ad_X_inv @ body_jacobian(q_j)
    delta_a = -Ad_A_inv @ pose_fault_i + pose_fault_j
    jf = -Ad_X @ Ad_A @ delta_a

    # Recovered fixed X nuisance. Map it to the global X_F slot; X_B does not
    # enter relative hand-eye consistency.
    jn = np.zeros((6, 12))
    jn[:, 6:12] = Ad_X @ (Ad_A - np.eye(6))
    return {"J_fault": jf, "J_nuisance": jn}
