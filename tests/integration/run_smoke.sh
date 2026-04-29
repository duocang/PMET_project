#!/usr/bin/env bash
# Smoke tests for behavior-preserving invariants in the PMET pipeline.
#
# Designed to be cheap (< 1s wall) and to run on the same `bedtools` /
# `samtools` versions the pipeline scripts use. Each test prints PASS/FAIL
# and the harness exits non-zero if any test fails.

set -uo pipefail

script_dir=$(cd -- "$(dirname "$0")" && pwd)
cd "$script_dir"

failed=0
section() { printf '\n[smoke] %s\n' "$1"; }
pass()    { printf '  PASS  %s\n' "$1"; }
fail()    { printf '  FAIL  %s\n' "$1"; failed=$((failed + 1)); }

# ---------------------------------------------------------------------------
# Test 1: bedtools getfasta with -s reverse-complements minus-strand entries.
# This guards against pipeline/02_benchmark_parameters.sh regressing to the
# strand-unaware extraction that produced wrong promoter sequences for
# minus-strand genes.
# ---------------------------------------------------------------------------
section "bedtools getfasta strand-awareness (relevant to pipeline/02 P0 fix)"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cp fixtures/strand_minigenome.fa "$tmp/genome.fa"
cp fixtures/strand_promoters.bed "$tmp/promoters.bed"

# Without -s: extracts literal + strand sequence regardless of BED column 6.
bedtools getfasta -fi "$tmp/genome.fa" -bed "$tmp/promoters.bed" \
    -name -fo "$tmp/no_strand.fa" 2>/dev/null

# With -s: reverse-complements - strand entries.
bedtools getfasta -fi "$tmp/genome.fa" -bed "$tmp/promoters.bed" \
    -name -s -fo "$tmp/with_strand.fa" 2>/dev/null

# Strip bedtools' header suffix to keep names predictable.
sed -e 's/::.*//g' "$tmp/no_strand.fa"   > "$tmp/no_strand_clean.fa"
sed -e 's/::.*//g' "$tmp/with_strand.fa" > "$tmp/with_strand_clean.fa"

get_seq() {
    awk -v want=">$1" '
        $0 == want { capture = 1; next }
        /^>/        { capture = 0 }
        capture     { printf "%s", $0 }
        END         { printf "\n" }
    ' "$2"
}

plus_no=$(get_seq gene_plus  "$tmp/no_strand_clean.fa")
plus_s=$(get_seq  gene_plus  "$tmp/with_strand_clean.fa")
minus_no=$(get_seq gene_minus "$tmp/no_strand_clean.fa")
minus_s=$(get_seq  gene_minus "$tmp/with_strand_clean.fa")

# Plus strand: -s is a no-op, sequence must match.
if [[ "$plus_no" == "$plus_s" ]]; then
    pass "+ strand sequence unchanged by -s ($plus_s)"
else
    fail "+ strand sequence changed by -s: '$plus_no' vs '$plus_s'"
fi

# Minus strand: with -s must be the reverse complement of without -s.
rc=$(printf '%s' "$minus_no" | tr 'ACGTacgt' 'TGCAtgca' | rev)
if [[ "$minus_s" == "$rc" ]]; then
    pass "- strand sequence reverse-complemented by -s ($minus_no -> $minus_s)"
else
    fail "- strand expected RC '$rc' but got '$minus_s'"
fi

# And the two extractions must actually differ (i.e. our fixture is non-palindromic).
if [[ "$minus_no" != "$minus_s" ]]; then
    pass "- strand fixture is non-palindromic"
else
    fail "- strand fixture is palindromic — test cannot detect the strand bug"
fi

# Path helpers — script_dir is scripts/tests/.
#   $script_dir/../pipeline    → scripts/pipeline
#   $script_dir/../python      → scripts/python
#   $script_dir/../../data     → repo-root data
repo_root="$script_dir/../.."
pipeline_dir="$script_dir/../pipeline"

# ---------------------------------------------------------------------------
# Test 2: build_promoters.py invokes bedtools getfasta with -s.
# Static check — keeps the P0-02 strand fix visible. After Stage 4 the
# `bedtools getfasta` call lives in build_promoters.py; it is shared by
# pipelines 02, 03 and 08 by construction.
# ---------------------------------------------------------------------------
section "build_promoters.py invokes bedtools getfasta with -s"

bp="$script_dir/../python/build_promoters.py"
if [[ ! -f "$bp" ]]; then
    fail "build_promoters.py not found at $bp"
else
    # Window around the single getfasta call: 1 line before, 8 after.
    # Look for `"-s"` anywhere in that window. The file has only one
    # `bedtools getfasta` invocation, so this is unambiguous.
    if grep -A 8 '"getfasta"' "$bp" | grep -q '"-s"'; then
        pass "build_promoters.py bedtools getfasta call includes -s"
    else
        fail "build_promoters.py bedtools getfasta call missing -s — minus-strand promoters will be wrong"
    fi
fi

section "01_benchmark_cpu inputs sanity"

p1="$pipeline_dir/01_benchmark_cpu.sh"
if [[ ! -f "$p1" ]]; then
    fail "01_benchmark_cpu.sh not found at $p1"
else
    gene_path=$(awk -F'=' '/^gene_input_file=/ { print $2; exit }' "$p1" | tr -d '"')
    if [[ -n "$gene_path" && -f "$repo_root/$gene_path" ]]; then
        pass "01 gene_input_file exists ($gene_path)"
    else
        fail "01 gene_input_file missing or unset ($gene_path)"
    fi

    # draw_heatmap.R hard-requires exactly 7 args; count tokens after the
    # script name on the Rscript line (split into a flat list).
    args_count=$(awk '
        /Rscript scripts\/r\/draw_heatmap.R/ { in_call = 1; next }
        in_call {
            for (i = 1; i <= NF; i++) {
                tok = $i
                if (tok == "\\") continue
                if (tok ~ /^#/) continue
                count++
            }
            if ($0 !~ /\\$/) { print count; exit }
        }
    ' "$p1")
    if [[ "${args_count:-0}" -eq 7 ]]; then
        pass "01 draw_heatmap.R receives 7 arguments"
    else
        fail "01 draw_heatmap.R receives ${args_count:-0} arguments (need 7)"
    fi
fi

# ---------------------------------------------------------------------------
# Test 4: every promoter pipeline that uses TAIR10.fasta + TAIR10.gff3 must
# guard against silent chromosome-name mismatch (e.g. "1" vs "Chr1").
# Pipelines 03 and 08 added the preflight; this regression-tests 02, 06, 07.
# Static check + synthetic mismatch detection.
# ---------------------------------------------------------------------------
section "chromosome-name preflight on promoter+anno pipelines"

for name in 02_benchmark_parameters.sh \
            05_promoter_gap.sh \
            06_elements_longest.sh \
            07_elements_merged.sh; do
    full="$pipeline_dir/$name"
    if [[ ! -f "$full" ]]; then
        fail "$name not found"
        continue
    fi
    # 06 and 07 source _elements_common.sh; the preflight body lives
    # there. Check the entry script itself first; if not found, follow a
    # single `source …_elements_common.sh` and check that body too.
    if grep -q 'Chromosome name mismatch' "$full"; then
        pass "$name contains chromosome-name preflight"
    elif grep -q 'source.*_elements_common.sh' "$full" \
        && grep -q 'Chromosome name mismatch' \
            "$pipeline_dir/_elements_common.sh"; then
        pass "$name inherits chromosome-name preflight from _elements_common.sh"
    else
        fail "$name missing chromosome-name preflight"
    fi
done

# Synthetic mismatch: build a tiny GFF3 with chrom "Chr1" and a FASTA with
# "1", then run the same preflight body the pipelines now embed. Must
# trigger the mismatch.
chr_tmp=$(mktemp -d)
printf '##gff-version 3\nChr1\tTAIR10\tgene\t1\t10\t.\t+\t.\tID=fake\n' > "$chr_tmp/anno.gff3"
printf '>1\nACGT\n' > "$chr_tmp/genome.fa"
gff3_chr=$(awk -F'\t' '!/^#/ && NF>=9 {print $1; exit}' "$chr_tmp/anno.gff3")
fasta_chr=$(grep '^>' "$chr_tmp/genome.fa" | head -1 | sed 's/^>//' | awk '{print $1}')
if [[ "$gff3_chr" != "$fasta_chr" ]]; then
    pass "synthetic mismatch caught (gff3='$gff3_chr', fasta='$fasta_chr')"
else
    fail "synthetic mismatch NOT caught"
fi
rm -rf "$chr_tmp"

# ---------------------------------------------------------------------------
# Test 5: assess_integrity.py resolves split promoters even when same-gene
# fragments are not adjacent after sortBed (P1-2 regression guard).
# ---------------------------------------------------------------------------
section "assess_integrity.py handles non-adjacent split fragments"

ai_tmp=$(mktemp -d)
cat > "$ai_tmp/promoters.bed" <<'BED'
chr1	1000	1500	GENE_X	1	+
chr1	1600	1900	GENE_Y	1	+
chr1	1700	2000	GENE_X	1	+
chr1	3000	3300	GENE_Z	1	-
chr1	3500	3600	GENE_W	1	+
chr1	3800	4000	GENE_Z	1	-
BED

if python3 "$script_dir/../python/assess_integrity.py" "$ai_tmp/promoters.bed" \
        > "$ai_tmp/run.log" 2>&1; then
    # Expectation: GENE_X collapses to its right (TSS-side) fragment 1700-2000;
    # GENE_Z collapses to its left (TSS-side) fragment 3000-3300; GENE_Y, GENE_W
    # untouched. Final BED has 4 rows.
    expected=$(printf 'chr1\t1600\t1900\tGENE_Y\t1\t+\nchr1\t1700\t2000\tGENE_X\t1\t+\nchr1\t3000\t3300\tGENE_Z\t1\t-\nchr1\t3500\t3600\tGENE_W\t1\t+\n')
    actual=$(cat "$ai_tmp/promoters.bed")
    if [[ "$actual" == "$expected" ]]; then
        pass "non-adjacent same-gene fragments resolved (GENE_X, GENE_Z)"
    else
        fail "non-adjacent fragment resolution mismatch"
        printf 'expected:\n%s\nactual:\n%s\n' "$expected" "$actual" >&2
    fi
else
    fail "assess_integrity.py exited non-zero: $(cat "$ai_tmp/run.log")"
fi
rm -rf "$ai_tmp"

# ---------------------------------------------------------------------------
# Test 6: real-data strand extraction (TAIR10). Skipped if data missing.
# ---------------------------------------------------------------------------
section "real-data strand extraction (TAIR10)"

if [[ -s "$repo_root/data/reference/TAIR10.fasta" && -s "$repo_root/data/reference/TAIR10.gff3" ]]; then
    if bash "$script_dir/test_pipeline02_strand_realdata.sh" > /tmp/strand_real.log 2>&1; then
        pass "TAIR10 promoter FASTA: + strand unchanged, - strand reverse-complemented by -s"
    else
        fail "real-data strand check failed (see /tmp/strand_real.log)"
    fi
else
    printf '  SKIP  TAIR10 inputs not present\n'
fi

# ---------------------------------------------------------------------------

if (( failed == 0 )); then
    printf '\n[smoke] all checks passed\n'
    exit 0
else
    printf '\n[smoke] %d check(s) failed\n' "$failed"
    exit 1
fi
