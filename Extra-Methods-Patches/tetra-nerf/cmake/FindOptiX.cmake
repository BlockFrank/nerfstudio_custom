# - Find OptiX
#
# This module defines:
#   OptiX_FOUND
#   OptiX_INCLUDE
#   OPTIX_INCLUDE_DIR
#   OPTIX_ROOT_DIR
#   OPTIX_INSTALL_DIR
#
# Accepted inputs, in priority order:
#   -DOPTIX_INCLUDE_DIR=...
#   -DOPTIX_INSTALL_DIR=...
#   -DOPTIX_ROOT_DIR=...
#   ENV{OPTIX_INCLUDE_DIR}
#   ENV{OPTIX_INSTALL_DIR}
#   ENV{OPTIX_ROOT_DIR}
#   ENV{OPTIX_PATH}
#
# The output variable used by this project is:
#   OptiX_INCLUDE

include(FindPackageHandleStandardArgs)

function(OptiX_report_error msg)
    message(FATAL_ERROR "${msg}")
endfunction()

# Normalize incoming cache/env values
if(NOT OPTIX_INCLUDE_DIR AND DEFINED ENV{OPTIX_INCLUDE_DIR})
    set(OPTIX_INCLUDE_DIR "$ENV{OPTIX_INCLUDE_DIR}" CACHE PATH "OptiX include directory" FORCE)
endif()

if(NOT OPTIX_INSTALL_DIR AND DEFINED ENV{OPTIX_INSTALL_DIR})
    set(OPTIX_INSTALL_DIR "$ENV{OPTIX_INSTALL_DIR}" CACHE PATH "OptiX install directory" FORCE)
endif()

if(NOT OPTIX_ROOT_DIR AND DEFINED ENV{OPTIX_ROOT_DIR})
    set(OPTIX_ROOT_DIR "$ENV{OPTIX_ROOT_DIR}" CACHE PATH "OptiX root directory" FORCE)
endif()

if(NOT OPTIX_INSTALL_DIR AND DEFINED ENV{OPTIX_PATH})
    set(OPTIX_INSTALL_DIR "$ENV{OPTIX_PATH}" CACHE PATH "OptiX install directory" FORCE)
endif()

# Candidate roots
set(_optix_roots "")
if(OPTIX_INCLUDE_DIR)
    list(APPEND _optix_roots "${OPTIX_INCLUDE_DIR}")
endif()
if(OPTIX_INSTALL_DIR)
    list(APPEND _optix_roots "${OPTIX_INSTALL_DIR}" "${OPTIX_INSTALL_DIR}/include")
endif()
if(OPTIX_ROOT_DIR)
    list(APPEND _optix_roots "${OPTIX_ROOT_DIR}" "${OPTIX_ROOT_DIR}/include")
endif()

if(WIN32)
    list(APPEND _optix_roots
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 9.1.0"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 9.0.0"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 8.1.0"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 8.0.0"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 9.1.0/include"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 9.0.0/include"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 8.1.0/include"
        "$ENV{ProgramFiles}/NVIDIA Corporation/OptiX SDK 8.0.0/include"
    )
else()
    list(APPEND _optix_roots
        "/opt/optix"
        "/opt/optix/include"
        "/usr/local/optix"
        "/usr/local/optix/include"
    )
endif()

find_path(
    OPTIX_INCLUDE_DIR
    NAMES optix.h
    HINTS ${_optix_roots}
    PATH_SUFFIXES include
)

if(NOT OPTIX_INCLUDE_DIR)
    OptiX_report_error("OptiX headers (optix.h and friends) not found. Please locate before proceeding.")
endif()

# Canonical project-facing variable
set(OptiX_INCLUDE "${OPTIX_INCLUDE_DIR}")

# Backfill root/install if missing
if(NOT OPTIX_INSTALL_DIR)
    get_filename_component(_optix_parent "${OPTIX_INCLUDE_DIR}" DIRECTORY)
    if(EXISTS "${_optix_parent}/optix.h")
        set(OPTIX_INSTALL_DIR "${_optix_parent}" CACHE PATH "OptiX install directory" FORCE)
    else()
        get_filename_component(_optix_root "${OPTIX_INCLUDE_DIR}" DIRECTORY)
        set(OPTIX_INSTALL_DIR "${_optix_root}" CACHE PATH "OptiX install directory" FORCE)
    endif()
endif()

if(NOT OPTIX_ROOT_DIR)
    set(OPTIX_ROOT_DIR "${OPTIX_INSTALL_DIR}" CACHE PATH "OptiX root directory" FORCE)
endif()

find_package_handle_standard_args(
    OptiX
    REQUIRED_VARS OPTIX_INCLUDE_DIR
)

mark_as_advanced(
    OPTIX_INCLUDE_DIR
    OPTIX_INSTALL_DIR
    OPTIX_ROOT_DIR
)