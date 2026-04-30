#include "pmet-index-MotifHit.h"

static void initMotifHitWithOwnership(MotifHit* hit, const char* motif_id, const char* motif_alt_id,
                                      const char* sequence_name, long startPos, long stopPos, char strand, double score,
                                      double pVal, const char* sequence, double binScore,
                                      unsigned char ownership_mask) {
  unsigned char effective_ownership_mask = ownership_mask;
  if (motif_id == NULL)
    effective_ownership_mask &= (unsigned char)~MOTIF_HIT_OWNS_MOTIF_ID;
  if (motif_alt_id == NULL)
    effective_ownership_mask &= (unsigned char)~MOTIF_HIT_OWNS_MOTIF_ALT_ID;
  if (sequence_name == NULL)
    effective_ownership_mask &= (unsigned char)~MOTIF_HIT_OWNS_SEQUENCE_NAME;
  if (sequence == NULL)
    effective_ownership_mask &= (unsigned char)~MOTIF_HIT_OWNS_SEQUENCE;

  hit->motif_id = ((effective_ownership_mask & MOTIF_HIT_OWNS_MOTIF_ID) ? new_strdup(motif_id) : (char*)motif_id);
  hit->motif_alt_id = ((effective_ownership_mask & MOTIF_HIT_OWNS_MOTIF_ALT_ID) ? new_strdup(motif_alt_id)
                                                                                : (char*)motif_alt_id);
  hit->sequence_name = ((effective_ownership_mask & MOTIF_HIT_OWNS_SEQUENCE_NAME) ? new_strdup(sequence_name)
                                                                                  : (char*)sequence_name);

  hit->startPos = startPos;
  hit->stopPos = stopPos;
  hit->strand = strand;
  hit->score = score;
  hit->pVal = pVal;

  hit->sequence = ((effective_ownership_mask & MOTIF_HIT_OWNS_SEQUENCE) ? new_strdup(sequence) : (char*)sequence);
  hit->binScore = binScore;
  hit->ownership_mask = effective_ownership_mask;
}

void initMotifHitBorrowMeta(MotifHit* hit, const char* motif_id, const char* motif_alt_id, const char* sequence_name,
                            long startPos, long stopPos, char strand, double score, double pVal, const char* sequence,
                            double binScore) {
  initMotifHitWithOwnership(hit, motif_id, motif_alt_id, sequence_name, startPos, stopPos, strand, score, pVal,
                            sequence, binScore, MOTIF_HIT_OWNS_SEQUENCE);
}

void setMotifHitSequenceNameShared(MotifHit* hit, char* sequence_name) {
  if (!hit)
    return;

  if (hit->ownership_mask & MOTIF_HIT_OWNS_SEQUENCE_NAME) {
    new_free(hit->sequence_name);
  }

  hit->sequence_name = sequence_name;
  hit->ownership_mask &= (unsigned char)~MOTIF_HIT_OWNS_SEQUENCE_NAME;
}

// Free the memory used by a MotifHit.
void deleteMotifHitContents(MotifHit* hit) {
  if (hit->ownership_mask & MOTIF_HIT_OWNS_MOTIF_ID)
    new_free(hit->motif_id);
  if (hit->ownership_mask & MOTIF_HIT_OWNS_MOTIF_ALT_ID)
    new_free(hit->motif_alt_id);
  if (hit->ownership_mask & MOTIF_HIT_OWNS_SEQUENCE_NAME)
    new_free(hit->sequence_name);
  if (hit->ownership_mask & MOTIF_HIT_OWNS_SEQUENCE)
    new_free(hit->sequence);
  // reset the pointers to NULL after freeing
  hit->motif_id = NULL;
  hit->motif_alt_id = NULL;
  hit->sequence_name = NULL;
  hit->sequence = NULL;
  hit->ownership_mask = 0;
}

void deleteMotifHit(MotifHit* hit) {
  deleteMotifHitContents(hit);

  new_free(hit);
}

// Compare two MotifHit structures based on their pVal.
// Return true if a's pVal is less than b's pVal, otherwise false.
int sortHits(const MotifHit* a, const MotifHit* b) {
  // Sort in ascending order based on pVal.
  return (a->pVal < b->pVal);
}

// Print the details of a MotifHit to an output stream.
void printMotifHit(const MotifHit* hit) {
  // The FIMO file format is:
  // motif gene    start   stop    strand  score   pVal  qVal  sequence
  // In the PMET analysis program, score is pVal, and p-val is adjusted p-val, qVal is empty.

  printf("%s\t%s\t%s\t%ld\t%ld\t%c\t%.10e\t%.10e", hit->motif_id, hit->motif_alt_id, hit->sequence_name, hit->startPos,
         hit->stopPos, hit->strand, hit->score, hit->pVal);

  if (hit->sequence != NULL) {
    printf("\t%s", hit->sequence);
  }

  // If binScore is valid (i.e., non-negative), print it as well.
  if (hit->binScore >= 0) {
    printf("\t%.10e", hit->binScore);
  }

  printf("\n"); // Append a newline for readability.
}
