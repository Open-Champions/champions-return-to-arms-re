#!/usr/bin/env python3
"""difftest_creature_init.py - tools/ref_creature_init.py against Creature_init 0x10a230.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_creature_init.py [SLUS_209.73] [--cases N] [--seed N] [-v]

The original runs in tools/ee_emu.py on a 0x500-byte creature block with a table of its
own: the entries of slots 16, 18 and 27 point at recording stubs (slot 16 answers 0 or a
model), and so do slots 2..8 of a weapon object at +0x50 (or +0x50 is 0).  REAL:
Creature_init, obj_getPropStr 0x14f4c0, obj_getPropInt 0x14c880, libc_sprintf and what
they call.  STUBS: model_getBounds (writes six chosen ints), model_buildHideMask (answers a
chosen 64-bit value), anim_snapTopToEnd, script_runByName (which records
g_scriptSelectedObj as it finds it).

Per case, random: the creature flags +0xa8 (MiniBoss bit on or off), the model answer,
the six bounds, the property list (dead, change0..31, the seven weapon keys with values
0, 1, -1 or text, initScript, other keys, capitalised keys that must not match),
the weapon pointer, g_cutsceneActive.  Compared: the stubbed calls in order with their
first arguments, and every store into the creature block and to g_scriptSelectedObj, in
order, with sizes and values.
"""
import hashlib
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature_init as R                   # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73'),
              os.path.expanduser('~/champions-re/SLUS_209.73')]
OPTIONS = {'cases': 400, 'seed': 20973, 'verbose': False}
M32 = 0xFFFFFFFF
CREATURE_INIT = 0x10A230
FAKE = 0x00F00000              # unmapped: the fake table entries point here (hooked)
SIZE = 0x500


def fake_fn(slot, weapon=False):
    return FAKE + (0x1000 if weapon else 0) + slot * 0x10


class Case:
    def __init__(self, rng, emu):
        self.flags = rng.getrandbits(64) & ~1 | rng.choice([0, 1])
        self.model = rng.choice([0, 0, 0x00A00000 | rng.getrandbits(12) << 4])
        self.bounds = [rng.choice([0, 1, 40, 83, 84, 85, 200, -5, 0x7FFF, rng.getrandbits(16)])
                       for _ in range(6)]
        self.mask_value = rng.getrandbits(64)
        self.weapon = rng.choice([0, 1])
        self.cutscene = rng.choice([0, 0, 1])
        props = []
        if rng.random() < 0.4:
            props.append(b'dead=' + rng.choice([b'1', b'', b'yes']))
        for n in rng.sample(range(32), rng.choice([0, 0, 1, 3])):
            props.append(b'change%d=%d' % (n, rng.randint(0, 2)))
        weapon_keys = [emu.mem.cstr(k) for k in R.KEY_WEAPONS]
        for key in weapon_keys:
            key = key.encode() if isinstance(key, str) else key
            if rng.random() < 0.25:
                props.append(key.lower() + b'=' + rng.choice([b'0', b'1', b'-1', b'x', b'2']))
            if rng.random() < 0.05:
                props.append(key + b'=1')                       # capitalised: never found
        if rng.random() < 0.4:
            props.append(b'initscript=' + rng.choice([b'go', b'', b'start1']))
        if rng.random() < 0.3:
            props.append(b'Dead=1')                              # capitalised key
        if rng.random() < 0.5:
            props.append(b'name=thing')
        rng.shuffle(props)
        self.props = props


def build(emu, case):
    obj = emu.alloc(SIZE)
    table = emu.alloc(0x200)
    for slot in range(40):
        emu.mem.w32(table + 8 * slot, 0)
        emu.mem.w32(table + 8 * slot + 4, fake_fn(slot))
    emu.mem.w32(obj + 0x48, table)
    emu.mem.w64(obj + 0xA8, case.flags)
    if case.weapon:
        weapon = emu.alloc(0x100)
        wtable = emu.alloc(0x200)
        for slot in range(16):
            emu.mem.w32(wtable + 8 * slot, 0)
            emu.mem.w32(wtable + 8 * slot + 4, fake_fn(slot, True))
        emu.mem.w32(weapon, wtable)
        emu.mem.w32(obj + 0x50, weapon)
    ptrs = []
    for p in case.props:
        a = emu.alloc(len(p) + 1)
        emu.mem.write(a, p + b'\0')
        ptrs.append(a)
    plist = emu.alloc(4 * (len(ptrs) + 1))
    for k, a in enumerate(ptrs + [0]):
        emu.mem.w32(plist + 4 * k, a)
    emu.mem.w32(obj + 0x2C, plist)
    emu.mem.w8(R.G_CUTSCENE, case.cutscene)
    return obj


def run_original(elf, case):
    emu = EE(elf)
    obj = build(emu, case)
    events = []
    for slot in range(40):
        def vslot(e, slot=slot):
            events.append(('vcall', slot, (e.r[4] - obj) & M32, e.r[5] & M32))
            return case.model if slot == R.SLOT_MODEL else 0
        emu.stub(fake_fn(slot), function=vslot)
    for slot in range(16):
        def wslot(e, slot=slot):
            events.append(('weapon', slot, e.r[5] & M32))
            return 0
        emu.stub(fake_fn(slot, True), function=wslot)

    def bounds(e):
        events.append(('bounds', e.r[4] & M32, e.r[5] & M32))
        for k, reg in enumerate((6, 7, 8, 9, 10, 11)):
            e.mem.w32(e.r[reg] & M32, case.bounds[k] & M32)
        return 0
    emu.stub(R.MODEL_GET_BOUNDS, function=bounds)

    def hide(e):
        events.append(('hide_mask', e.r[4] & M32, e.r[5] & M32))
        e.r[3] = 0
        return case.mask_value
    emu.stub(R.MODEL_HIDE_MASK, function=hide)
    emu.stub(R.ANIM_SNAP_TOP_TO_END, function=lambda e: events.append(('snap', (e.r[4] - obj) & M32)) and None)

    def script(e):
        sel = e.mem.u32(R.G_SCRIPT_SELECTED)
        events.append(('script', e.mem.cstr(e.r[4] & M32), 'this' if sel == obj else sel))
        return 0
    emu.stub(R.SCRIPT_RUN_BY_NAME, function=script)
    emu.record_writes = True
    emu.reset_log()
    emu.call(CREATURE_INIT, obj, max_steps=2000000)
    writes = []
    for _pc, addr, size, value in emu.writes:
        if obj <= addr < obj + SIZE:
            writes.append((addr - obj, size, value))
        elif addr == R.G_SCRIPT_SELECTED:
            writes.append(('g', size, 'this' if value == obj else value))
    return events, writes


class RefObj:
    def __init__(self, case, strings, writes):
        self.case, self.strings, self.writes = case, strings, writes
        self.flags = case.flags

    def flags64(self):
        return self.flags

    def set_flags64(self, v):
        self.flags = v & ((1 << 64) - 1)
        self.writes.append((0xA8, 8, self.flags))

    def weapon(self):
        return self.case.weapon

    def _find(self, key):
        key = key.lower()
        for entry in self.case.props:
            if entry[:len(key)] == key and entry[len(key):len(key) + 1] == b'=':
                return entry[len(key) + 1:]
        return None

    def prop_str(self, addr, text=None):
        return self._find(text if text is not None else self.strings(addr))

    def prop_int(self, addr):
        import ref_objects
        found = self._find(self.strings(addr))
        return 0 if found is None else ref_objects.atoi(found)

    def store(self, off, size, value):
        self.writes.append((off, size, value))

    def store_global(self, addr, size, value):
        self.writes.append(('g', size, value))


class RefHost:
    def __init__(self, case, strings, events):
        self.case, self.strings, self.events = case, strings, events

    def vcall(self, slot, args):
        self.events.append(('vcall', slot, 0, args[0] if args else None))
        return self.case.model if slot == R.SLOT_MODEL else 0

    def weapon_vcall(self, slot, args):
        self.events.append(('weapon', slot, 0))

    def bounds(self, model):
        self.events.append(('bounds', model, M32))
        return [b & M32 for b in self.case.bounds]

    def hide_mask(self, model, mask):
        self.events.append(('hide_mask', model, mask))
        return self.case.mask_value

    def call(self, name, args):
        if name == 'anim_snapTopToEnd':
            self.events.append(('snap', 0x114))
        elif name == 'script_runByName':
            self.events.append(('script', args[0].decode('latin-1'), 'this'))

    def cutscene(self):
        return self.case.cutscene

    def change_key(self, n):
        return self.strings(R.KEY_CHANGE).replace(b'%d', b'%d' % n)


def run_ref(case, strings):
    events, writes = [], []
    R.run(RefObj(case, strings, writes), RefHost(case, strings, events))
    return events, writes


def normalise(events, ref):
    """The original's vcall records carry the argument registers as found; a1 is only an
    argument for slot 27.  The ref records None for the other slots."""
    out = []
    for e in events:
        if e[0] == 'vcall':
            out.append(('vcall', e[1], e[2], e[3] if e[1] == R.SLOT_SET_STATE else None))
        else:
            out.append(e)
    return out


def main(argv):
    args = list(argv)
    if '--cases' in args:
        OPTIONS['cases'] = int(args[args.index('--cases') + 1])
    if '--seed' in args:
        OPTIONS['seed'] = int(args[args.index('--seed') + 1])
    OPTIONS['verbose'] = '-v' in args
    elf = None
    for a in [x for i, x in enumerate(args) if i == 0 or args[i - 1] not in ('--cases', '--seed')]:
        if not a.startswith('-') and os.path.exists(a):
            elf = a
    for c in CANDIDATES:
        if elf is None and os.path.exists(c):
            elf = c
    if elf is None:
        print('SLUS_209.73 not found; nothing compared')
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != ELF_SHA:
        print('this is not SLUS_209.73 v2.00; nothing compared')
        return 0
    probe = EE(elf)

    def strings(addr):
        t = probe.mem.cstr(addr)
        return t.encode('latin-1') if isinstance(t, str) else bytes(t)
    rng = random.Random(OPTIONS['seed'])
    bad, seen = [], {'dead': 0, 'change': 0, 'weapon': 0, 'script': 0, 'miniboss': 0, 'model': 0}
    for index in range(OPTIONS['cases']):
        case = Case(rng, probe)
        try:
            got_events, got_writes = run_original(elf, case)
        except EmuError as exc:
            bad.append((index, 'emulator stopped: %s' % exc))
            continue
        want_events, want_writes = run_ref(case, strings)
        got_events = normalise(got_events, False)
        got_events = [('script', e[1] if isinstance(e[1], str) else e[1].decode('latin-1'), e[2])
                      if e[0] == 'script' else e for e in got_events]
        if (got_events, got_writes) != (want_events, want_writes):
            bad.append((index, 'events %r / %r; writes %r / %r' % (got_events, want_events,
                                                                    got_writes, want_writes)))
        for e in got_events:
            if e[0] == 'snap':
                seen['dead'] += 1
            elif e[0] == 'hide_mask':
                seen['change'] += 1
            elif e[0] == 'weapon':
                seen['weapon'] += 1
            elif e[0] == 'script':
                seen['script'] += 1
            elif e[0] == 'vcall' and e[1] == R.SLOT_MINIBOSS:
                seen['miniboss'] += 1
            elif e[0] == 'bounds':
                seen['model'] += 1
    detail = '%d cases, %d mismatches (seed %d); paths entered: %s' % (
        OPTIONS['cases'], len(bad), OPTIONS['seed'],
        ', '.join('%s %d' % kv for kv in sorted(seen.items())))
    if bad and OPTIONS['verbose']:
        detail += '\n    ' + '\n    '.join('case %d: %s' % b for b in bad[:4])
    print('%s  creature_init  %s' % ('PASS' if not bad else 'FAIL', detail))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
