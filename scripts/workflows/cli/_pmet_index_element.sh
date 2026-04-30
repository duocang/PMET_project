#!/bin/bash
set -e

# Build a PMET homotypic index on a chosen genomic element
# (mRNA / exon / CDS / three_prime_UTR / five_prime_UTR) using one of two
# isoform-aggregation strategies:
#
#   -s longest : per gene, pick the single isoform whose total element length
#                is greatest and keep every fragment of that isoform.
#                When -e mRNA -m No, additionally subtract the chosen
#                isoform's UTRs from the mRNA span to yield CDS-spanning
#                fragments.
#
#   -s merged  : per gene, take the union of all isoforms' element intervals
#                (overlapping intervals merged into a single non-redundant
#                set). No isoform specificity, no UTR subtraction.

usage () {
    cat >&2 <<EOF
USAGE: _pmet_index_element.sh -s <longest|merged> [options] <genome.fa> <annot.gff3> <motifs.meme>

Required:
  -r <dir>   Pipeline root holding {python,r,third_party/gff3sort}/...
  -i <key>   GFF3 attribute key holding the transcript id, e.g. 'ID=transcript:'
             for mRNA, 'Parent=transcript:' for exon/CDS/UTR.
  -o <dir>   Output directory.
  -s <str>   Isoform-aggregation strategy: longest or merged.

Optional:
  -e <str>   Element type to index (matches GFF3 column 3). Default: mRNA.
  -m <Y|N>   Only for -s longest -e mRNA: keep full mRNA (Yes) or subtract
             the chosen isoform's UTRs (No). Default: No. Ignored for merged.
  -n <int>   FIMO --topn (top hits per motif).       Default: 5000
  -k <int>   FIMO --topk (max hits per sequence).    Default: 5
  -f <num>   FIMO p-value threshold.                 Default: 0.05
  -t <int>   Parallel jobs.                          Default: 4
  -d <Y|N>   Delete intermediate files on success.   Default: yes

(-v, -u, -p are accepted for compatibility but unused here.)
EOF
}

print_red()              { printf '\033[0;31m%s\033[0m\n' "$1"; }
print_green()            { printf '\033[0;32m%s\033[0m\n' "$1"; }
print_orange()           { printf '\033[0;33m%s\033[0m\n' "$1"; }
print_fluorescent_yellow(){ printf '\033[1;33m%s\033[0m\n' "$1"; }
print_white()            { printf '\033[1;37m%s\033[0m'   "$1"; }


# Defaults.
strategy=
topn=5000
maxk=5
promlength=1000
fimothresh=0.05
element=mRNA
mrnaFull=No
delete=yes
overlap="AllowOverlap"
utr="No"
gff3id='transcript:'
pmetroot="scripts"
buildDir="build"
threads=4

indexingOutputDir=
genomefile=
gff3file=
memefile=

if [ $# -eq 0 ]; then
    echo "No arguments supplied" >&2
    usage
    exit 1
fi

while getopts ":r:i:o:s:n:k:p:f:v:u:e:m:t:d:" options; do
    case $options in
        r) pmetroot=$OPTARG;;
        i) gff3id=$OPTARG;;
        o) indexingOutputDir=$OPTARG;;
        s) strategy=$OPTARG;;
        n) topn=$OPTARG;;
        k) maxk=$OPTARG;;
        p) promlength=$OPTARG;;
        f) fimothresh=$OPTARG;;
        v) overlap=$OPTARG;;
        u) utr=$OPTARG;;
        e) element=$OPTARG;;
        m) mrnaFull=$OPTARG;;
        t) threads=$OPTARG;;
        d) delete=$OPTARG;;
        \?) print_red "Invalid option: -$OPTARG" >&2; exit 1;;
        :)  print_red "Option -$OPTARG requires an argument." >&2; exit 1;;
    esac
done
shift $((OPTIND - 1))
genomefile=$1
gff3file=$2
memefile=$3
universefile=$indexingOutputDir/universe.txt
bedfile=$indexingOutputDir/${element}.bed

case $strategy in
    longest|merged) ;;
    "") print_red "Missing required option: -s <longest|merged>"; usage; exit 1;;
    *)  print_red "Invalid -s: '$strategy' (must be longest or merged)"; exit 1;;
esac

print_white "Genome file                  : "; print_orange "$genomefile"
print_white "Annotation file              : "; print_orange "$gff3file"
print_white "Motif meme file              : "; print_orange "$memefile"
print_white "PMET script root             : "; print_orange "$pmetroot"
print_white "GFF3 attribute key           : "; print_orange "$gff3id"
print_white "Isoform strategy             : "; print_orange "$strategy"
print_white "Genomic element              : "; print_orange "$element"
if [ "$strategy" = "longest" ]; then
    print_white "mRNA keeps UTRs              : "; print_orange "$mrnaFull"
fi
print_white "Output directory             : "; print_orange "$indexingOutputDir"
print_white "FIMO --topn / --topk         : "; print_orange "$topn / $maxk"
print_white "FIMO threshold               : "; print_orange "$fimothresh"
print_white "Threads                      : "; print_orange "$threads"

mkdir -p "$indexingOutputDir"
start=$SECONDS
print_green "Preparing data for FIMO and PMET index..."


# -------------------------------------------------------------------------------------------
# 0. Preflight: chromosome naming consistency check.
#    GFF3 may use '1' while FASTA uses 'Chr1' (or vice versa), causing bedtools
#    to silently produce empty output. Fail fast before any heavy processing.
print_fluorescent_yellow "     0. Checking chromosome naming consistency"
gff3_chrom=$(awk -F'\t' '/^[^#]/ && NF>=8 { print $1; exit }' "$gff3file")
fasta_chrom=$(awk '/^>/ { sub(/^>/, ""); sub(/ .*/, ""); print; exit }' "$genomefile")
if [ "$gff3_chrom" != "$fasta_chrom" ]; then
    print_red "Chromosome naming mismatch!"
    print_red "  GFF3 first data chromosome : $gff3_chrom"
    print_red "  FASTA first header         : $fasta_chrom"
    print_red "Ensure both files use the same naming convention."
    exit 1
fi
print_green "  GFF3='$gff3_chrom'  FASTA='$fasta_chrom'  OK"


# -------------------------------------------------------------------------------------------
# 1. Parse GFF3 into a BED table in a single pass (common).
#    Output columns: chrom, start(0-based), end, transcript_id, 1, strand.
#    GFF3 is 1-based closed; BED is 0-based half-open: BED_start = GFF3_start - 1.
#    Filters: feature type == $element, start < end, attribute key present.
print_fluorescent_yellow "     1. Extracting ${element} rows from GFF3 (${element}.bed)"
awk -F'\t' -v OFS='\t' -v elem="$element" -v key="$gff3id" '
    /^#/ { next }
    $3 == elem && $4 < $5 {
        n = split($9, attrs, ";")
        for (i = 1; i <= n; i++) {
            if (substr(attrs[i], 1, length(key)) == key) {
                print $1, $4-1, $5, substr(attrs[i], length(key)+1), 1, $7
                next
            }
        }
    }
' "$gff3file" > "$bedfile"

if [ ! -s "$bedfile" ]; then
    print_red "No ${element} rows extracted. Check -i '${gff3id}' against the GFF3 attribute format."
    exit 1
fi


# -------------------------------------------------------------------------------------------
# 2. Isoform-aggregation strategy. Both branches leave $bedfile holding
#    gene-id-labelled rows (column 4), possibly multiple per gene.
if [ "$strategy" = "longest" ]; then

    # 2a. Per gene, pick the transcript with the greatest total element length.
    #     For multi-fragment elements (exon/CDS/UTR) we must sum per transcript
    #     BEFORE comparing across isoforms, otherwise we would keep only the
    #     single longest fragment.
    print_fluorescent_yellow "     2a. Selecting longest isoform per gene (by total ${element} length)"
    awk -F'\t' '
    {
        tid = $4
        gid = tid; sub(/\..*/, "", gid)
        sum[tid] += $3 - $2
        gene[tid] = gid
    }
    END {
        for (t in sum) {
            g = gene[t]
            if (!(g in bestSum) || sum[t] > bestSum[g]) {
                bestSum[g] = sum[t]; bestTid[g] = t
            }
        }
        for (g in bestTid) print bestTid[g]
    }' "$bedfile" > "$indexingOutputDir/chosen_transcripts.txt"

    # 2b. Keep every row of a chosen transcript, relabel column 4 with the gene
    #     id. For mRNA this is one row per gene; for sub-elements it is all
    #     fragments of the chosen isoform.
    print_fluorescent_yellow "     2b. Retaining fragments of chosen isoforms"
    awk -F'\t' -v OFS='\t' '
        NR==FNR { chosen[$1] = 1; next }
        ($4 in chosen) {
            gid = $4; sub(/\..*/, "", gid); $4 = gid
            print
        }
    ' "$indexingOutputDir/chosen_transcripts.txt" "$bedfile" \
        | sort -k4,4 -k2,2n > "$bedfile.tmp"
    mv "$bedfile.tmp" "$bedfile"

    # 2c. (mRNA + mrnaFull=No only) Subtract the SAME chosen transcripts'
    #     UTRs from the mRNA intervals — using chosen_transcripts.txt
    #     guarantees we only remove UTRs belonging to the kept isoform.
    if [ "$element" = "mRNA" ] && [ "$mrnaFull" = "No" ]; then
        print_fluorescent_yellow "     2c. Subtracting chosen isoforms' UTRs from mRNA intervals"
        for item in three_prime_UTR five_prime_UTR; do
            awk -F'\t' -v OFS='\t' -v elem="$item" -v key="Parent=transcript:" '
                /^#/ { next }
                $3 == elem && $4 < $5 {
                    n = split($9, attrs, ";")
                    for (i = 1; i <= n; i++) {
                        if (substr(attrs[i], 1, length(key)) == key) {
                            print $1, $4-1, $5, substr(attrs[i], length(key)+1), 1, $7
                            next
                        }
                    }
                }
            ' "$gff3file" \
            | awk -F'\t' -v OFS='\t' '
                NR==FNR { chosen[$1] = 1; next }
                ($4 in chosen) { gid = $4; sub(/\..*/, "", gid); $4 = gid; print }
            ' "$indexingOutputDir/chosen_transcripts.txt" - \
            > "$indexingOutputDir/${item}.bed"
        done

        cp "$bedfile" "$indexingOutputDir/with_overlapping.bed"
        bedtools subtract -a "$bedfile"                   -b "$indexingOutputDir/three_prime_UTR.bed" > "$indexingOutputDir/tmp.bed"
        bedtools subtract -a "$indexingOutputDir/tmp.bed" -b "$indexingOutputDir/five_prime_UTR.bed"  > "$bedfile.tmp"
        rm -f "$indexingOutputDir/tmp.bed"
        mv "$bedfile.tmp" "$bedfile"
    fi

    rm -f "$indexingOutputDir/chosen_transcripts.txt"

else
    # Strategy: merged. Drop the .N transcript suffix so all isoforms of a gene
    # share a key, sort by gene + chrom + start, then sweep once emitting one
    # row per maximal contiguous run. Book-ended intervals (end == next.start)
    # are merged — they describe the same continuous stretch of physical DNA
    # split into two annotation rows by alternative splicing or annotation
    # convention; a TF binding site that spans the boundary should still be
    # detected. Matches `bedtools merge` default semantics.
    print_fluorescent_yellow "     2. Merging overlapping + book-ended intervals within each gene (union across isoforms)"
    awk -F'\t' -v OFS='\t' '{ sub(/\..*/, "", $4); print }' "$bedfile" \
        | sort -k4,4 -k1,1 -k2,2n \
        | awk -F'\t' -v OFS='\t' '
            function flush() { if (g != "") print chrom, s, e, g, ".", strand }
            {
                if ($4 != g || $1 != chrom || $2 > e) {
                    flush()
                    chrom = $1; s = $2; e = $3; g = $4; strand = $6
                } else if ($3 > e) {
                    e = $3
                }
            }
            END { flush() }
        ' > "$bedfile.tmp"
    mv "$bedfile.tmp" "$bedfile"
fi


# -------------------------------------------------------------------------------------------
# 3. Tag multi-interval genes with __GENE__N so FIMO treats each interval as
#    a distinct sequence; drop intervals <30bp (below typical TF motif widths
#    and too short to stabilise a local background). Idempotent when every
#    gene has a single row.
print_fluorescent_yellow "     3. Tagging fragments (__GENE__N) and dropping <30bp"
awk -F'\t' -v OFS='\t' '
    { n = ++seen[$4]; if (n > 1) $4 = "__" $4 "__" n; print }
' "$bedfile" \
    | awk -F'\t' '$3 - $2 >= 30' \
    | sort -k4,4 > "$bedfile.tmp"
mv "$bedfile.tmp" "$bedfile"


# -------------------------------------------------------------------------------------------
# 4. universe.txt — unique gene ids (strip the __N fragment suffix).
#    promoter_lengths.txt — length keyed by the FIMO sequence id (per interval),
#    because FIMO's --topn is a per-sequence budget.
print_fluorescent_yellow "     4. Writing universe.txt and promoter_lengths.txt"
awk -F'\t' '{ id = $4; sub(/^__/, "", id); sub(/__[0-9]+$/, "", id); print id }' \
    "$bedfile" | sort -u > "$universefile"
awk -F'\t' -v OFS='\t' '{ print $4, $3 - $2 }' "$bedfile" > "$indexingOutputDir/promoter_lengths.txt"


# -------------------------------------------------------------------------------------------
# 5. Unwrap multi-line FASTA, then extract sequences with strand awareness.
#    bedtools -s reverse-complements negative-strand intervals.
#    bedtools -name + -s appends "(+)" or "(-)" and "::chrom:start-end" to the
#    header; strip both for clean FIMO input.
print_fluorescent_yellow "     5. Extracting sequences (promoter.fa)"
awk '/^>/ { if (NR != 1) print ""; print; next } { printf "%s", $0 } END { print "" }' \
    "$genomefile" > "$indexingOutputDir/genome_stripped.fa"

bedtools getfasta \
    -fi  "$indexingOutputDir/genome_stripped.fa" \
    -bed "$bedfile" \
    -name \
    -s \
    | sed -e 's/([+-])::.*//' -e 's/::.*//' > "$indexingOutputDir/promoter.fa"

dup_ids=$(grep '^>' "$indexingOutputDir/promoter.fa" | sort | uniq -d)
if [ -n "$dup_ids" ]; then
    print_red "Duplicate FASTA ids detected; __N tagging likely failed:"
    echo "$dup_ids" | head
fi


# -------------------------------------------------------------------------------------------
# 6. Zero-order Markov background from the promoter set itself, so FIMO
#    P-values are calibrated against the local composition of the scanned
#    sequences.
print_fluorescent_yellow "     6. Estimating Markov background (promoter.bg)"
fasta-get-markov "$indexingOutputDir/promoter.fa" > "$indexingOutputDir/promoter.bg"


# -------------------------------------------------------------------------------------------
# 7. IC per motif (reads combined MEME directly; rows in deterministic
#    MEME-file order, motif IDs upper-cased so they line up with what
#    index_fimo_fused writes into binomial_thresholds.txt at step 8).
print_fluorescent_yellow "     7. Computing information content (IC.txt)"
python3 "$pmetroot/python/calculateICfrommeme_IC_to_csv.py" \
    "$memefile" \
    "$indexingOutputDir/IC.txt"


# -------------------------------------------------------------------------------------------
# 8. Run FIMO + PMET indexing as a single fused step.
#    Replaces the previous two-step flow (split MEME into batches ->
#    GNU parallel + per-batch fimo --topn/--topk -> separate pmet indexer)
#    that depended on PMET-patched fimo flags absent from upstream MEME.
#    index_fimo_fused has internal OpenMP motif batching + writes
#    binomial_thresholds.txt at $indexingOutputDir and per-motif binary
#    fimohits/*.bin (PMETBN01 format). Same call shape as
#    scripts/workflows/{intervals,promoter}.sh.
nummotifs=$(grep -c '^MOTIF' "$memefile")
print_fluorescent_yellow "     8. Running FIMO + PMETindex (${nummotifs} motifs, ${threads} thread(s))"
mkdir -p "$indexingOutputDir/fimohits"

BIN_INDEX="$buildDir/index_fimo_fused"
[ -x "$BIN_INDEX" ] || { print_red "Binary not found or not executable: $BIN_INDEX"; exit 1; }

OMP_NUM_THREADS="$threads" \
"$BIN_INDEX"                                  \
    --no-qvalue                               \
    --text                                    \
    --thresh "$fimothresh"                    \
    --verbosity 1                             \
    --bgfile "$indexingOutputDir/promoter.bg" \
    --topn "$topn"                            \
    --topk "$maxk"                            \
    --oc "$indexingOutputDir"                 \
    "$memefile"                               \
    "$indexingOutputDir/promoter.fa"          \
    "$indexingOutputDir/promoter_lengths.txt"


# -------------------------------------------------------------------------------------------
# 9. Collapse per-interval results back to gene level:
#    - promoter_lengths: sum interval lengths per gene (text, awk).
#    - fimohits/*.bin: strip __GENE__N -> GENE in the sequence name pool,
#      group by gene, keep top $maxk hits per gene by ascending p-value,
#      filter against the motif's binomial threshold. Done in Python because
#      index_fimo_fused emits PMETBN01 binary that needs proper parsing
#      (length-prefixed records, name-pool offsets) — sed/awk on bytes
#      would corrupt the file.
#    Idempotent when each gene has a single interval.
print_fluorescent_yellow "     9. Collapsing per-interval results back to gene level"
awk -F'\t' '{
    sub(/^__/, "", $1); sub(/__[0-9]+$/, "", $1)
    sum[$1] += $2
}
END { for (g in sum) print g "\t" sum[g] }' \
    "$indexingOutputDir/promoter_lengths.txt" \
    > "$indexingOutputDir/promoter_lengths.tmp"
mv "$indexingOutputDir/promoter_lengths.tmp" "$indexingOutputDir/promoter_lengths.txt"

python3 "$pmetroot/python/collapse_element_fimohits.py" \
    "$indexingOutputDir" "$maxk"


# -------------------------------------------------------------------------------------------
# Cleanup of intermediates (outputs consumed downstream are kept).
if [[ $delete == [Yy]* ]]; then
    print_green "Deleting intermediate files..."
    rm -rf "$bedfile" \
           "$indexingOutputDir/five_prime_UTR.bed" \
           "$indexingOutputDir/three_prime_UTR.bed" \
           "$indexingOutputDir/with_overlapping.bed" \
           "$indexingOutputDir/genome_stripped.fa" \
           "$indexingOutputDir/genome_stripped.fa.fai" \
           "$indexingOutputDir/promoter.bg" \
           "$indexingOutputDir/promoter.fa"
fi


# -------------------------------------------------------------------------------------------
# Sanity check: one fimohits file per motif (binary now after step 8 ->
# index_fimo_fused). A motif may be absent from fimohits/ if it produced
# zero hits at the chosen FIMO threshold; check_homotypic_contract.py
# treats that as a soft failure with a clear message rather than a count
# mismatch here.
file_count=$(find "$indexingOutputDir/fimohits" -maxdepth 1 -type f -name '*.bin' | wc -l)
if [ "$file_count" -eq "$nummotifs" ]; then
    python3 "$pmetroot/python/check_homotypic_contract.py" "$indexingOutputDir" \
        || { print_red "Homotypic contract violated; see stderr above"; exit 1; }
    elapsed=$((SECONDS - start))
    printf -v hms '%dd %dh %dm %ds' \
        $((elapsed/86400)) $(((elapsed%86400)/3600)) $(((elapsed%3600)/60)) $((elapsed%60))
    print_orange "      Time taken: $hms"
    print_green "DONE: homotypic search"
else
    print_red "Error: $file_count fimohits files, expected $nummotifs (some motifs may have zero hits at threshold $fimothresh)."
    exit 1
fi
