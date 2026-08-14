# E6/E7 novelty decision note

Status: decision implemented in `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md` v2.4. The
author chose **no physical rebuild** on 2026-08-14.

## Decision

The submission is now organized around one geometric-information progression:
E1 establishes the planar anchor, E2 tests what happens when the target leaves
that plane, and E6 tests whether a second camera contributes merely another
biased estimate or genuinely new parallax information. E3 and E5 are
supporting validity checks, E4 is a limited application-side check, E0 has one
main-text limitation summary plus full Supplement diagnostics, and E7 is excluded from the submission package. E7 remains a
repository-only simulation for possible future work; its physical validation
is not a prerequisite for the current paper because the project will not be
rebuilt.

The promising paper direction is not "which model wins." It is:

> When a target leaves the calibration plane, which geometric information is
> sufficient for localization, and does a second camera help by adding another
> estimate or by adding parallax?

This is more focused and more defensible than reporting only
Affine/Homography/PnP accuracy rankings or several co-equal deployment factors.

## E6: conclusions supported by real E2 data

1. **Two estimates are not automatically more informative.** At 25 mm,
   equal PnP fusion was 6.057 mm XY RMSE, between ihawk1 (8.850 mm) and ihawk2
   (4.786 mm). Leave-one-rebuild-out weighting reached 4.897 mm and still did
   not beat the stronger camera.
2. **Estimate fusion and two-view geometry are different information flows.**
   In the strict same-output XYZ ablation at 25 mm, ihawk1/ihawk2/equal
   XYZ/LOO-weighted XYZ/stereo had 10.348/6.144/7.431/6.351/3.342 mm 3-D RMSE.
   Stereo was lower than ihawk2 in all five paired rebuilds at this height.
3. **The defensible claim is conditional, not universal.** At 50 mm, ihawk2
   and stereo had 6.002/4.897 mm mean 3-D RMSE, but stereo was lower in only
   4/5 paired rebuilds. A second camera is useful when its calibrated parallax
   supplies depth observability; the magnitude and rebuild consistency of that
   benefit still depend on the tested condition.
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

What may be publishable is the controlled geometric-information hierarchy in
one low-cost eye-to-hand system: planar mapping, single-view 3-D pose, two
single-view estimates, and calibrated stereo parallax. The paper's distinctive
finding is the separation of a second estimate from a second geometric view.
That is an **evaluation/methodology contribution**, not a new pose-estimation,
fusion, or stereo algorithm.

## Recommended paper placement

- Use E1 and E2 to answer the first research question: when a target leaves the
  calibration plane, which geometric information remains sufficient?
- Use E6 to answer the second research question: does a second camera add only
  another board-coordinate estimate or new two-view geometry? Explicitly state
  its Z=0-derived geometry, static-target timing, and lack of endpoint
  propagation.
- Use E3 and E5 only as supporting validity checks; neither receives a separate
  research question or contribution claim.
- Keep E4 as a limited application-side check, not the narrative climax and not
  validation of E6.
- Keep E0's full diagnostics in the Supplement while retaining its key
  measurement-chain limitation in the main text. Exclude E7 from the
  manuscript, Appendix, and Supplement; do not promote any E7 number.
- Do not make a causal camera-angle claim from the present two placements.

## No-rebuild implementation

1. Freeze E5 as paired offline downsampling; use it for detection, stability,
   accuracy, latency and predefined feasibility gates, not native sensor-mode
   claims.
2. Freeze E6 as five-rebuild physical-data reuse; separate single-camera,
   estimate fusion and stereo triangulation in every figure and paragraph.
   The core comparison must use common board XYZ outputs, XY/Z/3-D metrics and
   rebuild-level paired contrasts. `fusion + stereo` is not an independent
   information condition and is not required for this ablation.
3. Use `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` as the only angle conclusion. The
   audit proves confounding/non-identifiability, not a preferred angle.
4. Preserve E7 only as repository evidence for future work. It is not part of
   the current manuscript, Appendix, or Supplement.
5. Run `paper_info/02_reproducibility/scripts/verify_no_rebuild_evidence.py`
   before migrating any E5/E6 number into the manuscript. Verification of E7
   preserves repository integrity and does not authorize manuscript use.

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
