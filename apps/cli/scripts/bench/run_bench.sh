#!/bin/bash
# Benchmark: large data indexing + pairing
# Records wall-clock and a deterministic hash of the outputs so we can
# compare baseline vs. optimized runs.
#
# Usage:
#   scripts/bench/run_bench.sh <label>
#
#   <label> appended to results/bench/, e.g. "baseline" or "binary-soa".

set -e

LABEL="${1:-run}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT"

DATA_DIR="$PROJECT_ROOT/data/cli/indexing/bench"
OUT_ROOT="$PROJECT_ROOT/results/bench/$LABEL"
INDEX_OUT="$OUT_ROOT/indexing"
PAIR_INPUT="$OUT_ROOT/pairing_input"
PAIR_OUT="$OUT_ROOT/pairing"
LOG_FILE="$OUT_ROOT/bench.log"

INDEX_BIN_SRC="$PROJECT_ROOT/build/index_fimo_fused"
PAIR_BIN_SRC="$PROJECT_ROOT/build/pair_parallel"
# Copy binaries into the run dir before invoking. Workaround: invoking the
# same binary path repeatedly from this checkout occasionally hangs at exec
# (suspected macOS hardened-runtime / kqueue interaction); a fresh path
# avoids it. The copies are also useful for archival of "what was tested".
INDEX_BIN=""
PAIR_BIN=""

NUM_THREADS="${NUM_THREADS:-8}"
# MinHash prefilter cutoff for the pair phase. 0 = disabled. Set via env so
# the same script handles baseline / binary-soa / minhash labels uniformly.
MINHASH_MIN="${MINHASH_MIN:-0}"

if [ ! -f "$INDEX_BIN_SRC" ]; then echo "missing $INDEX_BIN_SRC — build first"; exit 1; fi
if [ ! -f "$PAIR_BIN_SRC" ];  then echo "missing $PAIR_BIN_SRC — build first";  exit 1; fi
if [ ! -f "$DATA_DIR/promoters.bg" ]; then echo "missing $DATA_DIR/promoters.bg"; exit 1; fi
if [ ! -f "$DATA_DIR/gene.txt" ];     then echo "missing $DATA_DIR/gene.txt";     exit 1; fi

# When label starts with "baseline", force text fimohits (so the run reflects
# pre-optimization disk format); otherwise let the new binary writer kick in.
INDEX_FORMAT_FLAGS=()
case "$LABEL" in
  baseline*) INDEX_FORMAT_FLAGS+=("--text-output") ;;
  *)        ;;  # default = binary
esac

rm -rf "$OUT_ROOT"
mkdir -p "$INDEX_OUT" "$PAIR_INPUT" "$PAIR_OUT"

# Copy binaries into the run dir (see comment near INDEX_BIN_SRC).
INDEX_BIN="$OUT_ROOT/index_fimo_fused"
PAIR_BIN="$OUT_ROOT/pair_parallel"
cp "$INDEX_BIN_SRC" "$INDEX_BIN" && chmod +x "$INDEX_BIN"
cp "$PAIR_BIN_SRC"  "$PAIR_BIN"  && chmod +x "$PAIR_BIN"

# Portable wall-clock timer (seconds with ms). macOS date has no %N.
now_ms() { perl -MTime::HiRes=time -e 'printf("%.3f\n", time)'; }

run_timed() {
  local name="$1"; shift
  local t0 t1
  t0=$(now_ms)
  "$@" >> "$LOG_FILE" 2>&1
  t1=$(now_ms)
  awk -v n="$name" -v a="$t0" -v b="$t1" 'BEGIN{printf("%s %.3fs\n", n, b-a)}'
}

echo "=== bench label: $LABEL ===" | tee "$LOG_FILE"
echo "data: $DATA_DIR" | tee -a "$LOG_FILE"
echo "threads: $NUM_THREADS" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

# ---- 1. Indexing ----
echo "--- indexing ---" | tee -a "$LOG_FILE"
INDEX_TIME=$(run_timed indexing \
  "$INDEX_BIN" \
  --topk 5 --topn 5000 --no-qvalue --text --thresh 0.05 --verbosity 1 \
  "${INDEX_FORMAT_FLAGS[@]}" \
  --bgfile "$DATA_DIR/promoters.bg" \
  --oc "$INDEX_OUT" \
  "$DATA_DIR/motifs.meme" \
  "$DATA_DIR/promoters.fa" \
  "$DATA_DIR/promoter_lengths.txt")
echo "$INDEX_TIME" | tee -a "$LOG_FILE"

# ---- 2. Stage pairing inputs ----
cp "$DATA_DIR/gene.txt"             "$PAIR_INPUT/"
cp "$DATA_DIR/universe.txt"         "$PAIR_INPUT/"
cp "$DATA_DIR/IC.txt"               "$PAIR_INPUT/"
cp "$DATA_DIR/promoter_lengths.txt" "$PAIR_INPUT/"
cp -R "$INDEX_OUT/fimohits" "$PAIR_INPUT/"

# fused_fimo emits motif names UPPERCASED in binomial_thresholds.txt and as
# fimohits filenames, but keeps the original case in the fimohits column 1
# (which is what pairing uses as the lookup key against IC and thresholds).
# Rewrite binomial_thresholds.txt so its motif names match the fimohits payload.
python3 - "$INDEX_OUT/binomial_thresholds.txt" "$INDEX_OUT/fimohits" "$PAIR_INPUT/binomial_thresholds.txt" <<'PY'
import os, struct, sys
src_thresh, fimohits_dir, dst_thresh = sys.argv[1], sys.argv[2], sys.argv[3]

# Map UPPER motif name -> original-case motif name. For text fimohits, peek at
# column 1 of the first line. For binary fimohits (PMETBN01 magic), parse the
# header and read the embedded motif_name field.
upper_to_real = {}
for fname in os.listdir(fimohits_dir):
    if not (fname.endswith(".txt") or fname.endswith(".bin")):
        continue
    path = os.path.join(fimohits_dir, fname)
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
            if magic == b"PMETBN01":
                num_hits, name_pool_size, motif_name_len, _ = struct.unpack("<IIII", f.read(16))
                real = f.read(motif_name_len).decode()
            else:
                f.seek(0)
                first = f.readline().decode(errors="replace").strip()
                if not first:
                    continue
                real = first.split("\t", 1)[0]
        upper_to_real[real.upper()] = real
    except OSError:
        pass

with open(src_thresh) as f, open(dst_thresh, "w") as g:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if not parts:
            g.write(line); continue
        key = parts[0]
        real = upper_to_real.get(key, key)
        parts[0] = real
        g.write("\t".join(parts) + "\n")
PY

# Filter gene list to those present in universe (matches run_pairing.sh behavior)
grep -Ff "$PAIR_INPUT/universe.txt" "$PAIR_INPUT/gene.txt" > "$PAIR_INPUT/gene.filt"

# ---- 3. Pairing ----
echo "--- pairing ---" | tee -a "$LOG_FILE"
PAIR_TIME=$(run_timed pairing \
  "$PAIR_BIN" \
  -d "/" -x "true" \
  -g "$PAIR_INPUT/gene.filt" \
  -i 4 \
  -p "$PAIR_INPUT/promoter_lengths.txt" \
  -b "$PAIR_INPUT/binomial_thresholds.txt" \
  -c "$PAIR_INPUT/IC.txt" \
  -f "$PAIR_INPUT/fimohits" \
  -t "$NUM_THREADS" \
  -m "$MINHASH_MIN" \
  -o "$PAIR_OUT")
echo "$PAIR_TIME" | tee -a "$LOG_FILE"

# Merge per-thread temp output (mirrors run_pairing.sh)
if ls "$PAIR_OUT"/temp*.txt 1>/dev/null 2>&1; then
  cat "$PAIR_OUT"/temp*.txt > "$PAIR_OUT/motif_output.txt"
  rm -f "$PAIR_OUT"/temp*.txt
fi

# ---- 4. Result fingerprints ----
echo | tee -a "$LOG_FILE"
echo "--- fingerprints ---" | tee -a "$LOG_FILE"

# binomial_thresholds: sort to remove order non-determinism
THRESH_HASH=$(LC_ALL=C sort "$INDEX_OUT/binomial_thresholds.txt" | shasum -a 256 | awk '{print $1}')
echo "binomial_thresholds.sha256 $THRESH_HASH" | tee -a "$LOG_FILE"

# fimohits: decode each (binary or text) into a canonical text form, then hash.
# Canonical row: motif\tgene\tstart\tstop\tstrand\tscore_repr\tpVal_repr
# Floating-point values are formatted via %.10e on both sides (text path uses
# the same format string in writeVectorToStream), so the hash is comparable
# across binary vs text fimohits.
FIMOHITS_HASH=$(
python3 - "$INDEX_OUT/fimohits" <<'PY'
import hashlib, os, struct, sys
fimohits = sys.argv[1]
acc = hashlib.sha256()
for fname in sorted(os.listdir(fimohits)):
    path = os.path.join(fimohits, fname)
    rows = []
    with open(path, "rb") as f:
        magic = f.read(8)
        if magic == b"PMETBN01":
            num_hits, name_pool_size, motif_name_len, _ = struct.unpack("<IIII", f.read(16))
            motif_name = f.read(motif_name_len).decode()
            pool = f.read(name_pool_size)
            for _ in range(num_hits):
                rec = f.read(32)
                seq_off, start, stop = struct.unpack_from("<III", rec, 0)
                strand = chr(rec[12])
                score, pval = struct.unpack_from("<dd", rec, 16)
                end = pool.index(b"\x00", seq_off)
                gene = pool[seq_off:end].decode()
                rows.append(f"{motif_name}\t{gene}\t{start}\t{stop}\t{strand}\t{score:.10e}\t{pval:.10e}")
        else:
            f.seek(0)
            for line in f:
                parts = line.decode(errors="replace").rstrip("\n").split("\t")
                if len(parts) < 7:
                    continue
                # Strip optional matched_sequence column for canonical form
                rows.append("\t".join(parts[:7]))
    rows.sort()
    h = hashlib.sha256()
    for r in rows:
        h.update(r.encode()); h.update(b"\n")
    # Use stem (no extension) so binary .bin and text .txt of the same motif
    # hash to the same value when their contents are equivalent.
    acc.update(os.path.splitext(fname)[0].encode()); acc.update(b"=")
    acc.update(h.digest())
print(acc.hexdigest())
PY
)
echo "fimohits.sha256          $FIMOHITS_HASH" | tee -a "$LOG_FILE"

# pairing output
PAIR_HASH=$(LC_ALL=C sort "$PAIR_OUT/motif_output.txt" | shasum -a 256 | awk '{print $1}')
echo "pairing_output.sha256    $PAIR_HASH" | tee -a "$LOG_FILE"

# ---- 5. Summary line for easy diff ----
SUMMARY="$PROJECT_ROOT/results/bench/SUMMARY.tsv"
if [ ! -f "$SUMMARY" ]; then
  printf "label\tindex_s\tpair_s\tthresh_sha\tfimohits_sha\tpair_sha\n" > "$SUMMARY"
fi
INDEX_S=$(printf "%s\n" "$INDEX_TIME" | awk '{print $2}' | sed 's/s$//')
PAIR_S=$( printf "%s\n" "$PAIR_TIME"  | awk '{print $2}' | sed 's/s$//')
printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$LABEL" "$INDEX_S" "$PAIR_S" "$THRESH_HASH" "$FIMOHITS_HASH" "$PAIR_HASH" >> "$SUMMARY"

echo
echo "summary updated: $SUMMARY"
