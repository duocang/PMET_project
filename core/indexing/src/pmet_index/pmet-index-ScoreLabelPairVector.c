#include "pmet-index-ScoreLabelPairVector.h"

ScoreLabelPairVector* createScoreLabelPairVector() {
  ScoreLabelPairVector* vec = (ScoreLabelPairVector*)new_malloc(sizeof(ScoreLabelPairVector));
  if (!vec) {
    perror("Failed to allocate memory for ScoreLabelPairVector");
    exit(EXIT_FAILURE);
  }
  vec->items = NULL;
  vec->size = 0;
  vec->capacity = 0;
  return vec;
}

int comparePairs(const void* a, const void* b) {
  const ScoreLabelPair* pa = (const ScoreLabelPair*)a;
  const ScoreLabelPair* pb = (const ScoreLabelPair*)b;
  if (pa->score < pb->score)
    return -1;
  if (pa->score > pb->score)
    return 1;
  // Tie-breaker: sort by label lexicographically for cross-platform stability
  return strcmp(pa->label, pb->label);
}

void sortVector(ScoreLabelPairVector* vec) {
  if (!vec || !vec->items) {
    fprintf(stderr, "Warning: Attempted to sort a NULL or uninitialized ScoreLabelPairVector. Operation skipped.\n");
    return;
  }

  qsort(vec->items, vec->size, sizeof(ScoreLabelPair), comparePairs);
}

bool pushBack(ScoreLabelPairVector* vec, double score, char* label) {
  if (!vec || !label) {
    fprintf(stderr, "Warning: Received NULL vector or label in pushBack. Operation skipped.\n");
    return false;
  }

  if (vec->size >= vec->capacity) {
    size_t newCapacity = vec->capacity == 0 ? 4 : vec->capacity * 2;
    ScoreLabelPair* newItems = (ScoreLabelPair*)new_realloc(vec->items, newCapacity * sizeof(ScoreLabelPair));
    if (!newItems) {
      fprintf(stderr, "Memory allocation failed in pushBack.\n");
      return false;
    }
    vec->items = newItems;
    vec->capacity = newCapacity;
  }

  vec->items[vec->size].score = score;
  // Always strdup the label — caller may pass a stack-local string whose
  // lifetime ends before this vector's; without a copy we'd dangle.
  vec->items[vec->size].label = new_strdup(label);
  if (!vec->items[vec->size].label) {
    fprintf(stderr, "Memory allocation for label failed in pushBack.\n");
    return false;
  }

  vec->size++;
  return true;
}

void retainTopN(ScoreLabelPairVector* vec, size_t N) {
  if (!vec) {
    fprintf(stderr, "Error: Received NULL vector in retainTopN.\n");
    return;
  }

  // If N is greater than or equal to the current size, do nothing
  if (N >= vec->size) {
    return;
  }

  // Free memory for labels that are beyond the Nth element
  size_t i;
  for (i = N; i < vec->size; ++i) {
    new_free(vec->items[i].label);
  }

  // Update the size of the vector to N
  vec->size = N;

  // Resize the items array. Assign the realloc result to a fresh pointer
  // first so that on failure (NULL return) we still hold the original
  // vec->items and can free it later.
  ScoreLabelPair* newItems = new_realloc(vec->items, N * sizeof(ScoreLabelPair));
  if (newItems == NULL) {
    fprintf(stderr, "Error: Memory reallocation failed in retainTopN.\n");
    return; // Just return. It's up to the calling function to check the state of the vector and decide how to proceed.
  }
  vec->items = newItems;
  vec->capacity = N; // Update the capacity to N
}

int labelExists(const ScoreLabelPairVector* vec, const char* searchLabel) {
  if (!vec || !searchLabel) {
    fprintf(stderr, "Warning: NULL argument passed to labelExists().\n");
    return NOT_FOUND;
  }

  size_t i;
  for (i = 0; i < vec->size; i++) {
    if (strcmp(vec->items[i].label, searchLabel) == 0) {
      return FOUND; // Label found
    }
  }
  return NOT_FOUND; // Label not found
}

double findScoreByLabel(ScoreLabelPairVector* vec, const char* searchLabel) {
  if (!vec || !searchLabel) {
    fprintf(stderr, "Warning: NULL argument passed to findScoreByLabel().\n");
    return LABEL_NOT_FOUND;
  }

  size_t i;
  for (i = 0; i < vec->size; i++) {
    if (strcmp(vec->items[i].label, searchLabel) == 0) {
      return vec->items[i].score;
    }
  }
  return LABEL_NOT_FOUND; // Label not found
}

void printVector(ScoreLabelPairVector* vec) {
  if (!vec) {
    fprintf(stderr, "Warning: NULL vector passed to printVector().\n");
    return;
  }

  printf("Printing vector contents:\n");
  printf("==========================\n");
  size_t i;
  for (i = 0; i < vec->size; i++) {
    printf("Item %zu - Score: %.15e, Label: %s\n", i, vec->items[i].score, vec->items[i].label);
  }
  printf("==========================\n");
}

void deleteScoreLabelVectorContents(ScoreLabelPairVector* vec) {
  if (!vec) {
    return;
  }

  // Free each label
  size_t i;
  for (i = 0; i < vec->size; i++) {
    new_free(vec->items[i].label);
    vec->items[i].label = NULL;
  }

  // Free the items array
  new_free(vec->items);
  vec->items = NULL;
}

void deleteScoreLabelVector(ScoreLabelPairVector* vec) {
  if (!vec) {
    return;
  }

  deleteScoreLabelVectorContents(vec);

  // Free the vector itself
  new_free(vec);
}

void writeScoreLabelPairVectorToTxt(ScoreLabelPairVector* vector, const char* filename) {
  if (!vector || !filename) {
    fprintf(stderr, "Warning: NULL vector passed to printVector().\n");
    return;
  }

  FILE* file = fopen(filename, "a");
  if (!file) {
    perror("Unable to open file for writing");
    return;
  }

  // // Assuming the first line to be headers
  // fprintf(file, "Score\tLabel\n");

  size_t i;
  for (i = 0; i < vector->size; i++) {
    fprintf(file, "%s\t%.15e\n", vector->items[i].label, vector->items[i].score);
  }

  if (fclose(file) != 0) {
    perror("Error closing the file");
  }
}
