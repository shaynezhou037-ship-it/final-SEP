# B2 英文语言与主张审计标准

最后更新：2026-08-14

## 1. 审计顺序

每段按以下顺序检查，不能先润色再补证据：

1. 这段只回答一个问题吗？
2. 每个事实/数字来自哪个冻结文件或全文文献？
3. 统计单位写对了吗？
4. 证据强度允许这个动词吗？
5. 术语、数字和图表一致吗？
6. 最后才检查英语、节奏和 IEEE 格式。

## 2. 证据动词等级

| 证据状态 | 推荐动词 | 禁用或慎用 |
|---|---|---|
| 直接、预先定义、重复充分 | showed, yielded, was lower/higher | proved, guaranteed |
| 描述性配对结果 | was descriptively similar, differed by, was consistent with | was equivalent, significantly improved |
| 跨实验综合/机制相符 | suggests, supports, is consistent with | demonstrates the cause, confirms the mechanism |
| 探索性 E4 | in the completed block, the observed endpoint error… | validates generally, establishes the robot floor |
| 单数据集 E3 | in the tested candidate set/workspace | points are generally sufficient, universal rule |
| paired offline E5 | under simulated effective downsampling of the saved 640 × 400 images | native sensor mode, hardware frame-rate validation |
| physical-data offline E6 | under the tested static paired observations/five rebuilds | two cameras are universally better, end-to-end dual-camera validation |
| E6 angle audit | the current two fixed placements do not identify a causal angle effect | angle caused, optimal angle, angle-generalized model |
| simulation-only E7 | in the deterministic Monte Carlo simulation | experimentally validated moving-camera performance |

任何 `significant/significantly` 只在有明确统计检验和定义好的 alpha 时使用；表示幅度大时改为 `substantial/large` 并给数字。

## 3. 强制限定词

以下结论必须紧邻条件：

- `under the tested setup/workspace/candidate set`；
- `across two cameras and five physical rebuilds`；
- `at the 36 held-out spatial locations`；
- `in offline resampling of a single physical observation set`；
- `in one completed nine-target E4 block`；
- `exploratory end-to-end endpoint case study`。
- `under simulated effective resolution using the saved E2 images`；
- `under static paired observations across five physical rebuilds`；
- `descriptive only because camera identity and view geometry are confounded`；
- `simulation only; no physical camera motion was acquired`。

## 4. 术语冻结

全篇统一：

- `eye-to-hand`：固定外部相机相对机器人；
- `mapping pipeline`：Affine/Homography/PnP 的输入到 board XY 输出；
- `physical rebuild`：按 Methods 明确定义的物理重建；
- `held-out spatial location`：不是 independent physical trial；
- `offline subset/resample`：不是 recalibration experiment；
- `endpoint error`：机器人到达后的人工观测 XY error；
- `observed Oracle reference`：不是 pure robot error/floor；
- `end-to-end robot positioning`：仅限已定义 image-to-endpoint 链；
- `PnP/IPPE`：planar pose estimation 方法，不等同于完整 hand–eye calibration。
- `estimate fusion`：先由两相机各自生成 board-coordinate estimate，再做 equal/LOO-weighted combination；不是 stereo triangulation；
- `stereo parallax/triangulation`：直接使用配对像点和两投影矩阵恢复 board XYZ；不是两个结果的平均；
- `simulated effective resolution`：对保存的 640 × 400 图像离线降采样；不是 native sensor mode；
- `angle-identifiability audit`：量化 camera identity/geometry confounding；不是 camera-angle experiment；
- `relocalized PnP`：仿真中用固定 landmarks 更新当前 camera pose 后再估计 target；不是与 PnP 对立的另一类算法。

## 5. 机器腔和空话清理

看到以下表达默认删除或改成可核验内容：

- `In today's rapidly evolving…`
- `plays a pivotal/crucial role`（除非下一句给出具体后果）
- `It is worth noting that…`
- `This groundbreaking/novel/robust framework…`
- `comprehensive`、`significant`、`superior` 没有范围和数字
- 连续使用 `Moreover/Furthermore/Additionally`
- `delve into`、`leverage`、`underscores`、`paves the way`
- 每段结尾重复“this demonstrates the effectiveness of the proposed method”

替换原则：写谁做了什么、在什么条件下、产生什么数字、它回答哪个 RQ。

## 6. 句子与段落标准

- 主语必须明确；避免长串被动语态掩盖执行者和数据来源；
- 一个句子原则上只承载一个主结论和一个必要限定；
- Results 多用过去时；方法事实可用过去时，图表和论文结构可用现在时；
- 缩写首次出现定义，此后只用一种形式；
- 不把 `accuracy` 同时用于 mean error、RMSE、repeatability 和 success rate；
- 不用 `better` 而不说明 metric、方向和比较对象；
- 数字写单位，单位与数值之间保留空格，表内精度统一且不超过测量分辨率；
- 每段第一句给主题，最后一句给边界或意义，不机械重复结果。

## 7. 引用审计

- 引用必须在 `citation_sentence_ledger.csv` 绑定到一句具体主张；
- 优先原始论文、标准和官方文档；综述用于导航，不替代原始方法引用；
- 只读摘要的文献不能标 `VERIFIED_FULLTEXT`；
- 预印本必须显式标注，若有正式版本则替换；
- 禁止引用不存在、标题/DOI 不一致或只因“看起来相关”的论文；
- 不在同一句末尾堆 8–10 篇却不说明各自支持什么；
- 引用不能替代对本项目数据的论证。

## 8. 数字与图表文字审计

每个正文数字都要有：source path、metric definition、unit、aggregation、n、revision/freeze ID。Caption 至少说明：对象、条件、独立单位、线/点/误差带含义、失败值处理、exploratory 标签。

禁止：手工从图上读回结果；正文、表格和 caption 分别维护同一数字；四舍五入后制造不存在的差异；用 error bar 暗示独立性却不说明它跨 frame、target 还是 rebuild。

## 9. 章节终审问题

### Abstract

- 是否单段 ≤250 words、自包含且无引用？
- 是否只放正文确实证明的数字？
- 是否把 E4 写成 completed block，而不是 completed study？

### Introduction

- 第一页能否在 30 秒内说清问题、缺口、方法和贡献？
- 贡献是否是本项目真正新增的证据/协议，而不是已知算法？

### Results

- 每个 RQ 是否都有图/表和一句直接回答？
- 是否把解释与因果推断留给 Discussion？

### Discussion/Conclusion

- 是否重复数字而没有解释边界？
- 是否从两个相机/一个系统跳到所有机器人？
- 是否把 estimate fusion 和 stereo parallax 混成“dual-camera method”？
- 是否把 E5/E7 写成原生硬件/物理实验？
- 是否明确 E6 angle confounding、no endpoint propagation，以及 E4 registration/人工读数限制？

## 10. 审计输出格式

每次语言审计只输出问题表，不直接覆盖正文：

| ID | Section/Sentence | Problem type | Evidence/source | Proposed revision | Author decision |
|---|---|---|---|---|---|

问题类型固定为：`CLAIM_OVERREACH`、`NUMBER_MISMATCH`、`CITATION_MISMATCH`、`UNIT_OF_ANALYSIS`、`TERMINOLOGY`、`LOGIC`、`STYLE`、`FORMAT`。作者确认后才修改正文。
