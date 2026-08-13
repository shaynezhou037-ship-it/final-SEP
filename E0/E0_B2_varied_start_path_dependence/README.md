# E0-B2 — Varied-start / Configuration-Path-Dependence Endpoint Test

## Classification

This dataset is **not** pure same-start robot repeatability.

Each comparison trial first moved the RoArm to a different constrained random
high joint configuration, then executed the same Yunkai Task10 three-waypoint
Cartesian approach to one frozen target.

Therefore the observed endpoint variation contains:

- robot execution repeatability;
- starting-configuration dependence;
- path/history dependence;
- possible IK/backlash/controller effects.

## Dataset

- 20 total endpoint arrivals
- Trial 1 = physical baseline
- Trials 2–20 = 19 varied-start comparisons
- Manual needle-paper practical resolution ≈ 1 mm
- Same frozen target used throughout the run

## Main result

18 of 19 comparison arrivals showed a manually resolvable displacement above
approximately 1 mm.

The displacement was strongly concentrated in the RoArm feedback Y direction.
Feedback X and Z remained much smaller.

The manual paper direction recorded as X tracked RoArm feedback Y extremely
closely. Therefore the paper-axis naming should be checked before later formal
experiments.

The random starting base-joint angle was also strongly associated with the
final feedback-Y displacement.

These relationships support a start-configuration/path-dependence hypothesis,
but do not by themselves prove the underlying physical mechanism.

## Do NOT report this as

"RoArm repeatability = 5–20 mm"

because the start configuration was deliberately changed.

## Correct interpretation

"Endpoint position showed substantial start-configuration/path dependence
when the same Cartesian target was approached from different constrained
random joint configurations."

## Next experiment

E0-B1 — Same-start robot repeatability:

official HOME
→ identical waypoint 1
→ identical waypoint 2
→ identical waypoint 3
→ measure endpoint
→ return to official HOME
→ repeat

No random starting configuration.
