#!/bin/sh
# install-linux.sh - build the native Champions: Return to Arms from YOUR OWN disc, on this Linux computer.
#   sh tools/install/install-linux.sh [--disc FILE] [--desktop DIR] [--yes] [--no-packages]
# One step:
#   1. installs the tools from your distribution's own archive (it asks first; sudo asks for your password):
#      Debian, Ubuntu, Mint, Pop!_OS:  clang g++ python3 libsdl2-dev libssl-dev
#      Fedora:                         clang gcc-c++ libstdc++-static python3 SDL2-devel openssl-devel
#      Arch, Manjaro:                  clang gcc python sdl2 openssl
#      openSUSE:                       clang gcc-c++ python3 libSDL2-devel libopenssl-devel
#   2. asks for your disc image (.iso) of the US release, SLUS-20973 v2.00 (a file window when zenity or
#      kdialog is there, else a question in the terminal);
#   3. copies SLUS_209.73 out of it, translates the game's code to C++ and builds the program
#      (tools/install/fromdisc.py; 10 to 40 minutes);
#   4. puts "Champions RTA Native" in the applications menu and on the desktop.
# Nothing of the game comes with this repository and nothing of yours leaves this computer: the program is
# built here, into this folder's local/ (never share that folder).
set -u
cd "$(dirname "$0")/../.." || exit 1
DISC=""; DESKTOP=""; YES=0; PACKAGES=1
while [ $# -gt 0 ]; do
  case "$1" in
    --disc) DISC=$2; shift 2;;
    --desktop) DESKTOP=$2; shift 2;;
    --yes) YES=1; shift;;
    --no-packages) PACKAGES=0; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done
say() { printf '\n== %s\n' "$*"; }
ask() { [ $YES = 1 ] && return 0; printf '%s [Y/n] ' "$1"; read -r a; case "$a" in n*|N*) return 1;; *) return 0;; esac; }
die() { echo "$*"; exit 1; }

say "Champions: Return to Arms - the native build from your own disc ($PWD)"
[ "$(uname -s)" = Linux ] || die "This is the Linux installer; on a Mac use install-mac.command, on Windows install-windows.bat."
case "$(uname -m)" in x86_64|amd64|aarch64|arm64) ;; *) die "Only x86-64 and aarch64 (64-bit ARM) are built for: this is $(uname -m).";; esac

# 1. the tools
have_tools() {
  command -v clang++ >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 || return 1
  printf '#include <SDL2/SDL.h>\n#include <openssl/ssl.h>\n#include <thread>\nint main(){return 0;}\n' |
    clang++ -std=c++17 -x c++ - -o /dev/null -static-libstdc++ -static-libgcc -lSDL2 -lssl -lcrypto -lpthread >/dev/null 2>&1
}
if [ $PACKAGES = 1 ] && ! have_tools; then
  . /etc/os-release 2>/dev/null
  like="${ID:-} ${ID_LIKE:-}"
  if command -v apt-get >/dev/null 2>&1; then
    CMD="apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends clang g++ python3 libsdl2-dev libssl-dev"
  elif command -v dnf >/dev/null 2>&1; then
    CMD="dnf install -y clang gcc-c++ libstdc++-static python3 SDL2-devel openssl-devel"
  elif command -v pacman >/dev/null 2>&1; then
    CMD="pacman -S --needed --noconfirm clang gcc python sdl2 openssl"
  elif command -v zypper >/dev/null 2>&1; then
    CMD="zypper --non-interactive install clang gcc-c++ python3 libSDL2-devel libopenssl-devel"
  else
    die "This distribution ($like) is not known here. Install clang, a C++ standard library, python3 and the development files of SDL 2 and OpenSSL 3, then run this again with --no-packages."
  fi
  say "The compiler and two libraries are needed from your distribution's archive:"
  echo "  $CMD"
  ask "Install them now?" || die "Install them yourself, then run this again."
  if [ "$(id -u)" = 0 ]; then sh -c "$CMD"; else sudo sh -c "$CMD"; fi || die "The packages were not installed."
  have_tools || die "clang++ still cannot build against SDL2 and OpenSSL: see the lines above."
fi
command -v python3 >/dev/null 2>&1 || die "python3 is needed."
echo "compiler: $(clang++ --version | head -1)"

# 2. the disc image
if [ -z "$DISC" ]; then
  say "Your disc image of Champions: Return to Arms (US, SLUS-20973, v2.00)"
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v zenity >/dev/null 2>&1; then
    DISC=$(zenity --file-selection --title="Your disc image of Champions: Return to Arms (.iso)" --file-filter="Disc images | *.iso *.ISO" 2>/dev/null)
  elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v kdialog >/dev/null 2>&1; then
    DISC=$(kdialog --getopenfilename "$HOME" "*.iso *.ISO|Disc images" 2>/dev/null)
  fi
  if [ -z "$DISC" ]; then printf 'Path of the .iso file: '; read -r DISC; fi
fi
[ -f "$DISC" ] || die "Not a file: $DISC"

# 3. and 4.
say "Building (10 to 40 minutes, at a lower priority)"
if [ -n "$DESKTOP" ]; then
  nice -n 10 python3 -B tools/install/fromdisc.py --platform linux --disc "$DISC" --desktop "$DESKTOP" || die "The build did not finish; the lines above say why."
else
  nice -n 10 python3 -B tools/install/fromdisc.py --platform linux --disc "$DISC" || die "The build did not finish; the lines above say why."
fi
say "Done. Start the game with \"Champions RTA Native\" (applications menu or desktop), or play.sh in local/recomp-out/linux/rta-linux-$(uname -m | sed 's/arm64/aarch64/;s/amd64/x86_64/')/"
