#!/usr/bin/env python3
"""enum_interact.py - every "interact prompt" (virtual slot 13) and "interact" (slot 14) of the
GameObject family, and what each reads that belongs to one machine
(docs/issues/native-soak.md, "Save point" and "Script variables").

  python3 -I -B tools/recomp/soak/enum_interact.py [--depth N] [--all]

Player_interact 0x1b2640 calls slot 13 of the nearest usable object for every real player in
every tick (Player_run) and again at display rate for this machine's own players
(Player_draw, display only); a button press in the tick then calls slot 14.  A test of
per-machine state in either makes the machines do different things in the same tick; a
store in slot 13 happens at draw time on the owner's machine as well.

For each implementation (functions shared by several classes are listed once) the direct
calls are followed --depth levels (default 2) and these are reported:
  calls   to the functions of LOCAL_CALLS (card state, local slot, camera, tasks ...)
  reads   of globals that presentation-only code stores (tools/drawsim.py's strict tier:
          a global written by a function no simulation root reaches)
  stores  (slot 13 only) through `this` in the function itself, and calls it makes to the
          functions of EFFECT_CALLS (scripts, lists, messages)
Reading code: over-approximate (a callee two levels down may be reached on another path)
and blind where drawsim.py is blind (fields, indirect calls).  The table says where to
read, not what happens.
"""
import collections
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import drawsim                      # noqa: E402

LOCAL_CALLS = {
    0x217518: 'memcard_isBusy (this machine\'s card screens)', 0x217550: 'memcard_getState', 0x2175b4: 'memcard_requestSave (opens for a local slot only)',
    0x13e150: 'net_isLocalSlot', 0x13e1f0: 'net_getLocalPlayerSlot', 0x13e180: 'net_objOrGhost',
    0x13e110: 'net_getCamFlag (lockstep in the tick, this machine\'s current value at draw time)',
    0x19e5e8: 'task_isRunning (tasks are per machine)', 0x172be8: 'cd_isBusy', 0x1ebd90: 'near the camera', 0x1e77c0: 'isNearView',
    0x216480: 'audio stream position', 0x211b20: 'audio stream status', 0x1ec5d8: 'net_allPlayersState2',
}
SHARED_CALLS = {0x22fc2c: 'menuMutex_isHeld (shared in a net game: Creature_interact, Creature_trigger, dialog messages)',
                0x22fc04: 'menuMutex_tryAcquire', 0x1e7b78: 'game_inNoSaveZone', 0x22fbc0: 'dialog_isOpen'}
EFFECT_CALLS = {0x1ed694: 'script_runByName', 0x27db60: 'jumpgate_addCurrentLevel', 0x1d92a0: 'hud_showMessage',
                0x14dcc8: 'obj_runActionScripts', 0x1ed854: 'vars_set', 0x1ed778: 'vars_get (appends a missing name)',
                0x148bc8: 'light_link2', 0x1de0dc: 'hudmsg (game message 2)', 0x1de1a0: 'hudmsg_sendSavepoint'}


def closure(P, f, depth):
    """{function: chain from f} over direct calls."""
    seen = {f: [f]}
    frontier = [f]
    for _ in range(depth):
        nxt = []
        for g in frontier:
            for h in P.calls.get(g, ()):
                if h not in seen and h in P.bodies:
                    seen[h] = seen[g] + [h]
                    nxt.append(h)
        frontier = nxt
    return seen


def main(argv):
    depth = int(argv[argv.index('--depth') + 1]) if '--depth' in argv else 2
    show_all = '--all' in argv
    P = drawsim.Program()
    acc = P.accesses()
    pres_written = {}           # global -> a presentation-only writer
    for v, by_fn in acc.items():
        for f, hits in by_fn.items():
            if drawsim.pres_only(P, f) and any(kind == 'W' for _, kind in hits):
                pres_written.setdefault(v, f)
    readers = collections.defaultdict(list)     # function -> [global]
    for v in pres_written:
        for f, hits in acc[v].items():
            if any(kind == 'R' for _, kind in hits):
                readers[f].append(v)
    by_slot = {}
    for slot in (13, 14):
        owners = collections.defaultdict(list)
        for table, (name, fns) in P.vtables.items():
            if P.family.get(table) != 0x48 or name.startswith('vt') or len(fns) < slot:
                continue
            fn = fns[slot - 1]
            if fn in P.bodies:
                owners[fn].append(name)
        by_slot[slot] = owners
    for slot, title in ((13, 'interact prompt (slot 13): in the tick for every player, and at draw time on the owner\'s machine'),
                        (14, 'interact (slot 14): in the tick, after a button press')):
        owners = by_slot[slot]
        print('\n%s\n%d implementations over %d classes' % (title, len(owners), sum(len(c) for c in owners.values())))
        flagged = 0
        for fn, classes in sorted(owners.items(), key=lambda kv: -len(kv[1])):
            reach = closure(P, fn, depth)
            local, shared, effects, globs = [], [], [], []
            for g, chain in reach.items():
                via = '' if len(chain) <= 2 else ' via ' + P.name(chain[1])
                if g in LOCAL_CALLS and g != fn:
                    local.append(LOCAL_CALLS[g].split(' (')[0] + via)
                if g in SHARED_CALLS and g != fn:
                    shared.append(SHARED_CALLS[g].split(' (')[0] + via)
                if g in EFFECT_CALLS and len(chain) <= 2:
                    effects.append(EFFECT_CALLS[g].split(' (')[0])
                for v in readers.get(g, ()):
                    globs.append('%s%s' % (P.name(v), '' if g == fn else ' in ' + P.name(g)))
            stores = ''
            if slot == 13:
                out = subprocess.run([sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'fieldxref.py'),
                                      os.path.join(ROOT, 'SLUS_209.73'), '0-5ff', '--stores', '--this', '--certain', '--no-follow',
                                      '--func', '%x' % fn], capture_output=True, text=True).stdout
                hits = [h for line in out.splitlines() for h in line.split()[2:] if ':s' in h]
                stores = ' '.join(sorted({h.split(':', 1)[1] for h in hits}))
            if not (local or globs or effects or stores or show_all):
                continue
            flagged += 1
            print('  %x %s  [%d: %s%s]' % (fn, P.name(fn), len(classes), ' '.join(sorted(classes)[:5]), ' ...' if len(classes) > 5 else ''))
            if local:
                print('      per machine, calls: ' + '; '.join(sorted(set(local))))
            if globs:
                print('      per machine, reads: ' + '; '.join(sorted(set(globs))[:10]))
            if shared:
                print('      shared state tested: ' + '; '.join(sorted(set(shared))))
            if effects:
                print('      effects: ' + '; '.join(sorted(set(effects))))
            if stores:
                print('      stores through this: ' + stores)
        print('  (%d of %d listed; the others call none of these and read no such global within %d levels)' % (flagged, len(owners), depth))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
