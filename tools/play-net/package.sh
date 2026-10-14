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
# docs/play-online.md, "The application".
#
# Options (each also as the environment variable named beside it):
#   --default-server ADDRESS     RTA_DEFAULT_SERVER   the lobby server this copy uses until
#                                                     the person sets another (Online menu)
#   --default-online on|off      RTA_DEFAULT_ONLINE   "Go online at start", until the person
#                                                     switches it (without this: on)
#   --default-room-service HOST:PORT  RTA_DEFAULT_ROOM_SERVICE  the rendezvous service of the
#                                                     Room menu (docs/issues/app-rendezvous.md);
#                                                     a host name for a service inside TLS
#   --zip                        RTA_ZIP=1            also <name>.zip beside the application,
#                                                     for sending (the signature survives it)
#   --private-signin-patch FILE  RTA_PRIVATE_SIGNIN_PATCH
#                                                     copies that file into the application.
#                                                     FOR PRIVATE HAND-TO-HAND BUILDS ONLY: a
#                                                     copy made this way must never be published,
#                                                     uploaded to a public place or put into the
#                                                     repository. Without this option the sign-in
#                                                     patch is never put in.
#   --default-textures DIR       RTA_DEFAULT_TEXTURES the art pack's folder (dump/ and replace/
#                                                     below it) until the person sets another
#                                                     (launch.ini: textures=). Without it the
#                                                     application takes "textures" in its own
#                                                     folder in Application Support when a pack
#                                                     is there - a place macOS asks nothing about
#   --sign IDENTITY              RTA_SIGN_IDENTITY    sign with this code-signing identity of
#                                                     your keychain instead of ad hoc (a
#                                                     self-signed one will do). macOS then takes
#                                                     every build signed with it for the same
#                                                     program: its permission to read Desktop,
#                                                     Documents or Downloads is kept from one
#                                                     build to the next
#   --stable-requirement         RTA_SIGN_STABLE=1    ad hoc, but with the designated requirement
#                                                     "the identifier is ours" instead of the
#                                                     default "this very code": the same effect
#                                                     without any certificate (untested with
#                                                     macOS's permission store; see
#                                                     docs/issues/mac-app-start.md)
# The defaults are written to Contents/Resources/rta/defaults.ini; the application
# reads them only for what its own launch.ini does not say.
#
# The result is for this computer and for people you hand it to yourself: it is not
# notarised, so on another Mac the first opening is refused and has to be allowed once in
# System Settings > Privacy & Security ("Open Anyway"; before macOS 15 a right-click and
# "Open" does it). It stays under local/ (ignored by the repository).
set -e
DEFAULT_SERVER="${RTA_DEFAULT_SERVER:-}"
DEFAULT_ONLINE="${RTA_DEFAULT_ONLINE:-}"
DEFAULT_ROOM_SERVICE="${RTA_DEFAULT_ROOM_SERVICE:-}"
SIGNIN="${RTA_PRIVATE_SIGNIN_PATCH:-}"
ZIP="${RTA_ZIP:-}"
DEFAULT_TEXTURES="${RTA_DEFAULT_TEXTURES:-}"
SIGN_IDENTITY="${RTA_SIGN_IDENTITY:-}"
SIGN_STABLE="${RTA_SIGN_STABLE:-}"
while [ $# -gt 0 ]; do
	case "$1" in
	--default-server) DEFAULT_SERVER="$2"; shift 2 ;;
	--default-server=*) DEFAULT_SERVER="${1#*=}"; shift ;;
	--default-online) DEFAULT_ONLINE="$2"; shift 2 ;;
	--default-online=*) DEFAULT_ONLINE="${1#*=}"; shift ;;
	--default-room-service) DEFAULT_ROOM_SERVICE="$2"; shift 2 ;;
	--default-room-service=*) DEFAULT_ROOM_SERVICE="${1#*=}"; shift ;;
	--private-signin-patch) SIGNIN="$2"; shift 2 ;;
	--private-signin-patch=*) SIGNIN="${1#*=}"; shift ;;
	--zip) ZIP=1; shift ;;
	--default-textures) DEFAULT_TEXTURES="$2"; shift 2 ;;
	--default-textures=*) DEFAULT_TEXTURES="${1#*=}"; shift ;;
	--sign) SIGN_IDENTITY="$2"; shift 2 ;;
	--sign=*) SIGN_IDENTITY="${1#*=}"; shift ;;
	--stable-requirement) SIGN_STABLE=1; shift ;;
	-h|--help) sed -n '2,/^set -e$/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
	*) echo "package.sh: unknown option $1 (see --help)" >&2; exit 1 ;;
	esac
done
case "$DEFAULT_SERVER" in
*[!A-Za-z0-9.-]*) echo "package.sh: --default-server takes a host name or an IPv4 address" >&2; exit 1 ;;
esac
case "$DEFAULT_ROOM_SERVICE" in
*[!A-Za-z0-9.:-]*) echo "package.sh: --default-room-service takes HOST:PORT" >&2; exit 1 ;;
esac
case "$DEFAULT_ONLINE" in
"") ;;
on|true|1|yes) DEFAULT_ONLINE=true ;;
off|false|0|no) DEFAULT_ONLINE=false ;;
*) echo "package.sh: --default-online takes on or off" >&2; exit 1 ;;
esac
[ -z "$SIGNIN" ] || [ -f "$SIGNIN" ] || { echo "package.sh: --private-signin-patch: no such file" >&2; exit 1; }
case "$DEFAULT_TEXTURES" in
"" | /*) ;;
*) echo "package.sh: --default-textures takes a full path" >&2; exit 1 ;;
esac
[ -z "$SIGN_IDENTITY" ] || [ -z "$SIGN_STABLE" ] || { echo "package.sh: --sign and --stable-requirement are two ways to the same end: give one" >&2; exit 1; }
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
# what this copy does until the person says otherwise
if [ -n "$DEFAULT_SERVER$DEFAULT_ONLINE$DEFAULT_TEXTURES$DEFAULT_ROOM_SERVICE" ]; then
	{
		echo "[General]"
		[ -z "$DEFAULT_SERVER" ] || echo "server=$DEFAULT_SERVER"
		[ -z "$DEFAULT_ONLINE" ] || echo "online=$DEFAULT_ONLINE"
		[ -z "$DEFAULT_TEXTURES" ] || echo "textures=$DEFAULT_TEXTURES"
		[ -z "$DEFAULT_ROOM_SERVICE" ] || echo "room_service=$DEFAULT_ROOM_SERVICE"
	} > "$APP/Contents/Resources/rta/defaults.ini"
fi
# only when asked to, for a private build (see the top of this file)
[ -z "$SIGNIN" ] || cp "$SIGNIN" "$APP/Contents/Resources/rta/SLUS-20973_4028A55F_signin.pnach"

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
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier io.github.open-champions.play-rta" "$PLIST"   # IDENTIFIER below
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

# Signed: macOS on Apple silicon runs nothing unsigned. Without an identity ("ad hoc") the
# signature's designated requirement - what macOS takes for "the same program" when it
# looks up a permission it gave, such as reading the Desktop folder - is the hash of this
# very build, so every new build is asked about again (docs/issues/mac-app-start.md, "The
# permission across releases"). --sign IDENTITY makes it "our identifier, signed with that
# certificate"; --stable-requirement makes it "our identifier" on an ad-hoc signature (the
# nested Qt code is signed first as it is, then the bundle alone with the requirement).
# Extended attributes (Finder's, a synced Desktop's) are not allowed inside a signed bundle.
IDENTIFIER=io.github.open-champions.play-rta
xattr -cr "$APP"
if [ -n "$SIGN_IDENTITY" ]; then
	codesign --force --deep --sign "$SIGN_IDENTITY" "$APP" > "$DIST/codesign.log" 2>&1 || { echo "package.sh: codesign with the identity '$SIGN_IDENTITY' failed, see $DIST/codesign.log" >&2; exit 1; }
else
	codesign --force --deep --sign - "$APP" > "$DIST/codesign.log" 2>&1 || { echo "package.sh: codesign failed, see $DIST/codesign.log" >&2; exit 1; }
	if [ -n "$SIGN_STABLE" ]; then
		codesign --force --sign - -r="designated => identifier \"$IDENTIFIER\"" "$APP" >> "$DIST/codesign.log" 2>&1 || { echo "package.sh: codesign with the stable requirement failed, see $DIST/codesign.log" >&2; exit 1; }
	fi
fi
codesign --verify --deep --strict "$APP" || { echo "package.sh: the signature does not verify" >&2; exit 1; }
REQUIREMENT=$(codesign -d -r- "$APP" 2>/dev/null | sed -n 's/^designated => //p')

# the archive is made here too, before a synced folder can touch the bundle
[ -z "$ZIP" ] || ditto -c -k --keepParent "$APP" "$STAGE/$NAME.zip"

rm -rf "$FINAL"
mv "$APP" "$FINAL"
APP="$FINAL"
[ -z "$ZIP" ] || mv -f "$STAGE/$NAME.zip" "$DIST/$NAME.zip"

echo "package.sh: made $APP ($(du -sh "$APP" | cut -f1))"
echo "            double-click it, or: open \"$APP\""
echo "            its data: ~/Library/Application Support/$NAME/"
[ -z "$DEFAULT_SERVER$DEFAULT_ONLINE$DEFAULT_TEXTURES" ] || echo "            defaults inside: ${DEFAULT_SERVER:+server $DEFAULT_SERVER }${DEFAULT_ONLINE:+go online at start $DEFAULT_ONLINE }${DEFAULT_TEXTURES:+art pack $DEFAULT_TEXTURES}"
echo "            macOS takes for the same program: $REQUIREMENT"
case "$REQUIREMENT" in
cdhash*) echo "            (this very build only: a disc image or art pack under Desktop, Documents or Downloads is asked about again after every new build. Kept without a question: beside the application, or in ~/Library/Application Support/$NAME/ - the pack as textures/replace there. Or sign with --sign / --stable-requirement.)" ;;
esac
[ -z "$ZIP" ] || echo "            archive: $DIST/$NAME.zip ($(du -h "$DIST/$NAME.zip" | cut -f1))"
[ -z "$SIGNIN" ] || echo "            THE SIGN-IN PATCH IS INSIDE: a private copy, for people you hand it to yourself. Never publish it."
