# tests/unit/

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Purpose & sibling dirs](#en-1) | [3. Current tests](#en-3) |
| [2. Run](#en-2) | [4. Adding a new unit test](#en-4) |

<a id="en-1"></a>

## 1. Purpose & sibling dirs

You just fixed a bug. Without a test, the same bug can slip back in on the next refactor and you'd never notice — until a user runs into it months later. This directory is the antidote: one test file per fixed bug, each pinned to a single function (no docker, no celery, no real motif data, just `unittest.mock` and inlined fixtures), so the whole suite runs in under 5 seconds.

If a future change breaks the original fix, the matching test file fails fast and your CI catches it before merge.

Sibling test directories serve different purposes:

| Directory | Scope | Wall time | Needs |
|---|---|---|---|
| `tests/unit/` (this) | One function, no I/O beyond a tmp dir | < 5 s | bash + Rscript + python3 (+ tsx if frontend node_modules installed) |
| `tests/integration/` | Cross-script invariants on tiny fixtures | < 5 s | bedtools, samtools |
| `tests/audit/` | Whole-workflow runs against canonical inputs | minutes | full PMET stack |
| `tests/baseline/` | Build + run + fingerprint hash diff | minutes | full PMET stack |

<a id="en-2"></a>

## 2. Run

```bash
make test-unit                    # equivalent to: bash tests/unit/run.sh
```

**Needs** — `python3` always; `Rscript` for the heatmap test; `apps/pmet_frontend/node_modules/.bin/tsx` for the Zustand store test (i.e. `npm install` was run at least once). Missing tools auto-skip with a clear message — they don't fail the run.

**Produces** — stdout only. Exit 0 if every wired-in test file returned 0; exit 1 if any failed.

**How to read it** — each test file announces itself with a `[unit] <label>` line, then prints per-case PASS / SKIP / FAIL, then a final summary like `all N test file(s) passed`:

```
[unit] heatmap compute_dims (R)
  PASS  25-cluster grid: height capped at 40
  PASS  25-cluster grid: width capped at 40
  …
[unit] heatmap compute_dims: all passed

[unit] watchdog staleness (Python)
test_fresh_task_is_not_killed … ok
test_stale_progress_is_killed … ok
…
----------------------------------------------------------------------
Ran 7 tests in 0.050s
OK

…

========================================
[unit] all 9 test file(s) passed
```

A SKIP message is informational, not a failure — common ones: "`Rscript not found`", "`apps/pmet_frontend/node_modules not installed`". A FAIL prints the failing assertion plus the traceback for that test file, then keeps going to the next file (so one bad file doesn't hide later breakage).

<a id="en-3"></a>

## 3. Current tests

### `test_heatmap_dim_cap.R`

Covers the bug fixed in commit `4fd9aa2` (fix(heatmap): cap motifs, size figures dynamically). The original `scripts/r/heatmap.R` hard-coded `height <- 10 * ceiling(N/2)`; with many clusters this exceeded `ggplot2::ggsave`'s 50-inch sanity limit and aborted the whole task.

The fix lives at `scripts/r/heatmap.R::compute_dims` (top-level since the unit-test refactor); this test verifies:

- 25-cluster grid fits within `max_inches`
- small inputs are not inflated up to the cap
- monotonic in motif count
- extreme inputs (1000 motifs × 100 rows) still cap
- `max_inches` is configurable

### `test_stage_status.py`

Covers Problem 4 long-term fix in `TODO.md` — filesystem-derived per-stage view that augments the binary `task.status`. Exercises `services/stage_status.infer_stages` across:

- happy path (full Promoters): all 4 stages completed
- `promoters_pre` mode: indexing always reported as `skipped` (uses precomputed) and does NOT generate a warning
- the partial-result case: pairing completed but heatmap / zip show `skipped` with a warning note
- universe-mismatch failure: pairing `failed`, later stages still `pending`
- indexing-side failure (full mode), running mid-pipeline, cancelled mid-run
- `derive_effective_status`: returns `completed_with_warnings` only when a stage was skipped *with a non-trivial note*; pass-through for non-completed persisted states

### `test_partial_result_link.py`

Covers Problem 4 short-term fix in `TODO.md` — the partial-result rescue link. PMET writes `<task_id>/pairing/motif_output.txt` before the R heatmap and the zip stage; either of those late stages can fail and flip the task to `failed`, hiding the scientific output that's already on disk. The fix exposes a separate `/api/tasks/{id}/partial-result` link when the file exists, without changing `status` (so the failure remains visible).

Tests use `fastapi.TestClient` to drive the route handler with config patched to a tmp dir:

- `_locate_motif_output` returns Path / None / None on present / missing / empty file
- `GET /tasks/{id}` surfaces `partial_result_link` only when `status==failed` AND `motif_output.txt` exists
- `GET /tasks/{id}/partial-result` streams the TSV with a sensible filename, 404s when the file or the task is missing

### `test_mail_dispatch.py`

Companion to `test_stage_status.py` — that one tests status derivation; this one tests the worker mail templates do the right thing given an effective_status output. Stubs `MailService._send_email` so nothing leaves the test process and asserts subject/body content.

- `send_result_notification` clean: no "with notes" suffix, no warnings block, points at the zip
- `send_result_notification` with warnings: subject gets " (with notes)", warnings list rendered, status badge says `Completed (with notes)`
- `send_partial_result_notification`: subject says "partial result", body advertises the `/api/tasks/<id>/partial-result` endpoint with an explicit `motif_output.txt` reference and "Partial success" badge
- `send_partial_result_notification` without link: empty `partial_link` (NGINX_LINK unset) renders a "not configured" notice instead of a button — defensive
- `send_failed_notification`: "PMET task failed" subject, "Failed" badge, error summary inline, "Common causes" checklist present
- `_build_partial_result_link` helper (worker-side): https with path / http no trailing slash / empty / unparseable inputs map to the expected partial-result API URL

### `test_error_classification.py`

Covers Problem 3 in `TODO.md` — `is_retryable_task_error` skips celery's default 3x60s retry when the error message matches a permanent-failure substring, so a wrong-species gene list doesn't park a worker slot for ~3 minutes.

The fixture dicts (`PERMANENT_FIXTURES` / `TRANSIENT_FIXTURES`) hold real error strings lifted verbatim from their emit site (`scripts/workflows/*.sh`, `core/pairing/src/*.cpp`, `apps/pmet_backend/services/executor.py`). When you rename one of these messages, this test fails first. Cases:

- 9 permanent inputs (no-match-universe in all three workflow variants, missing files, FASTA/GFF3 chromosome mismatch, C++ promoter-lengths gene miss, no gene clusters, all 4 environment mismatches) → `is_retryable_task_error` returns False
- 8 transient inputs (generic command-failed, connection reset, disk I/O, redis unavailable, OOM kill, segfault, missing temp shards, empty string) → True
- Wrapped form: `executor.py` prefixes stderr with `Command failed:`; the substring detection must still trigger
- No-duplicates guard on the snippet list itself

### `test_watchdog_staleness.py`

Covers the liveness watchdog (problem 2 in `TODO.md`). The watchdog container scans `tasks/*.json` for `status==running` tasks whose `progress.json` mtime exceeds `LIVENESS_TIMEOUT_SEC`, marks them failed and process-tree-kills the bash subprocess.

Tests stub out the kill function and exercise:

- fresh task (recent progress) → not touched
- stale progress.json → killed, JSON marked failed with reason
- no progress.json yet, but old `started_at` → killed (catches pipelines that wedge before the first `emit_progress` call)
- non-running tasks (completed / failed / cancelled) → ignored
- malformed JSON → ignored
- threshold boundary (just under vs just over)
- missing `worker.pid` file → still mark failed, skip the kill silently

### `test_list_tasks_pagination.py`

Regression for the list-tasks endpoint where the search filter was applied AFTER slicing the page, hiding any match buried past the default 200-row limit. Drives the route handler against an in-memory fixture of mixed-status tasks:

- no filter → returns all within `limit`
- email filter → returns only matches even when buried past `limit`
- task_id substring filter → same
- combined filter → AND semantics
- `total` field reflects post-filter count, not page size
- empty result → 200 OK with empty list, not 404

### `test_minhash_resolver.sh`

Resolver-policy tests for `scripts/lib/minhash.sh::resolve_minhash_min`, which decides whether to enable the MinHash prefilter and with what `K`. Covers the env-var precedence chain (`PMET_MINHASH_MIN` overrides; `PMET_MINHASH_THRESHOLD` triggers auto-enable; `PMET_MINHASH_DEFAULT` is the value used when auto-enabled) and the no-arg default (off).

### `test_settings_store.ts`

Frontend Zustand store tests, run via `tsx`. Covers the per-mode form state actions that landed when the submit form was hoisted out of `useState` to fix SPA-nav state loss:

- `updateFilesForMode` patches only the target mode (no cross-bleed)
- `updateFilesForMode` merges patch (does not overwrite siblings)
- `updatePathsForMode` mirrors the file-update contract
- `setSpeciesForMode` is per-mode
- `updateParamsForMode` patches without dropping defaults
- `updateParamsForMode` applies multi-key patches in one call
- `resetSubmitForm` wipes files / paths / species / params back to defaults
- `mode` and `email` use plain (non-per-mode) setters

Auto-skipped if `apps/pmet_frontend/node_modules/.bin/tsx` is missing (fresh checkout where `npm install` hasn't been run).

<a id="en-4"></a>

## 4. Adding a new unit test

Convention:

1. One file per bug or invariant; name it `test_<topic>.{py,R,sh,ts}`.
2. The file must exit 0 on success, non-zero on any assertion failure.
3. Add a line to `run.sh` to invoke it.
4. Document the bug it covers (commit hash or `TODO.md` reference) in the file header.
5. Self-contained: no docker, no celery, no real motif data — use `unittest.mock`, fixture files inlined or generated on the fly.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 用途与同级目录](#cn-1) | [3. 当前测试](#cn-3) |
| [2. 运行](#cn-2) | [4. 新增 unit test](#cn-4) |

<a id="cn-1"></a>

## 1. 用途与同级目录

你刚修了一个 bug。如果不写测试，下一次重构很容易把同一个 bug 又带回来，而你毫无察觉 —— 直到几个月后用户撞上。这个目录就是解药：每个已修 bug 一份测试文件，每份钉死单个函数（不用 docker、不用 celery、不用真实 motif 数据，只 `unittest.mock` + 内联 fixture），整套跑不到 5 秒。

将来谁的改动把原修复弄坏了，对应那个测试文件先 fail，CI 在 merge 前就拦下。

同级测试目录用途各异：

| 目录 | 范围 | 耗时 | 需要 |
|---|---|---|---|
| `tests/unit/`（本目录） | 单函数，I/O 不出 tmp 目录 | < 5 秒 | bash + Rscript + python3（前端 node_modules 装了再加 tsx） |
| `tests/integration/` | 跨脚本不变量 + 小 fixture | < 5 秒 | bedtools、samtools |
| `tests/audit/` | 整 workflow 跑 canonical 输入 | 分钟 | 完整 PMET 栈 |
| `tests/baseline/` | build + run + 指纹 hash diff | 分钟 | 完整 PMET 栈 |

<a id="cn-2"></a>

## 2. 运行

```bash
make test-unit                    # 等价于：bash tests/unit/run.sh
```

**需要** —— `python3` 必装；heatmap 测试要 `Rscript`；Zustand store 测试要 `apps/pmet_frontend/node_modules/.bin/tsx`（即至少跑过一次 `npm install`）。缺工具自动跳过并明确说明，不算 fail。

**产出** —— 仅 stdout。所有挂上去的 test 文件返回 0 就 exit 0；任一失败 exit 1。

**怎么解读** —— 每个 test 文件先打一行 `[unit] <label>`，然后逐 case 输出 PASS / SKIP / FAIL，最后一行汇总，整体最末尾是 `all N test file(s) passed`：

```
[unit] heatmap compute_dims (R)
  PASS  25-cluster grid: height capped at 40
  PASS  25-cluster grid: width capped at 40
  …
[unit] heatmap compute_dims: all passed

[unit] watchdog staleness (Python)
test_fresh_task_is_not_killed … ok
test_stale_progress_is_killed … ok
…
----------------------------------------------------------------------
Ran 7 tests in 0.050s
OK

…

========================================
[unit] all 9 test file(s) passed
```

SKIP 是提示，不是失败 —— 常见的："`Rscript not found`"、 "`apps/pmet_frontend/node_modules not installed`"。FAIL 会打出失败的断言 + 该 test 文件的 traceback，然后继续跑下一个文件（一个坏的不会盖住后面的崩溃）。

<a id="cn-3"></a>

## 3. 当前测试

### `test_heatmap_dim_cap.R`

覆盖 commit `4fd9aa2`（fix(heatmap): cap motifs, size figures dynamically）修过的 bug。原版 `scripts/r/heatmap.R` 写死 `height <- 10 * ceiling(N/2)`； cluster 一多就超过 `ggplot2::ggsave` 的 50 寸 sanity 上限，整个任务 abort。

修后的实现在 `scripts/r/heatmap.R::compute_dims`（unit-test 重构后挪到顶层）；本测试验证：

- 25 个 cluster 的网格落在 `max_inches` 内
- 小输入不会被放大到 cap
- 对 motif 数单调
- 极端输入（1000 motif × 100 行）仍 cap 住
- `max_inches` 可配

### `test_stage_status.py`

覆盖 `TODO.md` 里 Problem 4 的长期修复 —— 文件系统派生的 per-stage 视图，对二元 `task.status` 做增强。覆盖 `services/stage_status.infer_stages` 的多种情况：

- happy path（完整 Promoters）：4 个 stage 全 completed
- `promoters_pre` 模式：indexing 永远报 `skipped`（用 precomputed），且不产生 warning
- partial-result 场景：pairing completed，但 heatmap / zip 显示 `skipped` + warning note
- universe 不匹配失败：pairing `failed`，后续 stage 仍 `pending`
- indexing 阶段失败（full 模式）、pipeline 中途仍 running、中途 cancelled
- `derive_effective_status`：只在某 stage 被 skip 且**有非平凡 note** 时返回 `completed_with_warnings`；非 completed 的持久化状态 pass-through

### `test_partial_result_link.py`

覆盖 `TODO.md` 里 Problem 4 的短期修复 —— partial-result rescue link。 PMET 在 R heatmap 和 zip stage 之前就写出 `<task_id>/pairing/motif_output.txt`；后两 stage 任一失败会把任务翻成 `failed`，把已经在盘上的科学产物藏起来。修复在文件存在时单独给一个 `/api/tasks/{id}/partial-result` 链接，不改 `status`（失败仍可见）。

测试用 `fastapi.TestClient` 驱动 route handler，把 config 打到 tmp 目录：

- `_locate_motif_output` 在文件存在 / 缺失 / 空三种情况下分别返回 Path / None / None
- `GET /tasks/{id}` 仅在 `status==failed` 且 `motif_output.txt` 存在时返回 `partial_result_link`
- `GET /tasks/{id}/partial-result` 用合理的文件名流式给 TSV，文件或任务缺失时 404

### `test_mail_dispatch.py`

`test_stage_status.py` 的伴生测试 —— 那个测状态推导;这个测 worker 的邮件模板,对 effective_status 输出做正确的事。把 `MailService._send_email` stub 掉,test 进程不会真发邮件,断言 subject/body 内容。

- `send_result_notification` 干净 case：subject 没有 " (with notes)" 尾巴、没有 warnings 段、指向 zip
- `send_result_notification` 有 warning：subject 加 " (with notes)"、渲染 warning 列表、状态徽章是 `Completed (with notes)`
- `send_partial_result_notification`：subject 含 "partial result"、正文广告 `/api/tasks/<id>/partial-result` 端点 + 显式 `motif_output.txt` 引用 + "Partial success" 徽章
- `send_partial_result_notification` 无 link：空 `partial_link` （NGINX_LINK 未设）渲染 "not configured" 提示而不是按钮 —— 防御
- `send_failed_notification`："PMET task failed" subject、"Failed" 徽章、错误摘要内联、"Common causes" 清单到位
- `_build_partial_result_link` 辅助函数（worker 侧）：含 path 的 https / 无尾斜杠的 http / 空串 / 不可解析输入都映射到对的 partial-result API URL

### `test_error_classification.py`

覆盖 `TODO.md` 里 Problem 3 —— `is_retryable_task_error` 在错误字符串匹配永久失败子串时跳过 celery 默认的 3×60s 重试,这样错物种的 gene list 不会霸占 worker slot ~3 分钟。

fixture dict（`PERMANENT_FIXTURES` / `TRANSIENT_FIXTURES`）持有真实的错误字符串,从原 emit 处一字不差地搬过来（`scripts/workflows/*.sh`、`core/pairing/src/*.cpp`、 `apps/pmet_backend/services/executor.py`）。改名其中任何一条信息,本测试最先 fail。case：

- 9 条永久输入（三种 workflow 下的 no-match-universe、缺文件、 FASTA/GFF3 染色体不匹配、C++ promoter-lengths 基因 miss、no gene clusters、4 种环境不匹配）→ `is_retryable_task_error` 返回 False
- 8 条临时输入（generic command-failed、连接重置、磁盘 I/O、redis 不可用、OOM kill、segfault、缺 temp shard、空字符串）→ True
- 包了一层的形式：`executor.py` 给 stderr 加 `Command failed:` 前缀; 子串检测仍要触发
- snippet 列表自身的去重 guard

### `test_watchdog_staleness.py`

覆盖 liveness watchdog（`TODO.md` Problem 2）。watchdog 容器扫 `tasks/*.json`,找 `status==running` 且 `progress.json` mtime 超过 `LIVENESS_TIMEOUT_SEC` 的任务,标失败、按进程树杀掉 bash 子进程。

测试 stub 掉 kill 函数,演练：

- 新鲜任务（recent progress）→ 不动
- progress.json 过时 → 杀,JSON 标 failed 带原因
- 还没 progress.json,但 `started_at` 老 → 杀（兜住第一次 `emit_progress` 之前就卡住的 pipeline）
- 非 running 任务（completed / failed / cancelled）→ 忽略
- 损坏 JSON → 忽略
- 阈值边界（刚好低于 vs 刚好高于）
- 缺 `worker.pid` 文件 → 仍标 failed,静默跳过 kill

### `test_list_tasks_pagination.py`

list-tasks 端点的回归测试 —— 之前 bug 是在切页**之后**才应用搜索过滤, 任何匹配藏在默认 200 行 limit 之外就消失。用 in-memory 混合状态任务 fixture 驱动 route handler:

- 无过滤 → `limit` 内全返
- email 过滤 → 即使藏在 `limit` 之外也只返匹配
- task_id 子串过滤 → 同上
- 组合过滤 → AND 语义
- `total` 字段反映过滤后数量,不是页大小
- 空结果 → 200 OK + 空列表,不是 404

### `test_minhash_resolver.sh`

测试 `scripts/lib/minhash.sh::resolve_minhash_min` 的策略 —— 它决定是否启用 MinHash 粗筛、用什么 `K`。覆盖 env 优先级链（`PMET_MINHASH_MIN` 强制覆盖；`PMET_MINHASH_THRESHOLD` 触发自动启用； `PMET_MINHASH_DEFAULT` 是自动启用时用的值）和无参默认值（关闭）。

### `test_settings_store.ts`

前端 Zustand store 测试,用 `tsx` 跑。覆盖 submit 表单从 `useState` 提到 store（修 SPA-nav 状态丢失）后落地的 per-mode 表单状态动作:

- `updateFilesForMode` 只 patch 目标 mode（无 cross-bleed）
- `updateFilesForMode` merge patch（不覆盖兄弟字段）
- `updatePathsForMode` 与文件更新合同对齐
- `setSpeciesForMode` 按 mode 隔离
- `updateParamsForMode` patch 时不丢 default
- `updateParamsForMode` 一次调用应用多键 patch
- `resetSubmitForm` 把 files / paths / species / params 全清回 default
- `mode` 与 `email` 用普通（非 per-mode）setter

`apps/pmet_frontend/node_modules/.bin/tsx` 缺失时自动跳过（全新 checkout 没跑 `npm install`）。

<a id="cn-4"></a>

## 4. 新增 unit test

约定：

1. 一个文件覆盖一个 bug 或不变量；命名 `test_<topic>.{py,R,sh,ts}`。
2. 文件成功 exit 0，任何断言失败 exit 非 0。
3. 在 `run.sh` 加一行调用它。
4. 在文件头注释里记下覆盖的 bug（commit hash 或 `TODO.md` 引用）。
5. 自包含：不要 docker、不要 celery、不要真实 motif 数据 —— 用 `unittest.mock`、fixture 内联或 on-the-fly 生成。
