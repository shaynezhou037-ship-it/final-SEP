# E1-v4R1 Reconstruction Contract

This directory implements the user-supplied reconstruction contract whose
verbatim source has SHA-256:

`7F510224A57C2989BDF0C1521C0143EC1686046BC20F2427CDF06FE0CE027488`

Artifact name: `E1-v4R1_reconstructed`. This is not E1-v5 and is not claimed
to be the unrecovered original source.

## Frozen definitions

- Fault order is `P(5), C(6), T(6), R(6)`, total 23.
- `P=[dfx,dfy,dcx,dcy,dk1]`.
- `C` and `T` are SE(3) translation-first twists.
- `R` contains only the six persistent UR5 joint-zero offsets.
- Transforms use right perturbations, `T_tilde=T Exp(delta_xi)`, and residuals
  use translation-first `Log(T_error)` coordinates.
- Evidence is vertically stacked as `zV, zR, zL, zG`.
- Processing order is whitening, fault-only engineering severity scaling, and
  nuisance projection. Nuisance columns are never severity-scaled.
- Each individual fault direction is normalized to 5-mm-equivalent RMS task
  error using a 0.1 m rotational lever arm.
- Actions are `P -> A_P`, `C/T -> A_C`, and `R -> A_R`. Required different
  action pairs are P-C, P-T, P-R, C-R, and T-R; C-T is excluded.
- Practical feasibility requires `d_min_cross >= 3`.

## Recovered evidence equations

For every image, target-pose nuisance is absorbed using training features:

`Bpose_i = -pinv(J_xi,tr,i) J_kappa,tr,i`

`J_V,i = J_kappa,ho,i + J_xi,ho,i Bpose_i`.

For relative visual motion `A_ij=T_CM,i^-1 T_CM,j`, the recovered zR
linearization is:

`delta_xi_CM,i = Bpose_i delta_kappa + Ad(X^-1) J_i^b delta_q0`

`delta_a_ij = -Ad(A_ij^-1) delta_xi_CM,i + delta_xi_CM,j`

`delta_r_ij = -Ad(X) Ad(A_ij) delta_a_ij + Ad(X)(Ad(A_ij)-I) delta_x`.

Thus zR contains P and R by relative-motion cancellation; C and T are exactly
zero without clipping.

The recovered zL block is:

`J_L=[Bpose, Ad(T_CM^-1), -I, Ad(X^-1)J_b]`.

The old zG executable was not recovered. The implementation differentiates a
physical base-fixed/flange-fixed fiducial forward equation and is labelled
`RECONSTRUCTION_CHOICE_zG_JACOBIAN`.

## Baseline and fingerprints

Baseline standard deviations are 0.17 px; 1.03 mm/0.719 deg single pose;
1.46 mm/1.02 deg relative pose; and a recorded nominal indexing coordinate of
0.05 deg. Historical minimum principal-angle fingerprints in degrees are:

| Pair | Historical |
|---|---:|
| P-C | 0.572 |
| P-T | 0.572 |
| P-R | 1.142 |
| C-R | 0.386 |
| T-R | 0.573 |

Specific historical residuals were about 0.95 sigma for C-yaw/q1 and 4.18
sigma for T-yaw/q6. Better camera and relative-pose precision must improve the
appropriate separations monotonically; indexing from 0.005 to 1 deg must not
become the dominant C-R control variable.

## Mandatory isolation gate

Until all restoration regression checks pass:

- E2 is not an input;
- no phase map is produced;
- no empirical replay is performed;
- no perfect-zG upper-bound result is claimed;
- no new experiment is authorized.

## Explicit reconstruction choices

The original source, exact pose list, seed, marker/camera geometry, zG
Jacobian, X_B/X_F construction, indexing covariance construction, and exact
d_min optimizer were not recovered. Every replacement is named in source and
in `results/reconstruction_manifest.json`; none may be described as historical
fact or selected using E2 outcomes.
