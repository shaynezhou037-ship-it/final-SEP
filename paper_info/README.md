# B2 paper information workspace

This folder stores paper-facing organization materials for the B2 study. Keep
raw experimental data, scripts, and generated analysis outputs in the existing
`E0` to `E7`, `config`, `metadata`, and `scripts` folders. E5/E6 reuse E2
physical observations offline; E7 is simulation-only and must not be counted as
new physical acquisition.

## Folder map

- `00_planning_and_audit/`
  - Research direction, action plan, repository/data audit, and decision notes.
  - Current direction audit:
    `NO_REBUILD_DIRECTION_AND_DOCUMENT_AUDIT.md`. The DOCX/HTML files are
    historical traceability sources and no longer override the v2.3 blueprint.

- `01_equipment_and_methods/`
  - Equipment tables, experimental setup, hardware parameters, method notes,
    measurement protocol, and setup characterization.
  - Current files: `B2_Equipment_Experimental_Setup.xlsx`.

- `02_reproducibility/`
  - Reproduction instructions, environment notes, data dictionaries, run
    order, script-to-output maps, exclusion rules, and paper-level evidence
    gates.
  - Current no-rebuild gate:
    `scripts/verify_no_rebuild_evidence.py`, which writes
    `no_rebuild_evidence_manifest.json` after E5/E6/E7 verification.

- `03_manuscript_notes/`
  - Current manuscript blueprint, claim-evidence map, figure/caption plans, and
    result narrative. The current blueprint is
    `PHASE1_PAPER_BLUEPRINT_V2_IEEE.md` v2.3. The submission follows one core
    progression, E1 → E2 → E6: planar mapping, off-plane single-view pose, and
    second-estimate versus second-view geometry. E3/E5 are supporting validity
    checks, E4 is a limited application-side check, E0 is Supplement-only, and
    E7 is excluded from the manuscript package.

- `04_writing_standards/`
  - Reusable IEEE writing, language/claim audit, figure/table, AI-use, and
    disclosure standards. These are updated in place rather than versioned on
    every edit.

- `05_literature_library/`
  - Curated final PDFs, verified reading notes, BibTeX, literature screening
    log, and citation-to-sentence ledger. Temporary candidates do not live here.

## Placement rule

- Put one-off experiment data under the matching experiment folder (`E0` to
  `E7`), while preserving each folder's physical/offline/simulation evidence
  class.
- Repository presence does not imply manuscript inclusion. In particular, E7
  remains reproducible repository-only future work and contributes no result to
  the current manuscript, Appendix, or Supplement.
- Put paper-level summaries or tables here under `paper_info`.
- Put reusable scripts under `scripts`.
- Put camera intrinsics, board definitions, and frozen configuration under
  `config` or `metadata`.
- Put screened citation/writing-benchmark PDFs only in
  `paper_info/05_literature_library/final_papers`; keep download/extraction
  caches under `tmp` and delete them after screening.
