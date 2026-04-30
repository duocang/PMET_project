#include "pmet-index-pair-test.h"

#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "pmet-index-MemCheck.h"

/* Round x to `d` significant digits. Used to absorb the last-bit differences
 * between libm implementations (Linux glibc vs. macOS libm) so the test gives
 * the same chosen prefix on both platforms — see the cross-platform-precision
 * thread in TODO.md. Originally lived in pmet-index-FimoFile.c; moved here
 * with its only remaining caller. */
static double roundToSignificantDigits(double x, int d) {
  if (x > 0.0) {
    double z = pow(10.0, ceil(d - 1 - log10(x)));
    return rint(z * x) / z;
  } else if (x < 0.0) {
    double z = pow(10.0, ceil(d - 1 - log10(-x)));
    return -rint(z * (-x)) / z;
  }
  return 0.0;
}

bool motifsOverlap(MotifHit* m1, MotifHit* m2) {
  if (!m1 || !m2)
    return false;
  /* Defensive: a malformed hit with start > stop can't overlap anything. */
  if (m1->startPos > m1->stopPos || m2->startPos > m2->stopPos)
    return false;
  return !(m1->stopPos < m2->startPos || m1->startPos > m2->stopPos);
}

double binomialCDF(size_t numPVals, size_t numLocations, double gm) {
  /* Standard log-domain accumulation of the binomial PMF up through k=numPVals.
   * gm is the geometric mean of the kept p-values, used as the success
   * probability per trial. */
  double cdf = 0.0;
  double b = 0.0;

  double logP = log(gm);
  double logOneMinusP = log(1 - gm);

  for (size_t k = 0; k < numPVals; k++) {
    if (k > 0) {
      b += log((double)(numLocations - k + 1)) - log((double)k);
    }
    cdf += exp(b + (double)k * logP + (double)(numLocations - k) * logOneMinusP);
  }
  return cdf;
}

Pair geometricBinTest(MotifHitVector* hitsVec, size_t promoterLength, size_t motifLength) {
  if (!hitsVec) {
    fprintf(stderr, "Error: Null hitsVec provided to geometricBinTest.\n");
    exit(EXIT_FAILURE);
  }
  if (promoterLength == 0 || motifLength == 0 || !hitsVec->hits) {
    fprintf(stderr, "Error: Invalid data provided to geometricBinTest.\n");
    exit(EXIT_FAILURE);
  }

  /* Both strands of every k-mer position are candidates. */
  const size_t possibleLocations = 2 * (promoterLength - motifLength + 1);

  double* pVals = (double*)new_malloc(hitsVec->size * sizeof(double));
  if (!pVals) {
    fprintf(stderr, "Error: Memory allocation failed in geometricBinTest.\n");
    exit(EXIT_FAILURE);
  }
  for (size_t i = 0; i < (size_t)hitsVec->size; i++) {
    pVals[i] = hitsVec->hits[i].pVal;
  }

  /* Walk prefixes 1..N. For each k, treat the geometric mean of pVals[0..k]
   * as the per-trial success probability and ask: how surprising is it to
   * see at least k+1 hits this strong? Track the best (lowest p) prefix. */
  double lowestScore = DBL_MAX;
  size_t lowestIdx = (size_t)hitsVec->size - 1;
  double product = 1.0;

  for (size_t k = 0; k < (size_t)hitsVec->size; k++) {
    product *= pVals[k];
    double geom = pow(product, 1.0 / (double)(k + 1));
    /* Round to 10 significant digits so cross-platform libm differences in
     * the LSBs of pow/exp don't bleed into the chosen prefix index. */
    geom = roundToSignificantDigits(geom, 10);
    double binomP = 1 - binomialCDF(k + 1, possibleLocations, geom);
    binomP = roundToSignificantDigits(binomP, 10);

    if (binomP < lowestScore) {
      lowestScore = binomP;
      lowestIdx = k;
    }
  }

  new_free(pVals);
  return (Pair){.idx = (long)lowestIdx, .score = lowestScore};
}
