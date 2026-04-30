cmake_minimum_required(VERSION 3.10)
project(index_c C)

# Set C standard
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Find OpenMP
find_package(OpenMP)

# Add compiler flags
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wall -O3")

# Add debug flags for debug builds
set(CMAKE_C_FLAGS_DEBUG "${CMAKE_C_FLAGS_DEBUG} -g -DDEBUG")

# Include directories
include_directories(${PROJECT_SOURCE_DIR}/src)

# Source files
set(SOURCES
    src/main.c
    src/FileRead.c
    src/FimoFile.c
    src/HashTable.c
    src/MemCheck.c
    src/MotifHit.c
    src/MotifHitVector.c
    src/Node.c
    src/PromoterLength.c
    src/ScoreLabelPairVector.c
    src/utils.c
)

# Header files (optional, for IDE support)
set(HEADERS
    src/FileRead.h
    src/FimoFile.h
    src/HashTable.h
    src/MemCheck.h
    src/MotifHit.h
    src/MotifHitVector.h
    src/Node.h
    src/PromoterLength.h
    src/ScoreLabelPairVector.h
    src/utils.h
)

# Create executable
add_executable(index_c ${SOURCES} ${HEADERS})

# Link math library
target_link_libraries(index_c m)

# Link OpenMP if available
if(OpenMP_C_FOUND)
    target_link_libraries(index_c OpenMP::OpenMP_C)
endif()

# Install target
install(TARGETS index_c DESTINATION bin)

# Print configuration
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C Compiler: ${CMAKE_C_COMPILER}")
message(STATUS "C Flags: ${CMAKE_C_FLAGS}")