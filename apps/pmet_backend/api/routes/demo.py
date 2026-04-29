from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...config import config

router = APIRouter(prefix="/demo", tags=["demo"])


# (mode, kind) -> (path under data/, public filename)
# Public filename mirrors the real file on disk so users immediately see
# what they've loaded (e.g. TAIR10.fasta, peaks.txt) rather than a generic
# `example_*` placeholder.
DEMO_FILES: dict[tuple[str, str], tuple[str, str]] = {
    ("promoters_pre", "genes"): ("demos/promoters/example_genes.txt", "example_genes.txt"),
    ("promoters", "genes"):     ("demos/promoters/example_genes.txt", "example_genes.txt"),
    ("promoters", "fasta"):     ("reference/TAIR10.fasta",            "TAIR10.fasta"),
    ("promoters", "gff3"):      ("reference/TAIR10.gff3",             "TAIR10.gff3"),
    ("promoters", "meme"):      ("demos/promoters/example_motif.meme", "example_motif.meme"),
    ("intervals", "genes"):     ("demos/intervals/peaks.txt",         "peaks.txt"),
    ("intervals", "fasta"):     ("demos/intervals/intervals.fa",      "intervals.fa"),
    ("intervals", "meme"):      ("demos/intervals/motif.meme",        "motif.meme"),
}


@router.get("/example-result")
async def get_example_result():
    full = config.PROJECT_ROOT / "data" / "demos" / "results" / "example_pmet_result.txt"
    if not full.exists():
        raise HTTPException(status_code=404, detail="Example result file missing on server")
    return FileResponse(path=str(full), filename="example_pmet_result.txt", media_type="text/plain")


@router.get("/{mode}/{kind}")
async def get_demo_file(mode: str, kind: str):
    entry = DEMO_FILES.get((mode, kind))
    if not entry:
        raise HTTPException(status_code=404, detail="No demo file for this slot")

    rel_path, public_name = entry
    full = config.PROJECT_ROOT / "data" / rel_path
    if not full.exists():
        raise HTTPException(status_code=404, detail="Demo file missing on server")

    return FileResponse(path=str(full), filename=public_name, media_type="application/octet-stream")
