#ifndef PMET_SEQUENCE_LIBRARY_H
#define PMET_SEQUENCE_LIBRARY_H

#include <stddef.h>

#include "alphabet.h"
#include "fimo.h"
#include "pmet-index-PromoterLength.h"
#include "seq.h"

typedef struct {
  SEQ_T* seq;
  size_t promoter_length;
} PMET_SEQUENCE_RECORD;

typedef struct {
  PMET_SEQUENCE_RECORD* records;
  size_t count;
  size_t capacity;
} PMET_SEQUENCE_LIBRARY;

PMET_SEQUENCE_LIBRARY* create_pmet_sequence_library(const FIMO_OPTIONS_T options, ALPH_T* alphabet,
                                                    PromoterList* promoter_len_list);

void delete_pmet_sequence_library(PMET_SEQUENCE_LIBRARY* library);

#endif
