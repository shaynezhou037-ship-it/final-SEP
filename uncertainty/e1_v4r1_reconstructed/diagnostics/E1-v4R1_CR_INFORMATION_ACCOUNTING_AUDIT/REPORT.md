# C-R information accounting audit

Classification: `NUISANCE_SEMANTICS_BLOCKER`.

D1 changes the C-R minimum principal angle from 0.604606 to 0.632959 deg (4.69% relative). It preserves every frozen marginal noise magnitude but accounts for the shared zR reference pose. The remaining uncertainty is materially limited by unresolved global X_B/X_F semantics: X_B has rank zero by implementation, while X_F supplies rank 6 and removes the reported directed energy shown in `nuisance_absorption.csv`.

The covariance is supported at full rank 462/462; no null directions were discarded. Support whitening uses eigenvalue tolerance 2.89e-14; `max|W Sigma W^T-I|=6.29e-13`. No epsilon regularization was used.

This is diagnostic only. It does not alter E1, authorize E2, calculate d_min, or authorize any decision.
