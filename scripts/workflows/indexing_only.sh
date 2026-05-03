#!/bin/bash
# ==============================================================================
# indexing_only — homotypic indexing stage only (no pairing, no heatmaps)
# ==============================================================================
# Builds a reusable homotypic index (genome/annotation prep -> promoter BED ->
# FIMO + pmetindex) and stops there. The resulting directory satisfies the
# homotypic contract (see docs/contracts/homotypic.md) and can be fed into
# pair_only.sh for downstream pairing runs.
#
# Use cases:
#   - precompute an index once for a (genome, motif library) pair, then sweep
#     gene lists / IC thresholds via pair_only.sh without re-doing FIMO
#   - regenerate a single Zenodo-style index from scratch
#
# Stages:
#   [1] Homotypic — genome/annotation prep -> promoter BED -> FIMO + pmetindex
#       via build/indexing_fimo_fused (delegated to scripts/python/run_homotypic.py)
#
# Derived from scripts/workflows/promoter.sh by stripping stages [2] and [3].
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
USAGE: indexing_only.sh [options] [<genome> <gff3> <memefile>]

Data (also settable as positional args in this order):
  -s <genome>            FASTA genome             (default: data/reference/TAIR10.fasta)
  -a <gff3>              GFF3 annotation          (default: data/reference/TAIR10.gff3)
  -m <memefile>          MEME motif file          (default: data/motifs/Franco-Zorrilla_et_al_2014.meme)

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

Runtime:
  -t <threads>           threads                                   (default: 4)
  -K <keep_intermediate> true | false                              (default: false)

Output:
  -o <homotypic_dir>     homotypic output         (default: results/cli/indexing_only)

Web-backend compat:
  -r <project_root>      override repo root for binary search (used in docker)

  -h                     show this help
EOF
}

# ==================== Defaults ====================

genome=data/reference/TAIR10.fasta
anno=data/reference/TAIR10.gff3
meme=data/motifs/Franco-Zorrilla_et_al_2014.meme

gff3id="gene_id="
gene_features=all
overlap=NoOverlap
utr=Yes
topn=5000
maxk=5
length=1000
fimothresh=0.05
isPoisson=false
threads=4
keep_intermediate=false

homotypic_output=results/cli/indexing_only
project_root=$script_dir

# ==================== Argument parsing ====================

while getopts ":s:a:m:i:F:v:u:n:k:p:f:P:t:K:o:r:h" opt; do
    case $opt in
        s) genome=$OPTARG ;;
        a) anno=$OPTARG ;;
        m) meme=$OPTARG ;;
        i) gff3id=$OPTARG ;;
        F) gene_features=$OPTARG ;;
        v) overlap=$OPTARG ;;
        u) utr=$OPTARG ;;
        n) topn=$OPTARG ;;
        k) maxk=$OPTARG ;;
        p) length=$OPTARG ;;
        f) fimothresh=$OPTARG ;;
        P) isPoisson=$OPTARG ;;
        t) threads=$OPTARG ;;
        K) keep_intermediate=$OPTARG ;;
        o) homotypic_output=$OPTARG ;;
        r) project_root=$OPTARG ;;
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done
shift $((OPTIND - 1))
[[ $# -ge 1 ]] && genome=$1
[[ $# -ge 2 ]] && anno=$2
[[ $# -ge 3 ]] && meme=$3

# ==================== Locate binaries ====================

BIN_DIR=
for cand in "$project_root/build" "$script_dir/build"; do
    if [[ -x "$cand/indexing_fimo_fused" ]]; then
        BIN_DIR=$cand
        break
    fi
done
[[ -n $BIN_DIR ]] || error_exit "PMET binary indexing_fimo_fused not found"
BIN_INDEX="$BIN_DIR/indexing_fimo_fused"

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

rm -rf "$homotypic_output"
mkdir -p "$homotypic_output"

grand_start=$SECONDS

# ==============================================================================
# [1] Homotypic
# ==============================================================================

print_green "\n[1/1] Homotypic motif search..."
emit_progress "homotypic" 1 1 "Homotypic motif search (FIMO scan)"
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

clear_progress
print_green "\nDone."
print_elapsed_time "$grand_start"
