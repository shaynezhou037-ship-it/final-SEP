# 阶段 2 新颖性缺口审计

日期：2026-08-13  
范围：第一轮正式检索；结论只适用于已筛选语料，不构成系统综述或穷尽性检索。

## 检索问题

1. 是否已有论文把 robot/camera calibration 的误差直接评价到 end-effector endpoint？
2. 是否已有论文明确使用 `end-to-end` robot calibration？
3. 是否已有低成本外部相机方案评价 robot positioning accuracy/repeatability？
4. 是否已有同一 fixed-camera observations/ground truth 下的 Affine、Homography、PnP 三模型比较，并同时覆盖 planar、off-plane、calibration coverage 和 robot endpoint？

检索主题组合包括：`robot camera calibration endpoint positioning error`、`eye-to-hand error propagation`、`end-to-end robot calibration`、`photogrammetric robot positioning accuracy repeatability`、`Affine Homography PnP comparison robot positioning`、`control point configuration photogrammetry accuracy`。优先核验 DOI、出版社/作者全文和官方标准页。

## 找到的最接近工作

| 工作 | 与本项目重叠 | 对新颖性的限制 |
|---|---|---|
| Zhong et al., T-RO 2023 | robot--camera calibration；3-D endpoint error；网格/微调平台；旋转误差传播 | 不能把 endpoint validation 或 error propagation 本身写成新贡献 |
| Ulrich et al., ISPRS JPRS 2024 | 明确 `end to end` calibration；整合 robot kinematics、hand--eye、camera intrinsics；application metric | 不能声称首次端到端校准；必须区分 calibration 与 evaluation chain |
| Chajón et al., Robotics 2026 | 低成本外部相机；planar accuracy/repeatability；测量链限制 | 不能把低成本相机外部 robot characterization 本身写成新贡献 |
| Enebuse et al., PLOS ONE 2022 | 六算法共享仿真/真实数据比较；噪声和运动范围条件效应 | 不能笼统声称“首次说明算法选择依赖几何/采集条件” |
| Acuna & Willert 2018 preprint + Challis & Kerwin 1992 | control-point distribution/conditioning 与精度 | 不能把“空间覆盖重要”写成首次发现；只能把 E3 写成 B2 tested workspace 的定量验证 |

## 当前可守的新颖性

第一轮没有发现一篇工作同时包含以下组合：

- 低成本 fixed-camera eye-to-hand setup；
- 共享图像观测、calibration/validation split 和 workspace ground truth；
- Affine、Homography、PnP 三个 mapping pipelines；
- held-out planar localization、off-plane height scan、calibration-point coverage resampling；
- 一个透明标注为 exploratory 的 robot endpoint block；
- 对 physical rebuild、video frames、offline resamples 和人工修订的统计边界审计。

因此当前贡献应写成 **a unified, geometry-conditioned, auditable multilevel evaluation protocol and dataset-specific evidence**，而不是新算法，也不是 `the first end-to-end calibration`。

## 禁止从本轮检索推出的句子

- `No prior work has compared these models.`
- `This is the first end-to-end robot calibration study.`
- `This is the first low-cost camera-based robot accuracy evaluation.`
- `Calibration-point distribution has not been studied before.`

允许的限定版本：

> In the literature screened for this study, we did not identify an evaluation that combines the same three mapping pipelines with shared held-out planar truth, off-plane scans, calibration-coverage resampling, and an exploratory robot-endpoint block.

该句在投稿前必须重新检索，并在目标 venue 冻结后加入其近五年论文范围。
