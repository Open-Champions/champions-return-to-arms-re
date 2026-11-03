"""Independent level-travel expectations for the round-four exit probes.

The act rows are read from the executable table at 0x4f8e48. Counts are the
13 words at 0x4f8e10. Matching is a prefix test, not an exact-name test.
"""
import struct


ACT_TABLE, ACT_COUNTS, ACT_N = 0x4F8E48, 0x4F8E10, 13
DIR_ENTRY, DIR_LIMIT = 0x18, 10
DATA_BASE, SIZE_LIMIT = 0x16118, 0x4BC78
FORCED_SIZE = 35000


def _u32(blob, off):
    return struct.unpack_from('<I', blob, off)[0]


def _cstr(blob, off):
    end = blob.find(b'\0', off)
    return blob[off:end].decode('ascii')


def load_acts(elf_path):
    """Return (rows, counts). rows[act] is every (name, size) pair in file order."""
    blob = open(elf_path, 'rb').read()
    phoff, = struct.unpack_from('<I', blob, 28)
    phentsize, phnum = struct.unpack_from('<HH', blob, 42)
    segs = []
    for i in range(phnum):
        kind, off, va, _pa, filesz, _memsz, _flags, _align = struct.unpack_from(
            '<8I', blob, phoff + i * phentsize)
        if kind == 1 and filesz:
            segs.append((va, off, filesz))

    def va_off(addr):
        for va, off, filesz in segs:
            if va <= addr < va + filesz:
                return off + (addr - va)
        raise ValueError('unmapped table address')

    counts = [_u32(blob, va_off(ACT_COUNTS + 4 * act)) for act in range(ACT_N)]
    rows = []
    for act in range(ACT_N):
        base = _u32(blob, va_off(ACT_TABLE + 4 * act))
        act_rows = []
        for index in range(counts[act]):
            name = _u32(blob, va_off(base + 8 * index))
            size = struct.unpack_from('<H', blob, va_off(base + 8 * index + 4))[0]
            act_rows.append((_cstr(blob, va_off(name)), size))
        rows.append(tuple(act_rows))
    return tuple(rows), tuple(counts)


def find_act(rows, current, name):
    """Act index, or -1. Current act is searched before acts 0..n-1."""
    order = []
    if 0 <= current < len(rows):
        order.append(current)
    order.extend(range(len(rows)))
    for act in order:
        for row_name, _size in rows[act]:
            if row_name and name.startswith(row_name):
                return act
    return -1


def act_change(rows, current, name):
    """Return (new act, changed flag). An unknown name leaves the act alone."""
    found = find_act(rows, current, name)
    if found < 0 or found == current:
        return current, 0
    return found, 1


def qualified_name(level, sub):
    return '%s_%s' % (level, sub) if sub else level


def split_request(pending):
    """Base name, sub name, and the orientation byte the loader forces."""
    if pending.startswith('_'):
        base, sub = '', pending[1:]
    elif '_' in pending:
        base, sub = pending.split('_', 1)
    else:
        base, sub = pending, ''
    return base, sub, 0xFE


def store_size(rows, current, name, forced):
    """Reserved directory size, or None when this departure stores nothing.

    The forced byte wins. Otherwise a hub prefix uses row 0 of the current
    act. Any other name uses the first current-act row it starts with.
    """
    if forced:
        return FORCED_SIZE
    if current < 0:
        return None
    if name.startswith('hub'):
        return rows[current][0][1]
    for row_name, size in rows[current]:
        if row_name and name.startswith(row_name):
            return size
    return None


def store_directory(entries, name, size):
    """Return (entries, data offset or None). Offset None means no writer call.

    entries are (name, size) in directory order. A new key is appended even
    when it becomes the 11th entry or the following bytes will not fit.
    """
    prior = 0
    match = None
    for index, (key, key_size) in enumerate(entries[:DIR_LIMIT]):
        if key == name:
            match = index
            break
        prior += key_size
    updated = list(entries)
    if match is None:
        updated.append((name, size))
    else:
        size = updated[match][1]
    write = prior + size + DATA_BASE <= SIZE_LIMIT
    return tuple(updated), prior if write else None
