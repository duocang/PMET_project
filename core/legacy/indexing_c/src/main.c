#include <dirent.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#ifdef _OPENMP
#include <omp.h>
#endif

#include "FileRead.h"
#include "FimoFile.h"
#include "PromoterLength.h"
#include "utils.h"

#define MAX_PATH_LENGTH 1024
#define MAX_FILES 10000

void printHelp();
bool findFiles(const char* searchDir, const char* pattern, char** filesFound, int* numFiles);
void writeProgress(const char* fname, const char* message, float inc, float total);
bool endsWith(const char* str, const char* suffix);
int countPromoters(PromoterList* list);

int main(int argc, char* argv[]) {
  // Default inputs
  char fimoDir[MAX_PATH_LENGTH] = "./fimo/";
  char fimoHitsDir[MAX_PATH_LENGTH] = "fimohits/";
  char outDir[MAX_PATH_LENGTH] = ".";
  char promotersFile[MAX_PATH_LENGTH] = "promoter_lengths.txt";
  char progressFile[MAX_PATH_LENGTH] = "progress.txt";
  float totalProgress = 0.25;

  long NHits = 5000;
  long kHits = 5;

  const char* binThreshFile = "binomial_thresholds.txt";
  bool binScore = false;
  bool hasMotifAlt = true;

  // Parse command line arguments
  int i = 0;
  while (++i < argc) {
    if (!strcmp(argv[i], "-h")) {
      printHelp();
      return 0;
    } else if (!strcmp(argv[i], "-b")) {
      binScore = true;
    } else if (!strcmp(argv[i], "-k")) {
      kHits = atol(argv[++i]);
    } else if (!strcmp(argv[i], "-n")) {
      NHits = atol(argv[++i]);
    } else if (!strcmp(argv[i], "-f")) {
      strncpy(fimoDir, argv[++i], MAX_PATH_LENGTH - 1);
    } else if (!strcmp(argv[i], "-o")) {
      strncpy(outDir, argv[++i], MAX_PATH_LENGTH - 1);
    } else if (!strcmp(argv[i], "-a")) {
      hasMotifAlt = false;
    } else if (!strcmp(argv[i], "-p")) {
      strncpy(promotersFile, argv[++i], MAX_PATH_LENGTH - 1);
    } else if (!strcmp(argv[i], "-g")) {
      strncpy(progressFile, argv[++i], MAX_PATH_LENGTH - 1);
    } else {
      fprintf(stderr, "Error: unknown command line switch %s\n", argv[i]);
      return 1;
    }
  }

  // Ensure directories end with '/'
  if (outDir[strlen(outDir) - 1] != '/') {
    strcat(outDir, "/");
  }
  if (fimoDir[strlen(fimoDir) - 1] != '/') {
    strcat(fimoDir, "/");
  }

  // Display inputs
  printf("          Input parameters          \n");
  printf("------------------------------------\n");
  printf("fimo files\t\t%s*.txt\n", fimoDir);
  printf("promoters file\t\t%s\n", promotersFile);
  printf("k\t\t\t%ld\n", kHits);
  printf("n\t\t\t%ld\n", NHits);
  printf("output directory\t%s\n", outDir);

  // Read promoters file
  writeProgress(progressFile, "Reading inputs...", 0.0, totalProgress);
  printf("Reading inputs...\n");

  // Create and initialize PromoterList
  PromoterList* promSizes = (PromoterList*)malloc(sizeof(PromoterList));
  if (!promSizes) {
    fprintf(stderr, "Error allocating PromoterList\n");
    return 1;
  }
  initPromoterList(promSizes);

  // Read promoter lengths file
  readPromoterLengthFile(promSizes, promotersFile);

  // Count promoters in the list
  int numPromoters = countPromoters(promSizes);

  if (numPromoters == 0) {
    fprintf(stderr, "Error: No promoters read from file\n");
    deletePromoterLenList(promSizes);
    free(promSizes);
    return 1;
  }

  printf("Universe size is %d\n", numPromoters);

  // Find fimo files
  printf("Searching for fimo files...");
  char** fimoFiles = (char**)malloc(MAX_FILES * sizeof(char*));
  for (int j = 0; j < MAX_FILES; j++) {
    fimoFiles[j] = (char*)malloc(MAX_PATH_LENGTH * sizeof(char));
  }

  int numFimoFiles = 0;
  if (!findFiles(fimoDir, ".txt", fimoFiles, &numFimoFiles)) {
    fprintf(stderr, "Error finding files\n");
    deletePromoterLenList(promSizes);
    free(promSizes);
    for (int j = 0; j < MAX_FILES; j++) {
      free(fimoFiles[j]);
    }
    free(fimoFiles);
    return 1;
  }

  printf("Found %d\n", numFimoFiles);

  if (numFimoFiles == 0) {
    deletePromoterLenList(promSizes);
    free(promSizes);
    for (int j = 0; j < MAX_FILES; j++) {
      free(fimoFiles[j]);
    }
    free(fimoFiles);
    return 1;
  }

  // Create output directory for fimo hits
  char fullOutDir[MAX_PATH_LENGTH * 2];
  snprintf(fullOutDir, sizeof(fullOutDir), "%s", outDir);
  mkdir(fullOutDir, 0755);

  float inc = totalProgress / numFimoFiles;

  // Process each fimo file
  #pragma omp parallel for schedule(dynamic) shared(promSizes, fimoFiles, fimoDir, fullOutDir, hasMotifAlt, binScore, kHits, NHits, progressFile, inc, totalProgress)
  for (int f = 0; f < numFimoFiles; f++) {
    char message[MAX_PATH_LENGTH * 2];
    snprintf(message, sizeof(message), "%d of %d, processing FIMO result file: %s", f + 1, numFimoFiles, fimoFiles[f]);
    #pragma omp critical(io)
    {
      printf("%s\n", message);
      writeProgress(progressFile, message, inc, totalProgress);
    }

    // Construct full file path
    char fullFilePath[MAX_PATH_LENGTH * 2];
    snprintf(fullFilePath, sizeof(fullFilePath), "%s%s", fimoDir, fimoFiles[f]);

    // Create FimoFile
    FimoFile* fimo = createFimoFile();

    // 从文件名提取motif名称（去掉.txt扩展名）
    char motifName[MAX_PATH_LENGTH];
    strncpy(motifName, fimoFiles[f], MAX_PATH_LENGTH - 1);
    motifName[MAX_PATH_LENGTH - 1] = '\0'; // 确保字符串结束

    // 找到并移除.txt扩展名
    char* dotPos = strrchr(motifName, '.');
    if (dotPos && strcmp(dotPos, ".txt") == 0) {
        *dotPos = '\0'; // 在点号处截断字符串
    }

    printf("Extracted motif name: %s\n", motifName);

    // Initialize with file info - 使用提取的motif名称
    initFimoFile(fimo, 0, motifName, 0, fullFilePath, fullOutDir, hasMotifAlt, binScore);

    // Read and process the file
    if (readFimoFile(fimo)) {
      processFimoFile(fimo, kHits, NHits, promSizes);
    }

    // 创建输出文件路径并打印
    char outputFilePath[MAX_PATH_LENGTH * 2];
    snprintf(outputFilePath, sizeof(outputFilePath), "%s/fimohits/%s.txt", removeTrailingSlashAndReturn(outDir), motifName);
    printf("Output file path: %s\n", outputFilePath);

    printf(fimo->motifName ? "Finished processing %s\n\n" : "Finished processing unknown motif\n", fimo->motifName);

    deleteFimoFile(fimo);
  }

  // Cleanup - 修复双重释放问题
  deletePromoterLenList(promSizes);
  // free(promSizes);  // 删除这一行！deletePromoterLenList 已经释放了内存

  for (int j = 0; j < MAX_FILES; j++) {
    free(fimoFiles[j]);
  }
  free(fimoFiles);

  printf("\nDone\n");
  return 0;
}

void printHelp() {
  printf("Required input arguments\n\n");
  printf("-b\tUse fimo files with the 10 column format. Use the 9 column format without this argument\n");
  printf("-o\tOutput directory. Default is the current working directory\n");
  printf("-p\tPromoter lengths file. Default is 'promoter_lengths.txt'\n");
  printf("-f\tThe name of a directory containing fimo output files. Default is the current working directory.\n");
  printf("-k\tMaximum motif hits allowed within each promoter. Default value is 5.\n");
  printf("-n\tHow many top promoter hits to take per motif. Default is 5000\n");
  printf("-h\tDisplay this message and exit.\n");
}

bool findFiles(const char* searchDir, const char* pattern, char** filesFound, int* numFiles) {
  DIR* pDir = opendir(searchDir);

  if (!pDir) {
    fprintf(stderr, "Error: Cannot find directory %s\n", searchDir);
    return false;
  }

  struct dirent* entry;
  *numFiles = 0;

  while ((entry = readdir(pDir)) != NULL) {
    if (entry->d_type == DT_REG && endsWith(entry->d_name, pattern)) {
      if (*numFiles < MAX_FILES) {
        strncpy(filesFound[*numFiles], entry->d_name, MAX_PATH_LENGTH - 1);
        (*numFiles)++;
      }
    }
  }

  closedir(pDir);
  return true;
}

void writeProgress(const char* fname, const char* message, float inc, float total) {
  float progress = 0.0;

  // Read current progress
  FILE* infile = fopen(fname, "r");
  if (infile) {
    fscanf(infile, "%f", &progress);
    fclose(infile);
  }

  progress += inc;

  // Write updated progress
  FILE* outfile = fopen(fname, "w");
  if (outfile) {
    fprintf(outfile, "%.4f\t%s\n", progress, message);
    fclose(outfile);
  }
}

bool endsWith(const char* str, const char* suffix) {
  if (!str || !suffix)
    return false;

  size_t lenstr = strlen(str);
  size_t lensuffix = strlen(suffix);

  if (lensuffix > lenstr)
    return false;

  return strncmp(str + lenstr - lensuffix, suffix, lensuffix) == 0;
}

/**
 * Count the number of promoters in the list.
 *
 * @param list Pointer to the PromoterList.
 * @return Number of promoters in the list.
 */
int countPromoters(PromoterList* list) {
  if (!list) {
    return 0;
  }
  return (int)list->count;
}