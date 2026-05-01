# TODO

矩阵测试跑（2026-04-30，72 个任务横扫 heat / salt / cell-type 多组基因列表）暴露的待办，按优先级粗排。已划掉的条目表示已修复，仅保留为历史记录；早期讨论稿在 `tmp/` 与 `tmp_cli/`。

> 本文件聚焦"已知问题与改进路线"。"如何安装/使用"在 [README.md](README.md)，两者不重叠。

---

## 目录

- ~~[问题 1：基因列表 cluster 多时，画图把整个任务拖死](#问题-1已修)~~
- ~~[问题 2：CIS-BP2 这种大库，正常用户也会撞超时](#问题-2已修)~~
- [问题 3：明知挂了还要机械重试 10 分钟](#问题-3)
- [问题 4（meta）：`task.status` 是个骗子](#问题-4-meta)
- [优先级建议](#优先级建议)
- [其它 backlog（节奏未到）](#其它-backlog节奏未到)

---

## ~~问题 1（已修）~~

### ~~基因列表 cluster 多时，画图把整个任务拖死~~

> ~~已在 commit `4fd9aa2` 修复（fix(heatmap): cap motifs, size figures dynamically）。下面整段保留作回顾。~~

~~**问题在哪产生**~~

~~`scripts/r/heatmap.R:146` 写死："每 2 个 cluster 就给图加 10 inch 高度"。~~`hei <- 10 * ceiling(length(clusters)/2)`~~。所以 25 个 cluster → 图尺寸 130 inch。`ggsave` 内置 50 inch 的安全闸（防止误手生成 GB 级 PNG），超过直接 abort。~~

~~**实际影响**~~

~~- 用户提交"分了很多组"的基因列表（如 `random_genes_topN.txt` 含 25+ cluster）~~
~~- 后端 fimo + pair 富集都跑完了，`motif_output.txt` 已经写到磁盘上了~~
~~- R 准备画 heatmap → 触发 50 inch 限制 → R 异常退出 → bash 工作流退出码非零 → celery 标记任务"失败"~~
~~- 用户在网页看到红色 Failed、下载按钮 404，以为分析挂了——其实数据早就完整了，只是图没画出来~~

~~**怎么修的**~~

~~比一行 `limitsize = FALSE` 更彻底的三层方案，避免"绕过 50 inch 限"换来"几 GB 不可读 PNG"的次生问题：~~

~~1. **R 端 motif 自适应选择**（`scripts/r/process_pmet_result.R`）：每个 cluster 按 `sum(-log10(p_adj))` 给 motif 打分，配额 = `max(3, floor(cap / n_clusters))`，并集超 cap 时按"出现 cluster 数 + 全局分数"二次裁剪。最终 motif 总数受 `max_motifs_in_plot`（默认 30）限制。~~
~~2. **R 端动态尺寸**（`scripts/r/heatmap.R`）：图宽高从实际 motif 数 + panel 布局推算（约 0.18 inch / cell + 边距），硬上限 `max_fig_inches`（默认 40 inch），`limitsize = FALSE` 兜底。~~
~~3. **bash 端 try-catch**（`scripts/workflows/{pair_only,promoter,intervals}.sh`）：`Rscript` 失败仅打 `print_orange` 警告，pairing 数据是核心产物，画图是锦上添花，不让锦上添花拖死任务。~~

~~**残留**~~：~~`max_motifs_in_plot` 默认 30 的合理性、scoring 用 `sum` 还是 `max`，等真实使用反馈后再调。~~

---

## ~~问题 2（已修）~~

### ~~CIS-BP2 这种大库，正常用户也会撞超时~~

> ~~已修。修法比 TODO 原方案 (拉 celery hard time limit) 更聪明：用"心跳判活"代替"硬墙时长"，配合前端 runtime estimate + progress 反馈。残留：长阶段内细粒度 progress emit 仍待加，见下方"其它 backlog"。~~

~~**问题在哪产生**~~

~~CIS-BP2 motif 库 ~2330 个 motif，pair 检验是 motif 两两组合 → 约 270 万 pair 要算。在 2 CPU 的 docker 容器里单任务跑 8–10 分钟。celery 默认 soft time limit 不够用，运行时 watchdog 也撞墙。~~

~~**实际影响**~~

~~- 用户在 dropdown 里完全合法地选了 Arabidopsis + CIS-BP2（这是 web 提供的选项）~~
~~- 起码 1/3 概率撞超时~~
~~- 用户看到 Failed 不知道为什么——他没做错任何事，是系统配额没给够~~

~~**实际怎么修的**~~

~~两层组合，避免了简单"拉高 time limit"带来的"分不清正常长跑和卡死"问题：~~

~~1. **Liveness watchdog（独立容器）** —— `apps/pmet_backend/worker/watchdog.py` + `deploy/docker-compose.yml` 新增 `liveness-watchdog` service：~~
   ~~- 不靠 wall-clock cap，靠扫 `results/app/<id>/progress.json` 的 mtime 判活；任务在持续 emit progress 就一直活着，跑 30 分钟也不被杀~~
   ~~- 真正"卡死"超过 `LIVENESS_TIMEOUT_SEC`（默认 900s，env: `PMET_LIVENESS_TIMEOUT_SEC`）才 process-tree-kill 整个 bash 子进程树并 mark failed~~
   ~~- 跟 worker 同 PID namespace（`pid: service:worker`），psutil 能看见并 SIGTERM/SIGKILL 整个进程树~~
   ~~- 跑在独立容器，即使 celery worker slot 全被卡死任务占满，watchdog 仍能动手解锁~~
   ~~- 配置：`apps/pmet_backend/config.py` 加 `LIVENESS_TIMEOUT_SEC` 字段~~
~~2. **Runtime estimate + progress 反馈（commit `5c64e63`）** —— 前端 submit 页面在估算超阈值时给"这个库较大"友好提示；任务详情页基于 `progress.json` 实时显示阶段进度；`scripts/lib/progress.sh` + 三个 workflow sh 在 stage 边界 emit 心跳；`data/configure/runtime_calibration.json` 给 estimate 模型校准。~~

~~**残留**~~：~~progress 当前只在 stage 边界（indexing→heterotypic→heatmaps）emit，单 stage 内部（如 CIS-BP2 一次 pair test）就要 ~10 分钟，所以 watchdog 阈值不得不保守地设 900s。等内层循环（FIMO 每 N 个 motif、pair test 每 N% 进度、heatmap 渲染前）也加心跳后，阈值可降到 ~300s 不会误杀。详见"其它 backlog → Liveness watchdog 细粒度心跳"。pair 算法层粗筛（10× 速度）仍是 P3 长期项。~~

---

## 问题 3

### 明知挂了还要机械重试 10 分钟

**问题在哪产生**

celery 默认：任务抛异常 → 60 秒后自动重试。但有些异常注定永远不会成功（典型：`No genes match the universe`，gene list 跟物种 universe 完全不交集），worker 仍机械重试好几轮才认输。

**实际影响**

- 一个 worker slot 被一个注定失败的任务占着 ~10 分钟
- API 那边其实立刻返回 failed 状态——前端显示是对的——但 worker 资源被白白占用
- 多个用户同时撞这种错时，正常任务排队

**大致解决方案**

区分两种异常：

| 类型 | 含义 | 策略 |
|---|---|---|
| Permanent | 用户输入有问题，再试一万次也是这个错（`No genes match`、文件格式错误、参数越界、precomputed 索引文件损坏） | 不重试，立即终止 |
| Transient | 环境瞬态故障（磁盘忙、外部服务暂时不可达） | 重试合理 |

具体：`apps/pmet_backend/worker/tasks/pmet.py` 已有 `NON_RETRYABLE_ERROR_SNIPPETS` 列表（exec-format / 缺二进制），扩展加入：

- `No genes from the input list match the index universe` → permanent
- `Index .* missing or empty` → permanent
- `binomial_thresholds.txt missing` → permanent

permanent 失败 `raise self.retry()` 设 `max_retries=0`，或干脆 early return。

---

## 问题 4 (meta)

### `task.status` 是个骗子

**问题在哪产生**

任务在数据库里只有一个 `status: failed | completed | running` 字段，但实际 pipeline 有 fimo 扫描、pair 富集、写结果文件、画图等好几个阶段。任意阶段挂了都算 failed——但前面阶段的产物已经在磁盘上了。

**实际影响**

- 从 web 上看不出"产物有没有部分生成"
- 矩阵测试和 manifest 重建脚本都被骗——把一批"假 fail"记成"完全失败"，但里面相当一部分只是 heatmap 失败、`motif_output.txt` 完整可用
- 信任 API status 字段的所有 caller（poller、监控、外部脚本）都被坑

**短期方案** ◐ 部分修

- ~~一次性 backfill 脚本：扫 `results/app/<id>/pairing/motif_output.txt` 是否存在，重建 manifest（已写在 `tmp_cli/fix_manifest.sh`）~~ — 矩阵测试当时用过，把假 fail 的 23+9 个任务正确翻成 success
- **生产 API：未做**。`/api/tasks/{id}` 应该在 `status==failed` 且 `motif_output.txt` 存在时附 `partial_result_link`（不动 status，让失败仍可见）；前端任务详情页基于 `partial_result_link` 显示 "Download partial result" 按钮

**长期方案**：把 status 拆开

```
{ "stage_indexing":  "completed",
  "stage_pairing":   "completed",
  "stage_heatmap":   "skipped",   # or "failed" / "in_progress"
  "stage_zip":       "completed",
  "warnings":        ["heatmap skipped: too many clusters"] }
```

外层 `status` 变成 derived rollup：`failed` 仅当任一上游阶段失败；`completed_with_warnings` 表示 heatmap 跳过但其它都过。这是问题 1 的根本治法——status 拆细后，画图失败再也不会让人误以为任务挂了。

---

## 优先级建议

| 优先级 | 修什么 | 工作量 | 影响 |
|---|---|---|---|
| ~~P0~~ | ~~问题 1：R 端动态尺寸 + bash try-catch~~ | ~~半小时~~ | ~~~25% 假 failed 立刻翻为 success~~ ✓ commit `4fd9aa2` |
| ~~P0~~ | ~~问题 2：celery time limit 调高 + 前端预警~~ | ~~1–2 小时~~ | ~~CIS-BP2 用户不再无故失败~~ ✓ liveness-watchdog 容器 + commit `5c64e63`（runtime estimate / progress） |
| P1 | 问题 4 短期：`partial_result_link` API + 前端按钮 | 2–3 小时 | 历史 task 的部分产物可下载 |
| P1 | 问题 3：permanent vs transient 异常分类 | 1–2 小时 | worker 资源利用率 |
| P2 | 问题 4 长期：status 字段拆分 + 前端配套 | 半天 | 长期 UX、监控可信度 |
| P3 | 问题 2 算法：pair 粗筛 | 1–2 天 | 实质降低大库 runtime |

> ~~一次性 manifest 重建脚本（`tmp_cli/fix_manifest.sh`）已写，矩阵测试时用过；问题 4 短期 API 修完后即可丢弃。~~

---

## 其它 backlog（节奏未到）

源自原 TODO.md，按主题归并、保留要点：

### Liveness watchdog：长阶段内更频繁 emit progress

watchdog 容器已落地（杀僵任务），但阈值偏保守（900 s），原因是 `scripts/lib/progress.sh` 只在阶段边界（`indexing → heterotypic → heatmaps`）打点。CIS-BP2 大库一次 pairing 在两个 emit 之间就要 ~10 分钟。

**接下来**：让内层循环（每 N 个 motif、每 N% pair test、每张 heatmap 前）push 心跳。完成后阈值可降到 300 s 不会误杀。

触点：`core/indexing/fused_fimo/src/main.cpp`、`core/pairing/parallel/src/...`、`scripts/r/heatmap.R`、`scripts/lib/progress.sh`（加 `bump_progress` helper 仅更 `updated_at`）。

### Worker concurrency 弹性化

`worker_concurrency=2` 通过 compose 的 `PMET_WORKERS=2` 写死。16 核机器闲置；2 核机器两个 CIS-BP2 就饱和。改：

```python
worker_concurrency = max(1, multiprocessing.cpu_count() // 2)
```

或暴露成 Makefile knob：`make up CONCURRENCY=4`。

### Tests / baseline 重抓

`tests/integration/baselines/01_baseline.stdout` 仍指向 `data/homotypic_promoters/...`（2026-04-30 重组已删）。修完 `01_perf_cpu.sh` 让它走新 `results/cli/promoter/01_homotypic` 路径后，重抓 fingerprint。

### 仓库小整理

- `data/configure/` 语义上属于部署期配置 → 该挪到 `deploy/configure/`（影响 4 处引用），等当前手头工作收尾后做
- `core/indexing/{c,cpp}/scripts/{run,run_interval,debug_run}.sh` 写到 `$PROJECT_DIR/result/`（引擎本地），未集成到 monorepo `results/` —— 要么集成、要么文档说明这些是 throwaway dev-only
- `scripts/fetch_data.sh` 和 `scripts/fetch_reference.sh` 在 TAIR10 拉取部分有重复。今天可接受（不同调用语境），但 `fetch_data.sh` 可以调用 `fetch_reference.sh` 处理 TAIR10 部分
