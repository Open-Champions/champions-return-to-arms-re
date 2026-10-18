#!/usr/bin/env python3
"""fx_skill_recipes.py - the visual recipe of every effect class of the skill files, with
the constant arguments of each effect call read from YOUR executable (docs/effects.md
section 11).

  python3 -I fx_skill_recipes.py <elf> [--json] [--class NAME] [lo hi]

For each class (the prefix of its functions' names) it prints the rows of
ref_fx_skills.RECIPES - phase, function, the model that reproduces it, the generators it
draws from - and then every call to an effect primitive in those functions with the values
the registers and stack slots hold at the call when the code makes them constants:
particle definition addresses, LightEffect colours / radii / floor / seconds, glow colours,
alphas, flags and texture words, trail rows, widths, flags, colours and lifetimes, decal
types, fx_spawn ids.  Unknown (computed) values are '?' in text and null in JSON.  The
default range is the skill files, 0x2c3cd4-0x320000.

This is how a native client gets the VALUES at run time without anyone copying them into
a repository: run it on the user's executable, keep the JSON outside the checkout, load the
particle definitions it names with tools/fx_particle_defs.py --json.  The rules (counts,
timings, placement) are the models named in each row; tools/ref_fx_skills.py explains how
their call-outs map to primitives.

Standard library only; reads ghidra_funcs.tsv and the symbol files of this repository for
function bounds and names.  Keep the output local.
"""
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fx_callsites as FC                       # noqa: E402
import fx_particle_defs as FD                   # noqa: E402
import ref_fx_skills as FS                      # noqa: E402
from ps2elf import Elf                          # noqa: E402

SKILL_LO, SKILL_HI = 0x2C3CD4, 0x320000
REG_NAMES = {4: 'a0', 5: 'a1', 6: 'a2', 7: 'a3', 8: 't0', 9: 't1', 10: 't2', 11: 't3'}

# what each argument means, per primitive (the order of fx_callsites.SIGNATURES)
MEANING = {
    'particle': {'f12': 'backdate', 'a0': 'definition', 'a1': 'position*', 'a2': 'velocity*'},
    'LightEffect': {'a0': 'block', 'a1': 'position*', 'a2': 'follow', 'a3': 'flag',
                    'f12': 'r0', 'f13': 'g0', 'f14': 'b0', 'f15': 'a0', 'f16': 'r1', 'f17': 'g1', 'f18': 'b1',
                    'f19': 'a1', 'sp+0x0': 'radius0', 'sp+0x8': 'radius1', 'sp+0x10': 'floor', 'sp+0x18': 'seconds'},
    'glow': {'f12': 'bias', 'f13': 'size', 'a0': 'position*', 'a1': 'r', 'a2': 'g', 'a3': 'b', 't0': 'alpha',
             't1': 'texture', 't2': 'angle', 't3': 'flags'},
    'trail': {'f12': 'lifetime', 'a0': 'row', 'a1': 'width', 'a2': 'flags', 'a3': 'r', 't0': 'g', 't1': 'b', 't2': 'a'},
    'beam': {'f12': 'jitter', 'f13': 'scale', 'a0': 'from*', 'a1': 'to*', 'a2': 'width', 'a3': 'depth', 't0': 'rgba'},
    'decal': {'f12': 'size', 'a0': 'position*', 'a1': 'angle', 'a2': 'type', 'a3': 'grow'},
    'fx_spawn': {'a0': 'id', 'a1': 'position*'},
}


def structured_args(prim, tracker):
    """{register or stack slot: value} for one call: integers as ints, float registers
    and float stack slots as floats, None when the code computes the value."""
    fregs, iregs, stack = FC.SIGNATURES.get(prim, ((), (), ()))
    out = {}
    for fr in fregs:
        v = tracker.f.get(fr)
        out['f%d' % fr] = None if v is None else FD.f32bits(v)
    for r in iregs:
        v = tracker.r.get(r)
        out[REG_NAMES[r]] = None if v is None else v & 0xFFFFFFFF
    for off in stack:
        v = tracker.stack.get(off)
        key = 'sp+%#x' % off
        if v is None:
            out[key] = None
        else:
            out[key] = FD.f32bits(v) if prim in FC.STACK_FLOATS else v & 0xFFFFFFFF
    return out


def class_of(name):
    return name.split('_', 1)[0] if name else ''


def scan(words, base, starts, names, read_u32=None, lo=SKILL_LO, hi=SKILL_HI):
    """Every effect call in [lo, hi): (function, name, site, primitive, args)."""
    rows = []
    for site, target, t in FC.scan_calls(words, base, set(FC.PRIMITIVES), read_u32):
        f = FC.owner(starts, site)
        if f is None or not lo <= f < hi:
            continue
        prim = FC.PRIMITIVES[target]
        rows.append((f, names.get(f, ''), site, prim, structured_args(prim, t)))
    return rows


def build(rows, recipes=None):
    """Group scanned calls by class and attach the recipe rows."""
    recipes = FS.RECIPES if recipes is None else recipes
    out = {}
    for f, name, site, prim, args in rows:
        cls = class_of(name) or '%08x' % f
        entry = out.setdefault(cls, {'phases': [], 'calls': []})
        entry['calls'].append({'function': name or '%08x' % f, 'address': f, 'site': site, 'primitive': prim,
                               'args': args, 'meaning': {k: MEANING.get(prim, {}).get(k, '') for k in args}})
    for cls, phases in recipes.items():
        entry = out.setdefault(cls, {'phases': [], 'calls': []})
        entry['phases'] = [{'phase': p.phase, 'function': p.function, 'address': p.addr, 'model': p.model,
                            'calls_in_code': p.calls, 'generators': p.generators.split()} for p in phases]
    return out


def definitions(classes):
    """The particle definition addresses the classes pass as constants."""
    out = set()
    for entry in classes.values():
        for call in entry['calls']:
            if call['primitive'] == 'particle' and call['args'].get('a0') is not None:
                out.add(call['args']['a0'])
    return sorted(out)


def run(path, lo=SKILL_LO, hi=SKILL_HI, root=None):
    root = root or os.path.dirname(HERE)
    e = Elf(path)
    addr, off, size = e.text
    words = list(struct.unpack_from('<%dI' % (size // 4), e.d, off))

    def read_u32(va):
        return None if e.in_text(va) else e.u32(va)

    rows = scan(words, addr, FC.load_funcs(root), FC.load_names(root), read_u32, lo, hi)
    classes = build(rows)
    return {'executable_sha256': hashlib.sha256(e.d).hexdigest(), 'range': [lo, hi],
            'classes': classes, 'particle_definitions': definitions(classes)}


def fmt(v):
    if v is None:
        return '?'
    if isinstance(v, float):
        return '%g' % v
    return '%#x' % v


def text(result, only=None):
    lines = []
    for cls in sorted(result['classes']):
        if only and cls != only:
            continue
        entry = result['classes'][cls]
        lines.append(cls)
        for p in entry['phases']:
            lines.append('  %-5s %-34s %08x  %-48s %s' % (p['phase'], p['function'], p['address'], p['model'],
                                                           ' '.join(p['generators'])))
        for c in entry['calls']:
            args = ' '.join('%s=%s' % (k if not c['meaning'].get(k) else c['meaning'][k], fmt(v))
                            for k, v in c['args'].items())
            lines.append('    %08x %-34s %-11s %s' % (c['site'], c['function'], c['primitive'], args))
    return '\n'.join(lines)


def main(argv):
    args = list(argv[1:])
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return 0 if args else 2
    path = args.pop(0)
    as_json = '--json' in args
    only = None
    if '--class' in args:
        i = args.index('--class')
        only = args[i + 1]
        del args[i:i + 2]
    args = [a for a in args if a != '--json']
    lo, hi = (int(args[0], 16), int(args[1], 16)) if len(args) >= 2 else (SKILL_LO, SKILL_HI)
    if not os.path.exists(path):
        print('no executable at %s' % path)
        return 2
    result = run(path, lo, hi)
    if as_json:
        if only:
            result['classes'] = {k: v for k, v in result['classes'].items() if k == only}
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        print(text(result, only))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
