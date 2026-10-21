#!/bin/bash
# Champions Setup for Linux - builds Champions: Return to Arms from YOUR OWN disc image, on this computer.
#
#   Double-click it (if your file manager asks: "Run"; if it only opens it as text: right-click, Properties,
#   "Allow executing file as program"), or in a terminal:  bash Champions-Setup-Linux.sh [--disc FILE] [--terminal]
#
# This file is a shell script with an archive appended (tools/install/setup/build_setups.py): our source code and the
# Godot version (our code only), nothing of the game.  What it does, with a progress window (zenity or kdialog) or in a
# terminal:
#   1. the compiler and libraries from your distribution's own archive when they are missing (it asks for your password
#      through your system's own window: pkexec, or sudo in a terminal);
#   2. finds your disc image of the US release, SLUS-20973 v2.00, in Downloads, Desktop, Documents or on a mounted
#      drive (an .iso whose SLUS_209.73 has PCSX2's checksum 4028A55F), else one file window;
#   3. unpacks the source code into ~/.local/share/champions/workspace and runs tools/install/fromdisc.py: the game's
#      executable out of the disc image, translated and built here, and the Godot version's game library;
#   4. "Champions" and "Champions Godot" in the applications menu and on the desktop, and starts Champions.
# setup.ini in the archive may hold "service = HOST:PORT", the room service the program uses.
set -u
SELF=$(readlink -f "$0" 2>/dev/null || echo "$0")
DISC=""; TERMINAL=0; START=1
while [ $# -gt 0 ]; do
  case "$1" in
    --disc) DISC=$2; shift 2;;
    --terminal) TERMINAL=1; shift;;
    --no-start) START=0; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
BASE="$DATA/champions"
WORK="$BASE/workspace"
SETUP="$BASE/setup"
LOG="$BASE/setup-log.txt"
mkdir -p "$BASE" || { echo "cannot make $BASE"; exit 1; }
: > "$LOG"

# ---- how to talk to the player: a zenity or kdialog window, or the terminal ----
GUI=""
if [ $TERMINAL = 0 ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  if command -v zenity >/dev/null 2>&1; then GUI=zenity
  elif command -v kdialog >/dev/null 2>&1; then GUI=kdialog
  fi
fi
if [ -z "$GUI" ] && [ ! -t 1 ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  # started from a file manager with no window tool: open a terminal and run there
  for t in x-terminal-emulator gnome-terminal konsole xfce4-terminal mate-terminal xterm; do
    command -v $t >/dev/null 2>&1 || continue
    case $t in
      gnome-terminal) exec gnome-terminal -- bash "$SELF" --terminal;;
      *) exec $t -e bash "$SELF" --terminal;;
    esac
  done
fi

PROG_FD=""
KREF=""
start_progress() {
  case "$GUI" in
    zenity)
      exec 3> >(zenity --progress --title="Champions Setup" --width=520 --no-cancel --auto-close \
                 --text="You need your own disc image of Champions: Return to Arms (US, v2.00)." 2>/dev/null)
      PROG_FD=3;;
    kdialog)
      KREF=$(kdialog --title "Champions Setup" --progressbar "Champions Setup" 100 2>/dev/null);;
  esac
}
progress() {   # progress PERCENT TEXT
  echo "$(date +%T) [$1%] $2" >> "$LOG"
  case "$GUI" in
    zenity) [ -n "$PROG_FD" ] && printf '%s\n# %s\n' "$1" "$2" >&3 2>/dev/null;;
    kdialog)
      if [ -n "$KREF" ] && command -v qdbus >/dev/null 2>&1; then
        qdbus $KREF Set "" value "$1" >/dev/null 2>&1; qdbus $KREF setLabelText "$2" >/dev/null 2>&1
      fi;;
    *) printf '== [%3s%%] %s\n' "$1" "$2";;
  esac
}
stop_progress() {
  [ -n "$PROG_FD" ] && { exec 3>&-; PROG_FD=""; }
  [ -n "$KREF" ] && command -v qdbus >/dev/null 2>&1 && qdbus $KREF close >/dev/null 2>&1
  KREF=""
}
tell() {   # tell TEXT: a message the player must see
  echo "$1" >> "$LOG"
  case "$GUI" in
    zenity) zenity --info --title="Champions Setup" --width=480 --text="$1" 2>/dev/null;;
    kdialog) kdialog --title "Champions Setup" --msgbox "$1" 2>/dev/null;;
    *) echo; echo "$1";;
  esac
}
fail() {
  stop_progress
  case "$GUI" in
    zenity) zenity --error --title="Champions Setup" --width=480 --text="Setup did not finish: $1\n\nThe details are in $LOG" 2>/dev/null;;
    kdialog) kdialog --title "Champions Setup" --error "Setup did not finish: $1

The details are in $LOG" 2>/dev/null;;
    *) echo; echo "Setup did not finish: $1"; echo "The details are in $LOG";;
  esac
  exit 1
}

start_progress
progress 0 "Starting"
[ "$(uname -s)" = Linux ] || fail "this is the setup for Linux."
ARCH=$(uname -m)
case "$ARCH" in x86_64|amd64) ARCH=x86_64;; aarch64|arm64) ARCH=aarch64;; *) fail "only x86-64 and 64-bit ARM computers are built for (this is $ARCH).";; esac

# ---- 0. unpack this file's archive ----
progress 1 "Unpacking the setup"
LINE=$(awk '/^__CHAMPIONS_ARCHIVE_BELOW__$/ { print NR + 1; exit 0 }' "$SELF")
[ -n "$LINE" ] || fail "this copy of the setup is damaged (no archive in it); download it again."
rm -rf "$SETUP"; mkdir -p "$SETUP"
tail -n +"$LINE" "$SELF" | tar -xzf - -C "$SETUP" || fail "this copy of the setup is damaged; download it again."
SERVICE=""
[ -f "$SETUP/setup.ini" ] && SERVICE=$(sed -n 's/^[[:space:]]*service[[:space:]]*=[[:space:]]*\([^[:space:]#]*\).*$/\1/p' "$SETUP/setup.ini" | head -1)

# ---- 1. the compiler and the libraries ----
have_tools() {
  command -v clang++ >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 || return 1
  printf '#include <SDL2/SDL.h>\n#include <openssl/ssl.h>\n#include <EGL/egl.h>\n#include <thread>\nint main(){return 0;}\n' |
    clang++ -std=c++17 -x c++ - -o /dev/null -static-libstdc++ -static-libgcc -lSDL2 -lssl -lcrypto -lpthread >/dev/null 2>&1
}
progress 2 "Looking for the compiler"
if ! have_tools; then
  if command -v apt-get >/dev/null 2>&1; then
    CMD="apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends clang g++ python3 libsdl2-dev libssl-dev libegl-dev"
  elif command -v dnf >/dev/null 2>&1; then
    CMD="dnf install -y clang gcc-c++ libstdc++-static python3 SDL2-devel openssl-devel mesa-libEGL-devel"
  elif command -v pacman >/dev/null 2>&1; then
    CMD="pacman -S --needed --noconfirm clang gcc python sdl2 openssl mesa"
  elif command -v zypper >/dev/null 2>&1; then
    CMD="zypper --non-interactive install clang gcc-c++ python3 libSDL2-devel libopenssl-devel Mesa-libEGL-devel"
  else
    fail "this Linux distribution is not known to the setup. Install clang, a C++ standard library, python3 and the development files of SDL 2, OpenSSL 3 and EGL, then start the setup again."
  fi
  echo "packages: $CMD" >> "$LOG"
  progress 3 "Installing the compiler and three libraries from your distribution$( [ "$(id -u)" = 0 ] || echo ' (it asks for your password)')"
  if [ "$(id -u)" = 0 ]; then sh -c "$CMD" >> "$LOG" 2>&1
  elif [ -n "$GUI" ] && command -v pkexec >/dev/null 2>&1; then pkexec sh -c "$CMD" >> "$LOG" 2>&1
  elif command -v sudo >/dev/null 2>&1; then
    if [ -t 0 ]; then echo "The compiler and three libraries come from your distribution: $CMD"; sudo sh -c "$CMD" 2>&1 | tee -a "$LOG"
    else fail "the compiler is missing. In a terminal: sudo sh -c \"$CMD\""; fi
  else fail "the compiler is missing and there is no sudo or pkexec. As the administrator: $CMD"
  fi
  have_tools || fail "the compiler still cannot build against SDL 2, OpenSSL and EGL (see the log)."
fi
echo "compiler: $(clang++ --version | head -1)" >> "$LOG"
FREE=$(df -Pk "$BASE" | awk 'NR==2 {print $4}')
[ "${FREE:-0}" -gt 4000000 ] || fail "not enough free disk space: about 4 GB are needed in your home folder."

# ---- 2. the source code, then the disc image ----
progress 5 "Unpacking the source code"
mkdir -p "$WORK"
tar -xzf "$SETUP/source.tar.gz" -C "$WORK" || fail "the source code did not unpack."
if [ -z "$DISC" ]; then
  progress 6 "Looking for your disc image"
  DISC=$(python3 -B "$WORK/tools/install/fromdisc.py" --find 2>>"$LOG" | head -1)
fi
while [ -z "$DISC" ] || ! python3 -B "$WORK/tools/install/fromdisc.py" --check "$DISC" >> "$LOG" 2>&1; do
  [ -n "$DISC" ] && tell "That file is not the US release, version 2.00, of Champions: Return to Arms (SLUS-20973): $DISC"
  case "$GUI" in
    zenity) DISC=$(zenity --file-selection --title="Your disc image of Champions: Return to Arms (US, v2.00, .iso)" --file-filter="Disc images | *.iso *.ISO" 2>/dev/null) || fail "no disc image was chosen.";;
    kdialog) DISC=$(kdialog --getopenfilename "$HOME" "*.iso *.ISO|Disc images" 2>/dev/null) || fail "no disc image was chosen.";;
    *) [ -t 0 ] || fail "no disc image found; start the setup with --disc FILE"
       printf 'Setup did not find your disc image. Path of the .iso file: '; read -r DISC; [ -n "$DISC" ] || fail "no disc image was chosen.";;
  esac
done
DISC=$(readlink -f "$DISC")
echo "disc image: $DISC" >> "$LOG"

# ---- 3. the translation and the build ----
GODOT=0
[ -f "$SETUP/godot-$ARCH/RtaGodot.pck" ] && GODOT=1
ARGS=(-B "$WORK/tools/install/fromdisc.py" --platform linux --disc "$DISC" --progress --launcher-name Champions)
[ $GODOT = 1 ] && ARGS+=(--godot)
[ -n "$SERVICE" ] && ARGS+=(--service "$SERVICE")
progress 7 "Building Champions from your disc image (10 to 40 minutes)"
set -o pipefail
nice -n 10 python3 "${ARGS[@]}" 2>&1 | while IFS= read -r line; do
  case "$line" in
    "@progress "*) rest=${line#@progress }; p=${rest%% *}; progress $(( 7 + p * 90 / 100 )) "${rest#* }";;
    *) printf '%s\n' "$line" >> "$LOG"; [ -z "$GUI" ] && printf '   %s\n' "$line";;
  esac
done || fail "the build did not finish."
set +o pipefail

# ---- 4. the Godot version (our application: no game inside) and the launchers ----
APPS="$DATA/applications"
DESK=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
if [ $GODOT = 1 ] && [ -f "$DATA/open-champions/rta-godot/librta_game.so" ]; then
  progress 98 "Putting the Godot version in place"
  rm -rf "$BASE/godot"; cp -r "$SETUP/godot-$ARCH" "$BASE/godot"
  chmod 755 "$BASE/godot/RtaGodot.$ARCH" 2>/dev/null
  mkdir -p "$APPS"
  cat > "$BASE/godot/champions-godot.sh" <<EOF
#!/bin/sh
# made by Champions Setup: the Godot version with your disc image
export RTA_DISC='$(printf '%s' "$DISC" | sed "s/'/'\\\\''/g")'
exec '$BASE/godot/RtaGodot.$ARCH' "\$@"
EOF
  chmod 755 "$BASE/godot/champions-godot.sh"
  ENTRY="[Desktop Entry]
Type=Application
Name=Champions Godot
Comment=Champions: Return to Arms in Godot, made from your own disc
Exec=\"$BASE/godot/champions-godot.sh\"
Terminal=false
Categories=Game;
"
  for d in "$APPS" "$DESK"; do
    [ -d "$d" ] || continue
    printf '%s' "$ENTRY" > "$d/champions-godot.desktop" && chmod 755 "$d/champions-godot.desktop"
    command -v gio >/dev/null 2>&1 && gio set "$d/champions-godot.desktop" metadata::trusted true >/dev/null 2>&1
  done
fi
PROGRAM=$(sed -n 's/^program=//p' "$WORK/local/install.txt" 2>/dev/null)
[ -n "$PROGRAM" ] && [ -x "$PROGRAM" ] || fail "the program was not made (see the log)."
echo "program: $PROGRAM" >> "$LOG"
progress 100 "Done"
stop_progress
if [ $START = 1 ]; then
  ( cd "$(dirname "$PROGRAM")" && setsid ./play.sh "$DISC" >/dev/null 2>&1 & )
fi
tell "Champions is ready: in your applications menu and on the desktop (\"Champions\", and \"Champions Godot\")."
exit 0
__CHAMPIONS_ARCHIVE_BELOW__
