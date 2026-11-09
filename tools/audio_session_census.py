#!/usr/bin/env python3
"""audio_session_census.py - the counts behind docs/audio-session.md 2.1, 2.2, 4.4 and 7.

Needs your own SLUS_209.73 (US v2.00), and for the level part a read-only copy of the
disc's files (the directory that holds BG/). Without the executable the script says so
and exits 0; without the disc root it skips the level part and says so.

  python3 tools/audio_session_census.py path/to/SLUS_209.73 [path/to/disc-root]

What it reads, and nothing else:
- the 90 level names of g_levelTable 0x4f7210 (0x30-byte rows) in the executable;
- for each level, the names in <LEVEL>.GOB::<level>.lmp::ntsc_dialog.bin, walked in
  0x50-byte rows until an empty name, the way game_loadLevel and the level poll walk it;
- the jal sites in the executable's code segments that call one of nine start functions,
  and the callers of the mixer set-up and volume setters;
- the stores to the process-lifetime audio words of section 7. The store scan tracks lui,
  addiu and ori per register inside each ghidra_funcs.tsv function, in listing order, and
  reports a store whose base register holds a known address. Stores through an indexed
  base (addu) or a pointer loaded from memory are not found; the caller lists cover the
  setters that write that way.

What it prints: counts, entry names (file names the game exposes) and code addresses. It
never prints or writes sample bytes, offsets, sizes or dialogue. Its output is for a log
kept under local/, not for a tracked file. Every count the document relies on is asserted
below (CHECKS); any mismatch prints FAIL and the exit status is 1.

The first lines of the output give the commit, whether the worktree was clean, and the
SHA-256 of this script and of the executable, so a retained log says what produced it.
"""
import glob
import hashlib
import os
import struct
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]

import anim_audio_info as A  # noqa: E402
import bisect  # noqa: E402

EXPECTED_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
ROOT = os.path.dirname(_HERE)

LEVEL_TABLE = 0x4F7210
LEVEL_ROW = 0x30
LEVELS = 90
DIR_ROW = 0x50
DIR_NAME = 0x40

# Start functions whose jal sites are counted (symbols/*.tsv names).
SEQUENCE_OR_SAMPLE = (
    (0x2134E8, "sound_playSample"),
    (0x214230, "sound_playOnObject"),
    (0x214428, "sound_playAtPos"),
)
MUSIC_OR_GLOBAL_STREAM = (
    (0x2110E0, "music_playGlobal"),
    (0x215F48, "music_playLevel"),
    (0x215EC8, "music_playLevelIndex"),
    (0x215C20, "stream_playGlobal"),
    (0x2160C0, "stream_playGlobalRandom"),
)
LEVEL_STREAM = ((0x215FC8, "stream_playLevel"),)   # dialog lines, startAudio, cutscene keys

# The values docs/audio-session.md states. Each is checked against what was counted.
CHECKS = {
    "levels": 90,
    "levels with exactly one mx_ row": 88,
    "levels with no mx_ row": ["innovat2", "storm1"],
    "levels with a level track": 88,
    "distinct level tracks": 54,
    "distinct ambience entries": 20,
    "levels without a level track": ["innovat2", "storm1"],
    "levels without an ambience entry": ["fay2", "innovat2"],
    "rows of storm1": 24,
    "rows of innovat2": 0,
    "levels with an enttag name": 0,
    "levels whose chosen track occurs more than once": 0,
    "levels whose chosen ambience occurs more than once": 0,
    "tracks not of the form mx_env_*_l.vag": 0,
    "ambience entries not of the form amb_*_l.vag": 0,
    "jal sites, sequence/sample starts": 406,
    "jal sites, music and global stream starts": 18,
    "jal sites, sequence/sample/music/global stream starts": 424,
    "jal sites, stream_playLevel": 5,
}

# Process-lifetime words of section 7: (address, size, name) -> expected store sites.
STORE_TARGETS = (
    (0x50608C, 4, "g_ambientCountdown", (0x321878, 0x322560, 0x3225A8, 0x322DB4)),
    (0x4F894C, 4, "duck scalar", (0x2125A0, 0x2125A4, 0x2125D8, 0x2125DC, 0x212608)),
    (0x4F8A0C, 4, "duck target", (0x212540, 0x21256C, 0x212570, 0x216584)),
    (0x4F8A18, 12, "channel floats", (0x214D00,)),
    (0x44FA7C, 4, "pause preview timer", (0x18D7AC, 0x18D7C8)),
    (0x4F7030, 4, "front-end preview timer", (0x1E10C4, 0x1E10F0)),
    (0x4F8950, 4, "sequence generation counter", (0x2143D8, 0x214594)),
)
# Functions that nothing references: no jal or j to them and no data word holding their address.
UNREFERENCED = ((0x321870, "mainloop_setAmbientCountdown"),)
# Callee -> expected jal sites.
CALLER_TARGETS = (
    (0x212F08, "sound_init", (0x19D73C,)),
    (0x212B28, "sound_allocStreamBuffers", (0x2130A0,)),
    (0x212500, "music_updateDucking", (0x212690,)),
    (0x216570, "music_setDuck", (0x2300DC,)),
    (0x216690, "audio_setChannelVolume", (0x199270, 0x211130, 0x21264C, 0x21286C, 0x215EB0,
                                          0x215F18, 0x215F98)),
)

FAILS = 0


def say(kind, name, detail):
    global FAILS
    if kind == "FAIL":
        FAILS += 1
    print("%s  %s  %s" % (kind, name, detail), flush=True)


def check(name, got):
    want = CHECKS[name]
    say("PASS" if got == want else "FAIL", name, "%r (expected %r)" % (got, want))


def sha256(path):
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def git(*args):
    try:
        return subprocess.run(("git", "-C", ROOT) + args, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class Image:
    """The PT_LOAD segments of the ELF, with their execute flag."""

    def __init__(self, path):
        with open(path, "rb") as source:
            data = source.read()
        if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
            raise ValueError("not a 32-bit little-endian ELF")
        phoff, = struct.unpack_from("<I", data, 28)
        phentsize, phnum = struct.unpack_from("<HH", data, 42)
        self.segments = []
        for index in range(phnum):
            kind, offset, vaddr, _paddr, filesz, _memsz, flags = struct.unpack_from(
                "<7I", data, phoff + index * phentsize)
            if kind == 1:
                self.segments.append((vaddr, data[offset:offset + filesz], bool(flags & 1)))

    def read(self, addr, n):
        for vaddr, blob, _x in self.segments:
            if vaddr <= addr and addr + n <= vaddr + len(blob):
                return blob[addr - vaddr:addr - vaddr + n]
        raise KeyError("0x%x is not in a loaded segment" % addr)

    def u32(self, addr):
        return struct.unpack("<I", self.read(addr, 4))[0]

    def cstr(self, addr, limit=64):
        return self.read(addr, limit).split(b"\0")[0].decode("latin-1")

    def code_words(self):
        for vaddr, blob, executable in self.segments:
            if executable:
                for off in range(0, len(blob) - 3, 4):
                    yield vaddr + off, struct.unpack_from("<I", blob, off)[0]


def directory_names(data):
    names = []
    for off in range(0, len(data) - DIR_ROW + 1, DIR_ROW):
        name = data[off:off + DIR_NAME].split(b"\0")[0].decode("latin-1")
        if not name:
            break
        names.append(name)
    return names


def level_census(image, disc):
    levels = [image.cstr(image.u32(LEVEL_TABLE + LEVEL_ROW * i), 32) for i in range(LEVELS)]
    gobs = {os.path.basename(p).upper(): p
            for p in glob.glob(os.path.join(disc, "BG", "**", "*.GOB"), recursive=True)}
    rows = []
    for level in levels:
        gob = gobs.get(level.upper() + ".GOB")
        if gob is None:
            raise SystemExit("FAIL  no %s.GOB under %s/BG" % (level.upper(), disc))
        blob = A.open_source("%s::%s.lmp::ntsc_dialog.bin" % (gob, level))
        names = directory_names(blob.bytes())
        track = next((n for n in names if "_env_" in n or "mx_theme" in n), None)
        amb = next((n for n in names if "amb_" in n), None)
        rows.append(dict(level=level, rows=len(names), track=track, amb=amb,
                         mx=sum(1 for n in names if n.startswith("mx_")),
                         enttag=sum(1 for n in names if "enttag" in n),
                         track_count=names.count(track) if track else 0,
                         amb_count=names.count(amb) if amb else 0))
    return rows


def jal_census(image):
    targets = {addr: name for addr, name in SEQUENCE_OR_SAMPLE + MUSIC_OR_GLOBAL_STREAM + LEVEL_STREAM}
    counts = {name: 0 for name in targets.values()}
    for _pc, word in image.code_words():
        if word >> 26 == 3:
            name = targets.get((word & 0x3FFFFFF) << 2)
            if name:
                counts[name] += 1
    return counts


def functions(image):
    """(sorted function starts, {address: name}) from ghidra_funcs.tsv, symbols/*.tsv and
    names.tsv. A named address inside a code segment also counts as a function start
    (mainloop_setAmbientCountdown 0x321870 is not in ghidra_funcs.tsv)."""
    starts = []
    with open(os.path.join(ROOT, "ghidra_funcs.tsv"), encoding="utf-8") as source:
        for line in source:
            if line.strip() and not line.startswith("#"):
                starts.append(int(line.split("\t")[0], 16))
    names = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "symbols", "*.tsv"))) + [os.path.join(ROOT, "names.tsv")]:
        with open(path, encoding="utf-8") as source:
            for line in source:
                field = line.rstrip("\n").split("\t")
                try:
                    names.setdefault(int(field[0], 16), field[1].strip())
                except (ValueError, IndexError):
                    pass
    code = [(vaddr, vaddr + len(blob)) for vaddr, blob, executable in image.segments if executable]
    starts = set(starts) | {a for a in names if any(lo <= a < hi for lo, hi in code) and a % 4 == 0}
    return sorted(starts), names


def owner(starts, names, pc):
    i = bisect.bisect_right(starts, pc) - 1
    start = starts[i] if i >= 0 else 0
    return names.get(start, "0x%x" % start)


def _sx(v):
    return v - 0x10000 if v & 0x8000 else v


STORE_OPS = {0x28: 1, 0x29: 2, 0x2A: 4, 0x2B: 4, 0x2C: 8, 0x2D: 8, 0x2E: 4, 0x39: 4, 0x3D: 8,
             0x3F: 8, 0x1F: 16}
# I-type opcodes whose rt is a general register that is overwritten
WRITES_RT = {0x08, 0x0A, 0x0B, 0x0C, 0x0E, 0x18, 0x19, 0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22,
             0x23, 0x24, 0x25, 0x26, 0x27, 0x37}


def store_census(image, starts):
    """{target address: [store sites]} for the STORE_TARGETS windows."""
    first = set(starts)
    found = {t[0]: [] for t in STORE_TARGETS}
    known = {}
    for pc, w in image.code_words():
        if pc in first:
            known = {}
        op, rs, rt, rd, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
        if op in STORE_OPS and rs in known:
            addr = (known[rs] + _sx(imm)) & 0xFFFFFFFF
            for base, size, _name, _want in STORE_TARGETS:
                if base <= addr < base + size:
                    found[base].append(pc)
        if op == 0x0F:
            known[rt] = imm << 16
        elif op in (0x09, 0x0D):
            if rs in known:
                known[rt] = ((known[rs] + _sx(imm)) if op == 0x09 else (known[rs] | imm)) & 0xFFFFFFFF
            else:
                known.pop(rt, None)
        elif op in WRITES_RT:
            known.pop(rt, None)
        elif op == 0 and rd:
            known.pop(rd, None)
    return found


def caller_census(image):
    want = {t[0]: [] for t in CALLER_TARGETS}
    for pc, w in image.code_words():
        if w >> 26 == 3:
            target = (w & 0x3FFFFFF) << 2
            if target in want:
                want[target].append(pc)
    return want


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not os.path.isfile(argv[0]):
        print("SKIP  pass the SLUS_209.73 path (and the disc root that holds BG/); nothing was counted")
        return 0
    elf = argv[0]
    disc = argv[1] if len(argv) > 1 else None
    digest = sha256(elf)
    if digest != EXPECTED_SHA256:
        print("SKIP  %s is not the US v2.00 executable; nothing was counted" % os.path.basename(elf))
        return 0
    status = git("status", "--porcelain", "--untracked-files=no")
    print("commit %s, tracked files %s" % (git("rev-parse", "HEAD") or "unknown",
                                           "clean" if not status else "MODIFIED"))
    print("tool tools/audio_session_census.py sha256 %s" % sha256(os.path.abspath(__file__)))
    print("executable sha256 %s" % digest)
    image = Image(elf)
    if disc and os.path.isdir(os.path.join(disc, "BG")):
        level_part(image, disc)
    else:
        print("SKIP  level directories: no disc root with BG/ given")
    executable_part(image)
    print("%d FAIL" % FAILS)
    return 1 if FAILS else 0


def level_part(image, disc):
    rows = level_census(image, disc)
    print("per level: level, directory rows, level track, ambience entry")
    for r in rows:
        print("  %-10s %3d  %-28s %s" % (r["level"], r["rows"], r["track"] or "-", r["amb"] or "-"))
    tracks = {}
    for r in rows:
        if r["track"]:
            tracks.setdefault(r["track"], []).append(r["level"])
    print("per level track: track, levels")
    for track in sorted(tracks):
        print("  %-28s %s" % (track, " ".join(tracks[track])))

    check("levels", len(rows))
    check("levels with exactly one mx_ row", sum(1 for r in rows if r["mx"] == 1))
    check("levels with no mx_ row", sorted(r["level"] for r in rows if r["mx"] == 0))
    check("levels with a level track", sum(1 for r in rows if r["track"]))
    check("distinct level tracks", len(tracks))
    check("distinct ambience entries", len({r["amb"] for r in rows if r["amb"]}))
    check("levels without a level track", sorted(r["level"] for r in rows if not r["track"]))
    check("levels without an ambience entry", sorted(r["level"] for r in rows if not r["amb"]))
    by_level = {r["level"]: r for r in rows}
    check("rows of storm1", by_level["storm1"]["rows"])
    check("rows of innovat2", by_level["innovat2"]["rows"])
    check("levels with an enttag name", sum(1 for r in rows if r["enttag"]))
    check("levels whose chosen track occurs more than once", sum(1 for r in rows if r["track_count"] > 1))
    check("levels whose chosen ambience occurs more than once", sum(1 for r in rows if r["amb_count"] > 1))
    check("tracks not of the form mx_env_*_l.vag",
          sum(1 for t in tracks if not (t.startswith("mx_env_") and t.endswith("_l.vag"))))
    check("ambience entries not of the form amb_*_l.vag",
          sum(1 for r in rows if r["amb"] and not (r["amb"].startswith("amb_") and r["amb"].endswith("_l.vag"))))



def executable_part(image):
    counts = jal_census(image)
    print("jal sites per start function (code segments of the executable):")
    for addr, name in SEQUENCE_OR_SAMPLE + MUSIC_OR_GLOBAL_STREAM + LEVEL_STREAM:
        print("  0x%06x %-24s %d" % (addr, name, counts[name]))
    seq = sum(counts[n] for _a, n in SEQUENCE_OR_SAMPLE)
    music = sum(counts[n] for _a, n in MUSIC_OR_GLOBAL_STREAM)
    check("jal sites, sequence/sample starts", seq)
    check("jal sites, music and global stream starts", music)
    check("jal sites, sequence/sample/music/global stream starts", seq + music)
    check("jal sites, stream_playLevel", counts["stream_playLevel"])

    starts, names = functions(image)
    stores = store_census(image, starts)
    print("stores to the process-lifetime words (lui/addiu/ori bases):")
    for base, size, name, want in STORE_TARGETS:
        got = stores[base]
        detail = ", ".join("0x%x %s" % (pc, owner(starts, names, pc)) for pc in got)
        say("PASS" if tuple(got) == want else "FAIL", "stores to 0x%x %s" % (base, name),
            "%d: %s" % (len(got), detail or "none"))
    for target, name in UNREFERENCED:
        jumps = [pc for pc, w in image.code_words() if w >> 26 in (2, 3) and (w & 0x3FFFFFF) << 2 == target]
        words = [vaddr + off for vaddr, blob, _x in image.segments
                 for off in range(0, len(blob) - 3, 4) if struct.unpack_from("<I", blob, off)[0] == target]
        say("PASS" if not jumps and not words else "FAIL", "references to 0x%x %s" % (target, name),
            "%d jal/j sites, %d data words" % (len(jumps), len(words)))
    callers = caller_census(image)
    print("jal callers:")
    for target, name, want in CALLER_TARGETS:
        got = callers[target]
        detail = ", ".join("0x%x %s" % (pc, owner(starts, names, pc)) for pc in got)
        say("PASS" if tuple(got) == want else "FAIL", "callers of 0x%x %s" % (target, name),
            "%d: %s" % (len(got), detail or "none"))


if __name__ == "__main__":
    sys.exit(main())
