#include "pmet-fimo-binary.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "pmet-index-MemCheck.h"

static const char* vector_seq_name(const MotifHitVector* vec) {
  if (!vec)
    return NULL;
  if (vec->shared_sequence_name)
    return vec->shared_sequence_name;
  if (vec->size > 0 && vec->hits)
    return vec->hits[0].sequence_name;
  return NULL;
}

int pmet_fimo_binary_write_motif(FILE* file, const char* motif_name, size_t num_vectors,
                                 MotifHitVector* const* vectors) {
  if (!file || !motif_name)
    return -1;

  size_t motif_name_len = strlen(motif_name);
  if (motif_name_len > 0xFFFFFFFFu)
    return -1;

  size_t num_hits = 0;
  size_t name_pool_size = 0;
  for (size_t i = 0; i < num_vectors; i++) {
    const MotifHitVector* vec = vectors[i];
    if (!vec || vec->size == 0)
      continue;
    const char* name = vector_seq_name(vec);
    if (!name)
      return -1;
    name_pool_size += strlen(name) + 1; // +1 for terminating NUL
    num_hits += (size_t)vec->size;
  }
  if (num_hits > 0xFFFFFFFFu || name_pool_size > 0xFFFFFFFFu)
    return -1;

  PmetBinHeader hdr;
  memcpy(hdr.magic, PMET_FIMO_BIN_MAGIC, PMET_FIMO_BIN_MAGIC_LEN);
  hdr.num_hits = (uint32_t)num_hits;
  hdr.name_pool_size = (uint32_t)name_pool_size;
  hdr.motif_name_len = (uint32_t)motif_name_len;
  hdr.reserved = 0;

  if (fwrite(&hdr, sizeof(hdr), 1, file) != 1)
    return -1;
  if (motif_name_len > 0 && fwrite(motif_name, 1, motif_name_len, file) != motif_name_len)
    return -1;

  if (name_pool_size == 0)
    return 0; // zero hits — header only

  /* Build name pool + hits buffer in memory, then write in two fwrite calls.
   * Faster than per-record fwrite and lets us compute seq_name_offset once
   * per vector. */
  if (num_hits > SIZE_MAX / sizeof(PmetBinHit))
    return -1; // multiplication overflow

  char* name_pool = (char*)new_malloc(name_pool_size);
  if (!name_pool)
    return -1;
  PmetBinHit* hits_buf = (PmetBinHit*)new_malloc(num_hits * sizeof(PmetBinHit));
  if (!hits_buf) {
    new_free(name_pool);
    return -1;
  }

  size_t pool_pos = 0;
  size_t hit_pos = 0;
  for (size_t i = 0; i < num_vectors; i++) {
    const MotifHitVector* vec = vectors[i];
    if (!vec || vec->size == 0)
      continue;
    const char* name = vector_seq_name(vec);
    size_t nlen = strlen(name);
    uint32_t name_offset = (uint32_t)pool_pos;
    memcpy(name_pool + pool_pos, name, nlen);
    name_pool[pool_pos + nlen] = '\0';
    pool_pos += nlen + 1;

    for (size_t j = 0; j < (size_t)vec->size; j++) {
      const MotifHit* hit = &vec->hits[j];
      PmetBinHit* out = &hits_buf[hit_pos++];
      out->seq_name_offset = name_offset;
      out->startPos = (uint32_t)hit->startPos;
      out->stopPos = (uint32_t)hit->stopPos;
      out->strand = (uint8_t)hit->strand;
      out->_pad[0] = out->_pad[1] = out->_pad[2] = 0;
      out->score = hit->score;
      out->pVal = hit->pVal;
    }
  }

  int rc = 0;
  if (fwrite(name_pool, 1, name_pool_size, file) != name_pool_size)
    rc = -1;
  if (rc == 0 && fwrite(hits_buf, sizeof(PmetBinHit), num_hits, file) != num_hits)
    rc = -1;

  new_free(name_pool);
  new_free(hits_buf);
  return rc;
}
