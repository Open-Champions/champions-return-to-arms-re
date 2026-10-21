#!/usr/bin/env python3
"""Count arena class-table indices from the owner's executable at run time.

Only counts and indices are printed. No class names or recipe bytes are saved.
The default active-slot count is one, matching the offline blocker report.
"""
import argparse
from collections import Counter

from ee_emu import EE
from ref_arena_modes import recipe_groups, spawn_budget, sdiv

RECIPES = 0x503868
RECIPE_COUNT = 0x503886
RECIPE_SIZE = 6
CLASS_COUNT = 30


def census(mem, active=1):
    count = mem.u16(RECIPE_COUNT)
    if count != 5:
        raise ValueError('expected five arena recipes')
    records = [bytes(mem.u8(RECIPES + RECIPE_SIZE * i + j)
                     for j in range(RECIPE_SIZE)) for i in range(count)]
    rows = []
    frequency = Counter()
    for recipe in range(count):
        waves = []
        for rem in range(3):
            wave = 3 * recipe + rem
            budget, quotient, remainder = spawn_budget(wave, active)
            if quotient != recipe or remainder != rem:
                raise ValueError('wave quotient mismatch')
            indices = recipe_groups(records[recipe], rem, budget)
            if len(indices) != budget or any(not 0 <= i < CLASS_COUNT for i in indices):
                raise ValueError('invalid class index or recipe count')
            wave_counts = Counter(indices)
            waves.append((wave, wave_counts))
            frequency.update(indices)
        rows.append(waves)
    return rows, frequency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', help='owner supplied US v2.00 executable')
    parser.add_argument('--active', type=int, default=1)
    args = parser.parse_args()
    rows, frequency = census(EE(args.elf).mem, args.active)
    for waves in rows:
        for wave, counts in waves:
            print('wave %2d total %2d indices %s' %
                  (wave, sum(counts.values()),
                   ', '.join('%d:%d' % pair for pair in sorted(counts.items()))))
    print('rank across all recipes: ' +
          ', '.join('%d:%d' % pair for pair in sorted(frequency.items(),
                                                     key=lambda pair: (-pair[1], pair[0]))))


if __name__ == '__main__':
    main()
