// Unit tests for fairDivision() in utils.cpp.
//
// What it does: greedy LPT (Longest Processing Time) load balancer.
// Sorts items descending by weight, then repeatedly assigns the next
// item to whichever group currently has the lowest accumulated weight
// (min-heap). Used to split motif indices across worker threads so
// each thread does roughly the same amount of pair-comparison work.
//
// Why a unit test: the production binary's perceived throughput
// depends on this — a regression that puts everything on one thread
// would still run, just slower, and would not show up in any sha256
// baseline. End-to-end tests can't catch a balance bug; only an
// invariant check on the partitioning can.

#include "test_runner.hpp"
#include "../src/utils.hpp"

#include <algorithm>
#include <numeric>
#include <set>

namespace {

// Total weight assigned to one bin (sum of weights of every motifIndex
// the bin received). Used to assert balance.
long long binWeight(const std::vector<int>& bin, const std::vector<long long>& weights) {
  long long total = 0;
  for (int idx : bin) {
    if (idx >= 0 && (size_t)idx < weights.size()) total += weights[idx];
  }
  return total;
}

// Across all bins, every motifIndex from `input` must appear exactly
// once. fairDivision is a partition, never a copy or a drop.
void assertEachInputAppearsOnce(const std::vector<std::vector<int>>& bins,
                                 const std::vector<int>& input) {
  std::vector<int> flat;
  for (const auto& bin : bins) flat.insert(flat.end(), bin.begin(), bin.end());
  std::sort(flat.begin(), flat.end());
  std::vector<int> sorted_input = input;
  std::sort(sorted_input.begin(), sorted_input.end());
  REQUIRE(flat == sorted_input);
}

}  // namespace

TEST_CASE("fairDivision: numGroups <= 0 returns empty (no crash, no allocation)") {
  auto out = fairDivision({1, 2, 3}, {0, 10, 20, 30}, 0);
  REQUIRE(out.empty());
  out = fairDivision({1, 2, 3}, {0, 10, 20, 30}, -5);
  REQUIRE(out.empty());
}

TEST_CASE("fairDivision: empty input returns N empty bins") {
  auto out = fairDivision({}, {10, 20, 30}, 4);
  REQUIRE(out.size() == 4);
  for (const auto& bin : out) REQUIRE(bin.empty());
}

TEST_CASE("fairDivision: single item lands in exactly one bin") {
  auto out = fairDivision({2}, {0, 0, 5, 0}, 3);
  REQUIRE(out.size() == 3);
  int total = 0;
  for (const auto& bin : out) total += (int)bin.size();
  REQUIRE(total == 1);
}

TEST_CASE("fairDivision: equal-weight items distribute round-robin") {
  // 6 items, all weight 10, into 3 bins → each bin gets exactly 2 items
  // and total weight 20.
  std::vector<int> input = {0, 1, 2, 3, 4, 5};
  std::vector<long long> weights(6, 10);
  auto out = fairDivision(input, weights, 3);
  REQUIRE(out.size() == 3);
  for (const auto& bin : out) {
    REQUIRE(bin.size() == 2);
    REQUIRE(binWeight(bin, weights) == 20);
  }
  assertEachInputAppearsOnce(out, input);
}

TEST_CASE("fairDivision: greedy LPT keeps the heaviest item alone in its bin") {
  // weights 100, 1, 1, 1 into 2 bins. LPT places 100 first (bin A),
  // then the three 1's all go to bin B (always the lightest). So the
  // heavy item should be the only thing in its bin.
  std::vector<int> input = {0, 1, 2, 3};
  std::vector<long long> weights = {100, 1, 1, 1};
  auto out = fairDivision(input, weights, 2);
  REQUIRE(out.size() == 2);
  // Find the bin holding index 0 (weight 100).
  size_t heavyBin = (std::find(out[0].begin(), out[0].end(), 0) != out[0].end()) ? 0 : 1;
  REQUIRE(out[heavyBin].size() == 1);
  REQUIRE(out[heavyBin][0] == 0);
  // The other bin holds all three lightweights.
  REQUIRE(out[1 - heavyBin].size() == 3);
  assertEachInputAppearsOnce(out, input);
}

TEST_CASE("fairDivision: balance ratio stays within LPT's 4/3 worst case") {
  // For LPT the makespan is at most (4/3 - 1/(3m)) × OPT (Graham 1969).
  // In a 2-bin split the bound is 7/6 of OPT. We construct a known
  // case (5,4,3,2,1 into 2 bins → optimal makespan 8) and check the
  // observed max bin doesn't exceed the LPT bound.
  std::vector<int> input = {0, 1, 2, 3, 4};
  std::vector<long long> weights = {5, 4, 3, 2, 1};
  auto out = fairDivision(input, weights, 2);
  long long w0 = binWeight(out[0], weights);
  long long w1 = binWeight(out[1], weights);
  long long maxW = std::max(w0, w1);
  // Total weight 15, so OPT ≥ 8. LPT bound ≤ 7/6 × OPT_lower_bound ≤ 10.
  // (LPT's actual answer here is 8 — perfect — but we test the bound.)
  REQUIRE(maxW <= 10);
  REQUIRE(w0 + w1 == 15);
  assertEachInputAppearsOnce(out, input);
}

TEST_CASE("fairDivision: out-of-range motifIndex defaults to weight 0") {
  // motifIndex 100 has no entry in the weights vector — production
  // code falls back to 0 instead of crashing. Test this explicitly so
  // a future bounds-check refactor doesn't accidentally change the
  // contract.
  std::vector<int> input = {0, 100};
  std::vector<long long> weights = {50};  // only weight for index 0
  auto out = fairDivision(input, weights, 2);
  REQUIRE(out.size() == 2);
  // The heavy motif (index 0, weight 50) and the unknown (index 100,
  // treated as 0) end up in different bins because LPT places the
  // heavy first and then the empty group gets the light one.
  size_t heavyBin = (std::find(out[0].begin(), out[0].end(), 0) != out[0].end()) ? 0 : 1;
  REQUIRE(out[heavyBin].size() == 1);
  REQUIRE(out[heavyBin][0] == 0);
  REQUIRE(out[1 - heavyBin].size() == 1);
  REQUIRE(out[1 - heavyBin][0] == 100);
}

TEST_CASE("fairDivision: more groups than items leaves trailing groups empty") {
  std::vector<int> input = {0, 1};
  std::vector<long long> weights = {3, 5};
  auto out = fairDivision(input, weights, 4);
  REQUIRE(out.size() == 4);
  int nonEmpty = 0;
  for (const auto& bin : out) if (!bin.empty()) ++nonEmpty;
  REQUIRE(nonEmpty == 2);  // exactly 2 items → exactly 2 non-empty bins
  assertEachInputAppearsOnce(out, input);
}

TEST_CASE("fairDivision: ties broken by ascending motifIndex (stable contract)") {
  // Three items with equal weight, into 1 bin. Order inside the bin
  // depends on the sort's tie-break. Production sort breaks ties by
  // ascending motifIndex (see the lambda in fairDivision). Pin that
  // so a future "use std::stable_sort" or comparator change doesn't
  // silently shuffle thread-assignment determinism.
  std::vector<int> input = {7, 3, 5};
  std::vector<long long> weights(8, 0);
  weights[3] = weights[5] = weights[7] = 10;  // all tied
  auto out = fairDivision(input, weights, 1);
  REQUIRE(out.size() == 1);
  REQUIRE(out[0].size() == 3);
  REQUIRE(out[0][0] == 3);
  REQUIRE(out[0][1] == 5);
  REQUIRE(out[0][2] == 7);
}
