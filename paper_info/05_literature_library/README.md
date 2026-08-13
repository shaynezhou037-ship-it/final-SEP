# B2 文献与引用资料库

本目录是论文引用和写作样本的唯一入口。

## 目录

- `final_papers/`：已下载、全文抽取并抽页视觉检查，预计会作为正文引用或高质量写作基准的 PDF；
- `notes/FINAL_PAPER_READING_NOTES.md`：逐篇可借鉴内容、支持的主张和限制；
- `notes/PHASE2_NOVELTY_GAP_AUDIT.md`：最接近工作、新颖性边界和禁止首创表述；
- `references.bib`：已核验元数据的候选 BibTeX；
- `citation_sentence_ledger.csv`：每篇文献准备支持正文哪一句，以及当前核验状态；
- `literature_screening_log.csv`：筛选、全文与图表检查状态。

## 状态定义

- `VERIFIED_FULLTEXT`：全文已读，DOI/出版信息已核对，可进入引用句子审计；
- `PROVISIONAL_PREPRINT`：全文已读但仅为预印本，优先找正式版本/替代文献；
- `BENCHMARK_ONLY`：主要学习写作/图表，不因期刊声誉强行引用；
- `NEED_SEARCH`：主张有文献缺口，不能先写引用编号占位。
- `VERIFIED_REMOTE_FULLTEXT`：正式全文已在线逐页核验，但本地下载不稳定；只留 DOI/官方链接，不保存损坏 PDF。
- `OFFICIAL_METADATA_ONLY` / `ABSTRACT_VERIFIED`：只能支持元数据或摘要明确陈述的有限句子，不能伪装成全文阅读。

## 控制膨胀规则

1. 候选 PDF 只放 `tmp/pdfs/literature_screening/`，筛选结束后清空；
2. `final_papers/` 不保留同一论文的 arXiv、accepted manuscript 和 publisher 三个重复版本；
3. 只有满足“将引用”或“明确作为写作/图表基准”之一才长期保留；
4. 被淘汰论文只在筛选日志保留元数据和理由，不留 PDF；
5. 引用前不仅看 PDF 是否存在，还必须在 `citation_sentence_ledger.csv` 把具体句子核验为 `VERIFIED`；
6. `references.bib` 在原文件更新，不生成多个副本。

## 已知版本例外

`Zhang2000_FlexibleCameraCalibration_EXTENDED_AUTHOR_VERSION.pdf` 是作者扩展技术报告，不是正式 5 页 TPAMI 排版版；引用使用期刊 DOI 和页码。`Acuna2018_..._PREPRINT.pdf` 目前只确认到 arXiv 预印本，不能伪装成 IEEE/期刊论文。
