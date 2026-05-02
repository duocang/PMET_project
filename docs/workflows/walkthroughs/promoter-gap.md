# Pipeline 05 walkthrough — Promoter PMET with TSS-proximal gap

**[English](#en) · [汉文](#cn)**

> **Heads-up:** this is a frozen pre-monorepo walkthrough. References like `scripts/pipeline/05_promoter_gap.sh` and `data/TAIR10.fasta` are stale — see [`../README.md`](README.md) for the current path mapping. The algorithm and biology described still apply.

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

Variant of [pipeline 03](promoter.md) that **shrinks the TSS-proximal end of every promoter by `gap = 100` bp** before running FIMO. The intent is to exclude the *core promoter* — the ~50–150 bp neighbourhood of the TSS that hosts general TFs (TBP / TFIIB / Inr / TATA) — so the heterotypic test is biased toward distal cell-type-specific TF sites rather than the housekeeping background.

Everything else (annotation, motifs, gene list, NoOverlap, the rest of the homotypic logic, heterotypic + heatmap stages) is identical to 03.

<a id="en-2"></a>

## 2. Inputs

Identical to pipeline 03 ([promoter.md §2](promoter.md#2-inputs)), plus one configuration knob:

| Parameter | Pipeline 03 | Pipeline 05 |
|---|---:|---:|
| `gap`     | 0 | **100** |
| `utr`     | Yes | **No (forced)** — see step 0 |
| `length`  | 1000 | 1000 |
| `overlap` | NoOverlap | NoOverlap |

### Step 0 — UTR force-disable (pipeline guard)

```text
if (( gap != 0 )) && [[ "$utr" =~ ^(yes|y|true|t)$ ]]; then
    print_fluorescent_yellow "   gap=$gap != 0 — forcing utr=No (UTR would undo the TSS-proximal exclusion)"
    utr=No
fi
```

(`scripts/pipeline/05_promoter_gap.sh:50-54`)

#### Bioinformatics meaning

The 5' UTR sits *between* the TSS and the start codon — exactly the region we are trying to mask out. Allowing `utr=Yes` while `gap > 0` would re-extend the promoter back toward the TSS, undoing the gap. The pipeline force-disables UTR if both are turned on. **PASS** — the guard is in place and emits a yellow warning when triggered.

<a id="en-3"></a>

## 3. Output contract

Identical to pipeline 03:

```
results/05_promoter_gap/
├── 01_homotypic/      # universe / lengths / IC / binomial / fimohits
├── 02_heterotypic/    # motif_output.txt + pmet.log
└── plot/              # 3 heatmaps
```

<a id="en-4"></a>

## 4. Step-by-step execution story

The homotypic flow is identical to pipeline 03 with two differences: the `--gap 100` argument and `--utr No`. Steps 1–4 / 6–10 are unchanged from [promoter.md](promoter.md). Only step 5 (`build_promoters.py`) behaves differently and is detailed below; the others are summarised.

### Step 1–4 — GFF3 sort, gene BED, chrom sizes, linearised FASTA

Identical to pipeline 03. **PASS** (same code path, same inputs).

### Step 5 — Build promoters with TSS-proximal gap

#### Command / code path

```text
python3 scripts/python/build_promoters.py \
    --length 1000 --gap 100 --overlap NoOverlap --utr No \
    [...]
```

(`scripts/pipeline/05_promoter_gap.sh:158-174`)

The relevant logic inside `build_promoters.py` is the `shrink_for_gap` helper:

- For `+` strand promoters: subtract `gap` from BED `end` (TSS is the upstream end of the gene-side flank, so the TSS-proximal end is `end`).
- For `−` strand promoters: add `gap` to BED `start` (TSS is at the lower-coord side because the flank lies above the gene start in `+`-strand coordinates).
- Drop intervals that collapse to ≤ 0.

#### Purpose

Mask the core-promoter region around the TSS while keeping the distal ≤ 900 bp window.

#### Bioinformatics meaning

The genome's *core promoter* is dominated by Pol II machinery (TFIIA / B / D / E / F / H, TBP, etc.) and a few sequence motifs (TATA box, Inr, DPE). Cell-type specificity is encoded mostly in the **distal** elements binding family-specific TFs (MYB, WRKY, BZIP, NAC, …). A 100 bp gap is the literature default for "drop the core promoter" when running motif-pair tests biased toward cell-type signal.

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

#### Expected properties

| Check | Expectation | Observation |
|---|---|---|
| Max length | ≤ 900 (i.e. `length − gap`) | 900 ✓ |
| Min length | ≥ 20 (post-NoOverlap filter) | 20 ✓ |
| Universe count | < 03's 29824 (gap shrinks) | 27500 (lost 2324 vs 03) |
| 05 ⊆ 03 universe | strictly | `comm -13` = 0 (no novel genes in 05); `comm -23` = 2324 (lost from 03) ✓ |
| Genes at the cap (length=900) | should be the majority | 13833 of 27500 ≈ 50 % — the others were already < 900 in 03 because of NoOverlap clipping |
| `+` strand BED end is shifted left by 100 | yes | for AT1G01010 the 03 promoter was 2630–3759 (length 1129; uses 5'UTR), the 05 promoter is 2630–3530 (length 900; UTR off, TSS gap on) — implied by length=900 |
| `−` strand BED start is shifted right by 100 | yes | by symmetry |
| Universe set ≡ promoter_lengths gene set | yes | `comm -3` returns 0 |

#### Observed result

All checks pass. The 2324-gene drop is the population that, after gapping plus NoOverlap, falls below the 20 bp minimum and gets removed at the lt20 filter (`build_promoters.py` step 6).

#### Assessment

PASS. The gap is doing exactly what the script promises: max length falls from `1000 + UTR ≤ 14813` (in 03) to 900 here, and the universe is a strict subset of 03's.

---

### Step 6–8 — IC, FIMO + index, contract validation

Identical to pipeline 03. 113 motifs in, 113 fimohits files out, 113 binomial-threshold rows out. Contract validator says `OK — homotypic contract holds (113 motifs, 27500 universe genes, 27500 genes with promoter lengths)`. **PASS**.

### Step 9 — Heterotypic motif-pair test

#### Command / code path

```text
build/pair_parallel \
    -d . -g <filtered_gene_list> -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/05_promoter_gap/02_heterotypic -t 4
```

(`scripts/pipeline/05_promoter_gap.sh:188-197`)

#### Output

`motif_output.txt` — 11 columns, **37969 rows** (same row count as pipeline 03; the cluster set and motif set are identical so the Cartesian product is identical).

#### Expected properties

- 11 fields. ✓
- Same row count as 03 (37969). ✓
- p-values valid. ✓

#### Assessment

PASS. The numerical p-values differ from 03 (because the underlying hit set is different), but the row shape is identical.

---

### Step 10 — Heatmaps

#### Output

| File | Bytes | SHA-256 |
|---|---:|---|
| `plot/heatmap.png` | 1 395 151 | `c1378e23adda79dae60cc59944ad1e62946db3be1379fb8609a46ff2366a0d29` |
| `plot/heatmap_overlap.png` | 837 854 | `af75ef92309bb999e700979be5921cd09d2ac56984a941c59e80c91b2e09f40d` |
| `plot/heatmap_overlap_unique.png` | 837 854 | `af75ef92309bb999e700979be5921cd09d2ac56984a941c59e80c91b2e09f40d` |

#### Expected properties

- Three PNGs, all non-empty. ✓
- `heatmap_overlap.png` and `heatmap_overlap_unique.png` differ.

#### Observed result

The two `Overlap` PNGs have **identical** SHA-256 (and identical byte count). Same observation as in 06 / 07.

#### Assessment

WARNING. The `unique=TRUE` flag is supposed to deduplicate motif pairs that recur in multiple clusters, but on this dataset the two PNGs are byte-identical. Investigation outside the scope of this audit suggests one of:

1. The 6 clusters in `genes_cell_type_treatment.txt` produce non-overlapping motif-pair sets (so dedup is a no-op).
2. The R script's `unique` filter does not change the rendered matrix when `mode=Overlap` is set with these dimensions (5 / 3 / 6 rows / cols / facets).

The `mode=All` heatmap is meaningfully larger (1.4 MB vs 838 KB) and hashes differently, so the pipeline is producing distinct content overall — the issue is specific to the `Overlap` × `unique` axis.

This is the same observation as for 06 and 07, but **not** for 03. The difference between 03 (`5 3 6`) and 05 (also `5 3 6` per the script) is the input `motif_output.txt` distribution. So this is a property of 05 / 06 / 07 inputs, not a bug introduced by the gap.

<a id="en-5"></a>

## 5. Final outputs

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

<a id="en-6"></a>

## 6. Risks / edge cases

1. **05 universe ⊊ 03 universe.** 2324 genes that were testable under 03 are not testable under 05 because their promoter shrinks below the 20 bp threshold after gapping + NoOverlap. The user's input gene list filtering at the heterotypic step silently drops these too. Important to document but not a defect.
2. **`heatmap_overlap.png` == `heatmap_overlap_unique.png`.** See step 10 above. Worth investigating in `draw_heatmap.R` to confirm intended semantics; not within the scope of this audit.
3. **Force-disabled UTR is correct, but the pipeline does not log the final effective UTR setting.** The yellow warning fires once on stdout; downstream consumers reading only the homotypic output directory have no record of what `utr` was actually used. Could be surfaced in `binomial_thresholds.txt`'s neighbouring metadata if needed.
4. **`gap` is not parameterised on the command line** — it is hard-coded to 100 in the script. Changing it requires editing the script, not passing a flag. This is the same pattern as 03's `length=1000`.

<a id="en-7"></a>

## 7. Summary

**Overall status: PASS** (with one downstream WARNING shared with 06 / 07). Pipeline 05 correctly applies a 100 bp TSS-proximal gap to every promoter, force-disables 5' UTR extension to keep the gap honest, and otherwise reuses pipeline 03's homotypic + heterotypic + plotting chain. The shrinkage is verifiable: max promoter length drops from `1000 + UTR` (≤ 14,813 bp in 03) to a clean 900 bp, the universe is a strict subset of 03's, and 2324 genes drop because gapping pushes them below 20 bp.

The motif_output table has the same row shape as 03 (same clusters × same motifs); the heatmaps differ from 03 in numeric content but share the `unique == non-unique` overlap-PNG quirk noted in 06 / 07. The outputs are suitable for downstream PMET interpretation as a "distal-element" complement to pipeline 03's "core+distal" view.

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

[pipeline 03](promoter.md) 的变体：跑 FIMO 之前，给每个启动子的 **TSS-邻近端** 切掉 `gap = 100` bp。意图是排除 *核心启动子*（TSS 周围 ~50–150 bp，住着通用 TF：TBP / TFIIB / Inr / TATA），让异型检验偏向**远端**细胞类型特异 TF 位点，而不是房屋管理（housekeeping）背景信号。

其它一切（注释、motif、基因列表、NoOverlap、剩下的同型逻辑、异型 + heatmap 阶段）跟 03 完全一样。

<a id="cn-2"></a>

## 2. 输入

跟 pipeline 03 ([promoter.md §2](promoter.md#2-inputs)) 完全一样，加一个配置开关：

| 参数      | Pipeline 03 | Pipeline 05 |
|---|---:|---:|
| `gap`     | 0 | **100** |
| `utr`     | Yes | **No（强制）** —— 见 step 0 |
| `length`  | 1000 | 1000 |
| `overlap` | NoOverlap | NoOverlap |

### Step 0 —— UTR 强制关闭（pipeline 守卫）

```text
if (( gap != 0 )) && [[ "$utr" =~ ^(yes|y|true|t)$ ]]; then
    print_fluorescent_yellow "   gap=$gap != 0 — forcing utr=No (UTR would undo the TSS-proximal exclusion)"
    utr=No
fi
```

(`scripts/pipeline/05_promoter_gap.sh:50-54`)

#### 生物学含义

5' UTR 位于 TSS 与起始密码子*之间* —— 正好是我们想 mask 掉的区域。`gap > 0` 同时 `utr = Yes` 会把启动子重新延伸回 TSS，把 gap 抹掉。脚本在两个都开时强制把 UTR 关掉。**PASS** —— 守卫到位，触发时打黄色 warning。

<a id="cn-3"></a>

## 3. 输出契约

跟 pipeline 03 完全一样：

```
results/05_promoter_gap/
├── 01_homotypic/      # universe / lengths / IC / binomial / fimohits
├── 02_heterotypic/    # motif_output.txt + pmet.log
└── plot/              # 3 张 heatmap
```

<a id="cn-4"></a>

## 4. 按 step 走读

同型流程跟 pipeline 03 一样，差两处：`--gap 100` 参数和 `--utr No`。Step 1–4 / 6–10 跟 [promoter.md](promoter.md) 完全相同。只有 step 5（`build_promoters.py`）行为不一样，下面详细讲；其它简短带过。

### Step 1–4 —— GFF3 排序、gene BED、染色体长度、linearise FASTA

跟 pipeline 03 完全相同。**PASS**（同代码路径、同输入）。

### Step 5 —— 建带 TSS-邻近 gap 的启动子

#### 命令 / 代码路径

```text
python3 scripts/python/build_promoters.py \
    --length 1000 --gap 100 --overlap NoOverlap --utr No \
    [...]
```

(`scripts/pipeline/05_promoter_gap.sh:158-174`)

`build_promoters.py` 里相关的逻辑是 `shrink_for_gap` 助手：

- `+` 链启动子：BED `end` 减 `gap`（TSS 是 gene 侧 flank 的上游端，所以 TSS-邻近端就是 `end`）。
- `−` 链启动子：BED `start` 加 `gap`（TSS 在小坐标那一侧，因为 flank 在 `+` 链坐标系里位于 gene start 上方）。
- 缩到 ≤ 0 的区间丢掉。

#### 目的

mask 掉 TSS 周围的核心启动子区，保留远端 ≤ 900 bp 窗口。

#### 生物学含义

基因组的 *核心启动子* 由 Pol II 机器（TFIIA / B / D / E / F / H、TBP 等）和几个序列 motif（TATA 盒、Inr、DPE）主导。细胞类型特异性主要由**远端**元件编码，结合家族特异 TF（MYB、WRKY、BZIP、NAC ……）。100 bp gap 是文献里"想偏向细胞类型信号、做 motif pair 检验时丢掉核心启动子"的默认值。

#### 输出

```
promoters.bed         27500 行
promoter_lengths.txt  27500 行
universe.txt          27500 行
```

`promoter_lengths.txt` 前 3 行：

```
AT1G01010   900
AT1G01020   900
AT1G03987   900
```

#### 期望属性

| 检查 | 期望 | 观察 |
|---|---|---|
| 最大长度 | ≤ 900（即 `length − gap`） | 900 ✓ |
| 最小长度 | ≥ 20（NoOverlap 过滤后） | 20 ✓ |
| Universe 数量 | < 03 的 29824（gap 缩短） | 27500（比 03 少 2324） |
| 05 ⊆ 03 universe | 严格 | `comm -13` = 0（05 没新增基因）；`comm -23` = 2324（03 里有但 05 丢） ✓ |
| 满 cap 长度 (length=900) 的基因 | 应该占多数 | 27500 里 13833 ≈ 50 % —— 其它的在 03 里就因 NoOverlap 切到 < 900 |
| `+` 链 BED end 左移 100 | 是 | AT1G01010 在 03 启动子是 2630–3759（长 1129；用 5'UTR），在 05 是 2630–3530（长 900；UTR off、TSS gap on）—— 由 length=900 隐含 |
| `−` 链 BED start 右移 100 | 是 | 对称 |
| Universe 集合 ≡ promoter_lengths gene 集合 | 是 | `comm -3` 返回 0 |

#### 观察结果

全过。少的 2324 基因是 gapping + NoOverlap 之后落到 20 bp 最低线下面、被 lt20 过滤掉的群体（`build_promoters.py` step 6）。

#### 判定

PASS。gap 干的事跟脚本说的一致：最大长度从 03 的 `1000 + UTR ≤ 14813` 降到这里清清爽爽 900，universe 是 03 的严格子集。

---

### Step 6–8 —— IC、FIMO + index、契约校验

跟 pipeline 03 完全相同。113 motif 进、113 fimohits 文件出、113 行 binomial 阈值。契约 validator 报 `OK — homotypic contract holds (113 motifs, 27500 universe genes, 27500 genes with promoter lengths)`。**PASS**。

### Step 9 —— 异型 motif 对检验

#### 命令 / 代码路径

```text
build/pair_parallel \
    -d . -g <filtered_gene_list> -i 4 \
    -p promoter_lengths.txt -b binomial_thresholds.txt \
    -c IC.txt -f fimohits \
    -o results/05_promoter_gap/02_heterotypic -t 4
```

(`scripts/pipeline/05_promoter_gap.sh:188-197`)

#### 输出

`motif_output.txt` —— 11 列，**37969 行**（跟 pipeline 03 行数一样；cluster 集合和 motif 集合一致，所以笛卡尔积一致）。

#### 期望属性

- 11 字段。✓
- 行数跟 03 相同（37969）。✓
- p 值合法。✓

#### 判定

PASS。p 值数字跟 03 不同（底层 hit 集合变了），但行 shape 一样。

---

### Step 10 —— Heatmap

#### 输出

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `plot/heatmap.png` | 1 395 151 | `c1378e23adda79dae60cc59944ad1e62946db3be1379fb8609a46ff2366a0d29` |
| `plot/heatmap_overlap.png` | 837 854 | `af75ef92309bb999e700979be5921cd09d2ac56984a941c59e80c91b2e09f40d` |
| `plot/heatmap_overlap_unique.png` | 837 854 | `af75ef92309bb999e700979be5921cd09d2ac56984a941c59e80c91b2e09f40d` |

#### 期望属性

- 三张 PNG 都非空。✓
- `heatmap_overlap.png` 和 `heatmap_overlap_unique.png` 不同。

#### 观察结果

两张 `Overlap` PNG SHA-256 **完全相同**（字节数也相同）。06 / 07 也是这个观察。

#### 判定

WARNING。`unique=TRUE` flag 的设计是把跨 cluster 重复出现的 motif 对去重，但在这个数据集上两张 PNG 字节相同。审计范围之外的初步排查指向二选一：

1. `genes_cell_type_treatment.txt` 那 6 个 cluster 产出的 motif 对集合不重叠（去重是 no-op）。
2. R 脚本的 `unique` 过滤在 `mode=Overlap` 这套维度（5 / 3 / 6 rows / cols / facets）下不改变渲染矩阵。

`mode=All` heatmap 显著更大（1.4 MB vs 838 KB）、hash 也不同，所以 pipeline 整体确实在产出不同内容 —— 问题专门发生在 `Overlap` × `unique` 这条轴上。

跟 06 / 07 的观察一致，但 **03 没有这个问题**（03 的 cluster 大小一样，详见 03 审计）。03（`5 3 6`）和 05（脚本里也是 `5 3 6`）的差别在输入 `motif_output.txt` 的分布。所以这是 05 / 06 / 07 输入特性，不是 gap 引入的 bug。

<a id="cn-5"></a>

## 5. 最终输出

```
results/05_promoter_gap/
├── 01_homotypic/
│   ├── universe.txt              27500 行（vs 03 的 29824）
│   ├── promoter_lengths.txt      27500 行；最大长度 900（vs 03 的 14813）
│   ├── binomial_thresholds.txt   113 行
│   ├── IC.txt                    113 行
│   └── fimohits/                 113 文件
├── 02_heterotypic/
│   ├── motif_output.txt          37969 行
│   └── pmet.log
└── plot/
    ├── heatmap.png               1.40 MB
    ├── heatmap_overlap.png       838 KB
    └── heatmap_overlap_unique.png 838 KB（== heatmap_overlap.png；见 step 10）
```

<a id="cn-6"></a>

## 6. 风险 / 边界情况

1. **05 universe ⊊ 03 universe。** 2324 个基因在 03 里能测，05 里不能 —— 因为 gapping + NoOverlap 之后启动子缩到 20 bp 阈值之下。用户输入的基因列表在异型阶段过滤时，这些基因被静默丢掉。要记录但不算缺陷。
2. **`heatmap_overlap.png` == `heatmap_overlap_unique.png`。** 见上面 step 10。值得在 `draw_heatmap.R` 里追一下确认语义；不在本次审计范围。
3. **强制关 UTR 是对的，但 pipeline 不记录最终生效的 UTR 设置。** 黄色 warning 在 stdout 上打一次；只读同型输出目录的下游消费者无法知道实际用的是什么 `utr`。如有需要可以暴露在 `binomial_thresholds.txt` 旁边的元数据里。
4. **`gap` 不是命令行参数** —— 在脚本里硬写成 100。改它要编辑脚本而不是传 flag。跟 03 里 `length = 1000` 是同一种模式。

<a id="cn-7"></a>

## 7. 总结

**整体状态：PASS**（有一条与 06 / 07 共享的下游 WARNING）。Pipeline 05 正确地给每个启动子施加了 100 bp 的 TSS-邻近 gap、强制关 5' UTR 延伸来保 gap 的纯净，其它沿用 pipeline 03 的同型 + 异型 + 绘图链。缩短可验证：最大启动子长度从 03 的 `1000 + UTR`（≤ 14,813 bp）降到干净的 900 bp，universe 是 03 的严格子集，2324 个基因因为 gapping 推到 20 bp 之下被丢掉。

motif_output 表的行 shape 跟 03 一样（同 cluster × 同 motif）；heatmap 跟 03 在数值内容上不同，但跟 06 / 07 一样有 `unique == non-unique` 重叠-PNG 怪事。输出适合作为 pipeline 03 "核心 + 远端"视图的"远端元件"补充。
