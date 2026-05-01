#!/usr/bin/env bash
# MinHash prefilter calibration sweep on a real precomputed index.
#
# Goal: pick a default `-m <min_intersection>` that loses ≤ 0.1 % of the
# Bonferroni-significant pairs while shaving runtime. Drives Phase A of the
# "pair 粗筛" backlog item — see TODO.md for the full plan.
#
# Usage:
#   apps/cli/scripts/bench/calibrate_minhash.sh \
#       <precomputed_index_dir> <gene_list> [m_values...]
#
# Defaults (when invoked with no args):
#   index   = data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2
#   gene    = data/genes/random_genes_300.txt
#   m_values = 0 3 5 10 20
#
# Output:
#   results/bench/calibrate/<index_name>__<gene_name>/
#     ├ m=<K>/motif_output.txt   (full pair output for each K)
#     ├ m=<K>/log
#     ├ m=<K>/runtime_s
#     └ SUMMARY.tsv              (m, runtime_s, sha)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

INDEX_DIR="${1:-$REPO_ROOT/data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2}"
GENE_FILE="${2:-$REPO_ROOT/data/genes/random_genes_300.txt}"
shift 2 2>/dev/null || true
M_VALUES=("$@")
if [ "${#M_VALUES[@]}" -eq 0 ]; then
  M_VALUES=(0 3 5 10 20)
fi

# Resolve to absolute paths so the staging symlink + per-m output dirs work
# regardless of cwd at invocation.
INDEX_DIR="$(cd "$INDEX_DIR" && pwd)"
GENE_FILE="$(cd "$(dirname "$GENE_FILE")" && pwd)/$(basename "$GENE_FILE")"

[ -d "$INDEX_DIR/fimohits" ] || { echo "missing $INDEX_DIR/fimohits" >&2; exit 1; }
[ -f "$GENE_FILE" ] || { echo "missing $GENE_FILE" >&2; exit 1; }

PAIR_BIN="$REPO_ROOT/build/pair_parallel"
[ -x "$PAIR_BIN" ] || { echo "missing $PAIR_BIN — run 'make build'" >&2; exit 1; }

INDEX_NAME="$(basename "$(dirname "$INDEX_DIR")")__$(basename "$INDEX_DIR")"
GENE_NAME="$(basename "$GENE_FILE" .txt)"
OUT_ROOT="$REPO_ROOT/results/bench/calibrate/${INDEX_NAME}__${GENE_NAME}"
NUM_THREADS="${NUM_THREADS:-8}"

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

# Filter the gene list down to the universe up front so every -m run sees
# exactly the same input (the C++ side errors out on unknown gene IDs).
# Stage everything (incl. fimohits/ as a symlink) under $WORK so we can pass
# -d $WORK and let the C++ side prepend `inputDir + filename` cleanly.
WORK="$OUT_ROOT/_input"
mkdir -p "$WORK"
cp "$INDEX_DIR/promoter_lengths.txt" "$WORK/"
cp "$INDEX_DIR/IC.txt" "$WORK/"
cp "$INDEX_DIR/binomial_thresholds.txt" "$WORK/"
ln -sfn "$INDEX_DIR/fimohits" "$WORK/fimohits"
awk 'NR==FNR {u[$1]=1; next} ($2 in u)' \
    "$INDEX_DIR/universe.txt" "$GENE_FILE" > "$WORK/gene.filt"
GENES_USED=$(wc -l < "$WORK/gene.filt")
CLUSTERS=$(awk '{print $1}' "$WORK/gene.filt" | sort -u | wc -l | tr -d ' ')
NUM_MOTIFS=$(ls -1 "$INDEX_DIR/fimohits" | wc -l | tr -d ' ')

echo "Index:        $INDEX_DIR"
echo "Motifs:       $NUM_MOTIFS  (pairs ~ $((NUM_MOTIFS*(NUM_MOTIFS-1)/2)))"
echo "Gene file:    $GENE_FILE"
echo "Genes in universe: $GENES_USED  ($CLUSTERS clusters)"
echo "Threads:      $NUM_THREADS"
echo "Sweep m:      ${M_VALUES[*]}"
echo "Output:       $OUT_ROOT"
echo

SUMMARY="$OUT_ROOT/SUMMARY.tsv"
printf "m\truntime_s\tsha256\n" > "$SUMMARY"

now_ms() { perl -MTime::HiRes=time -e 'printf("%.3f\n", time)'; }

for M in "${M_VALUES[@]}"; do
  RUN_DIR="$OUT_ROOT/m=$M"
  mkdir -p "$RUN_DIR"
  echo ">>> running m=$M"
  T0=$(now_ms)
  "$PAIR_BIN" \
      -d "$WORK/" \
      -g "$WORK/gene.filt" \
      -i 4 \
      -p "promoter_lengths.txt" \
      -b "binomial_thresholds.txt" \
      -c "IC.txt" \
      -f "fimohits" \
      -o "$RUN_DIR/" \
      -t "$NUM_THREADS" \
      -m "$M" > "$RUN_DIR/log" 2>&1 || {
    echo "    FAILED (see $RUN_DIR/log)"
    printf "%s\tFAIL\tFAIL\n" "$M" >> "$SUMMARY"
    continue
  }
  T1=$(now_ms)
  RUNTIME=$(awk -v a="$T0" -v b="$T1" 'BEGIN{printf("%.2f", b-a)}')
  echo "$RUNTIME" > "$RUN_DIR/runtime_s"

  # Merge per-cluster shards into a single file, sorted for stable hashing.
  shopt -s nullglob
  shards=("$RUN_DIR"/temp*.txt)
  shopt -u nullglob
  if [ "${#shards[@]}" -eq 0 ]; then
    echo "    no temp*.txt shards (see $RUN_DIR/log)"
    printf "%s\t%s\tNOSHARDS\n" "$M" "$RUNTIME" >> "$SUMMARY"
    continue
  fi
  cat "${shards[@]}" > "$RUN_DIR/motif_output.txt"
  rm "$RUN_DIR"/temp*.txt
  SHA=$(LC_ALL=C sort "$RUN_DIR/motif_output.txt" | shasum -a 256 | awk '{print $1}')
  printf "%s\t%s\t%s\n" "$M" "$RUNTIME" "$SHA" >> "$SUMMARY"
  echo "    runtime=${RUNTIME}s  sha=${SHA:0:12}"
done

echo
echo "Summary written to $SUMMARY"
cat "$SUMMARY"
