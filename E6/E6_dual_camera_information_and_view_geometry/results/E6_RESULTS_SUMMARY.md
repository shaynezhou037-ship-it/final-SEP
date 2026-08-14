# E6 single/dual-camera and view-geometry pilot — results

Generated: 2026-08-14T07:44:47.539437+00:00

## Executive findings

- All retained pairs passed the acquisition sync gate; pair delta median/P95/max was 18.267/46.519/49.217 ms. The target was static.
- The cameras had similar oblique optical-axis tilt (61.3°/62.9°), but ihawk2 was closer and produced a larger Z=0 marker footprint (570/1002 px²). Camera identity and geometry remain confounded.
- A dedicated identifiability audit confirmed that the ten run-camera rows represent only two fixed placements; angle was never independently manipulated. Pooled angle/error correlations therefore cannot support a causal angle claim.
- At 25 mm, equal PnP fusion had 6.057 mm XY RMSE versus 8.850/4.786 mm for ihawk1/ihawk2. Naive averaging therefore worsened the stronger camera.
- Leave-one-rebuild-out PnP weighting reduced the damage (4.897 mm at 25 mm) but did not beat ihawk2 (4.786 mm). A second biased estimate is not automatically useful.
- Stereo triangulation was materially different: XY RMSE was 0.679, 2.099, 2.752, and 4.386 mm at 0/5/25/50 mm. It outperformed ihawk1 PnP throughout and was competitive with or better than ihawk2 PnP over most tested heights.
- The new defensible conclusion is not 'two cameras are always better.' It is that estimate averaging and two-view geometry are different information flows: averaging preserves systematic bias, while calibrated parallax can add genuine depth information.

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

## Required interpretation

- `LOOWeightedGated` errors are conditional on accepted markers and must always be read with coverage.
- The angle analysis is descriptive because only two camera placements were tested and several geometric factors change together.
- `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` quantifies this confounding; it does not estimate an optimal view angle.
- Stereo uses Z=0-derived projection matrices and is not an independent metrology system.
- No dual-camera result has been propagated through E4 robot endpoint execution.
