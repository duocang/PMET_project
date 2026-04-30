#!/bin/bash
#############################################
# PMET Project - Run Full Pipeline
# Purpose: Run complete PMET pipeline (indexing + pairing)
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
DATA_DIR="$PROJECT_ROOT/data"
RESULT_DIR="$PROJECT_ROOT/results/cli/demo/pipeline"
NUM_THREADS=8

# Indexing versions
INDEXING_VERSIONS=("c" "cpp" "fused")
INDEXING_DESCRIPTIONS=(
    "C version (index_c) - Fast and lightweight"
    "C++ version (pmetindex) - Feature-rich"
    "Fused version (index_fimo_fused) - Integrated FIMO"
)

# Parse arguments for non-interactive mode
INTERACTIVE=true
while [[ $# -gt 0 ]]; do
    case $1 in
        --indexing-version)
            INDEXING_VERSION="$2"
            INTERACTIVE=false
            shift 2
            ;;
        -d|--data)
            DATA_DIR="$2"
            shift 2
            ;;
        -o|--output)
            RESULT_DIR="$2"
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
            echo "  --indexing-version VER  Indexing version: c, cpp, or fused"
            echo "  -d, --data DIR          Data directory (default: data)"
            echo "  -o, --output DIR        Output directory (default: results/cli/demo)"
            echo "  -t, --threads NUM       Number of threads (default: 8)"
            echo "  -h, --help              Show this help message"
            echo ""
            echo "If --indexing-version is not provided, interactive mode is used."
            echo "Pairing always uses pair_parallel."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Interactive mode (only the indexing version needs picking)
if [ "$INTERACTIVE" = true ]; then
    print_separator
    echo -e "${GREEN}PMET Full Pipeline - Interactive Mode${NC}"
    print_separator
    echo ""

    echo -e "${YELLOW}Select Indexing Version${NC}"
    echo ""
    for i in "${!INDEXING_VERSIONS[@]}"; do
        echo -e "  ${CYAN}$((i+1))${NC}) ${INDEXING_DESCRIPTIONS[$i]}"
    done
    echo ""
    read -p "Enter your choice [1-${#INDEXING_VERSIONS[@]}]: " idx_choice

    if [[ ! "$idx_choice" =~ ^[1-${#INDEXING_VERSIONS[@]}]$ ]]; then
        print_error "Invalid choice. Exiting."
        exit 1
    fi
    INDEXING_VERSION="${INDEXING_VERSIONS[$((idx_choice-1))]}"
    echo ""
    print_success "Selected indexing: $INDEXING_VERSION"
    echo ""
fi

print_separator
echo -e "${GREEN}PMET Full Pipeline${NC}"
echo -e "Indexing: ${YELLOW}$INDEXING_VERSION${NC} | Pairing: ${YELLOW}pair_parallel${NC}"
print_separator

# Set up directories
INDEXING_RESULT_DIR="$RESULT_DIR/indexing"
PAIRING_RESULT_DIR="$RESULT_DIR/pairing"

# Create results directory
rm -rf "$RESULT_DIR"
mkdir -p "$RESULT_DIR"

#############################################
# Step 1: Run Indexing
#############################################
print_step "Step 1/2: Running Indexing ($INDEXING_VERSION)..."

bash "$SCRIPT_DIR/run_indexing.sh" \
    -v "$INDEXING_VERSION" \
    -d "$DATA_DIR/indexing/demo" \
    -o "$RESULT_DIR/indexing"

#############################################
# Step 2: Run Pairing (always pair_parallel)
# Use indexing results as input for pairing
#############################################
print_step "Step 2/2: Running Pairing..."

# Prepare pairing data directory with indexing results
PAIRING_DATA_DIR="$RESULT_DIR/pairing_input"
rm -rf "$PAIRING_DATA_DIR"
mkdir -p "$PAIRING_DATA_DIR"

# Copy/link required files from original pairing data
cp "$DATA_DIR/pairing/demo/gene.txt" "$PAIRING_DATA_DIR/"
cp "$DATA_DIR/pairing/demo/universe.txt" "$PAIRING_DATA_DIR/"
cp "$DATA_DIR/pairing/demo/IC.txt" "$PAIRING_DATA_DIR/"
cp "$DATA_DIR/pairing/demo/promoter_lengths.txt" "$PAIRING_DATA_DIR/"

# Use binomial_thresholds from indexing results
cp "$INDEXING_RESULT_DIR/${INDEXING_VERSION}/binomial_thresholds.txt" "$PAIRING_DATA_DIR/"

# Use fimohits from indexing results
cp -r "$INDEXING_RESULT_DIR/${INDEXING_VERSION}/fimohits" "$PAIRING_DATA_DIR/"

bash "$SCRIPT_DIR/run_pairing.sh" \
    -d "$PAIRING_DATA_DIR" \
    -o "$PAIRING_RESULT_DIR" \
    -t "$NUM_THREADS"

# # Cleanup temporary pairing input directory
# rm -rf "$PAIRING_DATA_DIR"

# print_separator
# print_success "Full pipeline completed!"
# echo ""
# echo "Configuration:"
# echo -e "  Indexing version: ${YELLOW}$INDEXING_VERSION${NC}"
# echo -e "  Pairing version:  ${YELLOW}$PAIRING_VERSION${NC}"
# echo ""
# echo "Results:"
# echo -e "  Indexing: ${YELLOW}$INDEXING_RESULT_DIR${NC}"
# echo -e "  Pairing:  ${YELLOW}$PAIRING_RESULT_DIR${NC}"
# print_separator
