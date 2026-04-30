#!/bin/bash
# ==============================================================================
# intervals — full PMET intervals pipeline
# ==============================================================================
# Runs interval indexing, heterotypic motif-pair enrichment, and heatmaps in
# one go.
#
# Use cases:
#   - CLI:  research runs against bundled or user-supplied intervals
#   - Web:  the `intervals` mode (apps/pmet_backend/services/executor.py)
#
# Stages:
#   [1] Indexing  — interval FASTA + MEME -> universe / promoter_lengths /
#                   IC / fimohits via build/index_fimo_fused (OMP-batched)
#   [2] Heterotypic — pair_parallel consumes the index
#   [3] Heatmaps    — three R-rendered views (skipped if Rscript absent)
#
# Merged from cli/04_intervals.sh + web/intervals.sh — same inlined
# indexing body; takes web's better impl (BIN_DIR walker, R fallback,
# 3-heatmap default, threads=4) and adds the cli's `-s -m` named-arg
# aliases for callers that don't want positional args.
#
# FIMO and pair_parallel's binary fimohits ('PMETBN01' format) can't safely
# carry ':' in sequence names (FIMO mis-parses; binary records are length-
# prefixed). Sanitize ':' -> '__COLON__' on the way in and round-trip on the
# user-facing text outputs at the end.
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$script_dir"

# ==================== Helpers ====================
# Source colored logging if present; fall back to plain echo so the
# script also works in containers / other minimal environments.
if [[ -f scripts/lib/print_colors.sh ]]; then
    # shellcheck source=/dev/null
    source scripts/lib/print_colors.sh
else
    print_green()  { printf "\033[32m%s\033[0m\n" "$1"; }
    print_red()    { printf "\033[31m%s\033[0m\n" "$1"; }
    print_orange() { printf "\033[33m%s\033[0m\n" "$1"; }
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

usage() {
    cat >&2 <<'EOF'
USAGE: intervals.sh [options] [<genome> <memefile>]

Data (also settable as positional args in this order):
  -s <genome>          interval FASTA            (default: data/demos/intervals/indexing/intervals.fa)
  -m <memefile>        MEME motif file           (default: data/demos/intervals/indexing/motif_more.meme)
  -g <gene_file>       interval/gene list        (default: data/demos/intervals/indexing/peaks.txt)

Indexing parameters:
  -n <topn>            top n hits per motif      (default: 5000)
  -k <max_k>           max motif hits / interval (default: 5)
  -f <fimo_threshold>  FIMO p-value threshold    (default: 0.05)

Heterotypic / runtime:
  -c <ic_threshold>    pairing IC threshold      (default: 4)
  -t <threads>         threads                   (default: 4)

Output directories:
  -o <indexing_dir>    indexing stage output     (default: results/cli/intervals/01_indexing)
  -x <pairing_dir>     pairing stage output      (default: results/cli/intervals/02_pairing,
                       heatmaps land in <dir>/plot)

Web-backend compat:
  -r <project_root>    override repo root for binary search (used in docker)
  -e <email>           accepted, ignored by the script (backend handles)
  -l <result_link>     accepted, ignored

  -h                   show this help
EOF
}

# ==================== Defaults ====================

genome=data/demos/intervals/indexing/intervals.fa
meme=data/demos/intervals/indexing/motif_more.meme
gene_input_file=data/demos/intervals/indexing/peaks.txt

topn=5000
maxk=5
fimothresh=0.05
icthresh=4
threads=4

res_dir=results/cli/intervals
indexing_output=
pairing_output=
project_root=$script_dir

# ==================== Argument parsing ====================

while getopts ":s:m:g:n:k:f:c:t:o:x:r:e:l:h" opt; do
    case $opt in
        s) genome=$OPTARG ;;
        m) meme=$OPTARG ;;
        g) gene_input_file=$OPTARG ;;
        n) topn=$OPTARG ;;
        k) maxk=$OPTARG ;;
        f) fimothresh=$OPTARG ;;
        c) icthresh=$OPTARG ;;
        t) threads=$OPTARG ;;
        o) indexing_output=$OPTARG ;;
        x) pairing_output=$OPTARG ;;
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
[[ $# -ge 2 ]] && meme=$2

: "${indexing_output:=$res_dir/01_indexing}"
: "${pairing_output:=$res_dir/02_pairing}"
plot_output="$pairing_output/plot"

PY=scripts/python

# ==================== Locate binaries ====================

BIN_DIR=
for cand in "$project_root/build" "$project_root/pmet_pipeline/build" \
            "$script_dir/build" "$script_dir/pmet_pipeline/build"; do
    if [[ -x "$cand/index_fimo_fused" && -x "$cand/pair_parallel" ]]; then
        BIN_DIR=$cand
        break
    fi
done
[[ -n $BIN_DIR ]] || error_exit "PMET binaries (index_fimo_fused, pair_parallel) not found"
BIN_INDEX="$BIN_DIR/index_fimo_fused"
BIN_PMET="$BIN_DIR/pair_parallel"

# ==================== Preflight ====================

check_file "$genome" "Interval FASTA"
check_file "$meme"   "MEME motif file"
check_file "$gene_input_file" "Interval/gene list"

for cmd in fasta-get-markov python3; do
    check_dep "$cmd"
done

rm -rf "$indexing_output" "$pairing_output" "$plot_output"
mkdir -p "$indexing_output" "$pairing_output" "$plot_output"

grand_start=$SECONDS

# ==============================================================================
# [1] Indexing
# ==============================================================================

print_green "\n[1/3] Interval indexing..."
echo "Indexing output: $indexing_output"
h_start=$SECONDS

genome_sanitized="$indexing_output/genome_sanitized.fa"
sed 's/^\(>.*\):/\1__COLON__/g' "$genome" > "$genome_sanitized"

# Dedupe + per-interval lengths + universe.
python3 "$PY/deduplicate.py" \
    "$genome_sanitized" \
    "$indexing_output/no_duplicates.fa"
python3 "$PY/parse_promoter_lengths_from_fasta.py" \
    "$indexing_output/no_duplicates.fa" \
    "$indexing_output/promoter_lengths.txt"
cut -f1 "$indexing_output/promoter_lengths.txt" > "$indexing_output/universe.txt"
rm -f "$indexing_output/no_duplicates.fa"

# Background model.
fasta-get-markov "$genome_sanitized" > "$indexing_output/genome.bg"

mkdir -p "$indexing_output/fimohits"
python3 "$PY/calculateICfrommeme_IC_to_csv.py" \
    "$meme" \
    "$indexing_output/IC.txt"

nummotifs=$(grep -c '^MOTIF' "$meme")
echo "   └─ $nummotifs motifs"

# index_fimo_fused has internal OpenMP batching; one invocation handles
# every motif. Replaces the earlier shell-level for-loop that forked one
# process per motif each with its own OMP team, oversubscribing cores.
OMP_NUM_THREADS="$threads" \
"$BIN_INDEX"                            \
    --no-qvalue                         \
    --text                              \
    --thresh "$fimothresh"              \
    --verbosity 1                       \
    --bgfile "$indexing_output/genome.bg" \
    --topn "$topn"                      \
    --topk "$maxk"                      \
    --oc "$indexing_output"             \
    "$meme"                             \
    "$genome_sanitized"                 \
    "$indexing_output/promoter_lengths.txt"

# memefiles/ only existed for IC.txt. Sanitized FASTA was a temp.
rm -rf "$indexing_output/memefiles" "$genome_sanitized"

# Validate the indexing-output schema (presence + types).
python3 "$PY/check_homotypic_contract.py" "$indexing_output" \
    || error_exit "Homotypic contract violated; see stderr above"

print_elapsed_time "$h_start"

# ==============================================================================
# [2] Heterotypic
# ==============================================================================

print_green "\n[2/3] Heterotypic motif search..."
echo "Pairing output: $pairing_output"

# Stage [1] keeps the index in sanitized form (':' -> '__COLON__'). Sanitize
# the user gene list to match.
universefile="$indexing_output/universe.txt"
gene_sanitized=$(mktemp)
gene_tmp=$(mktemp)
trap 'rm -f "$gene_sanitized" "$gene_tmp"' EXIT
sed 's/:/__COLON__/g' "$gene_input_file" > "$gene_sanitized"
grep -wFf "$universefile" "$gene_sanitized" > "$gene_tmp" || true

if [[ ! -s "$gene_tmp" ]]; then
    error_exit "No intervals from the input list match the index universe"
fi

# Both genes_used and genes_not_found are computed in sanitized space;
# ':' is restored together with motif_output below.
cp "$gene_tmp" "$pairing_output/genes_used_PMET.txt"
grep -vwFf "$universefile" "$gene_sanitized" > "$pairing_output/genes_not_found.txt" || true

"$BIN_PMET" \
    -d "$indexing_output"      \
    -g "$gene_tmp"             \
    -i "$icthresh"             \
    -p promoter_lengths.txt    \
    -b binomial_thresholds.txt \
    -c IC.txt                  \
    -f fimohits                \
    -o "$pairing_output"       \
    -t "$threads" > "$pairing_output/pmet.log"

# Merge ONLY pair_parallel's temp*.txt shards.
shopt -s nullglob
shards=("$pairing_output"/temp*.txt)
shopt -u nullglob
if (( ${#shards[@]} == 0 )); then
    error_exit "pair_parallel produced no temp*.txt shards (see $pairing_output/pmet.log)"
fi
cat "${shards[@]}" > "$pairing_output/motif_output.txt"
rm -f "${shards[@]}"

# Restore ':' in user-facing text outputs (binary fimohits stay sanitized).
for f in motif_output.txt genes_used_PMET.txt genes_not_found.txt; do
    p="$pairing_output/$f"
    if [[ -f "$p" ]]; then
        sed 's/__COLON__/:/g' "$p" > "$p.tmp" && mv "$p.tmp" "$p"
    fi
done

# ==============================================================================
# [3] Heatmaps
# ==============================================================================

print_green "\n[3/3] Generating heatmaps..."

if ! command -v Rscript >/dev/null 2>&1; then
    print_orange "   Rscript not found — skipping heatmaps. Main output (motif_output.txt) is unaffected."
else
    draw() { Rscript scripts/r/draw_heatmap.R "$@"; }
    draw All     "$plot_output/heatmap.png"                "$pairing_output/motif_output.txt" 5 3 6 FALSE
    draw Overlap "$plot_output/heatmap_overlap_unique.png" "$pairing_output/motif_output.txt" 5 3 6 TRUE
    draw Overlap "$plot_output/heatmap_overlap.png"        "$pairing_output/motif_output.txt" 5 3 6 FALSE
fi

print_green "\nDone."
print_elapsed_time "$grand_start"
