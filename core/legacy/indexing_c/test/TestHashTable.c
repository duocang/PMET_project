#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "HashTable.h"
#include "MotifHit.h"
#include "MotifHitVector.h"

#include "MemCheck.h"

// size_t TABLE_SIZE = 79;

// 要放入哈希表中的结构体 Structures to be placed in the hash table
struct Student
{
  size_t age;
  float score;
  char name[32];
  char data[1024 * 1024 * 10];
};

// 结构体内存释放函数 Release Function of the structure
static void free_student(void *stu)
{
  new_free(stu);
}

// 显示学生信息的函数 Function to display student information
static void show_student(struct Student *p)
{
  printf("姓名name:%s, 年龄age:%zu, 学分score:%.2f\n", p->name, p->age, p->score);
}

void testStudent()
{
  // 新建一个HashTable实例
  HashTable *ht = createHashTable();
  if (NULL == ht)
  {
    printf("Fail to create a hash table!\n");
  }

  // 向哈希表中加入多个学生结构体
  for (size_t i = 0; i < 10; i++)
  {
    struct Student *stu = (struct Student *)new_malloc(sizeof(struct Student));
    stu->age = 18 + rand() % 5;
    stu->score = 50.0f + rand() % 100;
    sprintf(stu->name, "同学student%zu", i);
    putHashTable2(ht, stu->name, stu, free_student);
  }

  // 根据学生姓名查找学生结构 Search for student structure based on teacher name.
  for (size_t i = 0; i < 10; i++)
  {
    char name[32];
    sprintf(name, "同学student%zu", i);
    struct Student *stu = (struct Student *)getHashTable(ht, name);
    show_student(stu);
  }

  // 销毁哈希表实例
  deleteHashTable(ht);
}

// 要放入哈希表中的结构体 Structures to be placed in the hash table
struct Teacher
{
  size_t age;
  size_t id;
  char *name;
  char data[1024 * 1024 * 10];
};

// 结构体内存释放函数 Release Function of the structure
static void free_teacher(void *tec)
{
  struct Teacher *t = (struct Teacher *)tec;
  new_free(t->name); // Free the dynamically allocated name
  new_free(t);   // Free the teacher struct itself
}

// 显示教师信息的函数 Function to display teacher information
static void show_teacher(struct Teacher *p)
{
  printf("姓名name:%s, 年龄age:%zu, 工号id:%.2zu\n", p->name, p->age, p->id);
}

void testTeacher()
{
  // 新建一个HashTable实例
  HashTable *ht = createHashTable();
  if (NULL == ht)
  {
    printf("Fail to create a hash table!\n");
  }

  // 向哈希表中加入多个教师结构体 add teacher
  for (size_t i = 0; i < 10; i++)
  {
    struct Teacher *tec = (struct Teacher *)new_malloc(sizeof(struct Teacher));
    tec->age = 18 + rand() % 5;
    tec->id = 50.0f + rand() % 100;

    char name_buffer[100]; // Temporary buffer to format the name
    sprintf(name_buffer, "教师 teacher%zu", i);

    tec->name = strdup(name_buffer); // Duplicate the string to assign to tec->name

    putHashTable2(ht, tec->name, tec, free_teacher);
  }

  // 根据教师姓名查找教师结构 Search for teacher structure based on teacher name.
  for (size_t i = 0; i < 10; i++)
  {
    char name[32];
    sprintf(name, "教师 teacher%zu", i);
    struct Teacher *tec = (struct Teacher *)getHashTable(ht, name);
    show_teacher(tec);
  }

  // 销毁哈希表实例
  deleteHashTable(ht);
}

static void free_hit(void *hit)
{
  MotifHit *hp = (MotifHit *)hit;
  deleteMotifHitContents(hp);
}

void testMotif()
{
  MotifHit hit1, hit2, hit3, hit4;
  initMotifHit(&hit1, "AHL12", "孙悟空", "西游记", 614, 621, '+', 7.8501, 0.000559, "AAATAATT", 0);
  initMotifHit(&hit2, "AHL12", "唐三藏", "西游记", 700, 708, '-', 8.5001, 0.000600, "AAGGTTAA", 1);
  initMotifHit(&hit3, "AHL12", "诸葛亮", "三国志", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  initMotifHit(&hit4, "AHL12", "刘皇叔", "三国志", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  HashTable *ht = createHashTable();
  if (NULL == ht)
  {
    printf("Fail to create a hash table!\n");
  }

  putHashTable2(ht, "西游记", &hit1, free_hit);
  putHashTable2(ht, "西游记", &hit2, free_hit);
  putHashTable2(ht, "三国志", &hit3, free_hit);
  putHashTable2(ht, "三国志", &hit4, free_hit);

  MotifHit *hit = getHashTable(ht, "西游记");

  printMotifHit(hit);

  deleteHashTable(ht);
}

void freeVec(void *ptr)
{
  MotifHitVector *vec = (MotifHitVector *)ptr;

  printMotifHitVector(vec);

  if (vec)
  {
    deleteMotifHitVectorContents(vec); // 释放 hits 数组 release
    new_free(vec);                     // 释放 MotifHitVector 结构 release
  }
}

void testMotifVector()
{
  MotifHit hit3, hit4;

  initMotifHit(&hit3, "AHL12", "诸葛亮", "三国志", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  initMotifHit(&hit4, "AHL12", "刘皇叔", "三国志", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  // 动态分配内存给hit5和hit6
  MotifHit *hit5 = (MotifHit *)new_malloc(sizeof(MotifHit));
  MotifHit *hit6 = (MotifHit *)new_malloc(sizeof(MotifHit));
  // 使用动态分配的结构初始化
  initMotifHit(hit5, "AHL12", "智多星", "水浒传", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  initMotifHit(hit6, "AHL12", "小李广", "水浒传", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  printMotifHit(hit5);
  printMotifHit(hit6);

  MotifHitVector *vec2 = createMotifHitVector();

  MotifHitVector *vec3 = (MotifHitVector *)new_malloc(sizeof(MotifHitVector));
  vec3->size = 0;
  vec3->capacity = 10;
  vec3->hits = (MotifHit*)new_malloc(vec3->capacity * sizeof(MotifHit));


  pushMotifHitVector(vec2, &hit3);
  pushMotifHitVector(vec2, &hit4);
  pushMotifHitVector(vec3, hit5);
  pushMotifHitVector(vec3, hit6);

  HashTable *ht = createHashTable();
  if (NULL == ht)
  {
    printf("Fail to create a hash table!\n");
  }

  putHashTable2(ht, "三国志", vec2, freeVec);
  putHashTable2(ht, "水浒传", vec3, freeVec);

  printf("\n提取三国志：\n");
  MotifHitVector *vec = getHashTable(ht, "三国志");
  printMotifHitVector(vec);


  printf("\n提取水浒传：\n");
  vec = getHashTable(ht, "水浒传");
  printMotifHitVector(vec);


  deleteMotifHitContents(&hit3);
  deleteMotifHitContents(&hit4);
  deleteMotifHit(hit5);
  deleteMotifHit(hit6);

  deleteHashTable(ht);
}

int main()
{
#ifdef DEBUG
  atexit(show_block); // 在程序结束后显示内存泄漏报告 Display memory leak report after program ends.
#endif

  // testStudent();
  // testTeacher();
  // testMotif();
  testMotifVector();
  return 0;
}

// clang -DDEBUG -o test TestHashTable.c HashTable.c MotifHit.c MotifHitVector.c MemCheck.c
