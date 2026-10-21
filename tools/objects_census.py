#!/usr/bin/env python3
"""objects_census.py - which level objects are ScriptGenerators, and what the hideMonster /
showMonster / generateMonster name arguments find on a disc.  Counts only.

  python3 tools/objects_census.py --disc DIR --elf SLUS_209.73 [--out FILE]

Every level lump of every .GOB that holds both `objects.ob` and `script.scr` is one level.
`objects.ob` is read with the record layout of docs/objects.md ("Level-object records").
Each distinct class name is classified at run time against the user's own executable:

  factory     the original world_objectFactory 0x159c94 runs in tools/ee_emu.py with
              pool_new stubbed to hand out a zeroed block; the call that follows pool_new is
              the constructor (as tools/items_census.py does).  No pool_new: "no object".
  creature    the constructor then runs for real, with this rule for each call it makes:
              Creature_ctor 0x109d68 entered with the block as `this` = creature (stubbed
              there); GameObject_ctor 0x14cb10 entered with the block = the chain reached
              the base (stubbed there); any other call whose first argument is the block
              runs for real (base-class constructors, methods on this object); every other
              call is stubbed and returns 0.  A run that stops (fault, step limit) is
              "unknown".  Creature_ctor is the only certain setter of flag 0x20
              (flagxref, 0x109e5c), which is what hideMonster / showMonster test.

Script calls are found as tools/items_census.py finds them (PUSH.C literals before
SYSREQ.C).  A hide/show name is matched against the `name=` properties of the same level's
records the way world_findObjectsByName matches (case-insensitive, quotes stripped,
ref_objects.NameTable).  Nothing from the disc is printed or written except numbers and
the executable's own command and class names.
"""
import collections
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import struct                                   # noqa: E402
from gob import gob_entries, lmp_entries        # noqa: E402
import items_census as IC                       # noqa: E402
import ref_objects as O                         # noqa: E402

POOL_NEW = 0x14FDB8
FACTORY = 0x159C94
CREATURE_CTOR = 0x109D68
GAMEOBJECT_CTOR = 0x14CB10
SCRIPT_GENERATOR_CTOR = 0x265F54                # docs/objects.md: ScriptGenerator (0x4c, 0x265f54)
GENERATOR_CTOR = 0x2657A0                       # docs/objects.md: Generator / AntMaker (0x3e8, 0x2657a0)
SKELETON_CTOR = 0x2A5AF4
G_WORLD = 0x44FDC8                              # level world pointer; the factory reads +0x70 for PushTrigger
M32 = 0xFFFFFFFF
COMMANDS = {'hideMonster': 's', 'showMonster': 's', 'generateMonster': 'ss'}


def parse_objects(blob):
    """docs/objects.md: s16 count, u16 flags, s32 string table offset; records of {s32 class,
    s16 size, s16 angle, f32 x, y, height, s32 property offsets..., 0}; string offsets are
    relative to the string table.  Returns [(class bytes, [property bytes])]."""
    count, _flags, strtab = struct.unpack_from('<hHi', blob, 0)

    def s(off):
        o = strtab + off
        return bytes(blob[o:blob.index(b'\0', o)])
    out, p = [], 8
    for _ in range(count):
        cls, size = struct.unpack_from('<ih', blob, p)
        props, q = [], p + 20
        while q < p + size:
            po, = struct.unpack_from('<i', blob, q)
            if po == 0:
                break
            props.append(s(po))
            q += 4
        out.append((s(cls), props))
        if size <= 0:
            raise ValueError('record size %d' % size)
        p += size
    return out


def levels_from_disc(root):
    """[(objects.ob bytes, script.scr bytes)] per level lump, and the count of GOBs refused."""
    out, refused = [], 0
    for dirpath, _dirs, files in os.walk(root):
        for filename in sorted(files):
            if not filename.upper().endswith('.GOB'):
                continue
            try:
                data = open(os.path.join(dirpath, filename), 'rb').read()
                lumps = gob_entries(data)
            except (OSError, ValueError, IndexError):
                refused += 1
                continue
            for _name, off, size in lumps:
                lump = data[off:off + size]
                try:
                    entries = {n: (o, s) for n, o, s in lmp_entries(lump)}
                except Exception:       # noqa: BLE001  a lump that is not a container
                    continue
                if 'objects.ob' in entries and 'script.scr' in entries:
                    (oo, os_), (so, ss) = entries['objects.ob'], entries['script.scr']
                    out.append((lump[oo:oo + os_], lump[so:so + ss]))
    return out, refused


class _Decided(Exception):
    pass


def probe_class(elf, name, props=()):
    """(pool size or None, constructor or None, kind) with kind one of 'creature',
    'non-creature', 'no object', 'unknown'.  props: the record's property strings (they
    decide the class when no name test matches)."""
    from ee_emu import EE
    emu = EE(elf)
    block = emu.alloc(0x1000)
    emu.mem.w32(G_WORLD, emu.alloc(0x1000))     # the level-world pointer is 0 in the image
    state = {'after_pool': False, 'ctor': None, 'size': None, 'kind': None}
    original = emu._enter_call

    def stub_return(value):
        emu.r[2] = value & 0xFFFFFFFFFFFFFFFF
        emu.jump(emu.r[31] & M32)
        return True

    def enter(target):
        a0 = emu.r[4] & M32
        if target == POOL_NEW and not state['after_pool']:
            state['after_pool'] = True
            state['size'] = a0
            return stub_return(block)
        if not state['after_pool']:
            return original(target)
        if a0 == block and target in (CREATURE_CTOR, GAMEOBJECT_CTOR):
            state['kind'] = 'creature' if target == CREATURE_CTOR else 'non-creature'
            raise _Decided()
        if a0 == block:
            if state['ctor'] is None:
                state['ctor'] = target
            return original(target)
        return stub_return(0)
    emu._enter_call = enter
    text = emu.alloc(len(name) + 1)
    emu.mem.write(text, name + b'\0')
    pos = emu.alloc(16)
    array = emu.alloc(4 * (len(props) + 1))
    for k, p in enumerate(props):
        at = emu.alloc(len(p) + 1)
        emu.mem.write(at, bytes(p) + b'\0')
        emu.mem.w32(array + 4 * k, at)
    try:
        emu.call(FACTORY, text, pos, 0, array, max_steps=2000000)
    except _Decided:
        return (state['size'], state['ctor'], state['kind'])
    except Exception:           # noqa: BLE001  a stop before the chain reached a base
        return (state['size'], state['ctor'], 'unknown' if state['after_pool'] else 'unknown (factory)')
    if not state['after_pool']:
        return (None, None, 'no object')
    return (state['size'], state['ctor'], 'unknown')


def name_props(props):
    """The names a record enters in the name table (GameObject_ctor step 7)."""
    return [O.strip_quotes(p[5:]) for p in props if p[:5] == b'name=']


def census(levels, elf, log=None):
    classes = {}

    by_props = {}

    def kind_of(cls, props):
        if cls not in classes:
            classes[cls] = probe_class(elf, cls)
        if classes[cls][2] != 'no object':
            return classes[cls]
        key = (cls, tuple(props))           # no name test matched: the properties decide
        if key not in by_props:
            by_props[key] = probe_class(elf, cls, props)
        return by_props[key]
    c = collections.Counter()
    gen_props = collections.Counter()
    hide = collections.Counter()
    for objects_blob, script in levels:
        try:
            records = parse_objects(objects_blob)
        except (ValueError, struct.error, IndexError):
            c['levels refused (objects.ob)'] += 1
            continue
        c['levels'] += 1
        by_name = collections.defaultdict(list)
        level_gens = 0
        for cls, props in records:
            c['records'] += 1
            size, ctor, kind = kind_of(cls, props)
            c['records ' + kind] += 1
            if ctor == SCRIPT_GENERATOR_CTOR:
                level_gens += 1
                c['ScriptGenerator records'] += 1
                gen_props['props %d' % len(props)] += 1
                gen_props['with name='] += 1 if name_props(props) else 0
                gen_props['with hide'] += 1 if any(p[:5] == b'hide=' for p in props) else 0
            if ctor == GENERATOR_CTOR:
                c['Generator/AntMaker records (0x2657a0)'] += 1
            if kind == 'no object':
                continue                    # no object, so nothing enters the name table
            for n in name_props(props):
                by_name[n.lower()].append((cls, kind, ctor))
        if level_gens:
            c['levels with a ScriptGenerator'] += 1
        sites = _sites(script)
        if sites is None:
            c['scripts refused'] += 1
            continue
        for command, nbytes, lits, machine in sites:
            sig = COMMANDS[command]
            strings = [IC.string_at(machine, lits[k]) if k < len(lits) and lits[k] is not None else None
                       for k in range(len(sig))]
            if command in ('hideMonster', 'showMonster'):
                hide[command + ' calls'] += 1
                text = strings[0]
                if text is None:
                    hide[command + ' name not literal'] += 1
                    continue
                found = by_name.get(O.strip_quotes(text).lower(), [])
                if not found:
                    hide[command + ' finds no level-file object'] += 1
                    continue
                kinds = {k for _c, k, _t in found}
                label = ('all creatures' if kinds == {'creature'} else 'all non-creatures' if kinds == {'non-creature'}
                         else 'creatures and non-creatures' if kinds == {'creature', 'non-creature'} else 'some unknown')
                hide[command + ' ' + label] += 1
                hide[command + ' objects found'] += len(found)
                hide[command + ' creature objects found'] += sum(1 for _c, k, _t in found if k == 'creature')
                if any(t == SCRIPT_GENERATOR_CTOR for _c, _k, t in found):
                    hide[command + ' finds a ScriptGenerator'] += 1
            else:
                hide['generateMonster calls'] += 1
                gname = strings[0]
                if gname is None:
                    hide['generateMonster generator not literal'] += 1
                    continue
                found = by_name.get(O.strip_quotes(gname).lower(), [])
                gens = sum(1 for _c, _k, t in found if t == SCRIPT_GENERATOR_CTOR)
                label = 'no object' if not found else ('no ScriptGenerator' if gens == 0 else
                                                       'one ScriptGenerator' if gens == 1 else 'several ScriptGenerators')
                hide['generateMonster generator name finds ' + label] += 1
                hide['generateMonster ScriptGenerators reached'] += gens
    kinds = collections.Counter(k for _s, _c, k in classes.values())
    c['property-decided probes'] = len(by_props)
    for _key, (_s, ctor, k) in by_props.items():
        c['property-decided ' + k] += 1
    return c, gen_props, hide, kinds, classes


def _sites(script):
    """(command, nbytes, literals, machine) for the three commands, as items_census finds
    them (its COMMANDS list does not hold hideMonster / showMonster, so the scan is
    repeated here with this module's list)."""
    machine = IC.ref_amx.Machine(script)
    if machine.load() != 0:
        return None
    names = [machine.native_name(k).decode('latin-1', 'replace') for k in range(max(machine.num_natives, 0))]
    code = sorted(machine._decoded.items())
    out = []
    for pos, (_offset, (opcode, operand, _end)) in enumerate(code):
        if opcode != IC.SYSREQ_C or not isinstance(operand, int):
            continue
        if not 0 <= operand < len(names) or names[operand] not in COMMANDS:
            continue
        nbytes, literals = None, []
        if pos >= 1 and code[pos - 1][1][0] == IC.PUSH_C:
            nbytes = code[pos - 1][1][1]
            for k in range(max(nbytes, 0) // 4):
                at = pos - 2 - k
                literals.append(code[at][1][1] if at >= 0 and code[at][1][0] == IC.PUSH_C else None)
        out.append((names[operand], nbytes, literals, machine))
    return out


def main(argv):
    if '--disc' not in argv or '--elf' not in argv:
        print(__doc__)
        return 2
    root = argv[argv.index('--disc') + 1]
    elf = argv[argv.index('--elf') + 1]
    out = argv[argv.index('--out') + 1] if '--out' in argv else None
    levels, refused = levels_from_disc(root)
    c, gen_props, hide, kinds, classes = census(levels, elf)
    lines = ['GOBs refused %d' % refused, 'level lumps %d' % len(levels)]
    lines += ['%s %d' % kv for kv in sorted(c.items())]
    lines += ['distinct classes %d' % len(classes)]
    lines += ['distinct classes %s %d' % kv for kv in sorted(kinds.items())]
    lines += ['ScriptGenerator %s %d' % kv for kv in sorted(gen_props.items())]
    lines += ['%s %d' % kv for kv in sorted(hide.items())]
    text = '\n'.join(lines) + '\n'
    if out:
        with open(out, 'w') as f:
            f.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
