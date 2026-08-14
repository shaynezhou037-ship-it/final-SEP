# E7 moving-camera relocalization simulation — results

Generated: 2026-08-14T07:20:57.083764+00:00

## Executive findings

- E7 is simulation-only. It does not yet show real moving-camera performance.
- PnP is not opposed to a moving-camera algorithm: `RelocalizedPnP` uses PnP both to recover the current camera pose from fixed landmarks and to recover the target marker pose.
- Frozen mappings become stale after camera motion. Per-frame relocalization is the relevant comparison.
- Per-frame Homography can compensate camera motion for planar targets, but its planar assumption remains invalid at nonzero target height.
- At Z=0 and 0.5 px noise, per-frame Homography stayed near 0.87 mm XY RMSE from nominal through the largest motion, while frozen Homography grew from 1.21 to 68.54 mm.
- At Z=25 mm, per-frame Homography stayed near 35 mm because it repaired camera motion but not the violated planar assumption.
- At Z=25 mm, frozen-extrinsic PnP grew from 6.84 to 40.61 mm; relocalized PnP remained 6.62-6.85 mm and was close to the oracle (6.59-6.84 mm). Camera motion itself was not the limiting error after relocalization.

## Headline XY results: 25 mm target height, 0.5 px corner noise

| Method | Nominal RMSE/P95 | Small RMSE/P95 | Moderate RMSE/P95 | Large RMSE/P95 |
|---|---:|---:|---:|---:|
| FrozenHomography | 33.902/42.385 | 34.592/50.521 | 44.406/80.157 | 86.378/167.670 |
| DynamicHomography | 34.803/43.093 | 34.842/43.179 | 34.836/43.512 | 35.075/44.270 |
| FrozenExtrinsicPnP | 6.843/13.991 | 8.343/15.681 | 18.938/31.604 | 40.612/67.466 |
| RelocalizedPnP | 6.846/13.857 | 6.623/13.805 | 6.731/13.525 | 6.809/13.965 |
| OracleMotionAwarePnP | 6.843/13.991 | 6.592/13.608 | 6.708/13.437 | 6.759/13.762 |

All values are millimetres. Each cell pools five E2 rebuilds × two cameras × five target positions × 50 Monte Carlo trials.

## Interpretation boundary

- The Monte Carlo trials are simulated perturbations, not independent physical repeats.
- The detector is represented only by Gaussian corner noise; missed detections, motion blur, occlusion, vibration, rolling shutter, and timing are absent.
- The four motion tiers combine translation and rotation, so this pilot does not independently identify their effects.
- A physical E7 acquisition is required before using moving-camera claims as central paper evidence.
