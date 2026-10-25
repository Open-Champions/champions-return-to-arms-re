# Direction

Where the Open Champions game work is going, and the rules every change follows. This file
is the same in both game repositories:
[champions-return-to-arms-re](https://github.com/Open-Champions/champions-return-to-arms-re/blob/main/docs/DIRECTION.md)
and [open-champions-godot](https://github.com/Open-Champions/open-champions-godot/blob/main/docs/DIRECTION.md).
Last changed 2026-10-25.

## One portal, two games

The player opens one program, the portal (friends, rooms, settings), and picks one of two games.

**Classic** is the original *Champions: Return to Arms*, kept faithful: the original look,
HUD, combat and camera. Only two things are added: the sharp art pack (the game's own
pictures enlarged) and a steady 60 frames a second.

**Remastered** is the combined version, built on the Godot rebuild:

- 60 frames a second or more at all times; on a high-refresh display up to 120, with the
  pictures between game ticks interpolated. A drop below 60 is a regression and is treated
  as a bug.
- a new HUD, new lighting and cleaner models;
- five views (overhead as in the original, plus closer and first-person views), and aiming
  where you look;
- **Hardcore** mode: Elden Ring-style combat (lock-on, dodge, stamina, poise) and weapons;
- boss music;
- the Elden Ring look, built on the player's machine from the player's **own** copy of
  Elden Ring.

A room is either Classic or Remastered. The two never mix in one room.

## Online play is exact

The game is a deterministic lockstep: every copy in a room runs the same ticks from the
same inputs. So:

- every gameplay change must be lockstep-safe;
- every gameplay change is a **room option** that all copies in the room agree on before
  the game starts, never a per-player setting;
- every gameplay change is tested in rooms of several copies (two, three and four where
  it matters), through a level change;
- with a mode switched off, the game must stay byte-identical to the original game.

Presentation (resolution, frame rate above 60, views that do not change the simulation,
the art pack, the Elden Ring look) may differ per player only where it cannot change a tick.

## Champions of Norrath later

*Champions of Norrath* joins later as more campaign content in the same portal. As with
Return to Arms, each player brings their own discs.

## Hard rules

- No game data, disc images, BIOS files, Elden Ring data or personal information in any
  repository: no executables, no extracted or converted assets, no translations of the
  game's code, no home paths, no names, no addresses of private machines.
- Everything taken from a game stays on the player's machine. Players bring their own
  copies of every game; the tools build what they need locally.
- What may be committed is described in each repository's CONTRIBUTING.md.

## How the two rebuild tracks relate

| | Playable line now | Long-term clean-code line |
|---|---|---|
| Repository | [champions-return-to-arms-re](https://github.com/Open-Champions/champions-return-to-arms-re) | [open-champions-godot](https://github.com/Open-Champions/open-champions-godot) |
| What it is | the game's own code translated to C++ on each player's machine (Classic), and the same game hosted inside Godot (Remastered), plus the research behind both | a hand-written C++ and Godot rebuild, function by function, checked against the original |
| Today | the game people play | portable libraries and test scenes, not yet a full game |

The hand-written rebuild aims at the same product: the same Classic and Remastered games
in the same portal, the same 60+ frames-a-second bar and the same lockstep rules (logical
60 Hz tick, room options, multi-copy room tests, mode-off identical to the original). When
it can play a mode as well as the translated line, it takes that mode over. Until then the
translated line is what ships, and research in either repository feeds both.
