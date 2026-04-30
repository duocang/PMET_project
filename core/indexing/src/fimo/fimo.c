/********************************************************************
 * FILE: fimo.c
 * AUTHOR: William Stafford Noble, Charles E. Grant, Timothy Bailey
 * CREATE DATE: 12/17/2004
 * PROJECT: MEME suite
 * COPYRIGHT: 2004-2007, UW
 ********************************************************************/

#ifdef MAIN
#define DEFINE_GLOBALS
#endif

#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#ifdef _OPENMP
#include <omp.h>
#endif
#include "alphabet.h"
#include "cisml.h"
#include "config.h"
#include "dir.h"
#include "fimo.h"
#include "matrix.h"
#include "motif-in.h"
#include "pmet-sequence-library.h"
#include "pssm.h"
#include "seq.h"
#include "simple-getopt.h"
#include "string-list.h"
#include "utils.h"
// #include "wiggle-reader.h"

#include "pmet-fimo-binary.h"
#include "pmet-index-FileRead.h"
#include "pmet-index-MemCheck.h"
#include "pmet-index-MotifHit.h"
#include "pmet-index-MotifHitVector.h"
#include "pmet-index-PromoterLength.h"
#include "pmet-index-ScoreLabelPairVector.h"
#include "pmet-index-SiteStore.h"
#include "pmet-index-pair-test.h"
#include "pmet-index-utils.h"

/* Global verbosity used by `extern VERBOSE_T verbosity` declarations in the
 * MEME Suite headers we link against. */
VERBOSE_T verbosity = NORMAL_VERBOSE;

char* program_name = "fimo";

/* Ensure a directory exists; create it if missing. */
static void ensure_dir_exists(const char* path) {
  struct stat st;
  if (stat(path, &st) != 0) {
    if (mkdir(path, 0777) != 0) {
      fprintf(stderr, "Error: Failed to create directory: %s\n", path);
      exit(EXIT_FAILURE);
    }
  } else {
    if (!S_ISDIR(st.st_mode)) {
      fprintf(stderr, "Error: Path exists but is not a directory: %s\n", path);
      exit(EXIT_FAILURE);
    }
  }
}

typedef struct {
  int motif_index;
  int has_threshold;
  double threshold_score;
  char* motif_output_id;
  char* bare_motif_id;
} PMET_MOTIF_TASK_RESULT;

typedef struct PMET_MOTIF_RUNTIME PMET_MOTIF_RUNTIME;

static long fimo_score_sequence(const FIMO_OPTIONS_T options, const PMET_SEQUENCE_RECORD* sequence_record,
                                MOTIF_T* motif, MOTIF_T* rev_motif, PSSM_T* pssm, PSSM_T* rev_pssm, PATTERN_T* pattern,
                                MotifHitVector* vec);

static void fimo_build_pssms(MOTIF_T* motif, MOTIF_T* rev_motif, const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs,
                             PSSM_T** pos_pssm, PSSM_T** rev_pssm);

static int determine_motif_batch_size(int task_count);
static void init_motif_runtime(const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs, ARRAYLST_T* motifs, int motif_index,
                               int task_pos, int topn, PMET_MOTIF_RUNTIME* runtime);
static void destroy_motif_runtime(PMET_MOTIF_RUNTIME* runtime);
static void score_sequence_for_runtime(const FIMO_OPTIONS_T options, const PMET_SEQUENCE_RECORD* sequence_record,
                                       int topk, PMET_MOTIF_RUNTIME* runtime);
static void finalize_motif_runtime(const char* out_dir_no_slash, bool text_output, PMET_MOTIF_RUNTIME* runtime,
                                   PMET_MOTIF_TASK_RESULT* task_result);
static void process_motif_batch(const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs, ARRAYLST_T* motifs,
                                const int* task_indices, int batch_start, int batch_count, const char* out_dir_no_slash,
                                int topn, int topk, const PMET_SEQUENCE_LIBRARY* sequence_library,
                                PMET_MOTIF_TASK_RESULT* task_results);

/* Parse a CLI value as a base-10 int with full-string validation.
 * atoi() silently returns 0 on garbage like "abc" or "10.5" — these wrappers
 * report the offending option so the user gets a clean error instead of a
 * mystery default. Exits on parse failure (caller is in argv parsing, no
 * cleanup needed). */
static long parse_cli_long(const char* flag, const char* s) {
  if (!s || !*s) {
    fprintf(stderr, "Error: option '--%s' requires a value.\n", flag);
    exit(EXIT_FAILURE);
  }
  char* end = NULL;
  long v = strtol(s, &end, 10);
  if (*end != '\0') {
    fprintf(stderr, "Error: option '--%s' expects an integer, got '%s'.\n", flag, s);
    exit(EXIT_FAILURE);
  }
  return v;
}

static double parse_cli_double(const char* flag, const char* s) {
  if (!s || !*s) {
    fprintf(stderr, "Error: option '--%s' requires a value.\n", flag);
    exit(EXIT_FAILURE);
  }
  char* end = NULL;
  double v = strtod(s, &end);
  if (*end != '\0') {
    fprintf(stderr, "Error: option '--%s' expects a number, got '%s'.\n", flag, s);
    exit(EXIT_FAILURE);
  }
  return v;
}

static char* create_output_motif_id(const char* motif_id) {
  char* output_motif_id = new_strdup(motif_id);
  if (!output_motif_id) {
    fprintf(stderr, "Error: Failed to allocate motif output id.\n");
    exit(EXIT_FAILURE);
  }

  int i;
  for (i = 0; output_motif_id[i]; i++) {
    if (output_motif_id[i] >= 'a' && output_motif_id[i] <= 'z') {
      output_motif_id[i] = output_motif_id[i] - 'a' + 'A';
    }
  }

  if (output_motif_id[0] == '+') {
    memmove(output_motif_id, output_motif_id + 1, strlen(output_motif_id));
  }

  return output_motif_id;
}

static void filter_overlapping_hits_mark_compact(MotifHitVector* vec, size_t k) {
  if (!vec || vec->size == 0) {
    return;
  }

  size_t vec_size = vec->size;
  char* removed = (char*)new_calloc(vec_size, sizeof(char));
  if (!removed) {
    fprintf(stderr, "Error: Failed to allocate removal markers.\n");
    exit(EXIT_FAILURE);
  }

  size_t kept_count = 0;
  size_t current_index;
  for (current_index = 0; current_index < vec_size && kept_count < k; current_index++) {
    if (removed[current_index])
      continue;

    size_t next_index;
    for (next_index = current_index + 1; next_index < vec_size; next_index++) {
      if (!removed[next_index] && motifsOverlap(&vec->hits[current_index], &vec->hits[next_index])) {
        removed[next_index] = 1;
      }
    }
    kept_count++;
  }

  size_t write_index = 0;
  size_t i;
  for (i = 0; i < vec_size; i++) {
    if (!removed[i]) {
      if (write_index != i) {
        vec->hits[write_index] = vec->hits[i];
      }
      write_index++;
    } else {
      deleteMotifHitContents(&vec->hits[i]);
    }
  }

  vec->size = write_index;
  new_free(removed);
}

typedef struct {
  double score;
  char* label;
  MotifHitVector* vec;
} PMET_TOPN_ENTRY;

typedef struct {
  PMET_TOPN_ENTRY* items;
  size_t size;
  size_t capacity;
} PMET_TOPN_HEAP;

struct PMET_MOTIF_RUNTIME {
  int task_pos;
  int motif_index;
  MOTIF_T* motif;
  MOTIF_T* rev_motif;
  int motif_length;
  char* motif_id;
  char* bare_motif_id;
  char* bare_motif_id2;
  char* output_motif_id;
  PSSM_T* pos_pssm;
  PSSM_T* rev_pssm;
  PATTERN_T* pattern;
  PMET_TOPN_HEAP topn_promoters;
};

static bool topn_entry_is_worse(const PMET_TOPN_ENTRY* lhs, const PMET_TOPN_ENTRY* rhs) {
  if (lhs->score > rhs->score)
    return true;
  if (lhs->score < rhs->score)
    return false;
  return strcmp(lhs->label, rhs->label) > 0;
}

static bool topn_candidate_is_better(double score, const char* label, const PMET_TOPN_ENTRY* worst_kept) {
  if (score < worst_kept->score)
    return true;
  if (score > worst_kept->score)
    return false;
  return strcmp(label, worst_kept->label) < 0;
}

static int determine_motif_batch_size(int task_count) {
  if (task_count <= 1)
    return 1;

  const char* env_value = getenv("PMET_MOTIF_BATCH_SIZE");
  if (env_value != NULL && env_value[0] != '\0') {
    char* endptr = NULL;
    long parsed = strtol(env_value, &endptr, 10);
    if (endptr != env_value && parsed > 0) {
      if (parsed > task_count)
        parsed = task_count;
      return (int)parsed;
    }
  }

  int max_threads = 1;
#ifdef _OPENMP
  max_threads = omp_get_max_threads();
#endif

  int target_batches = max_threads * 4;
  if (target_batches < 1)
    target_batches = 1;

  int batch_size = (task_count + target_batches - 1) / target_batches;
  if (batch_size < 1)
    batch_size = 1;
  if (batch_size > 16)
    batch_size = 16;

  return batch_size;
}

static int compare_topn_entries_for_output(const void* lhs, const void* rhs) {
  const PMET_TOPN_ENTRY* a = (const PMET_TOPN_ENTRY*)lhs;
  const PMET_TOPN_ENTRY* b = (const PMET_TOPN_ENTRY*)rhs;
  if (a->score < b->score)
    return -1;
  if (a->score > b->score)
    return 1;
  return strcmp(a->label, b->label);
}

static void init_topn_heap(PMET_TOPN_HEAP* heap, size_t capacity) {
  heap->items = NULL;
  heap->size = 0;
  heap->capacity = capacity;
  if (capacity == 0)
    return;

  heap->items = (PMET_TOPN_ENTRY*)new_malloc(capacity * sizeof(PMET_TOPN_ENTRY));
  if (!heap->items) {
    fprintf(stderr, "Error: Failed to allocate top-N promoter heap.\n");
    exit(EXIT_FAILURE);
  }
}

static void delete_topn_entry_contents(PMET_TOPN_ENTRY* entry) {
  if (entry->vec) {
    deleteMotifHitVector(entry->vec);
    entry->vec = NULL;
  }
  new_free(entry->label);
  entry->label = NULL;
}

static void delete_topn_heap_contents(PMET_TOPN_HEAP* heap) {
  if (!heap)
    return;

  for (size_t i = 0; i < heap->size; i++) {
    delete_topn_entry_contents(&heap->items[i]);
  }
  new_free(heap->items);
  heap->items = NULL;
  heap->size = 0;
  heap->capacity = 0;
}

static void topn_heap_sift_up(PMET_TOPN_HEAP* heap, size_t index) {
  while (index > 0) {
    size_t parent = (index - 1) / 2;
    if (!topn_entry_is_worse(&heap->items[index], &heap->items[parent]))
      break;

    PMET_TOPN_ENTRY tmp = heap->items[parent];
    heap->items[parent] = heap->items[index];
    heap->items[index] = tmp;
    index = parent;
  }
}

static void topn_heap_sift_down(PMET_TOPN_HEAP* heap, size_t index) {
  while (true) {
    size_t left = index * 2 + 1;
    size_t right = left + 1;
    size_t worst = index;

    if (left < heap->size && topn_entry_is_worse(&heap->items[left], &heap->items[worst])) {
      worst = left;
    }
    if (right < heap->size && topn_entry_is_worse(&heap->items[right], &heap->items[worst])) {
      worst = right;
    }
    if (worst == index)
      break;

    PMET_TOPN_ENTRY tmp = heap->items[index];
    heap->items[index] = heap->items[worst];
    heap->items[worst] = tmp;
    index = worst;
  }
}

static void topn_heap_consider(PMET_TOPN_HEAP* heap, double score, const char* label, MotifHitVector* vec) {
  if (heap->capacity == 0) {
    deleteMotifHitVector(vec);
    return;
  }

  if (heap->size == heap->capacity && !topn_candidate_is_better(score, label, &heap->items[0])) {
    deleteMotifHitVector(vec);
    return;
  }

  char* label_copy = new_strdup(label);
  if (!label_copy) {
    fprintf(stderr, "Error: Failed to allocate top-N promoter label.\n");
    deleteMotifHitVector(vec);
    exit(EXIT_FAILURE);
  }

  PMET_TOPN_ENTRY candidate;
  candidate.score = score;
  candidate.label = label_copy;
  candidate.vec = vec;

  if (heap->size < heap->capacity) {
    heap->items[heap->size] = candidate;
    topn_heap_sift_up(heap, heap->size);
    heap->size++;
    return;
  }

  delete_topn_entry_contents(&heap->items[0]);
  heap->items[0] = candidate;
  topn_heap_sift_down(heap, 0);
}

static void init_motif_runtime(const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs, ARRAYLST_T* motifs, int motif_index,
                               int task_pos, int topn, PMET_MOTIF_RUNTIME* runtime) {
  runtime->task_pos = task_pos;
  runtime->motif_index = motif_index;
  runtime->motif = (MOTIF_T*)arraylst_get(motif_index, motifs);
  runtime->rev_motif = NULL;
  if (options.scan_both_strands) {
    runtime->rev_motif = (MOTIF_T*)arraylst_get(motif_index + 1, motifs);
  }

  runtime->motif_id = get_motif_st_id(runtime->motif);
  runtime->bare_motif_id = get_motif_id(runtime->motif);
  runtime->bare_motif_id2 = get_motif_id2(runtime->motif);
  runtime->motif_length = get_motif_length(runtime->motif);

  if (verbosity >= NORMAL_VERBOSE) {
    fprintf(stderr, "Using motif %s of width %d.\n", runtime->motif_id, runtime->motif_length);
    if (runtime->rev_motif) {
      fprintf(stderr, "Using motif %s of width %d.\n", get_motif_st_id(runtime->rev_motif), runtime->motif_length);
    }
  }

  runtime->output_motif_id = create_output_motif_id(runtime->motif_id);
  runtime->pos_pssm = NULL;
  runtime->rev_pssm = NULL;
  fimo_build_pssms(runtime->motif, runtime->rev_motif, options, bg_freqs, &runtime->pos_pssm, &runtime->rev_pssm);
  runtime->pattern = allocate_pattern(runtime->bare_motif_id, runtime->bare_motif_id2);
  init_topn_heap(&runtime->topn_promoters, (size_t)topn);
}

static void destroy_motif_runtime(PMET_MOTIF_RUNTIME* runtime) {
  if (!runtime)
    return;

  delete_topn_heap_contents(&runtime->topn_promoters);
  if (runtime->pattern) {
    free_pattern(runtime->pattern);
    runtime->pattern = NULL;
  }
  if (runtime->pos_pssm) {
    free_pssm(runtime->pos_pssm);
    runtime->pos_pssm = NULL;
  }
  if (runtime->rev_pssm) {
    free_pssm(runtime->rev_pssm);
    runtime->rev_pssm = NULL;
  }
  if (runtime->output_motif_id) {
    new_free(runtime->output_motif_id);
    runtime->output_motif_id = NULL;
  }
}

static void score_sequence_for_runtime(const FIMO_OPTIONS_T options, const PMET_SEQUENCE_RECORD* sequence_record,
                                       int topk, PMET_MOTIF_RUNTIME* runtime) {
  const char* fasta_seq_name = get_seq_name(sequence_record->seq);
  MotifHitVector* vec = createMotifHitVector();

  (void)fimo_score_sequence(options, sequence_record, runtime->motif, runtime->rev_motif, runtime->pos_pssm,
                            runtime->rev_pssm, runtime->pattern, vec);

  if (vec->size == 0) {
    deleteMotifHitVector(vec);
    return;
  }

  sortMotifHitVectorByPVal(vec);
  filter_overlapping_hits_mark_compact(vec, (size_t)topk);

  if (vec->size == 0) {
    deleteMotifHitVector(vec);
    return;
  }

  if (vec->size > (size_t)topk) {
    retainTopKMotifHits(vec, (size_t)topk);
  }

  Pair binom_p = geometricBinTest(vec, sequence_record->promoter_length, runtime->motif_length);

  if (vec->size > (size_t)(binom_p.idx + 1)) {
    retainTopKMotifHits(vec, (size_t)(binom_p.idx + 1));
  }

  topn_heap_consider(&runtime->topn_promoters, binom_p.score, fasta_seq_name, vec);
}

static void finalize_motif_runtime(const char* out_dir_no_slash, bool text_output, PMET_MOTIF_RUNTIME* runtime,
                                   PMET_MOTIF_TASK_RESULT* task_result) {
  task_result->motif_index = runtime->motif_index;
  task_result->has_threshold = 0;
  task_result->threshold_score = 0.0;
  task_result->motif_output_id = runtime->output_motif_id;
  runtime->output_motif_id = NULL;
  // Carry the original-case motif id so binomial_thresholds keys match the
  // motif name written into the .bin header (and the IC/threshold lookup
  // pairing performs against it). bare_motif_id is owned by the MOTIF_T,
  // so we strdup to outlive the parallel batch.
  task_result->bare_motif_id = runtime->bare_motif_id ? new_strdup(runtime->bare_motif_id) : NULL;

  if (runtime->topn_promoters.size == 0) {
    return;
  }

  const char* ext = text_output ? ".txt" : PMET_FIMO_BIN_EXT;
  char* motif_hit_file_path = paste(4, "", out_dir_no_slash, "/fimohits/", task_result->motif_output_id, ext);
  FILE* motif_hit_file = fopen(motif_hit_file_path, text_output ? "a" : "wb");
  if (motif_hit_file == NULL) {
    fprintf(stderr, "Failed to open motif hit file for writing: %s (%s)\n", motif_hit_file_path, strerror(errno));
    exit(EXIT_FAILURE);
  }

  qsort(runtime->topn_promoters.items, runtime->topn_promoters.size, sizeof(PMET_TOPN_ENTRY),
        compare_topn_entries_for_output);

  if (text_output) {
    for (size_t i = 0; i < runtime->topn_promoters.size; i++) {
      writeVectorToStream(runtime->topn_promoters.items[i].vec, motif_hit_file);
    }
  } else {
    /* Binary writer wants an array of MotifHitVector* — build one from the
     * top-N entries (already sorted in output order). */
    size_t n = runtime->topn_promoters.size;
    MotifHitVector** vecs = (MotifHitVector**)new_malloc(n * sizeof(MotifHitVector*));
    if (!vecs) {
      fprintf(stderr, "Failed to allocate vector pointer array for binary fimohits.\n");
      exit(EXIT_FAILURE);
    }
    for (size_t i = 0; i < n; i++) {
      vecs[i] = runtime->topn_promoters.items[i].vec;
    }
    /* Use the bare motif id (matches text format column 1, e.g. lower-case
     * original from the MEME file), not the upper-cased output id used for
     * the filename, so pairing's IC/threshold lookup keeps working. */
    const char* motif_name = runtime->bare_motif_id ? runtime->bare_motif_id : runtime->motif_id;
    if (pmet_fimo_binary_write_motif(motif_hit_file, motif_name, n, vecs) != 0) {
      fprintf(stderr, "Failed to write binary fimohits for motif %s.\n", motif_name);
      exit(EXIT_FAILURE);
    }
    new_free(vecs);
  }

  task_result->has_threshold = 1;
  task_result->threshold_score = runtime->topn_promoters.items[runtime->topn_promoters.size - 1].score;

  if (fclose(motif_hit_file) != 0) {
    fprintf(stderr, "Error closing motif hit file %s.\n", motif_hit_file_path);
    exit(EXIT_FAILURE);
  }
  new_free(motif_hit_file_path);
}

static void process_motif_batch(const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs, ARRAYLST_T* motifs,
                                const int* task_indices, int batch_start, int batch_count, const char* out_dir_no_slash,
                                int topn, int topk, const PMET_SEQUENCE_LIBRARY* sequence_library,
                                PMET_MOTIF_TASK_RESULT* task_results) {
  if (!sequence_library) {
    fprintf(stderr, "Error: Failed to initialize motif batch state.\n");
    exit(EXIT_FAILURE);
  }

  PMET_MOTIF_RUNTIME* runtimes = (PMET_MOTIF_RUNTIME*)new_calloc((size_t)batch_count, sizeof(PMET_MOTIF_RUNTIME));

  for (int batch_offset = 0; batch_offset < batch_count; batch_offset++) {
    int task_pos = batch_start + batch_offset;
    init_motif_runtime(options, bg_freqs, motifs, task_indices[task_pos], task_pos, topn, &runtimes[batch_offset]);
  }

  for (size_t seq_index = 0; seq_index < sequence_library->count; seq_index++) {
    const PMET_SEQUENCE_RECORD* sequence_record = &sequence_library->records[seq_index];
    for (int batch_offset = 0; batch_offset < batch_count; batch_offset++) {
      score_sequence_for_runtime(options, sequence_record, topk, &runtimes[batch_offset]);
    }
  }

  for (int batch_offset = 0; batch_offset < batch_count; batch_offset++) {
    PMET_MOTIF_RUNTIME* runtime = &runtimes[batch_offset];
    finalize_motif_runtime(out_dir_no_slash, options.text_output, runtime, &task_results[runtime->task_pos]);
    destroy_motif_runtime(runtime);
  }

  new_free(runtimes);
}

/***********************************************************************
  Free memory allocated in options processing
 ***********************************************************************/
static void cleanup_options(FIMO_OPTIONS_T options) {
  free_string_list(options.selected_motifs);
  if (options.alphabet != NULL)
    alph_release(options.alphabet);
}

/***********************************************************************
  Process command line options
 ***********************************************************************/
static FIMO_OPTIONS_T process_fimo_command_line(int argc, char* argv[]) {

  FIMO_OPTIONS_T options;

  // Define command line options.
  cmdoption const fimo_options[] = {{"bfile", REQUIRED_VALUE},
                                    {"bgfile", REQUIRED_VALUE},
                                    {"keep-matched-sequence", NO_VALUE},
                                    {"motif", REQUIRED_VALUE},
                                    {"motif-pseudo", REQUIRED_VALUE},
                                    {"norc", NO_VALUE},
                                    {"o", REQUIRED_VALUE},
                                    {"oc", REQUIRED_VALUE},
                                    {"no-qvalue", NO_VALUE},
                                    {"parse-genomic-coord", NO_VALUE},
                                    {"text", NO_VALUE},
                                    {"topk", REQUIRED_VALUE},
                                    {"topn", REQUIRED_VALUE},
                                    {"skip-matched-sequence", NO_VALUE},
                                    {"text-output", NO_VALUE},
                                    {"thresh", REQUIRED_VALUE},
                                    {"verbosity", REQUIRED_VALUE},
                                    {"version", NO_VALUE}};
  const int num_options = sizeof(fimo_options) / sizeof(cmdoption);

  // Define the usage message.
  options.usage = "Usage: fimo [options] <motif file> <sequence file> <promoter length file>\n"
                  "\n"
                  "   Options:\n"
                  "     --oc                     <output dir> (default: fimo_out)\n"
                  "     --o                      <output dir> (same as --oc)\n"
                  "     --text                   (accepted for compatibility; PMET mode is always text-only)\n"
                  "     --no-qvalue              (accepted for compatibility; q-values are not computed)\n"
                  "     --keep-matched-sequence  (disabled by default in PMET mode)\n"
                  "     --skip-matched-sequence\n"
                  "     --text-output            (write text fimohits/*.txt instead of binary fimohits/*.bin)\n"
                  "     --motif                  <id> (default: all)\n"
                  "     --motif-pseudo           <float> (default: 0.1)\n"
                  "     --parse-genomic-coord\n"
                  "     --bfile                  <background file>\n"
                  "     --thresh                 <float> (default: 1e-4)\n"
                  "     --topk                   <int> (default: 5)\n"
                  "     --topn                   <int> (default: 5000)\n"
                  "     --norc\n"
                  "     --version (print the version and exit)\n"
                  "     --verbosity [1|2|3|4|5] (default: 2)\n"
                  "\n"
                  "   This PMET-integrated build supports MEME text motif input and FASTA promoter input.\n"
                  "\n";

  int option_index = 0;

  /* Make sure various options are set to NULL or defaults. */
  options.parse_genomic_coord = false;
  options.scan_both_strands = true;
  options.skip_matched_sequence = true;
  options.text_output = false; // default: binary fimohits

  options.bg_filename = NULL;
  options.meme_filename = NULL;
  options.output_dirname = "fimo_out";
  options.seq_filename = NULL;
  options.promoter_length = NULL;

  options.pseudocount = 0.1;
  options.output_threshold = 1e-4;

  options.topk = 5;
  options.topn = 5000;

  options.selected_motifs = new_string_list();
  options.alphabet = NULL;
  verbosity = 2;

  simple_setopt(argc, argv, num_options, fimo_options);

  // Parse the command line.
  while (true) {
    int c = 0;
    char* option_name = NULL;
    char* option_value = NULL;
    const char* message = NULL;

    // Read the next option, and break if we're done.
    c = simple_getopt(&option_name, &option_value, &option_index);
    if (c == 0) {
      break;
    } else if (c < 0) {
      (void)simple_getopterror(&message);
      die("Error processing command line options: %s\n", message);
    }
    if (strcmp(option_name, "bfile") == 0 || strcmp(option_name, "bgfile") == 0) {
      options.bg_filename = option_value;
    } else if (strcmp(option_name, "motif") == 0) {
      if (options.selected_motifs == NULL) {
        options.selected_motifs = new_string_list();
      }
      add_string(option_value, options.selected_motifs);
    } else if (strcmp(option_name, "motif-pseudo") == 0) {
      options.pseudocount = parse_cli_double(option_name, option_value);
    } else if (strcmp(option_name, "norc") == 0) {
      options.scan_both_strands = false;
    } else if (strcmp(option_name, "o") == 0) {
      options.output_dirname = option_value;
    } else if (strcmp(option_name, "oc") == 0) {
      options.output_dirname = option_value;
    } else if (strcmp(option_name, "parse-genomic-coord") == 0) {
      options.parse_genomic_coord = true;
    } else if (strcmp(option_name, "thresh") == 0) {
      options.output_threshold = parse_cli_double(option_name, option_value);
    } else if (strcmp(option_name, "no-qvalue") == 0) {
      // Accepted for CLI compatibility; PMET mode never computes q-values.
    } else if (strcmp(option_name, "keep-matched-sequence") == 0) {
      options.skip_matched_sequence = false;
    } else if (strcmp(option_name, "skip-matched-sequence") == 0) {
      options.skip_matched_sequence = true;
    } else if (strcmp(option_name, "text") == 0) {
      // Accepted for CLI compatibility; PMET mode is always text-only.
    } else if (strcmp(option_name, "text-output") == 0) {
      options.text_output = true;
    } else if (strcmp(option_name, "topk") == 0) {
      options.topk = (int)parse_cli_long(option_name, option_value);
    } else if (strcmp(option_name, "topn") == 0) {
      options.topn = (int)parse_cli_long(option_name, option_value);
    } else if (strcmp(option_name, "verbosity") == 0) {
      verbosity = (int)parse_cli_long(option_name, option_value);
    } else if (strcmp(option_name, "version") == 0) {
      fprintf(stdout, VERSION "\n");
      exit(EXIT_SUCCESS);
    }
  }

  // Must have sequence and motif file names
  if (argc != option_index + 3) {
    fprintf(stderr, "%s", options.usage);
    exit(EXIT_FAILURE);
  }

  // Record the input file names
  options.meme_filename = argv[option_index];
  option_index++;
  options.seq_filename = argv[option_index];
  option_index++;
  options.promoter_length = argv[option_index];
  option_index++;

  return options;
} // process_fimo_command_line

/**********************************************
* Read the motifs from the motif file.
**********************************************/
static void fimo_read_motifs(FIMO_OPTIONS_T* options, ARRAYLST_T** motifs, ARRAY_T** bg_freqs) {

  MREAD_T* mread;

  mread = mread_create(options->meme_filename, OPEN_MFILE, options->scan_both_strands);
  mread_set_bg_source(mread, options->bg_filename, NULL);
  mread_set_pseudocount(mread, options->pseudocount);

  *motifs = mread_load(mread, NULL);
  options->alphabet = alph_hold(mread_get_alphabet(mread));

  // Check that the reading of the motif file was successful.
  if (options->alphabet == NULL) {
    die("An error occurred reading the motif file.\n");
  }

  *bg_freqs = mread_get_background(mread);
  options->bg_filename = mread_get_other_bg_src(mread);
  mread_destroy(mread);

  // Check that we got back some motifs
  int num_motif_names = arraylst_size(*motifs);
  if (num_motif_names == 0) {
    die("No motifs could be read.\n");
  }

  // If motifs use protein alphabet we will not scan both strands
  if (!alph_has_complement(options->alphabet)) {
    options->scan_both_strands = false;
  }

  if (options->scan_both_strands == true) {
    add_reverse_complements(*motifs); // Make reverse complement motifs.
  }
}

/*************************************************************************
 * Write a motif match to the appropriate output files.
 *************************************************************************/
static void fimo_record_score(const FIMO_OPTIONS_T options, SCANNED_SEQUENCE_T* scanned_seq, MATCHED_ELEMENT_T* match,
                              MotifHitVector* NodeStore) {
  double pvalue = get_matched_element_pvalue(match);
  add_scanned_sequence_scanned_position(scanned_seq);

  if (pvalue <= options.output_threshold) {
    insert_site_into_store(stdout, false, match, scanned_seq, NodeStore);
  }
}

/*************************************************************************
 * Calculate the log odds score for a single motif-sized window.
 *************************************************************************/
static inline bool fimo_score_site(const int8_t* encoded_seq, PSSM_T* pssm,
                                   double* pvalue, // OUT
                                   double* score   // OUT
) {

  ARRAY_T* pv_lookup = pssm->pv;
  MATRIX_T* pssm_matrix = pssm->matrix;
  bool scorable_site = true;
  double scaled_log_odds = 0.0;

  // For each position in the site
  int motif_position;
  for (motif_position = 0; motif_position < pssm->w; motif_position++) {
    int aindex = encoded_seq[motif_position];

    // Check for gaps and ambiguity codes at this site
    if (aindex < 0) {
      scorable_site = false;
      break;
    }
    scaled_log_odds += get_matrix_cell(motif_position, aindex, pssm_matrix);
  } // position

  if (scorable_site == true) {

    int w = pssm->w;
    *score = get_unscaled_pssm_score(scaled_log_odds, pssm);

    // Handle scores that are out of range
    // This should never happen and indicates a bug has been
    // introduced in the code if it does.
    int max_log_odds = get_array_length(pv_lookup) - 1;
    if (scaled_log_odds < 0.0) {
      fprintf(stderr, "Scaled log-odds score out of range: %d\n", (int)scaled_log_odds);
      fprintf(stderr, "Assigning 0 to scaled log-odds score.\n");
      scaled_log_odds = 0.0;
    } else if ((int)scaled_log_odds > max_log_odds) {
      fprintf(stderr, "Scaled log-odds score out of range: %d\n", (int)scaled_log_odds);
      fprintf(stderr, "Assigning %d to scaled log-odds score.\n", max_log_odds);
      scaled_log_odds = (float)max_log_odds;
    }
    // Round scores and pvalues to 10 significant digits so they will be consistent across platforms
    // (especially cross-compiled Docker).
    *score = scaled_to_raw(scaled_log_odds, w, pssm->scale, pssm->offset);
    RND(*score, 10, *score);
    *pvalue = get_array_item((int)scaled_log_odds, pv_lookup);
    RND(*pvalue, 10, *pvalue);

  } // scorable_site

  return scorable_site;
} // fimo_score_site

/*************************************************************************
 * Calculate and record the log-odds score and p-value for each
 * possible motif site in the sequence.
 *
 * Returns the length of the sequence.
 *************************************************************************/
static long fimo_score_sequence(const FIMO_OPTIONS_T options, const PMET_SEQUENCE_RECORD* sequence_record,
                                MOTIF_T* motif, MOTIF_T* rev_motif, PSSM_T* pssm, PSSM_T* rev_pssm, PATTERN_T* pattern,
                                MotifHitVector* vec) {
  assert(sequence_record != NULL);
  assert(motif != NULL);
  assert(pssm != NULL);

  SEQ_T* sequence = sequence_record->seq;
  char* fasta_seq_name = get_seq_name(sequence);
  const int8_t* encoded_seq = get_isequence(sequence);
  char* raw_seq = (options.skip_matched_sequence ? NULL : get_raw_sequence(sequence));
  const size_t seq_length = get_seq_length(sequence);
  const unsigned int seq_starting_coord = get_seq_starting_coord(sequence);

  // Create a scanned_sequence record and record it in pattern.
  SCANNED_SEQUENCE_T* scanned_seq = allocate_scanned_sequence(fasta_seq_name, fasta_seq_name, pattern);

  MATCHED_ELEMENT_T* fwd_match = NULL;
  MATCHED_ELEMENT_T* rev_match = NULL;
  fwd_match = allocate_matched_element(0, 0, scanned_seq);
  if (rev_pssm) {
    rev_match = allocate_matched_element(0, 0, scanned_seq);
  }

  int motif_width = get_motif_length(motif);
  long num_positions = (seq_length >= (size_t)motif_width ? (long)(seq_length - (size_t)motif_width + 1U) : 0L);

  for (size_t position = 0; position + (size_t)motif_width <= seq_length; position++) {
    int fwd_start = (int)(seq_starting_coord + position + 1U);
    int rev_stop = fwd_start;
    int fwd_stop = fwd_start + motif_width - 1;
    int rev_start = fwd_stop;
    set_matched_element_start(fwd_match, fwd_start);
    set_matched_element_stop(fwd_match, fwd_stop);
    if (rev_pssm) {
      set_matched_element_start(rev_match, rev_start);
      set_matched_element_stop(rev_match, rev_stop);
    }

    if (!options.skip_matched_sequence) {
      set_matched_element_sequence(fwd_match, raw_seq + position, motif_width);
    }
    set_matched_element_strand(fwd_match, '+');
    if (rev_pssm) {
      // Since we're using the reverse complemment motif
      // convert sequence to reverse complment for output.
      if (!options.skip_matched_sequence) {
        set_matched_element_sequence(rev_match, raw_seq + position, motif_width);
        invcomp_seq(options.alphabet, get_mutable_matched_element_sequence(rev_match), motif_width, false);
      }
      set_matched_element_strand(rev_match, '-');
    }

    bool scoreable_site = false;
    double fwd_score = NAN;
    double fwd_pvalue = NAN;
    double rev_score = NAN;
    double rev_pvalue = NAN;

    // Always score forward strand
    scoreable_site = fimo_score_site(encoded_seq + position, pssm, &fwd_pvalue, &fwd_score);
    if (scoreable_site) {
      set_matched_element_score(fwd_match, fwd_score);
      set_matched_element_pvalue(fwd_match, fwd_pvalue);
    }
    if (scoreable_site && rev_pssm != NULL) {
      // Score reverse strand if reverse PSSM available.
      scoreable_site = fimo_score_site(encoded_seq + position, rev_pssm, &rev_pvalue, &rev_score);
      if (scoreable_site) {
        set_matched_element_score(rev_match, rev_score);
        set_matched_element_pvalue(rev_match, rev_pvalue);
      }
    }

    if (scoreable_site) {
      fimo_record_score(options, scanned_seq, fwd_match, vec);
      if (rev_match) {
        fimo_record_score(options, scanned_seq, rev_match, vec);
      }
    }
  }

  if (vec->size > 0) {
    setMotifHitVectorSharedSequenceName(vec, fasta_seq_name);
  }

  free_matched_element(fwd_match);
  if (rev_match) {
    free_matched_element(rev_match);
  }
  free_scanned_sequence(scanned_seq);

  return num_positions;
}

static void fimo_build_pssms(MOTIF_T* motif, MOTIF_T* rev_motif, const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs,
                             PSSM_T** pos_pssm, PSSM_T** rev_pssm) {
  // Build PSSM for motif and tables for p-value calculation.
  // TODO: the non-averaged freqs should be used for p-values
  *pos_pssm = build_motif_pssm(motif, bg_freqs, bg_freqs, NULL, 0.0, PSSM_RANGE,
                               0,    // no GC bins
                               false // make log-likelihood pssm
  );

  // If needed, build the PSSM for the reverse complement motif.
  if (options.scan_both_strands) {
    // TODO: the non-averaged freqs should be used for p-values
    *rev_pssm = build_motif_pssm(rev_motif, bg_freqs, bg_freqs, NULL, 0.0, PSSM_RANGE,
                                 0, // GC bins
                                 false);
  }
}

/**************************************************************
 * Score each of the sites for each of the selected motifs.
 **************************************************************/
static void fimo_score_each_motif(const FIMO_OPTIONS_T options, ARRAY_T* bg_freqs, ARRAYLST_T* motifs,
                                  int* num_scanned_sequences, long* num_scanned_positions, char* outDir, int N, int k,
                                  const PMET_SEQUENCE_LIBRARY* sequence_library) {
  int num_motifs = arraylst_size(motifs);
  int num_selected_motifs = get_num_strings(options.selected_motifs);
  int stride = options.scan_both_strands ? 2 : 1;
  int max_task_count = (num_motifs + stride - 1) / stride;
  int* task_indices = (int*)new_malloc(max_task_count * sizeof(int));
  int task_count = 0;

  int motif_index;
  for (motif_index = 0; motif_index < num_motifs; motif_index += stride) {
    MOTIF_T* motif = (MOTIF_T*)arraylst_get(motif_index, motifs);
    char* bare_motif_id = get_motif_id(motif);
    char* motif_id = get_motif_st_id(motif);

    if (num_selected_motifs > 0 && have_string(bare_motif_id, options.selected_motifs) == false) {
      if (verbosity >= NORMAL_VERBOSE) {
        fprintf(stderr, "Skipping motif %s.\n", motif_id);
      }
      continue;
    }

    task_indices[task_count++] = motif_index;
  }

  if (verbosity >= QUIET_VERBOSE) {
#ifdef _OPENMP
    fprintf(stderr, "Fused FIMO parallel mode: OpenMP enabled, up to %d thread(s).\n", omp_get_max_threads());
#else
    fprintf(stderr, "Fused FIMO parallel mode: OpenMP not enabled, using single-thread fallback.\n");
#endif
    fprintf(stderr, "Fused FIMO will process %d motif(s)%s.\n", task_count,
            (num_selected_motifs > 0 ? " after applying motif selection" : ""));
    fprintf(stderr, "Fused FIMO matched sequence output: %s.\n",
            (options.skip_matched_sequence ? "disabled" : "enabled"));
  }

  *num_scanned_sequences = (int)sequence_library->count;
  *num_scanned_positions = 0;

  int motif_batch_size = determine_motif_batch_size(task_count);
  int batch_count = (task_count + motif_batch_size - 1) / motif_batch_size;

  if (verbosity >= QUIET_VERBOSE) {
    fprintf(stderr, "Fused FIMO motif batching: %d batch(es), up to %d motif(s) per batch.\n", batch_count,
            motif_batch_size);
  }

  char* out_dir_no_slash = removeTrailingSlashAndReturn(outDir);
  char* fimohits_dir = paste(3, "", out_dir_no_slash, "/", "fimohits");
  ensure_dir_exists(out_dir_no_slash);
  ensure_dir_exists(fimohits_dir);

  PMET_MOTIF_TASK_RESULT* task_results = (PMET_MOTIF_TASK_RESULT*)new_calloc((size_t)task_count,
                                                                             sizeof(PMET_MOTIF_TASK_RESULT));

#ifdef _OPENMP
#pragma omp parallel for schedule(dynamic)
#endif
  for (int batch_index = 0; batch_index < batch_count; batch_index++) {
    int batch_start = batch_index * motif_batch_size;
    int current_batch_count = motif_batch_size;
    if (batch_start + current_batch_count > task_count) {
      current_batch_count = task_count - batch_start;
    }

    process_motif_batch(options, bg_freqs, motifs, task_indices, batch_start, current_batch_count, out_dir_no_slash, N,
                        k, sequence_library, task_results);
  }

  ScoreLabelPairVector* binResults = createScoreLabelPairVector();
  for (int task_pos = 0; task_pos < task_count; task_pos++) {
    if (task_results[task_pos].has_threshold) {
      const char* bin_label = task_results[task_pos].bare_motif_id ? task_results[task_pos].bare_motif_id
                                                                   : task_results[task_pos].motif_output_id;
      pushBack(binResults, task_results[task_pos].threshold_score, (char*)bin_label);
    }
    new_free(task_results[task_pos].motif_output_id);
    if (task_results[task_pos].bare_motif_id) {
      new_free(task_results[task_pos].bare_motif_id);
    }
  }

  char* binomialThresholdFilePath = paste(3, "", out_dir_no_slash, "/", "binomial_thresholds.txt");
  writeScoreLabelPairVectorToTxt(binResults, binomialThresholdFilePath);
  new_free(binomialThresholdFilePath);

  deleteScoreLabelVector(binResults);
  new_free(task_results);
  new_free(task_indices);
  new_free(fimohits_dir);
  new_free(out_dir_no_slash);
}

/*************************************************************************
 * Entry point for fimo
 *************************************************************************/
int main(int argc, char* argv[]) {

  //   /* Simple run-check print (uncomment if you want startup diagnostics). */
  //   printf("fimo: simple run check\n");
  //   printf("program: %s\n", program_name);
  // #ifdef VERSION
  //   printf("version: %s\n", VERSION);
  // #endif
  //   printf("argc = %d\n", argc);

  //   printf("\n\n******************************** Start timing *******************************\n\n");
  //   // Start timing
  //   clock_t start_time = clock();

  // Get command line arguments
  FIMO_OPTIONS_T options = process_fimo_command_line(argc, argv);

  // Set up motif input
  ARRAYLST_T* motifs = NULL;
  ARRAY_T* bg_freqs = NULL;
  fimo_read_motifs(&options, &motifs, &bg_freqs);

  // Initialize tracking variables
  int num_scanned_sequences = 0;
  long num_scanned_positions = 0;

  /****************************************************************************
   * Iterate through each motif, searching homotypic matches on all promoters
   ****************************************************************************/
  PromoterList* promoterList = new_malloc(sizeof(PromoterList));
  (void)readPromoterLengthFile(promoterList, options.promoter_length);
  PMET_SEQUENCE_LIBRARY* sequence_library = create_pmet_sequence_library(options, options.alphabet, promoterList);

  fimo_score_each_motif(options, bg_freqs, motifs, &num_scanned_sequences, &num_scanned_positions,
                        options.output_dirname, options.topn, options.topk, sequence_library);

  delete_pmet_sequence_library(sequence_library);
  deletePromoterLenList(promoterList);
  cleanup_options(options);

  show_block(); // Memory leak report (no-op unless tracking is enabled in pmet-index-MemCheck.c)

  // // Stop timing
  // clock_t end_time = clock();

  // // Calculate and print the elapsed time.
  // int time_taken = (int) ((double)end_time - start_time) / CLOCKS_PER_SEC;
  // printf("\n\n************************** %d seconds spent **************************\n\n", time_taken);

  // printf("\nDONE\n");

  return 0;
}
