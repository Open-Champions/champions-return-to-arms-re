# Lobby protocol (Return to Arms ↔ matchmaking server)

What the game says to its matchmaking ("lobby") server, what it expects back, and how two
consoles end up with each other's address. Written from three sources, and every claim is
tagged with the one it rests on:

- **[S]** read in the Champions Reborn server source (github.com/HikikoMarmy/Champions-Reborn-Server,
  AGPL-3.0; file named, paths relative to that repository). This says what *that server*
  does, which is not always what the game expects.
- **[G]** read in the game executable SLUS_209.73 at the address given. This says what the
  game sends and how it parses replies.
- **[T]** exercised against a running Champions Reborn server (the local macOS port, built
  2026-10-09) on loopback with `tools/lobby_e2e_test.py`.

Nothing here was confirmed with a real console or an emulator. "Observed" below means [S],
[G] or [T]; "Inferred" and "Unknown" are marked.

Names of messages are the server project's; the game has no names for them, only numbers.
Champions of Norrath ("CON") uses the same protocol with small differences, collected in
one section at the end.

## 1. Result of the end-to-end test

`python3 tools/lobby_e2e_test.py 127.0.0.1` simulates two consoles and passes all 16 steps
[T]: gateway, key exchange, account creation, login, create public game, host discovery,
game list, join request, joiner discovery, each side told the other's address, a datagram
exchanged between the two reported addresses, join report, start, logout.

`--extended` adds optional flows. Characters, friends, ignore, instant messages, chat
rooms and cancelling work [T]. Six extended steps fail, each because of a server defect
listed in section 10.

## 1a. Update after the server fixes

The defects listed in section 10 were fixed in a fork of the server,
[TrustlessMike/Champions-Reborn-Server](https://github.com/TrustlessMike/Champions-Reborn-Server)
(branch `macos-port`; its `FIXES.md` describes each fix and how the right behaviour was
established from the game's own parser). Against that build `tools/lobby_e2e_test.py` passes
16 of 16 core steps and 33 of 33 with `--extended`; the unfixed build fails 17 of the 33
and stops on a malformed message. Still nothing has been run against the real game.

That work also corrected four statements in this document; the text below has not been
rewritten, so read it with these in mind:

- The keep-alive is known: the game sends an empty frame after about 10 idle seconds in
  the lobby (section 13 lists it as open).
- The game parses a reply according to the type of the request it has pending, not by the
  reply's own id.
- 0x62 returns "friends, friends online", not "friends, ignored".
- 0x5D (a piece of character data) has no reply of its own; the single 0x58/0x5E reply
  comes after the last piece and carries the new character id.

## 2. Transport and framing

- TCP, one request/reply stream per connection, plus one UDP datagram type (section 6).
- Every TCP message, in both directions, is `u32 length` **big-endian** followed by the
  payload; the length counts itself. Everything inside the payload is little-endian.
  [S: Source/Lobby Server/LobbyServer.cpp, Source/Network/RealmSocket.cpp] [T]
- Request payload: `u16 id`, `u32 tracking number`, `u32 version`, then the body. The
  version is 6 for Return to Arms and 2 for Champions of Norrath; the server reads and
  ignores it. [S: Include/Network/GenericNetRequest.hpp] [G: header writer 0x37cc64 writes
  id, tracking number and the first word of the API object]
- Reply payload: `u16 id` (same as the request), `u32 tracking number` (same as the
  request), `u32 result`, then the body. Result 0 is success. [S] [G: 0x3837bc]
- Notification payload (server to console, unasked): `u16 id`, `u32 0`, then the body. No
  result field. [S: Source/Network/Event/Notify*.cpp] [G: 0x387388 reads u16 then u32]
- The console matches a reply to its request by tracking number and picks the parser by id
  [G: 0x3841dc]. Notifications can arrive between a request and its reply [T].
- Server limits [S: LobbyServer.cpp]: an inbound frame longer than 2048 bytes (or with a
  length ≤ 0) closes the connection; a connection that sends nothing for 30 seconds is
  dropped. Which message the game uses to stay alive while idle is **Unknown** (the game
  has a builder for 0x24 "touch session" at 0x37d644 with no direct caller).
- The game gives each request a timeout, passed as the second argument of every request
  builder: 30 for most, 20 for the connect sequence and character transfers, 60 for the
  statistics request [G: e.g. 0x32aa48, 0x3278f0, 0x328360]. Inferred to be seconds.
- When the game cannot parse a reply it reports the request as failed with its own result
  code 45 (0x2d) [G: every error branch in 0x3841dc]. Result codes are mapped to on-screen
  texts `clientText1`…`clientText68` [G: 0x32d498].

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
bytes (two per character) and the ciphertext is the UTF-16LE text zero-padded to a multiple
of 16 bytes and encrypted with AES in ECB mode (no IV, no chaining).
[S: Source/Common/ByteStream.cpp] [G: 0x388c50 encrypts, 0x38a0dc writes] [T]

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
- **Server shortcut:** Champions Reborn ignores the request body and always returns the
  default key, so in effect every connection uses the published default key. The original
  service presumably issued a per-session key (the project's own source comment says so);
  what the `nstr` in the request meant to it is **Unknown**.

## 5. Connecting: the gateway step

1. The console opens TCP to the gateway. The host name `con.soegames.net` and port 40810
   are compiled in [G: 0x324920 builds the API object with them]. A replacement server is
   reached by making that name resolve to it; how is outside this document.
2. On connect it sends 0x43 (body: `u32` 12) [G: 0x37cec4, sent from 0x388a34].
3. The reply body is `nstr address`, `u32 port`. The console drops the gateway connection
   and connects to that address and port — the lobby [G: 0x387124]. The address string is
   resolved with the console's name-to-address call, so a dotted address works; whether a
   host name works was not checked.
4. On the lobby connection it sends 0x27 (section 4), then reports "connected" to the
   game. If either step fails it starts again at the original host and port [G: 0x387124].

The server answers 0x43 on any of its gateway ports with the `public_ip` from its
`config.ini` and its lobby port [S: RequestGetServerAddress.cpp, Source/configuration.cpp].
A connection to a gateway port has no user attached, so nothing but 0x43 is meaningful
there. A connection to the lobby port gets a user record at accept time [S: LobbyServer.cpp].

## 6. The UDP discovery datagram

One datagram type exists. Payload, 36 bytes: `u32 0x20`, then the 16-character session id
as UTF-16LE (32 bytes) AES-encrypted with the connection key [G: 0x37cbcc builds it;
0x32a8d0 sends it] [S: Source/Discovery Server/DiscoveryServer.cpp] [T]. It is the body of
an `estr` without the leading unit count.

- The console sends it to the address and port it was given in the reply to a create-game
  or join request, **from the same UDP socket it will use for game traffic** [G: 0x32a8d0
  takes the socket from the object the UdpManager was built on, 0x32a650].
- It is re-sent on every tenth lobby tick for as long as the console is waiting for the
  matching notification (0x3E for a host, 0x40 for a joiner) [G: 0x32d368, flag bit 2 of
  the word at client+0x64; cleared at 0x330128 and 0x32a0d0].
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
the user by the TCP connection and ignores the `estr session` it is sent.

### Requests used by Return to Arms

| id | name | request body | reply body after `u32 result` | results and remarks |
| --- | --- | --- | --- | --- |
| 0x43 | GetServerAddress | *u32 12* | `nstr address`, `u32 port` | gateway step [T] |
| 0x27 | GetEncryptionKey | *nstr*, *u32 12* | `u32` cipher length + 4, `u32` key length, ciphertext | section 4 [T] |
| 0x06 | CreateAccount | `estr` user name, `estr` password, `estr` e-mail, `estr` date of birth, `estr` chat handle | `estr` session id (empty on failure) | 0 ok, 1 failed (name taken, empty field, database). The connection is logged in afterwards. User names are unique, chat handles are not checked. [T] |
| 0x16 | Login | `estr` user name, `estr` password | `estr` session id, `estr` placeholder | 0 ok, 1 already logged in, 4 unknown account or wrong password. The game stores the second string as its own chat handle (section 10, D3). [T] |
| 0x17 | Logout | `estr` session | — | always 0; removes the user. [T] |
| 0x24 | TouchSession | `estr` session | — | always 0; does nothing. [T] |
| 0x42 | GetRules | *nstr*, *nstr* | `wstr` text | fixed welcome text; the two request strings (language?) are ignored. [T] |
| 0x0F | GetRealmStats | — | eight `u32` | first = number of lobby connections; the other seven are always 0. [T] |
| 0x54 | CreatePublicGame_RTA | `estr` session, *u16 1*, *u32 0*, *u32 50*, *u32 10*, `wstr` game info, *attribute list (u32 count 0)*, *blob (empty)*, `wstr` own LAN address, `u32` own UDP port, *wstr (empty)*, *u32 0* | `nstr` discovery address, `u32` discovery port | 0 ok, 2 failed (name in use). Game info is `NN,NN,NN,NN,NN\|name` (section 8.4). [T] |
| 0x56 | CreatePrivateGame_RTA | `estr` session, `wstr` game name, `wstr` own LAN address, `u32` own UDP port, *wstr (empty)*, *u32 0* | as 0x54 | 0 ok, 1 no user, 2 name in use. [T] |
| 0x55 | MatchGame_RTA | *estr session, u16, u32, u32, u32, filter list, u8, u32, u32* | eight arrays, section 8.5 | always 0. The server ignores the whole request and lists every open public RTA game. Defect D1. [T] |
| 0x57 | GetGame_RTA | `estr` session, `wstr` game name | `wstr` label, `u32` game id, `wstr` address, `u32` port, `wstr` address, `u32` port | 0 ok, 1 full or no host, 2 not found. Finds public and private games by exact name. Defect D2. [T] |
| 0x66 | DoClientDiscovery_RTA | `estr` session, `u32` game id, `wstr` own LAN address, `u32` own UDP port | `nstr` discovery address, `u32` discovery port | 0 ok, 1 no user, 2 no such game. Marks the user as wanting to join that game. [T] |
| 0x5F | UserJoinSuccess | `estr` session, *estr host's session id* | — | 0 ok, 1 failed (no game, not open, full, already a member). Adds the sender to the game. Sent by the joiner after the host's peer "welcome" [G: 0x32ca18]. [T] |
| 0x23 | StartGame | `estr` session, *u8 0, u16 0, three empty lists* | — | 0 ok, 1 failed. Removes the game from the list and closes its chat room. The game expects a `u32` after the result (D6). [T] |
| 0x60 | CancelGame_RTA | `estr` session | — | always 0. Takes the sender out of its game; an empty game is deleted. Defect D8. [T] |
| 0x05 | CancelGame | `estr` session | — | always 0; does nothing for an RTA connection. The game sends 0x05 and then 0x60 every time it leaves a game [G: 0x3309c8]. [T] |
| 0x44 | UpdateGameData | `estr` session, `blob` | — | always 0. Written for CON's 256-byte game description; the RTA game has a builder (0x38075c) with no direct caller. |
| 0x5B | GetNetCharacterList_RTA | *estr session, u32* | `u32` count, then per character: `u32` id, `u32` pair count, pairs of `wstr` key, `wstr` value | 0 ok. [T] |
| 0x58 | CreateNewCharacter_RTA | `estr` session, `u32` 0, `u32` 0 (an empty `wstr` to the game), `wstr[]` keys, `wstr[]` values, `blob` first piece of data, *u32* | — | 0 ok, 1 failed. Starts an upload (section 8.3). The game expects a `u32` character id (D5). [T] |
| 0x5E | SaveCharacter_RTA | `estr` session, `estr` session of the player being saved, `u32` character id, `u32` 0, `u32` 0, `wstr[]` keys, `wstr[]` values, `blob` first piece, *u32* | — | 0 ok, 1 failed. Starts an upload that replaces the target player's current character. [T] |
| 0x5D | AppendCharacterData | `estr` session, `blob` next piece, `u32` last-piece flag | — | always 0, even if storing failed. Carries the tracking number of the 0x58/0x5E it continues [G: 0x37ca08]. [T] |
| 0x5C | GetNetCharacterData_RTA | `estr` session, `u32` character id | `blob` (1024 bytes), `u32` last-piece flag; one reply frame per 1024 bytes | 0 ok, 1 failed (then no body). Also makes this the user's current character. [T] |
| 0x5A | DeleteCharacter_RTA | `estr` session, `u32` character id, *u32* | — | 0 ok, 1 no user, 2 session id does not match the connection or database error. [T] |
| 0x01 | AddFriend | `estr` session, `wstr` chat handle | — | 0 ok, 1, 2 database, 19 that user ignores you, 20 no such user **online**, 21 already a friend. [T] |
| 0x1C | RemoveFriend | `estr` session, `wstr` chat handle | — | 0 ok, 20 not a friend, 2 database. [T] |
| 0x02 | AddIgnore | `estr` session, `wstr` chat handle | — | 0 ok, 20 no such user online, 24 is a friend, 25 already ignored. [T] |
| 0x1D | RemoveIgnore | `estr` session, `wstr` chat handle | — | 0 ok, 20 not ignored. [T] |
| 0x61 | GetSocialListInitial | *estr session* | `wstr[]` friends, `wstr[]` one placeholder entry, `wstr[]` ignored | always 0. What the middle list is to the game is Unknown. [T] |
| 0x62 | GetSocialListUpdate | *estr session* | `wstr[]` friends, `wstr[]` ignored | always 0. [T] |
| 0x21 | SendInstantMessage | `estr` session, `wstr` chat handle, `wstr` text | — | 0 ok, 1 no such user online, 19 that user ignores you. Recipient gets 0x30. [T] |
| 0x0E | GetPublicRooms | *estr session* | `wstr[]` names, `wstr[]` placeholder text, `u32[]` 88, `u32[]` 99 | always 0. Six fixed rooms. The last three arrays are filler; their meaning to the game is Unknown. The game sends this straight after a successful login [G: 0x32eba8]. [T] |
| 0x0C | EnterRoom | `estr` session, `wstr` room name | `wstr` name, `wstr` banner (empty), `wstr[]` member handles, `wstr[]` moderator handles (empty) | 0 ok, 1 no such room or already in it. [T] |
| 0x11 | GetRoom | `estr` session, `wstr` room name | as 0x0C if a room was found | 0, 1 no user. The name is not looked up: an empty name returns the user's game room, anything else the user's public room. |
| 0x15 | LeaveRoom | `estr` session, `wstr` room name | — | 0 ok, 1 failed. [T] |
| 0x22 | SendRoomMessage | `estr` session, `wstr` room name, `wstr` text | — | 0 ok, 1 no such room or not a member. Every member not ignoring the sender, sender included, gets 0x3D. [T] |
| 0x09 | CreatePrivateRoom | `estr` session, `wstr` room name | — | always 0, even when the name is taken. Creates the chat room of a game with the sender as member. The game expects the 0x0C reply body here (D7). [T] |

Requests the game can send that this server has no handler for (it logs "unknown packet
id" and sends nothing back) [S: Include/Network/Events.hpp]:

| id | request body | when the game sends it |
| --- | --- | --- |
| 0x19 | `estr` session, `wstr` room name, `wstr` text | after a successful 0x09, with a fixed line saying the room is private to the game [G: 0x32ef50]. Presumably sets the room's banner. With this server 0x09 never "succeeds" in the game's eyes, so 0x19 is not reached. [T: no reply] |
| 0x63 | `estr` session | from two menu functions (0x34abb0, 0x34b2b0); reply parsed as one `wstr[]` of names up to 15 characters. Purpose Unknown. |
| 0x64 | `estr`, `estr` (the login screen's user name and password fields) | from the login screen (0x339a20); reply parsed as twelve strings. Purpose Unknown (account details?). |

The executable also contains builders for ids 0x00, 0x03, 0x04, 0x07, 0x0B, 0x10, 0x12–0x14,
0x1A, 0x1B, 0x1E, 0x1F, 0x28, 0x29, 0x45, 0x46, 0x52 and 0x53 that nothing calls directly
[G: 0x37d674–0x37f59c]. They were not examined.

### Notifications sent by the server

| id | name | body | sent to, when |
| --- | --- | --- | --- |
| 0x3E | GameDiscovered | `nstr` address, `u32` port | a host, when its first discovery datagram arrives: its own address as the server saw it. Opens the game. [T] |
| 0x40 | ClientDiscovered | `nstr` address, `u32` port | a joiner, for each discovery datagram while the game is open: its own address as the server saw it. [T] |
| 0x65 | ClientRequestConnect_RTA | `nstr` LAN address, `u32` LAN port, `nstr` observed address, `u32` observed port | the host, at the same moment: the joiner's two addresses. [T] |
| 0x2F | FriendStatus | `wstr` chat handle, `u8` 1 online / 0 offline | everyone **on the list of** the user who logs in or disconnects (not everyone who lists that user). |
| 0x30 | InstantMessage | `wstr` sender handle, `wstr` text | the addressee of 0x21. [T] |
| 0x3D | RoomMessage | `wstr` room, `wstr` sender handle, `wstr` text | room members. Also sent with an empty sender when someone enters a game's chat room. [T] |
| 0x41 | ForcedLogout | `u32` 0 (the game reads a `u16`) | a connection the server is about to drop, and everyone at shutdown. |

The game also parses notifications 0x2A–0x3C (two or three strings each: room and friend
events), 0x4C, 0x4F and 0x51 [G: 0x387388]. This server never sends them and their
meanings were not worked out.

## 8. Flows

`C` is a console, `S` the server. Tracking numbers and the common headers are left out.

### 8.1 Create an account

```
C -> S:40810   0x43                        S -> C  lobby address, port
C -> S:lobby   0x27                        S -> C  key
C -> S         0x06 name, password, e-mail, date of birth, chat handle
                                           S -> C  result 0, session id
```
The game copies the chat handle the user typed into its own "my handle" field before
sending [G: 0x330950]. The server's length checks for names and passwords exist but are
never called [S: RequestCreateAccount.cpp].

### 8.2 Log in

```
C -> S:40810   0x43      then on the lobby connection      0x27
C -> S         0x16 name, password         S -> C  result 0, session id, second string
C -> S         0x0E                        S -> C  public chat rooms
```
The server loads the friend and ignore lists and sends 0x2F to those friends who are
online. A second login for an account that is already connected gets result 1; this also
hits a console that logs in on the very connection it just created the account on,
because the check does not skip the asking connection [S: RequestLogin.cpp].

### 8.3 Characters (stored on the server)

A character is two things: a short list of key/value strings for the selection screen, and
an opaque data block. The keys the game uses are `name`, `raceandclass` (two numbers),
`level` and `ability` (six numbers) [G: strings from 0x554aa0, used at 0x327988 and
0x327dc8]. The server accepts at most four pairs.

```
list     C -> S  0x5B                       S -> C  ids and key/value lists
create   C -> S  0x58 keys, values, first piece
                                            S -> C  result (sent at once)
         C -> S  0x5D piece, flag 0   ...   S -> C  result 0
         C -> S  0x5D last piece, flag 1    S -> C  result 0     (stored now)
save     C -> S  0x5E whose, id, keys, values, first piece, then 0x5D as above
load     C -> S  0x5C id                    S -> C  1024-byte piece, flag 0  ...
                                            S -> C  last piece padded to 1024, flag 1
delete   C -> S  0x5A id                    S -> C  result
```
- The game cuts continuation pieces at 800 bytes and sends one per lobby tick, re-using
  the tracking number of the request that started the upload [G: 0x37ca08, 0x380888].
- The server stores nothing until a piece arrives with the flag set. It then checks that
  the block, read as "four header bytes, then bytes where every zero byte is followed by a
  repeat count", expands to at least 19,504 bytes, and cuts off anything after that point
  [S: Source/Game/RealmCharacterSaveTask.cpp]. If the check or the database write fails the
  console is still told 0.
- Any member of a party can save any other member's character: 0x5E names the target by
  session id, and the server writes to whatever character that target last created or
  loaded; the id in the request is read and not used [S: RequestSaveCharacter_RTA.cpp].
- Reply frames of a load all carry the request's tracking number.

### 8.4 Create a game (public or private)

```
host -> S   0x54 game info, LAN address, UDP port      (private: 0x56 name, LAN address, port)
                                            S -> host  result 0, discovery address, port
host -> S   0x09 game name                  S -> host  result 0        (game's chat room)
host -> S:discovery (UDP)  session datagram, repeated
                                            S -> host  0x3E  host's address as observed
```
- Game info is five two-digit numbers, commas, a bar, and the game's name:
  `NN,NN,NN,NN,NN|name` [G: format string used at 0x32aa48; parsed back at 0x329440]. The
  server project reads the numbers as difficulty, game mode, arena kill count, mission and
  network-save flag; it stores the whole string and hands it back unchanged in the list.
- "LAN address" is the console's own interface address as dotted text, or `0.0.0.0` if it
  cannot find one; "UDP port" is the local port of its game socket [G: 0x32aa48].
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
| 2 | `wstr[]` | a short text per game; this server sends empty strings; meaning Unknown | 15 characters |
| 3 | `u32[]` | game ids | |
| 4 | `blob[]` | one blob per game; this server sends none (see D1) | |
| 5 | `wstr[]` | host's LAN address | 512 |
| 6 | `u32[]` | host's LAN port | |
| 7 | `wstr[]` | host's address as observed by the server | 512 |
| 8 | `u32[]` | host's port as observed by the server | |

The server lists games that are public and open; started and cancelled games are gone.
A game holds four members.

### 8.6 Start or cancel

```
host -> peers   "start" (peer-to-peer)          host -> S  0x23      S -> host  result
anyone  -> S    0x05 then 0x60                  S -> ...   result 0 for each
```
The host tells its peers first and does not wait for the server [G: 0x330a40]. The server
forgets a started game entirely. When a lobby connection closes, a game owned by that
user is deleted; a member who was not the owner is not subtracted from the game's player
count [S: GameSessionManager.cpp, `OnDisconnectUser`].

### 8.7 Friends and chat

- Friends and ignores are lists of chat handles kept per account. Adding either needs the
  other person to be online at that moment. Only the owner's side is stored; nothing asks
  the other person.
- 0x21 delivers a private message (0x30) if the addressee is online and not ignoring the
  sender.
- Public rooms are fixed; a game's room is created with 0x09 and closed when the game
  starts. 0x0C/0x15 enter and leave, 0x22 talks.

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
socket (section 6). The game socket's local port: the UdpManager is created with the
values 4000 and 5 in the slots that, in SOE's UdpLibrary, are "port" and "port range", so
the console would bind a port from 4000 to 4004 [G: 0x32a650] — Inferred, the binding code
was not read.

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
  external pair [G: 0x329ec8 → 0x329d58]. It also puts the joiner on its seek list.
- **Joiner**: put the host on its seek list when it sent 0x66 [G: 0x32aeb0, 0x329880].
  It does not open a connection itself (the only caller of the connect routine on this
  path is the 0x65 handler). Instead, on every tenth lobby tick, it sends a one-byte
  datagram to the **external** pair of every peer on its seek list, giving up on a peer
  after 15 seconds [G: 0x32a4b8]. The host does the same toward the joiner. These
  datagrams are what open the senders' routers for the other side.
- **Either side**, when a connection arrives: it is accepted if its source address equals
  a sought peer's external address (any port), or equals the internal address with the
  internal port. A console that is not the host drops any other connection; the host lets
  strangers in [G: 0x32c2c0].
- When the joiner gets the host's "welcome" over that connection it sends 0x5F to the
  server [G: 0x32ca18].

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
  looping traffic back (hairpinning).
- **A console on the same LAN as the server is observed with its LAN address.** Players
  outside that LAN are then told a private address for it and cannot reach it. Someone
  hosting the server at home and playing from the same network will be unreachable for
  friends elsewhere, unless that console's traffic to the server goes out through the
  router and back (again hairpinning, with the server addressed by its public address).
- The server refuses a discovery datagram whose source IP differs from the source IP of
  the same user's TCP connection, so the two must leave through the same public address.

### 9.4 Whose address is which on the wire

The game reads **internal first, external second** in all three places:

| message | internal pair | external pair | evidence |
| --- | --- | --- | --- |
| 0x55 reply | arrays 5, 6 | arrays 7, 8 | [G: call at 0x3867b0 passes arrays 7/8 first; handler 0x329440 stores them at record+0xac/+0xb4, which the join code copies to the external slot] |
| 0x57 reply | first `wstr`/`u32` | second `wstr`/`u32` | [G: 0x386a68–0x386b6c → handler 0x329880] |
| 0x65 | first `nstr`/`u32` | second `nstr`/`u32` | [G: 0x387388 case 0x65 → handler 0x329ec8] |

Champions Reborn follows this in 0x55 and 0x65 [T] and not in 0x57 (D2).

## 10. What the server stubs, guesses or gets wrong

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
| 40810 | TCP | RTA gateway — the port compiled into the game [G: 0x324920] | yes |
| 40811–40817 | TCP | seven more RTA gateway listeners, identical in behaviour | no use by the game was found in the connect code (0x387124, 0x388a34); expose them if in doubt |
| 40910 (`rta_lobby_port`) | TCP | RTA lobby — whatever the gateway hands out | yes |
| 10101 (`discovery_port`) | UDP | discovery datagrams, inbound only | yes |
| 40800–40807, 40900 (`con_lobby_port`) | TCP | the same for Champions of Norrath | only for CON |

`public_ip` in config.ini is handed to consoles twice: as the lobby address (gateway
reply) and as the discovery address (create/join replies). It must be an address every
player's console can reach, and the UDP port must be reachable at that same address.

Consoles need no inbound port opened toward the server. Between consoles, traffic is UDP
on the game socket of each (section 9.1); the server relays nothing.

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

- What keeps an idle console's connection alive for longer than the server's 30 seconds.
- Whether the game ever uses gateway ports other than 40810.
- The meaning of the `nstr` in 0x27, the two strings in 0x42, array 2 and array 4 of the
  game list, the middle list of 0x61, the last three arrays of 0x0E, and the `u32` the
  game reads after the result of 0x23.
- Messages 0x19, 0x63, 0x64 and notifications 0x2A–0x3C, 0x4C, 0x4F, 0x51: purpose and,
  for the notifications, exact fields.
- Whether the console really binds UDP 4000–4004, and what it does after a failed join
  (the "backing out" path of D8 is inferred from 0x3309c8 having the only cancel calls).
- What the game does with a wrong chat handle (D3) and after the failed 0x09 (D7).
- Everything about the peer-to-peer messages after the connection is up (welcome, known
  peers, character info, start, eject); see the netlib notes in `symbols/netlib.tsv`.
- None of this has been run against the real game. The quickest confirmation would be two
  emulated consoles on separate networks with a packet capture at the server.
