// motifComparison.hpp — declares the motifComparison class that holds the
// per-pair statistics for a single motif × motif comparison.
// Original 2019 © Paul Brown.

#ifndef motifComparison_hpp
#define motifComparison_hpp

#include <fstream>
#include <string>
#include <vector>

#include "motif.hpp"

class motifComparison {
  // represents one line in the results file

public:
  double getpValue() const { return pval; };
  long getClusterSize() const { return clusterSize; };
  const std::vector<GeneId>& getSharedGeneIdsInCluster() const { return genesInClusterWithBothMotifs; };
  long getNumSharedGenesInUniverse() const { return genesInUniverseWithBothMotifs.size(); };

  void findIntersectingGenes(const motif& m1, const motif& m2, double ICthreshold, const std::vector<int>& promSizes,
                             bool isPoisson);
  void colocTest(long universeSize, double ICthreshold, const std::string& clusterName,
                 const std::vector<GeneId>& genesInCluster);
  void buildLogfTable(long universeSize);

  // Mark the current comparison as "skipped by prefilter": empty intersection,
  // pval = 1.0. Subsequent colocTest() calls become near no-ops (early-out on
  // numGenesWithBothMotifs == 0) so BH still counts them but they rank last.
  void recordSkippedPair() {
    pval = 1.0;
    clusterSize = 0;
    genesInUniverseWithBothMotifs.clear();
    genesInClusterWithBothMotifs.clear();
  }

  // Pure-math helpers — no `this` used. Public + static so unit tests
  // can call them directly without spinning up a motifComparison
  // instance. Internal callers (geometricBinomialTest below) pick them
  // up the same way.
  static double binomialCDF(long numPVals, long numLocations, double gm);
  static double poissonCDF(double lambda, int k);

private:
  void reset();
  bool motifInstancesOverlap(const motif& m1, const motif& m2, const motifInstance& m1Instance,
                             const motifInstance& m2Instance, double IDthreshold);
  // For one shared gene: walk every (m1 hit, m2 hit) pair whose positions
  // overlap (cheap two-pointer sweep over position-sorted indices) and mark
  // pairs that fail the IC overlap rule as "to drop" in keep1/keep2.
  // Updates kept1/kept2 to reflect how many entries survived.
  void detectOverlappingPositions(const motif& m1, const motif& m2, GeneId gene, double ICthreshold,
                                  std::vector<bool>& keep1, std::vector<bool>& keep2, long& kept1, long& kept2);
  bool geometricBinomialTest(const std::vector<bool>& motifLocationsToKeep, GeneId gene, int promoterLength,
                             const motif& mt, bool isPoisson);

  double pval;
  long clusterSize;

  std::vector<double> logf; // precomputed log factorial table
  std::vector<GeneId> genesInClusterWithBothMotifs;
  std::vector<GeneId> genesInUniverseWithBothMotifs;
};

#endif /* motifComparison_hpp */
