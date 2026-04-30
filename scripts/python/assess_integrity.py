#!/usr/bin/env python3
"""
assess_integrity.py — Resolve split promoters after bedtools subtract.

When bedtools subtract removes gene-body overlaps from promoter regions,
a single promoter may be split into multiple non-contiguous fragments.
This script keeps ONLY the fragment closest to the transcription start
site (TSS) and discards the rest.

Strand-aware logic:
  ┌─────────────────────────────────────┐
  │  + strand gene:                     │
  │    Promoter ◄──── TSS → Gene body   │
  │    TSS is at the RIGHT end of the   │
  │    promoter, so keep the fragment   │
  │    with the LARGEST coordinates.    │
  │                                     │
  │  − strand gene:                     │
  │    Gene body ← TSS ────► Promoter   │
  │    TSS is at the LEFT end of the    │
  │    promoter, so keep the fragment   │
  │    with the SMALLEST coordinates.   │
  └─────────────────────────────────────┘

The input BED6 file is modified IN-PLACE.

Usage:
    python3 assess_integrity.py <promoters.bed>
"""

import sys
import numpy as np
import pandas as pd
import argparse


def resolve_split_promoters(infile: str) -> None:
    """Remove split-promoter fragments, keeping the one closest to TSS."""

    # ------ read ------
    try:
        bed = pd.read_csv(
            infile, sep='\t', header=None,
            names=['chrom', 'start', 'end', 'name', 'score', 'strand'],
            dtype={'chrom': str, 'start': int, 'end': int,
                   'name': str, 'score': int, 'strand': str}
        )
    except Exception as e:
        print(f"ERROR: Failed to read {infile}: {e}", file=sys.stderr)
        sys.exit(1)

    if bed.empty:
        print(f"        WARNING: {infile} is empty — nothing to check",
              file=sys.stderr)
        return

    # ------ identify fragments to keep ------
    # Group by gene name: every group's strand is consistent (the BED comes
    # from a strand-aware flank → optional subtract pipeline). For each
    # split-into-N gene we keep the fragment closest to the TSS:
    #   + strand: TSS is at the right (larger end coord) → keep idxmax(end)
    #   − strand: TSS is at the left  (smaller start)    → keep idxmin(start)
    #
    # The previous implementation only compared adjacent rows after sortBed.
    # That holds on TAIR10 default config (29 824 unique gene names in the
    # scripts/03 baseline), but breaks the moment a third gene's promoter
    # sorts between two same-gene fragments — e.g. when a small gene falls
    # entirely inside another gene's flanking promoter region. We fix the
    # algorithm to be order-independent at no measurable cost.
    keep_idx = []
    for _, group in bed.groupby('name', sort=False):
        if len(group) == 1:
            keep_idx.append(group.index[0])
            continue
        strand = group.iloc[0]['strand']
        if strand == '+':
            keep_idx.append(group['end'].idxmax())
        else:
            keep_idx.append(group['start'].idxmin())

    keep_set = set(keep_idx)
    n_removed = len(bed) - len(keep_set)

    if n_removed > 0:
        print(f"        Removed {n_removed} split promoter fragment(s), "
              f"{len(keep_set)} promoters remain")
    else:
        print(f"        No split promoters detected ({len(bed)} promoters intact)")

    # Preserve original BED ordering (sortBed input order) by sorting the
    # kept index. This keeps downstream contract files byte-stable on the
    # paths where the bug never manifested.
    bed_clean = bed.loc[sorted(keep_set)].reset_index(drop=True)
    bed_clean.to_csv(infile, sep='\t', header=False, index=False)


def main():
    parser = argparse.ArgumentParser(
        description='Resolve split promoters — keep fragment closest to TSS')
    parser.add_argument(
        'infile', type=str,
        help='BED6 file of promoter regions (modified in-place)')
    args = parser.parse_args()

    resolve_split_promoters(args.infile)


if __name__ == '__main__':
    main()