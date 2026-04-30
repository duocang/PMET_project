#include "PromoterLength.h"

int main()
{
#ifdef DEBUG
  atexit(show_block); // 在程序结束后显示内存泄漏报告
#endif

  PromoterList *list = new_malloc(sizeof(PromoterList));
  initPromoterList(list);

  readPromoterLengthFile(list, "test_data/promoter_lengths.txt");

  printf("Length of AT1G01010: %zu\n", findPromoterLength(list, "AT1G01010"));
  // ... you can test with other gene names

  deletePromoterLenList(list);
  return 0;
}
// clang -DDEBUG -o test TestPromoterLength.c PromoterLength.c MemCheck.c
