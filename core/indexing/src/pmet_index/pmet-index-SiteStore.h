#ifndef PMET_INDEX_SITE_STORE_H
#define PMET_INDEX_SITE_STORE_H

#include <stdbool.h>
#include <stdio.h>

#include "cisml.h"
#include "pmet-index-MotifHitVector.h"

void insert_site_into_store(FILE* tsv_out, bool print_qvalue, MATCHED_ELEMENT_T* match, SCANNED_SEQUENCE_T* scanned_seq,
                            MotifHitVector* vec);

#endif /* PMET_INDEX_SITE_STORE_H */
