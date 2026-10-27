#!/usr/bin/env python3
"""playtest.py - play the game as a tester does, in the Godot scene or the native program, through their control ports.

  python3 tools/recomp/app/playtest.py launch godot|native RUN [--portal] [--port N] [--program P] [--godot-out DIR] [-- EXTRA]
  python3 tools/recomp/app/playtest.py RUN status | objs [--near R] [--cls NAME] | shot NAME
  python3 tools/recomp/app/playtest.py RUN newgame                      # title -> new game -> a character -> the hub
  python3 tools/recomp/app/playtest.py RUN goto X Y [--radius R] [--timeout S]   # walk there (stick), fighting on the way
  python3 tools/recomp/app/playtest.py RUN fight [--radius R] [--timeout S]      # every hostile creature in reach
  python3 tools/recomp/app/playtest.py RUN loot [--radius R]             # walk over gold and things lying about, open chests
  python3 tools/recomp/app/playtest.py RUN use [--hold N]                # the use button where the character stands, then
                                                                         # the dialogue / menu answered with cross until play
  python3 tools/recomp/app/playtest.py RUN exit [LEVEL]                  # to the level's exit that asks for LEVEL (exitmap)
                                                                         # and through it: walk in or stand by and use
  python3 tools/recomp/app/playtest.py RUN clear [--timeout S]           # the level: fight, loot, everything reachable
  python3 tools/recomp/app/playtest.py RUN tap BUTTONS [HOLD] [AFTER] | hold BUTTONS FRAMES | stick X Y FRAMES
  python3 tools/recomp/app/playtest.py RUN put X Y [Z]                   # a teleport: the last resort, logged as one
  python3 tools/recomp/app/playtest.py RUN quit

RUN is a directory (local/playtest/NAME): the program's output, its data folder (memory card), pictures, run.json (how
to reach the program) and play.log (every command, what it saw, every suspect).  The Godot scene is run with
`--control PORT` (project dev/control.gd), the native program with `--control SOCKET` (app/control.h): the same
commands, so one driver plays both.  `--portal` starts the Godot copy the way a player does: the portal's first screen,
the Classic card's Play (portal/dev/shots.gd `solo`), and the game options of the command line.

Movement is the left stick: the stick's two axes are measured in the world at each level's start (up, right), and a
target's direction is mapped through them.  The way is straight; when the character stops getting closer it tries a
side step, then another; after that it gives up (`put` is the explicit last resort).  Every step is checked:
- stuck: the stick held and the character still for more than STUCK seconds;
- fall: the character's height far below where it last stood, or still falling;
- hit points not a number, below zero, above the maximum;
- an enemy beside the character, struck for some seconds, whose hit points do not move ("does not react");
- the level not changing after an exit was used; a level change that does not end;
- the picture: wholly black or white, or one colour (pictures of every step are kept under RUN/shots).
Suspects go to play.log with the picture's path.  Nothing here is game data; what it writes (pictures, maps) stays
under local/.  Object classes are named from vtables.txt, positions from the object pool (docs/objects.md).
"""
import argparse
import json
import math
import os
import random
import re
import shlex
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'play-net'))

DISC = os.environ.get('RTA_DISC') or os.path.expanduser('~/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso')
GODOT = os.path.join(ROOT, 'local', 'godot-spike', 'deps', 'godot-editor', 'Godot.app', 'Contents', 'MacOS', 'Godot')
EXITMAP = os.path.join(ROOT, 'local', 'playtest', 'exitmap.json')

# the game's memory (tools/recomp/app/tour.py, docs/player.md, docs/objects.md)
G_IN_FRONTEND, G_LEVEL_NAME, G_PENDING, G_PLAYERS = 0x41B510, 0x41B721, 0x41B6D0, 0x4D8AF0
G_CAMERA, G_SIM_FRAME, G_PAUSED = 0x4F8450, 0x44FDCC, 0x41B4F4
G_INVULNERABLE = 0x44F20C            # the game's own test switch (tools/recomp/app/tour.py): the last resort of play()
G_CUTSCENE = 0x44FCD0                # g_cutsceneActive (tools/recomp/proof/play.py)
POOL_CLASSES = 0x403A10              # g_poolClasses: {size, count, base, free head} x 3
PLAYER_OBJ = G_PLAYERS + 0x43D8
REC_HP, REC_HP_MAX, REC_LEVEL, REC_EXP, REC_GOLD = 0xAC, 0xB0, 0x59, 0x5C, 0xE4
OBJ_POS, OBJ_FLAGS, OBJ_CLASS, OBJ_HP, OBJ_HP_MAX = 0x10, 0x0C, 0x48, 0x228, 0x22C
FLAG_USABLE, FLAG_CREATURE = 0x100000, 0x20
FRIENDLY = {'Player', 'Player1', 'NPC', 'Critter', 'Natasla', 'Rondo', 'Zek', 'Marr'}
NOT_FOES = {'GameObject', 'Generator', 'ScriptGenerator', 'CreatureContainer', 'EggSack', 'SpiritAnchor', 'Catapult', 'Boat', 'SkulBoat'}
LOOT = {'Gold', 'ItemProp', 'DragonGoldPile'}
CHESTS = {'Chest', 'AutoChest', 'AutoChestLP', 'Container', 'AutoContainer', 'AutoContainerLP'}
STUCK = 2.5


def vtables():
    table = {}
    for line in open(os.path.join(ROOT, 'vtables.txt'), errors='replace'):
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith('0x'):
            table[int(parts[0], 16)] = parts[1]
    return table


# ---- the two programs' control ports ----------------------------------------------------------------------------------
class GodotPort:
    def __init__(self, port):
        self.s = socket.create_connection(('127.0.0.1', port), timeout=30)
        self.f = self.s.makefile('rw', encoding='utf-8', newline='\n')

    def cmd(self, line):
        self.f.write(line + '\n')
        self.f.flush()
        answer = self.f.readline().rstrip('\n')
        if not answer.startswith('ok'):
            raise RuntimeError('%s -> %s' % (line, answer))
        return answer[3:]

    def pad(self, buttons, lx=128, ly=128):
        self.used_pad = True
        self.cmd('pad %s %d %d 128 128' % ('+'.join(buttons) if buttons else 'none', lx, ly))

    def read(self, address, length):
        out = b''
        while length > 0:
            n = min(length, 0x40000)
            out += bytes.fromhex(self.cmd('peek 0x%x %d' % (address, n)))
            address += n
            length -= n
        return out

    def write(self, address, data):
        self.cmd('poke 0x%x %s' % (address, data.hex()))

    def shot(self, path):
        self.cmd('shot ' + path)

    def blanks(self):
        return int(re.search(r'blanks=(\d+)', self.cmd('info')).group(1))

    def app(self, text):
        self.cmd('app ' + text)

    def close(self):
        # the controller goes back to the keyboard only when this driver held it (a look at the state leaves a player's
        # driver alone: several can be connected)
        if getattr(self, 'used_pad', False):
            try:
                self.cmd('release')
            except Exception:
                pass
        self.s.close()


class NativePort:
    BUTTONS = 'up down left right cross circle square triangle l1 l2 l3 r1 r2 r3 start select'.split()

    def __init__(self, path, kind='native'):
        from ctl import Control
        self.c = Control(path, timeout=60)
        self.kind = kind

    def cmd(self, line):
        return self.c.ok(line)

    def pad(self, buttons, lx=128, ly=128):
        self.c.ok('release all')
        if buttons:
            self.c.ok('press ' + '+'.join(buttons))
        self.c.ok('stick l %d %d' % (lx, ly))

    def read(self, address, length):
        out = b''
        while length > 0:
            n = min(length, 0x10000)
            out += bytes.fromhex(self.c.ok('peek 0x%x hex%d' % (address, n)))
            address += n
            length -= n
        return out

    def write(self, address, data):
        data = data + b'\0' * (-len(data) % 4)
        for k in range(0, len(data), 4):
            self.c.ok('poke 0x%x u32 0x%08x' % (address + k, struct.unpack_from('<I', data, k)[0]))

    def shot(self, path):
        if self.kind == 'emu':          # the emulator writes a BMP (twice the width for its height: brought to 4:3 here)
            bmp = path[:-4] + '.bmp'
            self.c.ok('shotfb ' + bmp)
            try:
                from PIL import Image
                image = Image.open(bmp)
                image.convert('RGB').resize((image.height * 4 // 3, image.height)).save(path)
                os.remove(bmp)
            except Exception:
                pass
            return
        self.c.ok('shotfb ' + path)

    def blanks(self):
        return int(dict(re.findall(r'(\w+)=(\S+)', self.c.ok('info'))).get('pictures', 0))

    def app(self, text):
        self.c.ok('app ' + text)

    def close(self):
        try:
            self.c.ok('release all')
            self.c.ok('stick l 128 128')
        except Exception:
            pass
        self.c.close()


# ---- a run ----------------------------------------------------------------------------------------------------------
class Run:
    def __init__(self, path):
        self.dir = os.path.abspath(path)
        self.meta = json.load(open(os.path.join(self.dir, 'run.json')))
        self.port = GodotPort(self.meta['port']) if self.meta['kind'] == 'godot' else NativePort(self.meta['socket'], self.meta['kind'])
        self.names = vtables()
        self.log_file = open(os.path.join(self.dir, 'play.log'), 'a')
        self.state_path = os.path.join(self.dir, 'state.json')
        self.state = json.load(open(self.state_path)) if os.path.exists(self.state_path) else {}
        os.makedirs(os.path.join(self.dir, 'shots'), exist_ok=True)
        self.unreachable = set(self.state.get('unreachable', [])) if self.state.get('unreachable_level') == self.level() else set()

    def save(self):
        with open(self.state_path, 'w') as sink:
            json.dump(self.state, sink, indent=1)

    def log(self, text):
        line = time.strftime('%H:%M:%S ') + text
        print(line, flush=True)
        self.log_file.write(line + '\n')
        self.log_file.flush()

    def suspect(self, kind, text, picture=True):
        path = self.shot('suspect-' + kind) if picture else ''
        self.log('SUSPECT %s: %s%s' % (kind, text, ' [%s]' % path if path else ''))
        self.state.setdefault('suspects', []).append({'kind': kind, 'text': text, 'shot': path, 'level': self.level(), 't': time.time()})
        self.save()

    # -- memory --
    def u32(self, a):
        return struct.unpack('<I', self.port.read(a, 4))[0]

    def f32(self, a):
        return struct.unpack('<f', self.port.read(a, 4))[0]

    def text(self, a, n=16):
        return self.port.read(a, n).split(b'\0')[0].decode('latin-1')

    def level(self):
        return self.text(G_LEVEL_NAME)

    def player(self):
        obj = self.u32(PLAYER_OBJ)
        rec = self.port.read(G_PLAYERS, 0xE8)
        hp, hp_max = struct.unpack_from('<2f', rec, REC_HP)
        out = {'obj': obj, 'hp': hp, 'hp_max': hp_max, 'lvl': rec[REC_LEVEL], 'exp': struct.unpack_from('<i', rec, REC_EXP)[0],
               'gold': struct.unpack_from('<i', rec, REC_GOLD)[0], 'pos': None}
        if obj and 0x100000 <= obj < 0x4000000:
            out['pos'] = struct.unpack('<3f', self.port.read(obj + OBJ_POS, 12))
        return out

    def pos(self):
        obj = self.u32(PLAYER_OBJ)
        if not obj or not 0x100000 <= obj < 0x4000000:
            return None
        return struct.unpack('<3f', self.port.read(obj + OBJ_POS, 12))

    def camera_follows(self):
        cam = self.u32(G_CAMERA)
        return bool(cam) and self.u32(cam + 0x34) == 1 and not self.port.read(G_CUTSCENE, 1)[0]

    def paused(self):
        return self.u32(G_PAUSED) != 0

    def objects(self):
        table = self.port.read(POOL_CLASSES, 48)
        out = []
        for n in range(3):
            size, count, base, _free = struct.unpack_from('<4I', table, 16 * n)
            if not (0 < size < 0x10000 and 0 < count < 100000 and 0x100000 <= base < 0x4000000):
                continue
            blob = self.port.read(base, size * count)
            for k in range(count):
                at = k * size
                cls = self.names.get(struct.unpack_from('<I', blob, at + OBJ_CLASS)[0])
                if not cls:
                    continue
                x, y, z = struct.unpack_from('<3f', blob, at + OBJ_POS)
                if not all(math.isfinite(v) and abs(v) < 1e6 for v in (x, y, z)):
                    continue
                o = {'addr': base + at, 'cls': cls, 'x': x, 'y': y, 'z': z, 'flags': struct.unpack_from('<I', blob, at + OBJ_FLAGS)[0]}
                if size > OBJ_HP_MAX + 4:
                    hp, top = struct.unpack_from('<2f', blob, at + OBJ_HP)
                    if o['flags'] & FLAG_CREATURE and math.isfinite(hp) and math.isfinite(top) and 0 < top < 1e6:
                        o['hp'], o['hp_max'] = hp, top
                out.append(o)
        return out

    def creatures(self, me=None):
        me = me or self.pos()
        found = []
        for o in self.objects():
            if 'hp' not in o or o['cls'] in FRIENDLY or o['cls'] in NOT_FOES or o['hp'] <= 0 or o['cls'].startswith(('Skill', 'Spell')):
                continue
            if me:
                o['d'] = math.hypot(o['x'] - me[0], o['y'] - me[1])
                o['dz'] = o['z'] - me[2]
            found.append(o)
        return sorted(found, key=lambda o: o.get('d', 0))

    # -- input --
    def pad(self, buttons=(), lx=128, ly=128):
        self.port.pad(list(buttons), lx, ly)

    def tap(self, buttons, hold=6, after=20):
        self.pad(buttons.split('+'))
        time.sleep(hold / 60.0)
        self.pad()
        time.sleep(after / 60.0)

    def shot(self, name):
        self.state['shot_n'] = self.state.get('shot_n', 0) + 1
        path = os.path.join(self.dir, 'shots', '%04d-%s-%s.png' % (self.state['shot_n'], self.level() or 'none', name))
        self.port.shot(path)
        self.save()
        time.sleep(0.15)
        self._look(path)
        return path

    def _look(self, path):
        # the picture: wholly black, white or one colour is a suspect (a load's own black is told apart by the caller)
        for _ in range(20):
            if os.path.exists(path) and os.path.getsize(path) > 0:
                break
            time.sleep(0.1)
        try:
            from PIL import Image, ImageStat
            time.sleep(0.1)
            image = Image.open(path).convert('RGB').resize((160, 120))
            stat = ImageStat.Stat(image)
            mean, spread = sum(stat.mean) / 3, sum(stat.stddev) / 3
            self.state['last_picture'] = {'path': path, 'mean': round(mean, 1), 'spread': round(spread, 1)}
            if spread < 2.0 and self.camera_follows() and not self.paused() and self.pos():
                self.log('SUSPECT picture: one colour (mean %.1f) while the game plays [%s]' % (mean, path))
                self.state.setdefault('suspects', []).append({'kind': 'picture', 'text': 'one colour %.1f' % mean, 'shot': path,
                                                              'level': self.level(), 't': time.time()})
        except Exception as error:      # (a picture not yet written: no judgement)
            self.state['last_picture'] = {'path': path, 'error': str(error)}

    def every(self, tag, seconds=8.0):
        # a picture every few seconds of play (the pictures are looked at afterwards; the automatic checks run on each)
        now = time.time()
        if now - getattr(self, '_last_shot', 0) >= seconds:
            self._last_shot = now
            self.shot(tag)

    # -- the stick in the world --
    def calibrate(self, force=False):
        level = self.level()
        cal = self.state.get('cal', {})
        if not force and cal.get('level') == level:
            return cal
        for _ in range(3):
            p0 = self.pos()
            self.pad((), 128, 0)
            time.sleep(0.4)
            p1 = self.pos()
            self.pad((), 255, 128)
            time.sleep(0.4)
            p2 = self.pos()
            self.pad()
            time.sleep(0.2)
            if p0 and p1 and p2:
                up, right = (p1[0] - p0[0], p1[1] - p0[1]), (p2[0] - p1[0], p2[1] - p1[1])
                if math.hypot(*up) > 5 and math.hypot(*right) > 5:
                    # keep only the directions: the stick's axes in the world (unit vectors)
                    nu, nr = math.hypot(*up), math.hypot(*right)
                    cal = {'level': level, 'up': [up[0] / nu, up[1] / nu], 'right': [right[0] / nr, right[1] / nr], 'speed': (nu + nr) / 0.8}
                    self.state['cal'] = cal
                    self.save()
                    self.log('calibrated in %s: up (%.2f, %.2f), right (%.2f, %.2f), %.0f units a second' % (
                        level, cal['up'][0], cal['up'][1], cal['right'][0], cal['right'][1], cal['speed']))
                    return cal
            time.sleep(0.5)
        # the overhead camera's usual axes (most levels): up = +x+y, right = +x-y
        cal = {'level': level, 'up': [0.7071, 0.7071], 'right': [0.7071, -0.7071], 'speed': 150, 'guessed': True}
        self.log('calibration failed in %s (the character did not move); using the usual axes' % level)
        self.state['cal'] = cal
        self.save()
        return cal

    def stick_toward(self, dx, dy, turn=0.0):
        cal = self.calibrate()
        c, s = math.cos(turn), math.sin(turn)
        dx, dy = dx * c - dy * s, dx * s + dy * c
        ux, uy = cal['up']
        rx, ry = cal['right']
        det = ux * ry - uy * rx
        if abs(det) < 1e-6:
            a, b = dx * ux + dy * uy, dx * rx + dy * ry
        else:   # (dx, dy) = a * up + b * right
            a = (dx * ry - dy * rx) / det
            b = (ux * dy - uy * dx) / det
        scale = max(abs(a), abs(b), 1e-6)
        return int(round(128 + 127 * b / scale)), int(round(128 - 127 * a / scale))

    # -- checks run at every step --
    def check(self, me, last):
        p = self.player()
        hp, top = p['hp'], p['hp_max']
        if not math.isfinite(hp) or hp < -1 or (top > 0 and hp > top * 1.01 + 1):
            self.suspect('hit-points', 'hit points %r of %r' % (hp, top))
        if me and last and last.get('ground') is not None and me[2] < last['ground'] - 400:
            self.suspect('fall', 'the character at height %.0f, it stood at %.0f' % (me[2], last['ground']))
            last['ground'] = me[2]
        return p

    # -- walking --
    # -- the way: a grid of what the character has found (free where it stood, blocked where it could not go), A* over it
    # with the unknown taken as free (the way is learnt by walking it, as a player learns a level) --
    CELL = 40.0

    def _grid(self):
        level = self.level()
        g = self.state.get('grid', {})
        if g.get('level') != level:
            g = {'level': level, 'blocked': [], 'free': []}
            self.state['grid'] = g
        if not hasattr(self, '_blocked') or getattr(self, '_grid_level', None) != level:
            self._blocked = set(tuple(c) for c in g['blocked'])
            self._free = set(tuple(c) for c in g['free'])
            self._grid_level = level
        return g

    def _cell(self, x, y):
        return (int(math.floor(x / self.CELL)), int(math.floor(y / self.CELL)))

    def _grid_save(self):
        g = self._grid()
        g['blocked'] = [list(c) for c in self._blocked][-20000:]
        g['free'] = [list(c) for c in self._free][-40000:]
        self.save()

    def plan(self, start, goal, limit=60000):
        import heapq
        self._grid()
        s, t = self._cell(start[0], start[1]), self._cell(goal[0], goal[1])
        if s == t:
            return [goal]
        span = max(abs(s[0] - t[0]), abs(s[1] - t[1])) + 40
        lo = (min(s[0], t[0]) - span, min(s[1], t[1]) - span)
        hi = (max(s[0], t[0]) + span, max(s[1], t[1]) + span)
        h = lambda c: math.hypot(c[0] - t[0], c[1] - t[1])
        openq = [(h(s), 0.0, s)]
        came = {s: None}
        cost = {s: 0.0}
        n = 0
        while openq and n < limit:
            _, g0, c = heapq.heappop(openq)
            n += 1
            if c == t:
                break
            if g0 > cost.get(c, 1e18):
                continue
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not dx and not dy:
                        continue
                    nb = (c[0] + dx, c[1] + dy)
                    if nb in self._blocked or not (lo[0] <= nb[0] <= hi[0] and lo[1] <= nb[1] <= hi[1]):
                        continue
                    if dx and dy and ((c[0] + dx, c[1]) in self._blocked or (c[0], c[1] + dy) in self._blocked):
                        continue
                    step = (1.4142 if dx and dy else 1.0) * (0.7 if nb in self._free else 1.0)
                    g1 = g0 + step
                    if g1 < cost.get(nb, 1e18):
                        cost[nb] = g1
                        came[nb] = c
                        heapq.heappush(openq, (g1 + h(nb) * 0.7, g1, nb))
        if t not in came:
            return None
        path, c = [], t
        while c is not None:
            path.append(((c[0] + 0.5) * self.CELL, (c[1] + 0.5) * self.CELL))
            c = came[c]
        path.reverse()
        path[-1] = goal
        return path

    def goto(self, x, y, radius=40.0, timeout=60.0, fight=True, label=''):
        """Walks to (x, y) along the grid's way. Returns 'there', 'stuck', 'timeout', 'level' or 'dead'."""
        level = self.level()
        start = time.time()
        moved_at = start
        last_pos = None
        last = {'ground': None}
        self.calibrate()
        self._grid()
        path = None
        progress_t, progress_d = start, 1e9
        replans = 0
        self._forgot = False
        while time.time() - start < timeout:
            if self.level() != level:
                self.pad()
                self._grid_save()
                return 'level'
            me = self.pos()
            if me is None:
                self.pad()
                time.sleep(0.3)
                continue
            p = self.check(me, last)
            if p['hp'] <= 0:
                self.pad()
                self._grid_save()
                return 'dead'
            if not self.camera_follows() or self.paused():
                self.pad()
                self.answer()
                progress_t, progress_d = time.time(), 1e9
                continue
            if last['ground'] is None or me[2] > last['ground'] - 100:
                last['ground'] = me[2] if last['ground'] is None else max(me[2], last['ground'] - 5)
            here = self._cell(me[0], me[1])
            if p['hp_max'] > 0 and p['hp'] >= 0.9 * p['hp_max'] and time.time() - getattr(self, '_safe_t', 0) > 2:
                self._safe_t = time.time()
                if not [c for c in self.creatures(me) if c['d'] < 350]:
                    self.state['safe'] = list(me)
            self._free.add(here)
            self._blocked.discard(here)
            d = math.hypot(x - me[0], y - me[1])
            self.every('walk')
            if d <= radius:
                self.pad()
                self._grid_save()
                return 'there'
            if last_pos and math.hypot(me[0] - last_pos[0], me[1] - last_pos[1]) > 4:
                moved_at = time.time()
            last_pos = me
            if fight:
                near = [c for c in self.creatures(me) if c['d'] < 90 and abs(c['dz']) < 80 and c['addr'] not in self.unreachable]
                if near:
                    self.pad()
                    self.fight(radius=140, timeout=25, quiet=True)
                    path = None
                    progress_t = time.time()
                    continue
            if path is None:
                path = self.plan(me, (x, y))
                if path is None and not getattr(self, '_forgot', False):
                    # what was learnt round here may be wrong (a creature in the way, a door since opened): forgotten once
                    self._forgot = True
                    c0 = self._cell(me[0], me[1])
                    self._blocked = set(c for c in self._blocked if max(abs(c[0] - c0[0]), abs(c[1] - c0[1])) > 4)
                    path = self.plan(me, (x, y))
                replans += 1
                if path is None or replans > 40:
                    self.pad()
                    self._grid_save()
                    if time.time() - moved_at > STUCK:
                        self.suspect('stuck', 'walking to (%.0f, %.0f)%s: no way left on the grid, the character has not moved for %.1f s at (%.0f, %.0f, %.0f)' % (
                            x, y, ' ' + label if label else '', time.time() - moved_at, me[0], me[1], me[2]))
                    return 'stuck'
                progress_t, progress_d = time.time(), 1e9
            # the next waypoint: the first on the way more than a cell and a half away
            while len(path) > 1 and math.hypot(path[0][0] - me[0], path[0][1] - me[1]) < self.CELL * 1.5:
                path.pop(0)
            wx, wy = path[0]
            wd = math.hypot(wx - me[0], wy - me[1])
            if wd < progress_d - 6:
                progress_d, progress_t = wd, time.time()
            elif time.time() - progress_t > 0.9:
                # no nearer to the waypoint: the cell ahead (toward it) is blocked; the way is planned again
                ux, uy = (wx - me[0]) / max(wd, 1e-6), (wy - me[1]) / max(wd, 1e-6)
                ahead = self._cell(me[0] + ux * self.CELL, me[1] + uy * self.CELL)
                if ahead != here:
                    self._blocked.add(ahead)
                else:
                    self._blocked.add(self._cell(wx, wy))
                path = None
                continue
            lx, ly = self.stick_toward(wx - me[0], wy - me[1])
            self.pad((), lx, ly)
            time.sleep(0.08)
        self.pad()
        self._grid_save()
        return 'timeout'

    def answer(self, limit=40):
        """A dialogue, a notice or a scene has the camera: cross until play goes on (START skips a scene)."""
        for k in range(limit):
            if self.camera_follows() and not self.paused():
                return True
            self.tap('cross' if k % 6 != 5 else 'start', 5, 25)
        return self.camera_follows()

    # -- fighting --
    def fight(self, radius=300.0, timeout=60.0, quiet=False):
        start = time.time()
        kills = 0
        level = self.level()
        struck = {}
        unreachable = self.unreachable
        while time.time() - start < timeout and self.level() == level:
            me = self.pos()
            if not me:
                time.sleep(0.3)
                continue
            p = self.player()
            if p['hp'] <= 0:
                self.pad()
                return 'dead'
            if not self.camera_follows():
                self.pad()
                self.answer()
                continue
            foes = [c for c in self.creatures(me) if c['d'] < radius and abs(c['dz']) < 120 and c['addr'] not in unreachable]
            if not foes:
                self.pad()
                break
            foe = foes[0]
            self.every('fight')
            close = [c for c in foes if c['d'] < 140]
            if p['hp_max'] > 0 and p['hp'] < 0.35 * p['hp_max'] and len(close) >= 2 and self.state.get('safe'):
                sx, sy = self.state['safe'][:2]
                self.log('fight: hit points %.0f of %.0f among %d: back to (%.0f, %.0f)' % (p['hp'], p['hp_max'], len(close), sx, sy))
                self.pad()
                self.goto(sx, sy, radius=60, timeout=20, fight=False, label='retreat')
                self.rest()
                continue
            dx, dy = foe['x'] - me[0], foe['y'] - me[1]
            key = foe['addr']
            seen = struck.setdefault(key, {'t': time.time(), 'hp': foe['hp'], 'hp0': foe['hp'], 'cls': foe['cls'], 'pos': (foe['x'], foe['y'])})
            if foe['d'] > 45:
                # toward it; a creature the character does not get closer to in 4 s (a wall, a cliff) is left
                if foe['d'] < seen.get('best', 1e9) - 8:
                    seen['best'], seen['best_t'] = foe['d'], time.time()
                elif time.time() - seen.get('best_t', time.time()) > 4:
                    unreachable.add(key)
                    self.state['unreachable'], self.state['unreachable_level'] = list(unreachable), self.level()
                    seen.pop('best', None)
                    continue
                seen.setdefault('best_t', time.time())
                lx, ly = self.stick_toward(dx, dy)
                self.pad((), lx, ly)
                time.sleep(0.12)
                if foe['d'] > 60:
                    seen['t'] = time.time()
                continue
            # beside it: face it and strike (a tap of the stick toward it, then the attack button); now and then the
            # skills on circle and triangle; a health potion (L2) when the hit points are low
            lx, ly = self.stick_toward(dx, dy)
            now = time.time()
            if p['hp_max'] > 0 and p['hp'] < 0.4 * p['hp_max'] and now - self.state.get('potion_t', 0) > 4:
                self.state['potion_t'] = now
                self.tap('l2', 4, 6)
            button = 'cross'
            if now - self.state.get('skill_t', 0) > 3:
                self.state['skill_t'] = now
                button = random.choice(('circle', 'triangle'))
            self.pad((), lx, ly)
            time.sleep(0.05)
            self.pad((button,), lx, ly)
            time.sleep(0.1)
            self.pad()
            time.sleep(0.12)
            if foe['hp'] < seen['hp'] - 0.01:
                seen['hp'], seen['t'] = foe['hp'], time.time()
            elif time.time() - seen['t'] > 12 and not seen.get('told'):
                seen['told'] = True
                self.suspect('no-damage', '%s at (%.0f, %.0f) struck beside the character for 12 s, hit points %.1f of %.1f unchanged' % (
                    foe['cls'], foe['x'], foe['y'], foe['hp'], foe['hp_max']))
        self.pad()
        dead = sum(1 for key, seen in struck.items() if key not in [c['addr'] for c in self.creatures()] or seen.get('hp', 1) <= 0)
        hurt = sum(1 for seen in struck.values() if seen.get('hp0', seen['hp']) > seen['hp'])
        self.state['kills'] = self.state.get('kills', 0) + dead
        self.save()
        self.log('fight: %d engaged, %d hurt, %d gone; hit points %.0f of %.0f, experience %d' % (
            len(struck), hurt, dead, self.player()['hp'], self.player()['hp_max'], self.player()['exp']))
        left = [c for c in self.creatures() if c.get('d', 1e9) < radius]
        if not quiet:
            self.log('fight: %d creatures left within %.0f (%s)' % (len(left), radius, ', '.join(sorted(set(c['cls'] for c in left))) or '-'))
        return 'clear' if not left else 'left'

    # -- things to pick up --
    def loot(self, radius=600.0, timeout=90.0):
        start = time.time()
        tried = set(self.state.get('looted', []))
        got = 0
        while time.time() - start < timeout:
            me = self.pos()
            if not me:
                break
            items = [o for o in self.objects() if (o['cls'] in LOOT or o['cls'] in CHESTS) and o['addr'] not in tried]
            items = sorted(items, key=lambda o: math.hypot(o['x'] - me[0], o['y'] - me[1]))
            items = [o for o in items if math.hypot(o['x'] - me[0], o['y'] - me[1]) < radius and abs(o['z'] - me[2]) < 120]
            if not items:
                break
            o = items[0]
            tried.add(o['addr'])
            gold = self.player()['gold']
            near = 18 if o['cls'] in LOOT else 40
            result = self.goto(o['x'], o['y'], radius=near, timeout=20, label=o['cls'])
            if result in ('there', 'stuck', 'timeout') and self.pos() and math.hypot(o['x'] - self.pos()[0], o['y'] - self.pos()[1]) < 60:
                if o['cls'].startswith(('Container', 'AutoContainer')):
                    for _ in range(3):          # barrels are broken open
                        self.tap('cross', 6, 20)
                else:
                    self.tap('square', 8, 30)
                    if o['cls'] in CHESTS:
                        self.tap('square', 8, 40)
                self.answer(6)
                got += 1
                result = 'used'
            after = self.player()['gold']
            self.log('loot: %s at (%.0f, %.0f): %s, gold %d -> %d' % (o['cls'], o['x'], o['y'], result, gold, after))
        self.state['looted'] = list(tried)[-400:]
        self.save()
        return got

    # -- a level-up the game's own way (docs/hud-dynamic.md: acknowledged +0x58 below the level +0x59) --
    def level_up(self):
        rec = self.port.read(G_PLAYERS + 0x58, 2)
        exp = self.player()['exp']
        table = struct.unpack('<50i', self.port.read(0x41B558, 200))       # g_expTable: the experience at which level n ends
        earned = sum(1 for n in range(1, 50) if table[n] > 0 and exp >= table[n]) + 1
        if rec[0] >= rec[1] and earned <= rec[1]:
            return False
        rec = bytes([rec[0], max(rec[1], earned)])
        self.log('level-up: level %d (acknowledged %d): the screen, its points spent' % (rec[1], rec[0]))
        self.tap('select', 8, 60)
        self.shot('levelup-abilities')
        for _ in range(6):                  # ability points: cross on the first row (strength)
            self.tap('cross', 6, 20)
        self.tap('r1', 6, 40)
        self.shot('levelup-skills')
        for _ in range(3):                  # a skill point: the first skill
            self.tap('cross', 6, 20)
        for _ in range(4):
            self.tap('circle', 6, 30)
            if self.camera_follows() and not self.paused():
                break
        self.answer(10)
        after = self.port.read(G_PLAYERS + 0x58, 2)
        self.log('level-up: acknowledged %d of %d now' % (after[0], after[1]))
        return True

    def rest(self, want=0.9, limit=90.0):
        """Hit points low and nothing near: stand and let them come back (as a player waits), a potion first (L2)."""
        p = self.player()
        if p['hp_max'] <= 0 or p['hp'] >= 0.6 * p['hp_max']:
            return
        self.tap('l2', 4, 10)
        start = time.time()
        while time.time() - start < limit:
            p = self.player()
            if p['hp'] >= want * p['hp_max'] or p['hp'] <= 0:
                break
            near = [c for c in self.creatures() if c['d'] < 250]
            if near:
                self.fight(radius=250, timeout=20, quiet=True)
                continue
            time.sleep(1.0)
        self.log('rest: hit points %.0f of %.0f after %.0f s' % (p['hp'], p['hp_max'], time.time() - start))

    def save_game(self, limit=2500.0):
        """To the nearest save point (if one is within `limit`), use it, the card's questions answered: Save Successful."""
        me = self.pos()
        points = sorted((math.hypot(o['x'] - me[0], o['y'] - me[1]), o) for o in self.objects() if o['cls'] == 'Savepoint') if me else []
        if not points or points[0][0] > limit:
            return False
        o = points[0][1]
        if self.goto(o['x'], o['y'], radius=45, timeout=90, label='save point') != 'there':
            return False
        self.tap('square', 10, 60)
        for _ in range(4):
            self.tap('cross', 8, 100)
        self.answer(10)
        p = self.player()
        self.state['saved'] = {'exp': p['exp'], 'gold': p['gold'], 'level': self.level(), 't': time.time()}
        self.save()
        self.log('saved at the save point (%.0f, %.0f): experience %d, gold %d' % (o['x'], o['y'], p['exp'], p['gold']))
        self.shot('saved')
        return True

    # -- play a level: fight what is there, pick up what lies about, on to the next creature --
    def play(self, timeout=600.0, radius=500.0):
        start = time.time()
        level = self.level()
        skip = set()
        while time.time() - start < timeout:
            if self.level() != level:
                return 'level'
            if self.player()['hp'] <= 0:
                deaths = self.state.setdefault('deaths', {})
                deaths[level] = deaths.get(level, 0) + 1
                self.log('death %d in %s' % (deaths[level], level))
                self.save()
                time.sleep(3)
                self.arrive()
                if deaths[level] >= 3:
                    # the last resort, as a teleport is: the game's own invulnerability for the rest of this level, said so
                    self.port.write(G_INVULNERABLE, struct.pack('<I', 1))
                    self.state['invulnerable'] = level
                    self.save()
                    self.log('LAST RESORT: invulnerability on in %s after %d deaths' % (level, deaths[level]))
                continue
            if self.level_up() or self.player()['exp'] - self.state.get('saved', {}).get('exp', 0) >= 600:
                self.save_game()
            result = self.fight(radius=radius, timeout=40, quiet=True)
            if result == 'dead':
                continue
            self.loot(radius=radius, timeout=40)
            me = self.pos()
            if not me:
                time.sleep(1)
                continue
            self.rest()
            me = self.pos() or me
            foes = [c for c in self.creatures(me) if c['addr'] not in skip and c['addr'] not in self.unreachable]
            if not foes:
                self.log('play: no creature left that the character can reach in %s' % level)
                return 'explored'
            # the nearest creature that stands with at most one other; a crowd only when nothing else is left
            def crowd(c):
                return sum(1 for o in foes if math.hypot(o['x'] - c['x'], o['y'] - c['y']) < 220)
            alone = [c for c in foes if crowd(c) <= 2]
            foe = (alone or foes)[0]
            self.log('play: on to the %s at (%.0f, %.0f), %.0f away (%d creatures left)' % (foe['cls'], foe['x'], foe['y'], foe['d'], len(foes)))
            r = self.goto(foe['x'], foe['y'], radius=60, timeout=60, label=foe['cls'])
            if r in ('stuck', 'timeout'):
                skip.add(foe['addr'])
            if r == 'level':
                return 'level'
        return 'timeout'

    # -- exits (exitmap.py) --
    def exits(self):
        if not os.path.exists(EXITMAP):
            subprocess.run([sys.executable, os.path.join(HERE, 'exitmap.py')], check=True)
        level = self.level()
        objs = json.load(open(EXITMAP)).get(level, [])
        out = []
        for o in objs:
            reach = o.get('reaches', {})
            dest = [a[0] for name in ('newWorld', 'simpleNewWorld', 'newWorldAlways') for a in reach.get(name, []) if a]
            if dest or 'activateMissionMenu' in reach:
                o['dest'] = dest or ['missions']
                out.append(o)
        return out

    def take_exit(self, want=None, timeout=120.0):
        level = self.level()
        me = self.pos()
        cands = [o for o in self.exits() if not want or want in o['dest']]
        if not cands:
            self.log('exit: %s has no exit to %s in the map' % (level, want))
            return 'none'
        cands.sort(key=lambda o: math.hypot(o['x'] - me[0], o['y'] - me[1]) + (0 if o['cls'] == 'PushTrigger' else 30))
        for o in cands[:4]:
            if o['cls'] == 'Trigger' and o.get('rect'):
                x0, y0, x1, y1 = o['rect']
                tx, ty = (x0 + x1) / 2, (y0 + y1) / 2
                rad = max(10.0, min(x1 - x0, y1 - y0) / 2 - 10)
            else:
                tx, ty, rad = o['x'], o['y'], 30.0
            self.log('exit: to %s by the %s at (%.0f, %.0f) (it asks for %s)' % (want or 'any', o['cls'], tx, ty, ','.join(o['dest'])))
            result = self.goto(tx, ty, radius=rad, timeout=timeout)
            if result == 'level':
                return 'level'
            if result != 'there':
                self.log('exit: %s on the way (%s)' % (result, o['cls']))
                continue
            if o['cls'] == 'PushTrigger':
                for _ in range(3):
                    self.tap('square', 10, 40)
                    if self.wait_level(level, 4.0):
                        return 'level'
                    self.answer(10)
                    if self.wait_level(level, 6.0):
                        return 'level'
            elif self.wait_level(level, 8.0):
                return 'level'
            self.log('exit: the %s at (%.0f, %.0f) did not take the character away (a key or the story may hold it)' % (o['cls'], tx, ty))
            self.shot('exit-held')
        return 'held'

    def wait_level(self, level, seconds):
        until = time.time() + seconds
        while time.time() < until:
            if self.level() != level or self.u32(G_PENDING) & 0xff:
                return True
            time.sleep(0.25)
        return False

    def arrive(self, timeout=180.0):
        """After a level change: until the new level plays (the load, its scene skipped, a notice answered)."""
        start = time.time()
        while time.time() - start < timeout:
            if not (self.u32(G_PENDING) & 0xff) and self.pos() and self.u32(G_SIM_FRAME) > 20 and self.player()['hp'] > 0:
                break
            time.sleep(0.5)
        else:
            self.suspect('load', 'the level %s did not start within %.0f s' % (self.level(), timeout))
            return False
        took = time.time() - start
        if self.state.get('invulnerable') and self.state['invulnerable'] != self.level():
            self.port.write(G_INVULNERABLE, struct.pack('<I', 0))
            self.log('invulnerability off again (left %s)' % self.state.pop('invulnerable'))
        self.shot('arrive')
        self.answer(60)
        self.state.pop('cal', None)
        self.save()
        self.log('arrived in %s after %.1f s' % (self.level(), took))
        return True


# ---- launching ----------------------------------------------------------------------------------------------------------
def launch(args):
    run = os.path.abspath(args.run)
    os.makedirs(os.path.join(run, 'shots'), exist_ok=True)
    data = os.path.join(run, 'data')
    os.makedirs(data, exist_ok=True)
    meta = {'kind': args.kind, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}
    out = open(os.path.join(run, args.kind + '.out'), 'a')
    if args.kind == 'godot':
        port = args.port or random.randint(20000, 40000)
        godot_out = os.path.abspath(args.godot_out)
        home = os.path.join(run, 'godot-home')
        env = dict(os.environ, XDG_CONFIG_HOME=home + '/config', XDG_DATA_HOME=home + '/data', XDG_CACHE_HOME=home + '/cache',
                   RTA_CWD=ROOT)
        for sub in ('config', 'data', 'cache'):
            os.makedirs(os.path.join(home, sub), exist_ok=True)
        game = ['--disc', DISC, '--data', data, '--workspace', ROOT, '--mute', '--test', 'classic playtest', '--control', str(port),
                '--frame-log', os.path.join(run, 'frames.csv'), '--figures', os.path.join(run, 'figures.txt')]
        if args.audio:
            game += ['--audio-tap', os.path.join(run, 'master.wav')]
        if args.portal:
            env['RTA_SHOTS_EDITION_A'] = 'classic'
            command = [GODOT, '--path', os.path.join(godot_out, 'project'), 'res://portal/dev/shots.tscn', '--', '--out',
                       os.path.join(run, 'portal'), '--portal-data', os.path.join(run, 'portal-data'), '--only', 'solo'] + game
        else:
            command = [GODOT, '--path', os.path.join(godot_out, 'project'), '--', '--no-portal', '--edition', 'classic', '--mode', 'scene'] + game
        meta['port'] = port
    elif args.kind == 'emu':
        # the original in the emulator (the reference of docs/issues/classic-complete.md: the Play! build, no patch section)
        sock = '/tmp/rta-playtest-emu-%d.sock' % os.getpid()
        command = [os.path.join(ROOT, 'tools', 'play-net', 'play.sh'), '--disc', DISC, '--data', data, '--sections', 'none', '--',
                   '--rta-test', 'classic playtest reference - silent, no network', '--rta-no-net', '--rta-control', sock]
        meta['socket'] = sock
        env = dict(os.environ)
    else:
        sock = '/tmp/rta-playtest-%d.sock' % os.getpid()
        command = [args.program, '--disc', DISC, '--data', data, '--test', 'classic playtest', '--window', '640x448', '--control', sock]
        meta['socket'] = sock
        env = dict(os.environ)
    command += args.extra
    command = ['nice', '-n', str(args.nice)] + command
    process = subprocess.Popen(command, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=ROOT, start_new_session=True)
    meta['pid'] = process.pid
    meta['command'] = command
    with open(os.path.join(run, 'run.json'), 'w') as sink:
        json.dump(meta, sink, indent=1)
    print('launched %s pid %d (%s)' % (args.kind, process.pid, run))
    for _ in range(600):
        time.sleep(0.5)
        try:
            Run(run).port.close()
            print('control port answers')
            return 0
        except Exception:
            if process.poll() is not None:
                print('the program ended: %d' % process.returncode)
                return 1
    return 1


# ---- the game's own way into the first level ----------------------------------------------------------------------------
def new_game(r, class_taps=0, stat_row=0):
    """Title -> new game -> offline -> one player -> the mission game -> difficulty -> a character -> the hub (the
    presses of tour.py to_hub, but each screen waited for)."""
    r.log('new game: waiting for the front end')
    for _ in range(240):
        if r.u32(G_IN_FRONTEND) & 0xff == 1 and r.level() == 'intro':
            break
        r.tap('cross', 6, 40)
    else:
        r.suspect('frontend', 'the front end did not come up')
        return False
    time.sleep(7)
    r.shot('frontend')
    for after in (90, 90, 90, 90, 200):
        r.tap('cross', 8, after)
    for _ in range(class_taps):             # the next class on the class screen
        r.tap('right', 6, 50)
    r.shot('class')
    r.tap('cross', 8, 120)
    r.shot('appearance')
    r.tap('cross', 8, 120)
    for _ in range(stat_row):               # the row the 20 points go to (0 strength ... 3 stamina)
        r.tap('down', 4, 10)
    for _ in range(20):
        r.tap('right', 4, 6)
    time.sleep(0.4)
    r.shot('abilities')
    r.tap('cross', 8, 120)
    r.shot('name')
    for _ in range(3):
        r.tap('cross', 4, 8)
    for _ in range(6):
        r.tap('down', 4, 8)
    for _ in range(5):
        r.tap('right', 4, 8)
    r.tap('cross', 8, 60)
    for _ in range(240):
        if r.level() == 'hub' and r.u32(PLAYER_OBJ):
            break
        time.sleep(0.5)
    else:
        r.suspect('newgame', 'the hub was not reached')
        return False
    r.arrive()
    return True


def frame_report(path, settle=3.0):
    """The frame log (main.gd --frame-log): game frames' intervals per level, the late ones, after each level's first
    `settle` seconds (a load holds the game on purpose)."""
    rows = []
    level, since = '', 0
    per = {}
    last = None
    marks = set()
    for line in open(path):
        f = line.rstrip('\n').split(',')
        if f[0] == 'M' and len(f) > 2 and f[2].startswith('control'):
            marks.add(int(f[1]))
            continue
        if f[0] == 'L' and len(f) > 2:
            if f[2] != level:
                level, since, last = f[2], None, None
            continue
        if not f[0].isdigit() or len(f) < 7 or f[2] != '1':
            continue
        t = int(f[0])
        if since is None:
            since = t
        blank = int(f[6])
        if last is not None and (t - since) / 1e6 >= settle and not any(blank - k in marks for k in range(0, 4)):
            gap = (t - last) / 1000.0
            d = per.setdefault(level or '-', {'n': 0, 'late25': 0, 'late50': 0, 'worst': 0.0, 'worst_blank': 0, 'sum': 0.0})
            d['n'] += 1
            d['sum'] += gap
            d['late25'] += gap > 25
            d['late50'] += gap > 50
            if gap > d['worst']:
                d['worst'], d['worst_blank'] = gap, int(f[6])
        last = t
    for level, d in per.items():
        rows.append('%-10s %6d frames %5.1f a second  >25 ms %4d  >50 ms %3d  worst %6.1f ms at blank %d' % (
            level, d['n'], 1000.0 * d['n'] / max(d['sum'], 1), d['late25'], d['late50'], d['worst'], d['worst_blank']))
    return rows


def hub_mission(r, rows_down=0):
    """In the hub: Firiona's offer (the first time), the mission portal (the PushTrigger at the ring), the mission
    menu: `rows_down` presses of right (the next mission on the menu's line), accept; then the level's arrival."""
    if r.level() != 'hub':
        return False
    p = r.player()
    if not r.state.get('firiona_done'):
        r.goto(122, -40, radius=15)
        r.tap('square', 10, 60)
        r.shot('firiona')
        r.answer(60)
        r.state['firiona_done'] = True
        r.save()
    r.goto(60, 300, radius=25)
    r.tap('square', 10, 90)
    r.shot('mission-menu')
    for _ in range(rows_down):
        r.tap('right', 6, 40)
        r.shot('mission-menu-next')
    level = r.level()
    r.tap('cross', 8, 60)
    for _ in range(60):
        if r.level() != level or r.u32(G_PENDING) & 0xff:
            break
        time.sleep(0.5)
    time.sleep(3)
    return r.arrive()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'launch':
        parser = argparse.ArgumentParser()
        parser.add_argument('cmd')
        parser.add_argument('kind', choices=('godot', 'native', 'emu'))
        parser.add_argument('run')
        parser.add_argument('--portal', action='store_true')
        parser.add_argument('--port', type=int, default=0)
        parser.add_argument('--audio', action='store_true')
        parser.add_argument('--nice', type=int, default=10)
        parser.add_argument('--godot-out', default=os.path.join(ROOT, 'local', 'godot-play-classic'))
        parser.add_argument('--program', default=os.path.join(ROOT, 'local', 'recomp-out', 'bin', 'rta_app_playc'))
        parser.add_argument('extra', nargs='*')
        return launch(parser.parse_args())
    if len(sys.argv) > 2 and sys.argv[1] == 'frames':
        print('\n'.join(frame_report(sys.argv[2])))
        return 0
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    r = Run(sys.argv[1])
    what, rest = sys.argv[2], sys.argv[3:]
    parser = argparse.ArgumentParser()
    parser.add_argument('pos', nargs='*')
    parser.add_argument('--radius', type=float, default=0)
    parser.add_argument('--timeout', type=float, default=0)
    parser.add_argument('--near', type=float, default=0)
    parser.add_argument('--cls', default='')
    parser.add_argument('--hold', type=int, default=10)
    a = parser.parse_args(rest)
    r.log('> %s %s' % (what, ' '.join(rest)))
    try:
        if what == 'status':
            p = r.player()
            print(json.dumps({'level': r.level(), 'blanks': r.port.blanks(), 'sim': r.u32(G_SIM_FRAME), 'paused': r.paused(),
                              'camera_follows': r.camera_follows(), 'pending': r.text(G_PENDING), **p}, default=str))
        elif what == 'objs':
            me = r.pos() or (0, 0, 0)
            for o in sorted(r.objects(), key=lambda o: math.hypot(o['x'] - me[0], o['y'] - me[1])):
                d = math.hypot(o['x'] - me[0], o['y'] - me[1])
                if (a.near and d > a.near) or (a.cls and a.cls.lower() not in o['cls'].lower()):
                    continue
                print('%08x %-20s (%8.0f %8.0f %6.0f) %6.0f away flags %08x%s' % (
                    o['addr'], o['cls'], o['x'], o['y'], o['z'], d, o['flags'], ' hp %.0f/%.0f' % (o['hp'], o['hp_max']) if 'hp' in o else ''))
        elif what == 'exits':
            me = r.pos() or (0, 0, 0)
            for o in r.exits():
                print('%-12s (%7.0f %7.0f %5.0f) %6.0f away -> %s%s' % (o['cls'], o['x'], o['y'], o['z'], math.hypot(o['x'] - me[0], o['y'] - me[1]),
                                                                ','.join(o['dest']), ' (key)' if o.get('key') else ''))
        elif what == 'shot':
            print(r.shot(a.pos[0] if a.pos else 'look'))
            print(json.dumps(r.state.get('last_picture')))
        elif what == 'newgame':
            new_game(r, int(a.pos[0]) if a.pos else 0, int(a.pos[1]) if len(a.pos) > 1 else 0)
        elif what == 'goto':
            print(r.goto(float(a.pos[0]), float(a.pos[1]), radius=a.radius or 40, timeout=a.timeout or 60))
        elif what == 'fight':
            print(r.fight(radius=a.radius or 300, timeout=a.timeout or 60))
        elif what == 'loot':
            print(r.loot(radius=a.radius or 600, timeout=a.timeout or 90))
        elif what == 'use':
            r.tap('square', a.hold, 40)
            time.sleep(0.5)
            r.shot('use')
        elif what == 'answer':
            print(r.answer(int(a.pos[0]) if a.pos else 40))
        elif what == 'exit':
            result = r.take_exit(a.pos[0] if a.pos else None, timeout=a.timeout or 120)
            print(result)
            if result == 'level':
                r.arrive()
        elif what == 'mission':
            print(hub_mission(r, int(a.pos[0]) if a.pos else 0))
        elif what == 'play':
            print(r.play(timeout=a.timeout or 600, radius=a.radius or 500))
        elif what == 'levelup':
            print(r.level_up())
        elif what == 'arrive':
            r.arrive()
        elif what == 'clear':
            t = a.timeout or 300
            start = time.time()
            while time.time() - start < t:
                if r.fight(radius=a.radius or 900, timeout=60) == 'dead':
                    break
                r.loot(radius=a.radius or 900, timeout=60)
                foes = r.creatures()
                if not foes or foes[0]['d'] > (a.radius or 900):
                    break
            r.shot('cleared')
        elif what == 'tap':
            r.tap(a.pos[0], int(a.pos[1]) if len(a.pos) > 1 else 6, int(a.pos[2]) if len(a.pos) > 2 else 20)
        elif what == 'hold':
            r.pad(a.pos[0].split('+'))
            time.sleep(int(a.pos[1]) / 60.0)
            r.pad()
        elif what == 'stick':
            r.pad((), int(a.pos[0]), int(a.pos[1]))
            time.sleep(int(a.pos[2]) / 60.0)
            r.pad()
        elif what == 'put':
            x, y = float(a.pos[0]), float(a.pos[1])
            z = float(a.pos[2]) if len(a.pos) > 2 else r.pos()[2]
            obj = r.u32(PLAYER_OBJ)
            r.log('TELEPORT in %s from %s to (%.0f, %.0f, %.0f)' % (r.level(), r.pos(), x, y, z))
            for _ in range(4):
                r.port.write(obj + OBJ_POS, struct.pack('<3f', x, y, z))
                cam = r.u32(G_CAMERA)
                if cam:
                    r.port.write(cam + 0x16D, b'\x05')
                time.sleep(0.08)
        elif what == 'app':
            r.port.app(' '.join(a.pos))
        elif what == 'raw':
            print(r.port.cmd(' '.join(a.pos)))
        elif what == 'quit':
            try:
                r.port.cmd('quit')
            except Exception:
                pass
        else:
            print(__doc__)
            return 2
    finally:
        try:
            r.port.close()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
