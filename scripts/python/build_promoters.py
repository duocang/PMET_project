#!/usr/bin/env python3
"""Build the promoter side of a homotypic input from a gene BED.

Replaces the inline 9-step `bedtools flank → … → fasta-get-markov`
sequence that was duplicated across `02_perf_params.sh`,
`03_promoter.sh`, and `05_promoter_gap.sh`. The behaviour matches the
union of those scripts exactly:

    1. bedtools flank -l <length> -r 0 -s -i <gene_bed> -g <chrom_sizes>
    2. sortBed
    3. (if gap > 0) shrink the TSS-proximal end by `gap` bp; drop intervals
       that collapse to empty.
    4. Filter promoters shorter than 10 bp (from edge clipping).
    5. (if overlap == "NoOverlap") bedtools subtract -a promoters -b gene_bed.
    6. Filter promoters shorter than 20 bp (post-subtraction).
    7. (if overlap == "NoOverlap") resolve split promoters using
       scripts/python/assess_integrity.py — keep TSS-side fragment.
    8. (if utr == "Yes") extend each promoter to include its 5' UTR using
       scripts/python/parse_utrs.py and the sorted GFF3.
    9. Compute promoter_lengths.txt (gene_id\tlength).
   10. Compute universe.txt (one gene id per line).
   11. bedtools getfasta -name -s, then strip bedtools header suffixes
       (`::chr:start-end` and trailing `(+)`/`(-)`).
   12. fasta-get-markov on the cleaned FASTA.

Output paths are explicit; nothing is written outside the `--out-*`
files. Intermediate `.bed.tmp` and `.fa.tmp` files are written next to
their final outputs and removed before exit.

Pipelines retain final responsibility for short-promoter removal logs
(`promoters_removed_lt{10,20}.bed`); this CLI emits them next to
`--out-bed` only when called with `--out-removed-dir`. Mirrors what
03 / 08 used to write.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, raising on non-zero exit.

    Stdout/stderr are passed through (callers see external tool output).
    """
    return subprocess.run(cmd, check=True, **kwargs)


def filter_short_promoters(
    bed: Path, min_len: int, removed: Optional[Path] = None
) -> int:
    """Drop rows shorter than `min_len`. Optionally save dropped rows to
    `removed`. Returns the number of rows dropped.
    """
    keep_lines: list[str] = []
    drop_lines: list[str] = []
    with bed.open() as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            try:
                start, end = int(cols[1]), int(cols[2])
            except ValueError:
                continue
            if end - start < min_len:
                drop_lines.append(line)
            else:
                keep_lines.append(line)
    bed.write_text("".join(keep_lines))
    if removed is not None and drop_lines:
        removed.write_text("".join(drop_lines))
    return len(drop_lines)


def shrink_for_gap(bed: Path, gap: int) -> tuple[int, int]:
    """Shrink the TSS-proximal end of every promoter by `gap` bp.

    + strand TSS is at the BED end ($3) → subtract `gap` from end.
    - strand TSS is at the BED start ($2) → add `gap` to start.
    Drop rows that collapse to empty.

    Returns (rows_before, rows_after).
    """
    keep: list[str] = []
    before = 0
    with bed.open() as fh:
        for line in fh:
            before += 1
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 6:
                continue
            chrom, start_s, end_s, name, score, strand = cols[:6]
            start, end = int(start_s), int(end_s)
            if strand == "+":
                end -= gap
            else:
                start += gap
            if start < end:
                keep.append(
                    f"{chrom}\t{start}\t{end}\t{name}\t{score}\t{strand}\n"
                )
    bed.write_text("".join(keep))
    return before, len(keep)


def clean_fasta_headers(raw: Path, clean: Path) -> None:
    """Strip bedtools' name decorations.

    `getfasta -name -s` produces headers like
    `>gene::chr:start-end(+)`. Pipeline scripts had been collapsing
    them to bare `>gene` via two sed expressions; replicate that here
    so the FASTA is what the FIMO step has always seen.
    """
    with raw.open() as src, clean.open("w") as dst:
        for line in src:
            if line.startswith(">"):
                # `>name::chr:start-end(+)` → strip `::...` and `(+)/(−)` suffix.
                cut = line.split("::", 1)[0]
                # Also handle the `(+)/(-)` directly after the name (rare).
                if cut.endswith("(+)") or cut.endswith("(-)"):
                    cut = cut[:-3]
                dst.write(cut + "\n")
            else:
                dst.write(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build promoter BED + FASTA + bg + lengths + universe from a "
            "gene BED. Behaviourally equivalent to the inline blocks in "
            "pipelines 02, 03, 08."
        )
    )
    parser.add_argument("--gene-bed", type=Path, required=True,
                        help="Gene BED6 (chrom, start, end, name, score, strand).")
    parser.add_argument("--genome-sizes", type=Path, required=True,
                        help="Two-column TSV: chrom, length.")
    parser.add_argument("--genome-fasta", type=Path, required=True,
                        help="Linearised, indexed genome FASTA.")
    parser.add_argument("--sorted-gff3", type=Path, default=None,
                        help="Sorted GFF3; required when --utr Yes.")
    parser.add_argument("--length", type=int, required=True,
                        help="Promoter flank length (bp upstream of TSS).")
    parser.add_argument("--gap", type=int, default=0,
                        help="TSS-proximal gap; 0 = no gap.")
    parser.add_argument("--overlap", choices=("AllowOverlap", "NoOverlap"),
                        default="AllowOverlap")
    parser.add_argument("--utr", choices=("Yes", "No"), default="No")
    parser.add_argument("--out-bed", type=Path, required=True)
    parser.add_argument("--out-fasta", type=Path, required=True)
    parser.add_argument("--out-bg", type=Path, required=True)
    parser.add_argument("--out-lengths", type=Path, required=True)
    parser.add_argument("--out-universe", type=Path, required=True)
    parser.add_argument("--out-removed-dir", type=Path, default=None,
                        help="Directory to drop promoters_removed_lt{10,20}.bed.")
    parser.add_argument("--assess-integrity",
                        type=Path,
                        default=Path(__file__).parent / "assess_integrity.py")
    parser.add_argument("--parse-utrs",
                        type=Path,
                        default=Path(__file__).parent / "parse_utrs.py")
    args = parser.parse_args()

    if args.utr == "Yes" and args.sorted_gff3 is None:
        print("error: --utr Yes requires --sorted-gff3", file=sys.stderr)
        return 2

    out_bed = args.out_bed
    out_bed.parent.mkdir(parents=True, exist_ok=True)
    args.out_fasta.parent.mkdir(parents=True, exist_ok=True)
    args.out_bg.parent.mkdir(parents=True, exist_ok=True)
    args.out_lengths.parent.mkdir(parents=True, exist_ok=True)
    args.out_universe.parent.mkdir(parents=True, exist_ok=True)
    if args.out_removed_dir is not None:
        args.out_removed_dir.mkdir(parents=True, exist_ok=True)

    # 1. flank
    flank_unsorted = out_bed.with_suffix(out_bed.suffix + ".unsorted")
    with flank_unsorted.open("w") as f:
        run(
            [
                "bedtools", "flank",
                "-l", str(args.length), "-r", "0", "-s",
                "-i", str(args.gene_bed),
                "-g", str(args.genome_sizes),
            ],
            stdout=f,
        )

    # 2. sortBed
    with out_bed.open("w") as f:
        run(["sortBed", "-i", str(flank_unsorted)], stdout=f)
    flank_unsorted.unlink()

    # 3. gap shrink (08 path)
    if args.gap > 0:
        before, after = shrink_for_gap(out_bed, args.gap)
        print(
            f"        Applied gap={args.gap} bp; promoters: {before} -> {after}"
        )

    # 4. filter < 10 bp
    removed_lt10 = (
        args.out_removed_dir / "promoters_removed_lt10.bed"
        if args.out_removed_dir is not None
        else None
    )
    n10 = filter_short_promoters(out_bed, 10, removed_lt10)
    if n10:
        print(f"        Removed {n10} promoter(s) < 10 bp")

    # 5. subtract gene bodies (NoOverlap)
    if args.overlap == "NoOverlap":
        sub = out_bed.with_suffix(out_bed.suffix + ".sub")
        with sub.open("w") as f:
            run(
                ["bedtools", "subtract", "-a", str(out_bed), "-b", str(args.gene_bed)],
                stdout=f,
            )
        sub.replace(out_bed)

    # 6. filter < 20 bp
    removed_lt20 = (
        args.out_removed_dir / "promoters_removed_lt20.bed"
        if args.out_removed_dir is not None
        else None
    )
    n20 = filter_short_promoters(out_bed, 20, removed_lt20)
    if n20:
        print(f"        Removed {n20} promoter(s) < 20 bp")

    # 7. resolve split promoters (NoOverlap)
    if args.overlap == "NoOverlap":
        run(["python3", str(args.assess_integrity), str(out_bed)])

    # 8. UTR extension (utr=Yes)
    if args.utr == "Yes":
        run(["python3", str(args.parse_utrs), str(out_bed), str(args.sorted_gff3)])

    # 9. promoter_lengths.txt
    with args.out_lengths.open("w") as fh:
        with out_bed.open() as src:
            for line in src:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 4:
                    continue
                fh.write(f"{cols[3]}\t{int(cols[2]) - int(cols[1])}\n")

    # 10. universe.txt
    with args.out_universe.open("w") as fh:
        with args.out_lengths.open() as src:
            for line in src:
                fh.write(line.split("\t", 1)[0] + "\n")

    gene_count = sum(1 for _ in args.out_universe.open())
    print(f"        {gene_count} genes with valid promoters")

    # 11. getfasta + clean headers
    raw_fa = args.out_fasta.with_suffix(args.out_fasta.suffix + ".raw")
    run(
        [
            "bedtools", "getfasta",
            "-fi", str(args.genome_fasta),
            "-bed", str(out_bed),
            "-fo", str(raw_fa),
            "-name", "-s",
        ]
    )
    clean_fasta_headers(raw_fa, args.out_fasta)
    raw_fa.unlink()

    # 12. fasta-get-markov
    with args.out_bg.open("w") as f:
        run(["fasta-get-markov", str(args.out_fasta)], stdout=f)

    return 0


if __name__ == "__main__":
    sys.exit(main())
