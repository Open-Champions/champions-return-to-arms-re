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
- Historic-display extent build, window executable SHA-256:
  `5223bc3dbd42ad5b9e8f208a3bf5adc960350b7046b55d80f4df593c514afcd3`.
  Its full arithmetic/PNG/boot/62-input receipt and matched three-scene diagnostic
  smoke pass. Earlier gameplay and multiplayer receipts retain their build identities.
- Subsequent sample-lifecycle/depth-preservation build, window executable SHA-256:
  `d7c2258b9fa65ea1dd5616b0d64e29e8491aef7e567ecab3431f3cb97b07eb93`.
  It repeats arithmetic/PNG/boot/62-input qualification. Authored mode-transition
  checks pass; strict selected-image equality remains false as documented below.
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
python tools/recomp/render/tests/run_gl.py --cxx C:/toolchains/bin/x86_64-w64-mingw32-clang++.exe
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
| Historic-display extent/stride transitions | 33 authored public-interface checks, zero failures |
| OpenGL historic-extent canary | 31 core checks, zero failures; repeat-edge fidelity remains open |
| OpenGL requested-sample/color/depth reuse | 157 checks per mode, zero failures in normal and simulated sample-rounding modes |
| Counter-only renderer replay | 3,011 completed frames with identical draw/texture/resource checksums |
| Earlier visible baseline session | 461.219 seconds, 59.8 pictures/s at 1280x960, clean exit |
| Earlier visible sound-device session | WASAPI, 460.43 seconds taken, no request gaps above 30 ms |

The application input run sends messages through its compiled window handler and
uses the existing game-controller test adapter. It covers movement, all digital pad
buttons, full stick directions, aliases in both release orders, dead zones and
trigger-byte boundaries. The old binary failed the newly named alias cases and the
first-alias-release cases; the rebuilt binary passed. Native scan-code tests cover
the physical identity cases which posted messages do not exercise.

During the earlier software-qualification observation, an XInput controller was
detected but no physical button or axis movement was recorded. Hardware switches, physical vibration and audible quality
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

A later continuation on that same native build isolates a stronger guard and kills
it with four aimed Holy Strike rank-two casts and normal blocking/regeneration,
earning 1,271 XP. Normal loot adds two gold and raises the health-potion stack
from one to two. A real hub overwrite and Load, a separately bounded fresh-process
frontend Load, and clean mission reentry preserve level two, Strength 49, Holy
Strike two, zero unspent points, 52 gold and the new guard death. All five accepted
trials exit zero without timeouts or valid player-death rows. Three longer walking
probes time out after valid Load prefixes; their entire trials remain rejected.
The first mission is still unfinished.

A later continuation on the same input-fixed native build clears three enemies at
the next choke using ordinary melee and aimed Holy Strike two, adding 75 XP.
Another offscreen enemy dies for an additional 25 XP; its cause is not traced to
a player attack. Proximity to environmental fire is an inference. The resulting
1,371 XP, 54 gold, level-two allocations and remaining health potion survive normal
hub overwrite/Load, a fresh frontend Load and mission reentry, and another normal
save/Load at the existing first mission checkpoint. All four accepted trials exit
zero without timeouts or valid live-player death rows. This does not qualify the
next northern checkpoint or mission completion.

Three further northern-enemy kills add 75 XP, reaching 1,446 XP. Ordinary Exit
Mission and hub regeneration restore full 46 HP and 36.6 mana; a normal overwrite
and Load plus an independent frontend Load/mission reentry preserve that XP,
allocations and 54 gold. The last health potion was consumed normally. All three
accepted trials exit zero with no timeouts or valid player-death rows; 21 reported
dead targets retain their flags/positions on reentry. A separate probe died and
automatically restored the older checkpoint despite process exit zero, and remains
rejected. The next northern checkpoint and mission completion remained open at
that stage.

Two further ordinary Holy Strike kills add 50 XP, reaching 1,496 XP. Normal Square
loot adds one armor item, raising its bag count from three to four; no equipped
bonus is claimed. Ordinary walking reaches a new northern Savepoint. Its actual
card write, transaction-gated pause-menu Load and separate fresh-process frontend
Load preserve 1,496 XP, level two, Strength 49, Holy Strike two, zero unspent points,
54 gold and the new armor item. The fresh Load creates a live Player at the new
checkpoint with 24.5562 HP and 36.6 mana. The 310,392-byte card is distinct from
all preserved earlier checkpoint cards.

All nine accepted continuation trials exit zero without timeouts or valid
live-player death rows. Twenty-three reported defeated targets retain their
raw-verified death state and positions; this is not a completeness claim about the
entire object pool. The fresh-load endpoint is paused and bounded, with living
enemies nearby. Longer unpaused survival, the good exit to `strife`, completion of
the initial Plane of War level and the wider quest remain unqualified.

Three further ordinary kills add 75 XP, reaching 1,571 XP and 57 gold on the same
preserved native build. A same-Savepoint overwrite/Load and an independent frontend
Load preserve those values and all five occupied item records across all three
bags. All six accepted trials exit zero without timeouts or valid live-player
death rows. An independent raw-card audit verifies all 26 saved defeated Kobold
records against both Loads, including their saved positions and variants. The
fresh live Player has 9.2476 HP and 8.4048 mana; this is a low-health checkpoint,
with no consumables remaining, rather than a survival or mission-completion pass.

A separate ordinary Exit Mission, hub regeneration and free hub Recall route
restores full 46 HP / 36.6 mana while retaining 1,571 XP, 57 gold, the earned
allocations and every occupied 72-byte item record. All 5,898 valid live-player
rows stay alive and the process exits zero without timeouts or a card write.
Recall returns to its older stored position, not the northern Savepoint; that
location is verified against the actual returned actor. The original northern
card retains its low saved resources. The endpoint is immediately paused and
does not establish a new full-health card, an extended encounter or level completion.

A subsequent ordinary-control route retraces the cleared corridor after that
recovery and stops paused at 44.045 HP / 36.6 mana. All 9,855 logged frames are
complete, the process exits zero and no valid live-player death is observed.
Allocations, all occupied 72-byte item records and the 26 reported defeated Kobolds
remain unchanged. Ten approximately one-HP losses occur earlier in the corridor;
their attacker or environmental cause remains untraced.

On the same preserved native build, a guarded approach reaches a hostile WarWraith.
The paired damage and no-second-cast runs have byte-identical 32-MiB RAM snapshots
immediately before the compared cast. Holy Strike rank two removes exactly 48 HP
and costs exactly 10 mana relative to that control; the player's position and HP
match at the comparison endpoint. Both runs include the same earlier missed cast.
The original lead-shot invocation that timed out waiting for damage remains failed.
All four accepted approach/damage/control processes exit zero with no timeouts or
valid player-death rows, and the original checkpoint card remains unchanged.

A separate continuation uses one additional ordinary cast after that hit boundary.
The observed final hit removes 49 HP, sets the WarWraith's death flag/state and
awards 142 XP, reaching 1,713 XP. Its recorded last attacker resolves to the actual
Player. The process exits zero and pauses alive at 35.9834 HP / 8.1412 mana, with
57 gold and unchanged allocations, occupied item records and equipped definitions.
The player takes one HP loss during casting whose exact attack attribution remains
untraced. This kill trial writes no card; it does not establish saved-kill
persistence, a new level transition or completion of the wider quest.

A separate normal Savepoint overwrite and fresh-process frontend Load now qualify
that earned progress on the preserved native build. Both complete processes exit
zero without timeouts or valid player-death rows; 240 independent audit checks
pass. The game writes a complete 310,392-byte test save using the ordinary occupied-
slot Square confirmation. Fresh Load preserves 1,713 XP, 57 gold, level two, the
earned allocations, all occupied 72-byte bag records and all equipped definitions.
The fresh Player starts alive at the same northern checkpoint with 36.5461 HP and
8.7090 mana, including normal regeneration after loading.

The complete saved WarWraith records change from nine to eight: only the killed
actor is removed, while every survivor's class, position, angle, properties and
saved state remain unchanged. The primary save/recreation rules corroborate this
result; a pool count alone is not the proof. String offsets and alignment padding
are excluded from semantic record comparison. All 26 previously saved defeated
Kobolds remain verified. Earlier seed cards and the new immutable 1,713-XP seed
are preserved. This adds durable progress at the existing checkpoint, with the
initial mission and quest still open.

**Ran a fresh Load and short controls in the installed sample/depth application**
(`d7c2258b...`) using a private copy of that genuine 1,713-XP seed. The graphical
process exits zero without timeouts, and all 100 original automated checks plus
135 independent audit checks pass. Seven raw snapshots preserve XP, gold, class,
level, stats, all 32 skill-table entries, quest/decision flags, every occupied bag
record and all equipped definitions. Ordinary scripted controls move the player
15.3413 units, return to idle on release, enter block, return to idle again and
pause. All 177 valid Player rows remain alive. A 1.0969-HP loss during movement
has no traced attacker or environmental cause.

The 960-by-720 offscreen captures wait for all three present-color channels to
reach 128 and four further game frames. Viewed unpaused frames show lit textured
terrain, the character, Savepoint and readable level-two HUD; the pause menu is
also readable. This is bounded PC image inspection, without original-console
comparison, physical controls, sound or performance qualification. The original
first invocation is retained: its checker had six tuple-versus-list false
negatives, and its initial scene capture was still dark during the load fade.
The corrected second invocation waits for the observed fade state.

The source seed and all four game-save/icon files in each private app test card
remain byte-identical. Emulated game-card I/O reports zero bytes written during
these app Loads; normal host initialization separately adds four default
`BWNETCNF` network-configuration files to each private test card. No user card is
used. These app checks do not requalify every older headless combat/save route.

A further equipment test on the preserved headless native build equips the gloves
already earned in play through the normal inventory menu. Actual armor rises
from 27 to 40: the item has base armor five and a 175% armor bonus, contributing
13 after the game's integer calculation. All occupied 72-byte item records stay
unchanged; only equipped slot nine changes. The equip, normal Savepoint overwrite
and separate fresh frontend Load all exit zero without timeouts or valid player-
death rows; 343 independent audit checks pass. Fresh Load recomputes armor 40
while preserving 1,713 XP, 57 gold, stats and all 32 skill entries. The failed
first cursor attempt stops before confirmation and remains rejected. This proves
the equipment change and its persistence; reduced incoming damage and rendered
gloves appearance are separate tests.

A separate installed-application inventory inspection loads that equipped seed,
opens the armor page and selects the gloves. The viewed menu displays armor 13
and the normal Unequip action, with readable item art and character preview.
All 168 other original automated checks pass, but the original 169-check aggregate
remains false: its selected-item check incorrectly requires the menu pointer to
equal the canonical equipped pointer. The primary grid builder makes a local
72-byte item copy. Those two full records are byte-identical; a separate 229-check
audit verifies the intended selection, armor 40 and preserved character state.
The original checker/result remain unchanged. Three viewed 960x720 captures show
the settled scene, inventory and return to play; exact glove-mesh fidelity is not
established. A recorded HP decrease coincides with a last-source link to a Kobold,
without an exact damage-call or matched armor comparison.

**Ran further normal melee and durable progression on the preserved native build:**
a fresh attack edge after actual guard release enters melee. Two observed hits
remove 25 and 23 HP from the adjacent Kobold; its last attacker resolves to the
real Player, and death awards 25 XP, reaching 1,738. No hero HP decrease occurs in
this corrected fight. The fixed ten-pulse input budget continues after the kill,
including normal attack root motion, before a real paused endpoint at tick 278.
The earlier script's lone attack edge occurred during guard, then remained held
while walking; it times out without damage and has no paused tail. That failed
invocation is retained, rather than counted as a successful controls test.

Normal return to the existing Savepoint, occupied-slot overwrite and a separate
fresh frontend Load preserve 1,738 XP, 57 gold, armor 40, equipped gloves,
allocations and every occupied item record. The new 310,392-byte save equals the
entire saved RAM buffer. All 27 known saved defeated Kobolds match fresh typed
memory records at their saved positions, with matching negative HP/maxHP
fractions; this is not
a general active/free object census. Eight saved WarWraith records remain.
The fresh Player is alive with 39.6543 HP / 11.8455 mana near the same checkpoint.
The three accepted whole combat/save/fresh-Load processes exit zero without
timeouts or valid player deaths; a separate 303-check audit passes. Mission and
quest completion, full resource recovery and armor-related damage reduction remain
separate claims.

**Ran further natural combat, earned loot and durability on the preserved native build:**
six additional Kobolds raise the checkpoint from 1,738 to 1,888 XP. The final
survivor needs two short ordinary approach segments and a fresh melee press;
one observed 25-damage hit takes its remaining 1.7678 HP negative. Dead state 20
and the final 25 XP appear on the following tick. Earlier out-of-range attacks
and an overlong approach remain preserved, without being counted as successful
clears. A hero HP loss occurs in the accepted route; no armor comparison or
exact hit-source attribution is inferred.

Normal regeneration restores 46 HP and 36.6 mana in the cleared area. Ordinary
movement and Square pickup collect a real leggings drop, expanding the armor
bag from four to five records. Its canonical 72-byte record differs from the
world drop only at the declared signed 16-bit bag-index field; the other 70 bytes
match. All five previously occupied item records, equipment and allocations
remain unchanged. This pickup does not equip the leggings; armor stays 40.
The monster that originally spawned the drop is not traced.

A normal Savepoint overwrite writes the full 310,392-byte RAM save buffer, and a
separate fresh frontend Load preserves 1,888 XP, 68 gold, full resources, gloves,
leggings and the full skill table. All 33 known saved defeated Kobolds match the
fresh raw factory names, positions, variants and negative HP/maxHP fractions;
eight saved WarWraith records remain. This is a known-record check, without a
general active/free-object census. Six complete approach/combat/loot/save/Load
processes exit zero without timeouts or valid Player deaths, and a separate
454-check audit passes. The saved checkpoint remains in `blood1`; mission/quest
completion and the transition to `strife` remain open. This is preserved-native
evidence, separate from the installed application trials.

**Ran that melee route in the installed sample/depth application (`d7c2258b...`):**
all 196 original checks and 270 independent audit checks pass. The process exits
zero without timeouts; all 313 valid Player rows remain alive, at armor 40, with
a minimum 36.7069 HP. Ten fresh Cross presses produce the observed 25/23 damage;
target HP becomes negative at tick 79; dead state 20 and 1,738 XP appear
at tick 80. All 22 shared
logged fields match the native run literally over 1,618 rows: 35,596 formatted
values, zero differences. Twelve additional app rows are the declared paused tail.
This equality is bounded to those fields, rather than whole RAM or pixels.

Viewed unpaused captures show the settled encounter, a readable 25-damage number
and the final attack/corpse scene. All occupied items, equipment, full skill table,
allocations and 57 gold remain unchanged. The original four copied save/icon files
stay at 1,713 XP and emulated card writes stay zero; host initialization adds the
four declared private network-config files. This combat-only case is offscreen,
unpaced, AA4 and sound-disabled. Its lack of card writes is separate from the
installed persistence trials below; native durability retains its build identity.

**Ran ordinary save and a separate fresh Load in the installed application:**
the same melee/return route reaches the normal occupied-slot overwrite prompt.
All 337 original save checks and 306 independent audit checks pass. The actual
310,392-byte written card matches the entire saved RAM buffer and is byte-identical
to the separately qualified native 1,738-XP card. Only this private copied game
slot changes; its three other game files and all source seeds stay unchanged.
The four normal host network-config additions are recorded separately.

A separate fresh application process loads an installed-only copy of that card,
retaining 1,738 XP, 57 gold, armor 40, equipped gloves, allocations, all occupied
item records and the full skill table. It exits zero without timeouts or hero
HP losses. Its original aggregate remains false, with 180 of 185 checks passing:
five enemy checks compare saved factory names with a helper's vtable-catalogue
label. The actual raw object names remain exact, including the two tough Kobolds;
this is a checker namespace error, without a game type rename. A separate
439-check raw-memory/image review matches all 27 known saved defeated Kobolds by
exact factory name, position, variant and negative HP/maxHP fraction in each of
five snapshots. The original runner and false result remain unchanged.

Three viewed fresh-Load captures show the settled checkpoint, the equipped
13-armor gloves with Unequip action and return to play. The copied four game
save/icon files remain unchanged during Load; emulated card writes stay zero,
with host network-config creation recorded separately. These offscreen, unpaced,
sound-disabled AA4 cases qualify this checkpoint's persistence and UI behavior.
They do not establish physical input, audio, performance, exact glove-mesh or
original-console image fidelity, reduced incoming damage or quest completion.

**Ran the installed application through its normal visible, paced window path:**
a fresh copied 1,738-XP card loads through the frontend. Ordinary movement,
block/release, inventory and pause pass with no gameplay-state writes or RAM
snapshot loads. All 1,206 valid Player rows remain alive, with inventory,
allocations, 57 gold and armor 40 retained. The four copied game-save/icon files
stay unchanged and emulated card writes stay zero; four private startup network
configuration files are recorded separately.

The first resize trial's original aggregate remains false at 258 of 259 checks:
a deferred wide capture is followed immediately by a restore request and produces
960x540. Source review supports a capture/resize ordering explanation, but that
run lacks actual client measurements and does not qualify the width change.
A separate trial drains each capture before resizing again. All 303 original
checks and 319 independent audit checks pass. Verified owned-window measurements
at 96 DPI and the four viewed PNGs agree: 960x720, 1280x720 and restored 960x720.
The checkpoint, HUD and inventory are readable; a small black wedge at the wide
scene's lower-left edge remains an observation without reference-fidelity judgment.

The separate ten-second idle checkpoint interval reports 602 presents in
10,018 ms, 59.987 FPS, a longest interval of 16.6 ms and zero pacing restarts.
The earlier report printed by the reset includes boot stalls and is excluded
from that baseline. Peak observed working set is 285,704,192 bytes; peak sampled
private memory is 466,898,944 bytes. Active muted real-clock WASAPI renders
41.57 seconds, with no device-request gap above 30 ms. These are bounded readings
on this PC, without audible-quality, physical-feel, full-campaign, long-session,
4K-performance or original-console fidelity qualification.

A first installed 1,888-XP leggings equip/save attempt loads the new checkpoint
but searches only the armor grid's first row. The cursor reaches its right edge
while selecting the gloves, then the target-selection wait times out before any
equip Cross or save request. The actual child exits three; the whole 167-check
aggregate remains false. All 291 valid Player rows retain 46 HP and emulated
card writes stay zero. That rejected attempt makes no equipment/save claim.

A separate selection-only trial locates the extra leggings below the gloves,
at columns seven/eight and rows two through four. All 189 original checks and a
69-check raw/image review pass. The selected menu copy matches all 72 bytes of
the canonical earned item and displays Quilted Leggings, armor 18, required level
one and Equip. It changes no equipment or card data.

**Ran normal equipped-leggings save and a separate fresh Load in the installed app:**
one fresh Cross after the proven selection raises actual signed armor from 40
to 54. All 374 original checks and 438 independent whole-trial checks pass.
Only equipment slot 12 changes, from saved index 1002 to 1004; all six occupied
72-byte items, stats, allocations, full 32-entry skill table, 1,888 XP and 68 gold
remain unchanged. All 795 valid Player rows retain 46 HP. The actual Savepoint
occupied-slot overwrite writes 310,392 bytes, exactly matching the entire saved
RAM buffer. Source seeds stay unchanged; only this private copied slot changes.

A separate fresh application process loads that installed-only equipped card
with both initialization-counter overrides omitted. The normal virtual counter
reads are logged, without given-value reads. All 297 original and 324 independent
checks pass; all 604 valid Player rows retain 46 HP, armor 54, occupied items,
equipment, skills, allocations, XP and gold. Across ten save-trial and seven
fresh-Load snapshots, all 33 known saved defeated Kobolds match exact factory
names, positions, variants and negative HP/maxHP fractions; eight saved
WarWraith positions remain. Absolute recreated maxHP and object addresses need
not equal the earlier process. The fresh copy's four game-save/icon files stay
unchanged, with zero emulated card writes and four declared startup network
configuration additions.

Viewed fresh-Load images show the decorated new leggings covering the legs,
with the readable 18-armor/required-level-one/Unequip tooltip. Selected item/equipment records and the raw appearance state match in snapshots
bounding 180 ordinary paused menu frames. The earlier
immediate post-equip capture shows exposed thighs; raw source/cache review finds
an incomplete body hide mask and unpatched texture destination fields at that
observation. The later fresh Load is not a same-process delayed-equip experiment,
and the complete cause of the early frame remains unproven. These results qualify
this equipment/persistence route and the later viewed appearance, without exact
console-mesh fidelity, reduced incoming damage, physical feel, audible quality
or mission/quest completion.

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

A subsequent correction addresses the 69 boot-time missing states. A framebuffer
briefly named by DISPLAY remains in the display-history cache for 120 fields.
The baseline clamps it to 640x224 even after FRAME/scissor establish a 1280x448
offscreen surface, so the right-half texture alias at column 640 is rejected.
Fresh wider FRAME/transfer stride now overrides only the historic display clamp;
current display naming, actual narrow-stride reuse and film/field resizing keep
their previous behavior. A narrow scissor alone cannot erase an already proved
wider extent, and callers without fresh stride metadata preserve that proof.

The integrated decoder passes all 182 authored checks: 54 transfer, 95 palette and
33 extent checks. The extent baseline fails 11 of the new checks. A private
production-OpenGL fixture passes 31 core extent/clamp/current-display/film checks,
versus eight baseline failures. Eight additional repeat-wrap characterization
checks bring the internal total to 39; these characterize a known edge discrepancy
and must not be counted as correct-GS pixel assertions.

Independent pinned GS software rasterization of the authored repeat fixture finds
224 edge pixels whose channel classes differ: native repeat sampling puts green at
the left origin where the reference stays red. The clamp control's channel classes
match. The reference's 16-bit channel value 248 versus native 255 is a separate
quantization difference. No original-scene pixel equivalence is established, and
the UV/quantization issues remain open independently of the extent correction.

Full native replay with the original VIF metadata/RAM callbacks completes 3,011
fields and 165,474 records. Missing states fall from 72 to three, copies remain
4,537 and unsupported transfers/unimplemented VU instructions stay zero. Only
fields 56 through 124 change their modeled resources/vertices/commands; texture
digests match throughout and all modeled components match from field 125 onward.
This is a regression comparison of native execution, not independent VIF proof.

The rebuilt extent application repeats fresh matched diagnostic requests for
`fire4`, `torment0` and `tormenta`: missing states 72 to three, 4,537 copies,
zero unsupported transfers/unknown GS registers/unimplemented VU1 instructions,
and unchanged 2,899 frames / 3,012 fields / 143,983,790 units. With antialiasing
explicitly off, all three selected 960x720 PNGs are byte-identical. Default four-sample
captures differ in 145,510 / 63,980 / 72,220 pixels respectively; the original failed
equality receipt is retained. A separate 12-check authored probe queries actual
GL_SAMPLES at draws using the unchanged production backend: a 640-wide first
allocation followed by 1280-wide reuse keeps zero samples, while 1280-wide first
allocation gets the requested four. The early return for unchanged physical size
preserves those sample counts. The extent correction changes that initial allocation;
it does not repair the backend's general sample-allocation lifecycle. No-AA equality
and the driver probe explain the changed default captures without asserting original
console fidelity. Seven unsupported read-only information no-ops
were removed from both comparison scripts; destination writes are explicit test
setup rather than normal campaign transitions. The three remaining states belong
to one retained fire-scene texture case; general retained-VRAM support remains open.

A subsequent backend correction includes the requested sample mode in same-size
framebuffer reuse. A narrow-to-wide logical transition can now request multisampling
without requiring a physical resize; the reverse transition releases that mode.
The backend remembers the attempted request separately from its effective fallback,
so an unsupported multisampled allocation is not retried on every announcement.
Same-physical-size reallocations preserve color and depth before deleting the old
attachments. Existing physical-resize depth behavior is unchanged.

An initial private cache-only candidate passed color checks but lost retained
depth. It was rejected before installation. The final authored fixture detects
13 allocation failures on the original backend, four depth-occlusion failures on
that rejected candidate and zero failures on the corrected backend. Its 157 checks
cover requested-mode transitions, same-mode reuse, retained RGBA pixels, retained
depth occlusion, disabled AA and an injected unsupported-framebuffer fallback.
Color comparisons cover all 691,200 pixels of each physical target. The fixture
queries an independent same-format framebuffer for the driver's actual sample
count, respecting permitted upward rounding in
[OpenGL 4.1 section 4.4.2](https://registry.khronos.org/OpenGL/specs/gl/glspec41.core.pdf).
Both normal and simulated two-to-four rounding modes pass all 157 checks. The
rounding/fallback injections do not qualify a second physical driver or Qt/macOS.
The rebuilt application repeats the full arithmetic/PNG/boot/62-input receipt,
and the final repository Python suite passes all 675 tests.

Fresh baseline/candidate/baseline application smokes finish cleanly with unchanged
CPU receipts and three remaining missing states. Selected `fire4`/`torment0`/
`tormenta` comparisons differ in 1 / 55 / 0 pixels, at most two channel levels;
the two unchanged-baseline fire views also differ in two pixels. Strict image
equality remains false. A separate fixed-input replay brackets the corrected
backend with two runs of the exact same baseline executable. All 3,011 complete
decoded render-field records and all three normalized GL ledgers are byte-identical; each
ledger contains 6,875,434 records. This captures forwarded arguments, vertex and
texture payload hashes, resource identities and sample/target state. Yet the
unchanged baseline readbacks differ in 40 / 0 / 18 pixels, at most two channel
levels, with alpha unchanged. Small variation therefore occurs without the
candidate; its cause remains unattributed and is not relabeled harmless.

That fixed stream exercises no same-size requested-mode transition or depth blit;
the new path is qualified by the authored GPU fixture. Unqueried/default driver
and WGL state remain outside the ledger, and that replay does not poll GL errors
per field. These are bounded lifecycle/compatibility results, not original-console
pixel fidelity or a repair of the three retained-texture states. The failed
strict-equality receipts, rejected depth candidate and all baseline controls remain
preserved privately.

A separate current-source authored comparison confirms a rendered-16-bit colour
precision gap. At 64x64 logical/physical size, without AA, blending or dithering,
a nearest/clamp draw samples a flat-red rendered PSMCT16 surface into PSMCT32.
All 1,024 interior native pixels contain red 255, while independent pinned GS
software replay stores red 248. A rendered-PSMCT32 control matches at 255; a
packed-PSMCT16 host-upload control matches at 248. All native/reference processes
exit zero, the native checks report no GL error, and the production source hashes
remain unchanged. The exact comparison remains failed; no production correction
is applied. Correct rendered-format storage, blending, masks, dithering and
format/view changes require further qualification. This uses authored packets
and raw reference VRAM, without original game inputs, and does not establish the
visual extent of the issue across campaign scenes.

A private authored integer read/modify/write component then matches all 28,672
packed pixels against the same independent software reference across seven cases:
one opaque control and two, three or five overlapping sprites with repeated or
increasing red values. Each case uses one instanced draw at 64x64 without AA.
Six deliberately wrong controls retain eight-bit color through the batch and
pack only afterward; every one of their 24,576 pixels differs, while the opaque
control matches. The component packs after each ordered write instead. Its first
shader-version failure occurs before draws and remains preserved separately.

This is a component result on the tested NVIDIA driver, without production
integration. It covers positive FIX=64 blending and alpha 128, using one R32UI
texel per logical pixel. Full blend-selector coverage, masks, dithering, rejection,
depth, packed-word aliasing, format changes, MSAA/scaling, portability and
performance still need qualification. The production CT16 discrepancy above
remains unfixed.

A further private signed-rounding component compares 13 seeded red-channel
vectors and the seven unchanged positive regressions with the pinned software
reference. All 81,920 packed candidate pixels match across 20 cases. Nine ordinary
integer-division controls differ on 36,864 pixels; eleven controls match. One
observed boundary uses destination red 16, source red 15 and FIX 64: per-write
floor rounding stores red 8, while division toward zero stores red 16. Every
native/reference child exits zero and source/history pins stay unchanged. This
qualifies those arithmetic vectors, without general blend-selector, RGB/alpha,
mask, dithering or production-renderer qualification.

A further private full-RGB component exercises all 81 valid A/B/C/D blend-selector
combinations for each of six source/seed/FIX vectors, with two ordered overlapping
writes per cell. All 31,104 packed candidate pixels across 486 cells match the
independent software reference. An actual division-toward-zero control differs
in 11 cells / 704 pixels; its other 475 cells match. A separate 5,184-coordinate
ID calibration matches native output, raw reference VRAM and authored positions,
including page crossings; reference padding stays unchanged. All seven child
processes exit zero, and an independent raw/source/pin audit passes.

This extends arithmetic coverage to those RGB/alpha vectors and selector choices
on the tested NVIDIA driver. It does not qualify arbitrary inputs, masking,
dithering, tests/depth, texture functions, packed-byte aliasing, format changes,
MSAA/scaling, portability, performance or production integration. The original
production CT16 discrepancy remains unfixed.

An expanded private final-write component runs 156 dither, color-clamp, FBMSK and
FBA cells at one- and two-write boundaries. All seven children exit zero and setup
is valid, but the original strict comparison remains false: 1,366 packed pixels
differ. All differences occur in 16 opaque, dither-enabled D cells at each
boundary; the mask/FBA families and blended dither cells match. Calibration,
padding, unchanged scissored pixels and A1 checks pass.

An independent raw/source audit reproduces every difference. The pinned software
reference selects a solid-rectangle shortcut for those opaque sprites; its source
packs a constant color without DIMX, whereas its general scanline path applies
dithering. The recorded outputs match those source-path calculations. This is a
source-backed dispatch explanation without a per-call trace or a physical-PS2
fidelity decision. A separate executed alternative changes only the authored opaque D rectangles
to equivalent triangle pairs, preserving all state, seeds and native code. All
31,104 full candidate pixels and 19,968 case words now match the pinned software
reference. All 55 native raw outputs remain byte-identical to the first version;
all four mask/FBA reference VRAM dumps remain exact. Each D reference dump changes
only the original 683 differing halfwords. Eight actual controls separately
produce 2,367 / 1,738 / 1,776 / 2,526 / 922 / 844 / 8,384 / 768 mismatches.
Calibration, every dither phase, protected mask bits, FBA/A1, padding and scissored
seeds pass an independent raw audit. This is bounded alternative-primitive-path
component coverage. The original sprite discrepancy stays false, and neither
physical-PS2 sprite behavior nor production rendering is corrected by this test.
All candidate/reference inputs remain preserved, without vendor or production edits.

Private CPU prerequisites also retain 12 raw write registers and effective PRIM
per draw. Fourteen authored contract cases pass 82 checks. The baseline's 25
contract failures consist of eleven missing raw-boundary requirements and
fourteen checks for the proposed API's absence; this is not 25 rendered bugs.
Some conservative boundaries can already have equivalent or baked vertex data.
A further 48-case, 960-check matrix verifies the candidate's exported state and
vertex words across triangle lists/strips/fans, GIF paths 0 and 2, both
PRMODECONT choices and fast/slow decoding. All 24 equivalent fast/slow pairs match; private
counters confirm the fast route actually ran. Copies, synthetic commands,
primitive histories, the complete FrameList, GPU behavior and performance remain
unqualified by these CPU fixtures. All such candidates stay private; the installed
renderer and its CT16 precision discrepancy are unchanged.

A further private ordered-event observer qualifies 24 authored CPU cases with
706 owned events and 114 complete FrameList snapshot triples. Baseline slow,
candidate capture-off and candidate forced-slow outputs match every explicitly
serialized named field, including full vertex words, texture bytes/metadata,
target announcements and retirement lists. A corrected 724-check audit and a separate corrected
481-check root review pass. The original false evaluators remain preserved:
their expectations misread authored DIR ordering, TEXFLUSH count, a zero-area
transfer register and the constructor prefix's repeated PRMODECONT value.
Corrections run offline only, without changing source/input/runtime outputs.

This observes tested raw packets, original primitive queues, transfer fragments,
MMIO and separately tagged synthetic canvas/host-fill commands. It is not a
complete replay or a rendering correction. Host notes, direct public model/frame
mutation, optimized/VIF/VU/world history and additional transfer/primitive cases
remain unqualified. Attachment/lifetime proof covers the scoped fixture calls,
without universal mutation or thread-safety enforcement. The source and all
candidate/runtime evidence remain private; production is unchanged.

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

**Ran four separate local network clients on the guarded uniform-palette build:**
normal character selection and scripted hub play pass over direct loopback and a
forced loopback relay. Both strict drivers and all eight actual child exits are
zero; all scripts complete. All six peer comparisons match in each trial. The
four-way common intervals contain 1,355 direct ticks and 1,338 relay ticks across
43 shared columns; all four players move and remain alive, with zero out-of-sync
or dropped-player flags over those intervals.

Each client has three direct peer routes with zero relayed packets in the first
trial. In the second, every counted game packet uses the relay. One joining client
reports 18 carrier strays; their packet-level cause was not captured and remains
open. Shared simulation still matches. These are four independent local network
windows with the existing native launch adapter. Four-player missions, WAN and
single-window physical multi-controller play remain unqualified.

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
This trial establishes local mission entry and recall. It does not qualify revival,
mission completion, disconnect/rejoin or cross-machine play; later bounded local
checkpoint-recovery and survivor-revival trials are recorded below.

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
automatic checkpoint recovery, tested separately below. These combat routes do
not qualify survivor revival, four players, WAN or full mission completion; later
bounded local-client tests are recorded separately.

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

**Ran earned co-op owner persistence on the guarded uniform-palette build:** two
fresh, distinctly named Shamans use normal dialogue/portal entry, combat, recall
and serial hub Savepoint saves. The original driver and both actual child exits
are zero. All 47 shared columns match over 4,421 confirmed ticks, with no observed
death, automatic reload, out-of-sync or dropped-player flag. The players earn
55 and 37 XP; their valid-row health minima are 22.6647 and 27.1303.

Each local owner writes the correct separate 310,392-byte, one-player card after
positive busy/transfer and clean-idle gates. Two fresh offline frontend Loads exit
zero and preserve the distinct names, class six, level one, 55/37 XP and 500 gold.
Definition indices and quantities for every occupied item across all three bags
match between the final co-op records, each saved card and its fresh Load. This
includes used health/mana potions and the host's consumed recall. The source cards
remain byte-identical during verification. This establishes earned owner-card
persistence through separate offline Loads; online card rejoin is untested.

A separate normal-shop trial on that guarded-palette build opens and closes both
players' shop UI, confirms the Buy/Sell chooser and purchases two health potions.
The host's health-potion stack rises from two to four while gold falls 500 to 292
to 84: each purchase costs 208 gold, matching the inspected fixed-price item
definition. The
joiner's gold/items and both players' recall/mana stacks remain unchanged. All
1,951 confirmed ticks across 48 shared columns match, both children exit zero and
both players finish alive in the hub. Canonical item-definition/quantity snapshots
independently verify the purchases; earlier incorrect menu-input trials remain
failed and are not treated as shop defects.

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

Further survivor probes on the guarded-palette build observe actual Savepoint
resurrection on both peers: the dead player's countdown reaches zero, HP becomes
16.4 of 32.8, protection becomes 90, and the dead countdown resets to 240. The host
stays alive through that event and no load flag is set. This distinguishes the
event from automatic party-wipe recovery.

The original game's tick deliberately substitutes a zero pad while spawn
protection is nonzero ([pad-selection research](../spec/player-tick.md#2-which-pad-the-tick-reads-0x1a56400x1a5764));
24 exact supported-ELF instruction anchors independently verify this gate. Early
post-revival stick holds therefore do not establish a control defect. Later host
death prevents the strict usable-controls endpoint in those invocations; they
remain failed.

A later fresh guarded-palette trial passes actual survivor resurrection and both
players' subsequent controls. All 4,805 confirmed ticks across 55 shared columns
match, both children exit zero, and neither an all-dead event nor an automatic Load
occurs. The joiner returns at half HP, protection counts from 90 to zero, and
source-backed control gates clear before ordinary movement. The joiner and host
move 33.86 and 8.96 units. Only three further shared ticks follow the host's first
movement, so this establishes a bounded control response rather than a long soak.

A further independent trial extends revival through a normal recall and fresh hub
controls on the same guarded-palette executable. Both children exit zero and all
5,666 confirmed ticks across 59 shared columns match, with no out-of-sync or
dropped-player flags. The host remains alive while the joiner dies and revives at
16.4 of 32.8 HP; protection expires and both players move before recall. The host
uses normal guard and periodic potion-button attempts, with three actual health
consumptions from four to one. The game's ordinary health-plus-pending-heal gate
determines acceptance; no health/stat writes or invulnerability are used.

Normal recall consumes exactly one host recall, two to one. Raw canonical item
snapshots preserve the remaining health/mana stacks, per-player XP and gold across
the return. This fresh-character trial has zero XP in both slots and does not add
a new earned-XP claim. Actual hub rows span ticks 4,968 through 5,666: 699 matching
live rows, including 600 before fresh hub movement. Host and joiner then move
107.76 and 83.59 units and remain stationary for 20 further confirmed ticks after
release. Both finish alive at 27.7734 / 21.4099 HP, without party-wipe recovery or
automatic Load. The preceding completed tick-log row 4,967 still belongs to
`blood1` and is excluded from the hub count.

The same route also passes on the installed sample/depth build identified above
(`d7c2258b...`). The original driver and both actual child exits are zero. All 59
shared columns match over 5,452 confirmed ticks, with no out-of-sync, dropped-player,
automatic-Load or party-wipe event. The joiner revives at half HP at tick 4,520;
protection reaches zero at 4,610 and the source-backed control gates clear before
both players move. Two normal shop purchases again cost 208 gold each, raising
the host's health stack from two to four. This invocation consumes one health
potion, leaving three, and normal recall consumes one host recall, two to one.
Canonical occupied 72-byte item records, equipment bags, per-player XP and gold
are independently checked across 26 player-record snapshots. Both characters have
zero XP, so this adds no earned-XP persistence claim.

Actual hub rows span ticks 4,736 through 5,452: 717 matching live rows, excluding
the preceding completed row 4,735, which still belongs to `blood1`. Six hundred
actual hub rows precede fresh movement. Host and joiner move 143.76 and 102.97 units,
then remain stationary for 20 further confirmed ticks after release. They finish
alive at 32.8 / 21.5996 HP. This repeats the stated local route on the installed
build with separate fresh test data; it does not qualify WAN, physical controllers
or long-session stability.

An intervening longer trial timed out waiting for a healing condition that the
guarded host never needed. That whole invocation remains failed; it did not reach
recall. The accepted continuation uses event-gated death/revival and ordinary
periodic potion attempts without requiring unnecessary damage. These results
qualify the stated local two-client intervals; full campaign, WAN and long-session
stability remain open.

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

## Player-hosted multiplayer and couch-input qualification

The installed Windows build and the new discovery candidate have separate evidence. The installed application remains SHA-256 `d7c2258b9fa65ea1dd5616b0d64e29e8491aef7e567ecab3431f3cb97b07eb93`. The private discovery application is `e9010c9cf6090a7122ed6233cb526bba77703cad6766ea29d111c8559eabbf9e`, its native browser CLI is `d80e8afd965329b3aa94e2bb3aa6b5305717eef9f6963e9d7fa5a2fc7bab5e9e`, and the private directory/relay service is `2fa3decf3505fd1356ab821ead10337cf60efc671d6e5279e52d997c66326b39`. The discovery, launcher and controller changes are not installed or published here; their implementation remains private pending review and handoff to the native-client repository. This is a research and qualification update.

The latest installed-build network baseline passed an independent 184-check audit. Four separate game processes on one PC matched all 37 shared columns across 1,072 common confirmed ticks with direct loopback transport and 1,087 with forced local relay. Every pair also matched over its available common interval. Both strict drivers returned zero; their pinned completion contract requires all eight game children to finish successfully with exit zero. The per-child numeric exits were not separately serialized in this baseline. Recorded owned processes were absent after completion. These are network-client tests; they do not establish couch co-op in one game process.

The private service adds explicitly public rooms while retaining the existing private/friends settings. Authenticated browsing returns a bounded, correlated snapshot of sanitized room metadata. Private, full, started, stale and blocked rooms are excluded; listings do not disclose peer addresses, account identifiers, character data or chat. Its in-memory service fixture passed 67 checks. The actual native parser/CLI fixture passed 181 checks covering snapshot completion, request correlation, malformed/truncated responses, limits, disconnect/timeout behavior and JSON output. CPU fixtures alone do not establish live interoperability.

Three subsequent bounded integration checks used the private discovery application:

| Check | Actual route | Confirmed shared result |
| --- | --- | --- |
| Direct discovery | Public host, authenticated native browse, mapped Tk Find Games callback, join using the discovered code, ordinary character/control inputs | 1,393 common ticks; 21 shared columns; zero mismatches |
| TLS and forced relay | Local TLS directory/control listener with an explicit private CA override, discovered-code join and forced UDP relay | 1,381 common ticks; 21 shared columns; zero mismatches |
| Manual launcher flow | Two mapped launchers invoke the real Host Public, Find Games, Join Selected and Start Match button callbacks; automatic start disabled | 1,129 common ticks; 21 shared columns; zero mismatches |

All three intervals remained in the hub, with positive player HP and no observed out-of-sync or dropped-player flags. They establish basic discovery, joining and shared movement, not campaign completion. The existing native session bridge initializes the game before normal character/control inputs; the retired official login/lobby screens were not qualified by these checks.

The TLS run recorded four successful server handshakes and no failed handshakes. It also recorded 15 relay drops whose individual causes were not traced. That counter is distinct from the zero dropped-player flags and matching simulation data; a lossless-datagram claim is not supported. TLS was configured for directory/control TCP, with no packet-capture claim or encryption claim for the separate UDP gameplay payload. Public-CA deployment, WAN operation and NAT/router combinations remain untested.

The complete launcher flow recorded two launcher exits zero and two game exits zero. The owned local service was intentionally terminated and recorded Windows exit one; that exit is retained. Independent review required a positive matching interval, actual exits and absence of all recorded owned processes rather than relying on the original weaker aggregate flag. The host's Start callback ran once after the real room reported two ready, compatible players. Nine serialized Find Games callbacks reused one persisted browser identity; a copied service-database audit found exactly that browser account plus the two game accounts. Per-refresh login packets were not captured. Button invocation exercised actual Tk callbacks, not human mouse clicks or physical-controller input. Both captured game views had legible two-player HUDs; no console visual-fidelity claim follows.

A separate physical-controller session on the installed build provides partial evidence. During 48.62 seconds, read-only XInput sampling observed one connected controller, full left-stick travel, A/B/X/Y, right shoulder/trigger, Start and Back actuation. Overlapping game records show movement and cast/block/menu state changes. The user reported, “Finished—controls respond correctly.” However, physical input also merged during scripted setup: the Load transaction occurred before a later guard expected it, and the game exited three on that guard's timeout before READY. The planned 300-second session was not reached. This is retained as partial physical coverage and user feedback, not a whole-session pass, an event-level latency measurement, every-button coverage or physical rumble proof.

A normal visible, paced installed-build couch trial now completes the ordinary offline frontend, sequential creation of two characters, and independent movement in one shared hub/camera. The process exits zero with all 3,915 consecutive watched rows retained. Player one moves 30.4263 world units while player two remains stationary; player two then moves 30.0955 while player one remains stationary. Each leg records 12 effective axis rows, neutral opposite-port axes, and 30 final neutral rows with both positions stable. Both distinct player actors remain alive. The two captured views show a lit scene, readable two-player HUDs and changed player positions. These are two scripted PS2 input ports in one process, not two physical controllers, multiplayer combat or campaign acceptance.

An earlier private two-port candidate passed 254 CPU checks and linked as `370b5295aa12393a884ae4adac0bcae7e7abc7397434c2c0a8b2dc906d1f4662`, but remains rejected and uninstalled. Its fixtures missed the case where both pads detach and only the former second pad reconnects, allowing promotion to player one. A separate red control runs the new 70-check fixture against that preserved v1 source: all original 49 checks still pass, while 14 added ownership/reservation checks fail. The corrected v2 result is separate below. That revision did not qualify physical two-controller play or three/four-player virtual multitap; the later four-player software checks are recorded separately below.

The separate private v2 controller revision resolves former-slot ownership before filling vacant ports and prevents generic assignment from stealing another port's reserved XInput index. Its CPU fixtures passed 275 checks: the prior 129 input, 22 rumble, 39 mapping and 15 Windows merge checks, plus 70 two-port checks. The latter include 21 additional checks for both pads detached, reverse/forward/simultaneous reconnection, replacement slots and an arrival between probes. These use fake callbacks and establish the tested software behavior; they do not establish actual hardware hotplug identity or felt vibration.

The combined v2 application is SHA-256 `bef3bd53eb91bff48f8aaf98ecf291a82805f87076e433dcf465735e33ed5a4c`. Independent offline review found its control relink identical to the tested `e9010c9c` discovery build after normalizing only the PE/COFF timestamp, and only the two intended Windows controller/application objects replaced in the candidate link. Its private package passed the existing arithmetic, PNG, deterministic native-boot and 62 software-input qualification, with driver exit zero. Raw logs contain the expected arithmetic and PNG checksums, native boot counters and all 62 held/released input pairs. Arithmetic, PNG and native boot use unchanged companion programs; the `bef3bd53` application receives the software-input cases through its port-one test adapter in offscreen/unpaced mode. This is not a two-port physical test or a new discovery/network session on that binary. All audited inputs and the installed `d7c2258b` application stayed hash-identical.

Earlier failed runs remain unchanged. One qualification wrapper stopped before launching any child because TEMP/TMP shared a directory and creation was not idempotent. Offline couch runs retained exit three for an incorrect menu selection-word predicate, a transient character-handoff page predicate, a menu-fade-zero predicate, and an assumed actor-state value. Raw records and original-code review distinguish these test mistakes from a production defect: the handoff page had already completed; the normal New Game finalizer can leave the inactive menu-fade accumulator at 128 while world RGB settles normally; and the watched actor word remained two during actual movement. The accepted run uses persistent frontend conditions, actual world RGB, and measured per-player displacement and neutral stability. None of the earlier failed whole invocations is relabeled as passed.

The private `bef3bd53` candidate also completes the same normal visible/paced two-character couch route, with software input supplied through the compiled Windows host-controller adapters. Both scripted sticks remain neutral during its movement legs. Port one moves 30.4263 world units with port two stationary; port two moves 30.0955 with port one stationary. Both legs retain 30 final neutral rows with stationary positions. The actual process exits zero, all 3,915 consecutive watched rows remain, and held/released application pad diagnostics agree with the effective port axes. Viewed images show the two-player shared scene. This closes the bounded second-port software-to-game movement path; real two-pad input, physical reconnect behavior, all-button gameplay and vibration remain separate checks. This application remains a private candidate, with no new network session or installation claim on that binary.

A separate mapped-launcher check invokes Start local directory, Find games against that actual loopback listener, then the normal close callback. It receives a complete empty list, the native browser exits zero, and the owned service is deliberately terminated with Windows exit one. Both children are terminal before outer cleanup. Two convenience launcher copies with separate profiles expose the previously tested manual host/search/join/start route; their local paths, game inputs and private identities stay outside this report. They contain no automatic character or match-start scripts. No Internet directory is deployed by this work.

The proposed online path uses player-hosted game rooms, configurable replacement directory/rendezvous infrastructure, direct peer UDP where available, and relay fallback. Discovery still requires a directory; this is not fully decentralized server-free Internet discovery. The local tests did not contact retired official services or establish a public Internet deployment. No proprietary game files, generated game code, executable binaries, saves, certificates, credentials or raw game-state captures accompany this public prose. Existing failed and partial receipts remain retained privately.

## Four local players and subsequent campaign/rendering checks

A separate private opt-in virtual multitap application is SHA-256
`af99e292bad152a604e77385dbc95118c210dee5063b0df24fd3d047a53bb149`.
Its normal two-pad topology remains PS2 ports 0 and 1, slot 0. With `--multitap`,
four logical inputs map to PS2 port 0, slots 0 through 3, following the original
game's slot-count and player-routing code. Physical ports 2 and 3 are not invented.
The connection-monitor open/close behavior is an explicit virtual policy, without
a claim about physical PS2 adapter unplugging.

Ten CPU fixture runs report 426 checks with zero failures, including all 275 prior
input checks, four-host assignment/merge tests, the actual script parser/scheduler,
and baseline/candidate extracted IOP controller services. Ten of those checks run
the baseline IOP control. Complete normal-two controller records match byte for
byte. The private app replaces exactly four objects; the unchanged control relink
matches the prior two-port candidate after normalizing only the COFF timestamp.
These fixtures use fake device callbacks and do not establish physical hotplug or
felt vibration.

Two normal visible, paced four-character trials each finish with actual child exit
zero, no timeout and all 6,663 consecutive watched rows retained. Both use the
ordinary Four Players menu and serial character creation before entering one
shared hub. One supplies four logical scripted sticks; the other keeps those
sticks neutral during movement and uses all four compiled Windows software
controller adapters. Four distinct actors/names use the default class 6, level 1,
zero XP and 500 gold. Each finite leg moves its intended actor with the other
three stationary; releases retain 30 neutral, stationary rows. All four remain
alive, and inspected views show four readable HUDs and the shared scene. This is
bounded four-player movement, without four-player combat, mission, physical-pad
or network qualification on this binary.

The same application also repeats the accepted ordinary two-character Windows
software-controller route with multitap disabled: actual exit zero, no timeout
and 3,915 watched rows. The earlier two-port build's results remain separate.
Fresh private cards are used for these frontend tests; campaign saves and the
installed `d7c2258b` application are unchanged.

The installed application also continues from its preserved level-2 checkpoint
with 1,888 XP and armor 54 through ordinary frontend Load and controller inputs.
The west corridor route finishes with full health/mana. These campaign checks are
offscreen, clock-paced at 59.94 and muted; the original first plan's unpaced label
is corrected by its actual runtime header and option order.

An aimed Holy Strike deals 28 observed damage to a Kobold, with the player resolved
as its attacker and an advancing damage stamp. That target survives. A subsequent
spell/melee continuation deals 26 then 23 damage to another Kobold, kills it and
awards 25 XP, reaching 1,913 XP. That invocation ends alive; its minimum HP is
24.609240. The 1,913-XP progress is unsaved. A later blocking/regeneration attempt
fails survival and ordinary checkpoint recovery restores the saved 1,888-XP state.
A health-only test wait accepts restored health while the actor pointer is briefly
null. Its clean process exit and completion marker therefore do not qualify
surviving combat. This is a failed test strategy/guard and ordinary gameplay death,
with no demonstrated engine defect. All source/copied game-save files remain
unchanged, with zero emulated card bytes written. Mission completion remains open.

A separate private color-PSMCT16S address correction is built as
`e2719a8715f5ae0f318a696293d72138d2d37939cb9719a6b6c8801e8d986cce`.
The prior decoder aliases CT16S to CT16 at five upload/extent/palette/texture sites,
although their documented block layouts differ. An independent table oracle and
cross-format GIF upload/sample cases distinguish that error from a same-wrong
upload/read cancellation. The baseline fails 11 of 37 fixture checks; the candidate
passes all 37. Difference counts include byte comparisons and a size-mismatch
sentinel, not uniformly pixel counts. Fixture-only wrap arithmetic and unsupported
depth controls do not implement canonical wrapped storage or depth transfers.

Only the GS object changes in that standalone app; its unchanged control relink
matches installed d7 after COFF timestamp normalization. A matched ordinary west
walk completes with exit zero: all 2,043 rows across 43 watched columns and the
960x720 PNG are byte-identical to the installed baseline. Canonical items,
equipment, skills, stats, quests and the four game-save files match. Each whole-RAM
pair retains 26 differing bytes: 24 are source-backed copied-file timestamps and
two remain unclassified. Whole-RAM equality, CT16S use in this scene, visible
improvement and console fidelity are not established. The separate production
CT16 write-precision gap remains open. Both new applications and their source
overlays remain private, pending native-client handoff; this is an authored
research update with no new implementation, game data or raw captures published.

## Three-player frontend and four-player mission unlock

The private opt-in multitap application `af99e292` now also completes the ordinary
Three Players frontend and three character creations. The actual process exits
zero with 5,289 consecutive watched rows and no timeout. Each compiled Windows
software-controller adapter moves its intended actor while the other two remain
stationary; all three retain 30 neutral rows without drift. The fourth input stays
neutral and no fourth player actor is created. All three remain alive with their
initial XP and gold. Inspected views show three HUDs.
The virtual multitap still exposes four input slots; that capacity is distinct
from the three selected players. This is software input, not physical-pad proof.

A subsequent four-player test follows the ordinary frontend, character creation,
and approach to Firiona, then advances her dialogue with normal player-one button
edges. All four distinct live characters receive the first mission availability
bit before the dialogue closes. Their HP, XP, gold, canonical items, equipment,
skills and positions remain unchanged during the dialogue continuation. The
camera returns to its normal shared view and all four HUDs return. The actual
process exits zero with 7,745 consecutive watched rows and no timeout. This
qualifies the observed party mission unlock, not portal entry, four-player combat
or mission completion. An earlier approach-only diagnostic is retained separately;
its mission flags correctly remain unset before dialogue completion.

The party then gathers and walks north through normal Windows software-controller
inputs. A first portal approach stops before interaction: its finite route leaves
the trigger outside the player's source-backed interaction query, the prompt is
inactive, and the game exits three on the position guard. No Square, mission-menu
selection or level transfer occurs in that invocation. It remains a failed route.
A separate retry preserves that executed prefix and adds eight northward input
ticks for all four players, with the interaction and transition predicates intact.
It completes the normal owner-zero menu selection and actually enters `blood1`.
The process exits zero with 8,635 consecutive watched rows and no timeout. All four
current distinct actors arrive alive with full HP/mana, zero XP, 500 gold, their
mission availability, canonical items, equipment and skills retained. The final
ready interval is unpaused and neutral, with settled world RGB and stable player
positions. Inspected views show the usable portal and the actual four-player
mission scene. This qualifies first mission entry; combat, campaign saving and
mission completion remain separate four-player work.

An installed-build campaign continuation uses one melee finisher after the
previous ordinary spell setup, then retreats earlier. One Kobold kill awards
25 XP, reaching 1,913 XP. All valid mission-player rows remain alive without a
checkpoint reset; the minimum observed HP is 40.376095 and the paused endpoint
has 40.469875 of 46 HP. Five living pursuers remain nearby, so this is a bounded
survival improvement, not safe recovery, a cleared encounter or mission completion.
The process exits zero with 2,607 consecutive watched rows and no timeout.
The 1,913 XP remains unsaved: all four source/copied game-save/icon files retain
their hashes and the emulated memory card records zero bytes written. The earlier
failed survival attempt remains a failure. The installed application is unchanged.

A further bounded retreat also ends alive at 1,913 XP and 35.926376 HP, but does
not reach its intended waypoint. Most newly commanded movement occurs while the
player remains in state 8; observed displacement begins after state 2 returns.
The original state-machine code treats movement in state 8 as turning, with
release-to-move gated by animation track conditions. That supports the partial-motion
interpretation without proving the exact animation cause. The process exits zero
with 2,675 watched rows, but the route goal is explicitly failed. All five watched
living pursuers remain nearby, and no game save is written.

A separate north-facing guard continuation retains a contiguous 120-row actual
R1 hold. The recorded positions and facing place all five watched pursuers in the
approximate forward half-plane for 118 rows after the initial turn. HP does not
decrease during that held interval.
The paused endpoints rise from 35.926376 to 36.757004 HP while retaining 1,913 XP.
This is finite guarding and partial regeneration, not full healing, safe recovery,
an escaped encounter or durable progress. The actual process exits zero with
2,837 watched rows; no game save is written.

## Connected CT16 write-path experiment

A separate private renderer revision connects original GS write state through
the actual GS decoder and frame list to an optional GPU write path. For each
accepted raster triangle, it reads a separate destination snapshot, applies the
integer blend, dither/clamp, 16-bit packing and framebuffer-mask merge, and writes
the expanded packed result. This avoids sampling the active framebuffer and
quantizing only after an entire batch.

Six authored packet streams complete against an independent software GS reference.
The original three authored canary packets are unchanged. The original CT16 canary retains its
failure on both baseline and candidate-default, while the strict path corrects
red 255 to 248. The earlier 1,024-pixel ROI is an analysis subset of the actual
64x64 sprite; all 4,096 baseline pixels differ in red, with no alpha differences.
Two-, three- and five-sprite overlap cases also
separate the baseline from per-write packing. All six strict destination images
match all 24,576 reference RGBA pixels. The CT32-render and CT16-upload controls
continue to match. Baseline and candidate-default target bytes match on all 11
observed targets; their command and draw counts also match for these six inputs.

The actual decoder fixtures pass 960 checks across 48 cases. Their 24 fast/slow
pairs match raw input and vertex words plus the recorded write-state metadata;
they do not serialize every frame-list/resource field. The policy fixture passes
37 checks. Four actual GPU preflight rejection
controls issue no draws and allocate no target. An earlier private revision builds
as C++ but fails GLSL compilation; its failed result is retained. The subsequent
revision corrects the offending shader identifier.

An expanded state matrix first stops on an authored packet error: a write intended
for FBA instead targets the PABE register. The strict path rejects that unsupported
state before the affected target is mutated. This invocation is invalid overall;
its partial captures remain preserved and are not counted as a completed matrix.

A corrected sibling changes only the authored PABE/FBA register setup, retaining
all six original packet files and the same renderer sources and executables.
Its 24 streams include those six, 15 additional CT16 write sequences and three
additional upload controls. All 36 native/reference child invocations exit zero.
The strict path matches 98,304 destination pixels and 81,920 rendered-source pixels
against the independent software reference. All 180,224 observed default-target
pixels remain byte-identical to baseline. Five cases split one additional GS
command in default mode; actual GL draw counts remain equal to baseline in all
24 cases. The sequences cover negative and overflow blend results, clamp/wrap, signed nonuniform dither, colour and alpha
masks, FBA and destination-alpha history, source-alpha values and selectors,
plus the second context with PRMODE and shifted XY coordinates. Recorded strict
raster-triangle and snapshot counts agree at 86 each. These are 24 total streams,
not 30 unique cases when combined with the earlier six-stream run.

This path accepts only known fresh CT16-only target history, flat untextured
geometry at one-to-one resolution and no multisampling. Alpha testing, destination
alpha testing, depth writes, depth tests beyond always, PABE, fog and textures are
excluded. It rejects unsupported or ambiguous history before target mutation.
The 24 streams do not exhaust its permitted blend, dither and mask combinations.
The successful cases do not qualify CT16S rendering, canonical wrapped storage,
depth transfers, general game scenes, performance or console fidelity. Extra raw
write-state comparisons can split other default-path batches, so the matched
counts are not universal performance equivalence. These fixtures do not qualify
the strict path in general game scenes or an installation.

A separate private full-application build recompiles all 38 native C++ objects
against the candidate headers and reuses 49 pinned generated EE objects plus the
resource object. An original-object control matches the installed executable
after excluding only its COFF timestamp. The candidate completes the same ordinary
campaign Load and traversal in default mode: all 87,849 watched values and the
captured image match the installed-build baseline exactly. Both RAM snapshots
differ in 40 verified emulated memory-card timestamp bytes; the remaining bytes
match. Character data, canonical inventory, equipment, skills and the four copied
game-save/icon files remain unchanged, with zero card writes. This bounded
compatibility run leaves the strict path disabled and does not exercise strict
CT16 writes in gameplay. All eight installed programs remain unchanged. The
broader production CT16 problem remains open, and the implementation stays private.

## Separate online cameras and four-player input preflight

Two installed-build clients now complete a separate-camera test through the native
direct-launch integration and replacement loopback rendezvous. Both actual child
processes exit zero and finish their scripts. All 908 common confirmed ticks match
across 29 shared columns, including both decoded camera-yaw words: 26,332 equal
values, with no observed out-of-sync or drop-counter increase, death or checkpoint reset.
This is one-PC direct-peer evidence, not Internet, router/NAT or two-PC proof.

The two owners move 320.058707 and 292.115102 units, reaching an actual horizontal
separation of 630.214809 units. Each local camera follows its validated local
prediction copy rather than the party midpoint; maximum observed XY errors are
0.0000691 and 0.0001249 units. Opposite ordinary right-stick inputs produce local
yaw changes of +3,157 and -2,557 angle units, ending at -5,173 and -10,982. All four
actual captured views were inspected: the local characters occupy different hub
areas and each view follows its own character. Both real players remain alive at
32.799995 HP. Their positions and HP are exactly stable for the final 30 common
ticks with movement released. All four decoded axes are neutral for the final 26
ticks, and both camera yaws are settled for the final 23. These windows are distinct.
The application renders offscreen at 320x240 with sound disabled; its unpaced
render loop and 59.94 network pacing do not establish display performance or feel.

An earlier invocation fails both children at a late exact-reset-yaw assertion,
before any authored movement or captures. Its 200 common ticks still match. The
recorded first tick has the expected -8,192 yaw on both clients; the original
centered-stick codec startup transient then rotates their local cameras. The
corrected test declares a finite 2.8125-degree steering tolerance as a route
admission condition, checking local and replicated yaw, neutral axes, follow mode,
control, zoom and stopped yaw velocity before movement. This tolerance is not a
camera invariant, and the earlier failed invocation is preserved. No game camera
or simulation state is forced.

Fresh character startup writes the ordinary game header and two icon files,
129,572 bytes per client. No character-slot file or Save action occurs. The test
permits that explicit initialization and separate private network defaults; it
does not claim zero cumulative card writes. Each client uses a distinct private
profile; known source checkpoint files and installed programs remain unchanged.
The original multiplayer camera behavior is
preserved: online clients have individual views; couch play uses one shared view.

An additional private four-player mission preflight completes with exit zero and
9,203 watched rows. Each owner's ordinary Cross pulse reaches that owner's melee
action state while the other three digital inputs remain neutral. The party then
moves northwest through twelve finite chunks, with 96 actual held-input rows per
player. Their measured horizontal displacements range from 199.448267 to
232.601022 units. All four remain alive at 32.799995 HP and zero XP, with their
canonical items, equipment and skills unchanged.

This is approach and attack-input evidence only. Four watched enemies retain
positive HP, with no observed enemy HP decrease, death or earned XP; the closest
observed enemy-to-party distance is still 548.269957 units. An AI-state or target
handle change alone does not establish a chase, attack or hit. Fresh startup
writes the header and two icons, 129,572 game-card bytes, without creating a
character-slot file or issuing Save. The author-owned offline audit preserves its
earlier evaluator failure and correction; despite the receipt's filename, it is
not an independent review. Four-player combat and campaign durability remain open.

## Application frame-queue transport correction

Source inspection finds that the experimental CT16 write-history fields reach the
standalone backend fixtures but are omitted by both application frame queues. The
Windows and Qt handoffs manually transfer the older frame-list members, losing
the new upload windows and transfer-exclusion flags. The earlier full-application
compatibility test had strict mode disabled and remains a default-mode result.

A private correction transfers the whole frame list and restores the producer's
legacy display/aspect/number metadata. This retains the inactive display-rectangle
behavior when a following frame has no display target. Shot association, timing
and queue control stay unchanged. Exact source-extracted Windows and Qt handoffs
are tested with actual GS-decoded authored uploads and transfer exclusions, empty
and nonzero three-slot queues, reuse and empty-display frames. Across 36 cases and
432 checks, the original handoffs show 62 isolated CT16 transport failures; the
candidate has zero failures. The negative controls retain zero unrelated failures. The CPU fixture consumes
its ring immediately on one thread; it does not exercise real Screen scheduling,
mutex/event ordering, a full queue or sustained queue pressure.

The private Windows build recompiles only the application queue object and reuses
the other 87 pinned objects. An original-object control matches the previous
private application after excluding only its COFF timestamp. No frame-list ABI or
renderer-state layout changes, strict-mode option changes or installation occur.
The Qt evidence is an extracted CPU handoff test, not a built or running Qt app.
This correction alone does not qualify strict writes in general gameplay,
canonical GS storage, rendering fidelity or performance.

A subsequent private Windows application, `c32c93c8`, completes the same ordinary
checkpoint Load and westward traversal with the transport change, strict mode
still disabled, and a fresh copy of the accepted 1,888-XP checkpoint. Its actual
child exits zero with 2,043 watched rows and no timeout. Author and independent
offline reviews find all 87,849 values across 43 columns exactly equal to each of the installed
baseline and the previous private application. The 960x720 PNG bytes and all
decoded RGBA pixels also match both baselines exactly.

Each before/after 32 MiB RAM comparison actually differs in 40 bytes, all verified
as copied-card file timestamps and their original-game BCD menu-date derivatives;
the remaining bytes match. The full player record, six canonical items, equipment,
skills, allocations and quests remain unchanged. The character retains level 2,
1,888 XP, 68 gold, 46 HP, full mana and armor 54. The four original and copied
game-save/icon files retain their hashes, and game-card I/O records zero bytes
written. Private network defaults may still be created. Installed programs and
source inputs remain unchanged. The independently reviewed traversal qualifies
only the observed default-mode comparison; strict CT16 writes in gameplay, Qt
application runtime, console fidelity, performance and installation remain open.

## First four-player mission battle

A separate retry of the private multitap prototype completes one ordinary first-
mission battle. The previous attempt remains failed: it stops before casting at
an enemy-X admission condition, with all four players alive and no damage or XP.
Its endpoint already places the enemy within spell range; southwest facing is
41-54 degrees from the recorded enemy bearing, beyond the source's 30-degree
half-cone. No spell is attempted there. The retry preserves the
executed prefix and the same 300-field wait, turns west through ordinary blocking
input, and uses an attained range box. It changes the test recipe, not game code.

All four fresh Shamans cast their normally learned starting Poison Bolt twice.
The first burst kills the watched Kobold: three contemporaneously resolved party
attackers deal 22, 21 and 27 damage, taking HP from 69.0224914 to -0.977508544 and
AI state 20. XP rises on that death row to 51, 51, 51 and 77. The second burst is
another cast attempt, not another kill. Later post-death changes lower corpse HP
further; final HP must not be treated as the killing blow. A reused damage-handle
node resolves to different actors at the actual hits, so its final contents do
not establish ownership of earlier damage. The second player casts and spends
mana but has no credited direct hit in this observed kill.

The actual child exits zero with 10,077 watched rows, completion and no timeout.
All four remain at 32.7999954 HP through the added interval and finish released in
normal state 2. Canonical items, equipment and skills match the before/after
captures; character-slot files and Save actions are absent. Ordinary startup
writes the header and two icons, 129,572 game-card bytes. The seven startup files,
original checkpoints and installed programs remain unchanged. The captured shared
mission views were inspected; raw-state reviews establish the damage and XP.
This qualifies one scripted fresh-profile four-player battle. Wider combat,
campaign saving, mission completion, physical four-pad play and WAN remain open.

## Four-player party Save and fresh Load

The private four-controller Windows candidate `af99e292` completes one ordinary
battle, a single player's Recall and a hub Savepoint save. Its child exits zero
with 10,920 watched rows and no timeout. The complete earlier battle prefix,
10,077 rows across 301 columns, matches exactly. All four characters remain alive
and retain earned XP of 51, 51, 51 and 77. Only the initiating player's Recall
stack falls from two to one; the other three stay at two.

One normal offline transaction writes a 310,392-byte file containing all four
characters. The file exactly matches the completed RAM save buffer. Each complete
19,504-byte serialized character record also matches its game-built RAM snapshot.
After decoding the original serialization conversions, all 28 occupied 72-byte
item records, each character's 17 equipment and three auxiliary references,
48 skill pairs, statistics, allocated points and quest data match the live save
state. This establishes the serialized snapshot and canonical comparisons;
ordinary return metadata, mana regeneration and transient live fields change
during the route. The immediate hub image still shows loading artwork; later
images show the lit town, four avatars/HUDs and the card overlay closed.

A first fresh-load attempt remains a failed strict case. It stops at a guard
requiring the loaded-from-save flag after card transfer has finished; its controls
and RAM/image captures are never reached. The original game sets that temporary
flag during restoration, then consumes it during level setup and selects start
rank 3. The flag is already clear before the late guard starts. The corrected
test observes the positive flag during the read, then requires it cleared after
setup, retaining the other card, actor, ownership and visual barriers. Game code
is unchanged. The first 1,050 rows across 331 shared columns match the failed
attempt exactly, without normalization.

The corrected fresh process loads a separate copy of the four game-card files,
exits zero with 1,323 watched rows and no timeout, and records 311,272 card bytes
read with zero written. Both settled RAM captures restore the four names/classes,
earned XP, gold, Recall quantities and source-decoded items, references, skills,
statistics, allocated points and quests from the actual file. Fresh actor slots,
local-player lists, pad mappings and connections agree for all four owners. The
rendered town is inspected after RGB readiness and 30 neutral fields.

Each logical owner supplies eight movement-input rows alone, then releases for
30 fields. All four directly commanded actors move, and all four XYZ values are
stable in the last eight rows of each release interval. During slot 1's leg,
neutral slots 0 and 2 also move while recorded party contact is present. Their
inputs remain neutral. That motion is compatible with the original collision
path, but the full solver and its sole cause are not proven; zero non-owner
motion and whole-party stability for all 30 release rows are not claimed.

Original and copied party files, the earlier 1,888-XP checkpoint and installed
programs retain their hashes. The private candidate is not installed. These cases
qualify one scripted four-player return, party Save, fresh Load and movement/release
path on one PC. The following return test extends this evidence; wider campaign
progression/completion, physical multi-pad play, WAN, reference fidelity and
performance remain open.

## Four-player saved mission return

A fresh process on the private four-controller candidate loads the accepted
four-character party file through the normal frontend. After the existing four
movement/release checks, only owner 0 supplies the ordinary hub Recall chord.
The countdown starts and the whole party returns to the saved first mission.
The hub return consumes no additional Recall item: quantities remain 1, 2, 2
and 2. This extends the earlier Save/fresh Load result with actual mission return.

The first return attempt remains failed. It reaches four live mission actors,
but stops at the final brightness guard before its returned-world RAM/image
capture. The test accepted an old RGB value in the same field that the warm-up
counter reached zero. The original code then resets the new fade to zero and
advances it by four per field. The trace ends at RGB 116; the one-field final
deadline expires before full brightness. The initial source review missed this
temporal admission window. No game-code defect follows from that failed test.

The retry changes only the test's return-readiness sampling: advance one ordinary
field after warm-up reaches zero, reacquire exact RGB 128 with a bounded wait,
then retain all 30 neutral settling fields and the original final brightness,
ownership, liveness and card-idle checks. Gameplay inputs and game code are
unchanged. Its actual child exits zero with 1,573 watched rows and no timeout.
Post-reset RGB readiness is marked at frame 1,540 and the returned-world capture
at 1,570, after the complete neutral interval. The viewed image shows the rendered
mission with four avatars, their HUDs and the savepoint.

Independent raw-state review compares the restored party with the actual saved
file: all occupied item records, equipment and auxiliary references, skills,
statistics, allocated points and quests retain their source-decoded values.
The four live actors retain XP 51, 51, 51 and 77, full HP and 500 gold each.
Requested return coordinates match the saved metadata; normal terrain and
secondary-player placement can adjust live positions. Whole live-record byte
equality is not claimed for those positions, regeneration or transient fields.

The saved mission contains one negative-HP Kobold record from the earlier battle.
The runtime check resolves its current allocation from the actual object pools,
class, saved coordinates and variant, independently of its old address. It
requires the matching current creature to retain negative HP and the
source-defined dead state and flag bits; absence alone is not accepted. The saved
HP fraction is applied to the newly created creature's maximum HP, so raw HP need
not equal the earlier battle value. This establishes restoration of
that one saved defeated enemy after normal fresh Load and mission return. It
does not establish every saved object or completion of the mission.

The game reads 311,272 card bytes and writes zero. Original and copied party
files, the earlier campaign checkpoint, source inputs and installed programs
retain their hashes. The four-controller candidate remains private and is not
installed. Wider campaign progression/completion, physical multi-controller
play, WAN, reference fidelity and performance remain open.

## Four-player campaign route movement

The private four-controller candidate completes the first short western waypoint
on the saved mission route. Its actual child exits zero with 1,667 watched rows
and no timeout. The complete accepted return prefix, 1,573 rows across 300 shared
columns, matches exactly without normalization.

All four logical owners supply six eight-field movement pulses, separated by two
neutral fields, then release for 30 fields. The actual decoded input records
contain 48 held left-stick fields per owner, with digital controls and the eight
new right-stick columns neutral. Measured westward displacement is 112.65, 105.85,
49.30 and 123.64 units. All four exceed the predeclared displacement goals and
remain inside the corridor; maximum pairwise XY separation is 67.09 units, below
the 160-unit bound. Their positions are stable throughout the final release.
Different displacement under simultaneous input does not isolate the effects of
terrain, contact or camera behavior.

The initial offline readers misinterpreted the normalized diagonal axis values
and the relationship between command markers and decoded guest-pad updates.
The original false receipts are preserved. Separate corrected readers use the
actual adapter conversion and require each of the six exact eight-field guest
intervals. The game's raw-pad snapshot also copies decoded synthetic direction
bits. Source and trace review show the command at field F becomes visible
in guest pad RAM at F+1 in these intervals. No rows are shifted or normalized,
and game code and actual inputs are unchanged. This is not a measurement of
physical device or input-to-display latency.

All four remain at full HP, with XP 51, 51, 51 and 77, 500 gold each and Recall
quantities 1, 2, 2 and 2. All four RAM anchors retain the saved file's decoded
occupied items, equipment/auxiliary references, skills, statistics, allocated
points and quest data. Game-card I/O reads 311,272 bytes and writes zero.
The captured town, returned mission and new waypoint views were inspected;
image byte repeatability and reference fidelity are not established by this
movement result.

The first-waypoint census resolves the current allocated objects independently of old
addresses. No positive-HP member of the four explicitly checked creature classes
is within 500 units of the party at this endpoint. That bounded census does not
establish all-enemy absence, safe future travel or completion of the mission.

A further ordinary-control attempt clears space, moves selected owners south and
southwest, then advances the party toward the western corner. Its actual child
exits zero with 1,811 watched rows and no timeout. All 513,436 values in the
earlier 1,667-row, 308-column prefix match exactly. The intermediate alignment
goals pass: southward displacement is 34.00 and 27.32 units for the selected
owners, and north-south party spread is 15.58 units at that checkpoint.

This follow-up remains a partial route. It reaches the corner, with the leading
character at X 3038.34 and all four between X 3038.34 and 3079.41, but final
north-south spread is 42.76 units, exceeding the predeclared 40-unit limit.
The limit is preserved. Inputs, liveness, five canonical snapshots, source/card
preservation and zero-write checks pass; a clean process exit does not qualify
the unmet formation goal. The current endpoint census also finds a positive-HP
Kobold in state 3 about 432.54 units from the nearest player. Further travel
requires fresh combat and route checks. No northern turn is attempted here.

The first waypoint reaches part of the source-linked corridor toward Natasla.
It does not reach the NPC, make a story choice, complete a mission, earn new XP
or save new progress. Original/copied party files, the earlier checkpoint and
installed programs retain their hashes. The candidate remains private and
uninstalled; full campaigns, physical controllers, WAN, fidelity and performance
remain open.

## Four-player feedback alignment and northwest turn

The next attempt stops during startup because three new diagnostic watches use
unsupported `x64` types. Case 17 records no watched fields or captures and does
not qualify gameplay. Its failed run and the earlier source-admission review,
which missed the unsupported types, are preserved with a separate correction.
Case 18 changes those three watches to `hex8` reads, retaining their addresses,
ordinary controller sequence and geometric requirements. Game code is unchanged.
The actual child exits zero with 1,899 watched rows and no timeout. Its complete
1,811-row, 308-column prefix matches case 16 exactly: 557,788 values without
normalization. The two coordinate-gated alignment holds each take seven fields,
followed by the bounded northwest turn.

| Case 18 measurement | Observed result |
|---|---|
| Northward movement, players 1–4 | 51.012 / 14.937 / 35.212 / 36.575 units |
| Final north–south spread | 37.107 units; limit 40 |
| Greatest pairwise horizontal XY separation during the extension | 72.358 units; limit 160 |
| Final neutral inputs | All four players, 30 fields |
| Observed stationary XYZ tails within that release | 30 / 25 / 30 / 30 fields |
| Game-card traffic | 311,272 bytes read; zero written |

All predeclared case 18 movement and formation goals pass. Six recorded state
anchors retain all four heroes' canonical items, equipment/auxiliary references,
skills, statistics, allocations, quests and saved return metadata. Health stays
unchanged, with no additional Recall consumption. The author audit passes 660
checks and the independent audit passes 2,065; these are bounded receipt checks,
not game-completeness measures. Neutral inputs do not imply every actor remains
stationary for the whole release. No sole cause is assigned to the observed
settling. Source and copied game-save files and all eight installed programs
retain their hashes. A fresh allocated-object census validates a living Kobold
139.19 horizontal units from player 1, so this limited result establishes neither
all-threat absence nor safe onward travel to Natasla. Case 16 remains partial
under its original 40-unit formation limit, and case 17 remains a startup failure.
The candidate is private and uninstalled. No NPC decision, new battle, new Save,
mission or campaign completion, four physical controllers, WAN, general
performance or console pixel fidelity is qualified here.

## Private live input control and default-off comparison

A private opt-in Windows prototype accepts bounded ordinary controller leases
for four logical owners and read-only state snapshots. It exposes no game-memory
write or game-function interface. The build passes 79 Windows CPU checks and
eight Python fake-client tests, alongside the previously verified 98 core
checks. A control relink of all 88 baseline objects matches the accepted
four-controller build apart from its COFF timestamp; the prototype rebuilds one
translation unit and reuses the other 87 objects. Those build and synthetic-test
results do not establish actual gameplay or physical-controller behavior.

With the control option disabled, the new binary completes the case 18
route with all 1,899 rows and 338 columns identical: 641,862 watched values,
without shifting or normalization. All six party anchors retain canonical items,
equipment/auxiliary references, 48 skill entries, statistics, allocations, quests
and saved return metadata. Nevertheless, **strict default-off equivalence fails**.
The first three PNGs match exactly, but the later three differ by 2, 4 and 12 RGB
pixels, with a maximum channel change of two and no alpha differences. These are
actual decoded pixel differences, not PNG metadata changes. Full RAM comparisons
also retain 315 changed bytes: 240 in source-attributed card date/time and menu
structures, 65 in CD-request and sound structures, and ten stack bytes whose
writer remains unproved. Structure identification establishes neither the cause
of different values nor harmlessness or graphics causation. No bytes are ignored
or normalized, and no rerun is used to replace this failed comparison.

A separate ordinary fresh party Load and hub test completes with clean game and
client exits, 2,557 watched rows and no timeout. Its entire earlier Load prefix,
1,323 rows across 332 common columns, matches exactly. Raw-state review verifies
four isolated eight-field owner leases, a four-field joint lease and the default
eight-field expiry. Each isolated lease moves its owner while the other three
remain stationary. Cancellation produces three actual held guest samples before
neutralization, and disconnect produces one; both releases precede their
32-field expiries. Stale sessions, repeated request IDs and expired requests are
rejected, followed by working current-session input. These are software-input
observations, not physical-device or input-to-display latency measurements.

Independent raw review correlates 485 atomic 29-span snapshots with the same watched
fields, checks the actual guest-input intervals at command field F+1 without
shifting rows, and verifies three full canonical party anchors. All four retain
unchanged HP, XP 51/51/51/77, 500 gold each and Recall quantities 1/2/2/2. Mana
regenerates during the hub interval; whole Player-record immutability across that
interval is not claimed. The final
30 neutral fields also have stationary XYZ for all four. Independent acceptance covers this finite software-input hub case; client
acknowledgements and clean exits alone do not qualify it. Earlier evaluator failures remain preserved
with separate reader corrections, without game-data or native-code fixes.

Both trials read 311,272 game-card bytes and write zero. Generated network
bootstrap/address sidefiles are recorded separately from the four seeded game
save/icon files. Original and copied party saves, the earlier 1,888-XP checkpoint,
source inputs and all eight installed programs retain their hashes. The current
installed build remains unchanged; this candidate is neither installed nor
promoted. The strict graphics gap remains open, as do full campaigns, physical
controllers, WAN/NAT, public discovery operation, latency, general performance,
console fidelity and qualification of the Godot bridge.

## Bounded live-input campaign combat

A separate private trial uses the opt-in controller interface for one ordinary
Poison Bolt attempt after the established four-player campaign route. The game
and client both exit zero with 2,001 complete watched rows and no timeout. Its
entire 1,899-row, 338-column route prefix matches exactly: 641,862 values without
shifting or normalization. Fresh state snapshots revalidate the current party,
enemy allocation, handles, grid links, health, facing and range before input.

One Circle request produces seven actual held guest fields. The other three
players retain continuous R1 input through aiming, casting and release. Player
one enters the casting state, spends the source-defined eight mana alongside
regeneration, and starts a cooldown whose first watched value is 30. The same
living Kobold loses 23 HP
with a contemporary damage stamp and a current source handle resolving player
one. Two later one-HP reductions are recorded separately. No projectile was
observed in the sampled snapshots, so its flight and impact path remain unobserved.
The original plan explicitly permits that observation gap; the first independent
evaluator incorrectly made it mandatory and remains preserved with a separate
classification correction. No game or trace rerun replaces that result.

All four raw and decoded controllers become fully neutral and remain so for 63
recorded fields through the closing observation period. Player one then takes
damage during that period: HP falls from 32.800 to 26.667 and finishes at 26.734,
above the predeclared runtime floor of 25. The other three retain their HP.
The enemy survives and XP stays 51/51/51/77; neither a kill nor an XP award is
qualified. Seven full party anchors retain canonical items, equipment and
auxiliary references, skills, statistics, allocations, quests and saved return
metadata. The final anchor precedes the later player hit; final HP is established
by the continuing watched and atomic state records.

Two earlier automation attempts stop before Circle and remain failed. This
revision changes driver scheduling, preserving the same native freshness and
safety deadlines. Game-card traffic is 311,272 bytes read and zero written;
original and copied party files and all eight installed programs retain their
hashes. This accepts only the bounded software-input cast and attributed damage
case. The candidate remains private and uninstalled. Strict default-off graphics
equivalence remains failed, and wider combat, mission and campaign completion,
physical multi-controller play, audio/vibration, WAN/NAT, public discovery,
general performance, console fidelity and the Godot bridge remain open.

## Four-owner live-input battle

A subsequent private trial rotates one ordinary Poison Bolt request through each
of the four characters. Each cast has seven actual held guest fields and fresh
readiness and resource checks. The first three casters return to ordinary guard
before the next cast. The target dies after the fourth cast, followed by release
of all inputs; the optional fifth request is never sent.
The game and client exit zero with 2,089 complete watched rows and no timeout.
The full earlier route prefix remains identical across 641,862 watched values.

Living-target HP reductions of 23, 25, 24 and 26 resolve the four current player
owners in order. Three intervening one-HP reductions resolve player one. Actual
projectiles are sampled for players two, three and four, with current allocation
and owner handles revalidated; player one's projectile remains unsampled. These
observations do not establish every flight or exact impact path. The same target
reaches negative HP and death state, with player four as the current killing
source. XP rises from 51/51/51/77 to 102/102/102/154. A later one-HP corpse change
is recorded separately, with no additional kill or XP award inferred.

All four remain at 32.800 HP throughout the extension. All raw and decoded inputs
become neutral within the declared eight-field deadline and remain neutral
through the final capture and closing observation period. Seven full party
anchors retain canonical items, equipment and auxiliary references, skills,
statistics, allocations and quests, with earned XP reported separately. Gold
stays 500 per player and Recall quantities are unchanged. Game-card traffic is
311,272 bytes read and zero written; the new XP is **unsaved**. Original and copied
party files and all eight installed programs retain their hashes.

Independent raw review qualifies this finite software-controlled four-character
battle. The first author-reader failure, which incorrectly
searched loading fields for death, remains preserved with its post-arm correction.
The candidate remains private and uninstalled. Wider combat, earned checkpoint
durability, NPC/mission and full campaign completion, physical controllers,
audio/vibration, WAN/NAT, public discovery, strict rendering equivalence,
performance and the Godot bridge remain open.

## Earned four-character Save

A later private trial repeats the four-character battle and earned XP, then uses
player two's ordinary Recall control to return the whole party to the hub.
Only that player's Recall quantity falls, from two to one. The game rebuilds all
four current actors before the party walks to the Savepoint. Player one opens
Save and confirms overwriting the copied existing slot. The game and control
client exit zero with 2,943 complete watched rows and no timeout.

The new Save request clears Done, followed by a new Busy/Transfer transaction and
Done. The game remains paused through the captured completion and then returns
to normal play after an ordinary acknowledgement. The complete 310,392-byte
game-built buffer equals the changed copied save file. Its four records contain
XP 102/102/102/154 and Recall quantities 1/1/2/2. Ten full party anchors retain
the declared canonical statistics, skills, quest data, 28 occupied items and 80
equipment/auxiliary references, with the earned XP and consumed Recall reported
explicitly. Saved current hub positions and the four blood1 return positions
are checked separately against the actual actors and source-defined conversion.

Two earlier automation attempts remain failed: the test admitted the hub before
actor reconstruction, then applied an interaction-ready check during Recall's
intentional input lockout. The corrections preserve the original input and
execution limits. The completed run's outer wrapper also retains exit one:
its metadata reader expected LF, while the Windows writer generated CRLF.
Independent offline review checks that exact line ending and all original file
ledger constraints; no game rerun or edited result replaces the original.

This qualifies the bounded software-controlled combat, Recall, hub route and
Save sequence. The new XP is present in the completed copied file; a fresh
frontend Load of that checkpoint remains separate work. Original source saves
and all installed programs retain their hashes. The candidate remains private
and uninstalled, with strict default-off rendering equivalence still failed.

## Fresh Load of the earned four-character Save

A separate private trial starts through the normal frontend Load menu with a
copy of the newly earned four-character save. The game exits zero after 25.98
seconds, with 1,323 complete rows across 321 columns and no timeout.
All four characters retain XP 102/102/102/154 and Recall quantities 1/1/2/2.
The original temporary Load flag is observed and consumed during level entry;
settled readiness then requires four current owners, positive simulation progress
and a fresh rendered scene before the neutral settling period.

Two full RAM anchors retain all 28 occupied items, 80 equipment/auxiliary
references, 48 skill pairs per character, declared statistics, allocations and
quest data after the source-defined save-to-live fixups. The saved current hub
spawn/facing prefixes and the separate blood1 return records are checked
separately. The remaining record differences are confined to mana and the HUD timer, with
source writers identified; whole live-record byte equality is not claimed.

Each owner receives eight actual fields of isolated ordinary movement input,
followed by 30 fields with all 56 raw/decoded control values neutral. Every
commanded character moves, and the last eight whole-party position samples of
each release are stable. Player two still moves about 0.01673 units on the first
neutral field; the report does not claim zero motion throughout all 30 release
fields. No uncommanded character motion is observed in this case, without
qualifying a collision model or a sole cause for carryover motion. The original
author audit and its narrow motion-boundary clarification are both retained.

Game-card traffic is 311,272 bytes read and zero written. The four source game
files and their four copies, installed game files and other protected inputs retain their
hashes; declared host bootstrap metadata is tracked separately. This adds one
fresh software-controlled Load and finite four-owner input/release path. It
does not test mission return or world/enemy reconstruction from this checkpoint.
The candidate remains private and uninstalled, strict default-off rendering
equivalence remains failed, and full campaigns, WAN, physical controllers and
hands-on audio/vibration remain open.

## Return to the mission from the earned Save

A private test with four characters and software inputs completed a fresh Load
of the earned party save, followed by one ordinary eight-field Use+Select
input from player 1 in the hub. Recall returned all four players to the saved
Lost Battleground mission without consuming another potion. XP remained
102/102/102/154, Recall quantities remained 1/1/2/2, and party HP was
unchanged. The process exited normally after 27.738 seconds with 1,416
complete rows across 389 logged columns and no timeout. The final 30-field
capture drain completed at quit callback 1,417; its last field has no recorded
row. The game read 311,272 card bytes and wrote none; the four source files,
four copied save files and protected installed files stayed unchanged.

Both RAM anchors retained the party's canonical state after the source-defined
serialization fixups: all 28 occupied item instances, 80 equipment and
auxiliary references, 48 learned skill pairs per player, stats, allocations,
quests and stored mission-return metadata. Full inverse comparisons of all
four player records at both anchors exposed 40 residual bytes, entirely in
regenerating mana and the HUD spell-selection timer; whole live-record byte
equality is not claimed. Requested return vectors, source entry tables and
settled actor positions were recorded separately. The fourth player's entry
and settled positions differed, so this result does not assert that every
actor returns to an identical saved XYZ.

The two defeated Kobolds in the new save were identified as current allocated,
grid-linked objects after return, using their class, variant, saved
position/facing and state. Both had AI state 20, the required dead flags and
saved death animations. Their negative HP matched the saved signed fraction
multiplied by the current maximum HP using the runtime's round-toward-zero
single-precision arithmetic; exact old battle HP was not assumed. The returned
snapshot's 134 allocated Creature records are a census, not proof that all 261
serialized world objects are equivalent or that the area is safe. Both
captured scenes were inspected and showed the four-player party in the lit hub
and mission.

This is a bounded earned-save Load-and-return result. It adds no quest or
campaign-completion claim. The candidate remains private and uninstalled; the
existing strict rendering difference remains unresolved, and original-hardware
fidelity, physical-controller, WAN, audio and performance coverage are
unchanged.

## NPC-directed automation timing

Pure offline logging fixtures pass 143 checks across 24 groups, covering bounded
queues, record order and failure handling. A later private four-character trial
accepts 13 movement-only requests with eight-field leases; every acknowledgement
reaches the unchanged two-field deadline exactly. The fourteenth request is
rejected one field late, and owned cleanup ends the failed trial.

The audit confirms movement from all four characters and 56 neutral raw/decoded
pad values after the final accepted lease expires. The complete control journal
is drained and closed before the failure signal. No guard or cast input is
accepted, and NPC interaction is not reached. The timing evidence does not
establish a single cause or reliable automation. Original and copied saves and
installed files retain their hashes. The candidate stays private and uninstalled;
strict rendering equivalence, NPC/mission progression and full campaigns remain
unqualified.

## Automation decoding and expiry recognition

Two offline experiments tested how the automation reads captured game state. A
reader with a scalar-value cache preserved results but increased median complete
snapshot decoding time from 7.1179 to 8.7076 ms, so it was rejected. A later reader
with direct scalar access and no cache reduced that component's median from
7.1289 to 5.6543 ms: 1.4746 ms, or 20.68%. It met the predetermined 20% and 1 ms
thresholds, with lower medians in all three comparison passes.

Both versions used the same 15 full snapshots and one compact observation,
including the recorded target selection. Across the six direct-reader comparison
passes, all 96 outputs matched the recorded baseline, and 48 original/candidate
pairs preserved types, dictionary/list order and float bits. All 62 boundary
and error controls also passed. Timing retained all
45 full-snapshot samples per version, alternated which version ran first, and
preceded the primitive tests. This measures automation snapshot construction and
decoding, **not game FPS or the complete controller pipeline**.

A separate observer passed 706 pure checks across 20 groups for recognizing one
exactly matched expired input request. The completed trial's actual closed
journal remained ineligible; healthy open journal states used for positive tests
were explicitly synthetic. Recognition supplies a historical fact, not a retry
or permission to resume input.

These experiments add no fresh native gameplay run or live recovery/deadline
reliability proof. NPC and campaign progression, rendering fidelity, and the
previously stated physical-controller and multiplayer limits are unchanged.

## Bounded four-player spell and potion trial

A subsequent private native trial records 126.075 seconds elapsed, normal exits
from the game and controller process, 7,296 complete field records and no
input-expiry rejection. This adds no live expiry-recovery proof.
The tester records 13 Circle requests and 12 spell-response/guard-restoration
sequences before stopping the active traversal. NPC interaction is not reached.

Per-field observations explain the final response-witness failure. The casting
character is still receiving mana from a potion. Its mana falls from 22.2659568
to 14.3492832 at field 1988, but remains below the tester's original pre-request
mana minus seven only at fields 1988–1989. The actual state replies surrounding
that interval are at 1984 and 1991. The fixed-baseline net-mana test therefore
misses the brief threshold crossing, despite a visible debit in the recorded
fields. This is evidence about the tester's sampling and criterion; it does not
establish projectile impact or a particular damaged enemy.

After input is neutralized, the read-only scheduled tail records nonpositive HP
for each character, followed by a mission reload and a simulation-counter reset.
Card transfer remains idle. The late and terminal captures show four allocated
characters back in the mission corridor. Those captures do not show uninterrupted
survival, and the final world-boundary reason must not erase the earlier cast
witness stop. The run remains a controlled partial, without NPC/quest completion
or a full campaign pass.

Original and copied saves, protected sources and installed files retain their
hashes. The candidate remains private and uninstalled. Rendering fidelity,
performance, physical multiple-controller play and separate-PC Internet
multiplayer remain unqualified.

## Follow-up mana-witness and combat trial

A fresh private native trial with the revised sampled-mana witness completes in
126.450 seconds elapsed, with normal game and controller exits and 7,296 complete
field records. The controller records 32 Circle requests and 32 sampled
spell-response/guard-restoration sequences, with no pending cast. Five sequences
use a greater-than-seven decline from an observed mana peak while the original
pre-request net-mana criterion remains false. These are sampled response witnesses;
they do not establish 32 projectile impacts or 32 defeated enemies.

The tester retains its first active-input stop separately from the later tail
reason: the 32-cast limit is reached at field 3241 with living threats remaining.
The field records show all 56 input values neutral from 3244 through 7296. There
are seven mana-potion presses, no health-potion presses, no Confirm or Use requests
and no input-expiry rejection. This adds no live expiry-recovery proof.

During combat, XP rises to 510/562/588/640; all four characters remain level one.
After input stops, each character later reaches zero HP, with all four nonpositive
from fields 4479 through 4750. At 4751 the recorded XP returns to the loaded
102/102/102/154 values and the player actors clear; the simulation counter resets
on the next field. Card transfer remains idle throughout the post-arm window.
The late and terminal captures show four characters back at the mission entrance.
Their full HP does not establish uninterrupted survival or preserved combat gains.

NPC interaction and quest completion are not reached. The original and copied
saves and checked protected files remain unchanged. The candidate was not
installed. This trial remains a controlled partial; full campaign, rendering,
performance, physical-controller and separate-PC multiplayer qualification
are still open.

## Combat gains written through normal four-player Save

A fresh private native trial completes in 50.377 seconds elapsed, with normal
game and controller exits, 2,747 complete field records and no input-expiry
rejection. Four Circle requests have four sampled spell-response and guard
restoration sequences. XP increases from 102/102/102/154 to 153/153/179/205.
These observations do not attribute a particular projectile impact or XP award.

The field records show positive HP for every character throughout the post-arm
window. P2 uses one ordinary Recall potion, reducing its typed bag2 quantity from
two to one. The party returns collectively to the hub. During the ordinary
loading interval actor pointers clear, the local-player count falls to zero and
the simulation counter resets; earned XP and positive persistent HP remain
intact, and the Load flag stays inactive.

The new Save transaction starts with Done cleared, then records Busy/Xfer and a
new Done state before acknowledgement. The game writes exactly 310,392 bytes.
The private cloned slot and captured game-built buffer match byte for byte;
the tester also compares all four saved-player records, dynamically occupied
inventory items and equipment references. It checks saved positions against
current actors and confirms stored return metadata is retained.
The completed file contains the new XP values and Recall quantities 1/1/1/2.

The game returns to the hub with card transfer idle. All 56 input values are
neutral from fields 2681 through 2747. Original source saves, cloned header/icon
files and checked protected files retain their hashes; the single private clone
slot is the intended game-written exception. The candidate remains uninstalled.

An offline check against preserved captures first exposed an overly strict tester
camera guard: paused Save UI normally disables camera control. The corrected
phase-specific guard passes 51 offline checks while ordinary movement continues
to require active camera control. Those checks are separate from this native run.

An independent read of the completed raw recording passes 40 bounded checks,
including accepted input timing, requested-zero input values, Recall consumption
and Save serialization. It checks the stated owner/input/Save subsets; it does
not replay every strategy predicate or qualify nonzero analog mapping, unique
hit attribution or the origin of the retained return positions.

A separate fresh Load of this new save remains pending. This does not qualify
NPC/mission completion, a full campaign,
rendering fidelity, performance, physical multi-controller play or separate-PC
multiplayer.

## Separate fresh Load of the earned four-player checkpoint

A separate private native process finishes the scripted frontend Load and four
movement/release run in 26.002 seconds elapsed. It records 1,323 complete
474-column fields and exits normally. Native card traffic is 311,272 bytes read
and zero written. Original and copied game files, protected sources and the
candidate retain their hashes.

The loaded four-character party retains the newly earned XP values
153/153/179/205. While the Load flag is active at fields 911–977, every recorded
HP and mana value matches the corresponding saved float bits for all four
characters. The flag clears at 978 with start rank three. At both RAM captures,
the restored records match all occupied
72-byte items across all three bags, all 20 equipment/auxiliary references,
stored skill/ability and binding bytes, and the retained 44-byte return metadata.
The saved 14-byte facing/position entries also match their load-entry tables;
actual settled actor positions are reported separately.

The full record comparison preserves every difference. Each character has eight
changed bytes at each capture, all within current mana, the new actor pointer
and the HUD selector float counter. Source review identifies the normal mana
update, constructor assignment and HUD decrement writers. Exact per-call mana
arithmetic and the unique intervening HUD call history remain unqualified.

An independent raw reader passes 30 checks, including four current allocated
player owners and reciprocal grid handles at both captures. The recorded input
contains one eight-field movement hold for each character, with 30 neutral fields
after each hold. Nonselected controls remain neutral during each hold. All 56
input values are neutral during each release, and all four actors' XYZ values
are stable over its final eight fields. Root viewed both captures: four living
characters are visible at the hub savepoint before and after these movements.
This qualifies the bounded fresh Load and software-controlled movement/release
test for this checkpoint.

The candidate remains private and uninstalled. Full campaign and NPC/quest
completion, stored mission return from this new checkpoint, console-reference
fidelity, performance, physical multiple-controller play and separate-PC
multiplayer remain open.

## Normal mission return from the earned checkpoint

A new private native process completes a normal frontend Load, free hub Recall
and collective return to blood1 (Lost Battleground) in 27.472 seconds. It records
1,416 complete 474-column fields and exits normally without a timeout. Card
traffic is 311,272 bytes read and zero written. Original and copied game files,
protected sources and the candidate retain their hashes.

Player zero holds the ordinary Square+Select Recall chord for eight fields;
the other players' controls remain neutral. The recording observes a positive
hub Recall countdown, the pending mission and all four requested positions
matching their own saved return metadata, followed by the active mission and
released controls. Recall quantities remain 1/1/1/2. Actual settled positions
are recorded separately from the requested positions.

At both captures, all four characters retain XP 153/153/179/205, all occupied
inventory items, all 20 equipment/auxiliary references, stored skills and
ability/binding bytes, and the 44-byte return metadata. Every complete-record
difference remains in the private audit. Current mana, constructor actor pointers
and the HUD float counter change during normal updates. Player zero also loses
health after the mission resumes, reaching 29.705715 at the returned capture
and 26.734173 at the final recorded field; all four characters remain alive.
Exact attacker attribution remains unqualified.
Root viewed both captures: the four-character party at the hub savepoint and
then in Lost Battleground.

An independent object reader resolves four current allocated Player owners with
reciprocal grid handles at both captures. The three selected saved defeated
Kobolds each resolve to a unique current allocated object with exact saved
position, facing and variant. Each has nonpositive HP matching the guest
round-toward-zero product of its saved fraction and observed current maximum HP,
AI state 20, the expected frozen death-animation clip and reciprocal grid
membership. This is bounded endpoint evidence for those three creatures;
complete reconstruction of all saved object classes remains unqualified.

This qualifies normal stored mission return for this earned checkpoint. The
candidate remains private and uninstalled. NPC/quest completion, full campaign,
console-reference fidelity, performance, physical multiple-controller play and
separate-PC multiplayer remain open.

## North-route combat before the first story dialogue

One new private four-character attempt completes normal Load and stored mission
return, then advances north through combat. Both the native application and its
input driver exit zero. The run retains 7,296 complete 474-column fields over
127.512 seconds, with no timeout. Card traffic is 311,272 bytes read and zero
written. Source and copied game files, protected sources and the private
candidate retain their hashes.

The party starts with XP 153/153/179/205. At field 3,297, all four characters have
32.799995 HP and XP 510/562/614/614, with each more than 800 world units north of
its position when live input was armed. The controller reaches its declared
32-cast limit while living threats remain. All 32 accepted spell inputs have
watched cast-animation and mana-decrease witnesses before their recorded response
windows close. These are bounded input/resource observations; individual target
hits and kill attribution are not qualified by this audit.

The independent control reader verifies digital control timing, required neutral
values and inclusive input leases in its declared subset. Two expired requests
are rejected; each is followed by
a current full neutral observation and a later distinct source observation before
new input. The first evaluator incorrectly overwrote its earliest neutral
witness and reused a session/ID pair that collided after rejection. Its result
is retained. A corrected reader checks the same original recording using unique
request sequences and preserves all failed story predicates.

No dialogue choice or Save occurs. Gameplay input ends at the cast limit, and
the scheduled neutral observation period continues. Player deaths occur in that
later interval; both late RAM captures contain the original saved XP values.
The unsaved combat gains therefore do not establish a new durable checkpoint.
Root viewed all four captured images: the hub, initial mission return, and two
later mission views with empty or partly filled health bars and nearby enemies.

Natasla dialogue, the Good decision, its cutscene and mission completion remain
unqualified. Source analysis distinguishes the Good dialogue action and door
cutscene from the separate mission-completion state; an observed dialogue choice
would require its own progression and persistence checks. The next planned
attempt will try to preserve earned route progress through an ordinary hub Recall and
normal four-player Save, followed by separate fresh Load/return verification.
The candidate remains private and uninstalled; full campaign, fidelity,
performance, physical multiple-controller play and separate-PC multiplayer remain
open.


## North-route movement stall before a new checkpoint

A new private four-character attempt reaches normal application and controller
exits after ordinary Load, stored mission return, combat and northward movement.
The controller ends gameplay input at its declared traversal no-progress limit.
Recorded positions stop changing despite continuing movement inputs for two
characters; the other two receive neutral movement inputs. This is a bounded
controller outcome, not an established game defect. The precise cause of the
stall remains unqualified.

The late captures retain four living characters with XP 536/536/640/588. No new
Recall or Save transaction occurs. Card traffic is 311,272 bytes read and zero
written, and the cloned slot remains unchanged. These gains therefore do not
establish a new durable checkpoint; the previously verified saved XP remains
153/153/179/205. Original source saves, cloned game files, protected sources and
the candidate retain their hashes.

The candidate remains private and uninstalled. Continued progress through normal
Save and separate fresh Load/return, Natasla dialogue, mission and full-campaign
completion, physical multi-controller play, reference fidelity and separate-
PC/WAN multiplayer remain open.

## Route advance and Recall readiness boundary

A new private four-character trial advances beyond the corner where the previous
route attempt stalled. The recorded route diagnostics and measured positions
agree at the later waypoint observation. At the checkpoint handoff, all four
characters are alive with XP 536/510/666/588. An independent offline reader
verifies 32 accepted cast inputs with observed animation and mana responses,
guard restoration before handoff, and the declared control-timing subset. Unique
target hits, kills and awards remain unqualified.

The controller stops before sending Recall because the selected character is
still blocking. All raw and decoded controls are neutral by field 3,156, but the
fourth character (P3) remains in state 8 with blocking set through 3,164. It
reaches state 2 with blocking clear at 3,165, five fields after the readiness
check stopped the action phase. A bounded wait for observed actor readiness is
the next controller change; the ordinary pulse still requires its own fresh
admission.

No new Save occurs. Native card traffic is 311,272 bytes read and zero written,
and the cloned slot remains unchanged. The scheduled neutral observation period
later records character deaths and a return to the original saved XP
153/153/179/205. These observations do not establish the cause of those deaths
or a new durable checkpoint. The candidate remains private and uninstalled;
fresh persistence, Natasla dialogue, mission and full-campaign completion,
physical multi-controller play, reference fidelity and multiplayer between
separate PCs or over the internet remain open.

## Earned route progress written before Save acknowledgement

A new private four-character attempt completes the neutral-to-idle handoff and
uses ordinary Recall to return collectively to the hub. The normal occupied-slot
Save writes 310,392 bytes; native card traffic records 311,392 bytes read. The
written private slot and captured game-built buffer match, containing XP
536/562/614/588. Original source saves and cloned header/icon files retain their
hashes.

The controller stops at its reserved action-read allowance while waiting in the
paused Save capture phase. It has used 772 of the 900 total reads, preserving
the separate terminal allowance. The scheduled captures occur later, still
showing the paused player-zero Save screen with Done set and neutral controls.
Root viewed both late images, which display Overwrite Successful. No
Continue/acknowledgement input follows, so the complete Save flow and return to
ordinary idle remain unqualified.

At both late captures, all four saved-player records equal their buffer records,
and the checked direct-copy ranges, current actor facing/position entries and
retained return metadata match. Each inverse comparison with the later live
record retains two differing bytes within the HUD field. Those
differences remain recorded; this is not whole-record equality or proof of the
exact intervening update history.

The written slot is accepted as input for a separate normal frontend Load test.
Restoration and durability of this new progress remain pending that test. The
candidate remains private and uninstalled; Natasla dialogue, mission and
full-campaign completion, reference fidelity, physical multi-controller play and
separate-PC/WAN multiplayer remain open.

## Earned route progress persists through a fresh normal Load

A single fresh-process normal frontend Load restores the newly written private
checkpoint in the hub with four living characters. The first observed HP, mana
and XP match the saved bits; XP is 536/562/614/588, with one Recall scroll each.
The attempt exits normally after 23.3 seconds and 1,171 complete telemetry rows,
recording 311,272 bytes read and no card writes. Original saves, the written
input, copied files and protected files retain their hashes.

The independent audit passes 40 checks, including current allocated owners,
reciprocal handle/grid links, occupied inventory items, all 20 references per
player, skills, bindings and return data at two neutral hub observations. All
eight differing bytes per player at each observation remain recorded and
source-accounted within mana, the recreated actor pointer and the HUD field. No
generic mask or whole live-record equality is used; exact regeneration and HUD
call histories remain unqualified. Both images show the living party in the hub.

Root accepts bounded fresh Load and persistence of this checkpoint's earned XP.
The first offline audit failure remains preserved; a one-line correction
accounts for the unsampled final quit callback, without rerunning the native
attempt. The preceding Save's Continue/acknowledgement and complete Save flow
remain unqualified. Stored mission return, Natasla dialogue,
mission/full-campaign completion, reference fidelity, physical multi-controller
play and separate-PC/WAN multiplayer remain open; the candidate stays private
and uninstalled.

## Earned checkpoint returns to the northern mission area

A single private process uses the normal frontend to Load the earned checkpoint,
then one ordinary eight-field player-zero Square+Select chord to return
collectively from the hub to the stored mission. The run exits normally; its
wrapper records 27.654 seconds and 1,416 complete telemetry rows with 474
columns. XP remains 536/562/614/588, and each character retains one Recall
scroll at both captures. Recall from the hub is free. Card traffic records
311,272 bytes read and no writes; source saves, private copies and protected
files retain their hashes.

Independent checks establish current allocated owners and reciprocal links at
both captures, retained checked party data and all ten supported saved defeated
Kobold endpoints. Each endpoint is matched individually against current
identity, health, death state and animation; this does not qualify every
saved-world class or complete world reconstruction. All four requested
destinations match their own stored return data. Final follower positions differ
from those requests and are preserved separately, consistent with the source's
secondary-placement and terrain steps; exact placement replay remains
unqualified.

All 64 differing record-byte occurrences remain recorded and source-accounted
within mana, recreated actor pointers and the HUD counter. Whole live-record
equality and exact regeneration or HUD call histories are not claimed. Controls
are neutral after the chord's release. P3's HP drops after the returned-mission
capture, with the exact attacker unqualified; all four characters remain alive
at termination.

Root accepts this bounded stored return and the ten supported defeated-enemy
endpoints. The preceding Save's Continue/acknowledgement and complete Save flow
remain unqualified. Continuing north toward Natasla, story and mission
completion, the full campaign, reference fidelity, physical multi-controller
play and separate-PC/WAN multiplayer remain open. Strict default-off visual
equivalence remains false, and the candidate stays private and uninstalled.

## Northern continuation stops at the fresh-position guard

One private normal Load and free hub return completes before the next route
attempt. The native process and control client exit normally, with 7,296
complete 480-column telemetry rows. The wrapper records 127.317 seconds
including postprocessing; this is not a performance benchmark. Card traffic is
311,272 bytes read and zero written. All four source save files and all four
private copies retain their hashes, together with the protected files and
candidate.

The actual full reply at field 1,423 establishes four living current owners in
the expected world. Recomputing the route-entry projection from that reply
places P3 32.423332 units laterally from the reviewed incoming leg, beyond the
test's 32-unit limit. The other three owners satisfy the check. The driver stops
before movement, combat or dialogue input. The raw journal contains 112 read
requests, one neutral request and one cancel request; there are no ordinary pad
requests. All 56 pad scalars remain neutral in every one of the 5,871 sampled
native fields from cancel through the final trace row.

The fixed diagnostic schedule continues unpaused after this early stop.
Nonpositive health is subsequently observed, and the late image shows fallen
characters with enemies nearby. The exact attacker and movement cause remain
unqualified. Capture filenames do not establish a dialogue or pause state.

This is a completed bounded partial attempt, with no new route, story, pause,
mission or durability qualification. The next test needs a reviewed connector
from each freshly observed owner position and a purpose-specific normal pause on
an early controlled stop when a living ordinary-world source can be proved.
Existing intermediate waypoint bounds and global quotas remain in force. The
accepted earned checkpoint remains the preceding Load/return checkpoint; full
campaign, reference fidelity, physical multi-controller and separate-PC/WAN
qualification remain open. The candidate stays private and uninstalled.

## Fresh-position continuation reaches a later passage stall

**Ran on Windows, 2026-10-22:** one new bounded continuation used a normal Load
and free hub Recall from the same accepted northern checkpoint. The native
application and its sole control client exited normally. The run produced 7,296
complete 480-column native rows, all offline, in 127.129 seconds including
wrapper and postprocessing work; that elapsed time is not an FPS measurement.
Native game-card traffic was 311,272 bytes read and zero written. All four
original save files, all four case copies, the installed build and the protected
source inputs remained unchanged.

Root recomputed the four fresh route origins from the complete raw reply at
field 1425. Each origin is uncommanded context; the first target remains the
existing northern waypoint. This passed the previous entry-position stop without
widening the existing waypoint tolerances. The raw journal contains 209 accepted
ordinary pad requests, with correlated session/IDs and source-plus-two
deadlines; there were no expiry rejections, Confirm, Use or Start requests. Full
per-field control-lease and cast-response replay remain unqualified.

Independent decoding of complete raw replies at fields 1425 and 2881 established
the current allocated four-owner party and its handle/grid links at those two
anchors. XP changed from `[536,562,614,588]` to `[790,944,868,842]`. These are
in-session gains only: no Save was attempted and no new durable checkpoint
exists. All four persistent HP values remained positive from field 1425 through
the last native row. After the final neutral/cancel at field 2884, all 56
watched raw and decoded pad cells were neutral in every one of the remaining
4,413 rows.

The route-progress metric stopped the attempt at field 2881, 247 fields after
its last qualifying progress. A late image shows the living party clustered in a
narrow rocky passage near a barrel. The exact cause remains unknown: waypoint
corner acceptance, party congestion, terrain/object collision and screen limits
need further checks. The original partial reason remained intact through the
read-only tail. Protective pause was ineligible after gameplay inputs, so no
pause attempt or pause qualification is claimed.

The next work is a source-guided check of passage geometry, party collision and
nearby interaction semantics before another ordinary-control attempt. The
accepted saved seed remains unchanged. Natasla dialogue, full Save
acknowledgement, mission completion, the full campaign, reference
fidelity/performance, physical four-pad play and separate-PC/WAN play remain
open. The diagnostic candidate remains private and uninstalled.

## Expanded diagnostic snapshot stops at input expiry

**Ran on Windows, 2026-10-22:** one new private continuation tested a larger
read-only diagnostic snapshot covering all three allocation pools, handles and
grid links. Its native atomic read limit is 1.5 MiB, while the existing request
deadlines, input guards and global quotas remain unchanged. Separate CPU and
synthetic component checks passed before this run; they do not establish live
input timing or gameplay correctness. The candidate remains private and
uninstalled.

Normal Load and the free hub return completed from the accepted checkpoint.
Eight complete replies contained approximately 1.24 million bytes each in 27 to
30 spans. Root decoded the current four-owner party and complete object census
at two actual reply anchors, fields 1427 and 1446. These two anchors establish
snapshot readability at those points.

Both ordinary control requests expired before acceptance. Their source fields
were 1431 and 1446, deadlines 1433 and 1448, and rejection fields 1434 and 1449.
The driver stopped at its two-consecutive-expiry boundary. There were no
accepted ordinary pad requests, passage overrides, route observations, Confirm,
Use or Start requests. This attempt did not exercise passage prevention or add
campaign coverage. The precise timing bottleneck remains unknown.

The native application and control client exited normally after the fixed
diagnostic tail. The trace contains 7296 complete offline rows with 480 columns.
All 56 watched raw and decoded pad cells remained neutral throughout the armed
period, including all 5846 rows from cancel through the final trace row.
Nonpositive health was subsequently observed during the unpaused tail; the
original expiry partial remains distinct from that later outcome. Full
recovery-barrier and control-lease replay remain unqualified.

Game-card traffic was 311272 bytes read and zero written. The four original save
files, four private copies, installed build and protected inputs remained
unchanged. No new checkpoint or durable progress was created. The next step is
to measure the diagnostic read, decode, decision and send path before another
bounded attempt, preserving the existing deadlines. Passage traversal, Natasla
dialogue, full Save acknowledgement, campaign completion, reference fidelity and
performance, physical multiplayer and separate-PC/WAN multiplayer remain open.

## Snapshot decoding improvement does not resolve live input expiry

**Ran on Windows, 2026-10-22:** one private continuation used optimized snapshot
decoding and control-reply parsing while retaining the same gameplay driver,
complete atomic snapshots, request deadlines and input guards. Before launch,
183 synthetic equivalence checks passed and eight complete replies from the
preceding closed run produced identical decoded outputs. Separate warmed offline
measurements reduced complete snapshot decoding time by approximately 14
percent. Those measurements do not establish live input acceptance or game
performance.

Normal Load and the free hub return again completed from the accepted
checkpoint. The live run still rejected both ordinary control requests as
expired: source fields 1428 and 1442, deadlines 1430 and 1444, and rejection
fields 1431 and 1445. No ordinary pad request was accepted. The driver stopped
at its two-consecutive-expiry boundary; its route and passage diagnostic
observation counts remained zero, and it submitted no dialogue input or pause
request. The optimization was insufficient to resolve this live timing failure;
it added no campaign progression coverage.

The native application and control client exited normally. The trace contains
7296 complete offline-mode rows with 480 columns. All 56 watched raw and decoded
pad cells remained neutral throughout the armed period; nonpositive health was
subsequently observed during the unpaused diagnostic tail. This later outcome is
distinct from the initial input-expiry stop. Game-card traffic was 311272 bytes
read and zero written; the four accepted checkpoint source files, four private
copies, installed build and protected inputs remained unchanged. No new
checkpoint was created, and the previously accepted earned-progress checkpoint
remains the saved baseline. The candidate remains private and uninstalled.

The next step is to measure the remaining snapshot, decision, transport and
native input-processing latency before another campaign continuation. Full story
and campaign progression, complete Save acknowledgement, reference fidelity and
performance, physical multiplayer sessions and Windows separate-PC/WAN
qualification remain open. Earlier one-PC network and separate-camera results
remain valid within their recorded build and test scope.

## Remaining qualification

A full good/evil campaign, all quests, difficulties, item combinations and every
skill rank have not been completed. Rendering captures establish only the scenes
actually observed; a destination request is not a normal mission transition.
Cross-machine/WAN multiplayer, wider four-player combat and campaign save/load,
mission progression/completion, local physical multi-controller play, device disconnects
during physical gameplay and hands-on audio/vibration quality remain separate work.
The existing Godot bridge has not been qualified by these standalone-native tests.
