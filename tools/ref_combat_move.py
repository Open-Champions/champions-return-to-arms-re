#!/usr/bin/env python3
"""ref_combat_move.py - movement and collision for the combat contract of
tools/ref_combat_runtime.py (Champions: Return to Arms, SLUS_209.73, US v2.00): the player's
walk, turn and fall, the mover every player and plain object uses, and the player's
animation step.  docs/spec/combat-movement.md is the prose version.

A research tool, not game code.  Standard library only; no game data is embedded.

What it adds (all Executed: tools/difftest_combat_move.py runs the original under
tools/ee_emu.py and compares the calls with their arguments, the bytes stored outside the
stack, the shared seed and the result)

    MoveModel(T.CombatModel)
        move_with_collision     obj_moveWithCollision 0x14d4b8, with its two inline copies of
                                obj_updateGridCell (0x14d5b8, 0x14d8d0) done on the image
                                (inline_grid=True) or through the grid service (False)
        move_simple             creature_moveSimple 0x1186d8
        player_move             Player_move 0x1b4020: every mode 0..6 and beyond, a moving
                                stick, turning, the SpellCharge / SpellDrowsy call-outs,
                                water entry (one shared draw) and wading, the swing window
                                of action state 1, the slow factor, the screen clamp and its
                                second half, landing, the bookkeeping
        player_anim_step        Player_animStep 0x1b9520 (root motion into world axes)
        player_clamp_to_screen  Player_clampToScreen 0x1b3d90 (memory form, the entry point)
        player_clamp_to_screen_vec  the same on a Python vector (the form Player_move uses)
        vec3_dot_delta          0x1667d8 (point, normal, position) -> signed distance

    MoveRuntime(T.Runtime)
        the round-1 runtime with MoveModel as its model and the services the wider bodies
        reach (AUTHORED answers or refusals, each labelled), so a composed tick walks a
        player with a moving stick through the executed Player_move and Player_animStep.

Round-1 bodies this module supersedes (the round-1 methods are left as they are; see
docs/spec/combat-movement.md section 7 for the differences, each Executed):
    CombatModel.move_with_collision  calls obj_updateGridCell where the original has an
                                     inline copy of it (same stores, no call)
    CombatModel.player_move          omits the dialog_isOpen call (0x1b40c0) and the
                                     net_getCamFlag call (0x1b51e8) made on every call, and
                                     refuses the screen clamp on g_numPlayers as well as the
                                     alive count (the original tests only the alive count)

Domain: everything Player_move does is modelled; the call-outs it makes (the stick dialog
test, camera yaw and flag, spells, water services, sounds and effects, the footstep, the
animation, the screen planes, the mover when called out) are answered by the caller.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat as RB                         # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

M32, M64 = T.M32, T.M64
s8, s16, s32 = T.s8, T.s16, T.s32
ZERO, ONE = T.ZERO, T.ONE
MINUS_ONE = 0xBF800000
DT = RC.DT                                      # 0x3c888888
EPS = 0x3A83126E                                # 0.001
SIXTY = 0x42700000

# globals read here (addresses)
G_WORLD = T.G_WORLD                             # 0x44fdc8
G_SIM_FRAME = T.G_SIM_FRAME
G_RAND_SEED = T.G_RAND_SEED
G_NETWORK_MODE = T.G_NETWORK_MODE               # s8 0x402791
G_PVP_MODE_B = T.G_PVP_MODE_B                   # 0x4f7120
G_PVP_WORD_C = 0x4F7124                         # tested with g_pvpModeB for the 0.75 base
G_TURN_WORD = 0x4D8A28                          # Observed: no writer found; non-zero -> rate s x 0.035
G_LEVEL_NAME = T.G_LEVEL_NAME                   # 0x41b721
G_LEVEL_FLAGS = RC.G_LEVEL_FLAGS                # 0x44fe08 (bit 0x1000: water hurts)
G_RUN_SPEED = T.G_RUN_SPEED                     # 0x4f8418
G_ALIVE_COUNT = T.G_ALIVE_COUNT                 # 0x4f8420
G_FORCE_GHOST_REBASE = T.G_FORCE_GHOST_REBASE   # 0x402797
G_PLAYERS, REC_SIZE = T.G_PLAYERS, T.REC_SIZE
G_SCREEN_NORMALS = 0x4F8350                     # four ground normals (12 bytes each)
G_SCREEN_POINTS = 0x4F8380                      # four plane points
S_WATMEDAL = 0x537678                           # level name compared with (an address)
S_SPLASH_FMT = 0x537688                         # sprintf format of the splash sound name
S_FX_LUMP = 0x535EF0                            # lump name passed to res_find

G_MOVE_VELOCITY = 0x8657A0                      # static 12-byte vector Player_move passes to the mover
GRID_A, GRID_B, GRID_OFF = 0x5DB4F0, 0x5E95F0, 0x5F76F0
GRID_N = 0x78                                   # 120 x 120 cells of 256 units, origin -15360

WATER_BIT = 1 << 61                             # creature flags +0xa8: standing in water
F_PREDICTION_COPY = T.F_PREDICTION_COPY
F_OWN_SOUND = 0x200000                          # the machine's own real player: no sound position

Ext = RC.Ext
# call-outs of the bodies of this module, in the notation of ref_creature.Ext (kinds:
# i integer, p pointer, v vector read, V vector read and written back, W pointer to one word
# written (compared as 0 / non-zero), w the same not compared, s a C string, e elements, n list)
EXTERNALS = {
    'dialog_isOpen': Ext(0x22FBC0, '', 0, 'i'),
    'net_getCamYaw': Ext(0x13E0C8, 'i', 0, 'i', '(slot) -> camera yaw of the slot'),
    'net_getCamFlag': Ext(0x13E110, 'i', 0, 'i', '(slot) -> camera not in follow mode'),
    'net_isLocalSlot': Ext(0x13E150, 'i', 0, 'i'),
    'SpellDrowsy_typeinfo': Ext(0x3D1234, '', 0, 'i'),
    'SpellDrowsy_getStat3Fraction': Ext(0x30EF08, 'p', 0, 'f', '(spell) -> statistic 3 / 100'),
    'SpellCharge_typeinfo': Ext(0x3CCE9C, '', 0, 'i'),
    'SpellCharge_getStat3Scaled': Ext(0x2C95A4, 'p', 0, 'f', '(spell) -> turn rate of the rush'),
    'SpellCharge_onContact': Ext(0x2C95F4, 'pi', 0, 'n', '(spell or 0, target or 0)'),
    'creature_findSpellByType': Ext(0x11A710, 'pp', 0, 'i'),
    'damage_apply': Ext(0x1E8230, 'ppiiiiei', 2, 'i'),
    'water_test': Ext(0x189438, 'pvW', 1, 'i', '(world, position copy, height out; radius)'),
    'water_disturb': Ext(0x189514, 'pv', 2, 'i', '(world, position; strength, radius) -> chunks touched'),
    'res_find': Ext(0x17365C, 'ps', 0, 'i', '(lump name, entry name)'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'i', '(entry, object; volume)'),
    'fx_burst_1fbdf0': Ext(0x1FBDF0, 'v', 1, 'n', '(point; scale) splash particles'),
    'Player_animStep': Ext(0x1B9520, 'p', 1, 'i', '(player; speed) -> event bits'),
    'Player_clampToScreen': Ext(0x1B3D90, 'pVw', 0, 'i', '(player, velocity in/out, mask out)'),
    'game_buildScreenEdgePlanes': Ext(0x1E71B0, 'p', 0, 'n', '(position) -> planes at 0x4f8350 / 0x4f8380'),
    'creature_moveSimple': Ext(0x1186D8, 'pv', 0, 'i', '(object, velocity) -> bits'),
    'Player_footstep': Ext(0x1BEEC8, 'p', 0, 'n'),
    'anim_advance': Ext(0x16D748, 'pppp', 1, 'i', '(state, sound position or 0, root out, yaw out; speed)'),
    'world_slideMove': Ext(0x14D238, 'pviO', 1, 'i'),
    'world_collectObjectsInBox': Ext(0x14A928, 'vvni', 0, 'n'),
    'terrain_heightBelow': Ext(0x1834A8, 'pv', 1, 'f'),
    'obj_updateGridCell': Ext(0x14F028, 'p', 0, 'n'),
}


def shape(name, args, ret=0, fret=0, outs=None, table=None):
    """What a call-out hands back to the model, from its row of EXTERNALS (or `table`):
    the result (integer, or float pattern for 'f'), then every output in argument order -
    a vector for 'o', 'O' (when its argument is non-zero) and 'V', a word for 'w', 'W' (when
    non-zero), a list for 'n'.  A single value is returned bare, none as None."""
    ext = (table or EXTERNALS)[name]
    values, position, given = [], 0, list(outs) if outs is not None else None
    for kind in ext.ints:
        if kind in 'oOwWnbV':
            if given:
                value = given.pop(0)
            else:
                value = (0, 0, 0) if kind in 'oOV' else ([] if kind == 'n' else 0)
            if kind not in 'OW' or args[position]:
                values.append(value)
        if kind in 'ipvVesOW':
            position += 1
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


def track_weight(w, s, knee):
    """float((double(w) x (double(s) - knee)) x 3.0) through the soft-double library
    (0x3aef58, 0x3af468, 0x3af4d0, 0x3afb90).  The library keeps the sign of a zero: a
    weight of zero (either sign) times a negative difference is -0.0, pattern 0x80000000
    (Executed, difftest 'playerMove': a standing player whose blend weight has decayed to
    0 stores -0.0 in the four track fields).  `knee` (0.45 or 0.7 as doubles) is never a
    single, so the difference is never zero."""
    diff = RB.dbl_add(RB.dbl_from_single(s), -knee)
    q = RB.dbl_mul(RB.dbl_mul(RB.dbl_from_single(w), diff), T.D_3)
    if q == 0:
        return C.SIGN if (w >> 31) ^ (1 if diff < 0 else 0) else 0
    return RB.dbl_to_single(q)


def _feq(a, b):
    """c.eq.s on the patterns (+0 equals -0)."""
    return C.Fpu.compare(a, b) == 0


class MoveModel(T.CombatModel):
    """CombatModel with the movement bodies of this module.  `inline_grid` chooses how the
    two inline copies of obj_updateGridCell inside obj_moveWithCollision are done: on the
    image's list words (True: what the original stores; the differential test) or through
    the grid service 'obj_updateGridCell' (False: the shared world's grid, whose relink is
    the same operation - Observed, 0x14f028 against 0x14d5b8 and 0x14d8d0)."""

    INTERNAL = dict(T.CombatModel.INTERNAL)
    INTERNAL.update({
        'Player_animStep': 'player_anim_step',
        'Player_clampToScreen': 'player_clamp_to_screen_vec',
    })
    MODELLED = dict(T.CombatModel.MODELLED)
    MODELLED.update({'Player_animStep': 0x1B9520, 'Player_clampToScreen': 0x1B3D90, 'vec3_dotDelta': 0x1667D8})

    def __init__(self, mem, callbacks=None, external=(), inline_grid=True):
        T.CombatModel.__init__(self, mem, callbacks, external)
        self.inline_grid = inline_grid

    def call(self, name, *args):
        if name not in self.INTERNAL and name in EXTERNALS and self.cb.get(name) is None:
            args = tuple(a & M32 if isinstance(a, int) else a for a in args)
            self.calls.append((name, args))
            return shape(name, args)
        return T.CombatModel.call(self, name, *args)

    def cstr_bytes(self, addr, limit=256):
        out = bytearray()
        for k in range(limit):
            b = self.u8(addr + k)
            if b == 0:
                break
            out.append(b)
        return bytes(out)

    # ---- the grid relink (obj_updateGridCell 0x14f028 and its inline copies) -----------
    def grid_cell(self, obj):
        """The list head the position selects: grid B for flag 0x800, grid A otherwise,
        the off-grid list outside 120 x 120 cells.  Cell = (int(coordinate) + 0x3c00) >> 8;
        the column test is unsigned, the row test signed (0x14d5ec-0x14d688)."""
        ix = s32((C.to_int(self.u32(obj + 0x10)) + 0x3C00) & M32) >> 8
        iy = s32((C.to_int(self.u32(obj + 0x14)) + 0x3C00) & M32) >> 8
        if (ix & M32) < GRID_N and 0 <= iy < GRID_N:
            base = GRID_B if self.u32(obj + 0xC) & 0x800 else GRID_A
            return (base + (iy * GRID_N + ix) * 4) & M32
        return GRID_OFF

    def grid_relink(self, obj):
        """The grid node is the partner (+8) of the first node of head +8: unlink it, then
        put it at the front of the list of the current cell (even the same one)."""
        if not self.inline_grid:
            self.call('obj_updateGridCell', obj)
            return
        u32, w32 = self.u32, self.w32
        node = u32(u32(obj + 8) + 8)
        prev, nxt = u32(node + 4), u32(node)
        w32(prev, nxt)
        if nxt:
            w32(nxt + 4, prev)
        cell = self.grid_cell(obj)
        first = u32(cell)
        w32(node + 4, cell)
        w32(node, first)
        w32(cell, node)
        if first:
            w32(first + 4, node)

    # ---- obj_moveWithCollision 0x14d4b8 ------------------------------------------------
    def move_with_collision(self, obj, vel, ignore, skip_creatures):
        """obj_moveWithCollision(obj, vel, ignore, skipCreatures) -> bits 1 slid, 2 pushed
        out, 4 landed.  Executed (difftest 'moveWithCollision').

          d = vel x DT; when 0.001 < |d|^2 (3-D): slide with mask 1 / 3 creature / (|4)&5
            player, then relink.
          one box query (pos +- (r, r, 1000)), limit 0x40; top = z + height; stand = -100000.
          per object in list order, no break: skip flag 1, itself, `ignore`, a creature
            with skipCreatures; 2-D overlap dist + 0.001 < r + o.r; with flag 0x10 on
            either: skip when top < o.z + 3 or o's top < z; o's top within 5 of z: touch
            only (o 0x200 or mover 0x400) or stand on it (raise `stand`, no touch);
            push-out (slide mask 1 by the overlap, relink, bit 2) unless o 0x200, mover
            0x400 or dist <= 0.001; then o's slot 6 (unless the MOVER is the prediction
            copy, 0x14d9ac) and the mover's own slot 6.
          ground = max(terrain_heightBelow, stand); vz -= 8.999999; z += vz x DT; at or
            below ground + 0.01: z = ground and, falling, vz = 0 and bit 4."""
        u32 = self.u32
        d = (C.mul(vel[0], DT), C.mul(vel[1], DT), C.mul(vel[2], DT))
        bits = 0
        if C.lt(EPS, C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2]))):
            flags = u32(obj + 0xC)
            mask = 3 if flags & 0x20 else 1
            if flags & 0x40:
                mask = (mask | 4) & 5
            bits = 1 if self.call('world_slideMove', obj + 0x10, d, mask, 0, u32(obj + 0x1C)) else 0
            self.grid_relink(obj)
        x, y, z = self.vec(obj + 0x10)
        r = u32(obj + 0x1C)
        found = self.call('world_collectObjectsInBox', (C.sub(x, r), C.sub(y, r), C.sub(z, 0x447A0000)),
                          (C.add(x, r), C.add(y, r), C.add(z, 0x447A0000)), 0x40)
        top = C.add(u32(obj + 0x18), u32(obj + 0x20))
        stand = 0xC7C35000
        r = u32(obj + 0x1C)
        for o in found:
            oflags = u32(o + 0xC)
            if oflags & 1 or o == obj or o == ignore or (skip_creatures and oflags & 0x20):
                continue
            dx = C.sub(u32(obj + 0x10), u32(o + 0x10))
            dy = C.sub(u32(obj + 0x14), u32(o + 0x14))
            dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
            orad = u32(o + 0x1C)
            if not C.lt(C.add(dist, EPS), C.add(r, orad)):
                continue
            mf = u32(obj + 0xC)
            push = True
            if (oflags | mf) & 0x10:
                oz = u32(o + 0x18)
                if C.lt(top, C.add(oz, 0x40400000)):
                    continue
                otop = C.add(oz, u32(o + 0x20))
                z0 = u32(obj + 0x18)
                if C.lt(otop, z0):
                    continue
                if C.lt(C.sub(otop, z0), 0x40A00000):
                    if not (oflags & 0x200 or mf & 0x400):
                        if C.lt(stand, otop):
                            stand = otop
                        continue
                    push = False
            if push and not (oflags & 0x200 or mf & 0x400) and C.lt(EPS, C.fabs(dist)):
                k = C.div(C.sub(C.add(r, orad), dist), dist)
                self.call('world_slideMove', obj + 0x10, (C.mul(dx, k), C.mul(dy, k), ZERO), 1, 0, r)
                self.grid_relink(obj)
                bits |= 2
                mf = u32(obj + 0xC)
            if not mf & F_PREDICTION_COPY:
                self.vcall(o, 6, obj)
            self.vcall(obj, 6, o)
            r = u32(obj + 0x1C)
        ground = self.call('terrain_heightBelow', u32(G_WORLD), self.vec(obj + 0x10), r)
        if C.lt(ground, stand):
            ground = stand
        vz = C.sub(u32(obj + 0x30), 0x410FFFFF)
        self.w32(obj + 0x30, vz)
        nz = C.add(u32(obj + 0x18), C.mul(vz, DT))
        self.w32(obj + 0x18, nz)
        if C.le(C.sub(nz, 0x3C23D70A), ground):
            self.w32(obj + 0x18, ground)
            if C.lt(vz, ZERO):
                self.w32(obj + 0x30, ZERO)
                bits |= 4
        return bits

    def move_simple(self, obj, vel):
        """creature_moveSimple 0x1186d8 (obj, vel): obj_moveWithCollision(obj, copy, 0, 0).
        Executed (difftest 'moveSimple', with the mover running for real)."""
        return self.move_with_collision(obj, vel, 0, 0)

    # ---- Player_animStep 0x1b9520 ------------------------------------------------------
    def player_anim_step(self, P, speed):
        """Player_animStep(P; speed) -> event bits.  Executed (difftest 'playerAnimStep').

          Drowsy (+0x31a > 0 and a SpellDrowsy attached): speed x its fraction;
          slowed (1 <= +0x2fc <= 60): speed = (speed x f32(60 - slow)) x DT;
          ev = anim_advance(P+0x114, P+0x10 or 0 for flag 0x200000, P+0xbc, 0; speed)
            - which overwrites the root (+0xbc, +0xc0);
          (rx, ry) = root, c = cos16(F - 0x4000), s = sin16(F - 0x4000):
            root.y = (-rx) x s - ry x c;  root.x = (-rx) x c + ry x s."""
        u32 = self.u32
        if self.s16(P + 0x31A) > 0:
            spell = self.call('creature_findSpellByType', P, self.call('SpellDrowsy_typeinfo'))
            if spell:
                speed = C.mul(speed, self.call('SpellDrowsy_getStat3Fraction', spell))
        sound = 0 if u32(P + 0xC) & F_OWN_SOUND else P + 0x10
        n = self.u8(P + 0x2FC)
        if 1 <= n <= 60:
            speed = C.mul(C.mul(speed, C.from_int(60 - s8(n))), DT)
        ev = self.call('anim_advance', P + 0x114, sound, P + 0xBC, 0, speed)
        F = self.s16(P + 0x38)
        c, s = C.cos16(F - 0x4000), C.sin16(F - 0x4000)
        rx, ry = C.neg(u32(P + 0xBC)), u32(P + 0xC0)
        ny = C.sub(C.mul(rx, s), C.mul(ry, c))
        nx = C.add(C.mul(rx, c), C.mul(ry, s))
        self.w32(P + 0xC0, ny)
        self.w32(P + 0xBC, nx)
        return ev & M32

    # ---- Player_clampToScreen 0x1b3d90 -------------------------------------------------
    def vec3_dot_delta(self, point, normal, pos):
        """0x1667d8 (point, normal, pos) -> N . (pos - point), as N.x dx + N.y dy, + N.z dz."""
        p, n, q = self.vec(point), self.vec(normal), self.vec(pos)
        d = [C.sub(q[i], p[i]) for i in range(3)]
        return C.add(C.add(C.mul(n[0], d[0]), C.mul(n[1], d[1])), C.mul(n[2], d[2]))

    def player_clamp_to_screen_vec(self, P, V):
        """The body on a velocity value: returns (result, velocity, mask).

          mask = 0; step = V x DT; game_buildScreenEdgePlanes(P+0x10) (per machine: the
          camera's frustum; offline only); inside all four planes (signed distance >= 0)
          -> 0, V unchanged.  Else for each plane i the position is outside of: mask |=
          1 << i, and when step . N_i < 0: a first such plane removes that component
          (step -= N_i x dot); a second makes the step 0 and ends the loop.  With a plane
          used: V = step x 60, result 1; otherwise result 0."""
        return self._clamp_on_image(P, tuple(V), None)

    def player_clamp_to_screen(self, P, vptr, maskptr):
        """Player_clampToScreen(P, &V, &mask) on the image.  Executed (difftest
        'clampToScreen').  Stores: mask (0 first, then after each outside plane), V only
        when a plane was used."""
        self.w32(maskptr, 0)
        V = self.vec(vptr)
        result, newV, mask = self._clamp_on_image(P, V, maskptr)
        if result:
            self.wvec(vptr, newV)
        return result

    def _clamp_on_image(self, P, V, maskptr):
        """The body; with `maskptr` the mask word is stored the way the original stores it
        (after every plane the position is outside of)."""
        step = [C.mul(V[i], DT) for i in range(3)]
        self.call('game_buildScreenEdgePlanes', P + 0x10)
        pos = P + 0x10
        if not any(C.lt(self.vec3_dot_delta(G_SCREEN_POINTS + 12 * i, G_SCREEN_NORMALS + 12 * i, pos), ZERO)
                   for i in range(4)):
            return 0, V, 0
        used, mask = False, 0
        for i in range(4):
            N = G_SCREEN_NORMALS + 12 * i
            if not C.lt(self.vec3_dot_delta(G_SCREEN_POINTS + 12 * i, N, pos), ZERO):
                continue
            mask |= 1 << i
            if maskptr:
                self.w32(maskptr, mask)
            n = self.vec(N)
            dot = C.add(C.add(C.mul(step[0], n[0]), C.mul(step[1], n[1])), C.mul(step[2], n[2]))
            if not C.lt(dot, ZERO):
                continue
            if used:
                step = [ZERO, ZERO, ZERO]
                break
            used = True
            proj = (C.mul(n[0], dot), C.mul(n[1], dot), C.mul(n[2], dot))
            step = [C.sub(step[j], proj[j]) for j in range(3)]
        if used:
            return 1, tuple(C.mul(step[j], SIXTY) for j in range(3)), mask
        return 0, V, mask

    # ---- Player_move 0x1b4020 ----------------------------------------------------------
    def speed_scale(self, P):
        """4.1(b): the base (0.861945; 0.75 in a net game unless g_pvpModeB is set and the
        word 0x4f7124 is 0; 0.861945 again on the level 'watmedal'), x record +0x4c20 for a
        slot other than -1, x g_runSpeed, capped at 1.2, x the Drowsy fraction."""
        u32 = self.u32
        base = 0x3F5CA86D
        if self.s8(G_NETWORK_MODE) and (u32(G_PVP_MODE_B) == 0 or u32(G_PVP_WORD_C) != 0):
            base = 0x3F400000
        if self.cstr_bytes(G_LEVEL_NAME) == self.cstr_bytes(S_WATMEDAL):
            base = 0x3F5CA86D
        slot = s32(u32(P + 0x3C8))
        if slot != -1:
            base = C.mul(base, u32((G_PLAYERS + 0x4C20 + slot * REC_SIZE) & M32))
        S = C.mul(base, u32(G_RUN_SPEED))
        if C.lt(0x3F999999, S):
            S = 0x3F999999
        if self.s16(P + 0x31A) > 0:
            spell = self.call('creature_findSpellByType', P, self.call('SpellDrowsy_typeinfo'))
            if spell:
                S = C.mul(S, self.call('SpellDrowsy_getStat3Fraction', spell))
        return S

    def player_move(self, P, mode, pad, ext=0):
        """Player_move(P, mode, pad, vec) -> event bits (mode 0 only).  Executed (difftest
        'playerMove'); docs/spec/combat-movement.md section 3 gives the steps."""
        u32, w32 = self.u32, self.w32
        mode = s32(mode)
        slot = u32(P + 0x3C8)
        old = self.vec(P + 0x10)
        V = [ZERO, ZERO, ZERO]
        ev = 0
        # (a) stick suppression
        n = self.u8(P + 0x481)
        if n:
            self.w8(P + 0x481, n - 1)
            w32(pad + 0x14, ZERO)
            w32(pad + 0x18, ZERO)
        if self.call('dialog_isOpen'):
            w32(pad + 0x18, ZERO)
            w32(pad + 0x14, ZERO)
        # (b) speed scale, (c) magnitude and target angle
        S = self.speed_scale(P)
        lx, ly = u32(pad + 0x14), u32(pad + 0x18)
        m = C.sqrt(C.add(C.mul(lx, lx), C.mul(ly, ly)))
        aim = C.atan2_16(lx, ly)
        s = C.mul(S, m)
        yaw = s32(self.call('net_getCamYaw', slot))
        target = s16(aim - yaw - 0x41C2)
        if C.lt(S, s):
            s = S
        # (d) turning and the stick's components along the new facing
        cs = cc = ZERO
        if mode != 5 and C.lt(0x3C23D70A, s):
            if mode != 3:
                F = self.s16(P + 0x38)
                if mode == 1:
                    if s32(u32(P + 0x58C)) == 8:
                        a = C.mul(C.from_int(abs(s32(target - F))), 0x393EA672)
                        if C.lt(ONE, a):
                            a = ONE
                        w32(P + 0x1D4, C.add(u32(P + 0x1D4), C.mul(a, 0x3F7FFFFF)))
                    rate = 0x3E4CCCCC
                elif mode == 4:
                    rate = 0x3D5266E5
                elif mode == 6:
                    rate = C.mul(s, 0x3DA3D70A)
                elif u32(G_TURN_WORD):
                    rate = C.mul(s, 0x3D0F5C28)
                else:
                    spell = self.call('creature_findSpellByType', P, self.call('SpellCharge_typeinfo'))
                    if mode == 2 and spell:
                        rate = self.call('SpellCharge_getStat3Scaled', spell)
                    else:
                        rate = 0x3ECCCCCC
                self.w16(P + 0x38, C.angle_approach(rate, MINUS_ONE, MINUS_ONE, F, target))
            yaw2 = s32(self.call('net_getCamYaw', slot))
            cs = C.mul(C.sin16(self.s16(P + 0x38) + yaw2 + 0x4000), s)
            yaw3 = s32(self.call('net_getCamYaw', slot))
            cc = C.mul(C.cos16(self.s16(P + 0x38) + yaw3 + 0x4000), s)
        # (e)
        if mode == 2 or s32(u32(P + 0x58C)) == 1:
            s = ONE
        # (f) water
        self._player_water(P, s)
        # (g), (h) the velocity of the mode
        if mode == 0:
            ev = self._locomotion(P, s)
            yawc = s32(self.call('net_getCamYaw', slot))
            a1, a2 = -yawc - 0x4000, -yawc - 0x8000
            A = (C.neg(C.cos16(a1)), C.neg(C.sin16(a1)), ZERO)
            B = (C.neg(C.cos16(a2)), C.neg(C.sin16(a2)), ZERO)
            p, q = C.mul(cc, 0xC3340000), C.mul(cs, 0x43340000)
            V = [C.add(C.mul(A[i], p), C.mul(B[i], q)) for i in range(3)]
            if self.u8(P + 0x47E) and self.u8(P + 0x47C):
                V = [C.mul(v, 0x3FA00000) for v in V]
            w32(P + 0x4BC, V[0])
            w32(P + 0x4C0, V[1])
        elif mode in (1, 4, 6):
            for off in (0x46C, 0x184, 0x14C, 0x144, 0x16C, 0x164, 0x18C):
                w32(P + off, ZERO)
        elif mode == 2:
            F = self.s16(P + 0x38)
            V = [C.mul(C.cos16(F), 0x43960000), C.mul(C.sin16(F), 0x43960000), ZERO]
        elif mode == 5:
            V = list(ext)
        # (i) the swing window of action state 1
        heavy = s32(u32(P + 0x44C)) == 2
        if not heavy:
            self.w8(P + 0x490, 0)
        if s32(u32(P + 0x58C)) == 1:
            cls = self.s8((G_PLAYERS + 0x4A86 + s32(slot) * REC_SIZE) & M32)
            t = C.from_int(u32(G_SIM_FRAME) - u32(P + 0x448))
            if cls == 2:
                lo, hi = C.mul(0x3DCCCCCC if heavy else 0x3E199999, SIXTY), 0x41B40000
            elif cls == 1:
                lo, hi = 0x4220147A, 0x42B40000
            elif cls == 0:
                lo, hi = 0x410FFFFF, (0x4206A3D6 if heavy else 0x41B40000)
            elif cls == 3:
                lo, hi = C.mul(0x3DCCCCCC if heavy else 0x3EDDB22D, SIXTY), 0x42C3F5C1
            else:
                lo, hi = (0x4130A3D6, 0x4218E147) if heavy else (0x40C5C28E, 0x41BBAE13)
            if C.le(lo, t) and C.le(t, hi):
                V[0] = V[1] = ZERO
            if heavy and self.u8(P + 0x490) & 3:
                V[0] = V[1] = ZERO
        # (j) slow
        k = self.slow_factor(P)
        if k is not None:
            V = [C.mul(v, k) for v in V]
        # (k) screen clamp, offline with two or more alive
        mask = 0
        clamp = self.s32(G_ALIVE_COUNT) >= 2 and not self.s8(G_NETWORK_MODE)
        if clamp:
            _r, V, mask = self.call('Player_clampToScreen', P, tuple(V))
            V = list(V)
        # (l) the move
        x, y, z = self.vec(P + 0x10)
        goal = (C.add(x, C.mul(V[0], DT)), C.add(y, C.mul(V[1], DT)), z)
        W = (C.add(V[0], C.mul(u32(P + 0xBC), SIXTY)), C.add(V[1], C.mul(u32(P + 0xC0), SIXTY)), V[2])
        self.wvec(G_MOVE_VELOCITY, W)                    # a static copy is what is passed
        bits = self.call('creature_moveSimple', P, W) & M32
        w32(P + 0xBC, ZERO)
        w32(P + 0xC0, ZERO)
        # (m) bookkeeping
        if bits & 3:
            self.w8(P + 0x490, bits & 0xFF)
        if bits & 2 and self.call('net_isLocalSlot', slot) and not u32(P + 0xC) & F_PREDICTION_COPY:
            self.w8(G_FORCE_GHOST_REBASE, 1)
        if bits & 3 == 0:
            vx, vy = u32(P + 0x4BC), u32(P + 0x4C0)
            w32(P + 0x308, vx)
            w32(P + 0x30C, vy)
            k = self.slow_factor(P)
            if k is not None:
                w32(P + 0x308, C.mul(vx, k))
                w32(P + 0x30C, C.mul(vy, k))
        else:
            w32(P + 0x308, ZERO)
            w32(P + 0x30C, ZERO)
        if bits & 4:
            self.w8(P + 0x482, 15)
            if self.u8(P + 0x47D):
                self.call('Player_footstep', P)
                w32(P + 0x58C, 2)
                w32((P + 0x110 + 32 * self.s8(P + 0x118)) & M32, 0xBD6EEEEE)
                self.w8(P + 0x47C, 0)
                self.w8(P + 0x47D, 0)
            if not u32(P + 0xC) & F_PREDICTION_COPY and mode == 2 and bits & 3:
                spell = self.call('creature_findSpellByType', P, self.call('SpellCharge_typeinfo'))
                self.call('SpellCharge_onContact', spell, 0)
        else:
            v = (self.u8(P + 0x482) - 1) & 0xFF
            self.w8(P + 0x482, v)
            if s8(v) < 0:
                self.w8(P + 0x482, 0)
        # (n) the second half of the screen clamp
        if not self.call('net_getCamFlag', slot) and clamp:
            px, py, pz = self.vec(P + 0x10)
            if not (_feq(goal[0], px) and _feq(goal[1], py)):
                d = (C.sub(px, old[0]), C.sub(py, old[1]), C.sub(pz, old[2]))
                for i in range(4):
                    if not (mask >> i) & 1:
                        continue
                    nrm = self.vec(G_SCREEN_NORMALS + 12 * i)
                    dot = C.add(C.add(C.mul(d[0], nrm[0]), C.mul(d[1], nrm[1])), C.mul(d[2], nrm[2]))
                    if C.lt(dot, ZERO):
                        w32(P + 0x14, old[1])
                        w32(P + 0x10, old[0])
                        break
        return ev

    def _player_water(self, P, s):
        """4.1(f).  In water (+0xa8 bit 61): every 16th frame on a level with flag 0x1000,
        damage_apply on itself (attack 100000000, flags 0x1000030, range 1e8); water_disturb
        (300, 12) every frame while s >= 0.01, else every 16th; the bit cleared when that
        touches nothing.  Out of water, on frames with frame & 3 == 0: water_test (12); on
        a hit ONE SHARED DRAW, the bit, the splash sound (louder and a particle burst at the
        surface when airborne, +0x47c) and water_disturb (3000 or 1000, 24)."""
        u32 = self.u32
        frame = u32(G_SIM_FRAME)
        world = u32(G_WORLD)
        if self.u64(P + 0xA8) & WATER_BIT:
            if u32(G_LEVEL_FLAGS) & 0x1000 and not frame & 0xF:
                self.call('damage_apply', P, P, 100000000, 0, 0, 0x1000030, 0, 0, 0x4CBEBC20, 0x4CBEBC20)
            wet = 1
            if not C.lt(s, 0x3C23D70A) or not frame & 0xF:
                x, y, z = self.vec(P + 0x10)
                wet = self.call('water_disturb', world, (C.sub(x, ZERO), y, C.sub(z, 0x41400000)),
                                0x43960000, 0x41400000)
            if not wet:
                self.w64(P + 0xA8, self.u64(P + 0xA8) & ~WATER_BIT & M64)
            return
        if frame & 3:
            return
        hit, height = self.call('water_test', world, self.vec(P + 0x10), 1, 0x41400000)
        if not hit:
            return
        self.draw()
        self.w64(P + 0xA8, self.u64(P + 0xA8) | WATER_BIT)
        name = self.cstr_bytes(S_SPLASH_FMT).replace(b'%d', b'1', 1)
        loud = self.u8(P + 0x47C)
        entry = self.call('res_find', S_FX_LUMP, name)
        self.call('sound_playOnObject', entry, P, ONE if loud else 0x3ECCCCCC)
        x, y, z = self.vec(P + 0x10)
        self.call('water_disturb', world, (C.sub(x, ZERO), y, C.sub(z, 0x41400000)),
                  0x453B8000 if loud else 0x447A0000, 0x41C00000)
        if loud:
            self.call('fx_burst_1fbdf0', (u32(P + 0x10), u32(P + 0x14), height), ONE)

    def _locomotion(self, P, s):
        """4.1(g) without the velocity: the animation rate, blend weight +0x46c, the step,
        the ramp +0x468 and the three locomotion track weights.  Returns the event bits
        (bit 4 above s = 0.6, else bit 0)."""
        u32, w32 = self.u32, self.w32
        if C.lt(s, 0x3EDC28F5):
            rate = C.mul(s, 0x4014D653)
        elif C.lt(s, 0x3F333333):
            rate = C.add(C.mul(C.mul(C.sub(s, 0x3EDC28F5), 0x406D097A), 0x3EB33330), ONE)
        else:
            rate = C.add(C.mul(C.mul(C.sub(s, 0x3F333333), 0x40555554), 0x3E1999A0), 0x3FACCCCC)
        w = u32(P + 0x46C)
        if C.lt(0x3C23D70A, rate):
            w = C.add(w, 0x3DCCCCCC)
            w32(P + 0x46C, w)
            if C.lt(ONE, w):
                w32(P + 0x46C, ONE)
                w32(P + 0x134, 0)
        else:
            w = C.sub(w, 0x3DCCCCCC)
            w32(P + 0x46C, w)
            if C.lt(w, ZERO):
                w32(P + 0x46C, ZERO)
        if C.lt(rate, 0x3C23D70A) and C.lt(u32(P + 0x46C), 0x3D4CCCCC):
            self.call('Player_animStep', P, ONE)
            ev = 0
        else:
            ev = s8(self.call('Player_animStep', P, rate) & 0xFF)
            ev &= 4 if C.le(0x3F199999, s) else 1
        prev = u32(P + 0x468)
        if C.lt(C.sub(prev, s), 0xBD4CCCCC):
            s = C.add(prev, 0x3D4CCCCC)
        w = u32(P + 0x46C)
        w32(P + 0x14C, w)
        w32(P + 0x144, w)
        t2 = track_weight(w, s, T.D_045)
        w32(P + 0x164, t2)
        w32(P + 0x16C, t2)
        t3 = track_weight(w, s, T.D_07)
        w32(P + 0x468, s)
        w32(P + 0x184, t3)
        w32(P + 0x18C, t3)
        return ev & M32


# =======================================================================================
# The composed runtime
# =======================================================================================

class MoveRuntime(T.Runtime):
    """T.Runtime whose model is MoveModel (grid relinks through the shared world's grid):
    a player's Player_move and Player_animStep are the executed bodies, so a moving stick
    walks and turns the player through obj_moveWithCollision.  The new call-outs are
    answered here:
        net_getCamYaw / net_getCamFlag  AUTHORED (round 1): yaw 0, follow mode
        SpellCharge_typeinfo            its address (spells are refused by
                                        creature_findSpellByType when any are attached)
        Player_animStep                 the executed body; anim_advance is the authored
                                        timeline (no root motion) unless `root_motion` maps an
                                        animation state to a per-tick (x, y) root delta
        game_buildScreenEdgePlanes      AUTHORED planes from `screen_planes` (four (point,
                                        normal) pairs), refused when None - the real ones
                                        come from the camera's frustum (per machine)
        water_disturb, SpellCharge / Drowsy statistics, SpellCharge_onContact  refused
    `stick(slot, x, y)` sets the slot's movement stick (pad +0x14, +0x18)."""

    def __init__(self, terrain=None, anim=None, skill_stat=None, camera_mode=1, screen_planes=None,
                 root_motion=None):
        T.Runtime.__init__(self, terrain, anim, skill_stat, camera_mode)
        self.model = MoveModel(self.mem, self.services, inline_grid=False)
        self.screen_planes = screen_planes
        self.root_motion = dict(root_motion or {})

    def spawn_player(self, slot, pos, facing=0, hp=100.0, level=1, strength=20, armor=0, team=0, speed_mul=1.0):
        """T.Runtime.spawn_player plus the record's speed multiplier +0x4c20, which
        player_initNewCharacter and player_importCharacter set to 1.0 (Observed,
        docs/spec/movement-camera.md 4.1(b)) and without which a player cannot walk."""
        P = T.Runtime.spawn_player(self, slot, pos, facing, hp, level, strength, armor, team)
        self.mem.poke(G_PLAYERS + slot * REC_SIZE + 0x4C20, 4, T.f32(speed_mul))
        return P

    def stick(self, slot, x, y):
        pad = T.G_PADS + slot * T.PAD_SIZE
        self.mem.poke(pad + 0x14, 4, T.f32(x))
        self.mem.poke(pad + 0x18, 4, T.f32(y))

    def svc_SpellCharge_typeinfo(self):
        return 0x3CCE9C

    def svc_Player_animStep(self, P, speed):
        return self.model.player_anim_step(P, speed)

    def svc_anim_advance(self, state, sound_pos, root_out, yaw_out, speed):
        bits = self.anim.advance(self.mem, state)
        if root_out:
            rx, ry = self.root_motion.get(state, (0.0, 0.0))
            self.mem.poke(root_out, 4, T.f32(rx))
            self.mem.poke(root_out + 4, 4, T.f32(ry))
            self.note('anim', 'root', state, rx, ry)
        return bits

    def svc_water_test(self, world, pos, height_out, radius):
        r = self.terrain.water_test(pos, radius)
        self.note('terrain', 'water_test', r)
        if r:
            raise T.Unsupported('water: the water services are not in this contract')
        return (0, 0) if height_out else 0

    def svc_game_buildScreenEdgePlanes(self, pos):
        if self.screen_planes is None:
            raise T.Unsupported('the screen clamp needs the camera frustum (per machine)')
        for i, (point, normal) in enumerate(self.screen_planes):
            for j in range(3):
                self.mem.poke(G_SCREEN_POINTS + 12 * i + 4 * j, 4, T.f32(point[j]))
                self.mem.poke(G_SCREEN_NORMALS + 12 * i + 4 * j, 4, T.f32(normal[j]))
        self.note('camera', 'screen planes')
