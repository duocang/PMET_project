# elements — full PMET on a chosen genomic element (UTR / CDS / mRNA / exon)

_Audit refreshed 2026-04-29 13:18:10 UTC on this machine — workflow `elements`, exit 0, 183.6s_

**Source:** [`pipeline/workflows/elements.sh`](../../pipeline/workflows/elements.sh)
&nbsp;&nbsp;**Helper sub-workflow:** [`pipeline/workflows/cli/_pmet_index_element.sh`](../../pipeline/workflows/cli/_pmet_index_element.sh)
&nbsp;&nbsp;**Used by:** CLI research runs only (no web entry point)

## Purpose

Same shape as `promoter.sh` — homotypic indexing then heterotypic
pair test then heatmaps — but the indexed unit is **a chosen genomic
element** rather than the canonical 1 kb upstream window. Useful when:

- You're asking whether motif pair-enrichment patterns differ between
  promoters, 5' UTRs, CDS, and exons. (They do — TF binding partners
  in 5' UTRs are not the same set as in promoters.)
- The species you care about has unusual gene architecture and
  "promoter = 1 kb upstream" is a poor model.
- You want to compare longest-isoform vs all-isoforms-merged
  aggregation strategies (the `-s` flag).

This is a **research workflow**, not exposed in the web UI.

## Biological setup

For each gene, multiple isoforms typically share a transcription start
but can have different element boundaries (e.g. 5' UTR length varies
across splice variants). Two strategies:

- **`-s longest`** — pick the single isoform whose total element span
  is greatest, keep every fragment of that isoform. The default for
  research runs.
- **`-s merged`** — take the per-gene UNION of all isoforms' element
  intervals (overlapping intervals merged into a non-redundant set).
  No isoform specificity, no UTR subtraction.

For `-e mRNA` specifically there are **three biologically distinct modes**
depending on `-s` and `-m`:

| `-s` / `-e` / `-m` | What gets indexed | When to use |
|---|---|---|
| `-s longest -e mRNA -m Yes` | the longest isoform's full mRNA span (UTRs + CDS, single interval per gene) | binding analysis where 5'/3' UTR regulatory sites matter equally to CDS |
| `-s longest -e mRNA -m No` (default) | the same isoform with its annotated UTRs subtracted (CDS span as one interval per gene) | "what binds along the coding span" without UTR contamination, but at gene granularity (one interval per gene, not per CDS fragment) |
| `-s longest -e CDS` (or `-e exon`) | per-CDS-fragment / per-exon intervals from the longest isoform | per-fragment resolution — useful for asking whether motif co-occurrence localises to specific CDS fragments / exons |

`-m` is ignored for `-s merged` and for any non-mRNA element.

Both strategies typically produce multiple intervals per gene
(e.g. 3 exons → 3 intervals; one mRNA span → 1 interval). The script
tags each interval as `__GENE__N` (gene name + 1-based index) so FIMO
can scan them separately, then a **gene-level fold** in step 9
collapses per-interval hits back to per-gene rows so pair_parallel
sees one row per gene.

## What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + element prompt | `-s longest\|merged`, `-e 3UTR\|5UTR\|mRNA\|CDS\|exon`, optional `-m Yes\|No` | Strategy + element + (mRNA only) full-span flag |
| 2 | TAIR10 fetch (if absent) | `bash pipeline/data/fetch_tair10.sh` | One-shot download |
| 3 | Chromosome-name preflight | GFF3 first chrom vs FASTA first header | Same fail-fast as `promoter.sh` |
| 4 | Element BED extraction | `_pmet_index_element.sh` step 1 — awk over GFF3 column 3 | Filters rows where `feature == element`; pulls `<key>=<id>` from the attributes column |
| 5 | Isoform aggregation | `_pmet_index_element.sh` step 2 — `longest` / `merged` branch (and the optional UTR-subtraction sub-step for `-s longest -e mRNA -m No`) | See "biological setup" |
| 6 | Interval tagging + length filter | `_pmet_index_element.sh` step 3 — append `__GENE__N`, drop fragments < 30 bp | The tag survives FIMO scanning so step 10 can demangle it |
| 7 | Universe + per-interval lengths | `_pmet_index_element.sh` step 4 — `cut -f1 promoter_lengths.txt` → `universe.txt` | Index metadata |
| 8 | Promoter FASTA extract | `_pmet_index_element.sh` step 5 — `bedtools getfasta -s` (strand-aware) over a linearised + faidx'd genome | Per-interval sequences for FIMO |
| 9 | Markov background | `_pmet_index_element.sh` step 6 — `fasta-get-markov` over the just-extracted promoter set | Zero-order base composition; FIMO uses it as the null model so p-values reflect the local element composition rather than the genome's |
| 10 | IC.txt | `_pmet_index_element.sh` step 7 — `calculateICfrommeme_IC_to_csv.py` | Per-motif positional information content; `pair_parallel` uses this as a sanity floor (skip motifs less informative than `-i`) |
| 11 | FIMO + indexing | `_pmet_index_element.sh` step 8 — one `index_fimo_fused` call (OpenMP) | Replaces the older two-step (split MEME → parallel fimo → separate pmet indexer) flow that depended on PMET-patched `--topn`/`--topk` flags absent from upstream MEME's `fimo` (commit `d2663c0`) |
| 12 | **Gene-level fold** | `_pmet_index_element.sh` step 9 — `pipeline/python/collapse_element_fimohits.py` | Decodes PMETBN01 binary fimohits, strips `__GENE__N` from sequence names, groups hits by gene, keeps top-`maxk` per gene by ascending p-value, filters against the per-motif binomial threshold, re-encodes. Also normalises `binomial_thresholds.txt` motif IDs to upper-case to match IC.txt and the fimohits filenames |
| 13 | Indexing contract validation | `pipeline/python/check_homotypic_contract.py <homotypic>` | Catches motif-id case mismatches and missing files |
| 14 | Heterotypic loop over `data/genes/*.txt` | for each task: filter by universe → `pair_parallel` → optional heatmaps | Per-task `02_heterotypic_<task>/motif_output.txt`. Heatmap failures (e.g. ggsave's 50-inch dimension cap on huge tasks) are non-fatal — the loop continues |

## Run snapshot

This audit just ran:

```
bash pipeline/workflows/elements.sh -s longest -e 5UTR -t 4
```

Output root: `results/cli/elements_longest_five_prime_UTR/`.

### Indexing-stage outputs

| File | Rows / count | Meaning |
|---|---|---|
| `01_homotypic/fimohits/*.bin` | 113 files | one PMETBN01 file per motif (113 in Franco-Zorrilla) |
| `01_homotypic/binomial_thresholds.txt` | 113 rows | per-motif p-value cutoff (case-normalized by the collapse step) |
| `01_homotypic/IC.txt` | 113 rows | per-motif positional information content |
| `01_homotypic/universe.txt` | 22733 rows | every gene with a valid 5'UTR |
| `01_homotypic/promoter_lengths.txt` | 22733 rows | should equal `universe.txt` rows after gene-level fold |

### Heterotypic per-task summary

The script loops over every `data/genes/*.txt` file. Per-task results:

| task | motif_output rows | sha-256 (16) | anchor match |
|---|---|---|---|
| `gene_cortex_epidermis_pericycle` | 18985 | `821f00782d42e230` | ✅ |
| `genes_cell_type_treatment` | 37969 | `0c9ca861133e4401` | ✅ |
| `heat_top300` | 12657 | `8cb976813f466199` | ✅ |
| `random_genes_300` | 25313 | `325fc7241b23055d` | ✅ |
| `random_genes_topN` | 189841 | `3bf2de6907d611f7` | ✅ |
| `salt_top300` | 12657 | `8769c45243a01df2` | ✅ |

(`missing` rows = the gene list had zero overlap with the 5'UTR
universe, so the script skipped pair_parallel for that task — that's
expected biology, not a failure.)

Total enriched pair rows across all tasks: **297422**.

## Verification

✅ **PASS** — all 18 check(s) passed

| # | Check | Expected | Observed | Verdict |
|---|---|---|---|---|
| 1 | script exit code | `0` | `0` | ✅ PASS |
| 2 | fimohits/*.bin per motif | `113` | `113` | ✅ PASS |
| 3 | binomial_thresholds rows == motifs | `113` | `113` | ✅ PASS |
| 4 | IC.txt rows == motifs | `113` | `113` | ✅ PASS |
| 5 | universe.txt non-empty (genes with 5'UTR) | `>= 1` | `22733` | ✅ PASS — TAIR10 has ~22k genes with annotated 5' UTRs |
| 6 | promoter_lengths.txt rows == universe (post-collapse) | `22733` | `22733` | ✅ PASS — collapse_element_fimohits.py also folds the per-interval promoter_lengths into per-gene sums |
| 7 | one heterotypic dir per gene list | `6` | `6` | ✅ PASS — data/genes/*.txt globbed — bump n_gene_lists in spec if you add/remove files |
| 8 | at least 1 task produced motif_output | `>= 1` | `6` | ✅ PASS — some gene lists have zero overlap with the 5'UTR universe; that's biology, not failure |
| 9 | total enriched pair rows across tasks | `>= 1000` | `297422` | ✅ PASS — lower bound; canonical run yields ~297k rows total |
| 10 | indexing contract: binomial == IC motifs | `set equal` | `|both|=113` | ✅ PASS |
| 11 | indexing contract: binomial == fimohits motifs | `set equal` | `|both|=113` | ✅ PASS |
| 12 | indexing contract: IC == fimohits motifs | `set equal` | `|both|=113` | ✅ PASS |
| 13 | per-task anchor: gene_cortex_epidermis_pericycle | `821f00782d42e230…` | `821f00782d42e230…` | ✅ PASS |
| 14 | per-task anchor: genes_cell_type_treatment | `0c9ca861133e4401…` | `0c9ca861133e4401…` | ✅ PASS |
| 15 | per-task anchor: heat_top300 | `8cb976813f466199…` | `8cb976813f466199…` | ✅ PASS |
| 16 | per-task anchor: random_genes_300 | `325fc7241b23055d…` | `325fc7241b23055d…` | ✅ PASS |
| 17 | per-task anchor: random_genes_topN | `3bf2de6907d611f7…` | `3bf2de6907d611f7…` | ✅ PASS |
| 18 | per-task anchor: salt_top300 | `8769c45243a01df2…` | `8769c45243a01df2…` | ✅ PASS |

### Reproducing this audit

```bash
python3 tests/audit/generate.py elements
```

This audit deliberately uses `-s longest -e 5UTR` (smallest element by
universe size) for fast iteration. To audit the merged strategy or a
larger element, the spec needs another invocation; the architecture
verification (FIMO + collapse + pair) is identical regardless of which
strategy/element pair runs.

### Known limitation

R `ggsave` enforces a hard 50-inch dimension cap. Some gene tasks
(e.g. `random_genes_topN`'s ~190k motif-pair output) blow past that
and the heatmap step exits non-zero for that task. `elements.sh`
catches this with `|| print_orange "..."` so a single heatmap failure
doesn't take down the rest of the loop — the data outputs
(`motif_output.txt`) for that task are unaffected.
