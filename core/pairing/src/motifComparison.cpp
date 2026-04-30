// motifComparison.cpp — pairwise overlap filtering, geometric-binomial test,
// and hypergeometric coloc test for one motif pair. Original 2019 © Paul Brown.

#include "motifComparison.hpp"

#include <math.h>

#include <exception>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

void motifComparison::reset() {
  genesInUniverseWithBothMotifs.clear();
  genesInClusterWithBothMotifs.clear();
  pval = 1.0;
}

// One row in the position-sorted index used by the two-pointer overlap sweep.
// `idx` is the original index inside the motif's hit list for the current
// gene, so we can flip the matching keep-flag after sorting.
namespace {
struct PosIdx {
  int start;
  int end;
  long idx;
};
} // namespace

void motifComparison::detectOverlappingPositions(const motif& m1, const motif& m2, GeneId gene, double ICthreshold,
                                                 std::vector<bool>& keep1, std::vector<bool>& keep2, long& kept1,
                                                 long& kept2) {
  const long n1 = static_cast<long>(keep1.size());
  const long n2 = static_cast<long>(keep2.size());

  // Snapshot each motif's hit positions for this gene and sort them by start.
  // Sorting once is cheap (typically <=5 hits per gene per motif) and lets
  // the inner loop walk only positionally-overlapping pairs instead of all
  // n1*n2 combinations.
  std::vector<PosIdx> p1(n1), p2(n2);
  for (long k = 0; k < n1; k++) {
    const motifInstance& inst = m1.getInstance(gene, k);
    p1[k] = {inst.getStartPos(), inst.getEndPos(), k};
  }
  for (long k = 0; k < n2; k++) {
    const motifInstance& inst = m2.getInstance(gene, k);
    p2[k] = {inst.getStartPos(), inst.getEndPos(), k};
  }
  std::sort(p1.begin(), p1.end(), [](const PosIdx& a, const PosIdx& b) { return a.start < b.start; });
  std::sort(p2.begin(), p2.end(), [](const PosIdx& a, const PosIdx& b) { return a.start < b.start; });

  // Two-pointer sweep: for each p1 entry, advance j0 past all p2 entries that
  // already ended before p1[i] starts (those can't overlap any later p1 either,
  // since p1 is sorted by start). Then walk p2[j0..] while it can still overlap.
  long j0 = 0;
  for (long i = 0; i < n1; i++) {
    while (j0 < n2 && p2[j0].end < p1[i].start)
      j0++;
    for (long j = j0; j < n2 && p2[j].start <= p1[i].end; j++) {
      if (motifInstancesOverlap(m1, m2, m1.getInstance(gene, p1[i].idx), m2.getInstance(gene, p2[j].idx),
                                ICthreshold)) {
        if (keep1[p1[i].idx]) {
          keep1[p1[i].idx] = false;
          --kept1;
        }
        if (keep2[p2[j].idx]) {
          keep2[p2[j].idx] = false;
          --kept2;
        }
      }
    }
  }
}

void motifComparison::findIntersectingGenes(const motif& motif1, const motif& motif2, double ICthreshold,
                                            const std::vector<int>& promSizes, bool isPoisson) {
  reset();

  // Step 1 — set intersection on the sorted gene lists. tmpSharedGenes is the
  // candidate pool of genes that have at least one hit from each motif; this
  // is `bm_genes` in the original Python.
  const std::vector<GeneId>& m1Genes = motif1.getSortedGeneIDs();
  const std::vector<GeneId>& m2Genes = motif2.getSortedGeneIDs();
  std::vector<GeneId> tmpSharedGenes;
  tmpSharedGenes.reserve(std::min(m1Genes.size(), m2Genes.size()));
  std::set_intersection(m1Genes.begin(), m1Genes.end(), m2Genes.begin(), m2Genes.end(),
                        std::back_inserter(tmpSharedGenes));

  // Step 2 — for each candidate gene, drop hit pairs that overlap too much
  // (high IC overlap == we can't trust both motifs are independently present),
  // then re-run the binomial test on whatever survives. A gene is kept only
  // if both motifs still meet their per-gene threshold after dropping.
  for (GeneId gene : tmpSharedGenes) {
    int promoterLength = promSizes[gene];
    if (!promoterLength)
      continue;

    const long n1 = motif1.getNumInstances(gene);
    const long n2 = motif2.getNumInstances(gene);
    std::vector<bool> keep1(n1, true), keep2(n2, true);
    long kept1 = n1, kept2 = n2;

    detectOverlappingPositions(motif1, motif2, gene, ICthreshold, keep1, keep2, kept1, kept2);

    if (kept1 == 0 || kept2 == 0)
      continue; // gene loses both motifs after filtering

    if (kept1 == n1 && kept2 == n2) {
      // Nothing dropped — original threshold from indexing still holds.
      genesInUniverseWithBothMotifs.push_back(gene);
    } else if (geometricBinomialTest(keep1, gene, promoterLength, motif1, isPoisson) &&
               geometricBinomialTest(keep2, gene, promoterLength, motif2, isPoisson)) {
      // Some hits were dropped — re-test both motifs and only keep the gene
      // if each is still at or below its threshold with the survivors.
      genesInUniverseWithBothMotifs.push_back(gene);
    }
  }
}

bool motifComparison::motifInstancesOverlap(const motif& motif1, const motif& motif2, const motifInstance& m1Instance,
                                            const motifInstance& m2Instance, double ICthreshold) {
  // any that return true will be filtered out
  // this is defineOverlapsBetweenTwoMotifs in python code
  int m1Start = m1Instance.getStartPos();
  int m2Start = m2Instance.getStartPos();
  int m1End = m1Instance.getEndPos();
  int m2End = m2Instance.getEndPos();

  if ((m1Start < m2Start && m1End < m2Start) || (m2End < m1Start && m2End < m1End))
    return false; // no overlap so keep

  if ((m1Start >= m2Start && m1End <= m2End) || (m2Start >= m1Start && m2End <= m1End))
    return true; // one motif entirely with the other so reject

  if (m2Start > m1Start) {
    // overlap is in the last part of motif1 and beginning of motif2
    int overlapLen = m1End - m2Start + 1;
    return (std::min(motif1.getReverseICScore(overlapLen), motif2.getForwardICScore(overlapLen)) > ICthreshold);

    // fwdIC is defined as the sum of the IC of the overlap in the
    // beginning of the second motif
    // revIC is defined as the sum of IC in the overlapping end of motif 1
    // if the overlap is too large and we need to ditch both of these hits
  } else {
    // overlap is in the first part of motif1 and end of motif2
    int overlapLen = m2End - m1Start + 1;
    return (std::min(motif1.getForwardICScore(overlapLen), motif2.getReverseICScore(overlapLen)) > ICthreshold);
  }
}

bool motifComparison::geometricBinomialTest(const std::vector<bool>& motifLocationsToKeep, GeneId gene,
                                            int promoterLength, const motif& mt, bool isPoisson) {
  // Test for one motif in one promoter
  // motifLocations contain p-values. Use if motifLocationsToKeep is true

  // return smallest value for this motif in this promoter
  long numpVals = std::count(motifLocationsToKeep.begin(), motifLocationsToKeep.end(), true);
  std::vector<double> pVals;
  pVals.reserve(numpVals);

  long possibleLocations = 2 * (promoterLength - mt.getLength() + 1);

  for (size_t i = 0; i < motifLocationsToKeep.size(); i++) {
    if (motifLocationsToKeep[i]) {
      const motifInstance& mInst = mt.getInstance(gene, static_cast<long>(i));
      pVals.push_back(mInst.getPValue());
    }
  }

  // motif instances have already been sorted and so pVals will be in ascending order
  // calculate geometric mean of all included p-vals

  double lowestScore = std::numeric_limits<double>::max();

  int k = 0;
  double logSum = 0.0;
  for (std::vector<double>::iterator i = pVals.begin(); i < pVals.end(); i++) {
    // Incremental geometric mean: accumulate log sum instead of recomputing from scratch
    logSum += log(*i);
    long n = (i + 1) - pVals.begin();
    double gm = exp(logSum / n);
    double binomP;
    if (isPoisson) {
      binomP = 1 - poissonCDF(gm * possibleLocations, k++);
    } else {
      binomP = 1 - binomialCDF(n, possibleLocations, gm);
    }

    lowestScore = (binomP < lowestScore) ? binomP : lowestScore;
  }

  return lowestScore <= mt.getThreshold();
}

double motifComparison::binomialCDF(long numPVals, long numLocations, double gm) {
  // gm is geometric mean
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

double motifComparison::poissonCDF(double lambda, int k) {
  double cdf = 0.0;
  for (int i = 0; i <= k; i++) {
    double poisson_pmf = 1.0; // Initialize PMF for each i
    // Calculating lambda^i / i!
    for (int j = 1; j <= i; j++) {
      poisson_pmf *= lambda / j;
    }
    // Multiplying with e^-lambda
    poisson_pmf *= exp(-lambda);
    // Adding to CDF
    cdf += poisson_pmf;
  }
  return cdf;
}

void motifComparison::colocTest(long universeSize, double ICthreshold, const std::string& clusterName,
                                const std::vector<GeneId>& genesInCluster) {
  // universeSize - total of all genes
  // ICthreshold - used in discarding 2 motifs on same gene which partially overlap
  // clusterName - cluster name from input file
  // geneInCluster = genes in cluster clusterName. Already sorted to make this more efficient
  (void)ICthreshold;
  (void)clusterName;

  long numGenesWithBothMotifs = genesInUniverseWithBothMotifs.size();
  clusterSize = genesInCluster.size();

  if (!numGenesWithBothMotifs || !clusterSize || !universeSize)
    return;

  genesInClusterWithBothMotifs.clear();
  genesInClusterWithBothMotifs.reserve(numGenesWithBothMotifs);

  std::set_intersection(genesInUniverseWithBothMotifs.begin(), genesInUniverseWithBothMotifs.end(),
                        genesInCluster.begin(), genesInCluster.end(), std::back_inserter(genesInClusterWithBothMotifs));

  if (!genesInClusterWithBothMotifs.size())
    return;

  // Pairwise hypergeometric p-value, log-scaled for numerical stability;
  // mirrors the Matlab implementation from Meng et al. (2009).
  // logf is precomputed once via buildLogfTable().
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
  for (int i = 0; i < aSize; i++)
    aSum += exp(a[i] - amax);

  pval = exp(logf[clusterSize] + logf[universeSize - clusterSize] + logf[numGenesWithBothMotifs] +
             logf[universeSize - numGenesWithBothMotifs] - logf[universeSize] + amax + log(aSum));
}

void motifComparison::buildLogfTable(long universeSize) {
  logf.resize(universeSize + 2, 0.0);
  logf[1] = log(1);
  for (long i = 2; i < static_cast<long>(logf.size()); i++)
    logf[i] = logf[i - 1] + log(static_cast<double>(i));
}
