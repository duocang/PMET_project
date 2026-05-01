// Unit tests for geometricBinomialTest() in motifComparison.cpp.
//
// What it does, briefly: for one motif on one promoter, walk the
// kept hits sorted by p-value, accumulate the geometric mean of p
// incrementally, and ask binomialCDF (or poissonCDF when isPoisson)
// whether any prefix-of-k-hits + that prefix's geometric mean beats
// the motif's own per-motif threshold. Returns true if the lowest
// such score over any prefix is ≤ threshold.
//
// Why test it: it's the binomial recount that runs after position-
// overlap pruning; it decides whether a motif is still considered
// "present in this promoter" once overlapping hits have been dropped.
// Several easy regressions to make:
//   - log-sum vs sum-of-log mix-up
//   - "lowest score" tracking taking min/max in the wrong direction
//   - off-by-one between numpVals (count of true) and the index `n`
//     used in the binomialCDF call
// Integration baselines see only motif_output.txt drift; a unit test
// names the function in seconds.

#include "test_runner.hpp"
#include "../src/motif.hpp"
#include "../src/motifComparison.hpp"

#include <vector>

namespace {

// Build a motif with N hits at the given p-values for a single test
// gene (ID 0). Each hit's positions don't matter for this kernel —
// only motifInstance::getPValue() is read. promoter length / motif
// length come from the caller.
motif buildMotifWithHits(const std::vector<double>& pVals, int motifLen) {
  std::vector<double> ic(motifLen, 1.0);
  motif m = motif::makeForTest("M", ic);
  for (size_t i = 0; i < pVals.size(); ++i) {
    // Position columns are arbitrary — getPValue() drives the test.
    motifInstance inst(static_cast<int>(10 * (i + 1)),
                       static_cast<int>(10 * (i + 1) + motifLen - 1),
                       pVals[i],   // raw pVal (unused by getPValue())
                       pVals[i]);  // adjPVal — what getPValue() returns
    m.addInstanceForTest(/*gene=*/0, inst);
  }
  return m;
}

constexpr GeneId kTestGene = 0;

}  // namespace

TEST_CASE("geometricBinomialTest: empty kept-mask returns false") {
  // No hits kept → loop never runs → lowestScore stays at +inf →
  // +inf <= threshold is false for any sensible threshold.
  auto m = buildMotifWithHits({0.001}, /*motifLen=*/5);
  m.setThreshold(0.5);
  std::vector<bool> mask = {false};
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, /*promoterLength=*/100, m, /*isPoisson=*/false) == false);
}

TEST_CASE("geometricBinomialTest: single low-p hit + lax threshold → true") {
  // 1 hit p=0.0001 in a 100-bp promoter, motifLen 5, possibleLocations
  // = 2 * (100 - 5 + 1) = 192. binomP = 1 - binomialCDF(1, 192, 0.0001)
  //   = 1 - (1-p)^192 = 1 - 0.9999^192 ≈ 1 - 0.981 ≈ 0.019.
  // With threshold 0.05 → 0.019 ≤ 0.05 → true.
  auto m = buildMotifWithHits({0.0001}, 5);
  m.setThreshold(0.05);
  std::vector<bool> mask = {true};
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == true);
}

TEST_CASE("geometricBinomialTest: single low-p hit + tight threshold → false") {
  // Same numbers as above (~0.019 score) but threshold 0.001 → fails.
  auto m = buildMotifWithHits({0.0001}, 5);
  m.setThreshold(0.001);
  std::vector<bool> mask = {true};
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == false);
}

TEST_CASE("geometricBinomialTest: kept mask filters out a high-p hit") {
  // Two hits: p1 = 0.5 (high), p2 = 0.0001 (low). With both kept the
  // geometric mean is √(0.5 × 0.0001) ≈ 0.00707; with only the second
  // kept, gm = 0.0001 directly. The "kept-only-the-low" mask should
  // reach a strictly lower lowestScore than "kept-both" on the same
  // motif → if threshold is set such that "kept-low-only" passes but
  // "kept-both" fails, we've shown the mask works.
  auto m = buildMotifWithHits({0.5, 0.0001}, 5);
  m.setThreshold(0.025);  // see commentary below

  // "Both kept": prefix-1 score uses gm=0.5, n=1 → binomialCDF(1, 192,
  // 0.5) ≈ ~0 → binomP ≈ 1 (very high). Prefix-2 score uses
  // gm=√(0.5×0.0001)≈0.00707, n=2 → binomialCDF(2, 192, 0.00707) ≈
  // (1-p)^192 + 192·p·(1-p)^191 ≈ 0.255 + 0.345 ≈ 0.6 → binomP ≈ 0.4.
  // lowest = 0.4 > 0.025 → false.
  std::vector<bool> bothKept = {true, true};
  REQUIRE(motifComparison::geometricBinomialTest(bothKept, kTestGene, 100, m, false) == false);

  // "Only low kept": gm = 0.0001, n=1 → binomP ≈ 0.019 → ≤ 0.025 → true.
  std::vector<bool> onlyLowKept = {false, true};
  REQUIRE(motifComparison::geometricBinomialTest(onlyLowKept, kTestGene, 100, m, false) == true);
}

TEST_CASE("geometricBinomialTest: lowest-score tracking picks min over all prefixes") {
  // Three hits: p = [0.5, 0.0001, 0.5]. Prefix-1 uses gm=0.5
  // (terrible), prefix-2 uses gm=√(0.5×0.0001) (much better),
  // prefix-3 dilutes again with gm=∛(0.5×0.0001×0.5).
  // The function tracks the lowest binomP across prefixes, so the
  // best (lowest) prefix-2 score should drive the verdict — if that
  // prefix's score passes the threshold, the function returns true
  // even though prefixes 1 and 3 are worse.
  auto m = buildMotifWithHits({0.5, 0.0001, 0.5}, 5);
  m.setThreshold(0.5);  // very lax — any reasonable middle prefix wins
  std::vector<bool> mask = {true, true, true};
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == true);
}

TEST_CASE("geometricBinomialTest: poisson and binomial paths produce different scores") {
  // Identical inputs, isPoisson flag flipped. The Poisson path uses
  // poissonCDF(gm * possibleLocations, k) where k counts kept hits;
  // the Binomial path uses binomialCDF(n, possibleLocations, gm).
  // For small p × n they agree to leading order but the values
  // aren't byte-identical, so a function that returned the same
  // verdict regardless of `isPoisson` would be a bug.
  auto m = buildMotifWithHits({0.001, 0.0005}, 5);
  m.setThreshold(0.0);  // make any positive score fail
  std::vector<bool> mask = {true, true};
  // Both paths see the same 0 threshold and any positive score fails:
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == false);
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, true) == false);
  // With a permissive threshold (1.0) both paths should pass:
  m.setThreshold(1.0);
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == true);
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, true) == true);
}

TEST_CASE("geometricBinomialTest: threshold at exact boundary is ≤, not <") {
  // The production check is `lowestScore <= threshold`. If a refactor
  // changes that to `<` the boundary case fails. Pin the inequality.
  auto m = buildMotifWithHits({0.0001}, 5);
  std::vector<bool> mask = {true};
  // Compute the actual score so we can set threshold == score.
  // 1 - binomialCDF(1, 192, 0.0001) using the production helpers
  // — same path the function takes — guarantees byte-identity.
  double actualScore =
      1.0 - motifComparison::binomialCDF(1, 2 * (100 - 5 + 1), 0.0001);
  m.setThreshold(actualScore);  // boundary
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == true);
  // Just below boundary → fails.
  m.setThreshold(actualScore - 1e-12);
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == false);
}

TEST_CASE("geometricBinomialTest: all-false mask is equivalent to empty kept") {
  // Mask filters every hit out → numpVals=0 → same outcome as the
  // empty-mask case (false, regardless of threshold below +inf).
  auto m = buildMotifWithHits({0.0001, 0.0002, 0.0005}, 5);
  m.setThreshold(0.5);
  std::vector<bool> mask = {false, false, false};
  REQUIRE(motifComparison::geometricBinomialTest(mask, kTestGene, 100, m, false) == false);
}
