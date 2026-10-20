#!/usr/bin/env python3
"""tour.py - walks the native application, or the emulator build, through levels and
screens over their control sockets (the same protocol: tools/recomp/app/control.h,
tools/play-net/ctl.py) and takes a picture at every stop, so that the two builds can be
laid side by side stop for stop.

  tour.py native|emu levels NAME [NAME ...] --out DIR [--views N] [--paced] [--size WxH]
  tour.py native|emu screens --out DIR
  tour.py sheet OUT.png DIR_A DIR_B [--width W] [--cols N] [--only PREFIX]
  tour.py native fpwalk NAME [NAME ...] --out DIR [--points N] [--size WxH]
  tour.py fpreport DIR [DIR ...]

`levels`: from power-on to the first level, then every named level is asked for the way
the game's own level changes ask (the name written to g_pendingLevel 0x41b6d0); a picture
where the level starts, then N more with the game's free camera (camera mode 3) above
places spread over the level's chunks (read from the level's .world on the disc, the way
local/play-out/tourplan.py does, when that helper is there).  A line of figures per level:
memory, textures held, pictures a second, what the GS model approximated.
`screens`: the first level's pause menu, the bag's pages, the automap, a dialogue.
`sheet`: pictures of the same name from two directories, one above the other.
`fpwalk`: every named level in first person at eye height: where the level starts and N more
places the character walks to from there (the stick, the game's own movement and collision),
at each a turn through eight headings (the look controls, as a mouse turns them), one look 40 degrees up and
one 40 down, small pictures; the pitch is held at exactly those angles (a swing's tilt toward a target
does not move it).  Every look is taken twice, the second time with the level's clear colour
(g_backgroundColor) swapped for one far from it for three blanks: a pixel that takes the swapped colour
is one nothing was drawn on (coverage, not brightness: a black floor of a night level is a floor).
`hole` = such pixels in the lower third of a level look or anywhere in the look down (no ground
there), `open` = such pixels above in a level the ceilings are made for, `void` = more than half of a
level look's lower half is undrawn (floor and walls gone), `inside` = the picture is one flat colour (the eye inside
something).  At every place the game's own overhead view is taken the same way: where it too has
nothing drawn round the character, the flags of that place are the game's (`game`), not the view's.
A place where a scene, a dialogue or a film keeps the game's camera on the frame is not judged (`held`).
One line per level in <out>/fpwalk.tsv: ok, game (every flag is also in the overhead picture), fault, or
held (no place had the first-person view).
`fpreport`: the levels of those files, by fault.

Pictures and logs are game output: DIR must be under local/.  Test windows are titled
"AGENT TEST - ...", small, behind the others, silent.  Standard library (and PIL for
`sheet`).
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'play-net'))

G_IN_FRONTEND, G_LEVEL_NAME, G_PENDING, G_PLAYERS = 0x41B510, 0x41B721, 0x41B6D0, 0x4D8AF0
G_CAMERA, G_INVULNERABLE, G_SIM_FRAME, G_PAUSED = 0x4F8450, 0x44F20C, 0x44FDCC, 0x41B4F4
G_CAM_POS = 0x44F038
CAM_OFFSET = (98.48, -98.48, 370.17)      # camera minus character at the middle zoom, as a level starts
CAM_ANGLES = 0x2EFBE000                   # the camera's yaw (low half) and pitch then
PLAYER = '[0x%x]' % (G_PLAYERS + 0x43D8)


def f2u(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class Instance:
    """One running build and its control socket."""

    def __init__(self, kind, out, disc, paced=False, size='640x448', label=None, extra=()):
        from ctl import Control
        self.kind = kind
        self.out = os.path.abspath(out)
        os.makedirs(self.out, exist_ok=True)
        self.socket_path = '/tmp/rta-tour-%s-%d.sock' % (kind, os.getpid())
        data = os.path.join(self.out, 'data-%s-%d' % (kind, os.getpid()))
        self.data = data
        log = open(os.path.join(self.out, kind + '.out'), 'a')
        if kind == 'native':
            # RTA_TOUR_APP: another build of the window program (a candidate that is being checked)
            command = [os.environ.get('RTA_TOUR_APP', os.path.join(ROOT, 'local', 'recomp-out', 'bin', 'rta_app')), '--disc', disc, '--data', data,
                       '--test', label or 'native app tour', '--window', '320x240', '--size', size, '--control', self.socket_path]
            command += [] if paced else ['--unpaced']
            command += os.environ.get('RTA_TOUR_ARGS', '').split()      # more options for rta_app, e.g. --plain
            command += list(extra)
        else:
            os.makedirs(data)
            command = [os.path.join(ROOT, 'tools', 'play-net', 'play.sh'), '--disc', disc, '--data', data, '--sections', 'none', '--',
                       '--rta-test', label or 'reference pictures for the native app - silent, no network', '--rta-no-net',
                       '--rta-control', self.socket_path]
        self.process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        for _ in range(900):
            if os.path.exists(self.socket_path) or self.process.poll() is not None:
                break
            time.sleep(0.1)
        if not os.path.exists(self.socket_path):
            raise SystemExit('tour: the %s build did not open its control socket (see %s/%s.out)' % (kind, self.out, kind))
        self.c = Control(self.socket_path, timeout=900)
        if kind == 'emu' and not paced:
            self.c.send('throttle 0')

    def ok(self, command):
        return self.c.ok(command)

    def tap(self, buttons, hold=8, after=30):
        self.c.ok('tap %s %d %d' % (buttons, hold, after))

    def wait(self, frames):
        self.c.ok('wait %d' % frames)

    def peek(self, address, kind='u32'):
        return self.c.ok('peek %s %s' % (address if isinstance(address, str) else '0x%x' % address, kind))

    def poke(self, address, kind, value):
        self.c.ok('poke %s %s %s' % (address if isinstance(address, str) else '0x%x' % address, kind, value))

    def pokef(self, address, value):
        self.poke(address, 'u32', '0x%08x' % f2u(value))

    def info(self):
        fields = dict(re.findall(r'(\w+)=(\S+)', self.c.ok('info')))
        out = {}
        for k, v in fields.items():
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
        return out

    def level(self):
        return self.peek(G_LEVEL_NAME, 'str8')

    def shot(self, name):
        """The picture as the machine drew it, as <out>/<name>.png (the emulator writes a
        .bmp, at twice the width for its height: both are brought to 4:3 by `sheet`)."""
        if self.kind == 'native':
            self.c.ok('shotfb ' + os.path.join(self.out, name + '.png'))
        else:
            self.c.ok('shotfb ' + os.path.join(self.out, name + '.bmp'))

    def quit(self):
        try:
            self.c.send('quit')
        except (OSError, SystemExit):
            pass
        if self.kind == 'emu':
            with open(self.socket_path + '.ui', 'w') as handle:
                handle.write('close\n')
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate()
        for leftover in (self.socket_path, self.socket_path + '.ui'):
            if os.path.exists(leftover):
                os.remove(leftover)

    # ---- stages (the route of the emulator tours, local/play-out/arttour.py) ----
    def to_hub(self):
        self.wait(120)
        for _ in range(120):
            if self.peek(G_IN_FRONTEND, 'u8') == '1' and self.level() == 'intro':
                break
            self.tap('cross', 6, 40)
        else:
            raise SystemExit('the front end did not come up')
        self.wait(420)
        for after in (90, 90, 90, 90, 200):        # new game, normal, one player, mission game, difficulty
            self.tap('cross', 8, after)
        self.tap('cross', 8, 120)                   # class
        self.tap('cross', 8, 120)                   # appearance
        for _ in range(20):
            self.tap('right', 4, 6)
        self.wait(20)
        self.tap('cross', 8, 120)
        for _ in range(3):
            self.tap('cross', 4, 8)
        for _ in range(6):
            self.tap('down', 4, 8)
        for _ in range(5):
            self.tap('right', 4, 8)
        self.tap('cross', 8, 60)
        for _ in range(240):
            if self.level() == 'hub' and self.peek(G_PLAYERS + 0x43D8) != '0':
                break
            self.wait(30)
        else:
            raise SystemExit('the first level was not reached')
        self.wait(300)

    def enter(self, name, timeout=3600):
        """Asks for a level as the game's own level changes do and waits until it runs."""
        if self.level() != name or self.peek(G_PLAYERS + 0x43D8) == '0':
            self.poke(G_PENDING, 'str', name)
            waited = 0
            while waited < timeout:
                self.wait(30)
                waited += 30
                if self.level() == name and self.peek(G_PENDING, 'u8') == '0' and self.peek(G_PLAYERS + 0x43D8) != '0':
                    if int(self.peek(G_SIM_FRAME)) > 20:
                        break
                    if waited >= 240:                       # a notice box holds the game: "OK"
                        self.tap('cross', 6, 30)
            else:
                return False
            self.wait(90)
        self.poke(G_INVULNERABLE, 'u32', 1)
        return True

    def free_camera(self):
        """A dialogue or a cutscene has the camera: answers and skips until it follows the player again."""
        mode = '[0x%x]+0x34' % G_CAMERA
        if self.peek(mode) == '1':
            return True
        for button in ['cross'] * 30 + ['start', 'cross', 'triangle', 'cross', 'circle', 'cross'] * 4:
            self.tap(button, 4, 12)
            if self.peek(mode) == '1':
                self.wait(20)
                if self.peek(mode) == '1':
                    return True
        return False

    def camera_at(self, x, y, z, scale=1.3):
        """The game's own free camera (mode 3) above a place, as the following camera would be."""
        cam = '[0x%x]' % G_CAMERA
        if self.peek(cam + '+0x34') != '3':
            self.poke(cam + '+0x34', 'u32', 3)
            self.poke(cam + '+0x68', 'u32', '0x%08x' % CAM_ANGLES)
        self.pokef(G_CAM_POS, x + CAM_OFFSET[0] * scale)
        self.pokef(G_CAM_POS + 4, y + CAM_OFFSET[1] * scale)
        self.pokef(G_CAM_POS + 8, z + 60.0 + (CAM_OFFSET[2] - 60.0) * scale)

    def camera_follows(self):
        self.poke('[0x%x]+0x34' % G_CAMERA, 'u32', 1)

    def position(self):
        return struct.unpack('<3f', bytes.fromhex(self.peek(PLAYER + '+0x10', 'hex12')))

    def place(self, x, y, z):
        self.pokef(PLAYER + '+0x10', x)
        self.pokef(PLAYER + '+0x14', y)
        self.pokef(PLAYER + '+0x18', z)
        self.poke('[0x%x]+0x16d' % G_CAMERA, 'u8', 5)        # the camera goes there at once


def plan_of(level):
    """Places spread over a level's chunks, from the helper of the emulator tours when it is there."""
    helper = os.path.join(ROOT, 'local', 'play-out')
    if not os.path.exists(os.path.join(helper, 'tourplan.py')):
        return []
    sys.path.insert(0, helper)
    try:
        import tourplan
        return tourplan.plan(level, 250.0)
    except BaseException as error:                          # a level without a .world, a missing disc
        print('tour: no plan for %s (%s)' % (level, error))
        return []


def figures(m, since=None):
    i = m.info()
    text = 'load %.0f' % os.getloadavg()[0]
    if m.kind == 'native':
        text += ' | memory %.0f MB, textures held %d (%.1f MB), made %d, freed %d, missing %d, copies %d (+%d not carried out)' % (
            i.get('memory_mb', 0), i.get('tex_held', 0), i.get('tex_mb', 0), i.get('tex_made', 0), i.get('tex_freed', 0), i.get('tex_missing', 0),
            i.get('copies', 0), i.get('copies_skipped', 0))
        approx = ' '.join('%s=%d' % (k, v) for k, v in sorted(i.items()) if k.startswith('approx'))
        text += ' | approximated: ' + (approx or 'none')
        text += ' | sound ' + ' '.join('%s=%s' % (k[6:], v) for k, v in sorted(i.items()) if k.startswith('sound_'))
    if since:
        frames = i['frame'] - since['frame']
        ms = i['ms'] - since['ms']
        if ms > 0:
            text += ' | %.0f pictures a second' % (1000.0 * frames / ms)
    return i, text


def run_levels(args):
    m = Instance(args.build, args.out, args.disc, paced=args.paced, size=args.size, extra=args.app_arg)
    log = open(os.path.join(m.out, args.build + '-tour.log'), 'a')

    def say(text):
        line = time.strftime('%H:%M:%S ') + text
        print(line, flush=True)
        log.write(line + '\n')
        log.flush()
    try:
        m.to_hub()
        info, text = figures(m)
        say('first level reached: ' + text)
        for name in args.names:
            before = m.info()
            if not m.enter(name):
                say('%s: not entered' % name)
                continue
            m.free_camera()
            m.poke('[0x%x]+0x54' % G_CAMERA, 'u32', 2)        # the far zoom
            m.wait(60)
            m.shot('%s-0' % name)
            points = plan_of(name)
            if points and args.views:
                step = max(1, len(points) // args.views)
                for k, (x, y, top, low) in enumerate(points[step // 2::step][:args.views]):
                    m.camera_at(x, y, top)
                    m.wait(args.settle)
                    m.shot('%s-%d' % (name, k + 1))
                m.camera_follows()
                m.wait(10)
            info, text = figures(m, before)
            say('%s: %s' % (name, text))
    finally:
        m.quit()


def run_screens(args):
    """The first level's screens: pause menu and its options, the bag's pages, the map, a
    dialogue, the shop's lists (the routes of the emulator tours)."""
    m = Instance(args.build, args.out, args.disc, size=args.size)
    cam_mode = '[0x%x]+0x34' % G_CAMERA
    try:
        m.to_hub()
        m.free_camera()
        m.shot('s00-hub')
        m.tap('start', 6, 60); m.shot('s01-pause')
        for _ in range(3):
            m.tap('down', 6, 20)
        m.tap('cross', 6, 90); m.shot('s02-options')
        for _ in range(3):
            m.tap('circle', 6, 60)
        m.free_camera()
        m.tap('select', 6, 90); m.shot('s03-bag-1')
        for k in range(2, 7):
            m.tap('r1', 6, 60); m.shot('s03-bag-%d' % k)
        m.tap('select', 6, 90)
        m.free_camera()
        m.tap('r3', 6, 60); m.shot('s04-map-1')
        m.tap('r3', 6, 60); m.shot('s04-map-2')
        m.tap('r3', 6, 60)
        # the woman on the platform: what she says, then her shop
        m.place(122, -40, -47)
        m.wait(60)
        m.tap('square', 6, 150); m.shot('s05-dialogue-1')
        for k in range(12):
            m.tap('cross', 6, 100)
            if k == 1:
                m.shot('s05-dialogue-2')
            if m.peek(cam_mode) == '1':
                m.tap('square', 6, 150)
                m.tap('cross', 6, 150)
                break
        m.shot('s05-dialogue-end')
        m.tap('down', 6, 30)
        m.tap('cross', 6, 180); m.shot('s06-shop-menu')
        m.tap('cross', 6, 120); m.shot('s06-shop-buy')
        m.tap('down', 4, 20); m.tap('down', 4, 20); m.tap('right', 4, 30); m.shot('s06-shop-buy-2')
        m.tap('r1', 6, 60); m.shot('s06-shop-buy-tab2')
        for _ in range(4):
            m.tap('circle', 6, 60)
        info, text = figures(m)
        print(text, flush=True)
    finally:
        m.quit()


def run_sheet(args):
    from PIL import Image
    names = sorted(n[:-4] for n in os.listdir(args.a) if n.endswith(('.png', '.bmp')))
    if args.only:
        names = [n for n in names if any(n.startswith(p) for p in args.only.split(','))]

    def load(directory, name):
        for ext in ('.png', '.bmp'):
            path = os.path.join(directory, name + ext)
            if os.path.exists(path):
                return Image.open(path).convert('RGB').resize((args.width, args.width * 3 // 4), Image.LANCZOS)
        return Image.new('RGB', (args.width, args.width * 3 // 4), (60, 0, 60))
    cols = args.cols
    h = args.width * 3 // 4
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * args.width, rows * 2 * h + rows * 4))
    for i, name in enumerate(names):
        x, y = (i % cols) * args.width, (i // cols) * (2 * h + 4)
        sheet.paste(load(args.a, name), (x, y))
        sheet.paste(load(args.b, name), (x, y + h))
    sheet.save(args.sheet)
    print('%s: %s' % (args.sheet, ' '.join(names)))


# ---- first person at eye height, every level ----------------------------------------------------
G_BACKGROUND, G_DOME_LUMP = 0x506044, 0x86AF54
G_CUTSCENE_ACTIVE, G_LOADSCREEN_ACTIVE = 0x44FCD0, 0x506094
FP_HEADINGS = 8
FP_COUNT = 0.12                 # degrees of turn per mouse count of the look controls (app/fpcontrols.h)


def swapped_colour(clear):
    """A clear colour far from the level's own: magenta, or green when the level's is near magenta."""
    return (0, 255, 0) if clear[0] > 128 and clear[2] > 128 and clear[1] < 128 else (255, 0, 255)


def undrawn_mask(path_a, path_b, swap):
    """Which pixels of a picture nothing was drawn on: those that took the swapped clear colour in the
    second picture (a strong move toward it in every channel that differs).  A list of rows of booleans
    at 160 x 90, and picture A at that size."""
    from PIL import Image
    a = Image.open(path_a).convert('RGB').resize((160, 90), Image.NEAREST)
    b = Image.open(path_b).convert('RGB').resize((160, 90), Image.NEAREST)
    w, h = a.size
    pa, pb = list(a.getdata()), list(b.getdata())
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            ca, cb = pa[y * w + x], pb[y * w + x]
            took = True
            for k in range(3):
                d = cb[k] - ca[k]
                want = swap[k] - ca[k]
                if abs(want) > 100 and (d * want < 0 or abs(d) < abs(want) * 0.6):
                    took = False
                    break
                if abs(want) <= 100 and abs(d) > 60:
                    took = False
                    break
            row.append(took)
        out.append(row)
    return out, a


def measure(mask, picture):
    """Fractions of a look: undrawn in the lower third, in the upper half, in all of it (below the
    game's HUD band), in the lower half; and how flat picture A is (the spread of its brightness)."""
    from PIL import ImageStat
    h, w = len(mask), len(mask[0])
    top_hud = h // 7                                         # the game's own HUD sits in the top band

    def frac(rows):
        cells = [v for row in rows for v in row]
        return sum(cells) / max(1, len(cells))
    spread = ImageStat.Stat(picture.convert('L').crop((0, top_hud, w, h))).stddev[0]
    return frac(mask[h * 2 // 3:]), frac(mask[top_hud:h // 2]), frac(mask[top_hud:]), frac(mask[h // 2:]), spread


def overhead_undrawn(mask):
    """The overhead picture: undrawn share of the middle (the ground round the character)."""
    h, w = len(mask), len(mask[0])
    cells = [v for row in mask[h // 4:h * 3 // 4] for v in row[w // 4:w * 3 // 4]]
    return sum(cells) / len(cells)


def shot_pair(m, rel, bg, clear):
    """Picture REL and REL~b with the clear colour swapped; the undrawn mask and picture A."""
    m.shot(rel)
    swap = swapped_colour(clear)
    m.poke(G_BACKGROUND, 'u32', '0x%08x' % ((bg & 0xFF000000) | swap[0] | swap[1] << 8 | swap[2] << 16))
    m.wait(3)
    m.shot(rel + '~b')
    m.poke(G_BACKGROUND, 'u32', '0x%08x' % bg)
    return undrawn_mask(os.path.join(m.out, rel + '.png'), os.path.join(m.out, rel + '~b.png'), swap)


def hold_pitch(m, pitch):
    """The first-person pitch, exactly: the look controls and a swing's tilt cannot move it."""
    for key in ('pitch', 'pitch_min', 'pitch_max'):
        m.c.ok('app view set view.first.%s %d' % (key, pitch))


def run_fpwalk(args):
    done = set()
    table = os.path.join(os.path.abspath(args.out), 'fpwalk.tsv')
    if os.path.exists(table):
        done = {line.split('\t')[0] for line in open(table) if line.strip()}
    names = [n for n in args.names if n not in done]
    while names:
        m = Instance('native', args.out, args.disc, size=args.size, label='first person level walk',
                     extra=['--view', 'first', '--no-settings'] + list(args.app_arg))
        try:
            m.to_hub()
            while names:
                name = names[0]
                row = walk_level(m, name, args)
                with open(table, 'a') as handle:
                    handle.write('\t'.join(str(x) for x in row) + '\n')
                print('\t'.join(str(x) for x in row), flush=True)
                names.pop(0)
                if row[1] in ('not-entered', 'held'):       # whatever held it may hold the next (after an ending's
                    break                                    # scene the next level change hung or crashed the game): a fresh start
        except (OSError, SystemExit, RuntimeError) as error:   # the build stopped or a level hung it: on with the next
            if names:
                name = names.pop(0)
                with open(table, 'a') as handle:
                    handle.write('%s\tstopped\t%s\n' % (name, str(error).replace('\t', ' ')[:200]))
        finally:
            m.quit()


def walk_level(m, name, args):
    pics = os.path.join(m.out, name)
    os.makedirs(pics, exist_ok=True)
    if not m.enter(name, timeout=args.enter_timeout):
        return [name, 'not-entered']
    m.free_camera()
    # what holds the game after a level starts: a menu (the memory card's save question), a film or
    # a flight of the camera over the level, the fade-in.  Answered until the simulation runs with no
    # film or loading screen.
    for _ in range(40):
        tick = int(m.peek(G_SIM_FRAME))
        m.wait(20)
        running = int(m.peek(G_SIM_FRAME)) > tick
        held = m.peek(G_CUTSCENE_ACTIVE) != '0' or m.peek(G_LOADSCREEN_ACTIVE) != '0'
        if running and not held:
            break
        m.tap('cross', 6, 30)
    m.c.ok('app view set view first')
    hold_pitch(m, 0)
    m.wait(args.fade)
    if m.position()[2] < -50000:                             # no place for a character of this game kind (the arenas)
        return [name, 'no-player']
    bg = int(m.peek(G_BACKGROUND))
    clear = (bg & 255, (bg >> 8) & 255, (bg >> 16) & 255)
    dome = m.peek(G_DOME_LUMP) != '0'
    ceiling = world_info(m).get('ceiling', 0) > 0
    cam = '[0x%x]' % G_CAMERA
    counts = {'hole': 0, 'open': 0, 'void': 0, 'inside': 0}
    own = 0                                                  # flags at places where the overhead view has the same gap
    worst = {}
    shots = 0
    interior = ceiling                                       # the level gets the generated ceilings (fpworld: walled, black, no dome)
    uncelled = 0
    for point in range(args.points + 1):
        if point:                                            # walk on from here: the stick up, the camera turned a third
            m.c.ok('app fpc mouse %.1f 0' % (130.0 / FP_COUNT))   # a third of a turn and a bit
            m.wait(4)
            m.c.ok('stick l 128 0')
            m.wait(args.walk)
            m.c.ok('stick l 128 128')
            m.wait(20)
        held = view_held(m)
        if held:                                             # the game's camera has the frame: no first-person pictures to judge
            counts.setdefault('held', 0)
            counts['held'] += 1
            worst.setdefault('held', 'p%d: %s' % (point, held.replace(' ', '_')[:60]))
            continue
        x, y, z = m.position()
        looks = [(360.0 / FP_HEADINGS if k else 0, 0) for k in range(FP_HEADINGS)] + [(360.0 / FP_HEADINGS, 40), (0, -40)]
        here = []
        for k, (turn, pitch) in enumerate(looks):
            if turn:
                m.c.ok('app fpc mouse %.1f 0' % (turn / FP_COUNT))
            hold_pitch(m, pitch)
            m.wait(args.settle)
            tag = 'p%d-%s' % (point, ('h%d' % k) if not pitch else ('up' if pitch > 0 else 'down'))
            mask, picture = shot_pair(m, os.path.join(name, tag), bg, clear)
            shots += 1
            low, high, every, lower, spread = measure(mask, picture)
            uncelled = max(uncelled, world_info(m).get('no_cell', 0))
            faults = []
            if (pitch == 0 and low > 0.03) or (pitch < 0 and every > 0.03):
                faults.append('hole')
            if pitch > 0 and interior and high > 0.25:
                faults.append('open')
            if pitch == 0 and lower > 0.5:                   # most of the ground half gone (an open sky above is not a fault)
                faults.append('void')
            if spread < 6 and pitch <= 0 and every < 0.5:
                faults.append('inside')
            here += [(f, tag) for f in faults]
        game_gap = 0.0
        if here:                                             # the game's own view of this place
            hold_pitch(m, 0)
            m.c.ok('app view set view overhead')
            m.wait(args.settle + 30)
            mask, _ = shot_pair(m, os.path.join(name, 'p%d-overhead' % point), bg, clear)
            game_gap = overhead_undrawn(mask)
            m.c.ok('app view set view first')
            m.wait(args.settle + 30)
        for f, tag in here:
            if game_gap > 0.03 and f in ('hole', 'void'):
                own += 1
                continue
            counts[f] += 1
            if f not in worst:
                worst[f] = '%s@%.0f,%.0f,%.0f' % (tag, x, y, z)
    for key, value in (('pitch', 0), ('pitch_min', -65), ('pitch_max', 65)):
        m.c.ok('app view set view.first.%s %d' % (key, value))
    faults = {f: n for f, n in counts.items() if f != 'held'}
    verdict = 'held' if counts.get('held') == args.points + 1 else 'ok' if not any(faults.values()) and not own else 'game' if not any(faults.values()) else 'fault'
    detail = ' '.join('%s=%d(%s)' % (f, counts[f], worst[f]) for f in counts if counts[f])
    if own:
        detail = (detail + ' ' if detail else '') + 'as-overhead=%d' % own
    return [name, verdict, 'clear=%02x%02x%02x' % clear, ('dome' if dome else 'nodome') + (' ceiling' if ceiling else ''), 'shots=%d' % shots, detail or '-',
            'chunks without their texture cell: %d at most' % uncelled]


def view_state(m):
    """The view of the last frame (`app view info`): (shown view, why the game's camera has it or '')."""
    m.c.ok('app view info')
    m.wait(1)
    path = os.path.join(m.out, 'native.out')
    with open(path, 'rb') as handle:
        handle.seek(max(0, os.path.getsize(path) - 20000))
        lines = [l for l in handle.read().decode('latin-1').splitlines() if '] view: selected' in l]
    if not lines:
        return '', ''
    shown = re.search(r'shown (\w+)', lines[-1])
    why = re.search(r"the game's camera: ([^;]*);", lines[-1])
    return (shown.group(1) if shown else ''), (why.group(1).strip() if why else '')


def view_held(m):
    """Until the first-person view has the frame (a scene, a dialogue or a film can hold the game's
    camera after a level starts or a walk): answered and waited out.  The reason when it never does."""
    why = ''
    for attempt in range(16):
        shown, why = view_state(m)
        if shown == 'first' and not why:
            return ''
        m.tap('cross', 6, 30)
        m.wait(30)
    return why or 'the view never had the frame'


def world_info(m):
    """The figures of `app world info` (printed by the build to its output)."""
    m.c.ok('app world info')
    m.wait(1)
    path = os.path.join(m.out, 'native.out')
    with open(path, 'rb') as handle:
        handle.seek(max(0, os.path.getsize(path) - 20000))
        lines = [l for l in handle.read().decode('latin-1').splitlines() if 'chunks drawn' in l]
    out = {}
    if lines:
        found = re.search(r'(\d+) chunks drawn, (\d+) not \(texture cell', lines[-1])
        if found:
            out['chunks'], out['no_cell'] = int(found.group(1)), int(found.group(2))
        found = re.search(r'fill of \S+: ceiling (\d+)', lines[-1])
        if found:
            out['ceiling'] = int(found.group(1))
    return out


def run_fpreport(args):
    rows = []
    for directory in [args.what] + args.names:
        for line in open(os.path.join(directory, 'fpwalk.tsv')):
            if line.strip():
                rows.append(line.rstrip('\n').split('\t'))
    for row in sorted(rows):
        print(' | '.join(row[:6]))
    verdicts = {}
    for row in rows:
        verdicts[row[1]] = verdicts.get(row[1], 0) + 1
    print(verdicts)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('build', choices=['native', 'emu', 'sheet', 'fpreport'])
    parser.add_argument('what')
    parser.add_argument('names', nargs='*')
    parser.add_argument('--out')
    parser.add_argument('--disc', default=os.environ.get('RTA_DISC', ''))
    parser.add_argument('--views', type=int, default=2)
    parser.add_argument('--settle', type=int, default=50, help='vertical blanks to wait at a view before its picture (the emulator build loads a level\'s cells as slowly as a console)')
    parser.add_argument('--paced', action='store_true')
    parser.add_argument('--size', default='640x448')
    parser.add_argument('--width', type=int, default=320)
    parser.add_argument('--cols', type=int, default=4)
    parser.add_argument('--only')
    parser.add_argument('--points', type=int, default=3, help='fpwalk: places walked to besides the start')
    parser.add_argument('--walk', type=int, default=150, help='fpwalk: vertical blanks of walking between two places')
    parser.add_argument('--enter-timeout', type=int, default=3600)
    parser.add_argument('--fade', type=int, default=300, help='fpwalk: vertical blanks after a level runs before the first picture')
    parser.add_argument('--app-arg', action='append', default=[], help='one more argument for rta_app (repeatable; --app-arg=--opt ...)')
    args = parser.parse_args()
    if args.build == 'fpreport':
        return run_fpreport(args)
    if args.build == 'sheet':
        args.sheet, args.a, args.b = args.what, args.names[0], args.names[1]
        return run_sheet(args)
    if not args.out or os.sep + 'local' + os.sep not in os.path.abspath(args.out) + os.sep:
        raise SystemExit('tour: --out must be a directory under local/')
    if not args.disc:
        raise SystemExit('tour: --disc IMAGE (or RTA_DISC)')
    if args.what == 'levels':
        return run_levels(args)
    if args.what == 'screens':
        return run_screens(args)
    if args.what == 'fpwalk':
        if args.settle == 50:
            args.settle = 12
        return run_fpwalk(args)
    raise SystemExit('tour: levels, screens or fpwalk')


if __name__ == '__main__':
    sys.exit(main())
