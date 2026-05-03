#!/bin/bash
# ==============================================================================
# run_indexing — legacy pmetindex driver (consumes pre-computed FIMO hits)
# ==============================================================================
# The legacy two-step indexing path: run MEME's `fimo` first (see
# run_meme_fimo.sh), then feed the per-motif fimo hit files into a
# standalone pmetindex binary.
#
# Superseded for routine use by build/index_fimo_fused, which folds the
# FIMO scan and the pmetindex step into one process. This script is kept
# for parity testing against the legacy two-step pipeline and for working
# with pre-existing FIMO outputs.
#
# All parameters are required — no implicit defaults — so the caller has
# to be explicit about which binary, which inputs, and which outputs.
# ==============================================================================

set -euo pipefail

usage() {
    cat >&2 <<'EOF'
USAGE: run_indexing.sh -e <executable> -f <fimo_dir> -p <promoter_lengths> \
                       -o <outdir> -k <topk> -n <topn>

Required:
  -e <executable>        path to legacy pmetindex binary
                         (e.g. core/legacy/indexing_c/build/index_c)
  -f <fimo_dir>          directory of per-motif FIMO outputs
                         (produced by run_meme_fimo.sh)
  -p <promoter_lengths>  promoter_lengths.txt file
  -o <outdir>            output directory (will be wiped + recreated)
  -k <topk>              max motif hits per promoter
  -n <topn>              top n promoter hits per motif

  -h                     show this help

Example:
  bash scripts/workflows_legacy/run_meme_fimo.sh \
      -m data/demos/promoters/indexing/demo/motifs.txt \
      -p data/demos/promoters/indexing/demo/promoters.fa \
      -b data/demos/promoters/indexing/demo/promoters.bg \
      -o results/cli/run_meme_fimo

  bash scripts/workflows_legacy/run_indexing.sh \
      -e core/legacy/indexing_c/build/index_c \
      -f results/cli/run_meme_fimo \
      -p data/demos/promoters/indexing/demo/promoter_lengths.txt \
      -o results/cli/run_indexing_legacy \
      -k 5 -n 5000
EOF
}

executable=
fimo_dir=
promoter_lengths=
outdir=
topk=
topn=

while getopts ":e:f:p:o:k:n:h" opt; do
    case $opt in
        e) executable=$OPTARG ;;
        f) fimo_dir=$OPTARG ;;
        p) promoter_lengths=$OPTARG ;;
        o) outdir=$OPTARG ;;
        k) topk=$OPTARG ;;
        n) topn=$OPTARG ;;
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done

missing=()
[[ -n "$executable"        ]] || missing+=("-e <executable>")
[[ -n "$fimo_dir"          ]] || missing+=("-f <fimo_dir>")
[[ -n "$promoter_lengths"  ]] || missing+=("-p <promoter_lengths>")
[[ -n "$outdir"            ]] || missing+=("-o <outdir>")
[[ -n "$topk"              ]] || missing+=("-k <topk>")
[[ -n "$topn"              ]] || missing+=("-n <topn>")
if (( ${#missing[@]} > 0 )); then
    echo "ERROR: missing required argument(s): ${missing[*]}" >&2
    usage
    exit 1
fi

# ==================== Preflight ====================

[[ -x "$executable"        ]] || { echo "ERROR: executable not found or not executable: $executable" >&2; exit 1; }
[[ -d "$fimo_dir"          ]] || { echo "ERROR: fimo_dir not found: $fimo_dir" >&2; exit 1; }
[[ -n "$(ls -A "$fimo_dir" 2>/dev/null)" ]] || { echo "ERROR: fimo_dir is empty: $fimo_dir" >&2; exit 1; }
[[ -f "$promoter_lengths" && -s "$promoter_lengths" ]] || { echo "ERROR: promoter_lengths missing or empty: $promoter_lengths" >&2; exit 1; }

rm -rf "$outdir"
mkdir -p "$outdir"

# ==================== Run ====================

echo "Running legacy pmetindex..."
echo "  Executable       : $executable"
echo "  FIMO dir         : $fimo_dir"
echo "  Promoter lengths : $promoter_lengths"
echo "  topk / topn      : $topk / $topn"
echo "  Output           : $outdir"

"$executable" \
    -f "$fimo_dir"          \
    -k "$topk"              \
    -n "$topn"              \
    -p "$promoter_lengths"  \
    -o "$outdir"

# Stray progress sidecar some legacy builds drop into CWD.
rm -f progress.txt 2>/dev/null

echo "Done."
echo "Indexing results saved to $outdir/"
