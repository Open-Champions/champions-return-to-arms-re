#!/usr/bin/env python3
"""Count level-script built-in calls on a disc. Counts only.

  python3 tools/script_usage.py --disc DIR
  python3 tools/script_usage.py --scripts DIR

--disc walks DIR for .GOB archives and counts SYSREQ.C in each script.scr.
--scripts counts files already extracted as *.scr. Nothing is written.
Names of levels, entry points and string literals are not printed.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_amx                                  # noqa: E402
import ref_natives as N                         # noqa: E402
from gob import gob_entries, lmp_entries        # noqa: E402

SYSREQ_C = 0x7B
SYSREQ_PRI = 0x7A


def script_images_from_disc(root):
    images = []
    refused = 0
    for dirpath, _dirs, files in os.walk(root):
        for filename in files:
            if not filename.upper().endswith('.GOB'):
                continue
            path = os.path.join(dirpath, filename)
            try:
                data = open(path, 'rb').read()
                lumps = gob_entries(data)
            except (OSError, ValueError, IndexError):
                refused += 1
                continue
            for _lname, loff, lsize in lumps:
                if loff < 0 or lsize < 0 or loff + lsize > len(data):
                    refused += 1
                    continue
                lump = data[loff:loff + lsize]
                try:
                    entries = lmp_entries(lump)
                except (struct_error(), ValueError, IndexError):
                    refused += 1
                    continue
                for fname, foff, fsize in entries:
                    if fname != 'script.scr':
                        continue
                    if foff < 0 or fsize < 0 or foff + fsize > len(lump):
                        refused += 1
                        continue
                    images.append(lump[foff:foff + fsize])
    return images, refused


def struct_error():
    import struct
    return struct.error


def script_images_from_dir(directory):
    images = []
    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith('.scr'):
            continue
        with open(os.path.join(directory, filename), 'rb') as source:
            images.append(source.read())
    return images, 0


def count_image(image):
    """Return (import call counts, pri calls, load error) for one script image."""
    machine = ref_amx.Machine(image)
    error = machine.load()
    if error != 0:
        return {}, 0, error
    names = [machine.native_name(index).decode('latin1', 'replace') for index in range(max(machine.num_natives, 0))]
    calls = {}
    pri = 0
    for _start, (opcode, operand, _end) in machine._decoded.items():
        if opcode == SYSREQ_PRI:
            pri += 1
        elif opcode == SYSREQ_C:
            if isinstance(operand, int) and 0 <= operand < len(names):
                calls[names[operand]] = calls.get(names[operand], 0) + 1
            else:
                calls['?'] = calls.get('?', 0) + 1
    return calls, pri, 0


def census(images):
    calls = {name: 0 for name in N.NATIVE_NAMES}
    levels = {name: 0 for name in N.NATIVE_NAMES}
    unknown = 0
    pri = 0
    refused = 0
    for image in images:
        one, one_pri, error = count_image(image)
        pri += one_pri
        if error:
            refused += 1
            continue
        seen = set()
        for name, count in one.items():
            if name not in calls:
                unknown += count
                continue
            calls[name] += count
            seen.add(name)
        for name in seen:
            levels[name] += 1
    return calls, levels, unknown, pri, refused


def report(calls, levels, scripts, unknown, pri, refused):
    used = [name for name in N.NATIVE_NAMES if calls[name]]
    print('scripts %d' % scripts)
    print('refused %d' % refused)
    print('sysreq_c %d' % sum(calls.values()))
    print('sysreq_pri %d' % pri)
    print('unknown_names %d' % unknown)
    print('commands_used %d' % len(used))
    print('commands_never %d' % (len(N.NATIVE_NAMES) - len(used)))
    for name in sorted(used, key=lambda item: (-calls[item], item)):
        print('%d %d %s' % (calls[name], levels[name], name))


def main(argv):
    disc = scripts = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == '--disc' and index + 1 < len(argv):
            index += 1
            disc = argv[index]
        elif arg == '--scripts' and index + 1 < len(argv):
            index += 1
            scripts = argv[index]
        else:
            print(__doc__)
            return 2
        index += 1
    if (disc is None) == (scripts is None):
        print(__doc__)
        return 2
    if disc is not None:
        images, walk_refused = script_images_from_disc(disc)
    else:
        images, walk_refused = script_images_from_dir(scripts)
    calls, levels, unknown, pri, refused = census(images)
    report(calls, levels, len(images), unknown, pri, refused + walk_refused)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
