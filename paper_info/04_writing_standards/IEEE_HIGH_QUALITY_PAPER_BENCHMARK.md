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

对 B2 的直接要求：Fig. 1 必须画出 image-to-endpoint 链；E4 应作为故事终点，但 caption 和正文必须写清 one completed block、9 targets、manual reading 和 early stopping。

### B. Zhong et al. — IEEE RA-L, 2020

可学习之处：

- 首段直接给出任务失败模式与校准必要性；
- 三项贡献是具体技术/协议，不是“做了大量实验”式空话；
- 仿真、真实机器人平台和下游 needle handover case study 形成证据梯度；
- 方法局限在 Conclusion 中明确列出，没有用未来工作掩盖当前边界。

对 B2 的直接要求：Introduction 要从“平面成绩是否能传到机器人端点”这一真实问题切入；end-to-end 的每个组成环节都要定义，未覆盖的检测/抓取/接触不能暗示已经验证。

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

对 B2 的直接要求：我们的原创性重点也应是公平、可审计、多层级和 geometry-conditioned，不伪装成新算法。E1–E4 的统计单位和真实采集设置必须分表说明。

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
3. 方法与真实 n：两相机、五次 rebuild、36 planar locations、E3 offline resampling、E4 one completed block；
4. 关键数字：只选 2–3 个最能回答 RQ 的结果；
5. 条件性结论和 E4 exploratory 边界。

### Introduction

固定为五段：任务后果 → 方法选择缺口 → 现有评价为什么不够 → 我们的 end-to-end evaluation design → 三项可核验贡献。禁止从“近年来人工智能快速发展”开始。

### Related Work

按问题组织，不按作者流水账：planar mapping and pose；hand–eye/eye-to-hand calibration；calibration design/degeneracy；downstream/end-to-end evaluation。每段结尾写本项目的明确缺口。

### Methods

审稿人必须能从文中恢复：硬件和版本、坐标系、板尺寸、相机内参来源、三种模型的输入输出、calibration/validation 分割、每个 E 的独立单位、排除/失败规则、E4 人工读数与修订规则。

### Results

按 RQ1–RQ4，不按脚本/日期写。每节遵循：问题 → 图/表 → 主结果 → 不确定性/跨 rebuild 差异 → 一句边界。Discussion 才解释原因，不在 Results 中制造未经验证的机制。

### Discussion and Limitations

必须回答：何时 planar model 足够；何时 off-plane robustness 重要；为什么 coverage 不能简化为点数；为何视觉误差不会一比一传到端点；结果能推广到哪里。E4 early stop、registration held-out 检查有限、人工网格读数和未验证抓取成功率必须出现。

## 4. 图表设计基准

统一规则：

- 每张主图只回答一个 RQ；caption 自包含并写 n、误差定义、误差带和 exploratory/confirmatory；
- 模型颜色全篇固定，camera/rebuild 用线型或透明度编码；使用色盲友好配色；
- 连续高度数据不用柱状图；E2 显示每个 rebuild 细线和跨 rebuild 汇总粗线；
- 不用 3-D 柱图、彩虹色图、仅靠颜色区分、没有单位的轴、被截断且未标识的 y 轴；
- 数据图优先导出 PDF/SVG，照片 ≥300 dpi；最终按 IEEE 双栏尺寸检查 100% 缩放下的字体；
- 图中任何手工标注不得改变数据；数值图必须从冻结 CSV/JSON 自动生成。

建议主图：

1. **Fig. 1**：实物照片 + image-to-endpoint 坐标链 + E1–E4 证据地图；
2. **Fig. 2**：E1 paired target error/ECDF，而不是三个均值柱；
3. **Fig. 3**：E2 两相机高度曲线，每个 rebuild 可见；跨度过大时使用分面或明确的 inset，避免用单轴压扁 PnP；
4. **Fig. 4**：E3 `point count × distribution × model`，同时显示 failure/extreme cases；
5. **Fig. 5**：E4 target-paired endpoint error，并分解 vision、downstream residual 和 E2E；
6. **Fig. 6**：只总结数据支持的条件性模型选择，不发明普适高度阈值。

## 5. “取长补短”的执行方式

取：EasyHeC 的第一页任务链；Zhong 的下游 case study；Wu 的测量严谨性；Rustler 的公平比较和条件性建议；Acuna 的点分布可视化；Zhang/Collins 的退化与适用边界。

不取：只靠定性照片证明精度；把应用 demo 当确认性实验；过度堆公式；逐作者相关工作；用厂家规格替代实测；把大量离线样本写成物理重复；为了“像高水平论文”而制造不存在的创新或数据。

## 6. 写作前通过门槛

- [x] TIM、IEEE Access、RA-L 的当年 scope、模板、页数、anonymous review 和 supplement 规则已于 2026-08-14 重新核验；正式投稿前仍须复核；
- [ ] novelty gap 至少由 8–12 篇全文论文支撑，不只看摘要；
- [ ] `citation_sentence_ledger.csv` 中正文引用状态均为 `VERIFIED`；
- [ ] Fig. 1 草图和 Fig. 3/E2 主图先于 Introduction 定稿；
- [ ] 关键数字与 `claim_evidence_map_v2.csv` 一致；
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
