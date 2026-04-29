#!/bin/bash
#############################################
# PMET Project - Run Pairing
# Purpose: Run PMET pairing with test data
#############################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Resolve repo root (apps/cli/scripts/X.sh -> ../../..)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT"

print_separator() {
    echo -e "${BLUE}================================================================${NC}"
}

print_step() {
    echo -e "${CYAN}>>> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Default configuration
DATA_DIR="$PROJECT_ROOT/data/demos/promoters/pairing/demo"
RESULT_DIR="$PROJECT_ROOT/results/demo/pairing"
IC_THRESHOLD=4
NUM_THREADS=2

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--data)
            DATA_DIR="$2"
            shift 2
            ;;
        -o|--output)
            RESULT_DIR="$2"
            shift 2
            ;;
        -i|--ic-threshold)
            IC_THRESHOLD="$2"
            shift 2
            ;;
        -t|--threads)
            NUM_THREADS="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -d, --data DIR           Data directory (default: data/demos/promoters/pairing/demo)"
            echo "  -o, --output DIR         Output directory (default: results/demo/pairing)"
            echo "  -i, --ic-threshold VAL   IC threshold (default: 4)"
            echo "  -t, --threads NUM        Number of threads (default: 2)"
            echo "  -h, --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_separator
echo -e "${GREEN}PMET Pairing Pipeline${NC}"
print_separator

EXECUTABLE="$REPO_ROOT/build/pair_parallel"
if [ ! -f "$EXECUTABLE" ]; then
    print_error "Executable not found: $EXECUTABLE"
    echo "Please run: bash core/scripts/build_all.sh pair-parallel"
    exit 1
fi

# Data files
GENE_FILE="$DATA_DIR/gene.txt"
UNIVERSE_FILE="$DATA_DIR/universe.txt"
PROMOTER_LENGTHS_FILE="$DATA_DIR/promoter_lengths.txt"
BINOMIAL_THRESHOLDS_FILE="$DATA_DIR/binomial_thresholds.txt"
IC_FILE="$DATA_DIR/IC.txt"
FIMO_HITS_DIR="$DATA_DIR/fimohits"

# Create output directory
rm -rf "$RESULT_DIR"
mkdir -p "$RESULT_DIR"

print_step "Preparing gene list..."
# Remove genes not present in pre-computed pmet index (universe.txt)
grep -Ff "$UNIVERSE_FILE" "$GENE_FILE" > "$RESULT_DIR/gene.txttemp"

print_step "Running PMET Pairing..."

"$EXECUTABLE" \
    -d "/" \
    -x "true" \
    -g "$RESULT_DIR/gene.txttemp" \
    -i "$IC_THRESHOLD" \
    -p "$PROMOTER_LENGTHS_FILE" \
    -b "$BINOMIAL_THRESHOLDS_FILE" \
    -c "$IC_FILE" \
    -f "$FIMO_HITS_DIR" \
    -t "$NUM_THREADS" \
    -o "$RESULT_DIR"

# Merge per-thread temp output
if ls "$RESULT_DIR"/temp*.txt 1>/dev/null 2>&1; then
    cat "$RESULT_DIR"/temp*.txt > "$RESULT_DIR/motif_output.txt"
    rm -f "$RESULT_DIR"/temp*.txt
fi

# Cleanup
rm -f "$RESULT_DIR/gene.txttemp"

print_separator
print_success "Pairing completed!"
echo -e "Results: ${YELLOW}$RESULT_DIR${NC}"
print_separator
