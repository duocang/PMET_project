#!/bin/bash
# ==============================================================================
# promoter — full PMET promoters pipeline
# ==============================================================================
# Runs homotypic indexing (via run_homotypic.py), heterotypic motif-pair
# enrichment, and heatmaps in one go.
#
# Use cases:
#   - CLI:  research runs against TAIR10 + Franco-Zorrilla (defaults) or
#           any user genome/annotation/MEME with the research knobs
#   - Web:  the `promoters` mode (apps/pmet_backend/services/executor.py)
#
# Stages:
#   [1] Homotypic — genome/annotation prep -> promoter BED -> FIMO + pmetindex
#       via build/index_fimo_fused (delegated to scripts/python/run_homotypic.py)
#   [2] Heterotypic — pair_parallel consumes the index
#   [3] Heatmaps    — three R-rendered views (skipped if Rscript absent)
#
# Merged from cli/03_promoter.sh + web/promoter.sh — same body and same
# delegation to run_homotypic.py; takes web's better impl (BIN_DIR walker,
# R fallback, fetch_reference fallback) and adds cli's research knobs
# (-F gene_features, -P isPoisson, -K keep_intermediate, -y plot_dir,
# -s/-a/-m named-arg aliases).
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$script_dir"

# ==================== Helpers ====================
if [[ -f scripts/lib/print_colors.sh ]]; then
    # shellcheck source=/dev/null
    source scripts/lib/print_colors.sh
else
    print_green()             { printf "\033[32m%s\033[0m\n" "$1"; }
    print_red()               { printf "\033[31m%s\033[0m\n" "$1"; }
    print_orange()            { printf "\033[33m%s\033[0m\n" "$1"; }
    print_fluorescent_yellow(){ printf "\033[93m%s\033[0m\n" "$1"; }
fi
if [[ -f scripts/lib/progress.sh ]]; then
    # shellcheck source=/dev/null
    source scripts/lib/progress.sh
else
    emit_progress() { :; }
    clear_progress() { :; }
fi
if [[ -f scripts/lib/minhash.sh ]]; then
    # shellcheck source=/dev/null
    source scripts/lib/minhash.sh
else
    resolve_minhash_min() { printf '0'; }
fi
if [[ -f scripts/lib/timer.sh ]]; then
    # shellcheck source=/dev/null
    source scripts/lib/timer.sh
else
    print_elapsed_time() {
        local s=$1 dt=$((SECONDS - s))
        local d=$((dt / 86400)) h=$(((dt % 86400) / 3600)) m=$(((dt % 3600) / 60)) sec=$((dt % 60))
        echo "Time taken: ${d}d ${h}h ${m}m ${sec}s"
    }
fi

error_exit() { print_red "ERROR: $1" >&2; exit 1; }
check_file() { [[ -f "$1" && -s "$1" ]] || error_exit "${2:-$1} missing or empty"; }
check_dep()  { command -v "$1" &>/dev/null || error_exit "Tool not found: $1"; }

is_yes()        { local v; v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]'); [[ "$v" =~ ^(yes|y|true|t)$ ]]; }
is_no_overlap() { local v; v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]'); [[ "$v" =~ ^(nooverlap|no|n)$ ]]; }

usage() {
    cat >&2 <<'EOF'
USAGE: promoter.sh [options] [<genome> <gff3> <memefile> <gene_input_file>]

Data (also settable as positional args in this order):
  -s <genome>            FASTA genome             (default: data/reference/TAIR10.fasta)
  -a <gff3>              GFF3 annotation          (default: data/reference/TAIR10.gff3)
  -m <memefile>          MEME motif file          (default: data/motifs/Franco-Zorrilla_et_al_2014.meme)
  -g <gene_list>         user gene list           (default: data/genes/genes_cell_type_treatment.txt)

Homotypic parameters:
  -i <gff3_id_key>       GFF3 attribute key, e.g. gene_id= or ID=  (default: gene_id=)
  -F <gene_features>     all | strict (gene-row regex)             (default: all)
  -v <overlap_mode>      AllowOverlap | NoOverlap                  (default: NoOverlap)
  -u <include_utr>       Yes | No                                  (default: Yes)
  -n <topn>              top n promoter hits per motif             (default: 5000)
  -k <max_k>             max motif hits per promoter               (default: 5)
  -p <promoter_length>   promoter length, bp                       (default: 1000)
  -f <fimo_threshold>    FIMO p-value threshold                    (default: 0.05)
  -P <isPoisson>         true | false                              (default: false)

Heterotypic / runtime:
  -c <ic_threshold>      pairing IC threshold                      (default: 4)
  -t <threads>           threads                                   (default: 4)
  -K <keep_intermediate> true | false                              (default: false)

Output directories:
  -o <homotypic_dir>     homotypic output         (default: results/cli/promoter/01_homotypic)
  -x <heterotypic_dir>   heterotypic output       (default: results/cli/promoter/02_heterotypic)
  -y <plot_dir>          plot output dir          (default: <heterotypic_dir>/plot)

Web-backend compat:
  -r <project_root>      override repo root for binary search (used in docker)
  -e <email>             accepted, ignored (backend handles)
  -l <result_link>       accepted, ignored

  -h                     show this help
EOF
}

# ==================== Defaults ====================

genome=data/reference/TAIR10.fasta
anno=data/reference/TAIR10.gff3
meme=data/motifs/Franco-Zorrilla_et_al_2014.meme

task=genes_cell_type_treatment
gene_input_file=data/genes/$task.txt

gff3id="gene_id="
gene_features=all
overlap=NoOverlap
utr=Yes
topn=5000
maxk=5
length=1000
fimothresh=0.05
isPoisson=false
icthresh=4
threads=4
keep_intermediate=false

res_dir=results/cli/promoter
homotypic_output=
heterotypic_output=
plot_output=
project_root=$script_dir

# ==================== Argument parsing ====================

while getopts ":s:a:m:g:i:F:v:u:n:k:p:f:P:c:t:K:o:x:y:r:e:l:h" opt; do
    case $opt in
        s) genome=$OPTARG ;;
        a) anno=$OPTARG ;;
        m) meme=$OPTARG ;;
        g) gene_input_file=$OPTARG ;;
        i) gff3id=$OPTARG ;;
        F) gene_features=$OPTARG ;;
        v) overlap=$OPTARG ;;
        u) utr=$OPTARG ;;
        n) topn=$OPTARG ;;
        k) maxk=$OPTARG ;;
        p) length=$OPTARG ;;
        f) fimothresh=$OPTARG ;;
        P) isPoisson=$OPTARG ;;
        c) icthresh=$OPTARG ;;
        t) threads=$OPTARG ;;
        K) keep_intermediate=$OPTARG ;;
        o) homotypic_output=$OPTARG ;;
        x) heterotypic_output=$OPTARG ;;
        y) plot_output=$OPTARG ;;
        r) project_root=$OPTARG ;;
        e) : ;;  # backend interface compat
        l) : ;;
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done
shift $((OPTIND - 1))
[[ $# -ge 1 ]] && genome=$1
[[ $# -ge 2 ]] && anno=$2
[[ $# -ge 3 ]] && meme=$3
[[ $# -ge 4 ]] && gene_input_file=$4

: "${homotypic_output:=$res_dir/01_homotypic}"
: "${heterotypic_output:=$res_dir/02_heterotypic}"
: "${plot_output:=$heterotypic_output/plot}"

# ==================== Locate binaries ====================

BIN_DIR=
for cand in "$project_root/build" "$script_dir/build"; do
    if [[ -x "$cand/index_fimo_fused" && -x "$cand/pair_parallel" ]]; then
        BIN_DIR=$cand
        break
    fi
done
[[ -n $BIN_DIR ]] || error_exit "PMET binaries (index_fimo_fused, pair_parallel) not found"
BIN_INDEX="$BIN_DIR/index_fimo_fused"
BIN_PMET="$BIN_DIR/pair_parallel"

PY=scripts/python

# ==================== Preflight ====================

# Auto-fetch TAIR10 if missing AND a fetcher is present (CLI convenience).
if [[ ! -s "$genome" || ! -s "$anno" ]]; then
    if [[ -f scripts/fetch_reference.sh ]]; then
        print_green "Downloading genome and annotation..."
        bash scripts/fetch_reference.sh
    fi
fi

check_file "$genome" "Genome"
check_file "$anno"   "GFF3 annotation"
check_file "$meme"   "MEME motif file"
check_file "$gene_input_file" "Gene list"

for cmd in samtools bedtools sortBed fasta-get-markov parallel python3; do
    check_dep "$cmd"
done

# Catch GFF3 vs FASTA naming mismatches early (e.g. "1" vs "Chr1").
gff3_chr=$(awk -F'\t' '!/^#/ && NF>=9 {print $1; exit}' "$anno")
fasta_chr=$(grep '^>' "$genome" | head -1 | sed 's/^>//' | awk '{print $1}')
if [[ "$gff3_chr" != "$fasta_chr" ]]; then
    error_exit "Chromosome name mismatch: GFF3='$gff3_chr' vs FASTA='$fasta_chr'. Ensure consistent naming."
fi
print_fluorescent_yellow "   Preflight OK — chromosome naming consistent ('$gff3_chr')"

rm -rf "$homotypic_output" "$heterotypic_output" "$plot_output"
mkdir -p "$homotypic_output" "$heterotypic_output" "$plot_output"

grand_start=$SECONDS

# ==============================================================================
# [1] Homotypic
# ==============================================================================

print_green "\n[1/3] Homotypic motif search..."
emit_progress "homotypic" 1 3 "Homotypic motif search (FIMO scan)"
h_start=$SECONDS

overlap_arg=AllowOverlap; is_no_overlap "$overlap" && overlap_arg=NoOverlap
utr_arg=No;                is_yes "$utr"          && utr_arg=Yes
poisson_flag="";  is_yes "$isPoisson" && poisson_flag="--poisson"
keep_flag="";     is_yes "$keep_intermediate" && keep_flag="--keep-intermediate"

python3 "$PY/run_homotypic.py" \
    --genome      "$genome"     \
    --anno        "$anno"       \
    --meme        "$meme"       \
    --output-dir  "$homotypic_output" \
    --length      "$length"     \
    --gap         0             \
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
# [2] Heterotypic
# ==============================================================================

print_green "\n[2/3] Heterotypic motif search..."
emit_progress "heterotypic" 2 3 "Heterotypic pairing"

universefile="$homotypic_output/universe.txt"
gene_tmp=$(mktemp)
trap 'rm -f "$gene_tmp"' EXIT
grep -wFf "$universefile" "$gene_input_file" > "$gene_tmp" || true

if [[ ! -s "$gene_tmp" ]]; then
    error_exit "No genes from the input list match the universe (homotypic stage filtered them all out)"
fi

# Diagnostic outputs.
cp "$gene_tmp" "$heterotypic_output/genes_used_PMET.txt"
grep -vwFf "$universefile" "$gene_input_file" > "$heterotypic_output/genes_not_found.txt" || true

minhash_min=$(resolve_minhash_min "$homotypic_output/fimohits")
echo "MinHash prefilter: -m $minhash_min"

"$BIN_PMET" \
    -d "$homotypic_output"            \
    -g "$gene_tmp"                    \
    -i "$icthresh"                    \
    -p promoter_lengths.txt           \
    -b binomial_thresholds.txt        \
    -c IC.txt                         \
    -f fimohits                       \
    -o "$heterotypic_output"          \
    -t "$threads"                     \
    -m "$minhash_min" > "$heterotypic_output/pmet.log"

# Merge ONLY pair_parallel's temp*.txt shards.
shopt -s nullglob
shards=("$heterotypic_output"/temp*.txt)
shopt -u nullglob
if (( ${#shards[@]} == 0 )); then
    error_exit "pair_parallel produced no temp*.txt shards (see $heterotypic_output/pmet.log)"
fi
cat "${shards[@]}" > "$heterotypic_output/motif_output.txt"
rm -f "${shards[@]}"

# ==============================================================================
# [3] Heatmaps
# ==============================================================================

print_green "\n[3/3] Generating heatmaps..."
emit_progress "heatmaps" 3 3 "Generating heatmaps"

if ! command -v Rscript >/dev/null 2>&1; then
    print_orange "   Rscript not found — skipping heatmaps. Main output (motif_output.txt) is unaffected."
else
    # See pair_only.sh for rationale on max_motifs / max_fig_inches and the
    # try-catch wrapper. motif_output.txt is the canonical product; heatmap
    # is best-effort.
    max_motifs=30
    max_fig_inches=40
    draw() {
        if ! Rscript scripts/r/draw_heatmap.R "$@"; then
            print_orange "   heatmap render failed (method=$1, file=$2); main output unaffected"
        fi
    }
    draw All     "$plot_output/heatmap.png"                "$heterotypic_output/motif_output.txt" 5 3 6 FALSE "$max_motifs" "$max_fig_inches"
    draw Overlap "$plot_output/heatmap_overlap_unique.png" "$heterotypic_output/motif_output.txt" 5 3 6 TRUE  "$max_motifs" "$max_fig_inches"
    draw Overlap "$plot_output/heatmap_overlap.png"        "$heterotypic_output/motif_output.txt" 5 3 6 FALSE "$max_motifs" "$max_fig_inches"
fi

clear_progress
print_green "\nDone."
print_elapsed_time "$grand_start"
