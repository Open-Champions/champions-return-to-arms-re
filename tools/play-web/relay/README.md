# The relay of the browser build

A web page has no TCP or UDP of its own. A page of the browser build
([tools/play-web](../README.md)) therefore opens **one WebSocket connection** to this
program, and the console's network inside the page asks through it for what the desktop
application does with sockets of its own. The relay owns the real sockets:

| For the page's | the relay opens | to |
|---|---|---|
| two TCP connections (gateway, lobby) | one TCP connection each | the configured lobby server, the configured ports only (default 40810 and 40910) |
| UDP port (the game uses one of 4000–4004) | one UDP socket, kept for the session and used for every destination | the lobby server's discovery port (default 10101); the UDP socket of another session of this relay; a player outside, under the rule below |

So the lobby server sees a browser player as an ordinary player at the relay's address,
and hands that address and port to the other players. A datagram for another browser
player is handed from one session to the other inside the program.

**Players outside the relay** (the desktop application). A datagram passes between a
session's socket and an outside address and port only when that pair is *open* for the
session, and a pair is opened in two ways only:

- **named**: the lobby server named the address to this page. The relay reads the lobby
  connection as it passes (server to page only, nothing is changed) and takes the
  address the server *observed* for the host of a listed game, of a game found by name,
  and of a player who wants into the page's game (messages 0x55, 0x57, 0x65 of
  `docs/lobby-protocol.md`). The "own-network" address in those messages is a player's
  own claim and is not taken; nothing a player can type is read as an address. A
  datagram from a named address with another port opens that port as well (routers
  change ports; the game accepts a player by address).
- **both**: the page has asked to send to the address *and* a datagram from that address
  has arrived on the session's socket, in either order, within 30 seconds. That is how
  the third player of a game is met: the host passes addresses along player to player,
  and the lobby server names nobody.

What a page sends to an address that is not open is not sent. What arrives from an
address that is not open is not passed to a page. So it is **not a proxy to anywhere**,
and neither a page nor a stranger can make it send or pass anything alone: a page
reaches the lobby server, the other pages, and the players the lobby server put it in a
game with. Only public addresses, unless `--lan` is given; loop-back, multicast and
reserved addresses never (refused with a notice the page shows).

`relay.py` is Python 3.8 or later with the standard library only (the WebSocket
handshake and framing are written out in it), about 900 lines. Python because it is on
every server the lobby server runs on and on every developer's computer, needs nothing
installed, and the load is small: a few hundred small messages a second per game.

## Running it

```
relay.py --lobby 192.0.2.10                       # listens on ws://127.0.0.1:8975/relay
relay.py --lobby 192.0.2.10 --listen 127.0.0.1:8975 --path /relay \
         --origin https://play.example --trust-proxy --udp-ports 41000-41999
relay.py --lobby 192.168.1.20 --lan              # everything on one computer or one home network
```

- `--lobby` is the lobby server as the relay reaches it: an address or a name, **not a
  loop-back address** (the lobby server would then see every player at 127.0.0.1 and
  tell the others to look for them there). On the lobby server's own host give that
  host's network address. Run it beside the lobby server: gateway, lobby and discovery
  are expected at one address.
- **Mixed games need the relay's UDP sockets to be reachable from outside.** They are on
  every address of the host, on ports the system picks - or, with `--udp-ports
  LOW-HIGH`, in that range, which is then what a firewall has to let in (UDP, from
  anywhere; with `ufw`: `ufw allow 41000:41999/udp`). A session takes one port, 64
  sessions 64. The lobby server must see the relay at an address the application's
  players can reach, so `--lobby` is the lobby server's public address there. Behind a
  firewall that only lets answers in, a game of two still comes about where the lobby
  server named the player (the relay sends first and the answer comes back), but a third
  player and a player whose router changes ports are not reached.
- `--lan`: players on private addresses and on the relay's own computer are reached as
  well - for a relay on a home network, and for tests with everything on one computer
  (an application copy there is the one the lobby server saw at this computer's
  address). Without it such addresses are left alone, whoever names them.
  `--pages-only`: nothing passes to or from a player outside, as before mixed games.
  `--peer-rate N`: datagrams a second a page may send to one player outside (150).
- It listens on a loop-back address by default and speaks plain WebSocket. A page served
  over `https` may only open `wss://`, so put the web server that has the certificate in
  front and let it hand the connection on. For nginx:

  ```
  location = /some/path/relay {
      proxy_pass http://127.0.0.1:8975/relay;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header X-Real-IP $remote_addr;
      proxy_read_timeout 120s;
  }
  ```

  and beside the page a file `online.json` with `{ "relay": "relay" }` (the address
  relative to the page; see the README above for the other member).
- `--origin https://host` (may be given several times): only pages from there may use the
  relay. `--trust-proxy`: the player's address is taken from `X-Real-IP` when the
  connection comes from this host - give it when a web server is in front, or every
  player counts as one address.
- It needs no privileges and writes no files; what it has to say goes to standard output
  (one line when a session opens, one when a path to a player outside is opened or
  closed, one with its counts when it ends; never the content of anything). As a systemd
  service it can run as a dynamic user on a read-only system:

  ```
  [Service]
  DynamicUser=yes
  ExecStart=/usr/bin/python3 -B /opt/relay/relay.py --lobby 192.0.2.10 --origin https://play.example --trust-proxy --udp-ports 41000-41999
  Restart=always
  NoNewPrivileges=true
  ProtectSystem=strict
  ProtectHome=true
  PrivateTmp=true
  PrivateDevices=true
  RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
  ```

  (`AF_UNIX` is for Python's own event loop.) **No `IPAddressDeny=` / `IPAddressAllow=`
  lines**: a relay that may only talk to the host's own addresses (as the first version
  was set up, or with `--pages-only`) cannot reach a player outside. What it sends where
  is decided by the rule above, in the program. Restarting the relay ends every browser
  player's online session.

## Limits

| | Default | Option |
|---|---|---|
| sessions at a time | 64 | `--max-sessions` |
| sessions from one address | 4 | `--per-address` |
| largest message | 8192 bytes | `--max-message` |
| messages a second from one page (twice that for a moment) | 600 | `--message-rate` |
| bytes a second from one page | 262144 | `--byte-rate` |
| a page that says nothing at all (it pings every 15 s) | dropped after 60 s | `--silent` |
| a session with no connection to the lobby and nothing sent | closed after 900 s | `--idle` |
| TCP connections of one session / UDP sockets of one session | 4 / 8 | — |
| open paths to players outside, per session | 16 | — |
| datagrams a second to one player outside (twice that for a moment) | 150 | `--peer-rate` |
| datagrams and bytes a second arriving from outside for one session | as the page's own two rates | `--message-rate`, `--byte-rate` |
| largest datagram taken from outside | 1500 bytes | — |
| a path that hears nothing from outside | closed after 120 s | — |
| asking and hearing have to meet within | 30 s | — |
| an address stays named after the lobby server last named it | 300 s | — |

A datagram over the rate is lost, as on any line; anything else over a limit ends the
session with a notice the page shows. A session that was closed for idleness costs
nothing: the page connects again when the game next uses its network.

## Checking one

```
check.py --selftest
check.py wss://HOST/PATH/relay --origin https://HOST
```

`--selftest` starts a stand-in lobby server, stand-in players and relays of its own on
this computer and goes through everything above (30 checks: among them that a page
alone and a stranger alone open no path, that an address the stand-in lobby names is
reached and the own-network address beside it is not, what is read out of the lobby's
messages and what is not, and the three modes). Nothing leaves the computer. The second
form checks a running relay from outside without logging in anywhere: it opens two
sessions, asks for one TCP connection to the lobby server's gateway port and closes it
again without sending a byte, asks for destinations that must be refused (none of them
an address anything could be sent to), and times a message to the relay and back and a
datagram from one session to the other and back. It does not try a player outside: that
needs a game.

## The messages

One per binary WebSocket message, a byte of kind first, numbers big-endian; the table is
at the top of `relay.py`. The page's side is `../src/RtaWebNet.cpp` (the queues and the
socket calls) and `../web/rta-web.js` (the connection).
