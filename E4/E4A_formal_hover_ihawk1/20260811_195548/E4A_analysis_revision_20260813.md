# E4-A analysis revision — 2026-08-13

## Data correction

Three manual pointer X readings were corrected after the experimenter checked the original source evidence:

- `R1-T05-PnP_IPPE`: `-6.0 mm` → `-16.0 mm`.
- `R1-T05-Oracle`: `-7.5 mm` → `-17.5 mm`.
- `R2-T02-Homography`: `-17.5 mm` → `-12.5 mm`.

The endpoint and downstream error fields were recomputed from the corrected coordinates. Robot commands, T105 feedback, frozen predictions, and every other measurement remain unchanged. The machine-readable audit trail is in `E4A_measurement_corrections.json`.

## Corrected descriptive summary (all 44 acquired measurements)

| Method | n | Mean E2E error (mm) | RMSE (mm) | Median (mm) | Maximum (mm) |
|---|---:|---:|---:|---:|---:|
| Oracle | 11 | 1.226 | 1.462 | 1.118 | 2.500 |
| Affine | 11 | 3.213 | 3.519 | 3.041 | 5.831 |
| Homography | 11 | 2.249 | 2.714 | 1.803 | 4.610 |
| PnP_IPPE | 11 | 2.096 | 2.398 | 1.803 | 4.123 |

This all-row summary is descriptive only because T02 and T04 occur twice while the other targets occur once.

## Corrected primary summary (complete balanced repeat 1)

| Method | Targets | Mean E2E error (mm) | RMSE (mm) | Median (mm) | Maximum (mm) |
|---|---:|---:|---:|---:|---:|
| Oracle | 9 | 1.387 | 1.581 | 1.500 | 2.500 |
| Affine | 9 | 3.306 | 3.659 | 3.041 | 5.831 |
| Homography | 9 | 2.236 | 2.577 | 1.803 | 4.000 |
| PnP_IPPE | 9 | 2.065 | 2.375 | 1.803 | 4.123 |

Mean downstream residuals in the same complete block were 1.387 mm for Oracle, 1.659 mm for Affine, 1.332 mm for Homography, and 1.492 mm for PnP_IPPE.

## Revised interpretation

The previous interpretation that T05 contained an 8.5–10 mm downstream/robot failure is withdrawn. Those two extreme values came from confirmed manual X-scale reading errors.

After correction, Oracle provides a substantially lower end-to-end reference level (mean 1.387 mm in the complete balanced block). Homography and PnP_IPPE have similar end-to-end errors (2.236 and 2.065 mm) and both outperform Affine descriptively. Their downstream residuals remain around 1.3–1.5 mm, supporting the narrower conclusion that downstream registration, execution, and endpoint measurement become material once vision localization reaches approximately millimetre scale. The data do not show that all remaining error is intrinsic robot error, nor do they establish statistical equivalence between methods.

## Repeatability implication of the T02 correction

After correction, the two T02 Homography endpoints are `(-13.0, 35.5) mm` and `(-12.5, 36.0) mm`; their vector separation is 0.707 mm rather than 4.528 mm. The corrected second-repeat endpoint error is 4.610 mm relative to ground truth, while its downstream residual relative to the frozen Homography prediction is 1.158 mm. This removes the apparent repeatability failure but does not change the complete-repeat-1 primary analysis.

The T07 note mentioning `-43`/`-48` does not justify a correction: the saved `-43 mm` reading agrees with the frozen prediction, the T105-derived paper coordinate, and the adjacent method result. Other notes describe contact/settling or bounded pointer motion rather than an identifiable transcription error.
