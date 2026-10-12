#!/usr/bin/env python3
"""build_net.py - the native build with its network: translate, compile, link.

  python3 tools/recomp/net/build_net.py                       # -> local/recomp-out/bin/rta_native_net
  python3 tools/recomp/net/build_net.py --name fix --pnach patches/SLUS-20973_4028A55F.pnach \
          --sections tools/play-net/sections-suggested.txt    # -> .../bin/rta_native_net-fix

What it does, all of it in directories of its own (the shared translation in
local/recomp-out/gen and tools/recomp/hle.txt are not touched):

1. HLE list = tools/recomp/hle.txt + tools/recomp/net/hle-net.txt.
2. With --pnach: the patch words of the named sections are written into a COPY of the
   executable before translation.  Translated code is fixed at build time, so a code patch
   has to be in the executable the translator reads; the same words are also written to
   <gen>/patch-words.txt, which the shim applies to memory at start (RTA_NET_PATCH=<file>)
   for the words that are data and so that memory reads the same.  The function table is
   given extra rows at the targets of the patches' jumps (split_function_table).
3. tools/recomp/recomp.py --elf <copy> --hle <list> --out local/recomp-out/gen-net[-NAME].
4. Compile with the flags of tools/recomp/build.py and link with netshim.cpp and the
   runtime.  Objects are cached by the text of their source, so a second variant compiles
   only the files its patches changed.

The runtime: every .cpp in tools/recomp/rt/ except the test driver, UNMODIFIED
(--rt live, the default), or a runtime object built earlier (--rt object:<file.o>[,...]) -
for the days on which the runtime's sources are between two states and do not link.
The SHA-1 of what was linked is printed and stored in <gen>/build-info.txt; quote it with
results.

Only the compiler already on the machine is used (clang++); nothing is downloaded.
Everything this writes is derived from the game and stays under local/.
"""
import argparse
import concurrent.futures
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
RT = os.path.join(RECOMP, 'rt')
CACHE = os.path.join(OUT, 'net', 'objcache')


def sha1_file(path):
    digest = hashlib.sha1()
    with open(path, 'rb') as source:
        digest.update(source.read())
    return digest.hexdigest()


def read_pnach(path, sections):
    """[(address, value)] of the `patch=1,EE,<addr>,word,<value>` lines under the sections."""
    wanted = set(sections)
    found, words, section = set(), [], None
    with open(path, errors='replace') as source:
        for line in source:
            line = line.strip()
            match = re.match(r'\[(.*)\]$', line)
            if match:
                section = match.group(1)
                continue
            match = re.match(r'patch=1,EE,([0-9a-fA-F]+),(\w+),([0-9a-fA-F]+)', line)
            if not match or section not in wanted:
                continue
            if match.group(2) != 'word':
                raise SystemExit('pnach: only word patches are handled (%s)' % line)
            found.add(section)
            words.append((int(match.group(1), 16) & 0x1FFFFFFF, int(match.group(3), 16)))
    missing = wanted - found
    if missing:
        raise SystemExit('pnach: no such section: %s' % '; '.join(sorted(missing)))
    return words


def patch_elf(source, target, words):
    with open(source, 'rb') as handle:
        data = bytearray(handle.read())
    phoff, = struct.unpack_from('<I', data, 28)
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    segments = []
    for index in range(phnum):
        kind, offset, vaddr, _, filesz, _ = struct.unpack_from('<6I', data, phoff + index * phentsize)
        if kind == 1:
            segments.append((vaddr, filesz, offset))
    for address, value in words:
        for vaddr, filesz, offset in segments:
            if vaddr <= address and address + 4 <= vaddr + filesz:
                struct.pack_into('<I', data, offset + address - vaddr, value)
                break
        else:
            raise SystemExit('patch word at 0x%x is not in the executable file' % address)
    with open(target, 'wb') as handle:
        handle.write(data)


def split_function_table(source, target, words):
    """A patch that jumps to a routine written into the body of an unused function, and
    from there back into the middle of the patched function, makes the translator treat
    the two functions as entangled - and it merges every function that lies between them
    into one C++ function (the suggested fix set: 1,921 functions, 13.6 MB of C++ in one
    body, which the compiler does not get through).  Giving each target of such a jump a
    row of its own in the function table makes it the start of a unit instead: the jump
    is then an ordinary tail call.  Returns the addresses the table was split at."""
    import bisect
    rows = []
    with open(source) as handle:
        for line in handle:
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 3 or line.startswith('#'):
                continue
            rows.append((int(parts[0], 16), parts[1], [tuple(int(x, 16) for x in item.split('-')) for item in parts[2].split(',')]))
    ranges = sorted((lo, hi) for _, _, items in rows for lo, hi in items)
    starts = [r[0] for r in ranges]

    def range_of(address):
        index = bisect.bisect_right(starts, address) - 1
        if index >= 0 and ranges[index][0] <= address <= ranges[index][1]:
            return ranges[index]
        return None

    def targets(address, word):
        op = word >> 26
        if op == 2:                                                 # j
            return [(address & 0xF0000000) | ((word & 0x03FFFFFF) << 2)]
        if op in (4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17) or (op == 1 and ((word >> 16) & 31) in (0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13)):
            offset = word & 0xFFFF
            return [address + 4 + (offset - 0x10000 if offset & 0x8000 else offset) * 4]
        return []

    splits = set()
    for address, word in words:
        for goal in targets(address, word):
            here, there = range_of(address), range_of(goal)
            if there is not None and there is not here and goal != there[0]:
                splits.add(goal)
    out = []
    for owner, name, items in rows:
        pieces = []
        for lo, hi in items:
            cursor = lo
            for cut in sorted(s for s in splits if lo < s <= hi):
                pieces.append((cursor, cut - 1))
                cursor = cut
            pieces.append((cursor, hi))
        kept = [piece for piece in pieces if piece[0] not in splits]
        if kept:
            out.append((owner, name, kept))
        out += [(piece[0], 'PATCH_%08x' % piece[0], [piece]) for piece in pieces if piece[0] in splits]
    with open(target, 'w') as handle:
        for owner, name, items in sorted(out):
            handle.write('%08x\t%s\t%s\n' % (owner, name, ','.join('%08x-%08x' % item for item in items)))
    return sorted(splits)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', help='variant: gen-net-NAME, rta_native_net-NAME')
    parser.add_argument('--elf', default=os.path.join(ROOT, 'SLUS_209.73'))
    parser.add_argument('--funcs', default=os.path.join(ROOT, 'ghidra_funcs.tsv'))
    parser.add_argument('--pnach', help='PCSX2 patch file')
    parser.add_argument('--sections', help='file of section names, one per line (# comments)')
    parser.add_argument('--section', action='append', default=[], help='one section name; repeatable')
    parser.add_argument('--rt', default='live', help='live | object:<file.o>[,<file.o>...]')
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--define', action='append', default=[])
    parser.add_argument('--seed-cache', help='a directory of objects built by build.py from --seed-gen '
                                             '(same flags): reuse them where the source text is the same')
    parser.add_argument('--seed-gen', default=os.path.join(OUT, 'gen'))
    args = parser.parse_args()

    suffix = '-' + args.name if args.name else ''
    gen = os.path.join(OUT, 'gen-net' + suffix)
    objdir = os.path.join(OUT, 'obj-net' + suffix)
    program = os.path.join(OUT, 'bin', 'rta_native_net' + suffix)
    for path in (gen, objdir, CACHE, os.path.dirname(program)):
        os.makedirs(path, exist_ok=True)

    # 1. the HLE list
    hle_path = os.path.join(gen, 'hle.txt')
    with open(hle_path, 'w') as sink:
        for part in (os.path.join(RECOMP, 'hle.txt'), os.path.join(HERE, 'hle-net.txt')):
            with open(part) as source:
                sink.write(source.read().rstrip('\n') + '\n')

    # 2. patches go into a copy of the executable
    sections = list(args.section)
    if args.sections:
        with open(args.sections) as source:
            sections += [line.strip() for line in source if line.strip() and not line.startswith('#')]
    elf = args.elf
    words = []
    words_path = os.path.join(gen, 'patch-words.txt')
    if sections:
        if not args.pnach:
            raise SystemExit('--section/--sections need --pnach')
        words = read_pnach(args.pnach, sections)
        elf = os.path.join(gen, 'patched.elf')
        patch_elf(args.elf, elf, words)
        with open(words_path, 'w') as sink:
            for address, value in words:
                sink.write('%08x %08x\n' % (address, value))
        print('patched: %d words of %d sections into %s' % (len(words), len(sections), elf))
    elif os.path.exists(words_path):
        os.remove(words_path)
    table = []
    if words:
        funcs = os.path.join(gen, 'funcs-split.tsv')
        splits = split_function_table(args.funcs, funcs, words)
        table = ['--funcs', funcs]
        print('function table split at the targets of patch jumps: %s' % (' '.join('%x' % a for a in splits) or 'nowhere'))

    # 3. translate
    done = subprocess.run([sys.executable, os.path.join(RECOMP, 'recomp.py'), '--elf', elf, '--hle', hle_path,
                           '--out', gen] + table, capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout[-3000:] + done.stderr[-3000:])
        return 1
    for line in done.stdout.splitlines():
        if line.startswith(('warning', 'instructions emitted as rt_unimpl', 'entries', 'transfer targets', 'entangled')):
            print('recomp: ' + line)

    # 4. compile
    codegen = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math']
    codegen += ['-D' + d for d in args.define]
    includes = ['-I', RT, '-I', gen]
    # generated code includes recomp.h, which includes fpu.h and mmi.h, and funcs.h;
    # funcs.h is declarations only: it cannot change the code of a file that compiles
    headers = [os.path.join(RT, n) for n in ('recomp.h', 'fpu.h', 'mmi.h')]
    header_digest = hashlib.sha1()
    for path in headers:
        header_digest.update(open(path, 'rb').read())
    base_key = ' '.join(codegen) + header_digest.hexdigest()

    def key_of(source, extra=''):
        digest = hashlib.sha1((base_key + extra).encode())
        digest.update(open(source, 'rb').read())
        return digest.hexdigest()

    if args.seed_cache and os.path.isdir(args.seed_cache):
        newest_header = max(os.path.getmtime(p) for p in headers)
        seeded = 0
        for entry in sorted(os.listdir(args.seed_gen)):
            source = os.path.join(args.seed_gen, entry)
            obj = os.path.join(args.seed_cache, entry[:-4] + '.o')
            if not entry.endswith('.cpp') or not os.path.exists(obj):
                continue
            if os.path.getmtime(obj) < max(os.path.getmtime(source), newest_header):
                continue
            cached = os.path.join(CACHE, key_of(source) + '.o')
            if not os.path.exists(cached):
                shutil.copyfile(obj, cached)
                seeded += 1
        print('object cache: %d objects taken from %s' % (seeded, args.seed_cache))

    rt_objects, rt_sources, rt_note = [], [], ''
    if args.rt == 'live':
        rt_sources = sorted(os.path.join(RT, n) for n in os.listdir(RT)
                            if n.endswith('.cpp') and n != 'test_driver.cpp')
        digest = hashlib.sha1()
        for path in rt_sources:
            digest.update(open(path, 'rb').read())
        rt_note = 'runtime: live sources %s; runtime.cpp sha1 %s; all of them %s' % (
            ' '.join(os.path.basename(p) for p in rt_sources), sha1_file(os.path.join(RT, 'runtime.cpp')), digest.hexdigest())
    elif args.rt.startswith('object:'):
        rt_objects = [os.path.abspath(p) for p in args.rt[7:].split(',')]
        rt_note = 'runtime: prebuilt object(s) ' + ' '.join('%s sha1 %s' % (p, sha1_file(p)) for p in rt_objects)
    else:
        raise SystemExit('--rt live | object:<file.o>')

    jobs = []           # (source, object, cache key or None)
    for entry in sorted(os.listdir(gen)):
        if entry.endswith('.cpp'):
            source = os.path.join(gen, entry)
            jobs.append((source, os.path.join(objdir, entry[:-4] + '.o'), key_of(source)))
    shim_define = '-DRTA_NET_RT_NOTE="%s"' % rt_note.replace('"', '').replace('\\', '/')
    for source in [os.path.join(HERE, n) for n in sorted(os.listdir(HERE)) if n.endswith('.cpp')] + rt_sources:
        jobs.append((source, os.path.join(objdir, os.path.basename(source)[:-4] + '.o'), None))

    def build_one(job):
        source, target, key = job
        cached = os.path.join(CACHE, key + '.o') if key else None
        if cached and os.path.exists(cached):
            shutil.copyfile(cached, target)
            return source, 0, '', True
        extra = [shim_define] if source.startswith(HERE) else []
        result = subprocess.run(['nice', '-n', '15', 'clang++'] + codegen + includes + extra + ['-c', source, '-o', target],
                                capture_output=True, text=True)
        if result.returncode == 0 and cached:
            shutil.copyfile(target, cached + '.tmp')
            os.replace(cached + '.tmp', cached)
        return source, result.returncode, result.stderr, False

    start = time.time()
    failed = hits = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for source, code, err, hit in pool.map(build_one, jobs):
            hits += hit
            if code != 0:
                failed += 1
                print('FAILED %s\n%s' % (source, err[:3000]))
    print('compiled %d files, %d from the cache, in %.1f s (%d failed)' % (len(jobs) - hits, hits, time.time() - start, failed))
    if failed:
        return 1

    # 5. link.  Symbols of newer runtimes that the shim uses when they exist are weak.
    weak = ['-Wl,-U,__Z9rt_finishi', '-Wl,-U,__Z9rt_fieldsv']
    link = subprocess.run(['clang++', '-o', program] + [job[1] for job in jobs] + rt_objects + weak + ['-lpthread'],
                          capture_output=True, text=True)
    if link.returncode != 0:
        print('LINK FAILED\n' + link.stderr[:4000])
        return 1
    with open(os.path.join(gen, 'build-info.txt'), 'w') as sink:
        sink.write('%s\nexecutable sha1 %s\nhle %s\npatch words %d (%s)\nflags %s\n' % (
            rt_note, sha1_file(args.elf), ' '.join(l.split()[0] for l in open(hle_path) if l.strip() and not l.startswith('#')),
            len(words), '; '.join(sections), ' '.join(codegen)))
    print(rt_note)
    print('linked %s (%d bytes)' % (program, os.path.getsize(program)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
