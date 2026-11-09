#!/usr/bin/env python3
"""HUD feeds, round 3, against the original SLUS-20973 v2.00 functions.

  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_hud_feeds.py local/SLUS_209.73 --seed 20973

Census: every direct jal / j to hud_showMessage 0x1d92a0 in .text, with its containing
function from ghidra_funcs.tsv, asserted site by site (pointer calls not covered).

Runs, in tools/ee_emu.py: hud_run 0x1db870 (the level-up panel edge),
menu_openInventory 0x1c15c8 and invmsg_dispatch 0x1bfdb0 (acknowledged level +0x58);
script_setInfo, DoorSwing_interact, Savepoint_interactPrompt, JumpGate_interactPrompt and
itemprop_tryPickup with hud_showMessage 0x1d92a0 followed; the ammunition and thrown
notice starters in Player_run, SkillFireAxe_cast, SkillColdAxe_cast and
Player_weaponSwapInput; the icon registrar 0x1689a4 and the PushTrigger_ctor slice that
feeds it; phase B of the automap drawer 0x168cac with the real vars_get and
script_runByName. In tools/vu1_emu.py: every map-strip packet the drawer builds.

Every stub is named where it is installed. Stores are checked against planted
sentinels or the recorded write list. No game bytes or strings are printed.
"""
import argparse
import dis  # stdlib; tools/dis.py would shadow it once that directory is on the path
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ee_emu import EE
import ref_core as F
import ref_hud_feeds as H

PLAYER, STRIDE, PLAYERS = 0x4D8AF0, 0x4C30, 0x4D8AE0
SEEDS = (0x404460, 0x404464, 0x404468)
RAW_PADS = 0x4028D0
MENU = 0x41B69D
CAMERA = 0x4F8450
CUTSCENE = 0x44FCD0
INPUT_BLOCK = 0x4F66C8
WORD_503890 = 0x503890
RECALL = 0x41B51D
GLOW = 0x86AA50
NETWORK = 0x402791
EXIT_COUNT = 0x4F694A
CHEAT_XP = 0x4F8EE0
TIMER, FORCE, TEXT = 0x4F66E0, 0x4F66E2, 0x86AB78
PANEL_WORD, PANEL_BYTE = 0x4F4090, 0x4F65C8

HUD_RUN, OPEN_INVENTORY, INVMSG_DISPATCH = 0x1DB870, 0x1C15C8, 0x1BFDB0
SHOW_MESSAGE, WIDE_COPY = 0x1D92A0, 0x19E854
NET_IS_LOCAL, SEND_GAME_MSG = 0x13E150, 0x13DB38
PAUSE_OPEN, FROZEN, TRAVEL, TASK_RUNNING = 0x18CBFC, 0x1EBDF8, 0x27DD68, 0x19E5E8
TASK_A, TASK_B = 0x53C5B0, 0x53C280
SCRIPT_RUN, MENU_MUTEX, TEXT_LOOKUP = 0x1ED694, 0x22FC04, 0x173C84


class Fail(AssertionError):
    pass


def check(name, got, want):
    if got != want:
        raise Fail('%s: got %r want %r' % (name, got, want))


def draws(emu):
    return sum(1 for _pc, address, size, _value in emu.writes
               if address in SEEDS and size == 4)


def no_draws(emu, name):
    if draws(emu):
        raise Fail('%s drew a seed' % name)


# ---- 0. hud_showMessage census --------------------------------------------------------
# Every direct jump to hud_showMessage 0x1d92a0 in .text: (site, 'jal' or 'j', start of the
# containing function in ghidra_funcs.tsv). Pointer calls (jalr) are not covered.
SHOW_MESSAGE_SITES = (
    (0x1431C0, 'jal', 0x14318C), (0x143D94, 'jal', 0x143D04), (0x18C2F0, 'jal', 0x18C230),
    (0x18C4B8, 'jal', 0x18C230), (0x1A6EBC, 'jal', 0x1A5030), (0x1A7AF0, 'jal', 0x1A5030),
    (0x1A8040, 'jal', 0x1A5030), (0x1AAFC4, 'jal', 0x1A5030), (0x1D3298, 'jal', 0x1D3150),
    (0x1D8E9C, 'jal', 0x1D8CA0), (0x1DC024, 'jal', 0x1DBC48), (0x1DC054, 'jal', 0x1DBC48),
    (0x1DE3C8, 'j', 0x1DE340), (0x207D7C, 'jal', 0x207C3C), (0x207E40, 'jal', 0x207C3C),
    (0x218210, 'jal', 0x218128), (0x218270, 'jal', 0x218128), (0x218294, 'jal', 0x218128),
    (0x27D600, 'jal', 0x27CB58), (0x27D858, 'jal', 0x27D7A0), (0x28AB88, 'jal', 0x28AA7C),
    (0x28B2F8, 'j', 0x28B268), (0x28D6A0, 'jal', 0x28CDD0), (0x28DB70, 'jal', 0x28DA58),
    (0x28DB94, 'jal', 0x28DA58), (0x2C71CC, 'jal', 0x2C7140), (0x2CFFF8, 'jal', 0x2CFFB8),
    (0x2D0B68, 'jal', 0x2D0A58), (0x2D14F0, 'jal', 0x2D1484), (0x2D29E0, 'jal', 0x2D2984),
    (0x2D6018, 'jal', 0x2D5FC4), (0x2D6D94, 'jal', 0x2D6D40), (0x2D87D0, 'jal', 0x2D877C),
    (0x2D9A6C, 'jal', 0x2D9A18), (0x2DAC84, 'jal', 0x2DAC30), (0x2DE39C, 'jal', 0x2DE334),
    (0x2E6574, 'jal', 0x2E6534), (0x2FAA68, 'jal', 0x2FAA00), (0x3121AC, 'jal', 0x312168),
    (0x312208, 'jal', 0x312168), (0x319778, 'jal', 0x319710), (0x31A0B4, 'jal', 0x31A04C),
    (0x328140, 'j', 0x328090),
)


def elf_text(path):
    """(address, bytes) of the .text section, from the ELF section headers."""
    with open(path, 'rb') as source:
        data = source.read()
    shoff, = struct.unpack_from('<I', data, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 0x2E)

    def header(i):
        return struct.unpack_from('<10I', data, shoff + i * shentsize)
    names = header(shstrndx)[4]
    for i in range(shnum):
        h = header(i)
        name = data[names + h[0]:data.index(b'\0', names + h[0])]
        if name == b'.text':
            return h[3], data[h[4]:h[4] + h[5]]
    raise Fail('no .text section')


def function_ranges():
    """[(start, lo, hi)] from the tracked ghidra_funcs.tsv (a function may list several
    address ranges)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'ghidra_funcs.tsv')
    out = []
    with open(path) as source:
        for line in source:
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 3 or not parts[0][:1].isalnum():
                continue
            start = int(parts[0], 16)
            for span in parts[2].split(','):
                lo, hi = span.split('-')
                out.append((start, int(lo, 16), int(hi, 16)))
    return out


def census_cases(elf, rng):
    base, text = elf_text(elf)
    jal, j = 0x0C000000 | (SHOW_MESSAGE >> 2), 0x08000000 | (SHOW_MESSAGE >> 2)
    ranges = function_ranges()
    found = []
    for off in range(0, len(text) - 3, 4):
        word, = struct.unpack_from('<I', text, off)
        if word in (jal, j):
            site = base + off
            owner = [start for start, lo, hi in ranges if lo <= site <= hi]
            found.append((site, 'jal' if word == jal else 'j', owner[0] if len(owner) == 1 else None))
    check('hud_showMessage census', tuple(found), SHOW_MESSAGE_SITES)
    kinds = [k for _s, k, _f in found]
    check('hud_showMessage census kinds', (kinds.count('jal'), kinds.count('j')), (40, 3))
    census_cases.functions = len({f for _s, _k, f in found})
    return len(found)


# ---- 1. acknowledged level -----------------------------------------------------------
def ack_cases(elf, rng):
    emu = EE(elf)
    emu.follow = set()
    box = {'pause': 0, 'frozen': 0, 'travel': 0, 'tasks': set()}
    emu.stub(PAUSE_OPEN, function=lambda _e: box['pause'], name='pauseMenu_isOpen')
    emu.stub(FROZEN, function=lambda _e: box['frozen'], name='game_isFrozen')
    emu.stub(TRAVEL, function=lambda _e: box['travel'], name='jumpgate_getTravelState')
    emu.stub(TASK_RUNNING, function=lambda e: int((e.r[4] & 0xFFFFFFFF) in box['tasks']),
             name='task_isRunning')
    opened = []
    emu.stub(OPEN_INVENTORY, function=lambda e: opened.append(
        (e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)), name='menu_openInventory (recorded)')
    scripts = []
    emu.stub(SCRIPT_RUN, function=lambda e: scripts.append(e.r[4] & 0xFFFFFFFF) or 0,
             name='script_runByName (recorded)')
    camera = emu.alloc(0x40)
    objects = [emu.alloc(0x600) for _ in range(4)]
    checked = 0

    def run(n, slot, count, blocked, ack, earned, flags=0, health=8.0, bags=(0, 0, 0, 0)):
        nonlocal checked
        mem = emu.mem
        mem.w32(PLAYERS, count)
        mem.w16(EXIT_COUNT, 0)
        mem.w8(NETWORK, 0)
        mem.w8(CHEAT_XP, 0)
        mem.w8(0x4F66D4, 0)
        mem.w8(0x4F66D5, 0)
        mem.w32(CAMERA, camera)
        mem.w32(camera + 0x34, 2 if 'camera_mode' in blocked else 1)
        mem.w8(MENU, int('menu_open' in blocked))
        mem.w8(CUTSCENE, int('cutscene' in blocked))
        mem.w8(INPUT_BLOCK, int('input_block' in blocked))
        mem.w32(WORD_503890, int('word_503890' in blocked))
        mem.w8(RECALL, 60 if 'recall' in blocked else 0)
        box['pause'] = int('pause_menu' in blocked)
        box['frozen'] = int('frozen' in blocked)
        box['travel'] = int('travel' in blocked)
        box['tasks'] = {a for k, a in (('task_a', TASK_A), ('task_b', TASK_B)) if k in blocked}
        for i in range(4):
            pad = RAW_PADS + 0x58 * i
            pressed = i == slot and 'pressed' not in blocked
            mem.w32(pad + 0xC, 0x100 if pressed else 0)
            mem.w32(pad + 0x8, 0x80 if i == slot and 'held_80' in blocked else 0)
            rec = PLAYER + STRIDE * i
            obj = 0 if (i == slot and 'no_object' in blocked) else objects[i]
            mem.w32(rec + 0x43D8, obj)
            if obj:
                mem.w32(obj + 0x540, int(i == slot and 'object_540' in blocked))
                mem.w32(obj + 0xC, (flags | (0x400000 if 'flag_400000' in blocked else 0))
                        if i == slot else 0)
            mem.w8(rec + 0x58, (ack if i == slot else 3) & 0xFF)
            mem.w8(rec + 0x59, (earned if i == slot else 3) & 0xFF)
            mem.wf32(rec + 0xAC, health if i == slot else 5.0)
            mem.w32(rec + 0x1330, bags[i])
            mem.w32(GLOW + 4 * i, 0x5A5A0000 + i)
        opened.clear()
        scripts.clear()
        emu.reset_log()
        emu.call(HUD_RUN)
        want = H.hud_run_open(set(blocked), ack, earned, flags, health > 0)
        got = opened[0][1:] if opened else None
        check('hud_run case %d open' % n, (len(opened), got and (opened[0][0],)),
              (0, None) if want is None else (1, (slot,)))
        if want is not None:
            check('hud_run case %d level_up' % n, got, want)
        glow = [mem.u32(GLOW + 4 * i) for i in range(4)]
        want_glow = [0 if (want == (1,) and i == slot) else 0x5A5A0000 + i for i in range(4)]
        check('hud_run case %d glow' % n, glow, want_glow)
        reached = want is not None or (not blocked and (flags & 8 or health <= 0))
        want_scripts = [0x53C5C0] * sum(1 for b in bags[:count] if b > 0) if reached else []
        check('hud_run case %d bag scripts' % n, scripts, want_scripts)
        acks = [mem.u8(PLAYER + STRIDE * i + 0x58) for i in range(4)]
        check('hud_run case %d ack untouched' % n, acks[slot], ack & 0xFF)
        no_draws(emu, 'hud_run')
        checked += 1

    n = 0
    run(n, 0, 1, (), 1, 2)
    n += 1
    run(n, 0, 1, (), 2, 2)
    n += 1
    run(n, 0, 1, (), 5, 3)
    n += 1
    run(n, 0, 1, (), -128, 1)
    n += 1
    run(n, 1, 2, (), 4, 9)
    n += 1
    run(n, 0, 1, (), 1, 2, flags=8)
    n += 1
    run(n, 0, 1, (), 1, 2, health=0.0)
    n += 1
    run(n, 0, 2, (), 1, 2, bags=(3, 0, 0, 0))
    n += 1
    run(n, 1, 3, (), 1, 1, bags=(1, 2, 0, 0))
    n += 1
    for gate in H.ACK_GATES:
        run(n, 0, 1, (gate,), 1, 2)
        n += 1
    for _ in range(12):
        slot = rng.randrange(4)
        count = rng.randint(slot + 1, 4)
        blocked = tuple(g for g in H.ACK_GATES if rng.random() < 0.08)
        run(n, slot, count, blocked, rng.randrange(-3, 12), rng.randrange(-3, 12),
            flags=rng.choice((0, 0, 8)), health=rng.choice((8.0, 8.0, 0.0, -1.0)),
            bags=tuple(rng.choice((0, 0, 1, 5)) for _ in range(4)))
        n += 1
    return checked


def ack_chain_cases(elf, rng):
    """menu_openInventory(slot, levelUp) on the owner's machine and another machine, then
    the dispatcher on both with the bytes that were sent."""
    checked = 0

    def machine(local):
        emu = EE(elf)
        emu.follow = {OPEN_INVENTORY, INVMSG_DISPATCH}
        emu.stub(NET_IS_LOCAL, ret=int(local), name='net_isLocalSlot')
        emu.stub(MENU_MUTEX, ret=0, name='menuMutex_tryAcquire')
        sent = []
        emu.stub(SEND_GAME_MSG, function=lambda e: sent.append(
            e.mem.read(e.r[5] & 0xFFFFFFFF, e.r[6] & 0xFFFFFFFF)), name='net_sendGameMsg (recorded)')
        return emu, sent

    def run(n, slot, level_up, ack, earned, network=0):
        nonlocal checked
        owner, sent = machine(True)
        other, not_sent = machine(False)
        for emu in (owner, other):
            emu.mem.w8(NETWORK, network)
            emu.mem.w8(MENU, 0)
            for i in range(4):
                rec = PLAYER + STRIDE * i
                emu.mem.w8(rec + 0x58, (ack if i == slot else 0x33) & 0xFF)
                emu.mem.w8(rec + 0x59, (earned if i == slot else 0x44) & 0xFF)
                emu.mem.w8(rec + 0xED, 0x77)
                emu.mem.w8(rec + 0xEE, 0x66)
            emu.mem.w32(PANEL_WORD, 0xA5A5A5A5)
            emu.mem.w8(PANEL_BYTE, 0x5A)
            emu.reset_log()
            emu.call(OPEN_INVENTORY, slot, level_up)
        rec = PLAYER + STRIDE * slot
        want = H.level_ack_message(slot, earned) if level_up else None
        check('open case %d sent' % n, sent, [want] if want else [])
        check('open case %d remote sent' % n, not_sent, [])
        check('open case %d menu byte' % n, (owner.mem.u8(MENU), other.mem.u8(MENU)), (1, 0))
        if level_up:
            check('open case %d +0xed/+0xee' % n,
                  (owner.mem.u8(rec + 0xED), owner.mem.u8(rec + 0xEE)), (slot, 0))
        else:
            check('open case %d +0xed/+0xee' % n,
                  (owner.mem.u8(rec + 0xED), owner.mem.u8(rec + 0xEE)), (0x77, 0x66))
        check('open case %d remote +0xee' % n, other.mem.u8(rec + 0xEE), 0x66)
        # the same branch stores word 5 at 0x4f4090 and byte 1 at 0x4f65c8 (0x1c1834, 0x1c1838)
        check('open case %d panel globals' % n,
              [(e.mem.u32(PANEL_WORD), e.mem.u8(PANEL_BYTE)) for e in (owner, other)],
              [(5, 1) if level_up else (0xA5A5A5A5, 0x5A), (0xA5A5A5A5, 0x5A)])
        before = [(e.mem.u8(rec + 0x58)) for e in (owner, other)]
        check('open case %d ack before dispatch' % n, before, [ack & 0xFF] * 2)
        for emu in (owner, other):
            no_draws(emu, 'menu_openInventory')
        if want:
            target, value = H.apply_level_ack(want)
            for emu in (owner, other):
                buf = emu.alloc(0x10)
                emu.mem.write(buf, want + b'\0')
                emu.reset_log()
                emu.call(INVMSG_DISPATCH, buf)
                acks = [emu.mem.u8(PLAYER + STRIDE * i + 0x58) for i in range(4)]
                want_acks = [value if i == target else 0x33 for i in range(4)]
                if slot != target:
                    raise Fail('dispatch target')
                want_acks[slot] = value
                check('dispatch case %d acks' % n, acks, want_acks)
                stores = sorted({a for _pc, a, size, _v in emu.writes})
                check('dispatch case %d stores' % n, stores, [rec + 0x58])
                no_draws(emu, 'invmsg_dispatch')
        checked += 1

    run(0, 0, 1, 1, 2)
    run(1, 0, 0, 1, 2)
    run(2, 2, 1, 5, 9)
    run(3, 1, 1, 0, 80)
    run(4, 3, 1, -2, 7, network=1)
    for k in range(4):
        run(5 + k, rng.randrange(4), 1, rng.randrange(0, 40), rng.randrange(1, 81),
            network=rng.choice((0, 1)))
    return checked


# ---- 2. message callers ---------------------------------------------------------------
def message_machine(elf, local=True):
    """An interpreter where hud_showMessage and its wide copy run for real."""
    emu = EE(elf)
    emu.follow = {SHOW_MESSAGE, WIDE_COPY}
    emu.stub(NET_IS_LOCAL, ret=int(local), name='net_isLocalSlot')
    text = emu.alloc(8)
    emu.mem.w16(text, 0x43)
    emu.mem.w16(text + 2, 0)
    emu.stub(TEXT_LOOKUP, function=lambda e: (looked.append(e.r[4] & 0xFFFFFFFF), text)[1],
             name='text_lookup (recorded, returns a planted wide string)')
    looked = []
    emu.looked = looked
    return emu


def plant_message(emu, menu=0):
    emu.mem.w16(TIMER, 77)
    emu.mem.w8(FORCE, 9)
    emu.mem.w16(TEXT, 0)
    emu.mem.w8(MENU, menu)


def shown(emu):
    """(timer, force, first text char) and the recorded hud_showMessage arguments."""
    calls = [tuple(F.s32(a & 0xFFFFFFFF) for a in c.args[1:4])
             for c in emu.calls if c.target == SHOW_MESSAGE]
    return (emu.mem.u16(TIMER), emu.mem.u8(FORCE), emu.mem.u16(TEXT)), calls


def stored(frames, force):
    return (frames & 0xFFFF, force & 0xFF, 0x43)


UNSHOWN = (77, 9, 0)


def setinfo_cases(elf, rng):
    emu = message_machine(elf)
    key = emu.alloc(0x40)
    emu.stub(0x1414A8, function=lambda e: e.mem.w32(e.r[6] & 0xFFFFFFFF, key),
             name='scr_getString (writes a planted key pointer)')
    emu.stub(0x141650, ret=0, name='scr_copyString')
    checked = 0
    for n, menu in enumerate((0, 1, 0, 1)):
        plant_message(emu, menu)
        args = emu.alloc(0x10)
        emu.reset_log()
        emu.call(0x14318C, emu.alloc(0x40), args)
        want = H.set_info()
        state, calls = shown(emu)
        check('setInfo %d call' % n, calls, [(want['frames'], want['slot'], want['force'])])
        check('setInfo %d store' % n, state, UNSHOWN if menu else stored(180, 0))
        no_draws(emu, 'setInfo')
        checked += 1
    return checked


def prop_stub(emu, props):
    """obj_getPropStr / obj_getPropInt: answers by key address from props[key]."""
    def answer(e):
        return props.get(e.r[5] & 0xFFFFFFFF, 0)
    emu.stub(0x14F4C0, function=answer, name='obj_getPropStr (by key address)')
    emu.stub(0x14C880, function=answer, name='obj_getPropInt (by key address)')


def door_cases(elf, rng):
    emu = message_machine(elf)
    emu.follow |= {0x3B8534}                    # libc_strcmp runs for real
    props = {}
    prop_stub(emu, props)
    box = {'result': 0}
    emu.stub(SCRIPT_RUN, function=lambda _e: box['result'], name='script_runByName')
    voices, finds = [], []
    emu.stub(0x1B7BA8, function=lambda e: voices.append((F.s32(e.r[4] & 0xFFFFFFFF),
                                                         e.r[5] & 0xFFFFFFFF)), name='player_voice')
    emu.stub(0x17365C, function=lambda e: finds.append((e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)) or 0x1234,
             name='res_find (recorded)')
    emu.stub(0x214230, ret=0, name='sound_playOnObject')
    door = emu.alloc(0x200)
    script = emu.alloc(0x20)
    plain = emu.alloc(0x40)
    emu.mem.write(plain, emu.mem.read(0x549080, 0x20))
    other = emu.alloc(0x40)
    emu.mem.write(other, b'\x7fq\0')
    checked = 0

    def run(n, slot, lock_script, result, sound_prop, sound_plain):
        nonlocal checked
        props.clear()
        if lock_script:
            props[0x549070] = script
        if sound_prop:
            props[0x549078] = plain if sound_plain else other
        box['result'] = result
        voices.clear()
        finds.clear()
        plant_message(emu)
        emu.mem.w32(door + 0xC, 0x00100000 | 0x3)
        emu.mem.w16(door + 0x4C, 0xFFFF)        # no world cell: the open path stops early
        emu.reset_log()
        emu.call(0x28AA7C, door, slot)   # sign-extended, as a register holds it
        want = H.door_interact(slot, lock_script, result, sound_prop, sound_plain)
        state, calls = shown(emu)
        if want is None:
            check('door %d calls' % n, calls, [])
            check('door %d store' % n, state, UNSHOWN)
            check('door %d voice' % n, voices, [])
            check('door %d opened (flag 0x100000 cleared)' % n,
                  emu.mem.u32(door + 0xC) & 0x100000, 0)
        else:
            check('door %d calls' % n, calls, [want['message']])
            check('door %d store' % n, state, stored(180, 0))
            check('door %d voice' % n, voices, [want['voice']])
            check('door %d text key' % n, emu.looked[-1], 0x5490C0)
            sound = {None: [], 'named': [(0x549088, 0x549090)],
                     'default': [(0x549088, 0x5490A8)]}[want['sound']]
            check('door %d sound' % n, finds, sound)
            check('door %d still interactable' % n, emu.mem.u32(door + 0xC) & 0x100000, 0x100000)
        no_draws(emu, 'DoorSwing_interact')
        checked += 1

    n = 0
    for slot in (0, 2, -10):
        for lock_script in (False, True):
            for result in (0, 1, -1):
                for sound_prop, sound_plain in ((False, False), (True, True), (True, False)):
                    if not lock_script and (result or sound_prop):
                        continue
                    run(n, slot, lock_script, result, sound_prop, sound_plain)
                    n += 1
    return checked


def savepoint_cases(elf, rng):
    emu = message_machine(elf)
    props = {}
    prop_stub(emu, props)
    box = {'busy': 0, 'state2': 0, 'zone': 0}
    emu.stub(0x217518, function=lambda _e: box['busy'], name='memcard_isBusy')
    emu.stub(0x1EC5D8, function=lambda _e: box['state2'], name='net_allPlayersState2')
    emu.stub(0x1E7B78, function=lambda _e: box['zone'], name='game_inNoSaveZone')
    sp = emu.alloc(0x100)
    buf = emu.alloc(0x200)
    override = emu.alloc(0x20)
    objects = [emu.alloc(0x600) for _ in range(4)]
    checked = 0

    def run(n, busy, state2, zone, flags, has_override, network, frame_word, byte_c7):
        nonlocal checked
        box.update(busy=busy, state2=state2, zone=zone)
        props.clear()
        if has_override:
            props[0x549258] = override
        emu.mem.w32(0x4F8420, len(flags))
        for i, flag in enumerate(flags):
            slot = (i * 3 + 1) % 4
            emu.mem.w32(0x4F8440 + 4 * i, slot)
            emu.mem.w32(PLAYER + STRIDE * slot + 0x43D8, objects[slot])
            emu.mem.w32(objects[slot] + 0x540, int(flag))
        emu.mem.w8(NETWORK, network)
        emu.mem.w32(0x4F8F30, frame_word)
        emu.mem.w8(sp + 0xC7, byte_c7 & 0xFF)
        emu.mem.w16(buf, 0)
        plant_message(emu)
        emu.looked.clear()
        emu.reset_log()
        result = F.s32(emu.call(0x28DA58, sp, buf) & 0xFFFFFFFF)
        want = H.savepoint_prompt(busy, state2, zone, flags, has_override, network,
                                  frame_word, byte_c7)
        state, calls = shown(emu)
        check('savepoint %d result' % n, result, want[0])
        if want[1] is not None:
            check('savepoint %d calls' % n, calls, [(180, -1, 0)])
            check('savepoint %d store' % n, state, stored(180, 0))
            check('savepoint %d key' % n, emu.looked,
                  [override if want[1] == 'override' else want[1]])
        else:
            check('savepoint %d calls' % n, calls, [])
            check('savepoint %d store' % n, state, UNSHOWN)
            check('savepoint %d prompt key' % n, emu.looked, [want[2]] if want[2] else [])
            check('savepoint %d prompt text' % n, emu.mem.u16(buf), 0x43 if want[2] else 0)
        no_draws(emu, 'Savepoint_interactPrompt')
        checked += 1

    n = 0
    for busy, state2 in ((1, 0), (0, 1)):
        run(n, busy, state2, 1, [False], False, 0, 0, 0)
        n += 1
    for flags in ([False], [False, False, False], [True], [False, True], [False, False, True]):
        for has_override in (False, True):
            run(n, 0, 0, 1, flags, has_override, 0, 0, 0)
            n += 1
    for network, frame_word, byte_c7 in ((0, 0, 0), (1, 0x708, -1), (1, 0x709, -1),
                                         (1, 0x709, 0), (1, 0x2000, -1), (0, 0x2000, -1)):
        run(n, 0, 0, 0, [False], False, network, frame_word, byte_c7)
        n += 1
    return checked


def jumpgate_cases(elf, rng):
    emu = message_machine(elf)
    props = {}
    prop_stub(emu, props)
    box = {'task': 0, 'result': 0}
    tasks = []
    emu.stub(TASK_RUNNING, function=lambda e: tasks.append(e.r[4] & 0xFFFFFFFF) or box['task'],
             name='task_isRunning (recorded name pointer)')
    emu.stub(SCRIPT_RUN, function=lambda _e: box['result'], name='script_runByName')
    activated = []
    emu.stub(0x27DB60, function=lambda e: activated.append(1), name='jumpgate_0x27db60 (recorded; takes no argument)')
    gate = emu.alloc(0x200)
    buf = emu.alloc(0x200)
    script = emu.alloc(0x20)
    checked = 0

    def run(n, slot, flag_4f, task, has_script, result, seen, alive_slot):
        nonlocal checked
        box.update(task=task, result=result)
        props.clear()
        if has_script:
            props[0x547E40] = script
        emu.mem.w8(gate + 0x4F, flag_4f)
        emu.mem.w8(gate + 0x4D, seen)
        emu.mem.w32(0x4F8440 + 4 * slot, alive_slot)
        activated.clear()
        tasks.clear()
        plant_message(emu)
        emu.looked.clear()
        emu.reset_log()
        emu.call(0x27D7A0, gate, buf, slot)
        if not flag_4f:
            check('jumpgate %d task name' % n, tasks[:1], [0x547E10])
        want = H.jumpgate_first_prompt(flag_4f, task, has_script, result, seen)
        state, calls = shown(emu)
        if want == 'message':
            check('jumpgate %d calls' % n, calls[:1], [(180, alive_slot, 0)])
            check('jumpgate %d first key' % n, emu.looked[:1], [0x547E90])
            check('jumpgate %d seen byte' % n, emu.mem.u8(gate + 0x4D), 1)
            check('jumpgate %d activation' % n, activated, [1])
            check('jumpgate %d store' % n, state, stored(180, 0))
        else:
            first = [c for c in calls if c == (180, alive_slot, 0)]
            if want in ('stop', 'quiet'):
                check('jumpgate %d no first message' % n,
                      0x547E90 in emu.looked or bool(activated), False)
                check('jumpgate %d seen byte' % n, emu.mem.u8(gate + 0x4D), seen & 0xFF)
            if want == 'stop':
                check('jumpgate %d calls' % n, calls, [])
        no_draws(emu, 'JumpGate_interactPrompt')
        checked += 1

    n = 0
    for flag_4f in (0, 1):
        for task in (0, 1):
            for has_script, result in ((False, 0), (True, 0), (True, 1), (True, -1)):
                for seen in (0, 1):
                    run(n, n % 4, flag_4f, task, has_script, result, seen, -1 if n % 3 else 2)
                    n += 1
    return checked


def pickup_cases(elf, rng):
    emu = message_machine(elf)
    box = {'weight': 0}
    calls = []

    def weight(e):
        e.f[0] = box['weight']
        return 0
    emu.stub(0x1B6338, function=weight, name='item_weight (planted float)')
    for addr, name in ((0x17365C, 'res_find'), (0x214230, 'sound_playOnObject'),
                       (0x3B7EF0, 'sprintf'), (SCRIPT_RUN, 'script_runByName'),
                       (0x1C1868, 'inventory_giveItem'), (0x1BEC10, 'player_0x1bec10'),
                       (0x1B7BA8, 'player_voice')):
        emu.stub(addr, function=(lambda nm: lambda e: calls.append(nm) or args.append(
            (nm, tuple(F.s32(e.r[k] & 0xFFFFFFFF) for k in (4, 5, 6)))) or 0)(name),
            name=name + ' (recorded with a0-a2)')
    args = []
    item = emu.alloc(0x40)
    definition = emu.alloc(0x40)
    emu.mem.w32(item, definition)
    checked = 0

    def run(n, slot, bag, count, load, limit, weight, flags):
        nonlocal checked
        rec = PLAYER + STRIDE * slot
        emu.mem.w8(definition + 0x1D, bag)
        emu.mem.w32(rec + 0x1330 + bag * 0x1208, count)
        emu.mem.wf32(rec + 0x120, load)
        emu.mem.wf32(rec + 0x124, limit)
        box['weight'] = F.f32(weight)
        emu.mem.w64(item + 8, flags)
        calls.clear()
        args.clear()
        plant_message(emu)
        emu.reset_log()
        result = emu.call(0x154DBC, slot, item) & 0xFFFFFFFF
        fits = F.le(F.add(F.f32(load), F.f32(weight)), F.f32(limit))
        want = H.pickup(count + 1 < 64, fits)
        state, shows = shown(emu)
        check('pickup %d result' % n, result, want[0])
        check('pickup %d messages' % n, (shows, state), ([], UNSHOWN))
        effects = {('sound',): ['res_find', 'sound_playOnObject'], ('voice0',): ['player_voice'],
                   ('sound', 'script', 'giveItem', 'after'):
                   ['sprintf', 'res_find', 'sound_playOnObject', 'script_runByName',
                    'inventory_giveItem', 'player_0x1bec10']}[want[1]]
        check('pickup %d calls' % n, calls, effects)
        got = {nm: a for nm, a in args}
        if want[1] == ('voice0',):
            check('pickup %d voice args' % n, got['player_voice'][:2], (slot, 0))
        elif want[1] != ('sound',):
            check('pickup %d script name' % n, got['script_runByName'][0], 0x532678)
            check('pickup %d giveItem args' % n, got['inventory_giveItem'], (slot, F.s32(item), 1))
            check('pickup %d after' % n, got['player_0x1bec10'][0], slot)
        no_draws(emu, 'itemprop_tryPickup')
        checked += 1

    n = 0
    for bag in (0, 1, 2):
        for count, load, limit, weight in ((62, 1.0, 10.0, 1.0), (63, 1.0, 10.0, 1.0),
                                           (0, 9.0, 10.0, 1.0), (0, 9.5, 10.0, 1.0),
                                           (5, 0.0, 0.0, 0.0)):
            for flags in (0, 0x800000, 0x40000, 0x1000000):
                run(n, n % 4, bag, count, load, limit, weight, flags)
                n += 1
    return checked


# ---- 3. ammunition and thrown notices -------------------------------------------------
COUNT_NOTICES = 0x1DACF4


def notice_machine(elf):
    emu = EE(elf)
    emu.follow = set()
    rows = []
    emu.stub(COUNT_NOTICES, function=lambda e: (rows.append(
        (e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)), 0x30 + (e.r[5] & 0xFF))[1],
        name='hud_countActiveNotices (recorded; returns 0x30 + line)')
    voices = []
    emu.stub(0x1B7BA8, function=lambda e: voices.append((e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)),
             name='player_voice (recorded)')
    emu.rows, emu.voices = rows, voices
    emu.P = emu.alloc(0x600)
    emu.ability = emu.alloc(0x40)
    emu.item = emu.alloc(0x40)
    return emu


def plant_notices(emu):
    for slot in range(4):
        for line in range(8):
            emu.mem.w32(H.NOTICE_TIMER + 0x20 * slot + 4 * line, 0x1100 + 0x10 * slot + line)
            emu.mem.w32(H.NOTICE_ROW + 0x20 * slot + 4 * line, 0x2200 + 0x10 * slot + line)


def check_notices(emu, n, slot, want):
    """want: list of (line, frames) and ('voice', id) in order."""
    lines = [w for w in want if w[0] != 'voice']
    timers = [[emu.mem.u32(H.NOTICE_TIMER + 0x20 * s + 4 * i) for i in range(8)] for s in range(4)]
    rows = [[emu.mem.u32(H.NOTICE_ROW + 0x20 * s + 4 * i) for i in range(8)] for s in range(4)]
    want_t = [[0x1100 + 0x10 * s + i for i in range(8)] for s in range(4)]
    want_r = [[0x2200 + 0x10 * s + i for i in range(8)] for s in range(4)]
    for line, frames in lines:
        want_t[slot][line] = frames
        want_r[slot][line] = 0x30 + line
    check('%s timers' % n, timers, want_t)
    check('%s rows' % n, rows, want_r)
    check('%s counter calls' % n, emu.rows, [(slot, line) for line, _f in lines])
    check('%s voices' % n, emu.voices, [(slot, w[1]) for w in want if w[0] == 'voice'])
    no_draws(emu, n)


def run_slice(emu, start, until, regs):
    emu.rows.clear()
    emu.voices.clear()
    emu.reset_log()
    for index, value in regs.items():
        emu.r[index] = value & 0xFFFFFFFFFFFFFFFF
    emu.r[31] = emu.RETURN_ADDR
    stops = set(until) if isinstance(until, tuple) else {until}
    if emu.run(start=start, until=stops, max_steps=20000) != 'stop':
        raise Fail('slice 0x%x did not reach %r' % (start, until))


def ammo_cases(elf, rng):
    emu = notice_machine(elf)
    P = emu.P
    checked = 0
    counts = (0, 1, 2, 19, 20, 21, 60, 0xFFFF)

    def setup(slot, present, count, copy):
        rec = PLAYER + STRIDE * slot
        emu.mem.w32(P + 0x3C8, slot)
        emu.mem.w32(P + 0xC, 0x20000 if copy else 0)
        emu.mem.w16(emu.item + 4, count)
        emu.mem.w32(rec + 0x4410, emu.item if present else 0)
        plant_notices(emu)
    for slot in range(4):
        for present in (False, True):
            for count in counts if present else (5,):
                for copy in (False, True):
                    setup(slot, present, count, copy)
                    run_slice(emu, 0x1A758C, 0x1A7678, {17: slot, 18: emu.ability, 30: P})
                    check_notices(emu, 'neutral s%d p%d c%d copy%d' % (slot, present, count, copy),
                                  slot, H.ammo_neutral(present, count, copy))
                    setup(slot, present, count, copy)
                    run_slice(emu, 0x1A7D4C, 0x1A7EB4,
                              {4: 0x20000 if copy else 0, 17: slot, 30: P})
                    check_notices(emu, 'attack s%d p%d c%d copy%d' % (slot, present, count, copy),
                                  slot, H.ammo_attack(present, count, copy))
                    checked += 2
    return checked


def thrown_cases(elf, rng):
    emu = notice_machine(elf)
    P = emu.P
    sp = 0x01F80000
    checked = 0
    for slot in range(4):
        for count in (0, 1, 2, 20, 21, 99, 0x8000):
            for start, until, regs in (
                    (0x1A888C, (0x1A88E4, 0x1A88E8), {29: sp, 30: P}),
                    (0x319CC4, (0x319D10, 0x319D14), {18: P, 19: emu.item}),
                    (0x31A5F8, (0x31A644, 0x31A648), {18: P, 19: emu.item})):
                emu.mem.w32(P + 0x3C8, slot)
                emu.mem.w32(sp + 0xE50, emu.item)
                emu.mem.w16(emu.item + 4, count)
                plant_notices(emu)
                run_slice(emu, start, until, regs)
                check_notices(emu, 'thrown 0x%x s%d c%d' % (start, slot, count), slot,
                              H.thrown_release(count))
                check('thrown 0x%x count kept' % start, emu.mem.u16(emu.item + 4), count)
                checked += 1
    # One item and definition per weapon set word +0x4430 + 4*k (k = -1..3). Only set 1's
    # definition carries the class under test; the others carry the opposite answer, so a
    # read of another set's word would change the result. Counts vary per item.
    items = [emu.alloc(0x10) for _ in range(5)]
    defs = [emu.alloc(0x40) for _ in range(5)]
    swap_counts = (0, 1, 20, 21, 50, 0xFFFF)
    for slot in range(4):
        for which in (0, 1, 2, -1):
            for klass in (0, 4, 6, 7):
                rec = PLAYER + STRIDE * slot
                emu.mem.w32(P + 0x3C8, slot)
                emu.mem.w8(rec + 0x4A7C, which & 0xFF)
                for k in range(-1, 4):
                    it, d = items[k + 1], defs[k + 1]
                    emu.mem.w32(rec + 0x4430 + 4 * k, it)
                    emu.mem.w32(it, d)
                    emu.mem.w8(d + 0x1E, klass if k == 1 else (0 if klass == 6 else 6))
                    emu.mem.w16(it + 4, rng.choice(swap_counts))
                plant_notices(emu)
                run_slice(emu, 0x1BB9B0, 0x1BBA0C, {16: rec, 17: rec, 18: P, 20: 1})
                check_notices(emu, 'swap s%d set%d class%d' % (slot, which, klass), slot,
                              H.weapon_swap(which, klass))
                checked += 1
    return checked


# ---- 4. map icons ---------------------------------------------------------------------
REGISTRAR, PUSHTRIGGER_CTOR, GAMEOBJECT_CTOR = 0x1689A4, 0x1EC900, 0x14CB10
SSCANF, SPRINTF, STRCMP, STRNCMP, RES_FIND = 0x3B7F88, 0x3B7EF0, 0x3B8534, 0x3B91D8, 0x17365C
PROP_FLAG, PROP_NAME, PROP_OFFSET, PROP_SCALE, PROP_VAR, PROP_SCRIPT = (
    0x53E248, 0x53E258, 0x53E278, 0x53E288, 0x53E298, 0x53E2A8)
ROTATE_A, ROTATE_B = 0x53E260, 0x53E268
PREFIX, DIRECTIONS, ARROWS = 0x533B60, (0x533B68, 0x533B70, 0x533B80, 0x533B90), (
    0x533BA0, 0x533BB0, 0x533BC0, 0x533BD0)
QUEST_VARS, SCRIPT_MACHINE, FIND_ENTRY, INTERPRET = 0x86DA80, 0x86B270, 0x13EAC8, 0x13ECF8
DRAWER = 0x168CAC


def fake_sscanf(e):
    """Disclosed stub of libc sscanf: %f and %d conversions only, values from Python."""
    text = e.mem.cstr(e.r[4] & 0xFFFFFFFF).split()
    fmt = e.mem.cstr(e.r[5] & 0xFFFFFFFF)
    outs = [e.r[6], e.r[7], e.r[8], e.r[9]]
    convs = [c for c in fmt.split('%')[1:] if c]
    done = 0
    for conv, word, out in zip(convs, text, outs):
        if conv[0] == 'f':
            e.mem.w32(out & 0xFFFFFFFF, F.f32(float(word)))
        else:
            e.mem.w32(out & 0xFFFFFFFF, int(word) & 0xFFFFFFFF)
        done += 1
    return done


def icon_machine(elf):
    emu = EE(elf)
    emu.follow = {PUSHTRIGGER_CTOR, REGISTRAR, STRCMP, STRNCMP}
    props = {}
    prop_stub(emu, props)
    emu.stub(GAMEOBJECT_CTOR, ret=0, name='GameObject_ctor (base constructor, not run)')
    emu.stub(SSCANF, function=fake_sscanf, name='sscanf (%f / %d from Python)')
    formatted = []
    emu.stub(SPRINTF, function=lambda e: formatted.append(
        (e.r[5] & 0xFFFFFFFF, e.mem.cstr(e.r[6] & 0xFFFFFFFF))) or 0, name='sprintf (recorded)')
    found = []
    emu.stub(RES_FIND, function=lambda e: (found.append(
        (e.r[4] & 0xFFFFFFFF, e.mem.cstr(e.r[5] & 0xFFFFFFFF))), 0x2400000 + 0x100 * len(found))[1],
        name='res_find (recorded; returns a fresh texture handle)')
    emu.props, emu.formatted, emu.found = props, formatted, found
    return emu


def put(emu, text):
    if isinstance(text, str):
        text = text.encode('latin-1')
    a = emu.alloc(len(text) + 1)
    emu.mem.write(a, text + b'\0')
    return a


def registrar_cases(elf, rng):
    emu = icon_machine(elf)
    mem = emu.mem
    prefix = mem.cstr(PREFIX)[:4]
    directions = [mem.cstr(a) for a in DIRECTIONS]
    arrows = [mem.cstr(a) for a in ARROWS]
    obj = emu.alloc(0x200)
    pos = emu.alloc(0x10)
    checked = 0
    names = ['zz' + chr(0x61 + i) for i in range(3)] + [mem.cstr(ROTATE_A), mem.cstr(ROTATE_B)]
    names += directions + [prefix + 'qq', None]

    def run(n, name, angle, offset, scale, var, script, flag_prop):
        nonlocal checked
        props = emu.props
        props.clear()
        if flag_prop:
            props[PROP_FLAG] = 1
        if name is not None:
            props[PROP_NAME] = put(emu, name)
        if offset is not None:
            props[PROP_OFFSET] = put(emu, '%r %r' % offset)
        if scale is not None:
            props[PROP_SCALE] = put(emu, str(scale))
        if var:
            props[PROP_VAR] = put(emu, 'qv')
        if script:
            props[PROP_SCRIPT] = put(emu, 'qs')
        px, py = F.f32(rng.choice((0.0, 360.5, -1200.25))), F.f32(rng.choice((0.0, 77.0, 9600.0)))
        mem.w32(pos, px)
        mem.w32(pos + 4, py)
        mem.w32(pos + 8, F.f32(5.0))
        count = rng.randrange(0, 20)
        mem.w32(H.ICON_COUNT, count)
        entry = H.ICONS + count * H.ICON_STRIDE
        for off in range(0, H.ICON_STRIDE, 4):
            mem.w32(entry + off, 0xA5A5A500 + off)
        mem.w32(obj + 0xC, 0x3)
        emu.formatted.clear()
        emu.found.clear()
        emu.reset_log()
        emu.call(PUSHTRIGGER_CTOR, obj, pos, angle)
        check('pushtrigger %d flags' % n, mem.u32(obj + 0xC),
              (0x10000B | 0x3) & ~(1 if flag_prop else 0))
        check('pushtrigger %d angle' % n, mem.u16(obj + 0x38), angle & 0xFFFF)
        if name is None:
            check('pushtrigger %d no icon' % n, (mem.u32(H.ICON_COUNT), emu.found), (count, []))
            check('pushtrigger %d registrar not entered' % n,
                  [c for c in emu.calls if c.target == REGISTRAR], [])
            checked += 1
            return
        rotate = H.pushtrigger_rotate(name == mem.cstr(ROTATE_A), name == mem.cstr(ROTATE_B))
        dx, dy = (F.f32(offset[0]), F.f32(offset[1])) if offset is not None else (0, 0)
        want = H.register_icon((px, py), rotate, True, (dx, dy), scale or 0,
                               props.get(PROP_VAR, 0), props.get(PROP_SCRIPT, 0), F.add)
        got = {'x': mem.u32(entry), 'y': mem.u32(entry + 4), 'rotate': mem.u32(entry + 0xC),
               'scale': mem.u32(entry + 0x10), 'var': mem.u32(entry + 0x14),
               'script': mem.u32(entry + 0x18)}
        check('pushtrigger %d entry' % n, got, want)
        check('pushtrigger %d count' % n, mem.u32(H.ICON_COUNT), count + 1)
        if name[:4] == prefix:
            d = directions.index(name) if name in directions else -1
            k = H.arrow_choice(d, F.s32(angle))
            # compared as indices so that a failure prints no game string
            picked = [arrows.index(f[1]) if f[1] in arrows else -1 for f in emu.found]
            check('pushtrigger %d arrow' % n, (len(emu.formatted), picked), (0, [k]))
        else:
            check('pushtrigger %d formatted' % n,
                  [(f[0], f[1] == name) for f in emu.formatted], [(0x533BE0, True)])
        check('pushtrigger %d texture' % n, mem.u32(entry + 8), 0x2400100)
        check('pushtrigger %d lump' % n, [f[0] for f in emu.found], [0x533BE8])
        no_draws(emu, 'PushTrigger_ctor')
        checked += 1

    n = 0
    for name in names:
        for angle in (0, 0x3FFF, 0x4000, 0x8000 - 1, -1, -0x4000, -0x4001, -0x8000):
            if name is not None and name[:4] != prefix and angle not in (0, -1):
                continue
            run(n, name, angle, rng.choice((None, (0.0, 0.0), (12.5, -3.0))),
                rng.choice((None, 0, 1, 7)), rng.random() < 0.5, rng.random() < 0.5,
                rng.random() < 0.3)
            n += 1
    # The registrar's own null-name test: call 0x1689a4 directly with name 0 and real
    # offset / scale / var / script strings.
    for k in range(4):
        count = rng.randrange(0, 20)
        mem.w32(H.ICON_COUNT, count)
        entry = H.ICONS + count * H.ICON_STRIDE
        for off in range(0, H.ICON_STRIDE, 4):
            mem.w32(entry + off, 0xA5A5A500 + off)
        emu.formatted.clear()
        emu.found.clear()
        emu.reset_log()
        emu.call(REGISTRAR, pos, k & 1, 0, (k * 0x4000) & 0xFFFF, put(emu, '1.5 2.5'),
                 put(emu, '7'), put(emu, 'qv'), put(emu, 'qs'))
        check('registrar null %d' % k,
              (mem.u32(H.ICON_COUNT), [mem.u32(entry + off) for off in range(0, H.ICON_STRIDE, 4)],
               emu.found, emu.formatted),
              (count, [0xA5A5A500 + off for off in range(0, H.ICON_STRIDE, 4)], [], []))
        no_draws(emu, 'registrar')
        checked += 1
    return checked


def plant_vars(mem, entries):
    blob = b''.join(name.encode('latin-1') + b'\0' + bytes([value & 0xFF])
                    for name, value in entries) + b'\0'
    mem.write(QUEST_VARS, blob + b'\0' * 64)


def read_vars(mem):
    out, a = [], QUEST_VARS
    while mem.u8(a):
        name = mem.cstr(a)
        out.append((name, F.s32(mem.u8(a + len(name) + 1) << 24) >> 24))
        a += len(name) + 2
    return out


def icon_gate_cases(elf, rng):
    emu = EE(elf)
    emu.mem.map(0x10000000, 16)
    dl = emu.alloc(0x40000)
    tex = emu.alloc(0x40)
    emu.mem.w16(tex, 210)
    emu.mem.w16(tex + 2, 160)
    world = emu.alloc(0x90)
    emu.mem.w32(world + 0x6C, tex)
    centre = emu.alloc(0x10)
    callback = emu.alloc(0x10)
    emu.stub(callback, ret=-1, name='blip callback (no blips)')
    packets = []
    emu.stub(0x16B7F0, function=lambda e: packets.append(e.r[6] & 0xFFFFFFFF) or 0,
             name='gfx_addSortedPacket (recorded texture)')
    box = {'error': 0, 'result': 0}
    interpreted = []

    def find(e):
        e.mem.w32(e.r[6] & 0xFFFFFFFF, 7)          # entry index out
        return box['error']
    emu.stub(FIND_ENTRY, function=find, name='scr_findEntry (returns the planted error, index 7)')

    def interpret(e):
        interpreted.append(1)
        e.mem.w32(e.r[5] & 0xFFFFFFFF, box['result'] & 0xFFFFFFFF)
        return 0
    emu.stub(INTERPRET, function=interpret, name='scr_interpret (stores the planted result word)')
    icon_tex = [emu.alloc(0x10) for _ in range(4)]
    for t in icon_tex:
        emu.mem.w16(t, 16)
        emu.mem.w16(t + 2, 16)
    machine = emu.alloc(0x40)
    checked = 0

    def run(n, icons, vars_before, has_machine, error, result, frame, throttle):
        nonlocal checked
        mem = emu.mem
        mem.w32(0x44FE10, dl)
        mem.w32(0x44FE0C, dl)
        mem.w32(0x44FDA4, 0x40000)
        mem.w32(0x4044DC, 40)
        mem.w32(0x4044E0, 40)
        mem.w32(0x4044A8, 0)
        mem.w32(0x4044AC, 0)
        mem.write(0x4044F0, b'\0' * (216 * 216 * 2))
        mem.wf32(centre, 600.0)
        mem.wf32(centre + 4, 600.0)
        mem.w32(SCRIPT_MACHINE, machine if has_machine else 0)
        mem.w32(0x44FDD0, frame)
        mem.w32(0x4F8694, throttle)
        box.update(error=error, result=result)
        plant_vars(mem, vars_before)
        mem.w32(H.ICON_COUNT, len(icons))
        names = {}
        for i, (var, script) in enumerate(icons):
            e = H.ICONS + i * H.ICON_STRIDE
            mem.wf32(e, 600.0 + 30 * i)
            mem.wf32(e + 4, 600.0)
            mem.w32(e + 8, icon_tex[i])
            mem.w32(e + 0xC, i & 1)
            mem.w32(e + 0x10, H.SCALE_ONE)
            mem.w32(e + 0x14, put(emu, var) if var else 0)
            mem.w32(e + 0x18, put(emu, 'sc') if script else 0)
        packets.clear()
        interpreted.clear()
        emu.reset_log()
        emu.call(DRAWER, world, centre, callback, 0,
                 fargs=(0.0, 0.0, 1.0, 60.0, 60.0, 6.0, 16.0), max_steps=20000000)
        known = {name: value for name, value in vars_before}
        want_drawn, want_vars, want_runs = [], list(vars_before), 0
        for i, (var, script) in enumerate(icons):
            low = var.lower() if var else None
            drawn, appended, ran = H.icon_gate(bool(var), known.get(low, 0), low in known,
                                               script, has_machine, error, F.s32(result))
            if appended:
                known[low] = 0
                want_vars.append((low, 0))
            want_runs += int(ran)
            if drawn:
                want_drawn.append(icon_tex[i])
        got_icons = [t for t in packets if t in icon_tex]
        check('icon gate %d drawn' % n, got_icons, want_drawn)
        check('icon gate %d quest vars' % n, read_vars(mem), want_vars)
        check('icon gate %d interpreter runs' % n, len(interpreted), want_runs)
        probes = sum(1 for (var, script) in icons
                     if script and (not var or known.get(var.lower(), 0)))
        missing = has_machine and error != 0 and probes > 0
        want_throttle = (frame + 0x14) if (missing and F.s32(throttle) < F.s32(frame)) else throttle
        check('icon gate %d throttle word' % n, mem.u32(0x4F8694), want_throttle & 0xFFFFFFFF)
        no_draws(emu, 'automap icons')
        checked += 1

    n = 0
    vars_before = [('qa', 5), ('qb', 0), ('qc', -3)]
    var_choices = (None, 'qa', 'QA', 'qb', 'qc', 'qnew', 'QNeW2')
    for var in var_choices:
        for script in (False, True):
            for has_machine, error, result in ((False, 0, 0), (True, 3, 0), (True, 0, 0),
                                               (True, 0, 1), (True, 0, -5)):
                if not script and (has_machine or error or result):
                    continue
                run(n, [(var, script)], vars_before, has_machine, error, result, 500, 100)
                n += 1
    run(n, [(None, True)], vars_before, True, 3, 0, 500, 600)
    n += 1
    for _ in range(10):
        icons = [(rng.choice(var_choices), rng.random() < 0.5) for _ in range(rng.randint(1, 4))]
        run(n, icons, vars_before, rng.random() < 0.7, rng.choice((0, 2)), rng.choice((0, 1, -1)),
            rng.randrange(0, 1000), rng.randrange(0, 1000))
        n += 1
    return checked


# ---- 5. automap tile quads (VU1) ------------------------------------------------------
def tile_cases(elf, rng, cases=40):
    import difftest_hud_minimap as DM
    import vu1_emu as V
    emu = EE(elf)
    emu.mem.map(0x10000000, 0x1000)
    world, centre = emu.alloc(0x80), emu.alloc(16)
    dl = emu.alloc(0x40000)
    texs = [emu.alloc(0x10) for _ in range(4)]
    callback = emu.alloc(16)
    emu.stub(callback, ret=-1, name='blip callback (no blips)')
    stats = {'cases': 0, 'packets': 0, 'vertices': 0, 'drawn': 0}
    for _ in range(cases):
        s = DM.make_state(emu, rng, world, centre, dl, cb_blips=[])
        for i, ic in enumerate(s['icons']):
            ic['tex'] = texs[i] if ic['tex'] else 0
        want = DM.run_draw(emu, s, world, centre, dl, callback)
        stats['cases'] += 1
        if not want['drawn']:
            continue
        stats['drawn'] += 1
        ranges = [c for c in want['calls'] if c[0] == 'ranges'][0]
        _, c_min, r_min, c_end, r_end = ranges
        strips = [c[1] for c in want['calls']
                  if c[0] == 'gfx_addSortedPacket' and c[3] == s['world_tex']]
        runs = H.strip_columns(c_min, c_end)
        check('tile strips', len(strips), len(runs))
        copies = [c for c in want['calls'] if c[0] == 'memcpy']
        rows = list(range(r_min, r_end))
        want_copies = [(0x4044F0 + row * 0x1B0 + c0 * 2, n * 2) for c0, n in runs for row in rows]
        check('tile cells read', [(c[2], c[3]) for c in copies], want_copies)
        grid = s['grid']

        def cell(col, row):
            return grid[(row * 216 + col) * 2] | (grid[(row * 216 + col) * 2 + 1] << 8)
        for p, (c0, n) in zip(strips, runs):
            gs = V.GifReader()
            vif = V.Vif1(V.Vu1(), kick=gs.path1, direct=gs.path2)
            vif.feed(V.dma_chain_words(lambda a, k: emu.mem.read(a, k), p))
            have = [(v.uv[0], v.uv[1], v.rgba[3]) for v in gs.vertices]
            # GS packet shape: vertices per PRIM write, and each vertex's PRIM, ADC bit and
            # register.
            runs = []
            for ev in gs.events:
                if ev[0] == 'reg' and ev[1] == 'PRIM':
                    runs.append(0)
                elif ev[0] == 'vtx':
                    if not runs:
                        raise Fail('tile vertex before any PRIM write')
                    runs[-1] += 1
            check('tile packet cols %d+%d PRIM runs' % (c0, n), runs,
                  H.strip_prim_runs(len(rows), n))
            check('tile packet cols %d+%d vertex kinds' % (c0, n),
                  sorted({(v.prim, v.adc, v.reg) for v in gs.vertices}),
                  [(H.TILE_PRIM, 0, 'XYZ2')] if gs.vertices else [])
            expect = list(H.strip_vertices(cell, rows, c0, n))
            if have != expect:
                bad = next(i for i in range(min(len(have), len(expect)))
                           if have[i] != expect[i]) if have and expect else 0
                raise Fail('tile packet cols %d+%d rows %d..%d: %d vertices, want %d; first '
                           'difference at %d: %r / %r' % (
                               c0, n, r_min, r_end, len(have), len(expect), bad,
                               have[bad:bad + 1], expect[bad:bad + 1]))
            stats['packets'] += 1
            stats['vertices'] += len(have)
    tile_cases.stats = stats
    return stats['packets']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default=os.environ.get('CHAMPIONS_ELF'))
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--only', default='')
    args = parser.parse_args()
    if not args.elf or not os.path.isfile(args.elf):
        print('SKIP: SLUS-20973 v2.00 ELF missing')
        return 0
    parts = [
        ('message census', census_cases),
        ('acknowledge edge', ack_cases),
        ('acknowledge chain', ack_chain_cases),
        ('setInfo', setinfo_cases),
        ('door', door_cases),
        ('savepoint', savepoint_cases),
        ('jumpgate', jumpgate_cases),
        ('pickup', pickup_cases),
        ('ammunition notices', ammo_cases),
        ('thrown notices', thrown_cases),
        ('icon registrar', registrar_cases),
        ('icon gates', icon_gate_cases),
        ('tile packets', tile_cases),
    ]
    total = 0
    for name, fn in parts:
        if args.only and args.only not in name:
            continue
        count = fn(args.elf, random.Random('%d/%s' % (args.seed, name)))
        if fn is census_cases:
            print('PASS %s %d direct jumps to hud_showMessage (40 jal, 3 j) in %d functions, '
                  'each site and its function asserted' % (name, count, census_cases.functions))
        elif fn is tile_cases:
            st = tile_cases.stats
            print('PASS %s %d strip packets in vu1_emu (%d drawer calls, %d drew, %d vertices); '
                  'seed draws 0' % (name, count, st['cases'], st['drawn'], st['vertices']))
        else:
            print('PASS %s %d cases; seed draws 0' % (name, count))
        total += count
    print('PASS %d properties, %d cases, seed %d' % (len(parts), total, args.seed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
