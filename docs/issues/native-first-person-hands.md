# First-person hands: implementation and local validation

2026-10-14, branch `codex/first-person-hands`, based on `272dd42`. This follows
[the camera](native-first-person.md), [controls](native-first-person-controls.md)
and the comparison contract in [native-app sections 12/13](native-app.md).
All builds and private evidence are in this worktree, not the owner's checkout.

## Behaviour

`view.first.body = off|arms|full` is a saved camera setting. The default is `arms`.
At runtime, both hosts accept `app view set view.first.body arms` (or `off`, `full`).

* `off`: the previous behaviour, omitting the local player's draw packets.
* `arms`: draw the game's own animated player, equipment and cast effects; clip at
  least 14 units from the eye, scaled by character size. Omit upper central body
  meshes and appearance head parts from the host's DMA stream. A near plane alone
  was insufficient: the Iksar's face entered the picture during an attack.
* `full`: keep the whole model, using `view.first.near` (default 4). This deliberately
  exposes the face/body too; at the head-position camera they can obstruct the view.

The old `view.first.hide_player` remains accepted: yes means off, no means full;
the last setting applied wins. Invalid body values are rejected without changing
the current mode. Existing settings files with `hide_player=yes` must be changed
to `body=arms` to enable this feature.

There is no new art, animation, rig, weapon transform, spell origin or view-model
projection. The existing 70-degree first-person FOV is used. The original draw
function runs completely, including its pose-cache updates. The extra filter reads
the model's mesh table and cuts only the host stream, never the guest display list,
model hide masks or DMA accounting. References containing several meshes are split
at their original boundaries. Other players and world objects are not filtered.

OpenGL and Godot's scene tap consume this same stream. Godot uses the same near
plane for the complete triangles recovered by the tap. The character-card script
retains its last whole portrait while first person is shown, instead of recapturing
the partial figure. Existing strafe controls are unchanged.

## Builds and comparisons (ran)

Evidence root, abbreviated `W` below:

```
/Users/syndicatemike/Projects/champions-re-first-person-hands/local/first-person-hands
```

The executable and generated game inputs were read from the owner's checkout;
writeable generated/object/dependency directories were APFS-cloned into this
worktree. `python3 tools/doctor_home.py native godot` passed before builds. Final
`W/doctor-final.txt`: **0 would hang or fail**, three warnings (optional sign-in and
standard binary names; these builds have task-specific names).

Commands, from this worktree:

```sh
# build_app.py is a local runpy wrapper limiting the existing builder to 4 workers.
python3 local/first-person-hands/build_app.py --original --no-game --as rta_hands_final
python3 local/first-person-hands/build_app.py --no-game --as rta_hands_fixed_final
python3 tools/godot/build.py snapshot --refresh --jobs 4
python3 tools/godot/build.py lib --original --jobs 4
python3 tools/godot/build.py lib --jobs 4
python3 tools/godot/build.py project --jobs 4
python3 tools/godot/run.py import

python3 local/first-person-hands/check_rig.py rig-final-arms rta_hands_final first
python3 local/first-person-hands/check_godot_rig.py rig-godot-arms unused first
```

The local rig drivers run `tools/recomp/rigcompare.py boot-native --replay`, then
`boot-compare`, with a fresh card, the existing fight script, the original game's
translation, and `sound-clock=machine`. The Godot-library driver runs `rtag_host
--scene3d`, including list decoding and the scene tap. The reference rig log and
section 13 reports were copied read-only into `W`. No new emulator run is claimed.

| Check | Observed result |
| --- | --- |
| Old camera vs candidate, overhead | Entire native TSV identical; comparison identical to `reference-compare.txt` |
| First-person off, arms, full | Each comparison identical to `s13-first-compare.txt` |
| Arms before/after the head filter | Entire TSV identical, including pool and cosmetic columns |
| Final native arms vs Godot-library arms with scene tap | Entire TSV identical: **7,797 rows, all 27 columns** |
| Fight portion | **5,410 valor ticks** compared; simulation columns retain the section 13 result |
| Runtime switch off → arms → full → invalid | Near 4 → 14 → 4 → 4; invalid setting rejected (`modes.log`) |

Comparison report SHA-256:

* Overhead: `9cdc53c1d109539802956e6fe80aa948108adafe0526c97c625c6ef6900ff5c5`
* First person: `ba217b43a298213dfee390312d42a49965e08c09c6b3e1f8b24ab0f4e9410deb`
* Arms native/library TSV: `a0a47219cac60657f1db9e5b23a2687a2afe834dd39c91c4c7b7557bd7ceea40`

These are byte-identical **reports**, not a claim of identical whole RAM across
camera modes. As in sections 12/13, the reports contain known timing, front-end pad,
pool and cosmetic differences from the emulator. Changing off to arms changes the
pool checksum at 2,603 rows (draw-pose cache); all other logged columns are identical
between those runs. The additional mesh filter changes none of the logged bytes.
`boot-compare` returns 1 for the existing differences, so report `cmp` is the gate.

## Pictures (ran and inspected)

All pictures are private, 960×540, in `W`. Their names identify the script's requested
simulation tick; host logs also record the delivered frame. The sequences use fresh
cards, fixed pad scripts, and the game's own attacks in the valor boar fight.
The inherited fight fixture raises health to keep the subject alive; it is not part
of this change. Rig comparison uses the same fixture on both sides.

| Action | Native picture | Godot scene picture | What I actually saw |
| --- | --- | --- | --- |
| Iksar swing, tick 2410 | `swing-2410.png` | `godot-final/swing/tick-2410.png` | Green hand and wooden club rise from the bottom; the club blends into dark tree branches in OpenGL. Adjacent ticks show it moving out of view. |
| Bow draw, tick 2414 | `bowdraw-2414.png` | `godot-final/bowdraw/tick-2414.png` | Hand gripping the bow diagonally across the lower/right picture; bow/string extend beyond the frame, with a boar immediately below. State 0 and weapon class 4, the documented bow-draw state. |
| Spell cast, tick 2410 | `spell-2410.png` | `godot-final/spell/tick-2410.png` | Hand/staff at bottom right and the game's blue-white cast particles in front, beside a purple/frozen-looking boar. OpenGL's particles are much brighter than Godot's. |

`swing.rig`, `bowdraw.rig`, `spell.rig`, their logs and the full adjacent-tick
sequences are retained in `W`. Native swing uses the original translation with
`view.first.follow=1`; bow and spell use the existing patched strafe build. Native
captures ran on the v2 binaries; final binaries differ only by explicit standard
header includes and comments. Final native arms was replayed again and its whole
TSV matches v2. Godot libraries were also rebuilt from the final source.

Example native capture (use a fresh data directory on each rerun):

```sh
RTA_DISC="$HOME/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso" \
local/recomp-out/bin/rta_hands_fixed_final --offscreen --unpaced --no-settings \
  --size 960x540 --aspect 16:9 --view first \
  --data local/first-person-hands/new-bow-data \
  --script local/first-person-hands/bowdraw.rig
```

Godot captures used `W/run_godot.py` and the private `godot-capture-project` copy
in **scene** mode. Its local extension skips geometry submission before a player
exists / tick 2250, retaining texture updates; from 2250 onward it executes the
unchanged production scene renderer. This avoids costly intro geometry during QA.
The capture-only guard is not shipped. `build_capture_extension.py` preserves its
exact source/build procedure. Each final action has a separate data directory,
`run.log`, `capture.rig` and `figures.txt` under `godot-final/`. Swing/spell each
rendered 196 full scene lists with no missing camera; bowdraw rendered 198.
These figures are capture evidence, not a performance benchmark.

## Limits

Observed: the sampled arms-mode frames have no own face crossing the camera.
Hands can leave the picture during the original animation; nearby enemies can
occlude them. This is the requested clipped-original-body route, not a separately
composed FPS rig with a permanently visible weapon. Looking down can reveal the
lower body. Full mode can show the inside of the head by design.

The head classification uses rest-space upper-central mesh bounds, plus the
appearance head models. That classification is inferred from the original model
layout and checked on these Iksar, bow and caster sequences; every race, helmet,
transformation and animation has not been tested. No all-equipment guarantee is
claimed. The existing fixed head-height camera remains unchanged.

Terrain gaps remain visible in this fight, also in the body-off control capture.
Godot and OpenGL retain their existing lighting, transparency and particle-brightness
differences. A complete character-card refresh cycle, live controller feel,
Windows and multiplayer were not exercised by this presentation change. No public
server was contacted; nothing was pushed or published.

## 2026-10-17: worn armour, every character, the double buffer

Evidence root `local/fp-ready/` (pictures, rigs, logs; nothing of it is tracked).

### What was wrong (Ran)

* **Worn parts were never filtered.** The arms filter knew the body model (+0x544) and the two
  appearance head parts (+0x548, +0x54c). A character's armour is drawn as separate part models
  (`Player_drawEquipped`): torso plate, skirt, leggings, held weapon. Their meshes went through
  whole. A dump of the own figure's references (`--opt view-body-dump=N`) shows, per character,
  body + head + 3 to 4 worn parts + the weapon on an attach slot.
* **Dropping a mesh's packets broke later models and the level.** Each mesh packet ends with
  `MSCAL`, and each `MSCAL` swaps VU1's double buffer. If an odd number of packets is cut, every
  later packet is unpacked into the wrong half. With the Wood Elf Ranger the whole level then
  rendered magenta (yellow when only parts were cut) and the figure and the boar went missing
  (`a-c4/`, first run; `t1-c4/` against `t2-c4/`, `t3-c4/`). Head meshes alone had an even count
  by luck.
* **The "shoulder piece" in the bow-draw and spell pictures was the boar.** It is the same with
  `view.first.body=off` (`o-c4/attack-2415.png`, `o-c8/idle-2480.png`: the purple, frozen boar).
  The ground gaps around it were real; see the world document, section 8.

### What it does now (`app/fpview.cpp`)

* The host stream of the own player's `Player_draw` is checked **per model reference**. Each
  referenced address is traced to its model (the header whose mesh table holds it, found
  16 bytes at a time up to 1 MB back, cached by address). Each mesh's rest-space box comes
  from its record. A part on an attach slot (+0x13) is moved to that slot's origin in the
  body's attach table; a part with no slot is skinned on the body's joints and used as it is.
* **Kept:** body or skinned-part meshes that reach out to the side (at least 0.22 of the
  figure's height) with their middle between 0.30 and 0.62 of it: forearms, hands, gloves.
  Parts on a slot are kept unless they sit above 0.62 and not far forward. That keeps
  weapons, bows and shields and drops helmets. **Left out:** everything else, including the
  head, neck, shoulders, upper arms, chest, torso armour, belt, skirt, legs and feet. A
  look down shows hands and weapon, not legs.
* A left-out mesh is **still sent**, so every packet runs the vertex program and the double
  buffer stays in step. Only the vertex register of its strips' GIF tags changes, from
  XYZF2/XYZ2 to XYZF3/XYZ3 (a vertex with no drawing kick). Neither the OpenGL GS model nor the
  scene tap gets a triangle from it; the tap rejects such a strip by its count check. If a
  VIF code is not understood, the mesh is drawn as it is.
* Effects, other creatures and objects are not touched. A model that cannot be traced is
  drawn.

### Checked (Ran)

Six characters from the character screen (0, 2, 4, 6, 8, 10 presses right: Iksar Shaman,
Barbarian Warrior, Wood Elf Ranger, High Elf Cleric, Erudite Wizard, Dark Elf Shadow Knight). All
used the same route to the valor boar (`mkrig.py`): melee (cross held), cast (circle), idle,
run, look down 55 degrees, attack while looking down. That is 43 pictures each.

| | Before (`rta_app`) | After (`rta_app_next`) |
| --- | --- | --- |
| Sheet, six characters × seven moments | (b-c4, b-c8) | `local/fp-ready/final-hands.png` |
| Ranger bow draw | `b-c4/attack-2415.png` | `f-c4/attack-2415.png` |
| Wizard cast / idle | `b-c8/cast-2455.png`, `b-c8/idle-2480.png` | `f-c8/cast-2455.png`, `f-c8/idle-2480.png` |
| Look down (legs, kilt) | `b-c8/down-2537.png` | `f-c8/down-2537.png` |
| Godot scene mode, Ranger | - | `g-c4/` (the hands work's capture project with this library: same as OpenGL, hand and bow only) |

Simulation: `local/fp-ready/rig/check_rig.py` (the hands work's driver) on
`rta_orig_fpnext`. The first-person comparison report is byte-identical to section 13's
(SHA-256 `ba217b43…0deb`, as above), and the overhead report to the reference
(`9cdc53c1…c5ff5c5`). Against the hands work's final arms TSV, every column is identical except
`pool` in 1,465 rows. The cause is one word in the object pool (0x6c89d4, a pointer into the
render lists) that follows what was drawn. With `--opt view-collide=off` the whole TSV is
identical: it comes from the eye being kept out of walls (world document section 8), not from
the mesh filter. It is the same presentation-cache kind as the 2,603 rows of off → arms above.

Limits: the 0.22/0.30/0.62 figures were chosen on these six figures and their default
equipment. Other armour sets and transformations were not seen. Hands can still leave the
picture in the game's own animation.
