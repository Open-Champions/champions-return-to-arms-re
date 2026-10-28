#!/usr/bin/env python3
"""Strict, additive mission-2 record links and bounded static call checks.

Run with unittest preloaded before putting tools/ on sys.path. Owner inputs
stay under local/. Only the original record loader executes in ee_emu here;
script topology is Observed, not executed or a reachability claim. Existing
reference APIs and vectors are unchanged.
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import struct
import sys

import difftest_mission2 as D
from dump_tables import parse_objects
import ref_amx as A
import ref_mission2 as R
import scr


class ContractError(AssertionError):
    """A failure carrying only authored diagnostics, addresses or ordinals."""


def require(condition, message):
    """Fail closed even under python -O; never print private property values."""
    if not condition:
        raise ContractError(message)


def strict_objects(blob):
    """Validate record/string bounds before using the existing object parser."""
    require(len(blob) >= 8, 'object header truncated')
    count, _flags, pool = struct.unpack_from('<hHi', blob)
    require(count >= 0 and 8 <= pool <= len(blob), 'object header bounds')

    def string(offset):
        require(0 <= offset < len(blob) - pool, 'object string offset')
        end = blob.find(b'\0', pool + offset)
        require(end >= pool + offset, 'object string unterminated')
        require(end > pool + offset, 'object string empty')
        # The existing parser joins with this delimiter: refuse ambiguity.
        require(b';' not in blob[pool + offset:end], 'object property delimiter')

    at = 8
    for ordinal in range(count):
        require(at + 24 <= pool, f'record {ordinal}: truncated')
        cls, size, _angle = struct.unpack_from('<ihH', blob, at)
        require(size >= 24 and size % 4 == 0 and at + size <= pool,
                f'record {ordinal}: size')
        string(cls)
        terminal = None
        for pos in range(at + 20, at + size, 4):
            value = struct.unpack_from('<i', blob, pos)[0]
            if value == 0:
                terminal = pos
                break
            string(value)
        require(terminal is not None, f'record {ordinal}: no property terminator')
        require(all(x == 0 for x in blob[terminal:at + size]),
                f'record {ordinal}: nonzero trailing properties')
        at += size
    require(at == pool, 'record count does not reach string table')
    return parse_objects(blob, 'owner input')


class BoundedScript(D.ScriptCheck):
    """Validate table uniqueness and instruction boundaries without executing.

    Entry bounds are [public start, next public start), or the code end for
    the last entry. Require every PROC to have a public start so an unnamed
    procedure cannot silently be included in the preceding entry's range.
    """
    def __init__(self, image):
        require(len(image) >= 0xa0, 'script header truncated')
        base = scr.BASE
        require(struct.unpack_from('<H', image, base + 4)[0] == A.MAGIC, 'script magic')
        require(struct.unpack_from('<H', image, base + 8)[0] & 5 == 0,
                'unsupported script encoding')
        require((image[base + 6], image[base + 7]) == (3, 1),
                'unsupported script version')
        cod, dat, hea, stp = struct.unpack_from('<IIII', image, base + 0x0c)
        stored_size = struct.unpack_from('<I', image, base)[0]
        require(stored_size == hea and hea <= stp == len(image) - base
                and stp % 4 == 0 and stp <= 0x7ffffffe, 'script image/stack bounds')
        require(0x40 <= cod < dat <= hea <= len(image) - base,
                'script section bounds')
        require(cod % 4 == dat % 4 == hea % 4 == 0, 'script section alignment')
        require(struct.unpack_from('<H', image, base + 0x0a)[0] == 24,
                'script table record size')
        spans = []
        for header in (0x20, 0x28):
            count, off = struct.unpack_from('<II', image, base + header)
            require(0x40 <= off <= cod and count <= (cod - off) // 24,
                    'script table bounds')
            spans.append((off, off + count * 24))
            for i in range(count):
                name = image[base + off + i * 24 + 4:base + off + (i + 1) * 24]
                require(name[0] != 0 and b'\0' in name, 'script table name')
        require(spans[0][1] <= spans[1][0] or spans[1][1] <= spans[0][0],
                'overlapping script tables')
        parsed = scr.parse(image)
        starts = [at for at, _name in parsed['internals']]
        names = [name for _at, name in parsed['internals']]
        natives = [name for _at, name in parsed['externals']]
        require(bool(starts) and len(set(starts)) == len(starts), 'entry offset ambiguity')
        require(len(set(names)) == len(names), 'entry name ambiguity')
        require(len(set(natives)) == len(natives), 'native name ambiguity')
        require(all(at % 4 == 0 and 0 <= at < dat - cod for at in starts),
                'entry outside code')
        super().__init__(image)
        self.instructions = self._instructions()
        require({at for at, (op, _end) in self.instructions.items() if op == A.OP['PROC']}
                == set(starts), 'entry/procedure mismatch')
        ordered = sorted(starts)
        self.bounds = dict(zip(ordered, ordered[1:] + [dat - cod]))

    def _instructions(self):
        result, at, end = {}, 0, self.end - self.start
        while at < end:
            op = self.word(at)
            require(1 <= op < len(A.OPCODES), f'invalid opcode at {at:#x}')
            kind = A.OPCODES[op][1]
            length = 4
            if kind in (A.V, A.C):
                length = 8
            elif kind in (A.LINE, A.SRANGE):
                length = 12
            elif kind in (A.FILE, A.SYMBOL):
                require(at + 8 <= end, 'debug record truncated')
                size = self.word(at + 4)
                require(size >= (8 if kind == A.SYMBOL else 4) and size % 4 == 0,
                        'debug record size')
                length = 8 + size
            elif kind == A.CASETBL:
                require(at + 8 <= end, 'case table truncated')
                count = self.word(at + 4)
                require(count <= (end - at - 12) // 8, 'case table count')
                length = 12 + 8 * count
            require(at + length <= end, f'instruction truncated at {at:#x}')
            result[at] = (op, at + length)
            at += length
        return result

    def entry_bounds(self, start, end=None):
        require(start in self.bounds, f'entry absent at {start:#x}')
        actual = self.bounds[start]
        if end is not None:
            require(actual == end, f'entry bound changed at {start:#x}')
        return start, actual

    def call_values_in(self, start, end, site, native, count, strings=()):
        """Check a whole immediate-argument packet, call and cleanup in one entry.

        All offsets are code-relative. Strings are resolved only in memory;
        callers must specify their argument indices (integer zero is not a
        string merely because the pool has a value at offset zero).
        """
        self.entry_bounds(start, end)
        require(isinstance(count, int) and count >= 0, 'invalid argument count')
        require(len(set(strings)) == len(strings) and
                all(0 <= i < count for i in strings), 'invalid string arguments')
        first = site - 8 * (count + 1)
        require(start <= first and site + 16 <= end, f'call crosses entry at {site:#x}')
        expected = [(at, A.OP['PUSH.C']) for at in range(first, site, 8)]
        expected += [(site, A.OP['SYSREQ.C']), (site + 8, A.OP['STACK'])]
        for at, op in expected:
            require(self.instructions.get(at) == (op, at + 8),
                    f'call packet is not an instruction at {at:#x}')
        require(native in self.natives, f'native absent at {site:#x}')
        require(self.word(site + 4) == self.natives.index(native), f'wrong native at {site:#x}')
        require(self.word(site - 4) == count * 4, f'argument count at {site:#x}')
        require(self.word(site + 12) == (count + 1) * 4, f'cleanup count at {site:#x}')
        values = [self.word(at + 4) for at in range(first, site - 8, 8)][::-1]
        for i in strings:
            require(values[i] in self.strings, f'string argument at {site:#x}')
            values[i] = self.strings[values[i]]
        return tuple(values)

    def call_in(self, start, end, site, native, *args):
        """Assert typed arguments as well as the packet's owning entry."""
        actual = self.call_values_in(start, end, site, native, len(args),
                                     tuple(i for i, arg in enumerate(args) if isinstance(arg, str)))
        require(actual == args, f'call argument changed at {site:#x}')
        return actual


def property_values(row, key):
    return tuple(part[len(key) + 1:] for part in row['properties'].split(';')
                 if part.startswith(key + '='))


def one_property(row, key):
    values = property_values(row, key)
    require(len(values) == 1 and bool(values[0]),
            f"record {row['index']}: expected one nonempty property")
    return values[0]


def record_links(rows, ctor, key, script, expected):
    """Pin ordinal->entry pairs and their multiplicities, with one key per row."""
    selected = [row for row in rows if R.FACTORY.get(row['class'].lower(), (0, 0))[1] == ctor]
    require(Counter(row['index'] for row in selected) == Counter(at for at, _ in expected),
            'linked record ordinals/count changed')
    pairs = []
    for row in selected:
        name = one_property(row, key)
        require(name in script.entries, f"record {row['index']}: link is not an entry")
        pairs.append((row['index'], script.entries[name]))
    require(Counter(pairs) == Counter(expected), 'record link pairing changed')
    require(Counter(at for _record, at in pairs) == Counter(at for _record, at in expected),
            'record link multiset changed')
    return len(pairs)


# Only record ordinals, constructor addresses, and code-relative offsets.
LINKS = (
    (0, 0x29df04, 'dialogscript', ((72, 0x000), (73, 0x094))),
    (0, 0x1ec900, 'action', ((263, 0x128),)),
    (1, 0x1ec900, 'action', ((139, 0x000), (140, 0x044))),
    (2, 0x1ec900, 'action', ((38, 0x000), (102, 0x044))),
    (3, 0x1ec900, 'action', ((31, 0x044),)),
    (3, 0x27a00c, 'deathscript', ((30, 0x000),)),
    (3, 0x1ecdf4, 't', ((58, 0x150), (59, 0x194))),
    (3, 0x27c694, 'script', ((57, 0x110),)),
)


def check_contract(scripts, rows_by_level):
    """Observe exact mappings/cells, returning counts; does not execute scripts."""
    require(len(scripts) == len(rows_by_level) == 4, 'expected four levels')
    for level, (script, rows) in enumerate(zip(scripts, rows_by_level)):
        require(len(script.entries) == (28, 3, 3, 14)[level], 'entry count changed')
        require([row['index'] for row in rows] == list(range(len(rows))), 'record ordinal sequence')
        require(Counter(row['class'] for row in rows) == Counter(R.COUNTS[R.LEVELS[level]]),
                'record class counts changed')
    links = sum(record_links(rows_by_level[level], ctor, key, scripts[level], expected)
                for level, ctor, key, expected in LINKS)
    portals = [r for r in rows_by_level[0] if R.FACTORY.get(r['class'].lower(), (0, 0))[1] == 0x27c694]
    require(len(portals) == 1 and portals[0]['index'] == 71, 'first portal ordinal')
    require(not property_values(portals[0], 'script'), 'first portal has unexpected script link')
    calls = []

    def values(level, start, end, site, native, count, strings=()):
        result = scripts[level].call_values_in(start, end, site, native, count, strings)
        calls.append((level, start, end, site))
        return result

    def call(level, start, end, site, native, *args):
        actual = values(level, start, end, site, native, len(args),
                        tuple(i for i, x in enumerate(args) if isinstance(x, str)))
        require(actual == args, f'call argument changed at {site:#x}')

    def entry(level, offset):
        return scripts[level].entry_at(offset)

    for level, start, end, site, destination in (
        (0, 0x128, 0x16c, 0x154, R.LEVELS[1]),
        (1, 0x000, 0x044, 0x02c, 0), (1, 0x044, 0x088, 0x070, R.LEVELS[2]),
        (2, 0x000, 0x044, 0x02c, 0), (2, 0x044, 0x088, 0x070, R.LEVELS[3]),
        (3, 0x044, 0x088, 0x070, R.LEVELS[2]),
    ):
        call(level, start, end, site, 'newWorld', destination)
    dialogs = [values(0, start, end, site, 'startDialog', 3, (0,))
               for start, end, site in ((0, 0x54, 0x3c), (0x94, 0xe8, 0xd0))]
    require(dialogs[0][1:] == (1, 1) and dialogs[1][1:] == (1, 0), 'dialog controls changed')
    require(dialogs[0][0] != dialogs[1][0], 'dialog identities collapsed')
    call(0, 0x54, 0x94, 0x80, 'callScript', entry(0, 0xe48))
    call(0, 0xe8, 0x128, 0x114, 'callScript', entry(0, 0xfa4))
    call(0, 0xb00, 0xbe0, 0xb34, 'setMissionAvailable', 2, 1)
    started = values(0, 0xb00, 0xbe0, 0xb68, 'setv', 2, (0,))
    current = values(0, 0xb00, 0xbe0, 0xb9c, 'setv', 2, (0,))
    require(started[1] == 1 and current[1] == 2 and started[0] != current[0], 'mission variable controls')
    call(0, 0xb00, 0xbe0, 0xbc8, 'postAction', entry(0, 0xbe0))
    call(0, 0xbe0, 0xc98, 0xc4c, 'cutScene', R.LEVELS[0])
    branches = [values(0, start, end, site, 'addQuest', 2, (0, 1))
                for start, end, site in ((0x2e0, 0x360, 0x314), (0x910, 0x990, 0x944))]
    require(branches[0][0] == branches[1][0] and branches[0][1] != branches[1][1], 'quest argument relations')
    removed = values(0, 0x418, 0x4f0, 0x480, 'removePlayerItem', 2, (1,))
    require(removed == (0xffffffff, 'coppersprocket'), 'item removal controls')
    boss = rows_by_level[3][30]
    require(one_property(boss, 'dropitem') == removed[1], 'boss drop/turn-in relation')
    call(0, 0x418, 0x4f0, 0x4ac, 'removeQuest', branches[0][0])
    call(0, 0x418, 0x4f0, 0x4d8, 'addDeferedCall', entry(0, 0xc98))
    given = values(0, 0xc98, 0xe48, 0xcd4, 'givePlayerItem', 3, (0,))
    require(given[0] != removed[1] and given[1:] == (0, 0), 'grant item controls')
    call(0, 0xc98, 0xe48, 0xd00, 'grantMission', 2)
    call(3, 0x000, 0x044, 0x02c, 'callScript', entry(3, 0x46c))
    gate = values(3, 0x110, 0x150, 0x13c, 'getv', 1, (0,))
    call(3, 0x150, 0x194, 0x17c, 'callScript', entry(3, 0x21c))
    call(3, 0x194, 0x1d8, 0x1c0, 'callScript', entry(3, 0x3f0))
    call(3, 0x1d8, 0x21c, 0x204, 'addDeferedCall', entry(3, 0x4e4))
    cut = values(3, 0x21c, 0x32c, 0x280, 'cutScene', 1, (0,))
    require(cut == ('iron',), 'boss cutscene argument')
    call(3, 0x21c, 0x32c, 0x2e0, 'postAction', entry(3, 0x32c))
    call(3, 0x21c, 0x32c, 0x314, 'callScript', entry(3, 0x39c))
    call(3, 0x32c, 0x39c, 0x358, 'setSaveInhibit', 1)
    call(3, 0x32c, 0x39c, 0x384, 'callScript', entry(3, 0x39c))
    flag = values(3, 0x39c, 0x3f0, 0x3d8, 'setCFlag', 3, (0,))
    require(flag[1:] == (0, 1), 'boss flag controls')
    call(3, 0x46c, 0x4e4, 0x4a0, 'setv', gate[0], 1)
    call(3, 0x46c, 0x4e4, 0x4cc, 'setSaveInhibit', 0)
    require(len(set(calls)) == len(calls), 'duplicate call claim')
    return {'links': links, 'calls': len(calls), 'unlinked_portals': len(portals)}


def load_inputs(source_dir):
    scripts, rows, objects = [], [], []
    for level in R.LEVELS:
        gob = (Path(source_dir) / (level.upper() + '.GOB')).read_bytes()
        obj = D.lump(gob, 'objects.ob')
        objects.append(obj)
        rows.append(strict_objects(obj))
        scripts.append(BoundedScript(D.lump(gob, 'script.scr')))
    return scripts, rows, objects


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable')
    parser.add_argument('source_dir')
    args = parser.parse_args(argv)
    require(hashlib.sha256(Path(args.executable).read_bytes()).hexdigest() == D.SHA256,
            'executable identity mismatch')
    scripts, rows, objects = load_inputs(args.source_dir)
    result = check_contract(scripts, rows)
    consumed = sum(D.loader(args.executable, blob, records) for blob, records in zip(objects, rows))
    require(sum(map(len, rows)) == 699 and consumed == 22156, 'loader totals changed')
    print(f"PASS: {result['links']} per-record links, {result['unlinked_portals']} unlinked portal, "
          f"{result['calls']} bounded static calls; original loader Executed: 699 records/22156 bytes; "
          'factory callback stubbed; script ordering/reachability and transitions Unknown')


def cli(argv=None):
    """A failing command must not print source lines or owner-derived values."""
    try:
        main(argv)
    except ContractError as error:
        print(f'FAIL mission2 links: {error}', file=sys.stderr)
        return 1
    except Exception as error:
        # Imported parsers/emulators may include private data in exception
        # text. Deliberately suppress both their text and the traceback.
        print(f'FAIL mission2 links: {type(error).__name__} (details suppressed)', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
