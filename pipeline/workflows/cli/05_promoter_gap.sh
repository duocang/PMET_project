#!/bin/bash
# ==============================================================================
# Pipeline 08: PMET Promoter Analysis with TSS-proximal gap
# ==============================================================================
# Variant of pipeline/03 that shrinks the TSS-proximal end of each promoter
# by `gap` bp to exclude the core promoter (TATA / Inr / TSS-proximal general
# TF sites), improving signal for cell-type-specific TFs and distal elements.
#
# Stages:
#   [1] Homotypic — genome/annotation prep → promoter BED (with gap) →
#       FIMO + pmetindex via build/index_fimo_fused
#   [2] Heterotypic — pair_parallel consumes the index
#   [3] Heatmaps — three R-rendered views
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "$0")/../../.." && pwd)
cd "$script_dir"
source pipeline/lib/print_colors.sh
source pipeline/lib/timer.sh

# ==================== Configuration ====================

# Data
genome=data/reference/TAIR10.fasta
anno=data/reference/TAIR10.gff3
meme=data/motifs/Franco-Zorrilla_et_al_2014.meme

task=genes_cell_type_treatment
gene_input_file=data/genes/$task.txt

# Homotypic parameters
gff3id="gene_id="
gene_features=all        # all / strict — see docs/contracts/homotypic.md
                         #   all    → regex 'gene$': gene + ncRNA_gene + pseudogene + …
                         #   strict → regex '^gene$': only canonical 'gene' rows
overlap=NoOverlap        # AllowOverlap | NoOverlap
utr=Yes                  # Yes | No — force-disabled below when gap != 0
topn=5000
maxk=5
length=1000
fimothresh=0.05
isPoisson=false
gap=100

# When gap != 0 we shrink the TSS-proximal end to exclude the core promoter;
# adding the 5' UTR would re-extend from the TSS and undo that exclusion.
# `${utr,,}` is Bash 4+ only; macOS ships /bin/bash 3.2, so use `tr` instead.
utr_lc=$(printf '%s' "$utr" | tr '[:upper:]' '[:lower:]')
if (( gap != 0 )) && [[ "$utr_lc" =~ ^(yes|y|true|t)$ ]]; then
    print_fluorescent_yellow "   gap=$gap != 0 — forcing utr=No (UTR would undo the TSS-proximal exclusion)"
    utr=No
fi
unset utr_lc

# Heterotypic parameters
icthresh=4

# Runtime
threads=4

# Behavior
keep_intermediate=false  # true: retain all per-stage scratch files

# Output
res_dir=results/05_promoter_gap
homotypic_output=$res_dir/01_homotypic
heterotypic_output=$res_dir/02_heterotypic
plot_output=$res_dir/plot

# Binaries / tools
BIN_DIR=build
BIN_INDEX="$BIN_DIR/index_fimo_fused"
BIN_PMET="$BIN_DIR/pair_parallel"
PY=pipeline/python

# Derived paths (inside homotypic_output)
universefile="$homotypic_output/universe.txt"
bedfile="$homotypic_output/genelines.bed"
promoters="$homotypic_output/promoters.bed"
stripped="$homotypic_output/genome_stripped.fa"

# ==================== Helpers ====================

error_exit()  { print_red "ERROR: $1" >&2; exit 1; }
check_file()  { [[ -f "$1" && -s "$1" ]] || error_exit "${2:-$1} missing or empty"; }
check_dep()   { command -v "$1" &>/dev/null || error_exit "Tool not found: $1"; }
step()        { print_fluorescent_yellow "   $1. $2"; }

is_yes() {
    local v; v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    [[ "$v" =~ ^(yes|y|true|t)$ ]]
}

is_no_overlap() {
    local v; v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    [[ "$v" =~ ^(nooverlap|no|n)$ ]]
}

# Remove BED rows shorter than $2 bp; save removed rows to $3
filter_short_promoters() {
    local bed="$1" min_len="$2" removed="$3"
    local n; n=$(awk -F'\t' -v m="$min_len" '$3-$2 < m' "$bed" | wc -l | tr -d ' ')
    if (( n > 0 )); then
        print_fluorescent_yellow "        Removed $n promoter(s) < ${min_len} bp"
        awk -F'\t' -v m="$min_len" '$3-$2 < m' "$bed" > "$removed"
    fi
    awk -F'\t' -v m="$min_len" '$3-$2 >= m' "$bed" > "${bed}.tmp" && mv "${bed}.tmp" "$bed"
}

# ==================== Preflight ====================

if [[ ! -s "$genome" || ! -s "$anno" ]]; then
    print_green "Downloading genome and annotation..."
    bash pipeline/data/fetch_tair10.sh
fi

check_file "$genome" "Genome"
check_file "$anno"   "GFF3 annotation"
check_file "$meme"   "MEME motif file"
check_file "$gene_input_file" "Gene list"

for cmd in samtools bedtools sortBed fasta-get-markov parallel python3; do
    check_dep "$cmd"
done
[[ -f "$BIN_INDEX" ]] || error_exit "Binary not found: $BIN_INDEX"
[[ -f "$BIN_PMET"  ]] || error_exit "Binary not found: $BIN_PMET"

# ---- Chromosome naming consistency ----
# Catch GFF3 vs FASTA naming mismatches early (e.g. "1" vs "Chr1")
gff3_chr=$(awk -F'\t' '!/^#/ && NF>=9 {print $1; exit}' "$anno")
fasta_chr=$(grep '^>' "$genome" | head -1 | sed 's/^>//' | awk '{print $1}')
if [[ "$gff3_chr" != "$fasta_chr" ]]; then
    error_exit "Chromosome name mismatch: GFF3 uses '$gff3_chr' but FASTA uses '$fasta_chr'. Please ensure consistent naming."
fi
print_fluorescent_yellow "   Preflight OK — chromosome naming consistent ('$gff3_chr')"

rm -rf "$homotypic_output" "$heterotypic_output" "$plot_output"
mkdir -p "$homotypic_output" "$heterotypic_output" "$plot_output"

grand_start=$SECONDS

# ==============================================================================
# [1] Homotypic: genome → promoter index (delegated to run_homotypic.py)
# ==============================================================================

print_green "\n[1/3] Homotypic motif search..."
h_start=$SECONDS

overlap_arg=AllowOverlap; is_no_overlap "$overlap" && overlap_arg=NoOverlap
utr_arg=No; is_yes "$utr" && utr_arg=Yes
poisson_flag=""
is_yes "$isPoisson" && poisson_flag="--poisson"
keep_flag=""
[[ "$keep_intermediate" == true ]] && keep_flag="--keep-intermediate"

python3 "$PY/run_homotypic.py" \
    --genome      "$genome"     \
    --anno        "$anno"       \
    --meme        "$meme"       \
    --output-dir  "$homotypic_output" \
    --length      "$length"     \
    --gap         "$gap"        \
    --maxk        "$maxk"       \
    --topn        "$topn"       \
    --fimothresh  "$fimothresh" \
    --overlap     "$overlap_arg"\
    --utr           "$utr_arg"      \
    --gff3-id-key   "$gff3id"       \
    --gene-features "$gene_features" \
    --threads     "$threads"    \
    --bin-index   "$BIN_INDEX"  \
    $poisson_flag $keep_flag

print_elapsed_time "$h_start"

# ==============================================================================
# [2] Heterotypic: pair_parallel consumes the homotypic index
# ==============================================================================

print_green "\n[2/3] Heterotypic motif search..."

gene_tmp=$(mktemp)
trap 'rm -f "$gene_tmp"' EXIT
grep -Ff "$universefile" "$gene_input_file" > "$gene_tmp"

"$BIN_PMET" \
    -d .                                            \
    -g "$gene_tmp"                                  \
    -i "$icthresh"                                  \
    -p "$homotypic_output/promoter_lengths.txt"     \
    -b "$homotypic_output/binomial_thresholds.txt"  \
    -c "$homotypic_output/IC.txt"                   \
    -f "$homotypic_output/fimohits"                 \
    -o "$heterotypic_output"                        \
    -t "$threads" > "$heterotypic_output/pmet.log"

cat "$heterotypic_output"/*.txt > "$heterotypic_output/motif_output.txt"
rm -f "$heterotypic_output"/temp*.txt

# ==============================================================================
# [3] Heatmaps
# ==============================================================================

print_green "\n[3/3] Generating heatmaps..."

draw() { Rscript pipeline/r/draw_heatmap.R "$@"; }

draw All     "$plot_output/heatmap.png"                "$heterotypic_output/motif_output.txt" 5 3 6 FALSE
draw Overlap "$plot_output/heatmap_overlap_unique.png" "$heterotypic_output/motif_output.txt" 5 3 6 TRUE
draw Overlap "$plot_output/heatmap_overlap.png"        "$heterotypic_output/motif_output.txt" 5 3 6 FALSE

print_green "\nDone."
print_elapsed_time "$grand_start"
