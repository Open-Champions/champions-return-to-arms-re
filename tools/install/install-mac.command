#!/bin/bash
# install-mac.command - build the native Champions: Return to Arms from YOUR OWN disc, on this Mac.
# Double-click it in Finder (or run it in Terminal).  One step:
#   1. checks the tools: Apple's command line tools (the compiler), Homebrew, Homebrew's Qt 6 (qtbase);
#      what is missing is installed from its official source (Apple; brew.sh; Homebrew) after you say yes;
#   2. asks for your disc image (.iso) of the US release, SLUS-20973 v2.00;
#   3. copies SLUS_209.73 out of it, translates the game's code to C++ and builds the program
#      (tools/install/fromdisc.py; 10 to 30 minutes);
#   4. puts "Champions RTA Native" on your desktop;
#   5. builds the game library of the Godot application from the same translation (--no-godot: not).
# Nothing of the game comes with this repository and nothing of yours leaves this Mac: the disc image is
# read here and the program is built here, into this folder's local/ (never share that folder).
# Options for a terminal:  install-mac.command [--disc FILE] [--desktop DIR] [--yes] [--no-godot]
set -u
cd "$(dirname "$0")/../.." || exit 1
WORK=$PWD
DISC=""; DESKTOP=""; YES=0; GODOT=1
while [ $# -gt 0 ]; do
  case "$1" in
    --disc) DISC=$2; shift 2;;
    --desktop) DESKTOP=$2; shift 2;;
    --yes) YES=1; shift;;
    --no-godot) GODOT=0; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done
say() { printf '\n== %s\n' "$*"; }
ask() {   # ask "question": true for yes
  [ $YES = 1 ] && return 0
  printf '%s [Y/n] ' "$1"; read -r a; case "$a" in n*|N*) return 1;; *) return 0;; esac
}
finish() { echo; echo "$1"; [ -t 0 ] && [ $YES = 0 ] && { printf 'Press Return to close. '; read -r _; }; exit "${2:-0}"; }

say "Champions: Return to Arms - the native build from your own disc ($WORK)"
[ "$(uname -s)" = Darwin ] || finish "This is the Mac installer; on Linux use install-linux.sh, on Windows install-windows.bat." 1

# 1. the tools
if ! xcode-select -p >/dev/null 2>&1 || ! /usr/bin/xcrun --find clang++ >/dev/null 2>&1; then
  say "Apple's command line tools (the compiler) are not installed."
  xcode-select --install 2>/dev/null
  finish "A window from Apple asks to install them: click Install, wait until it is done, then open this file again." 1
fi
BREW=""
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && BREW=$b && break; done
[ -z "$BREW" ] && command -v brew >/dev/null 2>&1 && BREW=$(command -v brew)
if [ -z "$BREW" ]; then
  say "Homebrew (https://brew.sh) is not installed. It is needed for Qt, the window library of the program."
  ask "Install Homebrew now with its official installer? (it asks for your Mac password itself)" || finish "Install Homebrew from https://brew.sh, then open this file again." 1
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || finish "Homebrew was not installed." 1
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && BREW=$b && break; done
  [ -z "$BREW" ] && finish "Homebrew is still not found." 1
fi
eval "$("$BREW" shellenv)"
QT="$("$BREW" --prefix)/opt/qtbase"
if [ ! -d "$QT/lib/QtGui.framework" ]; then
  say "Qt 6 (Homebrew's qtbase) is not installed."
  ask "Install it now (brew install qtbase, about 300 MB)?" || finish "The program cannot be built without it." 1
  "$BREW" install qtbase || finish "brew install qtbase did not work." 1
fi
PY=""
for p in python3 /usr/bin/python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then PY=$(command -v "$p"); break; fi
done
[ -z "$PY" ] && finish "No python3 (3.8 or newer) was found; it comes with Apple's command line tools." 1
export RTA_QT="$QT"
echo "compiler: $(/usr/bin/xcrun --find clang++); Qt: $QT; python: $PY"

# 2. the disc image
if [ -z "$DISC" ]; then
  say "Choose your disc image of Champions: Return to Arms (US, SLUS-20973, v2.00) in the window that opens."
  DISC=$(osascript -e 'POSIX path of (choose file with prompt "Your disc image of Champions: Return to Arms (.iso)" of type {"iso", "public.iso-image", "public.data"})' 2>/dev/null)
  [ -z "$DISC" ] && finish "No disc image was chosen." 1
fi
[ -f "$DISC" ] || finish "Not a file: $DISC" 1

# 3. and 4. the translation, the build and the launcher
say "Building (10 to 30 minutes; the Mac stays usable - the compiler runs at a lower priority)"
ARGS=(--platform mac --disc "$DISC")
[ -n "$DESKTOP" ] && ARGS+=(--desktop "$DESKTOP")
[ $GODOT = 1 ] && ARGS+=(--godot)
if nice -n 10 "$PY" -B tools/install/fromdisc.py "${ARGS[@]}"; then
  finish "Done. Start the game with \"Champions RTA Native\" on your desktop (the log is in local/recomp-out/app-data/rta_app-log.txt); the Godot application (RtaGodot.app) finds its game library by itself."
else
  finish "The build did not finish; the lines above say why." 1
fi
