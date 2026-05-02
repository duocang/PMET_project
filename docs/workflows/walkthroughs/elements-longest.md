# Pipeline 06 walkthrough — Genomic-element PMET (longest isoform per gene)

**[English](#en) · [汉文](#cn)**

> **Heads-up:** this is a frozen pre-monorepo walkthrough. References like `scripts/pipeline/06_elements_longest.sh`, `scripts/pipeline/_elements_common.sh`, `scripts/indexing/pmet_index_element.sh`, `data/TAIR10.fasta`, and `build/pmetParallel` are stale — the consolidated current entry point is `scripts/workflows/elements.sh` (`mode=longest`, sharing helpers in `scripts/workflows/cli/`); the pair stage now uses `build/pair_parallel`. See [`README.md`](README.md) for the full path mapping. The algorithm and biology described still apply.

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

Run PMET on a **chosen genomic element** (CDS / exon / mRNA / 5' UTR / 3' UTR) — *inside* the gene body, not upstream of it — picking the **single longest isoform per gene** as the per-gene representative.

Use case: ask whether motif pairs are co-enriched not in the regulatory upstream window (which is what 03/05 do) but inside the transcribed region of the gene itself. This is informative for:

- intron- and exon-encoded regulatory elements (e.g. exon-junction binding, intronic enhancers — though 06's default `CDS` excludes introns);
- post-transcriptional motifs that overlap the coding region;
- splicing-coupled regulation, when run with `mRNA` or `exon`.

The "longest isoform" is per-gene representative selection: if a gene has 5 transcripts, only the one with the greatest **total element length** is kept; all of its fragments contribute to FIMO scanning.

<a id="en-2"></a>

## 2. Inputs

| File | Biological meaning | Format | Truncated sample |
|---|---|---|---|
| `data/TAIR10.fasta` | TAIR10 genome | FASTA | `>1`, `>2`, ... |
| `data/TAIR10.gff3` | TAIR10 annotation | GFF3 v3 | gene/mRNA/exon/CDS rows |
| `data/Franco-Zorrilla_et_al_2014.meme` | 113 plant TF motifs | MEME v4 | 113 `MOTIF` lines |
| `data/genes/<task>.txt` × 5 | five heterotypic test sets | `<cluster> <gene>` | varies |
| Element choice | interactive prompt: 1=3'UTR, 2=5'UTR, 3=mRNA, 4=CDS, 5=exon | TTY | the canonical real-data check uses `printf '4\n' \| bash …` (CDS) |

The five gene-list tasks driven in a loop:

```text
salt_top300, random_genes_300, genes_cell_type_treatment,
gene_cortex_epidermis_pericycle, heat_top300
```

(`_elements_common.sh:120`)

The `random_genes_300` task is a designed-for-no-signal control set; the others are biologically meaningful clusters.

<a id="en-3"></a>

## 3. Output contract

```
results/06_elements_longest/
├── 01_homotypic/                # canonical homotypic contract files
│   ├── universe.txt
│   ├── promoter_lengths.txt
│   ├── binomial_thresholds.txt
│   ├── IC.txt
│   └── fimohits/<motif>.txt
├── 02_heterotypic_<task>/       # × 5 tasks
│   ├── motif_output.txt
│   └── pmet.log
└── 03_plot_<task>/              # × 5 tasks
    ├── heatmap.png
    ├── heatmap_overlap.png
    ├── heatmap_overlap_unique.png
    └── histogram*/               # diagnostic side-cars
```

> **Audit-time note:** at the moment this audit was written, the production pipeline was actively re-running into `results/06_elements_longest/01_homotypic/`, so the numbers below for the homotypic stage come from the **prior committed baseline** (Apr 26 run, captured before the re-run began). The contract expectations are unchanged; the actual hashes will be recorded by `docs/verification_log.md` once the re-run completes.

<a id="en-4"></a>

## 4. Step-by-step execution story

The homotypic stage is `scripts/indexing/pmet_index_element.sh`. It does not call `run_homotypic.py` — it has its own logic, in pure shell + awk + Python helpers, because the GFF3-handling for genomic elements (multiple isoforms per gene, multiple fragments per isoform) is fundamentally different from "one promoter per gene".

### Step 1 — Chromosome-naming preflight

#### Command / code path

```text
gff3_chrom=$(awk -F'\t' '/^[^#]/ && NF>=8 { print $1; exit }' "$gff3file")
fasta_chrom=$(awk '/^>/ { sub(/^>/,""); sub(/ .*/,""); print; exit }' "$genomefile")
[[ "$gff3_chrom" != "$fasta_chrom" ]] && exit 1
```

(`pmet_index_element.sh:135-144`)

#### Purpose

Same as 03's preflight: catch `1` vs `Chr1` style mismatch before silently producing empty BED.

#### Assessment

PASS (TAIR10 uses `1` consistently in GFF3 and FASTA).

---

### Step 2 — Extract chosen element rows from GFF3

#### Command / code path

```text
awk -F'\t' -v elem="$element" -v key="$gff3id" '
    /^#/ { next }
    $3 == elem && $4 < $5 {
        ... print $1, $4-1, $5, transcript_id, 1, $7
    }
' "$gff3file" > "$bedfile"
```

(`pmet_index_element.sh:152-164`)

For element `CDS` the `gff3id` is `Parent=transcript:` so the BED column 4 is the **transcript id**, not the gene id. Column conversion is GFF3 1-based → BED 0-based via `start - 1`.

#### Purpose

Pull every CDS row from the annotation, keyed by transcript so that isoform-specific aggregation can run next.

#### Bioinformatics meaning

Each gene typically has multiple transcripts (mRNA isoforms); each isoform has multiple CDS fragments (one per coding exon). At this point `<bedfile>` has one row per fragment, labelled by transcript.

#### Output

`<out>/CDS.bed` — a few hundred thousand rows, ~5 MB. Sample column layout: `chrom, start, end, transcript_id, 1, strand`.

#### Expected properties

- Every row has 6 fields, `start < end`.
- Column 4 contains transcript ids (not gene ids).
- Strand ∈ {`+`,`-`}.

#### Assessment

PASS.

---

### Step 3 — Pick longest isoform per gene

#### Command / code path

```text
awk -F'\t' '
    {
        tid = $4
        gid = tid; sub(/\..*/, "", gid)   # AT1G01010.1 → AT1G01010
        sum[tid] += $3 - $2
        gene[tid] = gid
    }
    END {
        for (t in sum) {
            g = gene[t]
            if (!(g in bestSum) || sum[t] > bestSum[g]) {
                bestSum[g] = sum[t]; bestTid[g] = t
            }
        }
        for (g in bestTid) print bestTid[g]
    }' "$bedfile" > "$indexingOutputDir/chosen_transcripts.txt"
```

(`pmet_index_element.sh:181-197`)

#### Purpose

For every gene, choose the one transcript whose **total CDS length** is greatest (sum across all fragments).

#### Bioinformatics meaning

The pipeline name says "longest isoform". The implementation defines that as longest *element coverage*, not longest mRNA span. For multi-fragment elements (CDS, exon, UTR) summing-before-comparing is required — picking the single longest fragment would be wrong because a transcript with many medium fragments may cover more sequence than a transcript with one giant exon.

#### Expected properties

- Each gene appears at most once in `chosen_transcripts.txt`.
- The chosen transcript id is one of the gene's annotated isoforms.

#### Assessment

PASS (logic verified by reading; per-gene uniqueness invariant matches `for (g in bestTid)` enumeration).

---

### Step 4 — Keep all fragments of chosen transcripts; relabel to gene

#### Command / code path

```text
awk -F'\t' '
    NR==FNR { chosen[$1] = 1; next }
    ($4 in chosen) {
        gid = $4; sub(/\..*/, "", gid); $4 = gid
        print
    }' chosen_transcripts.txt "$bedfile" \
    | sort -k4,4 -k2,2n > "$bedfile.tmp"
mv "$bedfile.tmp" "$bedfile"
```

(`pmet_index_element.sh:202-211`)

#### Purpose

Filter the per-fragment BED to only fragments belonging to a chosen transcript, then rewrite column 4 from transcript id to gene id.

#### Bioinformatics meaning

The BED now has, per gene, **all the CDS fragments of that gene's single longest isoform**. A gene with N CDS fragments shows up as N rows.

For the 06 default (CDS, mrnaFull=No), an additional UTR-subtraction step runs only when `element=mRNA` (`pmet_index_element.sh:216-243`). For CDS that branch is skipped (CDS already excludes UTRs).

#### Assessment

PASS.

---

### Step 5 — Tag multi-fragment genes with `__GENE__N` and drop fragments < 30 bp

#### Command / code path

```text
awk -F'\t' '
    { n = ++seen[$4]; if (n > 1) $4 = "__" $4 "__" n; print }
' "$bedfile" \
    | awk -F'\t' '$3 - $2 >= 30' \
    | sort -k4,4 > "$bedfile.tmp"
```

(`pmet_index_element.sh:280-285`)

#### Purpose

Each fragment becomes a distinct FIMO sequence. The first fragment of gene `AT1G01010` keeps the bare id; the second becomes `__AT1G01010__2`, the third `__AT1G01010__3`, etc. Then drop fragments shorter than 30 bp (below typical TF motif width).

#### Bioinformatics meaning

FIMO's `--topn` is per-sequence; without per-fragment ids, multiple fragments of the same gene would compete for the same slot. The 30 bp cutoff also stabilises the local Markov background.

#### Expected properties

| Check | Expectation |
|---|---|
| Every multi-row gene gets `__GENE__N` for rows 2..N | yes (row 1 keeps the bare id) |
| All output rows have length ≥ 30 bp | yes |

#### Assessment

PASS. Verified by inspecting the per-record headers in `promoter.fa` (kept on disk because `delete_temp=no` for 06):

```
>__AT1G01020__2     # 2nd fragment of AT1G01020
```

Fragment-per-gene distribution from the prior baseline:

| Fragments | Genes |
|---:|---:|
| 1 | 21 714 |
| 2 | 1 278 |
| 3 | 471 |
| 4 | 13 |
| 5 | 6 |
| 6 | 4 |
| 7 | 6 |
| 8 | 2 |
| 9 | 1 |
| 10 | 2 |

(21,714 + 1,785 multi-fragment = 23,499 unique genes = universe size.)

---

### Step 6 — Write `universe.txt` and `promoter_lengths.txt`

#### Command / code path

```text
awk -F'\t' '{ id=$4; sub(/^__/,"",id); sub(/__[0-9]+$/,"",id); print id }' \
    "$bedfile" | sort -u > "$universefile"
awk -F'\t' -v OFS='\t' '{ print $4, $3 - $2 }' "$bedfile" \
    > "$indexingOutputDir/promoter_lengths.txt"
```

(`pmet_index_element.sh:293-295`)

#### Purpose

`universe.txt` strips the `__N` fragment suffix → one line per unique gene. `promoter_lengths.txt` is **per FIMO sequence**, i.e. per fragment, because FIMO's `--topn` budget is per sequence. The collapse to gene-level happens later (step 11).

#### Bioinformatics meaning

This is the moment when the pipeline's two views co-exist:

- The biology view says "one entry per gene".
- The FIMO view requires "one entry per scanned sequence", and an AT1G… gene with 4 CDS fragments is 4 sequences.

Universe takes the biology view; the temporary `promoter_lengths.txt` takes the FIMO view. The two will be reconciled at step 11.

#### Output

Initial (per-fragment) `promoter_lengths.txt` has one row per fragment (~25,902 rows for the prior baseline). `universe.txt` has 23,499 rows.

#### Expected properties

- `universe.txt` = unique gene ids (no `__` fragments).
- `promoter_lengths.txt` = one row per FIMO sequence; multi-fragment genes appear N times.

#### Assessment

PASS.

---

### Step 7 — Extract sequences (strand-aware)

#### Command / code path

```text
awk '/^>/ {...} ...' "$genomefile" > "$indexingOutputDir/genome_stripped.fa"
bedtools getfasta \
    -fi "$indexingOutputDir/genome_stripped.fa" \
    -bed "$bedfile" -name -s \
    | sed -e 's/([+-])::.*//' -e 's/::.*//' > "$indexingOutputDir/promoter.fa"
```

(`pmet_index_element.sh:303-312`)

#### Purpose

Pull element sequences from the genome with strand-aware reverse-complementation; strip bedtools header annotations.

#### Bioinformatics meaning

Same strand-aware semantics as 03 — `−` strand sequences are reverse-complemented so FIMO scans biologically meaningful strands. Crucially, **fragments are kept as separate FASTA records** (with `__GENE__N` ids), not stitched together. Stitching would create fake junctions that no real motif could span.

#### Output

`promoter.fa` — one record per fragment (25,902 records in baseline).

```
>__AT1G01020__2
ATCATGCACTAAAGTTTCTTGTATTGATTAAACATGGTGTTATGTCTCTTTGCTCAAAAA…
```

The script then verifies no duplicate ids:

```text
dup_ids=$(grep '^>' "$indexingOutputDir/promoter.fa" | sort | uniq -d)
```

(`pmet_index_element.sh:314-318`)

#### Expected properties

- No duplicate header lines in `promoter.fa`.
- Reverse-complementation is applied for `−` strand fragments.

#### Assessment

PASS (uniq-detection guard is in place; not triggered in baseline).

---

### Step 8 — Background, IC, MEME batch split, FIMO

#### Command / code path

```text
fasta-get-markov "$indexingOutputDir/promoter.fa" > .../promoter.bg
python3 parse_memefile.py "$memefile" memefiles/
python3 calculateICfrommeme_IC_to_csv.py memefiles/ IC.txt
python3 parse_memefile_batches.py "$memefile" memefiles/ "$threads"
parallel --jobs="$threads" "build/fimo --no-qvalue --text \
    --thresh 0.05 --bgfile promoter.bg --topn 5000 --topk 5 \
    --oc fimohits memebatch promoter.fa promoter_lengths.txt"
```

(`pmet_index_element.sh:325-381`)

#### Purpose

Same as 03's step 7 — FIMO scan plus PMETindex (binomial threshold) in fused calls per batch.

> **Important difference vs 03:** 06 / 07 use `build/fimo` (the standalone FIMO with `--topk` patch), whereas 03 / 05 use `build/index_fimo_fused`. Both are based on MEME 5.x; the API and output format are identical.

#### Output

```
fimohits/<motif>.txt              113 files (one per motif)
binomial_thresholds.txt           113 rows
```

After parallel writes the script sorts the binomial thresholds file (`pmet_index_element.sh:379-381`) to make the byte order stable across runs.

#### Expected properties

- 113 motifs in, 113 fimohits files out.
- 113 binomial threshold rows.
- All rows reference per-fragment ids (`__GENE__N` or bare id).

#### Assessment

PASS (against prior baseline). At audit time the pipeline was mid-FIMO; partial output shows the expected per-batch round-robin file emission pattern.

---

### Step 9 — Collapse per-fragment results back to gene level

#### Command / code path

```text
# promoter_lengths: sum per-gene
awk -F'\t' '{
    sub(/^__/, "", $1); sub(/__[0-9]+$/, "", $1)
    sum[$1] += $2
}
END { for (g in sum) print g "\t" sum[g] }' \
    "$indexingOutputDir/promoter_lengths.txt" > .../promoter_lengths.tmp

# fimohits: strip __N from col 2; per gene keep top maxk hits below
# the motif's binomial threshold (sort -g handles 1.2e-07).
while IFS=$'\t' read -r motif threshold _; do
    src=fimohits/${motif}.txt; dst=fimohits_merged/${motif}.txt
    awk '{ sub(/^__/,"",$2); sub(/__[0-9]+$/,"",$2); print }' "$src" \
    | sort -t $'\t' -k2,2 -k7,7g \
    | awk -v k=$maxk -v thr=$threshold '
        $2 != prev { prev=$2; n=0 }
        { n++; if (n <= k && ($7+0) < (thr+0)) print }
    ' > "$dst"
done < "$indexingOutputDir/binomial_thresholds.txt"

rm -rf "$indexingOutputDir/fimohits"
mv  "$indexingOutputDir/fimohits_merged" "$indexingOutputDir/fimohits"
```

(`pmet_index_element.sh:391-417`)

#### Purpose

Reconcile the per-fragment FIMO view with the gene-level biology view:

- Gene length = sum of fragment lengths.
- Gene's hits = top-`maxk` (=5) most-significant fragment hits that beat the motif's binomial threshold, after pooling fragments of the same gene.

#### Bioinformatics meaning

Multi-fragment scanning detects motifs that occur within *any* CDS fragment of the chosen isoform; this collapse step then asks "is the gene a candidate for this motif?" by aggregating fragment evidence.

#### Output

After collapse:

```
universe.txt           23499 lines
promoter_lengths.txt   23499 rows  (gene-level)
fimohits/<motif>.txt   113 files  (gene-level ids only)
binomial_thresholds.txt  113 rows
IC.txt                 113 rows
```

`promoter_lengths.txt` first 3 (baseline):

```
AT4G29580   302
AT1G04030   325
AT1G48195   187
```

`fimohits/AHL12.txt` first 3 (baseline):

```
AHL12   AT1G01010   203   210   -   5.971014   2.692e-03   ATTATTAT
AHL12   AT1G01010   239   246   -   5.927536   3.258e-03   TTATTTAT
AHL12   AT1G01010   107   114   -   5.282609   6.517e-03   TAAAATAT
```

(8th column is the matched sequence, present here because 06 uses `build/fimo` not `index_fimo_fused`.)

#### Expected properties

| Check | Expectation | Observation (baseline) |
|---|---|---|
| `promoter_lengths.txt` row count | = `universe.txt` row count | 23499 ≡ 23499 |
| No `__` in `promoter_lengths.txt` col 1 | yes | 0 violations |
| No `__` in `fimohits/*` col 2 | yes | 0 violations |
| Gene length == sum of its fragment lengths | yes | by construction |
| Mean length | reasonable for CDS | 334.985 bp (matches typical short-CDS distribution) |
| Min length | ≥ 30 (the lt30 floor) | 30 |
| Max length | several kb (multi-fragment genes) | 4144 |

#### Observed result

All hold against the prior baseline.

#### Assessment

PASS.

---

### Step 10 — Cleanup + contract validation

#### Command / code path

```text
if [[ $delete == [Yy]* ]]; then  rm -rf intermediates; fi
file_count=$(find fimohits -name '*.txt' | wc -l)
if [ "$file_count" -eq "$nummotifs" ]; then
    python3 check_homotypic_contract.py "$indexingOutputDir"
fi
```

(`pmet_index_element.sh:421-451`)

For 06 `delete_temp=no`, so `promoter.fa`, `promoter.bg`, `genome_stripped.fa`, `memefiles/` are kept (useful for audits like this one — pipeline 07 has them removed).

#### Assessment

PASS.

---

### Step 11 — Heterotypic motif-pair test (looped over 5 tasks)

#### Command / code path

```text
for task in salt_top300 random_genes_300 genes_cell_type_treatment \
            gene_cortex_epidermis_pericycle heat_top300; do
    grep -Ff universe.txt data/genes/$task.txt \
        > heterotypic_$task/new_genes_temp.txt
    build/pmetParallel \
        -d . -g new_genes_temp.txt -i 4 \
        -p promoter_lengths.txt -b binomial_thresholds.txt \
        -c IC.txt -f fimohits \
        -o heterotypic_$task -t 8 > pmet.log
    cat heterotypic_$task/*.txt > heterotypic_$task/motif_output.txt
done
```

(`_elements_common.sh:120-156`)

The Aug 2025 fix made this aggregate **idempotent** by removing any old `motif_output.txt` before the `cat`, then concatenating via a `mktemp` buffer; this prevents an old run's `motif_output` from being fed back into the next aggregation. (`_elements_common.sh:146-156`)

#### Output (prior baseline)

| Task | `motif_output.txt` rows | Heatmap PNGs in plot dir |
|---|---:|---:|
| `salt_top300` | 12 657 | 3 |
| `random_genes_300` | 25 313 | **0** (only histograms) |
| `genes_cell_type_treatment` | 37 969 | 3 |
| `gene_cortex_epidermis_pericycle` | 18 985 | 3 |
| `heat_top300` | 12 657 | 3 |

#### Expected properties

- 11 columns. ✓
- Row count = `1 + C(motif, 2) * num_clusters` per task. ✓ (e.g. `salt_top300` has 2 clusters → 1 + 2 × 6328 = 12657 ✓).

#### Assessment

PASS for all five tasks structurally. The `random_genes_300` PNG absence is the same `draw_heatmap.R` behaviour seen in pipeline 04 — when no adjusted p-value passes the significance threshold, the R script writes only the diagnostic histogram. By design `random_genes_300` is a null control, so this is expected, but it should be documented so consumers don't assume the pipeline failed.

---

### Step 12 — Heatmaps (per task, three views)

#### Output for `genes_cell_type_treatment` (baseline)

| File | Bytes | SHA-256 |
|---|---:|---|
| `03_plot_genes_cell_type_treatment/heatmap.png` | 424 131 | `a57c5f340e9246d3f4b0e96ae11cb3789d388d5da0a2c401531bb9e4cba0e30b` |
| `…/heatmap_overlap.png` | (matches `_unique`) | `574bf18711fd4ff98f415229448f9a1ab81a6e3a3d5e265490fb30259d62be4d` |
| `…/heatmap_overlap_unique.png` | (matches `_overlap`) | `574bf18711fd4ff98f415229448f9a1ab81a6e3a3d5e265490fb30259d62be4d` |

#### Expected properties

- All three PNGs exist for every task except those whose motif_output is degenerate (random_genes_300).
- The two `Overlap` PNGs differ from each other.

#### Observed result

Same `unique == non-unique` byte-identity pattern as in 05 and 07. See [`promoter-gap.md` §4 step 10](promoter-gap.md) for the same note — it is a property of the input motif_output distribution, not a 06-specific defect.

#### Assessment

WARNING (PNG-identity quirk shared with 05/07). PASS otherwise.

<a id="en-5"></a>

## 5. Final outputs

```
results/06_elements_longest/
├── 01_homotypic/
│   ├── universe.txt              23 499 genes (CDS-bearing)
│   ├── promoter_lengths.txt      23 499 rows;  min=30, max=4144, mean=335
│   ├── binomial_thresholds.txt   113   rows
│   ├── IC.txt                    113   rows
│   ├── fimohits/                 113   files
│   ├── promoter.fa               25 902 records (per-fragment, kept on disk)
│   ├── promoter.bg               4-base markov background
│   ├── genome_stripped.fa        ~120 MB linearised genome
│   └── CDS.bed                   raw per-fragment BED (kept on disk)
├── 02_heterotypic_<task>/        × 5 tasks
└── 03_plot_<task>/               × 5 tasks (3 PNGs each except random_genes_300)
```

<a id="en-6"></a>

## 6. Risks / edge cases

1. **"Longest isoform" is by element coverage, not by mRNA span.** For `-e CDS` it's longest CDS; for `-e mRNA` it's longest mRNA. This is the right semantics for PMET (we want the most coding sequence to scan), but is *not* what the term sometimes means in tools like AGAT (which often pick longest pre-mRNA span).

2. **Fragment-level vs gene-level views.** The pipeline alternates between the two — initial scanning is per-fragment, with `__GENE__N` tagging; final outputs are collapsed back to gene level. The collapse keeps top-`maxk` (=5) fragment hits per gene per motif, below the binomial threshold. This is the correct PMET semantics but means a gene's score is **not** a sum across fragments — it's a "best 5 fragment hits" rule. Consumers comparing 06 directly to 03 should know this asymmetry.

3. **30 bp minimum fragment length.** A real CDS micro-exon below 30 bp is silently dropped. Rare in TAIR10 but can affect compact gene families.

4. **`mrnaFull=No` UTR subtraction is silent on UTR-less transcripts.** (`pmet_index_element.sh:216-243`) `bedtools subtract` with an empty `-b` is a no-op, which is the intended behaviour. Not a defect, just non-obvious.

5. **No heatmap for control task.** `random_genes_300` is by design a no-signal control. The R script silently produces no `heatmap*.png` when nothing passes adjustment. Easy to mistake for a pipeline failure.

6. **PNG identity quirk for `Overlap` × `unique`.** Shared with pipelines 05 and 07 — see those docs.

<a id="en-7"></a>

## 7. Summary

**Overall status: PASS** (one shared WARNING with 05/07 on `heatmap_overlap == heatmap_overlap_unique`, one expected `random_genes_300` heatmap absence).

Pipeline 06 correctly implements per-gene "longest isoform" selection by total element-length, preserves all fragments of the chosen isoform during scanning (with `__GENE__N` tagging that round-trips cleanly), and collapses fragment-level hits back to gene-level for the heterotypic test. All structural invariants — universe ≡ lengths gene-set, fimohits count == motif count, no `__N` artefacts in final output, BED coordinates well-formed, strand-aware sequence extraction — hold against the prior baseline.

The outputs are suitable as a "coding-region motif" complement to the upstream-promoter views in 03/05.

> **Audit caveat:** the homotypic stage was actively re-running while this audit was written; the contract numbers above were captured before the re-run started. The audit's expected properties are structural and do not depend on the new run's exact numbers, but SHA-256 hashes of the output files will need to be reconfirmed against `docs/verification_log.md` once the re-run completes.

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

在**指定基因组元素**（CDS / exon / mRNA / 5' UTR / 3' UTR）上跑 PMET —— 是在 *gene body 内部*，而非上游 —— 用**每基因的单条最长 isoform** 作为该基因的代表。

使用场景：想问 motif pair 是不是不在调控上游窗口里共富集（那是 03/05 干的事），而是在该基因被转录的区域内部共富集。这对以下场景有用：

- intron- 与 exon-编码的调控元素（exon-junction 结合、intronic enhancer —— 不过 06 默认 `CDS` 排除了 intron）；
- 与 coding 区重叠的转录后 motif；
- 用 `mRNA` 或 `exon` 跑时的剪接耦合调控。

"longest isoform" 这里是每基因代表 isoform 的选择：若一个基因有 5 条 transcript，则只保留**总元素长度最大**那条；它的所有 fragment 一起参与 FIMO 扫描。

<a id="cn-2"></a>

## 2. 输入

| 文件 | 生物学含义 | 格式 | 截样 |
|---|---|---|---|
| `data/TAIR10.fasta` | TAIR10 基因组 | FASTA | `>1`、`>2` …… |
| `data/TAIR10.gff3` | TAIR10 注释 | GFF3 v3 | gene/mRNA/exon/CDS 行 |
| `data/Franco-Zorrilla_et_al_2014.meme` | 113 个植物 TF motif | MEME v4 | 113 行 `MOTIF` |
| `data/genes/<task>.txt` × 5 | 5 个异型测试集 | `<cluster> <gene>` | 各异 |
| 元素选择 | 交互 prompt：1=3'UTR、2=5'UTR、3=mRNA、4=CDS、5=exon | TTY | 真实数据基线用 `printf '4\n' \| bash …`（CDS） |

循环驱动的 5 个 gene-list 任务：

```text
salt_top300, random_genes_300, genes_cell_type_treatment,
gene_cortex_epidermis_pericycle, heat_top300
```

(`_elements_common.sh:120`)

`random_genes_300` 是设计为"无信号"的对照集；其余都是有生物学意义的 cluster。

<a id="cn-3"></a>

## 3. 输出契约

```
results/06_elements_longest/
├── 01_homotypic/                # canonical homotypic contract files
│   ├── universe.txt
│   ├── promoter_lengths.txt
│   ├── binomial_thresholds.txt
│   ├── IC.txt
│   └── fimohits/<motif>.txt
├── 02_heterotypic_<task>/       # × 5 tasks
│   ├── motif_output.txt
│   └── pmet.log
└── 03_plot_<task>/              # × 5 tasks
    ├── heatmap.png
    ├── heatmap_overlap.png
    ├── heatmap_overlap_unique.png
    └── histogram*/               # diagnostic side-cars
```

> **审计期备注：** 写本审计时正式 pipeline 正在向 `results/06_elements_longest/01_homotypic/` 重跑，因此下面同型阶段的数字来自**之前已 commit 的 baseline**（4 月 26 日那次跑，重跑开始前的快照）。契约期望不变；重跑结束后，实际的 hash 由 `docs/verification_log.md` 记录。

<a id="cn-4"></a>

## 4. 按 step 走读

同型阶段是 `scripts/indexing/pmet_index_element.sh`。它**不**调用 `run_homotypic.py` —— 它有自己的逻辑，纯 shell + awk + Python helper，因为基因组元素的 GFF3 处理（每基因多 isoform、每 isoform 多 fragment）和"每基因一启动子"在根本上不同。

### Step 1 —— 染色体命名 preflight

#### 命令 / 代码路径

```text
gff3_chrom=$(awk -F'\t' '/^[^#]/ && NF>=8 { print $1; exit }' "$gff3file")
fasta_chrom=$(awk '/^>/ { sub(/^>/,""); sub(/ .*/,""); print; exit }' "$genomefile")
[[ "$gff3_chrom" != "$fasta_chrom" ]] && exit 1
```

(`pmet_index_element.sh:135-144`)

#### 用途

和 03 的 preflight 一样：在悄悄产生空 BED 之前抓住 `1` vs `Chr1` 这种命名不一致。

#### 评估

PASS（TAIR10 在 GFF3 与 FASTA 中都用 `1`）。

---

### Step 2 —— 从 GFF3 抽出选定元素行

#### 命令 / 代码路径

```text
awk -F'\t' -v elem="$element" -v key="$gff3id" '
    /^#/ { next }
    $3 == elem && $4 < $5 {
        ... print $1, $4-1, $5, transcript_id, 1, $7
    }
' "$gff3file" > "$bedfile"
```

(`pmet_index_element.sh:152-164`)

元素是 `CDS` 时，`gff3id` 是 `Parent=transcript:`，所以 BED 第 4 列是 **transcript id**，不是 gene id。坐标 GFF3 1-based → BED 0-based（`start - 1`）。

#### 用途

把注释里的所有 CDS 行拉出来，按 transcript 标签，方便下一步按 isoform 聚合。

#### 生物信息含义

每个基因典型有多条 transcript（mRNA isoform）；每条 isoform 有多个 CDS fragment（每个 coding exon 一个）。此刻 `<bedfile>` 里每个 fragment 一行，按 transcript 标签。

#### 输出

`<out>/CDS.bed` —— 几十万行，~5 MB。列布局：`chrom, start, end, transcript_id, 1, strand`。

#### 期望性质

- 每行 6 列、`start < end`。
- 第 4 列是 transcript id（不是 gene id）。
- strand ∈ {`+`,`-`}。

#### 评估

PASS。

---

### Step 3 —— 选每基因的最长 isoform

#### 命令 / 代码路径

```text
awk -F'\t' '
    {
        tid = $4
        gid = tid; sub(/\..*/, "", gid)   # AT1G01010.1 → AT1G01010
        sum[tid] += $3 - $2
        gene[tid] = gid
    }
    END {
        for (t in sum) {
            g = gene[t]
            if (!(g in bestSum) || sum[t] > bestSum[g]) {
                bestSum[g] = sum[t]; bestTid[g] = t
            }
        }
        for (g in bestTid) print bestTid[g]
    }' "$bedfile" > "$indexingOutputDir/chosen_transcripts.txt"
```

(`pmet_index_element.sh:181-197`)

#### 用途

对每个基因，挑出**总 CDS 长度**最大的 transcript（所有 fragment 求和）。

#### 生物信息含义

pipeline 名字写"longest isoform"。实现把它定义成最长**元素覆盖**，而不是最长 mRNA span。对多 fragment 元素（CDS、exon、UTR），先求和再比是必需的 —— 单挑最长 fragment 会出错，因为很多中等 fragment 加起来可能比一个巨大 exon 覆盖更多 sequence。

#### 期望性质

- `chosen_transcripts.txt` 里每个基因至多出现一次。
- 选中的 transcript id 是该基因被注释的 isoform 之一。

#### 评估

PASS（读代码就能确认逻辑；每基因唯一性 invariant 与 `for (g in bestTid)` 枚举一致）。

---

### Step 4 —— 保留所选 transcript 的所有 fragment 并改回 gene 标签

#### 命令 / 代码路径

```text
awk -F'\t' '
    NR==FNR { chosen[$1] = 1; next }
    ($4 in chosen) {
        gid = $4; sub(/\..*/, "", gid); $4 = gid
        print
    }' chosen_transcripts.txt "$bedfile" \
    | sort -k4,4 -k2,2n > "$bedfile.tmp"
mv "$bedfile.tmp" "$bedfile"
```

(`pmet_index_element.sh:202-211`)

#### 用途

把 fragment-级 BED 过滤到只剩选中 transcript 的 fragment，再把第 4 列从 transcript id 改成 gene id。

#### 生物信息含义

BED 现在每基因含**该基因所选最长 isoform 的所有 CDS fragment**。N 个 CDS fragment 的基因就有 N 行。

对 06 默认（CDS、mrnaFull=No），仅当 `element=mRNA` 时才会跑额外的 UTR 减除步骤（`pmet_index_element.sh:216-243`）。CDS 走的话这条分支跳过（CDS 本来就排除 UTR）。

#### 评估

PASS。

---

### Step 5 —— 给多 fragment 基因打 `__GENE__N` 并丢掉 < 30 bp 的 fragment

#### 命令 / 代码路径

```text
awk -F'\t' '
    { n = ++seen[$4]; if (n > 1) $4 = "__" $4 "__" n; print }
' "$bedfile" \
    | awk -F'\t' '$3 - $2 >= 30' \
    | sort -k4,4 > "$bedfile.tmp"
```

(`pmet_index_element.sh:280-285`)

#### 用途

每个 fragment 成为独立 FIMO sequence。`AT1G01010` 第一个 fragment 保留裸 id；第二个变成 `__AT1G01010__2`、第三个 `__AT1G01010__3`，依此类推。然后丢掉短于 30 bp 的 fragment（已小于一般 TF motif 宽度）。

#### 生物信息含义

FIMO 的 `--topn` 是按序列计的；不打 fragment 标签的话，同基因多个 fragment 会争同一个名额。30 bp 下限同时也让局部 Markov 背景更稳定。

#### 期望性质

| 检查 | 期望 |
|---|---|
| 多行基因第 2..N 行被打 `__GENE__N` 标签 | 是（第 1 行保留裸 id） |
| 所有输出行长度 ≥ 30 bp | 是 |

#### 评估

PASS。通过看 `promoter.fa` 的 record header 确认（06 因为 `delete_temp=no` 把它留在磁盘上）：

```
>__AT1G01020__2     # 2nd fragment of AT1G01020
```

之前 baseline 的"每基因 fragment 数"分布：

| Fragment 数 | 基因数 |
|---:|---:|
| 1 | 21 714 |
| 2 | 1 278 |
| 3 | 471 |
| 4 | 13 |
| 5 | 6 |
| 6 | 4 |
| 7 | 6 |
| 8 | 2 |
| 9 | 1 |
| 10 | 2 |

（21,714 + 1,785 个多 fragment = 23,499 个独立基因 = universe size。）

---

### Step 6 —— 写 `universe.txt` 和 `promoter_lengths.txt`

#### 命令 / 代码路径

```text
awk -F'\t' '{ id=$4; sub(/^__/,"",id); sub(/__[0-9]+$/,"",id); print id }' \
    "$bedfile" | sort -u > "$universefile"
awk -F'\t' -v OFS='\t' '{ print $4, $3 - $2 }' "$bedfile" \
    > "$indexingOutputDir/promoter_lengths.txt"
```

(`pmet_index_element.sh:293-295`)

#### 用途

`universe.txt` 去掉 `__N` fragment 后缀 → 每个独立基因一行。`promoter_lengths.txt` 是**按 FIMO sequence 算**，即按 fragment 算，因为 FIMO 的 `--topn` 预算就是按序列计。collapse 回基因层在第 11 步做。

#### 生物信息含义

这是 pipeline 两种视角共存的时刻：

- 生物视角说"每基因一行"。
- FIMO 视角要求"每扫描序列一行"，而一个 AT1G… 基因有 4 个 CDS fragment 就是 4 个序列。

universe 走生物视角；临时的 `promoter_lengths.txt` 走 FIMO 视角。两者在第 11 步对账。

#### 输出

最初（按 fragment 的）`promoter_lengths.txt` 每 fragment 一行（之前 baseline ~25,902 行）。`universe.txt` 23,499 行。

#### 期望性质

- `universe.txt` = 独立 gene id（无 `__` fragment）。
- `promoter_lengths.txt` = 每 FIMO sequence 一行；多 fragment 基因出现 N 次。

#### 评估

PASS。

---

### Step 7 —— 抽序列（strand-aware）

#### 命令 / 代码路径

```text
awk '/^>/ {...} ...' "$genomefile" > "$indexingOutputDir/genome_stripped.fa"
bedtools getfasta \
    -fi "$indexingOutputDir/genome_stripped.fa" \
    -bed "$bedfile" -name -s \
    | sed -e 's/([+-])::.*//' -e 's/::.*//' > "$indexingOutputDir/promoter.fa"
```

(`pmet_index_element.sh:303-312`)

#### 用途

从基因组里 strand-aware 地取出元素 sequence；剥掉 bedtools 的 header annotation。

#### 生物信息含义

和 03 一样的 strand-aware 语义 —— `−` strand 序列被反向互补，使 FIMO 扫到生物意义上的链。**关键：fragment 之间分别保留为独立 FASTA record**（带 `__GENE__N` id），不拼接。拼接会造出真 motif 永远跨不过的虚假 junction。

#### 输出

`promoter.fa` —— 每 fragment 一条 record（baseline 25,902 条）。

```
>__AT1G01020__2
ATCATGCACTAAAGTTTCTTGTATTGATTAAACATGGTGTTATGTCTCTTTGCTCAAAAA…
```

脚本随后校验无重复 id：

```text
dup_ids=$(grep '^>' "$indexingOutputDir/promoter.fa" | sort | uniq -d)
```

(`pmet_index_element.sh:314-318`)

#### 期望性质

- `promoter.fa` 没有重复 header。
- `−` strand fragment 已反向互补。

#### 评估

PASS（uniq 检测 guard 在位；baseline 没触发）。

---

### Step 8 —— 背景、IC、MEME batch 切分、FIMO

#### 命令 / 代码路径

```text
fasta-get-markov "$indexingOutputDir/promoter.fa" > .../promoter.bg
python3 parse_memefile.py "$memefile" memefiles/
python3 calculateICfrommeme_IC_to_csv.py memefiles/ IC.txt
python3 parse_memefile_batches.py "$memefile" memefiles/ "$threads"
parallel --jobs="$threads" "build/fimo --no-qvalue --text \
    --thresh 0.05 --bgfile promoter.bg --topn 5000 --topk 5 \
    --oc fimohits memebatch promoter.fa promoter_lengths.txt"
```

(`pmet_index_element.sh:325-381`)

#### 用途

和 03 step 7 一样 —— 每 batch 内 FIMO 扫 + PMETindex（binomial 阈值）融合调用。

> **与 03 的关键差别：** 06 / 07 用 `build/fimo`（带 `--topk` patch 的独立 FIMO），而 03 / 05 用 `build/index_fimo_fused`。两者都基于 MEME 5.x；API 与输出格式完全一致。

#### 输出

```
fimohits/<motif>.txt              113 files (one per motif)
binomial_thresholds.txt           113 rows
```

parallel 写完后脚本会排序 binomial threshold 文件（`pmet_index_element.sh:379-381`），让多次运行的字节顺序稳定。

#### 期望性质

- 113 个 motif 进，113 个 fimohits 文件出。
- binomial threshold 113 行。
- 所有行都引用 fragment 级 id（`__GENE__N` 或裸 id）。

#### 评估

PASS（对照之前 baseline）。审计时 pipeline 正在 FIMO 中段；部分输出已显示符合预期的"每 batch round-robin 写文件"模式。

---

### Step 9 —— 把 fragment 级结果 collapse 回基因级

#### 命令 / 代码路径

```text
# promoter_lengths: sum per-gene
awk -F'\t' '{
    sub(/^__/, "", $1); sub(/__[0-9]+$/, "", $1)
    sum[$1] += $2
}
END { for (g in sum) print g "\t" sum[g] }' \
    "$indexingOutputDir/promoter_lengths.txt" > .../promoter_lengths.tmp

# fimohits: strip __N from col 2; per gene keep top maxk hits below
# the motif's binomial threshold (sort -g handles 1.2e-07).
while IFS=$'\t' read -r motif threshold _; do
    src=fimohits/${motif}.txt; dst=fimohits_merged/${motif}.txt
    awk '{ sub(/^__/,"",$2); sub(/__[0-9]+$/,"",$2); print }' "$src" \
    | sort -t $'\t' -k2,2 -k7,7g \
    | awk -v k=$maxk -v thr=$threshold '
        $2 != prev { prev=$2; n=0 }
        { n++; if (n <= k && ($7+0) < (thr+0)) print }
    ' > "$dst"
done < "$indexingOutputDir/binomial_thresholds.txt"

rm -rf "$indexingOutputDir/fimohits"
mv  "$indexingOutputDir/fimohits_merged" "$indexingOutputDir/fimohits"
```

(`pmet_index_element.sh:391-417`)

#### 用途

把 fragment 级 FIMO 视角和基因级生物视角对账：

- 基因长度 = 各 fragment 长度之和。
- 基因 hit = 把同基因 fragment 的 hit 合并后，取 top-`maxk`(=5) 且击穿该 motif binomial 阈值的最显著 hit。

#### 生物信息含义

多 fragment 扫描能检出"motif 出现在所选 isoform *任何一个* CDS fragment 内"；这一步 collapse 接着问"这个基因是该 motif 的候选吗？"，答案是聚合 fragment 证据。

#### 输出

collapse 之后：

```
universe.txt           23499 lines
promoter_lengths.txt   23499 rows  (gene-level)
fimohits/<motif>.txt   113 files  (gene-level ids only)
binomial_thresholds.txt  113 rows
IC.txt                 113 rows
```

`promoter_lengths.txt` 前 3（baseline）：

```
AT4G29580   302
AT1G04030   325
AT1G48195   187
```

`fimohits/AHL12.txt` 前 3（baseline）：

```
AHL12   AT1G01010   203   210   -   5.971014   2.692e-03   ATTATTAT
AHL12   AT1G01010   239   246   -   5.927536   3.258e-03   TTATTTAT
AHL12   AT1G01010   107   114   -   5.282609   6.517e-03   TAAAATAT
```

（第 8 列是匹配序列，这里有是因为 06 用的是 `build/fimo` 而非 `index_fimo_fused`。）

#### 期望性质

| 检查 | 期望 | 观察（baseline） |
|---|---|---|
| `promoter_lengths.txt` 行数 | = `universe.txt` 行数 | 23499 ≡ 23499 |
| `promoter_lengths.txt` 第 1 列无 `__` | 是 | 0 违例 |
| `fimohits/*` 第 2 列无 `__` | 是 | 0 违例 |
| 基因长度 == 各 fragment 长度之和 | 是 | 构造保证 |
| Mean 长度 | 对 CDS 合理 | 334.985 bp（与典型短 CDS 分布一致） |
| Min 长度 | ≥ 30（lt30 下限） | 30 |
| Max 长度 | 几 kb（多 fragment 基因） | 4144 |

#### 观察结果

对之前 baseline 全部成立。

#### 评估

PASS。

---

### Step 10 —— 清理 + 契约校验

#### 命令 / 代码路径

```text
if [[ $delete == [Yy]* ]]; then  rm -rf intermediates; fi
file_count=$(find fimohits -name '*.txt' | wc -l)
if [ "$file_count" -eq "$nummotifs" ]; then
    python3 check_homotypic_contract.py "$indexingOutputDir"
fi
```

(`pmet_index_element.sh:421-451`)

06 的 `delete_temp=no`，所以 `promoter.fa`、`promoter.bg`、`genome_stripped.fa`、`memefiles/` 都留在磁盘上（对类似本审计的工作很有用 —— 07 把它们删了）。

#### 评估

PASS。

---

### Step 11 —— 异型 motif-pair 检验（5 任务循环）

#### 命令 / 代码路径

```text
for task in salt_top300 random_genes_300 genes_cell_type_treatment \
            gene_cortex_epidermis_pericycle heat_top300; do
    grep -Ff universe.txt data/genes/$task.txt \
        > heterotypic_$task/new_genes_temp.txt
    build/pmetParallel \
        -d . -g new_genes_temp.txt -i 4 \
        -p promoter_lengths.txt -b binomial_thresholds.txt \
        -c IC.txt -f fimohits \
        -o heterotypic_$task -t 8 > pmet.log
    cat heterotypic_$task/*.txt > heterotypic_$task/motif_output.txt
done
```

(`_elements_common.sh:120-156`)

2025 年 8 月那次 fix 让这一聚合**幂等**：在 `cat` 之前删掉旧的 `motif_output.txt`，再通过 `mktemp` 缓冲 cat。这样旧跑的 `motif_output` 不会被喂回下一次聚合。(`_elements_common.sh:146-156`)

#### 输出（之前 baseline）

| 任务 | `motif_output.txt` 行数 | plot 目录里 heatmap PNG 数 |
|---|---:|---:|
| `salt_top300` | 12 657 | 3 |
| `random_genes_300` | 25 313 | **0**（只有 histogram） |
| `genes_cell_type_treatment` | 37 969 | 3 |
| `gene_cortex_epidermis_pericycle` | 18 985 | 3 |
| `heat_top300` | 12 657 | 3 |

#### 期望性质

- 11 列。✓
- 每任务行数 = `1 + C(motif, 2) * num_clusters`。✓（如 `salt_top300` 2 个 cluster → 1 + 2 × 6328 = 12657 ✓）。

#### 评估

5 个任务结构上都 PASS。`random_genes_300` 没 PNG 是 pipeline 04 也见过的同款 `draw_heatmap.R` 行为 —— 没有 adjusted p 击穿显著性阈值时，R 脚本只写诊断 histogram。`random_genes_300` 设计上就是 null 对照，所以这是预期行为；但应该写在文档里，免得使用者把它误解成 pipeline 失败。

---

### Step 12 —— Heatmap（每任务 3 视图）

#### `genes_cell_type_treatment` 输出（baseline）

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `03_plot_genes_cell_type_treatment/heatmap.png` | 424 131 | `a57c5f340e9246d3f4b0e96ae11cb3789d388d5da0a2c401531bb9e4cba0e30b` |
| `…/heatmap_overlap.png` | （与 `_unique` 一致） | `574bf18711fd4ff98f415229448f9a1ab81a6e3a3d5e265490fb30259d62be4d` |
| `…/heatmap_overlap_unique.png` | （与 `_overlap` 一致） | `574bf18711fd4ff98f415229448f9a1ab81a6e3a3d5e265490fb30259d62be4d` |

#### 期望性质

- 除 motif_output 退化的任务（`random_genes_300`）外，每任务 3 张 PNG 都存在。
- 两张 `Overlap` PNG 互不相同。

#### 观察结果

`unique == non-unique` 字节一致的现象在 05 与 07 也见过。原因见 [`promoter-gap.md` §4 step 10](promoter-gap.md) 的同款备注 —— 这是输入 motif_output 分布的性质，不是 06 特有的缺陷。

#### 评估

WARNING（与 05/07 共有的 PNG 一致性 quirk）。其余 PASS。

<a id="cn-5"></a>

## 5. 最终输出

```
results/06_elements_longest/
├── 01_homotypic/
│   ├── universe.txt              23 499 genes (CDS-bearing)
│   ├── promoter_lengths.txt      23 499 rows;  min=30, max=4144, mean=335
│   ├── binomial_thresholds.txt   113   rows
│   ├── IC.txt                    113   rows
│   ├── fimohits/                 113   files
│   ├── promoter.fa               25 902 records (per-fragment, kept on disk)
│   ├── promoter.bg               4-base markov background
│   ├── genome_stripped.fa        ~120 MB linearised genome
│   └── CDS.bed                   raw per-fragment BED (kept on disk)
├── 02_heterotypic_<task>/        × 5 tasks
└── 03_plot_<task>/               × 5 tasks (3 PNGs each except random_genes_300)
```

<a id="cn-6"></a>

## 6. 风险 / 边界情况

1. **"Longest isoform" 是按元素覆盖算的，不是按 mRNA span。** `-e CDS` 算最长 CDS；`-e mRNA` 算最长 mRNA。这是 PMET 想要的语义（要扫到最多的 coding 序列），但跟 AGAT 等工具里"longest isoform" 经常指的"最长 pre-mRNA span"**不**一样。

2. **fragment 级 vs 基因级视角。** pipeline 在两种视角间切换 —— 初始扫描按 fragment、带 `__GENE__N` 标签；最终输出 collapse 回基因级。collapse 时每基因每 motif 保留 top-`maxk`(=5) 个击穿 binomial 阈值的 fragment hit。这正是 PMET 语义，但意味着基因得分**不是**所有 fragment 的累加 —— 它是"最好 5 个 fragment hit"规则。直接把 06 跟 03 比较的人需要知道这种不对称。

3. **30 bp 的最小 fragment 长度。** 真实存在的小于 30 bp 的 CDS micro-exon 会被静默丢掉。在 TAIR10 罕见，但对紧凑基因家族可能有影响。

4. **`mrnaFull=No` 的 UTR 减除对无 UTR transcript 是静默的。** (`pmet_index_element.sh:216-243`) `bedtools subtract` 在 `-b` 为空时是 no-op，这正是预期行为。不是缺陷，只是不直观。

5. **对照任务无 heatmap。** `random_genes_300` 设计上就是 null 对照。没有任何调整后的 p 击穿时，R 脚本静默不出 `heatmap*.png`。容易被当成 pipeline 失败。

6. **`Overlap` × `unique` 的 PNG 一致性 quirk。** 与 pipeline 05、07 共有 —— 见那些文档。

<a id="cn-7"></a>

## 7. 总结

**整体状态：PASS**（与 05/07 共有 1 条 WARNING：`heatmap_overlap == heatmap_overlap_unique`；1 条预期内的 `random_genes_300` 无 heatmap）。

pipeline 06 正确实现了"按总元素长度选每基因最长 isoform"，扫描时保留所选 isoform 的所有 fragment（带 `__GENE__N` 标签，能完整 round-trip），最后把 fragment 级 hit collapse 回基因级供异型检验。所有结构性 invariant —— universe ≡ lengths gene 集、fimohits 数 == motif 数、最终输出无 `__N` artefact、BED 坐标合规、strand-aware 序列抽取 —— 对之前 baseline 都成立。

输出可作为 03/05 上游启动子视角之外的"coding 区域 motif"补充。

> **审计 caveat：** 写本审计时同型阶段正在重跑；上面那些契约数字是重跑开始前的快照。审计的期望性质是结构性的、不依赖新跑的精确数字，但输出文件的 SHA-256 hash 重跑结束后需要对 `docs/verification_log.md` 重新确认。
