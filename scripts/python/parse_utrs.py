#!/usr/bin/env python3
"""
Extend each promoter region to include the 5' UTR, by pushing the
promoter boundary from the gene-level TSS to the first CDS boundary.

Strand-aware logic:
  + strand: promoter is [upstream, gene_start)
            → extend end to min(CDS start) - 1  (0-based BED)
  - strand: promoter is [gene_end, downstream)
            → extend start to max(CDS end)       (0-based BED)

The promoter BED file is modified IN-PLACE.
"""

import sys
import argparse


def parse_gene_name(attr_field, prefix="ID=gene:"):
    """Extract gene name from GFF3 attribute field."""
    for field in attr_field.split(";"):
        if field.startswith(prefix):
            return field[len(prefix):]
    # fallback: try ID=
    for field in attr_field.split(";"):
        if field.startswith("ID="):
            return field[3:]
    return None


def build_cds_map(gff3_file):
    """Build a dict: gene_name -> {'min_cds_start': ..., 'max_cds_end': ...}

    CDS coordinates are converted from GFF3 (1-based closed) to BED (0-based).
    """
    # First pass: map each CDS Parent transcript to its gene
    transcript_to_gene = {}
    cds_map = {}

    with open(gff3_file, "r") as f:
        current_gene = None
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 9:
                continue

            feature = cols[2]
            start = int(cols[3])  # 1-based
            end = int(cols[4])    # 1-based
            attrs = cols[8]

            # Track current gene context
            if "gene" in feature and feature.endswith("gene"):
                # matches "gene", "ncRNA_gene", "pseudogene", etc.
                current_gene = parse_gene_name(attrs)

            elif feature == "mRNA" and current_gene:
                # Map transcript to its parent gene
                for field in attrs.split(";"):
                    if field.startswith("ID="):
                        tid = field[3:]
                        transcript_to_gene[tid] = current_gene
                        break

            elif feature == "CDS" and current_gene:
                # Convert to 0-based: start_bed = start_gff - 1, end_bed = end_gff
                cds_start_bed = start - 1
                cds_end_bed = end

                if current_gene not in cds_map:
                    cds_map[current_gene] = {
                        "min_cds_start": cds_start_bed,
                        "max_cds_end": cds_end_bed,
                    }
                else:
                    if cds_start_bed < cds_map[current_gene]["min_cds_start"]:
                        cds_map[current_gene]["min_cds_start"] = cds_start_bed
                    if cds_end_bed > cds_map[current_gene]["max_cds_end"]:
                        cds_map[current_gene]["max_cds_end"] = cds_end_bed

    return cds_map


def extend_promoters(prom_file, cds_map):
    """Extend promoter boundaries to include 5' UTR, modify in-place."""
    lines_out = []
    n_extended = 0
    n_no_cds = 0

    with open(prom_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 6:
                lines_out.append(line)
                continue

            chrom = cols[0]
            start = int(cols[1])
            end = int(cols[2])
            name = cols[3]
            score = cols[4]
            strand = cols[5]

            if name not in cds_map:
                # No CDS info (e.g. ncRNA) — keep as is
                n_no_cds += 1
                lines_out.append(f"{chrom}\t{start}\t{end}\t{name}\t{score}\t{strand}")
                continue

            if strand == "+":
                # Extend promoter end to the earliest CDS start (include 5'UTR)
                new_end = cds_map[name]["min_cds_start"]
                if new_end > end:
                    end = new_end
                    n_extended += 1
            else:
                # Extend promoter start to the latest CDS end (include 5'UTR)
                new_start = cds_map[name]["max_cds_end"]
                if new_start < start:
                    start = new_start
                    n_extended += 1

            lines_out.append(f"{chrom}\t{start}\t{end}\t{name}\t{score}\t{strand}")

    with open(prom_file, "w") as f:
        for line in lines_out:
            f.write(line + "\n")

    print(f"        Extended {n_extended} promoter(s) to include 5' UTR")
    if n_no_cds > 0:
        print(f"        {n_no_cds} gene(s) without CDS (ncRNA etc.) — unchanged")


def main():
    parser = argparse.ArgumentParser(
        description="Extend promoter regions to include 5' UTR"
    )
    parser.add_argument("promfile", help="Promoter BED6 file (modified in-place)")
    parser.add_argument("gff3file", help="Sorted GFF3 annotation file")
    args = parser.parse_args()

    cds_map = build_cds_map(args.gff3file)
    extend_promoters(args.promfile, cds_map)


if __name__ == "__main__":
    main()
