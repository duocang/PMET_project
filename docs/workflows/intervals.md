# intervals — full PMET on user-supplied genomic intervals

**[English](#en) · [汉文](#cn)**

_Audit refreshed 2026-05-02 14:14:47 UTC on this machine — workflow `intervals`, exit 0, 14.4s_

**Source:** [`scripts/workflows/intervals.sh`](../../scripts/workflows/intervals.sh)
&nbsp;&nbsp;**Used by:** CLI research runs · web `intervals` mode

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

Run the complete PMET pipeline (homotypic indexing **+** heterotypic pair test **+** heatmaps) starting from a user-supplied **interval FASTA** rather than a genome + annotation. Intervals here means **arbitrary sequence regions named by the user** — most commonly ATAC-seq peaks, ChIP-seq peaks, conserved elements, or any other non-promoter region the user wants to scan.

The motivation is: PMET's promoter pipeline only makes sense for genes with well-defined TSSs and annotated 5' UTRs. For peak-based assays the natural unit is the peak itself, not "the 1 kb upstream of a gene". `intervals.sh` accepts those peak sequences directly.

<a id="en-2"></a>

## 2. Biological setup

Each FASTA record is treated as one independent sequence (the analogue of one promoter in `promoter.sh`). The "universe" is the set of all interval names; the user's `peaks.txt` then defines a sub-cluster within that universe.

A subtlety: FIMO's input parser and PMET's binary fimohits format don't tolerate `:` characters in sequence names (FIMO mis-parses the header, the binary records are length-prefixed so a sed restore would shift bytes). Two sed passes handle this:

- On the input FASTA: `sed 's/^\(>.*\):/\1__COLON__/g'` rewrites the **last `:` on each header line** (the `\(.*\)` is greedy + the `^>` anchor restricts the match to header lines). Body sequence lines are untouched. For the typical `>chr:start-end(strand)` IDs there's only one `:` per header, so "last" coincides with "the only one"; multi-colon names get only their final `:` rewritten — anything earlier is preserved.
- On the user's gene list: `sed 's/:/__COLON__/g'` rewrites **every `:`**, since there are no header markers to anchor against and the list is line-per-name.

After indexing + pairing, only the user-facing text outputs (`motif_output.txt`, `genes_used_PMET.txt`, `genes_not_found.txt`) are restored to `:` — **binary fimohits stay sanitised internally**.

<a id="en-3"></a>

## 3. What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + binary preflight | locate `build/{indexing_fimo_fused, pairing_parallel}` | Single failure point if either binary is missing |
| 2 | Interval sanitization | `sed 's/^\(>.*\):/\1__COLON__/g'` over input FASTA | See "biological setup" above — FIMO/binary safety |
| 3 | Dedupe + lengths | `scripts/python/deduplicate.py` then `parse_promoter_lengths_from_fasta.py` | Drops duplicate sequences, writes per-interval lengths to `promoter_lengths.txt`, derives `universe.txt` from it |
| 4 | Background model | `fasta-get-markov` over the sanitized FASTA | Zero-order Markov base composition; FIMO uses it as the null model so p-values are calibrated against the user's actual interval composition |
| 5 | IC.txt | `scripts/python/calculateICfrommeme_IC_to_csv.py` | Per-motif positional information content; `pairing_parallel` uses this as a sanity floor |
| 6 | FIMO + indexing | one `indexing_fimo_fused` call (OpenMP-batched) | Replaces an older shell-level for-loop that forked one fimo per motif. Writes `binomial_thresholds.txt` + `fimohits/<MOTIF>.bin` (PMETBN01 binary) |
| 7 | Indexing contract validation | `scripts/python/check_homotypic_contract.py <indexing_dir>` | Asserts the schema in `docs/methods/homotypic-contract.md` holds — catches motif-id case mismatches and missing files early |
| 8 | Gene-list filter | `sed` colon sanitize → `grep -wFf universe.txt` | Match user's `peaks.txt` against the sanitized index universe |
| 9 | Heterotypic pair test | `build/pairing_parallel -d <index> -g <kept> ...` → temp shards | The actual pair enrichment |
| 10 | Shard aggregation + colon restore | `cat temp*.txt > motif_output.txt`, then `sed 's/__COLON__/:/g'` over the user-facing text outputs | Final `motif_output.txt` has the user's original `chr:start-end(strand)` interval names back |
| 11 | Heatmaps (optional) | three `Rscript scripts/r/draw_heatmap.R` calls | Skipped silently if `Rscript` is absent |

<a id="en-4"></a>

## 4. Reproducing this audit

```bash
# Full audit run — regenerates all four docs/workflows/*.md
make test-audit

# Or just this workflow's doc (~16 s for intervals alone)
python3 tests/audit/generate.py intervals
```

**Needs** — built host binaries (`make build`); the bundled demo inputs at `data/demos/intervals/` (ship with the repo, no fetch needed); Python 3 standard library; optionally `Rscript`.

**Produces** — overwrites `docs/workflows/intervals.md` (this file). Working files at `tests/audit/runs/intervals/` (gitignored).

**How to read it** — see [§Verification](#verification). PASS means the SHA of `motif_output.txt` matches the anchor for `data/demos/intervals` recorded on this machine. Both the demo data and `pairing_parallel`'s output are deterministic — any SHA drift is a real regression signal.

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

跑完整 PMET pipeline（同型 indexing **+** 异型 pair 检验 **+** heatmap），从用户给的**区间 FASTA** 开始，而不是基因组 + 注释。这里的"区间"指**用户命名的任意序列区域** —— 最常见的是 ATAC-seq peak、ChIP-seq peak、保守元件，或任何用户想扫的非启动子区域。

动机：PMET 启动子 pipeline 只对有明确 TSS、有注释 5' UTR 的基因有意义。peak 类 assay 的天然单元是 peak 本身，不是"基因上游 1 kb"。`intervals.sh` 直接吃这些 peak 序列。

<a id="cn-2"></a>

## 2. 生物学背景

每条 FASTA record 当作一条独立序列（相当于 `promoter.sh` 里的一个启动子）。"universe" 是所有 interval 名的集合；用户的 `peaks.txt` 在这个 universe 里再定义子 cluster。

一个细节：FIMO 的输入 parser 和 PMET 的二进制 fimohits 格式都不接受序列名里的 `:`（FIMO 会把 header 解析错；二进制 record 是 length-prefixed 的，sed 还原会让字节错位）。两次 sed 处理：

- 对输入 FASTA：`sed 's/^\(>.*\):/\1__COLON__/g'` 改写**每行 header 里最后一个 `:`**（`\(.*\)` 贪婪 + `^>` 锚把匹配限定在 header 行）。序列体行不动。典型的 `>chr:start-end(strand)` ID 一行只有一个 `:`，"最后一个"就是"唯一一个"；多冒号名只有最末那个被改写，前面的保留。
- 对用户基因列表：`sed 's/:/__COLON__/g'` 改写**每个 `:`**，因为没 header 标记可锚，列表是逐行每行一个名。

indexing + pairing 之后，只有用户面文本输出（`motif_output.txt`、`genes_used_PMET.txt`、`genes_not_found.txt`）会把 `:` 还原 —— **二进制 fimohits 内部保持 sanitised**。

<a id="cn-3"></a>

## 3. 脚本逐步做了什么

| # | 阶段 | 跑什么 | 为什么 |
|---|---|---|---|
| 1 | 参数 + 二进制预检 | 找 `build/{indexing_fimo_fused, pairing_parallel}` | 二进制缺一个就早退 |
| 2 | 区间 sanitization | `sed 's/^\(>.*\):/\1__COLON__/g'` 处理输入 FASTA | 见上 "生物学背景" —— FIMO/二进制安全 |
| 3 | 去重 + 长度 | `scripts/python/deduplicate.py` 然后 `parse_promoter_lengths_from_fasta.py` | 丢重复序列，per-interval 长度写到 `promoter_lengths.txt`，从中派生 `universe.txt` |
| 4 | 背景模型 | `fasta-get-markov` 处理 sanitized FASTA | 零阶 Markov 碱基组成；FIMO 当零分布用，让 p 值按用户实际区间组成校准 |
| 5 | IC.txt | `scripts/python/calculateICfrommeme_IC_to_csv.py` | per-motif 位置信息量；`pairing_parallel` 当 sanity floor |
| 6 | FIMO + indexing | 一次 `indexing_fimo_fused`（OpenMP-batched） | 替代旧的 shell for 循环 fork 一个 fimo per motif。写 `binomial_thresholds.txt` + `fimohits/<MOTIF>.bin`（PMETBN01 二进制） |
| 7 | indexing 契约校验 | `scripts/python/check_homotypic_contract.py <indexing_dir>` | 断言 `docs/methods/homotypic-contract.md` 里的 schema 成立 —— 早抓 motif-id 大小写不一致和缺文件 |
| 8 | 基因列表过滤 | `sed` colon sanitize → `grep -wFf universe.txt` | 把用户 `peaks.txt` 跟 sanitized 索引 universe 对上 |
| 9 | 异型 pair 检验 | `build/pairing_parallel -d <index> -g <kept> ...` → temp shard | 真正的 pair 富集 |
| 10 | shard 聚合 + colon 还原 | `cat temp*.txt > motif_output.txt`，再 `sed 's/__COLON__/:/g'` 处理用户面文本输出 | 最终 `motif_output.txt` 把用户原本的 `chr:start-end(strand)` 区间名还原 |
| 11 | heatmap（可选） | 三次 `Rscript scripts/r/draw_heatmap.R` | 缺 `Rscript` 静默跳过 |

<a id="cn-4"></a>

## 4. 重跑此审计

```bash
# 完整审计 —— 重新生成全部四份 docs/workflows/*.md
make test-audit

# 或者只跑这一个 workflow 的文档（intervals 单跑 ~16 秒）
python3 tests/audit/generate.py intervals
```

**需要** —— 编好的 host 二进制（`make build`）；`data/demos/intervals/` 下自带的 demo 输入（随仓库走，不用 fetch）；Python 3 标准库；可选 `Rscript`。

**产出** —— 覆盖写 `docs/workflows/intervals.md`（本文件）。工作文件在 `tests/audit/runs/intervals/`（gitignored）。

**怎么解读** —— 见 [§Verification](#verification)。PASS 表示 `motif_output.txt` 的 SHA 跟本机录制的 `data/demos/intervals` anchor 一致。demo 数据和 `pairing_parallel` 输出都是确定性的 —— 任何 SHA 漂移都是真回归信号。

---

<a id="run"></a>

## Run snapshot · 运行快照

This audit just ran:

```
bash scripts/workflows/intervals.sh -s data/demos/intervals/indexing/intervals.fa -m data/demos/intervals/indexing/motif.meme -g data/demos/intervals/indexing/peaks.txt -o /Users/nuioi/projects/pmet/tests/audit/runs/intervals/01_indexing -x /Users/nuioi/projects/pmet/tests/audit/runs/intervals/02_pairing -t 4
```

Indexing landed at `tests/audit/runs/intervals/01_indexing/`, pairing at `tests/audit/runs/intervals/02_pairing/`.

### Indexing-stage outputs · 同型阶段产出

| File | Rows / count | Meaning |
|---|---|---|
| `fimohits/*.bin` | 10 files | one PMETBN01 file per motif (10 in `motif.meme`) |
| `binomial_thresholds.txt` | 10 rows | per-motif p-value threshold for `--topn 5000` |
| `IC.txt` | 10 rows | per-motif positional information content |
| `universe.txt` | 26552 rows | every distinct interval name |
| `promoter_lengths.txt` | 26552 rows | should equal `universe.txt` rows |

### Pairing-stage output preview · 异型阶段输出预览

`motif_output.txt` first 3 rows (cluster ⟶ motif1 ⟶ motif2 ⟶ ...):

```
Cluster	Motif 1	Motif 2	Number of genes in cluster with both motifs	Total number of genes with both motifs	Number of genes in cluster	Raw p-value	Adjusted p-value (BH)	Adjusted p-value (Bonf)	Adjusted p-value (Global Bonf)	Genes
U	CCA1	MYB111	0	745	18	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00
U	CCA1	MYB111_2	0	710	18	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00
```

Total enriched pair rows · 富集对总行数：**46**.

### Worked example · 推导示例

Workflow output written one row per `(cluster, motif1, motif2)`. Picking the first data row of `motif_output.txt` from the intervals audit (prefers a row with k > 0 when one exists) and unpacking what each number means + how the reported p-value would be derived from the inputs.

**The row:**

```
U	MYB111	MYB52	1	426	18	2.5265441579e-01	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	1:49166-49909(-);
```

**Reading the columns** — quantities the workflow saw at the moment of the test:

- **N** (universe size) = `26,552` — every gene listed in `universe.txt`.
- **n** (cluster size) = `18` — column 6, total genes in cluster `U`.
- **K** (universe positives) = `426` — column 5, genes anywhere in the universe whose `MYB111` and `MYB52` hits both passed the per-motif binomial threshold.
- **k** (cluster positives) = `1` — column 4, the subset of those that fall inside cluster `U`. Specific genes (column 11): `1:49166-49909(-)`
- Per-motif thresholds (from `binomial_thresholds.txt`): `MYB111` → `1.129703058000000e-02`; `MYB52` → `1.597146785000000e-02`. These are the per-motif p-value cutoffs that decided which fimohits made it into the K set.

**Hypergeometric computation, from those four numbers:**

```
P(X >= k | N, K, n) = P(X >= 1 | N=26552, K=426, n=18)
                    = sum_{i=1}^{min(K,n)=18}  C(K,i) * C(N-K, n-i) / C(N, n)
                    = 2.526544e-01     ← independently recomputed here from k/K/n/N
vs reported raw_p   = 2.526544e-01     ← column 7 of the row above
```

After BH correction across every pair tested in cluster `U`, `adj_p_BH` settles at `1.0000` (column 8) — **not significant** at α = 0.05. 

_The recomputed and reported raw-p match to within numerical precision; any drift here would mean the C++ hypergeometric implementation has diverged from the textbook formula._

<a id="verification"></a>

## Verification · 验证

⚠️ **PASS WITH WARNINGS** — 1 warning(s), 12 pass(es)

| # | Check | Expected | Observed | Verdict |
|---|---|---|---|---|
| 1 | script exit code | `0` | `0` | ✅ PASS |
| 2 | fimohits/*.bin per motif | `10` | `10` | ✅ PASS |
| 3 | binomial_thresholds rows == motifs | `10` | `10` | ✅ PASS |
| 4 | IC.txt rows == motifs | `10` | `10` | ✅ PASS |
| 5 | universe.txt non-empty (interval names) | `>= 1` | `26552` | ✅ PASS |
| 6 | promoter_lengths.txt rows == universe size | `26552` | `26552` | ✅ PASS — every interval needs a length row |
| 7 | motif_output.txt non-empty (heterotypic pairs) | `>= 1` | `46` | ✅ PASS |
| 8 | motif_output.txt deterministic vs anchor | `4858412a09198363305a419af01d47a35ff7cfd63a2169dd01aa545f8ff800c6` | `4858412a09198363305a419af01d47a35ff7cfd63a2169dd01aa545f8ff800c6` | ✅ PASS — captured against demo_intervals on this host; differs if fixture or pairing_parallel sort changes |
| 9 | indexing contract: binomial == IC motifs | `set equal` | `|both|=10` | ✅ PASS |
| 10 | indexing contract: binomial == fimohits motifs | `set equal` | `|both|=10` | ✅ PASS |
| 11 | indexing contract: IC == fimohits motifs | `set equal` | `|both|=10` | ✅ PASS |
| 12 | Rscript invoked (3 histogram subdirs present) | `3` | `3` | ✅ PASS |
| 13 | 3 headline heatmap PNGs rendered | `3` | `0` | ⚠️ WARN — R ran but draw_heatmap.R's p-adj filter left nothing to plot (expected on small demo data) |
