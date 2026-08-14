# E6 — Single/dual-camera information flow and view-geometry pilot

## Purpose

E6 reuses the paired, static-target E2 observations to test whether a second
camera adds useful information beyond the two existing single-camera results.
It separates three questions that must not be conflated:

1. Does naive or reliability-weighted averaging improve Affine, Homography, or
   PnP XY estimates?
2. Does a genuine two-view geometric method (stereo triangulation) improve 3-D
   localization when every condition is scored on the same XYZ output?
3. Are the different camera results descriptively consistent with their view
   distance, marker footprint, and view angle?

E6 is a vision-level offline experiment. It does not claim that dual-camera
fusion was executed through the E4 robot endpoint chain.

## Frozen inputs and units

- Formal E2 predictions: `E2/E2_rebuilt/model_comparison/E2_predictions.csv`.
- Formal clean observations: `E2/E2_rebuilt/E2_all_5runs_REBUILT_clean.csv`.
- Frozen per-run/camera board poses:
  `E2/E2_rebuilt/model_comparison/E2_calibration_models.json`.
- Five physical rebuilds, two cameras, 11 heights, five markers, three paired
  frames per condition.
- Every E2 pair passed the acquisition gate (`pair_delta_ms <= 50 ms`). Targets
  were static during capture; observed pair deltas are still reported.
- Physical rebuild is the accuracy summary unit. Frames are averaged before
  run-level metrics and are not independent physical experiments.

## Compared information flows

### Single camera

`image -> marker observation -> camera-specific model -> board-coordinate estimate`

### Dual estimate fusion

`paired images -> two camera-specific estimates -> common board coordinates -> fusion`

Fusion variants:

- `EqualFusion`: arithmetic mean of the two XY predictions.
- `LOOWeightedFusion`: fixed inverse-MSE camera weights learned from the other
  four rebuilds at Z=0, then applied to the held-out rebuild at all heights.
- `LOOWeightedGated`: the same weighted estimate is accepted only when the two
  camera predictions disagree by no more than the Z=0 P95 disagreement learned
  from the other four rebuilds. Coverage is reported with conditional error.

The leave-one-rebuild-out design prevents a rebuild from choosing its own
weights, but Z=0 is still the model-calibration condition rather than an
independent deployment-validation plane.

The core same-output-dimensionality ablation additionally compares `ihawk1`
PnP XYZ, `ihawk2` PnP XYZ, `EqualXYZ`, and `LOOWeightedXYZ`. The XYZ weights use
inverse 3-D MSE learned from the other four rebuilds at Z=0. Every condition is
scored with XY RMSE, Z RMSE, and 3-D RMSE.

### Dual-view triangulation

`paired image centers + two frozen projection matrices -> homogeneous stereo triangulation -> board XYZ`

This is not an average of two estimates. It uses parallax and the calibrated
relative geometry of the two views. Each synchronized frame pair is
triangulated, then the three frame-level 3-D points are averaged.

`fusion + stereo` is intentionally not a core condition. It would combine
correlated estimators derived from the same image pair, introduce another
fusion rule, and no longer isolate “another estimate” from “stereo geometry.”

The strict ablation is paired by physical rebuild. Per height it reports the
estimate-minus-stereo difference, SD/range, and the number of rebuilds in which
stereo has lower 3-D error; marker rows are not treated as independent trials.

## View-geometry diagnostics

For each run/camera, E6 reports:

- camera center in board coordinates;
- distance to board center;
- optical-axis tilt relative to the board normal;
- line-of-sight incidence angle;
- azimuth around the board;
- median Z=0 marker side and footprint in pixels;
- board-pose reprojection RMSE.

The generated angle-identifiability audit additionally measures how strongly
camera identity separates the geometry variables and reports the within-camera
angle range. This turns the confounding limitation into a reproducible result;
it does not create a controlled angle experiment.

The two cameras are not a controlled continuous angle sweep. Angle/error
associations have only ten run-camera units and are descriptive; camera identity,
distance, azimuth, optics, and marker footprint remain confounded.

## Run and verify

```powershell
python E6/E6_dual_camera_information_and_view_geometry/scripts/e6_dual_camera_analysis.py
python E6/E6_dual_camera_information_and_view_geometry/scripts/verify_e6_outputs.py
```

The main angle-specific outputs are
`results/E6_angle_identifiability_audit.json` and
`results/E6_ANGLE_IDENTIFIABILITY_AUDIT.md`.

The strict XYZ outputs are `results/E6_pnp3d_height_summary.csv` and
`results/E6_pnp3d_contrast_summary.csv`; detailed predictions, run metrics, and
the leave-one-rebuild-out weight audit are generated alongside them.

## Interpretation limits

- The two cameras share the same target, ground truth, acquisition session, and
  calibration plane; their errors are not guaranteed independent or unbiased.
- Equal averaging can worsen a strong camera by importing systematic bias from
  a weaker camera. More cameras do not automatically imply higher accuracy.
- Stereo results depend on the frozen Z=0 projection matrices. They are not an
  independently calibrated metrology reference.
- E2 is static, so the up-to-50-ms pair skew is not a dynamic-scene test.
- E6 does not validate dual-camera robot endpoint positioning or grasp success.
