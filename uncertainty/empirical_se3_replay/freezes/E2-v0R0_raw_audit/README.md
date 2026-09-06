# Empirical SE(3) uncertainty replay

This analysis implements the raw-data part of the frozen-model replay request.
It deliberately does not refit any E1 model.

## Run

```powershell
python uncertainty/empirical_se3_replay/build_empirical_components.py
python uncertainty/empirical_se3_replay/verify_empirical_components.py
```

The analysis reads:

- the latest complete formal E0-A run at each workspace position;
- the frozen E4-v4 calibration and E4 frozen-model held-out ChArUco
  per-frame observations;
- the five original E2 acquisition CSVs, filtered only by the retained
  height-step IDs in `E2_REBUILD_MANIFEST.json`.

PnP variation is represented in right-invariant SE(3) log coordinates

\[
\xi_i = \operatorname{Log}(\bar T^{-1}T_i)
       = [\rho_x,\rho_y,\rho_z,\omega_x,\omega_y,\omega_z]^T.
\]

`rho_*` are the translational coordinates of the SE(3) logarithm, not a
component-wise subtraction of `tvec`. Rotations are never summarized by
taking ordinary standard deviations of the three stored Rodrigues-vector
components.

## Outputs

- `results/pixel_within.csv`: 2-D within-condition covariance by
  pose/height/run and image feature.
- `results/pnp_within_se3.csv`: SE(3) mean and 6-D within covariance by
  pose/height/run.
- `results/pnp_within_residuals_se3.csv`: every observed within-group SE(3)
  log residual, retained for non-Gaussian empirical replay.
- `results/run_bias_se3.csv`: the requested
  `Log(inv(T_bar_pose) @ T_bar_pose_run)` vectors for repeated E2 runs.
- `results/e2_hierarchical_components_se3.csv`: within-pose, between-run,
  cross-pose, and their covariance sum in board-normalized coordinates.
- `results/e2_hierarchical_vectors_se3.csv`: the actual empirical vectors
  behind those three hierarchical covariance components.
- `results/manifest.json`: provenance, conventions, inclusion rules, hashes,
  and data limitations.
- `results/RESULTS_SUMMARY.md`: compact data audit and numerical summary.

## Identifiability boundary

E0-A stores marker centers and depth-derived XYZ only. It does not store four
marker corners or a pose estimate, so a 6-D PnP covariance cannot be recovered
from that dataset. E0-A therefore contributes a genuine 2-D pixel covariance
only. E4 has one frozen physical setup observed in two acquisition stages, so
it contributes within-stage covariance and a calibration-to-held-out temporal
bias, but not an independent physical-rebuild covariance. The five-rebuild
decomposition is identified by E2.

Each E2 pose/height/run group contains only three frames. Its unregularized 6-D
sample covariance therefore has rank at most two and must not be inverted or
treated as a well-estimated full-rank Gaussian. The residual-vector output is
provided so a frozen replay can resample the observed residuals, or use a
pooling rule that was specified before inspecting replay performance. Planar
PnP can also be multi-modal; retaining the empirical vectors prevents a large
pose-solution jump from being hidden by six marginal standard deviations.

The repository currently contains no artifact named or declared as `E1-v4`,
and it contains no definition of `d_min,emp^cross` or its feasible boundary.
Consequently this directory stops before Step 3 rather than silently fitting a
replacement model. Once the frozen E1-v4 artifact and its input/output contract
are supplied, empirical replay must consume the CSVs above without modifying
the frozen artifact.
