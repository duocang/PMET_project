# shellcheck shell=bash
# Resolve the value passed to pairing_parallel's `-m` flag (MinHash prefilter
# minimum estimated intersection). The C++ side documents the flag in
# core/pairing/src/main.cpp; the calibration that picks the default lives in
# docs/perf/minhash_calibration.md.
#
# Usage:
#   minhash_min=$(resolve_minhash_min "$path/to/fimohits")
#
# Env overrides (highest priority first):
#   PMET_MINHASH_MIN=N        — force this exact value, skip auto-detection
#   PMET_MINHASH_THRESHOLD=N  — motif count at/above which auto-enable (default 500)
#   PMET_MINHASH_DEFAULT=N    — value used when auto-enabled (default 0; opt-in)
#
# Default policy: opt-in. The CIS-BP2 calibration sweep
# (docs/perf/minhash_calibration.md) found no operating point that reclaims
# meaningful runtime without a non-trivial false-negative rate, so the auto
# path returns 0 unless the operator explicitly sets PMET_MINHASH_DEFAULT.
# Power users who accept some FN can set PMET_MINHASH_MIN directly.
resolve_minhash_min() {
  local fimo_dir="$1"
  if [[ -n "${PMET_MINHASH_MIN:-}" ]]; then
    printf '%s' "$PMET_MINHASH_MIN"
    return
  fi
  if [[ ! -d "$fimo_dir" ]]; then
    printf '0'
    return
  fi
  local n threshold default
  n=$(ls -1 "$fimo_dir" 2>/dev/null | wc -l | tr -d ' ')
  threshold="${PMET_MINHASH_THRESHOLD:-500}"
  default="${PMET_MINHASH_DEFAULT:-0}"
  if (( n >= threshold )); then
    printf '%s' "$default"
  else
    printf '0'
  fi
}
