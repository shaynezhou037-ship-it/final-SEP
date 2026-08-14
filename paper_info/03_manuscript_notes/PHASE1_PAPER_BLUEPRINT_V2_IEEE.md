# Phase 1 Paper Blueprint v2 — IEEE Red-Team Revision

版本：v2.1（在原文件内更新，避免版本膨胀）  
日期：2026-08-13  
默认正文语言：English  
当前定位：IEEE journal-style experimental study  
状态：作者已确认 end-to-end 定义、E4 角色、三条 venue 检索路线和暂留 Acuna；阶段 2 第一轮近邻文献审计与 2026-08-14 三刊规则冻结已写回；作为当前唯一蓝图；V1 已删除

## 1. 论文定位

本文可以、也应当按照 end-to-end 主线来写，但必须把 end-to-end 的边界写窄、写实。本文不提出新的 Affine、Homography 或 PnP 算法，也不做脱离任务条件的模型排名；研究对象是在同一低成本固定相机 eye-to-hand 系统、共享观测和真值的条件下，任务几何与标定点覆盖如何改变映射误差，以及这种误差如何传递到机器人端点。

本文中的 **end-to-end** 仅指：图像观测/目标定位 → board 坐标映射 → board-to-robot registration → 机器人指令与执行 → 人工观测端点。它不包括任意物体检测、抓取规划、接触动力学、抓取成功率、双相机融合或连续闭环控制。标题、摘要、图注和结论中的每一次 `end-to-end` 都必须符合该定义。

阶段 2 文献边界：Ulrich et al. (ISPRS JPRS 2024) 已用 `end to end` 描述 robot kinematics、hand--eye 和 camera intrinsics 的同步校准；Zhong et al. (T-RO 2023) 已将 robot--camera calibration 评价到三维末端定位误差。因此本文不主张首次 `end-to-end calibration`，也不把 endpoint validation 本身当作首创。这里的可守贡献是：在共享观测/真值下，把三个 mapping pipelines 的 planar、off-plane、coverage 和 exploratory endpoint evidence 放入同一套可审计、多层评价协议。

### 推荐英文题目

**From Calibration Accuracy to End-to-End Robot Positioning: Geometry-Dependent Evaluation of Affine, Homography, and PnP Mapping**

### 文献审计通过后可选的题目

**Geometry-Aware Model Selection for Low-Cost Eye-to-Hand Positioning: Planar, Off-Plane, and Endpoint Errors**

暂不使用 `When Is Full 3D Calibration Necessary?`：当前没有预先定义的任务容差，且 PnP 不等同于完整 hand–eye/3-D calibration。

### 一句话主张

> In a tested low-cost eye-to-hand system, we trace calibration-model error from held-out planar localization through off-plane displacement and calibration-point coverage to robot endpoint error, showing that model choice is geometry dependent and that vision-level gains do not transfer one-to-one to the endpoint in the completed exploratory block.

## 2. 研究问题

### RQ1 — Planar accuracy

在同一平面观测、相同标定点、相同 held-out 空间位置和相同真值下，Affine、Homography 和 PnP 的 XY 定位误差如何？

预期回答：在 ihawk1 和当前板/工作区中，Homography 与 PnP 的 RMSE 为 0.660/0.661 mm，均低于全局 Affine 的 4.854 mm。36 个观测单位是 held-out spatial locations，不是 36 次独立物理重装；“相近”是描述性结论，不是统计等效。

### RQ2 — Off-plane robustness

目标离开 Z=0 标定平面时，三种模型的绝对误差和高度退化趋势如何随相机与 rebuild 改变？

预期回答：二维映射随高度明显退化，PnP 在两个相机和五个 physical rebuild 中对高度更稳健，但存在相机相关的绝对偏差。核心结论是 robustness，不是“PnP 在所有高度绝对最准确”。

### RQ3 — Calibration design sensitivity

在当前候选点和固定验证集上，标定点数量、空间覆盖与拟合稳定性有什么关系？

预期回答：tested dataset 中，spread configurations 明显优于 minimal clustered configurations；12 到 24 个 spread 点之间的额外收益较小。100 subsets/condition 是离线重采样，不是独立物理重标定。

### RQ4 — End-to-end endpoint transfer（exploratory validation block）

在一个冻结视觉预测、固定起点与路径的有限机器人实验中，视觉误差差异如何体现在端点误差中？

预期回答：完整 balanced block 的 Oracle/Affine/Homography/PnP mean E2E 分别为 1.387/3.306/2.236/2.065 mm。该结果只说明本次 completed block 中存在 material downstream residual；不将 Oracle 解释为纯机器人误差或稳定误差地板。

## 3. 主要贡献

### C1 — 可审计的 end-to-end 误差链

在共享 undistorted observations、ground truth、calibration/validation split 和统计边界的条件下比较三个 mapping pipelines，并把评价从平面定位、离平面退化和标定覆盖一直连接到机器人端点；同时公开数据冻结、失败、提前停止和人工修订规则。

### C2 — Geometry-dependent operating behavior

用平面 held-out locations 与两相机、五次 independent physical rebuild、0–50 mm 扫描区分 in-plane accuracy、off-plane degradation 和 absolute bias，显示模型复杂度的收益依赖任务几何。

### C3 — Calibration design sensitivity and downstream error transfer

量化 tested workspace 中空间覆盖、点数和数值退化的关系，并用 completed exploratory E4 block 说明 vision benchmark 的改进不必然一比一传递为 endpoint 改进。E4 是全文的叙事终点和下游有效性检查，但不是完成 108 次重复的确认性验证。

## 4. 实验角色与统计单位

| 实验 | 正文角色 | 正确统计/观察单位 | 不能写成 |
|---|---|---|---|
| E0-A | 静态测量噪声量级 | camera-position 下的短期 frame sequence | 500 次独立实验；完整 uncertainty budget |
| E0-B/B2 | 执行协议诊断 | 一个或有限 target 下的 arrivals | 纯 robot repeatability；backlash/IK 因果证明 |
| E1 | RQ1 主数据 | 36 个同一板上的 held-out spatial locations | 36 次独立部署；1800 个独立样本 |
| E2 | 全文主轴 | 每相机五次 physical rebuild；三帧先平均 | 三帧 = 三个独立重复；Z=0 = held-out test |
| E3 | RQ3 敏感性分析 | 同一物理观测集上的 offline subsets | 每条件 100 次物理重标定 |
| E4 | end-to-end endpoint case study | repeat 1 的 9 个 paired targets；repeat 2 仅 2 targets | 108 条已完成；确认性机器人验证；完整 manipulation success study |

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

## 5. 正文论证顺序

1. 定义系统、坐标链、三种 mapping pipelines 与公平比较原则。
2. E1 建立平面 held-out baseline。
3. E2 作为核心展示模型 × height × camera/rebuild 的条件依赖。
4. E3 分析标定几何覆盖与数值退化，形成限定于 tested setup 的工程启示。
5. E4 用一个完整结果小节和一张主图收束全文，展示限定边界下的 end-to-end endpoint transfer；篇幅地位可以突出，但证据强度仍标为 exploratory。
6. E0 作为方法合理性/限制背景穿插，不单独形成与 E1–E3 等长的结果章节。
7. Discussion 给出条件化选择，不给普适排名或未经定义的“必要高度”。

## 6. 统计分析计划

- 所有表格同时给出 metric、统计单位、physical n、offline n 和缺失/失败数。
- E1：target-wise paired error distribution 与 effect sizes；不把 frames 作为独立推断样本。
- E2：每个 rebuild 的曲线必须可见；报告跨 rebuild 的中心、离散性和区间。若阶段 3 进行正式模型检验，必须保留 method/height 的配对和 rebuild/target 层级。
- E3：使用 median、IQR/quantiles、failure rate 和 extreme-error panel，避免退化条件被均值掩盖。
- E4：只做 paired descriptive comparison 与透明 effect sizes，不做利用未完成重复的确认性 p-values。
- 不为增强显著性而把离线 resamples、frames 或 spatial locations 当成 physical replicates。

## 7. 正文图表

### Figures

1. **End-to-end system chain and experiment map.** 系统照片/示意、坐标系、图像到端点的完整链路，以及 E1–E4 分别验证哪一段。图中用实线表示已实测链路、虚线表示未覆盖的 detection/grasp/contact 环节。
2. **Planar held-out performance.** E1 的 target-wise paired errors；caption 明确 36 spatial locations。
3. **Height-dependent robustness.** 双相机 panels，显示每个 rebuild trace 与跨 rebuild summary；这是主图。
4. **Calibration-design sensitivity.** count × distribution × model，另标 failure/extreme cases。
5. **Exploratory end-to-end endpoint transfer.** E4 repeat-1 paired target plot + vision/downstream/E2E 分解；标题/caption 写明 9 targets、one completed block、manual endpoint reading 和 early stop。
6. **Conditional model-selection summary.** 只总结本文数据支持的条件，不创造普适阈值。

E0 静态结果优先压缩进 Table II 或 Supplement，不强制单独占用一张主图。

### Tables

1. **Hardware, targets, coordinates, and acquisition protocol.** 明确 50 mm ArUco、25 mm chessboard square 及其他板定义，避免标记尺寸混用。
2. **Experimental design and statistical units.** E0–E4 的 physical/offline units、主指标与限制。
3. **Headline quantitative results.** E1、E2 与 exploratory E4 的核心数字；不把不同独立性层级混成一个 n。

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
- S9 reproducibility README, code/data inventory, software versions。

## 10. 禁止与限定表述

禁止：

- `PnP is universally the most accurate method.`
- `Full 3D calibration becomes necessary above X mm.`（除非先定义应用容差并完成对应分析）
- `Homography and PnP are statistically equivalent.`
- `The robot error/floor is 1.4 mm.`
- `E4 completed 108 trials.`
- `The dual-camera system was fused and validated end to end.`
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
- `end-to-end robot positioning`（仅在紧邻定义或明确指向本文限定链路时）。

## 11. IEEE 目标与阶段 2 门槛

2026-08-14 官方硬规则与 B2 适配判断已冻结在 `../04_writing_standards/IEEE_VENUE_RULES_AND_FIT.md`。蓝图执行顺序为：

- **IEEE Access Research Article：当前默认路线。** 它最能容纳 B2 的完整应用实验、不同统计单位、透明限制与可复现补充材料；仍须证明相对现有工作的明确 advance，并保持高技术/统计标准。
- **TIM Regular Paper：条件冲刺路线。** 仅在现有数据能够通过 measurement gate 时升级：定义 measurand/measurement chain，区分并讨论各误差来源，形成诚实的不确定度/误差预算，以 I&M 文献和 measurement novelty 组织全文。E4 无法复读的 observer component 必须保留为未估计限制。
- **RA-L：暂停路线。** 当前没有足够突出的新机器人算法/系统贡献，且 6–8 页、禁止 supplemental text 的限制与 E0–E4 的透明证据链冲突；只保留 RA-L 样本作为叙事和图表基准。
- **Sensors Journal/OJIM：不在本轮三刊冻结范围内。** 除非后续 scope 判断出现实质变化，不新增分支，避免写作发散。

进入全文写作前必须完成三项：

1. 最接近工作第一轮精读已完成并形成 `PHASE2_NOVELTY_GAP_AUDIT.md`；投稿前仍需按最终 venue 更新检索，禁止把当前结果升级为穷尽性 `first` 声明；
2. TIM / IEEE Access / RA-L 的模板、页数、匿名审稿和 supplement 规则已冻结；仍需作者签认默认 venue，且正式投稿前按官网再次核验；
3. 冻结统计模型、figure list 和主张—证据映射 v2。

## 12. AI 与自然语言终审

阶段 5 末尾执行科学一致性审计、独立 AI red-team、自然语言/IEEE 文风审查和作者终审。AI 只生成待核验问题清单或辅助语言修改，不替代数据、引用与作者判断。因为本项目将使用 AI 辅助 outline/drafting/consistency checking，最终在 Acknowledgment 中按实际情况披露系统、涉及章节和使用程度。
