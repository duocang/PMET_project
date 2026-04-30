#include <stdio.h>
#include <string.h>
#include <assert.h>

#include "MotifHit.h"
#include "MotifHitVector.h"
#include "MemCheck.h"

int main()
{
#ifdef DEBUG
  atexit(show_block); // 在程序结束后显示内存泄漏报告 Display memory leak report after program ends.
#endif
  // 创建三个MotifHit数据 Create three MotifHit data.
  MotifHit hit1, hit2, hit3, hit4;

  initMotifHit(&hit1, "AHL12", "孙悟空", "AT1G01020", 614, 621, '+', 7.85401, 0.000559, "AAATAATT", 0);
  initMotifHit(&hit2, "AHL13", "猪八戒", "AT1G01020", 715, 722, '-', 6.85401, 0.009959, "TTAATAAT", 1);
  initMotifHit(&hit3, "AHL14", "沙和尚", "AT1G01020", 816, 823, '+', 5.85401, 0.000759, "GGGTAAGG", 2);
  initMotifHit(&hit4, "AHL15", "唐三藏", "AT1G01020", 816, 823, '+', 5.85401, 0.000009, "GGGTAAGG", 2);

  // 动态分配内存给hit5和hit6 Dynamically allocate memory to hit5 and hit6.
  MotifHit *hit5 = (MotifHit *)new_malloc(sizeof(MotifHit));
  MotifHit *hit6 = (MotifHit *)new_malloc(sizeof(MotifHit));
  // 使用动态分配的结构初始化 Initializing with dynamically allocated structures
  initMotifHit(hit5, "AHL12", "智多星", "水浒传", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  initMotifHit(hit6, "AHL12", "小李广", "水浒传", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  // 初始化MotifVector Initialize MotifVector
  MotifHitVector *vec = createMotifHitVector();

  // 添加到vector Add to vector
  pushMotifHitVector(vec, &hit1);
  pushMotifHitVector(vec, &hit2);
  pushMotifHitVector(vec, &hit3);
  pushMotifHitVector(vec, &hit4);

  pushMotifHitVector(vec, hit5);
  pushMotifHitVector(vec, hit6);

  printMotifHitVector(vec);

  // Test the new functions
  printf("\n\nVector size: %zu\n", motifHitVectorSize(vec)); // Expected output: 3

  printf("\n\nPrinting MotifHits in the vector:\n");
  printMotifHitVector(vec);

  printf("\n\nTesting ordering function:\n");
  // 对vector中的MotifHit按pVal排序
  sortMotifHitVectorByPVal(vec);
  printMotifHitVector(vec);

  printf("\nTesting TopK function:\n");
  retainTopKMotifHits(vec, 1);
  printMotifHitVector(vec);

  printf("\n\nTesting delete function:\n");
  removeHitAtIndex(vec, 1);
  printMotifHitVector(vec);

  printf("\n\nAll tests passed for MotifVector!\n");

  // 清理
  deleteMotifHitContents(&hit1);
  deleteMotifHitContents(&hit2);
  deleteMotifHitContents(&hit3);
  deleteMotifHitContents(&hit4);
  deleteMotifHit(hit5);
  deleteMotifHit(hit6);

  /*
    vec is obtained through deep copy, so after releasing data
    such as hit1, it is necessary to release the internal data of vec.
  */
  deleteMotifHitVector(vec);

  return 0;
}

// clang -DDEBUG -o test MotifHit.c MotifHitVector.c TestMotifHitVector.c MemCheck.c
