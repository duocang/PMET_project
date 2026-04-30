// motif.cpp — load a motif's hits from a fimohits file (text or binary)
// and expose the per-gene queries pairing needs. Original 2019 © Paul Brown.

#include "motif.hpp"

#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

bool sortHits(const motifInstance& a, const motifInstance& b) {
  // sort ascending
  return (a.getPValue() < b.getPValue());
}

/* Binary fimohits format — keep in sync with
 * src/indexing/fused_fimo/src/pmet_index/pmet-fimo-binary.h
 *
 *   Header (24 bytes, packed)
 *     magic[8]       = "PMETBN01"
 *     num_hits       uint32
 *     name_pool_size uint32
 *     motif_name_len uint32
 *     reserved       uint32
 *   motif_name      char[motif_name_len]   (no NUL)
 *   name pool       char[name_pool_size]   (NUL-separated)
 *   hits            PmetBinHit[num_hits]
 *
 *   PmetBinHit (32 bytes, packed)
 *     uint32 seq_name_offset
 *     uint32 startPos
 *     uint32 stopPos
 *     uint8  strand
 *     uint8  pad[3]
 *     double score
 *     double pVal
 */
namespace {
constexpr char kBinaryMagic[8] = {'P', 'M', 'E', 'T', 'B', 'N', '0', '1'};
constexpr std::size_t kBinaryMagicLen = 8;
constexpr std::size_t kBinaryHeaderSize = 24;
constexpr std::size_t kBinaryHitSize = 32;

#pragma pack(push, 1)
struct BinHit {
  std::uint32_t seq_name_offset;
  std::uint32_t startPos;
  std::uint32_t stopPos;
  std::uint8_t strand;
  std::uint8_t _pad[3];
  double score;
  double pVal;
};
#pragma pack(pop)
static_assert(sizeof(BinHit) == kBinaryHitSize, "BinHit must be 32 bytes");

bool isBinaryFimohits(std::ifstream& ifs) {
  char magic[kBinaryMagicLen] = {0};
  ifs.read(magic, kBinaryMagicLen);
  bool match = ifs.gcount() == static_cast<std::streamsize>(kBinaryMagicLen) &&
               std::memcmp(magic, kBinaryMagic, kBinaryMagicLen) == 0;
  // Reset state and rewind so the text path can re-use the same stream.
  ifs.clear();
  ifs.seekg(0, std::ios::beg);
  return match;
}
} // namespace

bool motif::readBinaryFimoFile(const std::string& filename, const std::unordered_map<std::string, GeneId>& geneNameToId,
                               std::unordered_map<std::string, std::vector<double>>& ICvalues,
                               std::unordered_map<std::string, double>& topNthreshold, bool* missingValues) {
  std::ifstream ifs(filename, std::ifstream::binary);
  if (!ifs) {
    std::cerr << "Error: Cannot open fimo file " << filename << std::endl;
    return false;
  }

  // Establish file size up front so we can bounds-check the header fields
  // before allocating any buffers — a corrupted header that claims, e.g.,
  // num_hits = 4G would otherwise trigger a 128 GB std::vector allocation.
  ifs.seekg(0, std::ios::end);
  const std::streamoff fileSize = ifs.tellg();
  ifs.seekg(0, std::ios::beg);
  if (fileSize < static_cast<std::streamoff>(kBinaryHeaderSize)) {
    std::cerr << "Error: Binary fimohits file too small for header in " << filename << std::endl;
    return false;
  }

  // Header: 8-byte magic + 4 uint32 fields
  char header[kBinaryHeaderSize];
  if (!ifs.read(header, kBinaryHeaderSize)) {
    std::cerr << "Error: Truncated binary fimohits header in " << filename << std::endl;
    return false;
  }
  if (std::memcmp(header, kBinaryMagic, kBinaryMagicLen) != 0) {
    std::cerr << "Error: Bad binary fimohits magic in " << filename << std::endl;
    return false;
  }
  std::uint32_t num_hits, name_pool_size, motif_name_len, reserved;
  std::memcpy(&num_hits, header + 8, 4);
  std::memcpy(&name_pool_size, header + 12, 4);
  std::memcpy(&motif_name_len, header + 16, 4);
  std::memcpy(&reserved, header + 20, 4);
  (void)reserved;

  // Verify the file actually contains the bytes the header promises.
  const std::uintmax_t expectedPayload = static_cast<std::uintmax_t>(motif_name_len) +
                                         static_cast<std::uintmax_t>(name_pool_size) +
                                         static_cast<std::uintmax_t>(num_hits) * sizeof(BinHit);
  if (expectedPayload > static_cast<std::uintmax_t>(fileSize) - kBinaryHeaderSize) {
    std::cerr << "Error: Binary fimohits header claims " << expectedPayload << " payload bytes but file has only "
              << (static_cast<std::uintmax_t>(fileSize) - kBinaryHeaderSize) << " in " << filename << std::endl;
    return false;
  }

  std::string motifNameStr(motif_name_len, '\0');
  if (motif_name_len > 0 && !ifs.read(motifNameStr.data(), motif_name_len)) {
    std::cerr << "Error: Truncated motif name in " << filename << std::endl;
    return false;
  }

  std::vector<char> namePool(name_pool_size);
  if (name_pool_size > 0 && !ifs.read(namePool.data(), name_pool_size)) {
    std::cerr << "Error: Truncated name pool in " << filename << std::endl;
    return false;
  }

  // One read for the entire SoA hit array — no parsing required.
  std::vector<BinHit> hits(num_hits);
  if (num_hits > 0 &&
      !ifs.read(reinterpret_cast<char*>(hits.data()), static_cast<std::streamsize>(num_hits) * sizeof(BinHit))) {
    std::cerr << "Error: Truncated hits in " << filename << std::endl;
    return false;
  }
  ifs.close();

  motifName = motifNameStr;

  // motifLength: derived from first hit (start/stop are inclusive 1-based, matches text path)
  motifLength = (num_hits > 0) ? static_cast<int>(hits[0].stopPos) - static_cast<int>(hits[0].startPos) + 1 : 0;

  lookupICAndThreshold(filename, ICvalues, topNthreshold, missingValues);

  // Convert SoA hits -> per-gene `instances` map. Skip hits whose gene isn't in
  // the universe (data-quality issue); flag missingValues but keep going so the
  // caller can collect every problem in one pass.
  long totalHits = 0;
  for (const BinHit& h : hits) {
    const char* gene_name = namePool.data() + h.seq_name_offset;
    auto geneIt = geneNameToId.find(gene_name);
    if (geneIt == geneNameToId.end()) {
      std::cerr << "Error : Gene " << gene_name << " from motif " << motifName << " not found in promoter lengths file!"
                << std::endl;
      *missingValues = true;
      continue;
    }
    instances[geneIt->second].emplace_back(static_cast<int>(h.startPos), static_cast<int>(h.stopPos), h.score, h.pVal);
    ++totalHits;
  }

  finalizeAfterLoad(totalHits);
  return true;
}

namespace {
// SplitMix64 finalizer (Steele/Lea 2014, used by Java's SplittableRandom).
// Fast, integer-only, with strong avalanche on the low bits — exactly what we
// need for per-slot MinHash permutations of the gene-id space. The three
// constants below are the published, canonical SplitMix64 mixing constants;
// don't change them without revisiting hash quality.
//   0x9E3779B97F4A7C15  = floor(2^64 / phi), the golden-ratio increment
//   0xBF58476D1CE4E5B9  = published mixer #1
//   0x94D049BB133111EB  = published mixer #2
inline std::uint64_t splitmix64(std::uint64_t x) {
  x += 0x9E3779B97F4A7C15ULL;
  x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
  x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
  x ^= (x >> 31);
  return x;
}

// Per-slot seed offset: any non-zero pattern works — picked 0xA5...A5 (the
// classic 0b1010...1010 byte) so slot 0 isn't accidentally splitmix64(0).
constexpr std::uint64_t kMinHashSlotSeedBase = 0xA5A5A5A5A5A5A5A5ULL;
} // namespace

void motif::buildMinHashSketch() {
  for (int k = 0; k < kMinHashK; ++k) {
    // Each slot uses a different permutation of the gene-id space, derived by
    // mixing the slot index into a fixed seed.
    const std::uint64_t seed = splitmix64(static_cast<std::uint64_t>(k) + kMinHashSlotSeedBase);
    std::uint64_t minH = std::numeric_limits<std::uint64_t>::max();
    for (GeneId g : sortedGeneIDs) {
      std::uint64_t h = splitmix64(static_cast<std::uint64_t>(g) ^ seed);
      if (h < minH)
        minH = h;
    }
    minhash[k] = minH;
  }
}

void motif::lookupICAndThreshold(const std::string& filename,
                                 std::unordered_map<std::string, std::vector<double>>& ICvalues,
                                 std::unordered_map<std::string, double>& topNthreshold, bool* missingValues) {
  if (auto it = ICvalues.find(motifName); it != ICvalues.end()) {
    IC = it->second;
    if (static_cast<int>(IC.size()) != motifLength) {
      std::cerr << "Error : Motif " << motifName << "  IC values do not correspond to length of motif (" << motifLength
                << ")!" << std::endl;
      std::cerr << "file=" << filename << std::endl;
      *missingValues = true;
    }
    // Precompute prefix sum for O(1) range IC queries
    ICPrefixSum.resize(IC.size() + 1, 0.0);
    for (std::size_t pi = 0; pi < IC.size(); pi++)
      ICPrefixSum[pi + 1] = ICPrefixSum[pi] + IC[pi];
  } else {
    std::cerr << "Error : Motif " << motifName << " not found in IC file!" << std::endl;
    *missingValues = true;
  }

  if (auto it = topNthreshold.find(motifName); it != topNthreshold.end()) {
    binomialThreshold = it->second;
  } else {
    std::cerr << "Error : Motif " << motifName << " not found in binomial thresholds file!" << std::endl;
    *missingValues = true;
  }
}

void motif::finalizeAfterLoad(long totalHits) {
  for (auto& kv : instances) {
    std::sort(kv.second.begin(), kv.second.end(), sortHits);
  }
  sortedGeneIDs.clear();
  sortedGeneIDs.reserve(instances.size());
  for (const auto& kv : instances)
    sortedGeneIDs.push_back(kv.first);
  std::sort(sortedGeneIDs.begin(), sortedGeneIDs.end());
  totalInstances = totalHits;

  buildMinHashSketch();

  std::cout << "Motif " << motifName << " has " << totalHits << " occurrences in " << instances.size() << "  genes"
            << std::endl;
}

int motif::minhashMatchCount(const motif& other) const {
  int matches = 0;
  for (int k = 0; k < kMinHashK; ++k) {
    if (minhash[k] == other.minhash[k])
      ++matches;
  }
  return matches;
}

void motif::setMotifName(const std::string& motif) {
  motifName = motif;
}

std::string motif::getMotifName() const {
  return motifName;
}

void motif::setThreshold(double thresh) {
  binomialThreshold = thresh;
}

double motif::getThreshold() const {
  return binomialThreshold;
}

bool motif::readFimoFile(const std::string filename, const std::unordered_map<std::string, GeneId>& geneNameToId,
                         std::unordered_map<std::string, std::vector<double>>& ICvalues,
                         std::unordered_map<std::string, double>& topNthreshold, bool* missingValues) {
  instances.clear();
  sortedGeneIDs.clear();
  totalInstances = 0;

  // get size of file
  long flength;
  bool success = false;

  std::ifstream ifs(filename, std::ifstream::binary);

  if (!ifs) {
    std::cerr << "Error: Cannot open fimo file " << filename << std::endl;
    return success;
  }

  // Auto-detect binary fimohits via magic header
  if (isBinaryFimohits(ifs)) {
    ifs.close();
    return readBinaryFimoFile(filename, geneNameToId, ICvalues, topNthreshold, missingValues);
  }

  ifs.seekg(0, ifs.end);
  flength = ifs.tellg();
  ifs.seekg(0, ifs.beg);

  // read all file in to memory

  std::string buffer(flength, '\0');
  std::stringstream results;

  if (!ifs.read(&buffer[0], flength))
    std::cerr << "Error reading fimo file " << filename << std::endl;
  else {
    results.str(buffer);
    success = true;
  }

  ifs.close();

  if (success) {
    std::string motif, gene;
    std::string strandIgnored; // parsed to advance the stream, then discarded
    int first, last;
    double p1, p2;

    auto appendInstance = [&](const std::string& geneName) {
      auto geneIt = geneNameToId.find(geneName);
      if (geneIt == geneNameToId.end()) {
        std::cerr << "Error : Gene " << geneName << " from motif " << motifName
                  << " not found in promoter lengths file!" << std::endl;
        *missingValues = true;
        return;
      }

      auto iter = instances.emplace(geneIt->second, std::vector<motifInstance>());
      iter.first->second.emplace_back(first, last, p1, p2);
    };

    std::string line;
    if (!std::getline(results, line)) {
      return false;
    }

    auto parseLine = [&](const std::string& rawLine) {
      std::istringstream lineStream(rawLine);
      std::string ignoredSequence;
      if (!(lineStream >> motif >> gene >> first >> last >> strandIgnored >> p1 >> p2)) {
        std::cerr << "Error parsing fimo file " << filename << std::endl;
        success = false;
        return false;
      }
      (void)(lineStream >> ignoredSequence); // optional matched_sequence column
      return true;
    };

    while (line.find_first_not_of(" \t\r") == std::string::npos && std::getline(results, line)) {}
    if (line.find_first_not_of(" \t\r") == std::string::npos || !parseLine(line)) {
      return false;
    }

    // These parts will be same fo revery line
    motifName = motif; // in case different from file name
    motifLength = last - first + 1;

    lookupICAndThreshold(filename, ICvalues, topNthreshold, missingValues);

    appendInstance(gene);

    // reads rest of file
    while (std::getline(results, line)) {
      if (line.find_first_not_of(" \t\r") == std::string::npos)
        continue;
      if (!parseLine(line)) {
        return false;
      }
      appendInstance(gene);
    }

    long totalHits = 0;
    for (const auto& kv : instances)
      totalHits += static_cast<long>(kv.second.size());
    finalizeAfterLoad(totalHits);
  }

  return success; // will be true as long as this fimo file read ok but if missingValues set then program will stop
                  // after all fimo files read
}

void motif::getListofGenes(std::vector<GeneId>& genes) const {
  genes = sortedGeneIDs;
}

const std::vector<GeneId>& motif::getSortedGeneIDs() const {
  return sortedGeneIDs;
}

long motif::getNumInstances(GeneId geneID) const {
  return instances.at(geneID).size();
}

const motifInstance& motif::getInstance(GeneId gene, long idx) const {
  return instances.at(gene)[idx];
}

double motif::getForwardICScore(int overlapLength) const {
  // fwdIC is defined as the sum of the IC of the overlap from the beginning of the motif
  // O(1) via prefix sum: sum of IC[0..overlapLength-1]
  return ICPrefixSum[overlapLength];
}

double motif::getReverseICScore(int overlapLength) const {
  // revIC is defined as the sum of IC in the overlapping end of motif
  // O(1) via prefix sum: sum of IC[size-overlapLength..size-1]
  return ICPrefixSum[IC.size()] - ICPrefixSum[IC.size() - overlapLength];
}

int motif::getLength() const {
  return motifLength;
}

long motif::getNumGenesWithMotif() const {
  return static_cast<long>(sortedGeneIDs.size());
}

long motif::getTotalInstances() const {
  return totalInstances;
}
