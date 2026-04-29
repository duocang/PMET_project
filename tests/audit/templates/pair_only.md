# pair_only — re-pair an existing homotypic index

<<RUN_HEADER>>

**Source:** [`pipeline/workflows/pair_only.sh`](../../pipeline/workflows/pair_only.sh)
&nbsp;&nbsp;**Used by:** CLI re-runs · web `promoters_pre` mode (`apps/pmet_backend/services/executor.py` SCRIPT_MAP)

## Purpose

Skip the expensive **homotypic indexing** stage and run only the
**heterotypic** pair-enrichment + heatmap stages against an index that
already exists on disk. Two real situations this serves:

1. **Re-pair the same index against a different gene list / IC threshold.**
   Indexing TAIR10 with the Franco-Zorrilla 113-motif set takes ~2 minutes
   wall and dominates the cost; pair_parallel against an already-indexed
   universe finishes in seconds. Iterating on the gene list (e.g. trying
   different cluster definitions) means re-pairing only.

2. **Web "Pre-computed Promoters" mode.** The species/motif-database
   indexes are built offline once (16 GB on disk for `data/indexing/`)
   and shipped to the server; user submissions only carry a gene list
   plus parameters. The backend dispatches that submission to this same
   `pair_only.sh` (see `apps/pmet_backend/services/executor.py`).

## Biological setup

A "homotypic index" is the cached output of motif scanning over a fixed
promoter universe (or interval set). For each motif `m`, the index
records every position in every promoter where `m` was found, along with:

- `binomial_thresholds.txt` — per-motif p-value cutoff such that only
  the top ≈`topn` hits across the universe survive (`--topn 5000` is
  the canonical choice).
- `IC.txt` — per-motif positional information content, used by
  pair_parallel as a sanity floor (skip motifs less informative than
  `-i <ic_threshold>`).
- `fimohits/<MOTIF>.{txt,bin}` — the per-motif hit list. Modern indexes
  produced by `index_fimo_fused` are PMETBN01 binary (`.bin`); older
  text-format indexes (`.txt`) are still accepted by `pair_parallel`,
  and the bundled `data/cli/pairing/demo` fixture uses text.
- `promoter_lengths.txt`, `universe.txt` — universe metadata.

The schema is defined in [`docs/methods/homotypic-contract.md`](../methods/homotypic-contract.md).

`pair_only` then asks, **for the user's gene list `G` against this
universe**: which motif pairs `(m1, m2)` co-occur in `G`'s promoters more
often than chance? The test is per-cluster (gene list rows have an
optional cluster label in column 1) and produces one row per
`(cluster, m1, m2)` triple in `motif_output.txt`.

## What the script does, step by step

| # | Stage | What runs | Why |
|---|---|---|---|
| 1 | Argument + binary preflight | locate `build/pair_parallel`, validate `-d` dir | Fail fast if the binary or index is missing — much clearer than pair_parallel's own missing-file errors |
| 2 | Index validation | check `<index>/{universe,promoter_lengths,binomial_thresholds,IC,fimohits/}.txt` | Ensures the supplied dir is a complete homotypic index. **Note**: the script intentionally does NOT invoke `check_homotypic_contract.py` here — the canonical demo `data/cli/pairing/demo` ships only 6 fimohits files for ~110 thresholds, which is valid for that fixture but would fail the strict contract |
| 3 | Gene-list filter | `grep -wFf universe.txt <gene_list>` → `genes_used_PMET.txt` + `genes_not_found.txt` | Word-boundary `-w` defends against substring collisions (e.g. AT1G01010 ⊂ AT1G010100). Records both kept and dropped genes for diagnostics |
| 4 | Heterotypic pair test | `build/pair_parallel -d <index> -g <kept_genes> -i <ic_thr> ...` | The actual binomial-vs-hypergeometric pair test. Produces per-thread `temp*.txt` shards |
| 5 | Shard aggregation | `cat temp*.txt > motif_output.txt` then `rm temp*.txt` | pair_parallel doesn't unify shards itself; the script does it |
| 6 | Heatmaps (optional) | three `Rscript pipeline/r/draw_heatmap.R` calls (All / Overlap-unique / Overlap-all) | Skipped silently with a warning if `Rscript` is absent |

## Run snapshot

This audit just ran:

```
<<COMMAND_DISPLAYED>>
```

into `<<OUT_DIR>>/`. Outputs landed at:

| File | Purpose |
|---|---|
| `<<OUT_DIR>>/motif_output.txt` | enriched motif pairs (one per `cluster, m1, m2`) |
| `<<OUT_DIR>>/genes_used_PMET.txt` | input genes that matched the universe |
| `<<OUT_DIR>>/genes_not_found.txt` | input genes dropped (universe miss) |
| `<<OUT_DIR>>/pmet.log` | pair_parallel's own log (per-thread progress) |
| `<<OUT_DIR>>/plot/` | optional heatmap PNGs (only if Rscript available) |

### Output preview

`motif_output.txt` first 3 rows:

```
<<MOTIF_OUTPUT_HEAD>>
```

Schema (tab-separated): `cluster ⟶ motif1 ⟶ motif2 ⟶ overlap_count ⟶
expected ⟶ p_value ⟶ p_adj ⟶ ...`. Higher rows = stronger
enrichment, lower p-values.

## Verification

<<OVERALL_VERDICT>>

<<CHECK_TABLE>>

### Reproducing this audit

```bash
python3 tests/audit/generate.py pair_only
```

The verification anchor `motif_output.txt` sha is captured against
`data/cli/pairing/demo` on this machine. It will only change if the fixture
itself changes (motif set or gene list). If pair_parallel's
implementation drifts (or its sort order does) the sha will differ —
that's exactly the regression signal this audit catches.
