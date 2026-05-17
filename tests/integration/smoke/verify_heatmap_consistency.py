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
    python3 tests/integration/smoke/verify_heatmap_consistency.py \
        [--input data/demos/promoters/pairing/demo/motif_output.txt] \
        [--p-adj-limit 0.05] [--topn 5] [--max-motifs 30] \
        [--unique-combination] [--report PATH]

Exits 0 if the two pipelines agree, 1 if they disagree, 2 on tooling
errors (missing R, missing input, etc.). Report (default
``results/tests/heatmap/consistency_report.txt``) gets the
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

# __file__ lives at tests/integration/smoke/verify_heatmap_consistency.py
# (3 levels deep from repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = REPO_ROOT / "tests/integration/smoke/fixtures/heatmap/motif_output.txt"
# All test artefacts share results/tests/<suite>/ — one root for every
# gitignored test output makes `make clean-tests` straightforward and
# survives across reboots (unlike /tmp).
DEFAULT_REPORT = REPO_ROOT / "results/tests/heatmap/consistency_report.txt"
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
                     max_motifs: int,
                     unique_combination: bool) -> Dict[str, dict]:
    """Mirror of processPmetResult() in apps/pmet_frontend/app/visualize/page.tsx.

    Both sides now use the same score-based motif selection (sum of
    -log10(p_adj) per motif, per-cluster cap = ⌊max_motifs / n_clusters⌋
    with a floor of 3, then a global secondary trim that prefers
    motifs hit by more clusters when the union still exceeds the cap).
    Originally the TS side used a different "top-N pairs, collect
    motifs" rule and this script existed to surface the divergence;
    after the alignment commit the two should report AGREE.
    """
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
    clusters = sorted(by_cluster)

    # Score motifs per cluster — Σ −log10(p_adj) over pairs containing
    # the motif. Floor p_adj at 1e-300 to avoid log(0)=Inf when
    # extremely-small adjusted p-values underflow.
    score_per_cluster: Dict[str, Dict[str, float]] = {}
    for clu in clusters:
        scores: Dict[str, float] = defaultdict(float)
        for r in by_cluster[clu]:
            neg_log_p = -math.log10(max(r["p_adj_bonf"], 1e-300))
            scores[r["motif1"]] += neg_log_p
            scores[r["motif2"]] += neg_log_p
        score_per_cluster[clu] = dict(scores)

    per_cluster_cap = max(3, max_motifs // max(1, len(clusters)))
    top_per_cluster: Dict[str, List[str]] = {}
    for clu in clusters:
        ordered = sorted(score_per_cluster[clu].items(),
                         key=lambda kv: kv[1], reverse=True)
        top_per_cluster[clu] = [m for m, _ in ordered[:per_cluster_cap]]

    # Global secondary trim — only when the union still exceeds the cap.
    union: List[str] = []
    seen_union = set()
    for clu in clusters:
        for m in top_per_cluster[clu]:
            if m not in seen_union:
                seen_union.add(m)
                union.append(m)
    if len(union) > max_motifs:
        global_agg: Dict[str, Dict[str, float]] = {}
        for clu in clusters:
            for m in top_per_cluster[clu]:
                score = score_per_cluster[clu].get(m, 0.0)
                cur = global_agg.setdefault(m, {"n_clu": 0, "global_score": 0.0})
                cur["n_clu"] += 1
                cur["global_score"] += score
        ranked = sorted(
            global_agg.items(),
            key=lambda kv: (-kv[1]["n_clu"], -kv[1]["global_score"]),
        )
        kept = {m for m, _ in ranked[:max_motifs]}
        for clu in clusters:
            top_per_cluster[clu] = [m for m in top_per_cluster[clu] if m in kept]

    out: Dict[str, dict] = {}
    for clu in clusters:
        # Re-sort cluster pairs by p_adj_bonf for the diagnostic
        # "top_pairs" preview the diff function shows on mismatch.
        sorted_pairs = sorted(by_cluster[clu], key=lambda r: r["p_adj_bonf"])
        out[clu] = {
            "motifs": top_per_cluster[clu],
            "top_pairs": [
                {"motif1": r["motif1"], "motif2": r["motif2"],
                 "p_adj_bonf": r["p_adj_bonf"], "gene_num": r["gene_num"]}
                for r in sorted_pairs[:5]
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


# --------------------------------------------------------------------------
# Optional visual rendering (--render-dir). The data-level check above is
# enough to prove the two pipelines pick the same motifs; this section
# additionally produces side-by-side PNGs so a reviewer can eyeball
# colour scale, label rotation, axis order, etc. — the things that
# differ visually even when the underlying data agrees.
# --------------------------------------------------------------------------

DRAW_HEATMAP_R = REPO_ROOT / "scripts/r/draw_heatmap.R"


def render_r_png(input_path: Path, out_png: Path,
                 max_motifs: int, max_inches: float = 40) -> None:
    """Drive scripts/r/draw_heatmap.R to produce the All-clusters PNG."""
    if shutil.which("Rscript") is None:
        raise RuntimeError("Rscript not found on PATH")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "Rscript", str(DRAW_HEATMAP_R.relative_to(REPO_ROOT)),
        "All", str(out_png), str(input_path),
        "5", "3", "6", "FALSE",                  # legacy positionals (ncol/width/unique)
        str(max_motifs), str(max_inches),
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise RuntimeError(f"R render failed (exit {proc.returncode})")


def render_frontend_png(input_path: Path, out_png: Path,
                        base_url: str = "http://localhost:5960") -> None:
    """Capture the live frontend's heatmap by driving /visualize via
    Playwright. Requires the docker stack to be up and Playwright +
    Chromium installed on the host (`pip install playwright &&
    playwright install chromium`).

    The frontend page accepts a local file via drag-drop; the cleaner
    headless path is `set_input_files()` against the underlying
    `<input type="file">`. After upload we wait for the Plotly heatmap
    container to mount, then screenshot it (not the whole page — the
    upload zone and surrounding chrome aren't part of the visual diff
    we care about).
    """
    try:
        from playwright.sync_api import sync_playwright   # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "playwright not installed. Install with:\n"
            "  pip install playwright && playwright install chromium"
        ) from exc

    out_png.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            page.goto(f"{base_url}/visualize", wait_until="networkidle", timeout=20_000)
            # The page hides a real <input type="file"> behind the drop zone;
            # set_input_files bypasses the drag-drop UI.
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(input_path))
            # Wait for any Plotly plot to render. The heatmap may take a
            # few seconds for large fixtures; bump timeout if needed.
            page.wait_for_selector(".js-plotly-plot", state="visible",
                                   timeout=20_000)
            # Plotly draws asynchronously; let the layout settle before
            # the screenshot. networkidle isn't enough — the data is
            # already in memory and the work is on the main thread.
            page.wait_for_timeout(1_500)
            plot = page.locator(".js-plotly-plot").first
            plot.screenshot(path=str(out_png))
        finally:
            browser.close()


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
    p.add_argument("--max-motifs", type=int, default=30,
                   help="global motif cap on the heatmap (matches both R's "
                        "max_motifs_in_plot and the frontend's maxMotifs knob)")
    p.add_argument("--unique-combination", action="store_true", default=True,
                   help="drop motif pairs that appear in multiple clusters "
                        "(matches the default in both pipelines)")
    p.add_argument("--no-unique-combination", dest="unique_combination",
                   action="store_false")
    p.add_argument("--report", default=str(DEFAULT_REPORT),
                   help="write diff report here (default: "
                        "results/tests/heatmap/consistency_report.txt)")
    p.add_argument("--render-dir", default=None,
                   help="when set, also render side-by-side PNGs of the R "
                        "and frontend heatmaps to <dir>/r.png and "
                        "<dir>/frontend.png. R needs Rscript on PATH. "
                        "Frontend needs the docker stack at --base-url and "
                        "Playwright (`pip install playwright && playwright "
                        "install chromium`); skipped with a hint if not "
                        "available.")
    p.add_argument("--base-url", default="http://localhost:5960",
                   help="frontend URL for visual capture (default: "
                        "http://localhost:5960; only used with --render-dir)")
    args = p.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return 2

    rows = parse_pmet_file(input_path)
    if not rows:
        print(f"ERROR: no rows parsed from {input_path}", file=sys.stderr)
        return 2

    ts_data = frontend_process(rows, args.p_adj_limit, args.max_motifs,
                               args.unique_combination)

    with tempfile.TemporaryDirectory() as td:
        r_json = Path(td) / "r.json"
        # The R driver still takes a `topn` arg for backwards compat
        # with older callers but ignores it inside ProcessPmetResult.
        # Pass any positive value; max_motifs is what actually drives
        # the motif selection on both sides.
        run_r_dump(input_path, args.p_adj_limit, 5,
                   args.unique_combination, args.max_motifs, r_json)
        r_data = json.loads(r_json.read_text())

    agrees, diff_lines = diff_pipelines(r_data, ts_data)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        f"# heatmap consistency report",
        f"# input:  {input_path.relative_to(REPO_ROOT) if input_path.is_relative_to(REPO_ROOT) else input_path}",
        f"# params: p_adj_limit={args.p_adj_limit} "
        f"unique={args.unique_combination} max_motifs={args.max_motifs}",
        f"# verdict: {'AGREE' if agrees else 'DIVERGE'}",
        "",
    ]
    report_path.write_text("\n".join(header + diff_lines) + "\n")

    print("\n".join(header + diff_lines))
    print(f"# wrote {report_path}")

    if args.render_dir:
        render_dir = Path(args.render_dir)
        render_dir.mkdir(parents=True, exist_ok=True)
        # R always rendered first — fast, dependency-light, and even if
        # the frontend capture fails we still want a usable artifact.
        try:
            render_r_png(input_path, render_dir / "r.png", args.max_motifs)
            print(f"# rendered {render_dir / 'r.png'}")
        except Exception as e:
            print(f"# R render skipped: {e}", file=sys.stderr)
        try:
            render_frontend_png(input_path, render_dir / "frontend.png",
                                args.base_url)
            print(f"# rendered {render_dir / 'frontend.png'}")
        except Exception as e:
            print(f"# frontend render skipped: {e}", file=sys.stderr)

    return 0 if agrees else 1


if __name__ == "__main__":
    sys.exit(main())
