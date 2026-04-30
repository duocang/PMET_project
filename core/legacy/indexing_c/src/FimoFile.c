#include "FimoFile.h"

#include <string.h>  // For strtok
#include <stdbool.h> // For bool
#include <math.h>
#include <float.h> // for DBL_MAX
#include <sys/stat.h> // For mkdir

/**
 * Round x to d significant digits.
 * Matches the RND macro used in FIMO (macros.h) to ensure cross-platform
 * consistency of floating-point results.
 */
static double roundToSignificantDigits(double x, int d)
{
  if (x > 0.0) {
    double z = pow(10.0, ceil(d - 1 - log10(x)));
    return rint(z * x) / z;
  } else if (x < 0.0) {
    double z = pow(10.0, ceil(d - 1 - log10(-x)));
    return -rint(z * (-x)) / z;
  }
  return 0.0;
}

FimoFile *createFimoFile()
{
  FimoFile *file = (FimoFile *)new_malloc(sizeof(FimoFile));
  if (!file)
  {
    fprintf(stderr, "Error: FimoFile Can not be created.\n");
    return NULL;
  }
  // Setting the entire structure to zero ensures that all members are `NULL` or `0`:
  memset(file, 0, sizeof(FimoFile));

  file->numLines = 0;
  file->motifName = NULL;
  file->motifLength = 0;
  file->fileName = NULL;
  file->outDir = NULL;
  file->binScore = false;
  file->hasMotifAlt = false;
  file->ht = NULL;
  file->ht = createHashTable();

  if (!file->ht)
  {
    fprintf(stderr, "Error: Memory allocation failed for Hash table *ht in createFimoFile function.\n");
    exit(1); // Or handle the error in another way if you prefer
  }
  return file;
}

void initFimoFile(FimoFile *file,
                  int numLines,
                  char *motifName,
                  int motifLength,
                  char *fileName,
                  char *outDir,
                  bool hasMotifAlt,
                  bool binScore)
{
  if (file == NULL)
  {
    fprintf(stderr, "Error: Provided FimoFile pointer is NULL in initFimoFile.\n");
    return;
  }

  // 不要使用 memset,保留已经分配的 ht
  // memset(file, 0, sizeof(FimoFile)); // 删除这行

  file->numLines = numLines;
  file->motifLength = motifLength;
  file->hasMotifAlt = hasMotifAlt;
  file->binScore = binScore;

  // 创建新的字符串副本
  file->motifName = motifName ? new_strdup(motifName) : NULL;
  file->fileName = fileName ? new_strdup(fileName) : NULL;
  file->outDir = outDir ? new_strdup(outDir) : NULL;

  // 检查内存分配
  if ((motifName && !file->motifName) || (fileName && !file->fileName) || (outDir && !file->outDir))
  {
    fprintf(stderr, "Error: Memory allocation failed for strings in initFimoFile.\n");
    // 清理已分配的内存
    new_free(file->motifName);
    new_free(file->fileName);
    new_free(file->outDir);
    return;
  }

  // 如果 ht 还未初始化,则创建
  if (file->ht == NULL)
  {
    file->ht = createHashTable();
    if (file->ht == NULL)
    {
      fprintf(stderr, "Error: Memory allocation failed for hash table in initFimoFile.\n");
      new_free(file->motifName);
      new_free(file->fileName);
      new_free(file->outDir);
      return;
    }
  }
}

bool readFimoFile(FimoFile *fimoFile)
{
  // 确保 fimoFile 及其哈希表已初始化
  if (!fimoFile || !fimoFile->ht || !fimoFile->fileName || !fimoFile->motifName || !fimoFile->outDir)
  {
    fprintf(stderr, "Error: Invalid FimoFile provided.\n\n");
    return false;
  }

  char *fileContent;
  size_t numLines = readFileAndCountLines(fimoFile->fileName, &fileContent); // 使用 size_t

  if (numLines <= 1) // 至少需要 header + 1 行数据
  {
    new_free(fileContent);
    printf("Error: Invalid FimoFile\n");
    return false;
  }

  numLines--; // 减去 header 行
  printf("Reading %s with %zu records...\n", fimoFile->fileName, numLines);

  fimoFile->numLines = (int)numLines; // 显式转换

  char *saveptr;
  char *line = strtok_r(fileContent, "\n", &saveptr);
  line = strtok_r(NULL, "\n", &saveptr); // 跳过 header
  int currentLineNum = 1; // 从1开始,因为跳过了header

  MotifHitVector *currentVec = createMotifHitVector();
  if (!currentVec)
  {
    new_free(fileContent);
    fprintf(stderr, "Error: Failed to create MotifHitVector.\n");
    return false;
  }

  char prevGeneID[256] = "NO_GENE_YET";

  while (line)
  {
    char motif[256], motifAlt[256], geneID[256], sequence[256];
    int start, stop, binScore;
    char strand;
    double score, pval;
    MotifHit hit;

    // 解析每一行
    int fieldsRead;
    if (fimoFile->binScore)
    {
      fieldsRead = sscanf(line, "%255s %255s %255s %d %d %c %lf %lf %255s %d",
                          motif, motifAlt, geneID, &start, &stop, &strand, &score, &pval, sequence, &binScore);
      if (fieldsRead != 10)
      {
        fprintf(stderr, "Error: Failed to parse line %d (expected 10 fields, got %d).\n", currentLineNum, fieldsRead);
        deleteMotifHitVector(currentVec);
        new_free(fileContent);
        return false;
      }
      initMotifHit(&hit, motif, motifAlt, geneID, start, stop, strand, score, pval, sequence, binScore);
    }
    else
    {
      fieldsRead = sscanf(line, "%255s %255s %255s %d %d %c %lf %lf %255s",
                          motif, motifAlt, geneID, &start, &stop, &strand, &score, &pval, sequence);
      if (fieldsRead != 9)
      {
        fprintf(stderr, "Error: Failed to parse line %d (expected 9 fields, got %d).\n", currentLineNum, fieldsRead);
        deleteMotifHitVector(currentVec);
        new_free(fileContent);
        return false;
      }
      initMotifHit(&hit, motif, motifAlt, geneID, start, stop, strand, score, pval, sequence, -1);
    }

    fimoFile->motifLength = (stop - start) + 1;

    // 检查 geneID 是否改变
    if (strcmp(prevGeneID, geneID) != 0)
    {
      // 保存之前的 vector
      if (currentVec && currentVec->size > 0)
      {
        putHashTable2(fimoFile->ht, prevGeneID, currentVec, adapterDeleteFunction);
      }

      // 为新基因创建新 vector
      if (currentLineNum > 1)
      {
        currentVec = createMotifHitVector();
        if (!currentVec)
        {
          new_free(fileContent);
          fprintf(stderr, "Error: Failed to create MotifHitVector.\n");
          return false;
        }
      }
      strcpy(prevGeneID, geneID);
    }

    pushMotifHitVectorMove(currentVec, &hit);

    line = strtok_r(NULL, "\n", &saveptr);
    currentLineNum++;
  }

  // 添加最后一个 MotifHitVector
  if (currentVec && currentVec->size > 0)
  {
    putHashTable2(fimoFile->ht, prevGeneID, currentVec, adapterDeleteFunction);
  }
  else if (currentVec)
  {
    deleteMotifHitVector(currentVec);
  }

  new_free(fileContent);
  return true;
}

void processFimoFile(FimoFile *fimoFile, int k, int N, PromoterList *promSizes)
{
  if (!fimoFile || !fimoFile->ht || !promSizes)
  {
    fprintf(stderr, "Error: Null pointer passed to processFimoFile.\n");
    exit(1);
  }

  ScoreLabelPairVector *binThresholds = createScoreLabelPairVector();

  if (!binThresholds)
  {
    fprintf(stderr, "Error: Failed to create binThresholds vector.\n");
    exit(1);
  }

  // 遍历每一个桶（bucket）
  int i;
  for (i = 0; i < TABLE_SIZE; ++i)
  {
    struct kv *current = fimoFile->ht->table[i];
    // 如果当前桶非空，遍历其链表
    while (current != NULL)
    {
      // // 这里，current->key 和 current->value 就是链表中当前节点的键和值。
      // printf("Key: %s, Value:\n", current->key);
      // printMotifHitVector(current->value);

      char *geneID = current->key;
      if (!geneID)
      {
        fprintf(stderr, "Error: Encountered a hash table with a null key.\n");
        deleteScoreLabelVectorContents(binThresholds);
        exit(1);
      }

      MotifHitVector *vec = current->value;
      if (!vec)
      {
        fprintf(stderr, "Error: Encountered a hash table with a null value.\n");
        deleteScoreLabelVectorContents(binThresholds);
        exit(1);
      }
      sortMotifHitVectorByPVal(vec);

      // Remove overlapping motif hits using mark-compact (O(n) instead of O(n²))
      // For each of the top-k retained hits, remove any later hit that overlaps with it
#ifdef DEBUG
      printf("Delete motif hit in vector with overlap\n\n");
#endif
      {
        // Allocate a boolean array to mark hits for removal
        size_t vecSize = vec->size;
        char *removed = (char *)new_calloc(vecSize, sizeof(char));
        if (!removed)
        {
          fprintf(stderr, "Error: Failed to allocate removal markers.\n");
          exit(1);
        }

        size_t keptCount = 0;  // number of kept (non-overlapping) top hits so far
        size_t j;
        for (j = 0; j < vecSize && keptCount < (size_t)k; j++)
        {
          if (removed[j]) continue;
          // This hit is kept as one of the top-k
          // Mark all subsequent hits that overlap with it
          size_t m;
          for (m = j + 1; m < vecSize; m++)
          {
            if (!removed[m] && motifsOverlap(&vec->hits[j], &vec->hits[m]))
            {
#ifdef DEBUG
              printf("Key: %s\n", current->key);
#endif
              removed[m] = 1;
            }
          }
          keptCount++;
        }

        // Compact: move non-removed elements to the front
        size_t writeIdx = 0;
        for (j = 0; j < vecSize; j++)
        {
          if (!removed[j])
          {
            if (writeIdx != j)
            {
              vec->hits[writeIdx] = vec->hits[j];
            }
            writeIdx++;
          }
          else
          {
            deleteMotifHitContents(&vec->hits[j]);
          }
        }
        vec->size = writeIdx;
        new_free(removed);
      }

      if (vec->size > k)
      {
        retainTopKMotifHits(vec, k);
      }

      // Find the promoter size for the current gene in promSizes map
      size_t promterLength = findPromoterLength(promSizes, geneID);
      if (promterLength == -1)
      {
        printf("Error: Sequence ID: %s not found in promoter lengths file!\n", geneID);
        exit(1);
      }

      // Calculate the binomial p-value and the corresponding bin value for this gene
      Pair binom_p = geometricBinTest(current->value, promterLength, fimoFile->motifLength);

      // Save the best bin value for this gene in the binThresholds vector
      pushBack(binThresholds, binom_p.score, geneID);

      // Resize the hits for this gene if necessary based on the bin value
      // void` pointers are general-purpose pointers that can point to any
      // data type, but they don't carry type information, so you can't
      // directly dereference them or access their members

      MotifHitVector *temp = current->value;
      if (temp->size > (binom_p.idx + 1))
      {
        retainTopKMotifHits(current->value, binom_p.idx + 1);
      }

      current = current->next;
    }
  }

  // Sort the binThresholds vector by ascending score
  sortVector(binThresholds);

  // Save the Nth best bin value and gene ID to the thresholds file
  if (binThresholds->size > N)
    retainTopN(binThresholds, N);

  /****************************************************************************
   * Write PMET index result
   ****************************************************************************/
  // Create fimohits subdirectory if it doesn't exist
  char *fimohitsDir = paste(3, "", removeTrailingSlashAndReturn(fimoFile->outDir), "/", "fimohits");
  mkdir(fimohitsDir, 0755);

  char *motifHitFilePath = paste(4, "", fimohitsDir, "/", fimoFile->motifName, ".txt");
  int ii;
  for (ii = 0; ii < binThresholds->size; ii++)
  {
    char *binThresholdName = binThresholds->items[ii].label;
    MotifHitVector *vec = getHashTable(fimoFile->ht, binThresholdName);
    writeVectorToFile(vec, motifHitFilePath);
  }
  new_free(fimohitsDir);

  /****************************************************************************
   * Write "binomial_thresholds.txt"
   ****************************************************************************/
  char *binomialThresholdFilePaht = paste(3, "", removeTrailingSlashAndReturn(fimoFile->outDir), "/", "binomial_thresholds.txt");

  #pragma omp critical(binomial_write)
  {
    FILE *file = fopen(binomialThresholdFilePaht, "a");

    if (file == NULL)
    {
      fprintf(stderr, "Failed to open the file for writing.\n");
      new_free(motifHitFilePath);
      new_free(binomialThresholdFilePaht);
      deleteScoreLabelVector(binThresholds);
      exit(EXIT_FAILURE);
    }

    double thresholdScore = binThresholds->items[binThresholds->size - 1].score;

    fprintf(file, "%s\t%.10e\n", fimoFile->motifName, thresholdScore);

    if (fclose(file) != 0) // 检查 fclose 返回值
    {
      perror("Error closing binomial_thresholds.txt");
    }
  }

  // Free memory
  new_free(motifHitFilePath);
  new_free(binomialThresholdFilePaht);

  deleteScoreLabelVector(binThresholds);
}

Pair geometricBinTest(MotifHitVector *hitsVec, size_t promoterLength, size_t motifLength)
{
  // Null check for hitsVec
  if (!hitsVec)
  {
    fprintf(stderr, "Error: Null hitsVec provided to geometricBinTest.\n");
    exit(1); // Consider if you want to exit or handle the error differently
  }

  // Data integrity checks
  // if (promoterLength <= 0 || motifLength <= 0 || motifLength > promoterLength || !hitsVec->hits)
  if (promoterLength <= 0 || motifLength <= 0 || !hitsVec->hits)
  {
    fprintf(stderr, "Error: Invalid data provided to geometricBinTest.\n");
    exit(1); // Consider if you want to exit or handle the error differently
  }

  size_t possibleLocations = 2 * (promoterLength - motifLength + 1);

  double *pVals = (double *)new_malloc(hitsVec->size * sizeof(double));

  // Check memory allocation
  if (!pVals)
  {
    fprintf(stderr, "Error: Memory allocation failed in geometricBinTest.\n");
    exit(1);
  }

  size_t i;
  for (i = 0; i < hitsVec->size; i++)
  {
    pVals[i] = hitsVec->hits[i].pVal;
  }

  double lowestScore = DBL_MAX;
  size_t lowestIdx = hitsVec->size - 1;
  double product = 1.0;
  size_t noImproveCount = 0;

  size_t k;
  for (k = 0; k < hitsVec->size; k++)
  {
    product *= pVals[k];
    double geom = pow(product, 1.0 / (k + 1.0));
    geom = roundToSignificantDigits(geom, 10);
    double binomP = 1 - binomialCDF(k + 1, possibleLocations, geom);
    binomP = roundToSignificantDigits(binomP, 10);

    if (lowestScore > binomP)
    {
      lowestScore = binomP;
      lowestIdx = k;
      noImproveCount = 0;
    }
    else
    {
      noImproveCount++;
      // Early termination: stop if score hasn't improved for 10 consecutive iterations
      if (noImproveCount >= 10)
        break;
    }
  }

  new_free(pVals);

  Pair result;
  result.idx = lowestIdx;
  result.score = lowestScore;

  return result;
}

bool motifsOverlap(MotifHit *m1, MotifHit *m2)
{
  // Check if motifs are NULL
  if (!m1 || !m2)
  {
    return false; // Consider if you want to exit or return false in this scenario
  }

  // Check data integrity for both motifs
  if (m1->startPos > m1->stopPos || m2->startPos > m2->stopPos)
  {
    return false; // Consider if you want to exit or return false in this scenario
  }

  // Overlapping condition
  return !(m1->stopPos < m2->startPos || m1->startPos > m2->stopPos);
}

double binomialCDF(size_t numPVals, size_t numLocations, double gm)
{
  // // gm is geometric mean
  // if (gm <= 0.0 || gm >= 1.0 || numPVals < 0 || numPVals > numLocations)
  // {
  //   fprintf(stderr, "Error: Invalid parameters in binomialCDF.\n");
  //   return -1.0; // Error value
  // }

  // gm is geometric mean
  double cdf = 0.0;
  double b = 0.0;

  double logP = log(gm);
  double logOneMinusP = log(1 - gm);

  size_t k;
  for (k = 0; k < numPVals; k++)
  {
    if (k > 0)
      b += log((double)(numLocations - k + 1)) - log((double)k);
    cdf += exp(b + k * logP + (numLocations - k) * logOneMinusP);
    // Early saturation: CDF is a probability, cannot exceed 1.0
    if (cdf >= 1.0)
    {
      cdf = 1.0;
      break;
    }
  }
  return cdf;
}

void deleteFimoFileContents(FimoFile *file)
{
  if (!file)
    return; // Check if the provided pointer is not NULL

  // Free the hash table
  if (file->ht)
  {
    deleteHashTable(file->ht);
    file->ht = NULL;
  }

  // Free motifName if allocated
  if (file->motifName)
  {
    new_free(file->motifName);
    file->motifName = NULL;
  }

  // Free fileName if allocated
  if (file->fileName)
  {
    new_free(file->fileName);
    file->fileName = NULL;
  }

  // Free outDir if allocated
  if (file->outDir)
  {
    new_free(file->outDir);
    file->outDir = NULL;
  }
#ifdef DEBUG
  printf("    FimoFile (contents only) has been released!\n");
#endif
}

void deleteFimoFile(FimoFile *file)
{
  deleteFimoFileContents(file);

  // Finally, release FimoFile struct itself
  new_free(file);

#ifdef DEBUG
  printf("    FimoFile (including itself) has been released!\n");
#endif
}

// Create a fake Fimo file
void createMockFimoFile(const char *fileName)
{
  FILE *file = fopen(fileName, "w");
  if (!file)
  {
    fprintf(stderr, "Error: Unable to create mock Fimo file.\n");
    return;
  }

  // a simple mockup of the motif hits. Please modify it to fit your real format.
  //  fprintf(file, "HEADER LINE\n");
  fprintf(file, "motif_id	motif_alt_id	sequence_name	start	stop	strand	score	p-value	q-value	matched_sequence\n");
  fprintf(file, "MOTIF11 MOTIF1-ALT GENE1 1 3 + 0.5 0.011 AAAC 1\n");
  fprintf(file, "MOTIF11 MOTIF2-ALT GENE1 1 4 + 0.6 0.202 TTTT 0\n");
  fprintf(file, "MOTIF11 MOTIF2-ALT GENE2 1 4 + 0.6 0.302 TTTT 0\n");
  fprintf(file, "MOTIF11 MOTIF2-ALT GENE2 1 4 + 0.6 0.602 TTTT 0\n");
  fprintf(file, "MOTIF11 MOTIF2-ALT GENE2 1 4 + 0.6 0.102 TTTT 0\n");
  fprintf(file, "MOTIF11 MOTIF1-ALT GENE2 2 3 + 0.5 0.001 AAAT 1\n");
  fprintf(file, "MOTIF11 MOTIF2-ALT GENE2 2 4 + 0.6 0.888 TTTT 0\n");
  fclose(file);
}

// bool writeFimoFile(FimoFile *fimoFile, const char *outputPath) {
//     if (!fimoFile || !outputPath) {
//         fprintf(stderr, "Error: Invalid parameters for writeFimoFile.\n");
//         return false;
//     }

//     FILE *file = fopen(outputPath, "w");
//     if (!file) {
//         fprintf(stderr, "Error: Unable to open file %s for writing.\n", outputPath);
//         return false;
//     }

//     // Write header information
//     fprintf(file, "# FimoFile Output\n");
//     fprintf(file, "# Original file: %s\n", fimoFile->fileName ? fimoFile->fileName : "Unknown");
//     fprintf(file, "# Motif name: %s\n", fimoFile->motifName ? fimoFile->motifName : "Unknown");
//     fprintf(file, "# Motif length: %d\n", fimoFile->motifLength);
//     fprintf(file, "# Total lines: %d\n", fimoFile->numLines);
//     fprintf(file, "# Has motif alt: %s\n", fimoFile->hasMotifAlt ? "true" : "false");
//     fprintf(file, "# Bin score: %s\n", fimoFile->binScore ? "true" : "false");
//     fprintf(file, "#\n");

//     // Write column headers
//     if (fimoFile->binScore) {
//         fprintf(file, "motif_id\tmotif_alt_id\tsequence_name\tstart\tstop\tstrand\tscore\tp-value\tmatched_sequence\tbin_score\n");
//     } else {
//         fprintf(file, "motif_id\tmotif_alt_id\tsequence_name\tstart\tstop\tstrand\tscore\tp-value\tmatched_sequence\n");
//     }

//     // Write data from hash table
//     if (!fimoFile->ht) {
//         fclose(file);
//         return true; // Empty hash table is not an error
//     }

//     int totalRecords = 0;
//     for (size_t i = 0; i < TABLE_SIZE; i++) {
//         struct kv *current = fimoFile->ht->table[i];
//         while (current != NULL) {
//             MotifHitVector *vec = (MotifHitVector *)current->value;
//             if (vec && vec->hits) {
//                 for (size_t j = 0; j < vec->size; j++) {
//                     MotifHit *hit = &vec->hits[j];
//                     if (fimoFile->binScore) {
//                         fprintf(file, "%s\t%s\t%s\t%d\t%d\t%c\t%.6f\t%.6e\t%s\t%d\n",
//                                 hit->motif_id ? hit->motif_id : "",
//                                 hit->motif_alt_id ? hit->motif_alt_id : "",
//                                 hit->sequence_name ? hit->sequence_name : "",
//                                 hit->startPos,
//                                 hit->stopPos,
//                                 hit->strand,
//                                 hit->score,
//                                 hit->pVal,
//                                 hit->sequence ? hit->sequence : "",
//                                 hit->binScore);
//                     } else {
//                         fprintf(file, "%s\t%s\t%s\t%d\t%d\t%c\t%.6f\t%.6e\t%s\n",
//                                 hit->motif_id ? hit->motif_id : "",
//                                 hit->motif_alt_id ? hit->motif_alt_id : "",
//                                 hit->sequence_name ? hit->sequence_name : "",
//                                 hit->startPos,
//                                 hit->stopPos,
//                                 hit->strand,
//                                 hit->score,
//                                 hit->pVal,
//                                 hit->sequence ? hit->sequence : "");
//                     }
//                     totalRecords++;
//                 }
//             }
//             current = current->next;
//         }
//     }

//     fprintf(file, "# Total records written: %d\n", totalRecords);
//     fclose(file);

//     printf("FimoFile written to %s (%d records)\n", outputPath, totalRecords);
//     return true;
// }

// void printFimoFileSummary(FimoFile *fimoFile) {
//     if (!fimoFile) {
//         printf("FimoFile: NULL\n");
//         return;
//     }

//     printf("\n=== FimoFile Summary ===\n");
//     printf("File name:      %s\n", fimoFile->fileName ? fimoFile->fileName : "NULL");
//     printf("Motif name:     %s\n", fimoFile->motifName ? fimoFile->motifName : "NULL");
//     printf("Motif length:   %d\n", fimoFile->motifLength);
//     printf("Output dir:     %s\n", fimoFile->outDir ? fimoFile->outDir : "NULL");
//     printf("Total lines:    %d\n", fimoFile->numLines);
//     printf("Has motif alt:  %s\n", fimoFile->hasMotifAlt ? "true" : "false");
//     printf("Bin score:      %s\n", fimoFile->binScore ? "true" : "false");
//     printf("Hash table:     %s\n", fimoFile->ht ? "initialized" : "NULL");

//     if (fimoFile->ht) {
//         int geneCount = 0;
//         int totalHits = 0;

//         for (size_t i = 0; i < TABLE_SIZE; i++) {
//             struct kv *current = fimoFile->ht->table[i];
//             while (current != NULL) {
//                 geneCount++;
//                 MotifHitVector *vec = (MotifHitVector *)current->value;
//                 if (vec) {
//                     totalHits += vec->size;
//                 }
//                 current = current->next;
//             }
//         }

//         printf("Genes in HT:    %d\n", geneCount);
//         printf("Total hits:     %d\n", totalHits);
//     }
//     printf("========================\n\n");
// }