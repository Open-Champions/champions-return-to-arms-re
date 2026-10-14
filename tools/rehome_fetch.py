#!/usr/bin/env python3
"""rehome_fetch.py OLD NEW LOG - bring across what iCloud has given back, and nothing else.

  python3 tools/rehome_fetch.py ~/Desktop/champions-re-icloud-old ~/champions-re local/rehome/fetch.log

For every file of OLD that is on this disk and that NEW does NOT have, an APFS clone is
made in NEW (no data is copied).  A file NEW already has is NEVER touched, whatever OLD
holds: work goes on in NEW, and its files are the newer ones (the first tool of the move
replaced them when size or time differed - right on the day of the move, destructive on
any later run; docs/issues/workspace-move.md).  A file or directory iCloud has evicted
("dataless") is never opened: it is listed in LOG.missing when NEW lacks it.  Names, sizes
and flags only (lstat); symbolic links are copied as links.  Not brought across, as on the
day of the move: OLD/.git (NEW has its own) and the directories of SKIP.
Prints the counts; LOG.fetched lists what was brought across.
"""
import ctypes
import os
import stat
import sys

SF_DATALESS = 0x40000000
SKIP = ('.git', os.path.join('local', 'hd-pack', 'replace.old.nosync'))     # relative to OLD


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    old, new, log = (os.path.abspath(os.path.expanduser(a)) for a in sys.argv[1:4])
    libc = ctypes.CDLL(None, use_errno=True)
    libc.clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    n = dict(fetched=0, kept=0, links=0, missing=0, missing_dirs=0, errors=0)
    with open(log + '.missing', 'w') as missing, open(log + '.fetched', 'w') as fetched, open(log + '.errors', 'w') as errors:
        stack = [old]
        while stack:
            sdir = stack.pop()
            ddir = os.path.join(new, os.path.relpath(sdir, old)) if sdir != old else new
            try:
                if os.lstat(sdir).st_flags & SF_DATALESS:
                    n['missing_dirs'] += 1
                    missing.write('DIR\t%s\n' % sdir)
                    continue
                with os.scandir(sdir) as it:
                    entries = list(it)
            except OSError as e:
                n['errors'] += 1
                errors.write('%s\t%s\n' % (sdir, e))
                continue
            for entry in entries:
                s, d = entry.path, os.path.join(ddir, entry.name)
                try:
                    st = os.lstat(s)
                    if stat.S_ISDIR(st.st_mode):
                        if os.path.relpath(s, old) not in SKIP:
                            stack.append(s)
                    elif os.path.lexists(d):
                        n['kept'] += 1                      # NEW has it: never replaced
                    elif stat.S_ISLNK(st.st_mode):
                        os.makedirs(ddir, exist_ok=True)
                        os.symlink(os.readlink(s), d)
                        n['links'] += 1
                    elif stat.S_ISREG(st.st_mode):
                        if st.st_flags & SF_DATALESS:
                            n['missing'] += 1
                            missing.write('FILE\t%s\n' % s)
                            continue
                        os.makedirs(ddir, exist_ok=True)
                        if libc.clonefile(s.encode(), d.encode(), 0) != 0:
                            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
                        n['fetched'] += 1
                        fetched.write(s + '\n')
                except OSError as e:
                    n['errors'] += 1
                    errors.write('%s\t%s\n' % (s, e))
    print('done %r' % n)
    print('%d files and %d directories are still evicted and not in %s' % (n['missing'], n['missing_dirs'], new))
    return 0


if __name__ == '__main__':
    sys.exit(main())
