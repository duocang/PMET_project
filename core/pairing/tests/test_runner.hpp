// Minimal C++ test runner — one TEST_CASE macro plus a REQUIRE
// assertion. Picked over vendoring doctest (~80 KB single header) for
// the bootstrap: this fits in 50 lines, has no extra build flags, and
// covers what the math kernels actually need (assert + label). If the
// test surface grows past "math correctness for a handful of pure
// functions" we can swap in doctest with a one-line include change.

#ifndef PMET_TEST_RUNNER_HPP
#define PMET_TEST_RUNNER_HPP

#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace pmet_test {

struct TestCase {
  std::string name;
  void (*fn)();
};

inline std::vector<TestCase>& registry() {
  static std::vector<TestCase> v;
  return v;
}

inline int registerCase(const char* name, void (*fn)()) {
  registry().push_back({name, fn});
  return 0;
}

}  // namespace pmet_test

#define PMET_CONCAT_INNER(a, b) a##b
#define PMET_CONCAT(a, b) PMET_CONCAT_INNER(a, b)

// Each TEST_CASE registers a free function at static-init time so main()
// finds it without manual list maintenance.
#define TEST_CASE(name)                                                                   \
  static void PMET_CONCAT(pmet_test_fn_, __LINE__)();                                     \
  static int PMET_CONCAT(pmet_test_reg_, __LINE__) =                                      \
      pmet_test::registerCase(name, PMET_CONCAT(pmet_test_fn_, __LINE__));                \
  static void PMET_CONCAT(pmet_test_fn_, __LINE__)()

#define REQUIRE(cond)                                                                     \
  do {                                                                                    \
    if (!(cond)) {                                                                        \
      throw std::runtime_error(std::string(#cond) + " at " __FILE__ ":" +                 \
                               std::to_string(__LINE__));                                 \
    }                                                                                     \
  } while (0)

// Floating-point compare with absolute tolerance — same semantics as
// doctest's `Approx`. Default 1e-9 is tight enough for our p-value math.
#define REQUIRE_NEAR(actual, expected, tol)                                               \
  do {                                                                                    \
    double a__ = (actual);                                                                \
    double e__ = (expected);                                                              \
    double t__ = (tol);                                                                   \
    if (!((a__ >= e__ - t__) && (a__ <= e__ + t__))) {                                    \
      throw std::runtime_error(std::string("|") + #actual + " - " + #expected +           \
                               "| > " + std::to_string(t__) + " (got " +                  \
                               std::to_string(a__) + ", expected " +                      \
                               std::to_string(e__) + ") at " __FILE__ ":" +               \
                               std::to_string(__LINE__));                                 \
    }                                                                                     \
  } while (0)

inline int pmet_test_main() {
  int passed = 0, failed = 0;
  for (const auto& t : pmet_test::registry()) {
    try {
      t.fn();
      std::cout << "  ok   " << t.name << "\n";
      ++passed;
    } catch (const std::exception& e) {
      std::cerr << "  FAIL " << t.name << ": " << e.what() << "\n";
      ++failed;
    } catch (...) {
      std::cerr << "  FAIL " << t.name << ": unknown exception\n";
      ++failed;
    }
  }
  std::cout << "\n[pair_tests] " << passed << " passed, " << failed << " failed\n";
  return failed ? 1 : 0;
}

#endif  // PMET_TEST_RUNNER_HPP
