#!/usr/bin/env python3
"""Count what the dialog gaps depend on in the shipped data.  Counts only.

  python3 tools/dialog_gaps_census.py --disc DIR [--elf SLUS_209.73] [--json]

DIR is any directory holding the disc's .GOB archives (searched recursively).  Nothing is
written and no level, object, entry or text name is printed.  With --elf (or a
SLUS_209.73 in local/) the original newlib sscanf and the original object factory run in
tools/ee_emu.py on each record (in emulator memory only); without it the reference model
of tools/ref_dialog_gaps.py is used and the output says so.

What is counted (docs/spec/dialog-gaps.md section 7):
  * the TestLocation records: how many, which dialog properties they carry, and which
    constructor world_objectFactory picks for each (none = the record makes no object);
    script string literals that name the class (a script could create it by name);
  * the level `intro` and the seven arena mode-B levels (names from the executable's
    table at 0x503798): objects with dialogScript, startDialog calls, .dbin files;
  * dlgbox.lmp copies and their box.tex entry;
  * every startDialog call with the swoop flag set: whether an object named like the
    dialog exists in the level and how many dialogOffset fields sscanf converts for it
    for the objects registered under that name ('mixed' when they differ; an absent
    property or fewer than four fields leaves stack slots uninitialised).
"""
import argparse
import collections
import json
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
from gob import gob_entries, lmp_entries   # noqa: E402
from dialog_census import Script            # noqa: E402
import ref_dialog_gaps as R                 # noqa: E402

CLASS = 'TestLocation'
DIALOG_KEYS = ('dialogscript', 'showname', 'shop', 'dialogoffset', 'talkcone', 'key')
ARENA_B_TABLE = 0x503798         # 7 level-file name pointers, then 0 (docs/arena-modes.md)


def raw_records(blob):
    """objects.ob -> [(className, [entry text as stored])] (docs/objects.md)."""
    count, _flags, strings = struct.unpack_from('<hHi', blob, 0)

    def text(off):
        p = strings + off
        return blob[p:blob.index(b'\0', p)].decode('latin1')
    out, p = [], 8
    for _ in range(count):
        cls, size, _angle = struct.unpack_from('<ihh', blob, p)
        q, entries = p + 20, []
        while True:
            v, = struct.unpack_from('<i', blob, q)
            q += 4
            if v == 0:
                break
            entries.append(text(v))
        out.append((text(cls), entries))
        if size <= 0:
            raise ValueError('record size %d' % size)
        p += size
    return out


def reg_name(entries):
    """The name objNames_add registers: props_getStr "name", a leading quote removed and
    the text cut at the next quote (docs/spec/object-system.md 4.5)."""
    v = R.props_get_str(entries, 'name')
    if v is None:
        return None
    if v.startswith('"'):
        v = v[1:].split('"')[0]
    return v


def keyset(entries):
    return {e.partition('=')[0].lower() for e in entries}


def value_of(entries, key):
    """The value of the first entry whose key equals `key` ignoring case (census view)."""
    for e in entries:
        k, sep, v = e.partition('=')
        if sep and k.lower() == key:
            return v
    return None


class Original:
    """sscanf and the factory run in ee_emu (one emulator reused)."""

    def __init__(self, elf):
        from ee_emu import EE
        import difftest_dialog_gaps as D
        self.EE, self.D, self.elf = EE, D, elf
        self.emu = EE(elf)
        self.fmt = 0x53E670

    def fields(self, text):
        emu = self.emu
        s = emu.alloc(len(text) + 8)
        emu.mem.write(s, text.encode('latin1') + b'\0')
        out = emu.alloc(16)
        return emu.call(0x3B7F88, s, self.fmt, out, out + 4, out + 8, out + 12) & 0xFFFFFFFF

    def factory(self, cls, entries):
        ctor, ret = self.D.factory_run(self.elf, cls, entries, emu=self.EE(self.elf))
        if ctor is None:
            return None if ret == 0 else 'returned %#x' % ret
        for k, (a, _s) in R.FALLBACK_CTORS.items():
            if a == ctor:
                return k
        return 'ctor %#x' % ctor


def arena_b_names(elf):
    if elf is None:
        return None
    from ee_emu import EE
    emu = EE(elf)
    names = []
    for i in range(16):
        p = emu.mem.u32(ARENA_B_TABLE + 4 * i)
        if p == 0:
            break
        names.append(emu.mem.cstr(p).lower())
    return names


def start_calls(script, entry):
    """(a, b, name) of every startDialog call reached from `entry` (internal calls and
    callScript of a literal followed, as dialog_census.Script.reach does)."""
    out, seen = [], set()

    def walk(start):
        if start in seen:
            return
        seen.add(start)
        lo, hi = script.body(start)
        for off, builtin, args in script.calls:
            if not lo <= off < hi:
                continue
            if builtin == 'startDialog' and len(args) >= 3:
                out.append((args[1], args[2], script.string(args[0]) if args[0] is not None else None))
            if builtin == 'callScript' and args and args[0] is not None:
                t = script.string(args[0])
                if t in script.entries:
                    walk(script.entries[t])
        for off, target in script.internal:
            if lo <= off < hi:
                walk(target)
    if entry in script.entries:
        walk(script.entries[entry])
    return out


def census(root, elf=None):
    c = collections.Counter()
    tl_keys, tl_ref, tl_orig = collections.Counter(), collections.Counter(), collections.Counter()
    offset_fields = collections.Counter()
    orig = Original(elf) if elf else None
    arena = arena_b_names(elf)
    c['arena_b_names_in_table'] = len(arena) if arena is not None else -1
    gobs = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.upper().endswith('.GOB'):
                gobs.append(os.path.join(dirpath, f))
            if f.lower() == 'dlgbox.lmp':
                c['dlgbox_loose_files'] += 1
                blob = open(os.path.join(dirpath, f), 'rb').read()
                try:
                    ents = {e[0].lower(): (e[1], e[2]) for e in lmp_entries(blob)}
                except (ValueError, IndexError, struct.error):
                    c['dlgbox_refused'] += 1
                    continue
                if 'box.tex' in ents:
                    c['dlgbox_with_box_tex'] += 1
                    o, _s = ents['box.tex']
                    w, h = struct.unpack_from('<HH', blob, o)
                    c['dlgbox_box_tex_560x156'] += (w, h) == (560, 156)
    for path in sorted(gobs):
        data = open(path, 'rb').read()
        for lname, loff, lsize in gob_entries(data):
            if not lname.lower().endswith('.lmp'):
                continue
            base = os.path.basename(lname.lower())[:-4]
            lump = data[loff:loff + lsize]
            try:
                ents = lmp_entries(lump)
            except (ValueError, IndexError, struct.error):
                c['lmp_refused'] += 1
                continue
            names = {e[0].lower(): (e[1], e[2]) for e in ents}
            if base == 'dlgbox':
                c['dlgbox_lumps'] += 1
                c['dlgbox_with_box_tex'] += 'box.tex' in names
            group = 'intro' if base == 'intro' else ('arena_b' if arena and base in arena else None)
            if group:
                c[group + '_lumps'] += 1
                c[group + '_dbin_files'] += sum(1 for n in names if n.endswith('.dbin'))
            script = None
            if 'script.scr' in names:
                o, s = names['script.scr']
                raw = lump[o:o + s]
                c['scripts'] += 1
                c['script_literals_naming_class'] += raw.lower().count(CLASS.lower().encode())
                try:
                    script = Script(raw)
                except (ValueError, IndexError, struct.error):
                    c['scripts_refused'] += 1
                if script is not None and group:
                    c[group + '_startDialog_calls'] += sum(1 for _o, b, _a in script.calls if b == 'startDialog')
            if 'objects.ob' not in names:
                continue
            o, s = names['objects.ob']
            try:
                records = raw_records(lump[o:o + s])
            except (ValueError, IndexError, struct.error):
                c['objects_refused'] += 1
                continue
            by_name = collections.defaultdict(list)
            for cls, entries in records:
                nm = reg_name(entries)
                if nm is not None:
                    by_name[nm.lower()].append(entries)
                ks = keyset(entries)
                if group:
                    c[group + '_objects'] += 1
                    c[group + '_talkers'] += 'dialogscript' in ks
                if cls.lower() == CLASS.lower():
                    c['testlocation_records'] += 1
                    for k in DIALOG_KEYS:
                        tl_keys[k] += k in ks
                    fb = [k for k in ('creaturecontainer', 'autocontainer', 'autochest', 'autoprop',
                                      'autoemitter', 'autodoor', 'autoswitch', 'critter', 'generator',
                                      'smokegen') if k in ks]
                    c['testlocation_with_a_fallback_key'] += bool(fb)
                    c['testlocation_with_uppercase_keys'] += any(
                        e.partition('=')[0] != e.partition('=')[0].lower() for e in entries)
                    tl_ref[R.factory_fallback(entries) or 'no object'] += 1
                    if orig:
                        tl_orig[orig.factory(cls, entries) or 'no object'] += 1
            if script is None:
                continue
            for cls, entries in records:
                ds = value_of(entries, 'dialogscript')
                if ds is None:
                    continue
                for a, b, dname in start_calls(script, ds):
                    if not a:
                        continue
                    c['talker_starts_with_swoop'] += 1
                    c['talker_starts_with_swoop_and_side'] += bool(b)
                    spk = by_name.get(dname.lower(), []) if dname else []
                    c['swoop_starts_with_a_named_object'] += bool(spk)
                    c['swoop_starts_with_several_named_objects'] += len(spk) > 1
                    kinds = set()
                    for e in spk:
                        text = R.props_get_str(e, 'dialogOffset')
                        if text is None:
                            kinds.add('absent')
                        else:
                            kinds.add(str(orig.fields(text) if orig else R.parse_dialog_offset(text)[1]))
                    if kinds:
                        offset_fields[kinds.pop() if len(kinds) == 1 else 'mixed'] += 1
    return dict(source='original sscanf and factory in ee_emu' if orig else 'reference model only',
                totals=dict(sorted(c.items())),
                testlocation_keys=dict(sorted(tl_keys.items())),
                testlocation_factory_reference=dict(sorted(tl_ref.items())),
                testlocation_factory_original=dict(sorted(tl_orig.items())),
                swoop_speaker_dialogoffset_fields=dict(sorted(offset_fields.items())))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--disc', required=True)
    ap.add_argument('--elf')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    elf = a.elf
    if elf is None:
        p = os.path.join(_HERE, '..', 'local', 'SLUS_209.73')
        elf = p if os.path.isfile(p) else None
    out = census(a.disc, elf)
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print('source: %s' % out['source'])
        for k, v in out.items():
            if isinstance(v, dict):
                print('%s:' % k)
                for kk, vv in v.items():
                    print('  %-48s %s' % (kk, vv))
    return 0


if __name__ == '__main__':
    sys.exit(main())
