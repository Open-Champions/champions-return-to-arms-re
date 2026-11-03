# Mission 2: second offer, story request and bounded hub return

2026-11-02. **STATUS: MORE.** Research in `t3/research-mission2-route`.
The five interrupted files at base `67d6d24` were reviewed and retained in
`6666b9a` / `87c3e83` after rerunning both seeds and the full analysis suite.
There was no `work/cursor-report.md`; the earlier notes and logs were present.
This continuation adds tests without changing existing reference APIs/vectors.

**Evidence convention:** Observed below includes **Executed** original EE
instructions on constructed state. It does not mean a running game. Native
addresses refer to the hash-checked US v2.00 executable; script offsets are
code-relative to the named level. Private disc data is read at runtime only.

## Second offer after mission 1

**Observed:** ordinary hub object 10 is an NPC whose dialog property names
entry `0x000`; native-command cell `0x03c` requests the dialog resource.
The resource selected by the earlier unlock harness equals that requested
resource. The new test uses its actual resource identity and authored controls
for original `dialog_onMsg` `0x22ee2c` / `dialog_show` `0x230c74`, with a
synthetic speaker and controlled resource return. Dialog node 7 has predicate
`0x734` and two unconditional choices calling `0x7b0` / `0x2064`, both closing.
Evidence: [input binding, lines 45–89](../tools/difftest_mission2_offer.py#L45-L89).
NPC use, resource I/O and message production are **Unknown** here.

**Observed / Executed:** with later missions unavailable, zero/absent quest
variables, ordinary alignment/decision, and mission 2 byte 0 or 2, the original
selector chooses node 1 for mission 1 byte 0/2, node 3 for byte 1, and node 7
for byte 3. Opening writes no availability. At node 7 either choice invokes
`mission_setAvailable` `0x1bf6d0` with `(difficulty,2,1)`. Only bit 0 of mission
2 in the one configured player's current difficulty row changes; all four full player
records are checked. The existing completion bit survives, including the
synthetic byte-2-to-3 control. All five difficulties and both choices run.
Evidence: [80 selectors per seed, lines 162–187](../tools/difftest_mission2_offer.py#L162-L187).

**Inferred, bounded:** mission 1's available-and-complete state permits the
second offer through the tested dialog's priority rules, but completion alone
does not set mission 2 availability. This is not a universal prerequisite
formula: the local predicate `0x734` checks mission 2 availability, while earlier
nodes can take priority. The pinned unlock research `950b2538` documents its
separate active-variable matrix; this continuation uses zero/absent variables.
Actual mission 1 completion and return, alternative hub dialog, active-variable
warning flows and a full campaign prerequisite graph remain **Unknown** here.

## Offer state to the original mission menu

**Observed:** hub PushTrigger record 11 has one action entry `0x054` and one
key entry `0x098`. **Executed:** the original key runs; original object action
dispatcher `0x14dcc8` reads that record's properties and invokes its wrapper.
With mission 1 byte 3 and mission 2 byte 1, the key returns 1; the action
reaches `setEntrance` at script cell `0x4a44`, `activateMissionMenu` at
`0x4a68` / native `0x143fa8`, then original menu setup `0x231520` and task
registration `0x19e4a0`. The entrance string comes from the private script.
Busy-dialog and recall controls prevent menu registration. These calls are
explicit harness orchestration; Player proximity/use remains **Unknown**.
Evidence: [dispatch and controls, lines 97–137](../tools/difftest_mission2_offer.py#L97-L137),
[negative controls, lines 188–194](../tools/difftest_mission2_offer.py#L188-L194).

**Observed / Executed:** `missionMenu_run` `0x2316fc` automatically selects
row 1, story column 0, after the offer makes mission 2 available/incomplete.
The row's pointer is at `0x4fe540 + 0x34 + 8`. Confirm and controlled fade
advance to the pending write at `0x232220`, yielding `innovat1` at `0x41b6d0`
and orientation 255 at `0x41b720`. Nine menu fields, all player bytes and the
shared RNG are compared after each tick. There are 390 snapshots per seed.
Evidence: [menu comparisons, lines 138–158](../tools/difftest_mission2_offer.py#L138-L158),
[bounded independent model](../tools/ref_mission2_offer.py#L16-L39).

**Observed controls:** mission 1 complete plus mission 2 byte 0 yields key 0.
An independently forced menu and row-1 confirm remain in selection and make no
pending request. Mission 2 byte 2 becomes 3 after either offer choice; its key
also returns 0 in this otherwise-empty state, so the harness does not dispatch
the action. Do not infer a usable trigger solely from an availability write.

**Unknown integration boundary:** the dialog and menu machines receive identical
player bytes through an explicit fixture transfer. Dialog closure is a controlled
service answer, and quest variables begin absent again on the menu side. This
is not continuous world/script state, dialog animation, a scheduler loop or a
loaded transition. UI/audio/resource calls and unnamed menu setup helper
`0x18ebb8` are explicitly stubbed; unexpected implicit stubs fail. No claim is
made about that helper's effects. Full loading remains bounded as described in
[the retained route handoff](mission2-route.md#portal-request-and-the-remaining-load-boundary).

## Final portal and hub return request

**Observed / Executed:** original `game_getHubName` `0x1ec300`, including
`0x1bf8d8`, `0x1bf960` and `0x1bf730`, returns `hub2` only when the current
row's evil and decision bits are set and mission 1 is complete; otherwise
`hub`. Tests cross both bits, both missions' completion bits, the portal gate,
and difficulties 0/4: 64 cases per seed. Both missions start available.
Evidence: [resolver controls, lines 22–48](../tools/difftest_mission2_hub_return.py#L22-L48).

**Observed / Executed:** with that hub name **explicitly registered by the
fixture** in the destination list, final-level Portal record 57 runs its real
predicate entry `0x110` / `getv` call `0x13c`, native prompt `0x27d7a0`,
interaction `0x27d754` and menu `0x27dd74`. Gate 0 refuses even with mission 2
complete. Gate 1 permits a selected hub request even with mission 2 incomplete.
It writes the selected name and orientation 255 after input counter 181, leaves
all four player records and RNG unchanged, and removes its tasks. The 5,792
counter comparisons per seed use the unchanged travel reference.
Evidence: [prompt, menu and preservation, lines 49–98](../tools/difftest_mission2_hub_return.py#L49-L98).

**Inferred, bounded:** the tested final portal is a travel gate separate from
mission-2 completion. Boss death opens it before actual item pickup is established;
turn-in and deferred `grantMission(2)` are separate executed paths in
[the route handoff](mission2-route.md#deferred-completion-and-auxiliary-branches).
This test does not call the hub resolver to choose its destination; the harness
registers and selects that row.

The [route-list continuation](mission2-compose.md) executes
`jumpgate_resetDestinations` `0x27db00` and `jumpgate_addCurrentLevel`
`0x27db60` instead of planting the hub name. With the card latch clear, reset
stores the resolver hub, and arrival at the four route levels leaves that hub
at row 0. The same final portal, given that list, writes the hub request, and
the retained pre-load stop accepts it. Physical navigation, the loader body,
arrival, and saving the list remain **Unknown**. No return-to-hub completion
or playable mission claim is made.

## Reproduction and client handoff

Run from this worktree with private inputs in ignored `local/`:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_offer.py",run_name="__main__")' local/SLUS_209.73 local/disc.iso --seed 20973
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_hub_return.py",run_name="__main__")' local/SLUS_209.73 local --seed 20973
python3 -m unittest discover -s tools -p 'test_*.py'
```

Results: both seeds PASS (80 selectors, three trigger suppressors, 390 menu
snapshots, 64 hub-return controls and 5,792 counter comparisons per seed);
680 analysis tests PASS. The recovered route/dialog/travel difftests and 222
private malformed-input controls also PASS; exact commands are in
`work/cursor-report.md` and logs remain under `local/`. No pictures were generated.

Repeat both difftests with seed 7. The offer test reads existing models/harnesses
from immutable local Git objects `950b2538ef8f1cb4f5ad26cf3f88fd502c0184f6`,
`76d4447c8e372f5e7e662edb267e0dcd51f13279` and transitive dialog pin
`334578d310179760daff20ea6098353a54958df8`. Missing dependencies fail; no fetch
is attempted. Existing APIs and test vectors remain unchanged.

Client implementation order: preserve the addressed dialog selection and choice
writes, bind the real interaction and close event, preserve full script/player
state into the trigger, compare menu request, then verify loading/arrival. Use
the retained objective/deferred/death contracts for mission 2. Actual inventory,
physical interactions, full transitions and save/load still need original/native
comparisons before a playable second-offer journey can be claimed.
