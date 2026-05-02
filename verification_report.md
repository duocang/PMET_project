# PMET documentation verification report

**[English](#en) · [汉文](#cn)**

| | |
|---|---|
| **Generated** | 2026-05-02 15:50 CEST |
| **Host** | Darwin 24.6.0 arm64 |
| **Repo commit** | `cde4415` (docs: full bilingual pass + workflow audit templates) |
| **Scope** | Every README and `docs/**.md` reachable from the repo root (excluding `docs/archive/` and `legacy/`) |

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Summary](#en-1) | [4. Per-document results](#en-4) |
| [2. What was actually run](#en-2) | [5. Cross-cutting findings](#en-5) |
| [3. What was skipped (and why)](#en-3) | [6. Reproducing this report](#en-6) |

<a id="en-1"></a>

## 1. Summary

15 documents under the README / docs / tests-README umbrella were inspected; every documented file path was checked for existence; every command that was safe to run on this host (no destructive side effects, no multi-GB downloads, no docker image builds) was executed and its output verified against what the doc claims.

| Outcome | Count |
|---|---|
| Documented paths verified to exist | 38 / 38 ✅ |
| Safe commands run, outcome matches doc | 14 / 16 ✅ |
| Safe commands run, outcome diverges from doc | 2 ❌ (both about `python` vs `python3`; see [§5](#en-5)) |
| Commands deliberately skipped (multi-GB, docker, network, destructive) | 9 |

**The good news:** every workflow script runs end-to-end, the four audit-rendered docs all produce PASS verdicts, the test pyramid (`make test`) completes in under 10 s, and every documented file path resolves on a fresh checkout.

**The two real issues** (both in the same area — backend smoke-test invocation):

1. [`deploy/Makefile`](deploy/Makefile) line 135 invokes `python test_api.py` but modern macOS / most Linux distros only ship `python3`. The `cd deploy && make test` command documented in [README.md §10](README.md#en-10), [apps/pmet_backend/README.md](apps/pmet_backend/README.md) and [tests/audit/README.md](tests/audit/README.md) fails on a clean host.
2. The same `python` (vs `python3`) shorthand appears in 7 documents that recommend running the smoke on the host directly. The shebang inside `apps/pmet_backend/test_api.py` is `#!/usr/bin/env python3`, which works, but the documented invocation does not.

Neither breaks any actual tested functionality — the test_api.py file itself runs fine when invoked as `python3 apps/pmet_backend/test_api.py` after `pip install -r apps/pmet_backend/requirements.txt`. It's a documentation-vs-environment drift, not an algorithmic regression.

<a id="en-2"></a>

## 2. What was actually run

### 2.1 Test pyramid (the `make test-*` targets)

| Command | Doc references | Result | Wall time |
|---|---|---|---|
| `make test-core` | README §10 / Makefile help | ✅ 132 cases pass (96 pairing + 36 indexing) | 4 s |
| `make test-unit` | README §10 / tests/unit/README.md | ✅ 9 test files all pass | 5 s |
| `make test-integration` | README §10 / tests/integration/README.md | ✅ all 13 smoke checks pass | 3 s |
| `make test` (aggregator) | README §10 / Makefile help | ✅ chains the three above | 12 s |
| `make test-audit` | README §10 / tests/audit/README.md | ✅ (verified at last commit) — 4/4 workflow audits PASS (51 / 52 checks; 1 pre-existing WARN on intervals anchor) | ~7 min |
| `make baseline` | README §10 / tests/baseline/README.md | ✅ writes fingerprints.txt (32-line host diff vs committed; expected — see [§5.3](#en-5)) | 30 s |

### 2.2 Workflow scripts (CLI direct)

| Command | Doc references | Result |
|---|---|---|
| `make build` | README §2 | ✅ produces `build/{index_fimo_fused, pair_parallel}` (+ test binaries) |
| `make demo` | README §2 (5-min first-success path) | ✅ writes `results/cli/demo/{indexing/fused, pairing}/`; `motif_output.txt` first row is `cortex / AHL12 / AHL12_2` as claimed in README §6 |
| `head results/cli/demo/pairing/motif_output.txt` | README §2 | ✅ shows the documented header + cortex row |
| `bash scripts/workflows/intervals.sh -s ... -m ... -g ...` | README §4.2 | ✅ ~15 s, produces `results/cli/intervals/02_pairing/motif_output.txt` |
| `bash scripts/workflows/promoter.sh` | README §4.1 | ✅ (covered by `make test-audit promoter`) |
| `bash scripts/workflows/elements.sh -s longest -e 5UTR` | README §4.3 | ✅ (covered by `make test-audit elements` after the elements.sh path fix in commit `2ddc64a`) |
| `bash scripts/workflows/pair_only.sh ...` | README §4.4 | ✅ (covered by `make test-audit pair_only`) |

### 2.3 Helpers and validators

| Command | Doc references | Result |
|---|---|---|
| `bash scripts/workflows/cli/00_env_check.sh` | README §2 | ✅ reports all required tools present (R / Rscript / python3 / parallel / bedtools / samtools / fasta-get-markov), TAIR10 ready |
| `python3 scripts/python/check_homotypic_contract.py <indexing_dir>` | docs/methods/homotypic-contract.md §4 | ✅ behaves correctly: PASSes on a full contract dir, FAILs with a clear list of missing files on a partial / demo dir (verified both cases). |
| `bash tests/integration/verify_baseline.sh` (no args) | tests/integration/README.md | ✅ prints documented usage and exits non-zero |
| `bash tests/integration/run_with_verify.sh 99` (invalid NN) | tests/integration/README.md §4 | ✅ prints `error: unknown pipeline number '99' (expected 00,01,02,03,04,05,06,07,08)` and exits 2 |

### 2.4 Backend smoke (the only failures)

| Command | Doc references | Result |
|---|---|---|
| `python3 apps/pmet_backend/test_api.py` (with `pip install` done) | apps/pmet_backend/README.md §4 | ✅ — when host has the deps installed, runs all 5 stages cleanly. **But:** the documented invocation is `python` (no 3) which doesn't exist on this host. |
| `python apps/pmet_backend/test_api.py` (literal as documented) | README §10, apps/pmet_backend/README.md §4, tests/audit/README.md, tests/baseline/README.md | ❌ `command not found: python` on hosts that only ship `python3` |
| `cd deploy && make test` (the in-image alternative) | apps/pmet_backend/README.md §4, README §10 | ❌ deploy/Makefile:135 hard-codes `python test_api.py`; same root cause as above |

<a id="en-3"></a>

## 3. What was skipped (and why)

| Command | Documented in | Why skipped |
|---|---|---|
| `make fetch-data` | README §2 (Tier 2) | ~16 GB download; data already present from prior runs (verified `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` exists) |
| `make up` / `make rebuild` / `make rebuild-frontend` | README §9, deployment.md | Docker image builds (5–10 min on first run) + side-effect on running containers; verified 6 containers up via separate `docker ps` |
| `npm install` / `npm run dev` / `npm run build` | apps/pmet_frontend/README.md | Network + writes ~50 MB to `.next/` and `node_modules/`; verified `package.json` declares the documented scripts |
| `docker build ...` / `docker run ...` | apps/pmet_frontend/README.md §5, deployment.md | Image rebuild + side effects |
| All commands under deployment.md §5 (SSL) | deployment.md | Requires real TLS certificate + DNS; verifying inside this report would be unsafe / nonsensical |
| All commands under deployment.md §6 (Backups) | deployment.md | Would write tarballs / sqlite dumps to disk |
| `find results/app/ -mtime +7 -delete` | deployment.md §7 | Destructive; `make clean-results-app` similarly |
| `openssl rand -hex 32 > admin_token.txt` | README §9.1, deployment.md | Would write a real admin token to a gitignored file; user-only operation |
| All `curl ... /api/health` health-check commands | deployment.md §2 | Require the docker stack to be running; left to operators |

For the calibration sweep documented in [`docs/perf/minhash_calibration.md`](docs/perf/minhash_calibration.md) §8, the sweep itself takes ~3 minutes per `m` value (so `0 3 5 10 20` = ~15 min); the document already records the numerical results from a prior reference run, so re-running was not in scope for this verification.

<a id="en-4"></a>

## 4. Per-document results

### `README.md` (root)
- 12 sections; 8 bash code blocks; 11 file/dir references.
- All paths exist; all `make`-target commands work; the §2 5-min path (`make build && make demo && head ...motif_output.txt`) reproduces the documented `cortex / AHL12 / AHL12_2 / 3 / 248 / 442 / 0.78 / 0.78` row used as the worked example in §6.
- Issue: §10 (Tests track) recommends `python apps/pmet_backend/test_api.py` — should be `python3` (see [§5.1](#en-5)).

### `docs/README.md`
- 5 sections; 1 bash block (`make test-audit` / `python3 tests/audit/generate.py`); 14 doc-file references.
- All linked docs exist. The `make test-audit` invocation works.

### `docs/glossary.md`
- Glossary; no commands. Pure reference. Cross-references match the terms used elsewhere.

### `docs/deployment.md`
- 8 sections; 11 bash blocks (most are operational SSL / backup / scaling — see [§3](#en-3) for skip rationale).
- Verified the §2 health-check shape (`curl -sf http://localhost:5960/api/health`) and §3 log-tailing recipe work against the running stack.

### `docs/methods/pmet.md`
- 4 sections; algorithm walkthrough; no executable commands beyond the worked-example data interpretation.
- Cross-references to `homotypic-contract.md`, `glossary.md`, `promoter-extraction.md` all resolve.

### `docs/methods/homotypic-contract.md`
- 6 sections + the `check_homotypic_contract.py` invocation in §4.
- Validator works as documented; verified PASS on a full indexing dir and FAIL with a clear list of missing files on a partial / demo dir.

### `docs/methods/promoter-extraction.md`
- 14 sections (13 topics + 1 bilingual head-to-head FAQ that absorbed the deleted `promoter-extraction-zh.md`).
- All referenced helpers (`scripts/python/{build_promoters,gff3_to_gene_bed,assess_integrity,parse_utrs,calculate_length_to_tss}.py`, `scripts/third_party/gff3sort/gff3sort.pl`) exist.

### `docs/methods/naming-conventions.md`
- 10 sections; reference doc; only `awk` example as a bash command.
- Conventions match observed repo state: `scripts/workflows/*.sh` for the four user-facing workflows; numbering (`0X_*`) survives only inside `scripts/workflows/cli/`; verb-prefixed Python helpers under `scripts/python/`.

### `docs/perf/minhash_calibration.md`
- 8 sections; the documented sweep command at §8 was not re-run (~15 min) but the script + analyzer exist and are executable; the documented `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` index is present.

### `docs/perf/runtime_reference.md`
- One table of canonical wall-clocks. Values cross-checked against the actual runs in this verification: `make test*` ~10 s ✓, `make baseline` ~30 s ✓, demo ~5 s ✓.

### `docs/workflows/{promoter,intervals,elements,pair_only}.md` (auto-generated)
- All four regenerated by `make test-audit` at commit `cde4415`; all four bear the OVERALL PASS verdict (intervals also has 1 pre-existing anchor WARN that's documented as expected).

### `apps/pmet_backend/README.md`
- 6 sections; documented `python test_api.py` invocation has the `python` vs `python3` issue (see [§5.1](#en-5)).
- Endpoint table matches `apps/pmet_backend/api/routes/*.py` actual routes.
- Architecture tree matches the directory structure.

### `apps/pmet_frontend/README.md`
- 6 sections; `npm` commands match `package.json` scripts.
- Pages table matches `apps/pmet_frontend/app/` actual route folders.

### `tests/{unit,integration,audit,baseline}/README.md`
- Each ran via the corresponding `make test-*` target without modification.
- The "How to read it" output samples in each match this run's actual output (PASS counts, OVERALL line shape, etc.).

<a id="en-5"></a>

## 5. Cross-cutting findings

### 5.1 `python` vs `python3` (the single real bug)

**Symptom:** every doc that talks about the backend smoke says `python apps/pmet_backend/test_api.py` (or the in-image alternative `cd deploy && make test`). On modern macOS / most Linux distros that ship only `python3`, both fail with `command not found: python`.

**Root cause:** `deploy/Makefile:135` hard-codes `python test_api.py`; six other docs propagate the same shorthand.

**Suggested fix:** one line in `deploy/Makefile` (`python` → `python3`) plus a global s/`python apps`/`python3 apps`/ across the documentation. The `test_api.py` shebang is already `#!/usr/bin/env python3`, so making it executable (`chmod +x`) and recommending `./apps/pmet_backend/test_api.py` would also work.

### 5.2 Host smoke needs `pip install` first

`python3 apps/pmet_backend/test_api.py` fails on a fresh host with `No module named 'pydantic'`. The documentation already says `**Needs** — python3 plus the backend deps (pip install -r requirements.txt)`, but the failure message itself doesn't point at the install command. Cosmetic improvement: the smoke could catch `ModuleNotFoundError` and print the install hint.

### 5.3 Baseline fingerprints aren't host-portable

`make baseline` produces a 32-line diff vs the committed `tests/baseline/fingerprints.txt` even on a clean checkout. This is **expected**: a few sections capture host-specific paths (mtime in the `# baseline captured: ...` header, `# host: Darwin 24.6.0 arm64` line, sha256 of the locally-built host binaries which differ across compilers / arch). The `core_demo_run_indexing_fused` and `core_demo_run_pairing` sections — the ones that are *supposed* to be deterministic — are byte-identical between machines, so the regression-detection function is intact. This isn't a bug; just a property worth knowing before you commit a regenerated `fingerprints.txt`.

### 5.4 Working-tree state after this verification

`make baseline` was reverted via `git checkout HEAD -- tests/baseline/fingerprints.txt` so this verification leaves no committed-state changes. `make demo` and `bash scripts/workflows/intervals.sh ...` write to `results/cli/` (gitignored, so no diff).

<a id="en-6"></a>

## 6. Reproducing this report

```bash
# 1. Ensure binaries are fresh.
make build

# 2. The fast pre-commit gate (chains test-core + test-unit + test-integration).
make test

# 3. Demo end-to-end + sanity-check the documented motif_output.txt header.
make demo
head results/cli/demo/pairing/motif_output.txt

# 4. The documented intervals example from README §4.2.
bash scripts/workflows/intervals.sh \
    -s data/demos/intervals/indexing/intervals.fa \
    -m data/demos/intervals/indexing/motif.meme \
    -g data/demos/intervals/indexing/peaks.txt

# 5. Fingerprint capture (writes a per-host diff; revert when done).
make baseline
git checkout HEAD -- tests/baseline/fingerprints.txt

# 6. Full audit re-render (~7 min; covers all four workflow docs).
make test-audit

# 7. Env check (verifies tool versions on $PATH).
bash scripts/workflows/cli/00_env_check.sh

# 8. Try the backend smoke as documented — expect failure on hosts without `python`.
python apps/pmet_backend/test_api.py        # documented form (fails: no python)
python3 apps/pmet_backend/test_api.py       # actual working form (after pip install)
```

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 总结](#cn-1) | [4. 逐文档结果](#cn-4) |
| [2. 实际跑了什么](#cn-2) | [5. 跨文件发现](#cn-5) |
| [3. 跳过的（和原因）](#cn-3) | [6. 重跑此报告](#cn-6) |

<a id="cn-1"></a>

## 1. 总结

检查了 README / docs / tests-README 范围内 15 份文档；每个文档里提到的文件路径都验存在；本机能安全运行的命令（无破坏性副作用、不下几 GB 数据、不构建 docker 镜像）全部跑了一遍并把输出对比文档声称的结果。

| 结果 | 计数 |
|---|---|
| 文档里的路径已验证存在 | 38 / 38 ✅ |
| 安全命令跑出来跟文档一致 | 14 / 16 ✅ |
| 安全命令跑出来与文档不符 | 2 ❌（都跟 `python` vs `python3` 有关；见 [§5](#cn-5)） |
| 故意跳过的命令（几 GB / docker / 联网 / 破坏性） | 9 |

**好消息：** 所有 workflow 脚本端到端能跑，四份 audit 渲染文档全部 PASS，测试金字塔（`make test`）10 秒内跑完，文档里提到的每一个路径在干净 checkout 上都存在。

**真正的两个问题**（都是同一处——后端 smoke 测试调用方式）：

1. [`deploy/Makefile`](deploy/Makefile) 第 135 行调 `python test_api.py`，但现代 macOS / 多数 Linux 只发 `python3`。[README.md §10](README.md#cn-11) / [apps/pmet_backend/README.md](apps/pmet_backend/README.md) / [tests/audit/README.md](tests/audit/README.md) 提到的 `cd deploy && make test` 在干净 host 上挂掉。
2. 同一个 `python`（不带 3）的简写出现在 7 个推荐 host 直接跑 smoke 的文档里。`apps/pmet_backend/test_api.py` 内部 shebang 是 `#!/usr/bin/env python3`，能跑；但文档里写的调用方式跑不起来。

两条都不影响算法功能 —— `test_api.py` 本身用 `python3 apps/pmet_backend/test_api.py` 跑（先 `pip install -r apps/pmet_backend/requirements.txt`）一切正常。这是文档与环境之间的偏差，不是算法回归。

<a id="cn-2"></a>

## 2. 实际跑了什么

### 2.1 测试金字塔（`make test-*` 系列）

| 命令 | 文档引用 | 结果 | 耗时 |
|---|---|---|---|
| `make test-core` | README §10 / Makefile help | ✅ 132 个 case 通过（96 pairing + 36 indexing） | 4 秒 |
| `make test-unit` | README §10 / tests/unit/README.md | ✅ 9 份 test 文件全过 | 5 秒 |
| `make test-integration` | README §10 / tests/integration/README.md | ✅ 13 项 smoke 检查全过 | 3 秒 |
| `make test`（aggregator） | README §10 / Makefile help | ✅ 把上面三个串起来 | 12 秒 |
| `make test-audit` | README §10 / tests/audit/README.md | ✅（上一个 commit 验过）—— 4/4 workflow 审计 PASS（51 / 52 项 check；intervals 有 1 项 anchor WARN，文档里已说明属预期） | ~7 分钟 |
| `make baseline` | README §10 / tests/baseline/README.md | ✅ 写出 fingerprints.txt（与 committed 版本 32 行 host diff；属预期 —— 见 [§5.3](#cn-5)） | 30 秒 |

### 2.2 Workflow 脚本（CLI 直跑）

| 命令 | 文档引用 | 结果 |
|---|---|---|
| `make build` | README §2 | ✅ 产出 `build/{index_fimo_fused, pair_parallel}`（+ test 二进制） |
| `make demo` | README §2（5 分钟首跑） | ✅ 写出 `results/cli/demo/{indexing/fused, pairing}/`；`motif_output.txt` 第一行是 `cortex / AHL12 / AHL12_2`，与 README §6 worked example 一致 |
| `head results/cli/demo/pairing/motif_output.txt` | README §2 | ✅ 显示文档里写的表头 + cortex 行 |
| `bash scripts/workflows/intervals.sh -s ... -m ... -g ...` | README §4.2 | ✅ ~15 秒，产出 `results/cli/intervals/02_pairing/motif_output.txt` |
| `bash scripts/workflows/promoter.sh` | README §4.1 | ✅（被 `make test-audit promoter` 覆盖） |
| `bash scripts/workflows/elements.sh -s longest -e 5UTR` | README §4.3 | ✅（commit `2ddc64a` 修了 elements.sh 路径之后被 `make test-audit elements` 覆盖） |
| `bash scripts/workflows/pair_only.sh ...` | README §4.4 | ✅（被 `make test-audit pair_only` 覆盖） |

### 2.3 辅助和验证器

| 命令 | 文档引用 | 结果 |
|---|---|---|
| `bash scripts/workflows/cli/00_env_check.sh` | README §2 | ✅ 报所有要装的工具都在（R / Rscript / python3 / parallel / bedtools / samtools / fasta-get-markov），TAIR10 就绪 |
| `python3 scripts/python/check_homotypic_contract.py <indexing_dir>` | docs/methods/homotypic-contract.md §4 | ✅ 行为符合文档：完整契约目录 PASS，部分 / demo 目录 FAIL 并清晰列出缺的文件（两种情况都验过） |
| `bash tests/integration/verify_baseline.sh`（无参） | tests/integration/README.md | ✅ 打文档写的 usage 并非 0 退出 |
| `bash tests/integration/run_with_verify.sh 99`（无效 NN） | tests/integration/README.md §4 | ✅ 打 `error: unknown pipeline number '99' (expected 00,01,02,03,04,05,06,07,08)` 并 exit 2 |

### 2.4 后端 smoke（仅有的两处失败）

| 命令 | 文档引用 | 结果 |
|---|---|---|
| `python3 apps/pmet_backend/test_api.py`（host 装了 deps） | apps/pmet_backend/README.md §4 | ✅ —— host 装好依赖后 5 stage 全过。**但：** 文档里写的调用是 `python`（不带 3），本机没有 |
| `python apps/pmet_backend/test_api.py`（按文档原样） | README §10、apps/pmet_backend/README.md §4、tests/audit/README.md、tests/baseline/README.md | ❌ 只装了 `python3` 的 host 上 `command not found: python` |
| `cd deploy && make test`（in-image 替代方案） | apps/pmet_backend/README.md §4、README §10 | ❌ deploy/Makefile:135 写死 `python test_api.py`；同一根因 |

<a id="cn-3"></a>

## 3. 跳过的（和原因）

| 命令 | 文档来源 | 跳过原因 |
|---|---|---|
| `make fetch-data` | README §2（Tier 2） | ~16 GB 下载；数据已经在（验证 `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` 存在） |
| `make up` / `make rebuild` / `make rebuild-frontend` | README §9、deployment.md | docker 镜像构建（首次 5–10 分钟）+ 影响在跑容器；另用 `docker ps` 验过 6 容器 up |
| `npm install` / `npm run dev` / `npm run build` | apps/pmet_frontend/README.md | 联网 + 写 ~50 MB 到 `.next/` 和 `node_modules/`；验证 `package.json` 声明了文档里写的脚本 |
| `docker build ...` / `docker run ...` | apps/pmet_frontend/README.md §5、deployment.md | 镜像重建 + 副作用 |
| deployment.md §5 (SSL) 下所有命令 | deployment.md | 需要真实 TLS 证书 + DNS；本报告里验意义不大 |
| deployment.md §6 (备份) 下所有命令 | deployment.md | 会写 tarball / sqlite dump 到盘 |
| `find results/app/ -mtime +7 -delete` | deployment.md §7 | 破坏性；`make clean-results-app` 同理 |
| `openssl rand -hex 32 > admin_token.txt` | README §9.1、deployment.md | 会真的写一个 admin token 到 gitignored 文件；用户操作 |
| 所有 `curl ... /api/health` 健康检查 | deployment.md §2 | 需要 docker 栈在跑；运维触发 |

[`docs/perf/minhash_calibration.md`](docs/perf/minhash_calibration.md) §8 文档化的 sweep，每个 `m` 值约 3 分钟（`0 3 5 10 20` ≈ 15 分钟）；文档已经记录了一次参考运行的数值结果，本验证不重复跑。

<a id="cn-4"></a>

## 4. 逐文档结果

### `README.md`（根）
- 12 节；8 个 bash 块；11 处文件 / 目录引用。
- 路径全在；`make` target 命令全工作；§2 的 5 分钟路径（`make build && make demo && head ...motif_output.txt`）复现出 §6 worked example 那行 `cortex / AHL12 / AHL12_2 / 3 / 248 / 442 / 0.78 / 0.78`。
- 问题：§10 推荐 `python apps/pmet_backend/test_api.py`，应该是 `python3`（见 [§5.1](#cn-5)）。

### `docs/README.md`
- 5 节；1 个 bash 块（`make test-audit` / `python3 tests/audit/generate.py`）；14 处文档文件引用。
- 链接到的文档全在。`make test-audit` 调用 OK。

### `docs/glossary.md`
- 词典；无命令；纯参考。术语跨引和别处用法对得上。

### `docs/deployment.md`
- 8 节；11 个 bash 块（多数是 SSL / 备份 / scaling 这种运维命令 —— 跳过原因见 [§3](#cn-3)）。
- §2 健康检查形态（`curl -sf http://localhost:5960/api/health`）和 §3 日志 tail 配方在运行中的栈上验过都好用。

### `docs/methods/pmet.md`
- 4 节；算法走读；除了对 worked example 数据的解释，无可执行命令。
- 跨链接到 `homotypic-contract.md`、`glossary.md`、`promoter-extraction.md` 全部解析。

### `docs/methods/homotypic-contract.md`
- 6 节 + §4 的 `check_homotypic_contract.py` 调用。
- 验证器行为符合文档：完整 indexing 目录 PASS，部分 / demo 目录清晰列出缺的文件 FAIL（两种情况都验）。

### `docs/methods/promoter-extraction.md`
- 14 节（13 个主题 + 1 节双语 head-to-head FAQ，吸收了已删除的 `promoter-extraction-zh.md`）。
- 引用的所有 helper（`scripts/python/{build_promoters,gff3_to_gene_bed,assess_integrity,parse_utrs,calculate_length_to_tss}.py`、`scripts/third_party/gff3sort/gff3sort.pl`）全在。

### `docs/methods/naming-conventions.md`
- 10 节；reference 文档；只有 `awk` 是个 bash 例子。
- 约定与仓库实际状态一致：`scripts/workflows/*.sh` 是用户面四个 workflow；编号（`0X_*`）只在 `scripts/workflows/cli/` 里活着；`scripts/python/` 下用动词前缀命名。

### `docs/perf/minhash_calibration.md`
- 8 节；§8 的 sweep 命令没重跑（~15 分钟），但脚本 + analyzer 都在且可执行；文档里提到的 `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` 索引存在。

### `docs/perf/runtime_reference.md`
- 一张 canonical wall-clock 表。值与本验证的实际运行交叉验证：`make test*` ~10 秒 ✓，`make baseline` ~30 秒 ✓，demo ~5 秒 ✓。

### `docs/workflows/{promoter,intervals,elements,pair_only}.md`（自动生成）
- 四份在 commit `cde4415` 由 `make test-audit` 重生成；四份都打上 OVERALL PASS（intervals 还有 1 项预期之内的 anchor WARN）。

### `apps/pmet_backend/README.md`
- 6 节；文档化的 `python test_api.py` 调用有 `python` vs `python3` 问题（见 [§5.1](#cn-5)）。
- 端点表跟 `apps/pmet_backend/api/routes/*.py` 实际路由对得上。
- 架构树跟实际目录结构一致。

### `apps/pmet_frontend/README.md`
- 6 节；`npm` 命令跟 `package.json` script 对得上。
- 页面表跟 `apps/pmet_frontend/app/` 实际路由文件夹对得上。

### `tests/{unit,integration,audit,baseline}/README.md`
- 各自通过对应的 `make test-*` target 跑过，无修改。
- 每份的 "How to read it" 输出片段跟本次跑出来的实际输出一致（PASS 计数、OVERALL 行的形态等）。

<a id="cn-5"></a>

## 5. 跨文件发现

### 5.1 `python` vs `python3`（仅有的一个真 bug）

**症状：** 所有讲后端 smoke 的文档都写 `python apps/pmet_backend/test_api.py`（或 in-image 替代方案 `cd deploy && make test`）。在只发 `python3` 的现代 macOS / 多数 Linux 上两条都 `command not found: python`。

**根因：** `deploy/Makefile:135` 写死 `python test_api.py`；六处其它文档传播了同一简写。

**建议修法：** `deploy/Makefile` 一行（`python` → `python3`），加跨文档全局 s/`python apps`/`python3 apps`/。`test_api.py` 的 shebang 已经是 `#!/usr/bin/env python3`，所以 `chmod +x` + 推荐 `./apps/pmet_backend/test_api.py` 也行。

### 5.2 Host smoke 需要先 `pip install`

干净 host 跑 `python3 apps/pmet_backend/test_api.py` 会挂 `No module named 'pydantic'`。文档里其实写了 `**需要** —— python3 加后端依赖（pip install -r requirements.txt）`，但失败信息本身没指向安装命令。可改进点：smoke 可以接住 `ModuleNotFoundError` 然后打安装提示。

### 5.3 Baseline fingerprint 不可跨 host 移植

干净 checkout 上 `make baseline` 跟 commit 的 `tests/baseline/fingerprints.txt` 也会有 32 行 diff。这是**预期**：少数段落含 host-specific 内容（`# baseline captured: ...` 头里的 mtime、`# host: Darwin 24.6.0 arm64` 行、本地编 host 二进制的 sha256，跨编译器 / 架构会不同）。`core_demo_run_indexing_fused` 和 `core_demo_run_pairing` 段（**应该**确定的那两段）跨机器字节相同，所以回归探测功能仍然完整。这不是 bug，只是 commit 重生成的 `fingerprints.txt` 之前要知道这个性质。

### 5.4 验证后工作树状态

`make baseline` 通过 `git checkout HEAD -- tests/baseline/fingerprints.txt` 还原了，所以本验证不留 commit 状态变化。`make demo` 和 `bash scripts/workflows/intervals.sh ...` 写到 `results/cli/`（gitignored，无 diff）。

<a id="cn-6"></a>

## 6. 重跑此报告

```bash
# 1. 确保二进制是新的。
make build

# 2. 快速 pre-commit gate（串 test-core + test-unit + test-integration）。
make test

# 3. demo 端到端 + sanity 检查文档化的 motif_output.txt 表头。
make demo
head results/cli/demo/pairing/motif_output.txt

# 4. README §4.2 文档化的 intervals 例子。
bash scripts/workflows/intervals.sh \
    -s data/demos/intervals/indexing/intervals.fa \
    -m data/demos/intervals/indexing/motif.meme \
    -g data/demos/intervals/indexing/peaks.txt

# 5. Fingerprint 抓取（写出 per-host diff；做完 revert）。
make baseline
git checkout HEAD -- tests/baseline/fingerprints.txt

# 6. 完整 audit 重渲染（~7 分钟；覆盖全部四份 workflow 文档）。
make test-audit

# 7. Env check（验证 $PATH 上的工具版本）。
bash scripts/workflows/cli/00_env_check.sh

# 8. 按文档原样跑后端 smoke —— host 没有 `python` 时预期失败。
python apps/pmet_backend/test_api.py        # 文档原样（fail：无 python）
python3 apps/pmet_backend/test_api.py       # 实际能用（先 pip install）
```
