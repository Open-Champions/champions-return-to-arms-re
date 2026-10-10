#!/usr/bin/env python3
"""Structure dump for the animation and audio files of Champions: Return to Arms (PS2).

Reads files you extracted from your own disc (or the disc image itself) and prints their
layout. It can also decode a sound to WAV and dump an animation's bone tracks to CSV.
Standard library only. Formats are described in docs/formats/anim-audio.md.

  python3 -I -B tools/anim_audio_info.py info SOURCE [--events] [--keys N] [--dir SOURCE --entry NAME]
  python3 -I -B tools/anim_audio_info.py list CONTAINER
  python3 -I -B tools/anim_audio_info.py csv  SOURCE OUT.csv [--keys] [--step TICKS] [--dir SOURCE --entry NAME]
  python3 -I -B tools/anim_audio_info.py wav  SOURCE OUT.wav [--dir SOURCE --entry NAME]
                                              [--raw mono|stereo] [--rate HZ] [--bd FILE --index N]
  python3 -I -B tools/anim_audio_info.py scan PATH [PATH ...] [--quiet]

SOURCE is a file, or a path into containers written with "::" between the steps:

  1_walk.anm                                         a loose file
  SKELETON.LMP::1_walk.anm                           an entry of a lump
  DRUNARE.GOB::drunare.lmp::ntsc_dialog.bin          a lump inside a .GOB, then an entry
  game.iso::/BG/DATA/SKELETON.LMP::1_walk.anm        straight from a disc image

What it understands (by entry name and content):
  *.anm              skeletal animation / sound sequence
  *.vag in a lump    one ADPCM sample with a 0x30-byte header
  *dialog.bin        the directory of a .VAT stream file (not dialog text)
  *.vat, *.va1, headerless *.vag   raw ADPCM stream data (needs --dir or --raw to decode)
  *.dbin             dialog nodes (cutscene lines, NPC conversations)
  ambient.bin        text schedule of ambient stream one-shots
  *.hd (+ .bd)       Sony IECS sample bank of the network setup program

Stream files (.VAT) have no header; name an entry through the directory:
  ... wav  DRUNARE.VAT out.wav --dir DRUNARE.GOB::drunare.lmp::ntsc_dialog.bin --entry NAME.vag
  ... info DRUNARE.VAT --dir DRUNARE.GOB::drunare.lmp::ntsc_dialog.bin --entry NAME.anm
  ... wav  PORKO.VAG out.wav --raw stereo

Anything else, and any file that fails a structural check, is reported as an error
(exit status 2); nothing is guessed.
"""
import argparse
import csv
import math
import mmap
import os
import re
import struct
import sys
import wave

TICKS_PER_SECOND = 60          # animation time unit
ANM_HEADER_SIZE = 0x70
ANM_MAX_JOINTS = 64            # decoder slot and pose buffer capacity in the game
STREAM_RATE_NOMINAL = 24000    # directory value for nearly every entry
STREAM_PITCH = 0x7fe           # what the sound driver programs for every stream voice
STREAM_RATE_CONSOLE = 48000.0 * STREAM_PITCH / 4096.0
STREAM_CHUNK = 0x400           # bytes of one channel in an interleaved stereo stream
DIR_ENTRY_SIZE = 0x50
DBIN_NODE_SIZE = 0x448
DBIN_CHOICE_SIZE = 0x54
DBIN_MAX_CHOICES = 12


class FormatError(Exception):
    """The file is not something this tool understands, or it failed a structural check."""


# --------------------------------------------------------------------------- containers

def _cstr(b):
    return b.split(b"\0", 1)[0].decode("latin1")


def iso_files(m):
    """{upper-case path: (offset, size)} for an ISO9660 image."""
    pvd = 16 * 2048
    if len(m) < pvd + 2048 or m[pvd + 1:pvd + 6] != b"CD001":
        raise FormatError("not an ISO9660 image")
    root = m[pvd + 156:pvd + 190]
    stack = [("", struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0])]
    out = {}
    while stack:
        path, lba, size = stack.pop()
        data = m[lba * 2048:lba * 2048 + size]
        i = 0
        while i < len(data):
            n = data[i]
            if n == 0:
                i = (i // 2048 + 1) * 2048
                continue
            rec = data[i:i + n]
            e_lba, e_size = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
            flags, nlen = rec[25], rec[32]
            name = rec[33:33 + nlen]
            i += n
            if name in (b"\x00", b"\x01"):
                continue
            full = path + "/" + name.decode("latin1").split(";")[0]
            if flags & 2:
                stack.append((full, e_lba, e_size))
            else:
                out[full.upper()] = (e_lba * 2048, e_size, full)
    return out


def gob_entries(d):
    out, i = [], 0
    while i + 40 <= len(d) and d[i] != 0:
        name = _cstr(d[i:i + 32])
        off, size = struct.unpack_from("<II", d, i + 32)
        if off + size > len(d):
            raise FormatError("GOB record %r points outside the file" % name)
        out.append((name, off, size))
        i += 40
    if not out:
        raise FormatError("empty or malformed GOB")
    return out


def lmp_entries(d):
    if len(d) < 4:
        raise FormatError("lump too short")
    n, = struct.unpack_from("<I", d, 0)
    if n > 0x4000 or 4 + n * 12 > len(d):
        raise FormatError("not a lump (entry count %d)" % n)
    out = []
    for i in range(n):
        no, do, ds = struct.unpack_from("<III", d, 4 + i * 12)
        if no >= len(d) or do + ds > len(d):
            raise FormatError("lump record %d points outside the file" % i)
        end = d.find(b"\0", no, no + 64)
        if end < 0:
            raise FormatError("lump record %d has no name" % i)
        out.append((d[no:end].decode("latin1"), do, ds))
    return out


def container_kind(name):
    n = name.lower()
    if n.endswith(".iso"):
        return "iso"
    if n.endswith(".gob"):
        return "gob"
    if n.endswith(".lmp"):
        return "lmp"
    return None


class Blob:
    """A named byte range of an open file (mmap), so big images are never copied whole."""

    def __init__(self, name, buf, off, size):
        self.name, self.buf, self.off, self.size = name, buf, off, size

    def bytes(self):
        return bytes(self.buf[self.off:self.off + self.size])

    def read(self, off, n):
        off = max(0, off)
        n = max(0, min(n, self.size - off))
        return bytes(self.buf[self.off + off:self.off + off + n])

    def sub(self, name, off, size):
        return Blob(name, self.buf, self.off + off, size)

    def children(self):
        """[(name, Blob)] if this blob is a container, else None."""
        kind = container_kind(self.name)
        if kind == "iso":
            return [(v[2], self.sub(v[2], v[0], v[1])) for v in iso_files(self.buf).values()]
        if kind == "gob":
            return [(n, self.sub(n, o, s)) for n, o, s in gob_entries(self.bytes())]
        if kind == "lmp":
            return [(n, self.sub(n, o, s)) for n, o, s in lmp_entries(self.bytes())]
        return None


_open_files = []


def open_path(path):
    if not os.path.isfile(path):
        raise FormatError("no such file: %s" % path)
    size = os.path.getsize(path)
    f = open(path, "rb")
    _open_files.append(f)
    if size == 0:
        return Blob(os.path.basename(path), b"", 0, 0)
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    return Blob(os.path.basename(path), m, 0, size)


def open_source(spec):
    """Resolve 'file::entry::entry' to a Blob."""
    parts = spec.split("::")
    blob = open_path(parts[0])
    for step in parts[1:]:
        kids = blob.children()
        if kids is None:
            raise FormatError("%s is not a container (.iso, .gob, .lmp)" % blob.name)
        want = step.lower()
        hit = [b for n, b in kids if n.lower() == want]
        if not hit:  # be forgiving about a leading slash and directories inside an image
            hit = [b for n, b in kids if n.lower().rsplit("/", 1)[-1] == want.rsplit("/", 1)[-1]]
        if not hit:
            raise FormatError("no entry %r in %s" % (step, blob.name))
        blob = hit[0]
        blob.name = blob.name.rsplit("/", 1)[-1]
    return blob


# --------------------------------------------------------------------------- .anm

class BitReader:
    """The key stream: 16-bit little-endian words, bits taken from the top of each word."""

    def __init__(self, data, base, limit):
        self.d, self.base, self.limit, self.pos = data, base, limit, 0

    def _need(self, pos, n):
        if self.base + ((pos + n + 15) >> 4) * 2 > self.limit:
            raise FormatError("key stream runs past its section (bit %d)" % pos)

    def peek(self, n, signed=False, at=None):
        pos = self.pos if at is None else at
        self._need(pos, n)
        i = self.base + (pos >> 4) * 2
        hi = self.d[i] | self.d[i + 1] << 8
        lo = (self.d[i + 2] | self.d[i + 3] << 8) if i + 4 <= len(self.d) else 0
        w = (((hi << 16) | lo) << (pos & 15)) & 0xffffffff
        v = w >> (32 - n)
        if signed and v >> (n - 1):
            v -= 1 << n
        return v

    def get(self, n, signed=False):
        v = self.peek(n, signed)
        self.pos += n
        return v


class Anm:
    def __init__(self, data, name="?"):
        self.name = name
        d = self.d = data
        if len(d) < ANM_HEADER_SIZE:
            raise FormatError("too short for an .anm header (%d bytes)" % len(d))
        (self.joints, self.length, self.keys_off, self.bind_off,
         self.depth_off) = struct.unpack_from("<5I", d, 0)
        if self.joints > ANM_MAX_JOINTS:
            raise FormatError("joint count %d outside 0..%d" % (self.joints, ANM_MAX_JOINTS))
        if self.length > 0x100000:
            raise FormatError("implausible length %d ticks" % self.length)
        n = self.joints
        for what, off, size in (("key stream", self.keys_off, 4), ("bind offsets", self.bind_off, n * 8),
                                ("depth list", self.depth_off, n)):
            if off < ANM_HEADER_SIZE or off + size > len(d):
                raise FormatError("%s offset 0x%x outside the file" % (what, off))
        self.events = []
        for i in range(4):
            sec, mask = struct.unpack_from("<fB", d, 0x14 + i * 8)
            if not (sec == sec and -1.0 <= sec < 3600.0):
                raise FormatError("event slot %d has an implausible time" % i)
            self.events.append((sec, mask))
        self.names_off, self.sevents_off = struct.unpack_from("<II", d, 0x34)
        self.sound_group, self.sound_version = d[0x3c], d[0x3d]
        self.joint_mask, = struct.unpack_from("<Q", d, 0x48)
        self.unknown_nonzero = [o for o in list(range(0x3e, 0x48)) + list(range(0x50, 0x70)) if d[o]]
        # skeleton
        self.depth = list(d[self.depth_off:self.depth_off + n])
        if n and self.depth[0] != 0:
            raise FormatError("first joint has depth %d, expected 0" % self.depth[0])
        self.parent = []
        last_at_depth = {}
        for j, dep in enumerate(self.depth):
            if j and dep > self.depth[j - 1] + 1:
                raise FormatError("joint %d jumps from depth %d to %d" % (j, self.depth[j - 1], dep))
            self.parent.append(last_at_depth.get(dep - 1, -1))
            last_at_depth[dep] = j
        self.bind = [tuple(v / 64.0 for v in struct.unpack_from("<3h", d, self.bind_off + j * 8))
                     for j in range(n)]
        self.bind_pad = [struct.unpack_from("<h", d, self.bind_off + j * 8 + 6)[0] for j in range(n)]
        self._parse_sounds()
        self._parse_keys()

    # sound name table and sound events
    def _parse_sounds(self):
        d = self.d
        self.sound_names, self.sound_events = [], []
        if self.names_off:
            o = self.names_off
            while True:
                if o + 4 > len(d):
                    raise FormatError("sound name table is not terminated")
                p, = struct.unpack_from("<I", d, o)
                if p == 0:
                    break
                if p >= len(d) or o + 8 > len(d):
                    raise FormatError("sound name pointer 0x%x outside the file" % p)
                end = d.find(b"\0", p, p + 80)
                if end < 0:
                    raise FormatError("sound name at 0x%x is not terminated" % p)
                self.sound_names.append(d[p:end].decode("latin1"))
                o += 8
                if len(self.sound_names) > 4096:
                    raise FormatError("sound name table too long")
        if self.sevents_off:
            o = self.sevents_off
            while True:
                if o + 4 > len(d):
                    raise FormatError("sound event list is not terminated")
                t, = struct.unpack_from("<i", d, o)
                if t == 0x7fffffff:
                    break
                if o + 0x1c > len(d):
                    raise FormatError("sound event list is cut short")
                idx, = struct.unpack_from("<h", d, o + 4)
                grp, _, pitch, pitch_j, vol, vol_j, delay_j = struct.unpack_from("<7b", d, o + 8)
                rest = d[o + 6:o + 8] + d[o + 9:o + 10] + d[o + 0xf:o + 0x1c]
                if idx >= len(self.sound_names) and self.sound_version >= 2:
                    raise FormatError("sound event uses name %d of %d" % (idx, len(self.sound_names)))
                self.sound_events.append(dict(tick=t, sound=idx, select=grp, pitch=pitch, pitch_jitter=pitch_j,
                                              volume=vol, volume_jitter=vol_j, delay_jitter=delay_j,
                                              other_nonzero=any(rest)))
                o += 0x1c
                if len(self.sound_events) > 4096:
                    raise FormatError("sound event list too long")

    # initial pose and key records
    def _parse_keys(self):
        d = self.d
        limit = len(d)
        for off in (self.bind_off, self.depth_off, self.names_off, self.sevents_off):
            if self.keys_off < off < limit:
                limit = off
        # Files with sound tables carry a 0x28-byte block in front of the name table whose first
        # two words are the table offsets relative to the block; the key stream ends there.
        self.sound_block_off = 0
        if self.names_off and self.names_off - 0x28 >= self.keys_off:
            blk = self.names_off - 0x28
            rel_names, rel_events = struct.unpack_from("<II", d, blk)
            if rel_names == 0x28 and blk + rel_events == self.sevents_off:
                self.sound_block_off = blk
                limit = min(limit, blk)
        r = BitReader(d, self.keys_off, limit)
        self.init_pos, self.init_rot, self.init_widths = [], [], []
        for _ in range(self.joints):
            w = r.get(4) + 1
            p = [r.get(w, True) / 64.0 for _ in range(3)]
            w2 = r.get(4) + 1
            qw, qx, qy, qz = [r.get(w2, True) / 4096.0 for _ in range(4)]
            self.init_pos.append(p)
            self.init_rot.append([qx, qy, qz, qw])
            self.init_widths.append((w, w2))
        self.keys = []          # (tick, 'P' or 'R', joint, bit width, raw integers)
        self.closing_in_clip = False
        tick = 0
        while True:
            dt = r.peek(8)
            if tick + dt > self.length:
                break               # the game never consumes a record beyond the last tick
            if dt == 255 and self._stream_ends_after(r.pos + 8, limit):
                # The stream is closed by a single delta of 255 and zero padding. When the last
                # key is more than 255 ticks before the end, that delta is inside the clip and
                # no record follows it (the game would read on into whatever comes next).
                self.closing_in_clip = True
                break
            r.pos += 8
            tick += dt
            is_pos = r.get(1)
            joint = r.get(6)
            w = r.get(4) + 1
            vals = [r.get(w, True) for _ in range(3 if is_pos else 4)]
            if joint >= max(self.joints, 1):
                raise FormatError("key at tick %d names joint %d of %d" % (tick, joint, self.joints))
            self.keys.append((tick, "P" if is_pos else "R", joint, w, vals))
            if len(self.keys) > 2000000:
                raise FormatError("key stream does not end")
        if dt != 255:
            raise FormatError("key stream is not closed by a delta of 255 (found %d at bit %d)" % (dt, r.pos))
        self.last_key_tick = tick
        self.key_bits = r.pos
        self.keys_end = self.keys_off + (((r.pos + 8 + 7) // 8 + 3) & ~3)
        self.keys_limit = limit
        # bytes the closing rule leaves unexplained; zero fill (the 0x800 padding of a clip stored
        # in a stream file) does not count
        self.keys_slack = (limit - self.keys_end) if any(d[self.keys_end:limit]) or limit < self.keys_end else 0

    def _stream_ends_after(self, bit, limit):
        """True when only zero padding (to a 4-byte boundary) lies between this bit and the stream's end."""
        end = self.keys_off + (((bit + 7) // 8 + 3) & ~3)
        if end != limit:
            return False
        word = bit >> 4                 # bits are consumed from the top of 16-bit little-endian words
        at = self.keys_off + word * 2
        if at + 2 <= limit:
            if struct.unpack_from("<H", self.d, at)[0] & (0xffff >> (bit & 15)):
                return False
            at += 2
        return not any(self.d[at:limit])

    # evaluation
    def sample(self, ticks):
        """Yield (tick, [pos xyz per joint], [quat xyzw per joint]) for increasing ticks."""
        n = self.joints
        pos = [list(p) for p in self.init_pos]
        pvel = [[0.0, 0.0, 0.0] for _ in range(n)]
        ptick = [0] * n
        rot = [list(q) for q in self.init_rot]
        rvel = [[0.0, 0.0, 0.0, 0.0] for _ in range(n)]
        rtick = [0] * n
        k = 0
        for t in ticks:
            while k < len(self.keys) and self.keys[k][0] <= int(t):
                tick, kind, j, _, vals = self.keys[k]
                if kind == "P":
                    dt = tick - ptick[j]
                    for a in range(3):
                        pos[j][a] += pvel[j][a] * dt
                    pvel[j] = [v / 256.0 for v in vals]
                    ptick[j] = tick
                else:
                    dt = tick - rtick[j]
                    for a in range(4):
                        rot[j][a] += rvel[j][a] * dt
                    vw, vx, vy, vz = [v / 131072.0 for v in vals]
                    rvel[j] = [vx, vy, vz, vw]
                    rtick[j] = tick
                k += 1
            out_p, out_q = [], []
            for j in range(n):
                dp, dr = t - ptick[j], t - rtick[j]
                out_p.append([pos[j][a] + pvel[j][a] * dp for a in range(3)])
                q = [rot[j][a] + rvel[j][a] * dr for a in range(4)]
                norm = math.sqrt(sum(c * c for c in q)) or 1.0
                out_q.append([c / norm for c in q])
            yield t, out_p, out_q

    def model_positions(self, pos, rot):
        """Joint origins in model space: world[j] = world[parent] * (rotation, translation)."""
        mats = [None] * self.joints
        out = []
        for j in range(self.joints):
            x, y, z, w = rot[j]
            r = [[1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w],
                 [2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w],
                 [2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y]]
            local = [r[i] + [pos[j][i]] for i in range(3)]
            p = self.parent[j]
            if p < 0:
                m = local
            else:
                pm = mats[p]
                m = [[sum(pm[i][c] * local[c][k] for c in range(3)) for k in range(3)] +
                     [sum(pm[i][c] * local[c][3] for c in range(3)) + pm[i][3]] for i in range(3)]
            mats[j] = m
            out.append((m[0][3], m[1][3], m[2][3]))
        return out

    @staticmethod
    def yaw16(q):
        x, y, z, w = q
        a = math.atan2(2 * (x * y + z * w), x * x - y * y - z * z + w * w)
        return int(round(a * 65536 / (2 * math.pi)))

    def describe(self, out, show_events=False, show_keys=0):
        p = lambda *a: print(*a, file=out)
        secs = self.length / TICKS_PER_SECOND
        p("%s: .anm, %d bytes" % (self.name, len(self.d)))
        p("  joints %d, length %d ticks (%.3f s at %d ticks/s)" % (self.joints, self.length, secs, TICKS_PER_SECOND))
        p("  sections: depth list 0x%x, bind offsets 0x%x, key stream 0x%x..0x%x (%d bits)"
          % (self.depth_off, self.bind_off, self.keys_off, self.keys_end, self.key_bits))
        npos = sum(1 for k in self.keys if k[1] == "P")
        animated = len(set((k[1], k[2]) for k in self.keys))
        p("  keys: %d position + %d rotation records on %d of %d channels; closing delta %s"
          % (npos, len(self.keys) - npos, animated, self.joints * 2,
             "255, inside the clip (see the format notes)" if self.closing_in_clip else "255"))
        if self.keys_slack:
            p("  note: %d bytes after the key stream are not explained by the closing rule" % self.keys_slack)
        if self.joint_mask:
            off = [j for j in range(self.joints) if self.joint_mask >> j & 1]
            p("  partial-body: joint mask 0x%x (%d joints not driven)" % (self.joint_mask, len(off)))
        ev = [(s, m) for s, m in self.events if m or s]
        p("  event slots: " + (", ".join("%.3f s -> mask 0x%02x" % e for e in ev) if ev else "none used"))
        if self.joints:
            first = next(self.sample([0]))
            last = next(self.sample([self.length]))
            q_norm = [math.sqrt(sum(c * c for c in q)) for q in self.init_rot]
            p("  joint 0 travel over the clip: dx %.3f dy %.3f dz %.3f, yaw %d/65536 turn"
              % (last[1][0][0] - first[1][0][0], last[1][0][1] - first[1][0][1], last[1][0][2] - first[1][0][2],
                 (self.yaw16(last[2][0]) - self.yaw16(first[2][0]) + 32768) % 65536 - 32768))
            p("  stored quaternion length at tick 0: min %.4f max %.4f" % (min(q_norm), max(q_norm)))
        if self.unknown_nonzero:
            p("  non-zero bytes in unexplained header fields at: " + " ".join("0x%x" % o for o in self.unknown_nonzero))
        p("  skeleton (joint: depth parent, bind position = -offset):")
        for j in range(self.joints):
            b = self.bind[j]
            p("    %2d: depth %2d parent %2d  bind (%8.3f %8.3f %8.3f)"
              % (j, self.depth[j], self.parent[j], -b[0], -b[1], -b[2]))
        if self.names_off or self.sevents_off:
            p("  sound: group %d, data version %d, %d names, %d events (tables at 0x%x / 0x%x)"
              % (self.sound_group, self.sound_version, len(self.sound_names), len(self.sound_events),
                 self.names_off, self.sevents_off))
            if show_events:
                for i, nme in enumerate(self.sound_names):
                    p("    name %d: %s" % (i, nme))
                for e in self.sound_events:
                    p("    tick %5d sound %3d select %d pitch %+d (+-%d) volume %+d (+-%d) delay 0..%d ticks"
                      % (e["tick"], e["sound"], e["select"], e["pitch"], e["pitch_jitter"], e["volume"],
                         e["volume_jitter"], e["delay_jitter"]))
        else:
            p("  sound: no tables")
        for k in self.keys[:show_keys]:
            p("    key tick %4d %s joint %2d width %2d %s" % k)


def anm_csv(anm, path, raw_keys=False, step=1.0):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        if raw_keys:
            w.writerow(["tick", "kind", "joint", "bits", "a", "b", "c", "d"])
            for j in range(anm.joints):
                w.writerow([0, "P0", j, anm.init_widths[j][0]] + ["%.6f" % v for v in anm.init_pos[j]])
                w.writerow([0, "R0", j, anm.init_widths[j][1]] + ["%.6f" % v for v in anm.init_rot[j]])
            for tick, kind, joint, bits, vals in anm.keys:
                scale = 256.0 if kind == "P" else 131072.0
                vals = [v / scale for v in vals]
                if kind == "R":
                    vals = vals[1:] + vals[:1]      # stored w first; written x y z w
                w.writerow([tick, kind, joint, bits] + ["%.8f" % v for v in vals])
            return len(anm.keys) + anm.joints * 2
        w.writerow(["tick", "joint", "parent", "px", "py", "pz", "qx", "qy", "qz", "qw", "mx", "my", "mz"])
        ticks, t = [], 0.0
        while t <= anm.length:
            ticks.append(t)
            t += step
        rows = 0
        for t, pos, rot in anm.sample(ticks):
            world = anm.model_positions(pos, rot)
            for j in range(anm.joints):
                w.writerow(["%g" % t, j, anm.parent[j]] + ["%.5f" % v for v in pos[j]] +
                           ["%.6f" % v for v in rot[j]] + ["%.4f" % v for v in world[j]])
                rows += 1
        return rows


# --------------------------------------------------------------------------- ADPCM

ADPCM_COEF = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


def adpcm_check(data, what="ADPCM data"):
    """Structural check of 16-byte blocks: filter 0-4, shift 0-12, flags 0-7."""
    if len(data) % 16:
        raise FormatError("%s: length %d is not a multiple of 16" % (what, len(data)))
    heads, flags = set(data[0::16]), set(data[1::16])
    bad = sorted(h for h in heads if (h >> 4) > 4 or (h & 15) > 12)
    if bad:
        raise FormatError("%s: block header byte 0x%02x is not ADPCM (filter 0-4, shift 0-12)" % (what, bad[0]))
    if any(f > 7 for f in flags):
        raise FormatError("%s: block flag 0x%02x is not ADPCM" % (what, max(flags)))
    return flags


def adpcm_decode(data, stop_at_end=True):
    """Decode 16-byte blocks to a list of signed 16-bit samples (28 per block)."""
    s1 = s2 = 0
    out = []
    for i in range(0, len(data) - 15, 16):
        head, flag = data[i], data[i + 1]
        if stop_at_end and flag == 7:
            break                       # end marker block: not played
        shift, filt = head & 15, head >> 4
        c1, c2 = ADPCM_COEF[filt if filt < 5 else 0]
        for b in data[i + 2:i + 16]:
            for nib in (b & 15, b >> 4):
                v = nib << 12
                if v & 0x8000:
                    v -= 0x10000
                v = (v >> shift) + ((s1 * c1 + s2 * c2 + 32) >> 6)
                v = -32768 if v < -32768 else 32767 if v > 32767 else v
                s2, s1 = s1, v
                out.append(v)
        if stop_at_end and flag & 1:
            break                       # last block of a one-shot or of a loop
    return out


def write_wav(path, channels, rate):
    n = min(len(c) for c in channels)
    if len(channels) == 1:
        frames = struct.pack("<%dh" % n, *channels[0][:n])
    else:
        inter = [0] * (n * 2)
        inter[0::2] = channels[0][:n]
        inter[1::2] = channels[1][:n]
        frames = struct.pack("<%dh" % (n * 2), *inter)
    w = wave.open(path, "wb")
    w.setnchannels(len(channels))
    w.setsampwidth(2)
    w.setframerate(int(round(rate)))
    w.writeframes(frames)
    w.close()
    return n


class Vag:
    """A lump sample: 0x30-byte header (big-endian size and rate), then ADPCM blocks."""

    def __init__(self, data, name="?"):
        self.name = name
        if len(data) < 0x40:
            raise FormatError("too short for a sample header")
        self.magic = data[:4]
        self.version, self.reserved, self.size, self.rate = struct.unpack_from(">4I", data, 4)
        if self.magic not in (b"VAGp", b"\0\0\0\0"):
            raise FormatError("no VAGp header (this may be raw stream data: use --raw or --dir)")
        if self.size + 0x30 != len(data):
            raise FormatError("header data size 0x%x does not match the entry (0x%x)" % (self.size, len(data) - 0x30))
        if not 500 <= self.rate <= 48000:
            raise FormatError("implausible sample rate %d" % self.rate)
        self.label = _cstr(data[0x20:0x30])
        self.body = data[0x30:]
        self.flags = adpcm_check(self.body, "sample body")
        # the game's rule: the sample loops when a block before the last one has flag value 4 set
        self.loop_start = next((i for i in range(0, len(self.body) - 16, 16) if self.body[i + 1] & 4), None)
        self.loops = self.loop_start is not None
        self.blocks = len(self.body) // 16

    def samples(self):
        return adpcm_decode(self.body)

    def describe(self, out):
        n = len(self.samples())
        print("%s: sample, magic %s, version 0x%x, %d Hz mono, %d blocks, %d samples (%.3f s), %s"
              % (self.name, "VAGp" if self.magic == b"VAGp" else "none", self.version, self.rate, self.blocks, n,
                 n / self.rate, "loops from block %d" % (self.loop_start // 16) if self.loops else "one-shot"),
              file=out)
        print("  pitch register %d (rate * 4096 / 48000); header label %r; block flags used %s"
              % ((self.rate << 12) // 48000, self.label, sorted(self.flags)), file=out)
        if self.rate == 1000:
            print("  note: 1000 Hz entries are tiny placeholders on the disc", file=out)


class StreamDir:
    """*dialog.bin: 0x50-byte records naming byte ranges of a .VAT file."""

    def __init__(self, data, name="?"):
        self.name = name
        self.entries = []
        n = len(data) // DIR_ENTRY_SIZE
        terminated = False
        for i in range(n):
            e = data[i * DIR_ENTRY_SIZE:(i + 1) * DIR_ENTRY_SIZE]
            nm = _cstr(e[:0x40])
            off, rate, stereo, lang, extra = struct.unpack_from("<IIHhI", e, 0x40)
            if not nm:
                self.end = off
                terminated = True
                break
            if any(c < 0x20 or c > 0x7e for c in nm.encode("latin1")):
                raise FormatError("stream directory record %d has a non-text name" % i)
            self.entries.append(dict(name=nm, offset=off, rate=rate, stereo=stereo, lang=lang, extra=extra))
        if not terminated:
            if any(data):
                raise FormatError("stream directory has no terminating record")
            self.end = 0
        prev = 0
        for i, e in enumerate(self.entries):
            nxt = self.entries[i + 1]["offset"] if i + 1 < len(self.entries) else self.end
            if e["offset"] < prev or nxt < e["offset"]:
                raise FormatError("stream directory offsets are not ascending at %s" % e["name"])
            if e["offset"] % 0x800:
                raise FormatError("stream entry %s is not sector aligned" % e["name"])
            e["length"] = nxt - e["offset"]
            prev = e["offset"]

    def find(self, name, lang=0):
        """The game's rule: exact name, the whole table is walked and the last match wins;
        an entry in the current language is preferred over one in language 0."""
        in_lang = fallback = None
        for e in self.entries:
            if e["name"] == name:
                if e["lang"] == 0:
                    fallback = e
                if e["lang"] == lang:
                    in_lang = e
        return in_lang or fallback

    def describe(self, out, limit=12):
        kinds = {}
        for e in self.entries:
            k = (e["name"].rsplit(".", 1)[-1], e["rate"], e["stereo"], e["lang"])
            kinds[k] = kinds.get(k, 0) + 1
        print("%s: stream directory, %d entries, stream file size 0x%x" % (self.name, len(self.entries), self.end),
              file=out)
        for (ext, rate, st, lang), c in sorted(kinds.items()):
            print("  %5d x .%s rate field %d, %s, language %d"
                  % (c, ext, rate, "stereo (0x400 interleave)" if st else "mono", lang), file=out)
        for e in self.entries[:limit]:
            print("  0x%08x +0x%07x %s" % (e["offset"], e["length"], e["name"]), file=out)
        if len(self.entries) > limit:
            print("  ... %d more" % (len(self.entries) - limit), file=out)


def stream_channels(data, stereo):
    """Split raw stream bytes into per-channel ADPCM byte strings."""
    if not stereo:
        return [data]
    left = b"".join(data[i:i + STREAM_CHUNK] for i in range(0, len(data), 2 * STREAM_CHUNK))
    right = b"".join(data[i + STREAM_CHUNK:i + 2 * STREAM_CHUNK] for i in range(0, len(data), 2 * STREAM_CHUNK))
    return [left, right]


def stream_check(data, stereo, what):
    if len(data) % 0x800:
        raise FormatError("%s: length 0x%x is not a multiple of 0x800" % (what, len(data)))
    return adpcm_check(data, what)


def raw_stream_summary(data, what):
    """Check a whole headerless stream file. Returns (share of 0x800 sectors that are pure ADPCM, flags seen).

    A stream file may also hold lip-sync .anm entries, so not every sector has to be audio; a file
    in which fewer than half of the sectors look like ADPCM is rejected."""
    if len(data) % 0x800:
        raise FormatError("%s: length 0x%x is not a multiple of 0x800" % (what, len(data)))
    if not data:
        return 1.0, set()
    legal = bytes(1 if (h >> 4) <= 4 and (h & 15) <= 12 else 0 for h in range(256))
    heads = data[0::16].translate(legal)
    flags_ok = data[1::16].translate(bytes(1 if f <= 7 else 0 for f in range(256)))
    sectors = len(data) // 0x800
    good = sum(1 for i in range(sectors)
               if 0 not in heads[i * 128:(i + 1) * 128] and 0 not in flags_ok[i * 128:(i + 1) * 128])
    share = good / sectors
    if share < 0.5:
        raise FormatError("%s: only %d%% of the sectors hold ADPCM blocks; not stream data" % (what, share * 100))
    return share, set(data[1::16]) if share == 1.0 else set()


def describe_raw_stream(blob, out):
    data = blob.bytes()
    if not data:
        print("%s: empty stream file" % blob.name, file=out)
        return
    share, flags = raw_stream_summary(data, blob.name)
    if share == 1.0:
        print("%s: raw ADPCM stream data, %d bytes = %d blocks (%.1f s if mono, %.1f s if stereo, at %d Hz), "
              "flags %s" % (blob.name, len(data), len(data) // 16, len(data) / 16 * 28 / STREAM_RATE_NOMINAL,
                            len(data) / 32 * 28 / STREAM_RATE_NOMINAL, STREAM_RATE_NOMINAL, sorted(flags)), file=out)
    else:
        print("%s: stream file, %d bytes; %.1f%% of its 0x800-byte sectors are ADPCM, the rest are other "
              "entries (lip-sync .anm clips are stored in stream files)" % (blob.name, len(data), share * 100),
              file=out)
    print("  no header: entry boundaries and mono/stereo come from the matching *dialog.bin (--dir);"
          " pure audio can also be decoded whole with --raw mono|stereo", file=out)


# --------------------------------------------------------------------------- .dbin, ambient.bin, .hd

class Dbin:
    def __init__(self, data, name="?"):
        self.name = name
        if not data or len(data) % DBIN_NODE_SIZE:
            raise FormatError("size %d is not a multiple of the 0x448-byte node" % len(data))
        count = struct.unpack_from("<b", data, 0)[0]
        if count != len(data) // DBIN_NODE_SIZE:
            raise FormatError("node count byte %d does not match the size (%d nodes)"
                              % (count, len(data) // DBIN_NODE_SIZE))
        self.nodes = []
        for k in range(count):
            r = data[k * DBIN_NODE_SIZE:(k + 1) * DBIN_NODE_SIZE]
            nch, = struct.unpack_from("<i", r, 0x54)
            if not 0 <= nch <= DBIN_MAX_CHOICES:
                raise FormatError("node %d has %d choices" % (k, nch))
            choices = []
            for i in range(nch):
                c = r[0x58 + i * DBIN_CHOICE_SIZE:0x58 + (i + 1) * DBIN_CHOICE_SIZE]
                nxt, = struct.unpack_from("<i", c, 0x50)
                if not -1 <= nxt < count:
                    raise FormatError("node %d choice %d jumps to node %d" % (k, i, nxt))
                choices.append(dict(text=_cstr(c[0:0x10]), condition=_cstr(c[0x10:0x30]),
                                    action=_cstr(c[0x30:0x50]), next=nxt))
            self.nodes.append(dict(condition=_cstr(r[1:0x21]), text=_cstr(r[0x21:0x31]), voice=_cstr(r[0x31:0x41]),
                                   speaker=_cstr(r[0x41:0x54]), choices=choices))

    def describe(self, out):
        print("%s: dialog file, %d nodes of 0x448 bytes" % (self.name, len(self.nodes)), file=out)
        for k, n in enumerate(self.nodes):
            print("  node %2d: condition %-12r text key %-18s voice %-16s speaker %-10r choices %d"
                  % (k, n["condition"], n["text"], n["voice"], n["speaker"], len(n["choices"])), file=out)
            for i, c in enumerate(n["choices"]):
                print("      choice %d: text key %-18s condition %-12r action %-14r next %d"
                      % (i, c["text"], c["condition"], c["action"], c["next"]), file=out)


class Ambient:
    """ambient.bin: text. A group is 'min-max' seconds, up to two numbers, then .vag names."""

    _two = re.compile(r"\s*([+-]?\d+)-([+-]?\d+)")
    _one = re.compile(r"\s*([+-]?\d+)")

    def __init__(self, data, name="?"):
        self.name = name
        if any(b >= 0x80 for b in data):
            raise FormatError("ambient.bin is not text")
        # the game lower-cases the buffer, splits at CR/LF and ignores lines starting with ';'
        lines = [l for l in data.decode("ascii").lower().replace("\r", "\n").split("\n") if l and l[0] != ";"]
        self.groups = []
        i = 0
        while i < len(lines):
            line = lines[i]
            m = self._two.match(line) if "-" in line else self._one.match(line)
            if not m:
                i += 1                      # not the start of a group: skipped, as the game does
                continue
            g = dict(min=int(m.group(1)), max=int(m.group(m.lastindex)), numbers=[], names=[])
            i += 1
            while i < len(lines):
                line = lines[i]
                m = self._one.match(line)
                if m and not g["names"]:
                    if not g["numbers"]:
                        g["numbers"].append(int(m.group(1)))
                    else:                   # a third number would overwrite the second
                        g["numbers"][1:] = [int(m.group(1))]
                elif ".vag" in line:
                    g["names"].append(line.split()[0])
                else:
                    break                   # this line is looked at again as a possible group start
                i += 1
            if len(g["names"]) > 16:
                raise FormatError("ambient group with %d names (the game's table holds 16)" % len(g["names"]))
            self.groups.append(g)
        if len(self.groups) > 16:
            raise FormatError("more than 16 ambient groups")
        if not self.groups and any(l.strip() for l in lines):
            raise FormatError("no ambient group found")

    def describe(self, out):
        print("%s: ambient schedule, %d groups" % (self.name, len(self.groups)), file=out)
        for g in self.groups:
            print("  every %d-%d s, volume group/attenuation %s, %d stream names"
                  % (g["min"], g["max"], g["numbers"], len(g["names"])), file=out)


class IecsHd:
    """Sony IECS sample bank header (.HD); the samples are in the .BD next to it."""

    def __init__(self, data, name="?"):
        self.name = name
        if data[:8] != b"IECSsreV":
            raise FormatError("not an IECS header")
        self.chunks = {}
        o = 0
        while o + 12 <= len(data):
            if data[o:o + 4] != b"IECS":
                o += 4
                continue
            tag = data[o + 4:o + 8][::-1].decode("latin1")
            size, = struct.unpack_from("<I", data, o + 8)
            if size < 12 or o + size > len(data):
                raise FormatError("IECS chunk %s has a bad size" % tag)
            self.chunks[tag] = (o, size)
            o += size
        if "Head" not in self.chunks or "Vagi" not in self.chunks:
            raise FormatError("IECS header without Head/Vagi chunks")
        ho, hs = self.chunks["Head"]
        vo, vs = self.chunks["Vagi"]
        if hs < 20 or vs < 16:
            raise FormatError("IECS Head/Vagi chunk too small")
        self.header_size, self.body_size = struct.unpack_from("<II", data, ho + 12)
        last, = struct.unpack_from("<I", data, vo + 12)
        if last >= 0x10000 or 16 + (last + 1) * 4 > vs:
            raise FormatError("IECS sample table does not fit its chunk")
        self.samples = []
        for i in range(last + 1):
            p, = struct.unpack_from("<I", data, vo + 16 + i * 4)
            if p + 8 > vs:
                raise FormatError("IECS sample record %d lies outside its chunk" % i)
            off, rate, loop = struct.unpack_from("<IHB", data, vo + p)
            self.samples.append(dict(offset=off, rate=rate, loop=loop))
        for i, s in enumerate(self.samples):
            nxt = self.samples[i + 1]["offset"] if i + 1 < len(self.samples) else self.body_size
            if nxt < s["offset"]:
                raise FormatError("IECS sample offsets are not ascending")
            s["length"] = nxt - s["offset"]

    def describe(self, out):
        print("%s: IECS bank header, chunks %s, body %d bytes, %d samples"
              % (self.name, " ".join(sorted(self.chunks)), self.body_size, len(self.samples)), file=out)
        for i, s in enumerate(self.samples):
            print("  sample %d: body offset 0x%x, %d bytes, %d Hz, loop flag %d"
                  % (i, s["offset"], s["length"], s["rate"], s["loop"]), file=out)


# --------------------------------------------------------------------------- dispatch

def classify(name, head):
    """Decide what an entry is from its name and first bytes; None for types we do not cover."""
    n = name.lower()
    if n.endswith(".anm"):
        return "anm"
    if n.endswith("dialog.bin"):
        return "streamdir"
    if n == "ambient.bin":
        return "ambient"
    if n.endswith(".dbin"):
        return "dbin"
    if n.endswith(".hd") and head[:4] == b"IECS":
        return "iecs"
    if n.endswith(".vag"):
        if head[:4] == b"VAGp" or (head[:4] == b"\0\0\0\0" and len(head) >= 0x14 and
                                    500 <= struct.unpack_from(">I", head, 0x10)[0] <= 48000):
            return "vag"
        return "rawstream"
    if n.endswith(".vat") or n.endswith(".va1"):
        return "rawstream"
    return None


def parse_blob(blob, kind=None):
    kind = kind or classify(blob.name, blob.read(0, 0x40))
    if kind == "anm":
        return Anm(blob.bytes(), blob.name)
    if kind == "vag":
        return Vag(blob.bytes(), blob.name)
    if kind == "streamdir":
        return StreamDir(blob.bytes(), blob.name)
    if kind == "dbin":
        return Dbin(blob.bytes(), blob.name)
    if kind == "ambient":
        return Ambient(blob.bytes(), blob.name)
    if kind == "iecs":
        return IecsHd(blob.bytes(), blob.name)
    if kind == "rawstream":
        return None
    raise FormatError("%s: not an animation or audio type this tool knows "
                      "(.anm, .vag, *dialog.bin, .vat, .va1, .dbin, ambient.bin, .hd)" % blob.name)


def stream_entry(blob, dir_spec, entry_name):
    """(sub-blob, directory record) for a named entry of a .VAT, found through its directory."""
    directory = parse_blob(open_source(dir_spec), "streamdir")
    if not entry_name:
        raise FormatError("--dir needs --entry NAME (see 'info' on the directory for names)")
    e = directory.find(entry_name.lower()) or directory.find(entry_name)
    if e is None:
        raise FormatError("no stream entry %r in %s" % (entry_name, directory.name))
    if e["offset"] + e["length"] > blob.size:
        raise FormatError("entry lies outside %s: wrong stream file for this directory?" % blob.name)
    return blob.sub(e["name"], e["offset"], e["length"]), e


def source_blob(args):
    """The blob a command works on: SOURCE itself, or one stream entry of it (--dir, --entry)."""
    blob = open_source(args.source)
    if getattr(args, "dir", None):
        blob, _ = stream_entry(blob, args.dir, args.entry)
    return blob


def cmd_info(args, out):
    blob = source_blob(args)
    if container_kind(blob.name):
        return cmd_list(args, out)
    kind = classify(blob.name, blob.read(0, 0x40))
    if args.dir and kind == "rawstream":
        _, e = stream_entry(open_source(args.source), args.dir, args.entry)
        stream_check(blob.bytes(), bool(e["stereo"]), blob.name)
        frames = blob.size // 16 * 28 // (2 if e["stereo"] else 1)
        print("%s: stream entry at 0x%x, %d bytes, %s, %d sample frames (%.2f s at %d Hz), rate field %d"
              % (blob.name, e["offset"], blob.size, "stereo, 0x400 interleave" if e["stereo"] else "mono",
                 frames, frames / STREAM_RATE_NOMINAL, STREAM_RATE_NOMINAL, e["rate"]), file=out)
        return 0
    obj = parse_blob(blob, kind)
    if kind == "rawstream":
        describe_raw_stream(blob, out)
    elif kind == "anm":
        obj.describe(out, show_events=args.events, show_keys=args.keys)
    else:
        obj.describe(out)
    return 0


def cmd_list(args, out):
    blob = open_source(args.source)
    kids = blob.children()
    if kids is None:
        raise FormatError("%s is not a container" % blob.name)
    for name, b in sorted(kids, key=lambda t: t[0].lower()):
        kind = classify(name.rsplit("/", 1)[-1], b.read(0, 0x40)) or container_kind(name) or "-"
        print("%-10s %10d  %s" % (kind, b.size, name), file=out)
    return 0


def cmd_csv(args, out):
    blob = source_blob(args)
    obj = parse_blob(blob)
    if not isinstance(obj, Anm):
        raise FormatError("csv needs an .anm")
    if args.step <= 0:
        raise FormatError("--step must be positive")
    rows = anm_csv(obj, args.out, raw_keys=args.keys_only, step=args.step)
    print("wrote %d rows to %s" % (rows, args.out), file=out)
    return 0


def cmd_wav(args, out):
    blob = open_source(args.source)
    kind = classify(blob.name, blob.read(0, 0x40))
    if kind == "vag":
        v = Vag(blob.bytes(), blob.name)
        n = write_wav(args.out, [v.samples()], args.rate or v.rate)
        print("wrote %d samples, mono, %d Hz to %s" % (n, args.rate or v.rate, args.out), file=out)
        return 0
    if kind == "iecs":
        hd = IecsHd(blob.bytes(), blob.name)
        if not args.bd:
            raise FormatError("an .hd holds no audio: give the body with --bd FILE and pick --index N")
        if not 0 <= args.index < len(hd.samples):
            raise FormatError("--index must be 0..%d" % (len(hd.samples) - 1))
        body = open_source(args.bd)
        s = hd.samples[args.index]
        data = body.read(s["offset"], s["length"])
        data = data[:len(data) // 16 * 16]
        adpcm_check(data, "bank sample")
        n = write_wav(args.out, [adpcm_decode(data)], args.rate or s["rate"])
        print("wrote %d samples, mono, %d Hz to %s" % (n, args.rate or s["rate"], args.out), file=out)
        return 0
    if kind != "rawstream":
        raise FormatError("%s holds no audio this tool can decode" % blob.name)
    rate = args.rate or STREAM_RATE_NOMINAL
    if args.dir:
        sub, e = stream_entry(blob, args.dir, args.entry)
        if not e["name"].endswith(".vag"):
            raise FormatError("%s is not audio (stream files also hold lip-sync .anm entries)" % e["name"])
        data, stereo = sub.bytes(), bool(e["stereo"])
        if e["rate"] not in (0, STREAM_RATE_NOMINAL):
            print("note: the directory says %d Hz; the console plays every stream at %.1f Hz regardless"
                  % (e["rate"], STREAM_RATE_CONSOLE), file=out)
    elif args.raw:
        data, stereo = blob.bytes(), args.raw == "stereo"
    else:
        raise FormatError("raw stream data: give --dir DIRECTORY --entry NAME, or --raw mono|stereo")
    stream_check(data, stereo, blob.name)
    chans = [adpcm_decode(c, stop_at_end=False) for c in stream_channels(data, stereo)]
    n = write_wav(args.out, chans, rate)
    print("wrote %d sample frames, %s, %d Hz to %s" % (n, "stereo" if stereo else "mono", rate, args.out), file=out)
    return 0


# --------------------------------------------------------------------------- scan (self-test)

class Tally:
    def __init__(self, quiet):
        self.ok, self.bad, self.skipped, self.quiet, self.failures = {}, {}, 0, quiet, []

    def good(self, kind):
        self.ok[kind] = self.ok.get(kind, 0) + 1

    def fail(self, kind, where, err):
        self.bad[kind] = self.bad.get(kind, 0) + 1
        self.failures.append("%s [%s]: %s" % (where, kind, err))


def scan_blob(blob, where, tally, siblings=None):
    name = blob.name.rsplit("/", 1)[-1]
    blob.name = name
    if container_kind(name):
        try:
            kids = blob.children()
        except FormatError as e:
            tally.fail("container", where, e)
            return
        table = dict((n.upper(), b) for n, b in kids)
        for n, b in kids:
            scan_blob(b, where + "::" + n, tally, table)
        return
    kind = classify(name, blob.read(0, 0x40))
    if kind is None:
        tally.skipped += 1
        return
    try:
        if kind == "rawstream":
            scan_stream_file(blob, where, tally, siblings)
        else:
            parse_blob(blob, kind)
            tally.good(kind)
    except FormatError as e:
        tally.fail(kind, where, e)
    except (struct.error, IndexError, ValueError) as e:     # a malformed file, reported not crashed on
        tally.fail(kind, where, "malformed: %s" % e)


def find_stream_dir(blob, siblings):
    """In a disc image: LEVEL.VAT is indexed by LEVEL.GOB::level.lmp::ntsc_dialog.bin (MOUTH.VAT by MOUTH.LMP)."""
    if not siblings:
        return None
    stem = blob.name.rsplit(".", 1)[0].upper()
    folder = None
    for key in siblings:
        if key.endswith("/" + blob.name.upper()):
            folder = key[:-len(blob.name)]
    if folder is None:
        return None
    for ext in (".LMP", ".GOB"):
        cont = siblings.get(folder + stem + ext)
        if cont is None:
            continue
        cont.name = stem + ext
        try:
            kids = cont.children()
            if ext == ".GOB":
                inner = [b for n, b in kids if n.lower() == stem.lower() + ".lmp"]
                if not inner:
                    continue
                inner[0].name = stem + ".lmp"
                kids = inner[0].children()
        except FormatError:
            continue
        for want in ("ntsc_dialog.bin", "dialog.bin"):
            for n, b in kids:
                if n.lower() == want:
                    b.name = n
                    return b
    return None


def scan_stream_file(blob, where, tally, siblings):
    dblob = find_stream_dir(blob, siblings)
    if dblob is None:
        if blob.size:
            raw_stream_summary(blob.bytes(), blob.name)
        tally.good("rawstream (no directory)")
        return
    directory = StreamDir(dblob.bytes(), dblob.name)
    if directory.end != blob.size:
        raise FormatError("directory ends at 0x%x but the stream file is 0x%x bytes" % (directory.end, blob.size))
    tally.good("stream file + directory")
    for e in directory.entries:
        sub = where + "::" + e["name"]
        try:
            data = blob.read(e["offset"], e["length"])
            if e["name"].endswith(".anm"):
                Anm(data, e["name"])
                tally.good("anm (in stream file)")
            else:
                stream_check(data, bool(e["stereo"]), e["name"])
                tally.good("stream entry")
        except FormatError as err:
            tally.fail("stream entry", sub, err)
        except (struct.error, IndexError, ValueError) as err:
            tally.fail("stream entry", sub, "malformed: %s" % err)


def cmd_scan(args, out):
    tally = Tally(args.quiet)
    for path in args.paths:
        if os.path.isdir(path):
            for root, _, files in sorted(os.walk(path)):
                table = {}
                blobs = []
                for fn in sorted(files):
                    try:
                        b = open_path(os.path.join(root, fn))
                    except (FormatError, OSError, ValueError) as e:
                        tally.fail("file", os.path.join(root, fn), e)
                        continue
                    table["/" + fn.upper()] = b
                    blobs.append((fn, b))
                for fn, b in blobs:
                    scan_blob(b, os.path.join(root, fn), tally, table)
        else:
            scan_blob(open_path(path), path, tally)
    kinds = sorted(set(tally.ok) | set(tally.bad))
    total_ok = total_bad = 0
    for k in kinds:
        ok, bad = tally.ok.get(k, 0), tally.bad.get(k, 0)
        total_ok += ok
        total_bad += bad
        print("%-28s parsed %6d   failed %4d" % (k, ok, bad), file=out)
    print("%-28s parsed %6d   failed %4d   (%d files of other types not examined)"
          % ("total", total_ok, total_bad, tally.skipped), file=out)
    if not args.quiet:
        for line in tally.failures[:200]:
            print("FAILED " + line, file=out)
        if len(tally.failures) > 200:
            print("... %d more failures" % (len(tally.failures) - 200), file=out)
    return 1 if total_bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("info", help="print the structure of one file or entry")
    p.add_argument("source")
    p.add_argument("--dir", help="stream directory (*dialog.bin) when SOURCE is a .VAT")
    p.add_argument("--entry", help="stream entry name inside --dir (.vag or lip-sync .anm)")
    p.add_argument("--events", action="store_true", help="list sound names and events of an .anm")
    p.add_argument("--keys", type=int, default=0, metavar="N", help="also print the first N key records")
    p = sub.add_parser("list", help="list the entries of a .iso, .gob or .lmp")
    p.add_argument("source")
    p = sub.add_parser("csv", help="dump an animation's bone tracks")
    p.add_argument("source")
    p.add_argument("out")
    p.add_argument("--dir", help="stream directory (*dialog.bin) when SOURCE is a .VAT")
    p.add_argument("--entry", help="lip-sync .anm entry name inside --dir")
    p.add_argument("--keys", dest="keys_only", action="store_true", help="raw key records instead of sampled poses")
    p.add_argument("--step", type=float, default=1.0, help="sampling step in ticks (default 1)")
    p = sub.add_parser("wav", help="decode a sound to a 16-bit WAV file")
    p.add_argument("source")
    p.add_argument("out")
    p.add_argument("--dir", help="stream directory (*dialog.bin) for a .VAT")
    p.add_argument("--entry", help="stream entry name inside --dir")
    p.add_argument("--raw", choices=("mono", "stereo"), help="decode headerless stream data whole")
    p.add_argument("--rate", type=int, help="override the output sample rate")
    p.add_argument("--bd", help="body file for an IECS .hd")
    p.add_argument("--index", type=int, default=0, help="sample number inside the bank")
    p = sub.add_parser("scan", help="parse everything under the given paths and count results")
    p.add_argument("paths", nargs="+")
    p.add_argument("--quiet", action="store_true", help="totals only")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        return {"info": cmd_info, "list": cmd_list, "csv": cmd_csv, "wav": cmd_wav, "scan": cmd_scan}[args.cmd](
            args, sys.stdout)
    except FormatError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    except (struct.error, IndexError, OverflowError) as e:      # safety net: never a traceback
        print("error: malformed file (%s)" % e, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
