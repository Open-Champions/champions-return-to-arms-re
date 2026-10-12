#!/usr/bin/env python3
"""disc.py - read files out of your own disc image (ISO 9660), for the recompiler.

  python3 tools/recomp/disc.py list                      # every file: sector, size, path
  python3 tools/recomp/disc.py extract BG/LIBINSCK.ERX   # to local/recomp-out/disc/
  python3 tools/recomp/disc.py extract --all '*.ERX'

The image is named by --disc or the environment variable RTA_DISC and is only read.
Whatever is extracted is game data: it goes under local/recomp-out/disc/, never into
docs/ or tools/.
"""
import argparse
import fnmatch
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'local', 'recomp-out', 'disc')
SECTOR = 2048


class Iso:
    def __init__(self, path):
        self.f = open(path, 'rb')
        pvd = self.read(16, 1)
        if pvd[1:6] != b'CD001':
            raise SystemExit('%s is not an ISO 9660 image' % path)
        self.root = self.record(pvd[156:190])

    def read(self, sector, count):
        self.f.seek(sector * SECTOR)
        return self.f.read(count * SECTOR)

    @staticmethod
    def record(raw):
        lba, size = struct.unpack_from('<I4xI', raw, 2)
        flags = raw[25]
        name = raw[33:33 + raw[32]].decode('latin1')
        return {'lba': lba, 'size': size, 'dir': bool(flags & 2), 'name': name}

    def entries(self, directory):
        data = self.read(directory['lba'], (directory['size'] + SECTOR - 1) // SECTOR)
        at = 0
        while at < len(data):
            length = data[at]
            if length == 0:                     # records do not cross sectors
                at = (at // SECTOR + 1) * SECTOR
                continue
            entry = self.record(data[at:at + length])
            at += length
            if entry['name'] in ('\x00', '\x01'):
                continue
            yield entry

    def walk(self, directory=None, prefix=''):
        for entry in self.entries(directory or self.root):
            path = prefix + entry['name'].split(';')[0]
            if entry['dir']:
                yield from self.walk(entry, path + '/')
            else:
                yield path, entry

    def find(self, path):
        want = path.replace('\\', '/').strip('/').upper().split(';')[0]
        for name, entry in self.walk():
            if name.upper() == want:
                return entry
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('list', 'extract'))
    parser.add_argument('names', nargs='*')
    parser.add_argument('--disc', default=os.environ.get('RTA_DISC'))
    parser.add_argument('--all', action='store_true', help='names are patterns; extract every match')
    parser.add_argument('--out', default=OUT)
    args = parser.parse_args()
    if not args.disc:
        raise SystemExit('name the disc image with --disc or RTA_DISC')
    iso = Iso(args.disc)
    if args.command == 'list':
        for name, entry in iso.walk():
            print('%8d %10d %s' % (entry['lba'], entry['size'], name))
        return 0
    wanted = []
    for name in args.names:
        if args.all:
            wanted += [(path, entry) for path, entry in iso.walk()
                       if fnmatch.fnmatch(path.upper(), name.upper()) or fnmatch.fnmatch(os.path.basename(path).upper(), name.upper())]
        else:
            entry = iso.find(name)
            if not entry:
                raise SystemExit('%s is not on the disc' % name)
            wanted.append((name.replace('\\', '/').strip('/').upper(), entry))
    for path, entry in wanted:
        target = os.path.join(args.out, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        iso.f.seek(entry['lba'] * SECTOR)
        with open(target, 'wb') as sink:
            sink.write(iso.f.read(entry['size']))
        print('%s: %d bytes' % (target, entry['size']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
