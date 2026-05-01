# PMET Analysis

PMET (Paired Motif Enrichment Test) is a tool for identifying enriched motif pairs in genomic sequences.

## Motif Pair Enrichment Heatmap

![PMET motif pair enrichment heatmap](data/heatmap_overlap_unique.png)

This repository contains a visualization of enriched motif pairs across different gene clusters, generated using the PMET (Paired Motif Enrichment Test) tool. The heatmap above illustrates the enrichment patterns of motif pairs in various conditions and tissues, specifically focusing on cortex and epidermis with different treatment states denoted as "up" or "down".

Key Features:

- Gene clusters: Rows represent different gene clusters associated with several transcription factors.
- Motif pair enrichment: Colors represent the enrichment of motif pairs, with each color corresponding to a specific condition.
- Conditions: Cortex_flg22_up, Cortex_pep1_up, Epidermis_pep1_do, Cortex_pep1_do, Epidermis_flg22_up, Epidermis_pep1_up.
- Visualization details: The intensity and hue indicate enrichment strength, enabling quick assessment of which gene clusters are enriched under specific conditions.

This visualization serves as an effective tool for exploring the interactions between motifs under diverse biological contexts, facilitating a deeper understanding of gene regulation mechanisms in different tissues.

## Project Structure

```
.
├── run.sh                  # Interactive pipeline launcher
├── readme.md / TODO.md / LICENSE.md
├── data/                   # Input data (genome, motifs, gene lists)
├── build/                  # Compiled binaries (pmet, pmetParallel, fimo, etc.)
├── results/                # All run outputs (gitignored)
├── docs/                   # Method notes, diagrams, naming conventions, verification log
├── legacy/                 # Original C++ source code
└── scripts/
    ├── pipeline/           # Top-level pipeline entrypoints (00–08)
    ├── tests/              # Smoke + verifiers + fixtures + baselines
    ├── python/             # Python helpers (parse_*, build_*, check_*)
    ├── r/                  # R plotting helpers
    ├── lib/                # Shared bash helpers (colors, timer)
    ├── indexing/           # Homotypic indexing wrappers
    ├── gff3sort/           # Vendored GFF3 sorter
    ├── archive/            # Retired scripts
    └── temp/               # Local scratch (gitignored)
```

Naming rules: see [`docs/naming_conventions.md`](docs/naming_conventions.md).

## Quick Start

### 1. Check Requirements & Setup

```bash
bash run.sh                                        # interactive
# or
bash scripts/pipeline/00_requirements.sh           # direct
```

This will:

- Check for required tools (fimo, samtools, bedtools, parallel)
- Download TAIR10 genome and annotation if needed
- Clone and compile PMET binaries

### 2. Run Analysis Pipelines

Interactive launcher:

```bash
bash run.sh
```

| #  | Pipeline                       | Description                                             |
| -- | ------------------------------ | ------------------------------------------------------- |
| 00 | 00_requirements.sh             | Check system requirements and setup                     |
| 01 | 01_benchmark_cpu.sh            | Benchmark heterotypic analysis (single CPU vs parallel) |
| 02 | 02_benchmark_parameters.sh     | Benchmark PMET parameters on promoters                  |
| 03 | 03_promoter.sh                 | Run PMET on promoter regions                            |
| 04 | 04_intervals.sh                | Run PMET on genomic intervals (e.g., ATAC-seq peaks)    |
| 05 | 05_promoter_gap.sh             | Run PMET on promoters with a TSS-proximal gap           |
| 06 | 06_elements_longest.sh         | Run PMET on a genomic element, longest isoform per gene |
| 07 | 07_elements_merged.sh          | Run PMET on a genomic element, merged isoforms per gene |

Or run a pipeline directly and verify against the recorded baseline:

```bash
bash scripts/pipeline/03_promoter.sh
bash scripts/tests/verify_baseline.sh \
    results/03_promoter \
    scripts/tests/baselines/03_baseline.hashes.txt
```

### 3. Smoke and regression tests

```bash
bash scripts/tests/run_smoke.sh                    # < 30s, no TAIR10 needed
bash scripts/tests/run_with_verify.sh 03           # run pipeline + verify (helper)
```

## Requirements

The following tools are required:

- **fimo** (from MEME Suite) - Motif scanning
- **samtools** - FASTA indexing
- **bedtools** - Genomic interval operations
- **GNU parallel** - Parallel processing

Install via conda:

```bash
conda install -c bioconda meme samtools bedtools parallel
```

## License

See [LICENSE.md](LICENSE.md)
