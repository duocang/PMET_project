// Single test entry point. Each TEST_CASE in test_*.cpp registers
// itself at static-init time; main here just runs the registry.

#include "test_runner.hpp"

int main() {
  return pmet_test_main();
}
