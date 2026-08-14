# E6 camera-angle identifiability audit

Generated: 2026-08-14T07:44:46.656315+00:00

## Verdict

The current E6 data do **not** identify a causal camera-angle effect. The ten run-camera rows are five rebuild repetitions of only two fixed placements, not ten independently selected angles. Camera identity, distance, azimuth, marker footprint, optics, and calibration change together.

## Camera-identity separation

`eta²` is the fraction of observed variation in each geometry variable explained by the two camera identities. A non-overlapping range means the two fixed placements can be separated perfectly by that variable in this dataset.

| Geometry variable | ihawk1 mean [range] | ihawk2 mean [range] | Camera eta² | Standardized separation | Ranges overlap |
|---|---:|---:|---:|---:|---:|
| distance_to_board_center_mm | 630.460 [629.017, 631.614] | 524.859 [523.250, 525.734] | 0.9997 | -110.62 | no |
| optical_axis_tilt_to_board_normal_deg | 61.334 [61.214, 61.532] | 62.879 [62.824, 63.016] | 0.9863 | 15.18 | no |
| median_z0_marker_side_px | 27.790 [27.627, 28.161] | 35.413 [35.265, 35.585] | 0.9984 | 44.44 | no |
| median_z0_marker_footprint_px2 | 570.035 [569.112, 571.264] | 1002.486 [993.865, 1009.196] | 0.9997 | 108.78 | no |

## Permitted interpretation

- Report both cameras' placement geometry and marker footprint as descriptive setup information.
- Report pooled correlations only as diagnostics demonstrating confounding, never as evidence that tilt caused the error difference.
- Do not fit or publish an optimal-angle rule from these data. A controlled angle sweep would require new physical acquisition and is outside the no-rebuild plan.
