#!/usr/bin/env python3
"""Original run functions vs ref_own_machines.step, one tick at a time.

Usage: python3 tools/difftest_own_machines.py local/SLUS_209.73 [Class ...]

The class run function executes in tools/ee_emu.py with every callee stubbed.
The slot-27 requests, the decision calls and (where the tick stores one) the
final timer words are compared with the reference. Stubbed callees; not a
running game. Existing round-2 and round-3 vectors are not modified.
"""
import sys
import own_exec
import ref_own_machines as M

# (class, state, ctx). Defaults match Exec.tick: clock 1000, timer 0, queue 1.
CASES = []


def add(name, state, ctx=None):
    CASES.append((name, state, dict(ctx or {})))


def _suite():
    F = 5000
    # Gnaw
    add('Gnaw', 0, {'seen': 1})
    add('Gnaw', 0, {})
    add('Gnaw', 0, {'away': 1})
    add('Gnaw', 1, {'seen': 1})
    add('Gnaw', 1, {})
    add('Gnaw', 3, {})
    add('Gnaw', 3, {'target': 1, 'see': 1})
    add('Gnaw', 3, {'target': 1, 'seq': {'see': [0, 1]}})
    add('Gnaw', 3, {'target': 1, 'seq': {'see': [0, 0]}})
    add('Gnaw', 5, {'target': 1, 'see': 1})
    add('Gnaw', 5, {'target': 1, 'seq': {'see': [0, 1]}})
    add('Gnaw', 5, {'target': 1, 'seq': {'see': [0, 0]}})
    add('Gnaw', 5, {'target': 1, 'rooted': 1, 'seq': {'see': [0, 0]}})
    add('Gnaw', 6, {'target': 1, 'anim': 8})
    add('Gnaw', 6, {'target': 1, 'anim': 0, 'events': 1})
    add('Gnaw', 0x10, {'ready': 1})
    add('Gnaw', 0x10, {})
    add('Gnaw', 0x12, {'anim': 0x10})
    add('Gnaw', 0x12, {})
    add('Gnaw', 0x13, {})
    add('Gnaw', 0x13, {'stunned': 1})
    add('Gnaw', 0x14, {})
    add('Gnaw', 7, {})
    # Skelight
    add('Skelight', 0, {'seen': 1})
    add('Skelight', 0, {'away': 1})
    add('Skelight', 0, {})
    add('Skelight', 1, {'seen': 1})
    add('Skelight', 1, {})
    add('Skelight', 3, {})
    add('Skelight', 3, {'target': 1, 'see': 1})
    add('Skelight', 3, {'target': 1, 'seq': {'see': [0, 1]}})
    add('Skelight', 3, {'target': 1})
    add('Skelight', 5, {'target': 1, 'see': 1})
    add('Skelight', 5, {'target': 1})
    add('Skelight', 5, {'target': 1, 'rooted': 1})
    add('Skelight', 6, {'target': 1, 'anim': 8, 'timer': 5})
    add('Skelight', 6, {'target': 1, 'anim': 0, 'timer': 5, 'events': 1})
    add('Skelight', 6, {'target': 1, 'anim': 0, 'timer': 1, 'events': 1})
    add('Skelight', 6, {'anim': 0, 'timer': 5})
    add('Skelight', 6, {'anim': 8, 'timer': 0})
    add('Skelight', 6, {'anim': 0, 'timer': 0})
    add('Skelight', 0x10, {'ready': 1})
    add('Skelight', 0x10, {})
    add('Skelight', 0x12, {})
    add('Skelight', 0x13, {})
    add('Skelight', 0x13, {'stunned': 1})
    add('Skelight', 0x14, {})
    add('Skelight', 0x17, {'anim': 0x80})
    add('Skelight', 0x17, {})
    add('Skelight', 7, {})
    # GnomeNavigator
    add('GnomeNavigator', 0, {'cflags': 0x400000, 'clock': 1000, 'timer': 0})
    add('GnomeNavigator', 0, {'cflags': 0x800000, 'away': 1, 'clock': 100, 'timer': F})
    add('GnomeNavigator', 0, {'cflags': 0xc00000, 'away': 0, 'clock': 100, 'timer': F})
    add('GnomeNavigator', 0, {'clock': 1000, 'timer': 0, 'away': 1})
    add('GnomeNavigator', 1, {'arrived': 1, 'clock': 100, 'timer': F})
    add('GnomeNavigator', 1, {'arrived': 0, 'clock': 1000, 'timer': 0})
    add('GnomeNavigator', 1, {'arrived': 0, 'clock': 100, 'timer': F})
    add('GnomeNavigator', 3, {})
    add('GnomeNavigator', 3, {'target': 1})
    add('GnomeNavigator', 5, {})
    add('GnomeNavigator', 5, {'rooted': 1})
    add('GnomeNavigator', 0x13, {})
    add('GnomeNavigator', 0x13, {'stunned': 1})
    add('GnomeNavigator', 0x14, {})
    add('GnomeNavigator', 6, {})
    add('GnomeNavigator', 0x12, {})
    # Mermaid
    add('Mermaid', 0, {'clock': 1000, 'timer': 0})
    add('Mermaid', 0, {'clock': 100, 'timer': F})
    add('Mermaid', 1, {'clock': 1000, 'timer': 0})
    add('Mermaid', 1, {'clock': 100, 'timer': F, 'arrived': 1})
    add('Mermaid', 3, {})
    add('Mermaid', 3, {'target': 1})
    add('Mermaid', 5, {})
    add('Mermaid', 5, {'rooted': 1})
    add('Mermaid', 0x12, {'anim': 0})
    add('Mermaid', 0x12, {'anim': 0x10})
    add('Mermaid', 0x14, {'anim': 0x80})
    add('Mermaid', 0x14, {})
    add('Mermaid', 0x13, {})
    add('Mermaid', 2, {})
    # Natasla / NPC
    add('Natasla', 0, {})
    add('Natasla', 1, {'seen': 1, 'away': 1, 'target': 1})
    add('Natasla', 0x14, {})
    add('NPC', 0, {'cflags': 0x8000000})
    add('NPC', 0, {})
    add('NPC', 1, {})
    add('NPC', 3, {'target': 1, 'seen': 1})
    # Critter
    add('Critter', 0, {'move': 1, 'clock': 1000, 'timer': 0})
    add('Critter', 0, {'move': 1, 'clock': 100, 'timer': F})
    add('Critter', 0, {'move': 1, 'clock': 1000, 'timer': 0, 'anim': 8})
    add('Critter', 0, {'move': 1, 'away': 1, 'clock': 100, 'timer': F})
    add('Critter', 0, {'clock': 1000, 'timer': 0})
    add('Critter', 0, {'fidget_a': 1, 'move': 1, 'clock': 1000, 'fid_time': 0, 'timer': F})
    add('Critter', 0, {'fidget_a': 1, 'fidget_b': 1, 'move': 1, 'clock': 1000,
                       'fid_time': 0, 'timer': F, 'rand': 1})
    add('Critter', 0, {'class_flags': 0x10, 'move': 1, 'clock': 1000, 'timer': 0})
    add('Critter', 0, {'class_flags': 0x10, 'move': 1, 'clock': 100, 'timer': F})
    add('Critter', 0, {'fidget_a': 1, 'move': 1, 'clock': 1000, 'fid_time': 0, 'timer': 0})
    add('Critter', 1, {'idle': 1, 'arrived': 1, 'clock': 100, 'timer': F})
    add('Critter', 1, {'arrived': 1, 'clock': 100, 'timer': F})
    add('Critter', 1, {'idle': 1, 'clock': 1000, 'timer': 0})
    add('Critter', 1, {'idle': 1, 'anim': 8, 'clock': 1000, 'timer': 0})
    add('Critter', 1, {'class_flags': 2, 'arrived': 1, 'clock': 100, 'timer': F})
    add('Critter', 1, {'idle': 1, 'class_flags': 8, 'arrived': 1, 'clock': 100, 'timer': F})
    add('Critter', 1, {'idle': 1, 'class_flags': 8, 'clock': 1000, 'timer': 0})
    add('Critter', 1, {'idle': 1, 'clock': 100, 'timer': F})
    add('Critter', 1, {'class_flags': 0x10, 'idle': 1, 'clock': 1000, 'timer': 0})
    add('Critter', 0x10, {'idle': 1})
    add('Critter', 0x10, {})
    add('Critter', 0x10, {'target': 1, 'flee_clip': 1, 'clock': 100, 'timer': F})
    add('Critter', 0x10, {'target': 1, 'flee_clip': 1, 'idle': 1, 'clock': 1000, 'timer': 0})
    add('Critter', 0x14, {})
    add('Critter', 0x16, {'path': 1})
    add('Critter', 0x16, {})
    add('Critter', 0x16, {'path': 1, 'snap': 1})
    add('Critter', 0x17, {'fidget_a': 1, 'clock': 1000, 'fid_time': 0})
    add('Critter', 7, {})
    # AntQueen
    add('AntQueen', 0, {'seen': 1, 'queue': 1, 'clock': 100, 'timer': F})
    add('AntQueen', 0, {'seen': 0, 'queue': 1, 'clock': 100, 'timer': F})
    add('AntQueen', 0, {'queue': 1, 'clock': 100, 'timer': F, 'seq': {'v25': [0, 1]}})
    add('AntQueen', 0, {'seen': 1, 'queue': 4, 'clock': 100, 'timer': F})
    add('AntQueen', 0, {'seen': 0, 'queue': 4, 'clock': 1000, 'timer': 0})
    add('AntQueen', 1, {'seen': 1})
    add('AntQueen', 1, {})
    add('AntQueen', 3, {})
    add('AntQueen', 3, {'target': 1, 'rand': 0, 'enemy': 1, 'flight': F, 'clock': 100})
    add('AntQueen', 3, {'target': 1, 'rand': 0, 'enemy': 0, 'flight': F, 'clock': 100})
    add('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 1, 'flight': F, 'clock': 100})
    add('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 0, 'flight': F, 'clock': 100})
    add('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 0, 'flight': 0, 'clock': 1000, 'queue': 1})
    add('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 0, 'flight': 0, 'clock': 1000, 'queue': 4})
    add('AntQueen', 5, {'target': 1, 'rand': 0, 'enemy': 1})
    add('AntQueen', 5, {'target': 1, 'rand': 1, 'see': 1})
    add('AntQueen', 5, {'rand': 1, 'see': 0})
    add('AntQueen', 5, {'rand': 1, 'see': 0, 'rooted': 1})
    add('AntQueen', 5, {'rand': 0, 'enemy': 0})
    add('AntQueen', 5, {'target': 1, 'rand': 0, 'enemy': 0})
    add('AntQueen', 6, {'target': 1, 'anim': 8, 'events': 0})
    add('AntQueen', 6, {'target': 1, 'anim': 8, 'events': 1})
    add('AntQueen', 6, {'target': 1, 'anim': 0})
    add('AntQueen', 7, {'anim': 8, 'events': 1})
    add('AntQueen', 7, {'anim': 0})
    add('AntQueen', 7, {'anim': 0, 'events': 1})
    add('AntQueen', 8, {'flight': F, 'clock': 100})
    add('AntQueen', 8, {'target': 1, 'anim': 8, 'flight': F, 'clock': 100})
    add('AntQueen', 8, {'target': 1, 'anim': 0, 'see': 1, 'flight': F, 'clock': 100, 'rand': 0})
    add('AntQueen', 8, {'target': 1, 'anim': 0, 'see': 1, 'flight': F, 'clock': 100, 'rand': 1})
    add('AntQueen', 8, {'target': 1, 'anim': 0, 'see': 0, 'flight': F, 'clock': 100})
    add('AntQueen', 8, {'target': 1, 'anim': 0, 'flight': 0, 'clock': 1000})
    add('AntQueen', 9, {'target': 1, 'anim': 8, 'events': 1})
    add('AntQueen', 9, {'target': 1, 'anim': 0})
    add('AntQueen', 10, {'target': 1, 'anim': 0, 'events': 1})
    add('AntQueen', 10, {'target': 1, 'anim': 8})
    add('AntQueen', 0x12, {'anim': 0x10})
    add('AntQueen', 0x12, {'anim': 0, 'queue': 1})
    add('AntQueen', 0x12, {'anim': 0, 'queue': 4})
    add('AntQueen', 0x13, {})
    add('AntQueen', 0x13, {'stunned': 1})
    add('AntQueen', 0x14, {})
    add('AntQueen', 0x17, {})
    add('AntQueen', 0x17, {'target': 1, 'anim': 8, 'flight': F, 'clock': 100})
    add('AntQueen', 0x17, {'target': 1, 'anim': 0, 'flight': F, 'clock': 100})
    add('AntQueen', 0x17, {'target': 1, 'anim': 0, 'flight': F, 'clock': 100, 'arrived': 1})
    add('AntQueen', 0x17, {'target': 1, 'anim': 0, 'flight': F, 'clock': 100, 'stuck': 31})
    add('AntQueen', 0x17, {'target': 1, 'anim': 0, 'flight': F, 'clock': 100, 'stuck': 30})
    add('AntQueen', 0x17, {'target': 1, 'anim': 0, 'flight': 0, 'clock': 1000, 'see': 1})
    add('AntQueen', 0x17, {'target': 1, 'anim': 0, 'flight': 0, 'clock': 1000, 'see': 0})
    add('AntQueen', 0x18, {'anim': 8})
    add('AntQueen', 0x18, {'anim': 0, 'queue': 1})
    add('AntQueen', 0x18, {'anim': 0, 'queue': 4})
    add('AntQueen', 0x19, {'target': 1, 'clock': 1000, 'timer': 1120, 'queue': 1})
    add('AntQueen', 0x19, {'target': 1, 'clock': 1000, 'timer': 0, 'queue': 1})
    add('AntQueen', 0x19, {'target': 1, 'clock': 100, 'timer': F, 'queue': 1})
    add('AntQueen', 0x10, {})
    add('AntQueen', 2, {})
    # Skeleton
    add('Skeleton', 0, {'seen': 1, 'clock': 100, 'timer': F})
    add('Skeleton', 0, {'clock': 100, 'timer': F})
    add('Skeleton', 0, {'away': 1, 'clock': 100, 'timer': F})
    add('Skeleton', 0, {'clock': 1000, 'timer': 0})
    add('Skeleton', 0, {'kind': 4, 'seen': 1, 'clock': 100, 'timer': F})
    add('Skeleton', 0, {'kind': 4, 'clock': 100, 'timer': F})
    add('Skeleton', 0, {'kind': 4, 'seq': {'v25': [0, 1]}, 'clock': 100, 'timer': F})
    add('Skeleton', 1, {'seen': 1})
    add('Skeleton', 1, {'clock': 1000, 'timer': 0})
    add('Skeleton', 1, {'clock': 100, 'timer': F})
    add('Skeleton', 1, {'kind': 4, 'clock': 100, 'timer': F})
    add('Skeleton', 3, {})
    add('Skeleton', 3, {'target': 1, 'see': 1})
    add('Skeleton', 3, {'target': 1, 'seq': {'see': [0, 1]}})
    add('Skeleton', 3, {'target': 1, 'ally': 1, 'rand': 7})
    add('Skeleton', 3, {'target': 1})
    add('Skeleton', 3, {'kind': 4, 'target': 1, 'see': 1})
    add('Skeleton', 3, {'kind': 4, 'target': 1, 'seq': {'see': [0, 1]}})
    add('Skeleton', 3, {'kind': 4, 'target': 1})
    add('Skeleton', 5, {'target': 1, 'see': 1})
    add('Skeleton', 5, {'target': 1, 'clock': 1000, 'timer': 0})
    add('Skeleton', 5, {'target': 1, 'clock': 100, 'timer': F, 'ally': 1})
    add('Skeleton', 5, {'target': 1, 'clock': 100, 'timer': F, 'ally': 0})
    add('Skeleton', 5, {'clock': 100, 'timer': F})
    add('Skeleton', 5, {'target': 1, 'rooted': 1, 'clock': 1000, 'timer': 0})
    add('Skeleton', 5, {'kind': 4, 'target': 1, 'see': 1})
    add('Skeleton', 6, {'target': 1, 'anim': 8, 'timer': 5})
    add('Skeleton', 6, {'target': 1, 'anim': 0, 'timer': 5, 'events': 1})
    add('Skeleton', 6, {'target': 1, 'anim': 0, 'timer': 1, 'events': 1})
    add('Skeleton', 6, {'target': 1, 'anim': 8, 'timer': 1, 'events': 1})
    add('Skeleton', 8, {'anim': 8, 'timer': 5})
    add('Skeleton', 8, {'anim': 0, 'timer': 5})
    add('Skeleton', 8, {'anim': 0, 'timer': 1})
    add('Skeleton', 8, {'target': 1, 'anim': 8, 'timer': 5, 'events': 0})
    add('Skeleton', 8, {'target': 1, 'anim': 0, 'timer': 1})
    add('Skeleton', 0x10, {'ready': 1})
    add('Skeleton', 0x10, {})
    add('Skeleton', 0x11, {'clock': 1000, 'timer': 0})
    add('Skeleton', 0x11, {'clock': 100, 'timer': F})
    add('Skeleton', 0x12, {'anim': 0})
    add('Skeleton', 0x12, {'anim': 0x10})
    add('Skeleton', 0x13, {})
    add('Skeleton', 0x14, {})
    add('Skeleton', 0x17, {'anim': 0})
    add('Skeleton', 0x17, {'anim': 0x10})
    add('Skeleton', 7, {})
    # Soul
    add('Soul', 0, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': F})
    add('Soul', 0, {'frame': 0, 'demon': 0, 'clock': 100, 'timer': F})
    add('Soul', 0, {'frame': 1, 'clock': 100, 'timer': F, 'away': 1})
    add('Soul', 0, {'frame': 1, 'clock': 1000, 'timer': 0})
    add('Soul', 0, {'frame': 1, 'clock': 100, 'timer': F})
    add('Soul', 0, {'owner': 1, 'frame': 0, 'demon': 1, 'clock': 100, 'timer': F})
    add('Soul', 1, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': F})
    add('Soul', 1, {'frame': 1, 'arrived': 1, 'clock': 100, 'timer': F})
    add('Soul', 1, {'frame': 1, 'clock': 1000, 'timer': 0})
    add('Soul', 1, {'frame': 1, 'clock': 100, 'timer': F})
    add('Soul', 0x18, {'frame': 0, 'demon': 0, 'clock': 100, 'timer': F})
    add('Soul', 0x18, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': F})
    add('Soul', 0x18, {'frame': 1, 'demon': 0, 'clock': 100, 'timer': F})
    add('Soul', 3, {})
    add('Soul', 3, {'target': 1})
    add('Soul', 5, {})
    add('Soul', 5, {'rooted': 1})
    add('Soul', 0x12, {'anim': 0})
    add('Soul', 0x12, {'anim': 0x10})
    add('Soul', 0x19, {'anim': 0})
    add('Soul', 0x17, {'clock': 1000, 'timer': 0})
    add('Soul', 0x17, {'clock': 100, 'timer': F})
    add('Soul', 0x14, {'clock': 1000, 'timer': 0})
    add('Soul', 0x14, {'clock': 100, 'timer': F})
    add('Soul', 0x14, {'anim': 0x80, 'clock': 100, 'timer': F})
    add('Soul', 0x22, {'clock': 1000, 'timer': 0})
    add('Soul', 0x22, {'clock': 100, 'timer': F})
    add('Soul', 0x22, {'anim': 0x80, 'clock': 100, 'timer': F})
    add('Soul', 0x1b, {'clock': 1000, 'timer': 0})
    add('Soul', 0x1b, {'clock': 100, 'timer': F, 'z': 0})
    add('Soul', 0x1b, {'clock': 100, 'timer': F, 'z': 0x42c80000})
    add('Soul', 0x1a, {'owner': 1})
    add('Soul', 6, {})


_suite()


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    only = set(argv[2:])
    ex = own_exec.Exec(argv[1])
    checks = 0
    fails = 0
    for name, state, ctx in CASES:
        if only and name not in only:
            continue
        status, calls, _stored = ex.tick(name, state, M.materialize(ctx), follow_extra=False)
        got_req = own_exec.requests(calls)
        got_calls = M.decision(calls)
        want_req, want_calls, words = M.step(name, state, ctx)
        bad = []
        if status != 'ok':
            bad.append(status)
        if got_req != want_req or got_calls != want_calls:
            bad.append('req %s/%s calls %s/%s' % (got_req, want_req, got_calls, want_calls))
        for off, value in words.items():
            got = ex.ee.mem.load(own_exec.OBJ + off, 4) & 0xffffffff
            if got != (value & 0xffffffff):
                bad.append('+%#x %s/%s' % (off, hex(got), hex(value & 0xffffffff)))
        checks += 1
        if bad:
            fails += 1
            print('FAIL %s %02x %s' % (name, state, ctx))
            for line in bad:
                print('   ', line)
    # NPC root-motion gate, state 1. The zero is a transient store.
    if not only or 'NPC' in only:
        for word, cleared in ((0x3f000000, False), (0x3f000001, True), (0xbf000001, True)):
            ex.tick('NPC', 1, M.materialize({'root_y': word, 'speed': 0x42c80000}),
                    follow_extra=False)
            stores = [w[3] & 0xffffffff for w in ex.ee.writes if w[1] == own_exec.OBJ + 0xb8]
            want = [0, 0x42c80000] if cleared else [0x42c80000]
            checks += 1
            if stores != want or M.root_clears_speed(word) != cleared:
                fails += 1
                print('FAIL NPC root %#x stores %s' % (word, [hex(s) for s in stores]))
    print('%d checks, %d failed' % (checks, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
