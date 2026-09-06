# zG transform graph

Frames evidenced by code: `B` robot base, `F` flange, `C` camera (explicitly deleted from zG), and `M_F` flange marker through `T_FM`. A physical `M_B` base fiducial is asserted in comments only; no measured `T_BM_B`, fixture geometry, calibration record, or finite uncertainty is recovered.

Implemented chain:

`T_BF^vision = X_B · fk(q+dq) · T_FM · exp(Bpose dp) · (T_FM exp(dt))^{-1} · X_F`

`T_BF^reference = fk(q)`

and `zG=Log((T_BF^vision)^{-1} T_BF^reference)`. Camera `T_BC` and camera fault `dc` are explicitly deleted. A base-side item being physically fixed does not establish that it is known relative to `B`; the missing factor is exactly the required independent anchor.
