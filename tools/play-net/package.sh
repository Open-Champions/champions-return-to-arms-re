#!/bin/sh
# Makes the application a person can double-click: local/dist/Play-RTA.app.
#
#   tools/play-net/build.sh       # first: the application itself
#   tools/play-net/package.sh
#
# It is the built Play.app with Qt's frameworks copied in (macdeployqt, part of Homebrew's
# qtbase), our patch file and the list of sections in Contents/Resources/rta, Play!'s
# licence and Qt's in Contents/Resources/licences, another name and identifier (so that
# it is not taken for an ordinary Play! installation and does not share its settings),
# and an ad-hoc code signature. Such an application needs no command line: see
# docs/play-online.md, "The application". The sign-in patch is never put in.
#
# The result is for this computer and for people you hand it to yourself: it is not
# notarised, so on another Mac it has to be opened the first time with a right-click and
# "Open". It stays under local/ (ignored by the repository).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
NAME="${RTA_APP_NAME:-Play-RTA}"
BUILT="${RTA_PLAY_BUILD:-$ROOT/local/play-playable-build}/Source/ui_qt/Play.app"
SOURCE="${RTA_PLAY_SOURCE:-$ROOT/local/play-playable}"
DIST="${RTA_DIST:-$ROOT/local/dist}"
APP="$DIST/$NAME.app"
PATCHES="$ROOT/patches/SLUS-20973_4028A55F.pnach"
SECTIONS="$HERE/sections-suggested.txt"

[ -x "$BUILT/Contents/MacOS/Play" ] || { echo "package.sh: build first: tools/play-net/build.sh" >&2; exit 1; }
[ -f "$PATCHES" ] || { echo "package.sh: $PATCHES is missing" >&2; exit 1; }
DEPLOY="${RTA_MACDEPLOYQT:-}"
if [ -z "$DEPLOY" ]; then
	for candidate in /opt/homebrew/opt/qtbase/bin/macdeployqt /opt/homebrew/opt/qt/bin/macdeployqt /usr/local/opt/qtbase/bin/macdeployqt /usr/local/opt/qt/bin/macdeployqt; do
		[ -x "$candidate" ] && DEPLOY="$candidate" && break
	done
fi
[ -n "$DEPLOY" ] || DEPLOY=$(command -v macdeployqt || true)
[ -n "$DEPLOY" ] || { echo "package.sh: macdeployqt not found (it comes with: brew install qtbase)" >&2; exit 1; }

# Put together and signed in a temporary directory and moved into place at the end: a
# folder that is synced (a Desktop kept in iCloud) gets extended attributes hung on
# every bundle in it within seconds, and a bundle with those can be neither signed nor
# checked.
mkdir -p "$DIST"
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/play-rta-package.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
FINAL="$APP"
APP="$STAGE/$NAME.app"
cp -R "$BUILT" "$APP"

# what play.sh gives on the command line
mkdir -p "$APP/Contents/Resources/rta"
cp "$PATCHES" "$APP/Contents/Resources/rta/SLUS-20973_4028A55F.pnach"
cp "$SECTIONS" "$APP/Contents/Resources/rta/sections.txt"

# whose work this is
LICENCES="$APP/Contents/Resources/licences"
mkdir -p "$LICENCES"
cp "$SOURCE/License.txt" "$LICENCES/Play-LICENSE.txt"
for dir in "$SOURCE"/deps/* "$SOURCE"/deps/Dependencies/*; do
	[ -d "$dir" ] || continue
	for file in "$dir"/LICENSE* "$dir"/License* "$dir"/COPYING* "$dir"/LICENCE*; do
		[ -f "$file" ] && cp "$file" "$LICENCES/$(basename "$dir")-$(basename "$file")" || true
	done
done
QTPREFIX=$(cd "$(dirname "$DEPLOY")/.." && pwd)
for file in "$QTPREFIX"/LICENSE* "$QTPREFIX"/share/doc/qtbase*/LICENSE* "$QTPREFIX"/LICENSES/LGPL-3.0-only.txt "$QTPREFIX"/LICENSES/GPL-3.0-only.txt; do
	[ -f "$file" ] && cp "$file" "$LICENCES/Qt-$(basename "$file")" || true
done
cat > "$LICENCES/README.txt" <<NOTE
$NAME is the Play! PlayStation 2 emulator (https://github.com/jpd002/Play-), by
Jean-Philip Desjardins and contributors, under the BSD 2-clause licence
(Play-LICENSE.txt), with changes by the Champions RE project for playing Champions:
Return to Arms online. The changes are a patch and source files published in that
project (tools/play-net: play-net.patch, src/); Play! was taken at commit
83700b2c31e593bc94e845b4b31b797be84dda59.

It is not an official product of the Play! project, of Sony Computer Entertainment, of
Sony Online Entertainment, of Snowblind Studios or of anyone else. It contains no
PlayStation 2 BIOS and nothing of the game.

The Qt frameworks in Contents/Frameworks are the Qt Company's and contributors', used
under the GNU Lesser General Public License version 3 (Qt-*.txt, https://www.qt.io); they
are unchanged copies of Homebrew's build and may be replaced by other builds of the same
version. The other files here are the licences of the libraries Play! is built with.
NOTE

# its own name: its own settings, its own place in the Dock and in the firewall's list
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string $NAME" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier io.github.open-champions.play-rta" "$PLIST"
/usr/libexec/PlistBuddy -c "Delete :NSMainNibFile" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :GCSupportsControllerUserInteraction bool true" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string 'The game talks to the lobby server and to the other players on your network.'" "$PLIST" 2>/dev/null || true

# Qt inside
(cd "$STAGE" && "$DEPLOY" "$NAME.app" -always-overwrite) > "$DIST/macdeployqt.log" 2>&1 || { echo "package.sh: macdeployqt failed, see $DIST/macdeployqt.log" >&2; exit 1; }
OUTSIDE=$(find "$APP/Contents" -type f \( -name "*.dylib" -o -perm +111 \) -exec otool -L {} + 2>/dev/null | grep -E "^\s+(/opt/homebrew|/usr/local)" | sort -u || true)
if [ -n "$OUTSIDE" ]; then
	echo "package.sh: something inside still wants a library from outside the application:" >&2
	echo "$OUTSIDE" >&2
	exit 1
fi

# signed for this computer (no identity): macOS on Apple silicon runs nothing unsigned.
# Extended attributes (Finder's, a synced Desktop's) are not allowed inside a signed bundle.
xattr -cr "$APP"
codesign --force --deep --sign - "$APP" > "$DIST/codesign.log" 2>&1 || { echo "package.sh: codesign failed, see $DIST/codesign.log" >&2; exit 1; }
codesign --verify --deep --strict "$APP" || { echo "package.sh: the signature does not verify" >&2; exit 1; }

rm -rf "$FINAL"
mv "$APP" "$FINAL"
APP="$FINAL"

echo "package.sh: made $APP ($(du -sh "$APP" | cut -f1))"
echo "            double-click it, or: open \"$APP\""
echo "            its data: ~/Library/Application Support/$NAME/"
