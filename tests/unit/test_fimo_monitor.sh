#!/usr/bin/env bash
# Unit tests for scripts/lib/fimo_monitor.sh.
#
# Verifies the per-motif progress poller used by the homotypic stage of
# every workflow. Tests use a 1-second poll cadence and a tmpdir to keep
# wall time under ~6s.

set -uo pipefail

repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)
cd "$repo_root"

# shellcheck source=/dev/null
source scripts/lib/progress.sh
# shellcheck source=/dev/null
source scripts/lib/fimo_monitor.sh

export PMET_FIMO_MONITOR_POLL_SEC=1

failed=0
fail() { echo "  FAIL: $1"; failed=$((failed + 1)); }
pass() { echo "  ok   $1"; }

# ---- 1. CLI mode (PROGRESS_FILE unset) returns "0" + does not fork ----
unset PROGRESS_FILE
pid=$(start_fimo_monitor /tmp/x 5 stage 1 1 lbl)
[[ "$pid" == "0" ]] && pass "cli_mode_returns_zero" || fail "cli_mode_returns_zero (got $pid)"

# ---- 2. total=0 returns "0" (caller couldn't count motifs) ----
export PROGRESS_FILE=/tmp/pmet_fimo_monitor_test.json
rm -f "$PROGRESS_FILE"
pid=$(start_fimo_monitor /tmp/x 0 stage 1 1 lbl)
[[ "$pid" == "0" ]] && pass "zero_total_returns_zero" || fail "zero_total_returns_zero (got $pid)"

# ---- 3. monitor emits progress when files appear ----
tmpdir=$(mktemp -d)
fhd="$tmpdir/fimohits"
mkdir -p "$fhd"
rm -f "$PROGRESS_FILE"

pid=$(start_fimo_monitor "$fhd" 10 homotypic 1 3 "FIMO scan")
if [[ -z "$pid" || "$pid" == "0" ]]; then
    fail "monitor_emits_progress (start_fimo_monitor returned $pid)"
else
    sleep 1
    touch "$fhd/m1.txt" "$fhd/m2.txt" "$fhd/m3.txt"
    sleep 2
    if [[ -f "$PROGRESS_FILE" ]] && grep -q "3/10 motifs" "$PROGRESS_FILE"; then
        pass "monitor_emits_progress (3/10 motifs reported)"
    else
        fail "monitor_emits_progress (progress.json: $(cat "$PROGRESS_FILE" 2>/dev/null || echo missing))"
    fi
    stop_fimo_monitor "$pid"
fi

# ---- 4. monitor self-terminates after stop_fimo_monitor ----
sleep 1
if kill -0 "$pid" 2>/dev/null; then
    fail "monitor_stops_on_demand (pid $pid still alive)"
else
    pass "monitor_stops_on_demand"
fi

# ---- 5. stop_fimo_monitor 0 is a no-op ----
stop_fimo_monitor 0 && pass "stop_zero_is_noop" || fail "stop_zero_is_noop"

# ---- 6. count_meme_motifs counts MOTIF lines ----
mf="$tmpdir/example.meme"
{
    printf 'MEME version 4\n\n'
    printf 'MOTIF foo\n'
    printf 'letter-probability matrix:\n'
    printf 'MOTIF bar\n'
    printf 'MOTIF baz\n'
} > "$mf"
n=$(count_meme_motifs "$mf")
[[ "$n" == "3" ]] && pass "count_meme_motifs (3)" || fail "count_meme_motifs (got $n)"

n=$(count_meme_motifs /tmp/no_such_meme_file_for_test)
[[ "$n" == "0" ]] && pass "count_meme_motifs_missing_file" || fail "count_meme_motifs_missing_file (got $n)"

# ---- 7. monitor does not refresh progress when fimohits dir is empty ----
fhd2="$tmpdir/fimohits_empty"
mkdir -p "$fhd2"
rm -f "$PROGRESS_FILE"
pid=$(start_fimo_monitor "$fhd2" 10 homotypic 1 3 "FIMO scan")
sleep 2
if [[ -f "$PROGRESS_FILE" ]]; then
    # Allowed: a single emit for "0/10" (file count == initial last==-1 case).
    # Forbidden: stale heartbeat that hides a wedged FIMO.
    if grep -q "0/10 motifs" "$PROGRESS_FILE"; then
        pass "no_growth_no_extra_refresh (only initial 0/10 emit)"
    else
        fail "no_growth_no_extra_refresh (unexpected content: $(cat "$PROGRESS_FILE"))"
    fi
fi
stop_fimo_monitor "$pid"

rm -rf "$tmpdir" "$PROGRESS_FILE"

if (( failed > 0 )); then
    echo "[fimo_monitor] $failed failed"
    exit 1
fi
echo "[fimo_monitor] all passed"
