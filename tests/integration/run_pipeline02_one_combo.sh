#!/usr/bin/env bash
# Run scripts/scripts/02 with a one-element grid so the post-fix output
# can be captured as a real-data regression baseline. The full grid is
# 4 tasks × 7 lengths × 9 maxk × 1 topn = 252 combinations; this harness
# copies the script to a temp file, rewrites the four grid arrays to a
# single point, and runs the patched copy.
#
# Default combo (configurable via env vars):
#   task=genes_cell_type_treatment
#   plen=200
#   maxk=5
#   topn=5000
#
# Designed to run end-to-end in roughly a minute on the project's TAIR10
# inputs. Outputs land under results/cli/02_benchmark_parameters/ as the real
# pipeline does — so don't run this and the full pipeline 02 in parallel.

set -uo pipefail

repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)
cd "$repo_root"

task=${TASK:-genes_cell_type_treatment}
plen=${PLEN:-200}
maxk=${MAXK:-5}
topn=${TOPN:-5000}

src=scripts/scripts/02_benchmark_parameters.sh

# The patched copy must live next to the original so its
# `script_dir=$(cd -- "$(dirname "$0")/../.." && pwd)` resolves to the repo
# root. /tmp would put script_dir somewhere unrelated and break every
# relative path. Use a deterministic name and clean up on EXIT.
patched=scripts/scripts/.smoke_02_one_combo.sh
trap 'rm -f "$patched"' EXIT

# Replace the 4 grid arrays with single-point versions, and force
# keep_intermediate=true so the post-fix promoter FASTA / promoter BED /
# binomial_thresholds files survive for hashing.
sed \
    -e "s/^tasks=(.*/tasks=($task)/" \
    -e "s/^promlength_values=(.*/promlength_values=($plen)/" \
    -e "s/^maxk_values=(.*/maxk_values=($maxk)/" \
    -e "s/^topn_values=(.*/topn_values=($topn)/" \
    -e "s|^keep_intermediate=.*|keep_intermediate=true  # forced by scripts/tests/run_pipeline02_one_combo.sh|" \
    "$src" > "$patched"

# Sanity: make sure exactly one of each array survived.
for v in tasks promlength_values maxk_values topn_values; do
    n=$(grep -c "^$v=(" "$patched")
    if [[ "$n" != "1" ]]; then
        echo "[02-one-combo] failed to rewrite $v ($n hits)" >&2
        exit 1
    fi
done

echo "[02-one-combo] task=$task plen=$plen maxk=$maxk topn=$topn"
chmod +x "$patched"
bash "$patched"
