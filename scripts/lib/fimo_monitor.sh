#!/usr/bin/env bash
# Background poller that turns "fimohits/<motif>.txt files appearing on disk"
# into per-motif progress.json updates while the homotypic FIMO scan runs.
#
# Why this exists
# ---------------
# emit_progress is called at *stage boundaries* by the workflow scripts, but
# the homotypic stage on a 1000+ motif library (CIS-BP2, JASPAR vertebrate)
# can take >15 min on its own. The liveness watchdog
# (apps/pmet_backend/worker/watchdog.py) treats absence of progress.json
# updates beyond LIVENESS_TIMEOUT_SEC (default 900 s) as "task stuck" and
# kills it. Without per-motif refreshes a legitimate long FIMO scan looks
# identical to a deadlock.
#
# Honest progress, not a fake heartbeat
# -------------------------------------
# The poller refreshes progress.json *only when the fimohits file count
# grows*. If FIMO actually wedges, no new files appear, the poller stops
# touching progress.json, and the watchdog still fires after its threshold.
# A blind `touch progress.json` loop would silence the watchdog entirely;
# this preserves it.
#
# Requires emit_progress (scripts/lib/progress.sh) to be sourced first.

# start_fimo_monitor <fimohits_dir> <total_motifs> <stage> <stage_idx> <total_stages> <label>
# Echoes the monitor PID. Caller passes that to stop_fimo_monitor when the
# FIMO step returns. Returns "0" when PROGRESS_FILE is unset (CLI mode) or
# total_motifs is 0 (caller couldn't count) — stop_fimo_monitor handles 0
# as a no-op so callers don't need to special-case.
start_fimo_monitor() {
    local dir=$1
    local total=$2
    local stage=$3
    local idx=$4
    local total_stages=$5
    local label=$6

    if [[ -z "${PROGRESS_FILE:-}" ]] || (( total <= 0 )); then
        echo 0
        return 0
    fi

    local poll=${PMET_FIMO_MONITOR_POLL_SEC:-30}
    local parent=$$

    # Redirect FDs *before* backgrounding: callers use `pid=$(start_…)` to
    # capture the PID, and $(…) waits for the substitution shell's stdout to
    # close. Without these redirects the backgrounded poller inherits the
    # captured stdout, $(…) hangs forever, and the caller never proceeds.
    (
        # Self-terminate if the workflow shell dies (crash, kill, watchdog).
        # Without this the subshell would orphan and keep touching the file
        # past the task's death.
        local last=-1
        while true; do
            sleep "$poll"
            kill -0 "$parent" 2>/dev/null || exit 0
            local n=0
            if [[ -d "$dir" ]]; then
                # Count regular files only — fimohits/<motif>.{txt,bin}.
                # Subdir entries (none expected, but defensive) are excluded.
                n=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
            fi
            if [[ "$n" != "$last" ]]; then
                emit_progress "$stage" "$idx" "$total_stages" \
                    "$label — $n/$total motifs"
                last=$n
            fi
        done
    ) </dev/null >/dev/null 2>&1 &
    echo $!
}

# stop_fimo_monitor <pid>
# Idempotent: 0 / empty / already-dead PIDs all no-op.
stop_fimo_monitor() {
    local pid=${1:-}
    [[ -z "$pid" || "$pid" == "0" ]] && return 0
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

# count_meme_motifs <meme_file>
# Echoes the number of MOTIF records, or 0 on missing file. Cheap helper
# so callers don't reinvent the grep idiom.
count_meme_motifs() {
    local meme=$1
    [[ -f "$meme" ]] || { echo 0; return; }
    grep -c '^MOTIF' "$meme" 2>/dev/null || echo 0
}
