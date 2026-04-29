#!/bin/bash
#############################################
# fimo (fused version) - Run Script
#############################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"

# Executable (prefer unified build directory)
EXECUTABLE="$PROJECT_ROOT/build/index_fimo_fused"

# Default data paths
DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/data/cli/indexing/demo}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_DIR/result}"

# Parameters
TOP_K=5
TOP_N=5000
FIMO_THRESH=0.05

# Input files
BG_FILE="$DATA_DIR/promoters.bg"
MOTIF_FILE="$DATA_DIR/motifs.txt"
SEQUENCE_FILE="$DATA_DIR/promoters.fa"
PROMOTER_LENGTHS="$DATA_DIR/promoter_lengths.txt"

echo "==> Running fimo (fused version)..."
echo "    Executable: $EXECUTABLE"
echo "    Output: $OUTPUT_DIR"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/fimo_custom"

"$EXECUTABLE" \
    --topk $TOP_K \
    --topn $TOP_N \
    --no-qvalue \
    --text \
    --thresh $FIMO_THRESH \
    --verbosity 1 \
    --bgfile "$BG_FILE" \
    --oc "$OUTPUT_DIR/fimo_custom" \
    "$MOTIF_FILE" \
    "$SEQUENCE_FILE" \
    "$PROMOTER_LENGTHS" > "$OUTPUT_DIR/log.txt" 2>&1

rm -f "$OUTPUT_DIR/log.txt" progress.txt 2>/dev/null

echo "✓ Done. Output: $OUTPUT_DIR"
