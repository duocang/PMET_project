#include <stdio.h>

#include "MemCheck.h"
#include "MotifHit.h"

int main() {
#ifdef DEBUG
  atexit(show_block);  // 在程序结束后显示内存泄漏报告
#endif

  // Sample data
  const char* motif_id = "AHL12";
  const char* motif_alt_id = "孙悟空";
  const char* sequence_name = "AT1G01020";
  long startPos = 614;
  long stopPos = 621;
  char strand = '+';
  double score = 7.85401;
  double pVal = 0.000559;
  const char* sequence = "AAATAATT";
  double binScore = 0;  // Assume this is the binScore as it was not explicitly provided

  // Initialize a MotifHit instance using the init function
  MotifHit hit;
  initMotifHit(&hit, motif_id, motif_alt_id, sequence_name, startPos, stopPos, strand, score, pVal, sequence, binScore);

  // Test the initialization
  assert(strcmp(hit.motif_id, motif_id) == 0);
  assert(strcmp(hit.motif_alt_id, motif_alt_id) == 0);
  assert(strcmp(hit.sequence_name, sequence_name) == 0);
  assert(hit.startPos == startPos);
  assert(hit.stopPos == stopPos);
  assert(hit.strand == strand);
  assert(hit.score == score);
  assert(hit.pVal == pVal);
  assert(strcmp(hit.sequence, sequence) == 0);
  assert(hit.binScore == binScore);
  printf("Initialization test passed!\n");

  // Test printing the MotifHit
  printf("\nExpected Output:\n");
  printf("AHL12\t孙悟空\tAT1G01020\t614\t621\t+\t7.85401\t0.000559\tAAATAATT\t0\n");

  printf("\nActual Output:\n");
  printMotifHit(&hit);

  deleteMotifHitContents(&hit);
  printf("\n\n");

  // Simulate a sample motif hit data
  MotifHit sampleHit;
  initMotifHit(&sampleHit, "MOTIF_ID1", "MOTIF_ALT_ID1", "SEQUENCE_NAME2", 10, 20, '+', 0.95, 0.05, "AAATAATT", 0.8);

  printf("Printing sampleHit:\n");
  printMotifHit(&sampleHit);

  // For the sake of this example, let's create another motif hit and compare them
  MotifHit* anotherHit = new_malloc(sizeof(MotifHit));

  // using string literals to initialize `char*` pointers
  // no need to free them
  anotherHit->motif_id = "MOTIF_ID2";
  anotherHit->motif_alt_id = "MOTIF_ALT_ID2";
  anotherHit->sequence_name = "SEQUENCE_NAME2";
  anotherHit->startPos = 15;
  anotherHit->stopPos = 25;
  anotherHit->strand = '-';
  anotherHit->score = 0.90;
  anotherHit->pVal = 0.10;
  anotherHit->sequence = "AAATAATT";
  anotherHit->binScore = 0.75;

  printf("Printing anotherHit:\n");
  printMotifHit(anotherHit);

  // Compare the p-values of the two hits using sortHits function
  int comparison = sortHits(&sampleHit, anotherHit);
  if (comparison < 0) {
    printf("\nThe sampleHit has a lower pVal than anotherHit.\n");
  } else if (comparison > 0) {
    printf("\nThe anotherHit has a lower pVal than sampleHit.\n");
  } else {
    printf("\nBoth hits have the same pVal.\n");
  }

  // sampleHit were initialized without allocating ram, no need to free
  new_free(anotherHit);

  // 添加边界条件测试
  printf("\n=== Testing edge cases ===\n");

  // 测试NULL指针处理
  MotifHit nullTest;
  initMotifHit(&nullTest, NULL, NULL, NULL, 0, 0, '+', 0.0, 0.0, NULL, 0.0);
  printf("NULL pointer test completed\n");
  deleteMotifHitContents(&nullTest);

  // 测试空字符串
  MotifHit emptyTest;
  initMotifHit(&emptyTest, "", "", "", 0, 0, '+', 0.0, 0.0, "", 0.0);
  printf("Empty string test completed\n");
  deleteMotifHitContents(&emptyTest);

  // 测试排序功能
  printf("\n=== Testing sorting ===\n");
  MotifHit hits[3];
  initMotifHit(&hits[0], "M1", "A1", "S1", 1, 10, '+', 1.0, 0.1, "ATCG", 0.5);
  initMotifHit(&hits[1], "M2", "A2", "S2", 1, 10, '+', 2.0, 0.05, "ATCG", 0.6);
  initMotifHit(&hits[2], "M3", "A3", "S3", 1, 10, '+', 3.0, 0.2, "ATCG", 0.4);

  printf("Before sorting (by pVal):\n");
  for (int i = 0; i < 3; i++) {
    printf("Hit %d: pVal = %f\n", i, hits[i].pVal);
  }

  // 简单的冒泡排序测试sortHits函数
  for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 2 - i; j++) {
      if (sortHits(&hits[j], &hits[j + 1]) > 0) {
        MotifHit temp = hits[j];
        hits[j] = hits[j + 1];
        hits[j + 1] = temp;
      }
    }
  }

  printf("After sorting (by pVal):\n");
  for (int i = 0; i < 3; i++) {
    printf("Hit %d: pVal = %f\n", i, hits[i].pVal);
  }

  // 清理内存
  for (int i = 0; i < 3; i++) {
    deleteMotifHitContents(&hits[i]);
  }

  return 0;
}

// 编译命令:
// clang -DDEBUG -I src -o test test/TestMotifHit.c src/MotifHit.c src/MemCheck.c
// 或者使用更严格的编译选项:
// clang -DDEBUG -Wall -Wextra -I src -o test test/TestMotifHit.c src/MotifHit.c src/MemCheck.c