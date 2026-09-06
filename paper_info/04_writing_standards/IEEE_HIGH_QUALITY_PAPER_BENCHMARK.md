# IEEE 高质量实验论文基准：B2 写作与图表要求

最后更新：2026-08-13  
用途：在正文动笔前冻结“什么是好论文”的项目内标准。该文件是写作基准，不等同于目标期刊已确定。

## 1. 选刊与基准原则

不能只按影响因子挑论文。影响因子会变化，而且高影响力但不匹配 scope 的期刊不会提高录用率。本项目采用三重筛选：

1. **期刊声誉/审稿标准**：优先 IEEE 正式期刊与领域公认期刊；
2. **与本研究的结构相似度**：系统型实验、标定、测量、RGB-D/eye-to-hand、端点验证；
3. **可学习性**：全文可核验，方法、图表、限制和贡献边界清楚。

IEEE 的期刊搜索页可查看当前 bibliometric scores；投稿前再核验当年的 Impact Factor，不把今天的指标写死在内部故事中：<https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/tools-for-ieee-authors/find-a-journal/>。

当前 venue 判断：

| Venue | 本项目用途 | 当前匹配判断 |
|---|---|---|
| IEEE Transactions on Instrumentation and Measurement (TIM) | 测量设计、校准、误差与不确定性基准 | 条件冲刺；只有通过 measurement gate 才升级为首选 |
| IEEE Access | 完整实验比较、应用导向、可复现数据 | 当前默认；仍要求明确 advance、高技术标准和由数据支持的结论 |
| IEEE Robotics and Automation Letters (RA-L) | 机器人叙事、Fig. 1、端到端任务收束 | 当前投稿路线暂停；只保留为叙事/图表基准 |
| IEEE Sensors Journal | 传感器系统和数据处理 | 仅在双相机/传感器测量贡献足够突出时考虑 |
| IEEE TPAMI | 经典视觉论文的表达与论证基准 | 只用于学习，不作为当前投稿目标；本项目尚无相应算法/理论创新 |

官方约束：TIM 强调推进 measurement science、methods、functionality 或 applications；IEEE Access 要求实验和统计达到高技术标准且结论由数据支持；RA-L 正文 6 页、最多 8 页，附录也计入，不能用 supplemental text 绕过页数限制。

三刊 2026 官方硬规则、费用、匿名方式、补充材料政策及 B2 适配门槛的唯一当前入口是 `IEEE_VENUE_RULES_AND_FIT.md`；本文件不再重复维护易变细节。

## 2. 已全文阅读的论文样本

完整 PDF 保存在 `../05_literature_library/final_papers/`，逐篇用途和引用状态保存在 `../05_literature_library/notes/FINAL_PAPER_READING_NOTES.md`。

### A. EasyHeC — IEEE RA-L, 2023

可学习之处：

- Fig. 1 在第一页同时回答“问题是什么—方法是什么—下游任务是什么”；
- Introduction 从机器人操作的实际后果进入 hand–eye calibration，而不是先堆算法史；
- 实验按 synthetic → public real-world data → real-robot high-precision targeting → ablation → application 逐级增强；
- 高精度 targeting 被放在叙事关键位置，但作者仍明确说它只是 preliminary indication，而不是夸大为完整操作成功率。

对 B2 的直接要求：学习其第一页信息密度，但不照搬 endpoint-centered story。Fig. 1 必须画出 planar Homography → single-view PnP → estimate fusion/stereo 的信息层级；E4 只作为 application-side supporting branch，并写清 one completed block、9 targets、manual reading 和 early stopping。

### B. Zhong et al. — IEEE RA-L, 2020

可学习之处：

- 首段直接给出任务失败模式与校准必要性；
- 三项贡献是具体技术/协议，不是“做了大量实验”式空话；
- 仿真、真实机器人平台和下游 needle handover case study 形成证据梯度；
- 方法局限在 Conclusion 中明确列出，没有用未来工作掩盖当前边界。

对 B2 的直接要求：Introduction 要从“目标离开标定平面后需要什么几何信息”切入，并在第一页引出“第二个估计不等于第二视图几何”。E4 的 downstream chain 只在 supporting application check 中定义，未覆盖的检测/抓取/接触不能暗示已经验证。

### C. Wu et al. — IEEE TIM, 2020

可学习之处：

- Table I 先建立相关方法的结构化比较，再进入公式；
- 理论、协方差/不确定性、仿真和多种机器人实验互相对应；
- 硬件照片、坐标关系、算法伪代码、统计表和轨迹验证各司其职。

需要避免：长推导直接塞进结果叙事会严重降低可读性。B2 若投 TIM，只保留主文理解必需的定义，完整推导或全量协议进入允许的 Appendix/Supplement。

### D. Rustler et al. — IEEE Access, 2025

可学习之处：

- 证明“没有新算法的比较论文”仍可成立：新意来自公平协议、多个实际场景、统一指标和公开 12,000+ RGB-D frames；
- Table I 写硬件规格，Table II 写实际采集设置，避免把厂家参数与实验参数混为一谈；
- 每一场景先给 setup，再给定量结果、可视化和场景内总结，最后才形成条件性设备建议；
- 结论按应用距离和场景限定，不给脱离条件的统一冠军。

对 B2 的直接要求：原创性重点是共享观测下的 controlled geometric-information hierarchy，不伪装成新算法。E1/E2/E6 是 core；E3/E5/E4 是 supporting；E0 的完整诊断进 Supplement 且关键 limitation 留正文；E7 excluded。分级必须在 Table II 明示。

### E. Collins and Bartoli — IJCV, 2014（IPPE 原始论文）

可学习之处：

- 明确定义 planar pose estimation 的歧义与适用情形；
- 理论性质、算法复杂度、仿真和真实数据互相核对；
- 论文长是因为它真正提供了理论和广泛比较，不应模仿其篇幅而缺少相同证据密度。

对 B2 的直接要求：OpenCV `SOLVEPNP_IPPE` 的方法说明必须引用原始 IPPE 论文；不能把 PnP 写成完整 hand–eye calibration 的同义词。

### F. Acuna and Willert — arXiv preprint, 2018

可学习之处：

- 直接研究 control-point configuration、condition number、Homography/IPPE/EPnP 精度与点数的关系；
- 图中同时呈现 well-conditioned、ill-conditioned 和理想 square configuration，适合支持 E3 的图表思路；
- 结果强调点的空间分布可能比单纯增加数量更重要，与 E3 高度相关。

限制：目前只核验到预印本，未确认正式同行评审版本。可以作为检索线索或谨慎引用，但投稿前优先寻找正式发表的替代证据。

### G. Zhang — IEEE TPAMI, 2000（本地为扩展作者版）

可学习之处：

- 方法按 closed-form initialization → distortion estimation → nonlinear refinement 清晰展开；
- 单列 degenerate configurations、simulation、real data 和 sensitivity；
- 结果不是只报平均误差，还讨论模型板非平面等系统误差。

版本说明：本地 22 页 PDF 是作者扩展技术报告，正式 TPAMI 论文为 vol. 22, no. 11, pp. 1330–1334，DOI `10.1109/34.888718`。正式引用使用期刊元数据，不把 22 页扩展版误写成出版社版本。

## 3. B2 正文必须达到的结构基准

### Title

- 说明研究对象、关键比较和任务层级；
- 可以用 `End-to-End Robot Positioning`，但不能用 `Complete Manipulation` 或暗示抓取成功率；
- 不把 `PnP` 等同于 `full 3-D calibration`。

### Abstract

IEEE 通用要求：单段、≤250 words、自包含、无引用/脚注/未定义缩写/显示公式，含 3–5 个关键词。B2 必须按五句功能组织：

1. 实际问题：平面标定分数未必反映机器人端点；
2. 缺口：同一系统中缺少从 planar/off-plane/coverage 到 endpoint 的公平比较；
3. 方法与真实 n：36 planar locations、两相机、五次 physical rebuild 和 E6 paired static views；
4. 关键数字：只选 2–3 个最能回答 RQ 的结果；
5. 条件性结论与 E6 static-target/Z=0-derived geometry/no-endpoint-propagation 边界。E3/E5/E4/E7 不在摘要中扩展为并列结果。

### Introduction

Introduction 的核心任务不是泛泛介绍领域，而是建立一条可检验的论证链，回答“为什么这个问题值得研究”。应用价值是其中的重要证据：它说明一个几何、估计或测量问题会影响哪些真实任务，以及问题解决后谁会受益；但应用场景不能替代研究缺口，也不能暗示尚未验证的系统能力。

通用功能主线为：**背景（context） → 为什么重要（application/why it matters） → 已有方法（what is known） → 尚存缺口（gap） → 研究问题（research question） → 研究路径（approach） → 可核验贡献（contributions）**。具体写作时应完成以下功能：

1. **背景 / Context**：界定问题空间、对象和任务层级，例如 homography、planar pose estimation 及其在计算机视觉与机器人系统中的位置；避免从“近年来人工智能快速发展”等空泛宏观叙述起笔。
2. **应用 / Why it matters**：用与本文证据边界一致的任务说明实际后果，例如 fiducial-marker pose estimation、AR、robot localization、camera calibration 和 planar tracking。应用段必须回答“这个问题会影响什么”，而不是简单罗列场景；若本文只验证静态定位或 supporting application check，不得扩写为完整检测、抓取或操控性能。
3. **已有方法 / What people already know**：概括现有方法如何处理该问题、已建立哪些结论，并只保留导向本文缺口所必需的文献脉络；详细分类与比较移至 Related Work。
4. **缺口 / Problem or gap**：明确指出现有知识为何不足。例如，已知 control-point configuration 会影响 homography 或 pose estimation，但不同 configuration 下的 robustness 如何变化仍缺乏系统、受控且公平的分析。缺口必须由已核验文献支持，不能只靠“研究较少”之类判断。
5. **研究问题 / Research question**：把缺口收束为本文实际能够回答的问题，并与后文 RQ、指标、实验和图表一一对应。
6. **研究路径 / Approach**：用少量句子预告如何回答问题，例如分析 conditioning/robustness、比较不同 control-point configurations，并用 simulation、real experiment 或受控重建验证；不在 Introduction 展开方法细节。
7. **贡献 / Contributions**：列出具体、可核验且彼此区分的技术或实证贡献。贡献应写成“建立了什么比较/证据/结论”，而不是“进行了大量实验”，也不得把应用动机写成已验证贡献。

对 B2 正文，上述七项功能压缩并固定为五段，而不是机械写成七段：

1. **任务后果与应用价值**：从真实任务中误差传播或失败后果切入，建立 planar mapping/pose 与 robot positioning、calibration 等应用的联系，回答 why it matters。
2. **第一层已有认识与缺口**：交代 planar 方法已能解决什么，随后指出 planar-to-off-plane 的信息缺口。
3. **第二层已有认识与缺口**：区分 second estimate 与真正的 second-view geometry，说明现有处理为什么仍不能回答本文问题。
4. **研究问题与 controlled evaluation design**：明确本文比较什么、在什么条件下比较、使用什么证据回答 RQ；只做方法预告。
5. **两项可核验贡献**：贡献与 RQ、核心结果和证据边界直接对应，不把 E4 supporting branch 或未覆盖的 downstream chain 提升为核心贡献。

自检时用一句话复述全文入口：**背景 → 为什么重要 → 现在做到哪了 → 还缺什么 → 我研究什么 → 我怎么研究 → 我贡献什么**。若其中任一箭头无法自然成立，说明 Introduction 仍存在跳步、应用堆砌或贡献越界。

### Related Work

按问题组织，不按作者流水账：planar mapping and pose；hand–eye/eye-to-hand calibration；calibration design/degeneracy；downstream/end-to-end evaluation。每段结尾写本项目的明确缺口。

### Methods

审稿人必须能从文中恢复：硬件和版本、坐标系、板尺寸、相机内参来源、三种模型的输入输出、calibration/validation 分割、每个 E 的独立单位、排除/失败规则、E4 人工读数与修订规则。

### Results

按 RQ1–RQ2 组织两个核心结果节，再设一个简短 `Supporting Validity Checks` 和一个 `Exploratory Application-Side Check`；不按 E 编号逐项写项目报告。每节遵循：问题 → 图/表 → 主结果 → 不确定性 → 一句边界。

### Discussion and Limitations

必须优先回答：目标离面后为何二维平面信息不足；为什么 estimate fusion 不等于 stereo information；结果只适用于哪些静态 low-cost eye-to-hand 条件。随后用较短篇幅说明 calibration coverage、saved-image downsampling、angle confounding 和 E4 measurement-chain 限制。E7 只可作为 future work 名称，不报告仿真数字。

## 4. 图表设计基准

统一规则：

- 每张核心结果图只回答一个 RQ；系统图和 E4 supporting 图必须有单一明确目的；caption 自包含并写 n、误差定义、误差带和 exploratory/confirmatory；
- 模型颜色全篇固定，camera/rebuild 用线型或透明度编码；使用色盲友好配色；
- 连续高度数据不用柱状图；E2 显示每个 rebuild 细线和跨 rebuild 汇总粗线；
- 不用 3-D 柱图、彩虹色图、仅靠颜色区分、没有单位的轴、被截断且未标识的 y 轴；
- 数据图优先导出 PDF/SVG，照片 ≥300 dpi；最终按 IEEE 双栏尺寸检查 100% 缩放下的字体；
- 图中任何手工标注不得改变数据；数值图必须从冻结 CSV/JSON 自动生成。

建议主图：

1. **Fig. 1**：实物照片、坐标系与 planar Homography → single-view PnP → estimate fusion/stereo hierarchy；E4 仅作小型 supporting branch；
2. **Fig. 2**：E1 planar paired errors + E2 两相机 height curves，合并回答 RQ1；
3. **Fig. 3**：E6 左 panel 为 single-camera/equal/LOO-weighted PnP 与 stereo 的 XY height curves，右 panel 为统一 XYZ 输出的 ihawk1/ihawk2/equal/LOO-weighted/stereo 3-D RMSE；caption/表给出 paired rebuild sign counts，回答 RQ2；不放 angle panel；
4. **Fig. 4**：E4 target-paired endpoint error，明确 `not an E6 endpoint validation`。

E0/E3/E5/angle 图进入 Supplement；E7 不进入投稿图表资产。

## 5. “取长补短”的执行方式

取：EasyHeC 的第一页任务链；Zhong 的下游 case study；Wu 的测量严谨性；Rustler 的公平比较和条件性建议；Acuna 的点分布可视化；Zhang/Collins 的退化与适用边界。

不取：只靠定性照片证明精度；把应用 demo 当确认性实验；过度堆公式；逐作者相关工作；用厂家规格替代实测；把大量离线样本写成物理重复；为了“像高水平论文”而制造不存在的创新或数据。

## 6. 写作前通过门槛

- [x] TIM、IEEE Access、RA-L 的当年 scope、模板、页数、anonymous review 和 supplement 规则已于 2026-08-14 重新核验；正式投稿前仍须复核；
- [ ] novelty gap 至少由 8–12 篇全文论文支撑，不只看摘要；
- [ ] `citation_sentence_ledger.csv` 中正文引用状态均为 `VERIFIED`；
- [ ] Fig. 1 information hierarchy、Fig. 2 E1+E2 和 Fig. 3 E6 在 Introduction 定稿前冻结；
- [ ] 核心数字与冻结源文件及 `no_rebuild_evidence_manifest.json` 一致；`claim_evidence_map_v2.csv` 的旧 RQ/图号角色在使用前完成迁移；
- [ ] 作者签认 end-to-end 定义和所有 E4 限制；
- [ ] AI 使用日志已持续记录，引用列表未交给生成式 AI 自动改写。

## 7. 官方依据

- IEEE journal article structure：<https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-the-text-of-your-article/structure-your-article/>
- IEEE submission/AI policy：<https://journals.ieeeauthorcenter.ieee.org/become-an-ieee-journal-author/publishing-ethics/guidelines-and-policies/submission-and-peer-review-policies/>
- IEEE Editorial Style Manual：<https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Editorial-Style-Manual-for-Authors.pdf>
- IEEE supplementary materials：<https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/prepare-supplementary-materials/>
- TIM scope：<https://ieee-ims.org/publication/ieee-tim>
- IEEE Access preparation criteria：<https://ieeeaccess.ieee.org/authors/preparing-your-article/>
- RA-L information for authors：<https://www.ieee-ras.org/publications/ra-l/ra-l-information-for-authors/>
- 三刊规则与适配冻结：`IEEE_VENUE_RULES_AND_FIT.md`
