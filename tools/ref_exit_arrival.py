"""Independent arrival expectations for the round-five exit probes.

Nothing here is game code or game data. The disc helpers describe how a
read-only copy of the disc's BG/DATA folder is presented to the original
CD layer: a synthetic ISO9660 directory with synthetic sector numbers. The
placement helpers restate Player1_ctor 0x158928 and world_findFreeSpot
0x14acf8 over tools/ref_world.py terrain queries. The record helpers
restate save_writeLevelState 0x218600 and its three section writers.
"""
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # appended: tools/dis.py must not shadow stdlib dis
import gob                                          # noqa: E402
import ref_world as W                               # noqa: E402

M32 = 0xFFFFFFFF
SECTOR = 0x800
DIR_LSN, FIRST_FILE_LSN = 1000, 2000
LCG_MUL, LCG_ADD = 0x19660D, 0x3C6EF35F
ONE, TWO_M16, SIX = 0x3F800000, 0x37800000, 0x40C00000
BOX_Z = 0x47C35000                  # 100000.0, the box half height in 0x14acf8
FREE_TRIES = 50


# ---------------------------------------------------------------------------
# Disc presentation (synthetic sector numbers; real names and sizes)
# ---------------------------------------------------------------------------

def _record(ident, lsn, size, flags=0):
    rec = bytearray(33 + len(ident) + ((33 + len(ident)) & 1))
    rec[0] = len(rec)
    struct.pack_into('<I', rec, 2, lsn)
    struct.pack_into('>I', rec, 6, lsn)
    struct.pack_into('<I', rec, 10, size)
    struct.pack_into('>I', rec, 14, size)
    rec[25] = flags
    rec[32] = len(ident)
    rec[33:33 + len(ident)] = ident
    return bytes(rec)


def iso_layout(listing):
    """listing: (name, size) pairs. Return (sectors, files, toc).

    files maps an upper-case ISO name ('NAME.EXT;1') to (lsn, size, name).
    toc is what the directory parser 0x1721e4 should store, in record order:
    (identifier bytes, lsn, size), including the 0x00 and 0x01 records.
    Records never cross a sector; the rest of a sector is zero.
    """
    files, toc = {}, []
    lsn = FIRST_FILE_LSN
    records = [_record(b'\0', DIR_LSN, 0, 2), _record(b'\1', DIR_LSN - 1, 0, 2)]
    toc += [(b'\0', DIR_LSN, 0), (b'\1', DIR_LSN - 1, 0)]
    for name, size in sorted(listing):
        ident = (name.upper() + ';1').encode('ascii')
        files[ident.decode()] = (lsn, size, name)
        records.append(_record(ident, lsn, size))
        toc.append((ident, lsn, size))
        lsn += (size + SECTOR - 1) // SECTOR
    sectors, cur = [], bytearray()
    for rec in records:
        if len(cur) + len(rec) > SECTOR:
            sectors.append(bytes(cur.ljust(SECTOR, b'\0')))
            cur = bytearray()
        cur += rec
    sectors.append(bytes(cur.ljust(SECTOR, b'\0')))
    return sectors, files, toc


def gob_plan(gob_bytes):
    """Return (entries, sequential). entries: (name, offset, size).

    gob_loadAll 0x1737d8 does not read the stored offsets. It reads entry k at
    0x800 plus the 0x800-rounded sizes of entries 0..k-1. sequential says
    whether the stored offsets equal that layout.
    """
    entries = gob.gob_entries(gob_bytes)
    at, same = SECTOR, True
    for _name, offset, size in entries:
        same &= offset == at
        at += (size + SECTOR - 1) & ~(SECTOR - 1)
    return entries, same


def gob_reads(entries, gob_lsn, tex_lsn, world_lump=0, tex_bytes=0x5000):
    """sceCdRead (lsn, sector count) list for one gob_loadAll call.

    The directory sector first. Each lump is one read. world_fixup 0x181d30
    reads the level .tex header (0x5000 bytes) while the lump holding the
    .world entry is fixed up, so that read follows that lump's read.
    """
    reads = [(gob_lsn, 1)]
    at = SECTOR
    for index, (_name, _offset, size) in enumerate(entries):
        rounded = (size + SECTOR - 1) & ~(SECTOR - 1)
        reads.append((gob_lsn + (at >> 11), (rounded + SECTOR - 1) >> 11))
        at += rounded
        if index == world_lump:
            reads.append((tex_lsn, (tex_bytes + SECTOR - 1) >> 11))
    return reads


def lump_names(entries):
    """Lump table names gob_loadAll stores, in GOB order."""
    rename = {'gaydark1.lmp': 'faydark1.lmp', 'gaydark2.lmp': 'faydark2.lmp'}
    return [rename.get(name, name) for name, _o, _s in entries]


def first_by_extension(lmp_bytes, ext):
    """lump_findNthByExtension(lmp, ext, 0): first entry whose text after the
    last '.' equals ext."""
    for name, _offset, _size in gob.lmp_entries(lmp_bytes):
        if '.' in name and name.rsplit('.', 1)[1] == ext:
            return name
    return None


def lmp_entry(lmp_bytes, name):
    for entry, offset, size in gob.lmp_entries(lmp_bytes):
        if entry == name:
            return lmp_bytes[offset:offset + size]
    return None


# ---------------------------------------------------------------------------
# objects.ob records (format in docs/objects.md, "Level-object records")
# ---------------------------------------------------------------------------

def objects(ob):
    """Yield (index, class, angle, (x, y, z) raw patterns, props) per record."""
    count, _flags, table = struct.unpack_from('<hHi', ob, 0)
    at = 8

    def text(off):
        return ob[table + off:ob.index(b'\0', table + off)].decode('latin1')

    for index in range(count):
        cls, size, angle = struct.unpack_from('<ihH', ob, at)
        pos = struct.unpack_from('<3I', ob, at + 8)
        props, q = [], at + 20
        while True:
            value, = struct.unpack_from('<i', ob, q)
            q += 4
            if value == 0:
                break
            props.append(text(value))
        yield index, text(cls), angle, pos, props
        at += size


def prop(props, key):
    """obj_getPropStr 0x14f4c0 with index 0: text after 'key='."""
    for item in props:
        if item.startswith(key) and item[len(key):len(key) + 1] == '=':
            return item[len(key) + 1:]
    return None


def prop_int(props, key):
    """obj_getPropInt 0x14c880 with default 0: C atoi of the value."""
    value = prop(props, key)
    if value is None:
        return 0
    digits, sign, i = 0, 1, 0
    value = value.lstrip(' \t\n\r\v\f')
    if value[:1] in '+-':
        sign = -1 if value[0] == '-' else 1
        i = 1
    while i < len(value) and value[i].isdigit():
        digits = digits * 10 + int(value[i])
        i += 1
    return sign * digits


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

def lcg(seed):
    return (seed * LCG_MUL + LCG_ADD) & M32


def free_spot(level, seed, origin, radius, size, climb=0, blockers=()):
    """world_findFreeSpot 0x14acf8(out, in, radius, size, flag, climb).

    origin is three raw float patterns. blockers are (x, y, r) patterns of
    objects with flag bit 0 clear that the box query returns. Returns
    (out, found, seed). out keeps the origin until one try passes the
    terrain tests; z of out is the terrain height of that try.
    """
    fr, fs = W.i2f(radius), W.i2f(size)
    ox, oy, oz = origin
    out = tuple(origin)
    tries = 0
    while tries < FREE_TRIES:
        while True:
            seed = lcg(seed)
            a = W.fsub(_twice(seed), ONE)
            seed = lcg(seed)
            b = W.fsub(_twice(seed), ONE)
            seed = lcg(seed)
            c = W.fsub(_twice(seed), ONE)
            d = W.fadd(W.fadd(W.fmul(a, a), W.fmul(b, b)), W.fmul(c, c))
            if not W.flt(ONE, d):
                break
        dx, dy = W.fmul(a, fr), W.fmul(b, fr)
        cand = (W.fadd(dx, ox), W.fadd(dy, oy), oz)
        if W.terrain_test_flag1(level, fs, cand) != 0:
            tries += 1
            continue
        height = W.terrain_height(level, fs, (cand[0], cand[1], W.fadd(0, oz)))
        if not W.flt(W.fsub(height, oz), SIX) and not climb:
            tries += 1
            continue
        out = (W.fadd(ox, dx), W.fadd(oy, dy), height)
        reach = W.i2f((size * size) & M32)
        blocked = False
        for bx, by, br in blockers:
            ex, ey = W.fsub(bx, out[0]), W.fsub(by, out[1])
            dist = W.fadd(W.fmul(ex, ex), W.fmul(ey, ey))
            if W.fle(dist, W.fadd(reach, W.fmul(br, br))):
                blocked = True
                break
        if not blocked:
            return out, 1, seed
        tries += 1
    return out, 0, seed


def _twice(seed):
    value = W.fmul(W.i2f(seed >> 16), TWO_M16)
    return W.fadd(value, value)


def player_start(markers, rank, prev, entrance, leg):
    """Player1_ctor's choice over markers in file order.

    markers: (props) lists. Returns (rank after, list of taken marker
    indexes in order). A taken marker rewrites all four spawn slots.
    """
    taken = []
    for index, props in enumerate(markers):
        if rank == 3:
            continue
        frm, name = prop(props, 'from'), prop(props, 'name')
        take = False
        if rank <= 0:
            take, rank = True, 1
        elif rank < 2 and prop_int(props, 'default') != 0:
            take, rank = True, 1
        gate_check = leg
        if frm is not None and frm == prev:
            if not leg:
                take, rank = True, 2
        if gate_check and frm is not None and frm == 'gate':
            take, rank = True, 3
        if name is not None and not leg and name == entrance:
            take, rank = True, 3
        if take:
            taken.append(index)
    return rank, taken


def spawn_facing(angle, seed):
    """One facing draw after a slot's free spot: (halfword, seed)."""
    seed = lcg(seed)
    return (angle + (seed >> 16) % 4000 - 2000) & 0xFFFF, seed


# ---------------------------------------------------------------------------
# Level-state record (save_writeLevelState 0x218600)
# ---------------------------------------------------------------------------

def intern(table, text):
    """saveStr_intern 0x14de60 over a string area of length-prefixed names.

    Returns (offset of the text after its length byte, table)."""
    at = 0
    while at < len(table):
        length = table[at]
        if table[at + 1:at + 1 + length] == text:
            return at + 1, table
        at += length + 2
    table = table + bytes([len(text)]) + text + b'\0'
    return at + 1, table


def object_record(table, cls, props, angle, pos, tail, at=0):
    """obj_writeRecord 0x14df50 for one object. Returns (bytes, table).

    cls and props are bytes. pos is three raw patterns. tail is what the
    class's slot-9 body writes. at is the record's address modulo 8: the tail
    starts at (record + 4*props + 0x1f) & ~7 as an address, and the record
    size, stored as s16 at +4, is rounded up to 4.
    """
    name_off, table = intern(table, cls)
    prop_offs = []
    for item in props:
        off, table = intern(table, item)
        prop_offs.append(off)
    body = struct.pack('<IhH3I', name_off, 0, angle, *pos)
    body += b''.join(struct.pack('<I', o) for o in prop_offs) + struct.pack('<I', 0)
    tail_at = ((at + 4 * len(prop_offs) + 0x1F) & ~7) - at
    record = bytearray(body.ljust(tail_at, b'\0'))
    gap = (len(body), tail_at)              # obj_writeRecord does not store these
    record += tail
    size = ((at + len(record) + 3) & ~3) - at
    pad = (len(record), size)               # nor these; the copy carries stack bytes
    record = record.ljust(size, b'\0')
    struct.pack_into('<h', record, 4, size)
    return bytes(record), table, (gap, pad)


def objects_section(records, base=0):
    """world_saveState 0x14e5c8 with no thinning.

    records: (cls, props, angle, pos, tail) in walk order, text as str.
    base is the address modulo 8 of the record area. Returns (bytes, holes,
    padded length). bytes runs from the section start: s16 count, u16 1,
    s32 string-table offset (record bytes + 8), records, strings. holes are
    (start, end) ranges that obj_writeRecord leaves unset in its stack record
    buffer; memcpy 0x14e734 copies them with the records. The padded length
    rounds the end up to 4; those pad bytes are not written at all.
    """
    table, body, holes = b'', b'', []
    for cls, props, angle, pos, tail in records:
        rec, table, (gap, pad) = object_record(
            table, cls.encode('latin1'), [p.encode('latin1') for p in props],
            angle, pos, tail, (base + len(body)) & 7)
        at = 8 + len(body)
        for lo, hi in (gap, pad):
            if hi > lo:
                holes.append((at + lo, at + hi))
        body += rec
    head = struct.pack('<hHi', len(records), 1, len(body) + 8)
    out = head + body + table
    return out, holes, (len(out) + 3) & ~3


def automap_pack(grid):
    """automap_packExplored 0x16865c: 108 rows of 54 bytes from the grid.

    Byte j of row i is (grid[2*row + 8*j + 1] & 0xf0) + (grid[... + 5] >> 4),
    where row advances by 0x1b0 per output row and is doubled into a byte
    offset."""
    out = bytearray()
    row = 0
    for _i in range(0, 0xD8, 2):
        base = 2 * row
        for j in range(0, 0xD8, 4):
            at = base + 2 * j
            out.append(((grid[at + 1] & 0xF0) + (grid[at + 5] >> 4)) & 0xFF)
        row += 0x1B0
    return bytes(out)
