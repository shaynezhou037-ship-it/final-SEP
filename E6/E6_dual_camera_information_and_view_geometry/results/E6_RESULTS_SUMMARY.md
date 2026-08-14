# E6 single/dual-camera and view-geometry pilot — results

Generated: 2026-08-14T10:05:00.285243+00:00

## Executive findings

- All retained pairs passed the acquisition sync gate; pair delta median/P95/max was 18.267/46.519/49.217 ms. The target was static.
- The cameras had similar oblique optical-axis tilt (61.3°/62.9°), but ihawk2 was closer and produced a larger Z=0 marker footprint (570/1002 px²). Camera identity and geometry remain confounded.
- A dedicated identifiability audit confirmed that the ten run-camera rows represent only two fixed placements; angle was never independently manipulated. Pooled angle/error correlations therefore cannot support a causal angle claim.
- At 25 mm, equal PnP fusion had 6.057 mm XY RMSE versus 8.850/4.786 mm for ihawk1/ihawk2. Naive averaging therefore worsened the stronger camera.
- Leave-one-rebuild-out PnP weighting reduced the damage (4.897 mm at 25 mm) but did not beat ihawk2 (4.786 mm). A second biased estimate is not automatically useful.
- In the strict XYZ ablation at 25 mm, 3-D RMSE was 10.348/6.144/7.431/6.351/3.342 mm for ihawk1/ihawk2/equal XYZ/LOO XYZ/stereo. Estimate fusion did not beat the stronger single camera on the rebuild mean.
- At 25 mm, the ihawk2-minus-stereo paired 3-D difference was 2.802 mm on average (range 1.856 to 3.946 mm), with stereo lower in 5/5 rebuilds. At 50 mm it was 1.105 mm (range -2.902 to 2.845 mm), with stereo lower in only 4/5; the aggregate advantage is therefore not rebuild-universal.
- The defensible conclusion is not 'two cameras are always better.' Independent-estimate fusion and calibrated stereo are distinct information flows: the former adds redundancy but can preserve bias; the latter adds parallax-based depth observability, with a benefit that still varies by rebuild and height.

## Key XY RMSE results (mean across five rebuilds)

| Model | Height | ihawk1 | ihawk2 | Equal fusion | LOO weighted |
|---|---:|---:|---:|---:|---:|
| Affine | 0 mm | 11.498 | 12.679 | 10.496 | 10.446 |
| Affine | 5 mm | 13.833 | 14.106 | 12.283 | 12.285 |
| Affine | 25 mm | 35.851 | 30.829 | 29.653 | 29.965 |
| Affine | 50 mm | 69.631 | 56.432 | 55.637 | 56.439 |
| Homography | 0 mm | 0.150 | 0.088 | 0.083 | 0.071 |
| Homography | 5 mm | 8.113 | 6.451 | 6.669 | 6.477 |
| Homography | 25 mm | 38.425 | 31.005 | 31.349 | 30.337 |
| Homography | 50 mm | 81.974 | 64.263 | 65.342 | 62.803 |
| PnP | 0 mm | 7.722 | 3.212 | 4.831 | 3.437 |
| PnP | 5 mm | 9.526 | 4.685 | 6.243 | 4.843 |
| PnP | 25 mm | 8.850 | 4.786 | 6.057 | 4.897 |
| PnP | 50 mm | 10.630 | 4.544 | 6.596 | 4.779 |

## Stereo triangulation

| Height | XY RMSE | Z RMSE | 3-D RMSE |
|---:|---:|---:|---:|
| 0 mm | 0.679 | 0.848 | 1.088 |
| 5 mm | 2.099 | 0.976 | 2.369 |
| 25 mm | 2.752 | 1.772 | 3.342 |
| 50 mm | 4.386 | 1.610 | 4.897 |

## Strict same-output XYZ ablation

All rows below estimate board XYZ and use the same five physical rebuilds as the statistical unit. PnP fusion weights are learned from the other four rebuilds at Z=0.

| Height | ihawk1 PnP 3-D | ihawk2 PnP 3-D | Equal XYZ | LOO weighted XYZ | Stereo 3-D | Stereo lower than ihawk2 (paired rebuilds) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 mm | 9.096 | 4.406 | 6.022 | 4.737 | 1.088 | 5/5 |
| 5 mm | 11.059 | 6.092 | 7.513 | 6.261 | 2.369 | 5/5 |
| 25 mm | 10.348 | 6.144 | 7.431 | 6.351 | 3.342 | 5/5 |
| 50 mm | 12.757 | 6.002 | 8.412 | 6.515 | 4.897 | 4/5 |

## Required interpretation

- `LOOWeightedGated` errors are conditional on accepted markers and must always be read with coverage.
- The angle analysis is descriptive because only two camera placements were tested and several geometric factors change together.
- `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` quantifies this confounding; it does not estimate an optimal view angle.
- Stereo uses Z=0-derived projection matrices and is not an independent metrology system.
- `fusion + stereo` is intentionally excluded from the core ablation: it reuses the same image pair in correlated estimators, adds a new fusion rule, and is not a separate information condition.
- With only five independent rebuilds, paired differences, SD/range, and sign counts are descriptive; marker rows are not treated as independent replicates.
- No dual-camera result has been propagated through E4 robot endpoint execution.
