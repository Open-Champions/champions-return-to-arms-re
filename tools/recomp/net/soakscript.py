#!/usr/bin/env python3
"""soakscript.py - write a long input script for a pair: walking in closed loops while
the fight buttons are drawn from a seed.

  python3 tools/recomp/net/soakscript.py --cycles 200 --step 40 --seed 100 > soak.rig

One cycle is four legs (west, east, north, south for machine A; north, south, east, west
for machine B), each `step` frames of `fuzz` on the button groups with the stick held, so
a player ends a cycle near where it began and does not wander into a level exit - which
matters while the native runtime cannot load a level.  The file is in the rig's script
language and drives a native instance (RTA_NET_SCRIPT) or an rta_rig runner (--script).
"""
import argparse

LEGS = {'A': ['0 128', '255 128', '128 0', '128 255'], 'B': ['128 0', '128 255', '255 128', '0 128']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cycles', type=int, default=100)
    parser.add_argument('--step', type=int, default=40)
    parser.add_argument('--seed', type=int, default=100)
    parser.add_argument('--groups', default='fight,potion')
    parser.add_argument('--rest', type=int, default=0, help='frames of no input after each cycle')
    args = parser.parse_args()
    print('# %d cycles of 4 legs of %d frames; fuzz seeds from %d; groups %s' % (args.cycles, args.step, args.seed, args.groups))
    print('wait 30')
    seed = args.seed
    for _ in range(args.cycles):
        for leg in range(4):
            print('A: stick L %s' % LEGS['A'][leg])
            print('B: stick L %s' % LEGS['B'][leg])
            print('fuzz %d %d %s' % (seed, args.step, args.groups))
            seed += 1
        if args.rest:
            print('wait %d' % args.rest)
    print('wait 120')


if __name__ == '__main__':
    main()
