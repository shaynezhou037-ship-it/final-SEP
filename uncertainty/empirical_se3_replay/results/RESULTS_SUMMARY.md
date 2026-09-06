# Empirical SE(3) component summary

## Coverage

- E0-A pixel groups: 10 (5 poses x 2 cameras; 50 samples each).
- E4 PnP groups: 4 (two acquisition stages per camera in one frozen physical setup).
- E2 PnP groups: 550 (2 cameras x 11 heights x 5 marker poses x 5 runs; 3 frames each).
- E2 run-bias vectors: 550; E4 temporal-stage bias vectors: 4.
- E2 hierarchical component rows: 88.

## Selected numerical checks

- E4 ihawk1 board PnP, stage=20260811_191758, n=20: sigma-rho mm = 0.2714/0.2367/0.3624, sigma-omega rad = 0.001066/0.002292/0.000442.
- E4 ihawk2 board PnP, stage=20260811_191758, n=20: sigma-rho mm = 0.0140/0.0808/0.0713, sigma-omega rad = 0.000410/0.000356/0.000227.
- E4 ihawk1 board PnP, stage=20260811_192958, n=20: sigma-rho mm = 0.2131/0.1776/0.1924, sigma-omega rad = 0.000940/0.001992/0.000584.
- E4 ihawk2 board PnP, stage=20260811_192958, n=20: sigma-rho mm = 0.0223/0.1928/0.1639, sigma-omega rad = 0.003002/0.001534/0.001281.

E2 within-group covariance diagnostics (RSS of the six marginal sigmas, summarized across 275 pose/height/run groups per camera):

- ihawk1: sigma-rho RSS median/P90/max = 0.290/1.293/36.040 mm; sigma-omega RSS = 0.00152/0.00715/1.36684 rad.
- ihawk2: sigma-rho RSS median/P90/max = 0.195/0.429/17.412 mm; sigma-omega RSS = 0.00097/0.00182/0.03239 rad.

E2 direct between-run bias magnitudes across pose/height conditions:

- ihawk1: |b_rho| median/P90/max = 4.357/8.822/31.436 mm; |b_omega| = 0.01539/0.38885/1.74935 rad.
- ihawk2: |b_rho| median/P90/max = 2.460/5.061/24.984 mm; |b_omega| = 0.01006/0.01800/0.05376 rad.

E4 calibration-to-held-out temporal-stage bias magnitude (two captures, not independent physical rebuilds):

- ihawk1: |b_rho| = 0.2575/0.2575 mm; |b_omega| = 0.010109/0.010109 rad.
- ihawk2: |b_rho| = 0.3676/0.3676 mm; |b_omega| = 0.001153/0.001153 rad.

For E2, the following are total covariance sums (within + between-run + cross-pose):

- ihawk1, h=0 mm: sigma-rho mm = 9.397/9.835/59.616, sigma-omega rad = 0.42618/0.26218/0.01244.
- ihawk1, h=5 mm: sigma-rho mm = 9.840/7.868/4.648, sigma-omega rad = 0.01041/0.01120/0.01515.
- ihawk1, h=10 mm: sigma-rho mm = 8.491/8.245/2.621, sigma-omega rad = 0.01211/0.00957/0.01704.
- ihawk1, h=15 mm: sigma-rho mm = 8.120/7.462/2.813, sigma-omega rad = 0.00841/0.01384/0.00886.
- ihawk1, h=20 mm: sigma-rho mm = 7.618/7.938/6.486, sigma-omega rad = 0.14604/0.16888/0.01427.
- ihawk1, h=25 mm: sigma-rho mm = 13.958/18.086/71.946, sigma-omega rad = 0.48319/0.36521/0.02448.
- ihawk1, h=30 mm: sigma-rho mm = 12.960/19.852/98.259, sigma-omega rad = 0.59221/0.45426/0.01390.
- ihawk1, h=35 mm: sigma-rho mm = 13.339/17.877/71.346, sigma-omega rad = 0.47636/0.33025/0.02145.
- ihawk1, h=40 mm: sigma-rho mm = 11.696/14.411/55.342, sigma-omega rad = 0.30573/0.20830/0.01944.
- ihawk1, h=45 mm: sigma-rho mm = 11.781/15.180/55.151, sigma-omega rad = 0.30851/0.20686/0.01462.
- ihawk1, h=50 mm: sigma-rho mm = 14.811/18.516/63.956, sigma-omega rad = 0.33282/0.22676/0.02176.
- ihawk2, h=0 mm: sigma-rho mm = 10.026/8.056/1.910, sigma-omega rad = 0.00845/0.01150/0.01040.
- ihawk2, h=5 mm: sigma-rho mm = 10.528/8.163/3.849, sigma-omega rad = 0.01503/0.01772/0.01525.
- ihawk2, h=10 mm: sigma-rho mm = 9.689/8.112/2.371, sigma-omega rad = 0.01484/0.01466/0.01024.
- ihawk2, h=15 mm: sigma-rho mm = 9.387/8.043/1.889, sigma-omega rad = 0.01601/0.01902/0.00684.
- ihawk2, h=20 mm: sigma-rho mm = 9.453/7.763/2.205, sigma-omega rad = 0.01584/0.01527/0.00573.
- ihawk2, h=25 mm: sigma-rho mm = 9.531/7.678/2.602, sigma-omega rad = 0.01825/0.01649/0.00469.
- ihawk2, h=30 mm: sigma-rho mm = 10.947/7.759/4.060, sigma-omega rad = 0.01614/0.01463/0.00725.
- ihawk2, h=35 mm: sigma-rho mm = 9.130/7.658/2.208, sigma-omega rad = 0.01904/0.01857/0.01177.
- ihawk2, h=40 mm: sigma-rho mm = 9.200/8.099/3.854, sigma-omega rad = 0.01689/0.02016/0.01215.
- ihawk2, h=45 mm: sigma-rho mm = 12.128/8.214/5.643, sigma-omega rad = 0.01705/0.01828/0.01766.
- ihawk2, h=50 mm: sigma-rho mm = 9.128/7.514/2.200, sigma-omega rad = 0.01903/0.01920/0.01914.

## Boundary

Every E2 group has n=3, so each unregularized 6-D within covariance has rank 2. Several ihawk1 groups contain large planar-PnP solution changes; they are retained in the empirical vector bank rather than clipped or Gaussianized.

E0-A has no recoverable 6-D pose observation, E4 has no repeated physical run, and the repository has no E1-v4 replay artifact or definition of `d_min,emp^cross`. No replacement E1 model was fitted.
