#!/usr/bin/env bash
# Compare current demo / binary fingerprints against the committed
# baseline. Substance only — header lines (timestamp / host / git SHA)
# are excluded from the comparison, so running on a different machine
# or commit doesn't false-positive.
#
# Exit 0 on no regression, non-zero on real divergence. The transient
# capture lands at tests/baseline/fingerprints.actual.txt (gitignored)
# so the operator can `diff` it themselves if needed.
#
# Usage: make baseline-check    (or: bash tests/baseline/check.sh)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

expected="tests/baseline/fingerprints.txt"
actual="tests/baseline/fingerprints.actual.txt"

if [ ! -f "$expected" ]; then
  echo "ERROR: no committed baseline at $expected" >&2
  echo "       Run 'make baseline-update' first to create one." >&2
  exit 2
fi

# Capture into the gitignored actual file. capture.sh prints both fresh
# header (timestamp + SHA — changes every run) and content (binary +
# output hashes — stable iff behaviour is stable).
bash tests/baseline/capture.sh > "$actual"

# Substance-only diff: strip the three header lines that are expected
# to differ between runs.
strip_header() {
  grep -vE '^# baseline captured|^# host|^# git' "$1"
}

if diff -u <(strip_header "$expected") <(strip_header "$actual") > /dev/null 2>&1; then
  echo "[baseline] OK — output hashes match $expected"
  rm -f "$actual"
  exit 0
fi

echo "[baseline] REGRESSION — output hashes diverged from $expected"
echo ""
diff -u <(strip_header "$expected") <(strip_header "$actual") || true
echo ""
echo "Full new capture saved at $actual (gitignored)."
echo "If this change is intentional, run:  make baseline-update"
exit 1
