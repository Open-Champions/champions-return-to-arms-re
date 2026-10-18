#!/usr/bin/env python3
"""difftest_fx_props.py - compare tools/ref_fx_props.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_fx_props.py [path/to/SLUS_209.73] [--quick] [--seed N] [-v]

How it is tested
    Torch_run 0x2b2088, Candle_run 0x2b2dc4, Candle2_run 0x2b3164 (Candle3), Lantern_run
    0x2b3554 and Lamp_run 0x2b3858 are executed by tools/ee_emu.py on objects this script
    allocates (position, generator state +0x44, kind, counters), with a random
    g_noiseTable 0x6e0d90 and level name 0x41b721.  particle_spawn is replaced by a stub
    that records its four arguments (f12 back-date, definition, position, velocity);
    obj_stopRunning by one that records the call.  Each tick the recorded spawns, the light
    node (both radii, both falloffs, position), the generator state, the counters and the
    stop are compared with the model, bit for bit.

Property
    props        runs of 1-300 ticks of each class (torch kinds 0-5, big and small candles,
                 lantern levels with and without 'mine'), random g_simFrame and objects
"""
import hashlib
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, M32                 # noqa: E402
import ref_core as C                       # noqa: E402
import ref_fx_props as F                   # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'verbose': False}

RUN_ADDR = {F.TORCH: 0x2B2088, F.CANDLE: 0x2B2DC4, F.CANDLE3: 0x2B3164, F.LANTERN: 0x2B3554, F.LAMP: 0x2B3858}
UNDRAWN = {F.TORCH: 0x89, F.CANDLE: 0x8D, F.CANDLE3: 0x4D, F.LANTERN: 0x95, F.LAMP: 0x89}
SPAWN, STOP = 0x18F3F8, 0x14F290
G_NOISE, G_LEVEL_NAME, G_SIM_FRAME = 0x6E0D90, 0x41B721, 0x44FDCC


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = []
    while argv:
        a = argv.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(argv.pop(0), 0)
        else:
            positional.append(a)
    elf = next((p for p in positional + [os.path.join(ROOT, 'SLUS_209.73')] if os.path.isfile(p)), None)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path); nothing was tested')
        return 0
    with open(elf, 'rb') as h:
        if hashlib.sha256(h.read()).hexdigest() != EXPECTED_SHA256:
            print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
            return 0
    t0 = time.time()
    rng = random.Random(OPTIONS['seed'])
    e = EE(elf)
    e.record_writes = e.record_calls = False
    m = e.mem
    got, stops = [], []

    def spawn(emu):
        mm = emu.mem
        got.append(F.Spawn(emu.f[12], emu.r[4] & M32, [mm.u32(emu.r[5] + 4 * i) for i in range(3)],
                           [mm.u32(emu.r[6] + 4 * i) for i in range(3)]))
    e.stub(SPAWN, function=spawn)
    e.stub(STOP, function=lambda emu: stops.append(1))
    cases = 40 if OPTIONS['quick'] else 400
    fails, ex, ticks, spawned, stopped = 0, [], 0, 0, 0
    per = {}
    for case in range(cases):
        cls = rng.choice([F.TORCH, F.TORCH, F.CANDLE, F.CANDLE3, F.LANTERN, F.LAMP])
        table = [rng.randint(-0x8000, 0x7FFF) for _ in range(256)]
        for i, v in enumerate(table):
            m.w16(G_NOISE + 2 * i, v & 0xFFFF)
        name = rng.choice(['d_town', 'mine01', 'f_minefield', 'castle'])
        m.write(G_LEVEL_NAME, name.encode() + b'\0')
        addr = e.alloc(0xA0)
        pos = [C.f32(rng.uniform(-5000, 5000)) for _ in range(3)]
        seed = rng.getrandbits(16)
        kind = rng.randint(0, 5)
        big = rng.random() < 0.5
        model = F.FireProp(cls, addr, pos, seed, kind=kind, big=big, level_name=name)
        for i in range(3):
            m.w32(addr + 0x10 + 4 * i, pos[i])
            m.w32(addr + 0x7C + 4 * i, pos[i])
        m.w32(addr + 0x44, seed)
        m.w8(addr + 0x8A, kind)
        m.w32(addr + 0x90, 1 if big else rng.choice([0, 2]))
        for off, v in ((0x68, model.model_radius), (0x6C, model.model_falloff),
                       (0x70, model.level_radius), (0x74, model.level_falloff)):
            m.w32(addr + off, v)
        start_undrawn = rng.choice([0, 0, 25, 30])
        m.w8(addr + UNDRAWN[cls], start_undrawn)
        model.undrawn = start_undrawn
        m.w32(addr + 0x88, 0) if cls == F.CANDLE else None
        frame = rng.randint(0, 200000)
        bad = None
        for step in range(rng.choice([1, 8, 40, 300])):
            frame += 1
            m.w32(G_SIM_FRAME, frame)
            got.clear()
            stops.clear()
            e.call(RUN_ADDR[cls], addr)
            tick = F.RUN[cls](model, frame, table)
            ticks += 1
            spawned += len(got)
            stopped += len(stops)
            have = (got[:], bool(stops), m.u32(addr + 0x44), m.u8(addr + UNDRAWN[cls]))
            want = (tick.spawns, tick.stopped, model.rng.state, model.undrawn)
            if have != want:
                bad = 'step %d: spawns/stop/seed/counter %r vs %r' % (step, have[1:], want[1:]) \
                    if have[1:] != want[1:] else 'step %d: spawn %r vs %r' % (step, have[0][:2], want[0][:2])
            elif cls != F.CANDLE3:
                node = tuple(m.u32(addr + o) for o in (0x68, 0x6C, 0x70, 0x74))
                wn = (model.model_radius, model.model_falloff, model.level_radius, model.level_falloff)
                if node != wn:
                    bad = 'step %d: node %r vs %r' % (step, node, wn)
                elif cls == F.TORCH and [m.u32(addr + 0x7C + 4 * i) for i in range(3)] != model.light_pos:
                    bad = 'step %d: light position' % step
            if bad:
                break
        per[cls] = per.get(cls, 0) + 1
        if bad:
            fails += 1
            ex.append('case %d %s kind %d big %s: %s' % (case, cls, kind, big, bad))
    ok = not fails
    print('executable %s, seed %d' % (elf, OPTIONS['seed']))
    print('%s  props          %7d cases  %d ticks (%s): %d spawns (back-date, definition, position, '
          'velocity), light node, generator, counters, %d stops, bit for bit%s'
          % ('PASS' if ok else 'FAIL', cases, ticks, ', '.join('%s %d' % kv for kv in sorted(per.items())),
             spawned, stopped, '' if ok else '  [%d mismatches]' % fails))
    if not ok and OPTIONS['verbose']:
        for line in ex[:3]:
            print('        ' + line)
    print('1 properties, %d failed, %.0f s' % (0 if ok else 1, time.time() - t0))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
