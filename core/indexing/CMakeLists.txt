cmake_minimum_required(VERSION 3.10)
project(indexing_fimo_fused C)

if(POLICY CMP0074)
  cmake_policy(SET CMP0074 NEW)
endif()

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(PMET_FUSED_OPENMP_TARGET "")
set(PMET_OPENMP_ROOT "")
find_package(OpenMP QUIET)

if(NOT OpenMP_C_FOUND AND APPLE AND CMAKE_C_COMPILER_ID MATCHES "Clang")
  if(NOT "$ENV{OpenMP_ROOT}" STREQUAL "")
    set(PMET_OPENMP_ROOT "$ENV{OpenMP_ROOT}")
  elseif(EXISTS "/opt/homebrew/opt/libomp")
    set(PMET_OPENMP_ROOT "/opt/homebrew/opt/libomp")
  elseif(EXISTS "/usr/local/opt/libomp")
    set(PMET_OPENMP_ROOT "/usr/local/opt/libomp")
  endif()

  if(NOT PMET_OPENMP_ROOT STREQUAL "")
    set(OpenMP_ROOT "${PMET_OPENMP_ROOT}" CACHE PATH "OpenMP root path" FORCE)
    set(OpenMP_C_FLAGS "-Xpreprocessor -fopenmp -I${PMET_OPENMP_ROOT}/include" CACHE STRING "OpenMP C flags" FORCE)
    set(OpenMP_C_LIB_NAMES "omp" CACHE STRING "OpenMP C libraries" FORCE)
    set(OpenMP_omp_LIBRARY "${PMET_OPENMP_ROOT}/lib/libomp.dylib" CACHE FILEPATH "OpenMP omp library" FORCE)

    find_package(OpenMP QUIET)
  endif()

  if(OpenMP_C_FOUND)
    message(STATUS "OpenMP configured for AppleClang from ${PMET_OPENMP_ROOT}")
  else()
    message(STATUS
      "OpenMP not found: indexing_fimo_fused will run in single-thread fallback. "
      "On macOS, install libomp and optionally export OpenMP_ROOT, then reconfigure. "
      "Example OpenMP_ROOT values: /opt/homebrew/opt/libomp (Apple Silicon) or /usr/local/opt/libomp (Intel)."
    )
  endif()
endif()

if(OpenMP_C_FOUND)
  set(PMET_FUSED_OPENMP_TARGET OpenMP::OpenMP_C)
endif()

# 编译选项
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
# fimo 源码来自第三方，抑制不影响正确性的警告
add_compile_options(-Wall -Wextra -O2
  -Wno-unused-variable
  -Wno-unused-but-set-variable
  -Wno-unused-parameter
  -Wno-unused-function
  -Wno-sign-compare
)

#############################################
# 收集源文件
#############################################

# 显式列出源文件，避免把未使用的第三方模块通过 GLOB 自动带入构建。
# 已确认可移除：
#   fasta-io.c、html-data.c、mhmm-state.c、mp.c
#   fimo-output.c、motif-in-meme-xml.c、meme-sax.c
#   cisml-sax.c、hash_table.c、heap.c
#   prior-dist.c、prior-reader-from-psp.c、prior-reader-from-wig.c、qvalue.c、reservoir.c
#   sax-parser-utils.c、wiggle-reader.c、xml-out.c、xml-util.c
#   fasta-get-markov.c、xlate-in.c
#   binary-search.c、io.c、mtwist.c、ushuffle.c（所有导出函数均为死代码）
set(FIMO_SOURCES
  "${CMAKE_SOURCE_DIR}/src/fimo/alph-in.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/alphabet.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/array-list.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/array.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/cisml.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/data-block-reader.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/data-block.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/fimo.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/linked-list.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/matrix.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/motif-in-common.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/motif-in-meme-text.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/motif-in.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/motif.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/parser-message.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/pmet-sequence-library.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/pssm.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/red-black-tree.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/regex-utils.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/scanned-sequence.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/seq-reader-from-fasta.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/seq.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/simple-getopt.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/string-builder.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/string-list.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/string-match.c"
  "${CMAKE_SOURCE_DIR}/src/fimo/utils.c"
)

set(PMET_INDEX_SOURCES
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-fimo-binary.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-FileRead.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-MemCheck.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-MotifHit.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-MotifHitVector.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-pair-test.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-PromoterLength.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-ScoreLabelPairVector.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-SiteStore.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-utils.c"
)

#############################################
# 创建可执行文件
#############################################
add_executable(${PROJECT_NAME}
  ${FIMO_SOURCES}
  ${PMET_INDEX_SOURCES}
)

#############################################
# 设置头文件搜索路径
#############################################
target_include_directories(${PROJECT_NAME} PRIVATE
  ${CMAKE_SOURCE_DIR}/src
  ${CMAKE_SOURCE_DIR}/src/fimo
  ${CMAKE_SOURCE_DIR}/src/pmet_index
)

#############################################
# 链接库
#############################################
# 需要链接数学库 m（用于 exp, log 等函数）
target_link_libraries(${PROJECT_NAME} PRIVATE
  m
)

if(NOT PMET_FUSED_OPENMP_TARGET STREQUAL "")
  target_link_libraries(${PROJECT_NAME} PRIVATE ${PMET_FUSED_OPENMP_TARGET})
endif()

#############################################
# Unit tests (opt-in via -DPMET_BUILD_TESTS=ON)
#############################################
# Mirrors the pairing-side setup, with one twist: tests link against
# a *subset* of PMET_INDEX_SOURCES — just the pure-math + utility
# pieces that don't reach into FIMO. SiteStore / FileRead / fimo-binary
# pull in the upstream FIMO API, which would force the test target
# to link the entire FIMO blob; we don't test those (they're glue +
# I/O), so cut them out instead.
set(PMET_INDEX_TEST_SOURCES
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-MemCheck.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-MotifHit.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-MotifHitVector.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-pair-test.c"
  "${CMAKE_SOURCE_DIR}/src/pmet_index/pmet-index-utils.c"
)

option(PMET_BUILD_TESTS "Build indexing unit tests" OFF)
if(PMET_BUILD_TESTS)
  enable_language(CXX)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  add_executable(test_indexing
    tests/test_main.cpp
    tests/test_pair_test.cpp
    tests/test_utils.cpp
    ${PMET_INDEX_TEST_SOURCES}
  )
  target_include_directories(test_indexing PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_SOURCE_DIR}/src/pmet_index
  )
  target_link_libraries(test_indexing PRIVATE m)
endif()

#############################################
# 安装规则
#############################################
install(TARGETS ${PROJECT_NAME} RUNTIME DESTINATION bin)
