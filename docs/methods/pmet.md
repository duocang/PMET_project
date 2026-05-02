# PMET method — what the algorithm actually does

**[English](#en) · [汉文](#cn)**

A walkthrough of the two-stage algorithm at the level a bioinformatician needs to interpret the output. For terminology (motif vs hit, IC threshold, raw p vs adj_p_BH, …) see [`docs/glossary.md`](../glossary.md). For the file-level schema produced by indexing, see [`homotypic-contract.md`](homotypic-contract.md).

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Why this algorithm exists](#en-1) | [3. Stage 2 — pairing (heterotypic search)](#en-3) |
| [2. Stage 1 — indexing (homotypic search)](#en-2) | [4. From p-value to interpretation](#en-4) |

<a id="en-1"></a>

## 1. Why this algorithm exists

PMET answers: *which transcription-factor motif **pairs** co-occur in the promoters of a gene set more than chance?* Co-occurrence (both motifs hit the same promoter) is a circumstantial signal that the two TFs may bind cooperatively to drive transcription of that gene set. The algorithm has two stages because the heavy work — scanning every motif against every promoter — depends only on the genome and the motif library, not on the user's gene list. So we do it **once** (indexing) and reuse the index across many gene-list queries (pairing).

<a id="en-2"></a>

## 2. Stage 1 — indexing (homotypic search)

Goal: for each motif, build a small artifact recording "which promoters contain a strong hit and how strong". Reusable forever.

1. **Promoter extraction.** Take the genome FASTA + GFF3, pull the 1 kb upstream of each gene's TSS (default; configurable with `-p`), optionally including the 5'UTR (`-u Yes|No`). Strand-aware: the extracted sequence is reverse-complemented for `-` strand genes so motif matching reads in transcription direction.
2. **Overlap removal.** If two genes' inferred promoter regions overlap (head-to-head or short intergenic), trim each so they're disjoint. The trimmed regions go to `promoter.fa`.
3. **Motif scan.** Run FIMO across `promoter.fa` for each motif in the MEME library. For one (motif, promoter) pair FIMO returns multiple "hits" with positions and per-hit p-values.
4. **Per-promoter score (binomial threshold).** For each (motif, promoter):
   - Take the `maxk` best (lowest-p) hits (default `-k 5`). Compute their geometric-mean p-value `p_geo`.
   - The number of possible motif start positions is `possibleLocations = 2 * (promoter_length - motif_length + 1)` (×2 for both strands).
   - For each `n` from 0 to `maxk`, compute the binomial-CDF probability `P(X ≥ n)` of seeing at least `n` hits with success rate `p_geo` over `possibleLocations` trials.
   - Take the **smallest** `P(X ≥ n)` as the promoter's score for this motif. This rewards "few but extreme hits" and "many moderate hits" symmetrically.
5. **Top-N filter.** For each motif, keep only the `topn` promoters (default `-n 5000`) with the smallest binomial scores. Write the score to `binomial_thresholds.txt` and the per-motif promoter list to `fimohits/<motif>.txt`.

The artifacts written by this stage form the **homotypic contract** — see [`homotypic-contract.md`](homotypic-contract.md).

<a id="en-3"></a>

## 3. Stage 2 — pairing (heterotypic search)

Goal: for each motif pair `(A, B)` and each user-defined gene cluster, score whether `A`'s promoters and `B`'s promoters intersect more inside the cluster than chance predicts.

1. **Universe filter.** Drop any motif whose information content (IC) is below the threshold `-c <X>` (default 4.0). Low-IC motifs hit too many promoters and contaminate the pair statistics.
2. **For each unordered pair `(A, B)`:** intersect the two top-N promoter sets. If the intersection is empty, skip. Optionally a MinHash prefilter (`-m K`, default off) skips pairs whose estimated intersection is below `K`; see [`docs/perf/minhash_calibration.md`](../perf/minhash_calibration.md).
3. **Co-occurrence check.** For each promoter in the intersection, also check that the FIMO hit positions of `A` and `B` overlap (so they can plausibly co-bind). Recompute the binomial score using the overlapping hits; keep the pair only if the score is below both per-motif thresholds from step (4) of indexing.
4. **Hypergeometric test against the user cluster.** Build the contingency table:

   - **N** = universe size (number of promoters with usable indexing data)
   - **K** = number of universe promoters with the pair (the surviving co-occurrence set)
   - **n** = size of the user cluster
   - **k** = number of cluster promoters with the pair (intersection)

   The hypergeometric test asks: under the null "the pair distributes randomly across the universe", what's the probability of seeing ≥ `k` cluster hits? That's the **raw p-value**.
5. **Multiple-testing correction.** With ~10⁶ pairs × N clusters, raw p needs adjustment. Three corrections are reported (see [glossary](../glossary.md) for full definitions):
   - `adj_p_BH` — Benjamini-Hochberg FDR within each cluster. **The column to filter on.** `< 0.05` is the conventional significance call.
   - `adj_p_Bonf` — per-cluster Bonferroni. Stricter; near 1.0 for almost everything.
   - `adj_p_global` — Bonferroni across all (cluster, pair) rows in the file. Used only when you want one globally-comparable rank.

<a id="en-4"></a>

## 4. From p-value to interpretation

A row of `motif_output.txt` after stage 2 looks like (see main README §6 for the full column list and a worked example):

```
cortex   AHL12   AHL12_2   3   248   442   0.784   0.784   1.0   1.0   AT1G05680;…
```

Translation: in cortex (442 cluster genes), 3 had both AHL12 and AHL12_2 in their promoters; 248 background promoters had both pair-positive — the cortex hit rate (3/442 = 0.7 %) is not above the background rate (248/N), so raw p = 0.78 and adj_p_BH = 0.78. **Not a cooperative pair for cortex.**

Treat `adj_p_BH < 0.05` as the call for "cooperative pair worth biological follow-up". The `Genes` column gives concrete cluster genes contributing the co-occurrence — useful for ChIP-validation candidates.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 这套算法解决什么](#cn-1) | [3. 第二阶段 —— pairing（异型搜索）](#cn-3) |
| [2. 第一阶段 —— indexing（同型搜索）](#cn-2) | [4. 从 p 值到结论](#cn-4) |

<a id="cn-1"></a>

## 1. 这套算法解决什么

PMET 回答：*在某个目标基因集合的启动子里，哪些转录因子 motif **对**共现的频率比偶然高？* 共现（两个 motif 都命中同一个启动子）是个间接信号，提示这两个 TF 可能协同结合、共同驱动这组基因的转录。算法分两步，是因为最重的活 —— 把每个 motif 在每个启动子上扫一遍 —— 只取决于基因组和 motif 库，跟用户的基因列表无关。所以**只做一次**（indexing），然后跨多个基因列表查询复用同一份索引（pairing）。

<a id="cn-2"></a>

## 2. 第一阶段 —— indexing（同型搜索）

目标：对每个 motif 建一个小工件，记录"哪些启动子有强命中、命中有多强"。一次建好长期复用。

1. **抽启动子。** 拿基因组 FASTA + GFF3，每个基因 TSS 上游 1 kb（默认；`-p` 可改），可选包含 5'UTR（`-u Yes|No`）。链感知：负链基因抽出来的序列做反向互补，让 motif 匹配按转录方向读。
2. **去重叠。** 两个基因推断出的启动子区域若有重叠（head-to-head 或基因间区太短），各自切掉重叠部分让它们互不相交。切完的区域写入 `promoter.fa`。
3. **motif 扫描。** 在 `promoter.fa` 上用 FIMO 跑每一个 MEME 库里的 motif。一个 (motif, 启动子) 对 FIMO 会返回多个 "hit"，带位置和单 hit 的 p 值。
4. **per-promoter 打分（binomial 阈值）。** 对每个 (motif, 启动子)：
   - 取 `maxk` 个最好（p 最小）的 hit（默认 `-k 5`）。算它们的几何平均 p 值 `p_geo`。
   - 可能的 motif 起始位置数 `possibleLocations = 2 * (promoter_length - motif_length + 1)`（×2 是因为两条链都要扫）。
   - 对 `n` 从 0 到 `maxk`，算 binomial-CDF 概率 `P(X ≥ n)`，即在 `possibleLocations` 次试验里、成功率 `p_geo`、看到至少 `n` 次命中的概率。
   - 取**最小**的 `P(X ≥ n)` 作为这个启动子在这个 motif 下的得分。这种打分对"少而极强的 hit"和"多而中等的 hit"都给好分，对称友好。
5. **Top-N 过滤。** 每个 motif 只留打分最低（最显著）的 `topn` 个启动子（默认 `-n 5000`）。打分写入 `binomial_thresholds.txt`，per-motif 启动子清单写入 `fimohits/<motif>.txt`。

这一阶段写出来的文件构成 **homotypic 契约** —— 见 [`homotypic-contract.md`](homotypic-contract.md)。

<a id="cn-3"></a>

## 3. 第二阶段 —— pairing（异型搜索）

目标：对每个 motif 对 `(A, B)` 和每个用户给的基因 cluster，判断 `A` 的启动子和 `B` 的启动子在 cluster 内的交集是否显著高于偶然。

1. **Universe 过滤。** 信息量 IC 低于阈值 `-c <X>`（默认 4.0）的 motif 全部丢掉。低 IC motif 命中太多启动子，会把 pair 统计搅成噪声。
2. **对每个无序对 `(A, B)`：** 对两个 top-N 启动子集合取交。空集就跳过。可选的 MinHash 粗筛（`-m K`，默认关）会跳过估计交集低于 `K` 的 pair；详见 [`docs/perf/minhash_calibration.md`](../perf/minhash_calibration.md)。
3. **共现检查。** 对交集里每个启动子，再确认 `A` 与 `B` 的 FIMO hit 位置有重叠（这样物理上两 TF 才能共结合）。用重叠的 hit 重算 binomial 得分；只有得分同时低于 indexing 第 (4) 步算的两个 motif 各自的阈值，这个 pair 才保留。
4. **对用户 cluster 做超几何检验。** 列联表：

   - **N** = universe 大小（有可用 indexing 数据的启动子总数）
   - **K** = universe 中带这个 pair 的启动子数（共现检查通过的集合）
   - **n** = 用户 cluster 大小
   - **k** = cluster 中带这个 pair 的启动子数（交集）

   超几何问的是：原假设"这个 pair 在 universe 上随机分布"下，看到 ≥ `k` 个 cluster 命中的概率。这就是 **raw p 值**。
5. **多重检验校正。** ~10⁶ 个 pair × N 个 cluster，raw p 必须校正。报三套（完整定义见[词典](../glossary.md)）：
   - `adj_p_BH` —— per-cluster 的 Benjamini-Hochberg FDR。**这是要拿来过滤的列。** 习惯阈值 `< 0.05`。
   - `adj_p_Bonf` —— per-cluster Bonferroni。更严，绝大多数贴近 1.0。
   - `adj_p_global` —— 整个文件里所有 (cluster, pair) 一起做 Bonferroni。仅在想要一个全局可比排名时用。

<a id="cn-4"></a>

## 4. 从 p 值到结论

阶段 2 跑完，`motif_output.txt` 一行长这样（完整列说明 + 翻译详见主 README §6）：

```
cortex   AHL12   AHL12_2   3   248   442   0.784   0.784   1.0   1.0   AT1G05680;…
```

翻译：cortex（442 个 cluster 基因）里 3 个的启动子同时命中 AHL12 和 AHL12_2；背景的 248 个启动子同时命中 —— cortex 命中率（3/442 = 0.7 %）不高于背景率（248/N），所以 raw p = 0.78、adj_p_BH = 0.78。**对 cortex 来说这不是协同对。**

`adj_p_BH < 0.05` 当作"值得做生物学跟进的协同对"的判定线。`Genes` 列给出贡献共现的具体 cluster 基因 —— 挑 ChIP 验证候选时直接从这里抓。
