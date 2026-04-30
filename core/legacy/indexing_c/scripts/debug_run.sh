#!/bin/bash
# Run PMET indexing with debug build (AddressSanitizer enabled)

set -e

# Change to project root
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Config
PROMOTER_LENGTHS=data/promoter_lengths.txt
FIMO_DIR=data/fimo
OUTPUT_DIR=result/pmetindex_debug
N_GENES=100  # smaller dataset for debugging

# Sanitizer options
export ASAN_OPTIONS="halt_on_error=1:abort_on_error=1"

# Check executable
if [ ! -f "./build/pmetindex_debug" ]; then
    echo "Error: ./build/pmetindex_debug not found. Run: bash scripts/debug_build.sh"
    exit 1
fi

# Run
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

echo "Running debug version (n=$N_GENES)..."
./build/pmetindex_debug \
    -f "$FIMO_DIR" \
    -k 5 \
    -n "$N_GENES" \
    -p "$PROMOTER_LENGTHS" \
    -o "$OUTPUT_DIR"

rm progress.txt 2>/dev/null

echo "Done. Exit code: $?"