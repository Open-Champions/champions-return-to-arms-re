#!/usr/bin/env python3
"""presets.py - per-level look presets for the Godot scene mode (project/scene_view.gd), picked from each level's
own colours, and contact sheets before / after.

  presets.py walk OUT [--levels FILE] [--only A,B] [--jobs N] [--size WxH] [--look K=V,...] [--tag NAME] [--renderer R]
      Godot's scene mode through every level (power-on, then each level asked for by name as the game's own level
      changes ask): at a few fixed ticks after the level starts it writes Godot's own pictures (g: chase standing with all of
      Godot's look off - the game's own colours, a: chase standing, b: after a walk, c: the camera turned, f: first person) and one line
      `rta_look_stats` of what scene_view.gd reads of the level: clear colour, dome, light level, far plane, the
      painted sun, the game's light nodes near the eye.  Each stop is taken twice: with the look of the fifth round
      (TAG-old: no preset, Compatibility's sun rule) and with the Forward+ balance (TAG-base: no preset).  With
      --tag after and no --look, the project's presets (presets/levels.cfg) are in force (one picture a stop).
  presets.py make OUT [--from TAG]
      the presets from the walk: OUT/levels.cfg (under local/: its comments quote the walk's measurements).  The look
      keys themselves are our own numbers: copied without the comments into project/presets/levels.cfg (tracked, so
      every build ships them).  The hand-tuning is tracked too: project/presets/tuning.cfg (read over it).
  presets.py sheets OUT [--before TAG-old] [--after after]
      one contact sheet per level, OUT/sheets/LEVEL.jpg: the stops of the walk before above, after below; and
      OUT/sheets/index.jpg with stop a of every level.
  presets.py stats OUT
      how far the pictures moved: mean brightness and saturation of every stop, before / base / after.

The level list is not in this file (the game's level names are read where the game's data is): --levels FILE, one
name a line (default: OUT/levels.txt, else local/fp-world2/all-levels.txt).  Everything written is game output and
must stay under local/.  At most --jobs (default 2, at most 3) Godot programs, small test windows off the screen,
silent, not paced.  Standard library, and PIL for the pictures.
"""
import argparse
import configparser
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GODOT_OUT = os.path.abspath(os.environ.get('RTA_GODOT_OUT', os.path.join(ROOT, 'local', 'godot-spike')))
DISC = os.environ.get('RTA_DISC', os.path.join(os.path.expanduser('~'), 'Desktop', 'Champions - Return to Arms (v2.00)',
                                               'Champions - Return to Arms (v2.00).iso'))
BOOT = os.path.join(ROOT, 'tools', 'rig', 'examples', 'boot-to-hub.rig')
PLAYER = 0x4D8AF0 + 0x43D8
G_PENDING, G_LEVEL, G_SIM = 0x41B6D0, 0x41B721, 0x44FDCC
G_CUTSCENE, G_LOADSCREEN, G_INVULNERABLE, G_CAMERA = 0x44FCD0, 0x506094, 0x44F20C, 0x4F8450
STOPS = 'gabcf'
T0 = 300                # ticks after a level starts before the first stop (the fade-in, a camera flight)
T0_LEVEL = int(os.environ.get('PRESETS_T0', T0))      # a later first stop, for levels whose opening scene is long


def under_local(path):
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(os.path.join(ROOT, 'local')) + os.sep):
        raise SystemExit('presets.py: %s is not under local/ (what it writes is game output)' % path)
    return real


def level_list(args):
    for path in [args.levels] if args.levels else [os.path.join(args.out, 'levels.txt'), os.path.join(ROOT, 'local', 'fp-world2', 'all-levels.txt')]:
        if path and os.path.exists(path):
            names = [l.strip() for l in open(path) if l.strip() and not l.startswith('#')]
            if args.only:
                names = [n for n in names if n in args.only.split(',')]
            return names
    raise SystemExit('presets.py: no level list (--levels FILE: one level name a line)')


# ---- the walk ------------------------------------------------------------------------------------------------------
def route(levels, pictures, tag, twice):
    """The rig script of one Godot program: power-on, then each level."""
    lines = [l for l in open(BOOT).read().splitlines() if not l.startswith('show ')]
    at = lambda t: 'until 0x%x:u32 >= %d timeout 6000 continue' % (G_SIM, t)

    def stop(letter, name):
        out = []
        base = os.path.join(pictures, '%s-%s' % (name, letter))
        if twice:
            out += ['app look balance off', 'app look saturation 1.10', 'wait 2', 'app shot %s-%s-old.png' % (base, tag),
                    'app look balance on', 'app look saturation 1.22', 'wait 2',
                    'app look stats', 'app shot %s-%s-base.png' % (base, tag)]
        else:
            out += ['app look stats', 'app shot %s-%s.png' % (base, tag)]
        return out

    for index, name in enumerate(levels):
        if name != 'hub' or index > 0:
            lines += ['poke 0x%x:str8 %s' % (G_PENDING, name),
                      'until 0x%x:str8 == %s timeout 3600 continue' % (G_LEVEL, name),
                      'until 0x%x:u32 != 0 timeout 3600 continue' % PLAYER,
                      'until 0x%x:u32 < 20 timeout 3600 continue' % G_SIM, at(21)]
            # what holds the game after a level starts: a film, a loading screen, a scene (answered as tour.py fpwalk does)
            # (the script's tapuntil ends the program when it times out: a bounded loop of waits and taps instead - the taps
            # that fall where nothing holds the game are swings of an invulnerable character)
            for _ in range(40):
                lines += ['until [0x%x]+0x34:u32 == 1 timeout 30 continue' % G_CAMERA, 'tap cross 4']
            # a scene that taps do not end keeps the game's camera on the frame (and, it was seen, through the next level
            # changes): the camera is put back to following the player, as tour.py does after its free camera
            lines += ['poke [0x%x]+0x34:u32 1' % G_CAMERA]
            t0 = T0_LEVEL
        else:
            t0 = 160
        lines += ['echo level %s' % name, 'app view chase', at(t0 - 60), 'poke 0x%x:u32 1' % G_INVULNERABLE, 'poke [0x%x]+0x34:u32 1' % G_CAMERA, at(t0)]
        lines += stop('a', name)
        if twice:
            # g: the same moment with everything of Godot's own look off - the game's own colours (the reference)
            switches = ('sun', 'fog', 'sky', 'grade', 'bloom', 'lights', 'lamp', 'fill')
            lines += ['app look %s off' % k for k in switches] + ['wait 2', 'app shot %s-g-%s-game.png' % (os.path.join(pictures, name), tag)]
            lines += ['app look %s auto' % k for k in switches] + ['wait 2']
        lines += ['pad none 128 0', at(t0 + 90), 'pad none'] + stop('b', name)
        lines += ['pad none 128 128 255 128', at(t0 + 135), 'pad none', at(t0 + 150)] + stop('c', name)
        lines += ['app view first', at(t0 + 190)] + stop('f', name)
        lines += ['app view chase', 'echo toured %s' % name]
    lines += ['wait 20', 'quit']
    return '\n'.join(lines) + '\n'


def walk(args):
    out = under_local(args.out)
    levels = level_list(args)
    pictures = os.path.join(out, 'pictures')
    os.makedirs(pictures, exist_ok=True)
    jobs = max(1, min(args.jobs, 3))
    # chunks of --chunk levels, each a program of its own from power-on (a level that leaves the game's camera holding the
    # frame - a boss's or an ending's scene - then spoils only its own chunk), at most --jobs at a time
    size = args.chunk if args.chunk > 0 else (len(levels) + jobs - 1) // jobs
    parts = [levels[k:k + size] for k in range(0, len(levels), size)]
    twice = args.tag != 'after' or bool(args.look)
    look = args.look or ('preset=off,balance=off' if twice else '')
    env = dict(os.environ)
    env['RTA_GODOT_OUT'] = GODOT_OUT
    env['RTA_TEST_OFFSCREEN'] = '1'
    t0 = time.time()
    waiting = list(enumerate(parts))
    running = []
    while waiting or running:
        while waiting and len(running) < jobs:
            k, part = waiting.pop(0)
            name = '%s-%s%d' % (args.tag, args.run, k)
            rig = os.path.join(out, name + '.rig')
            open(rig, 'w').write(route(part, pictures, args.tag, twice))
            data = os.path.join(out, 'data-' + name)
            shutil.rmtree(data, ignore_errors=True)
            command = [sys.executable, os.path.join(HERE, 'run.py')] + (['--rendering-method', args.renderer] if args.renderer else []) + [
                '--', '--disc', DISC, '--data', data, '--workspace', ROOT, '--mode', 'scene', '--size', args.size, '--aspect', '16:9', '--script', rig,
                '--unpaced', '--mute', '--no-portal', '--test', 'presets ' + name, '--figures', os.path.join(out, name + '-figures.txt')] + (['--look', look] if look else [])
            p = subprocess.Popen(command, env=env, cwd=ROOT, stdout=open(os.path.join(out, name + '.out'), 'w'), stderr=subprocess.STDOUT)
            running.append((name, p, time.time()))
            print('presets: %s pid %d, %d levels' % (name, p.pid, len(part)), flush=True)
            time.sleep(2)
        time.sleep(2)
        for item in list(running):
            name, p, started = item
            code = p.poll()
            if code is None and time.time() - started > args.timeout:
                p.kill()
                code = p.wait()
                print('presets: %s timed out: killed pid %d' % (name, p.pid))
            if code is not None:
                running.remove(item)
                print('presets: %s exit %d after %.0f s' % (name, code, time.time() - started), flush=True)
                shutil.rmtree(os.path.join(out, 'data-' + name), ignore_errors=True)
    got = sum(1 for n in levels if os.path.exists(os.path.join(pictures, '%s-a-%s%s.png' % (n, args.tag, '-base' if twice else ''))))
    print('presets: %d of %d levels have pictures (%.0f s)' % (got, len(levels), time.time() - t0))
    return 0


# ---- what the walk says ----------------------------------------------------------------------------------------------
def read_stats(out, tag):
    """level -> list of {key: value} of its rta_look_stats lines (in the order of the stops o a b c f)."""
    stats = {}
    for path in sorted(glob.glob(os.path.join(out, tag + '-*.out'))):
        for line in open(path, errors='replace'):
            if 'rta_look_stats ' not in line:
                continue
            d = dict(re.findall(r'(\w+)=(\S+)', line.split('rta_look_stats ', 1)[1]))
            d['_file'] = os.path.basename(path)
            stats.setdefault(d.get('level', ''), []).append(d)
    return stats


def picture_stats(path):
    """mean brightness (0..255, Rec. 601) and mean saturation (0..1) of a picture, and of its lower two thirds."""
    from PIL import Image, ImageStat
    im = Image.open(path).convert('RGB')
    w, h = im.size
    out = {}
    for part, box in (('all', (0, 0, w, h)), ('low', (0, h // 3, w, h))):
        crop = im.crop(box).resize((160, 90))
        r, g, b = ImageStat.Stat(crop).mean
        hsv = ImageStat.Stat(crop.convert('HSV')).mean
        out[part] = (0.299 * r + 0.587 * g + 0.114 * b, hsv[1] / 255.0, (r, g, b))
    return out


def floats(text):
    return [float(x) for x in str(text).split(',')]


def pick(name, rows, pics):
    """The preset of one level from what it is (rows: its rta_look_stats; pics: stop -> picture figures of the walk's
    base pictures).  Returns ({key: value}, why)."""
    if not rows:
        return None, 'no stats'
    ground = [r for r in rows if r.get('ground') == '1'] or rows
    r = ground[0]
    clear = floats(r.get('clear', '0,0,0'))
    dome, dark, light = r.get('dome') == '1', r.get('dark') == '1', int(r.get('light', '128'))
    far = float(r.get('far', '1800'))
    lights = max(int(x.get('lights', '0')) for x in rows)
    sun = floats(r.get('sun', '0,0,0,0'))
    p, why = {}, []
    # how the game's own colours (stop g: the chase view with all of Godot's look off) compare with ours (stop a)
    own = pics.get('g')
    ours = [pics[k] for k in 'a' if k in pics]
    if own and ours:
        y_own, s_own = own['low'][0], own['low'][1]
        y_ours = sum(x['low'][0] for x in ours) / len(ours)
        s_ours = sum(x['low'][1] for x in ours) / len(ours)
        # a part of the difference only: the haze and the shadows are meant to change the picture
        if y_ours > 4:
            # the target: a little under the game's own colours - the shadows and the haze are meant to take some (the
            # Compatibility picture of the earlier rounds stands at 0.66 to 0.93 of them)
            ratio = max(0.80, min(1.30, 0.85 * y_own / y_ours))
            bright = max(0.9, min(1.15, 1.0 + 0.5 * (ratio - 1.0)))
            if abs(bright - 1.0) >= 0.02:
                p['brightness'] = round(bright, 3)
                why.append('brightness %.0f -> %.0f (the game colours %.0f)' % (y_ours, y_ours * bright, y_own))
        if s_ours > 0.02:
            # the target: a quarter more colour than the game's own flat colours (the Compatibility picture: 1.3 to 1.6)
            sat = max(1.0, min(1.40, 1.22 * (1.0 + 0.5 * (1.25 * s_own / s_ours - 1.0))))
            if abs(sat - 1.22) >= 0.02:
                p['saturation'] = round(sat, 3)
                why.append('saturation %.2f against the game\'s %.2f' % (s_ours, s_own))
    brightest = max(clear) if clear else 0
    if dark:
        kind = 'dark, lit by the game\'s lights' if lights >= 3 else 'dark'
        # darkness closes in sooner; the game's torches carry the scene: a little more of them where there are many
        p['shade'] = 0.86 if light >= 128 else 0.90
        p['fog_end'] = 1000.0 if far >= 1500 else 850.0
        p['bloom_strength'] = 1.25 if lights >= 3 else 1.0
        if lights >= 3:
            p['light_energy'] = 1.15
        p['contrast'] = 1.08
    elif dome:
        kind = 'painted dome'
        p['shade'] = 0.66
        p['fog_end'] = round(max(900.0, min(1400.0, far * 0.72)), 0)
        p['fog_amount'] = 0.85
        p['bloom_strength'] = 0.85
    else:
        kind = 'open sky'
        warm = clear[0] - clear[2] if len(clear) == 3 else 0
        p['shade'] = 0.62 if brightest > 0.45 else 0.66
        p['fog_end'] = round(max(950.0, min(1450.0, far * 0.75)), 0)
        p['fog_start'] = 420.0 if brightest > 0.45 else 360.0
        p['bloom_strength'] = 0.75 if brightest > 0.6 else 0.9
        if warm > 0.12:                         # a warm (dusk, desert, fire) clear colour: the sun lower and warmer
            p['sun_el'] = 36.0
            why.append('warm clear colour: low sun')
        if float(sun[2]) >= 0.004:              # the textures say clearly where the light is: a sun with a firmer shadow
            p['shade'] = round(p['shade'] - 0.03, 3)
    why.insert(0, kind + ('; light level %d' % light) + ('; %d of the game\'s lights near' % lights if lights else ''))
    return p, '; '.join(why)


def make(args):
    out = under_local(args.out)
    tag = args.source
    stats = read_stats(out, tag)
    if not stats:
        raise SystemExit('presets.py: no rta_look_stats lines in %s/%s-*.out' % (out, tag))
    pictures = os.path.join(out, 'pictures')
    lines = ['# Look presets by level for scene_view.gd: made by tools/godot/presets.py make from the walk "%s" (%s).' % (tag, time.strftime('%Y-%m-%d %H:%M')),
             '# Game output (picked from the levels\' own colours): it stays under local/ and is staged with the project.', '']
    made = 0
    for name in sorted(stats):
        if not name:
            continue
        pics = {}
        for stop in STOPS:
            path = os.path.join(pictures, '%s-%s-%s-%s.png' % (name, stop, tag, 'game' if stop == 'g' else 'base'))
            if os.path.exists(path):
                pics[stop] = picture_stats(path)
            old = os.path.join(pictures, '%s-%s-%s-old.png' % (name, stop, tag))
            ground = [r for r in stats[name] if r.get('ground') == '1'] or stats[name]
            first_run = re.fullmatch(r'%s-\d+\.out' % re.escape(tag), ground[0].get('_file', '')) is not None
            if args.blend < 1.0 and first_run and stop != 'g' and stop in pics and os.path.exists(old):
                # a walk whose base pictures had the whole linear sun (balance 1): what balance 0.6 and the Forward+
                # saturation give, estimated between its old and base pictures
                o = picture_stats(old)
                for part in ('all', 'low'):
                    y = o[part][0] + args.blend * (pics[stop][part][0] - o[part][0])
                    sat = (o[part][1] + args.blend * (pics[stop][part][1] - o[part][1])) * 1.22 / 1.10
                    pics[stop][part] = (y, sat, pics[stop][part][2])
        preset, why = pick(name, stats[name], pics)
        if preset is None:
            continue
        lines.append('[%s]' % name)
        lines.append('; %s' % why)
        for key in sorted(preset):
            value = preset[key]
            lines.append('%s=%s' % (key, ('%.3f' % value).rstrip('0').rstrip('.') if isinstance(value, float) else value))
        lines.append('')
        made += 1
    target = os.path.join(out, 'levels.cfg')
    open(target, 'w').write('\n'.join(lines))
    print('presets: %d levels -> %s (to ship them: copy the key lines into tools/godot/project/presets/levels.cfg)' % (made, target))
    return 0


# ---- pictures ---------------------------------------------------------------------------------------------------------
def sheets(args):
    from PIL import Image, ImageDraw
    out = under_local(args.out)
    pictures = os.path.join(out, 'pictures')
    target = os.path.join(out, 'sheets')
    os.makedirs(target, exist_ok=True)
    names = sorted({os.path.basename(p).split('-')[0] for p in glob.glob(os.path.join(pictures, '*-a-*.png'))})
    W, H = 384, 216
    rows = [('before', args.before), ('after', args.after)] + ([('base', args.base)] if args.base else [])
    index = []
    for name in names:
        sheet = Image.new('RGB', (W * len(STOPS), (H + 18) * len(rows)), (18, 18, 18))
        draw = ImageDraw.Draw(sheet)
        any_after = False
        for r, (label, tag) in enumerate(rows):
            for k, stop in enumerate(STOPS):
                path = os.path.join(pictures, '%s-%s-%s.png' % (name, stop, tag))
                if stop == 'g':
                    path = os.path.join(pictures, '%s-g-%s-game.png' % (name, tag.split('-')[0]))
                if os.path.exists(path):
                    sheet.paste(Image.open(path).convert('RGB').resize((W, H)), (k * W, r * (H + 18) + 18))
                    any_after = any_after or label == 'after'
            draw.text((6, r * (H + 18) + 3), '%s  %s (%s)   stops: g the game colours (Godot look off), a chase, b walked, c turned, f first person' % (name, label, tag),
                      fill=(230, 230, 230))
        sheet.save(os.path.join(target, name + '.jpg'), quality=82)
        a_before = os.path.join(pictures, '%s-a-%s.png' % (name, args.before))
        a_after = os.path.join(pictures, '%s-a-%s.png' % (name, args.after))
        if os.path.exists(a_before):
            index.append((name, a_before, a_after if os.path.exists(a_after) else None))
    if index:
        cols, w, h = 6, 256, 144
        per = 2 * h + 14
        rows_n = (len(index) + cols - 1) // cols
        big = Image.new('RGB', (cols * w, rows_n * per), (18, 18, 18))
        draw = ImageDraw.Draw(big)
        for i, (name, a, b) in enumerate(index):
            x, y = (i % cols) * w, (i // cols) * per
            big.paste(Image.open(a).convert('RGB').resize((w, h)), (x, y + 14))
            if b:
                big.paste(Image.open(b).convert('RGB').resize((w, h)), (x, y + 14 + h))
            draw.text((x + 4, y + 1), name, fill=(230, 230, 230))
        big.save(os.path.join(target, 'index.jpg'), quality=80)
    print('presets: %d sheets in %s (index.jpg: stop a, before above after)' % (len(names), target))
    return 0


def stats_cmd(args):
    out = under_local(args.out)
    pictures = os.path.join(out, 'pictures')
    names = sorted({os.path.basename(p).split('-')[0] for p in glob.glob(os.path.join(pictures, '*-a-*.png'))})
    tags = args.tags.split(',')
    sums = {t: [0.0, 0.0, 0] for t in tags}
    print('level ' + ' '.join('%-16s' % t for t in tags) + '  (stop a, lower two thirds: brightness / saturation)')
    for name in names:
        cells = []
        for t in tags:
            path = os.path.join(pictures, '%s-a-%s.png' % (name, t))
            if os.path.exists(path):
                y, s, _ = picture_stats(path)['low']
                sums[t][0] += y; sums[t][1] += s; sums[t][2] += 1
                cells.append('%5.1f / %.3f    ' % (y, s))
            else:
                cells.append('%-16s' % '-')
        print('%-10s %s' % (name, ' '.join(cells)))
    print('mean      ' + ' '.join('%5.1f / %.3f    ' % (v[0] / max(v[2], 1), v[1] / max(v[2], 1)) for v in sums.values()))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('what', choices=['walk', 'make', 'sheets', 'stats'])
    ap.add_argument('out')
    ap.add_argument('--levels', default='')
    ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--size', default='960x540')
    ap.add_argument('--look', default='')
    ap.add_argument('--tag', default='before')
    ap.add_argument('--renderer', default='', help='walk: another renderer of Godot (gl_compatibility: the fifth round\'s comparison)')
    ap.add_argument('--timeout', type=float, default=1800, help='walk: seconds one program may take')
    ap.add_argument('--chunk', type=int, default=8, help='walk: levels a program (0: all of them in --jobs programs)')
    ap.add_argument('--run', default='', help='walk: a label in the names of the logs (a second walk of some levels beside the first)')
    ap.add_argument('--from', dest='source', default='before')
    ap.add_argument('--blend', type=float, default=1.0, help='make: the base pictures of the first walk (logs TAG-N.out) had balance 1: estimate balance BLEND from their old and base')
    ap.add_argument('--before', default='before-old')
    ap.add_argument('--after', default='after')
    ap.add_argument('--base', default='')
    ap.add_argument('--tags', default='before-old,before-base,after')
    args = ap.parse_args()
    return {'walk': walk, 'make': make, 'sheets': sheets, 'stats': stats_cmd}[args.what](args)


if __name__ == '__main__':
    sys.exit(main())
