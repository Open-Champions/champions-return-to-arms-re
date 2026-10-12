#!/usr/bin/env python3
"""playscript.py - write a script that boots the game and then plays, for rigcompare.py.

  python3 tools/recomp/playscript.py --out local/recomp-out/play.rig [--seed 1] [--ticks 2400]
                                     [--level valor] [--no-menus]

The script is in the rig's language and runs unchanged in the rig and in the native
build.  It is the boot route of examples/boot-to-hub-ticks.rig followed by play, with
every input keyed on the simulation tick (`until g_simFrame >= N`), so that both machines
press the same buttons at the same ticks however long their loading takes:

  1. first level: walk a square, strike, open and close the pause menu, open the pause
     menu's load entry (the card is searched, no save is found) and leave it again;
  2. change to a level with monsters (the level-change request the game itself uses is
     written into g_pendingLevel), then seeded random walking and striking for --ticks
     ticks - enemies come to the player, drops are picked up by walking over them or
     with the action button;
  3. change back to the first level.

While a menu is open the simulation stands still, so inside menus the script counts
frames; it keys on ticks again once the game runs.  Nothing here is game data: the
buttons and the level name are the only things taken from the game.
"""
import argparse
import os
import random
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.join(HERE, 'examples', 'boot-to-hub-ticks.rig')
G_PENDING_LEVEL = 0x41B6D0


def level_change(name):
    """Pokes that write a level name into g_pendingLevel; the first word last (it arms the change)."""
    raw = name.encode('ascii') + b'\0' * 8
    words = struct.unpack('<2I', raw[:8])
    return ['poke 0x%x:x32 %08x' % (G_PENDING_LEVEL + 4, words[1]), 'poke 0x%x:x32 %08x' % (G_PENDING_LEVEL, words[0])]


def at_tick(tick, patient=True):
    # During random play a button can open a message box or a dialog, which stops the
    # ticks; then the wait gives up after 45 frames and the next input (often the button
    # that dismisses the box) is applied anyway.  Ticks key the input again once they run.
    return 'until g_simFrame:u32 >= %d timeout %s' % (tick, '6000' if patient else '45 continue')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--ticks', type=int, default=2400, help='ticks of random play in the second level')
    parser.add_argument('--step', type=int, default=12, help='ticks between input changes')
    parser.add_argument('--level', default='valor')
    parser.add_argument('--no-menus', action='store_true')
    parser.add_argument('--no-return', action='store_true', help='stay in the second level')
    args = parser.parse_args()
    rng = random.Random(args.seed)
    out = [line.rstrip('\n') for line in open(BOOT)]
    out += ['', '# ---- play: first level ----']
    # walk a square and strike the air
    tick = 100
    for lx, ly in ((128, 0), (255, 128), (128, 255), (0, 128)):
        out += [at_tick(tick), 'pad none %d %d' % (lx, ly)]
        tick += 40
    out += [at_tick(tick), 'pad cross', at_tick(tick + 4), 'pad none', at_tick(tick + 20), 'pad triangle',
            at_tick(tick + 24), 'pad none']
    tick += 40
    if not args.no_menus:
        out += ['# pause menu: open, close', at_tick(tick), 'tap start 4', 'wait 60', 'show g_simFrame:u32 g_paused:s32',
                'tap start 4', 'until g_paused:s32 == 0 timeout 600', 'wait 20',
                '# pause menu: third entry (load), the card is searched; then out again with the back button (circle)',
                'tap start 4', 'wait 60', 'tap down 4', 'wait 20', 'tap down 4', 'wait 20', 'tap cross 4', 'wait 400',
                'show g_simFrame:u32 g_paused:s32 g_memcardState:s32',
                'tap circle 4', 'until g_paused:s32 == 0 timeout 600', 'show g_simFrame:u32 g_paused:s32 g_memcardState:s32']
        tick += 40
    out += ['# ---- play: a level with monsters ----', at_tick(tick)] + level_change(args.level)
    out += ['until g_levelName:str8 == %s timeout 6000' % args.level, 'show g_levelName:str16 g_simFrame:u32']
    directions = [(128, 128), (128, 0), (255, 0), (255, 128), (255, 255), (128, 255), (0, 255), (0, 128), (0, 0)]
    tick = 80
    heading = rng.randrange(1, 9)
    for _ in range(args.ticks // args.step):
        # keep a heading for a while, so that the walk covers ground; strike most of the time
        if rng.random() < 0.25:
            heading = rng.randrange(0, 9)
        buttons = []
        roll = rng.random()
        if roll < 0.55:
            buttons.append('cross')
        elif roll < 0.67:
            buttons.append('triangle')
        elif roll < 0.75:
            buttons.append('circle')
        elif roll < 0.80:
            buttons.append('square')
        elif roll < 0.84:
            buttons.append('r1')
        elif roll < 0.88:
            buttons.append('r2')
        lx, ly = directions[heading]
        out += [at_tick(tick, False), 'pad %s %d %d' % ('+'.join(buttons) or 'none', lx, ly)]
        # a strike is a press, not a hold: let go half-way
        if buttons:
            out += [at_tick(tick + args.step // 2, False), 'pad none %d %d' % (lx, ly)]
        tick += args.step
    out += [at_tick(tick, False), 'pad none', 'show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32 g_players+0x5c:s32 g_players+0xe4:s32']
    if not args.no_return:
        out += ['# ---- back to the first level ----', 'wait 30'] + level_change('hub')
        out += ['until g_levelName:str8 == hub timeout 6000', 'until g_simFrame:u32 >= 120 timeout 6000',
                'show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32 g_players+0x5c:s32 g_players+0xe4:s32']
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as sink:
        sink.write('\n'.join(out) + '\n')
    print('%s: %d lines' % (args.out, len(out)))


if __name__ == '__main__':
    main()
