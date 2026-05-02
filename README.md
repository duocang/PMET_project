# PMET — Paired Motif Enrichment Tool

**[English](#en) · [汉文](#cn)**

---

<a id="en"></a>

## Contents

|                                       |                                |                                                |
| ------------------------------------- | ------------------------------ | ---------------------------------------------- |
| [1. What this tool does](#en-1)       | [5. Key parameters](#en-5)     | [8. Web app deployment](#en-8)                 |
| [2. Install & quick start](#en-2)     | [6. Output format](#en-6)      | [9. Tests & regression baseline](#en-9)        |
| [3. The algorithm: two stages](#en-3) | [7. Repository layout](#en-7)  | [10. Troubleshooting — first-time gotchas](#en-10) |
| [4. The four workflows](#en-4)        | [→ 跳到汉文](#cn)              | [11. Migration history](#en-11)                |

<a id="en-1"></a>

## 1. What this tool does

PMET answers one question:

> Across a gene set you care about, which transcription factor (TF) motifs **co-occur in pairs** in their promoters (or any other region you specify) more often than chance?

Co-occurrence suggests two TFs may physically cooperate to regulate the same gene set — most TFs do not bind DNA alone; they need a partner adjacent on the sequence to drive a regulatory output. PMET finds those pairs.

**Two ways to use it.** As a CLI: invoke one of the four workflow
scripts under [`scripts/workflows/`](scripts/workflows/) directly
(see [§4](#en-4)). As a web app: a docker stack (FastAPI + Celery +
Next.js + redis + nginx) that takes user submissions through the
same workflow scripts. The user-facing flow is

> browser submits → API drops a job on redis → worker pulls it,
> runs the workflow under [`scripts/workflows/`](scripts/workflows/),
> writes outputs to `results/app/<task_id>/` → email goes out with
> a download link

— see [§8](#en-8) for the deployment.

> **New to motif analysis?** [`docs/glossary.md`](docs/glossary.md)
> has one-paragraph definitions for the domain words this README
> throws around (motif vs hit, homotypic vs heterotypic, IC threshold,
> raw p vs adj_p_BH, …).

<a id="en-2"></a>

## 2. Install & quick start

The fastest way to convince yourself PMET works on your machine — and
to see what its output actually looks like — is to run the bundled
demo. **Three commands, ~30 seconds end-to-end.** No real data needed;
the demo inputs ship in the repo.

```bash
make build                                          # compile C/C++ engines into ./build/  (~30 s, one-time)
make demo                                           # run indexing + pairing on data/demos/  (~5 s)
head results/cli/demo/pairing/motif_output.txt      # ← the actual answer; see §6 for how to read it
```

You should see a TAB-separated table with one row per
`(cluster, motif pair)`. [§6](#en-6) walks through what each column
means and what counts as a "significant" pair; [§4](#en-4) covers the
four workflows you'll reach for once you graduate to real data.

### What you need installed

System tools the workflows assume on `$PATH`. `00_env_check.sh`
sanity-checks the same list:

| Tool | Min version | Used by | Notes |
|---|---|---|---|
| `cmake` | 3.10 | `make build` | configures the C/C++ engines |
| C/C++ compiler | C99 + C++17 | `make build` | gcc 7+ or clang 6+ |
| `bedtools` | 2.30+ recommended | promoter / intervals / elements | needs `-s` strand support (any modern build has it) |
| `samtools` | 1.10+ | promoter / elements | for `faidx` |
| GNU `parallel` | any | promoter / elements | per-cluster fan-out |
| MEME suite (`fasta-get-markov`, `fimo`) | 5.0+ | indexing | scans motifs against sequence |
| `python3` | 3.8+ | helper scripts + backend | backend deps in `apps/pmet_backend/requirements.txt` |
| `R` + `Rscript` | 4.0+ | heatmap stage only | packages: see [`scripts/r/install_packages.R`](scripts/r/install_packages.R). Without R the `motif_output.txt` is still produced; only the heatmap step is skipped. |

For the web stack ([§8](#en-8)) you also need:

| Tool | Min version |
|---|---|
| `docker` | 20.10+ |
| `docker compose` | v2.x (the `docker compose` plugin, not standalone `docker-compose`) |
| `node` + `npm` | 18.17+ (Next.js 14 requirement) — only if you iterate on the frontend outside docker |

Wall-clock expectations for canonical inputs (full table at
[`docs/perf/runtime_reference.md`](docs/perf/runtime_reference.md)):
demo ~5 s, `make test` (core + unit + integration) ~10 s, `make
baseline` ~30 s, `make test-audit` ~7 min, a TAIR10 promoter scan
with CIS-BP2 on 16 cores ~30 min.

### Real-data prerequisites

Anything beyond the bundled demo needs public datasets. Two tiers,
fetch what you need:

```bash
# Tier 1 — TAIR10 reference only (~250 MB), needed by promoter.sh / elements.sh:
bash scripts/workflows/cli/00_env_check.sh    # also checks tool versions on your $PATH

# Tier 2 — TAIR10 + 21-species pre-computed indexes (~16 GB, run ONCE):
make fetch-data                                # needed by pair_only.sh against canonical
                                               # species and by the web app's
                                               # promoters_pre mode
```

The R heatmap stage needs `Rscript` plus the packages listed in
[`scripts/r/install_packages.R`](scripts/r/install_packages.R);
without R the `motif_output.txt` is still produced — only the heatmap
step is skipped.

### Save yourself an hour

If you're new, [§10 Troubleshooting](#en-10) lists the six things that
trip up most first-time users (chromosome-name mismatches between
GFF3 and FASTA, FIMO vs `:` in headers, gene-list format, missing R
packages, port conflicts, stuck "running" tasks). Skim it before
running on your own data.

<a id="en-3"></a>

## 3. The algorithm: two stages

![PMET algorithm: two stages](docs/figures/algorithm-two-stages-en.svg)

**Step 1 — Indexing (homotypic)**: scan every motif in the MEME file across your chosen region (promoter / UTR / CDS / ...) using FIMO. For each motif, a binomial threshold keeps the top n hits genome-wide; per-gene we keep at most k best hits. The result is an **index** that can be reused.

**Step 2 — Pairing (heterotypic)**: read the step-1 index, run a pair-enrichment test on your gene list. For every motif pair (m₁, m₂), is their co-occurrence in your cluster significantly higher than the genome-wide background? The test is a **hypergeometric**, with raw and BH/Bonferroni-adjusted p-values.

<a id="en-4"></a>

## 4. The four workflows

The four main scripts live under [`scripts/workflows/`](scripts/workflows/). Three of them produce a homotypic index, the fourth (`pair_only.sh`) re-uses one. Each has a corresponding audit + reference doc under [`docs/workflows/`](docs/workflows/) (step-by-step, biological intent, regression SHA anchors).

![PMET workflow overview](docs/figures/workflow-overview-en.svg)

### 4.1 Promoters — `promoter.sh` &nbsp;[details](docs/workflows/promoter.md)

The classic case. Scan ~1 kb upstream of every TSS (with 5'UTR included by default).

```bash
bash scripts/workflows/promoter.sh                                    # uses default TAIR10 + Franco-Zorrilla
bash scripts/workflows/promoter.sh -s my_genome.fa -a my_annot.gff3   # any other species
```

### 4.2 Arbitrary intervals — `intervals.sh` &nbsp;[details](docs/workflows/intervals.md)

Use this when your unit of analysis is not "the promoter of a gene" but ATAC/ChIP peaks, conserved elements, or any other FASTA region. Each FASTA record name (e.g. `chr1:1234-5678`) is one analysis unit; the script auto-sanitises `:` in headers (FIMO and the binary fimohits format don't accept it).

```bash
bash scripts/workflows/intervals.sh \
    -s data/demos/intervals/indexing/intervals.fa \
    -m data/demos/intervals/indexing/motif.meme \
    -g data/demos/intervals/indexing/peaks.txt
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
bash scripts/workflows/elements.sh -s longest -e 5UTR -t 8
bash scripts/workflows/elements.sh -s longest -e mRNA -m Yes -t 8
```

### 4.4 Re-pair an existing index — `pair_only.sh` &nbsp;[details](docs/workflows/pair_only.md)

Skip the expensive indexing stage; against an existing index, swap in a new gene list and rerun pairing only. The web app's `promoters_pre` mode is backed by this same script.

```bash
bash scripts/workflows/pair_only.sh \
    -d results/cli/promoter/01_homotypic \
    -g data/genes/my_new_clusters.txt \
    -o results/cli/repaired
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

**MinHash prefilter (opt-in).** `pair_parallel` ships a MinHash-based prefilter (`-m <K>`) that can skip pair candidates with low estimated gene-set intersection. The default is off — calibration on CIS-BP2 (see [docs/perf/minhash_calibration.md](docs/perf/minhash_calibration.md)) did not find a setting that gave meaningful speedup without a non-trivial false-negative rate. Power users on bigger hardware can enable it with `PMET_MINHASH_MIN=N`.

<a id="en-6"></a>

## 6. Output format

The terminal product is `motif_output.txt`, TAB-separated, 11 columns,
sorted by `Adjusted p-value (BH)`. Each row answers: in this cluster,
is this motif pair co-occurring more than chance?

```
Cluster   Motif 1  Motif 2     #both/cluster  #both/total  cluster_size   raw_p   adj_p (BH)  adj_p (Bonf)  adj_p (Global)  Genes
cortex    AHL12    AHL12_2     3              248          442            0.784   0.784       1.0           1.0             AT1G05680;AT2G20120;AT4G02170;
```

(The real header line uses verbose names like `Number of genes in
cluster with both motifs`; the table above abbreviates for fit.)

### How to read one row

Take the `cortex / AHL12 / AHL12_2` row above and translate to plain
words:

> The `cortex` cluster has **442** genes. Of those, only **3** had
> both AHL12 and AHL12_2 hits in their promoter. Across the entire
> indexed background (every gene with a usable promoter, the universe
> the workflow scanned), **248** genes had both motifs. The
> hypergeometric test asks: is `3 / 442` (cortex hit rate) higher
> than `248 / N` (background hit rate)? Answer: raw p = **0.78**,
> BH-adjusted p = **0.78** → no — **AHL12 and AHL12_2 are NOT a
> cooperative pair for `cortex`** in this run.

Treat `Adjusted p-value (BH)` as the call:

- `< 0.05` → significantly cooperative pair, worth following up
- `≈ 1.0` (like 0.78 above) → noise, the pair is no more co-occurring
  in this cluster than in the background
- between `0.05` and `~0.5` → suggestive but not significant; might
  be worth re-running with a different IC threshold or a tighter
  gene list

The `Genes` column lists which cluster genes contribute the
co-occurrence — useful when you want to pick concrete biological
examples to validate the pair downstream.

<a id="en-7"></a>

## 7. Repository layout

```
core/          C/C++ engines (indexing, pairing) + CMake
scripts/      shared bash + python + R helpers; workflows
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
results/       run outputs (gitignored): app/ for web tasks, cli/ for pipeline runs
```

Auxiliary scripts under [`scripts/workflows/cli/`](scripts/workflows/cli/): `00_env_check.sh` (dependency check + TAIR10 download), `01_perf_cpu.sh` / `02_perf_params.sh` (perf benchmarks), `05_promoter_gap.sh` (promoter gap analysis — see figure below), `_pmet_index_element.sh` (the indexing sub-pipeline library sourced by `elements.sh` — not invoked directly).

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

| Service           | Role                                                       | Host port       |
| ----------------- | ---------------------------------------------------------- | --------------- |
| nginx             | reverse proxy                                              | **5960**        |
| frontend          | Next.js                                                    | (internal 3000) |
| api               | FastAPI                                                    | (internal 8000) |
| worker            | Celery worker                                              | —               |
| liveness-watchdog | Kills tasks idle > 15 min (no progress.json update)        | —               |
| redis             | Celery broker + result backend                             | —               |

**Bind mounts** (host edits take effect without rebuild):

- `apps/pmet_backend/` → `/app/pmet_backend` (uvicorn auto-reloads; worker needs `make restart-worker`)
- `scripts/` → `/app/scripts`
- `data/` → `/app/data`
- `results/app/` → `/app/results` (single canonical location for web-app task outputs; same path whether the backend runs in docker or locally)

The frontend image is baked at build time (no bind mount); frontend edits require `make rebuild` (or `cd deploy && make rebuild-frontend` for just the frontend).

### First-time data setup

The web app's `promoters_pre` mode reads pre-computed per-species indexes that are not shipped in the repo. Run `make fetch-data` once on the host before bringing the stack up — see [Quick Start §2](#en-2) for what it downloads and what it's needed for.

### Email notifications

The backend sends per-task completion emails. Put SMTP credentials in `data/configure/email_credential.txt` (gitignored — **never commit it**). 5 lines: `username` / `password` (Gmail app-password recommended) / `from_address` / `smtp_server` / `port`.

### Administrator access

The stack ships with a single-admin auth model — a shared token grants access to "see-all-tasks" plus task-level termination. Regular users can only look up their own tasks by email; admins can see everything, filter, and kill in-flight runs.

**1. Provision the token (once)**

Generate a random token and write it to `data/configure/admin_token.txt` (gitignored — **never commit it**):

```bash
openssl rand -hex 32 > data/configure/admin_token.txt
```

If the file is missing or empty, all admin endpoints return `503 Admin not configured` and the `/admin/login` page tells the user the same. Generating or rotating the token does not need a stack rebuild — `data/configure/` is bind-mounted, the value is hot-read on the next admin API call.

**2. Log in**

Open [http://localhost:5960/admin/login](http://localhost:5960/admin/login), paste the token. The server validates it against the file and sets an httpOnly `pmet_admin` cookie (30-day expiry). After login you land on `/admin/settings`.

**3. What admin mode unlocks**

- **All tasks visible** — `/tasks` lists every task on the server, not just the searched-email's. The search box still works as a quick filter (substring match on email or task ID).
- **Filters** — additional dropdowns appear: status (pending / running / completed / failed / cancelled), mode (promoters / promoters_pre / intervals), date range (from / to). All client-side over the latest 200 tasks.
- **Terminate button** — every pending or running task gets a red `Terminate` button. Click → optional reason prompt → backend marks the task `cancelled`, walks the worker's process tree with `psutil` (SIGTERM, then SIGKILL after 5 s), and emails the user with the reason or a default message.
- **Settings page** — `/admin/settings` toggles `notify_on_submit`. When off, the worker stops sending the per-task "PMET: New Task Submitted" email to the admin. User-facing emails (started / completed / cancelled) are unaffected. The toggle persists in `data/configure/admin_settings.json` and is hot-reloaded.

**4. Sign out**

The `Sign out` button on the settings page deletes the cookie. To rotate the token, replace the contents of `data/configure/admin_token.txt`; existing cookies stop working on the next admin API call.

Finer deploy targets: `cd deploy && make help`.

<a id="en-9"></a>

## 9. Tests & regression baseline

Five tracks at different levels — fastest first. Each has a make target; **`make test` chains the three fast tracks** (core + unit + integration, ~10 s) as the default pre-commit gate.

| Track | Command | What it covers |
|---|---|---|
| Core math kernels (C/C++) | `make test-core` (or `make test-pairing` / `make test-indexing`) | ~96 unit cases over the pure-math pieces of both engines: BH correction, hypergeometric coloc, binomial / Poisson CDF, MinHash sketch, motif-overlap geometry, load-balancing partition, indexing-side string utils. Test binary links the same OBJECT library production uses → tests never drift from what ships. **< 5 s combined.** |
| Repo-wide unit tests (Python / R / bash / TS) | `make test-unit` | Stage-status inference, partial-result API, mail dispatch, error classification, watchdog staleness, list_tasks pagination + filter, heatmap dim cap (R), minhash workflow resolver (bash), frontend Zustand store actions (TypeScript via tsx — auto-skipped if `apps/pmet_frontend/node_modules` absent). **< 5 s.** |
| Pipeline-level integration | `make test-integration` (runs the smoke; see [`tests/integration/README.md`](tests/integration/README.md) for the heavier scripts: `run_pipeline02_one_combo.sh`, `run_pipeline08_ic_sweep.sh`, `test_pipeline02_strand_realdata.sh`, `verify_baseline.sh`, `run_with_verify.sh`) | Smoke invariants (~3 s, no real data needed): bedtools strand-awareness, build_promoters.py uses `-s`, chromosome-name preflight on promoter+anno pipelines, assess_integrity.py handles non-adjacent fragments, optional real-data TAIR10 strand check. The heavier scripts run end-to-end pipelines and need TAIR10 + a built homotypic index; their recorded baselines need recapture (post-monorepo paths). |
| Workflow audit ([`tests/audit/`](tests/audit/)) | `make test-audit` (or `python3 tests/audit/generate.py [<name> ...]` to scope to one) | Runs each workflow against canonical inputs, renders dict→template into [`docs/workflows/*.md`](docs/workflows/), records PASS / WARN / FAIL per verification check, SHA-256 anchors as regression sentinels. pair_only ~15 s, intervals ~16 s, promoter ~2 min, elements ~5 min. **Writes to docs/** — kept out of `make test` for that reason. |
| CLI baseline ([`tests/baseline/`](tests/baseline/)) | `make baseline` | Fingerprints `apps/cli/scripts/*` outputs. `tests/baseline/fingerprints.txt` is the anchor to diff against. **Writes the fingerprint file** — also out of `make test`. |

`apps/pmet_backend/test_api.py` is a 5-stage smoke (imports / TaskCreate / StorageService / PMETExecutor / app load). Run on the host with `python apps/pmet_backend/test_api.py`, or inside the backend image with `cd deploy && make test`.

<a id="en-10"></a>

## 10. Troubleshooting — first-time gotchas

The six things that bite new users most often. Each is a real
support email reduced to a one-line hint:

| Symptom | What's actually wrong | Fix |
|---|---|---|
| Pipeline aborts with `Chromosome name mismatch (gff3='Chr1', fasta='1')` | TAIR10 ships chromosomes as `1, 2, ...`; many other GFF3s use `Chr1, Chr2, ...`. The two files have to agree. | Rename one side, or pass matching files. The `promoter` / `elements` / `02_perf_params` workflows all have a preflight that catches this *before* they waste an hour on FIMO. |
| `intervals.sh` errors on a header containing `:` (e.g. `chr1:1234-5678`) | FIMO and the binary `fimohits` format don't accept `:` in FASTA record names. | `intervals.sh` auto-sanitises `:` → `_`. If you still hit this, you're calling the lower-level binary directly — go through the workflow script instead. |
| Pairing complains about an empty / wrong gene list | The gene list is **two columns** (`cluster_name<TAB>gene_id`), not one. | See [`data/demos/promoters/pairing/demo`](data/demos/promoters/pairing/demo) for the canonical shape; [`data/genes/genes_cell_type_treatment.txt`](data/genes/genes_cell_type_treatment.txt) is a real-world example. |
| `motif_output.txt` is produced but no heatmap appears | R or one of its packages (`ggplot2`, `RColorBrewer`, `pheatmap`) is missing. | The heatmap stage is best-effort — install with `Rscript scripts/r/install_packages.R` and rerun, or just consume `motif_output.txt` directly and skip the heatmap. |
| `make up` says `port 5960 already in use` | Another container or a non-docker process is bound to 5960. | The Makefile auto-stops leftover docker containers on 5960; if it still fails, the bound process is non-docker — the error message lists the PID. Free it, or change the host port in [`deploy/docker-compose.yml`](deploy/docker-compose.yml). |
| Web task is stuck on "running" forever | The worker was SIGKILLed mid-run and never wrote the final status. | The `liveness-watchdog` container marks any task with no `progress.json` update for 15 min as `failed`. To rescue earlier: `cd deploy && make restart-worker` and resubmit. |

If none of these match, the next places to look are
[`tests/integration/run_smoke.sh`](tests/integration/run_smoke.sh)
(catches most environment / convention regressions in ~3 s) and the
backend logs (`make logs` in repo root, then filter by service).

<a id="en-11"></a>

## 11. Migration history

This repo is the union of three previously-separate directories
(`PMET_project`, `pmet_analysis_pipeline`, `pmet_shiny_app`), unified
at tag `v0.1.0-monorepo`. See [`tests/baseline/README.md`](tests/baseline/README.md)
for the fingerprints used to verify no regressions across the move.

---

<a id="cn"></a>

## 目录

|                                |                        |                                       |
| ------------------------------ | ---------------------- | ------------------------------------- |
| [1. 这个工具做什么](#cn-1)     | [5. 关键参数](#cn-5)   | [8. Web 部署](#cn-8)                  |
| [2. 安装与 Quick start](#cn-2) | [6. 输出格式](#cn-6)   | [9. 测试与回归基线](#cn-9)            |
| [3. 算法：两步走](#cn-3)       | [7. 仓库结构](#cn-7)   | [10. 排错 —— 新人最先撞的几堵墙](#cn-10) |
| [4. 四种工作流](#cn-4)         | [→ Jump to English](#en) | [11. 迁移历史](#cn-11)             |

<a id="cn-1"></a>

## 1. 这个工具做什么

PMET 回答一个问题：

> 在一组你感兴趣的基因里，哪些转录因子（TF）**成对地**出现在启动子（或其它指定区域）中，比随机期望更频繁？

成对出现意味着两个 TF 可能在物理上协同调控同一组基因 — 大多数 TF 不单独结合 DNA，需要 partner 挨着绑定才能产生调控输出。PMET 找出这些 TF pair。

**两种用法。** CLI：直接调
[`scripts/workflows/`](scripts/workflows/) 下四个 workflow 脚本之一
（见 [§4](#cn-4)）。Web 应用：一个 docker 栈（FastAPI + Celery +
Next.js + redis + nginx），通过同一套 workflow 脚本接受用户提交。
面向用户的链路是

> 浏览器提交 → API 把任务扔到 redis 队列 → worker 捡起来跑
> [`scripts/workflows/`](scripts/workflows/) 下的对应脚本 → 输出写
> `results/app/<task_id>/` → 邮件给用户发下载链接

—— 部署细节见 [§8](#cn-8)。

> **第一次接触 motif 分析？** [`docs/glossary.md`](docs/glossary.md)
> 给本 README 用到的领域词都做了一段定义（motif vs hit、同型 vs 异
> 型、IC 阈值、raw p vs adj_p_BH …）。

<a id="cn-2"></a>

## 2. 安装与 Quick start

最快说服你自己 PMET 在这台机器上能跑、并且亲眼看一眼它的输出长什么
样的办法 —— 跑一遍自带 demo。**三条命令，端到端 ~30 秒。** 不需要
任何真实数据，demo 输入跟仓库一起走。

```bash
make build                                          # 编译 C/C++ 引擎到 ./build/  (~30 秒，一次性)
make demo                                           # 跑 data/demos/ 的 indexing + pairing  (~5 秒)
head results/cli/demo/pairing/motif_output.txt      # ← 真正的答案；怎么读见 §6
```

应该看到一张 TAB 分隔的表，每行一个 `(cluster, motif 对)`。
[§6](#cn-6) 讲每列什么意思、什么算"显著协同"；[§4](#cn-4) 讲跑真实
数据时该挑哪个 workflow。

### 需要装的工具

workflow 假定在 `$PATH` 上的系统工具。`00_env_check.sh` 会做同样
一份 sanity check：

| 工具 | 最低版本 | 谁用 | 说明 |
|---|---|---|---|
| `cmake` | 3.10 | `make build` | 配置 C/C++ 引擎 |
| C/C++ 编译器 | C99 + C++17 | `make build` | gcc 7+ 或 clang 6+ |
| `bedtools` | 推荐 2.30+ | promoter / intervals / elements | 需要 `-s` strand 支持（任何现代构建都有） |
| `samtools` | 1.10+ | promoter / elements | 用 `faidx` |
| GNU `parallel` | 任意 | promoter / elements | per-cluster fan-out |
| MEME suite（`fasta-get-markov`、`fimo`） | 5.0+ | indexing | motif 对序列扫描 |
| `python3` | 3.8+ | helper 脚本 + 后端 | 后端依赖在 `apps/pmet_backend/requirements.txt` |
| `R` + `Rscript` | 4.0+ | 仅 heatmap 阶段 | 包列表见 [`scripts/r/install_packages.R`](scripts/r/install_packages.R)。缺 R 不影响 `motif_output.txt`，只跳过 heatmap。 |

跑 web 栈（[§8](#cn-8)）还要：

| 工具 | 最低版本 |
|---|---|
| `docker` | 20.10+ |
| `docker compose` | v2.x（`docker compose` 子命令，不是独立的 `docker-compose`） |
| `node` + `npm` | 18.17+（Next.js 14 要求）—— 只在你想脱开 docker 改前端时才用 |

canonical 输入的耗时预期（完整表见
[`docs/perf/runtime_reference.md`](docs/perf/runtime_reference.md)）：
demo ~5 秒，`make test`（core + unit + integration）~10 秒，
`make baseline` ~30 秒，`make test-audit` ~7 分钟，TAIR10 启动子扫描
+ CIS-BP2 16 核 ~30 分钟。

### 跑真实数据需要什么

非 demo 的任何运行都要拉公共数据集。两档，按需选：

```bash
# Tier 1 —— 只拉 TAIR10 参考（~250 MB），promoter.sh / elements.sh 够用：
bash scripts/workflows/cli/00_env_check.sh    # 顺带检查 $PATH 上的工具版本

# Tier 2 —— TAIR10 + 21 物种预计算索引（~16 GB，跑一次就够）：
make fetch-data                                # pair_only.sh 跑 canonical 物种、
                                               # web app 的 promoters_pre 模式
                                               # 都依赖这个
```

R heatmap 阶段需要 `Rscript` 加
[`scripts/r/install_packages.R`](scripts/r/install_packages.R) 列出的
包；缺 R 不影响 `motif_output.txt` 的产出，只跳过 heatmap。

### 帮你省一小时

新人请先扫一眼 [§10 排错](#cn-10)，那里列了新手最容易撞的 6 堵墙
（GFF3 与 FASTA 染色体名不一致、FIMO 不认 header 里的 `:`、gene
list 格式、缺 R 包、5960 端口被占、任务卡在 running）。跑自己数据
之前先看，能救一小时。

<a id="cn-3"></a>

## 3. 算法：两步走

![PMET 算法：两步走](docs/figures/algorithm-two-stages-cn.svg)

**Step 1 — Indexing（同型搜索）**：在你指定的区域（启动子/UTR/CDS/...）上用 FIMO 扫描 MEME 文件里每一个 motif，对每个 motif 用 binomial 阈值筛出全基因组 top n 个 hit，对每个基因保留至多 k 个最佳 hit，输出一个**索引**。索引一旦建好就可以反复用。

**Step 2 — Pairing（异型配对）**：读 step 1 的索引，对你的基因列表做成对富集检验。每一对 motif (m₁, m₂) 在你的基因群里共同出现的次数，相对于全基因组背景，是不是显著偏高？用**超几何检验**，输出 p-value 和 BH/Bonferroni 校正后的 adjusted p-value。

<a id="cn-4"></a>

## 4. 四种工作流

四个主脚本都在 [`scripts/workflows/`](scripts/workflows/)。其中三个产生 homotypic 索引，第四个 `pair_only.sh` 复用已有索引。每个都对应 [`docs/workflows/`](docs/workflows/) 下一份审计 + 说明文档（含 step-by-step、生物学意图、回归 SHA 锚）。

![PMET 工作流总览](docs/figures/workflow-overview-cn.svg)

### 4.1 启动子 — `promoter.sh` &nbsp;[详细](docs/workflows/promoter.md)

最经典的场景。扫描每个基因 TSS 上游 ~1 kb（默认 + 5'UTR）。

```bash
bash scripts/workflows/promoter.sh                                    # 用默认 TAIR10 + Franco-Zorrilla
bash scripts/workflows/promoter.sh -s my_genome.fa -a my_annot.gff3   # 换物种
```

### 4.2 任意区间 — `intervals.sh` &nbsp;[详细](docs/workflows/intervals.md)

当分析单元不是「基因的启动子」而是 ATAC/ChIP peak、保守元件等任意 FASTA 区段时使用。FASTA record 名（如 `chr1:1234-5678`）就是分析单元；脚本自动 sanitize header 里的 `:`（FIMO 和二进制 fimohits 不认）。

```bash
bash scripts/workflows/intervals.sh \
    -s data/demos/intervals/indexing/intervals.fa \
    -m data/demos/intervals/indexing/motif.meme \
    -g data/demos/intervals/indexing/peaks.txt
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
bash scripts/workflows/elements.sh -s longest -e 5UTR -t 8
bash scripts/workflows/elements.sh -s longest -e mRNA -m Yes -t 8
```

### 4.4 复用已有索引 — `pair_only.sh` &nbsp;[详细](docs/workflows/pair_only.md)

跳过昂贵的 indexing，对已有索引换基因列表重跑 pairing。Web 的 `promoters_pre` 模式背后也是这个脚本。

```bash
bash scripts/workflows/pair_only.sh \
    -d results/cli/promoter/01_homotypic \
    -g data/genes/my_new_clusters.txt \
    -o results/cli/repaired
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

**MinHash 粗筛（opt-in）**。`pair_parallel` 自带 MinHash 粗筛（`-m <K>`），可跳过 gene-set 估计交集过小的候选对。**默认关闭**——CIS-BP2 校准显示没有"显著加速 + 可接受 FN 率"的安全默认值，详见 [docs/perf/minhash_calibration.md](docs/perf/minhash_calibration.md)。多核机器、可容忍少量漏检的 power user 可设 `PMET_MINHASH_MIN=N` 启用。

<a id="cn-6"></a>

## 6. 输出格式

最终产物 `motif_output.txt`，TAB 分隔 11 列，按
`Adjusted p-value (BH)` 排序。每行回答：这个 cluster 里，这对 motif
共同出现得是不是显著高于偶然？

```
Cluster   Motif 1  Motif 2     #both/cluster  #both/total  cluster_size   raw_p   adj_p (BH)  adj_p (Bonf)  adj_p (Global)  Genes
cortex    AHL12    AHL12_2     3              248          442            0.784   0.784       1.0           1.0             AT1G05680;AT2G20120;AT4G02170;
```

（真实表头是 `Number of genes in cluster with both motifs` 之类的长
名字；上面这张是为了排版缩了名。）

### 怎么读一行

把上面 `cortex / AHL12 / AHL12_2` 这行翻译成人话：

> `cortex` cluster 一共 **442** 个基因。其中只有 **3** 个的启动子
> 同时命中 AHL12 和 AHL12_2。在整个索引背景（这次扫到的所有可用
> 启动子）里，**248** 个基因同时命中这两个 motif。超几何检验问的
> 是：`3 / 442`（cortex 的命中率）显著高于 `248 / N`（背景的命中率）
> 吗？答：raw p = **0.78**，BH 校正后 p = **0.78** → 不显著，
> **AHL12 与 AHL12_2 在 `cortex` 这次跑里 _不_ 是协同对**。

`Adjusted p-value (BH)` 是判定线：

- `< 0.05` → 显著协同的 motif 对，值得跟进
- `≈ 1.0`（如上面 0.78）→ 噪声，这对 motif 在该 cluster 里并不比
  背景多
- `0.05` 到 `~0.5` 之间 → 有迹象但不显著；可以试试换 IC 阈值或者
  收紧基因列表再跑一遍

最后一列 `Genes` 列出贡献该共同出现的具体 cluster 基因 —— 想挑生
物学例子下游验证这对 motif 时直接从这里挑。

<a id="cn-7"></a>

## 7. 仓库结构

```
core/          C/C++ 引擎（indexing, pairing）+ CMake
scripts/      bash + python + R 共享工具；workflows
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
results/       运行输出（gitignored）：app/ 给 web 任务，cli/ 给 pipeline 运行
```

辅助脚本在 [`scripts/workflows/cli/`](scripts/workflows/cli/)：`00_env_check.sh`（依赖检查 + 下载 TAIR10）、`01_perf_cpu.sh` / `02_perf_params.sh`（perf benchmark）、`05_promoter_gap.sh`（启动子 gap 分析，见下图）、`_pmet_index_element.sh`（被 `elements.sh` source 的 indexing 子流程库，不直接调用）。

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

| 服务              | 角色                                              | host port   |
| ----------------- | ------------------------------------------------- | ----------- |
| nginx             | reverse proxy                                     | **5960**    |
| frontend          | Next.js                                           | (内部 3000) |
| api               | FastAPI                                           | (内部 8000) |
| worker            | Celery worker                                     | —           |
| liveness-watchdog | 杀掉 15 分钟无 progress.json 更新的任务           | —           |
| redis             | Celery broker + result backend                    | —           |

**Bind mount**（host 改文件即生效，无需 rebuild）：

- `apps/pmet_backend/` → `/app/pmet_backend`（uvicorn 自动 reload；worker 需 `make restart-worker`）
- `scripts/` → `/app/scripts`
- `data/` → `/app/data`
- `results/app/` → `/app/results`（web app 任务输出的唯一规范位置；docker 和本地模式 host 路径相同）

前端镜像在 build 时 baked，不挂载 — 改前端代码要 `make rebuild`（或 `cd deploy && make rebuild-frontend` 只重建前端）。

### 首次数据准备

Web app 的 `promoters_pre` 模式依赖预计算的物种索引，repo 不带。起 stack 之前在 host 上跑一次 `make fetch-data` —— 它下载什么、为什么要它，看 [Quick Start §2](#cn-2)。

### 邮件通知

后端任务完成后发邮件，SMTP 凭据放 `data/configure/email_credential.txt`（gitignored，**不要提交**）。5 行：`username` / `password`（推荐 Gmail app password）/ `from_address` / `smtp_server` / `port`。

### 管理员入口

栈采用单管理员的鉴权模型——一份共享 token 授予"查看所有任务 + 终止运行中任务"的权限。普通用户只能用邮箱搜自己的任务；管理员能看全部、筛选、强杀正在跑的任务。

**1. 生成 token（只做一次）**

随机生成一段并写入 `data/configure/admin_token.txt`（gitignored，**不要提交**）：

```bash
openssl rand -hex 32 > data/configure/admin_token.txt
```

文件不存在或为空时，所有 admin 接口返回 `503 Admin not configured`，`/admin/login` 页面也会同样提示。生成或轮换 token **不需要 rebuild** —— `data/configure/` 是 bind-mount，下一次 admin API 调用就生效。

**2. 登录**

打开 [http://localhost:5960/admin/login](http://localhost:5960/admin/login)，粘贴 token。后端校验后下发 httpOnly 的 `pmet_admin` cookie（30 天过期），登录成功跳转 `/admin/settings`。

**3. Admin 模式开放的功能**

- **看全部任务** —— `/tasks` 列出服务器上所有任务，而不是搜索那个邮箱的。搜索框仍然能用，作为快速筛选（邮箱 / task ID 子串匹配）。
- **筛选器** —— 多出几个下拉：状态（待运行 / 运行中 / 已完成 / 失败 / 已取消）、模式（promoters / promoters_pre / intervals）、起止日期。客户端在最新 200 条任务上过滤。
- **终止按钮** —— 每个 pending / running 的任务行右上角有红色 `Terminate` 按钮。点击 → 弹窗输入可选原因 → 后端把 JSON 状态先标 `cancelled`，再用 `psutil` 递归 walk worker 的进程树（先 SIGTERM，5 秒后未死则 SIGKILL），最后给用户发邮件（带原因或默认提示）。
- **设置页** —— `/admin/settings` 切换 `notify_on_submit`。关闭后 worker 不再发"PMET: New Task Submitted"那封管理员通知。用户侧邮件（任务开始 / 完成 / 被取消）不受影响。开关持久化到 `data/configure/admin_settings.json`，hot-reload。

**4. 退出登录**

设置页面 `Sign out` 按钮删 cookie。要轮换 token，直接改 `data/configure/admin_token.txt` 内容即可；旧 cookie 在下一次 admin API 调用时失效。

更细的 deploy target：`cd deploy && make help`。

<a id="cn-9"></a>

## 9. 测试与回归基线

五条不同层次的轨道，按快慢排序。每条都有 make target；**`make test` 把前三条快的串起来**（core + unit + integration，~10 秒），用作 commit 前的默认 gate。

| 轨道 | 命令 | 覆盖范围 |
|---|---|---|
| Core 数学 kernel（C/C++） | `make test-core`（或 `make test-pairing` / `make test-indexing`） | ~96 个单元测试，覆盖两套引擎的纯数学部分：BH correction、hypergeometric coloc、binomial / Poisson CDF、MinHash sketch、motif overlap 几何、负载均衡分区、indexing 侧字符串工具。测试二进制与生产共享同一份 OBJECT library，保证"测的代码 = 跑的代码"。**总计 < 5 秒。** |
| 仓库级单元测试（Python / R / bash / TS） | `make test-unit` | stage-status 推断、partial-result API、邮件分发、错误分类、watchdog staleness、list_tasks 分页+过滤、heatmap 尺寸 cap (R)、minhash workflow resolver (bash)、前端 Zustand store 动作（TypeScript via tsx，没装 `apps/pmet_frontend/node_modules` 自动跳过）。**< 5 秒。** |
| Pipeline 级集成 | `make test-integration`（跑 smoke；其它重脚本 `run_pipeline02_one_combo.sh`、`run_pipeline08_ic_sweep.sh`、`test_pipeline02_strand_realdata.sh`、`verify_baseline.sh`、`run_with_verify.sh` 见 [`tests/integration/README.md`](tests/integration/README.md)） | smoke 不变量（~3 秒，无需真实数据）：bedtools strand 处理、build_promoters.py 用了 `-s`、promoter+anno pipeline 的染色体名预检、assess_integrity.py 处理非相邻 fragment、可选的 TAIR10 真实数据 strand 检查。其它重脚本跑端到端 pipeline，需要 TAIR10 + 已建好的 homotypic 索引；它们的录制 baseline 待重抓（路径已迁 monorepo）。 |
| Workflow audit（[`tests/audit/`](tests/audit/)） | `make test-audit`（或 `python3 tests/audit/generate.py [<name> ...]` 跑指定 workflow） | 每个 workflow 跑一遍真实输入，用 dict→template 渲染出 [`docs/workflows/*.md`](docs/workflows/)，每条 verification check 都给 PASS/WARN/FAIL，SHA-256 anchor 当回归哨兵。pair_only ~15 s，intervals ~16 s，promoter ~2 min，elements ~5 min。**会写 docs/**，故不入 `make test`。 |
| CLI baseline（[`tests/baseline/`](tests/baseline/)） | `make baseline` | 对 `apps/cli/scripts/*` 输出做 fingerprint，`tests/baseline/fingerprints.txt` 当 anchor 对比。**会写 fingerprint 文件**，同样不入 `make test`。 |

`apps/pmet_backend/test_api.py` 是 5 stage smoke（imports / TaskCreate / StorageService / PMETExecutor / app load）。host 直接 `python apps/pmet_backend/test_api.py`，或在镜像里 `cd deploy && make test`。

<a id="cn-10"></a>

## 10. 排错 —— 新人最先撞的几堵墙

新人最常踩的 6 件事。每条都是把一封真实的求助邮件压成一行提示：

| 现象 | 实际原因 | 处理 |
|---|---|---|
| pipeline 报 `Chromosome name mismatch (gff3='Chr1', fasta='1')` 然后中止 | TAIR10 的染色体名是 `1, 2, ...`；很多别的 GFF3 是 `Chr1, Chr2, ...`。两边必须一致。 | 改一边的名字，或者直接换匹配的文件。`promoter` / `elements` / `02_perf_params` 几条 workflow 都有这个预检，会在跑 FIMO **之前**就拦下来，省你一小时。 |
| `intervals.sh` 在含 `:` 的 header（例如 `chr1:1234-5678`）上报错 | FIMO 和二进制 `fimohits` 格式都不认 FASTA record 名里的 `:`。 | `intervals.sh` 会自动把 `:` → `_`。还撞这个错说明你直接调底层二进制了 —— 走 workflow 脚本就行。 |
| pairing 抱怨 gene list 空了 / 格式不对 | gene list 是**两列**（`cluster_name<TAB>gene_id`），不是一列。 | 看 [`data/demos/promoters/pairing/demo`](data/demos/promoters/pairing/demo) 的标准形态；[`data/genes/genes_cell_type_treatment.txt`](data/genes/genes_cell_type_treatment.txt) 是个真实样本。 |
| `motif_output.txt` 跑出来了，heatmap 没出 | R 或它的某个包（`ggplot2`、`RColorBrewer`、`pheatmap`）没装。 | heatmap stage 是 best-effort —— 装了：`Rscript scripts/r/install_packages.R` 重跑；不装：直接消费 `motif_output.txt` 也行。 |
| `make up` 报 `port 5960 already in use` | 另一个容器或非 docker 进程占着 5960 端口。 | Makefile 会先尝试把 5960 上残留的 docker 容器停掉；还失败就是非 docker 进程占着 —— 错误信息里有 PID。腾出来，或者改 [`deploy/docker-compose.yml`](deploy/docker-compose.yml) 里的 host 端口。 |
| web 任务一直卡在 "running" | worker 跑一半被 SIGKILL 了，没机会写最终状态。 | `liveness-watchdog` 容器会把 `progress.json` 超过 15 分钟没更新的任务标 `failed`。想立刻救场：`cd deploy && make restart-worker` 然后重提一次。 |

以上都不对的话，下一步去看
[`tests/integration/run_smoke.sh`](tests/integration/run_smoke.sh)
（~3 秒抓出大部分环境/约定回归）和后端日志（仓库根 `make logs`，
按 service 过滤）。

<a id="cn-11"></a>

## 11. 迁移历史

本仓库由三个独立目录（`PMET_project`、`pmet_analysis_pipeline`、
`pmet_shiny_app`）合并而来，合并点是 tag `v0.1.0-monorepo`。
[`tests/baseline/README.md`](tests/baseline/README.md) 详细记录了用于
验证合并前后无回归的 fingerprint。
