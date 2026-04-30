/*
 * Binary on-disk format for fimohits files (per motif).
 *
 * Layout (little-endian assumed; PMET only ships on x86_64/arm64):
 *
 *   PmetBinHeader (24 bytes)
 *     magic[8]       = "PMETBN01"
 *     num_hits       uint32     -- total motif hits in this file
 *     name_pool_size uint32     -- bytes occupied by the sequence-name pool
 *     motif_name_len uint32     -- exact length of the motif name (no NUL)
 *     reserved       uint32     -- must be 0
 *
 *   motif_name      char[motif_name_len]   -- not NUL-terminated on disk
 *   name pool       char[name_pool_size]   -- concatenation of NUL-terminated
 *                                             sequence names; offsets in hits
 *                                             reference byte positions inside.
 *   hits            PmetBinHit[num_hits]   -- 32-byte fixed records
 *
 *   PmetBinHit (32 bytes, packed, no internal padding holes)
 *     seq_name_offset uint32   -- offset into the name pool
 *     startPos        uint32   -- 1-based, matches text format
 *     stopPos         uint32   -- 1-based inclusive
 *     strand          char     -- '+' or '-'
 *     _pad[3]         char[3]
 *     score           double
 *     pVal            double
 *
 * The format keeps exactly the columns that pairing currently consumes from
 * the 7-column text fimohits (motif_id, sequence_name, start, stop, strand,
 * score, pVal). The matched_sequence column is intentionally not written —
 * pairing already ignores it and indexing skips it by default.
 */

#ifndef PMET_FIMO_BINARY_H
#define PMET_FIMO_BINARY_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "pmet-index-MotifHitVector.h"

#define PMET_FIMO_BIN_MAGIC "PMETBN01"
#define PMET_FIMO_BIN_MAGIC_LEN 8
#define PMET_FIMO_BIN_EXT ".bin"

#pragma pack(push, 1)
typedef struct {
  char magic[PMET_FIMO_BIN_MAGIC_LEN];
  uint32_t num_hits;
  uint32_t name_pool_size;
  uint32_t motif_name_len;
  uint32_t reserved;
} PmetBinHeader;

typedef struct {
  uint32_t seq_name_offset;
  uint32_t startPos;
  uint32_t stopPos;
  uint8_t strand;
  uint8_t _pad[3];
  double score;
  double pVal;
} PmetBinHit;
#pragma pack(pop)

/*
 * Write a motif's top-N promoter MotifHitVectors to `file` in binary form.
 *
 * `vectors[i]` is the hit list for the i-th promoter (already in the desired
 * output order — caller is responsible for ordering). Each vector's
 * `shared_sequence_name` (or its first hit's `sequence_name`) is used as the
 * promoter name in the on-disk pool.
 *
 * Returns 0 on success, non-zero on I/O failure.
 */
int pmet_fimo_binary_write_motif(FILE* file, const char* motif_name, size_t num_vectors,
                                 MotifHitVector* const* vectors);

#endif /* PMET_FIMO_BINARY_H */
