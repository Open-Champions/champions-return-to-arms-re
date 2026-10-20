# Our own way into an online game: rendezvous, friends, direct launch

Started 2026-10-13. The owner looked at the "SOEGAMES.NET Login" screen and asked: "do we
actually need this connector or can we make our own internal engine" - and then: "Build a
new sick as portal thats easy and plug and play with friends list, etc their character
name". This file is the work behind such a portal for the NATIVE build: a small service of
our own (identity without accounts, friends, presence, invitations, rooms by code, UDP
hole punching and relay), the client library the portal's screens call, and a direct start
of the game's own lockstep session with no lobby screen. The old lobby path stays for
compatibility and is not touched. Every result says whether it was **Ran** or only
**Read**. The portal's screens are another agent's (`docs/issues/native-portal.md`).

## STATE (rewritten at every step; read this first after a stop)

**2026-10-20 14:50. Two networks: done.** Two computers in two different places - one at
home, one away on another provider's network - played one game through the service on
the project's server: the routes were punched straight through both routers (about 50 to
85 ms), and with the relay forced the server carried the game; every run in step through
a level change. Section "Two networks" below.

**2026-10-14 03:15. TLS: done on this Mac, prepared for the server.** The TCP conversation
goes inside TLS on both sides (the service with Python's `ssl`; the client with the
operating system's TLS - macOS run, Windows compiled only), the service was reviewed for
strangers and got the cheap fixes, and the server's unit and steps are prepared, not run:
[native-rendezvous-tls.md](native-rendezvous-tls.md). Once it is switched, players name the
service by its host name, not its address.

**2026-10-14 02:20. The service runs in public.** At the owner's word ("Make sure online
works") it runs on the project's server beside the lobby: systemd unit `champions-net2`
(no fixed user, state in its own directory, the same sandbox as the browser relay), TCP
and UDP port 41900 open. **Ran**, from this Mac through that server, with
`n2party.py --external`: two copies 2,104 ticks in step (the punch failed - two copies
behind one home router that does not loop back - and the relay carried the game, as
designed); three copies with every route forced through the relay, every pair in step for
about 2,000 ticks. Still not done then: TLS (section 8; since 03:15 done here, not yet on
the server), two computers in two homes, the Windows program in the game. The client's built-in default stays empty: the address is
given with `--service`, `RTA_NET2_SERVICE` or `net2-service.txt`.

**2026-10-13 23:10. Done and run, game side included.** Two, three and four native copies
get into one game through the service with no lobby screen, stay in step, change level,
survive a dropped player and a dropped host, play a second game in the same processes and
room, over punched routes (loop-back and this Mac's LAN address) and over the relay, and
under the service's limits. Section 6 has the table.

| Part | Where | State |
|---|---|---|
| the service | `tools/rendezvous/rendezvous.py` | **Ran**: `check.py` 189 of 189 (after the repair of 19:35, again); with TLS and the exposure fixes 225 of 225 (2026-10-14 03:15) |
| the client interface and its mock | `tools/recomp/net2/session.h`, `session_mock.cpp` | **Ran**; the portal is built on it |
| its real body | `session_net.cpp`, `carrier.cpp`, `tls.cpp`, `hash.h`, `cardchars.cpp`, `clicmd.cpp` | **Ran**: `check_client.py` 95 of 95 (after the last change of `carrier.cpp`, again); with TLS 118 of 118 (2026-10-14 03:15) |
| the direct launch | `launch.cpp`, `game.h`, `hooks.h` | **Ran**: 34 games of 2 to 4 copies launched and compared, section 6 |
| `net2.patch` | `tools/recomp/net2/net2.patch` | nine lines in `net/netdrv.cpp`, seven compile jobs in `app/build.py`; dry run clean against today's files; the runs used exactly these lines. **Not applied** to the shared tree (the owner of `net/` and `app/` merges) |
| `proposed.pnach` | - | does not exist: no word of the game had to be patched |
| the stand-alone program | `play.sh`, `--opt net2=...` | **Ran** with the window program off-screen as host and a headless joiner (pictures `local/recomp-net2/win/pictures/`) |
| the proof driver | `n2party.py`, `local/recomp-net2/series.sh` | **Ran** |

Builds: my snapshot of the native build taken 2026-10-13 19:44 (the objects of
`rta_app_next`, after the move), `local/recomp-net2/build.sh`. Nothing of this work is
running; nothing listens.

Damage of 19:31 (a copy tool of the move put six of my files back to the last commit and
some local files to their state before the move): repaired; nothing was lost for good.

## 1. What a lockstep game needs at its start, and what the lobby adds

Read from the game's code unless it says Ran. Addresses are the executable's.

### 1.1 What the game needs

| Thing | Where it lives | Who decides in a lobby game | In the developer's LAN start (`--net`) |
|---|---|---|---|
| how many players, and which number I am | count 0x402a37, own number 0x402a39, host's number 0x402a38 (always 0: `frontend_startNetGame` 0x1e21e0 writes 0 on both of its branches) | lobby state 7 (0x324288): from this machine's table of the room's players, the host is the lowest ident | the order of the machines' addresses (highest last octet first) |
| every player's address and port | two tables of four: addresses 0x402b3b and 0x402b4b (bytes a, b, c, d in memory), ports 0x402b5c and 0x402b6c | state 7 fills the FIRST pair from the live connections of SOE's peer library, never the second (the hole of `three-players.md`) | discovery by broadcast on port 4000; fixed 192.168.1.x |
| the launch handshake | `net_launchTransfer` 0x134c60 prepares it, `net_launchUpdate` 0x135638 runs it every frame while 0x402793 is set (`frontend_run` 0x1e08f0 polls it) | the same code | NOT run: `net_debugLanLobby` 0x1345c0 goes straight to the level |
| each player's character | the local player's record is `g_players[0]` (0x4d8af0, 0x4c30 bytes) while the front end is up, with a 0x2c-byte summary at 0x4fdb80; the handshake sends it to every other machine (types SIZE / DATA: the whole record, or the summary for a character just made - bits 4 and 2 of 0x402a30) and each machine puts it at that player's number | the game's character screens in the room: made new, taken from the server's list, or imported from the memory card | none: one placeholder per machine ("Toonces", "Otis"), made by `player_initNewCharacter`; the soak farm writes statistics into them in a lockstep tick |
| level | the handshake's end writes the pending level 0x41b6d0 = `game_getHubName()` 0x1ec300 ("hub", or "hub2" for an evil party) or the arena for versus | the game | `strife` (set by `main` for `--net`) |
| difficulty, mode, mission, kill limit | 0x402a32, 0x402a33, 0x402a34, 0x402a35; the HOST's travel in its SHAKE block (0x402c30..) and every machine takes them at the end (0x137434 onward: `g_difficultyIdx`, the versus flags, 0x4f8408) | the host's room form | fixed (difficulty 1) |
| random seed | `net_startSync` 0x13dce0 sets the shared seed `g_randSeed` to 0 at the start of every net game | nobody: always 0 | the same |
| button configurations, voice flags | in every player's SHAKE block, installed per player at the end (0x41b980..) | each player | the defaults |
| who is in step | the game's own sync hash per tick (seed + player positions), compared between machines (`docs/netcode.md`) | - | - |
| a player dropping | silence for 900 calls starts the kick negotiation, the others stand still about 24 s and go on without it; leaving by the pause menu is at once (`docs/netcode.md` "Drop", `native-online.md`) | the same code in every kind of game | the same |
| "the fix-set figure check" | NOT in the game. It is this project's own: the network layers tell each other a figure for the set of fix words (FNV-1a) and warn when two copies differ | the lobby driver's mark after a keep-alive (`netdrv.cpp`) | nothing |

So a game needs, from outside itself: **the list of players in order, an address and port
for each, which one I am, the host's options, and my character in `g_players[0]`.**
Everything else it does itself, between the machines.

### 1.2 What the lobby adds

| The lobby does | Kept, replaced or dropped here |
|---|---|
| an account: name, password, e-mail, date of birth | **dropped.** A device secret in one file is the player (section 3.1) |
| finding each other across the Internet: the server tells each machine the others' observed address and port (notification 0x65), SOE's peer library connects them, START goes over it | **replaced**: the service tells every machine the others' observed UDP address; the carrier punches; a relay is the fallback (the lobby has none: two players behind one router that does not loop back never connect there) |
| a list of open games, private games found by name | **replaced** by a room code, and by "my friend is in a room - join" |
| chat in the lobby and in a game's room, private messages | room chat **kept** (lines, 120 bytes). Lobby-wide chat and private messages: **not built** |
| friends and ignore lists, kept by the server by account | **replaced**: friends by friend code, block list, presence with the character played, invitations, recent players |
| characters stored on the server (kind 2), saved there every few minutes (request 0x5E), offered at the next log-in | **dropped**: the character is the player's own, on the player's memory card (kind 1) |
| the character checksum exchange every 240 ticks | only runs when the game was launched from the lobby AND every character is server-stored (`net_allPlayersState2` 0x1ec5d8); it compares each machine's live record with the same machine's save-buffer copy - a consistency check between machines, not a check against the server. **Off** in a direct launch, as in any game with a memory-card character |
| the server-stored character cannot be saved to a card (script `saveGame` and the save point refuse) | in a direct launch save points work: the game writes the local player's character to the local card (`save_packLocalPlayer`), which is how progress is kept |

### 1.3 Characters, plainly

- A player brings the character chosen on the game's own character screens before the
  launch: made new there, or "Import" (triangle on the first page) from a saved game on
  this machine's memory card. The record goes to the other machines whole.
- **What stops a player from bringing an edited character: nothing.** The record is taken
  as it is sent. `player_importCharacter` caps level 50 and the experience table on
  import from a card; a record edited in memory before the launch passes no check at all.
  The lobby did not check either (its server stored what a client sent). This is a game
  among friends.
- What a host COULD check, not built: after the launch every machine holds every record -
  level against experience, statistic points against level, skill points against level,
  item rows inside the item table - and could refuse to start or show "this character
  does not add up". It would be advice, not enforcement: the other side runs the same
  program and can edit that too.

## 2. The design in one page

```
 portal screens (Godot)  or  the stand-alone program's command line
            |  session.h (plain C, non-blocking, one poll)
            v
   +--------------------+        TCP, lines of text         +------------------------+
   | session_net.cpp    | <-------------------------------> | rendezvous.py          |
   | identity, friends, |        UDP: hello / seen          | players, friends,      |
   | rooms, start       | <-------------------------------> | presence, rooms,       |
   +---------+----------+                                   | observed addresses,    |
             | carrier.cpp: one UDP socket                  | relay                  |
             |   probe / answer  <--- straight --->  other players' carriers         |
             |   relay  -------------------------------->   (only within a started   |
             v                                               room, rate-limited)     |
   launch.cpp: the game's datagrams on port 4000 go through the carrier;
               the game is told player k is 10.77.0.(k+1):4000
             |
   the game's own launch handshake and lockstep netcode, unchanged
```

- **The game never sees a real address.** On every machine player k is 10.77.0.(k+1),
  port 4000. `launch.cpp` carries the game's datagrams for those addresses over the
  carrier's routes. The game's launch code can therefore not mistake one player for
  another by address, the "this is my own outside address" branch of `net_launchUpdate`
  is never true (the cause of the three-player failure in the lobby), both address tables
  are filled, and a route may be a relay without the game knowing.
- **The start is the game's own.** `launch.cpp` does what the game's own developer menu
  does on the way to a net game without a lobby (section 5); the handshake that carries
  the characters and the options is the game's.

## 3. The service (`tools/rendezvous/rendezvous.py`)

Python, standard library only (`selectors`, `sqlite3`, `hmac`, `hashlib`, `secrets`). One
process, one thread. One port number for TCP (the conversation) and UDP (hello, relay).

### 3.1 Identity without accounts

- The client makes 32 random bytes on its first start - the **device secret** - and keeps
  them in `<data>/net2-identity.key` (mode 0600, 205 bytes). **That file is the player.**
  Moving to another computer = copying that one file into the data folder there. Losing
  it = a new player (the friends have to be asked again).
- The service never gets the secret. At registration it gets
  `verifier = HMAC-SHA256(secret, "rta-net2 verifier v1")` and derives the player id from
  it (the first 16 bytes of `SHA-256("rta-net2 id v1" + verifier)`). Every later
  connection is proven with `HMAC-SHA256(verifier, nonce + "login")`, the nonce being 16
  random bytes the service sends when the connection opens and uses once.
- **Why not a key pair, as asked:** neither Python's nor C++'s standard library has a
  public-key signature, and none is written here. The client takes SHA-256, HMAC and its
  random bytes from the operating system (CommonCrypto on macOS; CNG on Windows -
  compiled never, run never). What this buys and what not: a proof read off the wire is
  worthless (nonce); but whoever reads the REGISTRATION on the wire, or the service's
  file, holds the verifier and can log in as that player. So: when the service runs in
  public its TCP port belongs inside TLS (section 8; built 2026-10-14,
  `native-rendezvous-tls.md`), and what the identity guards is a
  display name and a friends list. The secret (not the verifier) stays the root, so the
  same file can seed a real key pair the day the platforms' signature functions are used.
- A player has a **display name** (3 to 24 bytes, any text, changeable, a label: two
  players may have the same) and a **friend code** the service makes at registration:
  eight characters shown as `K7QF-2MXD`, from an alphabet without I, O, 0 and 1.

### 3.2 What the service stores, and for how long

On disk, one SQLite file (`<data>/rendezvous.db`, mode 0600), five tables:

| Table | Columns | Kept |
|---|---|---|
| `players` | id, verifier, display name, friend code, created (time), last seen (time), the character label last published: name, class, level | until the player deletes it, or 400 days after it was last seen |
| `friends` | player, player, since | until one side removes, blocks or is deleted |
| `requests` | from, to, when | until answered, taken back, or 30 days |
| `blocks` | player, blocked player, when | until unblocked or deleted |
| `recent` | player, a player it was in a game with, when | the 50 newest per player, 90 days |

**Not stored anywhere on disk:** addresses (IP or port), chat lines, room codes, rooms,
invitations, presence, the device secret (never received), e-mail, anything else. In
memory only, gone when the process ends: connections and their addresses (for the limits
and the hole punching), rooms with their last 32 chat lines, invitations, who is online.
The log has times and counts only.

`delete` (`net2_delete_everything`) removes the player's row and every row of the other
four tables that names it, tells the players who had it as a friend that the entry is
gone, and closes the connection; the client deletes the identity file and starts again as
a new player. **Ran** (both self-tests).

### 3.3 The conversation (TCP)

Lines of UTF-8 text ending in `\n`, at most 1,024 bytes. A line is a verb and
`key=value` fields separated by single blanks; in a value every byte outside
`A-Z a-z 0-9 . _ ~ - , :` is written `%XX`. A request carries `n=<number>`; the answer is
`ok n=<number> ...` or `err n=<number> code=<negative number> text=<words>`. Lines
without `n` are news. `bye code= text=` precedes a close by the service.

| Client says | Fields | Service answers / does |
|---|---|---|
| (connects) | | `hi v=1 nonce=<32 hex>` |
| `register` | `v=1 verifier=<64 hex> name=` | `welcome ...` (new player); refused for a known verifier |
| `login` | `id=<32 hex> proof=<64 hex>` | `welcome id= name= code= udp=<16 hex> new= cname= ccls= clevel=`, then the lists (`friend`, `request`, `blocked`, `recent` lines), then `synced`; `bye code=-5` for an unknown id (the client then registers), `-7` for a wrong proof |
| `ping` | | `ok` (clients ping every 20 s; 90 s of silence closes) |
| `name` | `name=` | `ok name=` |
| `char` | `name= cls= level=` | the character label, passed to friends and rooms |
| `copy` | `fix=<8 hex> words= can= does=` | what this copy of the game is: shown to the room |
| `local` | `eps=ip:port,...` | this machine's own addresses of its UDP socket (for two players behind one router) |
| `game` | `level=` | presence outside a room |
| `fadd` | `code=` or `id=` | a request; `ok friends=1` when the other side had asked already |
| `faccept` `fdecline` `fremove` `block` `unblock` | `id=` | |
| `invite` `idismiss` | `id=` | the friend gets `invite id= name= room= players= cname= ccls= clevel= when=` |
| `host` | `level= diff= mode= mission= kills= open=` | `ok code=<5>`, then the room |
| `join` / `joinf` | `code=` / `id=` (a friend) | `ok code=`, then the room |
| `chat` | `text=` | everybody in the room gets `chat n= from= text=` |
| `ready` | `v=0|1` | |
| `opts` `kick` `start` | host only | |
| `gstate` | `v=1 level=` / `v=0` | my game runs / is over; the room opens again when every machine's is over |
| `leave` | | |
| `delete` | | `deleted`, then the connection is closed |

News: `friend id= name= code= p=<0 offline,1 online,2 in a room,3 in a game> room= join=
players= level= since= seen= cname= ccls= clevel= inv=`, `unfriend`, `request id= name=
code= in= when=`, `unrequest`, `blocked`, `unblocked`, `recent id= name= code= when=
friend= asked= cname= ccls= clevel=`, `unrecent`, `invite`, `uninvite`, `notice text=`,
and the room, always whole: `room code= state=<open|started|none> slot= host=0 count=
level= diff= mode= mission= kills= open=`, one `member slot= id= name= ready= phase= fix=
words= can= does= cname= ccls= clevel= friend=` per player, `roomend`.

The start, to every machine of the room:

```
start session=<8 hex> count=<n> slot=<mine> host=0 seed=0 level= diff= mode= mission= kills=
peer slot=0 id= name= eps=<observed ip:port>,<its own ip:port>,... cname= ccls= clevel=
peer slot=1 ...
startend
```

The same on every machine but for `slot` and the `eps` of oneself (empty). Slot 0 is the
host; slots are the order of joining and close up when somebody leaves, so the host that
leaves hands the room to the next player. **Ran**: every field compared between four
clients.

### 3.4 Datagrams (UDP, the same port)

Eight bytes in front of everything: `'N' '2' kind slot session(4, little-endian)`.

| Kind | From, to | After the head | Meaning |
|---|---|---|---|
| 0x20 HELLO | client to service | key(8) from `welcome udp=` | "this is my game socket": the service notes the address it came from, answers |
| 0x21 SEEN | service to client | ip(4) port(2) | "this is how I see you" (14 bytes for a 16-byte hello: nothing to amplify) |
| 0x02 PROBE | player to player | nonce(8); slot = the sender's | hole punching: sent to every candidate address every 200 ms |
| 0x03 ANSWER | player to player | the nonce | the route works; the round trip is measured |
| 0x01 GAME | player to player | the game's own datagram; slot = the sender's | |
| 0x10 RELAY | client to service | key(8), then the game's datagram; slot = the player it is for | |
| 0x11 RELAYED | service to client | the game's datagram; slot = the sender's | |

Routes, per pair: probes go to the address the service saw and to the addresses the other
machine says are its own; the first answer makes the route **straight**. Until then, and
for good after 2.5 s without an answer, the game's datagrams for that player go through
the **relay** - the game never waits for the punching. A straight route found later is
taken (since 2026-10-14 a hello counts only from the IP address of its player's own TCP
connection: the key travels in every datagram, `native-rendezvous-tls.md` section 1). `net2_set(n, "relay", "force")` makes a machine neither probe nor answer (its
pairs stay on the relay): **Ran** with one of three clients forced, datagrams both ways
on both kinds of route.

The relay passes a datagram only when all of this holds: the key belongs to a logged-in
connection; that player is in a room whose game was started, with this session number;
the datagram comes from the address that player's hello was seen at; the slot names
another member; that member has said hello within 60 s (it goes to that address and
nowhere else); the sender is under its rate. Otherwise it is dropped and counted;
nothing is ever answered to an address that did not send a valid hello. **Ran**: each
refusal, one by one (`check.py`).

### 3.5 Limits (all in `LIMITS` at the head of the file; `--limit NAME=VALUE`)

| What | Value | Hit on purpose in `check.py` |
|---|---|---|
| connections: all told / from one address | 2,000 (and below the process's file limit) / 12 | yes (7th of 6; 33rd with 96 files) |
| new connections from one address | 60 a minute | yes |
| a line; lines per connection | 1,024 bytes; 20 a second sustained, 60 at once | yes, both: closed with a reason |
| time to log in; silence | 10 s; 90 s | yes (1 s, 2 s) |
| new players from one address; from everywhere | 10 an hour; 1,000 an hour | yes |
| wrong proofs from one address | 10 a minute (counted; the player is not locked out) | yes |
| name; character name, class, level name | 24 bytes each | yes (cut, cleaned) |
| friends per player; unanswered requests; requests | 200; 20; 10 an hour (guessing codes counts) | yes |
| unanswered requests TO one player | 100 | yes |
| name, character, copy, own addresses, level (told to friends and the room) | 1 a second, 10 at once | yes |
| blocked players | 500 | yes |
| invitations | 30 an hour, the same friend every 10 s, gone after 10 min | yes |
| rooms: all told / made from one address | 5,000 / 4 | yes |
| players in a room | 4 (the game's) | yes |
| wrong room codes from one address | 10 a minute, then that connection is closed (32^5 codes) | yes |
| chat | 120 bytes a line, 1 a second, 5 at once; the room keeps 32 | yes |
| a room nothing happens in; a started game | closed after 2 h; 12 h | yes (2 s) |
| hello from one address | 10 a second; only from its player's TCP address | yes |
| an observed address | forgotten 60 s after the last hello | yes |
| relay per player | 150 datagrams a second (300 at once), 256 kB a second, 2,064 bytes each | yes |

A lockstep game sends one input datagram every second frame per machine (30 a second in
all, `docs/netcode.md`) plus the launch's chunks; 150 a second per player leaves room for
four players and a fast-forwarding test.

### 3.6 Running it

```
python3 tools/rendezvous/rendezvous.py --data local/rendezvous-data            # 127.0.0.1:41900
python3 tools/rendezvous/rendezvous.py --data DIR --bind 127.0.0.1 --bind 192.168.1.123 --port 41900 --status-every 60
python3 tools/rendezvous/rendezvous.py --data DIR --bind ADDRESS --tls-cert CHAIN.pem --tls-key KEY.pem    # in public: TLS
python3 tools/rendezvous/check.py -v            # the service's self-test (starts its own, loop-back, 25 s)
python3 tools/rendezvous/check_client.py -v     # the C++ client against a service (builds net2cli, loop-back, 22 s)
```

`--bind 0.0.0.0` is refused unless `--public` is given; an address that is neither
loop-back nor private is refused without TLS unless `--plain` is given.

## 4. The client (`tools/recomp/net2/`)

| File | Is |
|---|---|
| `session.h` | the interface: plain C, nothing blocks, `net2_poll()` once a frame, events and snapshots. Me (id, name, friend code, link), friends with presence and character, requests, recent players, blocked, invitations, a room (members, ready, options, chat, fix-set warning, routes), the start (`net2_session`), `net2_delete_everything`, `net2_local_characters` |
| `session.cpp` | checks of what is typed, snapshots, the one lock, where the service is found |
| `session_mock.cpp` | the mock (`config.mock = 1`): everything made up locally, for building screens |
| `session_net.cpp` | the body that talks to the service; identity file; reconnects by itself |
| `tls.h/.cpp` | the TCP link inside the operating system's TLS (`native-rendezvous-tls.md`) |
| `carrier.h/.cpp` | the UDP socket: hello, probes, routes, the game's datagrams, the relay |
| `hash.h` | SHA-256, HMAC, random bytes from the operating system |
| `cardchars.cpp` | "characters I have": name, class, level from the save slots of a card folder (layout of `docs/audio-save.md`); needs no game. **Ran** against files the test makes to that layout; no real save slot was at hand (none of the test cards has one: a character is on a card once a player has saved at a save point) |
| `clicmd.cpp`, `net2cli.cpp` | the interface as lines of text: on a terminal (`net2cli --mock`, or `--service HOST:PORT --data DIR`), and in the stand-alone program as `app net2 <the same commands>` |
| `game.h`, `launch.cpp`, `hooks.h` | the direct launch (section 5); only in a program that contains the game |

**How a player gets into a game** (the steps a person takes; the stand-alone program):
one starts `tools/recomp/net2/play.sh --disc IMAGE --play-host` and reads "ROOM CODE
H4KQ7" to the others; they start `play.sh --disc IMAGE --play-join H4KQ7`. On every
machine the game boots to its title screen by itself and shows its own character screens:
make a character, or press triangle ("Import") for one saved on this machine's memory
card. When everybody has one, the host's game starts for all. With the portal the same
happens behind its screens, plus friends, invitations and a start button.

For a portal without the game: compile `session.cpp session_mock.cpp cardchars.cpp`
with `-DNET2_NO_SERVICE` (mock only), or add `session_net.cpp carrier.cpp` (the service
too; includes `../net/sock.h`). C++17, no other dependency.

**Where the service is found** (`net2_config.service` empty): the environment variable
`RTA_NET2_SERVICE`, then the first line of `<data>/net2-service.txt`, then the built-in
default `NET2_DEFAULT_SERVICE` in `session.cpp` - empty today, because where the service
runs is the owner's decision; until then the link says OFF and `net2_me().problem` says
"No service was named." **Ran**: each of the three, and none.

**Threads.** Every call of `session.h` takes one lock, and so do the game-side hooks; a
portal may poll from its own thread while the game runs on others.

**What a host may choose** (`net2_options`, for the portal's room screen):

| Field | Values | From |
|---|---|---|
| `difficulty` | 1 easy, 2 normal, 3 hard, 4 harder - the game's four, menu keys `menu_easy2`, `menu_normal2`, `menu_hard2`, `menu_harder2` (table 0x4f6e38; the words shown are in the game's text lump). 0 = normal. The game itself lets a host take only what its memory card has unlocked (`options_get4f8f38Level` 0x1ec448) | Read |
| `mode` | 0 play missions (the campaign), 1 arena co-operative, 2 arena versus (`menu_playmissions`, `menu_arena_coop`, `menu_arena_vs`, table 0x4f6c28) | Read |
| `mission` | mode 0: 0 = from the hub; 1..13 = `menu_mis1` .. `menu_mis13`, of which the game offers a host those its progress has opened (0x1ec520) | Read; how the value travels is not run |
| `kill_limit` | mode 2: 5, 10 or 25 | Read |
| `level` | "" = the game's own first level (the hub). Any name of the game's level table (90 names, `g_levelTable` 0x4f7210, e.g. `drunare`): every machine replaces the pending first level with it before anything is loaded - a jump for tests and for "start in the arena" | written, not run |
| `open_to` | by code only / my friends may walk in | Ran |

Only mode 0, difficulty and `level` are wired into the launch so far.

## 5. The direct launch (`launch.cpp`)

**Can the LAN start be entered from the title screen at run time, or only at boot? At run
time.** The boot argument `--net` is one of three developer paths (`docs/issues/live-rig.md`
4d); the third is a menu branch the retail menu cannot reach: `frontend_run` state 1 with
any key but the two retail ones clears the net settings block and shows a host / client
menu (state 6), which starts the game's character screens and then calls
`frontend_startNetGame` with the lobby state 0 - the launch handshake a lobby game uses,
between four fixed addresses. `launch.cpp` does what that branch does, from the game's
main thread, with the tables written from the room. No word of the game is patched.

| Step | What is done | Game code it stands in for |
|---|---|---|
| wait | the game is at its title screen: front end, state 0, lobby state 0, menu faded in, the front end's first pass made (0x4f6b70 = 0); stable for a second | - |
| choose | clear 0x402a30 (0x14c bytes); net flag 0x4f70a0 = 1; difficulty 1; host bit; 0x86ad54 -> 0x4fbbe2; front-end state 10; call `frontend_startPlayerSelect` 0x1e3ba0 | `frontend_run` states 1 and 6 (0x1e08f0) |
| chosen | the task `playerSelection` has ended (asked with the game's own `task_isRunning` 0x19e5e8) and 0x4fbbe2 is 1: the character is in `g_players[0]`; name, class, level are read for the room | state 7's test |
| launch | 0x402a3a = 0xff; bits of 0x402a30: host, and 2 or 4 by the kind of character (0x4fdba9 & 3); host: difficulty, mode; 0x402793 = 1, 0x402792 = 0; calls 0x19d8a4(10), 0x19d028, `net_gameInit(0)`; `g_lobbyLaunch` = 0; count, host 0, own number; both address tables = 10.77.0.(k+1), both port tables = 4000; `net_launchTransfer` | state 7 and `frontend_startNetGame` 0x1e21e0 |
| handshake | nothing: `frontend_run` polls `net_launchUpdate` every frame; its datagrams on port 4000 go through the carrier (`hooks.h`: `udp_owns`, `udp_send`, `udp_receive` in `netdrv.cpp`) | the game's own |
| launched | 0x402793 back to 0 with `g_networkMode` 1: the game has set the level; `options.level`, when given, replaces the pending name in the same pass (before the main loop loads anything) | - |
| over | back in the front end with the network mode off: the session's datagrams stop, the room is told, the machine is at the title screen again and can choose and launch again | - |

Front-end state 10 is "waiting for the lobby": with the lobby state 0 the front end draws
its background and does nothing, and it still polls the launch.

**Ran** (section 6): every step of the table. The launch handshake takes 211 or 212
vertical blanks (3.5 s) from `net_launchTransfer` to "launched", the game's own "Network
Game Launch" screen shows every player's character, level and "Ready!", and the first
level is the hub. What was learned on the way:

1. A choice made in the title menu's first frames finds the character screens' data not
   loaded (the screens come up and take no button): the menu must have stood for a
   second, at boot and again when a game is over.
2. After a net game the character screens take two leftovers of it: `g_numPlayers`
   0x4d8ae0 (the number that was in the game: the screens then wait for a second
   controller) and `g_difficultyIdx` 0x4f719c (above the first difficulty they take only
   an imported character). Both are set to 1 before the screens are started. That is
   what power-on has; the host's difficulty is applied by the handshake as before.
3. The task `playerSelection` ends by itself once a character is chosen; the front end
   is back at the title screen after a net game that was not started from the lobby;
   the pause menu's "Exit Game" is where it is in a lobby game.
4. A character just made is a summary until the launch builds its record: its class is
   known to the room once the game runs (the label said "Barbarian" for an Iksar before).
5. Hole punching through this Mac's LAN address failed at first and every pair went to
   the relay: an answer came back after the next probe had gone out (the first packets
   of a new path were slower than 200 ms) and was thrown away. Fixed in `carrier.cpp`
   (the last 16 probes are remembered); since then those pairs are straight too.

The developer path is reached from the title screen at run time: no boot argument and no
restart are needed, and a second game follows in the same process.

Why not the boot argument: `--net` skips the front end - placeholder characters, level
`strife`, no handshake, discovery by broadcast on 192.168.1.x, and only at boot. Its
netcode is the same; its start is the wrong one for players.

### 5.1 For the Godot side (a note; nothing under `tools/godot/` was edited)

- **One copy of net2 in the process.** Compile `tools/recomp/net2/*.cpp` once, into the
  library that contains the game, and let the extension call its plain-C functions.
  Two copies (one in the extension, one in the game library) would be two locks and two
  sets of state.
- The game library needs the network driver it does not link today
  (`tools/recomp/net/netdrv.cpp` with the nine lines of `net2.patch`, `online.cpp`,
  `RtaOnline.cpp`, and the translation made with `--hle-add net/hle-online.txt`, as
  `rta_app` has it) plus `net2/launch.cpp` and the session files.
- After `net2_open`: `net2_game_attach(n)` once. From then on `launch.cpp` follows that
  object's room: it publishes the chosen character (`net2_set_character`), launches when
  the room starts, tells the room `running <level>` / `over`, and keeps the character's
  level current. The portal never calls the game.
- What the portal does around it, with `net2_game_status()` (game.h) once a frame:

  | Moment | Portal |
  |---|---|
  | the player is in a room and has no character yet | `net2_game_choose(is_host)`, then get out of the way: phase CHOOSING is the game's own character screens (the player needs the game's picture and the controller) |
  | phase CHOSEN | come back; `net2_ready(n, 1)` (a host just shows Start); `status.character` is what was chosen |
  | phase TITLE with `failed` | the screens were left without a character: offer it again |
  | `NET2_EV_START` | "finding each other" with the routes of `net2_room()`; nothing to call |
  | phase LAUNCHING, LOADING, RUNNING | out of the way: the game shows its own launch screen and then the level |
  | phase TITLE again after RUNNING | the game is over on this machine: come back in front; the room is open again ("Play again" = choose, ready, start) |
- Boot: `--opt net2-boot=1` lets `launch.cpp` press cross through the memory-card question
  and the logos until the title screen is up (it does so by itself when the program was
  started with `--opt net2=...`); phase BOOTING until then.

## 6. Proof

All on this Mac, 2026-10-13 19:47-23:02. Programs: `local/recomp-net2/bin/n2_headless`
(the game, the runtime, `netdrv.cpp` with the patch, `launch.cpp`), at most four at a
time, `nice 10`, paced to 59.94 vertical blanks a second, `net-local-only=1`; once the
window program (`n2_window`, off-screen). Each copy has its own data folder: identity
file, memory card. A service of each run's own on 127.0.0.1 (and this Mac's LAN address
for the LAN rows), nothing else. Every copy boots by itself, makes a new character on the
game's screens (pressed by the script as a person would), sends one chat line in the room;
the host starts when everybody has a character. "In step": `tools/rig/compare.py ticks`
over every pair of tick logs (seed, level, player count, button maps, every player's
position, state, hit points, gold, experience, out-of-step flags, own sync hash) - no
column differed in any row below. Drawn input on every copy. Load average 9 to 58.

| Run | Copies | Routes | Launches | In the level | Ticks in step (every pair) | What else |
|---|---|---|---|---|---|---|
| fixed addresses, no service (`app net2 direct`) | 2 | straight | 1 | 1 | ticks to 2,044, both players | the first launch |
| `p2` | 2 | punched, 127.0.0.1 | 1 | 1 | 1,819 | chat line seen on both |
| `p3` | 3 | punched | 3 in a row | 3 | 1,819 each, all 3 pairs | second and third launch log in with the identity files of the first |
| `p4` | 4 | punched | 3 in a row | 3 | 1,818 - 1,819, all 6 pairs | |
| `lv2` `lv3` `lv4` | 2, 3, 4 | punched | 1 each | 3 | 4,335; 4,320; 4,303 - 4,304 | hub > drunare (level change in one lockstep tick), 0 / 2 / 2 deaths in the arena fight |
| `drop3` | 3 | punched | 1 | 1 | 2,133 between the two left (1,244 with the dropped one) | the last joiner's process killed at tick 1,244: lockstep stands about 20 s, then "DISCONNECTING PLAYER 2 on frame 1264", the game goes on |
| `hostq3` | 3 | punched | 1 | 1 | 2,130 between the two joiners | the HOST's process killed: the game goes on without its host |
| `again2` | 2 | punched | 2 games in the same processes and room | 2 | 1,409 and 1,219 | the joiner leaves by the pause menu, the host is put back by the game, both back at the title screen, characters again, the host starts again |
| `again3` | 3 | punched | 2 games | 2 | game 1: 2,008 / 1,408; game 2: 1,219, all pairs | leaving one after another |
| `relay2` (twice) | 2 | relay, forced on every copy | 1 + 1 | 2 | 1,818; 1,819 | the launch handshake (characters) and the game entirely through the service: 842 and 1,859 datagrams relayed |
| `relay3` | 3 | relay | 2 in a row | 2 | 1,819 each, all pairs | 7,086 relayed |
| `relay4` | 4 | relay | 2 in a row | 2 | 1,818 - 1,819, all 6 pairs | 10,301 relayed (612 kB), 3 dropped |
| `mixed3` | 3 | two punched, the third forced to the relay | 1 | 1 | 4,321 | hub > drunare |
| `lan3` | 3 | punched through 192.168.1.123 (after the fix of 5.5; before it: every pair relayed, 2 launches in step all the same) | 2 in a row | 2 | 1,819 each | |
| `lan4` | 4 | punched through 192.168.1.123 | 1 | 1 | 1,718 - 1,730, all 6 pairs | load 50 |
| window program hosting, headless joining | 2 | punched | 1 | 1 | (pictures, no tick log) | the game's character screens, the "Network Game Launch" screen with both players "Ready!", both in the hub |
| **limits under play** | | | | | | |
| `limrelay`: relay 10 datagrams a second, 20 at once | 2 | relay | 1 | 1 | 1,817 | the service dropped 847 of 1,370 datagrams as over the limit; the game went on in step (it repeats what was not acknowledged), slower |
| `limhello`: hello once a second from an address, an address forgotten after 4 s | 2 | relay | 1 | 1 | 1,145 | 264 relayed datagrams dropped (to an address gone stale), 18 hellos limited; in step, slower |
| `limlines`: 1 line a second, 5 at once | 2 | punched | 1 | 1 | 1,819 | not hit: the client says fewer lines than that |
| `limconn`: 2 connections from one address | 3 | - | 1 | **0** | - | the third copy was refused 5 times ("Too many connections."), the room never had three, nobody started: the limit holds and nothing else breaks |

Not run (then; two computers on two networks since 2026-10-20, section "Two networks"): two computers, a real router, a player behind a NAT that changes ports; a person
at the controls; the window program in a visible window; a character imported from a
memory card (the runs make new ones); the emulator application in a room.

## Two networks (2026-10-20)

The first game between two computers on two different networks. **Ran**, 2026-10-20
14:50-15:00 CDT. Host: a second Mac (Apple silicon, macOS 26.6) on the owner's home network,
behind its home router. Joiner: this Mac (macOS 27.2) away from home, on a different
provider's network behind that network's router - a network that also breaks TLS on the
way out (a middlebox answers the TLS handshake with something that is not TLS). The
service: `rendezvous.py` on the project's server; because of that middlebox, a second,
temporary instance of the same file in plain text (`--plain`, its own `--data` under
`/tmp`, its own port), started for the test only and removed afterwards; the public TLS
instance and everything else on the server were left alone.

How: `n2_headless` of `local/recomp-net2/bin` (the build of 2026-10-14; its minimum system
version lowered to 26.0 with `vtool`, nothing else changed - `otool -L`: only system
frameworks and libraries, so it ran on the other Mac as it is) on both computers, the same
`SLUS_209.73`, the disc image copied to the home Mac for the test and deleted afterwards.
On that Mac it booted to the title screen by itself in 418 frames. Each side ran one copy
with exactly `n2party.py`'s own script and options (`script_lines`, `start_copy`, imported
from the file; a small local driver started the host on the home Mac over SSH, read its
room code, then started the joiner here): room by code, a chat line, a new character on
the game's own screens, start, 900 frames of drawn input in the hub, the level name written
in one lockstep tick (`drunare`), 2,400 frames there. Both tick logs fetched to this Mac
and compared with `tools/rig/compare.py ticks`. The UDP socket of each copy was bound to
its computer's own Wi-Fi/Ethernet address (`--opt net2-bind=ADDRESS:0`) so that the two
computers' VPN (both are on one private Tailscale network) could not carry the game; the
last row is the same without it.

| Run | Routes | Ping (the carrier's own measure) | Ticks compared | Datagrams | Result |
|---|---|---|---|---|---|
| `auto1` (routes found by themselves) | **punched**: each copy's direct route is the other's public address as the service saw it, both ways | 79-81 ms at the start, 52-68 ms in play | 4,311, hub > drunare | 2,205 each way, none by relay | no shared column differs on any tick |
| `relay1` (`--relay force` on both) | relay through the server, both ways | (none measured on a relayed route) | 4,311, hub > drunare | 2,208 / 2,207 sent, all relayed; the joiner received 2,172 (lost ones repeated by the game's own acknowledgement) | no shared column differs |
| `auto2` (as `auto1`, again) | punched, both ways | 70-86 ms | 4,315, hub > drunare | 2,209 / 2,212, none by relay | no shared column differs |
| `nobind1` (no `net2-bind`, as a player would start it) | joiner > host punched to the host's public address; host > joiner to the joiner's **VPN** address (100.64.0.0/10, which the service accepts as "behind a router") | 51-86 ms | 4,315, hub > drunare | 2,206 / 2,205, none by relay | no shared column differs |

Both routers kept the UDP port of each socket (the address the service saw had the
socket's own port), so the punch needed no guessing. The service over all runs (and one
check of the plain instance with both copies on this Mac, which the router here did not
loop back, so relayed - as in the run of 2026-10-14): 21 connections, 5 rooms, 5 starts,
5,359 datagrams relayed (285 kB), 2 relay drops, nothing limited.

The TLS service from both sides: from the home Mac one copy reached the public TLS
instance by its host name, opened a room (code in under 9 s) and made its character -
**Ran**, no second player. From this Mac's network the client cannot reach it at all:
`net2cli` says "No secure link to the service: server closed session with no
notification (-9816)" - **Ran**; the plain instance was the only way to get this network
into a game. A player on such a network today cannot use the public service.

**Read**, from the runs: (1) a VPN address in the room's local list is taken as a straight
route across networks when both players share that VPN; harmless here (in step), but it
is a route nobody asked for - the client could leave 100.64.0.0/10 out of `local`, or try
public routes first. (2) Not tried: a router that changes ports (symmetric NAT; the punch
would fail and the relay would carry it, which `relay1` shows works across networks), IPv6,
more than two computers, a person at the controls on either side.

Changed on the server for the test and undone the same day: a transient unit
`rta-plain-test` (`systemd-run`, user `nobody`, the repository's `rendezvous.py` copied to
`/tmp/rta-plain` with `--data /tmp/rta-plain/data --plain` on a second port) and two UFW
rules for that port (TCP, UDP); afterwards the unit stopped, both rules deleted, the
folder deleted, nothing listens on that port; the lobby, the relay, the web server, the
browser page and the `champions-net2` unit were not touched and stayed active.

## 7. The emulator application (design only)

Built and run on 2026-10-14 - with one change to point 3 (a pnach section that is not in the
fix set): `docs/issues/app-rendezvous.md`.

The Mac application (Play!-based) has the game's whole network stack inside the emulated
machine; its layer `tools/play-net/src/RtaNet.cpp` sees every datagram between the game
and the host's sockets and already rewrites addresses. For it to sit in a rendezvous room
with native copies it needs four things, none of them in the game:

1. **The session client.** `session_net.cpp` + `carrier.cpp` compile as they are (no
   dependency on the native runtime); the application's own window would show the room
   (or the same portal, if it is ever given one).
2. **The datagrams.** In `RtaNet.cpp`, UDP from the game to 10.77.0.x:4000 goes to
   `Carrier::send(slot)`, and what `Carrier::receive` gives is injected as a datagram
   from 10.77.0.(k+1):4000 - the same two hooks `netdrv.cpp` got. The emulated adaptor
   needs an address in 10.77.0.0/24 for the game's own stack to send there without a
   gateway question (its DHCP answer is the layer's own).
3. **The start.** The application cannot call the game's functions; it does the same
   steps by writing memory at a vertical blank and letting the game's own code run: the
   settings block and tables are data, and the two calls that matter can be had without
   a call - `frontend_startPlayerSelect` by the front end's own state 6 (set state 6 with
   the menu pointer on the host/client table, press cross through the control path it has),
   and `frontend_startNetGame` runs from state 7 by itself; its fixed address table
   0x53d0e8 is data (written before), the count it hard-codes (4) and the ports (4000)
   are overwritten in the tables and launch records right after it has run, in the same
   blank. That last step is the delicate one and needs the rig to prove it; the
   alternative is one small code patch (a section that makes 0x1e21e0's developer branch
   read the count from 0x402a37) - which every emulator player would need, and no native
   player.
4. **The same figure and arithmetic** told to the room (`copy fix= words= can= does=`):
   the application has both already.

A room with both kinds would then need the arithmetic rule of `mixed-arithmetic.md`
(a browser copy in the room makes every copy that can switch) applied from the room's
members instead of from the lobby's keep-alive marks; the member lines carry what is
needed (`can`, `does`).

## 8. Running it in public (decided 2026-10-14: it runs on the project's server)

- **One port number, TCP and UDP** (41900 by default), beside the lobby's own (which
  uses TCP 40800-40817, 20002.. and UDP 10101). `--bind <the server's address> --public`.
- **Python 3.8 or later**, nothing to install; one file of state (`--data`).
- **Load:** one connection per player online; a relayed game costs the server about 30
  datagrams of 30 to 200 bytes per second per player in each direction - a few kB/s per
  relayed player; punched pairs cost nothing. The limits of 3.5 hold the rest.
- **TLS for the TCP port** (3.1), built 2026-10-14: `--tls-cert/--tls-key` in the service
  itself (Python's `ssl`, no proxy in front), the operating system's TLS in the client
  (`tools/recomp/net2/tls.h`: Network.framework on macOS - run; SChannel on Windows -
  compiled, not run), the certificate checked against the system's trust store and the host
  name. The client takes TLS by itself for every host name and public address and stays in
  plain text for this computer and a LAN (`tls://`, `plain://`, `RTA_NET2_TLS` override).
  On the server: prepared, not run (`tools/rendezvous/deploy/`). Without it: names, friend
  codes, room codes, chat and the verifier at a player's FIRST contact travel in the clear.
  The datagrams stay outside TLS; what they expose, what was fixed (a hello from another
  address) and what not (the game's datagrams can be read and forged on the path):
  [native-rendezvous-tls.md](native-rendezvous-tls.md) sections 1 and 4.
- **What it knows about people:** section 3.2, nothing else. A player deletes all of it
  with one call.
- **Not done for public use:** TLS on the server (prepared); the game's datagrams
  authenticated; log rotation (the unit logs to the journal, which rotates); a way for
  the owner to remove a player or a name; more than one process (SQLite and the in-memory
  rooms make it one machine, one process - thousands of players, not hundreds of
  thousands); IPv6; a grace time for a player whose TCP link breaks during a relayed game
  (today the service puts such a player out of its room at once and the relay stops for
  it; straight routes are not affected).
- Since 2026-10-14 it runs on the project's server (STATE above).

## 9. What the old lobby still does that this does not

Lobby-wide chat and private messages; a public list of open games (here: codes, friends,
invitations); characters stored on the server and carried between computers by logging
in (here: copy the memory card folder); the game's own room screens with the on-screen
keyboard; play for the emulator application, the browser page and - with the public
server's name pointed elsewhere - a real console (this is native only); joining with
nothing but the original disc.

## 10. Files

New: `tools/rendezvous/rendezvous.py`, `check.py`, `check_client.py`;
`tools/recomp/net2/session.h`, `session_impl.h`, `session.cpp`, `session_mock.cpp`,
`session_net.cpp`, `carrier.h`, `carrier.cpp`, `tls.h`, `tls.cpp` (2026-10-14),
`hash.h`, `cardchars.cpp`, `clicmd.h`,
`clicmd.cpp`, `net2cli.cpp`, `game.h`, `launch.cpp`, `hooks.h`, `net2.patch`, `play.sh`,
`n2party.py`. Local, not in the repository:
`local/recomp-net2/` (`snap/` the native build's objects and headers of 2026-10-13 13:33,
`work/net/` the network sources with the hook lines, `build.sh`, `bin/`, `rv/` test runs).
Nothing in `tools/recomp/rt|render|app|net`, `tools/godot`, `patches/` or
`tools/play-net` was edited.
