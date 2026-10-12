#!/usr/bin/env python3
"""coverage.py - which functions of the executable ran in the compared sessions.

  python3 tools/recomp/proof/coverage.py [NAME=hits.tsv ...] [--sessions NAME,...] [--list FILE]

The instrumented runtime (proof_rt.cpp, --opt proof-hits) writes, per run, every entry
point with the number of times it was reached.  This script adds the runs up in the order
given and counts, against the 7,732 functions of ghidra_funcs.tsv:

  - functions whose first instruction was reached, session by session (how much each
    session added: the curve that shows whether more sessions still find new code);
  - the same for the 12,147 entry points;
  - the functions never reached, grouped by the code area they lie in (symbol prefixes),
    and written one per line to --list.

--sessions a,b,c takes local/recomp-out/proof/cmp/<name>/hits.tsv for each name.
A function the runtime replaces (tools/recomp/hle.txt) counts as reached when the
runtime's replacement called the translation.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')


def read_index(path):
    kinds = {}
    for line in open(path):
        if line.startswith('#'):
            continue
        _, addr, kind, _owner = line.rstrip('\n').split('\t')
        kinds[int(addr, 16)] = kind
    return kinds


def symbols():
    names = {}
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        for line in open(path):
            parts = line.split('\t')
            if len(parts) >= 2 and not line.startswith('#'):
                try:
                    names[int(parts[0], 16)] = parts[1].strip()
                except ValueError:
                    pass
    return names


AREAS = ((0x100000, 'start-up, items, creatures, object clone functions'),
         (0x137000, 'netcode'),
         (0x142000, 'engine: script, objects, world, memory, maths, animation, models, camera, cutscenes'),
         (0x1A0000, 'player'),
         (0x1C4000, 'menus: inventory, item lists, shop, statistics, HUD, minimap'),
         (0x1EB000, 'effects and vehicles'),
         (0x214000, 'sound, memory card, save, player selection, dialogs'),
         (0x236000, 'monsters and their objects'),
         (0x2C7000, 'skills and spells'),
         (0x322000, 'main loop, lobby and network session client'),
         (0x34E000, 'libraries: SDK, keyboard, network configuration, UDP and lobby API'),
         (0x3A7000, 'C and C++ runtime: maths, exceptions, allocator, type information, virtual-table slots'))


def area(addr, name):
    """A coarse label for where a function lies (boundaries read off the symbol files)."""
    label = AREAS[0][1]
    for lo, text in AREAS:
        if addr >= lo:
            label = '%06x %s' % (lo, text)
    return label


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('runs', nargs='*', help='NAME=FILE')
    parser.add_argument('--sessions')
    parser.add_argument('--index', default=os.path.join(OUT, 'gen-proof', 'proof_index.tsv'))
    parser.add_argument('--list')
    parser.add_argument('--areas', action='store_true')
    args = parser.parse_args()
    kinds = read_index(args.index)
    starts = {a for a, k in kinds.items() if k in ('start', 'inner')}
    runs = [tuple(item.split('=', 1)) for item in args.runs]
    if args.sessions:
        runs += [(name, os.path.join(OUT, 'proof', 'cmp', name, 'hits.tsv')) for name in args.sessions.split(',')]
    seen_funcs, seen_entries = set(), set()
    calls = {}
    print('%-14s %9s %9s %9s | %9s %9s' % ('session', 'functions', 'new', 'total', 'entries', 'total'))
    for name, path in runs:
        if not os.path.exists(path):
            print('%-14s (no hits file)' % name)
            continue
        entries = set()
        for line in open(path):
            parts = line.split()
            if len(parts) == 2:
                addr = int(parts[0], 16)
                entries.add(addr)
                calls[addr] = calls.get(addr, 0) + int(parts[1])
        funcs = entries & starts
        new = funcs - seen_funcs
        seen_funcs |= funcs
        seen_entries |= entries
        print('%-14s %9d %9d %9d | %9d %9d' % (name, len(funcs), len(new), len(seen_funcs), len(entries), len(seen_entries)))
    print('functions reached: %d of %d (%.1f%%); entry points reached: %d of %d' % (
        len(seen_funcs), len(starts), 100.0 * len(seen_funcs) / len(starts), len(seen_entries), len(kinds)))
    names = symbols()
    never = sorted(starts - seen_funcs)
    if args.areas:
        groups = {}
        for addr in sorted(starts):
            key = area(addr, names.get(addr, ''))
            g = groups.setdefault(key, [0, 0])
            g[0] += 1
            g[1] += addr in seen_funcs
        print('%-78s %6s %7s %7s' % ('area', 'funcs', 'reached', 'never'))
        for key, (total, reached) in sorted(groups.items(), key=lambda kv: kv[0]):
            print('%-78s %6d %7d %7d' % (key, total, reached, total - reached))
    if args.list:
        with open(args.list, 'w') as sink:
            for addr in never:
                sink.write('%08x\t%s\n' % (addr, names.get(addr, '')))
        print('%d functions never reached written to %s' % (len(never), args.list))
    return 0


if __name__ == '__main__':
    sys.exit(main())
