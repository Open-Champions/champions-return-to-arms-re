#!/bin/sh
# Builds the playable application: Play! (https://github.com/jpd002/Play-, BSD 2-clause)
# at the commit this was written against, with play-net.patch and the sources in src/.
#
#   brew install cmake ninja qtbase        # once; "qt" instead of "qtbase" works too
#   tools/play-net/build.sh                # clone (first time), patch, configure, build
#
# Everything is put under local/ (ignored by the repository):
#   local/play-playable          the Play! checkout, patched
#   local/play-playable-build    the build; the application is
#                                local/play-playable-build/Source/ui_qt/Play.app
# Run again after changing src/: it copies src/ in and rebuilds. After the patch itself
# has changed (a newer version of this repository):
#   tools/play-net/build.sh --reset        # puts Play!'s own files back, applies the patch anew
# (--reset discards any change of your own under local/play-playable/Source).
set -e
RESET=""
[ "$1" = "--reset" ] && RESET=1
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
COMMIT=83700b2c31e593bc94e845b4b31b797be84dda59
SRC="${RTA_PLAY_SOURCE:-$ROOT/local/play-playable}"
BUILD="${RTA_PLAY_BUILD:-$ROOT/local/play-playable-build}"
JOBS="${RTA_BUILD_JOBS:-6}"

for tool in git cmake ninja; do
	command -v $tool >/dev/null 2>&1 || { echo "build.sh: $tool is not installed (brew install cmake ninja)" >&2; exit 1; }
done
QT="${RTA_QT_PREFIX:-}"
if [ -z "$QT" ]; then
	for candidate in /opt/homebrew/opt/qtbase /opt/homebrew/opt/qt /usr/local/opt/qtbase /usr/local/opt/qt; do
		[ -d "$candidate/lib/cmake/Qt6" ] && QT="$candidate" && break
	done
fi
[ -n "$QT" ] || { echo "build.sh: Qt 6 not found (brew install qtbase), or set RTA_QT_PREFIX" >&2; exit 1; }

if [ ! -d "$SRC/.git" ]; then
	echo "build.sh: cloning Play! into $SRC"
	git clone --recurse-submodules https://github.com/jpd002/Play-.git "$SRC"
	git -C "$SRC" checkout --detach $COMMIT
	git -C "$SRC" submodule update --init --recursive
fi
[ "$(git -C "$SRC" rev-parse HEAD)" = "$COMMIT" ] || { echo "build.sh: $SRC is not at commit $COMMIT" >&2; exit 1; }

# The patch is applied to a clean tree, or left alone when it is in already.
if git -C "$SRC" apply --check "$HERE/play-net.patch" 2>/dev/null; then
	git -C "$SRC" apply "$HERE/play-net.patch"
	echo "build.sh: play-net.patch applied"
elif git -C "$SRC" apply --check --reverse "$HERE/play-net.patch" 2>/dev/null; then
	echo "build.sh: play-net.patch is in already"
elif [ -n "$RESET" ]; then
	git -C "$SRC" checkout -- Source
	git -C "$SRC" apply "$HERE/play-net.patch"
	echo "build.sh: Play!'s files put back and play-net.patch applied"
else
	echo "build.sh: play-net.patch does not fit $SRC: another version of it is applied there." >&2
	echo "          Run  tools/play-net/build.sh --reset  (it discards changes under $SRC/Source)." >&2
	exit 1
fi
mkdir -p "$SRC/Source/ui_qt/rta"
cp "$HERE"/src/* "$SRC/Source/ui_qt/rta/"
# The client of our own rendezvous service (rooms by code, punched routes, the relay), compiled
# in as it is from the native program's tree: src/RtaRoom.cpp includes it from rta/net2, and it
# includes the socket layer from rta/net (docs/issues/app-rendezvous.md).
mkdir -p "$SRC/Source/ui_qt/rta/net2" "$SRC/Source/ui_qt/rta/net"
# (tls.h / tls.cpp: the TCP link inside the operating system's TLS, where the client has it.)
# CMake takes every .cpp file found in rta/net2.
for file in session.h session_impl.h session.cpp session_mock.cpp session_net.cpp carrier.h carrier.cpp hash.h cardchars.cpp tls.h tls.cpp; do
	[ -f "$ROOT/tools/recomp/net2/$file" ] || continue
	cmp -s "$ROOT/tools/recomp/net2/$file" "$SRC/Source/ui_qt/rta/net2/$file" || cp "$ROOT/tools/recomp/net2/$file" "$SRC/Source/ui_qt/rta/net2/"
done
cmp -s "$ROOT/tools/recomp/net/sock.h" "$SRC/Source/ui_qt/rta/net/sock.h" || cp "$ROOT/tools/recomp/net/sock.h" "$SRC/Source/ui_qt/rta/net/"

if [ ! -f "$BUILD/build.ninja" ]; then
	cmake -G Ninja -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF \
		-DBUILD_PSFPLAYER=OFF -DENABLE_AMAZON_S3=OFF -DCMAKE_PREFIX_PATH="$QT"
fi
cmake --build "$BUILD" --target Play -j "$JOBS"
echo "build.sh: built $BUILD/Source/ui_qt/Play.app; start it with tools/play-net/play.sh"
