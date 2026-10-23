"""Bounded vendor contracts for the US Return to Arms v2.00 shop.

These are function-level price and state rules, not a renderer or a stock
generator. The latter depends on item generators and private level state.
"""

from ee_emu import float_to_raw, fp_div, fp_mul, raw_to_float

PLAYER = 0x4D8AF0
STOCK = 0x866E78
STOCK_STRIDE = 0x1208
STOCK_COUNT = 64
GOLD_CAP = 99_999_999


def stock_list(index):
    assert 0 <= index < 3
    return STOCK + index * STOCK_STRIDE


def buy_price(value, category, slot, flags):
    """Price for the tested nonnegative item values under ee_emu's ps2 FPU."""
    factor = 0x3F199999               # 0.6, rounded toward zero in original
    if category == 1:
        factor = 0x3EE66666           # 0.45
    if flags & 0x30000000000 or slot == 8:
        factor = 0x3F800000           # 1.0
    return int(raw_to_float(fp_mul(float_to_raw(value), factor)))


def sell_credit(value, count, slot, definition_flags):
    """Ordinary single-stack sale; special zero-credit kinds included."""
    if slot == 8 or definition_flags & (1 << 46):
        return 0
    assert count > 0
    per_item = fp_div(float_to_raw(value), float_to_raw(count))
    return max(1, int(raw_to_float(fp_mul(per_item, 0x3D4CCCCC))))


def credited_gold(old, credit):
    return min(GOLD_CAP, old + credit)
