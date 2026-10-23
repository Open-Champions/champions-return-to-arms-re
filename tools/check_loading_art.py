#!/usr/bin/env python3
"""Read-only loading-art census for the operator's RTA v2.00 ISO.

Usage: PYTHONDONTWRITEBYTECODE=1 python3 tools/check_loading_art.py --iso IMAGE
Prints aggregate counts and texture header dimensions only; no asset bytes.
"""
import argparse
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "recomp"))
from disc import Iso  # noqa: E402
from gob import lmp_entries  # noqa: E402
from ref_loading import picture_lump  # noqa: E402

EXPECTED = {
    "scrollbar.tex": (640, 128),
    "scrollbar2.tex": (640, 96),
    "scrollbar3.tex": (640, 96),
    "titleload.tex": (184, 78),
    "titleloadsp.tex": (216, 72),
    "titleloadit.tex": (382, 90),
    "titleloadfr.tex": (244, 70),
    "titleloadgr.tex": (160, 72),
}


def headers(iso, record):
    iso.f.seek(record["lba"] * 2048)
    data = iso.f.read(record["size"])
    return {name.lower(): struct.unpack_from("<HH", data, offset)
            for name, offset, _size in lmp_entries(data)
            if name.lower().endswith(".tex")}


def main(image):
    iso = Iso(image)
    try:
        entries = {name.upper(): record for name, record in iso.walk()}
        gobs = [name.split("/")[-1][:-4].lower() for name in entries
                if name.startswith("BG/DATA/") and name.endswith(".GOB")]
        lumps = {name.split("/")[-1] for name in entries
                 if name.startswith("BG/DATA/L") and name.endswith(".LMP")}
        selected = [picture_lump(name, lumps) for name in gobs]
        shots = Counter()
        for lump in lumps:
            dimensions = headers(iso, entries["BG/DATA/" + lump])
            if "shot.tex" in dimensions:
                shots[dimensions["shot.tex"]] += 1
        misc = headers(iso, entries["BG/DATA/LOADMISC.LMP"])
        assert len(gobs) == 120, len(gobs)
        assert selected.count("lmiss.lmp") == 18
        assert len(set(selected)) == 91
        assert shots == {(640, 320): 97}, shots
        assert all(misc.get(name) == size for name, size in EXPECTED.items()), misc
        assert all(headers(iso, entries["BG/DATA/" + name])["shot.tex"] == (640, 320)
                   for name in ("LBLOOD1.LMP", "LHUB.LMP", "LINTRO.LMP", "LMISS.LMP"))
        print("PASS archives=120 fallback=18 distinct_selected=91 shot_headers=97")
        print("PASS misc_headers=8 representative_shot_headers=4")
    finally:
        iso.f.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True)
    main(parser.parse_args().iso)
