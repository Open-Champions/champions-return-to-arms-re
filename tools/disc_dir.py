"""Let the arena probe readers use an extracted disc directory instead of an image.

    import disc_dir; disc_dir.install(probe_arena_match_module)

After install, ``recipe0_world_from_disc(path)`` and the clip/model readers accept
either an image (unchanged path) or a directory holding the disc's files (``BG/DATA``).
Files are read in memory only; nothing is written.  This changes no reference API.
"""
import os


class _Closed(object):
    def close(self):
        pass


class DirDisc(object):
    def __init__(self, root):
        self.root = root
        self.f = _Closed()


def install(probe):
    original_iso = probe.Disc.Iso
    original_file = probe.disc_file

    def iso(path):
        return DirDisc(path) if os.path.isdir(path) else original_iso(path)

    def disc_file(disc, name):
        if isinstance(disc, DirDisc):
            target = os.path.join(disc.root, *name.split('/'))
            if not os.path.isfile(target):
                raise ValueError('%s absent from disc directory' % name)
            with open(target, 'rb') as handle:
                return handle.read()
        return original_file(disc, name)

    probe.Disc.Iso = iso
    probe.disc_file = disc_file
