#!/usr/bin/env bash
# Real-data verification of 02_benchmark_parameters's strand fix.
#
# Reproduces the promoter FASTA extraction that 02_benchmark_parameters
# performs (bedtools flank + getfasta) using the project's TAIR10 inputs,
# runs it both with and without `-s`, and checks that:
#
#   - + strand promoter sequences are identical with and without `-s`
#   - - strand promoter sequences differ, and the with-`-s` sequence is
#     the reverse complement of the without-`-s` sequence
#
# This is the real-data evidence behind the P0-02 fix. It runs in a few
# seconds and does not invoke FIMO or pmet, so it is cheap enough to run
# every time a baseline is captured.

set -uo pipefail

repo_root=$(cd -- "$(dirname "$0")/../../.." && pwd)
cd "$repo_root"

genome=data/reference/TAIR10.fasta
anno=data/reference/TAIR10.gff3
length=200

if [[ ! -s "$genome" || ! -s "$anno" ]]; then
    echo "[strand-real] missing TAIR10 inputs; skipping" >&2
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

scripts/third_party/gff3sort/gff3sort.pl "$anno" > "$work/sorted.gff3" 2>/dev/null

python3 scripts/python/gff3_to_gene_bed.py \
    --gff3           "$work/sorted.gff3" \
    --out            "$work/genelines.bed" \
    --id-key         "gene_id=" \
    --feature-regex  '^gene$' >/dev/null

# Linearise FASTA + faidx so bedtools getfasta can run.
awk '/^>/ { if (NR!=1) print ""; printf "%s\n",$0; next }
     { printf "%s",$0 } END { print "" }' "$genome" > "$work/genome.fa"
samtools faidx "$work/genome.fa"
cut -f 1-2 "$work/genome.fa.fai" > "$work/bedgenome.genome"

# Strand-aware flank: -s ensures upstream is taken on the correct strand.
bedtools flank -l "$length" -r 0 -s \
    -i "$work/genelines.bed" -g "$work/bedgenome.genome" \
    > "$work/promoters_unsorted.bed"
sortBed -i "$work/promoters_unsorted.bed" > "$work/promoters.bed"

# Two extractions: pre-fix style (literal +-strand) and post-fix style (-s).
bedtools getfasta -fi "$work/genome.fa" -bed "$work/promoters.bed" \
    -name -fo "$work/prefix_no_s.fa" 2>/dev/null
bedtools getfasta -fi "$work/genome.fa" -bed "$work/promoters.bed" \
    -name -s -fo "$work/postfix_with_s.fa" 2>/dev/null

# Strip header decorations so gene names match across the two files.
sed -e 's/::.*//g' -e 's/([+-])$//g' "$work/prefix_no_s.fa"   > "$work/prefix_clean.fa"
sed -e 's/::.*//g' -e 's/([+-])$//g' "$work/postfix_with_s.fa" > "$work/postfix_clean.fa"

# Stable hashes for the verification log.
prefix_hash=$(shasum -a 256 "$work/prefix_clean.fa"  | awk '{print $1}')
postfix_hash=$(shasum -a 256 "$work/postfix_clean.fa" | awk '{print $1}')

echo "[strand-real] PRE-FIX  (no -s) FASTA sha256: $prefix_hash"
echo "[strand-real] POST-FIX (-s)    FASTA sha256: $postfix_hash"

if [[ "$prefix_hash" == "$postfix_hash" ]]; then
    echo "[strand-real] FAIL — extraction unchanged by -s, fixture or data path is wrong" >&2
    exit 1
fi

# Build a per-gene comparison via Python.
python3 - "$work/promoters.bed" "$work/prefix_clean.fa" "$work/postfix_clean.fa" <<'PY'
import sys

bed_path, pre_path, post_path = sys.argv[1:4]

def load_fa(path):
    seqs, name, buf = {}, None, []
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line:
                continue
            if line.startswith('>'):
                if name is not None:
                    seqs[name] = ''.join(buf)
                name = line[1:].split()[0]
                buf = []
            else:
                buf.append(line)
        if name is not None:
            seqs[name] = ''.join(buf)
    return seqs

pre  = load_fa(pre_path)
post = load_fa(post_path)

strands = {}
with open(bed_path) as f:
    for line in f:
        cols = line.rstrip().split('\t')
        if len(cols) < 6:
            continue
        strands[cols[3]] = cols[5]

complement = str.maketrans('ACGTacgtNn', 'TGCAtgcaNn')

n_plus_match = n_plus_diff = 0
n_minus_rc_match = n_minus_rc_diff = 0
plus_examples_diff = []
minus_examples_bad = []

for name, strand in strands.items():
    if name not in pre or name not in post:
        continue
    a, b = pre[name], post[name]
    if strand == '+':
        if a == b:
            n_plus_match += 1
        else:
            n_plus_diff += 1
            if len(plus_examples_diff) < 3:
                plus_examples_diff.append(name)
    else:
        rc = a.translate(complement)[::-1]
        if rc == b:
            n_minus_rc_match += 1
        else:
            n_minus_rc_diff += 1
            if len(minus_examples_bad) < 3:
                minus_examples_bad.append(name)

print(f"[strand-real] + strand: {n_plus_match} identical, {n_plus_diff} differ")
print(f"[strand-real] - strand: {n_minus_rc_match} are RC of pre-fix, {n_minus_rc_diff} are not")

ok = (n_plus_diff == 0 and n_minus_rc_diff == 0
      and n_plus_match  > 0 and n_minus_rc_match > 0)
if not ok:
    if plus_examples_diff:
        print(f"  + strand mismatches sample: {plus_examples_diff}", file=sys.stderr)
    if minus_examples_bad:
        print(f"  - strand RC mismatches sample: {minus_examples_bad}", file=sys.stderr)
    sys.exit(1)
PY

rc=$?
if (( rc == 0 )); then
    echo "[strand-real] all per-gene checks passed"
fi
exit "$rc"
