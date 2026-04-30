#include "pmet-index-SiteStore.h"

#include "pmet-index-MotifHit.h"

void insert_site_into_store(FILE* tsv_out, bool print_qvalue, MATCHED_ELEMENT_T* match, SCANNED_SEQUENCE_T* scanned_seq,
                            MotifHitVector* vec) {
  (void)tsv_out;
  (void)print_qvalue;

  PATTERN_T* pattern = get_scanned_sequence_parent(scanned_seq);
  char* motif_id = get_pattern_accession(pattern);
  char* motif_id2 = get_pattern_name(pattern);
  char* seq_name = get_scanned_sequence_name(scanned_seq);
  char* seq = (char*)get_matched_element_sequence(match);
  int start = get_matched_element_start(match);
  int stop = get_matched_element_stop(match);
  if (stop < start) {
    int tmp = start;
    start = stop;
    stop = tmp;
  }

  MotifHit hit;
  initMotifHitBorrowMeta(&hit, motif_id, motif_id2, seq_name, start, stop, get_matched_element_strand(match),
                         get_matched_element_score(match), get_matched_element_pvalue(match), seq, 0.0);
  pushMotifHitVectorMove(vec, &hit);
}
