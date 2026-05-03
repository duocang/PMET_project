#!/bin/bash
# ==============================================================================
# run_pairing — legacy pairing_parallel driver (consumes a pre-built index)
# ==============================================================================
# Runs the standalone legacy pairing_parallel binary against an existing
# homotypic index (promoter_lengths.txt + binomial_thresholds.txt + IC.txt
# + fimohits/ + universe.txt). The gene list is filtered against the
# universe up front so substring noise doesn't leak through.
#
# Superseded for routine use by scripts/workflows/pair_only.sh, which
# wraps the modern build/pairing_parallel with the same defaults the rest of
# the pipeline uses. This script is kept as a thin, dependency-free
# wrapper for parity testing against legacy index outputs.
#
# All parameters are required — no implicit defaults — so the caller has
# to be explicit about which binary, which index files, and which outputs.
# ==============================================================================

set -euo pipefail

usage() {
    cat >&2 <<'EOF'
USAGE: run_pairing.sh -e <executable> -g <gene_file> -u <universe_file> \
                      -p <promoter_lengths> -b <binomial_thresholds> \
                      -c <ic_file> -f <fimohits_dir> \
                      -i <ic_threshold> -x <0|1> -t <threads> -o <outdir>

Required:
  -e <executable>           path to legacy pairing_parallel binary
  -g <gene_file>            gene list (one gene per line)
  -u <universe_file>        universe.txt — index gene universe (used to
                            filter the gene list)
  -p <promoter_lengths>     promoter_lengths.txt
  -b <binomial_thresholds>  binomial_thresholds.txt
  -c <ic_file>              IC.txt (information content)
  -f <fimohits_dir>         fimohits/ directory
  -i <ic_threshold>         pairing IC threshold
  -x <0|1>                  scoring model: 0 = binomial, 1 = Poisson.
                            Required (no implicit default) so the scoring
                            choice is always explicit. The historical
                            apps/cli wrapper passed `-x "true"`, which
                            the binary parses as Poisson because of its
                            value[0] != '0' rule (see
                            core/pairing/src/main.cpp:184) — so legacy
                            baselines reproduce with -x 1.
  -t <threads>              number of threads
  -o <outdir>               output directory (will be wiped + recreated)

  -h                        show this help

Example (using the curated demo fixture; -x 1 reproduces legacy anchor):
  bash scripts/workflows_legacy/run_pairing.sh \
      -e core/pairing/build/pairing_parallel \
      -g data/demos/promoters/pairing/demo/gene.txt \
      -u data/demos/promoters/pairing/demo/universe.txt \
      -p data/demos/promoters/pairing/demo/promoter_lengths.txt \
      -b data/demos/promoters/pairing/demo/binomial_thresholds.txt \
      -c data/demos/promoters/pairing/demo/IC.txt \
      -f data/demos/promoters/pairing/demo/fimohits \
      -i 4 -x 0 -t 2 \
      -o results/cli/run_pairing_legacy
EOF
}

executable=
gene_file=
universe_file=
promoter_lengths=
binomial_thresholds=
ic_file=
fimohits_dir=
ic_threshold=
poisson=
threads=
outdir=

while getopts ":e:g:u:p:b:c:f:i:x:t:o:h" opt; do
    case $opt in
        e) executable=$OPTARG ;;
        g) gene_file=$OPTARG ;;
        u) universe_file=$OPTARG ;;
        p) promoter_lengths=$OPTARG ;;
        b) binomial_thresholds=$OPTARG ;;
        c) ic_file=$OPTARG ;;
        f) fimohits_dir=$OPTARG ;;
        i) ic_threshold=$OPTARG ;;
        x) poisson=$OPTARG ;;
        t) threads=$OPTARG ;;
        o) outdir=$OPTARG ;;
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done

missing=()
[[ -n "$executable"           ]] || missing+=("-e <executable>")
[[ -n "$gene_file"            ]] || missing+=("-g <gene_file>")
[[ -n "$universe_file"        ]] || missing+=("-u <universe_file>")
[[ -n "$promoter_lengths"     ]] || missing+=("-p <promoter_lengths>")
[[ -n "$binomial_thresholds"  ]] || missing+=("-b <binomial_thresholds>")
[[ -n "$ic_file"              ]] || missing+=("-c <ic_file>")
[[ -n "$fimohits_dir"         ]] || missing+=("-f <fimohits_dir>")
[[ -n "$ic_threshold"         ]] || missing+=("-i <ic_threshold>")
[[ -n "$poisson"              ]] || missing+=("-x <0|1>")
[[ -n "$threads"              ]] || missing+=("-t <threads>")
[[ -n "$outdir"               ]] || missing+=("-o <outdir>")
if (( ${#missing[@]} > 0 )); then
    echo "ERROR: missing required argument(s): ${missing[*]}" >&2
    usage
    exit 1
fi

# ==================== Preflight ====================

[[ -x "$executable"           ]] || { echo "ERROR: executable not found or not executable: $executable" >&2; exit 1; }
[[ -f "$gene_file"            ]] || { echo "ERROR: gene_file not found: $gene_file" >&2; exit 1; }
[[ -f "$universe_file"        ]] || { echo "ERROR: universe_file not found: $universe_file" >&2; exit 1; }
[[ -f "$promoter_lengths"     ]] || { echo "ERROR: promoter_lengths not found: $promoter_lengths" >&2; exit 1; }
[[ -f "$binomial_thresholds"  ]] || { echo "ERROR: binomial_thresholds not found: $binomial_thresholds" >&2; exit 1; }
[[ -f "$ic_file"              ]] || { echo "ERROR: ic_file not found: $ic_file" >&2; exit 1; }
[[ -d "$fimohits_dir"         ]] || { echo "ERROR: fimohits_dir not found: $fimohits_dir" >&2; exit 1; }
[[ "$poisson" =~ ^[01]$       ]] || { echo "ERROR: -x must be 0 (binomial) or 1 (Poisson), got: $poisson" >&2; exit 1; }

# Canonicalize input paths to absolute. The binary resolves -p/-b/-c/-f
# against the -d base, and we pass `-d /` to disable that resolution —
# but `/` + relative `data/foo` would still join to `/data/foo`. By
# converting to absolute up front, callers can pass relative paths and
# the script DTRT.
gene_file=$(realpath "$gene_file")
universe_file=$(realpath "$universe_file")
promoter_lengths=$(realpath "$promoter_lengths")
binomial_thresholds=$(realpath "$binomial_thresholds")
ic_file=$(realpath "$ic_file")
fimohits_dir=$(realpath "$fimohits_dir")
executable=$(realpath "$executable")

rm -rf "$outdir"
mkdir -p "$outdir"

# ==================== Filter gene list against universe ====================
# Substring-only `grep -F` (no `-w`) preserves the original demo's exact
# behavior; the modern pair_only.sh uses `-wFf` for word-boundary safety.

gene_filtered="$outdir/gene.txttemp"
grep -Ff "$universe_file" "$gene_file" > "$gene_filtered" || true
if [[ ! -s "$gene_filtered" ]]; then
    echo "ERROR: no genes from $gene_file matched universe $universe_file" >&2
    rm -f "$gene_filtered"
    exit 1
fi

# ==================== Run ====================

echo "Running legacy pairing_parallel..."
echo "  Executable           : $executable"
echo "  Gene file            : $gene_file (filtered: $(wc -l < "$gene_filtered") of $(wc -l < "$gene_file"))"
echo "  Universe             : $universe_file"
echo "  Promoter lengths     : $promoter_lengths"
echo "  Binomial thresholds  : $binomial_thresholds"
echo "  IC                   : $ic_file"
echo "  FIMO hits            : $fimohits_dir"
echo "  IC threshold         : $ic_threshold"
echo "  Scoring model        : $([[ $poisson = 1 ]] && echo Poisson || echo binomial) (-x $poisson)"
echo "  Threads              : $threads"
echo "  Output               : $outdir"

# Pass `-d /` so the binary doesn't try to resolve the granular file paths
# (which we already supplied as absolute / repo-rooted paths) against its
# default base of `.`.
"$executable" \
    -d "/"                      \
    -x "$poisson"               \
    -g "$gene_filtered"         \
    -i "$ic_threshold"          \
    -p "$promoter_lengths"      \
    -b "$binomial_thresholds"   \
    -c "$ic_file"               \
    -f "$fimohits_dir"          \
    -t "$threads"               \
    -o "$outdir"

# Merge per-thread temp shards into the canonical motif_output.txt.
shopt -s nullglob
shards=("$outdir"/temp*.txt)
shopt -u nullglob
if (( ${#shards[@]} > 0 )); then
    cat "${shards[@]}" > "$outdir/motif_output.txt"
    rm -f "${shards[@]}"
else
    echo "WARNING: pairing_parallel produced no temp*.txt shards" >&2
fi

rm -f "$gene_filtered"

echo "Done."
echo "Pairing results saved to $outdir/"
