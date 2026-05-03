#!/usr/bin/env bash
# Baseline fingerprint capture.
# Records: production binary hashes, demo output hashes, smoke status, pytest status.
# Run from repo root: bash tests/baseline/capture.sh > tests/baseline/fingerprints.txt
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

hash_file() {
  if [ -f "$1" ]; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "MISSING"
  fi
}

hash_dir_files() {
  local d="$1"
  if [ -d "$d" ]; then
    (cd "$d" && find . -type f -not -name ".DS_Store" 2>/dev/null | sort | xargs shasum -a 256 2>/dev/null)
  else
    echo "DIR_MISSING $d"
  fi
}

echo "# baseline captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# host: $(uname -mrs)"
echo "# git: $(git rev-parse --short HEAD 2>/dev/null) on $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
echo ""

echo "## section:binaries"
for b in indexing_fimo_fused pairing_parallel; do
  printf "build/%s\t%s\n" "$b" "$(hash_file "build/$b")"
done
echo ""

echo "## section:core_demo_indexing_existing_outputs"
hash_dir_files "results/cli/demo/fimo_official"
echo ""

for v in fused; do
  echo "## section:core_demo_run_indexing_$v"
  out_dir="$(mktemp -d)"
  if bash apps/cli/scripts/run_indexing.sh -v "$v" -o "$out_dir" >"/tmp/baseline_idx_$v.log" 2>&1; then
    echo "# RUN_OK"
    hash_dir_files "$out_dir"
  else
    echo "# RUN_FAIL exit=$?"
    tail -20 "/tmp/baseline_idx_$v.log" | sed 's/^/# /'
  fi
  rm -rf "$out_dir"
  echo ""
done

echo "## section:core_demo_run_pairing"
out_dir="$(mktemp -d)"
if bash apps/cli/scripts/run_pairing.sh -o "$out_dir" >/tmp/baseline_pair.log 2>&1; then
  echo "# RUN_OK"
  hash_dir_files "$out_dir"
else
  echo "# RUN_FAIL exit=$?"
  tail -20 /tmp/baseline_pair.log | sed 's/^/# /'
fi
rm -rf "$out_dir"
echo ""

echo "## section:analysis_smoke"
# Still pre-refactor location until scripts/ workflows commit.
if [ -f pmet_analysis_pipeline/scripts/00_requirements.sh ]; then
  if bash pmet_analysis_pipeline/scripts/00_requirements.sh >/tmp/baseline_smoke.log 2>&1; then
    echo "# SMOKE_OK"
    tail -5 /tmp/baseline_smoke.log | sed 's/^/# /'
  else
    echo "# SMOKE_FAIL exit=$?"
    tail -20 /tmp/baseline_smoke.log | sed 's/^/# /'
  fi
elif [ -f scripts/workflows/cli/00_env_check.sh ]; then
  if bash scripts/workflows/cli/00_env_check.sh >/tmp/baseline_smoke.log 2>&1; then
    echo "# SMOKE_OK"
    tail -5 /tmp/baseline_smoke.log | sed 's/^/# /'
  else
    echo "# SMOKE_FAIL exit=$?"
    tail -20 /tmp/baseline_smoke.log | sed 's/^/# /'
  fi
else
  echo "# SMOKE_SKIP no requirements.sh found"
fi
echo ""

echo "## section:backend_pytest"
# Tries new location first, falls back to pre-refactor.
if [ -f apps/pmet_backend/test_api.py ]; then
  if (cd apps && python3 pmet_backend/test_api.py) >/tmp/baseline_pytest.log 2>&1; then
    echo "# PYTEST_OK"
  else
    echo "# PYTEST_FAIL exit=$?"
    tail -20 /tmp/baseline_pytest.log | sed 's/^/# /'
  fi
elif [ -f pmet_shiny_app/pmet_backend/test_api.py ]; then
  if (cd pmet_shiny_app && python3 pmet_backend/test_api.py) >/tmp/baseline_pytest.log 2>&1; then
    echo "# PYTEST_OK"
  else
    echo "# PYTEST_FAIL exit=$?"
    tail -20 /tmp/baseline_pytest.log | sed 's/^/# /'
  fi
else
  echo "# PYTEST_SKIP test_api.py not found"
fi
