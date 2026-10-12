#!/usr/bin/env python3
"""emuref.py - run a rig script on the playable emulator build and keep its sound.

The emulator rig (tools/rig) has no sound output; the playable build (tools/play-net) can
write what its sound chip mixes to a WAV file.  This runs the playable build as a silent
background test run, offline, with a new data directory, drives it through its control
socket with the commands of a rig script, and leaves the WAV in the data directory - the
reference the native sound library's output is compared with (sndcmp).

  python3 -I -B tools/recomp/sound/emuref.py --disc IMAGE --data local/sound/emuref/run1 \\
      --script local/sound/cap/capture.rig [--label "TEXT for the window title"]

Script commands understood (tools/rig/README.md): at, wait, tap, tapuntil, until, press,
release, stick, poke, show; conditions on u8/u16/u32/s32/strN values with == != < <= > >=.
Symbols come from names.tsv and symbols/*.tsv.  A log of what was done at which frame is
written to <data>/emuref.log.

The WAV is game audio: keep the data directory under local/ and delete it after use.
Standard library only.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'play-net'))


def symbols():
    table = {}
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        with open(path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                fields = line.rstrip('\n').split('\t')
                if len(fields) >= 2 and not line.startswith('#'):
                    try:
                        table.setdefault(fields[1], int(fields[0], 16))
                    except ValueError:
                        pass
    return table


class Driver:
    def __init__(self, control, table, log):
        self.control, self.table, self.log = control, table, log

    def frame(self):
        answer = self.control.ok('info')
        m = re.search(r'frame=(\d+)', answer)
        return int(m.group(1)) if m else -1

    def note(self, text):
        line = '[frame %d] %s' % (self.frame(), text)
        print(line, flush=True)
        self.log.write(line + '\n')
        self.log.flush()

    def expression(self, text):
        return re.sub(r'[A-Za-z_][A-Za-z_0-9]*', lambda m: '0x%x' % self.table[m.group(0)] if m.group(0) in self.table else m.group(0), text)

    def value(self, watch):
        expr, kind = watch.rsplit(':', 1)
        answer = self.control.ok('peek %s %s' % (self.expression(expr), kind))
        return answer.strip()

    def holds(self, watch, op, wanted):
        got = self.value(watch)
        if watch.rsplit(':', 1)[1].startswith('str'):
            a, b = got, wanted
        else:
            a, b = int(got, 0), int(wanted, 0)
        return {'==': a == b, '!=': a != b, '<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b}[op]

    def wait(self, frames):
        while frames > 0:
            step = min(frames, 120)
            self.control.ok('wait %d' % step)
            frames -= step

    def run(self, line):
        words = line.split('#')[0].split()
        if not words:
            return
        command = words[0]
        if command == 'at':
            self.wait(int(words[1]) - self.frame())
        elif command == 'wait':
            self.wait(int(words[1]))
        elif command == 'tap':
            hold = int(words[2]) if len(words) > 2 else 3
            gap = int(words[3]) if len(words) > 3 else 0
            self.control.ok('tap %s %d %d' % (words[1], hold, gap))
        elif command in ('press', 'release'):
            self.control.ok('%s %s' % (command, words[1]))
        elif command == 'stick':
            self.control.ok('stick %s %s %s' % (words[1].lower(), words[2], words[3]))
        elif command == 'poke':
            expr, kind = words[1].rsplit(':', 1)
            self.control.ok('poke %s %s %s' % (self.expression(expr), 'u32' if kind in ('f32', 'x32', 's32') else kind, words[2]))
            self.note(line.strip())
        elif command in ('until', 'tapuntil'):
            rest = words[1:]
            button = period = None
            if command == 'tapuntil':
                button, period, rest = rest[0], int(rest[1]), rest[2:]
            watch, op, wanted = rest[0], rest[1], rest[2]
            timeout = int(rest[rest.index('timeout') + 1]) if 'timeout' in rest else 3000
            start = self.frame()
            while not self.holds(watch, op, wanted):
                if self.frame() - start > timeout:
                    self.note('TIMED OUT: ' + line.strip())
                    raise SystemExit(3)
                if button:
                    self.control.ok('tap %s 4 %d' % (button, max(period - 4, 0)))
                else:
                    self.wait(5)
            self.note(line.strip())
        elif command == 'show':
            self.note(' '.join('%s=%s' % (w, self.value(w)) for w in words[1:]))
        else:
            raise SystemExit('emuref: command not understood: ' + line.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--disc', required=True)
    parser.add_argument('--data', required=True, help='a NEW directory under local/ (settings, memory card, the WAV)')
    parser.add_argument('--script', required=True)
    parser.add_argument('--label', default='sound reference run - silent, no network')
    parser.add_argument('--tail', type=int, default=120, help='frames to let pass after the script')
    args = parser.parse_args()
    from ctl import Control
    data = os.path.abspath(args.data)
    if os.path.exists(data):
        raise SystemExit('emuref: %s exists; give a new directory' % data)
    os.makedirs(data)
    socket_path = os.path.join('/tmp', 'rta-emuref-%d.sock' % os.getpid())
    command = [os.path.join(ROOT, 'tools', 'play-net', 'play.sh'), '--disc', args.disc, '--data', data, '--sections', 'none',
               '--', '--rta-test', args.label, '--rta-sound-wav', '--rta-no-net', '--rta-control', socket_path]
    app = subprocess.Popen(command, stdout=open(os.path.join(data, 'app.out'), 'w'), stderr=subprocess.STDOUT)
    try:
        for _ in range(600):
            if os.path.exists(socket_path) or app.poll() is not None:
                break
            time.sleep(0.1)
        if not os.path.exists(socket_path):
            raise SystemExit('emuref: the application did not open its control socket (see %s/app.out)' % data)
        control = Control(socket_path, timeout=600)
        with open(os.path.join(data, 'emuref.log'), 'w') as log:
            driver = Driver(control, symbols(), log)
            with open(args.script) as script:
                for line in script:
                    driver.run(line)
            driver.wait(args.tail)
            driver.note('end; ' + control.ok('sound'))
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
    wavs = glob.glob(os.path.join(data, 'sound-*.wav'))
    print('wav: ' + (wavs[0] if wavs else 'none written'))


if __name__ == '__main__':
    main()
