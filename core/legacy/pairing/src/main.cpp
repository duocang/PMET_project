//  Created by Paul Brown on 25/04/2019.
//  Copyright © 2019 Paul Brown. All rights reserved.
//

#include <dirent.h>
#include <math.h>
#include <string.h>
#include <sys/types.h>

#include <iomanip>
#include <iostream>
#include <sstream>
#include <utility>
#include <vector>

#include "Output.hpp"
#include "motif.hpp"
#include "motifComparison.hpp"
#include "utils.hpp"

// take progress up by 5% of total runtime

int main(int argc, const char* argv[]) {
  std::string inputDir(".");
  std::string promotersFile("promoter_lengths.txt");
  std::string binThreshFile("binomial_thresholds.txt");
  std::string ICFile("IC.txt");
  std::string fimoDir("fimohits/");

  std::string outputDirName("./");
  std::string outputFileName("motif_output.txt");

  std::string genesFile("input.txt");
  std::string progressFile("/Users/paulbrown/Desktop/progress.txt");
  float inc = 0.01;

  double ICthreshold = 4.0;

  std::stringstream msgString;

  for (int i = 1; i < argc; i += 2) {
    if (!strcmp(argv[i], "-h")) {
      std::cout << "pmet [-d input_directory = '.']\n"
                   "     [-g genes_file = 'input.txt']\n"
                   "     [-i ICthreshold = 4]\n"
                   "     [-p promoter_lengths_file = 'promoter_lengths.txt']\n"
                   "     [-b binomial_values_file = 'binomial_thresholds.txt']\n"
                   "     [-c information_content_file = 'IC.txt']\n"
                   "     [-f fimo_dir = 'fimohits']\n"
                   "     [-s progress_file = 'progress.log']\n"
                   "     [-o output_file = 'motif_found.txt']\n";

      std::cout << "Usage: pmet [OPTIONS]" << std::endl;
      return 0;
    } else if (!strcmp(argv[i], "-i"))
      ICthreshold = atof(argv[i + 1]);
    else if (!strcmp(argv[i], "-d"))
      inputDir = argv[i + 1];
    else if (!strcmp(argv[i], "-g"))
      genesFile = argv[i + 1];
    else if (!strcmp(argv[i], "-p"))
      promotersFile = argv[i + 1];
    else if (!strcmp(argv[i], "-b"))
      binThreshFile = argv[i + 1];
    else if (!strcmp(argv[i], "-c"))
      ICFile = argv[i + 1];
    else if (!strcmp(argv[i], "-f"))
      fimoDir = argv[i + 1];
    else if (!strcmp(argv[i], "-o"))
      outputDirName = argv[i + 1];
    else if (!strcmp(argv[i], "-s"))
      progressFile = argv[++i];
    else {
      std::cout << "Error: unknown command line switch " << argv[i] << std::endl;
      return 1;
    }
  }

  ensureEndsWith(inputDir, '/');
  ensureEndsWith(outputDirName, '/');
  ensureEndsWith(fimoDir, '/');

  fimoDir = inputDir + fimoDir;

  std::cout << "          Input parameters          " << std::endl;

  std::unordered_map<std::string, int> promSizes;
  std::unordered_map<std::string, double> topNthreshold;
  std::unordered_map<std::string, std::vector<double>> ICvalues;
  std::vector<std::string> fimoFiles;
  std::map<std::string, std::vector<std::string>> clusters;
  std::map<std::string, std::vector<Output>> results;

  writeProgress(progressFile, "Reading inputs...", 0.0);
  std::cout << "Reading inputs..." << std::endl;

  if (!loadFiles(inputDir, genesFile, promotersFile, binThreshFile, ICFile, fimoDir, promSizes, topNthreshold, ICvalues,
                 clusters, fimoFiles, results))
    exit(1);

  if (!validateInputs(promSizes, topNthreshold, ICvalues, clusters, fimoFiles)) {
    exit(1);
  }

  long numClusters = clusters.size();
  long numFimoFiles = fimoFiles.size();
  long totalComparisons = (numFimoFiles * numFimoFiles - numFimoFiles) / 2;

  std::vector<motif> allMotifs(numFimoFiles, motif());

  bool missingValues = false;

  msgString << "Reading " << fimoFiles.size() << " FIMO files..." << std::endl;
  std::cout << msgString.str();
  writeProgress(progressFile, msgString.str(), inc);

  for (long m = 0; m < numFimoFiles; ++m)
    allMotifs[m].readFimoFile(fimoDir + fimoFiles[m], inputDir, ICvalues, topNthreshold, &missingValues);
  std::cout << "Done" << std::endl;

  if (missingValues)
    exit(1);

  for (std::map<std::string, std::vector<Output>>::iterator i = results.begin(); i != results.end(); i++)
    (i->second).reserve(totalComparisons);

  long numComplete = 0;

  msgString.str("");
  msgString << "Perfomed 0 of " << totalComparisons << " pair-wise comparisons" << std::endl;
  writeProgress(progressFile, msgString.str(), inc);
  std::cout << std::unitbuf;
  std::cout << msgString.str();
  std::cout << " 10%";

  motifComparison mComp;
  for (std::vector<motif>::iterator motif1 = allMotifs.begin(); motif1 != allMotifs.end() - 1; ++motif1) {
    for (std::vector<motif>::iterator motif2 = motif1 + 1; motif2 != allMotifs.end(); ++motif2) {
      mComp.findIntersectingGenes(*motif1, *motif2, ICthreshold, promSizes);

      for (auto& cl : clusters) {
        mComp.colocTest(promSizes.size(), ICthreshold, cl.first, cl.second);
        results[cl.first].push_back(Output(motif1->getMotifName(), motif2->getMotifName(), mComp));
      }

      std::cout << "\b\b\b";
      double progVal = 0.1 + double(0.8 * ++numComplete) / totalComparisons;
      std::cout << std::setw(2) << long(progVal * 100) << "%";
    }

    msgString << "Perfomed " << numComplete << " of " << totalComparisons << " pair-wise comparisons" << std::endl;
    writeProgress(progressFile, msgString.str(), 0.0);
  }

  std::ofstream outputFile;
  outputFile.open(outputDirName + outputFileName, std::ios_base::out);

  if (!outputFile.is_open()) {
    std::cout << "Error openning results file " << (outputDirName + outputFileName) << std::endl;
    exit(1);
  }

  Output::writeHeaders(outputFile);

  std::cout << std::endl << "Applying correction factors" << std::endl;
  writeProgress(progressFile, "Applying correction factors", 0.02);

  long globalBonferroniFactor = numClusters * totalComparisons;
  for (std::map<std::string, std::vector<Output>>::iterator cl = results.begin(); cl != results.end(); cl++) {
    std::sort((cl->second).begin(), (cl->second).end(), sortComparisons);
    bhCorrection(cl->second);

    for (std::vector<Output>::iterator mc = std::begin(cl->second); mc != std::end(cl->second); mc++) {
      outputFile << cl->first << '\t';
      mc->printMe(globalBonferroniFactor, outputFile);
    }
  }
  outputFile.close();

  std::cout << "Done." << std::endl;
  writeProgress(progressFile, "Done", 0.0);
  return 0;
}
