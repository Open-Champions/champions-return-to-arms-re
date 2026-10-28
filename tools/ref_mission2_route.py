"""Authored mission-2 predicate contracts, addressed without private identifiers.

Entry offsets are code-relative in the first story script. Inputs are the
values queried by those entries, not a claim that inventory was loaded.
"""


def predicate(entry, evil, item_count=0, offered=0, completed=0):
    evil, item = bool(evil), bool(item_count)
    if entry == 0x16c:
        return int(evil)
    if entry == 0x1dc:
        return int(not evil and not item and completed == 0)
    if entry in (0x360, 0x11c0):
        return int(not evil and item)
    if entry == 0x4f0:
        return int(not evil and completed == 1)
    if entry == 0x5b0:
        return int(not evil)
    if entry == 0x624:
        return int(evil and not item)
    if entry in (0x6dc, 0x990):
        return int(evil and item)
    if entry == 0x810:
        return int(evil and not item and completed == 0)
    if entry == 0xa44:
        return int(evil and completed == 1)
    if entry == 0xe48:
        return int(not evil and completed != 1 and (item or offered != 1))
    if entry == 0xfa4:
        return int(evil and completed != 1 and (item or offered != 1))
    if entry == 0x1104:
        return int(not evil and not item)
    raise ValueError("unresearched entry")


PREDICATES = (0x16c, 0x1dc, 0x360, 0x4f0, 0x5b0, 0x624, 0x6dc,
              0x810, 0x990, 0xa44, 0xe48, 0xfa4, 0x1104, 0x11c0)


def death(game, obj, quiet, death_entry, descriptor):
    """0x10beb8, restricted to drawn non-PvP creatures; music is external.

    The death entry runs even for quiet deaths; the authored item call does
    not. Running the entry before the drop is part of this contract.
    """
    if obj.flags & 2:
        raise ValueError('undrawn deletion not covered')
    obj.set_cflags(obj.cflags() & ~0x08c00000)
    # obj_getPropStr lowercases its key buffer in place, including literal keys.
    # Derive the contents from the supplied executable; never embed them.
    def lower_key(address):
        while game.mem.u8(address):
            value = game.mem.u8(address)
            game.mem.w8(address, value + 32 if 65 <= value <= 90 else value)
            address += 1
    lower_key(0x52fbf8)
    if death_entry:
        game.selected_obj = obj.addr
        game.run_script(death_entry)
        game.selected_obj = 0
    if not quiet:
        lower_key(0x52fc08)
        if descriptor:
            game.ext('loot_spawnNamedItem', tuple(obj.pos), descriptor)
