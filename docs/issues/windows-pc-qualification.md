# Windows PC qualification and input fixes

Status: **Ran on a physical Windows x86-64 PC, 2026-10-21.** This is a bounded
qualification of the existing static recompilation, not a recovered original source
release or a completed campaign.

## Build identity

- Research/runtime base: `f3fe79166a5714b3b4c3d29c0209bf40b91194f5`.
- Input: US v2.00 `SLUS_209.73`, 5,777,312 bytes, SHA-256
  `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
- OS: Windows build 26200, x86-64; renderer: NVIDIA RTX 4080 SUPER,
  OpenGL 4.1, driver 616.56.
- Native compiler: LLVM-MinGW UCRT x86-64 release 20261006, clang 23.1.3.
- Existing 189-word fix set; no private sign-in patch. The stock Internet Game
  path therefore remains unavailable in this package.
- Baseline window executable SHA-256:
  `a460538b8a0463c4be76aea436a538c1c2fd9f779be207510f94d6561ed200e3`.
- Input-fixed window executable SHA-256:
  `ec4ad87a48651bca44fc70bfb545b198dd82901bb0aee736480869d4065e5256`.
- Subsequent diagnostic-only GS counter build, window executable SHA-256:
  `2533bca8ec77c73a4127c5edd2951246020f247a49ab2987035b621f05fb86f4`.
  This build repeats the full arithmetic/PNG/boot/62-input receipt below; earlier
  gameplay and network observations retain the input-fixed build identity above.
- Subsequent normal-finish tick-log correction, window executable SHA-256:
  `7ddfb8ec522741f9dc3b37e87912e3768c09659466e2ab2f39e76932b46ad3d0`.
  Its arithmetic/PNG/boot/62-input receipt also passes. The paired terminal-row
  trial is recorded separately below; earlier gameplay receipts retain their identities.
- Guarded uniform-palette build, window executable SHA-256:
  `830bd77800ad284e4c3244612f37deaf0d9fd82923cb9c6121355031ff8ad07c`.
  It repeats the full arithmetic/PNG/boot/62-input receipt and the matched affected-map
  smoke below. Other gameplay receipts retain their explicitly stated earlier builds.
- Generated game code, original data, executable binaries, saves, screenshots and
  raw logs remain private. Only authored changes and summarized receipts are contributed.

## Confirmed input defects and changes

**Ran:** while two keyboard aliases for one action are held, releasing either one
must leave the action held until the last key is released. The old shared bit mask
cleared it early. The window now records physical scan-code identities, including
the extended flag, and publishes their aggregate. Posted test keys use independent
virtual-key identities. This also handles the two Shift keys and a NumLock change
between press and release. Focus loss clears all held keys.

**Read and tested:** optional mouse side buttons were supported by the shared
controls code but their Windows messages were missing. Both XBUTTON messages now
reach that code with the existing button indices. The five mouse message mappings
have native regression coverage; a physical side-button session is still unverified.

**Read and tested:** Windows vibration requests were counted without reaching
XInput. The PS2 large amplitude now maps to the XInput left motor; the small motor
maps to on/off on the right. Successful values are cached. Focus loss, detach,
synthetic takeover and shutdown release outstanding commands; transient stop failures
are retried while polling. Synthetic pads cannot start physical motors.
The lifecycle checks use mocked XInput callbacks, so they do not establish how a
physical controller feels.

## Repeatable checks

Build with the existing installer from your own supported disc. Then, on Windows:

```powershell
python tools/recomp/app/win/tests/run.py --cxx C:/toolchains/bin/x86_64-w64-mingw32-clang++.exe
python tools/recomp/render/tests/run.py --cxx C:/toolchains/bin/x86_64-w64-mingw32-clang++.exe
python tools/recomp/app/win/qualify.py --disc C:/private/return-to-arms.iso
python -m unittest discover -s tools -p "test_*.py"
```

Both runners keep their default outputs under ignored `local/`; `--out` can select
a private directory outside the checkout. The executable identity is checked with
SHA-256 before the disc-based run. Hashes of all four programs and the boot rig
are recorded and checked again after execution. Raw output must remain local.

| Check | Recorded result |
|---|---|
| Native input state/message helper | 129 checks, zero failures |
| Native vibration lifecycle | 22 checks, zero failures; mocked output |
| Repository Python suite | 675 tests passed, including 14 rendezvous-driver contracts |
| Floating-point receipt | `2e77df4dc13ec9c5`, rounding toward zero |
| PNG decoder corpus | 961 files: 942 read, 19 refused; `b4ed3d8917871960` |
| Deterministic boot | 2,309 frames, 2,413 fields, 113,069,252 units; hub reached |
| VU0 boot receipt | 466,083 calls, 26,111,361 instructions |
| Rebuilt application's software inputs | 62 cases passed, held state and neutral release |
| Raw XInput conversion, separate production harness | 39 cases passed under FE_TOWARDZERO |
| GS transfer diagnostics and pending-upload order | 54 authored checks, zero failures |
| Uniform-palette load/alias/continuation behavior | 95 authored public-GIF checks, zero failures |
| OpenGL alpha/depth canary | 16 checks, zero failures; 1,024 pixels per colour/depth check |
| Counter-only renderer replay | 3,011 completed frames with identical draw/texture/resource checksums |
| Earlier visible baseline session | 461.219 seconds, 59.8 pictures/s at 1280x960, clean exit |
| Earlier visible sound-device session | WASAPI, 460.43 seconds taken, no request gaps above 30 ms |

The application input run sends messages through its compiled window handler and
uses the existing game-controller test adapter. It covers movement, all digital pad
buttons, full stick directions, aliases in both release orders, dead zones and
trigger-byte boundaries. The old binary failed the newly named alias cases and the
first-alias-release cases; the rebuilt binary passed. Native scan-code tests cover
the physical identity cases which posted messages do not exercise.

An XInput controller was detected, but the observation period contained no physical
button or axis movement. Hardware switches, physical vibration and audible quality
are not qualified by software injection or device counters. A script decimal
`0.30` rounds below the compiled `0.30f` threshold under FE_TOWARDZERO; raw trigger
bytes 76 (off) and 77 (on) mapped correctly. That script precision issue is separate
from hardware trigger conversion.

## Gameplay evidence and setup boundaries

**Ran, no gameplay memory writes or direct function calls:** normal character
creation, walking to Firiona, dialogue unlocking the first mission, walking to the
portal, accepting the mission menu, entering `blood1`, checkpoint save, pause-menu
reload, enemy damage, death and checkpoint restart. Recall used the starting item
stack (2 to 1), returned to the hub and resumed the mission through ordinary inputs.
The earlier locked-portal probe skipped the dialogue prerequisite; it did not identify
a runtime defect.

**Ran, no gameplay memory writes or direct function calls:** an aimed offensive
spell in that normal first-mission route reduced a kobold from 28.7678 HP to death
and awarded 67 XP. The matched no-cast route left the target at 28.7678 HP with zero
XP and the hero died. This verifies an actual offensive outcome, rather than only
a casting animation.

**Ran on the input-fixed native executable, seven paired classes:** Barbarian,
Cleric, Shadowknight, Ranger, Wizard, Berserker and Shaman each killed an initial
kobold and earned 67 XP from a normal level-one character. Cleric used starting
Holy Strike, Wizard Shock of Frost and Shaman Poison Bolt; the other four used
starting weapons, including the Ranger bow. Each matched no-attack control earned
zero XP and left its target alive. Each pair's pre-combat 32 MiB snapshot matched
byte for byte. All seven attacking characters stayed above zero HP throughout the
combat segment, including a minimum of 1.748 HP for the Ranger.

These runs initialized blank cards, used ordinary creation/dialogue/portal/checkpoint
and load menus, then used starting health/mana potions through normal controls.
They pinned the CPU-counter reads at `0x3229f0` and `0x322a00` to repeat the initial
random seed; they did not write health, mana, position, XP, levels, point pools,
skill ranks, enemy HP or inventory. This is headless automated combat evidence,
not physical controller or rendered/audio proof. Each character remained level one;
the later earned-level follow-up is recorded separately below. Mission completion remains unqualified.

**Ran a normal earned-XP persistence follow-up:** a Cleric killed the initial
kobold, earned 67 XP, saved at the checkpoint, confirmed overwrite with Square and
loaded that save. Three fresh corrected trials wrote the same 310,392-byte save;
XP remained 67 and the defeated enemy remained dead. Two independent continuations
also recalled to the hub and returned to `blood1`, retaining 67 XP and ending alive
at 20.9424 and 20.9039 HP. No XP, health, inventory or position writes were used.

A later natural Cleric continuation reached 268 XP after four total kobold kills.
It recalled to the hub, saved through the normal checkpoint/overwrite UI and loaded
in a separate process. Both the loaded hub and resumed `blood1` snapshots retain
268 XP, a valid live Player and 34 HP / 31.5 mana. This remains level-one progress;
it does not establish a completed mission or a fully earned first level.

Further normal combat on the preserved input-fixed native build reached eleven
kobold kills and 737 XP. A real chest and nearby drop raised the remaining gold
from 72 to 251; ordinary regeneration restored 34 HP / 31.5 mana. Square confirmed
an occupied-slot overwrite, positive card-write and transfer gates completed, and
normal pause-menu Load restored 737 XP, 251 gold and a live Player with full health
and mana. The saved file is 310,392 bytes. This later receipt tests save/Load within
one process; it does not extend the separate-process claim above to 737 XP.
At that checkpoint the character was level one; the first mission remains in progress.

A further natural continuation kills a stronger enemy for 339 XP, saves/loads 1,076 XP,
then earns another 67 XP to cross the 1,100-XP first-level threshold. At 1,143 XP the
Cleric reaches level two and receives three stat points plus one skill point. Actual
menu inputs spend them on Strength 46 to 49 and Holy Strike rank one to two. No
health, mana, XP, level, point or rank writes are used; the declared initialization
counter inputs remain the only fixture.

Normal pause-menu Exit Mission, with Left/Cross choosing Yes, returns the live
character to the hub. The automatically opened mission menu is closed with Circle
before walking to its Savepoint. An actual 310,392-byte write, transaction-gated
pause-menu Load, and a separate fresh-process frontend Load preserve 1,143 XP,
level/acknowledged level two, Strength 49, Holy Strike rank two, zero unspent points,
258 gold, 46 HP and 36.6 mana, with a live Player. This is on the preserved input-fixed
native executable (`27869a855f1d83c64d085443d181f39c3b8f9b640291411a3e72b38106b40cea`).
The accepted routes observe no valid live-player death frames. Rejected retreat
and menu-input attempts remain excluded; the first quest and good exit to `strife`
are still unfinished.

Earlier overwrite attempts pressed Cross while the overwrite screen required Square;
they wrote no new checkpoint and correctly loaded the older zero-XP save. This was
a test-input error, not an established persistence defect. Load readiness now witnesses
the actual card-transfer busy-to-idle transaction, idle card state and a valid live
player before issuing further controls. Pause clearing alone occurs before the new
player exists and is insufficient for this same-level load.

**Ran in the actual rendered application on the diagnostic build:** a normal
Shaman followed the dialogue/portal route, saved, loaded and killed the initial
kobold with the starting spell. Its HP changed from 28.7678 to -2.2322, XP reached
67, and the hero finished at 29.8317 HP with a combat minimum of 24.1691. The route
used the same declared initialization-counter fixture and ordinary inputs. Fresh
save/load transaction gates replaced fixed post-menu waits in the private test;
the earlier fixed waits could leave the character exposed after the menu closed.
No runtime timing fix or gameplay memory write was needed.

A matched music-volume-zero run also passed. Each game-mixer capture contains
4,985,780 stereo 16-bit frames at 48 kHz (103.8704 seconds). Watched HP, XP and mana
match throughout the 362-frame combat segment, and both targets have the same death
outcome. The music flag changes the PCM while other mixed output remains nonzero.
Both recordings report zero samples at full scale; that counter does not establish
audible quality, correct mixing or console fidelity. These WAVs are taken before
the physical output device and remain private.

**Ran with explicitly prepared level 25, pending-level state and points:** all seven classes spent points in the
actual skill menus; each learned an active skill through the menu. No skill-rank or
binding writes were used. A prepared low-health cleric's learned healing spell
increased HP from 10 to 111.28 while consuming mana; its no-cast control reached
14.39 HP through ordinary regeneration.

**Ran with other labeled fixtures:** inventory unequip/re-equip, health and mana
consumables, stat allocation and shop buying/selling. Earlier outgoing melee and
poison-target comparisons used prepared health, invulnerability or mana reserves.
An original-health enemy kill using invulnerability and a mana reserve also earned
the real level-up points: the UI spent all three stat points and one skill point
without writing XP, levels, points or ranks. Those combat fixtures do not establish
normal combat balance or campaign progression. The no-write first-mission
continuation separately killed a second enemy (134 total XP), picked up container
gold (500 to 504, versus 500 in a no-melee control) and unequipped/re-equipped the
original weapon through the inventory menu.

## Rendering and network boundaries

**Ran on the baseline application:** 111 fresh-boot destination requests reached
their end marker and produced decodable 960x720 captures. This is an asset/capture
sweep, not 111 completed missions. The audit found 108 distinct pixel images.
Four names share identical world/object payloads, explaining that duplicate group.

All sweep runs reported zero unimplemented VU1 instructions and zero unknown GS
registers. The original `fire4` sweep reported 36 unsupported GS-memory transfers.
A later recording reproduces 36 in the same-length segment and 63 over the longer
capture; every event has zero width and height. Empty rectangles move no pixels,
consistent with the bounded pixel loops in the [pinned PCSX2 implementation](https://github.com/PCSX2/pcsx2/blob/5b6e6e23eba403b589495c1abf8266eb1309a5b1/pcsx2/GS/GSState.cpp#L3057).
The correction changes only the unsupported-transfer counter guard. It preserves
all original upload flushes and command order; a pending-upload fixture specifically
protects that ordering. Nonempty unsupported transfers are still counted.

The 54 authored GIF-packet checks pass. CPU replay of the same private recording
leaves all 3,011 completed frame checksums identical, including vertices/fog, complete
draw commands, uploaded RGBA, target lifecycle and display rectangle/aspect. Nonempty
copy commands stay at 4,537 while skipped transfers change from 63 to zero. An actual
rebuilt-app `fire4` smoke also completes: 4,843 surface copies, zero skipped transfers,
zero unimplemented VU1 instructions/unknown registers, and an inspected 960x720 image.
This is a diagnostic correction, not a heat-haze or console-image fidelity fix.

General retained-texture fidelity remains open: the original `fire4`, `torment0` and
`tormenta` runs reported 72, 261 and 219 draws without a texture, respectively, against
69 accumulated during boot. The new trace isolates Torment's settled issue to 1x1
indexed strips with a palette upload but no uploaded image at the sampled address.
The current renderer does not retain general GS video memory across image sets.
A guarded constant-texture correction now handles the supported uniform-palette
case below. These state counters are not missing-pixel counts.

An independent reference now interprets the private native-produced GIF/MMIO history
with PCSX2 GS software renderer commit `5b6e6e23eba403b589495c1abf8266eb1309a5b1`.
It replays 4,220,552 events across 3,011 fields. Authored fragmented-upload,
local-copy, CSM1/CLD2, software-draw and freeze/load controls pass. Read-only probes
are built outside the unmodified vendor checkout; their final 4 MiB GS-memory hash
matches the uninstrumented replay.

For all 297 actual 1x1 Torment draw attempts, the active 256-entry palette is
uniform RGBA `0x8000ffff`. Texture alpha is 128; HIGHLIGHT2 with TCC enabled uses
that alpha. TEST enables LESS 127 with KEEP on failure, so the reference rejects
both colour and depth writes before queueing. Larger-texture draws at the same
addresses provide a positive queue control. The baseline native missing-image path
disables texturing and tests vertex alpha 0, allowing these draws through.
These are draw-state observations, rather than missing-pixel counts.

The reference consumes native-produced packets, so it independently checks their
GS interpretation, not the game's EE/VIF/VU execution or the original PS2 display.
Normal GS display presentation and cache aging are not exercised. This establishes
a specific alpha rejection defect; it does not establish complete scene fidelity or
general retained-VRAM support. The portable reference, original-data intermediate,
probe output and screenshots remain local.

The decoder now resolves a completely absent 1x1 PSMT8 image when every one of its
256 palette entries is the same colour. It requires one complete 16x16 CT32/BW1
palette upload, CSM1/CSA0/CPSM32, and an actual supported CLD2 TEX0 write tied to
that upload serial. Unknown image indices are irrelevant in this uniform case.
Overlapping uploads, local copies and possible colour/depth writes revoke eligibility;
ambiguous formats/strides/wrapping fail closed. Both TEX2 contexts and unrelated
TEX0 loads discard the load proof. Same-value reload and XYZ-only draw continuation
fixtures protect cache/load ordering. Other missing/incomplete cases keep their
existing behavior; general retained-VRAM support is not implemented.

Both public fixtures pass against the integrated source: 54 existing transfer checks
and 95 new GIF-interface checks. The baseline fails 25 of the new checks. A private
production-OpenGL canary passes all 16 checks, versus six baseline failures: alpha
127/128 fails LESS 127 without colour or depth writes, while alpha 126 and TCC-off
controls still draw. Each colour/depth check reads all 1,024 pixels of its target.

CPU replay of the same 4,220,552 raw events across 3,011 completed fields reduces
missing states from 666 to 72 and adds exactly two constant textures; nonempty copies
remain 4,537. After normalizing the expected material/UV changes, normal texture IDs
by content, and excluding the two added constant resource lifecycles, every remaining
modeled frame digest matches. Raw field numbers are compared; pending unfinished EOF
work is excluded. This is a modeled GS regression receipt, not original-scene pixel proof.

The rebuilt application also completes the matched `fire4`/`torment0`/`tormenta`
smoke with fresh test data: missing-texture states 660 to 72, copies unchanged at
4,537, and zero unsupported transfers, unknown GS registers or unimplemented VU1
instructions. Both runs keep 2,899 frames / 3,012 fields / 143,983,790 units. All
three inspected 960x720 capture files are byte-identical. The alpha/depth correction
is demonstrated by the authored GPU canary; broader scene fidelity and performance
remain unqualified. These destination requests are separate from normal campaign play.

Inspected captures show textured hub, ice, fire and stone-platform scenes. Forced
offline entry into three PvP arenas instead leaves the player at Z=-100000; longer
waits and alternate views do not repair that setup. `nitdung3` shows only a small
geometry corner and needs normal-entry/spawn/camera investigation. These scenes
are not visual passes, and no fidelity comparison against a console reference was made.

**Ran on the input-fixed application:** 1280x720 and 2560x1440 with 4x MSAA,
1720x720 with a 21:9 aspect and 2x MSAA, and the 960x720 plain mode completed
captures at the requested sizes. All five camera modes produced distinct captures;
the 1440p overhead and first-person hub captures were visually inspected.
These are configured-render checks, not frame-rate benchmarks.

**Ran functional controls on all five modes in the diagnostic build:** overhead,
action, chase, shoulder and first-person each pass 14 checks (70 total). Posted
keyboard movement and release, synthetic-pad movement, camera yaw/pitch or zoom,
controls-API mouse look, attack routing and actual block-to-idle state transitions
were observed in a normally created hub character with no setup writes.

Three further chase/shoulder/first-person runs pass 27 checks. An 88-degree look
turn occurs without walking; after another mouse turn, forward input travels
45.7-46.5 units in the new look direction (normalized direction alignment 0.995-1.000),
then stops with zero measured release drift. Shoulder and first-person modes align
the character's facing to the look, while chase preserves idle facing. No health
was lost. Mouse checks enter through the controls API; keyboard messages enter the
compiled window handler. These are synthetic functional tests, and the empty-hub
attack observations establish routing/animation rather than enemy damage.



A 3840x2160 no-AA capture also completed and was inspected. Some hidden, unpaced
4K trials showed 5,405-5,675 MB working sets and 8-24 second long pictures, taking
31-59 seconds to finish. Later same-binary, same-path controls completed in 7-9
seconds at roughly 300 MB. Captures matched. A private GPU-completion candidate
was discarded because the controlled baseline did not reproduce the anomaly, so
no cause or performance fix is claimed. 4K gameplay performance remains unqualified.

**Ran on the input-fixed application:** two isolated local clients, fresh separate
cards, identical disc/build/settings, both players moving in the hub. Direct loopback
matched 878 confirmed frames; a forced local-relay trial matched 851. The repository
comparator found no shared-state differences. Both clients exited successfully,
with no out-of-sync or dropped-player flags observed, and all test processes stopped.
Service and carrier traffic were bound to 127.0.0.1.

The public `tools/recomp/net2/n2party.py` driver was then run on Windows for
both direct and forced-relay trials: each matched 878 confirmed frames and both
scripts completed with exit zero. Its new `--kind window --offscreen` path avoids
POSIX-only child-process options, binds the local carrier explicitly, and supports
Windows cleanup. Native/POSIX invocation remains the default.

Its receipt now rejects early exits, missing expected game logs, empty comparisons,
failed comparison processes and zero trial counts. An exception in external-service
mode is allowed to propagate rather than being suppressed by a return in `finally`.

```powershell
$env:RTA_DISC = "C:/private/return-to-arms.iso"
python -B tools/recomp/net2/n2party.py local/pc-direct --players 2 --kind window --offscreen --play 600 --limit 120
python -B tools/recomp/net2/n2party.py local/pc-relay --players 2 --kind window --offscreen --play 600 --limit 120 --relay force
```

Use fresh output directories for independent trials. Both commands own a temporary
loopback service and fresh individual cards, and do not contact public players.

**Ran a further natural two-player mission round trip:** both characters walked
from the hub spawn; ordinary dialogue unlocked the mission for both. The host's
portal interaction loaded `blood1` on both clients. A normal recall consumed the
host's starting stack from 2 to 1 and returned both players to the hub. The run
matched all 2,768 shared confirmed frames, including quest availability, positions,
HP, XP, seed/hash and recall stacks, with zero out-of-sync or dropped-player flags.
Both scripts completed, the driver exited zero and all owned test processes stopped.
The clients had fresh separate cards; this continuation used no gameplay memory
writes, direct calls, teleports or level/inventory fixtures. Body-collision-aware
walking paths and read-only frame/coordinate conditions drove ordinary pad inputs.
This trial establishes local mission entry and recall. Revival, mission completion,
disconnect/rejoin and cross-machine play remain unqualified; the later automatic
party-wipe recovery trial is recorded below.

**Ran natural co-op combat on the input-fixed build:** one kobold died, the two
player slots earned 37/55 XP, normal health/mana potions were consumed, and both
players survived. The original driver exited zero and both scripts completed.
All 3,477 shared confirmed frames and 20,648 valid kobold-HP observations match.
At the last shared tick the peers agree on player HP 31.4261 / 32.8, with no
desync or dropped-player flags. Later independent log tails are not compared as
if they were the same simulation tick.

**Observed kill and post-combat recall on the diagnostic build identified above:** both
players reached the hub alive and retained their exact per-slot 55/37 XP. At the
last shared tick (3,752), both peers agree on HP 32.8 / 12.7904, valid Player
vtables and live state. The original invocation remains a failed receipt (driver
and comparator exit 1): two extra actor-flag watches were incorrectly labeled as
shared even though ownership bit `0x200000` is machine-local, as documented by
[`Player_animStep`](../../symbols/player.tsv#L40).

A corrected offline comparison uses separate copies with only those two watch
headers labeled local; every row byte is unchanged. The public comparator then
exits zero over all 3,752 shared ticks. An independent audit confirms every other
actor-flag bit matches, as do 25,188 valid kobold-HP samples, class membership,
player HP/mana/XP, potion/recall stacks and the other shared fields. Both original
completion markers are present; individual child exit-code values were not
persisted and are not invented. This is observed gameplay plus corrected offline
evaluation, not a claim that the original driver invocation passed. A further
waypoint probe timed out before combat and remains excluded from successful runs.
No gameplay state writes were used in either combat route. Their scope excludes
automatic checkpoint recovery, tested separately below. Survivor revival, four
players, WAN and full mission completion remain unqualified.

**Ran owner-card persistence on the diagnostic build identified above:** two fresh,
distinctly named level-one characters each saved through the actual hub Savepoint
UI. The original driver and both recorded child exits are zero, both scripts
complete, and all 33 shared columns match across 1,274 confirmed ticks with zero
out-of-sync or dropped-player flags. Each owner's card transaction positively
observes busy/transfer state followed by clean idle. The screen-done pulse is not
claimed observed; it can be consumed before confirmed-frame sampling.

Each computer writes its own character into a separate 310,392-byte, one-player
save. In particular, the joining computer saves its slot-one character, rather
than the host's slot-zero character. Two fresh offline frontend Loads of copied
cards exit zero and preserve each owner's distinct name, class, level, XP, gold
and tested starting item stacks. Both characters are fresh level-one Shamans with
zero XP and 500 gold; this does not establish persistence of earned co-op combat
progress. The original cards remain unchanged during verification.

Network pause-menu Load is deliberately disabled by the existing game code.
These offline loads verify the owner-card files; shared party-wipe recovery and
Savepoint resurrection are separate tests. A first resurrection probe times out
on a movement waypoint; it remains excluded from successful revival coverage.

This uses the existing native rendezvous direct-launch integration: it prepares
frontend/launch globals and calls the existing player-select and game-launch paths.
Character-menu selection and subsequent play are controller-scripted; there are no
rig `poke`/`call` commands or level/stat/inventory fixtures in these trials.
It does not test the original online menu flow, internet connectivity, different
PCs or long-session stability.

**Ran automatic two-player checkpoint recovery on the normal-finish build:** both
fresh level-one Shamans walk to the actual `blood1` Savepoint, establish its in-RAM
checkpoint and die through normal enemy damage. The confirmed logs witness both
dead, null actors with the load flag set, and both recreated alive. The original
driver and actual child exits are zero; both scripts complete. All 39 tested shared
columns match over 4,326 confirmed ticks, with zero out-of-sync/dropped-player flags.

The restored interval spans ticks 3,896 through 4,326: 431 matching live rows with
network mode one and two active players. Ordinary host and joiner movement is held
across confirmed tick changes after restoration; by tick 3,936 they have moved
43.63 and 62.04 units respectively, with identical positions on both peers. Both
remain alive at the last shared tick, at 32.8 / 11.4289 HP and zero XP.

Raw actor flags also differ in two source-backed local bits: `0x200000` identifies
the local real player, and `0x100` is a hit flash transferred to its prediction copy
and cleared by drawing ([object flag research](../objects.md#gameobject-layout-0x4c-bytes)). Exact
supported-ELF instruction words independently verify that transfer and clear. A
separate audit excludes only those bits and finds every remaining flag bit equal;
the original single-bit audit remains preserved as false, with no row changes.

This qualifies automatic recovery from the in-RAM checkpoint and both players'
subsequent controls on two local clients. It does not test a memory-card Load,
earned co-op XP persistence, survivor-at-Savepoint resurrection, four players or WAN.
Earlier raw-field movement attempts could occur before confirmed simulation resumed;
those trials remain excluded from the bidirectional input result.

## Windows tick-log completion

A normal scripted quit could lose the buffered end of a Windows network tick log,
because the host terminates the process after flushing only standard output and
standard error. The driver now flushes its own tick stream through the existing
game-thread finish callback, then chains the prior handler once. Installation is
one-time and the callback tolerates reentry. No GUI-thread or fatal-exit path is
changed.

A matched two-client, fresh-card trial issues echo-only markers at ticks 607 and
613, then quits through the ordinary rig command. Both baseline clients print the
613 marker and exit zero, but their tick files stop at 604 complete rows with one
partial trailing row. Both rebuilt clients retain all 613 complete rows and a
terminal newline, with no partial rows. All 22 shared columns match over those
613 ticks, and net/online/application finish reports each appear once. Both actual
child exits and the strict driver exit are zero. Exact-helper native normal, null
and reentrant tests also pass; the Python suite remains 675/675.

This corrects evidence loss at normal completion. It does not itself establish
party-wipe recovery or a rendering/gameplay correction. Earlier local recovery
observations whose confirmed logs end before restoration remain incomplete.

## Remaining qualification

A full good/evil campaign, all quests, difficulties, item combinations and every
skill rank have not been completed. Rendering captures establish only the scenes
actually observed; a destination request is not a normal mission transition.
Cross-machine/network multiplayer, local multi-controller play, device disconnects
during physical gameplay and hands-on audio/vibration quality remain separate work.
The existing Godot bridge has not been qualified by these standalone-native tests.
