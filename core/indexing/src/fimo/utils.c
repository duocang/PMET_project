/********************************************************************
 * FILE: utils.c
 * AUTHOR: William Stafford Noble
 * CREATE DATE: 9-8-97
 * PROJECT: shared
 * COPYRIGHT: 1997-2013 WSN, TLB
 * DESCRIPTION: Various useful generic utilities.
 ********************************************************************/
#include <regex.h>
#include <stdio.h>
#include <stdlib.h>
#include <libgen.h> // for basename
#include <stdarg.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include <math.h>
#include <assert.h>
#include <errno.h>
#include <ctype.h>
#include "dir.h"
#include "utils.h"

/************************************************************************
 * See .h file for description.
 ************************************************************************/
bool open_file
  (const char *    filename,            /* Name of the file to be opened. */
   const char *    file_mode,           /* Mode to be passed to fopen. */
   bool allow_stdin,         /* If true, filename "-" is stdin. */
   const char *    file_description,
   const char *    content_description,
   FILE **         afile)               /* Pointer to the open file. */
{
  if (filename == NULL) {
    fprintf(stderr, "Error: No %s filename specified.\n", file_description);
    return(false);
  } else if ((allow_stdin) && (strcmp(filename, "-") == 0)) {
    if (strchr(file_mode, 'r') != NULL) {
      fprintf(stderr, "Reading %s from stdin.\n", content_description);
      *afile = stdin;
    } else if (strchr(file_mode, 'w') != NULL) {
      fprintf(stderr, "Writing %s to stdout.\n", content_description);
      *afile = stdout;
    } else {
      fprintf(stderr, "Sorry, I can't figure out whether to use stdin ");
      fprintf(stderr, "or stdout for %s.\n", content_description);
      return(false);
    }
  } else if ((*afile = fopen(filename, file_mode)) == NULL) {
    fprintf(stderr, "Error opening file %s.\n", filename);
    return(false);
  }
  return(true);
}

/********************************************************************
 * See .h file for description.
 ********************************************************************/
void die
  (char *format,
   ...)
{
  va_list  argp;

  fprintf(stderr, "FATAL: ");
  va_start(argp, format);
  vfprintf(stderr, format, argp);
  va_end(argp);
  fprintf(stderr, "\n");
  fflush(stderr);

#ifdef DEBUG
/*
  Cause a crash
*/
  char *crash = NULL;
  *crash = 'x';
  abort();
#else
  exit(1);
#endif
}

/**************************************************************************
 * See .h file for description.
 **************************************************************************/
void myassert
  (bool die_on_error,
   bool test,
   char * const    format,
   ...)
{
  va_list  argp;

  if (!test) {

    if (die_on_error) {
      fprintf(stderr, "FATAL: ");
    } else {
      fprintf(stderr, "WARNING: ");
    }

    /* Issue the error message. */
    va_start(argp, format);
    vfprintf(stderr, format, argp);
    va_end(argp);
    fprintf(stderr, "\n");
    fflush(stderr);

    if (die_on_error) {
#ifdef DEBUG
      abort();
#else
      exit(1);
#endif
    }
  }
}

/********************************************************************
 * void mm_malloc, mm_calloc, mm_realloc
 *
 * See .h file for descriptions.
 ********************************************************************/
void *mm_malloc
  (size_t size)
{
  void * temp_ptr;

  if (size == 0)
    size++;

  temp_ptr = malloc(size);
  //memset(temp_ptr, '\0', size);		// Set this to see RAM requirements.

  if (temp_ptr == NULL)
    die("Memory exhausted.  Cannot allocate %d bytes.", (int)size);

  return(temp_ptr);
}

void *mm_calloc
  (size_t nelem,
   size_t size)
{
  void * temp_ptr;

  /* Make sure we allocate something. */
  if (size == 0) {
    size = 1;
  }
  if (nelem == 0) {
    nelem = 1;
  }

  temp_ptr = calloc(nelem, size);

  if (temp_ptr == NULL)
    die("Memory exhausted.  Cannot allocate %d bytes.", (int)size);

  return(temp_ptr);
}

void * mm_realloc
  (void * ptr,
   size_t  size)
{
  void * temp_ptr;

  /* Make sure we allocate something. */
  if (size == 0)
    size = 1;
  assert(size > 0);

  /* Some non-ANSI systems complain about reallocating NULL pointers. */
  if (ptr == NULL) {
    temp_ptr = malloc(size);
  } else {
    temp_ptr = realloc(ptr, size);
  }

  if (temp_ptr == NULL)
    die("Memory exhausted.  Cannot allocate %d bytes.", (int)size);

  return(temp_ptr);
}

/**************************************************************************
 * See .h file for description.
 **************************************************************************/
bool almost_equal
  (double value1,
   double value2,
   double slop)
{
  if ((value1 - slop > value2) || (value1 + slop < value2)) {
    return(false);
  } else {
    return(true);
  }
}

/*************************************************************************
 * Writes a unicode codepoint in UTF-8 encoding to the start of the buffer
 * and return it, optionally record the length of the written code unit.
 * The buffer must be at least 6 bytes long to hold any valid codepoint
 * though it will use the minimum possible. The output is NOT null terminated.
 *************************************************************************/
char* unicode_to_string(uint32_t code, char *buffer, int *code_unit_length) {
  int bytes, i;
  if (code <= 0x7F) { // 1 byte, max 7 bits
    buffer[0] = code;
    if (code_unit_length != NULL) *code_unit_length = 1;
    return buffer;
  } else if (code <= 0x7FF) { // 2 bytes, max 11 bits
    bytes = 2;
  } else if (code <= 0xFFFF) { // 3 bytes, max 16 bits
    bytes = 3;
  } else if (code <= 0x1FFFFF) { // 4 bytes, max 21 bits
    bytes = 4;
  } else if (code <= 0x3FFFFFF) { // 5 bytes, max 26 bits
    bytes = 5;
  } else if (code <= 0x7FFFFFFF) { // 6 bytes, max 31 bits
    bytes = 6;
  } else {
    die("a unicode codepoint can be at maximum 31 bits.");
    return NULL;
  }
  for (i = bytes-1; i > 0; i--) {
    buffer[i] = 0x80 | (code & 0x3F);
    code = code >> 6;
  }
  buffer[0] = ((0xFF << (8 - bytes)) & 0xFF) | code;
  if (code_unit_length != NULL) *code_unit_length = bytes;
  return buffer;
}

/*************************************************************************
 * Returns the Unicode codepoint at the start of the string assuming UTF-8.
 * This function handles NUL bytes!
 *
 * If something is wrong it will return one of these error codes:
 * -1   If the string begins with a byte 10xxxxxx indicating a middle byte,
 * -2   If the codepoint would go past the end of the string,
 * -3   If the start byte is the illegal value 0xFE, or 0xFF
 * -4   If there are too few middle bytes following the start byte,
 * -5   If the codepoint uses more bytes than needed.
 *************************************************************************/
int32_t unicode_from_string(const char *str, size_t len, int *code_unit_length) {
  int bytes, bytes_after, i;
  int32_t codepoint, min;
  if (code_unit_length != NULL) *code_unit_length = 1;
  if ((str[0] & 0x80) == 0x00) {	// 0xxx xxxx  == ASCII == 7 bits
    codepoint = str[0];
    return codepoint;
  } else if ((str[0] & 0xC0) == 0x80) {	// 10xx xxxx = middle byte (not allowed here!)
    return -1;
  } else if ((str[0] & 0xE0) == 0xC0) { // 110x xxxx == 2 byte == 11 bits
    bytes = 2;
    codepoint = (str[0] & 0x1F) << 6;
  } else if ((str[0] & 0xF0) == 0xE0) {	// 1110 xxxx == 3 bytes == 16 bits
    bytes = 3;
    codepoint = (str[0] & 0x0F) << 12;
  } else if ((str[0] & 0xF8) == 0xF0) { // 1111 0xxx == 4 bytes == 21 bits
    bytes = 4;
    codepoint = (str[0] & 0x07) << 18;
  } else if ((str[0] & 0xFC) == 0xF8) {	// 1111 10xx == 5 bytes == 26 bits
    bytes = 5;
    codepoint = (str[0] & 0x03) << 24;
  } else if ((str[0] & 0xFE) == 0xFC) {	// 1111 110x == 6 bytes == 31 bits
    bytes = 6;
    codepoint = (str[0] & 0x01) << 30;
  } else if ((str[0] & 0xFF) == 0xFE || (str[0] & 0xFF) == 0xFF) {
    return -3;
  } else {
    die("Impossible state!");
    return -6; 
  }
  if (code_unit_length != NULL) *code_unit_length = bytes;
  if (bytes > len) return -2;
  for (i = 1, bytes_after = bytes - 2; bytes_after >= 0; i++, bytes_after--) {
    if ((str[i] & 0xC0) != 0x80) return -4;
    codepoint |= ((str[i] & 0x3F) << (6 * bytes_after));
  }
  if (bytes > 2) {
    min = 1 << ((6 * (bytes - 2)) + (8 - bytes));
  } else {
    min = 0x80;
  }
  if (codepoint < min) return -5;
  return codepoint;
}

/*************************************************************************
 * MEME and DREME motifs can have very small E-values which are impossible
 * to represent using a double. By converting to log values we lose
 * precision but the range possible becomes much greater.
 *************************************************************************/
double log10_evalue_from_string(const char *str) {
  const char * EVALUE_RE = "^[+]?([0-9]*\\.?[0-9]+)([eE]([-+]?[0-9]+))?$";
  const char * INF_RE = "^[+]?inf(inity)?$";
  regex_t re_evalue, re_inf;
  regmatch_t matches[4];
  char *buffer;
  int len_m, len_e, i, j, myerrno;
  double m, e, log_ev;

  myerrno = 0;
  regcomp(&re_evalue, EVALUE_RE, REG_EXTENDED);
  regcomp(&re_inf, INF_RE, REG_EXTENDED | REG_ICASE);
  if (regexec(&re_evalue, str, 4, matches, 0) == 0) {
    len_m = matches[1].rm_eo - matches[1].rm_so;
    len_e = matches[3].rm_eo - matches[3].rm_so;
    buffer = mm_malloc(sizeof(char) * (MAX(len_m, len_e) + 1));
    for (i = 0, j = matches[1].rm_so; i < len_m; ++i, ++j) buffer[i] = str[j];
    buffer[i] = '\0';
    errno = 0; m = strtod(buffer, NULL); if (errno) myerrno = errno;
    e = 0;
    if (len_e) {
      for (i = 0, j = matches[3].rm_so; i < len_e; ++i, ++j) buffer[i] = str[j];
      buffer[i] = '\0';
      errno = 0; e = strtod(buffer, NULL); if (errno) myerrno = errno;
    }
    free(buffer);
    log_ev = log10(m) + e;
  } else if (regexec(&re_inf, str, 0, matches, 0) == 0) {
    log_ev = HUGE_VAL;
  } else {
    log_ev = 0; // seems safest
    myerrno = EINVAL;
  }
  regfree(&re_evalue);
  regfree(&re_inf);
  errno = myerrno;
  return log_ev;
}

/****************************************************************************
 * Copy a string, with allocation.
 ****************************************************************************/
void copy_string
 (char** target,
  const char*  source)
{
  if (source == NULL) {
    *target = NULL;
  } else {
    *target = (char *)mm_calloc(strlen(source) + 1, sizeof(char));
    strcpy(*target, source);
  }
}

/*
 * Local Variables:
 * mode: c
 * c-basic-offset: 2
 * End:
 */
