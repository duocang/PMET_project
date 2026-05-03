# Promoter PMET analysis — walkthrough

**[English](#en) · [汉文](#cn)**

> **About this doc:** path references throughout match the **current** monorepo layout (`scripts/workflows/promoter.sh`, `data/reference/TAIR10.*`, `data/motifs/...`, `results/cli/promoter/`, etc). The biology and algorithm content predates the monorepo merge — that's all unchanged from the original PMET. Inline `:line-range` annotations after a script path were captured against the pre-monorepo `03_promoter.sh` (retired, folded into the current `scripts/workflows/promoter.sh`); treat them as **section hints**, not exact citations.

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Pipeline purpose](#en-1) | [5. Final outputs](#en-5) |
| [2. Inputs](#en-2) | [6. Risks / edge cases](#en-6) |
| [3. Output contract](#en-3) | [7. Summary](#en-7) |
| [4. Step-by-step execution story](#en-4) | [汉文](#cn) |

<a id="en-1"></a>

## 1. Pipeline purpose

Find pairs of transcription-factor motifs that are co-enriched in the 1 kb upstream regions ("promoters") of a user-supplied gene cluster list, on the *Arabidopsis thaliana* TAIR10 reference, and render the result as motif × motif heatmaps per cluster.

The intuition is the canonical PMET test: most TFs do not act alone; two motifs that show up together in a cluster's promoters more than expected by chance are evidence of cooperative regulation. Pipeline 03 is the baseline form — promoters defined relative to the TSS, no gap, 5' UTR included, gene-body overlap stripped.

<a id="en-2"></a>

## 2. Inputs

| File | Biological meaning | Format | Truncated sample |
|---|---|---|---|
| `data/reference/TAIR10.fasta` | TAIR10 nuclear + organelle genome, ~135 Mb | linear FASTA, 7 records (`1..5,Mt,Pt`) | first headers: `>1`, `>2`, `>3` |
| `data/reference/TAIR10.gff3` | Ensembl/TAIR10 annotation | GFF3 v3 | `##gff-version 3` then `##sequence-region 1 1 30427671 …` |
| `data/motifs/Franco-Zorrilla_et_al_2014.meme` | 113 plant TF motifs (Franco-Zorrilla 2014) | MEME v4 | 113 lines starting `MOTIF ` |
| `data/genes/genes_cell_type_treatment.txt` | gene-cluster mapping for the heterotypic test | `<cluster_label> <gene_id>` per line, 1660 rows, 6 clusters | `Epidermis_flg22_up AT1G53080` |
| `build/indexing_fimo_fused` | fused FIMO + PMET indexer | ELF/macho binary | n/a |
| `build/pairing_parallel` | heterotypic pair tester | binary | n/a |

Each input passes its preflight check in `scripts/workflows/promoter.sh:108-126`:

- `check_file` confirms non-empty;
- `check_dep` confirms `samtools / bedtools / sortBed / fasta-get-markov / parallel / python3` exist;
- chromosome-name preflight (`'1'` vs `'Chr1'`) compares the first data row of the GFF3 against the first FASTA header. Both are `1` on this dataset → **PASS**.

<a id="en-3"></a>

## 3. Output contract

After a clean run the pipeline must populate three subtrees under `results/cli/promoter/`:

- `01_homotypic/`
  - `universe.txt` — gene set scanned by FIMO (one id / line).
  - `promoter_lengths.txt` — `<gene>\t<length>`.
  - `binomial_thresholds.txt` — `<motif>\t<thr>\t<extra>`.
  - `IC.txt` — `<motif> <ic1> <ic2> ...`.
  - `fimohits/<motif>.txt` — per-motif FIMO TSV.
- `02_heterotypic/`
  - `motif_output.txt` — 11-column TSV.
  - `pmet.log` — `pair_parallel` stdout.
- `plot/`
  - `heatmap.png`, `heatmap_overlap.png`, `heatmap_overlap_unique.png`.

The contract is enforced by `scripts/python/check_homotypic_contract.py` called from `run_homotypic.py:259-262`.

<a id="en-4"></a>

## 4. Step-by-step execution story

The homotypic stage is delegated end-to-end to [scripts/python/run_homotypic.py](../../../scripts/python/run_homotypic.py). The numbering below is `run_homotypic.py`'s 10-step layout.

For intermediate inspection this audit re-ran only the homotypic stage into `results/pipeline_story/03_homotypic_sample/` with `--keep-intermediate`, so BED/FASTA artefacts that the production pipeline cleans up are visible. The contract files there match the canonical baseline byte-for-row-count (29824 universe genes, 113 motif files).

### Step 1 — Sort the GFF3 by genomic coordinate

#### Command / code path

```text
perl scripts/third_party/gff3sort/gff3sort.pl data/reference/TAIR10.gff3 > <out>/sorted.gff3
```

(`run_homotypic.py:146-149`)

#### Purpose

Stabilise downstream `awk` / coordinate joins. The TAIR10 GFF3 is already mostly sorted but `gff3sort.pl` enforces hierarchy (`gene → mRNA → exon`) and chromosome-then-start order.

#### Bioinformatics meaning

Hierarchical, sorted GFF3 is the assumption every downstream parser makes. Without it `parse_utrs.py` would mis-attach UTR rows to genes.

#### Input

`data/reference/TAIR10.gff3` — first non-comment row:

```
1   araport11   chromosome   1   30427671   .   .   .   ID=chromosome:1
```

#### Output

`sorted.gff3` (sandbox: 60 MB, in formal pipeline run cleaned up).

#### Expected properties

- Same number of non-comment rows as input (sort doesn't drop rows).
- Chromosome column comes from `{1..5,Mt,Pt}` only.

#### Observed result

`results/pipeline_story/03_homotypic_sample/sorted.gff3` exists, non-empty.

#### Assessment

PASS.

---

### Step 2 — Extract gene rows into BED

#### Command / code path

```text
python3 scripts/python/gff3_to_gene_bed.py \
    --gff3 sorted.gff3 --out genelines.bed \
    --id-key 'gene_id=' --feature-regex 'gene$'
```

(`run_homotypic.py:152-160`)

#### Purpose

Convert per-gene rows of the GFF3 into a BED6 ready for `bedtools flank`. With `gene_features=all` (the pipeline's current default, `03_promoter.sh:35-37`) the regex `gene$` matches `gene`, `ncRNA_gene`, `pseudogene`, `transposable_element_gene`, etc.

#### Bioinformatics meaning

PMET is gene-centric, not locus-centric. We want one promoter per gene, not per transcript. GFF3 column 4/5 are 1-based closed; BED is 0-based half-open, so `start = gff3_start - 1`.

#### Input

`sorted.gff3` rows where col 3 ends in `gene`. TAIR10 has 32833 such rows (32833 = `awk '!/^#/ && $3 ~ /gene$/' | wc -l`).

#### Output

`genelines.bed` (32833 rows). Sandbox sample:

```
1   3630   5899    AT1G01010   1   +
1   6787   9130    AT1G01020   1   -
1   11100  11372   AT1G03987   1   +
1   11648  13714   AT1G01030   1   -
1   23120  31227   AT1G01040   1   +
```

Columns: `chrom, start (0-based), end (open), gene_id, score, strand`.

#### Expected properties

- Every row has 6 fields, `start < end`, strand ∈ {`+`,`-`}.
- Gene id is unique per row (no transcripts).
- Chromosome ∈ FASTA header set.

#### Observed result

`awk '$3<=$2'` on `genelines.bed` returns 0 rows. Strand split among **32833 rows** is `+ ≈ -`. All chromosome ids are within the FASTA's seven sequences.

#### Assessment

PASS.

---

### Step 3 — Build per-chromosome length file

#### Command / code path

```text
python3 scripts/python/genome_chrom_lengths.py \
    --gff3 anno --genome genome.fa --out bedgenome.genome
```

(`run_homotypic.py:163-169`)

#### Purpose

`bedtools flank` needs `<chrom>\t<length>` so it can clip flanks at chromosome ends.

#### Output

`bedgenome.genome`:

```
1    30427671
2    19698289
3    23459830
4    18585056
5    26975502
Mt   366924
Pt   154478
```

#### Expected properties

- Identical chromosome set to the FASTA (`samtools faidx` baseline).
- Lengths positive integers.

#### Observed result

7 rows, lengths match `data/reference/TAIR10.fasta.fai` byte-for-byte.

#### Assessment

PASS.

---

### Step 4 — Linearise the genome FASTA

#### Command / code path

```text
linearise_fasta(args.genome, stripped_fa)   # newline-collapse per record
samtools faidx stripped_fa
```

(`run_homotypic.py:172-174`)

#### Purpose

`bedtools getfasta` is unhappy with multi-line FASTA records; the linearised form has at most one sequence line per record.

#### Bioinformatics meaning

No biology. Pure I/O canonicalisation.

#### Output

`genome_stripped.fa` (~120 MB) plus `.fai` index.

#### Expected properties

- One header + one sequence line per record (9 lines total for 7 records is tolerated because `linearise_fasta` writes a trailing newline).
- `samtools faidx` succeeds.

#### Observed result

Sandbox file exists, indexed; first record `>1` followed by a single 30,427,671-character sequence line.

#### Assessment

PASS.

---

### Step 5 — Build promoters

#### Command / code path

```text
python3 scripts/python/build_promoters.py \
    --gene-bed genelines.bed --genome-sizes bedgenome.genome \
    --genome-fasta genome_stripped.fa --sorted-gff3 sorted.gff3 \
    --length 1000 --gap 0 --overlap NoOverlap --utr Yes \
    --out-bed promoters.bed --out-fasta promoters.fa \
    --out-bg promoters.bg --out-lengths promoter_lengths.txt \
    --out-universe universe.txt --out-removed-dir <out>
```

(`run_homotypic.py:177-195`, `build_promoters.py`)

This single call does, in order:

1. `bedtools flank -l 1000 -r 0 -s` — strand-aware upstream flank.
2. `sortBed`.
3. (`gap > 0` only — not used here).
4. Drop promoters < 10 bp (edge clipping at chromosome boundaries).
5. `bedtools subtract -a promoters -b genelines.bed` — `NoOverlap` strips any region that intrudes on a downstream gene body.
6. Drop promoters < 20 bp post-subtraction.
7. `assess_integrity.py` keeps the TSS-side fragment when subtraction splits a promoter in two.
8. `parse_utrs.py` extends each promoter into its 5' UTR (because `utr=Yes`).
9. Compute `promoter_lengths.txt`.
10. Compute `universe.txt`.
11. `bedtools getfasta -name -s` (strand-aware) → sed-strip the `::chrom:start-end` and `(+)/(-)` suffixes.
12. `fasta-get-markov` → `promoters.bg` (zero-order Markov background).

#### Purpose

Build the canonical "promoter" sequence set against which FIMO will score motifs.

#### Bioinformatics meaning

This is the most biology-laden step in the pipeline:

- "Upstream" means **5' upstream of the TSS in transcription direction**, so the operation is strand-aware.
- The *core promoter* (the ~50 bp around the TSS) is intentionally *included* here (gap=0). Pipeline 05 turns gap on to drop it.
- 5' UTR inclusion (`utr=Yes`) lets motifs in the 5' UTR contribute, which is appropriate for many plant TFs whose binding sites cluster there.
- `NoOverlap` prevents a long-flank promoter from claiming a motif that actually sits inside a neighbouring gene body — important on the gene-dense Arabidopsis genome.

#### Input

`genelines.bed` (32833 rows), `bedgenome.genome` (7 rows), `genome_stripped.fa` + `.fai`, `sorted.gff3`.

#### Output

```
promoters.bed         29824 rows
promoter_lengths.txt  29824 rows
universe.txt          29824 rows
promoters.fa          29824 records
promoters.bg          5 rows  (A,C,G,T frequencies)
promoters_removed_lt10.bed   1 row
promoters_removed_lt20.bed   763 rows
```

`promoters.bed` first 5 rows (sandbox):

```
1   2630   3759    AT1G01010   1   +
1   8666   10130   AT1G01020   1   -
1   10100  11100   AT1G03987   1   +
1   12940  14714   AT1G01030   1   -
1   22120  23120   AT1G01040   1   +
```

`promoters.fa` first record header + first 60 bp:

```
>AT1G01010
ATATTGCTATTTCTGCCAATATTAAAACTTCACTTAGGAAGACTTGAACCTACCACACGT
```

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| BED `start < end` | every row | 0 violations |
| Strand ∈ {`+`,`-`} | every row | `+`=15010, `-`=14814 (≈ even) |
| Length ≤ 1000 + max(5'UTR) | yes | min=20, max=14813, mean=907 — *max=14813 ⇒ a gene whose annotated 5' UTR is ~14 kb* |
| `+` strand promoter ends at gene start | yes | `AT1G01010` gene 3630–5899 → promoter 2630–3759 (end = 3759 because UTR extension covers the first 129 bp of the gene record, since AT1G01010's 5' UTR is annotated inside `[3630, 3759)`) |
| `-` strand promoter is downstream of gene end | yes | `AT1G01020` gene 6787–9130 → promoter 8666–10130 (i.e. region adjacent to gene end at coord 9130, extended further by 5' UTR which on `-` strand sits at higher coordinates) |
| `-` strand FASTA is reverse-complemented | yes | last 80 bp of `+` slice `1:8667-10130`, reverse-complemented, exactly equals first 80 bp of `>AT1G01020` in `promoters.fa` |
| `universe.txt` gene set == `promoter_lengths.txt` gene set | yes | `comm -3` returns 0 differences |
| `promoter_lengths.txt $2 > 0` | yes | 0 violations |
| Loss from 32833 genes → 29824 promoters | ~3009 lost | matches: 1 (lt10) + 763 (lt20) + 2245 (no flankable upstream / fully overlapped) |

#### Observed result

All structural checks pass.

#### Assessment

PASS. The mean promoter length (907 bp) and the 763 sub-20 bp drops both confirm that `NoOverlap` is doing real work — promoters in gene-dense regions are being correctly trimmed.

The very long promoters (max=14,813 bp) are not a bug — they happen when `parse_utrs.py` joins a long, multi-exon 5' UTR onto the upstream flank. PMET's `topn` / `topk` budgets keep this from skewing binomial thresholds, but it is worth noting.

---

### Step 6 — Per-motif information content

#### Command / code path

```text
python3 scripts/python/parse_memefile.py    motifs.meme memefiles_ic/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py memefiles_ic/ IC.txt
```

(`run_homotypic.py:198-208`)

#### Purpose

For each motif compute per-position information content. PMET's heterotypic pairing uses the IC vector to weight position importance when scoring overlap.

#### Bioinformatics meaning

`IC = log2(4) − H(P)` per column of the PWM. High-IC positions are "specific" positions; low-IC positions tolerate any base.

#### Output

`IC.txt` (113 rows). Sample:

```
ZAT18 0.7434 1.3087 0.7953 1.0010 1.0010 0.7953 1.3087 0.7434
ATHB51 0.8777 1.8638 1.8947 0.9433 1.9055 1.8637 1.7314 0.9412
DEAR3 1.0026 0.8653 1.3315 1.5593 1.2274 0.4203 1.0745 0.1985
```

#### Expected properties

- 113 rows = 113 motifs.
- Each value ∈ [0, 2] (per DNA column).

#### Observed result

`wc -l IC.txt` → 113. Spot check on the rows above: all values within [0, 2].

#### Assessment

PASS.

---

### Step 7 — FIMO + PMETindex (fused)

#### Command / code path

```text
build/indexing_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile promoters.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<batch>.txt promoters.fa promoter_lengths.txt
```

(`run_homotypic.py:225-239`)

`parse_memefile_batches.py` first round-robins the 113 motifs into `threads=4` batches; the binary processes each batch with internal OpenMP parallelism.

#### Purpose

Two operations fused into one binary:

1. Run FIMO on each promoter against each motif at p ≤ 0.05.
2. Compute the per-motif binomial threshold (the p-value below which a hit is "significant" given the motif's hits-per-bp rate). This threshold is `binomial_thresholds.txt`'s second column.

#### Bioinformatics meaning

`topn` caps how many of the most-significant hits are kept per motif across the genome (5000 = "the top 5000 hits"); `topk` caps how many hits are kept per sequence (5 = "at most 5 hits per promoter, even if the motif occurs 10×"). Both keep PMET from being dominated by a small number of long, hit-rich promoters.

#### Output

```
fimohits/<motif>.txt   113 files, one per motif
binomial_thresholds.txt   113 rows
```

`fimohits/AHL12_2.txt` first 3 rows:

```
AHL12_2   AT3G04895   323   330   +   7.5362318840e+00   1.8847481230e-04
AHL12_2   AT3G04895   357   364   -   7.5362318840e+00   1.8847481230e-04
AHL12_2   AT3G04895   774   781   +   7.5362318840e+00   1.8847481230e-04
```

Columns: `motif, gene, start, end, strand, score, p-value`.

`binomial_thresholds.txt`:

```
MYB52    1.32e-02
MYB46_2  1.63e-03
MYB55_2  1.19e-03
```

#### Expected properties

- `len(fimohits/*.txt) == nummotifs` (113).
- Every fimohits row has gene id ∈ `universe.txt`.
- Every motif has at least one row in `binomial_thresholds.txt`.

#### Observed result

`ls fimohits | wc -l` → 113. `wc -l binomial_thresholds.txt` → 113. The pipeline emits `WARNING` if any fimohits file is empty; here no warning was logged.

#### Assessment

PASS.

---

### Step 8 — Homotypic contract validation

#### Command / code path

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```

(`run_homotypic.py:258-262`)

#### Purpose

Programmatic guard against silent output corruption. Verifies file shapes, header presence, gene-id consistency.

#### Output

stdout: `OK — homotypic contract holds (113 motifs, 29824 universe genes, 29824 genes with promoter lengths)`.

#### Assessment

PASS.

---

### Step 9 — Heterotypic motif-pair test

#### Command / code path

```text
build/pairing_parallel \
    -d . \
    -g <filtered_gene_list> -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/cli/promoter/02_heterotypic -t 4
```

(`03_promoter.sh:171-187`)

The user gene list is first filtered to genes present in `universe.txt` (`grep -Ff universe gene_input_file > gene_tmp`). The flag `-i 4` is the IC threshold below which positions are not used for overlap detection.

#### Purpose

For every (cluster, motif₁, motif₂) triple, test whether genes in the cluster have both motifs in their promoter more often than expected by chance, given the cluster size and the genome-wide rate.

#### Bioinformatics meaning

This is the actual PMET hypothesis. The output's adjusted p-values (BH within cluster, Bonferroni within cluster, global Bonferroni) are the headline result that the heatmaps render.

#### Input

- Filtered cluster file (1595 of 1660 input rows survived the universe filter — 65 input gene ids are not in TAIR10's gene set per `gene_features=all`, presumably aliases or AT-style-but-missing).
- Homotypic contract files.

#### Output

`motif_output.txt` — 11 columns, 37969 rows (excluding header).

```
Cluster                Motif 1  Motif 2     N_in_cluster_with_both  N_genome_with_both  N_in_cluster  Raw_p   BH      Bonf    Global_Bonf  Genes
Cortex_flg22_up        AHL12    AHL12_2     0                       197                 119           1.000   1.000   1.000   1.000        
Cortex_flg22_up        AHL12    AHL12_3ARY  3                       682                 119           5.14e-1 6.97e-1 1.000   1.000        AT1G05660;AT1G34420;AT3G25900;
```

#### Expected properties

- 11 tab-separated columns.
- One row per (cluster, motif_pair) — a row count near `clusters * C(motifs, 2)` = 6 × 6328 = 37968 (allowing one header row).
- p-values ∈ [0, 1].

#### Observed result

`awk -F'\t' 'NR==1{print NF}' motif_output.txt` → 11. Row count 37969 (= 1 header + 37968 pair rows). All p-values in sampled range valid.

#### Assessment

PASS.

---

### Step 10 — Heatmaps

#### Command / code path

```text
Rscript scripts/r/draw_heatmap.R All     plot/heatmap.png                motif_output.txt 5 3 6 FALSE
Rscript scripts/r/draw_heatmap.R Overlap plot/heatmap_overlap_unique.png motif_output.txt 5 3 6 TRUE
Rscript scripts/r/draw_heatmap.R Overlap plot/heatmap_overlap.png        motif_output.txt 5 3 6 FALSE
```

(`03_promoter.sh:198-201`)

#### Purpose

Render motif × motif p-value matrices, faceted by cluster.

#### Bioinformatics meaning

`mode=All` shows every significant pair; `mode=Overlap` keeps only pairs that share genes; `unique=TRUE` deduplicates pairs that show up in multiple clusters so each pair appears at most once.

#### Output

| File | Bytes | SHA-256 |
|---|---:|---|
| `plot/heatmap.png` | 1 230 836 | `d8d29fc14379b65124d037ca11e1c05596994ee4f1576d31eb78b2691e0ad73a` |
| `plot/heatmap_overlap.png` | 754 830 | `15a8518b1f7facf0719fc4613f9e0ca38ba88b39150efc07961da61a4cbb41b2` |
| `plot/heatmap_overlap_unique.png` | 765 219 | `f6efec89aa808d239980afe5f7951a5c6f876649d01c95004762d4ef2b0d1d5c` |

(Re-run by this audit on 2026-04-27 from the existing homotypic baseline; hashes match the pipeline's documented baseline exactly.)

#### Expected properties

- All three PNG files exist and are non-empty.
- The `unique` and non-`unique` overlap heatmaps differ.

#### Observed result

All three exist. The `_unique` and `_overlap` PNGs differ by 10 KB and have different hashes, so the `unique` flag is producing real filtering on this dataset (contrast: 05/06/07 produce identical unique vs non-unique PNGs because their cluster sets do not overlap in motif pairs — see the WARNING in those audits).

#### Assessment

PASS.

<a id="en-5"></a>

## 5. Final outputs

```
results/cli/promoter/
├── 01_homotypic/
│   ├── universe.txt              29824 lines (gene set scanned)
│   ├── promoter_lengths.txt      29824 lines
│   ├── binomial_thresholds.txt   113   rows  (one per motif)
│   ├── IC.txt                    113   rows
│   └── fimohits/                 113   files (one per motif)
├── 02_heterotypic/
│   ├── motif_output.txt          37969 rows (1 header + 6 clusters × 6328 pairs)
│   └── pmet.log                  binary stdout log
└── plot/
    ├── heatmap.png               1.23 MB
    ├── heatmap_overlap.png       754 KB
    └── heatmap_overlap_unique.png 765 KB
```

<a id="en-6"></a>

## 6. Risks / edge cases

1. **`gene_features=all` includes pseudogenes and TE-genes.** The universe contains pseudogenes and `transposable_element_gene` rows. For a strict TF-regulation analysis these may be undesirable; the `strict` mode (regex `^gene$`) drops them, taking the universe down from 29824 to ~24000. Decision is upstream of this pipeline.

2. **Long promoters from multi-exon 5' UTRs.** With `utr=Yes` we observed a max length of ~14,800 bp. PMET's per-sequence `topk` cap (5 hits) prevents these from dominating the binomial threshold, but the global FIMO budget (`topn=5000`) is the only safeguard against motif counts being inflated.

3. **`grep -Ff` filtering of the user gene list.** The user-supplied cluster file went from 1660 lines → 1595 lines (65 dropped). These are gene ids not in `universe.txt`. They are silently dropped; if a downstream analyst expects every input gene to be tested, this is a surprise. The pipeline does not log this loss explicitly.

4. **No retention of intermediate files.** With `keep_intermediate=false` (default) the BED/FASTA artefacts are gone after the run, so this audit had to re-derive them in a sandbox. Not a bug, but it does make post-hoc debugging harder.

<a id="en-7"></a>

## 7. Summary

**Overall status: PASS.** Pipeline 03 produces a contractually valid homotypic index, a structurally valid heterotypic table, and three distinct heatmaps from a strand-aware, gene-body-disjoint, 5' UTR-extended promoter set on TAIR10. All structural invariants (BED coords, strand-aware reverse-complementation on `−` strand, universe ≡ promoter_lengths gene set, fimohits count = motif count) hold.

The outputs are suitable for downstream PMET interpretation. The two caveats — silent loss of user gene ids that aren't in the universe, and the long-UTR-driven max promoter length — are observational, not defects.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. pipeline 用途](#cn-1) | [5. 最终输出](#cn-5) |
| [2. 输入](#cn-2) | [6. 风险 / 边界情况](#cn-6) |
| [3. 输出契约](#cn-3) | [7. 总结](#cn-7) |
| [4. 按 step 走读](#cn-4) | [English](#en) |

<a id="cn-1"></a>

## 1. pipeline 用途

在 *拟南芥* TAIR10 参考上，对用户提供的 gene cluster 列表，找出 1 kb 上游区域（"启动子"）里共富集的 TF motif 对，并按 cluster 出 motif × motif 的 heatmap。

直觉是经典 PMET 假设：多数 TF 不单干；若两个 motif 在某 cluster 启动子里同时出现的频率显著高于偶然预期，那就是协同调控的证据。pipeline 03 是基线形式 —— 启动子相对 TSS 定义，gap=0，包 5' UTR，gene body 重叠剔除。

<a id="cn-2"></a>

## 2. 输入

| 文件 | 生物学含义 | 格式 | 截样 |
|---|---|---|---|
| `data/reference/TAIR10.fasta` | TAIR10 核 + 细胞器基因组，~135 Mb | linear FASTA，7 条 record（`1..5,Mt,Pt`） | 头部：`>1`、`>2`、`>3` |
| `data/reference/TAIR10.gff3` | Ensembl/TAIR10 注释 | GFF3 v3 | `##gff-version 3` 然后 `##sequence-region 1 1 30427671 …` |
| `data/motifs/Franco-Zorrilla_et_al_2014.meme` | 113 个植物 TF motif（Franco-Zorrilla 2014） | MEME v4 | 113 行 `MOTIF ` 开头 |
| `data/genes/genes_cell_type_treatment.txt` | 异型测试用的 gene-cluster 映射 | 每行 `<cluster_label> <gene_id>`，1660 行，6 个 cluster | `Epidermis_flg22_up AT1G53080` |
| `build/indexing_fimo_fused` | FIMO + PMET 融合索引器 | ELF/macho 二进制 | n/a |
| `build/pairing_parallel` | 异型 pair 检验器 | 二进制 | n/a |

每个输入在 `scripts/workflows/promoter.sh:108-126` 都过 preflight：

- `check_file` 确认文件非空；
- `check_dep` 确认 `samtools / bedtools / sortBed / fasta-get-markov / parallel / python3` 都在；
- 染色体名 preflight（`'1'` vs `'Chr1'`）拿 GFF3 第一条数据行和 FASTA 第一行 header 比，本数据集都是 `1` → **PASS**。

<a id="cn-3"></a>

## 3. 输出契约

干净跑完之后，pipeline 必须在 `results/cli/promoter/` 下填出三个子树：

- `01_homotypic/`
  - `universe.txt` —— FIMO 扫描的 gene 集（一行一个 id）。
  - `promoter_lengths.txt` —— `<gene>\t<length>`。
  - `binomial_thresholds.txt` —— `<motif>\t<thr>\t<extra>`。
  - `IC.txt` —— `<motif> <ic1> <ic2> ...`。
  - `fimohits/<motif>.txt` —— 每 motif 一份 FIMO TSV。
- `02_heterotypic/`
  - `motif_output.txt` —— 11 列 TSV。
  - `pmet.log` —— `pair_parallel` stdout。
- `plot/`
  - `heatmap.png`、`heatmap_overlap.png`、`heatmap_overlap_unique.png`。

契约由 `scripts/python/check_homotypic_contract.py` 强制（`run_homotypic.py:259-262` 调用）。

<a id="cn-4"></a>

## 4. 按 step 走读

同型阶段端到端委托给 [scripts/python/run_homotypic.py](../../../scripts/python/run_homotypic.py)。下面的编号对应 `run_homotypic.py` 的 10 step 布局。

为方便中间检查，本审计带 `--keep-intermediate` 单独把同型阶段重跑到 `results/pipeline_story/03_homotypic_sample/`，因此正式 pipeline 会清理掉的 BED / FASTA 中间产物可见。该处的契约文件与官方 baseline 行数一致（29824 个 universe gene、113 个 motif 文件）。

### Step 1 —— 按基因组坐标排序 GFF3

#### 命令 / 代码路径

```text
perl scripts/third_party/gff3sort/gff3sort.pl data/reference/TAIR10.gff3 > <out>/sorted.gff3
```

(`run_homotypic.py:146-149`)

#### 用途

让下游 `awk` / 坐标 join 稳定。TAIR10 GFF3 本来就基本有序，但 `gff3sort.pl` 强制层级（`gene → mRNA → exon`）和"先染色体再 start"的顺序。

#### 生物信息含义

层级化、有序的 GFF3 是下游每个 parser 的前提假设。不排好序，`parse_utrs.py` 会把 UTR 行错挂到基因上。

#### 输入

`data/reference/TAIR10.gff3` —— 第一条非注释行：

```
1   araport11   chromosome   1   30427671   .   .   .   ID=chromosome:1
```

#### 输出

`sorted.gff3`（沙箱里 60 MB，正式 pipeline 跑完会清掉）。

#### 期望性质

- 非注释行数与输入一致（排序不丢行）。
- 染色体列只来自 `{1..5,Mt,Pt}`。

#### 观察结果

`results/pipeline_story/03_homotypic_sample/sorted.gff3` 存在，非空。

#### 评估

PASS。

---

### Step 2 —— 抽出 gene 行成 BED

#### 命令 / 代码路径

```text
python3 scripts/python/gff3_to_gene_bed.py \
    --gff3 sorted.gff3 --out genelines.bed \
    --id-key 'gene_id=' --feature-regex 'gene$'
```

(`run_homotypic.py:152-160`)

#### 用途

把 GFF3 里每基因一行的部分变成 BED6，给 `bedtools flank` 用。`gene_features=all`（pipeline 当前默认值，`03_promoter.sh:35-37`）下，`gene$` regex 匹配 `gene`、`ncRNA_gene`、`pseudogene`、`transposable_element_gene` 等。

#### 生物信息含义

PMET 是 gene 中心，不是 locus 中心。一个基因一条启动子，不是一个转录本一条。GFF3 的第 4/5 列是 1-based 闭区间；BED 是 0-based 半开，因此 `start = gff3_start - 1`。

#### 输入

`sorted.gff3` 里第 3 列以 `gene` 结尾的行。TAIR10 上有 32833 行（32833 = `awk '!/^#/ && $3 ~ /gene$/' | wc -l`）。

#### 输出

`genelines.bed`（32833 行）。沙箱样本：

```
1   3630   5899    AT1G01010   1   +
1   6787   9130    AT1G01020   1   -
1   11100  11372   AT1G03987   1   +
1   11648  13714   AT1G01030   1   -
1   23120  31227   AT1G01040   1   +
```

列：`chrom, start (0-based), end (open), gene_id, score, strand`。

#### 期望性质

- 每行 6 列、`start < end`、strand ∈ {`+`,`-`}。
- 每行 gene id 唯一（不带 transcript）。
- chromosome ∈ FASTA header 集合。

#### 观察结果

`awk '$3<=$2'` 跑 `genelines.bed` 返回 0 行。**32833 行**的 strand 分布 `+ ≈ -`。所有染色体 id 都在 FASTA 7 条 sequence 里。

#### 评估

PASS。

---

### Step 3 —— 建每染色体长度文件

#### 命令 / 代码路径

```text
python3 scripts/python/genome_chrom_lengths.py \
    --gff3 anno --genome genome.fa --out bedgenome.genome
```

(`run_homotypic.py:163-169`)

#### 用途

`bedtools flank` 需要 `<chrom>\t<length>` 才能在染色体边界把 flank 截短。

#### 输出

`bedgenome.genome`：

```
1    30427671
2    19698289
3    23459830
4    18585056
5    26975502
Mt   366924
Pt   154478
```

#### 期望性质

- 染色体集合与 FASTA 完全一致（以 `samtools faidx` 为基准）。
- 长度为正整数。

#### 观察结果

7 行，长度与 `data/reference/TAIR10.fasta.fai` 逐字节一致。

#### 评估

PASS。

---

### Step 4 —— 把基因组 FASTA 拉成单行

#### 命令 / 代码路径

```text
linearise_fasta(args.genome, stripped_fa)   # newline-collapse per record
samtools faidx stripped_fa
```

(`run_homotypic.py:172-174`)

#### 用途

`bedtools getfasta` 不喜欢多行 FASTA record；linearise 之后每 record 最多一行 sequence。

#### 生物信息含义

无生物。纯 I/O 规范化。

#### 输出

`genome_stripped.fa`（~120 MB）和 `.fai` index。

#### 期望性质

- 每 record 一行 header + 一行 sequence（7 个 record 总共 9 行也算合规，因为 `linearise_fasta` 末尾加换行）。
- `samtools faidx` 成功。

#### 观察结果

沙箱文件存在并被索引；第一条 record `>1` 后面跟单行 30,427,671 字符的 sequence。

#### 评估

PASS。

---

### Step 5 —— 构造启动子

#### 命令 / 代码路径

```text
python3 scripts/python/build_promoters.py \
    --gene-bed genelines.bed --genome-sizes bedgenome.genome \
    --genome-fasta genome_stripped.fa --sorted-gff3 sorted.gff3 \
    --length 1000 --gap 0 --overlap NoOverlap --utr Yes \
    --out-bed promoters.bed --out-fasta promoters.fa \
    --out-bg promoters.bg --out-lengths promoter_lengths.txt \
    --out-universe universe.txt --out-removed-dir <out>
```

(`run_homotypic.py:177-195`、`build_promoters.py`)

这一个调用按顺序做：

1. `bedtools flank -l 1000 -r 0 -s` —— strand-aware 上游 flank。
2. `sortBed`。
3. （`gap > 0` 才走 —— 这里不用）。
4. 丢掉 < 10 bp 的启动子（染色体边界裁剪后产生）。
5. `bedtools subtract -a promoters -b genelines.bed` —— `NoOverlap` 把入侵下游 gene body 的部分剔除。
6. subtract 后再丢掉 < 20 bp 的启动子。
7. `assess_integrity.py`：当 subtract 把启动子切成两段时，保留 TSS 一侧的 fragment。
8. `parse_utrs.py` 把每个启动子向 5' UTR 扩展（因为 `utr=Yes`）。
9. 算 `promoter_lengths.txt`。
10. 算 `universe.txt`。
11. `bedtools getfasta -name -s`（strand-aware）→ sed 去掉 `::chrom:start-end` 和 `(+)/(-)` 后缀。
12. `fasta-get-markov` → `promoters.bg`（zero-order Markov 背景）。

#### 用途

构造 PMET 的标准"启动子" sequence 集，给 FIMO 评分用。

#### 生物信息含义

这是 pipeline 里生物学意味最重的一步：

- "Upstream" 指 **transcription 方向上 TSS 的 5' 上游**，所以这一步是 strand-aware 的。
- *core promoter*（TSS 周围 ~50 bp）这里**故意保留**（gap=0）。pipeline 05 会打开 gap 把它去掉。
- `utr=Yes` 让 5' UTR 里的 motif 也参与计数；很多植物 TF 的结合位点恰好聚集在 UTR，所以这是合理的。
- `NoOverlap` 防止一条长 flank 启动子把实际位于邻近 gene body 内部的 motif 据为己有 —— 在基因密度高的拟南芥基因组里很重要。

#### 输入

`genelines.bed`（32833 行）、`bedgenome.genome`（7 行）、`genome_stripped.fa` + `.fai`、`sorted.gff3`。

#### 输出

```
promoters.bed         29824 rows
promoter_lengths.txt  29824 rows
universe.txt          29824 rows
promoters.fa          29824 records
promoters.bg          5 rows  (A,C,G,T frequencies)
promoters_removed_lt10.bed   1 row
promoters_removed_lt20.bed   763 rows
```

`promoters.bed` 前 5 行（沙箱）：

```
1   2630   3759    AT1G01010   1   +
1   8666   10130   AT1G01020   1   -
1   10100  11100   AT1G03987   1   +
1   12940  14714   AT1G01030   1   -
1   22120  23120   AT1G01040   1   +
```

`promoters.fa` 第一条 record 的 header + 前 60 bp：

```
>AT1G01010
ATATTGCTATTTCTGCCAATATTAAAACTTCACTTAGGAAGACTTGAACCTACCACACGT
```

#### 期望性质

| 检查 | 期望 | 观察 |
|---|---|---|
| BED `start < end` | 每行 | 0 违例 |
| Strand ∈ {`+`,`-`} | 每行 | `+`=15010、`-`=14814（≈ 各半） |
| 长度 ≤ 1000 + max(5'UTR) | 是 | min=20、max=14813、mean=907 —— *max=14813 ⇒ 某个基因注释的 5' UTR 长达 ~14 kb* |
| `+` strand 启动子终点落在 gene start | 是 | `AT1G01010` 基因 3630–5899 → 启动子 2630–3759（end = 3759 因为 UTR 扩展把基因 record 前 129 bp 也吃进来：AT1G01010 的 5' UTR 注释在 `[3630, 3759)` 内） |
| `-` strand 启动子在 gene end 之后 | 是 | `AT1G01020` 基因 6787–9130 → 启动子 8666–10130（即与基因 end 在 9130 相邻的区域，再被 5' UTR 向更高坐标扩展，因为 `-` strand 的 5' UTR 在更高坐标处） |
| `-` strand FASTA 反向互补正确 | 是 | `+` slice `1:8667-10130` 末 80 bp，反向互补后，与 `promoters.fa` 中 `>AT1G01020` 的前 80 bp 完全一致 |
| `universe.txt` gene 集 == `promoter_lengths.txt` gene 集 | 是 | `comm -3` 返回 0 差异 |
| `promoter_lengths.txt $2 > 0` | 是 | 0 违例 |
| 32833 基因 → 29824 启动子的损失 | ~3009 丢失 | 对得上：1（lt10） + 763（lt20） + 2245（无可 flank 上游 / 完全被 overlap） |

#### 观察结果

所有结构性检查通过。

#### 评估

PASS。mean 启动子长度（907 bp）和 763 条 < 20 bp 被丢，都说明 `NoOverlap` 在认真干活 —— 基因密集区里的启动子被正确截短。

特别长的启动子（max=14,813 bp）不是 bug —— 这是 `parse_utrs.py` 把多 exon 的长 5' UTR 拼到上游 flank 上造成的。PMET 的 `topn` / `topk` 预算可以防止它们扭曲 binomial 阈值，但仍然值得记一笔。

---

### Step 6 —— 每 motif 算 information content

#### 命令 / 代码路径

```text
python3 scripts/python/parse_memefile.py    motifs.meme memefiles_ic/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py memefiles_ic/ IC.txt
```

(`run_homotypic.py:198-208`)

#### 用途

对每个 motif 算每个位置的 information content。PMET 的异型 pairing 用 IC 向量给位置加权，决定哪些位置参与重叠判定。

#### 生物信息含义

每列 PWM 上 `IC = log2(4) − H(P)`。高 IC 位置是"特异"位置；低 IC 位置任何碱基都行。

#### 输出

`IC.txt`（113 行）。样本：

```
ZAT18 0.7434 1.3087 0.7953 1.0010 1.0010 0.7953 1.3087 0.7434
ATHB51 0.8777 1.8638 1.8947 0.9433 1.9055 1.8637 1.7314 0.9412
DEAR3 1.0026 0.8653 1.3315 1.5593 1.2274 0.4203 1.0745 0.1985
```

#### 期望性质

- 113 行 = 113 motif。
- 每个值 ∈ [0, 2]（每 DNA 列）。

#### 观察结果

`wc -l IC.txt` → 113。抽查上面三行：所有值都在 [0, 2] 内。

#### 评估

PASS。

---

### Step 7 —— FIMO + PMETindex（融合）

#### 命令 / 代码路径

```text
build/indexing_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile promoters.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<batch>.txt promoters.fa promoter_lengths.txt
```

(`run_homotypic.py:225-239`)

`parse_memefile_batches.py` 先把 113 motif round-robin 分到 `threads=4` 个 batch；二进制每个 batch 内部还用 OpenMP 并行。

#### 用途

一个二进制里融合两步：

1. 对每个启动子 × 每个 motif 跑 FIMO，阈值 p ≤ 0.05。
2. 算每 motif 的 binomial 阈值（基于该 motif 每 bp 命中率，决定何为"显著"hit）。这就是 `binomial_thresholds.txt` 第二列。

#### 生物信息含义

`topn` 控制每 motif 全基因组保留的最显著 hit 数（5000 = "top 5000 hits"）；`topk` 控制每序列保留的 hit 数（5 = "每启动子至多 5 个 hit，即便 motif 出现 10 次"）。两个加在一起防止 PMET 被少数长且 hit 多的启动子主导。

#### 输出

```
fimohits/<motif>.txt   113 files, one per motif
binomial_thresholds.txt   113 rows
```

`fimohits/AHL12_2.txt` 前 3 行：

```
AHL12_2   AT3G04895   323   330   +   7.5362318840e+00   1.8847481230e-04
AHL12_2   AT3G04895   357   364   -   7.5362318840e+00   1.8847481230e-04
AHL12_2   AT3G04895   774   781   +   7.5362318840e+00   1.8847481230e-04
```

列：`motif, gene, start, end, strand, score, p-value`。

`binomial_thresholds.txt`：

```
MYB52    1.32e-02
MYB46_2  1.63e-03
MYB55_2  1.19e-03
```

#### 期望性质

- `len(fimohits/*.txt) == nummotifs`（113）。
- 每个 fimohits 行的 gene id ∈ `universe.txt`。
- 每个 motif 在 `binomial_thresholds.txt` 至少有一行。

#### 观察结果

`ls fimohits | wc -l` → 113。`wc -l binomial_thresholds.txt` → 113。如果某 fimohits 文件空，pipeline 会打 `WARNING`；这里没出现。

#### 评估

PASS。

---

### Step 8 —— 同型契约校验

#### 命令 / 代码路径

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```

(`run_homotypic.py:258-262`)

#### 用途

防止悄悄崩坏的程序化 guard。校验文件形状、header 是否在、gene id 是否一致。

#### 输出

stdout：`OK — homotypic contract holds (113 motifs, 29824 universe genes, 29824 genes with promoter lengths)`。

#### 评估

PASS。

---

### Step 9 —— 异型 motif-pair 检验

#### 命令 / 代码路径

```text
build/pairing_parallel \
    -d . \
    -g <filtered_gene_list> -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/cli/promoter/02_heterotypic -t 4
```

(`03_promoter.sh:171-187`)

用户 gene list 先按 `universe.txt` 过滤（`grep -Ff universe gene_input_file > gene_tmp`）。`-i 4` 是 IC 阈值，低于此值的位置不参与重叠判定。

#### 用途

对每个 (cluster, motif₁, motif₂) 三元组，给定 cluster 大小和全基因组率，检验 cluster 里同时含两个 motif 的基因是否显著多于偶然预期。

#### 生物信息含义

这是 PMET 真正的假设检验。输出里调整后的 p（cluster 内 BH、cluster 内 Bonferroni、全局 Bonferroni）就是 heatmap 渲染的核心结果。

#### 输入

- 过滤后的 cluster 文件（1660 行输入里 1595 行过了 universe 过滤 —— 65 个输入 gene id 不在 TAIR10 的 `gene_features=all` gene 集里，可能是别名或者像 AT 但不存在的 id）。
- 同型契约文件。

#### 输出

`motif_output.txt` —— 11 列，37969 行（不含 header）。

```
Cluster                Motif 1  Motif 2     N_in_cluster_with_both  N_genome_with_both  N_in_cluster  Raw_p   BH      Bonf    Global_Bonf  Genes
Cortex_flg22_up        AHL12    AHL12_2     0                       197                 119           1.000   1.000   1.000   1.000        
Cortex_flg22_up        AHL12    AHL12_3ARY  3                       682                 119           5.14e-1 6.97e-1 1.000   1.000        AT1G05660;AT1G34420;AT3G25900;
```

#### 期望性质

- 11 个 tab 分隔列。
- 每行一个 (cluster, motif_pair)。行数应接近 `clusters * C(motifs, 2)` = 6 × 6328 = 37968（外加一行 header）。
- p ∈ [0, 1]。

#### 观察结果

`awk -F'\t' 'NR==1{print NF}' motif_output.txt` → 11。行数 37969（= 1 header + 37968 pair）。抽样的 p 都在合法区间。

#### 评估

PASS。

---

### Step 10 —— Heatmap

#### 命令 / 代码路径

```text
Rscript scripts/r/draw_heatmap.R All     plot/heatmap.png                motif_output.txt 5 3 6 FALSE
Rscript scripts/r/draw_heatmap.R Overlap plot/heatmap_overlap_unique.png motif_output.txt 5 3 6 TRUE
Rscript scripts/r/draw_heatmap.R Overlap plot/heatmap_overlap.png        motif_output.txt 5 3 6 FALSE
```

(`03_promoter.sh:198-201`)

#### 用途

按 cluster 出 motif × motif p-value 矩阵的分面图。

#### 生物信息含义

`mode=All` 显示所有显著 pair；`mode=Overlap` 只保留共享基因的 pair；`unique=TRUE` 把多 cluster 中重复出现的 pair 去重，使每个 pair 只出现一次。

#### 输出

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `plot/heatmap.png` | 1 230 836 | `d8d29fc14379b65124d037ca11e1c05596994ee4f1576d31eb78b2691e0ad73a` |
| `plot/heatmap_overlap.png` | 754 830 | `15a8518b1f7facf0719fc4613f9e0ca38ba88b39150efc07961da61a4cbb41b2` |
| `plot/heatmap_overlap_unique.png` | 765 219 | `f6efec89aa808d239980afe5f7951a5c6f876649d01c95004762d4ef2b0d1d5c` |

（本审计 2026-04-27 在已有同型 baseline 上重跑；hash 与官方文档基线完全一致。）

#### 期望性质

- 三个 PNG 都存在且非空。
- `unique` 与非 `unique` 的 overlap heatmap 不同。

#### 观察结果

三个都存在。`_unique` 与 `_overlap` PNG 差 10 KB，hash 也不同，说明 `unique` flag 在本数据集上确实做了过滤（对照：05/06/07 的 unique 与非 unique PNG 一模一样，因为它们的 cluster 集在 motif pair 上不重合 —— 见那几份审计里的 WARNING）。

#### 评估

PASS。

<a id="cn-5"></a>

## 5. 最终输出

```
results/cli/promoter/
├── 01_homotypic/
│   ├── universe.txt              29824 lines (gene set scanned)
│   ├── promoter_lengths.txt      29824 lines
│   ├── binomial_thresholds.txt   113   rows  (one per motif)
│   ├── IC.txt                    113   rows
│   └── fimohits/                 113   files (one per motif)
├── 02_heterotypic/
│   ├── motif_output.txt          37969 rows (1 header + 6 clusters × 6328 pairs)
│   └── pmet.log                  binary stdout log
└── plot/
    ├── heatmap.png               1.23 MB
    ├── heatmap_overlap.png       754 KB
    └── heatmap_overlap_unique.png 765 KB
```

<a id="cn-6"></a>

## 6. 风险 / 边界情况

1. **`gene_features=all` 把 pseudogene 和 TE-gene 都包进来。** universe 里既有 pseudogene 也有 `transposable_element_gene`。严格的 TF 调控分析中可能不需要它们；`strict` 模式（regex `^gene$`）会把它们丢掉，universe 从 29824 降到 ~24000。这个决定在本 pipeline 之前就要做。

2. **多 exon 5' UTR 造成的超长启动子。** 在 `utr=Yes` 下观察到最大长度 ~14,800 bp。PMET 的每序列 `topk` 上限（5 hit）能阻止这些超长启动子主导 binomial 阈值，但全局 FIMO 预算（`topn=5000`）是唯一能防止 motif 计数被吹胀的护栏。

3. **`grep -Ff` 过滤用户 gene list。** 用户提供的 cluster 文件从 1660 行 → 1595 行（丢 65 行）。这些是 `universe.txt` 没有的 gene id，**被静默丢弃**；如果下游分析师以为每个输入 gene 都被测过，那就会被惊到。pipeline 不会显式记录这次损失。

4. **不保留中间文件。** `keep_intermediate=false`（默认）下，跑完 BED / FASTA 中间产物就消失了，所以本审计要在沙箱里再 derive 一次。这不是 bug，但 post-hoc 调试会更麻烦。

<a id="cn-7"></a>

## 7. 总结

**整体状态：PASS。** pipeline 03 在 TAIR10 上、用 strand-aware、与 gene body 不重叠、扩展了 5' UTR 的启动子集，产出契约合规的同型 index、结构合规的异型表，以及三张互不相同的 heatmap。所有结构性 invariant（BED 坐标、`−` strand 反向互补、universe ≡ promoter_lengths gene 集、fimohits 数 = motif 数）都成立。

输出可以直接喂给下游 PMET 解读。两条 caveat —— 不在 universe 里的用户 gene id 被静默丢、长 UTR 拉出来的 max 启动子长度 —— 都是观察事项，不是缺陷。
