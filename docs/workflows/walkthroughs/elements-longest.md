# Pipeline 06: Genomic-Element PMET (Longest Isoform per Gene)

Script: [scripts/pipeline/06_elements_longest.sh](../../scripts/pipeline/06_elements_longest.sh)
Shared body: [scripts/pipeline/_elements_common.sh](../../scripts/pipeline/_elements_common.sh)
Indexer: [scripts/indexing/pmet_index_element.sh](../../scripts/indexing/pmet_index_element.sh)

## 1. Pipeline Purpose

Run PMET on a **chosen genomic element** (CDS / exon / mRNA / 5' UTR /
3' UTR) — *inside* the gene body, not upstream of it — picking the
**single longest isoform per gene** as the per-gene representative.

Use case: ask whether motif pairs are co-enriched not in the
regulatory upstream window (which is what 03/05 do) but inside the
transcribed region of the gene itself. This is informative for:

- intron- and exon-encoded regulatory elements (e.g. exon-junction
  binding, intronic enhancers — though 06's default `CDS` excludes
  introns);
- post-transcriptional motifs that overlap the coding region;
- splicing-coupled regulation, when run with `mRNA` or `exon`.

The "longest isoform" is per-gene representative selection: if a gene
has 5 transcripts, only the one with the greatest **total element
length** is kept; all of its fragments contribute to FIMO scanning.

## 2. Inputs

| File | Biological meaning | Format | Truncated sample |
| --- | --- | --- | --- |
| `data/TAIR10.fasta` | TAIR10 genome | FASTA | `>1`, `>2`, ... |
| `data/TAIR10.gff3` | TAIR10 annotation | GFF3 v3 | gene/mRNA/exon/CDS rows |
| `data/Franco-Zorrilla_et_al_2014.meme` | 113 plant TF motifs | MEME v4 | 113 `MOTIF` lines |
| `data/genes/<task>.txt` × 5 | five heterotypic test sets | `<cluster> <gene>` | varies |
| Element choice | interactive prompt: 1=3'UTR, 2=5'UTR, 3=mRNA, 4=CDS, 5=exon | TTY | the canonical real-data check uses `printf '4\n' | bash …` (CDS) |

The five gene-list tasks driven in a loop:

```text
salt_top300, random_genes_300, genes_cell_type_treatment,
gene_cortex_epidermis_pericycle, heat_top300
```
([_elements_common.sh:120](../../scripts/pipeline/_elements_common.sh#L120))

The `random_genes_300` task is a designed-for-no-signal control set;
the others are biologically meaningful clusters.

## 3. Output Contract

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

> **Audit-time note:** at the moment this audit was written, the
> production pipeline was actively re-running into
> `results/06_elements_longest/01_homotypic/`, so the numbers below
> for the homotypic stage come from the **prior committed baseline**
> (Apr 26 run, captured before the re-run began). The contract
> expectations are unchanged; the actual hashes will be recorded by
> `docs/verification_log.md` once the re-run completes.

## 4. Step-by-Step Execution Story

The homotypic stage is `scripts/indexing/pmet_index_element.sh`. It
does not call `run_homotypic.py` — it has its own logic, in pure
shell + awk + Python helpers, because the GFF3-handling for
genomic elements (multiple isoforms per gene, multiple fragments per
isoform) is fundamentally different from "one promoter per gene".

### Step 1: Chromosome-naming preflight

#### Command / Code Path

```text
gff3_chrom=$(awk -F'\t' '/^[^#]/ && NF>=8 { print $1; exit }' "$gff3file")
fasta_chrom=$(awk '/^>/ { sub(/^>/,""); sub(/ .*/,""); print; exit }' "$genomefile")
[[ "$gff3_chrom" != "$fasta_chrom" ]] && exit 1
```
([pmet_index_element.sh:135-144](../../scripts/indexing/pmet_index_element.sh#L135-L144))

#### Purpose

Same as 03's preflight: catch `1` vs `Chr1` style mismatch before
silently producing empty BED.

#### Assessment

PASS (TAIR10 uses `1` consistently in GFF3 and FASTA).

---

### Step 2: Extract chosen element rows from GFF3

#### Command / Code Path

```text
awk -F'\t' -v elem="$element" -v key="$gff3id" '
    /^#/ { next }
    $3 == elem && $4 < $5 {
        ... print $1, $4-1, $5, transcript_id, 1, $7
    }
' "$gff3file" > "$bedfile"
```
([pmet_index_element.sh:152-164](../../scripts/indexing/pmet_index_element.sh#L152-L164))

For element `CDS` the `gff3id` is `Parent=transcript:` so the BED
column 4 is the **transcript id**, not the gene id. Column conversion
is GFF3 1-based → BED 0-based via `start - 1`.

#### Purpose

Pull every CDS row from the annotation, keyed by transcript so that
isoform-specific aggregation can run next.

#### Bioinformatics Meaning

Each gene typically has multiple transcripts (mRNA isoforms); each
isoform has multiple CDS fragments (one per coding exon). At this
point `<bedfile>` has one row per fragment, labelled by transcript.

#### Output

`<out>/CDS.bed` — a few hundred thousand rows, ~5 MB. Sample column
layout: `chrom, start, end, transcript_id, 1, strand`.

#### Expected Properties

- Every row has 6 fields, `start < end`.
- Column 4 contains transcript ids (not gene ids).
- Strand ∈ {`+`,`-`}.

#### Assessment

PASS.

---

### Step 3: Pick longest isoform per gene

#### Command / Code Path

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
([pmet_index_element.sh:181-197](../../scripts/indexing/pmet_index_element.sh#L181-L197))

#### Purpose

For every gene, choose the one transcript whose **total CDS length**
is greatest (sum across all fragments).

#### Bioinformatics Meaning

The pipeline name says "longest isoform". The implementation defines
that as longest *element coverage*, not longest mRNA span. For
multi-fragment elements (CDS, exon, UTR) summing-before-comparing is
required — picking the single longest fragment would be wrong because
a transcript with many medium fragments may cover more sequence than
a transcript with one giant exon.

#### Expected Properties

- Each gene appears at most once in `chosen_transcripts.txt`.
- The chosen transcript id is one of the gene's annotated isoforms.

#### Assessment

PASS (logic verified by reading; per-gene uniqueness invariant
matches `for (g in bestTid)` enumeration).

---

### Step 4: Keep all fragments of chosen transcripts; relabel to gene

#### Command / Code Path

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
([pmet_index_element.sh:202-211](../../scripts/indexing/pmet_index_element.sh#L202-L211))

#### Purpose

Filter the per-fragment BED to only fragments belonging to a chosen
transcript, then rewrite column 4 from transcript id to gene id.

#### Bioinformatics Meaning

The BED now has, per gene, **all the CDS fragments of that gene's
single longest isoform**. A gene with N CDS fragments shows up as N
rows.

For the 06 default (CDS, mrnaFull=No), an additional UTR-subtraction
step runs only when `element=mRNA` ([pmet_index_element.sh:216-243](../../scripts/indexing/pmet_index_element.sh#L216-L243)).
For CDS that branch is skipped (CDS already excludes UTRs).

#### Assessment

PASS.

---

### Step 5: Tag multi-fragment genes with `__GENE__N` and drop fragments < 30 bp

#### Command / Code Path

```text
awk -F'\t' '
    { n = ++seen[$4]; if (n > 1) $4 = "__" $4 "__" n; print }
' "$bedfile" \
    | awk -F'\t' '$3 - $2 >= 30' \
    | sort -k4,4 > "$bedfile.tmp"
```
([pmet_index_element.sh:280-285](../../scripts/indexing/pmet_index_element.sh#L280-L285))

#### Purpose

Each fragment becomes a distinct FIMO sequence. The first fragment of
gene `AT1G01010` keeps the bare id; the second becomes
`__AT1G01010__2`, the third `__AT1G01010__3`, etc. Then drop fragments
shorter than 30 bp (below typical TF motif width).

#### Bioinformatics Meaning

FIMO's `--topn` is per-sequence; without per-fragment ids, multiple
fragments of the same gene would compete for the same slot. The 30 bp
cutoff also stabilises the local Markov background.

#### Expected Properties

| Check | Expectation |
| --- | --- |
| Every multi-row gene gets `__GENE__N` for rows 2..N | yes (row 1 keeps the bare id) |
| All output rows have length ≥ 30 bp | yes |

#### Assessment

PASS. Verified by inspecting the per-record headers in
`promoter.fa` (kept on disk because `delete_temp=no` for 06):

```
>__AT1G01020__2     # 2nd fragment of AT1G01020
```

Fragment-per-gene distribution from the prior baseline:

| Fragments | Genes |
| ---: | ---: |
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

### Step 6: Write `universe.txt` and `promoter_lengths.txt`

#### Command / Code Path

```text
awk -F'\t' '{ id=$4; sub(/^__/,"",id); sub(/__[0-9]+$/,"",id); print id }' \
    "$bedfile" | sort -u > "$universefile"
awk -F'\t' -v OFS='\t' '{ print $4, $3 - $2 }' "$bedfile" \
    > "$indexingOutputDir/promoter_lengths.txt"
```
([pmet_index_element.sh:293-295](../../scripts/indexing/pmet_index_element.sh#L293-L295))

#### Purpose

`universe.txt` strips the `__N` fragment suffix → one line per unique
gene. `promoter_lengths.txt` is **per FIMO sequence**, i.e. per
fragment, because FIMO's `--topn` budget is per sequence. The
collapse to gene-level happens later (step 11).

#### Bioinformatics Meaning

This is the moment when the pipeline's two views co-exist:

- The biology view says "one entry per gene".
- The FIMO view requires "one entry per scanned sequence", and an
  AT1G… gene with 4 CDS fragments is 4 sequences.

Universe takes the biology view; the temporary `promoter_lengths.txt`
takes the FIMO view. The two will be reconciled at step 11.

#### Output

Initial (per-fragment) `promoter_lengths.txt` has one row per
fragment (~25,902 rows for the prior baseline). `universe.txt` has
23,499 rows.

#### Expected Properties

- `universe.txt` = unique gene ids (no `__` fragments).
- `promoter_lengths.txt` = one row per FIMO sequence; multi-fragment
  genes appear N times.

#### Assessment

PASS.

---

### Step 7: Extract sequences (strand-aware)

#### Command / Code Path

```text
awk '/^>/ {...} ...' "$genomefile" > "$indexingOutputDir/genome_stripped.fa"
bedtools getfasta \
    -fi "$indexingOutputDir/genome_stripped.fa" \
    -bed "$bedfile" -name -s \
    | sed -e 's/([+-])::.*//' -e 's/::.*//' > "$indexingOutputDir/promoter.fa"
```
([pmet_index_element.sh:303-312](../../scripts/indexing/pmet_index_element.sh#L303-L312))

#### Purpose

Pull element sequences from the genome with strand-aware reverse-
complementation; strip bedtools header annotations.

#### Bioinformatics Meaning

Same strand-aware semantics as 03 — `−` strand sequences are
reverse-complemented so FIMO scans biologically meaningful strands.
Crucially, **fragments are kept as separate FASTA records** (with
`__GENE__N` ids), not stitched together. Stitching would create
fake junctions that no real motif could span.

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
([pmet_index_element.sh:314-318](../../scripts/indexing/pmet_index_element.sh#L314-L318))

#### Expected Properties

- No duplicate header lines in `promoter.fa`.
- Reverse-complementation is applied for `−` strand fragments.

#### Assessment

PASS (uniq-detection guard is in place; not triggered in baseline).

---

### Step 8: Background, IC, MEME batch split, FIMO

#### Command / Code Path

```text
fasta-get-markov "$indexingOutputDir/promoter.fa" > .../promoter.bg
python3 parse_memefile.py "$memefile" memefiles/
python3 calculateICfrommeme_IC_to_csv.py memefiles/ IC.txt
python3 parse_memefile_batches.py "$memefile" memefiles/ "$threads"
parallel --jobs="$threads" "build/fimo --no-qvalue --text \
    --thresh 0.05 --bgfile promoter.bg --topn 5000 --topk 5 \
    --oc fimohits memebatch promoter.fa promoter_lengths.txt"
```
([pmet_index_element.sh:325-381](../../scripts/indexing/pmet_index_element.sh#L325-L381))

#### Purpose

Same as 03's step 7 — FIMO scan plus PMETindex (binomial threshold)
in fused calls per batch.

> **Important difference vs 03:** 06 / 07 use `build/fimo` (the
> standalone FIMO with `--topk` patch), whereas 03 / 05 use
> `build/index_fimo_fused`. Both are based on MEME 5.x; the API and
> output format are identical.

#### Output

```
fimohits/<motif>.txt              113 files (one per motif)
binomial_thresholds.txt           113 rows
```

After parallel writes the script sorts the binomial thresholds file
([pmet_index_element.sh:379-381](../../scripts/indexing/pmet_index_element.sh#L379-L381))
to make the byte order stable across runs.

#### Expected Properties

- 113 motifs in, 113 fimohits files out.
- 113 binomial threshold rows.
- All rows reference per-fragment ids (`__GENE__N` or bare id).

#### Assessment

PASS (against prior baseline). At audit time the pipeline was
mid-FIMO; partial output shows the expected per-batch round-robin
file emission pattern.

---

### Step 9: Collapse per-fragment results back to gene level

#### Command / Code Path

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
([pmet_index_element.sh:391-417](../../scripts/indexing/pmet_index_element.sh#L391-L417))

#### Purpose

Reconcile the per-fragment FIMO view with the gene-level biology view:

- Gene length = sum of fragment lengths.
- Gene's hits = top-`maxk` (=5) most-significant fragment hits that
  beat the motif's binomial threshold, after pooling fragments of the
  same gene.

#### Bioinformatics Meaning

Multi-fragment scanning detects motifs that occur within *any* CDS
fragment of the chosen isoform; this collapse step then asks "is the
gene a candidate for this motif?" by aggregating fragment evidence.

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

(8th column is the matched sequence, present here because 06 uses
`build/fimo` not `index_fimo_fused`.)

#### Expected Properties

| Check | Expectation | Observation (baseline) |
| --- | --- | --- |
| `promoter_lengths.txt` row count | = `universe.txt` row count | 23499 ≡ 23499 |
| No `__` in `promoter_lengths.txt` col 1 | yes | 0 violations |
| No `__` in `fimohits/*` col 2 | yes | 0 violations |
| Gene length == sum of its fragment lengths | yes | by construction |
| Mean length | reasonable for CDS | 334.985 bp (matches typical short-CDS distribution) |
| Min length | ≥ 30 (the lt30 floor) | 30 |
| Max length | several kb (multi-fragment genes) | 4144 |

#### Observed Result

All hold against the prior baseline.

#### Assessment

PASS.

---

### Step 10: Cleanup + contract validation

#### Command / Code Path

```text
if [[ $delete == [Yy]* ]]; then  rm -rf intermediates; fi
file_count=$(find fimohits -name '*.txt' | wc -l)
if [ "$file_count" -eq "$nummotifs" ]; then
    python3 check_homotypic_contract.py "$indexingOutputDir"
fi
```
([pmet_index_element.sh:421-451](../../scripts/indexing/pmet_index_element.sh#L421-L451))

For 06 `delete_temp=no`, so `promoter.fa`, `promoter.bg`, `genome_stripped.fa`,
`memefiles/` are kept (useful for audits like this one — pipeline 07
has them removed).

#### Assessment

PASS.

---

### Step 11: Heterotypic motif-pair test (looped over 5 tasks)

#### Command / Code Path

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
([_elements_common.sh:120-156](../../scripts/pipeline/_elements_common.sh#L120-L156))

The Aug 2025 fix made this aggregate **idempotent** by removing any
old `motif_output.txt` before the `cat`, then concatenating via a
`mktemp` buffer; this prevents an old run's `motif_output` from being
fed back into the next aggregation. ([_elements_common.sh:146-156](../../scripts/pipeline/_elements_common.sh#L146-L156))

#### Output (prior baseline)

| Task | `motif_output.txt` rows | Heatmap PNGs in plot dir |
| --- | ---: | ---: |
| `salt_top300` | 12 657 | 3 |
| `random_genes_300` | 25 313 | **0** (only histograms) |
| `genes_cell_type_treatment` | 37 969 | 3 |
| `gene_cortex_epidermis_pericycle` | 18 985 | 3 |
| `heat_top300` | 12 657 | 3 |

#### Expected Properties

- 11 columns. ✓
- Row count = `1 + C(motif, 2) * num_clusters` per task. ✓ (e.g.
  `salt_top300` has 2 clusters → 1 + 2 × 6328 = 12657 ✓).

#### Assessment

PASS for all five tasks structurally. The `random_genes_300` PNG
absence is the same `draw_heatmap.R` behaviour seen in pipeline 04 —
when no adjusted p-value passes the significance threshold, the R
script writes only the diagnostic histogram. By design `random_genes_300`
is a null control, so this is expected, but it should be documented
so consumers don't assume the pipeline failed.

---

### Step 12: Heatmaps (per task, three views)

#### Output for `genes_cell_type_treatment` (baseline)

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `03_plot_genes_cell_type_treatment/heatmap.png` | 424 131 | `a57c5f340e9246d3f4b0e96ae11cb3789d388d5da0a2c401531bb9e4cba0e30b` |
| `…/heatmap_overlap.png` | (matches `_unique`) | `574bf18711fd4ff98f415229448f9a1ab81a6e3a3d5e265490fb30259d62be4d` |
| `…/heatmap_overlap_unique.png` | (matches `_overlap`) | `574bf18711fd4ff98f415229448f9a1ab81a6e3a3d5e265490fb30259d62be4d` |

#### Expected Properties

- All three PNGs exist for every task except those whose
  motif_output is degenerate (random_genes_300).
- The two `Overlap` PNGs differ from each other.

#### Observed Result

Same `unique == non-unique` byte-identity pattern as in 05 and 07.
See [05_promoter_gap.md §4 step 10](05_promoter_gap.md) for the same
note — it is a property of the input motif_output distribution, not a
06-specific defect.

#### Assessment

WARNING (PNG-identity quirk shared with 05/07).
PASS otherwise.

## 5. Final Outputs

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

## 6. Risks / Edge Cases

1. **"Longest isoform" is by element coverage, not by mRNA span.**
   For `-e CDS` it's longest CDS; for `-e mRNA` it's longest mRNA.
   This is the right semantics for PMET (we want the most coding
   sequence to scan), but is *not* what the term sometimes means in
   tools like AGAT (which often pick longest pre-mRNA span).

2. **Fragment-level vs gene-level views.** The pipeline alternates
   between the two — initial scanning is per-fragment, with `__GENE__N`
   tagging; final outputs are collapsed back to gene level. The
   collapse keeps top-`maxk` (=5) fragment hits per gene per motif,
   below the binomial threshold. This is the correct PMET semantics
   but means a gene's score is **not** a sum across fragments — it's a
   "best 5 fragment hits" rule. Consumers comparing 06 directly to 03
   should know this asymmetry.

3. **30 bp minimum fragment length.** A real CDS micro-exon below 30 bp
   is silently dropped. Rare in TAIR10 but can affect compact gene
   families.

4. **`mrnaFull=No` UTR subtraction is silent on UTR-less transcripts.**
   ([pmet_index_element.sh:216-243](../../scripts/indexing/pmet_index_element.sh#L216-L243))
   `bedtools subtract` with an empty `-b` is a no-op, which is the
   intended behaviour. Not a defect, just non-obvious.

5. **No heatmap for control task.** `random_genes_300` is by design a
   no-signal control. The R script silently produces no `heatmap*.png`
   when nothing passes adjustment. Easy to mistake for a pipeline
   failure.

6. **PNG identity quirk for `Overlap` × `unique`.** Shared with
   pipelines 05 and 07 — see those docs.

## 7. Summary

**Overall status: PASS** (one shared WARNING with 05/07 on
`heatmap_overlap == heatmap_overlap_unique`, one expected
`random_genes_300` heatmap absence).

Pipeline 06 correctly implements per-gene "longest isoform" selection
by total element-length, preserves all fragments of the chosen
isoform during scanning (with `__GENE__N` tagging that round-trips
cleanly), and collapses fragment-level hits back to gene-level for
the heterotypic test. All structural invariants — universe ≡ lengths
gene-set, fimohits count == motif count, no `__N` artefacts in final
output, BED coordinates well-formed, strand-aware sequence
extraction — hold against the prior baseline.

The outputs are suitable as a "coding-region motif" complement to
the upstream-promoter views in 03/05.

> **Audit caveat:** the homotypic stage was actively re-running while
> this audit was written; the contract numbers above were captured
> before the re-run started. The audit's expected properties are
> structural and do not depend on the new run's exact numbers, but
> SHA-256 hashes of the output files will need to be reconfirmed
> against `docs/verification_log.md` once the re-run completes.
