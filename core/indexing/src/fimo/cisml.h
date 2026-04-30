#ifndef CISML_H
#define CISML_H

#include "utils.h"

typedef struct pattern PATTERN_T;
typedef struct scanned_sequence SCANNED_SEQUENCE_T;
typedef struct matched_element MATCHED_ELEMENT_T;

PATTERN_T *allocate_pattern(char *accession, char *name);
void free_pattern(PATTERN_T *pattern);
char *get_pattern_name(PATTERN_T *pattern);
char *get_pattern_accession(PATTERN_T *pattern);

SCANNED_SEQUENCE_T *allocate_scanned_sequence(
  char *accession,
  char *name,
  PATTERN_T *parent
);
void free_scanned_sequence(SCANNED_SEQUENCE_T *scanned_sequence);
PATTERN_T *get_scanned_sequence_parent(SCANNED_SEQUENCE_T *scanned_sequence);
char *get_scanned_sequence_name(SCANNED_SEQUENCE_T *scanned_sequence);
void add_scanned_sequence_scanned_position(SCANNED_SEQUENCE_T *sequence);

MATCHED_ELEMENT_T *allocate_matched_element(
  int start,
  int stop,
  SCANNED_SEQUENCE_T *parent
);
void free_matched_element(MATCHED_ELEMENT_T *element);
int get_matched_element_start(MATCHED_ELEMENT_T *matched_element);
void set_matched_element_start(MATCHED_ELEMENT_T *matched_element, int newstart);
int get_matched_element_stop(MATCHED_ELEMENT_T *matched_element);
void set_matched_element_stop(MATCHED_ELEMENT_T *element, int newstop);
void set_matched_element_score(MATCHED_ELEMENT_T *element, double score);
double get_matched_element_score(MATCHED_ELEMENT_T *element);
void set_matched_element_pvalue(MATCHED_ELEMENT_T *element, double pvalue);
double get_matched_element_pvalue(MATCHED_ELEMENT_T *element);
const char *get_matched_element_sequence(MATCHED_ELEMENT_T *element);
char *get_mutable_matched_element_sequence(MATCHED_ELEMENT_T *element);
void set_matched_element_strand(MATCHED_ELEMENT_T *element, char strand);
char get_matched_element_strand(MATCHED_ELEMENT_T *element);
void set_matched_element_sequence(MATCHED_ELEMENT_T *element, const char *seq, size_t length);

#endif
