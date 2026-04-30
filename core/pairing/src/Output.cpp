// Output.cpp — one row of the final pair output table; serializes itself to
// the merged motif_output.txt at the end of pairing. Original 2019 © Paul Brown.

#include "Output.hpp"

#include <iomanip>

void Output::printMe(long globalBonferroniFactor, std::ofstream& outFile,
                     const std::vector<std::string>& motifNamesByIndex,
                     const std::vector<std::string>& geneNamesById) const {
  /*Print in this order
  1 motif1name
  2 motif2name
  3 number of intersecting genes in the cluster
  4 Total number of intersecting genes
  5 Number of genes in cluster
  7 uncorrected pval
  8 BH corrected pval
  9 Bonferroni corrected for cluster size pval
  10 Global Bonferroni corrected pval
  11 list of genes in 3
   */

  double pvalBonferroniCorrected = std::min((pval * clusterSize), 1.0);

  // this factor is total number of all comparisons
  double pvalGlobalBonferroniCorrected = std::min((pval * globalBonferroniFactor), 1.0);

  outFile << motifNamesByIndex[motif1Index] << '\t' << motifNamesByIndex[motif2Index] << '\t'
          << genesInClusterWithBothMotifs.size() << '\t' << numSharedGenesInUniverse << '\t' << clusterSize << '\t'
          << std::scientific << std::setprecision(10) << pval << '\t' << pvalBHCorrected << '\t'
          << pvalBonferroniCorrected << '\t' << pvalGlobalBonferroniCorrected << '\t';

  for (GeneId geneId : genesInClusterWithBothMotifs)
    outFile << geneNamesById[geneId] << ';';

  outFile << std::endl;
}

void Output::writeHeaders(std::ofstream& of) {
  of << "Cluster\t"
     << "Motif 1\t"
     << "Motif 2\t"
     << "Number of genes in cluster with both motifs\t"
     << "Total number of genes with both motifs\t"
     << "Number of genes in cluster\t"
     << "Raw p-value\t"
     << "Adjusted p-value (BH)\t"
     << "Adjusted p-value (Bonf)\t"
     << "Adjusted p-value (Global Bonf)\t"
        "Genes"
     << std::endl;
}

bool sortComparisons(const Output& a, const Output& b, const std::vector<std::string>& motifNamesByIndex) {
  // sort ascending on motif1, then motif2

  const std::string& aMotif1 = motifNamesByIndex[a.motif1Index];
  const std::string& bMotif1 = motifNamesByIndex[b.motif1Index];
  if (aMotif1 == bMotif1)
    return motifNamesByIndex[a.motif2Index] < motifNamesByIndex[b.motif2Index];

  return aMotif1 < bMotif1;
}
