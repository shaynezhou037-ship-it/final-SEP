# Phase 1 Paper Blueprint v2 — IEEE Red-Team Revision

版本：v2.2（在原文件内更新，避免版本膨胀）
日期：2026-08-14
默认正文语言：English  
当前定位：IEEE journal-style experimental study  
状态：作者已决定不重新搭建物理系统；E5/E6 离线扩展、E6 角度可识别性审计与 E7 仿真边界已写回；E6 进入主文，E5 为主文支撑证据，E7 仅进入 Supplement；本文件仍是当前唯一蓝图

## 1. 论文定位

本文保留受限的 end-to-end 机器人定位链作为下游收束，但主问题从“哪种模型最好”调整为：在同一低成本 eye-to-hand 系统、共享观测和真值下，任务几何、标定覆盖、有效分辨率和单/双视图信息流如何共同限定各定位管线的可用范围。本文不提出新的 Affine、Homography、PnP、加权融合或立体三角测量算法；原创性定位为受控、可审计的条件化评价与信息流比较，而不是新算法。

本文中的 **end-to-end** 仅指 E4 已实测的：图像观测/目标定位 → board 坐标映射 → board-to-robot registration → 机器人指令与执行 → 人工观测端点。它不包括任意物体检测、抓取规划、接触动力学、抓取成功率或连续闭环控制。E6 的双相机融合/立体结果是与 E4 并列的 vision-level 离线分支，没有传播到机器人端点；标题、摘要、图注和结论中的每一次 `end-to-end` 都必须符合该边界。

阶段 2 文献边界：Ulrich et al. (ISPRS JPRS 2024) 已使用 `end to end` 描述 robot kinematics、hand--eye 和 camera intrinsics 的同步校准；Zhong et al. (T-RO 2023) 已将 robot--camera calibration 评价到三维末端定位误差；Volden et al. (2022) 已比较 marker-based monocular/stereo 定位；Popescu et al. (2020) 已研究多相机 fiducial fusion；Adámek et al. (2023) 已分析平面标记姿态方差与距离/视角的关系。因此本文不主张首次 end-to-end、首次双相机融合、首次 stereo marker localization 或首次角度效应。可守贡献是把 planar/off-plane、coverage、effective resolution、estimate fusion、stereo parallax 和 exploratory endpoint evidence 放入同一套共享物理数据与明确统计边界的部署条件评价协议。

### 推荐英文题目

**Information- and Geometry-Conditioned Operating Envelopes for Low-Cost Vision-to-Robot Positioning**

### 文献审计通过后可选的题目

**When Does a Second View Add Information? A Deployment-Oriented Evaluation of Low-Cost Eye-to-Hand Positioning**

暂不使用 `When Is Full 3D Calibration Necessary?`：当前没有预先定义的任务容差，且 PnP 不等同于完整 hand–eye/3-D calibration。

### 一句话主张

> In a tested low-cost eye-to-hand system, shared physical observations show that planar/off-plane geometry, calibration coverage, effective resolution, and the way a second view is used—not model complexity or camera count alone—determine the usable positioning pipeline, while a completed exploratory block shows that vision-level gains do not transfer one-to-one to the robot endpoint.

## 2. 研究问题

### RQ1 — Planar accuracy

在同一平面观测、相同标定点、相同 held-out 空间位置和相同真值下，Affine、Homography 和 PnP 的 XY 定位误差如何？

预期回答：在 ihawk1 和当前板/工作区中，Homography 与 PnP 的 RMSE 为 0.660/0.661 mm，均低于全局 Affine 的 4.854 mm。36 个观测单位是 held-out spatial locations，不是 36 次独立物理重装；“相近”是描述性结论，不是统计等效。

### RQ2 — Off-plane robustness

目标离开 Z=0 标定平面时，三种模型的绝对误差和高度退化趋势如何随相机与 rebuild 改变？

预期回答：二维映射随高度明显退化，PnP 在两个相机和五个 physical rebuild 中对高度更稳健，但存在相机相关的绝对偏差。核心结论是 robustness，不是“PnP 在所有高度绝对最准确”。

### RQ3 — Calibration and effective-resolution constraints

在当前候选点和固定验证集上，标定点数量/空间覆盖如何影响拟合稳定性；在同一批 640 × 400 保存图像的离线降采样中，有效分辨率如何影响标记检测、定位稳定性、XY 误差和处理时延？

预期回答：tested dataset 中，spread configurations 明显优于 minimal clustered configurations；12 到 24 个 spread 点之间的额外收益较小。保存图像的基准 640 × 400 对两相机均实现完整检测，最坏 pipeline P95 为 8.149 ms；480 × 300 的完整五标记图像率降至 ihawk1 78.4%、ihawk2 98.8%，且 ihawk2 PnP 在 25 mm 的 mean XY RMSE 从 4.786 mm 增至 12.808 mm。现有计算机上降分辨率不是满足 30 Hz 的必要条件。E3 的 100 subsets/condition 与 E5 的多分辨率图像均为离线变换，不是独立物理实验。

### RQ4 — Single- versus dual-view information flow

在相同静态目标、配对观测与五次 physical rebuild 下，第二台相机通过结果平均、留一重建加权与真正的 stereo parallax 使用时，分别带来什么信息？现有两种视图能否支持相机角度的因果结论？

预期回答：25 mm 高度下，PnP 的 ihawk1/ihawk2/equal/LOO-weighted XY RMSE 为 8.850/4.786/6.057/4.897 mm；简单或加权结果融合都未优于较强的 ihawk2。Stereo triangulation 的 XY/Z RMSE 为 2.752/1.772 mm，说明结果平均与双目几何是不同的信息流。角度不可识别性审计显示，10 个 run-camera rows 实际来自两个固定布局；相机身份解释了倾角变化的 98.63%，且距离、倾角、marker footprint 的两相机范围均不重叠，因此只能报告描述性布局差异，不能声称角度导致误差变化。

### RQ5 — End-to-end endpoint transfer（exploratory validation block）

在一个冻结视觉预测、固定起点与路径的有限机器人实验中，视觉误差差异如何体现在端点误差中？

预期回答：完整 balanced block 的 Oracle/Affine/Homography/PnP mean E2E 分别为 1.387/3.306/2.236/2.065 mm。该结果只说明本次 completed block 中存在 material downstream residual；不将 Oracle 解释为纯机器人误差或稳定误差地板。

## 3. 主要贡献

### C1 — 可审计的 end-to-end 误差链

在共享 undistorted observations、ground truth、calibration/validation split 和统计边界的条件下比较三个 mapping pipelines，并把评价从平面定位、离平面退化和标定覆盖一直连接到机器人端点；同时公开数据冻结、失败、提前停止和人工修订规则。

### C2 — Geometry- and resource-conditioned operating behavior

用平面 held-out locations 与两相机、五次 independent physical rebuild、0–50 mm 扫描区分 in-plane accuracy、off-plane degradation 和 absolute bias，并用有效分辨率、检测完整率和处理时延补充部署约束，显示模型复杂度与降采样的收益依赖任务几何和观测可靠性。

### C3 — Information-flow distinction for one versus two views

在相同 E2 物理观测上区分 single-camera prediction、estimate-level averaging/LOO weighting 与 calibrated stereo triangulation。核心新增证据是“第二台相机是否有用取决于如何使用其信息”：融合偏置估计不自动改善较强相机，而 parallax 可提供额外深度约束。该贡献是评价结论，不把已有融合或 triangulation 算法包装为新方法。

### C4 — Calibration design sensitivity and downstream error transfer

量化 tested workspace 中空间覆盖、点数和数值退化的关系，并用 completed exploratory E4 block 说明 vision benchmark 的改进不必然一比一传递为 endpoint 改进。E4 是全文的叙事终点和下游有效性检查，但不是完成 108 次重复的确认性验证。

## 4. 实验角色与统计单位

| 实验 | 正文角色 | 正确统计/观察单位 | 不能写成 |
|---|---|---|---|
| E0-A | 静态测量噪声量级 | camera-position 下的短期 frame sequence | 500 次独立实验；完整 uncertainty budget |
| E0-B/B2 | 执行协议诊断 | 一个或有限 target 下的 arrivals | 纯 robot repeatability；backlash/IK 因果证明 |
| E1 | RQ1 主数据 | 36 个同一板上的 held-out spatial locations | 36 次独立部署；1800 个独立样本 |
| E2 | 全文主轴 | 每相机五次 physical rebuild；三帧先平均 | 三帧 = 三个独立重复；Z=0 = held-out test |
| E3 | RQ3 标定敏感性 | 同一物理观测集上的 offline subsets | 每条件 100 次物理重标定 |
| E4 | end-to-end endpoint case study | repeat 1 的 9 个 paired targets；repeat 2 仅 2 targets | 108 条已完成；确认性机器人验证；完整 manipulation success study |
| E5 | RQ3 分辨率/时延支撑证据 | E2 保存图像的 paired downsampling；准确度仍按 physical rebuild 汇总 | 原生传感器模式实验；分辨率层级是独立部署 |
| E6 | RQ4 单/双视图主数据 | 五次 rebuild 下的静态配对观测；三帧先平均 | 双相机已贯通 E4；动态同步验证；独立 metrology ground truth |
| E7 | Supplement 仿真机制检查 | 10 nominal poses × Monte Carlo perturbations | 真实移动相机实验；独立物理重复；主文中心证据 |

### E0 边界

正文仅用一段或 Table II 中的量级摘要说明：短期相机随机波动不足以解释 E2 的数十毫米高度误差；固定起点与路径是 E4 的必要控制。完整位置表、axis mapping 和诊断进入 Supplement。

### E1 边界

三种方法使用相同 12 calibration points、36 held-out locations、50 accepted frames 和 board XY truth。主指标为每个位置的 median-observation prediction error；frame-wise 结果只描述定位波动敏感性。

### E2 边界

每次 rebuild 对每台相机只用自身 Z=0 数据标定并冻结模型，再应用到 Z=5–50 mm。正文必须说明“physical rebuild”的实际操作定义，并给出每个 rebuild 的 paired trace。

50 mm headline：

- ihawk1 Affine/Homography/PnP：69.63/81.97/10.63 mm；
- ihawk2 Affine/Homography/PnP：56.43/64.26/4.54 mm。

同时必须披露 Z=0 的 PnP XY RMSE 为 ihawk1 7.72 mm、ihawk2 3.21 mm；因此 PnP 的优势主要是 off-plane robustness，而不是所有条件下的最低 absolute error。

### E3 边界

4-point spread 的 Homography/PnP median RMSE 为 0.955/0.731 mm；4-point clustered 为 243.696/1.736 mm，PnP fitting failure 为 3%。12-point spread 为 0.584/0.597 mm，24-point spread 为 0.562/0.581 mm。

主文用“coverage mattered strongly in the tested candidate set”；“12–16 points”仅作为 Discussion 中的 dataset-specific observation，并由 Supplement 给出全部 54 conditions 与生成规则。

### E4 边界

主分析仅使用完整 repeat 1：9 targets × 4 methods = 36 trials。实际总采集 44/计划 108，repeat 2 的 T02/T04 共 8 条只用于有限短期重复性描述。

Oracle/Affine/Homography/PnP 的 mean E2E 为 1.387/3.306/2.236/2.065 mm；RMSE 为 1.581/3.659/2.577/2.375 mm。由于 Oracle 同时包含 registration、controller、mechanics、tool alignment 与人工网格读数，统一称 `observed Oracle reference in the completed block`。

board-to-robot registration 的训练 XY RMSE 为 3.327 mm，两个 2-point held-out batches 分别出现 5/14.142 mm 与 5/12.806 mm。这些检查太小且误差较大，必须进入 Supplement/Limitations；它们阻止我们把 1.387 mm 写成稳定 downstream floor。

文献对 E4 的额外约束：Zhong et al. 使用 XYZ microtrimming platform 和 checkerboard reference 对 3-D endpoint error 做外部测量；Chajón et al. 使用 30 repetitions × 5 poses，并以百分表提供机器人重复性的独立参考。相比之下，本项目是人工网格读数、one completed 9-target block，且没有独立计量设备。因此 E4 只能支持 model-conditioned endpoint observations，不能支持 ISO-style robot accuracy/repeatability 或对 robot-only 与 measurement-chain error 的严格分离。

### E5 边界

E5 只把 E2 的 lossless 640 × 400 保存图像按 area interpolation 离线降采样到 480 × 300、320 × 200、240 × 150 和 160 × 100，并同步缩放 camera matrix。它回答 effective spatial resolution，而不是传感器原生模式；曝光、光学、read noise、ISP 和 sensor frame rate 均未改变。Accuracy 只在完整检测五个 marker 的 run-height 条件上计算，必须与 detection/coverage 一起报告，防止 survivorship bias。时延只含分析计算机上的处理时间，不含磁盘 I/O、采集和机器人控制环。

E5 对主文最重要的结果是负面的部署结论：保存图像的基准 640 × 400 pipeline 已经通过预定义 30 Hz gate，降采样虽更快但显著损害检测完整率，并对 PnP 造成 camera-dependent accuracy cost；没有观察到跨相机/模型一致的 resolution × height 放大规律。因此 E5 是 RQ3 的工程约束证据，不单独承担论文创新性。

### E6 边界

E6 必须把三种信息流分开写：single-camera estimate；将两个 camera-specific board estimates 做 equal/LOO-weighted fusion；利用两视图投影矩阵与 parallax 做 stereo triangulation。只有第三种直接增加几何深度信息。所有 pairing 来自静态目标；pair delta median/P95/max 为 18.267/46.519/49.217 ms，不能外推到动态场景。Stereo 的投影矩阵由同一 E2 Z=0 数据导出，不是独立计量参考，也没有进入 E4 endpoint chain。

角度处理只允许使用 `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` 的结论：10 个 rows 是两种固定布局在五次 rebuild 中的重复，不是 10 个 angle levels。Camera identity 对 distance、tilt、marker side 与 footprint 的 eta² 为 0.9997/0.9863/0.9984/0.9997，四个变量的两相机范围全部不重叠。该结果证明当前设计的混杂程度，不证明任一角度更好。

### E7 边界

E7 是 deterministic Monte Carlo simulation。它可说明“moving camera algorithm 与 PnP 并非对立；关键是 stale calibration 与 current-frame relocalization 的区别”，但没有模拟 detector failures、motion blur、occlusion、vibration、rolling shutter、真实同步或机器人 endpoint。正文最多在 Discussion 用一句机制解释并指向 Supplement；Abstract、贡献列表和 Conclusion 不得把 E7 写成真实系统验证。

## 5. 正文论证顺序

1. 定义系统、坐标链、三种 mapping pipelines 与公平比较原则。
2. E1 建立平面 held-out baseline。
3. E2 作为核心展示模型 × height × camera/rebuild 的条件依赖。
4. E3 与 E5 回答部署约束：先说明 calibration coverage，再说明 effective resolution、detection、accuracy 与 latency；E5 的 negative result 明确写成“当前设备上无需为 30 Hz 降采样”。
5. E6 作为新的主文证据区分 single view、estimate fusion 与 stereo parallax，并紧接一个 angle-identifiability limitation panel/段落。
6. E4 用一个完整结果小节和一张主图收束全文，展示限定边界下的 end-to-end endpoint transfer；篇幅地位可以突出，但证据强度仍标为 exploratory。
7. E0 作为方法合理性/限制背景穿插；E7 仅在 Discussion/Supplement 说明 moving-camera relocalization 机制，两者都不形成与 E1–E6 等长的主结果章节。
8. Discussion 给出 tested conditions 下的信息充分性/可用范围，不给普适模型排名、角度建议或未经定义的“必要高度”。

## 6. 统计分析计划

- 所有表格同时给出 metric、统计单位、physical n、offline n 和缺失/失败数。
- E1：target-wise paired error distribution 与 effect sizes；不把 frames 作为独立推断样本。
- E2：每个 rebuild 的曲线必须可见；报告跨 rebuild 的中心、离散性和区间。若阶段 3 进行正式模型检验，必须保留 method/height 的配对和 rebuild/target 层级。
- E3：使用 median、IQR/quantiles、failure rate 和 extreme-error panel，避免退化条件被均值掩盖。
- E5：按 resolution × camera 同时报告 marker detection、complete-five-marker frame rate、center/corner stability、accuracy available n 和 latency median/P95；准确度以 physical rebuild 为单位，降采样层级是 paired transformation。预定义 feasibility profiles 是 engineering screening constraints，不称工业标准。
- E6：融合/triangulation 准确度以 physical rebuild 为单位；LOO-weighted 参数只从其余四个 rebuild 学习。`LOOWeightedGated` 的 conditional error 必须与 coverage 同报。角度只报告 setup descriptives、camera-identity eta² 和不可识别性，不给 pooled-correlation p-value 或多变量因果回归。
- E4：只做 paired descriptive comparison 与透明 effect sizes，不做利用未完成重复的确认性 p-values。
- E7：Monte Carlo trial 只是不确定扰动抽样；不得作为 physical n。所有仿真图/表必须标 `simulation only`。
- 不为增强显著性而把离线 resamples、frames 或 spatial locations 当成 physical replicates。

## 7. 正文图表

### Figures

1. **System, information flows, and evidence map.** 系统照片/示意、坐标系、single-view mapping、estimate fusion、stereo parallax 与 E4 image-to-endpoint 链。实线表示 physical evidence，点划线表示 offline transformation，虚线表示 simulation/unvalidated endpoint branch；明确 E6 未进入 E4。
2. **Planar held-out performance.** E1 的 target-wise paired errors；caption 明确 36 spatial locations。
3. **Height-dependent robustness.** 双相机 panels，显示每个 rebuild trace 与跨 rebuild summary；这是主图。
4. **Calibration and effective-resolution constraints.** E3 的 count × distribution × model 与 E5 的 detection/latency/accuracy operating envelope 组成两个明确标记的 panels；不能用 E5 的 offline resolution levels 充当 physical n。
5. **What the second view adds.** E6 的 single-camera/equal/LOO-weighted PnP 与 stereo XY/Z 结果；配一个小型 angle-identifiability panel，只展示两固定布局和混杂边界。
6. **Exploratory end-to-end endpoint transfer.** E4 repeat-1 paired target plot + vision/downstream/E2E 分解；标题/caption 写明 9 targets、one completed block、manual endpoint reading 和 early stop。

E0 静态结果优先压缩进 Table II 或 Supplement，不强制单独占用一张主图。

### Tables

1. **Hardware, targets, coordinates, and acquisition protocol.** 明确 50 mm ArUco、25 mm chessboard square 及其他板定义，避免标记尺寸混用。
2. **Experimental design and statistical units.** E0–E7 的 physical/offline/simulation units、主指标与限制。
3. **Headline quantitative results.** E1、E2、E5、E6 与 exploratory E4 的核心数字；不把不同独立性层级混成一个 n。
4. **Conditioned deployment decisions.** 以 tested evidence 给出 planar/off-plane、resolution、one/two views 与 endpoint status；每格同时列所需输入、accuracy/reliability evidence 和不可外推边界，不构造普适 winner。

## 8. 章节结构

1. Abstract
2. Index Terms
3. I. Introduction
4. II. Related Work
5. III. System and End-to-End Evaluation Protocol
6. IV. Results
7. V. Discussion and Limitations
8. VI. Conclusion
9. Appendix（仅在目标 venue 和内容确有需要时）
10. Acknowledgment（含实际 AI 使用披露）
11. References
12. Separate Supplementary Material

具体页数和各节长度在目标 IEEE venue 确定后按官方模板冻结。目前不使用 V1 的固定 7,000–8,000 words 作为硬指标。

## 9. Appendix 与 Supplementary Material

### 正文 Appendix

默认不设。只有一个无法在 Methods 简洁表达、又对主文证明不可缺少的推导/定义时才增加。它不能用于隐藏关键实验方法，也不能绕过目标 venue 的页数限制。

### Separate Supplementary Material（需要）

- S1 hardware/targets/coordinate conventions；
- S2 experimental units, inclusion rules, frozen IDs；
- S3 E0 full diagnostics；
- S4 E1 target-wise and frame-level results；
- S5 E2 rebuild × camera × height × model results；
- S6 E3 subset construction, 54 conditions, seeds, failures；
- S7 E4 all 44 rows, early stopping, partial repeat, correction audit；
- S8 board-to-robot registration training/held-out audit；
- S9 E5 effective-resolution detection/stability/accuracy/latency and feasibility gates；
- S10 E6 fusion weights, gated coverage, stereo XYZ, pair timing and angle-identifiability audit；
- S11 E7 simulation design/results with `simulation only` watermark and omitted-effect list；
- S12 reproducibility README, code/data inventory, software versions and `no_rebuild_evidence_manifest.json`。

## 10. 禁止与限定表述

禁止：

- `PnP is universally the most accurate method.`
- `Full 3D calibration becomes necessary above X mm.`（除非先定义应用容差并完成对应分析）
- `Homography and PnP are statistically equivalent.`
- `The robot error/floor is 1.4 mm.`
- `E4 completed 108 trials.`
- `The dual-camera system was fused and validated end to end.`
- `Two cameras are more accurate than one camera.`
- `The viewing angle caused ihawk2 to be more accurate.`
- `The current data identify an optimal camera angle.`
- `Lower native camera resolution was validated on the hardware.`
- `Height universally amplifies the effect of lower resolution.`
- `The moving-camera pipeline was experimentally validated.`
- `The complete manipulation pipeline was validated end to end.`
- `The end-to-end experiment confirms general robot accuracy.`
- `Twelve to sixteen points are generally sufficient.`
- `The E3 subsets/E1 frames are independent experiments.`

允许但需限定：

- `under the tested setup/workspace/candidate set`；
- `descriptively similar`；
- `more robust to off-plane displacement`；
- `observed Oracle reference in the completed block`；
- `consistent with material downstream residuals`；
- `exploratory end-to-end endpoint case study`；
- `estimate fusion and stereo parallax are distinct information flows under the tested static setup`；
- `the current two placements do not identify a causal angle effect`；
- `simulated effective resolution` 与 `simulation-only moving-camera analysis`；
- `end-to-end robot positioning`（仅在紧邻定义或明确指向本文限定链路时）。

## 11. IEEE 目标与阶段 2 门槛

2026-08-14 官方硬规则与 B2 适配判断已冻结在 `../04_writing_standards/IEEE_VENUE_RULES_AND_FIT.md`。蓝图执行顺序为：

- **IEEE Access Research Article：当前默认路线。** 它最能容纳 B2 的 E0–E7 多层应用证据、不同统计单位、透明限制与可复现补充材料。E6 的信息流区分增强了论文 advance，但 E5/E7 不能被包装成原生硬件或真实移动相机实验。
- **TIM Regular Paper：条件冲刺路线。** 仅在现有数据能够通过 measurement gate 时升级：定义 measurand/measurement chain，区分并讨论各误差来源，形成诚实的不确定度/误差预算，以 I&M 文献和 measurement novelty 组织全文。E4 无法复读的 observer component 必须保留为未估计限制。
- **RA-L：暂停路线。** 当前没有足够突出的新机器人算法/系统贡献，且 6–8 页、禁止 supplemental text 的限制与 E0–E7 的透明证据链冲突；只保留 RA-L 样本作为叙事和图表基准。
- **Sensors Journal/OJIM：不在本轮三刊冻结范围内。** 除非后续 scope 判断出现实质变化，不新增分支，避免写作发散。

进入全文写作前必须完成三项：

1. 最接近工作第一轮精读已完成并形成 `PHASE2_NOVELTY_GAP_AUDIT.md`；投稿前仍需按最终 venue 更新检索，禁止把当前结果升级为穷尽性 `first` 声明；
2. TIM / IEEE Access / RA-L 的模板、页数、匿名审稿和 supplement 规则已冻结；仍需作者签认默认 venue，且正式投稿前按官网再次核验；
3. 冻结统计模型、v2.2 figure list 和含 E5–E7 的主张—证据映射；当前机器已生成 `../02_reproducibility/no_rebuild_evidence_manifest.json`，CSV 主张表待专用表格组件可用时迁移 C19–C23。

## 12. AI 与自然语言终审

阶段 5 末尾执行科学一致性审计、独立 AI red-team、自然语言/IEEE 文风审查和作者终审。AI 只生成待核验问题清单或辅助语言修改，不替代数据、引用与作者判断。因为本项目将使用 AI 辅助 outline/drafting/consistency checking，最终在 Acknowledgment 中按实际情况披露系统、涉及章节和使用程度。
