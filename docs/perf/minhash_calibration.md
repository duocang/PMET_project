# MinHash prefilter — calibration & default

**[English](#en) · [汉文](#cn)**

Why the MinHash-based pair prefilter is implemented and shipped, but defaults to **off**: a 2026-Q2 sweep on CIS-BP2 found no operating point that gave meaningful speedup without a non-trivial false-negative rate. This doc records the data, the reasoning, and how to re-run.

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. What it is and why](#en-1) | [5. Why the curve looks like this](#en-5) |
| [2. Sweep setup](#en-2) | [6. Numerical consistency check](#en-6) |
| [3. Results — random gene clusters](#en-3) | [7. Decision and knobs](#en-7) |
| [4. Results — heat-stress (real signal)](#en-4) | [8. How to re-run](#en-8) |

<a id="en-1"></a>

## 1. What it is and why

The pair stage (`pair_parallel`) evaluates every motif pair `(i, j)` for co-occurrence enrichment in each gene cluster. With a typical large library like CIS-BP2 (~1.6 k motifs), that is ~1.4 M pairs × N clusters before any gene filtering — most of which can never reach Bonferroni significance because the two motifs barely share any genes in the universe.

To skip those, every motif gets a **128-slot MinHash sketch** over its gene-id support set at load time. For each pair, the C++ side estimates `|genes(i) ∩ genes(j)|` from the sketches and skips the full hypergeometric path when the estimate falls below a configurable threshold:

- Implementation: [`core/pairing/src/utils.cpp:418-438`](../../core/pairing/src/utils.cpp#L418-L438)
- CLI flag: `-m <min_intersection>` (default `0` = off)
- Skipped pairs still emit a dummy `Output` row with `pval = 1.0`, so BH and Bonferroni denominators stay correct — see `recordSkippedPair` and the loop body in `outputParallel`.

This document records the calibration sweep that picked the production default and the policy for when to enable the prefilter.

<a id="en-2"></a>

## 2. Sweep setup

| Parameter | Value |
|---|---|
| Index | `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` |
| Motifs | 1652 |
| Pairs | 1 363 726 |
| Universe | 26 558 promoters |
| Gene files | `data/genes/random_genes_300.txt` (4 random clusters, 1136 genes); `data/genes/heat_top300.txt` (heat_up + heat_down, 600 genes) |
| Significance criterion | adj.p (per-cluster Bonferroni) ≤ 0.05 |
| Hardware | macOS arm64, 8 worker threads |
| Sweep tool | [`apps/cli/scripts/bench/calibrate_minhash.sh`](../../apps/cli/scripts/bench/calibrate_minhash.sh) |
| Analyzer | [`apps/cli/scripts/bench/analyze_minhash_calibration.py`](../../apps/cli/scripts/bench/analyze_minhash_calibration.py) |

Ground truth is the `m=0` (prefilter off) run; every `m>0` run is compared against that set of significant pairs to compute false-negative rate and speedup. False positives are 0 by construction (skipped pairs become dummies with `pval=1.0`).

### Why per-cluster Bonferroni for the significance call

The pair output has three adjusted-p columns. With ~1.4 M pairs × N clusters, the BH (FDR) column collapses every row to high adj.p — no threshold gives a useful ground-truth set. Conversely the global Bonferroni column over-corrects for typical use. The middle option, **per-cluster Bonferroni** (`pval × clusterSize`, column 8 of `motif_output.txt`), is what PMET reports surface and matches the analyst's "is this pair significant in this cluster?" question. Calibration is done against that column at α = 0.05.

<a id="en-3"></a>

## 3. Results — `random_genes_300.txt` (4 random Arabidopsis clusters, 1136 genes)

Ground truth (m=0): **353 pairs at adj.p (per-cluster Bonferroni) ≤ 0.05**.

| m    | runtime (s) | speedup | sig pairs kept | FN  | FN rate |
|-----:|------------:|--------:|---------------:|----:|--------:|
| 0    | 188.3       | 1.00 ×  | 353            | —   | —       |
| 100  | 185.6       | 1.01 ×  | 353            | 0   | 0.00 %  |
| 300  | 184.9       | 1.02 ×  | 353            | 0   | 0.00 %  |
| 600  | 182.0       | 1.03 ×  | 334            | 19  | 5.38 %  |
| 900  | 159.5       | 1.18 ×  | 277            | 76  | 21.53 % |
| 1200 | 125.4       | 1.50 ×  | 176            | 177 | 50.14 % |

False positives: **0 across all m** (skipped pairs become dummy rows with `pval = 1.0`, so the prefilter cannot manufacture significance — sanity check passes).

Per-cluster FN breakdown (`m=900`): random_1 27/50, random_2 36/218, random_3 6/54, random_4 7/31. The loss is roughly proportional to cluster-truth size; no cluster is hit catastrophically harder than the rest.

(Source TSV: `results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__random_genes_300/ANALYSIS.tsv`.)

<a id="en-4"></a>

## 4. Results — `heat_top300.txt` (real biological signal, 2 clusters)

To check that the random-gene curve isn't just noise, the same sweep was re-run on a real heat-stress gene list (heat_up + heat_down, 600 genes total, ~300 each).

Ground truth (m=0): **72 948 pairs at adj.p (per-cluster Bonferroni) ≤ 0.05** — ~200× more than the random-gene case, as expected for a list with real co-regulation signal.

| m    | runtime (s) | speedup | sig pairs kept | FN     | FN rate |
|-----:|------------:|--------:|---------------:|-------:|--------:|
| 0    | 181.9       | 1.00 ×  | 72 948         | —      | —       |
| 100  | 181.4       | 1.00 ×  | 72 946         | 2      | 0.003 % |
| 300  | 177.0       | 1.03 ×  | 72 897         | 51     | 0.070 % |
| 600  | 175.7       | 1.04 ×  | 70 946         | 2 002  | 2.744 % |
| 900  | 152.4       | 1.19 ×  | 59 564         | 13 384 | 18.347 % |
| 1200 | 119.5       | 1.52 ×  | 38 207         | 34 741 | 47.624 % |

False positives: still **0 across all m** (sanity check passes again).

Per-cluster FN at m=600: heat_down 33/552 (6.0 %), heat_up 1969/72396 (2.7 %). The denser cluster loses *relatively* fewer pairs, which makes sense — its truly significant pairs tend to have higher gene-set intersection and are thus less likely to fall under the prefilter floor.

(Source TSV: `results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__heat_top300/ANALYSIS.tsv`.)

**Cross-check verdict.** Real biological signal does *not* shift the operating point in any useful direction: m=300 is still effectively a no-op (3 % speedup), m=600 still trades % speedup for % FN at a roughly 1:1 ratio, and the m≥900 regime still costs a fifth of the truth set or more. The random-gene calibration is a faithful proxy for picking the default.

<a id="en-5"></a>

## 5. Why the curve looks like this

Every motif in CIS-BP2 reports hits in **exactly the top 5 000 genes** (the binomial-threshold cap from indexing). With a universe of 26 558, the expected pairwise gene-set intersection is

```
E[|A ∩ B|] = 5000 × 5000 / 26558 ≈ 941
```

So for a typical pair, MinHash will estimate `|A ∩ B|` near 941 with a binomial-distributed sketch-match count (mean ≈ 13 of 128 slots). To skip a non-trivial fraction of pairs, the threshold m has to approach the typical intersection — which is also where genuinely significant pairs start disappearing. There is no operating point in this regime that gives speed without sacrificing recall.

<a id="en-6"></a>

## 6. Numerical consistency check

Even before deciding the default, we want to confirm the prefilter doesn't silently change the *numbers* on pairs that survive evaluation. The analyzer's `consistency_check()` compares each `m > 0` run column-by-column against the m=0 baseline on non-skipped pairs:

| Column | Behavior |
|---|---|
| 6 — raw p-value | byte-identical on all kept pairs at every m |
| 7 — adj.p (BH / FDR) | drifts by ~10⁻⁴ on ~9 % of kept rows (mathematically expected — see below) |
| 8 — adj.p (per-cluster Bonferroni) | byte-identical on all kept pairs at every m |
| 9 — adj.p (global Bonferroni) | byte-identical on all kept pairs at every m |

The BH drift is correct, not a bug: BH ranks all p-values descending, and the dummy rows (`pval = 1.0`) take the largest-p slots. That pushes every real p-value down by D ranks (where D = number of skipped pairs), so the multiplier `n / (n − rank)` shifts. In every case the drift is *upward* (more conservative); no real pair becomes more significant due to the prefilter. We pin calibration on column 8 (per-cluster Bonferroni), which is the column PMET actually surfaces and is **byte-identical** on kept pairs — so the FN counts in the table above measure pure skip behavior, not numerical contamination.

<a id="en-7"></a>

## 7. Decision and knobs

**Default `PMET_MINHASH_DEFAULT = 0` (prefilter off) — opt-in only.**

The data does not justify any auto-enabled positive default on CIS-BP2:

- `m ≤ 300`: 0 % FN, 1 % speedup → not worth flipping the switch.
- `m = 600`: 5 % FN for 3 % speedup → bad tradeoff.
- `m ≥ 900`: meaningful speedup (18–50 %) but ≥ 22 % FN — unacceptable as a silent default.

The flag, sketch, and dummy-output bookkeeping stay (cost is negligible at load time) so power users who tolerate FN can flip `PMET_MINHASH_MIN=N` on their own hardware. Smaller libraries (< 500 motifs) ship with `m = 0` for a different reason: even at full N²/2 they run in seconds, so the marginal FN risk is also not worth taking.

The workflows source [`scripts/lib/minhash.sh`](../../scripts/lib/minhash.sh). Three env vars (highest priority first):

| Variable | Default | Effect |
|---|---|---|
| `PMET_MINHASH_MIN`       | unset | Force this exact value, skip auto-detection. Set to `0` to disable. |
| `PMET_MINHASH_THRESHOLD` | `500` | Motif count at/above which auto-enable. |
| `PMET_MINHASH_DEFAULT`   | `0`   | Value used when auto-enable kicks in. `0` = ship-as-disabled. |

Worker side: `executor.py` does `env = os.environ.copy()` before spawning the workflow subprocess, so anything set on the worker container's `environment:` in `deploy/docker-compose.yml` propagates automatically.

The bash unit test at [`tests/unit/test_minhash_resolver.sh`](../../tests/unit/test_minhash_resolver.sh) pins the resolver policy. Hooked into `tests/unit/run.sh`.

<a id="en-8"></a>

## 8. How to re-run

```bash
make build                                       # ensure pair_parallel is fresh
NUM_THREADS=8 apps/cli/scripts/bench/calibrate_minhash.sh \
    data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2 \
    data/genes/random_genes_300.txt \
    0 3 5 10 20
apps/cli/scripts/bench/analyze_minhash_calibration.py \
    results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__random_genes_300
```

**Needs** — built `build/pair_parallel` (`make build`); the named precomputed index (`make fetch-data` Tier 2); a gene-list file in two-column format. `bash` + `python3` only on the host.

**Produces** — `results/bench/calibrate/<species>__<library>__<gene-list>/` with one `m=N/` subdir per sweep value (TSVs of pair output) and a top-level `ANALYSIS.tsv` produced by the analyzer. Stdout shows per-m runtime + speedup + FN.

**How to read it** — the `ANALYSIS.tsv` is the data feeding the tables in §3 / §4. Reproduce them by passing the species/library/gene-list combination of interest. When you change the MinHash sketch (the K value, the SplitMix constants, or the sketch construction) re-run the sweep against CIS-BP2 + `random_genes_300.txt` and update the table here.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 这是什么、为什么](#cn-1) | [5. 曲线为什么长这样](#cn-5) |
| [2. Sweep 设置](#cn-2) | [6. 数值一致性检查](#cn-6) |
| [3. 结果 —— 随机基因 cluster](#cn-3) | [7. 决策与开关](#cn-7) |
| [4. 结果 —— 热应激（真实信号）](#cn-4) | [8. 怎么重跑](#cn-8) |

<a id="cn-1"></a>

## 1. 这是什么、为什么

pair 阶段（`pair_parallel`）对每对 motif `(i, j)` 评估它们在每个基因 cluster 内的共现富集。CIS-BP2 这种典型大库（~1.6 k motif）就是 ~1.4 M 对 × N 个 cluster，绝大多数因为两 motif 在 universe 内基因集合本来就几乎不重叠，根本不可能跑到 Bonferroni 显著。

为跳过这些，每个 motif 在加载时建一个 **128 槽的 MinHash sketch**（基于其 gene-id 支持集）。对每对 motif，C++ 端用 sketch 估计 `|genes(i) ∩ genes(j)|`，估值低于可配阈值时跳过完整的超几何路径：

- 实现：[`core/pairing/src/utils.cpp:418-438`](../../core/pairing/src/utils.cpp#L418-L438)
- CLI flag：`-m <min_intersection>`（默认 `0` = 关）
- 跳过的 pair 仍然 emit 一个 dummy `Output` 行 `pval = 1.0`，BH 与 Bonferroni 的分母不变 —— 见 `recordSkippedPair` 和 `outputParallel` 的循环。

本文记录选定生产默认值的 calibration sweep，以及何时启用粗筛的策略。

<a id="cn-2"></a>

## 2. Sweep 设置

| 参数 | 值 |
|---|---|
| Index | `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` |
| Motif 数 | 1652 |
| Pair 数 | 1 363 726 |
| Universe | 26 558 启动子 |
| Gene 文件 | `data/genes/random_genes_300.txt`（4 个随机 cluster，1136 基因）；`data/genes/heat_top300.txt`（heat_up + heat_down，600 基因） |
| 显著判定 | adj.p（per-cluster Bonferroni）≤ 0.05 |
| 硬件 | macOS arm64，8 个 worker 线程 |
| Sweep 工具 | [`apps/cli/scripts/bench/calibrate_minhash.sh`](../../apps/cli/scripts/bench/calibrate_minhash.sh) |
| Analyzer | [`apps/cli/scripts/bench/analyze_minhash_calibration.py`](../../apps/cli/scripts/bench/analyze_minhash_calibration.py) |

Ground truth 是 `m=0`（关粗筛）那次的输出；每次 `m>0` 的运行跟它对比，算 false-negative 率和加速比。false positive 因构造原因为 0（被跳过的 pair 都是 `pval=1.0` 的 dummy）。

### 为什么显著判定用 per-cluster Bonferroni

pair 输出有 3 列校正 p。~1.4 M 对 × N cluster 下，BH（FDR）那列把每行都压成高 adj.p —— 没有阈值能给出有用的 ground-truth 集合。反过来 global Bonferroni 那列对典型用法过严。中间档 **per-cluster Bonferroni**（`pval × clusterSize`，`motif_output.txt` 第 8 列）是 PMET 报告里实际呈现的，也对应分析师"这对 pair 在这个 cluster 里显著吗？"的问法。所以校准就钉在这一列、α = 0.05。

<a id="cn-3"></a>

## 3. 结果 —— `random_genes_300.txt`（4 个随机 Arabidopsis cluster，1136 基因）

Ground truth（m=0）：**353 对 adj.p（per-cluster Bonferroni）≤ 0.05**。

| m    | 用时 (s) | speedup | 留下的 sig pair | FN  | FN 率 |
|-----:|---------:|--------:|----------------:|----:|------:|
| 0    | 188.3    | 1.00 ×  | 353             | —   | —     |
| 100  | 185.6    | 1.01 ×  | 353             | 0   | 0.00 %|
| 300  | 184.9    | 1.02 ×  | 353             | 0   | 0.00 %|
| 600  | 182.0    | 1.03 ×  | 334             | 19  | 5.38 %|
| 900  | 159.5    | 1.18 ×  | 277             | 76  | 21.53 %|
| 1200 | 125.4    | 1.50 ×  | 176             | 177 | 50.14 %|

False positive：**所有 m 都是 0**（被跳过的 pair 是 `pval = 1.0` 的 dummy 行，粗筛无法凭空造出显著 —— sanity check 通过）。

per-cluster FN 分布（`m=900`）：random_1 27/50、random_2 36/218、random_3 6/54、random_4 7/31。损失大致与该 cluster 真值大小成正比，没有哪个 cluster 被打得特别惨。

（源 TSV：`results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__random_genes_300/ANALYSIS.tsv`。）

<a id="cn-4"></a>

## 4. 结果 —— `heat_top300.txt`（真实生物信号，2 个 cluster）

为了确认随机基因那条曲线不是纯噪声，同 sweep 在真实热应激基因列表上重跑了一遍（heat_up + heat_down，共 600 基因，各 ~300）。

Ground truth（m=0）：**72 948 对 adj.p（per-cluster Bonferroni）≤ 0.05** —— 比随机基因那次多 ~200×，符合"真实共调控信号"的预期。

| m    | 用时 (s) | speedup | 留下的 sig pair | FN     | FN 率 |
|-----:|---------:|--------:|----------------:|-------:|------:|
| 0    | 181.9    | 1.00 ×  | 72 948          | —      | —     |
| 100  | 181.4    | 1.00 ×  | 72 946          | 2      | 0.003 %|
| 300  | 177.0    | 1.03 ×  | 72 897          | 51     | 0.070 %|
| 600  | 175.7    | 1.04 ×  | 70 946          | 2 002  | 2.744 %|
| 900  | 152.4    | 1.19 ×  | 59 564          | 13 384 | 18.347 %|
| 1200 | 119.5    | 1.52 ×  | 38 207          | 34 741 | 47.624 %|

False positive：依然**所有 m 都是 0**（sanity check 再次通过）。

per-cluster FN（m=600）：heat_down 33/552（6.0 %）、heat_up 1969/72396（2.7 %）。更密的 cluster 相对损失更少 —— 它真正显著的 pair 通常 gene-set 交集更大、不容易掉到粗筛地板线下。

（源 TSV：`results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__heat_top300/ANALYSIS.tsv`。）

**Cross-check 结论。** 真实生物信号*没有*让操作点向任何有用方向偏：m=300 仍然基本是 no-op（3 % 加速），m=600 仍然按 ~1:1 比例拿 FN 换 speedup，m≥900 仍然要付 ≥1/5 真值集合的代价。随机基因 calibration 是挑默认值的可靠代理。

<a id="cn-5"></a>

## 5. 曲线为什么长这样

CIS-BP2 里每个 motif 都报**正好 top 5 000** 个基因的 hit（indexing 的 binomial 阈值 cap）。universe 26 558 下，期望两两 gene-set 交集是

```
E[|A ∩ B|] = 5000 × 5000 / 26558 ≈ 941
```

所以对典型 pair，MinHash 会把 `|A ∩ B|` 估在 941 附近，sketch match 数服从二项分布（128 槽里平均匹中 ~13 个）。要跳过非平凡比例的 pair，阈值 m 就得逼近这个典型交集 —— 而真显著的 pair 也在那一带开始消失。这个 regime 没有"加速且不损召回"的操作点。

<a id="cn-6"></a>

## 6. 数值一致性检查

定默认值之前还要确认：粗筛不会悄悄改变那些没被跳过、真的算了的 pair 的*数值*。analyzer 的 `consistency_check()` 把每次 `m > 0` 跑出来的非跳过 pair 跟 m=0 baseline 逐列比：

| 列 | 行为 |
|---|---|
| 6 —— raw p | 所有 m 下、所有保留的 pair 都字节相同 |
| 7 —— adj.p（BH/FDR） | ~9 % 的保留行漂移 ~10⁻⁴（数学上可预期，见下） |
| 8 —— adj.p（per-cluster Bonferroni） | 所有 m 下、所有保留的 pair 都字节相同 |
| 9 —— adj.p（global Bonferroni） | 所有 m 下、所有保留的 pair 都字节相同 |

BH 漂移是对的、不是 bug：BH 把所有 p 降序排名，dummy 行（`pval = 1.0`）占据最大 p 的位置。这把每个真实 p 的排名向小推 D 位（D = 跳过的 pair 数），乘子 `n / (n − rank)` 因此偏移。每一处偏移都是*向上*（更保守），没有真实 pair 因为粗筛变得更显著。我们把 calibration 钉在第 8 列（per-cluster Bonferroni）—— PMET 实际呈现的列、且在保留 pair 上**字节相同**，所以上面表里的 FN 数测的是纯跳过行为，不是数值污染。

<a id="cn-7"></a>

## 7. 决策与开关

**默认 `PMET_MINHASH_DEFAULT = 0`（粗筛关）—— 仅 opt-in。**

数据不支持在 CIS-BP2 上 auto-enable 任何正值默认：

- `m ≤ 300`：0 % FN、1 % 加速 → 没必要打开。
- `m = 600`：5 % FN 换 3 % 加速 → 不划算。
- `m ≥ 900`：明显加速（18–50 %），但 FN ≥ 22 % —— 不能作为静默默认。

flag、sketch、dummy 输出簿记都保留（加载时开销可忽略），让能容忍 FN 的 power user 自己在自己硬件上拨 `PMET_MINHASH_MIN=N`。小库（< 500 motif）默认 `m = 0` 是另一个理由：满 N²/2 都是秒级跑完，FN 风险也没必要冒。

workflow 通过 [`scripts/lib/minhash.sh`](../../scripts/lib/minhash.sh) 解析。三个 env var（优先级从高到低）：

| 变量 | 默认 | 效果 |
|---|---|---|
| `PMET_MINHASH_MIN`       | 未设 | 强制此值，跳过自动检测。设 `0` 关粗筛。 |
| `PMET_MINHASH_THRESHOLD` | `500` | motif 数到/超过此值才自动启用。 |
| `PMET_MINHASH_DEFAULT`   | `0`   | 自动启用时使用的值。`0` = 出厂关。 |

worker 侧：`executor.py` spawn workflow 子进程前 `env = os.environ.copy()`，所以 worker 容器 `deploy/docker-compose.yml` 里 `environment:` 设的东西会自然透传过去。

bash 单元测试 [`tests/unit/test_minhash_resolver.sh`](../../tests/unit/test_minhash_resolver.sh) 钉死了 resolver 策略，挂在 `tests/unit/run.sh` 里。

<a id="cn-8"></a>

## 8. 怎么重跑

```bash
make build                                       # 保证 pair_parallel 是新的
NUM_THREADS=8 apps/cli/scripts/bench/calibrate_minhash.sh \
    data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2 \
    data/genes/random_genes_300.txt \
    0 3 5 10 20
apps/cli/scripts/bench/analyze_minhash_calibration.py \
    results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__random_genes_300
```

**需要** —— 编好的 `build/pair_parallel`（`make build`）；指定的预计算索引（`make fetch-data` Tier 2）；两列格式的基因列表文件。host 上只要 `bash` + `python3`。

**产出** —— `results/bench/calibrate/<species>__<library>__<gene-list>/`，每个 sweep 值一个 `m=N/` 子目录（pair 输出 TSV），顶层一份 analyzer 写的 `ANALYSIS.tsv`。stdout 给出 per-m 用时 + 加速比 + FN。

**怎么解读** —— `ANALYSIS.tsv` 就是 §3 / §4 那两张表的数据来源。换个 species/library/gene-list 组合就能复现自己关心的场景。改了 MinHash sketch 实现（K 值、SplitMix 常数、sketch 构造方式）后必须在 CIS-BP2 + `random_genes_300.txt` 上重跑一次 sweep 并更新本文里的表。
