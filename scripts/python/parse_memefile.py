#!/usr/bin/env python3
"""Split a MEME file into one file per motif, named after the motif identifier, into an output directory."""

import argparse
import numpy as np
import os

parser = argparse.ArgumentParser()
parser.add_argument('file', type=argparse.FileType('r'))
parser.add_argument('outdir', type=str)
args = parser.parse_args()

bigfile = np.asarray(args.file.readlines())

# Locate the first MOTIF line; everything before it is the shared MEME header.
headind = 0
while bigfile[headind].find('MOTIF') == -1:
    headind += 1

ind1 = headind
counter = 1
for i in range((ind1 + 1), len(bigfile)):
    if bigfile[i].find('MOTIF') > -1:
        ind2 = i
        inds_to_write = np.append(np.arange(headind), np.arange(ind1, ind2))
        bigfile[ind1] = bigfile[ind1].upper()
        lines_to_write = bigfile[inds_to_write]
        motname = bigfile[ind1].split()[1]
        with open(os.path.normcase(args.outdir + motname + '.txt'), 'w') as writer:
            writer.writelines(lines_to_write)
        ind1 = ind2
        counter = counter + 1

# Write the last motif (loop above only fires on motif boundaries).
ind2 = i + 1
inds_to_write = np.append(np.arange(headind), np.arange(ind1, ind2))
bigfile[ind1] = bigfile[ind1].upper()
lines_to_write = bigfile[inds_to_write]
motname = bigfile[ind1].split()[1]

with open(os.path.normcase(args.outdir + motname + '.txt'), 'w') as writer:
    writer.writelines(lines_to_write)