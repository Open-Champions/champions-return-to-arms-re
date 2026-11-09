#!/usr/bin/env python3
"""Round 3 vendor gates: storeLevel progression, bounded failure, shop menu states.

Original functions run in tools/ee_emu.py. Output is counts and addresses only.
Pass the private executable and --disc DIR (the extracted disc, read-only).
Seeds 20973 and 7 run in every group. Stubs are named where they are installed;
nothing here renders a frame or reads a controller.
"""
import argparse
import hashlib
import itertools
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != HERE] + [HERE]
import unittest  # noqa: E402,F401  tools/dis.py must not shadow stdlib dis.
from ee_emu import EE, StepLimit, s32  # noqa: E402
from gob import gob_entries, lmp_entries  # noqa: E402
import ref_amx  # noqa: E402
from scr import parse, strings  # noqa: E402
import ref_items as I  # noqa: E402
import ref_vendor_stock as S  # noqa: E402
import difftest_natives as N  # noqa: E402
from difftest_items import Original, EXPECTED_SHA256  # noqa: E402

SEEDS = (20973, 7)
PLAYERS, REC, MISSION = 0x4D8AF0, 0x4C30, 0x4BBF
NUM_PLAYERS, DIFFICULTY, ACT, ACTS = 0x4D8AE0, 0x4F719C, 0x88D3D4, 0x4F8E7C
FIND_ACT, ACT_CHANGED = 0x217D30, 0x217F70
STOCK_FN, VAR_GET, VAR_SET, RESOURCE = 0x1C7AF8, 0x1ED778, 0x1ED854, 0x173558
GENERATE, PRESET, PARSE, SAME, VALUE = 0x104CA4, 0x104758, 0x1069B8, 0x108924, 0x1024A8
STRINGS = {0x3B8534, 0x3B868C, 0x3B8DC4}
SCRIPTS = ('hub', 'hub2', 'stobonus', 'islgnome')
SHOP_TASK, SHOP_CLOSE, GRID, SEND_BUY = 0x1C6068, 0x1D0AB8, 0x1CBBE8, 0x1C5F78
NET_SEND, POPUP, SOUND, BAGS_VIEW, CONFIRM_DIALOG = 0x13DB38, 0x1D9954, 0x214230, 0x1C4E88, 0x1DADC0
SHOP_OPEN, PAUSE, LOCKOUT = 0x41B50C, 0x41B4F4, 0x41B4FC
CELLS, STOCK_CELLS = 0x4EBBB0, 0x4F4228
SELL_PENDING, LIST_STATE = 0x86A680, 0x4F4218
BLOCK_A, BLOCK_B = 0x4F4878, 0x4F4880
BAG_PANEL = 0x4F4040
# Live in the menu probe: the shop task, run, choice, cursor, join, close and list input.
MENU_FOLLOW = {SHOP_TASK, 0x1C74C0, 0x1C6BB8, 0x1C6570, 0x1C6438, 0x1658F0, 0x1C5B48,
               SHOP_CLOSE, 0x1D1380, 0x1D14C8, 0x1CD988, 0x1C6938, 0x1D1790, 0x1CEC68}
# Mission levels whose `start` stores currentMission (offset of the setv call).
CURRENT_MISSION = {
    'blood1': (1, 0x170), 'innovat1': (2, 0xB9C), 'islc1': (3, 0x3A8), 'islcave1': (3, 0xE0),
    'wat1': (4, 0x37C), 'water1': (4, 0xE0), 'tormenta': (5, 0xD9C), 'swamp1': (6, 0x17C),
    'swamp2': (6, 0x17C), 'valor': (7, 0xFD8), 'fire1': (8, 0x14C), 'obsfor1': (8, 0xE0),
    'storm1': (9, 0x2B4), 'storm2': (9, 0x420), 'storm4': (9, 0x78), 'fay1': (10, 0x67C),
    'fay2': (10, 0x654), 'nit1': (11, 0x124), 'nitmar1': (11, 0xE0), 'bossgood': (12, 0x9C),
    'bossevil': (12, 0x9C)}
# Opcodes of the non-literal store: stack, move.alt, const.pri 1, sub.alt, push.pri,
# push.c name, push.c 8, sysreq.c setv.
EXPRESSION = (0x2C, 0x22, 0x0B, 0x50, 0x24, 0x27, 0x27, 0x7B)
PROC = [name for name, _kind, _addr in ref_amx.OPCODES].index('PROC')
# Round 4 (fix of r3): menu sites and addresses the probe now asserts.
MENU_RESET, BUY_TAIL, HUD_MENU_STATE, TASK_REMOVE = 0x1D1380, 0x1BEC10, 0x1DE0DC, 0x19E664
ZERO_PAD, NET_FLAG, REGION = 0x86A6B0, 0x402791, 0x41B69C
OBJECT_PTR, LATCH = 0x43D8, 0x47A
SALE_STORES = 0x1CE4E0          # first instruction after the latch store, before the msg bytes
# (gold, bag count, carried weight, outcome): price 59 (value 100), item weight 1.0, capacity 100.0.
BUY_ROWS = ((1000, 0, 0.0, 'send'), (59, 0, 0.0, 'send'), (58, 0, 0.0, 'gold'),
            (10, 0, 0.0, 'gold'), (-1, 0, 0.0, 'gold'), (-0x80000000, 0, 0.0, 'gold'),
            (1000, 63, 0.0, 'send'), (1000, 64, 0.0, 'full'), (1000, 65, 0.0, 'full'),
            (1000, -1, 0.0, 'send'), (1000, 0, 99.0, 'send'), (1000, 0, 99.5, 'weight'),
            (1000, 0, 100.0, 'weight'))
# Mission bytes for the hub matrix: every mission 8/9 pair, plus every mission byte set.
BYTE_ROWS = tuple(((8, a), (9, b)) for a, b in itertools.product(range(4), range(4))) + (
    tuple((n, 3) for n in range(13)),)


def sha(path):
    with open(path, 'rb') as source:
        return hashlib.sha256(source.read()).hexdigest()


# ---- disc scripts -----------------------------------------------------------------------
def disc_scripts(disc):
    """Every level script.scr on the disc, keyed by archive base name (lower case)."""
    found = {}
    for dirpath, _dirs, files in os.walk(disc):
        for filename in sorted(files):
            if not filename.upper().endswith('.GOB'):
                continue
            data = open(os.path.join(dirpath, filename), 'rb').read()
            try:
                lumps = gob_entries(data)
            except (OSError, ValueError, IndexError, struct.error):
                continue
            for _lname, loff, lsize in lumps:
                lump = data[loff:loff + lsize]
                try:
                    entries = lmp_entries(lump)
                except (OSError, ValueError, IndexError, struct.error):
                    continue
                for fname, foff, fsize in entries:
                    if fname == 'script.scr':
                        found[os.path.splitext(filename)[0].lower()] = lump[foff:foff + fsize]
    return found


def variable_calls(blob, variable):
    """(offset, native, value) for every getv/setv/addv naming ``variable``.

    value is the pushed constant, or ('expr', opcodes, constant) when the store
    computes its value; then the decoded ops between the previous call and setv.
    """
    machine = ref_amx.Machine(blob)
    assert machine.load() == 0
    names = [machine.native_name(i).decode('latin1') for i in range(machine.num_natives)]
    parsed = parse(blob)
    pool = dict(strings(blob, *parsed['strings']))
    wanted = {off for off, text in pool.items() if text.lower() == variable.lower()}
    order = sorted(machine._decoded)
    rows = []
    pending = []
    window = []
    for start in order:
        opcode, operand, _end = machine._decoded[start]
        window.append((opcode, operand))
        if opcode == 0x7B:
            args = pending[:-1][::-1] if pending else []
            label = names[operand] if isinstance(operand, int) and 0 <= operand < len(names) else ''
            if args and args[0][0] == 'c' and args[0][1] in wanted and label in ('getv', 'setv', 'addv'):
                if label != 'setv':
                    rows.append((start, label, None))
                elif len(args) > 1 and args[1][0] == 'c':
                    rows.append((start, label, args[1][1]))
                else:
                    ops = tuple(op for op, _ in window[1:])
                    const = [value for op, value in window[1:] if op == 0x0B]
                    rows.append((start, label, ('expr', ops, tuple(const))))
            pending = []
            window = [(opcode, operand)]
        elif opcode == 0x27:
            pending.append(('c', operand))
        elif opcode == 0x28:
            pending.append(('var', operand))
        else:
            pending = []
    return rows


def entry_of(blob):
    """offset -> name of the public entry whose PROC contains that code offset (or None)."""
    machine = ref_amx.Machine(blob)
    assert machine.load() == 0
    procs = sorted(off for off, (opcode, _operand, _end) in machine._decoded.items() if opcode == PROC)
    publics = {off: name.decode('latin1') for name, off in machine.publics()}

    def lookup(offset):
        heads = [p for p in procs if p <= offset]
        return publics.get(heads[-1]) if heads else None
    return lookup


def public_proc(blob, name):
    """Code offset of the public entry ``name``; asserts a PROC is decoded there."""
    machine = ref_amx.Machine(blob)
    assert machine.load() == 0
    offsets = [off for entry, off in machine.publics() if entry.decode('latin1') == name]
    assert len(offsets) == 1 and machine._decoded[offsets[0]][0] == PROC, (name, offsets)
    return offsets[0]


def native_calls(blob, native):
    """(offset, args) for every sysreq.c of ``native``. args are the pushes before the
    call in argument order (the argument-size push dropped): ('c', value) for push.c,
    ('var', address) for push, ('expr', None) for push.pri / push.alt / push.r / push.s."""
    machine = ref_amx.Machine(blob)
    assert machine.load() == 0
    names = [machine.native_name(i).decode('latin1') for i in range(machine.num_natives)]
    rows, pending = [], []
    for start in sorted(machine._decoded):
        opcode, operand, _end = machine._decoded[start]
        if opcode == 0x7B:
            if isinstance(operand, int) and 0 <= operand < len(names) and names[operand] == native:
                rows.append((start, tuple(pending[:-1][::-1])))
            pending = []
        elif opcode == 0x27:
            pending.append(('c', operand))
        elif opcode == 0x28:
            pending.append(('var', operand))
        elif opcode in (0x24, 0x25, 0x26, 0x29):
            pending.append(('expr', None))
        else:
            pending = []
    return rows


def run_start(elf, blob, seed, current=None, missions=(), difficulty=0, row=None, variable=b'storeLevel'):
    """Run a shipped `start` through scr_load / scr_interpret with recorded vars_set calls.

    Stubs: difftest_natives.Rig engine services (named there) and its Responder.
    The quest variable table starts zeroed; ``current`` is planted with the
    original vars_set before the entry runs. Returns (result, readback, stored values,
    script offsets of the storing sysreq.c). The offset is the machine's cip, which the
    interpreter writes to the machine structure +0x0c before every native call, minus 8.
    """
    rig = N.Rig(elf)
    rig.checkpoint()
    image = blob + bytes(256)
    assert rig.place(image) == (0, 0)
    scene = N.Scene(rig, random.Random(seed), names=[b'portal', b'firiona'],
                    variables=[b'firstmissionever'], objects=2)
    machine = N.new_machine(image)
    N.setup_model(scene, seed, machine)
    rig.responder = N.Responder(seed, scene)
    mem = rig.emu.mem
    mem.write(PLAYERS, bytes(N.N.REC_SIZE * 4))
    mem.write(N.N.G_QUEST_VARS, bytes(0x2000))
    mem.w32(NUM_PLAYERS, 1)
    mem.w32(DIFFICULTY, difficulty)
    mem.w32(S.SHARED, seed)
    for number, value in missions:
        mem.w8(PLAYERS + MISSION + 13 * (difficulty if row is None else row) + number, value)
    if current is not None:
        rig.call(N.A['vars_set'], scene.cstring(b'currentMission'), current)
    sets = []
    rig.emu.hook(N.A['vars_set'], lambda e: sets.append(
        (mem.cstr(e.r[4] & 0xFFFFFFFF, 40).lower(), s32(e.r[5]), mem.s32(rig.base + 0x0C) - 8)))
    result = s32(rig.call(N.A['script_runByName'], scene.cstring(b'start'), max_steps=40000000))
    rig.emu.unhook(N.A['vars_set'])
    level = s32(rig.call(N.A['vars_get'], scene.cstring(variable)))
    mine = [(value, cip) for name, value, cip in sets if name == variable.decode().lower()]
    return result, level, [value for value, _ in mine], [cip for _, cip in mine]


def store_level_cases(elf, disc):
    scripts = disc_scripts(disc)
    cases = 0
    sites = {}
    # Static decode: both hubs, literal order, and the one computed store.
    for name in ('hub', 'hub2'):
        entry = entry_of(scripts[name])
        rows = [row for row in variable_calls(scripts[name], 'storeLevel') if row[1] == 'setv']
        values = [row[2] for row in rows]
        assert values[:7] == [0, 8, 7, 6, 5, 7, 6] and len(values) == 8, name
        offset, _label, expr = rows[7]
        assert expr[0] == 'expr' and expr[1][-len(EXPRESSION):] == EXPRESSION and expr[2] == (1,), name
        getv = [row for row in variable_calls(scripts[name], 'currentMission') if row[0] < offset]
        assert getv and getv[-1][1] == 'getv' and offset - getv[-1][0] == 0x34, name
        # Every store and the getv lie inside the PROC of the public entry `start`.
        assert {entry(row[0]) for row in rows} == {'start'} and entry(getv[-1][0]) == 'start', name
        sites[name] = {row[0]: row[2] for row in rows}
        # The mission tests of the mission-7 branch push constants 9, 9 and 8 (argument order).
        tests = [(native, args) for native in ('getMissionComplete', 'getMissionAvailable')
                 for off, args in native_calls(scripts[name], native) if entry(off) == 'start']
        assert sorted(tests) == [('getMissionAvailable', (('c', 8),)), ('getMissionAvailable', (('c', 9),)),
                                 ('getMissionComplete', (('c', 9),))], (name, tests)
        start = public_proc(scripts[name], 'start')
        assert start == {'hub': 0x2838, 'hub2': 0x134}[name] and start < min(row[0] for row in rows), name
        print('PASS storeLevel %s start PROC@0x%x setv=%s computed@0x%x = getv(currentMission)@0x%x - 1; '
              'all in start; start tests %s' % (name, start, ','.join('0x%x' % row[0] for row in rows), offset,
                                                getv[-1][0], ' '.join('%s(%d)' % (n, a[0][1])
                                                                      for n, a in sorted(tests))), flush=True)
        cases += 1
    # Who stores currentMission: one literal per mission level, all in `start`.
    census = {}
    for name, blob in sorted(scripts.items()):
        rows = variable_calls(blob, 'currentMission')
        stores = [(row[2], row[0]) for row in rows if row[1] == 'setv']
        if stores:
            assert len(stores) == 1 and isinstance(stores[0][0], int), name
            assert entry_of(blob)(stores[0][1]) == 'start', name
            census[name] = stores[0]
        elif rows:
            assert name in ('hub', 'hub2') and all(row[1] == 'getv' for row in rows), name
    assert census == CURRENT_MISSION, census
    print('PASS currentMission stores=%d missions=%s, each inside start' % (
        len(census), ','.join(str(n) for n in sorted({v for v, _ in census.values()}))), flush=True)
    cases += 1
    # Executed: each mission level's `start` from zeroed quest variables stores its literal
    # once, from the census offset.
    for name, seed in itertools.product(sorted(CURRENT_MISSION), SEEDS):
        mission, offset = CURRENT_MISSION[name]
        result, value, stores, offsets = run_start(elf, scripts[name], seed, variable=b'currentMission')
        assert result == 0 and value == mission and stores == [mission] and offsets == [offset], (
            name, result, value, stores, offsets)
        cases += 1
    print('PASS currentMission executed: %d mission-level starts store their literal once at the '
          'census offset' % len(CURRENT_MISSION), flush=True)
    # Executed: every hub branch, both hubs, both seeds; every c with all 17 byte rows.
    for name, seed in itertools.product(('hub', 'hub2'), SEEDS):
        seen = set()
        for current, bytes_row in itertools.product((None, 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13), BYTE_ROWS):
            result, level, stores, offsets = run_start(elf, scripts[name], seed, current, bytes_row)
            want = S.hub_store_level(current or 0, dict(bytes_row))
            assert want == S.hub_store_level(current or 0), 'only c = 7 reads mission bytes'
            assert result == 0 and level == want and stores == [want], (name, current, bytes_row, level)
            assert len(offsets) == 1 and offsets[0] in sites[name], (name, current, offsets)
            site = sites[name][offsets[0]]
            assert site == want if isinstance(site, int) else want == (current or 0) - 1, (name, current)
            seen.update(offsets)
            cases += 1
        for difficulty, eight, nine in itertools.product((0, 2), range(4), range(4)):
            rows = {8: eight, 9: nine}
            result, level, stores, offsets = run_start(elf, scripts[name], seed, 7, rows.items(), difficulty)
            want = S.hub_store_level(7, rows)
            assert result == 0 and level == want and stores == [want], (name, difficulty, rows)
            assert len(offsets) == 1 and sites[name][offsets[0]] == want, (name, rows, offsets)
            seen.update(offsets)
            cases += 1
        # Another difficulty row does not count.
        result, level, _, _ = run_start(elf, scripts[name], seed, 7, ((9, 3), (8, 3)), 2, row=0)
        assert result == 0 and level == 5
        cases += 1
        # All eight store sites run, each from inside `start`.
        assert seen == set(sites[name]), (name, sorted(seen))
    for name, seed in itertools.product(('stobonus', 'islgnome'), SEEDS):
        for current in (None, 3, 9):
            result, level, stores, _ = run_start(elf, scripts[name], seed, current)
            assert result == 0 and level == stores[-1] == S.STORE_LEVEL_LITERAL[name], name
            cases += 1
    print('PASS storeLevel executed hub/hub2 matrix (14 c x 17 byte rows, mission-7 x 2 rows), '
          'all 8 sites per hub run; stobonus/islgnome literals', flush=True)
    return cases


# ---- act resolution: does a hub visit clear quest variables? -----------------------------
def act_cases(elf):
    e = EE(elf)
    e.follow = set(STRINGS) | {FIND_ACT, 0x2180A8, 0x3B91D8}   # strlen, strncmp live
    acts = e.mem.s32(ACTS)
    assert acts == 13
    text = e.alloc(64)
    cases = 0
    homes = {}
    local = set()
    for name, (mission, _off) in CURRENT_MISSION.items():
        e.mem.write(text, name.encode() + b'\0')
        e.mem.w32(ACT, 0)
        homes[name] = s32(e.call(FIND_ACT, text))
    for current in range(-1, acts):
        for hub in (b'hub', b'hub2'):
            e.mem.write(text, hub + b'\0')
            e.mem.w32(ACT, current & 0xFFFFFFFF)
            found = s32(e.call(FIND_ACT, text))
            assert found == max(current, 0), (hub, current, found)
            e.mem.w32(ACT, current & 0xFFFFFFFF)
            assert e.call(ACT_CHANGED, text) == int(current == -1)
            assert e.mem.s32(ACT) == max(current, 0)
            cases += 2
        for name, home in homes.items():
            e.mem.write(text, name.encode() + b'\0')
            e.mem.w32(ACT, current & 0xFFFFFFFF)
            found = s32(e.call(FIND_ACT, text))
            # The current act's table is searched first (prefix match), then acts from 0.
            assert found in (home, current), (name, current, found)
            if found != home:
                local.add((name, current))
            cases += 1
    # Mission levels: blood1 shares act 0 with the hubs; the others are their own act or none.
    assert homes['blood1'] == 0 and homes['innovat1'] == 1 and homes['valor'] == 6
    assert {name for name, home in homes.items() if home == -1} == {'islcave1', 'nitmar1', 'obsfor1', 'water1'}
    # save_actChanged for every mission level from every current act: a change (and the
    # act write) only for a listed level entered from another act; -1 is never a change.
    for name, home in homes.items():
        e.mem.write(text, name.encode() + b'\0')
        for current in range(-1, acts):
            e.mem.w32(ACT, current & 0xFFFFFFFF)
            changed = e.call(ACT_CHANGED, text)
            want = int(home not in (-1, current))
            assert changed == want and e.mem.s32(ACT) == (home if want else current), (name, current, changed)
            cases += 1
    # The table entry is a prefix of the name (strncmp over the entry's strlen, 0x217db0/0x217dd4).
    prefix = {}
    for name in ('blood1', 'innovat1', 'valor'):
        for probe, want in ((name + 'zz', homes[name]), (name[:-1], -1)):
            e.mem.write(text, probe.encode() + b'\0')
            e.mem.w32(ACT, 0xFFFFFFFF)
            prefix[probe] = s32(e.call(FIND_ACT, text))
            assert prefix[probe] == want, (probe, prefix[probe])
            cases += 1
    # Executed call sites: strlen 0x3b8dc4 then strncmp 0x3b91d8 at 0x217db0 / 0x217dd4 for the
    # current act's table, and at 0x217e4c / 0x217e64 for the scan from act 0. Each strncmp
    # compares the name with a table entry over that entry's length.
    sites = set()
    for probe, current in (('valorzz', 0), ('valorzz', 6), ('blood1zz', 0xFFFFFFFF)):
        e.mem.write(text, probe.encode() + b'\0')
        e.mem.w32(ACT, current)
        e.reset_log()
        e.call(FIND_ACT, text)
        for c in e.calls:
            sites.add((c.target, c.site))
            if c.target == 0x3B91D8:
                pair = [e.mem.cstr(a & 0xFFFFFFFF, 64) for a in c.args[:2]]
                assert probe in pair, (probe, pair)
                entry = pair[1 - pair.index(probe)]
                assert c.args[2] & 0xFFFFFFFF == len(entry), (probe, entry, c.args[2])
        cases += 1
    assert sites == {(0x3B8DC4, 0x217DB0), (0x3B91D8, 0x217DD4), (0x3B8DC4, 0x217E4C),
                     (0x3B91D8, 0x217E64)}, sorted(sites)
    print('PASS actChanged %d names x %d acts; prefix %s' % (
        len(homes), acts + 1, ' '.join('%s=%d' % row for row in sorted(prefix.items()))), flush=True)
    print('PASS acts=%d hub/hub2 resolve to the current act; mission homes %s; found in another current act %s' % (
        acts, ' '.join('%s=%d' % (n, homes[n]) for n in sorted(homes)),
        ' '.join('%s@%d' % row for row in sorted(local)) or '-'), flush=True)
    return cases


# ---- generation failure --------------------------------------------------------------------
def stock_rig(elf, seed, level=0, difficulty=1, script=None):
    """Session stock body with every item service stubbed (named here)."""
    e = EE(elf)
    e.follow = set(STRINGS) | {VAR_GET, VAR_SET}
    e.call(VAR_SET, 0x538750, level)
    e.mem.w32(DIFFICULTY, difficulty)
    e.mem.w32(S.SHARED, seed)
    e.mem.w32(S.COSMETIC, seed)
    e.stub(0x3A5AC8, function=lambda m: m.fset(0, 10000.0) or 0)   # powf: fixed budget base
    e.stub(SAME, ret=0)                                             # never a duplicate
    e.stub(VALUE, ret=0)                                            # equal values, no swap
    e.stub(PRESET, ret=0)                                           # optional specials append nothing
    e.stub(RESOURCE, ret=0)                                         # resource request
    log = []
    counter = [0]

    def generate(m):
        category = s32(m.r[6])
        count = m.mem.u32(S.STOCK + category * S.LIST_STRIDE + 0x1200)
        log.append((category, s32(m.r[5]), s32(m.r[7]), s32(m.r[8]), count, m.mem.u32(S.SHARED)))
        ok = script(category, len([row for row in log if row[0] == category])) if script else 1
        if ok:
            counter[0] += 1
            m.mem.w32(m.r[4] & 0xFFFFFFFF, 0x10000 + counter[0] * 0x40)
        return ok
    e.stub(GENERATE, function=generate)
    return e, log


def failure_cases(elf):
    cases = 0
    for seed in SEEDS:
        # K failures, then success: same budget, same count, no extra draw.
        for category, failures in itertools.product((0, 1), (1, 6, 40)):
            e, log = stock_rig(elf, seed, script=lambda c, n, cat=category, k=failures: int(c != cat or n > k))
            e.call(STOCK_FN, 0, 1, 1, max_steps=2000000)
            rows = [row for row in log if row[0] == category]
            head = rows[:failures + 1]
            assert len({row[1:5] for row in head}) == 1, 'retry keeps budget, suffix, level and count'
            assert all(row[5] == seed for row in rows), 'stubbed failure draws nothing'
            counts = (e.mem.u32(0x868078), e.mem.u32(0x869280), e.mem.u32(0x86A488))
            assert counts == (26, 17, 9), counts
            assert len(rows) == (22 if category == 0 else 17) + failures
            cases += 1
        # The third list counts attempts, so failures shorten it and it still returns.
        for failures in (0, 3, 6, 40):
            e, log = stock_rig(elf, seed, script=lambda c, n, k=failures: int(c != 2 or n > k))
            e.call(STOCK_FN, 0, 1, 1, max_steps=2000000)
            rows = [row for row in log if row[0] == 2]
            assert len(rows) == 6 and e.mem.u32(0x86A488) == 3 + max(0, 6 - failures)
            cases += 1
        # Always failing first or second list: the loop state never changes and it never returns.
        for category in (0, 1):
            e, log = stock_rig(elf, seed, script=lambda c, n, cat=category: int(c != cat))
            try:
                e.call(STOCK_FN, 0, 1, 1, max_steps=400000)
                raise AssertionError('returned with a generator that always fails')
            except Exception as error:   # EmuError wraps StepLimit
                assert isinstance(error, StepLimit) or 'step limit' in str(error), error
            rows = [row for row in log if row[0] == category]
            assert len(rows) > 500 and len({row[1:] for row in rows}) == 1
            cases += 1
    print('PASS failure retry same-budget, list 3 bounded, always-fail never returns cases=%d' % cases, flush=True)
    return cases + fit_cases(elf)


def first_budgets(level, difficulty):
    contract = S.budget_contract(level, difficulty)
    return [(category, contract['low'] + contract['steps'][category], contract['caps'][category])
            for category in (0, 1)]


def fit_cases(elf):
    """Can the real generator always fail at the smallest attempt budget?

    Reference: unchanged ref_items.generate_with_affixes (difftested on its own
    in difftest_items). Executed: original 0x104ca4 calls at the two extreme
    contexts, compared call by call with that reference at both seeds.
    """
    tables = I.Tables(elf)
    worst = None
    stall = None
    rejected = {'bit40': 0, 'duplicate': 0}
    total = 0
    for level, difficulty in itertools.product(range(12), range(1, 6)):
        for category, budget, cap in first_budgets(level, difficulty):
            for seed in SEEDS:
                game = I.Game(num_players=1, difficulty=difficulty)
                rng = I.Rng(seed)
                misses = run = longest = 0
                # Non-advancing in the original loop (stock_plan): a failed call, a weapon with
                # record flag bit 40, or a duplicate while fewer than six retries were spent.
                # Category 0 scans its whole list from the base, so the scan starts with the
                # four fixed weapon records (FIXED_WEAPONS, parsed first with the same seed, as
                # stock_plan does) and then its accepted records; residue bytes are packed as
                # zero. Category 1 scans the previous third list (other-category definitions),
                # modelled as no duplicate.
                accepted, retries, still, longest_still = [], 0, 0, 0
                if category == 0:
                    accepted = [I.parse_descriptor(tables, tables.exe.cstr(descriptor), -1, False, rng).pack()
                                for descriptor in S.FIXED_WEAPONS]
                fixed = len(accepted)
                for _ in range(20):
                    item = I.generate_with_affixes(tables, game, rng, budget, category, -1, cap)
                    advance = item is not None
                    if item is None:
                        misses += 1
                        run += 1
                        longest = max(longest, run)
                    else:
                        run = 0
                        raw = item.pack()
                        if category == 0 and any(S.same_raw(prev, raw) for prev in accepted) and retries < 6:
                            retries += 1
                            advance = False
                            rejected['duplicate'] += 1
                        if category == 0 and item.flags & (1 << 40):
                            advance = False
                            rejected['bit40'] += 1
                    if advance:
                        accepted.append(raw)
                        retries = still = 0
                    else:
                        still += 1
                        longest_still = max(longest_still, still)
                assert misses < 20 and len(accepted) > fixed, ('no advance', level, difficulty, category)
                key = (longest, level, difficulty, category, seed)
                worst = key if worst is None or key > worst else worst
                key = (longest_still, level, difficulty, category, seed)
                stall = key if stall is None or key > stall else stall
                total += 1
    executed = 0
    # The four fixed weapon records: original parser 0x1069b8 against the reference, both seeds.
    for seed in SEEDS:
        o = Original(elf, fast=True)
        o.set_game(I.Game(num_players=1), seed)
        rng = I.Rng(seed)
        for descriptor in S.FIXED_WEAPONS:
            want = I.parse_descriptor(tables, tables.exe.cstr(descriptor), -1, False, rng).pack()
            o.call(PARSE, descriptor, o.rec, -1 & 0xFFFFFFFFFFFFFFFF, 0)
            assert o.mem.read(o.rec, S.ITEM_SIZE) == want and o.seed() == rng.seed, hex(descriptor)
            executed += 1
    for (level, difficulty), seed in itertools.product(((0, 1), (11, 5)), SEEDS):
        for category, budget, cap in first_budgets(level, difficulty):
            o = Original(elf, fast=True)
            game = I.Game(num_players=1, difficulty=difficulty)
            o.set_game(game, seed)
            rng = I.Rng(seed)
            for _ in range(4):
                want = I.generate_with_affixes(tables, game, rng, budget, category, -1, cap)
                got = s32(o.call(GENERATE, o.rec, budget, category, -1 & 0xFFFFFFFFFFFFFFFF, cap))
                assert got == int(want is not None) and o.seed() == rng.seed
                executed += 1
    print('PASS fit contexts=%d longest_failure_run=%d at storeLevel=%d difficulty=%d category=%d seed=%d '
          'executed=%d' % ((total,) + worst + (executed,)), flush=True)
    print('PASS fit longest_non_advancing_run=%d at storeLevel=%d difficulty=%d category=%d seed=%d '
          'bit40_rejects=%d duplicate_rejects=%d (one player, seeds %s, difficulty 1..5; '
          'category-0 scan seeded with the 4 fixed weapons)' % (
              stall + (rejected['bit40'], rejected['duplicate'], '/'.join(map(str, SEEDS)))), flush=True)
    return total + executed


# ---- shop menu -----------------------------------------------------------------------------
class Shop:
    """mode-0 shop open, then original shop_task ticks with planted pad words.

    Stubs: local-slot test 0x13e150 -> 1, resource-ready 0x17306c -> 1,
    texture lookup 0x17365c -> a 32x32 header, item value 0x1024a8 -> 100,
    item weight 0x1b6338 -> 1.0, item picture size 0x1083a4 -> one cell; every
    other callee outside MENU_FOLLOW returns 0 and is recorded (drawing, text,
    sound, network, menu-state message, task registration). The sale cases in
    menu_cases also stub inventory_isEquipped 0x1c41d8 and hud_confirmBox 0x1dadc0
    to chosen returns; with region set, game_initCamera runs first (callees stubbed).
    """

    def __init__(self, elf, seed, players=1, list_mask=0x80, region=None, opener=0):
        e = self.e = EE(elf)
        m = self.m = e.mem
        m.auto_map = True
        m.w32(S.SHARED, seed)
        m.w32(NUM_PLAYERS, players)
        for slot in range(players):
            m.wf32(PLAYERS + slot * REC + 0xAC, 100.0)
            m.w32(PLAYERS + slot * REC + 0xE4, 1000)
            m.wf32(PLAYERS + slot * REC + 0x124, 100.0)
        e.follow = set()
        if region is not None:
            # game_initCamera 0x1e6b68 with its callees stubbed writes the three masks.
            m.w8(REGION, region)
            e.call(0x1E6B68, max_steps=100000)
            list_mask = None
        e.stub(0x13E150, ret=1)
        e.call(STOCK_FN, opener, 0, 1, max_steps=500000)
        tex = e.alloc(0x40)
        m.w16(tex, 32)
        m.w16(tex + 2, 32)
        e.stub(0x17306C, ret=1)
        e.stub(0x17365C, ret=tex)
        e.stub(VALUE, ret=100)
        e.stub(0x1B6338, function=lambda emu: emu.fset(0, 1.0) or 0)
        e.stub(0x1083A4, function=lambda emu: (m.w32(emu.r[6] & 0xFFFFFFFF, 0),
                                               m.w32(emu.r[7] & 0xFFFFFFFF, 34)) and 0)
        self.cells = e.alloc(0x23988 * 4)
        self.grid = e.alloc(0xBDD8 * 4)
        m.w32(CELLS, self.cells)        # what inventory_pollResources points it at
        m.w32(STOCK_CELLS, self.grid)
        if list_mask is not None:
            m.w32(S.LIST_CONFIRM_MASK, list_mask)
        self.definition = e.alloc(0x80)
        m.w8(self.definition + 0x1C, 1)
        for index in range(3):
            record = S.STOCK + index * S.ITEM_SIZE
            m.w32(record, self.definition)
            m.w16(record + 4, 1)
        m.w32(S.STOCK + 0x1200, 3)
        e.follow = set(MENU_FOLLOW)
        self.confirm, self.cancel = m.u32(S.CONFIRM_MASK), m.u32(S.CANCEL_MASK)

    def build(self, slot, bag, stock):
        """itemGrid_build 0x1cbbe8 with all its callees live except the size stub."""
        saved, self.e.follow = self.e.follow, None
        self.e.call(GRID, slot, bag, stock, max_steps=5000000)
        self.e.follow = saved

    def panel(self, index=0):
        base = S.PANELS + index * S.PANEL_STRIDE
        m = self.m
        return (m.s32(base + 0x4C), m.s32(base + 0x18), m.s32(base + 0x14), m.u32(base + 0x3C))

    def tick(self, press=0, held=0, slot=0, held10=None):
        """One shop_task call. ``held`` goes to pad +0x8 and, unless ``held10`` is given,
        also to +0x10."""
        m = self.m
        held10 = held if held10 is None else held10
        for other in range(4):
            pad = S.PAD + other * S.PAD_STRIDE
            m.w32(pad + 0xC, press if other == slot else 0)
            m.w32(pad + 0x8, held if other == slot else 0)
            m.w32(pad + 0x10, held10 if other == slot else 0)
        self.e.reset_log()
        self.e.call(SHOP_TASK, max_steps=5000000)
        return [c for c in self.e.calls]

    def targets(self, calls):
        return [c.target for c in calls]

    def move(self, held, held10=None):
        ticks = 0
        start = self.panel()[1]
        while self.panel()[1] == start and ticks < 40:
            self.tick(held=held if ticks == 0 else 0, held10=(held10 if ticks == 0 else 0)
                      if held10 is not None else None)
            ticks += 1
        return ticks


def buy_outcome(shop, calls):
    """Classify one list confirm over a stock cell by the calls it made."""
    names = shop.targets(calls)
    sites = {(c.target, c.site) for c in calls}
    if SEND_BUY in names:
        assert (SOUND, 0x1CE19C) in sites and (BUY_TAIL, 0x1CE1B4) in sites
        assert names.index(SEND_BUY) < names.index(BUY_TAIL)
        return 'send'
    assert BUY_TAIL not in names
    if POPUP in names:
        return 'weight' if 0x1B7BA8 in names else 'gold'
    assert (SOUND, 0x1CE148) in sites, 'a full bag plays the sound at 0x1ce148'
    return 'full'


def sale_message(elf, seed, opener, slot, panel):
    """One unequipped sale (0x1c41d8 stubbed to 0) from ``slot`` on ``panel`` in a two-player
    shop opened by ``opener``; returns the 13 message bytes sent through 0x13db38."""
    shop = Shop(elf, seed, players=2, opener=opener)
    m = shop.m
    if panel == 1:
        shop.tick(press=shop.confirm, slot=slot)
    assert m.s32(S.PANELS + panel * S.PANEL_STRIDE + 0x34) == slot
    base = PLAYERS + slot * REC
    m.w32(base + 0x130, shop.definition)
    m.w16(base + 0x134, 1)
    m.w32(base + 0x1330, 1)
    player_object = shop.e.alloc(0x500)
    m.w32(base + OBJECT_PTR, player_object)
    for ticks in range(40):
        if shop.panel(panel)[1] == 1:
            break
        shop.tick(held=0x4000 if ticks == 0 else 0, slot=slot)
    calls = shop.tick(press=shop.confirm, slot=slot)
    view = [c for c in calls if c.target == BAGS_VIEW]
    assert shop.panel(panel)[0] == S.MENU_SELL and len(view) == 1 and view[0].args[:3] == (slot, panel, 0)
    shop.build(slot, panel, 0)                   # itemGrid_build(slot, panel, stock), as the join calls it
    m.wf32(BAG_PANEL + panel * 0x74 + 0x44, 16.0)
    m.wf32(BAG_PANEL + panel * 0x74 + 0x48, 96.0)
    shop.e.stub(0x1C41D8, ret=0)
    fill = []

    def prefill(emu):
        address = (emu.r[29] & 0xFFFFFFFF) + 0x10
        emu.mem.write(address, b'\xa5' * 13)
        fill.append(address)
    shop.e.hook(SALE_STORES, prefill)
    calls = shop.tick(press=0x80, slot=slot)
    sent = [c for c in calls if c.target == NET_SEND]
    assert len(sent) == 1 and sent[0].args[2] == 0xD and fill == [sent[0].args[1] & 0xFFFFFFFF]
    assert m.u8(player_object + LATCH) == 1
    message = m.read(sent[0].args[1] & 0xFFFFFFFF, 13)
    assert 0xA5 not in message, message.hex()
    return message


def menu_cases(elf):
    cases = 0
    for seed in SEEDS:
        shop = Shop(elf, seed)
        m = shop.m
        confirm, cancel = shop.confirm, shop.cancel
        assert (confirm, cancel, m.u32(S.LIST_CONFIRM_MASK)) == (0x40, 0x120, 0x80)
        assert shop.panel(0)[0] == S.MENU_CHOICE and shop.panel(1)[0] == S.MENU_IDLE
        assert m.s32(S.PANELS + 0x34) == 0 and m.s32(S.PANELS + S.PANEL_STRIDE + 0x34) == -1
        assert m.u32(SHOP_OPEN) == 1 and m.u32(PAUSE) == 1
        shop.tick()
        assert shop.panel() == (3, 0, 0, 0)
        # Executed reads: the choice reads pad +0x8 only at 0x1c6454 (helper 0x1c6438) and
        # +0xc; never +0x10. Every choice tick stores +0x18 into +0x54 at 0x1c6c3c.
        shop.e.reads = []
        m.w32(S.PANELS + 0x54, 7)
        shop.tick(held=0, held10=0x4000)
        pad_reads = {(pc, address - S.PAD) for pc, address, _size, _value in shop.e.reads
                     if S.PAD <= address < S.PAD + 0x58}
        shop.e.reads = None
        assert (0x1C6454, 0x8) in pad_reads and not any(off == 0x10 for _pc, off in pad_reads), pad_reads
        assert [(pc, value) for pc, address, _size, value in shop.e.writes
                if address == S.PANELS + 0x54] == [(0x1C6C3C, 0)] and m.u32(S.PANELS + 0x54) == 0
        cases += 2
        shop.tick(held=0x1000)                       # up at the top row
        assert shop.panel() == (3, 0, 0, 0)
        shop.tick(held=0, held10=0x4000)             # down on +0x10 alone: the cursor reads +0x8
        assert shop.panel() == (3, 0, 0, 0)
        shop.tick(held=0x4000, held10=0)             # down on +0x8 alone starts the animation
        assert shop.panel() == (3, 0, 1, S.CURSOR_STEP)
        shop.tick(press=confirm)                     # confirm mid-animation is ignored
        assert shop.panel()[0] == 3
        ticks = 2
        while shop.panel()[1] == 0:
            shop.tick()
            ticks += 1
        assert ticks == S.CURSOR_TICKS and shop.panel() == (3, 1, 0, 0)
        m.w32(S.PANELS + 0x54, 7)
        shop.tick()
        assert [(pc, value) for pc, address, _size, value in shop.e.writes
                if address == S.PANELS + 0x54] == [(0x1C6C3C, 1)] and m.u32(S.PANELS + 0x54) == 1
        cases += 1
        shop.tick(held=0x4000)                       # down at the last row
        assert shop.panel() == (3, 1, 0, 0)
        # The analogue bits, each alone on +0x8: 0x100000 up, 0x200000 down.
        assert shop.move(0x100000, held10=0) == S.CURSOR_TICKS and shop.panel() == (3, 0, 0, 0)
        shop.tick(held=0x100000, held10=0)
        assert shop.panel() == (3, 0, 0, 0)
        assert shop.move(0x200000, held10=0) == S.CURSOR_TICKS and shop.panel() == (3, 1, 0, 0)
        shop.tick(held=0x200000, held10=0)
        assert shop.panel() == (3, 1, 0, 0)
        calls = shop.tick(press=confirm)
        assert shop.panel()[0] == S.MENU_SELL and BAGS_VIEW in shop.targets(calls)
        assert any(c.target == MENU_RESET and c.site == 0x1C6E50 for c in calls)
        bag_view = next(c for c in calls if c.target == BAGS_VIEW)
        assert bag_view.args[:3] == (0, 0, 0) and m.s32(S.PANELS + 0x54) == 1
        # Saved row sentinel: +0x18 is 1, +0x54 planted 0; cancel restores 0 and its offset.
        m.w32(S.PANELS + 0x54, 0)
        calls = shop.tick(press=cancel)
        assert shop.panel()[:2] == (S.MENU_CHOICE, 0) and m.s32(S.PANELS + 0x24) == 0
        assert any(c.target == SOUND and c.site == 0x1CDB34 for c in calls)
        assert shop.move(0x4000) == S.CURSOR_TICKS and shop.panel() == (3, 1, 0, 0)
        assert shop.move(0x1000) == S.CURSOR_TICKS and shop.panel() == (3, 0, 0, 0)
        calls = shop.tick(press=confirm)
        assert shop.panel()[0] == S.MENU_BUY and BAGS_VIEW not in shop.targets(calls)
        assert any(c.target == MENU_RESET and c.site == 0x1C6D70 for c in calls)
        cases += 17
        # Buy: list confirm mask 0x41b970 over a stock cell; boundary rows.
        shop.build(0, 0, 1)
        m.wf32(S.PANELS + 0x44, 48.0)
        m.wf32(S.PANELS + 0x48, 96.0)
        price = S.buy_price(100, 0, 0, 0)
        assert price == 59
        outcomes = []
        for gold, count, carried, expected in BUY_ROWS:
            m.w32(PLAYERS + 0xE4, gold & 0xFFFFFFFF)
            m.w32(PLAYERS + 0x1330, count & 0xFFFFFFFF)
            m.wf32(PLAYERS + 0x120, carried)
            calls = shop.tick(press=0x80)
            got = buy_outcome(shop, calls)
            want = S.buy_allowed(gold, price, count, I.f_bits(carried), I.F_ONE, I.f_bits(100.0))
            assert got == want == expected, (gold, count, carried, got, want, expected)
            sent = [c for c in calls if c.target == SEND_BUY]
            if sent:
                cell = sent[0].args[1] & 0xFFFFFFFF
                assert sent[0].args[0] == 0 and shop.grid <= cell < shop.grid + 0xBDD8
                assert m.u32(cell) == shop.definition
            assert m.s32(PLAYERS + 0xE4) == gold, 'the sender does not debit'
            outcomes.append(got)
            cases += 1
        m.w32(PLAYERS + 0xE4, 1000)
        m.w32(PLAYERS + 0x1330, 0)
        m.wf32(PLAYERS + 0x120, 0.0)
        # Over the stock cell, itemList_input reads pad +0x10 at 0x1cdfcc (and +0xc at 0x1cdfa0);
        # the list confirm mask held on +0x10 alone does not buy, and the list writes no +0x54.
        shop.e.reads = []
        calls = shop.tick(held=0, held10=0x80)
        pad_reads = {(pc, address - S.PAD) for pc, address, _size, _value in shop.e.reads
                     if S.PAD <= address < S.PAD + 0x58}
        shop.e.reads = None
        assert {(0x1CDFCC, 0x10), (0x1CDFA0, 0xC)} <= pad_reads, pad_reads
        assert SEND_BUY not in shop.targets(calls) and shop.panel()[0] == S.MENU_BUY
        assert not any(address == S.PANELS + 0x54 for _pc, address, _size, _value in shop.e.writes)
        cases += 2
        # Confirm (0x40) is not the list mask: no buy.
        assert SEND_BUY not in shop.targets(shop.tick(press=confirm))
        # Input lockout, state 0: the real pad is ignored and the list reads 0x86a6b0.
        assert all(EE(elf).mem.u32(ZERO_PAD + off) == 0 for off in range(0, 0x58, 4)), 'loaded image'
        m.w32(LOCKOUT, 60)
        shop.tick(press=cancel)
        assert shop.panel()[0] == S.MENU_BUY
        m.w32(S.PANELS + 0x18, 0)
        m.w32(S.PANELS + 0x54, 1)                    # saved row sentinel (+0x18 is 0)
        m.w32(ZERO_PAD + 0xC, cancel)
        shop.tick()
        assert shop.panel()[:2] == (S.MENU_CHOICE, 1) and m.s32(S.PANELS + 0x24) == 39
        m.w32(ZERO_PAD + 0xC, 0)
        m.w32(LOCKOUT, 0)
        assert shop.move(0x1000) == S.CURSOR_TICKS and shop.panel() == (3, 0, 0, 0)
        shop.tick(press=confirm)
        assert shop.panel()[0] == S.MENU_BUY
        shop.tick(press=cancel)                      # cancel works again after the lockout
        assert shop.panel()[:2] == (S.MENU_CHOICE, 0)
        cases += 4
        # Sell: one item in bag 0, cursor in the bag panel, a player object at +0x43d8.
        record = PLAYERS + 0x130
        m.w32(record, shop.definition)
        m.w16(record + 4, 1)
        m.w32(PLAYERS + 0x1330, 1)
        player_object = shop.e.alloc(0x500)
        m.w32(PLAYERS + OBJECT_PTR, player_object)
        m.w8(LATCH, 0x5A)                            # absolute 0x47a: must stay untouched
        shop.build(0, 0, 0)
        shop.move(0x4000)
        shop.tick(press=confirm)
        assert shop.panel()[0] == S.MENU_SELL
        m.wf32(BAG_PANEL + 0x44, 16.0)
        m.wf32(BAG_PANEL + 0x48, 96.0)
        fill = []

        def prefill(emu):
            # The 13 message bytes at sp+0x10 get 0xa5 before the stores at 0x1ce4fc-0x1ce524.
            base = (emu.r[29] & 0xFFFFFFFF) + 0x10
            emu.mem.write(base, b'\xa5' * 13)
            fill.append(base)
        shop.e.hook(SALE_STORES, prefill)
        # (unsellable flag, equipped, prompt result) -> sent? STUBBED inputs: 0x1c41d8
        # (equipped-item test) returns `equipped`, and 0x1dadc0 (yes/no prompt) returns
        # `answer` (0 while open, 1 no, 2 yes); neither function runs.
        for flags, equipped, answer, want in ((1 << 38, 0, 0, 'refused'), (0, 1, 0, 'waiting'),
                                              (0, 1, 1, 'declined'), (0, 1, 2, 'sent'), (0, 0, 0, 'sent')):
            m.w64(record + 8, flags)
            shop.build(0, 0, 0)                       # the list shows a copy of the bag record
            m.w8(player_object + LATCH, 0)
            m.w32(SELL_PENDING, 0)
            m.w32(BLOCK_B, 0)
            m.w32(LIST_STATE, 0)
            del fill[:]
            shop.e.stub(0x1C41D8, ret=equipped)
            shop.e.stub(CONFIRM_DIALOG, ret=answer)
            calls = shop.tick(press=0x80)
            names = shop.targets(calls)
            sent = [c for c in calls if c.target == NET_SEND]
            if want == 'refused':
                assert not sent and POPUP in names and m.u32(SELL_PENDING) == 0
            elif want == 'waiting':
                assert not sent and CONFIRM_DIALOG in names and m.u32(SELL_PENDING) == 1
                assert m.u32(BLOCK_B) == 100
                # A pending sale holds the list's cancel.
                shop.tick(press=cancel)
                assert shop.panel()[0] == S.MENU_SELL
            elif want == 'declined':
                assert not sent and m.u32(SELL_PENDING) == 0 and m.u32(BLOCK_B) == 0
                assert m.u32(LIST_STATE) == 3
            else:
                assert len(sent) == 1 and m.u32(SELL_PENDING) == 0 and m.u32(LIST_STATE) == 3
                assert m.u8(player_object + LATCH) == 1 and m.u8(LATCH) == 0x5A and sent[0].args[2] == 0xD
                message = m.read(sent[0].args[1] & 0xFFFFFFFF, 13)
                assert fill == [sent[0].args[1] & 0xFFFFFFFF] and 0xA5 not in message, message.hex()
                assert message[0] == 1 and message[1] == 0 and message[0xB] == 0 and message[0xC] == 1
                assert any(c.target == BUY_TAIL and c.site == 0x1CE528 for c in calls)
                assert NET_SEND not in shop.targets(shop.tick(press=0x80)), 'latch holds a second sale'
            cases += 1
        shop.e.unhook(SALE_STORES)
        m.w32(SELL_PENDING, 0)
        m.w32(BLOCK_B, 0)
        # Input lockout, state 1: the real pad is ignored and the list reads 0x86a6b0.
        m.w32(LOCKOUT, 60)
        shop.tick(press=cancel)
        assert shop.panel()[0] == S.MENU_SELL
        m.w32(ZERO_PAD + 0xC, cancel)
        shop.tick()
        assert shop.panel()[0] == S.MENU_CHOICE
        m.w32(ZERO_PAD + 0xC, 0)
        m.w32(LOCKOUT, 0)
        cases += 2
        # A nonzero panel word at 0x4f4878 or 0x4f4880 blocks the choice cancel.
        for block in (BLOCK_A, BLOCK_B):
            m.w32(block, 1)
            shop.tick(press=cancel)
            assert shop.panel()[0] == S.MENU_CHOICE
            m.w32(block, 0)
            cases += 1
        # Cancel at the choice: state 2 on this tick, the close on the next.
        names = shop.targets(shop.tick(press=cancel))
        assert shop.panel()[0] == S.MENU_IDLE and SHOP_CLOSE not in names and HUD_MENU_STATE not in names
        assert m.u32(SHOP_OPEN) == 1
        calls = shop.tick()
        names = shop.targets(calls)
        menu_state = [c for c in calls if c.target == HUD_MENU_STATE]
        assert len(menu_state) == 1 and menu_state[0].site == 0x1C7690 and menu_state[0].args[:3] == (0, 0, 0)
        assert names.index(HUD_MENU_STATE) < names.index(SHOP_CLOSE)
        assert any(c.target == TASK_REMOVE and (c.args[0] & 0xFFFFFFFF) == SHOP_TASK for c in calls)
        assert m.u32(SHOP_OPEN) == 0 and m.u32(LOCKOUT) == 60 and m.u32(PAUSE) == 0
        assert m.u32(S.SHARED) == seed
        cases += 2
        # Death: shop_task tests HP only on the offline two-player path.
        shop = Shop(elf, seed)
        shop.m.wf32(PLAYERS + 0xAC, 0.0)
        names = shop.targets(shop.tick()) + shop.targets(shop.tick())
        assert SHOP_CLOSE not in names and shop.panel()[0] == S.MENU_CHOICE
        shop = Shop(elf, seed, players=2)
        shop.m.wf32(PLAYERS + 0xAC, 0.0)
        names = shop.targets(shop.tick()) + shop.targets(shop.tick())
        assert SHOP_CLOSE in names and shop.m.u32(SHOP_OPEN) == 0
        cases += 2
        # Two players: the second joins on confirm; the shop closes only when both are idle.
        # The offline two-player tick runs shop_run(1) then shop_run(0) (0x1c61ac, 0x1c61b4),
        # and a run closes when its own panel starts in state 2 with both panels at 2.
        for first, last, same_tick in ((0, 1, True), (1, 0, False)):
            shop = Shop(elf, seed, players=2)
            m = shop.m
            runs = []
            shop.e.hook(0x1C74C0, lambda emu: runs.append((s32(emu.r[4]), (emu.r[31] - 8) & 0xFFFFFFFF)))
            calls = shop.tick(press=shop.confirm, slot=1)
            assert runs == [(1, 0x1C61AC), (0, 0x1C61B4)], runs
            assert shop.panel(1)[0] == S.MENU_CHOICE and m.s32(S.PANELS + S.PANEL_STRIDE + 0x34) == 1
            assert any(c.target == GRID for c in calls)
            names = shop.targets(shop.tick(press=shop.cancel, slot=first))
            assert shop.panel(first)[0] == S.MENU_IDLE and SHOP_CLOSE not in names
            assert SHOP_CLOSE not in shop.targets(shop.tick()) and m.u32(SHOP_OPEN) == 1
            names = shop.targets(shop.tick(press=shop.cancel, slot=last))
            assert shop.panel(last)[0] == S.MENU_IDLE and (SHOP_CLOSE in names) == same_tick
            if not same_tick:
                assert m.u32(SHOP_OPEN) == 1
                del runs[:]
                calls = shop.tick()
                names = shop.targets(calls)
                assert runs == [(1, 0x1C61AC), (0, 0x1C61B4)], runs
            assert SHOP_CLOSE in names and HUD_MENU_STATE in names and m.u32(SHOP_OPEN) == 0
            assert all(c.site == 0x1C7690 and c.args[:3] == (0, 0, 0)
                       for c in shop.e.calls if c.target == HUD_MENU_STATE)
            shop.e.unhook(0x1C74C0)
            cases += 3
        # A sale from other slots and panels: byte 1 is the selling slot, byte 0xb the panel.
        for opener, slot, panel in ((1, 1, 0), (0, 1, 1), (1, 0, 1)):
            message = sale_message(elf, seed, opener, slot, panel)
            assert message[0] == 1 and message[1] == slot and message[0xB] == panel and message[0xC] == 1, (
                opener, slot, panel, message.hex())
            cases += 1
        # A shop opened by slot 1 closes with the same 0x1de0dc(0, 0, 0) at 0x1c7690.
        shop = Shop(elf, seed, players=2, opener=1)
        assert shop.m.s32(S.PANELS + 0x34) == 1
        shop.tick(press=shop.cancel, slot=1)
        calls = shop.tick()
        menu_state = [c for c in calls if c.target == HUD_MENU_STATE]
        assert menu_state and all(c.site == 0x1C7690 and c.args[:3] == (0, 0, 0) for c in menu_state)
        assert shop.m.u32(SHOP_OPEN) == 0
        cases += 1
        # Sentinel masks: the choice confirms with 0x41bfbc; the choice and both lists cancel with 0x41bfb8.
        shop = Shop(elf, seed)
        m = shop.m
        others = (m.u32(S.LIST_CONFIRM_MASK), m.u32(0x41B960), m.u32(0x41B968))
        new_confirm, new_cancel = 0x10000, 0x20000
        assert not any(value & (new_confirm | new_cancel) for value in others)
        m.w32(S.CONFIRM_MASK, new_confirm)
        m.w32(S.CANCEL_MASK, new_cancel)
        shop.tick()
        for press, want in ((0x40, S.MENU_CHOICE), (0x120, S.MENU_CHOICE), (new_confirm, S.MENU_BUY),
                            (0x120, S.MENU_BUY), (0x40, S.MENU_BUY), (new_cancel, S.MENU_CHOICE),
                            (0x120, S.MENU_CHOICE)):
            shop.tick(press=press)
            assert shop.panel()[0] == want, (hex(press), shop.panel())
            cases += 1
        # The own-bags list (state 1) also cancels only with the planted 0x41bfb8 bits.
        assert shop.move(0x4000) == S.CURSOR_TICKS and shop.panel()[:2] == (S.MENU_CHOICE, 1)
        for press, want in ((new_confirm, S.MENU_SELL), (0x120, S.MENU_SELL), (0x40, S.MENU_SELL),
                            (new_cancel, S.MENU_CHOICE), (new_cancel, S.MENU_IDLE)):
            shop.tick(press=press)
            assert shop.panel()[0] == want, (hex(press), shop.panel())
            cases += 1
        # Region 1 masks from game_initCamera in the same machine: a lone 0x20 cancels.
        shop = Shop(elf, seed, region=1)
        m = shop.m
        assert (shop.confirm, shop.cancel, m.u32(S.LIST_CONFIRM_MASK)) == (0x40, 0x20, 0x80)
        shop.tick()
        for press, want in ((0x100, S.MENU_CHOICE), (0x40, S.MENU_BUY), (0x100, S.MENU_BUY),
                            (0x20, S.MENU_CHOICE), (0x100, S.MENU_CHOICE)):
            shop.tick(press=press)
            assert shop.panel()[0] == want, (hex(press), shop.panel())
            cases += 1
        # Region 1, own-bags list: a lone 0x20 cancels it, 0x100 does not.
        assert shop.move(0x4000) == S.CURSOR_TICKS and shop.panel()[:2] == (S.MENU_CHOICE, 1)
        for press, want in ((0x40, S.MENU_SELL), (0x100, S.MENU_SELL), (0x20, S.MENU_CHOICE),
                            (0x20, S.MENU_IDLE)):
            shop.tick(press=press)
            assert shop.panel()[0] == want, (hex(press), shop.panel())
            cases += 1
        assert SHOP_CLOSE in shop.targets(shop.tick()) and m.u32(SHOP_OPEN) == 0
        cases += 1
    # hudmsg_sendMenuState 0x1de0dc run live: offline (0x402791 = 0) it sends nothing; a
    # net game sends one 4-byte message of type 2 (docs/ui.md:87).
    e = EE(elf)
    e.mem.auto_map = True
    e.follow = set()
    for net in (0, 1):
        e.mem.w8(NET_FLAG, net)
        e.reset_log()
        e.call(HUD_MENU_STATE, 0, 0, 0, max_steps=10000)
        sends = [c for c in e.calls if c.target == NET_SEND]
        assert len(sends) == net
        if net:
            assert sends[0].args[2] == 4 and e.mem.read(sends[0].args[1] & 0xFFFFFFFF, 4) == bytes((2, 0, 0, 0))
    for args in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (3, 5, 7)):
        e.reset_log()
        e.call(HUD_MENU_STATE, *args, max_steps=10000)
        sends = [c for c in e.calls if c.target == NET_SEND]
        assert len(sends) == 1 and e.mem.read(sends[0].args[1] & 0xFFFFFFFF, 4) == bytes((2,) + args), args
        cases += 1
    # Region masks from game_initCamera 0x1e6b68, every byte value. The .data byte is 1.
    assert EE(elf).mem.u8(REGION) == 1
    masks = {}
    for region in range(256):
        e = EE(elf)
        e.mem.auto_map = True
        e.follow = set()
        e.mem.w8(REGION, region)
        e.call(0x1E6B68, max_steps=100000)
        masks[region] = tuple(e.mem.u32(a) for a in (S.CONFIRM_MASK, S.CANCEL_MASK, S.LIST_CONFIRM_MASK))
    static = (0x40, 0x120, 0)
    assert masks[0] == (0x20, 0x140, 0) and masks[1] == (0x40, 0x20, 0x80), masks
    assert all(masks[r] == static for r in range(2, 256)), {r: v for r, v in masks.items() if r > 1 and v != static}
    print('PASS menu cases=%d masks region0=%s region1=%s bytes2..255=%s (static)' % (
        cases, *(','.join('0x%x' % v for v in row) for row in (masks[0], masks[1], static))), flush=True)
    return cases + 256 + 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--disc', required=True)
    parser.add_argument('--only', choices=('store', 'acts', 'failure', 'menu'))
    args = parser.parse_args()
    assert sha(args.elf) == EXPECTED_SHA256, 'executable digest'
    groups = (('store', lambda: store_level_cases(args.elf, args.disc)),
              ('acts', lambda: act_cases(args.elf)),
              ('failure', lambda: failure_cases(args.elf)),
              ('menu', lambda: menu_cases(args.elf)))
    total = 0
    for name, run in groups:
        if args.only and name != args.only:
            continue
        count = run()
        total += count
        print('PASS %s cases=%d' % (name, count), flush=True)
    print('PASS total=%d mismatches=0' % total)


if __name__ == '__main__':
    main()
