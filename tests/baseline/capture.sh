#!/usr/bin/env bash
# Baseline fingerprint capture.
# Records: production binary hashes, demo output hashes, smoke status, pytest status.
# Run from repo root: bash tests/baseline/capture.sh > tests/baseline/fingerprints.txt
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Per-step stderr lands here instead of /tmp/baseline_*.log — survives
# across reboots, lives next to other gitignored test artefacts under
# results/tests/, and `make clean-tests` wipes the whole tree.
LOG_DIR="$ROOT/results/tests/baseline"
mkdir -p "$LOG_DIR"

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

# --------------------------------------------------------------------------
# Demo indexing — invoke build/indexing_fimo_fused directly on the demo
# fixture. Was previously delegated to apps/cli/scripts/run_indexing.sh,
# but that wrapper is gone (apps/cli was retired). Inlining is the right
# call here: this harness has exactly one job (capture deterministic SHA
# fingerprints of the C engine on a frozen fixture), the wrapper added no
# value beyond hard-coding these args, and inlining keeps the recorded
# anchors anchored to the literal command that produced them.
# --------------------------------------------------------------------------
DEMO_IDX="data/demos/promoters/indexing/demo"
for v in fused; do
  echo "## section:core_demo_run_indexing_$v"
  out_dir="$(mktemp -d)"
  if build/indexing_fimo_fused \
       --topk 5 --topn 5000 --no-qvalue --text \
       --thresh 0.05 --verbosity 1 \
       --bgfile "$DEMO_IDX/promoters.bg" \
       --oc "$out_dir/$v" \
       "$DEMO_IDX/motifs.txt" "$DEMO_IDX/promoters.fa" "$DEMO_IDX/promoter_lengths.txt" \
       >"$LOG_DIR/indexing_$v.log" 2>&1; then
    echo "# RUN_OK"
    hash_dir_files "$out_dir"
  else
    echo "# RUN_FAIL exit=$?"
    tail -20 "$LOG_DIR/indexing_$v.log" | sed 's/^/# /'
  fi
  rm -rf "$out_dir"
  echo ""
done

# --------------------------------------------------------------------------
# Demo pairing — same rationale as indexing above; previously delegated to
# the now-deleted apps/cli/scripts/run_pairing.sh.
#
# Scoring model: `-x 0` (binomial). The binary parses `-x` as
# `value[0] != '0'` (see core/pairing/src/main.cpp:184), so `-x 0`
# selects binomial and any other value flips Poisson on. The retired
# apps/cli wrapper passed `-x "true"` (Poisson), but every production
# code path — workflows/pair_only.sh, promoter.sh, intervals.sh, plus
# the modern tests/audit/ harness — runs binomial by default. Pinning
# baseline to binomial too makes this anchor representative of what
# the pipeline actually computes. The audit anchor 0af5b936... is the
# binomial counterpart and now matches the pairing anchor recorded in
# fingerprints.txt.
# --------------------------------------------------------------------------
DEMO_PAIR="data/demos/promoters/pairing/demo"
echo "## section:core_demo_run_pairing"
out_dir="$(mktemp -d)"
gene_filt="$out_dir/gene.filt"
grep -Ff "$DEMO_PAIR/universe.txt" "$DEMO_PAIR/gene.txt" > "$gene_filt"
if build/pairing_parallel \
     -d "$DEMO_PAIR" \
     -x 0 \
     -g "$gene_filt" \
     -i 4 \
     -p promoter_lengths.txt \
     -b binomial_thresholds.txt \
     -c IC.txt \
     -f fimohits \
     -t 2 \
     -o "$out_dir" >$LOG_DIR/pairing.log 2>&1; then
  # Merge per-thread temp shards into the canonical motif_output.txt
  # (pairing_parallel writes one shard per thread; the wrapper used to do
  # this concatenation outside the binary).
  if ls "$out_dir"/temp*.txt >/dev/null 2>&1; then
    cat "$out_dir"/temp*.txt > "$out_dir/motif_output.txt"
    rm -f "$out_dir"/temp*.txt
  fi
  rm -f "$gene_filt"
  echo "# RUN_OK"
  hash_dir_files "$out_dir"
else
  echo "# RUN_FAIL exit=$?"
  tail -20 $LOG_DIR/pairing.log | sed 's/^/# /'
fi
rm -rf "$out_dir"
echo ""

echo "## section:analysis_smoke"
if [ -f scripts/workflows/cli/00_env_check.sh ]; then
  if bash scripts/workflows/cli/00_env_check.sh >$LOG_DIR/env_check.log 2>&1; then
    echo "# SMOKE_OK"
    tail -5 $LOG_DIR/env_check.log | sed 's/^/# /'
  else
    echo "# SMOKE_FAIL exit=$?"
    tail -20 $LOG_DIR/env_check.log | sed 's/^/# /'
  fi
else
  echo "# SMOKE_SKIP scripts/workflows/cli/00_env_check.sh not found"
fi
echo ""

echo "## section:backend_pytest"
# Backend smoke needs the package on PYTHONPATH; running from apps/ gets
# `pmet_backend` discoverable as a top-level package.
if [ -f apps/pmet_backend/test_api.py ]; then
  if (cd apps && python3 pmet_backend/test_api.py) >$LOG_DIR/backend_pytest.log 2>&1; then
    echo "# PYTEST_OK"
  else
    echo "# PYTEST_FAIL exit=$?"
    tail -20 $LOG_DIR/backend_pytest.log | sed 's/^/# /'
  fi
else
  echo "# PYTEST_SKIP apps/pmet_backend/test_api.py not found"
fi
