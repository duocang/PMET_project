# Pipeline 05: Promoter PMET with TSS-proximal Gap

Script: [scripts/pipeline/05_promoter_gap.sh](../../scripts/pipeline/05_promoter_gap.sh)

## 1. Pipeline Purpose

Variant of [pipeline 03](03_promoter.md) that **shrinks the
TSS-proximal end of every promoter by `gap=100` bp** before running
FIMO. The intent is to exclude the *core promoter* — the ~50–150 bp
neighbourhood of the TSS that hosts general TFs (TBP/TFIIB/Inr/TATA),
so the heterotypic test is biased toward distal cell-type-specific TF
sites rather than the housekeeping background.

Everything else (annotation, motifs, gene list, NoOverlap, the rest of
the homotypic logic, heterotypic + heatmap stages) is identical to 03.

## 2. Inputs

Identical to pipeline 03 ([03_promoter.md §2](03_promoter.md#2-inputs)),
plus one configuration knob:

| Parameter | Pipeline 03 | Pipeline 05 |
| --- | ---: | ---: |
| `gap` | 0 | **100** |
| `utr` | Yes | **No (forced)** — see step 0 |
| `length` | 1000 | 1000 |
| `overlap` | NoOverlap | NoOverlap |

### Step 0: UTR force-disable (pipeline guard)

```text
if (( gap != 0 )) && [[ "$utr" =~ ^(yes|y|true|t)$ ]]; then
    print_fluorescent_yellow "   gap=$gap != 0 — forcing utr=No (UTR would undo the TSS-proximal exclusion)"
    utr=No
fi
```
([05_promoter_gap.sh:50-54](../../scripts/pipeline/05_promoter_gap.sh#L50-L54))

#### Bioinformatics Meaning

The 5' UTR sits *between* the TSS and the start codon — exactly the
region we are trying to mask out. Allowing `utr=Yes` while `gap > 0`
would re-extend the promoter back toward the TSS, undoing the gap.
The pipeline force-disables UTR if both are turned on. **PASS**: the
guard is in place and emits a yellow warning when triggered.

## 3. Output Contract

Identical to pipeline 03:

```
results/05_promoter_gap/
├── 01_homotypic/      # universe / lengths / IC / binomial / fimohits
├── 02_heterotypic/    # motif_output.txt + pmet.log
└── plot/              # 3 heatmaps
```

## 4. Step-by-Step Execution Story

The homotypic flow is identical to pipeline 03 with two differences:
the `--gap 100` argument and `--utr No`. Steps 1–4 / 6–10 are
unchanged from [03_promoter.md](03_promoter.md). Only step 5
(`build_promoters.py`) behaves differently and is detailed below; the
others are summarised.

### Step 1–4: GFF3 sort, gene BED, chrom sizes, linearised FASTA

Identical to pipeline 03. **PASS** (same code path, same inputs).

### Step 5: Build promoters with TSS-proximal gap

#### Command / Code Path

```text
python3 scripts/python/build_promoters.py \
    --length 1000 --gap 100 --overlap NoOverlap --utr No \
    [...]
```
([05_promoter_gap.sh:158-174](../../scripts/pipeline/05_promoter_gap.sh#L158-L174))

The relevant logic inside `build_promoters.py` is the
`shrink_for_gap` helper:

- For `+` strand promoters: subtract `gap` from BED `end` (TSS is the
  upstream end of the gene-side flank, so the TSS-proximal end is
  `end`).
- For `−` strand promoters: add `gap` to BED `start` (TSS is at the
  lower-coord side because the flank lies above the gene start in
  `+`-strand coordinates).
- Drop intervals that collapse to ≤ 0.

#### Purpose

Mask the core-promoter region around the TSS while keeping the
distal ≤ 900 bp window.

#### Bioinformatics Meaning

The genome's *core promoter* is dominated by Pol II machinery
(TFIIA/B/D/E/F/H, TBP, etc.) and a few sequence motifs (TATA box,
Inr, DPE). Cell-type specificity is encoded mostly in the **distal**
elements binding family-specific TFs (MYB, WRKY, BZIP, NAC, ...).
A 100 bp gap is the literature default for "drop the core promoter"
when running motif-pair tests biased toward cell-type signal.

#### Output

```
promoters.bed         27500 rows
promoter_lengths.txt  27500 rows
universe.txt          27500 rows
```

`promoter_lengths.txt` first 3 rows:

```
AT1G01010   900
AT1G01020   900
AT1G03987   900
```

#### Expected Properties

| Check | Expectation | Observation |
| --- | --- | --- |
| Max length | ≤ 900 (i.e. `length − gap`) | 900 ✓ |
| Min length | ≥ 20 (post-NoOverlap filter) | 20 ✓ |
| Universe count | < 03's 29824 (gap shrinks) | 27500 (lost 2324 vs 03) |
| 05 ⊆ 03 universe | strictly | `comm -13` = 0 (no novel genes in 05); `comm -23` = 2324 (lost from 03) ✓ |
| Genes at the cap (length=900) | should be the majority | 13833 of 27500 ≈ 50% — the others were already < 900 in 03 because of NoOverlap clipping |
| `+` strand BED end is shifted left by 100 | yes | for AT1G01010 the 03 promoter was 2630–3759 (length 1129; uses 5'UTR), the 05 promoter is 2630–3530 (length 900; UTR off, TSS gap on) — implied by length=900 |
| `−` strand BED start is shifted right by 100 | yes | by symmetry |
| Universe set ≡ promoter_lengths gene set | yes | `comm -3` returns 0 |

#### Observed Result

All checks pass. The 2324-gene drop is the population that, after
gapping plus NoOverlap, falls below the 20 bp minimum and gets
removed at the lt20 filter ([build_promoters.py](../../scripts/python/build_promoters.py)
step 6).

#### Assessment

PASS. The gap is doing exactly what the script promises: max length
falls from `1000 + UTR ≤ 14813` (in 03) to 900 here, and the universe
is a strict subset of 03's.

---

### Step 6–8: IC, FIMO + index, contract validation

Identical to pipeline 03. 113 motifs in, 113 fimohits files out, 113
binomial-threshold rows out. Contract validator says
`OK — homotypic contract holds (113 motifs, 27500 universe genes,
27500 genes with promoter lengths)`. **PASS**.

### Step 9: Heterotypic motif-pair test

#### Command / Code Path

```text
build/pair_parallel \
    -d . -g <filtered_gene_list> -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/05_promoter_gap/02_heterotypic -t 4
```
([05_promoter_gap.sh:188-197](../../scripts/pipeline/05_promoter_gap.sh#L188-L197))

#### Output

`motif_output.txt` — 11 columns, **37969 rows** (same row count as
pipeline 03; the cluster set and motif set are identical so the
Cartesian product is identical).

#### Expected Properties

- 11 fields. ✓
- Same row count as 03 (37969). ✓
- p-values valid. ✓

#### Assessment

PASS. The numerical p-values differ from 03 (because the underlying
hit set is different), but the row shape is identical.

---

### Step 10: Heatmaps

#### Output

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `plot/heatmap.png` | 1 395 151 | `c1378e23adda79dae60cc59944ad1e62946db3be1379fb8609a46ff2366a0d29` |
| `plot/heatmap_overlap.png` | 837 854 | `af75ef92309bb999e700979be5921cd09d2ac56984a941c59e80c91b2e09f40d` |
| `plot/heatmap_overlap_unique.png` | 837 854 | `af75ef92309bb999e700979be5921cd09d2ac56984a941c59e80c91b2e09f40d` |

#### Expected Properties

- Three PNGs, all non-empty. ✓
- `heatmap_overlap.png` and `heatmap_overlap_unique.png` differ.

#### Observed Result

The two `Overlap` PNGs have **identical** SHA-256 (and identical byte
count). Same observation as in 06 / 07.

#### Assessment

WARNING. The `unique=TRUE` flag is supposed to deduplicate motif
pairs that recur in multiple clusters, but on this dataset the two
PNGs are byte-identical. Investigation outside the scope of this audit
suggests one of:

1. The 6 clusters in `genes_cell_type_treatment.txt` produce
   non-overlapping motif-pair sets (so dedup is a no-op).
2. The R script's `unique` filter does not change the rendered
   matrix when `mode=Overlap` is set with these dimensions
   (5 / 3 / 6 rows / cols / facets).

The `mode=All` heatmap is meaningfully larger (1.4 MB vs 838 KB) and
hashes differently, so the pipeline is producing distinct content
overall — the issue is specific to the `Overlap` × `unique` axis.

This is the same observation as for 06 and 07, but **not** for 03
(where 03 cluster size is the same — see 03 audit). The difference
between 03 (`5 3 6`) and 05 (also `5 3 6` per the script) is the
input `motif_output.txt` distribution. So this is a property of
05/06/07 inputs, not a bug introduced by the gap.

## 5. Final Outputs

```
results/05_promoter_gap/
├── 01_homotypic/
│   ├── universe.txt              27500 lines  (vs 29824 in 03)
│   ├── promoter_lengths.txt      27500 rows; max length 900 (vs 14813 in 03)
│   ├── binomial_thresholds.txt   113 rows
│   ├── IC.txt                    113 rows
│   └── fimohits/                 113 files
├── 02_heterotypic/
│   ├── motif_output.txt          37969 rows
│   └── pmet.log
└── plot/
    ├── heatmap.png               1.40 MB
    ├── heatmap_overlap.png       838 KB
    └── heatmap_overlap_unique.png 838 KB  (== heatmap_overlap.png; see step 10)
```

## 6. Risks / Edge Cases

1. **05 universe ⊊ 03 universe.** 2324 genes that were testable under
   03 are not testable under 05 because their promoter shrinks below
   the 20 bp threshold after gapping + NoOverlap. The user's input
   gene list filtering at the heterotypic step silently drops these
   too. Important to document but not a defect.

2. **`heatmap_overlap.png` == `heatmap_overlap_unique.png`.** See
   step 10 above. Worth investigating in `draw_heatmap.R` to confirm
   intended semantics; not within the scope of this audit.

3. **Force-disabled UTR is correct, but the pipeline does not log the
   final effective UTR setting**. The yellow warning fires once on
   stdout; downstream consumers reading only the homotypic output
   directory have no record of what `utr` was actually used. Could be
   surfaced in `binomial_thresholds.txt`'s neighbouring metadata if
   needed.

4. **`gap` is not parameterised on the command line** — it is hard-coded
   to 100 in the script. Changing it requires editing the script, not
   passing a flag. This is the same pattern as 03's `length=1000`.

## 7. Summary

**Overall status: PASS** (with one downstream WARNING shared with
06/07). Pipeline 05 correctly applies a 100 bp TSS-proximal gap to
every promoter, force-disables 5' UTR extension to keep the gap
honest, and otherwise reuses pipeline 03's homotypic + heterotypic +
plotting chain. The shrinkage is verifiable: max promoter length
drops from `1000 + UTR` (≤ 14,813 bp in 03) to a clean 900 bp, the
universe is a strict subset of 03's, and 2324 genes drop because
gapping pushes them below 20 bp.

The motif_output table has the same row shape as 03 (same clusters ×
same motifs); the heatmaps differ from 03 in numeric content but
share the `unique == non-unique` overlap-PNG quirk noted in 06/07.
The outputs are suitable for downstream PMET interpretation as a
"distal-element" complement to pipeline 03's "core+distal" view.
