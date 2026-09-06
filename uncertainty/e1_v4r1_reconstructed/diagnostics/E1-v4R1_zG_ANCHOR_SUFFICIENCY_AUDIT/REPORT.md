# zG gauge-breaking anchor sufficiency audit

Primary result: `INSUFFICIENT_EVIDENCE`. No local source documents an independently calibrated or mechanically indexed finite-uncertainty transform from the claimed base-side fiducial to robot base `B`. The current code asserts that the base marker is the reference but explicitly suppresses X_B specifically to retain q1 information; its own module labels the zG Jacobian a reconstruction choice. Therefore zG cannot currently be credited with independently breaking C_z↔q1.

Historical `N=[X_B,X_F]` and “zG breaks exact gauge into near-gauge” are `CONDITIONALLY_COMPATIBLE`: they are mathematically consistent only if X_B was independently anchored or assigned a documented finite prior. No such protocol/covariance is recovered here.

No E1 core modification, covariance invention, E2, d_min, phase map, perfect-zG, sweep, or physical collection occurred.
