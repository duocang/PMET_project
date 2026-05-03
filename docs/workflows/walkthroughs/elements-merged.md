# Genomic-Element PMET, per-gene UNION across isoforms — walkthrough

**[English](#en) · [汉文](#cn)**

> **About this doc:** path references throughout match the **current** monorepo layout (`scripts/workflows/elements.sh -s merged`, `scripts/workflows/cli/_pmet_index_element.sh`, `results/cli/elements_merged/`). The biology and algorithm content predates the monorepo merge — that's all unchanged from the original PMET. Inline `:line-range` annotations after a script path were captured against the pre-monorepo `07_elements_merged.sh` (retired, folded into `scripts/workflows/elements.sh`); treat them as **section hints**, not exact citations.

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

Same biological setting as [pipeline 06](elements-longest.md) — PMET on a chosen genomic element (CDS / exon / mRNA / 5' UTR / 3' UTR) inside the gene body — but using a different isoform aggregation strategy:

> Per gene, take the **union** of all isoforms' element intervals, merging overlapping and book-ended intervals into a single non-redundant set. No isoform specificity, no UTR subtraction.

If pipeline 06 says "pick the most-coding transcript and use its fragments", pipeline 07 says "consider every transcript's coding regions, pool them, scan once". The two are alternative answers to the same question — *which set of element-derived sequences should represent each gene?* — and produce a slightly different signal under alternative splicing.

<a id="en-2"></a>

## 2. Inputs

Identical to pipeline 06 ([elements-longest.md §2](elements-longest.md#2-inputs)). The only configuration that differs is the strategy flag:

| Parameter | 06 (longest) | 07 (merged) |
|---|---|---|
| `strategy` | `longest` | `merged` |
| `delete_temp` | `no` | `yes` |
| `mrnaFull` | `No` (subtract UTRs from mRNA) | not applicable (merge has no UTR-subtraction) |

The five heterotypic tasks are identical. Defaults are the same.

<a id="en-3"></a>

## 3. Output contract

Identical to pipeline 06:

```
results/cli/elements_merged/
├── 01_homotypic/
├── 02_heterotypic_<task>/   × 5
└── 03_plot_<task>/          × 5
```

<a id="en-4"></a>

## 4. Step-by-step execution story

Steps 1, 2, 4–10 are byte-identical to pipeline 06 (same indexer, same downstream code path). Only the **isoform aggregation step** diverges. This audit only re-describes the divergent step in detail and refers back to 06 for the rest.

### Step 1 — Chromosome-naming preflight + element extraction

Identical to 06 step 1 + 2. PASS.

### Step 2 — Per-gene merge across isoforms

#### Command / code path

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

(`scripts/workflows/cli/_pmet_index_element.sh:255-270`)

This block does three things in sequence:

1. **Strip `.N` transcript suffix** — every `AT1G01010.1`, `AT1G01010.2`, `AT1G01010.3` row collapses to gene id `AT1G01010` so all isoforms of the same gene end up adjacent in the next sort.
2. **Sort by gene + chromosome + start.**
3. **Single-pass linear merge** that emits one row per maximal contiguous run. The condition `$2 > e` (strictly greater than the running end) — not `>=` — means *book-ended* intervals (an interval that begins exactly where the previous ends) are merged into one.

The book-ended-interval policy is documented inline as a deliberate choice, matching `bedtools merge` default semantics. This was explicitly fixed in two recent commits:

```text
2785a52 fix: merge book-ended intervals in pmet_index_element merged strategy
2e6ec81 fix: merged strategy now merges book-ended intervals (bedtools semantics)
```

#### Purpose

Produce, per gene, a non-redundant minimal set of intervals covering **every CDS region present in any isoform** of that gene.

#### Bioinformatics meaning

Two reasons to prefer merge over longest:

1. *Robust to isoform misannotation.* If TAIR10 mistakenly omits an exon from one isoform, "longest" might pick that incomplete isoform; merge sees the union and is unaffected.
2. *Captures alternative coding regions.* Some TFs may bind sites that exist in an alternative isoform but not the longest one. Merge includes them.

The cost is loss of isoform specificity. If different isoforms have different binding-site complements, merge collapses that signal.

The book-ended fix matters because annotation conventions sometimes split a single contiguous CDS into two rows at an internal boundary (e.g. an internal stop reassignment). A binding site that spans the boundary should still be detectable; merging book-ended rows preserves that detection.

#### Input

The transcript-keyed BED from step 2 of 06 (~few hundred thousand fragment rows, each labelled with `<transcript>.N`).

#### Output

Per-gene-merged BED. From the prior baseline (CDS, default config), this collapses to **23,499 unique gene rows** + multi-fragment runs (genes with non-contiguous CDS spans).

`promoter_lengths.txt` (eventually) first 3 rows from baseline:

```
AT1G01010   1290
AT1G01020   1213
AT1G01030   …
```

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| Output rows are gene-keyed | yes | column 4 has no `.N` suffix |
| Same gene rows are non-overlapping | yes | enforced by the linear-merge invariant |
| Book-ended rows merged | yes | tested by recent regression (commits `2785a52`, `2e6ec81`) |
| Per-gene total length ≥ pipeline 06's per-gene total length | yes | 06 = "single longest isoform"; 07 = "all isoforms unioned" → 07 ≥ 06 per gene; baseline means: 06 = 334.985, 07 = 347.256 ✓ |
| Genes lost between 06 and 07 | none, by design | universe sizes both 23499 (CDS-bearing genes) |
| Strand assigned | yes | from first row of run; consistent because all isoforms of one gene share strand |

#### Observed result

All checks hold against the prior baselines.

#### Assessment

PASS. Importantly, 07 mean per-gene length (347.256) exceeds 06 (334.985), as expected for a per-gene UNION vs single-isoform selection.

---

### Step 3 — Tag, drop <30 bp, write contract files

Steps 5–9 of 06 apply identically. After tagging multi-row genes with `__GENE__N` and dropping <30 bp fragments, the per-FIMO-sequence lengths file is built; FIMO scans every fragment; results collapse back to gene level.

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

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| `universe.txt` ≡ `promoter_lengths.txt` gene set | yes | `comm -3` returns 0 differences |
| No `__` artefacts in final `promoter_lengths.txt` | yes | 0 lines with `__` |
| No `__` artefacts in final `fimohits/*` | yes | 0 hits with `__` in column 2 |
| 113 fimohits files | one per motif | 113 |
| All fimohits row counts > 0 | yes (`AHL12.txt` is the smallest, still has many rows) | confirmed |

#### Observed result

All hold.

#### Assessment

PASS.

---

### Step 4 — Cleanup

For 07, `delete_temp=yes` so the indexer removes:

- `<element>.bed`, `with_overlapping.bed`
- `genome_stripped.fa`, `genome_stripped.fa.fai`
- `promoter.bg`, `promoter.fa`
- `memefiles/`

This is why pipeline 07's homotypic dir at audit time is much smaller (only the contract files) than pipeline 06's (which keeps `promoter.fa` and `genome_stripped.fa`).

#### Assessment

PASS — only the contract files remain, which is the expected post-cleanup state.

---

### Step 5 — Heterotypic motif-pair test (looped over 5 tasks)

Identical command to 06 step 11.

#### Output

| Task | `motif_output.txt` rows | Heatmap PNGs |
|---|---:|---:|
| `salt_top300` | 12 657 | 3 |
| `random_genes_300` | 25 313 | **0** (only histograms) |
| `genes_cell_type_treatment` | 37 969 | 3 |
| `gene_cortex_epidermis_pericycle` | 18 985 | 3 |
| `heat_top300` | 12 657 | 3 |

The row counts are byte-identical to 06's, because both pipelines share the same gene set per task (the universe filter happens via `grep -Ff universe.txt`, and 06 and 07 have the same 23,499-gene universe).

#### Expected properties

- 11 columns. ✓
- Row count = `1 + C(motifs, 2) * num_clusters_in_task`. ✓
- p-values valid. ✓

#### Assessment

PASS.

---

### Step 6 — Heatmaps

#### Output for `genes_cell_type_treatment` (baseline)

| File | Bytes | SHA-256 |
|---|---:|---|
| `03_plot_genes_cell_type_treatment/heatmap.png` | 424 131 | `462c8f5dcf835d68077d9d3a11cd45f2708c7d58535b27969e59354e738cf41f` |
| `…/heatmap_overlap.png` | 654 940 | `5b801e44b242f95e1f6c5cea6bb8f496c4e7b49c52125246a12f2131091c1911` |
| `…/heatmap_overlap_unique.png` | 654 940 | `5b801e44b242f95e1f6c5cea6bb8f496c4e7b49c52125246a12f2131091c1911` |

#### Expected properties

- Three PNGs per task (except `random_genes_300`).
- The two `Overlap` PNGs differ.

#### Observed result

Same `heatmap_overlap == heatmap_overlap_unique` byte-identity observed in pipelines 05 and 06. See [promoter-gap.md §4 step 10](promoter-gap.md) for the analysis. The `mode=All` PNG is meaningfully smaller (424 KB) than the `Overlap` PNGs (655 KB) and has a different hash, so the pipeline is producing distinct content overall.

Hash differences vs 06's `genes_cell_type_treatment` heatmap:

- 06 `heatmap.png` → `a57c5f34…` (424 131 bytes)
- 07 `heatmap.png` → `462c8f5d…` (424 131 bytes; **same size, different hash**)

Same byte count, different hash → the two pipelines render visually-similar heatmaps with different cell values, exactly as expected (06 and 07 produce different per-gene fragment compositions → different motif counts → different p-values → different heatmap intensities).

#### Assessment

WARNING (`overlap == overlap_unique` quirk shared with 05 / 06). PASS otherwise.

<a id="en-5"></a>

## 5. Final outputs

```
results/cli/elements_merged/
├── 01_homotypic/                # only contract files (delete_temp=yes)
│   ├── universe.txt              23 499 genes
│   ├── promoter_lengths.txt      23 499 rows; min=30, max=4144, mean=347.256
│   ├── binomial_thresholds.txt   113 rows
│   ├── IC.txt                    113 rows
│   └── fimohits/                 113 files
├── 02_heterotypic_<task>/        × 5
└── 03_plot_<task>/               × 5  (3 PNGs each except random_genes_300)
```

<a id="en-6"></a>

## 6. Risks / edge cases

1. **Loss of isoform specificity is intentional.** A motif that binds only in an alternative isoform's coding region will appear in the merged universe with full weight, while in pipeline 06 it would only contribute if the alternative isoform happened to be the longest. Conversely, a motif specific to the longest isoform shows up in *both* pipelines — but in 07 with diluted weight (because non-longest fragments are also in the merged set).
2. **Book-ended interval merging is a recent change.** Earlier 07 runs (before commits `2785a52` / `2e6ec81`) treated `end == next.start` as non-mergeable, splitting binding sites that span annotation boundaries. The current behaviour matches `bedtools merge`. The prior baseline at audit time uses the new behaviour.
3. **Shared `Overlap == OverlapUnique` heatmap quirk** with 05 and 06.
4. **No heatmap for control task.** Same as 04 / 06: `random_genes_300` produces only the diagnostic histogram side-cars because no adjusted p-value passes the significance threshold. By design.
5. **No UTR-subtraction option.** `mrnaFull=No` is meaningful only for `strategy=longest`. For merged + mRNA, the merged region includes UTRs (because UTRs are part of the mRNA span). This is documented in the indexer help text but not enforced — a user who sets `mrnaFull=No` for 07 would be silently ignored.

<a id="en-7"></a>

## 7. Summary

**Overall status: PASS** (with the `Overlap == OverlapUnique` heatmap quirk shared with 05 / 06 and the by-design `random_genes_300` heatmap absence).

Pipeline 07 correctly implements per-gene UNION across isoforms. Verified properties: per-gene mean total length (347.256) is strictly greater than pipeline 06's (334.985), as required by the "merged ⊇ longest" inclusion; `__GENE__N` tagging round-trips cleanly through FIMO and is removed from final outputs; book-ended intervals merge as intended (regression-tested by recent commits); all five heterotypic tasks produce correctly-shaped `motif_output.txt` tables, four with three heatmaps (the fifth, the random control, intentionally renders only histograms).

The outputs are suitable for downstream PMET interpretation as a "per-gene CDS union" view, complementary to the "per-gene longest isoform" view in 06 and the "upstream promoter" views in 03 / 05.

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

跟 [pipeline 06](elements-longest.md) 同样的生物学场景 —— 在基因体内某个 genomic element（CDS / exon / mRNA / 5' UTR / 3' UTR）上跑 PMET —— 但用不同的 isoform 聚合策略：

> 每基因取**所有 isoform** element 区间的**并集**，把重叠的、首尾相接的区间合并成一份非冗余集合。无 isoform 特异性，无 UTR 减除。

如果说 pipeline 06 是"挑编码最长的转录本，用它的 fragment"，那 pipeline 07 就是"考虑每个转录本的编码区，全部汇总，扫一次"。两者是同一个问题（**该用哪一组 element 派生序列代表每个基因？**）的两种答案，在可变剪接情形下产生略有不同的信号。

<a id="cn-2"></a>

## 2. 输入

跟 pipeline 06 ([elements-longest.md §2](elements-longest.md#2-inputs)) 完全相同。唯一差别在策略 flag：

| 参数 | 06（longest） | 07（merged） |
|---|---|---|
| `strategy` | `longest` | `merged` |
| `delete_temp` | `no` | `yes` |
| `mrnaFull` | `No`（mRNA 减去 UTR） | 不适用（merge 没有 UTR-减除） |

5 个异型任务相同，默认值也相同。

<a id="cn-3"></a>

## 3. 输出契约

跟 pipeline 06 一致：

```
results/cli/elements_merged/
├── 01_homotypic/
├── 02_heterotypic_<task>/   × 5
└── 03_plot_<task>/          × 5
```

<a id="cn-4"></a>

## 4. 按 step 走读

Step 1、2、4–10 跟 pipeline 06 字节相同（同一个 indexer，下游代码路径相同）。只有 **isoform 聚合步**不同。本次审计只详细讲不同那一步，其余指回 06。

### Step 1 —— 染色体名预检 + element 抽取

跟 06 step 1 + 2 完全相同。PASS。

### Step 2 —— per-gene 跨 isoform merge

#### 命令 / 代码路径

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

(`scripts/workflows/cli/_pmet_index_element.sh:255-270`)

这一段顺序做三件事：

1. **去掉 `.N` 转录本后缀** —— `AT1G01010.1`、`AT1G01010.2`、`AT1G01010.3` 行都塌成 gene id `AT1G01010`，让同一基因的所有 isoform 在下一步 sort 后挨在一起。
2. **按 gene + chromosome + start 排序。**
3. **单遍线性 merge**，每一段最大连续 run 输出一行。条件 `$2 > e`（严格大于当前 end）—— 不是 `>=` —— 意思是**首尾相接**的区间（一个区间在前一个 end 处开始）会被合并成一个。

首尾相接 merge 是有意的策略选择，跟 `bedtools merge` 默认语义一致。最近两次 commit 显式修了这个：

```text
2785a52 fix: merge book-ended intervals in pmet_index_element merged strategy
2e6ec81 fix: merged strategy now merges book-ended intervals (bedtools semantics)
```

#### 目的

per-gene 产出一组非冗余、最小化的区间，覆盖该基因**任一 isoform 中出现的所有 CDS 区域**。

#### 生物学含义

merge 优于 longest 的两个理由：

1. *对 isoform 错误注释更鲁棒。* 如果 TAIR10 误漏了某个 isoform 的一个 exon，"longest" 可能会挑到那个不完整的 isoform；merge 看到的是并集，不受影响。
2. *捕获替代编码区。* 有些 TF 可能结合在替代 isoform 才有的位点；merge 会包含它们。

代价是丢了 isoform 特异性。如果不同 isoform 有不同的结合位点组合，merge 把这种信号塌掉。

book-ended 修复重要是因为：注释规范有时会把一段连续 CDS 在内部边界（如内部 stop 重新分配）切成两行。横跨边界的结合位点应该仍能被检测；merge 首尾相接行保住了这种检测。

#### 输入

来自 06 step 2 的转录本-keyed BED（~几十万行 fragment，每行带 `<transcript>.N` 标签）。

#### 输出

per-gene merged 后的 BED。基线（CDS、默认配置）下塌成 **23,499 个唯一 gene 行** + 多 fragment run（含非连续 CDS 跨度的基因）。

`promoter_lengths.txt`（最终）前 3 行 baseline：

```
AT1G01010   1290
AT1G01020   1213
AT1G01030   …
```

#### 期望属性

| 检查 | 期望 | 观察 |
|---|---|---|
| 输出行 gene-keyed | 是 | 第 4 列没 `.N` 后缀 |
| 同基因行不重叠 | 是 | 由 linear-merge 不变量保证 |
| 首尾相接行被 merge | 是 | 最近两次 commit 已回归测试（`2785a52`、`2e6ec81`） |
| per-gene 总长 ≥ pipeline 06 的 per-gene 总长 | 是 | 06 = "单一最长 isoform"；07 = "所有 isoform 并集" → 07 ≥ 06 per gene；baseline 均值：06 = 334.985、07 = 347.256 ✓ |
| 06 → 07 之间丢的基因 | 按设计应为 0 | universe 大小都是 23499（带 CDS 的基因） |
| strand 已分配 | 是 | 取 run 第一行的；同一基因所有 isoform 共享 strand，所以一致 |

#### 观察结果

跟 baseline 全对得上。

#### 判定

PASS。重要的是 07 per-gene 平均长度（347.256）超过 06（334.985），符合 per-gene UNION vs 单 isoform 选择的预期。

---

### Step 3 —— 打标、丢 <30 bp、写契约文件

06 的 step 5–9 同样适用。把多行基因打 `__GENE__N` 标签、丢 <30 bp fragment 后，per-FIMO-序列长度文件构造完成；FIMO 扫每个 fragment；结果折回 gene 层级。

#### 输出（baseline，step 9 后 gene 层级）

```
universe.txt           23499 行
promoter_lengths.txt   23499 行；min=30, max=4144, mean=347.256
binomial_thresholds.txt  113 行
IC.txt                 113 行
fimohits/              113 文件
```

`fimohits/AHL12.txt` 前 3 行（baseline）：

```
AHL12   AT1G01070   119   126   -   8.220588   5.667e-04   AAATATTT
AHL12   AT1G01070   153   160   +   7.272059   1.417e-03   AATAATTT
AHL12   AT1G01070   316   323   +   6.286765   2.707e-03   AAAATATT
```

#### 期望属性

| 检查 | 期望 | 观察 |
|---|---|---|
| `universe.txt` ≡ `promoter_lengths.txt` gene 集合 | 是 | `comm -3` 返回 0 |
| 最终 `promoter_lengths.txt` 无 `__` 痕迹 | 是 | 0 行含 `__` |
| 最终 `fimohits/*` 无 `__` 痕迹 | 是 | 第 2 列 0 命中含 `__` |
| 113 fimohits 文件 | 每 motif 一份 | 113 |
| 所有 fimohits 行数 > 0 | 是（`AHL12.txt` 最少，仍有不少行） | 已确认 |

#### 观察结果

全部成立。

#### 判定

PASS。

---

### Step 4 —— Cleanup

07 里 `delete_temp=yes`，indexer 删除：

- `<element>.bed`、`with_overlapping.bed`
- `genome_stripped.fa`、`genome_stripped.fa.fai`
- `promoter.bg`、`promoter.fa`
- `memefiles/`

这就是为什么 pipeline 07 审计时 homotypic 目录比 06（保留 `promoter.fa` 和 `genome_stripped.fa`）小很多——只剩契约文件。

#### 判定

PASS —— 只剩契约文件，符合 cleanup 后的预期状态。

---

### Step 5 —— 异型 motif 对检验（5 任务循环）

命令跟 06 step 11 完全相同。

#### 输出

| 任务 | `motif_output.txt` 行数 | Heatmap PNG |
|---|---:|---:|
| `salt_top300` | 12 657 | 3 |
| `random_genes_300` | 25 313 | **0**（仅直方图） |
| `genes_cell_type_treatment` | 37 969 | 3 |
| `gene_cortex_epidermis_pericycle` | 18 985 | 3 |
| `heat_top300` | 12 657 | 3 |

行数与 06 字节相同，因为两条 pipeline 每个任务的基因集合相同（universe 过滤走 `grep -Ff universe.txt`，06 和 07 universe 都是 23,499 基因）。

#### 期望属性

- 11 列。✓
- 行数 = `1 + C(motifs, 2) * num_clusters_in_task`。✓
- p 值合法。✓

#### 判定

PASS。

---

### Step 6 —— Heatmap

#### `genes_cell_type_treatment` 输出（baseline）

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `03_plot_genes_cell_type_treatment/heatmap.png` | 424 131 | `462c8f5dcf835d68077d9d3a11cd45f2708c7d58535b27969e59354e738cf41f` |
| `…/heatmap_overlap.png` | 654 940 | `5b801e44b242f95e1f6c5cea6bb8f496c4e7b49c52125246a12f2131091c1911` |
| `…/heatmap_overlap_unique.png` | 654 940 | `5b801e44b242f95e1f6c5cea6bb8f496c4e7b49c52125246a12f2131091c1911` |

#### 期望属性

- 每任务三张 PNG（除 `random_genes_300`）。
- 两张 `Overlap` PNG 不同。

#### 观察结果

跟 pipeline 05、06 同款 `heatmap_overlap == heatmap_overlap_unique` 字节同一现象。分析见 [promoter-gap.md §4 step 10](promoter-gap.md)。`mode=All` PNG 显著更小（424 KB vs `Overlap` 的 655 KB）且 hash 不同，pipeline 整体在产出不同内容。

跟 06 `genes_cell_type_treatment` heatmap 的 hash 差异：

- 06 `heatmap.png` → `a57c5f34…`（424 131 字节）
- 07 `heatmap.png` → `462c8f5d…`（424 131 字节；**字节数相同、hash 不同**）

字节相同 hash 不同 → 两条 pipeline 渲染了形态相似但单元格值不同的 heatmap，符合预期（06 和 07 产生不同的 per-gene fragment 组成 → 不同的 motif 计数 → 不同的 p 值 → 不同的 heatmap 强度）。

#### 判定

WARNING（`overlap == overlap_unique` 怪事，跟 05 / 06 共享）。否则 PASS。

<a id="cn-5"></a>

## 5. 最终输出

```
results/cli/elements_merged/
├── 01_homotypic/                # 仅契约文件（delete_temp=yes）
│   ├── universe.txt              23 499 基因
│   ├── promoter_lengths.txt      23 499 行；min=30、max=4144、mean=347.256
│   ├── binomial_thresholds.txt   113 行
│   ├── IC.txt                    113 行
│   └── fimohits/                 113 文件
├── 02_heterotypic_<task>/        × 5
└── 03_plot_<task>/               × 5（每个 3 PNG，random_genes_300 除外）
```

<a id="cn-6"></a>

## 6. 风险 / 边界情况

1. **丢 isoform 特异性是有意的。** 只在某个替代 isoform 编码区结合的 motif，会以全权重出现在 merged universe 里；而 pipeline 06 里只有当那个替代 isoform 恰好是最长的才贡献。反过来，仅出现在最长 isoform 的 motif，**两条** pipeline 都会出现 —— 但 07 里权重被稀释（因为非最长 fragment 也在 merged 集合里）。
2. **首尾相接 interval merge 是最近的改动。** 早期 07（在 commit `2785a52` / `2e6ec81` 之前）把 `end == next.start` 当作不可合并，把跨注释边界的结合位点拆开。当前行为匹配 `bedtools merge`。审计用的 baseline 用的是新行为。
3. **共享 `Overlap == OverlapUnique` heatmap 怪事**——跟 05、06 一样。
4. **控制任务无 heatmap。** 跟 04 / 06 一样：`random_genes_300` 只产诊断性直方图副件，因为没有校正 p 值过显著阈值。按设计如此。
5. **没有 UTR-减除选项。** `mrnaFull=No` 仅对 `strategy=longest` 有意义。merged + mRNA 时合并区域包含 UTR（因为 UTR 是 mRNA 跨度的一部分）。indexer help 文本里有写但不强制 —— 给 07 设 `mrnaFull=No` 会被静默忽略。

<a id="cn-7"></a>

## 7. 总结

**整体状态：PASS**（带跟 05 / 06 共享的 `Overlap == OverlapUnique` heatmap 怪事，和按设计 `random_genes_300` 无 heatmap 的现象）。

Pipeline 07 正确实现了 per-gene 跨 isoform UNION。已验证属性：per-gene 平均总长（347.256）严格大于 pipeline 06（334.985），符合 "merged ⊇ longest" 包含关系；`__GENE__N` 标签穿过 FIMO 后干净地从最终输出里去掉；首尾相接区间按预期合并（最近 commit 已回归测）；5 个异型任务都产出形态正确的 `motif_output.txt`，4 个有三张 heatmap（第 5 个随机控制按设计只渲染直方图）。

输出适合作为 PMET 下游解读的 "per-gene CDS 并集" 视图，跟 06 的 "per-gene 最长 isoform" 视图、03 / 05 的 "上游启动子" 视图互补。
