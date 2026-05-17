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

run_one "minhash resolver policy (bash)" \
    bash tests/unit/test_minhash_resolver.sh

run_one "fimo progress monitor (bash)" \
    bash tests/unit/test_fimo_monitor.sh

run_one "list_tasks pagination + filter (Python)" \
    "$PYTHON" tests/unit/test_list_tasks_pagination.py

# Backend security: upload-session binding + task-creation hardening.
# These tests live next to the code they cover (apps/pmet_backend/)
# rather than under tests/unit/ — historical placement. Running them
# from `apps/` puts `pmet_backend` on sys.path as a top-level package.
run_one "task creation security: session binding + token (Python)" \
    bash -c "cd apps && \"$PYTHON\" -m unittest -v pmet_backend.test_task_creation_security 2>&1 | tail -5"

run_one "upload routes: types / gzip / size caps / sessions (Python)" \
    bash -c "cd apps && \"$PYTHON\" -m unittest -v pmet_backend.test_upload_routes 2>&1 | tail -5"

run_one "admin stats aggregator (Python)" \
    "$PYTHON" tests/unit/test_admin_stats.py

run_one "admin audit log helper (Python)" \
    "$PYTHON" tests/unit/test_audit.py

run_one "admin retention cleanup (Python)" \
    "$PYTHON" tests/unit/test_cleanup.py

run_one "admin self-test probes (Python)" \
    "$PYTHON" tests/unit/test_healthcheck.py

run_one "admin task-level endpoints (Python)" \
    "$PYTHON" tests/unit/test_admin_tasks.py

run_one "admin login throttle + token rotate (Python)" \
    "$PYTHON" tests/unit/test_admin_auth.py

# Frontend tsx tests (zustand stores + runtime formatters). Skip if
# node_modules isn't installed (CI / fresh checkout where the user
# hasn't run npm install yet).
if [[ -x "$repo_root/apps/pmet_frontend/node_modules/.bin/tsx" ]]; then
    run_one "frontend stores + runtime formatters (TypeScript)" \
        bash -c "cd apps/pmet_frontend && npm run --silent test:unit"
else
    printf '\n[unit] frontend stores + runtime formatters (TypeScript): SKIP — apps/pmet_frontend/node_modules not installed\n'
fi

printf '\n========================================\n'
if (( failed == 0 )); then
    printf '[unit] all %d test file(s) passed\n' "$total"
    exit 0
else
    printf '[unit] %d / %d test file(s) FAILED\n' "$failed" "$total"
    exit 1
fi
