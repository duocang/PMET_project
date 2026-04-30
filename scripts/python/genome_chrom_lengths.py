#!/usr/bin/env python3
"""Emit chromosome lengths in `<chrom>\\t<length>` form, with FASTA fallback.

Replaces the inline `grep '^##sequence-region' | awk` + `samtools faidx`
fallback that pipelines 03 and 08 had duplicated.

Strategy:
    1. If --gff3 is provided and contains `##sequence-region` directives,
       parse them. Each line is `##sequence-region <chrom> <start> <end>`
       (optionally with extra fields); we emit `<chrom>\\t<end>`.
    2. Otherwise fall back to `<genome>.fai`. Run `samtools faidx` if the
       index does not exist yet.

Optionally checks chromosome-name consistency between GFF3 and FASTA
when both are provided (`--check-chrom-naming`).

Usage:
    python3 scripts/python/genome_chrom_lengths.py \\
        [--gff3 IN.gff3] \\
        --genome IN.fasta \\
        --out OUT.genome \\
        [--check-chrom-naming]

Exit codes:
    0 - wrote a non-empty file.
    1 - chromosome-name mismatch (when --check-chrom-naming set), or
        could not derive any lengths.
    2 - usage error or missing input.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


def parse_sequence_regions(gff3: Path) -> list[tuple[str, int]]:
    """Return [(chrom, end), ...] from `##sequence-region` directives."""
    out: list[tuple[str, int]] = []
    with gff3.open() as fh:
        for line in fh:
            if not line.startswith("##sequence-region"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            chrom = parts[1]
            try:
                end = int(parts[3])
            except ValueError:
                continue
            out.append((chrom, end))
    return out


def first_gff3_chrom(gff3: Path) -> Optional[str]:
    """First non-comment, ≥9-column row's chromosome value."""
    with gff3.open() as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 9:
                return cols[0]
    return None


def first_fasta_chrom(fasta: Path) -> Optional[str]:
    """First `>name` token from the FASTA header line."""
    with fasta.open() as fh:
        for line in fh:
            if line.startswith(">"):
                return line[1:].split()[0]
    return None


def parse_fai(fai: Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    with fai.open() as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 2:
                continue
            try:
                end = int(cols[1])
            except ValueError:
                continue
            out.append((cols[0], end))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit chromosome lengths (chrom<TAB>length)."
    )
    parser.add_argument("--gff3", type=Path, default=None,
                        help="If set and contains ##sequence-region "
                             "directives, parse them.")
    parser.add_argument("--genome", type=Path, required=True,
                        help="FASTA used for the .fai fallback.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check-chrom-naming", action="store_true",
                        help="If --gff3 is set and the first GFF3 row's "
                             "chrom does not match the first FASTA chrom, "
                             "fail.")
    args = parser.parse_args()

    if not args.genome.is_file():
        print(f"error: not a file: {args.genome}", file=sys.stderr)
        return 2

    if args.check_chrom_naming and args.gff3 is not None:
        gc = first_gff3_chrom(args.gff3)
        fc = first_fasta_chrom(args.genome)
        if gc is None or fc is None:
            print("error: --check-chrom-naming: could not extract chrom "
                  "from one of the files", file=sys.stderr)
            return 1
        if gc != fc:
            print(
                f"error: chromosome name mismatch: GFF3 uses {gc!r} but "
                f"FASTA uses {fc!r}",
                file=sys.stderr,
            )
            return 1

    rows: list[tuple[str, int]] = []

    if args.gff3 is not None and args.gff3.is_file():
        rows = parse_sequence_regions(args.gff3)

    if not rows:
        # Fall back to .fai (build it via `samtools faidx` if absent).
        fai = args.genome.with_suffix(args.genome.suffix + ".fai")
        if not fai.is_file():
            try:
                subprocess.run(
                    ["samtools", "faidx", str(args.genome)],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"error: samtools faidx failed: {e}", file=sys.stderr)
                return 1
        if not fai.is_file():
            print(f"error: no .fai produced at {fai}", file=sys.stderr)
            return 1
        rows = parse_fai(fai)

    if not rows:
        print("error: could not derive any chromosome lengths",
              file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for chrom, end in rows:
            fh.write(f"{chrom}\t{end}\n")

    print(f"wrote {len(rows)} chromosome lengths to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
