// PMET Pairing - Parallel motif enrichment analysis tool
// Analyzes co-occurrence of transcription factor binding motifs in gene promoters

#include <dirent.h>
#include <math.h>
#include <string.h>
#include <sys/types.h>

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cstring>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

#include "Output.hpp"
#include "motif.hpp"
#include "motifComparison.hpp"
#include "utils.hpp"

// Configuration structure for program parameters
struct Config {
  std::string inputDir = ".";
  std::string promotersFile = "promoter_lengths.txt";
  std::string binThreshFile = "binomial_thresholds.txt";
  std::string ICFile = "IC.txt";
  std::string fimoDir = "fimohits/";
  std::string outputDirName = "./";
  std::string outputFileName = "temp_header.txt";
  std::string genesFile = "input.txt";
  std::string progressFile = "progress.log";
  double ICthreshold = 4.0;
  int numThreads = 16;
  bool isPoisson = false;
  // MinHash prefilter: skip pair (i,j) if estimated |genes(i) ∩ genes(j)|
  // is below this many genes. 0 disables the prefilter (all pairs evaluated).
  int minhashMinIntersection = 0;
};

void printUsage();
bool parseCommandLineArgs(int argc, const char* argv[], Config& config);

bool loadFiles(const std::string& path, const std::string& genesFile, const std::string& promotersFile,
               const std::string& binThreshFile, const std::string& ICFile, const std::string& fimoDir,
               std::vector<int>& promSizes, std::unordered_map<std::string, double>& topNthreshold,
               std::unordered_map<std::string, std::vector<double>>& ICvalues,
               std::map<std::string, std::vector<GeneId>>& clusters,
               std::unordered_map<std::string, GeneId>& geneNameToId, std::vector<std::string>& geneNamesById,
               std::vector<std::string>& fimoFiles, std::vector<std::map<std::string, std::vector<Output>>>& results);
bool validateInputs(const std::vector<int>& promSizes, const std::unordered_map<std::string, double>& topNthreshold,
                    const std::unordered_map<std::string, std::vector<double>>& ICvalues,
                    const std::map<std::string, std::vector<GeneId>>& clusters,
                    const std::vector<std::string> fimoFiles);
bool fastFileRead(const std::string& filename, std::stringstream& results);

// Statistical correction and utility functions
void bhCorrection(std::vector<Output>& motifs);
void writeProgress(const std::string& fname, const std::string& message, float inc);
std::vector<std::vector<int>> fairDivision(const std::vector<int>& input, const std::vector<long long>& weights,
                                           int numGroups);

// Core analysis functions
int output(std::vector<motif>::iterator first, std::vector<motif>::iterator later, std::vector<motif>::iterator last,
           const std::map<std::string, std::vector<GeneId>>& clusters, motifComparison mComp,
           std::map<std::string, std::vector<Output>>* results, double ICthreshold, const std::vector<int>& promSizes,
           const std::vector<motif>& allMotifs, long numComplete, long totalComparisons,
           const std::string& outputDirName, bool isPoisson);

// Parallel worker function for motif comparison
int outputParallel(const std::vector<int>& motifsIndx, std::vector<motif>* allMotifs,
                   const std::map<std::string, std::vector<GeneId>>& clusters, motifComparison mComp,
                   std::map<std::string, std::vector<Output>>* results, double ICthreshold,
                   const std::vector<int>& promSizes, long numComplete, long totalComparisons,
                   const std::string& outputDirName, bool isPoisson, int minhashMinIntersection);

// Export results to file in parallel
void exportResultParallel(std::string cluster, std::vector<Output>::iterator beginIt,
                          std::vector<Output>::iterator endIt, std::string outFile, long globalBonferroniFactor,
                          const std::vector<std::string>& motifNamesByIndex,
                          const std::vector<std::string>& geneNamesById);

void printUsage() {
  std::cout
      << "Usage: pmet [OPTIONS]\n\n"
      << "Options:\n"
      << "  -d <input_directory>           Input directory.          Default: '.'\n"
      << "  -g <genes_file>                Genes file.               Default: 'input.txt'\n"
      << "  -i <ICthreshold>               IC threshold.             Default: 4\n"
      << "  -t <num_threads>               Number of threads.        Default: 16\n"
      << "  -p <promoter_lengths_file>     Promoter lengths file.    Default: 'promoter_lengths.txt'\n"
      << "  -b <binomial_values_file>      Binomial values file.     Default: 'binomial_thresholds.txt'\n"
      << "  -c <information_content_file>  Information content file. Default: 'IC.txt'\n"
      << "  -f <fimo_dir>                  FIMO directory.           Default: 'fimohits/'\n"
      << "  -s <progress_file>             Progress log file.        Default: 'progress.log'\n"
      << "  -o <output_dir>                Output directory.         Default: './'\n"
      << "  -x <0|1>                       Use Poisson model.        Default: 0\n"
      << "  -m <min_intersection>          MinHash prefilter: skip pair if estimated |A∩B| < this. Default: 0 (off)\n"
      << "  -h                             Show this help message\n";
}

bool parseCommandLineArgs(int argc, const char* argv[], Config& config) {
  // -h is the only zero-arg flag; everything else takes a value, so most
  // branches need argv[i+1]. Do bounds + numeric-parse error reporting in
  // one place via these helpers instead of exploding the parse loop.
  auto needValue = [&](int i) -> const char* {
    if (i + 1 >= argc) {
      std::cerr << "Error: option '" << argv[i] << "' requires a value." << std::endl;
      printUsage();
      return nullptr;
    }
    return argv[i + 1];
  };
  auto parseInt = [&](const char* flag, const char* s, int& out) -> bool {
    try {
      std::size_t consumed = 0;
      int v = std::stoi(s, &consumed);
      if (consumed != std::strlen(s))
        throw std::invalid_argument("trailing chars");
      out = v;
      return true;
    } catch (const std::exception&) {
      std::cerr << "Error: option '" << flag << "' expects an integer, got '" << s << "'." << std::endl;
      return false;
    }
  };
  auto parseDouble = [&](const char* flag, const char* s, double& out) -> bool {
    try {
      std::size_t consumed = 0;
      double v = std::stod(s, &consumed);
      if (consumed != std::strlen(s))
        throw std::invalid_argument("trailing chars");
      out = v;
      return true;
    } catch (const std::exception&) {
      std::cerr << "Error: option '" << flag << "' expects a number, got '" << s << "'." << std::endl;
      return false;
    }
  };

  for (int i = 1; i < argc; i += 2) {
    const char* flag = argv[i];
    if (!strcmp(flag, "-h")) {
      printUsage();
      return false;
    }
    const char* value = needValue(i);
    if (!value)
      return false;

    if (!strcmp(flag, "-i")) {
      if (!parseDouble(flag, value, config.ICthreshold))
        return false;
    } else if (!strcmp(flag, "-t")) {
      if (!parseInt(flag, value, config.numThreads))
        return false;
    } else if (!strcmp(flag, "-m")) {
      if (!parseInt(flag, value, config.minhashMinIntersection))
        return false;
    } else if (!strcmp(flag, "-d")) {
      config.inputDir = value;
    } else if (!strcmp(flag, "-g")) {
      config.genesFile = value;
    } else if (!strcmp(flag, "-p")) {
      config.promotersFile = value;
    } else if (!strcmp(flag, "-b")) {
      config.binThreshFile = value;
    } else if (!strcmp(flag, "-c")) {
      config.ICFile = value;
    } else if (!strcmp(flag, "-f")) {
      config.fimoDir = value;
    } else if (!strcmp(flag, "-o")) {
      config.outputDirName = value;
    } else if (!strcmp(flag, "-s")) {
      config.progressFile = value;
    } else if (!strcmp(flag, "-x")) {
      config.isPoisson = (value[0] != '0');
    } else {
      std::cerr << "Error: Unknown command line switch '" << flag << "'" << std::endl;
      printUsage();
      return false;
    }
  }
  return true;
}

int main(int argc, const char* argv[]) {
  Config config;

  // Parse command line arguments
  if (!parseCommandLineArgs(argc, argv, config)) {
    return 0; // Exit gracefully for -h or on error
  }

  constexpr float PROGRESS_INCREMENT = 0.01f;
  float inc = PROGRESS_INCREMENT;
  std::stringstream msgString;

  // Ensure directories end with '/'
  auto ensureTrailingSlash = [](std::string& path) {
    if (!path.empty() && path.back() != '/')
      path += '/';
  };

  ensureTrailingSlash(config.inputDir);
  ensureTrailingSlash(config.outputDirName);
  ensureTrailingSlash(config.fimoDir);
  config.fimoDir = config.inputDir + config.fimoDir;

  std::cout << "          Input parameters          " << std::endl;
  std::cout << "------------------------------------" << std::endl;
  std::cout << "Input Directory:\t\t\t" << config.inputDir << std::endl;
  std::cout << "Gene list file:\t\t\t\t" << config.genesFile << std::endl;
  std::cout << "IC threshold:\t\t\t\t" << config.ICthreshold << std::endl;
  std::cout << "Threads used:\t\t\t\t" << config.numThreads << std::endl;
  std::cout << "Promoter lengths:\t\t\t" << config.promotersFile << std::endl;
  std::cout << "Binomial threshold values:\t\t" << config.binThreshFile << std::endl;
  std::cout << "Motif IC values:\t\t\t" << config.ICFile << std::endl;
  std::cout << "Fimo files:\t\t\t\t" << config.fimoDir << std::endl;
  std::cout << "Output directory:\t\t\t" << config.outputDirName << std::endl;
  std::cout << "------------------------------------" << std::endl << std::endl;

  // Data structures for input data
  std::vector<int> promSizes;
  std::unordered_map<std::string, GeneId> geneNameToId;
  std::vector<std::string> geneNamesById;
  std::unordered_map<std::string, double> topNthreshold;
  std::unordered_map<std::string, std::vector<double>> ICvalues;
  std::vector<std::string> fimoFiles;
  std::map<std::string, std::vector<GeneId>> clusters;

  // Per-thread results storage for parallel processing
  // Each thread stores results by cluster name for efficient multiple testing correction
  std::vector<std::map<std::string, std::vector<Output>>> results(config.numThreads);

  if (!loadFiles(config.inputDir, config.genesFile, config.promotersFile, config.binThreshFile, config.ICFile,
                 config.fimoDir, promSizes, topNthreshold, ICvalues, clusters, geneNameToId, geneNamesById, fimoFiles,
                 results)) {
    std::cerr << "Error: Failed to load input files" << std::endl;
    return 1;
  }

  if (!validateInputs(promSizes, topNthreshold, ICvalues, clusters, fimoFiles)) {
    std::cerr << "Error: Input validation failed" << std::endl;
    return 1;
  }

  // Calculate total number of pairwise comparisons needed
  long numClusters = clusters.size();
  long numFimoFiles = fimoFiles.size();
  long totalComparisons = (numFimoFiles * numFimoFiles - numFimoFiles) / 2;

  std::vector<motif> allMotifs(numFimoFiles, motif());
  bool missingValues = false;

  for (long m = 0; m < numFimoFiles; ++m) {
    allMotifs[m].readFimoFile(config.fimoDir + fimoFiles[m], geneNameToId, ICvalues, topNthreshold, &missingValues);
  }

  if (missingValues) {
    std::cerr << "Error: Missing values detected in FIMO files" << std::endl;
    return 1;
  }

  std::vector<std::string> motifNamesByIndex;
  motifNamesByIndex.reserve(allMotifs.size());
  for (const motif& motifEntry : allMotifs)
    motifNamesByIndex.push_back(motifEntry.getMotifName());

  // Initialize pairwise comparison tracking
  long numComplete = 0;
  motifComparison mComp;
  mComp.buildLogfTable(promSizes.size());

  // Distribute motifs across threads to balance comparison workload
  // Note: work is divided into numThreads partitions
  const int numMotifs = static_cast<int>(allMotifs.size());
  std::vector<int> motifIndices(numMotifs);
  std::iota(motifIndices.begin(), motifIndices.end(), 0);
  std::vector<long long> motifWorkWeights(numMotifs, 0);
  for (int i = 0; i < numMotifs; ++i) {
    const long long remainingComparisons = static_cast<long long>(numMotifs - i - 1);
    const long long motifMass = static_cast<long long>(allMotifs[i].getNumGenesWithMotif()) +
                                static_cast<long long>(allMotifs[i].getTotalInstances());
    motifWorkWeights[i] = remainingComparisons * motifMass;
  }
  std::vector<std::vector<int>> motifsInThread = fairDivision(motifIndices, motifWorkWeights, config.numThreads);

  // Launch parallel computation threads. Wrap each worker so an uncaught
  // exception just sets a flag and logs the message — without this, a throw
  // from outputParallel would propagate out of the std::thread body and call
  // std::terminate, killing the whole process before we can even log which
  // worker died.
  std::atomic<bool> workerFailed{false};
  std::mutex stderrMutex;
  auto runWorker = [&](int threadIdx, const std::vector<int>& motifsForThread) {
    try {
      outputParallel(motifsForThread, &allMotifs, clusters, mComp, &results[threadIdx], config.ICthreshold, promSizes,
                     numComplete, totalComparisons, config.outputDirName, config.isPoisson,
                     config.minhashMinIntersection);
    } catch (const std::exception& e) {
      workerFailed = true;
      std::lock_guard<std::mutex> lk(stderrMutex);
      std::cerr << "Error: pair worker " << threadIdx << " failed: " << e.what() << std::endl;
    } catch (...) {
      workerFailed = true;
      std::lock_guard<std::mutex> lk(stderrMutex);
      std::cerr << "Error: pair worker " << threadIdx << " failed: unknown exception" << std::endl;
    }
  };

  std::vector<std::thread> threads;
  threads.reserve(config.numThreads - 1);

  for (int i = 0; i < config.numThreads - 1; ++i) {
    std::cout << "Starting Thread " << (i + 1) << std::endl;
    threads.emplace_back(runWorker, i, std::cref(motifsInThread[i]));
  }

  // Execute last partition in main thread
  std::cout << "Starting Thread " << config.numThreads << " (main thread)" << std::endl;
  runWorker(config.numThreads - 1, motifsInThread[config.numThreads - 1]);

  // Wait for all worker threads to complete
  for (auto& thread : threads) {
    thread.join();
  }

  if (workerFailed) {
    std::cerr << "Error: one or more pair workers failed; aborting before output." << std::endl;
    return 1;
  }

  // Merge results from all threads into results[0]
  std::cout << "\nMerging results from all threads..." << std::endl;
  for (size_t i = 1; i < results.size(); ++i) {
    for (const auto& clusterPair : results[0]) {
      const std::string& clusterName = clusterPair.first;
      auto& mainResults = results[0][clusterName];
      const auto& threadResults = results[i][clusterName];
      mainResults.insert(mainResults.end(), threadResults.begin(), threadResults.end());
    }
  }
  // Keep only results[0], discard others
  results.resize(1);

  // Apply multiple testing corrections
  std::cout << std::endl << "Applying correction factors" << std::endl;

  long globalBonferroniFactor = numClusters * totalComparisons;

  // Same exception-discipline wrapper as the pair workers above (4b): an
  // export thread that throws would otherwise terminate() the whole process
  // without joining its siblings.
  std::atomic<bool> exportFailed{false};
  auto runExport = [&](int threadIdx, const std::string& clusterName, std::vector<Output>::iterator beginIt,
                       std::vector<Output>::iterator endIt, const std::string& tempFile) {
    try {
      exportResultParallel(clusterName, beginIt, endIt, tempFile, globalBonferroniFactor, motifNamesByIndex,
                           geneNamesById);
    } catch (const std::exception& e) {
      exportFailed = true;
      std::lock_guard<std::mutex> lk(stderrMutex);
      std::cerr << "Error: export worker " << threadIdx << " failed: " << e.what() << std::endl;
    } catch (...) {
      exportFailed = true;
      std::lock_guard<std::mutex> lk(stderrMutex);
      std::cerr << "Error: export worker " << threadIdx << " failed: unknown exception" << std::endl;
    }
  };

  // Process each cluster: sort results and apply Benjamini-Hochberg FDR correction
  for (std::map<std::string, std::vector<Output>>::iterator cl = results[0].begin(); cl != results[0].end(); cl++) {
    std::sort((cl->second).begin(), (cl->second).end(), [&motifNamesByIndex](const Output& a, const Output& b) {
      return sortComparisons(a, b, motifNamesByIndex);
    });
    bhCorrection(cl->second);

    // Parallelize result export for this cluster
    int interval = (int)(cl->second).size() / config.numThreads;
    std::vector<std::thread> threads(config.numThreads);
    for (int i = 0; i < config.numThreads; i++) {
      int beginIndx = i * interval;
      int endIndx = i * interval + interval - 1;
      endIndx = (endIndx >= (cl->second).size() - 1 || i == config.numThreads - 1) ? (cl->second).size() - 1 : endIndx;

      const std::string tempFileName = config.outputDirName + "temp_result_" + cl->first + "_" + std::to_string(i) +
                                       ".txt";

      threads[i] = std::thread(runExport, i, cl->first, std::begin(cl->second) + beginIndx,
                               std::begin(cl->second) + endIndx + 1, tempFileName);
    }

    for (auto& entry : threads)
      entry.join();
  }
  if (exportFailed) {
    std::cerr << "Error: one or more export workers failed; output may be incomplete." << std::endl;
    return 1;
  }

  // Merge temporary files and create final output
  const std::string finalOutputPath = config.outputDirName + config.outputFileName;
  std::ofstream outputFile(finalOutputPath, std::ios_base::out);

  if (!outputFile.is_open()) {
    std::cerr << "Error: Failed to open output file '" << finalOutputPath << "'" << std::endl;
    return 1;
  }

  Output::writeHeaders(outputFile);
  outputFile.close();

  std::cout << "Done." << std::endl;
  return 0;
}
