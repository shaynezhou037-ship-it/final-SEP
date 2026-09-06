"""Physical full-SE(3) geometry evidence zG.

The old zG source/Jacobian was not recovered.  This module is deliberately
labelled RECONSTRUCTION_CHOICE_zG_JACOBIAN and differentiates the stated
forward equation; it contains no hand-written cross-block leakage.
"""

from __future__ import annotations

import numpy as np

from se3_utils import inv_transform, numerical_jacobian, se3_exp, se3_log
from ur5_model import fk


RECONSTRUCTION_LABEL = "RECONSTRUCTION_CHOICE_zG_JACOBIAN"


def geometry_residual(
    theta: np.ndarray,
    nuisance: np.ndarray,
    q: np.ndarray,
    T_BC: np.ndarray,
    T_FM: np.ndarray,
    Bpose: np.ndarray,
) -> np.ndarray:
    """Compare flange pose inferred by vision with robot forward kinematics."""
    theta = np.asarray(theta, dtype=float)
    dp, dc, dt, dq = theta[:5], theta[5:11], theta[11:17], theta[17:23]
    xb, xf = nuisance[:6], nuisance[6:]

    # Joint-zero R is a physical configuration error: the camera observes the
    # displaced flange, while the indexed reference remains the nominal FK.
    T_BF_true = fk(q + dq)
    # Physical reconstruction choice: zG is the base-fixed/flange-fixed
    # fiducial relative pose. The base marker defines the reference frame, so
    # the common camera extrinsic cancels. This makes zG non-redundant with zL
    # and matches its recovered role as an independent indexed B->F channel.
    # A complete future empirical implementation supplies both marker pose
    # biases; here the base marker is the reference and Bpose is the relative
    # flange-marker pose bias.
    del T_BC, dc
    T_FM_used = T_FM @ se3_exp(dt)
    T_BF_vision = T_BF_true @ T_FM @ se3_exp(Bpose @ dp) @ inv_transform(T_FM_used)

    # RECONSTRUCTION_CHOICE_nuisance: common base-left and flange-right gauge
    # transformations, shared over every task pose. They are projected only
    # after whitening and are never severity-scaled.
    T_BF_vision = se3_exp(xb) @ T_BF_vision @ se3_exp(xf)
    T_BF_robot = fk(q)
    return se3_log(inv_transform(T_BF_vision) @ T_BF_robot)


def geometry_evidence(q: np.ndarray, T_BC: np.ndarray, T_FM: np.ndarray, Bpose: np.ndarray) -> dict[str, np.ndarray | str]:
    theta_steps = np.r_[np.full(5, 1e-4), np.full(12, 1e-7), np.full(6, 1e-7)]
    nuisance_steps = np.full(12, 1e-7)
    jf = numerical_jacobian(
        lambda th: geometry_residual(th, np.zeros(12), q, T_BC, T_FM, Bpose),
        np.zeros(23), theta_steps,
    )
    jn = numerical_jacobian(
        lambda xn: geometry_residual(np.zeros(23), xn, q, T_BC, T_FM, Bpose),
        np.zeros(12), nuisance_steps,
    )
    # A base-fixed fiducial is the indexed reference of zG, so its base pose is
    # not an unconstrained gauge in this channel. Projecting a free X_B here
    # would exactly erase the q1 information zG was introduced to provide.
    # X_F remains the recovered fixed flange-side nuisance.
    jn[:, :6] = 0.0
    return {"J_fault": jf, "J_nuisance": jn, "label": RECONSTRUCTION_LABEL}
