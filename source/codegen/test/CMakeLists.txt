cmake_minimum_required(VERSION 3.16)

project("codegen_test")

add_subdirectory("${FERRITE}/app/cmake/config" "config")
add_subdirectory(".." "codegen")

set(SRC
    "../src/codegen_test.cpp"
)

include(${CMAKE_BINARY_DIR}/conanbuildinfo.cmake)
conan_basic_setup(NO_OUTPUT_DIRS)

enable_testing()
add_executable(${PROJECT_NAME} ${SRC})
target_link_libraries(${PROJECT_NAME} PRIVATE "core" "codegen" ${CONAN_LIBS})
add_test(${PROJECT_NAME} ${PROJECT_NAME})
