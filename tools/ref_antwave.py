"""ref_antwave.py - the AntWave, the object AntQueen state 0x19 makes: its constructor and
its own virtual slots (run, draw, destructor), on top of the AntQueen run that builds it.

Reference contract, executed against the original by tools/difftest_antwave.py
(docs/spec/antwave.md is the prose).  Everything here is Observed by that difftest unless a
docstring says otherwise.

    AntWave_ctor    0x238654 (block, target object, position, facing, lifetime)
    AntWave_dtor    0x238750 (slot 1: object, flags)
    AntWave_run     0x238938 (slot 4: object)
    AntWave_draw    0x2387d0 (slot 5: object)

Table 0x50d298.  Every other slot is a Creature base body (tools/vtab.py): slot 2
Creature_takeDamage, slots 6, 7, 10, 11 (the touch list: Creature_slot11, empty), 17, 20,
23, 26, 27 (Creature_default_slot27, a bare store), ...; slot 15 is AntWave_clone 0x11fcd0
(not executed here).  The creature base underneath (Creature_ctor, Creature_run,
Creature_moveTo with Creature_moveBy, Creature_takeDamage, Creature_dtor) is the models of
tools/ref_creature.py, tools/ref_arena_monsters.py and tools/ref_combat_monsters.py, run for
real by the difftest.
"""
import ref_core as C
import ref_creature as RC
import ref_combat_ctors as CT
import ref_combat_ctors2 as CT2
import ref_antqueen_run as AQ
import ref_monsters_1 as M1
from ref_creature import Ext, M32, s16, s32

ANTWAVE_CTOR, ANTWAVE_DTOR, ANTWAVE_RUN, ANTWAVE_DRAW = 0x238654, 0x238750, 0x238938, 0x2387D0
ANTWAVE_CLONE = 0x11FCD0                        # slot 15, not executed
VT_ANTWAVE = 0x50D298                           # 0x2386c8 / 0x2386dc; again in the dtor 0x238754 / 0x23876c
P_ANTWAVE = 0x4FEBE0                            # the draw's particle definition (0x2388c0 / 0x2388c8)
WAVE_SIZE = AQ.WAVE_SIZE                        # 0x3d8, AntQueen_run's pool_new (0x237668)

ZERO, ONE = RC.ZERO, RC.ONE                     # 1.0: the hit amount (0x238a00), the draw's ball (0x23881c)
F_2M16 = RC.F_2M16                              # 0x37800000, the draw's ball (0x238800)
F_10000 = 0x461C4000                            # placeholder hit points for Creature_ctor (0x238658 / 0x23865c)
F_0_6 = 0x3F199999                              # turn rate +0xb0 (0x2386bc / 0x2386c0)
F_100 = 0x42C80000                              # speed +0xb8 (0x2386b4)
F_5 = 0x40A00000                                # radius +0x1c, overwritten at once (0x2386cc)
F_10 = 0x41200000                               # radius past the target's (0x2386f0); draw spread (0x2388b0)
HIT_PERIOD = 60                                 # the run's damage test every 60 clock ticks (0x23898c)
HIT_FLAGS = 0x100                               # the target's slot 2 flags (0x238a08)
DRAW_PERIOD = 3                                 # the draw's particle every 3 clock ticks (0x2387d4)
DELETE = 3                                      # slot 1 flags the run passes (0x238a38 / 0x238a60)

# bodies executed by tools/difftest_antwave.py (name -> entry)
EXECUTED = {'AntWave_ctor': ANTWAVE_CTOR, 'AntWave_run': ANTWAVE_RUN, 'AntWave_draw': ANTWAVE_DRAW,
            'AntWave_dtor': ANTWAVE_DTOR}
# virtual bodies: function -> (slot, method)
CLASS_BODIES = dict(CT2.CLASS_BODIES)
CLASS_BODIES.update({ANTWAVE_DTOR: (1, 'antwave_dtor'), ANTWAVE_RUN: (4, 'antwave_run'),
                     ANTWAVE_DRAW: (5, 'antwave_draw')})

EXTERNALS = dict(AQ.EXTERNALS)
EXTERNALS.update(CT2.EXTERNALS)
del EXTERNALS['AntWave_ctor']                   # a body here


def shape_result(name, args, ret=0, fret=0, outs=None):
    """M1.shape_result for this module's rows."""
    saved = M1.EXTERNALS
    M1.EXTERNALS = EXTERNALS
    try:
        return M1.shape_result(name, args, ret, fret, outs)
    finally:
        M1.EXTERNALS = saved


c_rem = CT2.c_rem


class Model(CT2._Dtors, AQ.Model):
    """AntQueen_run (tools/ref_antqueen_run.py) with AntWave_ctor as a body, and the
    AntWave's own slots."""

    def call(self, name, *args):
        if name == 'AntWave_ctor':
            return self.antwave_ctor(*(a & M32 if isinstance(a, int) else a for a in args))
        method = CT2.INTERNAL.get(name)
        if method is not None:
            return getattr(self, method)(*(a & M32 if isinstance(a, int) else a for a in args))
        if name == 'AntQueen_pickFlyDest':
            return AQ.Model.call(self, name, *args)
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        body = CLASS_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and body[0] == slot:
            return getattr(self, body[1])((obj + self.s16(table + 8 * slot)) & M32, *args)
        return AQ.Model.vcall(self, obj, slot, *args)

    # ---- the constructor ----------------------------------------------------------------
    def antwave_ctor(self, c, target, pos, facing, life):
        """AntWave_ctor 0x238654 (block, target object, position, facing, lifetime).

        Creature_ctor(placeholder hit points 10000, no type name, a copy of the position,
        s16 facing, no class definition, no properties): GameObject_ctor's ONE SHARED DRAW
        seeds +0x44; the clock +0x300 is zeroed there.  Then turn rate +0xb0 = 0.6, speed
        +0xb8 = 100, radius +0x1c = 5 and at once target radius + 10, table 0x50d298,
        +0x3c8 = clock (0), +0x3cc = clock + lifetime, +0x3d0 = 0, object flags |= 1, and
        handle_link(+0x3d0, target, target): the wave holds a handle to its target.
        obj_runEveryFrame.  No draw of its own."""
        w32 = self.w32
        self.creature_ctor(c, 0, tuple(pos), s16(facing), 0, 0, F_10000)
        w32(c + 0xB0, F_0_6)
        w32(c + 0xB8, F_100)
        w32(c + 0x1C, F_5)
        radius = C.add(self.u32(target + 0x1C), F_10)
        clock = self.u32(c + 0x300)
        w32(c + 0x48, VT_ANTWAVE)
        w32(c + 0x3C8, clock)
        w32(c + 0x3CC, (clock + life) & M32)
        w32(c + 0x1C, radius)
        w32(c + 0x3D0, 0)
        w32(c + 0xC, self.u32(c + 0xC) | 1)
        self.call('handle_link', c + 0x3D0, target, target)
        self.call('obj_runEveryFrame', c)

    # ---- slot 1 -----------------------------------------------------------------------
    def antwave_dtor(self, c, flags):
        """AntWave_dtor 0x238750 (slot 1: object, flags): +0x48 = 0x50d298; when the
        target handle +0x3d0 is set, handle_clear(+0x3d0) TWICE (the member's own clear,
        then the destructor's), else once; Creature_dtor(c, 0); pool_free(c) with bit 0."""
        self.w32(c + 0x48, VT_ANTWAVE)
        if self.u32(c + 0x3D0):
            self.call('handle_clear', c + 0x3D0)
        self.call('handle_clear', c + 0x3D0)
        self.call('Creature_dtor', c, 0)
        if flags & 1:
            self.call('pool_free', c)

    # ---- slot 4 -----------------------------------------------------------------------
    def antwave_run(self, c):
        """AntWave_run 0x238938 (slot 4: object).

        Creature_run(c, no model) (its result is not tested; +1 on the clock).  No target
        handle +0x3d0: slot 1 with 3 (delete) and return.  Otherwise
        Creature_moveTo(c, a copy of the target's position) - the wave walks to it at speed
        100.  When the signed clock % 60 is 0 (signed remainder) and the squared distance
        to the target, ((dx^2 + dy^2) + dz^2) with d = target - wave, is strictly below
        radius^2: the TARGET's slot 2 (take damage) with (this wave, flags 0x100; amount
        1.0).  Then, when the signed +0x3cc is below the signed clock: slot 1 with 3.
        No draw of its own; Creature_moveTo may draw the wave's own generator (stuck side
        step) and the shared seed (free-spot teleport), Creature_run the shared seed."""
        u32 = self.u32
        self.run(c, 0)
        node = u32(c + 0x3D0)
        if not node:
            self.vcall(c, 1, DELETE)
            return
        self.move_to(c, self.vec(u32(node + 0xC) + 0x10))
        if c_rem(u32(c + 0x300), HIT_PERIOD) == 0:
            t = u32(u32(c + 0x3D0) + 0xC)
            dx = C.sub(u32(t + 0x10), u32(c + 0x10))
            dy = C.sub(u32(t + 0x14), u32(c + 0x14))
            dz = C.sub(u32(t + 0x18), u32(c + 0x18))
            r = u32(c + 0x1C)
            dist2 = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
            if C.lt(dist2, C.mul(r, r)):
                self.vcall(t, 2, c, HIT_FLAGS, ONE)
        if self.s32(c + 0x3CC) < self.s32(c + 0x300):
            self.vcall(c, 1, DELETE)

    # ---- slot 5 -----------------------------------------------------------------------
    def antwave_draw(self, c):
        """AntWave_draw 0x2387d0 (slot 5: object).  Draw code, but it advances the wave's
        OWN generator +0x44, which Creature_moveTo also draws in the run.

        Only when the signed clock % 3 is 0: a unit-ball vector by own draws (three a try,
        2 d 2^-16 - 1 each, again while (x^2 + y^2) + z^2 > 1), the point position +
        vector x 10, particle_spawn(0x4febe0, point, (0, 0, 0); 0.0)."""
        if c_rem(self.u32(c + 0x300), DRAW_PERIOD):
            return
        while True:
            v = [C.sub(C.add(f, f), ONE) for f in
                 (C.mul(C.from_int(self.obj_rand(c)), F_2M16) for _k in range(3))]
            size = C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))
            if not C.lt(ONE, size):
                break
        pos = self.vec(c + 0x10)
        point = tuple(C.add(C.mul(v[k], F_10), pos[k]) for k in range(3))
        self.call('particle_spawn', P_ANTWAVE, point, (ZERO, ZERO, ZERO), ZERO)
