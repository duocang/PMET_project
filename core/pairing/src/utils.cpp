#include <dirent.h>
// #include <gperftools/profiler.h>
#include <math.h>
#include <string.h>
#include <sys/types.h>

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

#include "Output.hpp"
#include "motif.hpp"
#include "motifComparison.hpp"
#include "utils.hpp"

void exportResultParallel(std::string cluster, std::vector<Output>::iterator beginIt,
                          std::vector<Output>::iterator endIt, std::string outFile, long globalBonferroniFactor,
                          const std::vector<std::string>& motifNamesByIndex,
                          const std::vector<std::string>& geneNamesById) {
  // open results file, pmet results
  std::ofstream outputFile;
  outputFile.open(outFile, std::ios_base::out);
  if (!outputFile.is_open()) {
    // Throw rather than exit(): we run inside a std::thread, and exit() here
    // would skip the joins above us. The thread launcher in main.cpp wraps
    // every export worker in a try/catch and reports which one failed.
    throw std::runtime_error("Error opening results file " + outFile);
  }

  // print sorted, correcgted compoarisons inb this cluster
  for (std::vector<Output>::iterator mc = beginIt; mc != endIt; mc++) {
    outputFile << cluster << '\t'; // cluster name
    mc->printMe(globalBonferroniFactor, outputFile, motifNamesByIndex, geneNamesById);
  }

  outputFile.close();
}

void writeProgress(const std::string& fname, const std::string& message, float inc) {
  std::ifstream infile;

  float progress = 0.0;
  std::string oldMessage;

  infile.open(fname, std::ifstream::in);
  if (infile.is_open()) {
    infile >> progress >> oldMessage;
    infile.close();
  }
  progress += inc;
  std::ofstream outfile;

  outfile.open(fname, std::ofstream::out);

  if (outfile.is_open()) {
    outfile << progress << "\t" << message << std::endl;
    outfile.close();
  }
}

bool loadFiles(const std::string& path, const std::string& genesFile, const std::string& promotersFile,
               const std::string& binThreshFile, const std::string& ICFile, const std::string& fimoDir,
               std::vector<int>& promSizes, std::unordered_map<std::string, double>& topNthreshold,
               std::unordered_map<std::string, std::vector<double>>& ICvalues,
               std::map<std::string, std::vector<GeneId>>& clusters,
               std::unordered_map<std::string, GeneId>& geneNameToId, std::vector<std::string>& geneNamesById,
               std::vector<std::string>& fimoFiles, std::vector<std::map<std::string, std::vector<Output>>>& results) {
  std::cout << "Reading input files..." << std::endl;

  // get promoter lengths. These are stored in tsv file "Name  length"
  std::stringstream promFileContent;
  if (!fastFileRead(path + promotersFile, promFileContent))
    return false;

  std::string geneID, len;
  std::vector<std::pair<std::string, int>> promoterEntries;
  while (promFileContent >> geneID >> len)
    promoterEntries.emplace_back(geneID, stoi(len));

  std::sort(promoterEntries.begin(), promoterEntries.end(),
            [](const auto& a, const auto& b) { return a.first < b.first; });

  geneNameToId.clear();
  geneNamesById.clear();
  promSizes.clear();
  geneNameToId.reserve(promoterEntries.size());
  geneNamesById.reserve(promoterEntries.size());
  promSizes.reserve(promoterEntries.size());

  for (const auto& entry : promoterEntries) {
    GeneId geneId = static_cast<GeneId>(geneNamesById.size());
    geneNameToId.emplace(entry.first, geneId);
    geneNamesById.push_back(entry.first);
    promSizes.push_back(entry.second);
  }

  std::cout << "Universe size is " << promSizes.size() << std::endl;

  std::stringstream binFileContent;
  // same for binomial thresholds
  if (!fastFileRead(path + binThreshFile, binFileContent))
    return false;

  std::string motifID, threshold;

  while (binFileContent >> motifID >> threshold)
    topNthreshold.emplace(motifID, stof(threshold));

  // Information Content values. Here there is a float value for each position in the motif

  std::ifstream ifs(path + ICFile);

  if (!ifs) {
    std::cerr << "Error: Cannot open file " << path + ICFile << std::endl;
    return false;
  }

  std::string line;
  while (std::getline(ifs, line)) {
    std::istringstream ics(line);
    double score;
    ics >> motifID;

    ICvalues.emplace(motifID, std::vector<double>());

    while (ics >> score)
      ICvalues[motifID].push_back(score);
  }

  // gene clusters

  std::stringstream geneFileContent;
  std::string clusterID;

  if (!fastFileRead(genesFile, geneFileContent))
    return false;

  long genesFound = 0;

  std::map<std::string, std::vector<GeneId>>::iterator got;
  while (geneFileContent >> clusterID >> geneID) {
    auto geneIt = geneNameToId.find(geneID);
    if (geneIt == geneNameToId.end()) {
      std::cerr << "Error : Gene ID " << geneID << " not found in promoter lengths file!" << std::endl;
      return false;
    }

    // vector of genes for each cluster
    if ((got = clusters.find(clusterID)) == clusters.end()) {
      clusters.emplace(clusterID, std::vector<GeneId>());

      for (int i = 0; i < results.size(); i++) {
        // initialise results vector for this cluster
        results[i].emplace(clusterID, std::vector<Output>());
      }
    }
    clusters[clusterID].push_back(geneIt->second);
    genesFound++;
  }
  std::cout << "Found " << genesFound << " gene IDs in " << clusters.size() << " clusters" << std::endl;

  // need to sort clustrer first oc can find intersection efficiently.
  for (auto& cl : clusters)
    std::sort(cl.second.begin(), cl.second.end());

  // list of fimo files
  std::string searchDir = fimoDir;
  DIR* pDir = opendir(searchDir.c_str());

  if (!pDir) {
    std::cerr << "Error: Cannot find directory " << searchDir << std::endl;
    return false;
  }

  struct dirent* fp;
  while ((fp = readdir(pDir))) // exclude "." and ".."
    if (fp->d_name[0] != '.')
      fimoFiles.push_back(fp->d_name);

  closedir(pDir);

  // sort, excluding .txt part
  std::sort(fimoFiles.begin(), fimoFiles.end(), [](const std::string& a, const std::string& b) {
    return (a.compare(0, a.size() - 4, b, 0, b.size() - 4) < 0);
  });

  return true;
}

bool fastFileRead(const std::string& filename, std::stringstream& results) {
  // fast way to read a text file into memory
  // reads entire file into results and returns number of lines

  long flength;
  long numLines = 0;
  bool success = false;

  std::ifstream ifs(filename, std::ifstream::binary);

  if (!ifs) {
    std::cerr << "Error: Cannot open file " << filename << std::endl;
    return false;
  }

  ifs.seekg(0, ifs.end);
  flength = ifs.tellg();
  ifs.seekg(0, ifs.beg);

  std::string buffer(flength, '\0');

  if (!ifs.read(&buffer[0], flength))
    std::cerr << "Error reading file " << filename << std::endl;
  else {
    results.str(buffer);
    success = true;
  }

  ifs.close();

  if (!success)
    return false;

  // count number of lines read
  numLines = std::count(std::istreambuf_iterator<char>(results), std::istreambuf_iterator<char>(), '\n');
  // in case no \n on last line
  results.unget();
  if (results.get() != '\n')
    numLines++;
  // reset iterator
  results.seekg(0);

  // Return type is bool; callers only care about success vs. failure (the
  // line count is informational and never consumed).
  (void)numLines;
  return true;
}

bool validateInputs(const std::vector<int>& promSizes, const std::unordered_map<std::string, double>& topNthreshold,
                    const std::unordered_map<std::string, std::vector<double>>& ICvalues,
                    const std::map<std::string, std::vector<GeneId>>& clusters,
                    const std::vector<std::string> fimoFiles) {
  std::cout << "Validating inputs...";

  if (clusters.empty()) {
    std::cerr << "Error : No gene clusters found!" << std::endl;
    return false;
  }

  if (fimoFiles.empty()) {
    std::cerr << "Error : FIMO files not found!" << std::endl;
    return false;
  }

  if (topNthreshold.empty()) {
    std::cerr << "Error : Binomial threshold values not found!" << std::endl;
    return false;
  }

  if (ICvalues.empty()) {
    std::cerr << "Error : Information Content values not found!" << std::endl;
    return false;
  }

  if (promSizes.empty()) {
    std::cerr << "Error : No promoter sizes found!" << std::endl;
    return false;
  }

  std::cout << "OK";
  std::cout << std::endl;
  return true;
}

void bhCorrection(std::vector<Output>& motifs) {
  // get list of all pvals fo rthis cluster, retaining original index position

  std::vector<std::pair<long, double>> pValues;
  long n = motifs.size();

  pValues.reserve(n);

  for (long i = 0; i < n; i++)
    pValues.push_back(std::make_pair(i, motifs[i].getpValue()));

  // sort descendingie largest p val first
  std::sort(pValues.begin(), pValues.end(),
            [](const std::pair<long, double>& a, const std::pair<long, double>& b) { return a.second > b.second; });

  // now multiply each p value by a factor based on its position in the sorted list
  // n and i are both `long` — without the explicit double cast the division is
  // integer, so for any i < n/2 the multiplier collapses to 1 and BH "correction"
  // is a no-op (adj p == raw p). The fix is just to force floating-point.
  for (long i = 0; i < n; i++) {
    pValues[i].second *= (static_cast<double>(n) / (n - i));
    if (i && pValues[i].second > pValues[i - 1].second)
      pValues[i].second = pValues[i - 1].second;

    motifs[pValues[i].first].setBHCorrection(
        pValues[i].second); // assign corrected value to its original index position before sort
  }
}

std::vector<std::vector<int>> fairDivision(const std::vector<int>& input, const std::vector<long long>& weights,
                                           int numGroups) {
  if (numGroups <= 0)
    return {};

  std::vector<std::vector<int>> resultVector(static_cast<size_t>(numGroups));
  if (input.empty())
    return resultVector;

  struct WeightedMotif {
    int motifIndex;
    long long weight;
  };

  std::vector<WeightedMotif> weightedMotifs;
  weightedMotifs.reserve(input.size());
  for (int motifIndex : input) {
    long long weight = 0;
    if (motifIndex >= 0 && static_cast<size_t>(motifIndex) < weights.size())
      weight = weights[motifIndex];
    weightedMotifs.push_back({motifIndex, weight});
  }

  std::sort(weightedMotifs.begin(), weightedMotifs.end(), [](const WeightedMotif& a, const WeightedMotif& b) {
    if (a.weight == b.weight)
      return a.motifIndex < b.motifIndex;
    return a.weight > b.weight;
  });

  // Min-heap: (current estimated work, group index) — always assign to the lightest group.
  std::priority_queue<std::pair<long long, int>, std::vector<std::pair<long long, int>>,
                      std::greater<std::pair<long long, int>>>
      minHeap;

  for (int i = 0; i < numGroups; ++i)
    minHeap.push({0, i});

  for (const WeightedMotif& motifEntry : weightedMotifs) {
    auto [currentWeight, groupIdx] = minHeap.top();
    minHeap.pop();
    resultVector[groupIdx].push_back(motifEntry.motifIndex);
    minHeap.push({currentWeight + motifEntry.weight, groupIdx});
  }

  return resultVector;
}

int output(std::vector<motif>::iterator blockstart, std::vector<motif>::iterator blockEnd,
           std::vector<motif>::iterator last, const std::map<std::string, std::vector<GeneId>>& clusters,
           motifComparison mComp, std::map<std::string, std::vector<Output>>* results, double ICthreshold,
           const std::vector<int>& promSizes, const std::vector<motif>& allMotifs, long numComplete,
           long totalComparisons, const std::string& outputDirName, bool isPoisson) {
  (void)outputDirName;
  for (std::vector<motif>::iterator motif1 = blockstart; motif1 != blockEnd; ++motif1) {
    const int motif1Index = static_cast<int>(
        std::distance(allMotifs.cbegin(), std::vector<motif>::const_iterator(motif1)));
    for (std::vector<motif>::iterator motif2 = motif1 + 1; motif2 != last; ++motif2) {
      const int motif2Index = static_cast<int>(
          std::distance(allMotifs.cbegin(), std::vector<motif>::const_iterator(motif2)));
      mComp.findIntersectingGenes(*motif1, *motif2, ICthreshold, promSizes,
                                  isPoisson); // sets genesInUniverseWithBothMotifs, used in Coloc Test
      // got shared genes so do test for each cluster
      for (auto& cl : clusters) {
        // std::cout << "                          Gene cluster: " << cl.first << std::endl;
        // std::cout << "                                 mComp: " << mComp.getpValue() << std::endl;
        mComp.colocTest(promSizes.size(), ICthreshold, cl.first, cl.second);
        (*results)[cl.first].push_back(Output(motif1Index, motif2Index, mComp));
      }

      std::cout << "\b\b\b";
      // progress goes from 10 to 90% in this loop
      double progVal = 0.1 + double(0.8 * ++numComplete) / totalComparisons;
      std::cout << std::setw(2) << long(progVal * 100) << "%" << std::endl;
    }
    std::cout << " Perfomed " << numComplete << " of " << totalComparisons << " pair-wise comparisons" << std::endl;
  }
  return 1;
}

/*
    motif pair comparsion, one of motif (from a vector) compares with following motifs

    @motifsIndxVector: a vector of motifs' index
    @*allMotifs: a vector of motifs' name
    @clusters: clusters of genes
    @motifComparison: result of motif's comparsion
    @*results: as it named
    @ICthreshold
    @promSizes
    @numComplete
    @outputDirName
*/
int outputParallel(const std::vector<int>& motifsIndxVector, std::vector<motif>* allMotifs,
                   const std::map<std::string, std::vector<GeneId>>& clusters, motifComparison mComp,
                   std::map<std::string, std::vector<Output>>* results, double ICthreshold,
                   const std::vector<int>& promSizes, long numComplete, long totalComparisons,
                   const std::string& outputDirName, bool isPoisson, int minhashMinIntersection) {
  (void)numComplete;
  (void)totalComparisons;
  (void)outputDirName;
  for (int i : motifsIndxVector) {
    const motif& motif1 = (*allMotifs)[i];
    const long m1Genes = motif1.getNumGenesWithMotif();
    for (int j = i + 1; j < (*allMotifs).size(); j++) {
      const motif& motif2 = (*allMotifs)[j];

      // MinHash prefilter: estimate |genes(motif1) ∩ genes(motif2)| from the
      // sketch. If far below `minhashMinIntersection`, skip the pair entirely
      // — its hypergeometric p-value cannot reach Bonferroni significance, so
      // dropping it does not change which pairs the user acts on.
      if (minhashMinIntersection > 0) {
        int matches = motif1.minhashMatchCount(motif2);
        // Estimated intersection size, conservative: jaccard * (|A| + |B|)
        // (true |A ∪ B| ≤ |A| + |B|, so this overestimates the intersection
        // — i.e. we err on the side of *keeping* pairs).
        long unionUpper = m1Genes + motif2.getNumGenesWithMotif();
        long estIntersect = (long)((double)matches * unionUpper / kMinHashK);
        if (estIntersect < minhashMinIntersection) {
          // Emit a dummy Output per cluster so BH correction still sees the
          // total comparison count; pval = 1.0 means it ranks last and never
          // crosses any threshold.
          mComp.recordSkippedPair();
          for (auto& cl : clusters) {
            mComp.colocTest(promSizes.size(), ICthreshold, cl.first, cl.second);
            (*results)[cl.first].push_back(Output(i, j, mComp));
          }
          continue;
        }
      }

      mComp.findIntersectingGenes(motif1, motif2, ICthreshold, promSizes,
                                  isPoisson); // sets genesInUniverseWithBothMotifs, used in Coloc Test
      // got shared genes so do test for each cluster
      for (auto& cl : clusters) {
        mComp.colocTest(promSizes.size(), ICthreshold, cl.first, cl.second);
        (*results)[cl.first].push_back(Output(i, j, mComp));
        // std::cout   << cl.first << " " << motif1.getMotifName() << " " << motif2.getMotifName()
        //             << " " << mComp.getSharedGenesInCluster().size() << " "  << mComp.getpValue() << std::endl;
      }
    }
  }
  return 1;
}
