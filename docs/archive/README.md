# Archive

Pre-monorepo and pre-rename material. Not maintained, kept for historical
reference (script names, file paths, and design rationale that informed the
current layout but no longer matches the active code).

| Item | What it is | Replaced / superseded by |
|---|---|---|
| `verification_log.md` | 2641-line journal kept during the analysis_pipeline cleanup roadmap (Stage 1..N entries with sha256 deltas) | superseded by `tests/baseline/fingerprints.txt` for active regression coverage |
| `core-reports/` | `PMET_project`'s own benchmark / optimization / style-refactor reports from before merging into this monorepo | n/a — historical context only |
| `*-README.md`, `*-TODO.md` | per-source README and TODO files from `PMET_project`, `pmet_analysis_pipeline`, `pmet_shiny_app` | replaced by the single repo-root `README.md` and per-area docs above |
| `pmet-method-zh.md` | Chinese version of the PMET method explanation | English-primary `docs/methods/pmet.md` |
| `motif_output_demo.txt` | sample heterotypic output from an old run | `data/demo_pmet_analysis/example_pmet_result.txt` is the live equivalent that the frontend's "Visualize" example button serves |

Anything in here referencing `scripts/pipeline/...`, `pmet_shiny_app/...`,
or the numbered `06_elements_longest.sh` / `07_elements_merged.sh` is
**stale by design** — see active docs for current paths.

The pre-monorepo pipeline story pack used to live here as
`pre-monorepo-pipeline-story/`. It moved to
[`docs/workflows/walkthroughs/`](../workflows/walkthroughs/) — same
content (frozen snapshot, paths still pre-monorepo), now sitting next
to its current auto-regenerated equivalents under
[`docs/workflows/`](../workflows/) so the two are easy to compare side
by side.
