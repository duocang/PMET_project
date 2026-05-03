#!/usr/bin/env python3
"""Verify R and frontend heatmap pipelines pick the same motifs.

Both sides start from the same ``motif_output.txt`` and apply the same
sanity filters (p_adj_bonf ≤ limit; gene_num > 5% × cluster_genes; drop
cross-cluster pairs when unique_combination is on). They then diverge:

  R   (scripts/r/process_pmet_result.R::ProcessPmetResult)
      Score every motif by sum(-log10(p_adj)) over pairs containing it,
      take floor(max_motifs / n_clusters) motifs per cluster, then a
      secondary global reshuffle if the union still exceeds max_motifs.

  TS  (apps/pmet_frontend/app/visualize/page.tsx::processPmetResult)
      Sort filtered pairs by p_adj_bonf ascending, take the top topN
      pairs per cluster, collect the motifs that appear in those pairs.

This script reproduces the TS logic in Python (it's pure data work, no
DOM bits) and compares against the R-side dump produced by
scripts/r/dump_processed_data.R. A clean diff means both UIs are
plotting the same data; any difference is a real divergence the user
would see as "the two heatmaps don't agree".

Usage:
    python3 tests/integration/verify_heatmap_consistency.py \
        [--input data/demos/promoters/pairing/demo/motif_output.txt] \
        [--p-adj-limit 0.05] [--topn 5] [--max-motifs 30] \
        [--unique-combination] [--report PATH]

Exits 0 if the two pipelines agree, 1 if they disagree, 2 on tooling
errors (missing R, missing input, etc.). Report (default
``tests/integration/heatmap_consistency_report.txt``) gets the
human-readable diff regardless of exit code.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data/demos/promoters/pairing/demo/motif_output.txt"
DEFAULT_REPORT = REPO_ROOT / "tests/integration/heatmap_consistency_report.txt"
R_DUMP_SCRIPT = REPO_ROOT / "scripts/r/dump_processed_data.R"


def parse_pmet_file(path: Path) -> List[dict]:
    """Read motif_output.txt into a list of row dicts (keys match the
    field names the frontend uses, not the original column titles)."""
    rows: List[dict] = []
    with path.open(newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader, None)  # header
        for cols in reader:
            if len(cols) < 8:
                continue
            try:
                p_bh = float(cols[7])
            except ValueError:
                continue
            rows.append({
                "cluster": cols[0],
                "motif1": cols[1],
                "motif2": cols[2],
                "gene_num": int(cols[3] or 0),
                "total_genes": int(cols[4] or 0),
                "cluster_genes": int(cols[5] or 0),
                "p_value": float(cols[6] or 1),
                "p_adj_bh": p_bh,
                "p_adj_bonf": float(cols[8] or 1) if len(cols) > 8 else 1.0,
                "p_adj_global": float(cols[9] or 1) if len(cols) > 9 else 1.0,
                "genes": [g for g in (cols[10] if len(cols) > 10 else "").split(";") if g],
                "motif_pair": f"{cols[1]}^^{cols[2]}",
            })
    return rows


def frontend_process(rows: List[dict],
                     p_adj_limit: float,
                     topn: int,
                     unique_combination: bool) -> Dict[str, dict]:
    """Mirror of processPmetResult() in apps/pmet_frontend/app/visualize/page.tsx.

    Returns ``{cluster: {motifs: [...], top_pairs: [...]}}``. Top pairs
    are kept alongside the motif set so the diff can show *why* the two
    pipelines chose different motifs (often it's that R's score-based
    ranking elevated a motif that's in many lower-significance pairs
    while the frontend stuck to motifs from the single highest-p pair).
    """
    # genesPerCluster: union of every gene mentioned in any row of that
    # cluster (matches the frontend's Set semantics).
    genes_per_cluster: Dict[str, set] = defaultdict(set)
    for r in rows:
        genes_per_cluster[r["cluster"]].update(r["genes"])

    filtered = []
    for r in rows:
        if r["p_adj_bonf"] > p_adj_limit:
            continue
        gene_limit = 0.05 * len(genes_per_cluster.get(r["cluster"], set()))
        if r["gene_num"] <= gene_limit:
            continue
        filtered.append(r)

    if unique_combination:
        pair_count: Dict[str, int] = defaultdict(int)
        for r in filtered:
            pair_count[r["motif_pair"]] += 1
        filtered = [r for r in filtered if pair_count[r["motif_pair"]] == 1]

    by_cluster: Dict[str, List[dict]] = defaultdict(list)
    for r in filtered:
        by_cluster[r["cluster"]].append(r)

    out: Dict[str, dict] = {}
    for clu in sorted(by_cluster):
        sorted_rows = sorted(by_cluster[clu], key=lambda r: r["p_adj_bonf"])
        topk = sorted_rows[:topn]
        motif_set: List[str] = []
        seen = set()
        for r in topk:
            for m in (r["motif1"], r["motif2"]):
                if m not in seen:
                    seen.add(m)
                    motif_set.append(m)
        out[clu] = {
            "motifs": motif_set,
            "top_pairs": [
                {"motif1": r["motif1"], "motif2": r["motif2"],
                 "p_adj_bonf": r["p_adj_bonf"], "gene_num": r["gene_num"]}
                for r in topk
            ],
        }
    return out


def run_r_dump(input_path: Path,
               p_adj_limit: float,
               topn: int,
               unique_combination: bool,
               max_motifs: int,
               out_json: Path) -> None:
    """Invoke scripts/r/dump_processed_data.R from the repo root."""
    if shutil.which("Rscript") is None:
        raise SystemExit("Rscript not found on PATH — install R or "
                         "skip the consistency check.")
    cmd = [
        "Rscript", str(R_DUMP_SCRIPT.relative_to(REPO_ROOT)),
        str(input_path), str(out_json),
        str(p_adj_limit), str(topn),
        "TRUE" if unique_combination else "FALSE",
        str(max_motifs),
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"R dump failed (exit {proc.returncode})")


def diff_pipelines(r_data: dict, ts_data: Dict[str, dict]) -> Tuple[bool, List[str]]:
    """Compare R vs TS motif selections per cluster. Returns (agrees, lines)."""
    lines: List[str] = []
    r_motifs = r_data.get("motifs_per_cluster", {}) or {}
    r_pairs = r_data.get("pairs_per_cluster", {}) or {}

    r_clusters = set(r_motifs)
    ts_clusters = set(ts_data)
    agrees = True

    if r_clusters != ts_clusters:
        agrees = False
        lines.append(f"!! cluster set differs")
        lines.append(f"   R  only: {sorted(r_clusters - ts_clusters)}")
        lines.append(f"   TS only: {sorted(ts_clusters - r_clusters)}")
        lines.append("")

    for clu in sorted(r_clusters | ts_clusters):
        r_set = set(r_motifs.get(clu, []) or [])
        ts_set = set(ts_data.get(clu, {}).get("motifs", []) or [])
        if r_set == ts_set:
            lines.append(f"== {clu}: {len(r_set)} motifs match")
            continue

        agrees = False
        lines.append(f"!! {clu}: motif set differs "
                     f"(R={len(r_set)}, TS={len(ts_set)})")
        only_r = sorted(r_set - ts_set)
        only_ts = sorted(ts_set - r_set)
        if only_r:
            lines.append(f"   R  only ({len(only_r)}): {', '.join(only_r)}")
        if only_ts:
            lines.append(f"   TS only ({len(only_ts)}): {', '.join(only_ts)}")
        # Surface the TS top-N pairs so the reader can see what the
        # frontend was working from when the two diverged.
        ts_pairs = ts_data.get(clu, {}).get("top_pairs", [])[:5]
        if ts_pairs:
            lines.append(f"   TS top {len(ts_pairs)} pairs (by p_adj_bonf):")
            for p in ts_pairs:
                lines.append(f"      {p['motif1']:<24} {p['motif2']:<24} "
                             f"p={p['p_adj_bonf']:.3e}  n={p['gene_num']}")
        # And how many R pairs that cluster ended up with — useful when
        # debugging whether R's score-based motif ranking pulled in
        # motifs from outside the TS top-N.
        r_pair_rows = r_pairs.get(clu) or []
        lines.append(f"   R total pairs after filter: {len(r_pair_rows)}")
        lines.append("")

    return agrees, lines


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default=str(DEFAULT_INPUT),
                   help="motif_output.txt to compare on (default: demo fixture)")
    p.add_argument("--p-adj-limit", type=float, default=0.05)
    p.add_argument("--topn", type=int, default=5,
                   help="frontend's per-cluster top-N pair count")
    p.add_argument("--max-motifs", type=int, default=30,
                   help="R's max_motifs_in_plot cap")
    p.add_argument("--unique-combination", action="store_true", default=True,
                   help="drop motif pairs that appear in multiple clusters "
                        "(matches the default in both pipelines)")
    p.add_argument("--no-unique-combination", dest="unique_combination",
                   action="store_false")
    p.add_argument("--report", default=str(DEFAULT_REPORT),
                   help="write diff report here (default: "
                        "tests/integration/heatmap_consistency_report.txt)")
    args = p.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return 2

    rows = parse_pmet_file(input_path)
    if not rows:
        print(f"ERROR: no rows parsed from {input_path}", file=sys.stderr)
        return 2

    ts_data = frontend_process(rows, args.p_adj_limit, args.topn,
                               args.unique_combination)

    with tempfile.TemporaryDirectory() as td:
        r_json = Path(td) / "r.json"
        run_r_dump(input_path, args.p_adj_limit, args.topn,
                   args.unique_combination, args.max_motifs, r_json)
        r_data = json.loads(r_json.read_text())

    agrees, diff_lines = diff_pipelines(r_data, ts_data)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        f"# heatmap consistency report",
        f"# input:  {input_path.relative_to(REPO_ROOT) if input_path.is_relative_to(REPO_ROOT) else input_path}",
        f"# params: p_adj_limit={args.p_adj_limit} topn={args.topn} "
        f"unique={args.unique_combination} max_motifs={args.max_motifs}",
        f"# verdict: {'AGREE' if agrees else 'DIVERGE'}",
        "",
    ]
    report_path.write_text("\n".join(header + diff_lines) + "\n")

    print("\n".join(header + diff_lines))
    print(f"# wrote {report_path}")
    return 0 if agrees else 1


if __name__ == "__main__":
    sys.exit(main())
