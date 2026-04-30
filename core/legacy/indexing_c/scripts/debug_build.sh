#!/bin/bash
# Build with AddressSanitizer for debugging memory issues

set -e

# Change to project root
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Clean and create build dir
rm -rf build
mkdir -p build

# Compile with debug flags and sanitizers
echo "Building debug version..."
gcc -g -O0 -Wall -Wextra -fsanitize=address -fsanitize=undefined \
    src/*.c \
    -o build/pmetindex_debug \
    -lm

echo "Done. Run: bash scripts/debug_run.sh"