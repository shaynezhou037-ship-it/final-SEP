# E2-v1R0 board-pose results

## Geometry decision

The printed geometry is confirmed as marker centres at `x=±70 mm`, `y=±113.5 mm`, with the centre marker at `(0,0)`.

- Correct geometry won in 330/330 paired raw frames.
- ihawk1 median reprojection RMSE: correct 0.579 px vs logged 1.863 px.
- ihawk2 median reprojection RMSE: correct 0.559 px vs logged 2.268 px.

The acquisition metadata/raw geometry fields at ±80/±123.5 mm are provenance-preserved but rejected for board normalization.

## Primary board measurement

- 330 board poses: 2 cameras × 5 runs × 11 heights × 3 frames; every pose uses all 20 marker corners.
- Board-level selected-branch switches: 0/110 groups.
- Single-marker selected-branch switches: 12/550 groups; large >0.25 rad mode jumps: 12/550. None were clipped.

Pooled `Sigma_within` examples (rho sigma mm / omega sigma rad):

- ihawk1, h=0: 0.2350/0.2182/0.2233 mm; 0.000311/0.000395/0.000125 rad.
- ihawk1, h=25: 0.2675/0.5443/0.3896 mm; 0.002086/0.001779/0.001458 rad.
- ihawk1, h=50: 0.4036/0.4721/0.3805 mm; 0.001188/0.000502/0.001414 rad.
- ihawk2, h=0: 0.0230/0.0054/0.0200 mm; 0.000092/0.000101/0.000086 rad.
- ihawk2, h=25: 0.0203/0.0032/0.0177 mm; 0.000095/0.000075/0.000082 rad.
- ihawk2, h=50: 0.0313/0.0095/0.0221 mm; 0.000079/0.000106/0.000072 rad.

## Replay semantics

`Sigma_within`, `b_pose`, and `b_run` are separate. `b_run` is an empirical bank, not a fitted Gaussian. No `total_sum` is generated. E1-v4 replay remains blocked until the original executable metric artifact is recovered; this analysis does not redefine it.
