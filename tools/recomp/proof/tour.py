#!/usr/bin/env python3
"""tour.py - write a script that boots the game and plays one character through a list of
levels, for the comparison with the rig (cmp.py / rigcompare.py) and for the coverage count.

  python3 tools/recomp/proof/tour.py --out local/recomp-out/proof/tour/t0.rig --class 0
          --levels valor,fire1,storm1 [--ticks 600] [--seed 1] [--die fire1] [--plain]

The script is in the rig's language and runs unchanged in the rig and in the native build
(tools/recomp/playscript.py does the same for one level).  After the boot route of
examples/boot-to-hub-ticks.rig:

  1. the class is chosen on the character-creation screen; in the first level the
     character is rewritten in memory - level 25, large statistics, every active skill of
     the class at rank 10 with one ability record each (--plain leaves the character as
     created);
  2. for every level of --levels: the level-change request the game itself uses
     (g_pendingLevel), then --ticks ticks of seeded random walking, striking, blocking and
     casting; every 96 ticks the two ability buttons are bound to the next two ability
     records, so a tour casts all of a class's skills;
  3. in the level named by --die the hit points are set to almost nothing in the second
     half, so the character dies and the level restarts; then back to the first level.

Memory writes are grouped and each group is announced by `echo @P <n>`: the rig prints
the frame in which it ran the group, and session.py makes the native run apply the same
bytes at the same tick (--opt proof-pokes) instead of running the pokes from the script,
where a late frame of either machine would move them by a tick.

Offsets in the player record are those of docs/player.md and tools/rig/sweep.py; skill
numbers per class come from --trees (the executable's skill-tree tables as JSON, default
local/rig-out/p6-trees.json).  Nothing here is game data.
"""
import argparse
import json
import os
import random
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
BOOT = os.path.join(RECOMP, 'examples', 'boot-to-hub-ticks.rig')
G_PENDING_LEVEL = 0x41B6D0
PLAYERS = 0x4D8AF0
MODEL = {0: 0, 1: 4, 2: 8, 3: 2, 4: 6, 5: 10, 6: 11}      # class -> model (tools/rig/sweep.py)
PRESSES = {6: 0, 5: 1, 0: 2, 3: 4, 1: 6, 4: 8, 2: 10}        # class -> presses of `right` on the class screen (measured; odd counts from 3 on give a class its second model)
DIRECTIONS = [(128, 128), (128, 0), (255, 0), (255, 128), (255, 255), (128, 255), (0, 255), (0, 128), (0, 0)]


def level_change(name):
    """Pokes that write a level name into g_pendingLevel; the first word last (it arms the change)."""
    raw = name.encode('ascii') + b'\0' * 12
    words = struct.unpack('<3I', raw[:12])
    return ['poke 0x%x:x32 %08x' % (G_PENDING_LEVEL + 8, words[2]), 'poke 0x%x:x32 %08x' % (G_PENDING_LEVEL + 4, words[1]),
            'poke 0x%x:x32 %08x' % (G_PENDING_LEVEL, words[0])]


def at_tick(tick, patient=False):
    return 'until g_simFrame:u32 >= %d timeout %s' % (tick, '6000' if patient else '45 continue')


def boot_route(presses, gap=100):
    """The boot route with `presses` presses of `right` on the character-creation screen,
    which turn it from the class shown first (6) to another (PRESSES above).  A turn takes
    long, so the presses are `gap` ticks apart and every later press of the route moves
    back by as much."""
    shift = gap * max(0, presses - 1)
    out = []
    for line in open(BOOT):
        line = line.rstrip('\n')
        if line.startswith('until g_simFrame:u32 >= 500 '):
            for n in range(presses):
                out += ['until g_simFrame:u32 >= %d timeout 3000' % (380 + gap * n), 'tap right 3']
        if line.startswith('until g_simFrame:u32 >= ') and 'timeout 3000' in line:
            tick = int(line.split()[3])
            if tick >= 500 and shift:
                line = 'until g_simFrame:u32 >= %d timeout 3000' % (tick + shift)
        if line.startswith('until g_levelName:str8 == hub'):
            line = 'until g_levelName:str8 != intro timeout 3000'
        out.append(line)
    return out


class Script:
    """Script lines; every group of pokes is announced by `echo @P <n>`, which makes the
    rig print the frame it ran them in (session.py turns that into the tick at which the
    native run applies the same pokes)."""

    def __init__(self, lines):
        self.lines = list(lines)
        self.groups = 0

    def add(self, *lines):
        self.lines += lines

    def pokes(self, pokes):
        self.lines.append('echo @P %d' % self.groups)
        self.groups += 1
        self.lines += pokes


def rec(off):
    return '0x%x' % (PLAYERS + off)


def character(skills):
    out = []
    for off in (0x58, 0x59):
        out.append('poke %s:s8 25' % rec(off))
    # statistics high enough that the game's own maxima for hit points and mana are large
    for off in (0x78, 0x7C, 0x80, 0x84, 0x90, 0x94, 0x98, 0x9C):
        out.append('poke %s:s32 3000' % rec(off))
    for off in (0xB0, 0xAC, 0xC4, 0xC0):
        out.append('poke %s:f32 100000' % rec(off))
    ranks = [(60, 1)] + [(s, 10) for s in skills if s != 60]
    blob = b''.join(struct.pack('<hh', i, r) for i, r in ranks) + struct.pack('<hh', -1, -1)
    out.append('poke %s:hex%d %s' % (rec(0x4B08), len(blob), blob.hex()))
    for n, skill in enumerate(skills[:15]):
        out.append('poke %s:str16 newstyle' % rec(0x4440 + n * 0x68))
        out.append('poke %s:hex6 %s' % (rec(0x4460 + n * 0x68), struct.pack('<hhBB', skill, 0, 1, 0).hex()))
    out.append('poke %s:hex2 0001' % rec(0x4A84))
    return out


def play(rng, script, ticks, step, abilities, die):
    tick = 80
    heading = rng.randrange(1, 9)
    bound = 0
    for n in range(ticks // step):
        if rng.random() < 0.25:
            heading = rng.randrange(0, 9)
        roll = rng.random()
        buttons = ('cross' if roll < 0.40 else 'triangle' if roll < 0.50 else 'circle' if roll < 0.65 else
                   'square' if roll < 0.80 else 'r1' if roll < 0.84 else 'r2' if roll < 0.88 else 'l1' if roll < 0.90 else
                   'l2' if roll < 0.92 else 'none')
        lx, ly = DIRECTIONS[heading]
        if n % 8 == 7 and (abilities > 2 or die):
            # a step without buttons: the two ability buttons move on to the next two ability
            # records and mana is topped up, in a tick in which nothing reads either
            script.add(at_tick(tick), 'pad none %d %d' % (lx, ly), at_tick(tick + step // 2))
            bound = (bound + 2) % max(2, abilities)
            pokes = ['poke %s:hex2 %02x%02x' % (rec(0x4A84), bound, (bound + 1) % max(2, abilities)),
                     'poke %s:f32 100000' % rec(0xC0)]
            if die and n >= (ticks // step) // 2:
                pokes.append('poke %s:f32 0.01' % rec(0xAC))
            script.pokes(pokes)
        else:
            script.add(at_tick(tick), 'pad %s %d %d' % (buttons, lx, ly))
            if buttons != 'none':
                script.add(at_tick(tick + step // 2), 'pad none %d %d' % (lx, ly))
        tick += step
    script.add(at_tick(tick), 'pad none')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True)
    parser.add_argument('--class', dest='cls', type=int, default=6, help='0..6; 6 is what the boot route creates')
    parser.add_argument('--presses', type=int, help='instead of --class: this many presses on the class screen')
    parser.add_argument('--gap', type=int, default=100)
    parser.add_argument('--levels', required=True)
    parser.add_argument('--ticks', type=int, default=600)
    parser.add_argument('--step', type=int, default=12)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--die', default='')
    parser.add_argument('--plain', action='store_true')
    parser.add_argument('--trees', default=os.path.join(ROOT, 'local', 'rig-out', 'p6-trees.json'))
    args = parser.parse_args()
    rng = random.Random('%d/%d' % (args.cls, args.seed))
    script = Script(boot_route(args.presses if args.presses is not None else PRESSES[args.cls], args.gap))
    skills = []
    if not args.plain:
        skills = json.load(open(args.trees))[str(args.cls)]['active']
        script.add('', '# ---- the character ----', at_tick(150, True), 'pad none', 'wait 4')
        script.pokes(character(skills))
        script.add('wait 30', 'show g_simFrame:u32 g_players+0x50:s32 g_players+0x58:s8 g_players+0xac:f32 g_players+0xb0:f32 g_players+0xc0:f32')
    abilities = min(15, len(skills))
    for level in args.levels.split(','):
        script.add('', '# ---- %s ----' % level, 'pad none', 'wait 20')
        script.pokes(level_change(level))
        script.add('until g_levelName:str8 == %s timeout 2500 continue' % level[:8], 'until g_players+0x43d8:u32 != 0 timeout 2500 continue',
                   'until g_simFrame:u32 >= 60 timeout 2500 continue', 'show g_levelName:str16 g_simFrame:u32 g_players+0x50:s32 g_players+0xac:f32')
        play(rng, script, args.ticks, args.step, abilities, level == args.die)
        script.add('show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32 g_players+0x5c:s32 g_players+0xe4:s32')
    script.add('', '# ---- back to the first level ----', 'pad none', 'wait 20')
    script.pokes(level_change('hub'))
    script.add('until g_levelName:str8 == hub timeout 2500 continue', at_tick(120, True),
               'show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32 g_players+0x5c:s32 g_players+0xe4:s32', 'quit')
    out = script.lines
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as sink:
        sink.write('\n'.join(out) + '\n')
    print('%s: %d lines' % (args.out, len(out)))


if __name__ == '__main__':
    main()
