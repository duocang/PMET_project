// Unit tests for motifComparison::colocTest().
//
// What it does: given the genes that contain BOTH motifs across the
// universe, plus the user's cluster, compute the right-tail
// hypergeometric p-value
//
//     P(X ≥ k) where X ~ Hypergeom(N, K, n)
//
// with
//     N = universeSize
//     K = |genesInUniverseWithBothMotifs|
//     n = |genesInCluster|
//     k = |intersection of those two|
//
// The implementation does this in log-space using a precomputed
// `logf` factorial table for numerical stability.
//
// Why this is the highest-value unit test: this is *the* p-value
// PMET reports for every (cluster, motif1, motif2) triple in
// motif_output.txt. A bug here pollutes every number a user sees.
// Integration baselines would catch the SHA drift but pinpointing
// the cause means re-deriving the math; a 5-line unit test names
// it instantly.

#include "test_runner.hpp"
#include "../src/motif.hpp"
#include "../src/motifComparison.hpp"

#include <cmath>
#include <vector>

namespace {

// Reference: hypergeometric right-tail probability P(X >= k) using
// lgamma — same formula but written for clarity, not stability.
double hypergeomTailReference(long N, long K, long n, long k) {
  auto lf = [](long x) { return std::lgamma(static_cast<double>(x) + 1.0); };  // log(x!)
  // log C(N, n)
  double logChooseNn = lf(N) - lf(n) - lf(N - n);

  double sum = 0.0;
  long maxH = std::min(n, K);
  for (long h = k; h <= maxH; ++h) {
    if (N - K - n + h < 0) continue;  // term is zero (binomial coefficient zero)
    double logTerm = (lf(K) - lf(h) - lf(K - h)) +
                     (lf(N - K) - lf(n - h) - lf(N - K - n + h)) - logChooseNn;
    sum += std::exp(logTerm);
  }
  return sum;
}

// Helper: spin up a fresh motifComparison with logf table sized for N,
// pre-populated with universeGenes (sorted), reset to a known pval.
motifComparison makeComp(long N, std::vector<GeneId> universeGenes) {
  motifComparison mc;
  mc.buildLogfTable(N);
  mc.recordSkippedPair();  // sets pval=1.0, clears state to a known baseline
  mc.setUniverseGenesForTest(std::move(universeGenes));
  return mc;
}

}  // namespace

TEST_CASE("colocTest: empty universe genes → no-op (pval unchanged)") {
  auto mc = makeComp(/*N=*/10, /*universe=*/{});
  // recordSkippedPair set pval to 1.0 — colocTest's no-op early-return
  // should leave it there.
  std::vector<GeneId> cluster = {1, 2, 3};
  mc.colocTest(/*N=*/10, /*ICthreshold=*/0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 1.0, 1e-12);
}

TEST_CASE("colocTest: empty cluster → no-op (pval unchanged)") {
  auto mc = makeComp(10, {1, 2, 3, 4});
  std::vector<GeneId> cluster;
  mc.colocTest(10, 0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 1.0, 1e-12);
}

TEST_CASE("colocTest: universeSize 0 → no-op") {
  auto mc = makeComp(10, {1, 2, 3});  // logf table still sized for tests
  std::vector<GeneId> cluster = {1, 2};
  mc.colocTest(/*N=*/0, 0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 1.0, 1e-12);
}

TEST_CASE("colocTest: zero intersection between universe + cluster → no-op") {
  // K = {1,2,3,4} but cluster = {7,8,9} — nothing in common.
  // colocTest's set_intersection returns empty → return without
  // updating pval.
  auto mc = makeComp(10, {1, 2, 3, 4});
  std::vector<GeneId> cluster = {7, 8, 9};
  mc.colocTest(10, 0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 1.0, 1e-12);
}

TEST_CASE("colocTest: hand-computed N=10, K=4, n=4, k=3 → 25/210") {
  // P(X >= 3) for Hypergeom(N=10, K=4, n=4)
  //   = P(X=3) + P(X=4)
  //   = C(4,3)*C(6,1)/C(10,4) + C(4,4)*C(6,0)/C(10,4)
  //   = (4 * 6 + 1 * 1) / 210
  //   = 25/210 ≈ 0.1190476...
  auto mc = makeComp(10, {1, 2, 3, 4});  // K=4
  std::vector<GeneId> cluster = {1, 2, 3, 5};  // n=4, intersection={1,2,3} → k=3
  mc.colocTest(10, 0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 25.0 / 210.0, 1e-10);
}

TEST_CASE("colocTest: maximum overlap (k = min(n, K)) → smallest p-value") {
  // Same N, K, n. Cluster ⊆ universe → k = n = 4.
  // P(X >= 4) for Hypergeom(N=10, K=4, n=4) = P(X=4) = 1/210 ≈ 0.00476.
  auto mc = makeComp(10, {1, 2, 3, 4});
  std::vector<GeneId> cluster = {1, 2, 3, 4};  // entirely inside universe
  mc.colocTest(10, 0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 1.0 / 210.0, 1e-12);
}

TEST_CASE("colocTest: minimum overlap (k = 1) → largest p-value of any non-trivial case") {
  // Cluster shares exactly one gene with the universe.
  // P(X >= 1) for Hypergeom(N=10, K=4, n=4)
  //   = 1 - P(X=0)
  //   = 1 - C(4,0)*C(6,4)/C(10,4)
  //   = 1 - 15/210
  //   = 195/210 ≈ 0.9286
  auto mc = makeComp(10, {1, 2, 3, 4});
  std::vector<GeneId> cluster = {1, 7, 8, 9};  // intersection = {1}
  mc.colocTest(10, 0.0, "c", cluster);
  REQUIRE_NEAR(mc.getpValue(), 195.0 / 210.0, 1e-10);
}

TEST_CASE("colocTest: matches lgamma reference on a sweep") {
  struct Case { long N, K_size, n_size, k_size; };
  // (N, K, n, k=size of intersection). For each, build a universe of
  // K consecutive ids, a cluster of n ids whose first k overlap with
  // the universe, then verify the production p-value matches the
  // lgamma reference within tight tolerance.
  Case cases[] = {
      {15, 6, 5, 2},
      {20, 8, 7, 4},
      {25, 10, 12, 5},
      {18, 4, 9, 3},
  };
  for (const auto& c : cases) {
    std::vector<GeneId> universe;
    for (long i = 0; i < c.K_size; ++i) universe.push_back((GeneId)(100 + i));
    std::vector<GeneId> cluster;
    // First k from universe → forms the intersection
    for (long i = 0; i < c.k_size; ++i) cluster.push_back((GeneId)(100 + i));
    // Remaining n - k from outside the universe
    for (long i = 0; i < c.n_size - c.k_size; ++i) cluster.push_back((GeneId)(900 + i));

    auto mc = makeComp(c.N, universe);
    mc.colocTest(c.N, 0.0, "c", cluster);
    double actual = mc.getpValue();
    double expected = hypergeomTailReference(c.N, c.K_size, c.n_size, c.k_size);
    REQUIRE_NEAR(actual, expected, 1e-10);
  }
}

TEST_CASE("colocTest: pval ∈ [0, 1] on every legitimate input") {
  // Sanity invariant: hypergeometric tail probabilities are always
  // in [0, 1]. A precision bug that lets `exp(amax + log(aSum))`
  // slip past 1.0 would be a real regression.
  std::vector<GeneId> universe = {1, 2, 3, 4, 5};
  std::vector<GeneId> cluster = {1, 2, 6, 7, 8};  // intersection = {1, 2}
  auto mc = makeComp(20, universe);
  mc.colocTest(20, 0.0, "c", cluster);
  double p = mc.getpValue();
  REQUIRE(p >= 0.0);
  REQUIRE(p <= 1.0 + 1e-12);  // tiny tolerance for floating-point round-up
}

TEST_CASE("colocTest: increasing k strictly decreases p-value (more overlap → more significant)") {
  // Same N, K, n. As k goes up, the right-tail P(X≥k) shrinks
  // monotonically. Pin that ordering — it's a property test that
  // catches sign flips or sum-bound off-by-ones.
  std::vector<GeneId> universe;
  for (int i = 0; i < 5; ++i) universe.push_back(i);  // K=5
  // Cluster of size 5 with k = 1, 2, 3, 4, 5 (intersection size).
  double prev = 1.0 + 1e-9;
  for (int k = 1; k <= 5; ++k) {
    std::vector<GeneId> cluster;
    for (int i = 0; i < k; ++i) cluster.push_back(i);  // overlap with universe
    for (int i = 0; i < 5 - k; ++i) cluster.push_back(100 + i);  // outside universe
    auto mc = makeComp(20, universe);
    mc.colocTest(20, 0.0, "c", cluster);
    double p = mc.getpValue();
    REQUIRE(p < prev);
    prev = p;
  }
}
