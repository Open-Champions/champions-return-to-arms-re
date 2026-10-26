#!/usr/bin/env python3
"""build_setups.py - "Champions Setup" for macOS, Windows and Linux: one file each that a player double-clicks.

  python3 tools/install/setup/build_setups.py [--platform mac,windows,linux] [--out DIR] [--service HOST:PORT]
          [--ref REV] [--godot-mac APP] [--godot-linux DIR] [--godot-windows DIR] [--no-godot]
  python3 tools/install/setup/build_setups.py --check FILE ...     # only the proof below, for setups made earlier

What a setup holds - and what it never holds:
  * our source code: the repository's files (git ls-files of this folder as it is, tracked and new but not ignored;
    --ref REV: `git archive REV` instead). The whitelist .gitignore keeps everything made from the game out of it;
  * the setup's own program: mac/main.swift + mac/setup-mac.sh, windows/stub.c + windows/setup-windows.ps1,
    linux/setup-linux.sh;
  * the Godot version as exported by tools/godot/build.py export (our code only, no game library), macOS, Linux and
    Windows (RtaGodot.exe, RtaGodot.pck and the extension's DLL; the setup builds the game library on the player's PC with
    tools/godot/build_lib_win.py, through fromdisc.py --godot);
  * with --service: setup.ini, "service = HOST:PORT" (the room service its programs use). The address is given by
    whoever builds the setup to hand it out; it is never in the repository.
  NEVER a disc image, the game's executable, a translation of it, a game library or program built from it, or any of
  the game's data: each player's setup reads the player's own disc image on the player's own computer. Every setup
  made here is checked for that (the proof, below) before it is written, and the list of its contents is written
  beside it (NAME.contents.txt).

The proof: every file in the setup, also inside the archives in it (zip, tar.gz), is checked for
  - names: *.iso, SLUS_209.73, librta_game*, rta_app*, rta_native*, objects (*.o), the translation's files (c_NNN.cpp,
    gen-app/, gen-vu/, funcs.h, vu1_fast.cpp) (the look presets, project/presets/levels.cfg, are our own numbers: allowed);
  - size: nothing over 300 MB (the Godot program for macOS, two processors in one, is 160 MB; a disc image 4 GB);
  - content: an ISO 9660 volume descriptor ("CD001" at 32769), a MIPS ELF header (the PS2's executables), the text
    of the translated code (the head of each translated function, the first line recomp.py writes into its files), the
    name of the game's first function (fn_ and its address: in the translation and in a program built from it), the
    translation's table of the game's functions as it is in a program built from it (also when stripped), and, when SLUS_209.73 is at the top of this folder, 32 pieces of 64 bytes from its code.

Made in --out (default local/dist-setups/; nothing of it belongs in the repository):
  Champions-Setup-Mac.zip       "Champions Setup.app", signed ad hoc (swiftc for arm64 and x86_64)
  Champions-Setup-Windows.exe   the program of windows/stub.c (MinGW-w64, x86-64) with its archive appended
  Champions-Setup-Linux.sh      linux/setup-linux.sh with its archive (tar.gz) appended, and
  Champions-Setup-Linux.zip     the same in a zip (it stays executable after a download)
Tools: Apple's swiftc and codesign, Homebrew's mingw-w64 (x86_64-w64-mingw32-gcc, -windres), git. Nothing is downloaded.
"""
import argparse
import io
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
GODOT_MAC = os.path.join(ROOT, 'local', 'godot-r7', 'export', 'macos', 'RtaGodot.app')
GODOT_LINUX = os.path.join(ROOT, 'local', 'godot-r7', 'export')
GODOT_WINDOWS = os.path.join(ROOT, 'local', 'godot-r9', 'export', 'windows')
TRAILER = b'CHSETUP1'


def say(text):
    print('[setups] ' + text, flush=True)


# ---- what goes in: the source code ------------------------------------------------------------------------------------
def source_id(ref):
    """SOURCE_ID: the commit the setup's source is (tools/recomp/app/buildid.py reads it where there is no git)."""
    rev = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', ref or 'HEAD'], capture_output=True, text=True).stdout.strip() or 'unknown'
    if not ref and subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', 'HEAD', '--'], capture_output=True).returncode != 0:
        rev += '+'
    return ('SOURCE_ID', (rev + ' (the source this setup was made from: tools/install/setup/build_setups.py)\n').encode(), 0o644)


def source_files(ref):
    """(path in the archive, bytes, mode) of the repository's files, and SOURCE_ID."""
    return [f for f in source_files_only(ref) if f[0] != 'SOURCE_ID'] + [source_id(ref)]


def source_files_only(ref):
    if ref:
        data = subprocess.run(['git', '-C', ROOT, 'archive', '--format=tar', ref], capture_output=True, check=True).stdout
        out = []
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                if m.isfile():
                    out.append((m.name, t.extractfile(m).read(), m.mode))
        return out
    names = subprocess.run(['git', '-C', ROOT, 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                           capture_output=True, check=True).stdout.split(b'\0')
    out = []
    for raw in names:
        name = raw.decode('utf-8')
        path = os.path.join(ROOT, name)
        if not name or not os.path.isfile(path) or os.path.islink(path):
            continue
        out.append((name, open(path, 'rb').read(), os.stat(path).st_mode & 0o777))
    return out


def source_tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz', compresslevel=9) as t:
        for name, data, mode in sorted(files):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode | 0o644, int(time.time())
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def source_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data, mode in sorted(files):
            z.writestr(name, data)
    return buf.getvalue()


def setup_ini(service):
    return ('# setup.ini - written by build_setups.py for this copy of the setup\nservice = %s\n' % service).encode() if service else None


# ---- the proof: nothing of the game ----------------------------------------------------------------------------------
BAD_NAMES = re.compile(r'(\.iso$|^slus_209\.73$|^librta_game|^rta_(app|native)[^.]*(\.exe)?$|\.o$|^c_\d{3}\.cpp$|^funcs\.h$|^vu1_fast\.cpp$)', re.I)
CODE_MARK = b'static void ' + b'body_00'                  # every function of the translation (split: not to find itself)
PROGRAM_MARK = b'fn_' + b'00100000'                       # the game's first function: in the translation's table and in every
                                                           # program or library built from it that keeps its symbols
# the translation's table of the game's functions, {address, function} at 16 bytes a row, as it is in a program or
# library built from it, stripped or not: its first three rows are the game's functions at 0x100000, ...08, ...10
TABLE_MARK = re.compile(rb'\x00\x00\x10\x00.{12}\x08\x00\x10\x00.{12}\x10\x00\x10\x00', re.S)
FILE_MARK = b'// generated by tools/recomp/' + b'recomp.py from the game executable'
BAD_DIRS = ('gen-app/', 'gen-vu/', 'gen-orig/', 'gen/', 'recomp-out/', 'godot-spike/', 'godot-install/')


def game_pieces():
    """32 pieces of 64 bytes from the code of the game's executable, when it is at the top of this folder."""
    path = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(path):
        return []
    data = open(path, 'rb').read()
    if data[:4] != b'\x7fELF':
        return []
    phoff, = struct.unpack_from('<I', data, 28)
    phnum, = struct.unpack_from('<H', data, 44)
    pieces = []
    for i in range(phnum):
        kind, offset, _, _, filesz = struct.unpack_from('<IIIII', data, phoff + 32 * i)
        if kind == 1 and filesz > 65536:
            for k in range(32):
                at = offset + 4096 + k * ((filesz - 8192) // 32)
                piece = data[at:at + 64]
                if len(set(piece)) > 12:          # not a run of zeros or padding
                    pieces.append(piece)
            break
    return pieces


class Proof:
    def __init__(self):
        self.pieces = game_pieces()
        self.lines, self.problems, self.files, self.bytes = [], [], 0, 0

    def look(self, where, data):
        """One file: name, size, content; archives are opened and their members looked at too."""
        self.files += 1
        self.bytes += len(data)
        self.lines.append('%12d  %s' % (len(data), where))
        base = where.rstrip('/').split('/')[-1].split('!')[-1]
        if BAD_NAMES.search(base):
            self.problems.append('a name of the game\'s files: ' + where)
        low = where.lower()
        if any('/' + d in '/' + low.split('!')[-1] for d in BAD_DIRS):
            self.problems.append('a folder of the translation: ' + where)
        if len(data) > 300 * 1048576:
            self.problems.append('over 300 MB (a disc image?): ' + where)
        if len(data) > 32775 and data[32769:32774] == b'CD001':
            self.problems.append('an ISO 9660 disc image: ' + where)
        at = data.find(b'\x7fELF\x01\x01\x01')
        while at >= 0:
            if data[at + 18:at + 20] == b'\x08\x00':
                self.problems.append('a MIPS executable (the PS2\'s) inside: %s at %d' % (where, at))
                break
            at = data.find(b'\x7fELF\x01\x01\x01', at + 1)
        if CODE_MARK in data:
            self.problems.append('translated game code: ' + where)
        if PROGRAM_MARK in data:
            self.problems.append('the translation\'s function names (a game program or library?): ' + where)
        if TABLE_MARK.search(data):
            self.problems.append('the translation\'s table of the game\'s functions (a game program or library): ' + where)
        if data.startswith(FILE_MARK):
            self.problems.append('a translated file: ' + where)
        for piece in self.pieces:
            if piece in data:
                self.problems.append('a piece of the game\'s executable: ' + where)
                break
        # archives inside
        mark = data.find(b'\n__CHAMPIONS_ARCHIVE_BELOW__\n') if data[:2] == b'#!' else -1
        if mark >= 0:
            self.look(where + '!<archive at the end>', data[mark + 29:])
        elif data[:4] == b'PK\x03\x04' or (where.endswith('.exe') and TRAILER in data[-16:]):
            body = data
            if data[-16:-8] == TRAILER:
                size, = struct.unpack('<Q', data[-8:])
                body = data[-16 - size:-16]
                self.lines.append('%12d  %s!<archive at the end>' % (len(body), where))
            try:
                with zipfile.ZipFile(io.BytesIO(body)) as z:
                    for info in z.infolist():
                        if not info.is_dir():
                            self.look(where + '!' + info.filename, z.read(info))
            except zipfile.BadZipFile:
                if where.endswith('.zip'):
                    self.problems.append('a damaged zip: ' + where)
        elif data[:2] == b'\x1f\x8b':
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
                    for m in t.getmembers():
                        if m.isfile():
                            self.look(where + '!' + m.name, t.extractfile(m).read())
            except tarfile.TarError:
                pass

    def look_tree(self, top, prefix):
        for folder, dirs, files in os.walk(top):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(folder, name)
                if os.path.islink(path):
                    self.lines.append('%12s  %s -> %s' % ('link', prefix + os.path.relpath(path, top), os.readlink(path)))
                    continue
                self.look(prefix + os.path.relpath(path, top), open(path, 'rb').read())

    def report(self, name, out_dir):
        listing = os.path.join(out_dir, name + '.contents.txt')
        with open(listing, 'w') as f:
            f.write('%s: %d files, %d bytes (unpacked), checked %s\n' % (name, self.files, self.bytes, time.strftime('%Y-%m-%d %H:%M')))
            f.write('checked for: disc images, MIPS executables, translated code, the game\'s file names, files over 300 MB%s\n'
                    % (', %d pieces of SLUS_209.73' % len(self.pieces) if self.pieces else ''))
            f.write('result: %s\n\n' % ('NOT CLEAN: ' + '; '.join(self.problems) if self.problems else 'nothing of the game'))
            f.write('\n'.join(self.lines) + '\n')
        return listing


def prove(path, name, out_dir):
    proof = Proof()
    if os.path.isdir(path):
        proof.look_tree(path, name + '/')
    else:
        proof.look(name, open(path, 'rb').read())
    listing = proof.report(name, out_dir)
    say('%s: %d files checked%s; %s; list: %s' % (name, proof.files, ' (with %d pieces of the game\'s code)' % len(proof.pieces) if proof.pieces else '',
                                               'NOT CLEAN' if proof.problems else 'nothing of the game', os.path.relpath(listing, ROOT)))
    for p in proof.problems[:20]:
        say('  ' + p)
    return not proof.problems


# ---- macOS --------------------------------------------------------------------------------------------------------------
INFO_PLIST = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Champions Setup</string>
<key>CFBundleIdentifier</key><string>org.open-champions.champions-setup</string>
<key>CFBundleName</key><string>Champions Setup</string>
<key>CFBundleDisplayName</key><string>Champions Setup</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleVersion</key><string>%s</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSDownloadsFolderUsageDescription</key><string>Champions Setup looks for your disc image of Champions: Return to Arms in Downloads. It is only read, never sent anywhere.</string>
<key>NSDesktopFolderUsageDescription</key><string>Champions Setup looks for your disc image of Champions: Return to Arms on the desktop and puts Champions there. The disc image is only read.</string>
<key>NSDocumentsFolderUsageDescription</key><string>Champions Setup looks for your disc image of Champions: Return to Arms in Documents. It is only read, never sent anywhere.</string>
<key>NSRemovableVolumesUsageDescription</key><string>Champions Setup looks for your disc image of Champions: Return to Arms on your drives. It is only read, never sent anywhere.</string>
<key>NSNetworkVolumesUsageDescription</key><string>Champions Setup looks for your disc image of Champions: Return to Arms on your drives. It is only read, never sent anywhere.</string>
</dict></plist>
'''


def build_mac(out, files, ini, godot, work):
    app = os.path.join(work, 'Champions Setup.app')
    macos, res = os.path.join(app, 'Contents', 'MacOS'), os.path.join(app, 'Contents', 'Resources')
    os.makedirs(macos)
    os.makedirs(res)
    parts = []
    for arch in ('arm64', 'x86_64'):
        part = os.path.join(work, 'setup-' + arch)
        r = subprocess.run(['swiftc', '-O', '-target', '%s-apple-macos13.0' % arch, os.path.join(HERE, 'mac', 'main.swift'), '-o', part],
                           capture_output=True, text=True)
        if r.returncode != 0:
            say('swiftc (%s) failed:\n%s' % (arch, r.stderr[-3000:]))
            return None
        parts.append(part)
    subprocess.run(['lipo', '-create'] + parts + ['-output', os.path.join(macos, 'Champions Setup')], check=True)
    open(os.path.join(app, 'Contents', 'Info.plist'), 'w').write(INFO_PLIST % time.strftime('%Y%m%d%H%M'))
    shutil.copy2(os.path.join(HERE, 'mac', 'setup-mac.sh'), os.path.join(res, 'setup-mac.sh'))
    os.chmod(os.path.join(res, 'setup-mac.sh'), 0o755)
    open(os.path.join(res, 'source.tar.gz'), 'wb').write(source_tar(files))
    if ini:
        open(os.path.join(res, 'setup.ini'), 'wb').write(ini)
    if godot:
        if not os.path.isdir(godot):
            say('no Godot export at %s (tools/godot/build.py export): the Mac setup is made without the Godot version' % godot)
        else:
            subprocess.run(['ditto', godot, os.path.join(res, 'RtaGodot.app')], check=True)
    subprocess.run(['xattr', '-cr', app])
    r = subprocess.run(['codesign', '--force', '--deep', '-s', '-', app], capture_output=True, text=True)
    if r.returncode != 0:
        say('codesign: ' + r.stderr.strip())
        return None
    subprocess.run(['codesign', '--verify', '--deep', '--strict', app], check=True)
    if not prove(app, 'Champions Setup.app', out):
        return None
    final = os.path.join(out, 'Champions-Setup-Mac.zip')
    if os.path.exists(final):
        os.remove(final)
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, final + '.part'], check=True)
    os.replace(final + '.part', final)
    return final


# ---- Windows --------------------------------------------------------------------------------------------------------
def build_windows(out, files, ini, godot, work):
    src = os.path.join(HERE, 'windows')
    res = os.path.join(work, 'setup-res.o')
    stub = os.path.join(work, 'stub.exe')
    for command in (['x86_64-w64-mingw32-windres', '-I', src, os.path.join(src, 'setup.rc'), '-O', 'coff', '-o', res],
                    ['x86_64-w64-mingw32-gcc', '-O2', '-municode', '-mwindows', '-Wall', '-o', stub, os.path.join(src, 'stub.c'), res,
                     '-lshell32', '-lole32', '-luuid', '-s']):
        r = subprocess.run(command, capture_output=True, text=True, cwd=src)
        if r.returncode != 0:
            say('%s failed:\n%s' % (command[0], (r.stdout + r.stderr)[-3000:]))
            return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('setup-windows.ps1', open(os.path.join(src, 'setup-windows.ps1'), 'rb').read())
        z.writestr('source.zip', source_zip(files))
        if ini:
            z.writestr('setup.ini', ini)
        if godot:
            # the Godot version (our application, no game inside): setup-windows.ps1 asks fromdisc.py for its game library
            # when godot/RtaGodot.pck is in the payload, and puts the three files beside it into place
            names = sorted(os.listdir(godot)) if os.path.isdir(godot) else []
            if 'RtaGodot.exe' not in names or 'RtaGodot.pck' not in names:
                say('no Godot export for Windows at %s (tools/godot/build.py extension --release --platform windows; export --platform windows): '
                    'the Windows setup is made without the Godot version' % godot)
            else:
                for name in names:
                    path = os.path.join(godot, name)
                    if os.path.isfile(path):
                        z.write(path, 'godot/' + name)
                say('the Godot version for Windows: %s' % ', '.join(names))
    payload = buf.getvalue()
    final = os.path.join(out, 'Champions-Setup-Windows.exe')
    with open(final + '.part', 'wb') as f:
        f.write(open(stub, 'rb').read())
        f.write(payload)
        f.write(TRAILER + struct.pack('<Q', len(payload)))
    if not prove(final + '.part', 'Champions-Setup-Windows.exe', out):
        os.remove(final + '.part')
        return None
    os.replace(final + '.part', final)
    return final


# ---- Linux --------------------------------------------------------------------------------------------------------------
def build_linux(out, files, ini, godot, work):
    stage = os.path.join(work, 'linux')
    os.makedirs(stage)
    open(os.path.join(stage, 'source.tar.gz'), 'wb').write(source_tar(files))
    if ini:
        open(os.path.join(stage, 'setup.ini'), 'wb').write(ini)
    if godot:
        for arch, theirs in (('x86_64', 'x86_64'), ('aarch64', 'arm64')):
            folder = os.path.join(godot, 'linux-' + theirs)
            exe = os.path.join(folder, 'RtaGodot.' + theirs)
            if not os.path.exists(exe):
                say('no Godot export for Linux %s at %s: left out' % (arch, folder))
                continue
            to = os.path.join(stage, 'godot-' + arch)
            os.makedirs(to)
            for name in os.listdir(folder):
                # the executable named for the setup's processor names; Godot finds RtaGodot.pck by the part before the dot
                shutil.copy2(os.path.join(folder, name), os.path.join(to, 'RtaGodot.' + arch if name == 'RtaGodot.' + theirs else name))
    if not prove(stage, 'Champions-Setup-Linux', out):
        return None
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz', compresslevel=9) as t:
        for folder, dirs, names in os.walk(stage):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(folder, name)
                t.add(path, arcname=os.path.relpath(path, stage))
    header = open(os.path.join(HERE, 'linux', 'setup-linux.sh'), 'rb').read()
    if not header.endswith(b'\n__CHAMPIONS_ARCHIVE_BELOW__\n'):
        say('linux/setup-linux.sh must end with the line __CHAMPIONS_ARCHIVE_BELOW__')
        return None
    final = os.path.join(out, 'Champions-Setup-Linux.sh')
    with open(final + '.part', 'wb') as f:
        f.write(header)
        f.write(buf.getvalue())
    os.chmod(final + '.part', 0o755)
    os.replace(final + '.part', final)
    # the same in a zip, for a download: the zip keeps the file executable (a browser's download does not), and a
    # browser offers a .zip for saving where it may show a .sh as text
    zipped = os.path.join(out, 'Champions-Setup-Linux.zip')
    info = zipfile.ZipInfo('Champions-Setup-Linux.sh', date_time=time.localtime()[:6])
    info.external_attr = (stat.S_IFREG | 0o755) << 16
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED            # the archive in it is compressed already
    with zipfile.ZipFile(zipped + '.part', 'w') as z:
        z.writestr(info, open(final, 'rb').read())
    os.replace(zipped + '.part', zipped)
    return zipped


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--platform', default='mac,windows,linux')
    parser.add_argument('--out', default=os.path.join(ROOT, 'local', 'dist-setups'))
    parser.add_argument('--service', default='', help='HOST:PORT of the room service, written into setup.ini')
    parser.add_argument('--ref', default='', help='take the source code from this git revision (default: this folder as it is)')
    parser.add_argument('--godot-mac', default=GODOT_MAC)
    parser.add_argument('--godot-linux', default=GODOT_LINUX)
    parser.add_argument('--godot-windows', default=GODOT_WINDOWS)
    parser.add_argument('--no-godot', action='store_true')
    parser.add_argument('--check', nargs='+', metavar='FILE', help='only the proof, for setups made earlier')
    args = parser.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    if args.check:
        ok = all([prove(os.path.abspath(p), os.path.basename(p.rstrip('/')), out) for p in args.check])
        return 0 if ok else 1
    if args.service and not re.match(r'^[A-Za-z0-9.-]+:\d{1,5}$', args.service):
        parser.error('--service must be HOST:PORT')
    files = source_files(args.ref)
    bad = [n for n, _, _ in files if BAD_NAMES.search(n.split('/')[-1])]
    if bad:
        say('the source code has files it must not have: ' + ', '.join(bad[:10]))
        return 1
    say('source code: %d files (%s), %.1f MB' % (len(files), args.ref or 'this folder as it is', sum(len(d) for _, d, _ in files) / 1048576.0))
    ini = setup_ini(args.service)
    work = tempfile.mkdtemp(prefix='champions-setups-')
    made, failed = [], []
    try:
        for platform_ in [p.strip() for p in args.platform.split(',') if p.strip()]:
            folder = os.path.join(work, platform_)
            os.makedirs(folder)
            if platform_ == 'mac':
                result = build_mac(out, files, ini, None if args.no_godot else args.godot_mac, folder)
            elif platform_ == 'windows':
                result = build_windows(out, files, ini, None if args.no_godot else args.godot_windows, folder)
            elif platform_ == 'linux':
                result = build_linux(out, files, ini, None if args.no_godot else args.godot_linux, folder)
            else:
                parser.error('unknown platform ' + platform_)
            (made if result else failed).append(result or platform_)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for path in made:
        say('made %s (%.1f MB)' % (os.path.relpath(path, ROOT), os.path.getsize(path) / 1048576.0))
    for name in failed:
        say('NOT made: ' + name)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
