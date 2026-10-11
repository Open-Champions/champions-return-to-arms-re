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
# Run again after changing src/ or the patch: it copies src/ in and rebuilds. To start
# from a clean checkout remove local/play-playable and local/play-playable-build first.
set -e
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
else
	echo "build.sh: play-net.patch does not fit $SRC (changed since it was applied?)." >&2
	echo "          git -C \"$SRC\" checkout -- Source   puts the checkout back; then run this again." >&2
	exit 1
fi
mkdir -p "$SRC/Source/ui_qt/rta"
cp "$HERE"/src/* "$SRC/Source/ui_qt/rta/"

if [ ! -f "$BUILD/build.ninja" ]; then
	cmake -G Ninja -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF \
		-DBUILD_PSFPLAYER=OFF -DENABLE_AMAZON_S3=OFF -DCMAKE_PREFIX_PATH="$QT"
fi
cmake --build "$BUILD" --target Play -j "$JOBS"
echo "build.sh: built $BUILD/Source/ui_qt/Play.app; start it with tools/play-net/play.sh"
