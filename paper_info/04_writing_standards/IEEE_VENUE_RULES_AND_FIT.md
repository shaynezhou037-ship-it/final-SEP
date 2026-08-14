# B2 目标期刊规则冻结与适配门槛

核验日期：2026-08-14  
适用范围：IEEE Transactions on Instrumentation and Measurement（TIM）、IEEE Access、IEEE Robotics and Automation Letters（RA-L）  
状态：官方硬规则已冻结；最终投稿期刊仍需作者签认  

## 1. 冻结原则

1. 本文件只把期刊官网明确写出的内容记为“官方规则”；项目适配度、录用风险和路线排序均标为“本项目判断”。
2. 规则按 2026-08-14 可访问的官方页面冻结。模板、费用、审稿匿名方式和补充材料政策属于易变信息，正式投稿前必须逐项复核。
3. 不以影响因子代替 scope 匹配，也不通过夸大 `end-to-end`、补造 E4 或隐藏人工读数限制提高表面新颖性。
4. 三个期刊均要求原创性、技术正确性、充分相关工作和由证据支持的结论；“开放获取”或“快速审稿”不等于低门槛。

## 2. 官方硬规则对照

| 项目 | TIM | IEEE Access | RA-L |
|---|---|---|---|
| Scope | 推进 instrumentation and measurement 的理论、方法、系统、信息处理或应用；必须明确 I&M novelty，并放入 I&M 文献语境 | 覆盖全部 IEEE fields of interest，特别接纳跨学科、应用导向、新实验或测量技术 | 机器人与自动化领域及时、简洁的创新研究思想、理论结果和应用案例 |
| 推荐稿型 | Regular Paper | Research Article | Letter |
| 初投稿格式 | IEEE 双栏 Transactions；单个自包含、未加密 PDF，≤20 MB；regular paper 至少 5 页 | 强制 IEEE Access 双栏单倍行距模板；Word/LaTeX 源文件与 PDF 内容一致，文件 ≤40 MB | 初稿用 IEEE/RAS conference 双栏格式；留作者栏位置但移除作者信息 |
| 篇幅 | Regular paper 无投稿页数上限，但当前链接的 overlength agreement 以 8 个出版页为免费额度，之后强制收费；正式投稿前重核费用 | 无硬性页数上限；强烈建议正文少于 20 页，超过 20 页须先获 EiC 许可；Appendix/Supplement 不计入这一询问阈值 | 6 页；最多增加 2 页，每页 USD 175；图、表、参考文献和 Appendix 全部计入最多 8 页 |
| Supplement/data/code | 可交 reviewed supplementary text；主文必须自包含。支持 multimedia 和 IEEE DataPort 数据集关联 | 允许 supplementary material（code、data 等）并可随文发布；视频须随初稿送审 | 禁止用 supplemental text/figures 扩展正文；允许合规 multimedia，数据集应在线发布并在参考文献中以 URL 引用 |
| 匿名审稿 | 官网要求审稿人不公开身份，但当前作者指南未要求去除作者信息；按非双盲稿准备，提交前在 portal 再核对 | Single-anonymized；至少 2 名独立审稿人；作者身份对审稿人可见 | 自 2025-02-01 起为 soft double-anonymous；初稿必须去除作者信息并谨慎处理自引 |
| 决策特点 | Accept / Minor Revision / Reject and Resubmit / Reject；一篇稿件最多一次 Major Revision | Binary accept/reject；若允许更新后重投，只能重投一次 | 目标是在 6 个月内给出最终决定；期刊称平均 submission-to-ePub 约 4 个月 |
| OA | Hybrid；默认传统订阅。2026 可选 OA APC 为 USD 2,800，另计税费；超页费另算 | Gold fully OA；当前 APC 为 USD 2,160，另计税费 | Hybrid；OA 在录用后选择。2026 OA APC 为 USD 2,800，另计税费；超页费另算 |
| 其他投稿项 | 每位作者 ORCID；选择 2 个准确 EDICS | submitting author 需公开且完善的 ORCID；全部作者 biography；3–10 个 keywords | 2–5 个 keywords；最终稿另按 RA-L journal format 重排 |

注：TIM 当前作者页写明 regular paper“无最大页数”，但其链接的超页协议文件修订日期较早；这里只冻结“8 页免费额度、超页强制收费”这一当前官网链接所示结构，不把旧协议中的单价当作 2026 最终价格。

## 3. 三条路线对 B2 的适配判断

### 3.1 IEEE Access：当前默认、最完整的投稿路线

本项目判断：**适配度最高，建议作为当前默认路线；稿型为 Research Article。**

理由：

- B2 的真实优势是完整应用实验和可审计比较，而不是新算法。IEEE Access 明确接纳应用工程、新实验与测量技术，也允许用足够篇幅交代 E0–E4 的不同统计单位、失败、提前停止和人工修订。
- Supplement 可容纳全量逐目标/逐 rebuild 结果、配置、代码和数据字典，主文仍可保持自包含。
- E4 的 one completed nine-target block 可以作为透明的 exploratory downstream case study；无需伪装成完整 manipulation 或确认性 108-trial study。

必须通过的 Access 门槛：

1. 贡献必须写成相对最接近工作的明确 advance，不能只说“比较了三个常见模型”。
2. 每个实验的 physical `n`、offline `n`、配对结构、缺失/失败和区间估计必须清楚。
3. 结论必须保持 geometry-conditioned；不能从单一硬件/工作区推出普适模型排名。
4. 正文建议控制在 14–18 个 IEEE Access 排版页，绝不因“无页数上限”堆放日志或重复图。
5. 投稿前必须确认作者可接受 OA 费用；费用不是科学质量判断的一部分。

### 3.2 TIM：高价值但有条件的冲刺路线

本项目判断：**scope 有入口，但当前并非直接可投；只有通过 measurement gate 才升级为首选。** TIM 官网明确说明，novelty 不一定是新算法，也可以是新的 measurement method、instrument、system 或 application，这使 B2 不会仅因 Affine/Homography/PnP 都是既有方法而自动出局。

TIM measurement gate：

1. 把论文对象从“机器人算法排名”重构为一个 vision-based measurement chain：measurand、坐标系、标定、参考值、误差传播和适用几何都必须定义。
2. 基于现有 E0–E3 与 E4 审计信息建立可追溯的不确定度/误差预算；区分相机观测噪声、模型失配、board-to-robot registration、机器人执行和人工网格读数。无法量化的 E4 observer component 必须保留为未估计限制，不能补数。
3. 与 I&M 文献中的 vision-based measurement、calibration、uncertainty 和 system evaluation 直接比较，不能主要依赖 robotics/vision 文献。
4. 给出相对于既有 calibration benchmarking/end-to-end calibration 工作的 journal-level measurement novelty，例如共享协议下的多层误差传播评价及其可复现实现；仅“数据更多”不够。
5. 主结果必须能回答 measurement question，而不只是 `which model wins`。

若上述任一关键项只能靠新增、并不存在的实验补齐，则不投 TIM，回到 IEEE Access 路线。现有照片不全不阻止做 TIM 可行性分析，但会限制 E4 人工读数不确定度能达到的证据强度。

### 3.3 RA-L：当前暂停，不作为默认投稿路线

本项目判断：**当前适配度最低，暂不投入 RA-L 专用正文。**

理由：

- RA-L 要求 concise account of innovative robotics/automation results；B2 当前核心是既有映射模型的条件化评价，新机器人算法/系统贡献不突出。
- 6–8 页且禁止 supplemental text/figures，使 E0–E4 的统计边界、失败记录和人工读数限制难以同时透明呈现。
- E4 只有一个完整九目标 block、人工读数且提前停止，可以收束叙事，但不足以单独承担一篇强调机器人创新的 Letter。

只有同时满足以下条件才重启 RA-L：能把贡献压缩为一个真正的 robotics/automation innovation；6–8 页内仍完整交代必要证据；无需隐藏 E4 局限；核心结论不依赖正文之外的文字补充。当前项目不满足这些条件。

## 4. 冻结后的路线排序

- **默认写作/投稿路线：IEEE Access Research Article。**
- **条件冲刺路线：TIM Regular Paper；先完成 measurement gate 审计，再由作者决定是否升级为首选。**
- **暂停路线：RA-L。** 保留其优秀论文作为机器人叙事和图表基准，但不按其模板投入正文。

这一区分允许正文先按“TIM 级测量严谨性 + Access 可容纳的完整透明度”建设；它不意味着同一稿件可同时投稿，也不意味着后续可不经改写直接换刊。

## 5. 对蓝图的直接约束

1. `end-to-end` 继续使用，但严格限定为 image/board observation 到 robot endpoint 的已测链路。
2. Appendix 默认不设。Access/TIM 的非核心全量结果进入 Separate Supplement；RA-L 路线暂停，因此不为其删减科学边界。
3. Fig. 1 必须把 measurand、坐标链、验证层级和未覆盖的 detection/grasp/contact 清楚区分。
4. E4 正文至少同时出现 `exploratory`、`one completed nine-target block`、`manual endpoint reading` 和 `early stop` 的事实。
5. 若走 TIM，Title/Abstract/Introduction 必须明确 I&M contribution；若走 Access，则强调 auditable geometry-conditioned evaluation，而不是虚构算法创新。

## 6. AI 规则

IEEE 通用政策要求：生成式 AI 产生的文字、图、代码等内容应在 Acknowledgment 披露系统名称、涉及章节和使用程度；纯语言/语法编辑通常不在强制披露的核心范围，但建议披露。IEEE Access 的当前投稿清单更具体：AI-generated text 要在 Acknowledgment 披露，使用该文本的章节还要引用所用 AI 系统。RA-L 同时遵循 IEEE/RAS 的生成式 AI 指南。

本项目仍按作者既有决定执行：现在只保留事实日志，不预先虚构最终披露文字；投稿前按真实使用记录生成并由作者签认。

## 7. 正式投稿前重新核验清单

- [ ] scope 与稿型仍未变化；
- [ ] 下载当日官方 Word/LaTeX 模板；
- [ ] 页数、文件大小、超页费和 APC；
- [ ] anonymous-review 要求与自引处理；
- [ ] Appendix、supplement、data、code 和 video 规则；
- [ ] AI disclosure、ORCID、author biography、keywords 与 EDICS；
- [ ] 是否存在更合适的 Society/Special Section；
- [ ] 当前稿件未同时投往其他期刊。

## 8. 官方来源

### TIM

- Scope：<https://ieee-ims.org/publication/ieee-tim>
- Information for Authors：<https://ieee-ims.org/publication/ieee-tim/information-authors>
- Information for Reviewers：<https://ieee-ims.org/publication/ieee-tim/information-reviewers>
- 当前官网链接的 Overlength Page Charge Agreement：<https://ieee-ims.org/sites/ieeeims/files/2020-08/overlengthagreement2020_1.pdf>

### IEEE Access

- Scope/About：<https://ieeeaccess.ieee.org/about/>
- Preparing Your Article：<https://ieeeaccess.ieee.org/authors/preparing-your-article/>
- Submission Guidelines：<https://ieeeaccess.ieee.org/authors/submission-guidelines/>
- Stages of Peer Review：<https://ieeeaccess.ieee.org/authors/stages-of-peer-review/>
- APC：<https://ieeeaccess.ieee.org/about/article-processing-charges/>

### RA-L 与 IEEE AI 政策

- RA-L scope：<https://www.ieee-ras.org/publications/ieee-robotics-and-automation-letters/>
- RA-L Information for Authors：<https://www.ieee-ras.org/publications/ra-l/ra-l-information-for-authors/>
- RA-L FAQ：<https://www.ieee-ras.org/publications/ra-l/faq/>
- RAS double-anonymous update：<https://www.ieee-ras.org/important-updates-to-journal-review-process-guidelines/>
- RAS Generative AI Guidelines：<https://www.ieee-ras.org/publications/guidelines-for-generative-ai-usage/>
- IEEE PSPB Operations Manual：<https://pspb.ieee.org/images/files/PSPB/opsmanual.pdf>
