cmake_minimum_required(VERSION 3.3.0)

project(dgmlrt)

set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_EXPORT_COMPILE_COMMANDS on)

include(${CMAKE_CURRENT_LIST_DIR}/cmake/wall.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/no-rtti.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/no-exceptions.cmake)

if(DGMLRT_ENABLE_ASAN)
  include(${CMAKE_CURRENT_LIST_DIR}/cmake/asan.cmake)
endif()

add_library(dgmlrt dgmlrt.cpp)
target_include_directories(dgmlrt PUBLIC include/)
dgmlrt_set_wall(dgmlrt)
dgmlrt_set_no_exceptions(dgmlrt)
dgmlrt_set_no_rtti(dgmlrt)

# This will only be true if this project is not used as a subdirectory (e.g. FetchContent)
if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_SOURCE_DIR)
  option(DGMLRT_BUILD_EXAMPLES "Build Examples" ON)
  if(DGMLRT_BUILD_EXAMPLES)
    add_executable(dgmlb-test dgmlb-test.cpp)
    dgmlrt_set_wall(dgmlb-test)
    dgmlrt_set_no_exceptions(dgmlb-test)
    dgmlrt_set_no_rtti(dgmlb-test)

    add_executable(dgmlrt-example example.cpp)
    target_link_libraries(dgmlrt-example PRIVATE dgmlrt)
    dgmlrt_set_wall(dgmlrt-example)
    dgmlrt_set_no_exceptions(dgmlrt-example)
    dgmlrt_set_no_rtti(dgmlrt-example)
  endif()
endif()