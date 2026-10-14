#!/bin/sh
# Starts the native build of Champions: Return to Arms (rta_app) and takes it into a room
# of our own - no SOE screen, no account, no password (docs/issues/native-rendezvous.md).
#
#   tools/recomp/net2/play.sh --disc "/path/to/your disc image.iso" --play-host
#   tools/recomp/net2/play.sh --disc "/path/to/your disc image.iso" --play-join H4KQ7
#
#   --disc IMAGE        your own disc image of SLUS-20973 v2.00 (or set RTA_DISC)
#   --play-host         open a room; its code is printed and shown ("ROOM CODE H4KQ7")
#   --play-join CODE    join the room with that code
#   --name NAME         your display name, the first time (a label; change it later in a portal)
#   --service HOST:PORT the rendezvous service (else RTA_NET2_SERVICE, else the file
#                       net2-service.txt in the data folder)
#   --players N         with --play-host: start by itself when N players are in the room and
#                       have chosen their characters (default 2)
#   --friends           with --play-host: your friends may walk in from their friends list
#   --level NAME        with --play-host: start in that level instead of the hub
#   --again             after a game, go back into the room's next game
#   --player N          a second, third... player on the same computer: its own settings,
#                       memory card and identity (default 1)
#   --data DIR          where settings, memory cards and the identity file go
#                       (default local/recomp-out/app-data, app-data-player<N> for N > 1)
#   --fullscreen
#   anything after --   is passed to rta_app as it is
#
# What happens: the game boots to its title screen by itself, its own character screens come
# up (make a character, or triangle "Import" for one saved on this computer's memory card),
# and when everybody in the room has a character the host's game starts for all.
# Build first: python3 tools/recomp/app/build.py with tools/recomp/net2/net2.patch applied.
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
APP="${RTA_NATIVE_APP:-$ROOT/local/recomp-out/bin/rta_app}"
DISC="${RTA_DISC:-}"
PLAYER=1
DATA=""
FULLSCREEN=""
ROOM=""
NAME=""
SERVICE=""
PLAYERS=""
FRIENDS=""
LEVEL=""
AGAIN=""
while [ $# -gt 0 ]; do
	case "$1" in
	--disc) DISC="$2"; shift 2 ;;
	--play-host) ROOM="host"; shift ;;
	--play-join) ROOM="join:$2"; shift 2 ;;
	--name) NAME="$2"; shift 2 ;;
	--service) SERVICE="$2"; shift 2 ;;
	--players) PLAYERS="$2"; shift 2 ;;
	--friends) FRIENDS=":friends"; shift ;;
	--level) LEVEL="$2"; shift 2 ;;
	--again) AGAIN=1; shift ;;
	--player) PLAYER="$2"; shift 2 ;;
	--data) DATA="$2"; shift 2 ;;
	--fullscreen) FULLSCREEN="--fullscreen"; shift ;;
	--) shift; break ;;
	-h|--help) sed -n '2,30p' "$0"; exit 0 ;;
	*) echo "play.sh: unknown option $1 (see --help)" >&2; exit 2 ;;
	esac
done
if [ ! -x "$APP" ]; then
	echo "play.sh: the application is not built yet: python3 tools/recomp/app/build.py (with net2.patch applied)" >&2
	exit 1
fi
if [ -z "$DISC" ] || [ ! -f "$DISC" ]; then
	echo "play.sh: give your disc image: --disc \"/path/to/image.iso\" (or set RTA_DISC)" >&2
	exit 1
fi
if [ -z "$ROOM" ]; then
	echo "play.sh: say --play-host or --play-join CODE" >&2
	exit 2
fi
if [ -z "$DATA" ]; then
	DATA="$ROOT/local/recomp-out/app-data"
	[ "$PLAYER" = "1" ] || DATA="$DATA-player$PLAYER"
fi
mkdir -p "$DATA" || exit 1
[ "$ROOM" = "host" ] && ROOM="host$FRIENDS"
set -- --disc "$DISC" --data "$DATA" $FULLSCREEN "$@" -- --opt "net-data=$DATA" --opt "net2-data=$DATA" --opt "net2=$ROOM"
[ -z "$NAME" ] || set -- "$@" --opt "net2-name=$NAME"
[ -z "$SERVICE" ] || set -- "$@" --opt "net2-service=$SERVICE"
[ -z "$PLAYERS" ] || set -- "$@" --opt "net2-players=$PLAYERS"
[ -z "$LEVEL" ] || set -- "$@" --opt "net2-level=$LEVEL"
[ -z "$AGAIN" ] || set -- "$@" --opt "net2-again=1"
echo "play.sh: settings, memory cards and your identity (net2-identity.key) are in $DATA"
exec "$APP" "$@"
