#!/usr/bin/env bash
# Progress reporter for the PMET workflow scripts.
#
# When the worker container invokes a workflow it sets PROGRESS_FILE to a
# path inside the task dir (e.g. results/app/<task_id>/progress.json). The
# scripts call emit_progress at stage boundaries to update that file; the
# frontend polls GET /api/tasks/<id>/progress and renders a progress bar +
# stage label without having to ssh into the worker.
#
# CLI runs leave PROGRESS_FILE unset and the calls degrade to no-ops.

# emit_progress <stage> <stage_index> <total_stages> <label>
emit_progress() {
    [[ -z "${PROGRESS_FILE:-}" ]] && return 0

    local stage=$1
    local stage_index=$2
    local total_stages=$3
    local label=$4

    # Atomic write so a poller never sees a torn JSON.
    local tmp="${PROGRESS_FILE}.tmp.$$"
    {
        printf '{\n'
        printf '  "stage": "%s",\n'         "$stage"
        printf '  "stage_index": %s,\n'     "$stage_index"
        printf '  "total_stages": %s,\n'    "$total_stages"
        printf '  "label": "%s",\n'         "$label"
        printf '  "updated_at": "%s"\n'     "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf '}\n'
    } > "$tmp" && mv -f "$tmp" "$PROGRESS_FILE"
}

# Convenience: clear-progress at completion. Frontend treats absence as
# "no longer running" too, but explicitly removing keeps the dir tidy.
clear_progress() {
    [[ -z "${PROGRESS_FILE:-}" ]] && return 0
    rm -f "$PROGRESS_FILE" 2>/dev/null || true
}
