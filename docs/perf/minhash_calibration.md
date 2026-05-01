# MinHash prefilter calibration

The pair stage (`pair_parallel`) evaluates every motif pair `(i, j)` for
co-occurrence enrichment in each gene cluster. With a typical large library
like CIS-BP2 (~1.6 k motifs), that is ~1.4 M pairs × N clusters before any
gene filtering — most of which can never reach Bonferroni significance because
the two motifs barely share any genes in the universe.

To skip those, every motif gets a 128-slot MinHash sketch over its gene-id
support set at load time. For each pair, the C++ side estimates
`|genes(i) ∩ genes(j)|` from the sketches and skips the full hypergeometric
path when the estimate falls below a configurable threshold:

- Implementation: [core/pairing/src/utils.cpp:418-438](../../core/pairing/src/utils.cpp#L418-L438)
- CLI flag: `-m <min_intersection>` (default `0` = off)
- Skipped pairs still emit a dummy `Output` row with `pval=1.0`, so BH and
  Bonferroni denominators stay correct — see `recordSkippedPair` and the loop
  body in `outputParallel`.

This document records the calibration sweep that picked the production
default and the policy for when to enable the prefilter.

## Sweep setup

| Parameter | Value |
|---|---|
| Index | `data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2/` |
| Motifs | 1652 |
| Pairs | 1 363 726 |
| Universe | 26 558 promoters |
| Gene files | `data/genes/random_genes_300.txt` (4 random clusters, 1136 genes); `data/genes/heat_top300.txt` (heat_up + heat_down, 600 genes) |
| Significance criterion | adj.p (Global Bonferroni) ≤ 0.05 |
| Hardware | macOS arm64, 8 worker threads |
| Sweep tool | [`apps/cli/scripts/bench/calibrate_minhash.sh`](../../apps/cli/scripts/bench/calibrate_minhash.sh) |
| Analyzer | [`apps/cli/scripts/bench/analyze_minhash_calibration.py`](../../apps/cli/scripts/bench/analyze_minhash_calibration.py) |

Ground truth is the `m=0` (prefilter off) run; every `m>0` run is compared
against that set of significant pairs to compute false-negative rate and
speedup. False positives are 0 by construction (skipped pairs become dummies
with `pval=1.0`).

## Significance column

The pair output has three adjusted-p columns. With ~1.4 M pairs × N
clusters, the BH (FDR) column collapses every row to high adj.p — no
threshold gives a useful ground-truth set. Conversely the global Bonferroni
column over-corrects for typical use. The middle option, **per-cluster
Bonferroni** (`pval × clusterSize`, column 8 of `motif_output.txt`), is what
PMET reports surface and matches the analyst's "is this pair significant in
this cluster?" question. Calibration is done against that column at α = 0.05.

## Results — `random_genes_300.txt` (4 random Arabidopsis clusters, 1136 genes)

Ground truth (m=0): **353 pairs at adj.p (per-cluster Bonferroni) ≤ 0.05**.

| m    | runtime (s) | speedup | sig pairs kept | FN  | FN rate |
|-----:|------------:|--------:|---------------:|----:|--------:|
| 0    | 188.3       | 1.00 ×  | 353            | —   | —       |
| 100  | 185.6       | 1.01 ×  | 353            | 0   | 0.00 %  |
| 300  | 184.9       | 1.02 ×  | 353            | 0   | 0.00 %  |
| 600  | 182.0       | 1.03 ×  | 334            | 19  | 5.38 %  |
| 900  | 159.5       | 1.18 ×  | 277            | 76  | 21.53 % |
| 1200 | 125.4       | 1.50 ×  | 176            | 177 | 50.14 % |

False positives: **0 across all m** (skipped pairs become dummy rows with
`pval=1.0`, so the prefilter cannot manufacture significance — sanity check
passes).

Per-cluster FN breakdown (`m=900`): random_1 27/50, random_2 36/218,
random_3 6/54, random_4 7/31. The loss is roughly proportional to
cluster-truth size; no cluster is hit catastrophically harder than the rest.

(Source TSV:
`results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__random_genes_300/ANALYSIS.tsv`.)

## Results — `heat_top300.txt` (real biological signal, 2 clusters)

To check that the random-gene curve isn't just noise, the same sweep was
re-run on a real heat-stress gene list (heat_up + heat_down, 600 genes
total, ~300 each).

Ground truth (m=0): **72 948 pairs at adj.p (per-cluster Bonferroni) ≤ 0.05**
— ~200× more than the random-gene case, as expected for a list with real
co-regulation signal.

| m    | runtime (s) | speedup | sig pairs kept | FN     | FN rate |
|-----:|------------:|--------:|---------------:|-------:|--------:|
| 0    | 181.9       | 1.00 ×  | 72 948         | —      | —       |
| 100  | 181.4       | 1.00 ×  | 72 946         | 2      | 0.003 % |
| 300  | 177.0       | 1.03 ×  | 72 897         | 51     | 0.070 % |
| 600  | 175.7       | 1.04 ×  | 70 946         | 2 002  | 2.744 % |
| 900  | 152.4       | 1.19 ×  | 59 564         | 13 384 | 18.347 % |
| 1200 | 119.5       | 1.52 ×  | 38 207         | 34 741 | 47.624 % |

False positives: still **0 across all m** (sanity check passes again).

Per-cluster FN at m=600: heat_down 33/552 (6.0%), heat_up 1969/72396 (2.7%).
The denser cluster loses *relatively* fewer pairs, which makes sense — its
truly significant pairs tend to have higher gene-set intersection and are
thus less likely to fall under the prefilter floor.

(Source TSV:
`results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__heat_top300/ANALYSIS.tsv`.)

**Cross-check verdict.** Real biological signal does *not* shift the
operating point in any useful direction: m=300 is still effectively a no-op
(3% speedup), m=600 still trades % speedup for % FN at a roughly 1:1 ratio,
and the m≥900 regime still costs a fifth of the truth set or more. The
random-gene calibration is a faithful proxy for picking the default.

## Why the curve looks like this

Every motif in CIS-BP2 reports hits in **exactly the top 5 000 genes** (the
binomial-threshold cap from indexing). With a universe of 26 558, the
expected pairwise gene-set intersection is

```
E[|A ∩ B|] = 5000 × 5000 / 26558 ≈ 941
```

So for a typical pair, MinHash will estimate `|A ∩ B|` near 941 with a
binomial-distributed sketch-match count (mean ≈ 13 of 128 slots). To skip a
non-trivial fraction of pairs, the threshold m has to approach the typical
intersection — which is also where genuinely significant pairs start
disappearing. There is no operating point in this regime that gives speed
without sacrificing recall.

## Numerical consistency check

Even before deciding the default, we want to confirm the prefilter doesn't
silently change the *numbers* on pairs that survive evaluation. The
analyzer's `consistency_check()` compares each `m > 0` run column-by-column
against the m=0 baseline on non-skipped pairs:

| Column | Behavior |
|---|---|
| 6 — raw p-value | byte-identical on all kept pairs at every m |
| 7 — adj.p (BH / FDR) | drifts by ~10⁻⁴ on ~9 % of kept rows (mathematically expected — see below) |
| 8 — adj.p (per-cluster Bonferroni) | byte-identical on all kept pairs at every m |
| 9 — adj.p (global Bonferroni) | byte-identical on all kept pairs at every m |

The BH drift is correct, not a bug: BH ranks all p-values descending, and
the dummy rows (`pval = 1.0`) take the largest-p slots. That pushes every
real p-value down by D ranks (where D = number of skipped pairs), so the
multiplier `n / (n − rank)` shifts. In every case the drift is *upward*
(more conservative); no real pair becomes more significant due to the
prefilter. We pin calibration on column 8 (per-cluster Bonferroni), which
is the column PMET actually surfaces and is **byte-identical** on kept
pairs — so the FN counts in the table above measure pure skip behavior,
not numerical contamination.

## Decision

**Default `PMET_MINHASH_DEFAULT = 0` (prefilter off) — opt-in only.**

The data does not justify any auto-enabled positive default on CIS-BP2:

- `m ≤ 300`: 0 % FN, 1 % speedup → not worth flipping the switch.
- `m = 600`: 5 % FN for 3 % speedup → bad tradeoff.
- `m ≥ 900`: meaningful speedup (18–50 %) but ≥ 22 % FN — unacceptable as a
  silent default.

The flag, sketch, and dummy-output bookkeeping stay (cost is negligible at
load time) so power users who tolerate FN can flip `PMET_MINHASH_MIN=N` on
their own hardware.

Smaller libraries (< 500 motifs) ship with `m = 0` for a different reason:
even at full N²/2 they run in seconds, so the marginal FN risk is also not
worth taking.

## Knobs (deploy time)

The workflows source [`scripts/lib/minhash.sh`](../../scripts/lib/minhash.sh).
Three env vars (highest priority first):

| Variable | Default | Effect |
|---|---|---|
| `PMET_MINHASH_MIN`       | unset | Force this exact value, skip auto-detection. Set to `0` to disable. |
| `PMET_MINHASH_THRESHOLD` | `500` | Motif count at/above which auto-enable. |
| `PMET_MINHASH_DEFAULT`   | `<K_CALIBRATED>` | Value used when auto-enable kicks in. |

Worker side: `executor.py` does `env = os.environ.copy()` before spawning the
workflow subprocess, so anything set on the worker container's `environment:`
in `deploy/docker-compose.yml` propagates automatically.

## How to re-run

```bash
make build                                    # ensure pair_parallel is fresh
NUM_THREADS=8 apps/cli/scripts/bench/calibrate_minhash.sh \
    data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2 \
    data/genes/random_genes_300.txt \
    0 3 5 10 20
apps/cli/scripts/bench/analyze_minhash_calibration.py \
    results/bench/calibrate/Arabidopsis_thaliana__CIS-BP2__random_genes_300
```

When changing the MinHash sketch (the K value, the SplitMix constants, or the
sketch construction) re-run the sweep and update the table here.

## Regression protection

The bash unit test at [`tests/unit/test_minhash_resolver.sh`](../../tests/unit/test_minhash_resolver.sh)
pins the resolver policy. Hooked into `tests/unit/run.sh`.
