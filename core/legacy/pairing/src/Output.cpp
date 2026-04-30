//  Created by Paul Brown on 25/09/2019.

#include "Output.hpp"

#include <iomanip>

void Output::printMe(long globalBonferroniFactor, std::ofstream& outFile) {
  double pvalBonferroniCorrected = std::min((pval * clusterSize), 1.0);
  double pvalGlobalBonferroniCorrected = std::min((pval * globalBonferroniFactor), 1.0);

  outFile << motif1Name << '\t' << motif2Name << '\t' << genesInClusterWithBothMotifs.size() << '\t'
          << numSharedGenesInUniverse << '\t' << clusterSize << '\t' << std::scientific << std::setprecision(10) << pval
          << '\t' << pvalBHCorrected << '\t' << pvalBonferroniCorrected << '\t' << pvalGlobalBonferroniCorrected
          << '\t';

  for (auto gene = std::begin(genesInClusterWithBothMotifs); gene != std::end(genesInClusterWithBothMotifs); gene++)
    outFile << *gene << ';';

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

bool sortComparisons(const Output& a, const Output& b) {
  if (a.motif1Name == b.motif1Name)
    return (a.motif2Name < b.motif2Name);
  else
    return (a.motif1Name < b.motif1Name);
}
