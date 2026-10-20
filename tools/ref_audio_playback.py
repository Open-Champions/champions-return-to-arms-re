#!/usr/bin/env python3
"""Playback decisions for the three EE streams.

The byte-level contracts stay in ref_audio.py. This module is the part the
original functions decide: which entry replaces another, which queue flags the
stream service ignores, how a loop restart is measured, how music volume eases,
and which frame counters the 4-, 8- and 16-frame work uses.

Arithmetic matches tools/ee_emu.py's R5900 single-precision helpers, so a
difftest can compare raw patterns. Nothing here reads a disc or an executable.
"""

from ee_emu import fp_add, fp_cmp, fp_from_int, fp_mul, fp_sub

MUSIC_VOLUME_GATE = 0x3D4CCCCC
MUSIC_VOLUME_SCALE = 0x3F480000
DUCK_VOICE_LEVEL = 0x3E4CCCD0
DUCK_CREEP = 0x3C888888
DUCK_STEP = 0x3C23D70A
FLOAT_ONE = 0x3F800000

MOVIE_FRAME_SCALE = 0x3D08AB85
MOVIE_BYTE_SCALE = 0x3798EADB
MOVIE_TIME_BIAS = 0x3D8F5C28
MOVIE_SYNC_THRESHOLD = 0x3CA3D70A

MOUTH_VAT = "mouth.vat"
MUSIC_FLAG_OR = 0x22
GLOBAL_BOSS_FLAGS = 0x103
LEVEL_POLL_FLAGS = 0x102

FLAG_LOOP = 0x1
FLAG_FADE = 0x2
FLAG_WAIT = 0x4
FLAG_HOLD = 0x8
FLAG_MUSIC = 0x20
FLAG_RECALL = 0x40
FLAG_AMBIENCE = 0x80
FLAG_CUTSCENE_KEEP = 0x100

# g_soundFrame and g_drawFrame as stored in the US v2.00 image.
SOUND_FRAME_IMAGE = 0
DRAW_FRAME_IMAGE = 0x400


def _u32(value):
    return value & 0xFFFFFFFF


def _mul(a, b, model, bias):
    return fp_mul(a, b, model, bias=bias)


def music_gate_open(volume_bits):
    """music_playGlobal / music_playLevel queue only when volume is not below the gate."""
    return fp_cmp(_u32(volume_bits), MUSIC_VOLUME_GATE) >= 0


def music_flags(caller_flags):
    """Both music entry points OR 0x22 into the caller's flags before queueing."""
    return _u32(caller_flags) | MUSIC_FLAG_OR


def loop_restart_bytes(value):
    """Bytes skipped from the VAT offset when a looping entry rewinds.

    Low 10 bits are dropped, so the span is a multiple of 0x800. Bit 31 of the
    directory value does not contribute. Equivalent to (value << 1) & 0xFFFFF800.
    """
    return _u32((_u32(value) & 0x7FFFFC00) << 1)


def after_completed_read(name, flags, position, remaining, offset, length, restart, nbytes):
    """Stream head after one completed disc read, before the next queue promote.

    position is stream+0x10 and remaining is stream+0x14, both before this read.
    offset, length and restart are stream+0x18, +0x1c and +0x3c. A rewind runs
    only when the entry has a name, the loop bit is set, and remaining hits
    exactly zero once nbytes have been subtracted. The rewind replaces both
    words: the file position becomes offset + span, and remaining becomes the
    stored length minus that span.
    """
    position = _u32(position + nbytes)
    remaining = _u32(remaining - nbytes)
    if name and remaining == 0 and (_u32(flags) & FLAG_LOOP):
        span = loop_restart_bytes(restart)
        position = _u32(offset + span)
        remaining = _u32(length - span)
    return position, remaining


def duck_update(current, target, voice_status, level_name, language, model="ps2", mul_bias=False):
    """One music_updateDucking easing step. Returns (current, target).

    `voice_status` is audio_streamStatus(1). Whether the result is sent to the
    music channel is duck_sends_volume; the pattern itself is ducked_volume.
    """
    del mul_bias  # the scalar step is add/sub only; volume is applied by ducked_volume
    saved = _u32(current)
    target = _u32(target)
    if voice_status & FLAG_MUSIC:
        target = DUCK_VOICE_LEVEL
    target = fp_add(target, DUCK_CREEP, model)
    if fp_cmp(FLOAT_ONE, target) < 0:
        target = FLOAT_ONE
    if fp_cmp(target, saved) < 0:
        stepped = fp_sub(saved, DUCK_STEP, model)
        current = target if fp_cmp(stepped, target) < 0 else stepped
    elif fp_cmp(saved, target) < 0:
        stepped = fp_add(saved, DUCK_STEP, model)
        current = target if fp_cmp(target, stepped) < 0 else stepped
    else:
        current = saved
    if level_name == "actintro" and language:
        current = 0
    return current, target


def ducked_volume(current, music_volume, model="ps2", mul_bias=False):
    """scalar * g_musicVolume * 0.78125, the channel-2 argument."""
    return _mul(_mul(_u32(current), _u32(music_volume), model, mul_bias), MUSIC_VOLUME_SCALE, model, mul_bias)


def duck_sends_volume(previous, current, stream2_status):
    """True when the scalar changed and stream 2 is a music entry (status bit 0x20)."""
    return fp_cmp(_u32(previous), _u32(current)) != 0 and bool(stream2_status & FLAG_MUSIC)


def set_duck_target(argument, model="ps2"):
    """music_setDuck stores 1 - argument and leaves the current scalar alone."""
    return fp_sub(FLOAT_ONE, _u32(argument), model)


def stream_status_bits(write_pos, read_pos, remaining, active_flags, queued_count, first_flags):
    """Value audio_streamStatus returns after its status RPC.

    A positive remaining count, or a driver write position different from the
    read position, reports the active entry's flags with bit 0 set. Otherwise
    the first queued entry is reported the same way, except a held entry
    (bit 8) reports idle. remaining is a signed compare: a negative word does
    not count as still playing.
    """
    playing = write_pos != read_pos or 0 < _u32(remaining) <= 0x7FFFFFFF
    if playing:
        return _u32(active_flags) | 1
    if queued_count > 0:
        if first_flags & FLAG_HOLD:
            return 0
        return _u32(first_flags) | 1
    return 0


def recall_stops_music(status):
    """Callers that test bit 0x40 then append a stream-2 stop marker."""
    return bool(status & FLAG_RECALL)


def cut_run_stream2(gate, status):
    """cut_runFrame's stream-2 decision once its global is in hand.

    None leaves stream 2 alone. 'stop' is audio_streamStop. Stream 1 is stopped
    before this decision, whether or not the global is set.
    """
    if gate and (status & FLAG_AMBIENCE) and not (status & FLAG_CUTSCENE_KEEP):
        return "stop"
    return None


def cut_end_stream2(gate, status):
    """cut_end's stream-2 decision. 'clear' drops the queue and keeps the active entry."""
    if not gate or (status & FLAG_CUTSCENE_KEEP):
        return None
    if status & FLAG_AMBIENCE:
        return "stop"
    return "clear"


def sound_cadence(frame):
    """What sound_update does with g_soundFrame, before it increments the counter.

    queues: stream_serviceQueues when the low 2 bits are 0.
    end_flags: the two SPU end-flag reads when the low 3 bits are 0.
    send_volumes: audio_sendVolumes after the increment, when the new value's
    low 4 bits are 0 (the value before the call ended in 0xF).
    """
    frame = _u32(frame)
    return {
        "queues": (frame & 3) == 0,
        "end_flags": (frame & 7) == 0,
        "send_volumes": ((frame + 1) & 0xF) == 0,
        "next": _u32(frame + 1),
    }


def draw_cadence(frame):
    """True on the displayed frames that poll amb_ and refresh group volumes."""
    return (_u32(frame) & 0xF) == 0


def movie_sync(enabled, frame, position, last, model="ps2", mul_bias=False):
    """movie_update's drift decision. Returns (hold, next_frame, last_position).

    hold means the picture is not advanced. The enable flag is not set by the
    intro: with it clear, the frame always advances and the stream is not read.
    With it set, the compared stream is stream 2. A changed position is stored
    as the last sample before the hold/advance choice.
    """
    frame = _u32(frame)
    position = _u32(position)
    last = _u32(last)
    if not enabled or position == last:
        return False, _u32(frame + 1), last
    video = fp_sub(_mul(fp_from_int(frame, model), MOVIE_FRAME_SCALE, model, mul_bias),
                   MOVIE_TIME_BIAS, model)
    audio = _mul(fp_from_int(_u32(position - 0x400), model), MOVIE_BYTE_SCALE, model, mul_bias)
    gap = fp_sub(audio, video, model) & 0x7FFFFFFF
    hold = fp_cmp(gap, MOVIE_SYNC_THRESHOLD) >= 0 and fp_cmp(video, audio) >= 0
    return hold, frame if hold else _u32(frame + 1), position


def queued_music(caller_flags, offset, length, rate, stereo, restart):
    """The stream-2 queue words music_playGlobal stores for one VAT span.

    The queued file name is always mouth.vat. The span comes from the directory
    row (offset, and the next row's offset minus this one). A zero length is not
    queued; the caller then sees no entry. Keys are byte offsets within the
    0x30-byte queue entry.
    """
    if _u32(length) == 0:
        return None
    return {
        0x10: _u32(offset),
        0x14: _u32(length),
        0x18: _u32(offset),
        0x1C: _u32(length),
        0x20: _u32(rate),
        0x24: _u32(stereo),
        0x28: _u32(restart),
        0x2C: music_flags(caller_flags),
    }


def boss_action(has_name, volume_bits, length):
    """What creature_startBossMusic does to stream 2.

    'noop' leaves the stream alone (the creature has no boss track).
    'silence' is the immediate stop with nothing queued after it: the music
    volume is below the gate, or the directory row has no bytes.
    'replace' is the stop followed by one mouth.vat queue entry. A second boss
    therefore removes the first entry rather than mixing with it.
    """
    if not has_name:
        return "noop"
    if not music_gate_open(volume_bits) or length == 0:
        return "silence"
    return "replace"
