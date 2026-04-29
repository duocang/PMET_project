import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from ...config import config

router = APIRouter(prefix="/indexing", tags=["indexing"])

# Names of files/dirs that are NOT motif databases but can live under a
# species directory (e.g. the background gene universe).
_NON_DB_NAMES = {"universe.txt"}

# How many sample entries to return in detail responses.
_GENE_SAMPLE_SIZE = 5
_MOTIF_SAMPLE_SIZE = 5


def _humanize(name: str) -> str:
    return name.replace("_", " ")


def _load_metadata() -> dict:
    """Load the per-species fixed-parameter record.

    Re-read on every request so operators can edit
    data/app/indexing_metadata.json live without restarting the API.
    Missing file, bad JSON, or non-dict values are all tolerated — we
    just return an empty map and the UI shows no Fixed-parameter panel.
    """
    path = config.PRECOMPUTED_INDEXING_METADATA
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # Keep only real species entries (skip `_note` / `_fields` docs).
    return {k: v for k, v in raw.items() if isinstance(v, dict) and not k.startswith("_")}


def _load_genome_metadata() -> dict:
    """Load data/app/genome_n_annotation.json with the same live-reload
    semantics as the indexing metadata loader."""
    path = config.GENOME_METADATA
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _fixed_params_for(metadata: dict, species: str, motif_db: str) -> dict:
    """Resolve fixed params with optional per-motif-db override."""
    entry = metadata.get(species)
    if not entry:
        return {}
    overrides = entry.get("by_motif_db", {})
    merged = {k: v for k, v in entry.items() if k != "by_motif_db"}
    if isinstance(overrides, dict):
        merged.update(overrides.get(motif_db, {}))
    return merged


def _safe_component(name: str) -> str:
    """Reject path components that could escape the indexing root."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid path component")
    return name


def _read_universe(species_dir: Path) -> tuple[int, list[str]]:
    """Return (gene_count, first-N sample) from universe.txt, or (0, [])."""
    path = species_dir / "universe.txt"
    if not path.exists():
        return 0, []
    try:
        with path.open() as fh:
            sample: list[str] = []
            count = 0
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                count += 1
                if len(sample) < _GENE_SAMPLE_SIZE:
                    sample.append(line)
        return count, sample
    except OSError:
        return 0, []


def _read_fimohits(db_dir: Path) -> tuple[int, list[str]]:
    """Return (motif_count, first-N motif names) from db_dir/fimohits/.

    Each motif hits file is one motif; the filename (minus the last
    extension) is the motif name.
    """
    hits_dir = db_dir / "fimohits"
    if not hits_dir.is_dir():
        return 0, []
    try:
        names = sorted(p.stem for p in hits_dir.iterdir() if p.is_file())
    except OSError:
        return 0, []
    return len(names), names[:_MOTIF_SAMPLE_SIZE]


@router.get("")
async def list_indexing():
    """List available pre-computed indexing databases.

    Scans data/app/indexing/<species>/<motif_db>/ and returns one entry per
    (species, motif_db) pair so the submit page can populate the
    pre-computed database dropdown without hard-coding.
    """
    root = config.PRECOMPUTED_INDEXING_DIR
    metadata = _load_metadata()
    entries: list[dict] = []
    if not root.exists():
        return {"entries": entries}

    for species_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for db_dir in sorted(p for p in species_dir.iterdir()
                             if p.is_dir() and p.name not in _NON_DB_NAMES):
            rel = f"data/app/indexing/{species_dir.name}/{db_dir.name}"
            entries.append({
                "value": rel,
                "species": species_dir.name,
                "motif_db": db_dir.name,
                "label": f"{_humanize(species_dir.name)} — {_humanize(db_dir.name)}",
                "fixed_params": _fixed_params_for(metadata, species_dir.name, db_dir.name),
            })
    return {"entries": entries}


def _species_block(species: str, species_meta: dict, species_dir: Path) -> dict:
    gene_count, gene_sample = _read_universe(species_dir)
    return {
        "name": species,
        "humanized": _humanize(species),
        "description": species_meta.get("description") or None,
        "genome_name": species_meta.get("genome_name") or None,
        "genome_link": species_meta.get("genome_link") or None,
        "annotation_name": species_meta.get("annotation_name") or None,
        "annotation_link": species_meta.get("annotation_link") or None,
        "gene_count": gene_count,
        "gene_sample": gene_sample,
    }


@router.get("/{species}")
async def get_species_detail(species: str):
    """Species-level detail for the submit-form expandable panel.

    Resolvable the moment a species is chosen — does not require the
    user to also pick a motif database.
    """
    species = _safe_component(species)
    species_dir = config.PRECOMPUTED_INDEXING_DIR / species
    if not species_dir.is_dir():
        raise HTTPException(status_code=404, detail="Species not found")

    genome_meta = _load_genome_metadata()
    species_meta_raw = genome_meta.get(species)
    species_meta: dict = species_meta_raw if isinstance(species_meta_raw, dict) else {}

    return {"species": _species_block(species, species_meta, species_dir)}


@router.get("/{species}/{motif_db}")
async def get_motif_db_detail(species: str, motif_db: str):
    """Motif-database-level detail (counts, source URL) for the
    submit-form expandable panel. Species block is served separately by
    get_species_detail so it can load the moment a species is picked.
    """
    species = _safe_component(species)
    motif_db = _safe_component(motif_db)

    species_dir = config.PRECOMPUTED_INDEXING_DIR / species
    db_dir = species_dir / motif_db
    if not species_dir.is_dir() or not db_dir.is_dir():
        raise HTTPException(status_code=404, detail="Species or motif_db not found")

    genome_meta = _load_genome_metadata()
    species_meta_raw = genome_meta.get(species)
    species_meta: dict = species_meta_raw if isinstance(species_meta_raw, dict) else {}
    motif_db_links_raw = species_meta.get("motif_db")
    motif_db_links: dict = motif_db_links_raw if isinstance(motif_db_links_raw, dict) else {}

    motif_count, motif_sample = _read_fimohits(db_dir)

    # Resolve source link with case-insensitive fallback since metadata
    # keys sometimes differ in casing from the directory name.
    source_link: Optional[str] = motif_db_links.get(motif_db)
    if source_link is None:
        lookup = {k.lower(): v for k, v in motif_db_links.items()}
        source_link = lookup.get(motif_db.lower())

    return {
        "motif_db": {
            "name": motif_db,
            "humanized": _humanize(motif_db),
            "source_link": source_link,
            "motif_count": motif_count,
            "motif_sample": motif_sample,
        },
    }
