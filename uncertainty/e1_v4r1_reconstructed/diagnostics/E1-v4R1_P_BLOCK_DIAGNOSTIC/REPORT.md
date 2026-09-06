# E1-v4R1 P-block diagnostic

Status: `DIAGNOSTIC_COMPLETE_REGRESSION_UNCHANGED_FAIL_CLOSED`

No evidence formula, configuration, noise value, threshold, regression result,
or E2 artifact was changed.

## Primary answer

The current P-C/P-T collapse is localized to **zV observability plus the
reconstructed nuisance geometry**, not to UR5 kinematics. The dangerous P
directions are absorbed extremely strongly by per-view target-pose nuisance.
Their roughly 10.27-sigma pre-projection zG response is then also absorbed by
the shared X_F nuisance, leaving almost only the 14.56-sigma zL depth-like
response. That response is nearly collinear with C/T depth translation.

| Pair | angle | zV before nuisance | zV after nuisance | retained fraction |
|---|---:|---:|---:|---:|
| P-C | 0.000179960 deg | 36.178 sigma | 2.8036e-05 sigma | 7.749e-07 |
| P-T | 0.000135366 deg | 36.2911 sigma | 1.86975e-05 sigma | 5.152e-07 |

Normalized P coefficients in `[dfx, dfy, dcx, dcy, dk1]` order:

- P-C: `[0.94753908, 0.31946989, -0.00309904, -0.00099834, -0.00990336]`
- P-T: `[0.94753626, 0.31948138, -0.00211009, -0.00212198, -0.00988582]`

The coefficient vectors and channel attribution are in `diagnostic.json` and
`dangerous_direction_channel_norms.csv`.

## P-mode ablation

| P subset | P-C | P-T |
|---|---:|---:|
| fx, fy | 0.0187586 deg | 0.0216899 deg |
| cx, cy | 0.0650627 deg | 0.0400412 deg |
| k1 | 1.85348 deg | 2.15817 deg |
| fx, fy, k1 | 0.000280744 deg | 0.000159663 deg |
| full P | 0.000179954 deg | 0.000135368 deg |

Focal/depth ambiguity is already severe at about 0.02 deg. k1 alone is not the
limiter, but allowing k1 to combine with fx/fy supplies the compensation that
collapses the angle by roughly two further orders of magnitude. This is an
ablation only; no P mode is removed from the formal model.

## Camera-geometry recovery result

The nine current zV views come from `task_poses_rad`. They are robot routine
configurations and are **not recovered historical zV calibration views**. The
investigator's recovered seven center/+/-X/Y/Z routine configurations likewise
describe robot-side local geometry; no evidence currently identifies them as
zV calibration views.

A local repository artifact does recover a different E1 planar experiment:
6x8 inner corners at 25 mm, 12 spread training points, 36 held-out points, one
fixed view summarized over 50 frames, K near (401.77, 401.92, 322.13, 202.54),
and undistorted pixels with D=0. There is no recovered provenance tying that
artifact to the E1-v3 uncertainty simulator, so this diagnostic does not swap
it into the model.

## Absolute-scale and nuisance audit

The current measurement inventory is zV=9
views, zR=8 pose
pairs, zL=9 poses, and
zG=9 poses.
All listed residual rows are treated as independent by the diagonal covariance.

`nuisance_rank=6` comes entirely from X_F columns shared by zR and zG. X_B is
zero in every current channel; zV and zL have no global nuisance columns. This
is a labelled reconstruction choice, not a recovered E1-v3 fact.

The total whitened/severity-scaled C_wz signal is 14.495 sigma, close to the
historical total-signal note of about 12.8 sigma. Therefore the 0.28--0.30x
gauge residuals are **not** explained by one global whitening-scale error.
For C_wz/q1, nuisance projection reduces the directed residual from
8.356 to
0.2823 sigma; for
T_wz/q6 it changes 1.182
to 1.153 sigma. The
common remaining factor is consistent with weaker/missing independent zR/zG
information. If measurement count alone were responsible it would correspond
to roughly 11.32x
and 13.15x
more independent information, respectively; this is a diagnostic equivalence,
not evidence that the historical experiment actually used those counts.

Stage-by-stage and per-channel norms for C_wz, q1, T_wz, and q6 are in
`gauge_stage_channel_norms.csv`; directed residuals are in
`gauge_stage_residuals.csv`.

## Gate

Regression was not rerun because no model input changed. P-C/P-T restoration
remains blocked. d_min, phase map, E2 replay, and perfect-zG remain prohibited.
