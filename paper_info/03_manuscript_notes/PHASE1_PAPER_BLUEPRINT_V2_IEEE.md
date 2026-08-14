# Phase 1 Paper Blueprint v2 — IEEE Red-Team Revision

版本：v2.4（在原文件内更新，避免版本膨胀）
日期：2026-08-14
默认正文语言：English  
当前定位：IEEE journal-style experimental study  
状态：作者已决定不重新搭建物理系统，并于 2026-08-14 进一步收束主线；E1→E2→E6 构成唯一核心证据链，E6 已补同输出维度 XYZ 消融与 rebuild-level paired contrasts；E3/E5 为支撑检查，E4 为有限应用检查，E0 完整结果进入 Supplement 但关键限制留在正文，E7 不进入投稿稿件；本文件仍是当前唯一蓝图

## 1. 论文定位

本文只回答一个中心问题：在低成本 fixed eye-to-hand fiducial localization 中，目标从标定平面移动到非平面后，二维平面映射、单目 PnP 与双目 stereo 分别提供了什么信息，增加第二个相机估计是否等同于增加双目几何信息？研究对象限定为静态目标、0–50 mm tested mechanical envelope、两台固定相机与五次 physical rebuild。本文不提出新的 Homography、PnP、加权融合或立体三角测量算法；原创性定位为在共享物理观测下对“几何信息充分性”的受控比较。

这里的 information hierarchy 指观测与几何约束逐级增加，而不是声称四种方法具有相同假设或构成一个可互换的算法序列：Homography 使用 marker center pixel 与 Z=0 平面映射；single-view PnP 使用四角点、已知 50 mm marker 尺寸和相机内参恢复 marker-to-camera pose，再通过每次 rebuild 的 Z=0 board extrinsic 转为 board XYZ；estimate fusion 组合两个独立的 camera-specific PnP XYZ；stereo 使用成对中心像素、两视图投影矩阵和 parallax 三角化 board XYZ。E2 的真实高度标签只用于评分，不作为 PnP 输入，也不存在由高度先验触发的 Homography→PnP 切换。

E4 保留为有限 application-side check，而不再承担全文主线或题目中的 `end-to-end` 定位。它只实测了：图像观测/目标定位 → board 坐标映射 → board-to-robot registration → 机器人指令与执行 → 人工观测端点；E6 的双相机融合/stereo 没有传播到该链。因此标题和核心贡献不使用 `end-to-end`，正文仅在 E4 方法、结果与限制中使用其窄定义。

阶段 2 文献边界：monocular/stereo marker localization、多相机 fiducial fusion、view-geometry-dependent marker uncertainty 和 endpoint calibration evaluation 均已有明确先例。因此本文不以“首次采用某算法”或“首次发现角度影响”为贡献。可守区别是：在同一批低成本 paired observations、相同 board truth 与五次 rebuild 上，把 planar mapping、single-view PnP、estimate-level fusion 和 stereo parallax 排成一个逐级增加几何信息的比较链，并量化“第二个估计”与“第二视图几何”在同一条件下的差异。

### 推荐英文题目

**Planar Mapping, Single-View PnP, or Stereo? A Geometry-Conditioned Evaluation for Low-Cost Eye-to-Hand Localization**

### 文献审计通过后可选的题目

**When Does a Second View Add Information? From Planar Mapping to Stereo Geometry in Low-Cost Eye-to-Hand Localization**

暂不使用 `When Is Full 3D Calibration Necessary?`：当前没有预先定义的任务容差，且 PnP 不等同于完整 hand–eye/3-D calibration。

### 一句话主张

> In the tested low-cost eye-to-hand system, Homography and PnP were descriptively similar on the calibration plane, PnP avoided the height-driven collapse of planar mappings, and calibrated stereo produced lower mean 3-D error than combining two camera-specific PnP estimates, although the stereo advantage was not rebuild-universal at the largest tested height.

## 2. 研究问题

### RQ1 — What geometric information is sufficient as the target leaves the calibration plane?

在共享 planar truth 与五次 physical rebuild 下，二维 Homography 和 single-view PnP 的相对表现如何从 Z=0 平面变化到 Z=5–50 mm？Affine 只作为低复杂度全局基线，不与 Homography/PnP 构成三条并列创新线。

预期回答：E1 的 36 个 held-out planar locations 上，Homography/PnP RMSE 为 0.660/0.661 mm，描述性相近；E2 中二维映射随高度明显退化，而 PnP 在两相机、五次 rebuild 中保持更稳定的 height response，但存在 camera-specific absolute bias。正文报告完整 height-conditioned curves、相对 Z=0 的误差增量及 rebuild 离散性。结论是“所需几何信息随目标是否离面改变”，不是 PnP 普适最优或从观察结果事后挑出的“不可接受高度”。只有未来先于数据定义应用精度容差，才能据此讨论 deployment switch point。

### RQ2 — What does the second view add: another estimate or new geometry?

在相同静态目标、配对观测与五次 physical rebuild 下，第二台相机作为另一个 camera-specific board estimate 被 equal/LOO-weighted fusion 使用，与直接通过 stereo parallax 恢复 board XYZ 时，分别产生什么结果？

预期回答：25 mm 高度下，严格同维度 XYZ 消融的 ihawk1 PnP/ihawk2 PnP/equal XYZ/LOO-weighted XYZ/stereo 3-D RMSE 为 10.348/6.144/7.431/6.351/3.342 mm；estimate fusion 未超过较强的 ihawk2。ihawk2-minus-stereo paired 3-D difference 均值为 2.802 mm、range 1.856–3.946 mm，stereo 在 5/5 rebuilds 中更低。到 50 mm，ihawk2/stereo 均值为 6.002/4.897 mm，paired difference 均值虽为 1.105 mm，但 range 为 −2.902–2.845 mm，stereo 只在 4/5 rebuilds 中更低，说明 aggregate advantage 不是 universal per-rebuild dominance。核心区别是：第二个带偏估计不自动增加有效信息，而 calibrated parallax 提供新的深度约束；这不是“任意双相机一定更好”的结论。

E3、E5 和 E4 不再定义独立 RQ。E3 检查 calibration coverage，E5 检查 saved-image resolution/detection/latency，E4 只检查有限的 application-side error transfer；它们用于审查主结论的边界，不扩展中心问题。

## 3. 主要贡献

### C1 — Controlled geometric-information hierarchy

在共享 undistorted observations、board truth、calibration convention 和正确统计单位下，建立从 planar Homography、single-view PnP、two-estimate fusion 到 stereo triangulation 的连续比较。E1/E2/E6 不是相互独立的数据故事，而是逐级回答“目标几何变化时需要多少视觉几何信息”。

### C2 — Empirical distinction between a second estimate and a second view

用五次 paired physical rebuild 及统一的 board XYZ 输出/XY、Z、3-D 指标定量显示：equal/LOO-weighted combination 只能重新组合两个 camera-specific estimates，可能继续保留系统偏置；使用同一对观测的 calibrated stereo parallax 则增加深度约束。以 rebuild 为单位的 paired contrasts 同时显示优势是否跨重建一致。该贡献是 controlled empirical finding，不把既有 fusion 或 triangulation 算法包装为新方法。

E3 calibration coverage、E5 simulated effective-resolution/latency 和 E4 exploratory endpoint transfer 是 supporting validity checks，不列为第三、第四项并列贡献。代码、失败记录、统计单位和人工修订审计属于可复现性基础，也不单独包装为算法创新。

## 4. 实验角色与统计单位

| 实验 | 正文角色 | 正确统计/观察单位 | 不能写成 |
|---|---|---|---|
| E0-A/B | Supplement diagnostics | camera-position frame sequence；有限 arrivals | 独立物理实验；完整 uncertainty budget；robot-only cause |
| E1 | RQ1 planar anchor | 36 个同一板上的 held-out spatial locations | 36 次独立部署；1800 个独立样本 |
| E2 | RQ1 physical core | 每相机五次 physical rebuild；三帧先平均 | 三帧 = 三个独立重复；Z=0 = held-out test |
| E3 | Supporting calibration check | 同一物理观测集上的 offline subsets | 独立 RQ；每条件 100 次物理重标定 |
| E4 | Limited application-side check | repeat 1 的 9 个 paired targets；repeat 2 仅 2 targets | 全文高潮；E6 endpoint validation；确认性 108-trial study |
| E5 | Supporting observation/resource check | E2 保存图像的 paired downsampling；准确度仍按 physical rebuild 汇总 | 独立 RQ；原生传感器模式实验；分辨率层级是独立部署 |
| E6 | RQ2 physical-data core | 五次 rebuild 下的静态配对观测；三帧先平均 | 双相机已贯通 E4；动态同步验证；独立 metrology ground truth |
| E7 | Repository-only future-work pilot | 10 nominal poses × Monte Carlo perturbations | 投稿正文或 Supplement 的证据；真实移动相机实验 |

### E0 边界

正文仅用一段或 Table II 中的量级摘要说明：短期相机随机波动不足以解释 E2 的数十毫米高度误差；固定起点与路径是 E4 的必要控制。完整位置表、axis mapping 和诊断进入 Supplement。

### E1 边界

三种方法使用相同 12 calibration points、36 held-out locations、50 accepted frames 和 board XY truth。主指标为每个位置的 median-observation prediction error；frame-wise 结果只描述定位波动敏感性。

### E2 边界

每次 rebuild 对每台相机只用自身 Z=0 数据标定并冻结模型，再应用到 Z=5–50 mm。正文必须说明“physical rebuild”的实际操作定义，并给出每个 rebuild 的 paired trace。

PnP 的操作定义必须写清：输入为检测到的四个 marker corners、已知 50 mm 平面 marker object points 与相机内参；`solvePnP` 得到 marker-to-camera pose，再用该 camera/rebuild 在 Z=0 冻结的 camera-to-board extrinsic 转成 board XYZ。Z=5–50 mm 标签只用于 ground-truth scoring，不输入 PnP，也不使用额外高度先验。Homography 只把 center pixel 映射到 Z=0 board XY，因此两者的区别是所用观测和几何约束不同，不是从一个模型“连续升级”到另一个模型。

0–50 mm 是已采集装置的 tested height envelope，不是为了发现显著性而选择的范围，也不支持超出该范围的外推。正文画出全范围曲线与相对 Z=0 的误差增量；未预定义 application tolerance 时，不把曲线上的任一点命名为“单目失效阈值”。

50 mm headline：

- ihawk1 Affine/Homography/PnP：69.63/81.97/10.63 mm；
- ihawk2 Affine/Homography/PnP：56.43/64.26/4.54 mm。

同时必须披露 Z=0 的 PnP XY RMSE 为 ihawk1 7.72 mm、ihawk2 3.21 mm；因此 PnP 的优势主要是 off-plane robustness，而不是所有条件下的最低 absolute error。

### E3 边界

4-point spread 的 Homography/PnP median RMSE 为 0.955/0.731 mm；4-point clustered 为 243.696/1.736 mm，PnP fitting failure 为 3%。12-point spread 为 0.584/0.597 mm，24-point spread 为 0.562/0.581 mm。

E3 不再单列 RQ 或主结果图。正文只用一个 supporting table/panel 证明主比较对 calibration coverage 敏感，并写“coverage mattered strongly in the tested candidate set”；“12–16 points”仅作为 Discussion 中的 dataset-specific observation，Supplement 给出全部 54 conditions 与生成规则。

### E4 边界

主分析仅使用完整 repeat 1：9 targets × 4 methods = 36 trials。实际总采集 44/计划 108，repeat 2 的 T02/T04 共 8 条只用于有限短期重复性描述。

Oracle/Affine/Homography/PnP 的 mean E2E 为 1.387/3.306/2.236/2.065 mm；RMSE 为 1.581/3.659/2.577/2.375 mm。由于 Oracle 同时包含 registration、controller、mechanics、tool alignment 与人工网格读数，统一称 `observed Oracle reference in the completed block`。

board-to-robot registration 的训练 XY RMSE 为 3.327 mm，两个 2-point held-out batches 分别出现 5/14.142 mm 与 5/12.806 mm。这些检查太小且误差较大，必须进入 Supplement/Limitations；它们阻止我们把 1.387 mm 写成稳定 downstream floor。

文献对 E4 的额外约束：Zhong et al. 使用 XYZ microtrimming platform 和 checkerboard reference 对 3-D endpoint error 做外部测量；Chajón et al. 使用 30 repetitions × 5 poses，并以百分表提供机器人重复性的独立参考。相比之下，本项目是人工网格读数、one completed 9-target block，且没有独立计量设备。因此 E4 只能支持 model-conditioned endpoint observations，不能支持 ISO-style robot accuracy/repeatability 或对 robot-only 与 measurement-chain error 的严格分离。E4 不进入题目、摘要主结论或贡献列表，也不能被解释为 RQ2/E6 的下游验证。

### E5 边界

E5 只把 E2 的 lossless 640 × 400 保存图像按 area interpolation 离线降采样到 480 × 300、320 × 200、240 × 150 和 160 × 100，并同步缩放 camera matrix。它回答 effective spatial resolution，而不是传感器原生模式；曝光、光学、read noise、ISP 和 sensor frame rate 均未改变。Accuracy 只在完整检测五个 marker 的 run-height 条件上计算，必须与 detection/coverage 一起报告，防止 survivorship bias。时延只含分析计算机上的处理时间，不含磁盘 I/O、采集和机器人控制环。

E5 对论文最重要的结果是负面的 observation/resource check：保存图像的基准 640 × 400 pipeline 已经通过预定义 30 Hz gate，降采样虽更快但显著损害检测完整率，并对 PnP 造成 camera-dependent accuracy cost；没有观察到跨相机/模型一致的 resolution × height 放大规律。因此 E5 不设 RQ、不进入题目或摘要，正文最多用一个 supporting table/短段，其完整曲线进入 Supplement。

### E6 边界

E6 必须把三种信息流分开写：single-camera estimate；将两个 camera-specific board estimates 做 equal/LOO-weighted fusion；利用两视图投影矩阵与 parallax 做 stereo triangulation。只有第三种直接增加 parallax-based depth information。核心消融统一输出 board XYZ，并统一报告 XY RMSE、Z RMSE 与 3-D RMSE：

| 条件 | 输入与处理 | 第二相机角色 | 核心输出 |
|---|---|---|---|
| ihawk1/ihawk2 PnP | 单相机四角点 + marker scale + intrinsics + frozen board extrinsic | 无/单相机基线 | board XYZ |
| EqualXYZ | 两个 camera-specific PnP XYZ 等权平均 | another estimate | board XYZ |
| LOOWeightedXYZ | 仅从其余四个 rebuild 的 Z=0 3-D MSE 学权重 | another estimate | board XYZ |
| StereoTriangulation | paired center pixels + 两投影矩阵 + parallax | stereo view | board XYZ |

不把 `fusion + stereo` 加入核心消融：它会对同一对图像产生的相关 estimators 再定义一套融合规则，既不是独立信息条件，也需要额外调参，反而破坏“另一个 estimate vs stereo geometry”的可解释比较。它可作为未来算法研究，但不是证明 RQ2 完整性的必要第四组。

所有 pairing 来自静态目标；pair delta median/P95/max 为 18.267/46.519/49.217 ms，不能外推到动态场景。Stereo 的投影矩阵由同一 E2 Z=0 数据导出，不是独立计量参考，也没有进入 E4 endpoint chain。25 mm 时 stereo 相对 ihawk2 PnP 的 3-D error 在 5/5 rebuilds 更低；50 mm 时为 4/5，必须同时报告均值差、SD/range 与 sign count，不能只用总体均值写“stereo always wins”。

角度处理只允许使用 `E6_ANGLE_IDENTIFIABILITY_AUDIT.md` 的结论：10 个 rows 是两种固定布局在五次 rebuild 中的重复，不是 10 个 angle levels。Camera identity 对 distance、tilt、marker side 与 footprint 的 eta² 为 0.9997/0.9863/0.9984/0.9997，四个变量的两相机范围全部不重叠。该结果只在 Supplement/Limitations 证明当前设计的混杂程度；不占主图 panel，不证明任一角度更好。

### E7 边界

E7 是 deterministic Monte Carlo simulation，没有 detector failures、motion blur、occlusion、vibration、rolling shutter、真实同步或机器人 endpoint。它不进入本次投稿正文、Appendix 或 Supplement，也不在 Abstract/Contribution/Conclusion 中出现；代码和结果保留在仓库，作为未来移动相机论文或后续物理验证的内部 pilot。Discussion 只能不带数字地把 moving-camera relocalization 列为 future work。

## 5. 正文论证顺序

1. 定义一个 information hierarchy：planar Homography → single-view PnP → two-estimate fusion → stereo triangulation，并说明 Affine 只是低复杂度 baseline。
2. 用 E1 的 held-out planar locations 建立 RQ1 的平面锚点，再直接进入 E2 的 0–50 mm height scan；E1/E2 合写成“from planar to off-plane”，不拆成两条论文故事。
3. 用 E6 回答唯一第二问题：第二台相机作为另一个 estimate 与作为 stereo view 时分别增加什么。主结果章节在这里达到论证峰值。
4. E3/E5 放入一个简短的 `Supporting validity checks` 小节或 Table：coverage matters；保存图像基准分辨率已满足 latency gate，降采样损害 reliability。正文用 2–3 句话说明这些检查约束何种外推，完整结果放 Supplement；由于它们不是同一 factorial experiment，不声称其“证明所有条件下主排序不变”。
5. E4 作为 `Exploratory application-side check`，只说明 single-camera vision differences 与 endpoint observations 并非一比一传递；不声称验证 E6，也不作为全文高潮。
6. E0 的完整诊断进 Supplement，但正文 Methods/Limitations 保留一句关键量级结论；E7 完全退出投稿包，正文不引用其数字。
7. Discussion 回答“在 tested setup 中二维平面信息如何随离面位移退化、第二视图何时提供了额外几何约束”，并明确 universal angle、native sensor mode、moving-camera relocalization 与 production-wide threshold 均超出当前证据，可作为 future work 而不作结果声称。

## 6. 统计分析计划

- 所有表格同时给出 metric、统计单位、physical n、offline n 和缺失/失败数。
- E1：target-wise paired error distribution 与 effect sizes；不把 frames 作为独立推断样本。
- E2：每个 rebuild 的曲线必须可见；报告跨 rebuild 的中心、离散性和区间，以及相对 Z=0 的变化。不从结果事后选择 application failure threshold。若阶段 3 进行正式模型检验，必须保留 method/height 的配对和 rebuild/target 层级。
- E3：作为 supporting check 使用 median、IQR/quantiles、failure rate 和 extreme-error summary；完整条件进入 Supplement。
- E5：作为 supporting check 同时报 marker detection/complete-frame coverage 与 accuracy available n；准确度以 physical rebuild 为单位，降采样层级是 paired transformation。正文只保留 baseline 640 × 400、480 × 300 和 latency gate 的关键结果。
- E6：核心比较统一为 board XYZ，并同时报告 XY、Z、3-D RMSE；融合/triangulation 准确度以 physical rebuild 为单位，逐 height 给 estimate-minus-stereo paired difference、SD/range 和 stereo-lower sign count。LOO-weighted 参数只从其余四个 rebuild 的 Z=0 数据学习。n=5 时不把 marker rows 当独立样本，也不以脆弱 p-value 代替 rebuild traces；`LOOWeightedGated` 仍是次要 XY/coverage 诊断，其 conditional error 必须与 coverage 同报。角度只报告 setup descriptives、camera-identity eta² 和不可识别性，不给 pooled-correlation p-value 或多变量因果回归。
- E4：只做 paired descriptive comparison 与透明 effect sizes，不做利用未完成重复的确认性 p-values；不与 E6 构造不存在的 endpoint comparison。
- E7：不进入稿件统计计划。
- 不为增强显著性而把离线 resamples、frames 或 spatial locations 当成 physical replicates。

## 7. 正文图表

### Figures

1. **System and geometric-information hierarchy.** 系统照片/坐标系，加一条清楚的 planar Homography → single-view PnP → estimate fusion / stereo parallax 信息链。E4 只作为旁支小框，E7 不出现。
2. **From planar to off-plane localization.** E1 held-out planar paired errors 与 E2 height curves 合为一张主图，直接回答 RQ1；caption 分清 E1 spatial locations 与 E2 physical rebuilds。
3. **What the second view adds.** 左 panel 保留 single-camera/equal/LOO-weighted PnP 与 stereo 的 XY height curves；右 panel 用严格同输出维度的 ihawk1/ihawk2/equal XYZ/LOO-weighted XYZ/stereo 3-D height curves，并在 caption 或相邻表给出 25/50 mm paired rebuild sign counts。它直接回答 RQ2，是全文最重要的结果图；不放 angle panel，也不画不存在的 `fusion + stereo` 条件。
4. **Exploratory application-side transfer.** E4 repeat-1 paired endpoint plot，标题/caption 写明 single-camera methods、9 targets、one completed block、manual reading、early stop 和 `not an E6 endpoint validation`。

E0、E3、E5 和 angle-identifiability 不单独占主图；其完整结果进入 Supplement，正文只用表格或短段。

### Tables

1. **Hardware, targets, coordinates, and acquisition protocol.** 明确 50 mm ArUco、25 mm chessboard square 及其他板定义，避免标记尺寸混用。
2. **Experimental design and evidence roles.** 明确 E1/E2/E6 是核心，E3/E5/E4 是 supporting，E0 是 main-text limitation + Supplement diagnostics，E7 excluded；同时列 physical/offline units。
3. **Headline results and supporting validity checks.** 主区只放 E1/E2/E6；次区压缩 E3 coverage、E5 detection/latency 和 E4 exploratory endpoint 数字，不把不同独立性层级混成一个 n。

## 8. 章节结构

1. Abstract
2. Index Terms
3. I. Introduction
4. II. Related Work
5. III. System and Geometric-Information Evaluation Protocol
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
- S10 E6 XY fusion diagnostics、strict XYZ ablation、LOO weight audit、rebuild-level paired contrasts、gated coverage、stereo XYZ、pair timing 和 angle-identifiability audit；
- S11 reproducibility README, code/data inventory, software versions and `no_rebuild_evidence_manifest.json`。

E7 资产保留在仓库，但不列入投稿 Supplement inventory。

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
- `This paper establishes a comprehensive deployment operating envelope.`
- `Resolution, camera angle, and camera motion are three co-equal research contributions.`
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
- `exploratory application-side endpoint check`；
- `estimate fusion and stereo parallax are distinct information flows under the tested static setup`；
- `the current two placements do not identify a causal angle effect`；
- `simulated effective resolution`（仅用于 E5 supporting check）；
- `end-to-end robot positioning`（只在 E4 窄定义内，不用于题目、摘要主结论或贡献）。

## 11. IEEE 目标与阶段 2 门槛

2026-08-14 官方硬规则与 B2 适配判断已冻结在 `../04_writing_standards/IEEE_VENUE_RULES_AND_FIT.md`。蓝图执行顺序为：

- **IEEE Access Research Article：当前默认路线。** 收束后的稿件只以 E1/E2/E6 支撑两个 RQ；E3/E5/E4 作为有限 supporting checks，E0 完整诊断进 Supplement 且关键 limitation 留正文，E7 不进投稿包。E6 的 strict same-output information-flow distinction 是唯一需要在第一页说清的 advance。
- **TIM Regular Paper：条件冲刺路线。** 仅在现有数据能够通过 measurement gate 时升级：定义 measurand/measurement chain，区分并讨论各误差来源，形成诚实的不确定度/误差预算，以 I&M 文献和 measurement novelty 组织全文。E4 无法复读的 observer component 必须保留为未估计限制。
- **RA-L：暂停路线。** 当前没有足够突出的新机器人算法/系统贡献；即使稿件已收束，也不把 controlled evaluation 包装成 robotics algorithm contribution。
- **Sensors Journal/OJIM：不在本轮三刊冻结范围内。** 除非后续 scope 判断出现实质变化，不新增分支，避免写作发散。

进入全文写作前必须完成三项：

1. 最接近工作第一轮精读已完成并形成 `PHASE2_NOVELTY_GAP_AUDIT.md`；投稿前仍需按最终 venue 更新检索，禁止把当前结果升级为穷尽性 `first` 声明；
2. TIM / IEEE Access / RA-L 的模板、页数、匿名审稿和 supplement 规则已冻结；仍需作者签认默认 venue，且正式投稿前按官网再次核验；
3. 冻结统计模型、v2.4 four-figure list 和收束后的主张—证据映射；C19/C20/C22/C23 只作为 supporting/excluded records，C21 是唯一新增核心 claim。当前机器已生成 `../02_reproducibility/no_rebuild_evidence_manifest.json`，CSV 主张表待专用表格组件可用时迁移。

## 12. AI 与自然语言终审

阶段 5 末尾执行科学一致性审计、独立 AI red-team、自然语言/IEEE 文风审查和作者终审。AI 只生成待核验问题清单或辅助语言修改，不替代数据、引用与作者判断。因为本项目将使用 AI 辅助 outline/drafting/consistency checking，最终在 Acknowledgment 中按实际情况披露系统、涉及章节和使用程度。
