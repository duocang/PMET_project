#!/usr/bin/env bash
# Run pipeline 08 (pair-only) across a grid of IC thresholds against a single
# pre-built homotypic index. Intended use: parameter exploration on a fixed
# gene list — measure how the heterotypic motif-pair set shifts as you tighten
# / relax the IC threshold, without paying for the homotypic indexing each
# time.
#
# Usage:
#   bash scripts/tests/run_pipeline08_ic_sweep.sh
#   IC_VALUES="2 4 6 8 10" bash scripts/tests/run_pipeline08_ic_sweep.sh
#   HOMOTYPIC=results/05_promoter_gap/01_homotypic \
#       GENE_LIST=data/genes/my_other_list.txt \
#       OUT_BASE=results/cli/08_pair_only/exp_2026q2 \
#       JOBS=2 \
#       bash scripts/tests/run_pipeline08_ic_sweep.sh
#
# Environment variables (all optional):
#   IC_VALUES   space-separated list of IC thresholds (default: "2 4 6 8")
#   HOMOTYPIC   homotypic index dir (default: results/cli/03_promoter/01_homotypic)
#   GENE_LIST   gene list (default: data/genes/genes_cell_type_treatment.txt)
#   OUT_BASE    base output dir (default: results/cli/08_pair_only/sweep_$(date +%Y%m%d_%H%M%S))
#   THREADS     pair_parallel threads per run (default: 4)
#   JOBS        how many 08 runs to launch concurrently (default: 1)
#               WARNING: each run uses $THREADS CPU; JOBS * THREADS should
#               not exceed your core count.
#
# Output layout:
#   $OUT_BASE/
#     ic2/{motif_output.txt, plot/, ...}
#     ic4/{...}
#     ic6/{...}
#     ic8/{...}
#     summary.tsv      ic | motif_output_lines | sha256 | wall_time_s | exit
#
# Exit codes:
#   0 — every IC succeeded; summary.tsv complete
#   1 — at least one IC failed; summary.tsv lists which

set -uo pipefail

repo_root=$(cd -- "$(dirname "$0")/../.." && pwd)
cd "$repo_root"

ic_values=${IC_VALUES:-"2 4 6 8"}
homotypic=${HOMOTYPIC:-results/cli/03_promoter/01_homotypic}
gene_list=${GENE_LIST:-data/genes/genes_cell_type_treatment.txt}
out_base=${OUT_BASE:-results/cli/08_pair_only/sweep_$(date +%Y%m%d_%H%M%S)}
threads=${THREADS:-4}
jobs=${JOBS:-1}

if [[ ! -f "$homotypic/universe.txt" ]]; then
    echo "error: HOMOTYPIC=$homotypic looks empty (no universe.txt). Run 03 first?" >&2
    exit 2
fi
if [[ ! -f "$gene_list" ]]; then
    echo "error: GENE_LIST=$gene_list not found" >&2
    exit 2
fi

mkdir -p "$out_base"
summary="$out_base/summary.tsv"
printf "ic\tmotif_output_lines\tsha256\twall_time_s\texit\n" > "$summary"

echo "[ic-sweep] homotypic=$homotypic"
echo "[ic-sweep] gene_list=$gene_list"
echo "[ic-sweep] ic_values=$ic_values  threads=$threads  jobs=$jobs"
echo "[ic-sweep] out_base=$out_base"
echo

# Run one IC value; appends one row to $summary on completion.
# Guarded by a per-IC subshell so failures don't kill peers under JOBS>1.
run_one_ic() {
    local ic=$1
    local out_dir="$out_base/ic${ic}"
    local log_dir
    log_dir=$(mktemp -d)
    local stdout="$log_dir/stdout"
    local stderr="$log_dir/stderr"

    local t0=$SECONDS
    local rc=0
    rm -rf "$out_dir"
    bash scripts/scripts/08_pair_only.sh \
        -d "$homotypic" \
        -g "$gene_list" \
        -o "$out_dir" \
        -i "$ic" \
        -t "$threads" \
        > "$stdout" 2> "$stderr" || rc=$?
    local elapsed=$((SECONDS - t0))

    local lines="-"
    local sha="-"
    if [[ $rc -eq 0 && -f "$out_dir/motif_output.txt" ]]; then
        lines=$(wc -l < "$out_dir/motif_output.txt" | tr -d ' ')
        sha=$(shasum -a 256 "$out_dir/motif_output.txt" | awk '{print $1}')
    else
        # Surface the tail of stderr so the user knows what failed.
        echo "[ic-sweep] ic=$ic FAILED (exit $rc); see $log_dir/stderr" >&2
        tail -5 "$stderr" >&2
    fi

    # Atomic append — single printf is one write() syscall under typical FS.
    printf "%s\t%s\t%s\t%s\t%s\n" "$ic" "$lines" "$sha" "$elapsed" "$rc" >> "$summary"

    if [[ $rc -eq 0 ]]; then
        echo "[ic-sweep] ic=$ic OK  ${elapsed}s  ${lines} lines  sha=${sha:0:12}…"
    fi

    rm -rf "$log_dir"
    return "$rc"
}

# Drive the grid. Sequential by default; respect JOBS for fan-out.
overall_rc=0
if (( jobs <= 1 )); then
    for ic in $ic_values; do
        run_one_ic "$ic" || overall_rc=1
    done
else
    pids=()
    for ic in $ic_values; do
        run_one_ic "$ic" &
        pids+=($!)
        # Throttle to $jobs concurrent runs.
        while (( $(jobs -rp | wc -l) >= jobs )); do
            sleep 0.5
        done
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || overall_rc=1
    done
fi

echo
echo "[ic-sweep] summary ($summary):"
column -t -s $'\t' "$summary"

exit "$overall_rc"
