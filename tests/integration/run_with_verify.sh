#!/usr/bin/env bash
# Run a pipeline end-to-end and immediately verify its output against the
# recorded baseline hashes.
#
# Usage:
#   scripts/tests/run_with_verify.sh <NN>
#
# where <NN> is the pipeline number (00, 01, 02, 03, 04, 06, 07, 08).
#
# What it does, per <NN>:
#   1. Removes any existing results/<results_dir>/ to ensure a fresh run.
#   2. Runs the pipeline under /usr/bin/time -l (macOS) when available.
#   3. Hashes the output and diffs against the recorded baseline via
#      verify_baseline.sh, with the standard exclude list.
#   4. Exits non-zero on any unexpected change.
#
# This is the single supported entrypoint for the "modify → run → verify"
# loop required before commit.

set -uo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    cat <<EOF >&2
usage: $0 <NN> [<element>]
  <NN>      00, 01, 02, 03, 04, 05, 06, 07, 08
  <element> for 06/07 only — cds (default), mrna, exon, 3utr, 5utr
EOF
    exit 2
fi

nn=$1
element=${2:-cds}
script_dir=$(cd -- "$(dirname "$0")" && pwd)
repo_root=$(cd -- "$script_dir/../.." && pwd)
cd "$repo_root"

baselines_dir="$script_dir/baselines"
verify="$script_dir/verify_baseline.sh"

# Map <element> shorthand → menu choice fed to the interactive prompt
# inside scripts/scripts/_elements_common.sh.
case "$element" in
    3utr) elem_choice=1 ;;
    5utr) elem_choice=2 ;;
    mrna) elem_choice=3 ;;
    cds)  elem_choice=4 ;;
    exon) elem_choice=5 ;;
    *)
        echo "error: unknown element '$element' (expected cds,mrna,exon,3utr,5utr)" >&2
        exit 2
        ;;
esac

# Map <NN> → (pipeline script, results dir, baseline.hashes.txt, runner cmd).
case "$nn" in
    00)
        echo "[run_with_verify] 00_requirements is environment-only; running smoke instead" >&2
        exec bash "$script_dir/run_smoke.sh"
        ;;
    01)
        runner=(bash scripts/scripts/01_benchmark_cpu.sh)
        results_dir=results/01_benchmark_cpu
        baseline=$baselines_dir/01_baseline.hashes.txt
        ;;
    02)
        runner=(bash scripts/tests/run_pipeline02_one_combo.sh)
        results_dir=results/cli/02_benchmark_parameters
        baseline=$baselines_dir/02_one_combo_baseline.hashes.txt
        ;;
    03)
        runner=(bash scripts/scripts/03_promoter.sh)
        results_dir=results/cli/03_promoter
        baseline=$baselines_dir/03_baseline.hashes.txt
        ;;
    04)
        runner=(bash scripts/scripts/04_intervals.sh)
        results_dir=results/cli/04_intervals
        baseline=$baselines_dir/04_baseline.hashes.txt
        ;;
    05)
        runner=(bash scripts/scripts/05_promoter_gap.sh)
        results_dir=results/05_promoter_gap
        baseline=$baselines_dir/05_baseline.hashes.txt
        ;;
    06)
        runner=(bash -c "printf '${elem_choice}\n' | bash scripts/scripts/06_elements_longest.sh")
        results_dir=results/06_elements_longest
        # CDS keeps its existing canonical 06_baseline.* name (most-tested).
        # Other elements use a per-element suffix.
        if [[ "$element" == "cds" ]]; then
            baseline=$baselines_dir/06_baseline.hashes.txt
        else
            baseline=$baselines_dir/06_${element}_baseline.hashes.txt
        fi
        ;;
    07)
        runner=(bash -c "printf '${elem_choice}\n' | bash scripts/scripts/07_elements_merged.sh")
        results_dir=results/07_elements_merged
        if [[ "$element" == "cds" ]]; then
            baseline=$baselines_dir/07_baseline.hashes.txt
        else
            baseline=$baselines_dir/07_${element}_baseline.hashes.txt
        fi
        ;;
    08)
        # 08 needs 03's homotypic index. If it's missing, point the user to
        # run 03 first instead of producing an opaque preflight error.
        if [[ ! -f results/cli/03_promoter/01_homotypic/universe.txt ]]; then
            echo "error: 08 needs results/cli/03_promoter/01_homotypic/ — run 'bash scripts/tests/run_with_verify.sh 03' first" >&2
            exit 2
        fi
        runner=(bash scripts/scripts/08_pair_only.sh
                -d results/cli/03_promoter/01_homotypic
                -g data/genes/genes_cell_type_treatment.txt
                -o results/cli/08_pair_only/cell_type_treatment_ic4
                -i 4 -t 4)
        results_dir=results/cli/08_pair_only/cell_type_treatment_ic4
        baseline=$baselines_dir/08_baseline.hashes.txt
        ;;
    *)
        echo "error: unknown pipeline number '$nn' (expected 00,01,02,03,04,05,06,07,08)" >&2
        exit 2
        ;;
esac

if [[ ! -f "$baseline" ]]; then
    echo "error: baseline not found: $baseline" >&2
    exit 2
fi

echo "[run_with_verify] $nn → $results_dir (baseline=$(basename "$baseline"))"

rm -rf "$results_dir"

# /usr/bin/time -l on macOS, fallback to plain run elsewhere.
log_dir=$(mktemp -d)
trap 'rm -rf "$log_dir"' EXIT
stdout="$log_dir/stdout"
stderr="$log_dir/stderr"

if [[ -x /usr/bin/time ]] && /usr/bin/time -l true >/dev/null 2>&1; then
    /usr/bin/time -l "${runner[@]}" > "$stdout" 2> "$stderr"
    rc=$?
else
    "${runner[@]}" > "$stdout" 2> "$stderr"
    rc=$?
fi

if (( rc != 0 )); then
    echo "[run_with_verify] pipeline exited non-zero ($rc); see $log_dir/{stdout,stderr}" >&2
    tail -20 "$stderr" >&2
    exit "$rc"
fi

# Pull the macOS time block (if present) for a one-line runtime summary.
if grep -q 'maximum resident set size' "$stderr"; then
    wall=$(awk '/[0-9]+\.[0-9]+ +real/ { print $1; exit }' "$stderr")
    rss_bytes=$(awk '/maximum resident set size/ { print $1; exit }' "$stderr")
    rss_mb=$(awk -v b="$rss_bytes" 'BEGIN { printf "%.1f", b/1024/1024 }')
    echo "[run_with_verify] $nn ran in ${wall}s, peak RSS ${rss_mb} MB"
fi

echo "[run_with_verify] verifying $results_dir against $baseline"
bash "$verify" "$results_dir" "$baseline"
