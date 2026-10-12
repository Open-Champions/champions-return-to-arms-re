#!/bin/sh
# Starts the playable build of Champions: Return to Arms (tools/play-net/README.md,
# docs/play-online.md).
#
#   tools/play-net/play.sh --disc "/path/to/your disc image.iso" [--server ADDRESS]
#
#   --disc IMAGE      your own disc image of SLUS-20973 v2.00 (or set RTA_DISC)
#   --server ADDRESS  the lobby server: an IPv4 address or a host name.
#                     Left out: a server running on this computer.
#   --server-public A the server's public address, if you are on the server's own
#                     network and it hands that address out (normally found by itself)
#   --player N        a second, third... player on the same computer: its own settings
#                     and memory card (default 1)
#   --data DIR        where settings, memory cards and logs go
#                     (default local/play-data/player<N>)
#   --sections LIST   patch sections: a file with one name per line, or '*' for all,
#                     or 'none' (default tools/play-net/sections-suggested.txt)
#   --fullscreen      start full screen (Escape leaves it)
#   --online          go online by itself: title screen, Internet Game, network setting,
#                     the server's terms, log-in - and stop at the lobby's game list. The
#                     first time it asks for a player name (docs/play-online.md section 4)
#   --host            as --online, and on: opens a game of your own, named with a code
#                     of four letters for your friends, and stops in its room
#   --join CODE       as --online, and on: joins the game with that code, into its room
#   --choose-character  with --host or --join: stop on the game's character screens
#                     (otherwise the character you used last is taken by itself)
#   anything after --  is passed to the application as it is
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
APP="${RTA_PLAY_APP:-$ROOT/local/play-playable-build/Source/ui_qt/Play.app/Contents/MacOS/Play}"
DISC="${RTA_DISC:-}"
SERVER=""
SERVER_PUBLIC=""
PLAYER=1
DATA=""
SECTIONS="$HERE/sections-suggested.txt"
FULLSCREEN=""
ONLINE=""
CHOOSE=""
while [ $# -gt 0 ]; do
	case "$1" in
	--disc) DISC="$2"; shift 2 ;;
	--server) SERVER="$2"; shift 2 ;;
	--server-public) SERVER_PUBLIC="$2"; shift 2 ;;
	--player) PLAYER="$2"; shift 2 ;;
	--data) DATA="$2"; shift 2 ;;
	--sections) SECTIONS="$2"; shift 2 ;;
	--fullscreen) FULLSCREEN="--fullscreen"; shift ;;
	--online) ONLINE="lobby"; shift ;;
	--host) ONLINE="host"; shift ;;
	--join) ONLINE="join:$2"; shift 2 ;;
	--choose-character) CHOOSE="+choose"; shift ;;
	--) shift; break ;;
	-h|--help) sed -n '2,27p' "$0"; exit 0 ;;
	*) echo "play.sh: unknown option $1 (see --help)" >&2; exit 2 ;;
	esac
done
if [ ! -x "$APP" ]; then
	echo "play.sh: the application is not built yet: run tools/play-net/build.sh" >&2
	exit 1
fi
if [ -z "$DISC" ] || [ ! -f "$DISC" ]; then
	echo "play.sh: give your disc image: --disc \"/path/to/image.iso\" (or set RTA_DISC)" >&2
	exit 1
fi
[ -n "$DATA" ] || DATA="$ROOT/local/play-data/player$PLAYER"
mkdir -p "$DATA" || exit 1

set -- --rta-data "$DATA" --disc "$DISC" $FULLSCREEN "$@"
[ -z "$SERVER" ] || set -- "$@" --rta-server "$SERVER"
[ -z "$SERVER_PUBLIC" ] || set -- "$@" --rta-server-public "$SERVER_PUBLIC"
[ "$ONLINE" = "lobby" ] && CHOOSE=""
[ -z "$ONLINE" ] || set -- "$@" --rta-online "$ONLINE$CHOOSE"
PATCHES="$ROOT/patches/SLUS-20973_4028A55F.pnach"
case "$SECTIONS" in
none) ;;
'*') set -- "$@" --rta-patch-file "$PATCHES" --rta-patch-sections '*' ;;
*) set -- "$@" --rta-patch-file "$PATCHES" --rta-patch-sections "@$SECTIONS" ;;
esac
# The sign-in step: Sony's servers for it are gone. The patch that skips it is not part
# of the repository; it is used if you have it at this place.
SIGNIN="${RTA_SIGNIN_PATCH:-$ROOT/local/SLUS-20973_4028A55F_signin.pnach}"
if [ -f "$SIGNIN" ]; then
	set -- "$@" --rta-extra-patch "$SIGNIN"
else
	echo "play.sh: no sign-in patch at $SIGNIN: the game will stop with a network error after 'Internet Game'" >&2
fi
echo "play.sh: settings, memory cards and the log (rta.log) are in $DATA"
exec "$APP" "$@"
