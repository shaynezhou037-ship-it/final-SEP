# B2 论文阶段、作者交互与版本控制协议

生效日期：2026-08-13

## 1. 权威入口

每次继续论文任务时按顺序读取：

1. `../03_manuscript_notes/PAPER_WRITING_MASTER_PLAN.md`；
2. `../03_manuscript_notes/PHASE1_PAPER_BLUEPRINT_V2_IEEE.md`；
3. `../03_manuscript_notes/claim_evidence_map_v2.csv`；
4. 当前任务对应的 `../04_writing_standards/` 标准；
5. 引用任务再读 `../05_literature_library/citation_sentence_ledger.csv`。

旧版本不参与新的科学判断。

## 2. 分阶段协作

| 阶段 | 助手负责 | 作者必须复核/决定 | 通过门槛 |
|---|---|---|---|
| 1 故事与边界 | 汇总数据、红队、定义 RQ/claim/禁止表述 | 认可 end-to-end 的限定定义、主要贡献和 E4 证据等级 | 蓝图与 claim map 签认 |
| 2 文献与 venue | 搜索官方页面、下载全文、筛选、BibTeX/句子绑定 | 目标期刊优先级；是否接受预印本；相关工作是否遗漏作者熟悉的论文 | 核心引用全文 VERIFIED；novelty gap 经检索 |
| 3 图表 | 从冻结数据生成图、caption 和数字审计 | 图是否忠实反映实验；照片/示意是否可公开 | 每张图能回答一个 RQ；正文数字可追溯 |
| 4 正文 | 依 evidence 写候选英文、维护引用和术语 | 科学判断、措辞强度、作者声音、未公开信息 | 每节通过 claim/citation/number audit |
| 5 终审投稿 | 独立红队、语言、AI 披露、模板和 PDF 渲染检查 | 作者逐条签认、作者名单/贡献、venue、披露、最终上传 | 无阻断问题；最终 PDF 逐页检查 |

## 3. 每轮固定交付格式

助手结束一轮工作时必须报告：

- **已完成**：本轮新增/更新的权威文件和结论；
- **需作者复核**：只有作者能确认的事实、照片、实验操作、目标期刊或措辞；
- **可删除**：临时缓存、重复 PDF、已被权威文件完全吸收的旧版本；
- **下一步**：一个最优先任务及所需输入。

作者可以直接用如下格式回复：

```text
复核通过：R1, R3
需修改：R2（原因……）
允许删除：D1, D2
下一步：继续阶段 2 / 进入阶段 3
```

## 4. 版本与容量规则

- 当前可编辑蓝图只保留 `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md`，小修在原文件进行并更新内文版本号；
- claim map、BibTeX、ledger、标准和正文也只保留一个 current 文件；
- 只有以下节点创建快照：scientific freeze、first full draft、submission、major revision；
- 候选 PDF、全文提取 `.txt` 和渲染页只放 `tmp/`，筛选结束删除；
- `final_papers/` 每篇只保留一个经过筛选的版本；
- 论文图片源文件与最终图分开，但不保留每次运行生成的无差异副本；
- 不删除任何 E0–E4 原始数据、正式分析代码、人工读数修订日志和唯一配置/模型文件。

## 5. 已完成的作者复核（2026-08-13）

- **R1 — 通过**：标题/叙事采用 `From Calibration Accuracy to End-to-End Robot Positioning`；end-to-end 只指已定义的 image-to-endpoint 链；
- **R2 — 通过**：E4 在叙事中使用一张主图/完整小节，但统计上仍为 exploratory、one completed nine-target block；
- **R3 — 2026-08-13 通过的检索起点，已完成**：按 TIM / IEEE Access / RA-L 三路线检索；其后形成的当前路线建议见 R6；
- **R4 — 通过**：暂留 Acuna 预印本作为 E3 线索，同时继续寻找同行评审替代；
- **R5 — 暂缓决定**：实际 AI 使用范围与披露文字在正文形成后再决定；期间继续保留事实日志，不预写最终披露结论。

## 6. 已执行删除（2026-08-13）

- **D1** `../03_manuscript_notes/PHASE1_PAPER_BLUEPRINT_V1.md`：已删除；
- **D2** `../03_manuscript_notes/claim_evidence_map_v1.csv`：已删除；
- **D3** `../03_manuscript_notes/PHASE1_IEEE_RED_TEAM_REVIEW_V1.md`：已删除，关键结论已吸收进 V2.1、master plan 和标准库。

`tmp/pdfs/literature_screening/` 中上一轮已筛选 PDF 的重复副本、提取文本和渲染页也已删除；最终 PDF 保存在 `../05_literature_library/final_papers/`。

## 7. 阶段 2 第一轮文献边界（2026-08-13）

- 已确认 endpoint calibration evaluation 有明确 T-RO 先例；
- 已确认 `end-to-end robot calibration` 有 2024 ISPRS JPRS 先例；
- 已确认低成本外部相机 robot characterization 有 2026 近邻工作；
- 当前不得使用 `first end-to-end calibration`、`first low-cost camera robot accuracy evaluation` 或 `no prior work`；
- 当前可守主张为同一受控数据协议下的 Affine/Homography/PnP 多层、几何条件化、可审计评价；
- 人工端点读数仍缺本项目 observer reread/inter-observer evidence，GUM 只能提供原则，不能自动补齐实验不确定度。
- 作者于 2026-08-14 确认 E4 照片不完整，无法进行系统性复读；取消该复读任务，不再等待补照片，但继续将人工读数不确定性列为明确限制。

## 8. 不接受的“提升录用率”手段

- 编造/补齐 E4、夸大为抓取或完整 manipulation success；
- 选择性删除不利数据而不报告规则；
- 把离线 resampling 或 video frames 写成独立物理实验；
- 伪造引用、只读摘要却声称全文核验；
- 用 AI paraphrasing 躲避检测或隐藏实际使用。

允许且推荐：更强的标题和 Fig. 1、更清晰的 end-to-end 定义、把真实 downstream case study 前置、强调公平可审计协议、公开数据/代码、补做不确定性和稳健性分析、根据 venue scope 调整叙事。

## 9. Git 基线与三刊规则冻结（2026-08-14）

- 当前公开 Git 基线为 commit `704bdda9b2dc97e0bb72facbd53c3c4eb08fb17a`（short `704bdda`），已推送到 `final-SEP` 的 `main`，本地与 `origin/main` 一致。
- 公开基线保留 E0–E4 实验数据、正式代码、配置、元数据、审计文档与写作资料；第三方论文 PDF 所在的 `05_literature_library/final_papers/` 仅本机保留，不公开再分发，引用元数据和核验记录仍纳入 Git。
- TIM、IEEE Access、RA-L 的官方规则已冻结到 `../04_writing_standards/IEEE_VENUE_RULES_AND_FIT.md`。
- **R6 — 待作者签认**：默认按 IEEE Access Research Article 推进；TIM 作为通过 measurement gate 后的冲刺路线；RA-L 暂停。
- 在 R6 签认前，可以继续做不依赖模板的统计/图表冻结，但不建立三套正文副本。
