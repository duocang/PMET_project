# Pipeline 04: Interval-Based PMET Analysis

Script: [scripts/pipeline/04_intervals.sh](../../scripts/pipeline/04_intervals.sh)

> **2026-04-28 update — structure refactored**
> The homotypic stage was previously delegated to a separate
> `scripts/indexing/intervals.sh` wrapper. That file has been deleted
> and its logic inlined into `scripts/pipeline/04_intervals.sh` to
> mirror `pmet_shiny_app/scripts/pipeline/intervals_index_pair.sh` and
> ease cross-project diff. The heterotypic engine is now `build/pair_parallel`
> (legacy `pmetParallel` no longer ships in `build/`). Section 4's
> step-by-step text below still describes each stage correctly, but
> the line-anchored links into `intervals.sh` are stale — read them
> as descriptions of what now lives inside `04_intervals.sh`.

## 1. Pipeline Purpose

Run PMET on a user-supplied set of pre-extracted DNA *intervals*
(arbitrary genomic regions), without any GFF3 / promoter construction.
Use case: you already have your regions of interest as a FASTA
(e.g. ATAC peaks, conserved blocks, custom promoter calls), and you
want to test motif co-occurrence among a labelled subset of those
intervals.

The "gene" abstraction is replaced by an **interval id** (typically
`<chrom>:<start>-<end>(+/-)`). Everywhere downstream where pipeline 03
talks about "genes", pipeline 04 talks about intervals — the
contract is identical, only the semantics shift.

## 2. Inputs

| File | Biological meaning | Format | Truncated sample |
| --- | --- | --- | --- |
| `data/homotypic_intervals/intervals.fa` | the universe — all intervals that FIMO will scan | FASTA, 2717 records | `>1:2631-3760(+)` then DNA |
| `data/homotypic_intervals/motif_more.meme` | 8 plant MYB motifs | MEME v5.4.1 | `MOTIF ` lines × 8 |
| `data/homotypic_intervals/intervals.txt` | the heterotypic test set: cluster label + interval id | `<cluster> <interval_id>`, 17 rows, 1 cluster (`U`) | `U 1:2631-3760(+)` |
| `scripts/indexing/intervals.sh` | homotypic shell wrapper for intervals | bash | n/a |
| `build/pmetParallel` | heterotypic engine | binary | n/a |

The 17-row test set is a tiny smoke fixture (one cluster `U`); the
homotypic FASTA covers ~2.7 K intervals, large enough to compute
realistic binomial thresholds.

## 3. Output Contract

```
results/04_intervals/
├── 01_homotypic/
│   ├── universe.txt
│   ├── promoter_lengths.txt
│   ├── binomial_thresholds.txt
│   ├── IC.txt
│   └── fimohits/<motif>.txt
└── 02_heterotypic/
    └── motif_output.txt
```

Note: pipeline 04 does **not** produce the three named heatmap PNGs
of pipeline 03. The R call is wired (`scripts/pipeline/04_intervals.sh:95-102`)
to write a single `heatmap.png` under `02_heterotypic/`, but at audit
time only the histogram side-car (`02_heterotypic/histogram/histgram_padj_before_filter.png`,
note typo) is present, not the named heatmap. See §6.

## 4. Step-by-Step Execution Story

The homotypic stage of pipeline 04 is `scripts/indexing/intervals.sh`,
not `run_homotypic.py`. Reading the wrapper end-to-end:

### Step 1: Sanitise FASTA headers (colon → `__COLON__`)

#### Command / Code Path

```text
sed 's/^\(>.*\):/\1__COLON__/g' intervals.fa > intervals_temp.fa
```
([intervals.sh:144-145](../../scripts/indexing/intervals.sh#L144-L145))

#### Purpose

FIMO mis-parses sequence names containing `:` (interpreted as
field separators). Replace temporarily; restore at step 6.

#### Bioinformatics Meaning

None; pure FIMO compatibility shim.

#### Expected Properties

After replacement, no `:` in any FASTA header line.

#### Assessment

PASS (verified: temporary file is removed after FIMO so cannot be
re-inspected, but the `^>` lines in the final `fimohits/*.txt` are
restored to the original `<chrom>:<start>-<end>(+/-)` form).

---

### Step 2: Deduplicate FASTA

#### Command / Code Path

```text
python3 scripts/python/deduplicate.py intervals_temp.fa no_duplicates.fa
python3 scripts/python/parse_promoter_lengths_from_fasta.py \
    no_duplicates.fa promoter_lengths.txt
cut -f1 promoter_lengths.txt > universe.txt
```
([intervals.sh:155-167](../../scripts/indexing/intervals.sh#L155-L167))

#### Purpose

Drop FASTA records whose header is a duplicate; derive
`promoter_lengths.txt` (interval id, length) and `universe.txt`
(interval id only) directly from the FASTA.

#### Bioinformatics Meaning

In the interval pipeline the FASTA itself *is* the gene set. There is
no GFF3 to consult. Length is sequence length, not promoter window
length. So the contract files are computed from the FASTA, not from
genomic coordinates.

#### Input

`intervals_temp.fa` — 2717 records (1 ± duplicate to test the dedup
step).

#### Output

```
universe.txt          2716 lines
promoter_lengths.txt  2716 rows
```

`universe.txt` first 3:

```
1:2631-3760(+)
1:8666-10130(-)
1:12940-14714(-)
```

`promoter_lengths.txt` first 3:

```
1:2631-3760(+)    1129
1:8666-10130(-)   1464
1:12940-14714(-)  1774
```

#### Expected Properties

| Check | Expectation | Observation |
| --- | --- | --- |
| Universe count ≤ FASTA count | yes | 2716 ≤ 2717 (1 duplicate dropped) |
| `universe.txt` ⊇ all `intervals.txt` ids | required by heterotypic step | `comm -23 intervals.txt univ` returns 0 |
| `length > 0` | yes | 0 violations, min=4, max=3517, mean=899 |
| length matches FASTA seq length | yes | by construction |
| Universe set ≡ promoter_lengths gene set | yes | `comm -3` returns 0 |

#### Observed Result

Counts and consistency all hold.

#### Assessment

PASS, with one **WARNING**: the minimum length is 4 bp (the FASTA does
contain a near-empty record). Most TF motifs are 6–14 bp, so a 4 bp
sequence cannot host any motif and silently consumes budget. Pipeline
04 does not filter short intervals (in contrast to 03's lt10/lt20
filters and 06/07's lt30 filter).

---

### Step 3: Background model + per-motif IC

#### Command / Code Path

```text
fasta-get-markov intervals_temp.fa > genome.bg
python3 scripts/python/parse_memefile.py            motif_more.meme memefiles/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py memefiles/ IC.txt
```
([intervals.sh:179-192](../../scripts/indexing/intervals.sh#L179-L192))

#### Purpose

`genome.bg` calibrates FIMO p-values against the *interval set's* base
composition (not the whole genome). `IC.txt` is the per-position info
content for heterotypic overlap weighting.

#### Output

```
genome.bg   5 rows  (0-order Markov: A,C,G,T plus header)
IC.txt      8 rows  (one per motif)
```

`IC.txt` first row:

```
MYB59 0.6150 1.3066 1.6431 1.2789 1.6761 1.6236 1.4806 0.4734
```

#### Expected Properties

- `IC.txt` has exactly `nummotifs` (8) rows.
- All IC values ∈ [0, 2].

#### Observed Result

Both hold.

#### Assessment

PASS.

---

### Step 4: FIMO + PMETindex per batch

#### Command / Code Path

```text
build/index_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile genome.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<motif>.txt intervals_temp.fa promoter_lengths.txt
```
([intervals.sh:203-219](../../scripts/indexing/intervals.sh#L203-L219))

Note: pipeline 04 does **not** use `parse_memefile_batches.py`; each
motif is one file (since there are only 8 motifs and the pipeline
runs single-threaded by default). Parallelism is `& wait` over batches
of `threads` motifs ([intervals.sh:202-220](../../scripts/indexing/intervals.sh#L202-L220)).

#### Purpose

Same dual-purpose call as in pipeline 03 — produce `fimohits/*.txt`
plus `binomial_thresholds.txt` in one binary invocation.

#### Output

```
fimohits/   8 files
binomial_thresholds.txt   8 rows
```

`fimohits/MYB111_2.txt` first 3 rows (after `__COLON__ → :` restoration
at step 6 below):

```
MYB111_2  1:7770659-7771897(+)   75    82    +   1.4961538460e+01  8.4661721950e-06
MYB111_2  1:7770659-7771897(+)   1114  1121  +   1.4961538460e+01  8.4661721950e-06
MYB111_2  1:7770659-7771897(+)   679   686   +   1.0125000000e+01  1.2063574980e-04
```

`binomial_thresholds.txt`:

```
MYB111_2  9.953298312e-01
MYB111    9.996405678e-01
MYB46_2   9.975487412e-01
```

#### Expected Properties

| Check | Expectation | Observation |
| --- | --- | --- |
| Number of fimohits files | 8 (motif count) | 8 |
| Number of binomial threshold rows | 8 | 8 |
| FIMO p-value ≤ 0.05 | enforced by `--thresh 0.05` | min ≈ 4.2e-06, max ≈ 0.0498 |
| Hit's seq id ∈ universe | yes | sampled, all rows reference ids in `universe.txt` |

#### Observed Result

All hold.

#### Assessment

PASS, with one **WARNING**: the binomial thresholds are very high
(≈ 0.99) compared to pipeline 03 (≈ 1e-3). This is consistent with a
small universe (2716 intervals × 1 kb mean length ≈ 2.7 Mb effective
search space, vs ~30 Mb of promoter sequence in pipeline 03):
the binomial null is much weaker, so almost any hit is "significant".
The downstream pair_parallel `-i 4` IC threshold is the actual filter
that prevents this from producing noise.

---

### Step 5: Restore `:` in FASTA ids

#### Command / Code Path

```text
sed 's/__COLON__/:/g' fimohits/*.txt
sed 's/__COLON__/:/g' promoter_lengths.txt
sed 's/__COLON__/:/g' universe.txt
rm intervals_temp.fa
```
([intervals.sh:223-231](../../scripts/indexing/intervals.sh#L223-L231))

#### Purpose

Reverse the step-1 sanitisation so that downstream consumers see the
original `chrom:start-end(strand)` ids.

#### Expected Properties

No `__COLON__` remains in any of the contract files.

#### Observed Result

`grep __COLON__ universe.txt promoter_lengths.txt fimohits/*.txt` →
no matches.

#### Assessment

PASS.

---

### Step 6: Homotypic contract validation

#### Command / Code Path

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```
([intervals.sh:256](../../scripts/indexing/intervals.sh#L256))

#### Output

`OK` (8 motifs, 2716 universe intervals).

#### Assessment

PASS.

---

### Step 7: Heterotypic motif-pair test

#### Command / Code Path

```text
build/pmetParallel \
    -d . -g intervals.txt -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/04_intervals/02_heterotypic -t 1
```
([04_intervals.sh:80-89](../../scripts/pipeline/04_intervals.sh#L80-L89))

Note: pipeline 04 uses **`pmetParallel`** (older binary), whereas 03 /
05 use **`pair_parallel`** (the fused replacement). Output format is
identical.

#### Purpose

Test motif-pair co-enrichment within cluster `U` against the global
2716-interval background.

#### Bioinformatics Meaning

The "gene" column actually holds an interval id. Reading
`motif_output.txt` requires understanding that a "gene in cluster" is
an interval in cluster.

#### Input

`intervals.txt` — 17 rows, single cluster `U`. (One row appears
twice, hence the heterotypic step sees 18 unique entries — see "N_in_cluster=18"
in the output.)

#### Output

`motif_output.txt` — 11 columns, 29 rows = 1 header + 28 motif pairs
= C(8,2) = 28 pairs × 1 cluster.

```
Cluster  Motif 1   Motif 2     ...
U        MYB111    MYB111_2    0  0  18  1  1  1  1
U        MYB111    MYB46       0  0  18  1  1  1  1
```

#### Expected Properties

- 11 columns. ✓
- `1 + C(8,2) * num_clusters = 1 + 28 = 29` rows. ✓
- All raw p-values ∈ [0, 1]. ✓

#### Observed Result

For every pair the "Number of genes in cluster with both motifs" is
0, and every adjusted p-value is 1. This is consistent with the test
fixture being intentionally tiny — the 17 intervals are a smoke-test
set, not a real biological cluster.

#### Assessment

PASS structurally, **WARNING** scientifically: with this fixture there
is nothing to discover; the run is a contract / wiring test only.

---

### Step 8: Heatmap

#### Command / Code Path

```text
Rscript scripts/r/draw_heatmap.R \
    Overlap heatmap.png motif_output.txt 5 3 6 FALSE
```
([04_intervals.sh:95-102](../../scripts/pipeline/04_intervals.sh#L95-L102))

#### Output (observed)

```
results/04_intervals/02_heterotypic/
├── motif_output.txt
└── histogram/
    └── histgram_padj_before_filter.png   23892 bytes
```

The intended `heatmap.png` is **not** present. `draw_heatmap.R`
appears to short-circuit when there is nothing significant to plot
(every adjusted p-value is 1) and writes only the diagnostic
histogram side-car. The histogram name has a typo (`histgram` for
`histogram`) — not a 04 issue, lives inside `draw_heatmap.R`.

#### Expected Properties

- `heatmap.png` exists.

#### Observed Result

`heatmap.png` does **not** exist; only the histogram side-car.

#### Assessment

WARNING. The pipeline does not raise an error when the heatmap is
empty / un-renderable. Not strictly a 04 bug — it's the R script's
behaviour on a degenerate input — but consumers who expect the
canonical PNG name will get a missing-file error. Documented here so
that the smoke fixture does not surprise anyone.

## 5. Final Outputs

```
results/04_intervals/
├── 01_homotypic/
│   ├── universe.txt              2716 intervals
│   ├── promoter_lengths.txt      2716 rows
│   ├── binomial_thresholds.txt   8    rows
│   ├── IC.txt                    8    rows
│   ├── genome.bg                 4-base markov background
│   ├── memefiles/                8 per-motif MEME splits (kept on disk)
│   └── fimohits/                 8    files
└── 02_heterotypic/
    ├── motif_output.txt          29 rows (1 header + 28 pairs × 1 cluster)
    └── histogram/histgram_padj_before_filter.png   23 KB
```

## 6. Risks / Edge Cases

1. **No short-interval filter.** A 4 bp interval is in the universe. It
   cannot match any motif but adds noise to the binomial threshold
   denominator. Recommendation (not implemented here): drop intervals
   shorter than the longest motif.

2. **Headers re-encoded as `__COLON__` in transit.** If any external
   process writes into `fimohits/` between steps 4 and 5, the restoration
   sed-pass might leave behind hybrid ids. Low risk in practice but
   worth knowing.

3. **`memefiles/` and `genome.bg` are kept on disk** post-run (the
   pipeline does not clean them up). They consume ~30 KB total — not a
   space issue but inconsistent with 03/05 which clean up by default.

4. **Heatmap silently absent on degenerate input.** The R script
   produces a histogram side-car instead of `heatmap.png` when the
   adjusted p-values are all 1. The pipeline exit code is still 0.

5. **Test fixture is too small to be biologically meaningful.** All
   adjusted p-values in `motif_output.txt` are 1. This is by design —
   the fixture is a wiring test — but documents are clear that the
   numerical output should not be interpreted.

## 7. Summary

**Overall status: PASS (structural) / NOT MEANINGFUL (scientific).**
Pipeline 04 produces a valid homotypic index and a structurally valid
`motif_output.txt` from a small interval-based fixture. All file-shape
invariants hold. The fixture is a smoke-test, not a real experiment;
its outputs are not meant to be interpreted as biology.

The pipeline itself is correct: contract files conform, FIMO p-values
respect the threshold, IC and binomial outputs are well-formed,
strand-aware sequence ids round-trip through the `__COLON__` shim.
Two soft issues to flag for users: the absence of a final heatmap on
degenerate input, and the lack of a short-interval filter.
