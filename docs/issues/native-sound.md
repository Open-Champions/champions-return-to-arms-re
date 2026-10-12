# Sound for the native build

Started 2026-10-12. The recompiled game (`docs/issues/native-recomp.md`) runs without its
I/O processor, and sound on the console is made entirely there. This file documents what
the game asks of the sound side, how the host-side replacement in `tools/recomp/sound/`
answers, and how its output compares with the emulator's. Every statement says how it is
known: **Read** (in the disassembly of the game or of the driver modules on the disc),
**Ran** (measured here), **Not reached**.

Nothing in the repository is derived from the game: the modules' listings, captures and
all audio stay under `local/sound/`.

## Notes for whoever continues (kept current)

- State (2026-10-12): library written and linked into the native build; the native build
  boots to the hub with sound rendered to a WAV; streams and one deterministic effect match
  the emulator to the waveform (section 4). Open: section 6.
- Local working files, all under `local/sound/`: `irx/` (the three modules cut from the
  disc, their listings and Ghidra output), `cap/` (rig scripts `capture*.rig`, `title.rig`,
  the rig capture `cap.log` and its converted form `cap.bin` — game data, kept for
  repeating the replay), `bin/` (`sndtool`, `sndcmp`, `rta_native_sound`), `match/` (the
  two throw-away scripts of 4.4). Every WAV, the emulator reference runs and the samples
  cut from the capture were deleted after the measurements.
- To repeat everything: section 7.

## 1. The interface

### 1.1 Who the game talks to

**Read** (module list in the loader calls of the boot, `sceSifBindRpc` 0x356510 with its
callers, the three modules' code). The game loads three sound modules from `\BG\0MOD\`:

| Module | Remote-call server | What it is |
|---|---|---|
| `LIBSD.IRX` | — | Sony's sound library (identifies itself as `libsd 3020`): the functions that touch the SPU2 chip |
| `SDRDRV.IRX` | 0x80000701 | Sony's "sound remote" (banner: version 4.0.1): one remote call per `LIBSD` function |
| `HELLO.IRX` | 0x000163a5 | the game's own stream driver: three streams fed from ring buffers, a 6 ms timer |

There is no sequencer, no sample-bank format of Sony's and no reverb library: sound
effects are raw register writes to the chip, decided on the main processor; music and
speech are ADPCM data read from the disc and pushed through the stream driver.

Calls are made with `sceSifCallRpc` 0x3566f0 in blocking mode. Client structures:
0x8f6140 (sound remote, bound by `sceSdRemoteInit` 0x35ece0) and 0x877160 (stream driver,
bound by `sound_init` 0x212f08).

### 1.2 The sound remote, 0x80000701

All calls go through one function, 0x35ee38 (`sceSdRemote(blocking, command, ...)`, 47
call sites). It copies six argument words to the block at 0x8f6100 behind a first word
that holds the block's own address, and sends 0x40 bytes; the answer is 0x10 bytes into
the same block, word 0 being the function's result (the other three words come from the
driver's static data and are 0). The command is the remote-call function number; for the
three effect calls the core is or-ed into it and the block sent is the caller's effect
structure instead. **Read** in 0x35ee38 and in the driver's dispatcher (SDRDRV+0x588).

A register is named as `LIBSD` names it: `entry = register << 8 | voice << 1 | core`
(volumes 0x09…0x10 also carry 0x80).

| Command | `LIBSD` function | Arguments (words 1…) | Answer | Sent from | When |
|---|---|---|---|---|---|
| 0x8000 | `sceSdInit` | 0 | 0 | 0x212980 | once, `sound_init` |
| 0x8010 | `sceSdSetParam` | entry, value (16 bit) | — | 0x212980, 0x2165a8, 0x2156e0 | start-up; level change; mute on reset |
| 0x8030 | `sceSdSetSwitch` | entry, 24-bit mask | — | 0x212980, 0x2156e0 | start-up; level change |
| 0x8040 | `sceSdGetSwitch` | entry 0x1700 / 0x1701 (voice end flags) | 24-bit mask | `sound_update` 0x212670 | both cores, every 8th sound frame |
| 0x8050 | `sceSdSetAddr` | entry 0x1d01 (effect area end, core 1), 0x1fffff | — | 0x2156e0 | level change |
| 0x8070 | `sceSdSetCoreAttr` | 3 (effect enable, core 1), 1 | — | 0x2156e0 | level change |
| 0x80b0 | `sceSdProcBatch` | I/O-processor address of the batch, 0 (no result array), count | count | `sound_flushSpuCommands` 0x210cd0 | at most once per sound frame, when there are commands |
| 0x80d0 | `sceSdVoiceTrans` | channel 0, mode 0 (write, by DMA), I/O-processor address, SPU2 address, size | size rounded up to 64 | `sample_uploadToSpu` 0x213ff0 | per piece of ≤ 0x1000 bytes of a sample, at lump load |
| 0x80f0 | `sceSdVoiceTransStatus` | channel, 1 (wait) | 1 | 0x213ff0, 0x2156e0 | after every piece |
| 0x8190 | `sceSdCleanEffectWorkArea` | core 1, channel, effect mode | 0 | 0x2156e0 | level change |
| 0x81a0 \| core | `sceSdSetEffectMode` | the structure | 0 | 0x2156e0 | level change |
| 0x81b0 \| core | `sceSdSetEffectModeParams` | the structure | 0 | 0x2156e0 | level change |
| 0x8140 \| core | `sceSdGetEffectAttr` | — | the structure | 0x216b58 | never (the function has no caller) |
| 0x8160, 0x8170, 0xe620, 0xe630 | interrupt / transfer handlers and their thread | | | library code at 0x35f1c0… | never seen in a boot |

Effect structure (0x14 bytes): `{ s32 core; s32 mode; s16 depth_left, depth_right; s32
delay; s32 feedback; }`. The game fills everything but `core`.

**A batch** is an array of 8-byte commands `{ u16 function; u16 entry; u32 value; }` that
the game builds at `g_spuCmdBatch` 0x875c00 (at most 512), copies to I/O-processor memory
(to the address in 0x4f89e4, 0x12ec00 in a boot, with 0x35ed90 = `sceSifSetDma` and a
wait) and then names in command 0x80b0. Functions used: 1 set parameter, 2 set switch,
3 set address. `LIBSD` also knows 4 (core attribute), 5–7 (write a word to I/O-processor
or main memory) and 0x11–0x14 (the matching reads); the game does not use them.

What the game puts in a batch (**Read**; **Ran**: the capture below holds nothing else):

| Written by | Commands |
|---|---|
| `voice_setVolume` 0x213a78 | VOLL (register 0), VOLR (1) of one voice |
| `sound_playSample` 0x2134e8 | VOLL, VOLR, PITCH (2), SSA (0x20: start address), ADSR1 (3) = 0xff, ADSR2 (4) = 0x1fc0, LSAX (0x21: loop address) = 0x5000 |
| `sound_pauseResumeVoices` 0x212340 | PITCH = 0 for voices frozen with the game, the stored pitch afterwards |
| `sound_flushSpuCommands` 0x210cd0 | last in the batch: key-on mask (switch 0x15) of each core with the bits of the key-off mask removed, then the key-off mask (0x16) |

So a new sound is: registers, then key-on, in one batch; a stopped sound is a key-off bit.

### 1.3 What the chip is asked to be

**Read** in `LIBSD` (initialisation at +0x48e4, +0x4644, +0x4344, +0x1638) and in the game.

- Two cores of 24 voices. The game uses **43 effect voices**: its voice n is core 0 voice
  n for n < 24 and core 1 voice n − 24 above (table 0x4f8960); `voice_alloc` 0x2169f8
  walks them round robin. The stream driver owns core 1 voices 19–23.
- **Start-up state** (`sceSdInit`, then 0x212980): a 16-byte silent block with flags 7
  (start, end, repeat: it loops to itself) is uploaded to SPU2 address 0x5000 and every
  voice is pointed at it and keyed on and off, which leaves every voice's end flag set.
  Master volume 0x3fff on core 0 and `0x3fff × the float at 0x877244` on core 1; effect
  volumes 0; core 1 takes core 0's output at 0x7fff (AVOL); pitch modulation and noise
  off for all voices; MMIX 0xc00 on core 0 (voices to the dry output) and 0xc0c on core 1
  (voices and core 0 to the dry output).
- **Sample memory.** 0x5000: the silent block. 0x5010, 0x6010, 0x7010: the three stream
  buffers of 0x1000 bytes. Samples from 0x8040 upward, each 64-byte aligned, in load
  order (`sample_register` 0x2130d0). A sample that would reach into the effect work area
  is given address 0x5000 instead (silence).
- **A voice.** Pitch register × 48000 / 4096 Hz, clamped to 0x3fff. Volumes 0…0x3fff per
  side (the game never uses the sweep modes or negative volumes). Envelope registers
  always 0xff / 0x1fc0: attack at the fastest rate (full level after 3 samples), no
  decay (sustain level 15), sustain rate 0x7f rising (the level stays), release linear at
  rate 0 (silent 2 samples after key-off). **The envelope is a gate**; every shape that is
  heard is in the sample data or in the volume registers the game rewrites.
- **Looping** is in the ADPCM data: flag 4 on a block makes it the loop address, flag 1
  ends the sample — with flag 2 the voice continues at the loop address, without it the
  voice is silenced. The game sets the loop address to 0x5000 before every key-on, so a
  sample without a loop start ends up on the silent block.
- **End detection.** Every 8th sound frame `sound_update` reads the end flags of both
  cores and frees every non-looping voice whose flag is set. A key-on clears the flag;
  reaching a block with flag 1 sets it.
- **Effects (reverb).** At every level change 0x2156e0 sets the effect mode and its
  parameters from four 16-bit fields of the level's row in `g_levelTable` (row + 0x24:
  mode, depth, delay, feedback), routes core 1 voices 0–18 and core 0's whole output to
  the effect input (VMIXE 0x7ffff, MMIX 0xf0f) and enables effects. **All 91 rows hold
  mode 0 (off), depth 0, delay 0, feedback 0** (**Ran**: counted in the executable's
  data; both level changes of the capture send exactly that). With mode "off" `LIBSD`
  writes effect volume 0. The game therefore has no reverb, and the effect processor is
  not part of what has to be built.
- **3-D position** never reaches the chip as such. `sound_panAtten` 0x213c50 turns a
  position into a left and a right factor on the main processor (full volume inside 360
  units of the camera, silent at 840, pan from the dot product with the camera's right
  vector; `docs/audio-save.md`), `voice_setVolume` scales by the effects volume option
  and writes VOLL / VOLR. A moving sound is rewritten volumes, once per sound frame at
  most. Pitch is the sample's base pitch (rate × 4096 / 48000) times the event's pitch
  factor.

### 1.4 The stream driver, 0x163a5

Documented from the module's code in `docs/formats/anim-audio.md` section 3.4 (commands,
data layout of `.VAT` entries, voices). Verified again here against the disassembly and
restated only as far as the replacement needs it. Calls send up to 0x10 bytes from
0x877200 and receive 0x40 bytes at 0x8771c0. **Every** call is answered with the same
0x40 bytes of the driver's memory: twelve words of status as command 0x50 last filled
them, then the driver's copy of the arguments.

| Command | Arguments (words) | Effect |
|---|---|---|
| 0x30 | stream, ring address in I/O-processor memory, ring size | clear the stream's state, set its ring. Sent three times before 0x20: rings of 0x19000, 0x1e000, 0x40000 bytes |
| 0x20 | — | key off core 1 voices 19–23; give each volume 0x3fff, pitch 0x7fe, start and loop address 0x5010 + stream × 0x1000, envelope 0xff / 0x1fc0; fill the three SPU2 buffers with silence (every block flag 2, the first 6, the last 3); per stream target volume 0x3fff, volume 0, scale 0x100; streams 0 and 2 get two voices; key on; timer after 10 ms |
| 0x40 | stream, bytes added, sample rate (stored, never used), s16 two-channel flag, s16 flags (1: first piece of an entry — restart the played counter) | the game has put that many bytes into the ring (disc read straight into I/O-processor memory); queued (32 entries) |
| 0x50 | — | status: per stream write position, read position, current volume, bytes played |
| 0x60 | stream | round the write position up to 0x800, read position = write position, played = 0, queue emptied |
| 0x70 | stream, target volume (0…0x3fff) | the timer moves the volume there: −0x20 per tick, +0x40 (stream 0) or +0xc0 (streams 1, 2) |
| 0x80 | two-channel output on/off, three volume scales (0x100 = 1) | voice volume = volume × scale >> 8; with two-channel output a two-voice stream plays hard left and hard right, without it both voices on both sides |
| 0xb0 / 0xa0, 0xc0 | — | stop the timer; start it again (first tick after 10 ms). Sent around every sample upload, because the timer and the upload use the same transfer channel |
| 0x10, 0x90 | | read voice 19's envelope; load a module. Not sent in a boot |

**The timer** (every 6 ms; **Read** HELLO+0x0…0x9d4): volumes as above; then, for the
first stream in the order 1, 0, 2 whose voice has crossed into the other half of its
0x1000-byte SPU2 buffer since the last look (the chip's read address NAX against
buffer + 0x800), it copies the next piece of the ring into the half just left:

| Stream | Piece | Layout in the half | How the voice gets there |
|---|---|---|---|
| one voice (1) | 0x800 bytes | one channel | first block of the buffer flagged 6, last block flagged 3: a plain loop |
| two voices (0, 2), two-channel entry | 0x800 bytes | 0x400 left, 0x400 right | each voice plays its 0x400; the last block of each is flagged 3 and the two loop addresses are rewritten to the other half's pieces |
| two voices, one-channel entry | 0x400 bytes | the same 0x400 twice | as above |

The flag byte of every block is overwritten (2 = inside a loop), so the flags in the
files do not matter. When the ring holds less than a piece, silence is copied and the
stream counts as stopped until a piece is available. Only one stream is served per tick.

**Rates.** A stream voice plays at pitch 0x7fe = 23,976.6 Hz whatever the entry says. One
voice consumes 0x800 bytes (3,584 samples) every 149.5 ms; a two-voice stream 0x800 bytes
every 74.7 ms.

### 1.5 Timing

**Read** `sound_update` 0x212670; **Ran**: call counts of a captured boot (6,000 fields,
19,511 remote calls in all, of them sound: see "Results").

| What | How often |
|---|---|
| `sound_update` | once per displayed frame (a "sound frame") |
| register batch 0x80b0 | once per sound frame if anything changed |
| end flags 0x8040 × 2 | every 8th sound frame |
| stream status 0x50 | from `stream_serviceQueues` every 4th sound frame, and from every `audio_streamStatus` / `audio_streamPosition` call of game code (two a frame on average in the capture: music ducking, dialog, lip sync) |
| stream data 0x40 | when the game has read more from the disc: up to 0x7f sectors (0x3f800 bytes) at a time into the music ring |
| sample upload 0x80d0 | only while lumps load |
| stream driver timer | every 6 ms on the I/O processor, independent of frames |

All calls block the calling thread until the I/O processor has answered; the game takes
positions and end flags as "now".

**How the game feeds a stream** (**Read** `stream_serviceQueues` 0x211df8,
`stream_startQueued` 0x211548; **Ran**: the sizes below are the capture's). The service
runs every 4th sound frame and does nothing while the disc is busy with anything else. It
finishes at most one read (command 0x40 with the bytes read) and starts at most one: for
the first stream, in the order 0, 1, 2, whose ring is at least half free it reads
`min(what is left of the entry, free space up to the ring's end)` rounded to 0x800, straight
into the ring. So music arrives in pieces of 0x20000 bytes every 4.8 s (0x3f800 for the
first), speech on stream 0 in pieces of 0xc800 every 3.7 s. An entry queued with flag 2
first fades what is playing: command 0x70 with target 0 every service round until the
status shows volume 0 (3.07 s from full volume), then 0x60 and 0x70 with 0x3fff.

## 2. Approach

**(a) Re-implement the behaviour, on an SPU2 core of our own.** Not (b), running the
modules.

- The effects interface *is* the chip's register set (through `LIBSD`'s numbering), so a
  model of the chip — voices, ADPCM, envelope, pitch, the two cores' mix — is needed in
  either case and is most of the work.
- What sits on top is small: `SDRDRV` is a dispatcher (14 commands used) and `LIBSD` is
  register arithmetic; `HELLO` is one command handler and one timer routine, about 1,170
  instructions together. Written from their behaviour they are 300 lines.
- Running the modules instead would need an R3000 interpreter or a second static
  translation, an I/O-processor kernel (threads, alarms, semaphores, interrupt handlers,
  the remote-call server loop, DMA) and the chip's registers at hardware level (address
  split into high and low words, transfer by DMA with status bits and interrupts) —
  all of it code that exists only to carry the two small drivers, and the modules would
  have to ship with the program or be loaded from the user's disc.
- Nothing is lost: the game needs no reverb (1.3), which is the one large piece of
  `LIBSD` data (its preset tables) that a re-implementation would otherwise have had to
  take from the disc.

## 3. The library

`tools/recomp/sound/` — portable C++17, no dependency besides the standard library (and
the host's sound API in one file).

| File | Holds |
|---|---|
| `rta_sound.h` | the interface: `Spu2`, `Engine` (the two servers and the time line), `AudioSink` |
| `spu2.cpp` | the chip: 2 × 24 voices over 2 MB, ADPCM decoding, four-tap interpolation, ADSR, volumes, the cores' mix, end flags, the registers as `LIBSD` numbers them |
| `drivers.cpp` | `SDRDRV` + `LIBSD` command set; `HELLO`'s commands and timer; `Engine::advance_to` |
| `audio_out.cpp` | WAV writer; ring buffer with a held reserve and rate correction; the macOS device (AudioQueue) |
| `sound_rta.cpp` | **the file the runtime links** in place of `rt/sound_null.cpp`: `sound_rpc`, `sound_vblank`, `sound_report`, nothing else; includes the three files above |
| `sndtool.cpp` | tests without the game: replay of a capture through `sound_rpc`, one sample, one stream, cost |
| `sndcmp.cpp` | numeric comparison of two recordings |
| `capture.py`, `emuref.py` | make a capture from a rig log; run a rig script on the playable emulator build and keep its WAV |
| `irxdis.py` | disassembler for the I/O-processor modules (listing stays under `local/`) |

**Connection to the runtime.** `python3 tools/recomp/build.py run --sound
tools/recomp/sound/sound_rta.cpp`. The file uses `g_ram`, `iop_ram()`, `rt_cycles()` and
`rt_option()`. Time: one 48 kHz sample is 6,144 cycles of the virtual clock; at every
remote call and every vertical blank the mixer renders up to "now" first, running the
stream timer at its sample positions (every 288 samples), so a register write or a status
read lands on the sample it would land on. Options (`--opt key=value`): `sound-wav=FILE`,
`sound-out=device`, `sound-gain=0..1`, `sound-latency=MS` (default 40),
`sound-interp=gauss|linear|nearest`, `sound-off=1`; for tests `sound-out=timer` (a stand-in
device that only keeps time), `sound-solo=effects|streams|stream0|stream1|stream2`,
`sound-log=FILE` (every remote call with its arguments and answer). Without an output the
chip still runs (voices end, streams advance) and nothing is kept.

**Host back end.** `AudioSink` is two functions. The device sink keeps a ring between the
renderer (virtual clock) and the device (its own clock): playing starts when the reserve
is queued, and the read rate is corrected by at most 0.5 % towards the reserve, with
four-point interpolation, so the two clocks may differ; a burst of more than 200 ms above
the reserve (the machine catching up after standing still) is given up at once. macOS:
AudioQueue with three 10 ms buffers, looked up with `dlopen` (no link flag needed). **Windows is not written**:
it needs the same pull function behind WASAPI (shared mode, event driven:
`IAudioClient::Initialize`, a thread waiting on the event, `IAudioRenderClient::GetBuffer`)
or, with less code and more delay, `waveOutWrite` with three buffers; nothing else in the
library is host specific.

**Offline.** `sound-wav=FILE` writes everything rendered, 48 kHz 16 bit stereo, in machine
time from power-on.

### What is not there

| Not modelled | Why it does not matter here | What would show it |
|---|---|---|
| effect processor (reverb) | every level sets mode off, depth 0 (1.3) | the report line "NOT HANDLED: … effect modes other than off" |
| the chip's interpolation table | it is in the chip's ROM; replaced by a Gaussian of σ = 0.567 samples at the four taps, unit gain — the same soft treble, not the same numbers | — |
| volume sweep modes, pitch modulation, noise | never written by the game or the driver | report: "sweep volumes" |
| block transfer (the chip's PCM input), SPDIF, interrupt on address | not used | — |
| time a transfer takes | uploads are instant here; on the console the stream timer skips a tick while one is in flight | — |
| `LIBSD` calls never made (note/pitch conversion, `ProcBatchEx`, `BlockTrans`) | no call site in the game | report: "unknown or refused commands" |
| sample memory of a machine resumed from a memory image | the image has no SPU2 memory; a key-on at memory never uploaded is answered as "ended" at once so the game's voice table keeps turning over; streams stay silent because the rings were never announced | report: "key-ons at memory never uploaded" |


## 4. Results

All **Ran** on 2026-10-12 on an Apple M5 Pro (18 cores) that was busy with other jobs the
whole time: load average between 40 and 410. Times are given with the load beside them
where it matters.

### 4.1 Self test (no game data)

`sndtool selftest` encodes its own ADPCM and checks the chip and the stream driver against
what section 1 says. 19 checks, all pass:

| Check | Measured |
|---|---|
| a one-shot at pitch 0x1000, no interpolation, is the decoded data | correlation 1.000000, one sample after the key-on |
| gain through voice, core 0, core 1 at full volumes | 0.99979 (0x7ffe / 0x8000 three times, 0x7fff once) |
| silent after the block flagged 1; end flag set then | yes |
| key-on clears the end flag; it is set 2,800 samples later for 100 blocks | yes |
| tone frequency follows pitch / 0x1000, six pitches 0x400 … 0x3fff | worst error 7.4 ppm |
| length is samples × 0x1000 / pitch, six pitches | end flag within ±200 samples |
| attack: full level within 3 samples; release: silent within 3 | 0, 25081, 28664, 28664; 14331, 0, 0 |
| loop: the data from the block flagged 6 follows the block flagged 3; 200 rounds identical | yes |
| volume registers 0x3fff / 0x2000 / 0x1000, one side at 0 | 0, −6.02, −12.04 dB; other side silent |
| one-voice stream: rate | 599.41 Hz for 599.41 expected (0.0 ppm of 23,976.6 Hz) |
| one-voice stream: length, counters | 5.979 s for 5.979 s of data; read = write, played = bytes |
| no seam where the buffer halves change (40 pieces; 80 on two voices) | largest period error 0.006 samples |
| two-channel entry: left pieces left, right pieces right | 599.41 Hz left, 428.15 Hz right |
| one-channel entry on a two-voice stream | identical on both sides |
| stream volume ramp and scale | 0x3000 after 70 ticks; level 0.3749 for 0.3750 |

### 4.2 Replay of a captured boot

A rig run from power-on through the menus and character creation into the hub, then
walking, attack presses and a wait (6,000 fields; script `boot-to-hub.rig` plus 30 lines).
The capture holds 18,359 sound calls, 934 copies to I/O-processor memory (2.08 MB of
samples and 191 register batches) and 34 disc reads into the stream rings. `sndtool
replay` plays it through `sound_rpc` / `sound_vblank` of `sound_rta.cpp` — a stand-in
runtime with a clock, the two memories and options, nothing else: 102 s of sound, 277
key-ons, 229 voices ran to their end, nothing unknown, nothing refused; 1.3 s of
processor time.

### 4.3 Against the emulator: what is the same data on both sides

The reference is the playable emulator build writing its mix to a WAV (44.1 kHz), driven
by the same script (`emuref.py`). Effects use random pitch, volume and choice of sample,
and the two runs are not the same run, so the comparison is made on what is determined:
streams (the same bytes from the disc) with the game's effects volume poked to 0 in the
emulator and the effect voices left out of our mix, and effects with the music volume
poked to 0.

**One fact about the reference first.** The emulator plays a stream voice **421 ppm
slow**: it turns pitch 0x7fe into a step of 48000 × 0x7fe / 44100 = 2226.94 / 4096 per
output sample and drops the fraction. Measured: +417 ppm of drift against ours over 13 s.
Ours runs at the driver's nominal 23,976.6 Hz (self test: 0.0 ppm). The figures below
read the reference with its clock corrected by 421 ppm (`sndcmp --b-rate-ppm 421`);
without the correction the two waveforms slide apart by 0.4 ms a second and only
loudness and spectrum can be compared.

| Event | Ours | Waveform correlation | Level, reference − ours | Envelope (10 ms) | Drift |
|---|---|---|---|---|---|
| title music, 15 s (two-channel entry on stream 2) | replay | 0.9995 mono, 0.9994 left, 0.9999 right; residual 30.4 dB down | +0.07 dB left, 0.00 dB right | correlation 0.9999, median difference 0.04 dB | 0.0 ppm |
| title music, **62 s** | the disc entry fed through the stream driver by `sndtool stream` | 0.9968 mono, 0.9933 left, 0.9994 right | (rendered at scale 0x100; the game's 0x64 is the 8.1 dB seen) | 1.0000 | **+0.8 ppm over 50 s (0.04 ms)** |
| title music, 15 s | **the native build** (recompiled game, `rta_native` + `sound_rta.cpp`) | 0.9991 mono, 0.9988 left, 0.9998 right | +0.07 / 0.00 dB | 0.9999, 0.04 dB | +1.4 ppm |
| hub: narration line (one-channel entry on two-voice stream 0) and music together, 20 s | replay, each stream alone against the emulator's mix of both | narration 0.7746, music 0.6197: together 98.4 % of the mix's energy; gain 0.9954 each | mix: +0.12 / +0.04 dB | — | 0.0 / 1.0 ppm |
| the same stretch | the native build with `--emulator-timing` | mix against mix 0.66 (the two streams start 0.3 s apart differently in the two runs) | +0.06 / −0.01 dB | — | — |
| race voice at character selection: an effect with fixed pitch 0x800 and volume 0x1fff | replay, effects only | 0.845 over 2.2 s with the title's random ambience under it; 0.986, 0.993, 0.973 in the half seconds where the voice carries | +0.03 dB | 0.907 | — |
| the same | the native build | 0.958, 0.991, 0.983 in the same half seconds | −0.09 dB | 0.938 | — |

Spectrum, title music, third-octave bands, reference − ours: within 0.1 dB up to 1.6 kHz,
+0.3 dB at 2.5 kHz, +0.7 at 4 kHz, +1.7 at 6.3 kHz, +2.8 at 8 kHz, +10.8 at 16 kHz. The
emulator interpolates linearly, which leaves images of a 24 kHz source above 12 kHz
(−22 dB in its band at 16 kHz, where the data has nothing); ours uses a four-tap Gaussian
as the chip does. With `sound-interp=linear` ours has the emulator's kind of treble.

### 4.4 Against the emulator: effects with random pitch

For an effect whose pitch is drawn at random the emulator's parameters are not known.
Method: the sample is cut from the capture, rendered alone at **every whole value of the
pitch register** in the range the game uses for it, and each render is looked for by
waveform in the emulator's effects-only recording (`sndcmp --by-waveform 1`). Check of the
method on the fixed-pitch voice above: register 2048 (the true one) gives 0.914, its
neighbours 2047 and 2049 give 0.65 and 0.61.

| Sample | Found | Notes |
|---|---|---|
| armour foley of a footstep (0.28 s, 16 kHz) while walking | waveform correlation 0.843 at register 1415 (factor 1.036) and 0.830 at 1260 (0.923), envelope correlation 0.96 | two instances; both factors inside the range the capture shows for these events (0.87 … 1.22) |
| attack swing "whoosh" (0.41 s) | 0.32 | not conclusive: a swing is three samples at once, each chosen at random among variants |
| wind loop of the title screen (0.96 s) | not found | not conclusive |

Stretches full of random effects can only be compared by loudness and spectrum, since the
events themselves differ between the two runs: title screen ambience, 7.5 s: reference
2.9 dB lower, bands within 2.7 dB on average; hub, walking and swings, 16.4 s: reference
0.6 dB higher, bands within 2.6 dB.
Full mix of the native build against the emulator's in the hub, 25 s: −0.5 / −0.8 dB.

### 4.5 The native build with sound

`sound_rta.cpp` compiled with the runtime's flags exports exactly `sound_rpc`,
`sound_vblank`, `sound_report`; linked with the runtime's objects in place of
`rt_sound_null.o` (the objects of `local/recomp-out/obj-run` as built at 09:14; a full
`build.py run --sound … --name …` was not run, to spare the machine).

- `native.py boot --script capture.rig --opt sound-wav=…`: power-on to the hub and through
  the script, 4,275 fields = 71.3 s of machine time in **17 s** of wall time (load average
  about 45), nothing unanswered. Sound: 0.63 s of processor time (0.88 % of the machine
  time rendered), 277 key-ons, 2,082,176 bytes of samples — the same counts as the rig
  capture. Three runs gave the same counts and field numbers.
- With `--emulator-timing` the game makes its stream calls at the rig's times to within
  0.2 s (title music announced at 22.44 s for 22.41 s; hub narration 47.58 for 47.38; hub
  music 48.99 for 48.98).
- **Without it the hub music is lost** (found here, not a sound fault): loading is so much
  faster than on a console that the level's script queues its music 2.6 s after the level
  change began, while the game is still fading the title music out for the stop markers
  of the level change (3.07 s). The stream call log (`sound-log`) shows five
  fade-and-start rounds on stream 2 and then no read for it; 26 s later a short entry of
  0x2f800 bytes plays there instead (by its size an ambience one-shot, not the 0x1ba000-byte
  music). The narration on stream 0 is unaffected. In the rig the same load takes 6.2 s
  and the order never arises. Which of the game's queue rules drops the entry was not
  traced.

## 5. Cost and latency

**Processor time** (`sndtool bench`: every voice playing a looping sample at its own
pitch; load average 40 to 50 at the time):

| Voices | Processor time for 60 s of sound | Share of one core |
|---|---|---|
| 43 effect + 5 stream | 1.5 to 1.8 s | 2.5 to 3.0 % |
| 16 effect + 5 stream | 0.81 s | 1.35 % |
| 5 stream only | 0.22 s | 0.37 % |
| the game itself, power-on to the hub (4.3) | 0.63 s for 71 s | 0.88 % |

A voice that has ended costs nothing (it is parked on the silent block).

**Latency.** In machine time there is none to speak of: a register write takes effect on
the sample at which the call is made, and the sound is rendered up to "now" at every call
and every vertical blank, so what reaches the output is at most one field (16.7 ms) behind
the machine. To the ear it is the device path: the held reserve + the device's queue.

| | Reserve asked | Held on average | Least | Ran dry |
|---|---|---|---|---|
| replay in real time, 30 s, load average 215 | 40 ms (default) | 60 ms | 27 ms | never |
| the same, load average 223 | 20 ms | 46 ms | 4.6 ms | 3 times, 6 ms of silence |

(The average is above the reserve because sound arrives a field at a time, 800 samples.)
Measured with `sound-out=timer`, a thread that takes 10 ms of sound every 10 ms and
discards it. **The real device was not exercised**: from this agent's shell
`AudioQueueStart` answered −66681 (cannot start), so the AudioQueue path is compiled and
opens its queue but has not played; no sound was made at any point. With AudioQueue's
three 10 ms buffers in front of the device, expect about 40 + 8 + 25 ≈ 75 ms from the
game's call to the device at the default reserve (the emulator build holds 71 ms queued:
`tools/play-net/README.md`).

## 6. What matches, what does not, what was not reached

- **Matches the emulator to the waveform**: streams of both kinds (two-channel music,
  a one-channel line on a two-voice stream), in replay, standalone from the disc, and from
  the native build; one fixed-pitch effect; level within 0.1 dB everywhere it could be
  measured on the same data; no drift over a minute once the emulator's own 421 ppm is
  taken out.
- **Matches by shape**: a footstep's armour foley found at two register values with 0.84.
- **Differs, known**: treble above 4 kHz (interpolation, 4.3); stream rate (the emulator's
  421 ppm); time line (the emulator makes 735 samples at 44.1 kHz per field, 1/60 s; ours
  follows the virtual clock, 800.8 samples at 48 kHz per field of 1/59.94 s).
- **Not shown**: swings, hits and the title's ambient loops could only be compared by
  loudness and spectrum (within 3 dB with different random draws); loop points of the
  game's own 28 looping samples were checked by the self test's loop only, not against
  the emulator.
- **Not reached**: a hit on an enemy and a spell (the script stays in the hub, where there
  is nothing to hit); the front end's menu moves start no sample in the capture, so there
  was no menu sound to compare; speech on stream 1 (dialog with a character; the one-voice
  path is covered by the self test only); a second level's sample set; the real sound
  device; Windows.
- **For the runtime's author**: the lost hub music under fast loading (4.5).

## 7. How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
mkdir -p local/sound/bin local/sound/cap
clang++ -std=c++17 -O2 -I tools/recomp/rt tools/recomp/sound/sndtool.cpp -o local/sound/bin/sndtool
clang++ -std=c++17 -O2 tools/recomp/sound/sndcmp.cpp -o local/sound/bin/sndcmp
local/sound/bin/sndtool selftest
local/sound/bin/sndtool bench

# a capture from the rig (break points: head of capture.py), then the replay
python3 -I -B tools/recomp/sound/capture.py local/sound/cap/cap.log local/sound/cap/cap.bin
local/sound/bin/sndtool replay local/sound/cap/cap.bin local/sound/cap/replay.wav --iso "$RTA_DISC" \
    --events local/sound/cap/replay-events.tsv [--opt sound-solo=streams]

# the emulator's WAV for the same script (silent background window, offline, new data directory)
python3 -I -B tools/recomp/sound/emuref.py --disc "$RTA_DISC" --data local/sound/emuref/run1 --script SCRIPT.rig
#   effects volume 0: script line  poke 0x4f8940:f32 0   music volume 0:  poke 0x4f8944:f32 0
local/sound/bin/sndcmp local/sound/cap/replay.wav local/sound/emuref/run1/sound-*.wav \
    --a-start 23 --a-len 15 --b-start 21 --search 4 --b-rate-ppm 421

# the native build with sound
python3 tools/recomp/build.py run --sound tools/recomp/sound/sound_rta.cpp --name rta_native_sound
RTA_NATIVE=local/recomp-out/bin/rta_native_sound python3 tools/recomp/native.py boot --emulator-timing \
    --card local/sound/native/card --script SCRIPT.rig --opt sound-wav=local/sound/native/native.wav
```

WAV files, captures and anything cut from them are game data: under `local/` only, WAVs
deleted after use.
