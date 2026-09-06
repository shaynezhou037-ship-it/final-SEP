# zV Geometry Causality Test

Status: `DIAGNOSTIC_COMPLETE_CORE_UNCHANGED`

Only the nine zV camera-target transforms were intervened on. Fault basis,
S_theta, all noise values, nuisance construction, UR5, zR/zL/zG matrices,
target points, view count, train/hold-out split, intrinsics, and k1 convention
were fixed and hash-checked.

| Geometry | P-C | P-T | tilt range | depth range | image coverage |
|---|---:|---:|---:|---:|---:|
| G0 current | 0.000179945835 deg | 0.000135352073 deg | 0.06-0.06 deg | 1.869-1.869 m | u 265.7-304.1, v 38.2-76.2 |
| G1 moderate | 0.253595551 deg | 0.257782555 deg | 14.11-21.52 deg | 0.750-1.050 m | u 177.2-451.0, v 125.6-347.5 |
| G2 calibration-like | 0.734488248 deg | 0.727598247 deg | 34.78-48.44 deg | 0.450-0.950 m | u 22.8-619.6, v 27.5-442.1 |

P-C changed by 4.08e+03x and P-T by
5.38e+03x from G0 to G2. Monotonicity
was P-C=True and P-T=True.

## zV singular values before/after target-pose nuisance

Raw native-parameter singular values, descending:

| Geometry | before nuisance: sv(J_kappa,ho) | after nuisance: sv(J_V) |
|---|---|---|
| G0 | `[231.386, 12.41, 2.14415, 0.208921, 0.0364715]` | `[1.51853, 0.0187092, 0.000393691, 0.000129004, 5.39438e-09]` |
| G1 | `[26.6752, 12.3694, 12.3681, 1.03544, 0.482171]` | `[5.55037, 0.118099, 0.021858, 0.0209403, 0.00482957]` |
| G2 | `[409.684, 12.3694, 12.3687, 2.5593, 0.916469]` | `[40.5747, 0.123804, 0.0563557, 0.0422126, 0.0138792]` |

The smallest post-nuisance singular value rises from about 5.39e-9 in G0 to
4.83e-3 in G1 and 1.39e-2 in G2. Full raw and whitened/severity-scaled spectra
are preserved in `zV_singular_values.csv`.

This is a controlled within-model causality result, not a recovery of the old
E1 geometry and not a fit to the historical 0.57-degree fingerprint.
Regression, d_min, phase map, E2, and perfect-zG were not run.
