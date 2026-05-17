# tests/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## What lives here

Four sibling subdirectories, each answering a different question. You usually only need to know two of them — `make test` chains the fast tracks, `make test-audit` is the heavy opt-in.

| Subdir | Asks | When it runs | See |
|---|---|---|---|
| [`unit/`](unit/) | "Did this single function / R kernel / TS reducer change behaviour?" | every `make test` (~5 s) | [`tests/unit/README.md`](unit/README.md) |
| [`integration/`](integration/) | "Do the pipeline-level invariants still hold? bedtools `-s`, chromosome preflight, R-vs-frontend heatmap consistency?" | every `make test` (~3–10 s, smoke), heavier scripts opt-in | [`tests/integration/README.md`](integration/README.md) |
| [`baseline/`](baseline/) | "Did my edit accidentally change the demo's numerical output?" | opt-in `make baseline` (~30 s) | [`tests/baseline/README.md`](baseline/README.md) |
| [`audit/`](audit/) | "What does each workflow actually do, on canonical inputs, end-to-end? Is it documented correctly?" | opt-in `make test-audit` (minutes); regenerates [`docs/workflows/*.md`](../docs/workflows/) | [`tests/audit/README.md`](audit/README.md) |

## Where outputs land — the `results/tests/` convention

Every test that produces files (logs, sidecars, replay workspaces, fingerprints) writes under **one root**:

```
results/tests/
├── audit/runs/<workflow>/    workflow replays driving docs/workflows/*.md
├── baseline/                 indexing_fused.log, pairing.log, env_check.log, backend_pytest.log
├── heatmap/                  consistency_report.txt
└── smoke/                    strand_real.log, heatmap_consistency.log
```

Two anchors stay outside — they're committed artefacts, not per-run logs:

- [`tests/baseline/fingerprints.txt`](baseline/fingerprints.txt) — the SHA anchors `make baseline` regenerates and you `git diff` against
- [`tests/integration/smoke/fixtures/`](integration/smoke/fixtures/) — small synthetic inputs (FASTA / BED / `motif_output.txt` for the heatmap consistency check)

`results/tests/` is gitignored (covered by the top-level `results/` rule), and `make clean-results-tests` wipes the whole tree in one shot. `unit/` writes nothing to disk — those tests are pure stdout PASS/FAIL.

## Three-line decision tree

| If you're about to … | Reach for … |
|---|---|
| commit any change touching `core/`, `apps/pmet_backend/`, `scripts/workflows/`, `apps/pmet_frontend/app/visualize/` | `make test` (covers unit + integration including R/frontend heatmap consistency) |
| commit a change touching the demo numerical output (binaries, indexers, pairing, R heatmap) | `make test` then `make baseline` and `git diff` the fingerprints file |
| commit a change to a workflow script or its docstrings | `make test` then `make test-audit` (regenerates `docs/workflows/*.md` from canonical replays) |
| just want to know what's currently broken on this machine | `make test` and read the FAIL line; the per-suite README points at the right log under `results/tests/` |

---

<a id="cn"></a>

## 这里都有啥

四个并列子目录，各回答一个不同的问题。日常通常只关心两个 —— `make test` 串起来跑那些快的，`make test-audit` 是重型 opt-in。

| 子目录 | 回答的问题 | 跑时机 | 详见 |
|---|---|---|---|
| [`unit/`](unit/) | "这个单函数 / R kernel / TS reducer 行为变了没？" | 每次 `make test`（~5 秒） | [`tests/unit/README.md`](unit/README.md) |
| [`integration/`](integration/) | "Pipeline 级不变量还在不在？bedtools `-s`、染色体预检、R 与前端的热图一致性？" | 每次 `make test`（smoke ~3–10 秒），重脚本 opt-in | [`tests/integration/README.md`](integration/README.md) |
| [`baseline/`](baseline/) | "我这次改有没有意外改了 demo 的数字输出？" | opt-in `make baseline`（~30 秒） | [`tests/baseline/README.md`](baseline/README.md) |
| [`audit/`](audit/) | "每个 workflow 在 canonical 输入上实际做了什么？文档跟实际对得上吗？" | opt-in `make test-audit`（分钟级），重生 [`docs/workflows/*.md`](../docs/workflows/) | [`tests/audit/README.md`](audit/README.md) |

## 输出落点 —— `results/tests/` 约定

任何会写文件（log、sidecar、replay 工作目录、fingerprint）的测试都落到**同一个根**：

```
results/tests/
├── audit/runs/<workflow>/    workflow replay，喂给 docs/workflows/*.md 渲染
├── baseline/                 indexing_fused.log、pairing.log、env_check.log、backend_pytest.log
├── heatmap/                  consistency_report.txt
└── smoke/                    strand_real.log、heatmap_consistency.log
```

两个锚点留在外头 —— 它们是要 commit 的产物，不是每次运行的日志：

- [`tests/baseline/fingerprints.txt`](baseline/fingerprints.txt) —— `make baseline` 重抓的 SHA 锚，是 `git diff` 的对象
- [`tests/integration/smoke/fixtures/`](integration/smoke/fixtures/) —— 小合成输入（FASTA / BED / 给热图一致性检查用的 `motif_output.txt`）

`results/tests/` 被 gitignore（顶层 `results/` 规则覆盖），`make clean-results-tests` 一次性擦掉整个子树。`unit/` 不写盘 —— 那些测试纯靠 stdout 的 PASS/FAIL。

## 三行决策树

| 你正要… | 找谁 |
|---|---|
| commit 任何动了 `core/`、`apps/pmet_backend/`、`scripts/workflows/`、`apps/pmet_frontend/app/visualize/` 的改动 | `make test`（覆盖 unit + integration，含 R/前端热图一致性） |
| commit 改了 demo 数值输出的东西（二进制、indexer、pairing、R 热图） | `make test` 后再 `make baseline` 加 `git diff` fingerprints |
| commit 改了 workflow 脚本或其 docstring | `make test` 后再 `make test-audit`（按 canonical replay 重生 `docs/workflows/*.md`） |
| 只想知道这台机器上当前坏在哪 | `make test` 看 FAIL 行；各子 README 指引 `results/tests/` 下对应那份 log |
