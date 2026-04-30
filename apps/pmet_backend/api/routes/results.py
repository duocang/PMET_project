from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
import csv
from typing import Optional

from ...config import config

router = APIRouter(prefix="/results", tags=["results"])


def _find_output_file(task_id: str) -> Path:
    result_dir = config.RESULT_DIR / task_id
    if not result_dir.exists():
        raise HTTPException(status_code=404, detail="Results not found")

    # New layout: results/app/<task_id>/pairing/motif_output.txt. Older runs
    # wrote it flat — keep flat paths as fallbacks so historical tasks
    # remain readable.
    candidates = (
        result_dir / "pairing" / "motif_output.txt",
        result_dir / "motif_output.txt",
        result_dir / "PMET_OUTPUT.txt",
    )
    for path in candidates:
        if path.exists():
            return path

    raise HTTPException(status_code=404, detail="Output file not found")


def _parse_row(row: list[str]) -> dict:
    return {
        "cluster": row[0] if len(row) > 0 else "",
        "motif1": row[1] if len(row) > 1 else "",
        "motif2": row[2] if len(row) > 2 else "",
        "gene_num": int(row[3]) if len(row) > 3 else 0,
        "total_genes": int(row[4]) if len(row) > 4 else 0,
        "cluster_genes": int(row[5]) if len(row) > 5 else 0,
        "p_value": float(row[6]) if len(row) > 6 else 1.0,
        "p_adj_bh": float(row[7]) if len(row) > 7 else 1.0,
        "p_adj_bonf": float(row[8]) if len(row) > 8 else 1.0,
        "p_adj_global": float(row[9]) if len(row) > 9 else 1.0,
        "genes": [g for g in row[10].split(";") if g] if len(row) > 10 and row[10] else [],
    }


@router.get("/{task_id}")
async def get_task_results(
    task_id: str,
    cluster: Optional[str] = None,
    p_adj_max: float = Query(1.0, description="Max adjusted p-value (BH) filter"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    output_file = _find_output_file(task_id)

    try:
        results = []
        total_matched = 0
        with open(output_file, newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader, None)

            for row in reader:
                if len(row) < 8:
                    continue
                if cluster and row[0] != cluster:
                    continue
                try:
                    p_bh = float(row[7])
                except ValueError:
                    continue
                if p_bh > p_adj_max:
                    continue

                total_matched += 1
                if total_matched > offset and len(results) < limit:
                    results.append(_parse_row(row))

        return {
            "task_id": task_id,
            "total_matched": total_matched,
            "offset": offset,
            "limit": limit,
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse results: {str(e)}")


@router.get("/{task_id}/summary")
async def get_result_summary(task_id: str):
    output_file = _find_output_file(task_id)

    try:
        clusters: dict[str, int] = {}
        motifs: set[str] = set()
        total_pairs = 0
        significant_005 = 0
        num_bins = 50
        hist_bins = [0] * num_bins

        with open(output_file, newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader, None)

            for row in reader:
                if len(row) < 8:
                    continue
                total_pairs += 1
                c = row[0]
                clusters[c] = clusters.get(c, 0) + 1
                motifs.add(row[1])
                motifs.add(row[2])
                try:
                    p_bh = float(row[7])
                except ValueError:
                    continue
                if p_bh < 0.05:
                    significant_005 += 1
                bin_idx = min(int(p_bh * num_bins), num_bins - 1)
                hist_bins[bin_idx] += 1

        bin_edges = [i / num_bins for i in range(num_bins + 1)]

        return {
            "task_id": task_id,
            "total_pairs": total_pairs,
            "num_clusters": len(clusters),
            "clusters": [{"name": k, "count": v} for k, v in sorted(clusters.items())],
            "num_unique_motifs": len(motifs),
            "significant_pairs_005": significant_005,
            "histogram": {"bin_edges": bin_edges, "counts": hist_bins},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse results: {str(e)}")


@router.get("/{task_id}/genes-used")
async def get_genes_used(task_id: str):
    result_dir = config.RESULT_DIR / task_id

    # Prefer the new layout; fall back to flat for legacy tasks.
    pairing_dir = result_dir / "pairing"
    base = pairing_dir if pairing_dir.exists() else result_dir
    genes_used_file = base / "genes_used_PMET.txt"
    genes_not_found_file = base / "genes_not_found.txt"

    result = {
        "task_id": task_id,
        "genes_used": [],
        "genes_not_found": [],
    }

    if genes_used_file.exists():
        result["genes_used"] = [g for g in genes_used_file.read_text().strip().split("\n") if g]

    if genes_not_found_file.exists():
        result["genes_not_found"] = [g for g in genes_not_found_file.read_text().strip().split("\n") if g]

    return result
