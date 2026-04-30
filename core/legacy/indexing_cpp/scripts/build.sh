#!/bin/bash

echo "Building PMET Indexing..."

mkdir -p build
cd build

cmake ..
make

if [ $? -eq 0 ]; then
    echo "✓ Build successful"
else
    echo "✗ Build failed"
    exit 1
fi

# 清理构建文件
rm -f Makefile cmake_install.cmake
rm -rf CMakeFiles CMakeCache.txt

echo "Done"