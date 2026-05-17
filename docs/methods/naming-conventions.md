# Naming conventions

**[English](#en) · [汉文](#cn)**

Single source of truth for how files in this repo are named. New code must follow it; pre-monorepo files that violate it are listed at the end as "grandfathered" and get cleaned up only when their contents change for an unrelated reason.

Goals: **predictable** (a name should hint at what the file does), **mechanically searchable** (`grep` / `find` should reliably locate everything for a given workflow), and **stable** (renames break tooling and history; we batch them).

---

<a id="en"></a>

## Contents

| | |
|---|---|
| [1. Top-level layout](#en-1) | [6. deploy/configure/ (deploy-time files)](#en-6) |
| [2. scripts/workflows/](#en-2) | [7. results/](#en-7) |
| [3. scripts/python/, scripts/r/, scripts/lib/](#en-3) | [8. docs/](#en-8) |
| [4. apps/cli/scripts/](#en-4) | [9. Commits](#en-9) |
| [5. tests/](#en-5) | [10. Grandfathered violations](#en-10) |

<a id="en-1"></a>

## 1. Top-level layout

```
.
├── README.md / Makefile / TODO.md / .gitignore
├── apps/                  CLI + web backend + web frontend
├── core/                  C/C++ engines (indexing + pairing) + CMake
├── scripts/               bash / python / R helpers + workflow scripts
├── data/                  inputs (genomes, gene lists, motif files, demos)
├── deploy/                docker-compose + nginx + Makefile shortcuts
├── docs/                  long-form documentation
├── tests/                 unit / integration / audit / baseline
├── build/                 host-compiled binaries (gitignored)
├── results/               run outputs (gitignored): app/ for web, cli/ for CLI
└── legacy/                pre-monorepo archive (gitignored)
```

Anything under `legacy/` is frozen historical reference and is not built, tested, or documented going forward.

<a id="en-2"></a>

## 2. scripts/workflows/

The four user-facing workflow scripts sit at this level:

```
scripts/workflows/
├── promoter.sh            classic 1 kb upstream of TSS
├── intervals.sh           arbitrary FASTA intervals (ATAC peaks etc.)
├── elements.sh            5'UTR / 3'UTR / CDS / mRNA / exon
├── pair_only.sh           re-pair an existing homotypic index
└── cli/                   CLI-only / dev / perf scripts (see §4)
```

These are runnable directly: `bash scripts/workflows/<name>.sh -h`. They also surface in the interactive menu at [`apps/cli/run.sh`](../../apps/cli/run.sh).

The leading `0X_` numbering used pre-monorepo (`03_promoter.sh`, `06_elements_longest.sh`, etc.) is **gone** at this level. Numbering survives only inside `cli/` for the perf / research scripts where the inherited pipeline number is still informative.

<a id="en-3"></a>

## 3. scripts/python/, scripts/r/, scripts/lib/

`scripts/python/<verb>_<object>.py` where `<verb>` is one of:

| Verb | Meaning |
|---|---|
| `parse_*` | read a file, emit a structured form |
| `build_*` | synthesise an artefact from inputs |
| `calculate_*` | numeric computation |
| `check_*` | validate a contract; non-zero exit on violation |
| `assess_*` | diagnostic / inspection without side effects |
| `run_*` | end-to-end driver (combines several helpers) |

When a script is retired, move it to `scripts/archive/` rather than deleting.

`scripts/r/<verb>_<object>.R` (preferred) or `<object>_<verb>.R` (grandfathered). Examples: `draw_heatmap.R`, `process_pmet_result.R`, `motif_pair_diagonal.R`.

`scripts/lib/<topic>.sh` — small bash helpers sourced by other scripts. `print_colors.sh`, `progress.sh`, `timer.sh`, `minhash.sh`.

`scripts/third_party/` — vendored upstream code (e.g. `gff3sort/`). Treated as a black box; updates from upstream replace the directory wholesale.

<a id="en-4"></a>

## 4. apps/cli/scripts/

The lower-level entry points for `make demo` and the perf benchmarks live here, plus the interactive menu wrapper:

```
apps/cli/
├── run.sh                 interactive menu (lists workflows + cli)
└── scripts/
    ├── run_indexing.sh        wraps build/indexing_fimo_fused
    ├── run_pairing.sh         wraps build/pairing_parallel
    ├── run_pipeline.sh        legacy umbrella
    ├── run_fimo_official.sh   FIMO-only sanity
    ├── compare_branches.sh    cross-branch hash diff
    ├── clean.sh               clear results/cli/
    └── bench/
        ├── calibrate_minhash.sh        MinHash perf sweep
        ├── analyze_minhash_calibration.py
        ├── pair_only.sh
        └── run_bench.sh
```

`scripts/workflows/cli/` (note the *parallel* path) holds workflow-adjacent scripts that aren't user-facing workflows in their own right:

```
scripts/workflows/cli/
├── 00_env_check.sh                 dependency check + TAIR10 download
├── 01_perf_cpu.sh                  CPU benchmark (single vs parallel)
├── 02_perf_params.sh               sweep promoter length / maxk / topn
├── 05_promoter_gap.sh              promoter scan with TSS-proximal gap
└── _pmet_index_element.sh          private helper sourced by elements.sh
```

The numbering inside `scripts/workflows/cli/` matches the historical pipeline numbers (`01–08` were the original monolithic scripts; `01`, `02`, `05` survived as standalone perf/research scripts; `03`/`04`/`06`/`07`/`08` got consolidated into `scripts/workflows/{promoter,intervals,elements,pair_only}.sh`).

<a id="en-5"></a>

## 5. tests/

```
tests/
├── unit/         < 5 s, one function per file
├── integration/  cross-script invariants on tiny fixtures
├── audit/        whole-workflow runs that regenerate docs/workflows/*.md
└── baseline/     CLI demo fingerprint diff
```

Naming inside each:

| Prefix / shape | Role | Examples |
|---|---|---|
| `test_<topic>.{py,R,sh,ts}` | one bug or invariant per file; exit 0 on pass | `tests/unit/test_heatmap_dim_cap.R` |
| `run_<scope>.sh` | run a suite or controlled workflow | `tests/integration/smoke/run.sh` |
| `verify_<thing>.sh` | compare output against a recorded contract / baseline | `tests/integration/scripts/verify_baseline.sh` |
| `<workflow>.py`, `<workflow>.md` (under `audit/`) | workflow audit specs and templates | `tests/audit/workflows/promoter.py` |

Subdirs: `tests/integration/smoke/` for the fast in-CI checks (with `fixtures/` for synthetic inputs + a small motif_output.txt for the heatmap consistency check), `tests/integration/scripts/` for the heavy manual scripts (real-data strand check, IC sweep, perf-params combo, generic baseline differ). The pre-monorepo `tests/integration/baselines/` directory was retired in favour of inline binary calls in `tests/baseline/capture.sh` and the data-level `verify_heatmap_consistency.py` regression check.

<a id="en-6"></a>

## 6. deploy/configure/ (deploy-time files)

These are bind-mounted into the running web stack and read at runtime. **All gitignored — never commit credentials.**

| File | Purpose | Required for |
|---|---|---|
| `email_credential.txt` | 5-line SMTP creds (username / password / from / server / port) | task-completion email notifications |
| `admin_token.txt` | one-line shared admin token (`openssl rand -hex 32`) | the admin-mode features in §8 of main README |
| `cpu_configuration.txt` | one integer (default thread count) | overrides `NUM_THREADS` for workflow scripts |
| `public_base_url.txt` | bare-domain deployment URL (e.g. `https://pmet.example.org`) used to build absolute links in outbound emails | task-detail link + partial-result link rendering |
| `admin_settings.json` | autogenerated; persists the `notify_on_submit` toggle | admin UI state |
| `runtime_calibration.json` | autogenerated; written by the worker on startup | runtime self-tuning |

<a id="en-7"></a>

## 7. results/

Two subdirs, both gitignored:

- `results/app/<task_id>/` — per-task outputs from the web app. The host-side path is the same whether the backend runs in docker or locally.
- `results/cli/<workflow>/` — outputs from CLI workflow runs (`results/cli/promoter/`, `results/cli/intervals/`, etc.).

Subdirectory layout inside each is a per-workflow contract — see [`tests/audit/workflows/<name>.py`](../../tests/audit/workflows/) and the rendered [`docs/workflows/<name>.md`](../workflows/).

`results/_AFTER_FIXES/` (if present) is a curated copy of selected artefacts kept after large fix series; optional, may be deleted.

<a id="en-8"></a>

## 8. docs/

Lowercase + hyphens, ASCII where practical (`pmet.md`, `promoter-extraction.md`, `homotypic-contract.md`).

Bilingual docs (`**[English](#en) · [汉文](#cn)**` header followed by parallel sections) is the preferred shape — see [`README.md`](../README.md) for the convention. Old split-file pairs (`*.md` + `*-zh.md`) are folded into one bilingual file when next touched.

Subdirs:

```
docs/
├── README.md         navigation
├── glossary.md       domain term reference
├── deployment.md     deep-dive companion to main README §8
├── methods/          algorithm / extraction / contract docs
├── workflows/        per-workflow audit (auto-rendered by tests/audit/)
├── perf/             performance investigations
├── figures/          SVG flowcharts and example outputs
└── archive/          pre-monorepo material kept for historical reference
```

<a id="en-9"></a>

## 9. Commits

Commit subjects use Conventional Commits prefixes (`feat`, `fix`, `docs`, `refactor`, `chore`, `test`). Subject ≤ 50 chars; body explains *why* not *what*. No co-authored-by tags.

<a id="en-10"></a>

## 10. Grandfathered violations

These exist in the repo and predate this document. They're not failures; they get cleaned up opportunistically when the file is next substantively edited.

- `scripts/python/calculateICfrommeme_IC_to_csv.py` — camel-mash. Functional; rename when next substantively edited.

---

<a id="cn"></a>

## 目录

| | |
|---|---|
| [1. 顶层目录](#cn-1) | [6. deploy/configure/（部署期文件）](#cn-6) |
| [2. scripts/workflows/](#cn-2) | [7. results/](#cn-7) |
| [3. scripts/python/、scripts/r/、scripts/lib/](#cn-3) | [8. docs/](#cn-8) |
| [4. apps/cli/scripts/](#cn-4) | [9. Commit](#cn-9) |
| [5. tests/](#cn-5) | [10. 历史遗留违规](#cn-10) |

<a id="cn-1"></a>

## 1. 顶层目录

```
.
├── README.md / Makefile / TODO.md / .gitignore
├── apps/                  CLI + web 后端 + web 前端
├── core/                  C/C++ 引擎（indexing + pairing）+ CMake
├── scripts/               bash / python / R helper + workflow 脚本
├── data/                  输入（基因组、基因列表、motif 文件、demo）
├── deploy/                docker-compose + nginx + Makefile 快捷方式
├── docs/                  长篇文档
├── tests/                 unit / integration / audit / baseline
├── build/                 host 编译产物（gitignored）
├── results/               运行输出（gitignored）：app/ 给 web，cli/ 给 CLI
└── legacy/                迁 monorepo 前的归档（gitignored）
```

`legacy/` 下的东西冻结成历史参考，往后不构建、不测、不维护。

<a id="cn-2"></a>

## 2. scripts/workflows/

四个面向用户的 workflow 脚本就在这一层：

```
scripts/workflows/
├── promoter.sh            经典：TSS 上游 1 kb
├── intervals.sh           任意 FASTA 区间（ATAC peak 等）
├── elements.sh            5'UTR / 3'UTR / CDS / mRNA / exon
├── pair_only.sh           对已有同型索引重新配对
└── cli/                   仅 CLI / dev / perf 脚本（见 §4）
```

直接可跑：`bash scripts/workflows/<name>.sh -h`。也在 [`apps/cli/run.sh`](../../apps/cli/run.sh) 的交互菜单里。

迁 monorepo 之前的前缀编号（`03_promoter.sh`、`06_elements_longest.sh` 之类）在这一层**已经没了**。编号只在 `cli/` 里活着，那些 perf/research 脚本继承的 pipeline 号还有信息量。

<a id="cn-3"></a>

## 3. scripts/python/、scripts/r/、scripts/lib/

`scripts/python/<verb>_<object>.py`，`<verb>` 是下面之一：

| 动词 | 含义 |
|---|---|
| `parse_*` | 读文件，输出结构化形式 |
| `build_*` | 从输入合成 artifact |
| `calculate_*` | 数值计算 |
| `check_*` | 校验某契约；违反 exit 非 0 |
| `assess_*` | 诊断 / 检查，无副作用 |
| `run_*` | 端到端 driver（组合多个 helper） |

退役的脚本搬到 `scripts/archive/`，不要直接删。

`scripts/r/<verb>_<object>.R`（首选）或 `<object>_<verb>.R`（遗留）。例：`draw_heatmap.R`、`process_pmet_result.R`、`motif_pair_diagonal.R`。

`scripts/lib/<topic>.sh` —— 被其它脚本 source 的 bash 小工具。`print_colors.sh`、`progress.sh`、`timer.sh`、`minhash.sh`。

`scripts/third_party/` —— 厂商代码（如 `gff3sort/`）。当黑盒处理；上游更新就整目录替换。

<a id="cn-4"></a>

## 4. apps/cli/scripts/

`make demo` 与 perf benchmark 的底层入口在这里，加上交互菜单 wrapper：

```
apps/cli/
├── run.sh                 交互菜单（列 workflow + cli）
└── scripts/
    ├── run_indexing.sh        包 build/indexing_fimo_fused
    ├── run_pairing.sh         包 build/pairing_parallel
    ├── run_pipeline.sh        遗留 umbrella
    ├── run_fimo_official.sh   仅 FIMO 的 sanity
    ├── compare_branches.sh    跨分支 hash diff
    ├── clean.sh               清 results/cli/
    └── bench/
        ├── calibrate_minhash.sh        MinHash perf sweep
        ├── analyze_minhash_calibration.py
        ├── pair_only.sh
        └── run_bench.sh
```

`scripts/workflows/cli/`（注意是平行路径）放跟 workflow 相邻、但本身不是用户面 workflow 的脚本：

```
scripts/workflows/cli/
├── 00_env_check.sh                 依赖检查 + 下载 TAIR10
├── 01_perf_cpu.sh                  CPU benchmark（单线程 vs 并行）
├── 02_perf_params.sh               sweep 启动子长度 / maxk / topn
├── 05_promoter_gap.sh              带 TSS 邻区 gap 的启动子扫描
└── _pmet_index_element.sh          被 elements.sh source 的私有 helper
```

`scripts/workflows/cli/` 里编号沿用历史 pipeline 号（`01–08` 是原本的单体脚本；`01`、`02`、`05` 作为独立 perf/research 留下；`03/04/06/07/08` 合并成了 `scripts/workflows/{promoter,intervals,elements,pair_only}.sh`）。

<a id="cn-5"></a>

## 5. tests/

```
tests/
├── unit/         < 5 秒，每文件一个函数
├── integration/  小 fixture 上的跨脚本不变量
├── audit/        端到端 workflow 跑完重生成 docs/workflows/*.md
└── baseline/     CLI demo 指纹 diff
```

每个目录里的命名：

| 前缀 / 形态 | 角色 | 示例 |
|---|---|---|
| `test_<topic>.{py,R,sh,ts}` | 一个 bug 或不变量一份；exit 0 即通过 | `tests/unit/test_heatmap_dim_cap.R` |
| `run_<scope>.sh` | 跑一个 suite 或受控 workflow | `tests/integration/smoke/run.sh` |
| `verify_<thing>.sh` | 输出对录制的契约 / baseline 做 diff | `tests/integration/scripts/verify_baseline.sh` |
| `<workflow>.py`、`<workflow>.md`（在 `audit/` 下） | workflow 审计 spec 与模板 | `tests/audit/workflows/promoter.py` |

子目录：`tests/integration/smoke/` 放 CI 跑的快检查（带 `fixtures/` 合成输入 + 一份小的 motif_output.txt 给热图一致性检查用），`tests/integration/scripts/` 放手动跑的重脚本（real-data strand 检查、IC sweep、perf-params 组合、通用 baseline differ）。monorepo 之前的 `tests/integration/baselines/` 已退役 —— 由 `tests/baseline/capture.sh` 内联二进制调用 + 数据级 `verify_heatmap_consistency.py` 接管。

<a id="cn-6"></a>

## 6. deploy/configure/（部署期文件）

bind-mount 进运行中的 web 栈、运行时读取。**全部 gitignored —— 凭据绝不要提交。**

| 文件 | 用途 | 谁需要 |
|---|---|---|
| `email_credential.txt` | 5 行 SMTP 凭据（username / password / from / server / port） | 任务完成邮件通知 |
| `admin_token.txt` | 一行共享 admin token（`openssl rand -hex 32`） | 主 README §8 的管理员功能 |
| `cpu_configuration.txt` | 一个整数（默认线程数） | 覆盖 workflow 脚本的 `NUM_THREADS` |
| `public_base_url.txt` | 部署的裸域名 URL（如 `https://pmet.example.org`），用来在外发邮件里拼绝对链接 | 任务详情链接 + partial-result 链接渲染 |
| `admin_settings.json` | 自动生成；持久化 `notify_on_submit` 开关 | 管理员 UI 状态 |
| `runtime_calibration.json` | 自动生成；worker 启动时写 | 运行时自调优 |

<a id="cn-7"></a>

## 7. results/

两个子目录，都 gitignored：

- `results/app/<task_id>/` —— web app 单任务输出。host 路径在 docker 模式和本地模式下完全相同。
- `results/cli/<workflow>/` —— CLI workflow 跑出来的输出（`results/cli/promoter/`、`results/cli/intervals/` 等）。

子目录布局是 per-workflow 契约 —— 见 [`tests/audit/workflows/<name>.py`](../../tests/audit/workflows/) 和渲染好的 [`docs/workflows/<name>.md`](../workflows/)。

`results/_AFTER_FIXES/`（如果存在）是大批 fix 之后挑出来的精选 artifact 副本；可选，可随时删。

<a id="cn-8"></a>

## 8. docs/

小写 + 短横线，能用 ASCII 就 ASCII（`pmet.md`、`promoter-extraction.md`、`homotypic-contract.md`）。

双语文档（顶部 `**[English](#en) · [汉文](#cn)**`，两段平行章节）是首选形态 —— 约定见 [`README.md`](../README.md)。遗留的 `*.md` + `*-zh.md` 分文件对，下次动到就合成一份双语。

子目录：

```
docs/
├── README.md         导航
├── glossary.md       领域术语词典
├── deployment.md     主 README §8 的深入伴生
├── methods/          算法 / 抽取 / 契约文档
├── workflows/        per-workflow 审计（tests/audit/ 自动渲染）
├── perf/             性能调研
├── figures/          SVG 流程图与示例输出
└── archive/          迁 monorepo 前的材料归档
```

<a id="cn-9"></a>

## 9. Commit

Commit subject 用 Conventional Commits 前缀（`feat`、`fix`、`docs`、`refactor`、`chore`、`test`）。subject ≤ 50 字；body 解释*为什么*而不是*做了什么*。不带 co-authored-by 标。

<a id="cn-10"></a>

## 10. 历史遗留违规

下面这些存在于仓库里、早于本文档。不算失败；下一次因为别的原因实质性编辑该文件时顺手清理。

- `scripts/python/calculateICfrommeme_IC_to_csv.py` —— camelCase 混搭。功能正常；下次实质性编辑再改名。
