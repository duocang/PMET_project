#!/usr/bin/env python3
"""Analyze a MinHash prefilter calibration sweep.

Compares each `m > 0` run against the `m=0` ground truth and reports, per-m:
  - Total significant pairs at adj.p (Global Bonf) <= alpha
  - Pairs lost to prefilter (false negatives)
  - FN rate (% of ground truth)
  - Wall-clock speedup vs m=0
  - Whether *any* false positive snuck in (sanity check; should always be 0
    since prefiltered pairs get pval=1.0 dummy rows)

Output: human-readable table to stdout, plus a TSV next to SUMMARY.tsv.

Usage: analyze_minhash_calibration.py <sweep_root> [--alpha 0.05]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Column indices in motif_output.txt (no header — see Output::printMe + the
# `cluster\t` prefix added by exportResultParallel).
#
# Default significance criterion: column 8 = adj.p (per-cluster Bonferroni)
# = pval × clusterSize. Empirically, on a 1.36 M-pair × 4-cluster sweep BH
# (col 7) is so conservative that no row clears any α; global Bonferroni
# (col 9) is conversely too aggressive. Per-cluster Bonferroni is the sweet
# spot that PMET users actually report on, so we calibrate against it.
COL_CLUSTER = 0
COL_MOTIF1 = 1
COL_MOTIF2 = 2
COL_RAW_P = 6
COL_ADJ_BH = 7
COL_ADJ_BONF = 8           # per-cluster (pval × clusterSize)
COL_ADJ_GLOBAL_BONF = 9
SIG_COLUMN_DEFAULT = COL_ADJ_BONF


def load_significant_pairs(path: Path, alpha: float, col: int) -> set[tuple[str, str, str]]:
    """Return the set of (cluster, motif1, motif2) with the chosen p-column <= alpha."""
    sig = set()
    with path.open() as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < col + 1:
                continue
            try:
                p = float(parts[col])
            except ValueError:
                continue
            if p <= alpha:
                sig.add((parts[COL_CLUSTER], parts[COL_MOTIF1], parts[COL_MOTIF2]))
    return sig


DUMMY_RAW_P = "1.0000000000e+00"


def consistency_check(sweep_root: Path, m_values: list[int]) -> list[str]:
    """For every m > 0, verify the per-pair raw / per-cluster-Bonferroni /
    global-Bonferroni columns are byte-identical to m=0 on non-skipped pairs.

    The BH column (col 7) is NOT expected to match because the dummies (pval=1.0)
    occupy the largest-p ranks of the descending sort and shift the BH multiplier
    `n/(n-i)` for the surviving real p-values. That drift is mathematically
    correct, so we only flag it informationally.
    """
    base_path = sweep_root / "m=0" / "motif_output.txt"
    if not base_path.exists():
        return [f"baseline missing: {base_path}"]

    def index(path: Path) -> dict[tuple[str, str, str], list[str]]:
        out: dict[tuple[str, str, str], list[str]] = {}
        with path.open() as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 11:
                    continue
                out[(parts[0], parts[1], parts[2])] = parts
        return out

    base = index(base_path)
    out_lines: list[str] = [
        "\nConsistency check (raw_p / Bonf-cluster / Bonf-global must match baseline on kept pairs):",
        f"  baseline rows: {len(base)}"
    ]
    all_pass = True
    for m in m_values:
        if m == 0:
            continue
        path = sweep_root / f"m={m}" / "motif_output.txt"
        if not path.exists():
            continue
        cand = index(path)
        kept = [k for k, v in cand.items() if v[6] != DUMMY_RAW_P and k in base]
        diff_raw = sum(1 for k in kept if cand[k][6] != base[k][6])
        diff_bh  = sum(1 for k in kept if cand[k][7] != base[k][7])
        diff_bf  = sum(1 for k in kept if cand[k][8] != base[k][8])
        diff_gb  = sum(1 for k in kept if cand[k][9] != base[k][9])
        ok = (diff_raw == 0 and diff_bf == 0 and diff_gb == 0)
        all_pass = all_pass and ok
        flag = "OK" if ok else "FAIL"
        out_lines.append(
            f"  m={m:>4}: kept={len(kept):>7}  raw_p_diff={diff_raw}  "
            f"Bonf_clust_diff={diff_bf}  Bonf_global_diff={diff_gb}  "
            f"BH_diff={diff_bh} (informational)  [{flag}]"
        )
    out_lines.append(f"  -> {'PASS' if all_pass else 'FAIL'}: prefilter does not perturb non-skipped numerics on calibration columns")
    return out_lines


def load_runtimes(summary: Path) -> dict[int, float]:
    out: dict[int, float] = {}
    with summary.open() as fh:
        next(fh, None)  # header
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                m = int(parts[0])
                rt = float(parts[1])
            except ValueError:
                continue
            out[m] = rt
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep_root", type=Path)
    ap.add_argument("--alpha", type=float, default=0.05,
                    help="significance threshold on the chosen p-value column. Default 0.05")
    ap.add_argument("--column", choices=["bh", "bonf", "global_bonf"], default="bonf",
                    help="which p-value column to call significance on. "
                         "'bonf' = per-cluster Bonferroni (col 8, default); "
                         "'bh' = Benjamini–Hochberg (col 7); "
                         "'global_bonf' = global Bonferroni (col 9).")
    args = ap.parse_args()
    col_map = {"bh": COL_ADJ_BH, "bonf": COL_ADJ_BONF, "global_bonf": COL_ADJ_GLOBAL_BONF}
    sig_col = col_map[args.column]

    summary = args.sweep_root / "SUMMARY.tsv"
    if not summary.exists():
        print(f"missing {summary}", file=sys.stderr)
        return 1

    runtimes = load_runtimes(summary)
    if 0 not in runtimes:
        print("no m=0 baseline in SUMMARY.tsv — cannot compute FN rate", file=sys.stderr)
        return 1

    # Load each per-m output. m=0 is the ground truth.
    sig_by_m: dict[int, set[tuple[str, str, str]]] = {}
    for m in sorted(runtimes):
        out = args.sweep_root / f"m={m}" / "motif_output.txt"
        if not out.exists():
            print(f"warn: missing {out}", file=sys.stderr)
            continue
        sig_by_m[m] = load_significant_pairs(out, args.alpha, sig_col)

    if 0 not in sig_by_m:
        print("m=0 motif_output.txt missing", file=sys.stderr)
        return 1

    truth = sig_by_m[0]
    base_runtime = runtimes[0]

    rows: list[dict] = []
    print(f"\nGround truth (m=0): {len(truth)} pairs at adj.p_{args.column} <= {args.alpha}")
    print(f"Baseline runtime:   {base_runtime:.1f} s\n")
    header = f"{'m':>4} | {'runtime':>9} | {'speedup':>7} | {'kept':>6} | {'FN':>5} | {'FN rate':>8} | {'FP':>3}"
    print(header)
    print("-" * len(header))

    for m in sorted(sig_by_m):
        sig = sig_by_m[m]
        rt = runtimes[m]
        speedup = base_runtime / rt if rt > 0 else float("nan")
        if m == 0:
            print(f"{m:>4} | {rt:>7.1f} s | {'1.00x':>7} | {len(sig):>6} | {'-':>5} | {'-':>8} | {'-':>3}")
            rows.append({"m": m, "runtime_s": rt, "speedup": 1.0, "kept": len(sig),
                         "fn": 0, "fn_rate": 0.0, "fp": 0})
            continue
        kept = sig & truth
        fn = truth - sig
        fp = sig - truth
        fn_rate = len(fn) / len(truth) if truth else 0.0
        print(f"{m:>4} | {rt:>7.1f} s | {speedup:>6.2f}x | {len(kept):>6} | {len(fn):>5} | "
              f"{fn_rate*100:>7.3f}% | {len(fp):>3}")
        rows.append({"m": m, "runtime_s": rt, "speedup": round(speedup, 3),
                     "kept": len(kept), "fn": len(fn),
                     "fn_rate": round(fn_rate, 6), "fp": len(fp)})

    # Persist a parsable copy alongside the inputs.
    out_tsv = args.sweep_root / "ANALYSIS.tsv"
    with out_tsv.open("w") as fh:
        fh.write("m\truntime_s\tspeedup\tkept\tfn\tfn_rate\tfp\n")
        for r in rows:
            fh.write(f"{r['m']}\t{r['runtime_s']:.2f}\t{r['speedup']}\t"
                     f"{r['kept']}\t{r['fn']}\t{r['fn_rate']:.6f}\t{r['fp']}\n")
    print(f"\nWrote {out_tsv}")

    for line in consistency_check(args.sweep_root, sorted(sig_by_m)):
        print(line)

    # Per-cluster breakdown (helps spot whether one cluster takes all the FN hits).
    print("\nPer-cluster FN breakdown:")
    by_cluster_truth: dict[str, int] = {}
    for c, _, _ in truth:
        by_cluster_truth[c] = by_cluster_truth.get(c, 0) + 1
    clusters = sorted(by_cluster_truth)
    head = f"{'cluster':>10} | {'truth':>6} | " + " | ".join(f"m={m:<3}" for m in sorted(sig_by_m) if m != 0)
    print(head)
    print("-" * len(head))
    for c in clusters:
        cells = [f"{c:>10}", f"{by_cluster_truth[c]:>6}"]
        for m in sorted(sig_by_m):
            if m == 0:
                continue
            sig = sig_by_m[m]
            fn = sum(1 for (cc, _, _) in (truth - sig) if cc == c)
            cells.append(f"{fn:>4}")
        print(" | ".join(cells))

    return 0


if __name__ == "__main__":
    sys.exit(main())
