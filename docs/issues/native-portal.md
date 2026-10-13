# The portal: what a player sees before and between games (Godot)

Started 2026-10-13. The owner: "Build a new sick as portal thats easy and plug and play with
friends list, etc their character name". This replaces the 2005 "SOEGAMES.NET Login" screens of
the native build inside Godot (`native-godot.md`). Every statement says **Ran** (with what was
seen) or **Read** / **not run**. Kept current; a successor needs only this file.

Nothing derived from the game is in the repository: the portal is scripts and two shaders, drawn
by code. Names of characters, classes and levels on screen come from the session or the game's
state at run time. Pictures, the staged project and logs are under `local/godot-portal/`.

## STATE (2026-10-13, 14:45)

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

1. **The one line** (Godot agent, `tools/godot/project/project.godot`):
   `run/main_scene="res://portal/portal.tscn"` in place of `res://main.tscn`.
   Everything that starts the game scene directly keeps working: with `--no-portal`, with
   `--script FILE` (every test route) or headless, `portal.gd` passes straight on to
   `res://main.tscn` in its first frame and does nothing else.
2. **The extension**: `rta_net2.h/.cpp` are new files in `tools/godot/extension/src`; the Godot
   agent's `CMakeLists.txt` already compiles them with `tools/recomp/net2/session.cpp` and
   `session_mock.cpp`, include path `tools/recomp/net2`, `NET2_NO_SERVICE=1`, and `register.cpp`
   needs `#include "rta_net2.h"` + `GDREGISTER_CLASS(RtaNet2);` (coordinator: already picked up).
   Nothing else in the extension is touched. Without `RtaNet2` the portal runs and says "offline".
3. **For a real service** (online agent + Godot agent): build the extension without
   `NET2_NO_SERVICE` and with `session_net.cpp`; give the portal the address (`--portal-service
   HOST:PORT` or `[online] service=` in `portal.cfg`). The portal passes `local_only` in a test.
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

1. Online agent: what the host can choose. The room shows `difficulty` as "The game's own, 1, 2,
   3, 4" and `open_to`; `level` and `mode` are not offered. Names for the difficulties and a list
   of start levels have to come from the game at run time.
2. Online agent: the address of the service for players (the portal has no default).
3. Godot agent: can the game scene show one character alone (for the card), and may the title
   scene run behind the portal before the first game? Until then: the drawn stand-in and the
   portal's own background.
4. HUD agent: who draws the in-game notice, and which controller button answers it (F2 on the
   keyboard now; nothing on the controller, so that no game button is taken).
