// Output.hpp — declares the Output class: one finalized motif × motif row,
// including its BH/Bonferroni-corrected p-values. Original 2019 © Paul Brown.

#ifndef Output_hpp
#define Output_hpp

#include "motifComparison.hpp"

class Output {
  friend bool sortComparisons(const Output& a, const Output& b, const std::vector<std::string>& motifNamesByIndex);

public:
  Output() = default;
  Output(int motif1Index, int motif2Index, const motifComparison& mComp)
      : motif1Index(motif1Index), motif2Index(motif2Index), pval(mComp.getpValue()), pvalBHCorrected(1.0),
        clusterSize(mComp.getClusterSize()), genesInClusterWithBothMotifs(mComp.getSharedGeneIdsInCluster()),
        numSharedGenesInUniverse(mComp.getNumSharedGenesInUniverse()) {}

  static void writeHeaders(std::ofstream& of);
  void printMe(long globalBonferroniFactor, std::ofstream& outFile, const std::vector<std::string>& motifNamesByIndex,
               const std::vector<std::string>& geneNamesById) const;
  double getpValue() const { return pval; };
  // Accessors below are write-set by the BH correction pass and read
  // back by exporters and unit tests; bhCorrection() in utils.cpp is
  // the only place that mutates pvalBHCorrected.
  double getBHCorrected() const { return pvalBHCorrected; };
  void setBHCorrection(double p) { pvalBHCorrected = p; };
  // Test-only constructor: lets unit tests build an Output with a
  // raw p-value without going through the full motifComparison flow.
  static Output makeForTest(double rawP) {
    Output o;
    o.pval = rawP;
    return o;
  }

private:
  int motif1Index = -1;
  int motif2Index = -1;
  double pval = 1.0;
  double pvalBHCorrected = 1.0;
  long clusterSize = 0;

  std::vector<GeneId> genesInClusterWithBothMotifs;
  long numSharedGenesInUniverse = 0;
};

bool sortComparisons(const Output& a, const Output& b, const std::vector<std::string>& motifNamesByIndex);

#endif /* Output_hpp */
