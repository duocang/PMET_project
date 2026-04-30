#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Parameters
fimothresh=0.05
memefile_dir=data/interval/memefiles
genomefile=data/interval/intervals.fa
interval_lengths=data/interval/interval_lengths.txt
bgfile=data/interval/genome.bg

echo -e "${GREEN}=== PMET Indexing Pipeline ===${NC}\n"

# Step 1: Create output directories
echo -e "${YELLOW}[1/5] Creating output directories${NC}"
rm -rf result/interval_indexed
mkdir -p result/fimo_indexed result/interval_indexed/fimo

# Step 2: Preprocess FASTA - replace ':' with '__COLON__' in sequence names
# FIMO has issues parsing sequence names containing ':'
echo -e "${YELLOW}[2/5] Preprocessing FASTA file (replacing ':' in sequence names)${NC}"
genomefile_temp="${genomefile%.fa}_temp.fa"
sed 's/^\(>.*\):/\1__COLON__/g' "$genomefile" > "$genomefile_temp"
echo -e "  Created temporary file: $genomefile_temp"

# Step 3: Run FIMO analysis
echo -e "${YELLOW}[3/5] Running FIMO analysis (threshold=$fimothresh)${NC}"

for memefile in $memefile_dir/*.txt; do
    name=$(basename "$memefile" .txt)
    printf "  Processing: %s..." "$name"

    if fimo --no-qvalue --text --thresh $fimothresh --verbosity 1 \
        --bgfile $bgfile $memefile $genomefile_temp \
        > result/interval_indexed/fimo/"${name}".txt 2>/dev/null; then
        echo -e " ${GREEN}OK${NC}"
    else
        echo -e " ${RED}FAILED${NC}"
    fi
done

# Step 4: Post-process FIMO output - restore ':' in sequence names
echo -e "${YELLOW}[4/5] Post-processing FIMO output (restoring ':' in sequence names)${NC}"
for fimofile in result/interval_indexed/fimo/*.txt; do
    sed -i '' 's/__COLON__/:/g' "$fimofile"
done
rm -f "$genomefile_temp"
echo -e "  Cleanup completed"

# Step 5: Run PMET Indexing
echo -e "${YELLOW}[5/5] Running PMET Indexing${NC}"

if [ ! -f "./build/index_cpp" ]; then
    echo -e "${RED}Error: ./build/index_cpp not found. Run: bash build.sh${NC}"
    exit 1
fi

if ./build/index_cpp -f result/interval_indexed/fimo -k 5 -n 5000 -p $interval_lengths -o result/interval_indexed; then
    echo -e "\n${GREEN}=== Pipeline completed successfully! ===${NC}"
else
    echo -e "${RED}PMET Indexing failed${NC}"
    exit 1
fi