#!/usr/bin/env python3
"""fx_level_lights.py - per-level light index from YOUR executable (docs/lighting.md
section 10).

  python3 -I fx_level_lights.py <elf> --json [objects.ob | file.lmp | file.gob ...]

Prints the level table (name, flag word, base light level), the default marker colours
and the addresses of the marker block and the runtime light record.  Optional object
files add the sun, ambient and direction those files' marker objects store.  The
executable does not contain a colour or direction for each level; those come from the
marker objects, and the flag word only selects the base level.

Nothing from the executable or from an object file is written into this repository.
Keep the output local.
"""
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gob                                         # noqa: E402
import ref_lighting as L                           # noqa: E402
from ps2elf import Elf                             # noqa: E402

LEVEL_TABLE = 0x4F7210
ROW_BYTES = 0x30
FLAG_OFFSET = 0x20
MARKER_BLOCK = 0x44FDE0
RUNTIME_RECORD = 0x5D3448
# world_loadRecords 0x14e808 writes these before objects.  Same values as
# LevelLight.from_markers() with no positions.
DEFAULTS = {
    'ambient': [0x20, 0x20, 0x20, 0],
    'sun': [0x44, 0x44, 0x44, 0],
    'direction': [0.0, -1.0, 1.0],
    'base_level': 0x80,
}


def read_levels(u32, cstr, table=LEVEL_TABLE, limit=128):
    """Rows of g_levelTable until the null-name row, which is also the default.

    u32(va) -> int, cstr(va) -> str or None.  Only the name and the flag word at
    +0x20 are lighting fields (docs/data-tables.md 7.1).
    """
    rows = []
    va = table
    for index in range(limit):
        name_ptr = u32(va)
        flags = u32(va + FLAG_OFFSET)
        if not name_ptr:
            return rows, {'index': index, 'flags': flags or 0,
                          'base_level': L.base_level(flags or 0)}
        name = cstr(name_ptr) or ''
        rows.append({'index': index, 'name': name, 'flags': flags or 0,
                     'base_level': L.base_level(flags or 0)})
        va += ROW_BYTES
    raise ValueError('level table did not end within %d rows' % limit)


def lookup_level(rows, default, name, sub=''):
    """The three passes in game_loadLevel (docs/data-tables.md 7.1).

    Exact compare of name + '_' + sub, then a row whose name starts with name, then a
    row whose name occurs inside name.  The first hit in table order wins.  No hit
    returns the null-name row.
    """
    name = name or ''
    exact = name + '_' + (sub or '')
    for row in rows:
        if row['name'] == exact:
            return row
    if name:
        for row in rows:
            if row['name'].startswith(name):
                return row
        for row in rows:
            if row['name'] and row['name'] in name:
                return row
    return default


def _cstr_at(blob, offset):
    if offset < 0 or offset >= len(blob):
        return ''
    end = blob.find(b'\0', offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode('latin1', 'replace')


def parse_objects(blob):
    """objects.ob rows: class name and position.  Returns a list of dicts."""
    if len(blob) < 8:
        return []
    count, _flags, strtab = struct.unpack_from('<hHi', blob, 0)
    rows, p = [], 8
    for _ in range(max(count, 0)):
        if p + 20 > len(blob):
            break
        cls, size, _angle = struct.unpack_from('<ihH', blob, p)
        x, y, z = struct.unpack_from('<3f', blob, p + 8)
        rows.append({'class': _cstr_at(blob, strtab + cls), 'x': x, 'y': y, 'z': z})
        if size <= 0:
            break
        p += size
    return rows


def markers_from_objects(blob):
    """Ambient and sun are trunc(position x 0.5); direction is the position itself.

    The last object of each class wins, which is the value left in the marker block
    when several objects of that class are loaded in order.
    """
    out = {}
    for row in parse_objects(blob):
        if row['class'] == 'charAmbient_Light':
            out['ambient'] = [L.trunc(row[k] * 0.5) for k in ('x', 'y', 'z')]
        elif row['class'] == 'charDirectional_Light':
            out['sun'] = [L.trunc(row[k] * 0.5) for k in ('x', 'y', 'z')]
        elif row['class'] == 'charDirectional_LightD':
            out['direction'] = [row['x'], row['y'], row['z']]
    return out


def _lump_member(blob, wanted):
    try:
        entries = gob.lmp_entries(blob)
    except (struct.error, ValueError, IndexError):
        return None
    for name, off, size in entries:
        if name.lower() == wanted and off >= 0 and size >= 0 and off + size <= len(blob):
            return blob[off:off + size]
    return None


def object_blobs(label, data):
    """(source label, objects.ob bytes) from an objects file, a lump or a GOB."""
    upper = label.upper()
    base = os.path.basename(label)
    if upper.endswith('.GOB'):
        found = []
        try:
            entries = gob.gob_entries(data)
        except (struct.error, ValueError, IndexError):
            return found
        for lname, off, size in entries:
            if off < 0 or size < 0 or off + size > len(data):
                continue
            ob = _lump_member(data[off:off + size], 'objects.ob')
            if ob:
                found.append(('%s:%s' % (base, lname), ob))
        return found
    if upper.endswith('.LMP'):
        ob = _lump_member(data, 'objects.ob')
        return [(base, ob if ob is not None else data)]
    return [(base, data)]


def source_keys(source):
    keys = set()
    for part in source.replace('\\', '/').split('/'):
        for piece in part.split(':'):
            stem, _ext = os.path.splitext(piece)
            if stem:
                keys.add(stem.casefold())
    return keys


def attach_markers(levels, files):
    """Copy marker fields onto the level row whose name matches the file stem."""
    by_name = {}
    for row in levels:
        by_name.setdefault(row['name'].casefold(), row)
    for item in files:
        for key in source_keys(item['source']):
            row = by_name.get(key)
            if row is None:
                continue
            for field in ('ambient', 'sun', 'direction'):
                if field in item:
                    row[field] = item[field]
            item['level_index'] = row['index']
            break
    return files


def build(elf, blobs=()):
    """blobs: iterable of (label, bytes)."""
    rows, default = read_levels(elf.u32, elf.cstr)
    levels = [dict(row) for row in rows]
    files = []
    for label, data in blobs:
        for source, ob in object_blobs(label, data):
            markers = markers_from_objects(ob)
            if markers:
                files.append(dict(markers, source=source))
    attach_markers(levels, files)
    out = {
        'executable_sha256': hashlib.sha256(elf.d).hexdigest(),
        'level_table': LEVEL_TABLE,
        'row_bytes': ROW_BYTES,
        'flag_offset': FLAG_OFFSET,
        'marker_block': MARKER_BLOCK,
        'runtime_record': RUNTIME_RECORD,
        'defaults': DEFAULTS,
        'levels': levels,
        'default': default,
    }
    if files:
        out['files'] = files
    return out


def main(argv):
    args = list(argv[1:])
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return 0 if args else 2
    path = args.pop(0)
    as_json = '--json' in args
    args = [a for a in args if a != '--json']
    if not os.path.exists(path):
        print('no executable at %s' % path)
        return 2
    blobs = []
    for extra in args:
        with open(extra, 'rb') as handle:
            blobs.append((extra, handle.read()))
    result = build(Elf(path), blobs)
    if as_json:
        print(json.dumps(result, indent=1, sort_keys=True))
        return 0
    print('level table 0x%08x  %d rows + default  base from flags at +0x%x' % (
        LEVEL_TABLE, len(result['levels']), FLAG_OFFSET))
    print('marker block 0x%08x  runtime record 0x%08x' % (MARKER_BLOCK, RUNTIME_RECORD))
    print('defaults ambient %s sun %s direction %s base %d' % (
        DEFAULTS['ambient'][:3], DEFAULTS['sun'][:3], DEFAULTS['direction'], DEFAULTS['base_level']))
    for row in result['levels']:
        extra = ''
        if 'ambient' in row or 'sun' in row or 'direction' in row:
            extra = ' markers'
        print('%3d  %08x  base %3d  %s%s' % (row['index'], row['flags'], row['base_level'], row['name'], extra))
    d = result['default']
    print('default row %d  flags %08x  base %d' % (d['index'], d['flags'], d['base_level']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
