# E1-v4R1 REAL-zV attainability bridge

Status: `DIAGNOSTIC_COMPLETE_CORE_UNCHANGED`

Both archived iHawk intrinsic-calibration sets were recovered in full: 42/42
accepted overhead views and 48/48 accepted side views. Every image yielded all
48 checkerboard corners using the archived detector logic. The two camera
models were processed separately. Selection was frozen first from geometry
alone (payload SHA-256 `b060fe2cb8485b29c91f52da50eabc0dd7041c84c2a68234b374cf0cb584cc67`), before this
program imported or evaluated E1 metrics.

| Camera | post-nuisance smallest whitened/scaled sv | vs G0 | P-C | P-T | P-R | predeclared label |
|---|---:|---:|---:|---:|---:|---|
| camera_overhead_B242 | 0.926133 | 1.38e+07x | 3.67328 deg | 3.67415 deg | 3.77179 deg | strong real-geometry recovery |
| camera_side_B479 | 1.03693 | 1.55e+07x | 3.98869 deg | 3.98958 deg | 4.12988 deg | strong real-geometry recovery |

The synthetic references are G0 P-C/P-T 0.000179946/0.000135352
deg, G1 0.253596/0.257783
deg, and G2 0.734488/0.727598
deg. Historical 0.572/0.572/1.142 deg values were consulted only after both
real-view calculations were complete.

## Geometry-only attainability

The overhead archive spans depth 0.324-0.689 m
and tilt 10.21-63.24 deg.
The side archive spans depth 0.314-0.937 m
and tilt 4.22-66.62 deg.
Both archives therefore equal or exceed G1's *diversity pattern* in tilt and
image position, but they are not samples of G1's exact joint descriptor
envelope: the real boards are generally closer and occupy a larger image
footprint. For G2, 4 overhead and 2 side images lie inside the joint synthetic
descriptor envelope. The nine geometry-only selections retain simultaneous
depth, tilt, and image-position variation.

The synthetic G2 envelope extends beyond the overhead archive at its far-depth,
far-left, far-right, upper-image, and small-footprint extremes. Relative to the
side archive, its far-depth limit is slightly larger and its far-left,
upper-image, and smallest-footprint extremes are outside. Tilt is not the
limiting descriptor for either archive. Exact ranges, flags, visibility, and
border margins are in `real_vs_synthetic_geometry.csv`; all 90 real boards are
fully visible, with minimum margins 22.74 px (overhead) and 19.31 px (side).

## Interpretation and hard stop

Both cameras satisfy the predeclared strong-recovery screen independently.
Under the current frozen zV formula, the geometry-rescue mechanism is therefore
represented in the existing real low-cost camera archive; it is not purely a
synthetic artifact. This bridge changes target layout, real K/D, and feature
count along with physical view geometry, as required for the real checkerboard,
so it is an attainability result rather than a second controlled geometry-only
causality experiment. It does not mean the diagnosis or E1 restoration is
solved.

This artifact did not modify the E1 core, connect E2, calculate d_min, rerun the
restoration regression, run a phase map, or run perfect-zG. No GO, STOP, or
ONE-RESCUE decision is authorized here.
