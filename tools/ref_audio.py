#!/usr/bin/env python3
"""Small RTA audio contracts using caller-supplied or synthetic bytes only.

Addressed evidence: docs/formats/audio.md and docs/audio-playback.md. This is not a
SPU2 emulator. It deliberately has no code for opening an original game archive.
"""

from dataclasses import dataclass
from math import sqrt
from struct import unpack_from


BLOCK_BYTES = 16
SAMPLES_PER_BLOCK = 28
VAT_SECTOR = 0x800
STEREO_CHUNK = 0x400
SPU_RATE = 48000
STREAM_PITCH = 0x7FE
FILTERS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


@dataclass(frozen=True)
class VagHeader:
    magic: bytes
    version: int
    data_size: int
    rate: int
    name: bytes


def parse_vag_header(data: bytes) -> VagHeader:
    """Lump VAG header: sample_register 0x2130d0, rate read 0x2169c8."""
    if len(data) < 0x30:
        raise ValueError("VAG header is shorter than 0x30 bytes")
    size = unpack_from(">I", data, 0x0C)[0]
    rate = unpack_from(">I", data, 0x10)[0]
    if size % BLOCK_BYTES or rate == 0:
        raise ValueError("invalid VAG data size or rate")
    return VagHeader(data[:4], unpack_from(">I", data, 4)[0], size,
                     rate, data[0x20:0x30].split(b"\0", 1)[0])


def base_pitch(rate: int) -> int:
    """Integer base pitch stored at sample +0x20 (0x2169c8)."""
    if rate < 0:
        raise ValueError("rate must be nonnegative")
    return rate * 4096 // SPU_RATE


@dataclass(frozen=True)
class AdpcmResult:
    pcm: tuple[int, ...]
    loop_start_sample: int | None
    loop_end_sample: int | None


def decode_adpcm(data: bytes) -> AdpcmResult:
    """PS2 ADPCM body, 16 bytes -> 28 samples; see audio.md codec contract.

    The returned loop end is exclusive. A 0x07 end marker is omitted. This models
    stored PCM and markers, not repeated playback, pitch interpolation or envelope.
    """
    if len(data) % BLOCK_BYTES:
        raise ValueError("ADPCM body is not block aligned")
    out: list[int] = []
    prev = older = 0
    loop_start = loop_end = None
    for pos in range(0, len(data), BLOCK_BYTES):
        block = data[pos:pos + BLOCK_BYTES]
        filt, shift = block[0] >> 4, block[0] & 15
        flags = block[1]
        if filt > 4 or shift > 12 or flags > 7:
            raise ValueError("invalid ADPCM block header")
        if flags == 7:  # terminal marker, not audible
            break
        if flags & 4:
            loop_start = len(out)
        c1, c2 = FILTERS[filt]
        for byte in block[2:]:
            for nibble in (byte & 15, byte >> 4):
                signed = nibble if nibble < 8 else nibble - 16
                sample = ((signed << 12) >> shift)
                sample += (c1 * prev + c2 * older + 32) >> 6
                sample = max(-32768, min(32767, sample))
                out.append(sample)
                older, prev = prev, sample
        if flags & 1:
            if flags & 2:
                loop_end = len(out)
            break
    return AdpcmResult(tuple(out), loop_start, loop_end)


@dataclass(frozen=True)
class VatEntry:
    name: str
    offset: int
    length: int
    declared_rate: int
    stereo: bool
    language: int
    loop_restart: int


def parse_vat_directory(directory: bytes, vat_size: int) -> list[VatEntry]:
    """0x50-byte dialog.bin records (0x210e60, 0x216860)."""
    if len(directory) % 0x50 or not directory:
        raise ValueError("VAT directory is not record aligned")
    raw = []
    for pos in range(0, len(directory), 0x50):
        record = directory[pos:pos + 0x50]
        name = record[:0x40].split(b"\0", 1)[0].decode("ascii")
        offset, rate, channels, language, restart = unpack_from("<IIHhI", record, 0x40)
        raw.append((name, offset, rate, channels, language, restart))
        if not name:
            break
    if raw[-1][0] or raw[-1][1] != vat_size:
        raise ValueError("VAT terminal record missing or wrong size")
    entries = []
    for record, following in zip(raw, raw[1:]):
        name, offset, rate, channels, language, restart = record
        end = following[1]
        if offset % VAT_SECTOR or end % VAT_SECTOR or not 0 <= offset <= end <= vat_size:
            raise ValueError("VAT offsets are unaligned or out of order")
        if channels not in (0, 1):
            raise ValueError("unsupported VAT channel flag")
        entries.append(VatEntry(name, offset, end - offset, rate,
                                bool(channels), language, restart))
    return entries


def split_stereo_chunks(data: bytes) -> tuple[bytes, bytes]:
    """VAT stereo: 0x400 left, 0x400 right (HELLO+0x648)."""
    if len(data) % (2 * STEREO_CHUNK):
        raise ValueError("stereo body is not a whole interleave pair")
    left = bytearray()
    right = bytearray()
    for pos in range(0, len(data), 2 * STEREO_CHUNK):
        left.extend(data[pos:pos + STEREO_CHUNK])
        right.extend(data[pos + STEREO_CHUNK:pos + 2 * STEREO_CHUNK])
    return bytes(left), bytes(right)


def stream_duration(byte_count: int, stereo: bool, rate: float = 24000) -> float:
    """Game's timing rate 24 kHz (0x22fdd8); SPU pitch yields 23976.5625."""
    if byte_count < 0 or byte_count % BLOCK_BYTES or rate <= 0:
        raise ValueError("invalid stream byte count or rate")
    return byte_count / BLOCK_BYTES * SAMPLES_PER_BLOCK / rate / (2 if stereo else 1)


def pan_atten(position: tuple[float, float, float],
              camera: tuple[float, float, float],
              camera_right: tuple[float, float, float],
              near: float = 360.0, far: float = 840.0) -> tuple[float, float]:
    """Linear distance and signed pan at sound_panAtten 0x213c50."""
    if far <= near or near < 0:
        raise ValueError("expected 0 <= near < far")
    dx = tuple(a - b for a, b in zip(position, camera))
    distance = sqrt(sum(x * x for x in dx))
    attenuation = min(1.0, max(0.0, (far - distance) / (far - near)))
    pan = min(1.0, max(-1.0, sum(a * b for a, b in zip(dx, camera_right)) / far))
    return attenuation * (1.0 - pan), attenuation * (1.0 + pan)
