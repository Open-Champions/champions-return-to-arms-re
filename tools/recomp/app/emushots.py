#!/usr/bin/env python3
"""emushots.py - reference pictures for the native application from the emulator build.

Runs the playable emulator build (tools/play-net) as a silent background test run,
offline, with a new data directory, drives it through its control socket with the same
script the native application is given, and where the script says `app shot FILE.png` it
asks the emulator for the picture as the machine drew it (`shotfb`, the console's
640 x 448 times the emulator's resolution factor) into DIR/<name of FILE>.

  python3 -I -B tools/recomp/app/emushots.py --disc IMAGE --data local/recomp-out/app-test/emu1 \\
      --script local/recomp-out/app-test/boot-shots.rig --out local/recomp-out/app-test/emu-shots

Other `app ...` lines, `echo`, `dump` and `quit` are passed over.  The script language and the
driver are those of tools/recomp/sound/emuref.py.  Pictures are game output: under local/
only.  Standard library only.
"""
import argparse
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'play-net'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recomp', 'sound'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--disc', required=True)
    parser.add_argument('--data', required=True, help='a NEW directory under local/ (settings, memory card)')
    parser.add_argument('--script', required=True)
    parser.add_argument('--out', required=True, help='directory for the pictures (.bmp)')
    parser.add_argument('--label', default='reference pictures for the native app - silent, no network')
    args = parser.parse_args()
    from ctl import Control
    from emuref import Driver, symbols
    data = os.path.abspath(args.data)
    if os.path.exists(data):
        raise SystemExit('emushots: %s exists; give a new directory' % data)
    os.makedirs(data)
    os.makedirs(args.out, exist_ok=True)
    socket_path = os.path.join('/tmp', 'rta-emushots-%d.sock' % os.getpid())
    command = [os.path.join(ROOT, 'tools', 'play-net', 'play.sh'), '--disc', args.disc, '--data', data, '--sections', 'none',
               '--', '--rta-test', args.label, '--rta-no-net', '--rta-control', socket_path]
    app = subprocess.Popen(command, stdout=open(os.path.join(data, 'app.out'), 'w'), stderr=subprocess.STDOUT)
    try:
        for _ in range(600):
            if os.path.exists(socket_path) or app.poll() is not None:
                break
            time.sleep(0.1)
        if not os.path.exists(socket_path):
            raise SystemExit('emushots: the application did not open its control socket (see %s/app.out)' % data)
        control = Control(socket_path, timeout=600)
        with open(os.path.join(data, 'emushots.log'), 'w') as log:
            driver = Driver(control, symbols(), log)
            with open(args.script) as script:
                for line in script:
                    words = line.split('#')[0].split()
                    if not words or words[0] in ('echo', 'sync', 'dump'):
                        continue
                    if words[0] == 'quit':
                        break
                    if words[0] == 'app':
                        if len(words) >= 3 and words[1] == 'shot':
                            name = os.path.splitext(os.path.basename(words[2]))[0] + '.bmp'
                            answer = control.send('shotfb ' + os.path.abspath(os.path.join(args.out, name)))
                            driver.note('shotfb %s: %s' % (name, answer))
                        continue
                    if words[0] == 'pad':
                        # the whole state of port 1 at once: buttons, then the left and right stick
                        control.ok('release all')
                        if len(words) > 1 and words[1] != 'none':
                            control.ok('press ' + words[1])
                        axes = [int(v) for v in words[2:6]] + [128] * 4
                        control.ok('stick l %d %d' % (axes[0], axes[1]))
                        control.ok('stick r %d %d' % (axes[2], axes[3]))
                        continue
                    if words[0] == 'poke' and len(words) >= 3 and ':' in words[1]:
                        # the control socket takes a number for a 32-bit word: a hex pattern
                        # (x32) and a float (f32) are handed over as that number
                        expr, kind = words[1].rsplit(':', 1)
                        if kind == 'x32':
                            line = 'poke %s:u32 %d' % (expr, int(words[2], 16))
                        elif kind == 'f32':
                            line = 'poke %s:u32 %d' % (expr, struct.unpack('<I', struct.pack('<f', float(words[2])))[0])
                    driver.run(line)
        control.close()
    finally:
        # ask the application's own thread to close the window, then make sure
        with open(socket_path + '.ui', 'w') as handle:
            handle.write('close\n')
        try:
            app.wait(timeout=20)
        except subprocess.TimeoutExpired:
            app.terminate()
        for leftover in (socket_path, socket_path + '.ui'):
            if os.path.exists(leftover):
                os.remove(leftover)
    return 0


if __name__ == '__main__':
    sys.exit(main())
