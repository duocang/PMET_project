#!/usr/bin/env python3
"""
For each gene, report how much room there is upstream of the TSS before hitting
the nearest neighbouring gene on the same chromosome (strand-agnostic — the
nearest neighbour is the nearest body regardless of strand, since any gene
body clips the usable promoter region).

- Positive strand (+): TSS is at the BED start; distance = start - previous_gene_end
    (first gene on chromosome: distance = start, i.e. to coord 0)
- Negative strand (-): TSS is at the BED end; distance = next_gene_start - end
    (last gene on chromosome: distance = chrom_end - end, or 0 if chrom_end unknown)
"""

import sys
import os

try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def load_chromosome_lengths(chrom_file):
    """Load chromosome lengths from tab-separated file."""
    chrom_lengths = {}
    with open(chrom_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                seqid = parts[0]
                length = int(parts[1])
                chrom_lengths[seqid] = length
    return chrom_lengths


def plot_distance_histogram(results, output_file):
    """Plot histogram of distances to TSS."""
    if not HAS_MATPLOTLIB:
        print("Warning: matplotlib not available, skipping histogram plot", file=sys.stderr)
        return

    # Extract distances and filter
    distances = [distance for _, distance in results]
    # Filter distances: remove 0 and values > 10000 (similar to R script)
    filtered_distances = [d for d in distances if 0 < d <= 10000]

    if not filtered_distances:
        print("Warning: No valid distances to plot", file=sys.stderr)
        return

    # Create histogram
    plt.figure(figsize=(8, 5))
    plt.hist(filtered_distances, bins=range(0, 10100, 100),
             color='#1ba784', alpha=0.8, edgecolor='#1ba784')

    plt.title('Distance to TSS Histogram', fontsize=14)
    plt.xlabel('Distance', fontsize=12)
    plt.ylabel('Count', fontsize=12)
    plt.grid(True, alpha=0.3)

    # Minimal theme styling
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().set_facecolor('white')

    # Save histogram to same directory as output_file
    output_dir = os.path.dirname(output_file)
    histogram_path = os.path.join(output_dir, "histogram_distance_tss.png")

    plt.tight_layout()
    plt.savefig(histogram_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"          Histogram saved to: histogram_distance_tss.png")


def calculate_length_to_tss(bed_file, output_file, chromosome_lengths=None, header=False, plot_histogram=True):
    """Compute the upstream gap from each gene's TSS to its nearest neighbour on
    the same chromosome (strand-agnostic neighbour). Writes `gene<TAB>distance`
    lines and optionally plots a histogram of distances <= 10kb.

    Args:
        bed_file: Input BED file path (BED6, sorted within each chromosome).
        output_file: Output TSV path.
        chromosome_lengths: Optional {chrom_id: length}. Required to give the
            last - strand gene on a chromosome a non-zero distance.
    """
    # If chromosome lengths are not provided, initialize as empty dict
    if chromosome_lengths is None:
        chromosome_lengths = {}
        print("Warning: No chromosome lengths provided. D2T for last genes on negative strands will be 0.")

    genes = []

    # Read BED file
    with open(bed_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 6:
                print(f"Warning: Invalid BED line (< 6 fields): {line}", file=sys.stderr)
                continue

            chromosome = parts[0]
            start = int(parts[1])
            end = int(parts[2])
            gene = parts[3]
            strand = parts[5]

            # Validate coordinates
            if start >= end:
                print(f"Warning: Invalid coordinates for {gene} ({start} >= {end})", file=sys.stderr)
                continue

            if strand not in ['+', '-']:
                print(f"Warning: Invalid strand '{strand}' for {gene}", file=sys.stderr)
                continue

            genes.append({
                'chr': chromosome,
                'start': start,
                'end': end,
                'gene': gene,
                'strand': strand
            })

    # Group genes by chromosome
    chrom_genes = {}
    for gene in genes:
        chrom = gene['chr']
        if chrom not in chrom_genes:
            chrom_genes[chrom] = []
        chrom_genes[chrom].append(gene)

    # For each chromosome, sort genes by start position
    for chrom in chrom_genes:
        chrom_genes[chrom] = sorted(chrom_genes[chrom], key=lambda x: x['start'])

    # Calculate distances for each chromosome group
    results = []
    for chrom, genes_in_chrom in chrom_genes.items():
        chrom_end = chromosome_lengths.get(chrom, 0)

        for i, gene in enumerate(genes_in_chrom):
            strand    = gene['strand']
            gene_name = gene['gene']
            distance  = 0

            if strand == '+':
                # For positive strand: start position is TSS
                if i == 0:
                    # First gene: distance from chromosome start (0) to TSS
                    distance = gene['start']
                else:
                    # Distance between end of previous gene and current TSS
                    prev_gene_end = genes_in_chrom[i-1]['end']
                    distance = max(0, gene['start'] - prev_gene_end)

            else:  # strand == '-'
                # For negative strand: end position is TSS
                if i == len(genes_in_chrom) - 1:
                    # Last gene: distance from TSS to chromosome end
                    if chrom_end > gene['end']:
                        distance = chrom_end - gene['end']
                    else:
                        print(f"Warning: Chromosome end not available for {gene_name}, setting distance=0", file=sys.stderr)
                        distance = 0
                else:
                    # Distance between TSS and next gene's start
                    next_gene_start = genes_in_chrom[i+1]['start']
                    distance = max(0, next_gene_start - gene['end'])

            results.append((gene_name, distance))

    # Write output
    with open(output_file, 'w') as f:
        # Write header
        if header:
            f.write("Gene\tDistance_to_TSS\n")

        for gene_name, distance in results:
            f.write(f"{gene_name}\t{distance}\n")

    # Plot histogram if requested
    if plot_histogram:
        plot_distance_histogram(results, output_file)

    # print(f"Processed {len(genes)} genes, results written to {output_file}")


if __name__ == '__main__':
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Usage: calculate_length_to_tss.py <bed_file> <chromosome_lengths_file> <output_file>")
        sys.stderr.write("Note: BED file should be sorted by chromosome and strand\n")
        sys.exit(1)

    bed_file = sys.argv[1]
    chrom_file = sys.argv[2]
    output_file = sys.argv[3]

    chromosome_lengths = load_chromosome_lengths(chrom_file)

    calculate_length_to_tss(bed_file, output_file, chromosome_lengths)
