#!/bin/bash
# setup-mac.sh - the work behind "Champions Setup" on a Mac (the window is main.swift; this can also be run in a terminal).
#
#   setup-mac.sh --disc "/path/to/your image.iso" [--resources DIR] [--no-start]
#
# What it does, with "@progress PERCENT TEXT" lines for the window:
#   1. Qt 6 (the window library of the native program): Homebrew's qtbase when it is there, else the official build of
#      The Qt Company (qtbase 6.11.3 for macOS, from download.qt.io; size and SHA-256 checked), unpacked into
#      ~/Library/Application Support/Champions/qt - nothing is installed into macOS;
#   2. our source code (source.tar.gz beside this script: the repository, nothing of the game) into
#      ~/Library/Application Support/Champions/workspace;
#   3. tools/install/fromdisc.py: the game's executable out of YOUR disc image, translated and built here, and the game
#      library of the Godot version;
#   4. "Champions" (the native program) and "Champions Godot" in ~/Applications, both also on the desktop;
#   5. starts Champions (not with --no-start).
# Needs Apple's command line tools (clang, python3); the window asks for them first.  The disc image is only read.
# setup.ini beside this script may say "service = HOST:PORT": the room service the programs use (written by whoever
# hands out the setup; there is none in the repository).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
RES="$HERE"; DISC=""; START=1
while [ $# -gt 0 ]; do
  case "$1" in
    --disc) DISC=$2; shift 2;;
    --resources) RES=$2; shift 2;;
    --no-start) START=0; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done
progress() { echo "@progress $1 $2"; }
fail() { echo "@error $*"; exit 1; }

BASE="$HOME/Library/Application Support/Champions"
WORK="$BASE/workspace"
APPS="$HOME/Applications"
QTVER=6.11.3
QTURL="https://download.qt.io/online/qtsdkrepository/mac_x64/desktop/qt6_6113/qt6_6113/qt.qt6.6113.clang_64/6.11.3-0-202609240332qtbase-MacOS-MacOS_15-Clang-MacOS-MacOS_15-X86_64-ARM64.7z"
QTSIZE=31038525
QTSHA=ace71e14bc590054aed32603f9876517f74198423f50700e6c6152da8916c482

[ -f "$DISC" ] || fail "No disc image: $DISC"
[ -f "$RES/source.tar.gz" ] || fail "The setup is damaged: source.tar.gz is missing."
SERVICE=""
[ -f "$RES/setup.ini" ] && SERVICE=$(sed -n 's/^[[:space:]]*service[[:space:]]*=[[:space:]]*\([^[:space:]#]*\).*$/\1/p' "$RES/setup.ini" | head -1)
mkdir -p "$BASE" "$APPS" || fail "Cannot make $BASE"

# 0. the compiler (the window has made sure of it; a terminal run is told)
if ! /usr/bin/xcode-select -p >/dev/null 2>&1 || ! /usr/bin/xcrun --find clang++ >/dev/null 2>&1; then
  /usr/bin/xcode-select --install 2>/dev/null
  fail "Apple's command line tools are needed: click Install in Apple's window, then start Champions Setup again."
fi
PY=/usr/bin/python3
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null || fail "python3 of Apple's command line tools does not run."
FREE=$(df -k "$BASE" | awk 'NR==2 {print $4}')
[ "${FREE:-0}" -gt 4000000 ] || fail "Not enough free disk space: about 4 GB are needed in your home folder."

# 1. Qt
progress 1 "Looking for Qt"
QT=""
for b in /opt/homebrew/opt/qtbase /usr/local/opt/qtbase; do
  [ "${CHAMPIONS_SETUP_OFFICIAL_QT:-0}" = 1 ] && break        # a test of the download on a Mac that has Homebrew's Qt
  [ -d "$b/lib/QtGui.framework" ] && QT=$b && break
done
if [ -z "$QT" ]; then
  QT="$BASE/qt/$QTVER"
  if [ ! -d "$QT/lib/QtGui.framework/Headers" ]; then
    mkdir -p "$BASE/qt"
    PART="$BASE/qt/qtbase-$QTVER.7z"
    rm -f "$PART"
    echo "downloading Qt $QTVER (qtbase, 30 MB) from download.qt.io"
    /usr/bin/curl -fsSL --retry 3 -o "$PART" "$QTURL" &
    CURL=$!
    while kill -0 $CURL 2>/dev/null; do
      sleep 1
      HAVE=$(stat -f %z "$PART" 2>/dev/null || echo 0)
      progress $(( 1 + HAVE * 7 / QTSIZE )) "Downloading Qt, the window library ($(( HAVE / 1048576 )) of 30 MB)"
    done
    wait $CURL || fail "The download of Qt from download.qt.io did not work: is this Mac online?"
    [ "$(stat -f %z "$PART")" = "$QTSIZE" ] || fail "The download of Qt is not complete; start Champions Setup again."
    GOT=$(shasum -a 256 "$PART" | cut -d' ' -f1)
    [ "$GOT" = "$QTSHA" ] || fail "The download of Qt is not the official file (SHA-256 $GOT)."
    progress 8 "Unpacking Qt"
    rm -rf "$QT.part"; mkdir -p "$QT.part"
    /usr/bin/tar -xf "$PART" -C "$QT.part" || fail "Qt did not unpack."
    rm -rf "$QT"; mv "$QT.part" "$QT"; rm -f "$PART"
    xattr -dr com.apple.quarantine "$QT" 2>/dev/null
  fi
fi
echo "Qt: $QT"

# 2. the source code
progress 9 "Unpacking the source code"
mkdir -p "$WORK"
/usr/bin/tar -xzf "$RES/source.tar.gz" -C "$WORK" || fail "The source code did not unpack."

# 3. the translation and the build
progress 10 "Reading your disc image"
export RTA_QT="$QT"
ARGS=(-B "$WORK/tools/install/fromdisc.py" --platform mac --disc "$DISC" --godot --progress --desktop "$APPS" --launcher-name Champions)
[ -n "$SERVICE" ] && ARGS+=(--service "$SERVICE")
LOG="$BASE/setup-log.txt"
: > "$LOG"
nice -n 10 "$PY" "${ARGS[@]}" 2>&1 | while IFS= read -r line; do
  printf '%s\n' "$line" >> "$LOG"
  case "$line" in
    "@progress "*)
      rest=${line#@progress }; p=${rest%% *}; text=${rest#* }
      progress $(( 10 + p * 85 / 100 )) "$text";;
    *) printf '%s\n' "$line";;
  esac
done
CODE=${PIPESTATUS[0]}
[ "$CODE" = 0 ] || fail "The build did not finish (the details are in $LOG)."
[ -d "$APPS/Champions.app" ] || fail "The launcher was not made (see $LOG)."

# 4. the Godot version: our application (no game inside) and a launcher that tells it where the disc image is
progress 96 "Putting Champions in your Applications"
GODOT_DONE=0
if [ -d "$RES/RtaGodot.app" ] && [ -f "$HOME/Library/Application Support/Open Champions/RTA Godot/librta_game.dylib" ]; then
  rm -rf "$BASE/RtaGodot.app"
  /usr/bin/ditto "$RES/RtaGodot.app" "$BASE/RtaGodot.app" && xattr -dr com.apple.quarantine "$BASE/RtaGodot.app" 2>/dev/null
  EXE=$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$BASE/RtaGodot.app/Contents/Info.plist" 2>/dev/null)
  if [ -n "$EXE" ] && [ -x "$BASE/RtaGodot.app/Contents/MacOS/$EXE" ]; then
    G="$APPS/Champions Godot.app"
    rm -rf "$G"; mkdir -p "$G/Contents/MacOS"
    cat > "$G/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>launch</string>
<key>CFBundleIdentifier</key><string>org.open-champions.champions-godot-launcher</string>
<key>CFBundleName</key><string>Champions Godot</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
PLIST
    q() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
    {
      echo '#!/bin/sh'
      echo '# made by Champions Setup: the Godot version with your disc image'
      echo "export RTA_DISC=$(q "$DISC")"
      echo "exec $(q "$BASE/RtaGodot.app/Contents/MacOS/$EXE") \"\$@\""
    } > "$G/Contents/MacOS/launch"
    chmod 755 "$G/Contents/MacOS/launch"
    GODOT_DONE=1
  fi
fi
for a in "Champions.app" "Champions Godot.app"; do
  [ -d "$APPS/$a" ] || continue
  /usr/bin/codesign --force -s - "$APPS/$a" >/dev/null 2>&1
  if [ -d "$HOME/Desktop" ] && [ ! -e "$HOME/Desktop/$a" ] || [ -L "$HOME/Desktop/$a" ]; then
    ln -sfn "$APPS/$a" "$HOME/Desktop/$a"
  fi
done
echo "installed: $APPS/Champions.app$( [ $GODOT_DONE = 1 ] && printf ' and %s' "$APPS/Champions Godot.app")"
progress 100 "Done"
echo "@done $APPS/Champions.app"
[ $START = 1 ] && /usr/bin/open "$APPS/Champions.app"
exit 0
