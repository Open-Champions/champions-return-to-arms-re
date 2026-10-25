#!/usr/bin/env python3
"""difftest_dialog.py - compare tools/ref_dialog.py with the original dialog functions.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_dialog.py [path/to/SLUS_209.73] [--seed N] [--cases N]

The original functions run in tools/ee_emu.py on synthetic state: a .dbin built by
ref_dialog.build_dbin, made-up text, objects and audio answers.  Every callee outside the
dialog machine is a recording stub fed from the same ref_dialog.Host the reference reads,
so each suite compares (a) the dialog state words in memory, (b) the calls made outside
the machine, in order, and (c) the scripts run.  No game file other than the executable
is read and nothing is written.

Suites: message (dialog_start), open (onMsg 0 + showNode + queueLineAudio), confirm /
move / end / leave (onMsg 1-4), tick (dialog_runTask), draw (dialog_drawTask), free,
interact (Creature_interact, Creature_trigger), builtins (startDialog, dialogRunning,
changeSwoop, startWithSwoopDone, newWorldPost, activateStore, activateMissionMenu,
forceMutexRelease), sequence (seeded conversations through open, ticks, messages and
draws), mouth (dialog_startTalkAnim, dialog_syncMouth), seeds (no write to the three generator words anywhere above).
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError  # noqa: E402
import ref_core as C  # noqa: E402
import ref_dialog as R  # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
HOME_ELF = os.path.expanduser('~/champions-re/SLUS_209.73')

# ---- the machine ------------------------------------------------------------------------
F_QUEUE_AUDIO = 0x22EC9C
F_ON_MSG = 0x22EE2C
F_FREE = 0x22F99C
F_START = 0x22FA50
F_IS_OPEN = 0x22FBC0
F_MUTEX_TRY, F_MUTEX_HELD, F_MUTEX_RELEASE, F_PROMPT_IS = 0x22FC04, 0x22FC2C, 0x22FC38, 0x22FC44
F_TALK_ANIM, F_SYNC_MOUTH = 0x22FC70, 0x22FDD8
F_RUN, F_DRAW, F_SHOW = 0x22FF48, 0x230628, 0x230C74
F_CLEAR_TEXT, F_SET_FOCUS, F_ROW, F_OBJ_IF_OPEN = 0x230FE4, 0x231014, 0x231038, 0x231050
F_INTERACT, F_TRIGGER = 0x116BD8, 0x11A5F0
B_START, B_RUNNING, B_SWOOP, B_SWOOP_DONE = 0x143824, 0x143CB0, 0x1438B0, 0x1438C4
B_NEXT_WORLD, B_MISSION_MENU, B_STORE, B_FORCE_RELEASE = 0x143CC4, 0x143FA8, 0x144010, 0x1471DC

# ---- leaf helpers that run as they are ---------------------------------------------------
LEAF = {0x3B8DC4, 0x3B868C, 0x3B8534, 0x3B60C0, 0x19E854, 0x19E994, 0x1658F0, 0x166630, 0x1666E0}
SPRINTF = 0x3B7EF0

# ---- state words ------------------------------------------------------------------------
A = dict(
    data=0x8E2D60, file=0x8E2D5C, node_index=0x8E2E88, prompt_node=0x8E2E8C, prompt_shown=0x8E2E90,
    revealing=0x8E2CB0, reveal_done=0x8E2CB4, reveal=0x8E2D4C, at_end=0x8E2CA8, more=0x8E2CAC,
    cursor=0x8E2CB8, cursor_target=0x8E2CBC, blend=0x8E2D54, scroll=0x8E2CCC,
    scroll_target=0x8E2CC8, total=0x8E2CD0, span=0x8E2D58, nvis=0x8E2D18, visible=0x8E2D20,
    choice_y=0x8E2CE8, text=0x4FDD38, text_len=0x8E2D48, cam_move=0x8E2D50, closing=0x8E2CD8,
    end_sent=0x8E2CE0, drawn=0x8E2CD4, swoop=0x4FDCE4, side=0x8E2CC4, remote=0x8E2CA0,
    store_pending=0x4FDD30, store_index=0x4F7150, next_world=0x4FDCF0, name=0x8E2D68,
    name_len=0x8E2CDC, hold=0x4FDCD4, anm_ready=0x4FDCD5, buf_sel=0x4FDCD6, cur_buf=0x4FDCD7,
    talking=0x4FDCD8, nudge=0x4FDCDC, buffers=0x8E2E68, queue_mark=0x8E2CA4, focus=0x4FDCC0,
    focus_word=0x4FDCC4, idle_anim=0x4FDCCC, node_ptr=0x4FDCD0, mutex=0x4FE53C,
    hud=0x4F66A8, swoop_done=0x4FDCE8, active_player=0x4D8AE4, pending_world=0x41B6D0,
    orient=0x41B720, shown=0x44E028, cc0=0x8E2CC0, channel=0x8E2E94)
G_NUM_PLAYERS = 0x4D8AE0
G_PLAYER_OBJ = 0x4DCEC8          # + slot * 0x4c30
G_PLAYERS = 0x4D8AF0
REC = 0x4C30
G_RAW_PAD = 0x4028DC             # + slot * 0x58
G_NET = 0x402791
G_ALIVE, G_ALIVE_COUNT = 0x4F8440, 0x4F8420
G_RECALL = 0x41B51D
G_SHOP_OPEN = 0x41B50C
G_CONFIRM = 0x41BFBC
G_FADE = 0x506070
G_OPTION = 0x4FDCC8
G_GLYPH = 0x41B978
G_CAMERA_POS = 0x44F038
G_LOOK_BASE = 0x44F110
G_LOCAL_CAMERA = 0x4F8450
G_FONT = 0x4F7100
G_BOX = 0x4FE538
G_LEVEL = 0x41B721
SEEDS = (0x404460, 0x404464, 0x404468)

RESULTS = []


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %-10s %s' % ('PASS' if ok else 'FAIL', name, detail))


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


class Rig:
    """One emulator with the dialog machine's surroundings stubbed from a ref Host."""

    def __init__(self, elf, host, nodes=None, level='level'):
        self.emu = emu = EE(elf)
        emu.follow = set(LEAF) | {F_QUEUE_AUDIO, F_ON_MSG, F_FREE, F_START, F_IS_OPEN, F_MUTEX_TRY,
                                  F_MUTEX_HELD, F_MUTEX_RELEASE, F_SHOW, F_CLEAR_TEXT, F_SET_FOCUS,
                                  F_ROW, F_OBJ_IF_OPEN, F_RUN, F_DRAW, F_INTERACT, F_TRIGGER,
                                  B_START, B_RUNNING, B_SWOOP, B_SWOOP_DONE, B_NEXT_WORLD,
                                  B_MISSION_MENU, B_STORE, B_FORCE_RELEASE, F_PROMPT_IS}
        emu.default_ret = 0
        self.mem = emu.mem
        self.host = host
        self.log = []
        self.asked = []
        self.unexpected = []
        self.io = None
        self.level = level
        self.mem.write(G_LEVEL, level.encode() + b'\0')
        self.cam = emu.alloc(0x200)
        self.mem.w32(G_LOCAL_CAMERA, self.cam)
        self.mem.w32(G_FONT, 0x00ABC000)
        self.mem.w32(G_BOX, 0x00BCD000)
        self.mem.w32(A['channel'], 7)
        self.wide_ptr = {}            # key -> address of the wide string
        self.wide_key = {}            # address -> key
        self.cstr_cache = {}
        self.objects = {}             # addr -> ref Object
        self.vt_npc = self._code_stub(lambda e: self.t_npc)
        self.vt_other = self._code_stub(lambda e: self.t_other)
        self.t_npc, self.t_other = emu.alloc(16), emu.alloc(16)
        self.file_ptr = 0
        if nodes is not None:
            self.load_file(nodes)
        self.yaw = self.pitch = 0
        self.first_active = 0
        self._install()

    # ---- memory helpers ------------------------------------------------------------------
    def _code_stub(self, fn):
        addr = self.emu.alloc(16)
        self.emu.stub(addr, function=fn)
        return addr

    def cstr(self, text):
        if text not in self.cstr_cache:
            data = text.encode('latin1') + b'\0'
            p = self.emu.alloc(len(data) + 4)
            self.mem.write(p, data)
            self.cstr_cache[text] = p
        return self.cstr_cache[text]

    def wide(self, key):
        if key not in self.wide_ptr:
            units = self.host.text(key)
            p = self.emu.alloc(2 * len(units) + 4)
            self.mem.write(p, struct.pack('<%dH' % len(units), *units) + b'\0\0')
            self.wide_ptr[key], self.wide_key[p] = p, key
        return self.wide_ptr[key]

    def read_wide(self, addr, limit=512):
        out = []
        for i in range(limit):
            u = self.mem.u16(addr + 2 * i)
            if u == 0:
                break
            out.append(u)
        return tuple(out)

    def load_file(self, nodes):
        data = R.build_dbin(nodes)
        self.file_ptr = self.emu.alloc(len(data) + 16)
        self.mem.write(self.file_ptr, data)
        self.entry = self.emu.alloc(16)
        self.mem.w32(self.entry + 4, self.file_ptr)

    def place(self, obj):
        """Give a ref Object memory (its addr is replaced by the allocation)."""
        p = self.emu.alloc(0x480)
        obj.addr = p
        self.objects[p] = obj
        self.sync_object(obj)
        return p

    def sync_object(self, obj):
        p = obj.addr
        for i in range(3):
            self.mem.w32(p + 0x10 + 4 * i, obj.pos[i])
        self.mem.w16(p + 0x38, obj.facing)
        self.mem.w32(p + 0x0C, obj.flags)
        vt = self.emu.alloc(16)
        self.mem.w32(vt + 4, self.vt_npc if obj.npc else self.vt_other)
        self.mem.w32(p + 0x48, vt)
        w = self.emu.alloc(16)
        self.mem.w32(w, obj.word24)
        self.mem.w32(p + 0x24, w)
        self.mem.w8(p + 0x118, obj.anim_count & 0xFF)
        self.mem.w32(p + 0x11C, obj.anim_cur)
        self.mem.w32(p + 0x368, obj.display_name)

    def plant_world(self):
        h, m = self.host, self.mem
        m.w8(G_NET, 1 if h.network else 0)
        m.w32(G_NUM_PLAYERS, h.num_players)
        for slot in range(4):
            o = h.player_obj.get(slot)
            m.w32(G_PLAYER_OBJ + slot * REC, o.addr if o is not None else 0)
            m.w32(G_RAW_PAD + slot * 0x58, h.raw_pad.get(slot, 0))
        m.w32(G_ALIVE_COUNT, len(h.alive))
        for i, slot in enumerate(h.alive):
            m.w32(G_ALIVE + 4 * i, slot)
        m.w8(G_RECALL, h.recall)
        m.w32(G_SHOP_OPEN, h.shop_open)
        m.w32(G_CONFIRM, h.confirm_mask)

    # ---- stubs --------------------------------------------------------------------------
    def _install(self):
        emu, mem, h = self.emu, self.mem, self.host
        st = emu.stub

        def rec(*t):
            self.log.append(t)

        def run_script(e):
            name = mem.cstr(e.r[4]) if e.r[4] else None
            if name is None:
                return -1 & 0xFFFFFFFF
            return h.run_script(name) & 0xFFFFFFFFFFFFFFFF
        st(0x1ED694, function=run_script, name='script_runByName')
        st(0x13E150, function=lambda e: 1 if h.is_local(s32(e.r[4])) else 0, name='net_isLocalSlot')

        def task_running(e):
            name = mem.cstr(e.r[4])
            if name == 'missionmenurun':
                return 1 if h.mission_menu else 0
            if name == 'pauseMenu':
                return 1 if h.pause_menu else 0
            self.unexpected.append(('task', name))
            return 0
        st(0x19E5E8, function=task_running, name='task_isRunning')
        self._lump = None

        def lump_load(e):
            self._lump = mem.cstr(e.r[4])
            self.log.append(('lump_load', self._lump))
            return 0x00CDE000
        st(0x173558, function=lump_load, name='lump_load')

        def find_entry(e):
            self.log.append(('lump', self._lump, mem.cstr(e.r[5])))
            return self.entry
        st(0x171DE4, function=find_entry, name='lump_findEntry')

        def find_one(e):
            found = h.objects.get(mem.cstr(e.r[4]), [])
            return found[0].addr if found else 0
        st(0x14F498, function=find_one, name='world_findObjectByName')

        def find_all(e):
            found = h.objects.get(mem.cstr(e.r[4]), [])[:s32(e.r[6])]
            out = e.r[5] & 0xFFFFFFFF
            for i, o in enumerate(found):
                mem.w32(out + 4 * i, o.addr)
            mem.w32(out + 4 * len(found), 0)
            return len(found)
        st(0x14BF58, function=find_all, name='world_findObjectsByName')
        st(0x3C4C30, function=lambda e: self.t_npc, name='NPC_typeinfo')
        st(0x3B1250, function=lambda e: 1 if (e.r[4] & 0xFFFFFFFF) == (e.r[5] & 0xFFFFFFFF) else 0,
           name='rtti_typeInfoEquals')

        def role_anim(e):
            obj = self.objects.get(e.r[4] & 0xFFFFFFFF)
            return h.role_anim(obj, mem.cstr(e.r[5]))
        st(0x160928, function=role_anim, name='obj_findRoleAnim')

        def prop_str(e):
            obj = self.objects.get(e.r[4] & 0xFFFFFFFF)
            key = mem.cstr(e.r[5]).lower()
            if obj is None or key not in obj.props:
                return 0
            return self.cstr(obj.props[key])
        st(0x14F4C0, function=prop_str, name='obj_getPropStr')

        def prop_int(e):
            obj = self.objects.get(e.r[4] & 0xFFFFFFFF)
            key = mem.cstr(e.r[5]).lower()
            if obj is None or key not in obj.props:
                return 0
            return R._atoi(obj.props[key]) & 0xFFFFFFFFFFFFFFFF
        st(0x14C880, function=prop_int, name='obj_getPropInt')

        def text_lookup(e):
            p = e.r[4] & 0xFFFFFFFF
            if p == 0:
                self.unexpected.append(('text_lookup', 0))
                return 0
            return self.wide(mem.cstr(p))
        st(0x173C84, function=text_lookup, name='text_lookup')
        st(0x11A450, function=lambda e: rec('freeze_all'), name='creatures_freezeAll')
        st(0x11A470, function=lambda e: rec('unfreeze_all'), name='creatures_unfreezeAll')

        def alloc(e):
            rec('alloc', s32(e.r[4]))
            return emu.alloc(max(s32(e.r[4]), 16))
        st(0x14FF88, function=alloc, name='mem_allocTagged')
        st(0x150198, function=lambda e: rec('free'), name='mem_free')
        st(0x322954, function=lambda e: rec('fade_wait', s32(e.r[4])), name='mainloop_startFadeWait')
        st(0x203BB8, function=lambda e: rec('dialog_view', s32(e.r[6])), name='Camera_setupDialogView')
        st(0x1EB000, function=lambda e: rec('close_local_menus', s32(e.r[4])), name='net_closeLocalMenus')
        st(0x207210, function=lambda e: rec('camera_push'), name='Camera_pushState')
        st(0x207308, function=lambda e: rec('camera_yaw', C.s16(e.r[5])), name='Camera_setYaw')
        st(0x207310, function=lambda e: rec('camera_pitch', C.s16(e.r[5])), name='Camera_setPitch')
        st(0x2035C8, function=lambda e: rec('camera_apply', e.f[12], e.f[13], e.f[14]),
           name='Camera_apply')
        st(0x203400, function=lambda e: rec('camera_update'), name='Camera_update')
        st(0x207450, function=lambda e: self.yaw & 0xFFFF, name='Camera_getYaw')
        st(0x207458, function=lambda e: self.pitch & 0xFFFF, name='Camera_getPitch')
        st(0x2072E8, function=lambda e: rec('camera_mode', s32(e.r[5])), name='Camera_setMode')

        def entry_length(e):
            name = mem.cstr(e.r[4])
            table = h.anm_length if name.endswith('.anm') else h.vag_length
            return table.get(name, 0) & 0xFFFFFFFFFFFFFFFF
        st(0x215E48, function=entry_length, name='stream_levelEntryLength')
        st(0x211CE8, function=lambda e: rec('stream_stop', s32(e.r[4])), name='audio_streamStop')
        st(0x170838, function=lambda e: rec('anim_push', (e.r[4] - 0x114) & 0xFFFFFFFF,
                                            s32(e.r[5]), s32(e.r[6])), name='anim_push')

        def text_begin(e):
            if e.r[4] & 0xFFFFFFFF != 0x00ABC000:
                self.unexpected.append(('font', hex(e.r[4])))
            rec('text_begin', s32(e.r[5]), e.r[6] & 0xFFFFFFFF)
        st(0x1800B8, function=text_begin, name='text_begin')

        def what(ptr):
            ptr &= 0xFFFFFFFF
            if ptr == A['text']:
                return 'body'
            return self.wide_key.get(ptr, hex(ptr))

        def wrapped(e):
            r = e.r
            x, y, w, top, bot, line = (s32(r[4]), s32(r[5]), s32(r[7]), s32(r[8]), s32(r[9]),
                                       s32(r[10]))
            rec('wrapped', x, y, what(r[6]), w, top, bot, line)
            if self.io is not None and (r[6] & 0xFFFFFFFF) == A['text'] and self.measuring:
                mem.w32(A['shown'], self.io.shown)
            return h.layout_height
        st(0x181280, function=wrapped, name='text_drawWrapped')
        st(0x180500, function=lambda e: rec('text_end'), name='text_end')
        st(0x1803E0, function=lambda e: rec('clip', s32(e.r[4]), s32(e.r[5]), s32(e.r[6]), s32(e.r[7])),
           name='text_setClip')
        st(0x181A78, function=lambda e: rec('budget', s32(e.r[4])), name='text_setBudget')
        st(0x1802E0, function=lambda e: rec('colour', e.r[4] & 0xFFFFFFFF), name='text_setColour')
        st(0x181C10, function=lambda e: rec('wide', s32(e.r[4]), s32(e.r[5]), what(e.r[6]), s32(e.r[7])),
           name='text_drawWide')
        st(0x181AA0, function=lambda e: rec('ascii', s32(e.r[4]), s32(e.r[5]),
                                            mem.u8(e.r[6] & 0xFFFFFFFF), s32(e.r[7])), name='text_drawAscii')
        st(0x181CA0, function=lambda e: rec('wide_centered', s32(e.r[4]), s32(e.r[5]),
                                            self.read_wide(e.r[6] & 0xFFFFFFFF), s32(e.r[7])),
           name='text_drawWideCentered')
        st(0x181AF8, function=lambda e: rec('ascii_centered', s32(e.r[4]), s32(e.r[5]),
                                            ((e.r[6] & 0xFFFFFFFF) - 0x4F3EC8) // 32, s32(e.r[7])),
           name='text_drawAsciiCentered')
        st(0x1BDF60, function=lambda e: rec('fit', s32(e.r[5]), s32(e.r[7])), name='ui_fitText')
        st(0x17FB68, function=lambda e: rec('sprite', s32(e.r[5]), s32(e.r[6]), s32(e.r[7]),
                                            e.r[8] & 0xFFFFFFFF), name='ui_drawSprite')
        st(0x320EC4, function=lambda e: rec('fade_restart', s32(e.r[4])), name='ui_restartFadeIn')

        def poll(e):
            raise EmuError('lump_pollAsync reached: the original would spin')
        st(0x172CA8, function=poll, name='lump_pollAsync')
        st(0x215FC8, function=lambda e: rec('stream_play', s32(e.r[4]), mem.cstr(e.r[5]), s32(e.r[6])),
           name='stream_playLevel')

        def find_level_entry(e):
            name = mem.cstr(e.r[4])
            if name not in h.anm_entry:
                return 0
            off, nxt = h.anm_entry[name]
            p = emu.alloc(0xA0)
            mem.w32(p + 0x40, off)
            mem.w32(p + 0x90, nxt)
            return p
        st(0x210E60, function=find_level_entry, name='stream_findLevelEntry')
        st(0x216820, function=lambda e: self.cstr('stream'), name='stream_levelFileName')

        def cd_read(e):
            rec('cd_read', s32(e.r[7]), s32(e.r[8]))
            mem.w8(e.r[6] & 0xFFFFFFFF, 0)
        st(0x1729E8, function=cd_read, name='cd_readAsync')
        st(0x1EDAC0, function=lambda e: rec('post_action'), name='script_runPostAction')
        st(0x1C7AF8, function=lambda e: rec('shop', s32(e.r[4]), s32(e.r[5]), s32(e.r[6])),
           name='shop_openOrStock')
        st(0x18617C, function=lambda e: rec('far_clip', e.f[12]), name='camera_setFarClip')
        st(0x216570, function=lambda e: rec('duck', e.f[12]), name='music_setDuck')
        st(0x13DB38, function=lambda e: rec('send', bytes(mem.read(e.r[5] & 0xFFFFFFFF, s32(e.r[6])))),
           name='net_sendGameMsg')
        st(0x231520, function=lambda e: rec('mission_menu', s32(e.r[4])), name='missionMenu_open')
        st(0x13E5A0, function=lambda e: self.first_active, name='net_firstActiveSlot')

        def ask(kind, fn):
            def run(e):
                if self.io is None:
                    self.unexpected.append(('ask', kind))
                    return 0
                return fn(e) & 0xFFFFFFFFFFFFFFFF
            return run
        st(0x204250, function=ask('camera', lambda e: self.io.camera_step(s32(e.r[5]))),
           name='Camera_lookAt')
        st(0x211C18, function=ask('held', lambda e: self.io.held_ready()), name='stream_heldEntryReady')
        st(0x216458, function=ask('queue', lambda e: self.io.queue_count()), name='stream_queueCount')
        st(0x2162A0, function=lambda e: rec('clear_hold', s32(e.r[4])), name='stream_clearHold')
        st(0x211B20, function=ask('status', lambda e: self.io.stream_status()), name='audio_streamStatus')
        st(0x216480, function=ask('position', lambda e: self.io.stream_position()),
           name='audio_streamPosition')
        st(F_TALK_ANIM, function=lambda e: rec('talk_anim'), name='dialog_startTalkAnim')
        st(F_SYNC_MOUTH, function=lambda e: rec('sync_mouth'), name='dialog_syncMouth')

        def sprintf(e):
            fmt = mem.cstr(e.r[4] if False else e.r[5])
            arg = e.r[6] & 0xFFFFFFFF
            if fmt == '%c':
                out = bytes([arg & 0xFF])
            elif fmt.count('%s') == 1 and '%' not in fmt.replace('%s', ''):
                out = fmt.replace('%s', mem.cstr(arg)).encode('latin1')
            else:
                raise EmuError('sprintf format %r not handled by the rig' % fmt)
            mem.write(e.r[4] & 0xFFFFFFFF, out + b'\0')
            return len(out)
        st(SPRINTF, function=sprintf, name='sprintf')

        def scr_get_addr(e):
            mem.w32(e.r[6] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)
            return 0
        st(0x1414A8, function=scr_get_addr, name='scr_getAddr')

        def scr_get_string(e):
            mem.write(e.r[4] & 0xFFFFFFFF, mem.read(e.r[5] & 0xFFFFFFFF, 64))
            return 0
        st(0x141650, function=scr_get_string, name='scr_getString')
        self.measuring = False

    # ---- running ------------------------------------------------------------------------
    def call(self, addr, *args, fargs=()):
        self.emu.reset_log()
        self.emu.record_writes = True
        try:
            return self.emu.call(addr, *args, fargs=fargs, max_steps=2000000)
        finally:
            for c in self.emu.calls:
                if getattr(c, 'stubbed', False) and c.target not in self.emu.hooks:
                    self.unexpected.append(('callee', hex(c.target)))
            for _pc, addr_w, _size, _v in self.emu.writes:
                for s in SEEDS:
                    if s <= addr_w < s + 4:
                        self.unexpected.append(('seed write', hex(addr_w)))

    def message(self, msg):
        buf = self.emu.alloc(len(msg) + 16)
        self.mem.write(buf, bytes(msg))
        return self.call(F_ON_MSG, buf)

    # ---- state transfer -----------------------------------------------------------------
    def plant_state(self, d):
        """Write a ref Dialog into memory (for suites that start mid-dialog)."""
        m = self.mem
        m.w32(A['file'], self.file_ptr)
        m.w32(A['data'], self.file_ptr + R.NODE_SIZE * d.node if d.node is not None else 0)
        m.w32(A['node_ptr'], m.u32(A['data']))
        for k in ('node_index', 'prompt_node', 'prompt_shown', 'revealing', 'reveal_done', 'reveal',
                  'at_end', 'more', 'cursor', 'cursor_target', 'scroll', 'scroll_target', 'total',
                  'cam_move', 'closing', 'end_sent', 'drawn', 'swoop', 'side', 'remote',
                  'name_len', 'queue_mark', 'idle_anim', 'mutex', 'swoop_done', 'active_player',
                  'focus_word', 'store_pending'):
            m.w32(A[k], getattr(d, k) & 0xFFFFFFFF)
        m.w32(A['blend'], d.blend)
        m.w32(A['span'], d.span)
        m.w32(A['nudge'], d.nudge)
        m.w32(A['nvis'], len(d.visible))
        for i in range(R.VISIBLE_ROOM):
            m.w32(A['visible'] + 4 * i, d.visible[i] if i < len(d.visible) else 0)
        for i in range(12):
            m.w32(A['choice_y'] + 4 * i, d.choice_y[i] & 0xFFFFFFFF)
        units = list(d.text) + [0]
        m.write(A['text'], struct.pack('<%dH' % len(units), *units))
        m.w32(A['text_len'], d.text_len)
        nm = list(d.name) + [0]
        m.write(A['name'], struct.pack('<%dH' % len(nm), *nm))
        for k in ('hold', 'anm_ready', 'buf_sel', 'cur_buf', 'talking'):
            m.w8(A[k], getattr(d, k))
        m.w8(A['hud'], d.hud_suppressed)
        m.write(A['next_world'], d.next_world.encode() + b'\0')
        for i, b in enumerate(d.buffers):
            base = A['buffers'] + 16 * i
            m.w32(base, self.emu.alloc(64) if b['ptr'] else 0)
            m.w32(base + 4, b['has'])
            m.w32(base + 8, b['size'])
            m.w32(base + 12, b['vag'])
        m.w32(A['focus'], d.focus.addr if d.focus is not None else 0)
        m.w32(A['cc0'], 0)

    def snap(self, with_text=True):
        m = self.mem
        data = m.u32(A['data'])
        out = dict(node=None if data == 0 else (data - self.file_ptr) // R.NODE_SIZE)
        for k in ('node_index', 'prompt_node', 'prompt_shown', 'revealing', 'reveal_done', 'reveal',
                  'at_end', 'more', 'cursor', 'cursor_target', 'scroll', 'scroll_target', 'total',
                  'cam_move', 'closing', 'end_sent', 'drawn', 'swoop', 'side', 'remote', 'name_len',
                  'queue_mark', 'idle_anim', 'mutex', 'swoop_done', 'active_player', 'focus_word',
                  'store_pending'):
            out[k] = m.s32(A[k])
        out['blend'] = m.u32(A['blend'])
        out['visible'] = [m.s32(A['visible'] + 4 * i) for i in range(m.s32(A['nvis']))]
        out['choice_y'] = [m.s32(A['choice_y'] + 4 * i) for i in range(12)]
        if with_text:
            out['text'] = list(self.read_wide(A['text'], 0x400))
            out['text_len'] = m.s32(A['text_len'])
            out['name'] = list(self.read_wide(A['name'], 128))
        for k in ('hold', 'anm_ready', 'buf_sel', 'cur_buf', 'talking'):
            out[k] = m.s8(A[k])
        out['hud'] = m.s8(A['hud'])
        out['next_world'] = m.cstr(A['next_world'])
        out['buffers'] = [(1 if m.u32(A['buffers'] + 16 * i) else 0, m.s32(A['buffers'] + 16 * i + 4),
                           m.s32(A['buffers'] + 16 * i + 8), m.s32(A['buffers'] + 16 * i + 12))
                          for i in range(2)]
        f = m.u32(A['focus'])
        out['focus'] = f
        return out


def ref_snap(d, rig, with_text=True):
    out = dict(node=d.node)
    for k in ('node_index', 'prompt_node', 'prompt_shown', 'revealing', 'reveal_done', 'reveal',
              'at_end', 'more', 'cursor', 'cursor_target', 'scroll', 'scroll_target', 'total',
              'cam_move', 'closing', 'end_sent', 'drawn', 'swoop', 'side', 'remote', 'name_len',
              'queue_mark', 'idle_anim', 'mutex', 'swoop_done', 'active_player', 'focus_word',
              'store_pending'):
        out[k] = s32(getattr(d, k))
    out['blend'] = d.blend
    out['visible'] = list(d.visible)
    out['choice_y'] = [s32(v) for v in d.choice_y]
    if with_text:
        out['text'] = list(d.text)
        out['text_len'] = d.text_len
        out['name'] = list(d.name)
    for k in ('hold', 'anm_ready', 'buf_sel', 'cur_buf', 'talking'):
        out[k] = getattr(d, k)
    out['hud'] = d.hud_suppressed
    out['next_world'] = d.next_world
    out['buffers'] = [(1 if b['ptr'] else 0, b['has'], s32(b['size']), s32(b['vag'])) for b in d.buffers]
    out['focus'] = d.focus.addr if d.focus is not None else 0
    return out


def diff(a, b):
    keys = sorted(set(a) | set(b))
    return [(k, a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)]


EXTERNAL = {'lump_load'}            # calls the rig records that the ref log leaves out


def norm(log):
    return [t for t in log if t[0] not in EXTERNAL]


# ======================================================================================
# Scenario builders
# ======================================================================================

def wide_text(rng, n):
    units = []
    for _ in range(n):
        r = rng.random()
        units.append(R.CARET if r < 0.05 else (R.SPACE if r < 0.2 else rng.randrange(0x41, 0x7B)))
    return units


def make_conversation(rng, nodes_n=None):
    """A synthetic .dbin with conditions, choice conditions, actions and jumps, the host
    answers for every script, text and voice it names."""
    host = R.Host()
    n = nodes_n or rng.randint(1, 7)
    nodes = []
    for k in range(n):
        choices = []
        for i in range(rng.choice([0, 1, 1, 2, 2, 3, 4, 8, 10])):
            nxt = rng.choice([-1, -1] + list(range(n)))
            choices.append(R.Choice('ch%d_%d' % (k, i),
                                    rng.choice(['', '', 'cc%d_%d' % (k, i), 'nosuch%d' % i]),
                                    rng.choice(['', 'act%d_%d' % (k, i), 'missing%d' % i]), nxt))
        cond = rng.choice(['', '', 'nc%d' % k, 'gone%d' % k]) if k else rng.choice(['', 'nc0'])
        nodes.append(R.Node(cond, 'tx%d' % k, 'v%d' % rng.randrange(3), '', choices))
        host.texts['tx%d' % k] = wide_text(rng, rng.randint(0, 120))
        for i in range(len(choices)):
            host.texts['ch%d_%d' % (k, i)] = wide_text(rng, rng.randint(1, 20))
            host.scripts['cc%d_%d' % (k, i)] = rng.choice([0, 0, 1, 2, -5])
            host.scripts['act%d_%d' % (k, i)] = rng.choice([0, 1])
        host.scripts['nc%d' % k] = rng.choice([0, 0, 0, 1, 3])
    for v in range(3):
        if rng.random() < 0.7:
            host.anm_length['v%d.anm' % v] = rng.randrange(0, 0x3000)
        host.vag_length['v%d.vag' % v] = rng.randrange(0, 0x20000)
        if rng.random() < 0.5:
            off = rng.randrange(0, 0x100000)
            host.anm_entry['v%d.anm' % v] = (off, off + rng.randrange(0, 0x3000))
    host.texts['Affirmation'] = [0x4F, 0x4B]
    host.texts['dialogMore'] = [0x4D, 0x6F]
    host.texts['nm'] = wide_text(rng, rng.randint(0, 14))
    host.layout_height = rng.choice([0, 19, 38, 57, 95, 133, 190, 400])
    return host, nodes


def make_world(rng, rig, host, name='npc'):
    """Speaker objects and the active player's object."""
    count = rng.choice([1, 1, 2, 3])
    found = []
    for i in range(count):
        o = R.Object(0, x=rng.uniform(-400, 400), y=rng.uniform(-400, 400), z=rng.uniform(-50, 50),
                     facing=rng.randrange(0x10000), flags=rng.choice([0x20, 0x20, 0x1100008, 0]),
                     npc=rng.random() < 0.7, word24=rng.randrange(1, 1 << 30),
                     props={'showname': 'nm'}, anim_count=rng.randint(0, 3),
                     anim_cur=rng.choice([0, 5, 7]))
        rig.place(o)
        found.append(o)
        host.role_anims[(o.addr, 'dialogidle')] = rng.choice([0, 7])
        host.role_anims[(o.addr, 'idle')] = rng.choice([5, 9])
    host.objects[name] = found
    p = R.Object(0, x=rng.uniform(-400, 400), y=rng.uniform(-400, 400), flags=rng.choice([0, 0, 8]))
    rig.place(p)
    host.player_obj = {0: p if rng.random() < 0.9 else None}
    host.num_players = 1
    return found


def open_both(elf, rng, seed_msg=None):
    """Build a conversation, open it in both, return (rig, dialog, host, nodes, ok)."""
    host, nodes = make_conversation(rng)
    host.network = rng.random() < 0.3
    host.local = {0} if rng.random() < 0.85 else {1}
    rig = Rig(elf, host, nodes)
    make_world(rng, rig, host)
    rig.plant_world()
    d = R.Dialog()
    d.active_player = 0
    rig.mem.w32(A['active_player'], 0)
    rig.mem.w8(A['anm_ready'], 1)
    cam = [C.f32(rng.uniform(-1000, 1000)) for _ in range(3)]
    msg = seed_msg or R.start_message('npc', 0, rng.choice([0, 1]), rng.choice([0, 1, 2, -1]), cam,
                                      rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000))
    host.ran = []
    rig.message(msg)
    ran_emu = list(host.ran)
    host.ran = []
    d.on_open(host, msg, nodes)
    return rig, d, host, nodes, ran_emu


# ======================================================================================
# Suites
# ======================================================================================

def suite_message(elf, rng, cases):
    bad = []
    for n in range(cases):
        host = R.Host()
        host.local = {0} if rng.random() < 0.8 else {1}
        rig = Rig(elf, host)
        rig.plant_world()
        name = ''.join(rng.choice('abcdefghij_0123') for _ in range(rng.randint(0, 40)))
        a, b = rng.randrange(-200, 300), rng.randrange(-200, 300)
        cam = [C.f32(rng.uniform(-3000, 3000)) for _ in range(3)]
        for i in range(3):
            rig.mem.w32(G_CAMERA_POS + 4 * i, cam[i])
        rig.yaw, rig.pitch = rng.randrange(-0x8000, 0x8000), rng.randrange(-0x8000, 0x8000)
        is_open = rng.random() < 0.15
        rig.mem.w32(A['data'], 0x1234 if is_open else 0)
        rig.mem.w32(A['swoop_done'], 1)
        ap = rng.choice([0, 0, 1])
        rig.mem.w32(A['active_player'], ap)
        d = R.Dialog()
        d.active_player = ap
        d.node = 0 if is_open else None
        d.swoop_done = 1
        p = rig.cstr(name)
        rig.call(F_START, p, a, b)
        want = d.start(host, name, a, b, cam, rig.yaw, rig.pitch)
        if norm(rig.log) != d.log or rig.mem.s32(A['swoop_done']) != d.swoop_done:
            bad.append((n, norm(rig.log)[-1:], d.log[-1:]))
        if want is not None and R.parse_start_message(want)['name'] != name:
            bad.append((n, 'parse'))
    report('message', not bad, '%d cases%s' % (cases, '' if not bad else ' ' + repr(bad[:2])))


def suite_open(elf, rng, cases):
    bad = []
    for n in range(cases):
        try:
            rig, d, host, nodes, ran_emu = open_both(elf, rng)
        except ValueError as exc:
            bad.append((n, 'ref refused', str(exc)))
            continue
        except EmuError as exc:
            bad.append((n, 'emu', str(exc)[:80]))
            continue
        problems = diff(rig.snap(), ref_snap(d, rig))
        if problems or norm(rig.log) != d.log or ran_emu != host.ran or rig.unexpected:
            bad.append((n, problems[:3], (norm(rig.log), d.log) if norm(rig.log) != d.log else '',
                        (ran_emu, host.ran) if ran_emu != host.ran else '', rig.unexpected[:3]))
    # refusal: recall countdown or mission menu running releases the mutex and returns
    for recall, menu in ((5, False), (0, True)):
        host, nodes = make_conversation(rng, 2)
        rig = Rig(elf, host, nodes)
        make_world(rng, rig, host)
        host.recall, host.mission_menu = recall, menu
        rig.plant_world()
        rig.mem.w32(A['mutex'], 1)
        rig.message(R.start_message('npc', 0, 1, 0, (0, 0, 0), 0, 0))
        d = R.Dialog()
        d.mutex = 1
        ok = d.on_open(host, R.start_message('npc', 0, 1, 0, (0, 0, 0), 0, 0), nodes)
        if ok or rig.mem.s32(A['mutex']) != 0 or rig.mem.u32(A['data']) or norm(rig.log) != d.log:
            bad.append(('refusal', recall, menu, norm(rig.log)))
    # overlap: 11 and 12 visible choices write the text length 0x8e2d48 and reveal 0x8e2d4c
    for count in (11, 12):
        host = R.Host()
        host.texts = {'t': [0x41] * 30, 'nm': [], 'c': [0x42]}
        nodes = [R.Node('', 't', 'v', '', [R.Choice('c', '', '', -1) for _ in range(count)])]
        rig = Rig(elf, host, nodes)
        o = R.Object(0, flags=0x20, props={'showname': 'nm'})
        rig.place(o)
        host.objects['npc'] = [o]
        rig.plant_world()
        rig.mem.w8(A['anm_ready'], 1)
        rig.message(R.start_message('npc', 0, 0, 0, (0, 0, 0), 0, 0))
        got = (rig.mem.s32(A['nvis']), rig.mem.s32(A['text_len']), rig.mem.s32(A['reveal']))
        want = (count, 10, 11 if count == 12 else 0)
        try:
            R.Dialog().on_open(host, R.start_message('npc', 0, 0, 0, (0, 0, 0), 0, 0), nodes)
            refused = False
        except ValueError:
            refused = True
        if got != want or not refused:
            bad.append(('overlap', count, got, want, refused))
    report('open', not bad, '%d conversations + 2 refusals + 2 overlaps%s'
           % (cases, '' if not bad else ' ' + repr(bad[:2])))


def suite_messages(elf, rng, cases):
    """Messages 1-4 on states reached by the reference, planted into memory."""
    bad = []
    counts = dict(confirm=0, move=0, end=0, leave=0)
    for n in range(cases):
        try:
            rig, d, host, nodes, _ = open_both(elf, rng)
        except (ValueError, EmuError):
            continue
        for step in range(rng.randint(1, 6)):
            # move the state somewhere interesting, in the reference, then plant it
            d.revealing = rng.choice([0, 1])
            d.reveal_done = rng.choice([0, 1])
            d.at_end = rng.choice([0, 1, 1])
            d.more = rng.choice([0, 0, 1])
            d.blend = rng.choice([C.ONE, C.ONE, C.ZERO, C.f32(0.5)])
            d.scroll = rng.choice([0, 5, 76, d.total])
            d.scroll_target = rng.choice([d.scroll, d.scroll + 5])
            if d.visible:
                d.cursor = rng.randrange(len(d.visible))
            d.closing = rng.choice([0, 0, 1])
            d.next_world = rng.choice(['', '', 'lvl%d' % step])
            d.store_pending = rng.choice([0, 0, 1])
            d.anm_ready = 1
            rig.plant_state(d)
            rig.log = []
            d.log = []
            host.ran = []
            kind = rng.choice(['confirm', 'confirm', 'move', 'end', 'leave'])
            counts[kind] += 1
            try:
                if kind == 'confirm':
                    rig.message([R.MSG_CONFIRM])
                    ran_emu = list(host.ran)
                    host.ran = []
                    d.on_confirm(host)
                elif kind == 'move':
                    delta = rng.choice([-1, 1, 2, -3])
                    rig.message([R.MSG_MOVE, delta & 0xFF])
                    ran_emu = list(host.ran)
                    d.on_move(host, delta)
                elif kind == 'end':
                    rig.message([R.MSG_END])
                    ran_emu = list(host.ran)
                    d.on_end(host)
                else:
                    rig.message([R.MSG_LEAVE])
                    ran_emu = list(host.ran)
                    d.on_leave(host)
            except ValueError as exc:
                bad.append((n, step, kind, 'ref', str(exc)))
                break
            except EmuError as exc:
                bad.append((n, step, kind, 'emu', str(exc)[:80]))
                break
            problems = diff(rig.snap(), ref_snap(d, rig))
            if kind == 'end' and d.pending_world is not None:
                if rig.mem.cstr(A['pending_world']) != d.pending_world or rig.mem.u8(A['orient']) != 0xFF:
                    problems.append(('pending_world', rig.mem.cstr(A['pending_world']), d.pending_world))
            if problems or norm(rig.log) != d.log or ran_emu != host.ran or rig.unexpected:
                bad.append((n, step, kind, problems[:3], norm(rig.log)[:6], d.log[:6], rig.unexpected[:2]))
                break
            if d.node is None:
                break
    report('messages', not bad, '%s%s' % (counts, '' if not bad else ' ' + repr(bad[:2])))


def random_io(rng):
    return R.TickIO(camera=[rng.choice([0, 0, 1, 2]) for _ in range(4)] + [1],
                    look=rng.choice([C.f32(-0.3), C.f32(-0.55), C.f32(-0.9), C.ZERO]),
                    held_ready=[rng.choice([0, 1])], queue_count=[rng.choice([0, 1, 2])],
                    stream_position=[rng.choice([0, 0, 5, -1])], stream_status=[rng.choice([0, 0, 1])],
                    fade=rng.choice([C.ONE, C.ZERO, C.f32(0.36)]), text_option=rng.choice([1, 1, 0]),
                    shown=rng.randrange(0, 60))


def clone_io(io):
    return R.TickIO(camera=list(io._camera), look=io.look, held_ready=list(io._held),
                    queue_count=list(io._queue), stream_position=list(io._pos),
                    stream_status=list(io._status), fade=io.fade, text_option=io.text_option,
                    shown=io.shown)


def tick_both(rig, d, host, io, rng=None):
    rig.mem.w32(G_FADE, io.fade)
    rig.mem.w32(G_OPTION, io.text_option)
    rig.mem.w32(G_LOOK_BASE + 0x20, io.look)
    rig.mem.w32(G_SHOP_OPEN, host.shop_open)
    eio = clone_io(io)
    rig.io = eio
    rig.measuring = True
    rig.log = []
    d.log = []
    try:
        rig.call(F_RUN)
    finally:
        rig.measuring = False
        rig.io = None
    d.tick(host, io)
    return eio


def suite_tick(elf, rng, cases):
    bad = []
    ticks = 0
    for n in range(cases):
        try:
            rig, d, host, nodes, _ = open_both(elf, rng)
        except (ValueError, EmuError):
            continue
        host.pause_menu = rng.random() < 0.1
        host.raw_pad = {0: 0, 1: 0}
        for step in range(rng.randint(5, 40)):
            # perturb state the reference reached so the branches all get visited
            if rng.random() < 0.3:
                d.cam_move = rng.choice([0, 1, -1])
                d.swoop_done = rng.choice([0, 1])
                d.hold = rng.choice([0, 1])
                d.anm_ready = rng.choice([0, 1, 1])
                d.talking = rng.choice([0, 1])
                d.closing = rng.choice([0, 0, 1])
                d.end_sent = rng.choice([0, 1])
                d.blend = rng.choice([C.ONE, C.ZERO, C.f32(0.9)])
                d.cursor_target = rng.randrange(max(len(d.visible), 1))
                host.shop_open = rng.choice([0, 0, 1])
                ob = host.player_obj.get(0)
                if ob is not None and rng.random() < 0.2:
                    ob.flags ^= 8
                    rig.sync_object(ob)
                rig.plant_state(d)
            host.raw_pad[0] = rng.choice([0, 0, host.confirm_mask, 0x1000, 0x4000, 0x100000, 0x200000,
                                          0x1000 | host.confirm_mask])
            host.raw_pad[1] = rng.choice([0, host.confirm_mask])
            rig.plant_world()
            io = random_io(rng)
            try:
                eio = tick_both(rig, d, host, io)
            except EmuError as exc:
                bad.append((n, step, 'emu', str(exc)[:90]))
                break
            ticks += 1
            problems = diff(rig.snap(with_text=False), ref_snap(d, rig, with_text=False))
            if problems or norm(rig.log) != d.log or eio.asked != io.asked or rig.unexpected:
                bad.append((n, step, problems[:3], norm(rig.log)[:8], d.log[:8], eio.asked, io.asked,
                            rig.unexpected[:2]))
                break
    report('tick', not bad, '%d ticks%s' % (ticks, '' if not bad else ' ' + repr(bad[:1])))


def suite_draw(elf, rng, cases):
    bad = []
    draws = 0
    for n in range(cases):
        try:
            rig, d, host, nodes, _ = open_both(elf, rng)
        except (ValueError, EmuError):
            continue
        for step in range(rng.randint(1, 5)):
            d.cam_move = rng.choice([0, 0, 0, 1])
            d.drawn = rng.choice([0, 1])
            d.reveal_done = rng.choice([0, 1, 1])
            d.revealing = rng.choice([0, 1])
            d.at_end = rng.choice([0, 1, 1])
            d.more = rng.choice([0, 0, 1])
            d.hold = rng.choice([0, 0, 1])
            d.closing = rng.choice([0, 1])
            d.blend = rng.choice([C.ONE, C.ZERO, C.f32(rng.random())])
            if d.visible:
                d.cursor = rng.randrange(len(d.visible))
                d.cursor_target = rng.randrange(len(d.visible))
            d.name_len = rng.randrange(0, len(d.name) + 1)
            d.scroll = rng.randrange(0, 300)
            ap = rng.choice([0, 0, 1])
            d.active_player = ap
            rig.plant_state(d)
            fade = C.f32(rng.choice([0.0, 0.12, 0.5, 0.96, 1.0]))
            opt = rng.choice([1, 1, 0])
            glyph = rng.randrange(1, 256)
            status = rng.choice([0, 0, 1])
            rig.mem.w32(G_FADE, fade)
            rig.mem.w32(G_OPTION, opt)
            rig.mem.w8(G_GLYPH, glyph)
            rig.io = R.TickIO(stream_status=[status])
            rig.log = []
            d.log = []
            try:
                rig.call(F_DRAW)
            except EmuError as exc:
                bad.append((n, step, 'emu', str(exc)[:90]))
                break
            finally:
                eio, rig.io = rig.io, None
            rio = R.TickIO(stream_status=[status])
            ops = d.draw(host, fade, opt, glyph, rio.stream_status)
            draws += 1
            problems = diff(rig.snap(with_text=False), ref_snap(d, rig, with_text=False))
            if problems or norm(rig.log) != ops or eio.asked != rio.asked or rig.unexpected:
                if os.environ.get('DIFFTEST_DEBUG'):
                    print('debug', dict(at_end=d.at_end, hold=d.hold, opt=opt, status=status,
                                        reveal_done=d.reveal_done, more=d.more, vis=d.visible,
                                        mem_hold=rig.mem.s8(A['hold']), asked=(eio.asked, rio.asked)))
                bad.append((n, step, problems[:3], [x for x in norm(rig.log) if x not in ops][:4],
                            [x for x in ops if x not in norm(rig.log)][:4], rig.unexpected[:2]))
                break
    report('draw', not bad, '%d draws%s' % (draws, '' if not bad else ' ' + repr(bad[:1])))


def suite_free(elf, rng, cases):
    bad = []
    for n in range(cases):
        try:
            rig, d, host, nodes, _ = open_both(elf, rng)
        except (ValueError, EmuError):
            continue
        rig.log = []
        d.log = []
        rig.call(F_FREE)
        d.free()
        problems = diff(rig.snap(with_text=False), ref_snap(d, rig, with_text=False))
        if problems or norm(rig.log) != d.log:
            bad.append((n, problems[:3]))
    report('free', not bad, '%d cases%s' % (cases, '' if not bad else ' ' + repr(bad[:2])))


def suite_interact(elf, rng, cases):
    bad = []
    seen = {}
    for n in range(cases):
        host = R.Host()
        host.local = {0} if rng.random() < 0.8 else {1}
        rig = Rig(elf, host)
        props = {}
        if rng.random() < 0.8:
            props['dialogscript'] = rng.choice(['talk', 'nosuch'])
        if rng.random() < 0.3:
            props['shop'] = rng.choice(['1', '0', '2'])
        obj = R.Object(0, x=rng.uniform(-200, 200), y=rng.uniform(-200, 200),
                       facing=rng.randrange(0x10000), props=props,
                       display_name=rng.choice([1, 1, 1, 0]))
        rig.place(obj)
        p = R.Object(0, x=rng.uniform(-200, 200), y=rng.uniform(-200, 200))
        rig.place(p)
        host.player_obj = {0: p if rng.random() < 0.9 else None}
        host.scripts = {'talk': 0}
        rig.plant_world()
        mutex = rng.choice([0, 0, 1])
        flag = rng.choice([0, 1])
        rig.emu.stub(0x1EC140, ret=flag, name='net_anyAlivePlayerFlag800000')
        rig.mem.w32(A['mutex'], mutex)
        rig.mem.w32(A['active_player'], 3)
        d = R.Dialog()
        d.mutex = mutex
        d.active_player = 3
        trig = rng.random() < 0.3
        host.ran = []
        if trig:
            rig.call(F_TRIGGER, obj.addr)
            ran_emu = list(host.ran)
            host.ran = []
            what = d.trigger(host, obj)
        else:
            rig.call(F_INTERACT, obj.addr, 0)
            ran_emu = list(host.ran)
            host.ran = []
            what = d.interact(host, obj, 0, bool(flag))
        seen[what] = seen.get(what, 0) + 1
        got = (rig.mem.s32(A['mutex']), rig.mem.s32(A['active_player']), norm(rig.log), ran_emu)
        want = (d.mutex, d.active_player, d.log, host.ran)
        if got != want or rig.unexpected:
            bad.append((n, trig, what, got, want, rig.unexpected[:2]))
    report('interact', not bad, '%s%s' % (dict(sorted(seen.items())), '' if not bad else ' ' + repr(bad[:2])))


def suite_builtins(elf, rng, cases):
    bad = []
    for n in range(cases):
        host = R.Host()
        host.network = rng.random() < 0.4
        host.local = rng.choice([{0}, {1}, {0, 1}])
        host.alive = rng.choice([[0], [0, 1], [1, 0]])
        host.num_players = 2
        host.recall = rng.choice([0, 0, 3])
        rig = Rig(elf, host)
        rig.plant_world()
        rig.first_active = rng.choice([0, 1])
        is_open = rng.random() < 0.5
        rig.mem.w32(A['data'], 0x1234 if is_open else 0)
        ap = rng.choice([0, 1])
        rig.mem.w32(A['active_player'], ap)
        d = R.Dialog()
        d.node = 0 if is_open else None
        d.active_player = ap
        params = rig.emu.alloc(32)
        kind = rng.choice(['store', 'menu', 'swoop', 'swoopdone', 'next', 'running', 'release', 'startDialog'])
        val = rng.choice([0, 3, 20, 21, -1, 7])
        rig.mem.w32(params + 4, val & 0xFFFFFFFF)
        rig.mem.w32(params + 8, rng.randrange(0, 3))
        rig.mem.w32(params + 12, rng.randrange(0, 3))
        rig.mem.w32(A['mutex'], 1)
        d.mutex = 1
        rig.mem.w16(A['store_index'], 0x7777)
        ret = None
        if kind == 'store':
            rig.call(B_STORE, 0, params)
            d.activate_store(host, val)
            want_idx = d.store_index if d.store_index is not None else 0x7777
            if C.s16(rig.mem.u16(A['store_index'])) != C.s16(want_idx):
                bad.append((n, kind, 'store index'))
        elif kind == 'menu':
            rig.call(B_MISSION_MENU, 0, params)
            d.activate_mission_menu(host, rig.first_active)
        elif kind == 'swoop':
            rig.call(B_SWOOP, 0, params)
            d.change_swoop(val)
        elif kind == 'swoopdone':
            rig.call(B_SWOOP_DONE, 0, params)
            d.start_with_swoop_done()
        elif kind == 'next':
            name = rig.cstr('lvl%d' % n)
            rig.mem.w32(params + 4, name)
            rig.call(B_NEXT_WORLD, 0, params)
            d.new_world_post('lvl%d' % n)
        elif kind == 'running':
            ret = rig.call(B_RUNNING, 0, params)
            if (ret != 0) != d.is_open:
                bad.append((n, kind, ret))
        elif kind == 'release':
            rig.call(B_FORCE_RELEASE, 0, params)
            d.mutex_release()
        else:
            name = rig.cstr('npc%d' % (n % 7))
            rig.mem.w32(params + 4, name)
            for i in range(3):
                rig.mem.w32(G_CAMERA_POS + 4 * i, C.f32(i * 10.5))
            rig.call(B_START, 0, params)
            d.log.append(('lump_load', rig.level + '.lmp'))
            d.start(host, 'npc%d' % (n % 7), rig.mem.s32(params + 8), rig.mem.s32(params + 12),
                    [C.f32(i * 10.5) for i in range(3)], 0, 0)
        got = (rig.mem.s32(A['swoop']), rig.mem.s32(A['swoop_done']), rig.mem.s32(A['store_pending']),
               rig.mem.s32(A['mutex']), rig.mem.cstr(A['next_world']), rig.log)
        want = (s32(d.swoop), d.swoop_done, d.store_pending, d.mutex, d.next_world, d.log)
        if got != want or rig.unexpected:
            bad.append((n, kind, got, want, rig.unexpected[:2]))
    report('builtins', not bad, '%d cases%s' % (cases, '' if not bad else ' ' + repr(bad[:2])))


def suite_sequence(elf, rng, cases):
    """Whole conversations: open, then ticks with pads, messages fed back to both sides
    as they were sent, draws, until the dialog closes or 400 ticks pass."""
    bad = []
    closed = ticks = 0
    for n in range(cases):
        try:
            rig, d, host, nodes, _ = open_both(elf, rng)
        except (ValueError, EmuError):
            continue
        host.raw_pad = {0: 0}
        for t in range(400):
            host.raw_pad[0] = rng.choice([0, 0, 0, host.confirm_mask, 0x1000, 0x4000])
            rig.plant_world()
            io = R.TickIO(camera=[rng.choice([0, 1])], fade=C.f32(min(1.0, 0.12 * (t % 10))),
                          stream_status=[rng.choice([0, 0, 1])], held_ready=[1],
                          queue_count=[t % 3], stream_position=[t % 2], text_option=1,
                          shown=rng.randrange(0, 200))
            d.anm_ready = 1
            rig.mem.w8(A['anm_ready'], 1)
            try:
                eio = tick_both(rig, d, host, io)
                sent = [x[1] for x in d.log if x[0] == 'send']
                for msg in sent:
                    host.ran = []
                    rig.log = []
                    rig.message(msg)
                    ran_emu = list(host.ran)
                    host.ran = []
                    d.log = []
                    d.on_message(host, msg)
                    if ran_emu != host.ran or norm(rig.log) != d.log:
                        raise AssertionError(('message', msg, norm(rig.log), d.log, ran_emu, host.ran))
            except ValueError:
                break
            except (EmuError, AssertionError) as exc:
                bad.append((n, t, str(exc)[:200]))
                break
            ticks += 1
            problems = diff(rig.snap(), ref_snap(d, rig))
            if problems:
                bad.append((n, t, problems[:3]))
                break
            if d.node is None:
                closed += 1
                break
    report('sequence', not bad, '%d ticks, %d conversations closed%s'
           % (ticks, closed, '' if not bad else ' ' + repr(bad[:1])))


def suite_mouth(elf, rng, cases):
    """dialog_startTalkAnim and dialog_syncMouth with the animation calls stubbed."""
    bad = []
    seen = dict(talk=0, line=0, none=0, nudge=0, still=0)
    for n in range(cases):
        host = R.Host()
        rig = Rig(elf, host)
        emu, mem = rig.emu, rig.mem
        emu.follow |= {F_TALK_ANIM, F_SYNC_MOUTH}
        emu.unhook(F_TALK_ANIM)
        emu.unhook(F_SYNC_MOUTH)
        f = R.Object(0, anim_count=rng.randint(0, 4))
        rig.place(f)
        f.tracks = [C.f32(rng.uniform(0, 600)) for _ in range(8)]
        for i in range(8):
            mem.w32(f.addr + 0x134 + 0x20 * i, f.tracks[i])
        f.flag20_track = rng.choice([-1000000000, 0, 1, 2]) if f.anim_count else -1000000000
        if f.flag20_track >= 0 and f.flag20_track >= f.anim_count:
            f.flag20_track = 0
        d = R.Dialog()
        d.focus = f if rng.random() < 0.9 else None
        mem.w32(A['focus'], f.addr if d.focus else 0)
        d.cur_buf = rng.choice([0, 1])
        mem.w8(A['cur_buf'], d.cur_buf)
        b = d.buffers[d.cur_buf]
        b['has'] = rng.choice([0, 1])
        b['vag'] = rng.randrange(0, 0x40000)
        base = A['buffers'] + 16 * d.cur_buf
        mem.w32(base, 0x00DEF000)
        mem.w32(base + 4, b['has'])
        mem.w32(base + 12, b['vag'])
        d.idle_anim = rng.choice([0, 9])
        mem.w32(A['idle_anim'], d.idle_anim)
        host.role_anims[(f.addr, 'talk')] = rng.choice([0, 11])
        d.last_position = rng.choice([0, 0x5000])
        mem.w32(0x4FDCE0, d.last_position)
        d.nudge = rng.choice([C.ZERO, R.NUDGE])
        mem.w32(A['nudge'], d.nudge)
        log = rig.log
        st = emu.stub
        st(0x16CFE0, function=lambda e: log.append(('anim_start', e.f[12], (e.r[4] - 0x114) & 0xFFFFFFFF,
                                                    'line' if (e.r[5] & 0xFFFFFFFF) == 0x00DEF000 else s32(e.r[5]),
                                                    s32(e.r[6]))), name='anim_start')
        st(0x1707B8, function=lambda e: log.append(('anm_relocate',)), name='anm_relocate')
        st(0x170938, function=lambda e: log.append(('anim_chain', (e.r[4] - 0x114) & 0xFFFFFFFF, s32(e.r[5]),
                                                    s32(e.r[6]))), name='anim_pushChained')
        st(0x171178, function=lambda e: f.flag20_track & 0xFFFFFFFFFFFFFFFF, name='anim_findTrackByFlag')
        pos = rng.choice([d.last_position, 0x400, rng.randrange(0, 0x80000)])
        st(0x216480, function=lambda e: pos, name='audio_streamPosition')
        which = rng.choice(['talk', 'sync'])
        if which == 'talk':
            rig.call(F_TALK_ANIM)
            store = d.talk_anim(host)
            kind = 'none' if not log else ('line' if b['has'] else 'talk')
            seen[kind] += 1
            if store is not None and mem.u32(f.addr + store[0]) != store[1]:
                bad.append((n, 'store', hex(mem.u32(f.addr + store[0])), hex(store[1])))
        else:
            rig.call(F_SYNC_MOUTH)
            d.sync_mouth(host, lambda: pos)
            seen['nudge' if not C.eq(d.nudge, C.ZERO) else 'still'] += 1
            got = [mem.u32(f.addr + 0x134 + 0x20 * i) for i in range(8)]
            if got != f.tracks or mem.u32(A['nudge']) != d.nudge or mem.s32(0x4FDCE0) != s32(d.last_position):
                bad.append((n, 'sync', got[:3], f.tracks[:3], hex(mem.u32(A['nudge'])), hex(d.nudge)))
        if norm(log) != d.log or rig.unexpected:
            bad.append((n, which, norm(log), d.log, rig.unexpected[:2]))
    report('mouth', not bad, '%s%s' % (seen, '' if not bad else ' ' + repr(bad[:2])))


def find_elf(argv):
    for a in argv:
        if not a.startswith('--') and os.path.isfile(a):
            return a
    for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'local', 'SLUS_209.73'),
              HOME_ELF):
        if os.path.isfile(p):
            return p
    return None


def main(argv):
    seed, cases = 20973, 60
    for i, a in enumerate(argv):
        if a == '--seed':
            seed = int(argv[i + 1])
        if a == '--cases':
            cases = int(argv[i + 1])
    elf = find_elf([a for i, a in enumerate(argv) if i == 0 or argv[i - 1] not in ('--seed', '--cases')])
    if elf is None:
        print('difftest_dialog: no SLUS_209.73 found; nothing to compare (exit 0)')
        return 0
    import hashlib
    sha = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if sha != ELF_SHA:
        print('difftest_dialog: %s is not US v2.00 (sha256 %s)' % (elf, sha))
        return 0
    C.set_fpu('ps2')
    print('difftest_dialog: seed %d, %d cases per suite' % (seed, cases))
    for suite in (suite_message, suite_open, suite_messages, suite_tick, suite_draw, suite_free,
                  suite_interact, suite_builtins, suite_mouth, suite_sequence):
        rng = random.Random('%d/%s' % (seed, suite.__name__))
        try:
            suite(elf, rng, cases)
        except Exception as exc:          # a harness error is a failure, not a crash
            import traceback
            traceback.print_exc()
            report(suite.__name__[6:], False, 'harness error %r' % exc)
    failed = [n for n, ok in RESULTS if not ok]
    print('difftest_dialog: %d suites, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
