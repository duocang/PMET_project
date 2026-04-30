#!/usr/bin/env python3
"""Validate a homotypic output directory against the contract in
docs/contracts/homotypic.md.

Usage:
    python3 scripts/python/check_homotypic_contract.py <homotypic_dir>

Exit codes:
    0 - contract holds
    1 - one or more violations (printed to stderr)
    2 - usage error or missing directory

The check is fast (O(N gene IDs) memory) and is intended to run at the end
of every pipeline's homotypic stage. It does not parse the FIMO TSV beyond
column 2 (gene id), and does not attempt to validate p-values numerically;
those are downstream invariants enforced by the binaries.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REQUIRED_FILES = (
    "promoter_lengths.txt",
    "binomial_thresholds.txt",
    "IC.txt",
    "universe.txt",
)
REQUIRED_DIRS = ("fimohits",)


def fail(violations: list[str], message: str) -> None:
    violations.append(message)


def check_existence(root: Path, violations: list[str]) -> None:
    for f in REQUIRED_FILES:
        path = root / f
        if not path.is_file():
            fail(violations, f"missing required file: {path.relative_to(root)}")
        elif path.stat().st_size == 0:
            fail(violations, f"empty required file: {path.relative_to(root)}")
    for d in REQUIRED_DIRS:
        path = root / d
        if not path.is_dir():
            fail(violations, f"missing required directory: {path.relative_to(root)}/")


def parse_motifs_thresholds(path: Path, violations: list[str]) -> list[str]:
    """Return motifs in file order; check column count and uniqueness."""
    motifs: list[str] = []
    seen: set[str] = set()
    if not path.is_file():
        return motifs
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                fail(
                    violations,
                    f"{path.name}:{lineno}: expected ≥2 tab-separated cols, "
                    f"got {len(cols)}",
                )
                continue
            motif = cols[0]
            if motif in seen:
                fail(violations, f"{path.name}: duplicate motif '{motif}'")
            seen.add(motif)
            motifs.append(motif)
            try:
                float(cols[1])
            except ValueError:
                fail(
                    violations,
                    f"{path.name}:{lineno}: column 2 not a float ({cols[1]!r})",
                )
    return motifs


def parse_motifs_ic(path: Path, violations: list[str]) -> list[str]:
    motifs: list[str] = []
    seen: set[str] = set()
    if not path.is_file():
        return motifs
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split()
            if len(cols) < 2:
                fail(
                    violations,
                    f"{path.name}:{lineno}: expected ≥2 space-separated cols, "
                    f"got {len(cols)}",
                )
                continue
            motif = cols[0]
            if motif in seen:
                fail(violations, f"{path.name}: duplicate motif '{motif}'")
            seen.add(motif)
            motifs.append(motif)
            for i, val in enumerate(cols[1:], 2):
                try:
                    float(val)
                except ValueError:
                    fail(
                        violations,
                        f"{path.name}:{lineno}: column {i} not a float ({val!r})",
                    )
                    break
    return motifs


def parse_universe(path: Path, violations: list[str]) -> set[str]:
    genes: set[str] = set()
    if not path.is_file():
        return genes
    with path.open() as fh:
        seen_count: dict[str, int] = {}
        for lineno, line in enumerate(fh, 1):
            gene = line.strip()
            if not gene:
                continue
            seen_count[gene] = seen_count.get(gene, 0) + 1
            genes.add(gene)
        dups = [g for g, n in seen_count.items() if n > 1]
        if dups:
            fail(
                violations,
                f"{path.name}: {len(dups)} duplicate gene id(s); first: "
                f"{dups[:3]}",
            )
    return genes


def parse_promoter_lengths(
    path: Path, violations: list[str]
) -> set[str]:
    genes: set[str] = set()
    if not path.is_file():
        return genes
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                fail(
                    violations,
                    f"{path.name}:{lineno}: expected ≥2 tab-separated cols, "
                    f"got {len(cols)}",
                )
                continue
            gene = cols[0]
            if gene in genes:
                fail(violations, f"{path.name}: duplicate gene '{gene}'")
            genes.add(gene)
            try:
                length = int(cols[1])
                if length <= 0:
                    fail(
                        violations,
                        f"{path.name}:{lineno}: non-positive length {length}",
                    )
            except ValueError:
                fail(
                    violations,
                    f"{path.name}:{lineno}: column 2 not an int ({cols[1]!r})",
                )
    return genes


def check_fimohits_motifs(
    fimohits_dir: Path,
    expected_motifs: set[str],
    universe: set[str],
    violations: list[str],
) -> None:
    if not fimohits_dir.is_dir():
        return

    # Upstream index_fimo_fused emits .bin since PMET_project commit 8fa9b66
    # ("perf: add binary SoA fimohits format"); older builds still emit .txt.
    found_files: dict[str, Path] = {}
    for entry in sorted(fimohits_dir.iterdir()):
        if entry.is_file() and entry.suffix in (".txt", ".bin"):
            motif_name = entry.stem
            if motif_name in found_files:
                fail(
                    violations,
                    f"fimohits/: duplicate motif filename {entry.name}",
                )
            found_files[motif_name] = entry

    missing = expected_motifs - found_files.keys()
    extra = found_files.keys() - expected_motifs
    if missing:
        sample = sorted(missing)[:5]
        fail(
            violations,
            f"fimohits/: missing {len(missing)} motif file(s); first: {sample}",
        )
    if extra:
        sample = sorted(extra)[:5]
        fail(
            violations,
            f"fimohits/: {len(extra)} unexpected motif file(s); first: {sample}",
        )

    # Spot-check: gene ids in column 2 of each fimohits file ⊆ universe.
    # Bound the cost: read first 1000 hits per motif. A pipeline regression
    # almost always violates the invariant in the first few rows. Binary
    # fimohits (.bin) cannot be parsed as text — pair_parallel validates the
    # header magic on load, so we only check non-emptiness here.
    for motif, path in found_files.items():
        if path.stat().st_size == 0:
            fail(violations, f"fimohits/{path.name} is empty")
            continue
        if path.suffix == ".bin":
            continue
        with path.open() as fh:
            for lineno, line in enumerate(fh, 1):
                if lineno > 1000:
                    break
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 2:
                    continue
                gene = cols[1]
                if gene and gene not in universe:
                    fail(
                        violations,
                        f"fimohits/{path.name}:{lineno}: gene {gene!r} not "
                        f"in universe.txt",
                    )
                    break


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a homotypic output directory against "
        "docs/contracts/homotypic.md."
    )
    parser.add_argument("homotypic_dir", type=Path)
    args = parser.parse_args()

    root = args.homotypic_dir
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    violations: list[str] = []

    check_existence(root, violations)

    motifs_thr = parse_motifs_thresholds(root / "binomial_thresholds.txt", violations)
    motifs_ic = parse_motifs_ic(root / "IC.txt", violations)
    universe = parse_universe(root / "universe.txt", violations)
    prom_genes = parse_promoter_lengths(root / "promoter_lengths.txt", violations)

    if set(motifs_thr) != set(motifs_ic):
        only_thr = sorted(set(motifs_thr) - set(motifs_ic))[:5]
        only_ic = sorted(set(motifs_ic) - set(motifs_thr))[:5]
        violations.append(
            f"motif sets differ between binomial_thresholds.txt and IC.txt; "
            f"only-thr={only_thr} only-ic={only_ic}"
        )

    if not prom_genes.issubset(universe):
        missing = sorted(prom_genes - universe)[:5]
        violations.append(
            f"promoter_lengths.txt has {len(prom_genes - universe)} gene(s) "
            f"not in universe.txt; first: {missing}"
        )

    check_fimohits_motifs(
        root / "fimohits", set(motifs_thr), universe, violations
    )

    if violations:
        print(f"FAIL — {len(violations)} contract violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print(
        f"OK — homotypic contract holds "
        f"({len(motifs_thr)} motifs, {len(universe)} universe genes, "
        f"{len(prom_genes)} genes with promoter lengths)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
