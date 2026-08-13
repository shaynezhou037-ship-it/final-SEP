# B2 生成式 AI 辅助写作、自然语言与披露准则

最后更新：2026-08-13

## 1. 目标

本项目不以“骗过 AI 检测器”或隐藏 AI 使用为目标。目标是让论文体现作者真实的科学判断，所有内容可追溯、可复核，并按目标期刊规则披露。

原因：对 14 种检测系统的公开研究发现，现有 AI 文本检测器并不准确可靠，文本混淆还会进一步降低检测表现（DOI `10.1007/s40979-023-00146-z`）；另一项研究指出检测器可能对非英语母语写作者产生偏差（DOI `10.1016/j.patter.2023.100779`）。检测分数不能替代科研诚信或作者终审。

## 2. IEEE 当前规则

IEEE Author Center 要求：文章中 AI 生成的文本、图、图像或代码应在 `Acknowledgment` 披露，说明所用系统、涉及的具体章节和使用程度。纯编辑/语法增强通常不在强制披露意图内，但 IEEE 建议披露；使用 AI 编辑时应排除 References，并始终人工复核。

官方页面：<https://journals.ieeeauthorcenter.ieee.org/become-an-ieee-journal-author/publishing-ethics/guidelines-and-policies/submission-and-peer-review-policies/>。

投稿前必须重新核验目标 venue 的最新规定；本文件不能替代投稿当日政策。

## 3. 允许的用途

- 整理 outline、研究问题和审稿人可能质疑点；
- 在作者已给出主张与证据后生成候选英文表达；
- 检查语法、术语一致、数字冲突和交叉引用；
- 辅助生成数据处理/绘图代码，随后由作者运行和核对；
- 生成 red-team 问题清单；
- 将作者已核验的中文技术判断翻译为英文草稿。

## 4. 禁止的用途

- 编造实验、样本、显著性、引用、DOI、硬件参数或失败原因；
- 把未完成的 108 trials 写成完成；
- 把 Oracle 解释为纯机械臂误差；
- 根据结论反向修改数据或人工读数；
- 用 paraphraser/同义词替换器规避检测；
- 上传未公开的审稿稿件到不允许的公共 AI 平台；
- 让 AI 自动改写 References 或添加未经全文/DOI 核验的论文；
- 把 AI 输出直接粘贴为最终段落而不经作者逐句签认。

## 5. “降低机器腔”的合规方法

这不是伪装，而是提高作者性和信息密度：

1. **先证据后句子**：先在 claim/evidence map 中写主张、数字、边界，再写英文；
2. **从图表写段落**：每段围绕一个 RQ 和一张冻结图，不让模型自由扩写背景；
3. **保留作者判断**：为什么选这个比较、什么结果意外、什么不能解释，由作者明确给出；
4. **删除套话**：删除无数据的 `novel/comprehensive/robust/significant` 与模板化转折；
5. **具体化**：用 camera、height、rebuild、target、metric 和数值替代抽象赞美；
6. **逐句反问**：这句话能否由数据/全文文献直接支持？若不能，降级或删除；
7. **人工重构**：作者用自己的理解重新组织逻辑，而不是只做同义词替换；
8. **朗读检查**：检查节奏和含混，但不故意加入错误、口语或异常词来“像人”。

## 6. 每次 AI 辅助的记录

在 `AI_USE_LOG.csv` 中记录：日期、系统/版本、用途、涉及文件/章节、是否产生可进入正文的内容、作者复核方式、是否可能需要披露。只记录必要摘要，不保存含敏感数据的完整 prompt。

## 7. 三道人工关卡

### Gate A — 来源

所有数字回到正式 CSV/JSON；所有引用打开 DOI/出版社页和全文；图从冻结数据重建。

### Gate B — 科学判断

作者签认主张强度、统计单位、E4 early stop、人工读数修订和 generalization boundary。

### Gate C — 语言和披露

作者逐句读最终英文；核对 References 未被 AI 篡改；根据日志写真实 Acknowledgment；再做模板/PDF 渲染检查。

## 8. Acknowledgment 占位文本

投稿前按日志和当时政策修改，不能现在虚构系统版本或章节：

> During the preparation of this work, the authors used [system and version] to assist with [outlining/language drafting/editing/code-assisted figure preparation/consistency checking] in [exact sections]. All AI-assisted outputs were checked against the source data and cited literature, revised by the authors, and remain the authors' responsibility.

这个披露放在 `Acknowledgment`，不单独创建一个看似科研贡献的 “AI Review” 章节。

## 9. 投稿前签认

- [ ] AI use log 完整；
- [ ] 所有生成式内容和图/代码用途按目标 venue 规则披露；
- [ ] References 完全人工核验；
- [ ] 未使用 AI 检测分数作为“合规证明”；
- [ ] 作者可以口头解释每个 RQ、数字、图和限制；
- [ ] 最终文字不是为规避检测而混淆或故意降质。

## 10. 依据

- IEEE AI policy：<https://journals.ieeeauthorcenter.ieee.org/become-an-ieee-journal-author/publishing-ethics/guidelines-and-policies/submission-and-peer-review-policies/>
- IEEE Editorial Style Manual：<https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE-Editorial-Style-Manual-for-Authors.pdf>
- Weber-Wulff et al., 2023：<https://doi.org/10.1007/s40979-023-00146-z>
- Liang et al., 2023：<https://doi.org/10.1016/j.patter.2023.100779>
