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
