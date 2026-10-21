#!/usr/bin/env python3
"""difftest_dialog_gaps.py - compare tools/ref_dialog_gaps.py with the original functions.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_dialog_gaps.py [path/to/SLUS_209.73] [--seed N] [--cases N]

The originals run in tools/ee_emu.py on synthetic state.  Callees outside the function
under test are recording stubs fed with the same answers the reference is given, except
the leaf helpers named in each suite, which run as they are (cos16, sin16, hermite,
angle_approach, vec3_dotDelta, the matrix helpers, newlib sscanf / strcmp / strcasecmp /
strncmp / strlen / atoi / sprintf and the property-list helpers).  dialog_isOpen 0x22fbc0
always runs for real on the word 0x8e2d60.  No game file other than the executable is read.

Suites:
  view      Camera_setupDialogView 0x203bb8 (sscanf followed; stale stack slots planted)
  lookat    Camera_lookAt 0x204250
  runcam    dialog_runTask 0x22ff48 with the camera moving (lookAt followed)
  apply     Camera_apply 0x2035c8 (forward 0): matrix, shake, cosmetic seed
  frozen    game_isFrozen 0x1ebdf8, every input combination
  recall    player_pollRecallButton 0x1bce88
  camctl    Camera_update 0x203400: +0x60 and the mode dispatch
  idle      mainloop_runSession's idle voice 0x322b48-0x322c00 (cosmetic seed)
  sites     the other 19 dialog_isOpen sites, each as a stretch with labelled exits
  box       dialog_loadBox 0x22f910; ui_drawSpriteImpl 0x17b590 with a null texture
  buttons   game_initCamera 0x1e6b68
  factory   world_objectFactory 0x159c94 for class names no test matches
  seeds     no suite wrote a generator word it should not have
"""
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, MemoryFault  # noqa: E402
import ref_core as C  # noqa: E402
import ref_dialog_gaps as R  # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
HOME_ELF = os.path.expanduser('~/champions-re/SLUS_209.73')

F_IS_OPEN = 0x22FBC0
F_VIEW, F_LOOK, F_APPLY, F_UPDATE = 0x203BB8, 0x204250, 0x2035C8, 0x203400
F_RUN = 0x22FF48
F_FROZEN, F_RECALL = 0x1EBDF8, 0x1BCE88
F_LOAD_BOX, F_SPRITE = 0x22F910, 0x17B590
F_INIT_CAMERA = 0x1E6B68
F_FACTORY = 0x159C94
COS, SIN, HERMITE, APPROACH, DOT_DELTA = 0x166630, 0x1666E0, 0x1658F0, 0x166C18, 0x1667D8
MAT_IDENT, MAT_ROT = 0x165680, 0x163000
SSCANF = 0x3B7F88
STRCMP = 0x3B8534
D_DATA = 0x8E2D60
SEEDS = (0x404460, 0x404464, 0x404468)
G_NET = 0x402791
G_LOCAL_CAMERA = 0x4F8450
REC = 0x4C30

RESULTS = []
SEED_WRITES = []          # (suite, address) of every write to a generator word


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %-8s %s' % ('PASS' if ok else 'FAIL', name, detail))


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def new_emu(elf, follow):
    emu = EE(elf)
    emu.follow = set(follow) | {F_IS_OPEN}
    emu.default_ret = 0
    return emu


def note_seeds(suite, emu):
    for _pc, addr, _size, _val in emu.writes:
        if addr in SEEDS:
            SEED_WRITES.append((suite, addr))


def set_dialog(emu, open_):
    emu.mem.w32(D_DATA, 0x00C0FFE0 if open_ else 0)


def rf(rng, lo, hi):
    return C.f32(rng.uniform(lo, hi))


# =======================================================================================
# Camera_setupDialogView
# =======================================================================================

def offset_text(rng):
    k = rng.random()
    if k < 0.2:
        return None
    if k < 0.75:
        return '%d,%d,%d,%d' % tuple(rng.randint(-60, 120) for _ in range(4))
    return rng.choice(['%d,%d' % (rng.randint(-9, 99), rng.randint(-9, 99)), ' 7, -3,12,900',
                       '%d,%d,%d' % (rng.randint(0, 50), rng.randint(0, 50), rng.randint(-30, 30)),
                       'x', '', '5 ,6,7,8', '+4,+5,-6,7', '%d,%d,%d,%d,%d' % (1, 2, 3, 4, 5)])


def suite_view(elf, rng, cases):
    bad, seen = [], {'side': 0, 'none': 0, 'partial': 0, 'far': 0}
    for n in range(cases * 4):
        emu = new_emu(elf, {COS, SIN, DOT_DELTA, SSCANF})
        emu.follow = None                     # sscanf calls newlib internals: run all ...
        mem = emu.mem
        cam = emu.alloc(0x200)
        npc = emu.alloc(0x200)
        text = offset_text(rng)
        tptr = 0
        if text is not None:
            tptr = emu.alloc(64)
            mem.write(tptr, text.encode() + b'\0')
        asked = []

        def prop(e, tptr=tptr, asked=asked):
            asked.append((e.r[4] & 0xFFFFFFFF, e.mem.cstr(e.r[5] & 0xFFFFFFFF), s32(e.r[6])))
            return tptr
        emu.stub(0x14F4C0, function=prop, name='obj_getPropStr')
        unexpected = []
        for t in (0x2035C8, 0x18A2B0, 0x1EBDF8):     # ... but nothing that should not run
            emu.stub(t, function=lambda e, t=t: unexpected.append(t))
        npos = (rf(rng, -500, 500), rf(rng, -500, 500), rf(rng, -50, 50))
        facing = rng.randrange(-0x8000, 0x8000)
        for i in range(3):
            mem.w32(npc + 0x10 + 4 * i, npos[i])
        mem.w16(npc + 0x38, facing & 0xFFFF)
        players = []
        count = rng.randrange(0, 5)
        slots = rng.sample(range(4), count)
        for k, slot in enumerate(slots):
            obj = emu.alloc(0x40)
            if rng.random() < 0.7:
                p = tuple(C.add(npos[i], rf(rng, -70, 70)) for i in range(2)) + (C.add(npos[2], rf(rng, -20, 20)),)
            else:
                p = tuple(C.add(npos[i], rf(rng, -300, 300)) for i in range(3))
            for i in range(3):
                mem.w32(obj + 0x10 + 4 * i, p[i])
            mem.w32(R.G_PLAYER_OBJ + slot * REC, obj)
            mem.w32(R.G_ALIVE + 4 * k, slot)
            players.append(p)
        mem.w32(R.G_ALIVE_COUNT, count)
        campos = tuple(C.add(npos[i], rf(rng, -400, 400)) for i in range(3))
        for i in range(3):
            mem.w32(R.G_CAMERA_POS + 4 * i, campos[i])
        yaw, pitch = rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000)
        mem.w16(cam + 0x68, yaw & 0xFFFF)
        mem.w16(cam + 0x6A, pitch & 0xFFFF)
        side = rng.choice([0, 1, 1, 2])
        # the callee's frame is sp - 0xd0: plant stale values in its four sscanf slots
        sp = 0x01FFF000
        stale = tuple(rng.randint(-40, 40) for _ in range(4))
        for off, v in zip((0x60, 0x64, 0x6C, 0x68), stale):
            mem.w32(sp - 0xD0 + off, v & 0xFFFFFFFF)
        emu.call(F_VIEW, cam, npc, side, sp=sp)
        v = R.View(yaw, pitch)
        try:
            info = R.setup_dialog_view(v, npos, facing, side, players, campos, text, stale)
        except ValueError as exc:
            bad.append((n, 'ref refused', str(exc)))
            continue
        seen['side'] += side != 0
        seen['none'] += text is None
        seen['partial'] += text is not None and info['converted'] < 4
        seen['far'] += v.k == R.FAR_K
        got = {
            'start': [mem.u32(cam + 4 * i) for i in range(3)],
            'target': [mem.u32(cam + 0xC + 4 * i) for i in range(3)],
            'yaw0': mem.s16(cam + 0x76), 'yaw1': mem.s16(cam + 0x78), 'pitch1': mem.s16(cam + 0x7A),
            'pitch0': mem.s16(cam + 0x7C), 'p': mem.u32(cam + 0xA8), 'k': mem.u32(cam + 0xAC)}
        want = {'start': list(v.start), 'target': list(v.target), 'yaw0': v.start_yaw,
                'yaw1': v.target_yaw, 'pitch1': v.target_pitch, 'pitch0': v.start_pitch,
                'p': v.progress, 'k': v.k}
        if got != want or unexpected or asked != [(npc, 'dialogOffset', 0)]:
            bad.append((n, text, side, {k: (got[k], want[k]) for k in got if got[k] != want[k]},
                        unexpected, asked))
        note_seeds('view', emu)
    report('view', not bad, '%d runs %s%s' % (cases * 4, seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# Camera_lookAt and the run task's camera step
# =======================================================================================

def random_view(rng):
    v = R.View(rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000))
    v.start = [rf(rng, -500, 500) for _ in range(3)]
    v.target = [rf(rng, -500, 500) for _ in range(3)]
    v.start_yaw, v.target_yaw = rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000)
    v.start_pitch, v.target_pitch = rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000)
    v.progress = rng.choice([C.ZERO, C.ONE, rf(rng, 0, 1), rf(rng, -0.2, 1.2)])
    v.k = rng.choice([R.FAR_K, rf(rng, 0, 1), C.ZERO, C.ONE])
    return v


def put_view(mem, cam, v):
    for i in range(3):
        mem.w32(cam + 4 * i, v.start[i])
        mem.w32(cam + 0xC + 4 * i, v.target[i])
    mem.w16(cam + 0x68, v.yaw & 0xFFFF)
    mem.w16(cam + 0x6A, v.pitch & 0xFFFF)
    mem.w16(cam + 0x76, v.start_yaw & 0xFFFF)
    mem.w16(cam + 0x78, v.target_yaw & 0xFFFF)
    mem.w16(cam + 0x7A, v.target_pitch & 0xFFFF)
    mem.w16(cam + 0x7C, v.start_pitch & 0xFFFF)
    mem.w32(cam + 0xA8, v.progress)
    mem.w32(cam + 0xAC, v.k)


def get_view(mem, cam):
    return (mem.s16(cam + 0x68), mem.s16(cam + 0x6A), mem.u32(cam + 0xA8))


def suite_lookat(elf, rng, cases):
    bad, seen = [], {'arrived': 0, 'moved': 0, 'chains': 0}
    emu = new_emu(elf, {HERMITE, APPROACH})
    mem = emu.mem
    applied = []
    emu.stub(F_APPLY, function=lambda e: applied.append((e.f[12], e.f[13], e.f[14],
                                                         e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)),
             name='Camera_apply')
    cam = emu.alloc(0x200)
    out = emu.alloc(16)
    for n in range(cases * 4):
        v = random_view(rng)
        steps = rng.choice([45, -45, 45, -45, rng.randint(1, 90), -rng.randint(1, 90)])
        use_out = rng.random() < 0.7
        put_view(mem, cam, v)
        mem.w32(out, 0xDEADBEEF)
        del applied[:]
        emu.reset_log()
        ret = emu.call(F_LOOK, cam, steps, out if use_out else 0) & 0xFFFFFFFF
        res, h, pos = R.look_at(v, steps)
        want_apply = [] if pos is None else [pos + (cam, 0)]
        want_out = h if (use_out and h is not None) else 0xDEADBEEF
        seen['arrived' if res else 'moved'] += 1
        if (ret != res or applied != want_apply or mem.u32(out) != want_out
                or get_view(mem, cam) != (v.yaw, v.pitch, v.progress)):
            bad.append((n, steps, ret, res, applied, want_apply, get_view(mem, cam), (v.yaw, v.pitch, v.progress)))
        note_seeds('lookat', emu)
    # whole swoops: call until arrival, in and out
    for n in range(cases):
        v = random_view(rng)
        v.progress = C.ZERO
        put_view(mem, cam, v)
        k = 0
        for steps in (45, -45):
            while True:
                del applied[:]
                ret = emu.call(F_LOOK, cam, steps, 0) & 0xFFFFFFFF
                res, _h, pos = R.look_at(v, steps)
                k += 1
                if ret != res or get_view(mem, cam) != (v.yaw, v.pitch, v.progress):
                    bad.append(('chain', n, steps, k))
                    break
                if res == 1 or k > 400:
                    break
        seen['chains'] += 1
    report('lookat', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


def suite_runcam(elf, rng, cases):
    bad, seen = [], {'open': 0, 'close': 0, 'sent3': 0, 'shop_wait': 0, 'repeat': 0}
    for n in range(cases * 2):
        emu = new_emu(elf, {F_LOOK, HERMITE, APPROACH, F_RUN})
        mem = emu.mem
        log = []
        emu.stub(F_APPLY, function=lambda e: log.append(('apply', (e.f[12], e.f[13], e.f[14]))),
                 name='Camera_apply')
        emu.stub(0x18617C, function=lambda e: log.append(('far_clip', e.f[12])), name='camera_setFarClip')
        emu.stub(0x13DB38, function=lambda e: log.append(('send', e.mem.u8(e.r[5] & 0xFFFFFFFF))),
                 name='net_sendGameMsg')
        cam = emu.alloc(0x200)
        mem.w32(G_LOCAL_CAMERA, cam)
        v = random_view(rng)
        v.progress = rng.choice([C.ZERO, C.ONE, rf(rng, 0, 1), rf(rng, 0.9, 1.0), rf(rng, 0, 0.1)])
        put_view(mem, cam, v)
        direction = rng.choice([1, -1])
        swoop_done = rng.choice([0, 0, 1])
        shop = rng.choice([0, 0, 0, 1])
        fz = rng.choice([rf(rng, -1, 0), C.f32(-0.5), C.f32(-0.6), C.f32(-0.7), rf(rng, -1, 1)])
        mem.w32(0x8E2D50, direction & 0xFFFFFFFF)
        mem.w32(0x4FDCE8, swoop_done)
        mem.w32(0x41B50C, shop)
        mem.w32(0x44F130, fz)
        mem.w32(0x8E2E94, 7)
        emu.call(F_RUN)
        acts, _h = R.run_task_camera(v, direction, swoop_done, shop, fz)
        want = [a for a in acts if a[0] != 'arrived']
        moved = 0 if ('arrived',) in acts else direction
        if direction == -1 and shop:
            moved = -1
            seen['shop_wait'] += 1
        seen['open' if direction == 1 else 'close'] += 1
        seen['sent3'] += ('send', 3) in acts
        seen['repeat'] += sum(1 for a in acts if a[0] == 'apply') > 1
        if (log != want or s32(mem.u32(0x8E2D50)) != moved
                or get_view(mem, cam) != (v.yaw, v.pitch, v.progress) or mem.u32(0x8E2E90) != 0):
            bad.append((n, direction, swoop_done, shop, log[:3], want[:3], s32(mem.u32(0x8E2D50)), moved))
        note_seeds('runcam', emu)
    report('runcam', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# Camera_apply
# =======================================================================================

def suite_apply(elf, rng, cases):
    bad, seen = [], {'shake': 0, 'still': 0, 'frozen_dialog': 0, 'frozen_blocked': 0}
    for n in range(cases * 3):
        emu = new_emu(elf, {MAT_IDENT, MAT_ROT, COS, SIN})
        mem = emu.mem
        cam = emu.alloc(0x200)
        frozen = rng.choice([0, 0, 1])
        dialog = rng.choice([0, 1])
        emu.stub(F_FROZEN, ret=frozen, name='game_isFrozen')
        got = {}

        def view(e):
            pa, ma = e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF
            got['pos'] = tuple(e.mem.u32(pa + 4 * i) for i in range(3))
            got['m'] = [e.mem.u32(ma + 4 * i) for i in range(12)]
        emu.stub(0x18A2B0, function=view, name='camera_setView')
        set_dialog(emu, dialog)
        yaw, pitch = rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000)
        mem.w16(cam + 0x68, yaw & 0xFFFF)
        mem.w16(cam + 0x6A, pitch & 0xFFFF)
        shake = rng.choice([C.ZERO, rf(rng, 0.01, 8), rf(rng, 0.01, 8), C.f32(-1.0), C.HALF])
        seed = rng.randrange(1 << 32)
        mem.w32(R.G_CAMERA_SHAKE, shake)
        mem.w32(R.G_COSMETIC_SEED, seed)
        pos = tuple(rf(rng, -1000, 1000) for _ in range(3))
        emu.call(F_APPLY, cam, 0, fargs=[C.to_float(p) for p in pos])
        wpos, wm, wshake, wseed, draws = R.camera_apply(pos, yaw, pitch, shake, seed, frozen, dialog)
        asked_dialog = any(c.target == F_IS_OPEN for c in emu.calls)
        want_asked = C.lt(C.ZERO, shake) and bool(frozen)
        seen['shake' if draws else 'still'] += 1
        if draws and frozen:
            seen['frozen_dialog'] += 1
        if C.lt(C.ZERO, shake) and frozen and not dialog:
            seen['frozen_blocked'] += 1
        if (got.get('pos') != wpos or got.get('m') != wm or mem.u32(R.G_CAMERA_SHAKE) != wshake
                or mem.u32(R.G_COSMETIC_SEED) != wseed or asked_dialog != want_asked):
            bad.append((n, frozen, dialog, got.get('pos'), wpos, hex(mem.u32(R.G_COSMETIC_SEED)), hex(wseed)))
        for _pc, addr, _s, _v in emu.writes:
            if addr in SEEDS and (addr != R.G_COSMETIC_SEED or not draws):
                bad.append((n, 'seed write', hex(addr)))
    report('apply', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# game_isFrozen, player_pollRecallButton, Camera_update
# =======================================================================================

def suite_frozen(elf, rng, cases):
    bad, n = [], 0
    emu = new_emu(elf, set())
    mem = emu.mem
    for bits in range(1 << 7):
        for frame in (10, 59, 60, 500):
            s = R.Frozen(network=bits & 1, paused=(bits >> 1) & 1, cutscene=(bits >> 2) & 1,
                         warmup=((bits >> 3) & 1) * rng.choice([1, 7]), player_select=(bits >> 4) & 1,
                         controller_out=(bits >> 5) & 1, dialog=(bits >> 6) & 1, sim_frame=frame)
            mem.w8(G_NET, s.network)
            mem.w32(0x41B4F4, s.paused)
            mem.w8(0x44FCD0, s.cutscene)
            mem.w32(0x506048, s.warmup)
            mem.w32(0x44FDCC, s.sim_frame)
            mem.w8(0x4F6708, s.controller_out)
            set_dialog(emu, s.dialog)
            emu.stub(0x19E5E8, ret=s.player_select, name='task_isRunning')
            emu.reset_log()
            ret = s32(emu.call(F_FROZEN))
            log = []
            want = R.game_is_frozen(s, log)
            calls = [('task',) if c.target == 0x19E5E8 else ('dialog',) for c in emu.calls]
            n += 1
            if ret != want or calls != log:
                bad.append((bits, frame, ret, want, calls, log))
    report('frozen', not bad, '%d input sets%s' % (n, '' if not bad else ' ' + repr(bad[:2])))


def suite_recall(elf, rng, cases):
    bad, seen = [], {'sent': 0, 'players': 0}
    for n in range(cases * 3):
        emu = new_emu(elf, set())
        mem = emu.mem
        count = rng.randrange(0, 5)
        slots = rng.sample(range(4), count)
        players = []
        frozen = rng.random() < 0.15
        lockout = rng.random() < 0.1
        dialog = rng.random() < 0.3
        recall = rng.random() < 0.1
        b66c8 = rng.random() < 0.1
        jump = rng.random() < 0.1
        pause = rng.random() < 0.1
        camflags = {}
        mem.w32(0x41B4FC, int(lockout))
        mem.w8(0x41B51D, int(recall))
        mem.w8(0x4F66C8, int(b66c8))
        set_dialog(emu, dialog)
        emu.stub(F_FROZEN, ret=int(frozen), name='game_isFrozen')
        emu.stub(0x13E110, function=lambda e: camflags.get(s32(e.r[4]), 0), name='net_getCamFlag')
        emu.stub(0x19E5E8, function=lambda e: int(jump) if e.mem.cstr(e.r[4] & 0xFFFFFFFF) == 'jumpgate'
                 else int(pause), name='task_isRunning')
        sent = []
        emu.stub(0x1DE138, function=lambda e: sent.append(s32(e.r[4])), name='hudmsg_sendRecall')
        mem.w32(0x4F8424, count)
        for k, slot in enumerate(slots):
            obj = emu.alloc(0x600)
            mem.w32(R.G_PLAYER_OBJ + slot * REC, obj)
            mem.w32(0x4F8430 + 4 * k, slot)
            p = {'slot': slot, 'lockout': lockout, 'frozen': frozen, 'dialog': dialog,
                 'obj4b4': rng.random() < 0.1, 'recall': recall, 'b4f66c8': b66c8,
                 'camflag': rng.random() < 0.1, 'jumpgate': jump, 'pausemenu': pause,
                 'obj540': rng.random() < 0.1, 'flag400000': rng.random() < 0.1,
                 'use': rng.random() < 0.7, 'b100': rng.random() < 0.7}
            camflags[slot] = int(p['camflag'])
            mem.w16(obj + 0x4B4, int(p['obj4b4']))
            mem.w32(obj + 0x540, int(p['obj540']))
            mem.w32(obj + 0xC, 0x400000 if p['flag400000'] else 0x10)
            mask = rng.choice([0x10, 0x4000, 0x80])
            mem.w32(0x41B9C0 + 4 * slot, mask)
            mem.w32(0x4028D8 + slot * 0x58, mask if p['use'] else 0)
            mem.w32(0x4028DC + slot * 0x58, 0x100 if p['b100'] else 0x1)
            players.append(p)
        emu.call(F_RECALL)
        want = R.recall_poll(players)
        seen['sent'] += len(want)
        seen['players'] += count
        if sent != want:
            bad.append((n, sent, want))
        note_seeds('recall', emu)
    report('recall', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


def suite_camctl(elf, rng, cases):
    bad, seen = [], {'allowed': 0, 'dialog_off': 0}
    for n in range(cases * 4):
        emu = new_emu(elf, set())
        mem = emu.mem
        cam = emu.alloc(0x200)
        c = {k: int(rng.random() < 0.15) for k in ('frozen', 'menu', 'warmup', 'b66c8', 'lockout', 'flag4')}
        c['world'] = int(rng.random() < 0.9)
        c['dialog'] = rng.choice([0, 1])
        mode = rng.choice([1, 1, 2, 0, 6])
        trans = rng.choice([0, 0, 1, 2])
        emu.stub(F_FROZEN, ret=c['frozen'], name='game_isFrozen')
        emu.stub(0x1BF4F0, ret=c['flag4'], name='game_localPlayerFlag400000')
        calls = []
        emu.stub(0x204938, function=lambda e: calls.append('follow'), name='Camera_updateFollow')
        emu.stub(0x206FD8, function=lambda e: calls.append('orbit'), name='Camera_updateOrbit')
        mem.w32(0x44FDC8, 0x00ABCDE0 if c['world'] else 0)
        mem.w32(0x41B4F8, c['menu'])
        mem.w32(0x506048, c['warmup'])
        mem.w8(0x4F66C8, c['b66c8'])
        mem.w32(0x41B4FC, c['lockout'])
        set_dialog(emu, c['dialog'])
        mem.w32(cam + 0x34, mode)
        mem.w32(cam + 0x48, trans)
        mem.w32(cam + 0x60, 0x55)
        mem.w8(0x4F66C9, 9)
        emu.call(F_UPDATE, cam)
        want = R.camera_update_control(c['frozen'], c['world'], c['menu'], c['warmup'], c['b66c8'],
                                       c['dialog'], c['lockout'], c['flag4'])
        want_calls, want_trans = [], trans
        if mode == 1 or trans != 0:
            want_calls = ['follow']
            if trans == 1 and mode != 1:
                want_trans = 2
        elif mode == 2:
            want_calls = ['orbit']
        seen['allowed'] += want
        seen['dialog_off'] += c['dialog'] and not c['frozen'] and c['world']
        if (mem.u32(cam + 0x60) != want or calls != want_calls or mem.u32(cam + 0x48) != want_trans
                or mem.u8(0x4F66C9) != 0):
            bad.append((n, c, mode, trans, mem.u32(cam + 0x60), want, calls, want_calls))
        note_seeds('camctl', emu)
    report('camctl', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# mainloop_runSession's idle voice
# =======================================================================================

def suite_idle(elf, rng, cases):
    bad, seen = [], {'voice': 0, 'held': 0, 'count': 0}
    for n in range(cases * 3):
        emu = new_emu(elf, set())
        mem = emu.mem
        cd = rng.choice([0, -3, 1, 2, 2, 3, rng.randint(4, 900)])
        cut, paused, menu = (int(rng.random() < 0.15) for _ in range(3))
        dialog = rng.choice([0, 1])
        players = rng.choice([1, 2, 3, 4, 0])
        seed = rng.randrange(1 << 32)
        mem.w32(R.G_IDLE_VOICE, cd & 0xFFFFFFFF)
        mem.w8(0x44FCD0, cut)
        mem.w32(0x41B4F4, paused)
        mem.w8(0x41B69D, menu)
        set_dialog(emu, dialog)
        mem.w32(0x4D8AE0, players)
        mem.w32(R.G_COSMETIC_SEED, seed)
        voices = []
        emu.stub(0x1B7BA8, function=lambda e: voices.append((s32(e.r[4]), s32(e.r[5]))), name='player_voice')
        emu.r[31] = emu.RETURN_ADDR
        stop = emu.run(0x322B48, until=(0x322C00, 0x322C04))
        wcd, wseed, slot = R.idle_voice(cd, cut, paused, menu, dialog, players, seed)
        want_voices = [] if slot is None else [(slot, 2)]
        label = R.site_outcome('idle_voice', {'countdown': cd, 'cutscene': cut, 'paused': paused,
                                              'local_menu': menu, 'dialog': dialog, 'players': players})
        seen['voice' if slot is not None else ('held' if label == 'held' else 'count')] += 1
        if (stop != 'stop' or s32(mem.u32(R.G_IDLE_VOICE)) != wcd or mem.u32(R.G_COSMETIC_SEED) != wseed
                or voices != want_voices):
            bad.append((n, cd, cut, paused, menu, dialog, players, s32(mem.u32(R.G_IDLE_VOICE)), wcd, voices, want_voices))
        for _pc, addr, _s, _v in emu.writes:
            if addr in SEEDS and (addr != R.G_COSMETIC_SEED or slot is None):
                bad.append((n, 'seed write', hex(addr)))
    report('idle', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# The 19 site stretches
# =======================================================================================

def _cam(emu, mode):
    cam = emu.alloc(0x100)
    emu.mem.w32(cam + 0x34, mode)
    emu.mem.w32(G_LOCAL_CAMERA, cam)


def site_case(name, emu, c):
    """-> (start pc, stops {pc: label} or None, label_fn(emu, stop_label))."""
    mem, r = emu.mem, emu.r
    g = lambda k: c.get(k, 0)   # noqa: E731
    same = lambda e, lab: lab   # noqa: E731
    if name in ('prop_draw', 'phprop_draw'):
        r[4] = emu.alloc(0x300)
        if name == 'prop_draw':
            return 0x1548BC, {0x1548E0: 'draw', 0x1549D4: 'skip'}, same
        return 0x156DB4, {0x156DDC: 'draw', 0x156F58: 'skip'}, same
    table = 0x44F3B8
    if name == 'pause_exit':
        r[2], r[17], r[18] = 0x4F0000, table, 0x20
        mem.w32(0x4F7120, g('pvp_b'))
        mem.w32(table + 0x24, 0x77)
        mem.w32(table + 0x2C, 0x2)

        def lab(e, _):
            if e.mem.u32(table + 0x2C) & 1:
                return 'hidden'
            return 'disabled' if e.mem.u32(table + 0x24) == 5 else 'unchanged'
        return 0x18CCE0, {0x18CD20: 'end'}, lab
    if name == 'pause_kick':
        r[17], r[18], r[19] = g('active'), 0x30, 0x450000
        mem.w32(table + 0x34, 0x77)
        mem.w32(table + 0x3C, 0x2 | (1 - (g('active') < 2)))

        def lab(e, _):
            f = 'hidden+' if e.mem.u32(table + 0x3C) & 1 else 'shown+'
            v = e.mem.u32(table + 0x34)
            return f + {5: 'disabled', 0: 'enabled'}.get(v, '?%x' % v)
        return 0x18CE70, {0x18CF00: 'end'}, lab
    if name in ('pause_recall', 'pause_change'):
        r[17], r[18], r[19] = 0x40, 0x44FA70, 0x450000
        mem.w32(0x44FA70, table)
        mem.w32(table + 0x44, 0x77)
        mem.w8(G_NET, g('network'))
        _cam(emu, g('cam_mode'))

        def lab(e, _):
            v = e.mem.u32(table + 0x44)
            return {5: 'disabled', 0: 'enabled'}.get(v, '?%x' % v)
        if name == 'pause_recall':
            emu.stub(0x13E1F0, ret=1, name='net_getLocalPlayerSlot')
            mem.w32(0x4D8AF0 + REC + 0xAC, C.f32(0.0 if g('hp_le0') else 25.0))
            emu.stub(0x19E5E8, ret=g('jumpgate'), name='task_isRunning')
            return 0x18D3C4, {0x18D4D4: 'end'}, lab
        emu.stub(0x1E7B78, ret=g('no_save'), name='game_inNoSaveZone')
        return 0x18D478, {0x18D4D4: 'end', 0x18D4D8: 'end', 0x18D4F0: 'end'}, lab
    if name == 'warp_menu':
        mem.w32(0x44FDA4, 100000)
        mem.w32(0x44FE0C, 0x1000)
        mem.w32(0x44FE10, 0x1000)
        emu.stub(F_FROZEN, ret=0, name='game_isFrozen')
        emu.stub(0x27DD68, ret=0, name='jumpgate_getTravelState')
        mem.w8(G_NET, 0)
        _cam(emu, g('cam_mode'))
        return 0x18E00C, {0x18E0F4: 'continue', 0x18E1E8: 'blocked'}, same
    if name == 'player_interact':
        obj = emu.alloc(0x500)
        mem.w32(obj + 0x3C8, 2)
        r[21] = obj
        mem.w32(0x41B4F4, g('paused'))
        mem.w32(0x41B4FC, g('lockout'))
        mem.w32(0x41B818 + 8, g('selector'))
        return 0x1A4784, {0x1A47CC: 'go', 0x1A480C: 'skip'}, same
    if name == 'player_name':
        obj = emu.alloc(0x500)
        mem.w32(obj + 0x3C8, 1)
        mem.w32(obj + 0xC, 0x400000 if g('flag400000') else 0x8)
        r[21] = obj
        mem.w8(G_NET, g('network'))
        emu.stub(0x13E150, ret=g('local'), name='net_isLocalSlot')
        return 0x1A4EA8, {0x1A4EE8: 'tag', 0x1A4FF8: 'skip', 0x1A4FF4: 'skip'}, same
    if name == 'player_marker':
        obj = emu.alloc(0x600)
        r[4] = obj
        mem.w32(0x4D8AE0, 2)
        mem.w32(0x4F8458, 1)
        emu.stub(0x13E110, ret=0, name='net_getCamFlag')
        return 0x1BBFF8, {0x1BC08C: 'draw', 0x1BC2C4: 'skip', 0x1BC2C0: 'skip'}, same
    if name == 'controller_out':
        r[19], r[20], r[17] = 1, 0x400000, 0x4F0000
        mem.w8(G_NET, g('network'))
        emu.stub(0x18CBFC, ret=g('pause_open'), name='pauseMenu_isOpen')
        mem.w32(0x41B510, g('frontend'))
        return 0x1DB584, {0x1DB5C0: 'go', 0x1DB690: 'skip'}, same
    if name == 'spell_select':
        r[4] = 0x420000
        mem.w32(0x41B4FC, g('lockout'))
        return 0x1DD374, {0x1DD390: 'next', 0x1DD40C: 'fallback', 0x1DD410: 'fallback'}, same
    if name in ('hud_panel_input', 'hud_panel_button'):
        _cam(emu, g('cam_mode'))
        mem.w32(0x41B4F4, g('paused'))
        if name == 'hud_panel_input':
            r[5] = g('lockout')
            r[17] = emu.alloc(0x100)
            return 0x1DE9D8, {0x1DEA18: 'go', 0x1DEA84: 'skip', 0x1DEA88: 'skip'}, same
        mem.w32(0x41B4FC, g('lockout'))
        r[20] = 0x4D8AF0
        return 0x1DEDB4, {0x1DEDFC: 'go', 0x1DEE7C: 'skip'}, same
    if name == 'compass':
        mem.w32(0x4F8424, 1)
        mem.w32(0x4F841C, 2)
        mem.w32(R.G_PLAYER_OBJ + 2 * REC, emu.alloc(0x100))
        mem.w8(0x4F66D5, g('compass_on'))
        return 0x1DF720, {0x1DF7DC: 'go', 0x1DFA74: 'skip', 0x1DFA78: 'skip'}, same
    if name == 'net_cam_prompt':
        mem.w8(G_NET, 1)
        emu.stub(0x13E1F0, ret=0, name='net_getLocalPlayerSlot')
        emu.stub(0x1EC580, ret=1, name='game_is4f713cOtherSlot')
        emu.stub(0x2074C8, ret=0, name='Camera_cycleSpectated')
        mem.w8(0x44FCD0, g('cutscene'))
        emu.stub(0x18CBFC, ret=g('pause_open'), name='pauseMenu_isOpen')
        _cam(emu, 1)
        return 0x1E01B8, {0x1E0290: 'go', 0x1E03A8: 'skip', 0x1E03AC: 'skip'}, same
    if name == 'status_fx':
        r[3], r[5] = g('flag10000000'), g('model')
        return 0x1F6B68, {0x1F6B88: 'go', 0x1FAD8C: 'skip', 0x1FAD90: 'skip'}, same
    if name == 'save_screen':
        mem.w8(G_NET, g('network'))
        mem.w8(0x41B6D0, g('pending_level'))
        mem.w8(0x44FCD0, g('cutscene'))
        return 0x218EE8, {0x218F24: 'go', 0x219088: 'abort'}, same
    if name == 'net_messages':
        mem.w8(G_NET, g('network'))
        emu.stub(0x31D34C, ret=0xFFFFFFFFFFFFFFFF, name='0x31d34c')
        mem.w32(0x41B510, g('frontend'))
        mem.w32(0x50391C, g('list_on'))
        return 0x31DEEC, {0x31DF60: 'go', 0x31E180: 'skip', 0x31E184: 'offline'}, same
    raise KeyError(name)


SITE_CONDITIONS = {
    'prop_draw': (), 'phprop_draw': (), 'player_marker': (),
    'pause_exit': ('pvp_b',), 'pause_kick': ('active',),
    'pause_recall': ('network', 'hp_le0', 'jumpgate', 'cam_mode'),
    'pause_change': ('network', 'no_save', 'cam_mode'), 'warp_menu': ('cam_mode',),
    'player_interact': ('paused', 'lockout', 'selector'),
    'player_name': ('network', 'flag400000', 'local'),
    'controller_out': ('network', 'pause_open', 'frontend'), 'spell_select': ('lockout',),
    'hud_panel_input': ('lockout', 'cam_mode', 'paused'),
    'hud_panel_button': ('lockout', 'cam_mode', 'paused'), 'compass': ('compass_on',),
    'net_cam_prompt': ('cutscene', 'pause_open'), 'status_fx': ('flag10000000', 'model'),
    'save_screen': ('network', 'pending_level', 'cutscene'),
    'net_messages': ('network', 'frontend', 'list_on'),
}
FULL_SUITES = {'recall_button': 'recall', 'is_frozen': 'frozen', 'camera_control': 'camctl',
               'camera_shake': 'apply', 'idle_voice': 'idle'}


def suite_sites(elf, rng, cases):
    bad, labels = [], {}
    names = [n for n in R.SITES if n not in FULL_SUITES]
    assert sorted(names) == sorted(SITE_CONDITIONS), 'site table mismatch'
    for name in names:
        site, func, _kind, _what = R.SITES[name]
        for n in range(max(32, cases)):
            emu = new_emu(elf, set())
            c = {k: (rng.choice([0, 1, 2, 3]) if k == 'active' else
                     rng.choice([1, 1, 0, 2]) if k == 'cam_mode' else int(rng.random() < 0.3))
                 for k in SITE_CONDITIONS[name]}
            if name == 'compass':
                c['compass_on'] = int(rng.random() < 0.7)
            if name == 'status_fx':
                c['model'] = int(rng.random() < 0.8)
            c['dialog'] = n % 2 if n < 4 else rng.choice([0, 1])
            set_dialog(emu, c['dialog'])
            emu.r[31] = emu.RETURN_ADDR
            emu.r[29] = 0x01FF0000
            start, stops, lab = site_case(name, emu, c)
            try:
                stop = emu.run(start, until=tuple(stops), max_steps=200000)
            except EmuError as exc:
                bad.append((name, c, 'emu', str(exc)[:80]))
                continue
            got = lab(emu, stops.get(emu.pc)) if stop == 'stop' else 'returned'
            want = R.site_outcome(name, c)
            called = [k.site for k in emu.calls if k.target == F_IS_OPEN]
            reached_site = site in called
            labels.setdefault(name, set()).add(got)
            if got != want:
                bad.append((name, c, got, want))
            # the gate is only asked once the conditions before it pass
            if c['dialog'] and got == want and want in ('skip', 'blocked', 'disabled', 'fallback', 'abort',
                                                         'held') and not reached_site and called:
                bad.append((name, c, 'gate asked from elsewhere', called))
            note_seeds('sites', emu)
    both = sum(1 for n in names if len(labels.get(n, ())) >= 2)
    one = [n for n in names if len(labels.get(n, ())) < 2]
    report('sites', not bad, '%d sites, %d with two or more outcomes seen %s%s' % (
        len(names), both, one, '' if not bad else ' ' + repr(bad[:3])))


# =======================================================================================
# dialog_loadBox and the sprite with no texture
# =======================================================================================

def suite_box(elf, rng, cases):
    bad, seen = [], {'kept': 0, 'loaded': 0, 'fault0': 0, 'read_ok': 0}
    for n in range(cases):
        emu = new_emu(elf, {STRCMP})
        mem = emu.mem
        level = rng.choice(['intro', 'Intro', 'intro2', 'level', 'arena', ''])
        pvp = rng.choice([0, 0, 1])
        old = rng.choice([0, 0x00ABC100])
        found = rng.choice([0, 0x00BCD200])
        mem.write(R.G_LEVEL_NAME, level.encode() + b'\0')
        mem.w32(R.G_PVP_MODE_B, pvp)
        mem.w32(R.G_BOX_TEX, old)
        asked = []
        emu.stub(0x17365C, function=lambda e: asked.append((e.mem.cstr(e.r[4] & 0xFFFFFFFF),
                                                            e.mem.cstr(e.r[5] & 0xFFFFFFFF))) or found,
                 name='res_find')
        emu.call(F_LOAD_BOX)
        want = R.load_box(level, pvp, old, found)
        want_asked = [] if want == old and (level == 'intro' or pvp) else [('dlgbox.lmp', 'box.tex')]
        seen['kept' if not want_asked else 'loaded'] += 1
        if mem.u32(R.G_BOX_TEX) != want or asked != want_asked:
            bad.append((n, level, pvp, hex(mem.u32(R.G_BOX_TEX)), hex(want), asked))
    emu = new_emu(elf, set())
    if emu.mem.u32(R.G_BOX_TEX) != R.BOX_WORD_INITIAL:
        bad.append(('initial word', hex(emu.mem.u32(R.G_BOX_TEX))))
    # ui_drawSpriteImpl(tex, 35, 280, 5, colour) as dialog_drawTask calls it (0x230ad8-0x230aec)
    for tex in (0, 'texture'):
        emu = new_emu(elf, set())
        mem = emu.mem
        mem.w32(0x44FDA4, 100000)
        dl = emu.alloc(0x400)
        mem.w32(0x44FE0C, dl)
        mem.w32(0x44FE10, dl)
        emu.reads = []
        addr = 0
        if tex != 0:
            addr = emu.alloc(0x40)
            mem.w16(addr, 560)
            mem.w16(addr + 2, 156)
        try:
            emu.call(F_SPRITE, addr, 35, 280, 5, 0x80808080)
            ok = tex != 0 and any(a == addr for _pc, a, _s, _v in emu.reads)
            seen['read_ok'] += ok
            if not ok:
                bad.append(('sprite', tex, 'no read of the texture header'))
        except MemoryFault as exc:
            if tex == 0 and getattr(exc, 'addr', None) in (0, 2):
                seen['fault0'] += 1
            else:
                bad.append(('sprite', tex, str(exc)[:80]))
        try:
            R.box_sprite_reads(addr)
            if tex == 0:
                bad.append(('ref did not refuse',))
        except ValueError:
            if tex != 0:
                bad.append(('ref refused a texture',))
    report('box', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# game_initCamera
# =======================================================================================

def suite_buttons(elf, rng, cases):
    bad, seen = [], {}
    watch = set(R.BUTTON_WORDS[0]) | set(R.BUTTON_WORDS[1]) | {0x4F85B4, 0x4F7134}
    for layout in (0, 1, 2, -1, 0x7F, 1, 0):
        emu = new_emu(elf, set())
        mem = emu.mem
        first = rng.choice([0, 1])
        mem.w32(0x4F834C, first)
        mem.w8(R.G_BUTTON_LAYOUT, layout & 0xFF)
        for a in watch:
            mem.w32(a, 0x5A5A)
        calls = []
        emu.stub(0x2071A8, function=lambda e: calls.append('Camera_init'), name='Camera_init')
        emu.stub(0x1EBCA0, function=lambda e: calls.append('skills'), name='skills_callVslot9All')
        emu.call(F_INIT_CAMERA)
        want = R.init_camera_buttons(layout)
        got = {a: mem.u32(a) for a in watch if mem.u32(a) != 0x5A5A}
        want_calls = (['Camera_init'] if not first else []) + ['skills']
        seen[layout] = hex(want.get(R.G_GLYPH_CONFIRM, 0))
        if got != want or calls != want_calls or mem.u32(G_LOCAL_CAMERA) == 0:
            bad.append((layout, {hex(a): hex(v) for a, v in got.items()}, calls))
    report('buttons', not bad, 'glyph byte by layout %s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


# =======================================================================================
# world_objectFactory's property fallback
# =======================================================================================

FACTORY_HELPERS = None


def factory_run(elf, class_name, entries, emu=None):
    """Run world_objectFactory(class, &pos, angle, list) with pool_new and every
    constructor stubbed -> (constructor address or None, return value)."""
    global FACTORY_HELPERS
    if emu is None:
        emu = EE(elf)
    mem = emu.mem
    if FACTORY_HELPERS is None:
        FACTORY_HELPERS = factory_callees(emu)
    emu.follow = None
    made = []
    pool = emu.alloc(0x40)
    emu.stub(0x14FDB8, ret=pool, name='pool_new')
    for t in FACTORY_HELPERS:
        emu.stub(t, function=lambda e, t=t: made.append(t), name='ctor')
    cls = emu.alloc(len(class_name) + 8)
    mem.write(cls, class_name.encode('latin1') + b'\0')
    lst = emu.alloc(4 * (len(entries) + 2))
    for i, e in enumerate(entries):
        p = emu.alloc(len(e) + 8)
        mem.write(p, e.encode('latin1') + b'\0')
        mem.w32(lst + 4 * i, p)
    mem.w32(lst + 4 * len(entries), 0)
    pos = emu.alloc(16)
    ret = emu.call(F_FACTORY, cls, pos, 0, lst, max_steps=3000000) & 0xFFFFFFFF
    return (made[0] if made else None), ret


def factory_callees(emu):
    """Every jal target inside the factory body 0x159c94-0x15d9c4 except the string and
    property helpers, which run as they are."""
    helpers = {0x3B81A0, 0x159C20, 0x14F730, 0x14F850, 0x23A2B4, 0x23A200, 0x23A100, 0x14FDB8}
    out = set()
    for a in range(F_FACTORY, 0x15D9C8, 4):
        w = emu.mem.u32(a)
        if w >> 26 == 3:
            t = ((a + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
            if t not in helpers:
                out.add(t)
    return out


FALLBACK_KEYS = ('CreatureContainer', 'AutoContainer', 'AutoChest', 'AutoProp', 'AutoEmitter',
                 'AutoDoor', 'AutoSwitch', 'Critter', 'Generator', 'SmokeGen', 'ParticleEmitter',
                 'DynamicLight', 'Halo', 'Halo2', 'DynamicLight0', 'ParticleEmitter3', 'Halo4')
OTHER_KEYS = ('dialogscript', 'showname', 'key', 'name', 'model')


def random_entries(rng):
    out = []
    for _ in range(rng.randrange(0, 6)):
        if rng.random() < 0.65:
            k = rng.choice(FALLBACK_KEYS)
            k = rng.choice([k.lower(), k.lower(), k, k.upper()])
        else:
            k = rng.choice(OTHER_KEYS)
        v = rng.choice(['1', '0', '7', '', 'abc', ' 3', '-2', 'x1'])
        out.append('%s=%s' % (k, v) if rng.random() < 0.95 else k)
    return out


def suite_factory(elf, rng, cases):
    bad, seen = [], {}
    by_addr = {a: k for k, (a, _s) in R.FALLBACK_CTORS.items()}
    for n in range(cases * 3):
        cls = rng.choice(['TestLocation', 'testlocation', 'TestLocationX', 'NoSuchClass'])
        entries = random_entries(rng)
        if n % 7 == 0:
            entries = []
        try:
            ctor, ret = factory_run(elf, cls, entries)
        except EmuError as exc:
            bad.append((n, cls, entries, str(exc)[:80]))
            continue
        want = R.factory_fallback(entries)
        got = by_addr.get(ctor, None if ctor is None else hex(ctor))
        seen[want or 'none'] = seen.get(want or 'none', 0) + 1
        if got != want or (want is None and ret != 0):
            bad.append((n, cls, entries, got, want, hex(ret)))
    report('factory', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


def suite_seeds(elf, rng, cases):
    report('seeds', not SEED_WRITES, 'writes to the generator words outside apply/idle: %d%s' % (
        len(SEED_WRITES), '' if not SEED_WRITES else ' ' + repr(SEED_WRITES[:3])))


def find_elf(argv):
    for a in argv:
        if not a.startswith('--') and os.path.isfile(a):
            return a
    for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'local', 'SLUS_209.73'),
              HOME_ELF):
        if os.path.isfile(p):
            return p
    return None


def check_elf(elf):
    import hashlib
    return hashlib.sha256(open(elf, 'rb').read()).hexdigest() == ELF_SHA


def main(argv):
    seed, cases = 20973, 60
    for i, a in enumerate(argv):
        if a == '--seed':
            seed = int(argv[i + 1])
        if a == '--cases':
            cases = int(argv[i + 1])
    elf = find_elf([a for i, a in enumerate(argv) if i == 0 or argv[i - 1] not in ('--seed', '--cases')])
    if elf is None:
        print('difftest_dialog_gaps: no SLUS_209.73 found; nothing to compare (exit 0)')
        return 0
    if not check_elf(elf):
        print('difftest_dialog_gaps: %s is not US v2.00' % elf)
        return 0
    C.set_fpu('ps2')
    print('difftest_dialog_gaps: seed %d, %d cases per suite' % (seed, cases))
    for suite in (suite_view, suite_lookat, suite_runcam, suite_apply, suite_frozen, suite_recall,
                  suite_camctl, suite_idle, suite_sites, suite_box, suite_buttons, suite_factory,
                  suite_seeds):
        rng = random.Random('%d/%s' % (seed, suite.__name__))
        try:
            suite(elf, rng, cases)
        except Exception as exc:          # a harness error is a failure, not a crash
            import traceback
            traceback.print_exc()
            report(suite.__name__[6:], False, 'harness error %r' % exc)
    failed = [n for n, ok in RESULTS if not ok]
    print('difftest_dialog_gaps: %d suites, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
