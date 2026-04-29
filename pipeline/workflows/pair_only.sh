#!/bin/bash
# ==============================================================================
# pair_only — heterotypic enrichment + heatmaps on a pre-built index
# ==============================================================================
# Skips the expensive homotypic indexing stage and consumes an existing
# homotypic dir produced by promoter.sh / intervals.sh / elements_*.sh
# (see docs/contracts/homotypic.md for the layout).
#
# Use cases:
#   - CLI:  re-pair the same index against a different gene list or with a
#           different IC threshold without redoing indexing (~110s -> ~2-5s)
#   - Web:  the `promoters_pre` mode (apps/pmet_backend/services/executor.py)
#
# Stages:
#   [1] Heterotypic — pair_parallel consumes the pre-built index
#   [2] Heatmaps    — three R-rendered views (skipped if Rscript absent)
#
# Merged from cli/08_pair_only.sh + web/promoter_precomputed.sh — same
# core; takes web's BIN_DIR walker (docker-friendly) + cli's homotypic
# contract validator + colored logging when sourceable.
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$script_dir"

# ==================== Helpers ====================
# Try to source the colored logging helpers; fall back to plain echo so the
# script also works inside docker containers without the lib mounted.
if [[ -f pipeline/lib/print_colors.sh ]]; then
    # shellcheck source=/dev/null
    source pipeline/lib/print_colors.sh
else
    print_green()  { printf "\033[32m%s\033[0m\n" "$1"; }
    print_red()    { printf "\033[31m%s\033[0m\n" "$1"; }
    print_orange() { printf "\033[33m%s\033[0m\n" "$1"; }
fi
if [[ -f pipeline/lib/timer.sh ]]; then
    # shellcheck source=/dev/null
    source pipeline/lib/timer.sh
else
    print_elapsed_time() {
        local s=$1 e=$SECONDS dt=$((SECONDS - s))
        local d=$((dt / 86400)) h=$(((dt % 86400) / 3600)) m=$(((dt % 3600) / 60)) sec=$((dt % 60))
        echo "Time taken: ${d}d ${h}h ${m}m ${sec}s"
    }
fi

error_exit() { print_red "ERROR: $1" >&2; exit 1; }
check_file() { [[ -f "$1" && -s "$1" ]] || error_exit "${2:-$1} missing or empty"; }

usage() {
    cat >&2 <<'EOF'
USAGE: pair_only.sh -d <pmetindex_dir> -g <gene_file> -o <output_dir> [options]

Required:
  -d <pmetindex_dir>     pre-built homotypic index, must contain:
                         promoter_lengths.txt, binomial_thresholds.txt,
                         IC.txt, fimohits/, universe.txt
  -g <gene_file>         gene list (one gene per line)
  -o <output_dir>        pairing output dir (heatmaps land in <dir>/plot)

Optional:
  -i <ic_threshold>      pairing IC threshold (default: 4)
  -t <threads>           threads (default: 4)
  -r <project_root>      override repo root for binary search (rarely needed;
                         used by the web backend in docker where binaries
                         live at $project_root/build/)
  -e <email>             accepted for backend compatibility, not used
  -l <result_link>       accepted for backend compatibility, not used
  -h                     show this help

Examples:
  # CLI: re-pair pipeline 03's index with a different gene list
  bash pipeline/workflows/pair_only.sh \
      -d results/03_promoter/01_homotypic \
      -g data/genes/genes_cell_type_treatment.txt \
      -o results/pair_only/cell_type_treatment_ic4

  # Web backend invocation (apps/pmet_backend/services/executor.py builds this)
  bash pipeline/workflows/pair_only.sh \
      -d <task_index_dir> -g <task_genes> -o <task_output> \
      -i 24 -t 4 -e user@example.com -l https://...
EOF
}

# ==================== Defaults ====================

pmetindex=
genefile=
outputdir=
icthresh=4
threads=4
project_root=$script_dir

# ==================== Argument parsing ====================

while getopts ":d:g:o:i:t:r:e:l:h" opt; do
    case $opt in
        d) pmetindex=$OPTARG ;;
        g) genefile=$OPTARG ;;
        o) outputdir=$OPTARG ;;
        i) icthresh=$OPTARG ;;
        t) threads=$OPTARG ;;
        r) project_root=$OPTARG ;;
        e) : ;;  # accepted, not used (backend interface compat)
        l) : ;;  # accepted, not used
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done

[[ -n $pmetindex ]] || { usage; error_exit "-d <pmetindex_dir> required"; }
[[ -n $genefile  ]] || { usage; error_exit "-g <gene_file> required"; }
[[ -n $outputdir ]] || { usage; error_exit "-o <output_dir> required"; }

# ==================== Locate binary ====================
# Walks candidate dirs so the script works on host (build/) and inside the
# docker container (where /app/build/ or /app/pmet_pipeline/build/ may apply).

BIN_DIR=
for cand in "$project_root/build" "$project_root/pmet_pipeline/build" \
            "$script_dir/build" "$script_dir/pmet_pipeline/build"; do
    if [[ -x "$cand/pair_parallel" ]]; then
        BIN_DIR=$cand
        break
    fi
done
[[ -n $BIN_DIR ]] || error_exit "PMET binary pair_parallel not found in any of: $project_root/build, $project_root/pmet_pipeline/build, $script_dir/build, $script_dir/pmet_pipeline/build"
BIN_PMET="$BIN_DIR/pair_parallel"

# ==================== Preflight ====================

[[ -d "$pmetindex" ]] || error_exit "Index dir not found: $pmetindex"

universefile="$pmetindex/universe.txt"
check_file "$universefile"                       "Index universe.txt"
check_file "$pmetindex/promoter_lengths.txt"     "Index promoter_lengths.txt"
check_file "$pmetindex/binomial_thresholds.txt"  "Index binomial_thresholds.txt"
check_file "$pmetindex/IC.txt"                   "Index IC.txt"
[[ -d "$pmetindex/fimohits" ]] || error_exit "Index fimohits/ directory missing: $pmetindex/fimohits"
check_file "$genefile" "Gene list"

# Note: a strict homotypic contract validator
# (pipeline/python/check_homotypic_contract.py) lives separately. It is
# intentionally NOT invoked here because it rejects the canonical
# data/cli/pairing/demo fixture (which ships a partial fimohits set on
# purpose). pair_parallel itself produces clear errors on malformed
# indexes; opt into the strict check by running the python helper
# manually before invoking pair_only.sh.

mkdir -p "$outputdir"
plot_output="$outputdir/plot"
mkdir -p "$plot_output"

grand_start=$SECONDS

# ==============================================================================
# [1] Heterotypic
# ==============================================================================

print_green "\n[1/2] Heterotypic motif search..."
echo "Homotypic index : $pmetindex"
echo "Gene list       : $genefile"
echo "Output dir      : $outputdir"
echo "IC threshold    : $icthresh"
echo "Threads         : $threads"

# Word-boundary filter against the index universe — defends against substring
# matches and produces a clean used/dropped split for diagnostics.
gene_tmp=$(mktemp)
trap 'rm -f "$gene_tmp"' EXIT
grep -wFf "$universefile" "$genefile" > "$gene_tmp" || true

if [[ ! -s "$gene_tmp" ]]; then
    error_exit "No genes from the input list match the index universe ($universefile)"
fi

# Diagnostic outputs (written before pair_parallel so failures still leave them).
cp "$gene_tmp" "$outputdir/genes_used_PMET.txt"
grep -vwFf "$universefile" "$genefile" > "$outputdir/genes_not_found.txt" || true

# pair_parallel resolves -p/-b/-c/-f relative to -d, so feed it the
# index dir as the base and bare filenames for the rest.
"$BIN_PMET" \
    -d "$pmetindex"            \
    -g "$gene_tmp"             \
    -i "$icthresh"             \
    -p promoter_lengths.txt    \
    -b binomial_thresholds.txt \
    -c IC.txt                  \
    -f fimohits                \
    -o "$outputdir"            \
    -t "$threads" > "$outputdir/pmet.log"

# Merge ONLY pair_parallel's temp*.txt shards — naive `cat *.txt` would now
# also concatenate the diagnostic files we just wrote.
shopt -s nullglob
shards=("$outputdir"/temp*.txt)
shopt -u nullglob
if (( ${#shards[@]} == 0 )); then
    error_exit "pair_parallel produced no temp*.txt shards (see $outputdir/pmet.log)"
fi
cat "${shards[@]}" > "$outputdir/motif_output.txt"
rm -f "${shards[@]}"

# ==============================================================================
# [2] Heatmaps
# ==============================================================================

print_green "\n[2/2] Generating heatmaps..."

if ! command -v Rscript >/dev/null 2>&1; then
    print_orange "   Rscript not found — skipping heatmaps. Main output (motif_output.txt) is unaffected."
else
    draw() { Rscript pipeline/r/draw_heatmap.R "$@"; }
    draw All     "$plot_output/heatmap.png"                "$outputdir/motif_output.txt" 5 3 6 FALSE
    draw Overlap "$plot_output/heatmap_overlap_unique.png" "$outputdir/motif_output.txt" 5 3 6 TRUE
    draw Overlap "$plot_output/heatmap_overlap.png"        "$outputdir/motif_output.txt" 5 3 6 FALSE
fi

print_green "\nDone."
print_elapsed_time "$grand_start"
