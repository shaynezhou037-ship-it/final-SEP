# E7 — Moving-camera relocalization simulation

## Question

Does a movable camera necessarily perform worse than the fixed-camera PnP
pipeline, and which information flow remains valid after the camera pose changes?

## Important terminology

"Moving-camera algorithm" is not the opposite of PnP. A moving camera normally
needs to estimate its current pose from fixed world landmarks, and that
relocalization step can itself use PnP. E7 therefore compares calibration
strategies, rather than presenting PnP and camera motion as mutually exclusive.

## Status and evidence boundary

- This is a deterministic Monte Carlo **simulation-only pilot**.
- The ten nominal camera poses are the five E2 rebuilds × two real cameras.
- No physical camera was moved and no detector failures, blur, occlusion,
  vibration, rolling shutter, or robot endpoint effects are simulated.
- E7 can justify a follow-up acquisition; it is not yet main-paper physical
  validation.

## Frozen design

- Fixed world landmarks: the four outer E2 board markers (16 corners).
- Independent 50 mm target marker: five interior workspace positions.
- Target heights: 0, 10, 25, and 50 mm.
- Camera motion tiers: nominal (0 mm/0°), small (5 mm/0.5°), moderate
  (15 mm/2°), and large (30 mm/5°).
- Pixel noise sigma: 0.1, 0.5, and 1.0 px.
- Monte Carlo trials: 50 per nominal pose/motion/noise setting; seed 20260814.

## Compared information flows

1. `FrozenHomography`: reuse the nominal image-to-plane mapping.
2. `DynamicHomography`: refit a planar mapping from landmarks every frame.
3. `FrozenExtrinsicPnP`: solve target-marker PnP but reuse the nominal
   camera-to-board transform.
4. `RelocalizedPnP`: solve the current camera pose from fixed landmarks, solve
   target-marker PnP, then transform into the board frame.
5. `OracleMotionAwarePnP`: use the true simulated current camera pose; this is
   a lower-reference pipeline, not a deployable method.

## Reproduction

```powershell
python E7\E7_moving_camera_relocalization_simulation\scripts\e7_moving_camera_simulation.py
python E7\E7_moving_camera_relocalization_simulation\scripts\verify_e7_outputs.py
```

