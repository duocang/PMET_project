#ifndef MOTIF_VECTOR_H
#define MOTIF_VECTOR_H

#include "pmet-index-MemCheck.h"
#include "pmet-index-MotifHit.h"
#include <stdio.h>

// Dynamic array of MotifHit. `shared_sequence_name` is borrowed when set —
// each hit's `sequence_name` then points at this single owned copy.
typedef struct {
  MotifHit* hits;
  int size;
  int capacity;
  char* shared_sequence_name;
} MotifHitVector;

/**
 * Returns the current size (number of elements) of the MotifHitVector.
 * @param vec Pointer to the MotifHitVector.
 * @return size_t The size of the vector.
 */
size_t motifHitVectorSize(const MotifHitVector* vec);

/**
 * Prints the contents of the MotifHitVector.
 * @param vec Pointer to the MotifHitVector to be printed.
 */
void printMotifHitVector(const MotifHitVector* vec);

void adapterPrintFunction(void* ptr);

/**
 * Creates a MotifHitVector*.
 * @return vec Pointer to the MotifHitVector to be initialized.
 */
MotifHitVector* createMotifHitVector();

/**
 * Initializes the given MotifHitVector.
 * @param vec Pointer to the MotifHitVector to be initialized.
 */
void initMotifHitVector(MotifHitVector* vec);

/**
 * Moves a MotifHit into the end of the MotifHitVector (transfer ownership).
 * After this call, the source hit's string pointers are set to NULL.
 * @param vec Pointer to the MotifHitVector.
 * @param hit The MotifHit to be moved (will be zeroed after move).
 */
void pushMotifHitVectorMove(MotifHitVector* vec, MotifHit* hit);

/**
 * Compares two MotifHits based on their p-values.
 * @param a Pointer to the first MotifHit.
 * @param b Pointer to the second MotifHit.
 * @return int Negative if 'a' is less than 'b', 0 if they're equal, positive if 'a' is greater than 'b'.
 */
int compareMotifHitsByPVal(const void* a, const void* b);

/**
 * Sorts the MotifHitVector based on the p-values of the contained MotifHits.
 * @param vec Pointer to the MotifHitVector to be sorted.
 */
void sortMotifHitVectorByPVal(MotifHitVector* vec);

/**
 * Retains only the top 'k' MotifHits in the MotifHitVector based on their order.
 * @param vec Pointer to the MotifHitVector.
 * @param k The number of MotifHits to retain.
 */
void retainTopKMotifHits(MotifHitVector* vec, size_t k);

/**
 * Removes the MotifHit at the specified index from the MotifHitVector.
 * @param vec Pointer to the MotifHitVector.
 * @param indx Index of the MotifHit to be removed.
 */
void removeHitAtIndex(MotifHitVector* vec, size_t indx);

/**
 * Clears all the MotifHits from the MotifHitVector without freeing the vector itself.
 * @param vec Pointer to the MotifHitVector to be cleared.
 */
void deleteMotifHitVectorContents(MotifHitVector* vec);

/**
 * Adapter function to bridge between a generic void pointer and the specific MotifHitVector deletion function.
 * Converts the void pointer back to a MotifHitVector pointer and then calls the appropriate delete function.
 * @param ptr Generic pointer to the object, which is expected to be of type MotifHitVector.
 */
void adapterDeleteFunction(void* ptr);

void deleteMotifHitVector(MotifHitVector* vec);

void setMotifHitVectorSharedSequenceName(MotifHitVector* vec, const char* sequence_name);

void writeVectorToStream(const MotifHitVector* vec, FILE* file);

void writeVectorToFile(const MotifHitVector* vec, const char* filename);

#endif /* MOTIF_VECTOR_H */
