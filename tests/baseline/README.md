# tests/baseline/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose](#en-1) | [4. Determinism](#en-4) |
| [2. Run](#en-2) | [5. Visual baselines](#en-5) |
| [3. What it captures](#en-3) | [6. Migration history](#en-6) |

<a id="en-1"></a>

## 1. Purpose

You changed something in the C/C++ engines — a refactor, a perf tweak, a bug fix — and you want to know **fast**: did the demo runs still produce exactly the same numbers as before, or did your change leak into the output?

This directory holds the "before" snapshot. `capture.sh` runs the demo indexing and pairing pipelines on tiny inputs from `data/demos/`, hashes every output file with sha256, and writes the whole hash list to `fingerprints.txt`. After your change, re-run and check the diff:

```bash
# Re-capture: hashes every demo output and overwrites fingerprints.txt.
make baseline

# Compare against the fingerprints.txt that's committed — any line that
# changed = a file whose bytes shifted since the last commit.
git diff tests/baseline/fingerprints.txt
```

- **No diff** → your change didn't affect any numbers. Safe to commit.
- **Some files differ** → either you broke something (revert and look), or you intentionally changed an algorithm. In the latter case the new fingerprints replace the old — commit the updated `fingerprints.txt` to bless the new behavior.

A full capture takes ~30 s once the host binaries are built.

<a id="en-2"></a>

## 2. Run

```bash
# Capture a fresh fingerprint set into tests/baseline/fingerprints.txt.
make baseline

# Diff against the version git knows about.
git diff tests/baseline/fingerprints.txt
```

**Needs** — `build/indexing_fimo_fused` and `build/pairing_parallel` (run `make build` once if missing). The demo inputs under `data/demos/` ship with the repo, so no `make fetch-data` required.

**Produces** — overwrites `tests/baseline/fingerprints.txt` (one ~1.7 KB plain-text file). Sections are headered like `## section:foo`; each section lists one sha256 per file produced by that step:

```
# baseline captured: 2026-04-30T07:11:16Z
# host: Darwin 24.6.0 arm64
# git: ac09b73 on main

## section:binaries
build/indexing_fimo_fused    b851f487d0471a58…
build/pairing_parallel       a14286e985542b53…

## section:core_demo_run_indexing_fused
# RUN_OK
c23b4b6b131d5abc…  ./fused/binomial_thresholds.txt
b5a8ee82b9078787…  ./fused/fimohits/CCA1.bin
…
```

**How to read it** — the actual signal is `git diff` against the committed `fingerprints.txt`:

- **No diff** → nothing changed, your edit is bytes-clean.
- **A per-file sha changed** → that one file's contents shifted; open the file and compare to its previous output to see how.
- **`# RUN_OK` flipped to `# RUN_FAIL exit=N`** → the underlying script aborted before producing output; the `# ...` lines below it are the last 20 lines of stderr from the matching log under `results/tests/baseline/{indexing_fused,pairing,env_check,backend_pytest}.log`.
- **A whole section gained or lost lines** → an output file was added or deleted by the workflow.

Safe to re-run any time. Each section is wrapped in a fallback block, so a missing input (no TAIR10 yet, no host binaries built, etc.) degrades to a clearly-marked SKIP instead of aborting mid-capture.

<a id="en-3"></a>

## 3. What it captures

| Section | What it hashes | Source |
|---|---|---|
| `binaries` | `build/indexing_fimo_fused`, `build/pairing_parallel` | host build (`make build`) |
| `core_demo_indexing_existing_outputs` | `results/cli/demo/fimo_official/*` if present | leftover from a previous demo run, optional |
| `core_demo_run_indexing_fused` | output of `apps/cli/scripts/run_indexing.sh -v fused` against `data/demos/promoters/indexing/demo` | runs the script |
| `core_demo_run_pairing` | output of `apps/cli/scripts/run_pairing.sh` against `data/demos/promoters/pairing/demo` | runs the script |
| `analysis_smoke` | tail of `scripts/workflows/cli/00_env_check.sh` (with fallback to legacy `pmet_analysis_pipeline/scripts/00_requirements.sh`) | tool-presence check |
| `backend_pytest` | exit status of `python apps/pmet_backend/test_api.py` (with fallback to legacy `pmet_shiny_app/pmet_backend/test_api.py`) | 5-stage smoke |

The `*_existing_outputs` and the two `legacy/*` fallback paths are holdovers from the pre-monorepo layout; they're guarded with `[ -f ... ]` checks and silently skipped on a fresh clone.

<a id="en-4"></a>

## 4. Determinism

The demo indexer (`indexing_fimo_fused`) and demo pairer (`pairing_parallel`) are designed to produce byte-identical output on every run, given the same input. So **any** diff in the `core_demo_run_indexing_fused` or `core_demo_run_pairing` section means something changed in the code, the build flags, or the input — there's no "flaky test" excuse to hand-wave it away.

<a id="en-5"></a>

## 5. Visual baselines

UI regression now lives in [`apps/pmet_frontend/e2e/`](../../apps/pmet_frontend/e2e/) (Playwright). The eight monorepo-merge-era screenshots that used to live here were removed in favour of automated E2E specs that actually fail when the UI breaks. To capture a fresh visual baseline, see the Playwright [`screenshot()`](https://playwright.dev/docs/test-snapshots) docs and add a spec under `e2e/`.

<a id="en-6"></a>

## 6. Migration history

The original `fingerprints.txt` was captured at commit `123a39b` on the `refactor/monorepo` branch — the moment three previously-separate codebases (`PMET_project`, `pmet_analysis_pipeline`, `pmet_shiny_app`) were merged into this monorepo at tag `v0.1.0-monorepo`. The current `capture.sh` still knows how to find inputs in the pre-merge layout, so the same script works whether you `git checkout` today's main or an old tag — handy for `git bisect` across the merge point.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途](#cn-1) | [4. 确定性](#cn-4) |
| [2. 运行](#cn-2) | [5. 视觉 baseline](#cn-5) |
| [3. 抓什么](#cn-3) | [6. 迁移历史](#cn-6) |

<a id="cn-1"></a>

## 1. 用途

你改了 C/C++ 引擎里的某个东西 —— 重构、性能微调、修 bug —— 你想立刻知道：demo 跑出来的数字跟改之前一字不差吗？还是你的改动悄悄漏进了输出里？

这个目录就是用来抓"改之前"那一份快照的。`capture.sh` 用 `data/demos/` 下的小输入跑 demo 的 indexing 和 pairing，给每个生成的文件算 sha256，全部写到 `fingerprints.txt`。改完后重新跑一次，看看 diff：

```bash
# 重新抓：把所有 demo 输出 hash 一遍，覆盖写 fingerprints.txt。
make baseline

# 跟仓库里 commit 过的 fingerprints.txt 对比 —— 任何变了的行 = 那个
# 文件的字节自上次 commit 以来变了。
git diff tests/baseline/fingerprints.txt
```

- **没 diff** → 你的改动没影响任何数字。可以提交。
- **有文件不一样** → 要么你写错了（revert 排查），要么你有意改了算法。后者只需把更新后的 `fingerprints.txt` 一起 commit，就算认可了新行为。

二进制编好的话，整次 capture 大约 30 秒。

<a id="cn-2"></a>

## 2. 运行

```bash
# 抓一份新的 fingerprint 写到 tests/baseline/fingerprints.txt。
make baseline

# 跟 git 里那一份对比。
git diff tests/baseline/fingerprints.txt
```

**需要** —— `build/indexing_fimo_fused` 和 `build/pairing_parallel`（缺就先 `make build` 一次）。`data/demos/` 下的 demo 输入随仓库一起带着，**不**需要 `make fetch-data`。

**产出** —— 覆盖写 `tests/baseline/fingerprints.txt`（一个 ~1.7 KB 的纯文本文件）。分段以 `## section:foo` 开头；每段列出该步骤产出的每个文件的 sha256：

```
# baseline captured: 2026-04-30T07:11:16Z
# host: Darwin 24.6.0 arm64
# git: ac09b73 on main

## section:binaries
build/indexing_fimo_fused    b851f487d0471a58…
build/pairing_parallel       a14286e985542b53…

## section:core_demo_run_indexing_fused
# RUN_OK
c23b4b6b131d5abc…  ./fused/binomial_thresholds.txt
b5a8ee82b9078787…  ./fused/fimohits/CCA1.bin
…
```

**怎么解读** —— 真正的信号是 `git diff` 对比仓库里 commit 过的 `fingerprints.txt`：

- **没 diff** → 啥都没变，你的改动在字节层面是干净的。
- **某个文件的 sha 变了** → 那个文件的内容有变化；打开它跟上一次输出对比看怎么变的。
- **`# RUN_OK` 翻成 `# RUN_FAIL exit=N`** → 底层脚本在产出之前就 abort 了；下面 `# ...` 那几行是 `results/tests/baseline/{indexing_fused,pairing,env_check,backend_pytest}.log` 对应那份末尾 20 行 stderr。
- **整段多了 / 少了几行** → workflow 多产了 / 少产了某个输出文件。

随时可以重跑。每段都包了 fallback，缺输入（还没下 TAIR10、还没编 host 二进制等）时会清清楚楚标个 SKIP，不会中途 abort。

<a id="cn-3"></a>

## 3. 抓什么

| 段 | 哈希什么 | 来源 |
|---|---|---|
| `binaries` | `build/indexing_fimo_fused`、`build/pairing_parallel` | host build（`make build`） |
| `core_demo_indexing_existing_outputs` | `results/cli/demo/fimo_official/*`（若存在） | 上次 demo 跑剩的，可选 |
| `core_demo_run_indexing_fused` | `apps/cli/scripts/run_indexing.sh -v fused` 跑 `data/demos/promoters/indexing/demo` 的输出 | 当场跑脚本 |
| `core_demo_run_pairing` | `apps/cli/scripts/run_pairing.sh` 跑 `data/demos/promoters/pairing/demo` 的输出 | 当场跑脚本 |
| `analysis_smoke` | `scripts/workflows/cli/00_env_check.sh` 的尾部输出（fallback 到老路径 `pmet_analysis_pipeline/scripts/00_requirements.sh`） | 工具存在性检查 |
| `backend_pytest` | `python apps/pmet_backend/test_api.py` 的退出状态（fallback 到老 `pmet_shiny_app/pmet_backend/test_api.py`） | 5 stage smoke |

`*_existing_outputs` 与两个 `legacy/*` fallback 路径都是 monorepo 之前的遗留；都用 `[ -f ... ]` 包了，全新 clone 上会静默跳过。

<a id="cn-4"></a>

## 4. 确定性

demo 用的索引器（`indexing_fimo_fused`）和 pairer（`pairing_parallel`）按设计同输入每次都给出**字节完全一致**的输出。所以 `core_demo_run_indexing_fused` 或 `core_demo_run_pairing` 段任何 diff 都意味着代码、build flag 或输入有变化 —— 没有"测试不稳定"这种借口能搪塞过去。

<a id="cn-5"></a>

## 5. 视觉 baseline

UI 回归现在归 [`apps/pmet_frontend/e2e/`](../../apps/pmet_frontend/e2e/)（Playwright）。原本这里那 8 张 monorepo 合并期的截图已删 —— 现在用自动 E2E spec 兜底，UI 真坏了能直接 fail。要抓新视觉 baseline 见 Playwright [`screenshot()`](https://playwright.dev/docs/test-snapshots) 文档，在 `e2e/` 下加 spec。

<a id="cn-6"></a>

## 6. 迁移历史

最初那份 `fingerprints.txt` 是在 `refactor/monorepo` 分支的 commit `123a39b` 上抓的 —— 三个原本独立的代码库（`PMET_project`、 `pmet_analysis_pipeline`、`pmet_shiny_app`）在 tag `v0.1.0-monorepo` 处合并的那一刻。现在的 `capture.sh` 仍然知道怎么在合并前的目录布局里找输入，所以同一份脚本在 `git checkout` 今天的 main 或一个老 tag 上都能跑 —— 跨这个合并点 `git bisect` 时很有用。
