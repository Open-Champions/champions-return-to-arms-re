#!/usr/bin/env python3
"""ref_music_volume.py - reference contract for the player's music volume g_musicVolume
0x4f8944 of Champions: Return to Arms (SLUS_209.73, US v2.00): where it is stored, its
image value, its default, every writer, and when each writer runs relative to the first
level or boss music request.

A research tool, not game code.  Written from the instruction sequences at the addresses
given; tools/difftest_music_volume.py runs the originals in tools/ee_emu.py and compares.
docs/spec/music-volume.md is the prose version.  Standard library plus tools/ref_core.py
(float arithmetic on raw 32-bit patterns, the interpreter's 'ps2' model).

Labels
  Observed  read at the address given.
  Executed  the original ran in tools/ee_emu.py on state the difftest built and this
            model agreed (difftest property named in brackets).
  Inferred  follows from observations; not seen directly.
  Unknown   not established.

Storage (Observed)
  0x4f8944 is inside .data (0x3e9c00..0x51e108), not .bss.  Its word in the ELF image is
  0x3f800000 (1.0) [static].  The options image g_savedConfig 0x4f8f38 is in .data too; its
  music word +0x08 (0x4f8f40) is 0 in the ELF image [static].  No gp-relative access can
  reach 0x4f8944 (gp 0x56c170 is 0x7382c away); the only code forms are lui 0x50 with
  offset -0x76bc.  Two data words point at it: 0x44f230 and 0x4f6ea0, the value pointers
  of the "menu_music" entries of the pause options list 0x44f218 and the front-end
  options list 0x4f6e88.

Writers of 0x4f8944 (Observed: every lui/offset store and both pointer words)
  W1 config_setDefaults 0x1e6238, store 0x1e627c, only when which == -1.
  W2 game_addCoreTasks 0x1e6cc0, store 0x1e6e2c: copies image +0x08.
  W3 memcard_optionsScreen 0x222b40 state 2, store 0x222ccc: copies the load buffer
     0x4f9240 +0x08 into 0x4f8944 and into image +0x08.
  W4 menuList_handleInput 0x1a01d0 type-4 slider, stores 0x1a0550/0x1a0554 and
     0x1a05a8/0x1a05ac through the entry's value pointer.
  config_restore 0x1e6528 (store 0x1e65d8) copies the backup 0x86af70 back; nothing calls
  it and no data word holds its address (Observed), so it is not a live writer.
Writers of image +0x08 (0x4f8f40)
  config_setDefaults (which == -1), memcard_optionsScreen state 2, config_commitOptions
  0x1e6650 (store 0x1e6a24, live value into the image when anything differs), and the
  boot-time options load: memcard_browser 0x219b90 step 29 (0x21b9d8) copies the 0x2f8
  bytes read into 0x4f9240 over the whole image when its mode argument is non-zero.

Boot order (Observed by address; the waits are Inferred from the loop structure)
  main 0x323dcc: save_init 0x216fcc (call 0x323e88) calls config_setDefaults(-1) at
  0x21700c unconditionally -> mainloop_runBootCardCheck 0x32396c (call 0x323fec) requests
  card state 0 and runs a modal loop until g_sessionExitCode 0x41b508 is non-zero;
  memcard_configScreen0 0x219a88 calls memcard_browser(1, ...) and sets that code when
  the browser finishes -> main loop -> mainloop_runSession 0x322998 -> game_addCoreTasks
  (call 0x322a20, straight-line from 0x322a08) -> session frame loop, where the front end
  and the levels run without leaving the session (docs/mainloop.md section 8).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as R            # noqa: E402

M32 = 0xFFFFFFFF

# ---- addresses (Observed) -------------------------------------------------------------
G_MUSIC_VOLUME = 0x4F8944          # float, the player's music volume
G_SFX_VOLUME = 0x4F8940            # float, effects volume (image +0x0c)
G_DUCK = 0x4F894C                  # float, music duck scalar (music_updateDucking 0x212500)
G_SAVED_CONFIG = 0x4F8F38          # options image, 0x2f8 bytes, the options file
G_CONFIG_LOAD = 0x4F9240           # card read buffer for the options file (0x2f8 bytes)
G_CONFIG_BACKUP = 0x86AF70         # config_backup 0x1e6428 / config_restore 0x1e6528
G_SCHEME = 0x41B69C                # s8 button scheme, 1 in this executable
G_OPTIONS_STATE = 0x88D3A8         # memcard_optionsScreen step
G_BROWSER_STEP = 0x88D3E0          # memcard_browser step
G_SESSION_EXIT = 0x41B508          # g_sessionExitCode
G_MENU_TIMER = 0x4D8A10            # per-slot float repeat timer of menuList_handleInput
PAUSE_OPTIONS = 0x44F218           # g_pauseOptionsTable; music entry is index 1
FRONTEND_OPTIONS = 0x4F6E88        # front-end options list; music entry is index 1
CONFIG_SIZE = 0x2F8
DATA_SECTION = (0x3E9C00, 0x51E108)

CONFIG_SET_DEFAULTS = 0x1E6238
CONFIG_BACKUP = 0x1E6428
CONFIG_RESTORE = 0x1E6528
CONFIG_COMMIT = 0x1E6650
GAME_ADD_CORE_TASKS = 0x1E6CC0
MUSIC_APPLY_VOLUME = 0x215E78
MUSIC_PLAY_LEVEL = 0x215F48
MUSIC_PLAY_GLOBAL = 0x2110E0
MUSIC_PLAY_LEVEL_INDEX = 0x215EC8   # music_playLevelIndex, same gate (not executed here)
AUDIO_STREAM_STATUS = 0x211B20
AUDIO_SET_CHANNEL_VOLUME = 0x216690
STREAM_QUEUE = 0x215FC8             # what music_playLevel queues through
MENU_HANDLE_INPUT = 0x1A01D0
MEMCARD_OPTIONS_SCREEN = 0x222B40
MEMCARD_REQUEST_OPTIONS = 0x222B10
MEMCARD_BROWSER = 0x219B90
MEMCARD_SET_STATE = 0x21F238
STRING_LOOKUP = 0x173C84
MESSAGE_BOX = 0x1DADC0
CONFIG_SAVE_REQUEST = 0x217BDC      # memcard_requestConfigSave
SAVE_INIT = 0x216FCC
MAIN = 0x323DCC
RUN_SESSION = 0x322998
BOOT_CARD_CHECK = 0x32396C
BROWSER_COPY_STEP = 29              # jump table 0x53f440 entry 29 = 0x21b9d8

# ---- constants (Observed patterns) ----------------------------------------------------
STATIC_MUSIC = 0x3F800000           # .data word at 0x4f8944 before any code runs
STATIC_IMAGE_MUSIC = 0x00000000     # .data word at image +0x08 (0x4f8f40)
DEFAULT_MUSIC = 0x3F000000          # 0.5, config_setDefaults(-1)
MUSIC_GATE = 0x3D4CCCCC             # queued unless volume compares below this
CHANNEL_SCALE = 0x3F480000          # 0.78125
SLIDER_STEP = 0x3C088888            # 1/120 per handled call while held
TIMER_STEP = 0x3E4FDEF8             # repeat timer increment, capped at 1.0
VOICE_DEFAULT = 0x3E199999
LEFT_MASK = 0x408000                # held bits that lower a type-4 slider
RIGHT_MASK = 0x802000               # held bits that raise it
STATUS_PLAYING = 0x20               # audio_streamStatus bit that lets the volume through

# Options image offset -> live global.  The 17 scalar pairs used identically by
# config_setDefaults, config_backup, config_commitOptions, game_addCoreTasks and
# memcard_optionsScreen (Observed in all five; the +0xc4..+0xd4 pairing is read from the
# loads and stores of 0x1e6cc0 and 0x222b40).
SCALARS = (
    (0x04, 0x44FD80, 0x3F000000),   # brightness
    (0x08, 0x4F8944, 0x3F000000),   # music
    (0x0C, 0x4F8940, 0x3F000000),   # effects
    (0x10, 0x4F8948, 1),            # stereo
    (0x14, 0x41BFB0, 1),            # vibration
    (0x18, 0x4FDCC8, 1),
    (0x1C, 0x44FCF4, 1),            # subtitles
    (0x20, 0x44FCF8, 1),            # damage numbers
    (0x24, 0x44FDC0, 0),            # blood / decal detail
    (0x28, 0x4F8458, 1),
    (0x2C, 0x4F845C, 1),
    (0x30, 0x4F8460, 0),
    (0xC4, 0x50391C, 1),
    (0xC8, 0x505AF0, VOICE_DEFAULT),
    (0xCC, 0x505AF4, 0x3F000000),
    (0xD0, 0x505B00, 1),
    (0xD4, 0x505AFC, 0),
)
ROWS_AT = 0x34                      # four button rows of nine words, stride 0x24
ROW_STRIDE = 0x24
# Row word k -> per-slot array (index slot*4), as game_addCoreTasks and
# config_commitOptions copy them (Observed 0x1e6d58..0x1e6dfc).
ROW_ARRAYS = (0x41B980, 0x41B990, 0x41B9A0, 0x41B9C0, 0x41B9D0,
              0x41BA10, 0x41BA20, 0x41B9E0, 0x41BA30)
ROW_SCHEME1 = (0x40, 0x20, 0x10, 0x80, 0x08, 0x02, 1, 0x400, 0x04)
ROW_SCHEME0 = (0x20, 0x10, 0x40, 0x80, 0x08, 0x02, 1, 0x400, 0x04)


# =======================================================================================
# Small helpers
# =======================================================================================

def music_gate_passes(volume):
    """music_playLevel 0x215f48 / music_playGlobal 0x2110e0 (Executed) and
    music_playLevelIndex 0x215ec8 (Observed, same three instructions): c.olt.s volume,
    0x3d4ccccc branches past the queue.  So a volume equal to the gate pattern is queued;
    anything comparing below it (including 0 and every negative pattern) queues nothing.
    Executed [gate]."""
    return not R.lt(volume, MUSIC_GATE)


def channel_volume(duck, volume):
    """The value handed to audio_setChannelVolume(value, 2): (duck * volume) * 0.78125, two
    truncated products in that order (0x215eac/0x215eb4).  Executed [apply]."""
    return R.mul(R.mul(duck, volume), CHANNEL_SCALE)


def music_apply_volume(volume, duck, status):
    """music_applyVolume 0x215e78.  Calls audio_streamStatus(2); when the result has bit
    0x20, calls audio_setChannelVolume(channel_volume(duck, volume), 2).  It never stores
    anything.  Returns the call list [(target, a0, f12 or None)].  Executed [apply]."""
    calls = [(AUDIO_STREAM_STATUS, 2, None)]
    if status & STATUS_PLAYING:
        calls.append((AUDIO_SET_CHANNEL_VOLUME, 2, channel_volume(duck, volume)))
    return calls


def music_play_level(volume, duck, name, flags):
    """music_playLevel 0x215f48(name, flags).  Gate as music_gate_passes; when it passes,
    audio_setChannelVolume(channel_volume(duck, volume), 2) and then the stream queue
    0x215fc8(2, name, flags | 0x22).  Below the gate there are no calls.  Executed [gate]."""
    if not music_gate_passes(volume):
        return []
    return [(AUDIO_SET_CHANNEL_VOLUME, 2, channel_volume(duck, volume)),
            (STREAM_QUEUE, 2, (name, (flags | 0x22) & M32))]


# =======================================================================================
# Writers
# =======================================================================================

def config_set_defaults(which, scheme, duck=0, status=0):
    """config_setDefaults 0x1e6238(which); scheme is the byte at 0x41b69c, duck the word at
    0x4f894c and status what audio_streamStatus(2) answers.  Returns (writes, calls):
    writes is a dict address -> word of every word stored, calls the callee list.

    which == -1: every scalar global and its image word get the default (music 0.5 at
    0x4f8944 and image +0x08; image +0x00 cleared); music_applyVolume runs after 0x4f8944
    and image +0x08 hold 0.5, so it sees 0.5.  Then the button rows of all four slots.
    which >= 0: only that slot's row; 0x4f8944 untouched, no call.
    Rows: scheme 1 ROW_SCHEME1, scheme 0 ROW_SCHEME0, any other scheme leaves the row.
    Executed [defaults]."""
    writes, calls = {}, []
    if which == -1:
        for offset, glob, default in SCALARS:
            writes[glob] = default
            writes[G_SAVED_CONFIG + offset] = default
        writes[G_SAVED_CONFIG] = 0
        calls = music_apply_volume(DEFAULT_MUSIC, duck, status)
    for slot in range(4):
        if which != -1 and slot != which:
            continue
        row = ROW_SCHEME1 if scheme == 1 else ROW_SCHEME0 if scheme == 0 else None
        if row is None:
            continue
        for k, value in enumerate(row):
            writes[G_SAVED_CONFIG + ROWS_AT + slot * ROW_STRIDE + 4 * k] = value
    return writes, calls


def game_add_core_tasks(image, duck, status):
    """game_addCoreTasks 0x1e6cc0, the part that concerns the options (it also registers
    the camera and drawWorld tasks first and calls lump_load("globsnd.lmp"), help_addTask,
    game_resetState, 0x171060, 0x18b930 and save_setAct(-1) after, and clears 0x4f7144).

    image: dict image offset -> word.  Copies the image scalars into their globals
    verbatim - no clamp, no validation: whatever float pattern is at image +0x08 becomes
    g_musicVolume - and the four button rows into the per-slot arrays.  0x4f8940 and
    0x4f8944 are stored before music_applyVolume, the rest after.
    Returns (writes, applyVolume calls).  Executed [coretasks]."""
    writes = {}
    for slot in range(4):
        for k, array in enumerate(ROW_ARRAYS):
            writes[array + 4 * slot] = image.get(ROWS_AT + slot * ROW_STRIDE + 4 * k, 0)
    for offset, glob, _default in SCALARS:
        writes[glob] = image.get(offset, 0)
    writes[0x4F7144] = 0
    return writes, music_apply_volume(image.get(0x08, 0), duck, status)


def options_screen(state, buffer, choice, browser_result, duck, status):
    """memcard_optionsScreen 0x222b40, one call, card state 10 (requested by
    memcard_requestOptions 0x222b10 from the pause menu 0x18d83c and frontend_run
    0x1e11c0 - a player action, never at boot).

    state 0: string "options_warn", message box; choice 1 -> memcard_setState(-1, 0);
             choice 2 -> state 1; anything else nothing.
    state 1: memcard_browser(0, "options_config", 0); -1 -> setState(-1, 0); 1 -> state 2.
    state 2: the 17 scalars of the load buffer 0x4f9240 go to their globals AND to the
             image (music first, with effects, then music_applyVolume, then the rest);
             the button rows and image +0x00 are not copied.  state 3, setState(-1, 0).
    state 3: setState(-1, 0).  Negative or above 3: nothing.
    Returns (writes, calls) with calls as (target, args).  Executed [optionsload]."""
    writes, calls = {}, []
    if state == 0:
        calls.append((STRING_LOOKUP, ('options_warn',)))
        calls.append((MESSAGE_BOX, (0x3C, -1, 0, 0)))
        if choice == 1:
            calls.append((MEMCARD_SET_STATE, (-1, 0)))
        elif choice == 2:
            writes[G_OPTIONS_STATE] = 1
    elif state == 1:
        calls.append((STRING_LOOKUP, ('options_config',)))
        calls.append((MEMCARD_BROWSER, (0, 0)))
        if browser_result == -1:
            calls.append((MEMCARD_SET_STATE, (-1, 0)))
        elif browser_result == 1:
            writes[G_OPTIONS_STATE] = 2
    elif state == 2:
        for offset, glob, _default in SCALARS:
            writes[glob] = buffer.get(offset, 0)
            writes[G_SAVED_CONFIG + offset] = buffer.get(offset, 0)
        for target, a0, f12 in music_apply_volume(buffer.get(0x08, 0), duck, status):
            calls.append((target, (a0,) if f12 is None else (a0, f12)))
        writes[G_OPTIONS_STATE] = 3
        calls.append((MEMCARD_SET_STATE, (-1, 0)))
    elif state == 3:
        calls.append((MEMCARD_SET_STATE, (-1, 0)))
    return writes, calls


def browser_config_copy(mode, image, buffer, or_bits):
    """memcard_browser 0x219b90 step 29 (0x21b9d8) after a successful read of the options
    file into 0x4f9240 (step 28, 0x21b96c, card op 3, 0x2f8 bytes): when the mode argument
    (kept in s5) is non-zero, the 0x2f8 bytes are copied over g_savedConfig; then, when
    the word at 0x88d3cc is not -1, image +0x00 |= that word | 4.  0x4f8944 is not touched
    here; it takes the loaded value at the next game_addCoreTasks.
    memcard_configScreen0 0x219a88 (boot, card state 0) passes mode 1;
    memcard_configScreen1 0x219b14 and memcard_optionsScreen pass mode 0.
    image/buffer: bytes.  Returns the new image bytes.  Executed [bootload]."""
    out = bytearray(buffer[:CONFIG_SIZE] if mode else image[:CONFIG_SIZE])
    if or_bits != -1:
        word = int.from_bytes(out[0:4], 'little') | (or_bits & M32) | 4
        out[0:4] = word.to_bytes(4, 'little')
    return bytes(out)


def slider_step(value, held):
    """menuList_handleInput 0x1a01d0 on a type-4 entry under the cursor, once its repeat
    timer is at 1.0: held & 0x408000 -> value - 1/120, stored, then 0 if that is below 0;
    then held & 0x802000 -> value + 1/120, stored, then 1.0 if 1.0 is below it.  Both can
    apply in one call.  Executed [slider]."""
    if held & LEFT_MASK:
        value = R.sub(value, SLIDER_STEP)
        if R.lt(value, 0):
            value = 0
    if held & RIGHT_MASK:
        value = R.add(value, SLIDER_STEP)
        if R.lt(R.ONE, value):
            value = R.ONE
    return value


def menu_slider_call(value, held, timer):
    """One menuList_handleInput call with no edge bits (pad +0x10 = 0), the cursor on a
    type-4 entry and nothing else changing: (new value, new timer, active).
    The timer gains 0x3e4fdef8 and is capped at 1.0; below 1.0 the call does nothing else.
    It is reset to 0 only when the cursor moves.  So the first four calls after the cursor
    lands are idle and from the fifth on every call (every frame) applies slider_step.
    Executed [slider]."""
    timer = R.add(timer, TIMER_STEP)
    if R.le(R.ONE, timer):
        timer = R.ONE
    if not R.le(R.ONE, timer):
        return value, timer, False
    return slider_step(value, held), timer, True


def slider_walk(start, held, limit=200):
    """Values after each active call holding one direction from start; stops at the clamp."""
    values, value = [], start
    for _ in range(limit):
        new = slider_step(value, held)
        values.append(new)
        if new == value:
            break
        value = new
    return values


def config_commit_music(live, image_music, query_only, no_card_save, force=0):
    """config_commitOptions 0x1e6650(force, queryOnly, noCardSave), reduced to a state where
    every other option already equals its image word: the count is 1 when 0x4f8944 differs
    from image +0x08 (c.eq.s), else 0.  Unless queryOnly, a non-zero count copies all the
    live scalars into the image (music at store 0x1e6a24) and rewrites the button arrays
    from the image rows; then, when the count or force is non-zero and noCardSave is 0,
    the config save request 0x217bdc is called.
    Returns (count, new image music, save requested).  Executed [commit]."""
    count = 0 if R.eq(live, image_music) else 1
    if query_only:
        return count, image_music, False
    new_image = live if count else image_music
    save = bool((count or force) and not no_card_save)
    return count, new_image, save


# =======================================================================================
# The question: what does g_musicVolume hold when the first music is requested?
# =======================================================================================

def boot_music_volume(options_file_music=None, slider_held=(), duck=R.ONE):
    """Value of 0x4f8944 at each step of a boot, as a list of (step, value pattern).

    options_file_music: None for no memory card / no options file (Inferred: the
    browser's copy at step 29 is only reached after a successful read), else the float
    pattern at +0x08 of the options file.  slider_held: held masks of front-end option
    slider frames (active calls) before the level starts.
    The final entry is what music_playLevel / music_playGlobal compare with the gate."""
    steps = [('elf image (.data)', STATIC_MUSIC)]
    image_music = STATIC_IMAGE_MUSIC
    # save_init -> config_setDefaults(-1)
    volume = DEFAULT_MUSIC
    image_music = DEFAULT_MUSIC
    steps.append(('save_init: config_setDefaults(-1)', volume))
    if options_file_music is not None:
        image_music = options_file_music & M32
    steps.append(('boot card check (image +0x08 = 0x%08x)' % image_music, volume))
    volume = image_music
    steps.append(('mainloop_runSession: game_addCoreTasks', volume))
    for held in slider_held:
        volume = slider_step(volume, held)
    if slider_held:
        steps.append(('front-end slider', volume))
    steps.append(('first level/boss music request (gate %s)' % (
        'passes' if music_gate_passes(volume) else 'fails'), volume))
    return steps
