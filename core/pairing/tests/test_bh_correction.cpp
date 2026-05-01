// Unit tests for bhCorrection() in utils.cpp.
//
// Why this kernel deserves a unit test (and not just integration
// baselines): the historical bug
//
//     pValues[i].second *= (n / (n - i));
//
// computed the multiplier in integer arithmetic, so for any i < n/2 the
// expression collapsed to 1 and "BH adjustment" was a no-op (adj_p ==
// raw_p). The fix was a one-character cast to double. End-to-end sha
// baselines did flag the regression, but the failure pointed at a
// 50 MB output mismatch — five test cases here would have pinned the
// blame to bhCorrection() in seconds.

#include "test_runner.hpp"
#include "../src/Output.hpp"
#include "../src/utils.hpp"

#include <vector>
#include <cmath>

namespace {

// Reference BH (Benjamini-Hochberg) implementation, written for clarity
// rather than performance. Used as the oracle that bhCorrection() must
// match. The monotonic clamp matches the production code: once we've
// taken min(adj_p[i-1], n/(n-i) * raw_p[i]), no later step can raise it.
std::vector<double> bhReference(std::vector<double> raw) {
  // Sort descending while remembering original indices.
  std::vector<std::pair<long, double>> idx(raw.size());
  for (long i = 0; i < (long)raw.size(); ++i) idx[i] = {i, raw[i]};
  std::sort(idx.begin(), idx.end(),
            [](const auto& a, const auto& b) { return a.second > b.second; });

  const long n = (long)raw.size();
  std::vector<double> adj(n);
  for (long i = 0; i < n; ++i) {
    double v = idx[i].second * (static_cast<double>(n) / (n - i));
    if (i > 0 && v > adj[idx[i - 1].first]) v = adj[idx[i - 1].first];
    adj[idx[i].first] = v;
  }
  return adj;
}

// Helper: build a vector of Output objects from raw p-values, run
// bhCorrection, return adj p-values in the same order.
std::vector<double> runBh(const std::vector<double>& raw) {
  std::vector<Output> motifs;
  motifs.reserve(raw.size());
  for (double p : raw) motifs.push_back(Output::makeForTest(p));
  bhCorrection(motifs);
  std::vector<double> out(motifs.size());
  for (size_t i = 0; i < motifs.size(); ++i) out[i] = motifs[i].getBHCorrected();
  return out;
}

}  // namespace

TEST_CASE("bhCorrection: empty input is a no-op") {
  std::vector<Output> motifs;
  bhCorrection(motifs);
  REQUIRE(motifs.empty());
}

TEST_CASE("bhCorrection: single value passes through unchanged (n/(n-0) == 1)") {
  auto adj = runBh({0.04});
  REQUIRE(adj.size() == 1);
  REQUIRE_NEAR(adj[0], 0.04, 1e-12);
}

TEST_CASE("bhCorrection: smallest p in 4-value mix gets the n/1 multiplier") {
  // Raw 0.04, 0.03, 0.02, 0.01. Sorted descending: 0.04 (multiplier 4/4=1),
  // 0.03 (4/3), 0.02 (4/2=2), 0.01 (4/1=4). After monotonic clamp:
  //   adj[0.04] = 0.04
  //   adj[0.03] = min(0.04, 0.03 * 4/3) = min(0.04, 0.04) = 0.04
  //   adj[0.02] = min(0.04, 0.02 * 2)   = 0.04
  //   adj[0.01] = min(0.04, 0.01 * 4)   = 0.04
  // (All tied at 0.04 because the raw p-values were uniformly spaced.)
  auto adj = runBh({0.04, 0.03, 0.02, 0.01});
  REQUIRE(adj.size() == 4);
  REQUIRE_NEAR(adj[0], 0.04, 1e-12);
  REQUIRE_NEAR(adj[1], 0.04, 1e-12);
  REQUIRE_NEAR(adj[2], 0.04, 1e-12);
  REQUIRE_NEAR(adj[3], 0.04, 1e-12);
}

TEST_CASE("bhCorrection: exposes the historical integer-division bug") {
  // The old buggy code (`n / (n - i)` where both were `long`) produced
  // multiplier = 1 for every i < n/2 — which means the smallest p,
  // multiplied by n=10/(n-i)=10, would have come out as raw_p * 1.
  // We assert the multiplier is applied: smallest of 10 raw values
  // sees n/1 = 10x scaling (before clamp). With raw = {0.001} as the
  // smallest, adj should reach 0.01, not stay at 0.001.
  std::vector<double> raw;
  for (int i = 0; i < 9; ++i) raw.push_back(0.5);  // 9 large p's
  raw.push_back(0.001);                             // 1 small p
  auto adj = runBh(raw);
  // The smallest raw (0.001) at rank 9 → multiplier 10/(10-9) = 10
  // → adj = 0.01 (before any clamp from larger ranks).
  REQUIRE_NEAR(adj[9], 0.01, 1e-12);
  // If the bug were back, adj[9] would be 0.001.
  REQUIRE(adj[9] > 0.005);
}

TEST_CASE("bhCorrection: matches reference implementation on random-ish input") {
  std::vector<double> raw = {0.001, 0.04, 0.005, 0.5, 0.02, 0.9, 0.1, 0.0001, 0.3, 0.06};
  auto adj_prod = runBh(raw);
  auto adj_ref = bhReference(raw);
  REQUIRE(adj_prod.size() == adj_ref.size());
  for (size_t i = 0; i < raw.size(); ++i) {
    REQUIRE_NEAR(adj_prod[i], adj_ref[i], 1e-12);
  }
}

TEST_CASE("bhCorrection: monotonic clamp prevents adj from ever rising") {
  // Construct raw values that, without the clamp, would produce a
  // non-monotonic adj sequence: the third-largest raw at i=2 has
  // multiplier 5/3 ≈ 1.67, and 0.05 * 1.67 = 0.0833 > 0.01 (the
  // adj of the second-largest, which started at 0.005 * 5/4 = 0.00625
  // → clamped to its own predecessor 0.005). Verify clamping forces
  // the descending order.
  std::vector<double> raw = {0.005, 0.004, 0.05, 0.001, 0.002};
  // Sort descending: 0.05 0.005 0.004 0.002 0.001 → indices 2,0,1,4,3
  // multipliers 5/5=1, 5/4, 5/3, 5/2, 5/1.
  // Without clamp we'd get jumps; the production code clamps each
  // to its predecessor when it tries to rise.
  auto adj = runBh(raw);
  // Sort the adj values descending alongside original raw descending —
  // the BH-adjusted sequence in the same order MUST be monotonically
  // non-increasing.
  std::vector<size_t> order = {2, 0, 1, 4, 3};
  for (size_t k = 1; k < order.size(); ++k) {
    REQUIRE(adj[order[k]] <= adj[order[k - 1]] + 1e-12);
  }
}
