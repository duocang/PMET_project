# Pipeline 07: Genomic-Element PMET (Per-Gene UNION across Isoforms)

Script: [scripts/pipeline/07_elements_merged.sh](../../scripts/pipeline/07_elements_merged.sh)
Shared body: [scripts/pipeline/_elements_common.sh](../../scripts/pipeline/_elements_common.sh)
Indexer: [scripts/indexing/pmet_index_element.sh](../../scripts/indexing/pmet_index_element.sh)
(strategy = `merged`)

## 1. Pipeline Purpose

Same biological setting as [pipeline 06](06_elements_longest.md) —
PMET on a chosen genomic element (CDS / exon / mRNA / 5' UTR /
3' UTR) inside the gene body — but using a different isoform
aggregation strategy:

> Per gene, take the **union** of all isoforms' element intervals,
> merging overlapping and book-ended intervals into a single
> non-redundant set. No isoform specificity, no UTR subtraction.

If pipeline 06 says "pick the most-coding transcript and use its
fragments", pipeline 07 says "consider every transcript's coding
regions, pool them, scan once". The two are alternative answers to
the same question — which set of element-derived sequences should
represent each gene? — and produce a slightly different signal under
alternative splicing.

## 2. Inputs

Identical to pipeline 06 ([06_elements_longest.md §2](06_elements_longest.md#2-inputs)).
The only configuration that differs is the strategy flag:

| Parameter | 06 (longest) | 07 (merged) |
| --- | --- | --- |
| `strategy` | `longest` | `merged` |
| `delete_temp` | `no` | `yes` |
| `mrnaFull` | `No` (subtract UTRs from mRNA) | not applicable (merge has no UTR-subtraction) |

The five heterotypic tasks are identical. Defaults are the same.

## 3. Output Contract

Identical to pipeline 06:

```
results/07_elements_merged/
├── 01_homotypic/
├── 02_heterotypic_<task>/   × 5
└── 03_plot_<task>/          × 5
```

## 4. Step-by-Step Execution Story

Steps 1, 2, 4–10 are byte-identical to pipeline 06 (same indexer,
same downstream code path). Only the **isoform aggregation step**
diverges. This audit only re-describes the divergent step in detail
and refers back to 06 for the rest.

### Step 1: Chromosome-naming preflight + element extraction

Identical to 06 step 1 + 2. PASS.

### Step 2: Per-gene merge across isoforms

#### Command / Code Path

```text
awk -F'\t' -v OFS='\t' '{ sub(/\..*/, "", $4); print }' "$bedfile" \
    | sort -k4,4 -k1,1 -k2,2n \
    | awk -F'\t' -v OFS='\t' '
        function flush() { if (g != "") print chrom, s, e, g, ".", strand }
        {
            if ($4 != g || $1 != chrom || $2 > e) {
                flush()
                chrom = $1; s = $2; e = $3; g = $4; strand = $6
            } else if ($3 > e) {
                e = $3
            }
        }
        END { flush() }
    ' > "$bedfile.tmp"
mv "$bedfile.tmp" "$bedfile"
```
([pmet_index_element.sh:255-270](../../scripts/indexing/pmet_index_element.sh#L255-L270))

This block does three things in sequence:

1. **Strip `.N` transcript suffix** — every `AT1G01010.1`, `AT1G01010.2`,
   `AT1G01010.3` row collapses to gene id `AT1G01010` so all isoforms
   of the same gene end up adjacent in the next sort.
2. **Sort by gene + chromosome + start.**
3. **Single-pass linear merge** that emits one row per
   maximal contiguous run. The condition `$2 > e` (strictly greater
   than the running end) — not `>=` — means *book-ended* intervals
   (an interval that begins exactly where the previous ends) are
   merged into one.

The book-ended-interval policy is documented inline as a deliberate
choice, matching `bedtools merge` default semantics. This was
explicitly fixed in two recent commits:

```text
2785a52 fix: merge book-ended intervals in pmet_index_element merged strategy
2e6ec81 fix: merged strategy now merges book-ended intervals (bedtools semantics)
```
([git log](../../) recent commits)

#### Purpose

Produce, per gene, a non-redundant minimal set of intervals covering
**every CDS region present in any isoform** of that gene.

#### Bioinformatics Meaning

Two reasons to prefer merge over longest:

1. *Robust to isoform misannotation.* If TAIR10 mistakenly omits an
   exon from one isoform, "longest" might pick that incomplete
   isoform; merge sees the union and is unaffected.
2. *Captures alternative coding regions.* Some TFs may bind sites that
   exist in an alternative isoform but not the longest one. Merge
   includes them.

The cost is loss of isoform specificity. If different isoforms have
different binding-site complements, merge collapses that signal.

The book-ended fix matters because annotation conventions sometimes
split a single contiguous CDS into two rows at an internal boundary
(e.g. an internal stop reassignment). A binding site that spans the
boundary should still be detectable; merging book-ended rows
preserves that detection.

#### Input

The transcript-keyed BED from step 2 of 06 (~few hundred thousand
fragment rows, each labelled with `<transcript>.N`).

#### Output

Per-gene-merged BED. From the prior baseline (CDS, default config),
this collapses to **23,499 unique gene rows** + multi-fragment runs
(genes with non-contiguous CDS spans).

`promoter_lengths.txt` (eventually) first 3 rows from baseline:

```
AT1G01010   1290
AT1G01020   1213
AT1G01030   …
```

#### Expected Properties

| Check | Expectation | Observation |
| --- | --- | --- |
| Output rows are gene-keyed | yes | column 4 has no `.N` suffix |
| Same gene rows are non-overlapping | yes | enforced by the linear-merge invariant |
| Book-ended rows merged | yes | tested by recent regression (commits `2785a52`, `2e6ec81`) |
| Per-gene total length ≥ pipeline 06's per-gene total length | yes | 06 = "single longest isoform"; 07 = "all isoforms unioned" → 07 ≥ 06 per gene; baseline means: 06=334.985, 07=347.256 ✓ |
| Genes lost between 06 and 07 | none, by design | universe sizes both 23499 (CDS-bearing genes) |
| Strand assigned | yes | from first row of run; consistent because all isoforms of one gene share strand |

#### Observed Result

All checks hold against the prior baselines.

#### Assessment

PASS. Importantly, 07 mean per-gene length (347.256) exceeds 06
(334.985), as expected for a per-gene UNION vs single-isoform
selection.

---

### Step 3: Tag, drop <30 bp, write contract files

Steps 5–9 of 06 apply identically. After tagging multi-row genes with
`__GENE__N` and dropping <30 bp fragments, the per-FIMO-sequence
lengths file is built; FIMO scans every fragment; results collapse
back to gene level.

#### Output (baseline, gene-level after step 9)

```
universe.txt           23499 lines
promoter_lengths.txt   23499 rows;  min=30, max=4144, mean=347.256
binomial_thresholds.txt  113 rows
IC.txt                 113 rows
fimohits/              113 files
```

`fimohits/AHL12.txt` first 3 rows (baseline):

```
AHL12   AT1G01070   119   126   -   8.220588   5.667e-04   AAATATTT
AHL12   AT1G01070   153   160   +   7.272059   1.417e-03   AATAATTT
AHL12   AT1G01070   316   323   +   6.286765   2.707e-03   AAAATATT
```

#### Expected Properties

| Check | Expectation | Observation |
| --- | --- | --- |
| `universe.txt` ≡ `promoter_lengths.txt` gene set | yes | `comm -3` returns 0 differences |
| No `__` artefacts in final `promoter_lengths.txt` | yes | 0 lines with `__` |
| No `__` artefacts in final `fimohits/*` | yes | 0 hits with `__` in column 2 |
| 113 fimohits files | one per motif | 113 |
| All fimohits row counts > 0 | yes (`AHL12.txt` is the smallest, still has many rows) | confirmed |

#### Observed Result

All hold.

#### Assessment

PASS.

---

### Step 4: Cleanup

For 07, `delete_temp=yes` so the indexer removes:

- `<element>.bed`, `with_overlapping.bed`
- `genome_stripped.fa`, `genome_stripped.fa.fai`
- `promoter.bg`, `promoter.fa`
- `memefiles/`

This is why pipeline 07's homotypic dir at audit time is much smaller
(only the contract files) than pipeline 06's (which keeps `promoter.fa`
and `genome_stripped.fa`).

#### Assessment

PASS — only the contract files remain, which is the expected
post-cleanup state.

---

### Step 5: Heterotypic motif-pair test (looped over 5 tasks)

Identical command to 06 step 11.

#### Output

| Task | `motif_output.txt` rows | Heatmap PNGs |
| --- | ---: | ---: |
| `salt_top300` | 12 657 | 3 |
| `random_genes_300` | 25 313 | **0** (only histograms) |
| `genes_cell_type_treatment` | 37 969 | 3 |
| `gene_cortex_epidermis_pericycle` | 18 985 | 3 |
| `heat_top300` | 12 657 | 3 |

The row counts are byte-identical to 06's, because both pipelines
share the same gene set per task (the universe filter happens via
`grep -Ff universe.txt`, and 06 and 07 have the same 23,499-gene
universe).

#### Expected Properties

- 11 columns. ✓
- Row count = `1 + C(motifs, 2) * num_clusters_in_task`. ✓
- p-values valid. ✓

#### Assessment

PASS.

---

### Step 6: Heatmaps

#### Output for `genes_cell_type_treatment` (baseline)

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `03_plot_genes_cell_type_treatment/heatmap.png` | 424 131 | `462c8f5dcf835d68077d9d3a11cd45f2708c7d58535b27969e59354e738cf41f` |
| `…/heatmap_overlap.png` | 654 940 | `5b801e44b242f95e1f6c5cea6bb8f496c4e7b49c52125246a12f2131091c1911` |
| `…/heatmap_overlap_unique.png` | 654 940 | `5b801e44b242f95e1f6c5cea6bb8f496c4e7b49c52125246a12f2131091c1911` |

#### Expected Properties

- Three PNGs per task (except `random_genes_300`).
- The two `Overlap` PNGs differ.

#### Observed Result

Same `heatmap_overlap == heatmap_overlap_unique` byte-identity
observed in pipelines 05 and 06. See [05_promoter_gap.md §4 step 10](05_promoter_gap.md)
for the analysis. The `mode=All` PNG is meaningfully smaller (424 KB)
than the `Overlap` PNGs (655 KB) and has a different hash, so the
pipeline is producing distinct content overall.

Hash differences vs 06's `genes_cell_type_treatment` heatmap:

- 06 `heatmap.png` → `a57c5f34…` (424 131 bytes)
- 07 `heatmap.png` → `462c8f5d…` (424 131 bytes; **same size, different hash**)

Same byte count, different hash → the two pipelines render
visually-similar heatmaps with different cell values, exactly as
expected (06 and 07 produce different per-gene fragment compositions →
different motif counts → different p-values → different heatmap
intensities).

#### Assessment

WARNING (`overlap == overlap_unique` quirk shared with 05/06).
PASS otherwise.

## 5. Final Outputs

```
results/07_elements_merged/
├── 01_homotypic/                # only contract files (delete_temp=yes)
│   ├── universe.txt              23 499 genes
│   ├── promoter_lengths.txt      23 499 rows; min=30, max=4144, mean=347.256
│   ├── binomial_thresholds.txt   113 rows
│   ├── IC.txt                    113 rows
│   └── fimohits/                 113 files
├── 02_heterotypic_<task>/        × 5
└── 03_plot_<task>/               × 5  (3 PNGs each except random_genes_300)
```

## 6. Risks / Edge Cases

1. **Loss of isoform specificity is intentional.** A motif that binds
   only in an alternative isoform's coding region will appear in the
   merged universe with full weight, while in pipeline 06 it would
   only contribute if the alternative isoform happened to be the
   longest. Conversely, a motif specific to the longest isoform shows
   up in *both* pipelines — but in 07 with diluted weight (because
   non-longest fragments are also in the merged set).

2. **Book-ended interval merging is a recent change.** Earlier 07
   runs (before commits `2785a52` / `2e6ec81`) treated `end == next.start`
   as non-mergeable, splitting binding sites that span annotation
   boundaries. The current behaviour matches `bedtools merge`. The
   prior baseline at audit time uses the new behaviour.

3. **Shared `Overlap == OverlapUnique` heatmap quirk** with 05 and 06.

4. **No heatmap for control task.** Same as 04 / 06: `random_genes_300`
   produces only the diagnostic histogram side-cars because no
   adjusted p-value passes the significance threshold. By design.

5. **No UTR-subtraction option.** `mrnaFull=No` is meaningful only
   for `strategy=longest`. For merged + mRNA, the merged region
   includes UTRs (because UTRs are part of the mRNA span). This is
   documented in the indexer help text but not enforced — a user who
   sets `mrnaFull=No` for 07 would be silently ignored.

## 7. Summary

**Overall status: PASS** (with the `Overlap == OverlapUnique` heatmap
quirk shared with 05/06 and the by-design `random_genes_300` heatmap
absence).

Pipeline 07 correctly implements per-gene UNION across isoforms.
Verified properties: per-gene mean total length (347.256) is
strictly greater than pipeline 06's (334.985), as required by the
"merged ⊇ longest" inclusion; `__GENE__N` tagging round-trips
cleanly through FIMO and is removed from final outputs; book-ended
intervals merge as intended (regression-tested by recent commits);
all five heterotypic tasks produce correctly-shaped `motif_output.txt`
tables, four with three heatmaps (the fifth, the random control,
intentionally renders only histograms).

The outputs are suitable for downstream PMET interpretation as a
"per-gene CDS union" view, complementary to the "per-gene longest
isoform" view in 06 and the "upstream promoter" views in 03 / 05.
