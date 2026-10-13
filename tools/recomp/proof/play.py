#!/usr/bin/env python3
"""play.py - write scripts that PLAY: fights, kills, a level-up with points spent, chests,
potions, a shop, a save point, a save loaded again, a death - for the comparison with the
rig (session.py) and the coverage count.  tour.py's sessions walk and cast at random where
a level starts, which is seldom where its monsters are: seven tours killed one monster.

  python3 tools/recomp/proof/play.py fight NAME --class 0..6 --levels a,b,c [--legs 3] [--plain]
  python3 tools/recomp/proof/play.py town  NAME [--class 6]

`fight` finds its way by looking, as tools/recomp/pilot.py does: it runs the native build
with the script so far, takes a memory image, reads where the living creatures are, and
writes the next piece - the character is PUT beside the nearest creature not yet visited
(memory writes of its position and facing), strikes and casts for a while, then the next.
Per session: the tour's character (level 25, large statistics, every active skill of the
class at rank 10) with its experience one point below the next level, so that the first
kill is a level-up; then the level-up screen (three ability points and one skill point
spent); a chest opened and its contents picked up where the level has one; a potion of
each kind drunk; and at the end the character's hit points written down among monsters
until it dies, and the restart.  --plain leaves the character as created (its first
skills, and a death soon).

`town` is the first level: both potions, the shop (talk, buy twice, sell list, equip and
unequip there, sell), the inventory screen (unequip, equip), the save point (save), the
pause menu's Load Game (the save loaded again).

What the script needs to know about a place - where the shop keeper, the save point, a
chest stand - is read from the memory image at the time (objs.py), not written here; the
key presses of the menus were found in a rig session with its screen text
(docs/issues/native-proof.md, R2.4).  Scripts and images go to
local/recomp-out/proof/play/ and are game-derived; nothing here is game data.

Every memory write is announced by `echo @P n` (tour.py): session.py makes the native run
apply the same bytes at the tick the rig applied them.  A write whose address is the
player object's goes through the record's pointer (`[g_players+0x43d8]+off`), which
session.py and proof_rt.cpp resolve when the write is applied.
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import imgdiff                                  # noqa: E402
import objs                                     # noqa: E402
import tour                                     # noqa: E402

ROOT = tour.ROOT
PROOF = os.path.join(ROOT, 'local', 'recomp-out', 'proof')
WORK = os.path.join(PROOF, 'play')
NATIVE = os.environ.get('PROOF_NATIVE') or os.path.join(PROOF, 'build', 'bin', 'rta_proof')
PLAYERS = tour.PLAYERS
OBJ = '[0x%x]' % (PLAYERS + 0x43D8)             # the first player's object
CAMERA = '[0x4f8450]'                           # g_localCamera
SEEDS = ['--count-at', '3229f0=0bade742', '--count-at', '322a00=0bade743']
EXP_TABLE = 0x41B558                            # g_expTable: experience at which level n ends
NOT_MONSTERS = ('player', 'npc', 'critter', 'light', 'trigger', 'savepoint', 'container', 'chest', 'weather', 'portal',
                'particle', 'jumpgate', 'door', 'torch', 'navigator', 'prop', 'blocker', 'camera', 'sound', 'item')


def rec(off):
    return '0x%x' % (PLAYERS + off)


class Script(tour.Script):
    def wait(self, n):
        self.add('wait %d' % n)

    def tap(self, button, hold=8, after=40):
        self.add('tap %s %d' % (button, hold), 'wait %d' % after)

    def hold(self, button, frames, after):
        self.add('press %s' % button, 'wait %d' % frames, 'release %s' % button, 'wait %d' % after)

    def put(self, x, y, z, angle=None):
        """The character moved to a place: its position written four times, five frames
        apart (the camera is told to follow without smoothing), then left to settle."""
        for _ in range(4):
            pokes = ['poke %s+0x16d:u8 5' % CAMERA, 'poke %s+0x10:f32 %.2f' % (OBJ, x), 'poke %s+0x14:f32 %.2f' % (OBJ, y),
                     'poke %s+0x18:f32 %.2f' % (OBJ, z)]
            if angle is not None:
                pokes.append('poke %s+0x38:u16 %d' % (OBJ, angle))
            self.pokes(pokes)
            self.wait(5)
        self.wait(12)

    def enter(self, level):
        self.add('', '# ---- %s ----' % level, 'pad none', 'wait 20')
        self.pokes(tour.level_change(level))
        self.add('until g_levelName:str8 == %s timeout 2500 continue' % level[:8], 'until g_players+0x43d8:u32 != 0 timeout 2500 continue',
                 'until g_simFrame:u32 >= 40 timeout 2500 continue',
                 # an arrival cutscene is skipped (the start button); without one nothing is pressed -
                 # the test is the cutscene flag itself (g_cutsceneActive): the camera's mode
                 # is not the follow mode for a moment in a level without a cutscene too, and
                 # start then opens the pause menu (session pf4 of 2026-10-13 went that way)
                 'tapuntil start 30 0x44fcd0:u8 == 0 timeout 1800', 'wait 30',
                 'show g_levelName:str16 g_simFrame:u32 g_players+0x59:s8 g_players+0x5c:s32 g_players+0xac:f32')


def probe(script, name, tail=()):
    """Run the script natively, then a memory image; returns the image."""
    os.makedirs(WORK, exist_ok=True)
    path, image = os.path.join(WORK, name + '-probe.rig'), os.path.join(WORK, name + '-probe.bin')
    if os.path.exists(image):
        os.remove(image)
    with open(path, 'w') as sink:
        sink.write('\n'.join(script.lines + list(tail) + ['dump 0 0x2000000 %s' % image, 'quit']) + '\n')
    card = os.path.join(WORK, name + '-card')
    subprocess.run(['rm', '-rf', card])
    env = dict(os.environ, RTA_NATIVE=NATIVE, RTA_NICE='15')
    done = subprocess.run([sys.executable, os.path.join(tour.RECOMP, 'native.py'), 'boot', '--card', card, '--script', path] + SEEDS,
                          capture_output=True, text=True, errors='replace', env=env, cwd=ROOT)
    with open(os.path.join(WORK, name + '-probe.out'), 'w') as sink:
        sink.write(done.stdout + done.stderr)
    if not os.path.exists(image):
        raise SystemExit('the probe run of %s wrote no image; see %s-probe.out' % (name, os.path.join(WORK, name)))
    with open(image, 'rb') as source:
        data = source.read()
    os.remove(image)
    return data


def f32(image, at):
    return struct.unpack_from('<f', image, at)[0]


def me(image):
    obj = imgdiff.word(image, PLAYERS + 0x43D8)
    return obj, struct.unpack_from('<3f', image, obj + 0x10)


def monsters(image):
    """Living creatures that are not the player or a townsman: (object, hit points)."""
    out = []
    mine, _ = me(image)
    for o in objs.objects(image):
        low = o['cls'].lower()
        if o['addr'] == mine or o['size'] < 0x500 or any(word in low for word in NOT_MONSTERS):
            continue
        hp, top = f32(image, o['addr'] + 0x228), f32(image, o['addr'] + 0x22C)
        if not (0 < hp <= top < 1e7) or abs(o['x']) + abs(o['y']) < 1:
            continue
        # awake: run by runObjects (flag 0x8000 clear) and not inert (+0x231: waiting, hidden, frozen)
        o['awake'] = not o['flags'] & 0x8000 and image[o['addr'] + 0x231] == 0
        out.append((o, hp))
    return out


def facing(dx, dy):
    """The facing angle (object +0x38, 65536 to the turn) that looks along (dx, dy): 0 is +x, 16384 +y."""
    return int(round(math.atan2(dy, dx) / (2 * math.pi) * 65536)) & 0xFFFF


def fight(script, rng, ticks, abilities, bound):
    """Strike, cast and block on the spot for `ticks` frames; the two ability buttons move on
    to the next two ability records now and then (tour.py)."""
    t = 0
    while t < ticks:
        roll = rng.random()
        button = 'cross' if roll < 0.45 else 'circle' if roll < 0.70 else 'triangle' if roll < 0.92 else 'r1'
        script.add('pad %s' % button, 'wait 5', 'pad none', 'wait 7')
        t += 12
        if abilities > 2 and (t // 12) % 5 == 4:
            bound[0] = (bound[0] + 2) % abilities
            script.pokes(['poke %s:hex2 %02x%02x' % (rec(0x4A84), bound[0], (bound[0] + 1) % abilities), 'poke %s:f32 100000' % rec(0xC0)])
    script.add('pad none')


def level_up_screen(script, levels):
    """Select opens the level-up screen while a gained level is not acknowledged: the
    confirm button puts an ability point into the row under the cursor (three points a
    level), then the skill page follows, where the stick moves the cursor and the confirm
    button spends a skill point; the back button leaves."""
    script.tap('select', 8, 60)
    for _ in range(3 * levels):
        script.tap('cross', 8, 30)
    script.wait(30)
    # the cursor starts above the tree: down twice and right reaches a skill (seen for class 6); then on through the tree
    for x, y in ((128, 255), (128, 255), (255, 128), (128, 128), (128, 255), (255, 128), (128, 255), (0, 128), (128, 255), (255, 128), (128, 0)):
        script.add('stick L %d %d' % (x, y), 'wait 8', 'stick L 128 128', 'wait 30')
        script.tap('cross', 8, 40)
    script.add('show g_players+0x58:s8 g_players+0x59:s8 g_players+0xe8:s32 g_players+0xec:s8 g_players+0x78:s32')
    for _ in range(3):
        script.tap('circle', 8, 40)
    # should the screen still be up (a count that did not fit), leave it
    script.add('tapuntil circle 30 g_paused:u32 == 0 timeout 600', 'wait 20')


def build_fight(args):
    import random
    rng = random.Random('%s/%d' % (args.name, args.cls))
    script = Script(tour.boot_route(tour.PRESSES[args.cls], 100))
    skills = []
    if not args.plain:
        skills = json.load(open(args.trees))[str(args.cls)]['active']
        script.add('', '# ---- the character ----', tour.at_tick(150, True), 'pad none', 'wait 4')
        script.pokes(tour.character(skills) + ['poke %s:s32 %d' % (rec(0x5C), exp_before(25)), 'poke %s:s32 200000' % rec(0xE4)])
        script.add('wait 30')
    else:
        script.add('', tour.at_tick(150, True), 'pad none', 'wait 30')
    abilities, bound = min(15, len(skills)), [0]
    spent = False
    report = []
    for number, level in enumerate(args.levels.split(',')):
        script.enter(level)
        visited, died = [], False
        for leg in range(args.legs):
            image = probe(script, args.name)
            if bytes(image[0x41B721:0x41B721 + len(level)]).decode('latin1') != level[:8]:
                report.append('%s: not entered' % level)
                break
            obj, (px, py, pz) = me(image)
            level_now, exp, hp = image[PLAYERS + 0x59], imgdiff.word(image, PLAYERS + 0x5C), f32(image, PLAYERS + 0xAC)
            if not args.plain and not spent and level_now > image[PLAYERS + 0x58]:
                level_up_screen(script, level_now - image[PLAYERS + 0x58])
                spent = True
                report.append('%s: level %d reached at leg %d; the level-up screen follows' % (level, level_now, leg))
            if hp <= 0:
                report.append('%s: the character is dead at leg %d (a creature killed it); the restart follows' % (level, leg))
                after_death(script)
                died = True
                break
            everything = monsters(image)
            found = [(o, h) for o, h in everything if not any(math.hypot(o['x'] - vx, o['y'] - vy) < 60 for vx, vy in visited)] or everything
            if not found:
                report.append('%s: no creature left at leg %d' % (level, leg))
                break
            if leg == 0:
                # the first: the nearest; afterwards the nearest to where the character stands
                kinds = {}
                for o, _ in found:
                    kinds[o['cls']] = kinds.get(o['cls'], 0) + 1
                report.append('%s: %s; %d awake' % (level, ', '.join('%d %s' % (n, k) for k, n in sorted(kinds.items())), sum(1 for o, _ in found if o['awake'])))
            # prefer a kind not fought yet in this session
            found.sort(key=lambda item: (not item[0]['awake'], item[0]['cls'] in build_fight.seen, math.hypot(item[0]['x'] - px, item[0]['y'] - py)))
            target = found[0][0]
            build_fight.seen.add(target['cls'])
            visited.append((target['x'], target['y']))
            side = 34.0
            script.add('# leg %d: beside a %s' % (leg, target['cls']))
            script.put(target['x'] + side, target['y'], target['z'] + 6.0, facing(-side, 0))
            if leg == 1 and not args.plain:
                # both potions: hit points and mana written low, then the two potion buttons
                script.pokes(['poke %s:f32 40' % rec(0xAC), 'poke %s:f32 5' % rec(0xC0)])
                script.add('wait 4', 'tap r2 6', 'wait 20', 'tap l2 6', 'wait 20')
            fight(script, rng, args.fight, abilities, bound)
            script.add('show g_levelName:str16 g_simFrame:u32 g_players+0x59:s8 g_players+0x5c:s32 g_players+0xac:f32 g_players+0xe4:s32')
            build_fight.exp.append(exp)
        script.add('# image')
        script.wait(4)
        # a chest, where the level has one in reach of a put: hold the use button, then take what fell out
        image = probe(script, args.name)
        if f32(image, PLAYERS + 0xAC) <= 0 and not died:
            report.append('%s: the character is dead after the last leg; the restart follows' % level)
            after_death(script)
        elif not died:
            _, (px, py, pz) = me(image)
            chests = sorted((math.hypot(o['x'] - px, o['y'] - py), o) for o in objs.objects(image)
                            if 'chest' in o['cls'].lower() and o['flags'] & 0x100000)
            if chests:
                c = chests[0][1]
                script.add('# a chest')
                script.put(c['x'], c['y'] + 26.0, c['z'] + 8.0, facing(0, -1))
                script.hold('square', 14, 70)
                for _ in range(3):
                    script.tap('square', 10, 30)
                report.append('%s: a %s opened' % (level, c['cls']))
            if number == len(args.levels.split(',')) - 1 and visited:
                # the end: among monsters with next to no hit points, until one of them hits
                script.add('# death')
                found = monsters(image)
                found.sort(key=lambda item: math.hypot(item[0]['x'] - px, item[0]['y'] - py))
                # six tries at a time, then a look: once the character is dead nothing more is
                # written (a write during the restart's load lands in a frame the other
                # machine's shorter load does not have: session pf2 of 2026-10-13)
                dead = False
                for k in range(0, args.death_tries, 6):
                    if found:
                        t = found[(k // 6) % len(found)][0]
                        script.put(t['x'] + 20.0, t['y'], t['z'] + 6.0)
                    for _ in range(6):
                        script.pokes(['poke %s:f32 0.5' % rec(0xAC)])
                        script.add('pad cross', 'wait 5', 'pad none', 'wait 15')
                    if f32(probe(script, args.name), PLAYERS + 0xAC) <= 0:
                        dead = True
                        break
                report.append('%s: %s' % (level, 'killed by a creature with its hit points written low' if dead else 'not killed in %d tries' % args.death_tries))
                if dead:
                    after_death(script)
    script.add('pad none', 'wait 30', 'quit')
    return script, report


def after_death(script):
    """What follows a death: the death is shown, the confirm button restarts, the level
    starts again at its save point."""
    script.add('pad none', 'show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32 %s+0x58c:s32' % OBJ, 'wait 200')
    for _ in range(4):
        script.tap('cross', 8, 90)
    script.add('wait 240', 'show g_levelName:str16 g_simFrame:u32 g_players+0xac:f32')


build_fight.seen = set()
build_fight.exp = []


def exp_before(level):
    """One point below the experience at which `level` ends (g_expTable in the executable)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    from ps2elf import Elf
    return Elf(os.path.join(ROOT, 'SLUS_209.73')).u32(EXP_TABLE + 4 * level) - 1


def usable(image, word):
    found = [o for o in objs.objects(image) if word in o['cls'].lower() and o['flags'] & 0x100000]
    if not found:
        raise SystemExit('no usable %s in the image' % word)
    return found[0]


def build_town(args):
    script = Script(tour.boot_route(tour.PRESSES[args.cls], 100))
    script.add('', '# ---- the first level ----', tour.at_tick(150, True), 'pad none', 'wait 30')
    image = probe(script, args.name)
    keeper, save = usable(image, 'npc'), usable(image, 'savepoint')
    report = ['shop keeper %06x, save point %06x' % (keeper['addr'], save['addr'])]
    # potions: both pools written low, then the two potion buttons
    script.pokes(['poke %s:f32 10' % rec(0xAC), 'poke %s:f32 5' % rec(0xC0), 'poke %s:s32 200000' % rec(0xE4)])
    script.add('wait 6', 'tap r2 6', 'wait 30', 'tap l2 6', 'wait 30', 'show g_players+0xac:f32 g_players+0xc0:f32 g_players+0x3740:hex4')
    # the shop: in front of the keeper (he looks along -y), talk, through his lines, the
    # second entry of the choice, then buy, sell, equip
    script.add('# the shop')
    script.put(keeper['x'], keeper['y'] - 30.0, keeper['z'])
    script.hold('square', 12, 90)
    for _ in range(7):
        script.tap('cross', 8, 70)
    script.tap('down', 8, 30)
    script.tap('cross', 8, 150)
    script.add('show g_paused:u32 g_simFrame:u32 g_players+0xe4:s32')
    script.tap('cross', 8, 40)                  # Buy
    script.tap('square', 8, 40)
    script.tap('square', 8, 40)
    script.add('show g_players+0xe4:s32 g_players+0x120:f32')
    script.tap('circle', 8, 40)
    script.tap('down', 8, 30)
    script.tap('cross', 8, 40)                  # Sell
    script.tap('cross', 8, 40)                  # equip what is under the cursor
    script.tap('cross', 8, 40)                  # and take it off again
    script.tap('square', 8, 40)                 # sell it
    script.add('show g_players+0xe4:s32 g_players+0x120:f32')
    script.tap('circle', 8, 40)
    script.tap('circle', 8, 80)
    script.add('tapuntil circle 30 g_paused:u32 == 0 timeout 600', 'wait 30')
    # the inventory screen: take the armour off, put it on, look at the pages
    script.add('# the inventory screen')
    script.tap('select', 8, 60)
    script.tap('cross', 8, 40)
    script.tap('cross', 8, 40)
    for _ in range(5):
        script.tap('r1', 8, 40)
    script.tap('circle', 8, 40)
    script.add('tapuntil circle 30 g_paused:u32 == 0 timeout 600', 'wait 30')
    # the save point
    script.add('# the save point')
    script.put(save['x'], save['y'] - 27.0, save['z'])
    script.hold('square', 12, 90)
    for _ in range(4):
        script.tap('cross', 8, 120)
    script.add('tapuntil circle 40 g_paused:u32 == 0 timeout 900', 'wait 60', 'show g_paused:u32 g_simFrame:u32')
    # the pause menu: the third entry is Load Game; the save just made; the level starts again
    script.add('# image', 'wait 4', '# load')
    script.tap('start', 8, 60)
    script.tap('down', 8, 30)
    script.tap('down', 8, 30)
    script.tap('cross', 8, 120)
    script.tap('cross', 8, 120)
    script.add('until g_simFrame:u32 >= 100 timeout 2500 continue', 'show g_levelName:str16 g_simFrame:u32 g_paused:u32 g_players+0xe4:s32',
               '# image', 'pad none 128 0', 'wait 60', 'pad none', 'wait 30', 'quit')
    return script, report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('what', choices=('fight', 'town'))
    parser.add_argument('name')
    parser.add_argument('--class', dest='cls', type=int, default=6)
    parser.add_argument('--levels', default='valor')
    parser.add_argument('--legs', type=int, default=4)
    parser.add_argument('--fight', type=int, default=216, help='frames of fighting per leg')
    parser.add_argument('--death-tries', type=int, default=30)
    parser.add_argument('--plain', action='store_true')
    parser.add_argument('--trees', default=os.path.join(ROOT, 'local', 'rig-out', 'p6-trees.json'))
    args = parser.parse_args()
    script, report = build_fight(args) if args.what == 'fight' else build_town(args)
    path = os.path.join(WORK, args.name + '.rig')
    with open(path, 'w') as sink:
        sink.write('\n'.join(script.lines) + '\n')
    for line in report:
        print('  ' + line)
    print('%s: %d lines, %d groups of memory writes' % (path, len(script.lines), script.groups))
    # register the session
    sessions = os.path.join(PROOF, 'sessions.json')
    table = json.load(open(sessions))
    table[args.name] = {'script': os.path.relpath(path, ROOT), 'watch': 'sound', 'ticked': True}
    marks = [line for line in script.lines if line == '# image']
    if marks:
        table[args.name]['dumps'] = marks
    with open(sessions, 'w') as sink:
        json.dump(table, sink, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
