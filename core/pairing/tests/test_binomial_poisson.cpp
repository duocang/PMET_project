// Unit tests for binomialCDF() and poissonCDF() in motifComparison.cpp.
//
// What they do:
// - binomialCDF(k, n, p) computes Σ_{i=0}^{k-1} C(n,i) p^i (1-p)^(n-i),
//   i.e. the strict-less-than CDF of Binomial(n, p) at k. (Note the
//   half-open interval — this is the loop's `for (k = 0; k < numPVals)`
//   convention, not the standard P(X ≤ k).) Used by geometricBinomialTest
//   to score one motif on one promoter as "this many hits or more is
//   below the binomial threshold".
// - poissonCDF(lambda, k) computes Σ_{i=0}^{k} (lambda^i / i!) e^{-lambda},
//   the proper P(X ≤ k) for Poisson(lambda). Alternative scoring
//   model used when -x 1 is passed.
//
// Why a unit test: these are the numerical floor under every p-value
// PMET reports. A subtle change in summation order or log-space
// handling could nudge p-values by enough to flip BH significance for
// borderline pairs, and integration baselines would only flag the
// drift as a sha mismatch — naming the kernel takes a unit test.

#include "test_runner.hpp"
#include "../src/motifComparison.hpp"

#include <cmath>

namespace {

// Reference binomial CDF — sums P(X = i) for i in [0, k) using
// exp(lgamma(...)) to avoid overflow on large n. Used as the oracle.
double binomialCdfReference(long k, long n, double p) {
  double cdf = 0.0;
  for (long i = 0; i < k; ++i) {
    double logChoose = std::lgamma((double)n + 1) -
                       std::lgamma((double)i + 1) -
                       std::lgamma((double)(n - i) + 1);
    cdf += std::exp(logChoose + i * std::log(p) + (n - i) * std::log(1 - p));
  }
  return cdf;
}

// Reference Poisson CDF up to and including k.
double poissonCdfReference(double lambda, int k) {
  double cdf = 0.0;
  for (int i = 0; i <= k; ++i) {
    double logPmf = i * std::log(lambda) - std::lgamma((double)i + 1) - lambda;
    cdf += std::exp(logPmf);
  }
  return cdf;
}

}  // namespace

TEST_CASE("binomialCDF: k=0 returns 0 (empty sum, correct boundary)") {
  // No terms summed → 0. This is the half-open convention; standard
  // P(X ≤ -1) would be 0 too, just for a different reason.
  REQUIRE_NEAR(motifComparison::binomialCDF(0, 100, 0.5), 0.0, 1e-15);
}

TEST_CASE("binomialCDF: k=n+1 returns 1 (full distribution mass)") {
  // Σ_{i=0}^{n} C(n,i) p^i (1-p)^(n-i) = (p + (1-p))^n = 1.
  REQUIRE_NEAR(motifComparison::binomialCDF(11, 10, 0.3), 1.0, 1e-12);
}

TEST_CASE("binomialCDF: hand-computed n=4, p=0.5, k=3") {
  // Σ_{i=0,1,2} C(4,i) × 0.5^4 = (1+4+6) / 16 = 11/16 = 0.6875.
  REQUIRE_NEAR(motifComparison::binomialCDF(3, 4, 0.5), 0.6875, 1e-12);
}

TEST_CASE("binomialCDF: matches lgamma reference on a sweep") {
  // 4 representative (k, n, p) combos covering small n, moderate n,
  // skewed p, symmetric p. Reference uses lgamma so it stays accurate
  // for n where direct factorial would overflow.
  struct Case { long k; long n; double p; };
  Case cases[] = {
      {3, 10, 0.5},
      {1, 20, 0.1},
      {15, 50, 0.4},
      {7, 100, 0.05},
  };
  for (const auto& c : cases) {
    double actual = motifComparison::binomialCDF(c.k, c.n, c.p);
    double expected = binomialCdfReference(c.k, c.n, c.p);
    REQUIRE_NEAR(actual, expected, 1e-10);
  }
}

TEST_CASE("binomialCDF: monotone increasing in k (each term is non-negative)") {
  // Sanity invariant: adding more terms can never decrease the sum
  // (every binomial pmf entry is ≥ 0). A regression that flipped a
  // sign somewhere would violate this.
  double prev = 0.0;
  for (long k = 0; k <= 20; ++k) {
    double cur = motifComparison::binomialCDF(k, 20, 0.4);
    REQUIRE(cur + 1e-15 >= prev);
    prev = cur;
  }
}

TEST_CASE("poissonCDF: lambda=0 collapses to point mass at 0") {
  // Poisson(0) puts all mass at i=0, so P(X ≤ 0) = 1 and P(X ≤ k>0) = 1.
  REQUIRE_NEAR(motifComparison::poissonCDF(0.0, 0), 1.0, 1e-12);
  REQUIRE_NEAR(motifComparison::poissonCDF(0.0, 5), 1.0, 1e-12);
}

TEST_CASE("poissonCDF: lambda=1, k=0 → exp(-1)") {
  // P(X = 0) for Poisson(1) is exp(-1). The CDF up to k=0 is just that.
  REQUIRE_NEAR(motifComparison::poissonCDF(1.0, 0), std::exp(-1.0), 1e-12);
}

TEST_CASE("poissonCDF: lambda=2, k=2 → e^-2 × (1 + 2 + 2) = 5/e^2") {
  // Hand-computable: Σ_{i=0}^{2} (2^i / i!) e^{-2}
  //               = (1 + 2 + 2) × e^{-2} = 5 × e^{-2} ≈ 0.6766764.
  REQUIRE_NEAR(motifComparison::poissonCDF(2.0, 2), 5.0 * std::exp(-2.0), 1e-12);
}

TEST_CASE("poissonCDF: matches lgamma reference on a sweep") {
  struct Case { double lambda; int k; };
  Case cases[] = {
      {0.5, 2}, {1.0, 5}, {3.7, 4}, {10.0, 12}, {25.0, 20},
  };
  for (const auto& c : cases) {
    double actual = motifComparison::poissonCDF(c.lambda, c.k);
    double expected = poissonCdfReference(c.lambda, c.k);
    REQUIRE_NEAR(actual, expected, 1e-10);
  }
}

TEST_CASE("poissonCDF: large k floors the CDF at 1 (within tolerance)") {
  // For lambda=5, P(X ≤ 50) is essentially 1.0. Any value > 1 + tol
  // would indicate a numerical instability worth investigating.
  double cdf = motifComparison::poissonCDF(5.0, 50);
  REQUIRE(cdf <= 1.0 + 1e-9);
  REQUIRE(cdf >= 1.0 - 1e-9);
}
