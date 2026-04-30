#include <dirent.h>
// #include <gperftools/profiler.h>
#include <math.h>
#include <string.h>
#include <sys/types.h>

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <thread>
#include <utility>
#include <vector>

#include "Output.hpp"
#include "motif.hpp"
#include "motifComparison.hpp"

int output(std::vector<motif>::iterator first, std::vector<motif>::iterator later, std::vector<motif>::iterator last,
           const std::map<std::string, std::vector<GeneId>>& clusters, motifComparison mComp,
           std::map<std::string, std::vector<Output>>* results, double ICthreshold, const std::vector<int>& promSizes,
           const std::vector<motif>& allMotifs, long numComplete, long totalComparisons,
           const std::string& outputDirName, bool isPoisson);

int outputParallel(const std::vector<int>& motifsIndx, std::vector<motif>* allMotifs,
                   const std::map<std::string, std::vector<GeneId>>& clusters, motifComparison mComp,
                   std::map<std::string, std::vector<Output>>* results, double ICthreshold,
                   const std::vector<int>& promSizes, long numComplete, long totalComparisons,
                   const std::string& outputDirName, bool isPoisson, int minhashMinIntersection);
void exportResultParallel(std::string cluster, std::vector<Output>::iterator beginIt,
                          std::vector<Output>::iterator endIt, std::string outFile, long globalBonferroniFactor,
                          const std::vector<std::string>& motifNamesByIndex,
                          const std::vector<std::string>& geneNamesById);

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

void bhCorrection(std::vector<Output>& motifs);
// void writeProgressFile(double val, std::string msg, std::string path);
void writeProgress(const std::string& fname, const std::string& message, float inc);
std::vector<std::vector<int>> fairDivision(const std::vector<int>& input, const std::vector<long long>& weights,
                                           int numGroups);
// take progress up by 5% of total runtime
