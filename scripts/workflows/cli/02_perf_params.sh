#!/bin/bash
# ==============================================================================
# Pipeline 02: PMET parameter benchmark on promoters (merged: no wrapper)
# ==============================================================================
# Runs the full PMET parameter sweep in one script. Replaces the previous
# two-script flow that chained scripts/02 → scripts/indexing/promoters_benchmark.sh.
#
# Structure:
#   [A] shared/                — run once: genome strip, faidx, gene BED,
#                                length-to-TSS, memefile split, IC
#   [B] LEN{p}_FIMO{f}/        — run per promoter length: promoter BED + FASTA
#                                + Markov bg + promoter_lengths + universe
#   [C] LEN{p}_K{k}_N{n}_FIMO{f}/ — run per (length, maxk, topn): FIMO hits +
#                                   binomial thresholds (no cp -r explosion)
#   [D] 02_heterotypic/{task}_LEN..._K..._N..._FIMO.../ — pairing_parallel output
#       └── motif_output.txt   — what the user actually keeps
# ==============================================================================

set -euo pipefail

script_dir=$(cd -- "$(dirname "$0")/../../.." && pwd)
cd "$script_dir"
source scripts/lib/print_colors.sh
source scripts/lib/timer.sh

# ==================== Configuration ====================

# Data
genome=data/reference/TAIR10.fasta
anno=data/reference/TAIR10.gff3
meme=data/motifs/Franco-Zorrilla_et_al_2014.meme

# Biology parameters
overlap=Yes              # Yes / NoOverlap (NoOverlap = subtract gene bodies)
utr=No                   # Yes / No (Yes = extend promoter into 5' UTR)
gff3id="gene_id="
gene_features=all        # all / strict — see docs/contracts/homotypic.md
                         #   all    → regex 'gene$': gene + ncRNA_gene + pseudogene + …
                         #   strict → regex '^gene$': only canonical 'gene' rows
fimothresh=0.05          # numeric value for FIMO
fimothresh_label=005     # filename label (no dot, matches historic layout)
icthresh=4

# Runtime
threads=8

# Parameter grid
tasks=(genes_cell_type_treatment gene_cortex_epidermis_pericycle salt_top300 heat_top300)
promlength_values=(50 200 500 1000 1500 2500 5000)
maxk_values=(1 2 3 4 5 6 7 8 9)
topn_values=(5000)

# Behavior
keep_intermediate=false  # false: delete shared/, per-length and per-combo dirs when no longer needed

# Output
res_dir=results/02_perf_params
shared_dir="$res_dir/shared"
heterotypic_output="$res_dir/02_heterotypic"
plot_output="$res_dir/heatmap"
logDir="$res_dir/logs"

mkdir -p "$shared_dir" "$heterotypic_output" "$plot_output" "$logDir"

# Binaries / tools
BIN_DIR=build
BIN_FIMO="$BIN_DIR/fimo"
BIN_PMET="$BIN_DIR/pairing_parallel"
PY=scripts/python

# ==================== Preflight ====================

for f in "$genome" "$anno" "$meme" "$BIN_FIMO" "$BIN_PMET"; do
    if [[ ! -f "$f" ]]; then
        print_red "Required input not found: $f"
        [[ "$f" == "$meme" ]] && print_orange "    (obtain Franco-Zorrilla_et_al_2014.meme separately)"
        exit 1
    fi
done

# Chromosome naming consistency. Without this, a GFF3 using "1" against a
# FASTA using "Chr1" silently produces an empty gene BED — every downstream
# step appears to succeed but indexes nothing. Pipelines 03 and 08 already
# guard for this; scripts/02 was missing the check.
gff3_chr=$(awk -F'\t' '!/^#/ && NF>=9 {print $1; exit}' "$anno")
fasta_chr=$(grep '^>' "$genome" | head -1 | sed 's/^>//' | awk '{print $1}')
if [[ "$gff3_chr" != "$fasta_chr" ]]; then
    print_red "Chromosome name mismatch: GFF3 uses '$gff3_chr' but FASTA uses '$fasta_chr'."
    print_red "Please ensure consistent naming between the genome and the annotation."
    exit 1
fi

chmod a+x "$BIN_FIMO" "$BIN_PMET" scripts/third_party/gff3sort/gff3sort.pl

# ==================== Helpers ====================

# True if the given value looks affirmative (yes / y / Y / Yes / ...)
is_yes() {
    local v
    v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    [[ "$v" == "y" || "$v" == "yes" ]]
}

# True if the given overlap value means "remove overlaps"
is_no_overlap() {
    local v
    v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    [[ "$v" == "n" || "$v" == "no" || "$v" == "nooverlap" ]]
}

# ==================== [A] Shared prep (runs once) ====================

prepare_shared() {
    print_green "\n[A] Shared genome + motif prep..."
    local t=$SECONDS

    # 1. Sort GFF3 so that transcripts follow their parent genes
    scripts/third_party/gff3sort/gff3sort.pl "$anno" > "$shared_dir/sorted.gff3"

    # 2–4. Build gene BED via gff3_to_gene_bed.py (drops the per-step
    #      genelines.gff3 intermediate). The feature regex is selected by
    #      the `gene_features` config above.
    local feature_regex='gene$'
    [[ "$gene_features" == strict ]] && feature_regex='^gene$'
    python3 "$PY/gff3_to_gene_bed.py" \
        --gff3           "$shared_dir/sorted.gff3" \
        --out            "$shared_dir/genelines.bed" \
        --id-key         "$gff3id" \
        --feature-regex  "$feature_regex"

    # 5. Strip any FASTA line wrapping so bedtools getfasta can work
    awk '/^>/ { if (NR!=1) print ""; printf "%s\n",$0; next;} \
         { printf "%s",$0;} \
         END { print ""; }' "$genome" > "$shared_dir/genome_stripped.fa"

    # 6. Chromosome sizes for bedtools flank
    samtools faidx "$shared_dir/genome_stripped.fa"
    cut -f 1-2 "$shared_dir/genome_stripped.fa.fai" > "$shared_dir/bedgenome.genome"

    # 7. Distance to upstream gene (Python replacement for a pure-bash loop
    #    that was O(N) shell reads — ~40x slower)
    python3 "$PY/calculate_length_to_tss.py" \
        "$shared_dir/genelines.bed" \
        "$shared_dir/bedgenome.genome" \
        "$shared_dir/length_to_tss.txt"

    # 8. Split MEME file into per-thread batches (used by FIMO for every combo)
    mkdir -p "$shared_dir/memefiles"
    python3 "$PY/parse_memefile_batches.py" "$meme" "$shared_dir/memefiles/" "$threads"

    # 9. Information content per motif (reads combined MEME directly)
    python3 "$PY/calculateICfrommeme_IC_to_csv.py" "$meme" "$shared_dir/IC.txt"

    print_elapsed_time "$t"
}

# ==================== [B] Per-length prep ====================

# Writes $res_dir/LEN{plen}_FIMO{label}/ containing promoters.bed/fa/bg,
# promoter_lengths.txt, universe.txt. Idempotent: removes any stale dir first.
prepare_length() {
    local plen="$1"
    local out="$res_dir/LEN${plen}_FIMO${fimothresh_label}"
    rm -rf "$out"
    mkdir -p "$out"

    print_green "\n[B] Per-length prep: LEN=${plen}..."
    local t=$SECONDS

    # Single CLI replaces the previous 7-step inline pipeline. Behaviour-
    # preserving — verified byte-identical to the recorded 02 one-combo
    # baseline. The strand-aware getfasta and the assess_integrity / parse_utrs
    # invocations are now inside build_promoters.py.
    local overlap_arg=AllowOverlap; is_no_overlap "$overlap" && overlap_arg=NoOverlap
    local utr_arg=No; is_yes "$utr" && utr_arg=Yes
    python3 "$PY/build_promoters.py" \
        --gene-bed       "$shared_dir/genelines.bed"          \
        --genome-sizes   "$shared_dir/bedgenome.genome"       \
        --genome-fasta   "$shared_dir/genome_stripped.fa"     \
        --sorted-gff3    "$shared_dir/sorted.gff3"            \
        --length         "$plen"                              \
        --gap            0                                    \
        --overlap        "$overlap_arg"                       \
        --utr            "$utr_arg"                           \
        --out-bed        "$out/promoters.bed"                 \
        --out-fasta      "$out/promoters.fa"                  \
        --out-bg         "$out/promoters.bg"                  \
        --out-lengths    "$out/promoter_lengths.txt"          \
        --out-universe   "$out/universe.txt"

    print_elapsed_time "$t"
}

# ==================== [C] FIMO for one (length, maxk, topn) ====================

# Writes $res_dir/LEN{plen}_K{maxk}_N{topn}_FIMO{label}/{fimohits, binomial_thresholds.txt}
run_fimo_combo() {
    local plen="$1" maxk="$2" topn="$3"
    local length_dir="$res_dir/LEN${plen}_FIMO${fimothresh_label}"
    local out="$res_dir/LEN${plen}_K${maxk}_N${topn}_FIMO${fimothresh_label}"
    rm -rf "$out"
    mkdir -p "$out/fimohits"

    # Run one FIMO per motif batch in parallel; each batch has a non-overlapping
    # slice of motifs so they write distinct files in fimohits/.
    # Command must be a single string for GNU parallel; {} is its own placeholder.
    find "$shared_dir/memefiles" -name '*.txt' | \
        parallel --jobs="$threads" \
            "$BIN_FIMO --topk $maxk --topn $topn --text --no-qvalue --thresh $fimothresh --verbosity 1 --oc $out/fimohits --bgfile $length_dir/promoters.bg {} $length_dir/promoters.fa $length_dir/promoter_lengths.txt"

    # FIMO writes binomial_thresholds.txt into fimohits/; pairing_parallel expects it one level up.
    # Parallel FIMO batches race to write this file; the row order is therefore
    # nondeterministic across runs. Sort by motif to make the file content
    # byte-stable (downstream binaries do not depend on row order).
    if [[ -f "$out/fimohits/binomial_thresholds.txt" ]]; then
        sort -o "$out/fimohits/binomial_thresholds.txt" "$out/fimohits/binomial_thresholds.txt"
        mv "$out/fimohits/binomial_thresholds.txt" "$out/binomial_thresholds.txt"
    fi
}

# ==================== [D] Heterotypic for one (task, length, maxk, topn) ====================

# Writes $heterotypic_output/{task}_LEN..._K..._N..._FIMO.../motif_output.txt
run_heterotypic_pass() {
    local task="$1" plen="$2" maxk="$3" topn="$4"
    local length_dir="$res_dir/LEN${plen}_FIMO${fimothresh_label}"
    local combo_dir="$res_dir/LEN${plen}_K${maxk}_N${topn}_FIMO${fimothresh_label}"
    local tag="${task}_LEN${plen}_K${maxk}_N${topn}_FIMO${fimothresh_label}"
    local out="$heterotypic_output/$tag"
    local log="$logDir/$tag.log"
    local gene_file="data/genes/${task}.txt"

    mkdir -p "$out"

    # Restrict the task's gene list to genes that survived the index universe
    grep -Ff "$length_dir/universe.txt" "$gene_file" > "$out/available_genes.txt"

    "$BIN_PMET" \
        -d .                                   \
        -g "$out/available_genes.txt"          \
        -i "$icthresh"                         \
        -p "$length_dir/promoter_lengths.txt"  \
        -b "$combo_dir/binomial_thresholds.txt" \
        -c "$shared_dir/IC.txt"                \
        -f "$combo_dir/fimohits"               \
        -o "$out"                              \
        -t "$threads" > "$log" 2>&1

    rm -f "$out/available_genes.txt"
    # Idempotent aggregate. On a re-run an old motif_output.txt would
    # otherwise be picked up by the *.txt glob (and self-amplify after a
    # mktemp staging step). Remove it first, then aggregate via temp.
    rm -f "$out/motif_output.txt"
    local concat_tmp
    concat_tmp=$(mktemp)
    cat "$out"/*.txt > "$concat_tmp"
    rm -f "$out"/temp*.txt
    mv "$concat_tmp" "$out/motif_output.txt"
}

# ==================== Main ====================

grand_start=$SECONDS

prepare_shared

total=$(( ${#tasks[@]} * ${#promlength_values[@]} * ${#maxk_values[@]} * ${#topn_values[@]} ))
i=0

for plen in "${promlength_values[@]}"; do
    prepare_length "$plen"

    for k in "${maxk_values[@]}"; do
        for n in "${topn_values[@]}"; do
            print_green "\n[C] FIMO: LEN=${plen} K=${k} N=${n}"
            local_start=$SECONDS
            run_fimo_combo "$plen" "$k" "$n"
            print_elapsed_time "$local_start"

            for task in "${tasks[@]}"; do
                i=$((i + 1))
                print_fluorescent_yellow "    [$i/$total] heterotypic  task=${task}  LEN=${plen} K=${k} N=${n}"
                run_heterotypic_pass "$task" "$plen" "$k" "$n"
            done

            # Free per-combo FIMO output once all tasks consumed it
            if [[ "$keep_intermediate" != true ]]; then
                rm -rf "$res_dir/LEN${plen}_K${k}_N${n}_FIMO${fimothresh_label}"
            fi
        done
    done

    # Free per-length prep after all its combos are done
    if [[ "$keep_intermediate" != true ]]; then
        rm -rf "$res_dir/LEN${plen}_FIMO${fimothresh_label}"
    fi
done

# Free shared prep at the very end
if [[ "$keep_intermediate" != true ]]; then
    rm -rf "$shared_dir"
fi

print_green "\nDone."
print_elapsed_time "$grand_start"
