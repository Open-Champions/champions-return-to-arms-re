#!/bin/sh
# Builds jitdiff twice: for this machine (Play!'s ARM64 code generator) and, with
# Emscripten, for node (Play!'s WebAssembly code generator). It links the code generator
# libraries of two existing builds of the emulator; nothing is downloaded.
#
#   tools/arith/build.sh NATIVE_BUILD_DIR WEB_BUILD_DIR PLAY_SOURCE_DIR OUT_DIR
#
#   NATIVE_BUILD_DIR  a build of the rig or the application (has PlayCore/CodeGen/libCodeGen.a)
#   WEB_BUILD_DIR     a build of the browser version (has Source/ui_js/Source/CodeGen/libCodeGen.a)
#   PLAY_SOURCE_DIR   the emulator's source tree the two were built from
# Then:  OUT_DIR/jitdiff --mode browser > native.txt;  node OUT_DIR/jitdiff-wasm.js > wasm.txt;
#        cmp native.txt wasm.txt   (the first line names the machine and differs)
set -e
N=$1; W=$2; P=$3; O=$4
[ -n "$O" ] || { echo "usage: build.sh NATIVE_BUILD_DIR WEB_BUILD_DIR PLAY_SOURCE_DIR OUT_DIR"; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
INC="-I$P/deps/CodeGen/include -I$P/deps/Framework/include"
mkdir -p "$O"
NL=$(find "$N" -name libCodeGen.a | head -1); NF=$(find "$N" -name libFramework.a | head -1)
WL=$(find "$W" -name libCodeGen.a | head -1); WF=$(find "$W" -name libFramework.a | head -1)
c++ -std=gnu++17 -O2 $INC "$HERE/jitdiff.cpp" "$NL" "$NF" -o "$O/jitdiff"
em++ -std=gnu++17 -O2 -fexceptions -pthread $INC "$HERE/jitdiff.cpp" "$WL" "$WF" \
	--bind -sALLOW_TABLE_GROWTH -sWASM_BIGINT -sENVIRONMENT=node,worker -sEXIT_RUNTIME=1 \
	-sINITIAL_MEMORY=268435456 -sNODERAWFS=1 -o "$O/jitdiff-wasm.js"
echo "built $O/jitdiff and $O/jitdiff-wasm.js"
