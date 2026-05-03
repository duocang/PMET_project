#!/usr/bin/env python3
"""Run the homotypic stage of a promoter PMET pipeline end-to-end.

Composes the existing helpers in `scripts/python/` and the
`build/indexing_fimo_fused` binary into a single Python entrypoint.
Pipelines 03 and 08 use this for their entire stage A; the bash entry
script then only orchestrates configuration and the heterotypic +
heatmap stages.

Inputs:
    --genome PATH           genome FASTA (will be linearised + indexed)
    --anno PATH             GFF3 annotation
    --meme PATH             MEME motif file
    --output-dir PATH       homotypic output directory
    --length INT            promoter flank length
    --gap INT               TSS-proximal gap (0 = none)
    --maxk INT --topn INT   FIMO --topk / --topn
    --fimothresh FLOAT      FIMO --thresh
    --overlap {AllowOverlap,NoOverlap}
    --utr {Yes,No}
    --gff3-id-key STR       attribute key (e.g. 'gene_id=' or 'ID=gene:')
    --threads INT           number of parallel FIMO batches
    [--poisson]             pass --poisson to indexing_fimo_fused
    [--keep-intermediate]   retain intermediate files for debugging

Output (canonical homotypic_dir contract — see docs/contracts/homotypic.md):
    promoter_lengths.txt
    binomial_thresholds.txt
    IC.txt
    universe.txt
    fimohits/<motif>.txt

The Python helpers used:
    gff3_to_gene_bed.py, genome_chrom_lengths.py, build_promoters.py,
    calculateICfrommeme_IC_to_csv.py,
    check_homotypic_contract.py.

The external tools used (must be on PATH):
    samtools, bedtools, sortBed, fasta-get-markov, perl (for gff3sort.pl),
    build/indexing_fimo_fused.

Pipelines that build their own gene BED differently (06/07 use
pmet_index_element.sh) do not use this entrypoint.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PY_DIR = Path(__file__).resolve().parent
REPO_ROOT = PY_DIR.parent.parent


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, raising on non-zero exit."""
    return subprocess.run(cmd, check=True, **kwargs)


def step(label: str) -> None:
    print(f"   [{label}]", flush=True)


def linearise_fasta(src: Path, dst: Path) -> None:
    """Strip line wrapping from a FASTA so bedtools getfasta is happy."""
    with src.open() as src_fh, dst.open("w") as dst_fh:
        first = True
        for line in src_fh:
            if line.startswith(">"):
                if not first:
                    dst_fh.write("\n")
                dst_fh.write(line.rstrip("\n") + "\n")
                first = False
            else:
                dst_fh.write(line.rstrip("\n"))
        dst_fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a promoter pipeline's homotypic stage end-to-end."
    )
    parser.add_argument("--genome", type=Path, required=True)
    parser.add_argument("--anno", type=Path, required=True)
    parser.add_argument("--meme", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--gap", type=int, default=0)
    parser.add_argument("--maxk", type=int, required=True)
    parser.add_argument("--topn", type=int, required=True)
    parser.add_argument("--fimothresh", type=float, required=True)
    parser.add_argument("--overlap",
                        choices=("AllowOverlap", "NoOverlap"),
                        default="AllowOverlap")
    parser.add_argument("--utr", choices=("Yes", "No"), default="No")
    parser.add_argument("--gff3-id-key", default="gene_id=")
    parser.add_argument(
        "--gene-features",
        choices=("all", "strict"),
        default="all",
        help=(
            "Which GFF3 column-3 feature types count as a gene. "
            "'all' (default) → regex 'gene$' — gene, ncRNA_gene, "
            "pseudogene, transposable_element_gene, etc. "
            "'strict' → regex '^gene$' — only canonical 'gene' rows."
        ),
    )
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--poisson", action="store_true")
    parser.add_argument("--keep-intermediate", action="store_true")
    parser.add_argument(
        "--bin-index",
        type=Path,
        default=REPO_ROOT / "build" / "indexing_fimo_fused",
        help="Path to the indexing_fimo_fused binary.",
    )
    parser.add_argument(
        "--gff3sort",
        type=Path,
        default=REPO_ROOT / "scripts" / "third_party" / "gff3sort" / "gff3sort.pl",
    )
    args = parser.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    sorted_gff3 = out / "sorted.gff3"
    gene_bed = out / "genelines.bed"
    chrom_sizes = out / "bedgenome.genome"
    stripped_fa = out / "genome_stripped.fa"
    promoters_bed = out / "promoters.bed"
    promoters_fa = out / "promoters.fa"
    promoters_bg = out / "promoters.bg"
    universe_txt = out / "universe.txt"
    lengths_txt = out / "promoter_lengths.txt"
    ic_txt = out / "IC.txt"
    fimohits_dir = out / "fimohits"

    # ---- 1. Sort GFF3 ----
    step("1. Sorting GFF3")
    args.gff3sort.chmod(0o755)
    with sorted_gff3.open("w") as fh:
        run(["perl", str(args.gff3sort), str(args.anno)], stdout=fh)

    # ---- 2. Build gene BED ----
    step(f"2. Building gene BED (gene_features={args.gene_features})")
    feature_regex = "^gene$" if args.gene_features == "strict" else "gene$"
    run([
        "python3", str(PY_DIR / "gff3_to_gene_bed.py"),
        "--gff3", str(sorted_gff3),
        "--out", str(gene_bed),
        "--id-key", args.gff3_id_key,
        "--feature-regex", feature_regex,
    ])

    # ---- 3. Chromosome sizes ----
    step("3. Chromosome lengths")
    run([
        "python3", str(PY_DIR / "genome_chrom_lengths.py"),
        "--gff3", str(args.anno),
        "--genome", str(args.genome),
        "--out", str(chrom_sizes),
    ])

    # ---- 4. Linearise FASTA + faidx ----
    step("4. Linearising FASTA")
    linearise_fasta(args.genome, stripped_fa)
    run(["samtools", "faidx", str(stripped_fa)])

    # ---- 5. Build promoters ----
    step("5. Building promoters (length=%d, gap=%d)" % (args.length, args.gap))
    cmd = [
        "python3", str(PY_DIR / "build_promoters.py"),
        "--gene-bed", str(gene_bed),
        "--genome-sizes", str(chrom_sizes),
        "--genome-fasta", str(stripped_fa),
        "--sorted-gff3", str(sorted_gff3),
        "--length", str(args.length),
        "--gap", str(args.gap),
        "--overlap", args.overlap,
        "--utr", args.utr,
        "--out-bed", str(promoters_bed),
        "--out-fasta", str(promoters_fa),
        "--out-bg", str(promoters_bg),
        "--out-lengths", str(lengths_txt),
        "--out-universe", str(universe_txt),
        "--out-removed-dir", str(out),
    ]
    run(cmd)

    # ---- 6. IC ----
    step("6. Computing IC (per-motif)")
    run([
        "python3", str(PY_DIR / "calculateICfrommeme_IC_to_csv.py"),
        str(args.meme), str(ic_txt),
    ])

    # ---- 7. FIMO + PMETindex via indexing_fimo_fused ----
    # Upper-case MOTIF header lines so motif ids are consistent with the IC
    # helper (which also upper-cases the MOTIF header before extracting the id)
    # — pairing_parallel joins fimohits ↔ IC ↔ binomial_thresholds by motif id.
    meme_upper = out / "meme_upper.meme"
    nummotifs = 0
    with args.meme.open() as src, meme_upper.open("w") as dst:
        for line in src:
            if line.startswith("MOTIF"):
                nummotifs += 1
                dst.write(line.upper())
            else:
                dst.write(line)
    if nummotifs <= 0:
        print("error: MEME file has no motifs", file=sys.stderr)
        return 1
    step(f"7. Running FIMO + PMETindex ({nummotifs} motifs, "
         f"{args.threads} threads)")
    fimohits_dir.mkdir(parents=True, exist_ok=True)

    poisson_args = ["--poisson"] if args.poisson else []
    fused_env = {**os.environ, "OMP_NUM_THREADS": str(args.threads)}
    run(
        [
            str(args.bin_index),
            *poisson_args,
            "--no-qvalue", "--text",
            "--thresh", str(args.fimothresh),
            "--verbosity", "1",
            "--bgfile", str(promoters_bg),
            "--topn", str(args.topn),
            "--topk", str(args.maxk),
            "--oc", str(out),
            str(meme_upper), str(promoters_fa), str(lengths_txt),
        ],
        env=fused_env,
    )

    # ---- 8. Sanity: file count ----
    # Upstream indexing_fimo_fused emits .bin since PMET_project commit 8fa9b66
    # ("perf: add binary SoA fimohits format"); older builds still emit .txt.
    # pairing_parallel auto-detects via the binary header magic, so accept either.
    fimohits_files = [
        p for p in fimohits_dir.iterdir()
        if p.is_file() and p.suffix in (".txt", ".bin")
    ]
    empty = [p for p in fimohits_files if p.stat().st_size == 0]
    if empty:
        print(
            f"        WARNING: {len(empty)} empty fimohit file(s)",
            file=sys.stderr,
        )
    if len(fimohits_files) != nummotifs:
        print(
            f"error: expected {nummotifs} fimohit files, found "
            f"{len(fimohits_files)}",
            file=sys.stderr,
        )
        return 1

    # ---- 9. Contract validation ----
    step("9. Validating homotypic contract")
    run([
        "python3", str(PY_DIR / "check_homotypic_contract.py"),
        str(out),
    ])

    # ---- 10. Cleanup intermediates ----
    if not args.keep_intermediate:
        for relpath in (
            "bedgenome.genome", "genelines.bed", "genelines.gff3",
            "genome_stripped.fa", "genome_stripped.fa.fai",
            "meme_upper.meme",
            "promoters.bed", "promoters.bg", "promoters.fa",
            "promoters_rough.fa", "sorted.gff3",
            "promoters_removed_lt10.bed", "promoters_removed_lt20.bed",
            "invalid_gff3_lines.txt", "feature_types.txt",
            "length_to_tss.txt", "fimo",
        ):
            target = out / relpath
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.is_file():
                target.unlink()

    gene_count = sum(1 for _ in universe_txt.open())
    print(
        f"   Homotypic done — {nummotifs} motifs, {gene_count} genes "
        f"in universe."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
