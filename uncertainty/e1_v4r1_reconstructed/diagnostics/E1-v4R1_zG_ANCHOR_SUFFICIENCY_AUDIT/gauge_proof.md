# Analytic C_z/q1 gauge test

For a standard fixed-base UR5, a small joint-1 perturbation is a left base-yaw action: `fk(q+delta q1 e1)=exp(delta q1 Z_B) fk(q)+O(delta q1^2)`. With a free fixed base-side nuisance, select `X_B=exp(-delta q1 Z_B)`. In the implemented vision chain the two left factors cancel to first order, so `T_BF^vision` and hence `zG` remain invariant. Thus a free `X_B` exactly absorbs the q1/base-yaw gauge.

`X_F` is right-multiplied. To absorb the same left yaw at pose k it would require `X_F,k = fk(q_k)^-1 exp(-delta q1 Z_B) fk(q_k)`, which varies with k. A single common X_F cannot generically absorb that multi-pose gauge.

Numerical verification at pose 0 (not a model change): unrestricted `X_B` leaves q1 residual norm 4.29e-16; unrestricted X_F leaves 6.21e-15. The frozen `geometry_evidence()` then explicitly sets `jn[:,0:6]=0`, so its apparent q1 anchoring is a `RECONSTRUCTION_CHOICE`, not proof of a physical anchor.
