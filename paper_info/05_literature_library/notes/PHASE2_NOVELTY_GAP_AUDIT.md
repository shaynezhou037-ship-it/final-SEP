# 阶段 2 新颖性缺口审计

日期：2026-08-14
范围：第一轮 end-to-end/measurement 检索，加上 no-rebuild 决策后的第二轮 resolution/multi-camera/view-geometry 检索；结论只适用于已筛选语料，不构成系统综述或穷尽性检索。

## 检索问题

1. 是否已有论文把 robot/camera calibration 的误差直接评价到 end-effector endpoint？
2. 是否已有论文明确使用 `end-to-end` robot calibration？
3. 是否已有低成本外部相机方案评价 robot positioning accuracy/repeatability？
4. 是否已有同一 fixed-camera observations/ground truth 下的 Affine、Homography、PnP 三模型比较，并同时覆盖 planar、off-plane、calibration coverage 和 robot endpoint？
5. marker-based monocular/stereo localization 和 multi-camera fiducial fusion 是否已有明确先例？
6. 平面 marker 的姿态误差/方差随距离、像素 footprint 和 viewing angle 变化是否已有明确先例？
7. 在同一低成本 robot-positioning 数据中，是否已有工作明确区分 estimate-level averaging 与 parallax-based triangulation，并联合 calibration coverage、effective resolution 和 endpoint evidence？

检索主题组合包括：`robot camera calibration endpoint positioning error`、`eye-to-hand error propagation`、`end-to-end robot calibration`、`photogrammetric robot positioning accuracy repeatability`、`Affine Homography PnP comparison robot positioning`、`control point configuration photogrammetry accuracy`、`monocular stereo fiducial marker localization`、`multi-camera fiducial fusion`、`planar marker pose variance distance viewing angle`。优先核验 DOI、出版社/作者全文和官方标准页。

## 找到的最接近工作

| 工作 | 与本项目重叠 | 对新颖性的限制 |
|---|---|---|
| Zhong et al., T-RO 2023 | robot--camera calibration；3-D endpoint error；网格/微调平台；旋转误差传播 | 不能把 endpoint validation 或 error propagation 本身写成新贡献 |
| Ulrich et al., ISPRS JPRS 2024 | 明确 `end to end` calibration；整合 robot kinematics、hand--eye、camera intrinsics；application metric | 不能声称首次端到端校准；必须区分 calibration 与 evaluation chain |
| Chajón et al., Robotics 2026 | 低成本外部相机；planar accuracy/repeatability；测量链限制 | 不能把低成本相机外部 robot characterization 本身写成新贡献 |
| Enebuse et al., PLOS ONE 2022 | 六算法共享仿真/真实数据比较；噪声和运动范围条件效应 | 不能笼统声称“首次说明算法选择依赖几何/采集条件” |
| Acuna & Willert 2018 preprint + Challis & Kerwin 1992 | control-point distribution/conditioning 与精度 | 不能把“空间覆盖重要”写成首次发现；只能把 E3 写成 B2 tested workspace 的定量验证 |
| [Volden et al. 2022](https://doi.org/10.1007/s41315-021-00193-0) | 低成本 marker-based monocular/stereo 定位；triangulation；实场外部参考 | 不能把单/双相机或 marker stereo comparison 本身写成新贡献 |
| [Popescu et al. 2020](https://doi.org/10.3390/s20092746) | 多相机 fiducial position fusion；adaptive Kalman；Monte Carlo | 不能把多相机加权融合或“多相机提升精度”的一般目标写成首次提出 |
| [Adámek et al. 2023](https://doi.org/10.3390/s23125746) | 平面 fiducial pose variance 与角度、距离/像素面积的关系 | 不能把 view geometry 影响 marker pose 写成新发现；E6 当前也不能识别因果 angle effect |

## 当前可守的新颖性

第一轮没有发现一篇工作同时包含以下组合：

- 低成本 fixed-camera eye-to-hand setup；
- 共享图像观测、calibration/validation split 和 workspace ground truth；
- Affine、Homography、PnP 三个 mapping pipelines；
- held-out planar localization、off-plane height scan、calibration-point coverage resampling 和 simulated effective-resolution failure/latency envelope；
- 在相同 paired physical observations 上明确区分 single-camera estimate、estimate-level fusion 与 calibrated stereo parallax；
- 一个透明标注为 exploratory 的 robot endpoint block；
- 对 physical rebuild、video frames、offline resamples、simulation trials、角度混杂和人工修订的统计边界审计。

因此当前贡献应写成 **an information- and geometry-conditioned, auditable operating-envelope evaluation using shared low-cost physical observations**。E6 最有区分度的项目级结论是：**two camera-specific estimates are not equivalent to two-view geometric information**；简单/加权平均保留系统偏置，而 calibrated parallax 可增加 depth constraint。它仍是 evaluation finding，不是新 fusion 或 stereo algorithm。

E5 不能单独承担创新性：其核心结论是当前分析机上的 native 640 × 400 已满足 30 Hz gate，降低分辨率的速度收益不抵检测/accuracy 损失。E7 也不能承担物理系统创新性：它只用 simulation 支持 stale calibration versus per-frame relocalization 的机制解释。

## 相机角度的可识别性结论

E6 只有两个固定 camera placements，各自在五次 rebuild 中重复。新增审计显示，camera identity 对 distance、tilt、marker side 和 marker footprint 的 eta² 分别为 0.9997、0.9863、0.9984、0.9997，且两相机在四个变量上的范围全部不重叠。由此可得的是“angle effect cannot be isolated from the present design”，而不是“某角度更准确”。现有 pooled angle/error correlation 只能作为混杂诊断，不进入因果贡献。

## 禁止从本轮检索推出的句子

- `No prior work has compared these models.`
- `This is the first end-to-end robot calibration study.`
- `This is the first low-cost camera-based robot accuracy evaluation.`
- `Calibration-point distribution has not been studied before.`
- `This is the first monocular-versus-stereo marker comparison.`
- `Two cameras are inherently more accurate than one.`
- `The viewing angle caused the observed camera difference.`
- `The moving-camera method was experimentally validated.`

允许的限定版本：

> In the literature screened for this study, we did not identify an evaluation that combines the same three mapping pipelines and paired single-/dual-view information flows with shared held-out planar truth, off-plane scans, calibration-coverage resampling, simulated effective-resolution limits, and an exploratory robot-endpoint block.

该句在投稿前必须重新检索，并在目标 venue 冻结后加入其近五年论文范围。

## 引用库迁移状态

Volden 2022、Popescu 2020 和 Adámek 2023 已完成 DOI/出版社全文级核验并用于本轮边界判断。由于本会话的专用表格工作区组件不可用，`citation_sentence_ledger.csv`、`literature_screening_log.csv` 和 `references.bib` 尚未同步；待组件恢复后必须一次性迁移并核对作者、卷期页码，正文在此之前不直接调用新的 cite key。
