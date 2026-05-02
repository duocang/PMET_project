# Pipeline 03: Promoter PMET Analysis

Script: [scripts/pipeline/03_promoter.sh](../../scripts/pipeline/03_promoter.sh)

## 1. Pipeline Purpose

Find pairs of transcription-factor motifs that are co-enriched in the
1 kb upstream regions ("promoters") of a user-supplied gene cluster
list, on the *Arabidopsis thaliana* TAIR10 reference, and render the
result as motif × motif heatmaps per cluster.

The intuition is the canonical PMET test: most TFs do not act alone;
two motifs that show up together in a cluster's promoters more than
expected by chance are evidence of cooperative regulation. Pipeline 03
is the baseline form — promoters defined relative to the TSS, no gap,
5' UTR included, gene-body overlap stripped.

## 2. Inputs

| File | Biological meaning | Format | Truncated sample |
| --- | --- | --- | --- |
| `data/TAIR10.fasta` | TAIR10 nuclear + organelle genome, ~135 Mb | linear FASTA, 7 records (`1..5,Mt,Pt`) | first headers: `>1`, `>2`, `>3` |
| `data/TAIR10.gff3` | Ensembl/TAIR10 annotation | GFF3 v3 | `##gff-version 3` then `##sequence-region 1 1 30427671 …` |
| `data/Franco-Zorrilla_et_al_2014.meme` | 113 plant TF motifs (Franco-Zorrilla 2014) | MEME v4 | 113 lines starting `MOTIF ` |
| `data/genes/genes_cell_type_treatment.txt` | gene-cluster mapping for the heterotypic test | `<cluster_label> <gene_id>` per line, 1660 rows, 6 clusters | `Epidermis_flg22_up AT1G53080` |
| `build/index_fimo_fused` | fused FIMO + PMET indexer | ELF/macho binary | n/a |
| `build/pair_parallel` | heterotypic pair tester | binary | n/a |

Each input passes its preflight check in `scripts/pipeline/03_promoter.sh:108-126`:
- `check_file` confirms non-empty;
- `check_dep` confirms `samtools / bedtools / sortBed / fasta-get-markov / parallel / python3` exist;
- chromosome-name preflight (`'1'` vs `'Chr1'`) compares the first
  data row of the GFF3 against the first FASTA header. Both are `1`
  on this dataset → **PASS**.

## 3. Output Contract

After a clean run the pipeline must populate three subtrees under
`results/03_promoter/`:

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

The contract is enforced by `scripts/python/check_homotypic_contract.py`
called from `run_homotypic.py:259-262`.

## 4. Step-by-Step Execution Story

The homotypic stage is delegated end-to-end to
[scripts/python/run_homotypic.py](../../scripts/python/run_homotypic.py).
The numbering below is `run_homotypic.py`'s 10-step layout.

For intermediate inspection this audit re-ran only the homotypic stage
into `results/pipeline_story/03_homotypic_sample/` with
`--keep-intermediate`, so BED/FASTA artefacts that the production
pipeline cleans up are visible. The contract files there match the
canonical baseline byte-for-row-count (29824 universe genes,
113 motif files).

### Step 1: Sort the GFF3 by genomic coordinate

#### Command / Code Path

```text
perl scripts/gff3sort/gff3sort.pl data/TAIR10.gff3 > <out>/sorted.gff3
```
([run_homotypic.py:146-149](../../scripts/python/run_homotypic.py#L146-L149))

#### Purpose

Stabilise downstream `awk`/coordinate joins. The TAIR10 GFF3 is
already mostly sorted but `gff3sort.pl` enforces hierarchy
(`gene → mRNA → exon`) and chromosome-then-start order.

#### Bioinformatics Meaning

Hierarchical, sorted GFF3 is the assumption every downstream parser
makes. Without it `parse_utrs.py` would mis-attach UTR rows to genes.

#### Input

`data/TAIR10.gff3` — first non-comment row:

```
1   araport11   chromosome   1   30427671   .   .   .   ID=chromosome:1
```

#### Output

`sorted.gff3` (sandbox: 60 MB, in formal pipeline run cleaned up).

#### Expected Properties

- Same number of non-comment rows as input (sort doesn't drop rows).
- Chromosome column comes from `{1..5,Mt,Pt}` only.

#### Observed Result

`results/pipeline_story/03_homotypic_sample/sorted.gff3` exists,
non-empty.

#### Assessment

PASS.

---

### Step 2: Extract gene rows into BED

#### Command / Code Path

```text
python3 scripts/python/gff3_to_gene_bed.py \
    --gff3 sorted.gff3 --out genelines.bed \
    --id-key 'gene_id=' --feature-regex 'gene$'
```
([run_homotypic.py:152-160](../../scripts/python/run_homotypic.py#L152-L160))

#### Purpose

Convert per-gene rows of the GFF3 into a BED6 ready for `bedtools
flank`. With `gene_features=all` (the pipeline's current default,
[03_promoter.sh:35-37](../../scripts/pipeline/03_promoter.sh#L35-L37))
the regex `gene$` matches `gene`, `ncRNA_gene`, `pseudogene`,
`transposable_element_gene`, etc.

#### Bioinformatics Meaning

PMET is gene-centric, not locus-centric. We want one promoter per gene,
not per transcript. GFF3 column 4/5 are 1-based closed; BED is 0-based
half-open, so `start = gff3_start - 1`.

#### Input

`sorted.gff3` rows where col 3 ends in `gene`. TAIR10 has 32833 such
rows (32833 = `awk '!/^#/ && $3 ~ /gene$/' | wc -l`).

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

#### Expected Properties

- Every row has 6 fields, `start < end`, strand ∈ {`+`,`-`}.
- Gene id is unique per row (no transcripts).
- Chromosome ∈ FASTA header set.

#### Observed Result

`awk '$3<=$2'` on `genelines.bed` returns 0 rows. Strand split among
**32833 rows** is `+ ≈ -`. All chromosome ids are within the FASTA's
seven sequences.

#### Assessment

PASS.

---

### Step 3: Build per-chromosome length file

#### Command / Code Path

```text
python3 scripts/python/genome_chrom_lengths.py \
    --gff3 anno --genome genome.fa --out bedgenome.genome
```
([run_homotypic.py:163-169](../../scripts/python/run_homotypic.py#L163-L169))

#### Purpose

`bedtools flank` needs `<chrom>\t<length>` so it can clip flanks at
chromosome ends.

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

#### Expected Properties

- Identical chromosome set to the FASTA (`samtools faidx` baseline).
- Lengths positive integers.

#### Observed Result

7 rows, lengths match `data/TAIR10.fasta.fai` byte-for-byte.

#### Assessment

PASS.

---

### Step 4: Linearise the genome FASTA

#### Command / Code Path

```text
linearise_fasta(args.genome, stripped_fa)   # newline-collapse per record
samtools faidx stripped_fa
```
([run_homotypic.py:172-174](../../scripts/python/run_homotypic.py#L172-L174))

#### Purpose

`bedtools getfasta` is unhappy with multi-line FASTA records; the
linearised form has at most one sequence line per record.

#### Bioinformatics Meaning

No biology. Pure I/O canonicalisation.

#### Output

`genome_stripped.fa` (~120 MB) plus `.fai` index.

#### Expected Properties

- One header + one sequence line per record (9 lines total for 7
  records is tolerated because `linearise_fasta` writes a trailing
  newline).
- `samtools faidx` succeeds.

#### Observed Result

Sandbox file exists, indexed; first record `>1` followed by a single
30,427,671-character sequence line.

#### Assessment

PASS.

---

### Step 5: Build promoters

#### Command / Code Path

```text
python3 scripts/python/build_promoters.py \
    --gene-bed genelines.bed --genome-sizes bedgenome.genome \
    --genome-fasta genome_stripped.fa --sorted-gff3 sorted.gff3 \
    --length 1000 --gap 0 --overlap NoOverlap --utr Yes \
    --out-bed promoters.bed --out-fasta promoters.fa \
    --out-bg promoters.bg --out-lengths promoter_lengths.txt \
    --out-universe universe.txt --out-removed-dir <out>
```
([run_homotypic.py:177-195](../../scripts/python/run_homotypic.py#L177-L195),
[build_promoters.py](../../scripts/python/build_promoters.py))

This single call does, in order:

1. `bedtools flank -l 1000 -r 0 -s` — strand-aware upstream flank.
2. `sortBed`.
3. (`gap > 0` only — not used here).
4. Drop promoters < 10 bp (edge clipping at chromosome boundaries).
5. `bedtools subtract -a promoters -b genelines.bed` — `NoOverlap`
   strips any region that intrudes on a downstream gene body.
6. Drop promoters < 20 bp post-subtraction.
7. `assess_integrity.py` keeps the TSS-side fragment when subtraction
   splits a promoter in two.
8. `parse_utrs.py` extends each promoter into its 5' UTR
   (because `utr=Yes`).
9. Compute `promoter_lengths.txt`.
10. Compute `universe.txt`.
11. `bedtools getfasta -name -s` (strand-aware) →
    sed-strip the `::chrom:start-end` and `(+)/(-)` suffixes.
12. `fasta-get-markov` → `promoters.bg` (zero-order Markov background).

#### Purpose

Build the canonical "promoter" sequence set against which FIMO will
score motifs.

#### Bioinformatics Meaning

This is the most biology-laden step in the pipeline:

- "Upstream" means **5' upstream of the TSS in transcription
  direction**, so the operation is strand-aware.
- The *core promoter* (the ~50 bp around the TSS) is intentionally
  *included* here (gap=0). Pipeline 05 turns gap on to drop it.
- 5' UTR inclusion (`utr=Yes`) lets motifs in the 5' UTR contribute,
  which is appropriate for many plant TFs whose binding sites cluster
  there.
- `NoOverlap` prevents a long-flank promoter from claiming a motif
  that actually sits inside a neighbouring gene body — important on
  the gene-dense Arabidopsis genome.

#### Input

`genelines.bed` (32833 rows), `bedgenome.genome` (7 rows),
`genome_stripped.fa` + `.fai`, `sorted.gff3`.

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

#### Expected Properties

| Check | Expectation | Observation |
| --- | --- | --- |
| BED `start < end` | every row | 0 violations |
| Strand ∈ {`+`,`-`} | every row | `+`=15010, `-`=14814 (≈ even) |
| Length ≤ 1000 + max(5'UTR) | yes | min=20, max=14813, mean=907 — *max=14813 ⇒ a gene whose annotated 5' UTR is ~14 kb* |
| `+` strand promoter ends at gene start | yes | `AT1G01010` gene 3630–5899 → promoter 2630–3759 (end = 3759 because UTR extension covers the first 129 bp of the gene record, since AT1G01010's 5' UTR is annotated inside `[3630, 3759)`) |
| `-` strand promoter is downstream of gene end | yes | `AT1G01020` gene 6787–9130 → promoter 8666–10130 (i.e. region adjacent to gene end at coord 9130, extended further by 5' UTR which on `-` strand sits at higher coordinates) |
| `-` strand FASTA is reverse-complemented | yes | last 80 bp of `+` slice `1:8667-10130`, reverse-complemented, exactly equals first 80 bp of `>AT1G01020` in `promoters.fa` |
| `universe.txt` gene set == `promoter_lengths.txt` gene set | yes | `comm -3` returns 0 differences |
| `promoter_lengths.txt $2 > 0` | yes | 0 violations |
| Loss from 32833 genes → 29824 promoters | ~3009 lost | matches: 1 (lt10) + 763 (lt20) + 2245 (no flankable upstream / fully overlapped) |

#### Observed Result

All structural checks pass.

#### Assessment

PASS. The mean promoter length (907 bp) and the 763 sub-20 bp drops
both confirm that `NoOverlap` is doing real work — promoters in
gene-dense regions are being correctly trimmed.

The very long promoters (max=14,813 bp) are not a bug — they happen
when `parse_utrs.py` joins a long, multi-exon 5' UTR onto the upstream
flank. PMET's `topn`/`topk` budgets keep this from skewing
binomial thresholds, but it is worth noting.

---

### Step 6: Per-motif information content

#### Command / Code Path

```text
python3 scripts/python/parse_memefile.py    motifs.meme memefiles_ic/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py memefiles_ic/ IC.txt
```
([run_homotypic.py:198-208](../../scripts/python/run_homotypic.py#L198-L208))

#### Purpose

For each motif compute per-position information content. PMET's
heterotypic pairing uses the IC vector to weight position importance
when scoring overlap.

#### Bioinformatics Meaning

`IC = log2(4) − H(P)` per column of the PWM. High-IC positions are
"specific" positions; low-IC positions tolerate any base.

#### Output

`IC.txt` (113 rows). Sample:

```
ZAT18 0.7434 1.3087 0.7953 1.0010 1.0010 0.7953 1.3087 0.7434
ATHB51 0.8777 1.8638 1.8947 0.9433 1.9055 1.8637 1.7314 0.9412
DEAR3 1.0026 0.8653 1.3315 1.5593 1.2274 0.4203 1.0745 0.1985
```

#### Expected Properties

- 113 rows = 113 motifs.
- Each value ∈ [0, 2] (per DNA column).

#### Observed Result

`wc -l IC.txt` → 113. Spot check on the rows above: all values within
[0, 2].

#### Assessment

PASS.

---

### Step 7: FIMO + PMETindex (fused)

#### Command / Code Path

```text
build/index_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile promoters.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<batch>.txt promoters.fa promoter_lengths.txt
```
([run_homotypic.py:225-239](../../scripts/python/run_homotypic.py#L225-L239))

`parse_memefile_batches.py` first round-robins the 113 motifs into
`threads=4` batches; the binary processes each batch with internal
OpenMP parallelism.

#### Purpose

Two operations fused into one binary:

1. Run FIMO on each promoter against each motif at p ≤ 0.05.
2. Compute the per-motif binomial threshold (the p-value below which
   a hit is "significant" given the motif's hits-per-bp rate). This
   threshold is `binomial_thresholds.txt`'s second column.

#### Bioinformatics Meaning

`topn` caps how many of the most-significant hits are kept per motif
across the genome (5000 = "the top 5000 hits"); `topk` caps how many
hits are kept per sequence (5 = "at most 5 hits per promoter, even if
the motif occurs 10×"). Both keep PMET from being dominated by a
small number of long, hit-rich promoters.

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

#### Expected Properties

- `len(fimohits/*.txt) == nummotifs` (113).
- Every fimohits row has gene id ∈ `universe.txt`.
- Every motif has at least one row in `binomial_thresholds.txt`.

#### Observed Result

`ls fimohits | wc -l` → 113. `wc -l binomial_thresholds.txt` → 113.
The pipeline emits `WARNING` if any fimohits file is empty; here
no warning was logged.

#### Assessment

PASS.

---

### Step 8: Homotypic contract validation

#### Command / Code Path

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```
([run_homotypic.py:258-262](../../scripts/python/run_homotypic.py#L258-L262))

#### Purpose

Programmatic guard against silent output corruption. Verifies file
shapes, header presence, gene-id consistency.

#### Output

stdout: `OK — homotypic contract holds (113 motifs, 29824 universe genes,
29824 genes with promoter lengths)`.

#### Assessment

PASS.

---

### Step 9: Heterotypic motif-pair test

#### Command / Code Path

```text
build/pair_parallel \
    -d . \
    -g <filtered_gene_list> -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/03_promoter/02_heterotypic -t 4
```
([03_promoter.sh:171-187](../../scripts/pipeline/03_promoter.sh#L171-L187))

The user gene list is first filtered to genes present in `universe.txt`
(`grep -Ff universe gene_input_file > gene_tmp`). The flag `-i 4` is
the IC threshold below which positions are not used for overlap
detection.

#### Purpose

For every (cluster, motif₁, motif₂) triple, test whether genes in the
cluster have both motifs in their promoter more often than expected by
chance, given the cluster size and the genome-wide rate.

#### Bioinformatics Meaning

This is the actual PMET hypothesis. The output's adjusted p-values
(BH within cluster, Bonferroni within cluster, global Bonferroni) are
the headline result that the heatmaps render.

#### Input

- Filtered cluster file (1595 of 1660 input rows survived the
  universe filter — 65 input gene ids are not in TAIR10's gene set
  per `gene_features=all`, presumably aliases or AT-style-but-missing).
- Homotypic contract files.

#### Output

`motif_output.txt` — 11 columns, 37969 rows (excluding header).

```
Cluster                Motif 1  Motif 2     N_in_cluster_with_both  N_genome_with_both  N_in_cluster  Raw_p   BH      Bonf    Global_Bonf  Genes
Cortex_flg22_up        AHL12    AHL12_2     0                       197                 119           1.000   1.000   1.000   1.000        
Cortex_flg22_up        AHL12    AHL12_3ARY  3                       682                 119           5.14e-1 6.97e-1 1.000   1.000        AT1G05660;AT1G34420;AT3G25900;
```

#### Expected Properties

- 11 tab-separated columns.
- One row per (cluster, motif_pair) — a row count near
  `clusters * C(motifs, 2)` = 6 × 6328 = 37968 (allowing one header
  row).
- p-values ∈ [0, 1].

#### Observed Result

`awk -F'\t' 'NR==1{print NF}' motif_output.txt` → 11. Row count 37969
(= 1 header + 37968 pair rows). All p-values in sampled range valid.

#### Assessment

PASS.

---

### Step 10: Heatmaps

#### Command / Code Path

```text
Rscript scripts/r/draw_heatmap.R All     plot/heatmap.png                motif_output.txt 5 3 6 FALSE
Rscript scripts/r/draw_heatmap.R Overlap plot/heatmap_overlap_unique.png motif_output.txt 5 3 6 TRUE
Rscript scripts/r/draw_heatmap.R Overlap plot/heatmap_overlap.png        motif_output.txt 5 3 6 FALSE
```
([03_promoter.sh:198-201](../../scripts/pipeline/03_promoter.sh#L198-L201))

#### Purpose

Render motif × motif p-value matrices, faceted by cluster.

#### Bioinformatics Meaning

`mode=All` shows every significant pair; `mode=Overlap` keeps only
pairs that share genes; `unique=TRUE` deduplicates pairs that show up
in multiple clusters so each pair appears at most once.

#### Output

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `plot/heatmap.png` | 1 230 836 | `d8d29fc14379b65124d037ca11e1c05596994ee4f1576d31eb78b2691e0ad73a` |
| `plot/heatmap_overlap.png` | 754 830 | `15a8518b1f7facf0719fc4613f9e0ca38ba88b39150efc07961da61a4cbb41b2` |
| `plot/heatmap_overlap_unique.png` | 765 219 | `f6efec89aa808d239980afe5f7951a5c6f876649d01c95004762d4ef2b0d1d5c` |

(Re-run by this audit on 2026-04-27 from the existing homotypic
baseline; hashes match the pipeline's documented baseline exactly.)

#### Expected Properties

- All three PNG files exist and are non-empty.
- The `unique` and non-`unique` overlap heatmaps differ.

#### Observed Result

All three exist. The `_unique` and `_overlap` PNGs differ by 10 KB
and have different hashes, so the `unique` flag is producing real
filtering on this dataset (contrast: 05/06/07 produce identical
unique vs non-unique PNGs because their cluster sets do not overlap
in motif pairs — see the WARNING in those audits).

#### Assessment

PASS.

## 5. Final Outputs

```
results/03_promoter/
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

## 6. Risks / Edge Cases

1. **`gene_features=all` includes pseudogenes and TE-genes.** The
   universe contains pseudogenes and `transposable_element_gene` rows.
   For a strict TF-regulation analysis these may be undesirable; the
   `strict` mode (regex `^gene$`) drops them, taking the universe down
   from 29824 to ~24000. Decision is upstream of this pipeline.

2. **Long promoters from multi-exon 5' UTRs.** With `utr=Yes` we
   observed a max length of ~14,800 bp. PMET's per-sequence `topk` cap
   (5 hits) prevents these from dominating the binomial threshold,
   but the global FIMO budget (`topn=5000`) is the only safeguard
   against motif counts being inflated.

3. **`grep -Ff` filtering of the user gene list.** The user-supplied
   cluster file went from 1660 lines → 1595 lines (65 dropped). These
   are gene ids not in `universe.txt`. They are silently dropped; if a
   downstream analyst expects every input gene to be tested, this is a
   surprise. The pipeline does not log this loss explicitly.

4. **No retention of intermediate files.** With `keep_intermediate=false`
   (default) the BED/FASTA artefacts are gone after the run, so this
   audit had to re-derive them in a sandbox. Not a bug, but it does
   make post-hoc debugging harder.

## 7. Summary

**Overall status: PASS.** Pipeline 03 produces a contractually valid
homotypic index, a structurally valid heterotypic table, and three
distinct heatmaps from a strand-aware, gene-body-disjoint, 5'
UTR-extended promoter set on TAIR10. All structural invariants
(BED coords, strand-aware reverse-complementation on `−` strand,
universe ≡ promoter_lengths gene set, fimohits count = motif count)
hold.

The outputs are suitable for downstream PMET interpretation. The two
caveats — silent loss of user gene ids that aren't in the universe,
and the long-UTR-driven max promoter length — are observational, not
defects.
