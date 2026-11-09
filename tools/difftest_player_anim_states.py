#!/usr/bin/env python3
"""Run the original player animation-state code in ee_emu and compare it with
tools/ref_player_anim_states.py.

  python3 tools/difftest_player_anim_states.py /path/to/SLUS_209.73 --seed N

Four parts, all on constructed state (no game data is read or written):
  L  Player_move 0x1b4020 mode 0: the locomotion blend, playback rate, acceleration
     clamp, layer weights, idle restart and footstep event mask; modes 1-6 (sentinels).
  R  Player_animStep 0x1b9520: the speed handed to anim_advance (Drowsy, slow) and the
     root delta turned into world axes; Player_move adding root x 60 to the move.
  H  Player_processDamage 0x1b2cc0: which clip a hit, knock-down, flinch or death starts,
     with flags, blend times, the fade of an older top track and the call sites.
  M  Player_run 0x1a5030: a melee swing timeline (start, hit frame, combo window,
     move mode, swing end) and the block entry/exit gates, one tick at a time.

Stubs (disclosed): everything not listed as followed is a recording stub that returns 0
unless the part names another answer.  Followed: the C library and software float range
0x3a5000-0x3c0000, math_cos16/sin16/atan2_16, angle_approach, net_isSlotActive and
GameObject_rand.  Animation clips are sentinel pointers; anim_advance, anim_start,
anim_startBlendInOut, res_find and Player_hasAnim are stubs.  A pass is evidence about
these functions on this state, not about loaded clips or a rendered game.
"""
import argparse
import hashlib
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_tests as ET                          # noqa: E402
import ref_core as C                           # noqa: E402
import ref_player_anim_states as M             # noqa: E402
from ee_emu import EE, M32, float_to_raw, raw_to_float     # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'

PLAYER_MOVE, PLAYER_ANIM_STEP, ANIM_ADVANCE = 0x1B4020, 0x1B9520, 0x16D748
PROCESS_DAMAGE, PLAYER_RUN = 0x1B2CC0, 0x1A5030
ANIM_BLEND, ANIM_START, RES_FIND, HAS_ANIM = 0x16CEB0, 0x16CFE0, 0x17365C, 0x1BF230
MELEE_HIT, PICK_ATTACK, CAN_BLOCK = 0x1B6A98, 0x1BBA88, 0x1BEE48
KNOCK_CHANCE, KNOCK_REACTION = 0x30851C, 0x308578
DROWSY_TYPE, FIND_SPELL, DROWSY_FRACTION = 0x3D1234, 0x11A710, 0x30EF08
COS16, SIN16, ATAN2_16, ANGLE_APPROACH = 0x166630, 0x1666E0, 0x166798, 0x166C18
NET_IS_SLOT_ACTIVE, OBJ_RAND = 0x13DD40, 0x1509D0
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
PRINTF_CORE = {0x3C0170}          # called by libc_sprintf 0x3b7ef0, just above the range
G_PLAYERS, STRIDE = 0x4D8AF0, 0x4C30
G_SEED, G_FRAME, G_PVP_A, G_KILL_PLANE = 0x404464, 0x44FDCC, 0x4F711C, 0x4F7188
G_BTN_ATTACK, G_BTN_BLOCK = 0x41B980, 0x41B9D0
G_PADS, PAD_SIZE = 0x41BFD8, 0x58
SEED_INC, SEED_STEP = 0x3C6EF35F, 0x0019660D
VTABLE_STUBS = 0x00E30000
ATTACK, BLOCK = 0x4000, 0x8000
SENT = 0x7F7F0001

COUNTS = {}
FAILS = []


def check(part, label, ok, detail=''):
    COUNTS[part] = COUNTS.get(part, 0) + 1
    if not ok:
        FAILS.append((part, label, detail))
        if len(FAILS) <= 12:
            print('FAIL %s %s %s' % (part, label, str(detail)[:600]))


class Follow:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or LIB_LO <= target < LIB_HI or target in PRINTF_CORE


def fbits(value):
    return float_to_raw(value)


def seed_for_high(high):
    return (((high << 16) - SEED_INC) * pow(SEED_STEP, -1, 1 << 32)) & M32


# ---------------------------------------------------------------------------------------
# L. Player_move mode 0, the locomotion blend
# ---------------------------------------------------------------------------------------
CELL = {'walk': (0x144, 0x14C), 'run1': (0x164, 0x16C), 'run2': (0x184, 0x18C)}
LOCO_FIELDS = (0x46C, 0x144, 0x14C, 0x164, 0x16C, 0x184, 0x18C)


MOVE_FOLLOW = Follow({COS16, SIN16, ATAN2_16, ANGLE_APPROACH, ET.NET_GET_CAM_YAW, ET.DIALOG_IS_OPEN,
                      ET.IS_LOCAL_SLOT, ET.NET_GET_CAM_FLAG})


def move_call(rig, mode, lx, ly, vec=0):
    """Player_move(P, mode, pad, vec) with MOVE_FOLLOW (the C library range included, so
    the software double helpers' inner routines run too)."""
    rig.mem.wf32(rig.pad + 0x14, lx)
    rig.mem.wf32(rig.pad + 0x18, ly)
    rig.emu.follow = MOVE_FOLLOW
    rig.emu.reset_log()
    return rig.emu.call(PLAYER_MOVE, rig.player, mode, rig.pad, vec) & M32


def loco_rig(elf, network):
    rig = ET.MoveRig(elf, network=network)
    planted = {'bits': 0}

    def step(emu):
        return planted['bits']
    rig.emu.stub(PLAYER_ANIM_STEP, function=step, name='Player_animStep')
    return rig, planted


def magnitudes(rng):
    """A stick script: rest, ramp up, hold, jumps, ramp down, rest."""
    seq = [0.0] * 3
    seq += [i / 12.0 for i in range(1, 13)]
    seq += [1.0] * 4
    seq += [rng.choice((0.2, 0.43, 0.5, 0.6, 0.7, 0.75, 0.9, 1.0, 0.05, 0.0))
            for _ in range(24)]
    seq += [1.0 - i / 10.0 for i in range(11)]
    seq += [0.0] * 6
    return seq


def part_locomotion(elf, rng):
    for network in (False, True):
        rig, planted = loco_rig(elf, network)
        mem, P = rig.mem, rig.player
        scale = M.speed_scale(network)
        blend = previous = 0
        mem.w32(P + 0x46C, 0)
        mem.w32(P + 0x468, 0)
        for magnitude in magnitudes(rng):
            angle = rng.uniform(-3.14159, 3.14159)
            lx = fbits(magnitude * __import__('math').cos(angle))
            ly = fbits(magnitude * __import__('math').sin(angle))
            planted['bits'] = rng.choice((0, 1, 4, 5, 0x85, 0xFF, 0x104))
            for off in LOCO_FIELDS[1:]:
                mem.w32(P + off, SENT)
            mem.w32(P + 0x134, 0x12345678)
            emu = rig.emu
            ret = move_call(rig, 0, raw_to_float(lx), raw_to_float(ly))
            s = M.stick_magnitude(scale, lx, ly)
            want = M.locomotion_step(blend, previous, s, planted['bits'])
            steps = [c for c in emu.calls if c.target == PLAYER_ANIM_STEP]
            got = {'rate': steps[0].fargs[0] & M32 if len(steps) == 1 else None,
                   'blend': mem.u32(P + 0x46C), 'previous': mem.u32(P + 0x468),
                   'reset_idle': mem.u32(P + 0x134) == 0, 'event': ret}
            for name, (a, b) in CELL.items():
                got[name] = mem.u32(P + a) if mem.u32(P + a) == mem.u32(P + b) else ('split', mem.u32(P + a),
                                                                                    mem.u32(P + b))
            clip_starts = [c for c in emu.calls if c.target in (ANIM_BLEND, ANIM_START)]
            ok = (all(got[k] == want[k] for k in got) and steps[0].args[0] & M32 == P
                  and not clip_starts)
            check('L', 'mode0 net=%d s=%08x' % (network, s), ok, (got, want))
            blend, previous = want['blend'], want['previous']
        # Modes 1, 4, 6 clear the blend and the six layer fields; 2, 3 leave them.
        for mode in (1, 2, 3, 4, 6):
            rig, planted = loco_rig(elf, network)
            mem, P = rig.mem, rig.player
            for off in LOCO_FIELDS:
                mem.w32(P + off, SENT)
            move_call(rig, mode, 0.0, -1.0)
            values = [mem.u32(P + off) for off in LOCO_FIELDS]
            want = [0] * 7 if mode in (1, 4, 6) else [SENT] * 7
            steps = [c for c in rig.emu.calls if c.target == PLAYER_ANIM_STEP]
            check('L', 'mode%d net=%d' % (mode, network), values == want and not steps, values)
        # Mode 5 (with a vector) also leaves them.
        rig, planted = loco_rig(elf, network)
        mem, P = rig.mem, rig.player
        for off in LOCO_FIELDS:
            mem.w32(P + off, SENT)
        vec = rig.emu.alloc(16)
        move_call(rig, 5, 0.0, -1.0, vec)
        check('L', 'mode5 net=%d' % network, [mem.u32(P + off) for off in LOCO_FIELDS] == [SENT] * 7)


# ---------------------------------------------------------------------------------------
# R. Root motion
# ---------------------------------------------------------------------------------------
def anim_step_case(elf, facing, speed, slow, flags, rx, ry, bits, drowsy=None):
    emu = EE(elf)
    mem = emu.mem
    P = emu.alloc(0x600)
    mem.w16(P + 0x38, facing & 0xFFFF)
    mem.w8(P + 0x2FC, slow)
    mem.w32(P + 0x0C, flags)
    mem.w32(P + 0xBC, SENT)
    mem.w32(P + 0xC0, SENT)
    seen = {}

    def advance(e):
        seen['f12'] = e.f[12] & M32
        seen['args'] = tuple(x & M32 for x in e.r[4:8])
        e.mem.w32(e.r[6] & M32, rx)
        e.mem.w32((e.r[6] + 4) & M32, ry)
        return bits
    emu.stub(ANIM_ADVANCE, function=advance, name='anim_advance')
    if drowsy is not None:
        mem.w16(P + 0x31A, 30)
        spell = emu.alloc(0x40)
        emu.stub(FIND_SPELL, ret=spell, name='creature_findSpellByType')

        def fraction(e):
            e.f[0] = drowsy
        emu.stub(DROWSY_FRACTION, function=fraction, name='SpellDrowsy_fraction')
    emu.follow = {COS16, SIN16}
    emu.reset_log()
    ret = emu.call(PLAYER_ANIM_STEP, P, fargs=(raw_to_float(speed),)) & M32
    want_speed = M.anim_step_speed(speed, slow, drowsy)
    want_root = M.root_to_world(C.s16(facing), rx, ry)
    sound = 0 if flags & 0x200000 else P + 0x10
    ok = (seen.get('f12') == want_speed and seen.get('args') == (P + 0x114, sound, P + 0xBC, 0)
          and (mem.u32(P + 0xBC), mem.u32(P + 0xC0)) == want_root and ret == bits)
    return ok, (seen, want_speed, (mem.u32(P + 0xBC), mem.u32(P + 0xC0)), want_root)


def part_root(elf, rng):
    slows = (0, 1, 30, 59, 60, 61, 0xFF)
    for slow in slows:
        for flags in (0x60, 0x200060):
            facing = rng.randrange(-0x8000, 0x8000)
            rx, ry = fbits(rng.uniform(-3, 3)), fbits(rng.uniform(-3, 3))
            speed = rng.choice((C.ONE, 0x40000000, fbits(1.25), fbits(0.7)))
            ok, detail = anim_step_case(elf, facing, speed, slow, flags, rx, ry, rng.randrange(256))
            check('R', 'animStep slow=%d flags=%x' % (slow, flags), ok, detail)
    for _ in range(8):
        facing = rng.randrange(-0x8000, 0x8000)
        ok, detail = anim_step_case(elf, facing, C.ONE, 0, 0x60, fbits(rng.uniform(-3, 3)),
                                    fbits(rng.uniform(-3, 3)), 0, drowsy=fbits(0.5))
        check('R', 'animStep drowsy', ok, detail)
    # Player_move: W = V + root x 60, then root is cleared.
    for network in (False, True):
        rig, planted = loco_rig(elf, network)
        mem, P = rig.mem, rig.player
        rx, ry = fbits(rng.uniform(-2, 2)), fbits(rng.uniform(-2, 2))
        mem.w32(P + 0xBC, rx)
        mem.w32(P + 0xC0, ry)
        move_call(rig, 0, 0.3, -0.8)
        vx, vy = mem.u32(P + 0x4BC), mem.u32(P + 0x4C0)
        want = (C.add(vx, C.mul(rx, M.F_60)), C.add(vy, C.mul(ry, M.F_60)))
        moved = rig.moved[-1] if rig.moved else None
        check('R', 'move adds root x 60 net=%d' % network,
              moved is not None and moved[:2] == want and mem.u32(P + 0xBC) == 0 and mem.u32(P + 0xC0) == 0,
              (moved, want))


# ---------------------------------------------------------------------------------------
# H. Player_processDamage clip choice
# ---------------------------------------------------------------------------------------
RELS = (-0x8000, -0x6000, -0x5FFF, -0x2001, -0x2000, -0x1FFF, 0, 0x2000, 0x2001, 0x5FFF, 0x6000, 0x7FFF)
RESIST_HIGH, FALL_HIGH, CHANCE, RANK = 100 * 300 + 39, 100 * 300 + 40, 40, 7


def damage_rig(elf, seed, cls=0, model=0, bits=0, high=None, pending=0x42200000, facing=0,
               rel=0, flag_word_extra=0, has_anim=0, tracks=0, top_weight=None, resist=C.ONE):
    emu = EE(elf)
    mem = emu.mem
    mem.w32(G_FRAME, 1000)
    mem.w32(G_SEED, seed_for_high(high) if high is not None else seed & M32)
    P = emu.alloc(0x600)
    table = emu.alloc(0x400)
    vtab = emu.alloc(0x200)
    lump = 0x2BAD0000
    mem.w32(table, lump)
    for c in range(8):
        mem.w32(table + M.reaction_offset(c), 0x31000000 | c << 8 | M.REACTION_ROW)
    mem.w32(table + 0x0C, 0x32000000 | 0x0C)
    mem.w32(table + 0x14, 0x32000000 | 0x14)
    mem.w32(P + 0x0C, 0x60)
    mem.w32(P + 0x24, table)
    mem.w32(P + 0x48, vtab)
    mem.w32(vtab + 0x138 + 4, 0x00E20100)
    emu.stub(0x00E20100, ret=RANK, name='rank')
    emu.stub(KNOCK_CHANCE, ret=CHANCE, name='knock_chance')
    emu.stub(HAS_ANIM, ret=has_anim, name='Player_hasAnim')
    emu.stub(RES_FIND, ret=0x33000000, name='res_find')
    R = G_PLAYERS
    mem.w32(P + 0x3C8, 0)
    mem.w32(P + 0x58C, 2)
    mem.w32(R + 0x43D8, P)
    mem.wf32(R + 0xAC, 100.0)
    mem.wf32(R + 0xB0, 100.0)
    mem.w32(R + 0x54, model)
    mem.w8(R + 0x4A86, cls)
    mem.w32(R + 0xDC, resist)
    mem.w16(R + 0x4B08, 0xFFFF)
    mem.w32(P + 0xC8, pending)
    mem.w32(P + 0x2DC, bits | flag_word_extra)
    mem.w16(P + 0x38, facing & 0xFFFF)
    mem.w16(P + 0x2E0, (facing + rel) & 0xFFFF)
    mem.w8(P + 0x118, tracks)
    if top_weight is not None:
        top = P + 0x11C + (tracks - 1) * 0x20
        mem.w32(top + 0x10, top_weight)
        mem.w32(top + 0x14, SENT)
    emu.follow = Follow(set())
    emu.reset_log()
    emu.call(PROCESS_DAMAGE, P)
    return emu, P, table


def anim_calls(emu):
    out = []
    for c in emu.calls:
        if c.target in (ANIM_BLEND, ANIM_START):
            out.append((c.target, c.site, c.args[0] & M32, c.args[1] & M32, c.args[2] & M32,
                        c.fargs[0] & M32, c.fargs[1] & M32 if c.target == ANIM_BLEND else None))
    return out


def part_hits(elf, rng, seed):
    classes = list(range(8))
    rng.shuffle(classes)
    for cls in classes:
        for rel in RELS:
            facing = rng.randrange(-0x8000, 0x8000)
            model = rng.randrange(12)
            emu, P, table = damage_rig(elf, seed, cls, model, bits=0x80000, high=FALL_HIGH,
                                       facing=facing, rel=rel)
            finds = [(c.args[0] & M32, emu.mem.cstr(c.args[1] & M32)) for c in emu.calls if c.target == RES_FIND]
            name = M.knockdown_name(cls, rel)
            want_anim = [(ANIM_BLEND, 0x1B30BC, P + 0x114, 0x33000000, M.FLAGS_KNOCKDOWN, M.BLEND_HIT, M.BLEND_HIT)]
            ok = (finds == [(0x2BAD0000, name)] and anim_calls(emu) == want_anim
                  and emu.mem.u32(P + 0x58C) == 3)
            check('H', 'knockdown cls=%d rel=%d' % (cls, rel), ok, (finds, anim_calls(emu), name))
            # Resisted: the same name goes to the skill-0x3e reaction; no clip starts.
            emu, P, table = damage_rig(elf, seed, cls, model, bits=0x80000, high=RESIST_HIGH,
                                       facing=facing, rel=rel)
            reaction = [(emu.mem.cstr(c.args[2] & M32), c.args[3] & M32) for c in emu.calls
                        if c.target == KNOCK_REACTION]
            check('H', 'resisted cls=%d rel=%d' % (cls, rel),
                  reaction == [(name, 150)] and not anim_calls(emu)
                  and not [c for c in emu.calls if c.target == RES_FIND] and emu.mem.u32(P + 0x58C) == 2,
                  (reaction, anim_calls(emu)))
        # Light knock: the class row's reaction clip.
        emu, P, table = damage_rig(elf, seed, cls, bits=0x40000, high=RESIST_HIGH)
        want = [(ANIM_BLEND, 0x1B317C, P + 0x114, emu.mem.u32(table + M.reaction_offset(cls)),
                 M.FLAGS_REACTION, M.BLEND_HIT, M.BLEND_HIT)]
        check('H', 'light cls=%d' % cls, anim_calls(emu) == want and emu.mem.u32(P + 0x58C) == 3,
              anim_calls(emu))
        # Surviving-hit flinch (no knock bit, roll below the limit, resistance 0).
        emu, P, table = damage_rig(elf, seed, cls, high=0, resist=0)
        want = [(ANIM_BLEND, 0x1B38D0, P + 0x114, emu.mem.u32(table + M.reaction_offset(cls)),
                 M.FLAGS_REACTION, M.BLEND_HIT, M.BLEND_HIT)]
        check('H', 'flinch cls=%d' % cls, anim_calls(emu) == want and emu.mem.u32(P + 0x58C) == 3,
              anim_calls(emu))
        # Death clip from the definition header.
        for model in range(12):
            emu, P, table = damage_rig(elf, seed, cls, model, pending=0x43FA0000)
            off = M.death_offset(model, cls)
            got = anim_calls(emu)
            ok = (len(got) == 1 and got[0][0] == ANIM_START and got[0][2:6] ==
                  (P + 0x114, emu.mem.u32(table + off), M.FLAGS_DEATH, M.BLEND_DEATH)
                  and got[0][1] in (0x1B34C0, 0x1B34E0) and emu.mem.u32(P + 0x58C) == 4)
            check('H', 'death model=%d cls=%d' % (model, cls), ok, got)
    # Guards: light hit with flag 0x400000 starts nothing; an already playing knock-down
    # name is not restarted; 5+ tracks fade the old top track.
    emu, P, table = damage_rig(elf, seed, 0, bits=0x40000, high=RESIST_HIGH, flag_word_extra=0x400000)
    check('H', 'light 0x400000', not anim_calls(emu) and emu.mem.u32(P + 0x58C) == 3, anim_calls(emu))
    emu, P, table = damage_rig(elf, seed, 1, bits=0x80000, high=FALL_HIGH, has_anim=1)
    check('H', 'knockdown already playing', not anim_calls(emu)
          and not [c for c in emu.calls if c.target == RES_FIND] and emu.mem.u32(P + 0x58C) == 3)
    for bits, high in ((0x80000, FALL_HIGH), (0x40000, RESIST_HIGH)):
        for tracks, weight, want_weight in ((5, fbits(2.0), C.ONE), (6, fbits(0.5), fbits(0.5)),
                                            (4, fbits(2.0), fbits(2.0))):
            emu, P, table = damage_rig(elf, seed, 0, bits=bits, high=high, tracks=tracks, top_weight=weight)
            top = P + 0x11C + (tracks - 1) * 0x20
            want_rate = M.FADE_RATE if tracks >= 5 else SENT
            check('H', 'fade tracks=%d bits=%x' % (tracks, bits),
                  emu.mem.u32(top + 0x14) == want_rate and emu.mem.u32(top + 0x10) == want_weight
                  and len(anim_calls(emu)) == 1,
                  (hex(emu.mem.u32(top + 0x14)), hex(emu.mem.u32(top + 0x10))))


# ---------------------------------------------------------------------------------------
# M. Player_run: melee timeline and block gates
# ---------------------------------------------------------------------------------------
class RunRig:
    FOLLOW = {COS16, SIN16, ATAN2_16, ANGLE_APPROACH, NET_IS_SLOT_ACTIVE, OBJ_RAND}

    def __init__(self, elf, network, cls, can_block=1, status2=0):
        world = ET.World(elf, players=1, local_slot=0, network=network)
        self.emu, self.mem = world.emu, world.emu.mem
        emu, mem = self.emu, self.mem
        self.P = P = world.objects[0]
        self.R = R = G_PLAYERS
        self.frame = 5000
        mem.w32(G_FRAME, self.frame)
        mem.wf32(G_KILL_PLANE, -100000.0)
        camera = emu.alloc(0x400)
        mem.w32(camera + 0x34, 1)
        mem.w32(ET.G_LOCAL_CAMERA, camera)
        mem.w16(R + 0x4B08, 0xFFFF)
        mem.w8(R + 0x4A86, cls)
        mem.w32(R + 0x50, 1)
        mem.w32(G_BTN_ATTACK, ATTACK)
        mem.w32(G_BTN_BLOCK, BLOCK)
        self.table = table = emu.alloc(0x400)
        for c in range(8):
            for k in range(0x44, 0xAC, 8):
                mem.w32(table + c * 0x68 + k, 0x34000000 | c << 8 | k)
        mem.w32(P + 0x24, table)
        vtab = emu.alloc(0x400)
        for slot in range(0x80):
            mem.w32(vtab + slot * 8 + 4, VTABLE_STUBS + slot * 8)
        mem.w32(P + 0x48, vtab)
        mem.w32(P + 0x374, status2)
        self.target = target = emu.alloc(0x600)
        mem.w32(target + 0x0C, 0x20)
        mem.wf32(target + 0x10, 130.0)
        mem.wf32(target + 0x14, 200.0)
        node = emu.alloc(0x20)
        mem.w32(node + 0x0C, target)
        mem.w32(P + 0x234, node)
        mem.w8(P + 0x118, 4)
        emu.stub(CAN_BLOCK, ret=can_block, name='player_canBlock')
        self.pad = G_PADS

    def tick(self, held=0, pressed=0, stick=(0.0, 0.0)):
        emu, mem = self.emu, self.mem
        self.frame += 1
        mem.w32(G_FRAME, self.frame)
        mem.w32(self.pad + 0x08, held)
        mem.w32(self.pad + 0x0C, pressed)
        mem.wf32(self.pad + 0x14, stick[0])
        mem.wf32(self.pad + 0x18, stick[1])
        emu.follow = Follow(self.FOLLOW)
        emu.reset_log()
        emu.call(PLAYER_RUN, self.P, max_steps=400000)
        calls = emu.calls
        return {
            'state': mem.u32(self.P + 0x58C),
            'start': mem.u32(self.P + 0x448),
            'hits': [(c.args[1] & M32, c.args[2] & M32) for c in calls if c.target == MELEE_HIT],
            'anims': [(c.target, c.site, c.args[1] & M32, c.args[2] & M32) for c in calls
                      if c.target in (ANIM_BLEND, ANIM_START)],
            'moves': [c.args[1] & M32 for c in calls if c.target == PLAYER_MOVE],
            'picks': [c for c in calls if c.target == PICK_ATTACK],
        }


def swing(elf, network, cls, press_at=None, stick_from=None, status2=0, ticks=110):
    """Press attack in state 2, then optionally once more at elapsed `press_at`, or hold
    the stick from elapsed `stick_from`.  Returns per-tick logs keyed by elapsed frame."""
    rig = RunRig(elf, network, cls, status2=status2)
    first = rig.tick(held=ATTACK, pressed=ATTACK)
    start = rig.frame
    logs = {}
    for _ in range(ticks):
        elapsed = rig.frame + 1 - start
        pressed = ATTACK if press_at == elapsed else 0
        stick = (0.0, -1.0) if stick_from is not None and elapsed >= stick_from else (0.0, 0.0)
        logs[elapsed] = rig.tick(held=pressed, pressed=pressed, stick=stick)
        if logs[elapsed]['state'] != 1:
            break
    return rig, first, start, logs


def part_melee(elf, rng):
    classes = [0, 1, 3, 5, 7]
    rng.shuffle(classes)
    for network in (False, True):
        for cls in classes:
            for status2 in (0, 1):
                speed, haste = M.swing_speed(status2=bool(status2))
                rig, first, start, logs = swing(elf, network, cls, status2=status2)
                P = rig.P
                clip = rig.mem.u32(rig.table + cls * 0x68 + 0x74)
                check('M', 'start cls=%d net=%d' % (cls, network),
                      first['state'] == 1 and first['start'] == start
                      and first['anims'] == [(ANIM_BLEND, 0x1A7F7C, clip, 0x802)], first)
                hit = M.hit_frame(speed, network)
                hits = [e for e, log in logs.items() if log['hits']]
                check('M', 'hit frame cls=%d net=%d haste=%d' % (cls, network, status2),
                      hits == [hit] and logs[hit]['hits'] == [(rig.target, 0 if network else 1)],
                      (hits, hit))
                end = max(logs)
                check('M', 'swing end cls=%d net=%d' % (cls, network),
                      end == M.swing_end_frame() and logs[end]['state'] == 2
                      and logs[end]['start'] == start + end, (end, logs[end]['state']))
                modes_ok = all(log['moves'] == [M.move_mode(e)] for e, log in logs.items())
                check('M', 'move modes cls=%d net=%d' % (cls, network), modes_ok,
                      [(e, log['moves']) for e, log in logs.items()][:30])
                # Combo window: a press one frame early does nothing; on the frame it starts.
                window = M.first_combo_frame(cls, haste, speed)
                for at, starts in ((window - 1, False), (window, True)):
                    rig, first, start, logs = swing(elf, network, cls, press_at=at, status2=status2,
                                                    ticks=at + 1)
                    log = logs[at]
                    combo = (log['start'] == start + at and len(log['picks']) == 1
                             and [(a[0], a[1], a[3]) for a in log['anims']] == [(ANIM_START, 0x1AAE5C, 0x802)]
                             and log['state'] == 1)
                    nothing = log['start'] == start and not log['picks'] and not log['anims']
                    check('M', 'combo cls=%d net=%d haste=%d at=%d' % (cls, network, status2, at),
                          combo if starts else nothing, log)
            # Stick over 0.8 ends the swing once 39.3 frames have passed.
            rig, first, start, logs = swing(elf, network, cls, stick_from=30)
            end = max(logs)
            check('M', 'stick end cls=%d net=%d' % (cls, network),
                  end == M.stick_end_frame() and logs[end]['state'] == 2, end)
    # Net game: a block in the last 16 ticks suppresses the frame-1 hit.
    rig = RunRig(elf, True, 0)
    rig.mem.w32(rig.P + 0x55C, 16)
    rig.tick(held=ATTACK, pressed=ATTACK)
    log = rig.tick()
    check('M', 'net hit suppressed after block', not log['hits'] and rig.mem.u32(rig.P + 0x55C) == 15)
    # Block: held block in neutral enters 8; state 8 starts the block clips and arms +0x55c;
    # release returns to 2 only once the top track's +8 value reaches 1.0.
    for network in (False, True):
        rig = RunRig(elf, network, 0)
        log = rig.tick(held=BLOCK)
        check('M', 'block entry net=%d' % network, log['state'] == 8, log)
        log = rig.tick(held=BLOCK)
        idle = rig.mem.u32(rig.table + 0x9C)
        raise_ = rig.mem.u32(rig.table + 0x84)
        flags = sorted((a[2], a[3]) for a in log['anims'])
        check('M', 'block clips net=%d' % network,
              flags == sorted([(idle, 0x2801), (raise_, 0x803)]) and log['moves'] == [1]
              and rig.mem.u32(rig.P + 0x55C) == 16 and log['state'] == 8, log)
        top = rig.P + 0x11C + 3 * 0x20 + 8
        rig.mem.w32(top, fbits(0.5))
        log = rig.tick()
        check('M', 'block release gated net=%d' % network, log['state'] == 8, log['state'])
        rig.mem.w32(top, C.ONE)
        log = rig.tick()
        check('M', 'block release net=%d' % network, log['state'] == 2, log['state'])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--parts', default='LRHM')
    args = parser.parse_args()
    with open(args.elf, 'rb') as fh:
        if hashlib.sha256(fh.read()).hexdigest() != EXPECTED_SHA256:
            parser.error('requires SLUS_209.73 US v2.00 (SHA-256 mismatch)')
    C.set_fpu('ps2')
    rng = random.Random(args.seed)
    parts = {'L': lambda: part_locomotion(args.elf, rng), 'R': lambda: part_root(args.elf, rng),
             'H': lambda: part_hits(args.elf, rng, args.seed), 'M': lambda: part_melee(args.elf, rng)}
    names = {'L': 'locomotion blend', 'R': 'root motion', 'H': 'hit/knockdown/death clips',
             'M': 'melee timeline and block gates'}
    for key in args.parts:
        parts[key]()
        failed = sum(1 for f in FAILS if f[0] == key)
        print('%s %s seed=%d cases=%d mismatches=%d' % ('PASS' if not failed else 'FAIL', names[key],
                                                        args.seed, COUNTS.get(key, 0), failed))
        sys.stdout.flush()
    return 1 if FAILS else 0


if __name__ == '__main__':
    raise SystemExit(main())
