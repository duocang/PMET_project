#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute per-position information content (IC) for every motif in a combined
MEME file and write one row per motif (`<motif_name> <ic1> <ic2> ...`) to a
TSV output file.

Motifs are emitted in the order they appear in the source MEME file, which is
deterministic across machines (the previous directory-walking implementation
used `os.listdir` order, which is filesystem-dependent).
"""

import argparse
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('memefile', type=Path,
                   help="Combined MEME file (multiple MOTIF blocks)")
    p.add_argument('outfile', type=Path,
                   help="TSV output, one motif per row")
    return p.parse_args()


def split_motifs(lines):
    """Yield (motif_name, motif_block_lines) for every MOTIF block in the file.

    The block returned is the full slice from the MOTIF header line up to (but
    not including) the next MOTIF header (or EOF), matching the slice that
    the legacy `parse_memefile.py` (now `scripts/archive/python/`) used to dump.
    """
    motif_idx = [i for i, line in enumerate(lines) if line.startswith('MOTIF')]
    if not motif_idx:
        return
    boundaries = motif_idx + [len(lines)]
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        header = lines[start]
        # Mirror legacy parse_memefile.py: upper-case the entire MOTIF header
        # before extracting the id. Downstream pair_parallel joins fimohits ↔
        # IC.txt ↔ binomial_thresholds by motif id, and the index_fimo_fused
        # path also feeds an uppercased meme — keep IC.txt's id column in the
        # same case so the join still works for mixed-case input MEMEs.
        name = header.upper().split()[1]
        yield name, lines[start:end]


def motif_length(block):
    """Parse `w=<int>` from the letter-probability matrix header inside the block."""
    for line in block:
        if 'letter-probability matrix' in line:
            m = re.search(r'w=\s*(\d+)', line)
            if m:
                return int(m.group(1))
    raise ValueError("letter-probability matrix line not found in motif block")


def extract_matrix(block, length):
    """Return the LPM as a (length, 4) float array."""
    for i, line in enumerate(block):
        if 'letter-probability matrix' in line:
            mat_start = i + 1
            mat_end = mat_start + length
            break
    else:
        raise ValueError("letter-probability matrix line not found in motif block")
    rows = []
    for raw in block[mat_start:mat_end]:
        # Whitespace split (not tab) — MEME matrices may be space-padded.
        rows.extend(raw.split()[:4])
    return np.asarray(rows, dtype=float).reshape((length, 4))


def calculate_ic(matrix):
    """Return per-position IC as a list. Mirrors the prior implementation:
    Shannon IC with 0-probability cells dropped; nansum is used only when NaNs
    are actually present (faster path otherwise)."""
    nrows = matrix.shape[0]
    ic_vec = [None] * nrows
    has_nan = np.isnan(matrix).any()
    for i in range(nrows):
        row = [v for v in matrix[i, :] if v != 0]
        if has_nan:
            ic_vec[i] = 2 + np.nansum([x * math.log2(x) for x in row])
        else:
            ic_vec[i] = 2 + sum(x * math.log2(x) for x in row)
    return ic_vec


def main():
    args = parse_args()

    with args.memefile.open() as fh:
        lines = fh.readlines()

    rows = []
    for name, block in split_motifs(lines):
        length = motif_length(block)
        mat = extract_matrix(block, length)
        ic = calculate_ic(mat)
        rows.append(name + ' ' + ' '.join(str(v) for v in ic))

    # Single-column TSV — matches the prior file shape exactly.
    df = pd.DataFrame(rows)
    df.to_csv(args.outfile, mode='w', sep='\t', header=False, index=False)


if __name__ == "__main__":
    main()
