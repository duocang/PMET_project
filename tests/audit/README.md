# tests/audit/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose & layout](#en-1) | [5. Anchors and determinism](#en-5) |
| [2. How a single audit works](#en-2) | [6. Cross-file invariants](#en-6) |
| [3. Running](#en-3) | [7. Adding a workflow](#en-7) |
| [4. Why not pytest](#en-4) | [8. What's NOT audited here](#en-8) |

<a id="en-1"></a>

## 1. Purpose & layout

For each of the four workflow scripts there's a long markdown doc at [`docs/workflows/`](../../docs/workflows/) explaining what it does and showing the actual numbers (file hashes, row counts, sizes, PASS/FAIL on every check) from a canonical run. Those numbers are not typed in by hand — they would rot the moment anyone touched a script. They're refreshed by **actually running each workflow** here and pasting the captured values into a markdown template.

That's what this directory is. The point: as long as `make test-audit` keeps passing, the docs at `docs/workflows/*.md` are still telling the truth about the code.

```
tests/audit/
├── generate.py           driver: python3 tests/audit/generate.py [<name> ...]
├── lib.py                shared helpers (sha, run, render check table, …)
├── workflows/            one spec per workflow
│   ├── pair_only.py
│   ├── intervals.py
│   ├── promoter.py
│   └── elements.py
├── templates/            one markdown template per workflow
│   ├── pair_only.md      (uses <<PLACEHOLDER>> slots that the spec fills in)
│   ├── intervals.md
│   ├── promoter.md
│   └── elements.md
└── runs/                 each spec runs into runs/<name>/ (gitignored)
```

Output lands at `docs/workflows/<name>.md`, which IS committed.

<a id="en-2"></a>

## 2. How a single audit works

Each spec under `workflows/<name>.py` exports two functions:

```python
def run(repo_root: Path, runs_dir: Path) -> dict:
    """Execute the workflow against canonical inputs.
    Return a dict whose keys feed BOTH the verification checks and
    the template <<PLACEHOLDER>> substitutions."""

def checks(data: dict) -> list[Check]:
    """Render the verification table from the run dict."""
```

The driver:

1. Imports `workflows.<name>`, calls `spec.run()`. The workflow executes in a clean `runs/<name>/` subdir.
2. Calls `spec.checks(data)`. Each check produces a `(name, expected, actual, verdict)` row — verdicts are `PASS`, `FAIL`, or `WARN`.
3. Reads `templates/<name>.md`, substitutes every `<<KEY>>` placeholder with the corresponding `data[key]`. Two synthetic placeholders are always available: `<<CHECK_TABLE>>` (the rendered markdown table) and `<<OVERALL_VERDICT>>` (the one-line summary).
4. Writes the rendered markdown to `docs/workflows/<name>.md`.

<a id="en-3"></a>

## 3. Running

```bash
# Run all four workflow audits and rewrite docs/workflows/*.md  (~7 min total)
make test-audit

# Or scope to one workflow (faster, useful while iterating)
python3 tests/audit/generate.py promoter

# Or run any subset by name (in order — the driver dispatches each)
python3 tests/audit/generate.py promoter intervals
```

**Needs** — host binaries (`make build`), Python 3 with the standard library (no extra `pip install`), and the inputs that each workflow expects: pair_only and intervals run on demos under `data/demos/`, promoter and elements run on TAIR10 + Franco-Zorrilla (`make fetch-data` → fetches TAIR10; the motif library is in-repo under `data/motifs/`).

**Produces**

- **Overwrites** `docs/workflows/<name>.md` for each workflow you ran. These are committed; `git diff docs/workflows/` is the signal.
- Drops working files into `tests/audit/runs/<name>/` (gitignored).
- Stdout: per-check verdicts and a final OVERALL line per workflow.

**How to read it** — start with the terminal output, then look at the rendered docs:

```
[audit] promoter
  PASS  motif_output.txt deterministic vs anchor (sha256 starts 4b24906abfe55e)
  PASS  binomial_thresholds.txt motifs == IC.txt motifs (n=110)
  PASS  binomial_thresholds.txt motifs == fimohits/ basenames
  PASS  IC.txt motifs == fimohits/ basenames
  …
[audit] promoter OVERALL: PASS (12 / 12)
```

- **OVERALL: PASS** → doc is fresh and faithful; commit `docs/workflows/<name>.md`.
- **OVERALL: WARN** → some non-blocking discrepancy (e.g. an unblessed elements anchor); inspect the WARN row, copy the captured sha into the spec's `TASK_ANCHORS` if intentional.
- **OVERALL: FAIL** → a workflow output drifted from its anchor or a cross-file invariant broke. Either revert the workflow change or update the anchor in `tests/audit/workflows/<name>.py` to bless the new behavior.

The rendered `docs/workflows/<name>.md` shows the same verdict table inline, plus the prose narrative. `git diff` it after the run to see what changed in the audit's view.

Wall time: pair_only ~15 s, intervals ~16 s, promoter ~2 min, elements ~5 min.

<a id="en-4"></a>

## 4. Why not pytest

The audit's purpose is **a human-readable, reviewable narrative** of each workflow — purpose, biology, design intuition, observed results — not a one-shot pass/fail signal. pytest would conflate the verification checks with what's really a documentation generator. The workflow audit and the regression baseline (`tests/baseline/`) live side-by-side: the baseline is the machine-readable fingerprint set, the audit is the prose explanation of what those fingerprints encode.

<a id="en-5"></a>

## 5. Anchors and determinism

Some checks (`motif_output.txt deterministic vs anchor`) compare an actual SHA-256 against a hard-coded "anchor" string captured on this machine. These are **regression sentinels**: if the workflow's implementation drifts, the SHA changes and the check FAILs. To bless a new SHA after an intentional change, edit the anchor in the spec.

The anchors currently committed:

| workflow | anchor file | sha (first 16) |
|---|---|---|
| pair_only | `data/demos/promoters/pairing/demo` → `motif_output.txt` | `0af5b936606fd3` |
| intervals | `data/demos/intervals` → `motif_output.txt` | `4858412a091983` |
| promoter | TAIR10 + Franco-Zorrilla → `motif_output.txt` | `4b24906abfe55e` |
| elements | per-task `motif_output.txt` (one anchor per `data/genes/*.txt`) | see `TASK_ANCHORS` in `workflows/elements.py` |

`elements` carries one anchor per gene-task; tasks present in the dict with a `None` value are "known but not yet blessed" — the first audit run after this commit captures the real sha and emits a WARN with the captured value, which a reviewer then pastes into `TASK_ANCHORS`. New tasks (gene lists added later) appear as a separate WARN until added to the dict.

(An older version of this README cited "C-engine non-determinism" as the reason for omitting elements anchors. That justification was stale — `elements.sh` now uses `index_fimo_fused`, which is deterministic; the C-indexer caveat in `tests/baseline/README.md` applies to a different workflow.)

<a id="en-6"></a>

## 6. Cross-file invariants (independent of the script's own validator)

Three of the four workflows (promoter, intervals, elements) call `scripts/python/check_homotypic_contract.py` themselves at the end of indexing. The audit ALSO runs an in-process equivalent — see `lib.contract_invariant_checks(index_dir)` — so a future change that skips or weakens the script-side validator still surfaces as audit FAIL rows. The three checks emitted:

  - binomial_thresholds.txt motifs == IC.txt motifs
  - binomial_thresholds.txt motifs == fimohits/ basenames
  - IC.txt motifs == fimohits/ basenames

For pair_only the input index is `data/demos/promoters/pairing/demo`, which intentionally ships only 6 fimohits files for ~110 binomial threshold rows. The same three checks run there but at WARN severity (a real mismatch you should know about, not a regression you should fix).

<a id="en-7"></a>

## 7. Adding a workflow

1. Create `tests/audit/workflows/<name>.py` with `run()` and `checks()`.
2. Create `tests/audit/templates/<name>.md` with `<<PLACEHOLDER>>` slots for everything `run()` returns. Always include `<<CHECK_TABLE>>` and `<<OVERALL_VERDICT>>`.
3. Add `<name>` to `ALL_WORKFLOWS` in `generate.py`.
4. Run `python3 tests/audit/generate.py <name>` and verify the output markdown reads cleanly + every `<<UNRESOLVED:KEY>>` is gone.

<a id="en-8"></a>

## 8. What's NOT audited here

- `scripts/workflows/cli/05_promoter_gap.sh` and the perf benchmarks (`01_perf_cpu`, `02_perf_params`) — these are research/perf scripts with one or two known callers; adding them to the audit is mechanical but low-priority.
- `apps/cli/scripts/*` (the lower-level `run_indexing.sh` / `run_pairing.sh` etc) — already covered by `tests/baseline/` which hashes their outputs against an anchor.
- `apps/pmet_backend/test_api.py` — a standalone 5-stage smoke (imports / TaskCreate / StorageService / PMETExecutor / app load), run with `python apps/pmet_backend/test_api.py` on the host or `cd deploy && make test` inside the backend image. Not pytest.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途与目录](#cn-1) | [5. Anchor 与确定性](#cn-5) |
| [2. 单次 audit 怎么跑](#cn-2) | [6. 跨文件不变量](#cn-6) |
| [3. 运行](#cn-3) | [7. 新增 workflow](#cn-7) |
| [4. 为什么不用 pytest](#cn-4) | [8. 这里不审计什么](#cn-8) |

<a id="cn-1"></a>

## 1. 用途与目录

四个 workflow 脚本各对应一份长篇 markdown 文档，放在 [`docs/workflows/`](../../docs/workflows/) 下，讲清楚每个 workflow 做什么，并给出 canonical 输入下跑出来的真实数字（文件 hash、行数、大小、每条 check 的 PASS/FAIL）。这些数字不是人肉敲进去的 —— 那样谁一动脚本就过期了。它们靠**真的把每个 workflow 跑一遍**抓出来，再把值塞进 markdown 模板。

这就是本目录干的事。要点：只要 `make test-audit` 还过得去， `docs/workflows/*.md` 就还在说真话。

```
tests/audit/
├── generate.py           驱动：python3 tests/audit/generate.py [<name> ...]
├── lib.py                共享辅助（sha、run、渲染 check 表 ...）
├── workflows/            每个 workflow 一份 spec
│   ├── pair_only.py
│   ├── intervals.py
│   ├── promoter.py
│   └── elements.py
├── templates/            每个 workflow 一份 markdown 模板
│   ├── pair_only.md      （用 <<PLACEHOLDER>> 槽，由 spec 填）
│   ├── intervals.md
│   ├── promoter.md
│   └── elements.md
└── runs/                 每个 spec 跑进 runs/<name>/（gitignored）
```

输出落到 `docs/workflows/<name>.md`，**这部分入仓**。

<a id="cn-2"></a>

## 2. 单次 audit 怎么跑

每个 `workflows/<name>.py` 导出两个函数：

```python
def run(repo_root: Path, runs_dir: Path) -> dict:
    """对 canonical 输入跑 workflow。
    返回的 dict 同时给 verification check 和模板 <<PLACEHOLDER>> 填值。"""

def checks(data: dict) -> list[Check]:
    """从 run dict 渲染出 verification 表。"""
```

驱动逻辑：

1. import `workflows.<name>`，调 `spec.run()`，workflow 在干净的 `runs/<name>/` 子目录里执行。
2. 调 `spec.checks(data)`，每个 check 产出一行 `(name, expected, actual, verdict)`，verdict 取 `PASS`、`FAIL` 或 `WARN`。
3. 读 `templates/<name>.md`，把 `<<KEY>>` 占位符替换成 `data[key]`。两个合成占位符总是可用：`<<CHECK_TABLE>>`（渲染好的 markdown 表）和 `<<OVERALL_VERDICT>>`（一行总览）。
4. 写到 `docs/workflows/<name>.md`。

<a id="cn-3"></a>

## 3. 运行

```bash
# 跑全部四个 workflow 审计、重写 docs/workflows/*.md（~7 分钟）
make test-audit

# 或只跑一个（更快，调单个 workflow 时常用）
python3 tests/audit/generate.py promoter

# 或按名跑任意子集（按顺序，驱动程序逐个 dispatch）
python3 tests/audit/generate.py promoter intervals
```

**需要** —— host 二进制（`make build`）、Python 3（标准库够用，无需额外 `pip install`），以及各 workflow 需要的输入：pair_only 和 intervals 跑 `data/demos/` 下的 demo，promoter 和 elements 跑 TAIR10
+ Franco-Zorrilla（`make fetch-data` 拉 TAIR10；motif 库已在仓库
`data/motifs/` 下）。

**产出**

- **覆盖写** `docs/workflows/<name>.md`，每个跑了的 workflow 一份。这些文件入仓；`git diff docs/workflows/` 是信号。
- 工作文件丢到 `tests/audit/runs/<name>/`（gitignored）。
- stdout：每条 check 的 verdict + 每个 workflow 一行 OVERALL。

**怎么解读** —— 先看终端输出，再看渲染好的文档：

```
[audit] promoter
  PASS  motif_output.txt deterministic vs anchor (sha256 starts 4b24906abfe55e)
  PASS  binomial_thresholds.txt motifs == IC.txt motifs (n=110)
  PASS  binomial_thresholds.txt motifs == fimohits/ basenames
  PASS  IC.txt motifs == fimohits/ basenames
  …
[audit] promoter OVERALL: PASS (12 / 12)
```

- **OVERALL: PASS** → 文档新鲜且忠实；提交 `docs/workflows/<name>.md`。
- **OVERALL: WARN** → 有不阻塞的差异（例如某个 elements anchor 还没 bless）；查那一条 WARN 行，确认是有意改动就把抓到的 sha 粘进 spec 的 `TASK_ANCHORS`。
- **OVERALL: FAIL** → 某个 workflow 输出偏离了 anchor，或某条跨文件不变量挂了。要么 revert 这次 workflow 改动，要么改 `tests/audit/workflows/<name>.py` 里的 anchor 去认可新行为。

渲染好的 `docs/workflows/<name>.md` 里同样有这张 verdict 表，加上散文叙事。跑完 `git diff` 一下就知道审计视角下哪里变了。

耗时：pair_only ~15 秒，intervals ~16 秒，promoter ~2 分钟，elements ~5 分钟。

<a id="cn-4"></a>

## 4. 为什么不用 pytest

audit 的目的是**给人看的、可 review 的叙事**——讲每个 workflow 的用途、生物学意图、设计直觉、观察结果——而不是一次性的 pass/fail 信号。pytest 会把校验 check 和"其实是文档生成器"的角色搅在一起。workflow audit 与回归 baseline（`tests/baseline/`）并列：baseline 是机器可读的指纹集合， audit 是把那些指纹的含义讲给人听的散文。

<a id="cn-5"></a>

## 5. Anchor 与确定性

部分 check（`motif_output.txt deterministic vs anchor`）把实际 SHA-256 对比到 spec 里写死的 "anchor" 字符串。这些是**回归哨兵**：workflow 实现漂移时 SHA 变化，check FAIL。有意改动后想 bless 新 SHA，就改 spec 里的 anchor。

当前提交里的 anchor：

| workflow | anchor 文件 | sha（前 16） |
|---|---|---|
| pair_only | `data/demos/promoters/pairing/demo` → `motif_output.txt` | `0af5b936606fd3` |
| intervals | `data/demos/intervals` → `motif_output.txt` | `4858412a091983` |
| promoter | TAIR10 + Franco-Zorrilla → `motif_output.txt` | `4b24906abfe55e` |
| elements | per-task `motif_output.txt`（每个 `data/genes/*.txt` 一个 anchor） | 见 `workflows/elements.py` 里的 `TASK_ANCHORS` |

`elements` 每个 gene-task 一个 anchor；dict 里值为 `None` 的是"已知但未 bless"——本次提交后第一次 audit 运行会抓到真实 sha 并以 WARN 形式报上抓到的值，reviewer 粘回 `TASK_ANCHORS`。后续新增的 task（新的 gene list）以单独的 WARN 出现，直到加进 dict。

（旧版本 README 把"C 引擎非确定性"列为不给 elements 加 anchor 的理由。那个理由已过期 —— `elements.sh` 现在用 `index_fimo_fused`，是确定性的； `tests/baseline/README.md` 里 C-indexer 的 caveat 指的是另一个 workflow。)

<a id="cn-6"></a>

## 6. 跨文件不变量（独立于脚本自带的 validator）

四个 workflow 中三个（promoter、intervals、elements）在 indexing 末尾自己调 `scripts/python/check_homotypic_contract.py`。audit **也**在自己进程里跑等价检查 —— 见 `lib.contract_invariant_checks(index_dir)` —— 这样未来谁削弱或跳过脚本侧 validator，audit FAIL 行依然会暴露出来。 emit 的三条 check：

  - binomial_thresholds.txt 的 motif == IC.txt 的 motif
  - binomial_thresholds.txt 的 motif == fimohits/ 的 basename
  - IC.txt 的 motif == fimohits/ 的 basename

pair_only 的输入索引是 `data/demos/promoters/pairing/demo`，故意只带 6 个 fimohits 对 ~110 行 binomial threshold。同样三条 check 在那里以 WARN 等级跑（这是你应该知道的真不匹配，但不算回归 bug，不用修）。

<a id="cn-7"></a>

## 7. 新增 workflow

1. 建 `tests/audit/workflows/<name>.py`，写 `run()` 与 `checks()`。
2. 建 `tests/audit/templates/<name>.md`，给 `run()` 返回的所有键留 `<<PLACEHOLDER>>` 槽。`<<CHECK_TABLE>>` 和 `<<OVERALL_VERDICT>>` 始终要包含。
3. 在 `generate.py` 的 `ALL_WORKFLOWS` 里加 `<name>`。
4. 跑 `python3 tests/audit/generate.py <name>`，确认输出 markdown 读起来通顺、没有遗留 `<<UNRESOLVED:KEY>>`。

<a id="cn-8"></a>

## 8. 这里不审计什么

- `scripts/workflows/cli/05_promoter_gap.sh` 和 perf benchmark （`01_perf_cpu`、`02_perf_params`）—— 研究/性能脚本，已知调用方就一两个；加进 audit 是机械活，优先级低。
- `apps/cli/scripts/*`（底层 `run_indexing.sh` / `run_pairing.sh` 等） —— 已经被 `tests/baseline/` 覆盖（对 anchor 哈希它们的输出）。
- `apps/pmet_backend/test_api.py` —— 独立的 5 stage smoke （imports / TaskCreate / StorageService / PMETExecutor / app load）， host 跑 `python apps/pmet_backend/test_api.py`，或在后端镜像里 `cd deploy && make test`。不是 pytest。
