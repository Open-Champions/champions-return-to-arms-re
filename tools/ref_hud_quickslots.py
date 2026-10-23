"""HUD quick slots for SLUS-20973 v2.00: potion / ammunition notices, the D-pad
quick-cast selector and its skill icons. See docs/spec/hud-quickslots.md.

Authored from addressed instruction sequences; no game data or code is embedded.
Extends tools/ref_hud_dynamic.py (notice drawing, selector fade and ring) with the
writers of the notice timers, the potion counts, the selector's input gates, its
button tail (messages, name, prompt) and the icon lookup.

Floats are raw 32-bit patterns handled by ref_core (PS2 FPU model).
"""
import ref_core as F
import ref_hud_dynamic as H

# ---------------------------------------------------------------------------------------
# Notice timers (draw: hud_drawPlayerStatus 0x1da864..0x1daca0, see ref_hud_dynamic).
# ---------------------------------------------------------------------------------------
NOTICE_TIMERS = 0x41b828        # g_hudNoticeTimers, s32[4][8]; slot stride 0x20
NOTICE_ROWS = 0x41b8a8          # g_hudNoticeRows, s32[4][8]; written, never read by the draw
COUNT_HEALTH = 0x41b940         # s32[4], player_countPotions(slot, 0) 0x1ba6f8
COUNT_MANA = 0x41b950           # s32[4], player_countPotions(slot, 1) 0x1ba6e0
NOTICE_LONG = 0xf0              # 240 frames: counted lines 4..7 (0x1ba0c4, 0x1a75c4, 0x1a88a8)
NOTICE_SHORT = 0x78             # 120 frames: lines 0..3 (0x1ba194, 0x1a763c, 0x205d44)
LOW_POTIONS = (1, 5)            # count shown when 1..5 left (0x1ba0b0 sltiu 5 after -1)
LOW_AMMO = (1, 20)              # count shown when 1..20 left (0x1a75b0, 0x1a8894 sltiu 0x14)

# Every store to the timer table found (tools/gxref.py over 0x41b828..0x41b95c).
# (line, frames, store address, function, condition). Rows (0x41b8a8 + same index)
# are written right after each timer with hud_countActiveNotices(slot, line).
NOTICE_STARTERS = (
    (0, NOTICE_SHORT, 0x205d50, 'Camera_followZoomInput', 'zoom input past its limit (camera, per machine)'),
    (0, NOTICE_SHORT, 0x206378, 'Camera_followRotateInput', 'rotate input with a stick value above 0.5 (camera, per machine)'),
    (1, NOTICE_SHORT, 0x1ba1a8, 'Player_usePotion', 'health potion wanted (hp + pending < max) but none in bag 2'),
    (2, NOTICE_SHORT, 0x1ba5a0, 'Player_usePotion', 'mana potion wanted but none in bag 2'),
    (3, NOTICE_SHORT, 0x1a7650, 'Player_run', 'ranged shot left no ammunition (+0x4410 == 0), real player only'),
    (3, NOTICE_SHORT, 0x1a7e0c, 'Player_run', 'same, second ranged release site'),
    (4, NOTICE_LONG, 0x1ba0d8, 'Player_usePotion', 'health potion used and 1..5 health potions left'),
    (5, NOTICE_LONG, 0x1ba4bc, 'Player_usePotion', 'mana potion used and 1..5 mana potions left'),
    (6, NOTICE_LONG, 0x1a75d0, 'Player_run', 'ammunition stack +0x4410 holds 1..20 after a shot'),
    (6, NOTICE_LONG, 0x1a7da0, 'Player_run', 'same, second ranged release site'),
    (7, NOTICE_LONG, 0x1a88bc, 'Player_run', 'thrown stack holds 1..20 after a throw'),
    (7, NOTICE_LONG, 0x1bb9ec, 'Player_weaponSwapInput', 'swap to weapon set 1 whose primary has class 6 (thrown)'),
    (7, NOTICE_LONG, 0x319cf0, 'SkillFireAxe_cast', 'conjured axe stack holds 1..20'),
    (7, NOTICE_LONG, 0x31a624, 'SkillColdAxe_cast', 'conjured axe stack holds 1..20'),
)
# Clearers: player_initNewCharacter 0x1b1f88 (all eight timers and rows of the slot);
# menu_openInventory 0x1c1720..0x1c172c (timers 3, 6, 7 of the slot); the draw
# (0x1dac84 timer -1, 0x1dac94 row 0 at <= 0).


def start_notice(timers, rows, line, frames):
    """One starter on one slot's eight timers/rows: the timer is stored first, then the
    row = hud_countActiveNotices(slot, line) 0x1dacf4 (which sees the new timer)."""
    timers = list(timers)
    rows = list(rows)
    timers[line] = frames
    rows[line] = H.count_active_notices(timers, line)
    return timers, rows


# ---------------------------------------------------------------------------------------
# Potions (bag 2 = record +0x2540, 64 cells of 0x48, count at +0x3740).
# ---------------------------------------------------------------------------------------
BAG2, BAG2_COUNT, CELL = 0x2540, 0x3740, 0x48
POTION_NAMES_HEALTH = 0x4ef478   # 9 name pointers, smallest first (Player_usePotion 0x1b9e2c)
POTION_NAMES_MANA = 0x4ef4a0     # 9 name pointers, smallest first (0x1ba20c)
POTION_NAMES_COUNT = 0x4ef4c8    # 18 pointers: 0..8 mana, 9..17 health (largest first)
REGEN_FRACTION = 0x3b088888      # 0.0020833 = 1/480: R+0xb8 / +0xbc = min(max x this, ...)
REGEN_CAP = 0x3effffff           # just under 0.5
POTION_STEP = 0x42700000         # 60.0: pending += (size + 1) * 60
USE_COUNTER = (0x4f85ca, 0x4f85c8)   # u16 use counters, health and mana


def count_potions(bag, kind):
    """player_countPotions(slot, kind) 0x1ba5f8. bag: list of (name, quantity), name
    = ('h', size) / ('m', size) / anything else. kind 0 counts health names
    (table entries 9..17, global 0x41b940), any other kind the mana names (0..8,
    global 0x41b950; note 'kind == 1' picks the store, 'kind != 0' the names).
    Returns (total, global address)."""
    want = 'h' if kind == 0 else 'm'
    total = 0
    for name, qty in bag:
        if isinstance(name, tuple) and name[0] == want:
            total += F.s16(qty & 0xffff)
    return total, (COUNT_MANA if kind == 1 else COUNT_HEALTH)


def potion_size(missing_plus, found):
    """0x1b9e9c..0x1b9f2c: wanted = trunc(missing + 1) / 60 (C division), capped at 8;
    if absent, size 8 if present, else the largest present, else -1.
    missing_plus is the raw float max - (cur + pending) + 1.0."""
    s = int(F.s32(F.to_int(missing_plus)) / 60)
    if s >= 9:
        s = 8
    if found[s] >= 0:
        return s
    if found[8] >= 0:
        return 8
    for i in range(7, -1, -1):
        if found[i] >= 0:
            return i
    return -1


def use_potion(st):
    """Player_usePotion(P, kind, ...) 0x1b9cb8 for kind 0 (health) and 1 (mana).

    st: dict with copy (object flag 0x20000), hp, maxhp, hp_pending (+0xb4), mana,
    maxmana, mana_pending (+0xc8) (raw floats), bag (list of (name, qty)), local
    (net_isLocalSlot), menu_open (0x41b69d), grid (0x4ebbb0 nonzero), kind,
    timers, rows (eight each). Returns a dict of what changes."""
    out = {'returned_early': True, 'notices': [], 'removed': None, 'sent_drop': False,
           'sound': None, 'count': None, 'regen': None, 'counter': None}
    if st['copy'] or F.le(st['hp'], F.ZERO):
        return out
    out['regen'] = (F.fmin(F.mul(st['maxhp'], REGEN_FRACTION), REGEN_CAP),
                    F.fmin(F.mul(st['maxmana'], REGEN_FRACTION), REGEN_CAP))
    kind = st['kind']
    if kind == 0:
        cur, mx, pend, tag, no_line, count_line = st['hp'], st['maxhp'], st['hp_pending'], 'h', 1, 4
    else:
        cur, mx, pend, tag, no_line, count_line = st['mana'], st['maxmana'], st['mana_pending'], 'm', 2, 5
    have = F.add(cur, pend)
    if F.le(mx, have):
        return out
    out['returned_early'] = False
    found = [-1] * 9
    for i in range(9):
        for j, (name, _q) in enumerate(st['bag']):
            if name == (tag, i):
                found[i] = j
    size = potion_size(F.add(F.sub(mx, have), F.ONE), found)
    timers, rows = list(st['timers']), list(st['rows'])
    if size == -1:
        timers, rows = start_notice(timers, rows, no_line, NOTICE_SHORT)
        out['notices'].append((no_line, NOTICE_SHORT))
        out.update(timers=timers, rows=rows, pending=pend)
        return out
    pend = F.add(pend, F.mul(F.from_int(size + 1), POTION_STEP))
    if F.lt(mx, F.add(cur, pend)):
        pend = F.sub(mx, cur)
    if st['local']:
        out['sound'] = 'potion_health.anm' if kind == 0 else 'potion_mana.anm'
    bag = [list(c) for c in st['bag']]
    if st['menu_open'] and st['local'] and st['grid']:
        out['sent_drop'] = True
    else:
        cell = found[size]
        bag[cell][1] = (bag[cell][1] - 1) & 0xffff
        if bag[cell][1] == 0:
            out['removed'] = cell
    n, _g = count_potions([tuple(c) for c in bag], kind)
    out['count'] = n
    if LOW_POTIONS[0] <= n <= LOW_POTIONS[1]:
        timers, rows = start_notice(timers, rows, count_line, NOTICE_LONG)
        out['notices'].append((count_line, NOTICE_LONG))
    out['counter'] = USE_COUNTER[0 if kind == 0 else 1]
    out.update(timers=timers, rows=rows, pending=pend, bag=[tuple(c) for c in bag], size=size)
    return out


# ---------------------------------------------------------------------------------------
# Quick-cast selector, hud_spellSelect(slot, page, menu, kind, value) 0x1dd270.
# ---------------------------------------------------------------------------------------
PAD_HELD = 0x4028d8             # g_rawPads 0x4028d0 + 8, stride 0x58 (raw local pad)
PAD_PRESSED = 0x4028dc          # g_rawPads + 0xc
PAD_STRIDE = 0x58
DPAD_UP, DPAD_RIGHT, DPAD_DOWN, DPAD_LEFT = 0x1000, 0x2000, 0x4000, 0x8000
BTN_MENU_ACCEPT = 0x41b960      # s32[4] mask; 0x1ddce8 reads entry 0 for every slot
BTN_ABILITY_A = 0x41b990        # g_btnAbilityA
BTN_ABILITY_B = 0x41b9a0        # g_btnAbilityB
BTN_USE = 0x41b9c0              # g_btnUse
SELECTOR_HELD = 0x41b818        # g_spellSelectorHeld s32[4]
SELECTOR_DIR = 0x4f66b8         # g_spellSelectorDir s32[4]
SELECTOR_ALPHA = 0x86a8d8       # g_spellSelectorAlpha s32[4]
BUST_LATCH = 0x4f66a9           # byte set while alpha > 64, slot >= 2, 4 players
MASK_TABLE = 0x5d0bc8           # net_maskLocalButtons entries, 12 bytes per slot
MASK_FRAMES = 3                 # 0x1dd4a4
RES_BACKGROUND = 0x86aa30       # resref hud.lmp / spellbook.tex (hud_staticInit 0x1e0888)
RES_BLANK = 0x86aa40            # resref icons.lmp / icblank.tex (0x1e08ac)
RES_BOX = 0x86aa20              # resref hud.lmp / hudbox.tex (0x1e0864), not used here
ICON_TABLE = 0x4f85e0           # hud_loadIcons 0x1e7068: texture per index
ICON_TABLE_INDEX = {            # index -> icons.lmp resource (store offsets 0x64..0x98)
    25: 'icroot.tex', 28: 'icfroststorm.tex', 30: 'noarrows.tex', 31: 'nohealth.tex',
    32: 'nomana.tex', 33: 'nocamera.tex', 34: 'counthealth.tex', 35: 'countmana.tex',
    36: 'countarrows.tex', 37: 'icslam.tex', 38: 'countthrown.tex'}
MENU_ITEM_ICON = 37             # 0x4f8674 = ICON_TABLE + 0x94: menu icon when kind != 1
RECORDS = 0x4440                # ability records, 0x68 bytes; ring k uses record k
RECORD_SIZE = 0x68
QUICK_A, QUICK_B = 0x4a84, 0x4a85
GLYPH_MASKS = (0x20, 0x10, 0x80, 0x40, 0x8000, 0x2000, 0x1000, 0x4000, 0x4, 0x1, 0x8, 0x2)  # 0x53c8f0
GLYPH_BASE = 0x7b               # 0x1df0e4: glyph char = 0x7b + index
BUTTON_CONFIG = 0x4f8f6c        # u32[4][9] pad mask per logical button (config_setDefaults)
LABEL_COLOUR = 0x323c3c         # 0x1ddaec
GREY = 0x808080
TEXT_WIDTH_LABEL = 100000       # 0x1ddbec
TEXT_WIDTH_NAME = 1000000       # 0x1dde34
MSG_QUICKSLOT, MSG_ASSIGN, MSG_QUICKCAST = 0, 1, 13

# The gates, in test order (0x1dd374..0x1dd404). Any one set blocks the D-pad read
# unless g_localMenuOpen 0x41b69d is set (then the pad is read anyway).
GATES = (
    ('menu_lockout', 'g_menuInputLockout 0x41b4fc != 0'),
    ('dialog', 'dialog_isOpen() 0x22fbc0'),
    ('camera', 'g_localCamera 0x4f8450 -> +0x34 != 1 (not follow mode)'),
    ('paused', 'g_paused 0x41b4f4 != 0'),
    ('pause_menu', 'byte 0x44fa78 != 0 (pauseMenu_open 0x18e3fc / close 0x18dfd4)'),
    ('memcard', 'memcard_isBusy() 0x217518'),
    ('medal', 'g_medalDialogTicks 0x4f7114 != 0'),
    ('jumpgate', 'task_isRunning("jumpgate") 0x19e5e8'),
    ('input_block', 'byte 0x4f66c8 != 0 (cleared by hud_addTasks 0x1dc230)'),
)


def button_glyph(config_mask):
    """0x1df060(slot, n): first index i of GLYPH_MASKS equal to the slot's configured
    mask for logical button n gives the font character 0x7b + i; 0 when none."""
    for i, m in enumerate(GLYPH_MASKS):
        if m == config_mask:
            return GLYPH_BASE + i
    return 0


def pad_axes(bits):
    """0x1dd434..0x1dd478: right then left set dx, up then down set dy (later wins).
    Returns (dx, dy, any_direction_bit)."""
    dx = dy = 0
    if bits & DPAD_RIGHT:
        dx = 1
    if bits & DPAD_LEFT:
        dx = -1
    if bits & DPAD_UP:
        dy = -1
    if bits & DPAD_DOWN:
        dy = 1
    return dx, dy, bool(bits & 0xf000)


def pad_readable(gates, local_menu_open):
    return local_menu_open or not any(gates.get(name) for name, _ in GATES)


def record_icon(rec):
    """Icon of one ability record (0x1dd8c4..0x1dd950). rec: dict id (s16), newstyle
    (name equals 'newstyle'). Returns ('blank',), ('skill', id) = vslot 7 of
    g_skillTable[id] (table offset 0x38), or ('table', id) = ICON_TABLE[id], which
    falls back to the blank when the entry is 0."""
    if rec['id'] == -1:
        return ('blank',)
    if rec['newstyle']:
        return ('skill', rec['id'])
    return ('table', rec['id'])


def record_name_key(rec):
    """Text key of the selected record (0x1ddd30..0x1dddc4): 'EmptySpellSlot', or
    '<skill internal name>_name' (Skill +0x00) for new-style records, else
    '<record name>_name'."""
    if rec['id'] == -1:
        return ('key', 'EmptySpellSlot')
    if rec['newstyle']:
        return ('skillname', rec['id'])
    return ('recname', rec['name'])


def selector_frame(st):
    """One call of hud_spellSelect. st keys: slot, page, menu, kind, value, players,
    network, local, hp (raw), gates, local_menu_open, held_bits, pressed_bits,
    masks {a, b, use: the slot's; accept: entry 0 of 0x41b960}, alpha, timer, speed, prev_dir, tick, quick (a, b) as
    s8, records (8 dicts), glyphs (n -> char for n = 1, 2, 3), mask_entry (frames,
    mask, third), font. Returns (events, state) where events is the ordered list of
    observable calls and state the stored globals."""
    ev = []
    slot, page, menu = st['slot'], st['page'], st['menu']
    s = dict(alpha=st['alpha'], timer=st['timer'], speed=st['speed'], held=st.get('held', 0),
             dir=st['prev_dir'], latch=0, mask_entry=st['mask_entry'])
    if not st['local'] or F.le(st['hp'], F.ZERO):
        return ev, s
    cx, cy = H.selector_centre(slot, st['network'], menu)
    dx = dy = 0
    if pad_readable(st['gates'], st['local_menu_open']):
        dx, dy, anybit = pad_axes(st['held_bits'])
        if anybit:
            mask = st['masks']['a'] | st['masks']['b'] | st['masks']['use']
            frames, _m, _t = s['mask_entry']
            s['mask_entry'] = (max(frames, MASK_FRAMES), mask, 0)
    active = bool(dx or dy or menu)
    s['held'] = 1 if active else 0
    s['alpha'], s['timer'], s['speed'] = H.selector_fade_step(s['alpha'], s['timer'], s['speed'], active)
    alpha = s['alpha']
    if alpha > 0x40 and slot >= 2 and st['players'] >= 4:
        s['latch'] = 1
    if alpha <= 0:
        s['held'] = 0
        return ev, s
    d = H.selector_direction(dx, dy)
    if d != s['dir']:
        ev.append(('sound', 'fx.lmp', 'menu_spell_high.anm'))
    s['dir'] = d
    A = (alpha & 0xff) << 24
    px = 320 * page
    if d != -1 and not menu:
        ev.append(('S', ('res', 'hud.lmp', 'spellbookarrow%d.tex' % d), cx + px - 26, cy - 24, 7, A | GREY))
    ev.append(('S', ('ref', RES_BACKGROUND), cx + px - 68, cy - 65, 6, A | GREY))
    r2 = H.selector_radii(alpha)[1]
    for k, x, y in H.selector_ring(cx, cy, alpha, page):
        icon = record_icon(st['records'][k])
        if k == d:
            corona, tint = H.selector_highlight(st['tick'], alpha)
            ev.append(('S', ('res', 'hud.lmp', 'smallspelliconcorona.tex'), x - 6, y - 6, 7, corona))
            ev.append(('S', ('icon', icon), x, y, 6, tint))
        else:
            ev.append(('S', ('icon', icon), x, y, 6, A | GREY))
        if menu:
            continue
        a = -0x4000 + H.SELECTOR_STEP * k
        lx = cx + F.to_int(F.mul(F.from_int(r2), F.cos16(a))) + px + 6
        ly = cy + F.to_int(F.mul(F.from_int(r2), F.sin16(a))) + 3
        ev.append(('TB', st['font'], 7, A | LABEL_COLOUR, -1))
        for j in range(2):
            if st['quick'][j] == k:
                g = st['glyphs'][j + 1]      # sprintf '%c' of 0 gives an empty string
                ev.append(('TA', lx, ly, chr(g) if g else '', TEXT_WIDTH_LABEL))
        ev.append(('TE',))
    if d != -1:
        p = st['pressed_bits']
        if not menu:
            if p & st['masks']['a']:
                ev.append(('msg', MSG_QUICKSLOT, (slot, 0, d)))
            elif p & st['masks']['b']:
                ev.append(('msg', MSG_QUICKSLOT, (slot, 1, d)))
            elif p & st['masks']['use']:
                ev.append(('msg', MSG_QUICKCAST, (slot, d)))
        elif p & st['masks']['accept']:
            ev.append(('msg', MSG_ASSIGN, (slot, d, st['kind'], st['value'])))
        name_alpha = int(alpha / 2)
        ev.append(('TB', st['font'], 7, ((name_alpha & 0xff) << 24) | GREY, -1))
        ev.append(('TW', cx + px + 16, cy + 0x5c, record_name_key(st['records'][d]), TEXT_WIDTH_NAME))
        ev.append(('TE',))
        if not menu:
            g = st['glyphs']
            ev.append(('fmt', 'AssignCast', g[1], g[2], g[3]))
            ev.append(('prompt', 0x80, slot, 0))
    if menu:
        icon = ('skill', st['value']) if st['kind'] == 1 else ('table', MENU_ITEM_ICON)
        ev.append(('S', ('icon_or_none', icon), px + 0x8d, 0xfa, 6, A | GREY))
        if d != -1:
            ev.append(('S', ('res', 'hud.lmp', 'spellbookarrow%d.tex' % d), cx + px - 26, cy - 24, 6, A | GREY))
        ev.append(('S', ('res', 'inventry.lmp', 'spellbookparch.tex'), px + 0x39, 0xa5, 6, A | GREY))
    return ev, s
