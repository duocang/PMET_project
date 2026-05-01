# tests/unit/

Fast, isolated regression tests for individual functions. Each file
covers one bug that has been fixed, so we catch a regression before it
reaches the real pipeline.

Sibling test directories serve different purposes:

| Directory | Scope | Wall time | Needs |
|---|---|---|---|
| `tests/unit/` (this) | One function, no I/O beyond a tmp dir | < 5 s | bash + Rscript + python3 |
| `tests/integration/` | Cross-script invariants on tiny fixtures | < 5 s | bedtools, samtools |
| `tests/audit/` | Whole-workflow runs against canonical inputs | minutes | full PMET stack |
| `tests/baseline/` | Build + run + fingerprint hash diff | minutes | full PMET stack |

## Run

```bash
bash tests/unit/run.sh
```

Wrapper invokes each individual test file; exits 0 if all pass.

## Current tests

### `test_heatmap_dim_cap.R`

Covers the bug fixed in commit `4fd9aa2` (fix(heatmap): cap motifs,
size figures dynamically). The original `scripts/r/heatmap.R` hard-coded
`height <- 10 * ceiling(N/2)`; with many clusters this exceeded
`ggplot2::ggsave`'s 50-inch sanity limit and aborted the whole task.

The fix lives at `scripts/r/heatmap.R::compute_dims` (top-level since
the unit-test refactor); this test verifies:

- 25-cluster grid fits within `max_inches`
- small inputs are not inflated up to the cap
- monotonic in motif count
- extreme inputs (1000 motifs × 100 rows) still cap
- `max_inches` is configurable

### `test_stage_status.py`

Covers Problem 4 long-term fix in `TODO.md` — filesystem-derived
per-stage view that augments the binary `task.status`. Exercises
`services/stage_status.infer_stages` across:

- happy path (full Promoters): all 4 stages completed
- `promoters_pre` mode: indexing always reported as `skipped`
  (uses precomputed) and does NOT generate a warning
- the partial-result case: pairing completed but heatmap / zip
  show `skipped` with a warning note
- universe-mismatch failure: pairing `failed`, later stages still
  `pending`
- indexing-side failure (full mode), running mid-pipeline,
  cancelled mid-run
- `derive_effective_status`: returns `completed_with_warnings` only
  when a stage was skipped *with a non-trivial note*; pass-through
  for non-completed persisted states

### `test_partial_result_link.py`

Covers Problem 4 short-term fix in `TODO.md` — the partial-result
rescue link. PMET writes `<task_id>/pairing/motif_output.txt` before
the R heatmap and the zip stage; either of those late stages can fail
and flip the task to `failed`, hiding the scientific output that's
already on disk. The fix exposes a separate
`/api/tasks/{id}/partial-result` link when the file exists, without
changing `status` (so the failure remains visible).

Tests use `fastapi.TestClient` to drive the route handler with config
patched to a tmp dir:

- `_locate_motif_output` returns Path / None / None on present /
  missing / empty file
- `GET /tasks/{id}` surfaces `partial_result_link` only when
  `status==failed` AND `motif_output.txt` exists
- `GET /tasks/{id}/partial-result` streams the TSV with a sensible
  filename, 404s when the file or the task is missing

### `test_watchdog_staleness.py`

Covers the liveness watchdog (problem 2 in `TODO.md`). The watchdog
container scans `tasks/*.json` for `status==running` tasks whose
`progress.json` mtime exceeds `LIVENESS_TIMEOUT_SEC`, marks them failed
and process-tree-kills the bash subprocess.

Tests stub out the kill function and exercise:

- fresh task (recent progress) → not touched
- stale progress.json → killed, JSON marked failed with reason
- no progress.json yet, but old `started_at` → killed (catches
  pipelines that wedge before the first `emit_progress` call)
- non-running tasks (completed / failed / cancelled) → ignored
- malformed JSON → ignored
- threshold boundary (just under vs just over)
- missing `worker.pid` file → still mark failed, skip the kill silently

## Adding a new unit test

Convention:

1. One file per bug or invariant; name it `test_<topic>.{py,R}`.
2. The file must exit 0 on success, non-zero on any assertion failure.
3. Add a line to `run.sh` to invoke it.
4. Document the bug it covers (commit hash or `TODO.md` reference) in
   the file header.
5. Self-contained: no docker, no celery, no real motif data — use
   `unittest.mock`, fixture files inlined or generated on the fly.
