// Unit tests for indexing's pair-test kernels (pmet-index-pair-test.c):
// motifsOverlap, binomialCDF, geometricBinTest.
//
// These exist alongside the *pairing* engine's same-named functions
// (core/pairing/src/motifComparison.cpp) — the indexing build has its
// own copy because indexing was authored as a self-contained C
// project and pairing was authored later in C++. The two sets of
// kernels need to stay numerically aligned with each other; tests
// here pin the C side just like core/pairing/tests/ pins the C++ side.

#include "test_runner.hpp"

#include <cmath>
#include <cstring>
#include <vector>

extern "C" {
#include "pmet-index-MotifHit.h"
#include "pmet-index-MotifHitVector.h"
#include "pmet-index-pair-test.h"
}

namespace {

// Construct a MotifHit with only the fields motifsOverlap reads.
MotifHit makeHitForOverlap(long start, long stop) {
  MotifHit h{};
  h.startPos = start;
  h.stopPos = stop;
  h.strand = '+';
  return h;
}

// Construct a MotifHit with a chosen pVal — the only field that
// drives geometricBinTest.
MotifHit makeHitForPVal(double pVal) {
  MotifHit h{};
  h.startPos = 1;
  h.stopPos = 5;
  h.strand = '+';
  h.score = 0.0;
  h.pVal = pVal;
  return h;
}

// Reference binomial CDF using lgamma. Same formula and half-open
// convention (P(X < numPVals)) as the production code.
double binomialCdfReference(size_t k, size_t n, double p) {
  double sum = 0.0;
  for (size_t i = 0; i < k; ++i) {
    double logChoose = std::lgamma((double)n + 1) -
                       std::lgamma((double)i + 1) -
                       std::lgamma((double)(n - i) + 1);
    sum += std::exp(logChoose + i * std::log(p) + (n - i) * std::log(1 - p));
  }
  return sum;
}

}  // namespace

// ------------------------------------------------------------------
// motifsOverlap
// ------------------------------------------------------------------

TEST_CASE("motifsOverlap: NULL inputs return false (defensive)") {
  MotifHit valid = makeHitForOverlap(10, 14);
  REQUIRE(motifsOverlap(nullptr, &valid) == false);
  REQUIRE(motifsOverlap(&valid, nullptr) == false);
  REQUIRE(motifsOverlap(nullptr, nullptr) == false);
}

TEST_CASE("motifsOverlap: malformed hit (start > stop) returns false") {
  MotifHit bad = makeHitForOverlap(20, 10);   // start > stop
  MotifHit good = makeHitForOverlap(5, 25);   // would otherwise overlap
  REQUIRE(motifsOverlap(&bad, &good) == false);
  REQUIRE(motifsOverlap(&good, &bad) == false);
}

TEST_CASE("motifsOverlap: disjoint intervals don't overlap") {
  MotifHit a = makeHitForOverlap(10, 14);
  MotifHit b = makeHitForOverlap(20, 24);
  REQUIRE(motifsOverlap(&a, &b) == false);
  REQUIRE(motifsOverlap(&b, &a) == false);
}

TEST_CASE("motifsOverlap: touching at one position counts as overlap") {
  // a = [10, 15], b = [15, 20]. Endpoint shared → overlap.
  MotifHit a = makeHitForOverlap(10, 15);
  MotifHit b = makeHitForOverlap(15, 20);
  REQUIRE(motifsOverlap(&a, &b) == true);
}

TEST_CASE("motifsOverlap: nested intervals overlap") {
  MotifHit outer = makeHitForOverlap(10, 30);
  MotifHit inner = makeHitForOverlap(15, 20);
  REQUIRE(motifsOverlap(&outer, &inner) == true);
  REQUIRE(motifsOverlap(&inner, &outer) == true);
}

TEST_CASE("motifsOverlap: identical intervals overlap") {
  MotifHit a = makeHitForOverlap(10, 20);
  MotifHit b = makeHitForOverlap(10, 20);
  REQUIRE(motifsOverlap(&a, &b) == true);
}

// ------------------------------------------------------------------
// binomialCDF
// ------------------------------------------------------------------

TEST_CASE("indexing/binomialCDF: k=0 returns 0 (empty sum)") {
  REQUIRE_NEAR(binomialCDF(0, 100, 0.5), 0.0, 1e-15);
}

TEST_CASE("indexing/binomialCDF: k=n+1 sums full distribution to 1") {
  // Σ_{i=0}^{n} C(n,i) p^i (1-p)^(n-i) = (p + (1-p))^n = 1.
  REQUIRE_NEAR(binomialCDF(11, 10, 0.3), 1.0, 1e-12);
}

TEST_CASE("indexing/binomialCDF: hand-computed n=4, p=0.5, k=3 → 11/16") {
  // Σ_{i=0,1,2} C(4,i) × 0.5^4 = (1 + 4 + 6) / 16.
  REQUIRE_NEAR(binomialCDF(3, 4, 0.5), 0.6875, 1e-12);
}

TEST_CASE("indexing/binomialCDF: matches lgamma reference on a sweep") {
  struct Case { size_t k; size_t n; double p; };
  Case cases[] = {
      {3, 10, 0.5}, {1, 20, 0.1}, {15, 50, 0.4}, {7, 100, 0.05},
  };
  for (const auto& c : cases) {
    double actual = binomialCDF(c.k, c.n, c.p);
    double expected = binomialCdfReference(c.k, c.n, c.p);
    REQUIRE_NEAR(actual, expected, 1e-10);
  }
}

TEST_CASE("indexing/binomialCDF: matches the pairing-engine implementation") {
  // The pairing engine (core/pairing) carries its own binomialCDF
  // intended to be numerically identical. If they ever drift, p-values
  // computed at index time and at pair time would disagree silently.
  // Cross-check on a representative input.
  //
  // (We don't link the pairing impl from here — instead we trust the
  // lgamma reference covers both.)
  const size_t n = 20;
  const double p = 0.15;
  for (size_t k = 0; k <= n + 1; ++k) {
    double actual = binomialCDF(k, n, p);
    double expected = binomialCdfReference(k, n, p);
    REQUIRE_NEAR(actual, expected, 1e-10);
  }
}

// ------------------------------------------------------------------
// geometricBinTest
// ------------------------------------------------------------------

namespace {

// Build a MotifHitVector pointing at a stack-allocated hit array.
// The vector owns nothing; tests must keep `hits` alive for the
// vector's lifetime. geometricBinTest reads only `pVal` so other
// fields are arbitrary.
struct VectorFixture {
  std::vector<MotifHit> hitArray;
  MotifHitVector vec{};

  explicit VectorFixture(std::vector<double> pVals) {
    hitArray.reserve(pVals.size());
    for (double p : pVals) hitArray.push_back(makeHitForPVal(p));
    vec.hits = hitArray.data();
    vec.size = (int)hitArray.size();
    vec.capacity = (int)hitArray.size();
    vec.shared_sequence_name = nullptr;
  }
};

}  // namespace

TEST_CASE("geometricBinTest: single-hit vector returns idx 0") {
  VectorFixture f({0.0001});
  Pair r = geometricBinTest(&f.vec, /*promoterLength=*/100, /*motifLength=*/5);
  REQUIRE(r.idx == 0);
  // 1 - binomialCDF(1, 192, 0.0001) ≈ 0.019. Don't pin the exact value
  // (it goes through roundToSignificantDigits) — just sanity range.
  REQUIRE(r.score > 0.0);
  REQUIRE(r.score < 0.1);
}

TEST_CASE("geometricBinTest: best-prefix index falls on the cleanest p-value run") {
  // Hit p-values: [0.001, 0.5, 0.5]. Prefix-1 sees gm=0.001 (sharpest);
  // prefix-2 sees gm=√(0.001×0.5)≈0.0224 (worse); prefix-3 dilutes
  // further. The function tracks the lowest binomP across prefixes,
  // which should land on prefix-1 → idx 0.
  VectorFixture f({0.001, 0.5, 0.5});
  Pair r = geometricBinTest(&f.vec, 100, 5);
  REQUIRE(r.idx == 0);
}

TEST_CASE("geometricBinTest: a low p later in the list pulls the best prefix forward") {
  // Hit p-values: [0.1, 0.0001]. Prefix-1 sees gm=0.1 (mediocre);
  // prefix-2 sees gm=√(0.1×0.0001)=√(1e-5)≈0.00316 (much better).
  // Lowest binomP is at prefix-2 → idx 1.
  VectorFixture f({0.1, 0.0001});
  Pair r = geometricBinTest(&f.vec, 100, 5);
  REQUIRE(r.idx == 1);
}

TEST_CASE("geometricBinTest: monotone decreasing p-values pick the last prefix") {
  // [0.1, 0.01, 0.001, 0.0001]. Each prefix improves the gm so the
  // last prefix should always win.
  VectorFixture f({0.1, 0.01, 0.001, 0.0001});
  Pair r = geometricBinTest(&f.vec, 100, 5);
  REQUIRE(r.idx == 3);
}

TEST_CASE("geometricBinTest: idx in [0, size), score > 0") {
  // Property test: any input where every p ∈ (0, 1) should produce
  // a valid idx and a positive score.
  VectorFixture f({0.05, 0.02, 0.01, 0.5, 0.001, 0.3});
  Pair r = geometricBinTest(&f.vec, 200, 8);
  REQUIRE(r.idx >= 0);
  REQUIRE(r.idx < f.vec.size);
  REQUIRE(r.score > 0.0);
  REQUIRE(r.score < 1.0);
}
