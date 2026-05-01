cmake_minimum_required(VERSION 3.10)
project(pmetParallel)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Enable aggressive optimization in release builds
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3")

# Implementation files (everything except main()). Compiled once into
# an OBJECT library so the production binary and the test binary share
# exactly the same code — tests can never drift from what ships.
set(PAIR_LIB_SOURCES
    src/motif.cpp
    src/motifComparison.cpp
    src/Output.cpp
    src/utils.cpp
)

set(PAIR_LIB_HEADERS
    src/motif.hpp
    src/motifComparison.hpp
    src/Output.hpp
    src/utils.hpp
)

add_library(pair_lib OBJECT ${PAIR_LIB_SOURCES} ${PAIR_LIB_HEADERS})

# Production binary
add_executable(pair_parallel src/main.cpp $<TARGET_OBJECTS:pair_lib>)

# Find and link threading lib (pthread)
find_package(Threads REQUIRED)
target_link_libraries(pair_parallel Threads::Threads)

# Unit tests — opt-in via -DPMET_BUILD_TESTS=ON. Default off so the
# normal `make build` stays lean. The Makefile target `make
# test-pairing` configures with the flag enabled, builds, and runs.
# Tiny custom runner in tests/test_runner.hpp; one TEST_CASE per
# pure-math kernel that has earned a regression test.
option(PMET_BUILD_TESTS "Build pairing unit tests" OFF)
if(PMET_BUILD_TESTS)
  add_executable(pair_tests
      tests/test_main.cpp
      tests/test_bh_correction.cpp
      tests/test_fair_division.cpp
      tests/test_binomial_poisson.cpp
      tests/test_motif_instances_overlap.cpp
      tests/test_minhash_sketch.cpp
      $<TARGET_OBJECTS:pair_lib>
  )
  target_link_libraries(pair_tests Threads::Threads)
endif()
