#!/usr/bin/env python3
"""fx_particle_defs.py - list the particle definitions an executable builds with constant
arguments, by reading the argument set-up before every call of particleDef_ctor 0x18f3d0,
particleDef_init 0x18ee70 and particleDef_set 0x18f118 (docs/effects.md section 2).

  python3 -I fx_particle_defs.py <elf> [--json] [--all]

Reads your own SLUS_209.73; prints one line (or JSON object) per call site: the call
address, the definition's address, the 16 arguments and what they mean (life ticks, kind,
texture cell, sizes, colours).  Nothing from the game is stored in this file.  Output is
for local use (for example a native client's build step); do not commit it.

How: the executable's .text is walked once in address order with a small constant
tracker.  It follows lui / ori / addiu / daddiu / moves through $zero, sw / sd to the
stack pointer, mtc1, mov.s, cvt.s.w, and lwc1 from a constant address (read from the
file).  Any other write makes the register unknown; any other call forgets the
caller-saved registers.  Branches are ignored, which is right for the straight-line
static initialisers that make almost all definitions.  A call site whose arguments are not
all known is printed with `?` (or omitted unless --all) instead of guessed.

Calling convention (PS2 EABI, as particleDef_init reads it): f12 f13 f14 = sizeStart,
sizeEnd, gravity; a0 = definition; a1..t3 = r0 g0 b0 a0 r1 g1 b1; stack +0x00 a1 (end
alpha), +0x08 lifeClass, +0x10 kind, +0x18 tile, +0x20 callback.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps2elf import Elf                                    # noqa: E402

DEF_CTOR, DEF_INIT, DEF_SET = 0x18f3d0, 0x18ee70, 0x18f118
TARGETS = {DEF_CTOR: 'particleDef_ctor', DEF_INIT: 'particleDef_init', DEF_SET: 'particleDef_set'}
LIFE_TICKS = (11, 30, 60, 90)
KINDS = ('blend', 'add', 'line', 'hidden')
SP = 29
CALLER_SAVED = [r for r in range(1, 26) if not 16 <= r <= 23] + [31]
STACK_ARGS = (0x00, 0x08, 0x10, 0x18, 0x20)
INT_ARGS = (4, 5, 6, 7, 8, 9, 10, 11)


def f32bits(bits):
    return struct.unpack('<f', struct.pack('<I', bits & 0xffffffff))[0]


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


class Tracker:
    """Registers: dict reg -> 32-bit value (unknown = absent).  f: dict freg -> bits.
    stack: dict sp offset -> value."""

    def __init__(self, read_u32=None):
        self.r = {0: 0}
        self.f = {}
        self.stack = {}
        self.read_u32 = read_u32

    def setr(self, reg, val):
        if reg == 0:
            return
        if val is None:
            self.r.pop(reg, None)
        else:
            self.r[reg] = val & 0xffffffff

    def forget_call(self):
        for reg in CALLER_SAVED:
            self.r.pop(reg, None)
        for fr in range(20):
            self.f.pop(fr, None)

    def step(self, word):
        """Apply one instruction (not a call).  Returns ('call', target) for jal/j."""
        op = word >> 26
        rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        imm = word & 0xffff
        simm = imm - 0x10000 if imm & 0x8000 else imm
        g = self.r.get
        if op == 0x03 or op == 0x02:
            return ('call' if op == 3 else 'jump', (word & 0x3ffffff) << 2)
        if op == 0x0f:                                   # lui
            self.setr(rt, imm << 16)
        elif op == 0x0d:                                 # ori
            self.setr(rt, None if g(rs) is None else g(rs) | imm)
        elif op in (0x09, 0x19):                         # addiu, daddiu
            self.setr(rt, None if g(rs) is None else g(rs) + simm)
        elif op == 0x00:                                 # SPECIAL
            funct = word & 0x3f
            if funct in (0x21, 0x2d, 0x25) and (rs == 0 or rt == 0):   # move
                src = rt if rs == 0 else rs
                self.setr(rd, g(src))
            elif funct in (0x08, 0x09, 0x0c, 0x0d, 0x0f):  # jr, jalr, syscall, break, sync
                if funct == 0x09:
                    self.setr(rd, None)
                    return ('call', None)
            else:
                self.setr(rd, None)
        elif op in (0x2b, 0x3f):                         # sw, sd
            if rs == SP:
                self.stack[simm] = g(rt)
        elif op == 0x39:                                 # swc1 to the stack: float slot
            if rs == SP:
                self.stack[simm] = self.f.get(rt)
        elif op == 0x11:                                 # COP1
            fmt = rs
            ft, fs, fd = rt, rd, (word >> 6) & 31
            funct = word & 0x3f
            if fmt == 0x04:                              # mtc1 rt -> fs
                self.f[fs] = g(rt)
                if self.f[fs] is None:
                    del self.f[fs]
            elif fmt == 0x00:                            # mfc1
                self.setr(rt, self.f.get(fs))
            elif fmt == 0x10 and funct == 0x06:          # mov.s
                self._setf(fd, self.f.get(fs))
            elif fmt == 0x14 and funct == 0x20:          # cvt.s.w
                v = self.f.get(fs)
                self._setf(fd, None if v is None else
                           struct.unpack('<I', struct.pack('<f', float(s32(v))))[0])
            elif fmt in (0x10, 0x14):
                self._setf(fd, None)
            elif fmt in (0x02, 0x06):                    # cfc1 / ctc1
                if fmt == 0x02:
                    self.setr(rt, None)
        elif op == 0x31:                                 # lwc1
            base = g(rs)
            v = None
            if base is not None and self.read_u32 is not None:
                v = self.read_u32((base + simm) & 0xffffffff)
            self._setf(rt, v)
        elif op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x37, 0x1e, 0x1a, 0x1b, 0x22, 0x26,
                    0x08, 0x0a, 0x0b, 0x0c, 0x0e, 0x18, 0x1f):
            self.setr(rt, None)                          # loads and other ALU writes to rt
        elif op == 0x1c:                                 # MMI
            self.setr(rd, None)
        return None

    def _setf(self, fr, v):
        if v is None:
            self.f.pop(fr, None)
        else:
            self.f[fr] = v

    def call_args(self):
        floats = [self.f.get(12), self.f.get(13), self.f.get(14)]
        ints = [self.r.get(r) for r in INT_ARGS]
        stack = [self.stack.get(o) for o in STACK_ARGS]
        return floats, ints, stack


def describe(site, kind, floats, ints, stack):
    known = all(v is not None for v in floats + ints + stack)
    rec = {'site': site, 'call': TARGETS[kind], 'def': ints[0], 'complete': known}
    if floats[0] is not None:
        rec['size_start'] = f32bits(floats[0])
    if floats[1] is not None:
        rec['size_end'] = f32bits(floats[1])
    if floats[2] is not None:
        rec['gravity'] = f32bits(floats[2])
    rgba0 = ints[1:5]
    rgba1 = ints[5:8] + [stack[0]]
    rec['start_rgba'] = [None if v is None else s32(v) for v in rgba0]
    rec['end_rgba'] = [None if v is None else s32(v) for v in rgba1]
    lc, kd, tile, cb = stack[1:5]
    if lc is not None:
        lc = min(max(s32(lc), 0), 3)
        rec['life_class'] = lc
        rec['life_ticks'] = LIFE_TICKS[lc]
    if kd is not None:
        kd = min(max(s32(kd), 0), 3)
        rec['kind'] = kd
        rec['kind_name'] = KINDS[kd]
    if tile is not None:
        rec['tile'] = s32(tile)
    if cb is not None:
        rec['callback'] = cb
    return rec


def branch_kind(word):
    """None for a non-branch; else (likely, (rs, rt) for bne / bnel or None).  The walk
    takes the fall-through path, where a likely branch's delay slot does not run."""
    op = word >> 26
    rs, rt = (word >> 21) & 31, (word >> 16) & 31
    if op in (0x04, 0x06, 0x07):
        return (False, None)
    if op == 0x05:
        return (False, (rs, rt))
    if op in (0x14, 0x16, 0x17):
        return (True, None)
    if op == 0x15:
        return (True, (rs, rt))
    if op == 0x01 and rt in (0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x13):
        return (bool(rt & 2), None)
    if op == 0x11 and rs == 0x08:                        # bc1f / bc1t (likely: bit 1 of rt)
        return (bool(rt & 2), None)
    return None


def scan_words(words, base, read_u32=None):
    """words: list of 32-bit instruction words starting at address base.  Yields the
    described call sites, in address order."""
    t = Tracker(read_u32)
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        br = branch_kind(w)
        if br is not None:
            likely, eq_regs = br
            if not likely and i + 1 < n:
                t.step(words[i + 1])                     # the delay slot always runs
            if eq_regs is not None:                      # fall-through of bne: rs == rt
                a, b = eq_regs
                if t.r.get(a) is None and t.r.get(b) is not None:
                    t.setr(a, t.r[b])
                elif t.r.get(b) is None and t.r.get(a) is not None:
                    t.setr(b, t.r[a])
            i += 2                                       # a likely branch's slot is skipped
            continue
        res = t.step(w)
        if res is None:
            i += 1
            continue
        kind, target = res
        site = base + 4 * i
        if i + 1 < n:                                    # the delay slot runs first
            t.step(words[i + 1])
        if target in TARGETS:
            yield describe(site, target, *t.call_args())
        if kind == 'call':
            t.forget_call()
        elif kind == 'jump' and target not in TARGETS:
            t = Tracker(read_u32)                        # a plain jump ends straight-line code
        i += 2


def scan_elf(path):
    e = Elf(path)
    addr, off, size = e.text
    words = list(struct.unpack_from('<%dI' % (size // 4), e.d, off))

    def read_u32(va):
        if e.in_text(va):
            return None
        return e.u32(va)

    return list(scan_words(words, addr, read_u32))


def fmt_line(r):
    def h(v):
        return '?' if v is None else '%x' % v
    def fl(k):
        return '?' if k not in r else '%g' % r[k]
    rgba = lambda c: ','.join('?' if v is None else str(v) for v in c)
    return '\t'.join([
        '%08x' % r['site'], r['call'], h(r['def']),
        fl('size_start'), fl('size_end'), fl('gravity'),
        rgba(r['start_rgba']), rgba(r['end_rgba']),
        str(r.get('life_ticks', '?')), r.get('kind_name', '?'),
        '?' if 'tile' not in r else '%d' % r['tile'],
        'ok' if r['complete'] else 'partial'])


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rows = scan_elf(argv[1])
    if '--all' not in argv:
        rows = [r for r in rows if r['complete']]
    if '--json' in argv:
        json.dump(rows, sys.stdout, indent=1)
        print()
        return 0
    print('# site\tcall\tdef\tsizeStart\tsizeEnd\tgravity\tstartRGBA\tendRGBA\tlife\tkind\ttile\tstate')
    for r in rows:
        print(fmt_line(r))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
