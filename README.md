# PMET — Paired Motif Enrichment Tool

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

|                                       |                                |                                         |
| ------------------------------------- | ------------------------------ | --------------------------------------- |
| [1. What this tool does](#en-1)       | [5. Key parameters](#en-5)     | [8. Web app deployment](#en-8)          |
| [2. Install & quick start](#en-2)     | [6. Output format](#en-6)      | [9. Tests & regression baseline](#en-9) |
| [3. The algorithm: two stages](#en-3) | [7. Repository layout](#en-7)  | [10. Migration history](#en-10)         |
| [4. The four workflows](#en-4)        | [→ 跳到汉文](#cn)              |                                         |

<a id="en-1"></a>

## 1. What this tool does

PMET answers one question:

> Across a gene set you care about, which transcription factor (TF) motifs **co-occur in pairs** in their promoters (or any other region you specify) more often than chance?

Co-occurrence suggests two TFs may physically cooperate to regulate the same gene set — most TFs do not bind DNA alone; they need a partner adjacent on the sequence to drive a regulatory output. PMET finds those pairs.

<a id="en-2"></a>

## 2. Install & quick start

```bash
make build       # compile C/C++ engines into ./build/
make demo        # run indexing + pairing on the bundled demo data (data/*/demo)
make baseline    # capture regression fingerprints into tests/baseline/fingerprints.txt
```

Before the first real run, you may need to fetch public datasets (e.g. TAIR10):

```bash
bash pipeline/workflows/cli/00_env_check.sh   # check tools, download TAIR10 if missing
```

The R heatmap stage needs `Rscript` plus the packages listed in [`pipeline/r/install_packages.R`](pipeline/r/install_packages.R); without R the `motif_output.txt` is still produced — only the heatmap step is skipped.

<a id="en-3"></a>

## 3. The algorithm: two stages

![PMET algorithm: two stages](docs/figures/algorithm-two-stages-en.svg)

**Step 1 — Indexing (homotypic)**: scan every motif in the MEME file across your chosen region (promoter / UTR / CDS / ...) using FIMO. For each motif, a binomial threshold keeps the top n hits genome-wide; per-gene we keep at most k best hits. The result is an **index** that can be reused.

**Step 2 — Pairing (heterotypic)**: read the step-1 index, run a pair-enrichment test on your gene list. For every motif pair (m₁, m₂), is their co-occurrence in your cluster significantly higher than the genome-wide background? The test is a **hypergeometric**, with raw and BH/Bonferroni-adjusted p-values.

<a id="en-4"></a>

## 4. The four workflows

The four main scripts live under [`pipeline/workflows/`](pipeline/workflows/). Three of them produce a homotypic index, the fourth (`pair_only.sh`) re-uses one. Each has a corresponding audit + reference doc under [`docs/workflows/`](docs/workflows/) (step-by-step, biological intent, regression SHA anchors).

![PMET workflow overview](docs/figures/workflow-overview-en.svg)

### 4.1 Promoters — `promoter.sh` &nbsp;[details](docs/workflows/promoter.md)

The classic case. Scan ~1 kb upstream of every TSS (with 5'UTR included by default).

```bash
bash pipeline/workflows/promoter.sh                                    # uses default TAIR10 + Franco-Zorrilla
bash pipeline/workflows/promoter.sh -s my_genome.fa -a my_annot.gff3   # any other species
```

### 4.2 Arbitrary intervals — `intervals.sh` &nbsp;[details](docs/workflows/intervals.md)

Use this when your unit of analysis is not "the promoter of a gene" but ATAC/ChIP peaks, conserved elements, or any other FASTA region. Each FASTA record name (e.g. `chr1:1234-5678`) is one analysis unit; the script auto-sanitises `:` in headers (FIMO and the binary fimohits format don't accept it).

```bash
bash pipeline/workflows/intervals.sh \
    -s data/demos/intervals/intervals.fa \
    -m data/demos/intervals/motif.meme \
    -g data/demos/intervals/peaks.txt
```

### 4.3 Genomic elements — `elements.sh` &nbsp;[details](docs/workflows/elements.md)

Not restricted to promoters. Index any GFF3 feature type: 5'UTR / 3'UTR / CDS / mRNA / exon. The figure below shows one gene on the chromosome (top row), then five rows below — one per `-e` option — with the indexed parts highlighted:

![What each -e option indexes](docs/figures/gff3-element-options-en.svg)

The `mRNA` feature in GFF3 is the **primary transcript** — the full span from TSS to TTS, introns included. This is distinct from "mature mRNA" (exons only, after splicing) which GFF3 does not encode directly.

| GFF3 type         | Physical region indexed                                | In plain words                                    |
| ----------------- | ------------------------------------------------------ | ------------------------------------------------- |
| `mRNA`            | TSS → TTS as one continuous span, **introns included** | the whole gene body — TFs can bind in introns too |
| `CDS`             | one interval per coding exon, **introns excluded**     | only the protein-coding bits                      |
| `exon`            | one interval per exon (UTR + CDS portions)             | like CDS but also catches UTR-bearing exons       |
| `five_prime_UTR`  | the 5' UTR span per isoform                            | untranslated leader upstream of CDS               |
| `three_prime_UTR` | the 3' UTR span per isoform                            | untranslated trailer downstream of CDS            |

A gene may have multiple isoforms — two aggregation strategies:

| `-s`      | Meaning                                                                         |
| --------- | ------------------------------------------------------------------------------- |
| `longest` | per gene, pick the isoform with the largest total length for the chosen element |
| `merged`  | take the genomic union across all isoforms as one span                          |

For `-e mRNA` an additional `-m Yes\|No` controls UTR inclusion:

| Command              | Resulting region                                                  |
| -------------------- | ----------------------------------------------------------------- |
| `-e mRNA -m Yes`     | full mRNA (5'UTR + CDS + 3'UTR), one span per gene                |
| `-e mRNA -m No`      | mRNA minus UTRs (CDS span), one span per gene                     |
| `-e CDS` / `-e exon` | each CDS fragment / exon as its own span (no isoform aggregation) |

`-m` is only meaningful with `-s longest -e mRNA`; in any other combination it is ignored with a warning.

```bash
bash pipeline/workflows/elements.sh -s longest -e 5UTR -t 8
bash pipeline/workflows/elements.sh -s longest -e mRNA -m Yes -t 8
```

### 4.4 Re-pair an existing index — `pair_only.sh` &nbsp;[details](docs/workflows/pair_only.md)

Skip the expensive indexing stage; against an existing index, swap in a new gene list and rerun pairing only. The web app's `promoters_pre` mode is backed by this same script.

```bash
bash pipeline/workflows/pair_only.sh \
    -d results/promoter/01_homotypic \
    -g data/genes/my_new_clusters.txt \
    -o results/repaired
```

<a id="en-5"></a>

## 5. Key parameters

Each script's `-h` is the authoritative reference (with defaults). The table below only highlights the **easy-to-trip-on** ones — short-option letters **differ across scripts**, so memorise per-script.

### Indexing stage

| Parameter                                         | promoter | intervals | elements        |
| ------------------------------------------------- | -------- | --------- | --------------- |
| topn / per-motif top n genome-wide (default 5000) | `-n`     | `-n`      | (fixed)         |
| maxk / per-gene max k hits (default 5)            | `-k`     | `-k`      | (fixed)         |
| FIMO p-value threshold (default 0.05)             | `-f`     | `-f`      | (fixed)         |
| promoter length, bp (default 1000)                | `-p`     | —         | —               |
| include 5'UTR (default Yes)                       | `-u`     | —         | —               |
| promoter overlap (default NoOverlap)              | `-v`     | —         | —               |
| element type                                      | —        | —         | `-e` (required) |
| isoform strategy (`longest`)                      | —        | —         | `-s`            |

`elements.sh` deliberately exposes only `-s -e -m -t -d`; everything else uses `_pmet_index_element.sh` defaults — call that lower-level script directly if you need finer knobs.

### Pairing stage

| Parameter                                                | promoter        | intervals       | elements                        | pair_only       |
| -------------------------------------------------------- | --------------- | --------------- | ------------------------------- | --------------- |
| IC threshold (filters low-information motifs, default 4) | **`-c`**        | **`-c`**        | (fixed)                         | **`-i`**        |
| gene list                                                | `-g` (required) | `-g` (required) | (loops over `data/genes/*.txt`) | `-g` (required) |
| threads (default 4; pair_only check `-h`)                | `-t`            | `-t`            | `-t`                            | `-t`            |

> ⚠️ The IC threshold is `-c` in `promoter.sh / intervals.sh` but `-i` in `pair_only.sh` — historical mismatch, never harmonised. In `promoter.sh`, `-i` is actually `gff3_id_key` (the GFF3 attribute key).

<a id="en-6"></a>

## 6. Output format

The terminal product is `motif_output.txt`, TAB-separated, 11 columns:

```
Cluster  Motif1  Motif2  n_genes_with_both  total_with_both  n_in_cluster  raw_p  adj_p_BH  adj_p_Bonf  adj_p_global  genes
cortex   AHL12   AHL12_2 3                  248              442           0.784  0.784     1.0         1.0           AT1G05680;AT2G20120;AT4G02170;
```

Sorted by `adj_p_BH`. Each row answers: in cluster `cortex`, is the motif pair `(AHL12, AHL12_2)` co-occurring as a significant cooperative signal?

<a id="en-7"></a>

## 7. Repository layout

```
core/          C/C++ engines (indexing, pairing) + CMake
pipeline/      shared bash + python + R helpers; workflows
apps/
  cli/             command-line entry points and helpers
  pmet_backend/    FastAPI + Celery worker
  pmet_frontend/   Next.js
deploy/        docker-compose, nginx, Dockerfiles
data/          demo / fixture data (large data is gitignored)
tests/
  audit/         workflow audit + auto-rendered docs/workflows/*.md
  baseline/      regression fingerprints
  integration/   end-to-end tests
docs/
legacy/        archived historical code
build/         compile artifacts (gitignored)
results/       script outputs (gitignored)
```

Auxiliary scripts under [`pipeline/workflows/cli/`](pipeline/workflows/cli/): `00_env_check.sh` (dependency check + TAIR10 download), `01_perf_cpu.sh` / `02_perf_params.sh` (perf benchmarks), `05_promoter_gap.sh` (promoter gap analysis — see figure below), `_pmet_index_element.sh` (the indexing sub-pipeline library sourced by `elements.sh` — not invoked directly).

`05_promoter_gap.sh` lets you exclude a window adjacent to the TSS from motif scanning, so that ubiquitous core-promoter elements (TATA box, Inr) don't drown out the signal from cell-type-specific TF sites further upstream:

![Promoter scan with vs without gap](docs/figures/promoter-gap-comparison-en.svg)

<a id="en-8"></a>

## 8. Web app deployment

The full stack is FastAPI + Celery + Next.js + nginx + redis as a docker-compose deployment. All commands run from repo root:

```bash
make up          # build images + bring the stack up (5–10 min on first run)
make logs        # tail logs from all services
make ps          # container status
make down        # stop the stack
make rebuild     # rebuild images after editing app code
```

When `make up` finishes, open **http://localhost:5960** — nginx fronts the frontend (`/`) and the API (`/api/...`).

| Service  | Role                           | Host port       |
| -------- | ------------------------------ | --------------- |
| nginx    | reverse proxy                  | **5960**        |
| frontend | Next.js                        | (internal 3000) |
| api      | FastAPI                        | (internal 8000) |
| worker   | Celery worker                  | —               |
| redis    | Celery broker + result backend | —               |

**Bind mounts** (host edits take effect without rebuild):

- `apps/pmet_backend/` → `/app/pmet_backend` (uvicorn auto-reloads; worker needs `make restart-worker`)
- `pipeline/` → `/app/pipeline`
- `data/` → `/app/data`
- `deploy/result/` → `/app/result`

The frontend image is baked at build time (no bind mount); frontend edits require `make rebuild` (or `cd deploy && make rebuild-frontend` for just the frontend).

### First-time data setup

The pre-computed per-species indexes (GBs) are not shipped in the repo. Run once on the host:

```bash
cd deploy && make fetch-data
```

This downloads TAIR10 into `data/` and per-species indexes into `data/app/indexing/` (16 GB if you grab everything). The `data/app/` namespace keeps web-app inputs separate from CLI/core demo data in `data/indexing/{demo,bench}/`.

### Email notifications

The backend sends per-task completion emails. Put SMTP credentials in `data/configure/email_credential.txt` (gitignored — **never commit it**). 5 lines: `username` / `password` (Gmail app-password recommended) / `from_address` / `smtp_server` / `port`.

Finer deploy targets: `cd deploy && make help`.

<a id="en-9"></a>

## 9. Tests & regression baseline

Two independent verification tracks:

- [`tests/audit/`](tests/audit/) — **runs every workflow** against canonical inputs and renders the dict→template into [`docs/workflows/*.md`](docs/workflows/). Every verification check produces PASS / WARN / FAIL, with SHA-256 anchors as regression sentinels. Run one or all with `python3 tests/audit/generate.py [<name> ...]`; wall time: pair_only ~15 s, intervals ~16 s, promoter ~2 min, elements ~5 min.
- [`tests/baseline/`](tests/baseline/) — fingerprints the lower-level scripts (`apps/cli/scripts/*`); `make baseline` re-captures, `tests/baseline/fingerprints.txt` is the anchor to diff against.

`apps/pmet_backend/test_api.py` is covered separately by pytest inside the backend's docker image.

<a id="en-10"></a>

## 10. Migration history

This repo is the union of three previously-separate directories (`PMET_project`, `pmet_analysis_pipeline`, `pmet_shiny_app`), unified at tag `v0.1.0-monorepo`. See `tests/baseline/README.md` for the fingerprints used to verify no regressions across the move.

---

<a id="cn"></a>

## 目录

|                                |                        |                              |
| ------------------------------ | ---------------------- | ---------------------------- |
| [1. 这个工具做什么](#cn-1)     | [5. 关键参数](#cn-5)   | [8. Web 部署](#cn-8)         |
| [2. 安装与 Quick start](#cn-2) | [6. 输出格式](#cn-6)   | [9. 测试与回归基线](#cn-9)   |
| [3. 算法：两步走](#cn-3)       | [7. 仓库结构](#cn-7)   | [10. 迁移历史](#cn-10)       |
| [4. 四种工作流](#cn-4)         | [→ Jump to English](#en) |                            |

<a id="cn-1"></a>

## 1. 这个工具做什么

PMET 回答一个问题：

> 在一组你感兴趣的基因里，哪些转录因子（TF）**成对地**出现在启动子（或其它指定区域）中，比随机期望更频繁？

成对出现意味着两个 TF 可能在物理上协同调控同一组基因 — 大多数 TF 不单独结合 DNA，需要 partner 挨着绑定才能产生调控输出。PMET 找出这些 TF pair。

<a id="cn-2"></a>

## 2. 安装与 Quick start

```bash
make build       # 编译 C/C++ 引擎到 ./build/
make demo        # 跑 indexing + pairing 的 demo（data/*/demo 数据）
make baseline    # 抓取回归 fingerprint 到 tests/baseline/fingerprints.txt
```

第一次跑前可能需要拉 TAIR10 等公共数据：

```bash
bash pipeline/workflows/cli/00_env_check.sh   # 检查依赖工具，如缺则下载 TAIR10
```

R heatmap 阶段需要 `Rscript` 和 [`pipeline/r/install_packages.R`](pipeline/r/install_packages.R) 列出的包；缺 R 不影响 motif_output.txt 的产出，只跳过 heatmap。

<a id="cn-3"></a>

## 3. 算法：两步走

![PMET 算法：两步走](docs/figures/algorithm-two-stages-cn.svg)

**Step 1 — Indexing（同型搜索）**：在你指定的区域（启动子/UTR/CDS/...）上用 FIMO 扫描 MEME 文件里每一个 motif，对每个 motif 用 binomial 阈值筛出全基因组 top n 个 hit，对每个基因保留至多 k 个最佳 hit，输出一个**索引**。索引一旦建好就可以反复用。

**Step 2 — Pairing（异型配对）**：读 step 1 的索引，对你的基因列表做成对富集检验。每一对 motif (m₁, m₂) 在你的基因群里共同出现的次数，相对于全基因组背景，是不是显著偏高？用**超几何检验**，输出 p-value 和 BH/Bonferroni 校正后的 adjusted p-value。

<a id="cn-4"></a>

## 4. 四种工作流

四个主脚本都在 [`pipeline/workflows/`](pipeline/workflows/)。其中三个产生 homotypic 索引，第四个 `pair_only.sh` 复用已有索引。每个都对应 [`docs/workflows/`](docs/workflows/) 下一份审计 + 说明文档（含 step-by-step、生物学意图、回归 SHA 锚）。

![PMET 工作流总览](docs/figures/workflow-overview-cn.svg)

### 4.1 启动子 — `promoter.sh` &nbsp;[详细](docs/workflows/promoter.md)

最经典的场景。扫描每个基因 TSS 上游 ~1 kb（默认 + 5'UTR）。

```bash
bash pipeline/workflows/promoter.sh                                    # 用默认 TAIR10 + Franco-Zorrilla
bash pipeline/workflows/promoter.sh -s my_genome.fa -a my_annot.gff3   # 换物种
```

### 4.2 任意区间 — `intervals.sh` &nbsp;[详细](docs/workflows/intervals.md)

当分析单元不是「基因的启动子」而是 ATAC/ChIP peak、保守元件等任意 FASTA 区段时使用。FASTA record 名（如 `chr1:1234-5678`）就是分析单元；脚本自动 sanitize header 里的 `:`（FIMO 和二进制 fimohits 不认）。

```bash
bash pipeline/workflows/intervals.sh \
    -s data/demos/intervals/intervals.fa \
    -m data/demos/intervals/motif.meme \
    -g data/demos/intervals/peaks.txt
```

### 4.3 基因组元素 — `elements.sh` &nbsp;[详细](docs/workflows/elements.md)

不局限在启动子，对 GFF3 任意 feature type 建索引：5'UTR / 3'UTR / CDS / mRNA / exon。下图最上面一行是基因在染色体上的物理结构，下面 5 行对应 5 种 `-e` 选项，**高亮**部分就是该选项实际索引的区间：

![每种 -e 选项索引的区域](docs/figures/gff3-element-options-cn.svg)

GFF3 中 `mRNA` feature 是 **primary transcript**（初始转录本），即 TSS 到 TTS 全段，**包含 intron**。这不同于"成熟 mRNA"（剪接后只剩 exon）的概念，GFF3 并不直接编码成熟 mRNA。

| GFF3 类型         | PMET 索引的物理区间                   | 说人话                            |
| ----------------- | ------------------------------------- | --------------------------------- |
| `mRNA`            | TSS → TTS 连续一段，**含 intron**     | 整个基因体，TF 可能在内含子中结合 |
| `CDS`             | 每个编码外显子一段，**不含 intron**   | 只扫翻译成蛋白的片段              |
| `exon`            | 每个外显子一段（含 UTR 部分的外显子） | 比 CDS 宽，多扫了含 UTR 的 exon   |
| `five_prime_UTR`  | 5' UTR 片段                           | CDS 上游的不翻译前导              |
| `three_prime_UTR` | 3' UTR 片段                           | CDS 下游的不翻译尾部              |

一个基因可能多 isoform，提供两种聚合策略：

| `-s`      | 含义                                    |
| --------- | --------------------------------------- |
| `longest` | 每基因选指定 element 总长最大的 isoform |
| `merged`  | 把所有 isoform 在基因组上的并集作为一段 |

![Isoform 聚合策略对比](docs/figures/element-structure-strategies.svg)

`-e mRNA` 时还有 `-m Yes\|No` 控制 UTR：

| 命令                 | 得到的区域                                        |
| -------------------- | ------------------------------------------------- |
| `-e mRNA -m Yes`     | 完整 mRNA（5'UTR + CDS + 3'UTR），每基因一段      |
| `-e mRNA -m No`      | mRNA 减去 UTR（CDS span，每基因一段）             |
| `-e CDS` / `-e exon` | 每个 CDS 片段 / 外显子单独成段（无 isoform 聚合） |

`-m` 仅在 `-s longest -e mRNA` 时有效，其他组合下被忽略并提示。

多 fragment 元件（`-e CDS / exon` 等）会在内部用 `__GENE__N` 后缀给每个 fragment 打标，让 FIMO 把它们当独立序列扫描，最后再合并回基因层级：

![Fragment tagging 与 gene-level collapse](docs/figures/element-fragment-tagging.svg)

```bash
bash pipeline/workflows/elements.sh -s longest -e 5UTR -t 8
bash pipeline/workflows/elements.sh -s longest -e mRNA -m Yes -t 8
```

### 4.4 复用已有索引 — `pair_only.sh` &nbsp;[详细](docs/workflows/pair_only.md)

跳过昂贵的 indexing，对已有索引换基因列表重跑 pairing。Web 的 `promoters_pre` 模式背后也是这个脚本。

```bash
bash pipeline/workflows/pair_only.sh \
    -d results/promoter/01_homotypic \
    -g data/genes/my_new_clusters.txt \
    -o results/repaired
```

<a id="cn-5"></a>

## 5. 关键参数

每个脚本都有 `-h`，里面是权威清单（含默认值）。下表只列**容易踩坑的**几个 — 不同脚本中**短选项字母不一致**，照着记。

### 同型阶段 (indexing)

| 参数                                          | promoter | intervals | elements    |
| --------------------------------------------- | -------- | --------- | ----------- |
| topn / 每 motif 全基因组保留前 n（默认 5000） | `-n`     | `-n`      | (固定)      |
| maxk / 每基因保留至多 k 个 hit（默认 5）      | `-k`     | `-k`      | (固定)      |
| FIMO p-value 阈值（默认 0.05）                | `-f`     | `-f`      | (固定)      |
| 启动子长度 (bp，默认 1000)                    | `-p`     | —         | —           |
| 是否含 5'UTR（默认 Yes）                      | `-u`     | —         | —           |
| 启动子重叠（默认 NoOverlap）                  | `-v`     | —         | —           |
| 元素类型                                      | —        | —         | `-e` (必填) |
| isoform 策略（默认 `longest`）                | —        | —         | `-s`        |

`elements.sh` 故意只暴露 `-s -e -m -t -d` 五个核心 flag，其它沿用 `_pmet_index_element.sh` 的默认值；要细调请直接调那个底层脚本。

### 异型阶段 (pairing)

| 参数                                  | promoter    | intervals   | elements                  | pair_only   |
| ------------------------------------- | ----------- | ----------- | ------------------------- | ----------- |
| IC 阈值（过滤低信息量 motif，默认 4） | **`-c`**    | **`-c`**    | (固定)                    | **`-i`**    |
| 基因列表                              | `-g` (必填) | `-g` (必填) | (`data/genes/*.txt` 全跑) | `-g` (必填) |
| 线程数（默认 4，pair_only 见 `-h`）   | `-t`        | `-t`        | `-t`                      | `-t`        |

> ⚠️ IC 阈值在 `promoter.sh / intervals.sh` 是 `-c`，在 `pair_only.sh` 是 `-i` — 历史遗留，未统一。`promoter.sh` 的 `-i` 实际是 `gff3_id_key`（GFF3 attribute key）。

<a id="cn-6"></a>

## 6. 输出格式

最终产物 `motif_output.txt`，TAB 分隔 11 列：

```
Cluster  Motif1  Motif2  n_genes_with_both  total_with_both  n_in_cluster  raw_p  adj_p_BH  adj_p_Bonf  adj_p_global  genes
cortex   AHL12   AHL12_2 3                  248              442           0.784  0.784     1.0         1.0           AT1G05680;AT2G20120;AT4G02170;
```

按 `adj_p_BH` 排序。每行回答：在 cluster `cortex` 中，motif pair `(AHL12, AHL12_2)` 的共同出现是否是显著协同信号。

<a id="cn-7"></a>

## 7. 仓库结构

```
core/          C/C++ 引擎（indexing, pairing）+ CMake
pipeline/      bash + python + R 共享工具；workflows
apps/
  cli/             命令行入口与 helper
  pmet_backend/    FastAPI + Celery worker
  pmet_frontend/   Next.js
deploy/        docker-compose、nginx、Dockerfile
data/          demo / fixture（大数据 gitignored）
tests/
  audit/         workflow 审计 + 自动渲染 docs/workflows/*.md
  baseline/      回归 fingerprint
  integration/   端到端测试
docs/
legacy/        归档的历史代码
build/         编译产物（gitignored）
results/       脚本输出（gitignored）
```

辅助脚本在 [`pipeline/workflows/cli/`](pipeline/workflows/cli/)：`00_env_check.sh`（依赖检查 + 下载 TAIR10）、`01_perf_cpu.sh` / `02_perf_params.sh`（perf benchmark）、`05_promoter_gap.sh`（启动子 gap 分析，见下图）、`_pmet_index_element.sh`（被 `elements.sh` source 的 indexing 子流程库，不直接调用）。

`05_promoter_gap.sh` 允许在 TSS 紧邻区域排除一段长度（gap），把扫描限定在更上游的调控区，避开 TATA box / Inr 这类几乎所有基因共用的核心启动子元件：

![启动子扫描有无 gap 对比](docs/figures/promoter-gap-comparison-cn.svg)

<a id="cn-8"></a>

## 8. Web 部署

FastAPI + Celery + Next.js + nginx + redis 的 docker-compose 栈，所有命令从 repo root 跑：

```bash
make up          # 构建镜像 + 起栈（首次 5–10 分钟）
make logs        # 跟所有服务日志
make ps          # 容器状态
make down        # 停栈
make rebuild     # 改了代码后重建
```

`make up` 完成后开 **http://localhost:5960** — nginx 反代前端 (`/`) 和 API (`/api/...`)。

| 服务     | 角色                           | host port   |
| -------- | ------------------------------ | ----------- |
| nginx    | reverse proxy                  | **5960**    |
| frontend | Next.js                        | (内部 3000) |
| api      | FastAPI                        | (内部 8000) |
| worker   | Celery worker                  | —           |
| redis    | Celery broker + result backend | —           |

**Bind mount**（host 改文件即生效，无需 rebuild）：

- `apps/pmet_backend/` → `/app/pmet_backend`（uvicorn 自动 reload；worker 需 `make restart-worker`）
- `pipeline/` → `/app/pipeline`
- `data/` → `/app/data`
- `deploy/result/` → `/app/result`

前端镜像在 build 时 baked，不挂载 — 改前端代码要 `make rebuild`（或 `cd deploy && make rebuild-frontend` 只重建前端）。

### 首次数据准备

预计算的物种索引（GB 级）不随 repo 走。host 上跑一次：

```bash
cd deploy && make fetch-data
```

TAIR10 下载到 `data/`，per-species 索引下载到 `data/app/indexing/`（全要 16 GB）。`data/app/` 命名空间用来把 Web 应用的输入和 CLI / core 的 demo / bench 数据（位于 `data/indexing/{demo,bench}/`）分开。

### 邮件通知

后端任务完成后发邮件，SMTP 凭据放 `data/configure/email_credential.txt`（gitignored，**不要提交**）。5 行：`username` / `password`（推荐 Gmail app password）/ `from_address` / `smtp_server` / `port`。

更细的 deploy target：`cd deploy && make help`。

<a id="cn-9"></a>

## 9. 测试与回归基线

两条独立的验证轨道：

- [`tests/audit/`](tests/audit/) — **每个 workflow 跑一遍**真实输入，用 dict→template 渲染出 [`docs/workflows/*.md`](docs/workflows/)。每条 verification check 都给 PASS/WARN/FAIL，SHA-256 anchor 当回归哨兵。`python3 tests/audit/generate.py [<name> ...]` 跑一个或全部；wall time pair_only ~15 s，intervals ~16 s，promoter ~2 min，elements ~5 min。
- [`tests/baseline/`](tests/baseline/) — 对底层脚本（`apps/cli/scripts/*`）的输出做 fingerprint，`make baseline` 重新捕获，`tests/baseline/fingerprints.txt` 当 anchor 对比。

`apps/pmet_backend/test_api.py` 由后端 docker 镜像里的 pytest 单独覆盖。

<a id="cn-10"></a>

## 10. 迁移历史

本仓库由三个独立目录（`PMET_project`、`pmet_analysis_pipeline`、`pmet_shiny_app`）合并而来，合并点是 tag `v0.1.0-monorepo`。`tests/baseline/README.md` 详细记录了用于验证合并前后无回归的 fingerprint。
