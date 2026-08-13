# E0-B — Robot Endpoint Deviation / Physical–Feedback Cross-check

## What this dataset directly contains

This run contains 20 endpoint arrivals to the same frozen Cartesian target.

The acquisition protocol included different constrained high joint-space
starting poses. That is recorded as a protocol condition only. This archive
does **not** assign the observed endpoint deviations to a specific cause.

## Primary question for this re-analysis

Do the physically observed needle-paper endpoint displacements agree with the
RoArm T105 endpoint-feedback displacements?

## Candidate observed axis correspondence

- physical/paper X ≈ + robot feedback ΔY
- physical/paper Y ≈ - robot feedback ΔX
- physical/paper Z ≈ + robot feedback ΔZ

This correspondence should be physically checked before it is treated as a
formal coordinate-frame definition.

## Main analysis outputs

See:

- `results/E0B_endpoint_physical_vs_feedback_trials.csv`
- `results/E0B_endpoint_physical_vs_feedback_summary.json`

Continuous correlation/error statistics exclude the Trial-1 baseline and rows
whose physical displacement was only classified as below the ~1 mm manual
measurement resolution.

No causal interpretation is imposed by this archive.
