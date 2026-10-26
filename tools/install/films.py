#!/usr/bin/env python3
"""films.py - sharp films: the game's films enlarged on this computer, from YOUR OWN disc.

  python3 tools/install/films.py --disc "/path/to/your image.iso" [--out DIR] [--upscaler PATH]
          [--model realesrgan-x4plus|realesr-animevideov3] [--height 1344] [--quality 3] [--list] [--force]

Remastered shows these in place of the game's own 640 x 448 pictures while a film plays (the portal's Remastered;
Classic shows the originals).  The film still plays through the game's own film player and the host decoder
(tools/recomp/app/film.cpp): its timing and its sound are the game's; only the picture on the screen is the
enlarged copy of the picture the game has just decoded (docs/issues/native-cutscenes.md).

What it does:
  1. finds the films on the disc: the MPEG-2 video streams in the game's lump and stream files (.LMP, .SMG): from a
     sequence header to its sequence end code - the pieces the game's film player hands to the decoder one at a time
     (it resets the decoder between them);
  2. names each by the key film.cpp computes while it plays: the FNV-1a hash of the stream's first 65,536 bytes;
  3. decodes each to pictures (ffmpeg), enlarges them with an AI upscaler (Real-ESRGAN's ncnn-vulkan program, when it
     is found: --upscaler, $RTA_UPSCALER, the PATH, local/upscaler/ncnn/), else with ffmpeg's lanczos and a light
     sharpening (said so), and scales them to --height lines (default 1344: three times the film's 448);
  4. writes them as JPEG files, one per picture in display order, under the user data folder:
       macOS    ~/Library/Application Support/Play-RTA/films/<key>/00000.jpg ...
       Windows  %APPDATA%/Play-RTA/films/<key>/...
       Linux    ~/.local/share/Play-RTA/films/<key>/...
     with manifest.json (where the film was found, its picture count and size, how it was made).  A film whose
     manifest says it was made the same way is not made again (--force does).

Needs ffmpeg (Homebrew: brew install ffmpeg) and, for the AI enlarging, the official release of
realesrgan-ncnn-vulkan (https://github.com/xinntao/Real-ESRGAN, releases: the ncnn-vulkan program with its models).
Everything written is made from the game's film: it stays on this computer, never in a repository.
Standard library only.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recomp'))
from disc import Iso, SECTOR  # noqa: E402

VERSION = 1                     # of how a film is made: a change makes every film again
KEY_BYTES = 65536               # tools/recomp/app/film.cpp KEY_BYTES
SEQ, SEQ_END = b'\x00\x00\x01\xb3', b'\x00\x00\x01\xb7'
KINDS = ('.LMP', '.SMG', '.M2V', '.PSS')


def say(text):
    print('[films] ' + text, flush=True)


def fnv64(data):
    h = 1469598103934665603
    for b in data:
        h = ((h ^ b) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h or 1


def default_out():
    system = platform.system()
    if system == 'Darwin':
        return os.path.expanduser('~/Library/Application Support/Play-RTA/films')
    if system == 'Windows':
        return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Play-RTA', 'films')
    return os.path.join(os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share')), 'Play-RTA', 'films')


def sequence_ok(data, at):
    """A plausible MPEG-2 sequence header at `at`: a picture size a console film has, known aspect and rate codes."""
    if at + 12 > len(data):
        return False
    b = data[at + 4:at + 8]
    width, height = (b[0] << 4) | (b[1] >> 4), ((b[1] & 15) << 8) | b[2]
    aspect, rate = b[3] >> 4, b[3] & 15
    return 160 <= width <= 1024 and 112 <= height <= 768 and 1 <= aspect <= 4 and 1 <= rate <= 8


def find_films(iso):
    """[(path, offset, size, width, height)] of every stream: a valid sequence header after a sequence end (or the
    file's start) up to and including the next sequence end."""
    out = []
    for path, entry in iso.walk():
        if not path.upper().endswith(KINDS) or entry['size'] < 4096:
            continue
        iso.f.seek(entry['lba'] * SECTOR)
        data = iso.f.read(entry['size'])
        at = 0
        while True:
            start = data.find(SEQ, at)
            if start < 0:
                break
            if not sequence_ok(data, start):
                at = start + 4
                continue
            end = data.find(SEQ_END, start)
            if end < 0:
                break
            b = data[start + 4:start + 8]
            out.append((path, start, end + 4 - start, (b[0] << 4) | (b[1] >> 4), ((b[1] & 15) << 8) | b[2], data[start:end + 4]))
            at = end + 4
    return out


def find_upscaler(given):
    names = ['realesrgan-ncnn-vulkan.exe', 'realesrgan-ncnn-vulkan'] if platform.system() == 'Windows' else ['realesrgan-ncnn-vulkan']
    for candidate in [given, os.environ.get('RTA_UPSCALER', '')]:
        if candidate and os.path.isfile(candidate):
            return candidate
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        local = os.path.join(ROOT, 'local', 'upscaler', 'ncnn', name)
        if os.path.isfile(local):
            return local
    return ''


def run(cmd, **kw):
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if result.returncode != 0:
        raise SystemExit('failed: %s\n%s' % (' '.join(cmd[:3]), (result.stderr or result.stdout)[-2000:]))
    return result


def make(stream, key, target, args, upscaler):
    """Decode, enlarge, scale and write one film's pictures; returns the manifest."""
    work = tempfile.mkdtemp(prefix='rta-film-')
    try:
        src = os.path.join(work, 'film.m2v')
        open(src, 'wb').write(stream)
        raw, big = os.path.join(work, 'raw'), os.path.join(work, 'big')
        os.makedirs(raw)
        os.makedirs(big)
        # every picture in display order, as the game's decoder hands them out (no frame dropped or repeated)
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'mpegvideo', '-i', src, '-fps_mode', 'passthrough', '-start_number', '0',
             os.path.join(raw, '%05d.png')])
        pictures = len([n for n in os.listdir(raw) if n.endswith('.png')])
        if pictures == 0:
            return None
        made_by = 'ffmpeg lanczos + cas'
        if upscaler:
            model = args.model
            scale = '4' if model.endswith('x4plus') or model.endswith('anime') else '4'
            cmd = [upscaler, '-i', raw, '-o', big, '-n', model, '-s', scale, '-f', 'png']
            models = os.path.join(os.path.dirname(upscaler), 'models')
            if os.path.isdir(models):
                cmd += ['-m', models]
            if args.tile:
                cmd += ['-t', str(args.tile)]
            run(cmd)
            made_by = 'Real-ESRGAN ncnn-vulkan, model %s, x%s' % (model, scale)
            source = big
        else:
            source = raw
        os.makedirs(target, exist_ok=True)
        # to the height asked for (the width keeps the film's shape), as JPEG; a light sharpening after a plain enlarging
        flt = 'scale=-2:%d:flags=lanczos' % args.height + ('' if upscaler else ',cas=0.5')
        run(['ffmpeg', '-v', 'error', '-y', '-start_number', '0', '-i', os.path.join(source, '%05d.png'), '-vf', flt,
             '-q:v', str(args.quality), '-start_number', '0', os.path.join(target, '%05d.jpg')])
        written = len([n for n in os.listdir(target) if n.endswith('.jpg')])
        if written != pictures:
            raise SystemExit('film %016x: %d pictures decoded, %d written' % (key, pictures, written))
        first = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
                     os.path.join(target, '00000.jpg')]).stdout.strip().split(',')
        return {'version': VERSION, 'key': '%016x' % key, 'pictures': pictures, 'width': int(first[0]), 'height': int(first[1]),
                'made_by': made_by, 'height_asked': args.height, 'quality': args.quality}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--disc', default=os.environ.get('RTA_DISC', ''))
    ap.add_argument('--out', default='')
    ap.add_argument('--upscaler', default='')
    ap.add_argument('--model', default='realesrgan-x4plus', help='realesrgan-x4plus (default: films of rendered scenes) | realesr-animevideov3')
    ap.add_argument('--height', type=int, default=1344)
    ap.add_argument('--quality', type=int, default=3, help="ffmpeg's JPEG quality scale: 2 best .. 31 worst")
    ap.add_argument('--tile', type=int, default=0, help='the upscaler\'s tile size (0: its own choice; smaller for little video memory)')
    ap.add_argument('--list', action='store_true', help='only list the films found')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    if not args.disc or not os.path.isfile(args.disc):
        raise SystemExit('name your own disc image with --disc (or RTA_DISC)')
    if not shutil.which('ffmpeg') and not args.list:
        raise SystemExit('ffmpeg is needed (macOS: brew install ffmpeg)')
    out = args.out or default_out()
    t0 = time.time()
    films = find_films(Iso(args.disc))
    say('%d film(s) on the disc (%.1f s)' % (len(films), time.time() - t0))
    upscaler = '' if args.list else find_upscaler(args.upscaler)
    if not args.list:
        say('enlarging with ' + (upscaler if upscaler else "ffmpeg's lanczos (no realesrgan-ncnn-vulkan found: see --upscaler)"))
    done = 0
    for path, offset, size, width, height, stream in films:
        key = fnv64(stream[:KEY_BYTES])
        line = '%016x  %s +%d, %d bytes, %d x %d' % (key, path, offset, size, width, height)
        if args.list:
            say(line)
            continue
        target = os.path.join(out, '%016x' % key)
        manifest_path = os.path.join(target, 'manifest.json')
        if not args.force and os.path.isfile(manifest_path):
            try:
                m = json.load(open(manifest_path))
                if m.get('version') == VERSION and m.get('height_asked') == args.height and \
                        (('Real-ESRGAN' in m.get('made_by', '')) == bool(upscaler)) and \
                        all(os.path.isfile(os.path.join(target, '%05d.jpg' % k)) for k in range(int(m['pictures']))):
                    say(line + ': already made')
                    continue
            except (OSError, ValueError, KeyError):
                pass
        if os.path.isdir(target):
            shutil.rmtree(target)
        t1 = time.time()
        m = make(stream, key, target, args, upscaler)
        if m is None:
            say(line + ': no picture decoded, left out')
            continue
        m.update({'file': path, 'offset': offset, 'size': size, 'film_width': width, 'film_height': height,
                  'stream_sha1': hashlib.sha1(stream).hexdigest()})
        json.dump(m, open(manifest_path, 'w'), indent=1)
        done += 1
        say('%s: %d pictures -> %d x %d in %.0f s' % (line, m['pictures'], m['width'], m['height'], time.time() - t1))
    if not args.list:
        say('done: %d film(s) made, under %s (%.0f s)' % (done, out, time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
