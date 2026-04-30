#!/usr/bin/env python3
"""Remove duplicate FASTA records by ID, keeping the first occurrence of each."""

from Bio import SeqIO
import argparse


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('infilepath', type=str)
    parser.add_argument('outfilepath', type=str)
    return parser.parse_args()


args = get_args()

with open(args.outfilepath, 'a') as outFile:
    record_ids = list()
    for record in SeqIO.parse(args.infilepath, 'fasta'):
        if record.id not in record_ids:
            record_ids.append(record.id)
            SeqIO.write(record, outFile, 'fasta')
