# tests/integration/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose & layout](#en-1) | [4. run_with_verify.sh](#en-4) |
| [2. Per-script status](#en-2) | [5. Baseline staleness](#en-5) |
| [3. Quick start](#en-3) | [6. Adding a new check](#en-6) |

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
├── fixtures/                             tiny FASTA/BED used by run_smoke.sh
└── baselines/                            recorded {exit, hashes, stdout, stderr} per pipeline
```

<a id="en-2"></a>

## 2. Per-script status

| Script | Wall time | Needs | Status |
|---|---|---|---|
| `run_smoke.sh` | ~3 s | bedtools, samtools, python3 (TAIR10 optional) | ✅ all 13 checks pass |
| `test_pipeline02_strand_realdata.sh` | ~3 s | TAIR10 (`data/reference/TAIR10.{fasta,gff3}`) | ✅ skips cleanly without TAIR10, passes with it |
| `verify_baseline.sh` | seconds | shasum | ✅ generic — diff any results dir against any hashes file |
| `run_pipeline02_one_combo.sh` | ~1 min | TAIR10, full FIMO + PMET stack | ✅ runs end-to-end (output won't match the stale 02 baseline; see [§5](#en-5)) |
| `run_pipeline08_ic_sweep.sh` | ~30 s × N IC values | a built homotypic index (`results/cli/promoter/01_homotypic/`) | ✅ runs end-to-end |
| `run_with_verify.sh` | varies (per NN) | per-pipeline (see [§4](#en-4)) | ✅ runners invokable; baselines stale (see [§5](#en-5)) |

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

## 4. run_with_verify.sh — pipeline runner with diff

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
bash tests/integration/run_with_verify.sh 03            # promoter
bash tests/integration/run_with_verify.sh 06 mrna       # elements -s longest -e mRNA
bash tests/integration/run_with_verify.sh 08            # pair_only — needs 03's homotypic
```

<a id="en-5"></a>

## 5. Baseline staleness

The `baselines/` directory was captured before the monorepo merge, when the workflow scripts were under `scripts/scripts/0X_*.sh` and their outputs landed in directories like `data/homotypic_promoters/`. Today's workflow scripts produce different paths (`results/cli/promoter/` etc.) and slightly different log lines, so **`verify_baseline.sh` will report many spurious diffs even on a clean monorepo run** until the baselines are regenerated.

The runner scripts themselves (the left half of `run_with_verify.sh`) do work — use the dispatcher to drive an end-to-end run, then ignore the diff step until you can reset baselines:

```bash
# Capture a fresh baseline for one pipeline (manual procedure):
bash scripts/workflows/promoter.sh                                  # produce a clean run
( cd results/cli/promoter && find . -type f | sort | xargs shasum -a 256 ) \
    > tests/integration/baselines/03_baseline.hashes.txt
```

The same pattern works for any of `01, 02, 04, 05, 06, 07, 08` — swap the runner script and the per-pipeline `results_dir` from the dispatch table above.

<a id="en-6"></a>

## 6. Adding a new check

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
| [1. 用途与目录](#cn-1) | [4. run_with_verify.sh](#cn-4) |
| [2. 各脚本状态](#cn-2) | [5. Baseline 已过期](#cn-5) |
| [3. Quick start](#cn-3) | [6. 新增 check](#cn-6) |

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
├── fixtures/                             run_smoke.sh 用的小 FASTA/BED
└── baselines/                            每个 pipeline 录制的 {exit, hashes, stdout, stderr}
```

<a id="cn-2"></a>

## 2. 各脚本状态

| 脚本 | 耗时 | 需要 | 状态 |
|---|---|---|---|
| `run_smoke.sh` | ~3 秒 | bedtools、samtools、python3（TAIR10 可选） | ✅ 13 项检查全过 |
| `test_pipeline02_strand_realdata.sh` | ~3 秒 | TAIR10（`data/reference/TAIR10.{fasta,gff3}`） | ✅ 没 TAIR10 干净跳过，有就过 |
| `verify_baseline.sh` | 秒级 | shasum | ✅ 通用 —— diff 任意 results 目录对任意 hashes 文件 |
| `run_pipeline02_one_combo.sh` | ~1 分钟 | TAIR10、完整 FIMO + PMET 栈 | ✅ 端到端能跑（输出对不上过期的 02 baseline，见 [§5](#cn-5)） |
| `run_pipeline08_ic_sweep.sh` | ~30 秒 × N 个 IC 值 | 已建好的 homotypic 索引（`results/cli/promoter/01_homotypic/`） | ✅ 端到端能跑 |
| `run_with_verify.sh` | 因 NN 而异 | per-pipeline（见 [§4](#cn-4)） | ✅ runner 可调用；baseline 已过期（见 [§5](#cn-5)） |

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

## 4. run_with_verify.sh —— "跑 + diff" pipeline runner

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
bash tests/integration/run_with_verify.sh 03            # promoter
bash tests/integration/run_with_verify.sh 06 mrna       # elements -s longest -e mRNA
bash tests/integration/run_with_verify.sh 08            # pair_only —— 需要 03 的 homotypic
```

<a id="cn-5"></a>

## 5. Baseline 已过期

`baselines/` 是 monorepo 合并前抓的，那时 workflow 脚本在 `scripts/scripts/0X_*.sh`，输出落到 `data/homotypic_promoters/` 那种目录。今天的 workflow 脚本走不同路径（`results/cli/promoter/` 等）和略有不同的 log 行，所以**即便干净的 monorepo 运行，`verify_baseline.sh` 也会报很多假 diff**，直到重抓 baseline 为止。

runner 脚本本身（`run_with_verify.sh` 左半边）能跑——用调度器把端到端跑一遍，然后跳过 diff 步骤即可，等 baseline 重抓后再启用：

```bash
# 单个 pipeline 重抓 baseline 的手动流程：
bash scripts/workflows/promoter.sh                                  # 干净跑一遍
( cd results/cli/promoter && find . -type f | sort | xargs shasum -a 256 ) \
    > tests/integration/baselines/03_baseline.hashes.txt
```

`01, 02, 04, 05, 06, 07, 08` 同套 —— 把 runner 脚本和上表的 per-pipeline `results_dir` 换一下。

<a id="cn-6"></a>

## 6. 新增 check

1. 在 `tests/integration/` 下新建 `.sh`。
2. 早早写 `set -uo pipefail` 与 `cd "$repo_root"`；不要假设 CWD。
3. 用 `repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)` 解析 repo 路径，不要用 `$script_dir/..` —— 后者只在脚本在 `tests/` 下一级时才对。
4. 每个断言打 PASS / FAIL；任何 FAIL 都退出非 0。
5. 加进本 README 的表，若是不变量 smoke 检查再往主 README §9 Track 3 描述里加一句。
