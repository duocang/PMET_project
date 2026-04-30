cmake_minimum_required(VERSION 3.12)
project(index_cpp)

# 设置编译参数
# add_compile_options(-std=c++11)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")

# 收集src目录下的所有源文件
aux_source_directory(src SRC_FILES)

# 添加可执行文件
add_executable(index_cpp ${SRC_FILES})

# target_link_libraries(${PROJECT_NAME} profiler unwind)
target_link_libraries(${PROJECT_NAME})
