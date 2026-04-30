#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "FileRead.h"
#include "MemCheck.h"


size_t readFileAndCountLines(const char *filename, char **content)
{
  size_t numLines = 0;
  FILE *file = fopen(filename, "rb"); // 改为二进制模式

  if (!file)
  {
    perror("Error opening file");
    exit(ERR_OPEN_FILE);
  }

  // Get the file length.
  fseek(file, 0, SEEK_END);
  long flength = ftell(file);

  if (flength == -1L)
  {
    perror("Error determining file size");
    fclose(file);
    exit(ERR_OPEN_FILE);
  }

  fseek(file, 0, SEEK_SET);

  // Allocate memory for the buffer.
  *content = (char *)new_malloc(flength + 1);
  if (!*content)
  {
    perror("Error allocating memory");
    fclose(file);
    exit(1);
  }

  // Read the file content into the buffer.
  size_t bytesRead = fread(*content, 1, flength, file);
  if (ferror(file)) // 检查读取错误而不是字节数
  {
    perror("Error reading file");
    new_free(*content);
    fclose(file);
    exit(ERR_OPEN_FILE);
  }

  (*content)[bytesRead] = '\0'; // 使用实际读取的字节数

  if (fclose(file) != 0)
  {
    perror("Error closing the file");
  }

  // Count the number of lines in the buffer.
  for (size_t i = 0; i < bytesRead; i++) // 使用 size_t 和实际字节数
  {
    if ((*content)[i] == '\n')
    {
      numLines++;
    }
  }

  // Check for the last line without a newline character.
  if (bytesRead > 0 && (*content)[bytesRead - 1] != '\n')
  {
    numLines++;
  }

  return numLines;
}
