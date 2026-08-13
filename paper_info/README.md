# B2 paper information workspace

This folder stores paper-facing organization materials for the B2 study. Keep
raw experimental data, scripts, and generated analysis outputs in the existing
`E0` to `E4`, `config`, `metadata`, and `scripts` folders.

## Folder map

- `00_planning_and_audit/`
  - Research direction, action plan, repository/data audit, and decision notes.
  - Current files: `计划.docx`, `筛选+行动主线.html`, `信息库_B2资料审计更新版.docx`.

- `01_equipment_and_methods/`
  - Equipment tables, experimental setup, hardware parameters, method notes,
    measurement protocol, and setup characterization.
  - Current files: `B2_Equipment_Experimental_Setup.xlsx`.

- `02_reproducibility/`
  - Future home for reproduction instructions, environment notes, data
    dictionaries, run order, script-to-output maps, and exclusion rules.

- `03_manuscript_notes/`
  - Current manuscript blueprint, claim-evidence map, figure/caption plans, and
    result narrative. The current blueprint is `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md`.

- `04_writing_standards/`
  - Reusable IEEE writing, language/claim audit, figure/table, AI-use, and
    disclosure standards. These are updated in place rather than versioned on
    every edit.

- `05_literature_library/`
  - Curated final PDFs, verified reading notes, BibTeX, literature screening
    log, and citation-to-sentence ledger. Temporary candidates do not live here.

## Placement rule

- Put one-off experiment data under the matching experiment folder (`E0` to
  `E4`).
- Put paper-level summaries or tables here under `paper_info`.
- Put reusable scripts under `scripts`.
- Put camera intrinsics, board definitions, and frozen configuration under
  `config` or `metadata`.
- Put screened citation/writing-benchmark PDFs only in
  `paper_info/05_literature_library/final_papers`; keep download/extraction
  caches under `tmp` and delete them after screening.
