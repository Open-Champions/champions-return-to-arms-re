#!/usr/bin/env python3
"""build_online.py - the native game with its network: a headless program for the lobby path.

  python3 tools/recomp/net/build_online.py            # local/recomp-out/bin/rta_native_online
  options: --opt -O1|-O2   --jobs N
           --pnach FILE --sections FILE   the fix set (defaults: the suggested set, as rta_app)
           --signin FILE      the local sign-in patch (default local/SLUS-20973_4028A55F_signin.pnach,
                              used when it is there; --signin none: without)
           --name NAME        gen-NAME, obj-NAME, bin/NAME (default rta_native_online)

The translation is the one rta_app is built from - the executable with the suggested fix
set - with two additions: the addresses of tools/recomp/net/hle-online.txt are left to the
network driver (recomp.py --hle-add), and the local sign-in patch, a file kept outside the
repository, is applied when present (recomp.py --extra-pnach; nothing of it is printed or
copied).  Without that patch the game stops after "Internet Game" at its sign-in step, whose
servers are gone.  Linked: the runtime as it is (tools/recomp/rt), the driver
(net/netdrv.cpp), the one-step online (net/online.cpp with tools/play-net/src/RtaOnline.cpp).
Everything written goes to local/recomp-out/.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
SIGNIN = os.path.join(ROOT, 'local', 'SLUS-20973_4028A55F_signin.pnach')
SOURCES = [os.path.join(HERE, 'netdrv.cpp'), os.path.join(HERE, 'online.cpp'),
           os.path.join(ROOT, 'tools', 'play-net', 'src', 'RtaOnline.cpp')]


def translation_options(pnach, sections, signin):
    """What recomp.py is given for a translation that can go online (also used by app/build.py)."""
    options = ['--pnach', pnach, '--sections', sections, '--hle-add', os.path.join(HERE, 'hle-online.txt')]
    if signin and signin != 'none' and os.path.isfile(signin):
        options += ['--extra-pnach', signin]
    return options


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--jobs', type=int)
    parser.add_argument('--pnach', default=os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach'))
    parser.add_argument('--sections', default=os.path.join(ROOT, 'tools', 'play-net', 'sections-suggested.txt'))
    parser.add_argument('--signin', default=SIGNIN)
    parser.add_argument('--name', default='rta_native_online')
    args = parser.parse_args()
    gen = os.path.join(OUT, 'gen-' + args.name.replace('rta_native_', ''))
    if args.signin != 'none' and not os.path.isfile(args.signin):
        print('no sign-in patch at %s: the game will stop with a network error after "Internet Game"' % args.signin)
    result = subprocess.run([sys.executable, os.path.join(RECOMP, 'recomp.py'), '--out', gen] +
                            translation_options(args.pnach, args.sections, args.signin), capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-3000:] + result.stderr[-3000:])
        return result.returncode
    for line in result.stdout.splitlines():
        if line.startswith(('patched', 'warning', 'entangled', 'instructions emitted as rt_unimpl')):
            print('recomp: ' + line)
    command = [sys.executable, os.path.join(RECOMP, 'build.py'), 'run', '--gen', gen, '--name', args.name, '--opt=' + args.opt]
    if args.jobs:
        command += ['--jobs', str(args.jobs)]
    for source in SOURCES:
        command += ['--extra', source]
    return subprocess.run(command).returncode


if __name__ == '__main__':
    sys.exit(main())
