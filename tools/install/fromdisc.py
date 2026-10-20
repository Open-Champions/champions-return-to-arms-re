#!/usr/bin/env python3
"""fromdisc.py - build the native game from YOUR OWN disc image, on this computer.

  python3 tools/install/fromdisc.py --platform mac|linux|windows --disc "/path/to/your image.iso"
          [--desktop DIR] [--no-launcher] [--jobs N]

The step the three installers (install-mac.command, install-linux.sh, install-windows.ps1)
share once their toolchain is in place.  The game's code is never distributed: it is
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
     tools/godot/build_lib_linux.py on Linux) from the same translation, put where the Godot
     application looks for it (tools/godot/project/gamelib.gd): macOS ~/Library/Application Support/
     Open Champions/RTA Godot/, Linux ~/.local/share/open-champions/rta-godot/.  The Godot application
     itself holds only our code; this library is the game, made here, and stays on this computer.

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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APP = os.path.join(ROOT, 'tools', 'recomp', 'app')
OUT = os.path.join(ROOT, 'local', 'recomp-out')
ELF_NAME = 'SLUS_209.73'
ELF_CRC = 0x4028A55F          # PCSX2's figure for the executable: the XOR of its 32-bit words
SECTOR = 2048


def say(text):
    print('[install] ' + text, flush=True)


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


# ---- the build --------------------------------------------------------------------------------
def run(command):
    say('running: ' + ' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in command))
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


def build(target, jobs):
    py = sys.executable
    if target == 'mac':
        ok = run([py, os.path.join(APP, 'build.py')] + (['--qt', os.environ['RTA_QT']] if os.environ.get('RTA_QT') else []))
        program = os.path.join(OUT, 'bin', 'rta_app')
    elif target == 'linux':
        ok = run([py, os.path.join(APP, 'build_linux.py'), '--jobs', str(jobs)])
        arch = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'aarch64': 'aarch64', 'arm64': 'aarch64'}.get(platform.machine().lower(), platform.machine())
        program = os.path.join(OUT, 'linux', 'rta-linux-' + arch, 'rta_app')
    else:
        ok = run([py, os.path.join(APP, 'build_win.py'), '--jobs', str(jobs)])
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
    else:
        say('the Godot application\'s game library is not made for %s yet (docs/issues/native-godot.md); the native program is' % target)
        return None
    for step in steps:
        say('running: ' + ' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in step))
        if subprocess.run(step, cwd=ROOT, env=env).returncode != 0:
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


def launcher_mac(desktop, program, disc):
    app = os.path.join(desktop, 'Champions RTA Native.app')
    macos = os.path.join(app, 'Contents', 'MacOS')
    os.makedirs(macos, exist_ok=True)
    plist = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
             '<plist version="1.0"><dict>\n'
             '<key>CFBundleExecutable</key><string>launch</string>\n'
             '<key>CFBundleIdentifier</key><string>org.open-champions.rta-native-launcher</string>\n'
             '<key>CFBundleName</key><string>Champions RTA Native</string>\n'
             '<key>CFBundlePackageType</key><string>APPL</string>\n'
             '<key>LSMinimumSystemVersion</key><string>13.0</string>\n'
             '</dict></plist>\n')
    open(os.path.join(app, 'Contents', 'Info.plist'), 'w').write(plist)
    script = os.path.join(macos, 'launch')
    q = lambda s: "'" + s.replace("'", "'\\''") + "'"
    open(script, 'w').write('#!/bin/sh\n# made by tools/install/fromdisc.py: the native build of this workspace with your disc image\n'
                            'mkdir -p %s\nexec %s --disc %s "$@" > %s 2>&1\n'
                            % (q(os.path.join(OUT, 'app-data')), q(program), q(disc), q(os.path.join(OUT, 'app-data', 'rta_app-log.txt'))))
    os.chmod(script, 0o755)
    return app


def launcher_linux(desktop, program, disc):
    folder = os.path.dirname(program)
    exec_line = '"%s" "%s"' % (os.path.join(folder, 'play.sh'), disc)
    entry = ('[Desktop Entry]\nType=Application\nName=Champions RTA Native\n'
             'Comment=The native build of Champions: Return to Arms, made from your own disc\n'
             'Exec=%s\nPath=%s\nTerminal=false\nCategories=Game;\n' % (exec_line, folder))
    made = []
    apps = os.path.join(os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share')), 'applications')
    for d in (apps, desktop):
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, 'rta-native.desktop')
            open(path, 'w').write(entry)
            os.chmod(path, 0o755)
            made.append(path)
        except OSError as e:
            say('no launcher in %s: %s' % (d, e))
    if made and made[-1].startswith(desktop) and shutil.which('gio'):
        # GNOME asks once before it starts a launcher it has not been told to trust
        subprocess.run(['gio', 'set', made[-1], 'metadata::trusted', 'true'], capture_output=True)
    return made[-1] if made else None


def launcher_windows(desktop, program, disc):
    # a shortcut through the Windows Script Host (no extra module): rta_app.exe --disc "<image>"
    link = os.path.join(desktop, 'Champions RTA Native.lnk')
    ps = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\'%s\'); $s.TargetPath = \'%s\'; '
          '$s.Arguments = \'--disc "%s"\'; $s.WorkingDirectory = \'%s\'; $s.Save()'
          % (link.replace("'", "''"), program.replace("'", "''"), disc.replace("'", "''"), os.path.dirname(program).replace("'", "''")))
    ok = subprocess.run(['powershell', '-NoProfile', '-Command', ps]).returncode == 0
    return link if ok else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--platform', choices=('mac', 'linux', 'windows'), required=True)
    parser.add_argument('--disc', required=True, help='your own disc image of Champions: Return to Arms (SLUS-20973, v2.00)')
    parser.add_argument('--desktop', help='where the launcher goes (default: this user\'s desktop)')
    parser.add_argument('--no-launcher', action='store_true')
    parser.add_argument('--godot', action='store_true', help='also the game library of the Godot application (tools/godot)')
    parser.add_argument('--jobs', type=int, default=max(1, min(8, os.cpu_count() or 4)))
    args = parser.parse_args()
    disc = os.path.abspath(os.path.expanduser(args.disc))
    if not os.path.isfile(disc):
        say('no such file: ' + disc)
        return 1
    say('workspace: ' + ROOT)
    try:
        if not extract_elf(disc):
            return 1
    except (OSError, ValueError) as e:
        say(str(e))
        return 1
    if args.platform != 'linux':          # Linux interprets VU1 anyway (native-linux.md: its flush-to-zero mode)
        vu1_translation()
    program = build(args.platform, args.jobs)
    if not program:
        return 1
    library = godot_library(args.platform, args.jobs) if args.godot else None
    os.makedirs(os.path.join(ROOT, 'local'), exist_ok=True)
    with open(os.path.join(ROOT, 'local', 'install.txt'), 'w') as f:
        f.write('disc=%s\nprogram=%s\n' % (disc, program) + ('godot_library=%s\n' % library if library else ''))
    say('built: ' + program)
    if not args.no_launcher:
        desktop = desktop_dir(args.desktop)
        make = {'mac': launcher_mac, 'linux': launcher_linux, 'windows': launcher_windows}[args.platform]
        try:
            where = make(desktop, program, disc)
        except OSError as e:
            where = None
            say('no launcher: %s' % e)
        if where:
            say('launcher: ' + where)
    say('done.  Higher-resolution art is a separate, optional step with your own textures: docs/issues/native-graphics.md, section 3 "The art pack"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
