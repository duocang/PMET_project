#!/usr/bin/env python3
"""Split a MEME file into N batch files by round-robin assignment of motifs, preserving the MEME header in each batch."""

import argparse
import numpy as np
import os


def count_motifs_in_file(file_content):
    """Count occurrences of 'MOTIF' in the file content."""
    return sum('MOTIF' in line for line in file_content)


def distribute_motifs_evenly(bigfile, threads, outdir):
    """Distribute motifs across `threads` output files by round-robin assignment."""
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Find the location of the first MOTIF.
    headind = next(i for i, line in enumerate(bigfile) if 'MOTIF' in line)
    meme_header_lines = bigfile[0:headind]

    # Initially create all the output files and write the header lines.
    files = [open(os.path.join(outdir, f"{i}.txt"), 'w') for i in range(threads)]
    for f in files:
        f.writelines(meme_header_lines)
        f.close()

    file_counter = 0
    ind1 = headind
    for i in range(ind1 + 1, len(bigfile)):
        if 'MOTIF' in bigfile[i] or i == len(bigfile) - 1:
            ind2 = i if 'MOTIF' in bigfile[i] else i + 1  # Include the last line.

            # Convert the found MOTIF interval to uppercase.
            bigfile[ind1] = bigfile[ind1].upper()

            lines_to_write = bigfile[ind1:ind2]
            with open(os.path.join(outdir, f"{file_counter}.txt"), 'a') as writer:
                writer.writelines(lines_to_write)

            # Rotate the file_counter within the range [0, threads-1].
            file_counter = (file_counter + 1) % threads

            ind1 = ind2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=argparse.FileType('r'), help="Input MEME file")
    parser.add_argument('outdir', type=str, help="Output directory")
    parser.add_argument('batch', type=int, default=8, help="Number of output batch files")
    args = parser.parse_args()

    bigfile = np.asarray(args.file.readlines())
    distribute_motifs_evenly(bigfile, args.batch, args.outdir)

if __name__ == "__main__":
    main()
