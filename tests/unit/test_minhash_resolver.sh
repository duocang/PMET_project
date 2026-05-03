#!/usr/bin/env bash
# Unit test for scripts/lib/minhash.sh::resolve_minhash_min — the policy that
# decides what value each pairing_parallel invocation passes to its `-m` flag.
#
# The C++ engine accepts the flag verbatim; this resolver is the only place
# that picks a sensible default, so behavior is worth pinning.

set -uo pipefail

repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../scripts/lib/minhash.sh
source "$repo_root/scripts/lib/minhash.sh"

failed=0
total=0

assert_eq() {
  local label=$1 expected=$2 actual=$3
  total=$((total + 1))
  if [[ "$expected" == "$actual" ]]; then
    printf '  ok   %s\n' "$label"
  else
    printf '  FAIL %s: expected=%q got=%q\n' "$label" "$expected" "$actual"
    failed=$((failed + 1))
  fi
}

# Build temp fimohits-like dirs of two sizes.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/small/fimohits" "$tmp/large/fimohits"
for i in $(seq 1 100); do : > "$tmp/small/fimohits/m$i.txt"; done
for i in $(seq 1 600); do : > "$tmp/large/fimohits/m$i.txt"; done

# 1. Missing dir → 0 (don't accidentally enable on a malformed input)
unset PMET_MINHASH_MIN PMET_MINHASH_THRESHOLD PMET_MINHASH_DEFAULT
assert_eq "missing dir → 0" "0" "$(resolve_minhash_min /nonexistent/path)"

# 2. Small library → 0 (below the auto threshold)
assert_eq "small lib (100 motifs) → 0" "0" "$(resolve_minhash_min "$tmp/small/fimohits")"

# 3. Large library still defaults to 0 (calibration found no good auto value).
assert_eq "large lib (600 motifs) → 0 (auto opt-in)" "0" "$(resolve_minhash_min "$tmp/large/fimohits")"

# 4. PMET_MINHASH_MIN forces an exact value, regardless of size.
# Use 0 (legitimate "off" override) to confirm even falsy values aren't fallen through.
assert_eq "explicit MIN=0 even on large" "0" \
  "$(PMET_MINHASH_MIN=0 resolve_minhash_min "$tmp/large/fimohits")"
assert_eq "explicit MIN=99 on small" "99" \
  "$(PMET_MINHASH_MIN=99 resolve_minhash_min "$tmp/small/fimohits")"

# 5. PMET_MINHASH_THRESHOLD shifts the auto cutoff (still gated on DEFAULT being set).
assert_eq "lowered threshold + DEFAULT=5 flips small → 5" "5" \
  "$(PMET_MINHASH_THRESHOLD=50 PMET_MINHASH_DEFAULT=5 resolve_minhash_min "$tmp/small/fimohits")"
assert_eq "raised threshold keeps large → 0" "0" \
  "$(PMET_MINHASH_THRESHOLD=10000 resolve_minhash_min "$tmp/large/fimohits")"

# 6. PMET_MINHASH_DEFAULT replaces the auto-enabled value.
assert_eq "DEFAULT=8 on large" "8" \
  "$(PMET_MINHASH_DEFAULT=8 resolve_minhash_min "$tmp/large/fimohits")"

# 7. PMET_MINHASH_MIN takes priority over THRESHOLD/DEFAULT.
assert_eq "MIN wins over DEFAULT/THRESHOLD" "42" \
  "$(PMET_MINHASH_MIN=42 PMET_MINHASH_DEFAULT=99 PMET_MINHASH_THRESHOLD=10 \
       resolve_minhash_min "$tmp/large/fimohits")"

if (( failed == 0 )); then
  printf '\n[minhash resolver] %d/%d ok\n' "$total" "$total"
  exit 0
else
  printf '\n[minhash resolver] %d FAIL of %d\n' "$failed" "$total"
  exit 1
fi
