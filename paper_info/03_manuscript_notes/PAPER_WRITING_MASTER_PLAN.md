# B2 论文写作长期计划

最后更新：2026-08-14

## 总目标

基于当前 E0-E4 的正式数据，完成一篇具有可追溯引用、正式图表、透明统计边界和完整复现资产的英文实验论文。论文采用诚实的 end-to-end robot positioning 主线：从 image/board mapping 一直追踪到机器人端点，但不暗示已完成物体检测、抓取规划、接触或抓取成功率验证。内部规划与审计文档使用中文；在目标期刊/会议尚未确定前，正文按通用 IEEE 风格和 IMRaD 结构准备。

## 五阶段工作流

### 阶段 1：冻结论文故事与证据边界

产出：

- 论文题目与一句话主张；
- RQ1-RQ4；
- 主要贡献；
- E0-E4 在正文中的角色；
- 正文和补充材料边界；
- 主张-证据映射；
- 明确禁止声称的结论；
- 图表清单和章节骨架。

状态：已完成首轮冻结和 IEEE 红队复核；根据正式论文样本，已把 V2 在原文件内更新为 v2.1，并将 E4 设为叙事终点、探索性 endpoint validation。唯一当前基准是 `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md` 和 `claim_evidence_map_v2.csv`。V1、claim map v1 和独立红队报告已于作者确认后删除。

### 阶段 2：写作基准、文献检索与引用核验

#### 2A. 高质量论文基准

先从 IEEE 官方 scope/author policy 和代表性正式全文学习标题、摘要、贡献、图表、实验梯度、限制和下游任务写法。写作基准固化在 `../04_writing_standards/IEEE_HIGH_QUALITY_PAPER_BENCHMARK.md`，不靠影响因子数字代替期刊匹配判断。

#### 2B. 引用证据库

围绕 fixed-camera/eye-to-hand positioning、Affine/Homography/PnP、planar degeneracy、calibration design、RGB-D measurement uncertainty、robot accuracy/repeatability 和 error propagation 检索正式论文和标准。每条引用必须保存 DOI/出版社页面，并记录它具体支持哪一句话。正式资料入口是 `../05_literature_library/`；候选 PDF 只在 `tmp/` 停留，筛选完成即删除。

#### 2C. 写作门槛

在 Introduction 动笔前，`citation_sentence_ledger.csv` 的正文引用必须完成全文核验，最接近本研究的 novelty gap 必须被验证而不是假设；目标 venue 的最新 scope、页数、模板、double-anonymous、AI 和 supplement 规则必须重新冻结。

状态：阶段 2 已正式开启。2A 已完成首轮；2B 已完成第一轮近邻/缺口审计：新增核验 T-RO endpoint propagation、PLOS algorithm benchmarking、ISPRS end-to-end prior art、2026 low-cost external metrology 和 JCGM GUM，并形成 `../05_literature_library/notes/PHASE2_NOVELTY_GAP_AUDIT.md`。当前不能声称首次 end-to-end calibration；可守新意是共享数据协议下的 geometry-conditioned、auditable multilevel evaluation。2026-08-14 已在 `../04_writing_standards/IEEE_VENUE_RULES_AND_FIT.md` 冻结 TIM / IEEE Access / RA-L 官方硬规则；当前建议顺序为 IEEE Access 默认、TIM 通过 measurement gate 后冲刺、RA-L 暂停。最终 venue 仍需作者签认，统计模型、figure list 与主张—证据映射冻结后才进入完整正文。

### 阶段 3：正式图表

所有正文图表必须由冻结 CSV/JSON 自动生成，不手工抄数。计划包括系统坐标链、E0 静态基线、E1 平面比较、E2 高度退化、E3 点数与分布、E4 端到端误差和模型选择框架。输出同时保留矢量格式和高分辨率位图。

Fig. 1 优先完成，必须定义本文的 end-to-end 边界；E4 使用一张完整主图收束全文，而不是藏在附带 panel 中。具体标准见 `../04_writing_standards/IEEE_HIGH_QUALITY_PAPER_BENCHMARK.md`。

### 阶段 4：完整正文

按 Title、Abstract、Introduction、Related Work、System and Methods、Results、Discussion、Limitations、Conclusion、References、Supplementary Material 顺序撰写。先保存可版本控制的 Markdown/LaTeX 源稿，再生成 DOCX。

写作采用“图表/主张先行”：先冻结 figure + caption + claim/evidence，再写 Results，再写 Methods/Discussion，最后写 Introduction/Abstract/Title。正文当前稿只保留一个可编辑版本；里程碑快照只在科学内容冻结或投稿节点创建。

### 阶段 5：全链路审计、AI 与自然语言审查

阶段 5 不以一次“润色”代替科研核验，固定分为四道关卡：

#### 5A. 科学与数据一致性审计

- 所有数字可追溯到正式数据；
- 所有引用真正支持对应句子；
- 标定、验证和测试集合未混用；
- 重复帧/离线子集未被写成独立物理样本；
- E4 提前停止和人工读数修订透明披露；
- 图、表、正文数字完全一致；
- 结论没有超出硬件、工作区和实验条件；
- 统计单位、样本数、置信区间和 exploratory/confirmatory 标签一致。

#### 5B. AI 辅助红队审查

用与正文撰写分离的审查提示词逐句检查：主张是否越界、数字是否冲突、引用是否存在且真正支持句子、术语是否前后一致、是否把相关性写成因果、是否把离线样本或重复帧写成独立实验。AI 输出只作为问题清单，不自动覆盖正文；每一项修改都必须回到原始数据、代码或正式文献核验。

#### 5C. 自然语言与 IEEE 文风审查

检查英文语法、逻辑衔接、冗余、中文式英语、主客体不清、时态、缩写首次定义、图表自解释性，以及 Abstract/Conclusion 是否包含正文未证明的强结论。禁止 AI 生成或“补全”未经 DOI/出版社页面核验的参考文献。

#### 5D. 人工作者终审与版式检查

- 作者逐条签认主张—证据映射、人工读数修订、E4 提前停止和限制；
- 根据最终目标期刊套用其官方 IEEE 模板，而不是仅凭“IEEE-style”推测格式；
- 最终 DOCX/PDF 完成逐页渲染、公式、字体、图分辨率、交叉引用和补充材料 README 检查；
- 在 Acknowledgment 中按 IEEE 规则披露生成式 AI 的实际用途、系统名称和涉及章节；不把 AI 列为作者，也不把“AI 审查通过”作为科研有效性证明。

### AI 使用披露占位文本（投稿前按实际情况更新）

> During the preparation of this work, the authors used [system and version] to assist with [outlining/language drafting/editing/code-assisted figure preparation/consistency checking] in [exact sections]. All AI-assisted outputs were checked against the source data and cited literature, revised by the authors, and remain the authors' responsibility.

该文字放在 Acknowledgment，而不是新增一个名为“AI Review”的科研章节。系统/版本、具体章节和使用范围必须在投稿前按真实过程填写，不能现在虚构。

## 跨会话继续规则

每次恢复论文任务时，先读取本文件，再读取当前阶段的最新版文件。未经明确讨论，不改变以下冻结原则：

1. B2 标定模型比较是论文主线。
2. 实际 E0-E4 的内容优先于早期《计划.docx》中的旧实验编号。
3. E1-E3 是视觉模型主体，E0 是误差解释基础，E4 是全文叙事终点和探索性 end-to-end endpoint validation；叙事地位突出不等于证据等级升级。
4. 不编造未完成实验，不把 E4 写成完成 108 次。
5. 不把 Oracle 称为纯机械臂误差。
6. 不把离线重采样称为独立物理重复。
7. 不声称完成了双相机融合端到端比较或抓取成功率验证。
8. E1 的 36 个 held-out 点是同一平面采集中的空间验证位置，不表述为 36 次独立物理重复。
9. E4 Oracle 只称为该次实验中的 observed downstream reference；由于 registration 的独立检查有限且误差较大，不称为稳定的“误差地板”。
10. “12–16 个点趋于饱和”只作为当前数据集的条件性观察，不写成普适设计定律。
11. E4 现有照片覆盖不完整，无法执行系统性的照片盲复读或双观察者复读；该项不再作为阶段 2/正文写作门槛。人工网格读数的分辨率、修订记录和潜在观察者误差必须作为 measurement-chain limitation 披露，不能用缺失照片补造复读结果。

## 人机协作与文件控制

详细协议见 `../00_planning_and_audit/PAPER_COLLABORATION_WORKFLOW.md`。每轮论文工作固定给出四类结果：

1. 本轮已完成并可直接保留的文件；
2. 需要作者复核/签认的科学判断；
3. 复核后可以删除的旧版本或临时文件；
4. 下一轮唯一优先任务和进入条件。

不使用 `final_v2_revised_latest` 式文件名。标准、蓝图、BibTeX 和 ledger 原文件更新；只有数据冻结、投稿或大修前才保存里程碑快照。未经作者确认，不删除原始实验数据、正式代码、修订审计记录或唯一证据文件。

## 当前冻结数据修订

E4 使用修订 ID `20260813_confirmed_manual_reading_corrections_v2`。三条人工 X 读数已依据实验者原始证据确认并保留机器可读审计记录。后续分析不得回退到修订前的 8.5/10 mm T05 异常结论。
