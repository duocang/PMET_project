#ifndef FIMO_H
#define FIMO_H

#include "alphabet.h"
#include "array-list.h"
#include "projrel.h"
#include "string-list.h"
#include "utils.h"

// Structure for tracking fimo command line parameters.
typedef struct options {
  bool parse_genomic_coord;
  bool scan_both_strands;
  bool skip_matched_sequence;
  bool text_output;  // when true, write fimohits as text .txt; default = binary .bin

  char *bg_filename;
  char *meme_filename;
  char *output_dirname;
  char *seq_filename;
  char *promoter_length;

  int topk;
  int topn;

  double pseudocount;
  double output_threshold;

  ALPH_T *alphabet;
  STRING_LIST_T *selected_motifs;

  const char *usage;

} FIMO_OPTIONS_T;
#endif
