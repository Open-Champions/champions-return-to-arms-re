#!/usr/bin/env python3
"""sections_test.py - the sections of tools/recomp/soak/proposed-sections.pnach in the
function-level interpreter, each against the game as shipped.

  python3 tools/recomp/soak/sections_test.py [path/to/SLUS_209.73]

A. Savepoint_interact 0x28dc30 with the section "save point is used on every machine whatever
   this machine's card screen does".  memcard_requestSave, light_link2 and
   obj_runActionScripts are stubbed and their calls recorded; memcard_isBusy and
   menuMutex_isHeld run for real on the globals they read (g_memcardState 0x88d3a0, the card
   result word 0x88d3bc, 0x88d3c8, g_menuMutex 0x4fe53c).
B. vars_get 0x1ed778 with the section "reading a quest variable never adds it to the table",
   together with the game's own vars_set 0x1ed854 and C library, on a table of its own.

C. JumpGate_interactPrompt 0x27d7a0 with the section "a jump gate is found only inside the
   tick": called as Player_interact calls it, with that function's display-only argument in
   register s7; the script, the level list and the message are stubbed and counted.

PASS/FAIL lines as tools/ee_tests.py prints them.  One function on a prepared state: this
shows what the code does there, not that the state occurs (docs/issues/native-soak.md has
the runs on two, three and four machines).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ee_emu import EE  # noqa: E402

PNACH = os.path.join(HERE, 'proposed-sections.pnach')
SEC_A = 'save point is used on every machine'
SEC_B = 'reading a quest variable never adds it'
SEC_C = 'a jump gate is found only inside the tick'
GATE_PROMPT, TASK_IS_RUNNING, GET_PROP, RUN_SCRIPT, ADD_LEVEL = 0x27D7A0, 0x19E5E8, 0x14F4C0, 0x1ED694, 0x27DB60
TEXT_LOOKUP, HUD_MESSAGE, WSTR_COPY = 0x173C84, 0x1D92A0, 0x19E854
GATE_COUNT, ALIVE_COUNT, ALIVE_LIST = 0x8E3C30, 0x4F8420, 0x4F8440
INTERACT, REQUEST_SAVE, LIGHT_LINK, RUN_ACTIONS = 0x28DC30, 0x2175B4, 0x148BC8, 0x14DCC8
CARD_STATE, CARD_RESULT, CARD_3C8, MENU_MUTEX = 0x88D3A0, 0x88D3BC, 0x88D3C8, 0x4FE53C
VARS_GET, VARS_SET, QUEST_VARS, TABLE_BYTES = 0x1ED778, 0x1ED854, 0x86DA80, 0x2000
M32 = 0xFFFFFFFF
FAILED = []


def check(ident, ok, text):
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    if not ok:
        FAILED.append(ident)


# ---- A ------------------------------------------------------------------------------------------
def interact(elf, patched, card_state=-1, card_result=0, mutex=0, slot=1):
    """What one call does: (+0x84, +0xc4, [requestSave slots], [light arguments - object],
    [(action object - object, raw)], callee-saved registers kept)."""
    emu = EE(elf)
    if patched:
        assert emu.apply_pnach(PNACH, SEC_A) == 5
    for a in (CARD_STATE, MENU_MUTEX):
        emu.mem.map(a & ~0xFFF, 0x1000)
    emu.mem.w32(CARD_STATE, card_state & M32)
    emu.mem.w32(CARD_RESULT, card_result)
    emu.mem.w32(CARD_3C8, 0)
    emu.mem.w32(MENU_MUTEX, mutex)
    point = emu.alloc(0x180)
    requests, lights, actions = [], [], []
    emu.stub(REQUEST_SAVE, function=lambda e: requests.append(e.r[4] & M32))
    emu.stub(LIGHT_LINK, function=lambda e: lights.append((e.r[4] & M32) - point))
    emu.stub(RUN_ACTIONS, function=lambda e: actions.append(((e.r[4] & M32) - point, e.r[5] & M32)))
    emu.set_reg('s0', 0x1111)
    emu.set_reg('s1', 0x2222)
    stack = emu.r[29]
    emu.call(INTERACT, point, slot, max_steps=20000)
    kept = emu.reg('s0') == 0x1111 and emu.reg('s1') == 0x2222 and emu.r[29] == stack
    return emu.mem.u32(point + 0x84), emu.mem.u8(point + 0xC4), requests, lights, actions, kept


def test_a(elf):
    used = lambda slot: (1, 1, [slot], [0x88], [(0, 1)], True)
    lit = (1, 1, [], [0x88], [(0, 1)], True)           # everything but the request
    nothing = (0, 0, [], [], [], True)
    # 1. nobody busy: the section changes nothing
    for slot in range(4):
        check('A%d' % (1 + slot), interact(elf, False, slot=slot) == used(slot) and interact(elf, True, slot=slot) == used(slot),
              'no card screen, mutex free, player %d: state, light, action scripts and the save request for that player - '
              'as shipped and with the section' % slot)
    # 2. this machine's card screen is up: the difference between the machines
    for ident, state, what in (('A5', 3, 'the save dialog (state 3)'), ('A6', 5, 'the options being written (state 5)'),
                               ('A7', 10, 'the options being read back (state 10)')):
        check(ident, interact(elf, False, card_state=state) == nothing, 'as shipped, %s: nothing at all' % what)
        check(ident + 'p', interact(elf, True, card_state=state) == lit,
              'with the section, %s: state +0x84, light and action scripts as on the other machines, no save request' % what)
    check('A8', interact(elf, False, card_result=7) == nothing and interact(elf, True, card_result=7) == lit,
          'card idle but a result pending (0x88d3bc): nothing as shipped; with the section everything but the request')
    # 3. the menu mutex (shared state in a net game) still guards everything
    check('A9', interact(elf, False, mutex=1) == nothing and interact(elf, True, mutex=1) == nothing,
          'menu mutex held: nothing, as shipped and with the section')
    check('A10', interact(elf, False, mutex=1, card_state=3) == nothing and interact(elf, True, mutex=1, card_state=3) == nothing,
          'menu mutex held and a card screen up: nothing, as shipped and with the section')
    # 4. two machines in the same tick, one with its save dialog up
    a, b = interact(elf, False, card_state=-1), interact(elf, False, card_state=3)
    check('A11', a[:2] != b[:2], 'as shipped, two machines of which one has a card screen up: the save point differs (+0x84 %d against %d)' % (a[0], b[0]))
    a, b = interact(elf, True, card_state=-1), interact(elf, True, card_state=3)
    check('A12', a[:2] == b[:2] and a[3:5] == b[3:5] and a[2] == [1] and b[2] == [],
          'with the section: the same on both; only the machine that is not busy asks for its save dialog')


# ---- B ------------------------------------------------------------------------------------------
class Vars:
    def __init__(self, elf, patched):
        self.emu = EE(elf)
        if patched:
            assert self.emu.apply_pnach(PNACH, SEC_B) == 1
        self.emu.mem.map(QUEST_VARS, TABLE_BYTES + 0x1000)
        self.name = self.emu.alloc(64)

    def _text(self, name):
        self.emu.mem.write(self.name, name.encode() + b'\0')
        return self.name

    def get(self, name):
        value = self.emu.call(VARS_GET, self._text(name), max_steps=200000) & 0xFF
        return value - 256 if value & 0x80 else value

    def set(self, name, value):
        self.emu.call(VARS_SET, self._text(name), value & 0xFFFFFFFFFFFFFFFF, max_steps=200000)

    def table(self):
        """[(name, value)] in table order."""
        raw = bytes(self.emu.mem.read(QUEST_VARS, TABLE_BYTES))
        out, at = [], 0
        while raw[at]:
            end = raw.index(b'\0', at)
            value = raw[end + 1]
            out.append((raw[at:end].decode(), value - 256 if value & 0x80 else value))
            at = end + 2
        return out

    def raw(self):
        return bytes(self.emu.mem.read(QUEST_VARS, TABLE_BYTES))


def test_b(elf):
    # 1. a read of a missing name
    v = Vars(elf, False)
    check('B1', v.get('Nit_GotShard') == 0 and v.table() == [('nit_gotshard', 0)],
          'as shipped, empty table: a read of a missing name returns 0 and appends it (lower-cased)')
    v = Vars(elf, True)
    check('B2', v.get('Nit_GotShard') == 0 and v.raw() == bytes(TABLE_BYTES),
          'with the section: returns 0, not one byte of the table written')
    for patched in (False, True):
        v = Vars(elf, patched)
        v.set('one', 1)
        v.set('Two', -2)
        before = v.table()
        got = v.get('three')
        after = v.table()
        if patched:
            check('B4', got == 0 and after == before == [('one', 1), ('two', -2)], 'with the section, two names set: a missing third reads 0, table unchanged')
        else:
            check('B3', got == 0 and after == before + [('three', 0)], 'as shipped, two names set: a missing third reads 0 and is appended')
        # 2. everything else is as it was
        tag = 'p' if patched else ''
        check('B5' + tag, v.get('one') == 1 and v.get('TWO') == -2 and v.get('two') == -2,
              '%s: names that exist read their values, whatever the case of the letters' % ('with the section' if patched else 'as shipped'))
        v.set('three', 3)
        v.set('one', 127)
        v.set('big', 1000)
        v.set('low', -1000)
        check('B6' + tag, (v.get('three'), v.get('one'), v.get('big'), v.get('low')) == (3, 127, 127, -128) and v.get('never') == 0,
              '%s: a store after a missing read, an overwrite, the clamp to a signed byte; a name never set reads 0' % ('with the section' if patched else 'as shipped'))
    # 3. the order hazard of docs/script.md P1: one machine reads at draw time before the store
    def machine(patched, draws_first):
        v = Vars(elf, patched)
        v.set('a', 1)
        if draws_first:
            v.get('gate')           # the prompt's predicate, from drawing, on the owner's machine
        v.set('b', 2)               # a trigger's script, in the tick, on every machine
        v.get('gate')               # the same predicate inside the tick, on every machine
        v.set('gate', 1)
        return v
    owner, other = machine(False, True), machine(False, False)
    check('B7', owner.table() != other.table() and sorted(owner.table()) == sorted(other.table()),
          'as shipped, a draw-time read on one machine: the same names and values in a different order for good (%s against %s)' % (
              ','.join(n for n, _ in owner.table()), ','.join(n for n, _ in other.table())))
    owner, other = machine(True, True), machine(True, False)
    check('B8', owner.raw() == other.raw() and owner.table() == [('a', 1), ('b', 2), ('gate', 1)],
          'with the section: the tables are the same byte for byte')
    # 4. a machine with the section beside one without: every value read is the same
    mixed, plain = machine(True, True), machine(False, True)
    names = ('a', 'b', 'gate', 'nothere')
    check('B9', [mixed.get(n) for n in names] == [plain.get(n) for n in names],
          'a machine with the section and one without read the same value for every name')


# ---- C ------------------------------------------------------------------------------------------
def gate_prompt(elf, patched, display, found=0, count=1, script=None, s7_garbage=None):
    """One call of the prompt as Player_interact makes it (s7 = its display-only argument):
    (result, +0x4d, levels added, messages shown, text chosen)."""
    emu = EE(elf)
    if patched:
        assert emu.apply_pnach(PNACH, SEC_C) == 2
    for a in (GATE_COUNT, ALIVE_COUNT):
        emu.mem.map(a & ~0xFFF, 0x1000)
    emu.mem.w8(GATE_COUNT, count)
    emu.mem.w32(ALIVE_COUNT, 1)
    emu.mem.w32(ALIVE_LIST, 0)
    gate = emu.alloc(0x180)
    text = emu.alloc(0x200)
    emu.mem.w8(gate + 0x4D, found)
    added, shown, texts = [], [], []
    emu.stub(TASK_IS_RUNNING, ret=0)
    emu.stub(GET_PROP, ret=0 if script is None else 0x547E40)
    emu.stub(RUN_SCRIPT, ret=0 if script is None else script)
    emu.stub(ADD_LEVEL, function=lambda e: added.append(1))
    emu.stub(TEXT_LOOKUP, function=lambda e: texts.append(e.r[4] & M32) or 0)
    emu.stub(HUD_MESSAGE, function=lambda e: shown.append(1))
    emu.stub(WSTR_COPY)
    emu.set_reg('s7', (1 if display else 0) if s7_garbage is None else s7_garbage)
    result = emu.call(GATE_PROMPT, gate, text, 0, max_steps=20000) & M32
    names = {0x547E90: 'activated', 0x547EA8: 'virgin', 0x547EB8: 'others too far', 0x547ED0: 'gate'}
    return result, emu.mem.u8(gate + 0x4D), len(added), len(shown), [names.get(t, hex(t)) for t in texts if t != 0x547E90]


def test_c(elf):
    marked = lambda count: (0 if count == 1 else 1, 1, 1, 1, ['virgin' if count == 1 else 'gate'])
    shown = lambda count, found: (0 if count == 1 else 1, found, 0, 0, ['virgin' if count == 1 else 'gate'])
    for ident, count in (('C1', 1), ('C2', 2)):
        check(ident, gate_prompt(elf, False, False, count=count) == marked(count) and gate_prompt(elf, True, False, count=count) == marked(count),
              'from the tick, gate not found, %d destination%s: found flag set, level added, message shown - as shipped and with the section' % (
                  count, '' if count == 1 else 's'))
    check('C3', gate_prompt(elf, False, True, count=2) == marked(2), 'as shipped, from drawing: the same marking, on the machine that draws alone')
    for ident, count in (('C4', 1), ('C5', 2)):
        check(ident, gate_prompt(elf, True, True, count=count) == shown(count, 0),
              'with the section, from drawing, %d destination%s: nothing marked, nothing added, no message; the result and the text of a found gate' % (
                  count, '' if count == 1 else 's'))
    for display in (False, True):
        check('C6' + ('d' if display else 't'), gate_prompt(elf, False, display, found=1, count=2) == shown(2, 1) and
              gate_prompt(elf, True, display, found=1, count=2) == shown(2, 1),
              'a gate already found, from %s: no marking, as shipped and with the section' % ('drawing' if display else 'the tick'))
    check('C7', gate_prompt(elf, False, True, script=0) == (0, 0, 0, 0, []) and gate_prompt(elf, True, True, script=0) == (0, 0, 0, 0, []) and
          gate_prompt(elf, True, False, script=0) == (0, 0, 0, 0, []),
          'a gate whose script says no: nothing at all, as shipped and with the section')
    check('C8', gate_prompt(elf, True, False, script=1, count=2) == marked(2) and gate_prompt(elf, True, True, script=1, count=2) == shown(2, 0),
          'with the section, a gate whose script says yes: marked from the tick, not from drawing')
    a, b = gate_prompt(elf, False, True, count=1), gate_prompt(elf, False, False, found=0, count=1)
    check('C9', a[1:3] == (1, 1), 'as shipped: the owner\'s machine has the gate found and the level added after one displayed frame, before any tick ran the prompt')


def main(argv):
    elf = argv[0] if argv else os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.isfile(elf):
        print('no executable at %s (bring your own SLUS_209.73)' % elf)
        return 0
    test_a(elf)
    test_b(elf)
    test_c(elf)
    print('%d failed' % len(FAILED))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
