# The relay of the browser build

A web page has no TCP or UDP of its own. A page of the browser build
([tools/play-web](../README.md)) therefore opens **one WebSocket connection** to this
program, and the console's network inside the page asks through it for what the desktop
application does with sockets of its own. The relay owns the real sockets:

| For the page's | the relay opens | to |
|---|---|---|
| two TCP connections (gateway, lobby) | one TCP connection each | the configured lobby server, the configured ports only (default 40810 and 40910); whole lobby requests only, as many as the player's address may send ("Limits per player address" below) |
| UDP port (the game uses one of 4000–4004) | one UDP socket, kept for the session and used for every destination | the lobby server's discovery port (default 10101); the UDP socket of another session of this relay; a player outside, under the rule below |

So the lobby server sees a browser player as an ordinary player at the relay's address,
and hands that address and port to the other players. A datagram for another browser
player is handed from one session to the other inside the program - when that page wants
to hear from the sender: the lobby server named the sender to it, or it has itself sent
to the sender within the last 30 seconds. (Both hold in every game: the lobby server
names host and joiner to each other, and the game's players all send to each other when
they meet.) A page cannot make another page receive anything by itself.

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
handshake and framing are written out in it), about 1,350 lines. Python because it is on
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
  relay. (A browser says truthfully where a page is from; another program can say what
  it likes. It keeps other people's pages off the relay, nothing more.)
- `--trust-proxy`: the player's address is taken from `X-Real-IP` when the connection
  comes from this host - give it when a web server is in front, or every player counts
  as one address (four sessions in all, one allowance of everything). **The web server
  has to set the header itself**, as the `proxy_set_header X-Real-IP $remote_addr;` line
  above does: that replaces whatever the client sent under that name. Without that line
  nginx would pass a client's own `X-Real-IP` through, and every limit below could be
  walked around by writing a new address into each request. The relay reads the last
  value of the last `X-Real-IP` line and no other header (`X-Forwarded-For` is whatever
  the client wrote). Every program on the relay's own host can connect to it and claim
  any address: nothing but the web server should run there under other people's control.
- It needs no privileges and writes no files; what it has to say goes to standard output
  ("What it logs" below). As a systemd service it can run as a dynamic user on a
  read-only system:

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
  # the network: the web server on this host, the lobby server, and public IPv4 addresses
  IPAddressAllow=127.0.0.1 192.0.2.10
  IPAddressDeny=0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12
  IPAddressDeny=192.0.0.0/24 192.0.2.0/24 192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24
  IPAddressDeny=224.0.0.0/4 240.0.0.0/4 ::/0
  ```

  (`AF_UNIX` is for Python's own event loop.) For mixed games the relay has to reach
  players at any public address, so **not `IPAddressDeny=any`** as the first version
  had it (that, or `--pages-only`, is a relay for browser players only). The lines above
  are the tightest that still works: systemd lets a packet pass when its address is on
  the allow list, else stops it when it is on the deny list, else lets it pass - so the
  service reaches 127.0.0.1 (where the web server hands it the pages' connections), the
  lobby server's address, and whatever is in none of the denied ranges: public IPv4.
  Private, link-local (the address a cloud host's own metadata service has), loop-back
  other than 127.0.0.1, multicast and all of IPv6 are closed to it whatever the program
  does. The ranges are the ones the program itself leaves alone without `--lan`; a relay
  run with `--lan` cannot have these lines. A lobby server on a private or loop-back
  address goes on the allow list like any other. Restarting the relay ends every
  browser player's online session.

## Limits per player address

The lobby server sees every browser player at the relay's address. Its own limits per
address (its `SECURITY.md`) would treat all of them as one player - 16 connections, one
request budget, 40 password checks and 20 new accounts for everybody together - so an
operator will want the relay's address on the lobby server's `trusted_addresses` list,
which switches those limits off for it. **That is only safe with a relay that keeps the
same limits itself, per player.** This one does, with the lobby server's own numbers
unless told otherwise:

| per player address | default | option | over the limit |
|---|---|---|---|
| sessions at a time | 4 | `--per-address` | the session is not taken; notice 2 |
| new sessions | 12 at once, 12 more a minute | `--new-sessions` | the session is not taken; notice 8 with the seconds to wait |
| log-ins and account-detail requests - the two requests that check a password (lobby messages 0x16, 0x64) | 40 at once, one more every 3 s | `--login-burst`, `--login-every` | the request is **not passed to the lobby server**; the connection to the lobby server is closed; notice 8 with the seconds to wait |
| accounts created (0x06) | 20 at once, one more every 180 s | `--account-burst`, `--account-every` | the same |
| request budget: a request costs what the lobby server says it costs (1; a chat line 2; a character list 3; a game or room opened or a friend-list change 5; a log-in or a character download 10; an account 20; a character upload 33) | 400 units at once, 50 a second | `--request-burst`, `--request-rate` | the requests wait in the relay, in order, as they would wait at the lobby server; notice 8 once |

And per session: connections to the lobby server 8 a second (`--connect-rate`; a game
that cannot get through tries about five times a second), discovery datagrams 10 a
second and 256 bytes each.

How it counts. The length of a lobby request (four bytes, big-endian, counting
themselves) and its kind (the next two, little-endian) are not encrypted - the game
encrypts single text fields and nothing else (`docs/lobby-protocol.md` sections 2 and 4;
the lobby server's `LobbyServer::ProcessFrames` reads the same six bytes for its own
limits) - so the relay reads those six bytes of every request on both of a page's
connections and nothing after them. It keeps what a page sends until a request is whole
and hands the lobby server whole requests only, so a log-in counts however it arrives:
cut into single bytes, behind another request in one message, on a second connection or
from a second session. Something that is not a lobby request (a length under 4 or over
2,048, which makes the lobby server close the connection) is not sent on at all.

The allowances belong to the address, not to the session: a page that connects again
finds them as it left them. An address is forgotten when nothing of it is open and every
allowance is full again (4,096 addresses are kept at most; when that many still owe
something a newcomer is turned away, never an allowance handed out afresh). An IPv6
player counts by its /64.

**What an operator must set** for a relay that anybody can reach:

1. `--trust-proxy`, and in the web server `proxy_set_header X-Real-IP $remote_addr;`
   (above) - or all players are one address.
2. `--origin`, `--udp-ports` and the firewall for that range (mixed games).
3. On the lobby server, `trusted_addresses=<the address the relay connects from>`, **in
   the same step as this relay and never before it**: with an older relay behind it that
   line gives every page unlimited password guesses and accounts. The lobby server's
   limits that are not per address (512 connections in all, 2,048 bytes a request, one
   game and one room per session, the size of the database) hold for the relay as for
   everybody.
4. Nothing: the numbers above are the lobby server's own. Smaller ones are safe; larger
   ones give a page more than the lobby server gives a player who connects directly.

## What it logs

Standard output only, one line each: its settings and limits at the start; a session
opened (the player's address) and ended (why, and its counts: connections, bytes,
datagrams, paths, requests passed on, made to wait and refused); a path to a player
opened or closed (that player's address and port; the first 64 of a session); a
destination that was refused (the address and port a page asked for; the first 8 kinds
of a session); a log-in or an account over the allowance, and a session that was not
taken (one line a minute per address, with the number left out). **Never the content of
anything**: no request, no datagram, no header, and not the path a page asked for. The
relay does not decrypt anything and holds no key. Players' addresses are personal data:
how long the system keeps the service's output is the operator's choice (`journalctl`
keeps it until its own limits).

## Limits

The limits per player address are in the section before this one. The rest:

| | Default | Option |
|---|---|---|
| sessions at a time | 64 | `--max-sessions` |
| largest message | 8192 bytes | `--max-message` |
| messages a second from one page (twice that for a moment), pings and their answers included | 600 | `--message-rate` |
| bytes a second from one page | 262144 | `--byte-rate` |
| what may wait for a page that is slow to read: its datagrams are dropped above / its session is ended above | 256 KiB / 1 MiB | — |
| requests of one lobby connection that may wait in the relay | 128 KiB | — |
| largest lobby request (the lobby server's own limit) | 2048 bytes | — |
| largest datagram a page may send a player | 1500 bytes | — |
| connections that have not finished the WebSocket handshake | 64 | — |
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

A datagram over the rate is lost, as on any line; anything else in this table over its
limit ends the session with a notice. A session that was closed for idleness costs
nothing: the page connects again when the game next uses its network. A session holds
at most 13 open files (its own connection, 4 to the lobby server, 8 UDP sockets): the
relay raises its own limit of open files to what `--max-sessions` needs when it may, and
says so at the start when it may not. `--udp-ports` wants 8 ports a session to be safe
from a page that takes all it can (the default 64 sessions: 512; a game takes one).

## Checking one

```
check.py --selftest
check.py wss://HOST/PATH/relay --origin https://HOST
```

`--selftest` starts a stand-in lobby server, stand-in players and relays of its own on
this computer and goes through everything above (57 checks: among them that a page
alone and a stranger alone open no path, towards a player outside or towards another
page; that an address the stand-in lobby names is reached and the own-network address
beside it is not; what is read out of the lobby's messages and what is not; the three
modes; and every limit per player address - that it is the address's and not the
session's, that another address is not affected, that a forwarding header a client
writes itself does not help, that a log-in counts however it is cut up, that the
stand-in lobby never sees what was refused, and that nothing a page sent is in a
relay's log). In those checks the test plays the web server in front: it says in
`X-Real-IP` who the player is. Nothing leaves the computer; it takes about half a
minute. The second
form checks a running relay from outside without logging in anywhere: it opens two
sessions, asks for one TCP connection to the lobby server's gateway port and closes it
again without sending a byte, asks for destinations that must be refused (none of them
an address anything could be sent to), and times a message to the relay and back and a
datagram from one session to the other and back. It does not try a player outside: that
needs a game.

## The messages

One per binary WebSocket message, a byte of kind first, numbers big-endian; the table is
at the top of `relay.py`. A NOTICE carries a code and a sentence: 1 the relay is full,
2 too many pages from the address, 3 idle, 4 not the relay's messages (or not a lobby
request), 5 a destination that is not allowed, 6 more data than a game sends, 7 the
relay is stopping, 8 a limit of the player's address. The page puts 1, 2 and 8 on the
screen and all of them into its log (a page built before 2026-10-12 evening: the log
only). The page's side is `../src/RtaWebNet.cpp` (the queues and the
socket calls) and `../web/rta-web.js` (the connection).
