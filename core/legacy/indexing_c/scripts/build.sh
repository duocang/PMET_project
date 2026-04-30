#!/bin/bash
#############################################
# pmetindex (C version) - Build Script
#############################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"

# Binary name
BINARY_NAME="index_c"
UNIFIED_NAME="index_c"

echo "==> Building pmetindex (C version)..."

cd "$PROJECT_DIR"
rm -rf build
mkdir -p build
cd build

cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)

if [ -f "$BINARY_NAME" ]; then
    echo "✓ Build successful: build/$BINARY_NAME"

    # Copy to project root build directory
    if [ -d "$PROJECT_ROOT/build" ] || mkdir -p "$PROJECT_ROOT/build"; then
        cp "$BINARY_NAME" "$PROJECT_ROOT/build/$UNIFIED_NAME"
        echo "✓ Copied to: $PROJECT_ROOT/build/$UNIFIED_NAME"
    fi
else
    echo "✗ Build failed"
    exit 1
fi
