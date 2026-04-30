#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "pmet-index-PromoterLength.h"

static int comparePromotersByName(const void* lhs, const void* rhs) {
  const Promoter* a = (const Promoter*)lhs;
  const Promoter* b = (const Promoter*)rhs;
  return strcmp(a->promoterName, b->promoterName);
}

void initPromoterList(PromoterList* list) {
  if (list == NULL) {
    fprintf(stderr, "Error: The provided PromoterList pointer is NULL. Cannot initialize.\n");
    exit(EXIT_FAILURE);
  }

  list->items = NULL;
  list->size = 0;
  list->capacity = 0;
}

size_t findPromoterLength(PromoterList* list, const char* promoterName) {
  if (!list) {
    fprintf(stderr, "Error: The provided PromoterList pointer is NULL. Cannot perform the search.\n");
    return -1;
  }

  if (!promoterName) {
    fprintf(stderr, "Error: The provided promoter name is NULL. Cannot perform the search.\n");
    return -1;
  }

  size_t left = 0;
  size_t right = list->size;

  while (left < right) {
    size_t mid = left + (right - left) / 2;
    int cmp = strcmp(list->items[mid].promoterName, promoterName);
    if (cmp == 0) {
      return (size_t)list->items[mid].length;
    }
    if (cmp < 0) {
      left = mid + 1;
    } else {
      right = mid;
    }
  }
  return -1; // Not found
}

void deletePromoterLenListContents(PromoterList* list) {
  if (!list) {
    fprintf(stderr, "Warning: Attempted to free a NULL PromoterList. Operation skipped.\n");
    return;
  }
  // Start timing
  clock_t start_time = clock();
  size_t i;
  for (i = 0; i < list->size; i++) {
    if (list->items[i].promoterName) {
      new_free(list->items[i].promoterName);
    }
  }
  new_free(list->items);
  list->items = NULL;
  list->size = 0;
  list->capacity = 0;

  // Stop timing
  clock_t end_time = clock();

#ifdef DEBUG
  // Calculate and print the elapsed time.
  double time_taken = ((double)end_time - start_time) / CLOCKS_PER_SEC; // in seconds
  printf("deletePromoterLenListContents took %f seconds to execute.\n", time_taken);
#endif
}

void deletePromoterLenList(PromoterList* list) {
  if (!list) {
    fprintf(stderr, "Warning: Attempted to free a NULL PromoterList. Operation skipped.\n");
    return;
  }

  deletePromoterLenListContents(list);

  new_free(list);
}

void insertPromoter(PromoterList* list, const char* promoterName, int length) {
  if (!list) {
    fprintf(stderr, "Error: The provided PromoterList pointer is NULL. Cannot insert.\n");
    exit(EXIT_FAILURE);
  }

  if (!promoterName) {
    fprintf(stderr, "Error: The provided promoter name is NULL. Cannot insert.\n");
    exit(EXIT_FAILURE);
  }

  if (list->size == list->capacity) {
    size_t new_capacity = (list->capacity == 0) ? 1024 : list->capacity * 2;
    Promoter* new_items = (Promoter*)new_realloc(list->items, new_capacity * sizeof(Promoter));
    if (!new_items) {
      perror("Failed to allocate memory for promoter list");
      exit(EXIT_FAILURE);
    }
    list->items = new_items;
    list->capacity = new_capacity;
  }

  list->items[list->size].promoterName = new_strdup(promoterName);
  if (!list->items[list->size].promoterName) {
    perror("Failed to allocate memory for promoter name");
    exit(EXIT_FAILURE);
  }

  list->items[list->size].length = length;
  list->size++;
}

size_t readPromoterLengthFile(PromoterList* list, const char* filename) {
  if (list == NULL) {
    fprintf(stderr, "Error: The provided PromoterList pointer is NULL. Cannot initialize.\n");
    exit(EXIT_FAILURE);
  }

  // Initialize PromoterList
  initPromoterList(list);

  FILE* file = fopen(filename, "r");
  if (!file) {
    perror("Failed to open file");
    return 0; // Return 0 if unable to open the file
  }

  char promoterName[MAX_PROMOTER_NAME_LENGTH];
  long length;
  size_t lineCount = 0; // To keep track of the number of lines read

  while (fscanf(file, "%99s %ld", promoterName, &length) == 2) {
    // Read max 99 chars to prevent overflow
    lineCount++; // Increase the count for every line read

    if (strlen(promoterName) >= MAX_PROMOTER_NAME_LENGTH - 1) {
      fprintf(stderr, "Promoter name too long: %s\n", promoterName);
      continue; // Skip this line and move to next
    }

    insertPromoter(list, promoterName, length);
  }

  if (list->size > 1) {
    qsort(list->items, list->size, sizeof(Promoter), comparePromotersByName);
  }

  if (fclose(file) != 0) {
    perror("Failed to close the file");
  }

  return lineCount; // Return the number of lines read
}
