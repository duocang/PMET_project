cmake_minimum_required(VERSION 3.10)
project(pmetParallel)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Enable aggressive optimization in release builds
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3")

# 源文件
set(SOURCES
    src/main.cpp
    src/motif.cpp
    src/motifComparison.cpp
    src/Output.cpp
    src/utils.cpp
)

# 头文件
set(HEADERS
    src/motif.hpp
    src/motifComparison.hpp
    src/Output.hpp
    src/utils.hpp
)

# 创建可执行文件
add_executable(pair_parallel ${SOURCES} ${HEADERS})

# 查找并链接线程库 (pthread)
find_package(Threads REQUIRED)
target_link_libraries(pair_parallel Threads::Threads)