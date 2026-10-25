# Contributing

Everyone is welcome, whatever your experience. This is a large job and it only gets done
if many people can add small, trustworthy pieces.

## What may not be committed

Nothing that comes from the game:

- the executable, the disc image, or anything unpacked from it (models, textures, audio,
  level files, compiled scripts);
- full disassembly or raw decompiler output;
- game text such as dialogue.

What is fine: addresses, names you chose, struct layouts, descriptions in your own words,
pseudo-code you wrote yourself, and short identifiers the game exposes (class names, script
command names, file names). The `.gitignore` is a whitelist to make mistakes hard; do not
weaken it.

Independently authored C++ reconstructions belong in the dedicated
[Return to Arms source repository](https://github.com/Open-Champions/champions-return-to-arms).
The hand-written native C++/Godot rebuild for both games belongs in
[open-champions-godot](https://github.com/Open-Champions/open-champions-godot).
Keep research, symbol maps, original-file analysis tools, the translated native game and
its Godot host here. Every gameplay change follows the rules in
[docs/DIRECTION.md](docs/DIRECTION.md): lockstep-safe, a room option all copies agree on,
tested in multi-copy rooms, byte-identical to the original with the mode off. See
[the repository map](docs/REPOSITORIES.md) before starting work.

## The one rule about claims

Say how you know. Every statement in `FINDINGS.md` and the area documents is one of:

- **Observed** — you read it in the bytes at the address you give.
- **Inferred** — it follows from observations, but you did not see it directly.
- **Unknown** — not established; say what would settle it.

Two more words are used for things that were run, not read:

- **Executed** — one function at a time was run in `tools/ee_emu.py` on state a test
  built; name the test.
- **Ran** — it was seen on the running game; say on what. So far that has always been the
  Play! emulator, mostly the two-machine rig of `docs/issues/live-rig.md`. Do not write
  "Ran" for PCSX2 or a console unless it ran there.

A wrong name costs more than a missing one, because people build on it. If you are not
sure what a function is, leave it unnamed or name only what you can prove
(`creature_setField2fc` beats `creature_applySlow` until you have seen who reads the
field). Nothing counts as confirmed on a running game unless someone ran it and says so.

## What to work on

The open items as of 2026-10-12, taken from the "not done" and "not tried" lists of the
documents named. [docs/STATE-OF-PLAY.md](docs/STATE-OF-PLAY.md) says what works today.
Several of these are being worked on; open an issue or look at the document's status
line before you start.

What needs a machine or a person the project has not had:

- **PCSX2 or a PlayStation 2.** Nothing has run on either: the DNS override, the sign-in
  step, two clients meeting, the patch file, staying in sync
  ([docs/online-setup.md](docs/online-setup.md), "Not checked";
  [docs/VALIDATION.md](docs/VALIDATION.md) is the procedure).
- **Two different computers in one game.** Every pair so far was two copies of one build
  on one Mac. Two Macs with the Mac application is the first case to try
  ([docs/play-online.md](docs/play-online.md) section 8;
  [docs/issues/float-divergence.md](docs/issues/float-divergence.md)).
- **Two networks.** A session between two homes, through real routers
  (docs/play-online.md section 7; [docs/lobby-protocol.md](docs/lobby-protocol.md)
  section 13).
- **A person playing the Mac application.** Type the player name and the room code, press
  buttons on a real controller (USB, Bluetooth, other makes), listen to the sound, look at
  the inventory, shop, skill and map screens, cast spells, visit more levels
  (docs/play-online.md section 8).
- **More than two players.** No run with three or four machines is reported yet
  ([docs/issues/live-rig.md](docs/issues/live-rig.md) section 22.8).
- **The browser build by hand and in other browsers.** A controller, the file dialog, full
  screen, the sound; Safari and Firefox; anything beyond the first level
  ([docs/issues/browser-build.md](docs/issues/browser-build.md), "Left to do").

What can be done with the tools here:

- **A soak for the touch-handler section**, the one section of the suggested set that has
  not been in one ([docs/issues/touch-handlers.md](docs/issues/touch-handlers.md)
  section 8).
- **Open ends of the last soak** (docs/issues/live-rig.md section 22.8): who reads the two
  bytes of local effect state that differ between machines; cases the random input never
  made (a skill or stat point spent, the workshop, a save-point prompt with a card screen
  open); pairs longer than 17 minutes of play; the pause-menu kick that ended four pairs
  ([docs/issues/online-quality.md](docs/issues/online-quality.md) has started on it).
- **Lobby protocol**: the open questions of docs/lobby-protocol.md section 13.
- **Browser build**: the relay and the network module for online play among browser
  players; linking translated blocks; pacing by the display's refresh; one of the two
  ways to let browser and Mac players share a game, which they cannot as built
  (docs/issues/browser-build.md, "Left to do" and "Ways out").
- **Native build**: the I/O services, then a renderer, sound, the network and a Windows
  build; a comparison with fighting, input and a level change
  ([docs/issues/native-recomp.md](docs/issues/native-recomp.md), "What a playable native
  application still needs").
- **Formats**: an unpacker for the level textures in `<LEVEL>.TEX`; the camera key types
  of `.cut` files ([docs/FORMATS.md](docs/FORMATS.md)).
- **Tools**: the gaps of `tools/ee_emu.py` listed in `docs/spec/creature-tick.md` section
  17; the writers `tools/ghostreach.py` misses (`docs/issues/field-claims-audit.md`
  section 6.3); the false function starts `tools/ps2elf.py` makes
  (`docs/issues/vtable-labels.md`).
- **Names**: pick an area from [docs/STATUS.md](docs/STATUS.md).

## Adding symbols

Symbols are tab-separated: address in hex without `0x`, name, optional note.

```
001b9cb8	Player_usePotion	guarded against the prediction copy; menu path differs for the local player
```

- Put them in `symbols/<area>.tsv`, where the area is one from `docs/STATUS.md`.
  `names.tsv` is the original core list; fix mistakes there but add new work under
  `symbols/`.
- Functions: `Class_method` for members, `subsystem_verbNoun` otherwise. Globals: `g_name`.
- The note should carry the evidence or the caveat.
- Run `python3 tools/symtab.py check` (no conflicts, no malformed lines) and
  `python3 tools/coverage.py --write` before you open a pull request.

## Writing an area document

`docs/<area>.md` should let the next person skip the work you did: what the subsystem does,
its data structures as offset tables, the functions that matter, and what is still open.
Mark anything that reads per-machine state (camera, audio position, the local player slot,
menus, hardware timers, what was drawn) while changing shared game state — those are the
places online play breaks. `docs/OVERVIEW.md` explains the distinction.

## Testing on a running game

For PCSX2 and consoles this is still the biggest gap. The project's own rig joins two
copies of the game in the Play! emulator and compares them tick by tick
(`docs/issues/live-rig.md`, `tools/rig/`), and the playable Mac build is the same
emulator (`docs/play-online.md`). Nothing has been run in PCSX2 or on a PlayStation 2.
If you can run two copies of the game against each other in
PCSX2, you can settle questions that reading cannot. Patches go in `patches/` as PCSX2
`.pnach` files: one change per patch, a description of what it does and what it costs, and
whether you tested it. Report results in an issue with what you did, on which frame or
scene, and what each screen showed.

Use the [two-client validation protocol](docs/VALIDATION.md) to compare a repeatable
baseline with one patch at a time. A run without a reproduced baseline is inconclusive
about whether a fix works.

## Working together

- Open an issue before starting a big area so two people do not map the same code.
- Small pull requests are easier to check than big ones.
- Disagreements about a name are settled by evidence: point at the address.
