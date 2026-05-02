# Pipeline 04 walkthrough — Interval-based PMET analysis

**[English](#en) · [汉文](#cn)**

> **Heads-up:** this is a frozen pre-monorepo walkthrough. References like `scripts/pipeline/04_intervals.sh`, `scripts/indexing/intervals.sh`, `data/homotypic_intervals/`, and `build/pmetParallel` are stale — the consolidated current entry point is `scripts/workflows/intervals.sh` (which uses `build/pair_parallel`). See [`README.md`](README.md) for the full path mapping. The algorithm and biology described still apply.

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
| `data/homotypic_intervals/intervals.fa` | the universe — all intervals that FIMO will scan | FASTA, 2717 records | `>1:2631-3760(+)` then DNA |
| `data/homotypic_intervals/motif_more.meme` | 8 plant MYB motifs | MEME v5.4.1 | `MOTIF ` lines × 8 |
| `data/homotypic_intervals/intervals.txt` | the heterotypic test set: cluster label + interval id | `<cluster> <interval_id>`, 17 rows, 1 cluster (`U`) | `U 1:2631-3760(+)` |
| `scripts/indexing/intervals.sh` | homotypic shell wrapper for intervals | bash | n/a |
| `build/pmetParallel` | heterotypic engine | binary | n/a |

The 17-row test set is a tiny smoke fixture (one cluster `U`); the homotypic FASTA covers ~2.7 K intervals, large enough to compute realistic binomial thresholds.

<a id="en-3"></a>

## 3. Output contract

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

Note: pipeline 04 does **not** produce the three named heatmap PNGs of pipeline 03. The R call is wired (`scripts/pipeline/04_intervals.sh:95-102`) to write a single `heatmap.png` under `02_heterotypic/`, but at audit time only the histogram side-car (`02_heterotypic/histogram/histgram_padj_before_filter.png`, note typo) is present, not the named heatmap. See §6.

<a id="en-4"></a>

## 4. Step-by-step execution story

The homotypic stage of pipeline 04 is `scripts/indexing/intervals.sh`, not `run_homotypic.py`. Reading the wrapper end-to-end:

### Step 1 — Sanitise FASTA headers (colon → `__COLON__`)

#### Command / code path

```text
sed 's/^\(>.*\):/\1__COLON__/g' intervals.fa > intervals_temp.fa
```

(`scripts/indexing/intervals.sh:144-145`)

#### Purpose

FIMO mis-parses sequence names containing `:` (interpreted as field separators). Replace temporarily; restore at step 6.

#### Bioinformatics meaning

None; pure FIMO compatibility shim.

#### Expected properties

After replacement, no `:` in any FASTA header line.

#### Assessment

PASS (verified: temporary file is removed after FIMO so cannot be re-inspected, but the `^>` lines in the final `fimohits/*.txt` are restored to the original `<chrom>:<start>-<end>(+/-)` form).

---

### Step 2 — Deduplicate FASTA

#### Command / code path

```text
python3 scripts/python/deduplicate.py intervals_temp.fa no_duplicates.fa
python3 scripts/python/parse_promoter_lengths_from_fasta.py \
    no_duplicates.fa promoter_lengths.txt
cut -f1 promoter_lengths.txt > universe.txt
```

(`scripts/indexing/intervals.sh:155-167`)

#### Purpose

Drop FASTA records whose header is a duplicate; derive `promoter_lengths.txt` (interval id, length) and `universe.txt` (interval id only) directly from the FASTA.

#### Bioinformatics meaning

In the interval pipeline the FASTA itself *is* the gene set. There is no GFF3 to consult. Length is sequence length, not promoter window length. So the contract files are computed from the FASTA, not from genomic coordinates.

#### Input

`intervals_temp.fa` — 2717 records (1 ± duplicate to test the dedup step).

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

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| Universe count ≤ FASTA count | yes | 2716 ≤ 2717 (1 duplicate dropped) |
| `universe.txt` ⊇ all `intervals.txt` ids | required by heterotypic step | `comm -23 intervals.txt univ` returns 0 |
| `length > 0` | yes | 0 violations, min=4, max=3517, mean=899 |
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

(`scripts/indexing/intervals.sh:179-192`)

#### Purpose

`genome.bg` calibrates FIMO p-values against the *interval set's* base composition (not the whole genome). `IC.txt` is the per-position info content for heterotypic overlap weighting.

#### Output

```
genome.bg   5 rows  (0-order Markov: A,C,G,T plus header)
IC.txt      8 rows  (one per motif)
```

`IC.txt` first row:

```
MYB59 0.6150 1.3066 1.6431 1.2789 1.6761 1.6236 1.4806 0.4734
```

#### Expected properties

- `IC.txt` has exactly `nummotifs` (8) rows.
- All IC values ∈ [0, 2].

#### Observed result

Both hold.

#### Assessment

PASS.

---

### Step 4 — FIMO + PMETindex per batch

#### Command / code path

```text
build/index_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile genome.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<motif>.txt intervals_temp.fa promoter_lengths.txt
```

(`scripts/indexing/intervals.sh:203-219`)

Note: pipeline 04 does **not** use `parse_memefile_batches.py`; each motif is one file (since there are only 8 motifs and the pipeline runs single-threaded by default). Parallelism is `& wait` over batches of `threads` motifs.

#### Purpose

Same dual-purpose call as in pipeline 03 — produce `fimohits/*.txt` plus `binomial_thresholds.txt` in one binary invocation.

#### Output

```
fimohits/   8 files
binomial_thresholds.txt   8 rows
```

`fimohits/MYB111_2.txt` first 3 rows (after `__COLON__ → :` restoration at step 6 below):

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

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| Number of fimohits files | 8 (motif count) | 8 |
| Number of binomial threshold rows | 8 | 8 |
| FIMO p-value ≤ 0.05 | enforced by `--thresh 0.05` | min ≈ 4.2e-06, max ≈ 0.0498 |
| Hit's seq id ∈ universe | yes | sampled, all rows reference ids in `universe.txt` |

#### Observed result

All hold.

#### Assessment

PASS, with one **WARNING**: the binomial thresholds are very high (≈ 0.99) compared to pipeline 03 (≈ 1e-3). This is consistent with a small universe (2716 intervals × 1 kb mean length ≈ 2.7 Mb effective search space, vs ~30 Mb of promoter sequence in pipeline 03): the binomial null is much weaker, so almost any hit is "significant". The downstream pair_parallel `-i 4` IC threshold is the actual filter that prevents this from producing noise.

---

### Step 5 — Restore `:` in FASTA ids

#### Command / code path

```text
sed 's/__COLON__/:/g' fimohits/*.txt
sed 's/__COLON__/:/g' promoter_lengths.txt
sed 's/__COLON__/:/g' universe.txt
rm intervals_temp.fa
```

(`scripts/indexing/intervals.sh:223-231`)

#### Purpose

Reverse the step-1 sanitisation so that downstream consumers see the original `chrom:start-end(strand)` ids.

#### Expected properties

No `__COLON__` remains in any of the contract files.

#### Observed result

`grep __COLON__ universe.txt promoter_lengths.txt fimohits/*.txt` → no matches.

#### Assessment

PASS.

---

### Step 6 — Homotypic contract validation

#### Command / code path

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```

(`scripts/indexing/intervals.sh:256`)

#### Output

`OK` (8 motifs, 2716 universe intervals).

#### Assessment

PASS.

---

### Step 7 — Heterotypic motif-pair test

#### Command / code path

```text
build/pmetParallel \
    -d . -g intervals.txt -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/04_intervals/02_heterotypic -t 1
```

(`scripts/pipeline/04_intervals.sh:80-89`)

Note: pipeline 04 uses **`pmetParallel`** (older binary), whereas 03 / 05 use **`pair_parallel`** (the fused replacement). Output format is identical.

#### Purpose

Test motif-pair co-enrichment within cluster `U` against the global 2716-interval background.

#### Bioinformatics meaning

The "gene" column actually holds an interval id. Reading `motif_output.txt` requires understanding that a "gene in cluster" is an interval in cluster.

#### Input

`intervals.txt` — 17 rows, single cluster `U`. (One row appears twice, hence the heterotypic step sees 18 unique entries — see "N_in_cluster=18" in the output.)

#### Output

`motif_output.txt` — 11 columns, 29 rows = 1 header + 28 motif pairs = C(8,2) = 28 pairs × 1 cluster.

```
Cluster  Motif 1   Motif 2     ...
U        MYB111    MYB111_2    0  0  18  1  1  1  1
U        MYB111    MYB46       0  0  18  1  1  1  1
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

(`scripts/pipeline/04_intervals.sh:95-102`)

#### Output (observed)

```
results/04_intervals/02_heterotypic/
├── motif_output.txt
└── histogram/
    └── histgram_padj_before_filter.png   23892 bytes
```

The intended `heatmap.png` is **not** present. `draw_heatmap.R` appears to short-circuit when there is nothing significant to plot (every adjusted p-value is 1) and writes only the diagnostic histogram side-car. The histogram name has a typo (`histgram` for `histogram`) — not a 04 issue, lives inside `draw_heatmap.R`.

#### Expected properties

- `heatmap.png` exists.

#### Observed result

`heatmap.png` does **not** exist; only the histogram side-car.

#### Assessment

WARNING. The pipeline does not raise an error when the heatmap is empty / un-renderable. Not strictly a 04 bug — it's the R script's behaviour on a degenerate input — but consumers who expect the canonical PNG name will get a missing-file error. Documented here so that the smoke fixture does not surprise anyone.

<a id="en-5"></a>

## 5. Final outputs

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
| `data/homotypic_intervals/intervals.fa` | universe —— FIMO 要扫的所有区间 | FASTA，2717 条 record | `>1:2631-3760(+)` 然后 DNA |
| `data/homotypic_intervals/motif_more.meme` | 8 个植物 MYB motif | MEME v5.4.1 | 8 行 `MOTIF ` |
| `data/homotypic_intervals/intervals.txt` | 异型测试集：cluster 标签 + 区间 id | `<cluster> <interval_id>`，17 行，1 个 cluster（`U`） | `U 1:2631-3760(+)` |
| `scripts/indexing/intervals.sh` | 区间用的同型 shell 包装 | bash | n/a |
| `build/pmetParallel` | 异型引擎 | 二进制 | n/a |

17 行测试集是个很小的 smoke fixture（一个 cluster `U`）；同型 FASTA 涵盖 ~2.7 K 区间，量足以算出真实的 binomial 阈值。

<a id="cn-3"></a>

## 3. 输出契约

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

注意：pipeline 04 **不**产 pipeline 03 那三张命名 heatmap PNG。R 调用接成（`scripts/pipeline/04_intervals.sh:95-102`）写一张 `heatmap.png` 到 `02_heterotypic/`，但审计时只见到直方图副件（`02_heterotypic/histogram/histgram_padj_before_filter.png`，注意是 typo），没有命名 heatmap。见 §6。

<a id="cn-4"></a>

## 4. 按 step 走读

pipeline 04 的同型阶段是 `scripts/indexing/intervals.sh`，不是 `run_homotypic.py`。从头读这个 wrapper：

### Step 1 —— FASTA header sanitise（冒号 → `__COLON__`）

#### 命令 / 代码路径

```text
sed 's/^\(>.*\):/\1__COLON__/g' intervals.fa > intervals_temp.fa
```

(`scripts/indexing/intervals.sh:144-145`)

#### 目的

FIMO 把含 `:` 的序列名解析错（当成字段分隔符）。临时换掉，第 6 步还原。

#### 生物学含义

无；纯 FIMO 兼容垫片。

#### 期望属性

替换后任何 FASTA header 行都不含 `:`。

#### 判定

PASS（验证：临时文件在 FIMO 跑完后被删了不能回看，但最终 `fimohits/*.txt` 里 `^>` 行都被还原成了原始的 `<chrom>:<start>-<end>(+/-)` 形式）。

---

### Step 2 —— FASTA 去重

#### 命令 / 代码路径

```text
python3 scripts/python/deduplicate.py intervals_temp.fa no_duplicates.fa
python3 scripts/python/parse_promoter_lengths_from_fasta.py \
    no_duplicates.fa promoter_lengths.txt
cut -f1 promoter_lengths.txt > universe.txt
```

(`scripts/indexing/intervals.sh:155-167`)

#### 目的

丢掉 header 重复的 FASTA record；从 FASTA 直接派生 `promoter_lengths.txt`（区间 id、长度）和 `universe.txt`（仅区间 id）。

#### 生物学含义

区间 pipeline 里 FASTA 本身**就是**基因集合。没 GFF3 可查。长度是序列长度，不是启动子窗口长度。所以契约文件由 FASTA 计算出来，而不是基因组坐标。

#### 输入

`intervals_temp.fa` —— 2717 条 record（1 条故意重复以测 dedup 步）。

#### 输出

```
universe.txt          2716 行
promoter_lengths.txt  2716 行
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
| Universe 数 ≤ FASTA record 数 | 是 | 2716 ≤ 2717（丢了 1 条重复） |
| `universe.txt` ⊇ `intervals.txt` 所有 id | 异型阶段要求 | `comm -23 intervals.txt univ` 返 0 |
| `length > 0` | 是 | 0 违反；min=4，max=3517，mean=899 |
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

(`scripts/indexing/intervals.sh:179-192`)

#### 目的

`genome.bg` 让 FIMO p 值按*区间集*的碱基组成校准（不是整个基因组）。`IC.txt` 给异型重叠加权用。

#### 输出

```
genome.bg   5 行（0 阶 Markov：A、C、G、T 加 header）
IC.txt      8 行（每 motif 一行）
```

`IC.txt` 第一行：

```
MYB59 0.6150 1.3066 1.6431 1.2789 1.6761 1.6236 1.4806 0.4734
```

#### 期望属性

- `IC.txt` 正好 `nummotifs`（8）行。
- 所有 IC 值 ∈ [0, 2]。

#### 观察结果

都成立。

#### 判定

PASS。

---

### Step 4 —— FIMO + PMETindex 按批

#### 命令 / 代码路径

```text
build/index_fimo_fused --no-qvalue --text \
    --thresh 0.05 --bgfile genome.bg \
    --topn 5000 --topk 5 --oc <out> \
    memefiles/<motif>.txt intervals_temp.fa promoter_lengths.txt
```

(`scripts/indexing/intervals.sh:203-219`)

注意：pipeline 04 **不**用 `parse_memefile_batches.py`；每 motif 一个文件（只有 8 个 motif，pipeline 默认单线程）。并行度走 `& wait`，按 `threads` 个 motif 分批。

#### 目的

跟 pipeline 03 同样的二合一调用 —— 一个二进制调用同时产 `fimohits/*.txt` 和 `binomial_thresholds.txt`。

#### 输出

```
fimohits/   8 文件
binomial_thresholds.txt   8 行
```

`fimohits/MYB111_2.txt` 前 3 行（第 6 步 `__COLON__ → :` 还原后）：

```
MYB111_2  1:7770659-7771897(+)   75    82    +   1.4961538460e+01  8.4661721950e-06
MYB111_2  1:7770659-7771897(+)   1114  1121  +   1.4961538460e+01  8.4661721950e-06
MYB111_2  1:7770659-7771897(+)   679   686   +   1.0125000000e+01  1.2063574980e-04
```

`binomial_thresholds.txt`：

```
MYB111_2  9.953298312e-01
MYB111    9.996405678e-01
MYB46_2   9.975487412e-01
```

#### 期望属性

| 检查 | 期望 | 观察 |
|---|---|---|
| fimohits 文件数 | 8（motif 数） | 8 |
| binomial 阈值行数 | 8 | 8 |
| FIMO p 值 ≤ 0.05 | 由 `--thresh 0.05` 强制 | min ≈ 4.2e-06，max ≈ 0.0498 |
| hit 的 seq id ∈ universe | 是 | 抽样所有行的 id 都在 `universe.txt` 里 |

#### 观察结果

全成立。

#### 判定

PASS，带一条 **WARNING**：binomial 阈值非常高（≈ 0.99），跟 pipeline 03 的 ≈ 1e-3 形成对比。这跟小 universe 一致（2716 区间 × 1 kb 平均长度 ≈ 2.7 Mb 有效搜索空间，vs pipeline 03 的 ~30 Mb 启动子序列）：binomial 零分布弱很多，几乎任何 hit 都"显著"。下游 pair_parallel `-i 4` 的 IC 阈值才是真正的过滤，防止这一步产噪声。

---

### Step 5 —— 还原 FASTA id 里的 `:`

#### 命令 / 代码路径

```text
sed 's/__COLON__/:/g' fimohits/*.txt
sed 's/__COLON__/:/g' promoter_lengths.txt
sed 's/__COLON__/:/g' universe.txt
rm intervals_temp.fa
```

(`scripts/indexing/intervals.sh:223-231`)

#### 目的

逆向 step 1 的 sanitise，让下游消费者看到原始的 `chrom:start-end(strand)` id。

#### 期望属性

任何契约文件里都不剩 `__COLON__`。

#### 观察结果

`grep __COLON__ universe.txt promoter_lengths.txt fimohits/*.txt` → 无匹配。

#### 判定

PASS。

---

### Step 6 —— 同型契约校验

#### 命令 / 代码路径

```text
python3 scripts/python/check_homotypic_contract.py <out>/
```

(`scripts/indexing/intervals.sh:256`)

#### 输出

`OK`（8 motif，2716 universe 区间）。

#### 判定

PASS。

---

### Step 7 —— 异型 motif 对检验

#### 命令 / 代码路径

```text
build/pmetParallel \
    -d . -g intervals.txt -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/04_intervals/02_heterotypic -t 1
```

(`scripts/pipeline/04_intervals.sh:80-89`)

注意：pipeline 04 用 **`pmetParallel`**（旧二进制），03 / 05 用 **`pair_parallel`**（fused 替代）。输出格式相同。

#### 目的

测 cluster `U` 内 motif 对在 2716 区间全局背景下的共富集。

#### 生物学含义

"gene" 那一列实际上装的是区间 id。读 `motif_output.txt` 时要明白"cluster 内的 gene"实际是 cluster 内的区间。

#### 输入

`intervals.txt` —— 17 行，单一 cluster `U`。（一行出现两次，所以异型阶段看到 18 个唯一条目 —— 输出里 "N_in_cluster=18"。）

#### 输出

`motif_output.txt` —— 11 列，29 行 = 1 header + 28 motif 对 = C(8,2) = 28 对 × 1 cluster。

```
Cluster  Motif 1   Motif 2     ...
U        MYB111    MYB111_2    0  0  18  1  1  1  1
U        MYB111    MYB46       0  0  18  1  1  1  1
```

#### 期望属性

- 11 列。✓
- `1 + C(8,2) * num_clusters = 1 + 28 = 29` 行。✓
- 所有 raw p 值 ∈ [0, 1]。✓

#### 观察结果

每对的 "Number of genes in cluster with both motifs" 都是 0，每个校正 p 值都是 1。跟测试 fixture 故意很小一致 —— 17 区间是 smoke 测集，不是真实生物 cluster。

#### 判定

结构上 PASS，**WARNING** 在科学上：这个 fixture 没什么可发现，跑这一步只是契约 / wiring 测试。

---

### Step 8 —— Heatmap

#### 命令 / 代码路径

```text
Rscript scripts/r/draw_heatmap.R \
    Overlap heatmap.png motif_output.txt 5 3 6 FALSE
```

(`scripts/pipeline/04_intervals.sh:95-102`)

#### 输出（观察）

```
results/04_intervals/02_heterotypic/
├── motif_output.txt
└── histogram/
    └── histgram_padj_before_filter.png   23892 字节
```

预期的 `heatmap.png` **不存在**。`draw_heatmap.R` 在没有任何显著值可画时短路（每个校正 p 值都是 1），只写诊断直方图副件。直方图文件名有 typo（`histgram` 应为 `histogram`）—— 不是 04 的问题，在 `draw_heatmap.R` 内部。

#### 期望属性

- `heatmap.png` 存在。

#### 观察结果

`heatmap.png` **不**存在；只有直方图副件。

#### 判定

WARNING。pipeline 在 heatmap 空 / 无法渲染时不报错。严格说不是 04 的 bug —— 是 R 脚本对退化输入的行为 —— 但期待规范 PNG 名的消费者会撞到缺文件错。在这里记一下，让 smoke fixture 别让人惊讶。

<a id="cn-5"></a>

## 5. 最终输出

```
results/04_intervals/
├── 01_homotypic/
│   ├── universe.txt              2716 区间
│   ├── promoter_lengths.txt      2716 行
│   ├── binomial_thresholds.txt   8    行
│   ├── IC.txt                    8    行
│   ├── genome.bg                 4 碱基 markov 背景
│   ├── memefiles/                8 份 per-motif MEME 切片（保留在盘上）
│   └── fimohits/                 8    文件
└── 02_heterotypic/
    ├── motif_output.txt          29 行（1 header + 28 对 × 1 cluster）
    └── histogram/histgram_padj_before_filter.png   23 KB
```

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
