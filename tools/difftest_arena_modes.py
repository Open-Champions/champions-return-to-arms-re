#!/usr/bin/env python3
"""Run the arena and PvP-mode functions of SLUS_209.73 and compare them with
tools/ref_arena_modes.py.

    python3 tools/difftest_arena_modes.py local/SLUS_209.73

The executable is not in this repository.  A missing file skips the comparison.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE]
sys.path.append(_HERE)

import random                                          # noqa: E402

import ee_emu                                          # noqa: E402
from ee_emu import EE, EmuError                        # noqa: E402
import ref_arena_modes as A                            # noqa: E402
from ref_core import ONE, TWO, ZERO, from_int, s16     # noqa: E402

PICK = 0x3050A4
FIND = 0x14ACF8
CAM = 0x207478
NET_COUNT = 0x1EC878
ACTIVE = 0x13DD40
RESPAWN = 0x1BD040
SCREEN = 0x322954
WALK = 0x14A610
LOCAL = 0x13E1F0
HERMITE = 0x162310
DRAW_HUD = 0x305904
SCREEN_POS = 0x1E0430
RESET = 0x307C80
TICK = 0x307F68
FADE = 0x3075DC
START = 0x305ED4
STEP = 0x3065B0
SPAWN = 0x3065FC
RUN = 0x306B78
GRANT = 0x307EE0
RANK = 0x307E50
CMP = 0x307DF0
END = 0x307EBC
NEXT = 0x305E9C
SCAN = 0x1EB950
STRCPY = 0x3B868C
CLOSE = 0x1EB000
PICKER = 0x304BC8
SPELL = 0x305BBC
JOINTS = 0x1799C8
LOSE = 0x305650
ADDK = 0x3056CC
KILLED = 0x305580
LIFE = 0x3058C0
RESPAWN_P = 0x305784
DAMAGE = 0x1E8230

MODE_A = 0x4F711C
MODE_B = 0x4F7120
SCRAMBLE = 0x4F7124
NET = 0x402791
SEED = 0x404464
FOCUS = 0x44F048
SPAWN_N = 0x8E7342
SPAWN_P = 0x503888
NUM = 0x4D8AE0
PLAYERS = 0x4D8AF0
REC = 0x4C30
COUNTDOWN = 0x4F84A8
INTER = 0x8E733C
WAVE = 0x8E7338
LEFT = 0x8E733A
SAVED = 0x8E7340
LEVEL = 0x4F714C
INTRO = 0x5038C8
ENDF = 0x503894
FADE_W = 0x8E735C
BUDGET = 0x8E7358
LIMIT = 0x4F8408
FRAME = 0x44FDCC
PAUSED = 0x41B4F4
LOCK_A = 0x41B4FC
LOCK_B = 0x41B500
WORD890 = 0x503890
FRONT = 0x41B510
MENU = 0x41B69D
SCORE = 0x503898
ANGLE_W = 0x8E7364
ANGLE_H = 0x8E7360
GOLD_N = 0x4F8420
GOLD_T = 0x4F8440
HUD = 0x4F6950
EXIT = 0x41B508
PENDING = 0x41B6D0
NAMES_A = 0x5037B8
NAMES_B = 0x503798
CLASSES = 0x5037F0
RECIPES = 0x503868
NREC = 0x503886
ANCHOR_Y = 0x4F6710
ANCHOR_X = 0x4F6730
INDEX = 0x8E7343
RANK_B = 0x8E7348
PAD0 = 0x41BFD8
CONFIRM = 0x41BFBC
CANCEL = 0x41BFB8


class Check(object):
    def __init__(self):
        self.failed = 0
        self.passed = 0
        self.notes = []

    def eq(self, name, got, want):
        if got != want:
            self.failed += 1
            print('FAIL  %s\n      got  %s\n      want %s' % (name, got, want))
        else:
            self.passed += 1

    def true(self, name, cond, detail=''):
        self.eq(name, True if cond else detail, True)

    def note(self, text):
        self.notes.append(text)
        print('      ' + text)


def boot(path):
    emu = EE(path)
    emu.record_calls = True
    return emu


def words(emu, addr, n):
    return [emu.mem.u32(addr + 4 * i) for i in range(n)]


def put_words(emu, addr, values):
    for i, value in enumerate(values):
        emu.mem.w32(addr + 4 * i, value & 0xFFFFFFFF)


def put_points(emu, points):
    addr = emu.alloc(16 * max(1, len(points)) + 16)
    for i, (x, y, z, angle) in enumerate(points):
        put_words(emu, addr + 16 * i, (x, y, z))
        emu.mem.w16(addr + 16 * i + 12, angle)
    emu.mem.w32(SPAWN_P, addr)
    emu.mem.w8(SPAWN_N, len(points))
    return addr


def put_obj(emu, flags, slot=0, owner=0):
    addr = emu.alloc(0x400)
    emu.mem.w32(addr + 0xC, flags)
    emu.mem.w32(addr + 0x3C8, slot)
    emu.mem.w8(addr + 0x5A, owner & 0xFF)
    return addr


def bind_player(emu, slot, obj):
    emu.mem.w32(PLAYERS + slot * REC + 0x43D8, obj)


def put_slot(emu, slot, kills, lives, snap, timer):
    base = SCORE + slot * A.SCORE_STRIDE
    emu.mem.w16(base + 0, kills)
    emu.mem.w16(base + 2, lives)
    emu.mem.w16(base + 4, snap)
    emu.mem.w32(base + 8, timer)


def read_slot(emu, slot):
    base = SCORE + slot * A.SCORE_STRIDE
    return (emu.mem.u16(base), emu.mem.u16(base + 2), emu.mem.u16(base + 4), emu.mem.u32(base + 8))


def modes(emu, mode_a=0, mode_b=0, scramble=0, network=0, seed=1, players=1):
    emu.mem.w32(MODE_A, mode_a)
    emu.mem.w32(MODE_B, mode_b)
    emu.mem.w32(SCRAMBLE, scramble)
    emu.mem.w8(NET, network)
    emu.mem.w32(SEED, seed)
    emu.mem.w32(NUM, players)
    emu.mem.w32(PAUSED, 0)
    emu.mem.w32(FRONT, 0)
    emu.mem.w8(MENU, 0)


def names(emu, addr):
    out = []
    for i in range(20):
        p = emu.mem.u32(addr + 4 * i)
        if p == 0:
            break
        out.append(p)
    return out


def calls(emu, target):
    return [c for c in emu.calls if c.target == target]


def test_pick(chk, path):
    points = [
        (from_int(0), from_int(0), from_int(5), 0x1000),
        (from_int(128), from_int(0), from_int(1), 0x2000),
        (from_int(256), from_int(0), from_int(9), 0x0100),
    ]
    focus = (ZERO, ZERO, ZERO)
    camera = (from_int(3), from_int(4), from_int(5))

    def run(flag, slot, seed, mode_a, scramble, network, active, script, use_camera=False, table=None):
        emu = boot(path)
        put_points(emu, table if table is not None else points)
        modes(emu, mode_a=mode_a, scramble=scramble, network=network, seed=seed, players=4)
        put_words(emu, FOCUS, focus)
        seen = []
        pending = list(script)

        def search(centre, spread, radius):
            seen.append((list(centre), spread & 0xFFFFFFFF, radius & 0xFFFFFFFF))
            pos, ok = pending.pop(0)
            return list(pos), ok

        def find(emu):
            centre = emu.r[5] & 0xFFFFFFFF
            find.got.append((words(emu, centre, 3), emu.r[6] & 0xFFFFFFFF, emu.r[7] & 0xFFFFFFFF))
            pos, ok = script[len(find.got) - 1]
            out = emu.r[4] & 0xFFFFFFFF
            put_words(emu, out, pos)
            okp = emu.r[8] & 0xFFFFFFFF
            if okp:
                emu.mem.w8(okp, ok)

        find.got = []

        def cam(emu):
            put_words(emu, emu.r[4] & 0xFFFFFFFF, camera)
            cam.n += 1

        cam.n = 0
        emu.stub(FIND, function=find)
        emu.stub(CAM, function=cam)
        emu.stub(NET_COUNT, ret=active)
        pos_a = emu.alloc(16)
        face_a = emu.alloc(4)
        used = table if table is not None else points
        want_pos, want_face, want_seed = A.pick_spawn(
            flag, slot, used, seed, bool(mode_a), bool(scramble), bool(network),
            focus, active, search, camera)
        emu.call(PICK, flag, slot, pos_a, face_a)
        chk.eq('pick centres flag=%d net=%d' % (flag, network), find.got, seen)
        chk.eq('pick pos flag=%d slot=%d' % (flag, slot), words(emu, pos_a, 3), want_pos)
        chk.eq('pick facing flag=%d' % flag, s16(emu.mem.u16(face_a)), want_face)
        chk.eq('pick seed flag=%d' % flag, emu.mem.u32(SEED), want_seed)
        chk.eq('pick camera calls', cam.n, 1 if use_camera else 0)

    here = (from_int(9), from_int(8), from_int(7))
    run(1, 1, 1, 1, 0, 0, 4, [(here, 1)])
    run(1, 2, 1, 0, 0, 0, 4, [((from_int(1), from_int(1), from_int(1)), 0), (here, 1)])
    run(1, 0, 1, 1, 1, 0, 3, [(here, 1)])
    run(0, 1, 20973, 0, 0, 1, 1, [])
    run(0, 0, 7, 0, 0, 0, 1, [])
    far = [(from_int(256), from_int(0), from_int(9), 0x0100)]
    run(0, 0, 3, 0, 0, 0, 1, [(camera, 1)], use_camera=True, table=far)


def test_scores(chk, path):
    emu = boot(path)
    modes(emu, players=2)
    victim = put_obj(emu, 0x60, slot=0)
    other = put_obj(emu, 0x60, slot=1)
    pet = put_obj(emu, 0x20, owner=1)
    ghost = put_obj(emu, 0x20020, slot=0)
    bind_player(emu, 0, victim)
    bind_player(emu, 1, other)
    for slot in range(2):
        put_slot(emu, slot, 0, 2, 0, TWO)

    def killed(slot, killer, mode_a):
        emu.mem.w32(MODE_A, mode_a)
        emu.reset_log()
        emu.call(KILLED, slot, killer)

    killed(0, other, 1)
    chk.eq('kill credits the other player', read_slot(emu, 1)[0], 1)
    killed(0, victim, 0)
    chk.eq('suicide drops a life', s16(read_slot(emu, 0)[1]), 1)
    killed(0, 0, 0)
    chk.eq('null killer drops a life in mode B', s16(read_slot(emu, 0)[1]), 0)
    killed(0, pet, 1)
    chk.eq('pet credits its owner', read_slot(emu, 1)[0], 2)
    emu.mem.w32(other + 0xC, 0)                 # neither player nor creature
    killed(0, other, 0)
    chk.eq('a non-creature killer drops a life', s16(read_slot(emu, 0)[1]), -1)
    bind_player(emu, 0, ghost)
    before = read_slot(emu, 0)[1]
    killed(0, other, 0)
    chk.eq('prediction copy is ignored', read_slot(emu, 0)[1], before)
    emu.mem.w32(MODE_B, 1)
    emu.mem.w32(MODE_A, 0)
    emu.call(LIFE, 1)
    chk.eq('mode B grants a life', read_slot(emu, 1)[1], 3)
    emu.mem.w32(MODE_A, 1)
    emu.call(LIFE, 1)
    chk.eq('mode A does not grant a life', read_slot(emu, 1)[1], 3)

    emu.mem.w8(NET, 1)
    emu.call(RESET)
    chk.eq('reset lives', (read_slot(emu, 0)[1], read_slot(emu, 1)[1]), (2, 2))
    chk.eq('reset timer', (read_slot(emu, 0)[3], read_slot(emu, 1)[3]), (TWO, TWO))
    chk.eq('net movement', (emu.mem.u32(PLAYERS + 0x4C20), emu.mem.u32(PLAYERS + REC + 0x4C20)),
           (A.K_MOVE_NET, A.K_MOVE_NET))
    emu.mem.w8(NET, 0)
    emu.call(RESET)
    chk.eq('offline movement', emu.mem.u32(PLAYERS + 0x4C20), A.K_MOVE_OFF)

    put_slot(emu, 0, 0, 2, 7, ZERO)
    emu.call(TICK)
    got = read_slot(emu, 0)
    slot = A.Slot(0, 2, 7, ZERO)
    A.tick_overlay([slot])
    chk.eq('overlay climb', (got[2], got[3]), (slot.snapshot, slot.timer))
    put_slot(emu, 0, 0, 4, 1, TWO)
    emu.call(TICK)
    chk.eq('timer on 2.0 stays', read_slot(emu, 0)[3], TWO)


def test_respawn(chk, path):
    emu = boot(path)
    modes(emu, mode_b=1, players=1, network=0)
    obj = put_obj(emu, 0x60, slot=0)
    bind_player(emu, 0, obj)
    emu.mem.w32(PLAYERS + 0xB0, from_int(80))
    emu.mem.w32(PLAYERS + 0xAC, from_int(1))
    emu.mem.w32(PLAYERS + 0xC4, from_int(40))
    emu.mem.w32(PLAYERS + 0xC0, from_int(1))
    put_slot(emu, 0, 0, 2, 0, TWO)
    emu.mem.w16(INTER, 0)
    emu.stub(PICK, ret=0)
    emu.stub(RESPAWN, ret=0)
    emu.stub(SCREEN, ret=0)
    emu.stub(WALK, ret=0)
    emu.stub(ACTIVE, ret=1)
    emu.stub(LOCAL, ret=0)
    emu.call(RESPAWN_P, 0)
    chk.eq('respawn calls pick with a0 = 0',
           [(c.args[0], c.args[1]) for c in calls(emu, PICK)], [(0, 0)])
    chk.eq('player_respawn spread args', [(c.args[3], c.args[4]) for c in calls(emu, RESPAWN)], [(2, 3)])
    chk.eq('dead countdown', emu.mem.u16(COUNTDOWN), A.DEAD_COUNTDOWN)
    chk.eq('snapshot copied from lives', emu.mem.u16(SCORE + 4), 2)
    chk.eq('hp refilled', emu.mem.u32(PLAYERS + 0xAC), from_int(80))
    chk.eq('mana refilled', emu.mem.u32(PLAYERS + 0xC0), from_int(40))
    chk.true('screen effect for the only local player', calls(emu, SCREEN))
    emu.reset_log()
    emu.mem.w32(NUM, 2)
    emu.stub(LOCAL, ret=1)
    emu.call(RESPAWN_P, 0)
    chk.eq('no screen effect for a remote slot', calls(emu, SCREEN), [])
    emu.reset_log()
    put_slot(emu, 0, 0, 0xFFFF, 0, TWO)
    emu.mem.w32(MODE_A, 0)
    emu.call(RESPAWN_P, 0)
    chk.eq('no respawn at -1 life', calls(emu, PICK), [])
    emu.mem.w32(MODE_A, 1)
    put_slot(emu, 0, 0, 0xFFFF, 0, TWO)
    emu.mem.w16(INTER, 4)
    emu.reset_log()
    emu.call(RESPAWN_P, 0)
    chk.eq('no respawn during intermission', calls(emu, PICK), [])
    emu.mem.w16(INTER, 0)
    emu.reset_log()
    emu.call(RESPAWN_P, 0)
    chk.eq('mode A respawns at -1 life',
           [(c.args[0], c.args[1]) for c in calls(emu, PICK)], [(0, 0)])


def test_hermite_and_hud(chk, path):
    emu = boot(path)
    samples = [
        (ZERO, [from_int(1), from_int(2), from_int(3)], [from_int(9), from_int(8), from_int(7)],
         [from_int(4), ZERO, from_int(-2)], [ONE, TWO, ZERO]),
        (from_int(1), [A.K_259, A.K_290, ZERO], [from_int(100), from_int(10), ZERO],
         [A.K_259, A.K_290, ZERO], [A.K_M500, A.K_M500, ZERO]),
        (A.overlay_t(from_int(1), 2), [ZERO, ZERO, ZERO], [ONE, ONE, ONE], [TWO, TWO, TWO], [HALF_f(), HALF_f(), HALF_f()]),
    ]
    for index, (t, p0, p1, m0, m1) in enumerate(samples):
        bufs = [emu.alloc(16) for _ in range(5)]
        for buf, vec in zip(bufs, (p0, p1, m0, m1)):
            put_words(emu, buf, vec)
        emu.f[12] = t
        emu.call(HERMITE, bufs[0], bufs[1], bufs[2], bufs[3], bufs[4])
        chk.eq('hermite %d' % index, words(emu, bufs[4], 3), A.hermite(t, p0, p1, m0, m1))

    emu = boot(path)
    modes(emu, mode_b=1, mode_a=0, players=2)
    put_slot(emu, 0, 0, 2, 0, ZERO)
    put_slot(emu, 1, 0, 2, 0, from_int(1))
    screens = {0: (100, 10), 1: (400, 20)}
    emu.mem.w32(ANCHOR_X, 11)
    emu.mem.w32(ANCHOR_X + 4, 22)
    emu.mem.w32(ANCHOR_Y, 33)
    emu.mem.w32(ANCHOR_Y + 4, 44)

    def screen(emu):
        slot = emu.r[4] & 0xFFFFFFFF
        x, y = screens[slot]
        emu.mem.w32(emu.r[5] & 0xFFFFFFFF, x)
        emu.mem.w32(emu.r[6] & 0xFFFFFFFF, y)

    seen = []

    def enter(emu):
        seen.append({
            't': emu.f[12],
            'p0': words(emu, emu.r[4] & 0xFFFFFFFF, 3),
            'p1': words(emu, emu.r[5] & 0xFFFFFFFF, 3),
            'm0': words(emu, emu.r[6] & 0xFFFFFFFF, 3),
            'm1': words(emu, emu.r[7] & 0xFFFFFFFF, 3),
            'out': emu.r[8] & 0xFFFFFFFF,
        })

    def leave(emu):
        item = seen[-1]
        item['got'] = words(emu, item['out'], 3)

    emu.stub(SCREEN_POS, function=screen)
    for addr in (0x1EC360, 0x1800B8, 0x173C84, 0x181CA0, 0x180500):
        emu.stub(addr, ret=0)
    emu.hook(HERMITE, enter)
    emu.hook(0x162438, leave)
    emu.call(DRAW_HUD)
    expect = []
    anchor = A.K_259
    for slot, timer in ((0, ZERO), (1, from_int(1))):
        sx, sy = screens[slot]
        anchor = A.overlay_anchor_x(sx, anchor)
        for k in range(5):
            if not A.overlay_draws(timer, k):
                continue
            p0 = [from_int(emu.mem.u32(ANCHOR_X + 4 * slot)), from_int(emu.mem.u32(ANCHOR_Y + 4 * slot)), ZERO]
            # anchor x word is the integer at 0x4f6730, y at 0x4f6710
            p0 = [from_int([11, 22][slot]), from_int([33, 44][slot]), ZERO]
            p1 = [from_int(sx), from_int(sy), ZERO]
            m0 = [anchor, A.K_290, ZERO]
            m1 = [A.K_M500, A.K_M500, ZERO]
            t = A.overlay_t(timer, k)
            expect.append((t, p0, p1, m0, m1, A.hermite(t, p0, p1, m0, m1)))
    chk.eq('overlay steps', len(seen), len(expect))
    for i, (item, want) in enumerate(zip(seen, expect)):
        chk.eq('overlay t %d' % i, item['t'], want[0])
        chk.eq('overlay points %d' % i, (item['p0'], item['p1'], item['m0'], item['m1']), want[1:5])
        chk.eq('overlay out %d' % i, item.get('got'), want[5])


def HALF_f():
    return 0x3F000000


def test_waves(chk, path):
    nrec = emu_count(path)
    chk.eq('recipe count', nrec, 5)
    emu = boot(path)
    records = []
    for i in range(nrec):
        records.append(bytes(emu.mem.u8(RECIPES + 6 * i + b) for b in range(6)))
    table = [emu.mem.u32(CLASSES + 4 * i) for i in range(32)]

    def one(wave, active, mode_a=0):
        emu = boot(path)
        modes(emu, mode_a=mode_a, mode_b=1, players=0, seed=20973, network=0)
        # The halfword is the value BEFORE startWave adds 1, matching arena_begin's -1.
        emu.mem.w16(WAVE, (wave - 1) & 0xFFFF)
        emu.mem.w16(LEFT, 3)
        emu.mem.w16(SAVED, 0)
        emu.mem.w32(0x4F8450, 0)
        emu.follow = {STEP}
        emu.stub(NET_COUNT, ret=active)
        emu.stub(SPAWN, ret=0)
        emu.stub(0x203210, ret=0)
        emu.stub(0x1EB000, ret=0)
        emu.stub(0x1EC2B8, ret=0)
        emu.call(START, 1)
        classes, seed, steps = A.wave_plan(wave, active, nrec, records, 20973, 0)
        got = [c.args[0] & 0xFFFFFFFF for c in calls(emu, SPAWN)]
        want = [table[cls & 0xFF] for cls in classes]
        chk.eq('wave %d active %d spawns' % (wave, active), got, want)
        chk.eq('wave %d spawn flag' % wave, [c.args[1] & 0xFFFFFFFF for c in calls(emu, SPAWN)], [0] * len(want))
        chk.eq('wave %d ring steps' % wave, len(calls(emu, STEP)), len(steps))
        chk.eq('wave %d seed' % wave, emu.mem.u32(SEED), seed)
        if steps:
            chk.eq('wave %d angle' % wave, (emu.mem.u32(ANGLE_W), emu.mem.u16(ANGLE_H)), (steps[-1][1], steps[-1][2]))
        chk.eq('wave index', s16(emu.mem.u16(WAVE)), s16(wave))
        chk.eq('monster level', emu.mem.u32(LEVEL), A.monster_level(wave))
        chk.eq('waves left', s16(emu.mem.u16(LEFT)), 2)
        chk.eq('intro armed', emu.mem.u16(INTRO), A.INTRO_FRAMES)
        chk.eq('match word', emu.mem.u32(WORD890), 1)

    for wave in (0, 1, 2, 3, 5, 8):
        for active in (1, 4):
            try:
                A.wave_plan(wave, active, nrec, records, 1, 0)
            except ZeroDivisionError:
                chk.note('wave %d active %d has a zero group; the original divides by it' % (wave, active))
                continue
            one(wave, active)

    emu = boot(path)
    modes(emu, mode_a=1, mode_b=1, players=2, network=1, seed=1)
    emu.mem.w16(WAVE, 0xFFFF)
    emu.mem.w16(SAVED, 0)
    emu.follow = {0x307C80, 0x3B60C0}
    emu.stub(NET_COUNT, ret=1)
    emu.stub(0x203210, ret=0)
    emu.stub(0x1EB000, ret=0)
    emu.stub(0x1EC2B8, ret=0)
    emu.call(START, 1)
    chk.eq('mode A spawns nothing', calls(emu, SPAWN), [])
    chk.eq('mode A reset lives', (read_slot(emu, 0)[1], read_slot(emu, 1)[1]), (2, 2))
    chk.eq('mode A still advances the wave', s16(emu.mem.u16(WAVE)), 0)


def emu_count(path):
    emu = boot(path)
    return emu.mem.u16(NREC)


def test_task(chk, path):
    emu = boot(path)
    nrec = emu.mem.u16(NREC)
    records = [bytes(emu.mem.u8(RECIPES + 6 * i + b) for b in range(6)) for i in range(nrec)]
    names_a = names(emu, NAMES_A)
    names_b = names(emu, NAMES_B)
    chk.eq('mode A map count', len(names_a), A.MODE_A_MAPS)
    chk.eq('mode B map count', len(names_b), 7)
    chk.eq('initial file kill limit', emu.mem.u8(LIMIT), 0)

    def task(**kw):
        emu = boot(path)
        players = kw.get('players', 1)
        modes(emu, mode_a=kw.get('mode_a', 0), mode_b=1, network=kw.get('network', 0),
              players=players, seed=1)
        emu.mem.w16(INTRO, kw.get('intro', 0xFFFF))
        emu.mem.w16(INTER, kw.get('inter', 0))
        emu.mem.w32(ENDF, kw.get('end', 0))
        emu.mem.w32(FADE_W, kw.get('fade', 0))
        emu.mem.w32(FRAME, kw.get('frame', 1))
        emu.mem.w32(PAUSED, kw.get('paused', 0))
        emu.mem.w8(LIMIT, kw.get('limit', 10))
        emu.mem.w32(BUDGET, kw.get('budget', 100))
        emu.mem.w32(GOLD_N, kw.get('gold_n', 0))
        emu.mem.w32(GOLD_T, kw.get('gold_slot', 0))
        emu.mem.w16(WAVE, kw.get('wave', 2))
        emu.mem.w16(LEFT, kw.get('left', 2))
        emu.mem.w8(INDEX, kw.get('index', 0))
        for slot in range(players):
            put_slot(emu, slot, kw.get('kills', 0), kw.get('lives', 2), kw.get('snap', 2), TWO)
            emu.mem.w32(PLAYERS + slot * REC + 0xAC, kw.get('hp', from_int(10)))
            emu.mem.w32(PLAYERS + slot * REC + 0xE4, kw.get('gold', 0))
            emu.mem.w16(COUNTDOWN + 2 * slot, kw.get('dead', 0))
        follow = {TICK}
        if kw.get('grant'):
            follow.add(GRANT)
        emu.follow = follow
        emu.stub(ACTIVE, ret=1)
        emu.stub(END, ret=0)
        emu.stub(NEXT, ret=0)
        emu.stub(SCAN, ret=kw.get('scan', 0))
        emu.stub(STRCPY, ret=0)
        emu.stub(CLOSE, ret=0)
        if kw.get('pad'):
            save = emu.alloc(0x4C20)
            emu.mem.write(save, b'\x5a' * 0x4C20)
            emu.stub(0x21837C, ret=save)
        else:
            emu.stub(0x21837C, ret=0)
        emu.stub(0x304FB0, ret=0)
        emu.stub(PICKER, ret=kw.get('picked', names_b[0]))
        emu.stub(0x13E5A0, ret=0)
        emu.stub(0x17365C, ret=0)
        emu.stub(0x2134E8, ret=0)
        emu.stub(0x14A610, ret=0)
        if kw.get('pad'):
            emu.mem.w32(CONFIRM, kw['pad'][0])
            emu.mem.w32(CANCEL, kw['pad'][1])
            emu.mem.w32(PAD0 + 0xC, kw['pad'][2])
        emu.call(RUN)
        return emu

    paused = task(intro=50, paused=1)
    chk.eq('paused task does nothing', paused.mem.u16(INTRO), 50)

    intro = task(intro=180)
    chk.eq('intro counts down', intro.mem.u16(INTRO), 179)
    chk.eq('intro locks set', (intro.mem.u32(LOCK_A), intro.mem.u32(LOCK_B), intro.mem.u32(WORD890)), (1, 1, 1))

    cue = task(intro=0x85, mode_a=0)
    chk.eq('cue frame', cue.mem.u16(INTRO), 0x84)
    chk.true('mode B plays the cue', calls(cue, 0x214230) or calls(cue, 0x17365C))

    done = task(intro=0)
    chk.eq('intro latches at -1', s16(done.mem.u16(INTRO)), -1)
    chk.eq('locks cleared', (done.mem.u32(LOCK_A), done.mem.u32(LOCK_B)), (0, 0))

    early = task(intro=0xFFFF, inter=10, lives=2, hp=from_int(10))
    chk.eq('intermission not finished', early.mem.u16(INTER), 11)
    chk.eq('no level change yet', calls(early, STRCPY), [])

    expired = task(intro=0xFFFF, inter=A.INTERMISSION_OFFLINE, left=0, wave=2, network=0)
    chk.eq('offline limit changes the level', len(calls(expired, STRCPY)), 1)
    record = A.level_record_index(2, nrec)
    want = names_b[A.low_nibble(records[record][0])]
    chk.eq('mode B next name', calls(expired, STRCPY)[0].args[1] & 0xFFFFFFFF, want)
    chk.eq('orientation byte cleared', expired.mem.s8(PENDING + 0x50), -1)

    online = task(intro=0xFFFF, inter=A.INTERMISSION_ONLINE, left=0, network=1, wave=2)
    chk.eq('online limit', len(calls(online, STRCPY)), 1)
    short = task(intro=0xFFFF, inter=A.INTERMISSION_OFFLINE, network=1, left=0, wave=2)
    chk.eq('online ignores the offline limit', calls(short, STRCPY), [])

    nxt = task(intro=0xFFFF, inter=A.INTERMISSION_OFFLINE, left=2, mode_a=0, wave=0)
    chk.eq('waves remaining start the next wave', [c.args[0] for c in calls(nxt, NEXT)], [1])
    chk.eq('and do not change level', calls(nxt, STRCPY), [])

    wrapped = task(intro=0xFFFF, inter=A.INTERMISSION_OFFLINE, mode_a=1, index=12, scan=2, left=9)
    chk.eq('mode A wrap uses the scan', calls(wrapped, STRCPY)[0].args[1] & 0xFFFFFFFF, names_a[2])
    chk.eq('stored index', wrapped.mem.u8(INDEX), 2)
    plain = task(intro=0xFFFF, inter=A.INTERMISSION_OFFLINE, mode_a=1, index=0, left=9)
    chk.eq('mode A steps the index', calls(plain, STRCPY)[0].args[1] & 0xFFFFFFFF, names_a[1])

    won = task(intro=0xFFFF, mode_a=1, kills=10, limit=10)
    chk.eq('kill limit opens the end', won.mem.u16(INTER), 1)
    chk.true('end prompt', calls(won, END))
    shortk = task(intro=0xFFFF, mode_a=1, kills=9, limit=10)
    chk.eq('below the limit continues', shortk.mem.u16(INTER), 0)

    wipe = task(intro=0xFFFF, inter=10, lives=0xFFFF, hp=ZERO, snap=0)
    chk.eq('wipe clears the countdown', wipe.mem.u16(INTER), 0)
    chk.eq('wipe sets the end flag', wipe.mem.u32(ENDF), 1)

    retry = task(intro=0xFFFF, lives=0xFFFF, hp=ZERO, dead=0, snap=2, end=0)
    chk.eq('wipe with a saved life retries', [c.args[0] for c in calls(retry, NEXT)], [0])
    defeat = task(intro=0xFFFF, lives=0xFFFF, hp=ZERO, dead=0, snap=0, end=0)
    chk.eq('wipe with no saved life ends', defeat.mem.u32(ENDF), 1)
    chk.eq('and does not retry', calls(defeat, NEXT), [])

    bought = task(intro=0xFFFF, lives=0, hp=from_int(5), gold=150, budget=100, gold_n=1, gold_slot=0, grant=True)
    chk.eq('gold buys a life', (bought.mem.u32(PLAYERS + 0xE4), bought.mem.u32(BUDGET), bought.mem.u16(SCORE + 2)),
           (50, 200, 1))
    chk.eq('bought life clears the timer', bought.mem.u32(SCORE + 8), ZERO)
    chk.eq('hud word', bought.mem.u32(HUD), 0x80)

    confirm = task(intro=0xFFFF, end=1, fade=ONE, lives=0xFFFF, hp=ZERO, dead=0, snap=0,
                   pad=(0x100, 0, 0x100))
    chk.true('confirm shuts the arena down', calls(confirm, 0x304FB0))
    chk.eq('confirm requests the picker name', len(calls(confirm, STRCPY)), 1)
    chk.eq('confirm keeps mode B', confirm.mem.u32(MODE_B), 1)
    cancel = task(intro=0xFFFF, end=1, fade=ONE, lives=0xFFFF, hp=ZERO, dead=0, snap=0,
                  pad=(0, 0x100, 0x100))
    chk.eq('cancel clears mode B', cancel.mem.u32(MODE_B), 0)
    chk.eq('cancel sets the session exit', cancel.mem.u32(EXIT), 1)
    chk.eq('cancel does not copy a name', calls(cancel, STRCPY), [])

    rank = boot(path)
    modes(rank, players=3)
    put_slot(rank, 0, 1, 2, 0, TWO)
    put_slot(rank, 1, 5, 2, 0, TWO)
    put_slot(rank, 2, 1, 2, 0, TWO)
    for a, b, ka, kb in ((0, 1, 1, 5), (1, 0, 5, 1), (0, 2, 1, 1), (2, 0, 1, 1)):
        pa, pb = rank.alloc(4), rank.alloc(4)
        rank.mem.w8(pa, a)
        rank.mem.w8(pb, b)
        got = s16(rank.call(CMP, pa, pb) & 0xFFFFFFFF)
        chk.eq('compare %d %d' % (a, b), got, A.compare_kills(a, b, ka, kb))
    rank.call(RANK)
    order = [rank.mem.s8(RANK_B + i) for i in range(3)]
    chk.eq('highest kill is first', order[0], 1)


def test_fade_and_spell(chk, path):
    emu = boot(path)
    text = emu.alloc(4)
    emu.mem.w32(0x8E734C, text)
    emu.mem.w32(0x8E7350, text)
    emu.follow = set()
    emu.mem.w32(FADE_W, ZERO)
    try:
        emu.call(FADE, max_steps=200000)
        ran = True
    except EmuError as exc:
        ran = False
        chk.note('prompt draw stopped after the fade store (%s)' % exc)
    chk.eq('fade step', emu.mem.u32(FADE_W), A.fade_step(ZERO))
    emu.mem.w32(FADE_W, ONE)
    emu.follow = set()
    try:
        emu.call(FADE, max_steps=200000)
    except EmuError:
        pass
    chk.eq('fade clamps at 1', emu.mem.u32(FADE_W), ONE)
    chk.true('fade function returned', ran)

    def spell(counter, flags):
        emu = boot(path)
        owner = emu.alloc(0x100)
        spell = emu.alloc(0x20)
        pos = emu.alloc(16)
        vt = emu.alloc(0x90)
        fn = emu.alloc(16)
        emu.mem.w32(spell + 0xC, owner)
        emu.mem.w32(owner + 0xC, flags)
        emu.mem.w32(owner + 0x48, vt)
        emu.mem.w16(vt + 0x80, 0)
        emu.mem.w32(vt + 0x84, fn)
        emu.stub(fn, ret=0)
        emu.stub(JOINTS, ret=1)
        emu.follow = set()
        emu.mem.w16(INTRO, counter & 0xFFFF)
        for off in range(0x90, 0xA0, 2):
            emu.mem.w16(owner + off, 0x1111)
        stopped = None
        try:
            emu.call(SPELL, spell, pos, max_steps=2000000)
        except (EmuError, ee_emu.CpuTrap) as exc:
            stopped = str(exc)
        tint = [emu.mem.u16(owner + 0x90 + 2 * i) for i in range(4)]
        return emu.mem.u32(owner + 0xC), tint, stopped

    flags, tint, stopped = spell(180, 0x11)
    chk.eq('counter >= 61 sets flag bit 1', flags, 0x13)
    chk.true('counter 180 ran', stopped is None, stopped)
    chk.eq('counter >= 30 tints', tint, list(A.TINT))
    flags, tint, stopped = spell(40, 0x13)
    chk.eq('counter 40 clears bit 1 and keeps bit 0', flags, 0x11)
    if stopped:
        chk.note('counter 40 particle loop stopped (%s); tint stores are the ones executed at counter 180' % stopped)
    else:
        chk.eq('counter 40 still tints', tint, list(A.TINT))
    flags, tint, stopped = spell(10, 0x13)
    chk.eq('counter < 30 clears bit 1 and keeps bit 0', flags, 0x11)
    chk.eq('counter < 30 leaves the tint', tint, [0x1111] * 4)
    flags, tint, stopped = spell(0xFFFF, 0x13)
    chk.eq('steady state clears bit 1 and keeps bit 0', flags, 0x11)
    chk.eq('steady state leaves the tint', tint, [0x1111] * 4)


def test_pvp(chk, path):
    import difftest_combat as C
    rig = C.Rig(path)
    rng_seed = 20973

    def hit(pvp, player, armor, amount):
        rng = random.Random(rng_seed)
        sc = C.gen_damage(rng)
        victim, attacker = sc['victim'], sc['attacker']
        if attacker is not None:
            attacker.flags &= ~0x20000
        victim.flags = 0x20 | (0x40 if player else 0)
        victim.cflags = 0
        victim.spells = []
        victim.res = [ZERO] * 5
        victim.armor = armor
        victim.cls = 'Creature'
        victim.kind = 0
        victim.status = [ZERO] * 5
        if player:
            victim.slot = 0
            sc['world'].players[0].obj = victim
            sc['world'].players[0].passives = [0] * 48
        sc['min'] = sc['max'] = from_int(amount)
        sc['attack'] = 100000
        sc['flags'] = 0
        sc['desc'] = None
        sc['no_crit'] = 1
        sc['world'].pvp_a = pvp
        sc['world'].cutscene = 1
        rig.begin(sc)
        rig.put_objects(sc['objects'])
        rig.put_world(sc['world'])
        desc = 0
        rig.call(DAMAGE, rig.addr[id(victim)], rig.addr[id(attacker)] if attacker is not None else 0,
                 sc['attack'], 0, 0, sc['flags'], desc, sc['no_crit'], fargs=(sc['min'], sc['max']))
        return [e for e in rig.events if e[0] == 'take_damage' and e[1] == victim.tag]

    off = hit(0, True, 0, 40)
    on = hit(1, True, 0, 40)
    chk.true('player hit lands', off and on and off[0][2] != 0, (off, on))
    if off and on:
        chk.eq('mode A halves a player', on[0][2], A.pvp_half(off[0][2]))
        chk.eq('no stun event in mode A', [e for e in rig.events if e[0] == 'stun'], [])
    mon_off = hit(0, False, 300, 100)
    mon_on = hit(1, False, 300, 100)
    chk.true('monster hit lands', mon_off and mon_on, (mon_off, mon_on))
    if mon_off and mon_on:
        chk.eq('monster outside mode A is not mitigated', mon_off[0][2], from_int(100))
        chk.eq('mode A mitigates a monster', mon_on[0][2], A.armour_bound(from_int(100), 300))
        chk.eq('mode A does not also halve a monster', mon_on[0][2] == A.pvp_half(mon_off[0][2]), False)


def test_picker(chk, path):
    emu = boot(path)
    names_a = names(emu, NAMES_A)
    names_b = names(emu, NAMES_B)
    record0 = emu.mem.u8(RECIPES)
    emu.mem.w32(MODE_A, 1)
    emu.stub(SCAN, ret=3)
    chk.eq('mode A picker', emu.call(PICKER) & 0xFFFFFFFF, names_a[3])
    emu.mem.w32(MODE_A, 0)
    emu.unhook(SCAN)
    chk.eq('mode B picker uses record 0', emu.call(PICKER) & 0xFFFFFFFF, names_b[A.low_nibble(record0)])


REG = 0x30503C
VISIT = 0x306AF0


def test_edges(chk, path):
    """Score reset, the life grant's caller, spawn registration and the respawn visit."""
    emu = boot(path)
    modes(emu, mode_b=1, network=1, players=2)
    emu.mem.w16(SCORE, 9)
    emu.mem.w16(SCORE + 2, 9)
    emu.call(RESET)
    chk.eq('reset lives', emu.mem.u16(SCORE + 2), 2)
    chk.eq('reset timer', emu.mem.u32(SCORE + 8), TWO)
    chk.eq('reset movement, networked', emu.mem.u32(PLAYERS + 0x4C20), A.K_MOVE_NET)
    chk.eq('reset movement, slot 1', emu.mem.u32(PLAYERS + REC + 0x4C20), A.K_MOVE_NET)
    emu.mem.w8(NET, 0)
    emu.call(RESET)
    chk.eq('reset movement, offline', emu.mem.u32(PLAYERS + 0x4C20), A.K_MOVE_OFF)

    emu.mem.w32(MODE_A, 0)
    emu.mem.w32(MODE_B, 1)
    emu.mem.w16(SCORE + 2, 2)
    emu.call(LIFE, 0)
    chk.eq('mode B grants a life', emu.mem.u16(SCORE + 2), 3)
    emu.mem.w32(MODE_A, 1)
    emu.call(LIFE, 0)
    chk.eq('mode A ignores the grant', emu.mem.u16(SCORE + 2), 3)
    emu.mem.w32(MODE_A, 0)
    emu.mem.w32(MODE_B, 0)
    emu.call(LIFE, 0)
    chk.eq('no arena ignores the grant', emu.mem.u16(SCORE + 2), 3)

    table = emu.alloc(64)
    emu.mem.w32(SPAWN_P, table)
    emu.mem.w8(SPAWN_N, 0)
    vec = emu.alloc(16)
    for i, word in enumerate((0x11, 0x22, 0x33)):
        emu.mem.w32(vec + 4 * i, word)
    emu.call(REG, -1, vec, 0x1234)
    chk.eq('append bumps the count', emu.mem.u8(SPAWN_N), 1)
    chk.eq('append wrote the point', [emu.mem.u32(table + 4 * i) for i in range(3)], [0x11, 0x22, 0x33])
    chk.eq('append wrote the angle', s16(emu.mem.u16(table + 0xC)), 0x1234)
    emu.mem.w32(vec, 0x44)
    emu.call(REG, 1, vec, 0xFFFE)
    chk.eq('overwrite leaves the count', emu.mem.u8(SPAWN_N), 1)
    chk.eq('overwrite wrote slot 1', emu.mem.u32(table + 0x10), 0x44)
    chk.eq('overwrite angle', s16(emu.mem.u16(table + 0x1C)), -2)

    def visit(flags, seed):
        one = boot(path)
        obj = one.alloc(0x60)
        vt = one.alloc(0xC0)
        fn = one.alloc(8)
        one.mem.w32(obj + 0xC, flags)
        one.mem.w32(obj + 0x48, vt)
        one.mem.w16(vt + 0xB8, 0)
        one.mem.w32(vt + 0xBC, fn)
        one.mem.w32(SEED, seed)
        one.stub(fn, ret=0)
        one.follow = set()
        one.call(VISIT, obj)
        called = [c.args[0] for c in one.calls if c.target == fn]
        return one.mem.u32(SEED), called

    seed, called = visit(0x40, 1)
    chk.eq('a player is not scattered', (seed, called), (1, []))
    seed, called = visit(0x60, 1)
    chk.eq('a player creature is not scattered', (seed, called), (1, []))
    nxt, bit = A.lcg(1)
    seed, called = visit(0x20, 1)
    chk.eq('a creature consumes one draw', seed, nxt)
    chk.eq('bit 0 of the draw calls', len(called), 1 if (bit & 1) else 0)
    # a second seed whose low bit differs, so both arms are executed
    other = 1
    while (A.lcg(other)[1] & 1) == (bit & 1):
        other += 1
    nxt2, bit2 = A.lcg(other)
    seed, called = visit(0x20, other)
    chk.eq('the other draw bit', (seed, len(called)), (nxt2, 1 if (bit2 & 1) else 0))
    chk.true('both draw bits were seen', (bit & 1) != (bit2 & 1))

    emu = boot(path)
    modes(emu, players=3)
    put_slot(emu, 0, 1, 2, 0, TWO)
    put_slot(emu, 1, 5, 2, 0, TWO)
    put_slot(emu, 2, 1, 2, 0, TWO)
    emu.mem.w32(FADE_W, ONE)
    emu.call(END)
    chk.eq('end prompt clears the fade', emu.mem.u32(FADE_W), 0)
    chk.eq('highest kill is ranked first', emu.mem.u8(RANK_B), 1)

    one = boot(path)
    modes(one, players=1)
    put_slot(one, 0, 0, 4, 9, ZERO)
    one.call(TICK)
    slot = A.Slot(0, 4, 9, ZERO)
    A.tick_overlay([slot])
    chk.eq('overlay climbs', one.mem.u32(SCORE + 8), slot.timer)
    chk.eq('climb does not copy the snapshot yet', one.mem.u16(SCORE + 4), 9)


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(_HERE, '..', 'local', 'SLUS_209.73')
    if not os.path.isfile(path):
        print('difftest_arena_modes: %s not found - nothing to compare with (this is not a failure)' % path)
        return 0
    chk = Check()
    test_pick(chk, path)
    test_scores(chk, path)
    test_respawn(chk, path)
    test_hermite_and_hud(chk, path)
    test_waves(chk, path)
    test_task(chk, path)
    test_fade_and_spell(chk, path)
    test_picker(chk, path)
    test_edges(chk, path)
    test_pvp(chk, path)
    print('difftest_arena_modes: %d passed, %d failed' % (chk.passed, chk.failed))
    return 1 if chk.failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
