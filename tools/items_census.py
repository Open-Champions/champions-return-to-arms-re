#!/usr/bin/env python3
"""Count the item, gold, skill and monster-builder script calls on a disc. Counts only.

  python3 tools/items_census.py --disc DIR [--elf SLUS_209.73]
  python3 tools/items_census.py --scripts DIR [--elf SLUS_209.73]

--disc walks DIR for .GOB archives and reads every script.scr; --scripts reads *.scr
files.  Nothing is written.  No level name, entry point, string literal, item name or
class name is printed: only numbers, and the names of the script commands.

With --elf (the user's own executable) the literal arguments are also classified against
the executable's own tables, at run time: item names against the definition table
(exact, case-only, none), descriptors against the parser's lookup, generator class names
through the original world_objectFactory run in tools/ee_emu.py (a constructor, or no
object).  Arguments that are not literals (variables, expressions) are counted apart.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_amx                                  # noqa: E402
from gob import gob_entries, lmp_entries        # noqa: E402

PUSH_C, SYSREQ_C = ref_amx.OP['PUSH.C'], ref_amx.OP['SYSREQ.C']
SKELETON_CTOR = 0x2A5AF4        # Skeleton_ctor: the class ScriptGenerator_spawn sets to state 0x17
COMMANDS = ('playerHasItem', 'onePlayerHasItem', 'countQuestItems', 'removePlayerItem', 'removeAllItems',
            'removeAllWeapons', 'givePlayerItem', 'giveOnePlayerItem', 'givePlayerRandom', 'dropItem',
            'selectDropItem', 'givePlayerGold', 'takePlayerGold', 'checkPlayerGold', 'checkPlayerMinGold',
            'clearAllSkills', 'generateMonster')
KINDS = {'playerHasItem': 's', 'onePlayerHasItem': 'is', 'countQuestItems': 's', 'removePlayerItem': 'is',
         'givePlayerItem': 'sii', 'giveOnePlayerItem': 'isii', 'dropItem': 'ss', 'selectDropItem': 's',
         'givePlayerGold': 'i', 'takePlayerGold': 'i', 'generateMonster': 'ss'}


def images_from_disc(root):
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
                    entries = lmp_entries(lump)
                except Exception:       # noqa: BLE001  a lump that is not a container
                    continue
                for fname, foff, fsize in entries:
                    if fname == 'script.scr' and 0 <= foff and foff + fsize <= len(lump):
                        out.append(lump[foff:foff + fsize])
    return out, refused


def images_from_dir(directory):
    out = []
    for filename in sorted(os.listdir(directory)):
        if filename.lower().endswith('.scr'):
            out.append(open(os.path.join(directory, filename), 'rb').read())
    return out, 0


def call_sites(image):
    """[(command name, argument bytes or None, [literal or None per argument])]."""
    machine = ref_amx.Machine(image)
    if machine.load() != 0:
        return None
    names = [machine.native_name(k).decode('latin-1', 'replace') for k in range(max(machine.num_natives, 0))]
    code = sorted(machine._decoded.items())
    out = []
    for pos, (_offset, (opcode, operand, _end)) in enumerate(code):
        if opcode != SYSREQ_C or not isinstance(operand, int):
            continue
        index = operand
        if not 0 <= index < len(names) or names[index] not in COMMANDS:
            continue
        name = names[index]
        nbytes, literals = None, []
        if pos >= 1 and code[pos - 1][1][0] == PUSH_C:
            nbytes = code[pos - 1][1][1]
            for k in range(max(nbytes, 0) // 4):
                at = pos - 2 - k
                if at >= 0 and code[at][1][0] == PUSH_C:
                    literals.append(code[at][1][1])
                else:
                    literals.append(None)
        out.append((name, nbytes, literals, machine))
    return out


def string_at(machine, address):
    try:
        return machine.get_string(address)
    except Exception:           # noqa: BLE001  not a data address
        return None


class Classifier:
    def __init__(self, elf):
        import ref_items as I
        self.tables = I.Tables(I.Exe(elf))
        rows = self.tables.defs + self.tables.presets       # a bag entry may point at either table
        self.exact = {d.name for d in rows}
        self.lower = {d.name.lower() for d in rows}
        self.base = {d.name for d in self.tables.defs}
        self.presets = {d.name for d in self.tables.presets}
        self.elf = elf
        self._factory = {}

    def name_kind(self, text):
        if text in self.exact:
            return 'exact'
        if text.lower() in self.lower:
            return 'case only'
        return 'none'

    def contained(self, text):
        return len({d.name for d in self.tables.defs + self.tables.presets if d.name and d.name in text})

    def factory(self, name):
        if name not in self._factory:
            self._factory[name] = factory_probe(self.elf, name)
        return self._factory[name]


def factory_probe(elf, name):
    """(pool size, constructor) the original world_objectFactory 0x159c94 picks for name, or
    (None, None) when it makes no object."""
    from ee_emu import EE
    emu = EE(elf)
    block = emu.alloc(0x1000)
    asked = []
    emu.stub(0x14FDB8, function=lambda e: asked.append(e.r[4] & 0xFFFFFFFF) or block)
    state = {'after': False, 'target': None}
    original = emu._enter_call

    def enter(target):
        if state['after'] and state['target'] is None:
            state['target'] = target
            emu.stub(target, ret=block)
        if target == 0x14FDB8:
            state['after'] = True
        return original(target)
    emu._enter_call = enter
    text = emu.alloc(len(name) + 1)
    emu.mem.write(text, name + b'\0')
    pos, props = emu.alloc(16), emu.alloc(16)
    emu.default_ret = 0
    try:
        emu.call(0x159C94, text, pos, 0, props, max_steps=3000000)
    except Exception:           # noqa: BLE001  stopped inside the factory: report as unknown
        return ('stopped', None)
    return (asked[0] if asked else None, state['target'])


def census(images, classifier):
    calls = {c: 0 for c in COMMANDS}
    levels = {c: 0 for c in COMMANDS}
    literal = {c: 0 for c in COMMANDS}
    nbytes = {}
    kinds = {}
    give_flags = {}
    gen_names = set()
    gen_per_script = 0
    gen_results = {}
    refused = 0
    for image in images:
        sites = call_sites(image)
        if sites is None:
            refused += 1
            continue
        seen, distinct = set(), set()
        for name, nb, lits, machine in sites:
            calls[name] += 1
            seen.add(name)
            nbytes[(name, nb)] = nbytes.get((name, nb), 0) + 1
            sig = KINDS.get(name, '')
            if lits and all(v is not None for v in lits[:len(sig)]) and len(lits) >= len(sig):
                literal[name] += 1
            if classifier is None or not lits:
                continue
            strings = [string_at(machine, lits[k]) if k < len(lits) and lits[k] is not None and sig[k] == 's'
                       else None for k in range(len(sig))]
            if name in ('playerHasItem', 'onePlayerHasItem', 'countQuestItems'):
                text = strings[sig.index('s')]
                key = (name, classifier.name_kind(text) if text is not None else 'not literal')
                kinds[key] = kinds.get(key, 0) + 1
            elif name == 'removePlayerItem':
                text = strings[1]
                n = classifier.contained(text) if text is not None else None
                label = 'not literal' if n is None else ('names none' if n == 0 else
                                                         'names one' if n == 1 else 'names several')
                kinds[(name, label)] = kinds.get((name, label), 0) + 1
            elif name in ('givePlayerItem', 'giveOnePlayerItem'):
                k0 = 0 if name == 'givePlayerItem' else 1
                text = strings[k0]
                equip = lits[k0 + 1] if k0 + 1 < len(lits) else None
                presets = lits[k0 + 2] if k0 + 2 < len(lits) else None
                give_flags[(name, 'equip', equip)] = give_flags.get((name, 'equip', equip), 0) + 1
                give_flags[(name, 'usePresets', presets)] = give_flags.get((name, 'usePresets', presets), 0) + 1
                if text is None:
                    label = 'not literal'
                elif presets:
                    label = 'preset found' if text in classifier.presets else 'preset row 0 (not found)'
                else:
                    label = 'definition found' if text.split(b'+')[0] in classifier.base else 'row 0 (not found)'
                kinds[(name, label)] = kinds.get((name, label), 0) + 1
            elif name == 'generateMonster':
                cls = strings[1]
                if cls is None:
                    kinds[(name, 'class not literal')] = kinds.get((name, 'class not literal'), 0) + 1
                    continue
                gen_names.add(cls)
                distinct.add(cls)
                size, ctor = classifier.factory(cls)
                label = 'no object' if size is None else ('stopped' if size == 'stopped' else 'constructor')
                gen_results[label] = gen_results.get(label, 0) + 1
                if ctor == SKELETON_CTOR:
                    gen_results['Skeleton constructor (rises, state 0x17)'] = \
                        gen_results.get('Skeleton constructor (rises, state 0x17)', 0) + 1
                if len(cls) >= 24:
                    gen_results['name of 24 bytes or more'] = gen_results.get('name of 24 bytes or more', 0) + 1
        for name in seen:
            levels[name] += 1
        gen_per_script = max(gen_per_script, len(distinct))
    return dict(calls=calls, levels=levels, literal=literal, nbytes=nbytes, kinds=kinds, give=give_flags,
                gen_distinct=len(gen_names), gen_per_script=gen_per_script, gen_results=gen_results,
                refused=refused, scripts=len(images))


def report(r, classifier):
    print('scripts %d' % r['scripts'])
    print('refused %d' % r['refused'])
    print('command calls scripts literal')
    for c in COMMANDS:
        print('%s %d %d %d' % (c, r['calls'][c], r['levels'][c], r['literal'][c]))
    print('argument bytes')
    for (c, nb), n in sorted(r['nbytes'].items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        print('%s %s %d' % (c, nb, n))
    if classifier is None:
        return
    print('classified')
    for (c, label), n in sorted(r['kinds'].items()):
        print('%s %s %d' % (c, label, n))
    for (c, what, value), n in sorted(r['give'].items(), key=lambda kv: (kv[0][0], kv[0][1], str(kv[0][2]))):
        print('%s %s=%s %d' % (c, what, value, n))
    print('generateMonster distinct class names %d' % r['gen_distinct'])
    print('generateMonster most distinct names in one script %d' % r['gen_per_script'])
    for label, n in sorted(r['gen_results'].items()):
        print('generateMonster factory %s %d' % (label, n))


def main(argv):
    elf = None
    if '--elf' in argv:
        elf = argv[argv.index('--elf') + 1]
    if '--disc' in argv:
        images, refused = images_from_disc(argv[argv.index('--disc') + 1])
    elif '--scripts' in argv:
        images, refused = images_from_dir(argv[argv.index('--scripts') + 1])
    else:
        print(__doc__)
        return 2
    classifier = Classifier(elf) if elf else None
    r = census(images, classifier)
    r['refused'] += refused
    report(r, classifier)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
