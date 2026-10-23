"""Small reference for US v2.00 player appearance and item model choices.

Only authored selection rules and short resource identifiers belong here. The
executable/disc tables are read by the differential test, not embedded here.
"""

BODY_CODES = ('bm', 'bf', 'wem', 'wef', 'hem', 'hef', 'em', 'ef',
              'dem', 'def', 'vm', 'im')


def part_requests(model_index, appearance, select2=False):
    """Ordered (lump, filename, Player object offset) constructor lookups."""
    if not 0 <= model_index < len(BODY_CODES) or len(appearance) != 4:
        raise ValueError('invalid model index or appearance record')
    hair, colour, beard, skin = appearance
    code = BODY_CODES[model_index]
    lump = 'select2.lmp' if select2 else 'select.lmp'
    result = []
    if hair != -1:
        result += [(lump, f'{code}_hair{hair + 1}a.vif', 0x548),
                   (lump, f'{code}_hair{hair + 1}{chr(97 + colour)}.tex', 0x558)]
    if beard != -1:
        result += [(lump, f'{code}_beard{beard + 1}a.vif', 0x54c),
                   (lump, f'{code}_beard{beard + 1}{chr(97 + colour)}.tex', 0x554)]
    result += [(lump, f'{code}_bodyv1.vif', 0x544),
               (lump, f'{code}_bodyv{skin + 1}.tex', 0x550)]
    return result


def item_model_index(definition_index, item_flags):
    """item_getResourceIndex 0x1083f8, before g_itemModels[index]."""
    return definition_index + (((item_flags >> 11) & 31) if item_flags & (1 << 36) else 0)


def draw_route(slot):
    """The player draw's visible resource route for one equipment slot."""
    if slot in (0, 1, 2, 3, 4, 9, 10, 11, 12, 13):
        return 'equipment-cache'
    if slot in (5, 6, 7, 8, 14, 15):
        return 'skip'
    if slot == 16:
        return 'item-model-table'
    raise ValueError('equipment slot outside 0..16')


def draw_appearance_gates(model_index, skin, cover_state, head_name):
    """Hair/beard draw gates after the equipment loop, before handle checks.

    cover_state is the draw-local flag set by the equipped-item comparisons,
    not merely the presence of an item in the head slot. head_name is the
    compared definition name for the item at record +0x441c, or None.
    """
    hair = not cover_state or model_index == 11 or (model_index == 10 and skin == 4)
    beard = (not cover_state or model_index == 11
             or (head_name is not None
                 and ('leatherhelmet' in head_name or model_index == 6)))
    return hair, beard


def draw_cover_state(model_index, slot, name, resource, prior=False):
    """Draw-local state after one equipped part passed its handle checks."""
    state = bool(prior)
    if model_index != 7 and slot == 11 and 'circlet' not in name:
        state = True
    if model_index == 7:
        if slot == 11 and 'cloth1' not in resource and 'circlet' not in name:
            state = True
        if slot == 4 and 'cloth3body' in resource:
            state = True
    if model_index == 9 and slot == 4:
        if 'chain' in name or (resource is not None and 'chainbody' in resource):
            state = True
    return state
