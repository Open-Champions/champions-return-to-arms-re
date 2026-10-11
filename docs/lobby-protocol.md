# Lobby protocol (Return to Arms ↔ matchmaking server)

What the game says to its matchmaking ("lobby") server, what it expects back, and how two
consoles end up with each other's address. Written from four sources, and every claim is
tagged with the one it rests on:

- **[S]** read in the Champions Reborn server source (github.com/HikikoMarmy/Champions-Reborn-Server,
  AGPL-3.0; file named, paths relative to that repository). This says what *that server*
  does, which is not always what the game expects. Since section 1a "this server" is the
  fork with its fixes; a `FIXES.md` section number refers to that fork's `FIXES.md`.
- **[G]** read in the game executable SLUS_209.73 at the address given. This says what the
  game sends and how it parses replies.
- **[T]** exercised against a running server on loopback with `tools/lobby_e2e_test.py`
  (first the local macOS port built 2026-10-09, since section 1a the fork); a step number
  is that of the test's `--extended` run.
- **[R]** seen on the wire with the real client: the game itself, started in an emulator on
  the project's live rig and talking to the fork of the server through its own network
  stack, with every frame at its emulated network adaptor recorded. Each such mark is
  written out — "seen on the wire with the real client, live-rig.md section N" — and N is a
  section of `docs/issues/live-rig.md`, which describes the run.

What [R] is and is not: the emulator is Play!, not a PlayStation 2 and not PCSX2, and both
machines of a pair are copies of one emulator build. Nothing here was confirmed on a
console. The path the real client has been through is: terms, account, log in, character
create / list / load / save, a public game hosted and joined, the peer handshake, start,
play with its saves, a lost connection and a forced logout (live-rig.md sections 13, 19
and 20). Not run with the real client: private games (0x56, 0x57), a list of two or more
games, friends, ignore, instant messages, chat typed by a player, cancelling (0x05, 0x60),
deleting a character, a third console, and Champions of Norrath. "Observed" below means
[S], [G], [T] or [R]; "Inferred" and "Unknown" are marked.

No capture, account name or credential from those runs is reproduced here; sizes and
field layouts are.

Names of messages are the server project's; the game has no names for them, only numbers.
Champions of Norrath ("CON") uses the same protocol with small differences, collected in
one section at the end.

## 1. Result of the end-to-end test

`python3 tools/lobby_e2e_test.py 127.0.0.1` simulates two consoles and passes all 16 steps
[T]: gateway, key exchange, account creation, login, create public game, host discovery,
game list, join request, joiner discovery, each side told the other's address, a datagram
exchanged between the two reported addresses, join report, start, logout.

`--extended` adds optional flows. Characters, friends, ignore, instant messages, chat
rooms and cancelling work [T]. Against the unmodified server six extended steps failed,
each because of a server defect listed in section 10.

## 1a. Update after the server fixes, and after the real client

The defects listed in section 10 were fixed in a fork of the server,
[TrustlessMike/Champions-Reborn-Server](https://github.com/TrustlessMike/Champions-Reborn-Server)
(branch `macos-port`; its `FIXES.md` describes each fix and how the right behaviour was
established from the game's own parser). Against that build `tools/lobby_e2e_test.py` passes
16 of 16 core steps and 40 of 40 with `--extended` [T] (33 until 2026-10-11, when seven
steps about a console that has lost its connection were added behind the others). The
unmodified build failed 17 of the first 33 and stopped on a malformed message.

On 2026-10-11 the real game was run against that fork on the project's live rig
(`docs/issues/live-rig.md` sections 13, 19 and 20). On the path that was run — it is
listed at the top of this document — no reply of the server was refused or misread by the
game. Four of the fixes that change a reply the game parses were seen to do what they
were made for: the chat handle in the login reply (D3), one reply per character upload
with the new id (D5), the `u32` after the start-game result (D6), the room reply and the
0x19 that follows it (D7) [R: seen on the wire with the real client, live-rig.md
sections 19.4, 19.5, 19.6, 19.10; summed up in 19.13]. Three more defects were found
there (S1 to S3: a console that reconnects without logging in, the length of 0x41, a
server that had stood still) and fixed (`FIXES.md` 16 to 18), and those fixes were then
run with the real game as well [R: seen on the wire with the real client, live-rig.md
section 20.1]. A fourth (S6, `FIXES.md` 19: a session picked up again was not in its
chat room) was fixed afterwards and has only been run with the test client [T: step 40].

Sections 2 to 9 were brought in line with all of this on 2026-10-11: they describe the
fork as it is now, and every statement that changed because of what the real client did
carries an [R] mark. Section 10 is kept as the record of the unmodified server.

## 2. Transport and framing

- TCP, one request/reply stream per connection, plus one UDP datagram type (section 6).
- Every TCP message, in both directions, is `u32 length` **big-endian** followed by the
  payload; the length counts itself. Everything inside the payload is little-endian.
  [S: Source/Lobby Server/LobbyServer.cpp, Source/Network/RealmSocket.cpp] [T]
- The game sends each message as two TCP segments, the four-byte length word first and
  the payload after it [R: seen on the wire with the real client, live-rig.md section
  13.4]. A receiver has to collect a frame across reads; the server does [S:
  LobbyServer.cpp, `ReadSocket`]. The game also has several requests pending at once:
  after a login 0x0E and 0x61 leave one frame apart, then 0x5B, 0x0C, 0x55 and 0x0E, and
  they are answered in order [R: seen on the wire with the real client, live-rig.md
  section 19.4].
- Request payload: `u16 id`, `u32 tracking number`, `u32 version`, then the body. The
  version is 6 for Return to Arms and 2 for Champions of Norrath; the server reads and
  ignores it. [S: Include/Network/GenericNetRequest.hpp] [G: header writer 0x37cc64 writes
  id, tracking number and the first word of the API object] The tracking number is a
  counter that starts at 1 and is not reset when the game connects again: 1, 2 and 3 for
  the first 0x43, 0x27 and 0x42, and in the hundreds after a long run of reconnects [R:
  seen on the wire with the real client, live-rig.md sections 13.4 and 20.1].
- Reply payload: `u16 id` (same as the request), `u32 tracking number` (same as the
  request), `u32 result`, then the body. Result 0 is success. [S] [G: 0x3837bc]
- Notification payload (server to console, unasked): `u16 id`, `u32 0`, then the body. No
  result field. [S: Source/Network/Event/Notify*.cpp] [G: 0x387388 reads u16 then u32]
- The console matches a reply to its request by tracking number alone, and parses it as
  the reply to whatever request it has pending under that number, not by the id in the
  reply [G: 0x381f80; `FIXES.md` 5]. So the pieces of a character upload, which re-use
  the tracking number of the request that started it, have one reply between them
  (section 8.3). Notifications can arrive between a request and its reply [T].
- Server limits [S: LobbyServer.cpp, Source/configuration.cpp]: an inbound frame whose
  length field is below 4 or above 2048 closes the connection (`FIXES.md` 9); a
  connection that sends nothing for `client_timeout` seconds is dropped. That is a
  setting, 120 unless changed and never less than 15 (`FIXES.md` 13); the unmodified
  server had a fixed 30. Time in which the server itself did not run — its computer
  asleep, the process stopped — is not counted as silence of the clients (`FIXES.md` 18):
  with the server held for 140 s and then continued, nobody was dropped and the requests
  that had waited were answered [R: seen on the wire with the real client, live-rig.md
  section 20.1].
- What keeps an idle connection alive: a frame with no payload, the four bytes
  `00 00 00 04`, which the game's transport sends when it has sent nothing else for more
  than ten units of its lobby clock (lobby-task calls divided by 60) [G: 0x38b858,
  0x38c53c, interval set at 0x383594; `FIXES.md` 13]. From the real client it came about
  every 760 frames while idle, and nothing is sent in reply [R: seen on the wire with the
  real client, live-rig.md section 19.4]. While its game list is on the screen the game
  also repeats 0x55, about every 710 to 725 frames [R: seen on the wire with the real
  client, live-rig.md sections 19.4 and 20.1] [G: every 610 lobby-task calls, 0x324288].
  The builder for 0x24 "touch session" (0x37d644) has no caller.
- The game gives each request a timeout, passed as the second argument of every request
  builder: 30 for most, 20 for the connect sequence and character transfers, 60 for the
  statistics request [G: e.g. 0x32aa48, 0x3278f0, 0x328360]. Inferred to be seconds.
- When the game cannot parse a reply it reports the request as failed with its own result
  code 45 (0x2d) [G: every error branch in 0x3841dc]. Result codes are mapped to on-screen
  texts `clientText1`…`clientText68` [G: 0x32d498]: results 0 to 36 take the text numbered
  one higher, 40 to 63 the one numbered two lower. So 1, this server's general failure,
  is shown as a time-out, 2 as a database error, and 45 as a protocol violation (the
  texts are on the disc; the fork's `FIXES.md` lists them under "Not fixed").
- **Result 7 is the client's "invalid session".** That is what its text says, and it is
  one of four results for which the game also tells its connect handler that the
  connection is over (−6), as it does for a lost connection and for notification 0x41;
  the other three (1000 to 1002: timed out, server disconnected, not connected) the game
  produces itself [G: 0x32d498, 0x32e8b8, 0x3301f0; `FIXES.md` 16]. It is what a
  connection that is not logged in gets for 0x55 (sections 7 and 8.9).

## 3. Field types

| name in this document | wire form |
| --- | --- |
| `u8` `u16` `u32` | little-endian integers |
| `wstr` | `u32` count of UTF-16 code units, then that many units, little-endian, no terminator [G: writer 0x382790, reader 0x38a158] |
| `nstr` | `u32` byte count, then the bytes (ASCII in practice: dotted addresses) [G: writer 0x3826e0, reader 0x38a034] |
| `blob` | `u32` byte count, then the bytes [G: writer 0x389e94, reader 0x389f10] |
| `estr` | encrypted wide string, see below |
| `T[]` | `u32` count, then that many `T` [G: readers 0x3dedc0 (wstr), 0x3defec (u32), 0x3df2cc (blob)] |

The game's readers take a maximum length per field and fail the whole reply when a string
is longer; the limits are given where they matter.

### Encrypted wide string (`estr`)

`u32 a`, `u32 n`, then `2·a − 4` bytes of ciphertext, where `n` is the plaintext length in
bytes (two per character) and the ciphertext is the UTF-16LE text, zero-padded and
encrypted with AES in ECB mode (no IV, no chaining).
[S: Source/Common/ByteStream.cpp] [G: 0x388c50 encrypts, 0x38a0dc writes] [T]

How much padding depends on who writes:

- **The game** pads to `n` rounded *down* to a multiple of 16, plus 16. Text that is not a
  multiple of 16 bytes is filled up to the next one, but **text that already is a
  multiple of 16 bytes carries one extra block**: the 16-character session id, 32 bytes
  of text, travels as 48 bytes of ciphertext (`a` = 26), and a request with nothing but a
  session id is 70 bytes on the wire with its length word [R: seen on the wire with the
  real client, live-rig.md section 19.4] [G: `docs/netlib.md`, encoder 0x38cf34].
- **The server and the test client** pad to the next multiple of 16 only, so their session
  id is 32 bytes of ciphertext (`a` = 18) [S: Source/Crypto/RealmCrypt.cpp] [T].
- Each side reads the other's form. The server takes the ciphertext length from `a` and
  the text length from `n` [S: ByteStream.cpp]; the game decrypts the length it is given
  rounded down to 16, plus 16, from a zero-filled buffer and keeps `n` bytes [G: 0x38d14c;
  `FIXES.md` 4]. Every encrypted string of the server was accepted by the game [R: seen
  on the wire with the real client, live-rig.md section 19.4].

Seen from the game it is simply a `wstr` whose characters are `n` followed by the
ciphertext, which is why `a` counts 16-bit units.

## 4. Encryption and key exchange

- Cipher: Rijndael/AES with a 256-bit key, ECB. The executable carries a 32-character
  default key (string at 0x55b728, loaded by the function at 0x38c8c8) [G]. The server
  project's Source/Crypto/RealmCrypt.cpp holds the same 32 bytes [S], and a standard
  AES-256 implementation interoperates with the server [T].
- Only `estr` fields are encrypted: the session id in almost every request, and the
  account fields at account creation and login. Everything else, including chat and all
  addresses, is plain. There is no integrity check.
- Key exchange, message 0x27 [G: 0x37cf98, 0x387124] [S: RequestGetEncryptionKey.cpp] [T]:
  the console sends an `nstr` and a `u32` 12; the reply body is an `nstr` whose content is
  `u32 key length` followed by the key encrypted with the default key. The console
  decrypts it and uses the result as the key for the rest of the connection.
- The `nstr` of the request is **32 hexadecimal digits**, and it was the same string on
  both machines of the rig [R: seen on the wire with the real client, live-rig.md section
  13.4]. So it is not drawn at random per connection: it comes from something two
  identical machines share (Inferred there). The game's own code treats it as the
  client's key string [G: `docs/netlib.md`, builder 0x37cf98]. The reply to it, 54 bytes
  with the length word, was accepted [R: same section].
- **Server shortcut:** Champions Reborn ignores the request body and always returns the
  default key, so in effect every connection uses the published default key. The original
  service presumably issued a per-session key (the project's own source comment says so);
  what it did with the request's string is **Unknown**.

## 5. Connecting: the gateway step

1. The console opens TCP to the gateway. The host name `con.soegames.net` and port 40810
   are compiled in [G: 0x324920 builds the API object with them]. A replacement server is
   reached by making that name resolve to it; how is outside this document. The real
   client asks its name server for that name and connects to port 40810 of the answer [R:
   seen on the wire with the real client, live-rig.md section 13.4].
2. On connect it sends 0x43 (body: `u32` 12) [G: 0x37cec4, sent from 0x388a34]: 18 bytes
   with the length word [R: seen on the wire with the real client, live-rig.md section
   13.4].
3. The reply body is `nstr address`, `u32 port`. The console drops the gateway connection
   and connects to that address and port — the lobby [G: 0x387124]. **It closes the
   gateway connection and then sends a reset on it as well**, so the server sees that
   connection end with an error, not only with a clean close [R: seen on the wire with the
   real client, live-rig.md section 13.4]. The address string is resolved with the
   console's name-to-address call, so a dotted address works (the server's dotted address
   was accepted [R: same section]); whether a host name works was not checked.
4. On the lobby connection it sends 0x27 (section 4), then reports "connected" to the
   game. If either step fails it starts again at the original host and port [G: 0x387124]
   — and keeps at it: shut out for 150 seconds, the real client tried the gateway 723
   times [R: seen on the wire with the real client, live-rig.md section 20.1].
5. The first time the lobby is entered it then asks for the rules, 0x42, and shows the
   reply as a terms screen. Accepting is a button press; no message is sent for it. Left
   and entered again in the same run, the game sends no second 0x42 [R: seen on the wire
   with the real client, live-rig.md sections 13.4, 19.3 and 19.4].

The same sequence, without step 5 and without a login, is what the game does by itself
when it finds its connection gone (section 8.9).

The server answers 0x43 on any of its gateway ports with the `public_ip` from its
`config.ini` and its lobby port [S: RequestGetServerAddress.cpp, Source/configuration.cpp].
A connection to a gateway port has no user attached, so nothing but 0x43 is meaningful
there. A connection to the lobby port gets a user record at accept time [S: LobbyServer.cpp].

## 6. The UDP discovery datagram

One datagram type exists. It is the body of an `estr` without the leading unit count:
`u32 0x20` (the 32 bytes of text), then the 16-character session id as UTF-16LE,
AES-encrypted with the connection key [G: 0x37cbcc builds it; 0x32a8d0 sends it]
[S: Source/Discovery Server/DiscoveryServer.cpp] [T].

- **From the real game the payload is 52 bytes, not 36**: the `u32` and 48 bytes of
  ciphertext, because 32 bytes of text get one extra block (section 3) [R: seen on the
  wire with the real client, live-rig.md sections 19.4 and 19.6]. The test client sends
  the 36-byte form, `u32` and 32 bytes [T]. The server takes any datagram of 36 bytes or
  more that starts with 0x20 and decrypts its first 32 bytes of ciphertext, which are
  the same in both forms [S: DiscoveryServer.cpp].
- The console sends it to the address and port it was given in the reply to a create-game
  or join request, **from the same UDP socket it will use for game traffic** [G: 0x32a8d0
  takes the socket from the object the UdpManager was built on, 0x32a650] — from port
  4001 in the run recorded (section 9.1) [R: seen on the wire with the real client,
  live-rig.md section 19.6].
- It is re-sent on every tenth lobby tick for as long as the console is waiting for the
  matching notification (0x3E for a host, 0x40 for a joiner) [G: 0x32d368, flag bit 2 of
  the word at client+0x64; cleared at 0x330128 and 0x32a0d0]. On the rig, where the
  server is on the same host, the joiner sent it once and had its 0x40 [R: seen on the
  wire with the real client, live-rig.md section 19.7].
- The server ignores datagrams shorter than 36 bytes or not starting with 0x20, looks the
  session id up among logged-in users, and **requires the datagram's source IP to equal
  the source IP of that user's TCP connection**; otherwise it logs an error and does
  nothing [S: DiscoveryServer.cpp]. It then records the datagram's source IP and source
  port as that user's "discovery address". The server never sends UDP; the answer comes
  as a TCP notification.

## 7. Messages

Request bodies are given as the game writes them [G: builders 0x37cec4–0x3818f8]; a field
in *italics* is sent by the game but not read by this server. Reply bodies are what this
server writes [S: Source/Network/Event/*.cpp], with a note where the game's parser
[G: 0x3841dc] expects something else. Unless a row says otherwise the server identifies
the user by the TCP connection and ignores the `estr session` it is sent. There is one
general exception: on a connection that is not logged in, the session id at the start of
a request is looked up among the sessions whose connection was lost (section 8.9).

An [R] mark in a row means that this request and its reply went between the real client
and the server, and that the game took the reply.

### Requests used by Return to Arms

| id | name | request body | reply body after `u32 result` | results and remarks |
| --- | --- | --- | --- | --- |
| 0x43 | GetServerAddress | *u32 12* | `nstr` address, `u32` port | gateway step [T] [R: seen on the wire with the real client, live-rig.md section 13.4] |
| 0x27 | GetEncryptionKey | *nstr* (32 hexadecimal digits from the game), *u32 12* | `u32` cipher length + 4, `u32` key length, ciphertext | section 4 [T] [R: seen on the wire with the real client, live-rig.md section 13.4] |
| 0x06 | CreateAccount | `estr` user name, `estr` password, `estr` e-mail, `estr` date of birth, `estr` chat handle | `estr` session id (empty on failure) | 0 ok, 1 failed (name taken, empty field, chat handle longer than 15 characters, database). The connection is logged in afterwards. User names are unique; chat handles are not checked for being unique. [T] [R: seen on the wire with the real client, live-rig.md section 19.4] |
| 0x16 | Login | `estr` user name, `estr` password | `estr` session id, `estr` the account's chat handle | 0 ok, 4 unknown account or wrong password. The game keeps the second string as its own chat handle (D3, `FIXES.md` 3). A login for an account that is still connected is accepted and ends the earlier session, whose connection is sent 0x41 and closed (`FIXES.md` 13; section 8.9). [T: steps 16 and 31] [R: seen on the wire with the real client, live-rig.md sections 19.4 and 20.1] |
| 0x17 | Logout | `estr` session | — | always 0; removes the user. [T] The session is over with that: its id is not picked up again (section 8.9) [T: step 37]. |
| 0x24 | TouchSession | `estr` session | — | always 0; does nothing. [T] |
| 0x42 | GetRules | *nstr* language code, *nstr* country code | `wstr` text | always 0. The two strings were `en` and `us` from the real client; the server ignores them and returns one fixed welcome text, which the game shows as its terms screen (section 5). [T] [R: seen on the wire with the real client, live-rig.md sections 13.4 and 19.4] |
| 0x0F | GetRealmStats | — | eight `u32` | first = number of lobby connections; the other seven are always 0. [T] |
| 0x54 | CreatePublicGame_RTA | `estr` session, *u16 1*, *u32 0*, *u32 50*, *u32 10*, `wstr` game info, *attribute list (u32 count 0)*, *blob (empty)*, `wstr` own LAN address, `u32` own UDP port, *wstr (empty)*, *u32 0* | `nstr` discovery address, `u32` discovery port | 0 ok, 2 failed (name in use). Game info is `NN,NN,NN,NN,NN\|name` (section 8.4). [T] [R: seen on the wire with the real client, live-rig.md section 19.6] |
| 0x56 | CreatePrivateGame_RTA | `estr` session, `wstr` game name, `wstr` own LAN address, `u32` own UDP port, *wstr (empty)*, *u32 0* | as 0x54 | 0 ok, 1 no user, 2 name in use. [T] |
| 0x55 | MatchGame_RTA | *estr session, u16, u32, u32, u32, filter list, u8, u32, u32* (27 bytes after the session id; 97 bytes in all from the game) | eight arrays, section 8.5; they are there whatever the result, empty when it is not 0 | **Not "always 0".** 0 with every open public RTA game (the search filter is ignored), or **7** — the client's "invalid session" (section 2) — for a connection that is not logged in: eight empty arrays, no 0x41, and the connection is left open (`FIXES.md` 16). The handler does not read the session id; on a connection that is not logged in, a lost session is picked up by it first (section 8.9). The game sends this after a login and then about every 710 frames while its list is shown. [T: steps 9, 24, 34 and 36 to 39] [R: seen on the wire with the real client, live-rig.md sections 19.4, 19.7 and 20.1] |
| 0x57 | GetGame_RTA | `estr` session, `wstr` game name | `wstr` label, `u32` game id, `wstr` host's LAN address, `u32` LAN port, `wstr` host's observed address, `u32` observed port | 0 ok, 1 full or no host, 2 not found, or not open yet (no discovery datagram from its host so far). Finds public and private games by exact name. The two pairs are in the order the game reads them (section 9.4) since `FIXES.md` 2 (D2). [T: step 23] |
| 0x66 | DoClientDiscovery_RTA | `estr` session, `u32` game id, `wstr` own LAN address, `u32` own UDP port | `nstr` discovery address, `u32` discovery port | 0 ok, 1 no user, 2 no such game. Marks the user as wanting to join that game. [T] [R: seen on the wire with the real client, live-rig.md section 19.7] |
| 0x5F | UserJoinSuccess | `estr` session, *estr host's session id* | — | 0 ok, 1 failed (no game, not open, full, already a member). Adds the sender to the game. Sent by the joiner after the host's peer "welcome" [G: 0x32ca18]. [T] [R: seen on the wire with the real client, live-rig.md section 19.8] |
| 0x23 | StartGame | `estr` session, *u8 0, u16 0, three empty lists* (15 zero bytes) | `u32` 0 | 0 ok, 1 failed (no game, or the sender is not its host). Removes the game from the list and closes its chat room. The game reads the `u32` and reports result 45 without it; what the number means is Unknown (D6, `FIXES.md` 6). [T: step 18] [R: seen on the wire with the real client, live-rig.md section 19.10] |
| 0x60 | CancelGame_RTA | `estr` session | — | always 0. Takes the sender out of its game and out of the game's chat room. The game is deleted when its host leaves or when nobody is left; a player who had only asked to join it just stops pointing at it (D8, `FIXES.md` 8). [T: steps 20 to 22] |
| 0x05 | CancelGame | `estr` session | — | always 0; does nothing for an RTA connection. The game sends 0x05 and then 0x60 every time it leaves a game [G: 0x3309c8]. [T] |
| 0x44 | UpdateGameData | `estr` session, `blob` | — | always 0. Written for CON's 256-byte game description; the RTA game has a builder (0x38075c) with no direct caller. |
| 0x5B | GetNetCharacterList_RTA | *estr session, u32* | `u32` count, then per character: `u32` id, `u32` pair count, pairs of `wstr` key, `wstr` value | 0 ok. Sent after a login, and again when the list of characters to import is opened (section 8.3). [T] [R: seen on the wire with the real client, live-rig.md sections 19.4 and 19.13] |
| 0x58 | CreateNewCharacter_RTA | `estr` session, `u32` 0, `u32` 0 (an empty `wstr` to the game), `wstr[]` keys, `wstr[]` values, `blob` first piece of data, *u32* | `u32` id of the new character — **one reply for the whole upload**, sent after the last 0x5D piece | 0 ok, 1 failed (not logged in, data that cannot be a character, a thirteenth character, database). Starts an upload (section 8.3). The game files the id and uses it in every later save (D5, `FIXES.md` 5). [T: step 17] [R: seen on the wire with the real client, live-rig.md section 19.5] |
| 0x5E | SaveCharacter_RTA | `estr` session, `estr` session of the player being saved, `u32` character id, `u32` 0, `u32` 0, `wstr[]` keys, `wstr[]` values, `blob` first piece, *u32* | — (one reply for the whole upload, after the last piece) | 0 ok, 1 failed. Starts an upload that replaces the target player's current character. In play a machine sends it for the other players' characters as well as for its own (section 8.8). [T: step 17] [R: seen on the wire with the real client, live-rig.md section 19.11] |
| 0x5D | AppendCharacterData | `estr` session, `blob` next piece, `u32` last-piece flag | none of its own | The game expects no reply to a piece [G: 0x3841dc, `case 0x5d: return`]. It carries the tracking number of the 0x58/0x5E it continues [G: 0x37ca08]; after the piece with the flag set, or when a piece is refused, the server sends the reply to *that* request, under its id (`FIXES.md` 5). A piece with no upload in progress is ignored. [T: step 17] [R: seen on the wire with the real client, live-rig.md section 19.5] |
| 0x5C | GetNetCharacterData_RTA | `estr` session, `u32` character id | `blob` (1024 bytes), `u32` last-piece flag; one reply frame per 1024 bytes | 0 ok, 1 failed (then no body). Also makes this the user's current character. [T] [R: seen on the wire with the real client, live-rig.md section 19.8] |
| 0x5A | DeleteCharacter_RTA | `estr` session, `u32` character id, *u32* | — | 0 ok, 1 no user, 2 session id does not match the connection or database error. [T] |
| 0x01 | AddFriend | `estr` session, `wstr` chat handle | — | 0 ok, 1, 2 database, 19 that user ignores you, 20 no such user **online**, 21 already a friend. [T] |
| 0x1C | RemoveFriend | `estr` session, `wstr` chat handle | — | 0 ok, 20 not a friend, 2 database. [T] |
| 0x02 | AddIgnore | `estr` session, `wstr` chat handle | — | 0 ok, 20 no such user online, 24 is a friend, 25 already ignored. [T] |
| 0x1D | RemoveIgnore | `estr` session, `wstr` chat handle | — | 0 ok, 20 not ignored. [T] |
| 0x61 | GetSocialListInitial | *estr session* | `wstr[]` friends, `wstr[]` those of them who are logged in, `wstr[]` ignored | always 0. The game marks the names of the second list as online [G: 0x32ee38, 0x328868] (`FIXES.md` 11). It sends this with 0x0E straight after a login; a new account gets three empty lists. [T: step 19] [R: seen on the wire with the real client, live-rig.md section 19.4] |
| 0x62 | GetSocialListUpdate | *estr session* | `wstr[]` friends, `wstr[]` those of them who are logged in | always 0. The friend list on its own [G: 0x328868] (`FIXES.md` 11). [T: step 19] |
| 0x63 | GetIgnoreList | *estr session* | `wstr[]` ignored | always 0. The ignore list on its own; the game's ignore screen waits for this reply [G: 0x34abb0, 0x34b2b0, 0x328a10] (`FIXES.md` 11). [T: step 19] |
| 0x64 | GetAccountInfo | `estr` user name, `estr` password (no session id) | twelve `estr`: the first is the account's e-mail address, the sixth its date of birth, the others empty | 0 ok, 4 unknown account or wrong password (then twelve empty strings). The game sends it from its login screen when a login returns result 63, which this server never does, and fills its account screen from the first and sixth string [G: 0x339a20, 0x32fd08] (`FIXES.md` 11). [T: step 26] |
| 0x21 | SendInstantMessage | `estr` session, `wstr` chat handle, `wstr` text | — | 0 ok, 1 no such user online, 19 that user ignores you. Recipient gets 0x30. [T] |
| 0x0E | GetPublicRooms | *estr session* | `wstr[]` names, `wstr[]` placeholder text, `u32[]` 88, `u32[]` 99 | always 0. Six fixed rooms. The last three arrays are filler; their meaning to the game is Unknown. The game sends this straight after a successful login or account creation [G: 0x32eba8], and once more after its first 0x55. [T] [R: seen on the wire with the real client, live-rig.md section 19.4] |
| 0x0C | EnterRoom | `estr` session, `wstr` room name | `wstr` name, `wstr` text (empty for a public room; for a game's room what its owner set with 0x19), `wstr[]` member handles, `wstr[]` moderator handles (empty) | 0 ok, 1 no such room or already in it. After a login the game enters the first public room; a joiner enters the game's room after its 0x5F. [T] [R: seen on the wire with the real client, live-rig.md sections 19.4 and 19.8] |
| 0x11 | GetRoom | `estr` session, `wstr` room name | as 0x0C if a room was found | 0, 1 no user. The name is not looked up: an empty name returns the user's game room, anything else the user's public room. |
| 0x15 | LeaveRoom | `estr` session, `wstr` room name | — | 0 ok, 1 no such room or not in it. The game does nothing with the result. It leaves the public room when it goes to host a game, when a game starts and when it leaves the lobby. [T] [R: seen on the wire with the real client, live-rig.md sections 19.5, 19.10 and 20.1] |
| 0x22 | SendRoomMessage | `estr` session, `wstr` room name, `wstr` text | — | 0 ok, 1 no such room or not a member. Every member not ignoring the sender, sender included, gets 0x3D. [T] |
| 0x09 | CreatePrivateRoom | `estr` session, `wstr` room name | as 0x0C: name, text, members, moderators (all empty when it fails) | 0 ok, 1 the name is taken. Creates the chat room of a game with the sender as its owner and first member. On result 0 the game goes on to send 0x19 (D7, `FIXES.md` 7). [T: steps 18 and 25] [R: seen on the wire with the real client, live-rig.md section 19.6] |
| 0x19 | SetRoomBanner | `estr` session, `wstr` room name, `wstr` text | — | 0 ok, 1 no such room or the sender does not own it. Sets the room's text, cut at 1000 characters; a player entering the room is shown it (0x0C). The game sends it after a successful 0x09, with a fixed line saying that the room is private to the game [G: 0x32ef50, 0x32f038] (`FIXES.md` 7). [T: step 25] [R: seen on the wire with the real client, live-rig.md section 19.6] |

The unmodified server had no handler for 0x19, 0x63 and 0x64, three requests the game
does send; the fork has, and they are in the table above. A request with an id the
server does not know is logged ("unknown packet id") and gets no reply
[S: Include/Network/Events.hpp].

The executable also contains builders for ids 0x00, 0x03, 0x04, 0x07, 0x0B, 0x10, 0x12–0x14,
0x1A, 0x1B, 0x1E, 0x1F, 0x28, 0x29, 0x45, 0x46, 0x52 and 0x53 that nothing calls directly
[G: 0x37d674–0x37f59c]. They were not examined.

### Notifications sent by the server

| id | name | body | sent to, when |
| --- | --- | --- | --- |
| 0x3E | GameDiscovered | `nstr` address, `u32` port | a host, when its first discovery datagram arrives: its own address as the server saw it. Opens the game. [T] [R: seen on the wire with the real client, live-rig.md section 19.6] |
| 0x40 | ClientDiscovered | `nstr` address, `u32` port | a joiner, for each discovery datagram while the game is open: its own address as the server saw it. [T] [R: seen on the wire with the real client, live-rig.md section 19.7] |
| 0x65 | ClientRequestConnect_RTA | `nstr` LAN address, `u32` LAN port, `nstr` observed address, `u32` observed port | the host, at the same moment: the joiner's two addresses. [T] [R: seen on the wire with the real client, live-rig.md section 19.7] |
| 0x2F | FriendStatus | `wstr` chat handle, `u8` 1 online / 0 offline | everyone **on the list of** the user who logs in or disconnects (not everyone who lists that user). The game parses it and does nothing with it: its handler is an empty function [G: 0x330028]. |
| 0x30 | InstantMessage | `wstr` sender handle, `wstr` text | the addressee of 0x21. [T] |
| 0x3D | RoomMessage | `wstr` room, `wstr` sender handle, `wstr` text | room members. Also sent with an empty sender when someone enters a game's chat room. [T] [R: seen on the wire with the real client, live-rig.md section 19.8] |
| 0x41 | ForcedLogout | `u16` 0. With the header that is **12 bytes on the wire**: `00 00 00 0c`, `41 00`, `u32` 0, `u16` 0 | the earlier connection of an account that has logged in again, which the server then closes; and every connection when the server shuts down. The game reads the 16-bit field and does not use it [G: 0x387388, case at 0x388654, handler 0x3301f0]; the unmodified server sent a `u32` there, 14 bytes in all (`FIXES.md` 17). On the real client the handler cleared the logged-in bit of the client's flag word, which a plain lost connection does not do, and the game then went on as after a lost connection (section 8.9). [T: step 31] [R: seen on the wire with the real client, live-rig.md section 20.1] |

The game also parses notifications 0x2A–0x3C (two or three strings each: room and friend
events), 0x4C, 0x4F and 0x51 [G: 0x387388]. This server never sends them and their
meanings were not worked out.

## 8. Flows

`C` is a console, `S` the server. Tracking numbers and the common headers are left out.

### 8.1 Create an account

```
C -> S:40810   0x43                        S -> C  lobby address, port
C -> S:lobby   0x27                        S -> C  key
C -> S         0x42 language, country      S -> C  the text of the terms screen
C -> S         0x06 name, password, e-mail, date of birth, chat handle
                                           S -> C  result 0, session id
```
The game copies the chat handle the user typed into its own "my handle" field before
sending [G: 0x330950]. The server's length checks for names and passwords exist but are
never called; a chat handle longer than 15 characters is refused, because the game drops
a whole list of names when one name in it is longer [S: RequestCreateAccount.cpp;
`FIXES.md` 15]. The game's form has six fields (the password twice) and sends five
strings; after result 0 it shows a notice and goes on exactly as after a login, with the
requests of 8.2 [R: seen on the wire with the real client, live-rig.md section 19.4].

### 8.2 Log in

```
C -> S:40810   0x43      then on the lobby connection      0x27
C -> S         0x16 name, password         S -> C  result 0, session id, chat handle
C -> S         0x0E, 0x61                  S -> C  the rooms; friends, friends online, ignored
C -> S         0x5B                        S -> C  the account's characters
C -> S         0x0C first room's name      S -> C  the room and its members
C -> S         0x55, 0x0E                  S -> C  the game list; the rooms once more
      ... and 0x55 again about every 710 frames while the list is on the screen ...
```
The requests after the login are the game's own sequence; the server asks for none of
them [R: seen on the wire with the real client, live-rig.md section 19.4].

The server loads the friend and ignore lists and sends 0x2F to those friends who are
online. A login for an account that is still connected is accepted: the newcomer has
shown that it knows the password, so the earlier session is ended, and its connection is
sent 0x41 and closed (`FIXES.md` 13; 8.9) [T: step 31] [R: seen on the wire with the real
client, live-rig.md section 20.1]. A console that logs in on the very connection it has
just created the account on is not a second login [S: RequestLogin.cpp]. The unmodified
server answered result 1 in both cases.

### 8.3 Characters (stored on the server)

A character is two things: a short list of key/value strings for the selection screen, and
an opaque data block. The keys the game uses are `name`, `raceandclass` (two numbers),
`level` and `ability` (six numbers) [G: strings from 0x554aa0, used at 0x327988 and
0x327dc8]. The server accepts at most four pairs.

```
list     C -> S  0x5B                       S -> C  ids and key/value lists
create   C -> S  0x58 keys, values, first piece      (no reply yet)
         C -> S  0x5D piece, flag 0   ...            (no reply)
         C -> S  0x5D last piece, flag 1    S -> C  the reply to 0x58: result, new character id
save     C -> S  0x5E whose, id, keys, values, first piece, then 0x5D as above
                                            S -> C  the reply to 0x5E: result, after the last piece
load     C -> S  0x5C id                    S -> C  1024-byte piece, flag 0  ...
                                            S -> C  last piece padded to 1024, flag 1
delete   C -> S  0x5A id                    S -> C  result
```
- The game cuts the data into pieces of 800 bytes, the first inside the request, and
  sends one per lobby tick, re-using the tracking number of the request that started the
  upload [G: 0x37ca08, 0x380888]. When everything fits into the request it still sends
  one more piece, flagged and empty (`FIXES.md` 5) [T: step 17].
- **One upload has one reply**: to the request that started it, under that request's id
  and tracking number, after the last piece — for 0x58 with the id of the new character.
  The game parses a reply by the request it has pending under the tracking number
  (section 2), has no case for a reply to 0x5D, and files the id for its later saves
  (D5, `FIXES.md` 5). With the real client: a new level-1 character packed to 1,109
  bytes and went up as a 0x58 with a first piece of 800 bytes and one 0x5D with the
  other 309 and the flag, under the same tracking number; one reply came back, numbered
  0x58, result 0, with the id, and the game took it [R: seen on the wire with the real
  client, live-rig.md section 19.5].
- The server stores nothing until a piece arrives with the flag set. It then checks that
  the block, read as "four header bytes, then bytes where every zero byte is followed by a
  repeat count", expands to at least 19,504 bytes, and cuts off anything after that point
  [S: Source/Game/RealmCharacterSaveTask.cpp]. When the check or the database write
  fails, or the account already has twelve characters, the reply says so with result 1
  (`FIXES.md` 5) [T: step 17].
- Any member of a party can save any other member's character: 0x5E names the target by
  session id, and the server writes to whatever character that target last created or
  loaded; the id in the request is read and not used [S: RequestSaveCharacter_RTA.cpp].
  This is how the game saves, not a hole it never uses: see 8.8.
- Reply frames of a load all carry the request's tracking number. A character whose
  upload had been 1,109 bytes came back as one frame of 1,024 bytes with the flag set:
  the server keeps of an upload what expands to a full record, and pads the last piece
  [R: seen on the wire with the real client, live-rig.md section 19.8].
- **Where the player meets the stored characters.** They are not offered first. "Host"
  and "join" always open the new-character screens; the characters kept by the server
  are behind "import" (triangle) on that screen, in one list with those on the memory
  card and marked as network characters. Opening that list sends 0x5B again, and
  choosing one sends 0x5C with its id. A character made on those screens is uploaded
  with 0x58 when its name is confirmed, before the create-game form appears [R: seen on
  the wire with the real client, live-rig.md sections 19.5, 19.8 and 19.13].

### 8.4 Create a game (public or private)

```
host -> S   0x54 game info, LAN address, UDP port      (private: 0x56 name, LAN address, port)
                                            S -> host  result 0, discovery address, port
host -> S   0x09 game name                  S -> host  result 0 and the room, as for 0x0C
host -> S   0x19 game name, a fixed line    S -> host  result 0        (the room's text)
host -> S:discovery (UDP)  session datagram, repeated
                                            S -> host  0x3E  host's address as observed
```
- The public game went exactly so between the real client and the server, and after
  0x3E the game's room listed the host's character and offered "start". Around it the
  game moves between chat rooms by itself: 0x15 for the public room when "host game" is
  chosen, and 0x15 then 0x0C for the public room once the game's room exists [R: seen on
  the wire with the real client, live-rig.md sections 19.5 and 19.6]. The private form
  (0x56) was not run with the real client.
- Game info is five two-digit numbers, commas, a bar, and the game's name:
  `NN,NN,NN,NN,NN|name` [G: format string used at 0x32aa48; parsed back at 0x329440]. The
  server project reads the numbers as difficulty, game mode, arena kill count, mission and
  network-save flag; it stores the whole string and hands it back unchanged in the list.
- "LAN address" is the console's own interface address as dotted text, or `0.0.0.0` if it
  cannot find one; "UDP port" is the local port of its game socket [G: 0x32aa48]. The
  real client sent the address its network had given it and port 4001 (section 9.1), and
  a game info of the form above, `01,00,00,00,01|` and the name [R: seen on the wire with
  the real client, live-rig.md section 19.6].
- The game stays unlisted ("not ready") until the datagram arrives. At that moment the
  server freezes the host's two addresses for the listing [S: GameSessionManager.cpp].
- A private game differs only in not being listed by 0x55; it is found by exact name
  with 0x57.

### 8.5 Find and join a game

```
joiner -> S  0x55                           S -> joiner  the list
   (private game:  0x57 name                S -> joiner  game id and the host's addresses)
joiner -> S  0x66 game id, LAN address, UDP port
                                            S -> joiner  result 0, discovery address, port
joiner -> S:discovery (UDP)  session datagram, repeated
                                            S -> joiner  0x40  joiner's address as observed
                                            S -> host    0x65  joiner's LAN and observed address
      ... consoles connect to each other directly (section 9) ...
joiner -> S  0x5F                           S -> joiner  result 0   (now a member)
```
The 0x55 reply is eight parallel arrays, each with its own count [G: 0x3841dc case 0x55,
handler 0x329440]:

| # | type | content | limit in the game |
| --- | --- | --- | --- |
| 1 | `wstr[]` | game info strings | 256 characters |
| 2 | `wstr[]` | a short text per game; this server sends empty strings; meaning Unknown. Nothing was visibly missing on the game's list screen [R: seen on the wire with the real client, live-rig.md section 19.12] | 15 characters |
| 3 | `u32[]` | game ids. The game sends the id back unchanged in 0x66; the first column of its list screen showed the id plus one, and what that column is meant to hold is Unknown [R: seen on the wire with the real client, live-rig.md section 19.12] | |
| 4 | `blob[]` | one blob per game; this server sends an empty one for each (D1, `FIXES.md` 1) [T: step 24] | |
| 5 | `wstr[]` | host's LAN address | 512 |
| 6 | `u32[]` | host's LAN port | |
| 7 | `wstr[]` | host's address as observed by the server | 512 |
| 8 | `u32[]` | host's port as observed by the server | |

The server lists games that are public and open; started and cancelled games are gone.
A game holds four members. When the result is not 0 the eight counts are still there,
all zero (section 7).

With the real client, one game open: the other machine's list showed it after its next
0x55 — one entry in each array, the blob empty — and the join ran as drawn above. On the
host's peer "welcome" the joiner sent 0x5F with its own session id and the host's, was
answered 0, entered the game's chat room with 0x0C (the reply carried the text the host
had set with 0x19, and both members) and left the public room. Only then did it get its
character screens [R: seen on the wire with the real client, live-rig.md sections 19.7
and 19.8]. A list of two or more games, and the private path through 0x57, have only
been run with the test client [T: steps 23 and 24].

### 8.6 Start or cancel

```
host -> peers   "start" (peer-to-peer)          host -> S  0x23      S -> host  result, u32 0
everyone -> S   0x15 public room                S -> ...   result 0
anyone  -> S    0x05 then 0x60                  S -> ...   result 0 for each
```
The host tells its peers first and does not wait for the server [G: 0x330a40]. The server
forgets a started game entirely. With the real client the 0x23 reply (result 0 and the
`u32`) was taken, both machines left the public chat room, and about 600 frames later
both were in the first level [R: seen on the wire with the real client, live-rig.md
section 19.10]. Cancelling (0x05, 0x60) was not run with the real client [T: steps 20 to
22].

When a lobby connection closes, a game owned by that user is deleted, and a member who
was not the owner gives its place back (D8, `FIXES.md` 8) [S: GameSessionManager.cpp,
`OnDisconnectUser`] [T: step 22]. That stays so when the user's session is picked up
again afterwards (8.9).

### 8.7 Friends and chat

- Friends and ignores are lists of chat handles kept per account. Adding either needs the
  other person to be online at that moment. Only the owner's side is stored; nothing asks
  the other person.
- 0x21 delivers a private message (0x30) if the addressee is online and not ignoring the
  sender.
- Public rooms are fixed; a game's room is created with 0x09, given its text with 0x19,
  and closed when the game starts. 0x0C/0x15 enter and leave, 0x22 talks.
- Friends, ignore, instant messages and chat typed by a player were not run with the
  real client [T: step 19]; the room requests the game sends by itself were (8.2, 8.4 to
  8.6).

### 8.8 During play

The lobby connection stays open while a launched game runs. The server has no part in
the game itself: it has forgotten the started game (8.6), and all game traffic is console
to console (section 9). What still crosses the connection [R: seen on the wire with the
real client, live-rig.md sections 19.10, 19.11 and 20.2]:

- **Character saves.** About every 2,100 to 2,400 frames a machine sends 0x5E — its own
  session id, the session id of the player being saved, that character's id, the four
  keys and values, a first piece of 800 bytes — and a last 0x5D piece under the same
  tracking number. The server answers once, result 0, under 0x5E.
- **Each machine saves the other players' characters too, not only its own.** In one run
  each machine saved only the *other* player's character; in another each saved both in
  turn. Which machine saves which player is drawn from the game's shared random seed
  [G: 0x1eb5c8]. So "any member can save any other member's character" (8.3) is the
  game's ordinary way of saving, and a server that accepted a save only from the
  character's owner would lose saves. The character loaded at the next login carried
  what the earlier game had given it. (`FINDINGS.md` row V52.)
- No other request was noted during play. Whether the keep-alive frames of section 2 go
  on then was not recorded. (Inferred from the numbers alone: saves 35 to 40 seconds
  apart at full speed keep a connection inside the default `client_timeout` of 120.)

**The character checksum exchange is not part of this protocol.** While a
lobby-launched game runs, the consoles compare checksums of each other's characters every
240 ticks, in the game's own peer-to-peer messages; the server is not asked and is not
told. Its outcome is game-side too: a mismatch makes a machine drop the other player, and
each machine ends up back at the lobby's game list, still logged in — which is all the
server sees of it. For what the exchange is, see `FINDINGS.md` rows B1 and B2; for it
running with the real client, and for what a difference made on purpose did, row V51
(live-rig.md section 19.11).

A machine that falls silent in mid-game is the same to the server as any silent
connection: it is timed out after `client_timeout`, and its session is kept as lost (8.9).
The other machine drops the silent player on its own and is back at the game list, its
0x55 answered as usual [R: seen on the wire with the real client, live-rig.md section
20.4].

### 8.9 A lost connection, and a forced logout

**What the game does.** When its connection to the server is gone, the game notices on
its next send and **connects again by itself**: gateway (0x43), lobby, key exchange
(0x27), as in section 5. **It does not log in again.** Its first request on the new
connection is whatever it would have sent next, and it carries the old session id: on the
game list the periodic 0x55, during play a character save (0x5E). It was back about 20
frames after the failed send on the game list, and about 600 frames after the loss
during play. A machine that was filling in the account form when the connection went
sent its 0x06 on the new connection as if nothing had happened [R: seen on the wire with
the real client, live-rig.md sections 19.9, 20.1 and 20.2].

**The server's resume rule** (`FIXES.md` 16 and 19) [S: Source/Game/RealmUserManager.cpp,
`OnConnectionLost` and `ResumeSession`; LobbyServer.cpp, `HandleRequest`]. When the
connection of a logged-in Return to Arms user ends without a logout — closed, reset or
timed out — the server keeps the session for `client_timeout` seconds: the id, the
account, the names, the current character, the public chat room, and the address the
connection came from. A connection that is not logged in has the session id of each
request looked up there before the request is handled; every request starts with one
except 0x06, 0x0F, 0x16, 0x27, 0x42, 0x43 and 0x64 [G: header writers 0x37cd14 and
0x37cc64]. When it is the id of a lost session, the connection becomes that session's.
A session is picked up

- only when its connection is gone: while a connection still holds it, the id gets
  nobody else in, and the holder is not disturbed;
- only from the address the lost connection came from, which is also what a discovery
  datagram has to meet (section 6);
- only within `client_timeout` seconds of the loss, and once;
- not after a logout (0x17), and not after the account has logged in again.

The user comes back in the public chat room it was in: the game still shows that room,
does not ask to enter it again, and asks to leave it (0x15) when it moves on. It does
not come back into a game it had opened or joined, nor into that game's chat room: the
lost connection ended those (8.6). [T: steps 34, 35 and 37 to 40;
`tools/lobby_fix_checks.py` for the address and the time limit]

**A connection that is not logged in and has no session to pick up** gets **result 7**
for 0x55 — the client's "invalid session" (section 2) — with eight empty arrays, no 0x41,
and the connection left open [T: steps 36 to 39]. The unmodified server answered result
0 with an empty list, sent 0x41 and closed; the game then connected and asked again,
about every 650 frames, for as long as it was left alone [R: seen on the wire with the
real client, live-rig.md section 19.9].

**As the real client met the rule** [R: seen on the wire with the real client,
live-rig.md sections 20.1 and 20.2]:

| case | what the server did | what the game did |
| --- | --- | --- |
| connection lost on the game list, the game back within `client_timeout` | first 0x55 under the old id: result 0 and the list, on a connection that stays open | no loop any more: it went on asking every 725 frames on the one connection. But its own notice of the lost connection was already over the list, and the only way out of that notice is to leave the lobby: 0x15 for the public room, the network menu, the login screen, and an ordinary 0x16 with a new session id. **A session picked up on the game list cannot be used from there** |
| the same, kept away for longer than `client_timeout` | every 0x55: result 7, eight empty arrays, connection left open | 0x55 every 725 frames, each answered 7; nothing new on the screen, the same notice; then out as above |
| connection lost during play | the next request was a save, 0x5E under the old id: picked up, result 0 | the saves went on as before, nothing appeared on the screen, and the lockstep game was not affected (it does not use this connection). **This is where picking a session up helps a player** |
| a second login to the same account from another machine | 0x41, 12 bytes, to the first connection, which was then closed | the 0x41 handler ran (it cleared the logged-in bit of the client's flag word); then as after a lost connection: reconnect, the notice, 0x55 under the old id, result 7 each time |

Not seen with the real client: result 7 on its own, without a lost connection before it
(the game showed nothing new for it because its lost-connection notice was already up;
live-rig.md section 20.6), and the chat room of a session that is picked up. In the run
of 20.1 the server did not yet restore the room, and the game's 0x15 on leaving the lobby
was answered with result 1, which the game ignored (S6 there). The fix (`FIXES.md` 19)
came after that run and has been through the test client only [T: step 40].

## 9. How two consoles learn each other's address

This decides whether players behind home routers can connect, so it is spelled out.

### 9.1 What the server knows and where it comes from

For each player in a game the server has two address/port pairs:

- **LAN pair** — whatever the console wrote into 0x54/0x56/0x66. The server cannot check
  it. Behind a router it is a private address such as 192.168.x.x.
- **Observed pair** — the source IP and source port of that console's discovery datagram
  **as it arrived at the server machine**. Behind a router this is the router's public
  address and whatever port the router chose for the console's game socket. If the console
  and the server are on the same LAN it is the console's LAN address.

The observed port is valid for the game socket because the datagram leaves from that very
socket (section 6). **The game socket's local port is one of 4000 to 4004.** 4001 and 4004
were seen, the port being chosen anew in each run; it is the port the console reports in
0x54 and 0x66 and the port its discovery datagram leaves from [R: seen on the wire with
the real client, live-rig.md sections 19.6, 19.8 and 19.13]. This is what the code
suggested: the UdpManager is created with the values 4000 and 5 in the slots that, in
SOE's UdpLibrary, are "port" and "port range" [G: 0x32a650]; the binding code itself was
not read. Behind a router the observed port is whatever the router makes of it.

### 9.2 Who is told what

| who | is told | by |
| --- | --- | --- |
| host | its own observed pair | 0x3E |
| joiner | its own observed pair | 0x40 |
| joiner | host's LAN pair and observed pair | 0x55 arrays 5–8, or the 0x57 reply |
| host | joiner's LAN pair and observed pair | 0x65 |
| later joiners and earlier joiners | each other | not by the server — the host passes its peer list along peer-to-peer [G: 0x32bce8, 0x32a1b8] |

The server takes no further part. All game traffic is console to console over UDP.

### 9.3 What the consoles do with the addresses

Each console keeps, per peer, an "external" slot and an "internal" slot (address + port)
[G: peer record offsets 0x90/0x98 and 0x94/0x9a; the game's own debug texts call them ext
and int].

- **Host**, on 0x65: starts a UdpLibrary connection to the joiner's external pair, and a
  second one to the internal pair *only if both the address and the port differ* from the
  external pair [G: 0x329ec8 → 0x329d58]. It also puts the joiner on its seek list. Both
  attempts were made by the real client: a 14-byte UdpLibrary connect request to the
  joiner's observed pair and another to its LAN pair, each repeated about every 125
  frames [R: seen on the wire with the real client, live-rig.md sections 19.7 and
  19.13].
- **Joiner**: put the host on its seek list when it sent 0x66 [G: 0x32aeb0, 0x329880].
  It does not open a connection itself (the only caller of the connect routine on this
  path is the 0x65 handler). Instead, on every tenth lobby tick, it sends a one-byte
  datagram to the **external** pair of every peer on its seek list, giving up on a peer
  after 15 seconds [G: 0x32a4b8]. The host does the same toward the joiner. These
  datagrams are what open the senders' routers for the other side. From the real client
  the datagram is the single byte 01, sent to the host's observed address about every
  200 frames; when nothing came back, the game said after eight of them that it could
  not connect to the host [R: seen on the wire with the real client, live-rig.md section
  19.7].
- **Either side**, when a connection arrives: it is accepted if its source address equals
  a sought peer's external address (any port), or equals the internal address with the
  internal port. A console that is not the host drops any other connection; the host lets
  strangers in [G: 0x32c2c0].
- When the joiner gets the host's "welcome" over that connection it sends 0x5F to the
  server [G: 0x32ca18] [R: seen on the wire with the real client, live-rig.md section
  19.8, which also lists the datagrams of the handshake by size].

So the scheme is ordinary UDP hole punching, coordinated by the lobby server:

- It works when each router gives the game socket the same public port toward the other
  console as it gave toward the server (most home routers), because then the observed pair
  is where the other console's packets must go.
- It fails for a console whose router picks a new public port for every destination
  ("symmetric" NAT) unless the other side accepts by address alone and is reachable — the
  accept rule above tolerates a different port on the external address, the router of the
  receiving side may not.
- Two consoles behind the same router are told each other's public address. The internal
  pair is tried by the host only when the router changed the port number, and the joiner's
  one-byte datagrams never go to the internal pair, so this case leans on the router
  looping traffic back (hairpinning). The rig is this case: the server saw both machines
  at one address with different ports and told each to find the other there. Nothing
  arrived until that address looped back to the other machine; then the join went
  through, while the host's second attempt, to the joiner's LAN pair, went nowhere [R:
  seen on the wire with the real client, live-rig.md sections 19.7 and 19.8].
- **A console on the same LAN as the server is observed with its LAN address.** Players
  outside that LAN are then told a private address for it and cannot reach it. Someone
  hosting the server at home and playing from the same network will be unreachable for
  friends elsewhere, unless that console's traffic to the server goes out through the
  router and back (again hairpinning, with the server addressed by its public address).
  The fork has a setting for this, `report_public_ip_for_lan_consoles`, with its limits
  written down in `FIXES.md` 12; it was not exercised end to end.
- The server refuses a discovery datagram whose source IP differs from the source IP of
  the same user's TCP connection, so the two must leave through the same public address.

### 9.4 Whose address is which on the wire

The game reads **internal first, external second** in all three places:

| message | internal pair | external pair | evidence |
| --- | --- | --- | --- |
| 0x55 reply | arrays 5, 6 | arrays 7, 8 | [G: call at 0x3867b0 passes arrays 7/8 first; handler 0x329440 stores them at record+0xac/+0xb4, which the join code copies to the external slot] |
| 0x57 reply | first `wstr`/`u32` | second `wstr`/`u32` | [G: 0x386a68–0x386b6c → handler 0x329880] |
| 0x65 | first `nstr`/`u32` | second `nstr`/`u32` | [G: 0x387388 case 0x65 → handler 0x329ec8] |

The server follows this in all three: in 0x55 and 0x65 as it always did, in 0x57 since
`FIXES.md` 2 (D2) [T: steps 9, 11 and 23]. The 0x55 reply and the 0x65 went to the real
client in this order, and the host's connection attempts and the joiner's datagrams went
to the pairs this table says [R: seen on the wire with the real client, live-rig.md
section 19.7]. 0x57 was not run with the real client.

## 10. What the server stubs, guesses or gets wrong

**This section is the record of the unmodified server**, kept as it was written on
2026-10-10. Every defect D1 to D10 below is fixed in the fork (`FIXES.md` sections 1 to
10, in the same order), and so are the stubs for 0x19, 0x63, 0x64, the middle list of
0x61 and the five numbers of 0x54 (`FIXES.md` 7, 11 and 15). D9 and D10, "read,
deliberately not tried" here, were tried against the old build afterwards and both are
real. Still as described at the end of this section: the key exchange, the ignored
search filter and array 2 of 0x55, the fixed label of 0x57, the filler in 0x0E and
0x0F, 0x11, 0x24, 0x44, and a session id that is not checked against the connection
except in 0x5A (and now when a lost session is picked up, 8.9). The fork's own list of
what it has not fixed is at the end of its `FIXES.md`.

Line numbers are for the checkout examined (local branch `macos-port`). Going by file
dates, every file named here except ByteStream.cpp and LobbyServer.cpp is unchanged from
upstream, so D1–D8 and D10 are upstream's. Those two files were edited by the port; whether
the lines cited in D9 were is not known. Git was not consulted.

Defects that change what players see:

- **D1 — game list breaks with two or more open games.**
  Source/Network/Event/RequestMatchGame_RTA.cpp lines 64–68 write array 4 as a count
  followed by a single `u32` 0 whatever the count is. The game reads `count` blobs. With
  one game the bytes happen to line up; with none, four stray bytes are ignored; with two
  or more the rest of the reply is misread and the game reports the request as failed.
  [G: 0x3df2cc] [T: extended step "two public games"]
- **D2 — private games hand the joiner the wrong addresses.**
  Source/Network/Event/RequestGetGame_RTA.cpp line 52 and lines 73–77 put the host's
  observed address first and its LAN address second, both with the observed port. The game
  takes the first as internal and the second as external (9.4). The joiner therefore aims
  its hole-punching datagrams at the host's LAN address, and accepts the host only if the
  host's packets arrive from the exact observed port. Private games can be expected to
  work on one LAN and through routers that let unsolicited packets in, and not otherwise.
  The LAN port the host reported is never sent. [T: extended step "private game"]
- **D3 — the console is not told its chat handle at login.**
  Source/Network/Event/RequestLogin.cpp line 121 sends a fixed placeholder as the second
  string. The game copies that string into the field holding its own chat handle
  [G: 0x32eba8 writes client+0xca1; 0x330950 fills the same field at account creation].
  What then misbehaves in the game was not traced. [T]
- **D4 — encryption of strings that are not a multiple of 16 bytes reads freed memory.**
  Source/Crypto/RealmCrypt.cpp lines 127–132 (and 147–152 for decryption): the padded copy
  is a vector local to the `if` block, and the function goes on using a view of it after
  the block has ended. The only string affected in practice is the 40-byte placeholder of
  D3, which on this build decrypts to bytes that change from run to run [T]. Session ids
  and the key are 32 bytes and are not affected.
- **D5 — creating a character looks like a failure to the game.**
  Source/Network/Event/RequestCreateNewCharacter_RTA.cpp lines 59–64 reply with a result
  only. The game reads a `u32` after it, treats its absence as result 45 and shows its
  network-save error; on success it would file the number as the new character's id
  [G: 0x3841dc case 0x58, 0x32fa60, 0x328090]. The server does store the character once
  the last piece arrives [T], and never reports a failed store (8.3).
- **D6 — start-game reply is short.** Source/Network/Event/RequestStartGame.cpp lines
  52–57: no `u32` after the result; the game reads one [G: case 0x23] and records result
  45. The peers have already been told to start, so the effect is probably limited to a
  status text (Inferred). [T]
- **D7 — game chat room reply is empty; 0x19 unknown.**
  Source/Network/Event/RequestCreatePrivateRoom.cpp lines 40–45 reply with a result only;
  the game parses name, banner, members and moderators [G: case 9] and so sees result 45,
  and skips 0x19. There is no handler for 0x19, 0x63 or 0x64
  (Include/Network/Events.hpp). [T]
- **D8 — backing out of a join deletes the host's game.**
  Source/Game/GameSession.cpp line 181 lowers the player count in `RemoveMember` whether
  or not the user was a member, and Source/Game/GameSessionManager.cpp lines 257–261 delete
  the game when the count reaches zero. A user who has sent 0x66 (or 0x57) points at the
  game without being a member; when it leaves, the game sends 0x05/0x60 and a one-player
  game disappears from the list while its host still waits. Likewise 0x23 from such a user
  starts (removes) the game: neither path checks ownership
  (GameSessionManager.cpp lines 322–356). [T: extended step "backs out"]

Robustness (read, deliberately not tried against the running server):

- **D9 — a malformed message stops the server.** Source/Common/ByteStream.cpp lines 198
  and 218 throw when a counted string runs past the end of the frame, and nothing between
  there and the lobby thread's entry catches it (Source/Lobby Server/LobbyServer.cpp,
  `HandleRequest`, lines 427–446). The zero-terminated readers (lines 237, 251) and the
  encrypted and raw byte readers do not check the frame length at all.
- **D10 — 0x61 or 0x62 sent to a gateway port dereferences a null user.**
  Source/Network/Event/RequestGetSocialListInitial.cpp lines 17–21 and 38, and the same
  lines of RequestGetSocialListUpdate.cpp.

Stubs and guesses that are visible on the wire:

- Key exchange always returns the built-in key (section 4).
- 0x54: the five numbers are parsed into a local array and thrown away; the array handed
  on (Source/Network/Event/RequestCreatePublicGame_RTA.cpp line 83) is never filled, so the
  session's difficulty/mode fields are indeterminate. They are not sent to anyone. A taken
  name gives result 2, not the 38 the project's own enum reserves for it.
- 0x55: array 2 is a member that nothing sets; the request's search filter is ignored.
- 0x57: the first string is a fixed label.
- 0x0E: three of four arrays are filler. 0x0F: seven of eight numbers are zero.
  0x61: the middle list is one fixed entry. 0x11 ignores the room name. 0x24 does nothing.
- 0x44 expects CON's data layout.
- The session id inside requests is not checked against the connection except in 0x5A.
- Seven source files in Source/Network/Event are leftovers that the build skips
  (Notify_4C, Notify_65, NotifyClientReqConnect, NotifyReserveUserSlot_RTA,
  RequestGetFriendList, Request_5F, Request_61).

## 11. Ports a server host must expose

Defaults of Champions Reborn [S: LobbyServer.cpp, configuration.cpp, bin/config.ini];
the gateway ports are fixed in the source, the other two are settings.

| port | protocol | purpose | needed for RTA |
| --- | --- | --- | --- |
| 40810 | TCP | RTA gateway — the port compiled into the game [G: 0x324920], and the one the real client connected to [R: seen on the wire with the real client, live-rig.md section 13.4] | yes |
| 40811–40817 | TCP | seven more RTA gateway listeners, identical in behaviour | no use by the game was found in the connect code (0x387124, 0x388a34); expose them if in doubt |
| 40910 (`rta_lobby_port`) | TCP | RTA lobby — whatever the gateway hands out | yes |
| 10101 (`discovery_port`) | UDP | discovery datagrams, inbound only | yes |
| 40800–40807, 40900 (`con_lobby_port`) | TCP | the same for Champions of Norrath | only for CON |

`public_ip` in config.ini is handed to consoles twice: as the lobby address (gateway
reply) and as the discovery address (create/join replies). It must be an address every
player's console can reach, and the UDP port must be reachable at that same address.

Consoles need no inbound port opened toward the server. Between consoles, traffic is UDP
on the game socket of each, a port from 4000 to 4004 (section 9.1); the server relays
nothing.

One more setting matters to players: `client_timeout`, the seconds a silent connection is
kept and a lost session can be picked up again (120 unless changed; sections 2 and 8.9).

## 12. Champions of Norrath differences

Read in the server source only [S]; not tested.

- Version field 2; its own gateway and lobby ports.
- Addresses in replies and notifications are zero-terminated byte strings instead of
  `nstr` (0x43, 0x08, 0x0A, 0x25, 0x3E, 0x3F, 0x40).
- Login is a fixed name and password; there are no accounts or server-side characters.
- Create game 0x0A / 0x08, list 0x18, find 0x0D, join 0x25, host notified with 0x3F (one
  address pair: the joiner's observed address). No LAN addresses are exchanged; the list
  gives each host as one `address:port` string, substituting the host's LAN address when
  the asker has the same public address.
- The server's note says CON consoles simply disconnect when the game starts.

## 13. Open questions

Answered since this list was first written, and now in the text: what keeps an idle
connection alive (section 2), the form of the `nstr` in 0x27 (section 4), the two strings
of 0x42 and the middle list of 0x61 (section 7), what 0x19, 0x63 and 0x64 are for
(section 7), and that the console binds UDP 4000 to 4004 (section 9.1).

Still open:

- Whether the game ever uses gateway ports other than 40810. The real client used 40810
  where the port was recorded (live-rig.md section 13.4), and the connect code shows no
  other.
- What the 32 hexadecimal digits in 0x27 are made from, and what the original service
  did with them; array 2 and array 4 of the game list; the first column of the game's
  list screen, which showed the game id plus one (live-rig.md section 19.12, S4); the
  last three arrays of 0x0E; the `u32` the game reads after the result of 0x23.
- Notifications 0x2A–0x3C, 0x4C, 0x4F, 0x51: purpose and exact fields.
- What the game sends to the server after a failed join (the "backing out" path of D8
  is inferred from 0x3309c8 having the only cancel calls; live-rig.md section 19.7 has
  the game's notice that it could not connect, not what it sent after it).
- What the game's connect handler does when it is told −6 for result 7 (not followed in
  the code), and what a player sees for result 7 on its own: with the real client the
  lost-connection notice was already on the screen each time (section 8.9).
- What the game does when its connection is lost while it sits in a game's room before
  the start. The server brings such a session back without its game and without the
  game's chat room (section 8.9); this was not run.
- The fields of the peer-to-peer messages after the connection is up (welcome, known
  peers, character info, start, eject). Their order and sizes were seen (live-rig.md
  section 19.8); for the fields see `docs/netlib.md` and `symbols/netlib.tsv`.
- Everything listed at the top as not run with the real client, and anything on a
  console or in a second emulator. The rig's two machines also sit behind one address
  that loops back by construction; two consoles behind two real routers have not met
  through this server.
