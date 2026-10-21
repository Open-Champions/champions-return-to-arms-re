#!/usr/bin/env python3
"""difftest_music_volume.py - compare tools/ref_music_volume.py with the original writers
and readers of the music volume g_musicVolume 0x4f8944.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_music_volume.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-v]

    --seed N    seed of the random cases (default 20973); a seed repeats exactly
    --cases N   random cases per property (default 300)
    -v          print the first mismatches of a failing property

What is compared
  The original functions run in tools/ee_emu.py (an instruction interpreter, not a
  console) on state this script builds; the same state goes through the model.  For every
  case: the calls made to everything outside the function under test, in order, with the
  arguments that matter (a0, f12, strings), every word stored outside the stack (final
  value per address), and the result where there is one.  Floats are compared as 32-bit
  patterns under the interpreter's 'ps2' model.  Nothing here was run on a console, in
  PCSX2 or on the live rig.

Properties
  static       the ELF image word of 0x4f8944 and of image +0x08, and the section holding them
  defaults     config_setDefaults 0x1e6238 with music_applyVolume 0x215e78 running for real
  apply        music_applyVolume 0x215e78
  gate         music_playLevel 0x215f48 and music_playGlobal 0x2110e0 around 0x3d4ccccc
  coretasks    game_addCoreTasks 0x1e6cc0 (image -> live globals at session start)
  optionsload  memcard_optionsScreen 0x222b40, every state
  bootload     memcard_browser 0x219b90 step 29 (0x21b9d8), the boot options copy
  slider       menuList_handleInput 0x1a01d0 on the music entry of both option lists,
               single calls and whole walks from 0.5
  commit       config_commitOptions 0x1e6650, music part
  chain        static image -> config_setDefaults(-1) -> [options file copy] ->
               game_addCoreTasks -> music_playLevel: the value the first request sees
"""
import hashlib
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as R                            # noqa: E402
import ref_music_volume as M                    # noqa: E402
from ee_emu import EE, EmuError, MemoryFault    # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
OPTIONS = {'seed': 20973, 'cases': 300, 'verbose': False}
RESULTS = []

# Function ranges for the coverage count (heuristic bounds of tools/dis.py, end exclusive).
RANGES = {
    'config_setDefaults': (0x1E6238, 0x1E6428),
    'music_applyVolume': (0x215E78, 0x215EC8),
    'music_playLevel': (0x215F48, 0x215FC8),
    'music_playGlobal(gate part)': (0x2110E0, 0x211138),
    'game_addCoreTasks': (0x1E6CC0, 0x1E6F58),
    'memcard_optionsScreen': (0x222B40, 0x222E10),
    'memcard_browser step 29': (0x21B9D8, 0x21BB68),
    'menuList_handleInput': (0x1A01D0, 0x1A076C),
    'config_commitOptions': (0x1E6650, 0x1E6B68),
}
COVERED = {name: set() for name in RANGES}

OTHER_CORE_CALLS = (0x19E4A0, 0x19E4A0)                 # camera, drawWorld task adds
LATER_CORE_CALLS = (0x173558, 0x1DD240, 0x1E6F58, 0x171060, 0x18B930, 0x2180A8)


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith('-')]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        candidates.append(env)
    candidates += [os.path.join(ROOT, 'local', 'SLUS_209.73'),
                   os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73']
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def report(name, failures, count, text, examples=()):
    RESULTS.append((name, failures == 0))
    print('%s  %-12s %d cases, %d mismatches  %s' % (
        'PASS' if failures == 0 else 'FAIL', name, count, failures, text))
    if failures and OPTIONS['verbose']:
        for line in examples[:6]:
            print('        ' + line)
    sys.stdout.flush()


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def cstr(ee, addr, limit=64):
    raw = ee.mem.read(addr, limit)
    end = raw.find(b'\x00')
    return (raw if end < 0 else raw[:end]).decode('latin-1')


def boot(elf, follow):
    ee = EE(elf)
    ee.mem.auto_map = True
    ee.follow = set(follow)
    ee.default_ret = 0
    ee.trace = []
    return ee


def run(ee, addr, *args):
    ee.calls, ee.writes, ee.notes = [], [], []
    ee.trace = []
    value = ee.call(addr, *args, max_steps=2000000) & M32
    pcs = set(ee.trace)
    for name, (lo, hi) in RANGES.items():
        COVERED[name].update(pc for pc in pcs if lo <= pc < hi)
    ee.trace = []
    return value


def stored(ee):
    """Final value of every word stored outside the stack (4-byte stores only here)."""
    out = {}
    for _pc, addr, size, value in ee.writes:
        if size == 4:
            out[addr] = value
        elif size == 8:
            out[addr] = value & M32
            out[addr + 4] = value >> 32
        else:
            base = addr & ~3
            word = out.get(base, ee.mem.u32(base))
            shift = (addr & 3) * 8
            mask = ((1 << (size * 8)) - 1) << shift
            out[base] = (word & ~mask) | ((value << shift) & mask)
    return out


def outside_calls(ee, keep=None):
    """Stubbed calls as (target, a0, f12) tuples; f12 only for audio_setChannelVolume."""
    out = []
    for rec in ee.calls:
        if not rec.stubbed:
            continue
        if keep is not None and rec.target not in keep:
            continue
        a0 = rec.args[0] & M32
        f12 = rec.fargs[0] & M32 if rec.target == M.AUDIO_SET_CHANNEL_VOLUME else None
        out.append((rec.target, a0, f12))
    return out


def gen_volume(rng):
    pick = rng.random()
    if pick < 0.15:
        return rng.choice((0, 0x80000000, M.MUSIC_GATE, M.MUSIC_GATE - 1, M.MUSIC_GATE + 1,
                           R.ONE, M.DEFAULT_MUSIC, 0x3F7FFFFF, 0x3F800001))
    if pick < 0.7:
        return f32(rng.uniform(0.0, 1.0))
    if pick < 0.85:
        return f32(rng.uniform(-2.0, 4.0))
    return rng.getrandbits(32)


def gen_status(rng):
    return rng.choice((0, 0x20, 0x21, 0x1, 0xFFFFFFFF, rng.getrandbits(32)))


def stub_audio(ee, box):
    ee.stub(M.AUDIO_STREAM_STATUS, function=lambda emu: box['status'], name='audio_streamStatus')
    ee.stub(M.AUDIO_SET_CHANNEL_VOLUME, ret=0, name='audio_setChannelVolume')


def model_calls(calls):
    return [(t, a0 & M32, f12) for t, a0, f12 in calls]


# =======================================================================================

def test_static(elf):
    ee = EE(elf)
    with open(elf, 'rb') as source:
        data = source.read()
    shoff, = struct.unpack_from('<I', data, 32)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 46)
    headers = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)]
    names_at = headers[shstrndx][4]

    def section_of(addr):
        for h in headers:
            if h[3] <= addr < h[3] + h[5] and h[3]:
                name = data[names_at + h[0]:data.index(b'\x00', names_at + h[0])].decode()
                return name, h[1]
        return None, None

    failures, notes = 0, []
    music = ee.mem.u32(M.G_MUSIC_VOLUME)
    image = ee.mem.u32(M.G_SAVED_CONFIG + 8)
    sec_music, type_music = section_of(M.G_MUSIC_VOLUME)
    sec_image, _ = section_of(M.G_SAVED_CONFIG)
    checks = [
        (music == M.STATIC_MUSIC, '0x4f8944 image word 0x%08x' % music),
        (image == M.STATIC_IMAGE_MUSIC, 'image +0x08 word 0x%08x' % image),
        (sec_music == '.data' and type_music == 1, '0x4f8944 in %s (type %s)' % (sec_music, type_music)),
        (sec_image == '.data', 'g_savedConfig in %s' % sec_image),
        (M.DATA_SECTION[0] <= M.G_MUSIC_VOLUME < M.DATA_SECTION[1], 'model .data range'),
    ]
    for ok, text in checks:
        if not ok:
            failures += 1
            notes.append(text)
    report('static', failures, len(checks), '0x4f8944 = 0x%08x in %s; image +0x08 = 0x%08x in %s' % (
        music, sec_music, image, sec_image), notes)


def test_defaults(elf, rng):
    ee = boot(elf, {M.CONFIG_SET_DEFAULTS, M.MUSIC_APPLY_VOLUME})
    box = {'status': 0}
    stub_audio(ee, box)
    failures, notes, count = 0, [], OPTIONS['cases']
    for _ in range(count):
        which = rng.choice((-1, -1, -1, 0, 1, 2, 3, 4, 7, -2))
        scheme = rng.choice((0, 1, 1, 2, -1))
        duck = gen_volume(rng)
        box['status'] = gen_status(rng)
        ee.mem.write(M.G_SAVED_CONFIG, bytes(rng.getrandbits(8) for _ in range(0xF8)))
        for _off, glob, _d in M.SCALARS:
            ee.mem.w32(glob, rng.getrandbits(32))
        before = ee.mem.u32(M.G_MUSIC_VOLUME)
        ee.mem.w32(M.G_DUCK, duck)
        ee.mem.w8(M.G_SCHEME, scheme & 0xFF)
        run(ee, M.CONFIG_SET_DEFAULTS, which)
        got_w, got_c = stored(ee), outside_calls(ee)
        want_w, want_c = M.config_set_defaults(which, scheme, duck, box['status'])
        want_c = model_calls(want_c)
        bad = got_w != want_w or got_c != want_c
        if which != -1 and ee.mem.u32(M.G_MUSIC_VOLUME) != before:
            bad = True
        if bad:
            failures += 1
            extra = sorted(set(got_w.items()) ^ set(want_w.items()))[:4]
            notes.append('which %d scheme %d: writes differ %s; calls %s / %s' % (
                which, scheme, ['%x=%x' % kv for kv in extra], got_c, want_c))
    report('defaults', failures, count, 'every word stored, applyVolume calls; music 0.5 only for which -1',
           notes)


def test_apply(elf, rng):
    ee = boot(elf, {M.MUSIC_APPLY_VOLUME})
    box = {'status': 0}
    stub_audio(ee, box)
    failures, notes, count = 0, [], OPTIONS['cases']
    for _ in range(count):
        volume, duck = gen_volume(rng), gen_volume(rng)
        box['status'] = gen_status(rng)
        ee.mem.w32(M.G_MUSIC_VOLUME, volume)
        ee.mem.w32(M.G_DUCK, duck)
        run(ee, M.MUSIC_APPLY_VOLUME)
        got_w, got_c = stored(ee), outside_calls(ee)
        want_c = model_calls(M.music_apply_volume(volume, duck, box['status']))
        if got_w or got_c != want_c:
            failures += 1
            notes.append('vol %08x duck %08x status %x: %s / %s, writes %s' % (
                volume, duck, box['status'], got_c, want_c, got_w))
    report('apply', failures, count, 'calls and f12; stores nothing', notes)


def test_gate(elf, rng):
    ee = boot(elf, {M.MUSIC_PLAY_LEVEL, M.MUSIC_PLAY_GLOBAL})
    ee.stub(M.AUDIO_SET_CHANNEL_VOLUME, ret=0)
    ee.stub(M.STREAM_QUEUE, ret=0)
    name = ee.alloc(32)
    failures, notes, count = 0, [], OPTIONS['cases']
    fixed = [M.MUSIC_GATE, M.MUSIC_GATE - 1, M.MUSIC_GATE + 1, 0, 0x80000000, 0xBF800000,
             R.ONE, M.DEFAULT_MUSIC, 0x3D4CCC08]
    passed_equal = None
    for index in range(count):
        volume = fixed[index] if index < len(fixed) else gen_volume(rng)
        duck = gen_volume(rng)
        flags = rng.choice((0x102, 0x103, 3, rng.getrandbits(16)))
        ee.mem.w32(M.G_MUSIC_VOLUME, volume)
        ee.mem.w32(M.G_DUCK, duck)
        # level
        run(ee, M.MUSIC_PLAY_LEVEL, name, flags)
        got = []
        for rec in ee.calls:
            if rec.target == M.AUDIO_SET_CHANNEL_VOLUME:
                got.append((rec.target, rec.args[0] & M32, rec.fargs[0] & M32))
            elif rec.target == M.STREAM_QUEUE:
                got.append((rec.target, rec.args[0] & M32, (rec.args[1] & M32, rec.args[2] & M32)))
        want = [(t, a, (name, b[1]) if t == M.STREAM_QUEUE else b)
                for t, a, b in M.music_play_level(volume, duck, name, flags)]
        # global: only the gate and the first call are modelled
        run(ee, M.MUSIC_PLAY_GLOBAL, name, flags)
        first = [(rec.target, rec.args[0] & M32, rec.fargs[0] & M32) for rec in ee.calls
                 if rec.stubbed][:1]
        want_g = []
        if M.music_gate_passes(volume):
            want_g = [(M.AUDIO_SET_CHANNEL_VOLUME, 2, M.channel_volume(duck, volume))]
        if volume == M.MUSIC_GATE:
            passed_equal = bool(got)
        if got != want or first != want_g:
            failures += 1
            notes.append('vol %08x: level %s / %s; global %s / %s' % (volume, got, want, first, want_g))
    report('gate', failures, count, 'queued iff not below 0x3d4ccccc; the equal pattern %s' % (
        'is queued' if passed_equal else 'is NOT queued'), notes)


def _random_image(rng):
    image = {}
    for offset, _glob, _d in M.SCALARS:
        image[offset] = gen_volume(rng) if offset in (0x04, 0x08, 0x0C, 0xC8, 0xCC) \
            else rng.choice((0, 1, 2, rng.getrandbits(32)))
    for slot in range(4):
        for k in range(9):
            image[M.ROWS_AT + slot * M.ROW_STRIDE + 4 * k] = rng.getrandbits(32)
    return image


def _write_image(ee, base, image):
    for offset, value in image.items():
        ee.mem.w32(base + offset, value)


def test_coretasks(elf, rng):
    ee = boot(elf, {M.GAME_ADD_CORE_TASKS, M.MUSIC_APPLY_VOLUME})
    box = {'status': 0}
    stub_audio(ee, box)
    failures, notes, count = 0, [], OPTIONS['cases']
    for _ in range(count):
        image = _random_image(rng)
        _write_image(ee, M.G_SAVED_CONFIG, image)
        duck = gen_volume(rng)
        box['status'] = gen_status(rng)
        ee.mem.w32(M.G_DUCK, duck)
        run(ee, M.GAME_ADD_CORE_TASKS)
        got_w = stored(ee)
        got_c = [(rec.target, rec.args[0] & M32,
                  rec.fargs[0] & M32 if rec.target == M.AUDIO_SET_CHANNEL_VOLUME else None)
                 for rec in ee.calls if rec.stubbed]
        want_w, apply_calls = M.game_add_core_tasks(image, duck, box['status'])
        want_targets = list(OTHER_CORE_CALLS) + [c[0] for c in apply_calls] + list(LATER_CORE_CALLS)
        got_targets = [c[0] for c in got_c]
        apply_got = [c for c in got_c if c[0] in (M.AUDIO_STREAM_STATUS, M.AUDIO_SET_CHANNEL_VOLUME)]
        save_act = [c[1] for c in got_c if c[0] == 0x2180A8]
        if (got_w != want_w or got_targets != want_targets
                or apply_got != model_calls(apply_calls) or save_act != [M32]):
            failures += 1
            extra = sorted(set(got_w.items()) ^ set(want_w.items()))[:4]
            notes.append('image music %08x: writes %s; targets %s' % (
                image[0x08], ['%x=%x' % kv for kv in extra], ['%x' % t for t in got_targets]))
    report('coretasks', failures, count, '0x4f8944 := image +0x08 verbatim, no clamp; all stores, call order',
           notes)


def test_optionsload(elf, rng):
    ee = boot(elf, {M.MEMCARD_OPTIONS_SCREEN, M.MUSIC_APPLY_VOLUME})
    box = {'status': 0, 'choice': 0, 'browser': 0}
    stub_audio(ee, box)
    texts = {}

    def lookup(emu):
        text = cstr(emu, emu.r[4] & M32)
        addr = 0x01600000 + 0x40 * len(texts)
        texts[addr] = text
        return addr

    ee.stub(M.STRING_LOOKUP, function=lookup)
    ee.stub(M.MESSAGE_BOX, function=lambda emu: box['choice'])
    ee.stub(M.MEMCARD_BROWSER, function=lambda emu: box['browser'])
    ee.stub(M.MEMCARD_SET_STATE, ret=0)
    failures, notes, count = 0, [], OPTIONS['cases']
    for index in range(count):
        state = (-1, 0, 1, 2, 3, 4)[index % 6] if index < 60 else rng.choice((-1, 0, 1, 2, 2, 3, 4))
        box['choice'] = rng.choice((0, 1, 2, 3, -1))
        box['browser'] = rng.choice((-1, 0, 1, 2))
        box['status'] = gen_status(rng)
        texts.clear()
        buffer = _random_image(rng)
        _write_image(ee, M.G_CONFIG_LOAD, buffer)
        duck = gen_volume(rng)
        ee.mem.w32(M.G_DUCK, duck)
        ee.mem.w32(M.G_OPTIONS_STATE, state & M32)
        run(ee, M.MEMCARD_OPTIONS_SCREEN)
        got_w = stored(ee)
        got_c = []
        for rec in ee.calls:
            if not rec.stubbed:
                continue
            a = [x & M32 for x in rec.args]
            if rec.target == M.STRING_LOOKUP:
                got_c.append((rec.target, (cstr(ee, a[0]),)))
            elif rec.target == M.MESSAGE_BOX:
                got_c.append((rec.target, (a[1], a[2], a[3], a[4]) if texts.get(a[0]) == 'options_warn'
                              else ('wrong text',)))
            elif rec.target == M.MEMCARD_BROWSER:
                got_c.append((rec.target, (a[0], a[2]) if texts.get(a[1]) == 'options_config'
                              else ('wrong text',)))
            elif rec.target == M.MEMCARD_SET_STATE:
                got_c.append((rec.target, (a[0], a[1])))
            elif rec.target == M.AUDIO_SET_CHANNEL_VOLUME:
                got_c.append((rec.target, (a[0], rec.fargs[0] & M32)))
            else:
                got_c.append((rec.target, (a[0],)))
        want_w, want_c = M.options_screen(state, buffer, box['choice'], box['browser'], duck,
                                          box['status'])
        want_c = [(t, tuple(x & M32 if isinstance(x, int) else x for x in args)) for t, args in want_c]
        if got_w != want_w or got_c != want_c:
            failures += 1
            extra = sorted(set(got_w.items()) ^ set(want_w.items()))[:4]
            notes.append('state %d choice %d browser %d: writes %s; calls %s / %s' % (
                state, box['choice'], box['browser'], ['%x=%x' % kv for kv in extra], got_c, want_c))
    report('optionsload', failures, count, 'states -1..4; state 2 copies buffer +0x08 to 0x4f8944 and image',
           notes)


def test_bootload(elf, rng):
    ee = boot(elf, {M.MEMCARD_BROWSER})
    ee.stub(0x2233E4, ret=0)                     # card op still busy? no
    failures, notes, count = 0, [], max(40, OPTIONS['cases'] // 5)
    for _ in range(count):
        mode = rng.choice((0, 1, 1, 2))
        or_bits = rng.choice((-1, -1, 0, 0x10, rng.getrandbits(8)))
        image = bytes(rng.getrandbits(8) for _ in range(M.CONFIG_SIZE))
        buffer = bytes(rng.getrandbits(8) for _ in range(M.CONFIG_SIZE))
        music_before = rng.getrandbits(32)
        ee.mem.write(M.G_SAVED_CONFIG, image)
        ee.mem.write(M.G_CONFIG_LOAD, buffer)
        ee.mem.w32(M.G_MUSIC_VOLUME, music_before)
        ee.mem.w32(M.G_BROWSER_STEP, M.BROWSER_COPY_STEP)
        ee.mem.w32(0x4F9544, M32)                # no directory listing drawn
        ee.mem.w32(0x8E11FC, 0)
        ee.mem.w32(0x8E11F8, 0)
        ee.mem.w32(0x88D3C4, 0)                  # timeout word, decremented to -1 on entry
        ee.mem.w32(0x88D3BC, 0)                  # g_cardOpResult
        ee.mem.w32(0x4F9540, 0)
        ee.mem.w32(0x88D3CC, or_bits & M32)
        ee.mem.w32(0x88D3A0, 1)                  # card state: the config screen
        run(ee, M.MEMCARD_BROWSER, mode, 0, 0)
        got = ee.mem.read(M.G_SAVED_CONFIG, M.CONFIG_SIZE)
        want = M.browser_config_copy(mode, image, buffer, or_bits)
        touched = any(a <= M.G_MUSIC_VOLUME < a + s for _pc, a, s, _v in ee.writes)
        if got != want or touched or ee.mem.u32(M.G_MUSIC_VOLUME) != music_before:
            failures += 1
            at = next((i for i in range(M.CONFIG_SIZE) if got[i] != want[i]), -1)
            notes.append('mode %d or %d: first image difference at +0x%x, 0x4f8944 written %s' % (
                mode, or_bits, at, touched))
    report('bootload', failures, count, 'mode != 0 copies the 0x2f8 bytes; 0x4f8944 never written', notes)


def _table_count(ee, table):
    n = 0
    while ee.mem.u32(table + 16 * n):
        n += 1
    return n


def test_slider(elf, rng):
    ee = boot(elf, {M.MENU_HANDLE_INPUT})
    pad = ee.alloc(0x58)
    flag = ee.alloc(16)
    failures, notes, count = 0, [], OPTIONS['cases']
    tables = (M.PAUSE_OPTIONS, M.FRONTEND_OPTIONS)
    info = []
    for table in tables:
        n = _table_count(ee, table)
        entry = table + 16
        ok = ee.mem.u32(entry + 8) == M.G_MUSIC_VOLUME and ee.mem.u32(entry + 4) == 4 \
            and cstr(ee, ee.mem.u32(entry)) == 'menu_music'
        info.append('%x: %d entries, music entry type %d' % (table, n, ee.mem.u32(entry + 4)))
        if not ok:
            failures += 1
            notes.append('table %x entry 1 is not the music slider' % table)
    timers = (0, M.TIMER_STEP, 0x3F000000, 0x3F4CCCCD, 0x3F59999A, 0x3F800000, 0x3F400000)
    masks = (0, 0x400000, 0x8000, 0x800000, 0x2000, 0x408000, 0x802000, 0x400000 | 0x2000,
             0x8000 | 0x800000)
    for index in range(count):
        table = tables[index & 1]
        n = _table_count(ee, table)
        term = table + 16 * n
        prev = rng.randrange(n)
        ee.mem.w32(term + 4, 1 | (prev << 8))
        slot = rng.randrange(4)
        timer = rng.choice(timers)
        value = gen_volume(rng) if rng.random() < 0.5 else rng.choice(
            (0, R.ONE, M.SLIDER_STEP, M.SLIDER_STEP - 1, 0x3F7FFFFF, 0x3F7DDDDE, M.DEFAULT_MUSIC))
        held = rng.choice(masks) | (rng.getrandbits(32) & ~(M.LEFT_MASK | M.RIGHT_MASK) & M32
                                    if rng.random() < 0.3 else 0)
        use_flag = rng.random() < 0.5
        ee.mem.w32(M.G_MENU_TIMER + 4 * slot, timer)
        ee.mem.w32(M.G_MUSIC_VOLUME, value)
        ee.mem.w32(pad + 0x8, held)
        ee.mem.w32(pad + 0x10, 0)
        ee.mem.w32(flag, 0xDEADBEEF)
        result = run(ee, M.MENU_HANDLE_INPUT, table, pad, flag if use_flag else 0, slot)
        got_w = stored(ee)
        new_value, new_timer, active = M.menu_slider_call(value, held, timer)
        want_w = {M.G_MENU_TIMER + 4 * slot: new_timer}
        if active:
            if held & (M.LEFT_MASK | M.RIGHT_MASK):
                want_w[M.G_MUSIC_VOLUME] = new_value
            want_w[term + 4] = 1 | (prev << 8)
        if use_flag:
            want_w[flag] = 0
        if got_w != want_w or result != 1 or [c for c in ee.calls if c.stubbed]:
            failures += 1
            notes.append('table %x value %08x held %x timer %08x: got %s want %s ret %d' % (
                table, value, held, timer, {('%x' % k): '%08x' % v for k, v in got_w.items()},
                {('%x' % k): '%08x' % v for k, v in want_w.items()}, result))
    # whole walks from the default, holding one direction, timer already at 1.0
    walks = []
    for direction, held in (('down', 0x400000), ('up', 0x800000)):
        ee.mem.w32(M.G_MUSIC_VOLUME, M.DEFAULT_MUSIC)
        ee.mem.w32(pad + 0x8, held)
        ee.mem.w32(M.G_MENU_TIMER, R.ONE)
        got_vals = []
        for _ in range(200):
            run(ee, M.MENU_HANDLE_INPUT, M.PAUSE_OPTIONS, pad, 0, 0)
            got_vals.append(ee.mem.u32(M.G_MUSIC_VOLUME))
            if len(got_vals) > 1 and got_vals[-1] == got_vals[-2]:
                break
        want_vals = M.slider_walk(M.DEFAULT_MUSIC, held)
        count += 1
        if got_vals != want_vals:
            failures += 1
            notes.append('walk %s differs at step %d' % (direction, next(
                (i for i, (a, b) in enumerate(zip(got_vals, want_vals)) if a != b), -1)))
        below = next((i + 1 for i, v in enumerate(got_vals) if not M.music_gate_passes(v)), None)
        walks.append('%s: %d steps to the clamp%s' % (
            direction, len(got_vals) - 1,
            ', below the gate after %d (0x%08x)' % (below, got_vals[below - 1]) if below else ''))
    report('slider', failures, count, '; '.join(info + walks), notes)


def test_commit(elf, rng):
    ee = boot(elf, {M.CONFIG_COMMIT, M.CONFIG_SET_DEFAULTS, M.GAME_ADD_CORE_TASKS,
                    M.MUSIC_APPLY_VOLUME})
    box = {'status': 0}
    stub_audio(ee, box)
    failures, notes, count = 0, [], max(60, OPTIONS['cases'] // 3)
    for _ in range(count):
        ee.mem.w8(M.G_SCHEME, 1)
        run(ee, M.CONFIG_SET_DEFAULTS, -1)
        image_music = gen_volume(rng) & 0x7FFFFFFF or 1      # avoid +0 / -0 equality pairs
        ee.mem.w32(M.G_SAVED_CONFIG + 8, image_music)
        run(ee, M.GAME_ADD_CORE_TASKS)                       # live == image everywhere
        live = image_music if rng.random() < 0.3 else (gen_volume(rng) & 0x7FFFFFFF or 2)
        ee.mem.w32(M.G_MUSIC_VOLUME, live)
        query, nosave, force = rng.choice((0, 1)), rng.choice((0, 1)), rng.choice((0, 0, 1))
        result = run(ee, M.CONFIG_COMMIT, force, query, nosave)
        saved = any(rec.target == M.CONFIG_SAVE_REQUEST for rec in ee.calls)
        got = (result, ee.mem.u32(M.G_SAVED_CONFIG + 8), saved)
        want = M.config_commit_music(live, image_music, query, nosave, force)
        if got != want:
            failures += 1
            notes.append('live %08x image %08x q%d n%d f%d: got %s want %s' % (
                live, image_music, query, nosave, force, got, want))
    report('commit', failures, count, 'count, image +0x08 after, save request', notes)


def test_chain(elf, rng):
    failures, notes = 0, []
    files = [None, 0, M.MUSIC_GATE, M.MUSIC_GATE - 1, R.ONE, f32(1.5), 0xBF800000,
             f32(0.25), M.DEFAULT_MUSIC]
    files += [rng.choice((None, gen_volume(rng))) for _ in range(11)]
    lines = []
    for music in files:
        ee = boot(elf, {M.CONFIG_SET_DEFAULTS, M.MUSIC_APPLY_VOLUME, M.MEMCARD_BROWSER,
                        M.GAME_ADD_CORE_TASKS, M.MUSIC_PLAY_LEVEL})
        box = {'status': 0}
        stub_audio(ee, box)
        ee.stub(M.STREAM_QUEUE, ret=0)
        ee.stub(0x2233E4, ret=0)
        seen = [ee.mem.u32(M.G_MUSIC_VOLUME)]
        ee.mem.w32(M.G_DUCK, R.ONE)
        run(ee, M.CONFIG_SET_DEFAULTS, -1)
        seen.append(ee.mem.u32(M.G_MUSIC_VOLUME))
        if music is not None:
            buffer = bytearray(ee.mem.read(M.G_SAVED_CONFIG, M.CONFIG_SIZE))
            buffer[8:12] = struct.pack('<I', music)
            ee.mem.write(M.G_CONFIG_LOAD, bytes(buffer))
            for addr, value in ((M.G_BROWSER_STEP, M.BROWSER_COPY_STEP), (0x4F9544, M32),
                                (0x8E11FC, 0), (0x88D3C4, 0), (0x88D3BC, 0), (0x4F9540, 0),
                                (0x88D3CC, M32), (0x88D3A0, 0)):
                ee.mem.w32(addr, value)
            run(ee, M.MEMCARD_BROWSER, 1, 0, 0)
        seen.append(ee.mem.u32(M.G_MUSIC_VOLUME))
        run(ee, M.GAME_ADD_CORE_TASKS)
        seen.append(ee.mem.u32(M.G_MUSIC_VOLUME))
        run(ee, M.MUSIC_PLAY_LEVEL, 0x01000000, 0x102)
        queued = any(rec.target == M.STREAM_QUEUE for rec in ee.calls)
        seen.append(ee.mem.u32(M.G_MUSIC_VOLUME))
        want = [v for _step, v in M.boot_music_volume(music)]
        want_queued = M.music_gate_passes(want[-1])
        if seen != want or queued != want_queued:
            failures += 1
            notes.append('file %s: seen %s want %s queued %s' % (
                music if music is None else '%08x' % music, ['%08x' % v for v in seen],
                ['%08x' % v for v in want], queued))
        if music in (None, R.ONE) and len(lines) < 2:
            lines.append('%s -> 0x%08x' % ('no file' if music is None else 'file 1.0', seen[-1]))
    report('chain', failures, len(files), 'first music request sees: ' + ', '.join(lines[:2]), notes)


def coverage():
    parts = []
    for name, (lo, hi) in RANGES.items():
        parts.append('%s %d of %d' % (name, len(COVERED[name]), (hi - lo) // 4))
    print('coverage (instructions executed of the range): ' + '; '.join(parts))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == '--seed' and argv:
            OPTIONS['seed'] = int(argv.pop(0), 0)
        elif item == '--cases' and argv:
            OPTIONS['cases'] = int(argv.pop(0), 0)
        elif item == '-v':
            OPTIONS['verbose'] = True
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable (sha256 %s); nothing was compared' % (elf, digest))
        return 0
    R.set_fpu('ps2')
    rng = random.Random(OPTIONS['seed'])
    tests = (test_static, test_defaults, test_apply, test_gate, test_coretasks, test_optionsload,
             test_bootload, test_slider, test_commit, test_chain)
    for test in tests:
        try:
            if test is test_static:
                test(elf)
            else:
                test(elf, rng)
        except (EmuError, MemoryFault, AssertionError) as error:
            report(test.__name__[5:], 1, 0, '%s: %s' % (type(error).__name__, error))
    coverage()
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d PASS, %d FAIL (seed %d, %d cases)' % (
        len(RESULTS), len(RESULTS) - len(failed), len(failed), OPTIONS['seed'], OPTIONS['cases']))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
