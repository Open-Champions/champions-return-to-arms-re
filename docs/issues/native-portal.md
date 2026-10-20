# The portal: what a player sees before and between games (Godot)

Started 2026-10-13. The owner: "Build a new sick as portal thats easy and plug and play with
friends list, etc their character name". This replaces the 2005 "SOEGAMES.NET Login" screens of
the native build inside Godot (`native-godot.md`). Every statement says **Ran** (with what was
seen) or **Read** / **not run**. Kept current; a successor needs only this file.

Nothing derived from the game is in the repository: the portal is scripts and two shaders, drawn
by code. Names of characters, classes and levels on screen come from the session or the game's
state at run time. Pictures, the staged project and logs are under `local/godot-portal/`.

## STATE (2026-10-19): the whole way on the real service, the game in scene mode, in step through a level change

- **Ran: two portal programs WITH THE GAME IN SCENE MODE through a service of their own** (`local/godot-r5/test/room.py
  loc2`: `tools/rendezvous/rendezvous.py` on 127.0.0.1; the staged project of `RTA_GODOT_OUT=local/godot-r5`, Forward+
  on Metal, the art pack; each program its own data folder, identity and memory card; scenario `room5` of
  `dev/shots.gd`).  In order: first start and the name on both -> B types A's friend code -> A gets the request card,
  one press (Y) -> both friends, **presence "online"** -> A hosts -> **A invites B from the friends list (X)** -> B gets
  the invitation card, one press -> both in the room -> the game scene boots behind each portal -> the game's own
  character screens (walked by each copy's script, as n2party does) -> back in the room with the character -> A's
  Start -> both in the hub (tick 90) -> at lockstep tick 1121 both copies change to drunare (`tick-do`: the pending
  level written on each copy at the same tick, as native-rendezvous.md section 6 does) -> both play on there.
  **Tick logs compared** (`tools/rig/compare.py ticks`): 1851 ticks (hub 1120, drunare 731), "no shared column
  differs on any tick" (seed, level, player count, button maps, both players' position, state, hit points, gold,
  experience, out-of-step flags, own sync hash).  Pictures: `local/godot-r5/test/loc2/pictures/real5/` (a-01 ...
  a-09, b-01 ... b-09), contact sheet `local/godot-r5/test/loc2/pictures/sheet.jpg`.
- **The public service** (named by its host name with `--service`, never in a file here; TLS by the client's rule):
  **Ran in part.**  `room.py pub2 --join-by code`: both programs online through TLS ("link 2"), B's friend request
  reached A, A accepted and saw B online (presence 1), A hosted; then A's test window stopped drawing (the
  off-screen window above) and the run went no further - B's friends list never filled in that run, B joined
  nothing.  After the window fix (`pub3`, `pub4`, 18:30-19:05) neither program got past "link 1": from about 19:00
  the service's port answers a TLS hello with no TLS (`openssl s_client`: "wrong version number"; at 12:50 the
  same command got the certificate for the host name, verify 0) and sends no greeting in plain text either.  Nothing
  on the server was touched from here; the machine stood at a load average of 210 at the time.  Left: the public run
  again once the service answers TLS again (`python3 local/godot-r5/test/room.py pubN --service HOST:41900
  --join-by code`).
- `handover.gd`: the game scene is handed over in **scene mode** (`opt.mode = "scene"`; `--mode` on the command line
  still decides).  `portal.gd` `character_card()` gives the game's card of the local character (main.gd
  `get_character_card`, scene mode); `widgets.gd` `Portrait.live` takes it in place of the drawn stand-in (home card,
  my seat in the room, the current character on the character screen).  Not seen in a run: the runs stood in the
  overhead view at the moment of the pictures, and `has_character_card()` was false ("character card none").
- Found: `portal.gd` opened the session with `local_only` in every test, so a test could not reach the public service
  ("link 0"); `RTA_PORTAL_PUBLIC=1` lets a test out.  `net2_game_status().level` stays the level the launch named
  (it said "hub" in drunare): for the owner of `tools/recomp/net2/launch.cpp`.
- Found: a test window wholly off the screen is not drawn by Godot on macOS - a portal program stopped at
  `frame_post_draw`; `RTA_TEST_OFFSCREEN=1` puts the windows beyond the screen's edges but for two points of a
  corner (a: lower right, b: lower left - one window over another's corner hid it too).

## STATE (2026-10-14, 00:10): a real launch from the portal

- **Ran: two portal programs WITH THE GAME through a local service, two games in a row**
  (`python3 local/godot-portal/portal.py duo2 duo2`, 469 s). Each program: the portal as the
  first thing, the game scene (`res://main.tscn`, the game library of 23:32 with net2) put
  under it, its own data folder, identity and memory card; the service
  `tools/rendezvous/rendezvous.py` on 127.0.0.1:41962. What each did, from the log:
  first start and name -> online -> A hosts / B joins by the code -> **the game scene
  starts behind the portal** (`--opt net2-boot=1`: it walks to its title screen by itself;
  the room says "Your game is getting ready...") -> title: "Choose your character" ->
  `game_choose` -> **the game's own character screens get the screen and the controller**
  -> chosen: the portal is back in front ("Playing aaa (level 1)"), B is marked ready by
  itself -> A's Start -> "finding each other" -> the game's own "Network Game Launch"
  screen (both characters, "Ready!") -> **both in the hub** (tick 90+, "2 players") ->
  B leaves by the pause menu, A's game goes back to its title -> **both portals back in
  front, the room open, "Play again"** -> characters again -> Start -> **both in the hub a
  second time**. The second game was not left (the run ended in it).
  Pictures: `local/godot-portal/pictures/real2/` - `a-1-08-in-the-hub.png`,
  `b-1-08-in-the-hub.png` (the moment both are in the hub), `a-1-05-everybody-ready.png`,
  `a-1-07-the-games-launch-screen.png`, `b-1-09-back-in-the-room.png`, `a-2-08-in-the-hub.png`.
- **The character screens: handed over, not driven.** The portal calls `game_choose` and gives
  the game the screen and the controller (main.gd's `hold_input` follows the portal's
  `shown_changed`); a player makes a character or imports one there, and the portal comes
  back by itself when the game says CHOSEN (or TITLE with `failed`: "No character was
  chosen"). Pressing the game's screens for the player would break on any change of them.
  In the test the screens were walked by each copy's script (`--script`, the lines of
  `tools/recomp/net2/n2party.py`, as the Godot agent's flow does) - a person's presses.
- **Difficulty**: the list is cut to `game_status().difficulty_unlocked` (Easy only on a new card:
  `a-1-05`, "More as your game unlocks them").
- **Found: `net2_game_status()` crashes the program when it is called before the game's machine
  runs** (SIGSEGV in the library: it reads the options record of the game's memory,
  `rd32(A_SAVED_CONFIG)`, unconditionally; launch.cpp line 681). The portal now asks for it
  only once `main.gd` says the machine has started and says "booting" until then
  (`gameflow.gd`); the library should answer BOOTING by itself (for the online agent).
  It can also answer `difficulty_unlocked` 5 (the portal caps it at 4).
- Changed after the run: the room's line while the game goes back to its title after a game
  says "Back to the title screen..." instead of "Your game is getting ready..." (in
  `b-1-09` it still says the latter).
- New: `tools/godot/project/portal/gameflow.gd` (the game's side of a room), `handover.prepare()`;
  the extension is the Godot agent's (RtaNet2 on the library's net2) - nothing of the portal
  is in `tools/godot/extension` any more except `rta_net2.*`, which the Godot agent now keeps.
- Nothing of this work is running (the pids of `local/godot-portal/test/duo2/pids` are gone;
  the service was stopped by `portal.py`).

## STATE (2026-10-13, night): on the real service

The project's home is `~/champions-re` now (`docs/issues/workspace-move.md`);
`local/godot-portal/` survived the move whole (flags only: no evicted file), the snapshot of
`tools/godot` was taken again after it (`local/godot-portal/snap/SNAPSHOT.txt`).

- **Ran: two portal programs through the real service** (`tools/rendezvous/rendezvous.py` on
  127.0.0.1:41961 with a data folder of its own; each program its own data folder, so its
  own identity file; `python3 local/godot-portal/portal.py duo duo`, three runs, 40 s each,
  nothing waited in vain). In order, as a person would do it (keyboard events; the
  programs only learn what a person would read out through two files in a sync folder):
  first start and the name on both; B types A's friend code; A gets the request card and
  accepts it with one press (Y); both see each other online **with the character they
  publish** (name, level, class); A hosts; **B's friends list shows A "in a room - you can
  join"**; B joins by typing the code; chat both ways; B ready; A starts; **the routes come
  up: "Connected - 16 ms", a direct route punched between the two programs**; the portal
  gets out of the way; the room is open again after the game; "Play again"; B leaves; A
  invites B from the friends list (X); B gets the invitation card and joins with one press.
  Pictures: `local/godot-portal/pictures/real/a-01 ... a-15`, `b-01 ... b-16`.
- **The game between "start" and "over" is the stand-in** (`dev/stub_game.gd`): the Godot game
  library of 22:46 has no net2 game side (`nm`: no `net2_*` symbol; `launch.cpp`, the
  network driver and the online translation are not linked into it - native-rendezvous.md
  5.1). The stand-in says to the room what `launch.cpp` says in a program with the game:
  `running` after 2.5 s and `over` after 8 s (`net2_game_state`). So **not run: two copies
  landing in the hub from the portal's Start**, and "Play again" into a second real game.
  The portal side of it is written against `session.h` (EV_START -> the room stays in front
  until the room says "in game", then the game scene has the screen; EV_GAME_OVER -> back in
  the room) and was run with the stand-in only.
- **Ran: no service named** (the real client, no `--portal-service`, no `RTA_NET2_SERVICE`, no
  `net2-service.txt`): the line at the bottom says "Offline - playing alone works (No service
  was named)"; Friends says it in one sentence with a button "Set the address"; Settings ->
  Online has the sentence and a field. An address typed there is written to
  `<data>/net2-service.txt` (where the client looks) and the session is opened again; with
  nobody listening the page says the client's own words: "The service at 127.0.0.1:41999 does
  not answer: Connection refused - trying again." Pictures `real/noservice-01 ... 05`.
- **The extension with the service**: `rta_net2.*` take the grown records (`mission`,
  `kill_limit`, member `phase`). Built with `session.cpp session_mock.cpp session_net.cpp
  carrier.cpp cardchars.cpp`, no `NET2_NO_SERVICE`: (1) by `portal.py ext` (the build switch:
  `PORTAL_NET2=mock` for the mock only), (2) **from clean with the Godot agent's
  `CMakeLists.txt` plus the change below** in a private copy: 1039 steps, 0 warnings, with
  the service (`socket`, `CC_SHA256` imported) and with `-DRTA_GODOT_NET2_SERVICE=OFF`
  (no socket code); the two-program run passed on that build.
- Room options now as the online agent answered: difficulty Easy / Normal / Hard / Harder
  (1..4, a new room takes 1), who may join. Mode, mission and kill limit are not shown: only
  missions are wired into the launch. Not done: limiting the difficulties to
  `net2_game_status().difficulty_unlocked` - that is a game-side call, absent from this
  library.
- Nothing of this work is running: every program was started by `portal.py` and waited for;
  the services were stopped by `portal.py` (terminate, then waited). See "Processes".

### What has to be merged for the service (Godot agent: `tools/godot/extension/CMakeLists.txt`)

`local/godot-portal/cmake-proposal/CMakeLists.diff` against today's file:

```cmake
option(RTA_GODOT_NET2_SERVICE "RtaNet2 talks to the real service (socket code); OFF: the mock only" ON)
...  # inside the RTA_GODOT_NET2 block, after cardchars.cpp:
    if(RTA_GODOT_NET2_SERVICE AND EXISTS "${RTA_NET2_DIR}/session_net.cpp" AND EXISTS "${RTA_NET2_DIR}/carrier.cpp")
        list(APPEND RTA_GODOT_SOURCES "${RTA_NET2_DIR}/session_net.cpp" "${RTA_NET2_DIR}/carrier.cpp")
        set(RTA_GODOT_HAVE_NET2_SERVICE ON)
    endif()
...  # in place of  RTA_GODOT_HAVE_NET2=1 NET2_NO_SERVICE=1
    target_compile_definitions(rta-godot-extension PRIVATE RTA_GODOT_HAVE_NET2=1)
    if(NOT RTA_GODOT_HAVE_NET2_SERVICE)
        target_compile_definitions(rta-godot-extension PRIVATE NET2_NO_SERVICE=1)
    elseif(WIN32)
        target_link_libraries(rta-godot-extension PRIVATE ws2_32 bcrypt)
    endif()
```

No new include path is needed (`session_net.cpp` and `carrier.cpp` reach `../net/sock.h` by
a relative include; CommonCrypto and `arc4random_buf` are in macOS's libSystem). The
Windows line is Read, not built.

### The next step, once the game library carries net2 (Read; written down, not built)

- **One copy of net2 in the process**: `RtaNet2` must then call the library's `net2_*`
  (resolved from the loaded library as `RtaMachine` resolves `rtag_*`) instead of its own
  compiled copy; otherwise the game's launch and the portal look at two different session
  objects. Until then the extension's copy is the only one and is right.
- The portal then calls `net2_game_attach(n)` once, polls `net2_game_status()` once a frame,
  and follows native-rendezvous.md 5.1: in a room without a character -> `net2_game_choose`
  and hand the screen to the game (its own character screens); CHOSEN -> back in front,
  `net2_ready(1)`; EV_START -> "finding each other" (written); LAUNCHING/LOADING/RUNNING -> out
  of the way (written: `handover.start(..., false)` then `reveal`); TITLE after RUNNING ->
  back in front, the room open again (written: EV_GAME_OVER). The places in the code:
  `portal.gd` `_on_event`, `handover.gd`.

### Pictures of the real flow (`local/godot-portal/pictures/real/`)

`a-04-request-arrives.png`, `a-05-friends-two-is-online.png`, `b-07-friends-one-is-in-a-room.png`,
`b-09-in-the-room.png`, `a-10-connected.png`, `a-12-back-in-the-room-play-again.png`,
`b-15-invitation-arrives.png`, `b-16-joined-with-one-press.png`, `noservice-02-friends.png`,
`noservice-05-nobody-there.png`.

## STATE before (2026-10-13, 14:45)


- **Ran:** every screen below, in an off-screen viewport at 1920 x 1080 (and 1440 x 1080,
  1280 x 720, 2560 x 1080, 3840 x 2160, 1024 x 768) driven by the same events a controller, a
  keyboard and a mouse send, against the online agent's mock
  (`tools/recomp/net2/session_mock.cpp` through the extension's `RtaNet2`). 95 pictures.
- **Ran:** the scripted walk-through with a controller - first start -> the name -> home -> host
  -> a friend walks in -> ready -> start ("finding each other", routes) -> the game (a stand-in) ->
  back in the room with "Play again": `local/godot-portal/pictures/walk-01 ... walk-12`.
- **Ran:** the portal in front of the REAL game scene (`res://main.tscn`, the game library of
  14:00, interface version 6, the owner's disc image): "Play alone" put the game scene under the
  portal, the machine booted and ran 655 vertical blanks at the game's own first screen; an
  invitation card showed over the running game; the portal came back in front of the stopped
  game with its picture blurred behind; the program ended through the game scene's own
  `_finish` (machine stopped, figures printed). Pictures `real-01 ... real-05` (game output:
  they stay under `local/`).
- **Ran:** the portal as the project's real first scene in a window (640 x 360 test window,
  `window-first-start.png`); and `--no-portal`: the game scene started as before the portal
  existed (240 blanks, exit 0).
- **Ran:** the extension from clean with the Godot agent's `CMakeLists.txt` as it stands
  (`local/godot-portal/build/cmake-clean`: 1036 steps, 0 warnings, 0 errors; `rta_net2.cpp`,
  `session.cpp`, `session_mock.cpp` in it), and the portal against that build.
- **Not run:** a real controller (events are injected); a real service (the extension is built
  with `NET2_NO_SERVICE`: there is no socket code in it); a game started from a room for real
  (the launch is `net2/launch.cpp`'s; the portal only gets out of the way); the camera view and
  picture settings arriving in a running game beyond "the options are written" (Read).
- Nothing of this work is running; test windows were 480 x 270 to 640 x 360 points, titled
  "AGENT TEST ...", without focus, in the screen's corner, silent.

### Pictures to look at first (`local/godot-portal/pictures/`)

- `walk-02-name-typed.png` (the one question, with a controller), `state-home.png`,
  `friends-more-selected.png` (the list, a friend who can be joined), `walk-08-everybody-ready.png`
  (the room), `walk-10-starting-connected.png`, `walk-12-back-in-the-room.png`.
- `friends-none-yet.png`, `friends-eight.png`, `friends-forty.png`, `friends-long-names.png`.
- `room-different-version.png` (the warning, only when something is wrong), `join-room-full.png`.
- `settings-view.png`, `settings-controls.png`.
- `ratio-4x3-room.png`, `ratio-21x9-home.png`, `ratio-720p-friends.png`, `ratio-4k-home.png`.
- `real-03-invitation-over-the-game.png`, `real-05-friends-in-front-of-the-game.png`.

### How the pictures are made

```
python3 local/godot-portal/portal.py ext        # once, and when the extension's sources change
python3 local/godot-portal/portal.py shots NAME -- [--only walk,states,friends,room,join,settings,ratios]
python3 local/godot-portal/check.sh             # parse-check of every script
```

`dev/shots.gd` is the test window's scene: it puts the portal into a `SubViewport` of the wanted
size, sends `InputEventJoypadButton` / `InputEventKey` / mouse events into it, waits on the
session's state (not on the clock) and saves the viewport's texture. `--only real` with the game
scene's own options (`--disc`, `--test`, `--mute`, `--size`, `--data`, `--workspace`) is the run
with the real game. `local/godot-portal/snap/` is `tools/godot` as it was at 14:20 (the second
snapshot: the library's interface had moved from version 5 to 6 in between, and an extension
built from the older header refuses the newer library - the game scene says so in words).

## Where things are

```
tools/godot/project/portal/           everything of the portal (new directory)
  portal.tscn, portal.gd              the first scene: layers, screens, modals, input, what the session says
  session.gd                          THE one script between the screens and the online session (RtaNet2)
  profile.gd                          portal.cfg: the name, the character played last, known characters, settings
  handover.gd                         into the game scene and back
  ui.gd, widgets.gd                   the look (colours, fonts, drawing) and the controls (all drawn by code)
  screen.gd                           base of a screen: rebuild from state, focus by key, text with a controller
  keys.gd                             on-screen letters for a controller
  notices.gd                          invitations / requests: one press answers
  background.gdshader                 the animated background (arithmetic only)
  backdrop.gdshader                   the game's picture blurred and dimmed behind the portal
  screens/first.gd disc.gd home.gd friends.gd join.gd room.gd characters.gd settings.gd
  dev/shots.gd, shots.tscn            pictures and the scripted walk-through (development aid)
  dev/stub_game.gd                    a stand-in for the game scene (pictures, tests)
tools/godot/extension/src/rta_net2.h, rta_net2.cpp     RtaNet2: session.h for Godot scripts (new files)
local/godot-portal/portal.py          ext | stage | shots NAME | run NAME   (local helper, not in the repository)
local/godot-portal/check.sh           parse-check of every portal script (headless)
local/godot-portal/pictures/          every picture
local/godot-portal/snap/              tools/godot as it was when this work started
```

## What must be merged (and by whom)

1. **The one line** (Godot agent, `tools/godot/project/project.godot`) - merged by now:
   `run/main_scene="res://portal/portal.tscn"` in place of `res://main.tscn`.
   Everything that starts the game scene directly keeps working: with `--no-portal`, with
   `--script FILE` (every test route) or headless, `portal.gd` passes straight on to
   `res://main.tscn` in its first frame and does nothing else.
2. **The extension**: `rta_net2.h/.cpp` are new files in `tools/godot/extension/src`; the Godot
   agent's `CMakeLists.txt` already compiles them with `tools/recomp/net2/session.cpp` and
   `session_mock.cpp`, include path `tools/recomp/net2`, `NET2_NO_SERVICE=1`, and `register.cpp`
   needs `#include "rta_net2.h"` + `GDREGISTER_CLASS(RtaNet2);` (coordinator: already picked up).
   Nothing else in the extension is touched. Without `RtaNet2` the portal runs and says "offline".
3. **For the real service**: the CMake change above (section "What has to be merged for the
   service"). The address: `--portal-service HOST:PORT`, else the client's own order
   (`RTA_NET2_SERVICE`, `<data>/net2-service.txt` - what Settings -> Online writes - then the
   built-in default). The portal passes `local_only` in a test.
4. **For the HUD agent** (the tiny signal): `get_tree().get_first_node_in_group("portal")` has
   `signal notice(d)` (`d = {id, kind: "invite"|"request", who, seed, title, text, accept_text}`),
   `signal notice_gone(id)`, `func notice_answer(id, accept)`, and `var draw_notices_in_game`
   (set it false to draw them in the HUD's own style; until then the portal draws one small card
   top right, answered with F2). `signal shown_changed(is_shown)` says when the portal is in front.
5. **For the game scene** (Godot agent; optional, see "Hand-over"): a way to say "the game is
   over" other than quitting, and holding the controller while the portal is in front.

## The screens

| Screen | What it does | Pictures (`local/godot-portal/pictures/`) |
|---|---|---|
| first start | one question, "What should friends call you?"; a keyboard types, a controller gets letters on screen; nothing else is asked - the session is only opened once the name is there | `walk-01`, `walk-02` |
| disc | when the disc image has not been found: one sentence, one button (native file dialog; the path goes where `main.gd` reads it, `user://settings.cfg` `[game] disc`). Home also carries the sentence as a strip until it is found | `state-disc-missing`, `state-home-no-disc-no-character` |
| home | Play alone / Host a game / Join with a code / Friends, and the character card (name, level, class of the character played last; "Change character") | `state-home`, `walk-03` |
| friends | invitations and requests first; then playing now / online / asked / offline. Each friend: name, what they do (joinable? where?), the character they play. A = join (or invite), left / right = the row's other actions, X = invite, "more" = remove / block behind a question. Right: my code (copy), add by code, played with lately (+Add), blocked | `friends-six`, `friends-eight`, `friends-forty`, `friends-none-yet`, `friends-long-names`, `friends-more-menu`, `friends-block-question`, `friends-add-code-keys` |
| join | five characters, typed or picked; the service's own words when it fails; friends whose room can be joined now beside it | `join-empty`, `join-no-such-room`, `join-room-full`, `join-game-started`, `join-controller` |
| room | four seats (name + character card, ready mark, host), the code large, chat, the host's choices (difficulty, who may walk in), Start / Ready, Invite, Leave; a red line only when versions differ; "finding each other" with the route per member after Start; "Play again" after a game | `walk-05 ... walk-10`, `walk-12`, `room-guest`, `room-different-version`, `room-host-seat-menu` |
| characters | the characters known on this computer, "New character" (handed to the game's own screen) | `state-characters`, `state-characters-new` |
| settings | View (five camera views as diagrams), Display, Sound, Controls (controller picture / keyboard), Interface (new / original), You (name, code, "forget me online") | `settings-*` |
| notices | invitation / request cards: Y (controller or key) or a click answers from anywhere; in the game one small card, F2 | `state-home-invitation`, `state-in-game-invitation` |

Input: Godot's own focus moves with the direction pad / stick / arrow keys; A / cross / Enter
presses; B / circle / Esc goes back (asks before leaving a room or quitting). Godot's built-in
"accept" and "cancel" actions have no controller buttons - `portal.gd` adds A and B to them at
run time (`_controller_actions`; the project's settings are not touched). Pointing with the
mouse gives the focus, so there is one highlight. The hints at the bottom follow the last device
used and the controller's make (letters or the PlayStation shapes).

Sizes: everything is laid out in "design pixels" of a 1080-high picture and multiplied by
`UI.s = min(height / 1080, width / 1440)`; a screen is rebuilt when the viewport changes.

## The interface the portal calls

`session.gd` only (see its head). It mirrors `tools/recomp/net2/session.h` one to one through
`RtaNet2` (records as Dictionaries with the structs' field names): `me`, `friends`, `recent`,
`blocked`, `requests`, `invites`, `room`, `session`; `set_name`, `set_character`, `set_game`,
`local_characters`, `delete_everything`; `friend_add`, `friend_add_id`, `friend_accept`,
`friend_decline`, `friend_remove`, `block`, `unblock`; `invite`, `invite_accept`,
`invite_dismiss`; `host`, `join`, `join_friend`, `chat`, `ready`, `set_options`, `kick`, `start`,
`leave`; events by `poll()`. The portal does **not** call `net2_game_state` - that is the
launch's (`net2/launch.cpp`).

From the game: `RtaGameState` once a second while a game runs (`handover.gd`): the local player's
name / class / level -> "the character you played last" and `set_character`; the level's name ->
`set_game`.

## Hand-over (Ran with the stand-in and with the real game scene)

- `handover.start(intent)` instantiates `res://main.tscn` under `Portal/Game` the first time and,
  before its `_ready` reads the command line, writes into its `opt`: `disc`, `view`,
  `aspect_window`, `size` (sharpness). The portal's layer (CanvasLayer 20) fades out.
  `intent = {kind: "alone" | "session" | "create", character, session}` is there for the launch.
- A session start (`NET2_EV_START`): the game scene is made / woken at once, the room stays in
  front ("finding each other", routes per seat) until the room says "in game" (or 8 s), then the
  portal leaves.
- `handover.finish(why)`: on `NET2_EV_GAME_OVER`, or F9 (provisional), the portal comes back; the
  game scene is stopped (`process_mode` disabled, its sound paused) and its last picture shows
  blurred and dimmed behind the portal (`backdrop.gdshader`). **Ran** with the stand-in:
  `state-home-over-the-game`, `walk-12`.
- **Ran** with the real game scene: start, the notice over the game, `finish("key")`, the blurred
  picture behind, and the end of the program through `main.gd`'s own `_finish` (`quit_game`).
- **Open** (needs the Godot agent): `main.gd` ends the program when the machine ends
  (`_finish` -> `quit`); a game that returns to the portal needs the game side to say "over"
  without quitting (the machine is one run per process). And while the portal is in front of a
  game that must keep running (a session), `main.gd` still reads the controller.

## What is real and what is mocked

| | |
|---|---|
| the screens, input, layout, settings file, hand-over mechanics | real |
| friends, presence, rooms, chat, invitations | the online agent's **mock** (six friends, a request, an invitation at 12 s, a room that fills...) through the real client interface; lists of 0 / 8 / 40 friends in the pictures are injected by `dev/shots.gd` (`session.friends_for_pictures`) |
| the game behind the hand-over | a **stand-in** (`dev/stub_game.gd`) in the pictures |
| "your characters" | what the portal has seen played + `net2_local_characters` (empty until the launch code supplies the card reader); in the pictures the list is seeded by `dev/shots.gd` |
| the character's picture | a **drawn stand-in** (`widgets.gd` `Portrait`); `Portrait.texture` takes a live viewport when the game scene can show one character |
| settings: view | stored; given to the game at the hand-over (`opt.view`) and at once to a running game (`machine.set_option("view", ...)`) - the options were written in the real run; that the view changed was not looked at |
| settings: window / full screen, master volume | applied by the portal (never in a test) |
| settings: sharpness, picture shape | stored; given to the game scene at its first start |
| settings: music / effects volume | **stored only** - needs a switch on the sound side |
| settings: interface new / original | written where the HUD reads it (`hud.cfg`, `[hud] mode`) when the portal's folder is `user://` |

## Open questions (asked through the coordinator)

1. Answered (online agent): difficulty 1..4, mode / mission / kill limit not wired yet, member
   phase; the room shows difficulty and who may join.
2. Answered: the client finds the service itself; the owner decides the built-in default.
3. Godot agent: can the game scene show one character alone (for the card), and may the title
   scene run behind the portal before the first game? Until then: the drawn stand-in and the
   portal's own background.
4. HUD agent: who draws the in-game notice, and which controller button answers it (F2 on the
   keyboard now; nothing on the controller, so that no game button is taken).
