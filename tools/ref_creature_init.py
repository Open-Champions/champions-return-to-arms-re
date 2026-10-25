#!/usr/bin/env python3
"""ref_creature_init.py - Creature_init 0x10a230, the setup every creature constructor ends with.

Reference contract for docs/script-session.md section 4.  Observed instruction by
instruction (0x10a230-0x10a61c) and executed in tools/difftest_creature_init.py.

    Creature_init(this)

 1. If bit 0 of the creature flags (+0xa8, the MiniBoss bit) is set: virtual slot 18
    (table +0x90) (this).
 2. Virtual slot 16 (table +0x80) (this), the model getter.  When it returns non-zero:
    slot 16 again, then model_getBounds 0x179400 (model, -1, six int outputs).  The height
    +0x20 (f32) becomes float(out[5] - out[2]), raised to 84.0 when below it (the store of
    the difference happens first, at 0x10a304, then 84.0 at 0x10a308), and the draw byte
    +0x29 = int(height) + 1.
 3. obj_getPropStr(this, "dead") non-null: creature flags |= bit 32 (a 64-bit store),
    virtual slot 27 (table +0xd8) (this, 0x14): the class's own set-state to 0x14, then
    anim_snapTopToEnd 0x170c80 (this + 0x114).
 4. For n = 0..31, obj_getPropStr(this, "change%d" % n) non-null sets bit n of a mask.  A
    non-zero mask: +0xe8 = mask; slot 16 (this); +0x220 (u64) = model_buildHideMask
    0x179550 (model, mask).
 5. Seven obj_getPropInt keys in order ("FireWeapons", "FireBurstWeapons", "ColdWeapons",
    "PoisonWeapons", "ShockWeapons", "DiseaseWeapons", "NoMagicWeapons").  For each that is
    non-zero, when the weapon pointer +0x50 is not 0: the weapon's virtual slot 2..8 (its
    own table at weapon +0; entries +0x10..+0x40) (weapon, 0); slot 8 gets (weapon, 0, 0).
 6. Unless g_cutsceneActive (byte 0x44fcd0) is non-zero: obj_getPropStr(this,
    "initScript") non-null: g_scriptSelectedObj (0x4039f8) = this, script_runByName
    0x1ed694 (text), g_scriptSelectedObj = 0.

Nothing else is stored by the function itself.  In particular it never stores the object
flags +0x0c, the hit points +0x228 or the byte +0x231; only the class's slot 18 and
slot 27, and the script that initScript names, can.

The keys are named by their addresses; obj_getPropStr / obj_getPropInt lower the key and
compare case-sensitively (tools/ref_objects.props_find).  Nothing from the game is in this
file.
"""
M32 = 0xFFFFFFFF

KEY_DEAD = 0x52FAC8
KEY_CHANGE = 0x52FAD0          # a format: "change%d"
KEY_WEAPONS = (0x52FAE0, 0x52FAF0, 0x52FB08, 0x52FB18, 0x52FB28, 0x52FB38, 0x52FB48)
KEY_INIT_SCRIPT = 0x52FB58
G_CUTSCENE = 0x44FCD0
G_SCRIPT_SELECTED = 0x4039F8
MODEL_GET_BOUNDS, MODEL_HIDE_MASK = 0x179400, 0x179550
ANIM_SNAP_TOP_TO_END, SCRIPT_RUN_BY_NAME = 0x170C80, 0x1ED694
SLOT_MINIBOSS, SLOT_MODEL, SLOT_SET_STATE = 18, 16, 27
DEAD_STATE = 0x14
HEIGHT_FLOOR = 0x42A80000      # 84.0 (0x10a2e0)
DEAD_BIT = 1 << 32


def f32_from_int(v):
    """cvt.s.w: a signed 32-bit integer to the float pattern (exact below 2**24; rounded
    toward zero above, as the R5900 does)."""
    import struct
    v = v - (1 << 32) if v & 0x80000000 else v
    if v == 0:
        return 0
    sign = 0x80000000 if v < 0 else 0
    m = abs(v)
    e = m.bit_length() - 1
    if e > 23:
        m >>= e - 23
    else:
        m <<= 23 - e
    return sign | ((e + 127) << 23) | (m & 0x7FFFFF)


def f32_lt(a, b):
    """c.olt.s on R5900 patterns (no NaNs: every pattern is a number)."""
    def key(x):
        return -(x & 0x7FFFFFFF) if x & 0x80000000 else x
    return key(a) < key(b)


def f32_to_int(x):
    """cvt.w.s: truncation toward zero, saturating."""
    sign = -1 if x & 0x80000000 else 1
    e = ((x >> 23) & 0xFF) - 127
    if e < 0:
        return 0
    m = (x & 0x7FFFFF) | 0x800000
    v = m << (e - 23) if e >= 23 else m >> (23 - e)
    v = min(v, 0x7FFFFFFF)
    return (sign * v) & M32


def run(obj, host):
    """obj: .flags64() / .set_flags64(v), .weapon(), .prop_str(key_addr[, text]) -> text or
    None, .prop_int(key_addr) -> int, .store(off, size, value).  host: .vcall(slot, args)
    -> value, .weapon_vcall(slot, args), .bounds() -> six ints, .hide_mask(model, mask) ->
    u64, .call(name, args), .cutscene() -> byte, .change_key(n) -> the formatted key text.
    Returns nothing; every effect goes through obj and host, in the original's order."""
    if obj.flags64() & 1:
        host.vcall(SLOT_MINIBOSS, ())
    if host.vcall(SLOT_MODEL, ()):
        model = host.vcall(SLOT_MODEL, ())
        out = host.bounds(model)
        height = f32_from_int((out[5] - out[2]) & M32)
        obj.store(0x20, 4, height)
        if f32_lt(height, HEIGHT_FLOOR):
            height = HEIGHT_FLOOR
            obj.store(0x20, 4, height)
        obj.store(0x29, 1, (f32_to_int(height) + 1) & 0xFF)
    if obj.prop_str(KEY_DEAD) is not None:
        obj.set_flags64(obj.flags64() | DEAD_BIT)
        host.vcall(SLOT_SET_STATE, (DEAD_STATE,))
        host.call('anim_snapTopToEnd', ('anim',))
    mask = 0
    for n in range(32):
        if obj.prop_str(None, host.change_key(n)) is not None:
            mask |= 1 << n
    if mask:
        obj.store(0xE8, 4, mask)
        model = host.vcall(SLOT_MODEL, ())
        obj.store(0x220, 8, host.hide_mask(model, mask))
    for k, key in enumerate(KEY_WEAPONS):
        if obj.prop_int(key) and obj.weapon():
            host.weapon_vcall(2 + k, (0, 0) if k == 6 else (0,))
    if not host.cutscene():
        text = obj.prop_str(KEY_INIT_SCRIPT)
        if text is not None:
            obj.store_global(G_SCRIPT_SELECTED, 4, 'this')
            host.call('script_runByName', (text,))
            obj.store_global(G_SCRIPT_SELECTED, 4, 0)
