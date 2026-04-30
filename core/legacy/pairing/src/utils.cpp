#include "utils.hpp"

#include <dirent.h>
#include <math.h>
#include <string.h>
#include <sys/types.h>

#include <iomanip>
#include <iostream>
#include <sstream>
#include <utility>
#include <vector>

void ensureEndsWith(std::string& str, char character) {
  if (!str.empty() && str.back() != character) {
    str += character;
  }
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
               std::unordered_map<std::string, int>& promSizes, std::unordered_map<std::string, double>& topNthreshold,
               std::unordered_map<std::string, std::vector<double>>& ICvalues,
               std::map<std::string, std::vector<std::string>>& clusters, std::vector<std::string>& fimoFiles,
               std::map<std::string, std::vector<Output>>& results) {
  std::cout << "Reading input files..." << std::endl;

  std::stringstream promFileContent;
  fastFileRead(path + promotersFile, promFileContent);

  std::string geneID, len;

  while (promFileContent >> geneID >> len) promSizes.emplace(geneID, stoi(len));

  std::cout << "Universe size is " << promSizes.size() << std::endl;

  std::stringstream binFileContent;
  fastFileRead(path + binThreshFile, binFileContent);

  std::string motifID, threshold;

  while (binFileContent >> motifID >> threshold) topNthreshold.emplace(motifID, stof(threshold));

  std::ifstream ifs(path + ICFile);

  if (!ifs) {
    std::cout << "Error: Cannot open file " << path + ICFile << std::endl;
    return false;
  }

  std::string line;
  while (std::getline(ifs, line)) {
    std::istringstream ics(line);
    double score;
    ics >> motifID;

    ICvalues.emplace(motifID, std::vector<double>());

    while (ics >> score) ICvalues[motifID].push_back(score);
  }

  std::stringstream geneFileContent;
  std::string clusterID;

  fastFileRead(genesFile, geneFileContent);

  long genesFound = 0;

  std::map<std::string, std::vector<std::string>>::iterator got;
  while (geneFileContent >> clusterID >> geneID) {
    if ((got = clusters.find(clusterID)) == clusters.end()) {
      clusters.emplace(clusterID, std::vector<std::string>());
      results.emplace(clusterID, std::vector<Output>());
    }

    clusters[clusterID].push_back(geneID);
    genesFound++;
  }
  std::cout << "Found " << genesFound << " gene IDs in " << clusters.size() << " clusters" << std::endl;

  for (auto& cl : clusters) std::sort(cl.second.begin(), cl.second.end());

  std::string searchDir = fimoDir;

  DIR* pDir = opendir(searchDir.c_str());

  if (!pDir) {
    std::cout << "Error: Cannot find directory " << searchDir << std::endl;
    return false;
  }

  struct dirent* fp;
  while ((fp = readdir(pDir)))
    if (fp->d_name[0] != '.')
      fimoFiles.push_back(fp->d_name);

  closedir(pDir);

  std::sort(fimoFiles.begin(), fimoFiles.end(), [](const std::string& a, const std::string& b) {
    return (a.compare(0, a.size() - 4, b, 0, b.size() - 4) < 0);
  });

  return true;
}

bool fastFileRead(std::string filename, std::stringstream& results) {
  long flength;
  long numLines = 0;
  bool success = false;

  std::ifstream ifs(filename, std::ifstream::binary);

  if (!ifs) {
    std::cout << "Error: Cannot open file " << filename << std::endl;
    exit(1);
  }

  ifs.seekg(0, ifs.end);
  flength = ifs.tellg();
  ifs.seekg(0, ifs.beg);

  std::string buffer(flength, '\0');

  if (!ifs.read(&buffer[0], flength))
    std::cout << "Error reading file " << filename << std::endl;
  else {
    results.str(buffer);
    success = true;
  }

  ifs.close();

  if (success) {
    numLines = std::count(std::istreambuf_iterator<char>(results), std::istreambuf_iterator<char>(), '\n');
    results.unget();
    if (results.get() != '\n')
      numLines++;
    results.seekg(0);

  } else
    exit(1);

  return numLines;
}

bool validateInputs(const std::unordered_map<std::string, int>& promSizes,
                    const std::unordered_map<std::string, double>& topNthreshold,
                    const std::unordered_map<std::string, std::vector<double>>& ICvalues,
                    const std::map<std::string, std::vector<std::string>>& clusters,
                    const std::vector<std::string> fimoFiles) {
  std::cout << "Validating inputs...";

  if (clusters.empty()) {
    std::cout << "Error : No gene clusters found!" << std::endl;
    return false;
  }

  if (fimoFiles.empty()) {
    std::cout << "Error : FIMO files not found!" << std::endl;
    return false;
  }

  if (topNthreshold.empty()) {
    std::cout << "Error : Binomial threshold values not found!" << std::endl;
    return false;
  }

  if (ICvalues.empty()) {
    std::cout << "Error : Information Content values not found!" << std::endl;
    return false;
  }

  if (promSizes.empty()) {
    std::cout << "Error : No promoter sizes found!" << std::endl;
    return false;
  }

  bool noError = true;
  for (auto cl = std::begin(clusters); cl != std::end(clusters); cl++) {
    for (auto gene = std::begin(cl->second); gene != std::end(cl->second); gene++) {
      if (promSizes.find(*gene) == promSizes.end()) {
        std::cout << "Error : Gene ID " << *gene << " (" << cl->first << ") " << " not found in promoter lengths file!"
                  << std::endl;
        noError = false;
      }
    }
  }

  if (noError)
    std::cout << "OK";
  std::cout << std::endl;
  return noError;
}

void bhCorrection(std::vector<Output>& motifs) {
  std::vector<std::pair<long, double>> pValues;
  long n = motifs.size();

  pValues.reserve(n);

  for (long i = 0; i < n; i++) pValues.push_back(std::make_pair(i, motifs[i].getpValue()));

  std::sort(pValues.begin(), pValues.end(),
            [](const std::pair<long, double>& a, const std::pair<long, double>& b) { return a.second > b.second; });

  for (long i = 0; i < n; i++) {
    pValues[i].second *= (n / (n - i));
    if (i && pValues[i].second > pValues[i - 1].second)
      pValues[i].second = pValues[i - 1].second;

    motifs[pValues[i].first].setBHCorrection(pValues[i].second);
  }
}
