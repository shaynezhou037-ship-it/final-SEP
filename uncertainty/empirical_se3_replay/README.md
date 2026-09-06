# Empirical SE(3) uncertainty replay

This directory preserves the first raw audit and contains the corrected
board-level E2 camera-side analysis. It deliberately does not refit or
reconstruct E1-v4 from unstated assumptions.

## Status

- `freezes/E2-v0R0_raw_audit/` is an immutable audit snapshot. Its large
  `total_sum` is prohibited as a formal E1-v4 input.
- `E2-v1R0_board_pose/results/` is the current camera-side candidate. The
  primary measurement is one rigid-board pose from all 20 observed corners.
- `E1_V4_REPLAY_BLOCKER.md` records the exhaustive recovery search and the
  minimum original artifact needed before a perfect-geometry replay can run.

## Rebuild and verify the board-level analysis

```powershell
python uncertainty/empirical_se3_replay/build_e2_board_pose_v1.py
python uncertainty/empirical_se3_replay/verify_e2_board_pose_v1.py
```

The build reads the same five raw E2 acquisition CSVs and uses the retained
height-step IDs in `E2_REBUILD_MANIFEST.json`. It tests the printed-board
geometry against the geometry logged by the acquisition scripts. The actual
marker centres are `x = +/-70 mm`, `y = +/-113.5 mm`, plus `(0,0)`; this model
has lower paired reprojection error in all 330 frames.

PnP variation is represented in SE(3) log coordinates

\[
\xi_i = \operatorname{Log}(\bar T^{-1}T_i)
       = [\rho_x,\rho_y,\rho_z,\omega_x,\omega_y,\omega_z]^T.
\]

`rho_*` are SE(3)-log translation coordinates, not component-wise `tvec`
differences. Rodrigues-vector components are never assigned ordinary marginal
standard deviations.

## Current outputs

- `board_pose_candidates.csv`: both planar rigid-board IPPE branches.
- `board_pose_per_frame.csv`: refined 20-corner board pose and branch flags.
- `board_within_by_run_height_se3.csv`: group means and 6-D within covariance.
- `board_within_residuals_se3.csv`: all unclipped within-group log residuals.
- `Sigma_within_pooled_se3.csv`: pooled random measurement covariance by
  camera and height, using `sum_g(n_g-1)` degrees of freedom.
- `b_pose_se3.csv`: stable height-conditioned bias after each run's height-0
  baseline.
- `b_run_empirical_bank_se3.csv`: baseline-placement and condition-residual
  run effects, preserved as empirical vectors with `gaussian_fit=0`.
- `single_marker_ippe_candidates.csv` and
  `single_marker_ippe_failure_modes.csv`: all single-marker IPPE candidates and
  mode-switch flags retained as a failure-mode comparator; nothing is clipped.
- `geometry_hypothesis_audit.csv`, `manifest.json`, and `RESULTS_SUMMARY.md`:
  geometry evidence, provenance/hashes, and compact results.

No `total_sum` is produced. `Sigma_within`, `b_pose`, and `b_run` have separate
semantics and must remain separate in replay.

## Identifiability boundary

Each E2 run-height group contains three frames, so its unregularized 6-D sample
covariance has rank at most two. The pooled within covariance and the empirical
residual bank are supplied; a replay must use the rule already frozen by
E1-v4, not choose a regularizer after seeing performance.

The repository and available local histories contain the gate
`d_min^cross >= 3`, but not the original E1-v4 executable definition or frozen
acquisition sets. Therefore `Sigma_G=0` has not been evaluated: emitting a
number now would invent a replacement metric. See `E1_V4_REPLAY_BLOCKER.md`.
