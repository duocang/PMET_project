#!/bin/bash
#############################################
# pmetpair (parallel version) - Run Script
#############################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"

# Executable (prefer unified build directory)
EXECUTABLE="$PROJECT_ROOT/build/pmetpair"
if [ ! -f "$EXECUTABLE" ]; then
    EXECUTABLE="$PROJECT_DIR/build/pmetpair"
fi

if [ ! -f "$EXECUTABLE" ]; then
    echo "Error: pmetpair not found. Run: bash scripts/build.sh"
    exit 1
fi

# Default data paths
DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/data/cli/pairing/demo}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_DIR/result}"

# Input files
GENE_FILE="$DATA_DIR/gene.txt"
UNIVERSE_FILE="$DATA_DIR/universe.txt"
PROMOTER_LENGTHS="$DATA_DIR/promoter_lengths.txt"
BINOMIAL_THRESHOLDS="$DATA_DIR/binomial_thresholds.txt"
IC_FILE="$DATA_DIR/IC.txt"
FIMO_HITS_DIR="$DATA_DIR/fimohits"

# Parameters
EXCESS_FLAG="true"
IC_THRESHOLD=4
NUM_THREADS=8

echo "==> Running pmetpair (parallel version)..."
echo "    Executable: $EXECUTABLE"
echo "    Threads: $NUM_THREADS"
echo "    Output: $OUTPUT_DIR"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Filter genes by universe
grep -Ff "$UNIVERSE_FILE" "$GENE_FILE" > "$OUTPUT_DIR/gene.txttemp"

"$EXECUTABLE" \
    -x "$EXCESS_FLAG" \
    -d "$PROJECT_DIR" \
    -g "$OUTPUT_DIR/gene.txttemp" \
    -i $IC_THRESHOLD \
    -p "$PROMOTER_LENGTHS" \
    -b "$BINOMIAL_THRESHOLDS" \
    -c "$IC_FILE" \
    -f "$FIMO_HITS_DIR" \
    -t $NUM_THREADS \
    -o "$OUTPUT_DIR"

rm -f "$OUTPUT_DIR/gene.txttemp"

# Merge results
if ls "$OUTPUT_DIR"/temp*.txt 1>/dev/null 2>&1; then
    cat "$OUTPUT_DIR"/*.txt > "$OUTPUT_DIR/motif_output.txt"
    rm -f "$OUTPUT_DIR"/temp*.txt
fi

echo "✓ Done. Output: $OUTPUT_DIR"
