# Promoter extraction — knowledge points and pitfalls

**[English](#en) · [汉文](#cn)**

A practical reference for everything that can go wrong (or has gone wrong) when deriving promoter sequences from a genome FASTA + GFF3. Each topic below corresponds to a real bug fix in the pipeline. Read this if you're touching `scripts/python/build_promoters.py`, `gff3_to_gene_bed.py`, or any of the workflow scripts that consume promoter FASTA.

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Coordinate systems (GFF3 vs BED)](#en-1) | [8. `bedtools getfasta -s` (strand-aware)](#en-8) |
| [2. + and − strand gene structure](#en-2) | [9. Chromosome-name consistency](#en-9) |
| [3. Defining a promoter](#en-3) | [10. Getting chromosome lengths](#en-10) |
| [4. Gene-level feature types in GFF3](#en-4) | [11. Python helpers (current state)](#en-11) |
| [5. GFF3 attribute parsing](#en-5) | [12. `bedtools subtract` and split promoters](#en-12) |
| [6. Multi-isoform genes and TSS choice](#en-6) | [13. `awk -F'\t'` for tab-separated input](#en-13) |
| [7. 5'UTR vs promoter](#en-7) | |

<a id="en-1"></a>

## 1. Coordinate systems (GFF3 vs BED)

GFF3 uses 1-based **closed** intervals (start and end both included). BED uses 0-based **half-open** intervals (start included, end excluded). Mixing them silently shifts every coordinate by 1 bp.

Example: AT1G01010 in GFF3 is `3631..5899`. In BED that becomes `3630..5899` — start dropped by 1, end unchanged. Conversion: `BED_start = GFF3_start - 1`, `BED_end = GFF3_end`.

The legacy `parse_genelines.py` did *not* do this conversion and shifted every downstream coordinate by 1 bp. The replacement is [`scripts/python/gff3_to_gene_bed.py`](../../scripts/python/gff3_to_gene_bed.py); the old script is in `scripts/archive/`.

<a id="en-2"></a>

## 2. + and − strand gene structure

A `+` strand gene runs left → right along the genome: promoter → TSS → 5'UTR → exons/introns → 3'UTR. TSS sits at the *small-coordinate* end. The promoter is to its left (smaller coordinates).

A `−` strand gene is mirrored: TSS sits at the *large-coordinate* end. The promoter is to its right (larger coordinates).

The mRNA is always read 5' → 3', but its layout on the genome depends on strand. BED `start` is always less than `end` regardless of strand.

<a id="en-3"></a>

## 3. Defining a promoter

GFF3 doesn't carry an explicit promoter feature; it has to be inferred from gene coordinates. Two strategies:

**Fixed window** — take a fixed length (e.g. 1000 bp) upstream of TSS. This pipeline uses `bedtools flank -l $length -r 0 -s`. Simple and uniform, but can poke into a neighbouring gene.

**Variable window** — `min(fixed_length, distance_to_nearest_neighbour)`. Needs `length_to_tss.txt` precomputed per gene. The pipeline computes this file but doesn't use it directly; instead it does fixed-window first and trims overlaps with `bedtools subtract` after.

Edge cases:

- **Head-to-head genes** share an intergenic region: each takes the whole gap as its inferred promoter, so the two annotations overlap until subtract trims them.
- **Nested genes** (e.g. AT1G03997 fully inside AT1G01050): the inner gene has 0 bp of usable promoter and gets dropped downstream.

<a id="en-4"></a>

## 4. Gene-level feature types in GFF3

Column 3 of GFF3 is not just `gene`. Real annotations also use `ncRNA_gene`, `pseudogene`, `transposable_element_gene`, `tRNA_gene`, `rRNA_gene`, `snRNA_gene`. Strict `$3 == "gene"` matching misses them.

Concrete bite: TAIR10 has `AT1G03987` annotated as `ncRNA_gene`. Skipping it lets the inferred promoter of `AT1G01020` extend across this lncRNA — wrong by ~270 bp.

[`gff3_to_gene_bed.py`](../../scripts/python/gff3_to_gene_bed.py) takes a `--feature-regex` so callers can choose:

- `--feature-regex 'gene$'` (default) — matches `gene`, `ncRNA_gene`, `pseudogene`, anything ending in `gene`. Used by `promoter.sh` and `cli/05_promoter_gap.sh`.
- `--feature-regex '^gene$'` — strict; only `gene`. Used by `cli/02_perf_params.sh` to keep its narrower scope.

Quick sanity check before running on a new annotation:

```bash
awk -F'\t' '$3 ~ /gene/' sorted.gff3 | cut -f3 | sort -u
```

<a id="en-5"></a>

## 5. GFF3 attribute parsing

Column 9 of GFF3 is `;`-separated `key=value` pairs. Different sources use different keys for gene name:

- TAIR / Ensembl: `ID=gene:AT1G01010`
- Some: `gene_id=AT1G01010`
- NCBI: `ID=gene-LOC123456`

Note Ensembl-style values carry a `gene:` prefix. If you want to match against an expression matrix, strip it: `gsub(/^[Gg]ene[:\-]/, "", name)`.

The legacy `parse_utrs.py` checked `'gene' in annot[i, :]` (the whole row) — but the attribute column has `gene_id=...` on every row, causing false matches. Fixed to check column 3 only.

<a id="en-6"></a>

## 6. Multi-isoform genes and TSS choice

A single gene can have multiple isoforms with different 5'UTR lengths and therefore different TSSs. Example (AT1G01020, − strand):

- AT1G01020.1 → 5'UTR `8667..9130` → TSS at `9130`
- AT1G01020.2 → 5'UTR `8667..8737` → TSS at `8737`

The gene-level GFF3 row reports the outermost edges across all isoforms (`6788..9130` here), corresponding to the most upstream TSS. Using the gene row picks the longest-5'UTR isoform automatically — the conservative and most common choice.

Per-isoform precision needs parsing `mRNA` / `transcript` rows instead, with non-trivial downstream complexity. For batch promoter analysis, gene-level is the right default.

<a id="en-7"></a>

## 7. 5'UTR vs promoter

The 5'UTR is **not** part of the promoter. TSS is the first transcribed base; 5'UTR runs from TSS to the start of the CDS as part of the mRNA. The promoter is upstream of TSS.

This pipeline can optionally extend the promoter downstream past the TSS to the start of the CDS (i.e. include the 5'UTR), for a broader cis-regulatory analysis. `parse_utrs.py` handles this by taking the outermost CDS start across all isoforms.

<a id="en-8"></a>

## 8. `bedtools getfasta -s` (strand-aware)

`bedtools getfasta` defaults to extracting the literal `+` strand sequence. For a `−` strand gene the coordinates are right but the **sequence** is the reverse complement of what the TF actually sees — motif scanning would silently give wrong answers.

You **must** pass `-s` so bedtools reverse-complements `−` strand intervals. Without `-s`, every motif result for `−` strand genes is wrong.

After `-s`, the FASTA header may end up as either `>gene(+)::chr:start-end` or `>gene::chr:start-end(+)` depending on bedtools version. Strip both:

```bash
sed -e 's/::.*//g' -e 's/([+-])$//g' input.fa > clean.fa
```

<a id="en-9"></a>

## 9. Chromosome-name consistency

GFF3 and FASTA can use different chromosome naming: GFF3 with `1, 2, 3` while FASTA uses `Chr1, Chr2, Chr3`, or vice versa. Mismatch causes `bedtools flank` and `bedtools getfasta` to silently emit empty output — no error.

The promoter / elements / perf-params workflows have a preflight that compares the first GFF3 data row's chromosome name against the first FASTA header and aborts with a clear error if they don't match. Don't disable it.

<a id="en-10"></a>

## 10. Getting chromosome lengths

`bedtools flank` needs a `<chrom>\t<length>` file (`-g`) to clamp coordinates at chromosome ends. Two ways:

1. From GFF3 `##sequence-region` headers (preferred): `grep '^##sequence-region' anno.gff3 | awk '{print $2"\t"$4}'`.
2. Fall back to `samtools faidx genome.fa` and use the first two columns of the resulting `.fai`.

[`scripts/python/genome_chrom_lengths.py`](../../scripts/python/genome_chrom_lengths.py) wraps both.

<a id="en-11"></a>

## 11. Python helpers (current state)

The `scripts/python/` helpers have grown from "patch tools" to "pipeline backbone". Active ones:

| Script | Role |
|---|---|
| `gff3_to_gene_bed.py` | GFF3 → BED conversion. Handles feature-regex filter, attribute-key fallback (`gene_id=` then `ID=`), 1-based → 0-based coordinate fix, dedup, drop `start ≥ end`. |
| `genome_chrom_lengths.py` | Chromosome length file + naming-consistency preflight. |
| `build_promoters.py` | Single CLI that does flank → subtract → assess → UTR → `getfasta -s` → bg, replacing inline shell sequences. |
| `run_homotypic.py` | End-to-end homotypic stage; combines every helper above + `build/index_fimo_fused`. The promoter / promoter_gap workflows now invoke this rather than wiring the steps inline. |
| `check_homotypic_contract.py` | Validates the 5-file schema; runs at end of every indexing pipeline. |
| `calculate_length_to_tss.py` | TSS-to-neighbour distance per gene. Called by `run_homotypic.py`. |
| `assess_integrity.py` | Resolves split-promoter fragments; called by `build_promoters.py`. |
| `parse_utrs.py` | 5'UTR extension. Called by `build_promoters.py`. |
| `calculateICfrommeme_IC_to_csv.py` | Per-motif IC; called by `run_homotypic.py`. |
| `parse_memefile.py` / `parse_memefile_batches.py` | Split MEME into single-motif files / N batches for IC computation and parallel FIMO. |

Archived (under `scripts/archive/`): `parse_genelines.py`, `calculate_chromosome_length.py`, `calculateICfrommeme.py`, `parse_matrix_n*.py`, `parse_mRNAlines.py`, `parse_promoter_lengths.py`, `parse_promoters.py`, `promoter_add_gap.py`, `promoter_remove_overlap.py`, `strip_newlines.py`. Either subsumed by a new helper, or no active pipeline calls them anymore.

<a id="en-12"></a>

## 12. `bedtools subtract` and split promoters

When `bedtools subtract` removes the parts of a promoter that overlap a gene body, an embedded small gene splits the promoter into multiple disjoint fragments. `assess_integrity.py` resolves this by keeping only the fragment closest to TSS:

- `+` strand: keep the largest-coordinate fragment (closest to gene start).
- `−` strand: keep the smallest-coordinate fragment (closest to gene end).

This step only runs if overlap removal was requested. With `AllowOverlap` it's skipped.

<a id="en-13"></a>

## 13. `awk -F'\t'` for tab-separated input

Always pass `-F'\t'` to `awk` when processing BED / GFF3. Default whitespace splitting works most of the time, but if a chromosome name or gene name contains a space (yes, real annotations do this), fields shift silently. Defensive:

```bash
awk -F'\t' '...' file.bed
```

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 坐标系统（GFF3 vs BED）](#cn-1) | [8. `bedtools getfasta -s`（链感知）](#cn-8) |
| [2. 正链与负链基因的结构](#cn-2) | [9. 染色体命名一致性](#cn-9) |
| [3. 启动子的定义与推断](#cn-3) | [10. 染色体长度的获取](#cn-10) |
| [4. GFF3 的 gene-level feature](#cn-4) | [11. Python helper 当前状态](#cn-11) |
| [5. GFF3 属性字段解析](#cn-5) | [12. `bedtools subtract` 与 split promoter](#cn-12) |
| [6. 多转录本与 TSS 选择](#cn-6) | [13. `awk -F'\t'` 处理 tab 分隔](#cn-13) |
| [7. 5'UTR 与启动子的关系](#cn-7) | [14. 答疑：head-to-head / 嵌套基因](#cn-14) |

<a id="cn-1"></a>

## 1. 坐标系统（GFF3 vs BED）

GFF3 用 1-based **闭区间**（start 和 end 都含）。BED 用 0-based **半开区间**（start 含，end 不含）。混用会让所有下游坐标静默偏移 1 bp。

例：AT1G01010 在 GFF3 是 `3631..5899`，转 BED 是 `3630..5899` —— start 减 1，end 不变。转换规则：`BED_start = GFF3_start - 1`，`BED_end = GFF3_end`。

旧版 `parse_genelines.py` 没做这个转换，导致所有下游坐标偏 1 bp。替换者是 [`scripts/python/gff3_to_gene_bed.py`](../../scripts/python/gff3_to_gene_bed.py)；老脚本归档在 `scripts/archive/`。

<a id="cn-2"></a>

## 2. 正链与负链基因的结构

`+` 链基因在基因组上从左到右排：启动子 → TSS → 5'UTR → exon/intron → 3'UTR。TSS 在*小坐标*那端，启动子在它左边（更小坐标方向）。

`−` 链基因镜像排：TSS 在*大坐标*那端，启动子在它右边（更大坐标方向）。

mRNA 永远按 5' → 3' 读，但在基因组上的排列方向看链。BED 的 `start` 永远小于 `end`，与链无关。

<a id="cn-3"></a>

## 3. 启动子的定义与推断

GFF3 一般不带显式启动子注释；要从基因坐标推断。两种策略：

**固定窗口** —— 取 TSS 上游固定长度（如 1000 bp）。本管道用 `bedtools flank -l $length -r 0 -s`。简单、统一，但可能侵入邻近基因。

**可变窗口** —— `min(固定长度, 到最近邻基因的距离)`。需要预先按基因算 `length_to_tss.txt`。本管道算了这个文件但不直接用，而是先按固定窗口取，再用 `bedtools subtract` 切掉重叠部分。

边界情况：

- **Head-to-head 基因**共享同一段基因间区：两个都把整段当自己的启动子，注释会重叠，到 subtract 才被切开。
- **嵌套基因**（如 AT1G03997 完全嵌在 AT1G01050 内）：内层基因可用启动子空间为 0 bp，下游会丢掉。

<a id="cn-4"></a>

## 4. GFF3 的 gene-level feature

GFF3 第 3 列不只有 `gene`。真实注释还会出现 `ncRNA_gene`、`pseudogene`、`transposable_element_gene`、`tRNA_gene`、`rRNA_gene`、`snRNA_gene`。严格 `$3 == "gene"` 匹配会漏。

具体踩坑：TAIR10 里 `AT1G03987` 注释成 `ncRNA_gene`。漏掉它，`AT1G01020` 推断的启动子会跨过这个 lncRNA —— 错 ~270 bp。

[`gff3_to_gene_bed.py`](../../scripts/python/gff3_to_gene_bed.py) 用 `--feature-regex` 让调用方选：

- `--feature-regex 'gene$'`（默认）—— 匹配 `gene`、`ncRNA_gene`、`pseudogene` 等所有以 `gene` 结尾的。`promoter.sh` 与 `cli/05_promoter_gap.sh` 用这个。
- `--feature-regex '^gene$'` —— 严格，只 `gene`。`cli/02_perf_params.sh` 用，保持其原本更窄的范围。

跑新注释前先 sanity check：

```bash
awk -F'\t' '$3 ~ /gene/' sorted.gff3 | cut -f3 | sort -u
```

<a id="cn-5"></a>

## 5. GFF3 属性字段解析

GFF3 第 9 列是 `;` 分隔的 `key=value`。不同来源用不同的 key 表达基因名：

- TAIR / Ensembl：`ID=gene:AT1G01010`
- 有些：`gene_id=AT1G01010`
- NCBI：`ID=gene-LOC123456`

注意 Ensembl 风格的值带 `gene:` 前缀。要跟表达矩阵对名时记得清理：`gsub(/^[Gg]ene[:\-]/, "", name)`。

旧的 `parse_utrs.py` 用 `'gene' in annot[i, :]` 检查整行 —— 但属性列几乎每行都有 `gene_id=...`，导致误匹配。改成只查第 3 列就好了。

<a id="cn-6"></a>

## 6. 多转录本与 TSS 选择

同一基因可能有多个转录本，5'UTR 长度不同、TSS 也不同。例（AT1G01020，`−` 链）：

- AT1G01020.1 → 5'UTR `8667..9130` → TSS 在 `9130`
- AT1G01020.2 → 5'UTR `8667..8737` → TSS 在 `8737`

gene 级的 GFF3 行报的是所有转录本的最外层边界（这里 `6788..9130`），对应最上游的 TSS。用 gene 行就是自动选了最长 5'UTR 那个转录本 —— 最保守、最常见的做法。

要 per-isoform 精确，得解析 `mRNA` / `transcript` 行，下游复杂度显著上升。批量启动子分析里 gene 级是合理默认。

<a id="cn-7"></a>

## 7. 5'UTR 与启动子的关系

5'UTR **不**是启动子的一部分。TSS 是第一个被转录的碱基；5'UTR 从 TSS 到 CDS start，是 mRNA 的一段。启动子在 TSS 上游。

本管道可选地把启动子向下游延伸到 CDS start（即把 5'UTR 包进去），用于更广义的顺式调控元件分析。`parse_utrs.py` 干这个，取所有转录本中最外层的 CDS start 来延。

<a id="cn-8"></a>

## 8. `bedtools getfasta -s`（链感知）

`bedtools getfasta` 默认抽 `+` 链上的字面序列。对 `−` 链基因，坐标是对的但**序列**是 TF 实际看到的反向互补 —— motif 扫会静默给错答案。

**必须**传 `-s`，让 bedtools 对 `−` 链区间自动做反向互补。没 `-s`，所有 `−` 链基因的 motif 结果都是错的。

加 `-s` 后 FASTA header 可能是 `>gene(+)::chr:start-end` 或 `>gene::chr:start-end(+)`（看 bedtools 版本）。两种都得清：

```bash
sed -e 's/::.*//g' -e 's/([+-])$//g' input.fa > clean.fa
```

<a id="cn-9"></a>

## 9. 染色体命名一致性

GFF3 和 FASTA 可能用不同的染色体命名：GFF3 是 `1, 2, 3`、FASTA 是 `Chr1, Chr2, Chr3`，反过来也有。不一致会让 `bedtools flank` 和 `bedtools getfasta` 静默给空输出 —— 不报错。

promoter / elements / perf-params 工作流都有预检：取 GFF3 第一条数据行的染色体名跟 FASTA 第一条 header 比，不匹配立即报错退出。别关掉。

<a id="cn-10"></a>

## 10. 染色体长度的获取

`bedtools flank` 需要 `<chrom>\t<length>` 文件（`-g`）来把坐标 clamp 到染色体边界。两条路：

1. 从 GFF3 的 `##sequence-region` 头取（首选）：`grep '^##sequence-region' anno.gff3 | awk '{print $2"\t"$4}'`。
2. 没有的话回退到 `samtools faidx genome.fa`，取生成的 `.fai` 前两列。

[`scripts/python/genome_chrom_lengths.py`](../../scripts/python/genome_chrom_lengths.py) 把这两条都包了。

<a id="cn-11"></a>

## 11. Python helper 当前状态

`scripts/python/` 下的 helper 已从"补丁工具"演成"管线主干"。当前活跃的：

| 脚本 | 角色 |
|---|---|
| `gff3_to_gene_bed.py` | GFF3 → BED 转换。处理 feature-regex 过滤、属性 key fallback（先 `gene_id=` 后 `ID=`）、1-based → 0-based、去重、丢 `start ≥ end`。 |
| `genome_chrom_lengths.py` | 染色体长度文件 + 命名一致性预检。 |
| `build_promoters.py` | 单 CLI 干完 flank → subtract → assess → UTR → `getfasta -s` → bg，替代原本散在 shell 里的内联序列。 |
| `run_homotypic.py` | 端到端 homotypic stage；组合上面所有 helper + `build/index_fimo_fused`。promoter / promoter_gap 工作流现在调它，而不是把步骤一条条写在 shell 里。 |
| `check_homotypic_contract.py` | 校验 5 文件 schema；每条 indexing pipeline 末尾跑一次。 |
| `calculate_length_to_tss.py` | per-gene TSS 到邻基因距离。`run_homotypic.py` 内部调。 |
| `assess_integrity.py` | 解决 split promoter；`build_promoters.py` 内部调。 |
| `parse_utrs.py` | 5'UTR 延伸；`build_promoters.py` 内部调。 |
| `calculateICfrommeme_IC_to_csv.py` | per-motif IC；`run_homotypic.py` 内部调。 |
| `parse_memefile.py` / `parse_memefile_batches.py` | 把 MEME 切成单 motif 文件 / N 批，给 IC 计算和 FIMO 并行用。 |

归档（`scripts/archive/`）：`parse_genelines.py`、`calculate_chromosome_length.py`、`calculateICfrommeme.py`、`parse_matrix_n*.py`、`parse_mRNAlines.py`、`parse_promoter_lengths.py`、`parse_promoters.py`、`promoter_add_gap.py`、`promoter_remove_overlap.py`、`strip_newlines.py`。要么逻辑被新 helper 吸收，要么活跃 pipeline 已不调用。

<a id="cn-12"></a>

## 12. `bedtools subtract` 与 split promoter

用 `bedtools subtract` 把启动子里和基因体重叠的部分切掉时，如果启动子内嵌了一个小基因，subtract 后启动子会被切成多个不连续片段。`assess_integrity.py` 处理这种情况：同基因的多个片段，只留离 TSS 最近的那个：

- `+` 链：留坐标最大的（最靠近 gene start）。
- `−` 链：留坐标最小的（最靠近 gene end）。

仅在请求了 overlap removal 时才跑这一步。`AllowOverlap` 模式下跳过。

<a id="cn-13"></a>

## 13. `awk -F'\t'` 处理 tab 分隔

处理 BED / GFF3 时 `awk` 一律传 `-F'\t'`。默认按空白分割大多数情况下也对，但如果染色体名或基因名里带空格（真实注释里有），字段就静默错位。防御性写法：

```bash
awk -F'\t' '...' file.bed
```

<a id="cn-14"></a>

## 14. 答疑：head-to-head / 嵌套基因

**核心原则：启动子位于基因转录起始位点（TSS）的上游。** `+` 链基因的上游在小坐标方向；`−` 链基因的上游在大坐标方向。

用四个 TAIR10 基因做具体分析：

**AT1G01010**（`+` 链，3631–5899）：TSS 在 3631。它是 chr1 的第一个基因，上游没有其它基因，所以启动子区域可以取 1–3630。

**AT1G01020**（`−` 链，6788–9130）：负链，TSS 在 9130（坐标最大那端）。上游是坐标增大方向，所以启动子是 9131 到下一个基因（AT1G03987，起始于 11101）之前，即 9131–11100。

**AT1G03987**（`+` 链 lncRNA，11101–11372）：TSS 在 11101，上游就是 AT1G01020 的右端（9130）之后，即 9131–11100。会发现这段和 AT1G01020 的推断启动子重叠了 —— 这是这种方法的天然问题：**当两个基因 head-to-head（背靠背）排列时，它们共享同一段基因间区作为各自的启动子。** 实操中用 `bedtools subtract` 各切一半，或者干脆都保留（`AllowOverlap` 模式）。

**AT1G01030**（`−` 链，11649–13714）：TSS 在 13714，上游是坐标更大方向，需要再下一个基因的位置才能定边界。

实务建议：

- 大多数人不会取整个基因间区，而是设个**固定窗口**（1 kb / 1.5 kb / 2 kb）。核心启动子在 TSS 上游几百 bp，远端调控元件一般在 2–3 kb 内。整段基因间区在基因稀疏区会太长，引入噪声。
- 用 gene 行坐标 = 自动选最长 5'UTR 那个转录本（见 §6）。要 per-isoform 精确得自己解析 mRNA 行。
- `−` 链 一定记住方向：**`+` 链基因的启动子在 start 坐标的左边，`−` 链基因的启动子在 end 坐标的右边。**

要更精确的启动子注释，可以叠加 ATAC-seq、ChIP-seq（H3K4me3）或 CAGE-seq 数据来校准。
