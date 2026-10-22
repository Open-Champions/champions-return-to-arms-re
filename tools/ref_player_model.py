"""Reference for the resource choices made by Player_ctor (US v2.00).

Only short resource identifiers are recorded here. No disc payload is embedded.
The animation-entry names stay in the executable's class definition table and are
checked against the disc by difftest_player_model.py.
"""

BODY_CODES = ('bm', 'bf', 'wem', 'wef', 'hem', 'hef', 'em', 'ef',
              'dem', 'def', 'vm', 'im')
CLASS_INDEX = (0, 0, 3, 3, 1, 1, 4, 4, 2, 2, 5, 6)
ANIM_LUMPS = ('ragnar2.lmp', 'sonya2.lmp', 'elf_mwo2.lmp', 'elf_fwo2.lmp',
              'hem_high.lmp', 'elf_fhi2.lmp', 'eru_male.lmp', 'eru_fem.lmp',
              'elf_mdk.lmp', 'elf_fdk2.lmp', 'vashir.lmp', 'iksar.lmp')


def requests(model_index, appearance=(-1, 0, -1, 0), select2=False):
    """Ordered (lump, entry, object offset) lookups by Player_ctor.

    appearance is record +0x20..+0x23: hair style, hair colour, beard
    style, skin variant. -1 in a style slot suppresses both lookups.
    """
    if not 0 <= model_index < len(BODY_CODES) or len(appearance) != 4:
        raise ValueError('model index or appearance outside the playable record layout')
    code = BODY_CODES[model_index]
    hair, colour, beard, skin = appearance
    lump = 'select2.lmp' if select2 else 'select.lmp'
    out = []
    if hair != -1:
        n = hair + 1
        out.extend(((lump, f'{code}_hair{n}a.vif', 0x548),
                    (lump, f'{code}_hair{n}{chr(colour + 97)}.tex', 0x558)))
    if beard != -1:
        n = beard + 1
        out.extend(((lump, f'{code}_beard{n}a.vif', 0x54c),
                    (lump, f'{code}_beard{n}{chr(colour + 97)}.tex', 0x554)))
    out.extend(((lump, f'{code}_bodyv1.vif', 0x544),
                (lump, f'{code}_bodyv{skin + 1}.tex', 0x550)))
    return out
