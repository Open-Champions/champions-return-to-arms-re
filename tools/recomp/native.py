#!/usr/bin/env python3
"""native.py - run the translated game (local/recomp-out/bin/rta_native) with the usual options.

  export RTA_DISC="/path/to/your/disc image.iso"
  python3 tools/recomp/native.py boot --script tools/rig/examples/boot-to-hub.rig
  python3 tools/recomp/native.py boot --card local/recomp-out/card --fields 3000 --log out.tsv --watch g_simFrame:u32

Adds what every run needs and passes the rest on: `--elf` (the executable beside the
repository's symbol files), `--disc` (from RTA_DISC), one `--sym` per symbol file
(names.tsv, symbols/*.tsv) so that names can be used in scripts and watches, and, unless
given, `--card local/recomp-out/card`.  RTA_NATIVE names another binary.  The process is
started at low priority (nice 10; RTA_NICE names another value).  Exit codes are the program's: 0 done, 2 bad option, 3 a script
condition timed out or the program stopped on something it cannot do, 4 --seconds ended.
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return 2
    binary = os.environ.get('RTA_NATIVE', os.path.join(ROOT, 'local', 'recomp-out', 'bin', 'rta_native'))
    command = ['nice', '-n', os.environ.get('RTA_NICE', '10'), binary, args[0]]
    rest = args[1:]
    if args[0] == 'boot' and '--elf' not in rest:
        command += ['--elf', os.path.join(ROOT, 'SLUS_209.73')]
    if '--disc' not in rest:
        disc = os.environ.get('RTA_DISC')
        if not disc and args[0] == 'boot':
            raise SystemExit('name the disc image with --disc or RTA_DISC')
        if disc:
            command += ['--disc', disc]
    if '--card' not in rest:
        command += ['--card', os.path.join(ROOT, 'local', 'recomp-out', 'card')]
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        if os.path.exists(path):
            command += ['--sym', path]
    os.execvp(command[0], command + rest)


if __name__ == '__main__':
    sys.exit(main())
