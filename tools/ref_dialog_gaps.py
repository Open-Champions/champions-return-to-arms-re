#!/usr/bin/env python3
"""ref_dialog_gaps.py - the parts of the NPC dialog that docs/dialog.md left open (SLUS-20973 v2.00).

Contract: docs/spec/dialog-gaps.md.  Synthetic tests: tools/test_ref_dialog_gaps.py.
Comparison with the original functions in tools/ee_emu.py: tools/difftest_dialog_gaps.py.
Disc counts: tools/dialog_gaps_census.py.

Covers:

  Camera_setupDialogView 0x203bb8 ......... parse_dialog_offset(), setup_dialog_view()
  Camera_lookAt 0x204250 .................. look_at()
  Camera_apply 0x2035c8 (forward = 0) ..... camera_apply()
  game_isFrozen 0x1ebdf8 .................. game_is_frozen()
  player_pollRecallButton 0x1bce88 ........ recall_poll()
  Camera_update 0x203400 (control word) ... camera_update_control()
  the other 24 dialog_isOpen sites ........ SITES, site_outcome()
  dialog_loadBox 0x22f910 ................. load_box()
  game_initCamera 0x1e6b68 (glyph bytes) .. init_camera_buttons()
  world_objectFactory 0x159c94, property fallback (the TestLocation records)
                                            props_get_int(), props_get_str(), has_any_light(),
                                            factory_fallback()

Floats are raw single-precision patterns and use tools/ref_core.py (R5900 rules).  Inputs the
original reads from other subsystems are arguments.  Where the original reads memory nobody
initialised (a stack slot, address 0), the reference takes that value as an explicit
argument or raises ValueError; it never makes one up.
"""
import ref_core as C

M32 = 0xFFFFFFFF

# ---- addresses (all Observed in the functions named) -----------------------------------
G_CAMERA_POS = 0x44F038          # Vec3, this machine's camera position (camera_setView)
G_CAMERA_MATRIX = 0x44F110       # mat34; forward vector 0x44f118 / 0x44f124 / 0x44f130
G_ALIVE_COUNT, G_ALIVE = 0x4F8420, 0x4F8440
G_PLAYER_OBJ = 0x4DCEC8          # + slot * 0x4c30
G_CAMERA_SHAKE = 0x4F8488        # float; Camera_apply 0x2037fc
G_COSMETIC_SEED = 0x404460
G_BOX_TEX = 0x4FE538             # dialog_loadBox's only store, dialog_drawTask's only load
G_LEVEL_NAME = 0x44FE18
G_PVP_MODE_B = 0x4F7120
G_GLYPH_CONFIRM = 0x41B978       # byte the dialog cursor draws with "%c"
G_BUTTON_LAYOUT = 0x41B69C       # s8 read by game_initCamera and config_setDefaults
G_IDLE_VOICE = 0x506054          # mainloop_runSession's idle-voice countdown

S_DIALOG_OFFSET = 0x53E660       # "dialogOffset"
S_OFFSET_FORMAT = 0x53E670       # "%d,%d,%d,%d"
S_INTRO = 0x540D08               # "intro"
S_DLGBOX = 0x540D10              # "dlgbox.lmp"
S_BOX_TEX = 0x540D20             # "box.tex"

# ---- constants of Camera_setupDialogView / Camera_lookAt -------------------------------
NEAR = 0x42A00000                # 80.0  players nearer than this choose the side (0x203cb8)
SIDE_DOT = 0x3E4CCCCC            # 0.2   (0x203ce0); -0.2 = 0xbe4ccccc (0x203cd0)
SIDE_DOT_NEG = 0xBE4CCCCC
SIDE_ANGLE = 6000                # 0x1770, angle = idx * -6000 + 6000 (0x203eec-0x203ef8)
FACING_X_ADD, FACING_Y_ADD = 0x4000, 0x41C2   # cos16(facing + 0x4000), sin16(facing + 0x41c2)
DIST_ADD, HEIGHT_ADD, PITCH_ADD = 0x50, 0x46, 0xFA0   # 80, 70, 4000
FAR_START = 0x43B10000           # 354.0 (0x204118)
FAR_K = 0x3F599999               # 0.85  (0x204214)
LOOK_K_SCALE = 0x3F400000        # 0.75  (0x2042c8)
APPLY_PITCH_ADD = 0x3FD3         # Camera_apply: rotate X by pitch + 0x3fd3 (0x2037d4)
SHAKE_SCALE = 0x37800000         # 2^-16 (0x20386c)
LCG_MUL, LCG_ADD = 0x19660D, 0x3C6EF35F

# ---- dialog_runTask's use of the camera (0x22ff74-0x23004c) ------------------------------
SWOOP_STEPS = 45                 # Camera_lookAt(cam, +45 / -45)
FAR_CLIP_OPEN = 0x44340000       # 720.0  while forward z > -0.491
FAR_CLIP_CLOSE = 0x44E10000      # 1800.0 while forward z < -0.645
FWD_Z_OPEN = 0xBEFB645A          # -0.491
FWD_Z_CLOSE = 0xBF251E85         # -0.645


# =======================================================================================
# Camera_setupDialogView 0x203bb8
# =======================================================================================

def _atoi_digits(text, i):
    """The %d conversion of newlib's scanner on text[i:]: skip white space, an optional sign,
    at least one digit.  -> (value, new index) or None.  Values outside 32 bits refuse."""
    n = len(text)
    while i < n and text[i] in ' \t\n\r\v\f':
        i += 1
    start = i
    if i < n and text[i] in '+-':
        i += 1
    d0 = i
    while i < n and text[i].isdigit():
        i += 1
    if i == d0:
        return None
    value = int(text[start:i])
    if not -0x80000000 <= value <= 0x7FFFFFFF:
        raise ValueError('dialogOffset field out of 32-bit range: not modelled')
    return value, i


def parse_dialog_offset(text, stale=(None, None, None, None)):
    """libc_sscanf(text, "%d,%d,%d,%d", &dist(sp+0x60), &height(+0x64), &lateral(+0x6c),
    &pitch(+0x68)) as Camera_setupDialogView calls it (0x203c34).

    text None = no dialogOffset property: dist, height and pitch are stored 0 (0x203c48-
    0x203c50) and LATERAL IS NOT STORED: it is whatever the stack slot held (stale[2]).
    With a property, fields the scan does not reach keep the stale stack values as well.
    Returns ((dist, height, lateral, pitch), fields converted).  A stale value that is None
    where the original would use it makes setup_dialog_view raise."""
    dist, height, lateral, pitch = stale
    if text is None:
        return (0, 0, lateral, 0), 0
    out = [dist, height, lateral, pitch]
    i, got = 0, 0
    for k in range(4):
        if k:
            if i < len(text) and text[i] == ',':
                i += 1
            else:
                break
        r = _atoi_digits(text, i)
        if r is None:
            break
        out[k], i = r
        got += 1
    return tuple(out), got


def side_index(flags_front, flags_mid, flags_back, behind_camera):
    """The choice at 0x203e08-0x203ee4 from the three flags (A: a near player with dot >
    0.2, B: |dot| <= 0.2, C: dot < -0.2) -> index 0, 1 or 2 (angle +6000, 0, -6000).
    behind_camera() is vec3_dotDelta(npc, forward, g_cameraPos) < 0, asked only for
    (A, B, C) = (0, 1, 0)."""
    a, b, c = bool(flags_front), bool(flags_mid), bool(flags_back)
    if (a, b, c) == (0, 0, 0):
        return 1
    if (a, b, c) == (0, 1, 0):
        return 2 if behind_camera() else 0
    if not a and c:
        return 0                                # (0,0,1) and (0,1,1)
    if a and not c:
        return 2                                # (1,0,0) and (1,1,0)
    # (1,0,1), (1,1,1): leading non-zero flags counted, 3 becomes 1
    lead = 1 + (1 if b else 0) + (1 if (b and c) else 0)
    return 1 if lead == 3 else lead


class View:
    """The camera words Camera_setupDialogView writes and Camera_lookAt reads.

    start (+0x00..+0x08) and target (+0x0c..+0x14) positions, yaw +0x68 / pitch +0x6a
    (s16, current), start yaw +0x76 / target yaw +0x78 / target pitch +0x7a / start pitch
    +0x7c (s16), progress +0xa8 and turn factor +0xac (floats)."""
    __slots__ = ('start', 'target', 'yaw', 'pitch', 'start_yaw', 'target_yaw', 'target_pitch',
                 'start_pitch', 'progress', 'k')

    def __init__(self, yaw=0, pitch=0):
        self.start = [0, 0, 0]
        self.target = [0, 0, 0]
        self.yaw, self.pitch = C.s16(yaw), C.s16(pitch)
        self.start_yaw = self.target_yaw = self.target_pitch = self.start_pitch = 0
        self.progress = self.k = 0


def setup_dialog_view(view, npc_pos, npc_facing, side, players, camera_pos, offset_text,
                      stale=(None, None, None, None)):
    """Camera_setupDialogView(cam, npc, side) 0x203bb8.

    npc_pos: raw floats at npc+0x10..+0x18; npc_facing: s16 at npc+0x38; side: the third
    argument (message 0 byte b); players: positions of the objects of g_alivePlayers[0..
    count) in order; camera_pos: g_cameraPos; offset_text: the dialogOffset value or None.
    Writes the View; returns a dict with the parsed fields, the flags and the angle."""
    fields, got = parse_dialog_offset(offset_text, stale)
    dist, height, lateral, pitch_off = fields
    if None in (dist, height, lateral, pitch_off):
        raise ValueError('Camera_setupDialogView reads an uninitialised stack slot here '
                         '(no dialogOffset, or fewer than four fields): value not modelled')
    nx, ny, nz = npc_pos
    flags = (0, 0, 0)
    if side == 0:
        off = 0
    else:
        fx = C.cos16(npc_facing + FACING_X_ADD)
        fy = C.sin16(npc_facing + FACING_Y_ADD)
        fz = C.ZERO
        a = b = c = 0
        for px, py, pz in players:
            dx, dy, dz = C.sub(px, nx), C.sub(py, ny), C.sub(pz, nz)
            d = C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
            if not C.lt(d, NEAR):
                continue
            r = C.rsqrt(C.ONE, C.add(C.mul(dx, dx), C.mul(dy, dy)))
            ux, uy, uz = C.mul(dx, r), C.mul(dy, r), C.mul(C.ZERO, r)
            dot = C.add(C.add(C.mul(ux, fx), C.mul(uy, fy)), C.mul(uz, fz))
            if C.lt(dot, SIDE_DOT_NEG):
                c = 1
            elif C.lt(SIDE_DOT, dot):
                a = 1
            else:
                b = 1
        flags = (a, b, c)

        def behind():
            return C.lt(C.vec3_dot_delta((nx, ny, nz), (fx, fy, fz), camera_pos), C.ZERO)
        idx = side_index(a, b, c, behind)
        off = (idx * -SIDE_ANGLE + SIDE_ANGLE) & M32
        off = off - (1 << 32) if off & 0x80000000 else off
    cs = C.cos16(npc_facing + off)
    sn = C.sin16(npc_facing + off)
    r = C.rsqrt(C.ONE, C.add(C.mul(cs, cs), C.mul(sn, sn)))
    s1, c1 = C.mul(sn, r), C.mul(cs, r)
    # side vector = up (0, 0, 1) x direction
    up = (C.ZERO, C.ZERO, C.ONE)
    side_v = (C.neg(C.mul(up[2], s1)), C.mul(up[2], c1), C.sub(C.mul(up[0], s1), C.mul(up[1], c1)))
    lat = C.from_int(lateral)
    r2 = C.rsqrt(C.ONE, C.add(C.add(C.mul(c1, c1), C.mul(s1, s1)), C.mul(C.ZERO, C.ZERO)))
    cx, cy = C.mul(c1, r2), C.mul(s1, r2)
    dist_f = C.from_int(dist + DIST_ADD)
    height_f = C.from_int(height + HEIGHT_ADD)
    view.target = [C.add(C.add(nx, C.mul(cx, dist_f)), C.mul(side_v[0], lat)),
                   C.add(C.add(ny, C.mul(cy, dist_f)), C.mul(side_v[1], lat)),
                   C.add(C.add(nz, height_f), C.mul(side_v[2], lat))]
    view.target_pitch = C.s16((pitch_off & 0xFFFF) + PITCH_ADD)
    view.target_yaw = C.s16(-((npc_facing & 0xFFFF) + off + 0x4000))
    view.start = list(camera_pos)
    view.start_pitch = view.pitch
    view.start_yaw = view.yaw
    a0, b0 = C.cos16(view.yaw), C.sin16(view.start_yaw)
    a2, b2 = C.cos16(view.target_yaw), C.sin16(view.target_yaw)
    r = C.rsqrt(C.ONE, C.add(C.mul(a0, a0), C.mul(b0, b0)))
    a0, b0, z0 = C.mul(a0, r), C.mul(b0, r), C.mul(C.ZERO, r)
    r = C.rsqrt(C.ONE, C.add(C.add(C.mul(a2, a2), C.mul(b2, b2)), C.mul(C.ZERO, C.ZERO)))
    a2, b2, z2 = C.mul(a2, r), C.mul(b2, r), C.mul(C.ZERO, r)
    dot = C.add(C.add(C.mul(a0, a2), C.mul(b0, b2)), C.mul(z0, z2))
    view.k = C.sub(C.ONE, C.mul(C.add(dot, C.ONE), C.HALF))
    ddx = C.sub(view.start[0], view.target[0])
    ddy = C.sub(view.start[1], view.target[1])
    ddz = C.sub(view.start[2], view.target[2])
    if C.lt(FAR_START, C.sqrt(C.add(C.add(C.mul(ddx, ddx), C.mul(ddy, ddy)), C.mul(ddz, ddz)))):
        view.k = FAR_K
    view.progress = C.ZERO
    return {'fields': fields, 'converted': got, 'flags': flags, 'angle': off}


# =======================================================================================
# Camera_lookAt 0x204250
# =======================================================================================

def look_at(view, steps):
    """Camera_lookAt(cam, steps, out) 0x204250 -> (result, h, apply) where apply is the
    (x, y, z) passed to Camera_apply(x, y, z, cam, 0) or None, and h the smoothstep stored
    through out.  result 1 = arrived (nothing written), 0 = moved.

    steps > 0 moves the progress up by (1 - 0.75 k) / steps and arrives once it is exactly
    1.0 on entry; steps < 0 moves it down and arrives once it is exactly 0.0.  Steps 0
    divides by zero and is refused."""
    p = view.progress
    if steps > 0 and C.eq(p, C.ONE):
        return 1, None, None
    if steps < 0 and C.eq(p, C.ZERO):
        return 1, None, None
    if steps == 0:
        raise ValueError('Camera_lookAt with 0 steps divides by zero')
    inv = C.div(C.ONE, C.from_int(steps))
    p = C.add(p, C.sub(inv, C.mul(C.mul(inv, view.k), LOOK_K_SCALE)))
    if C.lt(C.ONE, p):
        p = C.ONE
    if C.lt(p, C.ZERO):
        p = C.ZERO
    view.progress = p
    h = C.hermite(p, C.ZERO, C.ONE, C.ZERO, C.ZERO)
    view.pitch = C.angle_approach(C.mul(C.mul(h, h), h), C.MINUS_ONE, C.MINUS_ONE,
                                  view.start_pitch, view.target_pitch)
    view.yaw = C.angle_approach(h, C.MINUS_ONE, C.MINUS_ONE, view.start_yaw, view.target_yaw)
    pos = tuple(C.add(view.start[i], C.mul(C.sub(view.target[i], view.start[i]), h))
                for i in range(3))
    return 0, h, pos


def run_task_camera(view, direction, swoop_done, shop_open, forward_z, apply_cb=None):
    """dialog_runTask's camera step (0x22ff74-0x2300bc) on top of look_at -> (actions, h):
    actions lists ('far_clip', value), ('apply', pos), ('arrived',) and ('send', 3) in
    order.  direction 1 opens, -1 closes.  forward_z is the float at 0x44f130, read once."""
    acts = []
    h = None
    if direction == 1:
        while True:
            res, h, pos = look_at(view, SWOOP_STEPS)
            if pos is not None:
                acts.append(('apply', pos))
                if apply_cb:
                    apply_cb(pos)
            if C.lt(FWD_Z_OPEN, forward_z):
                acts.append(('far_clip', FAR_CLIP_OPEN))
            if not swoop_done or res != 0:
                break
        if res == 1:
            acts.append(('arrived',))
        return acts, h
    if shop_open:
        return acts, h
    res, h, pos = look_at(view, -SWOOP_STEPS)
    if pos is not None:
        acts.append(('apply', pos))
        if apply_cb:
            apply_cb(pos)
    if C.lt(forward_z, FWD_Z_CLOSE):
        acts.append(('far_clip', FAR_CLIP_CLOSE))
    if res == 1:
        acts.append(('arrived',))
        acts.append(('send', 3))
    return acts, h


# =======================================================================================
# Camera_apply 0x2035c8 with no forward vector, and its shake
# =======================================================================================

def lcg(seed):
    return (seed * LCG_MUL + LCG_ADD) & M32


def camera_apply(pos, yaw, pitch, shake, seed, frozen, dialog_open):
    """Camera_apply(x, y, z, cam, 0) -> (pos, matrix, shake, seed, draws).

    matrix = identity, rotate X by s16(u16(pitch) + 0x3fd3), rotate Z by yaw.  When
    g_cameraShake > 0 and (not game_isFrozen() or dialog_isOpen()): three draws from the
    cosmetic seed jitter the position by (2u-1) s, (2v-1) s, (w-0.5) s and the shake falls
    by 0.5.  frozen and dialog_open are the two answers (dialog_open is only asked when
    frozen).  The result goes to camera_setView(pos, matrix)."""
    m = C.mat34_set_identity()
    m = C.mat34_rotate_axis(m, 0, C.s16((pitch & 0xFFFF) + APPLY_PITCH_ADD))
    m = C.mat34_rotate_axis(m, 2, C.s16(yaw))
    x, y, z = pos
    draws = 0
    if C.lt(C.ZERO, shake) and (not frozen or dialog_open):
        s1 = lcg(seed)
        s2 = lcg(s1)
        s3 = lcg(s2)
        seed, draws = s3, 3
        u = C.sub(C.mul(C.from_int(s1 >> 16), SHAKE_SCALE), C.HALF)
        v = C.sub(C.mul(C.from_int(s2 >> 16), SHAKE_SCALE), C.HALF)
        w = C.sub(C.mul(C.from_int(s3 >> 16), SHAKE_SCALE), C.HALF)
        x = C.add(x, C.mul(C.add(u, u), shake))
        y = C.add(y, C.mul(C.add(v, v), shake))
        z = C.add(z, C.mul(w, shake))
        shake = C.sub(shake, C.HALF)
    return (x, y, z), m, shake, seed, draws


# =======================================================================================
# game_isFrozen 0x1ebdf8
# =======================================================================================

class Frozen:
    """Inputs of game_isFrozen; each is the word or byte at the address named."""
    __slots__ = ('network', 'paused', 'cutscene', 'warmup', 'player_select', 'sim_frame',
                 'controller_out', 'dialog')

    def __init__(self, **kw):
        self.network = 0        # 0x402791
        self.paused = 0         # 0x41b4f4
        self.cutscene = 0       # 0x44fcd0 (byte)
        self.warmup = 0         # 0x506048
        self.player_select = 0  # task_isRunning("playerSelection")
        self.sim_frame = 0      # 0x44fdcc
        self.controller_out = 0  # 0x4f6708 (byte), set by hud_drawControllerOut
        self.dialog = 0         # dialog_isOpen()
        for k, v in kw.items():
            setattr(self, k, v)


def game_is_frozen(s, log=None):
    """game_isFrozen 0x1ebdf8 -> value.  log collects ('task',) and ('dialog',) for the
    two calls it makes, in order."""
    if s.network:
        return s.paused
    if s.cutscene:
        return s.warmup
    if log is not None:
        log.append(('task',))
    if s.player_select and s.sim_frame < 60:
        return 0
    if s.paused or s.warmup:
        return 1
    if not s.controller_out:
        return 0
    if log is not None:
        log.append(('dialog',))
    if s.dialog:
        return 0
    return 1


# =======================================================================================
# player_pollRecallButton 0x1bce88
# =======================================================================================

RECALL_CHECKS = ('lockout', 'frozen', 'dialog', 'obj4b4', 'recall', 'b4f66c8', 'camflag',
                 'jumpgate', 'pausemenu', 'obj540', 'flag400000', 'use', 'b100')


def recall_poll(players):
    """player_pollRecallButton -> slots sent to hudmsg_sendRecall, in order.  players is a
    list (in g_localAlivePlayers order) of dicts with the slot and every RECALL_CHECKS key:
    the first eleven must all be false (in that order of evaluation), 'use' (raw pad word
    0x4028d8 & g_btnUse[slot]) and 'b100' (0x4028dc & 0x100) true."""
    out = []
    for p in players:
        if any(p[k] for k in RECALL_CHECKS[:11]):
            continue
        if p['use'] and p['b100']:
            out.append(p['slot'])
    return out


# =======================================================================================
# Camera_update 0x203400: the "user control allowed" word +0x60
# =======================================================================================

def camera_update_control(frozen, world, menu_open, warmup, b4f66c8, dialog, lockout, flag400000):
    """+0x60 as Camera_update sets it (0x203418-0x2034a0): 1 only when not frozen, a world
    is loaded (0x44fdc8), no menu flag (0x41b4f8), no warm-up (0x506048), byte 0x4f66c8
    clear, no dialog open, no lockout (0x41b4fc) and game_localPlayerFlag400000() false."""
    if frozen or not world:
        return 0
    if menu_open or warmup or b4f66c8 or dialog or lockout:
        return 0
    return 0 if flag400000 else 1


# =======================================================================================
# The 24 dialog_isOpen sites that docs/dialog.md 6.1 had not followed
# =======================================================================================

# kind: 'sim' changes or gates shared game state or a game message; 'input' gates this
# machine's pad reading; 'draw' only drawing; 'seed' gates a cosmetic-seed draw.
SITES = {
    'prop_draw':        (0x1548D0, 0x1548BC, 'draw', 'Prop_draw returns without drawing the prop'),
    'phprop_draw':      (0x156DCC, 0x156DB4, 'draw', 'PhProp_draw returns without drawing'),
    'pause_exit':       (0x18CD08, 0x18CC08, 'input', 'pause menu: menu_exitmission +4 = 5'),
    'pause_kick':       (0x18CEB4, 0x18CC08, 'input', 'pause menu: menu_kickplayers +4 = 5 (else 0)'),
    'pause_recall':     (0x18D400, 0x18CC08, 'input', 'pause menu: menu_recall +4 = 5'),
    'pause_change':     (0x18D498, 0x18CC08, 'input', 'pause menu: menu_changeplayers +4 = 5'),
    'warp_menu':        (0x18E0E4, 0x18E00C, 'sim', 'warpMenu (offline): the start button cannot open the pause menu'),
    'player_interact':  (0x1A47BC, 0x1A46C0, 'draw', 'Player_draw skips Player_interact(P, 0, 1)'),
    'player_name':      (0x1A4ED8, 0x1A46C0, 'draw', 'Player_draw skips a remote player\'s name tag'),
    'player_marker':    (0x1BC07C, 0x1BBFF8, 'draw', 'Player_drawMarker draws no marker'),
    'recall_button':    (0x1BCF18, 0x1BCE88, 'sim', 'no hudmsg_sendRecall'),
    'controller_out':   (0x1DB5B0, 0x1DB3C8, 'sim', 'controller removed: no automatic pause menu offline'),
    'spell_select':     (0x1DD380, 0x1DD270, 'input', 'hud_spellSelect reads no pad (unless g_localMenuOpen)'),
    'hud_panel_input':  (0x1DE9E0, 0x1DE8C4, 'input', '0x1de8c4: no weapon swap / ability cycle / cursor input'),
    'hud_panel_button': (0x1DEDC4, 0x1DE8C4, 'input', '0x1de8c4: second pad test skipped'),
    'compass':          (0x1DF7BC, 0x1DF720, 'draw', 'hud_drawCompass draws nothing'),
    'net_cam_prompt':   (0x1E0260, 0x1E01B8, 'input', 'spectator prompt: not drawn, confirm does not cycle'),
    'is_frozen':        (0x1EBE8C, 0x1EBDF8, 'sim', 'game_isFrozen: controller-out does not freeze'),
    'status_fx':        (0x1F6B78, 0x1F6AC8, 'seed', 'fx_modelStatusEffects returns: no effects, no cosmetic draws'),
    'camera_control':   (0x203464, 0x203400, 'input', 'Camera_update: +0x60 (user control) = 0'),
    'camera_shake':     (0x203820, 0x2035C8, 'seed', 'Camera_apply: shake (3 cosmetic draws) even while frozen'),
    'save_screen':      (0x218F14, 0x218AFC, 'sim', 'memcard_saveScreen state 4: aborted'),
    'net_messages':     (0x31DF40, 0x31DEEC, 'draw', '0x31deec (net game): message list not drawn'),
    'idle_voice':       (0x322B8C, 0x322998, 'seed', 'mainloop_runSession: idle voice countdown held'),
}


def site_outcome(name, c):
    """The label each stretch of tools/difftest_dialog_gaps.py ends on, from the conditions
    tested at and around the site (c is a dict; missing keys are 0)."""
    g = lambda k: c.get(k, 0)   # noqa: E731
    d = g('dialog')
    if name in ('prop_draw', 'phprop_draw'):
        return 'skip' if d else 'draw'
    if name == 'pause_exit':
        if g('pvp_b'):
            return 'hidden'
        return 'disabled' if d else 'unchanged'
    if name == 'pause_kick':
        hidden = g('active') < 2
        return ('hidden+' if hidden else 'shown+') + ('disabled' if d else 'enabled')
    if name == 'pause_recall':
        if g('hp_le0') and g('network'):
            return 'disabled'
        if d or g('jumpgate'):
            return 'disabled'
        return 'enabled' if g('cam_mode') == 1 else 'disabled'
    if name == 'pause_change':
        if g('no_save') or g('network') or d:
            return 'disabled'
        return 'enabled' if g('cam_mode') == 1 else 'disabled'
    if name == 'warp_menu':
        if g('cam_mode') != 1 or d:
            return 'blocked'
        return 'continue'
    if name == 'player_interact':
        if g('paused') or g('lockout') or g('selector') or d:
            return 'skip'
        return 'go'
    if name == 'player_name':
        if not g('network') or not g('flag400000') or g('local') or d:
            return 'skip'
        return 'tag'
    if name == 'player_marker':
        return 'skip' if d else 'draw'
    if name == 'controller_out':
        if g('network') or g('pause_open') or g('frontend') or d:
            return 'skip'
        return 'go'
    if name == 'spell_select':
        if g('lockout') or d:
            return 'fallback'
        return 'next'
    if name in ('hud_panel_input', 'hud_panel_button'):
        if g('lockout') or d or g('cam_mode') != 1 or g('paused'):
            return 'skip'
        return 'go'
    if name == 'compass':
        if not g('compass_on') or d:
            return 'skip'
        return 'go'
    if name == 'net_cam_prompt':
        if d or g('cutscene') or g('pause_open'):
            return 'skip'
        return 'go'
    if name == 'status_fx':
        if g('flag10000000') or not g('model') or d:
            return 'skip'
        return 'go'
    if name == 'save_screen':
        if (g('network') and g('pending_level')) or g('cutscene') or d:
            return 'abort'
        return 'go'
    if name == 'net_messages':
        if not g('network'):
            return 'offline'
        if g('frontend') or d or not g('list_on'):
            return 'skip'
        return 'go'
    if name == 'idle_voice':
        if g('countdown') <= 0:
            return 'idle'
        if g('cutscene') or g('paused') or g('local_menu') or d:
            return 'held'
        if g('countdown') - 1 == 1:
            return 'voice' if g('players') > 0 else 'count'
        return 'count'
    raise KeyError(name)


def idle_voice(countdown, cutscene, paused, local_menu, dialog, players, seed):
    """mainloop_runSession's idle voice (0x322b50-0x322bfc) -> (countdown, seed, voice slot
    or None).  The countdown is stored decremented whenever the gates pass; at 1, one draw
    of the cosmetic seed picks (seed >> 16) % g_numPlayers for player_voice(slot, 2)."""
    if countdown <= 0 or cutscene or paused or local_menu or dialog:
        return countdown, seed, None
    countdown -= 1
    if countdown != 1 or players <= 0:
        return countdown, seed, None
    seed = lcg(seed)
    return countdown, seed, (seed >> 16) % players


# =======================================================================================
# dialog_loadBox 0x22f910 and what the draw is given
# =======================================================================================

def load_box(level, pvp_b, old, res_find_result):
    """dialog_loadBox (game_loadLevel 0x1e617c) -> the new word 0x4fe538.  strcmp(level,
    "intro") is case-sensitive; in intro or with g_pvpModeB set the word is not written.
    Otherwise it is res_find("dlgbox.lmp", "box.tex") - 0 when the lump or entry is absent."""
    if level == 'intro' or pvp_b:
        return old
    return res_find_result


BOX_WORD_INITIAL = 0             # the executable's data word at 0x4fe538


def box_sprite_reads(word):
    """ui_drawSpriteImpl's first reads of its texture argument: the s16 width at +0 and
    height at +2 (0x17b5d0 path).  With word 0 those are addresses 0 and 2, which the
    reference does not know (console kernel memory)."""
    if word == 0:
        raise ValueError('box sprite with no texture: reads s16 at addresses 0 and 2 (not modelled)')
    return (word, word + 2)


# =======================================================================================
# game_initCamera 0x1e6b68: confirm / cancel masks and button glyph bytes
# =======================================================================================

BUTTON_WORDS = {
    1: {0x41B968: 0x10, 0x41B96C: 0x7C, 0x41B970: 0x80, 0x41B974: 0x7D, 0x41B978: 0x7E,
        0x41B97C: 0x7B, 0x41BFBC: 0x40, 0x41BFB8: 0x20, 0x41B960: 0x40, 0x41B964: 0x7E},
    0: {0x41B968: 0x80, 0x41B96C: 0x7C, 0x41B978: 0x7B, 0x41B97C: 0x7E, 0x41BFBC: 0x20,
        0x41BFB8: 0x140, 0x41B960: 0x20, 0x41B964: 0x7B},
}


def init_camera_buttons(layout):
    """The words game_initCamera stores after Camera_init / skills_callVslot9All, by the s8
    at 0x41b69c: 1 and 0 each store a fixed set (BUTTON_WORDS); any other value stores
    none of them.  0x41b978 is the byte dialog_drawTask's cursor prints with "%c";
    0x41bfbc is g_btnConfirmMask, 0x41bfb8 g_btnCancelMask.  Both paths also store 0 to
    0x4f85b4 and 0x4f7134 first."""
    words = {0x4F85B4: 0, 0x4F7134: 0}
    words.update(BUTTON_WORDS.get(layout, {}))
    return words


# =======================================================================================
# world_objectFactory 0x159c94: the property fallback a class name with no test reaches
# =======================================================================================

def _lower(key):
    return ''.join(ch.lower() if 'A' <= ch <= 'Z' else ch for ch in key)


def _atoi(text):
    """newlib atoi: white space, sign, digits; 0 when none.  32-bit range only."""
    r = _atoi_digits(text, 0)
    return 0 if r is None else r[0]


def props_get_str(entries, key, nth=0):
    """props_getStr 0x14f850: the key is lower-cased (in place), then the nth entry that
    starts with it CASE-SENSITIVELY and has '=' right after -> the value text, or None."""
    k = _lower(key)
    for e in entries:
        if e.startswith(k) and len(e) > len(k) and e[len(k)] == '=':
            if nth == 0:
                return e[len(k) + 1:]
            nth -= 1
    return None


def props_get_int(entries, key, nth=0):
    """props_getInt 0x14f730 / propList_getInt 0x23a100: atoi of props_get_str, or 0."""
    v = props_get_str(entries, key, nth)
    return 0 if v is None else _atoi(v)


def has_any_light(entries):
    """propList_hasAnyLight 0x23a2b4: ParticleEmitter, DynamicLight, Halo, then for n in
    0..3 ParticleEmitter<n>, DynamicLight<n>, Halo<n> (propList_hasLightIndex 0x23a200);
    true at the first non-zero atoi."""
    for k in ('ParticleEmitter', 'DynamicLight', 'Halo'):
        if props_get_int(entries, k):
            return True
    for n in range(4):
        for k in ('ParticleEmitter%d', 'DynamicLight%d', 'Halo%d'):
            if props_get_int(entries, k % n):
                return True
    return False


# constructor address and pool_new size of each fallback (0x15d6a0-0x15d998, Observed)
FALLBACK_CTORS = {
    'CreatureContainer': (0x243624, 0x3D0),
    'AutoContainerLP': (0x24259C, 0x150), 'AutoContainer': (0x23D93C, 0x148),
    'AutoChestLP': (0x241468, 0x100), 'AutoChest': (0x23AD18, 0xF8),
    'AutoPropLP': (0x2416C4, 0x448), 'AutoProp/Door/Switch': (0x23C44C, 0x198),
    'AutoEmitter': (0x240DC8, 0x60), 'Critter': (0x2547FC, 0x448),
    'Generator': (0x2657A0, 0x3E8), 'SmokeGen': (0x31D180, 0x490),
}


def factory_fallback(entries):
    """The tail of world_objectFactory (0x15d690 on) for a class name no test matched ->
    the FALLBACK_CTORS key it picks, or None (the factory returns 0 and the record makes
    no object).  Order and keys Observed; each key is a props_getInt / props_getStr test."""
    if props_get_int(entries, 'CreatureContainer'):
        return 'CreatureContainer'
    if props_get_int(entries, 'AutoContainer'):
        return 'AutoContainerLP' if has_any_light(entries) else 'AutoContainer'
    if props_get_int(entries, 'AutoChest'):
        return 'AutoChestLP' if has_any_light(entries) else 'AutoChest'
    if props_get_int(entries, 'AutoProp'):
        return 'AutoPropLP' if has_any_light(entries) else 'AutoProp/Door/Switch'
    if props_get_int(entries, 'AutoEmitter'):
        return 'AutoEmitter'
    if props_get_int(entries, 'AutoDoor') or props_get_int(entries, 'AutoSwitch'):
        return 'AutoProp/Door/Switch'
    if props_get_int(entries, 'Critter'):
        return 'Critter'
    if props_get_str(entries, 'Generator') is not None:
        return 'Generator'
    if props_get_str(entries, 'SmokeGen') is not None:
        return 'SmokeGen'
    return None
