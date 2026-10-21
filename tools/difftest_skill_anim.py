#!/usr/bin/env python3
"""Original skill constructors vs ref_skill_anim.

Usage: python3 tools/difftest_skill_anim.py local/SLUS_209.73

Each constructor runs in tools/ee_emu.py. Callees are stubbed (the soft-float
band is not followed; following it does not reach the state store). The
player is zeroed, so the weapon class reads as 0. A step limit is a failure
except for SpellShadowStep_ctor, whose tail loops after the clip has started;
that call is accepted once the state and the push match, and its destructor
is then run on the same skill object.
"""
import sys
from ee_emu import EE, EmuError
from ps2elf import Elf
import ref_skill_anim as S

PLAYER, SKILL, DEF = 0x1400000, 0x1500000, 0x1600000
ANIM = {0x16cfe0: 'start', 0x16ceb0: 'bio', 0x170838: 'push',
        0x1708c0: 'push_w', 0x170938: 'chain'}
# sb, sh, sw, sd
STORE_OPS = (0x28, 0x29, 0x2b, 0x3f)


def harvest(ee, elf):
    anims = []
    names = []
    last = None
    for c in ee.calls:
        for arg in c.args[:4]:
            text = elf.cstr(arg & 0xffffffff) if arg else None
            if text and text.endswith('.anm') and text != last:
                last = text
                names.append(text)
        if c.target in ANIM:
            anims.append((ANIM[c.target], last, c.args[2] & 0xffffffff,
                          c.fargs[0] & 0xffffffff, c.fargs[1] & 0xffffffff))
    return anims, tuple(names)


def call_ctor(elf_path, fn, flags, follow, steps):
    ee = EE(elf_path)
    ee.mem.auto_map = True
    ee.follow = set(follow)
    ee.default_ret = 0x1080000
    m = ee.mem
    m.write(PLAYER, bytes(0x800))
    m.write(SKILL, bytes(0x200))
    m.write(DEF, bytes(0x40))
    m.store(PLAYER + 0x24, 4, DEF)
    m.store(PLAYER + 0xc, 4, flags)
    err = None
    try:
        ee.call(fn, SKILL, 1, PLAYER, 0, sp=EE.STACK_HI - 0x4000, max_steps=steps)
    except EmuError as e:
        err = e
    return ee, err


def check(label, cond, detail):
    check.n += 1
    if cond:
        return 0
    print('FAIL', label, detail)
    return 1


check.n = 0


def immediate(elf, site, window=48):
    """Constant stored by a word/half/byte at `site`, if the register was
    loaded with addiu/ori from $zero inside the window. None if computed."""
    word = elf.u32(site)
    rt = (word >> 16) & 31
    if rt == 0:
        return 0
    for back in range(1, window + 1):
        prev = elf.u32(site - 4 * back)
        if prev is None:
            return None
        op = prev >> 26
        rd = (prev >> 16) & 31
        if op == 9 and rd == rt:  # addiu
            if ((prev >> 21) & 31) != 0:
                return None
            imm = prev & 0xffff
            return imm - 0x10000 if imm & 0x8000 else imm
        if op == 0xd and rd == rt:  # ori
            if ((prev >> 21) & 31) != 0:
                return None
            return prev & 0xffff
        if op == 0:
            dest = (prev >> 11) & 31
            funct = prev & 63
            if dest == rt and funct in (0x21, 0x23, 0x25, 0x2b):
                return None
    return None


def scan_state_stores(elf):
    base, _, size = elf.text
    found = []
    for off in range(0, size, 4):
        word = elf.u32(base + off)
        if word >> 26 not in STORE_OPS:
            continue
        disp = word & 0xffff
        if disp & 0x8000:
            disp -= 0x10000
        if disp != 0x58c:
            continue
        site = base + off
        found.append((site, immediate(elf, site)))
    return found


def main():
    path = sys.argv[1]
    elf = Elf(path)
    failed = 0
    for row in S.STATE6:
        ee, err = call_ctor(path, row['fn'], 0x40, {row['fn']}, 80000)
        state = ee.mem.load(PLAYER + 0x58c, 4)
        anims, names = harvest(ee, elf)
        failed += check(row['name'], err is None, err)
        failed += check(row['name'] + ' state', state == 6, state)
        failed += check(row['name'] + ' anim', anims[:1] == [row['anim']], anims[:3])
        failed += check(row['name'] + ' names', names == row['names'], names)
    # Charge: flag 0x40 stores 9 and starts nothing; without it the state stays 0.
    for flags, expect in ((0x40, 9), (0, 0)):
        ee, err = call_ctor(path, S.CHARGE, flags, {S.CHARGE}, 40000)
        state = ee.mem.load(PLAYER + 0x58c, 4)
        anims, names = harvest(ee, elf)
        failed += check('charge %#x' % flags, err is None and state == expect
                        and anims == [] and names == (), (err, state, anims, names))
        failed += check('charge rule', S.charge_state(flags) == expect, flags)
    # Shadow step. The constructor loops after the push; stop there.
    ee, err = call_ctor(path, S.SHADOW_CTOR, 0x40, {S.SHADOW_CTOR, S.SHADOW_HELPER}, 20000)
    state = ee.mem.load(PLAYER + 0x58c, 4)
    flags = ee.mem.load(PLAYER + 0xc, 4)
    anims, names = harvest(ee, elf)
    failed += check('shadow ctor', isinstance(err, EmuError) and 'step limit' in str(err), err)
    failed += check('shadow state', state == S.SHADOW_STATE, state)
    failed += check('shadow flags', flags == S.SHADOW_FLAGS_AFTER_CTOR, hex(flags))
    failed += check('shadow anim', anims[:1] == [S.SHADOW_ANIM], anims[:2])
    failed += check('shadow name', S.SHADOW_CLIP in names, names)
    # Destructor, on the skill the constructor already filled in.
    ee.follow = {S.SHADOW_DTOR}
    ee.calls = []
    err = None
    try:
        ee.call(S.SHADOW_DTOR, SKILL, sp=EE.STACK_HI - 0x2000, max_steps=8000)
    except EmuError as e:
        err = e
    failed += check('shadow dtor', err is None, err)
    failed += check('shadow end state',
                    ee.mem.load(PLAYER + 0x58c, 4) == S.SHADOW_END_STATE,
                    ee.mem.load(PLAYER + 0x58c, 4))
    failed += check('shadow end flags',
                    ee.mem.load(PLAYER + 0xc, 4) == S.SHADOW_FLAGS_AFTER_DTOR,
                    hex(ee.mem.load(PLAYER + 0xc, 4)))
    # No direct store of the constant 7 into the action state.
    stores = scan_state_stores(elf)
    imms = [imm for _, imm in stores if imm is not None]
    failed += check('no constant 7', 7 not in imms, imms)
    failed += check('store count', len(stores) == 64, len(stores))
    known = {0x2d18f8: 6, 0x2de6c4: 6, 0x2e0c58: 6, 0x2fad68: 6,
             0x300204: 6, 0x3017e0: 6, 0x303318: 6,
             0x2c88e8: 9, 0x2c88f0: 9, 0x31173c: 14}
    got = dict(stores)
    for site, imm in known.items():
        failed += check('store %#x' % site, got.get(site) == imm, got.get(site))
    print('%d checks, %d failed' % (check.n, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
