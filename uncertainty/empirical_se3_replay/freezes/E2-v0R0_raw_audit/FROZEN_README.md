# E2-v0R0_raw_audit — frozen

This is the non-destructive snapshot of the original single-marker-primary SE(3) audit. It is retained as a failure-mode and provenance baseline.

`results/e2_hierarchical_components_se3.csv` and especially its `total_sum` rows are **PROHIBITED as formal E1-v4 replay inputs**. The snapshot used the per-marker IPPE measurements as the primary pose channel and mixed stable cross-pose and run effects into a covariance sum. It must not be silently updated or overwritten.
