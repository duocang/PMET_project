// Unit tests for pmet-index-utils.c — small string helpers used
// throughout the indexing pipeline (path manipulation, separator
// concatenation). Cheap to test, easy to break in a refactor, and
// untouched by integration baselines (their bugs would manifest as
// "wrong output filename" rather than data drift).

#include "test_runner.hpp"

#include <cstring>
#include <string>

extern "C" {
#include "pmet-index-utils.h"
}

// Helper: own a heap C-string returned by paste2/paste/etc., free
// at scope exit. Tests stay leak-clean for any future enabling of
// the MemCheck leak tracker.
struct OwnedCStr {
  char* p;
  ~OwnedCStr() { if (p) free(p); }  // dbg_free is just free under the hood (leak tracking is currently disabled)
  OwnedCStr(char* x) : p(x) {}
  OwnedCStr(const OwnedCStr&) = delete;
  OwnedCStr& operator=(const OwnedCStr&) = delete;
};

// ------------------------------------------------------------------
// paste2
// ------------------------------------------------------------------

TEST_CASE("paste2: typical separator") {
  OwnedCStr r{paste2("/", "foo", "bar")};
  REQUIRE(std::strcmp(r.p, "foo/bar") == 0);
}

TEST_CASE("paste2: NULL separator treated as empty") {
  OwnedCStr r{paste2(nullptr, "foo", "bar")};
  REQUIRE(std::strcmp(r.p, "foobar") == 0);
}

TEST_CASE("paste2: NULL inputs propagate as NULL") {
  REQUIRE(paste2("/", nullptr, "bar") == nullptr);
  REQUIRE(paste2("/", "foo", nullptr) == nullptr);
}

TEST_CASE("paste2: empty strings preserve separator") {
  OwnedCStr r{paste2("__", "", "")};
  REQUIRE(std::strcmp(r.p, "__") == 0);
}

// ------------------------------------------------------------------
// paste (variadic)
// ------------------------------------------------------------------

TEST_CASE("paste: 3 strings with separator") {
  OwnedCStr r{paste(3, ".", "a", "bb", "ccc")};
  REQUIRE(std::strcmp(r.p, "a.bb.ccc") == 0);
}

TEST_CASE("paste: NULL separator collapses to empty (no separators inserted)") {
  OwnedCStr r{paste(3, nullptr, "x", "y", "z")};
  REQUIRE(std::strcmp(r.p, "xyz") == 0);
}

TEST_CASE("paste: single string ignores separator") {
  OwnedCStr r{paste(1, "/", "lonely")};
  REQUIRE(std::strcmp(r.p, "lonely") == 0);
}

TEST_CASE("paste: 5-way concatenation length matches sum + separators") {
  OwnedCStr r{paste(5, "_", "a", "b", "c", "d", "e")};
  REQUIRE(std::strcmp(r.p, "a_b_c_d_e") == 0);
  REQUIRE(std::strlen(r.p) == 9);  // 5 chars + 4 separators
}

// ------------------------------------------------------------------
// getFilenameNoExt
// ------------------------------------------------------------------

TEST_CASE("getFilenameNoExt: strips extension and directory") {
  OwnedCStr r{getFilenameNoExt("/some/path/to/foo.txt")};
  REQUIRE(std::strcmp(r.p, "foo") == 0);
}

TEST_CASE("getFilenameNoExt: handles bare filename without directory") {
  OwnedCStr r{getFilenameNoExt("bare.fasta")};
  REQUIRE(std::strcmp(r.p, "bare") == 0);
}

TEST_CASE("getFilenameNoExt: no extension keeps the whole name") {
  OwnedCStr r{getFilenameNoExt("/path/to/Makefile")};
  REQUIRE(std::strcmp(r.p, "Makefile") == 0);
}

TEST_CASE("getFilenameNoExt: multi-dot keeps everything before the LAST dot") {
  // "foo.bar.baz" → "foo.bar". This is the standard Unix convention.
  OwnedCStr r{getFilenameNoExt("/x/foo.bar.baz")};
  REQUIRE(std::strcmp(r.p, "foo.bar") == 0);
}

TEST_CASE("getFilenameNoExt: empty path returns empty string") {
  OwnedCStr r{getFilenameNoExt("")};
  REQUIRE(std::strcmp(r.p, "") == 0);
}

// ------------------------------------------------------------------
// removeTrailingSlash (in-place)
// ------------------------------------------------------------------

TEST_CASE("removeTrailingSlash: trims a single trailing slash in place") {
  char buf[] = "data/";
  removeTrailingSlash(buf);
  REQUIRE(std::strcmp(buf, "data") == 0);
}

TEST_CASE("removeTrailingSlash: leaves a path with no trailing slash unchanged") {
  char buf[] = "data";
  removeTrailingSlash(buf);
  REQUIRE(std::strcmp(buf, "data") == 0);
}

TEST_CASE("removeTrailingSlash: empty / NULL is a no-op") {
  char empty[] = "";
  removeTrailingSlash(empty);
  REQUIRE(empty[0] == '\0');
  // NULL must not crash — function returns early.
  removeTrailingSlash(nullptr);
}

TEST_CASE("removeTrailingSlash: only the LAST slash is removed (not multiple)") {
  // Documented behavior: only one trailing slash trimmed per call.
  // "data//" → "data/" (one slash remaining).
  char buf[] = "data//";
  removeTrailingSlash(buf);
  REQUIRE(std::strcmp(buf, "data/") == 0);
}

// ------------------------------------------------------------------
// removeTrailingSlashAndReturn (returns a fresh heap string)
// ------------------------------------------------------------------

TEST_CASE("removeTrailingSlashAndReturn: returns a heap copy with slash trimmed") {
  OwnedCStr r{removeTrailingSlashAndReturn("data/")};
  REQUIRE(std::strcmp(r.p, "data") == 0);
}

TEST_CASE("removeTrailingSlashAndReturn: NULL input returns NULL") {
  REQUIRE(removeTrailingSlashAndReturn(nullptr) == nullptr);
}

TEST_CASE("removeTrailingSlashAndReturn: empty input returns empty string (heap)") {
  OwnedCStr r{removeTrailingSlashAndReturn("")};
  REQUIRE(r.p != nullptr);
  REQUIRE(r.p[0] == '\0');
}
