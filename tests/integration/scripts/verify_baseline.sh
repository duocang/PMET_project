#!/usr/bin/env bash
# Compare a results directory against a recorded baseline hashes file.
#
# Usage:
#   scripts/tests/verify_baseline.sh <results_dir> <baseline.hashes.txt>
#
# Re-hashes every file under <results_dir>, diffs against the recorded
# baseline, and exits non-zero on any unexpected change. Lines whose path
# matches the EXCLUDE pattern (default: pmet.log + per-task .log files) are
# dropped from both sides — those contain mktemp paths and per-thread
# scheduling that are nondeterministic across runs and so cannot be a
# regression.
#
# Override the exclude pattern via the EXCLUDE env var:
#   EXCLUDE='/pmet.log$|/foo$' scripts/tests/verify_baseline.sh ...
#
# Examples:
#   bash scripts/scripts/03_promoter.sh
#   scripts/tests/verify_baseline.sh \
#       results/cli/03_promoter \
#       scripts/tests/baselines/03_baseline.hashes.txt
#
#   bash scripts/scripts/04_intervals.sh
#   scripts/tests/verify_baseline.sh \
#       results/cli/04_intervals \
#       scripts/tests/baselines/04_baseline.hashes.txt
#
# Exit codes:
#   0 - hashes match (after exclude filter)
#   1 - hashes diverge; full diff printed on stderr
#   2 - usage error or missing files

set -uo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <results_dir> <baseline.hashes.txt>" >&2
    exit 2
fi

results_dir=$1
baseline=$2

if [[ ! -d "$results_dir" ]]; then
    echo "error: results dir not found: $results_dir" >&2
    exit 2
fi
if [[ ! -f "$baseline" ]]; then
    echo "error: baseline hashes file not found: $baseline" >&2
    exit 2
fi

# Default exclude: log files (timestamps + tmp paths + thread ordering).
exclude=${EXCLUDE:-'/pmet\.log$|/[^/]*\.log$'}

current=$(mktemp)
trap 'rm -f "$current"' EXIT

find "$results_dir" -type f | sort | xargs shasum -a 256 > "$current"

base_filtered=$(mktemp)
curr_filtered=$(mktemp)
trap 'rm -f "$current" "$base_filtered" "$curr_filtered"' EXIT

grep -vE "$exclude" "$baseline" | sort > "$base_filtered"
grep -vE "$exclude" "$current"  | sort > "$curr_filtered"

base_count=$(wc -l < "$base_filtered" | tr -d ' ')
curr_count=$(wc -l < "$curr_filtered" | tr -d ' ')

if diff -q "$base_filtered" "$curr_filtered" >/dev/null; then
    echo "OK — $base_count files match (exclude=$exclude)"
    exit 0
fi

echo "FAIL — hashes diverge ($base_count baseline / $curr_count current files after exclude=$exclude)" >&2
echo "" >&2
echo "Differences (< baseline, > current):" >&2
diff "$base_filtered" "$curr_filtered" >&2
exit 1
