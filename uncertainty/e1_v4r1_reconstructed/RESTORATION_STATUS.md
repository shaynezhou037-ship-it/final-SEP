# E1-v4R1 restoration status

Status: `FAIL_CLOSED` (10/13 historical checks pass).

This is a reconstruction-regression result, not a scientific STOP result.
E2 has not been connected and perfect-zG has not been evaluated.

## Current nominal fingerprints

| Quantity | Reconstructed | Historical |
|---|---:|---:|
| P-C minimum principal angle | 0.000180 deg | 0.572 deg |
| P-T minimum principal angle | 0.000135 deg | 0.572 deg |
| P-R minimum principal angle | 0.391 deg | 1.142 deg |
| C-R minimum principal angle | 0.605 deg | 0.386 deg |
| T-R minimum principal angle | 0.775 deg | 0.573 deg |
| C-yaw versus q1 residual | 0.282 sigma | 0.95 sigma |
| T-yaw versus q6 residual | 1.153 sigma | 4.18 sigma |

The qualitative gauge contrast is restored: C-yaw/q1 is much harder than
T-yaw/q6, and improving relative-pose precision strengthens the separation.
The camera-quality trend is monotonic and the indexing sweep is invariant in
the current persistent-offset treatment.

## Remaining blocker

The limiting P direction is mostly a focal-length/radial-distortion
combination and is almost exactly aligned with C/T depth translation under the
reconstructed planar, fixed-orientation target geometry. This drives P-C and
P-T nearly to zero and prevents C-R from being the globally smallest pair.

Changing coefficients to hit the old values would violate the contract. The
next valid input is recovered evidence for the original camera/target feature
geometry or the frozen E1-v3 `J_aug`/subspace operators. The old X_B/X_F and
correlated indexing covariance constructions would also reduce remaining
uncertainty.

The reconstructed constrained diagnostic currently gives
`d_min_cross=0.0856`, but it is explicitly
`RECONSTRUCTION_CHOICE_dmin_equal_severity_unit_direction`; because the
historical regression is FAIL, it is not a formal E1-v4 result and must not be
used with the threshold 3 gate.
