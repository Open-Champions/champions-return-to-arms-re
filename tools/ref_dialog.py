#!/usr/bin/env python3
"""ref_dialog.py - reference model of the NPC dialog machine (SLUS-20973 v2.00).

Contract: docs/dialog.md.  Synthetic tests: tools/test_ref_dialog.py.  Comparison with the
original functions in tools/ee_emu.py: tools/difftest_dialog.py.

Covers, function by function (names from symbols/audio-save.tsv and docs/dialog.md):

  .dbin parse / build ............................ docs/formats/anim-audio.md 4.2
  dialog_start 0x22fa50 .......................... start_message()
  dialog_onMsg 0x22ee2c case 0 (open) ............ Dialog.on_open()
  dialog_showNode 0x230c74 ....................... Dialog.show_node()
  dialog_queueLineAudio 0x22ec9c ................. Dialog.queue_line_audio()
  dialog_onMsg cases 1, 2, 3, 4 .................. on_confirm / on_move / on_end / on_leave
  dialog_runTask 0x22ff48 ........................ Dialog.tick()
  dialog_drawTask 0x230628 ....................... Dialog.draw()
  dialog_free 0x22f99c ........................... Dialog.free()
  Creature_interact 0x116bd8, Creature_trigger 0x11a5f0, the menu mutex 0x22fc04-0x22fc40
  script built-ins startDialog, dialogRunning, changeSwoop, startWithSwoopDone,
  newWorldPost, activateStore, activateMissionMenu, forceMutexRelease.

Floats are raw single-precision patterns and use tools/ref_core.py (R5900 rules).  The
reference never invents a value the original reads from hardware, the disc or another
subsystem: those come from a Host object the caller fills in (see class Host).  Where the
original would read through a null pointer or run off a buffer, the reference raises
ValueError instead of guessing.

Each call appends what the original does outside the dialog state to `self.log` as tuples;
tools/difftest_dialog.py compares that list with the calls the original made.
"""
import struct

import ref_core as C

NODE_SIZE = 0x448
CHOICE_SIZE = 0x54
MAX_CHOICES = 12
NODE_COND, NODE_TEXT, NODE_VOICE, NODE_SPEAKER = (0x01, 0x20), (0x21, 0x10), (0x31, 0x10), (0x41, 0x13)
NODE_NCHOICES, NODE_CHOICES = 0x54, 0x58
CH_TEXT, CH_COND, CH_ACTION, CH_NEXT = (0x00, 0x10), (0x10, 0x20), (0x30, 0x20), 0x50

MSG_OPEN, MSG_CONFIRM, MSG_MOVE, MSG_END, MSG_LEAVE = 0, 1, 2, 3, 4
MISSING_ENTRY = -1          # script_runByName 0x1ed694 when the entry does not exist

# Layout constants of the box (docs/dialog.md section 6).  Coordinates are the 640 x 448
# arguments of the text and sprite calls.
LINE = 19                   # 0x13
ROW0 = 0x127                # 0x231038(n) = 19 * n + 295
BODY_X = 0x38
BODY_W = 0x20C
BODY_TOP = 0x127
BODY_BOTTOM_TEXT = 0x186    # option 0x4fdcc8 set
BODY_BOTTOM_NOTEXT = 0x127  # option clear: no body line passes top < y < bottom
CHOICE_X = 0x56
CHOICE_TOP, CHOICE_BOTTOM = -100, 0x244
CHOICE_BASE = 0x1A1         # choice i of n: 0x1a1 - 19 * (n - i)
MORE_Y = 0x18E
SCROLL_PAGE = 0x4C
SCROLL_STEP = 5
HEIGHT_SLACK = 0x5F
BOX_X, BOX_Y, BOX_LAYER = 0x23, 0x118, 5
NAME_X, NAME_Y = 0xAE, 0x11D
PLAYER_X, PLAYER_Y, PLAYER_FIT = 0xB0, 0x100, 0xDA
TEXT_LAYER = 6
FORCED_BUDGET = 1000000
GLYPH_BUDGET = 100000
PLAYER_BUDGET = 10000
WIDE_NEWLINE, CARET, SPACE = 10, 0x5E, 0x20
TEXT_BUFFER_UNITS = 0x400   # 0x230fe4 clears 0x800 bytes at 0x4fdd38
VISIBLE_ROOM = 10           # 0x8e2d20 .. 0x8e2d47

BLEND_STEP = 0x3DF5C28E     # 0.12 at 0x2305c0
NAME_SHRINK = 0x3F199999    # 0.6 at 0x230b48
CLIP_FAR_OPEN = 0x44340000  # 720.0
CLIP_FAR_CLOSE = 0x44E10000 # 1800.0
OPEN_LOOK_LIMIT = 0xBEFB645A    # -0.491
CLOSE_LOOK_LIMIT = 0xBF251E85   # -0.645
DUCK = 0x3E999999           # music_setDuck(0.3)
SECONDS_PER_BYTE = 0x3898EADB   # 28 / (16 * 24000): PS2 ADPCM bytes -> seconds at 24 kHz
TICKS_PER_SECOND = 0x42700000   # 60.0
ONE_SIXTIETH = 0x3C888888
LIP_LEAD = 0x3D8F5C28           # 0.07 s subtracted from the track time
SYNC_TOLERANCE = 0x3CA3D70A     # 0.02 s
NUDGE = 0x3DCCCCCC              # 0.1 tick per call
TALK_BLEND = 0x3E999999     # anim_start blend of the talk track
IDLE_BLEND = 0x3ECCCCCC     # anim_start blend of the idle track under it
FADE_WAIT_FRAMES = 0x14
CAMERA_LOOK_FRAMES = 0x2D

UP_BITS = 0x101000          # cursor -1 (0x230364)
DOWN_BITS = 0x204000        # cursor +1 (0x230398)

COLOUR_BODY = 0x3A5262
COLOUR_PICK = 0x36775A
COLOUR_OTHER = 0x404040
COLOUR_GLYPH = 0x606060
COLOUR_NAME = 0x806464
COLOUR_BOX = 0x808080
COLOUR_MEASURE = 0x80808080
COLOUR_LAYOUT = 0x80323C3C


# ======================================================================================
# 1. Files
# ======================================================================================

def _s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def _cstr(raw):
    return raw.split(b'\0', 1)[0].decode('latin1')


def _put(buf, off, size, text):
    data = text.encode('latin1')
    if len(data) >= size:
        raise ValueError('%r does not fit %d bytes with its terminator' % (text, size))
    buf[off:off + len(data)] = data


class Choice:
    __slots__ = ('text', 'condition', 'action', 'next')

    def __init__(self, text='', condition='', action='', next=-1):
        self.text, self.condition, self.action, self.next = text, condition, action, next

    def __repr__(self):
        return 'Choice(%r, %r, %r, %d)' % (self.text, self.condition, self.action, self.next)


class Node:
    __slots__ = ('condition', 'text', 'voice', 'speaker', 'choices', 'raw_choices')

    def __init__(self, condition='', text='', voice='', speaker='', choices=(), raw_choices=None):
        self.condition, self.text, self.voice, self.speaker = condition, text, voice, speaker
        self.choices = list(choices)
        # +0x54 as stored; dialog_showNode loops over it.  None means len(choices).
        self.raw_choices = len(self.choices) if raw_choices is None else raw_choices

    def __repr__(self):
        return 'Node(%r, %r, choices=%r)' % (self.condition, self.text, self.choices)


def parse_dbin(data):
    """Nodes of a .dbin.  The count is the s8 at +0 of the file (dialog_onMsg 0x22ee2c reads
    only that); a file whose count does not match its size, a choice count outside 0..12 or
    a jump outside the file is refused."""
    if not data or len(data) % NODE_SIZE:
        raise ValueError('size %d is not a multiple of 0x448' % len(data))
    count = struct.unpack_from('<b', data, 0)[0]
    if count != len(data) // NODE_SIZE:
        raise ValueError('count byte %d, size says %d' % (count, len(data) // NODE_SIZE))
    nodes = []
    for k in range(count):
        r = data[k * NODE_SIZE:(k + 1) * NODE_SIZE]
        n, = struct.unpack_from('<i', r, NODE_NCHOICES)
        if not 0 <= n <= MAX_CHOICES:
            raise ValueError('node %d has %d choices' % (k, n))
        choices = []
        for i in range(n):
            c = r[NODE_CHOICES + i * CHOICE_SIZE:NODE_CHOICES + (i + 1) * CHOICE_SIZE]
            nxt, = struct.unpack_from('<i', c, CH_NEXT)
            if not -1 <= nxt < count:
                raise ValueError('node %d choice %d jumps to %d' % (k, i, nxt))
            choices.append(Choice(_cstr(c[0:0x10]), _cstr(c[0x10:0x30]), _cstr(c[0x30:0x50]), nxt))
        nodes.append(Node(_cstr(r[0x01:0x21]), _cstr(r[0x21:0x31]), _cstr(r[0x31:0x41]),
                          _cstr(r[0x41:0x54]), choices))
    return nodes


def build_dbin(nodes):
    """Bytes of a synthetic .dbin (count in byte 0 of node 0, the others 0)."""
    if not 0 < len(nodes) < 128:
        raise ValueError('1..127 nodes')
    out = bytearray(NODE_SIZE * len(nodes))
    for k, node in enumerate(nodes):
        b = k * NODE_SIZE
        if k == 0:
            out[0] = len(nodes)
        _put(out, b + 0x01, 0x20, node.condition)
        _put(out, b + 0x21, 0x10, node.text)
        _put(out, b + 0x31, 0x10, node.voice)
        _put(out, b + 0x41, 0x13, node.speaker)
        if len(node.choices) > MAX_CHOICES:
            raise ValueError('more than 12 choices')
        struct.pack_into('<i', out, b + NODE_NCHOICES, node.raw_choices)
        for i, ch in enumerate(node.choices):
            c = b + NODE_CHOICES + i * CHOICE_SIZE
            _put(out, c + 0x00, 0x10, ch.text)
            _put(out, c + 0x10, 0x20, ch.condition)
            _put(out, c + 0x30, 0x20, ch.action)
            struct.pack_into('<i', out, c + CH_NEXT, ch.next)
    return bytes(out)


def start_candidates(nodes):
    """Nodes dialog_onMsg case 0 can open at: node 0 (the default) and every node with a
    condition."""
    return [0] + [k for k, n in enumerate(nodes) if n.condition and k]


def reachable_nodes(nodes):
    """Nodes reachable from the start candidates through choice jumps (choice conditions
    taken as possibly true)."""
    seen, todo = set(), list(start_candidates(nodes))
    while todo:
        k = todo.pop()
        if k in seen or not 0 <= k < len(nodes):
            continue
        seen.add(k)
        todo.extend(ch.next for ch in nodes[k].choices if ch.next >= 0)
    return seen


def pick_start(nodes, run_script):
    """dialog_onMsg case 0 (loop at 0x22ef7c): the first node whose condition is not empty
    and returns non-zero; node 0 when none does.  A condition naming no entry returns -1
    from script_runByName and so counts as true.  Conditions are run in node order and
    the loop stops at the first acceptance."""
    for k, node in enumerate(nodes):
        if node.condition and run_script(node.condition) != 0:
            return k
    return 0


# ======================================================================================
# 2. The start message (dialog_start 0x22fa50)
# ======================================================================================

def start_message(name, player, a, b, cam_xyz, yaw, pitch):
    """Bytes of game message 0 as dialog_start builds them.  The buffer starts 4-aligned,
    so the name is padded with 0xff up to the next multiple of 4 counted from the start.
    a, b and player are stored as bytes; yaw and pitch as s16; the camera position as the
    three raw words of g_cameraPos 0x44f038."""
    data = name.encode('latin1')
    if b'\0' in data or len(data) > 127:
        raise ValueError('name must be 0..127 bytes without NUL')
    out = bytearray([MSG_OPEN, len(data)]) + data
    while len(out) & 3:
        out.append(0xFF)
    out += bytes([player & 0xFF, a & 0xFF, b & 0xFF, 0])
    out += struct.pack('<III', *[w & 0xFFFFFFFF for w in cam_xyz])
    out += struct.pack('<hh', C.s16(yaw), C.s16(pitch))
    return bytes(out)


def parse_start_message(msg):
    """What dialog_onMsg case 0 reads back.  The name length is an s8; a negative length
    copies nothing."""
    n = struct.unpack_from('<b', msg, 1)[0]
    name = msg[2:2 + max(n, 0)].decode('latin1')
    p = 2 + max(n, 0)
    while p & 3:
        p += 1
    player, a, b = struct.unpack_from('<bbb', msg, p)
    cam = struct.unpack_from('<III', msg, p + 4)
    yaw, pitch = struct.unpack_from('<hh', msg, p + 0x10)
    return dict(name=name, player=player, a=a, b=b, cam=cam, yaw=yaw, pitch=pitch)


# ======================================================================================
# 3. Host: everything the dialog reads from outside its own state
# ======================================================================================

class Object:
    """A level object as far as the dialog reads it."""

    def __init__(self, addr, x=0.0, y=0.0, z=0.0, facing=0, flags=0, npc=False, word24=0,
                 props=None, anim_count=1, anim_cur=0, display_name=1):
        self.addr = addr
        self.pos = [C.f32(x), C.f32(y), C.f32(z)]
        self.facing = facing & 0xFFFF
        self.flags = flags
        self.npc = npc
        self.word24 = word24             # the word *(obj+0x24) points at (non-NPC focus word)
        self.props = dict(props or {})    # key (lower case) -> text
        self.anim_count = anim_count      # s8 +0x118
        self.anim_cur = anim_cur          # +0x11c, the first track's animation
        self.display_name = display_name  # +0x368 (ShowName pointer), 0 = none
        self.tracks = [C.ZERO] * 8        # raw time of track i at +0x134 + 0x20 i
        self.flag20_track = -1            # anim_findTrackByFlag(+0x114, 0x20)
        self.track_store = None


class Host:
    """Inputs the original takes from other subsystems.  Every field is plain data so a
    test can set it and the difftest can plant the same thing in memory."""

    def __init__(self):
        self.network = False                 # g_networkMode 0x402791
        self.local = {0}                     # slots net_isLocalSlot accepts
        self.num_players = 1                 # g_numPlayers 0x4d8ae0
        self.player_obj = {0: None}          # slot -> Object (record +0x43d8)
        self.alive = [0]                     # g_alivePlayers 0x4f8440, count 0x4f8420
        self.raw_pad = {0: 0}                # word 0x4028dc + slot * 0x58
        self.confirm_mask = 0x40             # g_btnConfirmMask 0x41bfbc
        self.recall = 0                      # g_recallCountdown 0x41b51d
        self.mission_menu = False            # task "missionmenurun"
        self.pause_menu = False              # task "pauseMenu"
        self.shop_open = 0                   # g_shopOpen 0x41b50c
        self.objects = {}                    # name -> [Object] in registration order
        self.scripts = {}                    # entry -> return value (missing: -1)
        self.texts = {}                      # text key -> list of u16 (wide text)
        self.role_anims = {}                 # (obj addr, role) -> anim id (0 = none)
        self.anm_length = {}                 # "<voice>.anm" -> stream_levelEntryLength
        self.vag_length = {}                 # "<voice>.vag" -> stream_levelEntryLength
        self.anm_entry = {}                  # "<voice>.anm" -> (offset +0x40, next +0x90)
        self.layout_height = 0               # text_drawWrapped(56, 0, ...) in showNode
        self.ran = []                        # scripts run, in order

    def run_script(self, name):
        self.ran.append(name)
        return self.scripts.get(name, MISSING_ENTRY)

    def is_local(self, slot):
        return slot in self.local

    def text(self, key):
        if key not in self.texts:
            raise ValueError('text key %r not provided' % key)
        return list(self.texts[key])

    def role_anim(self, obj, role):
        return self.role_anims.get((obj.addr if obj else 0, role), 0)


# ======================================================================================
# 4. The machine
# ======================================================================================

class Dialog:
    """State of the dialog machine.  Attribute -> address in the original."""

    def __init__(self):
        self.nodes = None          # 0x8e2d5c file (list of Node); None until a dialog opened
        self.node = None           # 0x8e2d60 g_dialogData: index of the shown node, None = closed
        self.node_index = -1       # 0x8e2e88 (dialog_free sets -1)
        self.prompt_node = -1      # 0x8e2e8c
        self.prompt_shown = 0      # 0x8e2e90
        self.revealing = 0         # 0x8e2cb0 typewriter running
        self.reveal_done = 0       # 0x8e2cb4
        self.reveal = 0            # 0x8e2d4c characters revealed
        self.at_end = 0            # 0x8e2ca8 text fully scrolled
        self.more = 0              # 0x8e2cac waiting for a press to scroll
        self.cursor = 0            # 0x8e2cb8 index into visible
        self.cursor_target = 0     # 0x8e2cbc
        self.blend = C.ONE         # 0x8e2d54 cursor move blend (raw float)
        self.scroll = 0            # 0x8e2ccc
        self.scroll_target = 0     # 0x8e2cc8
        self.total = 0             # 0x8e2cd0 scroll limit
        self.span = 0              # 0x8e2d58 float(target - scroll), written only
        self.visible = []          # 0x8e2d20 / count 0x8e2d18
        self.choice_y = [0] * MAX_CHOICES   # 0x8e2ce8 (not cleared between nodes)
        self.text = []             # 0x4fdd38 u16 units, without the terminator
        self.text_len = 0          # 0x8e2d48
        self.cam_move = 0          # 0x8e2d50: 1 opening, -1 closing, 0 none
        self.closing = 0           # 0x8e2cd8
        self.end_sent = 0          # 0x8e2ce0
        self.drawn = 0             # 0x8e2cd4
        self.swoop = 0             # 0x4fdce4 (script changeSwoop, message byte a)
        self.side = 0              # 0x8e2cc4 (message byte b), written only
        self.remote = 0            # 0x8e2ca0 the active player is not on this machine
        self.store_pending = 0     # 0x4fdd30
        self.store_index = None    # 0x4f7150 (s16)
        self.next_world = ''       # 0x4fdcf0 (script newWorldPost)
        self.name = []             # 0x8e2d68 showName text
        self.name_len = 0          # 0x8e2cdc
        self.hold = 0              # 0x4fdcd4 voice queued held
        self.anm_ready = 1         # 0x4fdcd5 the asynchronous .anm read is complete
        self.buf_sel = 0           # 0x4fdcd6
        self.cur_buf = 0           # 0x4fdcd7
        self.talking = 0           # 0x4fdcd8
        self.nudge = 0             # 0x4fdcdc (raw float)
        self.buffers = [dict(ptr=0, has=0, size=0, vag=0) for _ in range(2)]  # 0x8e2e68 + 16 i
        self.queue_mark = 0        # 0x8e2ca4
        self.focus = None          # 0x4fdcc0 Object
        self.focus_word = 0        # 0x4fdcc4
        self.idle_anim = 0         # 0x4fdccc
        self.mutex = 0             # 0x4fe53c
        self.hud_suppressed = 0    # 0x4f66a8
        self.swoop_done = 0        # 0x4fdce8 (script startWithSwoopDone)
        self.active_player = 0     # 0x4d8ae4 g_scriptActivePlayer
        self.pending_world = None  # 0x41b6d0 (written on end when next_world is set)
        self.orient = None         # 0x41b720
        self.shown = 0             # 0x44e028, written by text_drawWrapped (host supplies)
        self.last_position = 0     # 0x4fdce0 last voice position seen by dialog_syncMouth
        self.log = []

    # ---- helpers ------------------------------------------------------------------------
    @property
    def is_open(self):
        """dialog_isOpen 0x22fbc0 / script dialogRunning."""
        return self.node is not None

    def _reset_focus_anim(self):
        f = self.focus
        if f is None:
            return
        if f.anim_count > 1:
            f.anim_count = 1
        if f.anim_cur != self.idle_anim:
            # Only the count is written here; anim_push (0x170838) then adds the idle
            # track to the emptied state.  Its effect on +0x118/+0x11c is not modelled.
            f.anim_count = 0
            self.log.append(('anim_push', f.addr, self.idle_anim, 1))

    def clear_text(self):
        """0x230fe4: zero 0x800 bytes at 0x4fdd38 and the length 0x8e2d48."""
        self.text, self.text_len = [], 0

    # ---- menu mutex 0x4fe53c ------------------------------------------------------------
    def mutex_try(self):
        """menuMutex_tryAcquire 0x22fc04: 0 and take it when free, else -1."""
        if self.mutex == 0:
            self.mutex = 1
            return 0
        return -1

    def mutex_release(self):
        self.mutex = 0

    # ---- dialog_start 0x22fa50 (script startDialog) -------------------------------------
    def start(self, host, name, a, b, cam_xyz, yaw, pitch):
        """Returns the message bytes when this machine sends one, else None."""
        self.log.append(('camera_update',))
        self.swoop_done = 0
        if not host.is_local(self.active_player) or self.is_open:
            return None
        msg = start_message(name, self.active_player, a, b, cam_xyz, yaw, pitch)
        self.log.append(('send', msg))
        return msg

    # ---- message 0 ----------------------------------------------------------------------
    def on_open(self, host, msg, nodes, level='level'):
        m = parse_start_message(msg)
        if host.recall or host.mission_menu:
            self.mutex_release()
            return False
        self.log.append(('close_local_menus', 0))
        self.log.append(('camera_push',))
        self.log.append(('camera_yaw', C.s16(m['yaw'])))
        self.log.append(('camera_pitch', C.s16(m['pitch'])))
        self.log.append(('camera_apply',) + tuple(m['cam']))
        self.log.append(('lump', level + '.lmp', m['name'] + '.dbin'))
        start = pick_start(nodes, host.run_script)
        obj = self._find_speaker(host, m['name'], m['player'])
        if obj.flags & 0x20:
            if self.node is None:          # dialog_setFocusObj stores only while closed
                self.focus = obj
                self.focus_word = obj.addr + 0x3C8 if obj.npc else obj.word24
        idle = host.role_anim(self.focus, 'dialogidle')
        if idle == 0:
            idle = host.role_anim(self.focus, 'idle')
        self.idle_anim = idle
        key = obj.props.get('showname')
        self.name = host.text(key) if key is not None else []
        self.log.append(('freeze_all',))
        self.clear_text()
        self.nodes = nodes
        self.name_len = len(self.name)
        self.hud_suppressed = 1
        self.revealing = 1
        self.next_world = ''
        self.drawn = 0
        self.closing = 0
        self.swoop = m['a']
        self.side = m['b']
        self.end_sent = 0
        self.store_pending = 0
        biggest = 0
        for node in nodes:
            length = C.s32(host.anm_length.get(node.voice + '.anm', 0))
            if biggest < length:
                biggest = length
        size = (biggest + 0x7FF) & ~0x7FF & 0xFFFFFFFF
        for i in range(2):
            self.log.append(('alloc', size))
            self.buffers[i]['ptr'] = 1 + i       # stands for the allocation
        self.show_node(host, start)
        self.remote = 0 if host.is_local(self.active_player) else 1
        if self.remote:
            self.log.append(('fade_wait', FADE_WAIT_FRAMES))
        if self.swoop:
            self.log.append(('dialog_view', self.side))
            self.cam_move = 1
        return True

    def _find_speaker(self, host, name, player):
        """The object the conversation is with (0x22efe4-0x22f15c)."""
        found = host.objects.get(name, [])
        pobj = host.player_obj.get(player) if 0 <= player < host.num_players else None
        if pobj is None:
            if not found:
                raise ValueError('no object named %r: the original reads address 0xc' % name)
            return found[0]
        if not found:
            raise ValueError('no object named %r: the original reads address 0xc' % name)
        best, best_d = None, C.MINUS_ONE
        for o in found[:100]:
            dx = C.sub(o.pos[0], pobj.pos[0])
            dy = C.sub(o.pos[1], pobj.pos[1])
            dz = C.sub(o.pos[2], pobj.pos[2])
            d = C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
            if C.eq(best_d, C.MINUS_ONE) or C.lt(d, best_d):
                best, best_d = o, d
        return best

    # ---- dialog_showNode 0x230c74 -------------------------------------------------------
    def show_node(self, host, index):
        if not 0 <= index < len(self.nodes):
            raise ValueError('node %d outside the file' % index)
        node = self.nodes[index]
        self.prompt_node = -1
        self.blend = C.ONE
        self.revealing, self.reveal_done, self.reveal = 1, 0, 0
        self.at_end = self.more = 0
        self.cursor = self.cursor_target = 0
        self.scroll = self.scroll_target = 0
        self.hold = 0
        self.node = index
        self.node_index = index
        self.log.append(('stream_stop', 1))
        self._reset_focus_anim()
        units = [SPACE, SPACE]
        for u in host.text(node.text):
            if u == 0:
                break
            units.append(WIDE_NEWLINE if u == CARET else u)
        if len(units) >= TEXT_BUFFER_UNITS:
            raise ValueError('text runs past the 0x800-byte buffer')
        self.text, self.text_len = units, len(units)
        self.queue_line_audio(host, node)
        self.visible = []
        for i in range(node.raw_choices):
            if i >= len(node.choices):
                raise ValueError('raw choice count beyond the parsed choices')
            ch = node.choices[i]
            ok = 1 if not ch.condition else host.run_script(ch.condition)
            if ok != 0:
                self.visible.append(i)
        if len(self.visible) > VISIBLE_ROOM:
            # The list at 0x8e2d20 holds 10 words; entries 10 and 11 land on the text
            # length 0x8e2d48 and the reveal count 0x8e2d4c (difftest 'open', overlap case).
            raise ValueError('%d visible choices overrun 0x8e2d20' % len(self.visible))
        self.log.append(('text_begin', 1, COLOUR_LAYOUT))
        self.log.append(('wrapped', BODY_X, 0, 'body', BODY_W, 0, 0, LINE))
        self.log.append(('text_end',))
        n = len(self.visible)
        for i in range(n):
            self.choice_y[i] = CHOICE_BASE - LINE * (n - i)
        self.total = max(host.layout_height + LINE * n - HEIGHT_SLACK, 0)

    # ---- dialog_queueLineAudio 0x22ec9c -------------------------------------------------
    def queue_line_audio(self, host, node):
        if not self.anm_ready:
            raise ValueError('the original spins on lump_pollAsync until the .anm read ends')
        vag, anm = node.voice + '.vag', node.voice + '.anm'
        self.log.append(('stream_play', 1, vag, 0x28))
        buf = self.buffers[self.buf_sel]
        buf['vag'] = host.vag_length.get(vag, 0)
        self.hold = 1
        entry = host.anm_entry.get(anm)
        if entry is None:
            self.anm_ready = 1
            buf['has'] = 0
        else:
            off, nxt = entry
            size = C.s32(nxt - off)
            self.log.append(('cd_read', size, off))
            buf['size'], buf['has'] = size, 1
            self.anm_ready = 0             # cd_readAsync: the host sets it when done
        self.talking = 0
        self.cur_buf = self.buf_sel
        self.buf_sel = 1 if self.buf_sel == 0 else 0

    # ---- message 1 ----------------------------------------------------------------------
    def on_confirm(self, host):
        if self.node is None:
            return
        if self.revealing != 0 and self.reveal_done == 0:
            self.revealing, self.reveal_done = 0, 1
            return
        if self.at_end == 0 or not C.eq(self.blend, C.ONE):
            if self.more and self.scroll == self.scroll_target:
                self.more = 0
                self.reveal_done = 1 if self.revealing == 0 else 0
                self.scroll_target = min(self.scroll + SCROLL_PAGE, self.total)
                self.span = C.from_int(self.scroll_target - self.scroll)
            return
        self.log.append(('stream_stop', 1))
        if self.visible:
            ch = self.nodes[self.node].choices[self.visible[self.cursor]]
            if ch.action:
                host.run_script(ch.action)
            if self.visible and ch.next != -1:
                self.clear_text()
                self.show_node(host, ch.next)
                return
        if self.closing == 0:
            self.log.append(('fade_restart', 0))
            self.closing = 1

    # ---- message 2 ----------------------------------------------------------------------
    def on_move(self, host, delta):
        if len(self.visible) > 1 and self.more == 0 and self.at_end != 0:
            new = self.cursor + delta
            if 0 <= new < len(self.visible):
                self.cursor_target = new
                if host.network:
                    self.blend = C.ONE
                    self.cursor = new
                else:
                    self.blend = C.ZERO

    # ---- message 3 ----------------------------------------------------------------------
    def on_end(self, host):
        if self.node is None:
            return
        if not self.anm_ready:
            raise ValueError('the original spins on lump_pollAsync until the .anm read ends')
        for b in self.buffers:
            if b['ptr']:
                self.log.append(('free',))
                b['ptr'] = 0
        self.hud_suppressed = 0
        self.mutex = 0
        self.node = None
        self.log.append(('camera_mode', 1))
        self.log.append(('stream_stop', 1))
        self.hold = 0
        if self.focus is not None:
            self._reset_focus_anim()
            self.focus = None
        self.log.append(('unfreeze_all',))
        self.log.append(('far_clip', CLIP_FAR_CLOSE))
        if self.next_world:
            self.pending_world = self.next_world
            self.orient = 0xFF
        self.log.append(('post_action',))
        if self.store_pending:
            if not host.network:
                self.log.append(('shop', self.active_player, 0, 1))
            else:
                self.log.append(('close_local_menus', 0))
                for slot in range(host.num_players):
                    if host.is_local(slot):
                        self.log.append(('shop', slot, 0, 1))
                        break
        if self.remote:
            self.log.append(('fade_wait', FADE_WAIT_FRAMES))

    # ---- message 4 ----------------------------------------------------------------------
    def on_leave(self, host=None):
        self.cam_move = -1

    def on_message(self, host, msg, nodes=None, level='level'):
        kind = msg[0]
        if kind == MSG_OPEN:
            return self.on_open(host, msg, nodes, level)
        if kind == MSG_CONFIRM:
            return self.on_confirm(host)
        if kind == MSG_MOVE:
            return self.on_move(host, struct.unpack_from('<b', msg, 1)[0])
        if kind == MSG_END:
            return self.on_end(host)
        if kind == MSG_LEAVE:
            return self.on_leave(host)
        return None

    # ---- dialog_runTask 0x22ff48 --------------------------------------------------------
    def tick(self, host, io):
        """One run of the task.  io (a TickIO) carries the per-call inputs: camera move
        results, the look value, audio queries, the fade value, the dialog option and the
        glyph count the measuring pass produces.  Returns the messages sent."""
        sent = []

        def send(msg):
            sent.append(bytes(msg))
            self.log.append(('send', bytes(msg)))

        self.prompt_shown = 0
        if self.cam_move != 0:
            look = io.look
            if self.cam_move == 1:
                while True:
                    arrived = io.camera_step(CAMERA_LOOK_FRAMES)
                    if C.lt(OPEN_LOOK_LIMIT, look):
                        self.log.append(('far_clip', CLIP_FAR_OPEN))
                    if not (self.swoop_done != 0 and arrived == 0):
                        break
            else:
                arrived = 0
                if host.shop_open == 0:
                    arrived = io.camera_step(-CAMERA_LOOK_FRAMES)
                    if C.lt(look, CLOSE_LOOK_LIMIT):
                        self.log.append(('far_clip', CLIP_FAR_CLOSE))
            if arrived != 1:
                return sent
            if self.cam_move != -1:
                self.cam_move = 0
                return sent
            send([MSG_END])
            self.cam_move = 0
            return sent
        if self.node is None:
            self.prompt_shown = 0
            return sent
        pad = 0
        self.log.append(('duck', DUCK))
        self.prompt_node = self.node_index
        if not host.pause_menu:
            if not host.network:
                ap = self.active_player
                pad = host.raw_pad.get(ap, 0)
                pobj = host.player_obj.get(ap)
                if pobj is None or pobj.flags & 8:
                    self.active_player = ap ^ 1
            else:
                for slot in host.alive:
                    if host.is_local(slot):
                        pad = host.raw_pad.get(slot, 0)
                        break
        # voice and mouth (0x2301c0-0x230288)
        sync = False
        if self.hold == 1 and io.held_ready():
            if self.anm_ready:
                self.hold = 0
                self.queue_mark = io.queue_count()
                self.log.append(('clear_hold', 1))
                sync = self._audio_ready_branch(io)
            else:
                sync = bool(self.talking)
        else:
            sync = self._audio_ready_branch(io)
        if sync:
            self.log.append(('sync_mouth',))
        # input and closing (0x230290-0x2303f8)
        if self.closing == 0 or not C.eq(io.fade, C.ONE):
            if io.text_option != 0 or (self.hold == 0 and io.stream_status() == 0):
                if C.eq(self.blend, C.ONE):
                    if pad & UP_BITS:
                        send([MSG_MOVE, 0xFF])
                    if pad & DOWN_BITS:
                        send([MSG_MOVE, 1])
                if pad & host.confirm_mask:
                    send([MSG_CONFIRM])
        elif self.end_sent == 0:
            self.end_sent = 1
            send([MSG_LEAVE if self.swoop else MSG_END])
        # scroll (0x2303fc-0x2304ac)
        if self.scroll == self.scroll_target and self.more == 0 and self.at_end == 0:
            if self.scroll == self.total:
                self.more, self.at_end = 0, 1
            elif io.text_option == 0:
                self.scroll_target = min(self.scroll + SCROLL_PAGE, self.total)
                self.span = C.from_int(self.scroll_target - self.scroll)
            else:
                self.more = 1
        else:
            self.scroll = min(self.scroll + SCROLL_STEP, self.scroll_target)
        # measuring pass (0x2304b0-0x23058c): text is laid out with a zero-width clip
        self.log.append(('text_begin', TEXT_LAYER, COLOUR_MEASURE))
        if self.revealing:
            self.log.append(('budget', self.reveal))
        self.log.append(('clip', 0, ROW0 + LINE + 6, 0, ROW0 + 6 * LINE))
        bottom = BODY_BOTTOM_NOTEXT if io.text_option == 0 else BODY_BOTTOM_TEXT
        self.log.append(('wrapped', BODY_X, ROW0 + LINE - self.scroll, 'body', BODY_W, BODY_TOP,
                         bottom, LINE))
        self.log.append(('text_end',))
        self.shown = io.shown
        if self.revealing and self.reveal_done == 0:
            if self.shown < self.reveal:
                self.reveal_done = 1
            else:
                self.reveal += 1
        self.blend = C.add(self.blend, BLEND_STEP)
        if C.lt(C.ONE, self.blend):
            self.blend = C.ONE
            if self.cursor_target != self.cursor:
                self.cursor = self.cursor_target
        return sent

    def _audio_ready_branch(self, io):
        """0x230210: start the talk animation once the voice has begun; True when the
        mouth is to be synchronised this tick."""
        if not self.anm_ready:
            return bool(self.talking)
        if self.talking:
            return True
        if self.hold == 0 and io.queue_count() != self.queue_mark and io.stream_position() > 0:
            self.log.append(('talk_anim',))
            self.nudge = 0
            self.talking = 1
        return bool(self.talking)

    # ---- dialog_startTalkAnim 0x22fc70 / dialog_syncMouth 0x22fdd8 ----------------------
    def talk_anim(self, host):
        """Start the speaker's mouth.  With a lip-sync .anm read for this line: relocate it
        and start it (flags 0x26), then chain the idle track.  Without one: the generic
        'talk' animation (flags 3) and, under it, the idle track whose time is set to minus
        the line's length in ticks, so it takes over when the line ends.
        Returns the (offset from the object, raw float) the original stores, or None."""
        f = self.focus
        if f is None:
            return None
        buf = self.buffers[self.cur_buf]
        if buf['has'] == 0:
            talk = host.role_anim(f, 'talk')
            if talk == 0:
                return None
            self.log.append(('anim_start', TALK_BLEND, f.addr, talk, 3))
            if self.idle_anim == 0:
                return None
            self.log.append(('anim_start', IDLE_BLEND, f.addr, self.idle_anim, 3))
            secs = C.mul(C.from_int(C.s32(buf['vag'])), SECONDS_PER_BYTE)
            value = C.neg(C.mul(secs, TICKS_PER_SECOND))
            off = 0x114 + _s8(f.anim_count) * 0x20
            f.track_store = (off, value)
            return off, value
        self.log.append(('anm_relocate',))
        self.log.append(('anim_start', TALK_BLEND, f.addr, 'line', 0x26))
        if self.idle_anim != 0:
            self.log.append(('anim_chain', f.addr, self.idle_anim, 3))
        return None

    def sync_mouth(self, host, position):
        """Nudge every track of the speaker by +-0.1 tick while the lip-sync track (flag
        0x20, index from anim_findTrackByFlag) and the voice stream position (bytes) differ
        by 0.02 s or more.  position is audio_streamPosition(1); it is asked only when the
        speaker has such a track."""
        f = self.focus
        if f is None or f.flag20_track < 0:
            return
        pos = position()
        if pos != self.last_position:
            anim = C.sub(C.mul(f.tracks[f.flag20_track], ONE_SIXTIETH), LIP_LEAD)
            audio = C.mul(C.from_int(C.s32(pos - 0x400)), SECONDS_PER_BYTE)
            self.last_position = pos
            if C.lt(C.fabs(C.sub(audio, anim)), SYNC_TOLERANCE):
                self.nudge = C.ZERO
            elif C.lt(anim, audio):
                self.nudge = NUDGE
            else:
                self.nudge = C.neg(NUDGE)
        if C.eq(self.nudge, C.ZERO):
            return
        for i in range(max(_s8(f.anim_count), 0)):
            f.tracks[i] = C.add(f.tracks[i], self.nudge)

    # ---- dialog_drawTask 0x230628 -------------------------------------------------------
    def draw(self, host, fade, text_option, glyph, stream_status):
        """Draw calls in order.  fade is g_uiFadeIn[0] (raw); glyph the byte at 0x41b978;
        stream_status() is audio_streamStatus(1), called only where the original calls it.
        Returns the list of calls (also appended to self.log)."""
        ops = []
        if self.node is None or self.cam_move != 0:
            return ops
        if self.drawn == 0:
            self.drawn = 1
            ops.append(('fade_restart', 0))
        level = C.sub(C.ONE, fade) if self.closing else fade
        alpha = (C.to_int(C.mul(level, 0x43000000)) << 24) & 0xFFFFFFFF
        pick = alpha | COLOUR_PICK
        ops.append(('text_begin', TEXT_LAYER, alpha | COLOUR_BODY))
        if self.revealing:
            ops.append(('budget', self.reveal))
        ops.append(('clip', 0, ROW0 + LINE + 6, 0x280, ROW0 + 6 * LINE))
        bottom = BODY_BOTTOM_NOTEXT if text_option == 0 else BODY_BOTTOM_TEXT
        ops.append(('wrapped', BODY_X, ROW0 + LINE - self.scroll, 'body', BODY_W, BODY_TOP,
                    bottom, LINE))
        ops.append(('budget', -1))
        ops.append(('clip', 0, 0, 0x280, 0x1C0))
        if self.reveal_done:
            node = self.nodes[self.node]
            if self.at_end and (text_option != 0 or (self.hold == 0 and stream_status() == 0)):
                if not self.visible:
                    ops.append(('colour', pick))
                    ops.append(('wide', CHOICE_X, ROW0 + 6 * LINE, 'Affirmation', FORCED_BUDGET))
                else:
                    for i, k in enumerate(self.visible):
                        ops.append(('colour', pick if i == self.cursor else alpha | COLOUR_OTHER))
                        ops.append(('wrapped', CHOICE_X, self.choice_y[i], node.choices[k].text,
                                    BODY_W, CHOICE_TOP, CHOICE_BOTTOM, LINE))
                ops.append(('colour', pick))
                if node.raw_choices == 0:
                    y = MORE_Y
                else:
                    h = C.hermite(self.blend, C.ZERO, C.ONE, C.MINUS_ONE, C.MINUS_ONE)
                    y0 = self.choice_y[self.cursor]
                    y1 = self.choice_y[self.cursor_target]
                    v = C.add(C.from_int(y0), C.mul(C.from_int(C.s32(y1 - y0)), h))
                    y = C.to_int(C.add(C.from_int(C.to_int(v)), C.HALF))
                ops.append(('colour', alpha | COLOUR_GLYPH))
                ops.append(('ascii', BODY_X, y, glyph, GLYPH_BUDGET))
                self.prompt_shown = 1
            if self.more:
                ops.append(('colour', alpha | COLOUR_GLYPH))
                ops.append(('ascii', 0x33, MORE_Y, glyph, GLYPH_BUDGET))
                ops.append(('colour', pick))
                ops.append(('wide', 0x51, MORE_Y, 'dialogMore', FORCED_BUDGET))
        ops.append(('text_end',))
        ops.append(('sprite', BOX_X, BOX_Y, BOX_LAYER, alpha | COLOUR_BOX))
        if text_option != 0:
            shown = self.name[:self.name_len]
            if self.closing and self.name_len:
                cut = C.to_int(C.mul(C.from_int(self.name_len), NAME_SHRINK))
                self.name_len = max(self.name_len - max(1, cut), 0)
            ops.append(('text_begin', TEXT_LAYER, alpha | COLOUR_NAME))
            ops.append(('wide_centered', NAME_X, NAME_Y, tuple(shown), FORCED_BUDGET))
            ops.append(('text_end',))
            if not host.is_local(self.active_player):
                ops.append(('text_begin', TEXT_LAYER, alpha | COLOUR_NAME))
                ops.append(('fit', self.active_player, PLAYER_FIT))
                ops.append(('ascii_centered', PLAYER_X, PLAYER_Y, self.active_player, PLAYER_BUDGET))
                ops.append(('text_end',))
        self.log.extend(ops)
        return ops

    # ---- dialog_free 0x22f99c (game_clearLevel) -----------------------------------------
    def free(self):
        for b in self.buffers:
            if b['ptr']:
                self.log.append(('free',))
                b['ptr'] = 0
        self.prompt_node = -1
        self.focus = None
        self.focus_word = 0
        self.mutex = 0
        self.node = None
        self.active_player = 0
        self.node_index = -1
        self.prompt_shown = 0
        self.cam_move = 0
        self.swoop = 0

    # ---- 0x22fc44 (no caller found) -----------------------------------------------------
    def prompt_is(self, index):
        return 1 if self.prompt_shown != 0 and index == self.prompt_node else 0

    # ---- script built-ins ---------------------------------------------------------------
    def change_swoop(self, mode):
        self.swoop = C.s32(mode)

    def start_with_swoop_done(self):
        self.swoop_done = 1

    def new_world_post(self, name):
        self.next_world = name

    def activate_store(self, host, index):
        """script activateStore 0x144010."""
        if (index & 0xFFFFFFFF) < 21:
            self.store_index = C.s16(index)
        if self.is_open:
            self.store_pending = 1
            return
        if not host.network:
            self.log.append(('shop', self.active_player, 0, 1))
        else:
            for slot in host.alive:
                if host.is_local(slot):
                    self.log.append(('close_local_menus', 0))
                    self.log.append(('shop', slot, 0, 1))

    def activate_mission_menu(self, host, first_active=0):
        """script activateMissionMenu 0x143fa8: refused while a dialog is open."""
        if self.is_open or host.recall:
            return
        self.log.append(('mission_menu', first_active if host.network else self.active_player))

    # ---- Creature_interact 0x116bd8 / Creature_trigger 0x11a5f0 -------------------------
    def interact(self, host, obj, slot, flag800000=False):
        """Slot 14 of a creature: the player used it.  flag800000 is
        net_anyAlivePlayerFlag800000().  Returns what happened."""
        pobj = host.player_obj.get(slot)
        if not obj.display_name or pobj is None:
            return 'nothing'
        shop = obj.props.get('shop')
        if shop is not None and _atoi(shop) != 0 and flag800000:
            if host.is_local(slot):
                self.log.append(('shop', slot, 0, 1))
                return 'shop'
            return 'nothing'
        dx = C.sub(pobj.pos[0], obj.pos[0])
        dy = C.sub(pobj.pos[1], obj.pos[1])
        dot = C.add(C.mul(dx, C.cos16(obj.facing)), C.mul(dy, C.sin16(obj.facing)))
        if not C.lt(C.ZERO, dot):
            return 'behind'
        if self.mutex_try() != 0:
            return 'busy'
        self.active_player = slot
        name = obj.props.get('dialogscript')
        if name is None:
            return 'no script'         # script_runByName(0) returns -1, the mutex stays held
        host.run_script(name)
        return 'script'

    def trigger(self, host, obj):
        """Slot 3: script trigger(name, value) on a creature."""
        if not obj.display_name or obj.props.get('dialogscript') is None:
            return 'nothing'
        if self.mutex_try() != 0:
            return 'busy'
        host.run_script(obj.props['dialogscript'])
        return 'script'


def _atoi(text):
    """obj_getPropInt: the leading decimal integer (atoi rules), 0 when none."""
    text = text.strip()
    sign, i = 1, 0
    if text[:1] in '+-':
        sign, i = (-1 if text[0] == '-' else 1), 1
    j = i
    while j < len(text) and text[j].isdigit():
        j += 1
    return sign * int(text[i:j]) if j > i else 0


class TickIO:
    """Per-call inputs of dialog_runTask.  The audio functions are called only where the
    original calls them; each returns the next value of its list (the last one repeats)."""

    def __init__(self, camera=(1,), look=C.ZERO, held_ready=(0,), queue_count=(0,),
                 stream_position=(0,), stream_status=(0,), fade=C.ZERO, text_option=1, shown=0):
        self._camera = list(camera)
        self.look = look
        self._held, self._queue = list(held_ready), list(queue_count)
        self._pos, self._status = list(stream_position), list(stream_status)
        self.fade, self.text_option, self.shown = fade, text_option, shown
        self.asked = []

    @staticmethod
    def _next(values):
        return values.pop(0) if len(values) > 1 else values[0]

    def camera_step(self, frames):
        self.asked.append(('camera', frames))
        return self._next(self._camera)

    def held_ready(self):
        self.asked.append(('held',))
        return self._next(self._held)

    def queue_count(self):
        self.asked.append(('queue',))
        return self._next(self._queue)

    def stream_position(self):
        self.asked.append(('position',))
        return self._next(self._pos)

    def stream_status(self):
        self.asked.append(('status',))
        return self._next(self._status)
