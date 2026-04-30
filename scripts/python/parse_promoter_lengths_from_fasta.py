#!/usr/bin/env python3
"""Write a two-column TSV mapping FASTA record ID to sequence length."""

from Bio import SeqIO
import csv
import argparse


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('filepath', type=str)
    parser.add_argument('outfilepath', type=str)
    return parser.parse_args()


args = get_args()

input_file = open(args.filepath)
my_dict = SeqIO.to_dict(SeqIO.parse(input_file, "fasta"))
peak_size = {}

for x in my_dict:
    peak_size[x] = len(my_dict[x])

with open(args.outfilepath, 'w') as f:
    w = csv.writer(f, delimiter='\t', lineterminator='\n')
    w.writerows(peak_size.items())
