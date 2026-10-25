#!/usr/bin/env python3
"""fx_callsites.py - which functions call the visual-effect primitives, and with which
constant arguments (docs/effects.md section 11).

  python3 -I fx_callsites.py <elf> map [lo hi]          # per function: primitive -> calls
  python3 -I fx_callsites.py <elf> args <primitive> [lo hi]

Primitives: particle LightEffect glow trail trailPoint beam beamUpdate decal fx_spawn
ringBurst modelVerts statusFx modelParticlesLight modelParticles lightLink lightLink2
particleGroup puff disintegrate iceShatter Fire.  `lo hi` limit the calling functions to an
address range (hex), e.g. 2c3cd4 320000 for the skill files.

Reads your own executable, ghidra_funcs.tsv (function bounds) and the symbol files of this
repository (names); prints addresses, names and the constant register / stack values at
each call, nothing else.  Function bounds: the call belongs to the function in
ghidra_funcs.tsv whose start is the highest one at or below the call.  When that file
lists no start in the requested range, bounds are inferred (infer_starts).  Arguments use
the constant tracker of fx_particle_defs.py.  scan_calls walks straight-line code only
(unknown values print as `?`).  path_states is a separate per-function walk that recovers
a constant the straight-line walk lost; fx_skill_recipes uses it to fill empty slots.
Keep the output local.
"""
import bisect
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ps2elf import Elf                                    # noqa: E402
import fx_particle_defs as FD                             # noqa: E402

PRIMITIVES = {
    0x18f3f8: 'particle', 0x201bd8: 'LightEffect', 0x18fc78: 'glow', 0x190ff8: 'trail',
    0x192550: 'trailPoint', 0x193088: 'beam', 0x1933c8: 'beamUpdate', 0x19f110: 'decal',
    0x1ef270: 'fx_spawn', 0x1f3d00: 'ringBurst', 0x1eb1e8: 'modelVerts', 0x1f6ac8: 'statusFx',
    0x1f61c0: 'modelParticlesLight', 0x1f5210: 'modelParticles', 0x148af8: 'lightLink',
    0x148bc8: 'lightLink2', 0x18e880: 'particleGroup', 0x1fc150: 'puff',
    0x1f4340: 'disintegrate', 0x1fb240: 'iceShatter', 0x2020e0: 'Fire',
}
BY_NAME = {v: k for k, v in PRIMITIVES.items()}

# What to print per primitive: (float registers, integer registers, stack offsets)
SIGNATURES = {
    'particle': ((12,), (4, 5, 6), ()),
    'LightEffect': (tuple(range(12, 20)), (4, 5, 6, 7), (0x00, 0x08, 0x10, 0x18)),
    'glow': ((12, 13), (4, 5, 6, 7, 8, 9, 10, 11), ()),
    'trail': ((12,), (4, 5, 6, 7, 8, 9, 10), ()),
    'beam': ((12, 13), (4, 5, 6, 7, 8), ()),
    'decal': ((12,), (4, 5, 6, 7), ()),
    'fx_spawn': ((), (4, 5), ()),
}
STACK_FLOATS = {'LightEffect'}      # radius0, radius1, floor, seconds are floats
REG_NAMES = {4: 'a0', 5: 'a1', 6: 'a2', 7: 'a3', 8: 't0', 9: 't1', 10: 't2', 11: 't3'}


def load_names(root):
    names = {}
    try:
        import symtab
        for addr, name, _note, _f, _n in symtab.rows(root):
            if addr is not None and addr not in names:
                names[addr] = name
    except Exception:                                    # names are a convenience only
        pass
    return names


def load_funcs(root):
    starts = []
    path = os.path.join(root, 'ghidra_funcs.tsv')
    if os.path.exists(path):
        for line in open(path, encoding='utf-8', errors='replace'):
            if line.strip() and not line.startswith('#'):
                starts.append(int(line.split('\t')[0], 16))
    return sorted(starts)


def infer_starts(words, base, extra=()):
    """Function starts when ghidra_funcs.tsv is not available.

    A start is a jal target, an address in extra that lands on an instruction, or the
    first non-zero word after jr ra when that word is addiu/daddiu sp, sp, -N.  Observed:
    with no starts at all, scan_calls still finds calls but owner() drops every one.
    """
    n = len(words)
    text_lo, text_hi = base, base + 4 * n
    starts = set()
    for addr in extra:
        if text_lo <= addr < text_hi and (addr - base) % 4 == 0:
            starts.add(addr)
    for i, w in enumerate(words):
        pc = base + 4 * i
        if w >> 26 == 3:                                 # jal
            tgt = (pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
            if text_lo <= tgt < text_hi:
                starts.add(tgt)
        if w == 0x03E00008:                              # jr ra
            j = i + 2
            while j < n and words[j] == 0:
                j += 1
            if j < n and (words[j] & 0xFFFF8000) in (0x27BD8000, 0x67BD8000):
                starts.add(base + 4 * j)
    return sorted(starts)


def owner(starts, addr):
    i = bisect.bisect_right(starts, addr) - 1
    return starts[i] if i >= 0 else None


def scan_calls(words, base, targets, read_u32=None):
    """Yield (site, target, tracker) for every jal to one of `targets`, with the tracker
    state after the delay slot (the same walk as fx_particle_defs.scan_words)."""
    t = FD.Tracker(read_u32)
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        br = FD.branch_kind(w)
        if br is not None:
            likely, eq = br
            if not likely and i + 1 < n:
                t.step(words[i + 1])
            if eq is not None:
                a, b = eq
                if t.r.get(a) is None and t.r.get(b) is not None:
                    t.setr(a, t.r[b])
                elif t.r.get(b) is None and t.r.get(a) is not None:
                    t.setr(b, t.r[a])
            i += 2
            continue
        res = t.step(w)
        if res is None:
            i += 1
            continue
        kind, target = res
        if i + 1 < n:
            t.step(words[i + 1])
        if kind == 'call' and target in targets:
            snap = FD.Tracker(read_u32)
            snap.r, snap.f, snap.stack = dict(t.r), dict(t.f), dict(t.stack)
            yield base + 4 * i, target, snap
        if kind == 'call':
            t.forget_call()
        elif kind == 'jump':
            t = FD.Tracker(read_u32)
        i += 2


def _clone_tracker(t):
    n = FD.Tracker(t.read_u32)
    n.r, n.f, n.stack = dict(t.r), dict(t.f), dict(t.stack)
    return n


def _branch_index(pc, word, base):
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    return (pc + 4 + simm * 4 - base) // 4


def path_states(words, base, starts, targets, read_u32=None, lo=0, hi=1 << 32):
    """Per-function walk.  Returns {call site: tracker after the delay slot}.

    The straight-line walk falls into a call that a branch skips, then forget_call drops
    registers that are still live on the branch.  This walk does not replace that result:
    the first path to reach an instruction wins, and the caller copies a value only into
    a slot the straight-line walk left empty.  A function is one span between consecutive
    starts.  jal is not followed.  jr ends the path.  An unconditional beq/beql (both
    registers the same) does not fall through.
    """
    n = len(words)
    text_lo, text_hi = base, base + 4 * n
    bounds = sorted(s for s in set(starts) if text_lo <= s < text_hi and (s - base) % 4 == 0)
    if not bounds:
        return {}
    bounds.append(text_hi)
    targets = set(targets)
    out = {}
    for b0, b1 in zip(bounds, bounds[1:]):
        if b1 <= lo or b0 >= hi:
            continue
        _walk_paths(words, base, (b0 - base) // 4, (b1 - base) // 4, targets, read_u32, out)
    return out


def _walk_paths(words, base, i0, i1, targets, read_u32, out):
    seen = set()
    work = [(i0, FD.Tracker(read_u32))]
    budget = max(1, (i1 - i0) * 4 + 8)
    while work and budget > 0:
        i, t = work.pop()
        while i0 <= i < i1 and i not in seen and budget > 0:
            budget -= 1
            seen.add(i)
            w = words[i]
            pc = base + 4 * i
            if (w >> 26) == 0 and (w & 0x3F) == 8:       # jr
                if i + 1 < i1:
                    t.step(words[i + 1])
                break
            br = FD.branch_kind(w)
            if br is not None:
                likely, eq = br
                op = w >> 26
                rs, rt = (w >> 21) & 31, (w >> 16) & 31
                dest = _branch_index(pc, w, base)
                taken = _clone_tracker(t)
                if i + 1 < i1:
                    taken.step(words[i + 1])
                if i0 <= dest < i1 and dest not in seen:
                    work.append((dest, taken))
                if op in (0x04, 0x14) and rs == rt:      # always taken
                    break
                if not likely and i + 1 < i1:
                    t.step(words[i + 1])
                if eq is not None:
                    a, b = eq
                    if t.r.get(a) is None and t.r.get(b) is not None:
                        t.setr(a, t.r[b])
                    elif t.r.get(b) is None and t.r.get(a) is not None:
                        t.setr(b, t.r[a])
                i += 2
                continue
            res = t.step(w)
            if res is None:
                i += 1
                continue
            kind, target = res
            if i + 1 < i1:
                t.step(words[i + 1])
            if kind == 'call':
                if target in targets:
                    out[pc] = _clone_tracker(t)
                t.forget_call()
                i += 2
                continue
            if kind == 'jump':
                dest_addr = (pc & 0xF0000000) | (target & 0x0FFFFFFF)
                di = (dest_addr - base) // 4
                if i0 <= di < i1 and di not in seen:
                    i = di
                    continue
                break
            i += 2


def fill_unknown(dest, src):
    """Copy constants into slots dest does not already have."""
    if src is None:
        return
    for key, value in src.r.items():
        if key not in dest.r and value is not None:
            dest.r[key] = value
    for key, value in src.f.items():
        if key not in dest.f and value is not None:
            dest.f[key] = value
    for key, value in src.stack.items():
        if key not in dest.stack and value is not None:
            dest.stack[key] = value


def describe_args(prim, t):
    fregs, iregs, stack = SIGNATURES.get(prim, ((), (), ()))
    parts = []
    for fr in fregs:
        v = t.f.get(fr)
        parts.append('f%d=%s' % (fr, '?' if v is None else '%g' % FD.f32bits(v)))
    for r in iregs:
        v = t.r.get(r)
        parts.append('%s=%s' % (REG_NAMES[r], '?' if v is None else '%#x' % v))
    for off in stack:
        v = t.stack.get(off)
        if v is None:
            txt = '?'
        elif prim in STACK_FLOATS:
            txt = '%g' % FD.f32bits(v)
        else:
            txt = '%#x' % v
        parts.append('sp+%#x=%s' % (off, txt))
    return ' '.join(parts)


def run(path, mode, prim=None, lo=0, hi=1 << 32, root=None):
    root = root or os.path.dirname(HERE)
    e = Elf(path)
    addr, off, size = e.text
    words = list(struct.unpack_from('<%dI' % (size // 4), e.d, off))
    names = load_names(root)
    starts = load_funcs(root)
    if not any(lo <= s < hi for s in starts):
        starts = infer_starts(words, addr)

    def read_u32(va):
        return None if e.in_text(va) else e.u32(va)

    targets = set(PRIMITIVES) if mode == 'map' else {BY_NAME[prim]}
    out = []
    for site, target, t in scan_calls(words, addr, targets, read_u32):
        f = owner(starts, site)
        if f is None or not lo <= f < hi:
            continue
        out.append((f, names.get(f, ''), site, PRIMITIVES[target],
                    describe_args(PRIMITIVES[target], t) if mode == 'args' else ''))
    return out


def summarise(rows):
    per = {}
    for f, name, _site, prim, _a in rows:
        per.setdefault((f, name), {}).setdefault(prim, 0)
        per[(f, name)][prim] += 1
    return per


def main(argv):
    if len(argv) < 3 or argv[2] not in ('map', 'args'):
        print(__doc__)
        return 2
    mode = argv[2]
    rest = argv[3:]
    prim = None
    if mode == 'args':
        if not rest or rest[0] not in BY_NAME:
            print('primitive must be one of: ' + ' '.join(sorted(BY_NAME)))
            return 2
        prim, rest = rest[0], rest[1:]
    lo, hi = (int(rest[0], 16), int(rest[1], 16)) if len(rest) >= 2 else (0, 1 << 32)
    rows = run(argv[1], mode, prim, lo, hi)
    if mode == 'map':
        for (f, name), counts in sorted(summarise(rows).items()):
            print('%08x\t%s\t%s' % (f, name or '?', ' '.join('%s:%d' % kv for kv in sorted(counts.items()))))
    else:
        for f, name, site, _p, args in rows:
            print('%08x\t%s\t%08x\t%s' % (f, name or '?', site, args))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
