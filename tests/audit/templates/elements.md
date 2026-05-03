# elements — full PMET on a chosen genomic element (UTR / CDS / mRNA / exon)

**[English](#en) · [汉文](#cn)**

<<RUN_HEADER>>

**Source:** [`scripts/workflows/elements.sh`](../../scripts/workflows/elements.sh)
&nbsp;&nbsp;**Helper sub-workflow:** [`scripts/workflows/cli/_pmet_index_element.sh`](../../scripts/workflows/cli/_pmet_index_element.sh)
&nbsp;&nbsp;**Used by:** CLI research runs only (no web entry point)

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose](#en-1) | [4. Reproducing this audit](#en-4) |
| [2. Biological setup](#en-2) | [5. Known limitation](#en-5) |
| [3. What the script does, step by step](#en-3) | [→ Run snapshot, worked example & verification](#run) |

<a id="en-1"></a>

## 1. Purpose

Same shape as `promoter.sh` — homotypic indexing then heterotypic pair test then heatmaps — but the indexed unit is **a chosen genomic element** rather than the canonical 1 kb upstream window. Useful when:

- You're asking whether motif pair-enrichment patterns differ between promoters, 5' UTRs, CDS, and exons. (They do — TF binding partners in 5' UTRs are not the same set as in promoters.)
- The species you care about has unusual gene architecture and "promoter = 1 kb upstream" is a poor model.
- You want to compare longest-isoform vs all-isoforms-merged aggregation strategies (the `-s` flag).

This is a **research workflow**, not exposed in the web UI.

<a id="en-2"></a>

## 2. Biological setup

For each gene, multiple isoforms typically share a transcription start but can have different element boundaries (e.g. 5' UTR length varies across splice variants). Two strategies:

- **`-s longest`** — pick the single isoform whose total element span is greatest, keep every fragment of that isoform. The default for research runs.
- **`-s merged`** — take the per-gene UNION of all isoforms' element intervals (overlapping intervals merged into a non-redundant set). No isoform specificity, no UTR subtraction.

For `-e mRNA` specifically there are **three biologically distinct modes** depending on `-s` and `-m`:

| `-s` / `-e` / `-m` | What gets indexed | When to use |
|---|---|---|
| `-s longest -e mRNA -m Yes` | the longest isoform's full mRNA span (UTRs + CDS, single interval per gene) | binding analysis where 5'/3' UTR regulatory sites matter equally to CDS |
| `-s longest -e mRNA -m No` (default) | the same isoform with its annotated UTRs subtracted (CDS span as one interval per gene) | "what binds along the coding span" without UTR contamination, but at gene granularity (one interval per gene, not per CDS fragment) |
| `-s longest -e CDS` (or `-e exon`) | per-CDS-fragment / per-exon intervals from the longest isoform | per-fragment resolution — useful for asking whether motif co-occurrence localises to specific CDS fragments / exons |

`-m` is ignored for `-s merged` and for any non-mRNA element.

Both strategies typically produce multiple intervals per gene (e.g. 3 exons → 3 intervals; one mRNA span → 1 interval). The script tags each interval as `__GENE__N` (gene name + 1-based index) so FIMO can scan them separately, then a **gene-level fold** in step 12 collapses per-interval hits back to per-gene rows so `pairing_parallel` sees one row per gene.

<a id="en-3"></a>

## 3. What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + element prompt | `-s longest\|merged`, `-e 3UTR\|5UTR\|mRNA\|CDS\|exon`, optional `-m Yes\|No` | Strategy + element + (mRNA only) full-span flag |
| 2 | TAIR10 fetch (if absent) | `bash scripts/fetch_reference.sh` | One-shot download |
| 3 | Chromosome-name preflight | GFF3 first chrom vs FASTA first header | Same fail-fast as `promoter.sh` |
| 4 | Element BED extraction | `_pmet_index_element.sh` step 1 — awk over GFF3 column 3 | Filters rows where `feature == element`; pulls `<key>=<id>` from the attributes column |
| 5 | Isoform aggregation | `_pmet_index_element.sh` step 2 — `longest` / `merged` branch (and the optional UTR-subtraction sub-step for `-s longest -e mRNA -m No`) | See "biological setup" |
| 6 | Interval tagging + length filter | `_pmet_index_element.sh` step 3 — append `__GENE__N`, drop fragments < 30 bp | The tag survives FIMO scanning so step 12 can demangle it |
| 7 | Universe + per-interval lengths | `_pmet_index_element.sh` step 4 — `cut -f1 promoter_lengths.txt` → `universe.txt` | Index metadata |
| 8 | Promoter FASTA extract | `_pmet_index_element.sh` step 5 — `bedtools getfasta -s` (strand-aware) over a linearised + faidx'd genome | Per-interval sequences for FIMO |
| 9 | Markov background | `_pmet_index_element.sh` step 6 — `fasta-get-markov` over the just-extracted promoter set | Zero-order base composition; FIMO uses it as the null model so p-values reflect the local element composition rather than the genome's |
| 10 | IC.txt | `_pmet_index_element.sh` step 7 — `calculateICfrommeme_IC_to_csv.py` | Per-motif positional information content; `pairing_parallel` uses this as a sanity floor (skip motifs less informative than `-i`) |
| 11 | FIMO + indexing | `_pmet_index_element.sh` step 8 — one `indexing_fimo_fused` call (OpenMP) | Replaces the older two-step (split MEME → parallel fimo → separate pmet indexer) flow that depended on PMET-patched `--topn`/`--topk` flags absent from upstream MEME's `fimo` (commit `d2663c0`) |
| 12 | **Gene-level fold** | `_pmet_index_element.sh` step 9 — `scripts/python/collapse_element_fimohits.py` | Decodes PMETBN01 binary fimohits, strips `__GENE__N` from sequence names, groups hits by gene, keeps top-`maxk` per gene by ascending p-value, filters against the per-motif binomial threshold, re-encodes. Also normalises `binomial_thresholds.txt` motif IDs to upper-case to match `IC.txt` and the fimohits filenames |
| 13 | Indexing contract validation | `scripts/python/check_homotypic_contract.py <homotypic>` | Catches motif-id case mismatches and missing files |
| 14 | Heterotypic loop over `data/genes/*.txt` | for each task: filter by universe → `pairing_parallel` → optional heatmaps | Per-task `02_heterotypic_<task>/motif_output.txt`. Heatmap failures (e.g. `ggsave`'s 50-inch dimension cap on huge tasks) are non-fatal — the loop continues |

<a id="en-4"></a>

## 4. Reproducing this audit

```bash
# Full audit run — regenerates all four docs/workflows/*.md
make test-audit

# Or just this workflow's doc (elements alone takes ~5 min — the
# slowest of the four)
python3 tests/audit/generate.py elements
```

**Needs** — built host binaries (`make build`); TAIR10 (`make fetch-data`); Franco-Zorrilla MEME at `data/motifs/Franco-Zorrilla_et_al_2014.meme` (in-repo); Python 3 standard library; optionally `Rscript`.

**Produces** — overwrites `docs/workflows/elements.md` (this file). Working files at `tests/audit/runs/elements/` (gitignored). Per-gene-task heterotypic outputs at `<results>/02_heterotypic_<task>/motif_output.txt`.

**How to read it** — see [§Verification](#verification). The audit deliberately uses `-s longest -e 5UTR` (smallest element by universe size) for fast iteration. To audit the merged strategy or a larger element, the spec needs another invocation; the architecture verification (FIMO + collapse + pair) is identical regardless of which strategy/element pair runs.

<a id="en-5"></a>

## 5. Known limitation

R `ggsave` enforces a hard 50-inch dimension cap. Some gene tasks (e.g. `random_genes_topN`'s ~190k motif-pair output) blow past that and the heatmap step exits non-zero for that task. `elements.sh` catches this with `|| print_orange "..."` so a single heatmap failure doesn't take down the rest of the loop — the data outputs (`motif_output.txt`) for that task are unaffected.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途](#cn-1) | [4. 重跑此审计](#cn-4) |
| [2. 生物学背景](#cn-2) | [5. 已知限制](#cn-5) |
| [3. 脚本逐步做了什么](#cn-3) | [→ 运行快照、推导示例、验证](#run) |

<a id="cn-1"></a>

## 1. 用途

形态跟 `promoter.sh` 一样 —— 同型 indexing → 异型 pair 检验 → heatmap —— 但被索引的单元是**用户指定的基因组元素**，不是经典的 TSS 上游 1 kb 窗口。适用场景：

- 想问 motif 对富集模式在启动子、5' UTR、CDS、exon 之间是否不同。（确实不同 —— 5' UTR 里的 TF 结合伙伴不是启动子里那一组。）
- 研究的物种有非典型基因结构，"启动子 = 上游 1 kb"模型不成立。
- 想对比 longest-isoform vs all-isoforms-merged 聚合策略（`-s` flag）。

这是**研究 workflow**，web UI 没暴露。

<a id="cn-2"></a>

## 2. 生物学背景

每个基因通常多个 isoform 共享转录起始，但 element 边界可能不同（如 5' UTR 长度因剪接变体而异）。两种策略：

- **`-s longest`** —— 选 element 总跨度最大那个 isoform，留它所有 fragment。研究运行的默认。
- **`-s merged`** —— 取每基因所有 isoform element 区间的 UNION（重叠的合并成非冗余集）。不区分 isoform，不做 UTR 减除。

`-e mRNA` 还有 **3 种生物学上不同的模式**，由 `-s` 和 `-m` 组合：

| `-s` / `-e` / `-m` | 索引什么 | 何时用 |
|---|---|---|
| `-s longest -e mRNA -m Yes` | 最长 isoform 的完整 mRNA 跨度（UTR + CDS，per-gene 一个区间） | binding 分析里 5'/3' UTR 调控位点跟 CDS 同等重要 |
| `-s longest -e mRNA -m No`（默认） | 同 isoform 但减去其 annotated UTR（CDS 跨度作为 per-gene 一个区间） | "沿 coding 跨度有什么结合"且不被 UTR 污染，但是 gene 粒度（per-gene 一个区间，不是 per-CDS-fragment） |
| `-s longest -e CDS`（或 `-e exon`） | 最长 isoform 的 per-CDS-fragment / per-exon 区间 | per-fragment 分辨率 —— 用来问 motif 共现是否聚在特定 CDS fragment / exon |

`-m` 在 `-s merged` 和任何非 mRNA element 下被忽略。

两种策略通常都给每基因多个区间（如 3 exon → 3 区间；一个 mRNA 跨度 → 1 区间）。脚本给每个区间打 `__GENE__N` 标签（基因名 + 1-based 序号）让 FIMO 分别扫，然后 step 12 的 **gene-level fold** 把 per-interval hit 折回 per-gene 行，让 `pairing_parallel` 看到的是 per-gene 一行。

<a id="cn-3"></a>

## 3. 脚本逐步做了什么

| # | 阶段 | 跑什么 | 为什么 |
|---|---|---|---|
| 1 | 参数 + element 提示 | `-s longest\|merged`、`-e 3UTR\|5UTR\|mRNA\|CDS\|exon`、可选 `-m Yes\|No` | 策略 + element + （仅 mRNA）full-span 标记 |
| 2 | TAIR10 拉取（缺则补） | `bash scripts/fetch_reference.sh` | 一次性下载 |
| 3 | 染色体名预检 | GFF3 第一个 chrom 比 FASTA 第一个 header | 跟 `promoter.sh` 同样的 fail-fast |
| 4 | element BED 抽取 | `_pmet_index_element.sh` step 1 —— awk 处理 GFF3 第 3 列 | 过滤 `feature == element` 的行；从 attribute 列拉 `<key>=<id>` |
| 5 | isoform 聚合 | `_pmet_index_element.sh` step 2 —— `longest` / `merged` 分支（外加 `-s longest -e mRNA -m No` 时的可选 UTR 减除子步） | 见 "生物学背景" |
| 6 | 区间打标 + 长度过滤 | `_pmet_index_element.sh` step 3 —— 加 `__GENE__N`，丢 < 30 bp 的 fragment | 标签会跟着 FIMO 扫描走，所以 step 12 可以拆回来 |
| 7 | universe + per-interval 长度 | `_pmet_index_element.sh` step 4 —— `cut -f1 promoter_lengths.txt` → `universe.txt` | 索引元数据 |
| 8 | 启动子 FASTA 抽取 | `_pmet_index_element.sh` step 5 —— `bedtools getfasta -s`（链感知）处理已经单行化 + faidx 的基因组 | per-interval 序列给 FIMO |
| 9 | Markov 背景 | `_pmet_index_element.sh` step 6 —— `fasta-get-markov` 处理刚抽出来的启动子集 | 零阶碱基组成；FIMO 当零分布用，让 p 值反映局部 element 组成而不是基因组的 |
| 10 | IC.txt | `_pmet_index_element.sh` step 7 —— `calculateICfrommeme_IC_to_csv.py` | per-motif 位置信息量；`pairing_parallel` 当 sanity floor（IC 比 `-i` 低的 motif 跳过） |
| 11 | FIMO + indexing | `_pmet_index_element.sh` step 8 —— 一次 `indexing_fimo_fused`（OpenMP） | 替代旧的两步流程（拆 MEME → 并行 fimo → 单独的 pmet indexer），那个流程依赖上游 MEME `fimo` 没有的 PMET 补丁 `--topn` / `--topk` flag（commit `d2663c0`） |
| 12 | **gene-level fold** | `_pmet_index_element.sh` step 9 —— `scripts/python/collapse_element_fimohits.py` | 解码 PMETBN01 二进制 fimohits，从序列名里剥 `__GENE__N`，按基因分组 hit，按 p 值升序保留每基因 top-`maxk`，按 per-motif 二项阈值过滤，再编码回去。同时把 `binomial_thresholds.txt` 的 motif ID 大写化以匹配 `IC.txt` 和 fimohits 文件名 |
| 13 | indexing 契约校验 | `scripts/python/check_homotypic_contract.py <homotypic>` | 抓 motif-id 大小写不一致和缺文件 |
| 14 | 异型循环遍历 `data/genes/*.txt` | 对每 task：按 universe 过滤 → `pairing_parallel` → 可选 heatmap | per-task `02_heterotypic_<task>/motif_output.txt`。heatmap 失败（如 `ggsave` 50 寸尺寸 cap 在大 task 上）非致命 —— 循环继续 |

<a id="cn-4"></a>

## 4. 重跑此审计

```bash
# 完整审计 —— 重新生成全部四份 docs/workflows/*.md
make test-audit

# 或者只跑这一个 workflow 的文档（elements 单跑 ~5 分钟，是四个里最慢的）
python3 tests/audit/generate.py elements
```

**需要** —— 编好的 host 二进制（`make build`）；TAIR10（`make fetch-data`）；Franco-Zorrilla MEME 在 `data/motifs/Franco-Zorrilla_et_al_2014.meme`（仓库自带）；Python 3 标准库；可选 `Rscript`。

**产出** —— 覆盖写 `docs/workflows/elements.md`（本文件）。工作文件在 `tests/audit/runs/elements/`（gitignored）。每个 gene-task 的异型输出在 `<results>/02_heterotypic_<task>/motif_output.txt`。

**怎么解读** —— 见 [§Verification](#verification)。审计故意用 `-s longest -e 5UTR`（universe 最小的 element）做快迭代。要审 merged 策略或更大的 element，spec 需要再发一次调用；不论跑哪种策略/element 组合，架构验证（FIMO + collapse + pair）相同。

<a id="cn-5"></a>

## 5. 已知限制

R `ggsave` 强制 50 寸尺寸 cap。某些 gene task（如 `random_genes_topN` ~190k 行 motif 对输出）会突破这个 cap，那个 task 的 heatmap 步退出非 0。`elements.sh` 用 `|| print_orange "..."` 把这种情况接住，所以单个 heatmap 失败不会拖垮整个循环 —— 那个 task 的数据输出（`motif_output.txt`）不受影响。

---

<a id="run"></a>

## Run snapshot · 运行快照

This audit just ran:

```
<<COMMAND_DISPLAYED>>
```

Output root: `<<RESULT_ROOT>>/`.

### Indexing-stage outputs · 同型阶段产出

| File | Rows / count | Meaning |
|---|---|---|
| `01_homotypic/fimohits/*.bin` | <<FIMOHITS_COUNT>> files | one PMETBN01 file per motif (113 in Franco-Zorrilla) |
| `01_homotypic/binomial_thresholds.txt` | <<BINOMIAL_LINES>> rows | per-motif p-value cutoff (case-normalized by the collapse step) |
| `01_homotypic/IC.txt` | <<IC_LINES>> rows | per-motif positional information content |
| `01_homotypic/universe.txt` | <<UNIVERSE_LINES>> rows | every gene with a valid 5'UTR |
| `01_homotypic/promoter_lengths.txt` | <<PROMOTER_LENGTHS_LINES>> rows | should equal `universe.txt` rows after gene-level fold |

### Heterotypic per-task summary · 异型 per-task 汇总

The script loops over every `data/genes/*.txt` file. Per-task results:

<<TASK_TABLE>>

(`missing` rows = the gene list had zero overlap with the 5'UTR universe, so the script skipped `pairing_parallel` for that task — that's expected biology, not a failure.)

Total enriched pair rows across all tasks · 所有 task 的富集对总行数：**<<TOTAL_HET_LINES>>**.

### Worked example · 推导示例

<<WORKED_EXAMPLE>>

<a id="verification"></a>

## Verification · 验证

<<OVERALL_VERDICT>>

<<CHECK_TABLE>>
