# tests/integration/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose & layout](#en-1) | [5. run_with_verify.sh](#en-5) |
| [2. Per-script status](#en-2) | [6. Baseline staleness](#en-6) |
| [3. Quick start](#en-3) | [7. Adding a new check](#en-7) |
| [4. verify_heatmap_consistency.py](#en-4) | |

<a id="en-1"></a>

## 1. Purpose & layout

You changed something in a pipeline script (`scripts/workflows/...`) and you want to know whether the script-level invariants you depend on still hold — the bedtools call still uses `-s` for strand-aware extraction, the chromosome-name preflight still catches `1` vs `Chr1`, the GFF3 → BED converter still resolves split fragments correctly. Unit tests cover individual functions; this directory checks the same invariants but at the **script** level, against tiny synthetic fixtures so a full smoke run is ~3 seconds.

It sits in the middle of the test pyramid: slower than `tests/unit/` (individual functions), faster and lighter than `tests/audit/` (which re-runs full workflows and rewrites the audit docs).

```
tests/integration/
├── run_smoke.sh                          fast invariants (< 5 s, hits real bedtools/samtools)
├── run_pipeline02_one_combo.sh           one-cell perf-params run for hashing
├── run_pipeline08_ic_sweep.sh            IC-threshold sweep on a built homotypic index
├── test_pipeline02_strand_realdata.sh    TAIR10 strand-extraction fixed-bug check
├── verify_baseline.sh                    generic <results_dir> ↔ <baseline.hashes.txt> diff
├── run_with_verify.sh                    dispatcher: runs pipeline NN then verify_baseline.sh
├── verify_heatmap_consistency.py         R-vs-frontend heatmap motif-selection diff (§4)
├── fixtures/                             tiny FASTA/BED used by run_smoke.sh
└── baselines/                            recorded {exit, hashes, stdout, stderr} per pipeline
```

<a id="en-2"></a>

## 2. Per-script status

| Script | Wall time | Needs | Status |
|---|---|---|---|
| `run_smoke.sh` | ~3–10 s | bedtools, samtools, python3 (TAIR10 optional, Rscript optional) | ✅ all 13+ checks pass; the R-vs-frontend heatmap consistency check at the tail is auto-skipped if Rscript isn't on PATH |
| `test_pipeline02_strand_realdata.sh` | ~3 s | TAIR10 (`data/reference/TAIR10.{fasta,gff3}`) | ✅ skips cleanly without TAIR10, passes with it |
| `verify_baseline.sh` | seconds | shasum | ✅ generic — diff any results dir against any hashes file |
| `run_pipeline02_one_combo.sh` | ~1 min | TAIR10, full FIMO + PMET stack | ✅ runs end-to-end (output won't match the stale 02 baseline; see [§5](#en-5)) |
| `run_pipeline08_ic_sweep.sh` | ~30 s × N IC values | a built homotypic index (`results/cli/promoter/01_homotypic/`) | ✅ runs end-to-end |
| `run_with_verify.sh` | varies (per NN) | per-pipeline (see [§5](#en-5)) | ✅ runners invokable; baselines stale (see [§6](#en-6)) |
| `verify_heatmap_consistency.py` | ~5–10 s | Rscript + a `motif_output.txt` (PNG render extras: `--render-dir`) | ✅ AGREE on real fixtures after the algorithm-alignment commit (see [§4](#en-4)) |

<a id="en-3"></a>

## 3. Quick start

```bash
# Fast invariants — no real data needed beyond bedtools/samtools.
make test-integration                        # equivalent to: bash tests/integration/run_smoke.sh

# Real-data strand extraction (skips if TAIR10 not yet fetched):
bash tests/integration/test_pipeline02_strand_realdata.sh

# Verify any results dir against a recorded hashes file:
bash tests/integration/verify_baseline.sh \
    results/cli/promoter \
    tests/integration/baselines/03_baseline.hashes.txt
```

**Needs** — `bedtools`, `samtools`, `python3` on `$PATH`. The synthetic fixtures under `fixtures/` ship with the repo. The TAIR10 real-data check skips cleanly if `data/reference/TAIR10.{fasta,gff3}` aren't present (run `make fetch-data` once if you want it to actually run).

**Produces** — stdout only. `make test-integration` exits 0 if all 13 checks pass, 1 if any fail.

**How to read it** — each section announces itself with `[smoke] <label>`, then prints PASS / FAIL per check:

```
[smoke] bedtools getfasta strand-awareness (P0 strand fix)
  PASS  + strand sequence unchanged by -s (AACTGCAACTGC)
  PASS  - strand sequence reverse-complemented by -s (AACTGCAACTGC -> GCAGTTGCAGTT)
  PASS  - strand fixture is non-palindromic

[smoke] build_promoters.py invokes bedtools getfasta with -s
  PASS  build_promoters.py bedtools getfasta call includes -s

[smoke] 01_perf_cpu inputs sanity
  PASS  01 gene_input_file exists (data/genes/genes_cell_type_treatment.txt)
  PASS  01 draw_heatmap.R receives 7 arguments
…
[smoke] real-data strand extraction (TAIR10)
  PASS  TAIR10 promoter FASTA: + strand unchanged, - strand reverse-complemented by -s

[smoke] all checks passed
```

If TAIR10 isn't fetched, the last section prints `SKIP TAIR10 inputs not present` instead of running — that's expected, not a failure. A FAIL surfaces the offending file path and the assertion that broke (e.g. `02_perf_params.sh missing chromosome-name preflight`).

<a id="en-4"></a>

## 4. verify_heatmap_consistency.py — R vs frontend motif selection

**Why it exists.** Both the R heatmap pipeline (`scripts/r/draw_heatmap.R`, used by the CLI workflows and the embedded QuickLook) and the frontend visualizer (`/visualize`) consume the same `motif_output.txt`. Historically they used **different motif-selection algorithms** so the two heatmaps showed different motifs for the same input — the per-cluster top-N pair scan in the frontend and the score-based ranking in R picked different subsets when the data had a long tail. The frontend now mirrors R's algorithm; this script is the regression check that keeps it that way.

**Wired into `make test-integration`.** `run_smoke.sh` runs this check at the tail against the bundled fixture under `fixtures/heatmap/motif_output.txt` whenever `Rscript` is on `$PATH` (skipped cleanly otherwise — same conditional pattern as the TAIR10 strand check). For ad-hoc runs against your own task outputs, invoke the script directly:

**What it does.**

1. Parses a `motif_output.txt`.
2. Re-runs R's `ProcessPmetResult` via `scripts/r/dump_processed_data.R`, dumps the per-cluster motif list to JSON.
3. Replicates the frontend's `processPmetResult()` (in `apps/pmet_frontend/app/visualize/page.tsx`) in Python and computes its own per-cluster motif list.
4. Diffs the two motif sets per cluster. Exits 0 on agree, 1 on diverge, 2 on tooling errors.

**Needs.**

| | |
|---|---|
| `Rscript` | required (drives the R-side dump) |
| `python3` | 3.9+ (uses `Path.is_relative_to`) |
| `motif_output.txt` | any PMET pairing output; default fixture is the demo at `data/demos/promoters/pairing/demo/motif_output.txt`, but real-task outputs work too |
| Playwright + Chromium | optional, only for `--render-dir` (visual side-by-side) |
| Docker stack at `--base-url` | optional, only for `--render-dir` frontend capture |

**Commands.**

```bash
# Default: data-level check on the demo fixture.
python3 tests/integration/verify_heatmap_consistency.py

# On a real task's output (any motif_output.txt works).
python3 tests/integration/verify_heatmap_consistency.py \
    --input results/app/<task_id>/pairing/motif_output.txt

# Tune the cap if you want to match a specific draw_heatmap.R run.
python3 tests/integration/verify_heatmap_consistency.py \
    --input <path> --max-motifs 30 --p-adj-limit 0.05

# Visual side-by-side. Drops r.png + frontend.png into the chosen dir.
python3 tests/integration/verify_heatmap_consistency.py \
    --input <path> --render-dir tmp/heatmap_visuals
```

**Produces.**

- **Stdout** — one line per cluster (`== <cluster>: N motifs match` on agree, `!! <cluster>: motif set differs ...` on diverge with R-only / TS-only sets).
- **Report file** — `tests/integration/heatmap_consistency_report.txt` (gitignored; rewritten every run). Same content as stdout, useful for CI logs.
- **Render dir (with `--render-dir`)** — `<dir>/r.png` and (if Playwright is installed and the stack is up) `<dir>/frontend.png`. Each render is independent; if the frontend capture fails the R PNG still gets written, with a stderr hint about the missing dep.

**Reading the output.**

```
# heatmap consistency report
# input:  results/app/phase1_f506a30bf6534282/pairing/motif_output.txt
# params: p_adj_limit=0.05 unique=True max_motifs=30
# verdict: AGREE

== heat_down: 15 motifs match
== heat_up: 15 motifs match
```

A `DIVERGE` verdict prints the symmetric difference (`R only (n): ...`, `TS only (n): ...`) plus the TS top-N pairs that drove its choice — enough to debug whether the gap is in the score formula, the per-cluster cap, the secondary global trim, or upstream filters.

<a id="en-5"></a>

## 5. run_with_verify.sh — pipeline runner with diff

Dispatches by pipeline number. The numbers are inherited from the pre-monorepo numbering and the runners now point at the post-monorepo `scripts/workflows/...` files:

| NN | Runs | Default results_dir |
|---|---|---|
| 00 | `run_smoke.sh` | (no dir) |
| 01 | `scripts/workflows/cli/01_perf_cpu.sh` | `results/cli/01_perf_cpu` |
| 02 | `tests/integration/run_pipeline02_one_combo.sh` | `results/02_perf_params` |
| 03 | `scripts/workflows/promoter.sh` | `results/cli/promoter` |
| 04 | `scripts/workflows/intervals.sh` | `results/cli/intervals` |
| 05 | `scripts/workflows/cli/05_promoter_gap.sh` | `results/05_promoter_gap` |
| 06 | `scripts/workflows/elements.sh -s longest -e $E` | `results/cli/elements_longest_$E_norm` |
| 07 | `scripts/workflows/elements.sh -s merged  -e $E` | `results/cli/elements_merged_$E_norm` |
| 08 | `scripts/workflows/pair_only.sh` (needs 03 first) | `results/cli/pair_only/cell_type_treatment_ic4` |

```bash
# Run the promoter pipeline end-to-end and diff against its recorded baseline.
bash tests/integration/run_with_verify.sh 03

# Same for elements with the mRNA element under -s longest.
bash tests/integration/run_with_verify.sh 06 mrna

# Same for pair_only — but it needs 03's homotypic index, so run 03 first.
bash tests/integration/run_with_verify.sh 08
```

<a id="en-6"></a>

## 6. Baseline staleness

The `baselines/` directory was captured before the monorepo merge, when the workflow scripts were under `scripts/scripts/0X_*.sh` and their outputs landed in directories like `data/homotypic_promoters/`. Today's workflow scripts produce different paths (`results/cli/promoter/` etc.) and slightly different log lines, so **`verify_baseline.sh` will report many spurious diffs even on a clean monorepo run** until the baselines are regenerated.

The runner scripts themselves (the left half of `run_with_verify.sh`) do work — use the dispatcher to drive an end-to-end run, then ignore the diff step until you can reset baselines:

```bash
# Capture a fresh baseline for one pipeline (manual procedure):

# 1. Produce a clean run.
bash scripts/workflows/promoter.sh

# 2. sha256 every output file in stable order, redirect into the baseline file.
( cd results/cli/promoter && find . -type f | sort | xargs shasum -a 256 ) \
    > tests/integration/baselines/03_baseline.hashes.txt
```

The same pattern works for any of `01, 02, 04, 05, 06, 07, 08` — swap the runner script and the per-pipeline `results_dir` from the dispatch table above.

<a id="en-7"></a>

## 7. Adding a new check

1. New `.sh` file under `tests/integration/`.
2. `set -uo pipefail` and `cd "$repo_root"` early; never assume CWD.
3. Resolve repo paths from `repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)`, never from `$script_dir/..` — the latter only makes sense if the script lives one level under `tests/`.
4. Print PASS / FAIL per assertion; exit non-zero on any FAIL.
5. List it in this README's table and (if it's an invariant smoke check) wire it into the main README §9 Track 3 description.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途与目录](#cn-1) | [5. run_with_verify.sh](#cn-5) |
| [2. 各脚本状态](#cn-2) | [6. Baseline 已过期](#cn-6) |
| [3. Quick start](#cn-3) | [7. 新增 check](#cn-7) |
| [4. verify_heatmap_consistency.py](#cn-4) | |

<a id="cn-1"></a>

## 1. 用途与目录

你改了 pipeline 脚本（`scripts/workflows/...`）里的某个东西，想知道你依赖的那些脚本级不变量还在不在 —— bedtools 调用仍带 `-s` 做 strand-aware 抽取吗？染色体名预检还能逮住 `1` vs `Chr1` 吗？GFF3 → BED 转换还能正确处理拆段的同基因 fragment 吗？unit test 覆盖单个函数，这个目录用同样的不变量但在**脚本**层面验证，跑的是小的合成 fixture，所以一次 smoke 大约 3 秒。

它在测试金字塔中间：比 `tests/unit/`（单函数）慢，比 `tests/audit/` （重跑完整 workflow 还重写审计文档）轻。

```
tests/integration/
├── run_smoke.sh                          快不变量（< 5 秒，调真实 bedtools/samtools）
├── run_pipeline02_one_combo.sh           perf-params 单 combo 跑一遍，用于打 hash
├── run_pipeline08_ic_sweep.sh            在已建 homotypic 索引上做 IC 阈值 sweep
├── test_pipeline02_strand_realdata.sh    TAIR10 strand 抽取的修过 bug 校验
├── verify_baseline.sh                    通用 <results_dir> ↔ <baseline.hashes.txt> diff
├── run_with_verify.sh                    调度器：跑 pipeline NN 再 verify_baseline.sh
├── verify_heatmap_consistency.py         R vs 前端热图 motif 选择对比（§4）
├── fixtures/                             run_smoke.sh 用的小 FASTA/BED
└── baselines/                            每个 pipeline 录制的 {exit, hashes, stdout, stderr}
```

<a id="cn-2"></a>

## 2. 各脚本状态

| 脚本 | 耗时 | 需要 | 状态 |
|---|---|---|---|
| `run_smoke.sh` | ~3–10 秒 | bedtools、samtools、python3（TAIR10 可选，Rscript 可选） | ✅ 13+ 项检查全过；尾部 R-vs-前端热图一致性检查在 Rscript 不在 PATH 时自动跳过 |
| `test_pipeline02_strand_realdata.sh` | ~3 秒 | TAIR10（`data/reference/TAIR10.{fasta,gff3}`） | ✅ 没 TAIR10 干净跳过，有就过 |
| `verify_baseline.sh` | 秒级 | shasum | ✅ 通用 —— diff 任意 results 目录对任意 hashes 文件 |
| `run_pipeline02_one_combo.sh` | ~1 分钟 | TAIR10、完整 FIMO + PMET 栈 | ✅ 端到端能跑（输出对不上过期的 02 baseline，见 [§5](#cn-5)） |
| `run_pipeline08_ic_sweep.sh` | ~30 秒 × N 个 IC 值 | 已建好的 homotypic 索引（`results/cli/promoter/01_homotypic/`） | ✅ 端到端能跑 |
| `run_with_verify.sh` | 因 NN 而异 | per-pipeline（见 [§5](#cn-5)） | ✅ runner 可调用；baseline 已过期（见 [§6](#cn-6)） |
| `verify_heatmap_consistency.py` | ~5–10 秒 | Rscript + 一份 `motif_output.txt`（PNG 渲染需 `--render-dir`） | ✅ 算法对齐 commit 之后两端在真实 fixture 上 AGREE（见 [§4](#cn-4)） |

<a id="cn-3"></a>

## 3. Quick start

```bash
# 快不变量 —— 除 bedtools/samtools 外不需要真实数据。
make test-integration                        # 等价于：bash tests/integration/run_smoke.sh

# 真实数据 strand 抽取（没 TAIR10 干净跳过）：
bash tests/integration/test_pipeline02_strand_realdata.sh

# diff 任意 results 目录对录制的 hashes 文件：
bash tests/integration/verify_baseline.sh \
    results/cli/promoter \
    tests/integration/baselines/03_baseline.hashes.txt
```

**需要** —— `$PATH` 上要有 `bedtools`、`samtools`、`python3`。 `fixtures/` 下的合成 fixture 随仓库一起带。TAIR10 真实数据检查在缺 `data/reference/TAIR10.{fasta,gff3}` 时干净跳过（想真跑就先 `make fetch-data` 一次）。

**产出** —— 仅 stdout。`make test-integration` 13 项 check 全过 exit 0，任一 fail exit 1。

**怎么解读** —— 每段先打 `[smoke] <label>`，逐 check 输出 PASS / FAIL：

```
[smoke] bedtools getfasta strand-awareness (P0 strand fix)
  PASS  + strand sequence unchanged by -s (AACTGCAACTGC)
  PASS  - strand sequence reverse-complemented by -s (AACTGCAACTGC -> GCAGTTGCAGTT)
  PASS  - strand fixture is non-palindromic

[smoke] build_promoters.py invokes bedtools getfasta with -s
  PASS  build_promoters.py bedtools getfasta call includes -s

[smoke] 01_perf_cpu inputs sanity
  PASS  01 gene_input_file exists (data/genes/genes_cell_type_treatment.txt)
  PASS  01 draw_heatmap.R receives 7 arguments
…
[smoke] real-data strand extraction (TAIR10)
  PASS  TAIR10 promoter FASTA: + strand unchanged, - strand reverse-complemented by -s

[smoke] all checks passed
```

没拉 TAIR10 的话最后一段打 `SKIP TAIR10 inputs not present` 而不是真跑 —— 这是预期，不是失败。FAIL 会把出问题的文件路径和挂掉的断言打出来（例如 `02_perf_params.sh missing chromosome-name preflight`）。

<a id="cn-4"></a>

## 4. verify_heatmap_consistency.py —— R 与前端 motif 选择一致性

**为什么有这玩意**：R 端热图流水线（`scripts/r/draw_heatmap.R`，CLI workflow + 任务详情页 QuickLook 都走它）和前端 `/visualize` 共用同一份 `motif_output.txt`。两边一度用**不同的 motif 选择算法** —— 前端 per-cluster top-N pair 扫描 vs R 的累计得分排名 —— 同一份输入里长尾大的时候挑出来的 motif 完全不同。前端现在已经对齐到 R 算法，本脚本就是把这件事固化成回归 check。

**已并入 `make test-integration`**：`run_smoke.sh` 在尾部自动针对 `fixtures/heatmap/motif_output.txt` 跑一遍这个检查（只要 `Rscript` 在 `$PATH` 上；不在就干净跳过 —— 跟 TAIR10 strand 检查同样的条件）。要拿自己的任务输出 ad-hoc 跑就直接调脚本：

**在做什么**：

1. 解析 `motif_output.txt`。
2. 通过 `scripts/r/dump_processed_data.R` 跑 R 的 `ProcessPmetResult`，把 per-cluster motif list 输出成 JSON。
3. 用 Python 复刻前端 [`apps/pmet_frontend/app/visualize/page.tsx::processPmetResult`](../../apps/pmet_frontend/app/visualize/page.tsx) 的逻辑，自己算一份 per-cluster motif list。
4. per-cluster 比对两个集合。一致 exit 0，分叉 exit 1，工具/输入错 exit 2。

**需要**：

| | |
|---|---|
| `Rscript` | 必需（驱动 R 端 dump） |
| `python3` | 3.9+（用了 `Path.is_relative_to`） |
| `motif_output.txt` | 任意 PMET pairing 输出；默认 fixture 是 `data/demos/promoters/pairing/demo/motif_output.txt`，真实任务输出也行 |
| Playwright + Chromium | 可选，仅 `--render-dir`（视觉对比）要用 |
| 跑着的 docker 栈（`--base-url`） | 可选，仅 `--render-dir` 抓前端图要用 |

**命令**：

```bash
# 默认：在 demo fixture 上跑数据级 check。
python3 tests/integration/verify_heatmap_consistency.py

# 真实任务的输出（任何 motif_output.txt 都行）。
python3 tests/integration/verify_heatmap_consistency.py \
    --input results/app/<task_id>/pairing/motif_output.txt

# 想匹配某次 draw_heatmap.R 跑的，调上限。
python3 tests/integration/verify_heatmap_consistency.py \
    --input <path> --max-motifs 30 --p-adj-limit 0.05

# 视觉左右对比。在指定目录里输出 r.png + frontend.png。
python3 tests/integration/verify_heatmap_consistency.py \
    --input <path> --render-dir tmp/heatmap_visuals
```

**产出**：

- **stdout** —— 每个 cluster 一行（一致打 `== <cluster>: N motifs match`，分叉打 `!! <cluster>: motif set differs ...` 加 R 独有 / TS 独有的 motif 列表）。
- **报告文件** —— `tests/integration/heatmap_consistency_report.txt`（gitignored，每次重写）。内容跟 stdout 一样，方便看 CI 日志。
- **render 目录（带 `--render-dir` 时）** —— `<dir>/r.png` 加（如果 Playwright 装了且栈跑着）`<dir>/frontend.png`。两个渲染独立；前端抓失败时 R PNG 仍照常生成，并打一行 stderr 提示缺什么。

**怎么解读**：

```
# heatmap consistency report
# input:  results/app/phase1_f506a30bf6534282/pairing/motif_output.txt
# params: p_adj_limit=0.05 unique=True max_motifs=30
# verdict: AGREE

== heat_down: 15 motifs match
== heat_up: 15 motifs match
```

`DIVERGE` 的报告会打两边的对称差（`R only (n): ...`、`TS only (n): ...`）和驱动前端选择的 TS top-N pair —— 调 bug 时看一眼就知道差在 score 公式、per-cluster cap、二次全局裁剪还是上游 filter。

<a id="cn-5"></a>

## 5. run_with_verify.sh —— "跑 + diff" pipeline runner

按 pipeline 编号调度。编号沿用 monorepo 合并前的命名，runner 已指向合并后的 `scripts/workflows/...`：

| NN | 跑 | 默认 results_dir |
|---|---|---|
| 00 | `run_smoke.sh` | （无目录） |
| 01 | `scripts/workflows/cli/01_perf_cpu.sh` | `results/cli/01_perf_cpu` |
| 02 | `tests/integration/run_pipeline02_one_combo.sh` | `results/02_perf_params` |
| 03 | `scripts/workflows/promoter.sh` | `results/cli/promoter` |
| 04 | `scripts/workflows/intervals.sh` | `results/cli/intervals` |
| 05 | `scripts/workflows/cli/05_promoter_gap.sh` | `results/05_promoter_gap` |
| 06 | `scripts/workflows/elements.sh -s longest -e $E` | `results/cli/elements_longest_$E_norm` |
| 07 | `scripts/workflows/elements.sh -s merged  -e $E` | `results/cli/elements_merged_$E_norm` |
| 08 | `scripts/workflows/pair_only.sh`（需先跑 03） | `results/cli/pair_only/cell_type_treatment_ic4` |

```bash
# 端到端跑 promoter pipeline 并 diff 录制的 baseline。
bash tests/integration/run_with_verify.sh 03

# 同样跑 elements 在 -s longest 下用 mRNA element。
bash tests/integration/run_with_verify.sh 06 mrna

# 同样跑 pair_only —— 但它需要 03 的同型索引，所以先跑 03。
bash tests/integration/run_with_verify.sh 08
```

<a id="cn-6"></a>

## 6. Baseline 已过期

`baselines/` 是 monorepo 合并前抓的，那时 workflow 脚本在 `scripts/scripts/0X_*.sh`，输出落到 `data/homotypic_promoters/` 那种目录。今天的 workflow 脚本走不同路径（`results/cli/promoter/` 等）和略有不同的 log 行，所以**即便干净的 monorepo 运行，`verify_baseline.sh` 也会报很多假 diff**，直到重抓 baseline 为止。

runner 脚本本身（`run_with_verify.sh` 左半边）能跑——用调度器把端到端跑一遍，然后跳过 diff 步骤即可，等 baseline 重抓后再启用：

```bash
# 单个 pipeline 重抓 baseline 的手动流程：

# 1. 干净跑一遍。
bash scripts/workflows/promoter.sh

# 2. 按稳定顺序对每个输出文件算 sha256，重定向到 baseline 文件。
( cd results/cli/promoter && find . -type f | sort | xargs shasum -a 256 ) \
    > tests/integration/baselines/03_baseline.hashes.txt
```

`01, 02, 04, 05, 06, 07, 08` 同套 —— 把 runner 脚本和上表的 per-pipeline `results_dir` 换一下。

<a id="cn-7"></a>

## 7. 新增 check

1. 在 `tests/integration/` 下新建 `.sh`。
2. 早早写 `set -uo pipefail` 与 `cd "$repo_root"`；不要假设 CWD。
3. 用 `repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)` 解析 repo 路径，不要用 `$script_dir/..` —— 后者只在脚本在 `tests/` 下一级时才对。
4. 每个断言打 PASS / FAIL；任何 FAIL 都退出非 0。
5. 加进本 README 的表，若是不变量 smoke 检查再往主 README §9 Track 3 描述里加一句。
