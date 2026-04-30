#include "pmet-sequence-library.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "data-block-reader.h"
#include "seq-reader-from-fasta.h"

static size_t get_max_promoter_length(const PromoterList* promoter_len_list) {
  size_t max_length = 0;
  for (size_t i = 0; i < promoter_len_list->size; i++) {
    size_t current = (size_t)promoter_len_list->items[i].length;
    if (current > max_length) {
      max_length = current;
    }
  }
  return max_length;
}

static void ensure_sequence_library_capacity(PMET_SEQUENCE_LIBRARY* library) {
  if (library->count < library->capacity)
    return;

  size_t new_capacity = (library->capacity == 0 ? 256 : library->capacity * 2);
  PMET_SEQUENCE_RECORD* new_records = (PMET_SEQUENCE_RECORD*)mm_realloc(library->records,
                                                                        new_capacity * sizeof(PMET_SEQUENCE_RECORD));
  if (new_records == NULL) {
    fprintf(stderr, "Error: Failed to grow PMET sequence library.\n");
    exit(EXIT_FAILURE);
  }
  library->records = new_records;
  library->capacity = new_capacity;
}

PMET_SEQUENCE_LIBRARY* create_pmet_sequence_library(const FIMO_OPTIONS_T options, ALPH_T* alphabet,
                                                    PromoterList* promoter_len_list) {
  if (alphabet == NULL || promoter_len_list == NULL) {
    fprintf(stderr, "Error: Cannot build sequence library from NULL inputs.\n");
    exit(EXIT_FAILURE);
  }

  size_t max_promoter_length = get_max_promoter_length(promoter_len_list);
  if (max_promoter_length == 0) {
    fprintf(stderr, "Error: Promoter length list is empty.\n");
    exit(EXIT_FAILURE);
  }
  size_t read_buffer_size = max_promoter_length + 1;

  DATA_BLOCK_READER_T* fasta_reader = new_seq_reader_from_fasta(options.parse_genomic_coord, alphabet,
                                                                options.seq_filename);
  if (fasta_reader == NULL) {
    fprintf(stderr, "Error: Failed to open FASTA reader for sequence library.\n");
    exit(EXIT_FAILURE);
  }

  PMET_SEQUENCE_LIBRARY* library = (PMET_SEQUENCE_LIBRARY*)mm_malloc(sizeof(PMET_SEQUENCE_LIBRARY));
  library->records = NULL;
  library->count = 0;
  library->capacity = 0;

  while (true) {
    SEQ_T* seq = get_next_seq_from_readers(fasta_reader, NULL, true, read_buffer_size);
    if (seq == NULL)
      break;

    if (!is_complete(seq)) {
      fprintf(stderr, "Error: Sequence %s exceeds the expected maximum promoter length (%zu).\n", get_seq_name(seq),
              max_promoter_length);
      free_seq(seq);
      delete_pmet_sequence_library(library);
      free_data_block_reader(fasta_reader);
      exit(EXIT_FAILURE);
    }

    size_t promoter_length = findPromoterLength(promoter_len_list, get_seq_name(seq));
    if (promoter_length == (size_t)-1) {
      fprintf(stderr, "Error: Sequence ID: %s not found in promoter lengths file!\n", get_seq_name(seq));
      free_seq(seq);
      delete_pmet_sequence_library(library);
      free_data_block_reader(fasta_reader);
      exit(EXIT_FAILURE);
    }

    index_sequence(seq, alphabet, (options.skip_matched_sequence ? SEQ_NOAMBIG : (SEQ_KEEP | SEQ_NOAMBIG)));

    ensure_sequence_library_capacity(library);
    library->records[library->count].seq = seq;
    library->records[library->count].promoter_length = promoter_length;
    library->count++;
  }

  free_data_block_reader(fasta_reader);
  return library;
}

void delete_pmet_sequence_library(PMET_SEQUENCE_LIBRARY* library) {
  if (library == NULL)
    return;

  for (size_t i = 0; i < library->count; i++) {
    free_seq(library->records[i].seq);
    library->records[i].seq = NULL;
  }

  myfree(library->records);
  library->records = NULL;
  library->count = 0;
  library->capacity = 0;
  myfree(library);
}
