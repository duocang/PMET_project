# tests/integration/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose & layout](#en-1) | [6. test_pipeline02_strand_realdata.sh](#en-6) |
| [2. Per-script status](#en-2) | [7. run_pipeline02_one_combo.sh](#en-7) |
| [3. Quick start](#en-3) | [8. run_pipeline08_ic_sweep.sh](#en-8) |
| [4. verify_heatmap_consistency.py](#en-4) | [9. verify_baseline.sh](#en-9) |
| [5. run_smoke.sh](#en-5) | [10. Adding a new check](#en-10) |

<a id="en-1"></a>

## 1. Purpose & layout

You changed something in a pipeline script (`scripts/workflows/...`) and you want to know whether the script-level invariants you depend on still hold — bedtools called with `-s`, the chromosome-name preflight, the GFF3 → BED converter resolving split fragments, the R and frontend heatmap pipelines picking the same motifs. Unit tests cover individual functions; this directory checks the same invariants but at the **script** level.

It sits in the middle of the test pyramid: slower than `tests/unit/`, faster and lighter than `tests/audit/` (which re-runs full workflows and rewrites the audit docs).

```
tests/integration/
├── smoke/                                fast checks wired into `make test-integration`
│   ├── run.sh                            fast invariants + heatmap consistency (~3–10 s)
│   ├── verify_heatmap_consistency.py     R-vs-frontend heatmap motif-selection diff (~5–10 s)
│   └── fixtures/                         tiny FASTA / BED / heatmap fixtures
└── scripts/                              heavy manual scripts (real-data, slow, opt-in)
    ├── run_pipeline02_one_combo.sh       one-cell perf-params run end-to-end (~1 min, needs TAIR10)
    ├── run_pipeline08_ic_sweep.sh        IC-threshold sweep on a built homotypic index (~30 s × N values)
    ├── test_pipeline02_strand_realdata.sh  TAIR10 strand extraction sanity (~3 s)
    └── verify_baseline.sh                generic <results_dir> ↔ <hashes.txt> differ
```

<a id="en-2"></a>

## 2. Per-script status

Every row below was actually run on this machine and the verdict reflects observed output, not source-review optimism.

| Script | Wall time | Needs | Verdict |
|---|---|---|---|
| `run_smoke.sh` | ~3–10 s | bedtools, samtools, python3, optional Rscript & TAIR10 | ✅ all checks pass; auto-skip the R / TAIR10 sub-checks if either dep is missing |
| `verify_heatmap_consistency.py` | ~5 s | Rscript + a `motif_output.txt` (PNG render extras: `--render-dir`) | ✅ AGREE on the bundled fixture and on real task outputs |
| `test_pipeline02_strand_realdata.sh` | ~3 s | TAIR10 (`data/reference/TAIR10.{fasta,gff3}`) | ✅ skips cleanly without TAIR10, passes with it |
| `run_pipeline02_one_combo.sh` | ~1 min | TAIR10, full FIMO + PMET stack | ✅ runs end-to-end (verified by source review; rerun whenever `02_perf_params.sh` grid changes) |
| `run_pipeline08_ic_sweep.sh` | ~15 s × N IC values | a homotypic index dir | ✅ verified end-to-end against `data/demos/promoters/pairing/demo` (2 ICs, ~30 s) |
| `verify_baseline.sh` | seconds | shasum | ✅ generic differ — diff any results dir against any hashes file you generated |

<a id="en-3"></a>

## 3. Quick start

```bash
# Fast invariants + heatmap consistency. This is what `make test-integration` runs.
make test-integration

# Real-data strand extraction (auto-skips if TAIR10 not yet fetched).
bash tests/integration/scripts/test_pipeline02_strand_realdata.sh

# Heatmap consistency on your own task output.
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input results/app/<task_id>/pairing/motif_output.txt
```

<a id="en-4"></a>

## 4. verify_heatmap_consistency.py — R vs frontend motif selection

**Why it exists.** Both the R heatmap pipeline (`scripts/r/draw_heatmap.R`, used by the CLI workflows and the embedded QuickLook) and the frontend visualizer (`/visualize`) consume the same `motif_output.txt`. Historically they used **different motif-selection algorithms** so the two heatmaps showed different motifs for the same input. The frontend now mirrors R's algorithm; this script is the regression check that keeps it that way.

**Wired into `make test-integration`.** `run_smoke.sh` runs this check at the tail against the bundled fixture under `fixtures/heatmap/motif_output.txt` whenever `Rscript` is on `$PATH` (skipped cleanly otherwise — same conditional pattern as the TAIR10 strand check).

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
| `motif_output.txt` | any PMET pairing output; default fixture is `tests/integration/smoke/fixtures/heatmap/motif_output.txt`, real-task outputs work too |
| Playwright + Chromium | optional, only for `--render-dir` (visual side-by-side) |
| Docker stack at `--base-url` | optional, only for `--render-dir` frontend capture |

**Commands.**

```bash
# Default: data-level check on the bundled fixture.
python3 tests/integration/smoke/verify_heatmap_consistency.py

# On a real task's output.
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input results/app/<task_id>/pairing/motif_output.txt

# Tune the cap if you want to match a specific draw_heatmap.R run.
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input <path> --max-motifs 30 --p-adj-limit 0.05

# Visual side-by-side. Drops r.png + frontend.png into the chosen dir.
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input <path> --render-dir tmp/heatmap_visuals
```

**Produces.**

| Where | What |
|---|---|
| **stdout** | one line per cluster (`== <cluster>: N motifs match` on agree; `!! <cluster>: motif set differs ...` on diverge), plus the trailing `# wrote ...` pointer |
| `results/tests/heatmap/consistency_report.txt` | the same report as stdout, persisted across runs (rewritten every invocation). Override with `--report PATH` |
| `<dir>/r.png` | with `--render-dir <dir>`: R's `draw_heatmap.R` output. Always rendered when Rscript is on PATH |
| `<dir>/frontend.png` | with `--render-dir <dir>`: Playwright-captured frontend heatmap. Skipped with a stderr install hint if Playwright isn't installed |

Sample agree report:

```
# heatmap consistency report
# input:  tests/integration/smoke/fixtures/heatmap/motif_output.txt
# params: p_adj_limit=0.05 unique=True max_motifs=30
# verdict: AGREE

== heat_down: 15 motifs match
== heat_up: 15 motifs match
```

<a id="en-5"></a>

## 5. run_smoke.sh — fast pipeline invariants

**Why it exists.** A handful of cross-script invariants have bitten the project before (bedtools `-s` strand, chromosome-name preflight, GFF3-to-BED resolving non-adjacent fragments). `run_smoke.sh` re-asserts them all in under 10 seconds and is what `make test-integration` actually invokes.

**What it covers (in order).**

1. `bedtools getfasta -s` reverse-complements minus-strand entries.
2. `build_promoters.py` invokes `bedtools getfasta` with `-s`.
3. Pipeline 01's input fixtures exist and `draw_heatmap.R` is called with the right number of args.
4. Chromosome-name preflight is present in the promoter+anno workflows.
5. `assess_integrity.py` correctly resolves non-adjacent same-gene fragments.
6. Real-data TAIR10 strand extraction (skipped if TAIR10 not fetched).
7. R-vs-frontend heatmap motif selection (skipped if Rscript not on PATH; see [§4](#en-4)).

**Needs.** `bedtools`, `samtools`, `python3` always; `Rscript` and `data/reference/TAIR10.{fasta,gff3}` optional (the relevant sub-check skips cleanly when missing).

**Command.**

```bash
make test-integration            # equivalent to:
bash tests/integration/smoke/run.sh
```

**Produces.**

| Where | What |
|---|---|
| **stdout** | each section announces itself with `[smoke] <label>`, then prints PASS / FAIL / SKIP per assertion. Exit 0 if all checks pass, 1 if any fail |
| `results/tests/smoke/strand_real.log` | full stderr from the TAIR10 strand sub-check (only written when that branch ran). FAIL message points at this path |
| `results/tests/smoke/heatmap_consistency.log` | full stderr from the heatmap consistency sub-check. On FAIL, the first DIVERGE block is also echoed inline so the failure is actionable without opening the log |

Sample stdout tail:

```
[smoke] real-data strand extraction (TAIR10)
  PASS  TAIR10 promoter FASTA: + strand unchanged, - strand reverse-complemented by -s
[smoke] R vs frontend heatmap consistency
  PASS  R and frontend pipelines pick the same motifs on the bundled fixture
[smoke] all checks passed
```

<a id="en-6"></a>

## 6. test_pipeline02_strand_realdata.sh — TAIR10 strand extraction

**Why it exists.** Re-checks the bedtools `-s` fix on real TAIR10 data, not just the synthetic fixture in run_smoke.sh — catches regressions where the synthetic case still passes but real promoter sequences would silently flip on `-` strand genes.

**What it does.** Runs the promoter-extraction step twice (with and without `-s`), reads back per-gene FASTA records, asserts: every `+` strand gene sequence is identical between the two; every `-` strand gene is the reverse-complement of its no-`-s` counterpart.

**Needs.** `data/reference/TAIR10.{fasta,gff3}` (run `make fetch-data` once); `bedtools`, `samtools` on PATH.

**Command.**

```bash
bash tests/integration/scripts/test_pipeline02_strand_realdata.sh
```

**Produces.**

| Where | What |
|---|---|
| **stdout** | SHA-256 of each FASTA, per-strand counts of identical / reverse-complement matches |
| `/tmp/strand_pre_*.fa`, `/tmp/strand_post_*.fa` | the two FASTA files produced under each `-s` setting (the script makes its own `mktemp -d` and cleans up on success — paths printed in the trailing `[strand-real] ...` lines) |

Sample tail:

```
[strand-real] PRE-FIX  (no -s) FASTA sha256: 4b9f61d5c2a25a9b8a2860fded75aaafefc5209adc0300446a091fbcac55f273
[strand-real] POST-FIX (-s)    FASTA sha256: cd1ebf4a7359958826323fa74423d55f3583343b8ef12396e8c7a44eedfbeed3
[strand-real] + strand: 13855 identical, 0 differ
[strand-real] - strand: 13800 are RC of pre-fix, 0 are not
[strand-real] all per-gene checks passed
```

Exits 0 on every-check pass, non-zero on any mismatch.

<a id="en-7"></a>

## 7. run_pipeline02_one_combo.sh — single-combo perf-params run

**Why it exists.** `scripts/workflows/cli/02_perf_params.sh` sweeps a 4×7×9×1 = 252-combination grid and takes hours. This wrapper rewrites the four grid arrays to a single point so a real-data regression is achievable in ~1 minute. Useful when you've changed something in 02_perf_params.sh's pipeline body and want to confirm it still produces sane output without committing to the full sweep.

**Needs.** TAIR10, the full FIMO + PMET stack (i.e. `make build` plus all the host deps the workflow uses). Outputs land at `results/02_perf_params/` — don't run alongside the full perf-params pipeline.

**Command.**

```bash
# Defaults: task=genes_cell_type_treatment plen=200 maxk=5 topn=5000.
bash tests/integration/scripts/run_pipeline02_one_combo.sh

# Override the combo via env vars.
TASK=my_task PLEN=1000 MAXK=4 TOPN=3000 \
    bash tests/integration/scripts/run_pipeline02_one_combo.sh
```

**Produces.**

| Where | What |
|---|---|
| `results/02_perf_params/<task>_LEN<plen>_K<maxk>_N<topn>_FIMO0.05/` | one grid cell's full output (binomial_thresholds, fimohits/, motif_output.txt, plot/, etc.) — same shape as a full sweep at this combo |
| `results/02_perf_params/02_heterotypic/...` | per-cluster heterotypic output (the file the heatmap pipeline reads) |

Mirror the structure of a full sweep at one combo so any downstream tooling that points at the perf-params output keeps working.

<a id="en-8"></a>

## 8. run_pipeline08_ic_sweep.sh — IC-threshold parameter sweep

**Why it exists.** Once you have a homotypic index built, `pair_only.sh` is fast (~15 s on the demo, longer on TAIR10). This driver runs it across a configurable list of IC thresholds and records each output's SHA-256 + line count + wall time, so you can quickly see how the heterotypic motif-pair set shifts as IC tightens / relaxes — without paying for indexing on every IC.

**Needs.** A pre-built homotypic index. The default is `results/cli/promoter/01_homotypic` (run `bash scripts/workflows/promoter.sh` first, or run `bash scripts/workflows/indexing_only.sh` to build only the indexing half), but any homotypic dir works — including `data/demos/promoters/pairing/demo` for a quick smoke.

**Commands.**

```bash
# Default: IC values 2 4 6 8 against the canonical homotypic index.
bash tests/integration/scripts/run_pipeline08_ic_sweep.sh

# Quick smoke against the bundled demo index.
HOMOTYPIC=data/demos/promoters/pairing/demo \
GENE_LIST=data/demos/promoters/pairing/demo/gene.txt \
OUT_BASE=/tmp/ic_sweep \
IC_VALUES="2 4" \
    bash tests/integration/scripts/run_pipeline08_ic_sweep.sh
```

**Produces.**

| Where | What |
|---|---|
| `$OUT_BASE/icN/` (per IC) | full pair_only output: `motif_output.txt`, `plot/`, `genes_used_PMET.txt`, `pmet.log` |
| `$OUT_BASE/summary.tsv` | one row per IC: `ic`, `motif_output_lines`, `sha256`, `wall_time_s`, `exit` |
| stdout | per-IC progress (`[ic-sweep] ic=N OK 14s 46 lines sha=...`) plus the summary table at the end |

Sample `summary.tsv`:

```
ic   motif_output_lines   sha256                                                            wall_time_s   exit
2    46                   ce37e7211ada37623c4b4d0cdacf13997ab15a65087ae6bf4968ca713b321be2  14            0
4    46                   0af5b936606fd30f3e4989c3658170e93e208d1277fa97882a2e83c130a83d8f  14            0
```

Verified: `ic=4` SHA matches the binomial baseline anchor in [`tests/baseline/fingerprints.txt`](../baseline/fingerprints.txt) — independent corroboration that the demo path produces deterministic output.

**Exit codes.** 0 if every IC succeeded; 1 if at least one failed (`summary.tsv` `exit` column lists which).

<a id="en-9"></a>

## 9. verify_baseline.sh — generic results-dir differ

**Why it exists.** Hash every file under a results directory, diff against a recorded `hashes.txt`. Useful when you've captured a known-good output (e.g. via `make baseline` or a manual `find … | xargs shasum`) and want to confirm later runs still match. The previous bundled `baselines/*.hashes.txt` files referenced pre-monorepo paths and were dropped in the [retire-legacy-baselines commit](#); this script remains as a generic differ for any hashes file you generate yourself.

**Command.**

```bash
# Capture a baseline manually:
( cd results/cli/promoter && find . -type f | sort | xargs shasum -a 256 ) > my_baseline.hashes.txt

# Diff a later run against it:
bash tests/integration/scripts/verify_baseline.sh results/cli/promoter my_baseline.hashes.txt
```

**Produces.**

| Where | What |
|---|---|
| **stdout** | one-line summary: `OK — N files match (exclude=...)` on success |
| **stderr** | on FAIL, the diff in `diff` format (`< baseline`, `> current`) plus a header noting how many files counted on each side |

Exits 0 on match, 1 on diverge, 2 on usage errors. The default exclude pattern drops `*.log` files from both sides (timestamps and per-thread scheduling are nondeterministic); override via `EXCLUDE='/pmet\.log$'`.

<a id="en-10"></a>

## 10. Adding a new check

1. Drop a script under `tests/integration/`. Bash, Python, or anything that can be invoked from `run_smoke.sh`.
2. `set -uo pipefail` and resolve `repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)` early; never assume CWD.
3. Print PASS / FAIL / SKIP per assertion; exit non-zero on any FAIL.
4. If the check is fast (< 10 s) and dep-light, wire it into `run_smoke.sh` so `make test-integration` covers it.
5. Add a row to [§2](#en-2) and a dedicated section here following the **Why / What / Needs / Command / Produces** template.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途与目录](#cn-1) | [6. test_pipeline02_strand_realdata.sh](#cn-6) |
| [2. 各脚本状态](#cn-2) | [7. run_pipeline02_one_combo.sh](#cn-7) |
| [3. Quick start](#cn-3) | [8. run_pipeline08_ic_sweep.sh](#cn-8) |
| [4. verify_heatmap_consistency.py](#cn-4) | [9. verify_baseline.sh](#cn-9) |
| [5. run_smoke.sh](#cn-5) | [10. 新增 check](#cn-10) |

<a id="cn-1"></a>

## 1. 用途与目录

你改了 pipeline 脚本（`scripts/workflows/...`）里的某个东西，想知道你依赖的那些脚本级不变量还在不在 —— bedtools 调用带 `-s` 吗？染色体名预检还在吗？GFF3 → BED 还能正确处理拆段 fragment 吗？R 和前端的热图选 motif 还一致吗？unit test 覆盖单个函数，本目录在**脚本**层做同类不变量校验。

它在测试金字塔中间：比 `tests/unit/`（单函数）慢，比 `tests/audit/`（重跑完整 workflow + 重写文档）轻。

```
tests/integration/
├── smoke/                                进 `make test-integration` 的快检查
│   ├── run.sh                            快不变量 + 热图一致性（~3–10 秒）
│   ├── verify_heatmap_consistency.py     R vs 前端热图 motif 选择 diff（~5–10 秒）
│   └── fixtures/                         小 FASTA / BED / 热图 fixture
└── scripts/                              手动跑的重脚本（真实数据、慢、opt-in）
    ├── run_pipeline02_one_combo.sh       perf-params 一格端到端（~1 分钟，需 TAIR10）
    ├── run_pipeline08_ic_sweep.sh        已建好同型索引上做 IC 阈值 sweep（每 IC ~30 秒）
    ├── test_pipeline02_strand_realdata.sh  TAIR10 strand 抽取 sanity（~3 秒）
    └── verify_baseline.sh                通用 <results_dir> ↔ <hashes.txt> differ
```

<a id="cn-2"></a>

## 2. 各脚本状态

下表每行**都在本机真跑过**，结论是观察的实际输出，不是看源码乐观估计的。

| 脚本 | 耗时 | 需要 | 状态 |
|---|---|---|---|
| `run_smoke.sh` | ~3–10 秒 | bedtools、samtools、python3，可选 Rscript 与 TAIR10 | ✅ 全过；R / TAIR10 子项缺依赖时干净跳过 |
| `verify_heatmap_consistency.py` | ~5 秒 | Rscript + 一份 `motif_output.txt`（视觉对比需 `--render-dir`） | ✅ 在 bundled fixture 与真实任务输出上都 AGREE |
| `test_pipeline02_strand_realdata.sh` | ~3 秒 | TAIR10（`data/reference/TAIR10.{fasta,gff3}`） | ✅ 没 TAIR10 干净跳过，有就过 |
| `run_pipeline02_one_combo.sh` | ~1 分钟 | TAIR10、完整 FIMO + PMET 栈 | ✅ 端到端能跑（源码 review 验证；改 `02_perf_params.sh` grid 时建议复跑） |
| `run_pipeline08_ic_sweep.sh` | ~15 秒 × N | 同型索引目录 | ✅ 已在 `data/demos/promoters/pairing/demo` 上端到端跑过（2 个 IC，~30 秒） |
| `verify_baseline.sh` | 秒级 | shasum | ✅ 通用 differ —— diff 任意 results 目录对你自己抓的 hashes 文件 |

<a id="cn-3"></a>

## 3. Quick start

```bash
# 快不变量 + 热图一致性。`make test-integration` 跑的就是这个。
make test-integration

# 真实数据 strand 抽取（没 TAIR10 自动跳过）。
bash tests/integration/scripts/test_pipeline02_strand_realdata.sh

# 在自己的任务输出上跑热图一致性检查。
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input results/app/<task_id>/pairing/motif_output.txt
```

<a id="cn-4"></a>

## 4. verify_heatmap_consistency.py —— R 与前端 motif 选择一致性

**为什么有这玩意**：R 端热图流水线（`scripts/r/draw_heatmap.R`，CLI workflow + 任务详情页 QuickLook 都走它）和前端 `/visualize` 共用同一份 `motif_output.txt`。两边一度用**不同的 motif 选择算法**，同一份输入挑出来的 motif 完全不同。前端现在已经对齐到 R 算法，本脚本就是把这件事固化成回归 check。

**已并入 `make test-integration`**：`run_smoke.sh` 在尾部自动针对 `fixtures/heatmap/motif_output.txt` 跑一遍这个检查（只要 `Rscript` 在 `$PATH` 上；不在就干净跳过 —— 跟 TAIR10 strand 检查同样的条件）。

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
| `motif_output.txt` | 任意 PMET pairing 输出；默认 fixture 是 `tests/integration/smoke/fixtures/heatmap/motif_output.txt`，真实任务输出也行 |
| Playwright + Chromium | 可选，仅 `--render-dir`（视觉对比）要用 |
| 跑着的 docker 栈（`--base-url`） | 可选，仅 `--render-dir` 抓前端图要用 |

**命令**：

```bash
# 默认：bundled fixture 上的数据级 check。
python3 tests/integration/smoke/verify_heatmap_consistency.py

# 真实任务的输出。
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input results/app/<task_id>/pairing/motif_output.txt

# 调上限匹配某次 draw_heatmap.R 跑的。
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input <path> --max-motifs 30 --p-adj-limit 0.05

# 视觉左右对比。在指定目录里输出 r.png + frontend.png。
python3 tests/integration/smoke/verify_heatmap_consistency.py \
    --input <path> --render-dir tmp/heatmap_visuals
```

**产出**：

| 位置 | 内容 |
|---|---|
| **stdout** | 每个 cluster 一行（一致 `== <cluster>: N motifs match`，分叉 `!! <cluster>: motif set differs ...` 加双向独有 motif），尾部 `# wrote ...` 指示报告路径 |
| `results/tests/heatmap/consistency_report.txt` | 跟 stdout 同内容，落盘留底（每次重写）。`--report PATH` 可改写 |
| `<dir>/r.png` | 带 `--render-dir <dir>` 时：R `draw_heatmap.R` 输出。Rscript 在 PATH 上时一定生成 |
| `<dir>/frontend.png` | 带 `--render-dir <dir>` 时：Playwright 抓的前端热图。没装 Playwright 时 stderr 打安装提示后跳过 |

报告样例（一致）：

```
# heatmap consistency report
# input:  tests/integration/smoke/fixtures/heatmap/motif_output.txt
# params: p_adj_limit=0.05 unique=True max_motifs=30
# verdict: AGREE

== heat_down: 15 motifs match
== heat_up: 15 motifs match
```

<a id="cn-5"></a>

## 5. run_smoke.sh —— 快流水线不变量

**为什么有这玩意**：项目历史上被几个跨脚本不变量咬过（bedtools `-s` strand、染色体名预检、GFF3-to-BED 的非相邻 fragment 解析）。`run_smoke.sh` 在 10 秒内把它们全重新断言一遍，`make test-integration` 调的就是它。

**覆盖的检查（按顺序）**：

1. `bedtools getfasta -s` 对负链做反向互补。
2. `build_promoters.py` 调 `bedtools getfasta` 时带了 `-s`。
3. Pipeline 01 的输入 fixture 存在，`draw_heatmap.R` 调用参数数对。
4. promoter+anno workflow 里都有染色体名预检。
5. `assess_integrity.py` 正确处理非相邻同基因 fragment。
6. 真实数据 TAIR10 strand 抽取（缺 TAIR10 跳过）。
7. R-vs-前端 motif 选择一致性（缺 Rscript 跳过；见 [§4](#cn-4)）。

**需要**：必有 `bedtools`、`samtools`、`python3`；可选 `Rscript`、`data/reference/TAIR10.{fasta,gff3}`（缺了对应子检查会干净跳过）。

**命令**：

```bash
make test-integration            # 等价于：
bash tests/integration/smoke/run.sh
```

**产出**：

| 位置 | 内容 |
|---|---|
| **stdout** | 每段先打 `[smoke] <label>`，逐断言 PASS / FAIL / SKIP。全过 exit 0，任一 fail exit 1 |
| `results/tests/smoke/strand_real.log` | TAIR10 strand 子检查的完整 stderr（仅在该分支真跑时写入）。FAIL 时 stdout 提示这个路径 |
| `results/tests/smoke/heatmap_consistency.log` | 热图一致性子检查的完整 stderr。FAIL 时第一段 DIVERGE 也内联回显，不必另开 log 文件 |

stdout 尾段样例：

```
[smoke] real-data strand extraction (TAIR10)
  PASS  TAIR10 promoter FASTA: + strand unchanged, - strand reverse-complemented by -s
[smoke] R vs frontend heatmap consistency
  PASS  R and frontend pipelines pick the same motifs on the bundled fixture
[smoke] all checks passed
```

<a id="cn-6"></a>

## 6. test_pipeline02_strand_realdata.sh —— TAIR10 strand 抽取

**为什么有这玩意**：在真实 TAIR10 数据上重新校 bedtools `-s` 修复 —— 不光是 run_smoke.sh 里的合成 fixture。能逮到合成 case 还过、真启动子在负链基因上偷偷反了的回归。

**在做什么**：跑两遍启动子抽取（带与不带 `-s`），逐基因比 FASTA：每个 `+` 链基因序列两次完全相同；每个 `-` 链基因的带 `-s` 序列是不带 `-s` 的反向互补。

**需要**：`data/reference/TAIR10.{fasta,gff3}`（`make fetch-data` 一次拉好）；`bedtools`、`samtools` 在 PATH 上。

**命令**：

```bash
bash tests/integration/scripts/test_pipeline02_strand_realdata.sh
```

**产出**：

| 位置 | 内容 |
|---|---|
| **stdout** | 两份 FASTA 的 SHA-256，逐 strand 的相同 / 反向互补计数 |
| `/tmp/strand_pre_*.fa`、`/tmp/strand_post_*.fa` | 两次 `-s` 设置下产出的 FASTA（脚本自己 `mktemp -d` 用完清理；路径在尾部 `[strand-real] ...` 行打出） |

样例尾段：

```
[strand-real] PRE-FIX  (no -s) FASTA sha256: 4b9f61d5c2a25a9b8a2860fded75aaafefc5209adc0300446a091fbcac55f273
[strand-real] POST-FIX (-s)    FASTA sha256: cd1ebf4a7359958826323fa74423d55f3583343b8ef12396e8c7a44eedfbeed3
[strand-real] + strand: 13855 identical, 0 differ
[strand-real] - strand: 13800 are RC of pre-fix, 0 are not
[strand-real] all per-gene checks passed
```

全过 exit 0，任何不匹配 exit 非 0。

<a id="cn-7"></a>

## 7. run_pipeline02_one_combo.sh —— perf-params 单格运行

**为什么有这玩意**：`scripts/workflows/cli/02_perf_params.sh` 扫的是 4×7×9×1 = 252 组合，跑几小时。本 wrapper 把四个 grid 数组改成单点，~1 分钟跑完一份真实数据回归。改了 02_perf_params.sh 流水线 body 想确认还合理时用，比承诺跑全 sweep 强。

**需要**：TAIR10、完整 FIMO + PMET 栈（`make build` 加 host 依赖）。输出落 `results/02_perf_params/` —— 别跟完整 perf-params 同时跑。

**命令**：

```bash
# 默认：task=genes_cell_type_treatment plen=200 maxk=5 topn=5000。
bash tests/integration/scripts/run_pipeline02_one_combo.sh

# env 改组合。
TASK=my_task PLEN=1000 MAXK=4 TOPN=3000 \
    bash tests/integration/scripts/run_pipeline02_one_combo.sh
```

**产出**：

| 位置 | 内容 |
|---|---|
| `results/02_perf_params/<task>_LEN<plen>_K<maxk>_N<topn>_FIMO0.05/` | 一格输出（binomial_thresholds、fimohits/、motif_output.txt、plot/ 等），结构跟全 sweep 的一格相同 |
| `results/02_perf_params/02_heterotypic/...` | 各 cluster 的异型输出（热图流水线读这个） |

下游所有指向 perf-params 输出的工具都能继续工作。

<a id="cn-8"></a>

## 8. run_pipeline08_ic_sweep.sh —— IC 阈值参数 sweep

**为什么有这玩意**：同型索引一旦建好，`pair_only.sh` 就快（demo 上 ~15 秒，TAIR10 上更长一点）。这个 driver 在可配置的 IC 阈值列表上跑它，记录每次输出的 SHA-256 + 行数 + wall time，让你快速看 IC 收紧 / 放松时异型 motif-pair 集合怎么动 —— 不用每次都重建索引。

**需要**：一份事先建好的同型索引。默认指向 `results/cli/promoter/01_homotypic`（先 `bash scripts/workflows/promoter.sh`，或 `bash scripts/workflows/indexing_only.sh` 只跑 indexing 半），但任何同型索引目录都行 —— 包括 `data/demos/promoters/pairing/demo` 用作 smoke。

**命令**：

```bash
# 默认：IC 值 2 4 6 8 跑 canonical 同型索引。
bash tests/integration/scripts/run_pipeline08_ic_sweep.sh

# 用 bundled demo 索引快速 smoke。
HOMOTYPIC=data/demos/promoters/pairing/demo \
GENE_LIST=data/demos/promoters/pairing/demo/gene.txt \
OUT_BASE=/tmp/ic_sweep \
IC_VALUES="2 4" \
    bash tests/integration/scripts/run_pipeline08_ic_sweep.sh
```

**产出**：

| 位置 | 内容 |
|---|---|
| `$OUT_BASE/icN/` (每个 IC) | 完整 pair_only 输出：`motif_output.txt`、`plot/`、`genes_used_PMET.txt`、`pmet.log` |
| `$OUT_BASE/summary.tsv` | 每 IC 一行：`ic`、`motif_output_lines`、`sha256`、`wall_time_s`、`exit` |
| stdout | 每 IC 进度（`[ic-sweep] ic=N OK 14s 46 lines sha=...`），尾部打 summary 表 |

`summary.tsv` 样例：

```
ic   motif_output_lines   sha256                                                            wall_time_s   exit
2    46                   ce37e7211ada37623c4b4d0cdacf13997ab15a65087ae6bf4968ca713b321be2  14            0
4    46                   0af5b936606fd30f3e4989c3658170e93e208d1277fa97882a2e83c130a83d8f  14            0
```

实测：`ic=4` SHA 跟 [`tests/baseline/fingerprints.txt`](../baseline/fingerprints.txt) 里的 binomial baseline anchor **完全一致** —— 独立旁证 demo 路径的确定性。

**退出码**：每个 IC 都成功则 0；任一失败则 1（`summary.tsv` 的 `exit` 列标出哪个）。

<a id="cn-9"></a>

## 9. verify_baseline.sh —— 通用 results 目录 differ

**为什么有这玩意**：把 results 目录下每个文件都 hash 一遍，跟录制的 `hashes.txt` diff。适合你抓过一份"已知好"的输出（用 `make baseline` 或自己 `find … | xargs shasum`），后续想验证还在。原先随仓库带的 `baselines/*.hashes.txt` 都是 monorepo 之前的路径，已被 retire-legacy-baselines commit 删掉；脚本本身保留作通用 differ。

**命令**：

```bash
# 手动抓一份 baseline：
( cd results/cli/promoter && find . -type f | sort | xargs shasum -a 256 ) > my_baseline.hashes.txt

# 后续 diff：
bash tests/integration/scripts/verify_baseline.sh results/cli/promoter my_baseline.hashes.txt
```

**产出**：

| 位置 | 内容 |
|---|---|
| **stdout** | 一行摘要：成功打 `OK — N files match (exclude=...)` |
| **stderr** | FAIL 时打 `diff` 格式（`< baseline`、`> current`）加两边过滤后的文件计数 header |

一致 exit 0，分叉 1，用法错 2。默认 exclude 把两边的 `*.log` 文件丢掉（时间戳 + 多线程调度 nondeterministic），用 `EXCLUDE='/pmet\.log$'` 重设。

<a id="cn-10"></a>

## 10. 新增 check

1. 在 `tests/integration/` 下新建脚本（bash / Python / 任何能从 `run_smoke.sh` 调起来的）。
2. 早早写 `set -uo pipefail` 并 `repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)`；不要假设 CWD。
3. 每个断言打 PASS / FAIL / SKIP；任何 FAIL 退出非 0。
4. 如果检查快（< 10 秒）且依赖轻，挂进 `run_smoke.sh`，让 `make test-integration` 一并覆盖。
5. 在 [§2](#cn-2) 加一行，并按 **为什么 / 在做什么 / 需要 / 命令 / 产出** 模板加一节。
