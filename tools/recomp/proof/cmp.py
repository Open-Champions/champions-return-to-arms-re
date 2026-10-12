#!/usr/bin/env python3
"""cmp.py - tools/recomp/rigcompare.py in a directory of its own.

rigcompare.py keeps its logs, memory card and replay file in one fixed directory, so two
comparisons cannot run side by side and a second one overwrites the first.  This wrapper
runs the same code with another output directory, another native binary and extra watch
columns:

  python3 tools/recomp/proof/cmp.py NAME [--native BIN] [--watch W]... [--chunks LO:HI:STEP]...
          <rigcompare command> [its options]

  NAME          the run; everything goes to local/recomp-out/proof/cmp/NAME/
  --native BIN  the translated game to run (default: rigcompare's)
  --watch W     one more column on both machines, name=expr:type (repeatable)
  --chunks LO:HI:STEP[:PREFIX]
                checksum columns over LO..HI in pieces of STEP bytes (hex), to find where
                a block differs (repeatable)
  --native-arg A
                one more argument for the translated game (repeatable), for instance
                --native-arg --opt --native-arg proof-hits=FILE

Nothing here is game data; what the runs write is, and stays under local/.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import rigcompare                               # noqa: E402

ROOT = rigcompare.ROOT
BASE = os.path.join(ROOT, 'local', 'recomp-out', 'proof', 'cmp')


def setup(name, native=None, watches=(), chunks=(), native_args=()):
    """Point rigcompare at its own directory; returns the directory."""
    out = os.path.join(BASE, name)
    os.makedirs(out, exist_ok=True)
    rigcompare.OUT = out
    if native:
        rigcompare.NATIVE = native
        os.environ['RTA_NATIVE'] = native
    os.environ.setdefault('RTA_NICE', '19')
    extra = list(watches)
    for spec in chunks:
        parts = spec.split(':')
        lo, hi, step = (int(x, 16) for x in parts[:3])
        prefix = parts[3] if len(parts) > 3 else 'c'
        for at in range(lo, hi, step):
            extra.append('%s%06x=0x%x:crc%d' % (prefix, at, at, min(step, hi - at)))
    if native_args:
        real_run = subprocess.run

        def run(command, *args, **kwargs):
            if len(command) > 1 and str(command[1]).endswith('native.py'):
                command = list(command) + list(native_args)
            return real_run(command, *args, **kwargs)
        subprocess.run = run
    original = rigcompare.base_watches
    rigcompare.base_watches = lambda: original() + extra
    return out


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 2
    name, argv = argv[0], argv[1:]
    native, watches, chunks, native_args = None, [], [], []
    while argv and argv[0] in ('--native', '--watch', '--chunks', '--native-arg'):
        if argv[0] == '--native':
            native = os.path.abspath(argv[1])
        elif argv[0] == '--watch':
            watches.append(argv[1])
        elif argv[0] == '--native-arg':
            native_args.append(argv[1])
        else:
            chunks.append(argv[1])
        argv = argv[2:]
    setup(name, native, watches, chunks, native_args)
    sys.argv = [rigcompare.__file__] + argv
    return rigcompare.main()


if __name__ == '__main__':
    sys.exit(main())
