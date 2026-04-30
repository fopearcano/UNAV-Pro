# UNAV Pro — Native (C++) build placeholder.
#
# v0.8 feasibility spike: this file documents what the v0.9 build
# will look like, but is intentionally a no-op today. Running
# `cmake .` here does not produce a loaded Cinema 4D plugin.
#
# When the real work lands (see docs/PYTHON_TO_CPP_MIGRATION_PLAN.md
# Phase 1), this file will:
#
#   1. Pin a CMake minimum version compatible with the Maxon SDK
#      build infrastructure (CMake >= 3.20).
#   2. Locate the Cinema 4D SDK via a `MAXON_SDK_DIR` cache var or
#      a `find_package(Cinema4D REQUIRED)` macro.
#   3. Declare the `unav_native` target as a SHARED library
#      compiled with the host's expected ABI flags.
#   4. Add the `include/` headers to the target's interface and
#      compile every `src/*.cpp` translation unit.
#   5. Install the produced .xdl64/.xlib/.cdl into the user's
#      C4D plugins folder per platform conventions.
#
# Today, none of that is enabled. The variable below trips a
# clear warning if a curious user runs CMake on this folder.

cmake_minimum_required(VERSION 3.20)
project(unav_native_skeleton VERSION 0.8.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(UNAV_NATIVE_BUILD "Enable the v0.9 native build (off in v0.8)" OFF)

if(NOT UNAV_NATIVE_BUILD)
  message(STATUS
    "UNAV native skeleton: build is intentionally disabled in v0.8. "
    "See native/README.md and docs/V0_8_NATIVE_CPP_FEASIBILITY.md "
    "for the migration plan; expect this CMakeLists.txt to gain a "
    "real target in v0.9.")
  return()
endif()

# -----------------------------------------------------------------------------
# v0.9 placeholder. The block below is *not* exercised in v0.8. It
# exists so a reader of the skeleton sees the eventual shape.
# -----------------------------------------------------------------------------

if(NOT DEFINED MAXON_SDK_DIR)
  message(FATAL_ERROR
    "MAXON_SDK_DIR must point at a Cinema 4D 2023+ SDK install. "
    "Pass -DMAXON_SDK_DIR=/path/to/sdk to cmake.")
endif()

# These sources / includes are placeholders. The v0.9 implementer
# fills them in following docs/PYTHON_TO_CPP_MIGRATION_PLAN.md.
set(UNAV_NATIVE_SOURCES
  src/unav_native_plugin.cpp
  src/unav_point_buffer.cpp
)

add_library(unav_native SHARED ${UNAV_NATIVE_SOURCES})
target_include_directories(unav_native
  PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
  PRIVATE ${MAXON_SDK_DIR}/include
)
target_compile_features(unav_native PUBLIC cxx_std_17)

# Real install rules go here in v0.9.
