#!/usr/bin/env python3
"""enum_drawscripts.py - every level script that drawing code can start, over the whole disc,
and what each can do (docs/script.md P1; docs/issues/native-soak.md "Script variables").

  python3 tools/recomp/soak/enum_drawscripts.py "<disc image>" [--list] [--tsv FILE]

Reads every level archive of the disc image (objects.ob and script.scr of each level lump)
and docs/script.md's table of the built-ins.  Nothing is written unless --tsv names a file
(keep it under local/: its rows are level data).

Drawing code starts a script in three ways (docs/script.md 2.2):
  prompt   Player_draw -> Player_interact(display only) -> the nearest usable object's prompt
           (virtual slot 13): the `key` property of a PushTrigger, AutoChest, AutoProp or
           SpiritAnchor and the `script` property of a JumpGate.  The same prompt also runs
           inside the tick for every player.
  marker   the draw function of an NPC, Gnome, GnomeNavigator or Rondo: `exclamation`.
  map      the map-drawing function 0x168cac, for every map icon (a PushTrigger with an `icon`
           property; PushTrigger_ctor 0x1eca64): `iconValue` names a quest variable that the
           function reads itself, `iconScript` an entry it runs.
For every object property of these names the entry it names is followed through callScript
and through calls inside the script, and the built-ins it can reach are listed with what the
built-in table says they write.  `key` and `script` are listed for every class that carries
them; --list prints each (level, class, property, entry, built-ins).
"""
import argparse
import collections
import mmap
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from gob import gob_entries, lmp_entries            # noqa: E402
from find_hosts import iso_files                    # noqa: E402
import scr                                          # noqa: E402

DRAW_PROPS = ('key', 'script', 'exclamation', 'iconScript')
VALUE_PROPS = ('iconValue',)     # a quest variable read by the map drawing itself (vars_get at 0x1696a4)
# built-ins that only read (the table's "Shared state written" column is "-") are taken from
# docs/script.md; these are the ones a predicate may call with no effect beyond its result
CONTROL = {'callScript'}


def builtin_table():
    """name -> (shared state written, per-machine state read), from docs/script.md."""
    table = {}
    for line in open(os.path.join(ROOT, 'docs', 'script.md'), errors='replace'):
        found = re.match(r'\| (\d+) \| `(\w+)` \| (0x[0-9a-f]+) \| (.*?) \| (.*) \| (.*?) \| (.*?) \| (.*?) \|\s*$', line)
        if found:
            table[found.group(2)] = (found.group(6).strip(), found.group(7).strip())
    return table


def parse_objects(blob):
    count, _, strtab = struct.unpack_from('<hHi', blob, 0)

    def text(off):
        o = strtab + off
        return blob[o:blob.index(b'\0', o)].decode('latin1')
    rows, p = [], 8
    for _ in range(count):
        cls, size, _ = struct.unpack_from('<ihH', blob, p)
        props, q = [], p + 20
        while q < p + size:
            po, = struct.unpack_from('<i', blob, q)
            if po == 0:
                break
            props.append(text(po))
            q += 4
        rows.append((text(cls), props))
        p += size
    return rows


def parse_script(d):
    """entry name -> {'calls': [(built-in, [arguments])], 'internal': {entry names called}}."""
    p = scr.parse(d)
    cs, ce = p['code']
    pool = dict(scr.strings(d, *p['strings']))
    ext = [n for _, n in p['externals']]
    starts = sorted((val, name) for val, name in p['internals'])
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), d, cs)

    def owner(off):
        name = None
        for val, n in starts:
            if val <= off:
                name = n
            else:
                break
        return name
    entries = {name: {'calls': [], 'internal': set()} for _, name in starts}
    i, pending = 0, []
    while i < len(words):
        off, op = i * 4, words[i]
        here = entries.get(owner(off))
        if op == 0x7d:
            i += 3
            continue
        if op == 0x7b:
            args = pending[:-1][::-1] if pending else []
            if here is not None:
                here['calls'].append((ext[words[i + 1]], args))
            pending = []
            i += 2
            continue
        if op == 0x27:
            v = words[i + 1]
            pending.append(pool[v] if v in pool else (v if v < 0x80000000 else v - (1 << 32)))
            i += 2
            continue
        if op == 0x28:
            pending.append('var[%#x]' % words[i + 1])
            i += 2
            continue
        if op == 0x2c:
            pending = []
            i += 2
            continue
        pending = []
        if op == 0x31 and here is not None:
            target = owner(words[i + 1])
            if target:
                here['internal'].add(target)
        if op in (0x0f, 0x5b, 0x6d, 0x72) and here is not None:      # a store to a script global
            here['calls'].append(('(script global store)', ['var[%#x]' % words[i + 1]]))
        if op == 0x17 and here is not None:
            here['calls'].append(('(script memory store)', []))
        i += 1 + (0 if op in scr.NO_OPERAND else 1)
    return entries


def reach(entries, name, seen=None):
    """Every (built-in, arguments) the entry can execute, callScript and internal calls followed.
    Returns (calls, unknown names)."""
    seen = seen if seen is not None else set()
    key = name.lower()
    by_lower = {n.lower(): n for n in entries}
    if key in seen:
        return [], []
    seen.add(key)
    if key not in by_lower:
        return [], [name]
    entry = entries[by_lower[key]]
    calls, unknown = [], []
    for builtin, args in entry['calls']:
        calls.append((builtin, args))
        if builtin == 'callScript' and args and isinstance(args[0], str):
            more, missing = reach(entries, args[0], seen)
            calls += more
            unknown += missing
    for other in entry['internal']:
        more, missing = reach(entries, other, seen)
        calls += more
        unknown += missing
    return calls, unknown


def levels(iso):
    with open(iso, 'rb') as handle:
        m = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    for path, lba, size in sorted(iso_files(m)):
        if not path.upper().endswith('.GOB'):
            continue
        gob = m[lba * 2048:lba * 2048 + size]
        for lname, loff, lsize in gob_entries(gob):
            lump = gob[loff:loff + lsize]
            try:
                files = {name.lower(): lump[off:off + n] for name, off, n in lmp_entries(lump)}
            except Exception:
                continue
            if 'objects.ob' in files:
                yield os.path.basename(path)[:-4], lname, files['objects.ob'], files.get('script.scr')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('iso', nargs='?', default=os.environ.get('RTA_DISC'))
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--tsv')
    args = parser.parse_args()
    if not args.iso:
        raise SystemExit('give the disc image, or set RTA_DISC')
    table = builtin_table()
    rows = []                   # (level, class, property, value, calls, unknown)
    classes = collections.Counter()
    level_count = 0
    all_objects = 0
    prop_names = collections.Counter()
    value_props = collections.Counter()
    extra = collections.Counter()
    for level, lump, objects, script in levels(args.iso):
        level_count += 1
        entries = parse_script(script) if script else {}
        for cls, props in parse_objects(objects):
            all_objects += 1
            classes[cls] += 1
            for prop in props:
                name, _, value = prop.partition('=')
                if cls in ('Portal', 'Savepoint') and name in ('action', 'hurt', 'destination'):
                    extra[name] += 1
                prop_names[name] += 1
                if name in VALUE_PROPS:
                    value_props[(name, level, cls, value)] += 1
                if name in DRAW_PROPS:
                    calls, unknown = reach(entries, value) if entries else ([], [value])
                    rows.append((level, cls, name, value, calls, unknown))
    print('%d level lumps with objects, %d objects, %d properties named %s' % (
        level_count, all_objects, len(rows), ' / '.join(DRAW_PROPS)))
    for cls in ('Portal', 'Savepoint', 'PushTrigger', 'NPC'):
        print('  objects of class %s on the disc: %d' % (cls, classes[cls]))
    print('  properties %s: %d objects, %d different (level, name): %s' % (
        ' / '.join(VALUE_PROPS), sum(value_props.values()), len({(k[1], k[3]) for k in value_props}),
        ', '.join(sorted({'%s:%s' % (k[1], k[3]) for k in value_props}))[:600]))
    for name in ('action', 'hurt', 'destination'):
        print('  Savepoint / Portal objects with `%s`: %d' % (name, extra[name]))
    sink = open(args.tsv, 'w') if args.tsv else None
    by_kind = collections.defaultdict(list)
    for row in rows:
        by_kind[(row[2], row[1])].append(row)
    print('\nproperty, class: objects, different entries, levels')
    for (prop, cls), members in sorted(by_kind.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        print('  %-12s %-22s %4d objects  %3d entries  %2d levels' % (
            prop, cls, len(members), len({(r[0], r[3].lower()) for r in members}), len({r[0] for r in members})))
    for prop in DRAW_PROPS:
        members = [r for r in rows if r[2] == prop]
        used = collections.Counter()
        where = collections.defaultdict(set)
        missing = set()
        variables = collections.Counter()
        for level, cls, _, value, calls, unknown in members:
            for builtin, call_args in {(b, tuple(map(str, a))) for b, a in calls}:
                used[builtin] += 1
                where[builtin].add('%s:%s' % (level, value))
                if builtin == 'getv':
                    variables[(level, call_args[0] if call_args else '?')] += 1
            for name in unknown:
                missing.add('%s:%s' % (level, name))
        print('\n`%s`: %d objects, %d different (level, entry) pairs, %d names with no entry in the level script' % (
            prop, len(members), len({(r[0], r[3].lower()) for r in members}), len(missing)))
        for builtin, count in sorted(used.items(), key=lambda kv: -kv[1]):
            writes, local = table.get(builtin, ('?', '?'))
            mark = ' ' if writes in ('-', '') or builtin in CONTROL else '*'
            print('  %s %-24s %4d objects  writes: %-60s per machine: %s%s' % (
                mark, builtin, count, writes[:60], local[:70],
                '' if mark == ' ' else '   in ' + ', '.join(sorted(where[builtin])[:8]) + (' ...' if len(where[builtin]) > 8 else '')))
        if variables:
            print('  quest variables read by these entries: %d different (level, name)' % len(variables))
        if missing:
            print('  no entry: ' + ', '.join(sorted(missing)[:20]) + (' ...' if len(missing) > 20 else ''))
    if args.list or sink:
        for level, cls, prop, value, calls, unknown in sorted(rows, key=lambda r: (r[2], r[0], r[1], r[3])):
            text = '; '.join(sorted({'%s(%s)' % (b, ', '.join(map(str, a))) for b, a in calls}))
            line = '%s\t%s\t%s\t%s\t%s%s' % (level, cls, prop, value, text, '\tNO ENTRY ' + ','.join(unknown) if unknown else '')
            if sink:
                sink.write(line + '\n')
            if args.list:
                print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
