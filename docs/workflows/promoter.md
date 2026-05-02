# promoter — full PMET on gene promoters

**[English](#en) · [汉文](#cn)**

_Audit refreshed 2026-05-02 12:19:43 UTC on this machine — workflow `promoter`, exit 0, 108.0s_

**Source:** [`scripts/workflows/promoter.sh`](../../scripts/workflows/promoter.sh)
&nbsp;&nbsp;**Used by:** CLI research runs · web `promoters` mode

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose](#en-1) | [4. Reproducing this audit](#en-4) |
| [2. Biological setup](#en-2) | [→ Run snapshot & verification](#run) |
| [3. What the script does, step by step](#en-3) | |

<a id="en-1"></a>

## 1. Purpose

The canonical PMET pipeline. Given a genome FASTA, a GFF3 annotation, a MEME motif file, and a gene-cluster list, it asks:

> **Within the promoters of the user's gene clusters, which pairs of transcription-factor motifs co-occur more than expected by chance?**

Co-occurrence above null is a fingerprint of TF cooperativity — most TFs don't bind alone; partner TFs land at neighbouring sites and the combination drives the regulatory output. PMET uses a **hypergeometric test** to score per-cluster motif-pair enrichment, **gated by a per-motif binomial pre-filter** built during indexing. The two stages compose:

  1. **Indexing (per motif, once per universe):** `index_fimo_fused` scans every promoter and records per-motif binomial-distribution thresholds in `binomial_thresholds.txt`, calibrated so only the top ~`--topn` hits cross.
  2. **Pairing (per cluster + motif pair):** `pair_parallel` enumerates pairs `(m1, m2)`, intersects their per-promoter hit sets, re-evaluates the per-pair binomial threshold (drops pairs that fall below it), then runs a **hypergeometric test** comparing the overlap with the user's gene cluster against the universe-wide background — the resulting p-value is what `motif_output.txt` reports per `(cluster, m1, m2)`.

This script is the longest of the four (~2 minutes wall on TAIR10 + Franco-Zorrilla at 4 threads, dominated by FIMO scanning the 113-motif set against ~30k 1 kb promoters).

<a id="en-2"></a>

## 2. Biological setup

- **"Promoter"** here means the user-configurable upstream window of the gene's transcription start (default 1000 bp), optionally plus the gene's 5' UTR. Overlapping windows from neighbouring genes are trimmed so each base is attributed to at most one promoter (controlled by `-v NoOverlap`).
- **"Universe"** is every gene that survives the promoter-extraction filters (size ≥ 20 bp, valid sequence). This is the null background the pair test compares against.
- **"Cluster"** is one row of the gene-list file: `<cluster_label> <gene_id>`. Each cluster is tested independently for pair enrichment.

The deeper biology and stage-by-stage construction of the promoter set is documented separately in [`docs/methods/promoter-extraction.md`](../methods/promoter-extraction.md).

<a id="en-3"></a>

## 3. What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + binary preflight | locate `build/{index_fimo_fused, pair_parallel}` | Single failure point if either binary is missing |
| 2 | TAIR10 fetch (if absent) | `bash scripts/fetch_reference.sh` | One-shot ~220 MB download; subsequent runs find the file and skip |
| 3 | Chromosome-name preflight | compare GFF3 first chrom vs FASTA first header | Catches the `'1'` vs `'Chr1'` mismatch that silently produces empty BED downstream — quick fail beats a 2-minute "everything succeeded but indexed nothing" run |
| 4 | Homotypic indexing | `scripts/python/run_homotypic.py` — delegates the 10-step chain below | The expensive scan; produces the universe + per-motif binary fimohits + per-motif binomial thresholds |
| 4.1 | Sort GFF3 | `scripts/third_party/gff3sort/gff3sort.pl` | Some downstream tools assume sorted GFF3; this normalises arbitrary input |
| 4.2 | Build gene BED | `scripts/python/gff3_to_gene_bed.py` | Pulls the gene-row subset (`feature == 'gene'` or the wider `gene$`-regex set) into a 6-column BED |
| 4.3 | Chromosome lengths | `scripts/python/genome_chrom_lengths.py` | `bedtools flank` needs a `<chr> <length>` table to clamp at chromosome ends |
| 4.4 | Linearise FASTA + faidx | inline awk + `samtools faidx` | Single-line records make sed/grep predictable; the `.fai` index is consumed by `bedtools getfasta` later |
| 4.5 | Build promoters | `scripts/python/build_promoters.py` | The conceptual core — `bedtools flank -l <length> -r 0 -s` → trim against gene bodies → optional 5'-UTR extension → `bedtools getfasta -s` → drop fragments < min length → emit `promoter.fa` + `promoter_lengths.txt` |
| 4.6 | IC per motif | `scripts/python/calculateICfrommeme_IC_to_csv.py` | Reads the combined MEME directly (deterministic motif order); upper-cases motif IDs so they line up with what `index_fimo_fused` writes |
| 4.7 | MEME header upper-casing | inline (`meme_upper.meme`) | Same case as `IC.txt` → matches `index_fimo_fused`'s binary fimohits and `binomial_thresholds.txt`; `pair_parallel` does case-sensitive lookups |
| 4.8 | FIMO + indexing | `build/index_fimo_fused` (one OpenMP-batched call) | The scan itself; writes `binomial_thresholds.txt` + `fimohits/<MOTIF>.bin` (PMETBN01 binary) |
| 4.9 | Sanity: file count | inline `find ... -name '*.bin' \| wc -l` | Catches "indexing didn't crash but produced 0 files" early |
| 4.10 | Contract validation | `scripts/python/check_homotypic_contract.py` | Asserts the schema in `docs/methods/homotypic-contract.md` (motif sets across binomial / IC / fimohits, type checks) |
| 5 | Heterotypic gene filter | `grep -wFf universe.txt <gene_list>` | Drop user-list genes that aren't in the indexed universe (no promoter passed extraction) |
| 6 | Pair test | `build/pair_parallel -d <homotypic> -g <kept> ...` → temp shards | Per-cluster hypergeometric pair enrichment, gated by the per-motif binomial pre-filter in `binomial_thresholds.txt` |
| 7 | Shard aggregation | `cat temp*.txt > motif_output.txt` then `rm temp*.txt` | `pair_parallel` doesn't unify shards itself |
| 8 | Heatmaps (optional) | three `Rscript scripts/r/draw_heatmap.R` calls | Skipped silently if `Rscript` is absent |

<a id="en-4"></a>

## 4. Reproducing this audit

```bash
make test-audit                        # all four workflows
python3 tests/audit/generate.py promoter   # just this one
```

**Needs** — built host binaries (`make build`), TAIR10 (`make fetch-data`), Python 3 standard library, optionally `Rscript` for the heatmap step.

**Produces** — overwrites `docs/workflows/promoter.md` (this file). Working files land under `tests/audit/runs/promoter/` (gitignored).

**How to read it** — see the OVERALL line in [§Verification](#verification) below; PASS means anchors and contract invariants all match. The `motif_output.txt` SHA anchor `4b24906a...` was independently verified against the recorded baseline (cf. commit `d2663c0`'s message). `pair_only.sh` against this same homotypic index produces the same SHA — that's the cross-validation that ties the `pair_only` audit to this `promoter` audit.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途](#cn-1) | [4. 重跑此审计](#cn-4) |
| [2. 生物学背景](#cn-2) | [→ 运行快照与验证](#run) |
| [3. 脚本逐步做了什么](#cn-3) | |

<a id="cn-1"></a>

## 1. 用途

PMET 的经典 pipeline。给一份基因组 FASTA、GFF3 注释、MEME motif 文件、基因 cluster 列表，问：

> **在用户给的 gene cluster 的启动子里，哪些转录因子 motif 对的共现频率高于偶然？**

共现高于零假设是 TF 协同的足迹 —— 大多数 TF 不单独结合；伙伴 TF 在邻近位点结合，组合起来才驱动调控。PMET 用**超几何检验**给 per-cluster motif 对富集打分，**由 indexing 阶段建的 per-motif 二项预筛门控**。两阶段组合：

  1. **Indexing（每 motif，universe 内一次性）：** `index_fimo_fused` 扫每个启动子，per-motif 二项分布阈值写入 `binomial_thresholds.txt`，校准成只有 universe 里 top ~`--topn` 个 hit 能过线。
  2. **Pairing（每 cluster × motif 对）：** `pair_parallel` 枚举对 `(m1, m2)`、对它们 per-promoter hit 集合取交、重新评估这一对的二项阈值（不过线就丢）、然后跑**超几何检验**比较交集与用户 gene cluster 在 universe 内背景的差异 —— 得到的 p 值就是 `motif_output.txt` 里 per `(cluster, m1, m2)` 的那个。

这是四个里最长的一条（TAIR10 + Franco-Zorrilla 在 4 线程下 ~2 分钟 wall，主要 cost 是 FIMO 把 113 个 motif 扫 ~30k 个 1 kb 启动子）。

<a id="cn-2"></a>

## 2. 生物学背景

- **"启动子"**这里指基因转录起始位点上游、用户可配的窗口（默认 1000 bp），可选包含基因的 5' UTR。邻近基因的窗口重叠会被切掉，让每个碱基只归一个启动子（`-v NoOverlap` 控制）。
- **"Universe"** 是所有通过启动子抽取过滤的基因（size ≥ 20 bp、序列合法）。pair 检验的零分布就跟它对比。
- **"Cluster"** 是基因列表文件的一行：`<cluster 标签> <gene_id>`。每个 cluster 独立做 pair 富集检验。

更深入的生物学和启动子集合的逐步构造，单独记在 [`docs/methods/promoter-extraction.md`](../methods/promoter-extraction.md)。

<a id="cn-3"></a>

## 3. 脚本逐步做了什么

| # | 阶段 | 跑什么 | 为什么 |
|---|---|---|---|
| 1 | 参数 + 二进制预检 | 找 `build/{index_fimo_fused, pair_parallel}` | 二进制缺一个就早退 |
| 2 | TAIR10 拉取（缺则补） | `bash scripts/fetch_reference.sh` | 一次性 ~220 MB；后续运行发现已存在就跳 |
| 3 | 染色体名预检 | GFF3 第一个 chrom 比 FASTA 第一个 header | 抓 `'1'` vs `'Chr1'` 不匹配，那种会让下游 BED 静默空的 case —— 早 fail 比跑 2 分钟"全 OK 但啥都没索引"强 |
| 4 | 同型 indexing | `scripts/python/run_homotypic.py` —— 委托下面 10 步链 | 重头戏；产出 universe + per-motif 二进制 fimohits + per-motif 二项阈值 |
| 4.1 | 排 GFF3 | `scripts/third_party/gff3sort/gff3sort.pl` | 部分下游工具假定 sorted GFF3；这步把任意输入 normalize |
| 4.2 | 建 gene BED | `scripts/python/gff3_to_gene_bed.py` | 把 gene 行子集（`feature == 'gene'` 或更宽的 `gene$`-regex）拉成 6 列 BED |
| 4.3 | 染色体长度 | `scripts/python/genome_chrom_lengths.py` | `bedtools flank` 要 `<chr> <length>` 表来 clamp 到染色体边界 |
| 4.4 | 序列单行化 + faidx | inline awk + `samtools faidx` | 单行 record 让 sed/grep 行为可预测；`.fai` 索引后面 `bedtools getfasta` 用 |
| 4.5 | 建启动子 | `scripts/python/build_promoters.py` | 概念核心 —— `bedtools flank -l <length> -r 0 -s` → 切掉与基因体重叠 → 可选 5'-UTR 延伸 → `bedtools getfasta -s` → 丢小于最小长度的 fragment → 写出 `promoter.fa` + `promoter_lengths.txt` |
| 4.6 | per-motif IC | `scripts/python/calculateICfrommeme_IC_to_csv.py` | 直接读合并的 MEME（确定性 motif 顺序）；motif ID 大写化以与 `index_fimo_fused` 写出的对齐 |
| 4.7 | MEME header 大写化 | inline（`meme_upper.meme`） | 与 `IC.txt` 同 case → 匹配 `index_fimo_fused` 的二进制 fimohits 和 `binomial_thresholds.txt`；`pair_parallel` 是大小写敏感查找 |
| 4.8 | FIMO + indexing | `build/index_fimo_fused`（一次 OpenMP-batched 调用） | 扫描本身；写 `binomial_thresholds.txt` + `fimohits/<MOTIF>.bin`（PMETBN01 二进制） |
| 4.9 | sanity：文件数 | inline `find ... -name '*.bin' \| wc -l` | 早抓"indexing 没崩但产出 0 文件" |
| 4.10 | 契约校验 | `scripts/python/check_homotypic_contract.py` | 断言 `docs/methods/homotypic-contract.md` 里的 schema（motif 集合在 binomial / IC / fimohits 间一致、类型检查） |
| 5 | 异型 gene 过滤 | `grep -wFf universe.txt <gene_list>` | 丢掉用户列表里不在索引 universe 的（没有启动子通过抽取） |
| 6 | pair 检验 | `build/pair_parallel -d <homotypic> -g <kept> ...` → temp shard | per-cluster 超几何 pair 富集，由 `binomial_thresholds.txt` 里的 per-motif 二项预筛门控 |
| 7 | shard 聚合 | `cat temp*.txt > motif_output.txt` 再 `rm temp*.txt` | `pair_parallel` 自己不合并 shard |
| 8 | heatmap（可选） | 三次 `Rscript scripts/r/draw_heatmap.R` | 缺 `Rscript` 静默跳过 |

<a id="cn-4"></a>

## 4. 重跑此审计

```bash
make test-audit                        # 全部四个 workflow
python3 tests/audit/generate.py promoter   # 只跑这一个
```

**需要** —— 编好的 host 二进制（`make build`）、TAIR10（`make fetch-data`）、Python 3 标准库，可选 `Rscript` 用于 heatmap 步。

**产出** —— 覆盖写 `docs/workflows/promoter.md`（本文件）。工作文件落在 `tests/audit/runs/promoter/`（gitignored）。

**怎么解读** —— 看下方 [§Verification](#verification) 里的 OVERALL 行；PASS 表示 anchor 和契约不变量都对得上。`motif_output.txt` 的 SHA anchor `4b24906a...` 独立验证过对得上录制 baseline（参 commit `d2663c0` 的 message）。`pair_only.sh` 跑同一份同型索引产出相同 SHA —— 这就是把 `pair_only` 审计跟本 `promoter` 审计绑在一起的交叉验证。

---

<a id="run"></a>

## Run snapshot · 运行快照

This audit just ran:

```
bash scripts/workflows/promoter.sh -o /Users/nuioi/projects/pmet/tests/audit/runs/promoter/01_homotypic -x /Users/nuioi/projects/pmet/tests/audit/runs/promoter/02_heterotypic -y /Users/nuioi/projects/pmet/tests/audit/runs/promoter/03_plot -t 4
```

Indexing landed at `tests/audit/runs/promoter/01_homotypic/`, pairing at `tests/audit/runs/promoter/02_heterotypic/`, plots at `tests/audit/runs/promoter/03_plot/`.

### Indexing-stage outputs · 同型阶段产出

| File | Rows / count | Meaning |
|---|---|---|
| `fimohits/*.bin` | 113 files | one PMETBN01 file per motif (113 in Franco-Zorrilla) |
| `binomial_thresholds.txt` | 113 rows | per-motif p-value cutoff for `--topn 5000` |
| `IC.txt` | 113 rows | per-motif positional information content |
| `universe.txt` | 29824 rows | every gene with a valid extracted promoter |
| `promoter_lengths.txt` | 29824 rows | should equal `universe.txt` rows |

### Pairing-stage output preview · 异型阶段输出预览

`motif_output.txt` first 3 rows (cluster ⟶ motif1 ⟶ motif2 ⟶ ...):

```
Cluster	Motif 1	Motif 2	Number of genes in cluster with both motifs	Total number of genes with both motifs	Number of genes in cluster	Raw p-value	Adjusted p-value (BH)	Adjusted p-value (Bonf)	Adjusted p-value (Global Bonf)	Genes
Cortex_flg22_up	AHL12	AHL12_2	0	197	119	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00
Cortex_flg22_up	AHL12	AHL12_3ARY	3	682	119	5.1393905122e-01	1.0000000000e+00	1.0000000000e+00	1.0000000000e+00	AT1G05660;AT1G34420;AT3G25900;
```

Total enriched pair rows · 富集对总行数：**37969** — these are the per-cluster motif pairs that survived `pair_parallel`'s binomial pre-filter and the cluster-level hypergeometric test at the canonical IC and FIMO thresholds.

This run took **107.97638174984604s** at 4 threads. The dominant cost is stage 4 (FIMO scanning 113 motifs across ~30k 1 kb promoters); pair testing in stage 6 takes <30s of that.

<a id="verification"></a>

## Verification · 验证

✅ **PASS** — all 13 check(s) passed

| # | Check | Expected | Observed | Verdict |
|---|---|---|---|---|
| 1 | script exit code | `0` | `0` | ✅ PASS |
| 2 | fimohits/*.bin per motif | `113` | `113` | ✅ PASS |
| 3 | binomial_thresholds rows == motifs | `113` | `113` | ✅ PASS |
| 4 | IC.txt rows == motifs | `113` | `113` | ✅ PASS |
| 5 | universe.txt non-empty (genes with valid promoters) | `>= 1` | `29824` | ✅ PASS — TAIR10 with 1 kb promoter + UTR keeps about 30k genes |
| 6 | promoter_lengths.txt rows == universe size | `29824` | `29824` | ✅ PASS |
| 7 | motif_output.txt non-empty (heterotypic pairs) | `>= 1` | `37969` | ✅ PASS |
| 8 | motif_output.txt deterministic vs anchor | `4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70` | `4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70` | ✅ PASS — anchor matches the recorded cli/03_promoter baseline |
| 9 | indexing contract: binomial == IC motifs | `set equal` | `|both|=113` | ✅ PASS |
| 10 | indexing contract: binomial == fimohits motifs | `set equal` | `|both|=113` | ✅ PASS |
| 11 | indexing contract: IC == fimohits motifs | `set equal` | `|both|=113` | ✅ PASS |
| 12 | Rscript invoked (3 histogram subdirs present) | `3` | `3` | ✅ PASS |
| 13 | 3 headline heatmap PNGs rendered | `3` | `3` | ✅ PASS |
