#!/usr/bin/env bash
# Run a pipeline end-to-end and immediately verify its output against the
# recorded baseline hashes.
#
# Usage:
#   bash tests/integration/run_with_verify.sh <NN> [<element>]
#
# where <NN> is the pipeline number (00, 01, 02, 03, 04, 05, 06, 07, 08)
# inherited from the pre-monorepo numbering. The runner paths below have
# been updated to the post-monorepo file layout (scripts/workflows/...);
# the recorded baselines under tests/integration/baselines/ were captured
# pre-monorepo and still reference the OLD dir names — see
# tests/integration/README.md "Baseline staleness" for the recapture
# procedure. Use this script for "did the runner stay invokable" smoke
# checking until the baselines are refreshed.
#
# What it does, per <NN>:
#   1. Removes any existing results/<results_dir>/ to ensure a fresh run.
#   2. Runs the pipeline under /usr/bin/time -l (macOS) when available.
#   3. Hashes the output and diffs against the recorded baseline via
#      verify_baseline.sh, with the standard exclude list.
#   4. Exits non-zero on any unexpected change.

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

# Map <element> shorthand → (-e flag value, results-dir suffix).
# `-e CDS` produces dir `..._CDS`; `-e 3UTR` is canonicalised inside
# elements.sh to `three_prime_UTR` for the dir name.
case "$element" in
    3utr) elem_flag="3UTR"; elem_suffix="three_prime_UTR" ;;
    5utr) elem_flag="5UTR"; elem_suffix="five_prime_UTR"  ;;
    mrna) elem_flag="mRNA"; elem_suffix="mRNA"            ;;
    cds)  elem_flag="CDS";  elem_suffix="CDS"             ;;
    exon) elem_flag="exon"; elem_suffix="exon"            ;;
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
        runner=(bash scripts/workflows/cli/01_perf_cpu.sh)
        results_dir=results/cli/01_perf_cpu
        baseline=$baselines_dir/01_baseline.hashes.txt
        ;;
    02)
        runner=(bash tests/integration/run_pipeline02_one_combo.sh)
        results_dir=results/02_perf_params
        baseline=$baselines_dir/02_one_combo_baseline.hashes.txt
        ;;
    03)
        runner=(bash scripts/workflows/promoter.sh)
        results_dir=results/cli/promoter
        baseline=$baselines_dir/03_baseline.hashes.txt
        ;;
    04)
        runner=(bash scripts/workflows/intervals.sh)
        results_dir=results/cli/intervals
        baseline=$baselines_dir/04_baseline.hashes.txt
        ;;
    05)
        runner=(bash scripts/workflows/cli/05_promoter_gap.sh)
        results_dir=results/05_promoter_gap
        baseline=$baselines_dir/05_baseline.hashes.txt
        ;;
    06)
        runner=(bash scripts/workflows/elements.sh -s longest -e "$elem_flag")
        results_dir=results/cli/elements_longest_${elem_suffix}
        # CDS keeps its existing canonical 06_baseline.* name (most-tested).
        # Other elements use a per-element suffix.
        if [[ "$element" == "cds" ]]; then
            baseline=$baselines_dir/06_baseline.hashes.txt
        else
            baseline=$baselines_dir/06_${element}_baseline.hashes.txt
        fi
        ;;
    07)
        runner=(bash scripts/workflows/elements.sh -s merged -e "$elem_flag")
        results_dir=results/cli/elements_merged_${elem_suffix}
        if [[ "$element" == "cds" ]]; then
            baseline=$baselines_dir/07_baseline.hashes.txt
        else
            baseline=$baselines_dir/07_${element}_baseline.hashes.txt
        fi
        ;;
    08)
        # 08 needs 03's homotypic index. If it's missing, point the user to
        # run 03 first instead of producing an opaque preflight error.
        if [[ ! -f results/cli/promoter/01_homotypic/universe.txt ]]; then
            echo "error: 08 needs results/cli/promoter/01_homotypic/ — run 'bash tests/integration/run_with_verify.sh 03' first" >&2
            exit 2
        fi
        runner=(bash scripts/workflows/pair_only.sh
                -d results/cli/promoter/01_homotypic
                -g data/genes/genes_cell_type_treatment.txt
                -o results/cli/pair_only/cell_type_treatment_ic4
                -i 4 -t 4)
        results_dir=results/cli/pair_only/cell_type_treatment_ic4
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
