from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from ...config import config

router = APIRouter(prefix="/demo", tags=["demo"])

# Hard cap on lines a single preview request will return — TAIR10.fasta
# is ~120 MB and TAIR10.gff3 is ~50 MB, so we never want a curious caller
# to drag the whole file through this endpoint. 5000 is comfortably more
# than fits in any reasonable preview drawer.
_PREVIEW_LINES_CAP = 5000


# (mode, kind) -> (path under data/, public filename)
# Public filename mirrors the real file on disk so users immediately see
# what they've loaded (e.g. TAIR10.fasta, peaks.txt) rather than a generic
# `example_*` placeholder.
DEMO_FILES: dict[tuple[str, str], tuple[str, str]] = {
    ("promoters_pre", "genes"): ("genes/genes_cell_type_treatment.txt",      "genes_cell_type_treatment.txt"),
    ("promoters", "genes"):     ("genes/genes_cell_type_treatment.txt",      "genes_cell_type_treatment.txt"),
    ("promoters", "fasta"):     ("reference/TAIR10.fasta",                   "TAIR10.fasta"),
    ("promoters", "gff3"):      ("reference/TAIR10.gff3",                    "TAIR10.gff3"),
    ("promoters", "meme"):      ("motifs/Franco-Zorrilla_et_al_2014.meme",   "Franco-Zorrilla_et_al_2014.meme"),
    ("intervals", "genes"):     ("demos/intervals/indexing/peaks.txt",       "peaks.txt"),
    ("intervals", "fasta"):     ("demos/intervals/indexing/intervals.fa",    "intervals.fa"),
    ("intervals", "meme"):      ("demos/intervals/indexing/motif.meme",      "motif.meme"),
}


@router.get("/example-result")
async def get_example_result():
    full = config.PROJECT_ROOT / "data" / "demos" / "results" / "example_pmet_result.txt"
    if not full.exists():
        raise HTTPException(status_code=404, detail="Example result file missing on server")
    return FileResponse(path=str(full), filename="example_pmet_result.txt", media_type="text/plain")


@router.get("/{mode}/{kind}/preview")
async def get_demo_preview(mode: str, kind: str, lines: int = 200):
    """Stream the first ``lines`` lines of the demo file as plain text.

    Powers the side-drawer "view example" preview without forcing the
    client to download a multi-hundred-megabyte FASTA/GFF3. ``lines`` is
    clamped to [1, _PREVIEW_LINES_CAP].
    Three-segment path so it slots in front of the two-segment download
    route below without ordering games.
    """
    entry = DEMO_FILES.get((mode, kind))
    if not entry:
        raise HTTPException(status_code=404, detail="No demo file for this slot")
    rel_path, _ = entry
    full = config.PROJECT_ROOT / "data" / rel_path
    if not full.exists():
        raise HTTPException(status_code=404, detail="Demo file missing on server")

    n = max(1, min(int(lines), _PREVIEW_LINES_CAP))
    out: list[str] = []
    with full.open("r", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= n:
                break
            out.append(line)
    return PlainTextResponse("".join(out))


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
