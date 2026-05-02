# Homotypic output contract

**[English](#en) · [汉文](#cn)**

The exact files indexing must produce so pairing can consume them. This is the source-of-truth schema; [`scripts/python/check_homotypic_contract.py`](../../scripts/python/check_homotypic_contract.py) enforces it. Any refactor that touches the indexing stage must keep this contract intact.

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Why the contract exists](#en-1) | [4. Cross-file invariants](#en-4) |
| [2. Layout](#en-2) | [5. Heterotypic output (separate)](#en-5) |
| [3. File-by-file schema](#en-3) | [6. Plotting output](#en-6) |

<a id="en-1"></a>

## 1. Why the contract exists

### What "contract" means here

A **contract**, in software engineering, is just a written-down agreement between two pieces of code: "if you produce X in shape Y, I promise to read it; conversely, if you change shape Y without telling me, I'm allowed to break." It's the same idea as a function signature, an HTTP API spec, or a file format spec — but at the granularity of a *directory* of files.

PMET has two stages — indexing (the slow scan) and pairing (the per-cluster test) — that talk to each other through a directory on disk. The indexing stage **writes** a directory; the pairing binary **reads** that directory. They don't share memory or a function call. So the only thing keeping them in sync is an agreement on **what files exist, what columns they have, and what the values mean**. That agreement is this document.

### Why we have to write it down

The pairing binary (`build/pair_parallel`, also `build/pmetParallel`, `build/pmet`) assumes a fixed shape: five files at the top, plus one `fimohits/` subdirectory. If indexing writes the wrong shape — wrong column order, missing motif, gene IDs that don't agree across files — pairing fails *late*, in confusing ways: a bizarre segfault deep in C++, or "0 enriched pairs" that's actually a silent data mismatch.

Codifying the contract here gives three concrete things:

1. **A target** for any new indexer (`index_fimo_fused`, `index_fimo_batched`, anything someone writes next year) to satisfy. As long as the new indexer produces this shape, any existing pairing binary can consume its output.
2. **A fail-fast validator**: [`scripts/python/check_homotypic_contract.py`](../../scripts/python/check_homotypic_contract.py) runs at the end of every indexing pipeline and crashes immediately if the shape is wrong — rather than passing a bad index downstream and waiting for pairing to misbehave.
3. **A reference** for downstream consumers (the Python audit code, anyone reading an index manually with `head` / `awk`).

The contract is **flat**: only the five top-level files + `fimohits/` are part of it. Pipelines may write other intermediate files (`memefiles/`, `genome_stripped.fa`, etc.) but **nothing outside the producing pipeline may rely on them** — they're scratch and could disappear in a refactor without warning.

<a id="en-2"></a>

## 2. Layout

```
$homotypic_output/
├── promoter_lengths.txt       required, deterministic
├── binomial_thresholds.txt    required, deterministic
├── IC.txt                     required, deterministic
├── universe.txt               required, deterministic
└── fimohits/
    └── <motif>.txt            required, one file per motif in MEME
```

<a id="en-3"></a>

## 3. File-by-file schema

### `promoter_lengths.txt`

- Columns (TAB-separated, **no header**):
  1. `gene_id` — string; must appear in `universe.txt`.
  2. `length` — positive integer; bp the gene contributes to the homotypic search space (gene-level after collapsing per-fragment lengths if applicable).
- One line per gene; gene IDs unique.
- Used by: `-p` argument to PMET pairing binaries.

### `binomial_thresholds.txt`

- Columns (TAB-separated, **no header**):
  1. `motif` — string; matches the basename of one file under `fimohits/`.
  2. `threshold` — float; the binomial p-value cutoff used during indexing.
  3. `extra` — float; pipeline-specific (e.g. corrected threshold).
- One line per motif; motif names unique.
- Used by: `-b` argument to PMET pairing binaries.
- Row order: not enforced by the contract (pairing doesn't depend on it). Pipelines that fan FIMO out in parallel batches sort with `sort -o` to remove a race-induced nondeterminism; the serial `index_fimo_fused` produces a deterministic order without sorting.

### `IC.txt`

- Columns (SPACE-separated, **no header**):
  1. `motif` — string; matches column 1 of `binomial_thresholds.txt`.
  2..N. `ic_<i>` — float; information content per motif column (one value per position).
- One line per motif; motif names unique.
- Used by: `-c` argument to PMET pairing binaries.
- **Row order**: stable; produced by `scripts/python/calculateICfrommeme_IC_to_csv.py` in `mode='w'` so subsequent runs do not append.

### `universe.txt`

- Format: one gene ID per line, no header, ASCII.
- Lines: unique gene IDs that survived the indexing universe filter (length ≥ minimum, valid coordinates, etc.).
- Used by: `grep -Ff universe.txt user_genes` to filter the user's gene list before invoking pairing.

### `fimohits/<motif>.txt`

- One file per motif listed in `binomial_thresholds.txt` (and therefore in `IC.txt`).
- FIMO TSV format with the indexing pipeline's per-gene top-k filtering and binomial thresholding already applied.
- Columns relevant to pairing:
  - column 2 — `gene_id` (must be in `universe.txt`).
  - column 7 — `p-value` (float; must be `< the motif's threshold` from `binomial_thresholds.txt`).
- Used by: `-f $homotypic_output/fimohits` argument to PMET pairing binaries.

<a id="en-4"></a>

## 4. Cross-file invariants

These hold across the contract and are checked by the Python validator:

1. `set(motifs in binomial_thresholds.txt)` == `set(motifs in IC.txt)` == `set(basenames of fimohits/*.txt)`.
2. `set(genes in promoter_lengths.txt)` ⊆ `set(genes in universe.txt)`.
3. Every gene mentioned in any `fimohits/<motif>.txt` (column 2) is in `universe.txt`.
4. No empty files; no duplicate motif names; no duplicate gene names within a single file.

To run the validator manually on any homotypic directory:

```bash
python3 scripts/python/check_homotypic_contract.py path/to/homotypic_output/
```

**Needs** — `python3` only (standard library). The directory should already exist with the five files + `fimohits/`.

**Produces** — stdout report of pass / fail per invariant; exit 0 only if all four pass.

**How to read it** — non-zero exit + a failed invariant line names the offending file. Common failures: a motif in `binomial_thresholds.txt` has no corresponding `fimohits/<motif>.txt` (the FIMO batch for it failed); a gene appears in `fimohits/<motif>.txt` column 2 but not in `universe.txt` (the universe filter ran after FIMO and dropped it).

<a id="en-5"></a>

## 5. Heterotypic output (separate)

`$heterotypic_output/motif_output.txt` is the result of the pairing binary; it has its own 11-column TSV header documented at the top of [`scripts/r/process_pmet_result.R`](../../scripts/r/process_pmet_result.R) and explained in main README §6.

<a id="en-6"></a>

## 6. Plotting output (heatmaps and histograms)

Pipelines that render heatmaps (promoter, elements, pair_only) write three PNGs per task: `heatmap.png`, `heatmap_overlap.png`, `heatmap_overlap_unique.png`. Histogram subdirectories (`histogram/`, `histogram_overlap/`, `histogram_overlap_unique/`) sit beside them.

When a task has insufficient significant pairs after R filtering, only the histograms are written and R prints `No meaningful data left after filtering!`. This is data-driven and **not** a regression — the test data really has no significant pairs at the chosen IC threshold.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 为什么要这个契约](#cn-1) | [4. 跨文件不变量](#cn-4) |
| [2. 目录布局](#cn-2) | [5. Heterotypic 输出（另一份契约）](#cn-5) |
| [3. 逐文件 schema](#cn-3) | [6. 绘图输出](#cn-6) |

<a id="cn-1"></a>

## 1. 为什么要这个契约

### 这里的"契约"是什么意思

软件工程里所谓"**契约**"（contract），就是两段代码之间一份**写下来的约定**："你按 Y 形态产出 X，我就保证能读；反过来你不通知就改了 Y 形态，我可以坏给你看。" 跟函数签名、HTTP API spec、文件格式规范是同一个思路，只不过粒度是一**整个目录**的文件。

PMET 有两个阶段 —— indexing（重扫描）和 pairing（per-cluster 检验） —— 它们之间通过盘上一个目录来交流。indexing 阶段**写**这个目录；pairing 二进制**读**这个目录。它们不共享内存、不互相函数调用。所以让两者同步的唯一东西，就是一份关于**有哪些文件、什么列、值是什么含义**的约定。这份约定就是本文档。

### 为什么必须写下来

pairing 二进制（`build/pair_parallel`，也包括 `build/pmetParallel`、`build/pmet`）假定一个固定形态：顶层 5 个文件 + 一个 `fimohits/` 子目录。indexing 若写出不符的形态 —— 列序错、缺 motif、跨文件 gene ID 不一致 —— pairing 会**很晚才挂**、报错也费解：可能是 C++ 深处一个莫名其妙的 segfault，也可能是"0 个富集对"——其实是数据没对上，silently 出了错。

把契约写在这里能给三样具体东西：

1. **一个目标**：任何新写的 indexer（`index_fimo_fused`、`index_fimo_batched`、明年某人新写的）都按这份形态产出，现有任何 pairing 二进制都能消费。
2. **一份 fail-fast validator**：[`scripts/python/check_homotypic_contract.py`](../../scripts/python/check_homotypic_contract.py) 在每条 indexing pipeline 末尾跑一次，形态不对立刻挂 —— 而不是把坏索引传到下游、等 pairing 出怪事。
3. **一份参考**：给下游消费者（Python 审计代码、用 `head` / `awk` 手翻索引的人）。

契约是**扁平**的：只有那 5 个顶层文件 + `fimohits/` 算契约的一部分。Pipeline 写其它中间文件（`memefiles/`、`genome_stripped.fa` 等）随意，但**写它们的那条 pipeline 之外，谁都不能依赖** —— 那些是 scratch，下次重构可能不打招呼就消失。

<a id="cn-2"></a>

## 2. 目录布局

```
$homotypic_output/
├── promoter_lengths.txt       必需，确定性
├── binomial_thresholds.txt    必需，确定性
├── IC.txt                     必需，确定性
├── universe.txt               必需，确定性
└── fimohits/
    └── <motif>.txt            必需，每个 MEME 里的 motif 一份
```

<a id="cn-3"></a>

## 3. 逐文件 schema

### `promoter_lengths.txt`

- 列（TAB 分隔，**无表头**）：
  1. `gene_id` —— 字符串；必须在 `universe.txt` 里。
  2. `length` —— 正整数；该基因贡献给 homotypic 搜索空间的 bp 数（涉及拆段时，这里给的是 gene 层级合并后的总长）。
- 每基因一行；gene ID 唯一。
- 谁用：PMET pairing 二进制的 `-p` 参数。

### `binomial_thresholds.txt`

- 列（TAB 分隔，**无表头**）：
  1. `motif` —— 字符串；与 `fimohits/` 下某个文件的 basename 对应。
  2. `threshold` —— 浮点；indexing 时用的 binomial p 值阈值。
  3. `extra` —— 浮点；pipeline 自定义额外值（比如校正后阈值）。
- 每 motif 一行；motif 名唯一。
- 谁用：PMET pairing 二进制的 `-b` 参数。
- 行序：契约不强制（pairing 不依赖）。并行 FIMO 批量的 pipeline 用 `sort -o` 排一下消除并行 race；串行的 `index_fimo_fused` 天然有确定性顺序，无需排。

### `IC.txt`

- 列（**空格**分隔，**无表头**）：
  1. `motif` —— 字符串；与 `binomial_thresholds.txt` 第 1 列匹配。
  2..N. `ic_<i>` —— 浮点；motif 每一列的信息量（每位置一个值）。
- 每 motif 一行；motif 名唯一。
- 谁用：PMET pairing 二进制的 `-c` 参数。
- **行序**：稳定；由 `scripts/python/calculateICfrommeme_IC_to_csv.py` 以 `mode='w'` 写出，重跑不 append。

### `universe.txt`

- 格式：每行一个 gene ID，无表头，ASCII。
- 行：indexing universe 过滤后留下的、唯一的 gene ID（长度 ≥ 最小值、坐标合法等）。
- 谁用：跑 pairing 之前，用 `grep -Ff universe.txt user_genes` 过用户的基因列表。

### `fimohits/<motif>.txt`

- 每个 `binomial_thresholds.txt`（与 `IC.txt`）里列出的 motif 一份。
- FIMO TSV 格式，已经应用了 indexing pipeline 的 per-gene top-k 过滤和 binomial 阈值。
- pairing 关心的列：
  - 第 2 列 —— `gene_id`（必须在 `universe.txt` 里）。
  - 第 7 列 —— `p-value`（浮点；必须 `< binomial_thresholds.txt` 里这个 motif 的 threshold）。
- 谁用：PMET pairing 二进制的 `-f $homotypic_output/fimohits` 参数。

<a id="cn-4"></a>

## 4. 跨文件不变量

下面这些跨文件成立，由 Python validator 检查：

1. `set(binomial_thresholds.txt 的 motifs)` == `set(IC.txt 的 motifs)` == `set(fimohits/*.txt 的 basename)`。
2. `set(promoter_lengths.txt 的 genes)` ⊆ `set(universe.txt 的 genes)`。
3. `fimohits/<motif>.txt` 第 2 列里出现的每个 gene 都在 `universe.txt` 里。
4. 文件不能空；motif 名不能重；同一个文件内 gene 名不能重。

手动对任意 homotypic 目录跑 validator：

```bash
python3 scripts/python/check_homotypic_contract.py path/to/homotypic_output/
```

**需要** —— 仅 `python3`（标准库）。目录里必须已经有那 5 个文件和 `fimohits/`。

**产出** —— stdout 逐项不变量的 pass / fail 报告；只有 4 项全过 exit 0。

**怎么解读** —— 退出非 0 + 某条不变量 fail 的行会指出有问题的文件。常见失败：`binomial_thresholds.txt` 里某个 motif 没有对应的 `fimohits/<motif>.txt`（它那一批 FIMO 跑挂了）；`fimohits/<motif>.txt` 第 2 列里的 gene 不在 `universe.txt` 里（universe 过滤是在 FIMO 之后跑的、把它丢了）。

<a id="cn-5"></a>

## 5. Heterotypic 输出（另一份契约）

`$heterotypic_output/motif_output.txt` 是 pairing 二进制的产物；它自己的 11 列 TSV 表头记在 [`scripts/r/process_pmet_result.R`](../../scripts/r/process_pmet_result.R) 顶部，主 README §6 也有讲。

<a id="cn-6"></a>

## 6. 绘图输出（heatmap 和直方图）

会渲染 heatmap 的 pipeline（promoter、elements、pair_only）每个任务写 3 张 PNG：`heatmap.png`、`heatmap_overlap.png`、`heatmap_overlap_unique.png`。直方图子目录（`histogram/`、`histogram_overlap/`、`histogram_overlap_unique/`）放在它们旁边。

任务在 R 过滤之后没有足够多的显著 pair 时，只写直方图，R 会打 `No meaningful data left after filtering!`。这是数据驱动的，**不是**回归 —— 测试数据在选定的 IC 阈值下确实没有显著 pair。
