"""ref_combat_death.py - what a Skeleton's or an AntQueen's death runs that the round-5 Full
placement probe (tools/probe_full_placement.py) found unexecuted: Skeleton_shatter, the
boss test, the skill-rank lookup and its Player slot, the experience award, and the clip
search of AntQueen_setState 0x14.  The weapon holder's slot 11 (the dropped weapon) is
tools/ref_weapon_holder.py.

Reference contract, executed against the original by tools/difftest_combat_death.py
(docs/spec/combat-death.md is the prose).  Everything here is Observed by that difftest
unless a docstring says otherwise.

    Skeleton_shatter       0x2a7ef0  (skeleton, group)
    creature_bossRank      0x10d940  (creature) -> 0, 1 or 2
    player_getSkillRank    0x1bf330  (slot, skill id) -> rank
    Player_slot39          0x3c3b40  (player object, skill id) -> rank (tail jump)
    player_giveExp         0x1d3150  (slot, amount)
    anim_findTrack         0x170d88  (animation state, clip) -> track or 0

loot_generateDrops 0x100d54 is tools/ref_items.py's loot_generate_drops, executed by
tools/difftest_items.py (docs/spec/items.md 8); tools/difftest_combat_death.py reruns
that comparison for its coverage (LOOT below).
"""
import ref_core as C
import ref_creature as RC
from ref_creature import M32, M64, s8, s16, s32

SHATTER, BOSS_RANK, SKILL_RANK, PLAYER_SLOT39 = 0x2A7EF0, 0x10D940, 0x1BF330, 0x3C3B40
GIVE_EXP, FIND_TRACK, LOOT = 0x1D3150, 0x170D88, 0x100D54

# ---- Skeleton_shatter ---------------------------------------------------------------------
G_SHATTER_MASKS = 0x8E44C0          # static list of 64-bit part masks, zero-terminated
# group -> the masks it stores (0x2a7f40-0x2a8074; jump table 0x54bfd0, eight words for
# groups 1-8; groups 6 and 7 and anything outside 1-8 store only the terminator at
# 0x2a7f24, which every call makes first).  Bit 48-55 is the part block 0xfe << 48.
SHATTER_GROUPS = {
    1: (0xFE000000000000, 0xC0),
    2: (0x80000, 0x100000, 0x200000, 0x1000001000000000),
    3: (0x10000, 0x20000, 0x40000, 0x2000002000000000),
    4: (0x2, 0x4000, 0x8000),
    5: (0x1, 0x1000, 0x2000),
    8: (0xC0, 0x338, 0xC04, 0x10000, 0x20000, 0x80000, 0x100000, 0x1, 0x2, 0x1000, 0x4000, 0x40000,
        0x200000, 0x8000, 0x2000, 0xFE000000000000),
}
SHATTER_PROP_SIZE = 0x248           # 0x2a80b0
SHATTER_LAUNCH = 0x107              # third stack argument, 0x2a80dc
ONE = RC.ONE                        # 0x3f800000, 0x2a80e0

# ---- creature_bossRank --------------------------------------------------------------------
# the type names compared with libc_strcasecmp 0x3b81a0 (the strings are read from your
# executable; only their addresses are here)
BOSS_NAMES = tuple(range(0x52FD48, 0x52FD88, 0x10)) + (0x52FD88, 0x52FD90) + \
    tuple(range(0x52FDA0, 0x52FE10, 0x10)) + (0x52FE10,)          # 14 names, any one -> 2
BOSS_PAIRS = ((0x52FE20, 0x52FE30), (0x52FE20, 0x52FE38), (0x52FE40, 0x52FE48))   # name + its "name" property
BOSS_LAST = (0x52FE50, 0x52FE60)
S_NAME_PROPERTY = 0x52FAB0

# ---- player records -----------------------------------------------------------------------
G_PLAYERS, REC_SIZE = RC.G_PLAYERS, RC.REC_SIZE
REC_LEVEL, REC_EXP, REC_HP, REC_MAX_HP, REC_MANA, REC_MAX_MANA = 0x59, 0x5C, 0xAC, 0xB0, 0xC0, 0xC4
REC_SKILL_POINTS, REC_STAT_POINTS, REC_SKILLS = 0xE8, 0xEC, 0x4B08
G_EXP_TABLE = RC.G_EXP_TABLE        # 0x41b558, s32[81]
G_EXP_CAP = G_EXP_TABLE + 4 * 80    # 0x41b698, read at 0x1d3188
S_LEVEL_LUMP, S_LEVEL_SOUND, S_LEVEL_TEXT = 0x53B1F0, 0x53B338, 0x53B348
LEVEL_MESSAGE_FRAMES = 0x168        # 0x1d328c
# levels below each bound add the points beside it (0x1d31cc-0x1d3210), 5 from 36 up
SKILL_POINT_STEPS = ((6, 1), (0x10, 2), (0x1A, 3), (0x24, 4))

EXECUTED = {'Skeleton_shatter': SHATTER, 'creature_bossRank': BOSS_RANK, 'player_getSkillRank': SKILL_RANK,
            'Player_slot39': PLAYER_SLOT39, 'player_giveExp': GIVE_EXP, 'anim_findTrack': FIND_TRACK}
# Executed by tools/difftest_items.py against tools/ref_items.py (docs/spec/items.md):
# loot_generateDrops (its 'loot' job, rerun here for the coverage) and what that job runs
# for real underneath it; loot_spawnGold by the 'gold' job (Gold constructor 0x157668,
# terrain and pool answered there).  Listed in EXECUTED so that the probe runs them.
EXECUTED_ELSEWHERE = {
    'loot_generateDrops': LOOT, 'loot_spawnGold': 0x100974,
    'item_generateFromSpecialTable': 0x104758, 'item_generateWithAffixes': 0x104CA4,
    'item_generateFlag35Entry': 0x106214, 'item_generateFlag45Entry': 0x106658,
    'item_generateConsumable': 0x108590, 'level_monsterLevelTimes0_4': 0x1EBF20,
    'level_monsterLevelTimesDifficulty': 0x1EBF70,
}
EXECUTED.update(EXECUTED_ELSEWHERE)
BODY_END = {SHATTER: 0x2A815C, BOSS_RANK: 0x10DBD8, SKILL_RANK: 0x1BF398, PLAYER_SLOT39: 0x3C3B58,
            GIVE_EXP: 0x1D32E4, FIND_TRACK: 0x170DF8, LOOT: 0x101998}


def record(slot):
    return (G_PLAYERS + s32(slot) * REC_SIZE) & M32


class Model(RC.Model):
    """The death-path bodies on a memory image.  Callbacks: pool_new, PhProp_ctor2,
    obj_getPropStr, player_recalcStats, net_isLocalSlot, res_find, sound_playOnObject,
    text_lookup, hud_showMessage."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        return self.cb.get(name)(*args)

    def cstr(self, addr, limit=256):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(addr + len(out))
            if not b:
                break
            out.append(b)
        return bytes(out)

    def same_text(self, a, b):
        """libc_strcasecmp(a, b) == 0 for the ASCII texts the difftest uses."""
        return self.cstr(a).lower() == self.cstr(b).lower()

    # ---- Skeleton_shatter ---------------------------------------------------------------------
    def skeleton_shatter(self, c, group):
        """Skeleton_shatter 0x2a7ef0 (skeleton, group).

        Stores the group's masks in the static list 0x8e44c0 (64-bit words, terminated by
        0; the first word is zeroed by every call).  Then for each mask m of the list, in
        order, with the part bits p = +0x220 & m (the creature's show mask, a 64-bit word
        read once): when p is non-zero, pool_new(0x248) and, with a block,
        PhProp_ctor2(block, copy of the position, s16 facing, definition word +0xc, anim
        +0x114, definition words +0, +8, +0x10; 1.0; stack: p (64 bits, passed
        here as ('mask', p)), 0x107, 0) - and the bits of
        m are removed from the mask whether or not a block came.  The mask is stored back
        at the end.  No draw here (the constructor is a callback)."""
        self.w64(G_SHATTER_MASKS, 0)
        masks = SHATTER_GROUPS.get(s32(group))
        if masks is not None:
            for k, m in enumerate(masks + (0,)):
                self.w64(G_SHATTER_MASKS + 8 * k, m)
        mask = self.u64(c + 0x220)
        k = 0
        while True:
            m = self.u64(G_SHATTER_MASKS + 8 * k)
            if not m:
                break
            part = mask & m
            if part:
                block = self.call('pool_new', SHATTER_PROP_SIZE)
                if block:
                    d = self.u32(c + 0x24)
                    self.call('PhProp_ctor2', ONE, block, self.vec(c + 0x10), self.s16(c + 0x38), self.u32(d + 0xC),
                              c + 0x114, self.u32(d), self.u32(d + 8), self.u32(d + 0x10), ('mask', part),
                              SHATTER_LAUNCH, 0)
                mask &= ~m & M64
            k += 1
        self.w64(c + 0x220, mask)

    # ---- creature_bossRank --------------------------------------------------------------------
    def boss_rank(self, c):
        """creature_bossRank 0x10d940 (creature) -> 0, 1 or 2.

        0 without object flag 0x20.  No type name (+0x34 = 0): bit 0 of the creature flags.
        2 when the type name equals (without case) one of BOSS_NAMES; or the first BOSS_PAIRS
        name with its "name" property (obj_getPropStr(c, "name", 0)) equal to the first
        value, or the same name again (a second property call) with the second value, or
        the third name with the third value; or one of BOSS_LAST.  Otherwise bit 0 of the
        creature flags (MiniBoss)."""
        if not self.u32(c + 0xC) & 0x20:
            return 0
        name = self.u32(c + 0x34)
        if not name:
            return self.u64(c + 0xA8) & 1
        for s in BOSS_NAMES:
            if self.same_text(name, s):
                return 2
        for type_name, value in BOSS_PAIRS:
            if self.same_text(self.u32(c + 0x34), type_name):
                prop = self.call('obj_getPropStr', c, S_NAME_PROPERTY, 0)
                if self.same_text(prop, value):
                    return 2
        for s in BOSS_LAST:
            if self.same_text(self.u32(c + 0x34), s):
                return 2
        return self.u64(c + 0xA8) & 1

    # ---- skill ranks ----------------------------------------------------------------------------
    def get_skill_rank(self, slot, skill):
        """player_getSkillRank 0x1bf330 (slot, skill id) -> the signed rank of the first
        (id, rank) halfword pair at record +0x4b08 whose id is the argument (compared as
        a sign-extended halfword with the full register); the list ends at an id of -1
        (tested before each next pair); 0 when absent."""
        rec = record(slot)
        k = 0
        if self.s16(rec + REC_SKILLS) == -1:
            return 0
        while True:
            if self.s16(rec + REC_SKILLS + 4 * k) == s32(skill):
                return self.s16(rec + REC_SKILLS + 4 * k + 2) & M32
            k += 1
            if self.s16(rec + REC_SKILLS + 4 * k) == -1:
                return 0

    def player_slot39(self, p, skill):
        """Player slot 39, 0x3c3b40 (player, skill id): a jump to player_getSkillRank with
        the slot index at +0x3c8."""
        return self.get_skill_rank(self.u32(p + 0x3C8), skill)

    # ---- experience ---------------------------------------------------------------------------
    def give_exp(self, slot, amount):
        """player_giveExp 0x1d3150 (slot, amount).

        exp +0x5c += amount, stored; above table[80] - 1 (0x41b698) it is that.  While
        table[level] <= exp (signed, level the signed byte +0x59, re-read): skill points
        +0xe8 += 1 below level 6, 2 below 16, 3 below 26, 4 below 36, else 5; stat points
        (byte +0xec) += 3; level += 1; player_recalcStats(); with hp +0xac above 0.0, hp =
        max hp +0xb0 and mana +0xc0 = max mana +0xc4; when net_isLocalSlot(slot) the
        level-up sound (res_find, sound_playOnObject(sound, 0; 1.0)); the text
        (text_lookup) shown by hud_showMessage(text, 0x168, slot, 0).  No draw."""
        rec = record(slot)
        cap = s32(self.u32(G_EXP_CAP)) - 1
        exp = s32(self.u32(rec + REC_EXP) + amount)
        self.w32(rec + REC_EXP, exp)
        if cap < exp:
            self.w32(rec + REC_EXP, cap)
        while True:
            level = s8(self.u8(rec + REC_LEVEL))
            if s32(self.u32(rec + REC_EXP)) < s32(self.u32((G_EXP_TABLE + 4 * level) & M32)):
                return
            points = self.u32(rec + REC_SKILL_POINTS)
            step = 5
            for bound, value in SKILL_POINT_STEPS:
                if level < bound:
                    step = value
                    break
            self.w32(rec + REC_SKILL_POINTS, points + step)
            self.w8(rec + REC_STAT_POINTS, self.u8(rec + REC_STAT_POINTS) + 3)
            self.w8(rec + REC_LEVEL, self.u8(rec + REC_LEVEL) + 1)
            self.call('player_recalcStats')
            if C.lt(RC.ZERO, self.u32(rec + REC_HP)):
                self.w32(rec + REC_HP, self.u32(rec + REC_MAX_HP))
                self.w32(rec + REC_MANA, self.u32(rec + REC_MAX_MANA))
            if self.call('net_isLocalSlot', slot):
                sound = self.call('res_find', S_LEVEL_LUMP, S_LEVEL_SOUND)
                self.call('sound_playOnObject', ONE, sound, 0)
            text = self.call('text_lookup', S_LEVEL_TEXT)
            self.call('hud_showMessage', text, LEVEL_MESSAGE_FRAMES, slot, 0)

    # ---- anim_findTrack -----------------------------------------------------------------------
    def find_track(self, state, clip):
        """anim_findTrack 0x170d88 (state, clip) -> state + 8 + 32 k for the first of the
        signed-byte count +4 tracks whose clip word +8 + 32 k is the clip; 0 for a null
        state or clip, or none."""
        if not state or not clip:
            return 0
        count = s8(self.u8(state + 4))
        for k in range(max(count, 0)):
            if self.u32(state + 8 + 32 * k) == clip & M32:
                return (state + 32 * k + 8) & M32
        return 0
