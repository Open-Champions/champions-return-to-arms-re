#!/usr/bin/env python3
"""pilot.py - find the way to a fight and write it down as a script (a development aid).

A script for rigcompare.py cannot look at the game; this tool can.  It runs the native
build with a script that ends in memory dumps, reads the player's and the creatures'
positions from them, and writes the next piece of script: the stick direction that walks
the player toward the nearest creature, and strikes when it is close.  The result is a
plain script of tick-keyed input that plays the same on the rig.

  python3 tools/recomp/pilot.py --out local/recomp-out/fight.rig [--level valor] [--start 1500]

Object layout used (docs/objects.md, docs/creatures.md): position at +0x10, hit points and
their maximum at +0x228 / +0x22c of a creature object, its function table at +0x24; the pool is 0xe7700 bytes at
0x5f88c0; the first player's object pointer is at g_players + 0x43d8.
Everything it writes (dumps are game data) stays under local/recomp-out/pilot/.
"""
import argparse
import math
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.join(ROOT, 'local', 'recomp-out', 'pilot')
sys.path.insert(0, HERE)
import playscript  # noqa: E402

POOL, POOL_SIZE, PLAYER_PTR = 0x5F88C0, 0xE7700, 0x4D8AF0 + 0x43D8
SEEDS = ['--count-at', '3229f0=0bade742', '--count-at', '322a00=0bade743']


def run(lines, name):
    script = os.path.join(WORK, name + '.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(lines) + '\n')
    card = os.path.join(WORK, 'card')
    subprocess.run(['rm', '-rf', card])
    done = subprocess.run([sys.executable, os.path.join(HERE, 'native.py'), 'boot', '--card', card, '--script', script] + SEEDS,
                          capture_output=True, text=True, cwd=ROOT)
    with open(os.path.join(WORK, name + '.out'), 'w') as sink:
        sink.write(done.stdout + done.stderr)
    return done.returncode


def f32(mem, at):
    return struct.unpack_from('<f', mem, at)[0]


def u32(mem, at):
    return struct.unpack_from('<I', mem, at)[0]


def player(mem):
    obj = u32(mem, PLAYER_PTR)
    return obj, (f32(mem, obj + 0x10), f32(mem, obj + 0x14), f32(mem, obj + 0x18))


def creatures(mem):
    """(distance to the player, address, position, hit points, maximum) of every object that looks like a living creature."""
    me, (px, py, pz) = player(mem)
    found = []
    for at in range(POOL, POOL + POOL_SIZE - 0x230, 0x10):
        if at == me:
            continue
        vtable = u32(mem, at + 0x24)            # the object's function table, in the data section
        if not 0x3E5C40 <= vtable < 0x564380 or vtable & 3:
            continue
        hp, top = f32(mem, at + 0x228), f32(mem, at + 0x22C)
        x, y, z = f32(mem, at + 0x10), f32(mem, at + 0x14), f32(mem, at + 0x18)
        if not (0 < hp <= top < 1e6) or not all(math.isfinite(v) and abs(v) < 1e5 for v in (x, y, z)):
            continue
        if abs(x) + abs(y) < 1:
            continue
        found.append((math.hypot(x - px, y - py), at, (x, y, z), hp, top, vtable))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True)
    parser.add_argument('--level', default='valor')
    parser.add_argument('--start', type=int, default=1500, help='tick of the level at which play starts')
    parser.add_argument('--legs', type=int, default=8, help='pieces of walking to try at most')
    parser.add_argument('--target', type=int, default=0, help='which creature, nearest first')
    parser.add_argument('--hit-points', type=float, default=0, help='poke the player to this many hit points during the fight')
    parser.add_argument('--resume', help='continue a script this tool wrote: its lines are the start')
    parser.add_argument('--at', type=int, default=0, help='with --resume: the tick to continue at')
    parser.add_argument('--stick', help='with --resume: the calibration "upx,upy,rightx,righty" printed by the first run')
    parser.add_argument('--target-address', help='with --resume: the creature to go on with (hex)')
    parser.add_argument('--weaken', type=float, default=0, help='poke the creature down to this many hit points when the fight starts')
    args = parser.parse_args()
    os.makedirs(WORK, exist_ok=True)
    boot = [line.rstrip('\n') for line in open(playscript.BOOT)]
    base = boot + [playscript.at_tick(100)] + playscript.level_change(args.level) + \
        ['until g_levelName:str8 == %s timeout 6000' % args.level]

    def dump(tick, name):
        return [playscript.at_tick(tick), 'dump 0 0x2000000 %s' % os.path.join(WORK, name + '.bin')]

    def load(name):
        with open(os.path.join(WORK, name + '.bin'), 'rb') as source:
            return source.read()

    # 1. which way do "up" and "right" on the stick go in the world?
    if args.resume:
        base = [line.rstrip('\n') for line in open(args.resume) if not line.startswith('show ')]
        values = [float(v) for v in args.stick.split(',')]
        up, right = (values[0], values[1]), (values[2], values[3])
        speed = math.hypot(*up) / 30
        play, t = [], args.at
    else:
        t = args.start
        play = dump(t, 'c0') + ['pad none 128 0'] + dump(t + 30, 'c1') + ['pad none 255 128'] + dump(t + 60, 'c2') + ['pad none']
        if run(base + play, 'calibrate') not in (0,):
            raise SystemExit('the calibration run failed; see %s' % os.path.join(WORK, 'calibrate.out'))
        p0, p1, p2 = (player(load(n))[1] for n in ('c0', 'c1', 'c2'))
        up = (p1[0] - p0[0], p1[1] - p0[1])
        right = (p2[0] - p1[0], p2[1] - p1[1])
        speed = math.hypot(*up) / 30
        print('stick up moves (%.1f, %.1f), right (%.1f, %.1f) in 30 ticks: %.2f units per tick  (--stick %.1f,%.1f,%.1f,%.1f)' % (
            up + right + (speed,) + up + right))
        if speed < 0.5:
            raise SystemExit('the player does not move at tick %d (a cutscene?); try a later --start' % t)
        t += 70
    def stick_toward(dx, dy, turn=0.0):
        """The stick position whose movement points along (dx, dy), turned by `turn` radians."""
        c, sn = math.cos(turn), math.sin(turn)
        dx, dy = dx * c - dy * sn, dx * sn + dy * c
        a = (dx * up[0] + dy * up[1]) / (up[0] ** 2 + up[1] ** 2)
        b = (dx * right[0] + dy * right[1]) / (right[0] ** 2 + right[1] ** 2)
        scale = max(abs(a), abs(b), 1e-6)
        return int(round(128 + 127 * b / scale)), int(round(128 - 127 * a / scale))

    def look(extra, name='look'):
        if run(base + play + extra + dump(extra_end[0], name), name) != 0:
            raise SystemExit('run failed; see %s' % os.path.join(WORK, name + '.out'))
        return load(name)

    extra_end = [t]
    target = None
    fighting = False
    runs = 0
    for leg in range(args.legs):
        extra_end[0] = t
        mem = look([])
        runs += 1
        _, (px, py, pz) = player(mem)
        seen = creatures(mem)
        if leg == 0:
            for d, at, pos, hp, top, vtable in seen[:6]:
                print('  creature at 0x%x (class table 0x%x): %.0f away, hit points %.0f of %.0f' % (at, vtable, d, hp, top))
            if len(seen) <= args.target:
                raise SystemExit('no creature in the pool')
            target = int(args.target_address, 16) if args.target_address else seen[args.target][1]
        hit = [c for c in seen if c[1] == target]
        if not hit:
            print('the target is gone at tick %d (dead); walking over the place for what it dropped' % t)
            for lx, ly in ((128, 0), (255, 128), (128, 255), (0, 128), (128, 0)):
                play += [playscript.at_tick(t), 'pad triangle %d %d' % (lx, ly), playscript.at_tick(t + 6), 'pad none %d %d' % (lx, ly)]
                t += 25
            play += [playscript.at_tick(t), 'pad none']
            break
        d, _, (tx, ty, tz), hp, top, _ = hit[0]
        print('leg %d, tick %d: player (%.0f, %.0f), target (%.0f, %.0f) %.0f away, hit points %.0f of %.0f' % (leg, t, px, py, tx, ty, d, hp, top))
        if d <= 110:
            if not fighting:
                fighting = True
                print('    in reach at tick %d: the fight starts' % t)
                if args.weaken:
                    play += [playscript.at_tick(t), 'poke 0x%x:x32 %08x' % (target + 0x228, struct.unpack('<I', struct.pack('<f', args.weaken))[0])]
            lx, ly = stick_toward(tx - px, ty - py)
            if args.hit_points and not args.resume:
                # a new character does not survive one blow here; the same pokes on both
                # machines keep it alive so that blows are exchanged for a while
                bits = struct.unpack('<I', struct.pack('<f', args.hit_points))[0]
                play += [playscript.at_tick(t), 'poke [g_players+0x43d8]+0x228:x32 %08x' % bits, 'poke g_players+0xac:x32 %08x' % bits]
            for _ in range(5):                  # face it and strike; then look again (it moves)
                play += [playscript.at_tick(t), 'pad cross %d %d' % (lx, ly), playscript.at_tick(t + 5), 'pad none %d %d' % (lx, ly)]
                t += 12
            play += [playscript.at_tick(t), 'pad none']
            t += 2
            continue
        # walk: straight at it when that makes headway, else around what is in the way
        ticks = int(min(max((d - 50) / speed, 10), 100))
        for turn in (0, 45, -45, 90, -90, 135, -135, 180):
            lx, ly = stick_toward(tx - px, ty - py, math.radians(turn))
            trial = [playscript.at_tick(t), 'pad none %d %d' % (lx, ly), playscript.at_tick(t + ticks), 'pad none']
            extra_end[0] = t + ticks + 2
            after = player(look(trial, 'trial'))[1]
            runs += 1
            moved = math.hypot(after[0] - px, after[1] - py)
            if moved >= 0.6 * speed * ticks or turn == 180:
                if turn:
                    print('    blocked; turned %d degrees, moved %.0f' % (turn, moved))
                play += trial
                t += ticks + 5
                break
    print('%d native runs' % runs)
    play += [playscript.at_tick(t + 60), 'show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32 g_players+0x5c:s32 g_players+0xe4:s32']
    with open(args.out, 'w') as sink:
        sink.write('\n'.join(base + play) + '\n')
    print('%s: %d lines, play ends at tick %d' % (args.out, len(base + play), t + 60))


if __name__ == '__main__':
    main()
