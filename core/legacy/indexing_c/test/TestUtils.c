#include "utils.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

int main()
{
#ifdef DEBUG
  atexit(show_block); // 在程序结束后显示内存泄漏报告 Display memory leak report after program ends.
#endif
  char *result = paste(5, "-", "Hello", "world", "this", "is", "C", NULL);
  printf("%s\n", result); // Outputs: Hello-world-this-is-C
  new_free(result);

  result = paste(5, NULL, "Hello", "world", "this", "is", "C");
  printf("%s\n", result); // Outputs: Hello-world-this-is-C
  new_free(result);

  result = paste(5, "", "Hello", "world", "this", "is", "C");
  printf("%s\n", result); // Outputs: Hello-world-this-is-C
  new_free(result);

  result = paste2("Hello", "world", "-");
  printf("%s\n", result); // Outputs: Hello-world-this-is-C
  new_free(result);

  result = paste2("", "Hello", "world");
  printf("%s\n", result); // Outputs: Hello-world-this-is-C
  new_free(result);

  result = paste2(NULL, "Hello", "world");
  printf("%s\n", result); // Outputs: Hello-world-this-is-C
  new_free(result);
  return 0;
}

// clang -DDEBUG  -o test TestUtils.c utils.c MemCheck.c
