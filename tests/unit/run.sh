#!/usr/bin/env bash
# Run all unit tests in tests/unit/. Each individual test file exits
# non-zero on failure; this wrapper aggregates and reports a summary.
#
# Designed to be cheap (< 5s wall) and self-contained — no docker, no
# full pipeline dependency. Use `tests/integration/` for the longer
# behavior-preserving tests, `tests/audit/` for canonical-input runs.
#
# Usage:
#   bash tests/unit/run.sh
#
# Exit code: 0 if all pass, 1 if any fail.

set -uo pipefail

repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)
cd "$repo_root"

failed=0
total=0

run_one() {
    local label=$1; shift
    total=$((total + 1))
    printf '\n[unit] %s\n' "$label"
    if "$@"; then
        :
    else
        failed=$((failed + 1))
    fi
}

# R unit tests
if command -v Rscript >/dev/null 2>&1; then
    run_one "heatmap compute_dims (R)" \
        Rscript tests/unit/test_heatmap_dim_cap.R
else
    printf '\n[unit] heatmap compute_dims (R): SKIP — Rscript not found\n'
fi

# Python unit tests
PYTHON=python3
if [[ -x /tmp/pmet_test_venv/bin/python ]]; then
    PYTHON=/tmp/pmet_test_venv/bin/python
fi
run_one "watchdog staleness (Python)" \
    "$PYTHON" tests/unit/test_watchdog_staleness.py

run_one "partial-result rescue link (Python)" \
    "$PYTHON" tests/unit/test_partial_result_link.py

run_one "stage status inference (Python)" \
    "$PYTHON" tests/unit/test_stage_status.py

run_one "mail dispatch templates (Python)" \
    "$PYTHON" tests/unit/test_mail_dispatch.py

run_one "error classification permanent vs transient (Python)" \
    "$PYTHON" tests/unit/test_error_classification.py

printf '\n========================================\n'
if (( failed == 0 )); then
    printf '[unit] all %d test file(s) passed\n' "$total"
    exit 0
else
    printf '[unit] %d / %d test file(s) FAILED\n' "$failed" "$total"
    exit 1
fi
