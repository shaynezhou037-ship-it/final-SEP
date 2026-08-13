# E0-B — Robot Feedback vs Physical Endpoint Consistency

## Purpose

This experiment checks whether the endpoint displacement physically observed
at the needle tip agrees with the Cartesian endpoint displacement reported
internally by the RoArm through T105 feedback.

This experiment is NOT used to estimate pure same-start robot repeatability.

---

## Dataset

- 20 total endpoint arrivals
- Trial 1 used as the physical/reference baseline
- 19 comparison arrivals
- Same frozen Cartesian target was commanded
- Different constrained high joint-space starting poses were present in the
  acquisition protocol
- Manual needle-paper measurement resolution was approximately 1 mm

The varied starting pose is recorded as an experimental condition only.
This dataset does not claim that starting configuration caused the endpoint
deviation.

---

## Observed coordinate correspondence

The data indicate approximately:

physical paper X ≈ + RoArm feedback ΔY

physical paper Y ≈ - RoArm feedback ΔX

physical paper Z ≈ + RoArm feedback ΔZ

The paper/robot axis correspondence should be treated as an observed mapping
unless independently verified geometrically.

---

## Main quantitative results

### Physical X vs mapped robot X

Pearson r = 0.9988

MAE = 1.170 mm

RMSE = 1.314 mm

Maximum absolute difference = 2.634 mm

### Physical Y vs mapped robot Y

Pearson r = 0.8039

MAE = 0.435 mm

RMSE = 0.508 mm

Maximum absolute difference = 1.141 mm

### Z

Independent physical Z displacement could not be reliably quantified with the
needle-paper setup.

No visually obvious Z displacement was observed.

RoArm T105 feedback showed Z variation of approximately 1.2 mm or less relative
to the baseline during the analysed trials.

Therefore no independent physical-Z correlation is claimed.

### XY displacement magnitude

Pearson r = 0.9641

MAE = 1.180 mm

RMSE = 1.325 mm

---

## Interpretation

The physically observed planar endpoint displacement agrees strongly with the
RoArm T105 endpoint-feedback displacement.

Therefore the large observed endpoint shifts were not simply caused by manual
needle-paper reading error.

T105 feedback can be used as a useful internal diagnostic of endpoint movement,
but it is not treated as independent ground truth.

The cause of the endpoint shifts is outside the scope of this experiment.
Possible robot-control, IK, path, configuration, backlash, or execution-layer
effects are not distinguished here.

---

## Files

raw/
    Original 20-arrival acquisition data

results/E0B_trialwise_physical_vs_T105.csv
    Trial-by-trial physical and T105 displacement comparison

results/E0B_physical_vs_T105_summary.json
    Correlation, MAE, RMSE and residual statistics

scripts/e0b_acquire_endpoint_observations.py
    Robot-motion and data-acquisition program used for this experiment

scripts/e0b_analyze_physical_vs_T105_feedback.py
    Post-processing program used to compare physical displacement with T105

