#!/usr/bin/env python3
"""touchfix_test.py - the touch handlers and the prediction copy (FINDINGS G25, G26).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -I -B tools/touchfix_test.py [path/to/SLUS_209.73] [-v]

What runs.  The game's own Creature_moveBy (0x113c48), Creature_onTouch (0x11a418) and
SmallSpider_onTouch (0x2ab8e0) are executed by tools/ee_emu.py on three objects this
script builds: a mover and two things it overlaps, one with the base Creature table and
one with the SmallSpider table.  Everything else Creature_moveBy calls is replaced: the
box query hands back the two objects, the terrain, water, grid and sound calls return 0,
and the set-state call a small spider makes when it dies is recorded, not run.  No game
data is embedded or read from the disc.

What it shows.
  s  the survey: every object class's "touched" function (virtual slot 6) is one of the
     38 listed in docs/issues/touch-handlers.md, and the executable has nine call sites
     of that slot.
  p  the patch words: the originals are what the executable holds, the eight new words
     lie in the unused function Cyclops_dropClub, nothing in the image leads there, and
     no section of the patch file (when present) uses the same words.
  u  as shipped: with the prediction copy as the mover both handlers run, the creature is
     flagged and the small spider is told to die.
  f  with the patch: neither handler runs for a prediction copy; for every other mover
     the two runs make the same calls and the same stores; the mover is still told what
     it bumped into.

Every line is PASS or FAIL with a check id.  Nothing here shows that a state occurs in a
real game: one function, state built by the script, no second machine.
docs/issues/touch-handlers.md has the survey, the design and the live runs.
"""
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                            # noqa: E402
from ee_emu import EE, EmuError, M32                     # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- addresses (names.tsv / symbols) ---------------------------------------------------
CREATURE_MOVE_BY = 0x113C48
MOVE_BY_END = 0x1143E0
CREATURE_ON_TOUCH, CREATURE_ON_TOUCH_END = 0x11A418, 0x11A444
SPIDER_ON_TOUCH, SPIDER_ON_TOUCH_END = 0x2AB8E0, 0x2AB958
SPIDER_SET_STATE = 0x2AB704
WORLD_COLLECT = 0x14A928            # world_collectObjectsInBox(min, max, out, max count)
CREATURE_SLOT11 = 0x11A448          # "these are the objects I bumped into" (empty body)
VT_CREATURE, VT_SPIDER, VT_PLAYER = 0x50CC58, 0x50FD40, 0x511308
CALL_SITE = 0x114220                # jalr v1: touched->slot6(touched, mover)
RETURN_SITE = 0x114228

# object fields used here (docs/OVERVIEW.md, docs/creatures.md)
O_FLAGS, O_X, O_Y, O_Z, O_RADIUS, O_HEIGHT, O_VTABLE = 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x48
C_FLAGS64, C_STATE = 0xA8, 0x232
TOUCHED_BIT = 1 << 59               # "touched by a player" (G25)
DEAD_STATE = 0x14

F_CREATURE, F_PLAYER, F_COPY, F_OWN, F_CATCHUP = 0x20, 0x40, 0x20000, 0x200000, 0x4000000

# ---- the patch (docs/issues/touch-handlers.md section 4) ---------------------------------
CAVE_FN, CAVE_FN_END = 0x257AB4, 0x257BA0       # Cyclops_dropClub
STUB = 0x257B30
PATCH = [                                       # (address, original word, new word)
    (0x114220, 0x0060F809, 0x0C095ECC),         # jalr v1          ->  jal  0x257b30
    (STUB + 0x00, 0x26080114, 0x8CA1000C),      # lw   at, 0xc(a1)       the toucher's flags
    (STUB + 0x04, 0x6A030017, 0x00010B80),      # sll  at, at, 14        bit 0x20000 -> sign
    (STUB + 0x08, 0x6E030010, 0x04200003),      # bltz at, 0x257b48      a prediction copy
    (STUB + 0x0C, 0x8E070018, 0x00000000),      # nop
    (STUB + 0x10, 0xB0A30007, 0x00600008),      # jr   v1                the handler; it returns to 0x114228
    (STUB + 0x14, 0xB4A30000, 0x00000000),      # nop
    (STUB + 0x18, 0xACA70008, 0x03E00008),      # jr   ra                no handler for a copy
    (STUB + 0x1C, 0x3C013F80, 0x00000000),      # nop
]

# ---- the survey (docs/issues/touch-handlers.md section 2) --------------------------------
SLOT6_FUNCTIONS = (
    0x11A418, 0x152A18, 0x153900, 0x157A9C, 0x15DF4C, 0x1BEAF0, 0x1EE7B0, 0x1FCB70, 0x202DE0,
    0x208528, 0x23E358, 0x247E1C, 0x24A3A8, 0x255F7C, 0x26998C, 0x26DE54, 0x27C5E8, 0x283214,
    0x28C2C4, 0x28F340, 0x2900C8, 0x290DA8, 0x2946F8, 0x2AB8E0, 0x2B1C4C, 0x2B2860, 0x2CAEC8,
    0x2D685C, 0x2D7AAC, 0x2D932C, 0x2DA610, 0x2DB4F0, 0x2ECAE8, 0x2F5FB4, 0x2F71AC, 0x2F84E4,
    0x310028, 0x3C7EA8)
OBJECT_TABLE_SIZES = (16, 17, 19, 29, 39)       # entry counts of the GameObject family
SLOT6_CALL_SITES = (0x114220, 0x14D9D0, 0x14D9EC, 0x150DDC, 0x150DF8, 0x15EBC8, 0x15EBE4,
                    0x18C6E0, 0x28F35C)
LOBBY_UI_LO, LOBBY_UI_HI = 0x322000, 0x350000    # the SRS window classes (9- and 14-entry tables)

VERBOSE = False
RESULTS = []


def check(ident, ok, text):
    RESULTS.append((ident, bool(ok)))
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    return bool(ok)


def note(text):
    if VERBOSE:
        print('         ' + text)


# ---------------------------------------------------------------------------------------
# One call of Creature_moveBy on built objects
# ---------------------------------------------------------------------------------------
class Run:
    """What one call did."""

    def __init__(self):
        self.result = 0
        self.handler_pcs = set()        # handler entry points whose first instruction ran
        self.set_state = []             # (object, state) of each recorded set-state call
        self.bumped = None              # the list handed to the mover's slot 11
        self.stores = []                # (address - base of its object, size, value)
        self.calls = []                 # (target, a0 as an object number, a1)
        self.touched_flags = {}         # object name -> +0xa8 afterwards


def make_object(emu, vtable, flags, x, radius):
    obj = emu.alloc(0x600)
    mem = emu.mem
    mem.w32(obj + O_FLAGS, flags)
    mem.wf32(obj + O_X, x)
    mem.wf32(obj + O_Y, 0.0)
    mem.wf32(obj + O_Z, 0.0)
    mem.wf32(obj + O_RADIUS, radius)
    mem.wf32(obj + O_HEIGHT, 40.0)
    mem.w32(obj + O_VTABLE, vtable)
    return obj


def move_by(elf, mover_flags, patched):
    """Creature_moveBy(mover, zero velocity) with a small spider and a plain creature
    inside the mover's radius."""
    emu = EE(elf)
    if patched:
        for addr, _old, new in PATCH:
            emu.patch(addr, new)
    mover = make_object(emu, VT_PLAYER, mover_flags, 0.0, 10.0)
    spider = make_object(emu, VT_SPIDER, F_CREATURE, 4.0, 5.0)
    plain = make_object(emu, VT_CREATURE, F_CREATURE, -6.0, 8.0)
    names = {mover: 'mover', spider: 'spider', plain: 'creature'}
    velocity = emu.alloc(16)
    run = Run()

    def collect(e):
        out = e.r[6] & M32
        for index, obj in enumerate((spider, plain, 0)):
            e.mem.w32(out + 4 * index, obj)
        return 2

    def slot11(e):
        listed, at = [], e.r[5] & M32
        while e.mem.u32(at):
            listed.append(names.get(e.mem.u32(at), '?'))
            at += 4
        run.bumped = listed

    emu.stub(WORLD_COLLECT, function=collect, name='world_collectObjectsInBox')
    emu.stub(CREATURE_SLOT11, function=slot11, name='mover slot 11')
    emu.follow = {CREATURE_MOVE_BY, CREATURE_ON_TOUCH, SPIDER_ON_TOUCH, STUB}
    emu.trace = []
    emu.reset_log()
    run.result = emu.call(CREATURE_MOVE_BY, mover, velocity) & M32
    executed = set(emu.trace)
    run.handler_pcs = {pc for pc in (CREATURE_ON_TOUCH, SPIDER_ON_TOUCH) if pc in executed}
    run.stub_ran = STUB in executed
    for rec in emu.calls:
        who = names.get(rec.args[0] & M32, '-')
        if rec.target == SPIDER_SET_STATE:
            run.set_state.append((who, rec.args[1] & M32))
        if rec.site == CALL_SITE:
            continue                    # the dispatch itself: a handler, or the patch's stub
        run.calls.append((rec.site, rec.target, who))
    for _pc, addr, size, value in emu.writes:
        for base, name in names.items():
            if base <= addr < base + 0x600:
                run.stores.append((name, addr - base, size, value))
                break
        else:
            run.stores.append(('?', addr, size, value))
    for base, name in names.items():
        run.touched_flags[name] = emu.mem.u64(base + C_FLAGS64)
    return run


MOVERS = (                          # label, object flags, is a prediction copy
    ('a prediction copy (flag word 0x00024060)', 0x24060, True),
    ('a prediction copy as logged in a fight (0x000ac060)', 0xAC060, True),
    ('a prediction copy that is catching up (0x040ac060)', 0x40AC060, True),
    ("this machine's real player (0x00204060)", 0x204060, False),
    ("another machine's real player (0x00004060)", 0x4060, False),
    ('a monster (0x00000020)', 0x20, False),
)


# ---------------------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------------------
def group_s(elf):
    """(s) the survey is complete: slot 6 of every object table, and its call sites."""
    segments, _entry = ee_emu.load_elf_segments(elf)

    def word(addr):
        for vaddr, blob, _memsz in segments:
            if vaddr <= addr < vaddr + len(blob) - 3:
                return struct.unpack_from('<I', blob, addr - vaddr)[0]
        return None

    tables_path = os.path.join(ROOT, 'vtables.txt')
    if os.path.isfile(tables_path):
        seen, tables = {}, 0
        with open(tables_path) as source:
            for line in source:
                parts = line.split()
                if len(parts) < 3 or int(parts[2]) not in OBJECT_TABLE_SIZES:
                    continue
                tables += 1
                seen.setdefault(word(int(parts[0], 16) + 6 * 8 + 4), []).append(parts[1])
        extra = sorted(set(seen) - set(SLOT6_FUNCTIONS))
        missing = sorted(set(SLOT6_FUNCTIONS) - set(seen))
        check('s1', not extra and not missing,
              '%d object tables (%s entries) use %d slot-6 functions, the %d of the survey'
              % (tables, '/'.join(str(n) for n in OBJECT_TABLE_SIZES), len(seen),
                 len(SLOT6_FUNCTIONS)))
        note('extra %s missing %s' % (['%x' % a for a in extra], ['%x' % a for a in missing]))
        check('s2', seen.get(SPIDER_ON_TOUCH) == ['SmallSpider']
              and len(seen.get(CREATURE_ON_TOUCH, ())) == 72,
              'SmallSpider alone uses 0x2ab8e0; 72 tables use the base handler 0x11a418')
    else:
        print('SKIP  s1   vtables.txt not found: the table half of the survey was not checked')

    # call sites:  lw r,0x48(obj) ... addiu r,r,0x30 ; lh a0,0(r) ; lw f,4(r) ; jalr f
    text_lo, text_hi = 0x100000, 0x3E5C40
    sites = []
    for addr in range(text_lo, text_hi, 4):
        w = word(addr)
        if w is None or (w >> 26) != 0 or (w & 0x3F) != 9 or (w & 0x1F0000):
            continue                                    # not jalr
        target_reg = (w >> 21) & 31
        base = None
        for back in range(addr - 4, addr - 4 * 6, -4):
            x = word(back)
            if x is not None and (x >> 26) == 0x23 and ((x >> 16) & 31) == target_reg:
                base = (x >> 21) & 31 if (x & 0xFFFF) == 4 else None
                at_lw = back
                break
        if base is None:
            continue
        table_reg = None
        for back in range(at_lw - 4, at_lw - 4 * 8, -4):
            x = word(back)
            if x is not None and (x >> 26) == 9 and ((x >> 16) & 31) == base:
                table_reg = (x >> 21) & 31 if (x & 0xFFFF) == 0x30 else None
                at_addiu = back
                break
        if table_reg is None:
            continue
        for back in range(at_addiu - 4, at_addiu - 4 * 8, -4):
            x = word(back)
            if x is not None and (x >> 26) == 0x23 and ((x >> 16) & 31) == table_reg:
                if (x & 0xFFFF) == O_VTABLE:
                    sites.append(addr)
                break
    game = tuple(a for a in sites if a < LOBBY_UI_LO)
    other = [a for a in sites if a >= LOBBY_UI_LO]
    check('s3', game == SLOT6_CALL_SITES and all(a < LOBBY_UI_HI for a in other),
          'slot 6 of a table kept at +0x48 is called at %d places in the game\'s code: %s '
          '(and at %d in the lobby window library, 0x%x-0x%x, whose window classes keep a '
          'table of their own at the same offset)'
          % (len(game), ' '.join('0x%x' % a for a in game), len(other), LOBBY_UI_LO,
             LOBBY_UI_HI))
    # the one guard: obj_moveWithCollision tests the mover's 0x20000 before its first call
    guard = [word(a) for a in (0x14D9AC, 0x14D9B0, 0x14D9B4)]
    check('s4', guard == [0x3C020002, 0x00C21024, 0x54400009],
          'obj_moveWithCollision tests the mover for 0x20000 at 0x14d9ac-0x14d9b4 and skips '
          'the call at 0x14d9d0; Creature_moveBy has no such test before 0x114220')


def cave_references(elf):
    segments, _entry = ee_emu.load_elf_segments(elf)
    hits = []
    for vaddr, blob, _memsz in segments:
        for off in range(0, len(blob) - 3, 4):
            w = struct.unpack_from('<I', blob, off)[0]
            addr = vaddr + off
            inside = CAVE_FN <= addr < CAVE_FN_END
            if CAVE_FN <= w < CAVE_FN_END:
                hits.append(addr)
            op = w >> 26
            if op in (2, 3):
                target = ((addr + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
                if CAVE_FN <= target < CAVE_FN_END and not inside:
                    hits.append(addr)
            elif vaddr == 0x100000 and (op in (1, 4, 5, 6, 7, 20, 21, 22, 23)
                                        or (op == 17 and ((w >> 21) & 31) == 8)):
                target = addr + 4 + ee_emu.sx16(w) * 4
                if CAVE_FN <= target < CAVE_FN_END and not inside:
                    hits.append(addr)
    return hits


def group_p(elf):
    """(p) the patch words."""
    emu = EE(elf)
    wrong = [(a, emu.mem.u32(a), old) for a, old, _new in PATCH if emu.mem.u32(a) != old]
    check('p1', not wrong, 'the %d original words of the patch table are what the executable '
          'holds' % len(PATCH))
    for addr, have, want in wrong:
        note('0x%08x holds %08x, the table says %08x' % (addr, have, want))
    inside = all(CAVE_FN <= a < CAVE_FN_END for a, _o, _n in PATCH[1:])
    hits = cave_references(elf)
    check('p2', inside and not hits,
          'the eight new words 0x%x-0x%x lie in Cyclops_dropClub (0x257ab4-0x257b9f), and no '
          'jump, call, branch or stored pointer in the image leads into that function'
          % (STUB, STUB + 0x1F))
    jal = PATCH[0][2]
    check('p3', jal >> 26 == 3 and ((jal & 0x3FFFFFF) << 2) == STUB
          and emu.mem.u32(CALL_SITE + 4) == 0x02042021,
          'the call site becomes jal 0x%x; its delay slot (addu a0, s0, a0) is not changed'
          % STUB)
    pnach = os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach')
    if os.path.isfile(pnach):
        mine = {a for a, _o, _n in PATCH}
        clash = []
        for title, entries in ee_emu.parse_pnach(pnach):
            if (CALL_SITE, 4, PATCH[0][2]) in entries:
                continue                # this patch itself, once it is in the file
            used = {a for a, _size, _value in entries} & mine
            if used:
                clash.append((title, sorted(used)))
        check('p4', not clash, 'no other section of the patch file writes any of these nine '
              'addresses')
        for title, used in clash:
            note('%s: %s' % (title, ' '.join('0x%x' % a for a in used)))
    else:
        print('SKIP  p4   patch file not found: overlap with other sections was not checked')


def group_u(elf):
    """(u) as shipped, the prediction copy as mover reaches both handlers."""
    for index, (label, flags, is_copy) in enumerate(MOVERS):
        run = move_by(elf, flags, patched=False)
        player = bool(flags & F_PLAYER)
        ok = (run.handler_pcs == {CREATURE_ON_TOUCH, SPIDER_ON_TOUCH}
              and bool(run.touched_flags['creature'] & TOUCHED_BIT) == player
              and bool(run.touched_flags['spider'] & TOUCHED_BIT) == player
              and run.set_state == ([('spider', DEAD_STATE)] if player else [])
              and run.bumped == ['spider', 'creature'] and run.result & 2)
        effect = ('the creature is flagged and the spider is sent to state 0x14 (death)'
                  if player else 'neither changes anything: the mover is not a player')
        check('u%d' % (index + 1), ok, 'unpatched, mover %s: both handlers run; %s'
              % (label, effect))
        note('result %d, set-state %s, bumped %s' % (run.result, run.set_state, run.bumped))


def group_f(elf):
    """(f) with the patch no handler runs for a copy; nothing else changes."""
    for index, (label, flags, is_copy) in enumerate(MOVERS):
        before = move_by(elf, flags, patched=False)
        after = move_by(elf, flags, patched=True)
        ident = 'f%d' % (index + 1)
        if is_copy:
            mover_stores = [s for s in after.stores if s[0] == 'mover']
            ok = (after.stub_ran and not after.handler_pcs and not after.set_state
                  and not after.touched_flags['creature'] and not after.touched_flags['spider']
                  and not [s for s in after.stores if s[0] != 'mover']
                  and mover_stores == [s for s in before.stores if s[0] == 'mover']
                  and after.bumped == ['spider', 'creature'] and after.result == before.result)
            check(ident, ok, 'patched, mover %s: neither handler runs, nothing is stored in '
                  'the two objects, no set-state call; the mover moves as before and is still '
                  'told it bumped both (result %d)' % (label, after.result))
        else:
            ok = (after.stub_ran and after.handler_pcs == before.handler_pcs
                  and after.handler_pcs == {CREATURE_ON_TOUCH, SPIDER_ON_TOUCH}
                  and after.stores == before.stores and after.calls == before.calls
                  and after.set_state == before.set_state and after.bumped == before.bumped
                  and after.result == before.result
                  and after.touched_flags == before.touched_flags)
            check(ident, ok, 'patched, mover %s: both handlers run, and the calls, the stores '
                  'and the result are those of the unpatched run' % label)
        note('stores %d -> %d, calls %d -> %d' % (len(before.stores), len(after.stores),
                                                  len(before.calls), len(after.calls)))


GROUPS = (('s', 'the survey: slot 6 of every object table, and who calls it', group_s),
          ('p', 'the patch words', group_p),
          ('u', 'as shipped: Creature_moveBy hands the mover to the touch handlers', group_u),
          ('f', 'with the patch', group_f))


def find_elf(positional):
    for arg in positional:
        if os.path.isfile(arg):
            return arg
    for candidate in (os.environ.get('CHAMPIONS_ELF'), os.path.join(ROOT, 'SLUS_209.73'),
                      'SLUS_209.73'):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    global VERBOSE
    argv = sys.argv[1:] if argv is None else list(argv)
    VERBOSE = '-v' in argv
    elf = find_elf([a for a in argv if not a.startswith('-')])
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path, or set CHAMPIONS_ELF); nothing was run')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable these addresses belong to '
              '(SHA-256 %s); nothing was run' % (elf, digest))
        return 0
    print('executable: %s  (SHA-256 matches US v2.00)' % elf)
    print('executed in isolation: Creature_moveBy and two touch handlers on objects built here')
    for letter, title, function in GROUPS:
        print('--- %s. %s' % (letter, title))
        try:
            function(elf)
        except EmuError as exc:
            check(letter + '!', False, 'the interpreter stopped: %s' % exc)
        except (AssertionError, LookupError, ValueError, struct.error) as exc:
            check(letter + '!', False, 'this script could not finish the group: %r' % (exc,))
    passed = sum(1 for _, ok in RESULTS if ok)
    print('%d checks: %d PASS, %d FAIL' % (len(RESULTS), passed, len(RESULTS) - passed))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
