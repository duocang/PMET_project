# Naming Conventions

This document is the single source of truth for how files in this repository
are named. New code must follow it; existing files that violate it are listed
here as "grandfathered" and should be touched only when their contents change
for an unrelated reason.

The goals are:

- **Predictable**. Anyone scanning a directory should guess what each file
  does from its name alone.
- **Mechanically searchable**. `grep -l '<NN>_<scope>'` should reliably find
  every artefact for a pipeline.
- **Stable**. Renames break tooling and history; we batch them up rather than
  doing one-offs.

## 1. Directory layout

```
pmet_analysis_pipeline/
├── run.sh                      # User-facing launcher (root for visibility)
├── readme.md                   # Project overview
├── LICENSE.md
├── TODO.md
├── .gitignore
│
├── scripts/                    # All executable / library code
│   ├── scripts/               # Top-level pipeline entrypoints
│   ├── tests/                  # Test runners + verifiers + fixtures + baselines
│   ├── python/                 # Python helpers (parse_*, build_*, check_*, ...)
│   ├── r/                      # R plotting helpers
│   ├── lib/                    # Shell helpers (print_colors.sh, timer.sh)
│   ├── indexing/               # Indexer wrappers used by pipelines
│   ├── gff3sort/               # Vendored Perl tool
│   ├── archive/                # Retired scripts (kept for reference)
│   ├── fetch_reference.sh         # One-off data download
│   └── temp/                   # Local scratch (gitignored)
│
├── docs/
│   ├── verification_log.md     # Per-change runtime/memory/hash record
│   ├── naming_conventions.md   # This file
│   ├── pmet_method_*.md
│   ├── promoter_*.md
│   ├── *.svg
│   └── temp/                   # Local scratch (gitignored)
│
├── data/                       # Inputs (genomes, gene lists, motif files)
├── build/                      # Compiled binaries (gitignored)
├── legacy/                     # Frozen historical reference (gitignored)
└── results/                    # All run outputs, transient or permanent (gitignored)
```

## 2. scripts/

Form: `<NN>_<scope>_<variant>.sh`, where

- `<NN>` is a two-digit identifier that is unique within `scripts/`.
  The number is the pipeline's identity — it is referenced in baselines, in
  `run.sh`, and in the verification log. Numbers are not reassigned; if a
  pipeline is retired its number is retired with it.
- `<scope>` is the business domain: `requirements`, `benchmark`, `promoter`,
  `intervals`, `elements`.
- `<variant>` is omitted for the default member of a scope; otherwise it is
  the shortest meaningful disambiguator.

| File | scope | variant | One-line description |
|---|---|---|---|
| `00_requirements.sh` | requirements | — | Check tools, fetch TAIR10 |
| `01_benchmark_cpu.sh` | benchmark | cpu | Single-CPU vs threaded heterotypic |
| `02_benchmark_parameters.sh` | benchmark | parameters | (length, maxk, topn) sweep |
| `03_promoter.sh` | promoter | — | Default promoter pipeline |
| `04_intervals.sh` | intervals | — | Default interval pipeline |
| `05_promoter_gap.sh` | promoter | gap | Promoter with TSS-proximal gap |
| `06_elements_longest.sh` | elements | longest | Genomic element, longest isoform per gene |
| `07_elements_merged.sh` | elements | merged | Genomic element, merged isoforms per gene |
| `08_pair_only.sh` | pair | only | Heterotypic + heatmaps on a pre-built homotypic index (consumes 03/04/05 output) |

Pipeline numbers in flight: `00, 01, 02, 03, 04, 05, 06, 07, 08` (contiguous).
`05` was once retired and later reclaimed when `08_promoter_gap.sh` was
renumbered to fill the gap; `08` is now the new pair-only entrypoint
(2026-04-28).

Pipelines must be runnable directly: `bash scripts/<NN>_*.sh`. They
must also still appear in `run.sh`'s menu.

## 3. scripts/python/

Form: `<verb>_<object>.py` where `<verb>` is one of

- `parse_*` — read a file, emit a structured form
- `build_*` — synthesise an artefact from inputs
- `calculate_*` — numeric computation
- `check_*` — validate a contract; non-zero exit on violation
- `assess_*` — diagnostic / inspection without side effects

Examples (current and planned): `parse_genelines.py`, `parse_utrs.py`,
`build_promoters.py`, `calculate_length_to_tss.py`,
`check_homotypic_contract.py`, `assess_integrity.py`.

When a script is retired, move it to `scripts/archive/` rather than deleting.

## 4. scripts/r/

Form: `<verb>_<object>.R` (preferred) or `<object>_<verb>.R` (grandfathered).
Examples: `draw_heatmap.R`, `process_pmet_result.R`,
`motif_pair_diagonal.R`.

## 5. scripts/tests/

Three prefixes, each with a different role:

| Prefix | Role | Examples |
|---|---|---|
| `run_*.sh` | Run a suite or a controlled workflow | `run_smoke.sh`, `run_pipeline02_one_combo.sh`, `run_with_verify.sh` |
| `verify_*.sh` | Compare output against a recorded contract or baseline | `verify_baseline.sh`, `verify_homotypic_contract.sh` |
| `test_*.sh` | Single-scenario assertion (boolean pass/fail, no baselines) | `test_pipeline02_strand_realdata.sh` |

Subdirectories:

- `scripts/tests/fixtures/` — synthetic inputs, named `<scenario>_<artefact>.<ext>`,
  e.g. `strand_minigenome.fa`, `strand_promoters.bed`.
- `scripts/tests/baselines/` — recorded outputs from real pipelines.

### 5.1 Baselines naming (new rule)

Form: `<NN>_baseline.<stdout|stderr|exit|hashes.txt>`, one set per pipeline.

**Do not introduce state suffixes** (`_postfix`, `_post_rcleanup`,
`_postfix_one_combo`) for new work. When a fix produces an EXPECTED CHANGE
the existing baseline file is overwritten in the same commit; the verification
log entry and `git log` together are the audit trail. Pre-existing files with
state suffixes are kept as historical archives and are not maintained going
forward.

Exception: pipeline-specific harnesses that intentionally exercise a
restricted scope (e.g. `02_postfix_one_combo.hashes.txt` for the one-combo
grid harness) keep their descriptive suffix because their *scope* is
different from the default `02_baseline`.

## 6. scripts/temp/, docs/temp/

Anything goes. Suggested form `YYYYMMDD_<topic>_<artefact>` so chronological
sweep is easy. Both directories are gitignored.

## 7. docs/

Lowercase, words separated by `_`, ASCII where practical:

- `verification_log.md`, `naming_conventions.md`, `pmet_method_zh.md`,
  `pmet_method_en.md`, `promoter_pipeline_readme.md`.

Existing files that violate this (mixed case, mixed scripts) are
grandfathered. Rename only when the file is being substantively edited
anyway.

Root-level docs (`readme.md`, `LICENSE.md`, `TODO.md`) are
exceptions — community convention dominates over local style.

## 8. results/

`results/<NN>_<scope>[_<variant>]/` mirrors the pipeline name. The whole
`results/` tree is gitignored. Subdirectories created by individual pipelines
(`01_homotypic/`, `02_heterotypic/`, `plot/`, etc.) are pipeline-defined
contracts; see `scripts/tests/baselines/<NN>_baseline.hashes.txt` for the
recorded layout.

`results/_AFTER_FIXES/` is a curated copy of selected artefacts, used as a
human-readable index after large fix series. Optional, may be deleted at any
time.

## 9. Commits and verification log

Verification log entry titles: `## YYYY-MM-DD HH:MM - <change name>`. The
change name is short and matches the commit subject.

Commit subjects use Conventional Commits prefixes (`feat`, `fix`, `docs`,
`refactor`, `chore`, `test`). Subject ≤ 50 chars; body explains *why*.

## 10. Grandfathered violations

These exist in the repo and predate this document. They are not failures;
they will be cleaned up opportunistically.

- `docs/PMET_method_汉.md`, `docs/PMET_method_en.md` — mixed case + Chinese
  in filename. Will rename when content is next touched.
- `docs/如何获得启动子区域.md` — Chinese filename. Same.
- `scripts/python/calculateICfrommeme_IC_to_csv.py` — camel-mash. Functional;
  rename when the file is next substantively edited.
- `tests/baselines/0{1,3,4}_baseline.*` and `01_postfix.*` and others —
  pre-rule artefacts; preserved as history (see §5.1).
