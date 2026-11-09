#!/usr/bin/env python3
"""ref_dialog_system.py - the general machinery around the NPC dialog machine.

Adds to tools/ref_dialog.py (which it imports and does not change):

  1. Scripts       the post-action slot and the deferred-call queue
                   script_setPostAction 0x1eda9c, script_runPostAction 0x1edac0,
                   script_queueDeferred 0x1ed52c, script_runDeferred 0x1ed5a0,
                   script_clearDeferred 0x1eda08, script_resetState 0x1eda78,
                   and the built-ins postAction 0x143ee4, addDeferedCall 0x144160,
                   callScript 0x143158
  2. Programs      a tiny stand-in for level-script entries: each entry is a list of
                   operations that call the built-ins above and the dialog built-ins, so a
                   test can say "this choice action sets a post action and opens a shop"
  3. Session       ref_dialog.Dialog with the end handler (message 3) running the real
                   post action, and offline game messages delivered at once
                   (net_sendGameMsg 0x13db38: offline it calls the channel handler from the
                   table at 0x5d1498 at once, 0x13db64-0x13db78)
  4. input_map     which pad bits of the pressed word the run task turns into messages

No game data is used or produced: names are neutral ids made up by the tests.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_dialog as R  # noqa: E402

# ---- addresses (for the difftest and the document) --------------------------------------
POST_NAME = 0x86FA80        # g_scriptPostAction, a C string; empty = none
IN_POST = 0x4F8698          # g_scriptInPostAction, byte, 1 while the post action runs
DEFER_NAMES = 0x86B278      # g_scriptDeferNames: 2 halves x 64 names x 0x50 bytes
DEFER_RUN_COUNT = 0x86DA78  # names in the front half (run this frame)
DEFER_QUEUED = 0x86DA7C     # names in the back half (queued for the next frame)
DEFER_FLIP = 0x4F8690       # parity: front half = flip & 1
DEFER_MAX = 64
DEFER_NAME = 0x50
HALF = DEFER_MAX * DEFER_NAME   # 0x1400

UP_BITS, DOWN_BITS = R.UP_BITS, R.DOWN_BITS
DEFAULT_USE = 0x80          # g_btnUse[slot] after config_setDefaults(-1): options +0x40 + 0x24 slot
CONFIRM_LAYOUT = {1: 0x40, 0: 0x20}     # g_btnConfirmMask by the layout byte 0x41b69c
CANCEL_LAYOUT = {1: 0x20, 0: 0x140}     # g_btnCancelMask (docs/spec/dialog-gaps.md section 5)


# =======================================================================================
# 1. The post-action slot and the deferred queue
# =======================================================================================

class Scripts:
    """The script launcher state.  run(name) is the host's script_runByName; it returns
    the entry's result (-1 for a missing name, as ref_dialog.MISSING_ENTRY)."""

    def __init__(self):
        self.post = ''                          # 0x86fa80
        self.in_post = 0                        # 0x4f8698
        self.halves = [[''] * DEFER_MAX, [''] * DEFER_MAX]   # memory contents of 0x86b278
        self.run_count = 0                      # 0x86da78
        self.queued = 0                         # 0x86da7c
        self.flip = 0                           # 0x4f8690

    # script_setPostAction 0x1eda9c: strcpy into the slot (a second call replaces)
    def set_post(self, name):
        self.post = name

    # script_runPostAction 0x1edac0
    def run_post(self, run):
        """If a name is set: copy it to the stack, clear the slot, run the copy with the
        in-post byte set, clear the byte.  A postAction() made by the post action itself
        is therefore kept for the next call, not run now."""
        if not self.post:
            return None
        name, self.post = self.post, ''
        self.in_post = 1
        try:
            run(name)
        finally:
            self.in_post = 0
        return name

    # script_queueDeferred 0x1ed52c
    def queue(self, name):
        """Append to the back half ((flip & 1) ^ 1); a name past the 64th of a frame is
        dropped without notice (the count is not incremented either)."""
        if self.queued < DEFER_MAX:
            self.halves[(self.flip & 1) ^ 1][self.queued] = name
            self.queued += 1
            return True
        return False

    # script_runDeferred 0x1ed5a0 (run task "Script", priority 125)
    def run_deferred(self, run):
        """Run front-half names 0 .. run_count-1 in order.  The count and the parity are
        re-read after every name, so a clear made by a deferred entry stops the loop.
        Then flip += 1, run_count = queued, queued = 0."""
        i = 0
        while i < self.run_count:
            run(self.halves[self.flip & 1][i])
            i += 1
        self.flip = (self.flip + 1) & 0xFFFFFFFF
        self.run_count, self.queued = self.queued, 0

    # script_clearDeferred 0x1eda08
    def clear(self):
        self.run_count = self.queued = self.flip = 0

    # script_resetState 0x1eda78
    def reset(self):
        self.clear()
        self.post = ''

    def words(self):
        return dict(post=self.post, in_post=self.in_post, run_count=self.run_count,
                    queued=self.queued, flip=self.flip)


# =======================================================================================
# 2. Programs: neutral stand-ins for level-script entries
# =======================================================================================
#
# An entry is a list of operations.  The value an entry returns is the value of its last
# 'ret' or 'call' operation (0 when it has neither), as script_runByName returns the
# interpreter's result.
#
#   ('ret', v)              return value v
#   ('post', name)          postAction(name)          built-in 0x143ee4, returns 0
#   ('defer', name)         addDeferedCall(name)      built-in 0x144160, returns 0
#   ('call', name)          callScript(name)          built-in 0x143158, its result
#   ('store', index)        activateStore(index)      built-in 0x144010
#   ('start', npc, a, b)    startDialog(npc, a, b)    built-in 0x143824
#   ('running',)            dialogRunning()           built-in 0x143cb0 (result recorded)
#   ('nextworld', name)     newWorldPost(name)        built-in 0x143cc4
#   ('clear',)              script_clearDeferred      (stands for a level teardown)

OPS = ('ret', 'post', 'defer', 'call', 'store', 'start', 'running', 'nextworld', 'clear')


class Session:
    """Dialog + Scripts + programs, with the message delivery of an offline game (at
    once) or a net game (recorded, delivered by the test).

    Every entry started is recorded in self.runs as (name, sentinel) where sentinel is
    the state an entry can observe when it starts (see sentinel())."""

    MAX_DEPTH = 8

    def __init__(self, host, nodes, programs, level='level'):
        self.host = host
        self.nodes = nodes
        self.level = level
        self.programs = programs
        self.d = SessionDialog(self)
        self.s = Scripts()
        self.runs = []
        self.observed = []          # dialogRunning results, in order
        self.depth = 0
        self.cam = (0, 0, 0)
        host.run_script = self.run   # conditions and actions of the dialog come here

    def sentinel(self):
        d, s = self.d, self.s
        return (d.mutex, 1 if d.is_open else 0, d.hud_suppressed, d.store_pending & 0xFF,
                s.in_post, s.post, s.run_count, s.queued, d.pending_world or '')

    # script_runByName 0x1ed694, with the program table as the level script
    def run(self, name):
        self.runs.append((name, self.sentinel()))
        prog = self.programs.get(name)
        if prog is None:
            return R.MISSING_ENTRY
        if self.depth >= self.MAX_DEPTH:
            raise ValueError('program nesting too deep')
        self.depth += 1
        try:
            result = 0
            for op in prog:
                kind = op[0]
                if kind == 'ret':
                    result = op[1]
                elif kind == 'post':
                    self.s.set_post(op[1])
                elif kind == 'defer':
                    self.s.queue(op[1])
                elif kind == 'call':
                    result = self.run(op[1])
                elif kind == 'store':
                    self.d.activate_store(self.host, op[1])
                elif kind == 'start':
                    self.d.log.append(('lump_load', self.level + '.lmp'))
                    msg = self.d.start(self.host, op[1], op[2], op[3], list(self.cam), 0, 0)
                    if msg is not None:
                        self.deliver(msg)
                elif kind == 'running':
                    self.observed.append(1 if self.d.is_open else 0)
                elif kind == 'nextworld':
                    self.d.new_world_post(op[1])
                elif kind == 'clear':
                    self.s.clear()
                else:
                    raise ValueError('unknown op %r' % (kind,))
            return result
        finally:
            self.depth -= 1

    def deliver(self, msg):
        """net_sendGameMsg: offline the handler runs now; online the bytes wait for the
        test (self.outbox)."""
        if not self.host.network:
            self.d.on_message(self.host, bytes(msg), self.nodes, self.level)
        else:
            self.outbox.append(bytes(msg))

    outbox = None

    def message(self, msg):
        return self.d.on_message(self.host, bytes(msg), self.nodes, self.level)

    def frame_deferred(self):
        self.s.run_deferred(self.run)


class SessionDialog(R.Dialog):
    """ref_dialog.Dialog whose message 3 runs the session's post action at the point the
    original calls script_runPostAction (0x22f7f0), so what follows it (the deferred shop,
    the remote fade) sees what the post action left."""

    def __init__(self, session):
        R.Dialog.__init__(self)
        self.session = session

    def on_end(self, host):
        if self.node is None:          # g_dialogData == 0: the message does nothing
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
        self.log.append(('far_clip', R.CLIP_FAR_CLOSE))
        if self.next_world:
            self.pending_world = self.next_world
            self.orient = 0xFF
        self.session.s.run_post(self.session.run)
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
            self.log.append(('fade_wait', R.FADE_WAIT_FRAMES))


# =======================================================================================
# 4. The input map of the run task
# =======================================================================================

def input_map(pressed, confirm_mask, blend_one=True, gate_open=True, paused=False):
    """Messages dialog_runTask sends from one pressed word (pad +0x0c, newly pressed
    this tick; no auto-repeat), in send order: up (2, -1), down (2, +1), confirm (1).
    gate_open: not closing (or the fade below 1.0) and the voice gate passed.  The
    pause menu running zeroes the word.  Cancel, start and every other bit send
    nothing."""
    if paused or not gate_open:
        return []
    out = []
    if blend_one and pressed & UP_BITS:
        out.append(bytes((R.MSG_MOVE, 0xFF)))
    if blend_one and pressed & DOWN_BITS:
        out.append(bytes((R.MSG_MOVE, 0x01)))
    if pressed & confirm_mask:
        out.append(bytes((R.MSG_CONFIRM,)))
    return out
