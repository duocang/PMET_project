#!/bin/bash
# ==============================================================================
# run_meme_fimo — drive MEME-suite's official `fimo` binary
# ==============================================================================
# Splits a combined MEME motif file into per-motif files and runs `fimo` once
# per motif (PMET's downstream indexers consume a directory of fimo hit files).
#
# Locates the `fimo` binary by walking PATH first, then a list of common MEME
# install prefixes. Errors out with a clear message if none are found.
#
# With no arguments, uses the project's bundled demo fixture under
# data/demos/promoters/indexing/demo/ — handy for sanity-checking a new MEME
# install or producing the reference fimo output for an indexer comparison.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# ==================== Defaults ====================

memefile="$REPO_ROOT/data/demos/promoters/indexing/demo/motifs.txt"
promoters="$REPO_ROOT/data/demos/promoters/indexing/demo/promoters.fa"
bgfile="$REPO_ROOT/data/demos/promoters/indexing/demo/promoters.bg"
outdir="$REPO_ROOT/results/cli/run_meme_fimo"
fimothresh=0.05

usage() {
    cat >&2 <<EOF
USAGE: run_meme_fimo.sh [options]

Run MEME-suite's official \`fimo\` per motif. Output: one file per motif name
under <outdir>/<motif>.txt (consumable by PMET's indexers).

Options:
  -m <memefile>      combined MEME motif file
                     (default: data/demos/promoters/indexing/demo/motifs.txt)
  -p <promoters>     FASTA sequence file
                     (default: data/demos/promoters/indexing/demo/promoters.fa)
  -b <bgfile>        background frequency file
                     (default: data/demos/promoters/indexing/demo/promoters.bg)
  -t <threshold>     fimo p-value threshold (default: 0.05)
  -o <outdir>        output directory       (default: results/cli/run_meme_fimo)
  -h                 show this help

The fimo binary is located by walking PATH then common MEME install
prefixes (\$HOME/meme/bin, /opt/meme/bin, /usr/local/meme/bin,
\$CONDA_PREFIX/bin, ...). Set PATH or PMET_FIMO_BIN to override.
EOF
}

while getopts ":m:p:b:t:o:h" opt; do
    case $opt in
        m) memefile=$OPTARG ;;
        p) promoters=$OPTARG ;;
        b) bgfile=$OPTARG ;;
        t) fimothresh=$OPTARG ;;
        o) outdir=$OPTARG ;;
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done

# ==================== Locate fimo ====================
# PATH first (covers Homebrew, manual installs that did update PATH, conda
# envs that are activated). Fall back to common MEME install prefixes for
# the typical "I installed MEME but never put it on PATH" case.

find_fimo() {
    if [[ -n "${PMET_FIMO_BIN:-}" && -x "$PMET_FIMO_BIN" ]]; then
        echo "$PMET_FIMO_BIN"; return 0
    fi
    if command -v fimo >/dev/null 2>&1; then
        command -v fimo; return 0
    fi
    local candidates=(
        "$HOME/meme/bin/fimo"
        "/opt/meme/bin/fimo"
        "/usr/local/meme/bin/fimo"
        "/opt/homebrew/opt/meme/bin/fimo"
        "/usr/local/opt/meme/bin/fimo"
        "/opt/homebrew/bin/fimo"
        "/usr/local/bin/fimo"
        "/usr/bin/fimo"
        "$HOME/.local/bin/fimo"
        "${CONDA_PREFIX:-}/bin/fimo"
        "$HOME/miniconda3/bin/fimo"
        "$HOME/anaconda3/bin/fimo"
        "$HOME/miniforge3/bin/fimo"
        "$HOME/mambaforge/bin/fimo"
    )
    for c in "${candidates[@]}"; do
        [[ -n "$c" && -x "$c" ]] && { echo "$c"; return 0; }
    done
    return 1
}

if ! FIMO_BIN=$(find_fimo); then
    echo "ERROR: fimo binary not found." >&2
    echo "       Install MEME-suite (https://meme-suite.org/) and either:" >&2
    echo "         - add its bin/ to PATH, or" >&2
    echo "         - set PMET_FIMO_BIN=/path/to/fimo" >&2
    exit 1
fi
echo "Using fimo: $FIMO_BIN"
"$FIMO_BIN" --version 2>&1 | head -1 || true

# ==================== Preflight ====================

for f in "$memefile" "$promoters" "$bgfile"; do
    [[ -f "$f" && -s "$f" ]] || { echo "ERROR: missing or empty: $f" >&2; exit 1; }
done

rm -rf "$outdir"
mkdir -p "$outdir"

# ==================== Split MEME file per motif ====================
# PMET indexers expect one fimo output file per motif name, so we split the
# combined memefile up front and call fimo once per motif. The header
# (everything before the first MOTIF line) is prepended to each split.

tmp_meme_dir=$(mktemp -d)
trap 'rm -rf "$tmp_meme_dir"' EXIT

awk -v TMP="$tmp_meme_dir" '
  /^MOTIF / {
    if (cur != "") close(cur)
    cur = TMP "/" $2 ".txt"
    printf "%s", header > cur
    print > cur
    next
  }
  cur == "" { header = header $0 "\n"; next }
  { print > cur }
' "$memefile"

# ==================== Run fimo ====================

echo "Running FIMO analysis (threshold: $fimothresh)..."
echo "  Memefile  : $memefile"
echo "  Sequences : $promoters"
echo "  Background: $bgfile"
echo "  Output    : $outdir"

for split in "$tmp_meme_dir"/*.txt; do
    name=$(basename "$split" .txt)
    echo "  Processing: $name"
    "$FIMO_BIN" --text \
        --thresh "$fimothresh" \
        --verbosity 1 \
        --bgfile "$bgfile" \
        "$split" \
        "$promoters" \
        > "$outdir/${name}.txt" 2>/dev/null
done

echo "Done."
echo "FIMO results saved to $outdir/"
