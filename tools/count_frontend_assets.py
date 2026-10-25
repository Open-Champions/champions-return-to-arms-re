#!/usr/bin/env python3
"""Count related .tex/.fnt entries in private BG/DATA lumps, without outputting bytes.

Usage: python3 tools/count_frontend_assets.py /private/disc/BG/DATA
"""
import sys
from pathlib import Path

from anim_audio_info import lmp_entries


LUMPS = ("SOELOGO", "FRONTEND", "INTERFAC", "SELECT", "SELECT2",
         "SAVEPNT", "SAVEPNT2", "FONT", "PVPFONT", "PFONT",
         "PPVPFONT", "PORKO", "CREDITS", "HEADPIC")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: count_frontend_assets.py path/to/BG/DATA")
    root = Path(args[0])
    total_tex = total_fnt = 0
    for stem in LUMPS:
        entries = lmp_entries((root / (stem + ".LMP")).read_bytes())
        tex = sum(name.lower().endswith(".tex") for name, _, _ in entries)
        fnt = sum(name.lower().endswith(".fnt") for name, _, _ in entries)
        total_tex += tex
        total_fnt += fnt
        print("%s tex=%d fnt=%d" % (stem, tex, fnt))
    print("TOTAL tex=%d fnt=%d" % (total_tex, total_fnt))


if __name__ == "__main__":
    main()
