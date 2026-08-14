# B2 论文写作长期计划

最后更新：2026-08-14

## 总目标

基于 E1/E2/E6 的共享物理观测证据，完成一篇围绕“目标离开标定平面后需要多少几何信息，以及第二台相机何时真正增加信息”的英文实验论文。E1→E2→E6 是唯一核心链：planar mapping → single-view PnP → estimate fusion versus stereo parallax。E6 的核心比较统一输出 board XYZ，并以五次 physical rebuild 做 paired contrasts。E3/E5 是 supporting validity checks，E4 是有限 application-side check，E0 完整结果进 Supplement 但关键 limitation 留正文，E7 不进入投稿稿件。内部规划与审计文档使用中文；正文按通用 IEEE 风格和 IMRaD 结构准备。

## 五阶段工作流

### 阶段 1：冻结论文故事与证据边界

产出：

- 论文题目与一句话主张；
- RQ1-RQ2；
- 两项主要贡献；
- E0–E7 的 core/supporting/supplement/excluded 角色；
- 正文和补充材料边界；
- 主张-证据映射；
- 明确禁止声称的结论；
- 图表清单和章节骨架。

状态：2026-08-14 作者决定不重搭系统，并在严格 IEEE reviewer audit 后将蓝图更新为 v2.4。E1/E2 合并回答 planar-to-off-plane information sufficiency，E6 回答 second estimate versus second-view geometry；针对审稿意见已补 single-PnP XYZ、equal/LOO XYZ 与 stereo 的同维度消融及 rebuild-level paired contrasts。E3/E5/E4 不再各设 RQ，E7 退出投稿包。唯一当前方向基准是 `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md`；旧 claim map 的数字仍有效，但正文只提升与两个 RQ 直接相关的核心主张。

### 阶段 2：写作基准、文献检索与引用核验

#### 2A. 高质量论文基准

先从 IEEE 官方 scope/author policy 和代表性正式全文学习标题、摘要、贡献、图表、实验梯度、限制和下游任务写法。写作基准固化在 `../04_writing_standards/IEEE_HIGH_QUALITY_PAPER_BENCHMARK.md`，不靠影响因子数字代替期刊匹配判断。

#### 2B. 引用证据库

围绕 fixed-camera/eye-to-hand positioning、Affine/Homography/PnP、planar degeneracy、calibration design、RGB-D measurement uncertainty、robot accuracy/repeatability 和 error propagation 检索正式论文和标准。每条引用必须保存 DOI/出版社页面，并记录它具体支持哪一句话。正式资料入口是 `../05_literature_library/`；候选 PDF 只在 `tmp/` 停留，筛选完成即删除。

#### 2C. 写作门槛

在 Introduction 动笔前，`citation_sentence_ledger.csv` 的正文引用必须完成全文核验，最接近本研究的 novelty gap 必须被验证而不是假设；目标 venue 的最新 scope、页数、模板、double-anonymous、AI 和 supplement 规则必须重新冻结。

状态：阶段 2 已正式开启。当前不能声称首次 end-to-end calibration、首次双相机融合或首次角度效应；可守新意收束为：在共享 paired physical observations 上建立 planar mapping → single-view PnP → estimate fusion/stereo 的几何信息层级，并实证区分“第二个估计”与“第二视图几何”。2026-08-14 已冻结 TIM / IEEE Access / RA-L 官方硬规则；当前建议顺序仍为 IEEE Access 默认、TIM 通过 measurement gate 后冲刺、RA-L 暂停。

### 阶段 3：正式图表

所有正文图表必须由冻结 CSV/JSON 自动生成，不手工抄数。正文只计划四张主图：系统与 geometric-information hierarchy；E1+E2 planar-to-off-plane；E6 second estimate versus stereo parallax；E4 exploratory application-side transfer。E0/E3/E5/angle 完整结果进 Supplement，E7 不生成投稿图。输出同时保留矢量格式和高分辨率位图。

Fig. 1 优先完成，必须让读者在 30 秒内看出 planar Homography、single-view PnP、estimate fusion 与 stereo parallax 的信息差异。Fig. 3/E6 是全文论证峰值：左侧 XY height curves，右侧 strict same-output XYZ/3-D ablation，并在 caption/表中给 paired rebuild sign counts；E4 图明确标为 supporting check，而不是 E6 endpoint validation。

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
- E5 simulated effective resolution、检测失败与 survivorship boundary 同时披露；
- E6 estimate fusion/stereo、静态同步、Z=0-derived geometry 和 no endpoint propagation 边界同时披露；
- E6 的 single PnP、estimate fusion 与 stereo 使用统一 XYZ 输出和 XY/Z/3-D 指标，统计单位保持为 physical rebuild；
- E6 角度结果只作为 identifiability/confounding audit，不出现 causal angle claim；
- E7 不出现在投稿正文、Appendix 或 Supplement inventory；
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

1. B2 的唯一主线是 geometric-information sufficiency：E1/E2 的 planar-to-off-plane transition 加上 E6 的 second estimate versus stereo parallax。
2. 实际 E0–E7 内容优先于早期《计划.docx》，但“仓库中存在”不等于“投稿稿件必须包含”。
3. E1/E2/E6 是 core；E3/E5 是 supporting validity checks；E4 是有限 application-side check；E0 完整诊断进 Supplement 且关键 limitation 留正文；E7 excluded from submission。
4. 不编造未完成实验，不把 E4 写成完成 108 次。
5. 不把 Oracle 称为纯机械臂误差。
6. 不把离线重采样称为独立物理重复。
7. 不声称完成了双相机融合端到端比较或抓取成功率验证。
8. E1 的 36 个 held-out 点是同一平面采集中的空间验证位置，不表述为 36 次独立物理重复。
9. E4 Oracle 只称为该次实验中的 observed downstream reference；由于 registration 的独立检查有限且误差较大，不称为稳定的“误差地板”。
10. “12–16 个点趋于饱和”只作为当前数据集的条件性观察，不写成普适设计定律。
11. E4 现有照片覆盖不完整，无法执行系统性的照片盲复读或双观察者复读；该项不再作为阶段 2/正文写作门槛。人工网格读数的分辨率、修订记录和潜在观察者误差必须作为 measurement-chain limitation 披露，不能用缺失照片补造复读结果。
12. 不重新搭建物理系统；任何需要新角度、真实相机移动、原生分辨率模式或 E6 endpoint propagation 的主张均保留为 future work，不再用仿真填入本稿。
13. 两相机 angle/geometry 数据只有两个固定布局。`E6_ANGLE_IDENTIFIABILITY_AUDIT.md` 是唯一角度结论入口；禁止把 pooled correlation 写成 angle causality 或 optimal view recommendation。
14. E6 可说 calibrated parallax 增加了几何信息；不可说 two cameras are universally better。E6 未进入 E4，因此不可说 dual-camera end-to-end validation。
15. 标题、摘要和贡献只出现 E1/E2/E6 的核心信息链；E3/E5/E4 不能重新膨胀成并列故事，E7 不进入投稿包。
16. E2 PnP 不使用真实高度标签或额外高度先验；真实高度只用于评分。未预定义应用容差时，不从 height curve 事后命名“失效阈值”。
17. E6 不要求加入 `fusion + stereo`：它不是独立信息条件，会复用同一图像对并引入额外融合规则；如未来研究该算法，必须另行定义训练与验证协议。

## 人机协作与文件控制

详细协议见 `../00_planning_and_audit/PAPER_COLLABORATION_WORKFLOW.md`。每轮论文工作固定给出四类结果：

1. 本轮已完成并可直接保留的文件；
2. 需要作者复核/签认的科学判断；
3. 复核后可以删除的旧版本或临时文件；
4. 下一轮唯一优先任务和进入条件。

不使用 `final_v2_revised_latest` 式文件名。标准、蓝图、BibTeX 和 ledger 原文件更新；只有数据冻结、投稿或大修前才保存里程碑快照。未经作者确认，不删除原始实验数据、正式代码、修订审计记录或唯一证据文件。

## 当前冻结数据修订

E4 使用修订 ID `20260813_confirmed_manual_reading_corrections_v2`。三条人工 X 读数已依据实验者原始证据确认并保留机器可读审计记录。后续分析不得回退到修订前的 8.5/10 mm T05 异常结论。
