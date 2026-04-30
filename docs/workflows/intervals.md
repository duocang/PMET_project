# intervals — full PMET on user-supplied genomic intervals

_Audit refreshed 2026-04-29 13:13:10 UTC on this machine — workflow `intervals`, exit 0, 15.2s_

**Source:** [`scripts/workflows/intervals.sh`](../../scripts/workflows/intervals.sh)
&nbsp;&nbsp;**Used by:** CLI research runs · web `intervals` mode

## Purpose

Run the complete PMET pipeline (homotypic indexing **+** heterotypic
pair test **+** heatmaps) starting from a user-supplied **interval
FASTA** rather than a genome + annotation. Intervals here means
**arbitrary sequence regions named by the user** — most commonly
ATAC-seq peaks, ChIP-seq peaks, conserved elements, or any other
non-promoter region the user wants to scan.

The motivation is: PMET's promoter pipeline only makes sense for genes
with well-defined TSSs and annotated 5' UTRs. For peak-based assays
the natural unit is the peak itself, not "the 1 kb upstream of a
gene". intervals.sh accepts those peak sequences directly.

## Biological setup

Each FASTA record is treated as one independent sequence (the analogue
of one promoter in `promoter.sh`). The "universe" is the set of all
interval names; the user's `peaks.txt` then defines a sub-cluster
within that universe.

A subtlety: FIMO's input parser and PMET's binary fimohits format
don't tolerate `:` characters in sequence names (FIMO mis-parses the
header, the binary records are length-prefixed so a sed restore would
shift bytes). Two sed passes handle this:

- On the input FASTA: `sed 's/^\(>.*\):/\1__COLON__/g'` rewrites the
  **last `:` on each header line** (the `\(.*\)` is greedy + the `^>`
  anchor restricts the match to header lines). Body sequence lines
  are untouched. For the typical `>chr:start-end(strand)` IDs there's
  only one `:` per header, so "last" coincides with "the only one";
  multi-colon names get only their final `:` rewritten — anything
  earlier is preserved.
- On the user's gene list: `sed 's/:/__COLON__/g'` rewrites **every
  `:`**, since there are no header markers to anchor against and the
  list is line-per-name.

After indexing + pairing, only the user-facing text outputs
(`motif_output.txt`, `genes_used_PMET.txt`, `genes_not_found.txt`)
are restored to `:` — **binary fimohits stay sanitised internally**.

## What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + binary preflight | locate `build/{index_fimo_fused, pair_parallel}` | Single failure point if either binary is missing |
| 2 | Interval sanitization | `sed 's/^\(>.*\):/\1__COLON__/g'` over input FASTA | See "biological setup" above — FIMO/binary safety |
| 3 | Dedupe + lengths | `scripts/python/deduplicate.py` then `parse_promoter_lengths_from_fasta.py` | Drops duplicate sequences, writes per-interval lengths to `promoter_lengths.txt`, derives `universe.txt` from it |
| 4 | Background model | `fasta-get-markov` over the sanitized FASTA | Zero-order Markov base composition; FIMO uses it as the null model so p-values are calibrated against the user's actual interval composition |
| 5 | IC.txt | `scripts/python/calculateICfrommeme_IC_to_csv.py` | Per-motif positional information content; pair_parallel uses this as a sanity floor |
| 6 | FIMO + indexing | one `index_fimo_fused` call (OpenMP-batched) | Replaces an older shell-level for-loop that forked one fimo per motif. Writes `binomial_thresholds.txt` + `fimohits/<MOTIF>.bin` (PMETBN01 binary) |
| 7 | Indexing contract validation | `scripts/python/check_homotypic_contract.py <indexing_dir>` | Asserts the schema in `docs/methods/homotypic-contract.md` holds — catches motif-id case mismatches and missing files early |
| 8 | Gene-list filter | `sed` colon sanitize → `grep -wFf universe.txt` | Match user's `peaks.txt` against the sanitized index universe |
| 9 | Heterotypic pair test | `build/pair_parallel -d <index> -g <kept> ...` → temp shards | The actual pair enrichment |
| 10 | Shard aggregation + colon restore | `cat temp*.txt > motif_output.txt`, then `sed 's/__COLON__/:/g'` over the user-facing text outputs | Final motif_output.txt has the user's original `chr:start-end(strand)` interval names back |
| 11 | Heatmaps (optional) | three `Rscript scripts/r/draw_heatmap.R` calls | Skipped silently if `Rscript` is absent |

## Run snapshot

This audit just ran:

```
bash scripts/workflows/intervals.sh -s data/demos/intervals/indexing/intervals.fa -m data/demos/intervals/indexing/motif.meme -g data/demos/intervals/indexing/peaks.txt -o /Users/nuioi/projects/pmet/tests/audit/runs/intervals/01_indexing -x /Users/nuioi/projects/pmet/tests/audit/runs/intervals/02_pairing -t 4
```

Indexing landed at `tests/audit/runs/intervals/01_indexing/`, pairing at `tests/audit/runs/intervals/02_pairing/`.

### Indexing-stage outputs

| File | Rows / count | Meaning |
|---|---|---|
| `fimohits/*.bin` | 10 files | one PMETBN01 file per motif (10 in `motif.meme`) |
| `binomial_thresholds.txt` | 10 rows | per-motif p-value threshold for `--topn 5000` |
| `IC.txt` | 10 rows | per-motif positional information content |
| `universe.txt` | 26552 rows | every distinct interval name |
| `promoter_lengths.txt` | 26552 rows | should equal `universe.txt` rows |

### Pairing-stage output preview

`motif_output.txt` first 3 rows (cluster ⟶ motif1 ⟶ motif2 ⟶ ...):

```
Cluster	Motif 1	Motif 2	Number of genes in cluster with both motifs	Total number of genes with both motifs	Number of genes in cluster	Raw p-value	Adjusted p-value (BH)	Adjusted p-value (Bonf)	Adjusted p-value (Global Bonf)	Genes
U	CCA1	MYB111	0	745	18	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00
U	CCA1	MYB111_2	0	710	18	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00
```

Total enriched pair rows: **46**.

## Verification

⚠️ **PASS WITH WARNINGS** — 1 warning(s), 12 pass(es)

| # | Check | Expected | Observed | Verdict |
|---|---|---|---|---|
| 1 | script exit code | `0` | `0` | ✅ PASS |
| 2 | fimohits/*.bin per motif | `10` | `10` | ✅ PASS |
| 3 | binomial_thresholds rows == motifs | `10` | `10` | ✅ PASS |
| 4 | IC.txt rows == motifs | `10` | `10` | ✅ PASS |
| 5 | universe.txt non-empty (interval names) | `>= 1` | `26552` | ✅ PASS |
| 6 | promoter_lengths.txt rows == universe size | `26552` | `26552` | ✅ PASS — every interval needs a length row |
| 7 | motif_output.txt non-empty (heterotypic pairs) | `>= 1` | `46` | ✅ PASS |
| 8 | motif_output.txt deterministic vs anchor | `4858412a09198363305a419af01d47a35ff7cfd63a2169dd01aa545f8ff800c6` | `4858412a09198363305a419af01d47a35ff7cfd63a2169dd01aa545f8ff800c6` | ✅ PASS — captured against demo_intervals on this host; differs if fixture or pair_parallel sort changes |
| 9 | indexing contract: binomial == IC motifs | `set equal` | `|both|=10` | ✅ PASS |
| 10 | indexing contract: binomial == fimohits motifs | `set equal` | `|both|=10` | ✅ PASS |
| 11 | indexing contract: IC == fimohits motifs | `set equal` | `|both|=10` | ✅ PASS |
| 12 | Rscript invoked (3 histogram subdirs present) | `3` | `3` | ✅ PASS |
| 13 | 3 headline heatmap PNGs rendered | `3` | `0` | ⚠️ WARN — R ran but draw_heatmap.R's p-adj filter left nothing to plot (expected on small demo data) |

### Reproducing this audit

```bash
python3 tests/audit/generate.py intervals
```

The motif_output.txt sha is anchored to `data/demos/intervals` on this
machine. Both the demo data and pair_parallel's output are
deterministic — any sha drift is a real regression signal.
