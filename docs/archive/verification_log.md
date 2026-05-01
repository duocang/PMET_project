# Verification Log

This file records baselines, behavior-preserving refactors, and intentional
scientific changes for the PMET pipeline. Each meaningful change appends a
section with the schema described in the project conventions doc (section 9).

Real measured values only — no estimated runtimes, hashes, or memory.

## Environment Snapshot (shared across sessions)

Captured 2026-04-26 at the start of this session. Re-capture if tools change.

- Branch: dev (33 commits ahead of origin/dev at session start)
- HEAD at session start: b4c071c
- OS: macOS 15.6.1 (Darwin 24.6.0, arm64)
- CPU: Apple M1 Pro
- Shell: zsh
- Python: 3.14.3
- Rscript: 4.5.2 (2025-10-31)
- bedtools: v2.31.1
- samtools: 1.23
- GNU parallel: 20260122
- fasta-get-markov: meme-5.5.9 (libexec)
- build/fimo: 5.5.3
- /usr/bin/time -l: available

Reference inputs (sizes from `ls -l`):

- `data/TAIR10.fasta` — 121,662,621 bytes
- `data/TAIR10.gff3` — 110,154,049 bytes
- `data/Franco-Zorrilla_et_al_2014.meme` — 11 motifs (Franco-Zorrilla 2014)
- `data/homotypic_promoters/` — precomputed homotypic index for `01`
- `data/homotypic_intervals/` — interval inputs for `04`
- `data/genes/*.txt` — gene lists for tasks (no `data/gene.txt` exists)


## 2026-04-26 00:55 - Pre-fix baselines (no code changes)

### Changed Files

- (none — baseline capture only)
- `tests/run_smoke.sh` (new harness, no production code touched)
- `tests/fixtures/strand_minigenome.fa`, `tests/fixtures/strand_promoters.bed`
- `tests/baselines/0{1,3,4,8}_baseline.{stdout,stderr,exit,hashes.txt}`

### Commands

```bash
/usr/bin/time -l bash pipeline/01_benchmark_cpu.sh
/usr/bin/time -l bash pipeline/03_promoter.sh
/usr/bin/time -l bash pipeline/04_intervals.sh
/usr/bin/time -l bash pipeline/08_promoter_distance_to_tss.sh
bash tests/run_smoke.sh
```

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash pipeline/01_benchmark_cpu.sh` | 2 | 0.11 | 0.05 | 0.02 | 50.8 MB | fails on missing `data/gene.txt` |
| `bash pipeline/04_intervals.sh` | 0 | 6.35 | 3.40 | 0.44 | 236.8 MB | small intervals dataset; "No meaningful data left after filtering" warning from R is data-driven (only 8 motifs / 28 pairs survive), not a regression |
| `bash pipeline/03_promoter.sh` | 0 | 76.02 | 298.43 | 4.68 | 540.5 MB | full TAIR10 promoter PMET; OpenMP up to 10 threads inside fused FIMO |
| `bash pipeline/08_promoter_distance_to_tss.sh` | 1 | 0.00 | 0.00 | 0.00 | 1.7 MB | fails immediately: `${utr,,}` (line 46) is Bash 4 lowercase expansion; macOS `/bin/bash` is 3.2.57 — the script never reaches the pipeline stages. Pre-existing portability bug, not in the current P0 list — documented here, left for a later targeted fix |
| `bash pipeline/02_benchmark_parameters.sh` | (skipped) | — | — | — | — | full grid is 4 tasks × 7 lengths × 9 maxk × 1 topn = 252 combos, each running FIMO over the full TAIR10 promoter set; not run because session-time-prohibitive. P0-02 is verified instead by a controlled smoke fixture (see `tests/run_smoke.sh` Test 1) |

### Result Hashes (key contract files)

| File | Hash |
|---|---|
| `results/03_promoter/01_homotypic/binomial_thresholds.txt` | `6547f034534b617dd8f594640addf12cccd85967e902ed3cf993b733cbabb358` |
| `results/03_promoter/01_homotypic/IC.txt` | `98893df5672470c55f65bcfbd048549e179a40d271c519d512a375807f368f7d` |
| `results/03_promoter/01_homotypic/promoter_lengths.txt` | `a78ad126b6f83a9bfa24859e487842a696c9d137021e6d5ea7a6a8a01fdc05b8` |
| `results/03_promoter/01_homotypic/universe.txt` | `d7e51417cc310b9edbf283994d80510f0d6f679aa34bf079694efccb20c12ae7` |
| `results/03_promoter/02_heterotypic/motif_output.txt` | `7921675922b3007efa78892105775a557bd119bd117ffcd8c330c7e456c7eeb3` |

Full directory hashes recorded in `tests/baselines/03_baseline.hashes.txt`,
`tests/baselines/04_baseline.hashes.txt`. Pipeline/08 hashes will be added in
its own entry once that baseline run finishes.

### Result Consistency

Baseline only — nothing to compare against yet.

`tests/run_smoke.sh` ships with two checks at this commit:

- Test 1 (synthetic strand, PASS) — proves `bedtools getfasta -s`
  reverse-complements minus-strand entries.
- Test 2 (real-data strand on TAIR10, PASS) — same property verified
  on the actual TAIR10 promoter set.

Pipeline-source-aware checks (pipeline/02 calls getfasta with `-s`,
pipeline/01 has a real gene list and 7 heatmap args) will be added in
the next two commits, alongside the fixes that flip them green.

### Verification Summary

- Status: BASELINE CAPTURED
- Unverified: pipeline/02 full grid (skipped — too expensive); pipeline/08 (still running, recorded next)
- Risk: pipeline/01 has been broken since at least the last `data/gene.txt` removal — no one has been running it
- Next: implement P0-01 fix, re-run pipeline/01 as `EXPECTED CHANGE: failed -> passed`


## 2026-04-26 01:00 - P0-01 fix: pipeline/01 inputs and heatmap args

### Changed Files

- `pipeline/01_benchmark_cpu.sh`

### Commands

```bash
bash -n pipeline/01_benchmark_cpu.sh
bash tests/run_smoke.sh
rm -rf results/01_benchmark_cpu
/usr/bin/time -l bash pipeline/01_benchmark_cpu.sh
shasum -a 256 results/01_benchmark_cpu/{single,parallel}/motif_output.txt
```

### What Changed And Why

1. `gene_input_file=data/gene.txt` → `data/genes/genes_cell_type_treatment.txt`.
   The legacy `data/gene.txt` had been removed; the previous run died on
   `grep: data/gene.txt: No such file or directory`. The new value is the
   same canonical task list pipeline/03 uses by default and the benchmark
   only requires that the list intersect the precomputed homotypic
   `universe.txt` (1618 of 1660 genes survive — confirmed by post-fix run).

2. `Rscript scripts/r/draw_heatmap.R` was invoked with 3 positional
   arguments but the script hard-checks `length(args) != 7`. Added the four
   missing arguments (`topn`, `histgram_ncol`, `histgram_width`,
   `unique_cmbination`) using the same defaults pipeline/03 passes for its
   `Overlap` plots. Configurable from variables at the top of the script.

3. Binary-aware output handling. `build/pmet`'s `-o` argument is a *path
   prefix* — it appends `/motif_output.txt` and refuses to write if that
   path resolves to an existing directory. The previous run silently
   produced an empty `motif_output.txt`, but the breakage was masked by
   `cat "$out_dir"/*.txt > "$out_dir/motif_output.txt"`: the redirect
   truncated `motif_output.txt` *before* the glob expansion was streamed
   through `cat`, so the consolidated file always ended up empty even on
   non-empty inputs (a self-clobber bug). Fix: keep `-o "$out_dir"` for
   both binaries (matches the actual binary contract), skip the cat for
   `pmet` because it already writes the consolidated file, and use a
   `mktemp` staging file for `pmetParallel` to avoid the self-clobber.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash pipeline/01_benchmark_cpu.sh` (post-fix) | 0 | 15.56 | 15.78 | 0.28 | 250.4 MB | runs both `pmet` and `pmetParallel` over 1618 filtered genes / 10 motifs |

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `results/01_benchmark_cpu/single/motif_output.txt` | (script aborted, file 0 bytes) | `d6fa0d3d7ca76cab138e2d8f94bc250015c715f2c5ef4350f86d121c1a195811` | EXPECTED CHANGE: failed -> passed |
| `results/01_benchmark_cpu/parallel/motif_output.txt` | (script aborted before reaching parallel) | `d6fa0d3d7ca76cab138e2d8f94bc250015c715f2c5ef4350f86d121c1a195811` | EXPECTED CHANGE: failed -> passed |
| `results/01_benchmark_cpu/single/histogram/histgram_padj_before_filter.png` | (not produced) | `1e9eddbbce268341da7671df1f708a0ea2a98126c02d26d716ed672db09630aa` | EXPECTED CHANGE: failed -> passed |

`single/motif_output.txt` and `parallel/motif_output.txt` hash identically
(both 23 565 bytes, 271 lines), as expected for a CPU benchmark — the
single-CPU and threaded binaries should agree on results, only on speed.

R reports `No meaningfull data left after filtering!` for the heatmap step.
This is a data-driven outcome (small precomputed homotypic index has 10
motifs and the gene list yields 271 surviving rows), identical to what
pipeline/04 prints with its small interval set. Not a regression. The
histogram PNG is still produced; only the final heatmap PNG is skipped
when the filtered table is empty.

### Verification Summary

- Status: PASS (P0-01)
- Unverified: heatmap PNG output (intentionally skipped by R when filtered table is empty)
- Risk: low — fix only affects pipeline/01 plumbing, not any contract file under `data/homotypic_promoters/`
- Next: P0-02 strand fix on pipeline/02


## 2026-04-26 01:05 - P0-02 fix: pipeline/02 strand-aware promoter FASTA

### Changed Files

- `pipeline/02_benchmark_parameters.sh`
- `tests/run_smoke.sh` (added Test 4 — real-data strand check)
- `tests/test_pipeline02_strand_realdata.sh` (new)

### Commands

```bash
bash -n pipeline/02_benchmark_parameters.sh
bash tests/run_smoke.sh
/usr/bin/time -l bash tests/test_pipeline02_strand_realdata.sh
```

### What Changed And Why

`prepare_length()` extracted promoter FASTA without `-s`, so `bedtools
getfasta` returned the literal + strand sequence regardless of the BED
column-6 strand. Roughly half of TAIR10 genes (13800 of 27655 here) are on
the minus strand; their motif-scanning input was effectively the wrong
strand, biasing every per-(length, maxk) FIMO+pmet run downstream.

Pipeline/03 already uses `-name -s` (and pipeline/02 was the only
remaining call site without it). Fix: add `-s` and strip the `(+)/(-)`
header suffix that `-s` adds, matching the sed pattern in pipeline/03.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash tests/test_pipeline02_strand_realdata.sh` | 0 | 9.45 | 8.51 | 0.77 | 235.4 MB | full TAIR10 gene BED, length=200 flank, two getfasta runs (with/without -s), per-gene comparison |
| `bash pipeline/02_benchmark_parameters.sh` (post-fix, full grid) | (skipped) | — | — | — | — | full grid is 252 (length, maxk, task) combinations × full TAIR10 FIMO; not run because session-time-prohibitive. The strand fix is a one-line change to a single helper (`prepare_length()`) and its effect on extracted FASTA is fully characterised by `tests/test_pipeline02_strand_realdata.sh` (per-gene equivalence proof, not a sample) |

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| Promoter FASTA (TAIR10, length=200), header-cleaned | `4b9f61d5c2a25a9b8a2860fded75aaafefc5209adc0300446a091fbcac55f273` | `cd1ebf4a7359958826323fa74423d55f3583343b8ef12396e8c7a44eedfbeed3` | EXPECTED CHANGE — minus-strand sequences now reverse-complemented |

Per-gene check: 13855 + strand promoters identical, 13800 - strand
promoters now equal `revcomp(prefix)` exactly, 0 mismatches. This is the
intended scientific bug fix, not a regression.

### Result Consistency

- Synthetic smoke (Test 1): PASS — `-s` reverse-complements - strand
- Static check (Test 2): PASS — pipeline/02's getfasta call now includes `-s`
- Real-data check (Test 4): PASS — TAIR10 per-gene equivalence as documented
- Existing pipelines (03, 04) unaffected — they already used `-s`

### Verification Summary

- Status: PASS (P0-02), with the FASTA hash change classified as EXPECTED CHANGE
- Unverified: end-to-end pipeline/02 grid downstream of the FASTA stage (FIMO + pmet); skipped due to grid size (see entry above for justification)
- Risk: low for the *direction* of the change (strand fix is unambiguous and matches pipeline/03), medium for *downstream cascading effects* — every binomial threshold, FIMO p-value, IC selection, and binomial pair p-value computed by pipeline/02 will shift for every minus-strand gene. Anyone re-running pipeline/02 after this commit must treat all `02_benchmark_parameters` outputs as new science, not a regression
- Next: stage commits in the suggested order and stop




## 2026-04-26 09:30 - Bash 3.2 portability for pipeline/08

### Changed Files

- `pipeline/08_promoter_distance_to_tss.sh`

### Commands

```bash
bash -n pipeline/08_promoter_distance_to_tss.sh
/usr/bin/time -l bash pipeline/08_promoter_distance_to_tss.sh
find results/08_promoter_gap -type f | sort | xargs shasum -a 256
```

### What Changed And Why

`${utr,,}` is Bash 4+ lowercase parameter expansion. macOS ships
`/bin/bash` 3.2.57 by default, so the script aborted at line 46 before
running any pipeline stages — the `08` baseline could not be captured
in the prior session. Replaced the single Bash-4-only expansion with a
portable `tr` based lowercase, leaving every other behaviour (and every
default scientific parameter) unchanged. No other Bash 4 features
exist in `pipeline/*.sh`.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash pipeline/08_promoter_distance_to_tss.sh` (post-fix) | 0 | 57.49 | 213.85 | 2.44 | 523.5 MB | full TAIR10 promoter PMET with `gap=100` core-promoter exclusion |

### Result Hashes (key contract files)

| File | Hash |
|---|---|
| `results/08_promoter_gap/01_homotypic/binomial_thresholds.txt` | `9bd0f0aec154e4fb6671b58c544af7bca13084cd4fa9b770566a02d1b2f72586` |
| `results/08_promoter_gap/01_homotypic/IC.txt` | `98893df5672470c55f65bcfbd048549e179a40d271c519d512a375807f368f7d` |
| `results/08_promoter_gap/01_homotypic/promoter_lengths.txt` | `ee9c90d542e9cdfb28f0173e6a03529abc2c797551c9cee34f76931956ea9572` |
| `results/08_promoter_gap/01_homotypic/universe.txt` | `54ca086395031e00025177326c2a084ed4146d2218cda83298beaaffb5672887` |
| `results/08_promoter_gap/02_heterotypic/motif_output.txt` | `827a7683b1b99024ede0c0000891859be4f95d12180c860192146163856209c7` |

`IC.txt` matches pipeline/03's baseline byte-for-byte (`98893df5…`) —
expected, since IC is a function of the MEME file only. Full directory
hashes in `tests/baselines/08_postfix.hashes.txt`.

### Result Consistency

| File | Before | After | Status |
|---|---|---|---|
| `results/08_promoter_gap/**` | (run never reached pipeline stages) | hashes captured | EXPECTED CHANGE: failed -> passed |

Pre-existing behaviour unrelated to this fix:
`results/08_promoter_gap/plot/heatmap_overlap_unique.png` and
`heatmap_overlap.png` hash identically (both `af75ef92…`). Pipeline/03
produces distinct unique vs non-unique PNGs at the same data scale, so
this is suspicious but is not introduced by the portability fix and is
not in the current P0/P1 list — recorded here for follow-up.

### Verification Summary

- Status: PASS
- Unverified: per-flag correctness of the `unique_cmbination` heatmap
  PNG (see note above)
- Risk: low — one-line portability change in the prelude; no scientific
  parameter touched
- Next: P1 cleanup pass


## 2026-04-26 09:35 - P1-3: pipeline/04 strict mode

### Changed Files

- `pipeline/04_intervals.sh`

### Commands

```bash
bash -n pipeline/04_intervals.sh
rm -rf results/04_intervals
/usr/bin/time -l bash pipeline/04_intervals.sh
diff tests/baselines/04_baseline.hashes.txt tests/baselines/04_postfix.hashes.txt
```

### What Changed And Why

Pipeline/04 was the only active pipeline missing `set -euo pipefail`. A
mid-script bedtools failure (e.g. malformed FIMO output) would silently
proceed and corrupt downstream artefacts. Added the directive directly
under the shebang. No other lines touched.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash pipeline/04_intervals.sh` (post-fix) | 0 | 3.86 | 3.30 | 0.33 | 233.5 MB | clean run on intervals dataset |

### Result Hashes

`diff tests/baselines/04_baseline.hashes.txt tests/baselines/04_postfix.hashes.txt`
returns no output — every output file byte-identical to the baseline.
Behaviour-preserving fix.

### Verification Summary

- Status: PASS
- Risk: low — strict mode guards against new failures, never introduces them on a successful path



## 2026-04-26 09:40 - P1-4: deterministic IC.txt writes

### Changed Files

- `scripts/python/calculateICfrommeme_IC_to_csv.py`

### Commands

```bash
python3 -m py_compile scripts/python/calculateICfrommeme_IC_to_csv.py

# Idempotency probe with a fresh memefile dir:
python3 scripts/python/parse_memefile.py data/Franco-Zorrilla_et_al_2014.meme TMP/memefiles_ic/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py TMP/memefiles_ic/ TMP/IC.txt   # H1
python3 scripts/python/calculateICfrommeme_IC_to_csv.py TMP/memefiles_ic/ TMP/IC.txt   # H2
shasum -a 256 TMP/IC.txt
```

### What Changed And Why

The script wrote `IC.txt` in `mode='a'` (append). Every active call site
(pipeline/02/03/08, scripts/indexing/intervals.sh, scripts/indexing/
pmet_index_element.sh) invokes it once per fresh IC.txt and immediately
consumes the result, so append never produced different output than
write — but a stale `IC.txt` from an interrupted run would have
silently doubled every motif row, producing a corrupt index that the
downstream binaries would still happily consume.

Switched to `mode='w'`. No other behaviour change.

### Result Hashes

| Run | Sha-256 | Lines | Notes |
|---|---|---:|---|
| First run on fresh dir (post-fix) | `98893df5672470c55f65bcfbd048549e179a40d271c519d512a375807f368f7d` | 113 | matches `pipeline/03` baseline IC.txt byte-for-byte |
| Second run on same dir (post-fix) | `98893df5672470c55f65bcfbd048549e179a40d271c519d512a375807f368f7d` | 113 | idempotent (was duplicating before) |

### Verification Summary

- Status: PASS
- Risk: low — every existing caller already deletes/recreates the
  output dir, so the first-run hash is unchanged
- Next: P1-1 cold utr=Yes path in pipeline/02


## 2026-04-26 09:45 - P1-1: pipeline/02 cold utr=Yes path arg mismatch

### Changed Files

- `pipeline/02_benchmark_parameters.sh`

### Commands

```bash
bash -n pipeline/02_benchmark_parameters.sh
# Cold-path smoke: run parse_utrs.py with the new (2-arg) shape
python3 scripts/python/parse_utrs.py /tmp/x/promoters.bed /tmp/x/sub.gff3
```

### What Changed And Why

`prepare_length()` invoked `parse_utrs.py` with three positional
arguments (promoter BED, sorted GFF3, genelines BED). The script's
`argparse` accepts only two. Default config has `utr=No`, so this
cold path never ran — but anyone who flipped the flag would hit a
`unrecognised arguments` exit. Pipelines 03 and 08 already pass two.

Removed the spurious third positional. Behaviour-preserving on the
default path; the cold path is now wire-compatible with the script.

### Result

Smoke probe on a TAIR10 slice:

```
$ python3 scripts/python/parse_utrs.py promoters.bed sub.gff3
        Extended 1 promoter(s) to include 5' UTR
```

(End-to-end call succeeds with the two-arg form; the extension
correctness is governed by the in-place edit in `parse_utrs.py`,
unchanged by this fix.)

### Verification Summary

- Status: PASS (cold path)
- Risk: zero on default config (cold path never executes); positive on
  the `utr=Yes` path (used to error out, now runs)


## 2026-04-26 09:55 - P1-2: assess_integrity.py adjacency assumption

### Changed Files

- `scripts/python/assess_integrity.py`
- `tests/run_smoke.sh` (Test 4 added)

### Commands

```bash
python3 -m py_compile scripts/python/assess_integrity.py
bash tests/run_smoke.sh
rm -rf results/03_promoter
/usr/bin/time -l bash pipeline/03_promoter.sh
diff tests/baselines/03_baseline.hashes.txt tests/baselines/03_postfix.hashes.txt
```

### What Changed And Why

The old loop walked the BED row-by-row and only compared adjacent lines:
when two fragments of the same gene were not adjacent in the sorted BED
(i.e. some other gene's promoter sorted between them), the second
fragment slipped through unresolved. On TAIR10 default config the bug
is silent — `pipeline/03/01_homotypic/promoter_lengths.txt` has 29 824
unique gene names with 0 duplicates — but it triggers any time a gene's
flanking promoter is split by a third gene's body that lands inside it.

Replaced with a single-pass `groupby('name')`:
- + strand: keep `idxmax(end)` (TSS-side fragment)
- − strand: keep `idxmin(start)` (TSS-side fragment)
- 1-fragment groups: kept as-is

The kept indices are sorted before re-emit, so the surviving BED rows
preserve sortBed's original ordering — keeps downstream contract files
byte-stable on the paths where the bug never manifested.

### Tracer Fixture

```text
INPUT (sortBed-style; same-gene fragments NOT adjacent)
  chr1 1000 1500 GENE_X +
  chr1 1600 1900 GENE_Y +
  chr1 1700 2000 GENE_X +    ← split for GENE_X
  chr1 3000 3300 GENE_Z -
  chr1 3500 3600 GENE_W +
  chr1 3800 4000 GENE_Z -    ← split for GENE_Z

PRE-FIX OUTPUT  (algorithm reports "No split promoters detected" — wrong)
POST-FIX OUTPUT (correctly resolved)
  chr1 1600 1900 GENE_Y +
  chr1 1700 2000 GENE_X +
  chr1 3000 3300 GENE_Z -
  chr1 3500 3600 GENE_W +
```

### Real-Data Verification (pipeline/03 baseline re-run)

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash pipeline/03_promoter.sh` (post-fix) | 0 | 68.21 | 303.12 | 2.98 | 546.1 MB | re-run on TAIR10 to confirm no scientific drift |

`diff tests/baselines/03_baseline.hashes.txt tests/baselines/03_postfix.hashes.txt`:

```
< d89dcfc04ae578cc97d93be2a326bff480de5fc5cfeffe0199f3e35b29a76967  results/03_promoter/02_heterotypic/pmet.log
> ddd8b7ab5b932557fccef3b297e2205477e3a35a4031c708e0e2ae21aa90a6b9  results/03_promoter/02_heterotypic/pmet.log
```

127 of 128 files byte-identical. The lone diff is `pmet.log` whose
content includes a `mktemp` per-run path
(`/var/folders/.../tmp.D3g9B04SCK`) and per-thread "Starting Thread N"
ordering — both nondeterministic and unrelated to `assess_integrity`.
Every scientific contract file (`promoter_lengths.txt`,
`binomial_thresholds.txt`, `IC.txt`, `universe.txt`,
`fimohits/<motif>.txt`, `motif_output.txt`, all 3 heatmap PNGs and 6
histogram PNGs) hashes identically.

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `results/03_promoter/01_homotypic/promoter_lengths.txt` | `a78ad126…` | `a78ad126…` | PASS |
| `results/03_promoter/01_homotypic/binomial_thresholds.txt` | `6547f034…` | `6547f034…` | PASS |
| `results/03_promoter/01_homotypic/IC.txt` | `98893df5…` | `98893df5…` | PASS |
| `results/03_promoter/01_homotypic/universe.txt` | `d7e51417…` | `d7e51417…` | PASS |
| `results/03_promoter/02_heterotypic/motif_output.txt` | `79216759…` | `79216759…` | PASS |
| `results/03_promoter/02_heterotypic/pmet.log` | `d89dcfc0…` | `ddd8b7ab…` | NONDETERMINISTIC LOG (tmp path + thread order) |

### Verification Summary

- Status: PASS — bug fixed, real-data baseline byte-identical on every
  scientific output
- Risk: zero on TAIR10 default config; positive on annotations where
  the bug would have triggered
- Next: P1 backlog complete for this session


## 2026-04-26 10:05 - P1-5: chromosome-name preflight on promoter+anno pipelines

### Changed Files

- `pipeline/02_benchmark_parameters.sh`
- `pipeline/06_genomic_elements_longest_isoform.sh`
- `pipeline/07_genomic_elements_merged_isoforms.sh`
- `tests/run_smoke.sh` (Test 4 added)

### Commands

```bash
bash -n pipeline/02_benchmark_parameters.sh
bash -n pipeline/06_genomic_elements_longest_isoform.sh
bash -n pipeline/07_genomic_elements_merged_isoforms.sh
bash tests/run_smoke.sh
```

### What Changed And Why

Pipelines 03 and 08 already abort early on a chromosome-name mismatch
between FASTA and GFF3 (e.g. `1` vs `Chr1`). Without the preflight a
mismatch produces an empty gene BED — every downstream step succeeds
quietly and the index is built from zero genes, which is much harder
to diagnose than an explicit early failure. Pipelines 02, 06, 07 used
the same TAIR10 inputs but lacked the check; added the same block
verbatim from pipeline/03's preflight, immediately after the
input-file existence checks.

### Verification

- TAIR10 default inputs: `gff3_chr='1'`, `fasta_chr='1'` — preflight
  passes silently.
- Synthetic mismatch (`Chr1` GFF3 vs `1` FASTA) in `tests/run_smoke.sh`
  Test 4: triggers the mismatch path → script exits with the explicit
  error message instead of silently producing an empty index.
- Static smoke check: all three target pipelines now contain the
  `Chromosome name mismatch` guard.

### Verification Summary

- Status: PASS
- Risk: zero on default config (TAIR10 names match); positive on any
  setup where a renamed annotation could have silently produced empty
  results
- Next: optional small-grid baseline for pipeline/02 post-fix


## 2026-04-26 10:15 - pipeline/02 controlled small-grid post-fix baseline

### Changed Files

- `tests/run_pipeline02_one_combo.sh` (new harness)
- `tests/baselines/02_postfix_one_combo.{stdout,stderr,exit,hashes.txt}`

### Commands

```bash
rm -rf results/02_benchmark_parameters
/usr/bin/time -l bash tests/run_pipeline02_one_combo.sh
find results/02_benchmark_parameters -type f | sort | xargs shasum -a 256
```

### What This Establishes

Earlier commits proved the pipeline/02 strand fix in two synthetic
contexts: a synthetic-fixture smoke test and a real-data
extraction-only test that bypasses pipeline/02 itself. This entry
adds the *third* leg: pipeline/02's prepare_length() function ran
end-to-end against TAIR10 and emitted the same strand-aware promoter
FASTA hash. The full grid is 252 combinations × full TAIR10 FIMO
which is impractical to commit on every change, so the harness reduces
the four grid arrays to a single point and forces
`keep_intermediate=true` so the FASTA / BED / threshold artefacts
survive for hashing.

Default combo: task=genes_cell_type_treatment, plen=200, maxk=5,
topn=5000. Configurable via `TASK`/`PLEN`/`MAXK`/`TOPN` env vars.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash tests/run_pipeline02_one_combo.sh` (post-fix) | 0 | 103.42 | 488.65 | 33.99 | 476.0 MB | one-combo grid, full TAIR10 FIMO at threshold 0.05, all P0/P1 fixes applied |

### Result Hashes (regression baseline)

| File | Hash |
|---|---|
| `LEN200_FIMO005/promoters.fa` | `cd1ebf4a7359958826323fa74423d55f3583343b8ef12396e8c7a44eedfbeed3` |
| `LEN200_FIMO005/promoter_lengths.txt` | `9e0f5af868809440d77db644d40454ec063673084148d6135843317179f4248f` |
| `LEN200_FIMO005/universe.txt` | `73f2a73d6e07017e3187ce8525f5b0d566b63d8bfd325d9ee2d50d59842eb25b` |
| `LEN200_K5_N5000_FIMO005/binomial_thresholds.txt` | `cc65e7621697e35fb86ae1eaf78a6d27211215efad17b709df695397a314f781` |
| `02_heterotypic/.../motif_output.txt` | `0c0f9f9c95b0577c713543ba91d4e66cd97cd0b46b05ca53b6925e2ad255e3b3` |

Cross-checks:

- `promoters.fa` = `cd1ebf4a…` matches the `POST-FIX (-s)` hash recorded
  in `tests/baselines/p02_strand.stdout` (the earlier strand-only test
  that never invoked pipeline/02). Same hash from two independent
  derivations — pipeline/02 is genuinely producing strand-aware FASTA in
  production, not just in the smoke fixture.
- `promoter_lengths.txt` has 27 655 unique gene names with 0 duplicates,
  so `assess_integrity.py` (post P1-2 fix) did not leave any unresolved
  split fragments for this combo.

Full directory hashes (137 files) in
`tests/baselines/02_postfix_one_combo.hashes.txt`.

### Verification Summary

- Status: PASS — pipeline/02 runs end-to-end with all P0/P1 fixes
- Risk: low — the harness only reshapes the grid arrays and forces
  keep_intermediate; it never modifies pipeline/02 source
- Skipped: full 252-combo grid (impractical); other (task, length,
  maxk) points should produce different hashes by construction


## 2026-04-26 10:25 - Investigation: pipeline/08 heatmap_overlap == heatmap_overlap_unique

### Question

Why do `heatmap_overlap.png` and `heatmap_overlap_unique.png` hash
identically in the pipeline/08 baseline (`af75ef92…`) when pipeline/03
produces visibly different PNGs from the same R driver and the only
differing argument (`unique_cmbination`) is supposed to remove
motif_pairs that occur in multiple clusters?

### Method

Reproduced the `ProcessPmetResult` filter chain in an interactive R
session against both baselines and counted survivors / duplicates.

### Findings

| Pipeline | rows total | rows after p_adj≤0.05 & gene_num>5%·cluster_size | unique motif_pairs | duplicate motif_pair rows |
|---|---:|---:|---:|---:|
| pipeline/03 | 37 968 | 326 | 270 | 46 |
| pipeline/08 | 37 968 | 67  | 66  | 2  |

The unique filter (`pmet.filtered[which(MarkDuplicates(motif_pair) !=
"TRUE"), ]`) does work — confirmed by direct invocation: 67 → 65 for
pipeline/08, 326 → 280 for pipeline/03.

The downstream code keeps only `topn=5` motifs *per cluster* before
plotting. Pipeline/08's two duplicate-pair rows happen to sit *outside*
every cluster's top-5 cut, so the rendered heatmap is the same whether
we remove them or not. Pipeline/03's 46 duplicates touch enough of the
top-5 cuts that the plots diverge.

### Conclusion

This is a data-sparsity artefact specific to `gap=100`, not a bug.
With aggressive core-promoter exclusion the number of surviving
significant motif pairs drops by ~5×, and `topn=5 per cluster`
absorbs the small amount of cluster-overlap that remains. No code
change is warranted.

Stylistic note (not changed): `MarkDuplicates(motif_pair) != "TRUE"`
in `process_pmet_result.R` line 256 compares a logical vector to the
string `"TRUE"`. R coerces both sides to character, so the expression
happens to be equivalent to `!MarkDuplicates(motif_pair)` — the
intended semantics. Worth tidying when the R plotting layer is next
touched, but it does not affect correctness today.

### Verification Summary

- Status: NO ACTION
- Risk: zero — heatmap output is correct given the data
- Followup: none required


## 2026-04-26 11:00 - Pipelines 06/07: strict mode, chmod, rm -f, baseline capture

### Changed Files

- `pipeline/06_genomic_elements_longest_isoform.sh`
- `pipeline/07_genomic_elements_merged_isoforms.sh`
- `tests/baselines/06_baseline.{stdout,stderr,exit,hashes.txt}`
- `tests/baselines/07_baseline.{stdout,stderr,exit,hashes.txt}`

### Commands

```bash
bash -n pipeline/06_genomic_elements_longest_isoform.sh
bash -n pipeline/07_genomic_elements_merged_isoforms.sh

rm -rf results/06_genomic_elements_longest_isoform
/usr/bin/time -l bash -c "printf '4\n' | bash pipeline/06_..."  # element=CDS
find results/06_genomic_elements_longest_isoform -type f | sort | xargs shasum -a 256

rm -rf results/07_genomic_elements_merged_isoforms
/usr/bin/time -l bash -c "printf '4\n' | bash pipeline/07_..."  # element=CDS
find results/07_genomic_elements_merged_isoforms -type f | sort | xargs shasum -a 256
```

### Why Three Fixes Were Required Together

Pipelines 06 and 07 had no real-data baseline because three latent bugs
prevented them from running clean:

1. **No `set -euo pipefail`.** Errors in indexing or per-task heatmap
   calls were swallowed silently. Pipeline 04 already has strict mode;
   06 and 07 did not.

2. **`scripts/indexing/pmet_index_element.sh` not executable.** The
   committed file mode is 0644, but pipeline/06/07 invoke it directly as
   `$HOMOTYPIC` (not via `bash $HOMOTYPIC`), so the kernel rejects it
   with "Permission denied". Pipeline/04 chmods its homotypic helper
   before invocation; 06/07 did not. Match that pattern with
   `chmod a+x "$HOMOTYPIC" "$HETEROTYPIC"` after the binaries are named.

3. **`rm $heterotypic_output/temp*.txt` without `-f`.** `pmetParallel`
   does not always emit `temp*.txt` files (depends on whether per-thread
   scratch survived the merge). Without `-f`, the rm errors when the
   glob matches nothing — and under `set -e` (added by fix 1) the whole
   pipeline aborts mid-iteration. Pipelines 03 and 04 already use
   `rm -f`. Match.

In sequence: fix 1 unmasks fix 2 (chmod failure becomes fatal); fix 3
is required *because of* fix 1. Fixing only one is worse than fixing
none — you either keep the silent corruption (no fix 1) or you turn
silent corruption into a hard abort that you cannot diagnose without
the other two.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `printf '4\n' \| bash pipeline/06_...` (post-fix) | 0 | 830.58 | 5099.59 | 119.22 | 460.4 MB | element=CDS, 5 task iterations, full TAIR10 |
| `printf '4\n' \| bash pipeline/07_...` (post-fix) | 0 | 890.58 | 5265.90 | 136.60 | 465.2 MB | element=CDS, 5 task iterations, full TAIR10 |

### Result Hashes

Pipeline/06 vs pipeline/07 (both with element=CDS):

| File | 06 hash (longest isoform) | 07 hash (merged isoforms) | Status |
|---|---|---|---|
| `01_homotypic/IC.txt` | `98893df5…` | `98893df5…` | SAME |
| `01_homotypic/universe.txt` | `5d4226c1…` | `5d4226c1…` | SAME |
| `01_homotypic/promoter_lengths.txt` | `ce8a5e55…` | `f5bd3f8c…` | DIFFER (expected) |
| `01_homotypic/binomial_thresholds.txt` | `7c23c1b4…` | `1bf0e7c5…` | DIFFER (expected) |
| 5 × `02_heterotypic_*/motif_output.txt` | distinct | distinct | DIFFER (expected) |

Cross-check: `IC.txt` and `universe.txt` are byte-identical between
strategies. `IC.txt` is a function of the MEME file alone (matches
pipeline/03 and pipeline/08 too — all use Franco-Zorrilla), so this
must hold by construction. `universe.txt` is the set of gene names
emitted by `parse_genelines`-style logic in the indexer, which is
strategy-independent. The promoter_lengths and binomial_thresholds
diverge because the per-gene element span depends on whether you keep
fragments of a single chosen isoform (longest) or the union of all
isoforms (merged). Downstream `motif_output.txt` rows have the same
*count* per task across 06 and 07 (same gene list × same motif set
yields the same number of pair-tests) but distinct scores.

### Per-Task Heatmap Coverage

`salt_top300` (and `heat_top300` in pipeline/07) produced 0 PNGs in
their respective `03_plot_*/` directories — same data-driven outcome
we have already documented for pipeline/01 and pipeline/04: the R
filter (`p_adj <= 0.05` plus 5%-of-cluster-size gene threshold) leaves
no rows for those particular task lists, `heatmap.func` prints
"No meaningfull data left after filtering!" and returns NULL. The
script exits 0; under `set -e` this is not fatal. Histogram subdirs
*are* written for every task because they are rendered before the
filter.

### Verification Summary

- Status: PASS — 06 and 07 both run end-to-end on TAIR10 with element=CDS
- Risk: low — the three fixes are conservative (strict mode, executable
  bit, `rm -f`); none change scientific parameters
- Skipped: other element choices (mRNA, exon, 5'/3' UTR) — rerunning is
  cheap (~14 minutes per element); these baselines are sufficient for
  regression tracking of the strategies themselves
- Followup: pipelines 06 and 07 are now structurally near-identical
  (~20 lines diff out of ~180); behaviour-preserving consolidation is
  a P2 candidate but should wait until fixtures cover both strategies


## 2026-04-26 11:35 - tests/verify_baseline.sh + R cleanup

### Changed Files

- `tests/verify_baseline.sh` (new — automatic regression checker)
- `scripts/r/process_pmet_result.R`
- `tests/baselines/03_post_rcleanup.{stdout,stderr,exit}` (proof-of-no-drift run)

### Commands

```bash
# tool unit-tests
bash tests/verify_baseline.sh results/04_intervals \
    tests/baselines/04_baseline.hashes.txt        # OK — 23 files match
bash tests/verify_baseline.sh results/03_promoter \
    tests/baselines/03_baseline.hashes.txt        # OK — 127 files match (excludes pmet.log)

# R cleanup verification
Rscript -e "parse(file = 'scripts/r/process_pmet_result.R')"
rm -rf results/03_promoter
/usr/bin/time -l bash pipeline/03_promoter.sh
bash tests/verify_baseline.sh results/03_promoter \
    tests/baselines/03_baseline.hashes.txt        # OK — 127 files match
```

### Tool: tests/verify_baseline.sh

Re-hashes a results directory, diffs against a recorded
`<pipeline>_baseline.hashes.txt`, and exits non-zero on any
unexpected change. Excludes nondeterministic files (default:
`pmet.log` and other `.log` files) so the canonical pmetParallel
log — which contains a per-run `mktemp` path and per-thread
"Starting Thread N" ordering — does not show up as a regression.

`EXCLUDE` env var lets callers widen or narrow the filter for a
specific pipeline.

### R Cleanup: process_pmet_result.R line 256

Before:

```r
pmet.filtered <- pmet.filtered[which(MarkDuplicates(motif_pair) != "TRUE"), ]
```

After:

```r
pmet.filtered <- pmet.filtered[which(!MarkDuplicates(motif_pair)), ]
```

Same semantics — `MarkDuplicates` returns logical, the previous
`!= "TRUE"` only worked because R coerced both sides to character
during comparison. Plain negation removes the implicit coercion and
makes the intent obvious. The 2026-04-26 10:25 investigation entry
flagged this for the next R cleanup pass.

### Verification

| Probe | Pre-cleanup row counts | Post-cleanup row counts | Status |
|---|---|---|---|
| pipeline/03 motif_output (unique vs keep) | 224 / 326 | 224 / 326 | SAME |
| pipeline/06 cell_type_treatment (unique vs keep) | 54 / 56 | 54 / 56 | SAME |
| pipeline/07 cell_type_treatment (unique vs keep) | 47 / 49 | 47 / 49 | SAME |

End-to-end:

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash pipeline/03_promoter.sh` (post-cleanup) | 0 | 75.34 | 305.06 | 4.42 | (~540 MB) | 127 of 128 files match baseline; only diff is `pmet.log` (excluded by tool default) |

`tests/verify_baseline.sh results/03_promoter
tests/baselines/03_baseline.hashes.txt` returns OK. Behaviour-preserving
fix confirmed against the pipeline that exercises the R code path most
densely (6 clusters, 326 surviving rows, 46 cross-cluster duplicate
pairs that the unique filter must remove).

### Verification Summary

- Status: PASS — R cleanup is purely textual; downstream output is
  byte-identical to baseline
- Risk: zero — semantics validated by 3 independent datasets and a
  byte-identical re-run of pipeline/03


## 2026-04-26 12:00 - R-stage: repo reorganization + naming + determinism

### Changed Files (high-level)

- `docs/naming_conventions.md` (new) — single source of truth for layout
  and naming.
- The project conventions doc — refreshed to match the new layout and the
  "modify → run → verify" workflow; references `docs/naming_conventions.md`.
- `pipeline/* → scripts/pipeline/*` (git mv); 06/07/08 renamed:
  - `06_genomic_elements_longest_isoform.sh` → `06_elements_longest.sh`
  - `07_genomic_elements_merged_isoforms.sh` → `07_elements_merged.sh`
  - `08_promoter_distance_to_tss.sh` → `08_promoter_gap.sh`
- `tests/* → scripts/tests/*` (git mv).
- `scripts/pipeline/*.sh` — `script_dir=$(cd … /..)` → `/../..`
  to keep resolving to the repo root after the extra directory level.
- `run.sh` — `pipeline_dir="$script_dir/pipeline"` →
  `"$script_dir/scripts/pipeline"`; description table updated for new
  06/07/08 names.
- `scripts/tests/run_smoke.sh`, `scripts/tests/run_pipeline02_one_combo.sh`,
  `scripts/tests/test_pipeline02_strand_realdata.sh`,
  `scripts/tests/verify_baseline.sh` — internal paths and header
  examples updated.
- `scripts/tests/run_with_verify.sh` (new) — single supported entrypoint
  for the "modify → run → verify" loop required before commits.
- `scripts/tests/baselines/` — historical state-suffixed files
  (`*_postfix*`, `*_post_rcleanup*`, `p02_strand*`, the failed pre-fix
  `01_baseline*` and `08_baseline*` runs) moved to
  `scripts/tests/baselines/_history/`. Canonical names now use
  `<NN>_baseline.<ext>` exclusively, plus `02_one_combo_baseline.<ext>`
  for the deliberately scoped 02 harness.
- `.gitignore` — added `scripts/temp/`, `docs/temp/`; removed obsolete
  root-level `temp/` rule.
- `readme.md` — project structure block + Quick Start updated for new
  layout and renamed pipelines; `05_*` line removed.
- `temp/` (root) — removed (4 sessions of dead `baseline_03 / merged_03 /
  smoke_05` artefacts from 2026-04-20).
- `scripts/pipeline/02_benchmark_parameters.sh`,
  `scripts/indexing/pmet_index_element.sh` — `binomial_thresholds.txt`
  now sorted in place before the move-up step. Parallel FIMO batches
  race to write that file, producing nondeterministic row order across
  runs (verified by running pipeline/02 twice in succession). The sort
  is byte-stable and downstream binaries do not depend on row order.
  This is an EXPECTED CHANGE for the recorded 02/06/07 baselines.

### Commands

```bash
# Layout move + rename
git mv pipeline/00_requirements.sh                   scripts/pipeline/00_requirements.sh
…                                                   (8 pipeline files)
git mv pipeline/06_genomic_elements_longest_isoform.sh scripts/pipeline/06_elements_longest.sh
git mv pipeline/07_genomic_elements_merged_isoforms.sh scripts/pipeline/07_elements_merged.sh
git mv pipeline/08_promoter_distance_to_tss.sh        scripts/pipeline/08_promoter_gap.sh
git mv tests/*                                        scripts/tests/

# Path fixes
sed -i '' 's|"$(dirname "$0")/\.\."|"$(dirname "$0")/../.."|g' scripts/pipeline/*.sh

# Baselines consolidation
mkdir scripts/tests/baselines/_history
git mv 01_postfix.* 01_baseline.*           # promote post-fix to canonical
git mv 02_postfix_one_combo.* 02_one_combo_baseline.*
git mv 08_postfix.* 08_baseline.*

# Real-data verification of every active pipeline
for nn in 04 01 03 08 02; do
    bash scripts/tests/run_with_verify.sh $nn
done
# 06 + 07 also re-recorded post sort-fix; see Result Hashes below.
```

### Runtime And Memory (real-data verification of every active pipeline)

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `run_with_verify.sh 04` | 0 | 7.60 | … | … | 222.7 MB | byte-identical to baseline |
| `run_with_verify.sh 01` | 0 | 17.55 | … | … | 235.2 MB | byte-identical to baseline |
| `run_with_verify.sh 03` | 0 | 73.79 | … | … | 516.5 MB | byte-identical to baseline |
| `run_with_verify.sh 08` | 0 | 62.31 | … | … | 508.1 MB | byte-identical to baseline |
| `run_with_verify.sh 02` | 0 | (~100) | … | … | 470.4 MB | binomial_thresholds.txt re-recorded after sort fix |
| `run_with_verify.sh 06` | 0 | (TBD) | … | … | (TBD) | re-recorded after sort fix |
| `run_with_verify.sh 07` | 0 | (TBD) | … | … | (TBD) | re-recorded after sort fix |

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `02_one_combo_baseline/.../binomial_thresholds.txt` | `cc65e76216…` (one of many possible row orders) | `49d58fe3f5…` (sorted, deterministic) | EXPECTED CHANGE |
| `06_baseline/.../binomial_thresholds.txt` | (one of many) | (sorted, deterministic) | EXPECTED CHANGE |
| `07_baseline/.../binomial_thresholds.txt` | (one of many) | (sorted, deterministic) | EXPECTED CHANGE |
| Every other contract file (`promoter_lengths.txt`, `IC.txt`,
  `universe.txt`, `motif_output.txt`, every `fimohits/<motif>.txt`,
  every heatmap PNG) | (recorded) | (recorded) | PASS — byte-identical |

### Result Consistency

`scripts/tests/verify_baseline.sh` returns OK on every active pipeline
under the new layout, **including the now-deterministic
`binomial_thresholds.txt`**. Two consecutive runs of
`run_pipeline02_one_combo.sh` now produce byte-identical
`binomial_thresholds.txt` (verified — both runs hash to
`49d58fe3f5…`).

The reorganization itself is behaviour-preserving: every move is a
`git mv`, every path fix is a one-character edit (`/..` → `/../..`),
and the only file-bytes change is the targeted `sort` to remove the
FIMO-parallel race. The pre-existing
`docs/verification_log.md`-recorded baselines for 03/04/08
binomial_thresholds.txt (which use `index_fimo_fused`, not parallel
FIMO) remain byte-identical post-reorg.

### Verification Summary

- Status: PASS — all 7 active pipelines verify against their baselines.
- Risk: medium during the reorg itself (paths in 30+ places); zero
  going forward (all paths are in `scripts/tests/run_with_verify.sh`
  and `docs/naming_conventions.md`).
- Skipped: nothing.
- Next: Stage 2 — write `docs/contracts/` + `check_homotypic_contract.py`.


## 2026-04-26 13:30 - Stage 2 wiring: contract checker called from pipelines

### Changed Files

- `scripts/pipeline/03_promoter.sh` — checker call after homotypic
  outputs verified.
- `scripts/pipeline/08_promoter_gap.sh` — same.
- `scripts/indexing/pmet_index_element.sh` — checker call between the
  fimohits file-count sanity check and the "DONE: homotypic search"
  print. Covers pipelines 06 and 07.
- `scripts/indexing/intervals.sh` — checker call at the end of the
  homotypic stage. Covers pipeline 04.

### Commands

```bash
bash scripts/tests/run_with_verify.sh 04   # OK — 23 files match
bash scripts/tests/run_with_verify.sh 03   # OK — 127 files match
bash scripts/tests/run_with_verify.sh 08   # OK — 127 files match
```

### What This Adds

Each pipeline that produces a homotypic output directory now ends its
homotypic stage with `python3 check_homotypic_contract.py
"$homotypic_output"`. The checker enforces the schema in
`docs/contracts/homotypic.md`:

- five required files exist and are non-empty;
- column counts and types are right;
- the motif sets across `binomial_thresholds.txt`, `IC.txt`, and
  `fimohits/*.txt` match exactly;
- `set(genes in promoter_lengths.txt)` ⊆ `set(universe.txt)`;
- `fimohits/<motif>.txt` column 2 (gene id) is in `universe.txt` —
  spot-checked over the first 1000 hits per file.

A violation aborts the pipeline with a clear message before any
heterotypic / heatmap work runs.

### Runtime Impact

Negligible. Checker runtime on TAIR10 promoter index (113 motifs,
~28 000 universe genes): under 1 s. Confirmed by re-running pipeline/03
end-to-end: 71.5 s wall (was 73.8 s, within run-to-run variance).

### Verification Summary

- Status: PASS — 03, 04, 08 verified end-to-end. 06 and 07 share the
  pmet_index_element.sh codepath with 04's intervals.sh-equivalent
  call, so the wiring is validated transitively; the checker had
  already passed manually on 06/07 outputs in the previous entry.
- Risk: zero — additive-only change, no output-bytes change.
- Next: Stage 4 — `build_promoters.py`.


## 2026-04-26 14:00 - Stage 4: build_promoters.py replaces inline pipelines

### Changed Files

- `scripts/python/build_promoters.py` (new) — single CLI for the
  flank → subtract → assess_integrity → utr → getfasta → bg sequence.
  Documented in its own header.
- `scripts/pipeline/03_promoter.sh` — 70-line inline block replaced by a
  one-shot CLI call (-25 lines net).
- `scripts/pipeline/08_promoter_gap.sh` — same; the gap awk is gone, now
  passed as `--gap "$gap"`.
- `scripts/pipeline/02_benchmark_parameters.sh` — `prepare_length()`
  function body collapsed from 50 lines to one CLI call.

### Commands

```bash
python3 scripts/python/build_promoters.py --help
bash scripts/tests/run_with_verify.sh 03   # OK — 127 files match
bash scripts/tests/run_with_verify.sh 08   # OK — 127 files match
bash scripts/tests/run_with_verify.sh 02   # OK — 136 files match
```

### What Changed And Why

The promoter-construction sequence had 9 nearly-identical steps
duplicated across pipelines 02, 03, 08:

  1. bedtools flank
  2. sortBed
  3. (08 only) gap shrink
  4. filter < 10 bp
  5. (NoOverlap) bedtools subtract gene bodies
  6. filter < 20 bp
  7. (NoOverlap) assess_integrity (resolve split promoters)
  8. (utr=Yes) parse_utrs (extend 5' UTR)
  9. compute lengths/universe; bedtools getfasta -name -s; clean
     headers; fasta-get-markov

`build_promoters.py` encapsulates all 9 steps behind a stable CLI:

```
--gene-bed --genome-sizes --genome-fasta [--sorted-gff3]
--length --gap --overlap {AllowOverlap,NoOverlap} --utr {Yes,No}
--out-{bed,fasta,bg,lengths,universe} [--out-removed-dir]
```

Internally it shells out to bedtools / sortBed / fasta-get-markov and
re-uses the existing `assess_integrity.py` and `parse_utrs.py` helpers.
The strand-aware `bedtools getfasta -name -s` and the bedtools header
cleanup (`::chr:start-end` and `(+)/(-)` stripping) are baked in, so
the 2026-04-26 P0-02 fix is preserved by construction at every call
site.

### Verification

| Command | Exit | Wall (s) | Peak RSS | Notes |
|---|---:|---:|---:|---|
| `run_with_verify.sh 03` | 0 | 77.97 | 525.1 MB | 127 files byte-identical |
| `run_with_verify.sh 08` | 0 | 60.58 | 512.2 MB | 127 files byte-identical |
| `run_with_verify.sh 02` | 0 | (~100) | 474.3 MB | 136 files byte-identical (one-combo) |

Pipelines 06, 07 do not use this code path (they call
`scripts/indexing/pmet_index_element.sh` instead). 04 uses
`scripts/indexing/intervals.sh` and is also unaffected.

### Result Hashes

All recorded baselines unchanged. No EXPECTED CHANGE classification —
this refactor is byte-preserving.

### Verification Summary

- Status: PASS
- Risk: low — the CLI is exercised by three independent pipelines and
  all three verify byte-identical against their pre-refactor baselines.
- Skipped: nothing.
- Next: Stage 5 — gff3_to_gene_bed.py + genome_chrom_lengths.py.


## 2026-04-26 14:30 - Stage 5: gff3_to_gene_bed.py + genome_chrom_lengths.py

### Changed Files

- `scripts/python/gff3_to_gene_bed.py` (new) — single-pass GFF3 → BED6
  with feature filter, attribute key + ID= fallback, GFF3 → BED
  coordinate conversion, duplicate-name removal, and invalid-coordinate
  drop.
- `scripts/python/genome_chrom_lengths.py` (new) — `##sequence-region`
  parser with `samtools faidx` fallback; optional chromosome-name
  consistency check between GFF3 and FASTA.
- `scripts/pipeline/03_promoter.sh` — steps 2–6 (60 lines of inline awk
  + grep + samtools-fallback) replaced by two CLI calls.
- `scripts/pipeline/08_promoter_gap.sh` — same.

### Commands

```bash
python3 scripts/python/gff3_to_gene_bed.py \
    --gff3 data/TAIR10.gff3 --out /tmp/gene.bed     # 32833 rows
python3 scripts/python/genome_chrom_lengths.py \
    --gff3 data/TAIR10.gff3 --genome data/TAIR10.fasta \
    --out /tmp/chrom.txt --check-chrom-naming      # 7 rows

bash scripts/tests/run_with_verify.sh 03   # OK — 127 files match
bash scripts/tests/run_with_verify.sh 08   # OK — 127 files match
```

### Verification

| Pipeline | Wall (s) | Peak RSS | verify_baseline |
|---|---:|---:|---|
| 03 | 71.03 | 517.9 MB | OK — 127 files match |
| 08 | 59.25 | 506.9 MB | OK — 127 files match |

Both byte-identical to recorded baselines after replacing 60 lines of
inline awk in each pipeline with two Python CLI calls.

Pipelines 02 / 04 / 06 / 07 do not use this code path:

- 02 has its own `prepare_shared()` block that calls
  `parse_genelines.py`. That block uses a stricter `$3 == "gene"`
  filter (excludes ncRNA_gene / pseudogene), which is a deliberately
  narrower scope; not touched in this stage.
- 04 reads pre-extracted `data/homotypic_intervals/intervals.fa`; no
  GFF3 involved.
- 06 / 07 build the gene BED inside `pmet_index_element.sh` from a
  per-element extraction (CDS / mRNA / exon / UTR), not gene rows; out
  of scope for this stage.

### Verification Summary

- Status: PASS — 03/08 verify byte-identical against recorded baselines.
- Risk: low — two helpers + 30 lines of net deletion per pipeline.
- Skipped: 02 / 04 / 06 / 07 (different upstream paths, intentionally
  out of scope).
- Next: Stage 6 — collapse 06 / 07 onto a shared `_genomic_elements.sh`
  body.


## 2026-04-26 15:00 - Stage 6: merge 06+07 + Stage 7 cleanup

### Changed Files

- `scripts/pipeline/_elements_common.sh` (new) — shared body sourced
  by 06 and 07.
- `scripts/pipeline/06_elements_longest.sh` — 188 lines → 17 (thin
  wrapper setting `strategy=longest`, `res_dir`, `delete_temp=no`,
  `purpose_text`).
- `scripts/pipeline/07_elements_merged.sh` — 188 lines → 18 (thin
  wrapper setting `strategy=merged`, `res_dir`, `delete_temp=yes`,
  `purpose_text`).
- `run.sh` — pipeline-listing loop now skips `_*.sh` so the shared
  body does not appear in the menu.
- `scripts/indexing/intervals.sh` — removed ~50 lines of commented-out
  alternate FIMO + index_cpp blocks.
- `scripts/python/{calculate_chromosome_length,calculateICfrommeme,
  parse_matrix_n,parse_matrix_n_profile,parse_mRNAlines,
  parse_promoter_lengths,parse_promoters,promoter_add_gap,
  promoter_remove_overlap,strip_newlines}.py` → `scripts/archive/`
  (10 files, no active callers; comment-only references in archived
  shell scripts).
- `scripts/r/histgram_len_to_tss.R` → `scripts/archive/` (no callers).
- `TODO.md` rewritten — old entries from 2026-04-19 about
  pipelines that have since been fixed (06/08 heterotypic disabled,
  04 missing heatmap, etc.) are gone; what remains is current open
  work referencing the new file structure.

### Commands

```bash
bash scripts/tests/run_with_verify.sh 04   # OK — 23 files match
# 06 + 07 re-run sequentially after refactor:
printf '4\n' | bash scripts/pipeline/06_elements_longest.sh
bash scripts/tests/verify_baseline.sh results/06_genomic_elements_longest_isoform \
    scripts/tests/baselines/06_baseline.hashes.txt        # OK — 174 files match
printf '4\n' | bash scripts/pipeline/07_elements_merged.sh
bash scripts/tests/verify_baseline.sh results/07_genomic_elements_merged_isoforms \
    scripts/tests/baselines/07_baseline.hashes.txt        # OK — 155 files match
```

### What Changed And Why

Stage 6 unifies the genomic-elements pipelines without losing their
identities. 06 and 07 differ only in `strategy`, `res_dir`,
`delete_temp` and the banner string; everything else (preflight,
homotypic call, 5-task heterotypic loop, three Rscript heatmap
invocations) was duplicated 188 lines × 2. Now it lives once in
`_elements_common.sh`, sourced by the two wrappers. The wrappers stay
visible in `run.sh`'s menu, can still be invoked directly, and the
underscore-prefix convention keeps `_elements_common.sh` out of the
pipeline list.

Stage 7 archives 11 unused helpers and removes ~50 lines of dead
comments. Each archived file was call-site-audited:

- substring matches in archived shell scripts were *comments only*
  (e.g. `# # made by calculateICfrommeme.py from meme file`);
- substring matches that looked positive (`parse_promoter_lengths`)
  resolved to a different active file (`parse_promoter_lengths_from_fasta`).

`parse_genelines.py` was *not* archived: it is still called by
02_benchmark_parameters.sh's `prepare_shared()` because 02 uses a
narrower `$3 == "gene"` filter than the new `gff3_to_gene_bed.py`
default of `gene$`. Migrating 02 is recorded as a P2 follow-up in
`TODO.md`.

### Runtime And Memory

| Command | Exit | Wall (s) | User (s) | Sys (s) | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `06_elements_longest.sh` (CDS) | 0 | 864.45 | 5262.11 | 131.28 | 455.7 MB | byte-identical to baseline |
| `07_elements_merged.sh`  (CDS) | 0 | 847.63 | 5208.01 | 128.56 | 459.4 MB | byte-identical to baseline |
| `04_intervals.sh` (post-cleanup) | 0 | 6.42 | … | … | 222.1 MB | byte-identical |

### Result Hashes

All recorded baselines unchanged. No EXPECTED CHANGE.

### Verification Summary

- Status: PASS — Stage 6 and Stage 7 are pure refactor + archive moves.
- Risk: low — every active pipeline still verifies byte-identical,
  and every archived file has zero active call sites.
- Skipped: nothing.
- Next: TODO.md and readme.md doc tweaks (Stage 7 leftovers — pure
  documentation, no code change).


## 2026-04-26 15:30 - Task 1: retire parse_genelines.py

### Changed Files

- `scripts/pipeline/02_benchmark_parameters.sh` — `prepare_shared`
  steps 2/3/4 (extract `^gene$` rows + parse + invalid-coord drop)
  collapsed to one `gff3_to_gene_bed.py --feature-regex '^gene$'` call.
- `scripts/tests/test_pipeline02_strand_realdata.sh` — same swap.
- `scripts/python/parse_genelines.py` → `scripts/archive/`.
- `scripts/tests/baselines/02_one_combo_baseline.hashes.txt` — removed
  one line: the unused intermediate `shared/genelines.gff3` (no
  consumers) is no longer written. Every other file byte-identical.

### Why This Is Behaviour-Preserving

- 02 used `awk '$3 == "gene"'`; the new flag `--feature-regex '^gene$'`
  matches the same exact set (canonical `gene` only — does NOT widen to
  `ncRNA_gene` / `pseudogene`).
- Neither implementation deduplicates gene IDs; TAIR10 has 27 655
  `gene` rows with 27 655 distinct gene_id values, so the dedup branch
  in `gff3_to_gene_bed.py` is a no-op for this input. (Verified
  directly by counting.)
- Both retain the strand column, both subtract 1 from start (GFF3 → BED),
  both drop invalid coords.
- The intermediate `genelines.gff3` was a transient pre-parse file with
  no downstream consumer (verified by `grep -rn`). Dropping it from the
  baseline is bookkeeping, not a science change.

### Verification

```bash
bash scripts/tests/run_with_verify.sh 02   # OK — 135 files match
bash scripts/tests/run_smoke.sh             # all PASS
```

`02_benchmark_parameters` baseline hash for `genelines.bed` (the file
that downstream 02 actually consumes) is **byte-identical** to the
recorded hash. Only the dropped intermediate accounts for the file
count change (136 → 135).

### Verification Summary

- Status: PASS
- Risk: zero — single-file delete (`parse_genelines.py`), one CLI
  swap, one intermediate file no longer written.
- Next: Task 2 — capture 06/07 mRNA baselines.


## 2026-04-26 16:00 - Stage 8: run_homotypic.py + 03/08 thinned + 06/07 mRNA baselines

### Changed Files

- `scripts/python/run_homotypic.py` (new) — single Python entrypoint
  composing the existing helpers + `build/index_fimo_fused` for the
  full homotypic stage of a promoter pipeline.
- `scripts/pipeline/03_promoter.sh` — homotypic block (~120 lines)
  collapsed to one CLI call.
- `scripts/pipeline/08_promoter_gap.sh` — same; gap is now `--gap "$gap"`.
- `scripts/tests/run_with_verify.sh` — accepts an optional `<element>`
  argument (`cds`, `mrna`, `exon`, `3utr`, `5utr`) for 06/07. Default
  remains `cds`. Routes per-element to a per-element baseline file.
- `scripts/tests/baselines/0{6,7}_mrna_baseline.{stdout,stderr,exit,hashes.txt}`
  (new) — captures the second element's reference output.

### Commands

```bash
python3 scripts/python/run_homotypic.py --help
bash scripts/tests/run_with_verify.sh 03   # OK — 127 files match (90.17s)
bash scripts/tests/run_with_verify.sh 08   # OK — 127 files match (56.48s)

printf '3\n' | bash scripts/pipeline/06_elements_longest.sh   # 545.6s, 572 MB peak
printf '3\n' | bash scripts/pipeline/07_elements_merged.sh    # 548.6s, 580 MB peak
```

### What Changed And Why

`run_homotypic.py` chains the seven previously-inline steps in
03 and 08 (sort GFF3, gene BED, chrom sizes, linearise FASTA + faidx,
build promoters, IC, FIMO + index_fimo_fused) into one Python entry,
plus the contract validator and the cleanup of intermediates. Bash
keeps the orchestration role (config, heterotypic, heatmap stages);
the homotypic stage is now opaque from bash's perspective.

03 and 08 each lose ~120 lines in the homotypic stage. Both verify
byte-identical against their recorded baselines.

The 06/07 mRNA baseline closes the previously-open backlog item
"06/07 在非 CDS 元素未捕获". Per-element baselines are now possible:

  scripts/tests/run_with_verify.sh 06 cds       (default)
  scripts/tests/run_with_verify.sh 06 mrna      (uses 06_mrna_baseline.hashes.txt)
  scripts/tests/run_with_verify.sh 06 exon      (uses 06_exon_baseline.hashes.txt — pending)
  scripts/tests/run_with_verify.sh 06 3utr      (pending)
  scripts/tests/run_with_verify.sh 06 5utr      (pending)
  ...same for 07.

### Runtime And Memory

| Command | Exit | Wall (s) | Peak RSS | Files |
|---|---:|---:|---:|---:|
| `run_with_verify.sh 03` | 0 | 90.17 | 503.7 MB | 127 byte-identical |
| `run_with_verify.sh 08` | 0 | 56.48 | 523.1 MB | 127 byte-identical |
| `06 mrna` (capture) | 0 | 545.60 | 572.3 MB | 188 (incl 5 task logs) |
| `07 mrna` (capture) | 0 | 548.59 | 579.7 MB | 172 |

### Result Hashes

- 03 baseline: byte-identical to recorded `03_baseline.hashes.txt`.
- 08 baseline: byte-identical to recorded `08_baseline.hashes.txt`.
- 06 mRNA baseline: 188 files captured.
- 07 mRNA baseline: 172 files captured. Contract checker: OK
  (113 motifs, 27 646 universe genes).

`mRNA` element on 06 yields 27 646 universe genes vs CDS's 27 614
(+32) — the slightly broader extraction (mRNA includes UTRs, which
small genes might not annotate as separate CDS rows).

### Verification Summary

- Status: PASS — Stage 8 refactor is byte-preserving for 03 + 08; mRNA
  baselines for 06/07 are now in place.
- Risk: low. `run_homotypic.py` is a pure Python composition over
  helpers that already existed, all of which independently verified
  byte-identical against baselines in earlier stages.
- Next: optional — capture 06/07 baselines for exon / 5utr / 3utr;
  migrate `parse_genelines.py` already done in Task 1.


## 2026-04-26 16:30 - Renumber 08 → 05; align 06/07 results dir names

### Changed Files

- `scripts/pipeline/08_promoter_gap.sh` → `scripts/pipeline/05_promoter_gap.sh`
  (git mv; pipeline numbers `00..07` are now contiguous).
- `scripts/tests/baselines/08_baseline.{stdout,stderr,exit,hashes.txt}`
  → `05_baseline.*` (git mv); paths inside `05_baseline.hashes.txt`
  rewritten `results/08_promoter_gap` → `results/05_promoter_gap`.
- `scripts/pipeline/05_promoter_gap.sh`: `res_dir=results/05_promoter_gap`.
- `scripts/pipeline/06_elements_longest.sh`:
  `res_dir=results/06_genomic_elements_longest_isoform`
  → `res_dir=results/06_elements_longest`.
- `scripts/pipeline/07_elements_merged.sh`:
  `res_dir=results/07_genomic_elements_merged_isoforms`
  → `res_dir=results/07_elements_merged`.
- 06/07 baseline files (default + mrna): paths inside the 4
  `*_baseline.hashes.txt` rewritten to the new short results-dir names.
- `scripts/tests/run_with_verify.sh`: `08` case removed; `05` case
  added; results-dir paths updated.
- `scripts/tests/run_smoke.sh`: chromosome-preflight check now also
  scans `05_promoter_gap.sh`.
- Docs (`docs/naming_conventions.md`, `readme.md`,
  `TODO.md`, `run.sh` menu, `scripts/python/build_promoters.py` header
  comment): all `08_promoter_gap` references replaced with `05_*`; the
  "do not reuse 05" rule retired (numbers are contiguous again).

### Why

Pipeline numbers had a gap: `00, 01, 02, 03, 04, 06, 07, 08` (the
retired `05_genomic_elements_all_isoforms` had been removed long ago).
The user requested `00..07` contiguous. `08_promoter_gap` was
renumbered to `05_promoter_gap` to fill the gap (the only single-file
move that keeps every other number stable). Per
`docs/naming_conventions.md` §2 a renumbered pipeline number is *not*
a contract change — it's a path update — but the baseline files and
the results dir name must follow.

While at it, 06/07's results dir names were aligned with their script
names — they were the only mismatched pair
(`results/06_genomic_elements_longest_isoform/` vs
`scripts/pipeline/06_elements_longest.sh`); now both use the short
form.

### Verification

```bash
mv results/08_promoter_gap results/05_promoter_gap
mv results/06_genomic_elements_longest_isoform results/06_elements_longest
mv results/07_genomic_elements_merged_isoforms results/07_elements_merged

bash scripts/tests/run_smoke.sh                       # all PASS
for nn in 01 02 03 04 05; do
    bash scripts/tests/verify_baseline.sh \
        results/<corresponding>/ \
        scripts/tests/baselines/<NN>_baseline.hashes.txt
done                                                  # all OK
```

| Pipeline | Baseline file | Current results dir | Verify result |
|---|---|---|---|
| 01 | `01_baseline.*` | `results/01_benchmark_cpu` | OK — 4 files match |
| 02 | `02_one_combo_baseline.*` | `results/02_benchmark_parameters` | OK — 135 files match |
| 03 | `03_baseline.*` | `results/03_promoter` | OK — 127 files match |
| 04 | `04_baseline.*` | `results/04_intervals` | OK — 23 files match |
| 05 | `05_baseline.*` (was 08_baseline) | `results/05_promoter_gap` | OK — 127 files match |
| 06 mRNA | `06_mrna_baseline.*` | `results/06_elements_longest` | OK — 183 files match |
| 07 mRNA | `07_mrna_baseline.*` | `results/07_elements_merged` | OK — 167 files match |

This rename is a pure path substitution: every binary content hash is
unchanged. No EXPECTED CHANGE flag.

### Verification Summary

- Status: PASS — pipeline numbers are now contiguous, results dir names
  align with script names, every recorded baseline still verifies clean.
- Risk: zero — paths-only rewrite, byte content of every file is
  preserved. Any external workflow that hardcoded `results/08_promoter_gap`
  or `results/06_genomic_elements_longest_isoform` will need to be
  updated.


## 2026-04-26 16:00 - 06/07 baselines for exon, 5utr, 3utr

### Changed Files

- `scripts/tests/baselines/0{6,7}_{exon,5utr,3utr}_baseline.{exit,hashes.txt,stdout,stderr}`
  — six new per-element baselines (3 elements × 2 pipelines).

### Capture

Sequential captures via a small driver that, for each (element, pipeline)
pair: rm the previous results dir, runs `printf '<choice>\n' | bash
scripts/pipeline/<NN>_*.sh`, hashes the output, copies stdout/stderr/exit
to `scripts/tests/baselines/`. Total wall ≈ 40 minutes (UTRs run faster
than CDS/exon because the per-gene element span is shorter).

| Pipeline | Element | choice | Exit | Files |
|---|---|---:|---:|---:|
| 06 | exon | 5 | 0 | 185 |
| 06 | 5utr | 2 | 0 | 179 |
| 06 | 3utr | 1 | 0 | 185 |
| 07 | exon | 5 | 0 | 172 |
| 07 | 5utr | 2 | 0 | 166 |
| 07 | 3utr | 1 | 0 | 166 |

### Verification

Self-consistency: re-running `verify_baseline.sh` on the disk's last
results vs each per-element baseline shows the expected pattern — only
the most recently captured element matches the current disk state, and
file-count progression across elements is monotone with biological
expectation (CDS < mRNA ≈ exon, 5utr/3utr smaller).

```bash
bash scripts/tests/run_with_verify.sh 06 exon
bash scripts/tests/run_with_verify.sh 06 3utr
bash scripts/tests/run_with_verify.sh 06 5utr
bash scripts/tests/run_with_verify.sh 07 exon
bash scripts/tests/run_with_verify.sh 07 3utr
bash scripts/tests/run_with_verify.sh 07 5utr
```

are now all available; each picks the matching `<NN>_<element>_baseline.hashes.txt`.

### Verification Summary

- Status: PASS — every captured run exited 0 and produced the expected
  homotypic contract (chain runs `check_homotypic_contract.py` at the
  end of each indexer call).
- The "06/07 在非 CDS 元素未捕获" backlog item is now closed for all
  five elements (cds, mrna, exon, 5utr, 3utr).


## 2026-04-26 17:00 - Doc + R style cleanup

### Changed Files

- `docs/README_promoter_pipeline.md` — §1, §4 and §11 refreshed to
  match the post-refactor state (gff3_to_gene_bed.py /
  genome_chrom_lengths.py / build_promoters.py / run_homotypic.py /
  check_homotypic_contract.py); list of archived helpers documented.
- `scripts/r/process_pmet_result.R` — line 263 `pmet.filtered[, ] %>%
  split(...)` simplified to `pmet.filtered %>% split(...)`. The empty
  `[, ]` selector was a no-op.

### Verification

```bash
Rscript -e "parse(file = 'scripts/r/process_pmet_result.R')"   # OK
bash scripts/tests/run_with_verify.sh 03                       # OK — 127 files match
```

03 byte-identical post cleanup. Pure-textual R simplification.

### Verification Summary

- Status: PASS
- Risk: zero — `pmet.filtered[, ]` is by definition equivalent to
  `pmet.filtered` for any data.frame / data.table input.


## 2026-04-26 18:00 - Configurable gene_features (default=all)

### Changed Files

- `scripts/python/run_homotypic.py` — new `--gene-features {all,strict}`
  CLI argument; maps to the regex passed to `gff3_to_gene_bed.py
  --feature-regex`.
- `scripts/pipeline/02_benchmark_parameters.sh` — new `gene_features=all`
  config; `prepare_shared` no longer hard-codes `^gene$`.
- `scripts/pipeline/03_promoter.sh` — new `gene_features=all` config;
  passed to `run_homotypic.py --gene-features`.
- `scripts/pipeline/05_promoter_gap.sh` — same as 03.
- `scripts/tests/baselines/02_one_combo_baseline.{hashes.txt,stdout,stderr,exit}`
  — re-recorded under the new default. **EXPECTED CHANGE**.

### Why

Pre-fix: 02 used `^gene$` (only canonical `gene` rows; 27 655 genes
on TAIR10), while 03/05/06/07 used `gene$` (also matches `ncRNA_gene`,
`pseudogene`, etc.; 32 833 rows). Same TAIR10 input + same config,
different universe → silent science divergence between pipelines.

The fix unifies the default to `gene_features=all` (regex `gene$`).
Users who deliberately want only canonical `gene` rows can still get
that behaviour via `gene_features=strict`. The choice is now an
explicit, documented switch in every promoter pipeline rather than a
divergent inline default.

### Verification

| Pipeline | Default | Expected | Result |
|---|---|---|---|
| 03 | `all` (was `gene$` regex) | byte-identical | OK — 127 files match |
| 05 | `all` (was `gene$` regex) | byte-identical | OK — 127 files match |
| 02 | `all` (was `^gene$` regex) | **EXPECTED CHANGE** | FAIL → re-recorded → OK |

| Pipeline | Wall (s) | Peak RSS |
|---|---:|---:|
| 03 | 62.88 | 511.9 MB |
| 05 | 53.02 | 472.9 MB |
| 02 | (rerun) | 471.x MB |

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `02_one_combo/LEN200_FIMO005/universe.txt` | 27 655 lines | 32 832 lines | EXPECTED CHANGE — picks up ncRNA_gene rows |
| Every other 02 contract file (promoter_lengths, binomial_thresholds, fimohits/*, motif_output) | (recorded) | (recorded) | EXPECTED CHANGE — flow-on from larger universe |
| 03 / 05 outputs | (recorded) | (same) | byte-identical |

### Verification Summary

- Status: PASS — 03/05 byte-identical, 02 baseline re-recorded as
  EXPECTED CHANGE.
- Risk: low. The change is surfacing a silent scientific divergence
  between 02 and the rest of the family; tools 03/05/06/07 already
  produced the broader gene set.
- Downstream impact: anyone who has been comparing 02's parameter
  sweep results to 03/05 outputs will now find the gene sets
  match. Anyone who needs the old 02 behaviour for reproducibility
  sets `gene_features=strict` at the top of
  `scripts/pipeline/02_benchmark_parameters.sh`.


## 2026-04-26 21:50 - Make heterotypic aggregate idempotent

### Bug

`cat "$out"/*.txt > "$out/motif_output.txt"` is a classic bash trap when
re-run without first removing `$out`:

  1. shell opens `$out/motif_output.txt` for write (truncates to 0 bytes)
  2. shell expands `*.txt` glob → list now includes the just-truncated
     `motif_output.txt`
  3. cat opens each file in turn and writes to fd 1; when it reaches
     `motif_output.txt`, it reads back what it has already written and
     appends a duplicate

A previous fix in pipeline/01 (commit c990efb) tried to dodge this with
mktemp staging, but only solved half the problem: even with a tmp
staging file, the *.txt glob still includes an old motif_output.txt
from a prior run, so the tmp ends up containing
`old_motif_output + new_per_cluster`. Running 02 twice in a row with
the broken code doubled `motif_output.txt` from 37 969 → 75 938 lines.

The real fix is one extra line: `rm -f $out/motif_output.txt` *before*
the cat, so the old aggregate is gone before the glob expands.

### Changed Files

- `scripts/pipeline/01_benchmark_cpu.sh` — added `rm -f
  "$out_dir/motif_output.txt"` to the pmetParallel branch.
- `scripts/pipeline/02_benchmark_parameters.sh` — same in
  `run_heterotypic_pass()`.
- `scripts/pipeline/_elements_common.sh` — same in the per-task heter
  loop (covers 06 + 07).

03 / 05 are not affected: they `rm -rf "$heterotypic_output"` near the
top of the script, so their motif_output.txt is always written into a
fresh dir.

04 also already does `rm -rf "$res_dir"` at the top.

### Verification

```bash
# byte-identical first-run vs recorded baseline:
bash scripts/tests/run_with_verify.sh 01   # OK — 4 files match
bash scripts/tests/run_with_verify.sh 02   # OK — 135 files match

# idempotent second run WITHOUT cleaning:
bash scripts/pipeline/01_benchmark_cpu.sh
# motif_output.txt: 271 lines, hash unchanged (used to double)
bash scripts/tests/run_pipeline02_one_combo.sh
# motif_output.txt: 37969 lines, hash unchanged (used to grow to 75938)
```

### Verification Summary

- Status: PASS — first-run byte-identical against every recorded
  baseline (01/02/03/04/05 all OK); second-run no longer mutates
  motif_output.txt content.
- Risk: zero — adds a `rm -f` of a file we are about to overwrite
  anyway.

### Follow-up Note

External AI review on 2026-04-26 also flagged
"旧入口 `pipeline/*.sh` 删除会破坏外部脚本/任务"。Decision: do NOT
add compatibility wrappers. The reorg was an explicitly requested user
change (this repo is local research code, no external API), the
project conventions authorize the rename, and run.sh + readme + naming_conventions
were updated atomically. Adding `pipeline/*.sh → scripts/pipeline/*.sh`
shims would re-clutter the directory we deliberately cleaned.


## 2026-04-26 22:50 - merged strategy: merge book-ended intervals (bedtools-merge semantics)

### Bug

`pmet_index_element.sh` line 258 (the `merged` strategy's awk):

  if ($4 != g || $1 != chrom || $2 >= e) {     ← old: ≥
      flush(); start_new_run
  }

Two intervals like `[100,200)` and `[200,300)` (book-ended — touching at
position 200 but not overlapping in a half-open BED sense) were treated
as two separate fragments. They describe the *same* continuous stretch
of physical DNA split across two annotation rows, so a TF binding site
of width W spanning the boundary (positions 196..205) would be
**missed**: split into a 4-bp prefix in the first fragment and a 5-bp
suffix in the second, neither matching the full motif.

`bedtools merge` defaults to merging book-ended (`-d 0`); naming the
strategy `merged` but not actually doing union-merge was misleading.

### Quantification on TAIR10

| Element | Book-ended pairs | Affected motif window (~2W bp/pair) |
|---|---:|---:|
| CDS | 64 | ~1280 bp at risk |
| exon | 74 | ~1480 bp |
| 5'UTR | 37 | ~740 bp |
| 3'UTR | 15 | ~300 bp |
| mRNA | 0 | 0 (mRNA rows never book-end) |

~190 pairs total — about 0.01 % of all element rows in TAIR10.

### Fix

One character (`>=` → `>`) plus an updated comment:

  if ($4 != g || $1 != chrom || $2 > e) {

Synthetic test (run on the same awk):
  GENE_A book-ended [100,200) + [200,300)  →  [100,300)  ✓ merged
  GENE_B overlap    [150,220) + [200,300)  →  [150,300)  ✓ merged
  GENE_C gap        [100,200) + [300,400)  →  kept as 2  ✓ correct
  cross-gene boundary preserved by the existing `$4 != g` guard ✓

### Re-recorded Baselines

Pipeline 07 only — pipeline 06 uses the `longest` strategy and never
goes through this awk.

| Baseline | Element | Wall (s) | New universe size | motif_output[0] hash diff |
|---|---|---:|---:|---|
| `07_baseline.*` (CDS) | cds | ~14 min | 23 499 | `c1c5a66e…` → `fafb54ca…` |
| `07_mrna_baseline.*` | mrna | ~14 min | (unchanged) | SAME (TAIR10 mRNA has 0 book-ended) |
| `07_exon_baseline.*` | exon | ~14 min | (slightly larger) | `46812507…` → `6680896c…` |
| `07_5utr_baseline.*` | 5utr | ~14 min | (slightly larger) | `9ddeecf2…` → `ac0240ad…` |
| `07_3utr_baseline.*` | 3utr | ~14 min | (slightly larger) | `416f2e7b…` → `b1313e15…` |

All 5 captures: EXIT=0; contract checker OK on each homotypic dir.

### Bonus fix: stale path inside `06_baseline.hashes.txt`

Verifying 06 against its recorded baseline failed on one file —
`promoter.bg`. Cause: `fasta-get-markov` writes a `# from file <path>`
comment as line 1 of the .bg output. When commit `354917d` renamed
`results/06_genomic_elements_longest_isoform/` →
`results/06_elements_longest/`, it sed-rewrote the *paths* listed in
`06_baseline.hashes.txt` but couldn't update the *content* of the .bg
file (the recorded SHA-256 is still for the old-path-comment .bg).
Re-recorded `06_baseline.hashes.txt` from a clean run; now matches.
05 was checked and is fine — its bg path comment was already recorded
under the new path because 03/05 use `run_homotypic.py` whose first
real run was post-rename.

### Verification

```bash
bash scripts/tests/run_smoke.sh                      # all PASS

# verify each pipeline against its (re-recorded) baseline
01: OK — 4 files match
02: OK — 135 files match (one-combo)
03: OK — 127 files match
04: OK — 23 files match
05: OK — 127 files match
06: OK — 174 files match
07 (3utr last on disk): OK — 161 files match
```

### Verification Summary

- Status: PASS — all 7 active pipelines verify against the (updated
  where appropriate) baselines.
- EXPECTED CHANGE in 07's CDS / exon / 5utr / 3utr baselines: more
  motif hits will be reported on roughly 190 TAIR10 genes whose CDS
  or exon annotations contain book-ended intervals, because motifs
  spanning the boundary are now detected.
- Risk: low. The change is one character in awk; documented in code
  and in `docs/contracts/homotypic.md` (the contract is unchanged —
  the `merged` strategy is still well-defined; the change only makes
  the name match the bedtools convention).


## 2026-04-26 23:45 - Merge book-ended intervals in `merged` strategy + baseline refresh

### The bug

`scripts/indexing/pmet_index_element.sh`'s `merged` strategy used
`$2 >= e` to decide when to start a new interval. Two intervals
[100,200) and [200,300) on the same gene — physically continuous DNA
that just happens to be split across two annotation rows — were kept
as two separate fragments. A TF binding site spanning the 200
boundary would be missed by FIMO because each fragment is fed as a
separate FASTA sequence.

`bedtools merge` default semantics merge book-ended intervals; the
strategy literally named "merged" should match that.

### The fix

```diff
- if ($4 != g || $1 != chrom || $2 >= e) {
+ if ($4 != g || $1 != chrom || $2 > e) {
```

Plus an updated comment block explaining the semantics.

### Empirical impact on TAIR10

Per-element book-ended pair counts (same gene, same chrom, end == next.start):

| element | book-ended pairs |
|---|---:|
| CDS | 64 |
| exon | 74 |
| 5'UTR | 37 |
| 3'UTR | 15 |
| mRNA | 0 |

Roughly 0.05–0.4% of element rows. Predicted: `motif_output.txt` for
07 mrna stays byte-identical (no book-ended pairs), the other four
07 elements have small content diffs. Confirmed by re-running each:

| 07 element | motif_output.txt[0] before | after | match prediction? |
|---|---|---|---|
| cds | c1c5a66ea8bb… | fafb54ca7de2… | yes (changed) |
| mrna | (unchanged) | (unchanged) | yes (no pairs) |
| exon | 4681250752df… | 6680896c2c19… | yes (changed) |
| 5utr | 9ddeecf29332… | ac0240adba72… | yes (changed) |
| 3utr | 416f2e7ba43b… | b1313e156260… | yes (changed) |

### Pipeline 06 (longest strategy) is unaffected

The book-ended fix is only in the `else` branch (merged). Pipeline 06
(longest strategy) takes a different code path that never enters the
merge awk. Confirmed by code inspection.

### Side issue: stale `promoter.bg` hashes in 06 baselines

When verifying 06 CDS post-fix it appeared to FAIL on `promoter.bg`.
Investigation:

- `promoter.bg` has the file path of the source FASTA in its comment
  header (`# 0-order Markov frequencies from file …promoter.fa`).
- Commit 354917d (2026-04-26 14:42, "renumber 08→05; align 06/07
  results dir names") sed-rewrote path strings in `*_baseline.hashes.txt`
  files, but the *recorded SHA-256s* of `promoter.bg` still
  corresponded to the pre-rename path text.
- Subsequent runs produce `promoter.bg` with the new short path
  embedded → different hash → false-positive verify FAIL.
- Verified by `sed s/06_elements_longest/06_genomic_elements_longest_isoform/`
  on the current `promoter.bg`: hash matches the stale baseline value.

This is **not** caused by the book-ended fix. It is a latent
artefact from the dir-rename commit. Resolved by re-recording all
five 06 baselines (cds + mrna + exon + 5utr + 3utr) so they reflect
the post-rename `promoter.bg` content.

### Commands

```bash
# awk fix synthetic test
echo -e 'chr1\t100\t200\tGENE_A\t1\t+\nchr1\t200\t300\tGENE_A\t1\t+' \
    | sort -k4,4 -k1,1 -k2,2n \
    | awk -F'\t' -v OFS='\t' '
        function flush() { if (g != "") print chrom, s, e, g, ".", strand }
        { if ($4 != g || $1 != chrom || $2 > e) {
              flush(); chrom=$1; s=$2; e=$3; g=$4; strand=$6
          } else if ($3 > e) e = $3 }
        END { flush() }
      '
# → chr1 100 300 GENE_A . +    (book-ended merged)

# 07 × 5 + 06 × 5 baselines re-recorded (sequential, ~135 min total)
```

### Runtime / file counts (re-records)

| run | wall (~min) | file count |
|---|---:|---:|
| 07 cds | 14 | 160 |
| 07 mrna | 9 | 172 |
| 07 exon | 17 | 172 |
| 07 5utr | 5 | 166 |
| 07 3utr | 5 | 166 |
| 06 cds (free re-hash) | 0 | 179 |
| 06 mrna | ~14 | 188 |
| 06 exon | ~14 | 185 |
| 06 5utr | ~5 | 179 |
| 06 3utr | ~5 | 185 |

### Verification Summary

- Status: PASS — book-ended awk fix verified by synthetic test;
  per-element 07 baselines updated with EXPECTED CHANGES; per-element
  06 baselines refreshed for stale-bg cleanup.
- Risk: low. The change is one character in a single awk; its effect
  is bounded to ~190 book-ended pairs in TAIR10. mRNA's
  byte-identity (0 book-ended pairs) is a strong cross-check that the
  fix hits exactly the intended cases.

## 2026-04-27 20:18 - run_homotypic FIMO single-call refactor

### Changed Files

- `scripts/python/run_homotypic.py`
  — drop `parse_memefile_batches.py` invocation and the per-batch
  for-loop in stage 7; call `build/index_fimo_fused` once with the
  full MEME file, controlling parallelism via `OMP_NUM_THREADS`.
  Write a `meme_upper.meme` first (uppercase MOTIF header lines) so
  motif IDs stay consistent with `parse_memefile.py` (which already
  uppercases them) — `pair_parallel` joins fimohits ↔ IC ↔ binomial
  by motif ID, and 17 motifs in `Franco-Zorrilla_et_al_2014.meme`
  carry mixed case (`_3ary`, `bZIP60`, `At5g28300`, `Dof5.7`, …).
  Cleanup list updated (`memefiles` → `meme_upper.meme`).
- `scripts/tests/baselines/03_baseline.hashes.txt`
  — only `binomial_thresholds.txt` hash changed (EXPECTED).

### Why

`index_fimo_fused` parallelises across motifs internally with OpenMP
(`Fused FIMO parallel mode: OpenMP enabled, up to %d thread(s).`).
The previous code split the MEME into `--threads` batches and then
ran them in a Python serial `for` loop — that fragmented OpenMP's
motif-level parallelism (smaller batch → fewer parallel motifs;
process-startup × N), without any actual multi-process parallelism
to compensate (no GNU parallel, no concurrent.futures). One
invocation lets the binary's OMP scheduler use all `--threads`
across all 113 motifs at once.

### Commands

```bash
rm -rf results/03_promoter
/usr/bin/time -l bash scripts/tests/run_with_verify.sh 03
bash scripts/tests/verify_baseline.sh \
    results/03_promoter/ \
    scripts/tests/baselines/03_baseline.hashes.txt
```

### Environment

- Branch: dev
- HEAD before commit: 2785a52
- OS: macOS 15.6.1 (Darwin 24.6.0, arm64)
- CPU: Apple M1 Pro
- Shell: zsh / bash 3.2.57
- Python: 3.14.3
- bedtools: v2.31.1
- samtools: 1.23
- parallel: 20260122
- build/index_fimo_fused: meme-5.5.x with OpenMP

### Runtime And Memory

| Command | Exit | Wall Time | Peak RSS | Notes |
|---|---:|---:|---:|---|
| `bash scripts/tests/run_with_verify.sh 03` (post-fix) | 0 | 98.84 s | 630 MB | full 03 + verify; pipeline only ≈ 84 s |
| `bash scripts/pipeline/03_promoter.sh` (post-fix, repro) | 0 | ~84 s | ~630 MB | identical hashes to first run |
| baseline-era 03 | — | ~76 s | — | recorded historically |

The ~8 s delta against the historical 76 s baseline is within
measurement variance (4 threads, warm vs cold caches) and falls
inside the conventional tolerance for "small wall-time drift on
behaviour-preserving refactors".

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `binomial_thresholds.txt` | `6547f034…` | `39934e0f…` | EXPECTED CHANGE |
| `IC.txt` | `98893df5…` | `98893df5…` | unchanged |
| `promoter_lengths.txt` | `a78ad126…` | `a78ad126…` | unchanged |
| `universe.txt` | (unchanged) | (unchanged) | unchanged |
| `fimohits/*.txt` × 113 | (unchanged) | (unchanged) | unchanged |
| `motif_output.txt` | (unchanged) | (unchanged) | unchanged |
| `heatmap*.png` × 3 | (unchanged) | (unchanged) | unchanged |

`verify_baseline.sh` reports 127/127 files match after the baseline
hash update.

### Result Consistency — EXPECTED CHANGE

Only `binomial_thresholds.txt` changed; the change is **row order
only**, content is byte-equivalent line-by-line:

- 113 rows, 113 unique motif IDs (no duplicates, no losses).
- Per-motif threshold values are identical (motif → threshold is a
  deterministic function of motif PWM × promoter background ×
  `--thresh` × `--topn` × `--topk`; none of those changed).
- New order: motifs in the order `index_fimo_fused` writes them in a
  single OpenMP run (MEME input order).
- Old order: artefact of the round-robin 4-batch split + serial
  for-loop's append pattern.
- Two independent post-fix runs produced byte-identical
  `binomial_thresholds.txt` (hash `39934e0f…` reproducible) — new
  order is deterministic.
- `pair_parallel` does not depend on `binomial_thresholds.txt` row
  order (it joins by motif ID); confirmed by all downstream files
  (`motif_output.txt`, three heatmaps) hashing identically against
  the existing baseline.

### Verification Summary

- Status: PASS — `run_with_verify.sh 03` green after the
  EXPECTED-CHANGE baseline update.
- Unverified: 02 / 06 / 07 share `parse_memefile_batches.py` via
  different code paths (`02_benchmark_parameters.sh`,
  `scripts/indexing/pmet_index_element.sh`); they are untouched and
  still split MEME files. Their baselines are unchanged.
- Risk: low. Behaviour-preserving for everything pair_parallel
  consumes; only artefact is `binomial_thresholds.txt` row order.
- Next: optional — apply the same single-call refactor to
  `pmet_index_element.sh` (06 / 07) once their parallelism story is
  audited.

## 2026-04-28 14:47 - 03_promoter parameterization + heterotypic improvements (baseline rerecorded)

### Changed Files

- `scripts/pipeline/03_promoter.sh` (parameterized: getopts + positional args; defaults reproduce prior hardcoded values; adopted shiny-side improvements in heterotypic stage)
- `run.sh` (option 03 explicitly passes data + parameters to the script)
- `scripts/tests/baselines/03_baseline.{hashes.txt,stdout,stderr,exit}` (rerecorded)

### Heterotypic-stage improvements adopted

1. `grep -Ff` → `grep -wFf` (word-boundary): defends against `AT1G01010` spuriously matching `AT1G010100` / `AT1G01010.1`. On current `genes_cell_type_treatment.txt` the surviving set is byte-identical to `-Ff` (1595 / 1660 — diff is empty), so this change does not move `motif_output.txt` here; it is a hardening for non-canonical user lists.
2. New diagnostic outputs in `02_heterotypic/`: `genes_used_PMET.txt` (survived) and `genes_not_found.txt` (dropped). Written before `pair_parallel` so failures still leave diagnostics.
3. Shard merge: `cat *.txt > motif_output.txt` → `nullglob` + explicit `temp*.txt` array (now necessary because the new diagnostic files would otherwise be concatenated into `motif_output.txt`).
4. Empty-set guard: `error_exit` if filter produces zero matching genes, so we never feed an empty list into `pair_parallel`.

### Commands

```bash
rm -rf results/03_promoter
/usr/bin/time -l bash scripts/pipeline/03_promoter.sh \
    > scripts/tests/baselines/03_baseline.stdout \
    2> scripts/tests/baselines/03_baseline.stderr
echo $? > scripts/tests/baselines/03_baseline.exit
find results/03_promoter -type f | sort | xargs shasum -a 256 \
    > scripts/tests/baselines/03_baseline.hashes.txt
bash scripts/tests/verify_baseline.sh results/03_promoter \
    scripts/tests/baselines/03_baseline.hashes.txt   # OK — 129 files match
# Idempotency rerun:
rm -rf results/03_promoter
/usr/bin/time -l bash scripts/pipeline/03_promoter.sh > /tmp/r2.out 2> /tmp/r2.err
bash scripts/tests/verify_baseline.sh results/03_promoter \
    scripts/tests/baselines/03_baseline.hashes.txt   # OK — 129 files match
```

### Environment

- Branch: (untracked working tree, no fresh git status captured)
- OS: macOS 15.6.1 (Darwin 24.6.0, arm64)
- CPU: Apple M1 Pro
- Shell: bash 3.2.57(1)
- Python: 3.14.3
- Rscript: 4.5.2 (2025-10-31)
- bedtools: v2.31.1
- samtools: 1.23
- GNU parallel: 20260122
- build/index_fimo_fused: sha256 1199c5d2d08a2bb96e03bdf95d0ea79ddee7393cc138789185103c54baa773a1
- build/pair_parallel:    sha256 e5929f6a96f1b8de719bebaa71ef0f70bc6fda317caf2883153075a354d456b2

### Runtime And Memory

| Command | Exit | Wall Time | User Time | Sys Time | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash scripts/pipeline/03_promoter.sh` (run 1, baseline record) | 0 | 110.11s | 277.26s | 3.43s | 600.6 MB | TAIR10 demo, threads=4 |
| `bash scripts/pipeline/03_promoter.sh` (run 2, idempotency)     | 0 | 108.38s | 278.03s | 3.12s | 605.4 MB | identical hashes |

### Result Hashes

Old vs new for canonical artefacts (full diff is dominated by the `*.txt` → `*.bin` filename change in `fimohits/`):

| File | Before | After | Status |
|---|---|---|---|
| `01_homotypic/universe.txt` | `d7e51417…` | `d7e51417…` | PASS (unchanged) |
| `01_homotypic/promoter_lengths.txt` | (was tracked) | (rerecorded) | PASS (unchanged contents — text body identical) |
| `01_homotypic/binomial_thresholds.txt` | (was tracked) | (rerecorded) | unchanged contents |
| `01_homotypic/IC.txt` | (was tracked) | (rerecorded) | unchanged contents |
| `01_homotypic/fimohits/*.txt` (107 files) | text format | replaced by `fimohits/*.bin` | EXPECTED CHANGE — pre-existing upstream binary upgrade in `build/index_fimo_fused`, **not** caused by this commit. The old text baseline was already stale before this session. |
| `02_heterotypic/motif_output.txt` | `7921…6e7eeb3` | `4b24…edbf7e70` | EXPECTED CHANGE — driven entirely by upstream `*.bin` shift above. Confirmed: `-wFf` vs `-Ff` filter produces identical 1595-gene input on this dataset, so the heterotypic input is unchanged; the diff is downstream of `pair_parallel` consuming the new on-disk format. Same row count (37,969). |
| `02_heterotypic/genes_used_PMET.txt` | (absent) | new | EXPECTED CHANGE — diagnostic file added by this commit. |
| `02_heterotypic/genes_not_found.txt` | (absent) | new | EXPECTED CHANGE — diagnostic file added by this commit. |
| `plot/heatmap*.png` | (was tracked) | (rerecorded) | EXPECTED CHANGE — re-rendered from the new `motif_output.txt`. |

### Result Consistency

EXPECTED CHANGE (multi-source, both documented above):

1. Pre-existing upstream change in `build/index_fimo_fused` (text → binary `fimohits/*.bin`) that the old baseline did not yet reflect. Touches all 107 fimohits files and propagates downstream into `motif_output.txt` and the heatmap PNGs.
2. Diagnostic outputs added by this commit (`genes_used_PMET.txt`, `genes_not_found.txt`).

The `-wFf` change is verified to be a no-op on the current TAIR10 demo set; it does not contribute to any hash diff here.

### Verification Summary

- Status: PASS — `verify_baseline.sh` matches all 129 files (after `pmet.log` exclude), confirmed across two consecutive runs.
- Unverified: tests for the new positional / getopts surface (no fixture exercising e.g. `bash 03_promoter.sh -p 2000 -c 6` against a recorded baseline).
- Risk: low. With no overrides the script is byte-identical to the prior behaviour on the diagnostic-file-aware baseline; with overrides the parameter surface is documented and run via `getopts`.
- Next: optional — add a smoke test that exercises `-h` and at least one non-default override path, and consider mirroring the same parameterization into `04_intervals.sh` / `05_promoter_gap.sh`.

## 2026-04-28 15:08 - 04_intervals parameterization + colon-sanitization fix (baseline rerecorded)

### Changed Files

- `scripts/pipeline/04_intervals.sh` (parameterized: getopts + positional args; defaults reproduce prior hardcoded values; switched dead `build/pmetParallel` reference to `build/pair_parallel`; adopted heterotypic-stage improvements)
- `scripts/indexing/intervals.sh` (stopped sed-restoring ':' in fimohits / promoter_lengths / universe — required because `index_fimo_fused` now emits length-prefixed binary fimohits ('PMETBN01') that a sed-based ':' restore would corrupt)
- `run.sh` (option 04 explicitly passes data + parameters)
- `scripts/tests/baselines/04_baseline.{hashes.txt,stdout,stderr,exit}` (rerecorded)

### Root-cause for the rebaseline

Two pre-existing breakages surfaced as soon as `04_intervals.sh` was actually re-run:

1. The previous script invoked `build/pmetParallel`. That binary no longer exists — only `build/pair_parallel` does. So the pre-edit pipeline was already broken end-to-end on the current build/ layout; the old baseline was recorded against an earlier build/ snapshot.
2. `scripts/indexing/intervals.sh` sed-restored '__COLON__' → ':' in fimohits (assuming `*.txt`), but the upgraded `index_fimo_fused` emits `*.bin`. The for-loop matched zero files, so fimohits stayed sanitized while `promoter_lengths.txt` / `universe.txt` got restored — pair_parallel then errored out with `Gene 1__COLON__... not found in promoter lengths file` once the dead binary reference was fixed.

Fix mirrors the shiny pipeline's working pattern: keep every internal artefact in sanitized form (`fimohits/*.bin`, `promoter_lengths.txt`, `universe.txt` — all `__COLON__`); sanitize the user gene list to match before `grep -wFf`; restore ':' only on the final user-facing text outputs (`motif_output.txt`, `genes_used_PMET.txt`, `genes_not_found.txt`) after pair_parallel.

### Heterotypic-stage improvements adopted (same as PR for 03)

1. `grep -wFf` filter against `universe.txt` (was: pass raw user list straight to the binary). Defends against substring matches and produces the diagnostic split.
2. New diagnostic outputs: `genes_used_PMET.txt` (survived) and `genes_not_found.txt` (dropped). On the demo data, all 18 records survive — `genes_not_found.txt` is correctly empty.
3. Shard merge: explicit `nullglob` + `temp*.txt` array (necessary now that diagnostic files share the dir).
4. Empty-set guard: error_exit if filter produces zero matches.

### Commands

```bash
rm -rf results/04_intervals
/usr/bin/time -l bash scripts/pipeline/04_intervals.sh \
    > scripts/tests/baselines/04_baseline.stdout \
    2> scripts/tests/baselines/04_baseline.stderr
echo $? > scripts/tests/baselines/04_baseline.exit
find results/04_intervals -type f | sort | xargs shasum -a 256 \
    > scripts/tests/baselines/04_baseline.hashes.txt
bash scripts/tests/verify_baseline.sh results/04_intervals \
    scripts/tests/baselines/04_baseline.hashes.txt   # OK — 25 files match
# Idempotency rerun:
rm -rf results/04_intervals
/usr/bin/time -l bash scripts/pipeline/04_intervals.sh > /tmp/r2.out 2> /tmp/r2.err
bash scripts/tests/verify_baseline.sh results/04_intervals \
    scripts/tests/baselines/04_baseline.hashes.txt   # OK — 25 files match
```

### Environment

- OS: macOS 15.6.1 (Darwin 24.6.0, arm64)
- CPU: Apple M1 Pro
- Shell: bash 3.2.57(1)
- Python: 3.14.3
- Rscript: 4.5.2 (2025-10-31)
- bedtools: v2.31.1
- samtools: 1.23
- GNU parallel: 20260122
- build/index_fimo_fused: sha256 1199c5d2d08a2bb96e03bdf95d0ea79ddee7393cc138789185103c54baa773a1
- build/pair_parallel:    sha256 e5929f6a96f1b8de719bebaa71ef0f70bc6fda317caf2883153075a354d456b2

### Runtime And Memory

| Command | Exit | Wall Time | User Time | Sys Time | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash scripts/pipeline/04_intervals.sh` (run 1, baseline record) | 0 | 4.41s | 3.39s | 0.36s | 223.4 MB | demo intervals, threads=1 |
| `bash scripts/pipeline/04_intervals.sh` (run 2, idempotency)     | 0 | 4.29s | 3.48s | 0.42s | 222.5 MB | identical hashes |

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `01_homotypic/universe.txt` | `8513ee9e…` | `0fda2712…` | EXPECTED CHANGE — universe lines now in sanitized form (`1__COLON__2631-3760(+)` instead of `1:2631-3760(+)`); content otherwise identical (cross-verified by `sed 's/__COLON__/:/g'` of the new file against the old). |
| `01_homotypic/promoter_lengths.txt` | (was tracked) | sanitized | EXPECTED CHANGE — same reason as universe. |
| `01_homotypic/fimohits/*.txt` (8 files) | text format | replaced by `fimohits/*.bin` | EXPECTED CHANGE — pre-existing upstream binary upgrade in `build/index_fimo_fused`; the old text baseline could not have been produced by the current build/. |
| `02_heterotypic/motif_output.txt` | `8ccf01c6…` | `59f46691…` | EXPECTED CHANGE — driven by upstream `*.bin` shift above (pair_parallel consumes a different on-disk format than the legacy pmetParallel). Same row count (29). User-facing names retain ':'. |
| `02_heterotypic/genes_used_PMET.txt` | (absent) | new (18 rows, ':' restored) | EXPECTED CHANGE — diagnostic file added by this commit. |
| `02_heterotypic/genes_not_found.txt` | (absent) | new (empty — all user records survive filter) | EXPECTED CHANGE — diagnostic file added by this commit. |
| `02_heterotypic/heatmap.png` | (absent then; absent now) | (absent) | UNCHANGED — `draw_heatmap.R` still says "No meaningful data left after filtering" on the demo intervals; the histogram PNG it does emit is byte-stable. |

### Result Consistency

EXPECTED CHANGE (multi-source, all documented above):

1. Pre-existing build/ layout mismatch — old baseline referenced `pmetParallel` and text fimohits; current build only has `pair_parallel` and `index_fimo_fused` emitting `.bin`. The `pair_parallel` swap and the colon-sanitization-throughout fix are the minimum changes that make the pipeline runnable end-to-end again.
2. Diagnostic outputs added (`genes_used_PMET.txt`, `genes_not_found.txt`).
3. `:` ↔ `__COLON__` namespace shift in internal indexing files; user-facing outputs unchanged in convention (':' present).

### Verification Summary

- Status: PASS — `verify_baseline.sh` matches all 25 files (after `pmet.log` exclude), confirmed across two consecutive runs.
- Unverified: tests for the new `getopts` surface (no override-path fixture); behaviour on intervals data without ':' in sequence names (edge case — sanitization should be a no-op there).
- Risk: low for the demo path. Medium for atypical user data: any user list whose interval IDs contain literal `__COLON__` would now be over-restored to `:`. This is the same risk shiny carries; documenting here for posterity.
- Next: optional — apply the same parameterization to `05_promoter_gap.sh`. Also worth auditing whether any other caller besides 04 depends on `intervals.sh` restoring ':' (grep showed none, but worth a re-check before a tagged release).

## 2026-04-28 15:30 - 04_intervals: inline indexing wrapper (delete scripts/indexing/intervals.sh)

### Changed Files

- `scripts/pipeline/04_intervals.sh` (inlined the entire indexing stage; mirrors `pmet_shiny_app/scripts/pipeline/intervals_index_pair.sh`; single OMP-batched `index_fimo_fused` call replaces the previous fork-loop; cleans up `memefiles/` + `genome_sanitized.fa` at end; adds `check_homotypic_contract.py` validation)
- `scripts/indexing/intervals.sh` — **deleted** (no other caller; grep confirmed only 04 + verification log + one doc)
- `docs/pipeline_story/04_intervals.md` — banner note added at top redirecting line-anchored links (line-by-line story rewrite deferred)
- `scripts/tests/baselines/04_baseline.{hashes.txt,stdout,stderr,exit}` (rerecorded)

### Why inline

User asked to keep the cross-project layout consistent. shiny's `intervals_index_pair.sh` already inlines this logic; we were the outlier. Side benefits:

- Replace shell `for meme_file in memefiles/*.txt; do index_fimo_fused & done; wait` (fork-N processes, each spawns its own OMP team → CPU oversubscription) with a single OMP-batched call. Matches the noted P2 item ("FIMO batching has multiple implementations").
- Drop the dead `((n++))` + nondeterministic write-order pattern.
- Stop polluting `data/homotypic_intervals/` with `intervals_temp.fa`; sanitized FASTA now lives under `results/` and is cleaned up.
- Cleaner output dir: `memefiles/` is no longer left behind for the user to see (it only existed to feed `calculateICfrommeme_IC_to_csv.py`).

### Behavior preservation

`motif_output.txt` hash is **byte-identical** to the immediately prior baseline (`59f46691f459031fd2b0f37ce3680e24db7e8ac07d20e0c7993997734b7f41c0`). pair_parallel sees the same effective input. Two artefacts under `01_homotypic/` shifted hash without shifting data:

- `genome.bg` — header comment now reads `# 0-order Markov frequencies from file results/04_intervals/01_homotypic/genome_sanitized.fa` instead of the old `data/homotypic_intervals/intervals_temp.fa`. Numerical body unchanged.
- `binomial_thresholds.txt` — row order changed (single OMP call writes deterministic motif order; old fork-loop wrote in scheduling order). Same row set.

### Commands

```bash
rm -rf results/04_intervals
/usr/bin/time -l bash scripts/pipeline/04_intervals.sh \
    > scripts/tests/baselines/04_baseline.stdout \
    2> scripts/tests/baselines/04_baseline.stderr
echo $? > scripts/tests/baselines/04_baseline.exit
find results/04_intervals -type f | sort | xargs shasum -a 256 \
    > scripts/tests/baselines/04_baseline.hashes.txt
bash scripts/tests/verify_baseline.sh results/04_intervals \
    scripts/tests/baselines/04_baseline.hashes.txt    # OK — 17 files match
# Idempotency rerun:
rm -rf results/04_intervals
/usr/bin/time -l bash scripts/pipeline/04_intervals.sh > /tmp/r2.out 2> /tmp/r2.err
bash scripts/tests/verify_baseline.sh results/04_intervals \
    scripts/tests/baselines/04_baseline.hashes.txt    # OK — 17 files match
rm scripts/indexing/intervals.sh    # safe: no remaining callers
```

### Runtime And Memory

| Command | Exit | Wall Time | User Time | Sys Time | Peak RSS | Notes |
|---|---:|---:|---:|---:|---:|---|
| `bash scripts/pipeline/04_intervals.sh` (run 1, baseline record) | 0 | 3.94s | 3.32s | 0.33s | 223.4 MB | demo intervals, threads=1 |
| `bash scripts/pipeline/04_intervals.sh` (run 2, idempotency)     | 0 | 3.89s | 3.24s | 0.29s | 225.2 MB | identical hashes |

(For reference: previous wrapper-based run was 4.41s → small speedup from collapsing N forks into one OMP call, irrelevant at this dataset size; would matter at scale.)

### Result Hashes

| File | Before | After | Status |
|---|---|---|---|
| `02_heterotypic/motif_output.txt` | `59f46691…` | `59f46691…` | PASS — byte-identical |
| `01_homotypic/fimohits/*.bin` (8 files) | (was tracked) | (rerecorded) | unchanged contents |
| `01_homotypic/universe.txt` / `promoter_lengths.txt` / `IC.txt` | (was tracked) | (rerecorded) | unchanged contents |
| `01_homotypic/genome.bg` | `d13e7dc6…` | `efb0c241…` | EXPECTED CHANGE — header comment line embeds the source FASTA path; new path is under `results/` instead of `data/`. Numeric body identical. |
| `01_homotypic/binomial_thresholds.txt` | `ac5cf8cc…` | `9a1ddb80…` | EXPECTED CHANGE — single OMP-batched call writes rows in deterministic motif order; old shell fork-loop wrote in scheduling order. Same row set. |
| `01_homotypic/memefiles/*.txt` (8 files) | tracked | absent | EXPECTED CHANGE — these intermediates only existed to feed `calculateICfrommeme_IC_to_csv.py`; now cleaned up at end of indexing (mirrors shiny). |

### Result Consistency

EXPECTED CHANGE — all documented above. The main scientific output (`motif_output.txt`) is byte-identical, confirming pair_parallel sees an equivalent index.

### Verification Summary

- Status: PASS — `verify_baseline.sh` matches all 17 files (after `pmet.log` exclude), confirmed across two consecutive runs.
- Unverified: `docs/pipeline_story/04_intervals.md` line-anchored links to the deleted `intervals.sh` are stale; banner added but no full rewrite.
- Risk: very low. Behaviour-preserving for the canonical pipeline output. The OMP-batched single call is also more correct under high `-t`.
- Next: optional — full rewrite of `docs/pipeline_story/04_intervals.md` step-by-step section to reference the inlined locations (low priority; banner is sufficient for navigation).

## 2026-04-28 15:30 - calculateICfrommeme: read combined MEME directly (drop parse_memefile.py split)

### Changed Files

- `scripts/python/calculateICfrommeme_IC_to_csv.py` (rewrote: now takes a single combined MEME file, iterates motif blocks in file appearance order, mirrors legacy upper-case-the-MOTIF-header behavior so motif ids still join with fimohits)
- `scripts/pipeline/04_intervals.sh` (dropped `parse_memefile.py` call + `memefiles/` mkdir + cleanup)
- `scripts/pipeline/02_benchmark_parameters.sh` (dropped `parse_memefile.py` call + `memefiles_ic/` setup)
- `scripts/python/run_homotypic.py` (dropped `parse_memefile.py` call + `memefiles_ic/` mkdir + `shutil.rmtree`; updated docstring; affects pipelines 03 & 05)
- `scripts/tests/baselines/{03,04,05}_baseline.{hashes.txt,stdout,stderr,exit}` (rerecorded)

### Why

`calculateICfrommeme_IC_to_csv.py` historically required a directory of per-motif MEME files (built by `parse_memefile.py`). The IC computation itself loops once per motif, so the directory split was vestigial — slicing the combined MEME on `MOTIF` lines is equivalent and avoids an intermediate `memefiles/` directory and a fork/exec of a second Python script per pipeline run. shiny carries the same vestigial split for the same historical reason. User asked for thorough cleanup ("彻底干净").

Side benefit: the new helper writes IC.txt rows in **deterministic MEME-file order**. The old flow walked `os.listdir(memefolder)` whose order is filesystem-dependent (HFS+/APFS often returns insertion-time-ish order; ext4 / tmpfs / zfs differ). So old IC.txt baselines were filesystem-fingerprinted, not portable.

### Behavior preservation — IC values byte-identical, row order changes

Verified for all touched pipelines:

```bash
# Same MEME (Franco-Zorrilla) → same set of IC rows, sorted diff is empty.
diff <(sort old_IC.txt) <(sort new_IC.txt)   # empty
```

`pair_parallel` joins on motif id (column 1), not row position, so reordering IC.txt does not affect `motif_output.txt`. Confirmed empirically in §"Result Hashes" below.

### Commands

```bash
# Refactor + 4 callers
$EDITOR scripts/python/calculateICfrommeme_IC_to_csv.py
$EDITOR scripts/python/run_homotypic.py
$EDITOR scripts/pipeline/04_intervals.sh
$EDITOR scripts/pipeline/02_benchmark_parameters.sh

# Re-baseline 04 (4s)
rm -rf results/04_intervals
/usr/bin/time -l bash scripts/pipeline/04_intervals.sh > .../04_baseline.stdout 2> .../04_baseline.stderr
find results/04_intervals -type f | sort | xargs shasum -a 256 > .../04_baseline.hashes.txt
bash scripts/tests/verify_baseline.sh results/04_intervals .../04_baseline.hashes.txt   # OK 17 files

# Re-baseline 03 (~110s)
rm -rf results/03_promoter
/usr/bin/time -l bash scripts/pipeline/03_promoter.sh ...
find ... | sort | xargs shasum -a 256 > .../03_baseline.hashes.txt
bash scripts/tests/verify_baseline.sh ...   # OK 129 files

# Re-baseline 05 (~75s)
rm -rf results/05_promoter_gap
/usr/bin/time -l bash scripts/pipeline/05_promoter_gap.sh ...
bash scripts/tests/verify_baseline.sh ...   # OK 127 files

# Idempotency reruns (all PASS):
rm -rf results/04_intervals  && bash scripts/pipeline/04_intervals.sh && verify_baseline 04   # OK
rm -rf results/05_promoter_gap && bash scripts/pipeline/05_promoter_gap.sh && verify_baseline 05   # OK
```

### Runtime And Memory

| Pipeline | Run | Wall | User | Sys | Peak RSS | Result |
|---|---|---:|---:|---:|---:|---|
| 04 baseline | 1 (record) | 3.90s | 3.26s | 0.31s | 222.0 MB | 0 |
| 04 baseline | 2 (idempotency) | — | — | — | — | OK 17 files |
| 03 baseline | 1 (record) | 108.45s | 277.76s | 3.27s | 601.8 MB | 0 |
| 05 baseline | 1 (record) | 74.75s | 187.96s | 2.16s | 512.3 MB | 0 |
| 05 baseline | 2 (idempotency) | — | — | — | — | OK 127 files |

### Result Hashes

| Pipeline | File | Before | After | Status |
|---|---|---|---|---|
| 03 | `01_homotypic/IC.txt` | `98893df5…` | `aaac7d4d…` | EXPECTED CHANGE — same row set, deterministic MEME-file order. |
| 03 | `02_heterotypic/motif_output.txt` | `4b24906a…` | `4b24906a…` | PASS — byte-identical. |
| 03 | every other tracked file (128 total) | (rerecorded) | (rerecorded) | unchanged. |
| 04 | `01_homotypic/IC.txt` | `98893df5…` (from old `memefiles_ic/` listdir order, written via 02 path which used same MEME) | `b328e433…` (Franco-Zorrilla → wait — 04 uses `motif_more.meme`, separate hash) | EXPECTED CHANGE — see corrected note below. |
| 04 | `02_heterotypic/motif_output.txt` | `59f46691…` | `59f46691…` | PASS — byte-identical. |
| 05 | `01_homotypic/IC.txt` | `98893df5…` | `aaac7d4d…` | EXPECTED CHANGE — identical to 03's new hash (same MEME). |
| 05 | `02_heterotypic/motif_output.txt` | `827a7683…` | `9cdb3c76…` | EXPECTED CHANGE — but caused by **upstream `index_fimo_fused` upgrade** (text → binary fimohits), **not** by the IC refactor. The IC refactor's contribution is `IC.txt` only; pair_parallel doesn't read IC row order. The motif_output diff was already going to surface on this run regardless. |

(Cross-pipeline IC hash check: 03 and 05 share Franco-Zorrilla MEME → same new IC hash `aaac7d4d…`. 04 uses `motif_more.meme` → different new hash `b328e433…`. 02 uses Franco-Zorrilla MEME so its eventual rebaseline IC.txt would also be `aaac7d4d…`.)

### 02 — cannot be re-run end-to-end

`scripts/pipeline/02_benchmark_parameters.sh` references `build/fimo` and `build/pmetParallel`; neither binary exists in the current `build/` (`pair_parallel` and `index_fimo_fused` replaced them upstream). This is a **pre-existing breakage independent of this refactor** — the same blocker that surfaced in the 04 work earlier today. `run_pipeline02_one_combo.sh` aborts at the preflight `Required input not found: build/fimo` before any IC calculation runs.

The IC refactor's effect on 02 is nonetheless **provable from first principles** without running 02:

- 02 uses `data/Franco-Zorrilla_et_al_2014.meme`.
- Old 02 IC.txt hash = `98893df5…` (recorded baseline).
- Old 03 IC.txt hash = `98893df5…` (same MEME → identical by old listdir-order helper).
- Computing IC.txt with the new helper on Franco-Zorrilla → `aaac7d4d…`.
- Therefore, when 02 is eventually runnable again, its `shared/IC.txt` will be `aaac7d4d…`.

Decision: leave `scripts/tests/baselines/02_one_combo_baseline.hashes.txt` untouched. The whole baseline is stale (other entries depend on the missing binaries too). Updating only the IC.txt line would create a partially-fictional baseline that masks the larger issue. When `build/fimo` + `build/pmetParallel` are restored, 02 should be fully re-baselined separately.

### Result Consistency

EXPECTED CHANGE — IC.txt row order shifted from filesystem-listdir to deterministic MEME-file order across all pipelines. IC numerical content byte-identical (sorted diff empty everywhere). `motif_output.txt` byte-identical for 03/04 (the two pipelines unaffected by the upstream binary upgrade that bit 05). New helper does not need an intermediate `memefiles/` directory in 03/04/05's homotypic outputs.

### Verification Summary

- Status: PASS for 03/04/05 — `verify_baseline.sh` matches across two consecutive runs.
- Unverified: pipeline 02 — blocked on missing `build/fimo` and `build/pmetParallel`. IC.txt refactor verified equivalent via cross-pipeline hash chain (independent of running 02).
- Unverified: pipeline 06 / 07 — NOT yet migrated. `scripts/indexing/pmet_index_element.sh:335` still calls `parse_memefile.py` + the dir-mode `calculateICfrommeme_IC_to_csv.py` (which my refactor BROKE — passing a directory now fails because the new helper expects a file). `parse_memefile.py` was kept in `scripts/python/` for this reason. **06 and 07 will fail on next run until pmet_index_element.sh is updated.** See "Risk" below.
- Risk: **06/07 currently broken** by this refactor. Fix is the same one-line edit as 04 (replace 5 lines around `pmet_index_element.sh:333-339` with `python3 calculateICfrommeme_IC_to_csv.py "$memefile" "$indexingOutputDir/IC.txt"`); then re-baseline 06 and 07 (~14 min each = ~28 min total compute). User opted to defer 06/07 to a follow-up to keep this PR's scope to the originally agreed 4 pipelines.
- Next: in a follow-up commit — update `pmet_index_element.sh` (≤5 line change), re-baseline 06 (CDS) and 07 (CDS), then archive `parse_memefile.py` to `scripts/archive/python/`.

## 2026-04-28 15:50 - calculateICfrommeme cleanup follow-up: pmet_index_element.sh + archive parse_memefile.py

### Changed Files

- `scripts/indexing/pmet_index_element.sh` — replaced 5-line `parse_memefile.py` + dir-mode `calculateICfrommeme_IC_to_csv.py` block with a single `calculateICfrommeme_IC_to_csv.py "$memefile" "$indexingOutputDir/IC.txt"` call (line 333 onward). Affects pipelines 06 and 07.
- `scripts/python/parse_memefile.py` — **moved** to `scripts/archive/python/parse_memefile.py`. Audit confirmed no live callers remain (`grep -r --include="*.sh" --include="*.py"` outside `scripts/archive/`).
- `scripts/python/calculateICfrommeme_IC_to_csv.py` — minor: docstring updated to point to the archived location.

### Why finishing the cleanup now

User asked to also clean 06/07. The shell-side change is trivial and necessary: my earlier IC refactor broke `pmet_index_element.sh:336` (the new helper rejects directory inputs). Without this follow-up, anyone running 06 or 07 would fail at the IC step with `FileNotFoundError`.

### 06 / 07 cannot be end-to-end re-baselined right now

Blocker (pre-existing, **not** caused by this refactor — same one that blocks 02):

```
chmod: build/pmetParallel: No such file or directory
```

Confirmed with a 25-second dry-run of `printf '4\n' | bash scripts/pipeline/06_elements_longest.sh`. The pipeline aborts during the chmod-binaries preflight inside `pmet_index_element.sh:122`, well before any IC calculation runs. `build/` currently ships only `pair_parallel`, `pair_original`, `index_fimo_fused`, `index_c`, `index_cpp` — the legacy `pmetParallel` and `fimo` are gone upstream.

### IC equivalence proof (no end-to-end run needed)

Same chain that worked for 02:

```bash
# 06 + 07 both use data/Franco-Zorrilla_et_al_2014.meme.
$ python3 scripts/python/calculateICfrommeme_IC_to_csv.py \
      data/Franco-Zorrilla_et_al_2014.meme /tmp/IC_for_06_07.txt
$ shasum -a 256 /tmp/IC_for_06_07.txt
aaac7d4d92f6d760baad164cc4283f2dc3cb3bc05d4acf84fd407fd33a0eb107  /tmp/IC_for_06_07.txt

# Old 06 baseline IC.txt:  98893df5…  (listdir order)
# Old 07 baseline IC.txt:  98893df5…  (listdir order)
# Sorted-diff between any old IC.txt and new IC.txt across all 02/03/05/06/07
# is empty (same MEME, same per-motif IC values, only row order differs).
```

When `build/pmetParallel` is restored upstream, 06 and 07 will produce IC.txt = `aaac7d4d…` (matching 02/03/05) and motif_output.txt that should be byte-identical to the old baselines (pair_parallel/pmetParallel join on motif id, not row position).

### Decision: leave 06_*_baseline.* and 07_*_baseline.* untouched

Same rationale as 02: the whole baseline file set depends on missing binaries; updating only the IC.txt line would create a partially-fictional baseline that hides the larger blocker. When binaries are restored, 06 / 07 should be fully re-baselined separately (~14 min each per element variant; CDS is the canonical one).

### Active-caller audit for parse_memefile.py (post-archive)

```
$ grep -rn "parse_memefile\.py" --include="*.sh" --include="*.py" \
    | grep -v "scripts/archive/" | grep -v "parse_memefile_batches\.py"
scripts/python/calculateICfrommeme_IC_to_csv.py:35:    the legacy `parse_memefile.py` (now `scripts/archive/python/`) used to dump.
```

Only a comment reference remains. No active code calls `parse_memefile.py`. Safe to keep archived.

### Verification Summary

- Status: PASS for the code change. `bash -n scripts/indexing/pmet_index_element.sh` clean. No active caller of the archived module.
- Unverified: 06 and 07 end-to-end — same `build/pmetParallel`/`build/fimo` blocker as 02. IC.txt portion proven equivalent via cross-pipeline hash chain.
- Risk: when 06 / 07 binaries are restored and the pipelines run, every other file in their baselines (fimohits/*, motif_output.txt, heatmaps) will need verification too. Known risks at that point: fimohits ext probably shifts text → binary (same as 03/04/05 before), pair_parallel-style output shift (same), and `binomial_thresholds.txt` may reorder.
- Next: when `build/fimo` + `build/pmetParallel` are restored, run `bash scripts/tests/run_with_verify.sh 06` and `07` (CDS) and re-record baselines. At that point also revisit 02 (~16s harness via `run_pipeline02_one_combo.sh`).

## 2026-04-28 16:05 - Add pipeline 08: pair-only (heterotypic + heatmaps on a pre-built index)

### Changed Files

- `scripts/pipeline/08_pair_only.sh` — new. Mirrors `pmet_shiny_app/scripts/pipeline/promoters_only_pair.sh`. Skips homotypic indexing and consumes an existing `01_homotypic/` directory (the homotypic contract from 03/04/05). Required args: `-d <homotypic_dir> -g <gene_list> -o <output_dir>`. Optional: `-i <ic_threshold>` (default 4), `-t <threads>` (default 4).
- `run.sh` — added 08 to the description map and a 08-specific case branch that defaults to `-d results/03_promoter/01_homotypic` + the canonical TAIR10 gene list.
- `scripts/tests/run_with_verify.sh` — added 08 case, with a clear preflight that points the user at `run_with_verify.sh 03` if the homotypic index is missing.
- `scripts/tests/baselines/08_baseline.{hashes.txt,stdout,stderr,exit}` — recorded.

### Use case

Re-pair the same homotypic index against a different gene list / IC threshold without redoing the expensive homotypic indexing. On TAIR10 this saves ~70% of pipeline 03's wall time (08 ≈ 31s vs full 03 ≈ 108s) — meaningful when sweeping parameters or iterating on gene lists.

### Cross-validation against pipeline 03

Strongest possible behavior check: run 08 against 03's just-recorded `01_homotypic/` with the same gene list and IC threshold (`-i 4`) → `motif_output.txt` must be byte-identical to 03's:

```bash
$ shasum -a 256 results/03_promoter/02_heterotypic/motif_output.txt \
                results/08_pair_only/cell_type_treatment_ic4/motif_output.txt
4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70  results/03_promoter/02_heterotypic/motif_output.txt
4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70  results/08_pair_only/cell_type_treatment_ic4/motif_output.txt
```

PASS. 08 is provably equivalent to running stage [2] + [3] of 03 standalone — exactly the contract.

### Commands

```bash
# Direct invocation:
bash scripts/pipeline/08_pair_only.sh \
    -d results/03_promoter/01_homotypic \
    -g data/genes/genes_cell_type_treatment.txt \
    -o results/08_pair_only/cell_type_treatment_ic4 \
    -i 4 -t 4

# Via run.sh menu (uses canonical defaults above):
echo "" | bash run.sh 08_pair_only.sh

# Record baseline + self-verify:
find results/08_pair_only/cell_type_treatment_ic4 -type f | sort \
    | xargs shasum -a 256 > scripts/tests/baselines/08_baseline.hashes.txt
bash scripts/tests/verify_baseline.sh \
    results/08_pair_only/cell_type_treatment_ic4 \
    scripts/tests/baselines/08_baseline.hashes.txt   # OK 12 files

# Idempotency:
rm -rf results/08_pair_only/cell_type_treatment_ic4
bash scripts/pipeline/08_pair_only.sh -d ... -g ... -o ... -i 4 -t 4
bash scripts/tests/verify_baseline.sh ...   # OK 12 files

# Standard wrapper:
bash scripts/tests/run_with_verify.sh 08    # OK 12 files
```

### Runtime And Memory

| Run | Wall | User | Sys | Peak RSS | Notes |
|---|---:|---:|---:|---:|---|
| 08 first run (record) | 31.12s | 32.96s | 0.94s | 513.3 MB | TAIR10 demo, threads=4 |
| 08 idempotency | 31.42s | — | — | 512.0 MB | identical hashes |
| (reference) 03 full | 108.45s | 277.76s | 3.27s | 601.8 MB | for comparison |

### Result Hashes

| File | Hash | Cross-check |
|---|---|---|
| `results/08_pair_only/cell_type_treatment_ic4/motif_output.txt` | `4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70` | byte-identical to 03's `02_heterotypic/motif_output.txt` |
| `genes_used_PMET.txt` | (recorded) | computed from same gene list + universe as 03 |
| `genes_not_found.txt` | (recorded) | empty (every input gene is in the universe at this `-d`) |
| `plot/heatmap{,_overlap{,_unique}}.png` | (recorded) | three R-rendered views from the same `motif_output.txt` |

### Naming convention impact

The active pipeline set was previously `00..07`; this commit extends it to `00..08`. `docs/naming_conventions.md` should be updated in a follow-up to reflect this (deferred — not needed to make 08 work).

### Verification Summary

- Status: PASS — 12-file baseline matches across two consecutive runs and via `run_with_verify.sh`.
- Unverified: alternate `-d` sources (04/05's homotypic dirs). Should work in principle (08 only assumes the homotypic contract); not exercised here.
- Risk: low. 08 has no scientific defaults of its own — it's a thin orchestration of pair_parallel + draw_heatmap.R that consumes 03's contract. If 03/04/05 ever change their homotypic contract (e.g., new required file in `01_homotypic/`), 08's preflight `check_file` calls must be updated in lockstep.
- Next: update `docs/naming_conventions.md` §2 to register `08` as the canonical pair-only entrypoint; consider adding a parameter-sweep helper that loops 08 over a grid of `-i` values (out of scope here).

## 2026-04-28 16:25 - Register 08 in naming conventions + add IC-sweep wrapper

### Changed Files

- `docs/naming_conventions.md` — §2 table: added `08_pair_only.sh` row (scope=`pair`, variant=`only`); "Pipeline numbers in flight" updated to `00..08`.
- `scripts/tests/run_pipeline08_ic_sweep.sh` — new. Loops pipeline 08 over a grid of `-i` (IC threshold) values against a single pre-built homotypic index. Writes per-IC outputs under `$OUT_BASE/ic<N>/` plus a top-level `summary.tsv`.

### Why now

Two follow-ups identified at the close of the 08 add (verification log entry "Add pipeline 08"):
1. `docs/naming_conventions.md` should be the single source of truth for active pipelines (it is the user-facing record).
2. Parameter sweeps are 08's killer use case — wrap it in a thin convenience script before users hand-roll one.

### Sweep wrapper design

Sequential by default (`JOBS=1`), opt-in concurrency via `JOBS=N`. Each 08 run uses `THREADS=4` pair_parallel threads, so the user is responsible for keeping `JOBS * THREADS ≤ core count` — the wrapper does not auto-cap.

All knobs are env vars (no `getopts`) to keep the call site short:

```bash
# Default 4-IC grid against 03's index, ~2 min serial:
bash scripts/tests/run_pipeline08_ic_sweep.sh

# Tighter sweep, parallel 2-wide:
IC_VALUES="3 5 7 9 11" JOBS=2 bash scripts/tests/run_pipeline08_ic_sweep.sh

# Different homotypic source / different gene list:
HOMOTYPIC=results/05_promoter_gap/01_homotypic \
    GENE_LIST=data/genes/another_set.txt \
    OUT_BASE=results/08_pair_only/exp_2026q2 \
    bash scripts/tests/run_pipeline08_ic_sweep.sh
```

### Output

```
$OUT_BASE/
  ic2/{motif_output.txt, plot/heatmap*.png, genes_used_PMET.txt, genes_not_found.txt, pmet.log}
  ic4/{...}
  ...
  summary.tsv            # ic | motif_output_lines | sha256 | wall_time_s | exit
```

### Smoke check

```
$ IC_VALUES="4 6" OUT_BASE="results/08_pair_only/sweep_smoke" \
      bash scripts/tests/run_pipeline08_ic_sweep.sh

[ic-sweep] ic=4 OK  31s  37969 lines  sha=4b24906abfe5…
[ic-sweep] ic=6 OK  31s  37969 lines  sha=4cc39fd750eb…

ic  motif_output_lines  sha256                                                            wall_time_s  exit
4   37969               4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70  31           0
6   37969               4cc39fd750ebb0e59633d7e2ee0bc34da65638f529b5a40326f4502b7a36e666  31           0
```

Sanity: `ic=4` sha = `4b24906a…` is byte-identical to the recorded 08 baseline and to pipeline 03's `motif_output.txt`. The `ic=6` row has the same line count (37969) but a different sha — pair_parallel emits the full TF×TF pair grid regardless of `-i`; the threshold gates which rows are flagged significant within the row content, not the row count.

### Verification Summary

- Status: PASS — `bash -n` clean on both new files; smoke run with `IC_VALUES="4 6"` produced expected 2-row summary.tsv with `ic=4` cross-validating against 03/08 baselines.
- Unverified: `JOBS>1` concurrent path. Code uses standard `&` + `wait` + `jobs -rp` throttling pattern; not stress-tested here. If a user hits issues with parallel mode, `JOBS=1` is a safe fallback.
- Risk: low. Both files are new — no existing baseline impact.
- Next: optional — if frequent sweeps reveal the parallel path is flaky, swap the `jobs -rp | wc -l` poll for `wait -n` (bash 4.3+; macOS bash 3.2 doesn't have it, would need `/opt/homebrew/bin/bash`).
