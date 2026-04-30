#!/bin/bash
# ==============================================================================
# elements — PMET on a chosen genomic element (UTR / CDS / mRNA / exon)
# ==============================================================================
# Per-element homotypic indexing (delegated to cli/_pmet_index_element.sh)
# followed by heterotypic motif-pair enrichment + heatmaps for every gene
# task under data/genes/.
#
# Two isoform-aggregation strategies (-s):
#   longest : per gene, pick the single isoform whose total element length
#             is greatest and keep every fragment of that isoform.
#             For -e mRNA the chosen isoform's UTRs are subtracted to leave
#             CDS-spanning fragments (controlled inside _pmet_index_element).
#   merged  : per gene, take the union of all isoforms' element intervals
#             (overlapping intervals merged into a single non-redundant set).
#             No isoform specificity, no UTR subtraction.
#
# Merged from cli/06_elements_longest.sh + 07_elements_merged.sh + the
# previous _common.sh (which only those two wrappers source'd).
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$script_dir"

source scripts/lib/print_colors.sh
source scripts/lib/timer.sh

# ==================== Helpers / defaults ====================

usage() {
    cat >&2 <<'EOF'
USAGE: elements.sh [-s longest|merged] [-e <element>] [options]

Strategy + element (interactive prompt if either is omitted):
  -s <strategy>  isoform aggregation: longest | merged
  -e <element>   one of: 3UTR | 5UTR | mRNA | CDS | exon
                 (also accepts the GFF3 names: three_prime_UTR, five_prime_UTR)

Optional:
  -m <Yes|No>    only meaningful with `-s longest -e mRNA` — keep the full
                 mRNA span (Yes) or subtract that isoform's UTRs to leave
                 CDS-spanning fragments (No, default). Three biologically
                 distinct mRNA modes from -e mRNA + this flag:
                   -e mRNA -m Yes  : full mRNA (UTRs + CDS, single span)
                   -e mRNA -m No   : mRNA minus UTRs (CDS, but as one span
                                     per isoform — different from -e CDS,
                                     which gives per-CDS-fragment intervals)
                   -e CDS / exon   : per-fragment intervals (no aggregation)
                 Ignored for any other -e or -s merged.
  -t <threads>   threads (default: 8)
  -d <yes|no>    delete intermediate files in the homotypic stage
                 (default: longest=no, merged=yes — historical baselines)
  -h             show this help

Output:
  results/cli/elements_<strategy>_<element>/
    01_homotypic/                pmet index for the element
    02_heterotypic_<task>/       per-task pair_parallel output
    03_plot_<task>/              per-task heatmaps

Gene tasks are looped over all data/genes/*.txt files.
EOF
}

strategy=
genomic_element=
mrna_full=
threads=8
delete_temp=

while getopts ":s:e:m:t:d:h" opt; do
    case $opt in
        s) strategy=$OPTARG ;;
        e) genomic_element=$OPTARG ;;
        m) mrna_full=$OPTARG ;;
        t) threads=$OPTARG ;;
        d) delete_temp=$OPTARG ;;
        h) usage; exit 0 ;;
        \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
        :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
    esac
done

# Interactive fallback for missing -s.
if [[ -z $strategy ]]; then
    echo -e "Select isoform-aggregation strategy:\n    1. longest (per gene, longest isoform)\n    2. merged  (per gene, union across isoforms)"
    read -p "Enter your choice (1/2): " strat_choice
    case $strat_choice in
        1) strategy=longest ;;
        2) strategy=merged ;;
        *) echo "Invalid choice." >&2; exit 1 ;;
    esac
fi

case $strategy in
    longest|merged) ;;
    *) echo "Invalid -s '$strategy' (must be longest|merged)" >&2; exit 1 ;;
esac

# Map element shorthand + apply the GFF3-id-key convention each one uses.
# (mRNA uses ID=transcript:; everything else uses Parent=transcript:.)
declare gff3id=
case $genomic_element in
    "")  ;;  # unset, prompt below
    3UTR|three_prime_UTR) genomic_element=three_prime_UTR; gff3id='Parent=transcript:' ;;
    5UTR|five_prime_UTR)  genomic_element=five_prime_UTR;  gff3id='Parent=transcript:' ;;
    mRNA)                 gff3id='ID=transcript:' ;;
    CDS)                  gff3id='Parent=transcript:' ;;
    exon)                 gff3id='Parent=transcript:' ;;
    *) echo "Invalid -e '$genomic_element' (must be 3UTR|5UTR|mRNA|CDS|exon)" >&2; exit 1 ;;
esac

if [[ -z $genomic_element ]]; then
    echo -e "Select the genomic element:\n    1. 3' UTR\n    2. 5' UTR\n    3. mRNA\n    4. CDS\n    5. Exon"
    read -p "Enter your choice (1/2/3/4/5): " elem_choice
    case $elem_choice in
        1) genomic_element=three_prime_UTR; gff3id='Parent=transcript:' ;;
        2) genomic_element=five_prime_UTR;  gff3id='Parent=transcript:' ;;
        3) genomic_element=mRNA;            gff3id='ID=transcript:' ;;
        4) genomic_element=CDS;             gff3id='Parent=transcript:' ;;
        5) genomic_element=exon;            gff3id='Parent=transcript:' ;;
        *) echo "Invalid choice." >&2; exit 1 ;;
    esac
fi

# -m / mrna_full handling.
#   - Default No (the pre-merge 06_elements_longest.sh historical default).
#   - Validate Yes/No.
#   - Warn if the user passed -m with a strategy/element where it has no
#     effect — silently accepting it would mask a real misuse.
if [[ -z $mrna_full ]]; then
    mrna_full=No
fi
case $mrna_full in
    Yes|yes|Y|y|true)  mrna_full=Yes ;;
    No|no|N|n|false)   mrna_full=No  ;;
    *) echo "Invalid -m '$mrna_full' (must be Yes|No)" >&2; exit 1 ;;
esac
if [[ "$strategy" != "longest" || "$genomic_element" != "mRNA" ]] \
   && [[ "$mrna_full" == "Yes" ]]; then
    echo "Warning: -m only takes effect with -s longest -e mRNA; ignoring." >&2
    mrna_full=No
fi

# Default delete-intermediates differs between strategies (historical
# baselines from when 06/07 were separate wrappers — preserved here).
if [[ -z $delete_temp ]]; then
    case $strategy in
        longest) delete_temp=no ;;
        merged)  delete_temp=yes ;;
    esac
fi

print_fluorescent_yellow "Strategy:        $strategy"
print_fluorescent_yellow "Genomic element: $genomic_element ($gff3id)"
if [[ "$strategy" == "longest" && "$genomic_element" == "mRNA" ]]; then
    print_fluorescent_yellow "mRNA full span:  $mrna_full"
fi
print_fluorescent_yellow "Threads:         $threads"
print_fluorescent_yellow "Delete temps:    $delete_temp"

# ==================== Pin the canonical Franco-Zorrilla / TAIR10 inputs ====================

data_dir=data
fetch_script=scripts/fetch_reference.sh

if [[ ! -s "$data_dir/TAIR10.fasta" || ! -s "$data_dir/TAIR10.gff3" ]]; then
    print_fluorescent_yellow "Downloading genome and annotation...\n"
    bash "$fetch_script"
else
    print_green "Genome and annotation are ready!"
fi

genome=$data_dir/TAIR10.fasta
anno=$data_dir/TAIR10.gff3
meme=$data_dir/Franco-Zorrilla_et_al_2014.meme

# Chromosome naming preflight (saves 30+ minutes of "succeeded but empty"
# downstream work when GFF3 uses '1' against a FASTA using 'Chr1').
gff3_chr=$(awk -F'\t' '!/^#/ && NF>=9 {print $1; exit}' "$anno")
fasta_chr=$(grep '^>' "$genome" | head -1 | sed 's/^>//' | awk '{print $1}')
if [[ "$gff3_chr" != "$fasta_chr" ]]; then
    print_red "Chromosome name mismatch: GFF3='$gff3_chr' but FASTA='$fasta_chr'."
    exit 1
fi

# ==================== Output layout ====================

res_dir=results/cli/elements_${strategy}_${genomic_element}
homotypic_output=$res_dir/01_homotypic
het_output_base=$res_dir/02_heterotypic
plot_output_base=$res_dir/03_plot

mkdir -p "$homotypic_output"

# ==================== Indexing parameters (canonical defaults) ====================

toolDir=pipeline
HOMOTYPIC=$toolDir/workflows/cli/_pmet_index_element.sh
HETEROTYPIC=build/pair_parallel

overlap=NoOverlap
utr=Yes
topn=5000
maxk=5
length=1000
fimothresh=0.05
icthresh=4

# Fresh checkouts have these as 0644; pmet_index_element.sh aborts with
# Permission denied without an explicit +x.
chmod a+x "$HOMOTYPIC" "$HETEROTYPIC"

# ==================== [1/2] Homotypic indexing ====================

print_green "\n[1/2] Homotypic indexing..."
start_time=$SECONDS

$HOMOTYPIC                  \
    -r "$toolDir"           \
    -o "$homotypic_output"  \
    -s "$strategy"          \
    -e "$genomic_element"   \
    -m "$mrna_full"         \
    -i "$gff3id"            \
    -k "$maxk"              \
    -n "$topn"              \
    -p "$length"            \
    -v "$overlap"           \
    -u "$utr"               \
    -f "$fimothresh"        \
    -t "$threads"           \
    -d "$delete_temp"       \
    "$genome" "$anno" "$meme"

# ==================== [2/2] Heterotypic + heatmaps, per gene task ====================

print_green "\n[2/2] Heterotypic search per gene task in data/genes/"
shopt -s nullglob
gene_files=(data/genes/*.txt)
shopt -u nullglob
if (( ${#gene_files[@]} == 0 )); then
    print_red "No gene lists found under data/genes/*.txt — nothing to pair."
    exit 1
fi

for gene_input_file in "${gene_files[@]}"; do
    task=$(basename "$gene_input_file" .txt)
    heterotypic_output=${het_output_base}_${task}
    plot_output=${plot_output_base}_${task}
    mkdir -p "$heterotypic_output" "$plot_output"

    print_green "\n  ── task: $task"

    # Filter genes to those in the homotypic universe (pair_parallel rejects unknowns).
    grep -Ff "$homotypic_output/universe.txt" "$gene_input_file" \
        > "$heterotypic_output/new_genes_temp.txt" || true

    if [[ ! -s "$heterotypic_output/new_genes_temp.txt" ]]; then
        print_orange "    skipping — no genes from $task overlap the $genomic_element universe"
        rm -f "$heterotypic_output/new_genes_temp.txt"
        continue
    fi

    "$HETEROTYPIC" \
        -d .                                              \
        -g "$heterotypic_output/new_genes_temp.txt"       \
        -i "$icthresh"                                    \
        -p "$homotypic_output/promoter_lengths.txt"       \
        -b "$homotypic_output/binomial_thresholds.txt"    \
        -c "$homotypic_output/IC.txt"                     \
        -f "$homotypic_output/fimohits"                   \
        -o "$heterotypic_output"                          \
        -t "$threads" > "$heterotypic_output/pmet.log"

    rm -f "$heterotypic_output/new_genes_temp.txt"
    # Aggregate idempotently: stage to a tmp, drop any pair_parallel temp*.txt
    # shards, then move into place. A naive cat over *.txt would fold an old
    # motif_output.txt back in on a re-run.
    rm -f "$heterotypic_output/motif_output.txt"
    concat_tmp=$(mktemp)
    cat "$heterotypic_output"/*.txt > "$concat_tmp"
    rm -f "$heterotypic_output"/temp*.txt
    mv "$concat_tmp" "$heterotypic_output/motif_output.txt"

    print_elapsed_time $start_time
    print_green "    done: $task"

    # Heatmaps: skip gracefully if Rscript is absent so the data outputs
    # are still useful in container/CI without R installed.
    # Each draw call is wrapped with `|| print_orange "..."` so a single
    # heatmap failure (e.g. ggsave's 50-inch dimension cap on huge gene
    # lists) doesn't take down the rest of the for-loop's tasks.
    if command -v Rscript >/dev/null 2>&1; then
        draw() {
            Rscript scripts/r/draw_heatmap.R "$@" \
                || print_orange "    heatmap step failed for $(basename "$1") on $task — continuing"
        }
        draw All     "$plot_output/heatmap.png"                "$heterotypic_output/motif_output.txt" 15 3 6 FALSE
        draw Overlap "$plot_output/heatmap_overlap_unique.png" "$heterotypic_output/motif_output.txt" 15 3 6 TRUE
        draw Overlap "$plot_output/heatmap_overlap.png"        "$heterotypic_output/motif_output.txt" 15 3 6 FALSE
    fi
done

print_green "\nAll tasks done."
print_elapsed_time $start_time
