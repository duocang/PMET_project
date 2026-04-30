#!/bin/bash

# Resolve repo root (apps/cli/scripts/X.sh -> ../../..)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

fimothresh=0.05
memefile="$REPO_ROOT/data/demos/promoters/indexing/demo/motifs.txt"
promoters="$REPO_ROOT/data/demos/promoters/indexing/demo/promoters.fa"
bgfile="$REPO_ROOT/data/demos/promoters/indexing/demo/promoters.bg"
outdir="$REPO_ROOT/results/cli/demo/fimo_official"

rm -rf "$outdir"
mkdir -p "$outdir"

# Split the combined MEME file into per-motif files in a tmp dir.
# Downstream PMET indexers discover motifs by scanning a directory of
# fimo result files, so we still run fimo once per motif — the user just
# doesn't have to maintain a pre-split memefiles/ directory by hand.
tmp_meme_dir=$(mktemp -d)
trap 'rm -rf "$tmp_meme_dir"' EXIT

awk -v TMP="$tmp_meme_dir" '
  /^MOTIF / {
    if (cur != "") close(cur)
    cur = TMP "/" $2 ".txt"
    printf "%s", header > cur
    print > cur
    next
  }
  cur == "" { header = header $0 "\n"; next }
  { print > cur }
' "$memefile"

echo "Running FIMO analysis (threshold: $fimothresh)..."
for split in "$tmp_meme_dir"/*.txt; do
    name=$(basename "$split" .txt)
    echo "  Processing: $name"
    fimo --text \
        --thresh "$fimothresh" \
        --verbosity 1 \
        --bgfile "$bgfile" \
        "$split" \
        "$promoters" \
        > "$outdir/${name}.txt" 2>/dev/null
done

echo "Done."
echo "FIMO results are saved in $outdir/"
