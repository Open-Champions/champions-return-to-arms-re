# The room service for strangers: TLS, and what the service lets through

Started 2026-10-14. The owner: "Anybody should be able to play with anybody." The room
service of `native-rendezvous.md` runs in public on the project's server, and its TCP
conversation was plain text: names, friend codes, room codes, chat and - at a player's
first registration - the verifier went over the wire as they were (`native-rendezvous.md`
3.1, 8). This file is the work that puts that conversation inside TLS on both sides, the
review of the service for strangers on the Internet, and the deployment, prepared for the
server and not run there. Every claim says **Ran** (done and seen, on this Mac) or **Read**
(from the code or the documentation, not run).

## STATE (rewritten at every step; read this first after a stop)

**2026-10-14 03:15. Done on this Mac; the server is not changed.** The service speaks TLS
when it is given a certificate and refuses a public address without one; the client (macOS
Network.framework, Windows SChannel) uses TLS by itself for every host name and public
address, checks the certificate against the system's trust store and the host name, and
stays in plain text for this computer and a LAN. Native game copies played through a TLS
service. The deployment files are in `tools/rendezvous/deploy/`; the server steps are
`tools/rendezvous/deploy/STEPS.txt` - for the orchestrating session to run.

| Part | Where | State |
|---|---|---|
| TLS in the service | `tools/rendezvous/rendezvous.py` `--tls-cert/--tls-key` | **Ran**: `check.py` 225 of 225 (189 before, all still passing; 36 new) |
| the exposure review's fixes | the same file | **Ran**, each limit hit on purpose in `check.py` (section 4) |
| TLS in the client, macOS | `tools/recomp/net2/tls.h`, `tls.cpp` (Network.framework + Security) | **Ran**: `check_client.py` 118 of 118 (95 before, all still passing; 23 new) |
| TLS in the client, Windows | `tls.cpp`, SChannel body | **Compiled and linked** for Windows with the cross-compiler (`-Wall -Wextra`, no warning); **NOT RUN**: no Windows here |
| other systems (Linux) | `tls.cpp`, last body | **Read** only: a start fails and says that there is no TLS here |
| the session using it | `session_net.cpp` (one link object instead of the socket; the rule; two settings) | **Ran** (both checks above) |
| game copies through a TLS service | `n2party.py --tls`, `local/recomp-net2/bin/n2_headless` | **Ran**: 2 copies punched, 2 copies relay-forced, 3 copies mixed: every pair 2,119 ticks in step |
| `rta_app` with it | `tools/recomp/app/build.py` (compiles `tls.cpp`, links Network and Security) | **Ran**: built as `local/recomp-out/bin/rta_app_tls` (`--no-game --as rta_app_tls`); `rta_app` itself untouched. Not started |
| Windows program, Godot game library | `build_win.py`, `tools/godot/build.py` | edited (one source, two libraries / three frameworks); **not run** |
| deployment | `tools/rendezvous/deploy/` (unit, renewal hook, steps) | **prepared, NOT RUN**; nothing on the server was touched |

To rebuild the owner's program with this: `python3 tools/recomp/app/build.py` (as always;
`--as rta_app_next` and a move if it is to be checked first). Players on the public service
must then name it by its host name (section 5).

## 1. What travels where now

**The TCP conversation** (everything of `native-rendezvous.md` 3.3: registration with the
verifier, the login proof, names, friend codes, friend lists and presence, requests,
invitations, room codes, room lists, chat, the start description with every player's
addresses, the datagram key of `welcome udp=`): inside TLS 1.2 or 1.3 when the service has
a certificate. **Ran**: a tap between client and service (`check_client.py`, class `Tap`)
recorded 4,661 bytes of a TLS session that registered "Wiretap Wendy TLS", hosted a room
and said a chat line, and found none of name, chat text, verifier, friend code, room code
or player id in them; the same tap in plain text found all six.

**The datagrams (UDP, the same port)** are as they were (`native-rendezvous.md` 3.4). What
they expose, read from `carrier.cpp` and the service:

| Datagram | In the clear | What somebody on the path can do with it | Done |
|---|---|---|---|
| HELLO to the service | the player's 8-byte datagram key | was: send hellos with it from **anywhere**, so that the service took that address as the player's - the relay and the other players' punching would go there (a stolen route), or, with a forged source address, at a third party (reflection) | **fixed**: a hello counts only from the IP address of its player's own TCP connection (`hello_same_address`). **Ran** (`check.py`, through this Mac's LAN address). Left: somebody who shares the player's public address (the same home router) |
| SEEN from the service | the address the service saw | tells the sender its own outside address; 14 bytes for a hello of at least 16: nothing to amplify | - |
| RELAY / RELAYED | the key, the session number, the game's datagram | read the game's inputs; a relayed datagram is only taken from the address the player's hello came from and only sent to the other members' hello addresses | - |
| PROBE / ANSWER / GAME between players | session number (4 bytes), slot, the game's datagram | read the game's inputs; **inject** datagrams with the right session number to the right port (an on-path attacker; off the path both are guessed: 2^32 x the port). The game would fall out of step or take a forged input | **not fixed** (section 4) |

Every member of a started room learns the other members' public address and port and up to
three of their LAN addresses (the `peer eps=` lines) - what peer-to-peer play needs; it now
travels inside TLS, so only the room's members see it. Forcing the relay does not hide it.

## 2. The service (`rendezvous.py`)

```
python3 tools/rendezvous/rendezvous.py --data DIR --bind ADDRESS --port 41900 --tls-cert CHAIN.pem --tls-key KEY.pem
```

- Python's `ssl` module, nothing else (**Read** the code; **Ran** with Python 3.12 /
  OpenSSL 3.0). `ssl.PROTOCOL_TLS_SERVER`, at least TLS 1.2, the module's defaults
  otherwise. A client that offers only TLS 1.1 is refused (**Ran**).
- One thread, non-blocking as before: an accepted socket is wrapped without a handshake;
  the handshake is stepped from the selector (`handshake()`); the greeting `hi` waits in the
  output until it is through; reads take what TLS has already decrypted (`pending()`);
  writes are whole records of at most 16 kB, and a write TLS could not finish is repeated
  with the same bytes (OpenSSL's rule). **Ran**: 2,500 chat lines (300 kB) to a client with
  a 4 kB receive buffer that did not read for a second arrived whole and in order.
- A connection that never finishes the handshake counts as one that never logged in: closed
  after `login_seconds` (**Ran**, 2 s). A plain-text client gets nothing readable and is
  closed (**Ran**). A refused connection (limits) is closed without a handshake and without
  the plain-text "bye" (a handshake is the expensive part).
- `SIGHUP` reads the certificate again; connections made afterwards get the new one, those
  that are open keep theirs (**Ran**: swapped for a certificate of another name and back).
  `SIGTERM` ends it like Ctrl-C, with the summary line (**Read**).
- Without `--tls-cert`: plain text as before, for this computer and a LAN. An address that
  is neither loop-back nor private (10/8, 172.16/12, 192.168/16, 100.64/10), or 0.0.0.0, is
  refused without TLS unless `--plain` is said (**Ran**). A certificate whose key does not
  belong to it, or a certificate without a key, is refused at the start in words (**Ran**).
- The summary line counts `TLS handshakes (failed)` and `hellos from another address`.

## 3. The client (`tools/recomp/net2/tls.h`, `tls.cpp`, `session_net.cpp`)

**When TLS is used** (`n2::tls_wanted`; **Ran**, `debug tls-rule`, nothing sent):

| The service written as | rule auto (the default) |
|---|---|
| `127.x.x.x:P`, `localhost:P` | plain text |
| `10.x`, `172.16-31.x`, `192.168.x`, `100.64-127.x`, `169.254.x` as numbers | plain text (a LAN, a tunnel) |
| any other address as numbers | TLS |
| any host name | TLS |

Overrides, strongest first: `net2_set(n, "tls", "on"|"off"|"auto")` (the link is made again);
the environment variable `RTA_NET2_TLS=on|off|auto`; `tls://host:port` or `plain://host:port`
as the service's address. `net2cli --tls on|off|auto`. **Ran**: each of them.

**What is checked.** The certificate chain against the system's trust store and that the
certificate is valid for the host name the player gave - or, with
`RTA_NET2_TLS_CA=FILE` / `net2_set(n, "tls-ca", FILE)` / `net2cli --tls-ca FILE`, against the
certificates of that file and nothing else (for tests, and for whoever runs a service with
a certificate of their own). A certificate is for a name: a service on the Internet is
named by its host name. Its address written as numbers takes TLS too (a public address) and
then refuses the certificate. **Ran**, each with the words the player sees in
`net2_me().problem` (macOS):

- no trust: `No secure link to the service: The service's certificate is not accepted for localhost: "rta-net2 test authority" certificate is not trusted (trusted: the system's store)`
- the right authority, another name: `... not accepted for localhost: "wrong" certificate name does not match input (trusted: only ca.pem)`
- another authority; a TLS client at a plain-text service; a trust file that is not there: refused, in words
- accepted: `debug link` says `tls on (rule on): TLS 1.3, certificate for localhost checked (trusted: only ca.pem)`

A refused certificate is tried again like any failed link (1, 3, 10, 30 s).

**macOS body** (**Ran**): Network.framework makes the TCP connection to the address the
session resolved (IPv4, as the datagrams) with the host name as the TLS server name; TLS 1.2
at least; the certificate is evaluated in a verify block by the Security framework with an
SSL policy for that name (`SecTrustEvaluateWithError`), with `SecTrustSetAnchorCertificatesOnly`
when a file is given. What arrives is kept in a buffer that the polling thread takes from;
nothing blocks the poll. Link `-framework Network -framework Security` (`app/build.py`,
`godot/build.py`, `check_client.py`, the local build do).

**Windows body** (compiled, **NOT RUN**): SChannel over a non-blocking socket of
`net/sock.h`, driven from the polling thread: `AcquireCredentialsHandleA` (TLS 1.2, strong
crypto; the system's own validation of chain and name), `InitializeSecurityContextA` steps,
`EncryptMessage`/`DecryptMessage` per record. With a trust file: manual validation - a chain
engine whose only root store is that file (`hExclusiveRoot`, Windows 8 or later) and the SSL
chain policy for the name. Link `-lsecur32 -lcrypt32` (`build_win.py` does). Built on this
Mac: `local/net2-tls/win/tlsprobe.exe` (a small program that opens a session and prints the
link; its source and build script beside it) - it imports `InitializeSecurityContextA`,
`EncryptMessage`, `DecryptMessage`, `CertGetCertificateChain`,
`CertVerifyCertificateChainPolicy` from Secur32/CRYPT32. To run it on a Windows computer:
`tlsprobe.exe tls://<server-host>:41900 C:\some\folder` (it registers a player there).
Not handled: TLS 1.3 (not offered: the old credential structure), a renegotiation (the
link is dropped and made again).

## 4. The service for strangers: what was looked at

| Exposure | Before | Now |
|---|---|---|
| new connections from one address (each may cost a TLS handshake) | 12 at once, no rate | also **60 a minute** (`connects_per_minute`); **Ran** |
| new players from everywhere together | 10 an hour per address only | also **1,000 an hour** all told; **Ran** |
| friend requests waiting for ONE player | unlimited (each asker: 20 open) | **100** (`requests_incoming`); **Ran** |
| changes every friend and the room is told of (name, character, copy, own addresses, level) | the line rate (20 a second): with many online friends a few hundred database reads per line | **1 a second, 10 at once** per connection (`updates_*`); **Ran** |
| guessing room codes | 10 a minute per connection - a new connection started again | **per address**, then that connection is closed; **Ran** |
| a member's "own addresses" passed to the room | any IPv4 address: a member could aim the others' probes anywhere | only private ones (what the list is for); **Ran** |
| a hello from another address | taken (section 1) | refused; **Ran** |
| names, labels, chat with invisible format characters (right-to-left override, zero-width space) | kept: a name could pass for another one | taken out (the zero-width joiner of emoji stays); a name with them is refused; **Ran** |
| the process's file limit | `accept()` failing at the limit leaves the listener readable: the loop would spin | connections capped below the limit (soft raised to hard first); at the limit the listener rests a second; **Ran** (the cap, with 96 files: 32 taken, the 33rd refused in words); the rest **Read** |
| a public address in plain text | allowed | refused without `--plain`; **Ran** |
| messages | 1,024 bytes a line, 24 a label, 120 a chat line, 2,064 a datagram | the same (they were tested before) |
| relay amplification | none (output = input - 8 bytes, only to members' hello addresses) | the same, and the hello rule above stops reflection to a third party |
| memory | rooms 5,000, connections 2,000, output 256 kB per connection; every table of limits swept hourly; a window keyed by address only after a real TCP connection or a valid datagram key | the same; the unit adds `MemoryMax=400M` |

**Not fixed** (each needs more than a cheap change, or is somebody else's):

1. **The game's datagrams are neither encrypted nor authenticated.** On the path they can be
   read and forged (section 1). The way: the service hands every room a session key over
   TLS (`start key=`), and the carrier puts an HMAC (truncated to 8 bytes, the hash of
   `hash.h`) on every datagram and drops what does not match. A change of the wire format in
   `carrier.cpp`, which the emulator application's work uses too.
2. Every room member learns the others' addresses (section 1). Possible: a "relay only, do
   not show my address" mark that makes the service leave `eps` out for that player.
3. The service's file holds verifiers: whoever has the file can log in as any player
   (`native-rendezvous.md` 3.1). Key pairs would end that.
4. Players who registered while the public service spoke plain text (2026-10-14 from 01:51)
   sent their verifier in the clear. Whoever cares can delete everything and register again
   (`net2_delete_everything`).
5. A renewed certificate is taken at a restart, which drops every room (`deploy/renew-hook.sh`
   says so); about every 60 days. A reload without a restart exists (`SIGHUP`) but the
   certificate given by `LoadCredential=` is a copy made at the start.
6. Output: 256 kB may wait per connection; 2,000 such connections would be 512 MB - more than
   the unit's `MemoryMax=400M` (systemd would end and restart the service, not the machine).
   Somebody would need hundreds of addresses and a way to make the service talk to clients
   that do not read. A cap for all connections together is not built.
7. No moderation: the owner cannot remove a player or a name; names are labels (the friend
   code is the identity); nobody can report anybody.
8. One process, one thread: a handshake flood from many addresses costs CPU (the per-address
   rates hold one address); a flood of datagrams is the hosting provider's to absorb. IPv6:
   none.

## 5. Deployment (prepared, NOT RUN)

`tools/rendezvous/deploy/`:

- `champions-net2.service` - the unit: the same name, program place and state directory as
  the one that runs now (so the players' file is kept), `--tls-cert %d/tls.crt --tls-key
  %d/tls.key` with `LoadCredential=` from `/etc/letsencrypt/live/<server-host>/` (root's
  files, copied at every start into a directory only this service reads), a user made for
  it alone, a read-only system, no capabilities, a system-call filter, IPv4 only, no traffic
  to loop-back, private networks, link-local (the provider's metadata address) or
  multicast, 4,096 file descriptors, 16 tasks, 400 MB.
- `renew-hook.sh` - certbot's deploy hook: restarts the service when that certificate was renewed.
- `STEPS.txt` - the steps in order, each with what it should print: look; copy to the side;
  the self-test on the server; keep the old files; the unit with its two placeholders filled
  and `systemd-analyze verify`; switch; check from the Mac with `openssl s_client`, `net2cli`
  and `n2party.py --external`; the renewal hook; the clients; the way back.

Placeholders: `<server-host>` (the certificate's host name) and `<server-address>` (the
server's public IPv4 address). Neither is written into the repository.

**For the clients after the switch:** the service is `<server-host>:41900` (not the address).
A program without `tls.cpp` speaks plain text and is closed after 10 s. The owner's
launchers and any `net2-service.txt` / `RTA_NET2_SERVICE` that name the address need the host
name instead.

## 6. Proof

All on this Mac, 2026-10-14 02:40-03:15. Services of the tests' own on 127.0.0.1 (and once
this Mac's LAN address, for the hello check); certificates made per run with the openssl
program by `check.py`'s `test_certificates()`: an authority of the test alone, a server
certificate for `localhost`/127.0.0.1, one for another name, one from another authority -
in the work directory, installed nowhere.

- `python3 tools/rendezvous/check.py` - 225 of 225 (33 s).
- `python3 tools/rendezvous/check_client.py` - 118 of 118 (32 s).
- `n2party.py --tls` (headless game copies, `local/recomp-net2/bin/n2_headless` built with
  `tls.cpp`, service with the test certificate, copies at `tls://localhost:PORT` trusting the
  test authority only):

  | Run | Copies | Routes | Ticks in step | Service |
  |---|---|---|---|---|
  | `rv/tls2` | 2 | punched | 2,119 | 2 TLS handshakes, 0 failed |
  | `rv/tlsrelay2` | 2 | relay, forced | 2,119 | 2,173 datagrams relayed |
  | `rv/tlsmixed3` | 3 | two punched, the third relayed | 2,119, all 3 pairs | 2,933 relayed, 3 handshakes |

- Windows: `local/net2-tls/win/build.sh` - compiles `session*.cpp carrier.cpp tls.cpp
  cardchars.cpp clicmd.cpp` with the flags of `build_win.py` and links `tlsprobe.exe`. Not run.

Not run: a real certificate from a public authority (the macOS path for the system's store
is the same code with no anchors; the refusal of the test authority by the system's store
was seen); the server; Windows; a client on another computer.

## 7. Files

New: `tools/recomp/net2/tls.h`, `tls.cpp`; `tools/rendezvous/deploy/champions-net2.service`,
`renew-hook.sh`, `STEPS.txt`; this file. Changed: `tools/rendezvous/rendezvous.py`,
`check.py`, `check_client.py`; `tools/recomp/net2/session_net.cpp` (the link),
`session.h` (a comment), `net2cli.cpp` (`--tls`, `--tls-ca`), `clicmd.cpp` (a comment),
`n2party.py` (`--tls`); `tools/recomp/app/build.py`, `build_win.py`, `tools/godot/build.py`
(one source and the libraries); `docs/issues/native-rendezvous.md` (sections 3, 8).
Local, not in the repository: `local/recomp-net2/build.sh` (with `tls.cpp`),
`local/recomp-net2/bin/` (rebuilt), `local/recomp-net2/rv/tls2`, `tlsrelay2`, `tlsmixed3`,
`local/recomp-out/bin/rta_app_tls`, `local/net2-tls/win/`.
