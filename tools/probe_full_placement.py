#!/usr/bin/env python3
"""probe_full_placement.py - how far the ORIGINAL AntQueen, Skeleton and Soul get on the
round-5 Full-fight placement before they call a body that no difftest has executed.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/probe_full_placement.py [path/to/SLUS_209.73] [--ticks N] [--class NAME]
                                          [--serial N] [--placement round5|native] [--all]

    --ticks N      ready ticks to run (default 300)
    --class NAME   antqueen, skeleton or soul (default: all three, one run each)
    --serial N     the creature serial counter 0x4f85c4 before construction (default 0)
    --placement    round5: AntQueen (0, 140), Skeleton (70, 140), Soul (-70, 140) as the
                   native Full fixture had them (open-champions 9c224e7); native: the Soul
                   at (-60, 100) as it is now (ed062c3); duel: round5 without the other
                   two classes' stand-ins.  Default round5.
    --hit-every N  every N ticks the player hits the probed creature through its own
                   virtual slot 2 (--hit-amount A, default 10; flags 1) before its run:
                   a stand-in for the attacking player of the native smoke test
    --all          do not stop at the first unexecuted body: answer it with 0 and go on,
                   so the run lists every one it meets, with the tick of its first call
    --type NAME    the type name the constructor gets (default AntQueen / Skeleton / Soul),
                   e.g. SkeletonBow or SkeletonSwordOHW to fix the Skeleton's weapon kind
    --pool         pool_new hands out zero-filled blocks (default: it refuses, so no effect
                   object is built); the objects built in them do not run
    --clips [PATH] the game's own animation code (executed by tools/difftest_anim.py) runs
                   on the class's own clips, read from your disc image PATH (default the
                   Play-RTA image) or a directory of its .LMP files: real clip lengths,
                   the constructor-installed event bits and root motion, instead of the
                   20-tick clip clock
    --run-objects  (implies --pool) the objects built in pool blocks run: the probe keeps
                   the run lists their obj_runEvery* calls join and, each frame, calls slot 4
                   of each in runObjects order (every-frame list before the creature, then
                   the 15- and 60-lists), and slot 1 (3) of each deleted one first
    --skills       the game's start-up initialiser builds the 101 Skill objects first (as
                   tools/difftest_skills_a.py does), so g_skillTable is not empty

What it is
    A probe, not a comparison.  The original constructor and run function of ONE class run
    in tools/ee_emu.py every tick, with every callee that some difftest of this repository
    has executed against a model running for real (EXECUTED below) and everything else a
    named stub.  A stub is either
      - a SERVICE: the engine answers the composed runtimes give from fixtures (flat dry
        ground, no walls, the 20-tick clip clock of ref_combat_runtime.AnimTimeline,
        presentation, handles, the pool) - answered here deterministically, or
      - an UNEXECUTED body: game logic whose body no difftest has run.  The probe stops at
        the first one (the "next unexecuted function" a port has to refuse).
    The run function's own state switch is a stop too when it dispatches into a state
    whose arm no difftest has executed (RUN_STATES_EXECUTED).

The world (AUTHORED, labelled): the round-5 Full fixture of the native client
    player 0 at the origin, team 0, idle; two Skelights at (80, 0) facing 0x8000 and
    (-40, 0) facing 0, team 0xff; AntQueen, Skeleton and Soul facing 0xc000, 120 hit
    points.  Only the probed class is real; the other actors are static stand-ins at their
    placement with the base Creature table (the player with object flags 0x60).  Flat
    ground at z = 0.  g_simFrame starts at 0 and the native "ready tick" k is frame k - 1.
"""
import hashlib
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ctors as CT                   # noqa: E402
import difftest_creature as DC                  # noqa: E402
import difftest_combat_ctors as DCT             # noqa: E402
from difftest_creature import Res, f32, fl, rd, M32     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------------------
# What has been executed
# ---------------------------------------------------------------------------------------
def executed_bodies():
    """Function entry -> module, for every body a difftest of this tree executed: the
    MODELLED / CLASS_BODIES tables of the ref_*.py modules and the round-2 FullModel."""
    import importlib
    out = {}
    names = ('ref_creature', 'ref_arena_monsters', 'ref_monsters_1', 'ref_combat_ctors',
             'ref_potion_ctors', 'ref_combat_round3', 'ref_combat_round4', 'ref_combat_round5',
             'ref_combat_round6', 'ref_skills_a', 'ref_skills_b', 'ref_skills_c',
             'ref_combat_ctors2', 'ref_antqueen_run', 'ref_fire_touch', 'ref_phprop', 'ref_soul_run', 'ref_skeleton_run',
             'ref_combat_death', 'ref_weapon_holder', 'ref_sweep', 'ref_holder_slots',
             'ref_attach_matrix', 'ref_antwave', 'ref_phprop_run', 'ref_gold', 'ref_prop_dtors',
             'ref_arrow_run', 'ref_prop_dtors')
    for name in names:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        for attr in ('MODELLED', 'EXECUTED'):
            table = getattr(mod, attr, None)
            if isinstance(table, dict):
                for value in table.values():
                    if isinstance(value, int):
                        out.setdefault(value, name)
        bodies = getattr(mod, 'CLASS_BODIES', None)
        if isinstance(bodies, dict):
            for fn in bodies:
                out.setdefault(fn, name)
    import ref_combat_full as F
    for value in F.FULL_MODELLED.values():
        out.setdefault(value, 'ref_combat_full')
    for addr in DC.REAL_OTHER:
        out.setdefault(addr, 'difftest_creature')
    for addr, where in EXECUTED_ELSEWHERE.items():
        out.setdefault(addr, where)
    try:                                        # the math leaves tools/difftest_core.py compares
        import difftest_core as DCO
        for case in DCO.CASES:
            if isinstance(case[1], int):
                out.setdefault(case[1], 'difftest_core %s' % case[0])
    except ImportError:                         # pragma: no cover
        pass
    import ref_combat_runtime as T
    for addr in T.EMPTY_BODIES:                 # empty bodies (docs/combat-runtime.md 9)
        out.setdefault(addr, 'ref_combat_runtime.EMPTY_BODIES')
    return out


# Executed bodies whose module keeps no address table.
EXECUTED_ELSEWHERE = {
    0x1E8230: 'ref_combat.damage_apply (tools/difftest_combat.py)',
    # a three-instruction getter of the word 0x500ae8; runs real in every
    # tools/difftest_natives.py case (its MACHINERY table)
    0x27DD68: 'jumpgate_getTravelState (tools/difftest_natives.py MACHINERY)',
}
# tools/ref_items.py keeps no address table.  Whole bodies its difftest (tools/difftest_items.py)
# compares, by property; rerun 2026-10-21: 22 of 22 properties PASS.  Partial ones (the scatter
# loop of loot_spawnGold, the seed side of item_loadResources) are not listed.
ITEM_BODIES = {
    0x1069B8: 'parse-tables, parse-random', 0x1024A8: 'value-random', 0x103E08: 'stats-random',
    0x103EC8: 'stats-random', 0x103F88: 'stats-random', 0x104100: 'stats-random', 0x1083F8: 'stats-random',
    0x104C04: 'small', 0x104C48: 'small', 0x108924: 'small', 0x107CA8: 'small', 0x107EA4: 'small',
    0x107EC0: 'small', 0x104758: 'preset-full', 0x104CA4: 'affix-full', 0x106214: 'plain', 0x106658: 'plain',
    0x108590: 'plain', 0x107D54: 'shop', 0x100D54: 'loot-full', 0x100BA0: 'named', 0x1C4948: 'equip',
    0x101E48: 'names',
    # callees those bodies run for real in the same properties (their jal closure, C library
    # aside): item_getUnitMultiplier (attack rating, damage range), item_randomizeVariant
    0x1046B4: 'stats-random, inside 0x103f88 and 0x104100', 0x1046E0: 'parse-random, preset-full, affix-full',
}
for _addr, _prop in ITEM_BODIES.items():
    EXECUTED_ELSEWHERE.setdefault(_addr, 'ref_items (tools/difftest_items.py %s)' % _prop)


# The run functions' switches: entry -> (address of the range test, jump-table base,
# states whose arm a difftest has executed).  Round 5 executed states 0 and 1 of Skeleton
# and the Soul phase gate (docs/spec/combat-round5.md); docs/spec/antqueen-run.md every
# AntQueen state.
RUN_SWITCHES = {
    'AntQueen_run': (0x236F78, 0x237004),
    'Skeleton_run': (0x2A6864, 0x2A6954),
    'Soul_run': (0x2A9870, 0x2A997C),
}
RUN_STATES_EXECUTED = {
    'AntQueen_run': set(range(0x1A)),   # every arm: tools/difftest_antqueen_run.py (this round)
    'Skeleton_run': set(range(0x18)),   # every arm: tools/difftest_skeleton_run.py
    'Soul_run': set(),
}
try:                                    # every Soul arm: tools/difftest_soul_run.py
    import ref_soul_run as _SR
    RUN_STATES_EXECUTED['Soul_run'] = set(_SR.SOUL_RUN_STATES_EXECUTED)
except ImportError:                     # pragma: no cover
    pass

# Call-outs the composed runtimes answer as services (ref_combat_runtime.Services and the
# native World's fixtures): engine, presentation and bookkeeping, not game rules.
SERVICES = {
    'anim_clear', 'anim_push', 'anim_pushChained', 'anim_start', 'anim_startBlendInOut',
    'anim_pushWithWeights', 'anim_advance', 'anim_releaseCaches', 'anim_snapTopToEnd',
    'anim_jumpTopToEnd', 'anim_syncToSimFrame', 'anim_setTrackWeightRate',
    'handle_link', 'handle_clear', 'handle_removeNode', 'iter_begin', 'iter_next',
    'pool_new', 'pool_free', 'GameObject_ctor', 'res_find', 'model_buildHideMask',
    'terrain_heightBelow', 'terrain_height', 'terrain_raycast', 'world_raycast',
    'world_collectObjectsInBox', 'world_slideMove', 'world_findFreeSpot', 'water_test',
    'water_disturb', 'obj_getPropInt', 'obj_getPropStr', 'Creature_setStats', 'balance_lookup',
    'fx_spawn', 'particle_spawn', 'sound_playOnObject', 'sound_playAtPos', 'decal_add',
    'creature_stopBossMusic', 'fx_burnModel', 'fx_shockModel', 'player_voice', 'glow_add',
    'libc_sprintf', 'model_getBounds', 'model_getAttachPoint', 'model_getSamplePointCount',
    'model_getSamplePoint', 'Creature_init', 'obj_updateActive', 'net_objOrGhost',
    'players_anyWithinRadius', 'player_speedScale',
    'isNearCameraFocus480',             # camera only; its callers are particle/effect code
    'obj_delete',                       # the deferred delete (docs/spec/object-system.md)
    # the physics prop's rigid body and its bookkeeping (docs/spec/gut-chunk.md 9): the body's
    # one draw is the cosmetic seed, not the shared one
    'rigidbody_init', 'quat_fromMat3', 'quat_normalize', 'rigidbody_updateDerived', 'obj_stopRunning',
    # resource and pose lookups (as res_find, model_getBounds, model_getAttachPoint): where a
    # bone prop starts (PhProp_ctor2) and the gold pile's clip (Gold_ctor2)
    'model_getMeshJoint', 'anim_getJointMatrix', 'resref_get',
    # the hit sound: builds a name (libc_sprintf, libc_strcat), res_find, sound_playOnObject;
    # no seed (Observed 0x1e7e40-0x1e822f).  Reached by damage_apply once a swing lands.
    'sound_playHit',
    # the dynamic-light grid of the renderer: no call, writes only the light-grid cell lists
    # and the overflow list 0x5db368 (Observed 0x148af8-0x148bc3).  MissileWeapon_ctor's
    # trail light; the ranged difftests stub it too.
    'light_link',
    'light_unlink',                     # its list unlink: two words of the node and its neighbours (0x14a4f0-0x14a523)
    # an arrow's trail ribbon and light (the ranged difftests stub them too): no call and no
    # seed word in trail_create 0x190ff8, trail_addPoint 0x192550, trail_release 0x192800,
    # light_dtor 0x14a490 (Observed).  trail_create answers 0: no trail
    'trail_create', 'trail_addPoint', 'trail_release', 'light_dtor', 'sound_playSample',
    # flying and exploding element arrows, settling props (docs/spec/arrow-run.md,
    # docs/spec/phprop-run.md): the light's grid relink, impact puffs (the cosmetic seed
    # 0x404460 only), the ring burst, the camera shake, the water ripple
    'light_relink', 'fx_impactPuffNearCamera', 'fx_ringBurst', 'camera_shake', 'water_disturb',
}


PLACEMENTS = {
    'round5': {'antqueen': (0, 140), 'skeleton': (70, 140), 'soul': (-70, 140)},
    'native': {'antqueen': (0, 140), 'skeleton': (70, 140), 'soul': (-60, 100)},
    # round5 without the other two classes' stand-ins (AUTHORED): the Soul stand-in is on
    # the player's team 0 and nearer the Skeleton than the player, so on round5 it is the
    # Skeleton's target; here the player is the only one
    'duel': {'antqueen': (0, 140), 'skeleton': (70, 140), 'soul': (-70, 140)},
}
SKELIGHTS = (((80, 0), 0x8000), ((-40, 0), 0))
FIXTURE_PAGE = 0x00C00000              # difftest_creature's fixture handles live in this page
POOL_LIMIT = 4000                       # blocks --pool hands out before refusing again
MAX_STEPS = 400000000                   # per call: a boss death builds items with the real C string code
FACING = 0xC000
LEVEL = b'drunare'                      # any level but airhub (the Soul class tests that name)
HP = 120.0
TYPE_NAMES = {'antqueen': b'AntQueen', 'skeleton': b'Skeleton', 'soul': b'Soul'}
# The stand-ins carry their class's own virtual table, so that a slot the probed creature
# calls on them reaches the real function (run when executed, reported when not).
TABLES = {'player': 0x511308, 'skelight': 0x5174B0, 'antqueen': 0x511078, 'skeleton': 0x5175F8,
          'soul': 0x517740}
# Type-info getters (virtual slot 0; C++ runtime, symbols/runtime.tsv): they run for real.
TYPEINFO = {'creature': 0x3C2608, 'player': 0x3C3AB8, 'antqueen': 0x3C3C78, 'skeleton': 0x3CC62C,
            'skelight': 0x3CC6DC, 'soul': 0x3CC7A0}


def symbol_names():
    """Function address -> name from names.tsv and symbols/*.tsv (for the report only)."""
    out = {}
    paths = [os.path.join(ROOT, 'names.tsv')]
    sym = os.path.join(ROOT, 'symbols')
    paths += [os.path.join(sym, f) for f in sorted(os.listdir(sym)) if f.endswith('.tsv')]
    for path in paths:
        for line in open(path, encoding='utf-8-sig'):
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 2:
                try:
                    out.setdefault(int(parts[0], 16), parts[1])
                except ValueError:
                    pass
    return out


class Stop(Exception):
    pass


def function_starts():
    """Sorted function entries of ghidra_funcs.tsv: every executed pc is mapped to the
    function that holds it, so that a body entered by a plain jump (which the interpreter
    does not record as a call) is still seen."""
    starts = []
    for line in open(os.path.join(ROOT, 'ghidra_funcs.tsv'), encoding='utf-8-sig'):
        parts = line.rstrip('\n').split('\t')
        try:
            starts.append(int(parts[0], 16))
        except (ValueError, IndexError):
            pass
    return sorted(set(starts))


# ---------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------
class World(DCT.World):
    """difftest_combat_ctors' world (definitions, tables, skelcom, level name) with every
    answer replaced by a deterministic one.  Answers not listed here fall back to 0 and
    are reported as such."""

    probe = None

    def respond(self, name, args, view, rng):
        probe = self.probe
        if probe is None:                       # during the world's own build
            return DCT.World.respond(self, name, args, view, rng)
        handler = getattr(self, 'on_' + name.replace('.', '_'), None)
        label = name
        rec = probe.rig.emu._fresh_call
        if name.startswith(('Creature.v', 'Holder.v')) and rec is not None and rec.target in probe.symbols:
            label = '%s (%s)' % (probe.symbols[rec.target], name)
        cls = probe.classify_name(name)
        probe.note_stub(label, cls, args)
        if handler is None or name not in self.DETERMINISTIC:
            probe.defaulted[name] = probe.defaulted.get(name, 0) + 1
            return Res()
        return handler(args, view, rng)

    DETERMINISTIC = {
        'GameObject_ctor', 'pool_new', 'Creature_setStats', 'res_find', 'model_buildHideMask',
        'world_collectObjectsInBox', 'terrain_heightBelow', 'terrain_height', 'world_slideMove',
        'world_findFreeSpot', 'water_test', 'anim_advance', 'anim_push', 'anim_pushChained',
        'anim_start', 'anim_startBlendInOut', 'anim_pushWithWeights', 'anim_clear',
        'handle_link', 'handle_clear', 'Creature.v16', 'Creature.v37', 'obj_getPropInt',
        'obj_getPropStr', 'iter_begin', 'iter_next', 'net_objOrGhost', 'player_speedScale',
        'model_getSamplePointCount', 'terrain_raycast', 'world_raycast',
        'SkillLifeTap_getStat0Fraction', 'player_getSkillRank', 'libc_sprintf',
        'obj_runEveryFrame', 'obj_runEvery60', 'obj_runEvery15', 'obj_stopRunning', 'obj_delete',
    }

    # ---- run lists (docs/spec/object-system.md 5.1), kept for --run-objects --------------
    def on_obj_runEveryFrame(self, args, view, rng):
        self.probe.link(args[0], 'frame')
        return Res()

    def on_obj_runEvery60(self, args, view, rng):
        self.probe.link(args[0], 60)
        return Res()

    def on_obj_runEvery15(self, args, view, rng):
        self.probe.link(args[0], 15)
        return Res()

    def on_obj_stopRunning(self, args, view, rng):
        self.probe.unlink(args[0])
        return Res()

    def on_obj_delete(self, args, view, rng):
        self.probe.unlink(args[0])
        if args[0] not in self.probe.delete_list:
            self.probe.delete_list.append(args[0])
        return Res()

    def on_libc_sprintf(self, args, view, rng):
        """The format with its one integer rendered (a sound or clip name)."""
        fmt, value = args[0], args[1]
        text = bytearray()
        while view.load(fmt + len(text), 1):
            text.append(view.load(fmt + len(text), 1))
        if value is not None and b'%d' in text:
            text = text.replace(b'%d', b'%d' % ee_emu.s32(value))
        return Res(outs=[bytes(text)])

    def on_SkillLifeTap_getStat0Fraction(self, args, view, rng):
        return Res(f=0)

    def on_player_getSkillRank(self, args, view, rng):
        return Res(0)

    # ---- construction and services -----------------------------------------------------
    def on_GameObject_ctor(self, args, view, rng):
        """GameObject_ctor (executed in ref_skills_a): position, class definition,
        properties, and the object's own generator from ONE shared draw."""
        obj, pos, class_def, props = args
        for i in range(3):
            view.poke(obj + 0x10 + 4 * i, 4, pos[i])
        view.poke(obj + 0xC, 4, 0)
        view.poke(obj + 0x24, 4, class_def)
        view.poke(obj + 0x2C, 4, props)
        seed = (rd(view, RC.G_RAND_SEED) * 0x19660D + 0x3C6EF35F) & M32
        view.poke(RC.G_RAND_SEED, 4, seed)
        view.poke(obj + 0x44, 4, seed)
        return Res()

    def on_pool_new(self, args, view, rng):
        """No block (the default), or with --pool a fresh zero-filled block as pool_new
        hands out (docs/spec/object-system.md); the object built in it does not run."""
        probe = self.probe
        if not probe.pool or probe.pool_used >= POOL_LIMIT:
            return Res(0)
        probe.pool_used += 1
        size = args[0] & M32
        probe.blocks[size] = probe.blocks.get(size, 0) + 1
        return Res(self.emu.alloc(max(size, 0x10)))

    def on_Creature_setStats(self, args, view, rng):
        c = args[0]
        view.poke(c + 0x228, 4, f32(HP))
        view.poke(c + 0x22C, 4, f32(HP))
        return Res()

    def on_res_find(self, args, view, rng):
        probe = self.probe
        if probe.disc is not None:              # --clips: the disc's own .anm / .vif entry
            def text(arg):                      # an address, or ('buf', text) a sprintf made
                if isinstance(arg, tuple) and len(arg) == 2 and isinstance(arg[1], (bytes, bytearray)):
                    return bytes(arg[1]).split(b'\0', 1)[0].decode('latin1')
                if not isinstance(arg, int):
                    return ''
                out = bytearray()
                while arg and view.load(arg + len(out), 1) and len(out) < 64:
                    out.append(view.load(arg + len(out), 1))
                return out.decode('latin1')
            addr = probe.load_entry(text(args[0]), text(args[1]))
            if addr is not None:
                return Res(addr)
        return Res(self.common.get(args[1], self.model))

    def on_model_buildHideMask(self, args, view, rng):
        return Res(0xFFFFFFFFFFFFFFFF)

    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(0)

    def on_obj_getPropInt(self, args, view, rng):
        return Res(0)

    def on_obj_getPropStr(self, args, view, rng):
        return Res(0)

    def on_net_objOrGhost(self, args, view, rng):
        return Res(args[0])

    def on_player_speedScale(self, args, view, rng):
        return Res(f=f32(1.0))

    def on_Creature_v16(self, args, view, rng):
        return Res(self.model)

    def on_Creature_v37(self, args, view, rng):
        return Res(rd(view, args[0] + 0x310, 1, True) & M32)

    # ---- geometry: flat dry ground at z = 0, no walls ------------------------------------
    def on_terrain_heightBelow(self, args, view, rng):
        return Res(f=f32(0.0))

    on_terrain_height = on_terrain_heightBelow

    def on_terrain_raycast(self, args, view, rng):
        return Res(f=f32(-1.0))

    on_world_raycast = on_terrain_raycast

    def on_world_slideMove(self, args, view, rng):
        pos, delta = args[0], args[1]
        for i in range(2):
            view.poke(pos + 4 * i, 4, f32(fl(rd(view, pos + 4 * i)) + fl(delta[i])))
        return Res(0, outs=[(0, 0, 0)])

    def on_world_findFreeSpot(self, args, view, rng):
        return Res(outs=[args[0], 1])

    def on_water_test(self, args, view, rng):
        return Res(0)

    def on_world_collectObjectsInBox(self, args, view, rng):
        """The query's contract (docs/spec/object-system.md 4.3, executed there): cells of
        the box grown by 96 in ascending row then column; an object counts when its x and y
        extents (+-radius +0x1c) and its height z .. z + +0x20 overlap the box; flags with
        g_excludeMask or 0x20000 skip it; at most limit - 1 results.  The probe's objects
        are all in grid A; within one cell they keep the probe's own order (AUTHORED)."""
        low, high, cap = [fl(v) for v in args[0]], [fl(v) for v in args[1]], args[2]

        def cell(v, bias):
            return min(max((int(v) + bias) >> 8, 0), 119)

        def cell_of(v):
            return min(max((int(v) + 0x3C00) >> 8, 0), 119)
        rows = (cell(low[1], 0x3BA0), cell(high[1], 0x3C60))
        cols = (cell(low[0], 0x3BA0), cell(high[0], 0x3C60))
        exclude = rd(view, RC.G_EXCLUDE_MASK)
        hits = []
        for index, obj in enumerate(self.probe.objects):
            x, y, z = [fl(rd(view, obj + 0x10 + 4 * i)) for i in range(3)]
            row, col = cell_of(y), cell_of(x)
            if not (rows[0] <= row <= rows[1] and cols[0] <= col <= cols[1]):
                continue
            flags = rd(view, obj + 0xC)
            if flags & exclude or flags & 0x20000:
                continue
            radius, height = fl(rd(view, obj + 0x1C)), fl(rd(view, obj + 0x20))
            if x + radius < low[0] or high[0] < x - radius:
                continue
            if y + radius < low[1] or high[1] < y - radius:
                continue
            if high[2] < z or z + height < low[2]:
                continue
            hits.append(((row, col, index), obj))
        found = [obj for _key, obj in sorted(hits)]
        return Res(outs=[found[:max(cap - 1, 0)]])

    # ---- handles and lists -------------------------------------------------------------
    def on_handle_link(self, args, view, rng):
        return DC.World.on_handle_link(self, args, view, rng)

    def on_handle_clear(self, args, view, rng):
        # handle +4 is an object's run-list link: clearing it leaves the list
        # (docs/spec/object-system.md 3, the destructor's step 4)
        if self.probe.where.get((args[0] - 4) & M32) is not None:
            self.probe.unlink((args[0] - 4) & M32)
        return DC.World.on_handle_clear(self, args, view, rng)

    def on_iter_begin(self, args, view, rng):
        return Res(0)

    def on_iter_next(self, args, view, rng):
        return Res(0)

    # ---- the clip clock (ref_combat_runtime.AnimTimeline, AUTHORED) -----------------------
    CLIP_TICKS = 20

    def _start(self, args, view, rng):
        anim = args[0]
        self.probe.clips[anim] = [args[1], 0]
        view.poke(anim + 4, 1, 1)
        view.poke(anim + 6, 2, 0x8)
        return Res()

    on_anim_push = on_anim_pushChained = on_anim_start = on_anim_startBlendInOut = _start
    on_anim_pushWithWeights = _start

    def on_anim_clear(self, args, view, rng):
        self.probe.clips.pop(args[0], None)
        view.poke(args[0] + 4, 1, 0)
        return Res()

    def on_anim_advance(self, args, view, rng):
        state, _sound, root, yaw = args[:4]
        view.poke(root, 4, 0)
        view.poke(root + 4, 4, 0)
        view.poke(yaw, 2, 0)
        entry = self.probe.clips.get(state)
        if entry is None:
            return Res(0)
        entry[1] += 1
        if entry[1] >= self.CLIP_TICKS:
            view.poke(state + 6, 2, (rd(view, state + 6, 2) & ~0x8 & 0xFFFF) | 0x80)
        return Res(0)


# Executed bodies the probe still answers as services: list bookkeeping and object
# construction whose executed bodies need the full object lists of tools/ref_objects.py.
KEEP_AS_SERVICE = {'GameObject_ctor', 'pool_new', 'pool_free', 'obj_runEveryFrame', 'obj_runEvery60',
                   'handle_link', 'handle_clear', 'handle_removeNode', 'obj_updateGridCell',
                   'obj_moveOffGrid', 'iter_begin', 'iter_next', 'iter_end',
                   # executed (skills); its skill object is the game's, which this world has
                   # not got: the stand-in player has no rank in it, so the answer is 0
                   'SkillLifeTap_getStat0Fraction'}
SERVICES |= KEEP_AS_SERVICE | {'obj_runEveryFrame', 'obj_runEvery60', 'obj_updateGridCell', 'obj_moveOffGrid',
                               'iter_end', 'lump_load'}


# Bodies not executed that the native World nevertheless records and answers, as it does
# for Gnaw (open-champions combat-ctors report, section 1): the weapon holder's slots 1 and
# 21 (slot 21 is presentation, D37) and Creature_init.  Counted apart from the services and
# from the unexecuted bodies; the probe does not stop on them.
RECORDED = {'Creature_init'}
# Holder slots 1 and 21 were recorded until their bodies were executed: slot 1 in round 3
# (tools/difftest_weapon_holder.py), slot 21 in round 4 (tools/difftest_holder_slots.py: no
# store outside the stack, no shared draw).  What slot 21 calls is presentation:
SERVICES |= {'fx_modelStatusEffects'}   # 0x1f6ac8: effect block and presentation tables, cosmetic seed only (FINDINGS D37)
SERVICES -= RECORDED


# ---------------------------------------------------------------------------------------
# --clips: the game's own animation code on the user's own clips
# ---------------------------------------------------------------------------------------
# Without --clips the probe's clip clock (World.on_anim_*) answers every animation call:
# 20 ticks per clip, no root motion, no events.  With --clips the animation bodies below
# run for real.  tools/difftest_anim.py executed each of them against tools/ref_anim.py on
# clips from the user's own disc (docs/spec/animation.md section 12; the property that
# reaches each is named).  The clips are the class definitions' and the skelcom block's own
# entries, read at run time from the user's disc image and relocated by the game's own
# anm_relocate; nothing of them is stored in this repository.  The event slots are what
# the constructors write (anm_setEventSlots / creature_setDefEntryParams, executed), and
# the root motion is what anim_advance extracts from the clip's joint 0.
ANIM_INIT, ANM_RELOCATE, ANIMSOUND_FIRE_RANGE = 0x16F9A8, 0x1707B8, 0x16D558
SKILL_STATIC_INIT, SKILL_INIT_STATS_ALL = 0x16AC74, 0x1EBCA0       # tools/difftest_skills_a.py
ANIM_BODIES = {
    0x16F9A8: 'anim_init (the set-up of every property; its pools are compared)',
    0x1707B8: 'anm_relocate (the set-up of every property; the clips are compared through the decoder)',
    0x16E468: 'animtrack_decode (decoder slot)', 0x16E388: 'animcache_alloc (decoder slot, advance)',
    0x16D748: 'anim_advance (advance)', 0x1162B0: 'Creature_stepAnim (Creature_stepAnim)',
    0x16CFE0: 'anim_start (advance)', 0x16CEB0: 'anim_startBlendInOut (advance)',
    0x170838: 'anim_push (advance)', 0x1708C0: 'anim_pushWithWeights (advance)',
    0x170938: 'anim_pushChained (advance)', 0x1707B0: 'anim_clear (advance)',
    0x1709F8: 'anim_syncToSimFrame (advance)', 0x16D0B8: 'anim_randomizeTopTime (advance)',
    0x170BC8: 'anim_jumpTopToEnd (advance)', 0x170C80: 'anim_snapTopToEnd (advance)',
    0x170D88: 'anim_findTrack (advance)', 0x171118: 'anim_releaseCaches (advance)',
    0x170E00: 'anim fade-in (advance)', 0x170EE8: 'anim fade-out (advance)',
    0x170FC8: 'anim_setTrackWeightRate (advance)',
    # the pose: the VU0 microprogram 0x3e5c50 runs in difftest_anim's own interpreter of its
    # instruction words (Vu0, install_cop2), installed here the same way
    0x16ED40: 'anim_buildPose (pose)', 0x16F720: 'anim_getJointMatrix (pose)',
}
# The game's model loader: mesh offsets become pointers (docs/formats/model-texture.md,
# Observed).  Not compared by any difftest; used only to set the world up, as the game's
# lump loader would, so that a body reading a model (a prop's hull table) reads the model.
MODEL_RELOCATE = 0x179130
# The sound events of a step: presentation (they play a sample and draw the cosmetic seed
# 0x404460, docs/spec/animation.md section 6).  difftest_anim stubs it too.
ANIM_SERVICES = {'animsound_fireRange'}
# Calls the report lists with the frame of their first call and their count: what tells a
# Skeleton reached its swing or released an arrow, and that damage was applied.
MILESTONES = {
    0x119938: 'Creature_hitTargetInArc', 0x119B58: 'Creature_hitAllEnemiesInArc',
    0x1196E8: 'Creature_hitTargetAtReach', 0x1E8230: 'damage_apply',
    0x150EE4: 'MissileWeapon_ctor', 0x2D6238: 'FireArrowProjectile_ctor',
    0x2D6FB4: 'ColdArrowProjectile_ctor', 0x2DAEB4: 'ExplodeArrowProjectile_ctor',
    0x116638: 'Creature_takeDamage', 0x2A7EF0: 'Skeleton_shatter',
    0x1B5330: 'Player_takeDamage',
}
# take-damage entries whose amount (f12) the report sums.  The stand-in player does not run
# its own tick, so what Player_takeDamage leaves for that tick never reaches +0x228.
TAKE_DAMAGE = {0x116638, 0x1B5330}
DEFAULT_DISC = os.path.expanduser('~/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso')


class DiscClips:
    """Clip files of the user's own disc image (or a directory of unpacked .LMP files),
    looked up as (lump name, entry name).  Read at run time only."""

    def __init__(self, path):
        import anim_audio_info as AI
        self.AI, self.path, self.lumps = AI, path, {}
        self.root = AI.open_path(path) if os.path.isfile(path) else None
        self.files = {}
        if self.root is not None:
            for name, blob in self.root.children() or ():
                self.files[name.rsplit('/', 1)[-1].upper()] = blob
        elif not os.path.isdir(path):
            raise FileNotFoundError(path)

    def lump(self, name):
        key = name.upper()
        if key not in self.lumps:
            if self.root is not None:
                blob = self.files.get(key)
                data = blob.bytes() if blob is not None else None
            else:
                hits = [f for f in os.listdir(self.path) if f.upper() == key]
                data = None
                if hits:
                    with open(os.path.join(self.path, hits[0]), 'rb') as f:
                        data = f.read()
            entries = {}
            if data is not None:
                for entry, off, size in self.AI.lmp_entries(data):
                    entries[entry.lower()] = data[off:off + size]
            self.lumps[key] = entries
        return self.lumps[key]

    def clip(self, lump, entry):
        return self.lump(lump).get(entry.lower())


# ---------------------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------------------
class Probe:
    def __init__(self, elf, kind, placement='round5', serial=0, stop_first=True, executed=None, pool=False,
                 type_name=None, clips=None, skills=False):
        self.kind, self.stop_first = kind, stop_first
        self.pool, self.pool_used, self.blocks = pool, 0, {}
        self.type_name = type_name
        self.executed = executed if executed is not None else executed_bodies()
        self.disc = clips
        self.clip_names = {}                    # clip address -> entry name (--clips)
        self.loaded_entries, self.clips_missing = {}, []
        self.elf, self.scratch = elf, None
        if clips is not None:
            self.executed = dict(self.executed)
            for addr, prop in ANIM_BODIES.items():
                self.executed.setdefault(addr, 'difftest_anim %s' % prop)
        self.symbols = symbol_names()
        self.events, self.first_seen, self.defaulted, self.clips = [], {}, {}, {}
        self.milestones, self.track = {}, []
        self.run_objects = False
        self.run_lists = {'frame': [], 15: [[] for _ in range(15)], 60: [[] for _ in range(60)]}
        self.cursor = {15: 0, 60: 0}
        self.where, self.delete_list, self.objects_run, self.destroyed = {}, [], {}, 0
        self.tick = -1
        self.states = []
        saved = DCT.World
        DCT.World = World
        try:
            rig = self.rig = DCT.Rig(elf, 20973, kind, 0, 0)
        finally:
            DCT.World = saved
        emu, world, mem = rig.emu, rig.world, rig.emu.mem
        if skills:
            self._build_skills()
        world.probe = self
        rig.script_rng = random.Random(0)
        emu.unpatch()                           # the run switches run for real here
        # The world's fixture handles (model 0x00c00040, the on-kill skill 0x00c00100, resources
        # 0x00c00200) point into a page nothing backs.  Executed bodies that read the model
        # (creature_dropHeldPartAsProp at a death) get zeros there (AUTHORED, like the rest).
        mem.map(FIXTURE_PAGE, 0x1000)
        self.name_of = {}
        for addr, name in rig.names.items():
            self.name_of[addr] = name
        # every executed body runs for real unless it is kept as a service
        self.runtime = set(TYPEINFO.values()) | {a for a, n in self.symbols.items() if n.endswith('_typeinfo')}
        self.tables = dict(TABLES)
        for addr, name in list(rig.names.items()):
            if addr in self.executed and name not in KEEP_AS_SERVICE:
                emu.unhook(addr)
        emu.follow = self
        # the switch hooks
        run_key = {'antqueen': 'AntQueen_run', 'skeleton': 'Skeleton_run', 'soul': 'Soul_run'}[kind]
        self.run_key = run_key
        entry, test = RUN_SWITCHES[run_key]
        self.run_entry = entry
        emu.hook(test, self._switch_hook)
        self.starts = function_starts()
        self.allowed = set(self.runtime) | {entry for entry, _test in RUN_SWITCHES.values()}
        emu.trace = []
        if clips is not None:
            self._load_clips()
        self.place(placement, serial)

    def _build_skills(self):
        """--skills: the game's own start-up initialiser builds the 101 Skill objects and
        their statistics, as tools/difftest_skills_a.py does (0x16ac74 (1, 0xffff), then
        0x1ebca0), before the probe takes over the world.  Without it g_skillTable
        0x41b170 is empty, and a body that reads a skill object (the AntQueen's state 7
        and 9 strikes read SkillPoisonWeapons, g_skillTable[26]) reads address 0."""
        emu = self.rig.emu
        # the creature world's two fixture objects (difftest_creature: burn 0x41b1a4, on-kill
        # 0x41b25c) have no virtual table; the game's own objects take their places
        for addr in (RC.G_SKILL_BURN, RC.G_SKILL_ONKILL):
            emu.mem.w32(addr, 0)
        follow, record = emu.follow, emu.record_calls
        emu.follow, emu.record_calls = None, False
        hooks = dict(emu.hooks)
        emu.hooks.clear()
        try:
            emu.r[29] = emu.stack_hi - 0x100
            emu.call(SKILL_STATIC_INIT, 1, 0xFFFF, max_steps=MAX_STEPS)
            emu.r[29] = emu.stack_hi - 0x100
            emu.call(SKILL_INIT_STATS_ALL, max_steps=MAX_STEPS)
        finally:
            emu.hooks.update(hooks)
            emu.follow, emu.record_calls = follow, record
            emu.reset_log()

    def load_entry(self, lump, entry):
        """An `.anm` or `.vif` entry of the user's disc, copied in and relocated by the
        game's own anm_relocate / model_relocate; None for other kinds or when missing."""
        relocate = {'.anm': ANM_RELOCATE, '.vif': MODEL_RELOCATE}.get(entry.lower()[-4:])
        if relocate is None or self.disc is None:
            return None
        key = (lump.lower(), entry.lower())
        if key not in self.loaded_entries:
            data = self.disc.clip(lump, entry)
            if data is None:
                self.clips_missing.append('%s::%s' % key)
                self.loaded_entries[key] = None
            else:
                # The relocation runs on a scratch interpreter, never on the probe's own: a
                # load is often asked for inside a stub's answer (res_find), where a nested
                # call would wreck the interrupted function.  The relocated bytes are copied
                # back; a store outside the file would be refused.
                emu = self.rig.emu
                size = len(data) + 0x40
                addr = emu.alloc(size)
                if self.scratch is None:
                    self.scratch = EE(self.elf)
                    self.scratch.record_calls = False
                sc = self.scratch
                sc.mem.map(addr, size)
                sc.mem.write(addr, bytes(data) + bytes(0x40))
                sc.reset_log()
                sc.record_writes = True
                sc.call(relocate, addr, max_steps=MAX_STEPS)
                stray = [w for w in sc.writes if not addr <= w[1] < addr + size]
                if stray:
                    raise EmuError('relocating %s::%s stored outside it at %#x' % (lump, entry, stray[0][1]))
                emu.mem.write(addr, bytes(sc.mem.read(addr, size)))
                self.loaded_entries[key] = addr
                self.clip_names[addr] = entry
        return self.loaded_entries[key]

    def _load_clips(self):
        """--clips: the game's anim_init sets up the decoder slots and pose buffers; every
        `.anm` entry of the probed class's definitions and of the skelcom block is read from
        the user's disc, copied in and relocated by the game's anm_relocate, and put where
        res_find would have put it.  Entries whose lump or file is missing keep the
        world's stand-in record and are counted."""
        emu, mem, world = self.rig.emu, self.rig.emu.mem, self.rig.world
        probe = self

        def fire_range(e):
            probe.note_stub('animsound_fireRange', 'service', ())
            return 0
        emu.stub(ANIMSOUND_FIRE_RANGE, function=fire_range, name='animsound_fireRange')
        emu.r[29] = emu.stack_hi - 0x100
        emu.call(ANIM_INIT, max_steps=MAX_STEPS)
        import difftest_anim as DAN
        self.vu = DAN.Vu0(emu)
        DAN.install_cop2(emu, self.vu)

        def cstr(addr):
            out = bytearray()
            while addr and mem.u8(addr + len(out)) and len(out) < 64:
                out.append(mem.u8(addr + len(out)))
            return out.decode('latin1')

        loaded, self.clips_missing = self.loaded_entries, []

        def resolve(block, k):
            return self.load_entry(cstr(mem.u32(block)), cstr(mem.u32(block + 8 * k)))

        blocks = [d for d, _first, _end in DCT.CLASSES[self.kind]['defs']]
        if self.kind == 'skeleton':
            blocks.append(CT.SKEL_COMMON)
        for block in blocks:
            k = 1
            while mem.u32(block + 8 * k) and k < 0x80:
                addr = resolve(block, k)
                if addr is not None:
                    name_ptr = mem.u32(block + 8 * k)
                    mem.w32(block + 8 * k + 4, addr)
                    if block == CT.SKEL_COMMON:
                        world.common[name_ptr] = addr
                k += 1
        self.clips_loaded = sum(1 for a in loaded.values() if a)
        # the definitions' model entry (+0xc) too
        for block in blocks:
            if block != CT.SKEL_COMMON:
                addr = self.load_entry(cstr(mem.u32(block)), cstr(mem.u32(block + 8)))
                if addr is not None:
                    mem.w32(block + 0xC, addr)

    # ---- run lists (AUTHORED copy of runObjects 0x14b910, docs/spec/object-system.md 5.4)
    def link(self, obj, which):
        """obj_runEveryFrame / obj_runEvery60 / obj_runEvery15: leave the current list,
        then join the front of the new one (a slow list steps its cursor first)."""
        self.unlink(obj)
        if which == 'frame':
            lst = self.run_lists['frame']
        else:
            self.cursor[which] = (self.cursor[which] + 1) % which
            lst = self.run_lists[which][self.cursor[which]]
        lst.insert(0, obj)
        self.where[obj] = lst

    def unlink(self, obj):
        lst = self.where.pop(obj, None)
        if lst is not None and obj in lst:
            lst.remove(obj)

    def _vcall(self, obj, slot, *args):
        """A virtual call the engine makes (slot 4 run, slot 1 destroy): runs when the
        body is executed, else it is an unexecuted stop."""
        mem = self.rig.emu.mem
        table = mem.u32(obj + 0x48)
        fn = mem.u32(table + 8 * slot + 4)
        this = (obj + mem.s16(table + 8 * slot)) & M32
        if fn not in self and fn not in self.rig.emu.hooks:
            self.note_stub('%s (slot %d of a pool object, table %#x)' % (self.label(fn), slot, table),
                           'unexecuted', ())
            return
        key = self.label(fn)
        self.objects_run[key] = self.objects_run.get(key, 0) + 1
        self._call(fn, this, *args)

    def run_pool_objects(self, frame, lists):
        """Every object the probe's pool built that is on the walked lists, front to back;
        the probed creature and the stand-ins are run (or not) by the probe itself."""
        mem, skip = self.rig.emu.mem, set(self.objects)
        walk = []
        for which in lists:
            if which == 'frame':
                walk += list(self.run_lists['frame'])
            else:
                walk += list(self.run_lists[which][frame % which])
        for obj in walk:
            if obj in skip or self.where.get(obj) is None or mem.u32(obj + 0xC) & 0x8000:
                continue
            self._vcall(obj, 4)

    def flush_deletes(self):
        """runObjects step 1: slot 1 with argument 3, last deleted first."""
        pending, self.delete_list = list(reversed(self.delete_list)), []
        for obj in pending:
            if obj in self.objects:
                continue
            self._vcall(obj, 1, 3)
            self.destroyed += 1

    def _functions_run(self, pcs):
        import bisect
        out = set()
        for pc in pcs:
            i = bisect.bisect_right(self.starts, pc) - 1
            if i >= 0:
                out.add(self.starts[i])
        return out

    # emu.follow protocol: the callee runs for real when it is executed or a C library body
    def __contains__(self, target):
        return target in self.executed or target in self.runtime or DC.LIB_LO <= target < DC.LIB_HI

    def label(self, addr):
        name = self.name_of.get(addr)
        if name is None or name.startswith(('Creature.v', 'Holder.v')) and addr in self.symbols:
            name = self.symbols.get(addr, name)
        return name or 'fn_%06x' % addr

    def classify_name(self, name):
        if name in SERVICES:
            return 'service'
        if name in RECORDED:
            return 'recorded'
        return 'unexecuted'

    def note_stub(self, name, cls, args):
        if name not in self.first_seen:
            self.first_seen[name] = (self.tick, cls)
        if cls == 'unexecuted':
            self.events.append((self.tick, name))
            if self.stop_first:
                raise Stop('%s at tick %d' % (name, self.tick))

    def _switch_hook(self, emu):
        c = self.world.C
        state = self.rig.emu.mem.s16(c + 0x232)
        if not self.states or self.states[-1][1] != state:
            self.states.append((self.tick, state))
            mem = self.rig.emu.mem
            self.track.append((self.tick, state, mem.f32(c + 0x10), mem.f32(c + 0x14)))
        if state not in RUN_STATES_EXECUTED[self.run_key] and 0 <= state < 0x40:
            name = '%s state %#x' % (self.run_key, state)
            self.note_stub(name, 'unexecuted', ())

    # ---- set-up --------------------------------------------------------------------------
    @property
    def world(self):
        return self.rig.world

    def place(self, placement, serial):
        rig, world = self.rig, self.rig.world
        emu, mem = rig.emu, rig.emu.mem
        spots = PLACEMENTS[placement]
        mem.w32(RC.G_SIM_FRAME, 0)
        world.set_level(LEVEL)
        mem.w32(RC.G_RAND_SEED, 0)
        order = ('antqueen', 'skeleton', 'soul')          # the native placement order
        mem.w8(0x4F85C4, (serial + order.index(self.kind)) & 0xFF)
        mem.w32(RC.G_NUM_PLAYERS, 1)
        self.objects = []
        # the player
        P = world.players[0]
        self._stand_in(P, (0, 0), 0, 0x60, 0, 'player')
        rec = RC.G_PLAYERS
        mem.w32(rec + RC.REC_OBJ, P)
        mem.w8(rec + 0x4C24, 0)
        mem.wf32(rec + 0xAC, 100.0)
        mem.wf32(rec + 0xB0, 100.0)
        for slot in range(1, 4):
            mem.w32(RC.G_PLAYERS + slot * RC.REC_SIZE + RC.REC_OBJ, 0)
        self.objects.append(P)
        # the two Skelights and the other two classes as stand-ins
        others = list(world.others)
        for (x, y), facing in SKELIGHTS:
            o = others.pop(0)
            self._stand_in(o, (x, y), facing, 0x20, 0xFF, 'skelight')
            self.objects.append(o)
        for kind, (x, y) in spots.items():
            if kind == self.kind or placement == 'duel':
                continue
            o = others.pop(0)
            self._stand_in(o, (x, y), FACING, 0x20, 0 if kind == 'soul' else 0xFF, kind)
            self.objects.append(o)
        for o in others:
            mem.w32(o + 0xC, 8)                 # unused blocks: dead, excluded from queries
            mem.wf32(o + 0x10, 50000.0)
        # the probed creature, by its own constructor
        c = world.C
        world.clear_creature()
        x, y = spots[self.kind]
        pos = world.argbuf
        for i, v in enumerate((float(x), float(y), 0.0)):
            mem.wf32(pos + 4 * i, v)
        name = emu.alloc(32)
        mem.write(name, (self.type_name or TYPE_NAMES[self.kind]) + b'\0')
        emu.r[29] = emu.stack_hi - 0x100
        ctor = {'antqueen': (0x236C70, (c, name, pos, FACING, world.props)),
                'skeleton': (0x2A5AF4, (c, pos, FACING, world.props, name, 0)),
                'soul': (0x2A9478, (c, name, pos, FACING, world.props, 0))}[self.kind]
        self.ctor_error = None
        try:
            self._call(ctor[0], *ctor[1])
        except Stop as exc:
            self.ctor_error = exc
        mem.wf32(c + 0x228, HP)
        mem.wf32(c + 0x22C, HP)
        self.objects.append(c)
        self.serial = mem.u8(c + 0x230)

    def _stand_in(self, o, xy, facing, flags, team, kind, hp=HP):
        mem, world = self.rig.emu.mem, self.rig.world
        mem.w32(o + 0xC, flags)
        mem.wf32(o + 0x10, float(xy[0]))
        mem.wf32(o + 0x14, float(xy[1]))
        mem.wf32(o + 0x18, 0.0)
        mem.wf32(o + 0x1C, 16.0 if flags & 0x40 else 12.0)
        mem.wf32(o + 0x20, 72.0)
        mem.w16(o + 0x38, facing)
        mem.w32(o + 0x48, self.tables[kind])
        mem.w64(o + 0xA8, 0)
        mem.wf32(o + 0x228, hp)
        mem.wf32(o + 0x22C, hp)
        mem.w8(o + 0x310, team)
        mem.w32(o + 0x4C, 0)
        # idle: no last move (Creature_moveBy's +0x308 / +0x30c).  The difftest worlds the
        # blocks come from leave random values there, which a bow's lead point reads
        mem.w32(o + 0x308, 0)
        mem.w32(o + 0x30C, 0)

    def _call(self, addr, *args, fargs=()):
        emu = self.rig.emu
        emu.reset_log()
        emu.r[29] = emu.stack_hi - 0x100
        ints = [ee_emu.s32(a & M32) for a in args]
        for k, raw in enumerate(fargs):
            emu.f[12 + k] = raw & M32
        emu.trace = []
        try:
            return emu.call(addr, *ints, max_steps=MAX_STEPS)
        finally:
            for fn in sorted(self._functions_run(set(emu.trace))):
                if fn in self.allowed or fn in self or fn in emu.hooks:
                    continue
                name = self.label(fn)
                if self.classify_name(name) != 'unexecuted':
                    continue
                name += ' (entered by a jump)'
                if name not in self.first_seen:
                    self.first_seen[name] = (self.tick, 'unexecuted')
                    self.events.append((self.tick, name))
            for rec in emu.calls:
                if rec.target in MILESTONES:
                    seen = self.milestones.setdefault(rec.target, [self.tick, 0, 0.0])
                    seen[1] += 1
                    if rec.target in TAKE_DAMAGE:           # the amount, in f12
                        seen[2] += fl(rec.fargs[0])
                if rec.target not in self and rec.target not in emu.hooks:
                    name = self.label(rec.target)
                    self.note_stub(name, self.classify_name(name), ())

    # ---- ticks ---------------------------------------------------------------------------
    def hit(self, amount, flags=1):
        """The player hits the creature: its own virtual slot 2 (attacker, flags; amount),
        as damage_apply's take-damage call makes it (AUTHORED stand-in for the attacking
        player of the native smoke test)."""
        mem, c = self.rig.emu.mem, self.world.C
        table = mem.u32(c + 0x48)
        fn = mem.u32(table + 8 * 2 + 4)
        this = (c + mem.s16(table + 8 * 2)) & M32
        if fn not in self and fn not in self.rig.emu.hooks:
            self.note_stub(self.label(fn), 'unexecuted', ())
        self._call(fn, this, self.world.players[0], flags, fargs=(f32(amount),))

    def run(self, ticks, hit_every=0, hit_amount=10.0):
        mem, c = self.rig.emu.mem, self.world.C
        self.stopped = self.ctor_error
        if self.stopped:
            return self
        gone = False
        for tick in range(ticks):
            self.tick = tick
            mem.w32(RC.G_SIM_FRAME, tick)
            try:
                if hit_every and tick % hit_every == hit_every - 1 and not gone:
                    self.hit(hit_amount)
                if self.run_objects:                # objects linked after the creature run first
                    self.flush_deletes()
                    self.run_pool_objects(tick, ('frame',))
                if not gone:
                    self._call(self.run_entry, c)
                if self.run_objects:
                    self.run_pool_objects(tick, (15, 60))
            except Stop as exc:
                self.stopped = exc
                break
            except EmuError as exc:
                self.stopped = 'emulator: %s' % exc
                break
            if not gone and mem.u32(c + 0xC) & 0x4000:
                self.events.append((tick, 'deleted'))
                self.deleted_at = tick
                gone = True
                if not self.run_objects:    # with --run-objects what it left keeps running
                    break
        return self


# ---------------------------------------------------------------------------------------
def report(probe):
    print('%s on the %s placement:' % (probe.kind, probe.placement))
    if probe.kind == 'skeleton':
        mem, c = probe.rig.emu.mem, probe.world.C
        print('  type %s, weapon kind +0x3d0 = %d' % ((probe.type_name or TYPE_NAMES['skeleton']).decode(),
                                                      mem.u32(c + 0x3D0)))
    print('  serial %d; states entered (frame:state): %s' % (probe.serial, ', '.join('%d:%#x' % s for s in probe.states[:24])))
    if probe.disc is not None:
        print('  clips and models: %d relocated from the disc (anim bodies real)%s' % (
            sum(1 for a in probe.loaded_entries.values() if a), '; missing: %s' % ', '.join(probe.clips_missing) if probe.clips_missing else ''))
        mem, c = probe.rig.emu.mem, probe.world.C
        print('  position at state changes (frame:state @ x,y): %s' % ', '.join(
            '%d:%#x@%.0f,%.0f' % t for t in probe.track[:24]))
        x, y = mem.f32(c + 0x10), mem.f32(c + 0x14)
        print('  final position (%.1f, %.1f), %.1f from the player' % (x, y, (x * x + y * y) ** 0.5))
    mem = probe.rig.emu.mem
    print('  player hit points +0x228: %.1f of %.1f' % (mem.f32(probe.world.players[0] + 0x228), HP))
    for addr, (tick, count, amount) in sorted(probe.milestones.items(), key=lambda kv: kv[1][0]):
        print('  milestone  %-40s first at frame %d, %d calls%s' % (
            MILESTONES[addr], tick, count, ', amounts %.1f in all' % amount if addr in TAKE_DAMAGE else ''))
    if probe.stopped:
        print('  STOP: %s' % probe.stopped)
    seen = sorted(probe.first_seen.items(), key=lambda kv: (kv[1][0], kv[0]))
    for name, (tick, cls) in seen:
        if cls != 'service':
            print('  %-10s %-40s first at frame %d (ready tick %d)' % (cls, name, tick, tick + 1))
    services = sorted(n for n, (_t, c) in probe.first_seen.items() if c == 'service')
    print('  services answered: %s' % ', '.join(services))
    if getattr(probe, 'deleted_at', None) is not None:
        print('  the creature deleted itself at frame %d%s' % (
            probe.deleted_at, '; the objects it left ran on' if probe.run_objects else ''))
    if probe.objects_run:
        print('  pool objects run (slot: calls): %s; destroyed %d' % (
            ', '.join('%s x%d' % kv for kv in sorted(probe.objects_run.items())), probe.destroyed))
    if probe.blocks:
        print('  pool blocks handed out (size x count): %s' % ', '.join('%#x x%d' % kv for kv in sorted(probe.blocks.items())))
    if probe.defaulted:
        print('  answered 0 by default: %s' % ', '.join('%s x%d' % kv for kv in sorted(probe.defaulted.items())))


def main(argv):
    args = list(argv)
    elf, ticks, kinds, serial, placement, stop_first = None, 300, ('antqueen', 'skeleton', 'soul'), 0, 'round5', True
    hit_every, hit_amount, pool, type_name, clips_path, skills = 0, 10.0, False, None, None, False
    run_objects = False
    while args:
        a = args.pop(0)
        if a == '--ticks':
            ticks = int(args.pop(0), 0)
        elif a == '--class':
            kinds = (args.pop(0).lower(),)
        elif a == '--serial':
            serial = int(args.pop(0), 0)
        elif a == '--placement':
            placement = args.pop(0)
        elif a == '--all':
            stop_first = False
        elif a == '--pool':
            pool = True
        elif a == '--type':
            type_name = args.pop(0).encode()
        elif a == '--hit-every':
            hit_every = int(args.pop(0), 0)
        elif a == '--hit-amount':
            hit_amount = float(args.pop(0))
        elif a == '--skills':
            skills = True
        elif a == '--run-objects':
            run_objects = pool = True
        elif a == '--clips':
            clips_path = args.pop(0) if args and not args[0].startswith('--') and not args[0].endswith('.73') \
                else DEFAULT_DISC
        else:
            elf = a
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('probe_full_placement: SLUS_209.73 not found - nothing to probe (this is not a failure)')
        return 0
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != DC.EXPECTED_SHA256:
        print('probe_full_placement: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    RC.C.set_fpu(DC.OPTIONS['fpu'])
    executed = executed_bodies()
    disc = None
    if clips_path is not None:
        if not os.path.exists(clips_path):
            print('probe_full_placement: --clips: %s not found - the clip clock answers instead' % clips_path)
        else:
            disc = DiscClips(clips_path)
    for kind in kinds:
        probe = Probe(elf, kind, placement, serial, stop_first, executed, pool, type_name, disc, skills)
        probe.placement = placement
        probe.run_objects = run_objects
        probe.run(ticks, hit_every, hit_amount)
        report(probe)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
