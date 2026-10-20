#!/bin/sh
# online.sh - the native build of Champions: Return to Arms, online by itself (Linux).
#   ./online.sh IMAGE.iso                     the lobby server's list of games
#   ./online.sh IMAGE.iso host [CODE]         open a game on the lobby server; its code is in the window's title
#   ./online.sh IMAGE.iso join CODE           join that game
#   ./online.sh IMAGE.iso room-host           a room of our own at the room service; its code is printed
#   ./online.sh IMAGE.iso room-join CODE      join that room
# Addresses: the first line of server.txt (the lobby server) and its line "service = HOST:PORT"
# (the room service); see that file.  A player name is asked on this terminal the first time
# (or give it: NAME=yourname ./online.sh ...).  The log goes to rta-data/rta_app-log.txt as well.
cd "$(dirname "$0")" || exit 1
if [ -z "$1" ]; then sed -n '2,10p' "$0"; exit 1; fi
disc=$1; shift
case "$1" in
  host) shift; mode="--host $1" ;;
  join) mode="--join $2" ;;
  room-host) mode="--play-host" ;;
  room-join) mode="--play-join $2" ;;
  *)
    echo "  1  the lobby's list of games"
    echo "  2  open a game of your own (you get a code for your friend)"
    echo "  3  join a friend's game (you need the code)"
    printf "Type 1, 2 or 3 and press Enter: "; read choice
    mode=--online
    [ "$choice" = 2 ] && mode=--host
    if [ "$choice" = 3 ]; then printf "The game's code: "; read code; mode="--join $code"; fi ;;
esac
mkdir -p rta-data
if [ -n "$NAME" ]; then set -- --name "$NAME"; else set --; fi
# shellcheck disable=SC2086
./rta_app --disc "$disc" $mode "$@" 2>&1 | tee rta-data/rta_app-log.txt
