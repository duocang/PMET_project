# tests/audit

Generates the per-workflow audit docs at [`docs/workflows/`](../../docs/workflows/)
by **actually running each workflow** against canonical inputs and
filling a hand-written markdown template with verification data
captured from that run.

## Layout

```
tests/audit/
├── generate.py           driver: python3 tests/audit/generate.py [<name> ...]
├── lib.py                shared helpers (sha, run, render check table, …)
├── workflows/            one spec per workflow
│   ├── pair_only.py
│   ├── intervals.py
│   ├── promoter.py
│   └── elements.py
├── templates/            one markdown template per workflow
│   ├── pair_only.md      (uses <<PLACEHOLDER>> slots that the spec fills in)
│   ├── intervals.md
│   ├── promoter.md
│   └── elements.md
└── runs/                 each spec runs into runs/<name>/ (gitignored — see below)
```

Output lands at `docs/workflows/<name>.md`, which IS committed.

## How a single audit works

Each spec under `workflows/<name>.py` exports two functions:

```python
def run(repo_root: Path, runs_dir: Path) -> dict:
    """Execute the workflow against canonical inputs.
    Return a dict whose keys feed BOTH the verification checks and
    the template <<PLACEHOLDER>> substitutions."""

def checks(data: dict) -> list[Check]:
    """Render the verification table from the run dict."""
```

The driver:

1. Imports `workflows.<name>`, calls `spec.run()`. The workflow executes
   in a clean `runs/<name>/` subdir.
2. Calls `spec.checks(data)`. Each check produces a `(name, expected,
   actual, verdict)` row — verdicts are `PASS`, `FAIL`, or `WARN`.
3. Reads `templates/<name>.md`, substitutes every `<<KEY>>`
   placeholder with the corresponding `data[key]`. Two synthetic
   placeholders are always available: `<<CHECK_TABLE>>` (the rendered
   markdown table) and `<<OVERALL_VERDICT>>` (the one-line summary).
4. Writes the rendered markdown to `docs/workflows/<name>.md`.

## Running

```bash
python3 tests/audit/generate.py                  # all four
python3 tests/audit/generate.py promoter         # just one
python3 tests/audit/generate.py promoter intervals  # any subset
```

Wall time: pair_only ~15s, intervals ~16s, promoter ~2 min, elements ~5 min.

## Anchors and determinism

Some checks (`motif_output.txt deterministic vs anchor`) compare an
actual SHA-256 against a hard-coded "anchor" string captured on this
machine. These are **regression sentinels**: if the workflow's
implementation drifts, the SHA changes and the check FAILs. To bless
a new SHA after an intentional change, edit the anchor in the spec.

The anchors currently committed:

| workflow | anchor file | sha (first 16) |
|---|---|---|
| pair_only | `data/demos/promoters/pairing/demo` → `motif_output.txt` | `0af5b936606fd3` |
| intervals | `data/demos/intervals` → `motif_output.txt` | `4858412a091983` |
| promoter | TAIR10 + Franco-Zorrilla → `motif_output.txt` | `4b24906abfe55e` |
| elements | per-task `motif_output.txt` (one anchor per `data/genes/*.txt`) | see `TASK_ANCHORS` in `workflows/elements.py` |

`elements` carries one anchor per gene-task; tasks present in the dict
with a `None` value are "known but not yet blessed" — the first audit
run after this commit captures the real sha and emits a WARN with the
captured value, which a reviewer then pastes into `TASK_ANCHORS`. New
tasks (gene lists added later) appear as a separate WARN until added
to the dict.

(An older version of this README cited "C-engine non-determinism" as
the reason for omitting elements anchors. That justification was
stale — `elements.sh` now uses `index_fimo_fused`, which is
deterministic; the C-indexer caveat in `tests/baseline/README.md`
applies to a different workflow.)

## Cross-file invariants (independent of the script's own validator)

Three of the four workflows (promoter, intervals, elements) call
`pipeline/python/check_homotypic_contract.py` themselves at the end
of indexing. The audit ALSO runs an in-process equivalent — see
`lib.contract_invariant_checks(index_dir)` — so a future change that
skips or weakens the script-side validator still surfaces as audit
FAIL rows. The three checks emitted:

  - binomial_thresholds.txt motifs == IC.txt motifs
  - binomial_thresholds.txt motifs == fimohits/ basenames
  - IC.txt motifs == fimohits/ basenames

For pair_only the input index is `data/demos/promoters/pairing/demo`, which
intentionally ships only 6 fimohits files for ~110 binomial threshold
rows. The same three checks run there but at WARN severity (a real
mismatch you should know about, not a regression you should fix).

## Adding a workflow

1. Create `tests/audit/workflows/<name>.py` with `run()` and `checks()`.
2. Create `tests/audit/templates/<name>.md` with `<<PLACEHOLDER>>` slots
   for everything `run()` returns. Always include `<<CHECK_TABLE>>` and
   `<<OVERALL_VERDICT>>`.
3. Add `<name>` to `ALL_WORKFLOWS` in `generate.py`.
4. Run `python3 tests/audit/generate.py <name>` and verify the output
   markdown reads cleanly + every `<<UNRESOLVED:KEY>>` is gone.

## Why not pytest

The audit's purpose is **a human-readable, reviewable narrative** of
each workflow — purpose, biology, design intuition, observed results —
not a one-shot pass/fail signal. pytest would conflate the
verification checks with what's really a documentation generator. The
workflow audit and the regression baseline (`tests/baseline/`) live
side-by-side: the baseline is the machine-readable fingerprint set,
the audit is the prose explanation of what those fingerprints encode.

## What's NOT audited here

- `pipeline/workflows/cli/05_promoter_gap.sh` and the perf benchmarks
  (`01_perf_cpu`, `02_perf_params`) — these are research/perf scripts
  with one or two known callers; adding them to the audit is mechanical
  but low-priority.
- `apps/cli/scripts/*` (the lower-level `run_indexing.sh` /
  `run_pairing.sh` etc) — already covered by `tests/baseline/` which
  hashes their outputs against an anchor.
- `apps/pmet_backend/test_api.py` — covered separately by `pytest`
  inside the backend's docker image.
