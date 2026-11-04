"""Address-only stock arithmetic for SLUS_209.73, shop_openOrStock 0x1c7af8.

Item selection remains in the unchanged ref_items module. Values here use its raw PS2 FPU
operations; no descriptors, item names, resource strings or game bytes live here.
"""
import ref_items as I
import struct

STOCK, LIST_STRIDE, ITEM_SIZE = 0x866e78, 0x1208, 0x48
SHARED, COSMETIC = 0x404464, 0x404460
FIXED_WEAPONS = (0x538760, 0x538768, 0x538778, 0x538788)
FIXED_OTHER = 0x5388e8


def budget_contract(store_level, difficulty, second_read=None):
    """0x1c7b48-0x1c7cd8; bounded to ordinary nonnegative load inputs.

    The scale validates the first variable read, while the budget uses the
    second read without that range check. Omitted second_read means equal reads.
    Negative power bases and integer overflow inputs are outside this contract.
    """
    s = store_level if 0 <= store_level <= 11 else -1
    scale = max(I.F_ONE, I.fadd(I.fmul(I.fint(s), 0x3eaaaaaa), I.F_ONE))
    second_read = store_level if second_read is None else second_read
    base_integer = 1600 * (second_read + 11 * (difficulty - 1))
    if not (1 <= difficulty <= 5 and 0 <= second_read <= 12):
        raise ValueError("unestablished budget input")
    x = I.fint(base_integer)
    powered = I.powf(x, 0x3f999999)
    base = I.fadd(powered, 0x45dac000)
    low = I.ftrunc(I.fsub(I.fmul(base, 0x3f199999), 0x453b8000))
    high = I.ftrunc(I.fadd(I.fmul(base, 0x3fc00000), 0x45bb8000))
    delta = I.s32(high - low)
    cap_base = I.fadd(I.fint(24 * difficulty - 24), I.fmul(scale, 0x40800000))
    cap = I.ftrunc(cap_base) + 2
    other_cap = I.ftrunc(I.fadd(I.fint(24 * difficulty - 18),
                              I.fmul(scale, 0x40800000)))
    steps = tuple(int(delta / n) for n in (22, 17, 6))
    # 0x1c81b0-0x1c8338: two variable fixed descriptors plus one constant.
    tier = 44 if not I.flt(0x3fc00000, scale) else 40 if not I.flt(0x40600000, scale) else 36
    offset = tier - 12 * min(difficulty, 3)
    return dict(scale=scale, low=low, high=high, steps=steps,
                caps=(cap, cap, other_cap), special_cap=cap,
                other_pointer_cells=(0x4f4280 + offset, 0x4f4258 + offset))


def draw(seed):
    seed = (seed * 0x19660d + 0x3c6ef35f) & 0xffffffff
    return seed, seed >> 16


def special_rolls(seed):
    """Three unconditional own-seed draws, 0x1c7ea0/0x1c80c4/0x1c8498."""
    result = []
    for _ in range(3):
        seed, value = draw(seed)
        result.append(I.flt(I.fmul(I.fint(value), 0x37800000), 0x3dcccccc))
    return seed, tuple(result)


def same_raw(a, b):
    """0x108924 includes the unwritten halfword +0x22, unlike Item identity."""
    return (b[:4] != bytes(4) and a[:4] == b[:4]
            and a[8:16] == b[8:16] and a[0x20:0x24] == b[0x20:0x24])


def stock_plan(contract, cosmetic_seed, memory, read32):
    """0x1c7af8 stock orchestration, independent of item-generator internals.

    memory is an owned bytearray beginning at STOCK, including 0x6000 bytes
    of preexisting state. Do not substitute empty lists for its other regions:
    category 1 scans category 2's OLD records, and category 2 scans beyond stock.
    Yield (kind, destination_address, arguments), receive (success, raw_record).
    Raw bytes must include caller-supplied/parser-stack residue. This interface
    deliberately does not invent those bytes or claim they are deterministic.
    Sorting is separate; list counts and the next unused slot are retained.
    """
    if len(memory) < 0x6000:
        raise ValueError("preexisting comparison memory is required")
    _, rolls = special_rolls(cosmetic_seed)
    for category, attempts in enumerate((22, 17, 6)):
        base = category * LIST_STRIDE
        count = 0

        def publish_count():
            struct.pack_into('<I', memory, base + 0x1200, count)

        def put(raw):
            if len(raw) != ITEM_SIZE:
                raise ValueError("candidate must contain a complete record")
            offset = base + count * ITEM_SIZE
            memory[offset:offset + ITEM_SIZE] = raw

        publish_count()
        fixed = FIXED_WEAPONS if category == 0 else ()
        if category == 2:
            fixed = tuple(read32(a) for a in contract['other_pointer_cells']) + (FIXED_OTHER,)
        for descriptor in fixed:
            destination = STOCK + base + count * ITEM_SIZE
            # Counts increment before parser dispatch in the original.
            count += 1
            publish_count()
            _, raw = yield ('parse', destination, (descriptor, -1, 0))
            offset = base + (count - 1) * ITEM_SIZE
            memory[offset:offset + ITEM_SIZE] = raw

        progress = retries = 0
        while progress < attempts:
            budget = I.s32(contract['low'] + (progress + 1) * contract['steps'][category])
            ok, raw = yield ('affix', STOCK + base + count * ITEM_SIZE,
                             (budget, category, 1 if category == 2 else -1,
                              contract['caps'][category]))
            put(raw)
            accept = bool(ok)
            if accept:
                # These offsets are surprising but observed, not corrected.
                scan = base + category * LIST_STRIDE
                duplicate = any(same_raw(memory[scan + n * ITEM_SIZE:
                                               scan + (n + 1) * ITEM_SIZE], raw)
                                for n in range(count))
                if duplicate and retries < 6:
                    retries += 1
                    accept = False
                if category == 0 and int.from_bytes(raw[8:16], 'little') & (1 << 40):
                    accept = False
                if category == 2 and raw[0x21] == 0xff:
                    accept = False
            if accept:
                count += 1
                publish_count()
                retries = 0
            # Weapons and armour retry the same budget; other advances even on failure.
            if accept or category == 2:
                progress += 1
        if rolls[category]:
            multiplier = (22, 17, 10)[category]
            subtotal = I.s32(contract['low'] + multiplier * contract['steps'][category])
            # Original calls int->double->int before the final integer doubling.
            budget = I.s32(2 * subtotal)
            _, raw = yield ('preset', STOCK + base + count * ITEM_SIZE,
                             (budget, category, contract['special_cap']))
            put(raw)
            if raw[:4] != bytes(4):
                count += 1
                publish_count()
    return memory


def sorted_records(memory, value):
    """0x1c8588-0x1c8724: ascending signed item value, stable equal values."""
    lists = []
    for category in range(3):
        base = category * LIST_STRIDE
        count = struct.unpack_from('<I', memory, base + 0x1200)[0]
        rows = [bytes(memory[base + n * ITEM_SIZE:base + (n + 1) * ITEM_SIZE])
                for n in range(count)]
        lists.append(sorted(rows, key=value))
    return lists


# shop_buy 0x1d1240. Category 1 is definition +0x1d. Slot 8 is definition +0x1c.
# Record flag bits 40 and 41 force factor 1. Truncation is CVT.W.S toward zero.
BUY_FACTOR, BUY_FACTOR_ARMOUR, BUY_FACTOR_FULL = 0x3F199999, 0x3EE66666, I.F_ONE
BUY_FULL_FLAGS = 0x30000000000

# shop_onMsg sell at 0x1c5d70. 0x41a00000 is the x20 stack adjustment.
# 0x3d4ccccc is the sell fraction (a value of 100 and a count of 1 pays 4).
SELL_STACK, SELL_FRACTION = 0x41A00000, 0x3D4CCCCC
SELL_STACK_FLAGS, SELL_ZERO_FLAGS = 0x1C0000000000, 0x400000000000
GOLD_CAP = 99999999

# shop_restockByGold 0x1c8a00. Not the session refresh. Player 0 gold is +0xe4.
PLAYERS, PLAYER_STRIDE, PLAYER_GOLD = 0x4D8AF0, 0x4C30, 0xE4
RESTOCK = 0x1C8A00
RESTOCK_LISTS = (STOCK, STOCK + LIST_STRIDE, STOCK + 2 * LIST_STRIDE)
RESTOCK_SEED_COUNTS = (1, 0, 1)
NAME_BUFFER, NAME_STRIDE, NAME_SLOTS = 0x86B278, 0x50, 64
# Category 2's duplicate scan is STOCK + 4*LIST_STRIDE, inside name half 0.
SCAN_BASE = STOCK + 4 * LIST_STRIDE


def buy_price(value, category, record_flags, slot):
    """0x1d1270-0x1d12f4. ``value`` is the signed result of item_getValue."""
    factor = BUY_FACTOR_ARMOUR if category == 1 else BUY_FACTOR
    if record_flags & BUY_FULL_FLAGS or slot == 8:
        factor = BUY_FACTOR_FULL
    return I.ftrunc(I.fmul(I.fint(value), factor))


def sell_credit(value, count, slot, name_has_stem, definition_flags):
    """0x1c5df8-0x1c5eac. ``count`` is the signed halfword at the sold record +4.

    A count of 0 uses the same division-by-zero pattern as fdiv (no trap).
    Slot 8 is scaled and then forced to 0, because the zero test is later.
    """
    amount = I.fint(value)
    if slot == 8 or name_has_stem or definition_flags & SELL_STACK_FLAGS:
        amount = I.fmul(amount, SELL_STACK)
    paid = I.ftrunc(I.fmul(I.fdiv(amount, I.fint(count)), SELL_FRACTION))
    if paid <= 0:
        paid = 1
    if slot == 8 or definition_flags & SELL_ZERO_FLAGS:
        paid = 0
    return paid


def buy_gold(gold, price):
    """0x1d12e4-0x1d130c. Signed compare; the debit is stored before giveItem."""
    gold, price = I.s32(gold), I.s32(price)
    if gold < price:
        return gold, False
    return I.s32(gold - price), True


def sell_gold(gold, paid):
    """0x1c5eb4-0x1c5ecc. 32-bit add, then the signed cap 99,999,999."""
    gold = I.s32(I.s32(gold) + I.s32(paid))
    if gold > GOLD_CAP:
        gold = GOLD_CAP
    return gold


def signed_half(gold):
    """0x1c8a24-0x1c8a58. Signed gold divided by 2 toward zero."""
    gold = I.s32(gold)
    return I.s32(gold + (gold < 0)) >> 1


def signed_double(gold):
    """0x1c8a9c. 32-bit left shift; the result is a signed budget."""
    return I.s32(I.s32(gold) << 1)


def restock_calls(gold):
    """0x1c8a00. Three lists, three budgets, five appends each.

    Yield (list_address, budget, attempt, category). The attempt is passed
    and ignored by item_appendGeneratedUnique 0x107d54. Counts are forced to
    1, 0, 1 before the loops and are not cleared by this function.
    """
    budgets = (signed_half(gold), I.s32(gold), signed_double(gold))
    for category, base in enumerate(RESTOCK_LISTS):
        for budget in budgets:
            for attempt in range(5):
                yield base, budget, attempt, category
