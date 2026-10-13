"""genfiles.py - which files a translation consists of.

recomp.py writes a translation into a directory as c_000.cpp, c_001.cpp, ... (numbered
without a gap), table.cpp, hle_weak.cpp and, when a fix set was given, patches.cpp, and
removes what an earlier translation left there.  The build scripts ask here for that list
instead of listing the directory: a directory under a file synchroniser gains copies such
as "c_003 2.cpp" and "c_003 2.o", and a copy that is compiled or linked as one more file
of the game gives every symbol twice.
"""
import os

FIXED = ('hle_weak.cpp', 'patches.cpp', 'table.cpp')


def sources(gen):
    """The translation's .cpp file names, in the order a sorted listing would give them."""
    names = []
    while os.path.isfile(os.path.join(gen, 'c_%03d.cpp' % len(names))):
        names.append('c_%03d.cpp' % len(names))
    return names + [n for n in FIXED if os.path.isfile(os.path.join(gen, n))]


def objects(gen, objdir, prefix=''):
    """The objects of that translation in objdir (named as build.py names them: prefix + c_000.o ...)."""
    return [os.path.join(objdir, prefix + n[:-4] + '.o') for n in sources(gen)]
