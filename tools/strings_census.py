#!/usr/bin/env python3
"""Count the string files on a disc and what the HUD text commands ask of them. Counts only.

  python3 tools/strings_census.py --disc DIR

DIR is any directory holding the disc's files (searched recursively for .LMP and .GOB).
Nothing is written.  No key and no text is printed: only totals, histograms, file and
entry names (which the game exposes) and the names of script built-ins.

What is counted (docs/strings.md section 6):
  * every lump entry whose extension is `uni` (text_registerTable 0x173bac takes it) or
    `txt` (only `credits.txt` is read, by 0x223ba0), in top-level .LMP files and in the
    lumps of every .GOB;
  * per `.uni`: entries, distinct keys, repeated keys, keys holding a double quote (no
    lookup can reach them), key and text lengths against the buffers of docs/strings.md,
    '%' conversions by kind, texts that end in a conversion (wstr_format then reads past
    the terminator), the probe lengths of the 13-bit hash table;
  * the level-script calls of setInfo, addHelpMessage, addHelpMessageF, showBust and
    showCompass: call sites, literal arguments, keys missing from the English table (the
    HUD would show "NF:..."), texts longer than the buffer each command copies into.
"""
import argparse
import collections
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
from gob import gob_entries, lmp_entries   # noqa: E402
import ref_strings as R                    # noqa: E402
import scr                                 # noqa: E402

COMMANDS = {                 # built-in -> (indices of text-key arguments, other string args)
    'setInfo': ((0,), ()),
    'addHelpMessage': ((0, 1), ()),
    'addHelpMessageF': ((0, 2), ()),
    'showBust': ((1,), (0,)),
    'showCompass': ((1,), (0,)),
}
LIMIT_OF = {                 # (command, argument index) -> buffer limit in units
    ('setInfo', 0): R.LIMITS['message'],
    ('showBust', 1): R.LIMITS['bust text'],
    ('showCompass', 1): R.LIMITS['compass label'],
    ('addHelpMessageF', 0): R.LIMITS['help F title'],
    ('addHelpMessageF', 2): R.LIMITS['help F body'],
}
CONV_NAMES = {'%': '%%', 'd': '%d', 'c': '%c', 's': '%s', 'u': '%u', 'f': '%f'}


def walk_files(root):
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            yield os.path.join(dirpath, name), name


def lump_blobs(root):
    """(container name, lump name, lump bytes) for every top-level .LMP and every lump of
    every .GOB."""
    for path, name in walk_files(root):
        upper = name.upper()
        if upper.endswith('.LMP'):
            with open(path, 'rb') as source:
                yield name, name, source.read()
        elif upper.endswith('.GOB'):
            with open(path, 'rb') as source:
                data = source.read()
            for lname, off, size in gob_entries(data):
                yield name, lname, data[off:off + size]


def conversions(units):
    """'%' pairs as wstr_format reads them: the unit after '%' decides."""
    out, i = [], 0
    while i < len(units):
        if units[i] == 0x25:
            nxt = units[i + 1] if i + 1 < len(units) else 0
            out.append(CONV_NAMES.get(chr(nxt) if nxt < 0x80 else '', 'other' if nxt else 'lone % at end'))
            i += 2
        else:
            i += 1
    return out


def ends_in_conversion(units):
    i, last = 0, False
    while i < len(units):
        if units[i] == 0x25:
            last = i + 2 >= len(units)
            i += 2
        else:
            last = False
            i += 1
    return last


def table_stats(data):
    entries = list(R.uni_entries(data))
    keys = [k for _ko, k, _to, _u, _n in entries]
    texts = [u for _ko, _k, _to, u, _n in entries]
    counter = collections.Counter(keys)
    table = R.TextTable()
    placed = table.register(data, 0x100000)
    probe = collections.Counter()
    for (addr, slot), key in zip(placed, keys):
        probe[(slot - R.text_hash(key)) & 0x1FFF] += 1
    conv = collections.Counter()
    for units in texts:
        conv.update(conversions(units))
    lengths = [len(u) for u in texts]
    return {
        'entries': len(entries),
        'distinct keys': len(counter),
        'keys repeated (later copies unreachable)': sum(n - 1 for n in counter.values() if n > 1),
        'keys holding a double quote (unreachable)': sum(1 for k in keys if b'"' in k),
        'keys with a byte >= 0x80': sum(1 for k in keys if any(b >= 0x80 for b in k)),
        'longest key (bytes)': max((len(k) for k in keys), default=0),
        'keys > 159 bytes (script stack copy)': sum(1 for k in keys if len(k) > R.LIMITS['script key']),
        'empty texts': sum(1 for n in lengths if n == 0),
        'longest text (units)': max(lengths, default=0),
        'texts > 31 units': sum(1 for n in lengths if n > 31),
        'texts > 99 units': sum(1 for n in lengths if n > 99),
        'texts > 127 units': sum(1 for n in lengths if n > 127),
        'texts > 255 units': sum(1 for n in lengths if n > 255),
        'texts with a unit >= 0x100': sum(1 for u in texts if any(c >= 0x100 for c in u)),
        'distinct units': len({c for u in texts for c in u}),
        'texts with a %': sum(1 for u in texts if 0x25 in u),
        'texts ending in a conversion': sum(1 for u in texts if ends_in_conversion(u)),
        'conversions': dict(sorted(conv.items())),
        'hash slots used': sum(1 for s in table.slots if s),
        'probe distance histogram': dict(sorted(probe.items())),
        'bytes': len(data),
    }, table, dict(zip(keys[::-1], texts[::-1]))   # first copy of a key wins


class Script:
    """Built-in calls of one script.scr with their literal arguments (layout in scr.py)."""

    def __init__(self, data):
        parsed = scr.parse(data)
        self.data = data
        self.imports = [name for _v, name in parsed['externals']]
        self.str_base = parsed['strings'][0]
        cs, ce = parsed['code']
        words = struct.unpack_from('<%dI' % ((ce - cs) // 4), data, cs)
        self.calls = []
        i, pending = 0, []
        while i < len(words):
            op = words[i]
            if op == 0x7D:
                i += 3
                continue
            if op == 0x7B:
                n = words[i + 1]
                name = self.imports[n] if n < len(self.imports) else '?'
                self.calls.append((name, pending[:-1][::-1]))
                pending = []
                i += 2
                continue
            if op == 0x27:
                pending.append(words[i + 1])
                i += 2
                continue
            if op == 0x2C:
                pending = []
                i += 2
                continue
            pending = pending + [None] if op == 0x28 else []
            i += 1 + (0 if op in scr.NO_OPERAND else 1)

    def string(self, offset):
        """A string literal at data offset `offset`: packed (big-endian bytes per cell)
        when its first cell is above 0xff, else one character per cell."""
        if offset is None:
            return None
        at = self.str_base + offset
        if at + 4 > len(self.data):
            return None
        first, = struct.unpack_from('<I', self.data, at)
        out = bytearray()
        if first > 0xFF:
            while at + 4 <= len(self.data):
                for b in struct.pack('>I', struct.unpack_from('<I', self.data, at)[0]):
                    if b == 0:
                        return bytes(out)
                    out.append(b)
                at += 4
            return None
        while at + 4 <= len(self.data):
            cell, = struct.unpack_from('<I', self.data, at)
            if cell == 0:
                return bytes(out)
            out.append(cell & 0xFF)
            at += 4
        return None


def census(root):
    files = []
    english = None
    scripts = []
    for container, lname, blob in lump_blobs(root):
        try:
            entries = lmp_entries(blob)
        except (struct.error, ValueError, IndexError):
            continue
        for ename, off, size in entries:
            ext = ename.rsplit('.', 1)[-1].lower() if '.' in ename else ''
            if ext in ('uni', 'txt'):
                files.append((container, lname, ename, ext, blob[off:off + size]))
            if ename == 'script.scr':
                scripts.append(blob[off:off + size])
    print('string files: %d (.uni %d, .txt %d)' % (
        len(files), sum(1 for f in files if f[3] == 'uni'), sum(1 for f in files if f[3] == 'txt')))
    for container, lname, ename, ext, data in files:
        where = container if container == lname else '%s/%s' % (container, lname)
        if ext != 'uni':
            print('  %s : %s  %d bytes (not a key table; credits.txt is split into lines by 0x223ba0)'
                  % (where, ename, len(data)))
            continue
        stats, table, texts = table_stats(data)
        print('  %s : %s' % (where, ename))
        for key, value in stats.items():
            print('    %-44s %s' % (key, value))
        if lname.lower() == 'gtext.lmp':
            english = (table, texts, data)
    if english is None:
        print('no GTEXT.LMP found')
        return 1
    table, texts, data = english
    print('level scripts: %d' % len(scripts))
    per = {name: collections.Counter() for name in COMMANDS}
    distinct = {name: set() for name in COMMANDS}
    longest = {name: 0 for name in COMMANDS}
    for image in scripts:
        script = Script(image)
        for name, args in script.calls:
            if name not in COMMANDS:
                continue
            c = per[name]
            c['calls'] += 1
            key_idx, other_idx = COMMANDS[name]
            for idx in key_idx:
                key = script.string(args[idx]) if idx < len(args) else None
                if key is None:
                    c['key not a literal'] += 1
                    continue
                distinct[name].add(key)
                stripped = R.strip_quotes(key)
                if stripped not in texts:
                    c['key missing from GTEXT (shows NF:)'] += 1
                    continue
                units = texts[stripped]
                longest[name] = max(longest[name], len(units))
                limit = LIMIT_OF.get((name, idx))
                if name == 'addHelpMessageF':
                    convs = conversions(units)
                    c['F text conversions %s' % (','.join(convs) or 'none')] += 1
                    value_idx = idx + 1
                    value = args[value_idx] if value_idx < len(args) else None
                    if value is None:
                        c['F value not a literal'] += 1
                    addr = table.find(key)
                    try:
                        out, _used = R.format_one_int(table.reader(addr), value or 0)
                    except R.FormatError:
                        c['F text would dereference a float (%s/%u)'] += 1
                        continue
                    if len(out) > len(R.visible(out)) + 1:
                        c['F formatter read past the terminator'] += 1
                    if limit is not None and len(R.visible(out)) > limit:
                        c['formatted text over its buffer (%d units)' % limit] += 1
                elif limit is not None and len(units) > limit:
                    c['text over its buffer (%d units)' % limit] += 1
            if name == 'showBust':
                maximum = args[3] if len(args) > 3 else None
                if maximum is None:
                    c['bust maximum not a literal'] += 1
                elif maximum == 0xFFFFFFFF:
                    c['bust maximum -1 (value shown as a number)'] += 1
                else:
                    c['bust maximum literal (meter)'] += 1
            for idx in other_idx:
                s = script.string(args[idx]) if idx < len(args) else None
                if s is None:
                    c['name argument not a literal'] += 1
                elif name == 'showBust' and len(s) > R.LIMITS['bust texture name']:
                    c['texture name over 39 bytes'] += 1
    for name in COMMANDS:
        print('  %s' % name)
        print('    %-44s %d' % ('distinct literal keys', len(distinct[name])))
        print('    %-44s %d' % ('longest looked-up text (units)', longest[name]))
        for key, value in sorted(per[name].items()):
            print('    %-44s %d' % (key, value))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--disc', required=True)
    args = parser.parse_args(argv)
    return census(args.disc)


if __name__ == '__main__':
    sys.exit(main())
