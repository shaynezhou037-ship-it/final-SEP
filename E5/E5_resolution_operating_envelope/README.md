# E5 — Effective-resolution operating-envelope pilot

## Purpose

E5 is an offline, low-cost extension of the formal E2 height-scan data. It asks
whether effective image resolution changes the practical choice among Affine,
Homography, and planar PnP when accuracy, detection reliability, and processing
latency are considered together.

This is **not** a native camera-resolution experiment. Every input is a saved,
lossless 640 x 400 E2 color frame. Lower resolutions are generated with
area-based downsampling, and the camera matrix is scaled to the corresponding
image geometry. Results therefore characterize simulated effective spatial
resolution under fixed exposure, optics, sensor readout, and scene content.

## Research questions

1. How does marker-detection success change as effective resolution decreases?
2. How do within-condition center and corner repeatability, and drift from the
   native-resolution detection, change?
3. How do Affine, Homography, and PnP XY errors change?
4. Does off-plane height amplify the downsampling penalty?
5. What are the median and P95 processing latencies for detection, mapping, and
   their sum on the analysis computer?
6. Under pre-registered accuracy, latency, and detection constraints, which
   model-resolution-height combinations remain empirically feasible?

## Frozen design

- Source: the five formal E2 rebuilds in
  `E2/E2_rebuilt/E2_all_5runs_REBUILT_clean.csv` and their saved color frames.
- Cameras: `ihawk1`, `ihawk2`.
- Heights: 0 to 50 mm in 5 mm steps.
- Expected markers: IDs 0 to 4, three frames per run/camera/height.
- Effective resolutions:
  - 640 x 400 (native saved image);
  - 480 x 300;
  - 320 x 200;
  - 240 x 150;
  - 160 x 100.
- Detector: OpenCV `DICT_4X4_50`, default detector parameters, followed by the
  same 3 x 3 `cornerSubPix` refinement used by the E2 collector.
- Calibration: each run/camera/resolution uses its own Z=0 observations; all
  five markers and all three frames must be detected. Models are then frozen
  for Z=5...50 mm, matching E2's comparison protocol.
- Accuracy unit: physical rebuild. Three frames are averaged before prediction;
  they are not treated as independent experiments.
- Latency: processing-only wall-clock time with one OpenCV thread. Disk I/O is
  excluded. Resize time is reported separately and excluded from the simulated
  native-resolution pipeline total. Detection includes grayscale conversion,
  marker detection, and corner refinement.

## Predefined feasibility profiles

Each height-specific combination must satisfy all three gates. Accuracy is the
observed P95 of run-level five-marker XY RMSE across available physical rebuilds.
At least four rebuilds are required.

| Profile | XY RMSE P95 | Pipeline P95 | Marker detection |
|---|---:|---:|---:|
| `precision_30hz` | <= 2 mm | <= 33.3 ms | >= 99% |
| `standard_20hz` | <= 5 mm | <= 50 ms | >= 99% |
| `coarse_10hz` | <= 10 mm | <= 100 ms | >= 95% |

These profiles are engineering screening constraints, not universal industrial
standards. Z=0 is the calibration condition rather than an independent held-out
plane, so feasibility labels remain conditional on this E2 protocol.

## Source-image integrity gate

The script re-detects every native frame and compares it with the frozen clean
CSV. An image is excluded when any expected marker is missing or the median
center displacement across the five markers exceeds 1 native pixel.

Preflight found that the six images for run `20260808_141232`, height 30 mm
(two cameras x three frames), were overwritten by a later acquisition entered
as 35 mm but saved into the 30 mm path. They are excluded from E5 and retained
in `results/E5_preflight_qc.csv` for audit. E2 data and results are not modified.

## Run

From the repository root:

```powershell
python E5/E5_resolution_operating_envelope/scripts/e5_resolution_operating_envelope.py
python E5/E5_resolution_operating_envelope/scripts/verify_e5_outputs.py
```

The script overwrites its named derived outputs under `results/` and `figures/`.
It does not modify E0-E4 source data.

## Main outputs

- `results/E5_RESULTS_SUMMARY.md`: concise human-readable findings.
- `results/E5_manifest.json`: frozen inputs, parameters, software, and output map.
- `results/E5_preflight_qc.csv`: native-frame traceability and exclusions.
- `results/E5_detection_summary.csv`: detection success by resolution/camera/height.
- `results/E5_stability_summary.csv`: center/corner repeatability and native drift.
- `results/E5_height_summary.csv`: XY accuracy across physical rebuilds.
- `results/E5_height_interaction_summary.csv`: downsampling penalty versus height.
- `results/E5_latency_summary.csv`: detection, mapping, and pipeline latency.
- `results/E5_feasibility_by_height.csv`: every constraint decision and reason.
- `results/E5_feasibility_summary.csv`: maximum contiguous feasible height.
- `figures/`: PNG and PDF figures generated only from the derived CSV results.

## Interpretation limits

- Downsampled copies share the same physical acquisition; resolution levels are
  paired transformations, not independent camera deployments.
- Sensor-mode effects such as exposure, read noise, frame rate, ISP behavior,
  and native-mode intrinsics are not varied.
- Timing is hardware/software specific and is not a robot control-loop deadline
  guarantee.
- Detection failures can create survivorship bias. Accuracy is reported only
  for complete five-marker run-height conditions, while failures remain visible
  in detection and feasibility outputs.
- The E2 Z=0 observations are reused for calibration. A future native-mode study
  should add an independent planar validation set.
