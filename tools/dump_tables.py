#!/usr/bin/env python3
"""Dump the rules tables of Champions: Return to Arms from YOUR OWN copy of the game.

This script contains no game data. It knows where the tables are (addresses, row sizes,
field offsets -- see docs/data-tables.md) and reads the values out of the files you give it.

  python3 dump_tables.py SLUS_209.73 --list
  python3 dump_tables.py SLUS_209.73 --table item_defs                  # CSV on stdout
  python3 dump_tables.py SLUS_209.73 --table levels --format json
  python3 dump_tables.py SLUS_209.73 --all --out dumps/                 # one file per table
  python3 dump_tables.py SLUS_209.73 --balance BALANCE.LMP --table monster_balance
  python3 dump_tables.py SLUS_209.73 --text GTEXT.LMP --table text
  python3 dump_tables.py SLUS_209.73 --objects DRUNARE.GOB --table objects
  python3 dump_tables.py --iso game.iso --all --out dumps/              # everything, from a disc image

Inputs
  executable      SLUS_209.73 (US v2.00). Other builds are refused unless --force is given,
                  because every address below belongs to that build.
  --balance F     BALANCE.LMP or an extracted monsters.bal
  --text F        GTEXT.LMP (or GTEXT_DE/FR/SP.LMP) or an extracted gtext.uni
  --objects F..   level .GOB files, level .lmp lumps or extracted objects.ob files
  --iso F         a disc image; the executable, BALANCE.LMP, GTEXT.LMP and every level GOB
                  are then read from it (explicit file arguments win)

Tables marked "code" in --list are not data tables in the game: the values are constants
inside functions. They are recovered by following the instructions of those functions in
a straight line, without evaluating branches, so a value that the game sets only under a
condition is listed without its condition. Treat them as a reading aid and check anything
important against the function whose address is given in the row.

Standard library only. Python 3.8 or later.
"""
import argparse
import bisect
import csv
import hashlib
import io
import json
import mmap
import os
import struct
import sys

KNOWN_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"

# ---------------------------------------------------------------------------------------
# Addresses for SLUS_209.73 v2.00. Layout only; see docs/data-tables.md for the evidence.
# ---------------------------------------------------------------------------------------
A = dict(
    item_base=0x3F7650, item_preset=0x3EA550, item_prefix=0x400E50, item_suffix=0x4019E0,
    item_model=0x3E9CE0, loot_quality=0x3E9C18, weapon_value_mult=0x3E9CB0,
    body_codes=0x4026D8, potions_mana=0x402708, potions_heal=0x402730,
    class_stats=0x4EF400, exp_table=0x41B558, legacy_abilities=0x4F5CC8,
    level_table=0x4F7210, mission_table=0x4FE540, mission_text_keys=0x4F83C0,
    skill_table=0x41B170, skill_tree_pictures=0x53B5B8,
    # functions
    fn_item_parse=0x1069B8, fn_skill_static_init=0x16AC74, fn_creature_ctor=0x109D68,
    fn_creature_droploot=0x10F2C8, fn_boss_rank=0x10D940, fn_object_factory=0x159C94,
    fn_pool_new=0x14FDB8, fn_strcasecmp=0x3B81A0, fn_str_prefix=0x159C20,
    fn_start_items=0x1ACC78, fn_recalc_stats=0x1B6458,
)
CLASS_PASSIVES = {0: 0x4EBBE8, 1: 0x4EBEC0, 2: 0x4EC400, 3: 0x4EC2B0, 4: 0x4EC0B8,
                  5: 0x4EC748, 6: 0x4EC5C0}
SKILL_TREES = {0: 0x4F4898, 1: 0x4F4E38, 2: 0x4F4B68, 3: 0x4F5108, 4: 0x4F53D8,
               5: 0x4F5720, 6: 0x4F5A18}
NUM_CLASSES = 7
NUM_SKILL_IDS = 102          # ids 0..101, id 0 unused
EXP_ENTRIES = 81             # index = character level, last entry is the cap sentinel
THIS = 0x7F000000            # stand-in address for "the object being constructed"


# ---------------------------------------------------------------------------------------
# ELF
# ---------------------------------------------------------------------------------------
class Elf:
    def __init__(self, data):
        self.d = data
        if data[:4] != b"\x7fELF":
            raise SystemExit("not an ELF file")
        phoff, = struct.unpack_from("<I", data, 28)
        phentsize, phnum = struct.unpack_from("<HH", data, 42)
        self.segs = []
        for i in range(phnum):
            t, off, va, _pa, fsz, _msz, _fl, _al = struct.unpack_from("<8I", data, phoff + i * phentsize)
            if t == 1:
                self.segs.append((va, off, fsz))
        shoff, = struct.unpack_from("<I", data, 32)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 46)
        secs = [struct.unpack_from("<10I", data, shoff + i * shentsize) for i in range(shnum)]
        stro = secs[shstrndx][4]
        self.sections = {}
        for s in secs:
            name = data[stro + s[0]:data.index(b"\0", stro + s[0])].decode("latin1")
            self.sections[name] = (s[3], s[4], s[5])
        self.text = self.sections[".text"]
        self._funcs = None

    def off(self, va):
        for sva, soff, fsz in self.segs:
            if sva <= va < sva + fsz:
                return soff + (va - sva)
        return None

    def has(self, va, n=1):
        o = self.off(va)
        return o is not None and self.off(va + n - 1) == o + n - 1

    def bytes(self, va, n):
        o = self.off(va)
        if o is None:
            raise ValueError("address %08x is not in the file" % va)
        return self.d[o:o + n]

    def u8(self, va): return self.bytes(va, 1)[0]
    def s8(self, va): return struct.unpack("<b", self.bytes(va, 1))[0]
    def u16(self, va): return struct.unpack("<H", self.bytes(va, 2))[0]
    def s16(self, va): return struct.unpack("<h", self.bytes(va, 2))[0]
    def u32(self, va): return struct.unpack("<I", self.bytes(va, 4))[0]
    def s32(self, va): return struct.unpack("<i", self.bytes(va, 4))[0]
    def u64(self, va): return struct.unpack("<Q", self.bytes(va, 8))[0]
    def s64(self, va): return struct.unpack("<q", self.bytes(va, 8))[0]
    def f32(self, va): return struct.unpack("<f", self.bytes(va, 4))[0]

    def cstr(self, va, maxlen=400):
        """Printable zero-terminated string at va, or None."""
        if not va:
            return None
        o = self.off(va)
        if o is None:
            return None
        e = self.d.find(b"\0", o, o + maxlen)
        if e <= o:
            return None
        s = self.d[o:e]
        if all(32 <= c < 127 for c in s):
            return s.decode("ascii")
        return None

    def in_text(self, va):
        a, _o, sz = self.text
        return a <= va < a + sz

    def words(self, start, end):
        o = self.off(start)
        return struct.unpack_from("<%dI" % ((end - start) // 4), self.d, o)

    def funcs(self):
        """Sorted function entry addresses: call targets, code pointers in data, and code
        that follows a return and opens a stack frame."""
        if self._funcs is not None:
            return self._funcs
        ta, _o, tsz = self.text
        w = self.words(ta, ta + tsz)
        out = {ta}
        for i, x in enumerate(w):
            if x >> 26 == 3:
                tgt = ((ta + i * 4) & 0xF0000000) | ((x & 0x03FFFFFF) << 2)
                if self.in_text(tgt):
                    out.add(tgt)
            elif x == 0x03E00008:                     # jr $ra
                j = i + 2
                while j < len(w) and w[j] == 0:
                    j += 1
                if j < len(w) and (w[j] & 0xFFFF8000) == 0x27BD8000:
                    out.add(ta + j * 4)
        for name in (".data", ".rodata", ".ctors", ".dtors", ".sdata"):
            if name not in self.sections:
                continue
            a, o, sz = self.sections[name]
            for v in struct.unpack_from("<%dI" % (sz // 4), self.d, o):
                if v % 4 == 0 and self.in_text(v) and v not in out:
                    # a data word that only happens to look like a code address is common
                    # (prices, experience values); accept it when the code there follows a
                    # return, or opens a stack frame
                    k = (v - ta) // 4
                    j = k - 1
                    while j > 0 and w[j] == 0 and k - j < 4:
                        j -= 1
                    if (k >= 2 and w[k - 2] == 0x03E00008) or (j >= 1 and w[j - 1] == 0x03E00008) \
                            or (w[k] & 0xFFFF8000) == 0x27BD8000:
                        out.add(v)
        self._funcs = sorted(out)
        return self._funcs

    def func_range(self, va):
        f = self.funcs()
        i = bisect.bisect_right(f, va) - 1
        end = f[i + 1] if i + 1 < len(f) else self.text[0] + self.text[2]
        return f[i], end


def f32_from_bits(bits):
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


def fnum(x):
    """Shortest decimal that reads back as the same 32-bit float."""
    s = repr(x)
    for nd in range(1, 10):
        s = "%.*g" % (nd, x)
        if struct.pack("<f", float(s)) == struct.pack("<f", x):
            break
    v = float(s)
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


# ---------------------------------------------------------------------------------------
# Generic fixed-row tables
# ---------------------------------------------------------------------------------------
def read_field(e, base, off, kind):
    a = base + off
    if kind == "str":
        p = e.u32(a)
        return e.cstr(p) if p else ""
    if kind == "s8": return e.s8(a)
    if kind == "u8": return e.u8(a)
    if kind == "s16": return e.s16(a)
    if kind == "u16": return e.u16(a)
    if kind == "s32": return e.s32(a)
    if kind == "u32": return e.u32(a)
    if kind == "s64": return e.s64(a)
    if kind == "x32": return "0x%08x" % e.u32(a)
    if kind == "x64": return "0x%016x" % e.u64(a)
    if kind == "f32": return fnum(e.f32(a))
    if kind.startswith("char"):
        n = int(kind[4:])
        return e.bytes(a, n).split(b"\0")[0].decode("latin1")
    raise ValueError(kind)


def read_rows(e, base, size, fields, count=None, stop=None):
    """fields: (name, offset, kind). Rows are read until `count`, or until stop(e, addr)."""
    rows = []
    i = 0
    while True:
        a = base + i * size
        if count is not None and i >= count:
            break
        if count is None and stop(e, a):
            break
        row = {"index": i, "address": "0x%x" % a}
        for name, off, kind in fields:
            row[name] = read_field(e, a, off, kind)
        rows.append(row)
        i += 1
    return rows


def null_ptr(e, a):
    return e.u32(a) == 0


ITEM_DEF_FIELDS = [
    ("name", 0x00, "str"), ("level", 0x04, "s16"), ("weight", 0x08, "f32"),
    ("default_count", 0x0C, "s16"), ("damage_min", 0x0E, "s16"), ("damage_max", 0x10, "s16"),
    ("fixed_price", 0x14, "s32"), ("armor", 0x18, "s16"), ("attack_rating", 0x1A, "s16"),
    ("equip_slot", 0x1C, "u8"), ("category", 0x1D, "u8"), ("weapon_subtype", 0x1E, "u8"),
    ("damage_type_bits", 0x20, "x32"), ("flags", 0x28, "x64"), ("picture", 0x30, "str"),
    ("model_row", 0x34, "s16"),
]


def t_item_defs(ctx):
    return read_rows(ctx.elf, A["item_base"], 0x40, ITEM_DEF_FIELDS, stop=null_ptr)


def t_item_presets(ctx):
    rows = read_rows(ctx.elf, A["item_preset"], 0x40, ITEM_DEF_FIELDS, stop=null_ptr)
    for r in rows:                      # the name of a preset is a whole descriptor
        r["descriptor"] = r.pop("name")
        r["base_name"] = r["descriptor"].split("+")[0]
        r["save_index"] = r["index"] - (len(rows) + 1)
    return rows


def t_item_prefixes(ctx):
    return read_rows(ctx.elf, A["item_prefix"], 0x28, [
        ("text_key", 0x00, "str"), ("level", 0x04, "s16"), ("colour_weapon", 0x06, "s8"),
        ("colour_armor", 0x07, "s8"), ("colour_weapon_alt", 0x08, "s8"),
        ("mods_weapon", 0x0C, "str"), ("mods_armor", 0x10, "str"), ("mods_other", 0x14, "str"),
        ("allowed_def_flags", 0x18, "x64"), ("allowed_damage_types", 0x20, "x32")], stop=null_ptr)


def t_item_suffixes(ctx):
    return read_rows(ctx.elf, A["item_suffix"], 0x14, [
        ("text_key", 0x00, "str"), ("level", 0x04, "s16"), ("mods_weapon", 0x08, "str"),
        ("mods_armor", 0x0C, "str"), ("mods_other", 0x10, "str")], stop=null_ptr)


def t_item_models(ctx):
    return read_rows(ctx.elf, A["item_model"], 0x10, [
        ("model_file", 0x00, "str"), ("texture_file", 0x04, "str")], stop=null_ptr)


def t_loot_quality(ctx):
    rows = read_rows(ctx.elf, A["loot_quality"], 12, [
        ("chance_poor", 0, "f32"), ("chance_normal", 4, "f32"), ("chance_good", 8, "f32")], count=12)
    for r in rows:
        r["note"] = "" if r["index"] < 10 else "padding row (the row argument is clamped to 0..9)"
    return rows


def t_weapon_value_mult(ctx):
    return [{"weapon_subtype": i, "value_multiplier": fnum(ctx.elf.f32(A["weapon_value_mult"] + 4 * i))}
            for i in range(7)]


def ptr_list(e, base, n=None):
    out, i = [], 0
    while n is None or i < n:
        p = e.u32(base + 4 * i)
        if n is None and p == 0:
            break
        out.append(e.cstr(p) if p else "")
        i += 1
    return out


def t_body_codes(ctx):
    return [{"model_index": i, "code": s} for i, s in enumerate(ptr_list(ctx.elf, A["body_codes"], 12))]


def t_potion_names(ctx):
    rows = []
    for kind, base in (("mana", A["potions_mana"]), ("healing", A["potions_heal"])):
        for i, s in enumerate(ptr_list(ctx.elf, base)):
            rows.append({"kind": kind, "rank_from_largest": i, "item_name": s})
    return rows


def t_class_stats(ctx):
    return read_rows(ctx.elf, A["class_stats"], 0x10, [
        ("strength", 0, "s32"), ("intelligence", 4, "s32"), ("dexterity", 8, "s32"),
        ("stamina", 12, "s32")], count=NUM_CLASSES)


def t_exp_table(ctx):
    e = ctx.elf
    rows = []
    for lvl in range(EXP_ENTRIES):
        v = e.s32(A["exp_table"] + 4 * lvl)
        rows.append({"level": lvl, "exp_to_leave_level": v,
                     "note": "cap sentinel: experience is clamped to this minus 1" if lvl == EXP_ENTRIES - 1 else ""})
    return rows


def t_class_passives(ctx):
    e = ctx.elf
    rows = []
    for cls in range(NUM_CLASSES):
        got = read_rows(e, CLASS_PASSIVES[cls], 0x38, [
            ("name", 0x00, "char32"), ("byte20", 0x20, "u8"), ("max_rank", 0x21, "u8"),
            ("point_cost", 0x22, "u8"), ("float24", 0x24, "f32"), ("mask", 0x28, "x64")],
            stop=lambda e_, a: e_.bytes(a, 4) in (b"END\0", b"\0\0\0\0"))
        for r in got:
            r["class"] = cls
        rows += got
    return rows


def t_skill_trees(ctx):
    e = ctx.elf
    pics = ptr_list(e, A["skill_tree_pictures"], NUM_CLASSES)
    rows = []
    for cls in range(NUM_CLASSES):
        got = read_rows(e, SKILL_TREES[cls], 0x28, [
            ("kind", 0x00, "u8"), ("base_level_required", 0x01, "s8"), ("id_or_mask", 0x08, "s64"),
            ("prereq_kind", 0x10, "s32"), ("prereq", 0x18, "s64"), ("x", 0x20, "s32"), ("y", 0x24, "s32")],
            stop=lambda e_, a: e_.s32(a + 0x20) == -1)
        for r in got:
            r["class"] = cls
            r["tree_picture"] = pics[cls]
            r["kind"] = "skill" if r["kind"] else "passive"
            if r["kind"] == "passive":
                r["id_or_mask"] = "0x%x" % r["id_or_mask"]
            pk = "skill" if r["prereq_kind"] else "passive"
            if r["prereq"] == -1:
                r["prereq_kind"], r["prereq"] = "none", ""
            elif r["prereq"] == 0:
                r["prereq_kind"], r["prereq"] = "either_weapon_skill", ""
            else:
                r["prereq_kind"] = pk
                if pk == "passive":
                    r["prereq"] = "0x%x" % r["prereq"]
        rows += got
    return rows


def t_legacy_abilities(ctx):
    return read_rows(ctx.elf, A["legacy_abilities"], 0x68, [
        ("name", 0x00, "char32"), ("skill_id", 0x20, "s16"), ("cooldown_frames", 0x22, "s16"),
        ("from_neutral", 0x24, "u8"), ("kind", 0x25, "u8"), ("word26", 0x26, "s16"),
        ("strength", 0x28, "s16"), ("mana_cost", 0x2C, "f32"), ("fade_rate", 0x40, "f32"),
        ("mask", 0x48, "x64")],
        stop=lambda e_, a: e_.bytes(a, 4) in (b"END\0", b"\0\0\0\0"))


LEVEL_FIELDS = [
    ("name", 0x00, "str"), ("monster_level", 0x04, "s8"), ("byte05", 0x05, "s8"),
    ("kill_plane_z", 0x08, "f32"), ("float0c", 0x0C, "f32"), ("float10", 0x10, "f32"),
    ("pool_count", 0x14, "s32"), ("byte18", 0x18, "s8"), ("float1c", 0x1C, "f32"),
    ("level_flags", 0x20, "x32"), ("sound_24", 0x24, "s16"), ("sound_26", 0x26, "s16"),
    ("sound_28", 0x28, "s16"), ("sound_2a", 0x2A, "s16"), ("s16_2c", 0x2C, "s16"),
]


def t_levels(ctx):
    e = ctx.elf
    rows = read_rows(e, A["level_table"], 0x30, LEVEL_FIELDS, stop=null_ptr)
    d = read_rows(e, A["level_table"] + len(rows) * 0x30, 0x30, LEVEL_FIELDS, count=1)[0]
    d["index"] = len(rows)
    d["name"] = "(default row, used when no name matches)"
    rows.append(d)
    for r in rows:
        r["level_scale_normal"] = r["monster_level"] + 2
    return rows


def t_missions(ctx):
    e = ctx.elf
    fields = [("name_key", 0x00, "str"), ("alt_name_key", 0x04, "str"), ("story_level", 0x08, "str"),
              ("alt_story_level", 0x0C, "str"), ("medal_level", 0x10, "str"), ("bonus_level", 0x14, "str"),
              ("picture", 0x18, "str"), ("alt_picture", 0x1C, "str"), ("flag20", 0x20, "s32"),
              ("has_medals", 0x24, "s32"), ("has_bonus", 0x28, "s32"), ("map_x", 0x2C, "s32"),
              ("map_y", 0x30, "s32")]
    keys = ptr_list(e, A["mission_text_keys"], 13)
    rows = read_rows(e, A["mission_table"], 0x34, fields, count=13)
    for r in rows:
        r["mission_number"] = r["index"] + 1      # mission 0 has no row
        r["menu_text_key"] = keys[r["index"]]
    return rows


# ---------------------------------------------------------------------------------------
# Disc files
# ---------------------------------------------------------------------------------------
def lmp_entries(d):
    n, = struct.unpack_from("<I", d, 0)
    out = []
    if n > 100000 or 4 + n * 12 > len(d):
        return out
    for i in range(n):
        no, do, ds = struct.unpack_from("<III", d, 4 + i * 12)
        if no >= len(d) or do + ds > len(d):
            return []
        name = d[no:d.index(b"\0", no)].decode("latin1")
        out.append((name, do, ds))
    return out


def gob_entries(d):
    out, i = [], 0
    while i + 40 <= len(d) and d[i] != 0:
        name = d[i:i + 32].split(b"\0")[0].decode("latin1")
        off, size = struct.unpack_from("<II", d, i + 32)
        out.append((name, off, size))
        i += 40
    return out


def find_in_lump(d, wanted):
    for name, off, size in lmp_entries(d):
        if name.lower() == wanted:
            return d[off:off + size]
    return None


def iso_files(m):
    """(path, offset, size) for every file of an ISO9660 volume."""
    pvd = 16 * 2048
    if m[pvd + 1:pvd + 6] != b"CD001":
        raise SystemExit("not an ISO9660 image")
    root = m[pvd + 156:pvd + 190]
    stack = [("", struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0])]
    while stack:
        path, lba, size = stack.pop()
        data = m[lba * 2048:lba * 2048 + size]
        i = 0
        while i < len(data):
            n = data[i]
            if n == 0:
                i = (i // 2048 + 1) * 2048
                continue
            rec = data[i:i + n]
            e_lba, e_size = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
            flags, nlen = rec[25], rec[32]
            name = rec[33:33 + nlen]
            i += n
            if name in (b"\x00", b"\x01"):
                continue
            full = "%s/%s" % (path, name.decode("latin1").split(";")[0])
            if flags & 2:
                stack.append((full, e_lba, e_size))
            else:
                yield full, e_lba * 2048, e_size


def balance_hash(name):
    """The 16-bit hash the game applies to a creature type name (lower-cased first)."""
    h = 0
    for ch in name.encode("latin1"):
        c = ch - 256 if ch > 127 else ch
        if 65 <= ch <= 90:
            c += 0x20
        h = ((h + c) & 0xFFFF) * 0x401 & 0xFFFF
        h ^= h >> 6
    h = h * 9 & 0xFFFF
    return ((h >> 11) ^ h) * 0x8001 & 0xFFFF


def text_hash(key):
    """Slot (0..8191) at which the game first looks for a text key."""
    h = 0
    for ch in key.encode("latin1"):
        c = ch - 256 if ch > 127 else ch
        h = ((h + c) * 0x401) & 0xFFFFFFFF
        s = h - (1 << 32) if h & 0x80000000 else h
        h = (h ^ (s >> 6)) & 0xFFFFFFFF
    h = (h * 9) & 0xFFFFFFFF
    s = h - (1 << 32) if h & 0x80000000 else h
    return (h ^ (s >> 11)) & 0x1FFF


def parse_uni(blob):
    rows, p = [], 0
    while p < len(blob) and blob[p] != 0:
        e = blob.index(b"\0", p)
        key = blob[p:e].decode("latin1")
        q = (p + len(key) + 2) & ~1
        v0 = q
        while q + 1 < len(blob) and blob[q:q + 2] != b"\0\0":
            q += 2
        rows.append({"index": len(rows), "offset": p, "key": key, "hash_slot": text_hash(key),
                     "text": blob[v0:q].decode("utf-16-le", "replace")})
        p = q + 2
    return rows


def parse_objects(blob, source):
    count, flags, strtab = struct.unpack_from("<hHi", blob, 0)

    def s(off):
        o = strtab + off
        return blob[o:blob.index(b"\0", o)].decode("latin1")

    rows, p = [], 8
    for i in range(count):
        cls, size, angle = struct.unpack_from("<ihH", blob, p)
        x, y, z = struct.unpack_from("<3f", blob, p + 8)
        props, q = [], p + 20
        while q < p + size:
            po, = struct.unpack_from("<i", blob, q)
            if po == 0:
                break
            props.append(s(po))
            q += 4
        rows.append({"source": source, "index": i, "class": s(cls), "x": fnum(x), "y": fnum(y),
                     "height": fnum(z), "angle": angle, "properties": ";".join(props)})
        p += size
    return rows


def objects_from_file(path_label, d):
    """Accepts objects.ob, a level lump, or a GOB of lumps."""
    out = []
    upper = path_label.upper()
    if upper.endswith(".GOB"):
        for lname, off, size in gob_entries(d):
            ob = find_in_lump(d[off:off + size], "objects.ob")
            if ob:
                out += parse_objects(ob, "%s:%s" % (os.path.basename(path_label), lname))
        return out
    ob = find_in_lump(d, "objects.ob") if upper.endswith(".LMP") else None
    return parse_objects(ob if ob else d, os.path.basename(path_label))


# ---------------------------------------------------------------------------------------
# Constants that live in code: a straight-line reader of MIPS instructions
# ---------------------------------------------------------------------------------------
M64 = (1 << 64) - 1
CALL_CLOBBERED = list(range(1, 16)) + [24, 25, 31]


def sx16(v): return v - 0x10000 if v & 0x8000 else v
def sgn(v): return v - (1 << 64) if v >> 63 else v
def sx32(v): return (v | ~0xFFFFFFFF) & M64 if v & 0x80000000 else v & 0xFFFFFFFF


class Scan:
    """A small reader of MIPS code that tracks constants. Registers hold a known integer,
    ('fld', offset, ormask) for "the object's own field with bits or-ed in", or are
    absent (unknown). Calls are not entered; they only forget the caller-saved registers.
    See run() for how branches are treated."""

    def __init__(self, e, on_call=None, on_store=None, on_load=None):
        self.e, self.on_call, self.on_store, self.on_load = e, on_call, on_store, on_load
        self.r, self.f = {}, {}

    def get(self, n):
        return 0 if n == 0 else self.r.get(n)

    def put(self, n, v):
        if n == 0:
            return
        if v is None:
            self.r.pop(n, None)
        else:
            self.r[n] = v & M64 if isinstance(v, int) else v

    def addr(self, base, simm):
        b = self.get(base)
        return (b + simm) & 0xFFFFFFFF if isinstance(b, int) else None

    def step(self, pc, w):
        e = self.e
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        sa, fn, imm = (w >> 6) & 31, w & 63, w & 0xFFFF
        simm = sx16(imm)
        if op == 0:
            a, b = self.get(rs), self.get(rt)
            v = None
            if fn in (0x21, 0x2D, 0x25):                       # addu daddu or
                if rt == 0: v = a
                elif rs == 0: v = b
                elif isinstance(a, int) and isinstance(b, int):
                    v = (a | b) if fn == 0x25 else (a + b)
                    if fn == 0x21: v = sx32(v & 0xFFFFFFFF)
                elif fn == 0x25:
                    for x, y in ((a, b), (b, a)):
                        if isinstance(x, tuple) and isinstance(y, int):
                            v = ("fld", x[1], x[2] | y)
            elif fn in (0x24, 0x26, 0x23, 0x2F, 0x2A, 0x2B) and isinstance(a, int) and isinstance(b, int):
                if fn == 0x24: v = a & b                         # and xor subu dsubu slt sltu
                elif fn == 0x26: v = a ^ b
                elif fn == 0x23: v = sx32((a - b) & 0xFFFFFFFF)
                elif fn == 0x2F: v = (a - b) & M64
                elif fn == 0x2A: v = int(sgn(a) < sgn(b))
                else: v = int(a < b)
            elif fn == 0x00 and isinstance(b, int): v = sx32((b << sa) & 0xFFFFFFFF)
            elif fn == 0x02 and isinstance(b, int): v = sx32((b & 0xFFFFFFFF) >> sa)
            elif fn == 0x03 and isinstance(b, int): v = sx32((sgn(sx32(b & 0xFFFFFFFF)) >> sa) & 0xFFFFFFFF)
            elif fn == 0x38 and isinstance(b, int): v = b << sa
            elif fn == 0x3C and isinstance(b, int): v = b << (sa + 32)
            if fn in (0x08, 0x09, 0x18, 0x19, 0x1A, 0x1B, 0x0C, 0x0D):
                return                                           # jr jalr mult div syscall
            self.put(rd, v)
        elif op == 0x0F: self.put(rt, sx32(imm << 16))
        elif op == 0x0D:
            a = self.get(rs)
            if isinstance(a, int): self.put(rt, a | imm)
            elif isinstance(a, tuple): self.put(rt, ("fld", a[1], a[2] | imm))
            else: self.put(rt, None)
        elif op in (0x08, 0x09, 0x18, 0x19):
            a = self.get(rs)
            if isinstance(a, int):
                v = a + simm
                self.put(rt, sx32(v & 0xFFFFFFFF) if op in (8, 9) else v)
            else: self.put(rt, None)
        elif op in (0x0A, 0x0B, 0x0C, 0x0E):                     # slti sltiu andi xori
            a = self.get(rs)
            if not isinstance(a, int): self.put(rt, None)
            elif op == 0x0A: self.put(rt, int(sgn(a) < simm))
            elif op == 0x0B: self.put(rt, int(a < (simm & M64)))
            elif op == 0x0C: self.put(rt, a & imm)
            else: self.put(rt, a ^ imm)
        elif op in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37, 0x1A, 0x1B, 0x1E):
            a = self.addr(rs, simm)
            v = None
            if a is not None and THIS <= a < THIS + 0x10000 and op in (0x23, 0x37):
                v = ("fld", a - THIS, 0)
            elif a is not None and self.on_load and op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x37):
                v = self.on_load(a)
                if isinstance(v, int):
                    if op == 0x20: v = v & 0xFF; v = (v | ~0xFF) & M64 if v & 0x80 else v
                    elif op == 0x24: v &= 0xFF
                    elif op == 0x21: v = v & 0xFFFF; v = (v | ~0xFFFF) & M64 if v & 0x8000 else v
                    elif op == 0x25: v &= 0xFFFF
                    elif op == 0x23: v = sx32(v & 0xFFFFFFFF)
                    elif op == 0x27: v &= 0xFFFFFFFF
            self.put(rt, v)
        elif op == 0x31:                                         # lwc1
            a = self.addr(rs, simm)
            if a is not None and e.has(a, 4): self.f[rt] = e.u32(a)
            else: self.f.pop(rt, None)
        elif op == 0x35: self.f.pop(rt, None)
        elif op in (0x28, 0x29, 0x2B, 0x3F, 0x39):               # sb sh sw sd swc1
            a = self.addr(rs, simm)
            if a is not None and self.on_store:
                width = {0x28: 1, 0x29: 2, 0x2B: 4, 0x3F: 8, 0x39: 4}[op]
                v = self.f.get(rt) if op == 0x39 else self.get(rt)
                self.on_store(pc, a, width, v, op == 0x39)
        elif op == 0x11:
            if rs == 4:                                          # mtc1
                v = self.get(rt)
                if isinstance(v, int): self.f[rd] = v & 0xFFFFFFFF
                else: self.f.pop(rd, None)
            elif rs in (0, 1, 2): self.put(rt, None)
            elif rs in (0x10, 0x14) and fn < 0x30:
                if fn == 6 and rd in self.f: self.f[sa] = self.f[rd]   # mov.s fd <- fs
                else: self.f.pop(sa, None)
        elif op == 0x1C: self.put(rd, None)
        elif op == 0x10 and rs == 0: self.put(rt, None)

    def branch_cond(self, w):
        """True / False when the operands of a conditional branch are known, else None."""
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        a, b = self.get(rs), self.get(rt)
        if not isinstance(a, int):
            return None
        sa_ = sgn(a)
        if op in (4, 0x14, 5, 0x15):
            if not isinstance(b, int):
                return None
            return (a == b) == (op in (4, 0x14))
        if op in (6, 0x16): return sa_ <= 0
        if op in (7, 0x17): return sa_ > 0
        if op == 1 and rt in (0, 2): return sa_ < 0
        if op == 1 and rt in (1, 3): return sa_ >= 0
        return None

    def run(self, start, end, regs=None, follow=False, limit=200000):
        """follow=False: every instruction once, in address order. follow=True: branches
        whose operands are known are taken or not as the processor would; the others fall
        through, and the walk stops at the function's return."""
        e = self.e
        self.r, self.f = dict(regs or {}), {}
        ws = e.words(start, end)
        i = steps = 0
        while 0 <= i < len(ws) and steps < limit:
            steps += 1
            pc, w = start + i * 4, ws[i]
            op, fn, rt = w >> 26, w & 63, (w >> 16) & 31
            is_jal = op == 3 or (op == 0 and fn == 9)
            is_ret = op == 0 and fn == 8
            is_cond = op in (1, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17) or (op == 0x11 and ((w >> 21) & 31) == 8)
            if not (is_jal or is_ret or is_cond or op == 2):
                self.step(pc, w)
                i += 1
                continue
            slot = ws[i + 1] if i + 1 < len(ws) else 0
            if is_jal:
                self.step(pc + 4, slot)
                tgt = ((pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2)) if op == 3 else None
                if self.on_call:
                    self.on_call(pc, tgt, self)
                for n in CALL_CLOBBERED:
                    self.r.pop(n, None)
                for n in range(20):
                    self.f.pop(n, None)
                i += 2
                continue
            if follow and (is_ret or op == 2):
                self.step(pc + 4, slot)
                tgt = (pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                if is_ret or not (start <= tgt < end):
                    break
                i = (tgt - start) // 4
                continue
            cond = self.branch_cond(w) if (follow and is_cond and op != 0x11) else None
            likely = op in (0x14, 0x15, 0x16, 0x17) or (op == 1 and rt in (2, 3))
            if cond is None:
                self.step(pc + 4, slot)
                i += 2
                continue
            if cond or not likely:
                self.step(pc + 4, slot)
            if cond:
                tgt = branch_target(pc, w)
                if not (start <= tgt < end):
                    break
                i = (tgt - start) // 4
            else:
                i += 2


def call_sites(e, target):
    ta, _o, tsz = e.text
    want = 0x0C000000 | ((target >> 2) & 0x03FFFFFF)
    return [ta + i * 4 for i, w in enumerate(e.words(ta, ta + tsz)) if w == want]


def branch_target(pc, w):
    return (pc + 4 + (sx16(w & 0xFFFF) << 2)) & 0xFFFFFFFF


def ffmt(bits):
    return "" if bits is None else fnum(f32_from_bits(bits))


def t_item_tokens(ctx):
    """Format strings the descriptor parser hands to its scanner, with the modifier code
    it stores when the format matches."""
    e = ctx.elf
    start, end = e.func_range(A["fn_item_parse"])
    hits = []

    def on_call(pc, tgt, s):
        fmt = e.cstr(s.get(5) & 0xFFFFFFFF) if isinstance(s.get(5), int) else None
        if fmt and "%d" in fmt:
            hits.append((pc, fmt))

    Scan(e, on_call=on_call).run(start, end)
    rows = []
    for pc, fmt in hits:
        code = ""
        ws = e.words(pc + 8, pc + 8 + 6 * 4)
        for w in ws:                                             # li $t2..$t5, code
            if (w & 0xFFE00000) == 0x24000000 and 10 <= ((w >> 16) & 31) <= 13 and (w & 0xFFFF) < 0x80:
                code = "0x%02x" % (w & 0xFFFF)
                break
            if w >> 26 == 0 and (w & 0x7FF) in (0x21, 0x25, 0x2D) and ((w >> 21) & 0x3FF) == 0 \
                    and 10 <= ((w >> 11) & 31) <= 13:            # move $t2..$t5, $zero
                code = "0x00"
                break
        token = fmt.split("%")[0]
        rows.append({"order": len(rows), "token": token, "format": fmt,
                     "values": fmt.count("%d"),
                     "modifier_code": code if token != "mesh" else "(sets the visual variant)",
                     "call_site": "0x%x" % pc})
    return rows


def t_boss_names(ctx):
    e = ctx.elf
    start, end = e.func_range(A["fn_boss_rank"])
    rows = []

    def on_call(pc, tgt, s):
        v = s.get(5)
        name = e.cstr(v & 0xFFFFFFFF) if isinstance(v, int) else None
        if name and tgt == A["fn_strcasecmp"]:
            rows.append({"order": len(rows), "string": name, "call_site": "0x%x" % pc})

    Scan(e, on_call=on_call).run(start, end)
    return rows


def t_fixed_descriptors(ctx):
    """Item descriptors written into code: every reference, inside a function that calls
    the descriptor parser, to a string whose first word is an item definition name."""
    e = ctx.elf
    known = {r["name"] for r in t_item_defs(ctx)} | {r["descriptor"] for r in t_item_presets(ctx)}
    funcs = sorted({e.func_range(cs) for cs in call_sites(e, A["fn_item_parse"])})
    rows = []
    for start, end in funcs:
        calls = sum(1 for w in e.words(start, end) if w == (0x0C000000 | (A["fn_item_parse"] >> 2)))
        hi = {}
        found = 0
        for i, w in enumerate(e.words(start, end)):
            op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
            if op == 0x0F:
                hi[rt] = (w & 0xFFFF) << 16
            elif op == 9 and rs in hi:
                text = e.cstr((hi[rs] + sx16(w & 0xFFFF)) & 0xFFFFFFFF)
                if text and (text in known or text.split("+")[0] in known):
                    found += 1
                    rows.append({"function": "0x%x" % start, "reference": "0x%x" % (start + i * 4),
                                 "descriptor": text, "parser_calls_in_function": calls,
                                 "starting_gear": int(start == A["fn_start_items"])})
        if not found:
            rows.append({"function": "0x%x" % start, "reference": "",
                         "descriptor": "(text built at run time or passed in)",
                         "parser_calls_in_function": calls,
                         "starting_gear": int(start == A["fn_start_items"])})
    return rows


def t_loot_calls(ctx):
    """Arguments each creature class passes to the death-drop function."""
    e = ctx.elf
    names = ("z_offset", "throw_speed", "gold_scale", "gold_chance", "quality_row", "item_chance")
    rows = []
    for cs in call_sites(e, A["fn_creature_droploot"]):
        start, end = e.func_range(cs)

        def on_call(pc, tgt, s, start=start):
            if tgt != A["fn_creature_droploot"]:
                return
            row = {"function": "0x%x" % start, "call_site": "0x%x" % pc}
            for i, n in enumerate(names):
                row[n] = ffmt(s.f.get(12 + i))
            rows.append(row)
        Scan(e, on_call=on_call).run(start, end)
    return rows


def class_def(e, addr):
    """Class definition block: lump name, generation word, then {name, pointer} pairs."""
    if not e.has(addr, 8):
        return "", []
    lump = e.cstr(e.u32(addr)) or ""
    res, a = [], addr + 8
    while e.has(a, 8) and len(res) < 200:
        s = e.cstr(e.u32(a))
        if not s or "." not in s:
            break
        res.append(s)
        a += 8
    return lump, res


CREATURE_FIELDS = {0x1C: ("radius", "f"), 0x20: ("height", "f"), 0x5C: ("resist_fire", "f"),
                   0x60: ("resist_cold", "f"), 0x64: ("resist_poison", "f"),
                   0x68: ("resist_disease", "f"), 0x6C: ("resist_lightning", "f"),
                   0xB0: ("turn_rate", "f"), 0xB4: ("kind", "i"), 0xB8: ("move_speed", "f"),
                   0xE0: ("visual_offset", "f"), 0x48: ("vtable", "x")}


def creature_ctor_info(e, start, end):
    info = {"ctor": "0x%x" % start, "base_hp_argument": "", "class_def": "", "lump": "",
            "model": "", "cflags_or": 0}
    seen = {}

    def on_call(pc, tgt, s):
        if tgt == A["fn_creature_ctor"]:
            info["base_hp_argument"] = ffmt(s.f.get(12))
            cd = s.get(8)
            if isinstance(cd, int) and e.has(cd & 0xFFFFFFFF, 8):
                info["class_def"] = "0x%x" % (cd & 0xFFFFFFFF)
                lump, res = class_def(e, cd & 0xFFFFFFFF)
                info["lump"], info["model"] = lump, (res[0] if res else "")
                info["resources"] = len(res)

    def on_store(pc, a, width, v, is_float):
        if not (THIS <= a < THIS + 0x10000):
            return
        off = a - THIS
        if isinstance(v, tuple):
            if v[1] == off == 0xA8:
                info["cflags_or"] |= v[2]
            return
        if v is None:
            return
        if off in CREATURE_FIELDS:
            name, kind = CREATURE_FIELDS[off]
            if kind == "f" and is_float: val = ffmt(v)
            elif kind == "f": val = ffmt(v & 0xFFFFFFFF)
            elif kind == "x": val = "0x%x" % (v & 0xFFFFFFFF)
            else: val = str(sx16(v & 0xFFFF) if width == 2 else v & (0xFF if width == 1 else 0xFFFFFFFF))
            seen.setdefault(name, [])
            if val not in seen[name]:
                seen[name].append(val)

    Scan(e, on_call=on_call, on_store=on_store).run(start, end, {4: THIS})
    for off, (name, _k) in sorted(CREATURE_FIELDS.items()):
        info[name] = "|".join(seen.get(name, []))
    info["cflags_or"] = "0x%x" % info["cflags_or"]
    return info


def t_object_factory(ctx):
    """Type name -> allocation size and constructor, from the tests in the object factory.
    Names are grouped by the block of code their test leads to."""
    e = ctx.elf
    start, end = e.func_range(A["fn_object_factory"])
    ws = e.words(start, end)
    tests = []                                                   # (pc, kind, name)
    jal = {0x0C000000 | (A[k] >> 2): kind for k, kind in
           (("fn_strcasecmp", "equals"), ("fn_str_prefix", "prefix"))}
    for i, w in enumerate(ws):
        if w not in jal:
            continue
        # the name is $a1 = lui hi (often set in an earlier delay slot) + addiu lo next to the call
        lo = hi = None
        base = 5
        for k in (i + 1, i - 1, i - 2, i - 3):
            if 0 <= k < len(ws) and ws[k] >> 26 == 9 and ((ws[k] >> 16) & 31) == 5:   # addiu $a1, $r, lo
                lo, base = sx16(ws[k] & 0xFFFF), (ws[k] >> 21) & 31
                break
        for k in range(i, max(i - 400, -1), -1):
            if ws[k] >> 26 == 0x0F and ((ws[k] >> 16) & 31) == base:         # lui $r, hi
                hi = ws[k] & 0xFFFF
                break
        if lo is None or hi is None:
            continue
        name = e.cstr(((hi << 16) + lo) & 0xFFFFFFFF)
        if name:
            tests.append((start + i * 4, jal[w], name))
    groups, order = {}, []
    for pc, kind, name in tests:
        i = (pc - start) // 4 + 2
        target = None
        for j in range(i, min(i + 3, len(ws))):                  # the branch on the result
            w = ws[j]
            op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
            here = start + j * 4
            if op in (4, 0x14) and rs == 2 and rt == 0:         # beqz/beqzl v0 -> matched there
                target = branch_target(here, w)
                break
            if op in (5, 0x15) and rs == 2 and rt == 0:         # bnez/bnezl v0 -> matched below
                target = here + 8
                break
        if target is None:
            continue
        if target not in groups:
            groups[target] = []
            order.append(target)
        groups[target].append((kind, name))
    test_pcs = {t[0] for t in tests}
    rows = []
    for target in order:
        size, ctor, note = "", "", ""
        j = (target - start) // 4
        seen_new = False
        hops = 0
        while 0 <= j < len(ws):
            w, here = ws[j], start + j * 4
            op = w >> 26
            if here in test_pcs:
                note = "another name test follows; see the rows for block 0x%x onward" % here
                break
            if op == 4 and ((w >> 21) & 31) == ((w >> 16) & 31) and hops < 4 and seen_new:
                hops += 1                                        # shared tail: follow the jump
                j = (branch_target(here, w) - start) // 4
                continue
            if op == 3:
                tgt = (here & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                if tgt == A["fn_pool_new"]:
                    seen_new = True
                    for k in (j + 1, j - 1, j - 2):              # li $a0, size (delay slot or just before)
                        if 0 <= k < len(ws) and (ws[k] & 0xFFFF0000) in (0x24040000, 0x34040000):
                            size = "0x%x" % (ws[k] & 0xFFFF)
                            break
                elif seen_new:
                    ctor = "0x%x" % tgt
                    break
                elif not ctor:
                    ctor, note = "0x%x" % tgt, "no allocation: calls this function"
                    break
            if op == 2 or (op == 4 and (w >> 16) & 0x3FF == 0) or w == 0x03E00008:
                if not seen_new:
                    note = note or "no allocation in this block"
                    break
            j += 1
        for kind, name in groups[target]:
            rows.append({"type_name": name, "match": kind, "alloc_size": size, "constructor": ctor,
                         "block": "0x%x" % target, "note": note})
    return rows


def t_creature_classes(ctx):
    """One row per function that calls the creature base constructor."""
    e = ctx.elf
    factory = {}
    for r in t_object_factory(ctx):
        if r["constructor"]:
            factory.setdefault(r["constructor"], []).append(
                r["type_name"] + ("*" if r["match"] == "prefix" else ""))
    rows, done = [], set()
    for cs in call_sites(e, A["fn_creature_ctor"]):
        start, end = e.func_range(cs)
        if start in done:
            continue
        done.add(start)
        info = creature_ctor_info(e, start, end)
        info["factory_type_names"] = " ".join(factory.get(info["ctor"], []))
        rows.append(info)
    return rows


SKILL_ARRAYS = (("t1_first_level", 0x0E, 2), ("t1_base", 0x18, 2), ("t1_step", 0x24, 4),
                ("t2_first_level", 0x38, 2), ("t2_base", 0x42, 2), ("t2_step", 0x4C, 4))


def t_skills(ctx):
    """Skill id table, plus what each skill's constructor and statistics function store."""
    e = ctx.elf
    objs = {}
    for sid in range(NUM_SKILL_IDS):
        p = e.u32(A["skill_table"] + 4 * sid)
        if p:
            objs[sid] = p
    if not objs:
        return []
    lo, hi = min(objs.values()), max(objs.values()) + 0x200
    mem, ctor_of = {}, {}

    def store_into(target):
        def on_store(pc, a, width, v, is_float):
            if lo <= a < hi and isinstance(v, int):
                target.setdefault(a, []).append(v)
        return on_store

    def on_call(pc, tgt, s):
        a0 = s.get(4)
        if tgt and isinstance(a0, int) and lo <= (a0 & 0xFFFFFFFF) < hi:
            a1 = s.get(5)
            ctor_of[a0 & 0xFFFFFFFF] = (tgt, a1 if isinstance(a1, int) else None)

    def load(a):
        vals = mem.get(a)
        return vals[-1] if vals else None

    start, end = e.func_range(A["fn_skill_static_init"])
    # the compiler-made initialiser is called once with (1, 0xffff) to construct
    Scan(e, on_call=on_call, on_store=store_into(mem)).run(start, end, {4: 1, 5: 0xFFFF}, follow=True)
    for obj, (ctor, a1) in sorted(ctor_of.items()):
        cs, ce = e.func_range(ctor)
        regs = {4: obj}
        if a1 is not None:
            regs[5] = a1
        Scan(e, on_store=store_into(mem), on_load=load).run(cs, ce, regs, follow=True)

    def last(addr, nonzero=False):
        vals = [v for v in mem.get(addr, []) if v or not nonzero]
        return vals[-1] if vals else None

    rows = []
    for sid, obj in sorted(objs.items()):
        row = {"id": sid, "object": "0x%x" % obj}
        ctor = ctor_of.get(obj)
        row["constructor"] = "0x%x" % ctor[0] if ctor else "(built inline by the static initialiser)"
        v = last(obj, nonzero=True)
        row["name"] = (e.cstr(v & 0xFFFFFFFF) or "") if v else ""
        v = last(obj + 4); row["flags"] = "" if v is None else "0x%x" % (v & 0xFFFFFFFF)
        v = last(obj + 8); row["kind"] = "" if v is None else v & 0xFFFFFFFF
        v = last(obj + 0xC); row["recast_frames"] = "" if v is None else sx16(v & 0xFFFF)
        vt = last(obj + 0x60, nonzero=True)
        row["vtable"] = "" if vt is None else "0x%x" % (vt & 0xFFFFFFFF)
        for col in ("can_use_fn", "cast_fn", "mana_cost_fn", "init_stats_fn"):
            row[col] = ""
        for name, _off, _w in SKILL_ARRAYS:
            row[name] = ""
        row["stats_ambiguous"] = ""
        if vt is not None and e.has((vt & 0xFFFFFFFF) + 0x50, 4):
            vt &= 0xFFFFFFFF
            for col, slot in (("can_use_fn", 1), ("cast_fn", 2), ("mana_cost_fn", 5), ("init_stats_fn", 9)):
                row[col] = "0x%x" % e.u32(vt + slot * 8 + 4)
            fn = e.u32(vt + 9 * 8 + 4)
            if e.in_text(fn):
                st = {}

                unknown = []

                def on_store(pc, a, width, v, is_float, obj=obj):
                    if obj + 0x0E <= a < obj + 0x60:
                        if isinstance(v, int):
                            st[a - obj] = v
                        else:
                            unknown.append(a - obj)

                fs, fe = e.func_range(fn)
                Scan(e, on_store=on_store, on_load=load).run(fs, fe, {4: obj}, follow=True)
                for name, off, w in SKILL_ARRAYS:
                    cells = []
                    for i in range(5):
                        v = st.get(off + i * w)
                        if v is None: cells.append("")
                        elif w == 4: cells.append(ffmt(v & 0xFFFFFFFF))
                        else: cells.append(str(sx16(v & 0xFFFF)))
                    row[name] = "/".join(cells)
                row["stats_ambiguous"] = int(bool(unknown))
        rows.append(row)
    return rows


def t_class_formulas(ctx):
    """Per-class constants of  max hp = level*hp_per_level + stamina*hp_per_stamina - hp_offset
    and  max mana = (intelligence - mana_int_offset)*mana_per_int + level*mana_per_level.
    They are immediates in the statistics function; the class test chain is walked once
    per class with the class value supplied."""
    e = ctx.elf
    start, end = e.func_range(A["fn_recalc_stats"])
    ws = e.words(start, end)
    first = reg = None
    for i, w in enumerate(ws):                       # lw $r, 0x50($s) followed by float immediates
        if w >> 26 == 0x23 and (w & 0xFFFF) == 0x50 and any(
                x >> 26 == 0x11 and ((x >> 21) & 31) == 4 for x in ws[i + 1:i + 6]):
            first, reg = i, (w >> 16) & 31
            break
    if first is None:
        return []
    join = None
    for j in range(first, len(ws)):                  # the chain's exits all jump to one place
        w = ws[j]
        if w >> 26 == 4 and ((w >> 21) & 31) == ((w >> 16) & 31):
            join = branch_target(start + j * 4, w)
            break
    if join is None:
        return []
    names = {23: "mana_int_offset", 24: "mana_per_int", 25: "mana_per_level",
             22: "hp_per_level", 20: "hp_per_stamina", 21: "hp_offset"}
    rows = []
    for cls in range(NUM_CLASSES):
        sc = Scan(e)
        sc.run(start + (first + 1) * 4, join, {reg: cls}, follow=True)
        row = {"class": cls}
        for r in (22, 20, 21, 23, 24, 25):
            row[names[r]] = ffmt(sc.f.get(r))
        row["code_from"] = "0x%x" % (start + first * 4)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------------------
# Disc-file tables
# ---------------------------------------------------------------------------------------
def name_candidates(ctx):
    """Strings that could be creature type names: identifier-like strings in the data
    sections of the executable, plus class names from any level files given."""
    out = set()
    e = ctx.elf
    for sec in (".rodata", ".data", ".sdata"):
        if sec not in e.sections:
            continue
        _a, o, sz = e.sections[sec]
        cur = bytearray()
        for c in e.d[o:o + sz]:
            if 48 <= c <= 57 or 65 <= c <= 90 or 97 <= c <= 122 or c == 95:
                cur.append(c)
            else:
                if c == 0 and 2 <= len(cur) <= 40 and not 48 <= cur[0] <= 57:
                    out.add(cur.decode("ascii"))
                cur = bytearray()
    return out


def t_monster_balance(ctx):
    """monsters.bal. The file stores only a 16-bit hash of each type name; names are found
    by hashing candidate strings, so a row can have more than one candidate. A candidate
    that the object factory accepts, or that a level file uses, is listed first."""
    d = ctx.need("balance")
    blob = find_in_lump(d, "monsters.bal") or d
    n, = struct.unpack_from("<H", blob, 0)
    if 2 + n * 12 > len(blob):
        raise SystemExit("this does not look like monsters.bal")
    level_names = {r["class"].lower() for r in ctx.object_rows()}
    fact = [(r["type_name"].lower(), r["match"]) for r in t_object_factory(ctx)]

    def factory_accepts(name):
        return any(name == f or (m == "prefix" and name.startswith(f)) for f, m in fact)

    by_hash = {}
    for s in name_candidates(ctx) | level_names:
        by_hash.setdefault(balance_hash(s), set()).add(s.lower())
    rows = []
    for i in range(n):
        h, hp, ac, dmg, att, xp = struct.unpack_from("<H5h", blob, 2 + i * 12)
        cands = sorted(by_hash.get(h, ()), key=lambda c: (not factory_accepts(c), c not in level_names, c))
        good = [c for c in cands if factory_accepts(c) or c in level_names]
        rows.append({"index": i, "name_hash": "0x%04x" % h,
                     "type_name": "|".join(good),
                     "other_strings_with_this_hash": "|".join(c for c in cands if c not in good),
                     "used_in_given_levels": int(any(c in level_names for c in cands)) if level_names else "",
                     "hit_points_pct": hp, "armor_pct": ac, "damage_pct": dmg,
                     "attack_pct": att, "experience_pct": xp})
    return rows


def t_text(ctx):
    d = ctx.need("text")
    blob = find_in_lump(d, "gtext.uni") or d
    return parse_uni(blob)


def t_objects(ctx):
    rows = ctx.object_rows()
    if not rows:
        raise SystemExit("table 'objects' needs --objects FILE... or --iso")
    return rows


# ---------------------------------------------------------------------------------------
TABLES = [
    # name, source, function, description
    ("item_defs", "exe", t_item_defs, "item definitions (base table)"),
    ("item_presets", "exe", t_item_presets, "preset items: a definition whose name is a full descriptor"),
    ("item_prefixes", "exe", t_item_prefixes, "item prefixes and the modifier text they add"),
    ("item_suffixes", "exe", t_item_suffixes, "item suffixes and the modifier text they add"),
    ("item_models", "exe", t_item_models, "model and texture file per model-table row"),
    ("item_tokens", "code", t_item_tokens, "descriptor grammar: modifier tokens, value counts and codes"),
    ("loot_quality", "exe", t_loot_quality, "drop quality rows (poor / normal / good chances)"),
    ("weapon_value_mult", "exe", t_weapon_value_mult, "price multiplier per weapon subtype"),
    ("body_codes", "exe", t_body_codes, "body-type code per player model"),
    ("potion_names", "exe", t_potion_names, "mana and healing potion item names, largest first"),
    ("class_stats", "exe", t_class_stats, "starting statistics per class"),
    ("class_formulas", "code", t_class_formulas, "per-class constants of the max hit point and max mana formulas"),
    ("class_passives", "exe", t_class_passives, "per-class passive list (name, max rank, cost, mask)"),
    ("skill_trees", "exe", t_skill_trees, "per-class skill tree: skill, level needed, prerequisite"),
    ("legacy_abilities", "exe", t_legacy_abilities, "older ability table that passives are built from"),
    ("exp_table", "exe", t_exp_table, "experience needed to leave each level"),
    ("skills", "code", t_skills, "skill id table with constructor and statistics constants"),
    ("levels", "exe", t_levels, "level table (name, monster level, per-level settings)"),
    ("missions", "exe", t_missions, "mission menu table (levels per mission)"),
    ("boss_names", "code", t_boss_names, "type names the boss-rank function compares against"),
    ("object_factory", "code", t_object_factory, "level object type name -> size and constructor"),
    ("creature_classes", "code", t_creature_classes, "constants stored by each creature constructor"),
    ("loot_calls", "code", t_loot_calls, "drop parameters each creature class passes on death"),
    ("fixed_descriptors", "code", t_fixed_descriptors, "item descriptors written into code (starting gear, rewards)"),
    ("monster_balance", "balance", t_monster_balance, "monsters.bal: per-type percentage multipliers"),
    ("text", "text", t_text, "string table (key, text)"),
    ("objects", "objects", t_objects, "level object records with their properties"),
]


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


class Ctx:
    def __init__(self, args):
        self.args = args
        self.iso = None
        self.iso_index = {}
        if args.iso:
            with open(args.iso, "rb") as f:
                self.iso = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for path, off, size in iso_files(self.iso):
                self.iso_index[path.rsplit("/", 1)[1].upper()] = (off, size)
        exe = None
        if args.executable:
            exe = read_file(args.executable)
        elif self.iso is not None:
            for name in self.iso_index:
                if name.startswith(("SLUS_", "SLES_", "SCUS_", "SCES_")):
                    exe = self.iso_file(name)
                    break
        if exe is None:
            raise SystemExit("give the executable, or --iso")
        digest = hashlib.sha256(exe).hexdigest()
        if digest != KNOWN_SHA256:
            msg = "this is not SLUS_209.73 v2.00 (sha256 %s); the addresses will not fit" % digest
            if not args.force:
                raise SystemExit(msg + "\nuse --force to try anyway")
            sys.stderr.write("warning: " + msg + "\n")
        self.elf = Elf(exe)
        self._objects = None

    def iso_file(self, name):
        if self.iso is None or name.upper() not in self.iso_index:
            return None
        off, size = self.iso_index[name.upper()]
        return self.iso[off:off + size]

    def available(self, source):
        if source in ("exe", "code"):
            return True
        if source == "balance":
            return bool(self.args.balance) or self.iso_file("BALANCE.LMP") is not None
        if source == "text":
            return bool(self.args.text) or self.iso_file("GTEXT.LMP") is not None
        if source == "objects":
            return bool(self.args.objects) or self.iso is not None
        return False

    def need(self, source):
        path = getattr(self.args, source)
        if path:
            return read_file(path)
        d = self.iso_file({"balance": "BALANCE.LMP", "text": "GTEXT.LMP"}[source])
        if d is None:
            raise SystemExit("this table needs --%s FILE (or --iso)" % source)
        return d

    def object_rows(self):
        if self._objects is not None:
            return self._objects
        rows = []
        if self.args.objects:
            for path in self.args.objects:
                rows += objects_from_file(path, read_file(path))
        elif self.iso is not None:
            for name in sorted(self.iso_index):
                if name.endswith(".GOB"):
                    try:
                        rows += objects_from_file(name, self.iso_file(name))
                    except (struct.error, ValueError, IndexError):
                        sys.stderr.write("skipped %s (not a level archive)\n" % name)
        self._objects = rows
        return rows


def columns(rows):
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols


def write_table(rows, fmt, stream):
    if fmt == "json":
        json.dump(rows, stream, indent=1, ensure_ascii=False)
        stream.write("\n")
        return
    w = csv.DictWriter(stream, fieldnames=columns(rows), lineterminator="\n", restval="")
    w.writeheader()
    for r in rows:
        w.writerow(r)


def main():
    ap = argparse.ArgumentParser(description="Dump rules tables from your own copy of the game.",
                                 epilog="See docs/data-tables.md for what each table means.")
    ap.add_argument("executable", nargs="?", help="SLUS_209.73")
    ap.add_argument("--iso", help="disc image to read the executable and data files from")
    ap.add_argument("--balance", help="BALANCE.LMP or monsters.bal")
    ap.add_argument("--text", help="GTEXT.LMP or gtext.uni")
    ap.add_argument("--objects", nargs="+", help="level .GOB / level .lmp / objects.ob files")
    ap.add_argument("--table", action="append", default=[], help="table to dump (repeatable)")
    ap.add_argument("--all", action="store_true", help="dump every table the inputs allow")
    ap.add_argument("--list", action="store_true", help="list the tables and exit")
    ap.add_argument("--format", choices=("csv", "json"), default="csv")
    ap.add_argument("--out", help="directory to write one file per table into")
    ap.add_argument("--force", action="store_true", help="accept an executable with a different hash")
    args = ap.parse_args()
    ctx = Ctx(args)
    known = {t[0]: t for t in TABLES}
    if args.list:
        for name, source, fn, desc in TABLES:
            try:
                n = len(fn(ctx)) if ctx.available(source) else None
            except SystemExit:
                n = None
            print("%-18s %-8s %-9s %s" % (name, source, "-" if n is None else "%d rows" % n, desc))
        return
    wanted = [t[0] for t in TABLES if ctx.available(t[1])] if args.all else args.table
    if not wanted:
        ap.error("nothing to do: use --list, --table NAME or --all")
    for name in wanted:
        if name not in known:
            ap.error("unknown table %r (see --list)" % name)
    if len(wanted) > 1 and not args.out:
        ap.error("more than one table: give --out DIR")
    for name in wanted:
        rows = known[name][2](ctx)
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            path = os.path.join(args.out, "%s.%s" % (name, args.format))
            with open(path, "w", encoding="utf-8", newline="") as f:
                write_table(rows, args.format, f)
            sys.stderr.write("%-18s %6d rows -> %s\n" % (name, len(rows), path))
        else:
            out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")
            write_table(rows, args.format, out)
            out.flush()
            out.detach()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:                 # e.g. piped into `head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(1)
