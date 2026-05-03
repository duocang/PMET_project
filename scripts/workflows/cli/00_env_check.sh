#!/bin/bash

# ==============================================================================
# PMET Requirements Checker
# ==============================================================================
# Checks required tools and optionally sets up PMET build environment.
# ==============================================================================

set -euo pipefail

# Project root is parent of pipeline directory
script_dir=$(cd -- "$(dirname "$0")/../../.." && pwd)
cd "$script_dir"

# Load color helpers or use fallback
if [ -f "$script_dir/scripts/lib/print_colors.sh" ]; then
    source "$script_dir/scripts/lib/print_colors.sh"
else
    print_green() { printf "\033[32m%s\033[0m\n" "$1"; }
    print_orange() { printf "\033[33m%s\033[0m\n" "$1"; }
    print_fluorescent_yellow() { printf "\033[93m%s\033[0m\n" "$1"; }
    print_red() { printf "\033[31m%s\033[0m\n" "$1"; }
fi

# ==============================================================================
# Helper Functions
# ==============================================================================

check_bin() {
    if command -v "$1" >/dev/null 2>&1; then
        print_green "[✓] $1"
    else
        print_red "[✗] $1"
    fi
}

print_list() {
    local title="$1"; shift
    print_orange "$title"
    for item in "$@"; do
        echo "  - $item"
    done
}

# ==============================================================================
# Build PMET binaries from this checkout
# ==============================================================================

setup_pmet() {
    print_orange "\n[SETUP] Building PMET binaries from this checkout..."

    (cd "$script_dir" && make build)

    if [[ -x "$script_dir/build/indexing_fimo_fused" && -x "$script_dir/build/pairing_parallel" ]]; then
        print_green "[✓] Build complete! Binaries available in ./build"
    else
        print_red "[✗] Build failed - expected binaries not found in ./build"
        exit 1
    fi
}

# ==============================================================================
# Configuration
# ==============================================================================

core_bins=("R" "Rscript" "python3" "pip" "pip3" "fasta-get-markov" "parallel" "bedtools" "samtools")
r_packages=("data.table" "tidyverse" "ggplot2" "hrbrthemes" "dplyr" "readr" "rJava")
py_packages=("numpy" "pandas" "scipy" "bio" "biopython")

# ==============================================================================
# Main
# ==============================================================================

print_fluorescent_yellow "\n=========================================="
print_fluorescent_yellow "  PMET Requirements Checker"
print_fluorescent_yellow "==========================================\n"

# Handle --setup-pmet flag
if [[ ${1:-} == "--setup-pmet" ]]; then
    setup_pmet
    exit 0
fi

# Check if build directory is empty and offer to set up
if [ ! -d "$script_dir/build" ] || [ -z "$(ls -A "$script_dir/build" 2>/dev/null)" ]; then
    print_orange "[!] build/ directory is empty."
    read -r -t 5 -p "Run PMET setup now? [Y/n] (auto-yes in 5s): " reply || reply="y"
    echo
    if [[ -z "$reply" || "$reply" =~ ^[Yy]$ ]]; then
        setup_pmet
    fi
fi

# Check binaries
print_orange "Checking binaries..."
for bin in "${core_bins[@]}"; do
    check_bin "$bin"
done

# Download genome/annotation if missing
print_orange "\nChecking genome data..."
if [[ ! -s data/reference/TAIR10.fasta || ! -s data/reference/TAIR10.gff3 ]]; then
    print_orange "Downloading genome and annotation..."
    bash scripts/fetch_reference.sh
else
    print_green "[✓] Genome and annotation are ready!"
fi

# Show package lists
print_list "\nR packages needed:" "${r_packages[@]}"
print_list "\nPython packages needed:" "${py_packages[@]}"

print_orange "\n------------------------------------------"
print_orange "Tips:"
print_orange "  • Install R packages:      Rscript scripts/r/install_packages.R"
print_orange "  • Install Python packages: pip install numpy pandas scipy biopython"
print_orange "  • Setup PMET binaries:     make build  (or: $0 --setup-pmet)"
print_orange "------------------------------------------\n"
