#include "pmet-index-MemCheck.h"

#include <stdio.h>
#include <stdlib.h>

// Head of the leak-tracking linked list. Currently the dbg_* wrappers below
// don't actually populate it (the mem_node_add call sites are commented out),
// so this lives as scaffolding for opt-in leak tracking — flip the comments
// back on in dbg_malloc / dbg_calloc / dbg_realloc / dbg_strdup / dbg_free
// when you want a leak report at exit.
mem_node* head = NULL;

// Allocate a tracking node and prepend it to the list.
static void mem_node_add(void* ptr, size_t block, size_t line, char* filename) {
  mem_node* node = malloc(sizeof(mem_node));
  node->ptr = ptr;
  node->block = block;
  node->line = line;
  node->filename = filename;
  node->next = NULL;

  if (head) {
    node->next = head;
    head = node;
  } else
    head = node;
}

// Remove the node tracking `ptr` from the list. No-op if not found.
static void mem_node_remove(void* ptr) {
  if (head) {
    if (head->ptr == ptr) {
      mem_node* pn = head->next;
      new_free(head);
      head = pn;
    } else {
      mem_node* pn = head->next;
      mem_node* pc = head;
      while (pn) {
        mem_node* pnext = pn->next;
        if (pn->ptr == ptr) {
          pc->next = pnext;
          new_free(pn);
        } else
          pc = pc->next;
        pn = pnext;
      }
    }
  } else {
    printf("\nError: Try to free a non-existing pointer\n");
  }
}

// Print the leak report (or "no leaks" if the tracking list is empty).
void show_block() {
  if (head) {
    size_t total = 0;
    mem_node* pn = head;

    puts("\n\n------------------- Memory leak report -------------------\n");

    while (pn) {
      mem_node* pnext = pn->next;
      // Strip directory prefix for compactness — keep only the last path
      // segment after a '\'.
      char *pfile = pn->filename, *plast = pn->filename;
      while (*pfile) {
        if (*pfile == '\\')
          plast = pfile + 1;
        pfile++;
      }
      printf("File: %s, line: %zu, address: %p (%zu bytes)\n", plast, pn->line, pn->ptr, pn->block);
      total += pn->block;
      new_free(pn);
      pn = pnext;
    }
    printf("Total memory leaked: %zu bytes\n", total);
  } else {
    printf("\n\nNo memory leak\n");
  }
}

// Debug-friendly malloc that can record the call-site for leak tracking.
// Tracking is opt-in: uncomment the mem_node_add line to enable.
void* dbg_malloc(size_t elem_size, char* filename, size_t line) {
  void* ptr = malloc(elem_size);
  // mem_node_add(ptr, elem_size, line, filename);
  (void)filename;
  (void)line;
  return ptr;
}

char* dbg_strdup(const char* s, char* filename, size_t line) {
  if (!s) return NULL;

  char* ptr = strdup(s);
  // mem_node_add(ptr, strlen(s) + 1, line, filename);
  (void)filename;
  (void)line;
  return ptr;
}

void* dbg_calloc(size_t count, size_t elem_size, char* filename, size_t line) {
  void* ptr = calloc(count, elem_size);
  // mem_node_add(ptr, elem_size * count, line, filename);
  (void)filename;
  (void)line;
  return ptr;
}

void* dbg_realloc(void* original_ptr, size_t new_size, char* filename, size_t line) {
  void* new_ptr = realloc(original_ptr, new_size);
  // If tracking is enabled, the new_ptr may differ from original_ptr — remove
  // the old record and add the new one. Currently disabled.
  (void)filename;
  (void)line;
  return new_ptr;
}

void dbg_free(void* ptr) {
  free(ptr);
  // mem_node_remove(ptr);
}
