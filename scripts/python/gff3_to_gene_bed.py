#!/usr/bin/env python3
"""Convert a GFF3 to a gene-level BED6 in one pass.

Replaces the inline awk blocks that pipelines 03 and 08 had used to:

  1. Filter rows whose column 3 matches `gene` (or any feature ending in
     `gene`, e.g. `ncRNA_gene`, `pseudogene`).
  2. Pull the gene name from the attribute column using `<key>=<value>`.
  3. Convert GFF3 1-based start to BED 0-based.
  4. Drop rows with `start >= end`.
  5. Drop duplicate gene names (keep first).

Output: BED6 with columns (chrom, start, end, name, score=1, strand).

Replaces (and supersedes) `parse_genelines.py` for new code; the old
script is retained as a thin compatibility wrapper.

Usage:
    python3 scripts/python/gff3_to_gene_bed.py \\
        --gff3 IN.gff3 \\
        --out  OUT.bed \\
        [--id-key gene_id=]   (default: gene_id=, with ID= as fallback)
        [--feature-regex 'gene$']

Exit codes:
    0 - wrote a non-empty BED.
    1 - any of the steps failed (no genes match, attribute key not found,
        all rows have start >= end, etc.).
    2 - usage error or missing input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


def parse_attribute(attrs: str, key: str) -> Optional[str]:
    """Return value of `<key>=<value>` from a GFF3 attribute string.

    `key` must include the trailing `=`. Tolerates surrounding whitespace.
    """
    for field in attrs.split(";"):
        field = field.strip()
        if field.startswith(key):
            return field[len(key):]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a GFF3 to gene-level BED6 in one pass."
    )
    parser.add_argument("--gff3", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--id-key", default="gene_id=",
        help="Attribute key (with trailing '='). Falls back to 'ID=' if "
             "the primary key is absent.",
    )
    parser.add_argument(
        "--feature-regex", default=r"gene$",
        help="Regex matched against column 3. Default 'gene$' matches "
             "'gene', 'ncRNA_gene', 'pseudogene'.",
    )
    args = parser.parse_args()

    if not args.gff3.is_file():
        print(f"error: not a file: {args.gff3}", file=sys.stderr)
        return 2

    feature_re = re.compile(args.feature_regex)
    primary_key = args.id_key
    if not primary_key.endswith("="):
        print(
            f"warning: --id-key {primary_key!r} does not end with '=' — "
            f"this is unusual",
            file=sys.stderr,
        )

    rows: list[tuple[str, int, int, str, str]] = []
    seen_names: set[str] = set()

    n_total = 0
    n_feature = 0
    n_invalid = 0
    n_dup = 0
    n_no_key = 0

    with args.gff3.open() as fh:
        for line in fh:
            n_total += 1
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 9:
                continue
            if not feature_re.search(cols[2]):
                continue
            n_feature += 1

            # Resolve gene name. Use primary key first; fall back to ID=.
            name = parse_attribute(cols[8], primary_key)
            if name is None and primary_key != "ID=":
                name = parse_attribute(cols[8], "ID=")
            if name is None:
                n_no_key += 1
                continue

            try:
                start = int(cols[3]) - 1   # GFF3 → BED
                end = int(cols[4])
            except ValueError:
                continue

            if start >= end:
                n_invalid += 1
                continue

            if name in seen_names:
                n_dup += 1
                continue
            seen_names.add(name)

            rows.append((cols[0], start, end, name, cols[6]))

    if not rows:
        print(
            f"error: no gene rows survived filters — "
            f"feature={n_feature} invalid={n_invalid} dup={n_dup} "
            f"missing-key={n_no_key}",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as out:
        for chrom, start, end, name, strand in rows:
            out.write(f"{chrom}\t{start}\t{end}\t{name}\t1\t{strand}\n")

    summary = (
        f"wrote {len(rows)} gene rows to {args.out} "
        f"(feature={n_feature} invalid={n_invalid} duplicates={n_dup} "
        f"missing-key={n_no_key})"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
