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
registers. Other counters remain unresolved: `fire4` recorded 36 unhandled GS-memory
transfers and 72 draws without a texture; `torment0` and `tormenta` recorded 261
and 219 such draws, compared with the hub run's total of 69. These totals include
boot and do not isolate the final frame's visual defect.

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

This uses the existing native rendezvous direct-launch integration: it prepares
frontend/launch globals and calls the existing player-select and game-launch paths.
Character-menu selection and subsequent play are controller-scripted; there are no
rig `poke`/`call` commands or level/stat/inventory fixtures in these trials.
It does not test the original online menu flow, internet connectivity, different
PCs, multiplayer mission transitions or long-session stability.

## Remaining qualification

A full good/evil campaign, all quests, difficulties, item combinations and every
skill rank have not been completed. Rendering captures establish only the scenes
actually observed; a destination request is not a normal mission transition.
Cross-machine/network multiplayer, local multi-controller play, device disconnects
during physical gameplay and hands-on audio/vibration quality remain separate work.
The existing Godot bridge has not been qualified by these standalone-native tests.
