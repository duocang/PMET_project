# TODO

This file tracks open work. Closed items live in `git log` and
`docs/verification_log.md`. Format: short and current. If an entry has
been here longer than a quarter, either close it or delete it.

---

## Open

### Tests / fixtures

- [ ] Add a smoke test that exercises
  `scripts/python/check_homotypic_contract.py` with synthetic *bad*
  fixtures (missing motif file, mismatched motif sets, gene id outside
  universe, etc.) so the validator's failure paths have a regression
  guard. Currently only the success path is covered indirectly through
  pipeline runs.

### Pipeline / data hygiene

- [ ] **`scripts/archive/parse_genelines.py`** has been retired in
  favour of `gff3_to_gene_bed.py`. Pipeline/02 still uses
  `gff3_to_gene_bed.py --feature-regex '^gene$'` to keep its narrower
  filter (only canonical `gene` rows). If pipeline/02's gene set should
  ever be widened to match 03/05/06/07 (`gene$` regex), it would be a
  behaviour-changing commit — record the new baseline as EXPECTED
  CHANGE.
- [ ] **Background symmetry guard.** PMET (and the embedded FIMO) does
  double-stranded motif scanning, which only matches the original
  PMET implementation when the background is reverse-complement
  symmetric (`freq(A)=freq(T)`, `freq(C)=freq(G)`). MEME's
  `fasta-get-markov` produces a symmetric `promoters.bg` by default, so
  the current pipeline is correct. Add a defensive check in
  `scripts/python/check_homotypic_contract.py` that reads
  `promoters.bg` and rejects (or auto-symmetrises with a loud warning)
  bg files where `|f(A)-f(T)| > 1e-6` or `|f(C)-f(G)| > 1e-6`. Required
  before exposing `--bgfile` to user-supplied paths or replacing
  `fasta-get-markov` with a custom frequency counter.
- [ ] Investigate `02_benchmark_parameters.sh` cluster-stratified
  output schema. The script hard-codes 4 `tasks=(...)` and 7 lengths
  × 9 maxk × 1 topn = 252 combos; document the consumer side
  (downstream comparison scripts) or note that 02 is the consumer.

### Documentation

- [ ] `readme.md`: add a one-paragraph description of
  `scripts/indexing/` as the core homotypic-index engine for 04 / 06 /
  07 (03 / 05 use `scripts/python/run_homotypic.py` instead).

### Optional

- [ ] Migrate plotting from R to Python (plotnine + matplotlib).
  Evaluated 2026-04-26; deferred. Cost ~1–2 days; benefit is one less
  language dependency. Re-running every PNG baseline is mandatory if
  this happens (PNG bytes are renderer-specific).

---

## Conventions

- Refactors must be byte-identical against
  `scripts/tests/baselines/<NN>_baseline.hashes.txt`. Use
  `scripts/tests/run_with_verify.sh <NN> [<element>]` before committing.
- Naming: see `docs/naming_conventions.md`.
- Commit discipline: small, single-purpose commits with conventional prefixes.
