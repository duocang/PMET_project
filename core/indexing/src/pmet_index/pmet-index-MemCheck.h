#ifndef PMET_INDEX_MEM_CHECK_H
#define PMET_INDEX_MEM_CHECK_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// One node in the leak-tracking list, recording the call-site of every
// outstanding allocation so we can dump them at process exit.
typedef struct _mem_node {
  void* ptr;      // leaked address
  size_t block;   // size of the allocation
  size_t line;    // source line that allocated it
  char* filename; // source file that allocated it
  struct _mem_node* next;
} mem_node;

// PMET code uses these wrappers (not bare malloc/free) so every allocation is
// tagged with its call-site for the leak report at exit.
#define new_malloc(s) dbg_malloc(s, __FILE__, __LINE__)
#define new_calloc(c, s) dbg_calloc(c, s, __FILE__, __LINE__)
#define new_realloc(p, s) dbg_realloc(p, s, __FILE__, __LINE__)
#define new_strdup(s) dbg_strdup(s, __FILE__, __LINE__)
#define new_free(p) dbg_free(p)

/**
 * allocate memory
 */
void* dbg_malloc(size_t elem_size, char* filename, size_t line);

char* dbg_strdup(const char* s, char* filename, size_t line);

/**
 * allocation and zero memory
 */
void* dbg_calloc(size_t count, size_t elem_size, char* filename, size_t line);

/**
 * The movement of memory and may return a different pointer address if the original
 * block cannot be extended.
*/
void* dbg_realloc(void* original_ptr, size_t new_size, char* filename, size_t line);

/**
 * deallocate memory
 */
void dbg_free(void* ptr);

/**
 * show memory leak report
 */
void show_block();

#endif // PMET_INDEX_MEM_CHECK_H
