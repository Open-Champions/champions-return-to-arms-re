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
particle definitions it names with tools/fx_particle_defs.py --json, and the embedded light
records the StaticFire and SpellPlanarSteelEffect constructors fill (optional
`light_records` in the same JSON; see docs/effects.md 12.2).  The rules (counts, timings,
placement) are the models named in each row; tools/ref_fx_skills.py explains how their
call-outs map to primitives.

Standard library only; reads ghidra_funcs.tsv and the symbol files of this repository for
function bounds and names.  When that table lists no start in the requested range, bounds
are inferred from jal targets, prologues and the recipe-table addresses (without any
bounds the scan keeps no calls).  A constant that is live on a branch around an earlier
call is filled in when the straight-line walk left that slot empty.  Keep the output local.
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

# Symbolic object base for straight-line scans (a0 at entry).
_OBJ_BASE = 0x10000000

# Constructor functions whose embedded light nodes the native client reads from
# light_records (docs/lighting.md section 2; ref_skills_c.light_record).
LIGHT_CONSTRUCTORS = (
    ('StaticFire_ctor', 0x2C5240, 0x2C54F8, 0x80, True),
    ('StaticFire_ctor2', 0x2C54F8, 0x2C5770, 0x80, True),
    ('SpellPlanarSteelEffect_ctor', 0x2FB728, 0x2FB924, 0x30, False),
)

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


def recipe_addresses(recipes=None):
    recipes = FS.RECIPES if recipes is None else recipes
    return [p.addr for phases in recipes.values() for p in phases]


def function_starts(words, base, listed, lo, hi, extra=()):
    """Use listed bounds when any start falls in [lo, hi); otherwise infer them.

    An empty start list makes owner() drop every call (0 calls in the JSON).  Observed
    when the tool is run from a copy of tools/ that has no ghidra_funcs.tsv.
    """
    if any(lo <= s < hi for s in listed):
        return listed
    return FC.infer_starts(words, base, extra)


def scan(words, base, starts, names, read_u32=None, lo=SKILL_LO, hi=SKILL_HI):
    """Every effect call in [lo, hi): (function, name, site, primitive, args).

    The straight-line walk is the source of a value it already recovered.  path_states
    fills a register, float or stack slot that walk left empty, from the first path that
    reaches the call without falling through an earlier call.
    """
    raw = []
    for site, target, t in FC.scan_calls(words, base, set(FC.PRIMITIVES), read_u32):
        f = FC.owner(starts, site)
        if f is None or not lo <= f < hi:
            continue
        raw.append((f, site, target, t))
    paths = FC.path_states(words, base, starts, set(FC.PRIMITIVES), read_u32, lo, hi)
    rows = []
    for f, site, target, t in raw:
        FC.fill_unknown(t, paths.get(site))
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


class _LightStoreTracker(FD.Tracker):
    """Constant tracker that also records stores into a synthetic object image."""

    def __init__(self, read_u32=None):
        super().__init__(read_u32)
        self.mem = {}

    def _store(self, addr, size, value):
        if value is None:
            return
        self.mem[addr & 0xffffffff] = (size, value & ((1 << (8 * size)) - 1))

    def step(self, word):
        op = word >> 26
        rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        imm = word & 0xffff
        simm = imm - 0x10000 if imm & 0x8000 else imm
        g = self.r.get
        if op == 0x28:                                 # sb
            base = g(rs)
            if base is not None:
                self._store(base + simm, 1, g(rt))
        elif op == 0x29:                               # sh
            base = g(rs)
            if base is not None:
                self._store(base + simm, 2, g(rt))
        elif op in (0x2b, 0x3f):                        # sw, sd
            base = g(rs)
            if base is not None and rs != SP:
                self._store(base + simm, 4, g(rt))
            elif rs == SP:
                self.stack[simm] = g(rt)
        elif op == 0x39:                                # swc1
            base = g(rs)
            if base is not None and rs != SP:
                self._store(base + simm, 4, self.f.get(rt))
            elif rs == SP:
                self.stack[simm] = self.f.get(rt)
        return super().step(word)


SP = 29


def _walk_function(words, base, lo, hi, read_u32):
    """Straight-line scan of one function body (same branch rules as fx_callsites)."""
    i0 = (lo - base) // 4
    i1 = (hi - base) // 4
    chunk = words[i0:i1]
    t = _LightStoreTracker(read_u32)
    t.setr(4, _OBJ_BASE)
    i, n = 0, len(chunk)
    while i < n:
        w = chunk[i]
        br = FD.branch_kind(w)
        if br is not None:
            likely, eq = br
            if not likely and i + 1 < n:
                t.step(chunk[i + 1])
            if eq is not None:
                a, b = eq
                if t.r.get(a) is None and t.r.get(b) is not None:
                    t.setr(a, t.r[b])
                elif t.r.get(b) is None and t.r.get(a) is not None:
                    t.setr(b, t.r[a])
            i += 2
            continue
        res = t.step(w)
        if res is not None:
            kind, target = res
            if i + 1 < n:
                t.step(chunk[i + 1])
            if kind == 'call':
                t.forget_call()
            elif kind == 'jump':
                t = _LightStoreTracker(read_u32)
                t.setr(4, _OBJ_BASE)
            i += 2
            continue
        i += 1
    return t.mem


def _u16(mem, light_base, off):
    addr = light_base + off
    if addr not in mem or mem[addr][0] != 2:
        return None
    return mem[addr][1] & 0xffff


def _u32(mem, light_base, off):
    addr = light_base + off
    if addr not in mem or mem[addr][0] != 4:
        return None
    return mem[addr][1]


def decode_light_record(mem, light_offset, need_falloff):
    """Decode a 0x3c-byte embedded light node (position at +0x30 is runtime; omitted)."""
    lb = _OBJ_BASE + light_offset
    colour = [_u16(mem, lb, 0x0A + 2 * k) for k in range(4)]
    colour += [_u16(mem, lb, 0x12 + 2 * k) for k in range(4)]
    if any(v is None for v in colour):
        return None
    radius = _u32(mem, lb, 0x1C)
    if radius is None:
        radius = _u32(mem, lb, 0x24)
    if radius is None:
        return None
    extra = _u32(mem, lb, 0x2C)
    if extra is None:
        return None
    out = {'colour': colour, 'radius': FD.f32bits(radius), 'extra': FD.f32bits(extra)}
    if need_falloff:
        falloff = _u32(mem, lb, 0x20)
        if falloff is None:
            falloff = _u32(mem, lb, 0x28)
        if falloff is None:
            return None
        out['falloff'] = FD.f32bits(falloff)
    return out


def scan_light_records(words, text_base, read_u32=None, constructors=LIGHT_CONSTRUCTORS):
    """Read constant light-record fields from each listed constructor (observed stores)."""
    out = {}
    for name, lo, hi, light_off, need_falloff in constructors:
        mem = _walk_function(words, text_base, lo, hi, read_u32)
        rec = decode_light_record(mem, light_off, need_falloff)
        if rec is not None:
            out[name] = rec
    return out


def run(path, lo=SKILL_LO, hi=SKILL_HI, root=None):
    root = root or os.path.dirname(HERE)
    e = Elf(path)
    addr, off, size = e.text
    words = list(struct.unpack_from('<%dI' % (size // 4), e.d, off))

    def read_u32(va):
        return None if e.in_text(va) else e.u32(va)

    listed = FC.load_funcs(root)
    starts = function_starts(words, addr, listed, lo, hi, recipe_addresses())
    rows = scan(words, addr, starts, FC.load_names(root), read_u32, lo, hi)
    classes = build(rows)
    lights = scan_light_records(words, addr, read_u32)
    out = {'executable_sha256': hashlib.sha256(e.d).hexdigest(), 'range': [lo, hi],
           'classes': classes, 'particle_definitions': definitions(classes)}
    if lights:
        out['light_records'] = lights
    return out


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
