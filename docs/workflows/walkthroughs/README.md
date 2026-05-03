# docs/workflows/walkthroughs/ — step-by-step pipeline walkthroughs (conceptual reference)

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## What this is

Five hand-written, step-by-step bioinformatics audits of the PMET pipelines. ~2700 lines of `command → purpose → biological meaning → input sample → output sample → expected properties → observed result → PASS/FAIL` originally written against the pre-monorepo `scripts/pipeline/0X_*.sh` layout, refreshed in 2026-05 to point at the current monorepo paths.

The depth-of-detail target is reasoning about whether a pipeline output is biologically and structurally what it should be — coordinate traces for specific genes, reverse-complement checks on `−` strand promoters, IC computation per motif, binomial threshold derivations.

## Caveats

These docs are **not** auto-regenerated. Unlike the [`docs/workflows/*.md`](../) sibling docs (which `make test-audit` rebuilds from real runs against canonical inputs), what you see here is human-maintained.

- **Path references**: file paths and directory layout match the current monorepo (verified by direct `ls` on every prefix at refresh time).
- **`:line-range` annotations**: were captured against the **pre-monorepo** scripts. Treat them as section hints, not exact citations — the current files have reorganised some control flow.
- **Embedded code blocks**: occasionally show pre-monorepo command shapes (e.g. the `06_elements_longest` walkthrough's `build/fimo` GNU-parallel batch). The current `_pmet_index_element.sh` uses a single fused `build/indexing_fimo_fused` call instead. The walkthrough flags this inline; read the live script for the present-day exact commands.

## Path mapping (historical)

For provenance / git-archaeology against pre-monorepo commits:

| Then | Now |
|---|---|
| `scripts/pipeline/03_promoter.sh` | `scripts/workflows/promoter.sh` |
| `scripts/pipeline/04_intervals.sh` | `scripts/workflows/intervals.sh` |
| `scripts/pipeline/05_promoter_gap.sh` | `scripts/workflows/cli/05_promoter_gap.sh` |
| `scripts/pipeline/06_elements_longest.sh`, `07_elements_merged.sh` | one consolidated `scripts/workflows/elements.sh -s longest\|merged` |
| `scripts/pipeline/_elements_common.sh` | folded into `scripts/workflows/elements.sh` |
| `scripts/indexing/pmet_index_element.sh` | `scripts/workflows/cli/_pmet_index_element.sh` |
| `data/TAIR10.fasta`, `data/TAIR10.gff3` | `data/reference/TAIR10.{fasta,gff3}` |
| `data/Franco-Zorrilla_et_al_2014.meme` | `data/motifs/Franco-Zorrilla_et_al_2014.meme` |
| `data/homotypic_intervals/` | `data/demos/intervals/indexing/` |
| `scripts/gff3sort/gff3sort.pl` | `scripts/third_party/gff3sort/gff3sort.pl` |
| `build/index_fimo_fused`, `build/fimo`, `build/pmetParallel`, `build/pair_parallel` | `build/indexing_fimo_fused` (single fused indexer) + `build/pairing_parallel` |
| `results/03_promoter/`, `04_intervals/`, ... | `results/cli/promoter/`, `cli/intervals/`, ... |

## Why we keep them

Three uses:

1. **Pedagogical** — when a new contributor wants to understand "what does step 5 of the promoter pipeline actually compute, and how would I sanity-check its output by hand", these docs show worked examples (specific gene coordinates, reverse-complement verification, etc.) that the auto-generated [`docs/workflows/promoter.md`](../promoter.md) doesn't go into.
2. **Audit pattern** — if we ever extend the [`tests/audit/`](../../../tests/audit/) framework to do per-step traces (not just the end-of-pipeline `motif_output.txt` row that's currently shown as "Worked example"), these are the depth-of-detail target.
3. **Migration provenance** — they record what the pipelines looked like immediately before the monorepo merge, useful when bisecting across the merge.

## Files

| Walkthrough | Current equivalent script | Pre-monorepo script (referenced inside the doc) |
|---|---|---|
| [`promoter.md`](promoter.md) | `scripts/workflows/promoter.sh` | `scripts/pipeline/03_promoter.sh` |
| [`intervals.md`](intervals.md) | `scripts/workflows/intervals.sh` | `scripts/pipeline/04_intervals.sh` |
| [`promoter-gap.md`](promoter-gap.md) | `scripts/workflows/cli/05_promoter_gap.sh` | `scripts/pipeline/05_promoter_gap.sh` |
| [`elements-longest.md`](elements-longest.md) | `scripts/workflows/elements.sh -s longest` | `scripts/pipeline/06_elements_longest.sh` |
| [`elements-merged.md`](elements-merged.md) | `scripts/workflows/elements.sh -s merged` | `scripts/pipeline/07_elements_merged.sh` |

For the **current**, **auto-regenerated** workflow docs see the sibling [`docs/workflows/`](../) directory.

---

<a id="cn"></a>

## 这是什么

五份手写的、按 step 走的 PMET pipeline 生信审计文档。~2700 行，每步按 `命令 → 目的 → 生物学含义 → 输入截样 → 输出截样 → 期望属性 → 观察结果 → PASS/FAIL` 的格式展开。原本针对 monorepo 之前的 `scripts/pipeline/0X_*.sh` 那批脚本写，2026-05 刷新过一遍指到当前 monorepo 路径。

深度目标是推理"一条 pipeline 的输出在生物学上和结构上是不是它该是的样子" —— 具体基因的坐标追踪、`−` 链启动子的反向互补校验、per-motif IC 计算、binomial 阈值推导。

## 注意

这些文档**不会自动重生成**。跟兄弟目录 [`docs/workflows/*.md`](../)（由 `make test-audit` 在 canonical 输入上真实跑出来再重生成）不同，这里是手维护的。

- **路径引用**：跟当前 monorepo 一致（刷新时每个前缀都 `ls` 验过）。
- **`:line-range` 注解**：基于 monorepo 之前的脚本捕获。当 section 提示读，别当精确引用 —— 当前文件 reorganise 过控制流。
- **嵌入的代码块**：偶尔展示 monorepo 之前的命令形态（比如 `06_elements_longest` 里的 `build/fimo` GNU-parallel 批跑）。当前 `_pmet_index_element.sh` 已改用一次性 `build/indexing_fimo_fused`。文档内联标了；当前精确命令读源码。

## 路径映射（历史溯源）

跨 monorepo 合并点 bisect 用：

| 那时候 | 现在 |
|---|---|
| `scripts/pipeline/03_promoter.sh` | `scripts/workflows/promoter.sh` |
| `scripts/pipeline/04_intervals.sh` | `scripts/workflows/intervals.sh` |
| `scripts/pipeline/05_promoter_gap.sh` | `scripts/workflows/cli/05_promoter_gap.sh` |
| `scripts/pipeline/06_elements_longest.sh`、`07_elements_merged.sh` | 合成一份 `scripts/workflows/elements.sh -s longest\|merged` |
| `scripts/pipeline/_elements_common.sh` | 已折进 `scripts/workflows/elements.sh` |
| `scripts/indexing/pmet_index_element.sh` | `scripts/workflows/cli/_pmet_index_element.sh` |
| `data/TAIR10.fasta`、`data/TAIR10.gff3` | `data/reference/TAIR10.{fasta,gff3}` |
| `data/Franco-Zorrilla_et_al_2014.meme` | `data/motifs/Franco-Zorrilla_et_al_2014.meme` |
| `data/homotypic_intervals/` | `data/demos/intervals/indexing/` |
| `scripts/gff3sort/gff3sort.pl` | `scripts/third_party/gff3sort/gff3sort.pl` |
| `build/index_fimo_fused`、`build/fimo`、`build/pmetParallel`、`build/pair_parallel` | `build/indexing_fimo_fused`（单一 fused indexer）+ `build/pairing_parallel` |
| `results/03_promoter/`、`04_intervals/`...  | `results/cli/promoter/`、`cli/intervals/`... |

## 文件

| 走读文档 | 今天对应的脚本 | 文档里引用的 monorepo 前脚本 |
|---|---|---|
| [`promoter.md`](promoter.md) | `scripts/workflows/promoter.sh` | `scripts/pipeline/03_promoter.sh` |
| [`intervals.md`](intervals.md) | `scripts/workflows/intervals.sh` | `scripts/pipeline/04_intervals.sh` |
| [`promoter-gap.md`](promoter-gap.md) | `scripts/workflows/cli/05_promoter_gap.sh` | `scripts/pipeline/05_promoter_gap.sh` |
| [`elements-longest.md`](elements-longest.md) | `scripts/workflows/elements.sh -s longest` | `scripts/pipeline/06_elements_longest.sh` |
| [`elements-merged.md`](elements-merged.md) | `scripts/workflows/elements.sh -s merged` | `scripts/pipeline/07_elements_merged.sh` |

**当前**、**自动重生成**的 workflow 文档见兄弟目录 [`docs/workflows/`](../)。
