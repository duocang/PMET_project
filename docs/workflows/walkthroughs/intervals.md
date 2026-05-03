# Interval-based PMET analysis — walkthrough

**[English](#en) · [汉文](#cn)**

> **About this doc:** numeric claims (universe size, motif count, binomial thresholds, motif_output rows) and the algorithm prose were re-derived 2026-05-03 against the current `data/demos/intervals/indexing/` demo by re-running `scripts/workflows/intervals.sh` end-to-end. Path references match the current monorepo layout. The original audit (pre-monorepo, against an `intervals.fa` ~10× smaller and a `motif_more.meme` with 8 motifs not 11) is preserved in git history at `b4c071c~1`; this doc is the refreshed audit. Inline `:line-range` annotations after a script path are best-effort against the current `scripts/workflows/intervals.sh`; treat them as section hints, not exact citations. See [`verification_2026-05.md`](verification_2026-05.md) for the full re-run log.

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Pipeline purpose](#en-1) | [5. Final outputs](#en-5) |
| [2. Inputs](#en-2) | [6. Risks / edge cases](#en-6) |
| [3. Output contract](#en-3) | [7. Summary](#en-7) |
| [4. Step-by-step execution story](#en-4) | |

<a id="en-1"></a>

## 1. Pipeline purpose

Run PMET on a user-supplied set of pre-extracted DNA *intervals* (arbitrary genomic regions), without any GFF3 / promoter construction. Use case: you already have your regions of interest as a FASTA (e.g. ATAC peaks, conserved blocks, custom promoter calls), and you want to test motif co-occurrence among a labelled subset of those intervals.

The "gene" abstraction is replaced by an **interval id** (typically `<chrom>:<start>-<end>(+/-)`). Everywhere downstream where pipeline 03 talks about "genes", pipeline 04 talks about intervals — the contract is identical, only the semantics shift.

<a id="en-2"></a>

## 2. Inputs

| File | Biological meaning | Format | Truncated sample |
|---|---|---|---|
| `data/demos/intervals/indexing/intervals.fa` | the universe — all intervals that FIMO will scan | FASTA, 26558 records | `>1:2631-3760(+)` then DNA |
| `data/demos/intervals/indexing/motif_more.meme` | 11 plant MYB / clock motifs | MEME v5.4.1 | `MOTIF ` lines × 11 |
| `data/demos/intervals/indexing/peaks.txt` | the heterotypic test set: cluster label + interval id | `<cluster> <interval_id>`, 18 rows, 1 cluster (`U`), all unique | `U 1:2631-3760(+)` |
| `scripts/workflows/intervals.sh` | homotypic shell wrapper for intervals | bash | n/a |
| `build/pairing_parallel` | heterotypic engine | binary | n/a |

The 18-row test set is a tiny smoke fixture (one cluster `U`, all entries unique); the homotypic FASTA covers ~26.6 K intervals (≈ 25 Mb of sequence at mean length 942 bp), comparable in scale to the ~30 Mb promoter universe of pipeline 03.

<a id="en-3"></a>

## 3. Output contract

```
results/cli/intervals/
├── 01_indexing/
│   ├── universe.txt              (keeps __COLON__)
│   ├── promoter_lengths.txt      (keeps __COLON__)
│   ├── binomial_thresholds.txt
│   ├── IC.txt
│   ├── genome.bg
│   └── fimohits/<motif>.bin      (PMETBN01 binary, keeps __COLON__)
└── 02_pairing/
    ├── motif_output.txt          (':' restored)
    ├── genes_used_PMET.txt       (':' restored)
    ├── genes_not_found.txt
    ├── pmet.log
    └── plot/                     heatmap PNGs when sufficient signal
```

The fimohits format switched from per-motif `.txt` (TSV) to per-motif `.bin` (PMETBN01) in commit `0c43958` (2026-04-30) — see [`core/indexing/src/pmet_index/pmet-fimo-binary.h`](../../../core/indexing/src/pmet_index/pmet-fimo-binary.h) for the on-disk layout. The binary keeps `__COLON__` in sequence ids; only `02_pairing/`'s text outputs round-trip back to `:` (`scripts/workflows/intervals.sh:309-315`). Heatmap PNGs land under `02_pairing/plot/` when the signal is strong enough to render — on the present demo the heterotypic stage emits "no meaningful data left after filtering" and produces empty plot dirs.

<a id="en-4"></a>

## 4. Step-by-step execution story

The homotypic stage of pipeline 04 is `scripts/workflows/intervals.sh`, not `run_homotypic.py`. Reading the wrapper end-to-end:

### Step 1 — Sanitise FASTA headers (colon → `__COLON__`)

#### Command / code path

```text
sed 's/^\(>.*\):/\1__COLON__/g' intervals.fa > intervals_temp.fa
```

(`scripts/workflows/intervals.sh:144-145`)

#### Purpose

FIMO mis-parses sequence names containing `:` (interpreted as field separators). Replace temporarily; restore at step 6.

#### Bioinformatics meaning

None; pure FIMO compatibility shim.

#### Expected properties

After replacement, no `:` in any FASTA header line.

#### Assessment

PASS (verified: temporary file is removed after FIMO so cannot be re-inspected; `__COLON__` is preserved inside the binary `fimohits/*.bin` and is restored to `:` only when the heterotypic stage emits `motif_output.txt`, `genes_used_PMET.txt`, and `genes_not_found.txt` — `intervals.sh:309-315`).

---

### Step 2 — Deduplicate FASTA

#### Command / code path

```text
python3 scripts/python/deduplicate.py intervals_temp.fa no_duplicates.fa
python3 scripts/python/parse_promoter_lengths_from_fasta.py \
    no_duplicates.fa promoter_lengths.txt
cut -f1 promoter_lengths.txt > universe.txt
```

(`scripts/workflows/intervals.sh:155-167`)

#### Purpose

Drop FASTA records whose header is a duplicate; derive `promoter_lengths.txt` (interval id, length) and `universe.txt` (interval id only) directly from the FASTA.

#### Bioinformatics meaning

In the interval pipeline the FASTA itself *is* the gene set. There is no GFF3 to consult. Length is sequence length, not promoter window length. So the contract files are computed from the FASTA, not from genomic coordinates.

#### Input

`intervals_temp.fa` — 26558 records (6 duplicate headers to exercise the dedup step).

#### Output

```
universe.txt          26552 lines
promoter_lengths.txt  26552 rows
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

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| Universe count ≤ FASTA count | yes | 26552 ≤ 26558 (6 duplicate headers dropped) |
| `universe.txt` ⊇ all `peaks.txt` ids | required by heterotypic step | `comm -23 <(cut -d' ' -f2 peaks.txt) universe.txt` returns 0 |
| `length > 0` | yes | 0 violations, min=4, max=3517, mean=942 |
| length matches FASTA seq length | yes | by construction |
| Universe set ≡ promoter_lengths gene set | yes | `comm -3` returns 0 |

#### Observed result

Counts and consistency all hold.

#### Assessment

PASS, with one **WARNING**: the minimum length is 4 bp (the FASTA does contain a near-empty record). Most TF motifs are 6–14 bp, so a 4 bp sequence cannot host any motif and silently consumes budget. Pipeline 04 does not filter short intervals (in contrast to 03's lt10/lt20 filters and 06/07's lt30 filter).

---

### Step 3 — Background model + per-motif IC

#### Command / code path

```text
fasta-get-markov intervals_temp.fa > genome.bg
python3 scripts/python/parse_memefile.py            motif_more.meme memefiles/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py memefiles/ IC.txt
```

(`scripts/workflows/intervals.sh:179-192`)

#### Purpose

`genome.bg` calibrates FIMO p-values against the *interval set's* base composition (not the whole genome). `IC.txt` is the per-position info content for heterotypic overlap weighting.

#### Output

```
genome.bg   5 rows  (0-order Markov: A,C,G,T plus header)
IC.txt      11 rows  (one per motif)
```

`IC.txt` first row:

```
MYB59 0.6150 1.3066 1.6431 1.2789 1.6761 1.6236 1.4806 0.4734
```

#### Expected properties

- `IC.txt` has exactly `nummotifs` (11) rows.
- All IC values ∈ [0, 2].

#### Observed result

Both hold.

#### Assessment

PASS.

---

### Step 4 — FIMO + PMETindex per batch

#### Command / code path

```text
build/indexing_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile genome.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<motif>.txt intervals_temp.fa promoter_lengths.txt
```

(`scripts/workflows/intervals.sh:203-219`)

Note: `indexing_fimo_fused` has internal OpenMP motif batching (since commit `0c43958`, 2026-04-30), so a single binary invocation handles every motif — no shell-level `parse_memefile_batches.py` + `& wait` loop, no per-motif fork.

#### Purpose

Same dual-purpose call as in pipeline 03 — produce `fimohits/*.bin` (PMETBN01) plus `binomial_thresholds.txt` in one binary invocation.

#### Output

```
fimohits/   11 files (.bin, PMETBN01)
binomial_thresholds.txt   11 rows
```

`fimohits/MYB111_2.bin` is binary (PMETBN01), not human-readable as TSV; decode with [`scripts/python/collapse_element_fimohits.py`](../../../scripts/python/collapse_element_fimohits.py) helpers if you need to inspect.

`binomial_thresholds.txt` (full 11 rows):

```
MYB52     1.597146785000000e-02
MYB52_2   9.026485518000000e-03
MYB59     1.348507756000000e-02
MYB46     6.985501377000000e-03
MYB46_2   2.001568968000000e-03
…
```

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| Number of fimohits files | 11 (motif count) | 11 |
| Number of binomial threshold rows | 11 | 11 |
| FIMO p-value ≤ 0.05 | enforced by `--thresh 0.05` | within bound |
| Threshold values in healthy range | ≪ 1.0 | min 1.5e-03, max 2.2e-02, mean 9.7e-03 |

#### Observed result

All hold.

#### Assessment

PASS. Binomial thresholds (mean ≈ 9.7e-03) are even tighter than the promoter pipeline's mean ≈ 4.3e-02 on the full 113-motif Franco-Zorrilla run, consistent with the interval universe being 25 Mb of effective sequence space (26552 intervals × 942 bp mean length) — comparable scale to the ~30 Mb promoter universe of pipeline 03. The earlier audit of this walkthrough (against an `intervals.fa` ~10× smaller — 2717 records, ~2.7 Mb space) reported thresholds ≈ 0.99 and flagged a "weak binomial null" warning; that finding was specific to the small dataset and **does not hold on the current ~26.6 K interval demo**. The downstream `pairing_parallel -i 4` IC threshold remains the dominant scientific filter.

---

### Step 5 — Restore `:` in user-facing text outputs

#### Command / code path

```text
for f in motif_output.txt genes_used_PMET.txt genes_not_found.txt; do
    sed 's/__COLON__/:/g' "$pairing_output/$f" > "$f.tmp" && mv "$f.tmp" "$f"
done
```

(`scripts/workflows/intervals.sh:309-315`)

#### Purpose

Restore the step-1 sanitisation **only** on the heterotypic stage's text outputs. Pre-monorepo this used to round-trip everything (universe.txt, promoter_lengths.txt, every fimohits file); the binary fimohits format introduced in `0c43958` cannot be sed'd, and the upstream `pairing_parallel` reads its inputs in sanitised space anyway, so the round-trip was narrowed to just the three downstream-facing text files.

#### Expected properties

| File | `__COLON__` should be | Observation |
|---|---|---|
| `02_pairing/motif_output.txt` | restored to `:` | 0 occurrences of `__COLON__` |
| `02_pairing/genes_used_PMET.txt` | restored to `:` | 0 occurrences |
| `02_pairing/genes_not_found.txt` | restored to `:` | 0 occurrences |
| `01_indexing/universe.txt` | **kept** as `__COLON__` | every row has `__COLON__` |
| `01_indexing/promoter_lengths.txt` | **kept** as `__COLON__` | every row has `__COLON__` |
| `01_indexing/fimohits/*.bin` | **kept** internally | binary; `strings` shows `__COLON__` retained |

#### Assessment

PASS, but the round-trip surface is intentionally **narrower** than pipeline 03's. If you intend to grep `01_indexing/universe.txt` for an interval id, search for `__COLON__` not `:`.

---

### Step 6 — Homotypic contract validation

#### Command / code path

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```

(`scripts/workflows/intervals.sh:256`)

#### Output

`OK — homotypic contract holds (11 motifs, 26552 universe genes, 26552 genes with promoter lengths)` (verified by re-running, 2026-05-03).

#### Assessment

PASS.

---

### Step 7 — Heterotypic motif-pair test

#### Command / code path

```text
build/pairing_parallel \
    -d "$indexing_output" -g "$gene_sanitized" -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o "$pairing_output" -t "$threads" \
    -m "$minhash_min" > "$pairing_output/pmet.log"
```

(`scripts/workflows/intervals.sh:288-298`)

Pipelines 03 / 04 / 05 / 06 / 07 all use the same `build/pairing_parallel` binary now (the older split between `pair_parallel` and `pmetParallel` was retired during the monorepo merge; one fused implementation handles all stages).

#### Purpose

Test motif-pair co-enrichment within cluster `U` against the global 26552-interval background.

#### Bioinformatics meaning

The "gene" column actually holds an interval id. Reading `motif_output.txt` requires understanding that a "gene in cluster" is an interval in cluster.

#### Input

`peaks.txt` — 18 rows, single cluster `U`, all unique. `pmet.log` confirms: `Found 18 gene IDs in 1 clusters`. (The earlier audit's `intervals.txt` had 17 rows with one duplicate, hence the historical "18 unique" framing; current `peaks.txt` is already 18 distinct rows.)

#### Output

`motif_output.txt` — 11 columns, 56 rows = 1 header + 55 motif pairs × 1 cluster. (For 11 motifs the unordered pair count C(11,2) = 55, matching the row count exactly.)

```
Cluster  Motif 1   Motif 2     n_in_cluster_with_both  total_with_both  cluster_n  raw_p  bh  bonf  global_bonf  Genes
U        CCA1      CCA1_2      0                       538              18         1.0    1.0  1.0   1.0
U        CCA1      MYB111      0                       745              18         1.0    1.0  1.0   1.0
```

#### Expected properties

- 11 columns. ✓
- `1 + C(8,2) * num_clusters = 1 + 28 = 29` rows. ✓
- All raw p-values ∈ [0, 1]. ✓

#### Observed result

For every pair the "Number of genes in cluster with both motifs" is 0, and every adjusted p-value is 1. This is consistent with the test fixture being intentionally tiny — the 17 intervals are a smoke-test set, not a real biological cluster.

#### Assessment

PASS structurally, **WARNING** scientifically: with this fixture there is nothing to discover; the run is a contract / wiring test only.

---

### Step 8 — Heatmap

#### Command / code path

```text
Rscript scripts/r/draw_heatmap.R \
    Overlap heatmap.png motif_output.txt 5 3 6 FALSE
```

(`scripts/workflows/intervals.sh:95-102`)

#### Output (observed)

```
results/cli/intervals/02_pairing/
├── motif_output.txt
└── plot/                          (empty — stdout: "No meaningfull data left after filtering!" repeated)
```

The intended `heatmap.png` is **not** present. `draw_heatmap.R` short-circuits when there is nothing significant to plot (every adjusted p-value is 1) — it doesn't write a PNG, it just prints `NULL` to stdout (visible in `run.log`). This is R's behaviour on a degenerate input, not a 04-side bug. Note: the earlier audit recorded a `histogram/histgram_padj_before_filter.png` side-car (filename typo); the current `draw_heatmap.R` no longer writes that file — an empty `plot/` directory is normal.

#### Expected properties

- `heatmap.png` exists.

#### Observed result

`heatmap.png` does **not** exist; `plot/` directory is empty. `run.log` shows R's `No meaningfull data left after filtering!` + `NULL` lines.

#### Assessment

WARNING. The pipeline does not raise an error when the heatmap is empty / un-renderable. Not strictly a 04 bug — it's the R script's behaviour on a degenerate input — but consumers who expect the canonical PNG name will get a missing-file error. Documented here so that the smoke fixture does not surprise anyone.

<a id="en-5"></a>

## 5. Final outputs

```
results/cli/intervals/
├── 01_indexing/
│   ├── universe.txt              26552 intervals (keeps __COLON__)
│   ├── promoter_lengths.txt      26552 rows      (keeps __COLON__)
│   ├── binomial_thresholds.txt   11    rows
│   ├── IC.txt                    11    rows
│   ├── genome.bg                 4-base markov background
│   └── fimohits/                 11    .bin files (PMETBN01)
└── 02_pairing/
    ├── motif_output.txt          56 rows (1 header + 55 pairs × 1 cluster)
    ├── genes_used_PMET.txt       18 rows
    ├── genes_not_found.txt       0 rows
    ├── pmet.log                  pairing_parallel stdout
    └── plot/                     heatmap PNG(s) when sufficient signal
```

Re-derived 2026-05-03 from `bash scripts/workflows/intervals.sh` with default args; output saved at `results/tests/walkthroughs_2026-05/intervals/`.

<a id="en-6"></a>

## 6. Risks / edge cases

1. **No short-interval filter.** A 4 bp interval is in the universe. It cannot match any motif but adds noise to the binomial threshold denominator. Recommendation (not implemented here): drop intervals shorter than the longest motif.
2. **Headers re-encoded as `__COLON__` in transit.** If any external process writes into `fimohits/` between steps 4 and 5, the restoration sed-pass might leave behind hybrid ids. Low risk in practice but worth knowing.
3. **`memefiles/` and `genome.bg` are kept on disk** post-run (the pipeline does not clean them up). They consume ~30 KB total — not a space issue but inconsistent with 03 / 05 which clean up by default.
4. **Heatmap silently absent on degenerate input.** The R script produces a histogram side-car instead of `heatmap.png` when the adjusted p-values are all 1. The pipeline exit code is still 0.
5. **Test fixture is too small to be biologically meaningful.** All adjusted p-values in `motif_output.txt` are 1. This is by design — the fixture is a wiring test — but documents are clear that the numerical output should not be interpreted.

<a id="en-7"></a>

## 7. Summary

**Overall status: PASS (structural) / NOT MEANINGFUL (scientific).** Pipeline 04 produces a valid homotypic index and a structurally valid `motif_output.txt` from a small interval-based fixture. All file-shape invariants hold. The fixture is a smoke-test, not a real experiment; its outputs are not meant to be interpreted as biology.

The pipeline itself is correct: contract files conform, FIMO p-values respect the threshold, IC and binomial outputs are well-formed, strand-aware sequence ids round-trip through the `__COLON__` shim. Two soft issues to flag for users: the absence of a final heatmap on degenerate input, and the lack of a short-interval filter.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. pipeline 用途](#cn-1) | [5. 最终输出](#cn-5) |
| [2. 输入](#cn-2) | [6. 风险 / 边界情况](#cn-6) |
| [3. 输出契约](#cn-3) | [7. 总结](#cn-7) |
| [4. 按 step 走读](#cn-4) | |

<a id="cn-1"></a>

## 1. pipeline 用途

对用户提供的一组预抽取 DNA *区间*（任意基因组区域）跑 PMET，不构造启动子、也不读 GFF3。使用场景：手头已经有 FASTA 形式的目标区域（ATAC peak、保守块、自定义启动子等），想测某个有标签子集里的 motif 共现。

"基因"概念被换成**区间 id**（典型是 `<chrom>:<start>-<end>(+/-)`）。pipeline 03 下游凡是讲"基因"的地方，pipeline 04 都讲区间 —— 契约一样，仅语义不同。

<a id="cn-2"></a>

## 2. 输入

| 文件 | 生物学含义 | 格式 | 截样 |
|---|---|---|---|
| `data/demos/intervals/indexing/intervals.fa` | universe —— FIMO 要扫的所有区间 | FASTA，26558 条 record | `>1:2631-3760(+)` 然后 DNA |
| `data/demos/intervals/indexing/motif_more.meme` | 11 个植物 MYB / clock motif | MEME v5.4.1 | 11 行 `MOTIF ` |
| `data/demos/intervals/indexing/peaks.txt` | 异型测试集：cluster 标签 + 区间 id | `<cluster> <interval_id>`，18 行，1 个 cluster（`U`），全 unique | `U 1:2631-3760(+)` |
| `scripts/workflows/intervals.sh` | 区间用的同型 shell 包装 | bash | n/a |
| `build/pairing_parallel` | 异型引擎 | 二进制 | n/a |

18 行测试集是个很小的 smoke fixture（一个 cluster `U`，全 unique）；同型 FASTA 涵盖 ~26.6 K 区间（≈ 25 Mb 序列空间，平均长度 942 bp），与 pipeline 03 的 ~30 Mb 启动子 universe 同量级。

<a id="cn-3"></a>

## 3. 输出契约

```
results/cli/intervals/
├── 01_indexing/
│   ├── universe.txt              （保留 __COLON__）
│   ├── promoter_lengths.txt      （保留 __COLON__）
│   ├── binomial_thresholds.txt
│   ├── IC.txt
│   ├── genome.bg
│   └── fimohits/<motif>.bin      （PMETBN01 二进制，保留 __COLON__）
└── 02_pairing/
    ├── motif_output.txt          （还原成 ':'）
    ├── genes_used_PMET.txt       （还原成 ':'）
    ├── genes_not_found.txt
    └── pmet.log
```

fimohits 格式从 per-motif `.txt`（TSV）切到 per-motif `.bin`（PMETBN01）发生在 commit `0c43958`（2026-04-30）—— 在线格式见 [`core/indexing/src/pmet_index/pmet-fimo-binary.h`](../../../core/indexing/src/pmet_index/pmet-fimo-binary.h)。二进制 fimohits 内部保留 `__COLON__`；只有 `02_pairing/` 的几个文本输出回环成 `:`（`scripts/workflows/intervals.sh:309-315`）。

<a id="cn-4"></a>

## 4. 按 step 走读

pipeline 04 的同型阶段是 `scripts/workflows/intervals.sh`，不是 `run_homotypic.py`。从头读这个 wrapper：

### Step 1 —— FASTA header sanitise（冒号 → `__COLON__`）

#### 命令 / 代码路径

```text
sed 's/^\(>.*\):/\1__COLON__/g' intervals.fa > intervals_temp.fa
```

(`scripts/workflows/intervals.sh:144-145`)

#### 目的

FIMO 把含 `:` 的序列名解析错（当成字段分隔符）。临时换掉，第 6 步还原。

#### 生物学含义

无；纯 FIMO 兼容垫片。

#### 期望属性

替换后任何 FASTA header 行都不含 `:`。

#### 判定

PASS（验证：临时文件在 FIMO 跑完后被删了不能回看；二进制 `fimohits/*.bin` 内部仍是 `__COLON__`，只在异型阶段产 `motif_output.txt`、`genes_used_PMET.txt`、`genes_not_found.txt` 时回环成 `:` —— `intervals.sh:309-315`）。

---

### Step 2 —— FASTA 去重

#### 命令 / 代码路径

```text
python3 scripts/python/deduplicate.py intervals_temp.fa no_duplicates.fa
python3 scripts/python/parse_promoter_lengths_from_fasta.py \
    no_duplicates.fa promoter_lengths.txt
cut -f1 promoter_lengths.txt > universe.txt
```

(`scripts/workflows/intervals.sh:155-167`)

#### 目的

丢掉 header 重复的 FASTA record；从 FASTA 直接派生 `promoter_lengths.txt`（区间 id、长度）和 `universe.txt`（仅区间 id）。

#### 生物学含义

区间 pipeline 里 FASTA 本身**就是**基因集合。没 GFF3 可查。长度是序列长度，不是启动子窗口长度。所以契约文件由 FASTA 计算出来，而不是基因组坐标。

#### 输入

`intervals_temp.fa` —— 26558 条 record（6 条 header 重复以触发 dedup 步）。

#### 输出

```
universe.txt          26552 行
promoter_lengths.txt  26552 行
```

`universe.txt` 前 3：

```
1:2631-3760(+)
1:8666-10130(-)
1:12940-14714(-)
```

`promoter_lengths.txt` 前 3：

```
1:2631-3760(+)    1129
1:8666-10130(-)   1464
1:12940-14714(-)  1774
```

#### 期望属性

| 检查 | 期望 | 观察 |
|---|---|---|
| Universe 数 ≤ FASTA record 数 | 是 | 26552 ≤ 26558（丢了 6 条重复 header） |
| `universe.txt` ⊇ `intervals.txt` 所有 id | 异型阶段要求 | `comm -23 intervals.txt univ` 返 0 |
| `length > 0` | 是 | 0 违反；min=4，max=3517，mean=942 |
| length 等于 FASTA 序列长度 | 是 | 由构造保证 |
| Universe 集合 ≡ promoter_lengths gene 集合 | 是 | `comm -3` 返 0 |

#### 观察结果

数量和一致性全成立。

#### 判定

PASS，带一条 **WARNING**：最小长度 4 bp（FASTA 里确有一条几乎空 record）。绝大多数 TF motif 是 6–14 bp，4 bp 序列装不下任何 motif，静默吃 budget。pipeline 04 不过滤短区间（对比 03 的 lt10/lt20、06/07 的 lt30 过滤）。

---

### Step 3 —— 背景模型 + per-motif IC

#### 命令 / 代码路径

```text
fasta-get-markov intervals_temp.fa > genome.bg
python3 scripts/python/parse_memefile.py            motif_more.meme memefiles/
python3 scripts/python/calculateICfrommeme_IC_to_csv.py memefiles/ IC.txt
```

(`scripts/workflows/intervals.sh:179-192`)

#### 目的

`genome.bg` 让 FIMO p 值按*区间集*的碱基组成校准（不是整个基因组）。`IC.txt` 给异型重叠加权用。

#### 输出

```
genome.bg   5 行（0 阶 Markov：A、C、G、T 加 header）
IC.txt      11 行（每 motif 一行）
```

`IC.txt` 第一行：

```
MYB59 0.6150 1.3066 1.6431 1.2789 1.6761 1.6236 1.4806 0.4734
```

#### 期望属性

- `IC.txt` 正好 `nummotifs`（11）行。
- 所有 IC 值 ∈ [0, 2]。

#### 观察结果

都成立。

#### 判定

PASS。

---

### Step 4 —— FIMO + PMETindex 按批

#### 命令 / 代码路径

```text
build/indexing_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile genome.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<motif>.txt intervals_temp.fa promoter_lengths.txt
```

(`scripts/workflows/intervals.sh:203-219`)

注意：`indexing_fimo_fused` 已带内部 OpenMP motif 分批（commit `0c43958`，2026-04-30 起），单次二进制调用就处理所有 motif —— 没有 shell 层的 `parse_memefile_batches.py` + `& wait` 循环、没有 per-motif fork。

#### 目的

跟 pipeline 03 同样的二合一调用 —— 一个二进制调用同时产 `fimohits/*.bin`（PMETBN01）和 `binomial_thresholds.txt`。

#### 输出

```
fimohits/   11 个文件（.bin，PMETBN01）
binomial_thresholds.txt   11 行
```

`fimohits/MYB111_2.bin` 是二进制（PMETBN01），不是 TSV，不可直接当文本看；想 inspect 用 [`scripts/python/collapse_element_fimohits.py`](../../../scripts/python/collapse_element_fimohits.py) 里的 helper 解码。

`binomial_thresholds.txt`（全 11 行）：

```
MYB52     1.597146785000000e-02
MYB52_2   9.026485518000000e-03
MYB59     1.348507756000000e-02
MYB46     6.985501377000000e-03
MYB46_2   2.001568968000000e-03
…
```

#### 期望属性

| 检查 | 期望 | 观察 |
|---|---|---|
| fimohits 文件数 | 11（motif 数） | 11 |
| binomial 阈值行数 | 11 | 11 |
| FIMO p 值 ≤ 0.05 | 由 `--thresh 0.05` 强制 | 在范围内 |
| 阈值在合理区间 | ≪ 1.0 | min 1.5e-03，max 2.2e-02，mean 9.7e-03 |

#### 观察结果

全成立。

#### 判定

PASS。binomial 阈值（mean ≈ 9.7e-03）甚至比 promoter pipeline 在完整 113 motif Franco-Zorrilla 上的 mean ≈ 4.3e-02 还紧 —— 跟区间 universe 是 25 Mb 有效序列空间（26552 区间 × 942 bp 平均长度）一致，跟 pipeline 03 的 ~30 Mb 启动子 universe 同量级。本走读早期版本（针对 `intervals.fa` ~10× 更小的数据集 —— 2717 record，~2.7 Mb 空间）报告阈值 ≈ 0.99 并标了"binomial 零分布弱"WARNING；那个发现是小数据集特有的，**当前 ~26.6 K 区间 demo 上不再成立**。下游 `pairing_parallel -i 4` 的 IC 阈值仍是主要的科学过滤。

---

### Step 5 —— 在用户面文本输出里还原 `:`

#### 命令 / 代码路径

```text
for f in motif_output.txt genes_used_PMET.txt genes_not_found.txt; do
    sed 's/__COLON__/:/g' "$pairing_output/$f" > "$f.tmp" && mv "$f.tmp" "$f"
done
```

(`scripts/workflows/intervals.sh:309-315`)

#### 目的

step 1 sanitise 的回环 —— **只**对异型阶段的文本输出做。Pre-monorepo 时这一步把所有东西都回环（universe.txt、promoter_lengths.txt、所有 fimohits 文件）；`0c43958` 引入二进制 fimohits 后没法 sed，且上游 `pairing_parallel` 本来就是在 sanitised 空间读输入，所以回环范围收窄到下游的三个文本文件。

#### 期望属性

| 文件 | `__COLON__` 应当 | 观察 |
|---|---|---|
| `02_pairing/motif_output.txt` | 还原成 `:` | 0 处 `__COLON__` |
| `02_pairing/genes_used_PMET.txt` | 还原成 `:` | 0 处 |
| `02_pairing/genes_not_found.txt` | 还原成 `:` | 0 处 |
| `01_indexing/universe.txt` | **保留** `__COLON__` | 每行都有 `__COLON__` |
| `01_indexing/promoter_lengths.txt` | **保留** `__COLON__` | 每行都有 |
| `01_indexing/fimohits/*.bin` | 内部**保留** | 二进制；`strings` 看仍是 `__COLON__` |

#### 判定

PASS，但回环面比 pipeline 03 更窄。如果你要 grep `01_indexing/universe.txt` 找某个区间 id，搜 `__COLON__` 而不是 `:`。

---

### Step 6 —— 同型契约校验

#### 命令 / 代码路径

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```

(`scripts/workflows/intervals.sh:256`)

#### 输出

`OK — homotypic contract holds (11 motifs, 26552 universe genes, 26552 genes with promoter lengths)`（2026-05-03 重跑验证）。

#### 判定

PASS。

---

### Step 7 —— 异型 motif 对检验

#### 命令 / 代码路径

```text
build/pairing_parallel \
    -d "$indexing_output" -g "$gene_sanitized" -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o "$pairing_output" -t "$threads" \
    -m "$minhash_min" > "$pairing_output/pmet.log"
```

(`scripts/workflows/intervals.sh:288-298`)

Pipelines 03 / 04 / 05 / 06 / 07 现在都用同一个 `build/pairing_parallel` 二进制（monorepo 合并时已经把旧的 `pair_parallel` / `pmetParallel` 拆分淘汰，融合成单一实现）。

#### 目的

测 cluster `U` 内 motif 对在 26552 区间全局背景下的共富集。

#### 生物学含义

"gene" 那一列实际上装的是区间 id。读 `motif_output.txt` 时要明白"cluster 内的 gene"实际是 cluster 内的区间。

#### 输入

`peaks.txt` —— 18 行，单一 cluster `U`，全 unique。`pmet.log` 确认：`Found 18 gene IDs in 1 clusters`。（早期审计的 `intervals.txt` 是 17 行带一条重复，所以才有历史上的"18 unique"说法；当前 `peaks.txt` 已经是 18 条 distinct）。

#### 输出

`motif_output.txt` —— 11 列，56 行 = 1 header + 55 motif 对 × 1 cluster。（11 motif 的无序对 C(11,2) = 55，跟行数对得上）。

```
Cluster  Motif 1   Motif 2     n_in_cluster_with_both  total_with_both  cluster_n  raw_p  bh  bonf  global_bonf  Genes
U        CCA1      CCA1_2      0                       538              18         1.0    1.0  1.0   1.0
U        CCA1      MYB111      0                       745              18         1.0    1.0  1.0   1.0
```

#### 期望属性

- 11 列。✓
- `1 + C(11,2) * num_clusters = 1 + 55 = 56` 行。✓
- 所有 raw p 值 ∈ [0, 1]。✓

#### 观察结果

每对的 "Number of genes in cluster with both motifs" 都是 0，每个校正 p 值都是 1。跟测试 fixture 故意很小一致 —— 18 区间是 smoke 测集，不是真实生物 cluster。

#### 判定

结构上 PASS，**WARNING** 在科学上：这个 fixture 没什么可发现，跑这一步只是契约 / wiring 测试。

---

### Step 8 —— Heatmap

#### 命令 / 代码路径

```text
Rscript scripts/r/draw_heatmap.R \
    Overlap heatmap.png motif_output.txt 5 3 6 FALSE
```

(`scripts/workflows/intervals.sh:95-102`)

#### 输出（观察）

```
results/cli/intervals/02_pairing/
├── motif_output.txt
└── plot/                          (空 —— stdout 多次 "No meaningfull data left after filtering!")
```

`heatmap.png` **不存在**。`draw_heatmap.R` 在没有任何显著 motif 对可画时短路（每个校正 p 值都是 1），不写 PNG，只把 `NULL` 印到 stdout（仍能在 `run.log` 里看到）。这是 R 端对退化输入的行为，不是 04 自己的 bug。注意：早期审计有一份 `histogram/histgram_padj_before_filter.png`（filename typo），当前 R 脚本不再写这个副件 —— 完全空 plot/ 目录是正常的。

#### 期望属性

- `heatmap.png` 存在。

#### 观察结果

`heatmap.png` **不**存在；plot/ 目录为空。`run.log` 里能看到 R 的 `No meaningfull data left after filtering!` + `NULL`。

#### 判定

WARNING。pipeline 在 heatmap 空 / 无法渲染时不报错。严格说不是 04 的 bug —— 是 R 脚本对退化输入的行为 —— 但期待规范 PNG 名的消费者会撞到缺文件错。在这里记一下，让 smoke fixture 别让人惊讶。

<a id="cn-5"></a>

## 5. 最终输出

```
results/cli/intervals/
├── 01_indexing/
│   ├── universe.txt              26552 区间（保留 __COLON__）
│   ├── promoter_lengths.txt      26552 行     （保留 __COLON__）
│   ├── binomial_thresholds.txt   11    行
│   ├── IC.txt                    11    行
│   ├── genome.bg                 4 碱基 markov 背景
│   └── fimohits/                 11    个 .bin 文件（PMETBN01）
└── 02_pairing/
    ├── motif_output.txt          56 行（1 header + 55 对 × 1 cluster）
    ├── genes_used_PMET.txt       18 行
    ├── genes_not_found.txt       0 行
    ├── pmet.log                  pairing_parallel stdout
    └── plot/                     信号足时写 heatmap PNG
```

2026-05-03 用 `bash scripts/workflows/intervals.sh` 默认参数重跑得到；输出存在 `results/tests/walkthroughs_2026-05/intervals/`。

<a id="cn-6"></a>

## 6. 风险 / 边界情况

1. **没有短区间过滤。** 4 bp 区间在 universe 里。它配不上任何 motif 但给 binomial 阈值分母加噪声。建议（这里没实现）：丢掉短于最长 motif 的区间。
2. **header 在中转中变成 `__COLON__`。** step 4 与 step 5 之间如果有外部进程写入 `fimohits/`，还原 sed 可能留下混杂 id。实践中风险低，但要知道。
3. **`memefiles/` 和 `genome.bg` 跑完留在盘上**（pipeline 不清理）。共 ~30 KB，不是空间问题，但跟 03 / 05 默认清理的行为不一致。
4. **退化输入下 heatmap 静默缺失。** R 脚本在所有校正 p 值都是 1 时产直方图副件而不是 `heatmap.png`。pipeline 退出码仍然是 0。
5. **测试 fixture 太小没有生物学意义。** `motif_output.txt` 所有校正 p 值都是 1。这是按设计 —— fixture 是 wiring 测试 —— 但要文档明确说数值输出不该被解读。

<a id="cn-7"></a>

## 7. 总结

**整体状态：结构 PASS / 科学不具意义。** Pipeline 04 从一个小区间-based fixture 产出有效的同型索引和结构上有效的 `motif_output.txt`。所有文件 shape 不变量都成立。fixture 是 smoke 测，不是真实实验；其输出不该按生物学解读。

pipeline 本身正确：契约文件符合要求、FIMO p 值遵守阈值、IC 与 binomial 输出 well-formed、链感知序列 id 通过 `__COLON__` 垫片来回穿越。两个软问题给用户：退化输入下没有最终 heatmap，没有短区间过滤。
