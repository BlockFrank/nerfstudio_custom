cmake_minimum_required(VERSION 3.22.1)
project(fast_traversal LANGUAGES CXX CUDA)

if(WIN32)
    add_compile_options("$<$<COMPILE_LANGUAGE:CXX>:/bigobj>")
    string(REPLACE "-fPIC" "" CMAKE_C_FLAGS "${CMAKE_C_FLAGS}")
    string(REPLACE "-fPIC" "" CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")
    string(REPLACE "-fPIC" "" CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS}")
endif()

enable_language(CUDA)

include(FetchContent)

set(CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake" ${CMAKE_MODULE_PATH})
set(CMAKE_BUILD_TYPE "Release")

find_library(libcnpy cnpy ${CONDA_PREFIX}/lib)
include_directories(${CONDA_PREFIX}/include)

find_package(Torch REQUIRED)
find_package(CGAL REQUIRED)

FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.9.2
)
FetchContent_MakeAvailable(pybind11)

if(WIN32 AND TARGET pybind11::windows_extras)
    set_property(TARGET pybind11::windows_extras PROPERTY INTERFACE_COMPILE_OPTIONS "")
endif()

if(WIN32)
    add_compile_options("$<$<COMPILE_LANGUAGE:CXX>:/bigobj>")
endif()

if(NOT WIN32)
    add_link_options(-flto=auto)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(BUILD_DIRECTORY "${CMAKE_BINARY_DIR}/build")
set(CUDA_GENERATED_OUTPUT_DIR "${BUILD_DIRECTORY}")

# --------------------------------------------------------------------------
# Canonical incoming cache/env values from setup.py / bootstrap
# --------------------------------------------------------------------------
if(NOT OPTIX_ROOT_DIR AND DEFINED ENV{OPTIX_ROOT_DIR})
    set(OPTIX_ROOT_DIR "$ENV{OPTIX_ROOT_DIR}" CACHE PATH "OptiX root directory" FORCE)
endif()

if(NOT OPTIX_INSTALL_DIR AND DEFINED ENV{OPTIX_INSTALL_DIR})
    set(OPTIX_INSTALL_DIR "$ENV{OPTIX_INSTALL_DIR}" CACHE PATH "OptiX install directory" FORCE)
endif()

if(NOT OPTIX_INCLUDE_DIR AND DEFINED ENV{OPTIX_INCLUDE_DIR})
    set(OPTIX_INCLUDE_DIR "$ENV{OPTIX_INCLUDE_DIR}" CACHE PATH "OptiX include directory" FORCE)
endif()

if(NOT OPTIX_ROOT_DIR AND NOT OPTIX_INSTALL_DIR AND DEFINED ENV{OPTIX_PATH})
    set(OPTIX_INSTALL_DIR "$ENV{OPTIX_PATH}" CACHE PATH "OptiX install directory" FORCE)
endif()

find_package(OptiX REQUIRED)
find_package(CUDA REQUIRED)

set(CUDA_SEPARABLE_COMPILATION ON)

include_directories(
    "${OptiX_INCLUDE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/cuda"
    ${CUDA_INCLUDE_DIRS}
)

find_program(BIN2C bin2c DOC "Path to the cuda-sdk bin2c executable.")

macro(cuda_compile_and_embed output_var generated_files_name)
    set(c_var_name ${output_var})
    set(generated_files "${${generated_files_name}}")
    list(GET ${generated_files_name} 0 ptx_file)
    get_filename_component(embedded_file ${ptx_file}_embedded.cpp NAME)
    set(embedded_file "${BUILD_DIRECTORY}/${embedded_file}")
    add_custom_command(
        OUTPUT ${embedded_file}
        COMMAND ${BIN2C} --padd 0 --type char --name ${c_var_name} ${ptx_file} > ${embedded_file}
        DEPENDS ${generated_files}
        COMMENT "compiling (and embedding ptx)")
    set(${output_var} ${embedded_file})
    list(APPEND ${generated_files_name} ${embedded_file})
endmacro()

CUDA_WRAP_SRCS(traversal PTX generated_files_trace_rays
    src/optix_types.h
    src/optix/optix_trace_rays.cu
    src/utils/preprocessor.h
    src/utils/vec_math.h
    OPTIONS -rdc true
)
cuda_compile_and_embed(ptx_code_file generated_files_trace_rays)

CUDA_WRAP_SRCS(traversal PTX generated_files_find_tetrahedra
    src/optix_types.h
    src/optix/optix_find_tetrahedra.cu
    src/utils/preprocessor.h
    src/utils/vec_math.h
    OPTIONS -rdc true
)
cuda_compile_and_embed(ptx_code_file_find_tetrahedra generated_files_find_tetrahedra)

CUDA_WRAP_SRCS(traversal PTX generated_files_trace_rays_triangles
    src/optix_types.h
    src/optix/optix_trace_rays_triangles.cu
    src/utils/preprocessor.h
    src/utils/vec_math.h
    OPTIONS -rdc true
)
cuda_compile_and_embed(ptx_code_file_triangles generated_files_trace_rays_triangles)

set(generated_files
    ${generated_files_trace_rays}
    ${generated_files_find_tetrahedra}
    ${generated_files_trace_rays_triangles}
)

if(NOT WIN32)
    add_link_options(-flto=auto)
endif()

pybind11_add_module(
    tetranerf_cpp_extension
    src/tetrahedra_tracer.cu
    src/tetrahedra_tracer.cpp
    src/triangulation.cpp
    src/py_binding.cpp
    ${generated_files}
)

target_link_libraries(tetranerf_cpp_extension PRIVATE ${CUDA_LIBRARIES} ${TORCH_LIBRARIES})
target_link_libraries(tetranerf_cpp_extension PRIVATE CGAL::CGAL)
target_compile_features(tetranerf_cpp_extension PRIVATE cxx_std_17)

set_target_properties(
    tetranerf_cpp_extension
    PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/tetranerf/utils/extension"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)