# pair_only — re-pair an existing homotypic index

**[English](#en) · [汉文](#cn)**

_Audit refreshed 2026-05-02 14:14:05 UTC on this machine — workflow `pair_only`, exit 0, 13.9s_

**Source:** [`scripts/workflows/pair_only.sh`](../../scripts/workflows/pair_only.sh)
&nbsp;&nbsp;**Used by:** CLI re-runs · web `promoters_pre` mode (`apps/pmet_backend/services/executor.py` SCRIPT_MAP)

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose](#en-1) | [4. Reproducing this audit](#en-4) |
| [2. Biological setup](#en-2) | [→ Run snapshot, worked example & verification](#run) |
| [3. What the script does, step by step](#en-3) | |

<a id="en-1"></a>

## 1. Purpose

Skip the expensive **homotypic indexing** stage and run only the **heterotypic** pair-enrichment + heatmap stages against an index that already exists on disk. Two real situations this serves:

1. **Re-pair the same index against a different gene list / IC threshold.** Indexing TAIR10 with the Franco-Zorrilla 113-motif set takes ~2 minutes wall and dominates the cost; `pairing_parallel` against an already-indexed universe finishes in seconds. Iterating on the gene list (e.g. trying different cluster definitions) means re-pairing only.

2. **Web "Pre-computed Promoters" mode.** The species/motif-database indexes are built offline once (16 GB on disk for `data/precomputed_indexes/`) and shipped to the server; user submissions only carry a gene list plus parameters. The backend dispatches that submission to this same `pair_only.sh` (see `apps/pmet_backend/services/executor.py`).

<a id="en-2"></a>

## 2. Biological setup

A "homotypic index" is the cached output of motif scanning over a fixed promoter universe (or interval set). For each motif `m`, the index records every position in every promoter where `m` was found, along with:

- `binomial_thresholds.txt` — per-motif p-value cutoff such that only the top ≈`topn` hits across the universe survive (`--topn 5000` is the canonical choice).
- `IC.txt` — per-motif positional information content, used by `pairing_parallel` as a sanity floor (skip motifs less informative than `-i <ic_threshold>`).
- `fimohits/<MOTIF>.{txt,bin}` — the per-motif hit list. Modern indexes produced by `indexing_fimo_fused` are PMETBN01 binary (`.bin`); older text-format indexes (`.txt`) are still accepted by `pairing_parallel`, and the bundled `data/demos/promoters/pairing/demo` fixture uses text.
- `promoter_lengths.txt`, `universe.txt` — universe metadata.

The schema is defined in [`docs/methods/homotypic-contract.md`](../methods/homotypic-contract.md).

`pair_only` then asks, **for the user's gene list `G` against this universe**: which motif pairs `(m1, m2)` co-occur in `G`'s promoters more often than chance? The test is per-cluster (gene-list rows have an optional cluster label in column 1) and produces one row per `(cluster, m1, m2)` triple in `motif_output.txt`.

<a id="en-3"></a>

## 3. What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + binary preflight | locate `build/pairing_parallel`, validate `-d` dir | Fail fast if the binary or index is missing — much clearer than `pairing_parallel`'s own missing-file errors |
| 2 | Index validation | check `<index>/{universe,promoter_lengths,binomial_thresholds,IC,fimohits/}.txt` | Ensures the supplied dir is a complete homotypic index. **Note:** the script intentionally does NOT invoke `check_homotypic_contract.py` here — the canonical demo `data/demos/promoters/pairing/demo` ships only 6 fimohits files for ~110 thresholds, which is valid for that fixture but would fail the strict contract |
| 3 | Gene-list filter | `grep -wFf universe.txt <gene_list>` → `genes_used_PMET.txt` + `genes_not_found.txt` | Word-boundary `-w` defends against substring collisions (e.g. AT1G01010 ⊂ AT1G010100). Records both kept and dropped genes for diagnostics |
| 4 | Heterotypic pair test | `build/pairing_parallel -d <index> -g <kept_genes> -i <ic_thr> ...` | The actual binomial-vs-hypergeometric pair test. Produces per-thread `temp*.txt` shards |
| 5 | Shard aggregation | `cat temp*.txt > motif_output.txt` then `rm temp*.txt` | `pairing_parallel` doesn't unify shards itself; the script does it |
| 6 | Heatmaps (optional) | three `Rscript scripts/r/draw_heatmap.R` calls (All / Overlap-unique / Overlap-all) | Skipped silently with a warning if `Rscript` is absent |

<a id="en-4"></a>

## 4. Reproducing this audit

```bash
# Full audit run — regenerates all four docs/workflows/*.md
make test-audit

# Or just this workflow's doc (~15 s for pair_only — fastest of the four)
python3 tests/audit/generate.py pair_only
```

**Needs** — built host binaries (`make build`); the bundled demo index at `data/demos/promoters/pairing/demo/` (ships with the repo); Python 3 standard library; optionally `Rscript`.

**Produces** — overwrites `docs/workflows/pair_only.md` (this file). Working files at `tests/audit/runs/pair_only/` (gitignored). The audit's outputs:

| File | Purpose |
|---|---|
| `motif_output.txt` | enriched motif pairs (one per `cluster, m1, m2`) |
| `genes_used_PMET.txt` | input genes that matched the universe |
| `genes_not_found.txt` | input genes dropped (universe miss) |
| `pmet.log` | `pairing_parallel`'s own log (per-thread progress) |
| `plot/` | optional heatmap PNGs (only if `Rscript` available) |

**How to read it** — see [§Verification](#verification). The verification anchor `motif_output.txt` SHA is captured against `data/demos/promoters/pairing/demo` on this machine. It will only change if the fixture itself changes (motif set or gene list). If `pairing_parallel`'s implementation drifts (or its sort order does) the SHA will differ — that's exactly the regression signal this audit catches.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途](#cn-1) | [4. 重跑此审计](#cn-4) |
| [2. 生物学背景](#cn-2) | [→ 运行快照、推导示例、验证](#run) |
| [3. 脚本逐步做了什么](#cn-3) | |

<a id="cn-1"></a>

## 1. 用途

跳过昂贵的**同型 indexing** 阶段，只对盘上已有索引跑**异型** pair 富集 + heatmap。两种实际场景：

1. **同一份索引换基因列表 / IC 阈值重新配对。** TAIR10 + Franco-Zorrilla 113 motif 集 indexing wall ~2 分钟，是 cost 主导；对已索引的 universe 跑 `pairing_parallel` 是秒级。迭代基因列表（如试不同 cluster 定义）只意味着重新 pairing。

2. **Web "预计算启动子" 模式。** species / motif-database 索引离线一次性建好（`data/precomputed_indexes/` ~16 GB 上盘）发到服务器；用户提交只带一份基因列表加参数。后端把这些提交派给同一份 `pair_only.sh`（见 `apps/pmet_backend/services/executor.py`）。

<a id="cn-2"></a>

## 2. 生物学背景

"同型索引"是 motif 在固定启动子 universe（或区间集）上扫描的缓存输出。每个 motif `m` 的索引记录了它在每个启动子里被找到的每个位置，加上：

- `binomial_thresholds.txt` —— per-motif p 值阈值，使得 universe 内只有 top ≈`topn` 个 hit 过线（`--topn 5000` 是经典选择）。
- `IC.txt` —— per-motif 位置信息量，`pairing_parallel` 当 sanity floor（IC 比 `-i <ic_threshold>` 低的 motif 跳过）。
- `fimohits/<MOTIF>.{txt,bin}` —— per-motif 命中列表。`indexing_fimo_fused` 产的现代索引是 PMETBN01 二进制（`.bin`）；老的文本格式索引（`.txt`）`pairing_parallel` 仍接受，自带的 `data/demos/promoters/pairing/demo` fixture 用文本格式。
- `promoter_lengths.txt`、`universe.txt` —— universe 元数据。

schema 定义在 [`docs/methods/homotypic-contract.md`](../methods/homotypic-contract.md)。

`pair_only` 然后问：**对用户基因列表 `G` 在这个 universe 上**，哪些 motif 对 `(m1, m2)` 在 `G` 的启动子里共现频率高于偶然？检验是 per-cluster 的（基因列表行第 1 列是可选的 cluster 标签），`motif_output.txt` 里 per `(cluster, m1, m2)` 三元组一行。

<a id="cn-3"></a>

## 3. 脚本逐步做了什么

| # | 阶段 | 跑什么 | 为什么 |
|---|---|---|---|
| 1 | 参数 + 二进制预检 | 找 `build/pairing_parallel`，校验 `-d` 目录 | 二进制或索引缺就早 fail —— 比 `pairing_parallel` 自己报缺文件清楚多了 |
| 2 | 索引校验 | 检查 `<index>/{universe,promoter_lengths,binomial_thresholds,IC,fimohits/}.txt` | 确认给的目录是完整同型索引。**注意：** 脚本故意**不**在这里调 `check_homotypic_contract.py` —— 经典 demo `data/demos/promoters/pairing/demo` 只带 6 个 fimohits 文件对 ~110 个 threshold，这对那个 fixture 合法但过不了严格契约 |
| 3 | 基因列表过滤 | `grep -wFf universe.txt <gene_list>` → `genes_used_PMET.txt` + `genes_not_found.txt` | 词边界 `-w` 防子串撞车（如 AT1G01010 ⊂ AT1G010100）。同时记保留和丢的基因供诊断 |
| 4 | 异型 pair 检验 | `build/pairing_parallel -d <index> -g <kept_genes> -i <ic_thr> ...` | 真正的 binomial-vs-hypergeometric pair 检验。产出 per-thread `temp*.txt` shard |
| 5 | shard 聚合 | `cat temp*.txt > motif_output.txt` 再 `rm temp*.txt` | `pairing_parallel` 自己不合并 shard；脚本干 |
| 6 | heatmap（可选） | 三次 `Rscript scripts/r/draw_heatmap.R`（All / Overlap-unique / Overlap-all） | 缺 `Rscript` 静默跳过（带 warning） |

<a id="cn-4"></a>

## 4. 重跑此审计

```bash
# 完整审计 —— 重新生成全部四份 docs/workflows/*.md
make test-audit

# 或者只跑这一个 workflow 的文档（pair_only ~15 秒，是四个里最快的）
python3 tests/audit/generate.py pair_only
```

**需要** —— 编好的 host 二进制（`make build`）；`data/demos/promoters/pairing/demo/` 下的 demo 索引（仓库自带）；Python 3 标准库；可选 `Rscript`。

**产出** —— 覆盖写 `docs/workflows/pair_only.md`（本文件）。工作文件在 `tests/audit/runs/pair_only/`（gitignored）。审计的输出：

| 文件 | 用途 |
|---|---|
| `motif_output.txt` | 富集 motif 对（每 `cluster, m1, m2` 一行） |
| `genes_used_PMET.txt` | 与 universe 匹配上的输入基因 |
| `genes_not_found.txt` | 被丢的输入基因（universe miss） |
| `pmet.log` | `pairing_parallel` 自己的日志（per-thread 进度） |
| `plot/` | 可选 heatmap PNG（仅在 `Rscript` 在的时候） |

**怎么解读** —— 见 [§Verification](#verification)。验证 anchor `motif_output.txt` SHA 是本机对 `data/demos/promoters/pairing/demo` 抓的。只要 fixture 本身（motif 集或基因列表）不变，SHA 就不变。`pairing_parallel` 的实现漂移（或排序顺序变）SHA 就不一样 —— 这正是本审计要抓的回归信号。

---

<a id="run"></a>

## Run snapshot · 运行快照

This audit just ran:

```
bash scripts/workflows/pair_only.sh -d data/demos/promoters/pairing/demo -g data/demos/promoters/pairing/demo/gene.txt -o /Users/nuioi/projects/pmet/tests/audit/runs/pair_only/out -i 4 -t 4
```

into `tests/audit/runs/pair_only/out/`. Outputs landed at:

| File | Purpose |
|---|---|
| `tests/audit/runs/pair_only/out/motif_output.txt` | enriched motif pairs (one per `cluster, m1, m2`) |
| `tests/audit/runs/pair_only/out/genes_used_PMET.txt` | input genes that matched the universe |
| `tests/audit/runs/pair_only/out/genes_not_found.txt` | input genes dropped (universe miss) |
| `tests/audit/runs/pair_only/out/pmet.log` | `pairing_parallel`'s own log (per-thread progress) |
| `tests/audit/runs/pair_only/out/plot/` | optional heatmap PNGs (only if `Rscript` available) |

### Output preview · 输出预览

`motif_output.txt` first 3 rows:

```
Cluster	Motif 1	Motif 2	Number of genes in cluster with both motifs	Total number of genes with both motifs	Number of genes in cluster	Raw p-value	Adjusted p-value (BH)	Adjusted p-value (Bonf)	Adjusted p-value (Global Bonf)	Genes
cortex	AHL12	AHL12_2	3	248	442	7.8378943939e-01	7.8378943939e-01	1.0000000000e+00	1.0000000000e+00	AT1G05680;AT2G20120;AT4G02170;
cortex	AHL12	AHL12_3ARY	16	744	442	1.7982386779e-01	3.3716975210e-01	1.0000000000e+00	1.0000000000e+00	AT1G44170;AT1G52760;AT1G62660;AT1G62975;AT1G65840;AT2G02780;AT2G15960;AT2G26690;AT2G46930;AT3G24120;AT3G55720;AT4G10390;AT4G12520;AT5G02230;AT5G23220;AT5G28010;
```

Schema (tab-separated): `cluster ⟶ motif1 ⟶ motif2 ⟶ overlap_count ⟶ expected ⟶ p_value ⟶ p_adj ⟶ ...`. Higher rows = stronger enrichment, lower p-values.

### Worked example · 推导示例

Workflow output written one row per `(cluster, motif1, motif2)`. Picking the first data row of `motif_output.txt` from the pair_only audit (prefers a row with k > 0 when one exists) and unpacking what each number means + how the reported p-value would be derived from the inputs.

**The row:**

```
cortex	AHL12	AHL12_2	3	248	442	7.8378943939e-01	7.8378943939e-01	1.0000000000e+00	1.0000000000e+00	AT1G05680;AT2G20120;AT4G02170;
```

**Reading the columns** — quantities the workflow saw at the moment of the test:

- **N** (universe size) = `26,558` — every gene listed in `universe.txt`.
- **n** (cluster size) = `442` — column 6, total genes in cluster `cortex`.
- **K** (universe positives) = `248` — column 5, genes anywhere in the universe whose `AHL12` and `AHL12_2` hits both passed the per-motif binomial threshold.
- **k** (cluster positives) = `3` — column 4, the subset of those that fall inside cluster `cortex`. Specific genes (column 11): `AT1G05680;AT2G20120;AT4G02170`
- Per-motif thresholds (from `binomial_thresholds.txt`): `AHL12` → `0.153980984861269`; `AHL12_2` → `0.210630832416030`. These are the per-motif p-value cutoffs that decided which fimohits made it into the K set.

**Hypergeometric computation, from those four numbers:**

```
P(X >= k | N, K, n) = P(X >= 3 | N=26558, K=248, n=442)
                    = sum_{i=3}^{min(K,n)=248}  C(K,i) * C(N-K, n-i) / C(N, n)
                    = 7.837894e-01     ← independently recomputed here from k/K/n/N
vs reported raw_p   = 7.837894e-01     ← column 7 of the row above
```

After BH correction across every pair tested in cluster `cortex`, `adj_p_BH` settles at `0.7838` (column 8) — **not significant** at α = 0.05. 

_The recomputed and reported raw-p match to within numerical precision; any drift here would mean the C++ hypergeometric implementation has diverged from the textbook formula._

<a id="verification"></a>

## Verification · 验证

⚠️ **PASS WITH WARNINGS** — 2 warning(s), 6 pass(es)

| # | Check | Expected | Observed | Verdict |
|---|---|---|---|---|
| 1 | script exit code | `0` | `0` | ✅ PASS |
| 2 | motif_output.txt non-empty | `>= 1` | `46` | ✅ PASS — rows = enriched motif pairs after pairing_parallel filtering |
| 3 | motif_output deterministic vs anchor | `0af5b936606fd30f3e4989c3658170e93e208d1277fa97882a2e83c130a83d8f` | `0af5b936606fd30f3e4989c3658170e93e208d1277fa97882a2e83c130a83d8f` | ✅ PASS — captured against data/demos/promoters/pairing/demo on this host; will differ if the fixture changes |
| 4 | genes_used_PMET.txt non-empty | `>= 1` | `1347` | ✅ PASS — genes from -g that survived the universe filter |
| 5 | pmet.log non-empty | `>= 1` | `32` | ✅ PASS |
| 6 | input index contract: binomial == IC motifs | `set equal` | `|both|=113` | ✅ PASS |
| 7 | input index contract: binomial == fimohits motifs | `set equal` | `only_binomial=['AHL25', 'AHL25_2', 'AHL25_3ARY']..., only_fimohits=[]` | ⚠️ WARN — motif-set mismatch — see note above |
| 8 | input index contract: IC == fimohits motifs | `set equal` | `only_IC=['AHL25', 'AHL25_2', 'AHL25_3ARY']..., only_fimohits=[]` | ⚠️ WARN — motif-set mismatch — see note above |
