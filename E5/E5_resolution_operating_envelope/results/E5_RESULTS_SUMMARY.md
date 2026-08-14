# E5 effective-resolution pilot — results summary

Generated: 2026-08-14T06:56:31.678440+00:00

## Data and QC

- Source: 330 saved E2 color images and 1650 expected marker observations.
- QC excluded 6 images. These are the overwritten run 20260808_141232 / 30 mm images described in the README.
- All conclusions below are conditional on simulated downsampling of 640 x 400 images.

## Executive findings

- Native 640 x 400 detection was complete for both cameras, and the worst model-specific native pipeline P95 was only 8.149 ms; every native pipeline therefore passed the predefined 30 Hz latency gate.
- At 480 x 300, complete five-marker frames fell to 78.4% for ihawk1 and 98.8% for ihawk2. Lower resolutions lost substantially more observations.
- Affine/Homography mapping itself cost at most 0.026 ms P95 at native resolution; PnP cost at most 1.784 ms. Detection, not the final matrix mapping, dominated processing time.
- PnP showed a resolution cost even when detection remained complete: for ihawk2 at 25 mm, mean XY RMSE changed from 4.786 mm (640 x 400) to 12.808 mm (480 x 300) and 18.126 mm (320 x 200).
- Height did not consistently amplify the downsampling penalty across cameras and models. The dominant, reproducible effects were camera-dependent detection loss and a PnP resolution-related bias, not a universal resolution x height interaction.
- Under the predefined budgets, reducing resolution was unnecessary on this computer because the native pipeline already met the strictest latency gate. The pilot therefore supports a supplementary operating-limit/negative-result role, not a new main speed-accuracy contribution by itself.

## Overall marker detection

| Camera | Resolution | Marker detection | Complete 5-marker images |
|---|---:|---:|---:|
| ihawk1 | 640x400 | 100.0% | 100.0% |
| ihawk1 | 480x300 | 95.3% | 78.4% |
| ihawk1 | 320x200 | 76.8% | 19.1% |
| ihawk1 | 240x150 | 43.7% | 0.0% |
| ihawk1 | 160x100 | 6.0% | 0.0% |
| ihawk2 | 640x400 | 100.0% | 100.0% |
| ihawk2 | 480x300 | 99.8% | 98.8% |
| ihawk2 | 320x200 | 94.1% | 71.6% |
| ihawk2 | 240x150 | 71.9% | 10.5% |
| ihawk2 | 160x100 | 30.1% | 0.0% |

## Processing latency

Processing-only timing; image I/O and simulated resize are excluded from pipeline totals.

| Camera | Resolution | Model | Detection P95 (ms) | Mapping P95 (ms) | Pipeline P95 (ms) |
|---|---:|---|---:|---:|---:|
| ihawk1 | 640x400 | Affine | 6.642 | 0.026 | 6.659 |
| ihawk1 | 640x400 | Homography | 6.642 | 0.025 | 6.658 |
| ihawk1 | 640x400 | PnP | 6.642 | 1.784 | 8.149 |
| ihawk1 | 480x300 | Affine | 4.025 | 0.022 | 4.043 |
| ihawk1 | 480x300 | Homography | 4.025 | 0.023 | 4.042 |
| ihawk1 | 480x300 | PnP | 4.025 | 2.083 | 5.617 |
| ihawk1 | 320x200 | Affine | 2.286 | 0.019 | 2.303 |
| ihawk1 | 320x200 | Homography | 2.286 | 0.020 | 2.303 |
| ihawk1 | 320x200 | PnP | 2.286 | 1.715 | 3.887 |
| ihawk1 | 240x150 | Affine | NA | NA | NA |
| ihawk1 | 240x150 | Homography | NA | NA | NA |
| ihawk1 | 240x150 | PnP | NA | NA | NA |
| ihawk1 | 160x100 | Affine | NA | NA | NA |
| ihawk1 | 160x100 | Homography | NA | NA | NA |
| ihawk1 | 160x100 | PnP | NA | NA | NA |
| ihawk2 | 640x400 | Affine | 6.117 | 0.024 | 6.133 |
| ihawk2 | 640x400 | Homography | 6.117 | 0.023 | 6.133 |
| ihawk2 | 640x400 | PnP | 6.117 | 1.493 | 7.338 |
| ihawk2 | 480x300 | Affine | 3.851 | 0.021 | 3.880 |
| ihawk2 | 480x300 | Homography | 3.851 | 0.022 | 3.867 |
| ihawk2 | 480x300 | PnP | 3.851 | 1.590 | 5.122 |
| ihawk2 | 320x200 | Affine | 2.492 | 0.025 | 2.509 |
| ihawk2 | 320x200 | Homography | 2.492 | 0.025 | 2.508 |
| ihawk2 | 320x200 | PnP | 2.492 | 2.105 | 4.156 |
| ihawk2 | 240x150 | Affine | 1.431 | 0.024 | 1.448 |
| ihawk2 | 240x150 | Homography | 1.431 | 0.017 | 1.447 |
| ihawk2 | 240x150 | PnP | 1.431 | 1.824 | 3.126 |
| ihawk2 | 160x100 | Affine | NA | NA | NA |
| ihawk2 | 160x100 | Homography | NA | NA | NA |
| ihawk2 | 160x100 | PnP | NA | NA | NA |

## Height amplification

Positive values mean the downsampling penalty grows from 0 to 50 mm; negative values mean it does not.

| Camera | Resolution | Model | Penalty slope (mm error/mm height) | Amplification 0→50 mm |
|---|---:|---|---:|---:|
| ihawk1 | 480x300 | Affine | 0.0159 | 0.395 |
| ihawk1 | 480x300 | Homography | 0.0309 | 0.625 |
| ihawk1 | 480x300 | PnP | 0.0238 | -1.261 |
| ihawk1 | 320x200 | Affine | NA | NA |
| ihawk1 | 320x200 | Homography | NA | NA |
| ihawk1 | 320x200 | PnP | NA | NA |
| ihawk1 | 240x150 | Affine | NA | NA |
| ihawk1 | 240x150 | Homography | NA | NA |
| ihawk1 | 240x150 | PnP | NA | NA |
| ihawk1 | 160x100 | Affine | NA | NA |
| ihawk1 | 160x100 | Homography | NA | NA |
| ihawk1 | 160x100 | PnP | NA | NA |
| ihawk2 | 480x300 | Affine | 0.0019 | 0.096 |
| ihawk2 | 480x300 | Homography | 0.0075 | 0.301 |
| ihawk2 | 480x300 | PnP | 0.0352 | 1.037 |
| ihawk2 | 320x200 | Affine | -0.0055 | -0.173 |
| ihawk2 | 320x200 | Homography | -0.0092 | -0.592 |
| ihawk2 | 320x200 | PnP | 0.0084 | -0.756 |
| ihawk2 | 240x150 | Affine | NA | NA |
| ihawk2 | 240x150 | Homography | NA | NA |
| ihawk2 | 240x150 | PnP | NA | NA |
| ihawk2 | 160x100 | Affine | NA | NA |
| ihawk2 | 160x100 | Homography | NA | NA |
| ihawk2 | 160x100 | PnP | NA | NA |

## Feasibility summary

Maximum contiguous feasible height beginning at Z=0; `—` means Z=0 itself failed at least one gate. Z=0 is the calibration condition, not an independent planar test.

| Profile | Camera | Resolution | Affine | Homography | PnP |
|---|---|---:|---:|---:|---:|
| precision_30hz | ihawk1 | 640x400 | — | 0 mm | — |
| precision_30hz | ihawk1 | 480x300 | — | 0 mm | — |
| precision_30hz | ihawk1 | 320x200 | — | — | — |
| precision_30hz | ihawk1 | 240x150 | — | — | — |
| precision_30hz | ihawk1 | 160x100 | — | — | — |
| precision_30hz | ihawk2 | 640x400 | — | 0 mm | — |
| precision_30hz | ihawk2 | 480x300 | — | 0 mm | — |
| precision_30hz | ihawk2 | 320x200 | — | 0 mm | — |
| precision_30hz | ihawk2 | 240x150 | — | — | — |
| precision_30hz | ihawk2 | 160x100 | — | — | — |
| standard_20hz | ihawk1 | 640x400 | — | 0 mm | — |
| standard_20hz | ihawk1 | 480x300 | — | 0 mm | — |
| standard_20hz | ihawk1 | 320x200 | — | — | — |
| standard_20hz | ihawk1 | 240x150 | — | — | — |
| standard_20hz | ihawk1 | 160x100 | — | — | — |
| standard_20hz | ihawk2 | 640x400 | — | 0 mm | 0 mm |
| standard_20hz | ihawk2 | 480x300 | — | 0 mm | 0 mm |
| standard_20hz | ihawk2 | 320x200 | — | 0 mm | — |
| standard_20hz | ihawk2 | 240x150 | — | — | — |
| standard_20hz | ihawk2 | 160x100 | — | — | — |
| coarse_10hz | ihawk1 | 640x400 | — | 0 mm | 0 mm |
| coarse_10hz | ihawk1 | 480x300 | — | 0 mm | — |
| coarse_10hz | ihawk1 | 320x200 | — | — | — |
| coarse_10hz | ihawk1 | 240x150 | — | — | — |
| coarse_10hz | ihawk1 | 160x100 | — | — | — |
| coarse_10hz | ihawk2 | 640x400 | — | 5 mm | 40 mm |
| coarse_10hz | ihawk2 | 480x300 | — | 5 mm | 0 mm |
| coarse_10hz | ihawk2 | 320x200 | — | 5 mm | — |
| coarse_10hz | ihawk2 | 240x150 | — | — | — |
| coarse_10hz | ihawk2 | 160x100 | — | — | — |

## Required interpretation

- Inspect `E5_height_summary.csv`, `E5_height_interaction_summary.csv`, and the figures before promoting any pattern to a paper claim.
- A useful paper extension requires a reproducible model × resolution interaction or a non-trivial feasibility trade-off; a generic 'lower resolution is faster/worse' result is insufficient.
- Native multi-resolution acquisition is required before making claims about sensor modes or production hardware.
