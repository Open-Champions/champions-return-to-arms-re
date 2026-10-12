#!/usr/bin/env python3
"""rigcompare.py - the translated game against the original, frame for frame.

The original runs in the headless rig (tools/rig, the Play! emulator core) from one of its
saved machine states.  At the head of the session loop the rig writes out main memory, the
scratchpad and the registers; the translated game (local/recomp-out/bin/rta_native) is
started from that image and both run on, with no input, logging the same values once per
displayed frame at the same code address (the entry of gfx_beginFrame).

  python3 tools/recomp/rigcompare.py snapshot --state local/rig-out/states/04-hub.zip
  python3 tools/recomp/rigcompare.py run      [--frames 2000]
  python3 tools/recomp/rigcompare.py compare
  python3 tools/recomp/rigcompare.py memdiff

Everything it writes (memory images are game data) goes to local/recomp-out/rig/.
Needs the disc image (RTA_DISC) for the rig.  Nothing here modifies the rig.
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'local', 'recomp-out', 'rig')
NATIVE = os.path.join(ROOT, 'local', 'recomp-out', 'bin', 'rta_native')
LOOP_HEAD = 0x322B48            # head of the session loop in mainloop_runSession
FRAME_HOOK = 0x19D8B0           # gfx_beginFrame: called once per displayed frame
G_NETFRAME = 0x4027AC           # unused offline; the rig keys its in-tick commands on it
PLAYERS = 0x4D8AF0

REGS = ('at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 '
        'gp sp fp ra').split()


def watches():
    """name=expression:type, numbers only, so that the rig and the runtime read them alike."""
    obj = '[0x%x]' % (PLAYERS + 0x43D8)
    rec = lambda off: '0x%x' % (PLAYERS + off)
    return [
        'sim=0x44fdcc:u32', 'seed=0x404464:x32', 'cosmetic=0x404460:x32', 'draw=0x44fdd0:u32',
        'net=0x%x:s32' % G_NETFRAME, 'level=0x41b721:str12', 'nplayers=0x4d8ae0:s32',
        'p0x=%s+0x10:x32' % obj, 'p0y=%s+0x14:x32' % obj, 'p0z=%s+0x18:x32' % obj,
        'p0angle=%s+0x38:u16' % obj, 'p0state=%s+0x58c:s32' % obj, 'p0objseed=%s+0x44:x32' % obj,
        'p0hp=%s:x32' % rec(0xAC), 'p0mana=%s:x32' % rec(0xC0), 'p0gold=%s:s32' % rec(0xE4),
        'p0exp=%s:s32' % rec(0x5C), 'p0bag0=%s:crc4612' % rec(0x130), 'p0stats=%s:crc84' % rec(0x58),
        'p0equip=%s:crc80' % rec(0x43F0), 'p0abil=%s:crc1560' % rec(0x4440),
        'p0skills=%s:crc192' % rec(0x4B08),
        # the whole player record, the whole object pool (every creature, item, projectile...),
        # the task table and the controller state
        'record0=%s:crc19504' % rec(0), 'pool=0x5f88c0:crc947968', 'tasks=0x840100:crc1024',
        'pads=0x41bfd8:crc256',
    ]


def rig(args, script_lines, tick_at, log=None, with_watches=True):
    disc = os.environ.get('RTA_DISC')
    if not disc:
        raise SystemExit('set RTA_DISC to the disc image')
    os.makedirs(OUT, exist_ok=True)
    script = os.path.join(OUT, 'script.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(script_lines) + '\n')
    command = ['nice', '-n', '19', sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'rig.py'),
               '--data', os.path.join(OUT, 'data'), '--tick-at', '0x%x' % tick_at, '--script', script] + args
    if log:
        command += ['--tick-log', log]
    if with_watches:
        for watch in watches():
            command += ['--tick-watch', watch]
    start = time.time()
    done = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    text = done.stdout + done.stderr
    return text, time.time() - start


def snapshot(args):
    ram, spr = os.path.join(OUT, 'image-ram.bin'), os.path.join(OUT, 'image-spr.bin')
    lines = ['ontick 1 dump 0 0x2000000 %s' % ram, 'ontick 1 dump 0x70000000 0x4000 %s' % spr,
             'ontick 1 show ' + ' '.join('$%s:u8' % r for r in REGS), 'wait 4']
    text, _ = rig(['--load', args.state, '--frames', '5'], lines, LOOP_HEAD, with_watches=False)
    found = dict(re.findall(r'\$(\w+)@([0-9a-f]{8})=', text))
    if len(found) != len(REGS):
        print(text[-2000:])
        raise SystemExit('the rig did not report the registers (is g_netFrame 1 in this state?)')
    with open(os.path.join(OUT, 'image-regs.txt'), 'w') as sink:
        for name in REGS:
            sink.write('%s %s\n' % (name, found[name]))
    with open(os.path.join(OUT, 'state.txt'), 'w') as sink:
        sink.write(args.state + '\n')
    print('image written: %s (%d bytes), registers of the main thread at 0x%x' % (ram, os.path.getsize(ram), LOOP_HEAD))


def run(args):
    with open(os.path.join(OUT, 'state.txt')) as source:
        state = source.read().strip()
    watch_file = os.path.join(OUT, 'watch.txt')
    with open(watch_file, 'w') as sink:
        sink.write('\n'.join(watches()) + '\n')
    rig_log, native_log = os.path.join(OUT, 'rig.tsv'), os.path.join(OUT, 'native.tsv')
    rig_end, native_end = os.path.join(OUT, 'rig-end.bin'), os.path.join(OUT, 'native-end.bin')
    for path in (rig_log, native_log, rig_end, native_end):
        if os.path.exists(path):
            os.remove(path)
    # the rig: log every frame; at the first frame after `frames` write out memory.  Its
    # in-tick commands are keyed on g_netFrame, which is 1 and unused offline: poking 77
    # into it arms the dump for the next frame.
    first = None
    lines = ['ontick 77 dump 0 0x2000000 %s' % rig_end,
             'until 0x44fdcc:u32 changed timeout 600',
             'wait %d' % args.frames, 'poke 0x%x:s32 77' % G_NETFRAME, 'wait 4']
    text, rig_wall = rig(['--load', state, '--frames', str(args.frames + 400)], lines, FRAME_HOOK, log=rig_log)
    speed = re.search(r'frames=(\d+) wall=([\d.]+)s fps=([\d.]+)', text)
    print('rig: %s' % (speed.group(0) if speed else text[-400:]))
    rows = [line.rstrip('\n').split('\t') for line in open(rig_log)]
    header, rows = rows[0], rows[1:]
    net = header.index('net')
    dump_row = next((i for i, row in enumerate(rows) if row[net] == '77'), None)
    if dump_row is None:
        raise SystemExit('the rig never reached the dump frame')
    print('rig: %d frames logged; memory written at row %d' % (len(rows), dump_row))
    command = ['nice', '-n', '19', NATIVE, 'resume', '--ram', os.path.join(OUT, 'image-ram.bin'),
               '--spr', os.path.join(OUT, 'image-spr.bin'), '--regs', os.path.join(OUT, 'image-regs.txt'),
               '--entry', '%x' % LOOP_HEAD, '--frames', str(dump_row + 2), '--watch-file', watch_file,
               '--log', native_log, '--dump-at', str(dump_row), native_end]
    start = time.time()
    done = subprocess.run(command, capture_output=True, text=True)
    with open(os.path.join(OUT, 'native.out'), 'w') as sink:
        sink.write(done.stdout + done.stderr)
    for line in (done.stdout + done.stderr).splitlines():
        if line.startswith(('frames=', 'rta_native', 'resumed', 'renderer', 'VU0')):
            print('native: ' + line)
    print('native: %.1f s wall' % (time.time() - start))
    return compare(args)


def compare(args):
    logs = []
    for name in ('rig.tsv', 'native.tsv'):
        rows = [line.rstrip('\n').split('\t') for line in open(os.path.join(OUT, name))]
        logs.append(rows)
    (head_a, *rows_a), (head_b, *rows_b) = logs
    if head_a[1:] != head_b[1:]:
        raise SystemExit('the two logs have different columns')
    count = min(len(rows_a), len(rows_b))
    first = {}
    for index in range(count):
        for column in range(1, len(head_a)):
            if rows_a[index][column] != rows_b[index][column] and head_a[column] not in first:
                first[head_a[column]] = index
    print('frames compared: %d (rig %d, translation %d); columns: %d' % (count, len(rows_a), len(rows_b), len(head_a) - 1))
    sim = head_a.index('sim')
    print('simulation ticks %s..%s' % (rows_a[0][sim], rows_a[count - 1][sim]))
    same = [name for name in head_a[1:] if name not in first]
    print('identical in every frame: %s' % (', '.join(same) or 'none'))
    for name, index in sorted(first.items(), key=lambda kv: kv[1]):
        column = head_a.index(name)
        differing = sum(1 for i in range(count) if rows_a[i][column] != rows_b[i][column])
        print('DIFFERENT %-10s first at frame %d (tick %s): rig %s, translation %s; %d of %d frames differ' % (
            name, index, rows_a[index][sim], rows_a[index][column], rows_b[index][column], differing, count))
    return 1 if first else 0


def memdiff(args):
    with open(os.path.join(OUT, 'rig-end.bin'), 'rb') as source:
        a = source.read()
    with open(os.path.join(OUT, 'native-end.bin'), 'rb') as source:
        b = source.read()
    with open(os.path.join(OUT, 'image-ram.bin'), 'rb') as source:
        start = source.read()
    regions = [(0x0, 0x100000, 'kernel area (thread contexts, kernel stack, tables)'),
               (0x100000, 0x3E5C40, 'code'), (0x3E5C40, 0x564380, 'data sections'),
               (0x564380, 0x5F88C0, 'bss below the object pool'), (0x5F88C0, 0x6E0000, 'object pool'),
               (0x6E0000, 0x90A440, 'bss above the object pool (render lists, caches, buffers)'),
               (0x90A440, 0x1F00000, 'heap'), (0x1F00000, 0x2000000, 'stacks')]
    total = changed_a = 0
    print('%-62s %10s %10s %10s' % ('region', 'bytes', 'changed', 'differ'))
    for lo, hi, name in regions:
        differ = sum(1 for i in range(lo, hi) if a[i] != b[i]) if a[lo:hi] != b[lo:hi] else 0
        changed = sum(1 for i in range(lo, hi) if a[i] != start[i]) if a[lo:hi] != start[lo:hi] else 0
        total += differ
        changed_a += changed
        print('%-62s %10d %10d %10d' % ('%s  %06x-%06x' % (name, lo, hi), hi - lo, changed, differ))
    print('bytes the original changed since the image: %d; bytes that differ between the two at the end: %d' % (changed_a, total))
    # where the differences are, by 4 KB page, largest first
    pages = {}
    for page in range(0, len(a), 4096):
        if a[page:page + 4096] != b[page:page + 4096]:
            pages[page] = sum(1 for i in range(page, page + 4096) if a[i] != b[i])
    names = []
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(
            os.path.join(ROOT, 'symbols', n) for n in os.listdir(os.path.join(ROOT, 'symbols')) if n.endswith('.tsv')):
        for line in open(path):
            parts = line.split('\t')
            if len(parts) >= 2 and not line.startswith('#'):
                try:
                    names.append((int(parts[0], 16), parts[1]))
                except ValueError:
                    pass
    names.sort()
    import bisect
    keys = [n[0] for n in names]

    def symbol(addr):
        i = bisect.bisect_right(keys, addr) - 1
        return '%s+0x%x' % (names[i][1], addr - names[i][0]) if i >= 0 else '?'

    print('pages with differences: %d' % len(pages))
    runs = []
    for page in sorted(pages):
        if runs and runs[-1][1] == page:
            runs[-1][1] = page + 4096
            runs[-1][2] += pages[page]
        else:
            runs.append([page, page + 4096, pages[page]])
    for lo, hi, count in sorted(runs, key=lambda r: -r[2])[:args.top]:
        first = next(i for i in range(lo, hi) if a[i] != b[i])
        print('  %06x-%06x  %7d bytes differ  (first at %06x, %s)' % (lo, hi, count, first, symbol(first)))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snapshot')
    p.add_argument('--state', default=os.path.join(ROOT, 'local', 'rig-out', 'states', '04-hub.zip'))
    p = sub.add_parser('run')
    p.add_argument('--frames', type=int, default=2000)
    sub.add_parser('compare')
    p = sub.add_parser('memdiff')
    p.add_argument('--top', type=int, default=25)
    args = parser.parse_args()
    return {'snapshot': snapshot, 'run': run, 'compare': compare, 'memdiff': memdiff}[args.command](args) or 0


if __name__ == '__main__':
    sys.exit(main())
