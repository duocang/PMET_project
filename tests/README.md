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
| [`baseline/`](baseline/) | "Did my edit accidentally change the demo's numerical output?" | opt-in `make baseline-check` (~30 s) | [`tests/baseline/README.md`](baseline/README.md) |
| [`audit/`](audit/) | "What does each workflow actually do, on canonical inputs, end-to-end? Is it documented correctly?" | opt-in `make test-audit` (minutes); regenerates [`docs/workflows/*.md`](../docs/workflows/) | [`tests/audit/README.md`](audit/README.md) |

`make test` chains the three fast hermetic tracks (core + unit + integration smoke, ~10 s). `make test-all` layers on the backend API smoke + the CLI baseline-check for ~30 s of "everything that runs without an external service." E2E (`make test-e2e`) + audit + baseline-update are opt-in; see [README §10](../README.md#en-10) for the full track-by-track table.

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

## Test catalog

Every test file in the tree, one row each, with the single sentence that says what bug or invariant it pins. Test counts come from the actual runs; case names + further context live inside each file's docstring.

### C++ math kernels — `core/pairing/tests/`, `core/indexing/tests/`

Compiled into `test_pairing` / `test_indexing` via [CMakeLists.txt](../core/pairing/CMakeLists.txt#L44) (opt-in `PMET_BUILD_TESTS=ON`). Run by `make test-core`.

| File | Cases | Pins |
|---|--:|---|
| [`pairing/test_bh_correction.cpp`](../core/pairing/tests/test_bh_correction.cpp) | 6 | Benjamini-Hochberg p-value adjustment monotonicity + the historical integer-division bug that flattened all adj_p to 1.0 |
| [`pairing/test_binomial_poisson.cpp`](../core/pairing/tests/test_binomial_poisson.cpp) | 10 | `binomialCDF` + `poissonCDF` boundary cases vs hand-computed values + lgamma reference sweep |
| [`pairing/test_coloc.cpp`](../core/pairing/tests/test_coloc.cpp) | 10 | Right-tail hypergeometric coloc test — the heart of pairing; monotonicity in k, edge cases when universe / cluster is empty |
| [`pairing/test_fair_division.cpp`](../core/pairing/tests/test_fair_division.cpp) | 9 | Greedy LPT load balancer (4/3 worst-case ratio) for splitting motifs across worker threads |
| [`pairing/test_geometric_binomial.cpp`](../core/pairing/tests/test_geometric_binomial.cpp) | 8 | Per-promoter geometric-binomial test that filters individual kept hits before pair-level scoring |
| [`pairing/test_minhash_sketch.cpp`](../core/pairing/tests/test_minhash_sketch.cpp) | 8 | MinHash sketch determinism + Jaccard-tracking accuracy (powers the optional `-m` prefilter, default off; see [docs/perf/minhash_calibration.md](../docs/perf/minhash_calibration.md)) |
| [`pairing/test_motif_instances_overlap.cpp`](../core/pairing/tests/test_motif_instances_overlap.cpp) | 9 | Motif-pair overlap geometry — drop pairs whose IC overlap exceeds the threshold (asymmetric, position-aware) |
| [`pairing/test_output_sort.cpp`](../core/pairing/tests/test_output_sort.cpp) | 6 | `Output::sortComparisons` lex-by-(motif1, motif2) — pins the row order that R heatmap + frontend viz both depend on |
| [`pairing/test_sort_hits.cpp`](../core/pairing/tests/test_sort_hits.cpp) | 8 | `motif::sortHits` ascending-adjPVal order — silent-wrong-p-values regression risk if flipped |
| [`indexing/test_pair_test.cpp`](../core/indexing/tests/test_pair_test.cpp) | 16 | Indexing-side `motifsOverlap` + `binomialCDF` + `geometricBinTest` (the C engine has its own copies; they have to agree with pairing's) |
| [`indexing/test_utils.cpp`](../core/indexing/tests/test_utils.cpp) | 20 | C string helpers — `paste` / `paste2` / `getFilenameNoExt` / `removeTrailingSlash` (cheap to test, easy to break in a refactor) |

### Python backend unit — `tests/unit/test_*.py`

Run by `make test-unit` via [`tests/unit/run.sh`](unit/run.sh). Each file is "one fixed bug or one new feature → one regression test."

| File | Pins |
|---|---|
| [`test_admin_auth.py`](unit/test_admin_auth.py) | A1 brute-force throttle (5 fails / 5 min → 60 s 429 lockout) + A3 token rotation invalidates old cookies; **11 cases** |
| [`test_admin_stats.py`](unit/test_admin_stats.py) | Admin stats aggregator — out-of-window filtering, runtime sample purity, error-id normalization, zero-filled trend; **8 cases** |
| [`test_admin_tasks.py`](unit/test_admin_tasks.py) | A5 debug + A8 rerun + A9 note endpoints — stderr tail, note clear/cap, rerun celery-failure rollback; **14 cases** |
| [`test_audit.py`](unit/test_audit.py) | Append-only audit JSONL helper — emit never raises, 5 MB rotation, category filter, corrupt-line tolerance; **10 cases** |
| [`test_cleanup.py`](unit/test_cleanup.py) | Retention sweep — age boundary, dry_run, partial-artefact handling, errors don't abort sweep; **10 cases** |
| [`test_error_classification.py`](unit/test_error_classification.py) | Celery permanent-vs-transient classifier — skips useless retries on missing-file / bad-input / OOM type errors |
| [`test_healthcheck.py`](unit/test_healthcheck.py) | A6 self-test probes — each probe's status thresholds (disk warn at <5 GB / fail at <1 GB), `run_all` ordering contract; **12 cases** |
| [`test_list_tasks_pagination.py`](unit/test_list_tasks_pagination.py) | `list_tasks` filters email / task_id BEFORE paging (historical "I know I submitted but search returns nothing" bug) |
| [`test_mail_dispatch.py`](unit/test_mail_dispatch.py) | Mail template rendering for every status path including partial-success (motif_output.txt direct link) |
| [`test_partial_result_link.py`](unit/test_partial_result_link.py) | "Problem 4" regression — failed tasks with usable motif_output.txt expose a downloadable partial link, both detail + list views |
| [`test_stage_status.py`](unit/test_stage_status.py) | FS-derived per-stage view extends the binary `status` field with timeline + warnings (long-term Problem 4 fix) |
| [`test_watchdog_staleness.py`](unit/test_watchdog_staleness.py) | Liveness watchdog — kills tasks whose `progress.json` hasn't moved for 15 min, leaves fresh tasks alone |

### Bash / R unit — `tests/unit/test_*.{sh,R}`

Same `make test-unit` track; different runtimes.

| File | Pins |
|---|---|
| [`test_fimo_monitor.sh`](unit/test_fimo_monitor.sh) | `scripts/lib/fimo_monitor.sh` per-motif progress poller — emits heartbeat lines, handles missing files cleanly |
| [`test_minhash_resolver.sh`](unit/test_minhash_resolver.sh) | `scripts/lib/minhash.sh::resolve_minhash_min` — the policy that picks the `-m` flag value (env `PMET_MINHASH_MIN` > `PMET_MINHASH_DEFAULT` + motif-count threshold > off); **9 cases** |
| [`test_heatmap_dim_cap.R`](unit/test_heatmap_dim_cap.R) | `scripts/r/heatmap.R::compute_dims` regression for commit `4fd9aa2` — figure sizes cap at ggplot2's 50-inch limit instead of OOM-crashing |

### Frontend unit — `apps/pmet_frontend/tests/test_*.ts`

Run via `npm run test:unit` (chained by `tests/unit/run.sh`). Pure tsx with stubs — no jsdom, no React render.

| File | Pins |
|---|---|
| [`test_admin_store.ts`](../apps/pmet_frontend/tests/test_admin_store.ts) | `useAdminStore` shape — initial unchecked state, setStatus marks checked, `submissionsPaused` piggyback, `bumpSettings` increment, reset semantics; **8 cases** |
| [`test_settings_store.ts`](../apps/pmet_frontend/tests/test_settings_store.ts) | Per-mode form-state actions on `useSettingsStore` — patches only the targeted mode, merges patches rather than overwriting, resetSubmitForm wipes everything; **8 cases** |
| [`test_runtime.ts`](../apps/pmet_frontend/tests/test_runtime.ts) | Pure formatters: `formatBytes` / `formatRuntimeRange` / `summarizeError` / `humanizeIdentifier` — the helpers behind a dozen UI labels; **21 cases** |

### Frontend E2E — `apps/pmet_frontend/e2e/`

Run by `make test-e2e`. Self-skips when `PMET_E2E_ADMIN_TOKEN` is absent.

| File | Pins |
|---|---|
| [`admin.spec.ts`](../apps/pmet_frontend/e2e/admin.spec.ts) | Real-browser admin walkthrough: login redirect fix, A6 health 5-probe render, A2 audit row appears, A4 cleanup refresh after settings save, A1 brute-force lockout; **5 specs** |

### Integration — `tests/integration/smoke/`, `tests/integration/scripts/`

`smoke/` runs every `make test-integration` (~3–10 s). `scripts/` is heavy, manual, opt-in.

| File | Role | Pins |
|---|---|---|
| [`smoke/run.sh`](integration/smoke/run.sh) | smoke driver | 7 cross-script invariants: bedtools `-s`, `build_promoters.py` uses `-s`, chromosome-name preflight, `assess_integrity.py` non-adjacent fragments, optional TAIR10 real-data strand check, R-vs-frontend heatmap consistency |
| [`smoke/verify_heatmap_consistency.py`](integration/smoke/verify_heatmap_consistency.py) | smoke helper | R-side `ProcessPmetResult` + frontend `lib/visualize.ts::sortAndFilter` pick the same motifs from the same `motif_output.txt` |
| [`scripts/run_pipeline02_strand_realdata.sh`](integration/scripts/run_pipeline02_strand_realdata.sh) | heavy, opt-in | Real-data verification of the `02_benchmark_parameters` strand fix (`bedtools flank + getfasta -s` on the project's TAIR10 inputs) |
| [`scripts/run_pipeline02_one_combo.sh`](integration/scripts/run_pipeline02_one_combo.sh) | heavy, opt-in | One-cell end-to-end of `02_perf_params.sh` for capturing a real-data regression baseline |
| [`scripts/run_pipeline08_ic_sweep.sh`](integration/scripts/run_pipeline08_ic_sweep.sh) | heavy, opt-in | IC-threshold sweep against a pre-built homotypic index — parameter exploration on a fixed gene list |
| [`scripts/verify_baseline.sh`](integration/scripts/verify_baseline.sh) | generic utility | `<results_dir>` ↔ `<hashes.txt>` differ — kept after the dedicated baseline harness took over its old role |

### Baseline — `tests/baseline/`

`capture.sh` runs the demo binaries on tiny fixtures and prints sha256 of every output. `check.sh` compares a fresh capture against the committed `fingerprints.txt` (substance only — timestamp / git SHA in the header are excluded). Two Makefile targets:

| Target | Behaviour |
|---|---|
| `make baseline-check` (alias `make baseline`) | Non-destructive. Writes gitignored `fingerprints.actual.txt`, diffs, exits 0/non-0. Clean tree on pass. |
| `make baseline-update` | Destructive. Overwrites the tracked `fingerprints.txt`. Use only after a behavioural change is intentional. |

### Workflow audit — `tests/audit/`

`make test-audit` invokes [`generate.py`](audit/generate.py), which drives `[lib.py](audit/lib.py)` plus the per-workflow audit modules. Each module re-runs its workflow against canonical inputs, captures SHA-256 anchors, and rewrites the matching template in `templates/` into the published `docs/workflows/*.md`.

| Workflow module | Replays | Resulting doc |
|---|---|---|
| [`workflows/pair_only.py`](audit/workflows/pair_only.py) | `scripts/workflows/pair_only.sh` against the bundled demo index (~15 s) | [`docs/workflows/pair_only.md`](../docs/workflows/pair_only.md) |
| [`workflows/intervals.py`](audit/workflows/intervals.py) | `scripts/workflows/intervals.sh` against the bundled demo intervals fixture (~16 s) | [`docs/workflows/intervals.md`](../docs/workflows/intervals.md) |
| [`workflows/promoter.py`](audit/workflows/promoter.py) | `scripts/workflows/promoter.sh` against TAIR10 + Franco-Zorrilla 2014 + a real heat-stress gene cluster (~2 min) | [`docs/workflows/promoter.md`](../docs/workflows/promoter.md) |
| [`workflows/elements.py`](audit/workflows/elements.py) | `scripts/workflows/elements.sh` across all five `-e` options on TAIR10 (~5 min) | [`docs/workflows/elements.md`](../docs/workflows/elements.md) |

### Backend API smoke — `apps/pmet_backend/test_api.py`

5 stages: imports → TaskCreate model → StorageService instantiation → PMETExecutor instantiation → FastAPI app load. Run by `make test-backend-smoke`. Catches "I broke an import" before any of the higher-level tracks try to render anything.

### Known gaps (catalog uncovered these)

| File | Issue |
|---|---|
| [`apps/pmet_backend/test_task_creation_security.py`](../apps/pmet_backend/test_task_creation_security.py) | **5 real `unittest` cases, NOT wired into `make test`.** Covers the upload-session binding security fixes (#16 in TODO.md): bad-token 401, cross-session 400, wrong-slot demo path 400, duplicate task_id 409, token-not-leaking. Runs in ~0.1 s. |
| [`apps/pmet_backend/test_upload_routes.py`](../apps/pmet_backend/test_upload_routes.py) | **25 real `unittest` cases, NOT wired into `make test`.** Covers `/api/files/upload` accepted types, gzipped fasta, oversize caps, per-type rejects, session expiry. Runs in ~0.1 s. |
| [`tests/integration/scripts/run_pipeline02_strand_realdata.sh`](integration/scripts/run_pipeline02_strand_realdata.sh) | Filename starts with `test_*` but the script is in `scripts/` (heavy, opt-in). [naming-conventions.md](../docs/methods/naming-conventions.md) says `test_*.sh` is for one-bug-one-file unit tests — should be `run_pipeline02_strand_realdata.sh` to match the other `scripts/` peers. |
| [`legacy/from_shiny/legacy/test_nginx.sh`](../legacy/from_shiny/legacy/test_nginx.sh) | Pre-monorepo nginx config sanity. Not wired anywhere; lives under `legacy/` where it belongs. |

The two backend files are the real problem — they have **30 cases of unique upload / session-binding security coverage that don't run unless someone remembers to call them by hand.** Wiring them into `tests/unit/run.sh` is a one-line change.

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
| [`baseline/`](baseline/) | "我这次改有没有意外改了 demo 的数字输出？" | opt-in `make baseline-check`（~30 秒） | [`tests/baseline/README.md`](baseline/README.md) |
| [`audit/`](audit/) | "每个 workflow 在 canonical 输入上实际做了什么？文档跟实际对得上吗？" | opt-in `make test-audit`（分钟级），重生 [`docs/workflows/*.md`](../docs/workflows/) | [`tests/audit/README.md`](audit/README.md) |

`make test` 串起三条快 hermetic 轨道（core + unit + integration smoke，~10 秒）。`make test-all` 再叠加后端 API smoke + CLI baseline-check，~30 秒"无外部依赖能跑的全跑了"。E2E（`make test-e2e`）+ audit + baseline-update 留 opt-in；完整一表见 [README §10](../README.md#cn-10)。

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

## 测试目录

仓库里每个测试文件，一行说明它钉住的是什么 bug / 不变量。case 数来自实测；case 名 + 更细的背景写在各文件 docstring 里。

### C++ 数学 kernel —— `core/pairing/tests/`、`core/indexing/tests/`

由 [CMakeLists.txt](../core/pairing/CMakeLists.txt#L44) 编译成 `test_pairing` / `test_indexing`（opt-in `PMET_BUILD_TESTS=ON`）。`make test-core` 跑。

| 文件 | Case 数 | 钉住什么 |
|---|--:|---|
| [`pairing/test_bh_correction.cpp`](../core/pairing/tests/test_bh_correction.cpp) | 6 | BH p 值校正的单调性 + 历史上整数除法 bug（曾把所有 adj_p 平到 1.0） |
| [`pairing/test_binomial_poisson.cpp`](../core/pairing/tests/test_binomial_poisson.cpp) | 10 | `binomialCDF` + `poissonCDF` 边界值 vs 手算 + lgamma 参考 sweep |
| [`pairing/test_coloc.cpp`](../core/pairing/tests/test_coloc.cpp) | 10 | 右尾超几何 coloc 测试 —— pairing 的心脏；k 单调、universe / cluster 空时的边界 |
| [`pairing/test_fair_division.cpp`](../core/pairing/tests/test_fair_division.cpp) | 9 | 贪心 LPT 负载均衡（4/3 worst-case），把 motif 分给 worker 线程 |
| [`pairing/test_geometric_binomial.cpp`](../core/pairing/tests/test_geometric_binomial.cpp) | 8 | 单 promoter 上的几何-binomial 测试，决定哪个 hit 进入 pair 级别打分 |
| [`pairing/test_minhash_sketch.cpp`](../core/pairing/tests/test_minhash_sketch.cpp) | 8 | MinHash sketch 的确定性 + Jaccard 估计精度（支撑可选的 `-m` 预筛；默认关，见 [docs/perf/minhash_calibration.md](../docs/perf/minhash_calibration.md)） |
| [`pairing/test_motif_instances_overlap.cpp`](../core/pairing/tests/test_motif_instances_overlap.cpp) | 9 | Motif pair overlap 几何 —— IC overlap 超阈则丢（非对称、位置敏感） |
| [`pairing/test_output_sort.cpp`](../core/pairing/tests/test_output_sort.cpp) | 6 | `Output::sortComparisons` 按 (motif1, motif2) 字母序 —— R 热图 + 前端可视都依赖这个行顺序 |
| [`pairing/test_sort_hits.cpp`](../core/pairing/tests/test_sort_hits.cpp) | 8 | `motif::sortHits` 按 adjPVal 升序 —— 颠倒就是"悄悄算错 p 值"的风险 |
| [`indexing/test_pair_test.cpp`](../core/indexing/tests/test_pair_test.cpp) | 16 | indexing 侧的 `motifsOverlap` + `binomialCDF` + `geometricBinTest`（C 引擎自带一份，必须与 pairing 那份等价） |
| [`indexing/test_utils.cpp`](../core/indexing/tests/test_utils.cpp) | 20 | C 字符串工具 —— `paste` / `paste2` / `getFilenameNoExt` / `removeTrailingSlash`（写得便宜，重构最容易坏） |

### Python 后端单测 —— `tests/unit/test_*.py`

`make test-unit` 经 [`tests/unit/run.sh`](unit/run.sh) 调度。每个文件 = "一个修过的 bug 或新功能 → 一份回归测试"。

| 文件 | 钉住什么 |
|---|---|
| [`test_admin_auth.py`](unit/test_admin_auth.py) | A1 brute-force 节流（5 错 / 5 分钟 → 60 秒 429 锁） + A3 token 轮换让旧 cookie 失效；**11 case** |
| [`test_admin_stats.py`](unit/test_admin_stats.py) | Admin 统计聚合器 —— 出窗口过滤、runtime 样本纯度、error-id 归一化、零填趋势；**8 case** |
| [`test_admin_tasks.py`](unit/test_admin_tasks.py) | A5 debug + A8 rerun + A9 note 三端点 —— stderr 尾巴、note 清空+截断、rerun celery 失败回滚；**14 case** |
| [`test_audit.py`](unit/test_audit.py) | append-only 审计 JSONL helper —— emit 永不抛异常、5 MB 轮转、category 过滤、损坏行容忍；**10 case** |
| [`test_cleanup.py`](unit/test_cleanup.py) | 保留期清理 —— 年龄边界、dry_run、残缺 artefact 容忍、错误不中止 sweep；**10 case** |
| [`test_error_classification.py`](unit/test_error_classification.py) | Celery 永久 vs 瞬时分类器 —— 缺文件 / 错输入 / OOM 类错误不要浪费重试 |
| [`test_healthcheck.py`](unit/test_healthcheck.py) | A6 自检 probe —— 各 probe 的状态阈值（disk warn <5 GB / fail <1 GB）、`run_all` 顺序契约；**12 case** |
| [`test_list_tasks_pagination.py`](unit/test_list_tasks_pagination.py) | `list_tasks` 在分页**之前**先按 email / task_id 过滤（历史 bug："明明提过任务但搜不到"） |
| [`test_mail_dispatch.py`](unit/test_mail_dispatch.py) | 所有状态分支的邮件模板渲染，含 partial-success（motif_output.txt 直链）那一路 |
| [`test_partial_result_link.py`](unit/test_partial_result_link.py) | "问题 4" 回归 —— 失败任务若已写出 motif_output.txt，详情页 + 列表都暴露部分结果下载链 |
| [`test_stage_status.py`](unit/test_stage_status.py) | FS 派生的 per-stage 视图扩展了二元 `status` 字段（含 timeline + warnings；问题 4 长期方案） |
| [`test_watchdog_staleness.py`](unit/test_watchdog_staleness.py) | Liveness watchdog —— `progress.json` 15 分钟没动的任务标 failed，新任务别误杀 |

### Bash / R 单测 —— `tests/unit/test_*.{sh,R}`

同 `make test-unit` 一条线，runtime 不同。

| 文件 | 钉住什么 |
|---|---|
| [`test_fimo_monitor.sh`](unit/test_fimo_monitor.sh) | `scripts/lib/fimo_monitor.sh` 的 per-motif 进度 poller —— 打 heartbeat、缺文件不崩 |
| [`test_minhash_resolver.sh`](unit/test_minhash_resolver.sh) | `scripts/lib/minhash.sh::resolve_minhash_min` —— 决定 `-m` flag 值的策略（env `PMET_MINHASH_MIN` > `PMET_MINHASH_DEFAULT` + 阈值 > off）；**9 case** |
| [`test_heatmap_dim_cap.R`](unit/test_heatmap_dim_cap.R) | `scripts/r/heatmap.R::compute_dims` —— commit `4fd9aa2` 的回归，图尺寸 cap 在 ggplot2 的 50 inch 上限，不再 OOM 崩 |

### 前端单测 —— `apps/pmet_frontend/tests/test_*.ts`

`npm run test:unit`（被 `tests/unit/run.sh` 串入）。纯 tsx + stub，没有 jsdom，没有 React 渲染。

| 文件 | 钉住什么 |
|---|---|
| [`test_admin_store.ts`](../apps/pmet_frontend/tests/test_admin_store.ts) | `useAdminStore` 形状 —— 初始 unchecked、setStatus 标 checked、`submissionsPaused` 顺带传、`bumpSettings` 计数器、reset 语义；**8 case** |
| [`test_settings_store.ts`](../apps/pmet_frontend/tests/test_settings_store.ts) | `useSettingsStore` 的 per-mode 表单状态动作 —— 只 patch 目标 mode、merge 而不是 overwrite、resetSubmitForm 全清；**8 case** |
| [`test_runtime.ts`](../apps/pmet_frontend/tests/test_runtime.ts) | 纯格式化函数：`formatBytes` / `formatRuntimeRange` / `summarizeError` / `humanizeIdentifier` —— 一打 UI label 共用的 helper；**21 case** |

### 前端 E2E —— `apps/pmet_frontend/e2e/`

`make test-e2e`。缺 `PMET_E2E_ADMIN_TOKEN` 时整套 skip。

| 文件 | 钉住什么 |
|---|---|
| [`admin.spec.ts`](../apps/pmet_frontend/e2e/admin.spec.ts) | 真浏览器跑管理员 walkthrough：登录跳转修复、A6 health 5 probe 渲染、A2 audit 行出现、A4 cleanup 在 settings 保存后刷新、A1 brute-force 锁；**5 spec** |

### 集成 —— `tests/integration/smoke/`、`tests/integration/scripts/`

`smoke/` 每次 `make test-integration` 都跑（~3–10 秒）。`scripts/` 重、手动、opt-in。

| 文件 | 角色 | 钉住什么 |
|---|---|---|
| [`smoke/run.sh`](integration/smoke/run.sh) | smoke 驱动 | 7 个跨脚本不变量：bedtools `-s`、`build_promoters.py` 用了 `-s`、染色体名预检、`assess_integrity.py` 非相邻 fragment、可选 TAIR10 真实数据 strand 检查、R-vs-前端热图一致性 |
| [`smoke/verify_heatmap_consistency.py`](integration/smoke/verify_heatmap_consistency.py) | smoke helper | R 端 `ProcessPmetResult` 与前端 `lib/visualize.ts::sortAndFilter` 从同一份 `motif_output.txt` 选出同一组 motif |
| [`scripts/run_pipeline02_strand_realdata.sh`](integration/scripts/run_pipeline02_strand_realdata.sh) | 重、opt-in | `02_benchmark_parameters` strand 修复的真实数据验证（项目 TAIR10 输入上 `bedtools flank + getfasta -s`） |
| [`scripts/run_pipeline02_one_combo.sh`](integration/scripts/run_pipeline02_one_combo.sh) | 重、opt-in | `02_perf_params.sh` 单格端到端，用于抓真实数据回归 baseline |
| [`scripts/run_pipeline08_ic_sweep.sh`](integration/scripts/run_pipeline08_ic_sweep.sh) | 重、opt-in | IC 阈值 sweep 跑在已建好的同型索引上 —— 固定基因列表上的参数探索 |
| [`scripts/verify_baseline.sh`](integration/scripts/verify_baseline.sh) | 通用工具 | `<results_dir>` ↔ `<hashes.txt>` differ —— baseline 专用工具接管它的角色后留下来 |

### Baseline —— `tests/baseline/`

`capture.sh` 在小 fixture 上跑 demo 二进制，打印每个输出的 sha256。`check.sh` 把新 capture 与 commit 过的 `fingerprints.txt` 比对（只比 substance —— header 里 timestamp / git SHA 不参与）。两个 Makefile target：

| Target | 行为 |
|---|---|
| `make baseline-check`（别名 `make baseline`） | 非破坏。写 gitignored 的 `fingerprints.actual.txt`，diff，exit 0 / 非 0。pass 时清掉中间文件，工作树干净。 |
| `make baseline-update` | 破坏。覆盖写 commit 过的 `fingerprints.txt`。仅在行为变化确实是故意的时候用。 |

### Workflow 审计 —— `tests/audit/`

`make test-audit` 调 [`generate.py`](audit/generate.py)，后者驱动 [`lib.py`](audit/lib.py) 加各 workflow 的审计模块。每个模块把对应 workflow 用 canonical 输入跑一遍、抓 SHA-256 anchor、把 `templates/` 里的模板重渲染到 `docs/workflows/*.md`。

| Workflow 模块 | replay 什么 | 渲染到 |
|---|---|---|
| [`workflows/pair_only.py`](audit/workflows/pair_only.py) | `scripts/workflows/pair_only.sh` 跑自带 demo 索引（~15 秒） | [`docs/workflows/pair_only.md`](../docs/workflows/pair_only.md) |
| [`workflows/intervals.py`](audit/workflows/intervals.py) | `scripts/workflows/intervals.sh` 跑自带 demo intervals fixture（~16 秒） | [`docs/workflows/intervals.md`](../docs/workflows/intervals.md) |
| [`workflows/promoter.py`](audit/workflows/promoter.py) | `scripts/workflows/promoter.sh` 跑 TAIR10 + Franco-Zorrilla 2014 + 真实热胁迫 gene cluster（~2 分钟） | [`docs/workflows/promoter.md`](../docs/workflows/promoter.md) |
| [`workflows/elements.py`](audit/workflows/elements.py) | `scripts/workflows/elements.sh` 跑 TAIR10 上 5 个 `-e` 选项（~5 分钟） | [`docs/workflows/elements.md`](../docs/workflows/elements.md) |

### 后端 API smoke —— `apps/pmet_backend/test_api.py`

5 阶段：imports → TaskCreate model → StorageService 实例化 → PMETExecutor 实例化 → FastAPI app load。`make test-backend-smoke` 跑。任何一个 import 坏掉，在更上层测试试图渲染任何东西之前就抓到。

### 已知 gap（catalog 顺带暴出来的）

| 文件 | 问题 |
|---|---|
| [`apps/pmet_backend/test_task_creation_security.py`](../apps/pmet_backend/test_task_creation_security.py) | **5 个真 `unittest` case，不在 `make test` 里**。覆盖上传 session 绑定的安全修复（TODO.md #16）：错 token 401、跨 session 400、错 slot demo 路径 400、重复 task_id 409、token 不落盘。~0.1 秒跑完。 |
| [`apps/pmet_backend/test_upload_routes.py`](../apps/pmet_backend/test_upload_routes.py) | **25 个真 `unittest` case，不在 `make test` 里**。覆盖 `/api/files/upload` 接受的类型、gzip fasta、超大上限、per-type 拒绝、session 过期。~0.1 秒跑完。 |
| [`tests/integration/scripts/run_pipeline02_strand_realdata.sh`](integration/scripts/run_pipeline02_strand_realdata.sh) | 文件名以 `test_*` 开头，但脚本在 `scripts/`（重、opt-in）。[naming-conventions.md](../docs/methods/naming-conventions.md) 说 `test_*.sh` 是"一 bug 一文件"的单测命名 —— 应改成 `run_pipeline02_strand_realdata.sh`，跟 `scripts/` 里其他同伴对齐。 |
| [`legacy/from_shiny/legacy/test_nginx.sh`](../legacy/from_shiny/legacy/test_nginx.sh) | 迁 monorepo 之前的 nginx 配置 sanity。哪都没接进；住在 `legacy/` 名副其实。 |

后端那两个文件是真问题 —— **30 个 case 覆盖了独有的 upload / session 绑定安全场景，但除非有人手动想起来跑它们才会跑**。挂进 `tests/unit/run.sh` 是一行的改动。

## 三行决策树

| 你正要… | 找谁 |
|---|---|
| commit 任何动了 `core/`、`apps/pmet_backend/`、`scripts/workflows/`、`apps/pmet_frontend/app/visualize/` 的改动 | `make test`（覆盖 unit + integration，含 R/前端热图一致性） |
| commit 改了 demo 数值输出的东西（二进制、indexer、pairing、R 热图） | `make test` 后再 `make baseline` 加 `git diff` fingerprints |
| commit 改了 workflow 脚本或其 docstring | `make test` 后再 `make test-audit`（按 canonical replay 重生 `docs/workflows/*.md`） |
| 只想知道这台机器上当前坏在哪 | `make test` 看 FAIL 行；各子 README 指引 `results/tests/` 下对应那份 log |
