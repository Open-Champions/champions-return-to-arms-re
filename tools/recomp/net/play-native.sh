#!/bin/sh
# Starts the native build of Champions: Return to Arms (tools/recomp/app, rta_app) for
# playing online, with the options of the emulator build's launcher (tools/play-net/play.sh).
#
#   tools/recomp/net/play-native.sh --disc "/path/to/your disc image.iso" [--server ADDRESS]
#
#   --disc IMAGE      your own disc image of SLUS-20973 v2.00 (or set RTA_DISC)
#   --server ADDRESS  the lobby server: an IPv4 address or a host name.
#                     Left out: a server running on this computer.
#   --server-public A the server's public address, if you are on the server's own
#                     network and it hands that address out (normally found by itself)
#   --player N        a second, third... player on the same computer: its own settings,
#                     memory card and login (default 1)
#   --data DIR        where settings, memory cards and the saved login go
#                     (default local/recomp-out/app-data, app-data-player<N> for N > 1)
#   --fullscreen      start full screen (Escape leaves it)
#   --online          go online by itself: title screen, Internet Game, network setting,
#                     the server's terms, log-in - and stop at the lobby's game list. The
#                     first time it asks for a player name; the account and its password
#                     are the application's business (docs/play-online.md section 4)
#   --host [CODE]     as --online, and on: opens a game of your own, named with a code
#                     for your friends (made up when none is given; shown in the window's
#                     title and on the terminal), and stops in its room
#   --join CODE       as --online, and on: joins the game with that code, into its room
#   --choose-character  with --host or --join: stop on the game's character screens
#                     (otherwise the character you used last is taken by itself)
#   anything after --  is passed to rta_app as it is (rta_app --help)
#
# Build first: python3 tools/recomp/app/build.py (docs/issues/native-app.md,
# docs/issues/native-online.md).  Going online needs the local sign-in patch at build time.
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
APP="${RTA_NATIVE_APP:-$ROOT/local/recomp-out/bin/rta_app}"
DISC="${RTA_DISC:-}"
SERVER=""
SERVER_PUBLIC=""
PLAYER=1
DATA=""
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
	--fullscreen) FULLSCREEN="--fullscreen"; shift ;;
	--online) ONLINE="lobby"; shift ;;
	--host)
		ONLINE="host"; shift
		case "${1:-}" in ""|-*) ;; *) ONLINE="host:$1"; shift ;; esac ;;
	--join) ONLINE="join:$2"; shift 2 ;;
	--choose-character) CHOOSE="+choose"; shift ;;
	--) shift; break ;;
	-h|--help) sed -n '2,28p' "$0"; exit 0 ;;
	*) echo "play-native.sh: unknown option $1 (see --help)" >&2; exit 2 ;;
	esac
done
if [ ! -x "$APP" ]; then
	echo "play-native.sh: the application is not built yet: run python3 tools/recomp/app/build.py" >&2
	exit 1
fi
if [ -z "$DISC" ] || [ ! -f "$DISC" ]; then
	echo "play-native.sh: give your disc image: --disc \"/path/to/image.iso\" (or set RTA_DISC)" >&2
	exit 1
fi
if [ -z "$DATA" ]; then
	DATA="$ROOT/local/recomp-out/app-data"
	[ "$PLAYER" = "1" ] || DATA="$DATA-player$PLAYER"
fi
mkdir -p "$DATA" || exit 1
[ "$ONLINE" = "lobby" ] && CHOOSE=""
set -- --disc "$DISC" --data "$DATA" $FULLSCREEN "$@" -- --opt "net-data=$DATA"
[ -z "$SERVER" ] || set -- "$@" --opt "net-server=$SERVER"
[ -z "$SERVER_PUBLIC" ] || set -- "$@" --opt "net-server-public=$SERVER_PUBLIC"
[ -z "$ONLINE" ] || set -- "$@" --opt "online=$ONLINE$CHOOSE"
echo "play-native.sh: settings, memory cards and the saved login are in $DATA"
exec "$APP" "$@"
