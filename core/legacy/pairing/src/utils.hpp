#ifndef utils_hpp
#define utils_hpp

#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

#include "Output.hpp"

void ensureEndsWith(std::string& str, char character);

void writeProgress(const std::string& fname, const std::string& message, float inc);

bool loadFiles(const std::string& path, const std::string& genesFile, const std::string& promotersFile,
               const std::string& binThreshFile, const std::string& ICFile, const std::string& fimoDir,
               std::unordered_map<std::string, int>& promSizes, std::unordered_map<std::string, double>& topNthreshold,
               std::unordered_map<std::string, std::vector<double>>& ICvalues,
               std::map<std::string, std::vector<std::string>>& clusters, std::vector<std::string>& fimoFiles,
               std::map<std::string, std::vector<Output>>& results);

bool validateInputs(const std::unordered_map<std::string, int>& promSizes,
                    const std::unordered_map<std::string, double>& topNthreshold,
                    const std::unordered_map<std::string, std::vector<double>>& ICvalues,
                    const std::map<std::string, std::vector<std::string>>& clusters,
                    const std::vector<std::string> fimoFiles);

bool fastFileRead(std::string filename, std::stringstream& results);

void bhCorrection(std::vector<Output>& motifs);

#endif /* utils_hpp */
