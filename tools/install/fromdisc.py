#!/usr/bin/env python3
"""fromdisc.py - build the native game from YOUR OWN disc image, on this computer.

  python3 tools/install/fromdisc.py --platform mac|linux|windows --disc "/path/to/your image.iso"
          [--desktop DIR] [--no-launcher] [--jobs N] [--godot]
          [--launcher-name NAME] [--service HOST:PORT] [--progress]
  python3 tools/install/fromdisc.py --find [DIR ...]     # the disc images of US v2.00 in the usual places
  python3 tools/install/fromdisc.py --check FILE         # exit code 0 when FILE is one

The step the three installers (install-mac.command, install-linux.sh, install-windows.ps1)
and the "Champions Setup" programs (tools/install/setup/) share once their toolchain is in place.
--progress adds lines "@progress PERCENT TEXT" for a setup window's progress bar; --service puts
the room service's address where the program reads it (the launcher on a Mac, server.txt beside the
program on Windows and Linux) - the address comes from whoever hands out the setup, never from here.

The game's code is never distributed: it is
translated here, from the executable on the player's own disc.

  1. reads the disc image (ISO 9660), copies SLUS_209.73 out of it to the top of this
     workspace (where tools/recomp/recomp.py looks for it) and checks it is the US v2.00
     executable (PCSX2's checksum 4028A55F; the fix set patches/SLUS-20973_4028A55F.pnach is
     made for exactly that file);
  2. translates the main VU1 microprogram ahead of time (render/vu1_translate.py --elf) when
     there is no translation yet - what is not translated is interpreted, the picture is the same;
  3. runs the platform's build: tools/recomp/app/build.py (macOS), build_linux.py (Linux),
     build_win.py (Windows) - the translation (recomp.py) and the compile;
  4. writes local/install.txt (where the disc image is and which program to start) and a
     launcher on the desktop;
  5. (--godot) the game library of the Godot application (tools/godot/build.py snapshot + lib, macOS;
     tools/godot/build_lib_linux.py on Linux; tools/godot/build_lib_win.py on Windows) from the same translation, put where the Godot
     application looks for it (tools/godot/project/gamelib.gd): macOS ~/Library/Application Support/
     Open Champions/RTA Godot/, Linux ~/.local/share/open-champions/rta-godot/, Windows %APPDATA%/Open Champions/RTA Godot/.  The Godot application
     itself holds only our code; this library is the game, made here, and stays on this computer.
     If --godot is requested and that step fails, the command fails too; the native build stays available
     and the previous install record/library are preserved.

Everything made from the game (the executable, the translation, objects, programs, the
player's data) stays under this workspace's local/ folder and SLUS_209.73 at its top, both
ignored by git (.gitignore): nothing of it is ever to be committed or shared.  Nothing is
downloaded by this script.  Standard library only.
"""
import argparse
import os
import platform
import shutil
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APP = os.path.join(ROOT, 'tools', 'recomp', 'app')
OUT = os.path.join(ROOT, 'local', 'recomp-out')
ELF_NAME = 'SLUS_209.73'
ELF_CRC = 0x4028A55F          # PCSX2's figure for the executable: the XOR of its 32-bit words
SECTOR = 2048


def say(text):
    print('[install] ' + text, flush=True)


PROGRESS = {'on': False, 'last': -1}


def progress(percent, text):
    """A line for a setup window (--progress): "@progress PERCENT TEXT"."""
    if PROGRESS['on']:
        percent = max(PROGRESS['last'], min(100, int(percent)))
        PROGRESS['last'] = percent
        print('@progress %d %s' % (percent, text), flush=True)


class Watch:
    """While a build step runs: how many object files it has written so far, as a share of the expected number,
    turned into the setup window's percent (from .. to).  Only a picture of the progress; the step says when it is done."""
    def __init__(self, folders, expected, low, high, text, first_text=None):
        self.folders, self.expected, self.low, self.high, self.text = folders, max(1, expected), low, high, text
        self.first_text = first_text or text
        self.start, self.stop = time.time(), threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def count(self):
        n = 0
        for top in self.folders:
            for folder, _, files in os.walk(top):
                for name in files:
                    if name.endswith(('.o', '.obj')):
                        try:
                            if os.path.getmtime(os.path.join(folder, name)) >= self.start - 1:
                                n += 1
                        except OSError:
                            pass
        return n

    def run(self):
        while not self.stop.wait(2.0):
            n = self.count()
            if n == 0:
                progress(self.low, self.first_text)
            else:
                share = min(0.97, n / float(self.expected))
                progress(self.low + (self.high - self.low) * share, '%s (%d of about %d files)' % (self.text, n, self.expected))

    def __enter__(self):
        if PROGRESS['on']:
            self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(5)


# ---- the disc image -------------------------------------------------------------------------
def iso_find(image, name):
    """(byte offset, size) of a file in the root directory of an ISO 9660 image, or None."""
    with open(image, 'rb') as f:
        f.seek(16 * SECTOR)
        pvd = f.read(SECTOR)
        if pvd[1:6] != b'CD001':
            raise ValueError('not an ISO 9660 disc image (no volume descriptor at sector 16): ' + image)
        root = pvd[156:156 + 34]
        lba, size = struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0]
        f.seek(lba * SECTOR)
        data = f.read(size)
    want = name.upper()
    at = 0
    while at < len(data):
        length = data[at]
        if length == 0:                       # records do not cross a sector: go to the next one
            at = (at // SECTOR + 1) * SECTOR
            continue
        record = data[at:at + length]
        ident = record[33:33 + record[32]].decode('latin1').upper()
        if ident.split(';')[0] == want and not record[25] & 2:
            return struct.unpack_from('<I', record, 2)[0] * SECTOR, struct.unpack_from('<I', record, 10)[0]
        at += length
    return None


def elf_crc(data):
    crc = 0
    for (word,) in struct.iter_unpack('<I', data[:len(data) // 4 * 4]):
        crc ^= word
    return crc


def extract_elf(image):
    target = os.path.join(ROOT, ELF_NAME)
    if os.path.exists(target):
        data = open(target, 'rb').read()
        if elf_crc(data) == ELF_CRC:
            say('%s is already here and is the right one' % ELF_NAME)
            return True
    found = iso_find(image, ELF_NAME)
    if not found:
        say('this disc image has no %s: it must be Champions: Return to Arms, US release (SLUS-20973)' % ELF_NAME)
        return False
    offset, size = found
    with open(image, 'rb') as f:
        f.seek(offset)
        data = f.read(size)
    if data[:4] != b'\x7fELF':
        say('%s on this disc image is not an executable (damaged image?)' % ELF_NAME)
        return False
    crc = elf_crc(data)
    if crc != ELF_CRC:
        say('%s on this disc image has the checksum %08X, not %08X: this build is for version 2.00 of the US release only'
            % (ELF_NAME, crc, ELF_CRC))
        return False
    with open(target + '.part', 'wb') as f:
        f.write(data)
    os.replace(target + '.part', target)
    say('copied %s out of the disc image (%d bytes, checksum %08X: US v2.00)' % (ELF_NAME, size, crc))
    return True


def check_disc(image):
    """True when the image holds the US v2.00 executable (reads the directory and the executable only)."""
    try:
        found = iso_find(image, ELF_NAME)
        if not found:
            return False
        offset, size = found
        if not 1000000 < size < 20000000:
            return False
        with open(image, 'rb') as f:
            f.seek(offset)
            data = f.read(size)
        return data[:4] == b'\x7fELF' and elf_crc(data) == ELF_CRC
    except (OSError, ValueError, struct.error, IndexError):
        return False


def usual_places():
    home = os.path.expanduser('~')
    places = [os.path.join(home, d) for d in ('Downloads', 'Desktop', 'Documents')]
    if sys.platform == 'darwin':
        places.append(os.path.join(home, 'Library', 'Application Support', 'Play-RTA'))
        places += [os.path.join('/Volumes', v) for v in sorted(os.listdir('/Volumes'))] if os.path.isdir('/Volumes') else []
    elif os.name == 'nt':
        places += ['%s:\\' % c for c in 'DEFGHIJKLMNOPQRSTUVWXYZ' if os.path.exists('%s:\\' % c)]
    else:
        user = os.environ.get('USER', '')
        for top in ('/media/' + user, '/run/media/' + user, '/mnt'):
            if os.path.isdir(top):
                places += [os.path.join(top, v) for v in sorted(os.listdir(top))]
    return places


def find_discs(places, depth=2):
    """Disc images (.iso, 1 to 9 GB) of the US v2.00 release under the given folders, a few levels deep."""
    found, seen = [], set()
    for top in places:
        top = os.path.abspath(os.path.expanduser(top))
        if not os.path.isdir(top):
            continue
        base = top.rstrip(os.sep).count(os.sep)
        for folder, dirs, files in os.walk(top):
            if folder.rstrip(os.sep).count(os.sep) - base >= depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.endswith(('.app', '.photoslibrary'))]
            for name in files:
                if not name.lower().endswith('.iso'):
                    continue
                path = os.path.join(folder, name)
                try:
                    real = os.path.realpath(path)
                    if real in seen or not 1000000000 < os.path.getsize(path) < 9000000000:
                        continue
                except OSError:
                    continue
                seen.add(real)
                if check_disc(path):
                    found.append(path)
    return found


# ---- the build --------------------------------------------------------------------------------
def run(command, watch=None):
    say('running: ' + ' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in command))
    if watch is None:
        return subprocess.run(command, cwd=ROOT).returncode == 0
    with watch:
        return subprocess.run(command, cwd=ROOT).returncode == 0


def vu1_translation():
    fast = os.path.join(OUT, 'gen-vu', 'vu1_fast.cpp')
    if os.path.exists(fast):
        return
    os.makedirs(os.path.dirname(fast), exist_ok=True)
    if not run([sys.executable, os.path.join(ROOT, 'tools', 'recomp', 'render', 'vu1_translate.py'),
                '--elf', os.path.join(ROOT, ELF_NAME), '--out', fast]):
        say('the VU1 translation did not work; VU1 is interpreted (the same picture, a little slower)')
        if os.path.exists(fast):
            os.remove(fast)


def build(target, jobs, high=96):
    py = sys.executable
    watch = Watch([OUT], {'mac': 75, 'linux': 85, 'windows': 91}[target], 12, high,
                  'Compiling the program', 'Translating the game\'s code to C++')
    if target == 'mac':
        ok = run([py, os.path.join(APP, 'build.py')] + (['--qt', os.environ['RTA_QT']] if os.environ.get('RTA_QT') else []), watch)
        program = os.path.join(OUT, 'bin', 'rta_app')
    elif target == 'linux':
        ok = run([py, os.path.join(APP, 'build_linux.py'), '--jobs', str(jobs)], watch)
        arch = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'aarch64': 'aarch64', 'arm64': 'aarch64'}.get(platform.machine().lower(), platform.machine())
        program = os.path.join(OUT, 'linux', 'rta-linux-' + arch, 'rta_app')
    else:
        ok = run([py, os.path.join(APP, 'build_win.py'), '--jobs', str(jobs)], watch)
        program = os.path.join(OUT, 'win', 'rta-windows', 'rta_app.exe')
    if not ok or not os.path.exists(program):
        say('the build did not finish: the lines above say why')
        return None
    return program


# ---- the Godot application's game library ------------------------------------------------------
def godot_folder(target):
    """Where the Godot application looks for the library (tools/godot/project/gamelib.gd, standard_folder)."""
    if target == 'mac':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Open Champions', 'RTA Godot')
    if target == 'windows':
        return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Open Champions', 'RTA Godot')
    data = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(data, 'open-champions', 'rta-godot')


def godot_library(target, jobs):
    """The game as the library the Godot application loads, from the translation the native build has just compiled."""
    py = sys.executable
    out = os.path.join(ROOT, 'local', 'godot-install')
    env = dict(os.environ, RTA_GODOT_OUT=out)
    build = os.path.join(ROOT, 'tools', 'godot', 'build.py')
    if target == 'mac':
        steps = [[py, build, 'snapshot', '--refresh'], [py, build, 'lib', '--jobs', str(min(jobs, 8))]]
        made, name = os.path.join(out, 'lib', 'librta_game.dylib'), 'librta_game.dylib'
    elif target == 'linux' and os.path.exists(os.path.join(ROOT, 'tools', 'godot', 'build_lib_linux.py')):
        arch = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower(), platform.machine())
        steps = [[py, os.path.join(ROOT, 'tools', 'godot', 'build_lib_linux.py'), '--here', '--arch', arch]]
        made, name = None, 'librta_game.so'
    elif target == 'windows' and os.path.exists(os.path.join(ROOT, 'tools', 'godot', 'build_lib_win.py')):
        # the same translation and toolchain as build_win.py (llvm-mingw or MinGW-w64): tools/godot/build_lib_win.py
        steps = [[py, os.path.join(ROOT, 'tools', 'godot', 'build_lib_win.py'), '--jobs', str(min(jobs, 8))]]
        variant = 'windows-p8' if env.get('RTA_GODOT_PARTY8') == '1' else 'windows'
        made, name = os.path.join(out, variant, 'librta_game.dll'), 'librta_game.dll'
    else:
        say('the Godot application\'s game library is not made for %s yet (docs/issues/native-godot.md); the native program is' % target)
        return None
    for step in steps:
        say('running: ' + ' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in step))
        with Watch([out], 70, 80, 97, 'Building the Godot version'):
            code = subprocess.run(step, cwd=ROOT, env=env).returncode
        if code != 0:
            say('the Godot library did not build: the lines above say why (the native program is built all the same)')
            return None
    if made is None:
        found = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(ROOT, 'local', 'godot-install')) for f in fs if f == name]
        made = max(found, key=os.path.getmtime) if found else ''
    if not made or not os.path.exists(made):
        say('the Godot library is not where it should be: %s' % made)
        return None
    folder = godot_folder(target)
    os.makedirs(folder, exist_ok=True)
    final = os.path.join(folder, name)
    shutil.copy2(made, final + '.part')
    os.replace(final + '.part', final)
    say('the Godot application\'s game library: ' + final)
    return final


# ---- the room service --------------------------------------------------------------------------
def set_service(program, service):
    """A line "service = HOST:PORT" in server.txt beside the program (Windows, Linux: read when it starts)."""
    path = os.path.join(os.path.dirname(program), 'server.txt')
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    lines = [l for l in lines if not l.strip().replace(' ', '').startswith('service=')]
    lines.append('service = ' + service)
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    say('the room service: %s (in %s)' % (service, path))


# ---- the launcher -----------------------------------------------------------------------------
def desktop_dir(given):
    if given:
        return given
    if os.name == 'nt':
        return os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
    if sys.platform.startswith('linux'):
        try:
            d = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True).stdout.strip()
            if d:
                return d
        except OSError:
            pass
    return os.path.join(os.path.expanduser('~'), 'Desktop')


def launcher_mac(desktop, program, disc, name='Champions RTA Native', service=''):
    app = os.path.join(desktop, name + '.app')
    macos = os.path.join(app, 'Contents', 'MacOS')
    os.makedirs(macos, exist_ok=True)
    ident = 'org.open-champions.' + (''.join(c for c in name.lower() if c.isalnum()) or 'rta') + '-launcher'
    plist = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
             '<plist version="1.0"><dict>\n'
             '<key>CFBundleExecutable</key><string>launch</string>\n'
             '<key>CFBundleIdentifier</key><string>%s</string>\n'
             '<key>CFBundleName</key><string>%s</string>\n'
             '<key>CFBundlePackageType</key><string>APPL</string>\n'
             '<key>LSMinimumSystemVersion</key><string>13.0</string>\n'
             '</dict></plist>\n') % (ident, name.replace('&', '&amp;').replace('<', '&lt;'))
    open(os.path.join(app, 'Contents', 'Info.plist'), 'w').write(plist)
    script = os.path.join(macos, 'launch')
    q = lambda s: "'" + s.replace("'", "'\\''") + "'"
    env = ''
    qt = os.environ.get('RTA_QT', '')
    if qt and os.path.isdir(os.path.join(qt, 'plugins', 'platforms')):
        env += 'export QT_PLUGIN_PATH=%s\n' % q(os.path.join(qt, 'plugins'))    # an official Qt build does not know where it is
    if service:
        env += 'export RTA_NET2_SERVICE=${RTA_NET2_SERVICE:-%s}\n' % q(service)
    open(script, 'w').write('#!/bin/sh\n# made by tools/install/fromdisc.py: the native build of this workspace with your disc image\n'
                            '%smkdir -p %s\nexec %s --disc %s "$@" > %s 2>&1\n'
                            % (env, q(os.path.join(OUT, 'app-data')), q(program), q(disc), q(os.path.join(OUT, 'app-data', 'rta_app-log.txt'))))
    os.chmod(script, 0o755)
    return app


def launcher_linux(desktop, program, disc, name='Champions RTA Native', service=''):
    folder = os.path.dirname(program)
    exec_line = '"%s" "%s"' % (os.path.join(folder, 'play.sh'), disc)
    entry = ('[Desktop Entry]\nType=Application\nName=%s\n' % name +
             'Comment=The native build of Champions: Return to Arms, made from your own disc\n'
             'Exec=%s\nPath=%s\nTerminal=false\nCategories=Game;\n' % (exec_line, folder))
    made = []
    apps = os.path.join(os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share')), 'applications')
    for d in (apps, desktop):
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, 'rta-native.desktop' if name == 'Champions RTA Native' else
                                ''.join(c for c in name.lower() if c.isalnum() or c == '-') + '.desktop')
            open(path, 'w').write(entry)
            os.chmod(path, 0o755)
            made.append(path)
        except OSError as e:
            say('no launcher in %s: %s' % (d, e))
    if made and made[-1].startswith(desktop) and shutil.which('gio'):
        # GNOME asks once before it starts a launcher it has not been told to trust
        subprocess.run(['gio', 'set', made[-1], 'metadata::trusted', 'true'], capture_output=True)
    return made[-1] if made else None


def launcher_windows(desktop, program, disc, name='Champions RTA Native', service=''):
    # a shortcut through the Windows Script Host (no extra module): rta_app.exe --disc "<image>"
    link = os.path.join(desktop, name + '.lnk')
    ps = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\'%s\'); $s.TargetPath = \'%s\'; '
          '$s.Arguments = \'--disc "%s"\'; $s.WorkingDirectory = \'%s\'; $s.Save()'
          % (link.replace("'", "''"), program.replace("'", "''"), disc.replace("'", "''"), os.path.dirname(program).replace("'", "''")))
    ok = subprocess.run(['powershell', '-NoProfile', '-Command', ps]).returncode == 0
    return link if ok else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--platform', choices=('mac', 'linux', 'windows'))
    parser.add_argument('--disc', help='your own disc image of Champions: Return to Arms (SLUS-20973, v2.00)')
    parser.add_argument('--desktop', help='where the launcher goes (default: this user\'s desktop)')
    parser.add_argument('--no-launcher', action='store_true')
    parser.add_argument('--godot', action='store_true', help='also the game library of the Godot application (tools/godot)')
    parser.add_argument('--jobs', type=int, default=max(1, min(8, os.cpu_count() or 4)))
    parser.add_argument('--launcher-name', default='Champions RTA Native', help='the name of the launcher (default: Champions RTA Native)')
    parser.add_argument('--service', default='', help='the room service, HOST:PORT, as the program is to find it')
    parser.add_argument('--progress', action='store_true', help='lines "@progress PERCENT TEXT" for a setup window')
    parser.add_argument('--find', nargs='*', metavar='DIR', help='only list the disc images of US v2.00 in these folders (default: the usual places)')
    parser.add_argument('--check', metavar='FILE', help='only check one disc image: exit code 0 when it is US v2.00')
    args = parser.parse_args()
    if args.check:
        ok = os.path.isfile(args.check) and check_disc(args.check)
        print('%s: %s' % (args.check, 'US v2.00' if ok else 'not the US v2.00 disc image'))
        return 0 if ok else 1
    if args.find is not None:
        for path in find_discs(args.find or usual_places()):
            print(path, flush=True)
        return 0
    if not args.platform or not args.disc:
        parser.error('--platform and --disc are needed (or --find)')
    PROGRESS['on'] = args.progress
    disc = os.path.abspath(os.path.expanduser(args.disc))
    if not os.path.isfile(disc):
        say('no such file: ' + disc)
        return 1
    say('workspace: ' + ROOT)
    progress(1, 'Reading your disc image')
    try:
        if not extract_elf(disc):
            return 1
    except (OSError, ValueError) as e:
        say(str(e))
        return 1
    if args.platform != 'linux':          # Linux interprets VU1 anyway (native-linux.md: its flush-to-zero mode)
        progress(4, 'Translating the graphics programs')
        vu1_translation()
    progress(12, 'Translating the game\'s code to C++')
    program = build(args.platform, args.jobs, 78 if args.godot else 97)
    if not program:
        return 1
    if args.service and args.platform != 'mac':
        set_service(program, args.service)
    progress(80 if args.godot else 97, 'Building the Godot version' if args.godot else 'Making the launcher')
    library = None
    if args.godot:
        try:
            library = godot_library(args.platform, args.jobs)
        except (OSError, subprocess.SubprocessError) as error:
            say('the requested Godot library could not be installed: %s' % error)
        if not library or not os.path.isfile(library):
            say('Godot was requested, but its game library was not installed; the installation is incomplete.')
            say('the native build remains available: ' + program)
            say('the existing Godot library and install record are unchanged; no success or launcher is written.')
            return 1
    os.makedirs(os.path.join(ROOT, 'local'), exist_ok=True)
    with open(os.path.join(ROOT, 'local', 'install.txt'), 'w') as f:
        f.write('disc=%s\nprogram=%s\n' % (disc, program) + ('godot_library=%s\n' % library if library else ''))
    say('built: ' + program)
    if not args.no_launcher:
        desktop = desktop_dir(args.desktop)
        make = {'mac': launcher_mac, 'linux': launcher_linux, 'windows': launcher_windows}[args.platform]
        try:
            where = make(desktop, program, disc, args.launcher_name, args.service)
        except OSError as e:
            where = None
            say('no launcher: %s' % e)
        if where:
            say('launcher: ' + where)
    progress(100, 'Done')
    say('done.  Higher-resolution art is a separate, optional step with your own textures: docs/issues/native-graphics.md, section 3 "The art pack"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
