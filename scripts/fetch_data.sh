#!/usr/bin/env bash
#
# Fetch the files the full-promoters analysis expects to find:
#   - data/reference/TAIR10.fasta            (Ensembl Plants release 56, Arabidopsis thaliana)
#   - data/reference/TAIR10.gff3             (matching annotation)
#   - data/precomputed_indexes/<species>/    (pre-computed PMET indexes; reusable
#                                             by both the web app and CLI's
#                                             pair_only.sh; kept apart from
#                                             demo / bench data under data/demos/)
#
# Safe to re-run; anything already present is skipped.

set -euo pipefail

# Resolve project root regardless of cwd at invocation; script lives one
# level under the repo root.
SCRIPT_DIR=$(cd -- "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR/.."

REF_DIR="data/reference"
INDEX_DIR="data/precomputed_indexes"
mkdir -p "$REF_DIR" "$INDEX_DIR"

log() { printf '\n>>> %s\n' "$*"; }

# ---- TAIR10 reference (Arabidopsis thaliana) ----
# Delegated to fetch_reference.sh — single source of truth for URLs +
# gunzip semantics. fetch_reference.sh writes to the same data/reference
# path, so anything we do downstream sees the same files.
log "Fetching TAIR10 reference"
bash "$SCRIPT_DIR/fetch_reference.sh"

# ---- Pre-computed PMET indexing archives (Zenodo) ----
urls=(
    "https://zenodo.org/record/8435321/files/Arabidopsis_thaliana.tar.gz"
    "https://zenodo.org/record/8435321/files/Brachypodium_distachyon.tar.gz"
    "https://zenodo.org/record/8435321/files/Brassica_napus.tar.gz"
    "https://zenodo.org/record/8435321/files/Glycine_max.tar.gz"
    "https://zenodo.org/record/8435321/files/Hordeum_vulgare_goldenpromise.tar.gz"
    "https://zenodo.org/record/8435321/files/Hordeum_vulgare_Morex_V3.tar.gz"
    "https://zenodo.org/record/8435321/files/Hordeum_vulgare_R1.tar.gz"
    "https://zenodo.org/record/8435321/files/Hordeum_vulgare_v082214v1.tar.gz"
    "https://zenodo.org/record/8435321/files/Medicago_truncatula.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_indica_9311.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_indica_IR8.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_indica_MH63.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_indica_ZS97.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_japonica_Ensembl.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_japonica_Kitaake.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_japonica_Nipponbare.tar.gz"
    "https://zenodo.org/record/8435321/files/Oryza_sativa_japonica_V7.1.tar.gz"
    "https://zenodo.org/record/8435321/files/Solanum_lycopersicum.tar.gz"
    "https://zenodo.org/record/8435321/files/Solanum_tuberosum.tar.gz"
    "https://zenodo.org/record/8435321/files/Triticum_aestivum.tar.gz"
    "https://zenodo.org/record/8435321/files/Zea_mays.tar.gz"
)

failed=()
for url in "${urls[@]}"; do
    species=$(basename "$url" .tar.gz)
    tarball="$INDEX_DIR/$species.tar.gz"
    if [[ -d "$INDEX_DIR/$species" ]]; then
        log "Already have indexing for ${species//_/ }, skipping"
        continue
    fi
    log "Downloading indexing for ${species//_/ }"
    # Don't let one species' network/tar failure abort the whole batch;
    # collect the names and report at the end.
    if ! curl -fL --progress-bar "$url" -o "$tarball"; then
        log "Download failed for ${species//_/ }"
        rm -f "$tarball"
        failed+=("$species")
        continue
    fi
    if ! tar -xzf "$tarball" -C "$INDEX_DIR"; then
        log "Extraction failed for ${species//_/ }"
        rm -f "$tarball"
        rm -rf "${INDEX_DIR:?}/$species"
        failed+=("$species")
        continue
    fi
    rm -f "$tarball"
done

if (( ${#failed[@]} > 0 )); then
    log "Done with errors. Failed species: ${failed[*]}"
    log "Re-run the script to retry. Files under $REF_DIR/ and $INDEX_DIR/"
    exit 1
fi

log "Done. Files under $REF_DIR/ and $INDEX_DIR/"
