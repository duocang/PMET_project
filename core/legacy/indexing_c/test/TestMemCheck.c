#include <stdio.h>
#include <string.h>
#ifdef DEBUG
#include "MemCheck.h"
#endif

typedef struct
{
  char name[50];
  int age;
  int student_id;
} Student;

Student *create_student(const char *name, int age, int student_id)
{
  Student *s = (Student *)new_malloc(sizeof(Student));
  if (!s)
  {
    perror("Failed to allocate memory for student");
    exit(EXIT_FAILURE);
  }
  strncpy(s->name, name, sizeof(s->name) - 1);
  s->name[sizeof(s->name) - 1] = '\0'; // Ensure null-terminated
  s->age = age;
  s->student_id = student_id;
  return s;
}

int main()
{
  int *p;
  int *q;

#ifdef DEBUG
  atexit(show_block); // 在程序结束后显示内存泄漏报告 Display memory leak report after program ends.
#endif                // DEBUG
  // 分配内存并不回收，显示内存泄漏报告 Allocate memory and do not reclaim it, show memory leak report
  q = (int *)new_malloc(5);

  // 分配内存并回收，则不显示内存泄漏报告 Allocate and deallocate memory, no memory leak report will be displayed.
  p = (int *)new_malloc(5);
  new_free(p);

  Student *s;
  s = create_student("Alice", 20, 12345);

  printf("Name: %s\n", s->name);
  printf("Age: %d\n", s->age);
  printf("Student ID: %d\n", s->student_id);


  char *str1 = new_strdup("Hello, World!");

  char *str2 = new_strdup("Hello, World!");

  new_free(str1);


  return 0;
}

// 编译命令：
// 调试模式（显示内存泄漏）: gcc -DDEBUG -o test/TestMemCheck test/TestMemCheck.c src/MemCheck.c -I src/
// 普通模式: gcc -o test/TestMemCheck test/TestMemCheck.c src/MemCheck.c -I src/