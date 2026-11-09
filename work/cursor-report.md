STATUS: COMPLETE (audit FIX round for research-hub-services: HSV-1..HSV-9 addressed)

# research-hub-npcs, round 4 (2026-11-09), with the audit fix round

Branch `t3/research-hub-npcs`, from tip `31db144`. Work and runs were on the Mac
mini worktree, and the commits were fast-forwarded to the MacBook worktree.
Deliverable: `docs/hub-services.md`.

## Documented (Executed in tools/ee_emu.py at seeds 20973 and 7)

- Every hub and hub2 object a player can use between missions: the NPC
  (mission giver and vendor), the store, the mission-map PushTrigger, the walk-in
  Trigger, the ring props, the jump gate, the save point, and the hub-entry
  services. Trainer, bank, stash, healer and ambient talkers are absent
  (census, plus a no-fee/heal/train/gold native assertion).
- Both NPC dialogs, all 31 + 26 nodes and 54 + 48 choices. The node and choice
  conditions are 4,600 + 4,416 original predicate results per seed, equal to the
  model. All 22 + 19 dialog actions and 17 + 13 unreferenced writers ran with
  recorded writes: mission bit, quest pair, variable and deferred store request,
  and nothing else. Every native they executed is in {setMissionAvailable,
  addQuest, setv, changeSwoop, activateStore}. 76 + 90 whole conversations per
  seed ran through the original `dialog_onMsg` (pinned `2ab82b2` Probe), with
  start node, visible choices, actions, mission writes and quest count checked at
  every step.
- No dialog choice takes an item. **Observed** (static): following every
  literal callScript/addDeferedCall/postAction and every internal call from the
  live dialog's entries reaches no item or gold native. The 19
  `removePlayerItem` sites per hub are 17 in `start` plus 1 + 1 in the two
  deferred checks, and the dialog reaches none of those entries. **Executed:**
  with an item planted as found in every action run and every conversation, no
  inventory stub is called.
- In-dialog store deferral, **Executed with the real `dialog_isOpen` 0x22fbc0**
  (the Rig's stub hook was removed; 38 + 45 store actions per seed;
  `g_dialogData` planted 0 before each open and non-zero after it). Opening at
  dialog end is Observed (`docs/dialog.md` `79a2e4a` line 273), not executed.
- Hub entry `start`, 148 cases per hub per seed: entry mission bits, save
  inhibit, the vendor store-level rule (this resolves vendor-stock's two
  "non-literal" stores: both are current − 1), flag 4, mana restore, 17-site
  quest-item cleanup, first-mission help, ring state. The deferred duplicate
  checks' tables have 10 and 13 cells (bounds checks 0..9 and 0..12, asserted
  from the bytecode). The executed loops visit only 9 and 12 cells.
- PushTrigger key, use and walk-in, 601 cases per hub per seed. nethostonly=1
  and radius 79 (hub) / 78 (hub2) are asserted. The key reads only A(12) for
  mission 12. Use with a started incomplete mission shows a help box and queues
  `K.poll`. **Correction from the first round:** the warning does not cancel the
  menu. `K.poll` re-queues itself, counts unpaused runs, and calls
  `activateMissionMenu` on the 6th, with no entrance write. It ran 162 (hub) and
  192 (hub2) sequences per seed. Without a warning, use writes the entrance and
  opens the menu unless a dialog or recall blocks it. The walk-in fires
  `trigger(ring name, 0)` once.
- The only other writer of the mana flag (`L-INN`, private name in local/) was
  found by a census of all 118 script lumps, and its store was executed. The
  restore is free on hub return; it is not a paid inn. Its script imports
  checkPlayerGold/givePlayerGold/takePlayerGold; their use is Unknown.

## Audit findings and what changed

- HSV-1: static reach plus executed native lists, a planted item, and the 19
  sites asserted per owner (`d41c780`, doc `c2c7b11`).
- HSV-2: the stub hook was removed, so the real function runs. The forced answer
  and the seed-20973 sentence are gone. The citations are pinned.
- HSV-3: table sizes asserted from the bounds checks.
- HSV-4: the deferred call target and the K.poll behaviour are executed, and the
  trigger arguments asserted. The doc's "no menu" was wrong and is corrected.
- HSV-5: radius/nethostonly, K.* callees (K.warn is an internal call, not
  callScript; K.help/K.poll added) and the cutscene line-list shape (plus its
  stem in public 0x34a4) are asserted and printed.
- HSV-6: `require(unused <= in_backup)`.
- HSV-7: census keyed by (archive, lump), with every script scanned. The
  "wagers" sentence was replaced by the observed gold imports, use Unknown.
- HSV-8: `docs/dialog.md` citations pinned to `79a2e4a`.
- HSV-9: the machine path was removed from this report.

## Partial / cited, not re-run

Jump gate (`t3/research-exits-walkin` `95760d9`), save screen
(`t3/research-save-screen` `c8895e2`), store contents and prices
(`t3/research-vendor-stock` `fdf6752`), mission menu after confirm
(`t3/research-story-route-r3` `3c7987c`), dialog suppressors and menu task
lifetime (`t3/research-mission-unlocks` `2ab82b2`), dialog end message 3
(`t3/research-dialog-gaps` `79a2e4a`). Line ranges are in the doc.

## Unknown

Live proximity/use of these objects; text, voice and camera pixels; how
`L-INN` is reached and what its gold natives do; the caller of the hub
cutscene entry `0x34a4`; whether the help box pauses the game; several queued
`K.poll` copies; the stack-read store index of the backup-only writers; the
real bag cell `removePlayerItem` removes; any native-client behaviour.

## Commits

- `ab7bfaa` model + synthetic tests (`tools/ref_hub_services.py`, `tools/test_ref_hub_services.py`)
- `b8ff840` difftest (`tools/difftest_hub_services.py`)
- `08b090a` `docs/hub-services.md`, follow-up note in `docs/spec/hub-npc-services.md`
- `bbbeca3` reproduction-command fix in the doc
- `40ba4a9` first report
- `d41c780` fix round: difftest assertions, `ref_hub_services.warn_poll_call` (added) and its unit test
- `c2c7b11` fix round: doc
- this report (final SHA in the log headers, the reply and the COORDINATION line)

## Tests (mini, after the final edit)

All runs at the report commit, single process, `PYTHONDONTWRITEBYTECODE=1`, from the
worktree root. `<disc>` is the mini's read-only `private-validation/rta-disc`. Each
retained log starts with the HEAD it ran on and the SHA-256 of
`tools/difftest_hub_services.py` and `tools/ref_hub_services.py`.

```sh
python3 -c 'import dis,runpy,sys; sys.argv=["difftest_hub_services.py","--elf","local/SLUS_209.73","--data","<disc>/BG/DATA"]; runpy.run_path("tools/difftest_hub_services.py", run_name="__main__")'
```
PASS on seeds 20973 and 7 (the default runs both): 109,045 checks, 0 mismatches.
Per seed and hub: 4,600 / 4,416 predicate results; 39 / 32 action entries with
the dialog open and closed; 148 entry cases; 24 duplicate-check cases; 601
trigger cases plus 162 / 192 warning-poll sequences; 76 / 90 whole
conversations over 38 / 45 progress states, with 38 / 45 store deferrals through
the real `dialog_isOpen`. The `L-INN` store ran at both seeds.

```sh
python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_hub_npcs.py","--elf","local/SLUS_209.73","--iso","local/disc.iso"]; runpy.run_path("tools/difftest_hub_npcs.py", run_name="__main__")'
```
PASS: two pinned hub archives, eight EE cases over seeds 20973/7, 0 mismatches.

```sh
python3 -c 'import dis,unittest; unittest.main(module=None, argv=["u","discover","-s","tools","-p","test_*.py"])'
```
OK: 668 tests (652 before round 4, 15 added in round 4, 1 added in the fix round).

Retained PASS logs (untracked, mini and MacBook):
`local/hub-services-difftest.log`, `local/hub-services-npcs.log`,
`local/hub-services-unittest.log`.
