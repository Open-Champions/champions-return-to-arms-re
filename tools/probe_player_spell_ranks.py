#!/usr/bin/env python3
"""Read player-tree skill costs and tier-1 statistics from the original in ee_emu.

Only numeric Skill slots are called. Stat 0 is not universally damage: consult the
per-skill specifications for each statistic's meaning and the later effect path.
No executable content or disassembly is written by this tool.
"""

import argparse
import hashlib
import json
import struct
from types import SimpleNamespace

import dump_tables
from ee_emu import EE, s32


def sample(executable, classes, skills, ranks):
    with open(executable, 'rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != dump_tables.KNOWN_SHA256:
        raise SystemExit('expected SLUS-20973 v2.00; sha256 is ' + digest)

    args = SimpleNamespace(executable=executable, iso=None, force=False,
                           balance=None, text=None, objects=None)
    tree = dump_tables.t_skill_trees(dump_tables.Ctx(args))
    emu = EE(executable)
    emu.call(0x16AC74, 1, 0xFFFF, max_steps=20000000)
    emu.call(0x1EBCA0, max_steps=20000000)
    mem = emu.mem
    for node in tree:
        if node['kind'] != 'skill' or node['class'] not in classes:
            continue
        sid = int(node['id_or_mask'])
        if skills and sid not in skills:
            continue
        skill = mem.u32(0x41B170 + 4 * sid)
        table = mem.u32(skill + 0x60)
        kind = mem.u32(skill + 8)
        if kind == 3:  # passive tree nodes have no cast request
            continue
        cost_fn = mem.u32(table + 8 * 5 + 4)
        stat_fn = mem.u32(table + 8 * 10 + 4)
        for rank in ranks:
            emu.call(cost_fn, skill, rank)
            bits = emu.f[0] & 0xFFFFFFFF
            stats = [s32(emu.call(stat_fn, skill, n, rank) & 0xFFFFFFFF)
                     for n in range(5)]
            yield {'class': node['class'], 'skill_id': sid, 'kind': kind, 'rank': rank,
                   'mana_cost': struct.unpack('<f', struct.pack('<I', bits))[0],
                   'mana_bits': '0x%08x' % bits, 'cost_pc': '0x%x' % cost_fn,
                   'tier1_stats_0_to_4': stats}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', help='private SLUS_209.73 v2.00 path')
    parser.add_argument('--class', dest='classes', type=int, action='append',
                        help='class 0..6; repeatable (default: all)')
    parser.add_argument('--skill', type=int, action='append',
                        help='skill id; repeatable (default: all castable tree entries)')
    parser.add_argument('--rank', type=int, action='append',
                        help='rank 1..20; repeatable (default: every rank)')
    args = parser.parse_args()
    classes = set(args.classes if args.classes is not None else range(7))
    ranks = args.rank if args.rank is not None else range(1, 21)
    if any(c not in range(7) for c in classes) or any(r not in range(1, 21) for r in ranks):
        parser.error('class must be 0..6 and rank must be 1..20')
    for row in sample(args.executable, classes, set(args.skill or ()), ranks):
        print(json.dumps(row, sort_keys=True))


if __name__ == '__main__':
    main()
