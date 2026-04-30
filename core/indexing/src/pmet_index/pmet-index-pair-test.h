/*
 * pmet-index-pair-test
 *
 * The three statistical helpers that the live indexing path (fimo.c) still
 * needs from the legacy "FimoFile" module:
 *
 *   - motifsOverlap     : positional overlap between two MotifHits
 *   - geometricBinTest  : geometric-mean binomial significance over a
 *                         MotifHitVector — returns the (idx, score) of the
 *                         best prefix
 *   - binomialCDF       : helper used by geometricBinTest
 *
 * Plus the small Pair struct that geometricBinTest returns.
 *
 * Everything else from the old pmet-index-FimoFile / HashTable / Node /
 * SiteStore modules was the dead text-fimo-file processing path and has
 * been deleted.
 */

#ifndef PMET_INDEX_PAIR_TEST_H
#define PMET_INDEX_PAIR_TEST_H

#include <stdbool.h>
#include <stddef.h>

#include "pmet-index-MotifHit.h"
#include "pmet-index-MotifHitVector.h"

typedef struct {
  long idx;
  double score;
} Pair;

bool motifsOverlap(MotifHit* m1, MotifHit* m2);
Pair geometricBinTest(MotifHitVector* hitsVec, size_t promoterLength, size_t motifLength);
double binomialCDF(size_t numPVals, size_t numLocations, double gm);

#endif /* PMET_INDEX_PAIR_TEST_H */
