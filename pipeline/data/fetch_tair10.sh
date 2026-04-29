#!/bin/bash
# Fetch TAIR10 genome FASTA and GFF3 into the data directory.
set -euo pipefail

script_dir=$(cd -- "$(dirname "$0")" && pwd)
ref_dir="$script_dir/../../data/reference"

mkdir -p "$ref_dir"

fasta="$ref_dir/TAIR10.fasta"
gff3="$ref_dir/TAIR10.gff3"

fetch_if_missing() {
    local url="$1"
    local dest="$2"
    local tmp="$dest.gz"

    if [[ -s "$dest" ]]; then
        echo "Found $(basename "$dest")"
        return
    fi

    echo "Downloading $(basename "$dest")..."
    curl -L --fail --retry 3 "$url" -o "$tmp"
    gunzip -c "$tmp" > "$dest"
    rm -f "$tmp"
    echo "Saved $(basename "$dest")"
}

fetch_if_missing "https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-56/fasta/arabidopsis_thaliana/dna/Arabidopsis_thaliana.TAIR10.dna.toplevel.fa.gz" "$fasta"
fetch_if_missing "https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-56/gff3/arabidopsis_thaliana/Arabidopsis_thaliana.TAIR10.56.gff3.gz" "$gff3"
