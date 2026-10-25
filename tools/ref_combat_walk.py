#!/usr/bin/env python3
"""ref_combat_walk.py - the composed combat runtime (tools/ref_combat_full.py) with the one
call-out a walking fight next to an armed creature reaches and FullRuntime refuses:
world_findFreeSpot 0x14acf8.  docs/spec/combat-walk.md is the prose.

A research tool, not game code.  Standard library only; no game data is embedded.

What is added
    world_findFreeSpot   ref_objects.World.find_free_spot (executed by
                         tools/difftest_objects.py, scenario load.marker, and by
                         tools/difftest_combat_walk.py with the creature caller's arguments),
                         on the runtime's own shared world: the shared seed is the image
                         word 0x404464, the box query is the world's own.
    the two terrain tests world_findFreeSpot makes
                         terrain_testFlag1 0x183b48 and terrain_height 0x183820, answered by
                         the runtime's terrain fixture.  FlatTerrain (AUTHORED, no walls):
                         blocked 0.0, height = the floor.  They are traced as
                         ('terrain', ...) so a trace never passes them off as the original's.

Who calls it in a fight
    Creature_moveTo's stuck recovery (tools/ref_creature.py, the teleport after 300 clock
    ticks without progress): world_findFreeSpot(position, 72, radius, 0).  A Skelight
    pressed against a walking player stops making progress, so a walking fight beside an
    armed creature reaches it after a few hundred ticks; FullRuntime refuses it.

Nothing else changes: every other name is answered (or refused) exactly as FullRuntime.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_full as F                     # noqa: E402


class FlatTerrainWithTests(T.FlatTerrain):
    """FlatTerrain plus world_findFreeSpot's two terrain tests.  AUTHORED like FlatTerrain:
    an open floor at height z, so nothing is blocked and the height is the floor."""

    def test_flag1(self, radius, pos):
        return 0                                # 0.0: not blocked

    def height(self, radius, pos):
        return self.z


class WalkRuntime(F.FullRuntime):
    """FullRuntime whose world answers world_findFreeSpot."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if type(self.terrain) is T.FlatTerrain:
            self.terrain = FlatTerrainWithTests(self.terrain.z)
        for need in ('test_flag1', 'height'):
            if not hasattr(self.terrain, need):
                raise T.Unsupported('world_findFreeSpot needs the terrain fixture to answer %s' % need)

    def _terrain_blocked(self, radius, pos):
        r = self.terrain.test_flag1(radius, pos)
        self.note('terrain', 'testFlag1', r)
        return r

    def _terrain_height(self, radius, pos):
        h = self.terrain.height(radius, pos)
        self.note('terrain', 'height', h)
        return h

    def svc_world_findFreeSpot(self, centre, spread, radius, any_height):
        """(centre, int spread, int radius, anyHeight) -> (position, ok), as the creature
        model calls it (ref_creature EXTERNALS: 'oviibi')."""
        pos, ok = self.world.find_free_spot(list(centre), spread, radius, any_height,
                                            self._terrain_blocked, self._terrain_height)
        pos = tuple(p & 0xFFFFFFFF for p in pos)
        self.note('findFreeSpot', tuple(centre), spread, radius, any_height, pos, ok)
        return pos, ok


def fl(bits):
    return C.to_float(bits)
