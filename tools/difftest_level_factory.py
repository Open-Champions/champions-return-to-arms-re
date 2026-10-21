#!/usr/bin/env python3
"""difftest_level_factory.py - tools/ref_level_factory.py against world_objectFactory 0x159c94.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_level_factory.py [SLUS_209.73] [--disc DIR] [--table] [-v]

    --disc DIR   also run every objects.ob record of the level archives under DIR (GOB
                 files with a sibling TEX, the <stem>.lmp lump inside).  Counts only
    --table      print the test table read from the executable as a Python literal (the
                 source of ref_level_factory.TESTS) and stop
    -v           print the first mismatches (record numbers only, no names)

Suites (the original runs in tools/ee_emu.py):

  table      the factory's name tests, in code order, read from the executable (a static
             scan for the strcasecmp / str_prefixDiffers calls and the string each passes),
             equal to ref_level_factory.TESTS
  names      every test string, upper and lower case, plus each prefix with a suffix
  props      the property fall-backs: every key with values 0, 1, -1 and text, alone,
             after another entry, with a light key, with a capitalised key
  disc       (with --disc) every level record's class string and property list

How the original runs: pool_new 0x14fdb8 answers a block and records the size.  Every
callee the reference names is a recording stub: the constructors, paths_add 0x20f844,
levelSettings_parse 0x22e714, 0x30503c, save_getAct 0x217edc, WaveMaker_ctor.  Everything
else runs for real: the factory, libc_strcasecmp, str_prefixDiffers, props_getInt
0x14f730, props_getStr 0x14f850 and what they call (libc_atoi, strtol, strlen, strncmp),
propList_hasAnyLight 0x23a2b4 and what it calls (libc_sprintf among them).  Compared per
case: the pool sizes asked, the stubbed calls in order, the result (the block, or 0), and
whether the word 0x506044 that clearColor writes was stored.

Nothing from the game is printed: the table mode prints string addresses, never strings;
the disc suite prints record counts.
"""
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError                 # noqa: E402
import ref_level_factory as F                   # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [os.path.join(ROOT, 'local', 'elf', 'SLUS_209.73'), os.path.join(ROOT, 'SLUS_209.73'),
              os.path.expanduser('~/champions-re/SLUS_209.73')]
M32 = 0xFFFFFFFF
FACTORY, POOL_NEW = 0x159C94, 0x14FDB8
G_WORLD = 0x44FDC8
STRCASECMP, PREFIX = 0x3B81A0, 0x159C20
# Every callee a row of the reference names (constructors, the no-object calls, save_getAct):
# these are recording stubs.  Everything else the factory reaches runs for real.
STUBBED = {c for row in F.TESTS + F.NESTED for c in row[3]} | {c for c in F.LINE_WAVE_ROW[1]} | \
    {o[1] for _g, _k, o in F.FALLBACKS if o[0] != 'light'} | \
    {r[1] for _g, _k, o in F.FALLBACKS if o[0] == 'light' for r in o[1:]}
# Constructors whose record counts the disc suite prints (the ones the native client ports;
# docs/script-session.md section 3).
COUNTED = {0x26741C, 0x2AB450, 0x297788, 0x2A4D68, 0x244018, 0x2A8770, 0x2C1F94, 0x271C70}
RESULTS = []
VERBOSE = False


def report(name, ok, detail=''):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


# ---- the table, read from the executable ----------------------------------------------------
def chain(elf, name, props=None):
    """(kind, string address) of every name test the original makes for one class string,
    in the order it makes them: libc_strcasecmp and str_prefixDiffers are hooked and their
    a1 recorded (both still run).  A name that matches no test walks the whole chain."""
    emu = EE(elf)
    seen = []
    emu.hook(STRCASECMP, lambda e: seen.append(('eq', e.r[5] & M32)))
    emu.hook(PREFIX, lambda e: seen.append(('prefix', e.r[5] & M32)))
    _setup(emu)
    n = emu.alloc(len(name) + 1)
    emu.mem.write(n, name + b'\0')
    emu.call(FACTORY, n, emu.alloc(16), 0, _plist(emu, props), max_steps=4000000)
    return seen


def scan_tests(elf):
    """The top-level chain (a class string no test accepts, no properties) and the tests
    nested under the Skeleton prefix (the class string of that prefix itself)."""
    top = chain(elf, b'\x01')
    probe = EE(elf)
    skeleton = [a for k, a in top if k == 'prefix' and probe.mem.cstr(a) in ('Skeleton', b'Skeleton')]
    nested = []
    if skeleton:
        name = probe.mem.cstr(skeleton[0])
        name = name if isinstance(name, bytes) else name.encode('latin-1')
        walk = chain(elf, name)
        nested = walk[walk.index(('prefix', skeleton[0])) + 1:]
    return top, nested


def _setup(emu):
    emu.mem.w32(G_WORLD, emu.alloc(0x100))        # PushTrigger's row reads g_world +0x70
    emu.stub(POOL_NEW, ret=0)


def _plist(emu, props):
    if props is None:
        return 0
    ptrs = []
    for p in props:
        a = emu.alloc(len(p) + 1)
        emu.mem.write(a, p + b'\0')
        ptrs.append(a)
    plist = emu.alloc(4 * (len(ptrs) + 1))
    for k, a in enumerate(ptrs + [0]):
        emu.mem.w32(plist + 4 * k, a)
    return plist


# ---- one run of the original -----------------------------------------------------------------
def run_factory(elf, name, props):
    """Run the factory on (class string, property strings).  Returns the observation
    (pool sizes, other calls, result kind, 0x506044)."""
    emu = EE(elf)
    block = emu.alloc(0x1000)
    world = emu.alloc(0x100)                      # PushTrigger's row reads g_world +0x70
    emu.mem.w32(G_WORLD, world)
    sizes = []

    def pool(e):
        sizes.append(e.r[4] & M32)
        return block
    emu.stub(POOL_NEW, function=pool)
    for target in STUBBED:
        emu.stub(target, ret=0)
    n = emu.alloc(len(name) + 1)
    emu.mem.write(n, name + b'\0')
    pos = emu.alloc(16)
    plist = _plist(emu, props)
    emu.record_writes = True
    emu.reset_log()
    result = emu.call(FACTORY, n, pos, 0, plist, max_steps=4000000)
    calls = tuple(c.target for c in emu.calls if c.target in STUBBED)
    kind = 'block' if (result & M32) == block else ('zero' if (result & M32) == 0 else 'other')
    color = any(w[1] == F.CLEAR_COLOR_WORD for w in emu.writes)
    return (tuple(sizes), calls, kind, color)


def ref_observation(name, props, strings):
    out = F.classify(name, props, strings)
    return (out.sizes, out.calls, 'block' if out.creates else 'zero', out.clear_color)


class ElfStrings:
    """String and ctype reads from the executable, for the reference."""
    def __init__(self, emu):
        self.emu = emu

    def string(self, addr):
        text = self.emu.mem.cstr(addr)
        return text.encode('latin-1') if isinstance(text, str) else bytes(text)

    def ctype(self, index):
        return self.emu.mem.u8((F.CTYPE + index) & M32)


# ---- suites ------------------------------------------------------------------------------------
def suite_table(emu):  # emu: the executable path
    top, nested = scan_tests(emu)
    ok = top == [(t[0], t[1]) for t in F.TESTS] and nested == [(t[0], t[1]) for t in F.NESTED]
    report('table', ok, '%d top-level and %d nested tests made by the original, %d and %d in the '
           'reference' % (len(top), len(nested), len(F.TESTS), len(F.NESTED)))


def compare(elf, cases, strings, label):
    bad = []
    for index, (name, props) in enumerate(cases):
        try:
            got = run_factory(elf, name, props)
        except EmuError as exc:
            bad.append((index, 'emulator stopped: %s' % exc))
            continue
        want = ref_observation(name, props, strings)
        if got != want:
            bad.append((index, 'emu %r ref %r' % (got, want)))
    detail = '%d cases, %d mismatches' % (len(cases), len(bad))
    if bad and VERBOSE:
        detail += '\n    ' + '\n    '.join('case %d: %s' % b for b in bad[:8])
    report(label, not bad, detail)
    return bad


def suite_names(elf, strings):
    cases = []
    for kind, addr, *_rest in F.TESTS + F.NESTED:
        s = strings.string(addr)
        for v in (s, s.upper(), s.lower()):
            cases.append((v, None))
        if kind == 'prefix':
            cases.append((s + b'x', None))
            cases.append((s.lower() + b'Z9', None))
        cases.append((s + b's', []))
        cases.append((s[:-1], []))
    cases.append((b'Line', [b'name=wave']))
    cases.append((b'Line', [b'name=WAVE']))
    cases.append((b'Line', [b'name=other']))
    cases.append((b'Line', []))
    cases.append((b'', []))
    compare(elf, cases, strings, 'names')


def suite_props(elf, strings):
    cases = []
    keys = [strings.string(a) for _k, a, _f in F.FALLBACKS]
    for key in keys:
        low = key.lower()
        for value in (b'0', b'1', b'-1', b'7', b'yes', b'', b'  1', b'\t-3', b'+0', b'4294967296',
                      b'99999999999999999999', b'-99999999999999999999', b'0x10'):
            cases.append((b'NoSuchClass', [low + b'=' + value]))
            cases.append((b'NoSuchClass', [b'other=1', low + b'=' + value]))
            cases.append((b'NoSuchClass', [low + b'=' + value, b'light1=1']))
            cases.append((b'NoSuchClass', [low + b'=' + value, b'ambient=1']))
        cases.append((b'NoSuchClass', [key + b'=1']))
        cases.append((b'NoSuchClass', [low + b'x=1']))
        cases.append((b'NoSuchClass', [low]))
    cases.append((b'NoSuchClass', []))
    cases.append((b'NoSuchClass', None))
    compare(elf, cases, strings, 'props')


def lumps(data):
    pos, out = 0x800, []
    for i in range(0, 0x800, 0x28):
        if data[i] == 0:
            break
        name = data[i:i + 32].split(b'\0')[0].decode('latin-1')
        size = struct.unpack_from('<I', data, i + 0x24)[0]
        out.append((name, data[pos:pos + size]))
        pos = (pos + size + 0x7FF) & ~0x7FF
    return out


def lmp(blob):
    count = struct.unpack_from('<I', blob, 0)[0]
    out = {}
    for k in range(count):
        na, da, size = struct.unpack_from('<III', blob, 4 + 12 * k)
        out.setdefault(blob[na:blob.index(b'\0', na)].decode('latin-1'), blob[da:da + size])
    return out


def records(ob):
    """(class string, property strings) of each record (docs/objects.md, level records)."""
    count, _flags, strtab = struct.unpack_from('<hHi', ob, 0)
    at, out = 8, []
    for _ in range(count):
        cls, size, _angle = struct.unpack_from('<ihh', ob, at)
        name = ob[strtab + cls:ob.index(b'\0', strtab + cls)]
        props, p = [], at + 20
        while True:
            off = struct.unpack_from('<i', ob, p)[0]
            p += 4
            if off == 0:
                break
            props.append(ob[strtab + off:ob.index(b'\0', strtab + off)])
        out.append((name, props))
        at += size
    return out


def suite_disc(elf, strings, root):
    seen, cases, total, levels, weight = {}, [], 0, 0, []
    for dirpath, _dirs, files in os.walk(root):
        lower = {f.lower() for f in files}
        for f in sorted(files):
            if not f.lower().endswith('.gob') or f[:-4].lower() + '.tex' not in lower:
                continue
            data = open(os.path.join(dirpath, f), 'rb').read()
            for name, blob in lumps(data):
                if name.lower() != f[:-4].lower() + '.lmp':
                    continue
                ob = lmp(blob).get('objects.ob')
                if ob is None:
                    continue
                levels += 1
                for cls, props in records(ob):
                    total += 1
                    key = (cls, tuple(props))
                    if key not in seen:
                        seen[key] = len(cases)
                        cases.append((cls, props))
                        weight.append(0)
                    weight[seen[key]] += 1
    bad = compare(elf, cases, strings, 'disc')
    kinds = {'object': 0, 'call': 0, 'clear_color': 0, 'nothing': 0}
    by_ctor = {}
    for (name, props), n in zip(cases, weight):
        out = F.classify(name, props, strings)
        if out.creates:
            kinds['object'] += n
            by_ctor[out.constructor] = by_ctor.get(out.constructor, 0) + n
        elif out.clear_color:
            kinds['clear_color'] += n
        elif out.calls:
            kinds['call'] += n
        else:
            kinds['nothing'] += n
    print('      disc: %d levels, %d records, %d distinct (class, properties), %d mismatches'
          % (levels, total, len(cases), len(bad)))
    print('      records: %d build an object (%d constructors), %d call a function and build '
          'none, %d set the clear colour, %d build nothing' % (
              kinds['object'], len(by_ctor), kinds['call'], kinds['clear_color'], kinds['nothing']))
    for ctor in sorted(by_ctor):
        if ctor in COUNTED:
            print('      constructor 0x%06x: %d records' % (ctor, by_ctor[ctor]))


def find_elf(argv):
    for a in argv:
        if not a.startswith('-') and os.path.exists(a) and not os.path.isdir(a):
            return a
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def main(argv):
    global VERBOSE
    VERBOSE = '-v' in argv
    disc = argv[argv.index('--disc') + 1] if '--disc' in argv else None
    elf = find_elf([a for i, a in enumerate(argv) if i == 0 or argv[i - 1] != '--disc'])
    if elf is None:
        print('SLUS_209.73 not found; nothing compared')
        return 0
    import hashlib
    if hashlib.sha256(open(elf, 'rb').read()).hexdigest() != ELF_SHA:
        print('this is not SLUS_209.73 v2.00; nothing compared')
        return 0
    probe = EE(elf)
    if '--table' in argv:
        top, nested = scan_tests(elf)
        for title, rows in (('TESTS', top), ('NESTED', nested)):
            print(title)
            for kind, addr in rows:
                s = probe.mem.cstr(addr)
                s = s if isinstance(s, bytes) else s.encode('latin-1')
                print("    ('%s', 0x%06X, %r)," % (kind, addr, run_factory(elf, s, [])))
        return 0
    strings = ElfStrings(probe)
    suite_table(elf)
    suite_names(elf, strings)
    suite_props(elf, strings)
    if disc:
        suite_disc(elf, strings, disc)
    failed = [n for n, ok in RESULTS if not ok]
    print('%d suites, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
