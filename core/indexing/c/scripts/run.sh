#!/bin/bash
#############################################
# pmetindex (C version) - Run Script
#############################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"

# Executable (prefer unified build directory)
EXECUTABLE="$PROJECT_ROOT/build/index_c"

# Default data paths (can be overridden via environment variables)
DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/data/cli/indexing/demo}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_DIR/result/pmetindex}"

# Parameters
FIMO_DIR="$DATA_DIR/fimo"
PROMOTER_LENGTHS="$DATA_DIR/promoter_lengths.txt"
TOP_K=5
TOP_N=5000

echo "==> Running pmetindex (C version)..."
echo "    Executable: $EXECUTABLE"
echo "    FIMO dir: $FIMO_DIR"
echo "    Output: $OUTPUT_DIR"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

"$EXECUTABLE" \
    -f "$FIMO_DIR" \
    -k $TOP_K \
    -n $TOP_N \
    -p "$PROMOTER_LENGTHS" \
    -o "$OUTPUT_DIR"

rm -f progress.txt 2>/dev/null

echo "✓ Done. Output: $OUTPUT_DIR"
