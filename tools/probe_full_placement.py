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
                   at (-60, 100) as it is now (ed062c3).  Default round5.
    --all          do not stop at the first unexecuted body: answer it with 0 and go on,
                   so the run lists every one it meets, with the tick of its first call

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
             'ref_combat_ctors2', 'ref_antqueen_run', 'ref_fire_touch')
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
    return out


# Executed bodies whose module keeps no address table.
EXECUTED_ELSEWHERE = {
    0x1E8230: 'ref_combat.damage_apply (tools/difftest_combat.py)',
}


# The run functions' switches: entry -> (address of the range test, jump-table base,
# states whose arm a difftest has executed).  Round 5 executed states 0 and 1 of AntQueen
# and Skeleton and the Soul phase gate (docs/spec/combat-round5.md).
RUN_SWITCHES = {
    'AntQueen_run': (0x236F78, 0x237004),
    'Skeleton_run': (0x2A6864, 0x2A6954),
    'Soul_run': (0x2A9870, 0x2A997C),
}
RUN_STATES_EXECUTED = {
    'AntQueen_run': {0, 1},
    'Skeleton_run': {0, 1},
    'Soul_run': set(),
}

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
}


PLACEMENTS = {
    'round5': {'antqueen': (0, 140), 'skeleton': (70, 140), 'soul': (-70, 140)},
    'native': {'antqueen': (0, 140), 'skeleton': (70, 140), 'soul': (-60, 100)},
}
SKELIGHTS = (((80, 0), 0x8000), ((-40, 0), 0))
FACING = 0xC000
LEVEL = b'drunare'                      # any level but airhub (the Soul class tests that name)
HP = 120.0
TYPE_NAMES = {'antqueen': b'AntQueen', 'skeleton': b'Skeleton', 'soul': b'Soul'}
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
        cls = probe.classify_name(name)
        probe.note_stub(name, cls, args)
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
    }

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
        return Res(0)                           # no effect objects: reported by the caller

    def on_Creature_setStats(self, args, view, rng):
        c = args[0]
        view.poke(c + 0x228, 4, f32(HP))
        view.poke(c + 0x22C, 4, f32(HP))
        return Res()

    def on_res_find(self, args, view, rng):
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
        low, high, cap = args[0], args[1], args[2]
        found = []
        exclude = rd(view, RC.G_EXCLUDE_MASK)
        for obj in self.probe.objects:
            if rd(view, obj + 0xC) & exclude:
                continue
            p = [fl(rd(view, obj + 0x10 + 4 * i)) for i in range(3)]
            if all(fl(low[i]) <= p[i] <= fl(high[i]) for i in range(3)):
                found.append(obj)
        return Res(outs=[found[:cap]])

    # ---- handles and lists -------------------------------------------------------------
    def on_handle_link(self, args, view, rng):
        return DC.World.on_handle_link(self, args, view, rng)

    def on_handle_clear(self, args, view, rng):
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
                   'obj_moveOffGrid', 'iter_begin', 'iter_next', 'iter_end'}
SERVICES |= KEEP_AS_SERVICE | {'obj_runEveryFrame', 'obj_runEvery60', 'obj_updateGridCell', 'obj_moveOffGrid',
                               'iter_end', 'lump_load'}


# Bodies not executed that the native World nevertheless records and answers, as it does
# for Gnaw (open-champions combat-ctors report, section 1): the weapon holder's slots 1 and
# 21 (slot 21 is presentation, D37) and Creature_init.  Counted apart from the services and
# from the unexecuted bodies; the probe does not stop on them.
RECORDED = {'Holder.v1', 'Holder.v21', 'Creature_init'}
SERVICES -= RECORDED


# ---------------------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------------------
class Probe:
    def __init__(self, elf, kind, placement='round5', serial=0, stop_first=True, executed=None):
        self.kind, self.stop_first = kind, stop_first
        self.executed = executed if executed is not None else executed_bodies()
        self.symbols = symbol_names()
        self.events, self.first_seen, self.defaulted, self.clips = [], {}, {}, {}
        self.tick = -1
        self.states = []
        saved = DCT.World
        DCT.World = World
        try:
            rig = self.rig = DCT.Rig(elf, 20973, kind, 0, 0)
        finally:
            DCT.World = saved
        emu, world, mem = rig.emu, rig.world, rig.emu.mem
        world.probe = self
        rig.script_rng = random.Random(0)
        emu.unpatch()                           # the run switches run for real here
        self.name_of = {}
        for addr, name in rig.names.items():
            self.name_of[addr] = name
        # every executed body runs for real unless it is kept as a service
        self.runtime = set(TYPEINFO.values())
        self.tables = {}
        for kind_, getter in TYPEINFO.items():         # a base Creature table per stand-in kind
            table = emu.alloc(8 * 48)
            for k in range(0, 8 * 48, 4):
                mem.w32(table + k, mem.u32(world.vt_base + k))
            mem.w32(table + 4, getter)
            self.tables[kind_] = table
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
        self.place(placement, serial)

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
        return self.name_of.get(addr) or self.symbols.get(addr) or 'fn_%06x' % addr

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
            if kind == self.kind:
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
        mem.write(name, TYPE_NAMES[self.kind] + b'\0')
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

    def _call(self, addr, *args):
        emu = self.rig.emu
        emu.reset_log()
        emu.r[29] = emu.stack_hi - 0x100
        ints = [ee_emu.s32(a & M32) for a in args]
        emu.trace = []
        try:
            return emu.call(addr, *ints, max_steps=4000000)
        finally:
            for fn in sorted(self._functions_run(set(emu.trace))):
                if fn in self.allowed or fn in self or fn in emu.hooks:
                    continue
                name = self.label(fn) + ' (entered by a jump)'
                if name not in self.first_seen:
                    self.first_seen[name] = (self.tick, 'unexecuted')
                    self.events.append((self.tick, name))
            for rec in emu.calls:
                if rec.target not in self and rec.target not in emu.hooks:
                    name = self.label(rec.target)
                    self.note_stub(name, 'unexecuted', ())

    # ---- ticks ---------------------------------------------------------------------------
    def run(self, ticks):
        mem, c = self.rig.emu.mem, self.world.C
        self.stopped = self.ctor_error
        if self.stopped:
            return self
        for tick in range(ticks):
            self.tick = tick
            mem.w32(RC.G_SIM_FRAME, tick)
            try:
                self._call(self.run_entry, c)
            except Stop as exc:
                self.stopped = exc
                break
            except EmuError as exc:
                self.stopped = 'emulator: %s' % exc
                break
            if mem.u32(c + 0xC) & 0x4000:
                self.events.append((tick, 'deleted'))
                break
        return self


# ---------------------------------------------------------------------------------------
def report(probe):
    print('%s on the %s placement:' % (probe.kind, probe.placement))
    print('  serial %d; states entered (frame:state): %s' % (probe.serial, ', '.join('%d:%#x' % s for s in probe.states[:24])))
    if probe.stopped:
        print('  STOP: %s' % probe.stopped)
    seen = sorted(probe.first_seen.items(), key=lambda kv: (kv[1][0], kv[0]))
    for name, (tick, cls) in seen:
        if cls != 'service':
            print('  %-10s %-40s first at frame %d (ready tick %d)' % (cls, name, tick, tick + 1))
    services = sorted(n for n, (_t, c) in probe.first_seen.items() if c == 'service')
    print('  services answered: %s' % ', '.join(services))
    if probe.defaulted:
        print('  answered 0 by default: %s' % ', '.join('%s x%d' % kv for kv in sorted(probe.defaulted.items())))


def main(argv):
    args = list(argv)
    elf, ticks, kinds, serial, placement, stop_first = None, 300, ('antqueen', 'skeleton', 'soul'), 0, 'round5', True
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
    for kind in kinds:
        probe = Probe(elf, kind, placement, serial, stop_first, executed)
        probe.placement = placement
        probe.run(ticks)
        report(probe)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
