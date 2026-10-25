# Return to Arms audio formats (SLUS-20973 v2.00)

This is a contract for the native client, not a copy of disc data. **Observed** means
read at the named game or driver address, or counted in the private NTSC disc as stated;
**Inferred** means a consequence of those reads; **Unknown** names an open check.
`docs/formats/anim-audio.md` sections 2.7 and 3 and `docs/issues/native-sound.md`
section 1 retain the longer evidence trail. No game sample is needed by the reference
contracts in `tools/ref_audio.py`.

## Codec and effect samples

**Observed** (`soundSeq_duration` 0x2132f8, `dialog_syncMouth` 0x22fdd8,
`sample_register` 0x2130d0, SPU2 behavior in `docs/issues/native-sound.md` 1.3):
Sony PS2 ADPCM uses 16-byte blocks yielding 28 signed PCM samples. Byte 0 has filter
0–4 in its high nibble and shift 0–12 in its low nibble. Byte 1 has flags: bit 0 end,
bit 1 repeat, bit 2 loop start. Bytes 2–15 hold signed 4-bit samples, low nibble first.
The filter coefficients `(c1,c2)` by index are `(0,0)`, `(60,0)`, `(115,-52)`,
`(98,-55)`, `(122,-60)`. For each nibble, sign extend, scale as signed 16-bit
`(nibble << 12) >> shift`, add `(c1*previous + c2*previous_previous + 32) >> 6`,
then clamp to signed 16-bit. Decoder history continues between blocks of one channel;
stereo channels have separate histories. A block flagged 7 is an end marker and is not
heard; flag 1 or 3 ends after that block. Flag 6 identifies the loop start, and flag 3
ends the loop. The SPU2 follows the block flags, while the stream driver replaces them.
These parameters were checked structurally on 4,933 samples and 5,351 stream entries
in `docs/formats/anim-audio.md` 3.1; no listening claim is made here.

**Observed** (`sample_register` 0x2130d0, rate conversion 0x2169c8): ordinary lump
`.vag` entries are mono. Their 0x30-byte header uses big-endian fields:

| Offset | Field | Use |
|---|---|---|
| 0x00 | 4-byte `VAGp` magic | Informative; five NTSC entries have zeros, and the game does not validate it |
| 0x04 | u32 version | Informative; usually 4, also 0x20 or 0 |
| 0x0c | u32 data byte count | Size after the header; used at registration |
| 0x10 | u32 sample rate, Hz | Base pitch = integer `rate * 4096 / 48000` |
| 0x20 | 16-byte name | Replaced at load; use the lump entry name for lookup |
| 0x30 | ADPCM blocks | First block is zero in the observed files |

The runtime record is the first 0x40 bytes of the entry after fixup
(`lump_fixupEntry` 0x17153c): +0x20 base pitch, +0x24 SPU address, +0x28 loop
flag (a pre-final block has bit 2 set), +0x2c data size. `sample_register`
0x2130d0 uploads in pieces up to 0x1000 bytes (`sample_uploadToSpu` 0x213ff0).
**Observed:** SPU memory 0x5000 is a silent block; stream buffers begin 0x5010,
0x6010 and 0x7010; effect samples begin 0x8040 and are 64-byte aligned. A sample
that does not fit before the effect workspace gets the silent address 0x5000.
Names are matched without case by `sample_findByName` 0x216798; a duplicate shares
the first registration's address and loop flag (0x2130d0). There is no Sony bank for
these effects: the game registers individual VAG entries and drives SPU2 registers
(`sound_playSample` 0x2134e8, `docs/issues/native-sound.md` 1.1–1.3).

**Inferred implementation rule:** decode the data once per registered sample, retain
the block flag positions, play at the header rate times the event's pitch scale, and
stop after flag 1 or loop from flag 6 to flag 3. Preserve a silent placeholder for a
failed SPU allocation or unresolved name. `NETGUI/EFF.HD` plus `EFF.BD` is a separate
four-sample Sony IECS bank for the network setup program; **inferred unused by this
executable** from the absent reference and module list (`docs/formats/anim-audio.md` 3.5).

## Stream directory and body

**Observed** (`stream_levelDirectory` 0x216860, `stream_levelFileName` 0x216820,
`stream_findLevelEntry` 0x210e60, `stream_findGlobalEntry` 0x210f38): each
`<level>.VAT` and global `MOUTH.VAT` is headerless. The corresponding lump's
`dialog.bin` is its directory, not dialog text. NTSC lump fixup removes the `ntsc_`
prefix and filters PAL entries (`lump_fixup` 0x1717d0). A directory contains 0x50-byte
records, terminated by an empty name. The next record's offset, including the terminal
record, closes the previous entry. All observed NTSC offsets are 0x800-aligned; the
closing offset equals the VAT file size in all 117 checked files.

| Offset | Field | Contract |
|---|---|---|
| 0x00 | char[0x40] | NUL-padded entry name (`.vag` or `.anm`) |
| 0x40 | u32 | Entry byte offset in VAT; length = next offset minus this offset |
| 0x44 | u32 | Claimed sample rate; sent to driver, stored but not used (HELLO+0xd28) |
| 0x48 | u16 | 0 mono, 1 stereo; interpreted at HELLO+0x35c |
| 0x4a | s16 | Language: current 0x44fddc preferred; 0 fallback |
| 0x4c | u32 | Loop restart value. **Executed** (`stream_serviceQueues` 0x211df8, `tools/difftest_audio.py` "loop restart"): with the loop bit set and the remaining count exactly 0 after the read, position becomes `offset + ((value & 0x7ffffc00) << 1)` and remaining becomes `length` minus that span, both as 32-bit words. Zero rewinds to the entry offset. Nonzero values skip in steps of 0x800; bits below 10 and bit 31 add nothing. A span past the length wraps the remaining word. Every observed NTSC record is still 0; the nonzero cases were synthetic |

The table is searched by exact, case-sensitive name; the last applicable duplicate
wins (0x210e60, 0x210f38). `stream_queueRandomByPrefix` 0x211190 selects among
prefix matches using the cosmetic RNG. **Observed:** stream audio is raw ADPCM blocks,
including a zero first block, a terminal block and padding. The driver overwrites each
block's flag byte before SPU transfer (HELLO+0x5f4–0x610), so a VAT entry plays for its
directory length. Mono blocks are sequential. Stereo is 0x400 bytes left, then 0x400
bytes right, repeating (HELLO+0x648–0x6a8); each chunk has 64 blocks/1,792 samples.
`tools/ref_audio.py` supplies a synthetic directory parser and chunk splitter.

**Observed:** the driver fixes five stream voice pitches at 0x7fe (HELLO+0x1018),
which is 23,976.5625 Hz with the 48 kHz SPU clock. It does not retune for the directory
rate. Game timing calculations instead use 24,000 Hz (0x22fdd8). Duration of mono
audio is `byte_count / 16 * 28 / rate`, and stereo duration is half that; for original
game timing, use 24,000 Hz, or 23,976.5625 Hz to match SPU playback. **Unknown:** 16
`mx_env_*` entries and seven missing-asset narration entries marked 48,000 may be
mislabelled or authored for playback at half rate; no listening check established it.

**Observed naming/counts** (`docs/formats/anim-audio.md` 3.4): level files include
`mx_*_l.vag` music (96 stereo), `ss_*_l.vag` ambience one-shots (2,518 stereo),
`amb_*_l.vag` ambience (96 mono), and 221 mono voice lines with 208 matching lip clips.
`MOUTH.VAT` carries 2,406 player lines, 13 music tracks and the intro soundtrack.
The `_l` suffix does not establish channel count; use directory +0x48.

**Inferred unused leftovers** (`docs/formats/anim-audio.md` 3.5): root
`PORKO.VAG` and `MAINMENU.VA1` are headerless 0x400-interleaved stereo streams,
but no executable string names them. `PORKO.VAG` differs from `porko_l.vag` in
`MOUTH.VAT`. Do not select either by filename alone.

## Open format checks

- **Unknown:** exact acoustic parity of a new decoder's interpolation and final mix;
  the native recompiled sound study measured this separately in
  `docs/issues/native-sound.md` section 4.
- **Unknown:** the purpose of the 48 kHz labels. A listening check is what would
  settle whether those entries are mislabelled. The loop-restart field is executed
  above; no NTSC record has been observed nonzero.
