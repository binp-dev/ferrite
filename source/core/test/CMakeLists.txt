cmake_minimum_required(VERSION 3.16)

project("core_test")

add_subdirectory("../../app/cmake/config" "config")
add_subdirectory(".." "core")

set(SRC
    "src/collections/vec.cpp"
    "src/collections/vec_deque.cpp"
    "src/convert.cpp"
    "src/numeric.cpp"
    "src/format.cpp"
    "src/main.cpp"
)

include(${CMAKE_BINARY_DIR}/conanbuildinfo.cmake)
conan_basic_setup(NO_OUTPUT_DIRS)

enable_testing()
add_executable(${PROJECT_NAME} ${SRC})
target_link_libraries(${PROJECT_NAME} PRIVATE "core" ${CONAN_LIBS})
add_test(${PROJECT_NAME} ${PROJECT_NAME})
