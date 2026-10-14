#!/usr/bin/env python3
"""fp_section_test.py - the section of tools/recomp/app/fp-proposed.pnach ("strafe mode") in the
function-level interpreter, against the game as shipped.

  python3 tools/recomp/app/fp_section_test.py [path/to/SLUS_209.73]

W. The words: every patched address still holds the word the file's "// was:" lines quote; the
   three functions the code is put into are referred to by nothing; no address of the section is
   touched by any other section (patches/SLUS-20973_4028A55F.pnach,
   tools/recomp/soak/proposed-sections.pnach).
M. Player_move 0x1b4020 on the fake player of tools/ee_tests.py (MoveRig: trigonometry, angle
   approach, yaw look-up run for real; animation, water and the move itself are stubs).  With
   the mode byte (player +0x47e) clear: every mode 0..6, sticks, yaw words, facings, offline and
   net - the whole player object, the pad and the vector handed to the move are the same bytes
   with and without the section.  With the byte set: modes 1..6 are still the same bytes; in
   mode 0 the facing goes 40 % of the way to 0x3e3d - yaw word (the game's own angle_approach,
   run beside it) also with the stick at rest, and the velocity is, to the bit, the one the
   shipped game gives a character that already faces the stick's direction.
H. The handler of game message 4 (0x1e01b0): sub-type 2 {2, slot, mode} stores the mode in that
   slot's player object and nothing else; the game's own messages on the channel ({0}, {1, slot}),
   a slot of 4 or more and a slot without an object store nothing.
S. The sender (0x215c98): one net_sendGameMsg(channel id, {2, local slot, mode}, 3); stack and
   saved registers kept.
C. The two words in Player_ctor (0x1a22fc): +0x47c, +0x47d cleared as shipped, +0x47e as well,
   +0x47f untouched.

PASS/FAIL lines as tools/ee_tests.py prints them.  One function on a prepared state: this shows
what the code does there; docs/issues/native-first-person-controls.md part 3 has the runs on
two, three and four machines.
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import ee_tests  # noqa: E402
from ee_emu import EE  # noqa: E402

PNACH = os.path.join(HERE, 'fp-proposed.pnach')
SECTION = 'strafe mode'
OTHERS = [os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach'), os.path.join(ROOT, 'tools', 'recomp', 'soak', 'proposed-sections.pnach')]
PLAYER_MOVE, ANGLE_APPROACH, HANDLER, SENDER, CTOR_WORDS = 0x1B4020, 0x166C18, 0x1E01B0, 0x215C98, 0x1A22FC
GET_LOCAL_SLOT, SEND_GAME_MSG, CHANNEL_ID = 0x13E1F0, 0x13DB38, 0x86AA60
CAVES = ((0x2128C8, 0x21297C), (0x215C98, 0x215D28), (0x215D28, 0x215DA4))
MODE = 0x47E
M32 = 0xFFFFFFFF
FAILED = []


def check(ident, ok, text):
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    if not ok:
        FAILED.append(ident)


def section_words(path, section=None, skip=None):
    """{address: word} of a patch file (one section, or all, or all but the one named by skip), and the "// was:"
    words in file order."""
    words, was, inside = {}, [], section is None
    for line in open(path, errors='replace'):
        line = line.strip()
        if line.startswith('['):
            inside = (section is None or section in line) and not (skip is not None and skip in line)
        elif inside and line.startswith('patch='):
            f = line.split(',')
            words[int(f[2], 16)] = int(f[4], 16)
        elif inside and section is not None and '// ' in line and 'was:' in line:
            was.append(re.findall(r'\b[0-9A-F]{8}\b', line.split('was:', 1)[1]))
    return words, was


# ---- W ------------------------------------------------------------------------------------------
def test_words(elf):
    data = open(elf, 'rb').read()
    segments = ((0x100000, 0x1000, 3054524), (0x3E9C00, 3058688, 1549984))
    word = lambda a: struct.unpack_from('<I', data, a - 0x100000 + 0x1000)[0]
    words, was = section_words(PNACH, SECTION)
    check('W1', len(words) == 84, 'the section has %d words' % len(words))
    blocks, run = [], []
    for a in sorted(words):                         # consecutive addresses are one block; the file quotes each block's old words
        if run and a != run[-1] + 4:
            blocks.append(run)
            run = []
        run.append(a)
    blocks.append(run)
    quoted = sorted(tuple(int(w, 16) for w in group) for group in was)
    held = sorted(tuple(word(a) for a in block) for block in blocks)
    check('W2', quoted == held, 'the %d blocks of the section stand on the words its "// was:" lines quote (%d words of the game as shipped)' % (len(blocks), sum(map(len, held))))
    outside = []
    for lo, hi in CAVES:
        for va, off, size in segments:
            ws = struct.unpack_from('<%dI' % (size // 4), data, off)
            for i, w in enumerate(ws):
                a = va + i * 4
                if lo <= a < hi:
                    continue
                op = w >> 26
                if va == 0x100000 and op in (2, 3) and lo <= ((w & 0x3FFFFFF) << 2) < hi:
                    outside.append((a, 'jump'))
                elif va == 0x100000 and (op in (1, 4, 5, 6, 7, 20, 21, 22, 23) or (op == 17 and ((w >> 21) & 31) == 8)) and \
                        lo <= a + 4 + (((w & 0xFFFF) ^ 0x8000) - 0x8000) * 4 < hi:
                    outside.append((a, 'branch'))
                elif lo <= w < hi and not w & 3:
                    outside.append((a, 'word'))
    check('W3', not outside, 'nothing in the executable refers to the three functions the code is put into (0x2128c8, 0x215c98, 0x215d28): no jump, no branch from outside, '
                             'no word holding an address inside them%s' % ('' if not outside else ' - FOUND %s' % outside[:4]))
    clash = []
    for other in OTHERS:
        if os.path.exists(other):
            theirs, _ = section_words(other, skip=SECTION)     # the fix set holds this section itself since its adoption
            clash += ['%08x in %s' % (a, os.path.basename(other)) for a in theirs if a in words or any(lo <= a < hi for lo, hi in CAVES)]
    check('W4', not clash, 'no address of the section, and none inside the three functions, is patched by any other section of the fix set or of the soak\'s proposals%s' % (
        '' if not clash else ' - CLASH %s' % clash[:4]))
    senders = [a for a in range(0x100000, 0x100000 + 3054524, 4) if word(a) in (0x0C000000 | (0x1E0134 >> 2), 0x08000000 | (0x1E0134 >> 2), 0x0C000000 | (0x1E0108 >> 2), 0x08000000 | (0x1E0108 >> 2))]
    check('W5', senders == [0x1D0B70], 'the game itself sends on this channel from one place: the jump at 0x1d0b70 to nullmsg_sendShopClosed (sub-type 1); nullmsg_send0 (sub-type 0) has no caller')


# ---- M ------------------------------------------------------------------------------------------
def one_move(elf, patched, network, mode, lx, ly, yaw, facing, byte, preset_facing=None):
    rig = ee_tests.MoveRig(elf, network=network, yaw=yaw, facing=facing if preset_facing is None else preset_facing)
    if patched:
        assert rig.emu.apply_pnach(PNACH, SECTION) == 84
    rig.mem.w8(rig.player + MODE, byte)
    if mode == 5:
        rig.mem.map(0, 0x1000)          # mode 5 takes its velocity from a vector; the rig passes none: a zero vector at address 0
    result = rig.move(lx, ly, mode)
    obj = bytes(rig.mem.read(rig.player, 0x590))
    pad = bytes(rig.mem.read(rig.pad, 0x58))
    return result, obj, pad, tuple(rig.moved), rig.emu.r[2] & M32


def approach(elf, cur, target):
    emu = EE(elf)
    emu.call(ANGLE_APPROACH, cur & M32, target & M32, fargs=(0.39999998, -1.0, -1.0))
    return ee_tests.sx16(emu.r[2]) if hasattr(ee_tests, 'sx16') else ((emu.r[2] + 0x8000) & 0xFFFF) - 0x8000


def test_move(elf):
    sticks = [(0.0, 0.0), (0.0, -0.0120), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0), (0.0, 0.9884), (0.7, -0.7), (-0.31, 0.52), (0.0, -0.0085), (0.2, 0.05)]
    yaws = [0x2000, -0x2000 & 0xFFFF, 0x7FFE, 0x0001]
    facings = [0, 0x4000, 0x9234]
    same = cases = 0
    first = None
    for network in (False, True):
        for mode in range(7):
            for lx, ly in sticks:
                for yaw in yaws:
                    for facing in facings[:2 if mode else 3]:
                        cases += 1
                        a = one_move(elf, False, network, mode, lx, ly, yaw, facing, 0)
                        b = one_move(elf, True, network, mode, lx, ly, yaw, facing, 0)
                        if a == b:
                            same += 1
                        elif first is None:
                            first = (network, mode, lx, ly, yaw, facing)
    check('M1', same == cases, 'mode byte 0: Player_move in modes 0..6, %d sticks x %d yaw words x facings, offline and net - %d of %d calls leave the same player object, pad, '
                               'move vector and return value with the section as without%s' % (len(sticks), len(yaws), same, cases, '' if first is None else ' (first difference: %s)' % (first,)))
    same = cases = 0
    for network in (False, True):
        for mode in range(1, 7):
            for lx, ly in sticks:
                for yaw in yaws[:2]:
                    cases += 1
                    a = one_move(elf, False, network, mode, lx, ly, yaw, 0x1234, 1)
                    b = one_move(elf, True, network, mode, lx, ly, yaw, 0x1234, 1)
                    same += a == b
    check('M2', same == cases, 'mode byte 1, modes 1..6 (the states where the stick only turns, skills, the rush): %d of %d calls the same bytes with the section as without' % (same, cases))
    good = cases = 0
    bad = None
    for network in (False, True):
        for lx, ly in sticks:
            for yaw in yaws:
                for facing in facings:
                    cases += 1
                    b = one_move(elf, True, network, 0, lx, ly, yaw, facing, 1)
                    look = (0x3E3D - yaw) & 0xFFFF
                    want_facing = approach(elf, facing, look)
                    # the shipped game for a character already facing the stick's direction: its velocity is along the stick
                    import math
                    stick_angle = None
                    probe = one_move(elf, False, network, 0, lx, ly, yaw, facing, 0)
                    moving = probe[0][0] > 0
                    if moving:
                        # the facing the shipped game turns to with this stick: run it until it stops turning
                        f = facing
                        for _ in range(64):
                            nf = one_move(elf, False, network, 0, lx, ly, yaw, f, 0)[0][2]
                            if nf == f:
                                break
                            f = nf
                        settled = one_move(elf, False, network, 0, lx, ly, yaw, f, 0)
                        # the settled facing is within 2 units of the stick's direction T; the section uses T itself
                        ok_velocity = math.hypot(struct.unpack('<f', struct.pack('<I', b[0][3][0]))[0] - struct.unpack('<f', struct.pack('<I', settled[0][3][0]))[0],
                                                 struct.unpack('<f', struct.pack('<I', b[0][3][1]))[0] - struct.unpack('<f', struct.pack('<I', settled[0][3][1]))[0]) <= 180.0 * 3 * 2 * math.pi / 65536 + 1e-3 \
                            and abs(b[0][0] - settled[0][0]) < 1e-3
                    else:
                        ok_velocity = b[0][3] == (0, 0) or b[0][0] == 0
                    ok = ((b[0][2] - want_facing) & 0xFFFF) == 0 and ok_velocity
                    good += ok
                    if not ok and bad is None:
                        bad = (network, lx, ly, hex(yaw), hex(facing), b[0], want_facing)
    check('M3', good == cases, 'mode byte 1, mode 0: in %d of %d calls the facing is angle_approach(0.4, facing, 0x3e3d - yaw word) - also with the stick at rest - and the velocity '
                               'has the shipped speed along the stick\'s own direction (the shipped game\'s velocity once its facing has settled on that stick)%s' % (
                                   good, cases, '' if bad is None else ' (first failure: %s)' % (bad,)))
    # the exact form of the velocity claim on one case where the shipped facing can be preset to the stick's direction T exactly
    exact = cases = 0
    for network in (False, True):
        for lx, ly in ((0.0, -1.0), (1.0, 0.0), (0.7, -0.7), (-0.31, 0.52)):
            for yaw in yaws:
                rig = ee_tests.MoveRig(elf, network=network, yaw=yaw, facing=0)
                rig.emu.follow = None
                emu = EE(elf)
                bits = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
                emu.call(0x166798, fargs=(lx, ly))                 # math_atan2_16(lx, ly)
                net_yaw = yaw
                t = (emu.r[2] - (((net_yaw + 0x8000) & 0xFFFF) - 0x8000) - 0x41C2) & 0xFFFF
                cases += 1
                a = one_move(elf, False, network, 0, lx, ly, yaw, 0, 0, preset_facing=t)
                b = one_move(elf, True, network, 0, lx, ly, yaw, 0x5555, 1)
                exact += a[0][3] == b[0][3] and a[3] == b[3]
    check('M4', exact == cases, 'mode byte 1, mode 0: in %d of %d calls the velocity words and the vector handed to the move are bit for bit those of the shipped game for a '
                                'character whose facing is exactly the stick\'s direction' % (exact, cases))


# ---- H, S, C ------------------------------------------------------------------------------------
def handler(elf, patched, payload, objects=4):
    world = ee_tests.World(elf, players=objects, local_slot=0, network=True)
    emu, mem = world.emu, world.emu.mem
    if patched:
        assert emu.apply_pnach(PNACH, SECTION) == 84
    for obj in world.objects:
        mem.w8(obj + MODE, 0x00)
    message = emu.alloc(16, fill=0xEE)
    for k, byte in enumerate(payload):
        mem.w8(message + k, byte)
    before = [bytes(mem.read(obj, 0x590)) for obj in world.objects]
    emu.set_reg('s0', 0x1111)
    emu.set_reg('s1', 0x2222)
    stack = emu.r[29]
    emu.reset_log()
    emu.call(HANDLER, message, len(payload), max_steps=2000)
    kept = emu.reg('s0') == 0x1111 and emu.reg('s1') == 0x2222 and emu.r[29] == stack
    after = [bytes(mem.read(obj, 0x590)) for obj in world.objects]
    changed = [(i, k, after[i][k]) for i in range(len(after)) for k in range(0x590) if after[i][k] != before[i][k]]
    return changed, kept


def test_handler(elf):
    ok = True
    for slot in range(4):
        for mode in (1, 0, 7):
            changed, kept = handler(elf, True, (2, slot, mode))
            ok = ok and kept and changed == ([(slot, MODE, mode)] if mode else [])
    check('H1', ok, 'with the section, {2, slot, mode} for slots 0..3 and modes 1, 0, 7: the byte +0x47e of that slot\'s player object takes the mode, nothing else in any player object changes, registers kept')
    quiet = all(handler(elf, True, p) == ([], True) for p in ((0,), (1, 0), (1, 3), (3, 0, 1), (2, 4, 1), (2, 255, 1), (0xFF, 0, 1)))
    check('H2', quiet, 'with the section, the game\'s own messages on the channel ({0}, {1, slot}), other sub-types and slots of 4 and above: nothing is stored')
    world = ee_tests.World(elf, players=2, local_slot=0, network=True)
    emu, mem = world.emu, world.emu.mem
    emu.apply_pnach(PNACH, SECTION)
    mem.w32(ee_tests.G_PLAYERS + 3 * ee_tests.PLAYER_STRIDE + 0x43D8, 0)
    message = emu.alloc(16)
    for k, byte in enumerate((2, 3, 1)):
        mem.w8(message + k, byte)
    emu.reset_log()
    emu.call(HANDLER, message, 3, max_steps=2000)
    check('H3', not [w for w in emu.writes if w[1] < 0x1000], 'with the section, {2, 3, 1} when slot 3 has no player object: returns without a store through the null pointer')
    as_shipped = all(handler(elf, False, p) == ([], True) for p in ((2, 0, 1), (1, 0), (0,)))
    check('H4', as_shipped, 'as shipped the handler is empty: nothing is stored for any of them')


def test_sender(elf):
    ok = True
    for slot in (0, 1, 3):
        for mode in (0, 1):
            emu = EE(elf)
            emu.apply_pnach(PNACH, SECTION)
            emu.mem.map(CHANNEL_ID & ~0xFFF, 0x1000)
            emu.mem.w32(CHANNEL_ID, 4)
            sent = []
            emu.stub(GET_LOCAL_SLOT, ret=slot, name='net_getLocalPlayerSlot')
            emu.stub(SEND_GAME_MSG, function=lambda e: sent.append((e.r[4] & M32, bytes(e.mem.read(e.r[5] & M32, e.r[6] & M32)))), name='net_sendGameMsg')
            emu.set_reg('s0', 0x1111)
            stack = emu.r[29]
            emu.call(SENDER, mode, max_steps=2000)
            ok = ok and sent == [(4, bytes((2, slot, mode)))] and emu.r[29] == stack and emu.reg('s0') == 0x1111
    check('S1', ok, 'the sender, local slot 0, 1, 3 and mode 0, 1: one net_sendGameMsg(the channel\'s id, {2, slot, mode}, 3); stack pointer and saved registers kept')


def test_ctor(elf):
    out = {}
    for patched in (False, True):
        emu = EE(elf)
        if patched:
            emu.apply_pnach(PNACH, SECTION)
        obj = emu.alloc(0x590, fill=0xAA)
        emu.set_reg('s5', obj)
        emu.run(start=CTOR_WORDS, until=(CTOR_WORDS + 8,), max_steps=10)
        out[patched] = tuple(emu.mem.u8(obj + k) for k in (0x47B, 0x47C, 0x47D, 0x47E, 0x47F))
    check('C1', out[False] == (0xAA, 0, 0, 0xAA, 0xAA) and out[True] == (0xAA, 0, 0, 0, 0xAA),
          'Player_ctor 0x1a22fc: as shipped +0x47c and +0x47d are cleared and +0x47e keeps what the memory held; with the section +0x47e is cleared too, +0x47b and +0x47f untouched')


def main(argv):
    elf = argv[1] if len(argv) > 1 else os.path.join(ROOT, 'SLUS_209.73')
    test_words(elf)
    test_ctor(elf)
    test_sender(elf)
    test_handler(elf)
    test_move(elf)
    print('%d failed%s' % (len(FAILED), ': ' + ' '.join(FAILED) if FAILED else ''))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
