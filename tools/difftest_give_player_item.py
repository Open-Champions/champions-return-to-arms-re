#!/usr/bin/env python3
"""difftest_give_player_item.py — original givePlayerItem, end to end.

The script native is 0x145a88. Starting equipment is player_giveStartingItems
0x1acc78, which this file does not run. It only counts that function's jal
targets so the two paths stay distinct.

  python3 tools/difftest_give_player_item.py [SLUS_209.73] --seed 20973
  python3 tools/difftest_give_player_item.py [SLUS_209.73] --seed 7

The original code runs in tools/ee_emu.py. Item names are read from the
executable at run time and are not printed. No game bytes are written here.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError  # noqa: E402
import ref_amx  # noqa: E402
import ref_items as I  # noqa: E402
import ref_script_items as R  # noqa: E402

GIVE = 0x145A88
GIVE_END = 0x145D20
PARSE = 0x1069B8
GIVE_ITEM = 0x1C1868
EQUIP = 0x1C27C0
CHECK_EQUIP = 0x1C4948
RECALC_LOAD = 0x1BEC10
ITEM_WEIGHT = 0x1B6338
GET_WEIGHT = 0x103E08
PASSIVE = 0x1BED48
SKILL_RANK = 0x1BF330
REMOVE_FLAG39 = 0x1BE1D8
REMOVE_ITEM = 0x1C1CB0
RUN_BY_NAME = 0x1ED694
DISPATCH = 0x141050
SCR_LOAD, SCR_REGISTER = 0x13E8F8, 0x141310
SCR_GET_ADDR, SCR_GET_STRING = 0x1414A8, 0x141650
NATIVE_TABLE = 0x403370
NATIVE_INDEX = 53
STARTING = 0x1ACC78
INIT_CHAR = 0x1B1D70
RESET_IDLE = 0x1B2470
LIBC = (0x3A5000, 0x3CC000)
FLAG_STACK = 0x100
FLAG_39 = 1 << 39
FLAG_41 = 0x20000000000
F_9999 = 0x461C3C00
F_64 = 0x42800000
TOKEN = 0x7000

STUBS = {
    0x1B6458: 'player_recalcStats',
    0x1BA5F8: 'player_countPotions',
    0x1B2470: 'player_resetIdleAnim',
    0x1C3F08: 'inventory_selectIdleAnim',
    0x14FDB8: 'pool_new',
    0x1590EC: 'ItemProp_ctor2',
    0x1ED778: 'vars_get',
    0x1ED854: 'vars_set',
    0x173C84: 'text_lookup',
    0x1D9830: 'hud_showHelpMessage',
    0x1D9954: 'hud_showPlayerNotice',
    0x13E150: 'net_isLocalSlot',
    0x2134E8: 'sound_playSample',
    0x214230: 'sound_playOnObject',
    0x214428: 'sound_playAtPos',
}
REAL = {
    GIVE, PARSE, GIVE_ITEM, EQUIP, CHECK_EQUIP, RECALC_LOAD, ITEM_WEIGHT, GET_WEIGHT,
    PASSIVE, SKILL_RANK, REMOVE_FLAG39, REMOVE_ITEM, RUN_BY_NAME, DISPATCH,
    SCR_GET_ADDR, SCR_GET_STRING,
    0x1046E0,   # item_randomizeVariant, called even when the variant count is 0
    0x108924,   # item_sameIdentityFields
    0x1024A8,   # item_getValue
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES = []
CHECKS = 0


def check(ok, detail):
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(detail)
        print('FAIL  %s' % detail)
    else:
        print('PASS  %s' % detail)


def find_elf(argv):
    args = [a for a in argv if not a.startswith('--')]
    if args:
        return args[0]
    for path in (os.path.join(ROOT, 'local', 'SLUS_209.73'),
                 os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73')):
        if os.path.isfile(path):
            return path
    sys.exit('no SLUS_209.73')


def seed_arg(argv):
    for i, a in enumerate(argv):
        if a == '--seed' and i + 1 < len(argv):
            return int(argv[i + 1])
    return 20973


def jal_count(mem, start, end, target):
    n, addr = 0, start
    while addr < end:
        word = mem.u32(addr)
        if (word >> 26) == 3 and ((word & 0x03FFFFFF) << 2) == target:
            n += 1
        addr += 4
    return n


def eligible(d):
    return (not d.preset and d.name and 0 <= d.category <= 2
            and ((d.flags >> 11) & 0x1F) == 0 and d.slot != 8
            and not (d.flags & R.ITEM_FLAG_THROWN_AXE))


def install(emu, pool=0):
    def make(addr, name):
        def run(e):
            if name == 'pool_new':
                return pool
            if name == 'vars_get':
                return 1
            return 0
        emu.stub(addr, function=run, name=name)
    for addr, name in STUBS.items():
        make(addr, name)

    strings = {}

    def get_addr(e):
        e.mem.w32(e.r[6] & R.M32, e.r[5] & R.M32)
        return 0

    def get_string(e):
        text = strings[e.r[5] & R.M32]
        e.mem.write(e.r[4] & R.M32, text + b'\0')
        return 0

    emu.stub(SCR_GET_ADDR, function=get_addr, name='scr_getAddr')
    emu.stub(SCR_GET_STRING, function=get_string, name='scr_getString')
    return strings


def bind_script(emu):
    """One native, givePlayerItem, bound by the original registrar."""
    image = ref_amx.build_image([], [], [], [b'givePlayerItem'], stack_cells=32)
    base = emu.alloc(len(image) + 32)
    emu.mem.write(base, image)
    loaded = R.s32(emu.call(SCR_LOAD, base, base + 0x60, max_steps=2000000))
    bound = R.s32(emu.call(SCR_REGISTER, base, NATIVE_TABLE, -1, max_steps=2000000))
    header = base + 0x60
    table = header + emu.mem.u32(header + 0x2C)
    handler = emu.mem.u32(table)
    return base, loaded, bound, handler


def call_give(emu, strings, text, equip, use_presets, machine):
    strings[TOKEN] = text
    params = emu.alloc(16)
    emu.mem.w32(params, 12)
    emu.mem.w32(params + 4, TOKEN)
    emu.mem.w32(params + 8, equip & R.M32)
    emu.mem.w32(params + 12, use_presets & R.M32)
    emu.reset_log()
    if machine is None:
        value = emu.call(GIVE, 0x01100000, params, max_steps=20000000)
        return R.s32(value), None
    pri = emu.alloc(4)
    emu.mem.w32(pri, 0x55555555)
    error = emu.call(DISPATCH, machine, 0, pri, params, max_steps=20000000)
    return R.s32(emu.mem.u32(pri)), R.s32(error)


def calls_to(emu, target, start=None, end=None):
    out = []
    for rec in emu.calls:
        if rec.target != target:
            continue
        if start is not None and not start <= rec.site < end:
            continue
        out.append(rec)
    return out


def unexpected(emu):
    bad = []
    for rec in emu.calls:
        t = rec.target
        if t in REAL or t in STUBS or LIBC[0] <= t < LIBC[1]:
            continue
        if t not in bad:
            bad.append(t)
    return bad


def cell(slot, bag, index):
    return R.bag_entry(slot, bag, index)


def prepare(emu, seed, players):
    emu.mem.w32(R.G_NUM_PLAYERS, players)
    emu.mem.w32(R.G_RAND_SEED, seed & R.M32)
    emu.mem.w32(R.G_MEDAL_MISSION, 0)
    emu.mem.w8(R.G_MEDAL_PLAYER, 0)
    emu.mem.w32(0x4F719C, 2)
    emu.mem.w32(0x50C530, 1)
    emu.mem.w8(0x402791, 0)
    emu.mem.w32(0x86B270, 0)
    for slot in range(4):
        r = R.rec(slot)
        for bag in range(3):
            emu.mem.write(r + R.P_BAGS + bag * R.BAG_SIZE, bytes(R.BAG_SIZE))
        for off in range(17):
            emu.mem.w32(r + 0x43F0 + 4 * off, 0)
        emu.mem.w32(r + R.P_SET_WEAPONS, 0)
        emu.mem.w32(r + R.P_SET_WEAPONS + 4, 0)
        emu.mem.w32(r + R.P_SET_WEAPONS + 8, 0)
        emu.mem.w32(r + R.P_LOAD, 0)
        emu.mem.w32(r + R.P_LOAD_LIMIT, F_9999)
        emu.mem.w32(r + R.P_CLASS, 0)
        emu.mem.w8(r + 0x58, 80)
        for off in (0x90, 0x94, 0x98, 0x9C):
            emu.mem.w32(r + off, 9999)
        emu.mem.w16(r + R.P_SKILL_PAIRS, 0xFFFF)
        emu.mem.w8(r + 0x4C25, 1)
        emu.mem.w8(r + 0x4A7C, 0)
        emu.mem.w8(r + 0x4A86, 0)
        obj = emu.alloc(0x800)
        emu.mem.w32(obj + R.OBJ_FLAGS, 0)
        emu.mem.w32(obj + 0x3C8, slot)
        emu.mem.w32(r + R.P_OBJECT, obj)
        emu.mem.w32(R.G_ALIVE_LIST + 4 * slot, slot)


def bag_count(emu, slot, bag):
    return R.s32(emu.mem.u32(R.bag_count_at(slot, bag)))


def run_cases(elf, tables, seed):
    defs = [d for d in tables.defs if eligible(d)]
    by_cat = {}
    for d in defs:
        by_cat.setdefault(d.category, d)
    stack = next(d for d in defs if d.flags & FLAG_STACK and 0 < d.count <= 20
                 and not (d.flags & FLAG_41))
    plain = [d for d in defs if not (d.flags & FLAG_STACK) and not (d.flags & FLAG_41)]
    heavy = next(d for d in plain if d.weight != 0)
    weapon = [d for d in tables.defs if not d.preset and d.name and d.category == 0
              and d.slot in (0, 2) and d.slot != 8 and not (d.flags & FLAG_41)]
    pinned = tables.by_addr.get(0x3F7F50)
    if pinned is not None:
        weapon = [pinned] + [d for d in weapon if d is not pinned]
    refused = next((d for d in defs if d.flags & FLAG_41 and 0 <= d.category <= 2
                    and ((d.flags >> 11) & 0x1F) == 0), None)
    flag39_rows = [d for d in tables.defs if not d.preset and d.name and d.flags & FLAG_39]
    cats = {}
    for d in flag39_rows:
        cats[d.category] = cats.get(d.category, 0) + 1
    check(len(flag39_rows) > 0,
          'base rows with flag bit 39: %d, by category %s' % (len(flag39_rows), sorted(cats.items())))

    emu = EE(elf)
    strings = install(emu)
    prepare(emu, seed, 2)

    # Argument contract and which bag receives the item.
    for cat in (0, 1, 2):
        d = by_cat[cat]
        prepare(emu, seed, 1)
        v0, _ = call_give(emu, strings, d.name, 0, 0, None)
        parses = calls_to(emu, PARSE, GIVE, GIVE_END)
        check(v0 == 0, 'category %d handler v0 is 0 (seed %d)' % (cat, seed))
        check(len(parses) == 1 and R.s32(parses[0].args[2]) == -1
              and R.s32(parses[0].args[3]) == 0,
              'category %d parse variant -1 and usePresets 0' % cat)
        check(bag_count(emu, 0, cat) == 1 and bag_count(emu, 0, (cat + 1) % 3) == 0
              and bag_count(emu, 0, (cat + 2) % 3) == 0,
              'category %d lands in that bag only' % cat)
        at = cell(0, cat, 0)
        check(emu.mem.u32(at) == d.addr and emu.mem.u16(at + 0x22) == 0,
              'category %d cell 0 is that definition, stamp 0' % cat)
        check(not calls_to(emu, REMOVE_FLAG39), 'give does not call removeFlag39')
        check(emu.mem.u32(R.G_RAND_SEED) == (seed & R.M32), 'category %d seed unchanged' % cat)
        extra = unexpected(emu)
        check(not extra, 'category %d no unexpected calls %s' % (cat, [hex(t) for t in extra[:8]]))

    # usePresets is the third script cell, still with variant -1.
    d = by_cat[2]
    prepare(emu, seed, 1)
    call_give(emu, strings, d.name, 0, 1, None)
    parses = calls_to(emu, PARSE, GIVE, GIVE_END)
    check(len(parses) == 1 and R.s32(parses[0].args[2]) == -1 and R.s32(parses[0].args[3]) == 1,
          'usePresets 1 is parse argument 4, variant stays -1')

    # Every joined slot, unless medal mode names one.
    d = by_cat[0]
    prepare(emu, seed, 2)
    v0, _ = call_give(emu, strings, d.name, 0, 0, None)
    check(v0 == 0 and bag_count(emu, 0, 0) == 1 and bag_count(emu, 1, 0) == 1
          and bag_count(emu, 2, 0) == 0,
          'two players each receive one; slot 2 does not')
    prepare(emu, seed, 2)
    emu.mem.w32(R.G_MEDAL_MISSION, 1)
    emu.mem.w8(R.G_MEDAL_PLAYER, 1)
    call_give(emu, strings, d.name, 0, 0, None)
    check(bag_count(emu, 0, 0) == 0 and bag_count(emu, 1, 0) == 1,
          'medal mode gives only the medal player')

    # Stacking: same definition, flags, prefix and suffix. A different prefix does not.
    d = stack
    prepare(emu, seed, 1)
    call_give(emu, strings, d.name, 0, 0, None)
    at = cell(0, d.category, 0)
    first = emu.mem.u16(at + 4)
    call_give(emu, strings, d.name, 0, 0, None)
    check(bag_count(emu, 0, d.category) == 1 and emu.mem.u16(at + 4) == (first + d.count) & 0xFFFF
          and emu.mem.u32(cell(0, d.category, 1)) == 0,
          'stackable second give adds the count and does not append')
    emu.mem.w8(at + 0x20, (emu.mem.u8(at + 0x20) + 1) & 0xFF)
    call_give(emu, strings, d.name, 0, 0, None)
    check(bag_count(emu, 0, d.category) == 2 and emu.mem.u32(cell(0, d.category, 1)) == d.addr,
          'a different prefix byte appends a second cell')

    # Full bag: the cell at `count` is not empty. Count 64 makes that cell the count word.
    d = by_cat[0]
    cat = d.category
    prepare(emu, seed, 1)
    emu.mem.w32(R.bag_count_at(0, cat), 64)
    bogus = cell(0, cat, -1)
    emu.mem.w32(bogus, 0)
    v0, _ = call_give(emu, strings, d.name, 1, 0, None)
    equips = calls_to(emu, EQUIP, GIVE, GIVE_END)
    check(v0 == 0 and bag_count(emu, 0, cat) == 64 and emu.mem.u32(cell(0, cat, 0)) == 0,
          'count 64 does not append and the handler still returns 0')
    check(emu.mem.u32(R.rec(0) + R.P_LOAD) == F_64,
          'the failed give still recomputes load across the 64 empty cells')
    check(len(equips) == 1 and (equips[0].args[0] & R.M32) == 0
          and (equips[0].args[1] & R.M32) == (bogus & R.M32) and (equips[0].args[2] & R.M32) == 0,
          'full bag still calls equip with the address one record before the bag')
    check(emu.mem.u32(R.rec(0) + 0x43F0) == 0, 'that address has a zero definition, so nothing equips')

    prepare(emu, seed, 1)
    emu.mem.w32(R.bag_count_at(0, cat), 63)
    v0, _ = call_give(emu, strings, d.name, 0, 0, None)
    at = cell(0, cat, 63)
    check(v0 == 0 and bag_count(emu, 0, cat) == 64 and emu.mem.u32(at) == d.addr
          and emu.mem.u16(at + 0x22) == 63,
          'count 63 appends at index 63 and the stamp is 63')

    # Weight. Limit 0 rejects a positive weight and still accepts a zero weight.
    prepare(emu, seed, 1)
    emu.mem.w32(R.rec(0) + R.P_LOAD_LIMIT, 0)
    v0, _ = call_give(emu, strings, heavy.name, 0, 0, None)
    check(v0 == 0 and bag_count(emu, 0, heavy.category) == 0
          and len(calls_to(emu, 0x14FDB8)) == 1
          and (calls_to(emu, 0x14FDB8)[0].args[0] & R.M32) == 0x190
          and not calls_to(emu, 0x1590EC),
          'a positive weight at limit 0 calls pool_new(0x190) and does not give')
    natural = [d for d in defs if d.count == 0 or d.weight == 0]
    accepted = None
    for d in natural:
        prepare(emu, seed, 1)
        emu.mem.w32(R.rec(0) + R.P_LOAD_LIMIT, 0)
        call_give(emu, strings, d.name, 0, 0, None)
        if bag_count(emu, 0, d.category) == 1:
            accepted = 'retail row'
            break
    if accepted is None:
        d = by_cat[2]
        old = emu.mem.u16(d.addr + 0xC)
        emu.mem.w16(d.addr + 0xC, 0)
        prepare(emu, seed, 1)
        emu.mem.w32(R.rec(0) + R.P_LOAD_LIMIT, 0)
        call_give(emu, strings, d.name, 0, 0, None)
        emu.mem.w16(d.addr + 0xC, old)
        if bag_count(emu, 0, d.category) == 1 and not calls_to(emu, 0x14FDB8):
            accepted = 'count halfword forced to 0'
    check(accepted is not None,
          'zero weight is given at limit 0 (%s, retail zero rows %d)' % (accepted, len(natural)))

    # Equipment. A permitted weapon is stored. A flag-41 item stays in the bag.
    equipped = False
    reasons = []
    for d in weapon[:40]:
        prepare(emu, seed, 1)
        call_give(emu, strings, d.name, 0, 0, None)
        at = cell(0, d.category, 0)
        if emu.mem.u32(at) != d.addr:
            reasons.append('other-row')
            continue
        reason = R.s32(emu.call(CHECK_EQUIP, 0, at, max_steps=2000000))
        reasons.append(reason)
        if reason != 0:
            continue
        prepare(emu, seed, 1)
        call_give(emu, strings, d.name, 1, 0, None)
        at = cell(0, d.category, 0)
        ptr = emu.mem.u32(R.rec(0) + 0x43F0 + 4 * (d.slot & 0xFF))
        idles = calls_to(emu, 0x1B2470, GIVE, GIVE_END)
        names = calls_to(emu, RUN_BY_NAME)
        equipped = (ptr == at and emu.mem.u32(at) == d.addr
                    and emu.mem.u8(R.rec(0) + 0x4A86) == (d.subtype & 0xFF)
                    and len(idles) == 1 and (idles[0].args[0] & R.M32) == 0
                    and len(names) == 1 and emu.mem.u32(0x86B270) == 0)
        break
    check(equipped, 'equip=1 stores the new cell, sets the weapon class, calls resetIdleAnim; reasons %s'
          % reasons[:8])

    if refused is not None:
        prepare(emu, seed, 1)
        d = refused
        call_give(emu, strings, d.name, 1, 0, None)
        at = cell(0, d.category, 0)
        ptr = emu.mem.u32(R.rec(0) + 0x43F0 + 4 * (d.slot & 0xFF))
        check(emu.mem.u32(at) == d.addr and ptr != at and len(calls_to(emu, EQUIP, GIVE, GIVE_END)) == 1,
              'flag bit 41 is given and equip does not keep that cell')
    else:
        check(False, 'no flag-41 definition to refuse')

    # A retail flag-39 row keeps the bit. The keep list runs later, in
    # player_removeFlag39Items, and is not consulted by the give.
    retail = next(d for d in flag39_rows if 0 <= d.category <= 2)
    prepare(emu, seed, 1)
    call_give(emu, strings, retail.name, 0, 0, None)
    retail_bit = False
    for bag in range(3):
        for i in range(max(0, bag_count(emu, 0, bag))):
            at = cell(0, bag, i)
            if emu.mem.u32(at) == retail.addr and emu.mem.u64(at + 8) & FLAG_39:
                retail_bit = bag == retail.category
    check(retail_bit, 'a retail flag-39 row lands in its category bag with bit 39 set')
    # The keep names are applied by the remover to whatever definition it finds.
    rows = [defs[0], defs[1], defs[2]]
    labels = (b'pickaxe', b'abloodstone', b'questtoken')
    saved = []
    for d in rows:
        saved.append((d.addr, emu.mem.u32(d.addr), emu.mem.u64(d.addr + 0x28)))
        emu.mem.w64(d.addr + 0x28, emu.mem.u64(d.addr + 0x28) | FLAG_39)
    prepare(emu, seed, 1)
    for d in rows:
        call_give(emu, strings, d.name, 0, 0, None)
    bufs = []
    for name in labels:
        buf = emu.alloc(len(name) + 1)
        emu.mem.write(buf, name + b'\0')
        bufs.append(buf)
    for d, buf in zip(rows, bufs):
        emu.mem.w32(d.addr, buf)
    found = {}
    for bag in range(3):
        for i in range(bag_count(emu, 0, bag)):
            at = cell(0, bag, i)
            if emu.mem.u32(at) in [d.addr for d in rows]:
                found[emu.mem.u32(at)] = emu.mem.u64(at + 8)
    check(len(found) == 3 and all(bits & FLAG_39 for bits in found.values()),
          'flag bit 39 is stored with the cell and is not a give-time filter')
    emu.call(REMOVE_FLAG39, 0, max_steps=20000000)
    left = set()
    for bag in range(3):
        for i in range(max(0, bag_count(emu, 0, bag))):
            left.add(emu.mem.u32(cell(0, bag, i)))
    check(rows[0].addr in left and rows[1].addr in left and rows[2].addr not in left,
          'removeFlag39 keeps an exact name and a contained name, and drops the other')
    for addr, name_ptr, flags in saved:
        emu.mem.w32(addr, name_ptr)
        emu.mem.w64(addr + 0x28, flags)

    # What the script sees: the dispatcher stores the handler result.
    machine, loaded, registered, handler = bind_script(emu)
    check(loaded == 0 and registered == 0 and handler == GIVE,
          'registrar binds the one native to 0x145a88 (load %d register %d)' % (loaded, registered))
    d = by_cat[1]
    prepare(emu, seed, 1)
    pri, error = call_give(emu, strings, d.name, 0, 0, machine)
    check(pri == 0 and error == 0 and bag_count(emu, 0, 1) == 1,
          'scr_callNative stores 0 and returns error 0')
    prepare(emu, seed, 1)
    full = by_cat[0]
    emu.mem.w32(R.bag_count_at(0, full.category), 64)
    pri, error = call_give(emu, strings, full.name, 0, 0, machine)
    check(pri == 0 and error == 0 and bag_count(emu, 0, full.category) == 64,
          'a full bag is still script result 0')


def main(argv):
    elf = find_elf(argv[1:])
    seed = seed_arg(argv[1:])
    tables = I.Tables(I.Exe(elf))
    emu = EE(elf)
    handler = emu.mem.u32(NATIVE_TABLE + 8 * NATIVE_INDEX + 4)
    check(handler == GIVE, 'native %d handler is 0x%08x' % (NATIVE_INDEX, handler))
    give_n = jal_count(emu.mem, STARTING, INIT_CHAR, GIVE)
    item_n = jal_count(emu.mem, STARTING, INIT_CHAR, GIVE_ITEM)
    equip_n = jal_count(emu.mem, STARTING, INIT_CHAR, EQUIP)
    parse_n = jal_count(emu.mem, STARTING, INIT_CHAR, PARSE)
    check(give_n == 0 and item_n > 0 and parse_n > 0,
          'starting items 0x1acc78 jal givePlayerItem %d, inventory_giveItem %d, equip %d, parse %d'
          % (give_n, item_n, equip_n, parse_n))
    init_give = jal_count(emu.mem, INIT_CHAR, RESET_IDLE, GIVE)
    init_start = jal_count(emu.mem, INIT_CHAR, RESET_IDLE, STARTING)
    check(init_give == 0 and init_start > 0,
          'new character 0x1b1d70 jal givePlayerItem %d, player_giveStartingItems %d'
          % (init_give, init_start))
    try:
        run_cases(elf, tables, seed)
    except (EmuError, StopIteration, KeyError, ZeroDivisionError) as exc:
        check(False, 'stopped: %r' % (exc,))
    print('%d checks, %d failed, seed %d' % (CHECKS, len(FAILURES), seed))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
