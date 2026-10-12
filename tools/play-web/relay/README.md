# The relay of the browser build

A web page has no TCP or UDP of its own. A page of the browser build
([tools/play-web](../README.md)) therefore opens **one WebSocket connection** to this
program, and the console's network inside the page asks through it for what the desktop
application does with sockets of its own. The relay owns the real sockets:

| For the page's | the relay opens | to |
|---|---|---|
| two TCP connections (gateway, lobby) | one TCP connection each | the configured lobby server, the configured ports only (default 40810 and 40910) |
| UDP port (the game uses one of 4000–4004) | one UDP socket, kept for the session and used for every destination | the lobby server's discovery port (default 10101), **or** the UDP socket of another session of this relay |

So the lobby server sees a browser player as an ordinary player at the relay's address,
and hands that address and port to the other players. A datagram for another browser
player is handed from one session to the other inside the program; nothing that arrives
from outside on those sockets is passed on to a page. It is **not a proxy to anywhere**:
a page reaches the lobby server and the other pages, and that is all. (Browser players
play with browser players: see the README above.)

`relay.py` is Python 3.8 or later with the standard library only (the WebSocket
handshake and framing are written out in it), about 550 lines. Python because it is on
every server the lobby server runs on and on every developer's computer, needs nothing
installed, and the load is small: a few hundred small messages a second per game.

## Running it

```
relay.py --lobby 192.0.2.10                       # listens on ws://127.0.0.1:8975/relay
relay.py --lobby 192.0.2.10 --listen 127.0.0.1:8975 --path /relay \
         --origin https://play.example --trust-proxy
```

- `--lobby` is the lobby server as the relay reaches it: an address or a name, **not a
  loop-back address** (the lobby server would then see every player at 127.0.0.1 and
  tell the others to look for them there). On the lobby server's own host give that
  host's network address. Run it beside the lobby server: gateway, lobby and discovery
  are expected at one address.
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
  (one line when a session opens, one with its counts when it ends; never the content of
  anything). As a systemd service it can run as a dynamic user on a read-only system
  with the network limited to the host's own addresses:

  ```
  [Service]
  DynamicUser=yes
  ExecStart=/usr/bin/python3 -B /opt/relay/relay.py --lobby 192.0.2.10 --origin https://play.example --trust-proxy
  Restart=always
  NoNewPrivileges=true
  ProtectSystem=strict
  ProtectHome=true
  PrivateTmp=true
  PrivateDevices=true
  RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
  IPAddressDeny=any
  IPAddressAllow=127.0.0.0/8 192.0.2.10
  ```

  (`AF_UNIX` is for Python's own event loop.) Restarting the relay ends every browser
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

A datagram over the rate is lost, as on any line; anything else over a limit ends the
session with a notice the page shows. A session that was closed for idleness costs
nothing: the page connects again when the game next uses its network.

## Checking one

```
check.py --selftest
check.py wss://HOST/PATH/relay --origin https://HOST
```

`--selftest` starts a stand-in lobby server and a relay of its own on this computer and
goes through everything above (18 checks). The second form checks a running relay from
outside without logging in anywhere: it opens two sessions, asks for one TCP connection
to the lobby server's gateway port and closes it again without sending a byte, asks for
destinations that must be refused, and times a message to the relay and back and a
datagram from one session to the other and back.

## The messages

One per binary WebSocket message, a byte of kind first, numbers big-endian; the table is
at the top of `relay.py`. The page's side is `../src/RtaWebNet.cpp` (the queues and the
socket calls) and `../web/rta-web.js` (the connection).
