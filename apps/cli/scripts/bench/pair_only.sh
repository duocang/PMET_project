#!/bin/bash
# Re-run only the pair stage against an existing indexing output, time it,
# and check pair_output sha against the baseline anchor. Used between every
# refactor sub-task — full indexing+pairing bench takes ~6 min, this takes
# ~1 min.
#
# Usage: scripts/bench/pair_only.sh <label> [path-to-indexing-dir]
# Default indexing dir: results/bench/baseline/indexing  (text fimohits)

set -e
LABEL="${1:-pair-only}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT"
INDEX_DIR="${2:-$PROJECT_ROOT/results/bench/baseline/indexing}"

DATA_DIR="$PROJECT_ROOT/data/cli/indexing/bench"
OUT_ROOT="$PROJECT_ROOT/results/bench/pair-only/$LABEL"
PAIR_INPUT="$OUT_ROOT/in"
PAIR_OUT="$OUT_ROOT/out"

PAIR_BIN_SRC="$PROJECT_ROOT/build/pair_parallel"
[ -f "$PAIR_BIN_SRC" ] || { echo "missing $PAIR_BIN_SRC"; exit 1; }
[ -d "$INDEX_DIR/fimohits" ] || { echo "missing $INDEX_DIR/fimohits"; exit 1; }

NUM_THREADS="${NUM_THREADS:-8}"
MINHASH_MIN="${MINHASH_MIN:-0}"

rm -rf "$OUT_ROOT"
mkdir -p "$PAIR_INPUT" "$PAIR_OUT"

PAIR_BIN="$OUT_ROOT/pair_parallel"
cp "$PAIR_BIN_SRC" "$PAIR_BIN" && chmod +x "$PAIR_BIN"

cp "$DATA_DIR/gene.txt" "$DATA_DIR/universe.txt" "$DATA_DIR/IC.txt" \
   "$DATA_DIR/promoter_lengths.txt" "$PAIR_INPUT/"
cp -R "$INDEX_DIR/fimohits" "$PAIR_INPUT/"

# Normalize binomial_thresholds motif names to the actual case used in the
# fimohits payload (shared logic with run_bench.sh).
python3 - "$INDEX_DIR/binomial_thresholds.txt" "$PAIR_INPUT/fimohits" "$PAIR_INPUT/binomial_thresholds.txt" <<'PY'
import os, struct, sys
src, dirp, dst = sys.argv[1:]
m = {}
for f in os.listdir(dirp):
    p = os.path.join(dirp, f)
    with open(p, "rb") as fh:
        magic = fh.read(8)
        if magic == b"PMETBN01":
            n,nps,mnl,_ = struct.unpack("<IIII", fh.read(16))
            real = fh.read(mnl).decode()
        else:
            fh.seek(0); real = fh.readline().decode().split("\t",1)[0]
    m[real.upper()] = real
with open(src) as f, open(dst,"w") as g:
    for line in f:
        p = line.rstrip("\n").split("\t")
        if p: p[0] = m.get(p[0], p[0])
        g.write("\t".join(p)+"\n")
PY
grep -Ff "$PAIR_INPUT/universe.txt" "$PAIR_INPUT/gene.txt" > "$PAIR_INPUT/gene.filt"

now_ms() { perl -MTime::HiRes=time -e 'printf("%.3f\n", time)'; }
T0=$(now_ms)
"$PAIR_BIN" \
  -d "/" -x "true" \
  -g "$PAIR_INPUT/gene.filt" -i 4 \
  -p "$PAIR_INPUT/promoter_lengths.txt" \
  -b "$PAIR_INPUT/binomial_thresholds.txt" \
  -c "$PAIR_INPUT/IC.txt" \
  -f "$PAIR_INPUT/fimohits" \
  -t "$NUM_THREADS" -m "$MINHASH_MIN" \
  -o "$PAIR_OUT" > "$OUT_ROOT/log" 2>&1
T1=$(now_ms)
PAIR_S=$(awk -v a="$T0" -v b="$T1" 'BEGIN{printf("%.3f", b-a)}')

cat "$PAIR_OUT"/temp*.txt > "$PAIR_OUT/motif_output.txt" && rm "$PAIR_OUT"/temp*.txt
SHA=$(LC_ALL=C sort "$PAIR_OUT/motif_output.txt" | shasum -a 256 | awk '{print $1}')

# Append a one-line record to a TSV that grows with the refactor.
SUMMARY="$PROJECT_ROOT/results/bench/pair-only/SUMMARY.tsv"
mkdir -p "$(dirname "$SUMMARY")"
[ -f "$SUMMARY" ] || printf "label\tpair_s\tpair_sha\n" > "$SUMMARY"
printf "%s\t%s\t%s\n" "$LABEL" "$PAIR_S" "$SHA" >> "$SUMMARY"

echo "label=$LABEL  pair_s=$PAIR_S  pair_sha=$SHA"
