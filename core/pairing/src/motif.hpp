// motif.hpp — declares the motif and motifInstance classes used during pairing.
// Original 2019 © Paul Brown.

#ifndef motif_hpp
#define motif_hpp

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

using GeneId = int;

// MinHash sketch width. With K=128, the standard error of the Jaccard estimate
// is ~1/sqrt(K) = ~9%; for the prefilter we just want "is the intersection
// surely tiny?", which is well within MinHash's strength even at modest K.
constexpr int kMinHashK = 128;

class motifInstance {
  // Represents one row of a fimohits file (text or binary).
  // The strand column from fimohits is loaded but never consumed by pairing
  // logic (overlap / hypergeometric tests are strand-agnostic), so it isn't
  // stored — saves ~24 B of std::string overhead per hit, which is millions
  // of hits at full scale.
public:
  motifInstance(int start, int end, double p1, double p2) : startPos(start), endPos(end), pVal(p1), adjPVal(p2) {};
  int getStartPos() const { return startPos; };
  int getEndPos() const { return endPos; };
  double getPValue() const { return adjPVal; }; // used for geometric mean

private:
  int startPos;
  int endPos;
  double pVal;
  double adjPVal;
};

bool sortHits(const motifInstance& a, const motifInstance& b);

class motif {
  // represents the content of 1 fimo file

public:
  bool readFimoFile(const std::string filename, const std::unordered_map<std::string, GeneId>& geneNameToId,
                    std::unordered_map<std::string, std::vector<double>>& ICvalues,
                    std::unordered_map<std::string, double>& topNthreshold, bool* missingValues);
  bool readBinaryFimoFile(const std::string& filename, const std::unordered_map<std::string, GeneId>& geneNameToId,
                          std::unordered_map<std::string, std::vector<double>>& ICvalues,
                          std::unordered_map<std::string, double>& topNthreshold, bool* missingValues);
  void setMotifName(const std::string& motif);
  std::string getMotifName() const;
  void setThreshold(double thresh);
  double getThreshold() const;
  void getListofGenes(std::vector<GeneId>& genes) const;
  const std::vector<GeneId>& getSortedGeneIDs() const;
  double getForwardICScore(int overlapLength) const;
  double getReverseICScore(int overlapLength) const;
  int getLength() const;
  long getNumGenesWithMotif() const;
  long getTotalInstances() const;

  long getNumInstances(GeneId geneID) const;

  const motifInstance& getInstance(GeneId gene, long idx) const;

  // Build the MinHash sketch over `sortedGeneIDs`. Call once after the gene
  // set is finalized.
  void buildMinHashSketch();
  const std::array<std::uint64_t, kMinHashK>& getMinHashSketch() const { return minhash; }

  // Number of MinHash slots that match between *this* and `other`. The
  // estimated Jaccard similarity is `count / kMinHashK`. Cheap (~kMinHashK
  // comparisons), independent of the gene-set sizes, so safe to call once
  // per pair.
  int minhashMatchCount(const motif& other) const;

  // Test-only factory: build a motif populated only with the IC vector
  // (which seeds motifLength + ICPrefixSum). Avoids the file-loading
  // path so unit tests can exercise the IC-overlap math without
  // crafting a fimohits file. Production code never calls this.
  static motif makeForTest(const std::string& name, const std::vector<double>& ic);
  // Test-only: same as makeForTest plus a sorted gene-id vector and an
  // immediately-built MinHash sketch. Used by sketch / Jaccard tests.
  static motif makeForTestWithGenes(const std::string& name, const std::vector<double>& ic,
                                    const std::vector<GeneId>& geneIds);
  // Test-only: append one motifInstance under the given gene. Lets
  // tests that exercise per-gene logic (geometricBinomialTest, etc.)
  // assemble a motif's hit list without going through fimohits I/O.
  void addInstanceForTest(GeneId gene, const motifInstance& inst) {
    instances[gene].push_back(inst);
  }

private:
  // Shared post-load step for both readFimoFile (text) and readBinaryFimoFile:
  // sort each gene's hits by p-value, materialize sortedGeneIDs, build the
  // MinHash sketch, and emit the "Motif X has N occurrences ..." log line.
  // Caller passes `totalHits` which it counted while populating `instances`.
  void finalizeAfterLoad(long totalHits);

  // Shared metadata lookup for both readers: given the parsed motifName and
  // motifLength, look up IC values and the binomial threshold from the
  // global maps, validate IC length, and build ICPrefixSum. Sets
  // *missingValues if IC or threshold is absent / mis-sized. Filename is
  // only used for context in error messages.
  void lookupICAndThreshold(const std::string& filename, std::unordered_map<std::string, std::vector<double>>& ICvalues,
                            std::unordered_map<std::string, double>& topNthreshold, bool* missingValues);

  std::string motifName;
  int motifLength;
  std::vector<double> IC;
  std::vector<double> ICPrefixSum; // prefix sum for O(1) range IC queries
  std::vector<GeneId> sortedGeneIDs;
  double binomialThreshold;
  long totalInstances = 0;

  // key is gene ID, value is list of positions found in that gene
  std::unordered_map<GeneId, std::vector<motifInstance>> instances;

  // MinHash sketch over `sortedGeneIDs`. Filled by buildMinHashSketch().
  std::array<std::uint64_t, kMinHashK> minhash{};
};

#endif /* motif_hpp */
