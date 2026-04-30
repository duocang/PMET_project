//  Created by Paul Brown on 01/07/2019.

#include "motifComparison.hpp"

#include <math.h>

#include <exception>
#include <fstream>
#include <iostream>
#include <limits>

void motifComparison::reset() {
  genesInUniverseWithBothMotifs.clear();
  genesInClusterWithBothMotifs.clear();
  pval = 1.0;
}

void motifComparison::findIntersectingGenes(motif& motif1, motif& motif2, double ICthreshold,
                                            std::unordered_map<std::string, int>& promSizes) {
  reset();

  std::vector<std::string> m1Genes, m2Genes, tmpSharedGenes;
  motif1.getListofGenes(m1Genes);
  motif2.getListofGenes(m2Genes);
  tmpSharedGenes.reserve(m1Genes.size());
  std::set_intersection(m1Genes.begin(), m1Genes.end(), m2Genes.begin(), m2Genes.end(),
                        std::inserter(tmpSharedGenes, tmpSharedGenes.begin()));

  for (std::vector<std::string>::iterator gene = tmpSharedGenes.begin(); gene != tmpSharedGenes.end(); gene++) {
    if (promSizes[*gene]) {
      long numM1Locations = motif1.getNumInstances(*gene);
      long numM2Locations = motif2.getNumInstances(*gene);
      std::vector<bool> motif1LocationsToKeep(numM1Locations, true);
      std::vector<bool> motif2LocationsToKeep(numM2Locations, true);

      for (long mLoc1 = 0; mLoc1 < numM1Locations; mLoc1++) {
        motifInstance& m1Instance = motif1.getInstance(*gene, mLoc1);
        for (long mLoc2 = 0; mLoc2 < numM2Locations; mLoc2++) {
          motifInstance& m2Instance = motif2.getInstance(*gene, mLoc2);
          if (motifInstancesOverlap(motif1, motif2, m1Instance, m2Instance, ICthreshold)) {
            motif1LocationsToKeep[mLoc1] = false;
            motif2LocationsToKeep[mLoc2] = false;
          }
        }
      }

      if ((std::find(motif1LocationsToKeep.begin(), motif1LocationsToKeep.end(), true) !=
           motif1LocationsToKeep.end()) &&
          (std::find(motif2LocationsToKeep.begin(), motif2LocationsToKeep.end(), true) !=
           motif2LocationsToKeep.end())) {
        if ((std::find(motif1LocationsToKeep.begin(), motif1LocationsToKeep.end(), false) ==
             motif1LocationsToKeep.end()) &&
            (std::find(motif2LocationsToKeep.begin(), motif2LocationsToKeep.end(), false) ==
             motif2LocationsToKeep.end())) {
          genesInUniverseWithBothMotifs.push_back(*gene);

        } else {
          if (geometricBinomialTest(motif1LocationsToKeep, *gene, promSizes[*gene], motif1) &&
              geometricBinomialTest(motif2LocationsToKeep, *gene, promSizes[*gene], motif2))
            genesInUniverseWithBothMotifs.push_back(*gene);
        }
      }
    }
  }
}

bool motifComparison::motifInstancesOverlap(motif& motif1, motif& motif2, motifInstance& m1Instance,
                                            motifInstance& m2Instance, double ICthreshold) {
  int m1Start = m1Instance.getStartPos();
  int m2Start = m2Instance.getStartPos();
  int m1End = m1Instance.getEndPos();
  int m2End = m2Instance.getEndPos();

  if ((m1Start < m2Start && m1End < m2Start) || (m2End < m1Start && m2End < m1End))
    return false;
  if ((m1Start >= m2Start && m1End <= m2End) || (m2Start >= m1Start && m2End <= m1End))
    return true;

  if (m2Start > m1Start) {
    int overlapLen = m1End - m2Start + 1;
    return (std::min(motif1.getReverseICScore(overlapLen), motif2.getForwardICScore(overlapLen)) > ICthreshold);
  } else {
    int overlapLen = m2End - m1Start + 1;
    return (std::min(motif1.getForwardICScore(overlapLen), motif2.getReverseICScore(overlapLen)) > ICthreshold);
  }
}

bool motifComparison::geometricBinomialTest(const std::vector<bool>& motifLocationsToKeep, const std::string& gene,
                                            int promoterLength, motif& mt) {
  long numpVals = std::count(motifLocationsToKeep.begin(), motifLocationsToKeep.end(), true);
  std::vector<double> pVals;
  pVals.reserve(numpVals);

  for (int i = 0; i < motifLocationsToKeep.size(); i++) {
    if (motifLocationsToKeep[i]) {
      motifInstance mInst = mt.getInstance(gene, i);
      pVals.push_back(mInst.getPValue());
    }
  }

  double lowestScore = std::numeric_limits<double>::max();
  long possibleLocations = 2 * (promoterLength - mt.getLength() + 1);

  for (std::vector<double>::iterator i = pVals.begin(); i < pVals.end(); i++) {
    double gm = geometricMean(pVals.begin(), i + 1);
    double binomP = 1 - binomialCDF((i + 1 - pVals.begin()), possibleLocations, gm);
    lowestScore = (binomP < lowestScore) ? binomP : lowestScore;
  }
  return lowestScore <= mt.getThreshold();
}

double motifComparison::geometricMean(std::vector<double>::iterator first, std::vector<double>::iterator last) {
  double sum = 0.0;
  long len = last - first;

  for (std::vector<double>::iterator i = first; i < last; i++) sum += log(*i);

  return exp(sum / len);
}

double motifComparison::binomialCDF(long numPVals, long numLocations, double gm) {
  double cdf = 0.0;
  double b = 0.0;
  double logP = log(gm);
  double logOneMinusP = log(1 - gm);

  for (int k = 0; k < numPVals; k++) {
    if (k > 0)
      b += log(numLocations - k + 1) - log(k);
    cdf += exp(b + k * logP + (numLocations - k) * logOneMinusP);
  }
  return cdf;
}

void motifComparison::colocTest(long universeSize, double ICthreshold, const std::string& clusterName,
                                std::vector<std::string>& genesInCluster) {
  long numGenesWithBothMotifs = genesInUniverseWithBothMotifs.size();

  clusterSize = genesInCluster.size();

  if (!numGenesWithBothMotifs || !clusterSize || !universeSize)
    return;

  genesInClusterWithBothMotifs.clear();
  genesInClusterWithBothMotifs.reserve(numGenesWithBothMotifs);

  std::set_intersection(genesInUniverseWithBothMotifs.begin(), genesInUniverseWithBothMotifs.end(),
                        genesInCluster.begin(), genesInCluster.end(),
                        std::inserter(genesInClusterWithBothMotifs, genesInClusterWithBothMotifs.begin()));

  if (!genesInClusterWithBothMotifs.size())
    return;

  std::vector<double> logf(universeSize + 2, 0.0);
  logf[1] = log(1);
  for (int i = 2; i < logf.size(); i++) logf[i] = logf[i - 1] + log(i);

  long minSetSize = (clusterSize < numGenesWithBothMotifs) ? clusterSize : numGenesWithBothMotifs;

  long aSize = minSetSize - genesInClusterWithBothMotifs.size() + 1;
  std::vector<double> a(aSize);

  double amax = -std::numeric_limits<double>::max();
  for (int i = 0; i < aSize; i++) {
    long hold = genesInClusterWithBothMotifs.size() + i;
    a[i] = (-logf[hold] - logf[clusterSize - hold] - logf[numGenesWithBothMotifs - hold] -
            logf[universeSize + hold - clusterSize - numGenesWithBothMotifs]);
    amax = (a[i] > amax) ? a[i] : amax;
  }
  double aSum = 0.0;
  for (int i = 0; i < aSize; i++) aSum += exp(a[i] - amax);

  pval = exp(logf[clusterSize] + logf[universeSize - clusterSize] + logf[numGenesWithBothMotifs] +
             logf[universeSize - numGenesWithBothMotifs] - logf[universeSize] + amax + log(aSum));
}
