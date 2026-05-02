# Runtime reference

**[English](#en) · [汉文](#cn)**

A handful of representative wall-clock numbers, so you have a sense of
"is my run normal" before you panic. All numbers are from the project's
canonical inputs; your mileage will vary with motif library size, gene
list count, and CPU.

---

<a id="en"></a>

## Wall-clock budget

| Task | Inputs | CPU | Wall time |
|---|---|---|---|
| Bundled demo (`make demo`) | `data/demos/promoters/{indexing,pairing}/demo` (toy: 6 motifs, 1 cluster) | any modern laptop, 1 thread used | ~5 s |
| Workflow audit, `pair_only` | demo index + demo gene list | 1 thread | ~15 s |
| Workflow audit, `intervals` | `data/demos/intervals/` (small motif lib) | 1 thread | ~16 s |
| Workflow audit, `promoter` | TAIR10 + Franco-Zorrilla (110 motifs, 4 gene clusters) | 4 threads | ~2 min |
| Workflow audit, `elements` | TAIR10 + Franco-Zorrilla, all 5 element types × longest/merged | 4 threads | ~5 min |
| Full `make test-audit` (all four workflows in sequence) | as above | 4 threads | ~7 min |
| `make test-core` + `test-unit` + `test-integration` | repo only, no real data | any | ~10 s |
| `make baseline` | demo data only, after `make build` | any | ~30 s |
| Production-style promoter scan | TAIR10 + CIS-BP2 (~5000 motifs), 1 cluster | 16 threads (Apple M2 Pro) | ~30 min |

The promoter scan number is the rough floor — at full CIS-BP2 size,
indexing dominates wall-clock. `pair_only` against a pre-built index
brings any subsequent re-pairing run down to seconds.

## When to expect surprises

- **First-time MinHash run** — the prefilter is opt-in and untuned for
  your motif library; see [`minhash_calibration.md`](minhash_calibration.md)
  for what we found on CIS-BP2 and why we ship with it off.
- **Heatmap stage** — proportional to (motif pairs × clusters); on
  pathological inputs (1000+ motifs) the R `ggsave` was the bottleneck
  until [`scripts/r/heatmap.R::compute_dims`](../../scripts/r/heatmap.R)
  added a size cap.
- **Disk I/O on `elements`** — splits into per-fragment FASTA records
  before FIMO; on a slow disk this can dominate. The `-t` thread flag
  doesn't help for I/O.

---

<a id="cn"></a>

## 时间预算

| 任务 | 输入 | CPU | wall time |
|---|---|---|---|
| 自带 demo（`make demo`） | `data/demos/promoters/{indexing,pairing}/demo`（玩具：6 motif、1 cluster） | 现代笔记本即可，单线程 | ~5 秒 |
| Workflow audit，`pair_only` | demo 索引 + demo 基因列表 | 1 线程 | ~15 秒 |
| Workflow audit，`intervals` | `data/demos/intervals/`（小 motif 库） | 1 线程 | ~16 秒 |
| Workflow audit，`promoter` | TAIR10 + Franco-Zorrilla（110 motif，4 个 gene cluster） | 4 线程 | ~2 分钟 |
| Workflow audit，`elements` | TAIR10 + Franco-Zorrilla，5 种 element × longest/merged | 4 线程 | ~5 分钟 |
| 完整 `make test-audit`（顺序跑四个 workflow） | 同上 | 4 线程 | ~7 分钟 |
| `make test-core` + `test-unit` + `test-integration` | 只用仓库内数据 | 任意 | ~10 秒 |
| `make baseline` | 只 demo 数据，`make build` 之后 | 任意 | ~30 秒 |
| 生产规模启动子扫描 | TAIR10 + CIS-BP2（~5000 motif），1 个 cluster | 16 线程（Apple M2 Pro） | ~30 分钟 |

启动子扫描那个数字是粗略下限 —— 完整 CIS-BP2 量级时 indexing 是
wall-clock 主导。后面拿现成索引跑 `pair_only`，重新配对都是秒级。

## 哪些情况会有意外

- **首次跑 MinHash** —— 粗筛是 opt-in 的，没针对你的 motif 库调过；
  我们在 CIS-BP2 上做过的事和为什么默认关，看
  [`minhash_calibration.md`](minhash_calibration.md)。
- **heatmap 阶段** —— 与 (motif 对 × cluster) 成正比；病态输入
  （1000+ motif）下 R 的 `ggsave` 曾经是瓶颈，
  [`scripts/r/heatmap.R::compute_dims`](../../scripts/r/heatmap.R)
  加了尺寸 cap 之后才稳。
- **`elements` 的磁盘 I/O** —— 在跑 FIMO 之前把序列按 fragment 拆
  成多条 FASTA record；慢盘上这一步可能是主导。`-t` 线程数对 I/O
  无济于事。
