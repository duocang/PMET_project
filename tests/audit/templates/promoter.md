# promoter — full PMET on gene promoters

<<RUN_HEADER>>

**Source:** [`scripts/workflows/promoter.sh`](../../scripts/workflows/promoter.sh)
&nbsp;&nbsp;**Used by:** CLI research runs · web `promoters` mode

## Purpose

The canonical PMET pipeline. Given a genome FASTA, a GFF3 annotation,
a MEME motif file, and a gene-cluster list, it asks:

> **Within the promoters of the user's gene clusters, which pairs of
> transcription-factor motifs co-occur more than expected by chance?**

Co-occurrence above null is a fingerprint of TF cooperativity — most TFs
don't bind alone; partner TFs land at neighbouring sites and the
combination drives the regulatory output. PMET uses a **hypergeometric
test** to score per-cluster motif-pair enrichment, **gated by a per-motif
binomial pre-filter** built during indexing. The two stages compose:

  1. **Indexing (per motif, once per universe):** `index_fimo_fused`
     scans every promoter and records per-motif binomial-distribution
     thresholds in `binomial_thresholds.txt`, calibrated so only the
     top ~`--topn` hits cross.
  2. **Pairing (per cluster + motif pair):** `pair_parallel` enumerates
     pairs `(m1, m2)`, intersects their per-promoter hit sets,
     re-evaluates the per-pair binomial threshold (drops pairs that
     fall below it), then runs a **hypergeometric test** comparing the
     overlap with the user's gene cluster against the universe-wide
     background — the resulting p-value is what motif_output.txt
     reports per `(cluster, m1, m2)`.

This script is the longest of the four (~2 minutes wall on TAIR10 +
Franco-Zorrilla at 4 threads, dominated by FIMO scanning the 113-motif
set against ~30k 1 kb promoters).

## Biological setup

- **"Promoter"** here means the user-configurable upstream window of
  the gene's transcription start (default 1000 bp), optionally plus
  the gene's 5' UTR. Overlapping windows from neighbouring genes are
  trimmed so each base is attributed to at most one promoter (controlled
  by `-v NoOverlap`).
- **"Universe"** is every gene that survives the promoter-extraction
  filters (size ≥ 20 bp, valid sequence). This is the null background
  the pair test compares against.
- **"Cluster"** is one row of the gene-list file: `<cluster_label>
  <gene_id>`. Each cluster is tested independently for pair enrichment.

The deeper biology and stage-by-stage construction of the promoter set
is documented separately in
[`docs/methods/promoter-extraction.md`](../methods/promoter-extraction.md).

## What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + binary preflight | locate `build/{index_fimo_fused, pair_parallel}` | Single failure point if either binary is missing |
| 2 | TAIR10 fetch (if absent) | `bash scripts/fetch_reference.sh` | One-shot ~220 MB download; subsequent runs find the file and skip |
| 3 | Chromosome-name preflight | compare GFF3 first chrom vs FASTA first header | Catches the `'1'` vs `'Chr1'` mismatch that silently produces empty BED downstream — quick fail beats a 2-minute "everything succeeded but indexed nothing" run |
| 4 | Homotypic indexing | `scripts/python/run_homotypic.py` — delegates the 10-step chain below | The expensive scan; produces the universe + per-motif binary fimohits + per-motif binomial thresholds |
| 4.1 | Sort GFF3 | `scripts/third_party/gff3sort/gff3sort.pl` | Some downstream tools assume sorted GFF3; this normalises arbitrary input |
| 4.2 | Build gene BED | `scripts/python/gff3_to_gene_bed.py` | Pulls the gene-row subset (`feature == 'gene'` or the wider `gene$`-regex set) into a 6-column BED |
| 4.3 | Chromosome lengths | `scripts/python/genome_chrom_lengths.py` | `bedtools flank` needs a `<chr> <length>` table to clamp at chromosome ends |
| 4.4 | Linearise FASTA + faidx | inline awk + `samtools faidx` | Single-line records make sed/grep predictable; the `.fai` index is consumed by `bedtools getfasta` later |
| 4.5 | Build promoters | `scripts/python/build_promoters.py` | The conceptual core — `bedtools flank -l <length> -r 0 -s` → trim against gene bodies → optional 5'-UTR extension → `bedtools getfasta -s` → drop fragments < min length → emit `promoter.fa` + `promoter_lengths.txt` |
| 4.6 | IC per motif | `scripts/python/calculateICfrommeme_IC_to_csv.py` | Reads the combined MEME directly (deterministic motif order); upper-cases motif IDs so they line up with what index_fimo_fused writes |
| 4.7 | MEME header upper-casing | inline (`meme_upper.meme`) | Same case as IC.txt → matches index_fimo_fused's binary fimohits and binomial_thresholds.txt; `pair_parallel` does case-sensitive lookups |
| 4.8 | FIMO + indexing | `build/index_fimo_fused` (one OpenMP-batched call) | The scan itself; writes `binomial_thresholds.txt` + `fimohits/<MOTIF>.bin` (PMETBN01 binary) |
| 4.9 | Sanity: file count | inline `find ... -name '*.bin' \| wc -l` | Catches "indexing didn't crash but produced 0 files" early |
| 4.10 | Contract validation | `scripts/python/check_homotypic_contract.py` | Asserts the schema in `docs/methods/homotypic-contract.md` (motif sets across binomial / IC / fimohits, type checks) |
| 5 | Heterotypic gene filter | `grep -wFf universe.txt <gene_list>` | Drop user-list genes that aren't in the indexed universe (no promoter passed extraction) |
| 6 | Pair test | `build/pair_parallel -d <homotypic> -g <kept> ...` → temp shards | Per-cluster hypergeometric pair enrichment, gated by the per-motif binomial pre-filter in `binomial_thresholds.txt` |
| 7 | Shard aggregation | `cat temp*.txt > motif_output.txt` then `rm temp*.txt` | pair_parallel doesn't unify shards itself |
| 8 | Heatmaps (optional) | three `Rscript scripts/r/draw_heatmap.R` calls | Skipped silently if `Rscript` is absent |

## Run snapshot

This audit just ran:

```
<<COMMAND_DISPLAYED>>
```

Indexing landed at `<<HOMOTYPIC_DIR>>/`,
pairing at `<<HETEROTYPIC_DIR>>/`,
plots at `<<PLOT_DIR>>/`.

### Indexing-stage outputs

| File | Rows / count | Meaning |
|---|---|---|
| `fimohits/*.bin` | <<FIMOHITS_COUNT>> files | one PMETBN01 file per motif (113 in Franco-Zorrilla) |
| `binomial_thresholds.txt` | <<BINOMIAL_LINES>> rows | per-motif p-value cutoff for `--topn 5000` |
| `IC.txt` | <<IC_LINES>> rows | per-motif positional information content |
| `universe.txt` | <<UNIVERSE_LINES>> rows | every gene with a valid extracted promoter |
| `promoter_lengths.txt` | <<PROMOTER_LENGTHS_LINES>> rows | should equal `universe.txt` rows |

### Pairing-stage output preview

`motif_output.txt` first 3 rows (cluster ⟶ motif1 ⟶ motif2 ⟶ ...):

```
<<MOTIF_OUTPUT_HEAD>>
```

Total enriched pair rows: **<<MOTIF_OUTPUT_LINES>>** — these are the
per-cluster motif pairs that survived pair_parallel's binomial
pre-filter and the cluster-level hypergeometric test at the canonical
IC and FIMO thresholds.

## Verification

<<OVERALL_VERDICT>>

<<CHECK_TABLE>>

### Reproducing this audit

```bash
python3 tests/audit/generate.py promoter
```

The motif_output.txt sha anchor `4b24906a...` was independently
verified against the recorded `cli/03_promoter.sh` baseline (cf.
commit `d2663c0`'s message). pair_only.sh against this same homotypic
index produces the same sha — that's the cross-validation that ties
the pair_only audit to the promoter audit.

### Cost

This run took **<<SECONDS>>s** at 4 threads. The dominant cost is
stage 4 (FIMO scanning 113 motifs across ~30k 1 kb promoters); pair
testing in stage 6 takes <30s of that.
