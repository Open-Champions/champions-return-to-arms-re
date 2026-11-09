#!/usr/bin/env python3
"""Round 6: hit direction, stagger, kill credit, the creature death path and the real
cast bodies of spell IDs 16, 23, 49 and 55 inside Player_castSkill.

Run with unittest already imported and PYTHONDONTWRITEBYTECODE=1. Both seeds run in
this one process. Every case runs original code in tools/ee_emu.py. Callees that are
not followed are stubs; each stub is named next to the case that uses it. Counts only
are written; no instruction text or executable bytes are emitted.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import unittest  # noqa: F401 - preload before tools/ is on the path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import difftest_combat as DC
import difftest_spell_numeric_r3 as N
import ee_emu
import ref_combat as R
import ref_core as C
import ref_player as RP
import ref_skills_a as SA

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (20973, 7)
M32 = 0xFFFFFFFF

# Original functions run here.
PLAYER_TAKE = 0x1B5330          # Player_takeDamage, player slot 2
PLAYER_PROCESS = 0x1B2CC0       # Player_processDamage
CREATURE_TAKE = 0x116638        # Creature_takeDamage, creature slot 2
CREATURE_PROCESS = 0x110D30     # Creature_processDamage
APPLY_KNOCK = 0x115EB8          # Creature_applyKnockback
DEAD_UPDATE = 0x1108A0          # Creature_deadUpdate
CREATURE_RUN = 0x112948         # Creature_run
HORSEMEN_SET_STATE = 0x272F4C   # a class slot 27 (docs/issues/kill-loot-xp.md section 2)
SET_STATE = 0x3C2688            # base slot 27 body: store the state at +0x232
CAST_HELPER = 0x1A42B8          # Player_castSkill
ATAN2 = 0x166798                # math_atan2_16
COS16, SIN16 = 0x166630, 0x1666E0
HANDLE_CLEAR, HANDLE_LINK = 0x1A1698, 0x1A1738
POWF = 0x3A5AC8
GET_RANK = 0x1BF330             # player_getSkillRank
STRCMP, IS_LOCAL = 0x3B8534, 0x13E150
CASTS = {16: 0x2ECFCC, 23: 0x2F8840, 49: 0x2DE3BC, 55: 0x2E8CF8}

# Callees that are stubs and recorded.
GIVE_EXP = 0x1D3150             # player_giveExp
LIFETAP_FRACTION = 0x2F8E78     # the stub sets f0 to the case's fraction
OWN_DRAW = 0x1509D0             # GameObject_rand: the stub returns the case's draw
POOL_NEW = 0x14FDB8
ONIBALL = 0x294014
PROP_INT = 0x14C880             # obj_getPropInt
SNAP_TOP = 0x170C80             # anim_snapTopToEnd
DROP_LOOT = 0x10F2C8            # Creature_dropLoot
OBJ_DELETE = 0x14F200
MOVE_BY = 0x113C48
STAGGER_FEEDBACK = 0x1B7BA8     # (slot, 0xc) after a stagger; also (slot, 3) on a player kill
KNOCK_CHANCE = 0x30851C         # SkillStrongStance_getStat0, followed with its two slots
SKILL_SLOT10, SKILL_SLOT14 = 0x3C88DC, 0x3C85FC
KNOCK_RESIST = 0x308578         # SkillStrongStance_trigger, followed with every callee
LIGHT_CTOR = 0x201BD8           # LightEffect_ctor (inside the trigger)
PHANTOM_CTOR = 0x1618D4         # StrongStancePhantom_ctor (inside the trigger)
GAMEOBJECT_CTOR = 0x14CB10      # GameObject_ctor: the shared draw of a new object
SAMPLE_COUNT = 0x1799C8         # model_getSamplePointCount: stub, 8 points
SAMPLE_POINT = 0x178E18         # model_getSamplePoint: stub, writes (0, 0, 0)
RES_FIND = 0x17365C             # res_find: stub, returns 0 (no clip for the phantom)
SPRINTF = 0x3B7EF0              # sprintf: stand-in with real_reaction (see real_reaction)
STATIC_INIT, STAT_SETUP = 0x16AC74, 0x1EBCA0   # the executable's skill start-up
ATTACH_SPELL = 0x11A838

RANK_STUB = 0x00E20100          # stands in for player virtual slot 39 (skill rank)
ONDEATH_STUB = 0x00E20110       # stands in for creature virtual slot 28

G_PLAYERS, STRIDE, G_NUM = 0x4D8AF0, 0x4C30, 0x4D8AE0
G_FRAME = 0x44FDCC
G_HANDLE_FREE = 0x864EA8        # free list read by handle_link
G_KNOCK_SKILL = 0x41B268        # the skill object handed to 0x30851c
G_LIFETAP_SKILL = 0x41B25C
G_EXP_TABLE = 0x41B558
SEED_INC, SEED_STEP = 0x3C6EF35F, 0x0019660D
K_STAGGER = 0x3D23D70A          # 0.04
K_65536 = 0x47800000
K_SINK = 0x3EB33333             # 0.35
K_AIM = 0x41C2
SENTINEL = 0x3F800000
HP = 0x42C80000                 # 100
PLAIN = 0x42200000              # 40
EXP_VALUE = 0x460CA000          # 9000
MAX_HP = 0x44610000             # 900
RANKS = (1, 5, 20)

# Oracles. tools/mutate_combat_r6.py changes one at a time; each change must fail.
KNOCK_PER_RANK = 5              # skill 0x3e chance = 5 x rank (docs/spec/skills-35-68.md)
KNOCK_MOD = 100                 # resist when (H % 100) < chance
REACTION_DRAWS = 2              # shared draws inside 0x308578: LightEffect, phantom
BLOCK_REL = 0x6000              # processDamage block: |rel| >= 0x6000 lowers one level
DEATH_ORDER = ('loot', 'slot28', 'state', 'flag', 'award')   # with Horsemen_setState
AWARD_SITES = {1: 0x1121E8, 2: 0x1120E4}   # player_giveExp call site by player count
DEAD_FLAG_PC = 0x111E04
DEAD_QUERY_SITE = 0x111E08      # obj_getPropInt(creature, "Dead") call site
HORSEMEN_STATE_PC = 0x2735C4    # Horsemen_setState's own store of 0x14 at +0x232
KNOCK_NAME = re.compile(rb'knockdown[12]_([abcd])\.anm')   # 0x308578 a2 (skills-35-68.md)


def knock_letter(rel):
    """The animation letter of docs/spec/skills-35-68.md (Player_processDamage) for
    rel = hit angle minus facing."""
    rel = ee_emu.sx16(rel & 0xFFFF)
    if rel < -0x5FFF or rel >= 0x6000:
        return b'a'
    if ((rel + 0x6000) & 0xFFFF) <= 0x4000:
        return b'c'
    if ((rel + 0x2000) & 0xFFFF) <= 0x4000:
        return b'b'
    return b'd'


def guest_string(emu, addr, limit=64):
    out = bytearray()
    while len(out) < limit:
        byte = emu.mem.u8(addr + len(out))
        if not byte:
            break
        out.append(byte)
    return bytes(out)


def block_added(state, behind, flags, amount=PLAIN):
    """Player_takeDamage in block state 8 or 0xb: what is added to pending damage."""
    if flags & 0x40 or behind:
        return amount
    return R.fmul(amount, R.HALF) if flags & 0x20000 else 0


def block_lowers(rel):
    """Player_processDamage, state 8: does the hit lose one knock level."""
    rel = ee_emu.sx16(rel & 0xFFFF)
    return rel >= BLOCK_REL or rel <= -BLOCK_REL


class Failure(Exception):
    pass


class Follow:
    """Callees that run for real: the named ones and the C library range."""

    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or DC.LIB_LO <= target < DC.LIB_HI


def seed_for_high(high):
    """The seed state whose next draw has upper half `high` and lower half 0."""
    return (((high << 16) - SEED_INC) * pow(SEED_STEP, -1, 1 << 32)) & M32


def fpat(value):
    return ee_emu.float_to_raw(value)


class Probe:
    def __init__(self, elf):
        self.elf = str(elf)
        self.counts = Counter()
        self.failures = Counter()
        C.set_fpu('ps2')
        self.numeric = None

    def check(self, label, ok):
        self.counts['assertions'] += 1
        if not ok:
            self.failures[label] += 1
            print('FAIL ' + label)

    # ---- guests -------------------------------------------------------------------------
    def guest(self, seed, players=1, skills=False):
        emu = ee_emu.EE(self.elf, fpu_model='ps2')
        if skills:
            # The executable's own start-up: every Skill object and its statistics.
            emu.call(STATIC_INIT, 1, 0xFFFF, max_steps=20000000)
            emu.call(STAT_SETUP, max_steps=20000000)
            emu.reset_log()
        emu.mem.w32(DC.G_SEED, seed & M32)
        emu.mem.w32(G_NUM, players)
        emu.mem.w32(G_FRAME, 1000)
        # Fixture: sixteen zeroed handle nodes on the free list, so handle_link runs.
        nodes = emu.alloc(0x20 * 16)
        for index in range(16):
            emu.mem.w32(nodes + 0x20 * index, nodes + 0x20 * (index + 1) if index < 15 else 0)
        emu.mem.w32(G_HANDLE_FREE, nodes)
        for slot in range(4):
            emu.mem.w16(G_PLAYERS + STRIDE * slot + 0x4B08, 0xFFFF)
        return emu

    def actor(self, emu, flags, x=0.0, y=0.0, hp=HP):
        obj = emu.alloc(0x600)
        table = emu.alloc(0x400)
        emu.mem.w32(obj + 0x0C, flags)
        emu.mem.w32(obj + 0x24, table)
        emu.mem.w32(obj + 0x48, table)
        emu.mem.wf32(obj + 0x10, x)
        emu.mem.wf32(obj + 0x14, y)
        emu.mem.w32(obj + 0x228, hp)
        return obj, table

    def player(self, emu, slot, flags=0x60, x=0.0, y=0.0, hp=HP, level=30, cls=1):
        obj, table = self.actor(emu, flags, x, y)
        record = G_PLAYERS + STRIDE * slot
        emu.mem.w32(obj + 0x3C8, slot)
        emu.mem.w32(obj + 0x58C, 2)
        emu.mem.w32(record + 0x43D8, obj)
        emu.mem.w32(record + 0xAC, hp)
        emu.mem.w32(record + 0xB0, HP)
        emu.mem.w8(record + 0x59, level)
        emu.mem.w32(record + 0x50, cls)
        emu.mem.w32(record + 0xC0, 0x41200000)      # 10
        emu.mem.w32(record + 0xC4, 0x43FA0000)      # 500
        return obj, table

    def node(self, emu, obj):
        """A handle node whose +0xc names obj (the shape takeDamage follows)."""
        node = emu.alloc(0x20)
        emu.mem.w32(node + 0x0C, obj)
        return node

    @staticmethod
    def stored(emu, addr, value=None, pc=None):
        return [index for index, (wpc, wrote, _size, pattern) in enumerate(emu.writes)
                if wrote == addr and (value is None or pattern == value) and (pc is None or wpc == pc)]

    @staticmethod
    def calls(emu, target, site=None):
        return [call for call in emu.calls if call.target == target and (site is None or call.site == site)]

    # ---- A. hit direction ---------------------------------------------------------------
    def direction(self, victim_xy, attacker_xy):
        dx = R.fsub(fpat(victim_xy[0]), fpat(attacker_xy[0]))
        dy = R.fsub(fpat(victim_xy[1]), fpat(attacker_xy[1]))
        return (0x4000 - C.atan2_16(dx, dy)) & 0xFFFF

    def hit_direction(self, seed):
        offsets = ((100.0, 0.0), (0.0, 100.0), (-37.5, 12.25), (5.0, -80.0),
                   (-60.0, -60.0), (250.5, -3.0))
        victim_xy = (10.0, 20.0)
        for dx, dy in offsets:
            attacker_xy = (victim_xy[0] + dx, victim_xy[1] + dy)
            want = self.direction(victim_xy, attacker_xy)
            # Player slot 2. Followed: strcmp, local-slot test, atan2, the handle pair.
            # Stubbed (return 0): holy-shield search 0x3cf124/0x11a710, jump-gate 0x27dd68.
            emu = self.guest(seed)
            obj, _ = self.player(emu, 0, x=victim_xy[0], y=victim_xy[1])
            emu.mem.w16(obj + 0x2E0, 0x1234)
            attacker, _ = self.actor(emu, 0x20, *attacker_xy)
            emu.follow = Follow({STRCMP, IS_LOCAL, ATAN2, HANDLE_CLEAR, HANDLE_LINK})
            emu.reset_log()
            emu.call(PLAYER_TAKE, obj, attacker, 0, fargs=(40.0,))
            self.counts['player_take_calls'] += 1
            self.check('player_direction', emu.mem.u16(obj + 0x2E0) == want
                       and self.stored(emu, obj + 0x2E0, want))
            link = emu.mem.u32(obj + 0x2E4)
            self.check('player_last_attacker', link and emu.mem.u32(link + 0xC) == attacker)
            # Knock-back consumer: Creature_applyKnockback offline on this player.
            self.knock_along(emu, obj, want, victim_xy, attacker_xy, 'player')
            # Creature slot 2. Followed: atan2, the handle pair.
            emu = self.guest(seed)
            obj, _ = self.actor(emu, 0x20, *victim_xy)
            emu.mem.w16(obj + 0x2E0, 0x1234)
            attacker, _ = self.actor(emu, 0x40, *attacker_xy)
            emu.follow = Follow({ATAN2, HANDLE_CLEAR, HANDLE_LINK})
            emu.reset_log()
            emu.call(CREATURE_TAKE, obj, attacker, 0, fargs=(40.0,))
            self.counts['creature_take_calls'] += 1
            self.check('creature_direction', emu.mem.u16(obj + 0x2E0) == want
                       and self.stored(emu, obj + 0x2E0, want))
            self.knock_along(emu, obj, want, victim_xy, attacker_xy, 'creature')
        self.player_block(seed, victim_xy)
        # No attacker, and a flag word with 0x800000: the angle is not written.
        attacker_xy = (victim_xy[0] + 30.0, victim_xy[1])
        for label, attacker_on, flags in (('none', False, 0), ('flag_800000', True, 0x800000)):
            emu = self.guest(seed)
            obj, _ = self.player(emu, 0, x=victim_xy[0], y=victim_xy[1])
            emu.mem.w16(obj + 0x2E0, 0x1234)
            attacker, _ = self.actor(emu, 0x20, *attacker_xy)
            emu.follow = Follow({STRCMP, IS_LOCAL, ATAN2, HANDLE_CLEAR, HANDLE_LINK})
            emu.reset_log()
            emu.call(PLAYER_TAKE, obj, attacker if attacker_on else 0, flags, fargs=(40.0,))
            self.counts['player_take_calls'] += 1
            self.check('player_no_direction_' + label, emu.mem.u16(obj + 0x2E0) == 0x1234
                       and not self.stored(emu, obj + 0x2E0)
                       and not self.calls(emu, ATAN2))
            link = emu.mem.u32(obj + 0x2E4)
            self.check('player_link_' + label, (link and emu.mem.u32(link + 0xC) == attacker)
                       if attacker_on else not self.calls(emu, HANDLE_LINK))
        # A creature already at 0 hit points: no angle and no link.
        emu = self.guest(seed)
        obj, _ = self.actor(emu, 0x20, *victim_xy, hp=0)
        emu.mem.w16(obj + 0x2E0, 0x1234)
        attacker, _ = self.actor(emu, 0x40, *attacker_xy)
        emu.follow = Follow({ATAN2, HANDLE_CLEAR, HANDLE_LINK})
        emu.reset_log()
        emu.call(CREATURE_TAKE, obj, attacker, 0, fargs=(40.0,))
        self.counts['creature_take_calls'] += 1
        self.check('creature_corpse_no_direction', emu.mem.u16(obj + 0x2E0) == 0x1234
                   and not self.calls(emu, ATAN2) and not self.calls(emu, HANDLE_LINK)
                   and emu.mem.u32(obj + 0x228) == R.fsub(0, PLAIN))

    def player_block(self, seed, victim_xy):
        """Player_takeDamage in block state 8 or 0xb. Followed: strcmp, local-slot test,
        atan2, cos16, sin16, the handle pair. Stubbed (return 0): block animation
        0x16ceb0, strcpy 0x3b7ef0, res_find 0x17365c, the sound 0x214428, 0x1b9658,
        holy-shield search. Facing 0, so the front is +x. Pending damage is planted at
        3.0, so an early return (pending kept, no store) cannot pass."""
        pending = 0x40400000                                     # 3.0
        cases = (('front', 8, 30.0, 0), ('front_half', 8, 30.0, 0x20000),
                 ('back', 8, -30.0, 0), ('state_b_front', 0xB, 30.0, 0),
                 ('state_b_back', 0xB, -30.0, 0), ('state_b_front_half', 0xB, 30.0, 0x20000),
                 ('flag_40', 8, 30.0, 0x40))
        for label, state, dx, flags in cases:
            emu = self.guest(seed)
            obj, _ = self.player(emu, 0, x=victim_xy[0], y=victim_xy[1])
            emu.mem.w32(obj + 0x58C, state)
            emu.mem.w16(obj + 0x38, 0)
            emu.mem.w32(obj + 0xC8, pending)
            emu.mem.w16(obj + 0x2E0, 0x1234)
            attacker_xy = (victim_xy[0] + dx, victim_xy[1])
            attacker, _ = self.actor(emu, 0x20, *attacker_xy)
            emu.follow = Follow({STRCMP, IS_LOCAL, ATAN2, COS16, SIN16, HANDLE_CLEAR, HANDLE_LINK})
            before = emu.mem.u32(DC.G_SEED)
            emu.reset_log()
            emu.call(PLAYER_TAKE, obj, attacker, flags, fargs=(40.0,))
            self.counts['player_take_calls'] += 1
            want = R.fadd(pending, block_added(state, dx < 0, flags))
            drew = emu.mem.u32(DC.G_SEED) == self.draws(before, 1)
            kept = emu.mem.u32(DC.G_SEED) == before
            self.check('block_' + label, emu.mem.u32(obj + 0xC8) == want
                       and self.stored(emu, obj + 0xC8, want, pc=0x1B56A4)
                       and (drew if state == 8 and not flags & 0x40 else kept))
            # The hit went on past the block test: angle stored, attacker linked.
            angle = self.direction(victim_xy, attacker_xy)
            link = emu.mem.u32(obj + 0x2E4)
            self.check('block_reached_angle_' + label, self.stored(emu, obj + 0x2E0, angle)
                       and link and emu.mem.u32(link + 0xC) == attacker)

    def knock_along(self, emu, obj, angle, victim_xy, attacker_xy, label):
        """Creature_applyKnockback after the hit. Followed: cos16, sin16. moveBy is a
        stub that keeps the velocity it is handed. Speed 30 planted, scale 1."""
        seen = []

        def move(guest):
            seen.append(tuple(guest.mem.u32(guest.r[5] + 4 * index) for index in range(3)))
            return 3
        emu.mem.w32(obj + 0x2E8, 0x41F00000)
        emu.follow = Follow({COS16, SIN16})
        emu.stub(MOVE_BY, function=move, name='moveBy')
        emu.reset_log()
        emu.call(APPLY_KNOCK, obj, fargs=(1.0,))
        emu.unhook(MOVE_BY)
        self.counts['knockback_calls'] += 1
        speed, scale = 0x41F00000, SENTINEL
        want = (R.fmul(C.mul(C.cos16(angle), speed), scale),
                R.fmul(C.mul(C.sin16(angle), speed), scale), 0)
        self.check(label + '_knock_velocity', seen == [want])
        if seen:
            vx, vy = ee_emu.raw_to_float(seen[0][0]), ee_emu.raw_to_float(seen[0][1])
            away = (vx * (victim_xy[0] - attacker_xy[0]) + vy * (victim_xy[1] - attacker_xy[1]))
            self.check(label + '_knock_away_from_attacker', away > 0)

    # ---- B. stagger -----------------------------------------------------------------------
    def stagger_threshold(self, resist):
        chance = R.fsub(K_STAGGER, R.fmul(resist, K_STAGGER))
        if R.flt(chance, 0):
            chance = 0
        limit = R.fmul(chance, K_65536)
        below = [high for high in range(0x10000) if R.flt(R.itof(high), limit)]
        return (max(below) if below else None), limit

    def resolve(self, seed, high, pending=PLAIN, bits=0, state=2, resist=0, flags=0x60,
                field_44c=0, facing=0, angle=0, rank_stub=None, pvp_a=0, real_reaction=False):
        """Original Player_processDamage. Every callee is a stub returning 0 unless
        named. With rank_stub: slot 39 (skill rank) is a recorded stub, the executable's
        skill start-up has run, and the chance getter 0x30851c runs for real. With
        real_reaction: 0x308578 runs for real with every callee, except four fixture
        stubs (pool_new: a zeroed block; the model's sample-point count 8 and points
        (0, 0, 0), because the planted player has no model; res_find: 0), and
        sprintf is a stand-in that copies its format (see real_reaction)."""
        emu = self.guest(seed, skills=rank_stub is not None)
        obj, table = self.player(emu, 0, flags=flags)
        record = G_PLAYERS
        emu.mem.w32(record + 0xDC, resist)
        emu.mem.w32(obj + 0xC8, pending)
        emu.mem.w32(obj + 0x2DC, bits)
        emu.mem.w32(obj + 0x58C, state)
        emu.mem.w32(obj + 0x44C, field_44c)
        emu.mem.w32(obj + 0x2E8, SENTINEL)
        emu.mem.w16(obj + 0x38, facing)
        emu.mem.w16(obj + 0x2E0, angle)
        emu.mem.w32(obj + 0x448, 0x5A5A)
        emu.mem.w32(SA.G_PVP_MODE_A, pvp_a)
        follow = set()
        if rank_stub is not None:
            emu.mem.w32(table + 0x138 + 4, RANK_STUB)
            emu.stub(RANK_STUB, ret=rank_stub, name='rank')
            follow |= {KNOCK_CHANCE, SKILL_SLOT10, SKILL_SLOT14}
        emu.reaction = {}
        emu.blocks = []
        if real_reaction:
            self.real_reaction(emu)
        planted = seed_for_high(high) if high is not None else seed & M32
        emu.mem.w32(DC.G_SEED, planted)
        emu.follow = Follow(follow)
        emu.reset_log()
        emu.call(PLAYER_PROCESS, obj, max_steps=3000000)
        self.counts['player_process_calls'] += 1
        return emu, obj, planted

    def real_reaction(self, emu):
        info = emu.reaction

        def pool(guest):
            block = guest.alloc(max(guest.r[4] & M32, 16))
            emu.blocks.append((guest.r[4] & M32, block))
            return block

        def point(guest):
            for index in range(3):
                guest.mem.w32((guest.r[9] & M32) + 4 * index, 0)

        def sprintf(guest):
            # Followed as library code, sprintf leaves the buffer empty here (its
            # callee 0x3c0170 is past DC.LIB_HI, so a stub), and the name's prefix
            # (Player_processDamage, call at 0x1b2f54) is lost. The stand-in copies the
            # format; a format with a conversion is copied as it is, and the name
            # check then fails.
            fmt = guest_string(guest, guest.r[5] & M32)
            emu.formats.append(fmt)
            guest.mem.write(guest.r[4] & M32, fmt + b'\0')
            return len(fmt)

        def enter(guest):
            ret = guest.r[31] & M32
            # a2, the animation name, read while the call is live (it is on the stack).
            info.update(seed_in=guest.mem.u32(DC.G_SEED), first=len(guest.calls) - 1,
                        follow=guest.follow, name_ptr=guest.r[6] & M32,
                        name=guest_string(guest, guest.r[6] & M32))
            guest.follow = None

            def leave(back):
                back.follow = info['follow']
                info.update(seed_out=back.mem.u32(DC.G_SEED), last=len(back.calls))
                back.unhook(ret)
            guest.hook(ret, leave)
        emu.stub(POOL_NEW, function=pool, name='pool_new')
        emu.stub(SAMPLE_COUNT, ret=8, name='sample_count')
        emu.stub(SAMPLE_POINT, function=point, name='sample_point')
        emu.stub(RES_FIND, name='res_find')
        emu.formats = []
        emu.stub(SPRINTF, function=sprintf, name='sprintf')
        emu.hook(KNOCK_RESIST, enter)

    def reaction_ok(self, emu, obj, speed, rel=0):
        """0x308578 ran to its return: one LightEffect and one StrongStancePhantom, each
        built by GameObject_ctor with one shared draw, and nothing else on the seed.
        a2 is a knockdown animation name whose letter fits rel, and the phantom gets
        the same pointer."""
        info = emu.reaction
        if 'seed_out' not in info:
            return False
        inner = emu.calls[info['first']:info['last']]
        lights = [call for call in inner if call.target == LIGHT_CTOR]
        ghosts = [call for call in inner if call.target == PHANTOM_CTOR]
        made = [call for call in inner if call.target == GAMEOBJECT_CTOR]
        sizes = [size for size, _block in emu.blocks]
        ok = (info['seed_out'] == self.draws(info['seed_in'], REACTION_DRAWS)
              and len(lights) == 1 and len(ghosts) == 1 and len(made) == 2
              and sizes == [0xBC, 0x3D8]
              and lights[0].args[0] == emu.blocks[0][1]
              and ghosts[0].args[0] == emu.blocks[1][1] and ghosts[0].args[1] == obj
              and ghosts[0].args[3] == speed and ghosts[0].args[4] == 0)
        name = KNOCK_NAME.fullmatch(info.get('name', b''))
        ok = (ok and name is not None and name.group(1) == knock_letter(rel)
              and ghosts[0].args[2] & M32 == info['name_ptr'])
        if ok:
            ghost = emu.blocks[1][1]
            ok = emu.mem.u32(ghost + 0x2E8) == R.fmul(R.itof(speed), 0x3FA00000)   # x 1.25
        return ok

    def staggered(self, emu, obj):
        return (emu.mem.u32(obj + 0x58C) == 3 and emu.mem.u32(obj + 0x448) == 1000
                and len(self.calls(emu, STAGGER_FEEDBACK)) == 1
                and self.calls(emu, STAGGER_FEEDBACK)[0].args[:2] == (0, 0xC))

    def draws(self, planted, count):
        seed = R.Seed(planted)
        for _ in range(count):
            seed.draw()
        return seed.state

    def stagger(self, seed):
        for resist in (0, 0x3E800000, 0x3F000000):              # 0, 0.25, 0.5
            top, limit = self.stagger_threshold(resist)
            self.check('stagger_limit_positive', top is not None)
            emu, obj, planted = self.resolve(seed, top, resist=resist)
            self.check('stagger_at_limit', self.staggered(emu, obj)
                       and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1)
                       and emu.mem.u32(G_PLAYERS + 0xAC) == R.fsub(HP, PLAIN))
            emu, obj, planted = self.resolve(seed, top + 1, resist=resist)
            self.check('no_stagger_above_limit', emu.mem.u32(obj + 0x58C) == 2
                       and not self.calls(emu, STAGGER_FEEDBACK)
                       and emu.mem.u32(obj + 0x448) == 0x5A5A
                       and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1))
            self.counts['stagger_limit_%x' % resist] = top
        for resist in (SENTINEL, 0x3FC00000):                   # 1.0 and 1.5: chance 0
            emu, obj, planted = self.resolve(seed, 0, resist=resist)
            self.check('stagger_resisted_fully', emu.mem.u32(obj + 0x58C) == 2
                       and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1))
        emu, obj, planted = self.resolve(seed, 0xFFFF, bits=0x4000000)
        self.check('stagger_forced', self.staggered(emu, obj)
                   and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1))
        for label, kwargs in (('flag_400000', {'bits': 0x400000}), ('state_3', {'state': 3}),
                              ('state_7', {'state': 7}), ('field_44c', {'field_44c': 2})):
            emu, obj, planted = self.resolve(seed, 0, **kwargs)
            self.check('stagger_no_roll_' + label, emu.mem.u32(DC.G_SEED) == planted
                       and not self.calls(emu, STAGGER_FEEDBACK)
                       and emu.mem.u32(obj + 0x58C) == kwargs.get('state', 2))
        for state in (6, 10):
            emu, obj, planted = self.resolve(seed, 0, state=state)
            self.check('stagger_rolled_kept_state', emu.mem.u32(obj + 0x58C) == state
                       and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1)
                       and not self.calls(emu, STAGGER_FEEDBACK))
        emu, obj, planted = self.resolve(seed, 0, pending=HP)
        self.check('stagger_no_roll_on_kill', emu.mem.u32(obj + 0x58C) == 4
                   and emu.mem.u32(DC.G_SEED) == planted)
        self.knock_down(seed)

    def knock_down(self, seed):
        """Knock bits draw one more number: (high % 100) < chance resists a knock-down.
        Resistance +0xdc is planted at 1.0 so the later stagger roll cannot fire. The
        rank is a stub (8); the chance comes from the real 0x30851c."""
        rank = 8
        chance = KNOCK_PER_RANK * rank
        # 307 is not a multiple of 100, so a wrong modulus moves the residue.
        resist_high = KNOCK_MOD * 307 + chance - 1
        fall_high = KNOCK_MOD * 307 + chance
        self.knock_chance_ladder(seed)
        # A resisted heavy hit: the real reaction for the player, none for the copy.
        for bits, speed, flags in ((0x80000, 150, 0x60), (0x80000, 150, 0x20060),
                                   (0x100000, 200, 0x60), (0x200000, 250, 0x60)):
            emu, obj, planted = self.resolve(seed, resist_high, bits=bits, resist=SENTINEL,
                                             flags=flags, rank_stub=rank, real_reaction=True)
            asked = self.calls(emu, RANK_STUB)
            got = self.calls(emu, KNOCK_CHANCE)
            reaction = self.calls(emu, KNOCK_RESIST)
            self.check('knock_rank_query', len(asked) == 1 and asked[0].args[1] == 0x3E
                       and len(got) == 1 and got[0].args[:2] == (emu.mem.u32(G_KNOCK_SKILL), rank))
            copy = bool(flags & 0x20000)
            # Shared draws: the knock roll, the reaction's two (player only), the
            # surviving-hit roll.
            count = 2 + (0 if copy else REACTION_DRAWS)
            self.counts['knock_resisted_draws_%x_%s' % (bits, 'copy' if copy else 'player')] = \
                self.count_draws(planted, emu.mem.u32(DC.G_SEED))
            self.check('knock_resisted', emu.mem.u32(obj + 0x58C) == 2
                       and emu.mem.u32(obj + 0x2E8) == 0
                       and self.stored(emu, obj + 0x2E8, fpat(float(speed)))
                       and self.stored(emu, obj + 0x2E8, 0)
                       and not self.calls(emu, STAGGER_FEEDBACK)
                       and emu.mem.u32(DC.G_SEED) == self.draws(planted, count))
            if copy:
                self.check('knock_resisted_copy_no_reaction', not reaction and not emu.reaction)
            else:
                self.check('knock_resisted_reaction', len(reaction) == 1
                           and reaction[0].args[0] == emu.mem.u32(G_KNOCK_SKILL)
                           and reaction[0].args[1] == obj and reaction[0].args[3] == speed
                           and self.reaction_ok(emu, obj, speed))
        emu, obj, planted = self.resolve(seed, fall_high, bits=0x80000, resist=SENTINEL,
                                         rank_stub=rank, real_reaction=True)
        self.check('knock_down', self.staggered(emu, obj)
                   and emu.mem.u32(obj + 0x2E8) == 0x43160000
                   and not self.calls(emu, KNOCK_RESIST)
                   and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1))
        emu, obj, planted = self.resolve(seed, resist_high, bits=0x40000, resist=SENTINEL,
                                         rank_stub=rank, real_reaction=True)
        self.check('light_knock_ignores_roll', self.staggered(emu, obj)
                   and emu.mem.u32(obj + 0x2E8) == 0x42C80000
                   and not self.calls(emu, KNOCK_RESIST)
                   and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1))
        # Blocking (state 8): a hit whose angle minus facing is at least 0x6000 away
        # from 0 drops one knock level, so the resisted heavy hit becomes a light one.
        for facing, angle in ((0, 0x5FFF), (0, 0x6000), (0, 0xA001), (0, 0xA000),
                              (0, 0x0000), (0, 0x8000), (0x6000, 0x6000)):
            emu, obj, planted = self.resolve(seed, resist_high, bits=0x80000, resist=SENTINEL,
                                             state=8, facing=facing, angle=angle,
                                             rank_stub=rank, real_reaction=True)
            if block_lowers(angle - facing):
                self.check('block_front_light', self.staggered(emu, obj)
                           and not self.calls(emu, KNOCK_RESIST)
                           and emu.mem.u32(DC.G_SEED) == self.draws(planted, 1))
            else:
                self.check('block_back_resisted', emu.mem.u32(obj + 0x58C) == 8
                           and emu.mem.u32(obj + 0x2E8) == 0
                           and self.reaction_ok(emu, obj, 150, angle - facing)
                           and emu.mem.u32(DC.G_SEED) == self.draws(planted, 2 + REACTION_DRAWS))
        # PvP mode A (0x4f711c): one knock level less and half the speed.
        for bits, speed, state, count in ((0x40000, 0x42480000, 2, 2), (0x80000, 0x42960000, 3, 1)):
            emu, obj, planted = self.resolve(seed, resist_high, bits=bits, resist=SENTINEL,
                                             rank_stub=rank, pvp_a=1, real_reaction=True)
            self.check('pvp_a_knock', emu.mem.u32(obj + 0x2E8) == speed
                       and emu.mem.u32(obj + 0x58C) == state
                       and not self.calls(emu, KNOCK_RESIST)
                       and emu.mem.u32(DC.G_SEED) == self.draws(planted, count))

    def knock_chance_ladder(self, seed):
        """The real 0x30851c after the executable's skill start-up: 5 x rank."""
        emu = self.guest(seed, skills=True)
        skill = emu.mem.u32(G_KNOCK_SKILL)
        emu.follow = Follow({SKILL_SLOT10, SKILL_SLOT14})
        for rank in range(0, 26):
            emu.reset_log()
            got = emu.call(KNOCK_CHANCE, skill, rank, max_steps=200000) & M32
            self.check('knock_chance_rank', got == KNOCK_PER_RANK * rank)
            self.counts['knock_chance_calls'] += 1
            if rank in (1, 10, 20, 25):
                self.counts['knock_chance_rank_%d' % rank] = got

    def count_draws(self, planted, final, limit=16):
        state = R.Seed(planted)
        for count in range(limit + 1):
            if state.state == final:
                return count
            state.draw()
        return -1

    # ---- C. kill credit and D. death path ------------------------------------------------
    def award_oracle(self, emu, levels, alive, killer, value=EXP_VALUE):
        total = sum(levels)
        raw = R.ftoi(R.powf(R.fdiv(value, R.itof(total)), 0x3FB33333))
        xp = R.ftoi(R.fmul(R.itof(raw), 0x3F400000))
        table = [emu.mem.s32(G_EXP_TABLE + 4 * index) for index in range(81)]

        def cap(level):
            return table[level + 1] - table[level] if level < 80 else table[level]
        if len(levels) < 2:
            return [(0, min(xp, cap(levels[0])))] if alive[0] else []
        out = []
        for slot, level in enumerate(levels):
            share = R.HALF if killer == -1 else 0x3F199999 if killer == slot else 0x3ECCCCCC
            amount = R.ftoi(R.fmul(R.itof(xp), share))
            if not alive[slot]:
                amount = R.ftoi(R.fmul(R.itof(amount), R.HALF))
            out.append((slot, min(amount, cap(level))))
        return out

    def kill(self, seed, players, hits, levels=(30,), alive=None, classes=None,
             fraction=0, own_draw=0, rank_list=None, prop=0, cflags=0, set_state=SET_STATE,
             extra_follow=(), facing=0):
        """Original Creature_takeDamage for each hit, then original Creature_processDamage.
        hits: (attacker key, damage flags, amount pattern). Followed: atan2, handle pair,
        powf, player_getSkillRank, the slot-27 body. Stubs: giveExp (recorded),
        0x2f8e78 (sets f0 to `fraction`), GameObject_rand (returns `own_draw`), pool_new
        (a zeroed block), obj_getPropInt (returns `prop`), slot 28 (recorded); every other
        callee returns 0."""
        alive = alive or (True,) * players
        classes = classes or (1,) * players
        emu = self.guest(seed, players)
        actors = {}
        for slot in range(players):
            obj, _ = self.player(emu, slot, x=float(slot), y=0.0,
                                 hp=HP if alive[slot] else 0, level=levels[slot], cls=classes[slot])
            actors['p%d' % slot] = obj
        actors['mob'], _ = self.actor(emu, 0x20, 50.0, 50.0)
        victim, table = self.actor(emu, 0x20, 10.0, 20.0, hp=PLAIN)
        emu.mem.w32(victim + 0x22C, MAX_HP)
        emu.mem.w16(victim + 0x38, facing)
        emu.mem.w32(victim + 0xD8, EXP_VALUE)
        emu.mem.w64(victim + 0xA8, cflags)
        emu.mem.w32(table + 0xD8 + 4, set_state)
        emu.mem.w32(table + 0xE0 + 4, ONDEATH_STUB)
        emu.stub(ONDEATH_STUB, name='slot28')
        if rank_list:
            for index, (sid, rank) in enumerate(rank_list):
                emu.mem.w16(G_PLAYERS + 0x4B08 + 4 * index, sid)
                emu.mem.w16(G_PLAYERS + 0x4B0A + 4 * index, rank)
            emu.mem.w16(G_PLAYERS + 0x4B08 + 4 * len(rank_list), 0xFFFF)
        # A projectile owned by p1 (or p0 with one player), and the timed-effect source.
        owner = actors['p1'] if players > 1 else actors['p0']
        projectile, _ = self.actor(emu, 0x80, 0.0, 0.0)
        emu.mem.w32(projectile + 0x4C, self.node(emu, owner))
        actors['bolt'] = projectile
        orphan, _ = self.actor(emu, 0x80, 0.0, 0.0)
        actors['orphan'] = orphan
        emu.mem.w32(victim + 0x360, self.node(emu, actors['p0']))
        emu.follow = Follow({ATAN2, HANDLE_CLEAR, HANDLE_LINK})
        for key, flags, amount in hits:
            emu.call(CREATURE_TAKE, victim, actors[key], flags, fargs=(ee_emu.raw_to_float(amount),))
            self.counts['creature_take_calls'] += 1

        def lifetap(guest):
            guest.f[0] = fraction
        blocks = []

        def pool(guest):
            block = guest.alloc(max(guest.r[4] & M32, 16))
            blocks.append(block)
            return block
        emu.stub(LIFETAP_FRACTION, function=lifetap, name='lifetap')
        emu.stub(OWN_DRAW, ret=own_draw, name='own_draw')
        emu.stub(POOL_NEW, function=pool, name='pool_new')
        emu.stub(PROP_INT, ret=prop, name='prop')
        emu.loot_args = []

        def loot(guest):
            # The three words behind a1 while the call is live (the stack is reused later).
            where = guest.r[5] & M32
            emu.loot_args.append(tuple(guest.mem.u32(where + 4 * n) for n in range(3)))
        emu.stub(DROP_LOOT, function=loot, name='dropLoot')
        emu.follow = Follow({POWF, GET_RANK, HANDLE_CLEAR, HANDLE_LINK, set_state} | set(extra_follow))
        emu.reset_log()
        emu.calls = StampedCalls(emu)
        emu.call(CREATURE_PROCESS, victim, 0)
        self.counts['creature_process_calls'] += 1
        awards = [(call.args[0] & M32, ee_emu.s32(call.args[1] & M32))
                  for call in self.calls(emu, GIVE_EXP)]
        if awards:
            site = AWARD_SITES[1 if players < 2 else 2]
            self.check('award_site_%d' % min(players, 2),
                       all(call.site == site for call in self.calls(emu, GIVE_EXP)))
        return emu, victim, actors, awards, blocks

    @staticmethod
    def event_order(emu, index):
        """Sort named events by when they happened: writes and calls share one clock,
        the write count at the time of each call. Two calls with no write between them
        (stack writes are not logged) share a stamp; their order is the order in which
        they were recorded (the call index), never the event name."""
        stamps = {}
        clock = Probe.call_clock(emu)
        for name, (kind, hits) in index.items():
            if not hits:
                return []
            # A write at index i comes after every call made with at most i writes before
            # it. A write never ties with a call (i + 0.5), and two writes never tie.
            stamps[name] = ((hits[0] + 0.5, -1) if kind == 'w'
                            else (clock[hits[0]], hits[0]))
        return sorted(stamps, key=lambda name: stamps[name])

    @staticmethod
    def call_clock(emu):
        return emu.calls.stamps

    def killer_of(self, emu, victim):
        link = emu.mem.u32(victim + 0x2E4)
        return emu.mem.u32(link + 0xC) if link else 0

    def kill_credit(self, seed):
        # One player. The share needs no killer; mana goes to a class-0 record.
        for key in ('p0', 'mob', 'bolt'):
            emu, victim, actors, awards, _ = self.kill(seed, 1, [(key, 0, PLAIN)], classes=(0,))
            want = self.award_oracle(emu, [30], [True], 0)
            self.check('one_player_award_' + key, awards == want and want == [(0, 2202)])
            self.check('one_player_mana', emu.mem.u32(G_PLAYERS + 0xC0) == 0x421FFFFF)
            self.check('one_player_link_' + key, self.killer_of(emu, victim)
                       == (actors['p0'] if key in ('p0', 'bolt') else actors['mob']))
            rolled = bool(self.calls(emu, GET_RANK))
            self.check('one_player_orb_roll_needs_killer', rolled == (key != 'mob'))
        emu, victim, actors, awards, _ = self.kill(seed, 1, [('p0', 0, PLAIN)], alive=(False,))
        self.check('one_dead_player_no_award', awards == [])
        # Two players: 0.6 for the killer, 0.4 for the other, halved when dead; 0.5 with
        # no player killer.
        cases = (('bolt', 0, (True, True), 1), ('bolt', 0, (False, True), 1),
                 ('p0', 0, (True, True), 0), ('mob', 0, (True, True), -1),
                 ('orphan', 0, (True, True), -1), ('mob', 0x10000000, (True, True), 0))
        for key, flags, alive, killer in cases:
            emu, victim, actors, awards, _ = self.kill(seed, 2, [(key, flags, PLAIN)],
                                                       levels=(30, 34), alive=alive, classes=(0, 0))
            want = self.award_oracle(emu, [30, 34], list(alive), killer)
            self.check('two_player_award', awards == want)
            mana = [emu.mem.u32(G_PLAYERS + STRIDE * slot + 0xC0) for slot in range(2)]
            self.check('two_player_mana_killer_only',
                       all((mana[slot] != 0x41200000) == (slot == killer) for slot in range(2)))
            self.counts['award_case_%s_%x_%d%d' % (key, flags, alive[0], alive[1])] = sum(a for _s, a in awards)
            if killer == -1:
                self.check('documented_vector_no_killer', awards == [(0, 381), (1, 381)])
        emu, _v, _a, awards, _ = self.kill(seed, 2, [('bolt', 0, PLAIN)], levels=(30, 34))
        self.check('documented_vector', awards == [(0, 304), (1, 457)])
        emu, _v, _a, awards, _ = self.kill(seed, 2, [('bolt', 0, PLAIN)], levels=(30, 34),
                                           alive=(False, True))
        self.check('documented_vector_dead', awards == [(0, 152), (1, 457)])
        # The killing blow keeps the credit: p0 hits while alive, the projectile of p1
        # lands the kill, p0 then hits the corpse.
        emu, victim, actors, awards, _ = self.kill(
            seed, 2, [('p0', 0, 0x41F00000), ('bolt', 0, PLAIN), ('p0', 0, PLAIN)], levels=(30, 34))
        self.check('killing_blow_keeps_credit', self.killer_of(emu, victim) == actors['p1']
                   and awards == self.award_oracle(emu, [30, 34], [True, True], 1))
        # The orb roll uses the killer's own rank of skill 0x3b and one own draw.
        for draw, made in ((0x7FFF, True), (0x8000, False)):
            emu, victim, actors, awards, blocks = self.kill(
                seed, 1, [('p0', 0, PLAIN)], fraction=0x3F000000, own_draw=draw,
                rank_list=[(0x3B, 4)])
            asked = self.calls(emu, LIFETAP_FRACTION)
            self.check('orb_rank', len(asked) == 1
                       and asked[0].args[:2] == (emu.mem.u32(G_LIFETAP_SKILL), 4))
            orbs = self.calls(emu, ONIBALL)
            if made:
                self.check('orb_made', len(orbs) == 1 and orbs[0].args[0] == blocks[0]
                           and orbs[0].args[3] == victim and orbs[0].args[4] == 0
                           and self.calls(emu, POOL_NEW)[0].args[0] == 0xB8)
            else:
                self.check('orb_not_made', not orbs and not self.calls(emu, POOL_NEW))
            self.check('orb_award_unchanged', awards == [(0, 2202)])
        self.death_path(seed)

    def death_path(self, seed):
        emu, victim, actors, awards, _ = self.kill(seed, 1, [('p0', 0, PLAIN)])
        state = self.stored(emu, victim + 0x232, 0x14)
        dead_flag = [index for index, (_pc, wrote, _size, pattern) in enumerate(emu.writes)
                     if wrote == victim + 0x0C and pattern & 0x2000]
        dead_pcs = [emu.writes[index][0] for index in dead_flag]
        slot27 = self.calls(emu, SET_STATE)
        self.check('death_slot27', len(slot27) == 1 and slot27[0].args[:2] == (victim, 0x14)
                   and slot27[0].site == 0x111DE8)
        self.check('death_state_then_flag', state and dead_flag and state[0] < dead_flag[0]
                   and dead_pcs == [DEAD_FLAG_PC]
                   and emu.mem.u16(victim + 0x232) == 0x14
                   and emu.mem.u32(victim + 0x0C) == 0x2129)
        self.check('death_award_after_state', awards == [(0, 2202)])
        self.check('death_no_delete', not self.calls(emu, OBJ_DELETE))
        # The one obj_getPropInt call is the Dead query, from the call right after the
        # flag store, on the creature with the name "Dead".
        query = self.calls(emu, PROP_INT)
        self.check('death_dead_query', len(query) == 1 and query[0].site == DEAD_QUERY_SITE
                   and query[0].args[0] & M32 == victim
                   and guest_string(emu, query[0].args[1] & M32) == b'Dead')
        # The Dead property and cflag 0x100000000 stop before the award.
        emu, victim, _a, awards, _ = self.kill(seed, 1, [('p0', 0, PLAIN)], prop=1)
        query = self.calls(emu, PROP_INT)
        self.check('dead_property', awards == [] and len(self.calls(emu, SNAP_TOP)) == 1
                   and emu.mem.u16(victim + 0x232) == 0x14
                   and len(query) == 1 and query[0].site == DEAD_QUERY_SITE)
        emu, victim, _a, awards, _ = self.kill(seed, 1, [('p0', 0, PLAIN)], cflags=0x100000000)
        self.check('cflag_no_award', awards == [] and emu.mem.u16(victim + 0x232) == 0x14)
        # A class slot 27: Horsemen_setState case 0x14 calls Creature_dropLoot and slot 28.
        # Followed: the set-state body. Stubbed: dropLoot (recorded), slot 28 (recorded),
        # its name lookup 0x10a9c0 and animation call (return 0). Two players, killer
        # p0 (own hit) or p1 (its bolt), victim facing 0x2345: the dropLoot arguments
        # must not change with the killer.
        seen = []
        for key, killer in (('p0', 0), ('bolt', 1)):
            emu, victim, actors, awards, _ = self.kill(seed, 2, [(key, 0, PLAIN)], levels=(30, 34),
                                                       set_state=HORSEMEN_SET_STATE, facing=0x2345)
            loot = self.calls(emu, DROP_LOOT)
            death = self.calls(emu, ONDEATH_STUB)
            self.check('class_drop_loot', len(loot) == 1 and loot[0].site == 0x273314
                       and loot[0].fargs[:6] == (0x42100000, 0x40000000, 0x3FE66666, 0x3F199999,
                                                 0x40000000, 0x3E800000))
            self.check('class_on_death', len(death) == 1 and death[0].args[0] == victim
                       and death[0].site == 0x2733B0)
            # Order of the whole death path: loot and slot 28 inside the class set-state,
            # then its own state store (pc HORSEMEN_STATE_PC, the only store of 0x14 at
            # +0x232; the base body 0x3c2688 is not called), the flag store, the award.
            states = self.stored(emu, victim + 0x232, 0x14)
            self.check('class_state_store', len(states) == 1
                       and emu.writes[states[0]][0] == HORSEMEN_STATE_PC
                       and not self.calls(emu, SET_STATE))
            index = {
                'state': ('w', self.stored(emu, victim + 0x232, 0x14, pc=HORSEMEN_STATE_PC)),
                'flag': ('w', self.stored(emu, victim + 0x0C, pc=DEAD_FLAG_PC)),
                'loot': ('c', [n for n, call in enumerate(emu.calls) if call.target == DROP_LOOT]),
                'slot28': ('c', [n for n, call in enumerate(emu.calls) if call.target == ONDEATH_STUB]),
                'award': ('c', [n for n, call in enumerate(emu.calls) if call.target == GIVE_EXP]),
            }
            self.check('class_death_order', self.event_order(emu, index) == list(DEATH_ORDER)
                       and awards == self.award_oracle(emu, [30, 34], [True, True], killer))
            # Loot before slot 28 by the recorded call order itself, whatever the clock.
            calls_first = [name for name in DEATH_ORDER if name in ('loot', 'slot28')]
            self.check('class_loot_slot28_call_order', index['loot'][1] and index['slot28'][1]
                       and sorted(calls_first, key=lambda name: index[name][1][0]) == calls_first)
            if index['loot'][1] and index['slot28'][1]:
                clock = self.call_clock(emu)
                same = clock[index['loot'][1][0]] == clock[index['slot28'][1][0]]
                self.counts['class_loot_slot28_same_write_stamp'] += int(same)
            if not loot:
                continue
            call = loot[0]
            ints = tuple(value & M32 for value in call.args)
            position = emu.loot_args[0]
            node = emu.mem.u32(victim + 0x2E4)
            killer_obj = actors['p%d' % killer]
            # a0 the creature, a1 a copy of its position, a2 its facing, a3 0 (the
            # Observed signature, docs/issues/kill-loot-xp.md section 2). No register
            # argument a0-t3 is the killer object or its handle node; for killer slot 1,
            # none is 1 either (slot 0 cannot be told from the zeros).
            self.check('drop_loot_args', ints[0] == victim
                       and position == tuple(emu.mem.u32(victim + 0x10 + 4 * n) for n in range(3))
                       and ee_emu.sx16(ints[2] & 0xFFFF) == 0x2345 and ints[3] == 0
                       and killer_obj not in ints and node not in ints
                       and (killer == 0 or killer not in ints))
            # Compared between the two killers: all eight integer registers (a0 relative
            # to the creature, a1 as a value), the three words behind a1, f12-f17.
            seen.append(((ints[0] - victim) & M32,) + ints[1:8] + (position, call.fargs[:6]))
            self.counts['drop_loot_calls'] += 1
        self.check('drop_loot_killer_independent', len(seen) == 2 and seen[0] == seen[1])
        # A corpse with more pending damage: pending cleared, flags kept, nothing else.
        emu = self.guest(seed)
        corpse, table = self.actor(emu, 0x2129, hp=0)
        emu.mem.w16(corpse + 0x232, 0x14)
        emu.mem.w32(corpse + 0xC8, PLAIN)
        emu.mem.w32(corpse + 0x2DC, 0x11)
        emu.mem.w32(table + 0xD8 + 4, SET_STATE)
        emu.follow = Follow(set())
        emu.reset_log()
        emu.call(CREATURE_PROCESS, corpse, 0)
        self.counts['creature_process_calls'] += 1
        self.check('corpse_pending_cleared', self.stored(emu, corpse + 0xC8, 0)
                   and emu.mem.u32(corpse + 0x2DC) == 0x11 and not self.stored(emu, corpse + 0x2DC)
                   and not self.calls(emu, GIVE_EXP) and not self.calls(emu, SET_STATE))
        self.despawn(seed)

    def despawn(self, seed):
        """Creature_deadUpdate: with cflag 0x1000000 and the top clip finished, the body
        sinks 0.35 per call and is deleted once the sink passes +0x20. Every callee is a
        stub (obj_delete recorded). Body +0x18 is 5 and the a2 vector's z is 7, so the
        two readings of +0x3c differ. f12 = 0, and 20, 30 and 100 with a zero vector as
        the monster classes pass them (docs/monsters-2.md). a1 = a3 = 0 throughout."""
        for f12, vector_z in ((0.0, 7.0), (20.0, 0.0), (30.0, 0.0), (100.0, 0.0)):
            emu = self.guest(seed)
            body, _ = self.actor(emu, 0x20)
            emu.mem.w64(body + 0xA8, 0x1000000)
            emu.mem.w16(body + 0x11A, 0x80)
            emu.mem.w32(body + 0x20, SENTINEL)
            emu.mem.w32(body + 0x18, 0x40A00000)           # body z 5
            position = emu.alloc(16)
            emu.mem.wf32(position + 8, vector_z)
            emu.follow = Follow(set())
            sink, steps, deleted_at = 0, 0, None
            while deleted_at is None and steps < 10:
                emu.mem.w32(body + 0x0C, 0x20)             # 0x4000 must come back each call
                emu.reset_log()
                emu.call(DEAD_UPDATE, body, 0, position, 0, fargs=(f12,))
                steps += 1
                self.counts['dead_update_calls'] += 1
                sink = R.fadd(sink, K_SINK)
                self.check('sink_step', emu.mem.u32(body + 0x2F4) == sink
                           and emu.mem.u32(body + 0x3C) == R.fsub(0x40A00000, sink))
                if self.calls(emu, OBJ_DELETE):
                    deleted_at = steps
                    self.check('sink_delete', R.flt(SENTINEL, sink)
                               and emu.mem.u32(body + 0x0C) == 0x4022
                               and self.calls(emu, OBJ_DELETE)[0].args[0] == body)
                else:
                    self.check('sink_keep', not R.flt(SENTINEL, sink)
                               and emu.mem.u32(body + 0x0C) == 0x4020)
            self.check('sink_deleted', deleted_at == 3)
            self.counts['sink_calls_to_delete_f%d' % int(f12)] = deleted_at or 0
        # Clip not finished: the sink is stored as 0. No cflag: no sink, no delete.
        for label, cflags, clip in (('clip_running', 0x1000000, 0), ('no_cflag', 0, 0x80)):
            emu = self.guest(seed)
            body, _ = self.actor(emu, 0x20)
            emu.mem.w64(body + 0xA8, cflags)
            emu.mem.w16(body + 0x11A, clip)
            emu.mem.w32(body + 0x2F4, SENTINEL)
            emu.follow = Follow(set())
            emu.reset_log()
            emu.call(DEAD_UPDATE, body, 0, position_of(emu), 0, fargs=(0.0,))
            self.counts['dead_update_calls'] += 1
            if cflags:
                self.check('sink_reset_' + label, self.stored(emu, body + 0x2F4, 0))
            else:
                self.check('sink_none_' + label, emu.mem.u32(body + 0x2F4) == SENTINEL
                           and not self.calls(emu, OBJ_DELETE))
        # Creature_run tail: cflag 0x1000000, active bit 63 clear, state 0x14 deletes.
        for label, cflags, state, deletes in (('inactive', 0x1000000, 0x14, True),
                                              ('active', 0x8000000001000000, 0x14, False),
                                              ('no_cflag', 0, 0x14, False)):
            emu = self.guest(seed)
            body, _ = self.actor(emu, 0x20)
            emu.mem.w64(body + 0xA8, cflags)
            emu.mem.w16(body + 0x232, state)
            emu.follow = Follow(set())
            emu.reset_log()
            emu.call(CREATURE_RUN, body, 0, max_steps=400000)
            self.counts['creature_run_calls'] += 1
            tail = self.calls(emu, OBJ_DELETE, site=0x113C04)
            self.check('run_tail_' + label, bool(tail) == deletes
                       and (emu.mem.u32(body + 0x0C) & 0x4002 == 0x4002) == deletes)

    # ---- E. real cast bodies inside Player_castSkill -------------------------------------
    def cast_bodies(self, seed):
        if self.numeric is None:
            self.numeric = N.Probe(self.elf)
        probe = self.numeric
        rigs = {16: (probe.projectiles.rig, probe.projectiles.world, probe.projectiles.world.player),
                23: (probe.projectiles.rig, probe.projectiles.world, probe.projectiles.world.player),
                49: (probe.support.rig, probe.support.world, probe.support.world.players[0]),
                55: (probe.support.rig, probe.support.world, probe.support.world.players[0])}
        for sid, (rig, world, player) in rigs.items():
            for rank in RANKS:
                self.cast_once(seed, sid, rank, rig, world, player, target=False)
            self.cast_once(seed, sid, 5, rig, world, player, target=True)

    def cast_once(self, seed, sid, rank, rig, world, player, target):
        probe = self.numeric
        mem = rig.emu.mem
        res = N.P.D.Res if rig is probe.projectiles.rig else N.Support.B.Res
        skill = mem.u32(SA.G_SKILL_TABLE + 4 * sid)
        table = mem.u32(skill + 0x60)
        cast = mem.u32(table + 8 * 2 + 4)
        self.check('cast_slot_is_family_entry', cast == CASTS[sid] and cast in rig.real)
        mem.w32(DC.G_SEED, seed & M32)
        world.place(rig.rng, centre=(0, 0, 100))
        mob = world.mobs[0] if hasattr(world, 'mobs') else world.monsters[0]
        arc = [mob] if target else []
        names = ('on_Creature_v39', 'on_world_collectObjectsInArc', 'on_Creature_v20')
        saved = {name: world.__dict__.get(name) for name in names}
        world.on_Creature_v39 = lambda args, view, rng: res(rank)
        world.on_world_collectObjectsInArc = lambda args, view, rng: res(outs=[list(arc)])
        world.on_Creature_v20 = lambda args, view, rng: res(1)
        mem.w32(player + 0xC, 0x40)
        mem.w16(player + 0x4AE, 0)
        mem.w32(player + 0x544, 1)
        mem.w32(player + 0x3C8, 0)
        record = RP.G_PLAYERS
        mem.w32(record + 0xC0, N.ABOVE)
        if sid == 49:
            mem.w32(record + 0x43FC, getattr(world, 'item', 1) or 1)
            mem.w8(record + 0x4A86, 0)
        rig.emu.reset_log()
        rig.emu.call(N.MANA[sid], skill, rank, max_steps=200000)
        cost = rig.emu.f[0] & M32
        ability = probe._ability(rig, sid)
        seen = {}

        def at_cast(emu):
            seen['cast'] = (emu.mem.u32(record + 0xC0), emu.mem.s16(player + 0x4AE),
                            tuple(emu.r[4:8]), ee_emu.sx16(emu.r[8] & 0xFFFF), len(emu.calls))

        def at_cost(emu):
            seen['cost'] = (emu.mem.u32(record + 0xC0), emu.mem.s16(player + 0x4AE))
        attach_hook = rig.emu.hooks.get(ATTACH_SPELL)

        def at_attach(emu):
            seen.setdefault('attach', (emu.mem.u32(record + 0xC0), emu.mem.s16(player + 0x4AE)))
            if attach_hook is not None:
                attach_hook(emu)
        rig.emu.hook(cast, at_cast)
        rig.emu.hook(N.MANA[sid], at_cost)
        rig.emu.hooks[ATTACH_SPELL] = at_attach
        rig.script_rng = random.Random(seed * 1000 + sid * 10 + rank)
        rig.calls = []
        rig.eview.state = {'alive': set()}
        rig.emu.r[29] = rig.emu.stack_hi - 0x400
        rig.emu.reset_log()
        rig.unknown = {}
        facing = mem.s16(player + 0x38)
        try:
            rig.emu.call(CAST_HELPER, player, ability, max_steps=6000000)
        except (ee_emu.EmuError, ee_emu.StepLimit) as exc:
            self.check('cast_helper_ran', False)
            print('cast %d: %s' % (sid, type(exc).__name__))
            return
        finally:
            rig.emu.unhook(cast)
            rig.emu.unhook(N.MANA[sid])
            if attach_hook is not None:
                rig.emu.hooks[ATTACH_SPELL] = attach_hook
            else:
                rig.emu.hooks.pop(ATTACH_SPELL, None)
            for name, value in saved.items():
                if value is not None:
                    setattr(world, name, value)
                else:
                    world.__dict__.pop(name, None)
        self.counts['cast_helper_calls'] += 1
        self.counts['cast_%d_runs' % sid] += 1
        unknown = [call.target for call in rig.emu.calls
                   if call.target not in rig.real and call.target not in rig.names]
        self.check('cast_known_calls', not unknown)
        self.check('cast_entered_once', len(self.calls(rig.emu, cast)) == 1)
        if 'cast' not in seen:
            return
        mana_at, recast_at, args, facing_arg, _ = seen['cast']
        self.check('cast_before_payment', mana_at == N.ABOVE and recast_at == 0)
        self.check('cast_args', args[0] == skill and args[1] == rank and args[2] == player)
        if target:
            dx = R.fsub(mem.u32(mob + 0x10), mem.u32(player + 0x10))
            dy = R.fsub(mem.u32(mob + 0x14), mem.u32(player + 0x14))
            want = ee_emu.sx16((K_AIM - C.atan2_16(dx, dy)) & 0xFFFF)
            self.check('cast_aim_at_target', facing_arg == want)
            self.counts['cast_aimed'] += 1
        else:
            self.check('cast_aim_facing', facing_arg == facing)
        self.check('cost_after_recast', seen.get('cost') == (N.ABOVE, 30))
        recast = self.stored(rig.emu, player + 0x4AE, 30, pc=0x1A4610)
        debit = self.stored(rig.emu, record + 0xC0, R.fsub(N.ABOVE, cost), pc=0x1A4690)
        self.check('recast_then_debit', len(recast) == 1 and len(debit) == 1 and recast[0] < debit[0]
                   and mem.u32(record + 0xC0) == R.fsub(N.ABOVE, cost))
        attach = self.calls(rig.emu, ATTACH_SPELL, site=0x1A45E0)
        held = [call for call in rig.emu.calls if call.site == 0x1A4600]
        self.check('cast_not_held', not held)
        if sid in (16, 23):
            self.check('projectile_returns_nothing', not attach)
            bolt = probe.projectiles.bolts[sid]
            level = 0x5C if sid == 16 else 0x94
            vel = 0x6C if sid == 16 else 0x9C
            speed = 0x43E10000 if sid == 16 else 0x43AF0000
            self.check('projectile_level', mem.s16(bolt + level) == rank)
            fired = facing_arg & 0xFFFF
            self.check('projectile_heading', mem.u32(bolt + vel) == C.mul(C.cos16(fired), speed)
                       and mem.u32(bolt + vel + 4) == C.mul(C.sin16(fired), speed))
            self.check('projectile_scheduled', any(rig.names.get(call.target) == 'obj_runEveryFrame'
                                                   for call in rig.emu.calls))
        else:
            pools = [call for call in rig.emu.calls if rig.names.get(call.target) == 'pool_new']
            self.check('spell_attached', len(attach) == 1 and attach[0].args[0] == player
                       and pools and attach[0].args[1] == pools[0].ret)
            # Attach comes before the recast store and the debit.
            self.check('attach_before_recast', seen.get('attach') == (N.ABOVE, 0))
            if sid == 55 and attach:
                spell = attach[0].args[1] & M32
                percent = probe.support.stat(55, 0, rank) & 0xFFFF
                most = mem.u32(RP.G_PLAYERS + 0xB0)
                share = N.Support.C.mul(N.Support.C.mul(most, N.HEAL_RATE),
                                        N.Support.C.mul(N.Support.C.from_int(percent), N.Support.SB.F_0_01))
                self.check('heal_amount_cached', mem.u32(spell + 0x1C) == share)

    # ---- driver ---------------------------------------------------------------------------
    def run_seed(self, seed):
        self.hit_direction(seed)
        self.stagger(seed)
        self.kill_credit(seed)
        self.cast_bodies(seed)

    def execute(self):
        for seed in SEEDS:
            self.run_seed(seed)
        return not self.failures


class StampedCalls(list):
    """emu.calls that also notes, on each record, how many writes came before it."""

    def __init__(self, emu):
        super().__init__()
        self.emu = emu
        self.stamps = []

    def append(self, record):
        self.stamps.append(len(self.emu.writes))
        super().append(record)


def position_of(emu):
    position = emu.alloc(16)
    emu.mem.w32(position + 8, 0x40A00000)
    return position


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='local/spells-r3/combat-r6-counts.json')
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    allowed = (ROOT / 'local/spells-r3').resolve()
    if not output.resolve().is_relative_to(allowed):
        parser.error('output must remain under local/spells-r3/')
    elf = ROOT / 'local/SLUS_209.73'
    digest = hashlib.sha256(elf.read_bytes()).hexdigest() if elf.is_file() else ''
    if digest != DC.EXPECTED_SHA256:
        print('BLOCKED: private input missing or unexpected; 0 comparisons')
        return 2
    probe = None
    failures = Counter()
    try:
        probe = Probe(elf)
        ok = probe.execute()
    except (Failure, N.Failure, N.Support.ProbeFailure) as exc:
        failures[str(exc)] += 1
        ok = False
    except Exception as exc:
        failures['aborted.' + type(exc).__name__] += 1
        print('aborted: %s %s' % (type(exc).__name__, exc))
        import traceback
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        print('  at %s:%d' % (Path(frame.filename).name, frame.lineno))
        ok = False
    if probe is not None:
        failures.update(probe.failures)
    report = {
        'status': 'PASS' if ok and not failures else 'FAIL',
        'seeds': list(SEEDS),
        'fpu': 'ps2',
        'counts': dict(sorted(probe.counts.items())) if probe else {},
        'failures': dict(sorted(failures.items())),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('%s  seeds %s  assertions %d  failures %d' % (
        report['status'], ','.join(str(seed) for seed in SEEDS),
        report['counts'].get('assertions', 0), sum(failures.values())))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
