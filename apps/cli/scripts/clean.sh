#!/bin/bash
#############################################
# PMET Project - Clean Script
# Purpose: Clean build artifacts and results
#############################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Resolve repo root (apps/cli/scripts/X.sh -> ../../..)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT"

print_step() {
    echo -e "${YELLOW}>>> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Parse arguments
CLEAN_TARGET="all"
if [ "$1" != "" ]; then
    CLEAN_TARGET="$1"
fi

echo -e "${BLUE}================================================================${NC}"
echo -e "${GREEN}PMET Project - Clean${NC}"
echo -e "Target: ${YELLOW}$CLEAN_TARGET${NC}"
echo -e "${BLUE}================================================================${NC}"

clean_builds() {
    print_step "Cleaning build directories..."
    rm -rf "$REPO_ROOT/build"
    rm -rf "$REPO_ROOT/core/indexing/build"
    rm -rf "$REPO_ROOT/core/pairing/build"
    print_success "Build directories cleaned"
}

clean_results() {
    print_step "Cleaning result directories..."
    rm -rf "$REPO_ROOT/results/cli/demo"
    print_success "Result directories cleaned"
}

clean_temp() {
    print_step "Cleaning temporary files..."
    find "$PROJECT_ROOT" -name "*.o" -delete 2>/dev/null || true
    find "$PROJECT_ROOT" -name "*.log" -delete 2>/dev/null || true
    find "$PROJECT_ROOT" -name "progress.txt" -delete 2>/dev/null || true
    find "$PROJECT_ROOT" -name ".DS_Store" -delete 2>/dev/null || true
    print_success "Temporary files cleaned"
}

case "$CLEAN_TARGET" in
    "all")
        clean_builds
        clean_results
        clean_temp
        ;;
    "builds")
        clean_builds
        ;;
    "results")
        clean_results
        ;;
    "temp")
        clean_temp
        ;;
    *)
        echo "Usage: $0 [target]"
        echo ""
        echo "Targets:"
        echo "  all     - Clean everything (default)"
        echo "  builds  - Clean build directories only"
        echo "  results - Clean result directories only"
        echo "  temp    - Clean temporary files only"
        exit 1
        ;;
esac

echo -e "${BLUE}================================================================${NC}"
print_success "Cleaning completed!"
echo -e "${BLUE}================================================================${NC}"
