# Headless, scriptable runner for Champions: Return to Arms on the core of the Play!
# PlayStation 2 emulator (https://github.com/jpd002/Play-, BSD 2-clause licence).
#
# Nothing of Play! is copied here: this file builds against a checkout whose path you
# give in PLAY_SOURCE_DIR. Only Play!'s core libraries are built (no Qt, no OpenGL).
#
#   cmake -G Ninja -S tools/rig -B local/rig-build \
#         -DPLAY_SOURCE_DIR=$PWD/local/play -DCMAKE_BUILD_TYPE=Release
#   cmake --build local/rig-build --target rta_rig
cmake_minimum_required(VERSION 3.18)

set(PLAY_SOURCE_DIR "" CACHE PATH "Checkout of github.com/jpd002/Play- including its submodules")
if(NOT PLAY_SOURCE_DIR OR NOT EXISTS "${PLAY_SOURCE_DIR}/Source/PS2VM.h")
	message(FATAL_ERROR "Set -DPLAY_SOURCE_DIR=<path to a Play! checkout with submodules>")
endif()
if(NOT EXISTS "${PLAY_SOURCE_DIR}/deps/Framework/include/Types.h")
	message(FATAL_ERROR "${PLAY_SOURCE_DIR} has no submodules; run 'git submodule update --init --recursive' in it")
endif()

# Same as Play!'s own top-level file: must be set before project().
if(APPLE)
	set(CMAKE_OSX_DEPLOYMENT_TARGET "10.15" CACHE STRING "Minimum macOS version")
endif()
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
	set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(CMAKE_MODULE_PATH ${PLAY_SOURCE_DIR}/deps/Dependencies/cmake-modules ${CMAKE_MODULE_PATH})
include(Header)

project(rta_rig)

# Core options.
#  DEBUGGER_INCLUDED  compiles the breakpoint check into translated blocks that contain a
#                     breakpoint (no cost for other blocks); the rig's --break needs it.
#  ENABLE_AMAZON_S3   off: no remote disc images, and no need for the HTTP/S3 code.
#  RTA_RIG_PLAY_LOGS  keeps Play!'s own log calls in a release build (written under
#                     <data>/logs when the rig is run with --play-logs). Off by default:
#                     with it on, the video thread formats a line of text for every
#                     graphics register write whether or not it is printed, which
#                     made the 3-D scenes of this game run about 20 times slower.
set(DEBUGGER_INCLUDED ON CACHE BOOL "Core breakpoint support" FORCE)
set(ENABLE_AMAZON_S3 OFF CACHE BOOL "Disc images from Amazon S3" FORCE)
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
option(RTA_RIG_PLAY_LOGS "Compile Play!'s log calls in (slow; for diagnosing the emulator)" OFF)
if(RTA_RIG_PLAY_LOGS)
	add_compile_definitions(LOGGING_ENABLED=1)
endif()

add_subdirectory(${PLAY_SOURCE_DIR}/Source ${CMAKE_CURRENT_BINARY_DIR}/PlayCore)

add_executable(rta_rig rig.cpp)
target_link_libraries(rta_rig PlayCore)
target_include_directories(rta_rig PRIVATE
	${PLAY_SOURCE_DIR}/deps/Framework/include
	${PLAY_SOURCE_DIR}/deps/CodeGen/include
)
