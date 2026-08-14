# E6/E7 novelty decision note

Status: decision implemented in `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md` v2.2. The
author chose **no physical rebuild** on 2026-08-14.

## Decision

E6 produces a useful new result for this project and is now assigned to the
main paper. E5 supports the deployment envelope. E7 produces a mechanism
hypothesis but remains a simulation-only supplementary analysis; physical
validation is no longer a prerequisite for writing because the project will
not be rebuilt.

The promising paper direction is not "which model wins." It is:

> Which visual information is sufficient under each deployment condition —
> planar/off-plane target, effective resolution, one/two views, and
> fixed/relocalized camera — and where does each low-cost pipeline cease to be
> operationally valid?

This is broader and more defensible than reporting only Affine/Homography/PnP
accuracy rankings.

## E6: conclusions supported by real E2 data

1. **Two estimates are not automatically more informative.** At 25 mm,
   equal PnP fusion was 6.057 mm XY RMSE, between ihawk1 (8.850 mm) and ihawk2
   (4.786 mm). Leave-one-rebuild-out weighting reached 4.897 mm and still did
   not beat the stronger camera.
2. **Estimate fusion and two-view geometry are different information flows.**
   Stereo triangulation reached 2.752 mm XY RMSE and 1.772 mm Z RMSE at 25 mm.
   At 50 mm it reached 4.386 mm XY RMSE, compared with 10.630/4.544 mm for the
   two single-camera PnP pipelines.
3. **The defensible claim is conditional, not universal.** A second camera is
   valuable when its parallax is actually used; naive averaging can preserve
   systematic bias and worsen the better single-camera result.
4. **There is no causal view-angle conclusion.** The two cameras had
   similar optical-axis tilt (about 61-63 degrees). Distance, azimuth, marker
   footprint, camera identity, and calibration also changed together. ihawk2's
   larger marker footprint and lower error are an association, not proof that
   its angle caused the improvement. The follow-up identifiability audit found
   camera-identity eta-squared values of 0.9997/0.9863/0.9984/0.9997 for
   distance/tilt/marker side/footprint, and the two camera ranges did not
   overlap for any of these variables.

## E7: conclusions supported only by simulation

At 0.5 px corner noise:

- For a planar target, per-frame Homography remained about 0.87 mm XY RMSE
  through the largest simulated camera motion; frozen Homography grew from
  1.21 to 68.54 mm.
- At 25 mm height, per-frame Homography remained about 35 mm. It corrected
  camera motion but could not correct the violated planar assumption.
- At 25 mm height, PnP with a frozen extrinsic grew from 6.84 to 40.61 mm,
  whereas relocalized PnP stayed between 6.62 and 6.85 mm and nearly matched
  the true-pose oracle.

Therefore, "moving-camera algorithm versus PnP" is the wrong distinction.
Moving-camera relocalization commonly uses PnP internally. The useful
distinction is **stale calibration versus current-frame relocalization**, then
**planar mapping versus 3-D pose estimation**.

## Novelty audit

The following components are established in prior work and cannot be claimed
as new algorithms by themselves:

- marker-based stereo triangulation and multi-camera tracking;
- multi-marker or multi-camera weighted fusion;
- PnP-based camera/marker relocalization;
- dependence of planar-marker pose uncertainty on distance and viewing angle.

What may be publishable is their controlled, deployment-oriented comparison in
one low-cost robotic manipulation chain, with explicit failure boundaries and
resource constraints. That is an **evaluation/methodology contribution**, not
a new pose-estimation algorithm.

## Recommended paper placement

- Keep E1-E4 as the physical baseline and task chain.
- Use E5 as supporting evidence about the resolution/reliability/latency
  envelope, not as a standalone novelty claim.
- Promote E6's "fusion versus parallax" result into the main experimental
  narrative, while explicitly stating its Z=0-derived geometry, static-target
  timing and lack of endpoint propagation.
- Keep E7 as supplementary simulation; do not wait for a physical moving-camera
  experiment and do not promote its numbers to Abstract/Contribution claims.
- Do not make a causal camera-angle claim from the present two placements.

## No-rebuild implementation

1. Freeze E5 as paired offline downsampling; use it for detection, stability,
   accuracy, latency and predefined feasibility gates, not native sensor-mode
   claims.
2. Freeze E6 as five-rebuild physical-data reuse; separate single-camera,
   estimate fusion and stereo triangulation in every figure and paragraph.
3. Use `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` as the only angle conclusion. The
   audit proves confounding/non-identifiability, not a preferred angle.
4. Keep E7 in the Supplement with `simulation only` labeling and an explicit
   list of omitted physical effects.
5. Run `paper_info/02_reproducibility/scripts/verify_no_rebuild_evidence.py`
   before migrating any E5–E7 number into the manuscript.

## Primary references used for this decision

- OpenCV `solvePnP`: https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html
- Adámek et al., marker pose variance versus geometry:
  https://doi.org/10.3390/s23125746
- Volden et al., monocular versus stereo marker localization:
  https://doi.org/10.1007/s41315-021-00193-0
- Popescu et al., multi-camera fiducial fusion:
  https://doi.org/10.3390/s20092746
- Oščádal et al., multi-tag 3-D placement and pose accuracy:
  https://doi.org/10.3390/s20174825
