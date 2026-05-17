# Test coverage — what each track actually exercises

Companion to [README §10](../../README.md#en-10). The README table lists the five tracks, runtimes, and the one-line "why" each exists. This file is the enumeration of concrete cases each track covers — kept out of the README so the table stays readable, kept in-tree so refactors have a reference for what is expected to keep passing.

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## English

### Core math kernels — `make test-core`

~96 unit cases across the C/C++ engines:

- BH correction (monotonicity, edge cases with ties)
- Hypergeometric coloc — the heart of the pairing test
- Binomial / Poisson CDF (used by indexing for per-motif threshold selection)
- MinHash sketch (Jaccard estimation, sketch determinism)
- Motif-overlap geometry (Bonferroni "Global" column accounting)
- Load-balancing partition (`compute_partition` workload split)
- Indexing-side string / parsing utilities

Critical property: the test binary links the **same OBJECT library** the production binaries link. Tests cannot drift from what ships — there is no separate "test build" of the math layer.

### Repo-wide unit tests — `make test-unit`

One test file per fixed bug, locking the fix in. Current cases:

- `task_status` inference (pending / running / completed / failed / cancelled from on-disk state)
- Partial-result rescue link (give the user *something* downloadable even if the workflow died mid-run)
- Mail template rendering (subjects, body interpolation, attachment paths)
- Error classification (skip useless Celery retries on permanent failures: missing file, bad input, OOM)
- Watchdog staleness rule (15 min no `progress.json` update → mark failed)
- `list_tasks` pagination (page boundaries, total count, sort order)
- Heatmap dimension cap (R refuses huge matrices; cap before passing in)
- MinHash workflow resolver (`PMET_MINHASH_MIN` / `PMET_MINHASH_THRESHOLD` / `PMET_MINHASH_DEFAULT` precedence — see [scripts/lib/minhash.sh](../../scripts/lib/minhash.sh))
- Frontend store-action invariants (no double-submit, locale persistence, task-list shape)

Frontend tsx test auto-skips if `apps/pmet_frontend/node_modules` is absent (don't fail CI on missing JS deps when only Python/bash changed).

### Pipeline-level integration — `make test-integration`

Catches cross-script invariants that pure unit tests cannot:

- `bedtools` is called with `-s` (strand-aware) wherever required
- `build_promoters.py` uses `-s` (regression test for a real silent-correctness bug)
- Chromosome-name preflight runs on promoter + anno pipelines before FIMO
- `assess_integrity.py` handles non-adjacent fragments (GFF3 split features)
- Optional real-data TAIR10 strand check (skipped when reference data not on host)
- R-vs-frontend heatmap motif selection consistency (the two computations must select the same motif set, in the same order, for the heatmap to match the table)

Heavier scripts not in the smoke (they need real TAIR10 + the full motif library):

- `run_pipeline02_one_combo.sh` — one full combo end-to-end
- `run_pipeline08_ic_sweep.sh` — IC threshold sweep
- `verify_baseline.sh` — generic file-tree differ (originally a baseline check, kept as a tool)

See [tests/integration/README.md](../../tests/integration/README.md) for invocation details.

### Workflow audit — `make test-audit`

Runs each workflow end-to-end against canonical inputs and rewrites the corresponding [docs/workflows/*.md](../workflows/) with fresh numbers:

- `pair_only` — ~15 s
- `intervals` — ~16 s
- `promoter` — ~2 min
- `elements` — ~5 min

Each rendered doc carries SHA-256 anchors on key output files as regression sentinels, plus cross-file invariant checks. **Writes to `docs/workflows/`** — opt-in, not in `make test`. The OVERALL `PASS / WARN / FAIL` line at the bottom of each workflow doc is the truth source for "does the documented behavior still match the code."

### CLI baseline — `make baseline`

Hashes every output file from the inlined demo invocation in [tests/baseline/capture.sh](../../tests/baseline/capture.sh), plus the production binaries themselves, and diffs against the committed fingerprint:

- Output: every file in `results/cli/demo/...` produced by the demo run
- Binaries: the host CLI binaries under `build/`

**Writes `tests/baseline/fingerprints.txt`** — opt-in, not in `make test`. ~30 s.

---

<a id="cn"></a>

## 汉文

### Core 数学 kernel —— `make test-core`

C/C++ 引擎下 ~96 个 unit case：

- BH correction（单调性、并列值边界）
- 超几何 coloc —— pairing 检验的核心
- Binomial / Poisson CDF（indexing 选 per-motif 阈值用）
- MinHash sketch（Jaccard 估计、sketch 确定性）
- Motif overlap 几何（Bonferroni "Global" 列的归账）
- 负载均衡分区（`compute_partition` 工作量切分）
- Indexing 侧字符串 / 解析工具

关键性质：测试二进制链接的是**生产同一份 OBJECT library**，测的代码 = 跑的代码，不存在单独的"测试构建"。

### 仓库级 unit 测试 —— `make test-unit`

每个 fix 配一份 test，把已修过的 bug 钉死。当前覆盖：

- `task_status` 推导（从盘上状态推出 pending / running / completed / failed / cancelled）
- Partial-result rescue link（workflow 中途死掉时也给用户一个能下的东西）
- 邮件模板渲染（subject、body 插值、附件路径）
- 错误分类（永久失败别让 Celery 浪费重试：缺文件、输入错、OOM）
- Watchdog staleness 规则（`progress.json` 15 分钟没更新 → 标 failed）
- `list_tasks` 分页（页边界、总数、排序）
- Heatmap 尺寸 cap（R 不接巨型矩阵；传进去之前限大小）
- MinHash workflow 解析器（`PMET_MINHASH_MIN` / `PMET_MINHASH_THRESHOLD` / `PMET_MINHASH_DEFAULT` 优先级，见 [scripts/lib/minhash.sh](../../scripts/lib/minhash.sh)）
- 前端 store 动作不变量（防双提交、locale 持久化、任务列表 shape）

前端 tsx 测试在缺 `apps/pmet_frontend/node_modules` 时自动跳过（只改 Python/bash 时别让 CI 因为 JS 依赖没装而红）。

### Pipeline 级集成 —— `make test-integration`

防纯 unit 测试盖不到的跨脚本不变量：

- 该带 `-s`（strand-aware）的 `bedtools` 调用一定带 `-s`
- `build_promoters.py` 用了 `-s`（防一个真实出过的悄悄算错 bug 的回归）
- promoter + anno pipeline 在跑 FIMO 之前会做染色体名预检
- `assess_integrity.py` 能处理非相邻 fragment（GFF3 拆段 feature）
- 可选的 TAIR10 真实数据 strand 检查（host 上没参考数据时自动跳过）
- R 端与前端的 heatmap motif 选择一致性（两侧必须选出同样的 motif 集合、同样的顺序，热图才与表格对应）

smoke 之外的重脚本（需要真实 TAIR10 + 完整 motif 库）：

- `run_pipeline02_one_combo.sh` —— 一个完整组合端到端
- `run_pipeline08_ic_sweep.sh` —— IC 阈值 sweep
- `verify_baseline.sh` —— 通用文件树 differ（最初是 baseline 检查，留作工具）

调用细节见 [tests/integration/README.md](../../tests/integration/README.md)。

### Workflow audit —— `make test-audit`

把每个 workflow 用 canonical 输入跑一遍，把抓到的值重新渲染回 [docs/workflows/*.md](../workflows/)：

- `pair_only` —— ~15 秒
- `intervals` —— ~16 秒
- `promoter` —— ~2 分钟
- `elements` —— ~5 分钟

每份渲染出的文档对关键输出文件挂 SHA-256 anchor 当回归哨兵 + 跨文件不变量检查。**会写 `docs/workflows/`** —— opt-in，不入 `make test`。每份 workflow 文档底部的 OVERALL `PASS / WARN / FAIL` 行是"文档化行为是否还跟代码一致"的真相来源。

### CLI baseline —— `make baseline`

把 [tests/baseline/capture.sh](../../tests/baseline/capture.sh) 内联 demo 调用产出的每个文件、加生产二进制本身的 hash 全抓一遍，与 commit 过的 fingerprint diff：

- 输出：demo run 在 `results/cli/demo/...` 下产生的全部文件
- 二进制：`build/` 下的 host CLI 二进制

**会写 `tests/baseline/fingerprints.txt`** —— opt-in，不入 `make test`。~30 秒。
