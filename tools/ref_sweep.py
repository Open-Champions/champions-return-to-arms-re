"""ref_sweep.py - the two bodies under creature_allyInLineOfFire that stayed callbacks in
tools/ref_skeleton_run.py: world_countLivingNonplayerCreaturesInBox and
creature_objInArcRange.

Reference contract, executed against the original by tools/difftest_sweep.py (inside the
whole Skeleton_run of tools/difftest_skeleton_run.py, and entered directly).
docs/spec/skeleton-run.md section 4a is the prose.  Everything here is Observed by that
difftest unless a docstring says otherwise.

    world_countLivingNonplayerCreaturesInBox 0x108970  (centre; half size) -> count
    creature_objInArcRange                   0x10c410  (creature, object, arc; range) -> 0 or 1
"""
import ref_core as C
import ref_creature as RC
import ref_skeleton_run as SR
from ref_creature import M32, s16, s32

COUNT_LIVING, OBJ_IN_ARC = 0x108970, 0x10C410
BOX_CAPACITY = 0x80                     # 0x108974
LIVING_MASK, LIVING_VALUE = 0x68, 0x20  # 0x108a38, 0x108a10: a creature, not a player, not dead
F_RAY_LENGTH = 0x3F8CCCCC               # 1.1, the terrain ray's length factor (0x10c538/0x10c53c)
RAY_MASK = 3                            # 0x10c54c
HALF, ONE, ZERO = RC.HALF, RC.ONE, RC.ZERO

EXECUTED = {'world_countLivingNonplayerCreaturesInBox': COUNT_LIVING, 'creature_objInArcRange': OBJ_IN_ARC}


class Model(SR.Model):
    """ref_skeleton_run's model with the two bodies real."""

    def call(self, name, *args):
        if name == 'world_countLivingNonplayerCreaturesInBox':
            return self.count_living(*args)
        if name == 'creature_objInArcRange':
            return self.obj_in_arc_range(*args)
        return SR.Model.call(self, name, *args)

    def count_living(self, centre, half):
        """world_countLivingNonplayerCreaturesInBox 0x108970 (centre; half size).

        The box centre +- half on each axis (sub.s / add.s of the copied centre),
        world_collectObjectsInBox(low, high, list, 0x80), then the number of listed objects
        whose flags +0xc & 0x68 are exactly 0x20 (a creature: not a player 0x40, not dead
        8).  No draws, no stores outside the stack."""
        x, y, z = centre
        low = (C.sub(x, half), C.sub(y, half), C.sub(z, half))
        high = (C.add(x, half), C.add(y, half), C.add(z, half))
        found = self.call('world_collectObjectsInBox', low, high, BOX_CAPACITY)
        return sum(1 for obj in found if self.u32(obj + 0xC) & LIVING_MASK == LIVING_VALUE)

    def obj_in_arc_range(self, c, obj, arc, reach):
        """creature_objInArcRange 0x10c410 (creature, object, arc; range) -> 0 or 1.

        0 for no object.  d = object - creature on x and y, and on z between the two
        mid-heights (z + height +0x20 x 0.5 each).  The bearing s16(0x4000 -
        atan2_16(dx, dy)) - the facing read unsigned, narrowed to s16, made absolute, must
        be below the arc (s16, signed compare); and (creature - object)^2 on x and y, less
        the object's radius +0x1c, below range^2 (strict).  Then a terrain ray from the
        creature's position raised by its height +0x20 (a full height, not half) along d:
        terrain_raycast(g_world, that point, d, 3; 1.1); a miss (t < 0) or t > 1 is 1,
        anything else 0.  No draws."""
        if not obj:
            return 0
        u32 = self.u32
        dx = C.sub(u32(obj + 0x10), u32(c + 0x10))
        dy = C.sub(u32(obj + 0x14), u32(c + 0x14))
        dz = C.sub(C.add(u32(obj + 0x18), C.mul(u32(obj + 0x20), HALF)),
                   C.add(u32(c + 0x18), C.mul(u32(c + 0x20), HALF)))
        bearing = C.atan2_16(dx, dy)
        diff = s16(s16(0x4000 - bearing) - self.u16(c + 0x38))
        if abs(diff) >= s16(arc):
            return 0
        ex = C.sub(u32(c + 0x10), u32(obj + 0x10))
        ey = C.sub(u32(c + 0x14), u32(obj + 0x14))
        if not C.lt(C.sub(C.add(C.mul(ex, ex), C.mul(ey, ey)), u32(obj + 0x1C)), C.mul(reach, reach)):
            return 0
        origin = (u32(c + 0x10), u32(c + 0x14), C.add(u32(c + 0x18), u32(c + 0x20)))
        t = self.call('terrain_raycast', u32(RC.G_WORLD), origin, (dx, dy, dz), RAY_MASK, F_RAY_LENGTH)
        if C.lt(t, ZERO):
            return 1
        return 1 if C.lt(ONE, t) else 0

    # ---- entries the difftest calls directly ------------------------------------------------
    def count_living_entry(self, centre, half):
        return self.count_living(centre, half)

    def obj_in_arc_range_entry(self, c, obj, arc, reach):
        return self.obj_in_arc_range(c, obj, arc, reach)
