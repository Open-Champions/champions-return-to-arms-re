#!/usr/bin/env python3
"""Audio decisions of ordinary play: level entry, menus, voices, foley and hits.

The prose is docs/audio-session.md. tools/difftest_audio_session.py runs the
original functions in tools/ee_emu.py and compares them with this module.

Every result is an identifier (a stream entry name, a sequence name, a flag word),
a counter or a raw float pattern. Nothing here reads a disc, an executable or a
sample. Float arithmetic uses tools/ee_emu.py's R5900 helpers so raw patterns can
be compared.
"""

from ee_emu import fp_add, fp_cmp, fp_div, fp_mul, fp_to_int

FLOAT_ONE = 0x3F800000
FLOAT_ZERO = 0

# ---- the cosmetic generator (g_cosmeticSeed 0x404460) --------------------------------
LCG_MUL = 0x19660D
LCG_ADD = 0x3C6EF35F


def lcg(seed):
    """One step of the cosmetic generator; the callers use the high half."""
    return (seed * LCG_MUL + LCG_ADD) & 0xFFFFFFFF


# ---- level entry and the level poll countdown -----------------------------------------
ENTRY_TAG = "enttag"
ENTRY_MUSIC_FLAGS = 2          # music_playLevel(name, 2) at 0x1e5a34
ENTRY_TIMER_BASE = 1800        # argument of game_set4f83b8 0x1ec0e0
ENTRY_TIMER_SPAN = 1200
SESSION_COUNTDOWN = 60         # g_ambientCountdown store at 0x322db4


def level_entry(recall_return, recall_out, directory, rand_seed):
    """game_loadLevel 0x1e59a4-0x1e5a90.

    recall_return / recall_out are the bytes 0x41b51c / 0x41b51e. directory is
    None (no level directory) or the list of directory names in order; the walk
    stops at the first empty name. rand_seed is g_randSeed 0x404464: the slice
    first copies it into g_cosmeticSeed (0x1e59b4-0x1e59c4), whatever the gates say.
    Returns (calls, cosmetic seed). A call is ('music_playLevel', row, 2),
    ('timer', value) or ('stream_queueStop', 2).
    """
    seed = rand_seed & 0xFFFFFFFF
    if recall_return or recall_out:
        return [], seed
    if directory is not None:
        for row, name in enumerate(directory):
            if not name:
                break
            if ENTRY_TAG in name:
                seed = lcg(seed)
                value = (seed >> 16) % ENTRY_TIMER_SPAN + ENTRY_TIMER_BASE
                return [("music_playLevel", row, ENTRY_MUSIC_FLAGS), ("timer", value)], seed
    return [("stream_queueStop", 2)], seed


def session_countdown(recall_return, recall_out, countdown):
    """mainloop_runSession 0x322d94-0x322db8: the poll countdown before a load."""
    if recall_return or recall_out:
        return countdown
    return SESSION_COUNTDOWN


# ---- PvP levels -----------------------------------------------------------------------
PVP_TRACKS = (
    "mx_ba_avataroffear_l.vag", "mx_ba_broon_l.vag", "mx_ba_cazicthule_l.vag",
    "mx_ba_dozekar_l.vag", "mx_ba_droon_l.vag", "mx_ba_ironguardian_l.vag",
    "mx_ba_matanielmarr_l.vag", "mx_ba_proon_l.vag", "mx_ba_ralloszek_l.vag",
    "mx_ba_vanerhost_l.vag", "mx_ba_whitetormentor_l.vag",
)
PVP_FLAGS = 1


def pvp_music(pvp_mode_b, seed):
    """game_loadLevel 0x1e5e00-0x1e5e58: a random boss track, looped, in PvP mode B."""
    if not pvp_mode_b:
        return [], seed
    seed = lcg(seed)
    return [("music_playGlobal", PVP_TRACKS[(seed >> 16) % len(PVP_TRACKS)], PVP_FLAGS)], seed


# ---- options sliders ------------------------------------------------------------------
PREVIEW_FLAGS = 0x41
PAUSE_PREVIEW = ("mx_main_l.vag", 241, 7)        # name, timer value that fades, tick mask
FRONT_PREVIEW = ("mx_maintheme_l.vag", 121, 3)


def _changed(new, old):
    return fp_cmp(new, old) != 0


def slider_preview(screen, entry_old, entry_new, music_old, music_new, status2,
                   timer, draw_frame):
    """pauseMenu_task 0x18d728-0x18d7e8 ('pause') or frontend_run 0x1e1048-0x1e1114 ('front').

    entry_* is the edited entry in the pause menu and the effects volume in the front
    end. Returns (calls, timer). Calls are in order; ('status', 2) is one
    audio_streamStatus(2) query.
    """
    name, fade_at, tick_mask = PAUSE_PREVIEW if screen == "pause" else FRONT_PREVIEW
    calls = []
    if _changed(entry_new, entry_old) and (draw_frame & tick_mask) == 0:
        calls.append(("lump_get",))
        calls.append(("sound_playOnObject", FLOAT_ONE, 0))
    if _changed(music_new, music_old):
        calls.append(("status", 2))
        if not status2 & 0x20:
            calls.append(("music_playGlobal", name, PREVIEW_FLAGS))
        timer = 0
    if screen == "front":
        calls.append(("music_applyVolume",))
        calls.append(("audio_sendVolumes",))
    timer = (timer + 1) & 0xFFFFFFFF
    signed = timer - (1 << 32) if timer & 0x80000000 else timer
    if signed >= fade_at:
        calls.append(("status", 2))
        if status2 & 0x40:
            calls.append(("stream_queueStop", 2))
    return calls, timer


# ---- character voice lines (player_voice 0x1b7ba8) ------------------------------------
VOICE_PREFIX = ("bwm", "bwf", "erm", "erf", "ecm", "ecf", "ewm", "ewf", "esm", "esf",
                "vm", "im")
VOICE_LINES = {   # kind -> (first number, count) for models 0-9
    0: (1, 1), 1: (11, 3), 3: (14, 1), 4: (18, 1), 5: (19, 1), 7: (43, 1),
    8: (41, 2), 9: (35, 2),
}
VOICE_LINES_10_11 = {0: (1, 2), 1: (11, 2), 4: (21, 2), 5: (31, 2), 9: (41, 2)}
VOICE_STREAM = 1
VOICE_FLAGS = 0x24
VOICE_KINDS = 10        # kinds 10 and above never play


def player_voice(model, kind, local, cutscene, net_byte, menu_byte, voice_status,
                 hp_bits, seed):
    """Returns (calls, seed). model is record +0x54 (0-11), hp_bits is record +0xac.

    Calls: ('isLocal',), ('status', 1), ('playGlobalRandom', 1, name, 0x24).
    Kind 2 compares the string at 0x41b721 with 34 fixed names (34 strcmp/strstr sites in
    0x1b7ba8-0x1b8f28). A match calls stream_playGlobal 0x215c20, which is not modelled:
    this model is only valid for strings that match none of them, such as every
    g_levelTable name and the empty string (difftest property 'idle voice').
    """
    calls = [("isLocal",)]
    if not local or cutscene:
        return calls, seed
    if not net_byte and menu_byte:
        return calls, seed
    if 0 <= kind < VOICE_KINDS:
        calls.append(("status", 1))
        if voice_status & 0x20:
            return calls, seed
    if fp_cmp(hp_bits, FLOAT_ZERO) <= 0:     # R5900 compare: no NaN, -0 equals +0
        return calls, seed
    if not 0 <= kind < VOICE_KINDS:
        return calls, seed
    table = VOICE_LINES_10_11 if model in (10, 11) else VOICE_LINES
    if kind not in table:
        return calls, seed
    first, count = table[kind]
    number = first
    if count > 1:
        seed = lcg(seed)
        number = first + (seed >> 16) % count
    calls.append(("playGlobalRandom", VOICE_STREAM, "%s%03d" % (VOICE_PREFIX[model], number),
                  VOICE_FLAGS))
    return calls, seed


# ---- footstep foley (sound_playFoley 0x1e7c40) ---------------------------------------
FOLEY_LUMP = "fx.lmp"
FOLEY_ARMOUR = ((0x400000, "foly_plate", 5), (0x200000, "foly_chainmail", 5),
                (0x100000, "foly_leather", 5), (0x80000, "foly_cloth", 4))
FOLEY_DEFAULT_FLAGS = 0x80000      # Player_footstep 0x1beef8 when neither equipped slot 4
                                   # (+0x4400) nor slot 10 (+0x4418) holds an item


def foley(in_water, flags, seed):
    """Returns (sequence name or None, seed). flags is the 32-bit word +0x08 of the item in
    equipped slot 4 (record +0x4400), else slot 10 (+0x4418), else FOLEY_DEFAULT_FLAGS."""
    if in_water:
        seed = lcg(seed)
        return "fs_water%d.anm" % (((seed >> 16) & 1) + 1), seed
    if not flags & 0x780000:
        return None, seed
    for bit, stem, count in FOLEY_ARMOUR:
        if flags & bit:
            seed = lcg(seed)
            high = seed >> 16
            index = (high & 3) if count == 4 else high % count
            return "%s%d.anm" % (stem, index + 1), seed
    raise AssertionError("unreachable")


# ---- hit sounds (sound_playHit 0x1e7e40) --------------------------------------------
HIT_LUMP = "fx.lmp"
# creature victims: object flag bit (of the 64-bit word +0xa8), in test order
HIT_CREATURE = ((35, "lthr"), (36, "chnmail"), (37, "mtlplate"), (40, "bone"),
                (39, "exo"), (38, "stone"), (34, "cloth"))
# player victims: word +0x08 of the item in equipped slot 4 (record +0x4400), in test order
HIT_PLAYER = ((0x80000, "cloth"), (0x100000, "lthr"), (0x200000, "chnmail"),
              (0x400000, "mtlplate"))
HIT_SLSH = ("stone", "exo")
HIT_LIGHT = 0x3E800000     # 0.25
HIT_MEDIUM = 0x3F199999    # about 0.6


def hit_material(victim_is_player, creature_flags, armour_flags):
    """armour_flags is the word +0x08 of the item in equipped slot 4 (record +0x4400), or
    None when that slot is empty."""
    if victim_is_player:
        if armour_flags is None:
            return "flesh"
        for bit, name in HIT_PLAYER:
            if armour_flags & bit:
                return name
        return "flesh"
    for bit, name in HIT_CREATURE:
        if creature_flags >> bit & 1:
            return name
    return "flesh"


def hit_name(victim_is_player, creature_flags, armour_flags, damage_flags, landed,
             amount_bits, max_hp_bits, model="ps2"):
    """Sequence name sound_playHit asks fx.lmp for, or None when it plays nothing."""
    if damage_flags & 0xC000:
        return None
    material = hit_material(victim_is_player, creature_flags, armour_flags)
    if damage_flags & 8:
        kind = "slsh" if material in HIT_SLSH else "slash"
    elif damage_flags & 4:
        kind = "pierce"
    else:
        kind = "bludg"
    if not landed:
        weight = "miss"
    else:
        ratio = fp_div(amount_bits, max_hp_bits, model)
        if fp_cmp(ratio, HIT_LIGHT) < 0:
            weight = "lt"
        elif fp_cmp(ratio, HIT_MEDIUM) < 0:
            weight = "med"
        else:
            weight = "hvy"
    return "hit_%s_%s_%s.anm" % (material, kind, weight)


# ---- option defaults (config_setDefaults(-1) 0x1e6238) --------------------------------
OPTION_DEFAULTS = {          # global -> value; the options image copy is +0x08 / +0x0c / +0x10
    "g_sfxVolume": 0x3F000000, "g_musicVolume": 0x3F000000, "stereo": 1,
}
OPTION_IMAGE = {"g_sfxVolume": 0x4F8940, "g_musicVolume": 0x4F8944, "stereo": 0x4F8948}
OPTION_SAVED = {"g_musicVolume": 0x4F8F40, "g_sfxVolume": 0x4F8F44, "stereo": 0x4F8F48}


# ---- sound_update order and channel volumes -----------------------------------------
UPDATE_ORDER = ("music_updateDucking", "sound_pauseResumeVoices", "stream_serviceQueues",
                "soundSeq_updateAll", "ambient_update", "sound_flushSpuCommands",
                "endFlags", "audio_setChannelVolume", "audio_sendVolumes")
CHANNEL0_SCALE = 0x3F160000   # 0.5859375 x min(2 x music, 1)
MUSIC_CHANNEL_SCALE = 0x3F480000


def update_order(sound_frame, stream0_music):
    """Callees of sound_update 0x212670, in order, when every callee returns 0."""
    out = ["music_updateDucking", "sound_pauseResumeVoices"]
    if sound_frame & 3 == 0:
        out.append("stream_serviceQueues")
    out += ["soundSeq_updateAll", "ambient_update", "sound_flushSpuCommands"]
    if sound_frame & 7 == 0:
        out += ["endFlags", "endFlags"]
    if not stream0_music:
        out.append("audio_setChannelVolume")
    if (sound_frame + 1) & 15 == 0:
        out.append("audio_sendVolumes")
    return out


def _fmin(a, b):
    return a if fp_cmp(a, b) < 0 else b


def _fmax(a, b):
    return a if fp_cmp(a, b) > 0 else b


def channel0_volume(music_bits, model="ps2"):
    """Argument sound_update passes to audio_setChannelVolume(0, v) (0x212848-0x212870)."""
    doubled = fp_add(music_bits, music_bits, model)
    return fp_mul(_fmin(doubled, FLOAT_ONE), CHANNEL0_SCALE, model)


def music_channel_volume(duck_bits, music_bits, model="ps2"):
    """music_applyVolume 0x215e78: argument for channel 2 when stream 2 carries music."""
    return fp_mul(fp_mul(duck_bits, music_bits, model), MUSIC_CHANNEL_SCALE, model)


def set_channel_volume(stored_bits, value_bits):
    """audio_setChannelVolume 0x216690: (new stored pattern, whether volumes are sent)."""
    clamped = _fmin(_fmax(value_bits, FLOAT_ZERO), FLOAT_ONE)
    if fp_cmp(clamped, stored_bits) == 0:
        return stored_bits, False
    return clamped, True


def send_volumes_payload(stereo_word, channels, model="ps2"):
    """The 16 bytes audio_sendVolumes 0x2166e0 sends with RPC 0x80, as four words."""
    scale = 0x43800000   # 256.0
    return (stereo_word & 0xFFFFFFFF,) + tuple(
        fp_to_int(fp_mul(c, scale, model)) & 0xFFFFFFFF for c in channels)
