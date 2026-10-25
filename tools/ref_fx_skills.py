#!/usr/bin/env python3
"""ref_fx_skills.py - the visual recipes of the skill and effect classes of Champions:
Return to Arms (SLUS_209.73, US v2.00): which effect primitives each class calls, in which
phase, from which generator, and with which arguments (docs/effects.md section 11).

A research tool, not game code.  Standard library only; no game data is embedded.

Three parts.

1. CALLOUTS - how the call-outs of the skill models become effect primitives.
   tools/ref_skills_a.py, _b.py and _c.py (and tools/ref_arena_monsters.py) already model
   140 of the 161 skill-file functions that call an effect primitive, and their
   differential tests run them against the original, call for call: every particle_spawn,
   LightEffect_ctor, glow_add, trail_create ... is made there with its exact arguments
   (canonical form: integers as unsigned 32-bit, floats as 32-bit patterns, a vector as a
   tuple of three patterns).  CALLOUTS names each such call-out, the primitive address and
   the meaning of each canonical argument, and to_primitive() turns one recorded call into
   a FxCall record a renderer can execute (tools/ref_particles.py, tools/ref_lighting.py,
   tools/ref_fx_render.py are the primitives' own contracts).

2. RECIPES - per effect class: phase (cast / run / draw / event), the original function,
   where its executed model lives (module.method), the primitives it calls and the
   generator its random placement draws from.  recipe(name) and classes() read it.

3. Models of the 21 functions the skill models did not have (the draw slots that queue
   glow sprites, and the run functions of StaticFire, DiseaseCloud, FireStormFlare,
   MultiFireProjectile, SpellPlanarSteelEffect, SpellHornOmenEffect, SpellArena and
   Pustule).  Model below is ref_skills_c.Model with these methods added; it sees the game
   exactly as that module does (a memory image, callbacks for everything outside, R5900
   float arithmetic from tools/ref_core.py).  tools/difftest_fx_skills.py runs each of them
   against the original under tools/ee_emu.py.

Constants.  Counts, timings, angle rates, offsets and glow colours are code constants and
are written here as the instructions hold them (round 1 did the same for fx_spawn and
Fire).  Particle definitions and LightEffect colours / radii are named by address or read
from the caller's memory; tools/fx_skill_recipes.py prints them from your own executable.
"""
import os
import sys
from collections import namedtuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_c as SC                       # noqa: E402
from ref_skills_c import *                      # noqa: E402,F401,F403 - the difftest rig reads these names
from ref_creature import Ext, M32, s16, s32     # noqa: E402

G_SIM_FRAME = RC.G_SIM_FRAME                    # 0x44fdcc
G_WORLD = RC.G_WORLD                            # 0x44fdc8
G_NUM_PLAYERS = 0x4D8AE0                        # s32 number of players in the session
ZERO, ONE = C.ZERO, C.ONE
F_2M16 = RC.F_2M16                              # 1 / 65536
HALF_F = C.HALF

# glow textures (resource words; docs/effects.md section 6 and round-2 item 7)
G_GLOW_TEX_A = 0x4F848C                         # light-chunk / summon glow
G_GLOW_TEX_B = 0x4F8494                         # fire-arrow glow
G_GLOW_TEX_C = 0x4F8498                         # shock / holy-strike glow
G_GLOW_TEX_RES = 0x44FE04                       # the resurrect ring
G_GLOW_TEX_FIRE = 0x4F84A0                      # StaticFire flames
G_GLOW_TEX_FIRE_DIM = 0x4F84A4                  # StaticFire flames below the fade height

# ---------------------------------------------------------------------------------------
# 1. Call-outs -> primitives
# ---------------------------------------------------------------------------------------
Callout = namedtuple('Callout', 'addr primitive fields note')
FxCall = namedtuple('FxCall', 'primitive fields')

CALLOUTS = {
    'particle_spawn': Callout(0x18F3F8, 'particle', ('definition', 'pos', 'vel', 'backdate'),
                              'ref_particles.ParticleSystem.spawn(def, pos, vel, backdate); definition by address'),
    'glow_add': Callout(0x18FC78, 'glow', ('pos', 'r', 'g', 'b', 'a', 'texture', 'angle', 'flags', 'bias', 'size'),
                        'docs/effects.md 6; texture is the resource word the code loaded'),
    'LightEffect_ctor': Callout(0x201BD8, 'light_effect',
                                ('block', 'pos', 'follow', 'flag', 'c0', 'c1', 'c2', 'c3', 'd0', 'd1', 'd2', 'd3',
                                 'radius', 'radius_end', 'floor', 'seconds'),
                                'ref_lighting.LightEffect; a GameObject: ONE SHARED DRAW in its constructor'),
    'trail_create': Callout(0x190FF8, 'trail', ('row', 'width', 'flags', 'r', 'g', 'b', 'a', 'lifetime'),
                            'docs/effects.md 7: (lifetime s; row, width, flags, rgba) -> handle'),
    'trail_addPoint': Callout(0x192550, 'trail_point', ('handle', 'pos'), 'stamp = trail clock + 1'),
    'trail_release': Callout(0x192800, 'trail_release', ('handle',), ''),
    'beam_create': Callout(0x193088, 'beam', ('from', 'to', 'width', 'depth', 'rgba', 'jitter', 'scale'), ''),
    'beam_update': Callout(0x1933C8, 'beam_update', ('handle', 'from', 'to', 'alpha', 'width'), ''),
    'decal_add': Callout(0x19F110, 'decal', ('pos', 'angle', 'type', 'grow', 'size'), 'docs/effects.md 8'),
    'fx_spawn': Callout(0x1EF270, 'fx_spawn', ('id', 'pos'), 'docs/effects.md 10, tools/ref_fx_recipes.py'),
    'fx_ringBurst': Callout(0x1F3D00, 'ring_burst', None, 'arguments as the model records them'),
    'fx_impactPuffNearCamera': Callout(0x1FC150, 'puff', ('pos', 'step', 'mode', 'radius', 'size'), ''),
    'fx_emitFromModelVerts': Callout(0x1EB1E8, 'model_verts', ('object', 'count', 'definition', 'a', 'b', 'speed'), ''),
    'fx_shockModel': Callout(0x1F61C0, 'model_particles_light', None,
                             'docs/effects.md calls it fx_modelParticlesNearCamera_1f61c0'),
    'fx_burnModel': Callout(0x1F5210, 'model_particles', None, 'docs/effects.md: fx_modelParticlesNearCamera_1f5210'),
    'fx_disintegrateModel': Callout(0x1F4340, 'disintegrate', None, 'tools/ref_fx_recipes.py'),
    'fx_shatterToLooseIce': Callout(0x1FB240, 'ice_shatter', None, 'draws the shared seed (docs/gameplay.md)'),
    'trail_setColor': Callout(0x191100, 'trail_color', ('handle', 'r', 'g', 'b', 'a'), ''),
    'trail_setLength': Callout(0x1911A8, 'trail_width', ('handle', 'value'),
                               'stores value >> 2 at +0x40f (round 1: trail_setWidth)'),
    'trail_setPoints': Callout(0x1918A0, 'trail_points', None, 'a point array handed to the trail'),
    'trail_setPoints_1918a0': Callout(0x1918A0, 'trail_points', None, 'the same function, another model\'s name'),
    'trail_clear_191e58': Callout(0x191E58, 'trail_clear', None, ''),
    'GlowingShaft_ctor': Callout(0x202FF0, 'object', None, 'a visual GameObject (shared draw in its constructor)'),
    'LightningBolt_ctor': Callout(0x295360, 'object', None, 'a GameObject with beams'),
    'LightningBolt_ctor2': Callout(0x295584, 'object', None, 'a GameObject with beams'),
    'GutChunk_ctor': Callout(0x201958, 'object', None, 'docs/effects.md 9: a gib'),
    'camera_shake': Callout(0x1EBAE0, 'camera_shake', None, 'per machine'),
    'gfx_setColorOffset': Callout(0x19B6BC, 'screen_tint', None, 'per machine'),
    'particleGroup_create': Callout(0x18E880, 'group_create', (), '-> handle'),
    'particleGroup_begin': Callout(0x18E958, 'group_begin', ('handle',), ''),
    'particleGroup_end': Callout(0x18E9A0, 'group_end', ('handle',), ''),
    'particleGroup_setMatrix': Callout(0x18E9E8, 'group_matrix', ('handle', 'matrix'), ''),
    'particleGroup_free': Callout(0x18EA90, 'group_free', ('handle',), ''),
    'light_link': Callout(0x148AF8, 'light_link', ('light',), 'the class\'s own light node (ref_lighting.LightNode)'),
    'light_relink': Callout(0x14A528, 'light_relink', ('light',), 'the light follows its new position'),
    'light_unlink': Callout(0x14A4F0, 'light_unlink', ('light',), ''),
}


def _float(raw):
    return C.to_float(raw & M32)


def to_primitive(name, args):
    """One recorded call-out (name, canonical args) -> FxCall, or None when the name is
    not an effect primitive.  Float patterns become Python floats, vectors tuples of
    floats; integers stay as they are.  The argument order of the canonical form is the
    integer registers a0.., then f12.., then stack words (ref_creature.Ext)."""
    out = CALLOUTS.get(name)
    if out is None:
        return None
    if out.fields is None:
        return FxCall(out.primitive, {'args': tuple(args)})
    a = list(args)
    if name == 'particle_spawn':
        values = (a[0], tuple(_float(v) for v in a[1]), tuple(_float(v) for v in a[2]), _float(a[3]))
    elif name == 'glow_add':
        values = (tuple(_float(v) for v in a[0]),) + tuple(a[1:8]) + (_float(a[8]), _float(a[9]))
    elif name == 'LightEffect_ctor':
        values = (a[0], tuple(_float(v) for v in a[1]), a[2], a[3]) + tuple(_float(v) for v in a[4:16])
    elif name == 'trail_create':
        values = tuple(a[0:7]) + (_float(a[7]),)
    elif name == 'trail_addPoint':
        values = (a[0], tuple(_float(v) for v in a[1]) if isinstance(a[1], tuple) else a[1])
    elif name == 'decal_add':
        values = (tuple(_float(v) for v in a[0]), a[1], a[2], a[3], _float(a[4]))
    elif name == 'fx_spawn':
        values = (a[0], tuple(_float(v) for v in a[1]))
    else:
        values = tuple(tuple(_float(x) for x in v) if isinstance(v, tuple) else v for v in a)
    return FxCall(out.primitive, dict(zip(out.fields, values)))


def effects_of(calls):
    """The effect primitives of a recorded call stream, in order."""
    return [fx for fx in (to_primitive(name, args) for name, args in calls) if fx is not None]


# ---------------------------------------------------------------------------------------
# 2. Recipes per class
# ---------------------------------------------------------------------------------------
# One row per function of the skill files (0x2c3cd4-0x320000) that calls an effect
# primitive (tools/fx_callsites.py map 2c3cd4 320000), 161 of them:
#   class, phase, function, address, model, primitive calls in the code, generators.
# phase: cast = the constructor / cast call (the tick the effect is made); run = every
#   simulated tick (GameObject slot 4, Spell slot 2, or a helper of them); draw = every
#   rendered frame (GameObject slot 5, Spell slot 3); event = the tick of a hit, contact,
#   expiry, absorption or trigger.  (From the function's slot and caller.)
# model: the method that reproduces the function, call for call, in the module named; every
#   one is executed against the original by that module's difftest
#   (tools/difftest_skills_a.py, _b, _c, tools/difftest_arena_monsters.py, and
#   tools/difftest_fx_skills.py for ref_fx_skills).
# primitive calls: the static count of calls in the function's code (round 1's map).
# generators: what the model's code of the function (and the helpers it calls) draws from:
#   own = the object's generator +0x44, spell = the spell's generator +0x10, SHARED = the
#   shared seed 0x404464 (gameplay: it is in the sync hash), SHARED(LightEffect) = the one
#   shared draw inside each LightEffect constructor, cosmetic = 0x404460 (per machine).  Inferred from the model's source, not
#   per particle: a SHARED draw may be a damage roll next to the visual.
# (class, phase, function, address, model, primitive calls in the code, generators)
_RECIPE_ROWS = (
    ('ShockProjectile', 'cast', 'ShockProjectile_ctor', 0x2C3FE4, 'ref_skills_b.shock_ctor', 'lightLink:1', ''),
    ('ShockProjectile', 'run', 'ShockProjectile_run', 0x2C42E4, 'ref_skills_b.shock_run', 'beam:1 beamUpdate:1 particle:2', 'SHARED own'),
    ('ShockProjectile', 'draw', 'ShockProjectile_draw', 0x2C4E64, 'ref_fx_skills.shock_draw', 'glow:1', ''),
    ('StaticFire', 'cast', 'StaticFire_ctor', 0x2C5240, 'ref_fx_skills.staticfire_ctor', 'lightLink:1', 'own'),
    ('StaticFire', 'cast', 'StaticFire_ctor2', 0x2C54F8, 'ref_fx_skills.staticfire_ctor2', 'lightLink:1', 'own'),
    ('StaticFire', 'run', 'StaticFire_run', 0x2C595C, 'ref_fx_skills.staticfire_run', 'particle:2', 'SHARED own'),
    ('StaticFire', 'draw', 'StaticFire_draw', 0x2C65E8, 'ref_fx_skills.staticfire_draw', 'glow:2', ''),
    ('GroundPoundEffect', 'cast', 'GroundPoundEffect_ctor', 0x2C74AC, 'ref_skills_b.groundpound_effect_ctor', 'lightLink:1', ''),
    ('GroundPoundEffect', 'run', 'GroundPoundEffect_run', 0x2C7808, 'ref_skills_b.groundpound_effect_run', 'LightEffect:1 decal:1 particle:7', 'SHARED(LightEffect) own seed3'),
    ('SpellCharge', 'cast', 'SpellCharge_ctor', 0x2C8CB4, 'ref_skills_b.charge_spell_ctor', 'lightLink:1 trail:1 trailPoint:1', 'SHARED'),
    ('SpellCharge', 'run', 'SpellCharge_run', 0x2C8F2C, 'ref_skills_b.charge_run', 'particle:2 trailPoint:1', 'spell'),
    ('SpellCharge', 'event', 'SpellCharge_onContact', 0x2C95F4, 'ref_skills_b.charge_on_contact', 'fx_spawn:1 particle:2', 'spell'),
    ('DiseaseBolt', 'run', 'DiseaseBolt_run', 0x2CA1A8, 'ref_skills_a.diseasebolt_run', 'fx_spawn:1 particle:6', 'own'),
    ('DiseaseTrail', 'run', 'DiseaseTrail_run', 0x2CB65C, 'ref_skills_a.diseasetrail_run', 'particle:3', 'own'),
    ('SpellDiseaseTrail', 'run', 'SpellDiseaseTrail_run', 0x2CC248, 'ref_skills_a.diseasetrail_spell_run', 'particle:3', 'SHARED spell'),
    ('SpellDiseaseShield', 'run', 'SpellDiseaseShield_run', 0x2CD318, 'ref_skills_a.diseaseshield_run', 'glow:1 particle:2', 'spell'),
    ('DiseaseCloud', 'run', 'DiseaseCloud_run', 0x2CE6E0, 'ref_fx_skills.diseasecloud_run', 'particle:3', 'own'),
    ('DarknessProjectile', 'cast', 'DarknessProjectile_ctor', 0x2CF460, 'ref_skills_b.darkness_ctor', 'lightLink:1', ''),
    ('DarknessProjectile', 'run', 'DarknessProjectile_run', 0x2CF690, 'ref_skills_b.darkness_run', 'particle:1', 'own'),
    ('SpellConvertEnemy', 'cast', 'SpellConvertEnemy_ctor', 0x2D0154, 'ref_skills_b.convert_spell_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellConvertEnemy', 'run', 'SpellConvertEnemy_run', 0x2D0354, 'ref_skills_b.convert_run', 'particle:1', 'SHARED'),
    ('SpellConvertUndead', 'cast', 'SpellConvertUndead_ctor', 0x2D0CC0, 'ref_skills_b.convert_spell_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellConvertUndead', 'run', 'SpellConvertUndead_run', 0x2D0EDC, 'ref_skills_b.convert_run', 'particle:1', 'SHARED'),
    ('SpellCyclone', 'cast', 'SpellCyclone_ctor', 0x2D17C8, 'ref_skills_b.cyclone_spell_ctor', 'lightLink:1', 'SHARED spell'),
    ('SpellCyclone', 'run', 'SpellCyclone_updateFx', 0x2D21E0, 'ref_skills_b.cyclone_update_fx', 'particle:2', 'spell'),
    ('SpellHarmTouch', 'event', 'SpellHarmTouch_applyToHit', 0x2D2CBC, 'ref_skills_b.harmtouch_apply_to_hit', 'LightEffect:1 particle:2', 'SHARED(LightEffect) spell'),
    ('FireStormFlare', 'run', 'FireStormFlare_run', 0x2D33C0, 'ref_fx_skills.firestormflare_run', 'decal:1 particle:5', 'own'),
    ('FireStorm', 'cast', 'FireStorm_ctor2', 0x2D4048, 'ref_skills_a.firestorm_ctor2', 'lightLink:1', 'SHARED SHARED(LightEffect)'),
    ('FireStorm', 'cast', 'FireStorm_ctor', 0x2D41F8, 'ref_skills_a.firestorm_ctor', 'lightLink:1', 'SHARED SHARED(LightEffect)'),
    ('FireStorm', 'cast', 'FireStorm_initCommon', 0x2D4480, 'ref_skills_a.firestorm_init_common', 'LightEffect:1', 'SHARED(LightEffect)'),
    ('SpellDiseaseEffect', 'run', 'SpellDiseaseEffect_run', 0x2D5854, 'ref_skills_a.disease_spell_run', 'glow:1', 'SHARED spell'),
    ('FireArrowProjectile', 'cast', 'FireArrowProjectile_ctor', 0x2D6238, 'ref_skills_b.firearrow_ctor', 'lightLink:1', 'SHARED'),
    ('FireArrowProjectile', 'cast', 'FireArrowProjectile_ctor2', 0x2D6440, 'ref_skills_b.firearrow_ctor2', 'lightLink:1', 'SHARED'),
    ('FireArrowProjectile', 'run', 'FireArrowProjectile_run', 0x2D66AC, 'ref_skills_b.firearrow_run', 'puff:1', 'own'),
    ('FireArrowProjectile', 'draw', 'FireArrowProjectile_draw', 0x2D67E8, 'ref_fx_skills.firearrow_draw', 'glow:1', ''),
    ('ColdArrowProjectile', 'cast', 'ColdArrowProjectile_ctor', 0x2D6FB4, 'ref_skills_b.coldarrow_ctor', 'lightLink:1', 'SHARED'),
    ('ColdArrowProjectile', 'cast', 'ColdArrowProjectile_ctor2', 0x2D718C, 'ref_skills_b.coldarrow_ctor2', 'lightLink:1', 'SHARED'),
    ('ColdArrowProjectile', 'run', 'ColdArrowProjectile_run', 0x2D73C8, 'ref_skills_b.coldarrow_run', 'particle:2', 'own'),
    ('ColdArrowProjectile', 'event', 'ColdArrowProjectile_onHit', 0x2D7AAC, 'ref_skills_b.coldarrow_on_hit', 'fx_spawn:2', 'own'),
    ('ColdArrowProjectile', 'event', 'ColdArrowProjectile_end', 0x2D7ECC, 'ref_skills_b.coldarrow_end', 'particle:3', 'own'),
    ('PoisonArrowProjectile', 'cast', 'PoisonArrowProjectile_ctor', 0x2D8A64, 'ref_skills_b.poisonarrow_ctor', 'lightLink:1', 'SHARED'),
    ('PoisonArrowProjectile', 'cast', 'PoisonArrowProjectile_ctor2', 0x2D8C40, 'ref_skills_b.poisonarrow_ctor2', 'lightLink:1', 'SHARED'),
    ('PoisonArrowProjectile', 'run', 'PoisonArrowProjectile_run', 0x2D8E80, 'ref_skills_b.poisonarrow_run', 'particle:2', 'own'),
    ('PoisonArrowProjectile', 'event', 'PoisonArrowProjectile_end', 0x2D95C8, 'ref_skills_b.poisonarrow_end', 'particle:1', ''),
    ('SkillMultiFire', 'cast', 'SkillMultiFire_cast', 0x2D9A90, 'ref_skills_b.multifire_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect) cosmetic'),
    ('MultiFireProjectile', 'cast', 'MultiFireProjectile_ctor', 0x2DA164, 'ref_fx_skills.multifire_ctor', 'trail:1 trailPoint:1', ''),
    ('MultiFireProjectile', 'run', 'MultiFireProjectile_run', 0x2DA2BC, 'ref_fx_skills.multifire_run', 'particle:1 trailPoint:1', 'own'),
    ('MultiFireProjectile', 'event', 'MultiFireProjectile_end', 0x2DA928, 'ref_fx_skills.multifire_end', 'fx_spawn:2', 'own'),
    ('ExplodeArrowProjectile', 'run', 'ExplodeArrowProjectile_run', 0x2DB17C, 'ref_skills_b.explodearrow_run', 'particle:1', 'own'),
    ('ExplodeArrowProjectile', 'event', 'ExplodeArrowProjectile_explode', 0x2DB50C, 'ref_skills_b.explodearrow_explode', 'LightEffect:1 fx_spawn:2 ringBurst:1', 'SHARED(LightEffect) own'),
    ('FireFlare', 'run', 'FireFlare_run', 0x2DBF10, 'ref_skills_a.fireflare_run', 'particle:5', 'own'),
    ('SpellFireFlares', 'cast', 'SpellFireFlares_ctor', 0x2DCD40, 'ref_skills_a.fireflares_ctor', 'lightLink:1', 'SHARED'),
    ('SkillRiposte', 'event', 'SkillRiposte_counterAttack', 0x2DDCCC, 'ref_skills_a.riposte_counter_attack', 'particle:2', 'SHARED cosmetic'),
    ('SpellBash', 'run', 'SpellBash_run', 0x2DE7DC, 'ref_skills_b.bash_run', 'LightEffect:1', 'SHARED SHARED(LightEffect) spell'),
    ('SpellBash', 'run', 'SpellBash_windupFx', 0x2DEDEC, 'ref_skills_b.bash_windup_fx', 'particle:1', 'spell'),
    ('SpellBlessed', 'cast', 'SpellBlessed_ctor', 0x2DF078, 'ref_skills_a.blessed_ctor', 'lightLink:1', 'SHARED spell'),
    ('SpellBlessed', 'run', 'SpellBlessed_run', 0x2DF4BC, 'ref_skills_a.blessed_run', 'glow:1 particle:2', 'spell'),
    ('SpellAncestralCall', 'cast', 'SpellAncestralCall_ctor', 0x2E09B4, 'ref_skills_b.ancestralcall_spell_ctor', 'LightEffect:1 particleGroup:1', 'SHARED SHARED(LightEffect)'),
    ('SpellAncestralCall', 'run', 'SpellAncestralCall_run', 0x2E0D10, 'ref_skills_b.ancestralcall_run', 'beam:1 beamUpdate:1 particle:1', 'spell'),
    ('SpellAncestralCall', 'run', 'SpellAncestralCall_tintAndGlow', 0x2E15A0, 'ref_skills_b.ancestralcall_tint_and_glow', 'modelParticlesLight:1', ''),
    ('SkillSummonSkeleton', 'cast', 'SkillSummonSkeleton_cast', 0x2E18A4, 'ref_arena_monsters.summon_cast', 'particle:2', 'SHARED cosmetic'),
    ('SpellLightningWeapons', 'cast', 'SpellLightningWeapons_ctor', 0x2E24D8, 'ref_skills_a.weaponbuff_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellLightningWeapons', 'run', 'SpellLightningWeapons_run', 0x2E2AC4, 'ref_skills_a.weaponbuff_run', 'modelParticlesLight:1', 'spell'),
    ('SpellFireWeapons', 'cast', 'SpellFireWeapons_ctor', 0x2E34E0, 'ref_skills_a.fireweapons_ctor', 'lightLink:1', 'SHARED'),
    ('SpellFireWeapons', 'run', 'SpellFireWeapons_run', 0x2E3B28, 'ref_skills_a.fireweapons_run', 'particle:3', 'spell'),
    ('SpellColdWeapons', 'cast', 'SpellColdWeapons_ctor', 0x2E4F94, 'ref_skills_a.weaponbuff_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellColdWeapons', 'run', 'SpellColdWeapons_run', 0x2E5578, 'ref_skills_a.weaponbuff_run', 'particle:2', 'spell'),
    ('SpellRoot', 'cast', 'SpellRoot_ctor', 0x2E68C8, 'ref_skills_a.root_spell_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellRoot', 'run', 'SpellRoot_run', 0x2E699C, 'ref_skills_a.root_spell_run', 'particle:3', 'SHARED spell'),
    ('SpellCriticalHit', 'cast', 'SpellCriticalHit_ctor', 0x2E7988, 'ref_skills_a.crit_spell_ctor', 'lightLink:1 particleGroup:1', 'SHARED'),
    ('SpellCriticalHit', 'run', 'SpellCriticalHit_run', 0x2E7ACC, 'ref_skills_a.crit_spell_run', 'particle:1', 'spell'),
    ('SpellHolyShield', 'cast', 'SpellHolyShield_ctor', 0x2E82FC, 'ref_skills_b.holyshield_spell_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellHolyShield', 'event', 'SpellHolyShield_absorb', 0x2E8534, 'ref_skills_b.holyshield_absorb', 'LightEffect:1 particle:1', 'SHARED(LightEffect) spell'),
    ('SpellHealing', 'cast', 'SpellHealing_ctor', 0x2E8EC8, 'ref_skills_b.healing_spell_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellHealing', 'run', 'SpellHealing_run', 0x2E90B8, 'ref_skills_b.healing_run', 'particle:1', 'spell'),
    ('SpellConeOfFrost', 'cast', 'SpellConeOfFrost_ctor', 0x2E9B08, 'ref_skills_b.coneoffrost_spell_ctor', 'lightLink:1', 'SHARED'),
    ('SpellConeOfFrost', 'run', 'SpellConeOfFrost_run', 0x2E9D10, 'ref_skills_b.coneoffrost_run', 'particle:3', 'SHARED spell'),
    ('SpellUndeadShield', 'cast', 'SpellUndeadShield_ctor', 0x2EA4D8, 'ref_skills_a.undeadshield_ctor', 'lightLink:1 particleGroup:1', 'SHARED'),
    ('SpellUndeadShield', 'run', 'SpellUndeadShield_run', 0x2EA74C, 'ref_skills_a.undeadshield_run', 'particle:1', 'SHARED spell'),
    ('SpellSecondaryUndeadShield', 'cast', 'SpellSecondaryUndeadShield_ctor', 0x2EB050, 'ref_skills_a.secondary_shield_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellSecondaryUndeadShield', 'run', 'SpellSecondaryUndeadShield_run', 0x2EB170, 'ref_skills_a.secondary_shield_run', 'particle:1', 'spell'),
    ('HolyStrike', 'cast', 'HolyStrike_ctor', 0x2EBA48, 'ref_skills_a.holystrike_ctor', 'trail:1 trailPoint:1', 'SHARED'),
    ('HolyStrike', 'run', 'HolyStrike_run', 0x2EBC50, 'ref_skills_a.holystrike_run', 'LightEffect:1 particle:6 trailPoint:1', 'SHARED(LightEffect) own'),
    ('HolyStrike', 'draw', 'HolyStrike_draw', 0x2ECD90, 'ref_fx_skills.holystrike_draw', 'glow:1', ''),
    ('HammerOfWrath', 'run', 'HammerOfWrath_run', 0x2EE068, 'ref_skills_a.hammer_run', 'particle:1', 'own seed3'),
    ('SkillHammerOfWrath', 'cast', 'SkillHammerOfWrath_cast', 0x2EFB20, 'ref_skills_a.hammer_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellConeOfFire', 'cast', 'SpellConeOfFire_ctor', 0x2F00AC, 'ref_skills_a.coneoffire_ctor', 'lightLink:1', 'SHARED'),
    ('SpellConeOfFire', 'run', 'SpellConeOfFire_run', 0x2F02FC, 'ref_skills_a.coneoffire_run', 'particle:3', 'spell'),
    ('SpellWizardBeam', 'cast', 'SpellWizardBeam_ctor', 0x2F1528, 'ref_skills_a.wizardbeam_ctor', 'trail:7', 'SHARED spell'),
    ('BlindingLightEffect', 'cast', 'BlindingLightEffect_ctor', 0x2F3F38, 'ref_skills_a.blindinglight_effect_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect) own'),
    ('BlindingLightEffect', 'run', 'BlindingLightEffect_run', 0x2F42E4, 'ref_skills_a.blindinglight_effect_run', 'particle:1', 'own'),
    ('SkillRepulseUndead', 'cast', 'SkillRepulseUndead_cast', 0x2F4D34, 'ref_skills_a.repulse_cast', 'LightEffect:1', 'SHARED(LightEffect)'),
    ('HolyBolt', 'cast', 'HolyBolt_ctor', 0x2F5248, 'ref_skills_a.holybolt_ctor', 'lightLink:1 trail:1 trailPoint:1', 'SHARED'),
    ('HolyBolt', 'run', 'HolyBolt_run', 0x2F57B0, 'ref_skills_a.holybolt_run', 'particle:1 trailPoint:1', 'own'),
    ('HolyBolt', 'event', 'HolyBolt_onHit', 0x2F5FB4, 'ref_skills_a.holybolt_hit', 'LightEffect:1 particle:1', 'SHARED(LightEffect) own'),
    ('FrostShard', 'run', 'FrostShard_run', 0x2F6B3C, 'ref_skills_a.frostshard_run', 'fx_spawn:1 particle:2', 'own'),
    ('ShockOfFrost', 'cast', 'ShockOfFrost_ctor', 0x2F7404, 'ref_skills_a.shockoffrost_ctor', 'lightLink:1', 'SHARED'),
    ('ShockOfFrost', 'run', 'ShockOfFrost_run', 0x2F77C0, 'ref_skills_a.shockoffrost_run', 'fx_spawn:1 particle:4', 'SHARED own'),
    ('PoisonRain', 'cast', 'PoisonRain_ctor', 0x2F8F48, 'ref_skills_a.poisonrain_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('PoisonRain', 'run', 'PoisonRain_run', 0x2F9254, 'ref_skills_a.poisonrain_run', 'LightEffect:1 particle:2', 'SHARED(LightEffect) own'),
    ('SpellShieldBash', 'run', 'SpellShieldBash_run', 0x2FAE80, 'ref_skills_a.shieldbash_run', 'LightEffect:1', 'SHARED SHARED(LightEffect) spell'),
    ('SpellShieldBash', 'run', 'SpellShieldBash_windupFx', 0x2FB49C, 'ref_skills_a.shieldbash_windup_fx', 'particle:1', 'spell'),
    ('SpellPlanarSteelEffect', 'cast', 'SpellPlanarSteelEffect_ctor', 0x2FB728, 'ref_fx_skills.planarsteel_ctor', 'lightLink:1', 'SHARED'),
    ('SpellPlanarSteelEffect', 'run', 'SpellPlanarSteelEffect_run', 0x2FB9B4, 'ref_fx_skills.planarsteel_run', 'glow:1 particle:5', 'spell'),
    ('SpellHornOmenEffect', 'cast', 'SpellHornOmenEffect_ctor', 0x2FC574, 'ref_fx_skills.hornomen_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellHornOmenEffect', 'run', 'SpellHornOmenEffect_run', 0x2FC684, 'ref_fx_skills.hornomen_run', 'particle:2', 'spell'),
    ('SkillUnspokenWord', 'cast', 'SkillUnspokenWord_cast', 0x2FD030, 'ref_skills_c.unspokenword_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellUnspokenWord', 'cast', 'SpellUnspokenWord_ctor', 0x2FD368, 'ref_skills_c.unspokenword_spell_ctor', 'trail:2', 'SHARED'),
    ('SpellUnspokenWord', 'run', 'SpellUnspokenWord_run', 0x2FD5D4, 'ref_skills_c.unspokenword_spell_run', 'particle:2', 'spell'),
    ('SkillSummonAxe', 'cast', 'SkillSummonAxe_cast', 0x2FE644, 'ref_skills_c.summonaxe_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellSummonAxe', 'cast', 'SpellSummonAxe_ctor', 0x2FEB88, 'ref_skills_c._summon_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellSummonAxe', 'run', 'SpellSummonAxe_run', 0x2FEDDC, 'ref_skills_c.summonaxe_spell_run', 'particle:1', 'spell'),
    ('SkillSummonArrows', 'cast', 'SkillSummonArrows_cast', 0x2FF5F4, 'ref_skills_c.summonarrows_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellSummonArrows', 'cast', 'SpellSummonArrows_ctor', 0x2FF87C, 'ref_skills_c._summon_ctor', 'particleGroup:1', 'SHARED'),
    ('SpellSummonArrows', 'run', 'SpellSummonArrows_run', 0x2FFAD4, 'ref_skills_c.summonarrows_spell_run', 'particle:1', 'spell'),
    ('SpellRoar', 'run', 'SpellRoar_run', 0x3003D8, 'ref_skills_c.roar_spell_run', 'particle:5', 'spell'),
    ('SpellBattleCry', 'run', 'SpellBattleCry_run', 0x301A34, 'ref_skills_c.battlecry_spell_run', 'LightEffect:1 particle:5 particleGroup:1', 'SHARED(LightEffect) spell'),
    ('SpellBloodLust', 'run', 'SpellBloodLust_run', 0x3034DC, 'ref_skills_c.bloodlust_spell_run', 'glow:4 particle:6', 'spell'),
    ('SpellArena', 'run', 'SpellArena_run', 0x305BBC, 'ref_fx_skills.arena_run', 'particle:2', 'spell'),
    ('SkillStrongStance', 'event', 'SkillStrongStance_trigger', 0x308578, 'ref_skills_b.strongstance_trigger', 'LightEffect:1 particle:1', 'SHARED(LightEffect) seed3'),
    ('SkillStunningStrike', 'cast', 'SkillStunningStrike_spawnEffect', 0x308CB4, 'ref_skills_b.stunningstrike_effect', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellGiantGrowth', 'cast', 'SpellGiantGrowth_ctor', 0x3090D0, 'ref_skills_b.giantgrowth_spell_ctor', 'lightLink:1 particleGroup:1', 'SHARED spell'),
    ('SpellGiantGrowth', 'run', 'SpellGiantGrowth_emitParticles', 0x309678, 'ref_skills_b.giantgrowth_emit', 'particle:1', 'spell'),
    ('SpellPlanarWind', 'cast', 'SpellPlanarWind_ctor', 0x309D0C, 'ref_skills_b.planarwind_spell_ctor', 'lightLink:1', 'SHARED'),
    ('SpellPlanarWind', 'run', 'SpellPlanarWind_run', 0x30A0B0, 'ref_skills_b.planarwind_run', 'particle:3', 'SHARED spell'),
    ('PusStorm', 'cast', 'PusStorm_ctor', 0x30AF6C, 'ref_skills_c._storm_ctor', 'LightEffect:1 lightLink:1', 'SHARED(LightEffect)'),
    ('Pustule', 'run', 'Pustule_run', 0x30BDE0, 'ref_fx_skills.pustule_run', 'particle:2', 'own'),
    ('SpellTagarsInsects', 'run', 'SpellTagarsInsects_run', 0x30CBC8, 'ref_arena_monsters.tagar_spell_run', 'particle:3', 'SHARED spell'),
    ('SpellTagarsInsects', 'run', 'SpellTagarsInsects_tickVictims', 0x30D558, 'ref_arena_monsters.tagar_tick_victims', 'particle:1', 'spell'),
    ('SkillDrowsy', 'cast', 'SkillDrowsy_cast', 0x30E1F0, 'ref_skills_c.drowsy_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellDrowsy', 'run', 'SpellDrowsy_run', 0x30E6F0, 'ref_skills_c.drowsy_spell_run', 'particle:2', 'spell'),
    ('PoisonBolt', 'cast', 'PoisonBolt_ctor', 0x30F398, 'ref_skills_c.poisonbolt_ctor', 'lightLink:1', ''),
    ('PoisonBolt', 'run', 'PoisonBolt_run', 0x30F800, 'ref_skills_c.poisonbolt_run', 'particle:2', 'own'),
    ('PoisonBolt', 'event', 'PoisonBolt_burst', 0x3101CC, 'ref_skills_c.poisonbolt_burst', 'particle:1', 'own'),
    ('SkillSummonBadger', 'cast', 'SkillSummonBadger_cast', 0x3106F4, 'ref_skills_c.summonbadger_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellSummonBadger', 'run', 'SpellSummonBadger_run', 0x310CD0, 'ref_skills_c.summonbadger_spell_run', 'particle:1', 'spell'),
    ('SpellSummonBadger', 'draw', 'SpellSummonBadger_draw', 0x311034, 'ref_fx_skills.badger_draw', 'glow:1', ''),
    ('SpellShadowStep', 'cast', 'SpellShadowStep_ctor', 0x311638, 'ref_skills_b.shadowstep_spell_ctor', 'LightEffect:1 particle:1', 'SHARED SHARED(LightEffect) spell'),
    ('SpellResurrect', 'cast', 'SpellResurrect_ctor', 0x3127B4, 'ref_skills_b.resurrect_spell_ctor', 'lightLink:1', 'SHARED'),
    ('SpellResurrect', 'run', 'SpellResurrect_run', 0x312B30, 'ref_skills_b.resurrect_run', 'modelVerts:2', ''),
    ('SpellResurrect', 'draw', 'SpellResurrect_draw', 0x312F48, 'ref_fx_skills.resurrect_draw', 'glow:1', ''),
    ('SpellResurrect', 'event', 'SpellResurrect_onOwnerDeath', 0x3130F4, 'ref_skills_b.resurrect_on_owner_death', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SkillRaiseArmy', 'cast', 'SkillRaiseArmy_cast', 0x3134E4, 'ref_skills_c.raisearmy_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellRaiseArmy', 'run', 'SpellRaiseArmy_run', 0x31399C, 'ref_skills_c.raisearmy_spell_run', 'particle:1', 'spell'),
    ('SpellRetribution', 'cast', 'SpellRetribution_ctor', 0x314488, 'ref_skills_c.retribution_spell_ctor', 'lightLink:1 particleGroup:1', 'SHARED'),
    ('SpellRetribution', 'run', 'SpellRetribution_run', 0x314618, 'ref_skills_c.retribution_spell_run', 'modelVerts:1', ''),
    ('SpellSpiritShield', 'cast', 'SpellSpiritShield_ctor', 0x31500C, 'ref_skills_c.spiritshield_spell_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellSpiritShield', 'run', 'SpellSpiritShield_dissolveParticles', 0x31539C, 'ref_skills_c._spiritshield_particles', 'particle:1', 'spell'),
    ('SpellSpiritShield', 'run', 'SpellSpiritShield_reformParticles', 0x315610, 'ref_skills_c._spiritshield_particles', 'particle:1', 'spell'),
    ('SpellPoisonWeapons', 'cast', 'SpellPoisonWeapons_ctor', 0x315F54, 'ref_skills_a.weaponbuff_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellWaveOfFlame', 'cast', 'SpellWaveOfFlame_ctor', 0x316D10, 'ref_skills_c.waveofflame_spell_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellWaveOfFlame', 'run', 'SpellWaveOfFlame_run', 0x317000, 'ref_skills_c.waveofflame_spell_run', 'particle:3', 'spell'),
    ('SpellFrostArmor', 'cast', 'SpellFrostArmor_ctor', 0x317D1C, 'ref_skills_c.frostarmor_spell_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SpellFrostArmor', 'run', 'SpellFrostArmor_run', 0x317EC0, 'ref_skills_c.frostarmor_spell_run', 'particle:2', 'spell'),
    ('SpellFrostArmor', 'event', 'SpellFrostArmor_onHit', 0x318264, 'ref_skills_c.frostarmor_on_hit', 'fx_spawn:1', 'SHARED'),
    ('SpellDiseaseBlade', 'cast', 'SpellDiseaseBlade_ctor', 0x318AD4, 'ref_skills_c.diseaseblade_spell_ctor', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SkillFireAxe', 'cast', 'SkillFireAxe_cast', 0x31979C, 'ref_skills_c.fireaxe_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('SkillColdAxe', 'cast', 'SkillColdAxe_cast', 0x31A0D8, 'ref_skills_c.coldaxe_cast', 'LightEffect:1', 'SHARED SHARED(LightEffect)'),
    ('LightningStrikeSpell', 'cast', 'LightningStrikeSpell_ctor', 0x31AE48, 'ref_skills_c._storm_ctor', 'LightEffect:1 lightLink:1', 'SHARED(LightEffect)'),
    ('SpellConeOfShock', 'cast', 'SpellConeOfShock_ctor', 0x31BAC8, 'ref_skills_c.coneofshock_spell_ctor', 'lightLink:1', 'SHARED'),
    ('SmokeGen', 'draw', 'SmokeGen_draw', 0x31CBF8, 'ref_fx_skills.smokegen_draw', 'glow:1', ''),
)
Phase = namedtuple('Phase', 'cls phase function addr model calls generators')
RECIPES = {}
for _row in _RECIPE_ROWS:
    RECIPES.setdefault(_row[0], []).append(Phase(*_row))
PHASES = ('cast', 'run', 'draw', 'event')


def recipe(cls):
    """The rows of one effect class, in address order."""
    return list(RECIPES.get(cls, ()))


def classes():
    return sorted(RECIPES)


def model_method(row):
    """(module name, method name) of a recipe row."""
    module, _, method = row.model.partition('.')
    return module, method


# ---------------------------------------------------------------------------------------
# 3. Models of the functions the skill models did not have
# ---------------------------------------------------------------------------------------
EXTERNALS = dict(SC.EXTERNALS)
EXTERNALS.update({
    'isNearView': Ext(0x1E77C0, 'v', 1, 'i', '(position; radius) -> 1 when the camera focus is near (per machine)'),
    'trail_addPoint': Ext(0x192550, 'iv', 0, 'n', '(handle, point)'),
    'trail_release': Ext(0x192800, 'i', 0, 'n', '(handle)'),
    'obj_addToAlwaysDraw': Ext(0x14EDD8, 'p', 0, 'n', '(object): drawn even when not active'),
    'path_blockNodes': Ext(0x18B6C0, 'pv', 1, 'n', '(world, position; radius): raises the block counter of the path nodes '
                           'around (tools/ref_world.py path_block_nodes)'),
    'mem_allocTagged': Ext(0x14FF88, 'ip', 0, 'i', '(size, tag) -> block'),
    'Creature.v0': Ext(0, '', 0, 'i', 'table slot 0: the type-info getter of the object\'s class (typeid)'),
    'rtti_typeInfoEquals': Ext(0x3B1250, 'ii', 0, 'i', '(type, type) -> 1 when equal'),
})
MODELLED = dict(SC.MODELLED)
TYPEINFO = dict(SC.TYPEINFO, StaticFire=0x3C7318)
SPELL_TABLES = set(SC.SPELL_TABLES) | {0x51AE58, 0x51AE28}      # HornOmen, PlanarSteel: destructors stay call-outs
DRAW_MODELLED = {}                              # name -> address, the functions of part 3


def shape_result(name, args, ret=0, fret=0, outs=None):
    """ref_skills_c.shape_result over this module's EXTERNALS."""
    saved = SC.EXTERNALS
    SC.EXTERNALS = EXTERNALS
    try:
        return SC.shape_result(name, args, ret, fret, outs)
    finally:
        SC.EXTERNALS = saved


def _register(name, addr):
    MODELLED[name] = addr
    DRAW_MODELLED[name] = addr


def _from_uint(v):
    """cvt.s.w of an unsigned value, the compiler's way: halve (keeping the low bit) and
    double when bit 31 is set."""
    v &= M32
    if v < 0x80000000:
        return C.from_int(v)
    half = C.from_int((v >> 1) | (v & 1))
    return C.add(half, half)


def _angle_shift(word, left):
    """(u16 word << left) >> 16, arithmetic: an angle built from the frame counter."""
    return s32(((word & 0xFFFF) << left) & M32) >> 16


class Calls:
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)


class Draws:
    """The draw slots that queue glow sprites (GameObject slot 5, Spell slot 3).  They run
    once per rendered frame; nothing here changes game state."""

    def shock_draw(self, obj):
        """ShockProjectile_draw 0x2c4e64.  t = min(1, (expiry +0x58 - frame + 300) / 30)
        (no lower bound); one glow at the position: grey 0x80, alpha int(128 t), size
        int(15152 t + sin16(frame mod 0x8000 x 0x1dd7) x int(15152 t x 0.195006)),
        bias 0, texture *0x4f8498, angle (frame << 26) >> 16, flags 1 (turned quad)."""
        u32 = self.u32
        frame = s32(u32(G_SIM_FRAME))
        t = C.mul(C.from_int(s32(u32(obj + 0x58)) - frame + 300), 0x3D088888)
        if C.lt(ONE, t):
            t = ONE
        rem = frame - int(frame / 0x8000) * 0x8000
        s = C.sin16((rem * 0x1DD7) & M32)
        big = C.mul(t, 0x466CC000)
        alpha = C.to_int(C.mul(t, 0x43000000))
        k = C.from_int(C.to_int(C.mul(big, 0x3E47AFA7)))
        size = C.from_int(C.to_int(C.add(big, C.mul(s, k))))
        angle = _angle_shift(u32(G_SIM_FRAME), 26)
        self.call('glow_add', self.vec(obj + 0x10), 0x80, 0x80, 0x80, alpha, u32(G_GLOW_TEX_C), angle, 1, ZERO, size)

    def firearrow_draw(self, obj):
        """FireArrowProjectile_draw 0x2d67e8: one glow at the arrow, size radius +0x1c x
        1408, bias 10, colour (0x93, 0x62, 0x49), alpha 0x49, texture *0x4f8494, angle 0,
        flags 6 (additive, second pass)."""
        size = C.mul(self.u32(obj + 0x1C), 0x44B00000)
        self.call('glow_add', self.vec(obj + 0x10), 0x93, 0x62, 0x49, 0x49, self.u32(G_GLOW_TEX_B), 0, 6,
                  0x41200000, size)

    def holystrike_draw(self, obj):
        """HolyStrike_draw 0x2ecd90: one glow one unit off the object sideways (the unit
        vector (dir.y, -dir.x, 0) of the direction +0x6c, +0x70) and one unit up; size
        5000 + 250 sin16(frame << 10), bias 5, colour (250, 200, 100), alpha 0x80, texture
        *0x4f8498, angle (frame << 25) >> 16, flags 3."""
        u32 = self.u32
        d0, d1, d2 = u32(obj + 0x70), C.neg(u32(obj + 0x6C)), ZERO
        length2 = C.add(C.add(C.mul(d0, d0), C.mul(d1, d1)), C.mul(d2, d2))
        r = C.rsqrt(ONE, length2)
        n = (C.mul(d0, r), C.mul(d1, r), C.mul(d2, r))
        p = self.vec(obj + 0x10)
        point = (C.add(C.add(n[0], ZERO), p[0]), C.add(C.add(n[1], ZERO), p[1]), C.add(C.add(n[2], ONE), p[2]))
        s = C.sin16((u32(G_SIM_FRAME) << 10) & M32)
        size = C.add(C.mul(s, 0x437A0000), 0x459C4000)
        angle = _angle_shift(u32(G_SIM_FRAME), 25)
        self.call('glow_add', point, 0xFA, 0xC8, 0x64, 0x80, u32(G_GLOW_TEX_C), angle, 3, 0x40A00000, size)

    def badger_draw(self, spell):
        """SpellSummonBadger_draw 0x311034, Spell slot 3.  Needs the badger (handle +0x18).
        f = +0x1c, folded above 1 to 1 - (f - 1) and clamped at 0; nothing when f <= 0.
        One glow at every sample point of the badger's model (slot 16 gives the model):
        size = the second output's x + 250 sin16(frame << 10), bias 12, colour (0x54, 0xc0,
        0x33), alpha int(65 f), texture *0x4f848c, angle (frame << 22) >> 16, flags 7."""
        u32 = self.u32
        node = u32(spell + 0x18)
        if not node:
            return
        badger = u32(node + 0xC)
        if not badger:
            return
        f = u32(spell + 0x1C)
        if C.lt(ONE, f):
            f = C.sub(ONE, C.sub(f, ONE))
            if C.lt(f, ZERO):
                f = ZERO
        if C.le(f, ZERO):
            return
        count = s32(self.call('model_getSamplePointCount', self.vcall(badger, 16)))
        at = self.visual_pos(badger)
        index = 0
        while index < count:
            model = self.vcall(badger, 16)
            point, extra = self.call('model_getSamplePoint', model, badger + 0x114, tuple(at), self.s16(badger + 0x38),
                                     index, 1, 0, u32(badger + 0xDC))
            index += 1
            s = C.sin16((u32(G_SIM_FRAME) << 10) & M32)
            size = C.add(extra[0], C.mul(s, 0x437A0000))
            alpha = C.to_int(C.mul(f, 0x42820000))
            angle = _angle_shift(u32(G_SIM_FRAME), 22)
            self.call('glow_add', point, 0x54, 0xC0, 0x33, alpha, u32(G_GLOW_TEX_A), angle, 7, 0x41400000, size)

    def resurrect_draw(self, spell):
        """SpellResurrect_draw 0x312f48, Spell slot 3.  Only with one player in the session
        (*0x4d8ae0 == 1).  f = 0 while +0x20 is 0, else min(1, (frame - +0x6c, unsigned)
        / 60).  Thirteen glows on a ring of radius int(100 f) + 15 around the owner (+0x18),
        116 above its position; angles start at frame x 0x75 and step 0x13b1 (16 bits),
        (x, y) = owner + (sin16, cos16) x radius; size 5000, bias 10, colour (0x6f, 0x38,
        0x28), alpha int((1 - f) x 128), texture *0x44fe04, angle 0, flags 2."""
        u32 = self.u32
        if s32(u32(G_NUM_PLAYERS)) != 1:
            return
        frame = u32(G_SIM_FRAME)
        angle = (frame * 0x75) & 0xFFFF
        if not u32(spell + 0x20):
            f = ZERO
        else:
            f = C.fmin(C.mul(_from_uint(frame - u32(spell + 0x6C)), 0x3C888888), ONE)
        radius_i = C.to_int(C.mul(f, 0x42C80000))
        alpha = C.to_int(C.mul(C.sub(ONE, f), 0x43000000))
        for _ in range(13):
            s = C.sin16(angle)
            radius = C.from_int(radius_i + 15)
            owner = u32(spell + 0x18)
            x = C.add(u32(owner + 0x10), C.mul(s, radius))
            c = C.cos16(angle)
            y = C.add(u32(owner + 0x14), C.mul(c, radius))
            z = C.add(u32(owner + 0x18), 0x42E80000)
            self.call('glow_add', (x, y, z), 0x6F, 0x38, 0x28, alpha, u32(G_GLOW_TEX_RES), 0, 2, 0x41200000, 0x459C4000)
            angle = (angle + 0x13B1) & 0xFFFF

    def smokegen_draw(self, obj):
        """SmokeGen_draw 0x31cbf8: when isNearView(position; 1000), one glow per live puff
        of the ring at +0x50 (100 records of five s16: x, y, z-and-age, two more; first
        +0x438, end +0x43a).  t = age / (lifetime +0x464 x 60 x speed +0x474); point =
        position + (x, y) / 32, z = position.z + age / 32 + rise +0x47c; size, colour and
        alpha run linearly from +0x45c / +0x43c..+0x448 to +0x460 / +0x44c..+0x458; bias 5,
        texture +0x4c, angle s16(+0x488 x +0x472), negated on odd records, flags 5."""
        u32, s16_ = self.u32, self.s16
        if not self.call('isNearView', self.vec(obj + 0x10), 0x447A0000):
            return
        span = C.mul(C.from_int(s32(u32(obj + 0x464)) * 60), u32(obj + 0x474))
        i = s16_(obj + 0x438)
        end = s16_(obj + 0x43A)
        while i != end:
            rec = obj + 0x50 + i * 10
            age = C.from_int(s16_(rec + 4))
            t = C.div(age, span)
            z = C.add(C.add(u32(obj + 0x18), C.mul(age, 0x3D000000)), u32(obj + 0x47C))
            x = C.add(u32(obj + 0x10), C.mul(C.from_int(s16_(rec)), 0x3D000000))
            y = C.add(u32(obj + 0x14), C.mul(C.from_int(s16_(rec + 2)), 0x3D000000))

            def lerp(a_off, b_off):
                a = s32(u32(obj + a_off))
                return C.add(C.from_int(a), C.mul(C.from_int(s32(u32(obj + b_off)) - a), t))
            colour = [C.to_int(lerp(0x43C + 4 * k, 0x44C + 4 * k)) for k in range(4)]
            size = lerp(0x45C, 0x460)
            angle = s16((s32(u32(obj + 0x488)) * s16_(obj + 0x472)) & 0xFFFF)
            if i & 1:
                angle = s16((-angle) & 0xFFFF)
            self.call('glow_add', (x, y, z), colour[0], colour[1], colour[2], colour[3], u32(obj + 0x4C), angle, 5,
                      0x40A00000, size)
            i += 1
            if i == 100:
                i = 0


_register('ShockProjectile_draw', 0x2C4E64)
_register('FireArrowProjectile_draw', 0x2D67E8)
_register('HolyStrike_draw', 0x2ECD90)
_register('SpellSummonBadger_draw', 0x311034)
_register('SpellResurrect_draw', 0x312F48)
_register('SmokeGen_draw', 0x31CBF8)


class MultiFire:
    """MultiFireProjectile (the arrows of Multi Fire): a projectile with a grey trail and
    a stream of particles, all placed with the arrow's OWN generator (+0x44)."""
    MF_VT = 0x519128
    MF_PARTICLE = 0x8E5910
    MF_LUMP, MF_SOUND_FIRE, MF_SOUND_DUST = 0x54F560, 0x54F598, 0x54F5B0
    LEVEL_FLAGS = 0x44FE08                      # level flag word; 0x40000 selects the fire burst

    def multifire_ctor(self, obj, pos, angle, owner, level, skill):
        """MultiFireProjectile_ctor 0x2da164 (object, position, angle, owner, level, skill).
        Projectile_ctor(object, position, owner, 0) (one shared draw inside); angle s16
        +0x64, table, radius +0x1c = 8, skill +0x70, level +0x68; speed = skill slot 13 (1,
        level, owner handle +0x4c, 10); velocity +0x54 = speed x (cos16, sin16)(angle), 0;
        age +0x6c and ended +0x60 = 0; trail_create(row 1, width 0x7a, flags 0, grey 0x80,
        alpha 0x20; 0.15 s) -> +0x74, its first point at the position; the run list."""
        u32, w32 = self.u32, self.w32
        angle = s16(angle)
        self.call('Projectile_ctor', obj, tuple(pos), owner, 0)
        self.w16(obj + 0x64, angle)
        w32(obj + 0x48, self.MF_VT)
        w32(obj + 0x1C, 0x41000000)
        w32(obj + 0x70, skill)
        w32(obj + 0x68, level)
        speed = C.from_int(s32(self.skill_call(skill, 13, 1, level, obj + 0x4C, 10)))
        w32(obj + 0x54, C.mul(C.cos16(self.s16(obj + 0x64)), speed))
        sine = C.sin16(self.s16(obj + 0x64))
        w32(obj + 0x5C, 0)
        w32(obj + 0x6C, 0)
        w32(obj + 0x60, 0)
        w32(obj + 0x58, C.mul(sine, speed))
        handle = self.call('trail_create', 1, 0x7A, 0, 0x80, 0x80, 0x80, 0x20, 0x3E199999)
        w32(obj + 0x74, handle)
        self.call('trail_addPoint', handle, self.vec(obj + 0x10))
        self.call('obj_runEveryFrame', obj)

    def multifire_run(self, obj):
        """MultiFireProjectile_run 0x2da2bc, GameObject slot 4.  Nothing once ended.  A trail
        point at the position, age + 1, obj_moveAndCollide with the velocity; terrain (bit
        1): end(1); age 601 or more: end(0); else ten particles 0x8e5910: v = 8 x a unit-ball
        point, position + v x r (r = one more draw / 65536), velocity v."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        self.call('trail_addPoint', u32(obj + 0x74), self.vec(obj + 0x10))
        self.w32(obj + 0x6C, u32(obj + 0x6C) + 1)
        result = self.call('obj_moveAndCollide', obj, self.vec(obj + 0x54))
        if result & 1:
            return self.multifire_end(obj, 1)
        if not self.s32(obj + 0x6C) < 0x259:
            return self.multifire_end(obj, 0)
        for _ in range(10):
            ball = self.obj_ball(obj)
            v = tuple(C.mul(b, 0x41000000) for b in ball)
            share = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
            step = tuple(C.mul(v[k], share) for k in range(3))
            p = self.vec(obj + 0x10)
            self.call('particle_spawn', self.MF_PARTICLE, tuple(C.add(p[k], step[k]) for k in range(3)), v, ZERO)

    def multifire_end(self, obj, reason):
        """MultiFireProjectile_end 0x2da928 (object, reason), once (ended +0x60).  The trail
        is released; with a reason, one own draw picks one of four impact sounds and
        fx_spawn(8) at the position when level flag 0x40000 is set, else fx_spawn(2) (dust),
        then the sound on the object; obj_delete; ended = 1."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        self.call('trail_release', u32(obj + 0x74))
        if reason:
            fire = u32(self.LEVEL_FLAGS) & 0x40000
            draw = self.obj_rand(obj)
            text = self.call('libc_sprintf', self.MF_SOUND_FIRE if fire else self.MF_SOUND_DUST, (draw & 3) + 1)
            self.call('fx_spawn', 8 if fire else 2, self.vec(obj + 0x10))
            self.call('sound_playOnObject', self.call('res_find', self.MF_LUMP, text), obj, ONE)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)


_register('MultiFireProjectile_ctor', 0x2DA164)
_register('MultiFireProjectile_run', 0x2DA2BC)
_register('MultiFireProjectile_end', 0x2DA928)


class FireStormFlare:
    """FireStormFlare: the falling fire balls of Fire Storm (skill 7).  Every particle is
    placed with the flare's OWN generator (+0x44); nothing here draws the shared seed."""
    FSF_PARTICLES = (0x8E5640, 0x8E5690, 0x8E56E0)
    FSF_LUMP, FSF_SOUND = 0x54F110, 0x54F138

    def _fsf_trail(self, obj, nv, per_scale, definition, speed=None, z_extra=None):
        """One of the three trail streams of a falling flare: while i < scale x per_scale,
        p = unit-ball x (scale x 8.7999935) + position, moved back along the velocity by r
        (one draw / 65536); velocity = a second ball point, scaled by `speed` (z once more
        by z_extra), or the raw point."""
        u32 = self.u32
        i = 0
        while C.lt(C.from_int(i), C.mul(u32(obj + 0x4C), per_scale)):
            ball = self.obj_ball(obj)
            k = C.mul(u32(obj + 0x4C), 0x410CCCC6)
            pos = self.vec(obj + 0x10)
            p = [C.add(C.mul(ball[j], k), pos[j]) for j in range(3)]
            share = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
            p = tuple(C.add(p[j], C.mul(nv[j], share)) for j in range(3))
            v = self.obj_ball(obj)
            if speed is not None:
                v = (C.mul(v[0], speed), C.mul(v[1], speed), C.mul(C.mul(v[2], speed), z_extra))
            self.call('particle_spawn', definition, p, tuple(v), ZERO)
            i += 1

    def firestormflare_run(self, obj):
        """FireStormFlare_run 0x2d33c0, GameObject slot 4.

        Falling (landed +0x50 = 0 and frame < expiry +0x68): vz += -0.39999998, position +=
        velocity +0x5c..+0x64; three particle streams with the reversed velocity (scale
        +0x4c): x30 of 0x8e5640 (speed 10.419806, z x 10.261909), x18 of 0x8e5690 (5.0619698,
        z x 7.171931), x4 of 0x8e56e0 (raw ball); then terrain_height(world, position;
        radius +0x1c): less than 16 above the ground lands it (+0x50 = 1) with a sound.
        Landed, while the ring +0x58 (s16) is below radius x 3 x scale: ring += 7 and 85
        pairs of particles (0x8e5640 and 0x8e5690, the same point and velocity) at angle =
        one draw, ring x (cos16, sin16) + 6.76 x a ball point + position, velocity a second
        ball point.  Then: one draw % 100 < 33 lowers z by 6 and lays a scorch decal (type 9,
        no growth, size = scale, angle = s16 of one more draw); slot 1 (3) destroys it."""
        u32, w32 = self.u32, self.w32
        if not u32(obj + 0x50) and s32(u32(G_SIM_FRAME)) < self.s32(obj + 0x68):
            w32(obj + 0x64, C.add(u32(obj + 0x64), 0xBECCCCCC))
            for j in range(3):
                w32(obj + 0x10 + 4 * j, C.add(u32(obj + 0x10 + 4 * j), u32(obj + 0x5C + 4 * j)))
            nv = tuple(C.neg(u32(obj + 0x5C + 4 * j)) for j in range(3))
            self._fsf_trail(obj, nv, 0x41F00000, self.FSF_PARTICLES[0], 0x4126B786, 0x412430C7)
            self._fsf_trail(obj, nv, 0x41900000, self.FSF_PARTICLES[1], 0x40A1FBA8, 0x40E58075)
            self._fsf_trail(obj, nv, 0x40800000, self.FSF_PARTICLES[2])
            ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
            if C.lt(C.sub(u32(obj + 0x18), ground), 0x41800000):
                w32(obj + 0x50, 1)
                self.call('sound_playOnObject', self.call('res_find', self.FSF_LUMP, self.FSF_SOUND), obj, ONE)
            return
        if C.lt(C.from_int(self.s16(obj + 0x58)), C.mul(C.mul(u32(obj + 0x1C), 0x40400000), u32(obj + 0x4C))):
            self.w16(obj + 0x58, self.u16(obj + 0x58) + 7)
            for _ in range(0x55):
                draw = self.obj_rand(obj)
                cx = C.mul(C.cos16(draw), C.from_int(self.s16(obj + 0x58)))
                sy = C.mul(C.sin16(draw), C.from_int(self.s16(obj + 0x58)))
                ring = (cx, sy, ZERO)
                ball = self.obj_ball(obj)
                pos = self.vec(obj + 0x10)
                p = tuple(C.add(C.add(ring[j], C.mul(ball[j], 0x40D851EB)), pos[j]) for j in range(3))
                v = self.obj_ball(obj)
                self.call('particle_spawn', self.FSF_PARTICLES[0], p, v, ZERO)
                self.call('particle_spawn', self.FSF_PARTICLES[1], p, v, ZERO)
            return
        if self.obj_rand(obj) % 100 < 0x21:
            w32(obj + 0x18, C.sub(u32(obj + 0x18), 0x40C00000))
            draw = self.obj_rand(obj)
            self.call('decal_add', self.vec(obj + 0x10), s16(draw), 9, 0, u32(obj + 0x4C))
        if obj:
            self.vcall(obj, 1, 3)


_register('FireStormFlare_run', 0x2D33C0)


class Pustule:
    """Pustule: the falling blobs of Pus Storm (skills 80 / 100).  It falls with a dribble
    of particles, bursts on its floor into ten drops that arc out under gravity, each
    leaving one particle a tick, and is destroyed 300 ticks after launch or 36 ticks after
    the burst.  OWN generator (+0x44) throughout."""
    PUS_FALL, PUS_DROP = 0x8E7548, 0x8E74F8
    PUS_LUMP, PUS_SOUND = 0x552328, 0x552388

    def pustule_run(self, obj):
        """Pustule_run 0x30bde0, GameObject slot 4.  Timer +0x64, burst flag +0x6c,
        velocity +0x58, floor +0x54, drops: positions +0x70 and velocities +0xe8 (10 x 12)."""
        u32, w32 = self.u32, self.w32
        timer = s32(u32(obj + 0x64))
        if u32(obj + 0x6C) and C.lt(0x420ECCFB, C.from_int(timer)):
            if obj:
                self.vcall(obj, 1, 3)
            return
        if not timer < 0x12D:
            if obj:
                self.vcall(obj, 1, 3)
            return
        if not u32(obj + 0x6C):
            old = self.vec(obj + 0x10)
            w32(obj + 0x60, C.add(u32(obj + 0x60), 0xBE4CCAB3))
            d = []
            for j in range(3):
                now = C.add(u32(obj + 0x10 + 4 * j), u32(obj + 0x58 + 4 * j))
                w32(obj + 0x10 + 4 * j, now)
                d.append(C.sub(old[j], now))
            for _ in range(3):
                r = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
                pos = self.vec(obj + 0x10)
                p = tuple(C.add(pos[j], C.mul(d[j], r)) for j in range(3))
                self.call('particle_spawn', self.PUS_FALL, p, (ZERO, ZERO, ZERO), ZERO)
            if C.le(u32(obj + 0x18), u32(obj + 0x54)):
                w32(obj + 0x64, 0)
                w32(obj + 0x6C, 1)
                self.call('sound_playAtPos', self.call('res_find', self.PUS_LUMP, self.PUS_SOUND),
                          self.vec(obj + 0x10), ONE)
                base = self.vec(obj + 0x10)
                ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), 0x41000000)
                base = (base[0], base[1], C.add(ground, 0x41400000))
                for i in range(10):
                    r1 = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
                    a = self.obj_rand(obj)
                    x = C.add(base[0], C.mul(C.mul(r1, C.cos16(a)), 0x40C3693C))
                    y = C.add(base[1], C.mul(C.mul(r1, C.sin16(a)), 0x40C3693C))
                    a2 = self.obj_rand(obj)
                    r2 = C.mul(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), 0x3F49FB1E)
                    vx = C.mul(C.mul(C.cos16(a2), r2), 0x408DAF39)
                    vy = C.mul(C.mul(C.sin16(a2), r2), 0x408DAF39)
                    self.wvec(obj + 0x70 + 12 * i, (x, y, base[2]))
                    self.wvec(obj + 0xE8 + 12 * i, (vx, vy, C.mul(ONE, 0x408DAF39)))
            if not u32(obj + 0x6C):
                w32(obj + 0x64, u32(obj + 0x64) + 1)
                return
        for i in range(10):
            p_at, v_at = obj + 0x70 + 12 * i, obj + 0xE8 + 12 * i
            for j in range(3):
                w32(p_at + 4 * j, C.add(u32(p_at + 4 * j), u32(v_at + 4 * j)))
            w32(v_at + 8, C.add(u32(v_at + 8), 0xBEE1C9F7))
            k = C.mul(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), 0x40A729F7)
            v = tuple(C.mul(u32(v_at + 4 * j), k) for j in range(3))
            ball = self.obj_ball(obj)
            p = tuple(C.add(C.mul(ball[j], 0x403FEE34), u32(p_at + 4 * j)) for j in range(3))
            self.call('particle_spawn', self.PUS_DROP, p, v, ZERO)
        w32(obj + 0x64, u32(obj + 0x64) + 1)


_register('Pustule_run', 0x30BDE0)


class DiseaseCloud:
    """DiseaseCloud: a growing ball of disease particles that also hurts.  Every 30th
    frame it damages what is in its box (gameplay: damage_apply with a disease entry and
    NO attacker).  Particles use the cloud's OWN generator (+0x44)."""
    DC_PARTICLES = (0x8E5320, 0x8E5370, 0x8E53C0)

    def diseasecloud_run(self, obj):
        """DiseaseCloud_run 0x2ce6e0, GameObject slot 4.  Until frame reaches +0x54: the
        radius +0x5c grows by 0.5 while below the integer +0x58; three streams of +0x58 / 10
        particles each at radius x a unit-ball point around the position, velocity a second
        ball point x 6, x 6 and x 12; on frames divisible by 30, every object in the box
        position -+ int(radius) other than the owner (+0x4c) - two players are skipped -
        takes damage_apply(victim, 0, 100000, 0, 0, 0x1000040, entry (0x26, +0x60, +0x60, 0),
        0; 0, 0).  At the end slot 1 (3) destroys it."""
        u32, w32 = self.u32, self.w32
        frame = s32(u32(G_SIM_FRAME))
        if not frame < self.s32(obj + 0x54):
            if obj:
                self.vcall(obj, 1, 3)
            return
        if C.lt(u32(obj + 0x5C), C.from_int(self.s32(obj + 0x58))):
            w32(obj + 0x5C, C.add(u32(obj + 0x5C), C.HALF))
        for definition, speed in zip(self.DC_PARTICLES, (0x40C00000, 0x40C00000, 0x41400000)):
            i = 0
            while i < int(self.s32(obj + 0x58) / 10):
                ball = self.obj_ball(obj)
                radius = u32(obj + 0x5C)
                pos = self.vec(obj + 0x10)
                p = tuple(C.add(C.mul(ball[j], radius), pos[j]) for j in range(3))
                v = tuple(C.mul(b, speed) for b in self.obj_ball(obj))
                self.call('particle_spawn', definition, p, v, ZERO)
                i += 1
        if frame - int(frame / 30) * 30:
            return
        h = C.from_int(C.to_int(u32(obj + 0x5C)))
        pos = self.vec(obj + 0x10)
        low = tuple(C.sub(pos[j], h) for j in range(3))
        high = tuple(C.add(pos[j], h) for j in range(3))
        found = self.call('world_collectObjectsInBox', low, high, 0x40)
        for victim in found or ():
            node = u32(obj + 0x4C)
            if not node:
                continue
            owner = u32(node + 0xC)
            if owner == victim:
                continue
            if u32(owner + 0xC) & 0x40 and u32(victim + 0xC) & 0x40:
                continue
            v = u32(obj + 0x60)
            self.call('damage_apply', victim, 0, 100000, 0, 0, 0x1000040, SC.desc((0x26, v, v, 0)), 0, ZERO, ZERO)


_register('DiseaseCloud_run', 0x2CE6E0)


class Arena:
    """SpellArena: the spell an arena puts on a fighter while the arena counter 0x5038c8
    (s16) runs.  Placement uses the SPELL's own generator (+0x10, Spell_rand)."""
    G_ARENA_COUNTER = 0x5038C8
    ARENA_PARTICLES = (0x8E71E0, 0x8E7190)
    ARENA_TINT = (0x56, 0x35, 0x21, 0x3D)

    def arena_run(self, spell, pos):
        """SpellArena_run 0x305bbc, Spell slot 2 (spell, position).  On the creature +0xc:
        object flag 2 is set when the counter is 61 or more, cleared below.  From counter 30
        on: f = 1 - (counter - 30) x 0.0066666664; int(23 f) particles, each at a random
        sample point of the creature's model (index = draw % count) moved back by v x
        7.5742016, velocity v = (cos16, sin16, 0)(one draw) x (1 - f) x 10; every fourth
        (i % 4 == 0) of definition 0x8e71e0, the rest 0x8e7190.  Then both tint colours
        (+0x90.. and +0x98..) are set to (0x56, 0x35, 0x21, 0x3d)."""
        u32 = self.u32
        counter = self.s16(self.G_ARENA_COUNTER)
        c = u32(spell + 0xC)
        flags = u32(c + 0xC)
        self.w32(c + 0xC, (flags & ~2) if counter < 0x3D else (flags | 2))
        if counter < 0x1E:
            return
        f = C.sub(ONE, C.mul(C.sub(C.from_int(counter), 0x41F00000), 0x3BDA740D))
        count = s32(self.call('model_getSamplePointCount', self.vcall(u32(spell + 0xC), 16)))
        n = C.to_int(C.mul(f, 0x41B80000))
        i = 0
        while i < n:
            model = self.vcall(u32(spell + 0xC), 16)
            draw = self.spell_rand(spell)
            c = u32(spell + 0xC)
            index = s32(draw) % count if count else 0
            point, _extra = self.call('model_getSamplePoint', model, c + 0x114, self.vec(c + 0x10), self.s16(c + 0x38),
                                      index, 1, 0, ONE)
            k = C.mul(C.sub(ONE, f), 0x41200000)
            a = self.spell_rand(spell)
            v = (C.mul(C.cos16(a), k), C.mul(C.sin16(a), k), C.mul(ZERO, k))
            p = tuple(C.sub(point[j], C.mul(v[j], 0x40F25FDC)) for j in range(3))
            self.call('particle_spawn', self.ARENA_PARTICLES[0 if i & 3 == 0 else 1], p, v, ZERO)
            i += 1
        c = u32(spell + 0xC)
        for k, value in enumerate(self.ARENA_TINT + self.ARENA_TINT):
            self.w16(c + 0x90 + 2 * k, value)


_register('SpellArena_run', 0x305BBC)


class HornOmen:
    """SpellHornOmenEffect: a ten-second glow on a creature made by a script command
    (caller 0x146628).  Its particles go into the spell's own particle GROUP, in model
    space: the group matrix is the creature's position turned by its facing, set every
    tick (mat34_setPosRotZ 0x163b30 -> particleGroup_setMatrix).  SPELL generator (+0x10)."""
    HO_VT = 0x51AE58
    HO_PARTICLE = 0x8E6C40

    def hornomen_ctor(self, spell, kind, owner, extra):
        """SpellHornOmenEffect_ctor 0x2fc574 (spell, kind byte, creature, word): the Spell
        base (ONE SHARED DRAW seeds the spell generator +0x10), group +0x1c =
        particleGroup_create(), end +0x18 = frame + 600."""
        self.w8(spell, kind)
        self.w32(spell + 0x14, VT_SPELL)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 8, extra)
        self.w32(spell + 4, 0)
        seed = self.draw()
        self.w32(spell + 0x14, self.HO_VT)
        self.w32(spell + 0x10, seed)
        self.w32(spell + 0x1C, self.call('particleGroup_create'))
        self.w32(spell + 0x18, self.u32(G_SIM_FRAME) + 600)

    def hornomen_run(self, spell, pos):
        """SpellHornOmenEffect_run 0x2fc684, Spell slot 2 (spell, position).  Until the end
        +0x18: a = frame - end + 600 (ticks since the start).  Below 140: tint of the
        creature (+0x90.. and +0x98..) = int(t x (225, 20, 0, 100)) with t = a x
        0.0071428567, and int(150 t) particles; from 140 on the tint is (225, 20, 0, 100) and
        there are 150.  The group matrix is set and the particles go into the group: each at a
        random sample point of the creature's model taken at the origin with facing 0 (index =
        draw % count; none when the count is 0) + 3.0007868 x a ball point, velocity
        30.000292 x a second ball point, definition 0x8e6c40.  At the end slot 1 (3)."""
        u32 = self.u32
        frame = s32(u32(G_SIM_FRAME))
        if not frame < self.s32(spell + 0x18):
            if spell:
                self.table_call('Spell', spell, 0x14, 1, 3)
            return
        a = C.from_int(frame - self.s32(spell + 0x18) + 600)
        c = u32(spell + 0xC)
        early = C.lt(a, 0x430C0000)
        if early:
            t = C.mul(a, 0x3BEA0EA0)
            r, g, b = (C.to_int(C.mul(t, k)) for k in (0x43610000, 0x41A00000, 0x42C80000))
        else:
            r, g, b = 0xE1, 0x14, 100
        for base in (0x90, 0x98):
            self.w16(c + base, r)
            self.w16(c + base + 2, g)
            self.w16(c + base + 4, 0)
            self.w16(c + base + 6, b)
        # mat34_setPosRotZ 0x163b30 (modelled by ref_core, runs on the stack): the matrix
        self.call('particleGroup_setMatrix', u32(spell + 0x1C), 'stack')
        self.call('particleGroup_begin', u32(spell + 0x1C))
        count = s32(self.call('model_getSamplePointCount', self.vcall(u32(spell + 0xC), 16)))
        if count:
            i = 0
            while True:
                if early:
                    if not C.lt(C.from_int(i), C.mul(C.mul(a, 0x3BEA0EA0), 0x43160000)):
                        break
                elif i > 0x95:
                    break
                model = self.vcall(u32(spell + 0xC), 16)
                index = self.spell_rand(spell) % count
                point = self.call('model_getSamplePoint', model, u32(spell + 0xC) + 0x114, (ZERO, ZERO, ZERO), 0,
                                  index, 0, 0, ONE)
                ball = self.spell_ball(spell)
                p = tuple(C.add(point[j], C.mul(ball[j], 0x40400CE4)) for j in range(3))
                v = tuple(C.mul(x, 0x41F00099) for x in self.spell_ball(spell))
                self.call('particle_spawn', self.HO_PARTICLE, p, v, ZERO)
                i += 1
        self.call('particleGroup_end', u32(spell + 0x1C))


_register('SpellHornOmenEffect_ctor', 0x2FC574)
_register('SpellHornOmenEffect_run', 0x2FC684)


class PlanarSteel:
    """SpellPlanarSteelEffect: four seconds of steel-blue light, glows and sparks on a
    creature, made by a script command (caller 0x1466d4).  SPELL generator (+0x10); the
    constructor draws the shared seed once (the Spell base)."""
    PS_VT = 0x51AE28
    PS_BURST, PS_SPARK, PS_SPARK2, PS_FALL = 0x8E6BA0, 0x8E6B00, 0x8E6B50, 0x8E6BF0
    PS_LUMP, PS_SOUND_START, PS_SOUND_BURST = 0x551320, 0x551328, 0x551340

    def planarsteel_ctor(self, spell, kind, owner, extra):
        """SpellPlanarSteelEffect_ctor 0x2fb728 (spell, kind byte, creature, word): the
        Spell base (ONE SHARED DRAW), a light record at +0x30 (colour (0x4b, 0x4b, 200,
        0xff) twice, radius 0, 1 / 0 squared, 0.65) at the creature's position, linked;
        burst flag +0x20 = 0, end +0x24 = frame + 240, burst countdown +0x1c = int(height
        +0x20 x 3), orbit angles +0x18 = 0 and +0x1a = 0x7fff; the start sound."""
        w8, w16, w32, u32 = self.w8, self.w16, self.w32, self.u32
        w8(spell, kind)
        w32(spell + 0x14, VT_SPELL)
        w32(spell + 4, 0)
        seed = self.draw()
        w32(spell + 0xC, owner)
        w32(spell + 8, extra)
        w32(spell + 0x10, seed)
        w32(spell + 0x14, self.PS_VT)
        light = spell + 0x30
        inverse = C.div(ONE, ZERO)
        w8(light + 9, 0)
        self.wvec(spell + 0x60, self.vec(owner + 0x10))
        w32(light + 0x28, inverse)
        w32(light + 0x2C, 0x3F266666)
        for off, value in ((0xA, 0x4B), (0xC, 0x4B), (0xE, 200), (0x10, 0xFF),
                           (0x12, 0x4B), (0x14, 0x4B), (0x16, 200), (0x18, 0xFF)):
            w16(light + off, value)
        w32(light + 0x20, inverse)
        w32(light + 0x1C, ZERO)
        w32(light + 0x24, ZERO)
        w8(light + 8, 0)
        self.call('light_link', light)
        w8(spell, kind)
        w32(spell + 8, extra)
        w32(spell + 0xC, owner)
        w32(spell + 0x20, 0)
        w32(spell + 0x24, u32(G_SIM_FRAME) + 0xF0)
        w16(spell + 0x1C, C.to_int(C.mul(u32(owner + 0x20), 0x40400000)))
        w16(spell + 0x18, 0)
        w16(spell + 0x1A, 0x7FFF)
        self.call('sound_playAtPos', self.call('res_find', self.PS_LUMP, self.PS_SOUND_START),
                  self.vec(owner + 0x10), ONE)

    def planarsteel_run(self, spell, pos):
        """SpellPlanarSteelEffect_run 0x2fb9b4, Spell slot 2 (spell, position).  Until the
        end +0x24, with s = sin16(frame x 1000):
        - the light follows the creature; radius = (kind byte + 0x42) + 10 s, falloff its
          inverse square; creature tint (+0x90..) = int(49 s + 75), int(49 s + 75),
          int(49 s + 200), int(5 s + 15), the same at +0x98;
        - the countdown +0x1c falls by one; the first time it is negative: 60 particles
          0x8e6ba0 18 above the creature, velocity (100 cos a, 100 sin a, 20 r), a stepping
          by 0x444, and a sound;
        - two orbit points (angles +0x18, +0x1a, each -0x5dc a tick) 40 from the creature at
          the height of the countdown: a glow each (size 4000, bias 0, colour (k, k, k + 50,
          alpha k), k = int(40 s + 50), texture *0x4f8498, flags 2), 6 sparks 0x8e6b00
          (velocity 0.4 x ball) and 4 sparks 0x8e6b50 (6 x ball) at the point + 2 x ball;
        - 10 falling sparks 0x8e6bf0 within 40 of the position, 100..300 above it,
          velocity (0, 0, -80); 10 ground sparks 0x8e6b00 within 40 of the position, 5 above
          terrain_heightAtPoint, velocity (+-1 or 0, +-1 or 0, 0).
        At the end slot 1 (3) destroys it."""
        u32, w16, w32 = self.u32, self.w16, self.w32
        frame = s32(u32(G_SIM_FRAME))
        if not frame < self.s32(spell + 0x24):
            if spell:
                self.table_call('Spell', spell, 0x14, 1, 3)
            return
        s = C.sin16((frame * 1000) & M32)
        c = u32(spell + 0xC)
        self.wvec(spell + 0x60, self.vec(c + 0x10))
        self.call('light_relink', spell + 0x30)
        radius = C.add(C.from_int(self.s8(spell) + 0x42), C.mul(s, 0x41200000))
        m49 = C.mul(s, 0x42440000)
        hi = C.to_int(C.add(m49, 0x43480000))
        low = C.to_int(C.add(C.mul(s, 0x40A00000), 0x41700000))
        mid = C.to_int(C.add(m49, 0x42960000))
        w32(spell + 0x4C, radius)
        w32(spell + 0x54, radius)
        inverse = C.div(ONE, C.mul(radius, radius))
        c = u32(spell + 0xC)
        for base in (0x90, 0x98):
            w16(c + base, mid)
            w16(c + base + 2, mid)
            w16(c + base + 4, hi)
            w16(c + base + 6, low)
        w32(spell + 0x58, inverse)
        w32(spell + 0x50, inverse)
        count = (self.u16(spell + 0x1C) - 1) & 0xFFFF
        w16(spell + 0x1C, count)
        if count & 0x8000 and not u32(spell + 0x20):
            w32(spell + 0x20, 1)
            angle = 0
            for _ in range(60):
                vx = C.mul(C.cos16(angle), 0x42C80000)
                vy = C.mul(C.sin16(angle), 0x42C80000)
                vz = C.mul(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), 0x41A00000)
                c = u32(spell + 0xC)
                p = (C.add(u32(c + 0x10), ZERO), u32(c + 0x14), C.add(u32(c + 0x18), 0x41900000))
                self.call('particle_spawn', self.PS_BURST, p, (vx, vy, vz), ZERO)
                angle = s16(angle + 0x444)
            self.call('sound_playAtPos', self.call('res_find', self.PS_LUMP, self.PS_SOUND_BURST),
                      self.vec(u32(spell + 0xC) + 0x10), ONE)
        for i in range(2):
            a = (self.u16(spell + 0x18 + 2 * i) - 0x5DC) & 0xFFFF
            w16(spell + 0x18 + 2 * i, a)
            x = C.mul(C.cos16(s16(a)), 0x42200000)
            y = C.mul(C.sin16(self.s16(spell + 0x18 + 2 * i)), 0x42200000)
            k40 = C.mul(s, 0x42200000)
            c = u32(spell + 0xC)
            z = C.from_int(self.s16(spell + 0x1C))
            k = C.to_int(C.add(k40, 0x42480000))
            blue = C.to_int(C.add(k40, 0x42C80000))
            point = (C.add(x, u32(c + 0x10)), C.add(y, u32(c + 0x14)), C.add(z, u32(c + 0x18)))
            self.call('glow_add', point, k, k, blue, k, u32(G_GLOW_TEX_C), 0, 2, ZERO, 0x457A0000)
            for definition, count_, speed in ((self.PS_SPARK, 6, 0x3ECCCCCC), (self.PS_SPARK2, 4, 0x40C00000)):
                for _ in range(count_):
                    v = tuple(C.mul(b, speed) for b in self.spell_ball(spell))
                    b2 = self.spell_ball(spell)
                    p = tuple(C.add(C.add(b2[j], b2[j]), point[j]) for j in range(3))
                    self.call('particle_spawn', definition, p, v, ZERO)
        for _ in range(10):
            a = s16(self.spell_rand(spell))
            r = C.mul(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), 0x42200000)
            x = C.mul(C.cos16(a), r)
            y = C.mul(C.sin16(a), r)
            z = C.add(C.add(0x43480000, C.from_int(self.spell_rand(spell) % 200)), 0xC2C80000)
            p = (C.add(x, pos[0]), C.add(y, pos[1]), C.add(z, pos[2]))
            self.call('particle_spawn', self.PS_FALL, p, (ZERO, ZERO, 0xC2A00000), ZERO)
        for _ in range(10):
            a = s16(self.spell_rand(spell))
            r = C.mul(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), 0x42200000)
            x = C.mul(C.cos16(a), r)
            y = C.mul(C.sin16(a), r)
            vx = C.add(C.from_int(self.spell_rand(spell) & 1), C.MINUS_ONE)
            vy = C.add(C.from_int(self.spell_rand(spell) & 1), C.MINUS_ONE)
            p = (C.add(x, pos[0]), C.add(y, pos[1]), C.add(ZERO, pos[2]))
            ground = self.call('terrain_heightAtPoint', u32(G_WORLD), p)
            p = (p[0], p[1], C.add(ground, 0x40A00000))
            self.call('particle_spawn', self.PS_SPARK, p, (vx, vy, ZERO), ZERO)


_register('SpellPlanarSteelEffect_ctor', 0x2FB728)
_register('SpellPlanarSteelEffect_run', 0x2FB9B4)


def _cstr(mem_u8, addr, limit=256):
    out = bytearray()
    while len(out) < limit:
        b = mem_u8(addr + len(out))
        if not b:
            break
        out.append(b)
    return bytes(out)


class StaticFire:
    """StaticFire: a fire burning on the ground (left by fire bombs and other attacks,
    ctor 0x2c5240; or placed in a level with properties, ctor2 0x2c54f8).  It blocks path
    nodes, has its own light (+0x80), keeps a ring of rising flame points at +0x4a4 (10-byte
    records: x, y, z in 1/16 units, drift x, y), spawns flame particles and embers, damages
    what stands in it every 12th frame - all of that only while isNearView(941) - and draws
    a glow per flame point.  OWN generator (+0x44) for everything visual; ONE SHARED DRAW
    per player it burns (the damage roll)."""
    SF_VT = 0x50DA38
    SF_TYPEINFO = 0x3C7318
    SF_FLAME, SF_EMBER = 0x8E4C90, 0x8E4D30
    LEVEL_NAME = 0x41B721                       # the current level's name
    SF_LEVEL_CUTSCENE, SF_LEVEL_DARK = 0x54E778, 0x54E788
    SF_PROPS = (0x54E728, 0x54E730, 0x54E740, 0x54E750, 0x54E758, 0x54E760)
    SF_SKILL = 0x41B1A4                         # g_skillTable[13]: Fire Weapons, whose tier-2 statistic sets player burns

    def _sf_light(self, obj, pos, colour, alpha_word):
        """The light record +0x80 both constructors fill: radius 120, 1 / 120^2, the
        given float at +0x2c, colour shorts, position = pos + (0, 0, 36)."""
        light = obj + 0x80
        self.w8(light + 9, 0)
        self.wvec(obj + 0xB0, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], 0x42100000)))
        for off, value in ((0x24, 0x42F00000), (0x28, 0x3891A2B3), (0x2C, alpha_word),
                           (0x1C, 0x42F00000), (0x20, 0x3891A2B3)):
            self.w32(light + off, value)
        for off, value in zip((0xA, 0xC, 0xE, 0x10, 0x12, 0x14, 0x16, 0x18), colour):
            self.w16(light + off, value)
        self.w8(light + 8, 0)
        self.call('light_link', light)

    def staticfire_wind(self, obj, angle):
        """0x2c6aa8 (object, angle): the drift +0x72, +0x74 = int(3.733333 x the unit
        vector of the angle) (s16), then one draw picks every fourth flame point of the ring
        (index % 4 == draw % 4), whose drift takes the new drift added."""
        c = C.cos16(angle)
        s = C.sin16(angle)
        r = C.rsqrt(ONE, C.add(C.mul(c, c), C.mul(s, s)))
        self.w16(obj + 0x74, C.to_int(C.mul(C.mul(s, r), 0x406EEEEE)))
        self.w16(obj + 0x72, C.to_int(C.mul(C.mul(c, r), 0x406EEEEE)))
        pick = self.obj_rand(obj) & 3
        i = self.s16(obj + 0x7A)
        while i != self.s16(obj + 0x78):
            rec = self.u32(obj + 0x4A4) + 10 * i
            if i & 3 == pick:
                self.w16(rec + 6, self.u16(rec + 6) + self.u16(obj + 0x72))
                self.w16(rec + 8, self.u16(rec + 8) + self.u16(obj + 0x74))
            i += 1
            if i == self.s16(obj + 0x76):
                i = 0

    def staticfire_add_flame(self, obj):
        """0x2c6bc0 (object): a new flame point at the ring's head when the ring is not
        full: a unit-ball point x radius +0x1c x fade +0x64, z made positive, in 1/16 units,
        drift ((draw / 65536 - 0.5) / 60 x 224) twice."""
        ball = self.obj_ball(obj)
        h = C.mul(self.u32(obj + 0x1C), self.u32(obj + 0x64))
        x, y, z = (C.mul(b, h) for b in ball)
        if C.lt(z, ZERO):
            z = C.neg(z)
        head = self.s16(obj + 0x78)
        nxt = head + 1
        if nxt == self.s16(obj + 0x76):
            nxt = 0
        if nxt == self.s16(obj + 0x7A):
            return
        rec = self.u32(obj + 0x4A4) + 10 * head
        for k, v in enumerate((x, y, z)):
            self.w16(rec + 2 * k, C.to_int(C.mul(v, 0x41800000)))
        for k in (3, 4):
            d = C.mul(C.mul(C.sub(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), HALF_F), 0x3C888888), 0x43600000)
            self.w16(rec + 2 * k, C.to_int(d))
        self.w16(obj + 0x78, nxt)

    def staticfire_move_flames(self, obj):
        """0x2c6df0 (object): every flame point drifts and rises 7 (1/16 units); one that
        reaches int(+0x58) (compared as 16-bit values) pushes the ring's tail +0x7a on."""
        i = self.s16(obj + 0x7A)
        while i != self.s16(obj + 0x78):
            rec = self.u32(obj + 0x4A4) + 10 * i
            top = C.to_int(self.u32(obj + 0x58))
            z = (self.u16(rec + 4) + 7) & 0xFFFF
            self.w16(rec, self.u16(rec) + self.u16(rec + 6))
            self.w16(rec + 2, self.u16(rec + 2) + self.u16(rec + 8))
            self.w16(rec + 4, z)
            if not s16(z) < s16(top & 0xFFFF):
                tail = (self.u16(obj + 0x7A) + 1) & 0xFFFF
                self.w16(obj + 0x7A, tail)
                if s16(tail) == self.s16(obj + 0x76):
                    self.w16(obj + 0x7A, 0)
            i += 1
            if i == self.s16(obj + 0x76):
                i = 0

    def staticfire_init_common(self, obj):
        """StaticFire_initCommon 0x2c5814: radius 16, heading 0, byte +0x28 = 60, ring
        empty; one own draw sets the wind clock +0x4c = draw % 300; +0x68 = 25000, flags |=
        0x40001, life +0x7c = -1, +0x54 = +0x64 = 1, +0x6c = 0; the wind (angle 0), the run
        and always-draw lists, path_blockNodes(world, position; radius).  Ring: 250 points in
        a 0x9c4-byte block (mem_allocTagged) and height 600 when byte +0x6f is set, else 100
        points at +0xbc and height 480 (240 when byte +0x70 is set)."""
        w8, w16, w32, u32 = self.w8, self.w16, self.w32, self.u32
        w32(obj + 0x1C, 0x41800000)
        w16(obj + 0x38, 0)
        w8(obj + 0x28, 0x3C)
        w16(obj + 0x78, 0)
        w16(obj + 0x7A, 0)
        draw = self.obj_rand(obj)
        w32(obj + 0x68, 0x46C35000)
        w32(obj + 0xC, u32(obj + 0xC) | 0x40001)
        w32(obj + 0x7C, M32)
        w32(obj + 0x54, ONE)
        w32(obj + 0x64, ONE)
        w8(obj + 0x6C, 0)
        w32(obj + 0x4C, C.from_int(draw % 300))
        self.staticfire_wind(obj, self.s16(obj + 0x38))
        self.call('obj_runEveryFrame', obj)
        self.call('obj_addToAlwaysDraw', obj)
        self.call('path_blockNodes', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
        if self.s8(obj + 0x6F):
            w16(obj + 0x76, 0xFA)
            w32(obj + 0x4A4, self.call('mem_allocTagged', 0x9C4, 0x54E768))
            w32(obj + 0x50, 0x44160000)
            return
        w32(obj + 0x50, 0x43F00000)
        w16(obj + 0x76, 100)
        w32(obj + 0x4A4, obj + 0xBC)
        if self.s8(obj + 0x70):
            w32(obj + 0x50, 0x43700000)

    def staticfire_ctor(self, obj, pos, life, owner, quiet, fuel, scale):
        """StaticFire_ctor 0x2c5240 (object, position, life, owner, quiet; height f12,
        scale f13).  GameObject_ctor (a shared draw inside); the table; the light (orange
        0xff, 0x80 and 1.0 at +0x2c) 36 above the given position; initCommon; life +0x7c,
        height +0x50 = f12, +0x68 x= f13, owner +0x4a8, burning +0x6e = 1; quiet: the light
        is unlinked again.  Then every other object in the +-30 box: when not quiet and it is a
        StaticFire (typeid), its light is unlinked; with more than three of them around the
        life is halved."""
        self.call('GameObject_ctor', obj, tuple(pos), 0, 0)
        self.w32(obj + 0x48, self.SF_VT)
        self._sf_light(obj, pos, (0xFF, 0x80, 0, 0, 0xFF, 0x80, 0, 0), ONE)
        self.w8(obj + 0x6F, 0)
        self.w8(obj + 0x70, 0)
        self.staticfire_init_common(obj)
        self.w32(obj + 0x7C, life)
        self.w32(obj + 0x50, fuel)
        self.w32(obj + 0x68, C.mul(self.u32(obj + 0x68), scale))
        self.w32(obj + 0x4A8, owner)
        self.w8(obj + 0x6E, 1)
        if quiet:
            self.call('light_unlink', obj + 0x80)
        p = self.vec(obj + 0x10)
        high = tuple(C.add(v, 0x41F00000) for v in p)
        low = tuple(C.sub(v, 0x41F00000) for v in p)
        found = self.call('world_collectObjectsInBox', low, high, 0x80)
        count = 0
        for other in found or ():
            if other == obj:
                continue
            if not quiet:
                kind = self.call('Creature.v0')
                mine = self.call('typeinfo', self.SF_TYPEINFO)
                if self.call('rtti_typeInfoEquals', kind, mine):
                    self.call('light_unlink', other + 0x80)
            count += 1
        if count > 3:
            self.w32(obj + 0x7C, int(self.s32(obj + 0x7C) / 2))

    def staticfire_ctor2(self, obj, pos, a2, a3):
        """StaticFire_ctor2 0x2c54f8 (object, position): a level fire.  GameObject_ctor
        (object, position, 0, the caller's a3); the light (0xff, 0x80, -16 shorts, 0 at
        +0x2c) 36 above the object; owner 0; properties: +0x6f and +0x70 (read before
        initCommon), then +0x6c, radius +0x1c, particle rate +0x54, burning +0x6e (default
        1)."""
        self.call('GameObject_ctor', obj, tuple(pos), 0, a3)
        self.w32(obj + 0x48, self.SF_VT)
        self._sf_light(obj, self.vec(obj + 0x10), (0xFF, 0x80, 0, 0xFFF0, 0xFF, 0x80, 0, 0xFFF0), ZERO)
        self.w32(obj + 0x4A8, 0)
        name = self.SF_PROPS
        for off, prop in ((0x6F, name[0]), (0x70, name[1])):
            if self.call('obj_getPropStr', obj, prop, 0):
                self.w8(obj + off, self.call('obj_getPropInt', obj, prop, 0))
            else:
                self.w8(obj + off, 0)
        self.staticfire_init_common(obj)
        if self.call('obj_getPropStr', obj, name[2], 0):
            self.w8(obj + 0x6C, self.call('obj_getPropInt', obj, name[2], 0))
        for off, prop in ((0x1C, name[3]), (0x54, name[4])):
            if self.call('obj_getPropStr', obj, prop, 0):
                self.w32(obj + off, C.from_int(self.call('obj_getPropInt', obj, prop, 0)))
        if self.call('obj_getPropStr', obj, name[5], 0):
            self.w8(obj + 0x6E, self.call('obj_getPropInt', obj, name[5], 0))
        else:
            self.w8(obj + 0x6E, 1)

    def _sf_level_is(self, name):
        return _cstr(self.u8, self.LEVEL_NAME) == _cstr(self.u8, name)

    def _sf_level_has(self, name):
        return _cstr(self.u8, name) in _cstr(self.u8, self.LEVEL_NAME)

    def _sf_offset(self, obj, ball):
        r = self.u32(obj + 0x1C)
        fade = self.u32(obj + 0x64)
        return tuple(C.mul(C.mul(C.mul(b, r), fade), 0x3F3168B5) for b in ball)

    def staticfire_run(self, obj):
        """StaticFire_run 0x2c595c, GameObject slot 4.  See the class docstring; in order:
        cutscene flag +0x6d (only in the one level 0x54e778, while a cutscene runs); life
        +0x7c (-1 = forever): counts down, fades in by 1/60 a tick and out by 1/120 over its
        last 120 ticks, unlinks the light at 0; the wind every 61 ticks unless +0x6c; a new
        flame point on one draw in 14 (top +0x58 = height x 0.45 x 16); the flames move.
        Burning (+0x6e) and alive and isNearView(941): the light flickers (+0x60 between 80
        and 108), radius (+0x60 x 0.34 + 54) x fade; int(4 x rate +0x54 x fade) flame
        particles 0x8e4c90; on one draw in 33, int(2 fade) embers 0x8e4d30; on frames
        divisible by 12 damage_apply to everything in the +-radius x fade box that is not
        itself and has no flag 1 (fire entry 0x15: (1, 1) for others, for players the Fire
        Weapons tier-2 statistic x 0.15 (at least 1) .. + 20 % of it times ONE SHARED DRAW);
        attacker the owner +0x4a8 when it is a creature whose slot 20 accepts the victim,
        else the fire itself for creatures.  A fire whose life is 0 and whose ring is empty
        deletes itself."""
        u8, u16, u32, w32 = self.u8, self.u16, self.u32, self.w32
        cutscene = 0
        if self._sf_level_is(self.SF_LEVEL_CUTSCENE) and self.s8(RC.G_CUTSCENE_ACTIVE):
            cutscene = 1
        self.w8(obj + 0x6D, cutscene)
        life = self.s32(obj + 0x7C)
        if life != -1:
            unlink = life == 0
            if life:
                life -= 1
                w32(obj + 0x7C, life)
                unlink = life == 0
                if life:
                    fade = u32(obj + 0x64)
                    if life < 0x78:
                        fade = C.sub(fade, 0x3C088888)
                        w32(obj + 0x64, fade)
                        if C.lt(fade, ZERO):
                            w32(obj + 0x64, ZERO)
                    else:
                        fade = C.add(fade, 0x3C888888)
                        w32(obj + 0x64, fade)
                        if C.lt(ONE, fade) or self.s8(obj + 0x6D):
                            w32(obj + 0x64, ONE)
            if unlink:
                self.call('light_unlink', obj + 0x80)
        if not self.s8(obj + 0x6C):
            clock = u32(obj + 0x4C)
            w32(obj + 0x4C, C.add(clock, ONE))
            if C.lt(0x42700000, clock):
                self.staticfire_wind(obj, self.obj_rand(obj))
                w32(obj + 0x4C, ZERO)
        if self.s32(obj + 0x7C) and self.obj_rand(obj) % 14 == 0:
            top = C.mul(C.mul(u32(obj + 0x50), 0x3EE66665), 0x41800000)
            w32(obj + 0x58, top)
            w32(obj + 0x5C, C.div(ONE, top))
            self.staticfire_add_flame(obj)
        self.staticfire_move_flames(obj)
        if self.s8(obj + 0x6E) and self.s32(obj + 0x7C) and self.call('isNearView', self.vec(obj + 0x10), 0x446B4000):
            self._sf_burn(obj)
        if self.s32(obj + 0x7C) == 0 and self.s16(obj + 0x7A) == self.s16(obj + 0x78):
            self.call('obj_delete', obj)

    def _sf_burn(self, obj):
        u32, w32 = self.u32, self.w32
        flicker = u32(obj + 0x60)
        if C.eq(flicker, 0x42A00000):
            if self.obj_rand(obj) % 10 == 0:
                w32(obj + 0x60, C.add(u32(obj + 0x60), 0x41E00000))
        else:
            v = C.sub(flicker, 0x40000000)
            w32(obj + 0x60, v)
            if C.lt(v, 0x42A00000):
                w32(obj + 0x60, 0x42A00000)
        radius = C.mul(C.add(C.mul(u32(obj + 0x60), 0x3EAE147A), 0x42580000), u32(obj + 0x64))
        w32(obj + 0x9C, radius)
        w32(obj + 0xA4, radius)
        inverse = C.div(ONE, C.mul(radius, radius))
        w32(obj + 0xA8, inverse)
        w32(obj + 0xA0, inverse)
        n = C.to_int(C.mul(C.mul(u32(obj + 0x54), 0x40800000), u32(obj + 0x64)))
        while n > 0:
            off = self._sf_offset(obj, self.obj_ball(obj))
            pos = self.vec(obj + 0x10)
            p = tuple(C.add(pos[k], off[k]) for k in range(3))
            b = self.obj_ball(obj)
            v = [C.mul(x, 0x40A00000) for x in b]
            if C.lt(v[2], ZERO):
                v[2] = C.neg(v[2])
            n -= 1
            self.call('particle_spawn', self.SF_FLAME, p, tuple(v), ZERO)
        if self.obj_rand(obj) % 33 == 0:
            i = 0
            while i < C.to_int(C.add(u32(obj + 0x64), u32(obj + 0x64))):
                off = self._sf_offset(obj, self.obj_ball(obj))
                pos = self.vec(obj + 0x10)
                base = tuple(C.add(pos[k], off[k]) for k in range(3))
                p = (C.add(base[0], ZERO), base[1], C.add(base[2], 0x41400000))
                b = list(self.obj_ball(obj))
                if C.lt(b[2], 0x3F4CCCCC):
                    b[2] = 0x3F4CCCCC
                i += 1
                x, y, z = C.mul(b[0], 0x3E800000), C.mul(b[1], 0x3E800000), b[2]
                r = C.rsqrt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z)))
                n3 = (C.mul(x, r), C.mul(y, r), C.mul(z, r))
                k = C.mul(C.add(C.mul(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), HALF_F), HALF_F), 0x41800000)
                self.call('particle_spawn', self.SF_EMBER, p, tuple(C.mul(v, k) for v in n3), ZERO)
        frame = s32(u32(G_SIM_FRAME))
        if frame - int(frame / 12) * 12:
            return
        h = C.mul(u32(obj + 0x1C), u32(obj + 0x64))
        pos = self.vec(obj + 0x10)
        found = self.call('world_collectObjectsInBox', tuple(C.sub(v, h) for v in pos),
                          tuple(C.add(v, h) for v in pos), 0x40)
        for victim in found or ():
            if victim == obj or u32(victim + 0xC) & 1:
                continue
            if u32(victim + 0xC) & 0x40:
                skill = u32(self.SF_SKILL)
                level = C.to_int(u32(RC.G_LEVEL_MONSTER_LEVEL))
                low = C.mul(C.from_int(s32(self.skill_call(skill, 11, 0, level, 0))), 0x3E199999)
                if C.lt(low, ONE):
                    low = ONE
                share = C.mul(C.from_int(self.draw()), F_2M16)
                high = C.add(low, C.mul(C.mul(low, 0x3E4CCCCC), share))
                entry = (0x15, C.to_int(low), C.to_int(high), 0)
            else:
                entry = (0x15, 1, 1, 0)
            owner = u32(obj + 0x4A8)
            if owner and u32(owner + 0xC) & 0x20:
                if self.vcall(owner, 20, victim):
                    self.call('damage_apply', victim, u32(obj + 0x4A8), 100000, 0, 0, 0x100C040, SC.desc(entry), 0,
                              ZERO, ZERO)
            elif u32(victim + 0xC) & 0x20:
                self.call('damage_apply', victim, obj, 100000, 0, 0, 0x100C040, SC.desc(entry), 0, ZERO, ZERO)

    def staticfire_draw(self, obj):
        """StaticFire_draw 0x2c65e8, GameObject slot 5: with isNearView(941), burning,
        alive and no cutscene flag, one glow over the fire (26 bias, size (flicker x 59 +
        12000) x fade, colour (0xb9, 0x68, 0x51), alpha 0x6e, texture *0x4f848c, flags 6);
        then one glow per flame point near the view: size from 4800 toward +0x68 with the
        point's height t = min(1, z x 1/top) (doubled for a level fire with +0x6f), colour
        from (56 - 46 t, 56 - 43 t, 56 - 42 t) toward (188, 83, 69) as the point rises
        (alive) or half of it (dying), dimmed toward (70, 102, 107) in levels whose name has
        0x54e788 by the height above -480, alpha int(171 - 171 t), texture *0x4f84a0 or the
        dim one *0x4f84a4, angle s16(+-(object + frame) x 0xb3), flags 1."""
        u32 = self.u32
        i = self.s16(obj + 0x7A)
        dark = self._sf_level_has(self.SF_LEVEL_DARK)
        near = self.call('isNearView', self.vec(obj + 0x10), 0x446B4000)
        if near and self.s8(obj + 0x6E) and u32(obj + 0x7C) and not self.s8(obj + 0x6D):
            size = C.mul(C.add(C.mul(u32(obj + 0x60), 0x426C0000), 0x463B8000), u32(obj + 0x64))
            pos = self.vec(obj + 0x10)
            p = (C.add(pos[0], ZERO), pos[1], C.add(pos[2], 0x41400000))
            self.call('glow_add', p, 0xB9, 0x68, 0x51, 0x6E, u32(G_GLOW_TEX_A), 0, 6, 0x41D00000, size)
        while i != self.s16(obj + 0x78):
            rec = u32(obj + 0x4A4) + 10 * i
            pos = self.vec(obj + 0x10)
            p = tuple(C.add(pos[k], C.mul(C.from_int(self.s16(rec + 2 * k)), 0x3D800000)) for k in range(3))
            if self.call('isNearView', p, 0x446B4000):
                t = C.mul(C.from_int(self.s16(rec + 4)), u32(obj + 0x5C))
                if C.lt(ONE, t):
                    t = ONE
                t0 = t
                if self.s8(obj + 0x6F):
                    t = C.add(t0, t0)
                    if C.lt(ONE, t):
                        t = ONE
                a46, a43, a42 = C.mul(t, 0xC2380000), C.mul(t, 0xC22C0000), C.mul(t, 0xC2280000)
                if u32(obj + 0x7C) and self.s8(obj + 0x6E):
                    zf = C.mul(C.from_int(self.s16(rec + 4)), 0x3D800000)
                    k = C.sub(ONE, C.fmin(ONE, C.div(zf, C.mul(u32(obj + 0x60), u32(obj + 0x64)))))
                    r = C.add(C.add(a46, C.mul(C.sub(0x433C0000, C.add(a46, 0x42600000)), k)), 0x42600000)
                    g = C.add(C.add(a43, C.mul(C.sub(0x42A60000, C.add(a43, 0x42600000)), k)), 0x42600000)
                    b = C.add(C.add(a42, C.mul(C.sub(0x428A0000, C.add(a42, 0x42600000)), k)), 0x42600000)
                else:
                    r = C.mul(C.add(a46, 0x42600000), HALF_F)
                    g = C.mul(C.add(a43, 0x42600000), HALF_F)
                    b = C.mul(C.add(a42, 0x42600000), HALF_F)
                dim = False
                if dark:
                    f = C.mul(C.sub(p[2], 0xC3F00000), 0x3B08D180)
                    f = C.fmax(ZERO, C.fmin(ONE, f))
                    r = C.add(C.mul(C.sub(r, 0x428C0000), f), 0x428C0000)
                    g = C.add(C.mul(C.sub(g, 0x42CC0000), f), 0x42CC0000)
                    b = C.add(C.mul(C.sub(b, 0x42D60000), f), 0x42D60000)
                    dim = C.lt(f, 0x3F7F3A68)
                alpha = C.to_int(C.add(C.mul(t0, 0xC32B0000), 0x432B0000))
                spin = ((obj + s32(u32(G_SIM_FRAME))) * 0xB3) & M32
                angle = s16((-spin) & 0xFFFF) if i & 1 else s16(spin & 0xFFFF)
                size = C.add(C.mul(C.sub(u32(obj + 0x68), 0x45960000), t), 0x45960000)
                tex = u32(G_GLOW_TEX_FIRE_DIM if dim else G_GLOW_TEX_FIRE)
                self.call('glow_add', p, C.to_int(r), C.to_int(g), C.to_int(b), alpha, tex, angle, 1, 0x40A00000, size)
            i += 1
            if i == self.s16(obj + 0x76):
                i = 0


_register('StaticFire_ctor', 0x2C5240)
_register('StaticFire_ctor2', 0x2C54F8)
_register('StaticFire_initCommon', 0x2C5814)
_register('StaticFire_wind', 0x2C6AA8)
_register('StaticFire_addFlame', 0x2C6BC0)
_register('StaticFire_moveFlames', 0x2C6DF0)
_register('StaticFire_run', 0x2C595C)
_register('StaticFire_draw', 0x2C65E8)


class Model(Calls, Draws, MultiFire, FireStormFlare, Pustule, DiseaseCloud, Arena, HornOmen, PlanarSteel,
            StaticFire, SC.Model):
    """ref_skills_c.Model with the methods of part 3."""
