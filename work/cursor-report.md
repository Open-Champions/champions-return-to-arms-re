STATUS: COMPLETE

Dialog system round on `t3/research-dialog` (base `334578d`). No push. Commits:

- `df8114d` tools: `tools/ref_dialog_system.py` (reference), `tools/difftest_dialog_system.py`
  (difftest), `tools/test_ref_dialog_system.py` (12 synthetic tests). `tools/ref_dialog.py`,
  `tools/difftest_dialog.py`, `tools/ref_netwire.py` and `tools/ee_emu.py` are unchanged.
- `f738e37` docs: new `docs/dialog-system.md`; `docs/dialog.md` gets a 4-line pointer at its
  end (no existing line moved, so its line citations stay valid).
- this report.

## Documented (Executed unless marked)

- Offline game messages reach `dialog_onMsg` at once (original `net_sendGameMsg` 0x13db38,
  table 0x5d1498), so the open happens inside the use, before the run task of that tick.
- Message 3 order with sentinels: HUD, mutex, `g_dialogData`, camera, stream, unfreeze,
  pending level from `newWorldPost`, then the post action, then the pending shop and the
  remote wait. A duplicate 3 is ignored when closed; a late 3 closes a conversation opened
  in between (Inferred net hazard; not reachable on the disc).
- Choice actions run synchronously with dialog open, mutex held, HUD suppressed.
  `callScript` nested, returns the entry's value or −1. `postAction`: one slot, overwritten,
  cleared before it runs, a post set during the run is kept. `addDeferedCall`: two halves of
  64, 65th dropped, runs next frame, count and parity re-read per entry. A reward queued by
  the closing choice runs while the box is still open (directed case).
- A post action that opens a conversation: offline it opens inside message 3 and drops a
  pending shop and runs without the mutex; net it waits. No shipped entry does this (census).
- Input: the run task reads the pressed word (`pad_apply` +0x0c, no auto-repeat): one
  message per press for confirm, d-pad and stick; cancel, start, select and the other
  buttons send nothing; no read of the cancel mask or `g_menuInputLockout` in
  0x22ec9c–0x231078 (Observed scan). Default use 0x80 for all slots
  (`config_setDefaults(-1)`), confirm 0x40, so use never confirms; a confirm in the open tick
  finishes the typewriter only without a swoop.
- Pause and lockout table; hub, hub2 and missions 1–5 by citation to 7b924e1, d17b46f,
  28b3712 and 79a2e4a (not re-run). Client list in section 9.

## Partial / Inferred

- Run tasks keep running while paused (from `docs/script.md` 2.6), so typewriter, scroll and
  deferred calls continue.
- Online, the start button test is offline-only (from 79a2e4a's wording).
- The deferred-reward-while-open case is the normal one because closing waits for the fade
  (Inferred; the directed case forces two frames before message 3).

## Unknown

- Whether `net_closeLocalMenus(0)` in a chained net open closes a just-opened shop.
- Per-machine frames of message 3 copies in a net game.
- Whether the options can remap use onto confirm.
- `pad_readAll`'s copy to `g_rawPads` was not run. No run on a game.

## Stubs (disclosed in the doc, section 1)

`script_runByName` is a recording stub that plays neutral programs through the original
built-ins (nested calls); `net_sendGameMsg` is a recording stub that delivers offline at once
(its original offline branch is run by suite `send`); shop, fade wait, camera and stream are
the dialog rig's recording stubs. Three injected reference faults were each caught (local
probe `local/probe_faults.py`, untracked).

## Tests (on the mini, `~/malik-champions/research/wt/research-dialog`, after the last code edit)

Code sha256 at the run: `difftest_dialog_system.py` bf5f76ff…, `ref_dialog_system.py`
16a216de…, `test_ref_dialog_system.py` 7b326be1… (`local/dialog-final-sha.txt`; identical
to `df8114d`). Logs (untracked): `local/dialog-system-seed20973.log`,
`local/dialog-system-seed7.log`, `local/dialog-seed20973.log`, `local/dialog-seed7.log`,
`local/dialog-unit.log`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog_system.py local/SLUS_209.73 --seed 20973   # 6 suites, 0 failed
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog_system.py local/SLUS_209.73 --seed 7       # 6 suites, 0 failed
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog.py local/SLUS_209.73 --seed 20973          # 10 suites, 0 failed
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog.py local/SLUS_209.73 --seed 7              # 10 suites, 0 failed
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis, unittest, sys; sys.path.append("tools"); import test_ref_dialog_system, test_ref_dialog, test_dialog_census; s=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_ref_dialog_system, test_ref_dialog, test_dialog_census)]); unittest.TextTestRunner().run(s)'
# 61 tests, OK
```

Suite figures (seed 20973 / 7): `queue` 633 / 705 operations, 358 / 988 dropped names;
`endchain` 49 / 44 confirms, 53 / 51 ends, 21 / 32 duplicate ends, 55 / 52 post actions
(13 / 13 saw a pending level), 16 / 11 dropped shops, 13 / 13 deferred entries run with the
box open; `input` 17 button patterns, at most one message per press; `sametick` 40 opens
each; `defaults` use 0x80 on all four slots, confirm 0x40, cancel 0x120, layout 1.
