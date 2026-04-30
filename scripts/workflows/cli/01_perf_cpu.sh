#!/bin/bash
# ==============================================================================
# Pipeline 01: CPU benchmark — heterotypic search on a precomputed promoter
# index, comparing single-CPU (build/pmet) against multi-threaded
# (build/pair_parallel).
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "$0")/../../.." && pwd)
cd "$script_dir"
source scripts/lib/print_colors.sh

# ==================== Configuration ====================

output=results/cli/01_perf_cpu
# Pre-built homotypic promoter index. Default to the standard output path of
# scripts/workflows/promoter.sh; run that once before this benchmark.
indexoutput=${PMET_HOMOTYPIC_INDEX:-results/cli/promoter/01_homotypic}
# Use a real, project-tracked gene list for the benchmark. The legacy
# `data/gene.txt` referenced here was removed; the benchmark only cares that
# the list intersects the precomputed homotypic universe, so we reuse the
# canonical task list that scripts/03 also defaults to.
gene_input_file=data/genes/genes_cell_type_treatment.txt

if [[ ! -d "$indexoutput" ]]; then
    echo "error: homotypic index not found at $indexoutput" >&2
    echo "       run scripts/workflows/promoter.sh first, or set PMET_HOMOTYPIC_INDEX" >&2
    exit 1
fi

parallel_threads=2
icthresh=4

# Heatmap parameters (must match scripts/r/draw_heatmap.R signature: 7 args).
# Mirrors the defaults scripts/03 uses for "Overlap" plots.
heatmap_topn=5
heatmap_ncol=3
heatmap_width=6
heatmap_unique=FALSE

temp_genes=$(mktemp)
trap 'rm -f "$temp_genes"' EXIT

# ==================== Shared runner ====================
# Run one heterotypic pass with the given binary into $output/<subdir>, then
# consolidate per-motif hits and draw the heatmap. Extra arguments after the
# subdir are forwarded verbatim to the binary (e.g. -t for pair_parallel).

run_pmet_pass() {
    local binary="$1"
    local subdir="$2"
    shift 2

    local out_dir="$output/$subdir"
    mkdir -p "$out_dir"

    # Restrict the gene list to genes present in the precomputed index.
    grep -Ff "$indexoutput/universe.txt" "$gene_input_file" > "$temp_genes"

    "$binary"                                       \
        -d .                                        \
        -g "$temp_genes"                            \
        -i "$icthresh"                              \
        -p "$indexoutput/promoter_lengths.txt"      \
        -b "$indexoutput/binomial_thresholds.txt"   \
        -c "$indexoutput/IC.txt"                    \
        -f "$indexoutput/fimohits"                  \
        -o "$out_dir"                               \
        "$@"

    # `build/pmet` writes a single $out_dir/motif_output.txt directly.
    # `build/pair_parallel` writes per-cluster .txt files; concatenate them.
    # In the latter case, redirecting into $out_dir/motif_output.txt while
    # the glob `$out_dir/*.txt` still contains it would self-clobber, so
    # build the consolidated file via mktemp first.
    case "$(basename "$binary")" in
        pmet)
            : # already wrote $out_dir/motif_output.txt
            ;;
        *)
            # Idempotent: rm any prior aggregate so it's not picked up
            # by the *.txt glob on a re-run.
            rm -f "$out_dir/motif_output.txt"
            local concat_tmp
            concat_tmp=$(mktemp)
            cat "$out_dir"/*.txt > "$concat_tmp"
            rm -f "$out_dir"/temp*.txt
            mv "$concat_tmp" "$out_dir/motif_output.txt"
            ;;
    esac

    Rscript scripts/r/draw_heatmap.R    \
        Overlap                         \
        "$out_dir/heatmap.png"          \
        "$out_dir/motif_output.txt"     \
        "$heatmap_topn"                 \
        "$heatmap_ncol"                 \
        "$heatmap_width"                \
        "$heatmap_unique"
}

# ==================== Single-CPU ====================
print_green "Searching for heterotypic motif hits with single CPU..."
run_pmet_pass build/pmet single

# ==================== Parallel ====================
print_green "Searching for heterotypic motif hits with pair_parallel..."
run_pmet_pass build/pair_parallel parallel -t "$parallel_threads"
