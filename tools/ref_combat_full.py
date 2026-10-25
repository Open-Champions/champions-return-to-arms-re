#!/usr/bin/env python3
"""ref_combat_full.py - the round-2 combat contract in ONE world: every executed body of
the six round-2 modules on one model, and one runtime whose player slot 4 is the real
player tick.  docs/combat-runtime.md (round 2 section) is the prose.

A research tool, not game code.  Standard library only; no game data is embedded.

What is composed (each body's evidence is in its own module and difftest)
    tools/ref_combat_move.py      MoveModel      obj_moveWithCollision, creature_moveSimple,
                                                 Player_move (all modes), Player_animStep,
                                                 Player_clampToScreen
    tools/ref_combat_melee.py     MeleeModel     Player_pickAttackAnim, Player_meleeHit (all
                                                 branches), Player_hitSparks, slot 16
    tools/ref_combat_ptick.py     DefenceModel   Player_takeDamage (block, Holy Shield),
                                                 Player_processDamage (knock-down, blood ...),
                                                 Player_blockSparks, Player_interact
    tools/ref_combat_ranged.py    RangedModel    obj_moveAndCollide, the projectile
                                                 constructors, runs, touch and destructors
    tools/ref_combat_monsters.py  MonsterCombatModel  sight / hit / cooldown helpers,
                                                 world_notifyObjectsNear, Creature_deadUpdate
                                                 (decal), Creature_dropLoot, destructors
    tools/ref_combat_spells.py    QueryModel     world_collectObjectsInArc /
                                                 collectInSphere / damageInRadius, the
                                                 effect destructors

FullModel merges their tables explicitly (each area model's call() jumps straight to
ref_combat_runtime.CombatModel.call, so inheritance alone would lose bodies) and checks at
import that no two areas give the same name or the same function two different bodies.

FullRuntime is one world (ref_combat_runtime.Runtime) with:
    slot 4 of a player   ref_player.Tick.run (Player_run 0x1a5030, executed by
                         tools/difftest_player.py) - TickRuntime's composition - with
                         Player_move / Player_animStep  = MoveModel (executed)
                         Player_meleeHit / pickAttackAnim / hitSparks = MeleeModel (executed)
                         Player_processDamage / takeDamage = DefenceModel (executed)
    projectiles          RangedRuntime's spawn_missile / spawn_thrown (AUTHORED call sites,
                         EXECUTED constructors), runs, touches, self-destruction
    spells               SpellRuntime's give_skill / queue_cast (AUTHORED cast point: here
                         just before the caster's tick tail, where Player_run state 5 would
                         call Player_castSkill), the skill models of ref_skills_a/b/c
    monsters             MonsterCombatModel's helpers on the model; destruction stays
                         round 1's Runtime._slot1 (its order is the executed one,
                         docs/spec/combat-monster-death.md 4)
Everything else is answered by the fixtures and refusals of the area runtimes; a name no
area answers is refused (ref_combat_runtime.Services).  Round 1's Runtime is unchanged.

Conflicts between the areas and how they are resolved (AUTHORED choices of this module)
    GameObject_dtor, Creature_dtor   MonsterCombatModel maps them to its executed bodies;
                     the projectile and effect destructors reach them as call-outs that the
                     shared world must answer (the object leaves the world's lists and
                     pool).  FullModel keeps them call-outs; the methods stay available.
    DTORS            RangedModel: a tuple (the two projectile destructors routed to the
                     runtime); QueryModel: a dict (the effect destructors).  FullModel.DTORS
                     is the dict; the projectile pair is RANGED_DTORS.
    type-info names  RangedRuntime writes the descriptors' name words in the mangled form
                     ('8Creature'), MeleeRuntime in plain form ('Creature') on first use.
                     Both are authored fixtures; rtti_typeInfoEquals only compares names, so
                     one form is used: the mangled one, for every descriptor of both tables.
                     Virtual slot 0 is answered from the union of the two tables by the
                     object's own getter (MeleeRuntime's answer used the last melee target).
    res_find         TickRuntime answers a token (animations, sounds of the tick);
                     RangedRuntime 0 for its effect lumps (given as text): by the form of
                     the lump argument.
    GameObject_ctor, GameObject_dtor, pool_free, damage_apply
                     by the object: a projectile's go to RangedRuntime's, others to
                     SpellRuntime's; damage_apply with a weapon item to MeleeRuntime's,
                     a projectile as attacker refused, everything else SpellRuntime's
                     (its descriptor forms are a superset of round 1's).
    water_test       MoveRuntime's (both call forms); a hit is refused in either.
    the player's spell walk  SpellRuntime runs it after the player's (authored) run; the
                     real tick's tail already calls slot 17 (Player_updateCast), so it is
                     not repeated here.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_player as RP                         # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_move as MV                    # noqa: E402
import ref_combat_melee as ML                   # noqa: E402
import ref_combat_ptick as PT                   # noqa: E402
import ref_combat_ranged as RG                  # noqa: E402
import ref_combat_monsters as MO                # noqa: E402
import ref_combat_spells as SP                  # noqa: E402

M32 = T.M32
s16, s32 = T.s16, T.s32
Unsupported, CompositionError = T.Unsupported, T.CompositionError

AREA_MODELS = (('move', MV.MoveModel), ('melee', ML.MeleeModel), ('defence', PT.DefenceModel),
               ('ranged', RG.RangedModel), ('monsters', MO.MonsterCombatModel), ('spells', SP.QueryModel))

# names the shared world answers, although an area model has a body for them (see above)
KEPT_AS_CALL_OUTS = ('GameObject_dtor', 'Creature_dtor')


def _merge(attr, extra=None):
    """Union of one table over the area models; refuse two different values for one key."""
    base = dict(getattr(T.CombatModel, attr, {}))
    out, owner = dict(base), {}
    for area, cls in AREA_MODELS:
        table = dict(getattr(cls, attr, {}))
        if extra is not None and area in extra:
            table.update(extra[area])
        for key, value in table.items():
            if key in base and base[key] == value:
                continue
            if key in owner and out[key] != value:
                raise CompositionError('%s[%r]: %s says %r, %s says %r' % (attr, key, owner[key], out[key],
                                                                         area, value))
            out[key], owner[key] = value, area
    return out, owner


FULL_INTERNAL, INTERNAL_OWNER = _merge('INTERNAL', {'ranged': RG.RangedModel.RANGED_INTERNAL})
FULL_MODELLED, MODELLED_OWNER = _merge('MODELLED', {'ranged': RG.RangedModel.RANGED_MODELLED})
FULL_COMBAT_BODIES, BODY_OWNER = _merge('COMBAT_BODIES')
for _name in KEPT_AS_CALL_OUTS:
    FULL_INTERNAL.pop(_name, None)


def _check_vtable_bodies():
    """No function word may reach two different bodies: the round-1 / area COMBAT_BODIES,
    RangedModel.RANGED_BODIES and its slot-16 getters must agree where they overlap."""
    seen = {fn: ('combat', body) for fn, body in FULL_COMBAT_BODIES.items()}
    for fn, body in RG.RangedModel.RANGED_BODIES.items():
        if fn in seen and seen[fn][1] != body:
            raise CompositionError('0x%x: %r and ranged %r' % (fn, seen[fn], body))
        seen[fn] = ('ranged', body)
    getters = {0x3C2738: 'creature_get_model', 0x3C3B38: 'player_get_model'}
    for fn, kind in RG.MODEL_GETTERS.items():
        if fn in getters and fn in FULL_COMBAT_BODIES and FULL_COMBAT_BODIES[fn][1] != getters[fn]:
            raise CompositionError('slot 16 0x%x: %s against ranged %s' % (fn, FULL_COMBAT_BODIES[fn], kind))
    return seen


VTABLE_BODIES = _check_vtable_bodies()


# Methods an area model defines that a base class (ref_creature.Model, ref_arena_monsters.
# Model, ref_combat_runtime.CombatModel) or another area also defines, reviewed one by one:
#   tables / dispatch    merged or rewritten in FullModel
#   same body            cstr, handle_obj (RangedModel's copies read the same bytes)
#   superset bodies      _cstr (longer limit), dead_update (with the decal), move_simple,
#                        move_with_collision, player_move (executed bodies replace round 1's)
REVIEWED_SHADOWS = {'COMBAT_BODIES', 'DTORS', 'INTERNAL', 'MODELLED', '_cstr', 'call', 'cstr',
                    'dead_update', 'handle_obj', 'knows', 'move_simple', 'move_with_collision', 'player_move',
                    'vcall'}


def _shadowed_names():
    defs = {}
    for area, cls in AREA_MODELS:
        for name in cls.__dict__:
            defs.setdefault(name, []).append(area)
    out = set()
    for name, areas in defs.items():
        if name.startswith('__'):
            continue
        if len(areas) > 1 or any(name in c.__dict__ for c in T.CombatModel.__mro__):
            out.add(name)
    return out


if _shadowed_names() != REVIEWED_SHADOWS:
    raise CompositionError('unreviewed method shadowing among the area models: %s'
                           % sorted(_shadowed_names() ^ REVIEWED_SHADOWS))

# virtual slot 0 (the type-info getter) -> descriptor, the union of the two area tables
TYPE_DESC = {fn: desc for fn, (desc, _name) in RG.TYPEINFO.items()}
for _fn, _desc in ML.TYPEINFO.items():
    if TYPE_DESC.get(_fn, _desc) != _desc:
        raise CompositionError('type-info getter 0x%x: two descriptors' % _fn)
    TYPE_DESC[_fn] = _desc
TYPE_NAME = {desc: name for _fn, (desc, name) in RG.TYPEINFO.items()}
for _desc, _plain in ML.TYPE_NAMES.items():
    TYPE_NAME.setdefault(_desc, (b'%d' % len(_plain)) + _plain)          # the mangled form


class FullModel(MV.MoveModel, ML.MeleeModel, PT.DefenceModel, RG.RangedModel, MO.MonsterCombatModel,
                SP.QueryModel):
    """Every round-2 body on one model.  Tables merged by _merge (checked at import)."""

    INTERNAL = FULL_INTERNAL
    MODELLED = FULL_MODELLED
    COMBAT_BODIES = FULL_COMBAT_BODIES
    RANGED_INTERNAL = {}                        # merged into INTERNAL
    DTORS = SP.QueryModel.DTORS                 # the effect destructors (effect_dtor)
    RANGED_DTORS = RG.RangedModel.DTORS         # the projectile destructors (destroy_hook)

    def __init__(self, mem, callbacks=None, external=(), inline_grid=False):
        MV.MoveModel.__init__(self, mem, callbacks, external, inline_grid)

    def call(self, name, *args):
        return MV.MoveModel.call(self, name, *args)        # the move rule, then the merged INTERNAL

    def vcall(self, obj, slot, *args):
        """RangedModel's dispatch (projectile destructors to the runtime, the projectile
        bodies here) with the projectile pair as RANGED_DTORS; otherwise round 1's
        dispatch over the merged COMBAT_BODIES."""
        table = self.u32(obj + 0x48)
        fn = self.u32(table + 8 * slot + 4)
        this = (obj + self.s16(table + 8 * slot)) & M32
        name = 'Creature.v%d' % slot
        if name not in self.external:
            if slot == 1 and fn in self.RANGED_DTORS and self.destroy_hook is not None:
                self.vcalls.append((name, (this,) + tuple(args)))
                return self.destroy_hook(this, *args)
            body = RG.RangedModel.RANGED_BODIES.get(fn)
            if body is not None:
                self.vcalls.append((name, (this,) + tuple(args)))
                return getattr(self, body[1])(this, *args)
        return T.CombatModel.vcall(self, obj, slot, *args)

    def type_of(self, obj):
        """Virtual slot 0 of `obj` from the union of the type-info tables, else refused."""
        fn = self.u32(self.u32(obj + 0x48) + 4)
        if fn in TYPE_DESC:
            return TYPE_DESC[fn]
        raise Unsupported('the type-info getter 0x%x of 0x%x' % (fn, obj))


class FullTick(RP.Tick):
    """ref_player.Tick whose tail is preceded by the runtime's queued casts (the AUTHORED
    cast point of SpellRuntime.queue_cast, moved to where Player_run state 5 would call
    Player_castSkill: after the state switch, before Player_updateCast walks the spells)."""

    runtime = None

    def tail(self):
        rt = self.runtime
        for skill_id, level, point, facing in rt.queued.pop(self.P, ()):
            rt.cast(self.P, skill_id, level, point, facing)
        return RP.Tick.tail(self)


class FullServices(PT.TickServices, SP.SpellServices):
    """Plug-ins first (TickServices), Spell.v / Skill.v and every other virtual call-out to
    the runtime's dispatcher (SpellServices), then round 1's table and svc_ methods."""

    PRESENTATION = tuple(dict.fromkeys(PT.TickServices.PRESENTATION + RG.RangedRuntime.PRESENTATION))

    def get(self, name):
        fn = self.rt.plugins.get(name)
        if fn is not None:
            return fn
        return SP.SpellServices.get(self, name)


class FullRuntime(PT.TickRuntime, MV.MoveRuntime, ML.MeleeRuntime, RG.RangedRuntime, MO.MonsterRuntime,
                  SP.SpellRuntime):
    """One world with every round-2 body.  See the module docstring; set-up:

        rt = FullRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))            # real tick, walking speed 1.0
        rt.give_weapon(0, dmg=(30, 40))                     # MeleeRuntime (authored item)
        s = rt.spawn_skelight((60.0, 0.0, 0.0))
        rt.stick(0, 1.0, 0.0); rt.press_attack(0)           # lockstep pad of slot 0
        rt.spawn_missile(p, pos, vel, ...)                  # RangedRuntime
        rt.give_skill(95, stats); rt.queue_cast(p, 95)      # SpellRuntime
        rt.tick()
    """

    RUN_BODIES = RG.RangedRuntime.RUN_BODIES
    DTOR_BODIES = RG.RangedRuntime.DTOR_BODIES

    def __init__(self, terrain=None, anim=None, skill_stat=None, camera_mode=1, screen_planes=None,
                 root_motion=None, lights=True):
        T.Runtime.__init__(self, terrain, anim or PT.PlayerAnim(), skill_stat, camera_mode)
        mem = self.mem
        # TickRuntime
        self.plugins = {}
        self.draws_by_player = {}
        self.services = FullServices(self)
        self.model = FullModel(mem, self.services, inline_grid=False)
        # MoveRuntime
        self.screen_planes = screen_planes
        self.root_motion = dict(root_motion or {})
        # MeleeRuntime: slot 0 is the model's type_of (both tables), names written below
        self.services.table['Creature.v0'] = self.svc_Creature_v0
        self._type_names = True
        # RangedRuntime
        self.model.destroy_hook = lambda addr, flags: self._slot1(self.world.obj(addr), flags)
        for table, slots in ((RG.VT_MISSILE, RG.MISSILE_SLOTS), (RG.VT_THROWN, RG.THROWN_SLOTS)):
            for slot, fn in slots.items():
                mem.poke(table + 8 * slot, 2, 0)
                mem.poke(table + 8 * slot + 4, 4, fn)
        for desc, name in sorted(TYPE_NAME.items()):
            text = self._alloc_fixture(len(name) + 1)
            for i, b in enumerate(name + b'\0'):
                mem.poke(text + i, 1, b)
            mem.poke(desc, 4, text)
        self.projectiles = {}
        self._pending = None
        self.dodge = {}
        # SpellRuntime
        self.qmodel = self.model
        self.models = {SP.SA: SP.SpellsA(self), SP.SB: SP.SpellsB(self), SP.SC: SP.SpellsC(self)}
        self.blocks = {}
        self.iterators = []
        self.lights = lights
        self.queued = {}
        mem.register_head(SP.STACK_HEAD, C.Cell(SP.STACK_HEAD))
        for table, words in list(SP.OBJECT_TABLES.items()) + list(SP.SPELL_TABLES.items()):
            for slot, fn in enumerate(words):
                mem.poke(table + 8 * slot, 2, 0)
                mem.poke(table + 8 * slot + 4, 4, fn)
        self.skill_objects = {}
        # AUTHORED: the list of timed-modifier ids Player_tickEnchantTimers walks for every
        # equipped item (0x537c08, executable data) is given as empty (-1 first): an armed
        # player's tick would otherwise read unmapped fixture memory.  No game value is used.
        mem.poke(RP.G_TIMED_MODIFIERS, 4, M32)

    # ---- set-up ----------------------------------------------------------------------------
    def spawn_player(self, slot, pos, facing=0, hp=100.0, level=1, strength=20, armor=0, team=0,
                     idle_voice_limit=0x7FFF, speed_mul=1.0):
        """TickRuntime's player (four base animation cells, the idle-voice limit as given)
        with MoveRuntime's speed multiplier record +0x4c20 (AUTHORED set-up)."""
        P = PT.TickRuntime.spawn_player(self, slot, pos, facing, hp, level, strength, armor, team,
                                        idle_voice_limit)
        self.mem.poke(T.G_PLAYERS + slot * T.REC_SIZE + 0x4C20, 4, T.f32(speed_mul))
        return P

    # ---- slot 4 and slot 1 ---------------------------------------------------------------
    def player_run(self, P):
        """TickRuntime.player_run with FullTick (the queued casts before the tail)."""
        seed = self.mem.u32(T.G_RAND_SEED)
        tick = FullTick(self.mem, P, self.services)
        tick.runtime = self
        out = tick.run()
        draws = PT.lcg_steps(seed, self.mem.u32(T.G_RAND_SEED))
        self.note('player_tick', P, out.returned, draws)
        self.draws_by_player.setdefault(P, []).append((self.mem.u32(T.G_SIM_FRAME), draws))
        return out

    def _slot4(self, obj):
        addr = obj.addr
        fn = self._fn(addr, 4)
        if self.RUN_BODIES.get(fn) in ('missile', 'thrown'):
            return RG.RangedRuntime._slot4(self, obj)
        if fn == SP.A_LIGHTEFFECT_RUN:
            self.note('run', addr, 'light')
            return self.light_effect_run(addr)
        model = self.model_for(fn)
        if model is not None:
            self.note('run', addr, model.MODULE.__name__)
            return model.vcall(addr, 4)
        T.Runtime._slot4(self, obj)
        if self.kinds.get(addr) != 'player':           # a creature's queued casts: end of its run
            for skill_id, level, point, facing in self.queued.pop(addr, ()):
                if addr in self.world.objects:
                    self.cast(addr, skill_id, level, point, facing)

    def _slot1(self, obj, flags):
        fn = self._fn(obj.addr, 1)
        if self.DTOR_BODIES.get(fn) in ('missile', 'thrown'):
            return RG.RangedRuntime._slot1(self, obj, flags)
        if fn in SP.OBJECT_DTORS:
            return self.object_dtor(obj.addr, flags, fn)
        return T.Runtime._slot1(self, obj, flags)

    # ---- call-outs two areas answer: resolved by the object or the argument form -----------
    def svc_GameObject_ctor(self, obj, pos, class_def, props):
        if obj in self.projectiles:
            return RG.RangedRuntime.svc_GameObject_ctor(self, obj, pos, class_def, props)
        return SP.SpellRuntime.svc_GameObject_ctor(self, obj, pos, class_def, props)

    def svc_GameObject_dtor(self, obj, flags):
        if obj in self.projectiles:
            return RG.RangedRuntime.svc_GameObject_dtor(self, obj, flags)
        return SP.SpellRuntime.svc_GameObject_dtor(self, obj, flags)

    def svc_pool_free(self, addr):
        if addr in self.projectiles:
            return RG.RangedRuntime.svc_pool_free(self, addr)
        return SP.SpellRuntime.svc_pool_free(self, addr)

    def svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit, dmin, dmax):
        if attacker in self.projectiles:
            raise Unsupported('a missile whose owner is gone is its own attacker (damage_apply with the missile)')
        if isinstance(desc, int) and desc:
            return ML.MeleeRuntime.svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit,
                                                    dmin, dmax)
        return SP.SpellRuntime.svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit,
                                                dmin, dmax)

    def svc_res_find(self, lump, entry):
        if isinstance(lump, tuple):                    # RangedModel passes its effect lumps as text
            return RG.RangedRuntime.svc_res_find(self, lump, entry)
        return PT.TickRuntime.svc_res_find(self, lump, entry)

    def svc_water_test(self, world, pos, height_out, radius):
        return MV.MoveRuntime.svc_water_test(self, world, pos, height_out, radius)

    def svc_anim_advance(self, state, sound_pos, root_out, yaw_out, speed):
        return MV.MoveRuntime.svc_anim_advance(self, state, sound_pos, root_out, yaw_out, speed)

    def svc_Player_pickAttackAnim(self, P, cls):
        return self.model.pick_attack_anim(P, cls)

    def svc_Creature_v0(self, *args):
        target = getattr(self.model, 'typeid_target', None)
        if target is None:
            raise Unsupported('virtual slot 0 without a known object')
        return self.model.type_of(target)

    def svc_terrain_height(self, world, pos, radius):
        return self.terrain.height_below(pos, radius)

    def svc_trail_create(self, *args):
        self.note('presentation', 'trail_create')
        return 0

    def live(self, addr):
        return SP.SpellRuntime.live(self, addr)
