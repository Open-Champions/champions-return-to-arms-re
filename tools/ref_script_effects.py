#!/usr/bin/env python3
"""Bodies of the level-script calls that touch combat, creature AI, audio and the HUD.

tools/ref_natives.py is the handler: it decodes the script arguments and names the
call. This module is that call's body, for the commands a shipped script uses and
for the same bodies reached by commands the disc never calls. Each body was written
from an execution under tools/ee_emu.py; tools/difftest_script_effects.py is the
comparison. docs/script-effects.md is the prose, in disc-call order.

A Trace records the calls the body makes and supplies the return the original's
stub returned, so both sides branch the same way. Floats are raw patterns. Nothing
here draws the shared seed at 0x404464.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_core as C                         # noqa: E402
import ref_natives as N                      # noqa: E402

M32 = N.M32
s8, s16, s32 = N.s8, N.s16, N.s32

# HUD and audio words the bodies store. Names that already have a symbol keep it.
G_LOCAL_MENU = 0x41B69D          # g_localMenuOpen
G_HUD_SUPPRESSED = 0x4F66A8
G_LOADSCREEN = 0x506094          # g_loadscreenActive
G_CAMERA = 0x4F8450              # g_localCamera; mode word at +0x34
G_MESSAGE_TEXT = 0x86AB78
G_MESSAGE_FRAMES = 0x4F66E0
G_MESSAGE_FORCE = 0x4F66E2
G_HELP_TITLE = 0x86AA64
G_HELP_BODY = 0x86AA68
G_COMPASS_POS = 0x86A8F0
G_COMPASS_COUNTER = 0x4F66D5
G_COMPASS_TEXT = 0x86AAF0
G_BUST_TEXTURE = 0x4F6B48
G_BUST_TEXT = 0x86AAB0
G_BUST_COUNTER = 0x4F66D4
G_BUST_A = 0x86AB30
G_BUST_B = 0x86AB34
G_MUSIC_VOLUME = 0x4F8944
G_MUSIC_SCALAR = 0x4F894C        # the duck scalar music_playLevel multiplies
G_STREAMS = 0x876C10
G_SOUND_SEQS = 0x871A68
HELP_CLOSE_DELAY = 0x4F66CC
HELP_RES_LUMP, HELP_RES_NAME = 0x53C3B8, 0x53C3C0
MUSIC_GATE = 0x3D4CCCCC          # volume below this queues nothing
MUSIC_SCALE = 0x3F480000
CREATURE_VTABLE = 0x50CC58
SKELETON_TYPEINFO = 0x3CC62C
BOSS_PROP_KEY = 0x52FAB0
# (type-name address, property address or 0, track address). The words at those
# addresses are the table in research-audio docs/audio-playback.md.
BOSS_ROWS = (
    (0x52FE10, 0, 0x52FE70),
    (0x52FE20, 0x52FE30, 0x52FE90),
    (0x52FE20, 0x52FE38, 0x52FEA8),
    (0x52FE40, 0x52FE48, 0x52FEC0),
    (0x52FE50, 0, 0x52FED8),
    (0x52FEF0, 0, 0x52FF00),
    (0x52FF18, 0, 0x52FF28),
    (0x52FF48, 0, 0x52FF58),
    (0x52FDF0, 0, 0x52FF78),
    (0x52FF90, 0, 0x52FFA0),
    (0x52FE60, 0, 0x52FFB8),
)

# Commands whose callee this module executes, in the order a disc census ranks them.
# status: executed (the body, including every call it makes), partial (the body runs
# until a call whose own body is a different contract).
COMMANDS = (
    ('generateMonster', 136, 'partial', 'ScriptGenerator_spawn',
     'The wrapper is executed. world_createObject is the factory and is not entered.'),
    ('setMonsterVal', 114, 'executed', 'slot 34 / field stores',
     'which 1, 2, 3 and 5 are the handler stores. which 4 is slot 34, executed.'),
    ('setInfo', 95, 'executed', 'hud_showMessage',
     'text_lookup then the setter. The setter is executed.'),
    ('addHelpMessage', 65, 'executed', 'hud_showHelpMessage',
     'The setter is executed. sound_playOnObject is the playback contract.'),
    ('setCreatureParams', 56, 'executed', 'Creature_scaleStats',
     'Five scales, each divided by 100 in the handler.'),
    ('stopFollowingPath', 45, 'partial', 'virtual slot 27',
     'The base store is executed. A derived set-state is the animation table.'),
    ('deleteMonster', 33, 'partial', 'virtual slot 1',
     'Creature_dtor is executed. A class destructor that does not chain here is not.'),
    ('showBust', 31, 'executed', 'hud_setBust',
     'The setter is executed. The draw is hud-dynamic section 7.'),
    ('followPath', 28, 'partial', 'obj_runEveryFrame',
     'The flag and radius stores are the handler. The every-frame list is not entered.'),
    ('soundSequence', 27, 'partial', 'sound_setPlaysWhileFrozen',
     'The frozen flag is executed. sound_playOnObject is the playback contract.'),
    ('charmMonster', 20, 'executed', 'Creature_setCharm',
     'The stores are executed. handle_clear of a live target is the handle contract.'),
    ('setCFlag', 18, 'partial', 'creature_startBossMusic',
     'The name selector and the stop-then-queue calls are executed.'),
    ('rootMonster', 16, 'partial', 'virtual slot 27',
     'The root timer is the handler. State 0 is not rewritten by the filter.'),
    ('killMonster', 15, 'partial', 'virtual slot 27',
     'Flags and hit points are the handler. Death state 0x14 is the class set-state.'),
    ('initScriptSetParams', 13, 'executed', 'Creature_scaleStats',
     'Same scale as setCreatureParams, on the selected creature.'),
    ('hitPlayers', 11, 'partial', 'virtual slot 2',
     'The push stores are the handler. Take-damage is the combat contract.'),
    ('selectStopPath', 11, 'partial', 'virtual slot 27',
     'Same stop as stopFollowingPath, on the selected object.'),
    ('setWeaponType', 10, 'partial', 'creature_buildElementDamage',
     'The weapon slot-8 chain is executed. The element entry is the skills contract.'),
    ('selectSetMonsterVal', 9, 'executed', 'slot 34 / field stores',
     'Same values as setMonsterVal, on the selected object.'),
    ('addHelpMessageF', 7, 'executed', 'hud_showHelpMessage',
     'The handler formats into the static buffers, then the same setter.'),
    ('playGotItemSound', 3, 'partial', 'player_voice',
     'The handler picks the slot. The voice body is not entered.'),
    ('showCompass', 3, 'executed', 'hud_setCompassTarget',
     'The setter is executed.'),
    ('selectFollowPath', 3, 'partial', 'obj_runEveryFrame',
     'Same follow as followPath, on the selected object.'),
    ('reapEnemies', 1, 'partial', 'virtual slot 1',
     'Same destructor argument as deleteMonster.'),
    ('startMusic', 0, 'executed', 'music_playLevel',
     'No shipped call. The level-music gate and the two calls are executed.'),
    ('endMusic', 0, 'executed', 'stream_queueStop',
     'No shipped call. The stop marker is executed.'),
    ('startAudio', 0, 'partial', 'stream_playLevel',
     'No shipped call. The handler calls stream 1 with flags 2.'),
    ('sound', 0, 'partial', 'sound_playSample',
     'No shipped call. Playback of a named sample is the audio contract.'),
    ('healPlayer', 0, 'partial', 'sound_playOnObject',
     'No shipped call. The refill is the handler. The sound is playback.'),
    ('hudResetFadeScreen', 0, 'executed', 'hud_setFade',
     'No shipped call. The fade word is executed.'),
    ('hudFadeScreen', 0, 'executed', 'hud_stepFade',
     'No shipped call. The handler returns the clamped fade.'),
    ('followPlayer', 0, 'executed', 'Creature_setCharm',
     'No shipped call. Bit 23 in the handler, then the same charm.'),
    ('setMonsterRange', 0, 'executed', 'slot 34',
     'No shipped call. Slot 34 when the range is above 0.'),
    ('selectSetCFlag', 0, 'partial', 'creature_startBossMusic',
     'No shipped call. Same bit 0 path as setCFlag.'),
)


class Trace:
    """Calls made by a body, and the returns the other side's stubs give back."""

    def __init__(self, returns=None):
        self.calls = []
        self.returns = dict(returns or {})

    def call(self, name, *args, fargs=()):
        spec = self.returns.get(name, 0)
        ret = spec(*args) if callable(spec) else spec
        norm = tuple(a if isinstance(a, tuple) else int(a) & M32 for a in args)
        self.calls.append((name, norm, tuple(fargs)))
        return ret


def _same_text(mem, left, right):
    """Case-folding byte compare, the relationship libc_strcasecmp decides."""
    if left == 0 or right == 0:
        return False
    while True:
        a, b = mem.u8(left), mem.u8(right)
        if 65 <= a <= 90:
            a += 32
        if 65 <= b <= 90:
            b += 32
        if a != b:
            return False
        if a == 0:
            return True
        left, right = (left + 1) & M32, (right + 1) & M32


def _trunc_float(pattern, scale):
    """cvt.w.s of a product, then cvt.s.w back. Toward zero."""
    return C.from_int(C.to_int(C.mul(pattern, scale)))


def _trunc_half(mem, addr, scale, floor):
    """A halfword times a scale, truncated. Armour and the two damage halves
    become 1 when the truncated value is not strictly positive in its low 16 bits.
    The attack rating keeps a negative truncation."""
    n = C.to_int(C.mul(C.from_int(mem.s16(addr)), scale))
    if floor:
        shifted = (n << 16) & M32
        if shifted == 0 or shifted >= 0x80000000:
            n = 1
    return n & 0xFFFF


def scale_stats(mem, creature, scales):
    """Creature_scaleStats 0x1185d8 (creature, f12..f16). Five multipliers, already
    divided by 100 by the handler. No call, no seed. The float fields are stored
    as the truncated product. Returns nothing the handler reads."""
    hp, armour, damage, rating, xp = scales
    mem.w16(creature + 0xE4, _trunc_half(mem, creature + 0xE4, armour, True))
    mem.w32(creature + 0x228, _trunc_float(mem.u32(creature + 0x228), hp))
    mem.w32(creature + 0x22C, _trunc_float(mem.u32(creature + 0x22C), hp))
    mem.w16(creature + 0xD0, _trunc_half(mem, creature + 0xD0, damage, True))
    mem.w16(creature + 0xD2, _trunc_half(mem, creature + 0xD2, damage, True))
    mem.w16(creature + 0xD4, _trunc_half(mem, creature + 0xD4, rating, False))
    mem.w32(creature + 0xD8, _trunc_float(mem.u32(creature + 0xD8), xp))
    return 0


def set_charm(mem, fx, creature, frames, team):
    """Creature_setCharm 0x1189f0 (creature, frames, team). A creature already
    charmed for -1 frame, a non-creature, or a player is left alone. Otherwise
    the team byte and the frame half are stored, the target handle is cleared
    and then zeroed."""
    if mem.s16(creature + 0x312) == -1:
        return -1
    flags = mem.u32(creature + 0xC)
    if (flags & 0x20) == 0:
        return 0
    if flags & 0x40:
        return flags & 0x20
    mem.w8(creature + 0x310, s8(team) & 0xFF)
    mem.w16(creature + 0x312, frames & 0xFFFF)
    ret = fx.call('handle_clear', creature + 0x234, M32)
    mem.w32(creature + 0x234, 0)
    return ret


def slot27_set_state(mem, creature, state):
    """Base slot 27, 0x3c2688. Stores the low 16 bits at +0x232. No filter."""
    mem.w16(creature + 0x232, state & 0xFFFF)


def slot34_set_home_range(mem, creature, value):
    """Base slot 34, 0x3c2708. The low 16 bits become a float at +0x3c0."""
    mem.w32(creature + 0x3C0, C.from_int(value & 0xFFFF))


def show_message(mem, fx, text, frames, slot, force):
    """hud_showMessage 0x1d92a0 (text, frames, slot, force). Slot -1 skips the
    local-player test. Force 0 refuses while g_localMenuOpen is set. Otherwise
    the wide text is copied to 0x86ab78. Success leaves v0 as 0x4f0000, the lui
    of that buffer; the handler returns 0."""
    force = s8(force)
    if s32(slot) != -1 and fx.call('net_isLocalSlot', slot & M32) == 0:
        return 0
    menu = mem.s8(G_LOCAL_MENU)
    if force == 0 and menu != 0:
        return menu & 0xFF
    fx.call('wstr_copy', G_MESSAGE_TEXT, text & M32)
    mem.w16(G_MESSAGE_FRAMES, frames & 0xFFFF)
    mem.w8(G_MESSAGE_FORCE, force & 0xFF)
    return 0x4F0000


def show_help(mem, fx, slot, title, body):
    """hud_showHelpMessage 0x1d9830 (slot, title, body). An explicit remote slot
    returns 0. Offline always opens. Online opens only when some alive slot is
    local, and then tells that slot with hudmsg_sendMenuState(slot, 1, 0).
    Opening plays the help sample at volume 1 on no object, marks that handle
    play-while-frozen, and starts UI pulse 0. Return is 90, which the handler
    discards."""
    if s32(slot) != -1 and fx.call('net_isLocalSlot', slot & M32) == 0:
        return 0
    opened = mem.s8(N.G_NETWORK_MODE) == 0
    if not opened:
        index, count = 0, mem.u32(N.G_ALIVE_COUNT)
        while index < count:
            live = mem.u32(N.G_ALIVE_LIST + 4 * index)
            index += 1
            if fx.call('net_isLocalSlot', live):
                fx.call('hudmsg_sendMenuState', live & 0xFF, 1, 0)
                opened = True
                break
    if not opened:
        # The scan leaves v0 as 4 times the alive count. An explicit remote
        # slot already returned 0 above. The handler discards this.
        return (mem.u32(N.G_ALIVE_COUNT) << 2) & M32
    resource = fx.call('res_find', HELP_RES_LUMP, HELP_RES_NAME)
    handle = fx.call('sound_playOnObject', resource, 0, fargs=(0x3F800000,))
    fx.call('sound_setPlaysWhileFrozen', handle & M32)
    fx.call('ui_startPulse', 0)
    mem.w8(N.G_HELP_OPEN, 1)
    mem.w32(G_HELP_TITLE, title & M32)
    mem.w32(G_HELP_BODY, body & M32)
    mem.w32(HELP_CLOSE_DELAY, 90)
    return 90


def hud_blocked(mem):
    """The shared early-out of the compass and bust setters. The first failing
    gate's value is the return; None means the setter runs. Camera mode must be
    1 (follow). A null camera is a fault in the original and here."""
    suppressed = mem.s8(G_HUD_SUPPRESSED)
    if suppressed:
        return suppressed & 0xFF
    menu = mem.s8(G_LOCAL_MENU)
    if menu:
        return menu & 0xFF
    mode = (mem.u32(mem.u32(G_CAMERA) + 0x34) ^ 1) & M32
    if mode:
        return mode
    loading = mem.s8(G_LOADSCREEN)
    if loading:
        return loading & 0xFF
    flag = mem.u32(N.G_MENU_OPEN_FLAG)
    if flag:
        return flag
    return None


def set_compass(mem, fx, pos, text):
    """hud_setCompassTarget 0x1df668 (position, text). Copies the three position
    words to 0x86a8f0, copies the wide text to 0x86aaf0, and stores 5 at the
    compass counter. The fourth word of the vector is not written."""
    blocked = hud_blocked(mem)
    if blocked is not None:
        return blocked
    mem.w32(G_COMPASS_POS, pos[0])
    mem.w32(G_COMPASS_POS + 4, pos[1])
    mem.w32(G_COMPASS_POS + 8, pos[2])
    fx.call('wstr_copy', G_COMPASS_TEXT, text & M32)
    mem.w8(G_COMPASS_COUNTER, 5)
    return 0x870000


def set_bust(mem, fx, texture, text, left, right):
    """hud_setBust 0x1dfaa0 (texture, text, a, b). Copies the texture name to
    0x4f6b48 and the wide text to 0x86aab0, stores 5 at the bust counter, and
    stores the two integers at 0x86ab30 and 0x86ab34. The draw reads 0x86ab34
    as the maximum."""
    blocked = hud_blocked(mem)
    if blocked is not None:
        return blocked
    fx.call('strcpy', G_BUST_TEXTURE, texture & M32)
    fx.call('wstr_copy', G_BUST_TEXT, text & M32)
    mem.w8(G_BUST_COUNTER, 5)
    mem.w32(G_BUST_A, left & M32)
    mem.w32(G_BUST_B, right & M32)
    return 0x870000


def set_fade(mem, on):
    """hud_setFade 0x1df5d0. Stores 128 or 0 at g_hudFade. Turning it on returns
    128. Turning it off leaves v0 alone; pass unchanged=True to the caller."""
    mem.w32(0x4F66AC, 0 if s32(on) == 0 else 128)
    return None if s32(on) == 0 else 128


def step_fade(mem, fx, delta):
    """hud_stepFade 0x1df5ec (delta). Adds the delta, clamps to 0..128, and
    draws a 640 by 448 rectangle on layer 6 tinted fade<<24 when the result
    is not 0. Returns the clamped fade. This is the handler's return."""
    value = s32(mem.u32(0x4F66AC)) + s32(delta)
    if value < 0:
        value = 0
    elif value > 128:
        value = 128
    mem.w32(0x4F66AC, value & M32)
    if value != 0:
        fx.call('ui_drawRect', 0, 0, 640, 448, 6, (value << 24) & M32)
    return value


def set_plays_while_frozen(mem, handle):
    """sound_setPlaysWhileFrozen 0x216ad0. A handle of -1, or one whose bit 15
    is clear, stores nothing and returns -1. Otherwise byte +0x3b of sequence
    slot (handle & 0xff) becomes 1. The return is the byte offset of that slot."""
    handle = s32(handle)
    if handle == -1 or (handle & 0x8000) == 0:
        return -1
    slot = handle & 0xFF
    offset = slot * 0x4C
    mem.w8(G_SOUND_SEQS + offset + 0x3B, 1)
    return offset


def stream_count_addr(stream):
    """The queue-count word of one stream inside g_streams."""
    stream &= M32
    scaled = (((stream * 7) & M32) << 4) & M32
    scaled = (scaled + stream) & M32
    stride = (scaled << 2) & M32
    return (G_STREAMS + stride + 448) & M32, stride


def queue_stop(mem, stream):
    """stream_queueStop 0x211338 (stream). When fewer than 8 markers are queued,
    appends one stop (flag word 2) and increments the count. A full queue stores
    nothing. Returns the count after the call."""
    count_at, stride = stream_count_addr(stream)
    count = mem.u32(count_at)
    if count >= 8:
        return (count * 3) & M32
    base = (G_STREAMS + stride) & M32
    slot = (count * 48) & M32
    entry = (base + slot) & M32
    # The six stores the original makes for one marker. The count word is last.
    mem.w8(entry + 64, 0)
    mem.w32(entry + 0x6C, 2)
    mem.w32(entry + 80, 0)
    mem.w32(entry + 88, 0)
    mem.w32(entry + 92, 0)
    mem.w32(entry + 84, 0)
    count = (count + 1) & M32
    mem.w32(count_at, count)
    return count


def music_level_volume(mem):
    """The f12 music_playLevel passes to audio_setChannelVolume, or None when
    the gate is shut. scalar * volume * 0x3f480000."""
    volume = mem.u32(G_MUSIC_VOLUME)
    if C.lt(volume, MUSIC_GATE):
        return None
    return C.mul(C.mul(mem.u32(G_MUSIC_SCALAR), volume), MUSIC_SCALE)


def music_play_level(mem, fx, name, flags):
    """music_playLevel 0x215f48 (name, flags). Below the gate, no call, and v0
    stays 0x500000 (the lui of the volume word). Otherwise channel 2's volume
    is set and stream_playLevel(2, name, flags | 0x22) runs. startMusic passes
    flags 3, so the queued flags are 0x23."""
    level = music_level_volume(mem)
    if level is None:
        return 0x500000
    fx.call('audio_setChannelVolume', 2, fargs=(level,))
    return fx.call('stream_playLevel', 2, name & M32, (flags | 0x22) & M32)


def boss_music_name(mem, fx, creature):
    """creature_bossMusicName 0x10dbe0. A null creature or a null type name
    returns 0. Otherwise the first row whose type text matches, and whose
    property text matches when the row has one. No match returns 0."""
    if creature == 0:
        return 0
    type_name = mem.u32(creature + 0x34)
    if type_name == 0:
        return 0
    for type_addr, prop_addr, track in BOSS_ROWS:
        if not _same_text(mem, type_name, type_addr):
            continue
        if prop_addr:
            prop = fx.call('obj_getPropStr', creature, BOSS_PROP_KEY, 0)
            if not _same_text(mem, prop, prop_addr):
                continue
        return track
    return 0


def start_boss_music(fx, creature):
    """creature_startBossMusic 0x1192b0. No name: no call, return 0. A name
    stops stream 2 and queues music_playGlobal(name, 0x103)."""
    name = fx.call('creature_bossMusicName', creature)
    if name == 0:
        return 0
    fx.call('audio_streamStop', 2)
    return fx.call('music_playGlobal', name, 0x103)


def generator_spawn(mem, fx, gen, name):
    """ScriptGenerator_spawn 0x265fc4 (generator, className). Angle is the
    signed half at +0x38 minus 0x4000. Props are the word at +0x2c. The
    position is the three floats at +0x10 and a zero fourth word. No object
    returns 0x01000000 and stores nothing. An object gets cflags bit 24, the
    class-name pointer at +0x34, then virtual slot 0 with the vtable pointer.
    Skeleton_typeinfo is not given a fresh argument. A Skeleton gets slot 27
    with state 23."""
    angle = s16((mem.u16(gen + 0x38) - 0x4000) & 0xFFFF)
    props = mem.u32(gen + 0x2C)
    pos = (mem.u32(gen + 0x10), mem.u32(gen + 0x14), mem.u32(gen + 0x18), 0)
    obj = fx.call('world_createObject', name & M32, pos, angle & M32, props)
    if not obj:
        return 0x01000000
    mem.w64(obj + 0xA8, mem.u64(obj + 0xA8) | 0x1000000)
    mem.w32(obj + 0x34, name & M32)
    info = fx.call('vtable_slot0', mem.u32(obj + 0x48))
    skeleton = fx.call('Skeleton_typeinfo')
    if fx.call('rtti_typeInfoEquals', info, skeleton):
        fx.call('slot27', obj, 0x17)
        mem.w16(obj + 0x232, 0x17)
        return 0x3C2688
    return 0


def weapon2_set_element(fx, obj, which, kind):
    """Weapon2_setElement 0x3c2238 (weapon, which, type). which 0 calls
    creature_buildElementDamage twice; which 1 only the first; which 2 only
    the second. The script passes which 0 and the type as a byte."""
    kind &= 0xFF
    which = s32(which)
    if which < 2:
        fx.call('creature_buildElementDamage', (obj + 4) & M32, (obj + 0x50) & M32, kind)
    if which == 0 or which == 2:
        fx.call('creature_buildElementDamage', (obj + 4) & M32, (obj + 0xE0) & M32, kind)


def weapon_shield_slot8(fx, obj, which, kind):
    """WeaponShield_slot8 0x3c2500. One element call when which < 2."""
    if s32(which) < 2:
        fx.call('creature_buildElementDamage', (obj + 4) & M32, (obj + 0x50) & M32, kind & 0xFF)


def weapon_object_slot8(mem, fx, holder, which, kind):
    """WeaponObject_slot8 0x3c17e8. Forwards to slot 8 of the object at +4,
    with the type masked to a byte. The script's setWeaponType calls this
    slot on the object at creature +0x50."""
    kind &= 0xFF
    inner = mem.u32(holder + 4)
    fx.call('inner_slot8', inner, s32(which) & M32, kind)
    return inner


def creature_dtor(mem, fx, creature, flags):
    """Creature_dtor 0x117128 (creature, flags). Sets the vtable to the base,
    walks the spell list at +0x364 (slot 1 with 3 on each spell; an empty list
    walks nothing), clears five handles, calls 0x202500(creature+0x320, 2),
    then AnimState_dtor(creature+0x114, 0) and GameObject_dtor(creature, 0).
    Bit 0 of flags pool_frees the block. deleteMonster passes 3 to slot 1, so
    a class that chains here does free."""
    mem.w32(creature + 0x48, CREATURE_VTABLE)
    fx.call('iter_begin', (creature + 0x364) & M32)
    fx.call('iter_end', 2)
    for off in (0x364, 0x360):
        fx.call('handle_clear', (creature + off) & M32, 0)
    fx.call('fn_202500', (creature + 0x320) & M32, 2)
    for off in (0x2E4, 0x238, 0x234):
        fx.call('handle_clear', (creature + off) & M32, 0)
    fx.call('AnimState_dtor', (creature + 0x114) & M32, 0)
    fx.call('GameObject_dtor', creature & M32, 0)
    if flags & 1:
        fx.call('pool_free', creature & M32)
    return 0


def ranked():
    """COMMANDS in disc-call order, then the zero-call bodies."""
    return tuple(sorted(COMMANDS, key=lambda row: (-row[1], row[0])))


def main():
    for name, calls, status, native, note in ranked():
        print('%4d  %-22s  %-18s  %s' % (calls, name, status, native))
        print('      %s' % note)


if __name__ == '__main__':
    main()
