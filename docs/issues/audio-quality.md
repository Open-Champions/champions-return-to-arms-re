# Audio quality: is the sound damaged? (2026-10-26)

The owner reported that the music sounds like static. Nobody here can listen, so the output was
**recorded in the process and measured** against the original game (the emulator build), for the
native program (`rta_app`), the Godot build in Remastered and in Classic, and the Remastered boss
music (the player's own Elden Ring tracks). Every recording stays under `local/audio-quality/`;
nothing game-derived is in the repository.

## Verdict

- **The game's own sound is not damaged in any of our builds.** In every run (native, Godot
  Remastered, Godot Classic; 120 Hz and 60 Hz; idle and with the processor overloaded) there were
  **0 zero-filled gaps, 0 dropouts, 0 one-sample jumps in the music, 0 samples at full scale in the
  music**, pitch within 0.5 to 1.4 cents of the original (the original's emulator itself runs
  0.7 cents slow: `native-sound.md` 4.3), and spectral flatness 0.0004 to 0.0011 during music
  (music is 0.01 or less; noise is 0.5 to 1). The title music matches the emulator's **waveform**
  at 0.998 (left 0.997, right 0.9996), and the native program's and Godot's outputs are
  **bit-identical** to each other (residual 99 dB down).
- **What was wrong is the Remastered boss music** (the player's Elden Ring tracks, both builds):
  it came in **11 to 13 dB louder than the game's music** (RMS -14 to -17 dBFS against the game's
  music at -24 to -33), its peaks reached full scale, the native program's 16-bit decode **clipped
  the tracks' own overs flat** (55 of the 82 tracks hold samples over full scale, up to +0.8 dB:
  105,424 clipped samples in all), and with the game's effects on top the sum went **past full
  scale** (106 samples clipped in a 4-minute native run, 16 samples over 1.0 in Godot). Fixed:
  each track is brought to the game's music level, decoded in floating point, and the sum is bent
  smoothly instead of cut (below).
- **Measuring itself could make a gap** in the native program: `sound-wav` wrote the file on the
  device's real-time thread, and one write held the device for 150 ms (a 160 ms gap in what is
  heard; the file does not show it). The WAV writer now has a thread of its own: 0 late requests
  since, under load as well.

Loud, noisy stretches in the measurements (the `fearboss` fight burst, monsters attacking a
standing player in `arachna1`, `nitbon2`, `storm3`) are **the game's own**: the original is as loud
and in fact clips more (below).

## How it was measured

**The taps** (in the process: the samples handed to the device, never a loopback; nothing heard):

| Build | Tap | What it records |
|---|---|---|
| native `rta_app` | `-- --opt sound-wav=FILE` (a test run: `--test`, device gain 0) | what the sound side renders into the device's buffers, on the device's real-time thread (`sound-clock=real`); the device's own request timing is counted by `PullCount` (gaps between requests, render time) |
| Godot | `--audio-tap FILE.wav` (new, `tools/godot/project/dev/audio_tap.gd`) | Godot's master bus from an `AudioEffectCapture` at its head, 32-bit float at the mix rate: the game's stream and the boss music after Godot's resampling and bus volumes. It sits before the bus's mute, so `--mute`/`--test` runs record everything silently. `FILE-clock.tsv`: wall time against seconds captured and seconds the mixer asked of the game (a callback the device skipped shows as a deficit); `FILE-marks.tsv`: `app audio mark NAME` script lines; `app audio engage on|off|auto` engages the boss music director by hand |
| emulator (the original) | `tools/recomp/sound/emuref.py` (`--rta-sound-wav`) | what the emulated SPU2 hands over, 44.1 kHz |

**The route** (the rig's script language, the same moments everywhere): power-on, the title menu
(20 s of title music), the hub (30 s), `fire1` (30 s), `fearboss` (30 s, later 90 s), then in
Remastered the boss music director engaged for 30 s (`app audio engage on` / `app music engage
on`). A short route (title, hub, `fire1` + boss music) for the load runs. The emulator route is
the same without the `app` lines.

**The analysis** (`tools/recomp/sound/audiocheck.cpp`, new; `sndcmp.cpp` for waveforms): per
segment, peak and RMS; samples at full scale; zero-filled gaps (exact zero for 1 to 250 ms with
sound on both sides); one-sample jumps over a quarter of full scale; clicks (second differences
12 x their surroundings); 10 ms dropouts; spectral flatness (200 Hz to 15 kHz), the share of power
above 10 kHz, the noise floor; and against the emulator's same segment, the pitch (the frequency
scale at which the long-term spectra match best, in cents) and the level.

**Load:** 24 to 48 processes spinning on the 18 cores (load average 41 to 117) through the route.
**Display rate:** Godot at `--display-rate auto` (120 Hz on this display: two pictures per game
frame) and `60`. The native program paces to 60 on the 120 Hz display.

## Numbers

### Before the fix (the builds as they are on main)

Per segment, inner part (2 s cut at each end). Gaps, jumps, clicks and dropouts per minute. Pitch
and level against the emulator's same segment.

| Run | Segment | Peak dBFS | RMS dBFS | Full scale | Gaps | Jumps | Clicks | Dropouts | Flatness | > 10 kHz dB | Pitch, cents | Level dB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **emulator (original)** | title | -21.1 | -38.7 | 0 | 0 | 0 | 0 | 0 | 0.0014 | -41.3 | | |
| | hub | -11.7 | -27.7 | 0 | 0 | 0 | 0 | 0 | 0.0008 | -42.1 | | |
| | fire1 | -6.7 | -22.6 | 0 | 0 | 0 | 127.8 | 0 | 0.0026 | -41.1 | | |
| **Godot Remastered**, 120 Hz | title | -21.2 | -38.0 | 0 | 0 | 0 | 0 | 0 | 0.0007 | -48.5 | +0.7 | +0.7 |
| | hub | -7.7 | -25.1 | 0 | 0 | 0 | 0 | 0 | 0.0004 | -49.0 | +1.0 | +2.5 |
| | fire1 | -6.7 | -21.5 | 0 | 0 | 0 | 15.4 | 0 | 0.0010 | -49.2 | +1.2 | +1.1 |
| | **boss music** | **-2.4** | **-16.9** | 0 | 0 | 0 | 4.1 | 0 | 0.0018 | -41.0 | | |
| | whole run | **+1.1** | -21.6 | **16** | 0 | | | 0 | 0.0012 | -45.5 | | |
| **Godot Classic**, 120 Hz | title | -21.2 | -38.0 | 0 | 0 | 0 | 0 | 0 | 0.0007 | -48.5 | +0.7 | +0.7 |
| | hub | -8.1 | -24.8 | 0 | 0 | 0 | 0 | 0 | 0.0004 | -48.6 | +1.2 | +2.9 |
| | fire1 | -6.4 | -19.6 | 0 | 0 | 0 | 18.9 | 0 | 0.0011 | -48.8 | +1.0 | +3.0 |
| **native**, 120 Hz display | title | -21.2 | -38.0 | 0 | 0 | 0 | 0 | 0 | 0.0007 | -48.5 | +0.7 | +0.7 |
| | hub | -9.4 | -26.6 | 0 | 0 | 0 | 0 | 0 | 0.0004 | -49.2 | +0.9 | +1.1 |
| | fire1 | -6.6 | -22.6 | 0 | 0 | 0 | 9.7 | 0 | 0.0011 | -48.6 | +0.7 | +0.1 |
| | **boss music** | **-1.9** | **-16.9** | 0 | 0 | 0 | 0 | 0 | 0.0002 | -53.4 | | |
| | whole run | **0.0** | -23.1 | **106** | 0 | | | 0 | 0.0006 | -48.5 | | |
| **Godot Remastered, 60 Hz** | title / hub / fire1 | -21.2 / -7.9 / -6.8 | -37.6 / -24.2 / -21.0 | 0 | 0 | 0 | 0 / 0 / 18.0 | 0 | 0.0005 to 0.0010 | -48.1 to -49.2 | +0.7 / +1.4 / +1.0 | |
| | **boss music** over `fire1` | **-1.1** | **-14.1** | 0 | 0 | 17.3 | 30.7 | 0 | 0.0045 | -41.6 | | |
| **Godot Remastered, 120 Hz, 24 spinners** (load 40) | title / hub / fire1 | -21.2 / -7.9 / -6.8 | -37.6 / -24.7 / -20.8 | 0 | 0 | 0 | 0 / 0 / 16.3 | 0 | 0.0004 to 0.0011 | -48.1 to -48.9 | +0.7 / +1.0 / +1.0 | |
| **Godot Classic, 60 Hz, 48 spinners** (load 53) | title / hub / fire1 | -21.2 / -11.7 / -7.1 | -37.6 / -27.4 / -22.9 | 0 | 0 | 0 | 0 / 0 / 6.9 | 0 | 0.0004 to 0.0011 | -48.1 to -49.0 | +0.7 / +0.9 / +0.7 | |
| **native, 36 spinners** (load 41) | whole short route, 141 s | -1.5 | -21.2 | 0 | 0 | 0 | 17.9 | 0 | 0.0010 | -47.1 | | |

Waveform against the original (`sndcmp`, the emulator's clock corrected by its 421 ppm): Godot
Remastered's title music **0.9980** (left 0.9966, right 0.9996), envelope 0.9999, level within
0.07 dB. Native against Godot: correlation 1.0000, residual **99 dB down** (the same samples).

**Underruns.** Godot: the mixer asked the game for 248.60 s of sound in 248.60 s of wall time
(93,225 requests) idle, 186.91 s in 186.9 s under 24 spinners, 141.23 s in 141.23 s under 48 at
60 Hz; in no second did it fall 50 ms behind the wall clock. That holds while the game itself ran
at 43 to 45 frames a second under load (`mixer asked ... in N requests`, `vertical blanks`): the
game's sound is pulled by Godot's audio thread (`RtaAudioStream`, `sound-clock=real`), not pushed
per frame, so a late frame cannot starve it. Native: the device's requests never more than 30 ms
apart in any run **without** the WAV tap or with the new one (longest 10.7 to 15.1 ms, render 0.09
to 0.23 ms at most, under 36 spinners as well); the one 160 ms gap was the old tap's (above).

**The pitch and the treble.** Pitch +0.5 to +1.4 cents everywhere: the emulator plays a stream
voice 421 ppm (0.73 cents) slow, so ours is within half a cent of the console. Ours has 7 to 8 dB
**less** above 10 kHz than the emulator (-48.5 against -41.3 dB): the emulator interpolates
linearly and leaves images above 12 kHz, ours uses the chip's four-tap Gaussian
(`native-sound.md` 4.3). Duller, not noisier.

**The loud stretches are the game's.** The same levels on the emulator (21 s each, a standing
invulnerable player with monsters on him):

| Level | Original: full scale / jumps / flatness / > 10 kHz | Native: full scale / jumps / flatness / > 10 kHz |
|---|---|---|
| arachna1 | 9,667 / 23,756 / 0.047 / -27.0 dB | 0 / 6,634 / 0.021 / -34.9 dB |
| nitbon2 | 2,327 / 2,408 / 0.013 / -33.3 | 0 / 1,165 / 0.004 / -42.8 |
| nitbonus | 1,575 / 6,024 / 0.019 / -32.1 | 0 / 1,507 / 0.009 / -39.4 |
| storm3 | 9,022 / 3,070 / 0.011 / -35.4 | 0 / 1,592 / 0.005 / -43.7 |
| inmine1 | 4,485 / 418 / 0.003 / -39.1 | 0 / 46 / 0.001 / -46.3 |

The `fearboss` burst 60 s after arrival: original peak -0.9 dBFS, flatness 0.014, -26.9 dB above
10 kHz; ours -1.3, 0.0125, -28.8. A sweep of 108 levels in the native program (machine clock,
25 s each): 0 gaps, 0 dropouts in all; spectral flatness median 0.001, at most 0.024 (`arachna1`).

**The boss tracks themselves** (the 82 in `app-data/music/boss`, decoded): RMS median -13.2 dBFS
(-24.1 to -10.0), 58 with peaks at full scale, decoded in floating point up to +0.76 dBFS; 55 clip
when decoded to 16 bits (105,424 samples; one track 40,033). The game's music alone (stream 2,
`sound-solo=stream2`, 12 levels): RMS -24.1 to -33.3 dBFS, median about -28, peaks -8.7 to -16.

## The fix

**Boss music loudness** (`tools/recomp/app/bossmusic.cpp`, `tools/godot/project/hud/music/music.gd`):

- Each track is measured when it is loaded (on the loader's thread) and given the gain that brings
  its RMS to **-24 dBFS at volume 1** (so the default 0.8 puts it at -26, where the game's music
  is), never so much that its loudest sample passes **0.70 (-3.1 dBFS)**. The log line says it:
  `playing ... (RMS -12.5 dBFS, peak +0.7 dBFS as decoded, played -11.4 dB)`. Godot measures the
  track by mixing it once through `AudioStreamPlayback.mix_audio` (about 0.5 s on the loader
  thread for a 2-minute track) and adds the gain to the player's `volume_db`.
- Native: the files are decoded in **floating point** (`stb_vorbis_get_samples_float_interleaved`,
  `drmp3_..._f32`, `drwav_..._f32`), so the overs are brought down by the gain instead of being
  clipped flat by a 16-bit decode; the gain is applied before the track is stored as 16 bits.
- Native: while a track is mixed, the sum of the game's sound and the track is passed through a
  **soft knee** above 80 % of full scale (`tanh` towards full scale) instead of being cut at full
  scale. The game's sound alone never passes through it (the mixer returns at once with no track),
  so Classic and every moment without boss music are unchanged sample for sample.

**The WAV tap** (`tools/recomp/sound/audio_out.cpp`): `WavSink::write` only appends to a buffer;
a thread writes it every 50 ms and keeps the header current. Nothing waits for the disk on the
device's thread any more.

Gameplay is untouched: nothing here is read by the game (the boss music is added after the chip,
`rta_sound_set_host_mix`; the director's state is local), the machine-clock and lockstep paths are
the same code, and the fix changes no byte the game sees.

### After the fix

| Run | Segment | Peak dBFS | RMS dBFS | Full scale | Gaps | Jumps/min | Clicks/min | Dropouts | Flatness |
|---|---|---|---|---|---|---|---|---|---|
| Godot Remastered, 120 Hz (load 69 from other work) | title / hub / fire1 | -14.2 / -8.0 / -6.6 | -33.8 / -24.9 / -21.1 | 0 | 0 | 0 | 0 / 0 / 25.0 | 0 | 0.0004 to 0.0010 |
| | **boss music** (played -11.4 dB) | **-13.0** (was -2.4) | **-26.0** (was -16.9) | 0 | 0 | 0 | 9.2 | 0 | 0.0026 |
| | whole run, 433 s | -1.3 (`fearboss` burst; was +1.1) | -26.5 | **0** (was 16) | 0 | | | 0 | 0.0015 |
| native, 120 Hz display | title / hub / fire1 | -21.2 / -9.7 / -7.1 | -38.0 / -26.6 / -22.6 | 0 | 0 | 0 | 0 / 0 / 16.9 | 0 | 0.0004 to 0.0011 |
| | **boss music** (played -11.4 dB) | **-12.8** (was -1.9) | **-25.7** (was -16.9) | 0 | 0 | 0 | 74.4 (the track's own) | 0 | 0.0034 |
| | whole run | -1.1 (was 0.0) | -27.2 | **0** (was 106) | 0 | | | 0 | 0.0013 |
| Godot Remastered, 60 Hz, 36 spinners (load 117) | title / hub / fire1 | -21.2 / -7.9 / -6.7 | -37.5 / -24.9 / -20.9 | 0 | 0 | 0 | 0 / 0 / 19.0 | 0 | 0.0004 to 0.0011 |
| | **boss music** over `fire1` (played -10.6 dB) | **-9.4** (was -1.1) | **-23.8** (was -14.1) | 0 | 0 | **0** (was 17.3) | 0 | 0 | 0.0036 |

The native boss music against the track decoded in floating point at the same gain: waveform
correlation 1.0000, residual 73 dB down (it is the track, only quieter). The `fearboss` segment and
every Classic segment are the same numbers as before (the same samples: the fix does not touch them).

## Another project's sound (`~/Projects/open-champions`, not ours)

Read only (its processes and files were not touched). Its Godot client would sound broken in the
way described, for three reasons in its code:

1. **Pushed per frame into a 100 ms buffer.** `godot/audio/playable_audio.gd` gives an
   `AudioStreamGenerator` `buffer_length = 0.1` and fills it from the main thread
   (`pump_frames` in `_process` and per game tick). Any main-thread stall over 100 ms - a level
   reset copies a 108 MB bank there (`real_data/real_audio.gd`) - runs the generator dry, and Godot
   plays silence for the missing frames: gaps and crackle at the frame rate.
2. **Mixed per game tick, not per time.** Its mixer makes exactly 800 frames per ready tick. A test
   loop that runs ticks faster than real time overfills the bounded 12,800-frame FIFO, which drops
   old sound (its own `docs/PLAYABLE_AUDIO.md`: "Accelerated/headless soaks can drop old
   presentation PCM"): what is heard is chopped and time-compressed. Slower than 60 ticks a second,
   it runs dry instead.
3. **The fixture bank is not music.** Without the user's disc it plays `audio/synthetic_bank.gd`:
   ADPCM blocks of constant nibbles (0x22 / 0xee, 0x33 / 0xdd) - square waves at about 54 and
   71 Hz, a harsh buzz.

Ours does not have (1) or (2): the game's sound side runs on the audio device's own thread and
clock (`native-sound.md` section 8), which is why a starved main thread, 60 or 120 Hz and a loaded
machine change nothing above.

## How to repeat

```
clang++ -std=c++17 -O2 tools/recomp/sound/audiocheck.cpp -o local/audio-quality/bin/audiocheck
clang++ -std=c++17 -O2 tools/recomp/sound/sndcmp.cpp -o local/audio-quality/bin/sndcmp
# Godot (a test run: silent; the master bus into a WAV; marks in the script)
Godot --path PROJECT -- --disc IMAGE --no-portal --edition remastered --mode scene --mute --test "audio" \
    --script ROUTE.rig --audio-tap OUT/master.wav [--display-rate 60|120|auto]
# native (gain 0 in a test run; the device still asks in real time)
rta_app --disc IMAGE --data DIR --test "audio" --script ROUTE.rig --boss-music on -- --opt sound-wav=OUT/native.wav
# the original
python3 -I -B tools/recomp/sound/emuref.py --disc IMAGE --data local/audio-quality/emuN --script ROUTE-emu.rig
audiocheck OUT/master.wav --start S --len L [--ref EMU.wav --ref-start S --ref-len L] [--json]
```

The route generator, the runners (with the spinners for the load runs) and the per-segment
analysis used here are `local/audio-quality/route.py`, `run_godot.py`, `run_native.py`,
`analyze.py`, `levels.py`; the recordings are game audio and stay under `local/`.
