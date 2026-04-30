#include "pmet-index-MotifHitVector.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Returns the current size of the MotifVector.
size_t motifHitVectorSize(const MotifHitVector* vec) {
  return vec->size;
}

// Prints all hits in the MotifVector to the console.
void printMotifHitVector(const MotifHitVector* vec) {
  size_t i;
  for (i = 0; i < vec->size; ++i) {
    printMotifHit(&(vec->hits[i]));
  }
}

void adapterPrintFunction(void* ptr) {
  printMotifHitVector((MotifHitVector*)ptr);
}

MotifHitVector* createMotifHitVector() {
  MotifHitVector* newVec = (MotifHitVector*)new_malloc(sizeof(MotifHitVector));
  if (newVec == NULL) {
#ifdef DEBUG
    fprintf(stderr, "Failed to allocate memory for MotifHitVector.\n");
#endif

    return NULL;
  }

  newVec->size = 0;
  newVec->capacity = 128;
  newVec->shared_sequence_name = NULL;
  newVec->hits = (MotifHit*)new_malloc(newVec->capacity * sizeof(MotifHit));
  if (newVec->hits == NULL) {
#ifdef DEBUG
    fprintf(stderr, "Failed to allocate memory for hits array.\n");
#endif

    new_free(newVec);
    return NULL;
  }

  return newVec;
}

void initMotifHitVector(MotifHitVector* vec) {
  if (!vec)
    return;

  vec->capacity = 128;
  vec->shared_sequence_name = NULL;
  vec->hits = (MotifHit*)new_malloc(vec->capacity * sizeof(MotifHit));
  if (!vec->hits) {
    fprintf(stderr, "Failed to allocate memory for MotifVector.\n");
    exit(EXIT_FAILURE);
  }
  vec->size = 0;
}

void pushMotifHitVectorMove(MotifHitVector* vec, MotifHit* hit) {
  if (!vec || !hit)
    return;

  if (vec->size == vec->capacity) {
    size_t new_capacity = (size_t)vec->capacity * 2;
    MotifHit* new_hits = (MotifHit*)new_realloc(vec->hits, new_capacity * sizeof(MotifHit));

    if (!new_hits) {
      fprintf(stderr, "Failed to reallocate memory for MotifVector.\n");
      exit(EXIT_FAILURE);
    }
    vec->hits = new_hits;
    vec->capacity = (int)new_capacity;
  }

  vec->hits[vec->size] = *hit;
  hit->motif_id = NULL;
  hit->motif_alt_id = NULL;
  hit->sequence_name = NULL;
  hit->sequence = NULL;
  hit->ownership_mask = 0;

  vec->size++;
}

int compareMotifHitsByPVal(const void* a, const void* b) {
  const MotifHit* ha = (const MotifHit*)a;
  const MotifHit* hb = (const MotifHit*)b;

  if (ha->pVal < hb->pVal)
    return -1;
  if (ha->pVal > hb->pVal)
    return 1;
  // Tie-breaker: sort by sequence_name then startPos for cross-platform stability
  int cmp = strcmp(ha->sequence_name, hb->sequence_name);
  if (cmp != 0)
    return cmp;
  if (ha->startPos < hb->startPos)
    return -1;
  if (ha->startPos > hb->startPos)
    return 1;
  return 0;
}

void sortMotifHitVectorByPVal(MotifHitVector* vec) {
  qsort(vec->hits, vec->size, sizeof(MotifHit), compareMotifHitsByPVal);
}

void retainTopKMotifHits(MotifHitVector* vec, size_t k) {
  if (!vec || k >= vec->size) {
    // If k is greater than the current size or the vector is not initialized, simply return.
    return;
  }

  // Resize the vector to only keep top k elements.
  size_t i;
  size_t new_size = k;
  for (i = new_size; i < vec->size; ++i) {
    // MotifHit has dynamic memory allocations like strings, free them here.
    deleteMotifHitContents(&vec->hits[i]);
  }
  // Shrink the hits array down to the new size.
  vec->hits = new_realloc(vec->hits, new_size * sizeof(MotifHit));
  vec->size = new_size;
}

void removeHitAtIndex(MotifHitVector* vec, size_t indx) {
  if (!vec || indx >= vec->size) {
    return; // Invalid vector or index
  }

  // Free memory of removed hits
  deleteMotifHitContents(&vec->hits[indx]);

  // Move elements to the left
  size_t i;
  for (i = indx; i < vec->size - 1; ++i) {
    vec->hits[i] = vec->hits[i + 1];
  }

  vec->size--; // Decrement the size
}

void deleteMotifHitVectorContents(MotifHitVector* vec) {
  size_t i;
  for (i = 0; i < vec->size; i++) {
    deleteMotifHitContents(&(vec->hits[i]));
  }
  new_free(vec->shared_sequence_name);
  vec->shared_sequence_name = NULL;
  new_free(vec->hits);
  vec->hits = NULL;
  vec->size = 0;
  vec->capacity = 0;
}

void deleteMotifHitVector(MotifHitVector* vec) {
  deleteMotifHitVectorContents(vec);
  new_free(vec);
}

void adapterDeleteFunction(void* ptr) {
  deleteMotifHitVector((MotifHitVector*)ptr);
}

void setMotifHitVectorSharedSequenceName(MotifHitVector* vec, const char* sequence_name) {
  if (!vec || !sequence_name)
    return;

  if (vec->shared_sequence_name) {
    new_free(vec->shared_sequence_name);
  }

  vec->shared_sequence_name = new_strdup(sequence_name);
  if (!vec->shared_sequence_name) {
    fprintf(stderr, "Failed to allocate shared sequence name for MotifVector.\n");
    exit(EXIT_FAILURE);
  }

  size_t i;
  for (i = 0; i < vec->size; i++) {
    setMotifHitSequenceNameShared(&vec->hits[i], vec->shared_sequence_name);
  }
}

void writeVectorToStream(const MotifHitVector* vec, FILE* file) {
  if (vec == NULL || vec->hits == NULL || file == NULL) {
    fprintf(stderr, "Invalid parameters provided to writeVectorToStream.\n");
    return;
  }

  size_t i;
  for (i = 0; i < vec->size; i++) {
    MotifHit hit = vec->hits[i];
    fprintf(file, "%s\t%s\t%ld\t%ld\t%c\t%.10e\t%.10e", hit.motif_id, hit.sequence_name, hit.startPos, hit.stopPos,
            hit.strand, hit.score, hit.pVal);
    if (hit.sequence != NULL) {
      fprintf(file, "\t%s", hit.sequence);
    }
    fputc('\n', file);
  }
}

void writeVectorToFile(const MotifHitVector* vec, const char* filename) {
  if (vec == NULL || vec->hits == NULL || filename == NULL) {
    fprintf(stderr, "Invalid parameters provided to writeVectorToFile.\n");
    return;
  }

  FILE* file = fopen(filename, "a");
  if (file == NULL) {
    fprintf(stderr, "Failed to open the file for writing: %s (%s)\n", filename, strerror(errno));
    return;
  }

  writeVectorToStream(vec, file);

  if (fclose(file) != 0) {
    fprintf(stderr, "Error closing the file %s.\n", filename);
  }
}
