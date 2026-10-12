#!/usr/bin/env python3
"""Takes the game's camera over every level, offline, so that the level textures get dumped.

    tools/play-net/leveltour.py --disc IMAGE --out DIR [--instances 3] [LEVEL...]
    tools/play-net/leveltour.py --out DIR --merge DUMP_DIR

A level's textures (one per piece of ground and wall, 132,280 pictures in 111 levels) can
only be named by the application when they are drawn (tools/play-net/README.md, "Upscaled
art"). This starts the playable build with `--rta-texture-dump` - as a background test
window (`--rta-test`), without network, without the frame limiter, at resolution factor
1 - makes a character, and for each level:

- asks for the level as the game's own level changes do (the name written to
  `g_pendingLevel`); a notice box that holds the game is answered with the confirm button;
- reads from the level's `.world` on the disc where its chunks are, and stops once over
  every square of 345 units that holds any;
- puts the game's own free camera (camera mode 3, which stays where its position is
  written) above each stop as the following camera would be, a little further away, and
  holds it until the application has written no new picture for 40 frames. The character
  stays at the level's start, so no trigger, dialog or way out of the level is touched.

With `--instances N` that many applications share the levels, each with its own folder
`DIR/texN/dump`; `DIR/done-N.jsonl` keeps what each level gave (a level that is done is
not done again: the command can be stopped and started again), `DIR/levels/<level>.txt`
the names of the pictures first seen in it. `--merge DUMP_DIR` then puts all of it into a
pack's dump folder for `upscale.py` (`.json` files of pictures that are there already are
joined: every way of drawing, the largest rectangles).

The application is `play.sh` beside this file (RTA_PLAY_APP names another build).
Everything written is the game's art: keep DIR out of any repository. Needs Python 3
with numpy and Pillow (for disctex.py's reading of the disc image).
"""
import argparse
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ctl import Control  # noqa: E402
from disctex import Iso, gob_entries, lmp_entries  # noqa: E402

# addresses in SLUS-20973 v2.00 (names.tsv, docs/mainloop.md, docs/spec/movement-camera.md)
G_IN_FRONTEND, G_LEVEL_NAME, G_PENDING_LEVEL, G_SIM_FRAME = 0x41B510, 0x41B721, 0x41B6D0, 0x44FDCC
G_PLAYER_OBJECT = 0x4D8AF0 + 0x43D8       # slot 0's object, 0 while there is none
G_CAMERA = '[0x4f8450]'                   # the camera object: mode +0x34, yaw and pitch +0x68
G_CAMERA_POSITION = 0x44F038              # three floats; in mode 3 the camera stays where they say
CAMERA_OFFSET = (98.48, -98.48, 370.17)   # camera minus character with the following camera at a level's start
CAMERA_ANGLES = 0x2EFBE000                # its yaw (low half) and pitch then
CAMERA_FURTHER = 1.3                      # the tour's camera is this much further from the place
SQUARE = 345.0                            # a stop per square of this size (checked: 165 finds 3 more pictures of 1,787)
# the order of the game's level table; levels it does not list follow
ORDER = ('hub hub2 blood1 strife drunarm drundar drunare blomedal compblo boar1 innovat1 inmine1 inmine2 innovat2 innmedal pvpinn '
         'innpit islc1 islc2 islsm1 islsm2a islsm2b islsm3a islsm3b islgnome islgoth wat1 watg2a watg2b watg2c wate2a wate2b wate2c '
         'watmedal compwat watbonus tormenta tormentb torment2 torment3 tormedal pvptor torbonus swamp1 swamp2 dis2 arachna1 dismedal '
         'compdis disbonus valor valor2 honor valmedal compval honor2 fire1 fire2 fire3 fire4 fire5 firmedal pvpfire firbonus storm1 '
         'storm1a storm1b storm1c storm2 storm3 storm4 storm5 stomedal pvpbas stobonus fay1 fay2 fay3 faybonus nit1 nitdung1 nitdung2 '
         'nit2 nitdung4 nitmedal pvpnit nitbonus nitbon2 bossevil bossgood').split()


# ---- what the disc says about a level -----------------------------------------------------

class Disc:
    def __init__(self, path):
        self.iso = Iso(path)
        self.files = {os.path.basename(p).upper(): r for p, r in self.iso.walk()}

    def levels(self):
        """Levels that have both a .GOB and a .TEX, in the game's order."""
        have = sorted(n[:-4].lower() for n in self.files if n.endswith('.TEX') and n[:-4] + '.GOB' in self.files)
        return [n for n in ORDER if n in have] + [n for n in have if n not in ORDER]

    def pictures(self, level):
        """Textures of <LEVEL>.TEX that are pictures (larger than the flat tile of 12 x 12)."""
        record = self.files[level.upper() + '.TEX']
        base = record['lba'] * 2048
        self.iso.file.seek(base)
        head = self.iso.file.read(0x5000)
        count, o = 0, 4
        while o + 12 <= len(head):
            cell, offset, size = struct.unpack_from('<iII', head, o)
            if cell < 0:
                break
            o += 12
            self.iso.file.seek(base + offset)
            n, = struct.unpack('<I', self.iso.file.read(4))
            self.iso.file.seek(base + offset + 0x40)
            headers = self.iso.file.read(0x40 * n)
            for i in range(n):
                width, height = struct.unpack_from('<HH', headers, i * 0x40)
                count += 1 if width * height > 144 else 0
        return count

    def stops(self, level):
        """(x, y, height) to look at: one for every square that holds a chunk of the level's
        .world (docs/formats/world.md: records of 0x3c bytes, bounds at +8, texture cell at
        +0x34, flags at +0x24), at the height of the upper chunks there, in rows there and back."""
        for _, lump in gob_entries(self.iso.read(self.files[level.upper() + '.GOB'])):
            for entry, data in lmp_entries(lump):
                if entry.lower().endswith('.world'):
                    count, = struct.unpack_from('<I', data, 0)
                    at, = struct.unpack_from('<I', data, 0x24)
                    squares = {}
                    for i in range(count):
                        x0, y0, z0, x1, y1, z1 = struct.unpack_from('<6f', data, at + i * 0x3c + 8)
                        flags, = struct.unpack_from('<I', data, at + i * 0x3c + 0x24)
                        cell, = struct.unpack_from('<h', data, at + i * 0x3c + 0x34)
                        if cell != 0 or flags & 0x4880:          # geometry; water, models, emitters
                            squares.setdefault((round((x0 + x1) / 2 / SQUARE), round((y0 + y1) / 2 / SQUARE)), []).append(z1)
                    out = []
                    for (gx, gy), tops in sorted(squares.items(), key=lambda s: (s[0][1], s[0][0] if s[0][1] % 2 == 0 else -s[0][0])):
                        out.append((gx * SQUARE, gy * SQUARE, sorted(tops)[len(tops) * 3 // 4]))
                    return out
        raise SystemExit('leveltour.py: no .world in the lumps of ' + level)


# ---- one running application ----------------------------------------------------------------

class Instance:
    def __init__(self, out, number, disc_path):
        self.textures = os.path.join(out, 'tex%d' % number)
        socket_path = os.path.join(out, 't%d.sock' % number)
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        command = [os.path.join(HERE, 'play.sh'), '--disc', disc_path, '--data', os.path.join(out, 'data', 'p%d' % number), '--sections', 'none',
                   '--', '--rta-control', socket_path, '--rta-test', 'art tour', '--rta-no-net', '--rta-no-online',
                   '--rta-textures', self.textures, '--rta-texture-dump']
        self.process = subprocess.Popen(command, stdout=open(os.path.join(out, 't%d.out' % number), 'w'), stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.time() + 90
        while not os.path.exists(socket_path):
            if self.process.poll() is not None or time.time() > deadline:
                raise SystemExit('leveltour.py: the application did not start; see ' + os.path.join(out, 't%d.out' % number))
            time.sleep(0.2)
        self.control = Control(socket_path, timeout=900)
        self.ok('throttle 0')
        self.ok('pref int renderer.opengl.resfactor 1')

    def ok(self, command):
        return self.control.ok(command)

    def tap(self, buttons, hold=8, after=30):
        self.ok('tap %s %d %d' % (buttons, hold, after))

    def peek(self, address, kind='u32'):
        return self.ok('peek %s %s' % (address if isinstance(address, str) else '0x%x' % address, kind))

    def poke(self, address, value, kind='u32'):
        self.ok('poke %s %s %s' % (address if isinstance(address, str) else '0x%x' % address, kind, value))

    def poke_float(self, address, value):
        self.poke(address, '0x%08x' % struct.unpack('<I', struct.pack('<f', value))[0])

    def dumped(self):
        return int(re.search(r'textures_dumped=(\d+)', self.ok('info')).group(1))

    def level(self):
        return self.peek(G_LEVEL_NAME, 'str8')

    def quit(self):
        try:
            self.control.send('quit')
        except (OSError, SystemExit):
            pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def to_first_level(self):
        """Power-on, the title, a new mission game, the first class as it is, into `hub`."""
        self.ok('wait 120')
        for _ in range(80):
            if self.peek(G_IN_FRONTEND, 'u8') == '1' and self.level() == 'intro':
                break
            self.tap('cross', 6, 40)
        else:
            raise SystemExit('leveltour.py: the front end did not come up')
        self.ok('wait 420')
        for after in (90, 90, 90, 90, 200, 120, 120):   # new game, normal, one player, mission game, difficulty, class, appearance
            self.tap('cross', 8, after)
        for _ in range(20):
            self.tap('right', 4, 6)
        self.ok('wait 20')
        self.tap('cross', 8, 120)
        for button, times in (('cross', 3), ('down', 6), ('right', 5)):      # a name, and "done"
            for _ in range(times):
                self.tap(button, 4, 8)
        self.tap('cross', 8, 60)
        for _ in range(120):
            if self.level() == 'hub':
                break
            self.ok('wait 30')
        else:
            raise SystemExit('leveltour.py: the first level was not reached')
        self.ok('wait 300')

    def enter(self, level, timeout=3600):
        self.poke(G_PENDING_LEVEL, level, 'str')
        waited = 0
        while waited < timeout:
            self.ok('wait 30')
            waited += 30
            if self.level() == level and self.peek(G_PENDING_LEVEL, 'u8') == '0' and self.peek(G_PLAYER_OBJECT) != '0':
                if int(self.peek(G_SIM_FRAME)) > 20:
                    self.ok('wait 90')
                    return True
                if waited >= 240:                       # a notice box holds the game: "OK"
                    self.tap('cross', 6, 30)
        return False

    def running(self, level, most=2400):
        """Waits until the level runs (a character there, its clock going) and answers a
        notice box that holds it; some levels begin again by themselves every ten seconds
        when entered this way. The level's clock then, or None."""
        waited, last = 0, -1
        while waited < most:
            if self.level() == level and self.peek(G_PLAYER_OBJECT) != '0':
                clock = int(self.peek(G_SIM_FRAME))
                if clock > 20 and last >= 0 and clock != last:
                    return clock
                if clock == last and waited >= 240:
                    self.tap('cross', 6, 20)
                last = clock
            self.ok('wait 10')
            waited += 10
        return None

    def look_at(self, x, y, height, least=50, quiet_for=40, most=260):
        if self.peek(G_CAMERA + '+0x34') != '3':
            self.poke(G_CAMERA + '+0x34', 3)
            self.poke(G_CAMERA + '+0x68', '0x%08x' % CAMERA_ANGLES)
        self.poke_float(G_CAMERA_POSITION, x + CAMERA_OFFSET[0] * CAMERA_FURTHER)
        self.poke_float(G_CAMERA_POSITION + 4, y + CAMERA_OFFSET[1] * CAMERA_FURTHER)
        self.poke_float(G_CAMERA_POSITION + 8, height + 60.0 + (CAMERA_OFFSET[2] - 60.0) * CAMERA_FURTHER)
        frames = quiet = 0
        last = self.dumped()
        while frames < most and not (frames >= least and quiet >= quiet_for):
            self.ok('wait 9')
            now = self.dumped()
            frames += 10
            quiet = quiet + 10 if now == last else 0
            last = now

    def tour(self, disc, level, out):
        """What the level gave, or None when the game would not enter it or stood still."""
        started = time.time()
        if not self.enter(level):
            return None
        before = set(n for n in os.listdir(os.path.join(self.textures, 'dump')) if n.endswith('.png'))
        stops = disc.stops(level)
        for x, y, top in stops:
            for attempt in range(4):
                clock = self.running(level)
                if clock is None:
                    return None
                self.look_at(x, y, top + 4.0)
                if int(self.peek(G_SIM_FRAME)) > clock and self.peek(G_PLAYER_OBJECT) != '0':
                    break                               # (else the level began again meanwhile: this stop once more)
            else:
                return None                             # it does not keep running
        self.poke(G_CAMERA + '+0x34', 1)
        new = sorted(set(n for n in os.listdir(os.path.join(self.textures, 'dump')) if n.endswith('.png')) - before)
        os.makedirs(os.path.join(out, 'levels'), exist_ok=True)
        with open(os.path.join(out, 'levels', level + '.txt'), 'a') as file:
            file.write(''.join(n + '\n' for n in new))
        return dict(level=level, stops=len(stops), new=len(new), pictures_in_file=disc.pictures(level), seconds=round(time.time() - started))


# ---- the levels, shared among the instances -------------------------------------------------

def done_levels(out):
    done = set()
    for name in os.listdir(out):
        if re.fullmatch(r'done-\d+\.jsonl', name):
            with open(os.path.join(out, name)) as file:
                done |= set(json.loads(line)['level'] for line in file if line.strip())
    return done


def work(out, disc_path, number, count, wanted):
    disc = Disc(disc_path)
    mine = [level for i, level in enumerate(wanted or disc.levels()) if i % count == (number - 1) % count]
    instance, since, failures = None, 0, {}
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))    # ended from outside: the application is quit below
    while True:
        todo = [level for level in mine if level not in done_levels(out) and failures.get(level, 0) < 2]
        if not todo:
            break
        level = todo[0]
        try:
            if instance is None or since >= 12:         # a new application now and then: its memory grows
                if instance is not None:
                    instance.quit()
                instance, since = Instance(out, number, disc_path), 0
                instance.to_first_level()
            result = instance.tour(disc, level, out)
            since += 1
            if result is None:
                raise ValueError('not entered, or the game stood still')
            print('[%d %s] %s' % (number, time.strftime('%H:%M:%S'), json.dumps(result)), flush=True)
            with open(os.path.join(out, 'done-%d.jsonl' % number), 'a') as file:
                file.write(json.dumps(result) + '\n')
        except (KeyboardInterrupt, SystemExit) as error:
            if instance is not None and not str(error).startswith('leveltour.py') and 'control socket' not in str(error):
                instance.quit()                         # stopped by somebody: leave nothing running
                raise
            failures[level] = failures.get(level, 0) + 1
            print('[%d %s] %s: %s' % (number, time.strftime('%H:%M:%S'), level, error), flush=True)
            if instance is not None:
                instance.quit()
            instance = None
        except (OSError, ValueError, KeyError) as error:
            failures[level] = failures.get(level, 0) + 1
            print('[%d %s] %s: %s; %s' % (number, time.strftime('%H:%M:%S'), level, error, 'again with a new application' if failures[level] < 2 else 'given up'), flush=True)
            if instance is not None:
                instance.quit()
            instance = None
    if instance is not None:
        instance.quit()


def merge(out, target):
    new = joined = 0
    os.makedirs(target, exist_ok=True)
    for directory in sorted(os.listdir(out)):
        source = os.path.join(out, directory, 'dump')
        if not re.fullmatch(r'tex\d+', directory) or not os.path.isdir(source):
            continue
        for name in sorted(os.listdir(source)):
            meta_name = name[:-4] + '.json'
            if not name.endswith('.png') or name.startswith('mem-') or not os.path.exists(os.path.join(source, meta_name)):
                continue
            try:
                with open(os.path.join(source, meta_name)) as file:
                    seen = json.load(file)
            except ValueError:
                continue
            if not os.path.exists(os.path.join(target, name)):
                if time.time() - os.path.getmtime(os.path.join(source, name)) < 20:
                    continue                            # perhaps still being written
                shutil.copyfile(os.path.join(source, name), os.path.join(target, name + '.part'))
                os.replace(os.path.join(target, name + '.part'), os.path.join(target, name))
                new += 1
            old = {}
            if os.path.exists(os.path.join(target, meta_name)):
                try:
                    with open(os.path.join(target, meta_name)) as file:
                        old = json.load(file)
                except ValueError:
                    old = {}
            if old.get('source') or not old.get('states'):
                result = seen                           # read from the disc, or nothing: what was seen counts
            else:
                result = dict(old)
                states = list(old['states']) + [state for state in seen.get('states', []) if state not in old['states']]
                if len(states) > 16 or seen.get('states_overflow'):
                    result['states_overflow'] = True
                result['states'] = states[:16]
                for field in ('sprite_uv', 'field0_uv', 'field1_uv', 'other_uv'):
                    a, b = old.get(field), seen.get(field)
                    if a and b:
                        result[field] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    elif b:
                        result[field] = b
            if result != old:
                with open(os.path.join(target, meta_name), 'w') as file:
                    json.dump(result, file, separators=(',', ':'))
                joined += 1
    print('leveltour.py: %d new pictures, %d .json files written, into %s' % (new, joined, target))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('levels', nargs='*', help='only these levels (default: every level of the disc)')
    parser.add_argument('--disc', default=os.environ.get('RTA_DISC'))
    parser.add_argument('--out', required=True, help='folder for the instances\' data, dumps and lists')
    parser.add_argument('--instances', type=int, default=3)
    parser.add_argument('--merge', metavar='DUMP_DIR', help='put what the instances dumped into this dump folder, and stop')
    parser.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    if args.merge:
        return merge(out, args.merge)
    if not args.disc:
        parser.error('give --disc IMAGE or set RTA_DISC')
    if args.worker:
        return work(out, args.disc, args.worker, args.instances, args.levels)
    workers = [subprocess.Popen([sys.executable, os.path.abspath(__file__), '--disc', args.disc, '--out', out, '--instances', str(args.instances),
                                 '--worker', str(n + 1)] + args.levels) for n in range(args.instances)]
    try:
        for worker in workers:
            worker.wait()
    except KeyboardInterrupt:                           # the workers get it too and quit their applications
        pass
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
            worker.wait()
    print('leveltour.py: %d levels done; then: leveltour.py --out %s --merge DUMP_DIR' % (len(done_levels(out)), args.out))


if __name__ == '__main__':
    sys.exit(main())
