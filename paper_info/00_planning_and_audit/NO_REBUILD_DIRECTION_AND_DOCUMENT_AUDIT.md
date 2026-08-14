# 不重搭系统后的论文方向与文档重构审计

日期：2026-08-14  
决策：不重新搭建物理系统；只使用冻结数据、保存图像、离线派生分析和明确标注的仿真。

## 1. 结论

论文不再以“三个模型谁最好”为中心，而改为：

> 在低成本 eye-to-hand positioning 中，任务几何、标定覆盖、有效分辨率和单/双视图的信息使用方式如何决定定位管线的可用范围？

这条路线比旧路线更有区分度，因为 E6 给出了项目内的新结论：**两个 camera-specific estimates 的平均/加权，不等于利用两视图 parallax 获得新的几何信息。** 25 mm 高度下，PnP 的 ihawk1/ihawk2/equal/LOO-weighted XY RMSE 为 8.850/4.786/6.057/4.897 mm，结果融合没有超过较强单相机；stereo triangulation 的 XY/Z RMSE 为 2.752/1.772 mm。

论文仍不是新算法论文。最合理的投稿定位仍是 IEEE Access 风格的 deployment-oriented、auditable evaluation。E6 提高了创新性和工程意义，但没有把项目提升为 RA-L 式新机器人算法，也没有自动满足 TIM 的 measurement novelty/uncertainty gate。

## 2. 新的证据层级

| 实验 | 使用位置 | 证据类型 | 允许主张 | 禁止外推 |
|---|---|---|---|---|
| E0 | Methods/Limitations/Supplement | physical diagnostics | 静态波动量级、路径控制理由 | 完整 uncertainty budget、robot-only cause |
| E1 | 主文 RQ1 | physical held-out spatial data | planar model comparison | 36 次独立部署 |
| E2 | 主文 RQ2 | 5 physical rebuilds | off-plane robustness | 普适必要高度 |
| E3 | 主文 RQ3 | offline resampling | coverage/count sensitivity | 100 次物理重标定 |
| E5 | 主文 RQ3 supporting | paired downsampling of saved E2 images | simulated effective-resolution detection/accuracy/latency envelope | native sensor mode、硬件 frame-rate 结论 |
| E6 | 主文 RQ4 | offline analysis of paired physical E2 data | single vs estimate fusion vs stereo information flow | dynamic scene、independent metrology、E4 endpoint validation |
| E6 angle | RQ4 limitation/Supplement | design identifiability audit | current data cannot isolate angle effect | angle causality、optimal angle |
| E4 | 主文 RQ5/叙事终点 | one completed physical endpoint block | exploratory downstream transfer | robot floor、确认性 108 trials |
| E7 | Supplement | deterministic Monte Carlo simulation | stale calibration vs relocalization mechanism | real moving-camera performance |

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
- E6 PnP fusion ordering、stereo 25 mm XY/Z headline 和 angle-identifiability verdict；
- E7 必须保持 `simulation_only`，并核对 frozen/relocalized PnP headline；
- 参与论文新主张的 JSON/CSV 的 SHA-256。

输出为 `paper_info/02_reproducibility/no_rebuild_evidence_manifest.json`，其中冻结了待写入 claim map 的 C19–C23。当前验证结果为 PASS。

## 5. `paper_info` 文档影响矩阵

| 文件 | 处理 | 原因/结果 |
|---|---|---|
| `03_manuscript_notes/PHASE1_PAPER_BLUEPRINT_V2_IEEE.md` | 已重改为 v2.2 | 新标题/一句话主张；RQ1–RQ5；E5/E6/E7 角色；图表、统计、Supplement、禁止表述 |
| `03_manuscript_notes/PAPER_WRITING_MASTER_PLAN.md` | 已重改 | 长期目标改为 geometry/resource/information-conditioned；加入 no-rebuild continuation rules |
| `03_manuscript_notes/EXPERIMENT_E6_E7_NOVELTY_DECISION.md` | 已更新 | 从“待决定”改为“已执行”；删除必须重搭的 follow-up gate |
| `00_planning_and_audit/PAPER_COLLABORATION_WORKFLOW.md` | 已更新 | 新权威入口、R7/R8、no-rebuild 数据边界、paper-level verifier |
| `05_literature_library/notes/PHASE2_NOVELTY_GAP_AUDIT.md` | 已重扫/更新 | 增加 monocular/stereo、multi-camera fusion、view-geometry prior art；收窄创新性 |
| `05_literature_library/notes/FINAL_PAPER_READING_NOTES.md` | 已补充 | Volden 2022、Popescu 2020、Adámek 2023 的可用/不可用主张 |
| `04_writing_standards/IEEE_HIGH_QUALITY_PAPER_BENCHMARK.md` | 已更新 | RQ1–RQ5、E0–E7 统计单位与 Fig. 1–6 |
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

主文只保留六张功能明确的图：system/information-flow map、E1 planar、E2 height、E3+E5 constraints、E6 second-view information、E4 endpoint transfer。E7 全部进入 Supplement。

主文的创新性句子只围绕三个层次展开：

1. 共享、可审计的多层 operating-envelope protocol；
2. geometry/resource conditions 决定管线可用性；
3. second estimate 与 second-view geometry 不是同一种信息。

不要把“研究内容更多”当作创新性。E5 的价值是约束和负结果，E6 是新增主结论，E7 是机制补充，E4 是下游边界检查。这个层级必须贯穿 Abstract、Contribution、Results、Discussion 和 Conclusion。
