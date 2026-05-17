// Unit tests for sortHits (motif.cpp).
//
// Why this matters: motif::finalizeAfterLoad() sorts every per-gene hit
// list by adjusted p-value using this predicate before downstream code
// (geometric-binomial test, motif-overlap detection) walks it. The
// downstream logic assumes ascending order — if sortHits ever flipped
// or became non-deterministic on ties the whole pairing pipeline would
// silently produce wrong p-values without any visible crash.
//
// These cases pin:
//   1. Strict-weak-ordering contract that std::sort needs
//   2. Ascending order is on adjPVal (the constructor's 4th arg —
//      stored as getPValue())
//   3. Equal-adjPVal pairs return false both ways (irreflexive,
//      stable when std::sort uses it)

#include "../src/motif.hpp"
#include "test_runner.hpp"

#include <algorithm>
#include <vector>

TEST_CASE("sortHits: returns true when a.adjP < b.adjP") {
  motifInstance a(10, 20, 0.5, 0.001);
  motifInstance b(30, 40, 0.7, 0.05);
  REQUIRE(sortHits(a, b) == true);
}

TEST_CASE("sortHits: returns false when a.adjP > b.adjP") {
  motifInstance a(10, 20, 0.5, 0.05);
  motifInstance b(30, 40, 0.7, 0.001);
  REQUIRE(sortHits(a, b) == false);
}

TEST_CASE("sortHits: equal adjP gives false in both directions (irreflexive)") {
  motifInstance a(10, 20, 0.1, 0.05);
  motifInstance b(30, 40, 0.9, 0.05);
  // std::sort requires a strict weak ordering: !cmp(x, x) and not both
  // cmp(a,b) && cmp(b,a) for equivalent values.
  REQUIRE(sortHits(a, b) == false);
  REQUIRE(sortHits(b, a) == false);
}

TEST_CASE("sortHits: ignores raw pVal — only adjPVal matters") {
  // Raw pVal a > b, but adjP a < b → still a-before-b.
  motifInstance a(10, 20, 0.9, 0.01);
  motifInstance b(30, 40, 0.1, 0.5);
  REQUIRE(sortHits(a, b) == true);
}

TEST_CASE("sortHits: ignores positional fields (start/end) — only adjPVal matters") {
  // a sits earlier on the chromosome but has a worse p than b.
  motifInstance a(1, 2, 0.5, 0.9);
  motifInstance b(100, 200, 0.5, 0.001);
  REQUIRE(sortHits(a, b) == false);
}

TEST_CASE("sortHits: drives std::sort to ascending adjPVal order") {
  std::vector<motifInstance> hits = {
      motifInstance(0, 0, 0.0, 0.5),
      motifInstance(0, 0, 0.0, 0.001),
      motifInstance(0, 0, 0.0, 0.05),
      motifInstance(0, 0, 0.0, 0.99),
      motifInstance(0, 0, 0.0, 0.01),
  };
  std::sort(hits.begin(), hits.end(), sortHits);
  for (size_t i = 1; i < hits.size(); ++i) {
    REQUIRE(hits[i - 1].getPValue() <= hits[i].getPValue());
  }
  // First entry is the smallest p (highest significance).
  REQUIRE(hits.front().getPValue() == 0.001);
  // Last entry is the largest.
  REQUIRE(hits.back().getPValue() == 0.99);
}

TEST_CASE("sortHits: handles boundary 0.0 and 1.0 p-values") {
  motifInstance a(0, 0, 0.0, 0.0);
  motifInstance b(0, 0, 0.0, 1.0);
  REQUIRE(sortHits(a, b) == true);
  REQUIRE(sortHits(b, a) == false);
}

TEST_CASE("sortHits: empty vector sort is a no-op (no crash)") {
  std::vector<motifInstance> empty;
  std::sort(empty.begin(), empty.end(), sortHits);
  REQUIRE(empty.empty());
}
