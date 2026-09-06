# E1-v4 recovery audit and replay blocker

Status: `BLOCKED_RECONSTRUCTION_REGRESSION_FAIL`  
Important: this is an analysis-input blocker, **not** a scientific `STOP`
decision. The perfect-geometry upper bound has not been evaluated.

## Reconstruction update (2026-09-06)

The investigator subsequently supplied an `E1-v4R1 Reconstruction Contract`
(SHA-256 `7F510224A57C2989BDF0C1521C0143EC1686046BC20F2427CDF06FE0CE027488`).
A clean-room, E2-disconnected candidate now exists at
`../e1_v4r1_reconstructed/`.

Its SE(3), finite-difference, zR cancellation, action-mapping, and fail-closed
gate tests pass. However, the historical restoration regression currently
passes only 10 of 13 checks. The unresolved checks are the P-C and P-T nominal
principal-angle fingerprints and the consequent requirement that C-R be the
most dangerous cross-action near-gauge. Therefore this candidate is **not** a
formal E1-v4 replay input.

The candidate manifest keeps all downstream permissions false. In particular,
no phase map, E2 replay, perfect-zG upper bound, STOP decision, or ONE-RESCUE
authorization has been produced.

### P-block diagnostic update

`../e1_v4r1_reconstructed/diagnostics/E1-v4R1_P_BLOCK_DIAGNOSTIC/`
contains a read-only channel-attribution, zV nuisance, P-mode ablation,
camera-geometry recovery, gauge-scale, measurement-count, and nuisance-rank
audit. Its manifest proves that the reconstruction core hashes did not change,
and the regression was not rerun.

The immediate cause of the P-C/P-T collapse is now localized: per-view pose
nuisance retains only about `7.75e-7`/`5.15e-7` of the dangerous P direction's
held-out zV norm, while the shared X_F nuisance removes nearly all of its zG
response. The remaining signal is almost entirely zL and is depth-like. This
supports a missing zV feature/view geometry plus nuisance-construction blocker,
not a UR5 kinematics repair.

### zV geometry causality update

A subsequent controlled test changed only the nine zV camera-target poses and
held every non-zV operator and covariance hash fixed. P-C/P-T increased from
`0.000180/0.000135 deg` for the current nearly fronto-parallel geometry, to
`0.2536/0.2578 deg` with moderate tilt/depth/coverage diversity, and to
`0.7345/0.7276 deg` with calibration-like diversity. All target points remained
inside the image. This establishes camera-target geometry as causal within the
reconstructed model, but does not recover or authorize substitution of the
historical zV geometry. Regression therefore remains unchanged and fail-closed.

## What is frozen and usable

- The former analysis is preserved, without deletion, as
  `freezes/E2-v0R0_raw_audit/`.
- Its manifest sets `formal_e1_v4_input=false`; the large `total_sum` is
  explicitly prohibited as an E1-v4 input.
- The corrected camera-side analysis is available as
  `E2-v1R0_board_pose/results/` and keeps `Sigma_within`, `b_pose`, and the
  empirical `b_run` bank separate.
- The previously fixed research gate supplied by the investigator is
  `d_min^cross >= 3` for practical feasibility. This threshold is preserved;
  it is not enough by itself to reconstruct the metric.

## Recovery searches completed

The following read-only recovery paths were searched on 2026-09-06:

1. Repository working tree, all Git refs/branches, commit history, reflog,
   stash, and unreachable objects reported by `git fsck`.
2. VS Code local History.
3. Local Codex session records under `C:/Users/ASUS/.codex/sessions`.
4. User Desktop, Documents, and Downloads text-like files.

No pre-existing E1-v4 executable, configuration, frozen candidate set, random
seed, or complete definition of `d_min,emp^cross` was found. The only E1-v4
matches in local Codex history are the current request and the current blocker
discussion. Consequently there is no recoverable artifact here that can be
hashed and frozen without inventing missing semantics.

## Why the perfect-z_G replay was not run

Setting `Sigma_G=0` removes the geometry-channel uncertainty, but does not
define any of the following E1-v4 quantities:

1. The fixed acquisition-set candidates or their frozen generator.
2. The mapping from E2 camera/height conditions to E1-v4 conditions.
3. The exact distance formula, coordinate scaling/units, and covariance or
   empirical-resampling rule used by `d_min,emp^cross`.
4. What `cross` ranges over.
5. The frozen definition of `d_worst/plausible`, replay count, and seed.

Choosing any of these now would create a new metric rather than restore
E1-v4. Therefore no numerical `d_min,emp^cross`, median, P10, or
worst/plausible value is emitted, and neither `STOP` nor `ONE-RESCUE` is
scientifically authorized yet.

## Minimum handoff needed to unblock

The contract restored most mathematical semantics. To clear the remaining
regression blocker without outcome-tuning, recover any one source containing
the original camera/target geometry and zV feature layout, the old X_B/X_F and
indexing covariance construction, or the original E1-v3 operator matrices.
Any recovered source should be copied verbatim into a read-only freeze with
its SHA-256 and used to replace the corresponding labelled reconstruction
choice. Only after the historical regression passes may `Sigma_G=0` be
evaluated against the fixed `d_min^cross >= 3` gate.

The decision rule after recovery is:

- `d_min,emp^cross < 3`: scientific `STOP`; do not run a new robot experiment.
- `d_min,emp^cross >= 3`: geometry quality is decision-changing; proceed only
  to the scoped ONE-RESCUE experiment.
