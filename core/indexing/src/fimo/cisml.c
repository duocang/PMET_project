#include "cisml.h"

#include <string.h>

struct pattern {
  char *accession;
  char *name;
};

struct scanned_sequence {
  char *accession;
  char *name;
  PATTERN_T *parent_pattern;
  long num_scanned_positions;
};

struct matched_element {
  int start;
  int stop;
  double score;
  double pvalue;
  char *sequence;
  size_t sequence_capacity;
  char strand;
  SCANNED_SEQUENCE_T *parent_sequence;
};

PATTERN_T *allocate_pattern(char *accession, char *name) {
  PATTERN_T *pattern = mm_malloc(sizeof(PATTERN_T));
  pattern->accession = strdup(accession != NULL ? accession : "");
  pattern->name = strdup(name != NULL ? name : "");
  return pattern;
}

void free_pattern(PATTERN_T *pattern) {
  if (pattern == NULL) return;
  myfree(pattern->accession);
  myfree(pattern->name);
  myfree(pattern);
}

char *get_pattern_name(PATTERN_T *pattern) {
  return pattern->name;
}

char *get_pattern_accession(PATTERN_T *pattern) {
  return pattern->accession;
}

SCANNED_SEQUENCE_T *allocate_scanned_sequence(
  char *accession,
  char *name,
  PATTERN_T *parent
) {
  SCANNED_SEQUENCE_T *scanned_sequence = mm_malloc(sizeof(SCANNED_SEQUENCE_T));
  scanned_sequence->accession = strdup(accession != NULL ? accession : "");
  scanned_sequence->name = strdup(name != NULL ? name : "");
  scanned_sequence->parent_pattern = parent;
  scanned_sequence->num_scanned_positions = 0;
  return scanned_sequence;
}

void free_scanned_sequence(SCANNED_SEQUENCE_T *scanned_sequence) {
  if (scanned_sequence == NULL) return;
  myfree(scanned_sequence->accession);
  myfree(scanned_sequence->name);
  myfree(scanned_sequence);
}

PATTERN_T *get_scanned_sequence_parent(SCANNED_SEQUENCE_T *scanned_sequence) {
  return scanned_sequence->parent_pattern;
}

char *get_scanned_sequence_name(SCANNED_SEQUENCE_T *scanned_sequence) {
  return scanned_sequence->name;
}

void add_scanned_sequence_scanned_position(SCANNED_SEQUENCE_T *sequence) {
  ++sequence->num_scanned_positions;
}

MATCHED_ELEMENT_T *allocate_matched_element(
  int start,
  int stop,
  SCANNED_SEQUENCE_T *parent
) {
  MATCHED_ELEMENT_T *element = mm_malloc(sizeof(MATCHED_ELEMENT_T));
  element->start = start;
  element->stop = stop;
  element->score = 0.0;
  element->pvalue = 1.0;
  element->sequence = NULL;
  element->sequence_capacity = 0;
  element->strand = '+';
  element->parent_sequence = parent;
  return element;
}

void free_matched_element(MATCHED_ELEMENT_T *element) {
  if (element == NULL) return;
  myfree(element->sequence);
  myfree(element);
}

int get_matched_element_start(MATCHED_ELEMENT_T *matched_element) {
  return matched_element->start;
}

void set_matched_element_start(MATCHED_ELEMENT_T *matched_element, int newstart) {
  matched_element->start = newstart;
}

int get_matched_element_stop(MATCHED_ELEMENT_T *matched_element) {
  return matched_element->stop;
}

void set_matched_element_stop(MATCHED_ELEMENT_T *element, int newstop) {
  element->stop = newstop;
}

void set_matched_element_score(MATCHED_ELEMENT_T *element, double score) {
  element->score = score;
}

double get_matched_element_score(MATCHED_ELEMENT_T *element) {
  return element->score;
}

void set_matched_element_pvalue(MATCHED_ELEMENT_T *element, double pvalue) {
  element->pvalue = pvalue;
}

double get_matched_element_pvalue(MATCHED_ELEMENT_T *element) {
  return element->pvalue;
}

const char *get_matched_element_sequence(MATCHED_ELEMENT_T *element) {
  return element->sequence;
}

char *get_mutable_matched_element_sequence(MATCHED_ELEMENT_T *element) {
  return element->sequence;
}

void set_matched_element_strand(MATCHED_ELEMENT_T *element, char strand) {
  element->strand = strand;
}

char get_matched_element_strand(MATCHED_ELEMENT_T *element) {
  return element->strand;
}

void set_matched_element_sequence(MATCHED_ELEMENT_T *element, const char *seq, size_t length) {
  if (seq == NULL) {
    myfree(element->sequence);
    element->sequence = NULL;
    element->sequence_capacity = 0;
    return;
  }

  if (element->sequence_capacity < length + 1) {
    element->sequence = mm_realloc(element->sequence, sizeof(char) * (length + 1));
    element->sequence_capacity = length + 1;
  }

  memcpy(element->sequence, seq, length);
  element->sequence[length] = '\0';
}
