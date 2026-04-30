#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

#include "ScoreLabelPairVector.h"

int main()
{
#ifdef DEBUG
  atexit(show_block); // 在程序结束后显示内存泄漏报告 Display memory leak report after program ends.
#endif
  ScoreLabelPairVector *vec = createScoreLabelPairVector();

  // Add items to the vector
  pushBack(vec, 3.4, "C");
  pushBack(vec, 1.2, "A");
  pushBack(vec, 2.7, "B");
  pushBack(vec, 4.8, "D");

  printf("Before sorting:\n");
  printVector(vec);

  // Sort and print
  sortVector(vec);

  printf("\nAfter sorting:\n");
  printVector(vec);



  printf("\nTop %d\n", 3);
  retainTopN(vec, 3);
  printVector(vec);

  // Find score by label
  char *searchLabel = "B";
  double foundScore = findScoreByLabel(vec, searchLabel);
  if (foundScore != -1.0)
  {
    printf("\nScore for label %s: %f\n", searchLabel, foundScore);
  }
  else
  {
    printf("\nLabel %s not found.\n", searchLabel);
  }

  // Clean up
  deleteScoreLabelVectorContents(vec);
  return 0;
}

// clang -DDEBUG -o test TestScoreLabelPairVector.c ScoreLabelPairVector.c MemCheck.c
