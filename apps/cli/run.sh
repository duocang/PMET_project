#!/bin/bash
# ==============================================================================
# PMET Analysis Pipeline Runner
# ==============================================================================
# Interactive menu to select and run analysis pipelines
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "$0")/../.." && pwd)
# Top-level merged workflows (post-dedup) live at scripts/workflows/;
# numbered ones still live under cli/. Both are surfaced in the menu.
pipeline_dir="$script_dir/scripts/workflows/cli"
top_workflows_dir="$script_dir/scripts/workflows"

# Load color helpers
if [ -f "$script_dir/scripts/lib/print_colors.sh" ]; then
    source "$script_dir/scripts/lib/print_colors.sh"
else
    print_green()  { printf "\033[32m%s\033[0m\n" "$1"; }
    print_orange() { printf "\033[33m%s\033[0m\n" "$1"; }
    print_yellow() { printf "\033[93m%s\033[0m\n" "$1"; }
    print_red()    { printf "\033[31m%s\033[0m\n" "$1"; }
    print_white()  { printf "\033[37m%s\033[0m" "$1"; }
fi

# ==============================================================================
# Pipeline Descriptions
# ==============================================================================

get_description() {
    case "$1" in
        promoter.sh)            echo "Run PMET on promoter regions (homotypic + heterotypic + heatmaps)" ;;
        intervals.sh)           echo "Run PMET on genomic intervals (e.g., ATAC-seq peaks)" ;;
        elements.sh)            echo "Run PMET on a genomic element (UTR/CDS/mRNA/exon) — prompts for strategy + element" ;;
        pair_only.sh)           echo "Re-pair an existing homotypic index (skips indexing; needs promoter.sh output by default)" ;;
        00_env_check.sh)        echo "Check system requirements and setup PMET environment" ;;
        01_perf_cpu.sh)         echo "Perf benchmark: heterotypic analysis (single CPU vs parallel)" ;;
        02_perf_params.sh)      echo "Perf benchmark: sweep PMET parameters on promoters" ;;
        05_promoter_gap.sh)     echo "Run PMET on promoters with a TSS-proximal gap" ;;
        *) echo "No description available" ;;
    esac
}

# ==============================================================================
# Functions
# ==============================================================================

show_header() {
    clear
    print_yellow "╔══════════════════════════════════════════════════════════════════╗"
    print_yellow "║              PMET Analysis Pipeline Runner                       ║"
    print_yellow "╚══════════════════════════════════════════════════════════════════╝"
    echo
}

show_menu() {
    print_orange "Available Pipelines:"
    print_orange "────────────────────────────────────────────────────────────────────"
    echo

    local i=0
    for script in "${pipelines[@]}"; do
        local desc=$(get_description "$script")
        print_white "  [$i] "
        print_green "$script"
        print_orange "      $desc"
        echo
        i=$((i + 1))
    done

    print_orange "────────────────────────────────────────────────────────────────────"
    print_white "  [q] "
    echo "Quit"
    echo
}

run_pipeline() {
    local script="$1"
    local script_path
    # Resolve: top-level merged workflows take precedence over numbered cli/ ones.
    if [[ -f "$top_workflows_dir/$script" ]]; then
        script_path="$top_workflows_dir/$script"
    elif [[ -f "$pipeline_dir/$script" ]]; then
        script_path="$pipeline_dir/$script"
    else
        print_red "Error: Script not found: $script (looked in $top_workflows_dir and $pipeline_dir)"
        return 1
    fi

    echo
    print_yellow "══════════════════════════════════════════════════════════════════"
    print_green "Running: $script"
    print_yellow "══════════════════════════════════════════════════════════════════"
    echo

    local start_time=$SECONDS
    # The merged top-level workflows have sensible defaults for the
    # canonical demo runs, so the launcher just executes them. Override
    # any default by passing flags directly:
    #   bash scripts/workflows/promoter.sh -s <fasta> -a <gff3> ...
    case "$script" in
        pair_only.sh)
            # Reuses promoter.sh's homotypic index and the same canonical
            # gene list. Requires promoter.sh to have been run first
            # (preflight fails with a clear error otherwise).
            bash "$script_path" \
                -d "results/cli/promoter/01_homotypic"                \
                -g "data/genes/genes_cell_type_treatment.txt"     \
                -o "results/cli/pair_only/cell_type_treatment_ic4"    \
                -i 4                                              \
                -t 4
            ;;
        *)
            bash "$script_path"
            ;;
    esac
    local exit_code=$?
    local elapsed=$(( SECONDS - start_time ))
    local hours=$(( elapsed / 3600 ))
    local minutes=$(( (elapsed % 3600) / 60 ))
    local seconds=$(( elapsed % 60 ))

    echo
    if [ $exit_code -eq 0 ]; then
        print_green "✓ Pipeline completed successfully!"
    else
        print_red "✗ Pipeline exited with code: $exit_code"
    fi
    printf "  Elapsed time: %02d:%02d:%02d (hh:mm:ss)\n" "$hours" "$minutes" "$seconds"

    echo
    print_white "Press Enter to continue..."
    read -r
}

# ==============================================================================
# Main
# ==============================================================================

# Build the menu by globbing two dirs, in this order:
#   1) scripts/workflows/*.sh    — merged top-level workflows (no cli/web split)
#   2) scripts/workflows/cli/*.sh — still-numbered research workflows
# Each entry stores both the display name and the full path so the
# dispatcher can locate the script regardless of which dir it lives in.
# Skip files starting with `_` — library bodies meant for `source`.
pipelines=()
pipeline_paths=()
for f in "$top_workflows_dir"/*.sh "$pipeline_dir"/*.sh; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    [[ "$name" == _* ]] && continue
    pipelines+=("$name")
    pipeline_paths+=("$f")
done

if [ ${#pipelines[@]} -eq 0 ]; then
    print_red "No pipeline scripts found in $top_workflows_dir or $pipeline_dir"
    exit 1
fi

# Check if running with command line arguments
if [ $# -gt 0 ]; then
    arg="$1"

    # Try to match by index number
    if [[ "$arg" =~ ^[0-9]+$ ]]; then
        if [ "$arg" -ge 0 ] && [ "$arg" -lt ${#pipelines[@]} ]; then
            run_pipeline "${pipelines[$arg]}"
            exit $?
        else
            print_red "Error: Invalid pipeline index: $arg"
            print_orange "Valid range: 0-$((${#pipelines[@]}-1))"
            exit 1
        fi
    fi

    # Try to match by script name (exact match)
    for script in "${pipelines[@]}"; do
        if [ "$script" = "$arg" ]; then
            run_pipeline "$script"
            exit $?
        fi
    done

    # Try to match by partial name or keyword
    matches=()
    for i in "${!pipelines[@]}"; do
        if [[ "${pipelines[$i]}" == *"$arg"* ]]; then
            matches+=("$i")
        fi
    done

    if [ ${#matches[@]} -eq 1 ]; then
        run_pipeline "${pipelines[${matches[0]}]}"
        exit $?
    elif [ ${#matches[@]} -gt 1 ]; then
        print_red "Error: Ambiguous match for '$arg'. Multiple pipelines found:"
        for idx in "${matches[@]}"; do
            print_orange "  [$idx] ${pipelines[$idx]}"
        done
        exit 1
    else
        print_red "Error: No pipeline found matching '$arg'"
        print_orange "Available pipelines:"
        for i in "${!pipelines[@]}"; do
            print_orange "  [$i] ${pipelines[$i]}"
        done
        exit 1
    fi
fi

# Main loop (interactive mode)
while true; do
    show_header
    show_menu

    print_white "Select a pipeline [0-$((${#pipelines[@]}-1))] or [q]uit: "
    read -r choice

    case "$choice" in
        q|Q)
            print_green "Goodbye!"
            exit 0
            ;;
        [0-9]*)
            if [ "$choice" -ge 0 ] 2>/dev/null && [ "$choice" -lt ${#pipelines[@]} ] 2>/dev/null; then
                run_pipeline "${pipelines[$choice]}"
            else
                print_red "Invalid selection: $choice"
                sleep 1
            fi
            ;;
        *)
            print_red "Invalid input. Enter a number or 'q' to quit."
            sleep 1
            ;;
    esac
done
