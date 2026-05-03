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

# Staging root for in-flight downloads and extractions. Lives next to
# (NOT inside) INDEX_DIR for two reasons:
#   1. The web backend's species scan iterates `precomputed_indexes/*`
#      and treats every directory it finds as an available species (see
#      apps/pmet_backend/api/routes/indexing.py). Putting partial state
#      anywhere under INDEX_DIR would expose half-extracted species in
#      the submit-page dropdown.
#   2. Same filesystem as INDEX_DIR, so the final `mv` to publish a
#      finished species is an atomic rename(2) rather than a copy.
STAGING_ROOT="data/.precomputed_indexes_staging"

mkdir -p "$REF_DIR" "$INDEX_DIR"

# Two cleanup hooks ensure the staging root is never left lying around:
#   1. Wipe on entry — clears anything left behind by a previous run that
#      was killed before its EXIT trap could fire (e.g. kill -9, OOM,
#      power loss). Without this, leftover staging would just accumulate.
#   2. Wipe on EXIT — bash runs EXIT traps on every exit path, including
#      normal completion, errexit failures, Ctrl+C (SIGINT) and SIGTERM,
#      so a single trap handles all the "graceful" cleanup cases.
rm -rf "$STAGING_ROOT"
mkdir -p "$STAGING_ROOT"
trap 'rm -rf "$STAGING_ROOT"' EXIT

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
    if [[ -d "$INDEX_DIR/$species" ]]; then
        log "Already have indexing for ${species//_/ }, skipping"
        continue
    fi
    log "Downloading indexing for ${species//_/ }"

    # Per-species staging dir. Both the .tar.gz and the extracted tree
    # live here while the work is in flight, so a single `rm -rf` wipes
    # everything for this species regardless of which step failed.
    # mktemp's random suffix prevents collisions if a previous run's
    # cleanup somehow missed this species' staging dir.
    staging=$(mktemp -d "$STAGING_ROOT/${species}.XXXXXX")
    tarball="$staging/$species.tar.gz"

    # Don't let one species' network/tar failure abort the whole batch;
    # collect the names and report at the end so the user knows what to
    # retry. INDEX_DIR is left untouched on failure — there is no partial
    # state to clean up there because we only publish on full success.
    if ! curl -fL --progress-bar "$url" -o "$tarball"; then
        log "Download failed for ${species//_/ }"
        rm -rf "$staging"
        failed+=("$species")
        continue
    fi
    if ! tar -xzf "$tarball" -C "$staging"; then
        log "Extraction failed for ${species//_/ }"
        rm -rf "$staging"
        failed+=("$species")
        continue
    fi
    # Defensive: every Zenodo tarball in this list extracts a top-level
    # `<species>/` directory. If a future tarball has a different layout
    # we want to know up front rather than silently producing nothing.
    if [[ ! -d "$staging/$species" ]]; then
        log "Tarball did not contain expected directory '$species/' for ${species//_/ }"
        rm -rf "$staging"
        failed+=("$species")
        continue
    fi

    # Atomic publish: on the same filesystem, `mv` is a single rename(2)
    # syscall, so the species directory either appears complete under
    # INDEX_DIR or not at all. This is what keeps the app from ever
    # observing a half-built species, even if the script is killed
    # immediately after this line.
    if ! mv "$staging/$species" "$INDEX_DIR/$species"; then
        log "Failed to publish ${species//_/ } into $INDEX_DIR"
        rm -rf "$staging"
        failed+=("$species")
        continue
    fi
    rm -rf "$staging"
done

if (( ${#failed[@]} > 0 )); then
    log "Done with errors. Failed species: ${failed[*]}"
    log "Re-run the script to retry. Files under $REF_DIR/ and $INDEX_DIR/"
    exit 1
fi

log "Done. Files under $REF_DIR/ and $INDEX_DIR/"
