"""Player skill-driven animation states 6, 7, 9 and 0xe. SLUS-20973 v2.00.

Executed in tools/ee_emu.py: each constructor below was called on a zeroed
player whose object flag word (+0xc) was 0x40 and whose weapon class read as
0 (no player record; those reads returned 0, so the looked-up names use the
class-0 prefix). Callees were stubbed. Not a running game, and not a rendered
check. difftest_skill_anim.py re-runs the same calls.

`select` in ref_creature_dispatch is unchanged. Player_run's own clip table
stays in that module's PLAYER_DISPATCH.
"""

# anim call: (kind, clip name looked up immediately before it, flags, blend in, blend out)
# blends are raw32. A push that does not pass a blend has 0.

F01 = 0x3dcccccc

# Constructors that store action state 6, then start one clip. Weapon class 0.
STATE6 = (
    dict(name='SkillCyclone_cast', fn=0x2d17c8, state=6,
         anim=('push', 'cyclone1.anm', 0x23, 0, 0),
         names=('cyclone1.anm', 'spel_bw_cyclone.anm')),
    dict(name='SpellBash_ctor', fn=0x2de640, state=6,
         anim=('bio', 'bash.anm', 0x812, F01, F01),
         names=('bash.anm',)),
    dict(name='SpellAncestralCall_ctor', fn=0x2e09b4, state=6,
         anim=('bio', 'ohw_warcry.anm', 0x22, F01, F01),
         names=('spel_bw_ancestral.anm', 'ohw_warcry.anm')),
    dict(name='SpellShieldBash_ctor', fn=0x2face4, state=6,
         anim=('bio', 'bash.anm', 0x812, F01, F01),
         names=('bash.anm',)),
    dict(name='SpellRoar_ctor', fn=0x30016c, state=6,
         anim=('bio', 'ohw_roar.anm', 0x22, F01, F01),
         names=('ohw_roar.anm', 'spel_vb_roar.anm')),
    dict(name='SpellBattleCry_ctor', fn=0x301714, state=6,
         anim=('bio', 'ohw_battlecry.anm', 0x22, F01, F01),
         names=('ohw_battlecry.anm', 'spel_vb_battlecry.anm')),
    dict(name='SpellBloodLust_ctor', fn=0x303254, state=6,
         anim=('bio', 'ohw_bloodlust.anm', 0x822, F01, F01),
         names=('ohw_bloodlust.anm',)),
)

CHARGE = 0x2c8864          # SkillCharge_cast
SHADOW_CTOR = 0x311638     # SpellShadowStep_ctor
SHADOW_HELPER = 0x214428   # holds the anim_push
SHADOW_DTOR = 0x311da0

# From object flags 0x40. The constructor ORs 0x5; the destructor clears those
# bits and stores action state 2. Only this flag pair was executed.
SHADOW_FLAGS_AFTER_CTOR = 0x45
SHADOW_FLAGS_AFTER_DTOR = 0x40
SHADOW_STATE = 0xe
SHADOW_END_STATE = 2
SHADOW_CLIP = 'spel_de_shadowstep.anm'
SHADOW_ANIM = ('push', SHADOW_CLIP, 0x4, 0x3f800000, 0)


def charge_state(object_flags):
    """Action state SkillCharge_cast stores. No clip is started either way.
    Executed: flag 0x40 set → 9; flag clear → the state stays 0."""
    return 9 if object_flags & 0x40 else 0


def state6_by_name(name):
    for row in STATE6:
        if row['name'] == name:
            return row
    raise KeyError(name)
