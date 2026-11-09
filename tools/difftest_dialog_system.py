#!/usr/bin/env python3
"""difftest_dialog_system.py - the machinery around the NPC dialog, original vs reference.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_dialog_system.py [path/to/SLUS_209.73] [--seed N] [--cases N]

Compares tools/ref_dialog_system.py (and tools/ref_dialog.py, tools/ref_netwire.py, which
it reuses unchanged) with the original functions run in tools/ee_emu.py.  The rig is the
one of tools/difftest_dialog.py, with these changes (all disclosed in the report):

  * script_runByName 0x1ed694 is a recording stub that plays a neutral "program" for the
    entry name by calling the ORIGINAL built-ins nested (postAction 0x143ee4,
    addDeferedCall 0x144160, callScript 0x143158, activateStore 0x144010, startDialog
    0x143824, dialogRunning 0x143cb0, newWorldPost 0x143cc4, script_clearDeferred
    0x1eda08).  At every entry it records the sentinel words an entry can see: menu mutex
    0x4fe53c, g_dialogData 0x8e2d60 != 0, g_hudSuppressed 0x4f66a8, pending store
    0x4fdd30, in-post byte 0x4f8698, post-action name 0x86fa80, deferred counts
    0x86da78 / 0x86da7c.
  * script_runPostAction 0x1edac0, script_setPostAction 0x1eda9c, the deferred queue
    0x1ed52c / 0x1ed5a0 / 0x1eda08 / 0x1eda78 run as they are (the dialog rig stubs the
    first; here it is followed).
  * net_sendGameMsg 0x13db38 is a recording stub; offline it then calls dialog_onMsg at
    once, which is what the original's offline branch does (suite `send` runs that
    branch of the original to show it).
  * pad_apply 0x174410 (with pad_decodeStick 0x174ce0) runs as it is in suite `input`,
    writing the raw pad that dialog_runTask reads.

Suites: send, queue, endchain, input, sametick, defaults.
"""
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EmuError  # noqa: E402
import ref_core as C  # noqa: E402
import ref_dialog as R  # noqa: E402
import ref_dialog_system as S  # noqa: E402
import ref_netwire as NW  # noqa: E402
import difftest_dialog as D  # noqa: E402

A = D.A
B_POST, B_DEFER, B_CALL = 0x143EE4, 0x144160, 0x143158
F_SET_POST, F_RUN_POST = 0x1EDA9C, 0x1EDAC0
F_QUEUE, F_RUN_DEFERRED, F_CLEAR_DEFERRED, F_RESET = 0x1ED52C, 0x1ED5A0, 0x1EDA08, 0x1EDA78
F_RUN_BY_NAME = 0x1ED694
F_SEND = 0x13DB38
F_PAD_APPLY, F_DECODE_STICK = 0x174410, 0x174CE0
F_SET_DEFAULTS = 0x1E6238
SEND_TABLE = 0x5D1498       # offline handler table of net_sendGameMsg (0x13db6c-0x13db74)
RAW_PADS = 0x4028D0         # g_rawPads; dialog_runTask reads +0x0c (pressed) at 0x4028dc
PAD_START_BLOCK, PAD_MUTE = 0x41BFC0, 0x41C138
G_CANCEL = 0x41BFB8
OPTIONS = 0x4F8F38          # options block; controller rows at +0x34 + 0x24 * slot
SCRIPT_FOLLOW = {B_POST, B_DEFER, B_CALL, F_SET_POST, F_RUN_POST, F_QUEUE, F_RUN_DEFERRED,
                 F_CLEAR_DEFERRED, F_RESET}

RESULTS = []


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %-10s %s' % ('PASS' if ok else 'FAIL', name, detail))


s32 = D.s32


def nested(emu, addr, *args):
    """Call an original function from inside a stub and put the CPU back as it was."""
    saved = (list(emu.r), list(emu.rh), list(emu.f), emu.hi, emu.lo, emu.hi1, emu.lo1, emu.sa,
             emu.acc, emu.fcr31, emu.pc, emu.npc, emu.cur, emu._pending_call, emu._fresh_call,
             emu._call_site)
    sp = ((emu.r[29] & 0xFFFFFFFF) - 0x1000) & ~0xF
    try:
        return emu.call(addr, *args, sp=sp, max_steps=2000000)
    finally:
        (r, rh, f, emu.hi, emu.lo, emu.hi1, emu.lo1, emu.sa, emu.acc, emu.fcr31, emu.pc, emu.npc,
         emu.cur, emu._pending_call, emu._fresh_call, emu._call_site) = saved
        emu.r[:], emu.rh[:], emu.f[:] = r, rh, f


class SysRig(D.Rig):
    """The dialog rig with the script launcher real and programs behind script_runByName."""

    def __init__(self, elf, host, nodes=None, programs=None):
        D.Rig.__init__(self, elf, host, nodes)
        emu, mem = self.emu, self.mem
        emu.follow |= SCRIPT_FOLLOW
        emu.hooks.pop(F_RUN_POST, None)          # the dialog rig records it; here it runs
        emu.stub_names.pop(F_RUN_POST, None)
        self.programs = programs or {}
        self.runs = []
        self.observed = []
        self.depth = 0
        emu.stub(F_RUN_BY_NAME, function=self._run_by_name, name='script_runByName')
        emu.stub(F_SEND, function=self._send, name='net_sendGameMsg')

    def cstr(self, text):
        """As the dialog rig's, but at least 0x50 bytes long: the scr_getString stub copies
        64 bytes, and a short block at the end of the test heap would end on an unmapped
        page."""
        if text not in self.cstr_cache:
            data = text.encode('latin1') + b'\0'
            p = self.emu.alloc(max(len(data) + 4, 0x50))
            self.mem.write(p, data)
            self.cstr_cache[text] = p
        return self.cstr_cache[text]

    def sentinel(self):
        m = self.mem
        return (m.s32(A['mutex']), 1 if m.u32(A['data']) else 0, m.s8(A['hud']),
                m.u8(A['store_pending']), m.u8(S.IN_POST), m.cstr(S.POST_NAME),
                m.s32(S.DEFER_RUN_COUNT), m.s32(S.DEFER_QUEUED), m.cstr(A['pending_world']))

    def params(self, *words):
        p = self.emu.alloc(32)
        for i, w in enumerate(words):
            self.mem.w32(p + 4 + 4 * i, w & 0xFFFFFFFF)
        return p

    def builtin(self, addr, *words):
        """Run a built-in nested, the way the interpreter calls it: (vm, params)."""
        return nested(self.emu, addr, 0, self.params(*words))

    def _run_by_name(self, e):
        name = self.mem.cstr(e.r[4]) if e.r[4] else None
        if name is None:
            return R.MISSING_ENTRY & 0xFFFFFFFFFFFFFFFF
        self.runs.append((name, self.sentinel()))
        prog = self.programs.get(name)
        if prog is None:
            return R.MISSING_ENTRY & 0xFFFFFFFFFFFFFFFF
        result = 0
        for op in prog:
            kind = op[0]
            if kind == 'ret':
                result = op[1]
            elif kind == 'post':
                self.builtin(B_POST, self.cstr(op[1]))
            elif kind == 'defer':
                self.builtin(B_DEFER, self.cstr(op[1]))
            elif kind == 'call':
                result = s32(self.builtin(B_CALL, self.cstr(op[1])))
            elif kind == 'store':
                self.builtin(D.B_STORE, op[1])
            elif kind == 'start':
                self.builtin(D.B_START, self.cstr(op[1]), op[2], op[3])
            elif kind == 'running':
                self.observed.append(1 if self.builtin(D.B_RUNNING) & 0xFFFFFFFF else 0)
            elif kind == 'nextworld':
                self.builtin(D.B_NEXT_WORLD, self.cstr(op[1]))
            elif kind == 'clear':
                nested(self.emu, F_CLEAR_DEFERRED)
        return result & 0xFFFFFFFFFFFFFFFF

    def _send(self, e):
        data = bytes(self.mem.read(e.r[5] & 0xFFFFFFFF, s32(e.r[6])))
        self.log.append(('send', data))
        if not self.host.network:                # 0x13db64-0x13db78: the handler, at once
            buf = self.emu.alloc(len(data) + 16)
            self.mem.write(buf, data)
            nested(self.emu, D.F_ON_MSG, buf, len(data))
        else:
            self.outbox.append(data)
        return 0

    outbox = None

    def script_words(self):
        m = self.mem
        halves = [[m.cstr(S.DEFER_NAMES + h * S.HALF + i * S.DEFER_NAME) for i in range(S.DEFER_MAX)]
                  for h in range(2)]
        return dict(post=m.cstr(S.POST_NAME), in_post=m.u8(S.IN_POST),
                    run_count=m.s32(S.DEFER_RUN_COUNT), queued=m.s32(S.DEFER_QUEUED),
                    flip=m.u32(S.DEFER_FLIP)), halves


def ref_words(s):
    return s.words(), [list(h) for h in s.halves]


def norm(log):
    return [t for t in log if t[0] not in D.EXTERNAL]


# ======================================================================================
# send: the original net_sendGameMsg offline calls the handler at once
# ======================================================================================

def suite_send(elf, rng, cases):
    bad = []
    for n in range(cases):
        host = R.Host()
        rig = D.Rig(elf, host)
        emu = rig.emu
        emu.hooks.pop(F_SEND, None)
        emu.follow.add(F_SEND)
        got = []
        handler = rig._code_stub(lambda e: got.append(
            (bytes(rig.mem.read(e.r[4] & 0xFFFFFFFF, s32(e.r[5]))), s32(e.r[5]))))
        channel = rng.randrange(0, 16)
        rig.mem.w32(SEND_TABLE + 4 * channel, handler)
        data = bytes(rng.randrange(256) for _ in range(rng.randint(1, 24)))
        buf = emu.alloc(len(data) + 8)
        rig.mem.write(buf, data)
        rig.mem.w8(D.G_NET, 0)
        rig.call(F_SEND, channel, buf, len(data))
        if got != [(data, len(data))] or rig.unexpected:
            bad.append((n, got, rig.unexpected[:2]))
    report('send', not bad, '%d offline sends reach the channel handler at once%s'
           % (cases, '' if not bad else ' ' + repr(bad[:1])))


# ======================================================================================
# queue: post-action slot, deferred queue and callScript, no dialog
# ======================================================================================

def random_programs(rng, names):
    """Programs for names[i] may call names[j] only for j > i (no unbounded recursion);
    they may post or defer any name."""
    progs = {}
    for i, name in enumerate(names):
        prog = []
        for _ in range(rng.randint(0, 4)):
            r = rng.random()
            if r < 0.25:
                prog.append(('post', rng.choice(names + ['nosuch'])))
            elif r < 0.5:
                prog.append(('defer', rng.choice(names + ['nosuch'])))
            elif r < 0.65 and i + 1 < len(names):
                prog.append(('call', rng.choice(names[i + 1:] + ['nosuch'])))
            elif r < 0.72:
                prog.append(('clear',))
            else:
                prog.append(('ret', rng.choice([0, 1, 2, -3])))
        progs[name] = prog
    return progs


def suite_queue(elf, rng, cases):
    bad = []
    stats = dict(ops=0, runs=0, dropped=0, nested_post=0)
    for n in range(cases):
        names = ['e%d_%d' % (n, i) for i in range(rng.randint(2, 7))]
        progs = random_programs(rng, names)
        host = R.Host()
        rig = SysRig(elf, host, programs=progs)
        sess = S.Session(R.Host(), [], progs)
        for step in range(rng.randint(4, 30)):
            op = rng.choice(['post', 'runpost', 'defer', 'frame', 'frame', 'call', 'clear', 'reset',
                             'flood'])
            rig.runs, sess.runs = [], []
            stats['ops'] += 1
            try:
                if op == 'post':
                    nm = rng.choice(names)
                    rig.call(B_POST, 0, rig.params(rig.cstr(nm)))
                    sess.s.set_post(nm)
                elif op == 'runpost':
                    rig.call(F_RUN_POST)
                    sess.s.run_post(sess.run)
                elif op == 'defer':
                    nm = rng.choice(names)
                    rig.call(B_DEFER, 0, rig.params(rig.cstr(nm)))
                    sess.s.queue(nm)
                elif op == 'flood':
                    for k in range(rng.randint(60, 70)):
                        nm = names[k % len(names)]
                        rig.call(B_DEFER, 0, rig.params(rig.cstr(nm)))
                        if not sess.s.queue(nm):
                            stats['dropped'] += 1
                elif op == 'frame':
                    rig.call(F_RUN_DEFERRED)
                    sess.frame_deferred()
                elif op == 'call':
                    nm = rng.choice(names + ['nosuch'])
                    got = s32(rig.call(B_CALL, 0, rig.params(rig.cstr(nm))))
                    want = sess.run(nm)
                    if got != want:
                        raise AssertionError(('callScript result', nm, got, want))
                elif op == 'clear':
                    rig.call(F_CLEAR_DEFERRED)
                    sess.s.clear()
                else:
                    rig.call(F_RESET)
                    sess.s.reset()
            except (EmuError, AssertionError, ValueError) as exc:
                bad.append((n, step, op, str(exc)[:160]))
                break
            stats['runs'] += len(sess.runs)
            stats['nested_post'] += sum(1 for _nm, sen in sess.runs if sen[4] == 1)
            if rig.runs != sess.runs or rig.script_words() != ref_words(sess.s) or rig.unexpected:
                bad.append((n, step, op, rig.runs[:4], sess.runs[:4], rig.script_words()[0],
                            sess.s.words(), rig.unexpected[:2]))
                break
    report('queue', not bad, '%s%s' % (stats, '' if not bad else ' ' + repr(bad[:1])))


# ======================================================================================
# endchain: choice actions, the end message, the post action, chained dialogs
# ======================================================================================

def make_chain(rng, n):
    """A conversation whose choice actions and the post actions they set use the
    built-ins; some post actions open the next conversation."""
    host = R.Host()
    k = rng.randint(1, 3)
    names = ['p%d_%d' % (n, i) for i in range(5)]
    progs = random_programs(rng, names)
    for name in names:                          # some entries also touch the dialog
        prog = progs[name]
        r = rng.random()
        if r < 0.25:
            prog.insert(0, ('start', 'npc', rng.choice([0, 1]), 0))
        elif r < 0.45:
            prog.append(('store', rng.choice([0, 5, 20, 21])))
        elif r < 0.6:
            prog.append(('nextworld', 'lv%d' % rng.randrange(3)))
        if rng.random() < 0.5:
            prog.append(('running',))
    nodes = []
    for j in range(k):
        choices = []
        for i in range(rng.choice([0, 1, 2, 3])):
            act = 'a%d_%d_%d' % (n, j, i)
            progs[act] = ([('post', rng.choice(names))] if rng.random() < 0.7 else []) + \
                ([('defer', rng.choice(names))] if rng.random() < 0.3 else []) + \
                ([('store', rng.choice([0, 3]))] if rng.random() < 0.3 else []) + \
                ([('running',)] if rng.random() < 0.5 else []) + \
                ([('start', 'npc', 0, 0)] if rng.random() < 0.15 else [])
            cond = rng.choice(['', '', 'c%d_%d_%d' % (n, j, i)])
            if cond:
                progs[cond] = [('ret', rng.choice([0, 1, 1]))]
            choices.append(R.Choice('ch%d_%d' % (j, i), cond, act, rng.choice([-1, -1] + list(range(k)))))
            host.texts['ch%d_%d' % (j, i)] = D.wide_text(rng, rng.randint(1, 10))
        nodes.append(R.Node('', 'tx%d' % j, 'v0', '', choices))
        host.texts['tx%d' % j] = D.wide_text(rng, rng.randint(0, 40))
    if n % 3 == 0:                              # directed: the post action opens the next
        nodes[0] = R.Node('', 'tx0', 'v0', '', [R.Choice('ch0_0', '', 'go%d' % n, -1)])  # store pending
        host.texts['ch0_0'] = [0x41]
        progs['go%d' % n] = [('store', 4), ('post', 'chain%d' % n), ('running',)]
        progs['chain%d' % n] = [('running',), ('start', 'npc', n % 2, 0), ('running',),
                                ('post', 'after%d' % n)]
        progs['after%d' % n] = [('defer', 'later%d' % n)]
    elif n % 3 == 1:                            # directed: the closing choice defers a reward
        nodes[0] = R.Node('', 'tx0', 'v0', '', [R.Choice('ch0_0', '', 'give%d' % n, -1)])
        host.texts['ch0_0'] = [0x41]
        progs['give%d' % n] = [('defer', 'reward%d' % n)]
        progs['reward%d' % n] = [('running',), ('store', 2), ('post', 'late%d' % n)]
    else:                                       # directed: a level request, then the post action
        nodes[0] = R.Node('', 'tx0', 'v0', '', [R.Choice('ch0_0', '', 'leave%d' % n, -1)])
        host.texts['ch0_0'] = [0x41]
        progs['leave%d' % n] = [('nextworld', 'lv%d' % (n % 3)), ('post', 'travel%d' % n)]
        progs['travel%d' % n] = [('running',)]
    host.texts['Affirmation'] = [0x4F, 0x4B]
    host.texts['dialogMore'] = [0x4D, 0x6F]
    host.texts['nm'] = D.wide_text(rng, 6)
    host.vag_length['v0.vag'] = 0x800
    host.layout_height = 19
    return host, nodes, progs


def clone_host(h):
    c = R.Host()
    for k, v in vars(h).items():
        if isinstance(v, dict):
            v = dict(v)
        elif isinstance(v, (list, set)):
            v = type(v)(v)
        setattr(c, k, v)
    return c


def suite_endchain(elf, rng, cases):
    bad = []
    stats = dict(confirms=0, ends=0, dup_ends=0, dup_closed_new=0, posts_run=0, posts_saw_level=0, chained_opens=0, shops=0,
                 shops_lost=0, frames=0, deferred_open=0, deferred_closed=0)
    for n in range(cases):
        host, nodes, progs = make_chain(rng, n)
        host.network = rng.random() < 0.3
        host.local = {0}
        rhost = clone_host(host)
        rig = SysRig(elf, host, nodes, progs)
        rig.outbox = []
        world = D.make_world(random.Random(n), rig, host)
        rhost.objects = {'npc': world}
        rhost.player_obj = dict(host.player_obj)
        rhost.role_anims = dict(host.role_anims)
        rhost.num_players = host.num_players
        rig.plant_world()
        sess = S.Session(rhost, nodes, progs)
        sess.outbox = []
        sess.d.active_player = 0
        rig.mem.w32(A['active_player'], 0)
        rig.mem.w32(A['mutex'], 1)                  # taken by Creature_interact
        sess.d.mutex = 1
        msg = R.start_message('npc', 0, 0, 0, [0, 0, 0], 0, 0)
        rig.log, sess.d.log = [], []
        try:
            rig.message(msg)
            sess.message(msg)
        except (EmuError, ValueError) as exc:
            bad.append((n, 'open', str(exc)[:120]))
            continue
        for step in range(rng.randint(3, 12)):
            d = sess.d
            if n % 3 == 0 and step < 2:
                ev = ('confirm', 'end')[step]
            elif n % 3 == 1 and step < 4:
                ev = ('confirm', 'frame', 'frame', 'end')[step]
            elif n % 3 == 2 and step < 2:
                ev = ('confirm', 'end')[step]
            else:
                ev = rng.choice(['confirm', 'confirm', 'end', 'end', 'frame', 'deliver', 'dup'])
            rig.log, d.log, rig.runs, sess.runs = [], [], [], []
            rig.observed, sess.observed = [], []
            try:
                if ev == 'confirm':
                    if d.node is None:
                        continue
                    d.revealing, d.reveal_done, d.at_end, d.more, d.blend = 0, 1, 1, 0, C.ONE
                    d.cursor = rng.randrange(max(1, len(d.visible)))
                    d.cam_move = 0
                    rig.plant_state(d)
                    rig.message(bytes((R.MSG_CONFIRM,)))
                    sess.message(bytes((R.MSG_CONFIRM,)))
                    stats['confirms'] += 1
                elif ev in ('end', 'dup'):
                    was_open = d.node is not None
                    pending = d.store_pending
                    rig.message(bytes((R.MSG_END,)))
                    sess.message(bytes((R.MSG_END,)))
                    if ev == 'dup':                  # a second machine's copy of message 3
                        reopened = d.node is not None
                        rig.message(bytes((R.MSG_END,)))
                        sess.message(bytes((R.MSG_END,)))
                        stats['dup_ends'] += 1
                        stats['dup_closed_new'] += 1 if (reopened and d.node is None) else 0
                    stats['ends'] += 1 if was_open else 0
                    stats['posts_run'] += sum(1 for _nm, sen in sess.runs if sen[4] == 1)
                    stats['posts_saw_level'] += sum(1 for _nm, sen in sess.runs if sen[4] == 1 and sen[8])
                    shop = any(t[0] == 'shop' for t in d.log)
                    stats['shops'] += 1 if shop else 0
                    stats['shops_lost'] += 1 if (was_open and pending and not shop) else 0
                elif ev == 'frame':
                    rig.call(F_RUN_DEFERRED)
                    sess.frame_deferred()
                    stats['frames'] += 1
                    stats['deferred_open'] += sum(1 for _nm, sen in sess.runs if sen[1] == 1)
                    stats['deferred_closed'] += sum(1 for _nm, sen in sess.runs if sen[1] == 0)
                else:
                    if not sess.outbox:
                        continue
                    m0 = sess.outbox.pop(0)
                    m1 = rig.outbox.pop(0)
                    if m0 != m1:
                        raise AssertionError(('outbox', m0, m1))
                    rig.message(m1)
                    sess.message(m0)
                stats['chained_opens'] += sum(1 for t in d.log if t[0] == 'freeze_all')
            except (EmuError, ValueError, AssertionError) as exc:
                if isinstance(exc, ValueError) and 'reads address' in str(exc):
                    break
                bad.append((n, step, ev, str(exc)[:200]))
                break
            problems = D.diff(rig.snap(with_text=False), D.ref_snap(d, rig, with_text=False))
            if (problems or norm(rig.log) != norm(d.log) or rig.runs != sess.runs
                    or rig.observed != sess.observed or rig.script_words() != ref_words(sess.s)
                    or rig.unexpected):
                bad.append((n, step, ev, problems[:3], norm(rig.log)[:6], norm(d.log)[:6],
                            rig.runs[:3], sess.runs[:3], rig.unexpected[:2]))
                break
    report('endchain', not bad, '%s%s' % (stats, '' if not bad else ' ' + repr(bad[:1])))


# ======================================================================================
# input: pad_apply -> raw pad -> dialog_runTask, held buttons over several ticks
# ======================================================================================

PATTERNS = [
    ('confirm', dict(buttons=0x40)), ('confirm_l0', dict(buttons=0x20, mask=0x20)), ('cross_l0', dict(buttons=0x40, mask=0x20)),
    ('dpad_up', dict(buttons=0x1000)), ('dpad_down', dict(buttons=0x4000)),
    ('stick_up', dict(stick_y=0)), ('stick_down', dict(stick_y=255)),
    ('cancel_exe', dict(buttons=0x120)), ('cancel_l0', dict(buttons=0x140, mask=0x20)), ('cancel_l1', dict(buttons=0x20)),
    ('use_default', dict(buttons=0x80)), ('start', dict(buttons=0x800)), ('select', dict(buttons=0x1)),
    ('triangle', dict(buttons=0x10)), ('shoulders', dict(buttons=0x0F00 & ~0x800)),
    ('dpad_lr', dict(buttons=0x2000 | 0x8000)), ('all', dict(buttons=0xFFFF)),
]


def record_for(pattern, held):
    buttons = pattern.get('buttons', 0) if held else 0
    sy = pattern.get('stick_y', 128) if held else 128
    # pad_readPort's record keeps buttons active-high here (pad_apply reads them as stored)
    return struct.pack('<H6B', buttons, 128, sy, 128, 128, 0, 0) + bytes(4)


def suite_input(elf, rng, cases):
    bad = []
    tally = {}
    for n in range(cases):
        try:
            rig, d, host, nodes, _ = D.open_both(elf, rng)
        except (ValueError, EmuError):
            continue
        emu = rig.emu
        emu.follow |= {F_PAD_APPLY, F_DECODE_STICK}
        slot = 0
        rig.mem.w32(PAD_START_BLOCK, 0)
        rig.mem.w32(PAD_MUTE, 0)
        prev_addr, rec_addr = emu.alloc(8), emu.alloc(16)
        prev = [0, 0]
        model_pad = bytearray(rig.mem.read(RAW_PADS + slot * 0x58, 0x58))
        name, pat = PATTERNS[n % len(PATTERNS)]
        host.confirm_mask = pat.get('mask', 0x40)
        rig.mem.w32(D.G_CONFIRM, host.confirm_mask)
        hold = rng.randint(2, 30)
        sched = [False] * rng.randint(0, 3) + [True] * hold + [False] * rng.randint(1, 4)
        d.cam_move = 0
        d.revealing, d.reveal_done, d.at_end, d.more, d.blend = 0, 1, 1, 0, C.ONE
        rig.plant_state(d)
        sent_kinds = []
        for t, held in enumerate(sched):
            rec = record_for(pat, held)
            rig.mem.write(rec_addr, rec)
            rig.mem.write(prev_addr, struct.pack('<II', *prev))
            try:
                rig.call(F_PAD_APPLY, RAW_PADS + slot * 0x58, rec_addr, prev_addr)
                NW.pad_apply(model_pad, rec, prev, NW.PadGlobals(0, 0, 0))
                got_word = rig.mem.u32(RAW_PADS + slot * 0x58 + 0xC)
                want_word = struct.unpack_from('<I', model_pad, 0xC)[0]
                if got_word != want_word:
                    raise AssertionError(('pressed word', hex(got_word), hex(want_word)))
                host.raw_pad[slot] = want_word
                io = R.TickIO(camera=[1], fade=C.ONE, held_ready=[1], queue_count=[0],
                              stream_position=[0], stream_status=[0], text_option=1, shown=100000)
                ap_before = rig.mem.s32(A["active_player"])
                d.anm_ready = 1
                rig.mem.w8(A['anm_ready'], 1)
                D.tick_both(rig, d, host, io)
                sent = [x[1] for x in d.log if x[0] == 'send']
                emu_sent = [x[1] for x in rig.log if x[0] == 'send']
                if sent != emu_sent:
                    raise AssertionError(('sends', emu_sent, sent))
                if not host.network and ap_before == slot and d.node is not None and not d.closing and \
                        any(m[0] == R.MSG_CONFIRM for m in sent) != bool(want_word & host.confirm_mask):
                    raise AssertionError(('confirm map', hex(want_word), sent))
                for msg in sent:
                    sent_kinds.append((t, msg))
                    rig.log, d.log = [], []
                    rig.message(msg)
                    d.on_message(host, msg)
                    if norm(rig.log) != d.log:
                        raise AssertionError(('message', msg, norm(rig.log), d.log))
            except ValueError:
                break
            except (EmuError, AssertionError) as exc:
                bad.append((n, name, t, str(exc)[:200]))
                break
            problems = D.diff(rig.snap(with_text=False), D.ref_snap(d, rig, with_text=False))
            if problems or rig.unexpected:
                bad.append((n, name, t, problems[:3], rig.unexpected[:2]))
                break
            if d.node is None:
                break
        per = tally.setdefault(name, [0, 0, 0])
        per[0] += 1
        per[1] += sum(1 for _t, m in sent_kinds if m[0] == R.MSG_CONFIRM)
        per[2] += sum(1 for _t, m in sent_kinds if m[0] == R.MSG_MOVE)
        if len([1 for _t, m in sent_kinds if m[0] == R.MSG_CONFIRM]) > 1 or \
                len([1 for _t, m in sent_kinds if m[0] == R.MSG_MOVE and m[1] == 0xFF]) > 1 or \
                len([1 for _t, m in sent_kinds if m[0] == R.MSG_MOVE and m[1] == 0x01]) > 1:
            bad.append((n, name, 'more than one message of a kind for one held press', sent_kinds))
    detail = ' '.join('%s=%d/%d/%d' % (k, v[0], v[1], v[2]) for k, v in sorted(tally.items()))
    report('input', not bad, '[presses/confirms/moves] %s%s' % (detail, '' if not bad else ' ' + repr(bad[:1])))


# ======================================================================================
# sametick: offline, the press that opens a dialog and the run task in the same tick
# ======================================================================================

def suite_sametick(elf, rng, cases):
    bad = []
    tally = {}
    for n in range(cases):
        swoop = n % 2
        press = [S.DEFAULT_USE, 0x40, 0x40 | S.DEFAULT_USE][(n // 2) % 3]
        host, nodes = D.make_conversation(rng)
        host.network = False
        host.local = {0}
        rig = D.Rig(elf, host, nodes)
        D.make_world(rng, rig, host)
        rig.plant_world()
        d = R.Dialog()
        msg = R.start_message('npc', 0, swoop, 0, [0, 0, 0], 0, 0)
        try:
            rig.mem.w8(A['anm_ready'], 1)
            rig.message(msg)
            d.on_open(host, msg, nodes)
        except (ValueError, EmuError):
            continue
        host.raw_pad[0] = press
        rig.mem.w32(D.G_RAW_PAD, press)
        io = R.TickIO(camera=[0], fade=C.ONE, held_ready=[1], queue_count=[0], stream_position=[0],
                      stream_status=[0], text_option=1, shown=0)
        try:
            D.tick_both(rig, d, host, io)
            sent = [x[1] for x in d.log if x[0] == 'send']
            if sent != [x[1] for x in rig.log if x[0] == 'send']:
                raise AssertionError(('sends', sent))
            for m in sent:
                rig.message(m)
                d.on_message(host, m)
        except (EmuError, AssertionError, ValueError) as exc:
            bad.append((n, str(exc)[:160]))
            continue
        problems = D.diff(rig.snap(with_text=False), D.ref_snap(d, rig, with_text=False))
        if problems or rig.unexpected:
            bad.append((n, problems[:3]))
        key = 'swoop%d/press%#x' % (swoop, press)
        t = tally.setdefault(key, [0, 0, 0])
        t[0] += 1
        t[1] += sum(1 for m in sent if m[0] == R.MSG_CONFIRM)
        t[2] += 1 if (d.node is not None and d.reveal_done and not d.revealing) else 0
    detail = ' '.join('%s=%d/%d/%d' % (k, v[0], v[1], v[2]) for k, v in sorted(tally.items()))
    report('sametick', not bad, '[opens/confirms/typewriter skipped] %s%s'
           % (detail, '' if not bad else ' ' + repr(bad[:1])))


# ======================================================================================
# defaults: the use button the options give every slot, against confirm and cancel
# ======================================================================================

def suite_defaults(elf, rng, cases):
    from ee_emu import EE
    e = EE(elf)
    e.default_ret = 0
    e.call(F_SET_DEFAULTS, 0xFFFFFFFFFFFFFFFF, max_steps=3000000)
    use = [e.mem.u32(OPTIONS + 0x40 + 0x24 * s) for s in range(4)]
    confirm, cancel, layout = e.mem.u32(D.G_CONFIRM), e.mem.u32(G_CANCEL), e.mem.u8(0x41B69C)
    ok = (use == [S.DEFAULT_USE] * 4 and confirm == S.CONFIRM_LAYOUT[1] and layout == 1
          and not any(u & confirm for u in use)
          and all(not (u & S.CONFIRM_LAYOUT[0]) for u in use))
    report('defaults', ok, 'use word per slot %s, executable confirm %#x cancel %#x layout byte %d'
           % ([hex(u) for u in use], confirm, cancel, layout))


def main(argv):
    seed, cases = 20973, 40
    for i, a in enumerate(argv):
        if a == '--seed':
            seed = int(argv[i + 1])
        if a == '--cases':
            cases = int(argv[i + 1])
    elf = D.find_elf([a for i, a in enumerate(argv) if i == 0 or argv[i - 1] not in ('--seed', '--cases')])
    if elf is None:
        print('difftest_dialog_system: no SLUS_209.73 found; nothing to compare (exit 0)')
        return 0
    import hashlib
    sha = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if sha != D.ELF_SHA:
        print('difftest_dialog_system: the executable is not US v2.00 (sha256 %s)' % sha)
        return 0
    C.set_fpu('ps2')
    print('difftest_dialog_system: seed %d, %d cases per suite' % (seed, cases))
    for suite in (suite_send, suite_queue, suite_endchain, suite_input, suite_sametick, suite_defaults):
        rng = random.Random('%d/%s' % (seed, suite.__name__))
        try:
            suite(elf, rng, cases)
        except Exception as exc:          # a harness error is a failure, not a crash
            import traceback
            traceback.print_exc()
            report(suite.__name__[6:], False, 'harness error %r' % exc)
    failed = [n for n, ok in RESULTS if not ok]
    print('difftest_dialog_system: %d suites, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
