#!/usr/bin/env python3
"""ref_items.py - reference model of the item system of Champions: Return to Arms.

US SLUS_209.73 v2.00.  A research tool: it reimplements, in plain Python, what the item
module of the executable (0x100974-0x10896f) computes, so that the rules can be read,
called and compared with the original.  tools/difftest_items.py runs the original machine
code in tools/ee_emu.py on the same inputs; the model is "tested" for exactly the inputs
that test covers (docs/spec/items.md lists them).

No game data is embedded.  Tables, token words and item names are read from YOUR copy of
the executable when a Tables object is made:

    from ref_items import Tables, Rng, Game, parse_descriptor, item_value
    t = Tables('SLUS_209.73')
    rng = Rng(0)
    item = parse_descriptor(t, t.defs[0].name + b'+' + t.token_words[27] + b'10', rng=rng)
    print(item_value(t, item), rng.seed)

What is here, with the address of the code each part mirrors:

    Rng                         the shared generator g_randSeed 0x404464
    parse_descriptor            item_parseDescriptor              0x1069b8
    randomize_variant           item_randomizeVariant             0x1046e0
    item_weight                 item_getWeight                    0x103e08
    item_armor                  item_getArmorValue                0x103ec8
    item_attack_rating          item_getModifiedField1a           0x103f88
    item_damage_range           item_getDamageRange               0x104100
    item_value                  item_getValue                     0x1024a8
    required_level_for_value    the block repeated at 0x104a98, 0x105654, 0x1059f0
    weapon_group, armor_group   item_classifyCategory0/1          0x104c04, 0x104c48
    generate_preset             item_generateFromSpecialTable     0x104758
    generate_with_affixes       item_generateWithAffixes          0x104ca4
    generate_reagent            item_generateFlag35Entry          0x106214
    generate_figurine           item_generateFlag45Entry          0x106658
    generate_consumable         item_generateConsumable           0x108590
    shop_append_unique          item_appendGeneratedUnique        0x107d54
    load_resources              the seed side of item_loadResources 0x108434
    spawn_named_item            loot_spawnNamedItem               0x100ba0
    gold_scatter                the scatter loop of loot_spawnGold 0x100974
    loot_generate_drops         loot_generateDrops                0x100d54
    same_identity, copy_mutable, encode/decode_definition_index   0x108924, 0x107ca8,
                                                                  0x107ea4, 0x107ec0
    resource_index              item_getResourceIndex             0x1083f8
    equip_restriction           inventory_checkEquipAllowed       0x1c4948 (outside the module:
                                the test of an item's requirements against a player record)
    build_name                  itemName_buildLocalizedName       0x101e48 (and its helpers
                                0x101998, 0x101cb4, 0x101d0c)
    powf                        the C library's powf 0x3a7930 (through the wrapper 0x3a5ac8)

Floating point.  The console's FPU is not IEEE: results are truncated, there are no
infinities, NaNs or denormals.  All float arithmetic here is done on raw 32-bit patterns
with the same rules as the default ("ps2") model of tools/ee_emu.py, and the float
constants are written as the bit patterns the code loads.  Results are bit for bit those
of the original code under that model; what real hardware does in the last bit of a
product is not established (docs/issues/dynamic-tests.md), which matters here only
where a result is compared or truncated at an exact boundary.

Standard library only.  Python 3.8 or later.
"""
import struct

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF

# ---------------------------------------------------------------------------------------
# Addresses (US v2.00).  Layout evidence: docs/startup.md, docs/data-tables.md.
# ---------------------------------------------------------------------------------------
A_DEFS = 0x3F7650            # g_itemDefs, rows of 0x40, null-name terminator
A_PRESETS = 0x3EA550         # g_itemPresets, same row layout
A_PREFIXES = 0x400E50        # rows of 0x28
A_SUFFIXES = 0x4019E0        # rows of 0x14
A_MODELS = 0x3E9CE0          # g_itemModels, rows of 0x10 (model file, texture file, ...)
A_QUALITY = 0x3E9C18         # g_lootQualityRows, 12 rows of 3 floats
A_WEAPON_MULT = 0x3E9CB0     # g_weaponValueMult, float per weapon subtype
A_MANA_POTIONS = 0x402708    # pointer list, largest first
A_HEAL_POTIONS = 0x402730
A_GOLD_SCALE_MP = 0x520048   # double: gold amount factor with more than one player
S_ARROWS = 0x520040          # descriptor parsed for the arrows drop
S_NAME_SUFFIX = 0x520058     # sprintf format that turns a definition name into a text key
S_SPACE = 0x520060           # separator between the words of a display name
S_OF_KEY = 0x520068          # text key of the word between noun and suffix
S_THROWN_STEM = 0x520070     # name stem tested by item_getValue (0.004 factor)
S_POTION_STEM = 0x520180     # name stem that suppresses suffixes and the level requirement
S_CIRCLET_STEM = 0x520188    # name stem allowed among cloth when cloth is preferred
S_RECALL = 0x52B798          # descriptor parsed by item_generateConsumable's third branch
S_CIRCLET_STEM_EQUIP = 0x5385E8   # the same stem as tested by inventory_checkEquipAllowed

# The 43 scanner formats of item_parseDescriptor in the order it tries them: the address of
# the format string and the modifier code stored on a match (None: the "mesh" token, which
# sets the visual variant).  The number of values stored is the number of conversions in
# the format.  Read from 0x106b90-0x107bd0.
TOKEN_FORMATS = (
    (0x520190, 0x23), (0x5201A8, 0x1E), (0x5201C0, 0x1D), (0x5201D0, 0x1C),
    (0x5201E0, 0x1B), (0x5201F0, 0x1A), (0x520200, 0x19), (0x520210, 0x15),
    (0x520220, 0x16), (0x520230, 0x18), (0x520248, 0x17), (0x520260, 0x14),
    (0x520270, 0x0E), (0x520280, 0x0F), (0x520298, 0x10), (0x5202B0, 0x11),
    (0x5202C8, 0x12), (0x5202E0, 0x13), (0x5202F0, 0x0D), (0x520300, 0x0B),
    (0x520318, 0x0C), (0x520330, 0x05), (0x520340, 0x06), (0x520350, 0x07),
    (0x520360, 0x08), (0x520378, 0x09), (0x520390, 0x0A), (0x5203A0, 0x00),
    (0x5203B0, 0x01), (0x5203C0, 0x02), (0x5203D0, 0x03), (0x5203E0, 0x04),
    (0x5203F0, 0x21), (0x520408, 0x1F), (0x520420, 0x20), (0x520438, 0x22),
    (0x520450, 0x24), (0x520468, 0x25), (0x520478, 0x27), (0x520488, 0x28),
    (0x5204A0, 0x2A), (0x5204B0, None), (0x5204B8, 0x26),
)

ITEM_SIZE = 0x48
DESCRIPTOR_BUFFER = 208      # stack buffer of the parser; longer text overruns it


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


# ---------------------------------------------------------------------------------------
# R5900 single precision on raw patterns (same rules as ee_emu's "ps2" model)
# ---------------------------------------------------------------------------------------
F_ZERO, F_HALF, F_ONE, F_TWO, F_THREE = 0, 0x3F000000, 0x3F800000, 0x40000000, 0x40400000
F_HUNDREDTH = 0x3C23D70A     # 0.01
F_2_POW_16 = 0x47800000      # 65536.0
F_2_POW_M16 = 0x37800000     # 1 / 65536
F_MAX = 0x7FFFFFFF


def f_bits(value):
    """Raw pattern of a Python number rounded to single precision (for inputs only)."""
    return struct.unpack('<I', struct.pack('<f', value))[0]


def f_value(raw):
    """Python float of a raw pattern (IEEE reading; for display only)."""
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


def _unpack(raw):
    exp = (raw >> 23) & 0xFF
    if exp == 0:
        return raw >> 31, 0, 0
    return raw >> 31, (raw & 0x7FFFFF) | 0x800000, exp


def _pack(sign, mag, e2):
    """(-1)**sign * mag * 2**e2, truncated toward zero, clamped like the hardware."""
    if mag == 0:
        return sign << 31
    shift = mag.bit_length() - 24
    mant = mag >> shift if shift > 0 else mag << -shift
    exp = e2 + shift + 150
    if exp > 255:
        return (sign << 31) | F_MAX
    if exp < 1:
        return sign << 31
    return (sign << 31) | (exp << 23) | (mant & 0x7FFFFF)


def fadd(a, b):
    sa, ma, ea = _unpack(a)
    sb, mb, eb = _unpack(b)
    if ma == 0 and mb == 0:
        return (sa & sb) << 31
    if ma == 0:
        return b & M32
    if mb == 0:
        return a & M32
    if ea < eb:
        a, sa, ma, ea, sb, mb, eb = b, sb, mb, eb, sa, ma, ea
    diff = ea - eb
    if diff >= 25:
        return a & M32
    total = ((-ma if sa else ma) << 6) + (((-mb if sb else mb) << 6) >> diff)
    if total == 0:
        return 0
    return _pack(1 if total < 0 else 0, abs(total), ea - 156)


def fsub(a, b):
    return fadd(a, b ^ 0x80000000)


def fmul(a, b):
    sa, ma, ea = _unpack(a)
    sb, mb, eb = _unpack(b)
    if ma == 0 or mb == 0:
        return (sa ^ sb) << 31
    return _pack(sa ^ sb, ma * mb, ea + eb - 300)


def fdiv(a, b):
    sa, ma, ea = _unpack(a)
    sb, mb, eb = _unpack(b)
    if mb == 0:
        return ((sa ^ sb) << 31) | F_MAX
    if ma == 0:
        return (sa ^ sb) << 31
    return _pack(sa ^ sb, (ma << 40) // mb, ea - eb - 40)


def fint(value):
    """CVT.S.W: signed 32-bit integer to float."""
    value = s32(value)
    return _pack(1, -value, 0) if value < 0 else _pack(0, value, 0)


def ftrunc(raw):
    """CVT.W.S: float to signed 32-bit integer, toward zero, saturating."""
    sign, mant, exp = _unpack(raw)
    if mant == 0:
        return 0
    if exp >= 158:
        return -0x80000000 if sign else 0x7FFFFFFF
    shift = exp - 150
    mag = mant << shift if shift >= 0 else mant >> -shift
    return -mag if sign else mag


def _fkey(raw):
    return -(raw & 0x7FFFFFFF) if raw & 0x80000000 else raw & 0x7FFFFFFF


def flt(a, b):
    """C.OLT.S"""
    return _fkey(a) < _fkey(b)


def fle(a, b):
    """C.OLE.S"""
    return _fkey(a) <= _fkey(b)


def fmax(a, b):
    return a if _fkey(a) >= _fkey(b) else b


def float_times_double(raw, double_value):
    """(float)((double)x * c) as the code at 0x100dec-0x100e3c does it with the software
    double routines 0x3aef58, 0x3af4d0 and 0x3afb90.  Those follow the console's float
    rules too: the product and the conversion back are both truncated, which together is
    the exact product truncated to 24 bits; a result of 2**129 or more becomes the
    pattern 0x7f800000, one below 2**-126 becomes zero.  c must be an ordinary double."""
    sign, mant, exp = _unpack(raw)
    bits = struct.unpack('<Q', struct.pack('<d', double_value))[0]
    sign ^= bits >> 63
    dexp = (bits >> 52) & 0x7FF
    if mant == 0 or dexp == 0:
        return sign << 31
    product = mant * ((bits & ((1 << 52) - 1)) | (1 << 52))
    shift = product.bit_length() - 24
    field = (exp - 150) + (dexp - 1075) + shift + 150
    if field > 255:
        return (sign << 31) | 0x7F800000
    if field < 1:
        return sign << 31
    return (sign << 31) | (field << 23) | ((product >> shift) & 0x7FFFFF)


# ---------------------------------------------------------------------------------------
# powf (0x3a7930): the C library's single-precision power function, operation for
# operation.  The item code reaches it through the wrapper 0x3a5ac8 with exponents that
# are constants, so only that use is exercised by the differential test.
# ---------------------------------------------------------------------------------------
_HUGE, _TINY = 0x7149F2C9, 0x0DA2425F
_BP = (0x3F800000, 0x3FC00000)
_DP_H = (0x00000000, 0x3F15C000)
_DP_L = (0x00000000, 0x35D1CFDC)
_TRIM = 0xFFFFF000


def _scalbnf(x, n):
    """0x3aa810.  No denormals on this machine, so an exponent of zero or less underflows."""
    hx = x & 0x7FFFFFFF
    if hx <= 0x7FFFFF:
        return x
    k = (hx >> 23) + n
    if k >= 0x100 or (k <= 0 and n > 50000):
        return fmul((x & 0x80000000) | _HUGE, _HUGE)
    if k > 0:
        return (x & 0x807FFFFF) | (k << 23)
    return fmul((x & 0x80000000) | _TINY, _TINY)


def powf(x, y):
    """x ** y on raw patterns."""
    hx, hy = s32(x), s32(y)
    ix, iy = hx & 0x7FFFFFFF, hy & 0x7FFFFFFF
    if iy <= 0x7FFFFF:
        return F_ONE
    yisint = 0
    if hx < 0:
        if iy > 0x4B7FFFFF:
            yisint = 2
        elif iy > 0x3F7FFFFF:
            k = (0x96 - (iy >> 23)) & 31
            j = iy >> k
            if (j << k) & M32 == iy:
                yisint = 2 - (j & 1)
    if iy == 0x3F800000:
        return x if hy >= 0 else fdiv(F_ONE, x)
    if hy == 0x40000000:
        return fmul(x, x)
    if hy == 0x3F000000 and hx >= 0:
        raise NotImplementedError('powf(x, 0.5) goes to the square-root routine 0x3a84c0, '
                                  'which this model does not include')
    ax = x & 0x7FFFFFFF
    if ix <= 0x7FFFFF or ix == 0x3F800000:
        z = ax
        if hy < 0:
            z = fdiv(F_ONE, z)
        if hx >= 0:
            return z
        if ix == 0x3F800000 and yisint == 0:
            t = fsub(z, z)
            return fdiv(t, t)
        return z ^ 0x80000000 if yisint == 1 else z
    negative = (hx >> 31) & 1
    if negative and yisint == 0:
        t = fsub(x, x)
        return fdiv(t, t)
    if iy > 0x4D000000:
        if ix < 0x3F7FFFF8:
            return 0x7F7FFFFF if hy < 0 else F_ZERO
        if ix > 0x3F800007:
            return 0x7F7FFFFF if hy > 0 else F_ZERO
        t = fsub(x, F_ONE)
        w = fmul(fmul(t, t), fsub(F_HALF, fmul(t, fsub(0x3EAAAAAA, fmul(t, 0x3E800000)))))
        u = fmul(t, 0x3FB8AA00)
        v = fsub(fmul(t, 0x36ECA56F), fmul(w, 0x3FB8AA3A))
        t1 = fadd(u, v) & _TRIM
        t2 = fsub(v, fsub(t1, u))
    else:
        j = ix & 0x7FFFFF
        n = (ix >> 23) - 0x7F
        ix = j | 0x3F800000
        if j <= 0x1CC471:
            k = 0
        elif j <= 0x5DB3D6:
            k = 1
        else:
            k = 0
            n += 1
            ix -= 0x00800000
        ax = ix
        u = fsub(ax, _BP[k])
        v = fdiv(F_ONE, fadd(ax, _BP[k]))
        s = fmul(u, v)
        s_h = s & _TRIM
        t_h = (((ix >> 1) | 0x20000000) + (k << 21) + 0x00040000) & M32
        t_l = fsub(ax, fsub(t_h, _BP[k]))
        s_l = fmul(v, fsub(fsub(u, fmul(s_h, t_h)), fmul(s_h, t_l)))
        s2 = fmul(s, s)
        r = fadd(fmul(s2, 0x3E53F142), 0x3E6C3254)
        r = fadd(fmul(s2, r), 0x3E8BA304)
        r = fadd(fmul(s2, r), 0x3EAAAAAB)
        r = fadd(fmul(s2, r), 0x3EDB6DB7)
        r = fadd(fmul(s2, r), 0x3F199999)
        r = fadd(fmul(fmul(s2, s2), r), fmul(s_l, fadd(s_h, s)))
        s2 = fmul(s_h, s_h)
        t_h = fadd(fadd(s2, F_THREE), r) & _TRIM
        t_l = fsub(r, fsub(fsub(t_h, F_THREE), s2))
        u = fmul(s_h, t_h)
        v = fadd(fmul(s_l, t_h), fmul(t_l, s))
        p_h = fadd(u, v) & _TRIM
        p_l = fsub(v, fsub(p_h, u))
        z_h = fmul(p_h, 0x3F763800)
        z_l = fadd(fadd(fmul(p_h, 0x369DC39F), fmul(p_l, 0x3F76384E)), _DP_L[k])
        t = fint(n)
        t1 = fadd(fadd(fadd(z_h, z_l), _DP_H[k]), t) & _TRIM
        t2 = fsub(z_l, fsub(fsub(fsub(t1, t), _DP_H[k]), z_h))
    sign = 0xBF800000 if (negative and yisint == 1) else F_ONE
    y1 = y & _TRIM
    p_l = fadd(fmul(fsub(y, y1), t1), fmul(y, t2))
    p_h = fmul(y1, t1)
    z = fadd(p_l, p_h)
    j = s32(z)
    i = j & 0x7FFFFFFF
    if j > 0:
        if i > 0x43010000 or (i == 0x43010000 and flt(fsub(z, p_h), fadd(p_l, 0x3338AA3B))):
            return fmul(fmul(sign, _HUGE), _HUGE)
    else:
        if i > 0x42FC0000 or (i == 0x42FC0000 and fle(p_l, fsub(z, p_h))):
            return fmul(fmul(sign, _TINY), _TINY)
    n = 0
    if i > 0x3F000000:
        n = (j + (0x00800000 >> (((i >> 23) - 0x7E) & 31))) & M32
        k = ((n >> 23) & 0xFF) - 0x7F
        t = n & ~(0x007FFFFF >> (k & 31)) & M32
        n = ((n & 0x007FFFFF) | 0x00800000) >> ((23 - k) & 31)
        if j < 0:
            n = -n
        p_h = fsub(p_h, t)
        z = fadd(p_l, p_h)
    t = z & _TRIM
    u = fmul(t, 0x3F317200)
    v = fadd(fmul(fsub(p_l, fsub(t, p_h)), 0x3F317217), fmul(t, 0x35BFBE8C))
    z = fadd(u, v)
    w = fsub(v, fsub(z, u))
    t = fmul(z, z)
    r = fadd(fmul(t, 0x3331BB4B), 0xB5DDEA0E)
    r = fadd(fmul(t, r), 0x388AB354)
    r = fadd(fmul(t, r), 0xBB360B60)
    r = fadd(fmul(t, r), 0x3E2AAAAA)
    t1 = fsub(z, fmul(t, r))
    r = fsub(fdiv(fmul(z, t1), fsub(t1, F_TWO)), fadd(w, fmul(z, w)))
    z = fsub(F_ONE, fsub(r, z))
    j = s32(z + ((n << 23) & M32))
    z = _scalbnf(z, n) if (j >> 23) <= 0 else j & M32
    return fmul(sign, z)


# ---------------------------------------------------------------------------------------
# The executable and its tables
# ---------------------------------------------------------------------------------------
class Exe:
    """Read-only view of the loadable segments of an ELF file."""

    def __init__(self, path):
        with open(path, 'rb') as source:
            data = source.read()
        if data[:4] != b'\x7fELF':
            raise ValueError('%s is not an ELF file' % path)
        self.data = data
        phoff = struct.unpack_from('<I', data, 28)[0]
        phentsize, phnum = struct.unpack_from('<HH', data, 42)
        self.segments = []
        for index in range(phnum):
            kind, offset, vaddr, _paddr, filesz = struct.unpack_from('<5I', data, phoff + index * phentsize)
            if kind == 1:
                self.segments.append((vaddr, offset, filesz))

    def read(self, addr, size):
        for vaddr, offset, filesz in self.segments:
            if vaddr <= addr and addr + size <= vaddr + filesz:
                start = offset + addr - vaddr
                return self.data[start:start + size]
        raise ValueError('address 0x%08x is not in the file' % addr)

    def u8(self, addr): return self.read(addr, 1)[0]
    def s8(self, addr): return s8(self.read(addr, 1)[0])
    def s16(self, addr): return struct.unpack('<h', self.read(addr, 2))[0]
    def u32(self, addr): return struct.unpack('<I', self.read(addr, 4))[0]
    def s32(self, addr): return struct.unpack('<i', self.read(addr, 4))[0]
    def u64(self, addr): return struct.unpack('<Q', self.read(addr, 8))[0]
    def f64(self, addr): return struct.unpack('<d', self.read(addr, 8))[0]

    def cstr(self, addr):
        """Bytes of the zero-terminated string at addr."""
        for vaddr, offset, filesz in self.segments:
            if vaddr <= addr < vaddr + filesz:
                start = offset + addr - vaddr
                return self.data[start:self.data.index(b'\0', start)]
        raise ValueError('address 0x%08x is not in the file' % addr)


class Definition:
    """One 0x40-byte definition row (base table or preset table)."""
    __slots__ = ('addr', 'index', 'preset', 'name', 'level', 'weight', 'count', 'damage_min',
                 'damage_max', 'price', 'armor', 'attack', 'slot', 'category', 'subtype',
                 'damage_bits', 'flags', 'picture', 'model_row')

    def __repr__(self):
        return '<Definition %s%d at 0x%x>' % ('preset ' if self.preset else '', self.index, self.addr)


class Prefix:
    __slots__ = ('addr', 'index', 'key', 'level', 'mask', 'damage_mask')


class Suffix:
    __slots__ = ('addr', 'index', 'key', 'level')


class Tables:
    """Everything the model reads from the executable."""

    def __init__(self, exe):
        self.exe = exe if isinstance(exe, Exe) else Exe(exe)
        e = self.exe
        self.defs = self._definitions(A_DEFS, False)
        self.presets = self._definitions(A_PRESETS, True)
        self.by_addr = {d.addr: d for d in self.defs + self.presets}
        self.prefixes = []
        addr = A_PREFIXES
        while e.u32(addr):
            p = Prefix()
            p.addr, p.index, p.key, p.level = addr, len(self.prefixes), e.cstr(e.u32(addr)), e.s16(addr + 4)
            p.mask, p.damage_mask = e.u64(addr + 0x18), e.u32(addr + 0x20)
            self.prefixes.append(p)
            addr += 0x28
        self.suffixes = []
        addr = A_SUFFIXES
        while e.u32(addr):
            s = Suffix()
            s.addr, s.index, s.key, s.level = addr, len(self.suffixes), e.cstr(e.u32(addr)), e.s16(addr + 4)
            self.suffixes.append(s)
            addr += 0x14
        self.formats = [(e.cstr(addr), code) for addr, code in TOKEN_FORMATS]
        self.token_words = [text.split(b'%')[0] for text, _code in self.formats]
        self.potion_stem = e.cstr(S_POTION_STEM)
        self.thrown_stem = e.cstr(S_THROWN_STEM)
        self.circlet_stem = e.cstr(S_CIRCLET_STEM)
        self.circlet_stem_equip = e.cstr(S_CIRCLET_STEM_EQUIP)
        self.arrows = e.cstr(S_ARROWS)
        self.recall = e.cstr(S_RECALL)
        self.name_key_format = e.cstr(S_NAME_SUFFIX)
        self.name_space = e.cstr(S_SPACE)
        self.of_key = e.cstr(S_OF_KEY)
        self.gold_scale_multiplayer = e.f64(A_GOLD_SCALE_MP)

    def _definitions(self, base, preset):
        e, rows, addr = self.exe, [], base
        while e.u32(addr):
            d = Definition()
            d.addr, d.index, d.preset = addr, len(rows), preset
            d.name = e.cstr(e.u32(addr))
            d.level, d.weight, d.count = e.s16(addr + 4), e.u32(addr + 8), e.s16(addr + 0xC)
            d.damage_min, d.damage_max = e.s16(addr + 0xE), e.s16(addr + 0x10)
            d.price, d.armor, d.attack = e.s32(addr + 0x14), e.s16(addr + 0x18), e.s16(addr + 0x1A)
            d.slot, d.category, d.subtype = e.s8(addr + 0x1C), e.s8(addr + 0x1D), e.s8(addr + 0x1E)
            d.damage_bits, d.flags = e.u32(addr + 0x20), e.u64(addr + 0x28)
            picture = e.u32(addr + 0x30)
            d.picture = e.cstr(picture) if picture else None
            d.model_row = e.s16(addr + 0x34)
            rows.append(d)
            addr += 0x40
        return rows

    # The original indexes these arrays with the definition's category byte and does not
    # check it; reading the pointer at the computed address keeps that behaviour.
    def prefix_text(self, prefix_index, category):
        """Modifier text of a prefix for a category, or None for a null pointer."""
        pointer = self.exe.u32(A_PREFIXES + 0xC + (prefix_index * 10 + category) * 4)
        return self.exe.cstr(pointer) if pointer else None

    def suffix_text(self, suffix_index, category):
        pointer = self.exe.u32(A_SUFFIXES + 8 + (suffix_index * 5 + category) * 4)
        return self.exe.cstr(pointer) if pointer else None

    def weapon_mult(self, subtype):
        return self.exe.u32(A_WEAPON_MULT + 4 * subtype)

    def quality_row(self, row):
        return [self.exe.u32(A_QUALITY + 12 * row + 4 * i) for i in range(3)]


# ---------------------------------------------------------------------------------------
# The shared generator and the globals the item code reads
# ---------------------------------------------------------------------------------------
class Rng:
    """g_randSeed 0x404464: seed = seed * 0x19660d + 0x3c6ef35f; a draw is seed >> 16."""

    def __init__(self, seed=0):
        self.seed = seed & M32
        self.draws = 0

    def next(self):
        self.seed = (self.seed * 0x19660D + 0x3C6EF35F) & M32
        self.draws += 1
        return self.seed >> 16


class Game:
    """The globals read by the generators and by loot_generateDrops.

    num_players  g_numPlayers 0x4d8ae0
    classes      class id of each player record (g_players[i] + 0x50); id 4 is the class
                 that steers armour drops toward cloth
    difficulty   g_difficultyIdx 0x4f719c (1..5)
    pvp_a, pvp_b g_pvpModeA 0x4f711c, g_pvpModeB 0x4f7120
    level        g_levelMonsterLevel 0x4f714c, a float: pass a number, or level_raw
    """

    def __init__(self, num_players=1, classes=(0, 0, 0, 0), difficulty=1, pvp_a=0, pvp_b=0,
                 level=1.0, level_raw=None):
        self.num_players = num_players
        self.classes = tuple(classes)
        self.difficulty = difficulty
        self.pvp_a, self.pvp_b = pvp_a, pvp_b
        self.level = f_bits(level) if level_raw is None else level_raw & M32

    def level_times_0_4(self):
        """level_monsterLevelTimes0_4 0x1ebf20"""
        level = self.level
        if self.pvp_b:
            level = fmax(F_ONE, fsub(level, 0x40800000))
        return fmul(level, 0x3ECCCCCC)

    def level_times_difficulty(self):
        """level_monsterLevelTimesDifficulty 0x1ebf70"""
        factor = {2: 0x41100000, 3: 0x41200000, 4: 0x41300000, 5: 0x41400000}.get(self.difficulty, 0x41000000)
        level = self.level
        if self.pvp_b:
            level = fmax(F_ONE, fsub(level, 0x40800000))
        return fmul(level, factor)

    def cloth_fraction(self):
        """Players of class 4 divided by the player count (0x104d00-0x104d54)."""
        count = sum(1 for i in range(max(self.num_players, 0)) if self.classes[i] == 4)
        return fdiv(fint(count), fint(self.num_players))


# ---------------------------------------------------------------------------------------
# The item record
# ---------------------------------------------------------------------------------------
class Item:
    """The 0x48-byte item record.

    +0x00 definition pointer   +0x04 s16 count        +0x08 u64 flags
    +0x10 s16[4], +0x18 s16[4] (zero)                 +0x20 u8 prefix, +0x21 u8 suffix
    +0x24 four modifier slots {s16 code, s16 v0, v1, v2}; code -1 = empty

    +0x44 four bytes of padding

    The code that builds a record never writes +0x06, +0x22, the three values of an
    empty slot or the padding at +0x44: those bytes keep whatever the stack held.  pack()
    takes them from `stale`.
    """
    __slots__ = ('definition', 'count', 'flags', 'a', 'b', 'prefix', 'suffix', 'mods')

    def __init__(self, definition=None):
        self.definition = definition
        self.count = 0
        self.flags = 0
        self.a = [0, 0, 0, 0]
        self.b = [0, 0, 0, 0]
        self.prefix = 0xFF
        self.suffix = 0xFF
        self.mods = [None, None, None, None]       # None or [code, v0, v1, v2]

    def copy(self):
        other = Item(self.definition)
        other.count, other.flags = self.count, self.flags
        other.a, other.b = list(self.a), list(self.b)
        other.prefix, other.suffix = self.prefix, self.suffix
        other.mods = [None if m is None else list(m) for m in self.mods]
        return other

    @property
    def variant(self):
        return (self.flags >> 11) & 0x1F

    def get(self, code, which=0):
        """Value `which` of the first slot holding `code`, or 0 (the lookup the original
        inlines everywhere)."""
        for mod in self.mods:
            if mod is not None and mod[0] == code:
                return mod[1 + which]
        return 0

    def set_modifier(self, code, v0=0, v1=0, v2=0):
        """Store into the first slot that is empty or already holds `code`; a fifth
        distinct code is dropped.  Returns the slot index or -1."""
        for index, mod in enumerate(self.mods):
            if mod is None or mod[0] == code:
                self.mods[index] = [code, s16(v0), s16(v1), s16(v2)]
                return index
        return -1

    def undefined_offsets(self):
        """Byte offsets whose content the building code leaves to chance."""
        offsets = [6, 7, 0x22, 0x23, 0x44, 0x45, 0x46, 0x47]
        for index, mod in enumerate(self.mods):
            if mod is None:
                offsets.extend(range(0x26 + 8 * index, 0x2C + 8 * index))
        return offsets

    def pack(self, stale=None):
        out = bytearray(stale if stale is not None else bytes(ITEM_SIZE))
        if len(out) != ITEM_SIZE:
            raise ValueError('stale must be 0x48 bytes')
        struct.pack_into('<Ih', out, 0, self.definition.addr if self.definition else 0, s16(self.count))
        struct.pack_into('<Q', out, 8, self.flags & M64)
        struct.pack_into('<8h', out, 0x10, *(self.a + self.b))
        out[0x20], out[0x21] = self.prefix & 0xFF, self.suffix & 0xFF
        for index, mod in enumerate(self.mods):
            if mod is None:
                struct.pack_into('<h', out, 0x24 + 8 * index, -1)
            else:
                struct.pack_into('<4h', out, 0x24 + 8 * index, *mod)
        return bytes(out)

    @classmethod
    def unpack(cls, tables, data):
        """Record bytes back to an Item (a slot whose code is -1 becomes empty)."""
        item = cls(tables.by_addr.get(struct.unpack_from('<I', data, 0)[0]))
        item.count = struct.unpack_from('<h', data, 4)[0]
        item.flags = struct.unpack_from('<Q', data, 8)[0]
        item.a = list(struct.unpack_from('<4h', data, 0x10))
        item.b = list(struct.unpack_from('<4h', data, 0x18))
        item.prefix, item.suffix = data[0x20], data[0x21]
        for index in range(4):
            mod = list(struct.unpack_from('<4h', data, 0x24 + 8 * index))
            item.mods[index] = None if mod[0] == -1 else mod
        return item


def encode_definition_index(tables, item):
    """item_encodeDefinitionIndex 0x107ea4: the saved form of the definition pointer.
    Preset rows come out negative."""
    return (item.definition.addr - A_DEFS) >> 6


def decode_definition_index(tables, index):
    """item_decodeDefinitionIndex 0x107ec0"""
    return tables.by_addr.get((A_DEFS + index * 0x40) & M32)


def same_identity(a, b):
    """item_sameIdentityFields 0x108924: b has a definition, and flags, definition and
    the 32-bit word at +0x20 agree.  That word includes +0x22, which the parser leaves
    unwritten; this model compares prefix and suffix only."""
    return (b.definition is not None and a.flags == b.flags and a.definition is b.definition
            and a.prefix == b.prefix and a.suffix == b.suffix)


def copy_mutable(dst, src):
    """item_copyMutableFields 0x107ca8: everything except the definition pointer; the
    two s16[4] arrays and +0x22 are zeroed."""
    dst.count, dst.flags = src.count, src.flags
    dst.prefix, dst.suffix = src.prefix, src.suffix
    dst.a, dst.b = [0, 0, 0, 0], [0, 0, 0, 0]
    dst.mods = [None if m is None else list(m) for m in src.mods]


def resource_index(item):
    """item_getResourceIndex 0x1083f8: row of the model table."""
    row = item.definition.model_row
    if item.flags & 0x1000000000:
        row += (item.flags >> 11) & 0x1F
    return row


# ---------------------------------------------------------------------------------------
# The descriptor parser
# ---------------------------------------------------------------------------------------
_SPACE = b' \t\n\v\f\r'


def scan(fmt, text):
    """The C library's sscanf for the formats the parser uses: literal characters and
    %d.  Returns (result, values): result is the number of values converted, or -1 when
    the text ends before the first conversion is done (which the parser also takes as a
    match, because it only tests for non-zero)."""
    values = []
    pos, fpos, flen, tlen = 0, 0, len(fmt), len(text)
    while fpos < flen:
        c = fmt[fpos]
        if c in _SPACE:
            fpos += 1
            while pos < tlen and text[pos] in _SPACE:
                pos += 1
            continue
        if c != 0x25:                                   # a literal character
            if pos >= tlen:
                return (len(values) or -1), values
            if text[pos] != c:
                return len(values), values
            pos += 1
            fpos += 1
            continue
        if fmt[fpos + 1:fpos + 2] != b'd':
            raise ValueError('format %r uses a conversion this model does not know' % fmt)
        fpos += 2
        if pos >= tlen:
            return (len(values) or -1), values
        while text[pos] in _SPACE:
            pos += 1
            if pos >= tlen:
                return (len(values) or -1), values
        start = pos
        if text[pos] in b'+-':
            pos += 1
        digits = pos
        while pos < tlen and 0x30 <= text[pos] <= 0x39:
            pos += 1
        if pos == digits:
            return len(values), values
        number = int(text[start:pos])
        number = max(-(1 << 63), min((1 << 63) - 1, number))    # strtol saturates a 64-bit long
        values.append(s32(number))
    return len(values), values


def randomize_variant(item, rng):
    """item_randomizeVariant 0x1046e0: bits 11-15 of the flags become a draw modulo the
    definition's variant count; no draw when the count is 0."""
    count = (item.definition.flags >> 11) & 0x1F
    variant = rng.next() % count if count > 0 else 0
    item.flags = (variant << 11) | (item.flags & 0xFFFFFFFFFFFF07FF)


def find_definition(tables, name, presets=False):
    """Linear search by exact name; an unknown name silently becomes row 0."""
    rows = tables.presets if presets else tables.defs
    for row in rows:
        if row.name == name:
            return row
    return rows[0]


def parse_descriptor(tables, text, variant=-1, use_presets=False, rng=None):
    """item_parseDescriptor 0x1069b8.

    text         bytes (or str): a definition name followed by +token modifiers
    variant      -1: draw the visual variant from rng; otherwise the variant to store
    use_presets  non-zero: the whole text is looked up as the name of a preset row
    rng          Rng; needed only when a draw can happen
    """
    if isinstance(text, str):
        text = text.encode('latin-1')
    if b'\0' in text:
        text = text[:text.index(b'\0')]
    if len(text) >= DESCRIPTOR_BUFFER:
        raise ValueError('descriptor of %d bytes overruns the parser\'s %d-byte buffer'
                         % (len(text), DESCRIPTOR_BUFFER))
    pieces = text.split(b'+')
    definition = find_definition(tables, text if use_presets else pieces[0], bool(use_presets))
    item = Item(definition)
    item.count = definition.count
    item.flags = definition.flags
    for token in pieces[1:]:
        for fmt, code in tables.formats:
            result, values = scan(fmt, token)
            if result == 0:
                continue
            values = (values + [0, 0, 0])[:3]
            if code is None:
                variant = values[0]
            else:
                wanted = fmt.count(b'%d')
                item.set_modifier(code, values[0], values[1] if wanted > 1 else 0,
                                  values[2] if wanted > 2 else 0)
            break
    if variant == -1:
        randomize_variant(item, rng)
    else:
        item.flags = ((s32(variant << 11)) & M64) | (item.flags & 0xFFFFFFFFFFFF07FF)
    return item


# ---------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------
def item_weight(item):
    """item_getWeight 0x103e08 -> raw float."""
    d = item.definition
    weight = d.weight
    limit = 0x40A00000 if d.category == 1 else 0x41700000          # 5.0 armour, 15.0 other
    if flt(limit, weight):
        weight = fsub(weight, fmul(fsub(weight, limit), 0x3F44EC4F))
    weight = fmul(weight, fint(item.count))
    return fadd(fmul(fmul(fint(item.get(0x24)), F_HUNDREDTH), weight), weight)


def item_armor(item):
    """item_getArmorValue 0x103ec8 -> int."""
    armor = item.definition.armor
    percent = item.get(0x0D)
    if percent != 0:
        armor = s32(armor + ftrunc(fmul(fint(armor), fmul(fint(percent), F_HUNDREDTH))))
    return armor


def item_attack_rating(item):
    """item_getModifiedField1a 0x103f88 -> int."""
    rating = fint(item.definition.attack)
    percent = item.get(0x23)
    if percent != 0:
        rating = fadd(fmul(fmul(fint(percent), F_HUNDREDTH), rating), rating)
    return ftrunc(rating)


def item_damage_range(item, with_elemental=True):
    """item_getDamageRange 0x104100 -> (min, max)."""
    d = item.definition
    high, low = fint(d.damage_max), fint(d.damage_min)
    percent = item.get(0x23)
    if percent != 0:
        factor = fadd(fmul(fint(percent), F_HUNDREDTH), F_ONE)
        high, low = fmul(high, factor), fmul(low, factor)
    if with_elemental:
        for code in (0x15, 0x16, 0x18, 0x17, 0x26):
            if item.get(code, 0) != 0:
                low = fadd(low, fint(item.get(code, 0)))
                high = fadd(high, fint(item.get(code, 1)))
    low = ftrunc(fint(ftrunc(fadd(fmul(low, F_ONE), F_HALF))))
    high = ftrunc(fint(ftrunc(fadd(fmul(high, F_ONE), F_HALF))))
    return low, high


# Weapon part of the value: constant of each elemental modifier (min += v0*k, max += v1*k
# when v2 <= 0), and of each "chance, range" modifier.
_VALUE_FLAT = {0x15: 0x3F028FB0, 0x16: 0x3F051EC9, 0x17: 0x3F028F4B, 0x18: 0x3EFFFFDE, 0x26: 0x3F000000}
_VALUE_BURST = {0x1F: 0x3F70621B, 0x20: 0x3F743914, 0x22: 0x3F826E6D}
# Exponent of the term each remaining modifier adds: total += powf(v0, exponent).
_VALUE_EXPONENT = {
    0x00: 0x3FC03E18, 0x01: 0x3FCCCAAB, 0x02: 0x3FB8D299, 0x03: 0x3FB3322F, 0x04: 0x3FAF5B9A,
    0x05: 0x3FD31105, 0x06: 0x3FD2D056, 0x07: 0x3FF998B7, 0x08: 0x3FF623D9, 0x09: 0x3FFCCC57,
    0x0A: 0x40001027, 0x0B: 0x3FDB8383, 0x0C: 0x3FDBA3D2, 0x0D: 0x3F4105F2, 0x1A: 0x3FFF9D4D,
    0x1C: 0x4009BA3C, 0x1E: 0x3FFDD263, 0x2A: 0x402CCD29,
}


def _weapon_base(tables, item):
    low, high = item_damage_range(item, False)
    low, high = fmul(fint(low), 0x3F199913), fmul(fint(high), 0x3F199913)
    for mod in item.mods:
        code = mod[0] if mod is not None else -1
        if code == 0x13:
            high, low = fmul(high, 0x3F666666), fmul(low, 0x3F666666)
        elif code == 0x14:
            speed = fmul(fint(item.get(0x14)), 0x3D3851EB)
            low = fadd(fmul(speed, low), low)
            high = fadd(fmul(speed, high), high)
        elif code in _VALUE_FLAT:
            if item.get(code, 2) <= 0:
                low = fadd(low, fmul(fint(item.get(code, 0)), _VALUE_FLAT[code]))
                high = fadd(high, fmul(fint(item.get(code, 1)), _VALUE_FLAT[code]))
        elif code == 0x19:
            low = fadd(low, fmul(fint(item.get(code, 0)), 0x3E0A3D70))
            high = fadd(high, fmul(fint(item.get(code, 1)), 0x3E0A3D70))
        elif code == 0x1B:
            low = fadd(low, fmul(fmul(fint(item.get(code, 0)), 0x3FA2D0AA), fmul(low, F_HUNDREDTH)))
            high = fadd(high, fmul(fmul(fint(item.get(code, 1)), 0x3FA2D0AA), fmul(high, F_HUNDREDTH)))
        elif code == 0x1D:
            chance = fmul(fint(item.get(code, 0)), F_HUNDREDTH)
            low = fadd(low, fmul(fmul(fadd(chance, chance), low), 0x3FD997BB))
            chance = fmul(fint(item.get(code, 1)), F_HUNDREDTH)
            high = fadd(high, fmul(fmul(fadd(chance, chance), high), 0x3FD997BB))
        elif code in _VALUE_BURST:
            chance = fmul(fint(item.get(code, 0)), F_HUNDREDTH)
            low = fadd(low, fmul(fmul(fint(item.get(code, 1)), chance), _VALUE_BURST[code]))
            high = fadd(high, fmul(fmul(fint(item.get(code, 2)), chance), _VALUE_BURST[code]))
        elif code == 0x21:
            chance = fmul(fint(item.get(code, 0)), F_HUNDREDTH)
            term = fmul(fmul(fint(item.get(code, 1)), chance), 0x42540011)
            low, high = fadd(low, term), fadd(high, term)
    mult = tables.weapon_mult(item.definition.subtype)
    high, low = fmul(high, mult), fmul(low, mult)
    return fsub(fmul(fadd(low, high), F_HALF), fmul(fsub(high, low), 0x3DCCCCCC))


def item_value(tables, item):
    """item_getValue 0x1024a8 -> signed 32-bit gold value."""
    d = item.definition
    if d.price >= 1:
        return s32(d.price * item.count)
    base = F_ZERO
    if d.category == 0:
        if d.subtype != 5:
            base = _weapon_base(tables, item)
    elif d.category == 1:
        base = fmul(fmul(fint(item_armor(item)), 0x3F199999), 0x3F8CCC5F)
        if d.slot == 3:
            base = fmul(base, F_HALF)
    elif d.category == 2:
        base = 0x40A00000
    total = powf(base, 0x3FF99999)
    for mod in item.mods:
        code = mod[0] if mod is not None else -1
        if code == 0x0D and d.category == 1:
            code = 0x1A                 # the armour case jumps into the code-0x1a case
        if code in _VALUE_EXPONENT:
            total = fadd(total, powf(fint(item.get(code)), _VALUE_EXPONENT[code]))
        elif code == 0x25:
            total = fadd(fmul(fmul(fint(item.get(0x25)), F_HUNDREDTH), total), total)
    total = fmul(total, 0x42200000)
    if tables.thrown_stem in d.name or d.flags & 0x1C0000000000:
        total = fmul(total, 0x3B83126E)
    if d.category == 2 and d.slot in (7, 5, 6, 14, 15):
        total = fmul(total, 0x41002899)
    return s32(ftrunc(fadd(total, F_HALF)) * item.count)


def required_level_for_value(value):
    """Level requirement the generators attach (0x104a98-0x104af0): from the value, 80 at
    most."""
    excess = s32(value - 1200)
    if excess < 0:
        excess = 0
    level = s32(ftrunc(powf(fint(excess // 5000), 0x3F28F5C2)) * 2 + 1)
    return level if level < 0x51 else 0x50


# ---------------------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------------------
EQUIP_OK, EQUIP_CLASS, EQUIP_LEVEL, EQUIP_STRENGTH, EQUIP_INTELLIGENCE = 0, 1, 2, 3, 4
EQUIP_DEXTERITY, EQUIP_STAMINA, EQUIP_BLUNT, EQUIP_SLASHING, EQUIP_FLAG_41 = 5, 6, 7, 8, 9


class Player:
    """The fields of a player record (g_players[slot] 0x4d8af0, stride 0x4c30) that the
    equip check reads: +0x50 class id, +0x58 s8 level (the acknowledged one), +0x90 /
    +0x94 / +0x98 / +0x9c strength, intelligence, dexterity, stamina, and the skill
    ranks, pairs {s16 id, s16 rank} from +0x4b08 ended by id -1 (player_getSkillRank
    0x1bf330)."""

    def __init__(self, class_id=0, level=1, strength=0, intelligence=0, dexterity=0, stamina=0, skills=None):
        self.class_id, self.level = class_id, level
        self.strength, self.intelligence, self.dexterity, self.stamina = strength, intelligence, dexterity, stamina
        self.skills = dict(skills or {})

    def skill_rank(self, skill_id):
        return self.skills.get(skill_id, 0)


def equip_restriction(tables, player, item):
    """inventory_checkEquipAllowed 0x1c4948 -> 0 when the player may equip the item, else
    the reason (EQUIP_*).  Every test is made and a later failing test replaces an
    earlier reason; the class named by a requiredclass modifier is tested last."""
    d = item.definition
    cls = player.class_id
    reason = 0
    if d.category == 1:
        if item.flags & 0x80000:                                    # cloth: class 4 only
            reason = int(cls != 4)
        elif tables.circlet_stem_equip not in d.name and cls == 4:  # class 4: cloth and circlets
            reason = 1
    elif cls == 1:
        reason = int(d.subtype in (3, 4) or d.damage_bits in (8, 4))
    elif cls == 3:
        reason = int(d.subtype in (1, 2, 3))
    elif cls == 4:
        reason = int(d.subtype in (1, 2, 4) or d.damage_bits in (8, 4))
        if item.flags & 0x1000000000:
            reason = 0
        if (d.subtype == 0 or item.flags & 0x80000000000) and player.skill_rank(0x5C) != 0:
            reason = 0
    elif cls == 6:
        reason = int(d.subtype in (1, 4))
    if s8(player.level) < item.get(0x0E):
        reason = EQUIP_LEVEL
    if player.strength < item.get(0x0F):
        reason = EQUIP_STRENGTH
    if player.intelligence < item.get(0x10):
        reason = EQUIP_INTELLIGENCE
    if player.dexterity < item.get(0x11):
        reason = EQUIP_DEXTERITY
    if player.stamina < item.get(0x12):
        reason = EQUIP_STAMINA
    if s16(player.skill_rank(0x3C)) < item.get(0x27):
        reason = EQUIP_BLUNT
    if s16(player.skill_rank(0x3D)) < item.get(0x28):
        reason = EQUIP_SLASHING
    if item.flags & 0x20000000000:
        reason = EQUIP_FLAG_41
    wanted = item.get(0x13)
    if wanted != 0 and cls != wanted - 1:
        reason = EQUIP_CLASS
    return reason


def load_resources(tables, rng):
    """What item_loadResources 0x108434 does to the shared generator: it parses every
    base definition with variant -1, one draw for each definition that has visual
    variants.  Returns the number of draws."""
    before = rng.draws
    for d in tables.defs:
        parse_descriptor(tables, d.name, -1, False, rng)
    return rng.draws - before


# ---------------------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------------------
def weapon_group(d):
    """item_classifyCategory0 0x104c04"""
    if d.category != 0:
        return -1
    if d.subtype == 6:
        return 0
    return 1 if d.subtype == 3 and d.damage_bits & 8 else 2


def armor_group(d):
    """item_classifyCategory1 0x104c48"""
    if d.category != 1:
        return -1
    return {11: 0, 4: 1, 9: 2, 12: 3, 3: 4}.get(d.slot, 5)


def _attach_required_level(tables, item, name, value):
    if tables.potion_stem not in name:
        item.set_modifier(0x0E, required_level_for_value(value))


def _cloth_roll(game, rng):
    """First draw of both budgeted generators for armour: True when cloth is excluded."""
    return ftrunc(fmul(game.cloth_fraction(), F_2_POW_16)) < rng.next() % 0xFFFF


def generate_preset(tables, game, rng, budget, category, level):
    """item_generateFromSpecialTable 0x104758 -> Item or None.

    category -1 = any.  Ten picks from the preset table; the most valuable one not above
    the budget wins (a later pick of equal value replaces an earlier one)."""
    exclude_cloth = _cloth_roll(game, rng) if category == 1 else False

    def eligible(d):
        if d.flags & 0x10000 or (category != -1 and d.category != category):
            return False
        if level < d.level or d.flags & 0x800000000:
            return False
        return not (exclude_cloth and d.category == 1 and d.flags & 0x80000)

    rows = [d for d in tables.presets if eligible(d)]
    if not rows:
        return None
    best, result = -1, None
    for _ in range(10):
        # The countdown stops at the first eligible row for a draw of 0 as well as 1, so
        # the first row is twice as likely and the last one is never picked.
        pick = rng.next() % len(rows)
        row = rows[max(pick - 1, 0)]
        item = parse_descriptor(tables, row.name, -1, True, rng)
        value = item_value(tables, item)
        _attach_required_level(tables, item, row.name, value)
        if best <= value <= budget:
            best, result = value, item
    if best < 0:
        return None
    randomize_variant(result, rng)
    return result


def generate_with_affixes(tables, game, rng, budget, category, want_suffix, level):
    """item_generateWithAffixes 0x104ca4 -> Item or None.

    category     0 weapon, 1 armour, 2 other (or -1)
    want_suffix  -1 lets the function decide; >= 1 asks for one
    level        cap for definitions, prefixes and suffixes
    """
    exclude_cloth = prefer_cloth = False
    if category == 1:
        fraction = game.cloth_fraction()
        if ftrunc(fmul(fraction, F_2_POW_16)) < rng.next() % 0xFFFF:
            exclude_cloth = True
        elif flt(F_ZERO, fraction):
            prefer_cloth = rng.next() % 0xFFFF <= 0xBFFF
    group_weapon = group_armor = -1
    if category == 0:
        roll = fmul(fint(rng.next()), F_2_POW_M16)
        group_weapon = 0 if flt(roll, 0x3D8F5C28) else 1 if flt(roll, 0x3DF5C28F) else 2
        if group_weapon == 0:
            budget = int(budget / 5)                                # C division
    elif category == 1:
        roll = fmul(fint(rng.next()), F_2_POW_M16)
        group_armor = 5
        for index, limit in enumerate((0x3E23D70A, 0x3EA3D70A, 0x3EF5C28F, 0x3F23D70A, 0x3F4CCCCC)):
            if flt(roll, limit):
                group_armor = index
                break

    def eligible(d):
        if d.flags & 0x10000 or (category != -1 and d.category != category) or level < d.level:
            return False
        if d.flags & 0x800000000 or d.flags & 0x200000000000:
            return False
        if prefer_cloth and d.category == 1 and not d.flags & 0x80000 \
                and tables.circlet_stem not in d.name:
            return False
        if exclude_cloth and d.category == 1 and d.flags & 0x80000:
            return False
        if d.category == 0 and weapon_group(d) != group_weapon:
            return False
        return not (d.category == 1 and armor_group(d) != group_armor)

    rows = [d for d in tables.defs if eligible(d)]
    if not rows:
        return None
    if want_suffix == -1:
        if category == 2:
            want_suffix = 1
        elif rng.next() < 0x1964:
            want_suffix = 1
    # The prefix loop runs over the first N rows, N being the number of prefixes whose
    # level fits, and tests each row's level again.
    prefix_rows = sum(1 for p in tables.prefixes if p.level <= level)
    if not any(suffix.level <= level for suffix in tables.suffixes):
        raise ValueError('no suffix has a level of %d or less: the original redraws for ever' % level)
    best, result = -1, None

    def consider(item, name):
        nonlocal best, result
        value = item_value(tables, item)
        _attach_required_level(tables, item, name, value)
        if best <= value <= budget:
            best, result = value, item

    for attempt in range(15 if category == 0 else 10):
        d = rows[rng.next() % len(rows)]
        suffix = rng.next() % len(tables.suffixes)
        while level < tables.suffixes[suffix].level:
            suffix = rng.next() % len(tables.suffixes)
        suffix_text = tables.suffix_text(suffix, d.category)
        suffix_fits = want_suffix > 0 and suffix_text is not None and tables.potion_stem not in d.name
        if category == 2:
            text = d.name + (suffix_text if suffix_fits else tables.suffix_text(0, d.category))
            item = parse_descriptor(tables, text, -1, False, rng)
            item.prefix = 0xFF
            item.suffix = suffix if suffix_fits else 0
            consider(item, d.name)
            continue
        for p in range(prefix_rows):
            prefix = tables.prefixes[p]
            if level < prefix.level:
                continue
            text = d.name
            if attempt:
                prefix_text = tables.prefix_text(p, d.category)
                allowed = (d.flags & prefix.mask) != 0 or prefix.mask == 0
                if allowed and prefix_text is not None:
                    text += prefix_text
                if suffix_fits:
                    text += suffix_text
            item = parse_descriptor(tables, text, -1, False, rng)
            if attempt:
                if allowed and prefix_text is not None:
                    item.prefix = p
                if prefix.damage_mask:
                    item.prefix = p if d.damage_bits & prefix.damage_mask else 0xFF
                if suffix_fits:
                    item.suffix = suffix
            consider(item, d.name)
    if best < 0:
        return None
    randomize_variant(result, rng)
    return result


def _difficulty_floor(game):
    return {2: 0x11, 3: 0x1B, 4: 0x20, 5: 0x26}.get(game.difficulty, -1)


def _pick_plain(tables, rng, rows):
    if not rows:
        return None
    row = rows[rng.next() % len(rows)]
    item = parse_descriptor(tables, row.name, -1, False, rng)
    randomize_variant(item, rng)
    return item


def generate_reagent(tables, game, rng, level, picture=None):
    """item_generateFlag35Entry 0x106214 -> Item or None.  level is taken as a signed
    16-bit value; picture, when given, restricts the choice to one picture name (and
    drops the test of flag 0x10000)."""
    level, floor = s16(level), _difficulty_floor(game)
    rows = []
    for d in tables.defs:
        if d.category != 2 or not d.flags & 0x800000000 or not floor <= d.level <= level:
            continue
        if picture is None:
            if d.flags & 0x10000:
                continue
        else:
            if d.picture is None:
                raise ValueError('definition %d has no picture name; the original compares '
                                 'the string at address 0 here' % d.index)
            if d.picture != picture:
                continue
        rows.append(d)
    return _pick_plain(tables, rng, rows)


def generate_figurine(tables, game, rng, level):
    """item_generateFlag45Entry 0x106658 -> Item or None."""
    level, floor = s16(level), _difficulty_floor(game)
    rows = [d for d in tables.defs if not d.flags & 0x10000 and d.category == 2
            and d.flags & 0x200000000000 and floor <= d.level <= level]
    return _pick_plain(tables, rng, rows)


def generate_consumable(tables, game, rng):
    """item_generateConsumable 0x108590 -> Item: a mana potion, a healing potion, or the
    third descriptor.  The size comes from the level and min(difficulty, 3)."""
    tier = game.difficulty if game.difficulty < 4 else 3
    low, high = (0x7FFF, 0x10000) if game.pvp_b else (30000, 60000)
    roll = rng.next()
    if roll >= high:
        return parse_descriptor(tables, tables.recall, -1, False, rng)
    table = A_MANA_POTIONS if roll < low else A_HEAL_POTIONS
    size = fadd(fmul(fmul(fint(rng.next()), F_2_POW_M16), 0x3E4CCCCC), fmul(game.level, 0x3DA3D70A))
    index = 11 if fle(size, F_ONE) else 10 if fle(size, F_TWO) else 9
    name = tables.exe.cstr(tables.exe.u32(table + 4 * (index - 3 * tier)))
    return parse_descriptor(tables, name, -1, False, rng)


def shop_append_unique(tables, game, rng, stock, budget, category):
    """item_appendGeneratedUnique 0x107d54: up to two tries of generate_with_affixes at
    level 1 for an item whose definition and flags are not already in `stock` (a list of
    Items); appends only definition, count and flags, as the original does.

    The original does not look at the generator's return value: after a try that made
    nothing it compares and appends whatever its stack buffer holds, which is the item of
    the earlier try or, on the first try, unwritten stack.  The first case is modelled;
    the second raises NotImplementedError."""
    current = None
    for _ in range(2):
        item = generate_with_affixes(tables, game, rng, budget, category, -1, 1)
        if item is not None:
            current = item
        if current is None:
            raise NotImplementedError('the first try made nothing: the original appends '
                                      'unwritten stack content')
        if not any(o.definition is current.definition and o.flags == current.flags for o in stock):
            entry = Item(current.definition)
            entry.count, entry.flags = current.count, current.flags
            stock.append(entry)
            return entry
    return None


# ---------------------------------------------------------------------------------------
# Loot
# ---------------------------------------------------------------------------------------
class World:
    """What loot_generate_drops asks of the world.  The default records the drops and
    draws nothing; the game's constructors do draw (GameObject_ctor 0x14cb10 takes one
    value from the shared generator for each object, and loot_spawnGold scatters with
    three draws per try), so a caller that wants the seed of a real game overrides these.

    spawn_item returns False to model a failed pool allocation: the drop is lost and, for
    equipment, the throw-angle draw is skipped.
    """

    def __init__(self):
        self.drops = []

    def spawn_gold(self, amount, rng):
        self.drops.append(('gold', amount))

    def spawn_item(self, kind, item, rng):
        self.drops.append((kind, item))
        return True

    def throw(self, item, angle):
        self.drops.append(('throw', angle))


def spawn_named_item(tables, rng, world, text):
    """loot_spawnNamedItem 0x100ba0 (fixed drops: the dropitem property, script
    built-ins): parse the descriptor with variant -1 and make the item prop.  Between the
    two the original searches a free spot (world_findFreeSpot 0x14acf8, three draws per
    try), which is left to the World: its spawn_item receives the kind 'named'."""
    item = parse_descriptor(tables, text, -1, False, rng)
    world.spawn_item('named', item, rng)
    return item


def gold_scatter(rng, ground_height, x, y, z):
    """The scatter loop of loot_spawnGold 0x100974 (run only for an amount above 0): up to
    ten tries; each draws three numbers until the point lies in the unit ball, moves 36
    units along x and y, and is accepted when the ground there is within 6 of z.
    ground_height(x_raw, y_raw, z_raw) -> raw float.  Returns the raw position."""
    for _ in range(10):
        while True:
            a = fmul(fint(rng.next()), F_2_POW_M16)
            b = fmul(fint(rng.next()), F_2_POW_M16)
            c = fmul(fint(rng.next()), F_2_POW_M16)
            vx, vy, vz = (fsub(fadd(v, v), F_ONE) for v in (a, b, c))
            if not flt(F_ONE, fadd(fadd(fmul(vx, vx), fmul(vy, vy)), fmul(vz, vz))):
                break
        dx = fmul(fmul(vx, 0x41400000), F_THREE)
        dy = fmul(fmul(vy, 0x41400000), F_THREE)
        height = ground_height(fadd(dx, x), fadd(dy, y), z)
        if flt(fsub(height, z) & 0x7FFFFFFF, 0x40C00000):
            return fadd(x, dx), fadd(y, dy), height
    return x, y, z


def half_level(game):
    """Level argument of the reagent and figurine generators (0x1012f4-0x101314)."""
    whole = ftrunc(game.level)
    return s16(s32((whole + ((whole >> 31) & 1)) << 15) >> 16)


def loot_generate_drops(tables, game, rng, world, gold_scale, gold_chance, quality_row,
                        item_chance, angle=0, reagent_filter=None, force_preset=False):
    """loot_generateDrops 0x100d54.

    gold_scale, gold_chance, quality_row, item_chance: raw float patterns, as the caller
    (Creature_dropLoot and others) passes them.  angle: 16-bit angle units.
    reagent_filter: a picture name or None.  Every draw comes from rng, in the original
    order.  The z offset and throw speed arguments of the original only position and
    launch the objects and are left to the World.

    Returns how the function ended: 'no reagent' or 'no figurine' when that roll succeeded
    but no definition qualified (the original returns at once, skipping the later
    rolls), 'no equipment roll', 'no equipment' (the generator made nothing), or 'done'.
    """
    if game.num_players >= 2:
        item_chance = fadd(item_chance, item_chance)
        gold_chance = float_times_double(gold_chance, 1.5)
        gold_scale = float_times_double(gold_scale, tables.gold_scale_multiplayer)
    item_chance = fmul(item_chance, F_HALF)
    if game.pvp_b:
        item_chance = 0x3E800000
    # quality: poor (x0.5), normal, or good (x3), from the blended row
    if flt(quality_row, F_ZERO):
        quality_row = F_ZERO
    if flt(0x41100000, quality_row):
        quality_row = 0x41100000
    row = ftrunc(quality_row)
    blend = fsub(quality_row, fint(row))
    here, there = tables.quality_row(row), tables.quality_row(row + 1)
    keep = fsub(F_ONE, blend)
    roll = fmul(fint(rng.next()), F_2_POW_M16)
    poor = fadd(fmul(here[0], keep), fmul(there[0], blend))
    normal = fadd(fmul(here[1], keep), fmul(there[1], blend))
    quality = F_ONE
    if flt(roll, poor):
        quality = F_HALF
    if flt(fadd(poor, normal), roll):
        quality = F_THREE
    # gold
    roll = rng.next()
    gold_rolls = 1 if roll <= 0xEE47 else 2 if roll <= 0xF9FF else 3
    gold_scale = fmul(gold_scale, game.level_times_0_4())
    if game.pvp_a:
        gold_chance = F_ZERO
    for _ in range(gold_rolls):
        if flt(fint(rng.next()), fmul(gold_chance, F_2_POW_16)):
            amount = ftrunc(fmul(fmul(fint(rng.next() % 40 + 40), gold_scale), 0x3D0F5C28))
            world.spawn_gold(amount, rng)
    # potion or arrows
    extra = fint(game.num_players - 1)
    if game.pvp_b:
        chance = fadd(fmul(extra, 0x3D75C28F), 0x3DA3D70A)
    else:
        chance = fadd(fmul(extra, 0x3D4CCCCC), 0x3D999999)
    if flt(fint(rng.next()), fmul(chance, F_2_POW_16)):
        if rng.next() < 8000:
            item = parse_descriptor(tables, tables.arrows, -1, False, rng)
        else:
            item = generate_consumable(tables, game, rng)
        world.spawn_item('consumable', item, rng)
    # reagent
    chance = 0x3C03126E if reagent_filter else 0x3C4CCCCC
    if flt(fint(rng.next()), fmul(chance, F_2_POW_16)):
        item = generate_reagent(tables, game, rng, half_level(game), reagent_filter or None)
        if item is None:
            return 'no reagent'
        world.spawn_item('reagent', item, rng)
    # figurine
    if flt(fint(rng.next()), 0x43A3D70A):
        item = generate_figurine(tables, game, rng, half_level(game))
        if item is None:
            return 'no figurine'
        world.spawn_item('figurine', item, rng)
    # equipment
    if not flt(fint(rng.next()), fmul(item_chance, F_2_POW_16)):
        return 'no equipment roll'
    spread = fadd(fmul(fmul(fint(rng.next()), F_2_POW_M16), 0x3ECCCCCC), 0x3F4CCCCC)
    budget = fmul(fmul(quality, spread), fmul(game.level_times_difficulty(), 0x43480000))
    roll = fint(rng.next())
    if flt(roll, 0x4423D666):
        budget = fmul(budget, F_THREE)
    elif flt(roll, 0x454CCBFF):
        budget = fadd(budget, budget)
    whole_budget = ftrunc(budget)
    category = 0
    if rng.next() >= 30000:
        category = 2 if rng.next() > 0xEA5F else 1
    level = ftrunc(game.level)
    if flt(fint(rng.next()), 0x44F5C28F) or force_preset:
        factor = 0x3FD99999 if flt(F_THREE, budget) else 0x40E00000
        item = generate_preset(tables, game, rng, ftrunc(fmul(fint(whole_budget), factor)), category, level)
    else:
        item = generate_with_affixes(tables, game, rng, whole_budget, category, -1, level)
    if item is None:
        return 'no equipment'
    if world.spawn_item('equipment', item, rng):
        world.throw(item, s32(angle + (rng.next() & 0x3FFF) - 0x2000))
    return 'done'


# ---------------------------------------------------------------------------------------
# Display names
# ---------------------------------------------------------------------------------------
def strip_grammar_suffix(text, language):
    """itemName_stripGrammarSuffix 0x101998 -> (text without the tag, form number).

    Language 4 uses a one-letter tag "_m", "_f", "_n", "_p" (forms 1-4); languages 1 and 3
    use "_ms", "_fs", "_mp", "_fp" (forms 1-4) and also accept a one-letter tag; every
    other language has no tags and returns form 0.  text is a str of at least three
    characters when the language has tags (the original reads before the buffer for a
    shorter one)."""
    n = len(text)
    if language == 4:
        if n < 2:
            raise ValueError('text shorter than a tag')
        if text[n - 2] != '_':
            return text, 0
        return text[:n - 2], {'m': 1, 'f': 2, 'n': 3, 'p': 4}.get(text[n - 1].lower(), 0)
    if language not in (1, 3):
        return text, 0
    if n < 3:
        raise ValueError('text shorter than a tag')
    if text[n - 3] != '_' and text[n - 2] != '_':
        return text, 1
    pair = (text[n - 2].lower(), text[n - 1].lower())
    form = {('m', 's'): 1, ('f', 's'): 2, ('m', 'p'): 3, ('f', 'p'): 4}.get(pair)
    if form:
        return text[:n - 3], form
    if pair[1] == 'm':
        return text[:n - 2], 1
    if pair[1] == 'f':
        return text[:n - 2], 2
    return text[:n - 3], 0


def _formatted(text):
    """The engine's wide formatter wstr_format 0x19ea78 used as a copy.  It gives percent
    signs a meaning and its callers here use 128-character buffers; neither is modelled."""
    if '%' in text or len(text) >= 128:
        raise ValueError('text %r is outside what this model covers' % text)
    return text


def affix_form(text_lookup, language, form, key):
    """itemName_getAffixForm 0x101d0c: the text of an affix key; when it holds
    bar-separated alternatives and form is not -1, alternative number `form` (an index
    past the last alternative reads on in the original; not modelled).  In languages 1
    and 3 a text that had alternatives then loses its last three characters."""
    text = _formatted(text_lookup(key))
    has_bar = False
    if form != -1:
        has_bar = '|' in text
        if has_bar:
            parts = text.split('|')
            if form >= len(parts):
                raise ValueError('form %d of %r' % (form, text))
            text = parts[form]
    if language in (1, 3) and has_bar:
        if len(text) < 3:
            raise ValueError('alternative shorter than a tag')
        text = text[:len(text) - 3]
    return text


def build_name(tables, item, decorated, text_lookup, language=0):
    """itemName_buildLocalizedName 0x101e48 -> str.

    text_lookup(key) -> str is the string table (text_lookup 0x173c84; keys are str).
    language is the signed byte at 0x44fddc.  Raises ValueError for the inputs the model
    does not cover (see _formatted, affix_form and strip_grammar_suffix).
    """
    d = item.definition
    space = tables.name_space.decode('latin-1')

    def noun(name):
        key = (tables.name_key_format % name.split(b'+')[0]).decode('latin-1')
        return strip_grammar_suffix(text_lookup(key), language)

    if not decorated or item.flags & 0x200:
        return strip_grammar_suffix(text_lookup((tables.name_key_format % d.name).decode('latin-1')), language)[0]
    prefix_key = tables.prefixes[item.prefix].key.decode('latin-1') if item.prefix != 0xFF else None
    suffix_key = tables.suffixes[item.suffix].key.decode('latin-1') if item.suffix != 0xFF else None
    if language in (1, 3):
        out, form = noun(d.name)
        if prefix_key is not None:
            out += space + affix_form(text_lookup, language, form - 1 if form in (1, 2, 3, 4) else -1, prefix_key)
        if suffix_key is not None:
            out += space + text_lookup(suffix_key)
        return out
    if language == 4:
        out = ''
        if prefix_key is not None:
            form = noun(d.name)[1]
            out = affix_form(text_lookup, language, {1: 0, 2: 1, 4: 3}.get(form, 2), prefix_key) + space
        out += noun(d.name)[0]
        if suffix_key is not None:
            out += space + text_lookup(suffix_key)
        return out
    out = ''
    # In the remaining languages the form argument is whatever the noun's tag stripping
    # returned, which is 0 for them.
    if prefix_key is not None:
        out = affix_form(text_lookup, language, 0, prefix_key) + space
    out += noun(d.name)[0]
    if suffix_key is not None:
        out += space + text_lookup(tables.of_key.decode('latin-1')) + space
        out += affix_form(text_lookup, language, 0, suffix_key)
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('usage: ref_items.py SLUS_209.73 "descriptor" [seed]\n'
              'prints the record, value, weight, armour, damage and seed after parsing')
        sys.exit(0)
    _tables = Tables(sys.argv[1])
    _rng = Rng(int(sys.argv[3], 0) if len(sys.argv) > 3 else 0)
    _item = parse_descriptor(_tables, sys.argv[2], rng=_rng)
    print('record   ', _item.pack().hex())
    print('value    ', item_value(_tables, _item))
    print('weight   ', f_value(item_weight(_item)))
    print('armour   ', item_armor(_item))
    print('damage   ', item_damage_range(_item))
    print('attack   ', item_attack_rating(_item))
    print('seed     ', '0x%08x after %d draw(s)' % (_rng.seed, _rng.draws))
