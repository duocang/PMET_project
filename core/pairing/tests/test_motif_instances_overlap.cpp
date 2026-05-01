// Unit tests for motifInstancesOverlap() in motifComparison.cpp.
//
// What it does: given two motif hits on the same promoter, decide
// whether they overlap by enough (measured in summed information
// content over the overlap region) that we should drop the pair from
// the per-promoter binomial recount. The asymmetric direction matters:
//   - When m2 starts after m1, overlap is at the END of m1 and the
//     START of m2 → reverse-IC of m1 vs forward-IC of m2.
//   - When m1 starts after m2, the opposite assignment holds.
//
// Why a unit test: this function gates which hits survive the binomial
// re-test in findIntersectingGenes. Five lines of geometric branching
// + two IC range queries — easy to flip a sign or a threshold sense
// during refactoring, and the only end-to-end signal would be
// motif_output.txt drift on borderline pairs.

#include "test_runner.hpp"
#include "../src/motifComparison.hpp"
#include "../src/motif.hpp"

namespace {

// Two-IC-position motifs are enough to exercise every branch:
// length 5 with IC = [2, 2, 2, 2, 2]. forwardIC(k) = 2k,
// reverseIC(k) = 2k. Total = 10.
const std::vector<double> kFlatIC = {2.0, 2.0, 2.0, 2.0, 2.0};

motifInstance makeInst(int start, int end) {
  // pVal / adjPVal are unused by motifInstancesOverlap; values
  // chosen to be visually distinct from the position columns.
  return motifInstance(start, end, 0.001, 0.005);
}

}  // namespace

TEST_CASE("motifInstancesOverlap: disjoint intervals → keep (false)") {
  // m1 = [10, 14], m2 = [20, 24]. No positional overlap → keep.
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(10, 14);
  auto i2 = makeInst(20, 24);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 4.0) == false);
}

TEST_CASE("motifInstancesOverlap: m1 fully inside m2 → drop (true)") {
  // m1 = [12, 14] (3 bp), m2 = [10, 18] (9 bp). m1 ⊂ m2.
  // The function returns "drop" without consulting IC — pure
  // containment is always too much overlap.
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(12, 14);
  auto i2 = makeInst(10, 18);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 4.0) == true);
}

TEST_CASE("motifInstancesOverlap: m2 fully inside m1 → drop (true)") {
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(10, 18);
  auto i2 = makeInst(12, 14);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 4.0) == true);
}

TEST_CASE("motifInstancesOverlap: rightward partial overlap, IC below threshold → keep") {
  // m1 = [10, 14] (5 bp), m2 = [13, 17] (5 bp). overlapLen = 14 - 13 + 1 = 2.
  // reverseIC(2) = 4, forwardIC(2) = 4. min = 4. With threshold 5,
  // 4 > 5 is false → keep.
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(10, 14);
  auto i2 = makeInst(13, 17);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 5.0) == false);
}

TEST_CASE("motifInstancesOverlap: rightward partial overlap, IC above threshold → drop") {
  // Same geometry: overlapLen 2, IC sum 4 on each side. With
  // threshold 3, 4 > 3 is true → drop.
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(10, 14);
  auto i2 = makeInst(13, 17);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 3.0) == true);
}

TEST_CASE("motifInstancesOverlap: leftward partial overlap (m2 starts before m1)") {
  // m1 = [13, 17], m2 = [10, 14]. overlapLen = 14 - 13 + 1 = 2.
  // The branch: forwardIC(m1, 2) = 4, reverseIC(m2, 2) = 4. min = 4.
  // With threshold 5 → keep, with threshold 3 → drop.
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(13, 17);
  auto i2 = makeInst(10, 14);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 5.0) == false);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 3.0) == true);
}

TEST_CASE("motifInstancesOverlap: asymmetric IC means min() picks the lower side") {
  // m1 IC = [10, 0, 0, 0, 0] — all the IC at position 0 (forward heavy).
  //   reverseIC(2) reads positions [3, 4] → sum = 0.
  //   forwardIC(2) reads positions [0, 1] → sum = 10.
  // m2 IC = [0, 0, 0, 0, 10] — opposite (reverse heavy).
  //   forwardIC(2) reads positions [0, 1] → sum = 0.
  //   reverseIC(2) reads positions [3, 4] → sum = 10.
  //
  // m1 = [10, 14], m2 = [13, 17] → rightward branch:
  //   min(reverseIC(m1,2), forwardIC(m2,2)) = min(0, 0) = 0 → keep.
  //
  // This pins the asymmetric handling: min() means the test fails as
  // long as either side has weak IC over the overlap, so we don't
  // drop a pair where one motif's overlap region was uninformative.
  auto m1 = motif::makeForTest("M1", {10.0, 0.0, 0.0, 0.0, 0.0});
  auto m2 = motif::makeForTest("M2", {0.0, 0.0, 0.0, 0.0, 10.0});
  auto i1 = makeInst(10, 14);
  auto i2 = makeInst(13, 17);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 4.0) == false);
}

TEST_CASE("motifInstancesOverlap: identical interval treated as containment → drop") {
  // m1 == m2 in position. The containment branch fires
  // ((m1Start >= m2Start && m1End <= m2End) — both true).
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(10, 14);
  auto i2 = makeInst(10, 14);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 999.0) == true);
}

TEST_CASE("motifInstancesOverlap: single-position overlap exercises edge boundary") {
  // m1 = [10, 13], m2 = [13, 17]. Overlap is exactly position 13
  // (overlapLen = 1). min(IC over 1 position) for kFlatIC = 2.
  // Threshold 1 → drop; threshold 3 → keep.
  auto m1 = motif::makeForTest("M1", kFlatIC);
  auto m2 = motif::makeForTest("M2", kFlatIC);
  auto i1 = makeInst(10, 13);
  auto i2 = makeInst(13, 17);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 1.0) == true);
  REQUIRE(motifComparison::motifInstancesOverlap(m1, m2, i1, i2, 3.0) == false);
}
