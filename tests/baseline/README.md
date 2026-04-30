# Baseline fingerprints

Captured before the monorepo refactor at commit `123a39b` on `refactor/monorepo`.

## What is captured

`capture.sh` records, by section:

- **binaries** — sha256 of the production binaries in `build/`: `index_fimo_fused` and `pair_parallel`.
- **core_demo_indexing_existing_outputs** — sha256 of `PMET_project/results/cli/demo/fimo_official/*` reference outputs.
- **core_demo_run_indexing_fused** — runs `apps/cli/scripts/run_indexing.sh -v fused` against `data/demos/promoters/indexing/demo` and hashes every produced file.
- **core_demo_run_pairing** — runs `apps/cli/scripts/run_pairing.sh` against `data/demos/promoters/pairing/demo` and hashes outputs.
- **analysis_smoke** — runs `pmet_analysis_pipeline/scripts/pipeline/00_requirements.sh` (tool presence check).
- **backend_pytest** — runs `pmet_shiny_app/pmet_backend/test_api.py`.

## Pre-refactor status

| Section | Status | Note |
|---|---|---|
| binaries | OK | production binaries only |
| core_demo_run_indexing_fused | OK | deterministic outputs |
| core_demo_run_pairing | OK | deterministic outputs |
| analysis_smoke | OK | only checks tool presence |
| backend_pytest | **FAIL** | env-blocked: `No module named 'pydantic'`. Not a code regression — the system python3 lacks backend deps. Re-run after `pip install -r apps/pmet_backend/requirements.txt` for true baseline. |
| frontend_home + submit + tasks + visualize + about (playwright) | OK | Full-page screenshots for `/` and `/submit` saved alongside this README. Submit page produces 4× expected `404 /api/indexing` errors when the backend is offline; UI degrades to "no databases found", does not crash. The other routes have 0 console errors. |

## Re-running

```bash
bash tests/baseline/capture.sh > tests/baseline/fingerprints.txt
```

Compare with `git diff tests/baseline/fingerprints.txt` after the refactor.
The "binaries" section contains only production binaries. The hashes for **demo outputs** must stay identical.

## Known non-determinism

The active fused indexing and parallel pairing demo outputs are expected to be deterministic.
