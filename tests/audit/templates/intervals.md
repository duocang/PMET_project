# intervals — full PMET on user-supplied genomic intervals

**[English](#en) · [汉文](#cn)**

<<RUN_HEADER>>

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
<<COMMAND_DISPLAYED>>
```

Indexing landed at `<<INDEXING_DIR>>/`, pairing at `<<PAIRING_DIR>>/`.

### Indexing-stage outputs · 同型阶段产出

| File | Rows / count | Meaning |
|---|---|---|
| `fimohits/*.bin` | <<FIMOHITS_COUNT>> files | one PMETBN01 file per motif (10 in `motif.meme`) |
| `binomial_thresholds.txt` | <<BINOMIAL_LINES>> rows | per-motif p-value threshold for `--topn 5000` |
| `IC.txt` | <<IC_LINES>> rows | per-motif positional information content |
| `universe.txt` | <<UNIVERSE_LINES>> rows | every distinct interval name |
| `promoter_lengths.txt` | <<PROMOTER_LENGTHS_LINES>> rows | should equal `universe.txt` rows |

### Pairing-stage output preview · 异型阶段输出预览

`motif_output.txt` first 3 rows (cluster ⟶ motif1 ⟶ motif2 ⟶ ...):

```
<<MOTIF_OUTPUT_HEAD>>
```

Total enriched pair rows · 富集对总行数：**<<MOTIF_OUTPUT_LINES>>**.

### Worked example · 推导示例

<<WORKED_EXAMPLE>>

<a id="verification"></a>

## Verification · 验证

<<OVERALL_VERDICT>>

<<CHECK_TABLE>>
