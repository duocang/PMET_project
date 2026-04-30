# intervals — full PMET on user-supplied genomic intervals

<<RUN_HEADER>>

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
<<COMMAND_DISPLAYED>>
```

Indexing landed at `<<INDEXING_DIR>>/`, pairing at `<<PAIRING_DIR>>/`.

### Indexing-stage outputs

| File | Rows / count | Meaning |
|---|---|---|
| `fimohits/*.bin` | <<FIMOHITS_COUNT>> files | one PMETBN01 file per motif (10 in `motif.meme`) |
| `binomial_thresholds.txt` | <<BINOMIAL_LINES>> rows | per-motif p-value threshold for `--topn 5000` |
| `IC.txt` | <<IC_LINES>> rows | per-motif positional information content |
| `universe.txt` | <<UNIVERSE_LINES>> rows | every distinct interval name |
| `promoter_lengths.txt` | <<PROMOTER_LENGTHS_LINES>> rows | should equal `universe.txt` rows |

### Pairing-stage output preview

`motif_output.txt` first 3 rows (cluster ⟶ motif1 ⟶ motif2 ⟶ ...):

```
<<MOTIF_OUTPUT_HEAD>>
```

Total enriched pair rows: **<<MOTIF_OUTPUT_LINES>>**.

## Verification

<<OVERALL_VERDICT>>

<<CHECK_TABLE>>

### Reproducing this audit

```bash
python3 tests/audit/generate.py intervals
```

The motif_output.txt sha is anchored to `data/demos/intervals` on this
machine. Both the demo data and pair_parallel's output are
deterministic — any sha drift is a real regression signal.
