#!/usr/bin/env python3
"""Collapse per-interval PMETBN01 fimohits to per-gene entries.

Element pipelines (06_elements_longest.sh / 07_elements_merged.sh) tag each
isoform fragment with __GENE__N to keep them separable through FIMO. After
indexing, hits must be folded back so pairing_parallel sees one row per (gene,
motif) — this script does that fold in place on the binary fimohits/.

Behaviour matches the old text-format awk pipeline that step 9 of
_pmet_index_element.sh used to run:

  for each motif:
    read fimohits/<motif>.bin
    for each hit:
      strip __ prefix and __<digits> suffix from sequence name (gene <- interval)
    group by gene
    sort hits within each gene by p-value ascending
    keep top maxk hits per gene whose p-value is below the motif's threshold
    re-encode as PMETBN01 binary in place

The PMETBN01 layout is documented in
core/indexing/src/pmet_index/pmet-fimo-binary.h.

Usage:
  python3 collapse_element_fimohits.py <indexing_dir> <maxk>

<indexing_dir> must contain:
  fimohits/<motif>.bin           per-motif binary hits (input, rewritten in place)
  binomial_thresholds.txt        TSV: <motif><TAB><threshold>[...]   (read-only)
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Format constants (mirror pmet-fimo-binary.h)
# ---------------------------------------------------------------------------
MAGIC = b"PMETBN01"
HEADER_FMT = "<8sIIII"          # magic, num_hits, name_pool_size, motif_name_len, reserved
HEADER_SIZE = struct.calcsize(HEADER_FMT)        # 24
HIT_FMT = "<IIIB3sdd"           # seq_offset, start, stop, strand, _pad[3], score, pVal
HIT_SIZE = struct.calcsize(HIT_FMT)              # 32

# ---------------------------------------------------------------------------
# Strip __GENE__N -> GENE (matches step 9's awk: sub(/^__/,"") + sub(/__[0-9]+$/,""))
# ---------------------------------------------------------------------------
_LEADING_UU = re.compile(r"^__")
_TRAILING_INTERVAL = re.compile(r"__\d+$")


def gene_from_interval(name: str) -> str:
    name = _LEADING_UU.sub("", name)
    name = _TRAILING_INTERVAL.sub("", name)
    return name


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def read_motif_bin(path: Path) -> tuple[str, list[tuple[str, int, int, int, float, float]]]:
    """Decode a PMETBN01 file. Returns (motif_name, [(seq_name, start, stop, strand, score, pval), ...])."""
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"{path}: file shorter than header")

    magic, num_hits, pool_size, name_len, reserved = struct.unpack_from(HEADER_FMT, raw, 0)
    if magic != MAGIC:
        raise ValueError(f"{path}: bad magic {magic!r}, expected {MAGIC!r}")
    if reserved != 0:
        raise ValueError(f"{path}: reserved field is {reserved}, expected 0")

    off = HEADER_SIZE
    motif_name = raw[off:off + name_len].decode("ascii")
    off += name_len

    pool = raw[off:off + pool_size]
    off += pool_size

    expected = HEADER_SIZE + name_len + pool_size + num_hits * HIT_SIZE
    if len(raw) != expected:
        raise ValueError(f"{path}: file size {len(raw)} != expected {expected}")

    # Pre-index NUL-terminated names in the pool by start offset for O(1) lookup.
    # Each name owns the byte range [start, NUL).
    name_at: dict[int, str] = {}
    start = 0
    for i, b in enumerate(pool):
        if b == 0:
            name_at[start] = pool[start:i].decode("ascii")
            start = i + 1

    hits = []
    for k in range(num_hits):
        seq_off, sp, ep, strand, _pad, score, pval = struct.unpack_from(HIT_FMT, raw, off)
        off += HIT_SIZE
        seq_name = name_at.get(seq_off)
        if seq_name is None:
            raise ValueError(f"{path}: hit {k} seq offset {seq_off} not at a name boundary")
        hits.append((seq_name, sp, ep, strand, score, pval))

    return motif_name, hits


def write_motif_bin(path: Path, motif_name: str,
                    hits: list[tuple[str, int, int, int, float, float]]) -> None:
    """Encode hits as PMETBN01.

    Sequence names are written into the pool in first-appearance order so two
    runs over the same input produce byte-identical files.
    """
    motif_bytes = motif_name.encode("ascii")

    seq_offset_of: dict[str, int] = {}
    pool = bytearray()
    for seq_name, *_ in hits:
        if seq_name not in seq_offset_of:
            seq_offset_of[seq_name] = len(pool)
            pool.extend(seq_name.encode("ascii"))
            pool.append(0)

    header = struct.pack(HEADER_FMT,
                        MAGIC, len(hits), len(pool), len(motif_bytes), 0)
    body = bytearray()
    for seq_name, sp, ep, strand, score, pval in hits:
        body.extend(struct.pack(HIT_FMT,
                                seq_offset_of[seq_name],
                                sp, ep, strand, b"\x00\x00\x00",
                                score, pval))

    with path.open("wb") as fh:
        fh.write(header)
        fh.write(motif_bytes)
        fh.write(bytes(pool))
        fh.write(bytes(body))


# ---------------------------------------------------------------------------
# Collapse
# ---------------------------------------------------------------------------
def collapse_one(path: Path, maxk: int, threshold: float) -> tuple[int, int]:
    """Rewrite path in place with per-gene top-maxk filter. Returns (in_hits, out_hits).

    The motif_name written back to disk is upper-cased to match the
    convention used in IC.txt and the (re-normalized) binomial_thresholds.txt.
    pairing_parallel uses the .bin's internal motif_name (not the filename)
    to look up these two files, so the cases must agree.
    """
    motif_name, hits = read_motif_bin(path)
    in_count = len(hits)

    # Group hits by gene (stripped sequence name). Preserve the order of
    # first gene appearance so output ordering is deterministic and matches
    # what awk -k2,2 -k7,7g would produce after the strip.
    by_gene: dict[str, list[tuple[str, int, int, int, float, float]]] = {}
    gene_order: list[str] = []
    for hit in hits:
        seq_name = hit[0]
        gene = gene_from_interval(seq_name)
        # Rewrite sequence name in the kept hit so the output references the
        # collapsed gene, not the per-interval tag.
        new_hit = (gene,) + hit[1:]
        if gene not in by_gene:
            by_gene[gene] = []
            gene_order.append(gene)
        by_gene[gene].append(new_hit)

    kept: list[tuple[str, int, int, int, float, float]] = []
    for gene in gene_order:
        # Sort by p-value ascending (column 7 in the old text format).
        # Stable secondary sort key isn't needed — duplicates are rare and the
        # original awk pipeline didn't promise any.
        gene_hits = sorted(by_gene[gene], key=lambda h: h[5])
        for h in gene_hits[:maxk]:
            if h[5] < threshold:
                kept.append(h)
            # Once we hit one above threshold we could short-circuit since
            # we're iterating in ascending order, but maxk is also a cap —
            # cleaner to just check both and let the slice handle the limit.

    write_motif_bin(path, motif_name.upper(), kept)
    return in_count, len(kept)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <indexing_dir> <maxk>", file=sys.stderr)
        return 2

    indexing_dir = Path(argv[1])
    try:
        maxk = int(argv[2])
    except ValueError:
        print(f"maxk must be an integer, got {argv[2]!r}", file=sys.stderr)
        return 2

    fimohits_dir = indexing_dir / "fimohits"
    thresholds_path = indexing_dir / "binomial_thresholds.txt"
    if not fimohits_dir.is_dir():
        print(f"{fimohits_dir} not found", file=sys.stderr)
        return 1
    if not thresholds_path.is_file():
        print(f"{thresholds_path} not found", file=sys.stderr)
        return 1

    # Parse thresholds: <motif>\t<threshold>[\t...]
    # Note on case: indexing_fimo_fused preserves MEME's original motif-id
    # case in binomial_thresholds.txt, but calculateICfrommeme uppercases
    # them in IC.txt and the fimohits filenames also end up uppercase
    # (HFS+ case folding / writer behaviour). pairing_parallel and
    # check_homotypic_contract.py require all three sets to match exactly.
    # We work around the upstream inconsistency by:
    #   1. Looking up thresholds by the motif name STORED IN THE .bin file
    #      (which uses the binomial_thresholds case), and
    #   2. Rewriting binomial_thresholds.txt with uppercased motif ids at
    #      the end so it lines up with IC.txt + fimohits filenames.
    thresholds: dict[str, float] = {}
    raw_threshold_lines: list[str] = []
    for line in thresholds_path.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            thresholds[parts[0]] = float(parts[1])
        except ValueError:
            continue
        raw_threshold_lines.append(line)

    if not thresholds:
        print(f"{thresholds_path}: no usable rows (expected <motif>\\t<threshold>)", file=sys.stderr)
        return 1

    bin_files = sorted(fimohits_dir.glob("*.bin"))
    if not bin_files:
        print(f"{fimohits_dir}: no *.bin files", file=sys.stderr)
        return 1

    total_in = total_out = 0
    skipped: list[str] = []
    for path in bin_files:
        # Threshold key is the motif name STORED IN THE FILE, not the filename.
        # On case-insensitive filesystems (macOS HFS+ default) the on-disk name
        # may have been normalized to a different case than what the writer
        # emitted, so trusting path.stem mismatches binomial_thresholds.txt
        # (e.g. file 'AHL12_3ARY.bin' but threshold key 'AHL12_3ary').
        motif_name, _ = read_motif_bin(path)
        thr = thresholds.get(motif_name)
        if thr is None:
            skipped.append(motif_name)
            continue
        n_in, n_out = collapse_one(path, maxk, thr)
        total_in += n_in
        total_out += n_out

    print(f"  collapsed {len(bin_files) - len(skipped)} motif file(s): "
          f"{total_in} hits -> {total_out} after gene-level fold, top-{maxk} "
          f"per-gene, threshold filter")
    if skipped:
        print(f"  skipped {len(skipped)} motif(s) with no threshold entry: "
              f"{', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''}",
              file=sys.stderr)

    # Normalize binomial_thresholds.txt motif ids to upper-case so they
    # line up with IC.txt + fimohits filenames (see comment by `thresholds`
    # parsing above). Only the first whitespace-separated field is touched.
    normalized = []
    for line in raw_threshold_lines:
        head, _, rest = line.partition("\t")
        normalized.append(f"{head.upper()}\t{rest}" if rest else head.upper())
    thresholds_path.write_text("\n".join(normalized) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
