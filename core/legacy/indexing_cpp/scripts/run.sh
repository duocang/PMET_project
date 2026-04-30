#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Parameters
fimothresh=0.05
memefile_dir=data/promoter/memefiles
promoters=data/promoter/promoters.fa
promoter_lengths=data/promoter/promoter_lengths.txt
bgfile=data/promoter/promoters.bg

echo -e "${GREEN}=== PMET Indexing Pipeline ===${NC}\n"

# Step 1: Create output directories
echo -e "${YELLOW}[1/3] Creating output directories${NC}"
rm -rf result
mkdir -p result/fimo_indexed result/fimo

# Step 2: Run FIMO analysis
echo -e "${YELLOW}[2/3] Running FIMO analysis (threshold=$fimothresh)${NC}"

for memefile in $memefile_dir/*.txt; do
    name=$(basename "$memefile" .txt)
    printf "  Processing: %s..." "$name"

    if fimo --text --thresh $fimothresh --verbosity 1 --bgfile $bgfile \
        $memefile $promoters > result/fimo/"${name}".txt 2>/dev/null; then
        echo -e " ${GREEN}OK${NC}"
    else
        echo -e " ${RED}FAILED${NC}"
    fi
done

# Step 3: Run PMET Indexing
echo -e "${YELLOW}[3/3] Running PMET Indexing${NC}"

if [ ! -f "./build/pmetindex" ]; then
    echo -e "${RED}Error: ./build/pmetindex not found. Run: bash build.sh${NC}"
    exit 1
fi

if ./build/pmetindex -f result/fimo -k 5 -n 5000 -p $promoter_lengths -o result/fimo_indexed; then
    echo -e "\n${GREEN}=== Pipeline completed successfully! ===${NC}"
else
    echo -e "${RED}PMET Indexing failed${NC}"
    exit 1
fi