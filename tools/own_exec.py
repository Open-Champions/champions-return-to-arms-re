#!/usr/bin/env python3
"""Execute one creature run tick with named helper answers (round 4).

The class's own run function runs in tools/ee_emu.py. Every callee is stubbed.
Known helpers return the values in a context dict; everything else returns 0
(or a dummy object when ``default`` says so). This is a single-function
execution on synthetic memory, not a running game.

Nothing here is a model of the state machine. tools/ref_own_machines.py is.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_anim_dispatch as S
from ee_emu import EE, EmuError

OBJ, DUMMY = S.OBJ, S.DUMMY

# Shared helpers the ten run functions call. Addresses are the named symbols.
HELPERS = {
    0x110d30: 'damage',
    0x112948: 'crun',
    0x10c0f0: 'active',
    0x1162b0: 'step',
    0x115eb8: 'knock',
    0x10eed8: 'away',
    0x118d40: 'see',
    0x10cf78: 'enemy',
    0x10d5e8: 'ally',
    0x1195e0: 'unroot',
    0x1195f0: 'ready',
    0x119608: 'unstun',
    0x119618: 'wander',
    0x1196e8: 'hit_reach',
    0x119938: 'hit_arc',
    0x119a20: 'hit_or',
    0x119b58: 'hit_all',
    0x1187e0: 'turn',
    0x114510: 'move_to',
    0x1155e0: 'move_direct',
    0x1143e8: 'move_target',
    0x119f08: 'flee',
    0x119f38: 'move_dest',
    0x11a1e0: 'clear_path',
    0x1108a0: 'dead',
    0x113c48: 'move_by',
    0x119e38: 'settle',
    0x119d10: 'knock_target',
    0x11aaf8: 'lead',
    0x1509d0: 'rand',
    0x10a9c0: 'filter',
    0x3b8534: 'strcmp',
    0x3b81a0: 'strcasecmp',
    0x14f200: 'delete',
    0x14f290: 'stop',
    0x14f028: 'grid',
    0x1ef270: 'fx',
    0x210128: 'path',
    0x16cfe0: 'anim_start',
    0x16ceb0: 'anim_bio',
    0x170838: 'anim_push',
    0x1708c0: 'anim_push_w',
    0x170938: 'anim_chain',
    0x1709f8: 'sync',
    0x16d0b8: 'randomize',
    0x115910: 'flee_from',
    0x1a1698: 'handle_clear',
    0x166630: 'cos16',
    0x1666e0: 'sin16',
    0x166798: 'atan2',
    0x166c18: 'approach',
    0x1799c8: 'samples',
    0x183820: 'terrain',
    0x163cb8: 'mat_place',
    0x163000: 'mat_rot',
    0x2ab2b4: 'demon',
    0x14fdb8: 'pool',
    0x238448: 'aq_air',
    0x2385dc: 'aq_ground',
    0x238150: 'aq_bank',
}
# strcmp-like: 0 means the strings match. Default answer is "not equal".
STRINGS = {0x3b8534, 0x3b81a0}

# Run entry of each own-machine class (docs/monsters.md 3.1, vtable slot 4).
RUNS = {
    'AntQueen': 0x236f78,
    'Critter': 0x255008,
    'Gnaw': 0x267654,
    'GnomeNavigator': 0x26a1e0,
    'Mermaid': 0x285c58,
    'Natasla': 0x29dbf0,
    'NPC': 0x29ea40,
    'Skeleton': 0x2a6864,
    'Skelight': 0x2a8b84,
    'Soul': 0x2a9870,
}

# Helpers whose logic IS the case (called and then the case returns into them).
# Filled after the first probe; empty means the switch stays in the run function.
FOLLOW = {
    'AntQueen': (0x238448, 0x2385dc, 0x238150),
}


class _Follow(object):
    """Membership: the named entries, plus the software-float / libm band."""

    def __init__(self, exact):
        self.exact = exact

    def __contains__(self, item):
        return item in self.exact or 0x380000 <= item < 0x3c0000


class Exec:
    def __init__(self, path):
        self.sc = S.Scanner(path)
        self.ee = self.sc.ee
        self._install()

    def _install(self):
        """Named stubs. A context copied into self.ans on each tick supplies returns."""
        self.ans = {}
        self.seq = {}          # name -> list consumed in order, else ans[name]
        ee = self.ee

        def make(name):
            def fn(emu):
                if name in self.seq and self.seq[name]:
                    return self.seq[name].pop(0)
                if name in self.ans:
                    return self.ans[name]
                if name in ('strcmp', 'strcasecmp'):
                    return 1
                if name == 'rand':
                    return 0
                if name == 'active':
                    return 1
                if name == 'step':
                    return 0
                return 0
            return fn

        for addr, name in HELPERS.items():
            ee.stub(addr, function=make(name), name=name)
        for slot in range(48):
            ee.stub(S.FAKE + 8 * slot, function=make('v%d' % slot), name='v%d' % slot)
            ee.stub(S.FAKE_HOLDER + 8 * slot, function=make('h%d' % slot), name='h%d' % slot)
            ee.stub(S.FAKE_OTHER + 8 * slot, function=make('o%d' % slot), name='o%d' % slot)

    def tick(self, name, state, ctx=None, follow_extra=True, max_steps=80000):
        """One run call. Returns (status, calls) where calls are (label, args, ret)
        in order. ``ctx`` keys are helper names, 'anim', 'events', 'target', 'clock',
        'timer', 'pokes' ((addr, size, value), ...), 'seq' ({name: [returns]})."""
        ctx = dict(ctx or {})
        sc = self.sc
        sc.reset(state, ctx.get('anim', 0))
        m = self.ee.mem
        m.store(OBJ + 0x300, 4, ctx.get('clock', 1000) & 0xffffffff)
        m.store(OBJ + 0xf4, 4, ctx.get('timer', 0) & 0xffffffff)
        # +0x118 is the track count (halfword). +0x11a is the flag union; a word
        # store at +0x118 would wipe it. Count is written as a halfword.
        m.store(OBJ + 0x118, 2, ctx.get('queue', 1) & 0xffff)
        if 'frame' in ctx:
            m.store(0x44fdcc, 4, ctx['frame'] & 0xffffffff)
        if 'serial' in ctx:
            m.store(OBJ + 0x230, 1, ctx['serial'] & 0xff)
        if 'cflags' in ctx:
            m.store(OBJ + 0xa8, 8, ((1 << 63) | ctx['cflags']) & 0xffffffffffffffff)
        if ctx.get('target'):
            m.store(OBJ + 0x234, 4, DUMMY)
        if ctx.get('owner'):
            m.store(OBJ + 0x3c8, 4, DUMMY)
        for addr, size, value in ctx.get('pokes', ()):
            m.store(addr, size, value & ((1 << (8 * size)) - 1))
        m.store(OBJ + 0x11a, 2, ctx.get('anim', 0) & 0xffff)
        self.ans = {
            'active': 1,
            'crun': 0,
            'step': ctx.get('events', 0),
            'damage': 0,
            'v16': DUMMY,
            'v25': 1 if ctx.get('seen') else 0,
            'away': 1 if ctx.get('away') else 0,
            'see': DUMMY if ctx.get('see') else 0,
            'enemy': DUMMY if ctx.get('enemy') else 0,
            'ally': 1 if ctx.get('ally') else 0,
            'unroot': 0 if ctx.get('rooted') else 1,
            'ready': 1 if ctx.get('ready') else 0,
            'unstun': 0 if ctx.get('stunned') else 1,
            'move_to': 1 if ctx.get('arrived') else 0,
            'move_direct': 1 if ctx.get('arrived') else 0,
            'move_dest': 1 if ctx.get('arrived') else 0,
            'rand': ctx.get('rand', 0),
            'filter': 0,
            'strcmp': 0 if ctx.get('streq') else 1,
            'strcasecmp': 0 if ctx.get('streq') else 1,
        }
        names = set(HELPERS.values())
        for key, value in ctx.items():
            if key in self.ans or key in names or key[:1] in ('v', 'h'):
                self.ans[key] = value
        self.seq = {k: list(v) for k, v in ctx.get('seq', {}).items()}
        fn = RUNS[name]
        extra = set(FOLLOW.get(name, ())) if follow_extra else set()
        # a followed helper must not be stubbed
        saved = {}
        for addr in extra:
            saved[addr] = self.ee.hooks.pop(addr, None)
        # Software float and libm are pure. Running them keeps comparisons exact;
        # stubbing them would turn every threshold into "callee returned 0".
        self.ee.follow = _Follow({fn} | extra)
        self.ee.default_ret = ctx.get('default', 0)
        self.ee.calls = []
        self.ee.writes = []
        try:
            self.ee.call(fn, OBJ, DUMMY, sp=EE.STACK_HI - 0x2000, max_steps=max_steps)
            status = 'ok'
        except EmuError as exc:
            status = 'error: %s' % str(exc)[:160]
        for addr, hook in saved.items():
            if hook is not None:
                self.ee.hooks[addr] = hook
        calls = []
        for c in self.ee.calls:
            label = c.name or ('%06x' % c.target)
            if c.target == fn:
                continue
            calls.append((label, c.args[1] & 0xffffffff if len(c.args) > 1 else 0, c.ret))
        stored = self.ee.mem.load(OBJ + 0x232, 2)
        return status, calls, stored


def requests(calls):
    """setState arguments asked through virtual slot 27, in order."""
    out = []
    for label, arg, _ret in calls:
        if label == 'v27':
            out.append(arg)
    return out


def main(argv):
    path = argv[1] if len(argv) > 1 else 'local/SLUS_209.73'
    only = set(argv[2:])
    ex = Exec(path)
    states = [0, 1, 3, 5, 6, 7, 8, 9, 0x10, 0x11, 0x12, 0x13, 0x14, 0x16,
              0x17, 0x18, 0x19, 0x1a, 0x1b, 0x22]
    grids = (
        ('base', {}),
        ('seen', {'seen': 1}),
        ('away', {'away': 1}),
        ('target-see', {'target': 1, 'see': 1}),
        ('target-blind', {'target': 1}),
        ('flag8', {'anim': 8, 'target': 1}),
        ('flag10', {'anim': 0x10, 'target': 1}),
        ('flag80', {'anim': 0x80}),
        ('ev1', {'events': 1, 'target': 1, 'anim': 8}),
        ('rooted', {'rooted': 1, 'target': 1}),
        ('hold', {'timer': 5000, 'clock': 1000}),
        ('ready', {'ready': 1}),
        ('arrive', {'arrived': 1, 'timer': 5000, 'clock': 1000}),
    )
    for name in RUNS:
        if only and name not in only:
            continue
        print('==', name)
        for st in states:
            base = None
            for tag, ctx in grids:
                status, calls, stored = ex.tick(name, st, ctx, follow_extra=False)
                req = requests(calls)
                labels = [c[0] for c in calls if c[0] not in
                          ('damage', 'crun', 'active', 'step', 'knock', 'v23', 'v16')]
                row = (tuple(req), tuple(labels), status, stored)
                if tag == 'base':
                    base = row
                    print('  %02x base %s req=%s calls=%s' % (st, status, req, labels[:12]))
                elif row != base:
                    print('  %02x %-12s req=%s calls=%s %s' % (st, tag, req, labels[:12], status))


if __name__ == '__main__':
    main(sys.argv)
