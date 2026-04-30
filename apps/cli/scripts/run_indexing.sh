#!/bin/bash
#############################################
# PMET Project - Run Indexing
# Purpose: Run PMET indexing with test data
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
VERSION="fused"
DATA_DIR="$PROJECT_ROOT/data/demos/promoters/indexing/demo"
RESULT_DIR="$PROJECT_ROOT/results/cli/demo/indexing"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
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
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -v, --version VERSION  Indexing version to run: fused (default: fused)"
            echo "  -d, --data DIR         Data directory (default: data/demos/promoters/indexing/demo)"
            echo "  -o, --output DIR       Output directory (default: results/cli/demo/indexing)"
            echo "  -h, --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_separator
echo -e "${GREEN}PMET Indexing Pipeline${NC}"
echo -e "Version: ${YELLOW}$VERSION${NC}"
print_separator

# Set executable path based on version (prefer root build/ directory)
case "$VERSION" in
    "fused")
        EXECUTABLE="$REPO_ROOT/build/index_fimo_fused"
        ;;
    *)
        print_error "Unknown version: $VERSION"
        exit 1
        ;;
esac

# Check executable
if [ ! -f "$EXECUTABLE" ]; then
    print_error "Executable not found: $EXECUTABLE"
    echo "Please run: make build"
    exit 1
fi

# Data files
PROMOTER_LENGTHS="$DATA_DIR/promoter_lengths.txt"
PROMOTERS_FA="$DATA_DIR/promoters.fa"
PROMOTERS_BG="$DATA_DIR/promoters.bg"
MOTIFS_FILE="$DATA_DIR/motifs.txt"

FIMO_DIR="$PROJECT_ROOT/results/cli/demo/fimo_official"

RESULT_DIR="$RESULT_DIR/$VERSION"
# Create output directory
rm -rf "$RESULT_DIR"
mkdir -p "$RESULT_DIR"

print_step "Running PMET Indexing..."

if [ "$VERSION" = "fused" ]; then
    # Fused FIMO version has different parameters
    "$EXECUTABLE" \
        --topk 5 \
        --topn 5000 \
        --no-qvalue \
        --text \
        --thresh 0.05 \
        --verbosity 1 \
        --bgfile "$PROMOTERS_BG" \
        --oc "$RESULT_DIR" \
        "$MOTIFS_FILE" \
        "$PROMOTERS_FA" \
        "$PROMOTER_LENGTHS"
else
    # 确保 FIMO 结果存在；缺失则自动生成
    if [ ! -d "$FIMO_DIR" ] || [ -z "$(ls -A "$FIMO_DIR" 2>/dev/null)" ]; then
        print_step "FIMO hits not found, generating via run_fimo_official.sh..."
        bash "$SCRIPT_DIR/run_fimo_official.sh"
    fi

    # Standard pmetindex (C or C++ version)
    "$EXECUTABLE" \
        -f "$FIMO_DIR" \
        -k 5 \
        -n 5000 \
        -p "$PROMOTER_LENGTHS" \
        -o "$RESULT_DIR"
fi

# Cleanup
rm -f progress.txt 2>/dev/null

print_separator
print_success "Indexing completed!"
echo -e "Results: ${YELLOW}$RESULT_DIR${NC}"
print_separator
