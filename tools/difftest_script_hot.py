#!/usr/bin/env python3
"""The most-used level-script commands, run on the original handlers.

Counts SYSREQ.C across the disc (counts only; tools/script_usage.py) and
requires that census to match the tables in docs/script.md. Then, for every
command with at least 100 calls, runs the original handler through
scr_callNative in tools/ee_emu.py and runs the entry points of the level
scripts that call it, comparing both with tools/ref_natives.py.

  python3 tools/difftest_script_hot.py --disc DIR --elf SLUS_209.73
      [--workdir DIR] [--cases N] [--seeds N] [--chain N]

--workdir receives numbered script images so the existing script runner can
read them. It is meant to be a directory under local/, which is not tracked.
The run prints counts and PASS/FAIL lines. It does not print level names,
entry-point names or string literals on success.

The handler cases and the script runs are the same comparison as
tools/difftest_natives.py. This file only chooses the commands and the scripts.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import difftest_natives as D                    # noqa: E402
import ref_natives as N                         # noqa: E402
import ref_script_compose as C                  # noqa: E402
import script_usage as U                        # noqa: E402

ROOT = os.path.dirname(_HERE)
CALL_FLOOR = 100


def hot_names(calls):
    return [name for name in N.NATIVE_NAMES if calls[name] >= CALL_FLOOR]


def check_census(calls, levels):
    published = C.published_counts()
    mismatches = []
    for name in N.NATIVE_NAMES:
        got = (calls[name], levels[name])
        if got != published[name]:
            mismatches.append((name, published[name], got))
    return mismatches


def extract(images, directory, calls_of):
    """Write images that call a hot command. File names are numbers."""
    os.makedirs(directory, exist_ok=True)
    for filename in os.listdir(directory):
        if filename.endswith('.scr'):
            os.remove(os.path.join(directory, filename))
    kept = 0
    for image in images:
        one, _pri, error = U.count_image(image)
        if error or not any(one.get(name, 0) for name in calls_of):
            continue
        path = os.path.join(directory, '%04d.scr' % kept)
        with open(path, 'wb') as out:
            out.write(image)
        kept += 1
    return kept


def main(argv):
    disc = elf = None
    work = os.path.join(ROOT, 'local', 'script-hot')
    cases, seeds, chain = 12, 1, 10
    index = 0
    args = list(argv)
    while index < len(args):
        arg = args[index]
        if arg in ('--disc', '--elf', '--workdir') and index + 1 < len(args):
            index += 1
            if arg == '--disc':
                disc = args[index]
            elif arg == '--elf':
                elf = args[index]
            else:
                work = args[index]
        elif arg in ('--cases', '--seeds', '--chain') and index + 1 < len(args):
            index += 1
            value = int(args[index])
            if arg == '--cases':
                cases = value
            elif arg == '--seeds':
                seeds = value
            else:
                chain = value
        else:
            print(__doc__)
            return 2
        index += 1
    if not disc or not elf:
        print(__doc__)
        return 2
    images, walk_refused = U.script_images_from_disc(disc)
    calls, levels, unknown, pri, refused = U.census(images)
    refused += walk_refused
    hot = hot_names(calls)
    mismatches = check_census(calls, levels)
    print('scripts %d' % len(images))
    print('refused %d' % refused)
    print('sysreq_c %d' % sum(calls.values()))
    print('sysreq_pri %d' % pri)
    print('unknown_names %d' % unknown)
    print('census_mismatches %d' % len(mismatches))
    print('hot %d' % len(hot))
    if mismatches or unknown or pri or refused or len(images) != 120:
        return 1
    kept = extract(images, work, set(hot))
    print('hot_scripts %d' % kept)
    with open(elf, 'rb') as source:
        digest = __import__('hashlib').sha256(source.read()).hexdigest()
    if digest != D.EXPECTED_SHA256:
        print('elf_sha_mismatch')
        return 1
    D.OPTIONS['quick'] = False
    D.OPTIONS['seed'] = 20973
    D.OPTIONS['filter'] = 'hot'
    D.OPTIONS['verbose'] = False
    D.OPTIONS['cases'] = cases
    D.OPTIONS['seeds'] = seeds
    D.OPTIONS['scripts'] = work
    D.CHAIN_TICKS = chain
    hot_set = set(hot)

    def wanted(text):
        return text in hot_set or text.lower().endswith('.scr')

    D.wanted = wanted
    D.RESULTS[:] = []
    sys.setrecursionlimit(20000)
    rig = D.Rig(elf)
    rig.checkpoint()
    coverage = D.Coverage(rig)
    stats = {'cases': 0, 'faults': 0, 'executed': set()}
    print('--- handlers')
    D.group_builtins(rig, coverage, stats)
    print('--- scripts')
    D.group_scripts(rig, coverage, stats)
    passed = sum(1 for _name, ok in D.RESULTS if ok)
    failed = len(D.RESULTS) - passed
    print('properties %d pass %d fail %d' % (len(D.RESULTS), passed, failed))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
