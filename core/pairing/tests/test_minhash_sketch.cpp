// Unit tests for buildMinHashSketch() + minhashMatchCount() in motif.cpp.
//
// These power the optional `-m` prefilter that skips motif pairs whose
// estimated gene-set intersection is too small to ever reach
// significance. Calibration of the prefilter is documented in
// docs/perf/minhash_calibration.md; that calibration assumes the
// sketch is correct. This file pins that.
//
// What we want to know:
// 1. Identical gene sets → 128/128 matches (sketch is deterministic
//    given a deterministic input ordering).
// 2. Empty vs empty → 128/128 (the loop never runs, every slot stays
//    at uint64_max — and uint64_max == uint64_max in all 128 slots).
// 3. Disjoint sets → matches very small (would be 0 in expectation;
//    K=128 random seeds make actual collisions rare).
// 4. Subset sets → match count tracks Jaccard within sketch noise.
// 5. Symmetry: matchCount(A, B) == matchCount(B, A).

#include "test_runner.hpp"
#include "../src/motif.hpp"

#include <numeric>
#include <vector>

namespace {

// Build a motif with [1..n] as the gene set and a 1-position IC vector
// (we don't need real IC content for sketch tests).
motif sketchMotifFromIds(const std::string& name, const std::vector<GeneId>& ids) {
  return motif::makeForTestWithGenes(name, {1.0}, ids);
}

}  // namespace

TEST_CASE("MinHash: identical gene sets → 128/128 matches") {
  std::vector<GeneId> ids;
  for (int i = 1; i <= 1000; ++i) ids.push_back(i);
  auto a = sketchMotifFromIds("A", ids);
  auto b = sketchMotifFromIds("B", ids);
  REQUIRE(a.minhashMatchCount(b) == kMinHashK);
}

TEST_CASE("MinHash: two empty gene sets → 128/128 matches") {
  // Empty sortedGeneIDs leaves every slot at uint64_max; two empty
  // motifs therefore agree on every slot. (Defensive: this means a
  // gene-less motif looks "perfectly similar" to anything else with
  // an empty set, which is fine because no pair test runs in that
  // case anyway.)
  auto a = sketchMotifFromIds("A", {});
  auto b = sketchMotifFromIds("B", {});
  REQUIRE(a.minhashMatchCount(b) == kMinHashK);
}

TEST_CASE("MinHash: disjoint gene sets → very few matches") {
  // {1..1000} vs {1001..2000}. With 128 independent slot seeds, the
  // probability of a slot accidentally tying is very low — we pin
  // < 5 matches as a sanity bound. (Theoretical expectation under
  // independence is essentially 0.)
  std::vector<GeneId> a_ids, b_ids;
  for (int i = 1; i <= 1000; ++i) a_ids.push_back(i);
  for (int i = 1001; i <= 2000; ++i) b_ids.push_back(i);
  auto a = sketchMotifFromIds("A", a_ids);
  auto b = sketchMotifFromIds("B", b_ids);
  int matches = a.minhashMatchCount(b);
  REQUIRE(matches < 5);
}

TEST_CASE("MinHash: matchCount is symmetric") {
  std::vector<GeneId> a_ids = {7, 11, 13, 17, 19, 23, 29, 31, 37, 41};
  std::vector<GeneId> b_ids = {11, 13, 17, 19, 23, 53, 59, 61, 67, 71};
  auto a = sketchMotifFromIds("A", a_ids);
  auto b = sketchMotifFromIds("B", b_ids);
  REQUIRE(a.minhashMatchCount(b) == b.minhashMatchCount(a));
}

TEST_CASE("MinHash: self-vs-self always returns full match count") {
  std::vector<GeneId> ids = {42, 100, 200, 300, 400};
  auto m = sketchMotifFromIds("M", ids);
  REQUIRE(m.minhashMatchCount(m) == kMinHashK);
}

TEST_CASE("MinHash: estimated Jaccard tracks true Jaccard within noise") {
  // A = {1..1000}, B = {1..500} ∪ {1501..2000}. |A ∩ B| = 500,
  // |A ∪ B| = 1500, true Jaccard = 1/3 ≈ 0.333. Sketch estimate is
  // matches/K with stderr ~1/sqrt(K) ≈ 9% of the truth.
  // K=128 means the count should land in [25, 60] for 1/3 most of
  // the time; we use a generous tolerance so the test isn't flaky on
  // pathological seed combinations.
  std::vector<GeneId> a_ids, b_ids;
  for (int i = 1; i <= 1000; ++i) a_ids.push_back(i);
  for (int i = 1; i <= 500; ++i) b_ids.push_back(i);
  for (int i = 1501; i <= 2000; ++i) b_ids.push_back(i);

  auto a = sketchMotifFromIds("A", a_ids);
  auto b = sketchMotifFromIds("B", b_ids);
  int matches = a.minhashMatchCount(b);
  // True Jaccard 1/3 → expected matches = 128/3 ≈ 42.7.
  // Wide tolerance so deterministic seed drift doesn't flake us.
  REQUIRE(matches >= 20);
  REQUIRE(matches <= 70);
}

TEST_CASE("MinHash: matchCount in [0, kMinHashK] for any inputs") {
  // Property test on a couple of arbitrary sets — the count must
  // always land in the valid range. Catches a corruption regression
  // (e.g. comparing the wrong slot in a refactor).
  std::vector<GeneId> a = {1, 2, 3, 4, 5};
  std::vector<GeneId> b = {3, 4, 5, 6, 7};
  std::vector<GeneId> c = {100, 200, 300};
  auto ma = sketchMotifFromIds("A", a);
  auto mb = sketchMotifFromIds("B", b);
  auto mc = sketchMotifFromIds("C", c);
  for (int v : {ma.minhashMatchCount(mb), ma.minhashMatchCount(mc), mb.minhashMatchCount(mc)}) {
    REQUIRE(v >= 0);
    REQUIRE(v <= kMinHashK);
  }
}

TEST_CASE("MinHash: sketch is order-independent (sortedGeneIDs sorted before hashing)") {
  // Production builds the sketch over `sortedGeneIDs` which
  // makeForTestWithGenes sorts before calling. So passing the same
  // ids in two different orders should yield byte-identical sketches
  // (and 128/128 matches).
  std::vector<GeneId> a_ids = {5, 3, 1, 4, 2};
  std::vector<GeneId> b_ids = {2, 4, 1, 3, 5};  // same set, different input order
  auto a = sketchMotifFromIds("A", a_ids);
  auto b = sketchMotifFromIds("B", b_ids);
  REQUIRE(a.minhashMatchCount(b) == kMinHashK);
}
