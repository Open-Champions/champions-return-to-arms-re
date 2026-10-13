# The native build online

Started 2026-10-12. The native build of Champions: Return to Arms (SLUS-20973 v2.00; the
game's code translated to C++, `docs/issues/native-recomp.md`, `native-app.md`) played
lockstep games over the hidden LAN start (`native-net.md`) but could not reach the lobby
server. This file is the work that takes it there: the design, what was **Ran** (with
what was seen), what was only built, and what is left. Nothing derived from the game is
in the repository: translations, programs, logs and cards are under `local/recomp-out/`.

## Status (2026-10-12, 15:20)

All **Ran** against the lobby server on this computer, with throwaway names made by the
tests; a native copy under test is started with `net-local-only=1` and sends nothing
beyond this computer. The machine was shared with other jobs the whole time: the load
average is quoted with every run (100 to 550 on 18 cores).

| What | Result |
|---|---|
| a native instance to the lobby's game list, from power-on | 17 s of real time; gateway 18 bytes out and 35 in, as the rig's capture |
| two native instances in one lobby game (host by code, join by code) | 7,610 ticks through a level change and a fight, **no shared column differs**; the game's own checksum exchange agreed every round |
| native + emulator application, native hosting | 3,062 ticks (drawn input on both from tick 200); checksum exchange agreed on both; 40 samples of the emulator copy equal the native tick log, 0 different |
| native + emulator application, emulator hosting | 2,413 ticks; the same; 34 samples equal, 0 different |
| the window program `rta_app` in a lobby game (as host, as joiner) | 1,229 and 1,684 ticks (the second with a level change), no shared column differs |
| one-step online: name asked once, account made, login saved 0600, used again | Ran on a terminal; no saved password in any of 240 output files |
| Host / Join by code, the character used last | Ran (every pair after its first run) |
| patch-set announcement | figure 3f5b1e14 (90 words), the application's; told and understood both ways with the emulator application; two native copies with different sets are both warned |
| characters saved by the periodic save, loaded at the next log-in | gold written in one tick came back in a new session on both copies |
| the name question on the window (a sheet), the note in the window's title | **Ran** in the second round (below): shown on a test window and worked from inside the program, from no login to the game list |
| three and four players, the window program among them; private game, chat, friends, leaving and returning, a player's program dying, a browser copy | second round, below |

## Second round (2026-10-12, from 22:45): what had not been exercised

Kept current while the work runs; the tables say what is **Ran**. Everything on one Mac,
every copy at 192.168.1.123, against a lobby server instance of this work's own
(`local/native-lobby/server/bin`: the binary built from `server/upstream` with FIXES 32,
its own database, bound to this Mac's address, every port the usual one plus 2000; the
lobby that was already running was not touched), throw-away names, `net-local-only=1` on
every copy. Load average 15 to 25.

**The builds tested.** `local/native-lobby/bin/rta_app_net` (window) and `rta_native_net`
(headless): `tools/recomp/net/` as it is now, linked with a snapshot of everything else
taken at 22:44 - the game's objects, runtime, renderer, sound and window program exactly
as `local/recomp-out/bin/rta_app` of 19:52 was linked from (`local/native-lobby/snap/`,
`build.sh`). So the window program is rta_app 19:52 (sha256 8ef21654...) with today's
network files; nothing another job rebuilt went into a test.

**New in `tools/recomp/net/`:** `--opt net-port-shift=N` (a second server instance whose
ports are the usual ones plus N: the gateway port built into the game is shifted, the
discovery port plus N counts as the server's); script command `app net sockets` (what the
driver holds open); `lobbyparty.py` (two to four copies, window or headless, several
launches, the scenarios below; one line per launch with the pairwise tick comparison and
the story the tick log tells: levels, deaths, reloads).

### Three and four players, with the window program

`lobbyparty.py OUT --players N --kinds ... --launches 3 --port-shift 2000 --play 1500
--level drunare --play2 3000`: drawn input on every copy, the level change written in one
lockstep tick, and in `drunare` the three or four players die one after another in the
arena fight; when the last one is dead the game puts everybody back (hit points full,
state 0) - "reloads after everybody died". Compared: every pair of tick logs
(`tools/rig/compare.py ticks`: seed, level, player count, button maps, every player's
position, state, hit points, gold, experience, out-of-step flags, own sync hash).

| Copies (host first) | Launches | All in the level | Ticks in step, each launch (every pair) | In each launch |
|---|---|---|---|---|
| 3 headless (first try of the set-up) | 1 | 1 | 2,719 | hub only |
| **window**, headless, headless | 1 + 3 in a row | 4 | 2,552; 5,377; 5,322; 5,376 | hub > drunare, 3 deaths, 1 reload |
| headless, **window**, headless | 3 in a row | 3 | 5,376; 5,344; 5,282 | hub > drunare, 3 deaths, 1 reload |
| **window**, headless, headless, headless | 3 in a row | 3 | 4,951; 5,207; 5,315 (all 6 pairs) | hub > drunare, 1 to 4 deaths, a reload in the third |
| headless, headless, headless, **window** | 3 in a row | **2** | 5,245; 5,206 (all 6 pairs) | hub > drunare, 4 deaths, a reload in the third; **the first launch failed for everybody** (below) |
| headless, **window**, headless, headless (launch tables printed) | 4 in a row | 4 | 5,126; 5,100; 5,453; 5,209 (all 6 pairs) | hub > drunare, 1 to 4 deaths |
| **window**, headless, headless, headless (again, after midnight) | 3 in a row | 3 | 5,347; 5,332; 5,312 (all 6 pairs) | hub > drunare, 4 deaths, 1 reload |

Games of three: 11 launches, 11 in the level. Games of four: 14 launches, 13 in the level.
In the 24 launches that got into the level no column differed in any pair, through the
level change, the deaths and the reload. (The launches from 23:13 on ran the build with
the arithmetic switch described below; the earlier ones the build before it; none of
these had the disconnect hold yet.)

**One launch of four did not start (1 of 7 launches of four, 23:21).** All four copies
went to lobby state 12 and none got a level within 60 s; no datagram to 0.0.0.0, nothing
"not carried" after Start. What the logs have: the host's "Terminating known peer" lines
read 2, 2, 1 (three different peers in a launch that works); joiner 1 took START last and
had only the host left ("Terminating known peer 0"); joiner 3's lines read 0, 1, 1; at the
end joiner 3 had not heard joiner 1 for 60 s (the whole launch) while it heard the host
until the end: the two never met in the launch handshake. That is the picture of
`three-players.md` cause 1 with BOTH of two joiners holding a wrong entry for each other,
which the handshake's repair-from-the-datagram cannot heal (each sends to where the other
is not). The launch tables were not in that run's log; `lobbyparty.py` prints them since
(`launch-tables`: 0x402a37.., the port table, each player's launch record four times),
so the next one can be read. Two other things ran on the Mac at that minute (the
leave-and-return rounds of two window copies, and the name-question test).

How two joiners can both be wrong about each other, when the one who fills its tables
first still has the other's connection: `three-players.md` names a second way to a wrong
entry - the peer library's accept rule files an arriving connection under the first
sought player with that ADDRESS, whatever the port, so with every player at one address
a fourth copy can hold two fellow joiners the wrong way round (seen there in two of four
launches). A swapped entry on one joiner and a stale one on the other is a pair that
never meets: the first sends its datagrams for the other to a third machine, the second
sends its to the host. Each alone is repaired from the first datagram that arrives.
**Inferred** from the logs above, not read from that run's tables.

**The defence, in the driver ("Fix", 2026-10-13):** a peer's disconnect is shown to a
game that is in a game's room half a second late - see "The disconnect hold" below.

### The disconnect hold (the fix for the launch that did not start)

**Reproduced** (2026-10-13, `lobbyparty.py --players 4 --stall j1`: four headless copies,
the second one standing still for 5 s across the host's Start - script command `app net
stall MS` - so that it takes START when the others have already disconnected). Launch 1
of 6 without the hold failed exactly as the one of the night: everybody in lobby state 12,
nobody in a level. Its launch tables (true ports: host 4004, players 1 to 3 at 56816,
56474, 52373):

- player 1 (the one that stood still): no "Terminating known peer" line - not one live
  connection when it took START; port table 0, own, 0, 0. The handshake then gave it the
  host (4004, state 8) and player 2 (56474, state 8); its record for player 3 stayed
  `00000000:0`, state 0, to the end;
- player 3: "Terminating known peer 0, 2" - two peers, not three; port table 4004, **4004**,
  **56816**, own: the host's port filed for player 1 and player 1's port for player 2.
  Player 2 was repaired from its datagrams (56474, state 8); its record for player 1
  stayed `c0a8017b:4004`, state 0: it sent player 1's datagrams to the host for 60 s.

Two joiners, each wrong about the other, neither entry pointing at the other machine: no
datagram ever arrives that could repair one. In the 5 launches that worked, the joiner
that stood still was wrong about everybody every time (0, 0, 0) and one other joiner held
a copy of the host's port for a third - but nobody was wrong about the one that stood
still, and the handshake repaired the rest. Across the 7 launches of four of the night
(no stall) every one had wrong entries at Start, of both kinds: copies of the host's port
or 0 (the race at Start, `three-players.md` cause 1) and two fellow joiners the wrong way
round (the accept rule that goes by address).

**The fix** (`netdrv.cpp`, `udp_receive`): a datagram that is the peer library's
disconnect - 8 bytes: `00 05`, the connection's code, a reason - and arrives while the
lobby state word says "in a game's room" (6) is kept for 30 vertical blanks, or until the
state has moved on, before the game sees it. By then a joiner has taken START and filled
its launch tables from connections that were all still there: the race cannot produce a
wrong entry on a native copy any more, whatever the other players' copies are. What stays
are swapped entries, and a swapped entry still points at a real player, who learns the
sender's true port from the first datagram. It is what a network that delivers that one
datagram half a second late would do; nothing else is held, and nothing during a game. A
player who just leaves a room is seen to leave half a second later. `--opt
net-hold-disconnects=0` turns it off; `app net sockets` counts the held ones.

| 4 headless copies, joiner 1 standing still 5 s across Start | Launches | All in the level | Ticks in step | At Start |
|---|---|---|---|---|
| hold off (`net-hold-disconnects=0`) | 6 | **5** | 1,218 - 1,219, all 6 pairs | the joiner that stood still terminated 0 peers and had 0 for every other player, 6 of 6; another joiner held the host's port for a third, 6 of 6 |
| hold on (the default now) | 6 in a row | **6** | 1,212 - 1,219, all 6 pairs | every joiner terminated 3 live peers, 6 of 6; 3 disconnects held on the joiner that stood still and 1 on another; no 0 and no copy of the host's port in any table; two fellow joiners the wrong way round in 5 of 6, repaired |

One failure in six is a thin "before"; what carries the claim is the tables: the kind of
wrong entry the failure needs was in every launch without the hold and in none with it.
The emulator application and the browser page have the same hole (their network layer is
`tools/play-net/src/RtaNet.cpp`, not this driver): **the same hold there would need a
change in `RtaNet.cpp`** - it sees every datagram on its way to the game and knows the
lobby state word the same way. Not done (not this work's file).

### The name question in the window: shown and worked

`online_mac.mm` left a test window alone, so the sheet had never been up. New, for tests
only: `--opt online-test-window=1` shows the question, the title note and the warnings on
a test window as on any other, and the script command `app online sheet info | type TEXT |
press N | picture FILE` reads and works the sheet from inside the program - `press` is the
button's own `performClick`, so the sheet ends and its handler runs as after a click. No
screen capture, no accessibility permission. The window program's control socket hands
`app` lines to the window program alone, so the network's commands also come in through a
file: `--opt online-commands=FILE` (looked for twice a second, carried out, removed).

**Ran** (`local/native-lobby/xname.sh`: the window program in a test window, a new data
directory, no name given, `online=lobby`):

| Step | Seen (the program's own lines) |
|---|---|
| start, no saved login | "no saved login for this server: asking for a player name"; the game goes on to its log-in screen and waits there; `sheet: up=1 attached=1 visible=1 message="Your player name" buttons="Play online|Not now"`; the window's title: "AGENT TEST - native online n1 - server 192.168.1.123 - Going online: waiting for your player name..." |
| "ab", *Play online* | the sheet is back with "A player name has at least 3 characters." |
| "has space", *Play online* | back with "A player name has letters and digits only (A-Z, a-z, 0-9): ..." |
| a made-up name, *Play online* | the account screen, "the new login for this server is saved", "done - you are in the lobby"; sheet gone; title "... Online: you are in the lobby (Game Selection and Chat). The controls are yours."; `online-login` mode 0600; the password occurs 0 times in the program's output and its network log; the server's database has the account. 4,410 vertical blanks from power-on |
| second copy: *Not now* | "STOPPED - no player name was given (log in on the game's own screen, or choose Play Online again)"; the game stays on its log-in screen |
| the same copy: `online start lobby` again, the first copy's name | "the server did not make the account: the name is taken, or it does not accept it"; the sheet is back with "That name is taken on this server (or the server did not accept it). Choose another one." |
| another made-up name | the lobby |

`sheet picture` writes what the sheet's view draws into a bitmap; AppKit draws only the
text field that way (labels and buttons are on layers), so the lines above are the
evidence, not the picture. A person has still not typed into it.

### The lobby's own screens, by hand (two window copies, driven over the control socket)

Two copies of the window program in test windows, `online=lobby`, then every press sent
over `--control` (the socket of `tools/recomp/app/control.h`), text typed on the game's
own on-screen keyboard (cursor read at keyboard window +0x5e0 = row * 14 + column; R2
held for a capital), and the game's own picture read back (`shotfb`: the renderer's
output written by the program, not a screen capture; pictures under
`local/native-lobby/x/`). The helper is `local/native-lobby/xlib.py`.

| Item | The original flow | What the native build did |
|---|---|---|
| **Chat in the lobby, both directions** | R1 to the chat pane, square *Chat*, type, L2 *Enter* (request 0x22; everybody in the room gets 0x3D) | **Ran.** A line typed on copy A appeared on A and B as `<A's handle>: hello from a 1`, one typed on B appeared on both |
| **A private message** | `/m <handle> text` in chat, or *Private Msg* on a friend (0x21 > 0x30) | **Ran.** `/m <B> secret 2` typed on A appeared on B's *Private Chat* tab with A's handle |
| **Who** | cross in the chat pane | **Ran.** "Players in 'Champions Reborn': ..." with both handles |
| **Friends list** | triangle *Config* > "Chat Configuration": square *Edit Name*, type a handle, cross *Add Friend* (0x01), the list shows it; cross *Private Msg* on an entry sets the target | **Ran.** "Added to Friends List"; the list showed B's handle; the server's `UserFriendList` had the row; *Private Msg* set the target (the room's private tab then says `Msg (<B>)`). *Remove* and the status of a friend who logs off: not tried |
| **Ignore list** | the same window, triangle *Add Ignore* (0x02) | **Ran.** B ignored A (the server's `UserIgnoredList` has the row); a public line typed by A afterwards did not appear on B; A's `/m <B> ...` got the game's box "There was an error sending a message to that person. They may be offline, or that may be an invalid chat handle." (the server's result 19) |
| **A private game with a password** | There is no password in the game: the host form has "Public or Private?", a private game is not in anybody's list, and whoever knows its **name** finds it: triangle *Host/Search*, square *Search*, "Searching for a Private Game:" (0x56, then 0x57) | **Ran.** A hosted "Creating A Private Game" named by hand; the server logged `Create Private Game`; B's list stayed empty (0 games) over a refresh; B searched a wrong name and got the game's box "Couldn't join game: A database error occured" (the server answers 2 = not found, and that is the game's text for 2); with the right name B got the character screens and the room |
| **Chat in a game's room, both directions** | the room has *Game Chat*, *Public Chat*, *Private Chat*; R1 to a pane, square *Chat* | **Ran.** "User '<B>' has joined the room." on the host; a line from A and one from B on both, under *Game Chat* |
| **The private game started** | cross *Start Game* on the host | **Ran.** Both in `hub`, 2 players, ticks running |
| **Leaving a game** | Start: pause menu (host: Return to Game, Use Gate Scroll, Load Game (grey), Options..., Kick Player, Exit Game; a joiner has no Kick Player); *Exit Game* > "Exit Game? Yes / No" | **Ran** (the joiner left): it was at the lobby's game list within a second, still logged in, back in the public chat room; **the host, alone, was put back to the game list by the game about two seconds later** (a game of two ends for both). The server logged both back in the chat room |
| **Cancelling in the room** | circle *Cancel* > "Leaving Game", cross (0x05, 0x60) | **Ran** on a host alone in its room: back at the game list. And with a joiner still on its character screens when the host cancelled: the joiner accepted its character and landed at the game list, no box, nothing stuck |
| **Start with a player still choosing a character** | the game refuses ("Not all players are ready to begin...") | **Ran** by accident (`late3`, first form): a third copy sat on its character screens; the host's Start presses did not start the game in 50 s |

Not tried by hand: *Kick Player*, removing a friend or an ignore, the *Sort* of the game list,
importing a memory-card character, deleting one.

### Leaving and coming back without restarting the program

`local/native-lobby/rounds.py` on the same two window copies (processes kept): host by a
new code (`app online start host:CODE` through the command file), join by it, Start, both
in `hub`, both walk, about 675 ticks, then one of them leaves by the pause menu and both
are back at the game list. **9 games in a row in the same two processes** (1 + 5 with the
joiner leaving, 3 with the host leaving - then it is the joiner the game puts back): every
round started, both in the level, checksum flag 0 on both, both back at the list, 59 to
87 s a round. Per process, read after every round (`lsof`, `ps -M`, `ps -o rss`):

| | before | after 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| sockets of the process | 6 | 6 | 7 | 7 | 8 | 8 | 9 | 9 | 9 |
| threads | 28 | 28 | 32 | 35 / 36 | 38 | 42 | 46 | 50 | 54 |
| resident memory, MB (copy A / B) | 482 / 1,458 | 509 / 1,504 | 349 / 461 | 399 / 487 | 422 / 497 | 419 / 510 | 409 / 506 | 451 / 498 | 383 / 499 |

(These eight follow one earlier game and two cancelled ones in the same processes: 9
games in all; a fresh process has 4 sockets and 20 threads at the game list.)

- **Sockets: bounded.** The driver keeps one host UDP socket per UDP port of the game for
  the whole run (so that the path the peer handshake opened is kept), and the game takes a
  port in 4000-4004 for each game: at most five, reached after a few games (9 = 4 others
  + 5), and it stayed at 9 for the last three games. One TCP stream to the lobby throughout; `app net sockets` after every game: "1
  streams (1 open), 1 datagram, 0 raw". Nothing of the driver's grows with the games but
  the list of players heard (a few bytes each).
- **Threads: four more per game, and they stay.** Not the network's: the game ends a few
  of its threads with `TerminateThread` at every level it leaves, and in
  `tools/recomp/rt/runtime.cpp` (system call 0x25) that sets `kill` on a thread that is
  waiting, while `wait_for_baton` (line 383) only looks at `kill` after the thread has been
  given the baton - which an unlinked thread never is. Its host thread waits for ever.
  **Needs a change in `rt/`** (wake the thread's condition variable in case 0x25 and let
  the wait end on `kill`). Harmless for an evening (each is a parked thread with a
  reserved, untouched stack); a few hundred games in one run would reach the system's
  thread limit.
- **Memory:** no growth with the games (it follows what the renderer holds: 350 to 520 MB
  after a level; one copy stood at 1.5 GB before the rounds, after an hour of lobby
  screens and pictures, and went back to 460 MB with the first level load).

**Three players, three games in the same three processes** (`lobbyparty.py --scenario
leave --rounds 3`, headless host, window joiner, headless joiner): in each game the last
joiner leaves by the pause menu after 900 frames, the other joiner 600 frames later, and
the host, alone, is put back to the game list by the game; then the host hosts by a new
code and the two join again. All three games started and ended for every copy. A player
who leaves on purpose is gone at once (`NET: DISCONNECTING PLAYER 2 on frame 1377`): the
two others do not stand still as they do for a dead one. Tick logs compared game by game,
every pair: 1,415 / 1,380 / 1,414 ticks with three players, 1,937 / 1,986 / 1,938 for the
host and the joiner who stayed longer - nothing differs. Sockets and threads per process
went as in the table above (headless host: 2 to 5 sockets, 9 to 19 threads over three
games).

**Joining a game in progress** (`lobbyparty.py --scenario late`): the original does not
allow it - a started game is in nobody's list and the server has forgotten it (the game
even has a text for a server that would say so, "Failed to join game: It has already
started."). **Ran**: two copies in their game (1,819 ticks in step), a third at the
lobby's game list asking for the game by its code 30 s after it started: its list held 0
games throughout, and the one-step driver said after its two minutes "STOPPED - no game
with the code ... appeared in the lobby's list within two minutes. Check the code with
your friend ...". Nothing reached the running game.

**Leaving the lobby altogether, a night at the lobby, and going online again.** The two
window copies of the rounds were left running overnight. Copy B stood at the game list
for 8 h 10 min (1.77 million vertical blanks): still logged in in the morning, its one
connection to the lobby open, 54 threads and 412 MB as at midnight. Copy A had been sent
out of the lobby by a circle press in the chat pane (*Exit*): the game closed its lobby
connection (44,634 bytes out, 43,058 in) and stood at "Normal Game / Internet Game" for
the night; in the morning `app online start lobby` in that same process logged in again
with the saved login and had the game list up (9 sockets, 60 threads, 342 MB).

### A player's program dying in mid-game; the host's program dying

`lobbyparty.py --scenario drop` and `--scenario hostquit`, three copies (headless host,
window joiner, headless joiner), drawn input on all; after 900 frames one PROCESS is
killed (`kill -9`: nothing is said to anybody), the other two play on for 2,400 frames.

| Killed | What the two others did | Ticks in step between the two |
|---|---|---|
| the last joiner, at tick 1,239 | lockstep stood still at tick 1,245 on both for **1,402 and 1,444 vertical blanks (23 to 24 s)**; the picture keeps the level and all three status bars and shows the game's connection sign in the middle (`d3/run1/j1-after-1.png`); then `NET: DISCONNECTING PLAYER 2 on frame 1258, whackHim = 1`, `NET: Done kicking!`, the dropped flag of player 2 is 1 on both, and the game goes on for the two | 2,129 (through the wait and after), nothing differs |
| the host, at tick 1,223 | the same: 1,203 and 1,448 blanks (20 to 24 s), then player 0 dropped on both, and **the game goes on without its host** | 2,047, nothing differs |

So a dead player costs the others 24 seconds of standing still, once, and nothing else.
The lobby server times the dead copy's connection out by itself (120 s). Not tried: the
copy coming back, a line that is only slow, a drop during a level load.

### With a browser copy: the arithmetic

**The gap.** `mixed-arithmetic.md` 5: every copy tells the others which arithmetic it can
compute with and which it does; the emulator application changes to a browser's while a
browser copy is in the room. The native build announced "can: the console's only, does:
the console's" and could only warn. **Closed tonight, in `netdrv.cpp`:** the translated
code computes with the host's own instructions and the runtime puts each game thread's
processor in the console's state when it starts (`rt/runtime.cpp`, `thread_main`); the
driver now puts the thread that runs the game's ticks in the wanted state at every call
of the task loop (the entry it already has, 0x3226e4) and at every vertical blank -
FPCR on ARM64: to nearest and tiny numbers kept for a browser's arithmetic, toward zero
and flush-to-zero for the console's. The rule is the application's (`CheckArithmetic`):
in the front end (lobby, room) a player heard in the last 15 s who cannot do the
console's, or already does a browser's, makes this copy change, nobody such and it
changes back; nothing changes once a level runs; a change is told again from the start;
a copy that cannot follow gets the warning on both sides. It announces "can: both".
`--opt net-arith=auto|console|browser` fixes it; `app net arith` and `app net peers` show
it. Limits: ARM64 only (an x86-64 or WebAssembly build of the native game says "the
console's only", as before); only the thread that runs the ticks and the one that reads
the controller are changed, the game's other threads (disc reader, network set-up) stay
as the runtime made them - they compute nothing of the simulation as far as was read;
the runtime's own `--opt arith=nearest` is taken as "a browser's, fixed".

**Ran** (`local/native-lobby/npage.py`): one native copy and one page of the browser build
(the page that exists under `local/three-players/site`, 20:52, read only; Chrome 155 in a
window of the test's own; the page server on 127.0.0.1 serves the page WITHOUT the disc -
the image is handed to the page's own file input from this computer, as a player picks
it), through `tools/play-web/relay/relay.py --lan` on this Mac pointed at this work's
lobby instance. The native copy's lines and the page's own line are quoted.

| Order | In the room | In the game | Result |
|---|---|---|---|
| native (headless) hosts, the page joins | native: "the player at ... computes with browser arithmetic (can do: the browser's)", "arithmetic: the machine now computes as a browser copy's does"; page: "Everyone computes the same way: 1 other player heard, the same patch set (3f5b1e14), browser arithmetic (in the Mac application)" | 3,216 lockstep frames in `hub`, both walking and swinging | the page received the native copy's sync hash for 1,778 frames it still held its own for: **all equal**; out-of-step and dropped flags 0, checksum flag 0 on both |
| the page hosts, native (headless) joins | the same lines | 3,107 frames | 1,837 hashes equal, 0 different; flags 0 |
| the **window** program hosts, the page joins | the same lines | 6,066 frames | 3,458 hashes equal, 0 different; flags 0 |
| control: native with `net-arith=console` (what the build did before tonight) hosts, the page joins | page: "WARNING: another player's copy cannot compute as a browser does (an older copy of the application, or one set to its own arithmetic): the game would fall out of step - do not start it..."; native: "WARNING: the player at ... computes with browser arithmetic and this copy cannot: the game would fall out of step - do not start it" | started all the same | hashes differ from frame 3; at frame 245 the game ended the session on both (page back at the title, native in the front end, one player) |

So the native build and a page play in step, both orders, and a native copy that cannot
follow is warned about on both sides. The page calls the native copy "the Mac
application" (it tells the two apart by nothing). Not done: a level change or a fight in
a mixed game (a page has no tick-keyed write; the game's own gateway was not walked), a
game of three with a page, Safari or Firefox, a relay that is not on this computer.
The relay carried the native copy's datagrams although they leave through the loop-back
interface (`--lan`).

## Where the cut is, and why

Two ways were open:

- **(a)** run the game's own network stack natively and put a virtual adaptor under it, as
  the emulator-based application does (`tools/play-net/src/RtaNet.cpp`);
- **(b)** answer Sony's network library at its entries, as `tools/recomp/net/netshim.cpp`
  does for the ten entries of the LAN start.

**(b) was taken.** What decided it:

1. **The stack is not in the executable.** The game's side of the network is three
   layers of its own code — the lobby client (SOEGamesAPI: framing, encryption), the peer
   library (SOE UdpLibrary: handshake, reliable channel) and the lockstep netcode — and all
   three end in Sony's libnet (0x364fb8–0x366550), which does nothing but carry each call
   by RPC to the I/O processor. The TCP/IP stack itself is eleven I/O-processor modules
   (`inet`, `inetctl`, `netcnf`, `ppp`, `pppoe`, `dev9`, `smap`, `msifrpc`, `libnet`,
   `eznetcnf`, `eznetctl`): MIPS R3000 code for a second processor, a second kernel and an
   Ethernet chip, none of which the native build has (it answers the I/O processor's
   services, it does not run its programs). Running that natively means translating
   Sony's modules and writing an I/O-processor kernel and a chip model for them — none of
   it code of ours, and none of it deciding anything a server or another player sees.
2. **The ERX modules are not on the lobby path.** `LIBINSCK.ERX`, `NG_INSCK.ERX` and
   `DNAS_NET.ERX` are loaded by the network window (`FUN_0033ed70`, states 0xc, 0xd, 9,
   10, 6 of the word at +0xdb4) for one purpose: the sign-in with Sony's servers, which
   are gone. With the project's local sign-in patch the window is done before any of them
   is loaded (**Ran**: no ERX file is asked for on the way to the lobby or in a game). Translating them ahead of
   time, as `native-recomp.md` planned, would serve a step that cannot succeed.
3. **The boundary is narrow and says everything.** 15 library entries and 13
   configuration-client entries. Above them every byte the server and the other players
   get is produced by the game's own translated code; below them a stream is a host TCP
   connection and a datagram a host UDP datagram. The emulator-based application ends the
   game's TCP in its own code and carries the bytes on host sockets too, so toward the
   server and toward other players the two builds do the same (what differs is listed
   under "Behaviour that differs from the emulator build").

It was also the soonest: the first run of the first build reached the game list.

## Design

| File | Does |
|---|---|
| `tools/recomp/net/hle-online.txt` | the addresses the driver supplies (`recomp.py --hle-add`) |
| `tools/recomp/net/netdrv.cpp`, `netdrv.h` | the library entries on host sockets; the network setting; the patch-set announcement; the tick log and tick-keyed writes of a test run |
| `tools/recomp/net/online.cpp` | joins the one-step driver of the emulator build (`tools/play-net/src/RtaOnline.cpp`, linked unchanged) to the runtime; script commands; the Config button |
| `tools/recomp/net/online_mac.mm` | the name question, the note and the set warning on the window (AppKit); linked into `rta_app` only |
| `tools/recomp/net/build_online.py` | `bin/rta_native_online`: the headless program with the network |
| `tools/recomp/net/play-native.sh` | starts `rta_app` with the options of `tools/play-net/play.sh` (`--server`, `--online`, `--host [CODE]`, `--join CODE`, `--choose-character`, `--player N`) |
| `tools/recomp/net/lobbypair.py`, `lobbyapp.py` | test: two copies (headless native, the window program, or the emulator application) through the lobby into one game, and the comparison |
| `tools/recomp/recomp.py` | new options `--hle-add FILE` (one more list of supplied addresses) and `--extra-pnach FILE` (a patch file from outside the repository, applied whole; its words follow the fix set's in `patches.cpp`, and `recomp_patch_set_words()` says how many belong to the set) |
| `tools/recomp/app/build.py` | `rta_app` is translated with the network list and the local sign-in patch (when present) and links the four network files |

Nothing in `tools/recomp/rt/` was changed, and `rt.h` / `iface.h` are as they were. The
driver sets itself up from the game's `main()` (an entry of its list): it reads its
options with `rt_option`, puts itself in front of the controller source
(`g_hooks.pad`), and chains `script_app_command` and `rt_at_finish`. `rta::NetDriver` in
`iface.h` stays reserved: the driver is linked at the entries, as the sound library is.

### The entries

| Address | Entry | Answered with |
|---|---|---|
| 0x365ec0, 0x365f88 | `sceLibnetInitialize`, `sceLibnetTerminate` | 0 |
| 0x365a08, 0x365a90 | `sceInetGetInterfaceList`, `sceInetInterfaceControl` | one interface; code 9 its address (this copy's made-up one), code 8 "up, running" |
| 0x3654a8 | `sceInetCreate` | type 0 a datagram socket on the game's port, 1 a stream to the address and port of the block, 3 the raw (ICMP) socket the peer library opens beside its data socket |
| 0x365518 | `sceInetOpen` | a stream: a host `connect` that does not block; 0, or −500 while it is under way |
| 0x3651e0 | `sceInetPoll` | bit 4 (out) for a connected stream, which is what the lobby client waits for |
| 0x365780, 0x3655a8 | `sceInetSend`, `sceInetRecv` | bytes moved, −500 for "not now", an error once the server has closed (the game then connects again by itself, as on the rig) |
| 0x365830, 0x365670 | `sceInetSendTo`, `sceInetRecvFrom` | one datagram; −500 when none waits |
| 0x365560 | `sceInetClose` | a stream is closed; a datagram socket's host socket stays |
| 0x365288, 0x365348 | `sceInetName2Address`, `sceInetAddress2String` | dotted text both ways (the peer library converts every address through text); the lobby's name gets the server's address; any other name does not exist |
| 0x364fb8 | `libnet_callRpc` | every other library entry ends here: an error, and a line in the report (none was called in any run) |
| 0x367da8 … 0x368270 | `ezNetCnfInit`, `Exit`, `GetCount`, `GetCombinationList`, `GetProperties` | the settings found in the card directory's `mc0/BWNETCNF`: the 0x800-byte list as the emulator's module fills it (head 6, 1, 1; per entry state 0 or −8, kind 2, three names of 64 bytes) |
| 0x37a5d8 … 0x37ad38 | `ezNetCtlInit`, `Exit`, `SetProperties`, `SetCombination`, `UpInterface`, `DownInterface`, `GetStatus`, `WaitEventTO` | the interface is "starting" for 20 vertical blanks after `UpInterface` and then as read on the emulator with the line up: 1, "eth0", 2, state 3, link 1; `DownInterface` leaves event 0xb for the next wait |
| 0x137a10, 0x13e638 | `net_loadModules`, `net_linkCheck` | 1 and 1, as the LAN shim |
| 0x323dcc | `main` | set-up, then the original |
| 0x3226e4 | `tasks_run` | the original; the call from `net_frameLoop` is one lockstep tick (tick log, tick-keyed writes — test equipment, idle without its options) |

A libnet address is 16 bytes: a zero word, then the IPv4 address **as one 32-bit word of
the machine** (192.168.1.2 is 0xC0A80102; in memory the bytes run backwards). The peer
library converts through text both ways and would work with any layout the driver chose,
but the netcode writes the word itself. Seen: with the bytes read in network order the
launch datagrams went to the reversed address (123.1.168.192) and the game hung at launch.

### Below the entries: the emulator application's rules

`netdrv.cpp` does under the entries what `tools/play-net/src/RtaNet.cpp` does under the
game's stack, rule for rule:

- a made-up own-network address per copy (198.19.x.y, made once, kept in
  `<data>/online-address`); the game reports it to the lobby server and other players'
  games try it — those attempts are not carried, "as between two houses";
- a server on this computer is reached at the computer's outside address, so that the
  server sees an address other players can use; the lobby's host name is answered with
  that address, and an address the gateway's reply names for the lobby is taken for the
  server when the server is local or private (read from the 0x43 reply as it passes);
- one host UDP socket per UDP port of the game, with the same number when free, kept for
  the whole run: the lobby server sees the pair other players must send to, and the
  netcode that opens the port again at launch keeps the path the peer handshake opened;
- the server's address on a port that is not the server's is another copy on the server's
  computer and goes through the loop-back interface; what comes back is shown to the game
  as coming from the address it sent to;
- every other player heard from is told this copy's patch set (the mark `RTAset1` after a
  keep-alive of the game's UDP library) and its arithmetic (`RTAari1`: can do the
  console's, does the console's); theirs are taken out before the game sees them.

### The network setting

"Internet Game" wants a network setting on the memory card. The driver writes the four
files of `BWNETCNF` into `<card>/mc0` when they are missing — the same bytes the emulator
application writes, so a card directory goes back and forth between the two builds — and
answers the configuration clients from what is in that directory (a card that holds more
settings, made by Sony's program in the emulator, lists them all).

The network screen offers "Config" (triangle), which restarts the machine into Sony's
network settings program on the disc — a second executable the native build does not
contain. As in the emulator application, the button is not passed on while that screen
lists the setting (**Ran**: the screen stays; cross then accepts and the game connects).

### The sign-in step

`build_online.py` and `app/build.py` hand `local/SLUS-20973_4028A55F_signin.pnach` to the
translator when the file is there (`--extra-pnach`; `RTA_SIGNIN_PATCH` names another
place). Its words are applied to the image before translation and written to memory with
the fix set's; they are not counted in the patch-set figure, as in the application.
Nothing of the file is in the repository, printed or logged; without it the game stops
at its sign-in step. The skip is not re-implemented in any code here.

### Options

`--opt key=value` to the runtime (after `--` for `rta_app`): `net-server`,
`net-server-public`, `net-data`, `net-card`, `net-netcnf=0`, `net-addr`,
`net-loopback=on|off`, `net-ports=0`, `net-set-quiet=1`, `net-local-only=1`, `net-pace=HZ`,
`net-log=FILE`, `net-log-all=1`, `net-arith=auto|console|browser`, `net-port-shift=N`,
`net-hold-disconnects=0`,
`online=lobby|host[:CODE]|join:CODE[+choose]`, `online-name=NAME[,NAME…]`,
`online-person=0`, `online-commands=FILE`, `online-test-window=1`, `tick-log`,
`tick-watch-file`, `tick-do`. `netdrv.h` describes each. Script commands: `app online
start MODE`, `app online stop`, `app online name NAME`, `app online`, `app online sheet
info|type TEXT|press N|picture FILE`, `app net peers`, `app net arith`, `app net sockets`,
`app net stall MS`, `app net drop`. From a script file they reach the network in the window program too; the
window program's control socket hands its `app` lines to the window program only
(`app/app_main.cpp` sets `g_control.app_command = app_command`, past the chain in
`script_app_command`), which is what `online-commands=FILE` is for.

## What was run

Headless copies are `bin/rta_native_online`, held to 59.94 vertical blanks a second
(`net-pace`); the lobby's time-outs count frames, and the server and the other copy answer
in real time. "Compared" is `tools/rig/compare.py ticks` over the two tick logs with the
rig launcher's columns (tick, shared seed, level, player count, button maps, the previous
tick's sync record, and for both players position, facing, action state, object seed, hit
points, mana, gold, experience, three bags, statistics, points, equipment, abilities,
skills) plus the lobby flag and `g_checksumFailed`.

| Run (`local/recomp-out/online/`) | Load | Result |
|---|---|---|
| `n1`: one copy, `online=lobby`, new account | 24–40 | game list at 16.9 s; 2 TCP connections, 928 bytes out, 1,525 in |
| `pair1`, first run with characters: host + join | 129 | launched at frame 3,205 of the host (53 s); 2,117 ticks compared, nothing differs |
| `pair2`: new accounts, new characters by script, `--play 3000 --level drunare --play2 3600` | 196 | 7,610 ticks compared (3,900 in `hub`, 3,710 in `drunare`), **nothing differs**; 95 and 332 distinct hit-point values (both die in the arena fight); checksum tables equal in all rounds (23 values); 4 saves answered |
| `x1`: native hosts, emulator application joins | 553 | 3,062 ticks, drawn input on both from tick 200; `g_checksumFailed` 0 and expected = received on both; 40 samples equal the native tick log in every column, 0 different |
| `x2`: emulator application hosts (new character through its control socket), native joins | 448 | 2,413 ticks; the same; 34 samples equal, 0 different |
| `pair1`: `rta_app` in a test window hosts, headless joins | 366 | 1,229 ticks compared, nothing differs; the pair ran at the window copy's speed, about 32 ticks a second |
| `pair1`: headless hosts, `rta_app` joins, level change in tick 1300 | 272 | 1,684 ticks compared, nothing differs |
| `pair2`, two sessions: the save round trip (below) | 361, 374 | 5,602 and 616 ticks compared, nothing differs |
| `pair1`: host with the 26 sections, joiner with 25 | 432 | both warned (below); 553 ticks in `hub`, nothing differs |
| `idle26`, `idle25`: no input after the launch (below) | 380–430 | nothing differs; the input is not stuck |

**The emulator copy has no tick log.** What it leaves is samples: one batch of control
commands reads the tick counter, the shared seed, both positions as raw bits, hit points,
gold and experience, and is kept when the counter is the same at both ends of the batch.
Each sample is looked up in the native copy's log at the tick before the counter (a
vertical blank falls between two ticks). In 5 of the 74 equal samples the emulator copy's
own player stood at its predicted position (`net_predictLocalPlayer` runs once per drawn
frame); those three columns are counted apart. This is weaker than a row-for-row
comparison; the game's own checksum exchange, which ran every 240 ticks on both copies
and never failed, is the other half. No level change was made in the mixed pairs: the
application has no tick-keyed write.

**On the wire** a native copy looks as the rig's captures of the emulator do
(`live-rig.md` 13.4, 19): gateway request 18 bytes, reply 35; the lobby connection; one
52-byte discovery datagram to port 10101; the one-byte seek, the 14-byte connect request,
the welcome; game port in 4000–4004 (4000, 4001 and 4004 seen), the host socket with the
same number unless another program on this computer held it.

### Conveniences

- **Name asked once.** Headless on a terminal with no saved login: the driver asks, an
  answer of two characters is refused with the rule and asked again, the account is made,
  the login is saved (`online-login`, mode 0600). Second start: "a saved login for it is
  there", the log-in form, the game list; nothing asked. The 15 passwords the tests saved
  were searched for in all 240 files the tests wrote (logs, tick logs, the terminal
  transcript): 0 occurrences outside the login files.
- **Host / Join by code**, **the character used last**: every pair. A copy with a stored
  character takes it from the server's list by itself (0x5B, 0x5C); a new account gets
  the game's character screens, which the test scripts fill.
- **Patch set.** The native build shows 3f5b1e14 with 90 words — the application's figure
  for the 26 suggested sections; the two words of the sign-in patch are not in it. A
  native copy and the emulator application each log the other's set as "the same as this
  copy". A copy built without one section (88 words, a5c309fa) and a 26-section copy in
  one room: both print `WARNING: a player (…) has patch set …: they would fall out of step`.
- **In the window program** (`rta_app`): the same driver; `online_mac.mm` puts the name
  question on the window as a sheet, the driver's note (where it is, the code of a hosted
  game) and the server into the window's title, and the set warning into a sheet.
  A test window is left alone by design (its title stays "AGENT TEST - …", the name comes
  from `online-name`) unless `online-test-window=1` is given: **Ran** that way in the
  second round ("The name question in the window: shown and worked"). The window program
  online as host and as joiner ran in both rounds.

### The save round trip

Session 1 (`pair2`, 5,602 ticks): the gold of both characters is written in lockstep tick
400 on both copies (500 → 12,345 for slot 0, 23,456 for slot 1), then nothing is pressed
for 5,400 frames. The periodic save (0x5E with its 0x5D piece) is answered with result 0
three times on each copy. Session 2, new processes with the same accounts: each copy
takes its character from the server's list by itself, the game is launched, and at tick 1
both copies have 12,345 and 23,456. The memory card has no part in it: no file of either
card directory changed after the copy's first boot.

## Findings

1. **The address word order** (above, "The entries").
2. **A timing dependency of the game's own launch.** On Start the host sends START to
   every peer, and `SRSClient_shutdownUdp` 0x328770 then waits for the acknowledgement
   before it disconnects: at most 100 rounds of `UdpManager_GiveTime` and
   `DelayThread(100)`. A joiner polls its socket every tenth frame, takes START, and
   fills its launch tables from the *live* connections on its next lobby-task call. On a
   console every empty receive of the peer library blocks 1 ms on the data socket and
   1 ms on the ICMP socket (the time-outs it asks for), so 100 rounds last over 200 ms —
   longer than the joiner's 167 ms between polls. With library calls that answer at once
   the 100 rounds are over in 10 ms: the joiner gets START and the disconnect in one
   poll, finds no live connection, fills its tables with address 0 (the uninitialised
   case `docs/netlib.md` describes under "Per-machine state", 2) and never launches.
   **Seen twice** before the fix: both copies in lobby state 12, the host sending 66
   datagrams, the joiner sending to 0.0.0.0:4000, no level. **Fix, in the driver**: a
   call that asked to wait and has nothing to give parks its game thread for that time
   on the virtual clock (`rt_sleep`) and looks once more. Every launch since has worked
   (13 of 13). The margin is the console's own: 200 ms against 167.
3. **The start ramp, and a check that was asked for.** In a lobby-launched game with
   nothing pressed, the stick value of the lockstep pad record (`g_pads[slot]+0x14`) is
   non-zero in ticks 1 to 5 (−0.25, −0.64, −0.75, −0.63, −0.24) for both slots on both
   copies, and both players move about 7 units; from tick 6 it is 0 and they stand. The
   same five values with the 26 sections and with "Net test: flush before a level load
   waits for the peers' tick" left out (25 sections), and the held word (+8) is 0 on every
   tick in both. The fault reported for the developer LAN start with that section (held
   word 0x500000 and stick bf91a47b for the whole game) **does not appear on the lobby
   path**: 1,797 and 1,815 idle ticks, and 1,845 more through a level load. With drawn
   input the record follows it (73 and 77 values of the held word, 126 and 105 of the
   stick, 508 and 476 positions) and ramps to 0 over five ticks when the stick is let go.
   One run each; native pair; `hub` and `drunare`.
4. **Bytes 0x38–0x3b and 0x50–0x53 of a pad record differ between the two copies** (two
   floats in the record of the other player's slot). Per machine; nothing in the
   comparison's shared columns depends on them.
5. **Other programs on the computer.** Game ports 4000–4004 are per computer: in most
   runs one native copy got another host port because a program on the computer held the
   game's number (other jobs ran emulator copies against the same lobby), which the rules
   above are made for. Once, after a native copy had quit, the emulator copy it
   had played with heard an arithmetic announcement from the port the native copy had
   used: another job's emulator had taken the freed port. Tests that share a computer
   share these ports.
6. **Two lines of the runtime's report that are not faults**: `eznetcnF.IRX` and
   `eznetctL.IRX` "not on the disc". They are the two configuration modules the game asks
   the loader for before it calls the clients this driver answers; the load is answered
   "loaded" and nothing reads them. No library entry went unanswered in any run, and no
   ERX file was asked for.

## Behaviour that differs from the emulator build

- No frame ever exists: there is no DHCP, ARP or DNS traffic, no TCP ended in a relay.
  The server and the other players see the same requests, replies and datagrams.
- TCP segments are cut by the host's stack (`TCP_NODELAY` is set, so the length word and
  the body the game sends separately leave as it sends them).
- The interface is "up" 20 vertical blanks after the game asks, where the emulator's
  stack takes its address by DHCP first.
- The arithmetic: as the emulator application since the second round - "can do both",
  the console's by default, a browser's while a browser copy is heard in the lobby or a
  room (ARM64; an x86-64 build still says "the console's only" and warns). Run with a page
  in both orders ("With a browser copy: the arithmetic").
- A peer's disconnect that arrives while the game is in a game's room is shown to it half
  a second late ("The disconnect hold"); the emulator build shows it at once.
- Library calls cost what they asked to wait and nothing else; on the emulator each is an
  RPC through the emulated I/O processor. Finding 2 is where that mattered.
- Nothing is relayed for `--arg --net` (the developer LAN start) by this driver:
  broadcast and made-up addresses are not carried. That start stays with
  `tools/recomp/net/netshim.cpp`.

## What remains for a native release online

**Timing.**

- The margin of finding 2 is the game's (200 ms against 167). A copy that is slow — the
  window program ran at about half speed under load here — stretches both sides alike,
  since both count frames; a joiner that stalls for a whole poll interval at the wrong
  moment would still lose the launch, as on a console. Not seen in 13 launches.
- A program without a window must be held to real time (`net-pace`, default 59.94): the
  lobby's time-outs count frames, the server answers in real time. Unpaced online runs
  were not tried.
- The game's thread must not stand still for long: the server drops a client it has not
  heard from for 120 s. Level loads take under a second here; the name sheet is a sheet
  for this reason (it does not stop the window's loop). A window being dragged, or the
  computer asleep, was not tried.
- The server's address is looked up before the game starts (a blocking `getaddrinfo`);
  inside the game nothing is looked up.
- Datagrams are read when the game asks, not at a frame boundary. Two native copies and a
  native with an emulator copy stayed in step with that; loss, delay and reordering on a
  real path were not tried (the loop-back interface loses nothing).

**Not exercised** (after the second round). Removing a friend or an ignore, what a
friend's logging off shows; *Kick Player*; deleting a character; importing a memory-card
character into the lobby; the "save the login on the memory card?" choice; the line to the
server cut during the lobby or a game (`app net drop` exists; the loop of `live-rig.md`
19.9 was not provoked); a dropped player coming back; a drop during a level load; the
game without the sign-in patch (it should stop at its sign-in error; not run); a server
that is not on this computer, two players on different networks, a router; a level change
or a fight in a game with a browser copy, three players with a browser copy, a native copy
with the emulator APPLICATION in a game of three or four (the application's builds were
being remade that night and were left alone); a person at the controls, and a person
typing into the name sheet. Exercised since and described above: private games, chat,
friends, three and four players, leaving by the pause menu and playing again in the same
run, cancelling, a player's and the host's program dying, a browser copy, the sheet.

**Windows.** Done since, as far as a Mac can take it (`docs/issues/native-windows.md`, "The
network"): the driver's socket calls are behind `tools/recomp/net/sock.h`, one header with
a BSD body and a Winsock body; `net/online_win.cpp` is the counterpart of `online_mac.mm`
(a Win32 dialogue for the name, the title note, the set warning); `net/posix_win.h` gives
`RtaOnline.cpp` the three file calls MinGW lacks, with an access list in place of mode
0600. `rta_app.exe` links all of it. The BSD body played three lobby games here (two
x86-64 copies; x86-64 with ARM64; the window program with a headless copy); the Winsock
body was compiled and read, never run. A build that does not link the driver still gets
the translated originals of the listed entries (`hle_weak.cpp`) and plays offline.

**Other.** The network settings program (Config) is kept away rather than run. The
`rta::NetDriver` shape in `iface.h` is still unused; if the runtime ever owns the library
entries, `netdrv.cpp` is one implementation of it.

## How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/net/build_online.py          # bin/rta_native_online (the sign-in patch from local/, when there)
python3 tools/recomp/app/build.py                 # bin/rta_app, with the network
O=local/recomp-out/online

# one copy to the game list
mkdir -p $O/n1
printf 'until 0x506160:u32 == 5 timeout 12000\nwait 600\napp online\nquit\n' > $O/lobby.rig
RTA_NATIVE=$PWD/local/recomp-out/bin/rta_native_online python3 tools/recomp/native.py boot \
    --card $O/n1/card --opt net-data=$O/n1 --opt net-local-only=1 --opt online=lobby \
    --opt online-name=SomeName --opt online-person=0 --opt net-log=$O/n1/net.log --script $O/lobby.rig

# two copies through the lobby into one game; --host / --join: native, window, app
python3 tools/recomp/net/lobbypair.py run $O/pair2 --play 3000 --level drunare --play2 3600
python3 tools/recomp/net/lobbypair.py run $O/x1 --host native --join app --play 3000
python3 tools/recomp/net/lobbypair.py run $O/x2 --host app --join native --play 3000
python3 tools/recomp/net/lobbypair.py run $O/pair1 --host window --join native --play 1800

# the save round trip: session 1 writes, session 2 reads the tick log's first row
python3 tools/recomp/net/lobbypair.py run $O/pair2 --idle --play 5400 \
    --tick-do "400 poke32 g_players+0xe4 12345" --tick-do "400 poke32 g_players+0x4c30+0xe4 23456"
python3 tools/recomp/net/lobbypair.py run $O/pair2 --idle --play 300

# a person: the window program, as the emulator build is started
tools/recomp/net/play-native.sh --disc "$RTA_DISC" --host
tools/recomp/net/play-native.sh --disc "$RTA_DISC" --player 2 --join CODE
```

```
# second round: three and four copies, the window program among them (a second server
# instance on ports + 2000; leave --port-shift out for the usual lobby on this computer)
python3 -B tools/recomp/net/lobbyparty.py OUT --players 4 --kinds window,native,native,native \
    --launches 3 --port-shift 2000 --play 1500 --level drunare --play2 3000
python3 -B tools/recomp/net/lobbyparty.py OUT --players 3 --scenario drop       # or hostquit, leave, late
# the name question on a test window, worked from inside the program
rta_app --test "name" --disc "$RTA_DISC" --data DIR -- --opt net-data=DIR --opt online=lobby \
    --opt online-test-window=1 --opt online-commands=DIR/commands.txt
echo "online sheet info" > DIR/commands.txt        # then: online sheet type NAME, online sheet press 0
```

A copy started by `lobbypair.py` keeps its name in `OUT/<role>/name` and its login in
`OUT/<role>/online-login`; a run directory can be used again (the character used last is
then taken by itself).

## Files

`tools/recomp/net/`: `hle-online.txt`, `netdrv.h`, `netdrv.cpp`, `online.cpp`,
`online_mac.mm`, `build_online.py`, `play-native.sh`, `lobbypair.py`, `lobbyapp.py`,
`lobbyparty.py` (second round). Local to the second round, not in the repository:
`local/native-lobby/` - `server/bin` (its lobby instance), `build.sh` and `snap/` (its
builds), `xstart.sh`, `xname.sh`, `xlib.py`, `rounds.py` (the window copies driven by
hand), `npage.py`, `redirect.c` (a page and the relay), the run directories.
Changed: `tools/recomp/recomp.py` (`--hle-add`, `--extra-pnach`), `tools/recomp/app/build.py`
(the network in `rta_app`). Linked unchanged: `tools/play-net/src/RtaOnline.cpp`.
Everything generated or logged: `local/recomp-out/gen-online*`, `obj-rta_native_online*`,
`bin/rta_native_online*`, `online/`.
