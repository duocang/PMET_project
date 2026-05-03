#!/bin/bash
# Fetch TAIR10 genome FASTA and GFF3 into the data directory.
#
# Resume / interrupt safety:
#   The done-marker is "the final file exists and is non-empty". To keep
#   that marker honest under Ctrl+C / SIGKILL / power loss, the gunzip
#   step writes to a `.partial` sidecar and only `mv`s onto the final
#   path on full success. `mv` on the same filesystem is a single
#   rename(2) syscall, so the final file is either complete or absent —
#   never half-written. Two cleanup hooks keep `.partial` files from
#   accumulating: one on entry (catches previous runs killed before
#   their EXIT trap could fire) and one EXIT trap (covers normal exit,
#   errexit, Ctrl+C, SIGTERM).
set -euo pipefail

script_dir=$(cd -- "$(dirname "$0")" && pwd)
ref_dir="$script_dir/../data/reference"

mkdir -p "$ref_dir"

cleanup_partials() { rm -f "$ref_dir"/*.partial 2>/dev/null || true; }
cleanup_partials
trap cleanup_partials EXIT

fasta="$ref_dir/TAIR10.fasta"
gff3="$ref_dir/TAIR10.gff3"

fetch_if_missing() {
    local url="$1"
    local dest="$2"
    local gz_tmp="$dest.gz.partial"
    local out_tmp="$dest.partial"

    if [[ -s "$dest" ]]; then
        echo "Found $(basename "$dest")"
        return
    fi

    echo "Downloading $(basename "$dest")..."
    # Stage the .gz next to the destination (same filesystem) so the
    # subsequent mv is a true atomic rename. curl --fail makes HTTP
    # errors (404, 504, ...) propagate as a non-zero exit.
    curl -L --fail --retry 3 "$url" -o "$gz_tmp"

    # Decompress into a sibling .partial file rather than directly onto
    # $dest. If gunzip is killed mid-write, the corrupt output stays as
    # `$dest.partial` (cleaned up by the trap) and `$dest` itself never
    # exists, so the next run's `[[ -s "$dest" ]]` check correctly
    # returns false and the file is re-fetched.
    gunzip -c "$gz_tmp" > "$out_tmp"

    # Atomic publish. After this line returns, $dest is fully readable.
    mv "$out_tmp" "$dest"
    rm -f "$gz_tmp"
    echo "Saved $(basename "$dest")"
}

fetch_if_missing "https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-56/fasta/arabidopsis_thaliana/dna/Arabidopsis_thaliana.TAIR10.dna.toplevel.fa.gz" "$fasta"
fetch_if_missing "https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-56/gff3/arabidopsis_thaliana/Arabidopsis_thaliana.TAIR10.56.gff3.gz" "$gff3"
