# Walkthroughs verification — 2026-05

Companion to the path refresh + scientific re-derivation of `docs/workflows/walkthroughs/`. Records what was actually executed and what was only static-checked, so future maintainers know which doc claims have evidence behind them and which were taken on faith.

Pattern adapted from [`docs/archive/verification_log.md`](../../archive/verification_log.md): every doc claim either gets a "verified by re-running command X, output saved to Y" entry, or is explicitly marked as deferred with a reason.

## Environment

- Date: 2026-05-03
- Branch: `main` at `28e6d37` (post the three-commit refresh: kill_process_tree share + fimo monitor + configure relocation)
- OS: macOS 15.6.1, Apple M1 Pro
- Binaries built host-side: `build/indexing_fimo_fused`, `build/pairing_parallel`
- Reference data: `data/reference/TAIR10.{fasta,gff3}`, `data/motifs/Franco-Zorrilla_et_al_2014.meme`, `data/genes/genes_cell_type_treatment.txt`

## Coverage map

| Walkthrough | Path-existence sweep | Pipeline run this round | Output dir | Numeric / scientific claims | Notes |
|---|---|---|---|---|---|
| `promoter.md` | ✓ all paths exist | ✓ this round (109 s wall, 277 s CPU) | `results/tests/walkthroughs_2026-05/promoter/` | **all 5 numeric claims match** my own re-run | 113 motifs / 29824 universe / 29824 promoter_lengths / 37969 motif_output rows / 11 cols all reproduce |
| `intervals.md` | ✓ all paths exist | ✓ this round (15 s wall) | `results/tests/walkthroughs_2026-05/intervals/` | **doc rewritten in this round** to track current data + corrected finding | demo grew ~10× (2717 → 26558 records) since original audit; prior "binomial null is weak" WARNING is invalidated and was rewritten |
| `promoter-gap.md` | ✓ all paths exist | ✗ deferred | n/a | numeric claims unverified | needs custom-gap config + TAIR10 run |
| `elements-longest.md` | ✓ all paths exist | ✗ deferred | n/a | numeric claims unverified | needs full elements.sh -s longest run; doc also needs the `.txt → .bin` fimohits update + `build/fimo` removal that intervals/promoter walkthroughs got |
| `elements-merged.md` | ✓ all paths exist | ✗ deferred | n/a | numeric claims unverified | same as elements-longest |
| (heterotypic stage shared by `promoter.md` step 8–10) | n/a | ✓ pair_only.sh on demo | `results/tests/walkthroughs_2026-05/pair_only/` | 11-column motif_output schema confirmed | demo's tiny fimohits/ (6 files) → 46 pair rows |

## Verified by re-run

### `scripts/workflows/promoter.sh` (default args, full TAIR10)

```bash
/usr/bin/time -l bash scripts/workflows/promoter.sh \
    -o results/tests/walkthroughs_2026-05/promoter/01_homotypic \
    -x results/tests/walkthroughs_2026-05/promoter/02_heterotypic \
    -y results/tests/walkthroughs_2026-05/promoter/03_plot
```

Wall: 109.15 s, user: 277.44 s, sys: 3.79 s. Exit 0.

**Numeric claims from `promoter.md` — all match this re-run:**

| `promoter.md` claim | This re-run actual | Pass? |
|---|---|---|
| 113 motifs (Franco-Zorrilla) | 113 fimohits files | ✓ |
| 29824 universe genes | 29824 rows | ✓ |
| 29824 promoter_lengths | 29824 rows | ✓ |
| 113 binomial threshold rows | 113 | ✓ |
| `motif_output.txt` 37969 rows | 37969 | ✓ |
| `motif_output.txt` 11 columns | 11 | ✓ |
| 3 named heatmap PNGs (`heatmap.png`, `heatmap_overlap.png`, `heatmap_overlap_unique.png`) | all 3 present | ✓ |

(Independently the prior audit baseline at `results/tests/audit/runs/promoter/` carries the same numbers — both runs are reproducible against TAIR10 + Franco-Zorrilla 113-motif library.)

### `scripts/workflows/intervals.sh` (default args, intervals demo)

```bash
bash scripts/workflows/intervals.sh \
    -o results/tests/walkthroughs_2026-05/intervals/01_indexing \
    -x results/tests/walkthroughs_2026-05/intervals/02_pairing
```

Wall: 15 s. Exit 0.

**This re-run drove the rewrite of `intervals.md`. Findings:**

| Original audit (pre-monorepo) | Current re-run | Action taken in `intervals.md` |
|---|---|---|
| `intervals.fa` 2717 records | **26558 records** (10× larger) | numbers updated |
| 1 duplicate header | **6 duplicates** | numbers updated |
| `universe.txt` 2716 lines | **26552 lines** | numbers updated |
| `motif_more.meme` 8 motifs | **11 motifs** | numbers updated; IC.txt / fimohits / binomial counts all rebased |
| `peaks.txt` 17 rows + 1 dup → 18 unique | **18 rows, all unique** (no dedup needed) | prose rewritten with historical sidebar |
| binomial thresholds ≈ 0.99 | **mean 9.7e-03 (range 1.5e-03 – 2.2e-02)** | **WARNING rewritten** — corrected reasoning below |
| effective search space ≈ 2.7 Mb | **25 Mb** (26552 × 942 bp mean) | reasoning rewritten |
| `motif_output.txt` 29 rows = 1 + C(8,2) | **56 rows = 1 + C(11,2) = 1 + 55** | row-count reasoning rebased |
| fimohits per-motif `.txt` (TSV) | **per-motif `.bin` (PMETBN01)** | format change documented + provenance commit cited |
| step 5 sed-restored everything to `:` | **only `02_pairing/` text outputs restored**; `01_indexing/` keeps `__COLON__`; binary fimohits keep it internally | step 5 rewritten with explicit table of what's restored vs preserved |
| heatmap side-car `histgram_padj_before_filter.png` (typo) | **no histogram side-car**; empty `plot/` dir | step 8 rewritten |

**Why the original "WARNING — binomial null is weak" finding was wrong on current data:** the warning's premise was a *small* universe (2.7 Mb), which makes the binomial null distribution diffuse — almost any FIMO hit's `--topn` cut-off translates to a near-1.0 binomial p-threshold. Current demo is 25 Mb, comparable to promoter pipeline's ~30 Mb. With this much sequence space the null distribution narrows, the per-motif binomial threshold lands in 1e-03 – 2e-02 (even *tighter* than the promoter pipeline's mean 4.3e-02 on its full 113-motif library), and the warning's recommendation ("treat the IC threshold as the real filter") is no longer needed — the binomial threshold is doing meaningful work too.

**Investigation trail (provenance of the change):**

```
$ git log --follow --oneline data/demos/intervals/indexing/intervals.fa
d7113e9 refactor(data): consolidate demo and index layouts
941f2ef refactor(data): namespace data/ by consumer
8115a67 refactor: drop migrated subdirs and finalize file placements
ef5cea8 chore: import three subdirs as monorepo baseline
```

The pre-monorepo era had **two** intervals datasets in `pmet_shiny_app/data/`: `homotypic_intervals/intervals.fa` (5434 lines = 2717 records, the small one the original walkthrough audited) and `demo_intervals/intervals.fa` (53116 lines = 26558 records, ~10× larger). Commit `941f2ef` (Apr 30) retired `homotypic_intervals/` and renamed `demo_intervals/` → `data/demos/intervals/`. The doc was static-snapshot of the small one; the consolidation kept the big one. Path drift was only the visible symptom; data identity drift was the actual cause.

The fimohits format switch (`.txt` → `.bin`, PMETBN01) happened in commit `0c43958` (also Apr 30), per `core/indexing/src/pmet_index/pmet-fimo-binary.h`. Before that switch, every fimohits file was a TSV that the bash workflow could `sed` post-hoc to restore `:` in sequence ids. The binary format made the post-hoc sed impossible, so the round-trip narrowed to the heterotypic stage's text outputs only — captured in `intervals.sh:309-315`.

### `scripts/workflows/pair_only.sh` (heterotypic-only smoke)

```bash
bash scripts/workflows/pair_only.sh \
    -d data/demos/promoters/pairing/demo \
    -g data/demos/promoters/pairing/demo/gene.txt \
    -o results/tests/walkthroughs_2026-05/pair_only
```

Wall: ~15 s. Exit 0. Output `motif_output.txt`: 46 rows × 11 cols. Header matches the schema from `promoter.md` § 5 verbatim:

```
Cluster  Motif 1  Motif 2  Number of genes in cluster with both motifs  Total number of genes with both motifs  Number of genes in cluster  Raw p-value  Adjusted p-value (BH)  Adjusted p-value (Bonf)  Adjusted p-value (Global Bonf)  Genes
```

## Deferred

`promoter-gap.md`, `elements-longest.md`, `elements-merged.md` — paths exist, but the underlying pipelines were not run this round. Likely-deeper drift than just numbers:

- `elements-longest.md` claims pipeline 06/07 use `build/fimo` (standalone FIMO + GNU parallel batches) vs 03/05's `build/indexing_fimo_fused` — that distinction was already retired (current `_pmet_index_element.sh` uses `indexing_fimo_fused` exclusively, like the others). The doc has a top-of-file note flagging this; the body code blocks still show the old `build/fimo` invocation.
- All three may need the same `.txt` → `.bin` fimohits update that `intervals.md` got.
- All three need a real ~5–10 min run on TAIR10 to verify their numeric claims.

Queued for a future verification round.

## Take-away

Path refresh alone was insufficient. The first round of the walkthroughs refresh checked path *existence* but not behaviour. Re-running revealed:

1. `intervals.md` had ~20 stale numbers AND a scientifically-backwards WARNING — both fixed in this round.
2. `promoter.md` happens to be byte-for-row-count current — its numeric anchors survived the monorepo merge unchanged because TAIR10 + Franco-Zorrilla didn't change.
3. The fimohits binary-format switch (`0c43958`) is a doc-relevant architecture change none of the walkthroughs reflected — `intervals.md` is now updated, the other three still need it.

For the deferred walkthroughs, the path-existence baseline is in place; the next round needs to actually run them.
