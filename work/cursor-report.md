STATUS: COMPLETE

# research-hub-npcs, round 4 (2026-11-09)

Branch `t3/research-hub-npcs`, from tip `31db144`. Work and runs were on the Mac
mini worktree (`~/malik-champions/research/wt/research-hub-npcs`), and the commits
were fast-forwarded to the MacBook worktree. Deliverable: `docs/hub-services.md`.

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
  and nothing else. 76 + 90 whole conversations per seed ran through the original
  `dialog_onMsg` (pinned `2ab82b2` Probe), with start node, visible choices,
  actions, mission writes and quest count checked at every step.
- `removePlayerItem` is not reachable from either dialog; all 19 sites are hub
  entry. The unreferenced writers, including hub `0x7fc` that mission-unlocks
  left open, are used only by each hub's unused backup `.dbin`.
- Hub entry `start`, 148 cases per hub per seed: entry mission bits, save
  inhibit, the vendor store-level rule (this resolves vendor-stock's two
  "non-literal" stores: both are current − 1), flag 4, mana restore, 17-site
  quest-item cleanup, first-mission help, ring state. The deferred duplicate
  checks visit only 9 of 10 and 12 of 13 table cells (loop bound one short).
- PushTrigger key, use and walk-in, 601 cases per hub per seed. The key reads
  only A(12) for mission 12, so the map stays usable after mission 12. Use
  warns while a started mission is incomplete, else writes the entrance and
  opens the menu unless a dialog or recall blocks it. The walk-in fires once.
- The only other writer of the mana flag (`L-INN`, private name in local/) was
  found by disc census, and its store was executed. The restore is free on hub
  return; it is not a paid inn.

## Partial / cited, not re-run

Jump gate (`t3/research-exits-walkin` `95760d9`), save screen
(`t3/research-save-screen` `c8895e2`), store contents and prices
(`t3/research-vendor-stock` `fdf6752`), mission menu after confirm
(`t3/research-story-route-r3` `3c7987c`), dialog suppressors and menu task
lifetime (`t3/research-mission-unlocks` `2ab82b2`). Line ranges are in the doc.

## Unknown

Live proximity/use of these objects; text, voice and camera pixels; how
`L-INN` is reached; the caller of the hub cutscene entry `0x34a4`; the
stack-read store index of the backup-only writers; the real bag cell
`removePlayerItem` removes; any native-client behaviour.

## Commits

- `ab7bfaa` model + synthetic tests (`tools/ref_hub_services.py`, `tools/test_ref_hub_services.py`)
- `b8ff840` difftest (`tools/difftest_hub_services.py`)
- `08b090a` `docs/hub-services.md`, follow-up note in `docs/spec/hub-npc-services.md`
- `bbbeca3` reproduction-command fix in the doc
- this report (final SHA in the reply / COORDINATION line)

## Tests (mini, after the final code/doc edit)

All runs at `bbbeca3`, single process, `PYTHONDONTWRITEBYTECODE=1`, from the
worktree root. `<disc>` is the mini's read-only `private-validation/rta-disc`.

```sh
python3 -c 'import dis,runpy,sys; sys.argv=["difftest_hub_services.py","--elf","local/SLUS_209.73","--data","<disc>/BG/DATA"]; runpy.run_path("tools/difftest_hub_services.py", run_name="__main__")'
```
PASS on seeds 20973 and 7 (the default runs both): 71,635 checks, 0 mismatches.
Per seed and hub: 4,600 / 4,416 predicate results; 39 / 32 action entries with
the dialog open and closed; 148 entry cases; 24 duplicate-check cases; 601
trigger cases; 76 / 90 whole conversations over 38 / 45 progress states. The
`L-INN` store ran at both seeds.

```sh
python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_hub_npcs.py","--elf","local/SLUS_209.73","--iso","local/disc.iso"]; runpy.run_path("tools/difftest_hub_npcs.py", run_name="__main__")'
```
PASS: two pinned hub archives, eight EE cases over seeds 20973/7, 0 mismatches.

```sh
python3 -c 'import dis,unittest; unittest.main(module=None, argv=["u","discover","-s","tools","-p","test_*.py"])'
```
OK: 667 tests (652 before this round, plus 15 new).

Retained PASS logs (untracked, mini and MacBook):
`local/hub-services-difftest.log`, `local/hub-services-npcs.log`,
`local/hub-services-unittest.log`. Each starts with the HEAD it ran on.
