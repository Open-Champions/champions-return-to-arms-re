# The GDExtension that puts the translated game into a Godot 4.5 project.
#
# It holds no game code: it loads the game library (tools/godot/build.py builds it from
# your own disc's executable into local/godot-spike/) at run time through the C interface
# of ../lib/rtag.h.  The layout, the options and the pins are those of
# open-champions-godot/gdextension, so that this directory can be moved there as it is:
#
#   cmake -S tools/godot/extension -B local/godot-spike/build/extension-template_debug -G Ninja \
#     -DGODOT_CPP_DIR=local/godot-spike/deps/godot-cpp/src -DCMAKE_BUILD_TYPE=Release \
#     -DGODOTCPP_TARGET=template_debug -DRTA_GODOT_OUTPUT_DIR=local/godot-spike/project/bin
#
# (tools/godot/build.py extension does exactly this.)
cmake_minimum_required(VERSION 3.21)
project(rta_godot VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(GODOTCPP_TARGET "template_debug" CACHE STRING "Godot host: template_debug or template_release")
set_property(CACHE GODOTCPP_TARGET PROPERTY STRINGS "template_debug;template_release")
if(NOT GODOTCPP_TARGET STREQUAL "template_debug" AND NOT GODOTCPP_TARGET STREQUAL "template_release")
    message(FATAL_ERROR "GODOTCPP_TARGET must be template_debug or template_release")
endif()
set(GODOT_CPP_DIR "" CACHE PATH "Checkout of the godot-cpp commit in dependencies.json")
if(NOT EXISTS "${GODOT_CPP_DIR}/CMakeLists.txt")
    message(FATAL_ERROR "Set GODOT_CPP_DIR to the pinned godot-cpp checkout (see dependencies.json).")
endif()
set(RTA_GODOT_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/bin" CACHE PATH "Where the extension library goes (the project's bin/)")
find_package(Git REQUIRED)
execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${GODOT_CPP_DIR}" rev-parse HEAD
    OUTPUT_VARIABLE GODOT_CPP_REV OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE PIN_RESULT)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/dependencies.json" DEPENDENCY_LOCK)
string(JSON GODOT_CPP_PIN GET "${DEPENDENCY_LOCK}" godot_cpp_commit)
if(NOT PIN_RESULT EQUAL 0 OR NOT GODOT_CPP_REV STREQUAL GODOT_CPP_PIN)
    message(FATAL_ERROR "godot-cpp must be checked out at ${GODOT_CPP_PIN}")
endif()
set(GODOTCPP_SYSTEM_HEADERS ON CACHE BOOL "Treat upstream bindings as system headers" FORCE)
set(GODOTCPP_PRECISION "single" CACHE STRING "Pinned Godot standard build precision" FORCE)
set(GODOTCPP_USE_HOT_RELOAD OFF CACHE BOOL "Restart after rebuilding the extension" FORCE)
if(MSVC)
    set(GODOTCPP_USE_STATIC_CPP ON CACHE BOOL "Self-contained desktop CRT" FORCE)
    set(GODOTCPP_DEBUG_CRT OFF CACHE BOOL "Use release CRT consistently" FORCE)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded" CACHE STRING "Static release CRT" FORCE)
endif()
add_subdirectory("${GODOT_CPP_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/godot-cpp")
file(GLOB RTA_GODOT_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")
# The game-state reader for a HUD drawn by Godot (RtaGameState, src/rta_gamestate.*): a plain C reader of the machine's
# memory - addresses and offsets, no game code or text - from where the core keeps it (rta_gamestate.cpp includes its
# source, so only the directory is named here).
set(RTA_GAMESTATE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../recomp/app" CACHE PATH "Where gamestate.h / gamestate.cpp are")
if(EXISTS "${RTA_GAMESTATE_DIR}/gamestate.cpp" AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/rta_gamestate.cpp")
    set(RTA_GODOT_HAVE_GAMESTATE ON)
else()
    list(FILTER RTA_GODOT_SOURCES EXCLUDE REGEX "rta_gamestate\\.cpp$")
endif()
# The online session for the portal (RtaNet2, src/rta_net2.*; tools/recomp/net2): compiled in WITHOUT its service
# (NET2_NO_SERVICE: no socket code in the extension - only the mock answers), when its sources are there.
set(RTA_NET2_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../recomp/net2" CACHE PATH "Where session.h / session.cpp / session_mock.cpp are")
option(RTA_GODOT_NET2 "Compile RtaNet2 into the extension when its sources exist" ON)
if(RTA_GODOT_NET2 AND EXISTS "${RTA_NET2_DIR}/session.cpp" AND EXISTS "${RTA_NET2_DIR}/session_mock.cpp" AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/rta_net2.cpp")
    list(APPEND RTA_GODOT_SOURCES "${RTA_NET2_DIR}/session.cpp" "${RTA_NET2_DIR}/session_mock.cpp")
    # the saved-character reader behind net2_local_characters (no game code needed)
    if(EXISTS "${RTA_NET2_DIR}/cardchars.cpp")
        list(APPEND RTA_GODOT_SOURCES "${RTA_NET2_DIR}/cardchars.cpp")
    endif()
    set(RTA_GODOT_HAVE_NET2 ON)
else()
    list(FILTER RTA_GODOT_SOURCES EXCLUDE REGEX "rta_net2\\.cpp$")
endif()
add_library(rta-godot-extension SHARED ${RTA_GODOT_SOURCES})
target_include_directories(rta-godot-extension PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../lib")
if(RTA_GODOT_HAVE_NET2)
    target_include_directories(rta-godot-extension PRIVATE "${RTA_NET2_DIR}")
    target_compile_definitions(rta-godot-extension PRIVATE RTA_GODOT_HAVE_NET2=1 NET2_NO_SERVICE=1)
endif()
if(RTA_GODOT_HAVE_GAMESTATE)
    target_include_directories(rta-godot-extension PRIVATE "${RTA_GAMESTATE_DIR}")
    target_compile_definitions(rta-godot-extension PRIVATE RTA_GODOT_HAVE_GAMESTATE=1)
endif()
target_link_libraries(rta-godot-extension PRIVATE godot::cpp ${CMAKE_DL_LIBS})
if(MSVC)
    target_compile_options(rta-godot-extension PRIVATE /W4 /utf-8 /EHsc)
else()
    target_compile_options(rta-godot-extension PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
get_target_property(RTA_GODOT_ARCH godot-cpp GODOTCPP_ARCH)
if(APPLE)
    set(RTA_GODOT_LIBRARY_NAME "rta_godot.macos.${GODOTCPP_TARGET}")
elseif(WIN32)
    set(RTA_GODOT_LIBRARY_NAME "rta_godot.windows.${GODOTCPP_TARGET}.${RTA_GODOT_ARCH}")
else()
    set(RTA_GODOT_LIBRARY_NAME "rta_godot.linux.${GODOTCPP_TARGET}.${RTA_GODOT_ARCH}")
endif()
set_target_properties(rta-godot-extension PROPERTIES
    PREFIX ""
    OUTPUT_NAME "${RTA_GODOT_LIBRARY_NAME}"
    LIBRARY_OUTPUT_DIRECTORY "${RTA_GODOT_OUTPUT_DIR}/$<0:>"
    RUNTIME_OUTPUT_DIRECTORY "${RTA_GODOT_OUTPUT_DIR}/$<0:>")
