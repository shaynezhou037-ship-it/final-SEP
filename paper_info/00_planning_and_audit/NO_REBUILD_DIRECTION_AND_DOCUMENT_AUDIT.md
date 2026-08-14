# 不重搭系统后的论文方向与文档重构审计

日期：2026-08-14  
决策：不重新搭建物理系统；投稿主线进一步收束为 E1→E2→E6，仿真 E7 仅保留在仓库。

## 1. 结论

严格 IEEE reviewer audit 后，论文不再以“多个部署因素的 operating envelope”为中心，而只回答：

> 当目标离开标定平面时，二维平面映射、single-view PnP 与 stereo 分别提供什么几何信息；第二个 camera-specific estimate 是否等同于第二视图的 parallax information？

这条路线比旧路线更有区分度，因为 E6 给出了项目内的新结论：**两个 camera-specific estimates 的平均/加权，不等于利用两视图 parallax 获得新的几何信息。** 严格同维度 XYZ 消融中，25 mm 高度下 ihawk1/ihawk2/equal/LOO-weighted/stereo 的 3-D RMSE 为 10.348/6.144/7.431/6.351/3.342 mm；stereo 在 5/5 paired rebuilds 中低于 ihawk2。50 mm 时 ihawk2/stereo 为 6.002/4.897 mm，但 stereo 只在 4/5 rebuilds 中更低，因此结果支持 conditional aggregate advantage，不支持 universal dominance。

论文仍不是新算法论文。最合理的投稿定位仍是 IEEE Access 风格的 controlled applied evaluation。标题、摘要和贡献只围绕 E1/E2/E6；E3/E5/E4 只检查边界，E0 完整结果进 Supplement 且关键 limitation 留正文，E7 不进投稿包。

## 2. 新的证据层级

| 实验 | 使用位置 | 证据类型 | 允许主张 | 禁止外推 |
|---|---|---|---|---|
| E0 | Main-text limitation + Supplement diagnostics | physical diagnostics | 静态波动量级、路径控制理由 | 完整 uncertainty budget、robot-only cause |
| E1 | 核心 RQ1 planar anchor | physical held-out spatial data | planar Homography/PnP comparison | 36 次独立部署 |
| E2 | 核心 RQ1 height transition | 5 physical rebuilds | off-plane robustness | 普适必要高度 |
| E3 | Supporting validity check | offline resampling | coverage/count sensitivity | 独立 RQ；100 次物理重标定 |
| E5 | Supporting observation/resource check | paired downsampling of saved E2 images | detection/accuracy/latency boundary | 独立 RQ；native sensor mode |
| E6 | 核心 RQ2 | offline analysis of paired physical E2 data | second estimate vs stereo parallax | dynamic scene、independent metrology、E4 endpoint validation |
| E6 angle | Supplement limitation | design identifiability audit | current data cannot isolate angle effect | 主图、angle causality、optimal angle |
| E4 | Limited application-side check | one completed physical endpoint block | exploratory downstream transfer | 全文高潮、E6 validation、robot floor |
| E7 | Excluded from submission | deterministic Monte Carlo simulation | repository-only future-work pilot | 正文、Appendix、Supplement evidence |

## 3. 角度变化后需要补充的信息处理

### 已完成

1. 每个 run/camera 的 camera center、board-center distance、azimuth、optical-axis tilt、line-of-sight incidence、Z=0 marker side/footprint 和 reprojection RMSE 已冻结在 `E6_camera_geometry.csv`。
2. 每个 height 的 geometry variable 与 PnP XY RMSE 的 Pearson/Spearman association 已生成，但全部标为 `descriptive_only=1` 和 `camera_identity_and_geometry_confounded=1`。
3. 新增 angle-identifiability audit，把“混杂”从口头限制变成可复现数字：
   - 10 个 run-camera rows 只对应 2 个固定 placements；
   - camera identity 对 distance/tilt/marker side/footprint 的 eta² 为 0.9997/0.9863/0.9984/0.9997；
   - 两相机在四个变量上的 ranges 全部不重叠；
   - 因此 causal angle levels = 0。
4. E6 verifier 已增加强制 gate：angle verdict 必须保持 `not_identifiable_from_current_E6`，固定布局数必须为 2，causal angle levels 必须为 0。

### 不再做

- 不拟合 optimal-angle curve；
- 不用 n=10 的 pooled correlation 做 p-value 或多变量因果回归；
- 不把五次 rebuild 当成五个新角度；
- 不等待控制 distance/footprint/lighting 的新物理 angle sweep。

原因不是分析方法不够复杂，而是当前设计中 angle、camera identity、distance、azimuth、footprint、optics 和 calibration 没有被独立操纵；离线统计不能恢复缺失的实验对照。

## 4. 补充的数据处理与证明

新增 paper-level verifier：

```powershell
python paper_info/02_reproducibility/scripts/verify_no_rebuild_evidence.py
```

它依次运行 E5/E6/E7 三套 component verifier，并检查：

- E5 source/QC cardinality、480 × 300 detection loss、native P95 latency 与 ihawk2 PnP resolution cost；
- E6 PnP fusion ordering、strict XYZ ablation、rebuild-level paired contrasts、stereo 25 mm XY/Z headline 和 angle-identifiability verdict；
- E7 必须保持 `simulation_only`，并核对 frozen/relocalized PnP headline；
- 参与论文新主张的 JSON/CSV 的 SHA-256。

输出为 `paper_info/02_reproducibility/no_rebuild_evidence_manifest.json`，其中冻结了 C19–C23。收束后只有 C21 是新增核心 claim；C19/C20/C22 是 supporting boundaries，C23 是 excluded/future-work record。当前验证结果为 PASS。

## 5. `paper_info` 文档影响矩阵

| 文件 | 处理 | 原因/结果 |
|---|---|---|
| `03_manuscript_notes/PHASE1_PAPER_BLUEPRINT_V2_IEEE.md` | 已重改为 v2.4 | 两个 RQ、两项贡献、四张主图；E6 strict XYZ ablation；E1/E2/E6 core；E7 excluded |
| `03_manuscript_notes/PAPER_WRITING_MASTER_PLAN.md` | 已重改 | 长期目标改为 geometric-information sufficiency；冻结 core/supporting/excluded 分级 |
| `03_manuscript_notes/EXPERIMENT_E6_E7_NOVELTY_DECISION.md` | 已更新 | 从“待决定”改为“已执行”；删除必须重搭的 follow-up gate |
| `00_planning_and_audit/PAPER_COLLABORATION_WORKFLOW.md` | 已更新 | 新权威入口、R9 scope-tightening decision、no-rebuild 数据边界 |
| `05_literature_library/notes/PHASE2_NOVELTY_GAP_AUDIT.md` | 已重扫/更新 | 增加 monocular/stereo、multi-camera fusion、view-geometry prior art；收窄创新性 |
| `05_literature_library/notes/FINAL_PAPER_READING_NOTES.md` | 已补充 | Volden 2022、Popescu 2020、Adámek 2023 的可用/不可用主张 |
| `04_writing_standards/IEEE_HIGH_QUALITY_PAPER_BENCHMARK.md` | 已更新 | 两个 RQ、core/supporting 分级与 four-figure plan |
| `04_writing_standards/LANGUAGE_AND_CLAIM_AUDIT_STANDARD.md` | 已更新 | 增加 E5/E6/E7 证据动词和术语冻结 |
| `04_writing_standards/IEEE_VENUE_RULES_AND_FIT.md` | 已更新 | IEEE Access 仍默认；TIM/RA-L gate 按新增证据重评 |
| `README.md` | 已更新 | 索引扩展到 E0–E7，并标明 physical/offline/simulation classes |
| `03_manuscript_notes/claim_evidence_map_v2.csv` | 待迁移 | E0–E4 仍有效；C19–C23 已冻结在 manifest，本会话缺专用 spreadsheet component，未做不受控 CSV 改写 |
| `05_literature_library/citation_sentence_ledger.csv` | 待迁移 | 需加入三条新引用句子与限制 |
| `05_literature_library/literature_screening_log.csv` | 待迁移 | 需加入三篇 full-text-verified primary papers |
| `05_literature_library/references.bib` | 待同步 | 与 ledger/screening log 一次完成，避免 cite key 不一致 |
| `01_equipment_and_methods/B2_Equipment_Experimental_Setup.xlsx` | 待补 sheet/rows | 只需增加 E5 offline resolution levels、E6 info flows 和证据等级；不改硬件事实 |
| `04_writing_standards/AI_USE_LOG.csv` | 待补事实日志 | 记录 E5–E7 分析/审计和文档辅助范围；不预写最终 disclosure |
| `计划.docx`、`筛选+行动主线.html`、`信息库_B2资料审计更新版.docx` | 不重改 | 仅作历史追溯，不再作为当前科学方向入口 |

## 6. 写作时的最终取舍

正文只保留四张主图：system/information hierarchy、E1+E2 planar-to-off-plane、E6 second estimate versus stereo（XY curves + strict XYZ/3-D ablation）、E4 limited application-side transfer。E3/E5/angle 完整图进入 Supplement；E7 完全退出投稿包。

主文只允许两项贡献：

1. 在共享 observations/truth/rebuild protocol 上建立 planar Homography → single-view PnP → estimate fusion/stereo 的 controlled information hierarchy；
2. 定量说明 second estimate 与 second-view geometry 不是同一种信息。

E3/E5/E4 的任务是防止主结论被标定覆盖、降采样或有限 endpoint chain 误读，不得重新膨胀成并列创新点。Abstract、Introduction、Results headings、Discussion 和 Conclusion 都执行这一层级。
