#!/usr/bin/env python3
"""difftest_player_init.py - what player_initNewCharacter 0x1b1d70 leaves in a record, and
what the first player_recalcStats 0x1b6458 with a Player object present makes of it.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_player_init.py [path/to/SLUS_209.73]

The ORIGINAL init runs in tools/ee_emu.py with every callee real (item descriptor parser,
inventory, equip, recalc: about 140,000 instructions for one character), for each of the 12
models, with the class start statistics (stat pointer null) and with four caller statistics.
g_numPlayers is 1.  Nothing else is stubbed.  Then record +0x43d8 (the Player object) is set
to a placeholder block and player_recalcStats runs for real; its one object-dependent query,
SkillNaturalResistance_getStat0Fraction 0x308a7c (armour and resistances only), is stubbed.

Properties (aggregate counts only; nothing from the executable is printed):
  init-record   after init: experience 0, level 1, acknowledged level 1, gold 500, class from
                the model, effective statistics = base statistics = the caller's or the class
                row, maximum hit points 0.0, maximum mana 10.0, current hit points and mana
                both the float 0x4e6e6b27, player object pointer null, 4 items equipped.
  init-recalc   player_recalcStats is called from init at 0x1b23f8 while the object pointer
                is null, and leaves the maxima alone (it skips them for a slot without an
                object, as tools/ref_combat.py recalc_stats says).
  gear          after recalc with the object present, effective statistics still equal the
                base ones: no starting item carries a statistic modifier 7..10.
  maxima        maximum hit points and mana equal ref_combat's formula (the class chain read
                from the executable, operations in recalcStats' order) bit for bit.
  currents      both current values were trimmed to their maxima.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE                           # noqa: E402
import ref_combat as R                          # noqa: E402

REC = 0x4D8AF0
NUM_PLAYERS = 0x4D8AE0
INIT, RECALC, FRACTION = 0x1B1D70, 0x1B6458, 0x308A7C
SENTINEL = 0x4E6E6B27
MODEL_CLASS = (0, 0, 3, 3, 1, 1, 4, 4, 2, 2, 5, 6)
SPREADS = (None, (46, 37, 24, 28), (5, 5, 5, 5), (127, 127, 127, 127), (26, 60, 1, 90))


def run_case(exe, model, spread):
    e = EE(exe)
    e.mem.auto_map = True
    e.follow = None                      # every callee real
    e.mem.w32(NUM_PLAYERS, 1)
    name = e.alloc(32)
    e.mem.write(name, b'Synthetic\0')
    sp = e.r[29]
    for offset, value in ((0, 0xFFFFFFFF), (4, 0xFFFFFFFF), (8, 0), (12, 0)):
        e.mem.w32(sp + offset, value)    # ninth argument -1: default character kind
    stats = 0
    if spread is not None:
        stats = e.alloc(16)
        e.mem.write(stats, bytes(spread))
    # a0 slot, a1 model, a2 name, a3..t2 appearance bytes (-1), t3 pointer to 4 stat bytes
    e.call(INIT, 0, model, name, 0xFF, 0xFF, 0xFF, 0xFF, stats, max_steps=30000000)
    g = lambda off: e.mem.u32(REC + off)                         # noqa: E731
    init_calls = [(c.site, c.target) for c in e.calls]
    after_init = {
        'exp': g(0x5C), 'level': e.mem.u8(REC + 0x59), 'ack': e.mem.u8(REC + 0x58),
        'gold': g(0xE4), 'cls': g(0x50), 'base': [g(0x78 + 4 * i) for i in range(4)],
        'eff': [g(0x90 + 4 * i) for i in range(4)], 'max_hp': g(0xB0), 'max_mana': g(0xC4),
        'hp': g(0xAC), 'mana': g(0xC0), 'obj': g(0x43D8),
        'equipped': sum(1 for i in range(17) if g(0x43F0 + 4 * i)),
    }
    obj = e.alloc(0x1000)
    e.mem.w32(REC + 0x43D8, obj)
    e.stub(FRACTION, ret=0)
    e.reset_log()
    e.call(RECALC, max_steps=5000000)
    after_recalc = {
        'eff': [g(0x90 + 4 * i) for i in range(4)], 'max_hp': g(0xB0), 'max_mana': g(0xC4),
        'hp': g(0xAC), 'mana': g(0xC0), 'level': e.mem.u8(REC + 0x59), 'cls': g(0x50),
    }
    return init_calls, after_init, after_recalc


def main():
    path = None
    for arg in sys.argv[1:]:
        if not arg.startswith('-'):
            path = arg
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'local', 'SLUS_209.73')
    if not os.path.exists(path):
        print('SLUS_209.73 not found (%s): nothing to compare.' % path)
        return 0
    tables = R.Exe(path) if hasattr(R, 'Exe') else None
    counts = {'cases': 0, 'init-record': 0, 'init-recalc': 0, 'gear': 0, 'maxima': 0, 'currents': 0}
    for model in range(12):
        for spread in SPREADS:
            init_calls, a, b = run_case(path, model, spread)
            counts['cases'] += 1
            want = list(spread) if spread is not None else None
            ok = (a['exp'] == 0 and a['level'] == 1 and a['ack'] == 1 and a['gold'] == 500
                  and a['cls'] == MODEL_CLASS[model] and a['eff'] == a['base']
                  and (want is None or a['base'] == want)
                  and a['max_hp'] == 0 and a['max_mana'] == 0x41200000
                  and a['hp'] == SENTINEL and a['mana'] == SENTINEL and a['obj'] == 0
                  and a['equipped'] == 4)
            counts['init-record'] += ok
            counts['init-recalc'] += ((0x1B23F8, RECALC) in init_calls and a['max_hp'] == 0)
            counts['gear'] += (b['eff'] == a['base'])
            f = R.read_class_formula(tables, b['cls'])
            level = R.itof(1)
            mana = R.fadd(R.fmul(R.fsub(R.itof(b['eff'][1]), f[0]), f[1]), R.fmul(level, f[2]))
            hp = R.fsub(R.fadd(R.fmul(level, f[3]), R.fmul(R.itof(b['eff'][3]), f[4])), f[5])
            counts['maxima'] += (b['max_hp'] == hp and b['max_mana'] == mana)
            counts['currents'] += (b['hp'] == b['max_hp'] and b['mana'] == b['max_mana'])
    failed = 0
    for key in ('init-record', 'init-recalc', 'gear', 'maxima', 'currents'):
        bad = counts['cases'] - counts[key]
        failed += bad
        print('%s %-12s %d/%d' % ('PASS' if not bad else 'FAIL', key, counts[key], counts['cases']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
