# 最终保留论文阅读笔记

检查日期：2026-08-13  
方法：PDF 全文文本提取 + 关键页视觉检查 + DOI/出版元数据核验。这里记录“能支持什么”和“不能支持什么”，避免写作时凭印象引用。

## Chen et al., EasyHeC, IEEE RA-L (2023)

- DOI：`10.1109/LRA.2023.3315551`
- 阅读重点：PDF pp. 1–8；视觉重点 p. 1 Fig. 1、p. 6 Figs. 6–7、结论/限制页。
- 可支持：hand–eye calibration directly affects downstream positioning/manipulation；高水平 RA-L 可用 real-robot targeting 作为下游收束；calibration pose/space coverage 会造成不均匀误差。
- 写作学习：第一页 problem–method–task 图；synthetic → public real data → targeting → ablation 的证据梯度。
- 不能支持：B2 的 PnP 比 Homography 好；B2 的 E4 是确认性 end-to-end study；B2 的具体误差来源。
- 决定：`VERIFIED_FULLTEXT`，正文 related work 候选 + 核心写作基准。

## Zhong et al., Interactive Hand–Eye Calibration, IEEE RA-L (2020)

- DOI：`10.1109/LRA.2020.2967685`
- 阅读重点：p. 1 contribution framing；pp. 5–7 real robot and robustness；p. 8 conclusion/limitations。
- 可支持：eye-to-hand calibration 可通过任务相关机器人实验和 downstream case study 评价；真实系统结果需与 simulation/parameter estimation 分层报告。
- 写作学习：具体三项贡献、系统实物图、仿真—真实—任务案例、结论中明确限制。
- 不能支持：低成本 RGB-D 系统的通用数值；本项目 endpoint floor。
- 决定：`VERIFIED_FULLTEXT`，related work 候选 + 写作基准。

## Wu et al., 4-D Procrustes, IEEE TIM (2020)

- DOI：`10.1109/TIM.2019.2930710`
- 阅读重点：pp. 1–2 problem/contribution/Table I；pp. 8–9 hardware and evaluation；pp. 14–16 appendix/conclusion。
- 可支持：hand–eye calibration 的 formal problem、算法比较与 uncertainty description 需要联合验证；真实机器人轨迹可作为标定下游误差检查。
- 写作学习：相关方法表、算法伪代码、协方差/仿真/真实实验对应。
- 不能支持：我们的 board-to-robot registration 等于经典 `AX=XB`；E4 residual 的因果分解。
- 决定：`VERIFIED_FULLTEXT`，TIM 风格基准；是否进正文取决于 related-work 边界。

## Rustler et al., RGB-D Camera Comparison, IEEE Access (2025)

- DOI：`10.1109/ACCESS.2025.3560810`
- 阅读重点：p. 1 abstract/contribution；p. 3 hardware/setup tables；pp. 6/9 results；pp. 13–14 discussion/limitations。
- 可支持：RGB-D 性能与距离、对象/表面和应用场景相关；公平多设备实证比较和公开数据本身可以形成贡献。
- 写作学习：厂家规格与实际设置分表；每个场景独立定义、指标和总结；建议始终绑定距离/任务。
- 不能支持：Berxel 相机的具体误差；B2 两台相机孰优。
- 决定：`VERIFIED_FULLTEXT`，Introduction/related work 候选 + 核心比较论文基准。

## Collins and Bartoli, IPPE, IJCV (2014)

- DOI：`10.1007/s11263-014-0725-5`
- 阅读重点：p. 1 definition/contribution；p. 5 PnP context；experiment/results；pp. 34–35 conclusion/references。
- 可支持：IPPE 的原始定义、planar pose ambiguity、analytic solutions 和适用范围；本项目使用 `SOLVEPNP_IPPE` 时应引用原始论文。
- 写作学习：理论主张与 simulation/real dataset 一一对应。
- 不能支持：OpenCV 具体版本行为（需查官方文档/代码）；B2 的坐标链实现正确性。
- 决定：`VERIFIED_FULLTEXT`，方法部分必引候选。

## Acuna and Willert, Control-Point Configurations (2018 preprint)

- 标识：arXiv `1803.03025`；未发现经核验的正式同行评审版本。
- 阅读重点：pp. 1–2 problem/method；p. 4 camera-pose simulation；pp. 5–7 configurations/error curves/conclusion。
- 可支持：point configuration/conditioning can affect Homography, IPPE and EPnP accuracy；well-distributed points may outperform larger ill-conditioned sets。
- 写作学习：同时画 well-conditioned、ill-conditioned、ideal square 和 number of points。
- 不能支持：把 “12–16 points sufficient” 写成定律；把预印本称为 IEEE paper。
- 决定：`PROVISIONAL_PREPRINT`。E3 最直接，但投稿前必须继续寻找正式来源；找不到时显式按 preprint 引用并降低依赖。

## Zhang, Flexible Camera Calibration, IEEE TPAMI (2000)

- DOI：`10.1109/34.888718`；正式期刊：22(11):1330–1334。
- 本地版本：22 页扩展作者/技术报告版；视觉重点为 procedure、degenerate configurations、simulation、non-planarity sensitivity。
- 可支持：planar-pattern intrinsic calibration 的经典 closed-form + nonlinear refinement；平面标定存在退化配置和系统误差敏感性。
- 写作学习：先给可复现步骤，再单列退化、simulation 和 real data。
- 不能支持：把本项目单平面 XY mapping 称为 Zhang calibration；把扩展报告页码写进正式期刊引用。
- 决定：`VERIFIED_FULLTEXT_WITH_VERSION_NOTE`，基础方法引用候选。

## Zhong et al., Robot--Camera Calibration, IEEE T-RO (2023)

- DOI：`10.1109/TRO.2023.3299533`。
- 阅读重点：pp. 13–14 的微调平台、三维端点误差和误差传播；视觉检查 Figs. 13–17。
- 可支持：robot--camera calibration 的旋转误差会传播到端点位置；task-level 3-D endpoint error 是有先例的标定评价方法。
- 与 B2 的最近关系：同样使用棋盘/网格、机器人末端和人工/机械微调形成外部位置参考，因此会被审稿人用于追问 E4 读数精度。
- 不能支持：B2 的人工网格与其微调平台等精度；其 `1.8 ± 1.0 mm` 可作为我们的机器人误差地板。
- 决定：`VERIFIED_FULLTEXT`，G01 核心引用和最接近方法基准。

## Enebuse et al., Hand--Eye Accuracy Evaluation, PLOS ONE (2022)

- DOI：`10.1371/journal.pone.0273261`。
- 阅读重点：pp. 13–18 的 robot-motion count/noise studies；pp. 22–23 conclusion；关键图已视觉检查。
- 可支持：算法表现会随旋转/平移噪声和运动范围变化，不存在脱离条件的固定排名。
- 不能支持：其六个 `AX=XB` 方法等同于 B2 的 Affine/Homography/PnP；仿真 motion 数等同于物理重标定。
- 决定：`VERIFIED_FULLTEXT`，related work 中支持 geometry/condition-dependent comparison。

## Ulrich et al., Vision-Guided Robot Calibration, ISPRS JPRS (2024)

- DOI：`10.1016/j.isprsjprs.2024.09.037`；18 页 CC BY 正式全文已在线逐页核验，KIT 下载服务器不稳定，因此不保存不完整本地副本。
- 可支持：repeatability/precision 与 vision-guided absolute accuracy 的明确区分；application-level metric 可同时反映 robot kinematics、hand--eye 和 camera parameters。
- 关键新颖性边界：该文已明确使用 `end to end` 描述 simultaneous robot-kinematic/hand--eye/camera-intrinsic calibration。B2 不能声称首次端到端校准，只能定义自己的 image-to-endpoint evaluation chain。
- 不能支持：B2 已完成 robot-kinematic calibration；B2 的 manual E4 是完整 metrology evaluation。
- 决定：`VERIFIED_REMOTE_FULLTEXT`，保留 DOI/官方全文链接与引用，不保留损坏 PDF。

## Chajón et al., Photogrammetric Robot Characterization, Robotics (2026)

- DOI：`10.3390/robotics15050086`。
- 阅读重点：pp. 3、6、9–11；视觉重点 p. 10 的 measurement-chain uncertainty 讨论。
- 可支持：低成本、控制器外部的相机测量可用于平面 accuracy/repeatability 描述；但结果混合了机器人本身和相机测量链，必须避免因果分离。
- 对 E4 的直接要求：本研究有 30 repetitions × 5 poses 和额外百分表参考；B2 只有 one completed 9-target block 且人工读数，因此必须继续称 exploratory，不能作标准化 robot accuracy claim。
- 决定：`VERIFIED_FULLTEXT`，E4 限制和外部测量方法的最近基准。

## JCGM 100:2008, GUM

- DOI：`10.59161/JCGM100-2008E`；官方 BIPM/JCGM PDF。
- 阅读重点：sections 3–5、7、F.2.1–F.2.2.1；视觉检查 resolution 公式所在 PDF p. 76。
- 可支持：分辨率、重复性、有限采样和测量模型不完整均可能形成不确定度分量；测量结果应连同不确定度说明。
- 不能支持：仅由 0.5/1 mm 网格分辨率便得到 B2 的完整 uncertainty budget；无需观察者复读便确认人工读数可靠。
- 决定：`VERIFIED_FULLTEXT`，Methods/Limitations 的通用计量指南。

## 仅元数据/摘要核验的补充来源

- `ISO 9283:1998`：官方页面确认标题、版本和状态；全文付费，未下载。只能用于标准背景，不宣称 B2 符合 ISO 流程。
- Challis & Kerwin (1992)，DOI `10.1016/0021-9290(92)90040-8`：PubMed 摘要确认需要独立 check criterion 且控制点外围分布更合适。它是同行评审的一般 photogrammetry 支撑，但不是 Homography/IPPE/PnP 的直接全文替代。

## 当前仍缺的全文证据

以下主张尚不能仅靠本批论文完成引用链，进入正文前继续检索：

1. 与 B2 完全相同的 Affine vs Homography vs PnP 同条件实证比较；当前只能报告“本轮筛选语料未发现”，不能写 `first`；
2. calibration point coverage/conditioning 针对 Homography/IPPE/PnP 的正式同行评审全文；Challis 只能一般补强，Acuna 仍保留为直接预印本；
3. B2 人工网格/照片读数没有完整照片可供 observer reread 或 inter-observer study；该证据不再等待补齐，GUM 只能提供原则，正文必须保留明确限制；
4. low-cost RGB/RGB-D intrinsic/extrinsic uncertainty 到 workspace XY 的更直接传播模型，若最终选择 TIM 路线需要补强。

这些缺口标为 `NEED_SEARCH`，不允许由 AI 自动补引用。
