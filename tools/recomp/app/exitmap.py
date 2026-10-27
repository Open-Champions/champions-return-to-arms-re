#!/usr/bin/env python3
"""exitmap.py - where each level's exits are and where they lead, read from your own disc (a playtest aid).

  python3 tools/recomp/app/exitmap.py [--disc ISO] [--out local/playtest/exitmap.json] [LEVEL ...]

For every level archive: the level objects a player uses to leave or to move the story on - rectangle `Trigger`s (walk
in), `PushTrigger`s (stand by and press use), `Portal`s (jump gates), save points, shops (an NPC with `shop=1`) - with
their place and, for the two trigger kinds, what their script reaches when it runs: the levels it asks for
(`newWorld`, `simpleNewWorld`, `newWorldAlways`), the entrance it names (`setEntrance`), the mission menu
(`activateMissionMenu`), the store (`activateStore`), and the script entry that guards a PushTrigger (`key=`).
Scripts are followed through `callScript('name')` and the script's own calls, to depth 6 (docs/level-flow.md 6.4).

Read: objects.ob (tools/ref_levels.py parse_objects) and script.scr (tools/scr.py) of each .GOB's level lumps.
The output is game data (names, places): it is written under local/ only and never tracked.
"""
import argparse
import json
import mmap
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from find_hosts import iso_files                # noqa: E402
from gob import gob_entries, lmp_entries        # noqa: E402
import ref_levels                               # noqa: E402
import scr                                      # noqa: E402

DISC = os.environ.get('RTA_DISC') or os.path.expanduser(
    '~/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso')
WANTED = ('newWorld', 'simpleNewWorld', 'newWorldAlways', 'newWorldPost', 'setEntrance', 'activateMissionMenu',
          'activateStore', 'saveCheckPoint', 'startDialog', 'setv', 'getv', 'trigger')
KINDS = ('Trigger', 'PushTrigger', 'Portal', 'Savepoint', 'NPC', 'Player1', 'Chest', 'AutoChest', 'MonsterTrigger')


class Script:
    """One script.scr: its functions (from each `enter`), what each calls."""

    def __init__(self, blob):
        p = scr.parse(blob)
        cs, ce = p['code']
        self.pool = dict(scr.strings(blob, *p['strings']))
        self.ext = [n for _, n in p['externals']]
        self.entries = {name.lower(): val for val, name in p['internals']}
        words = struct.unpack_from('<%dI' % ((ce - cs) // 4), blob, cs)
        self.funcs = {}             # start -> [(kind, name, args)]
        current, pending, i = None, [], 0
        while i < len(words):
            off, op = i * 4, words[i]
            if op == 0x2e:
                current = off
                self.funcs[current] = []
            if op == 0x7d:
                i += 3
                continue
            if op == 0x7b:
                n = words[i + 1]
                args = pending[:-1][::-1] if pending else []
                # a built-in that takes a name: a small number is the string pool's offset (0 is a string too)
                if n < len(self.ext) and self.ext[n] in ('callScript', 'newWorld', 'simpleNewWorld', 'newWorldAlways', 'newWorldPost', 'setEntrance'):
                    args = [self.pool.get(a, a) if isinstance(a, int) else a for a in args]
                if current is not None and n < len(self.ext):
                    self.funcs[current].append(('ext', self.ext[n], args))
                pending = []
                i += 2
                continue
            if op == 0x27:
                v = words[i + 1]
                pending.append(self.pool[v] if v in self.pool and v >= 8 else v)
                i += 2
                continue
            if op == 0x31 and current is not None:
                self.funcs[current].append(('call', words[i + 1], []))
            if op == 0x2c:
                pending = []
                i += 2
                continue
            if op == 0x28:
                pending.append('var')
                i += 2
                continue
            if op in (0x24, 0x25):
                pending.append('reg')
            else:
                pending = []
            if op in scr.OPS:
                i += 1 + scr.OPS[op][1]
            else:
                i += 1 + (0 if op in scr.NO_OPERAND else 1)
        self.starts = sorted(self.funcs)

    def function_at(self, address):
        best = None
        for s in self.starts:
            if s <= address:
                best = s
        return best

    def reach(self, name, depth=6, seen=None):
        """What the entry `name` reaches: {built-in: [args, ...]}."""
        out = {}
        seen = seen if seen is not None else set()
        start = self.entries.get(str(name).lower())
        if start is None:
            return out
        self._walk(self.function_at(start), depth, seen, out)
        return out

    def _walk(self, start, depth, seen, out):
        if start is None or start in seen or depth < 0:
            return
        seen.add(start)
        for kind, name, args in self.funcs.get(start, []):
            if kind == 'call':
                self._walk(self.function_at(name), depth - 1, seen, out)
            elif name == 'callScript' and args:
                target = self.entries.get(str(args[0]).lower())
                if target is not None:
                    self._walk(self.function_at(target), depth - 1, seen, out)
            elif name in WANTED:
                out.setdefault(name, [])
                if args and args not in out[name]:
                    out[name].append(args)
                elif not args and [] not in out[name]:
                    out[name].append([])


def levels(disc, only=()):
    f = open(disc, 'rb')
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    for path, lba, size in sorted(iso_files(m)):
        if not path.upper().endswith('.GOB'):
            continue
        gob = m[lba * 2048:lba * 2048 + size]
        for lump_name, lo, ls in gob_entries(gob):
            if not lump_name.lower().endswith('.lmp'):
                continue
            level = lump_name[:-4].lower()
            if only and level not in only and os.path.basename(path)[:-4].lower() not in only:
                continue
            lump = gob[lo:lo + ls]
            try:
                files = {n: lump[o:o + s] for n, o, s in lmp_entries(lump)}
            except Exception:
                continue
            if 'objects.ob' not in files:
                continue
            yield level, files


def describe(level, files):
    script = Script(files['script.scr']) if 'script.scr' in files else None
    out = []
    for k, r in enumerate(ref_levels.parse_objects(files['objects.ob'])):
        if r.cls not in KINDS and not (r.prop('action') or r.prop('t')):
            continue
        if r.cls in ('NPC',) and not r.prop('shop'):
            continue
        o = {'n': k, 'cls': r.cls, 'x': round(r.x, 1), 'y': round(r.y, 1), 'z': round(r.z, 1)}
        for key in ('w', 'h', 'radius', 'once', 'shop', 'name', 'lump', 'from', 'default'):
            if r.prop(key) is not None:
                o[key] = r.prop(key)
        if r.cls == 'Trigger' and r.prop('w'):
            # docs/level-flow.md 8: from (x, y) to (x + w, y - h)
            o['rect'] = [r.x, r.y - float(r.prop('h')), r.x + float(r.prop('w')), r.y]
        name = r.prop('t') or r.prop('action')
        if script is not None and name:
            o['script'] = name
            o['reaches'] = script.reach(name)
            if r.prop('key'):
                o['key'] = script.reach(r.prop('key'))
        out.append(o)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('levels', nargs='*')
    parser.add_argument('--disc', default=DISC)
    parser.add_argument('--out', default=os.path.join(ROOT, 'local', 'playtest', 'exitmap.json'))
    args = parser.parse_args()
    found = {}
    for level, files in levels(args.disc, set(n.lower() for n in args.levels)):
        found[level] = describe(level, files)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as sink:
        json.dump(found, sink, indent=1)
    exits = sum(1 for objs in found.values() for o in objs if 'newWorld' in o.get('reaches', {}))
    print('exitmap: %d levels, %d objects that ask for a level -> %s' % (len(found), exits, args.out))


if __name__ == '__main__':
    sys.exit(main())
