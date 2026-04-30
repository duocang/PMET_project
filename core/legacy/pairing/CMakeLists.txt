# cmake_minimum_required(VERSION 3.12)
project(pair_original)

# Set compilation parameters
set(CMAKE_CXX_STANDARD 11)

add_executable(${PROJECT_NAME}
  src/main.cpp
  src/Output.cpp
  src/motif.cpp
  src/motifComparison.cpp
  src/utils.cpp
)

# Add performance testing tools
# target_link_libraries(${PROJECT_NAME} profiler unwind)
# target_link_libraries(${PROJECT_NAME} )
