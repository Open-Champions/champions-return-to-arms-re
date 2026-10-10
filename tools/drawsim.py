#!/usr/bin/env python3
"""drawsim.py -- globals that per-machine code writes and the lockstep simulation reads.

  python3 -I -B tools/drawsim.py                 the candidate list (strict tier)
  python3 -I -B tools/drawsim.py --loose         also the loose tier (address taken, or an
                                                 access gxref marks '?' that is not confirmed)
  python3 -I -B tools/drawsim.py --tsv           one line per candidate, tab separated
  python3 -I -B tools/drawsim.py --check         exit 1 unless the three known cases are in
                                                 the strict list (0x41b818, 0x41b69d, 0x41b4fc)
  python3 -I -B tools/drawsim.py --roots         the roots of every category, with reasons
  python3 -I -B tools/drawsim.py --why HEX       categories of a function and one call chain
                                                 from a root of each category that reaches it
  python3 -I -B tools/drawsim.py --global HEX    every access to one global, with categories
  python3 -I -B tools/drawsim.py --vcalls [-v]   virtual call sites grouped by (table offset,
                                                 slot), to audit the slot classification
  python3 -I -B tools/drawsim.py --fields        object fields a draw slot stores through `this`
                                                 and a simulation slot of the same class loads
  python3 -I -B tools/drawsim.py --calls         simulation functions that change state and are
                                                 called directly by presentation-only code
  python3 -I -B tools/drawsim.py --stats         sizes of everything, and the blind-spot counts
  python3 -I -B tools/drawsim.py --prediction    second list: globals written by code the
                                                 prediction copy reaches and read by the tick
                                                 (large and over-approximate; not triaged)

What it does
------------
1. Builds a call graph over the function bodies of ghidra_funcs.tsv from disasm/text.asm:
     - direct calls (jal) and jumps out of a function (j);
     - virtual calls: a call site of the form  lw v, OFF(obj); [addiu v, v, n*8];
       lh d, n*8(v); lw f, n*8+4(v); jalr f  is resolved to slot n of every virtual table
       whose constructors store the table pointer at OFF (found by scanning for stores of
       each table's address).  Conservative: every class that keeps its table at that
       offset is a possible receiver.  Game classes (tables with type information) and
       library classes (lobby client, UdpLibrary: tables named vt<address>) share offsets,
       so a call site is resolved only to tables of its own world, decided by the address
       of the call (LIB_ZONES).  Entry 0 of a table (the type-info getter) is not a call;
     - function addresses built in code (lui/addiu giving a function entry) are an edge from
       the function that builds the address, except when the address is the first argument
       of task_add / task_remove (tasks are roots, classified by their flag argument) or of
       net_registerMsgHandler (message handlers are simulation roots);
     - function addresses in data tables are followed only for virtual tables and the
       script built-in table.  The rest are counted under --stats (in this executable they
       are library tables and one camera loader).
2. Classifies each function by which roots reach it:
     S  simulation: net_frameLoop, tasks_run, the run tasks that are simulation, pad_apply,
        the game-message handlers, the script built-ins, and every virtual slot of the
        GameObject, Spell and Skill families except the presentation ones (PRES_SLOTS);
     P  presentation / per machine during play: the draw tasks, the draw slots, the run
        tasks that the project documents classify as per-machine (RUN_TASK_PER_MACHINE),
        what the session loop calls once per displayed frame, the loading-screen thread and
        the vertical-blank handler;
     R  prediction: net_predictLocalPlayer and what the copy's Player_run reaches;
     L  level entry and exit (shared work done outside a tick);
     N  network transport (net_main without the tick and the prediction);
     B  boot and front end (main, the front-end task, character selection, lobby client).
   A function can be in several.  "Presentation only" means P and not S.  The session
   function, net_main and main are "self only": their own accesses count for their
   category, their callees are classified by the root tables.
3. Runs the address tracking of tools/gxref.py (scan, func_starts) over the whole listing
   for every address in the data sections and prints each global that
     - is written by at least one presentation-only function, and
     - is read by at least one simulation function.
   Strict tier: a store on the one side and a load on the other, each reported by gxref
   and confirmed by this tool's own register tracking (constant base, or constant base
   plus a computed index; unlike gxref it forgets caller-saved registers at a call, which
   removes the hits gxref reports through a register that held a lui before a call and a
   returned pointer after it).  This tool also adds the indexed accesses gxref attributes
   to a stale address.  For an indexed access the address is the array
   base plus the displacement; a constant folded into the index register is not seen, so
   the element or field may be a different one of the same array.
   Loose tier (--loose): "address taken" on either side, or an unconfirmed access (shown
   as a lower-case r / w).  Address-taken on the presentation side is nearly always a read.
4. --fields does the same job for object fields, in the one form that can be tracked:
   stores through the first argument (`this`, plus constants and indexes added to it, and
   through the functions `this` is handed to) of a draw slot, matched against loads through
   `this` in the simulation slots of the same class.

Why some run tasks are presentation roots
-----------------------------------------
hud_run, the dialog task, the pause-menu opener, text chat, voice, the save daemon and the
camera task are registered as run tasks and therefore execute inside every lockstep tick,
but they read the raw local controller (g_rawPads), the local camera, audio or card state.
docs/mainloop.md ("Every run task: simulation or not") gives the verdict for each; the
table RUN_TASK_PER_MACHINE copies it.  If they were simulation roots, everything they call
(for instance menu_openInventory, the only writer of the local-menu flag outside the close
functions) would count as simulation and 0x41b69d would not be listed.  The price: lockstep
helpers that only such a task calls (the gold floater tick, the pick-a-player list) show up
as presentation writers and have to be dismissed by reading.

Blind spots -- what this tool cannot see
----------------------------------------
- Struct fields.  A store through a pointer held in a register or loaded from memory (an
  object field, a player-record field reached through a pointer, a pad field reached
  through a pad pointer) is invisible to the global scan.  --fields covers only `this` in
  draw slots; a draw function that writes another object, or a menu function that writes a
  record through a pointer, needs tools/fieldxref.py and reading.
- Indirect addressing.  An array indexed with addu is attributed to its base (see 3); a
  base whose low half lives in the index register (bare lui) is loose tier only.
- Listing order is not execution order.  A constant built in one block and used in another
  can be lost by this tool's linear tracking; gxref's '?' then stays unconfirmed.
- Unresolved indirect calls.  A jalr whose register was not loaded from a table slot in
  the pattern above is not followed (count under --stats).  Resolved calls are
  over-approximated: slot n of every class with the table at the same offset.
- Function pointers stored into objects or globals and called later, callbacks registered
  with the kernel or the IOP (interrupt, thread, RPC) are not followed unless listed in the
  root tables.
- Over-approximation of S hides candidates: a presentation writer that is also reachable
  from any simulation root is not "presentation only", and its globals are listed only if
  another, presentation-only, function writes them too.  net_closeLocalMenus is the main
  case: simulation code calls it, it closes this machine's menus, and so inventory_close,
  shop_close and what they call (the item-list buffer pointer 0x4ebbb0) count as S.
- Per-machine *conditions* inside simulation code (net_isLocalSlot, the local slot, card
  and audio status calls) are not modelled at all.
- Function granularity.  A function that is partly per-frame and partly per-tick
  (tasks_run) gets one classification.
- Code outside ghidra_funcs.tsv bodies is ignored.
- The root tables are knowledge copied from the documents, not derived.
"""
import bisect, collections, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import symtab                                   # noqa: E402
from textinput import text_lines                # noqa: E402
from gxref import scan, func_starts             # noqa: E402

ELF = os.path.join(ROOT, 'SLUS_209.73')

# ---- fixed addresses (all named in names.tsv / symbols/) -------------------------------
TASK_ADD, TASK_REMOVE, TASK_ISRUNNING = 0x19e4a0, 0x19e664, 0x19e5e8
NET_REGISTER_MSG = 0x13da98
NET_FRAMELOOP, NET_PREDICT, NET_MAIN = 0x139e88, 0x131d88, 0x132e90
TASKS_RUN, TASKS_CALL, PAD_APPLY = 0x3226e4, 0x19e798, 0x174410
SESSION, MAIN, PLAYER_RUN = 0x322998, 0x323dcc, 0x1a5030
MAIN_LOOP_PSEUDO = 0x32316c       # names.tsv 'main_loop': a label inside the session function
SCRIPT_BUILTINS = (0x403370, 191)  # {name*, fn*} rows

# Run tasks that execute inside the tick but are per-machine code (docs/mainloop.md
# section 9, "Every run task: simulation or not").  Presentation roots, not simulation roots.
RUN_TASK_PER_MACHINE = {
    0x1db870: ('P', 'HUD Run: raw pads, local slot, local menu flag, camera; opens menus'),
    0x22ff48: ('P', 'Dialog Demon Run: raw pads, audio position and status, camera'),
    0x18e00c: ('P', 'warpMenu: pause-menu opener, raw pads, display-list fill'),
    0x31dc80: ('P', 'textMessageProcess: keyboard'),
    0x31fb30: ('P', 'commProcess: voice hardware'),
    0x2188a8: ('P', 'Async Load/Save Daemon RUN: memory card, local menu, local camera'),
    0x1ebbe0: ('P', 'camera: per machine, no-op in net games'),
    0x1e08f0: ('B', 'frontend: per machine, offline by construction'),
    0x324288: ('B', 'srs: lobby client'),
    0x225428: ('B', 'playerSelectionCache: front end'),
}
# Draw tasks that exist only in the front end.
DRAW_TASK_FRONT_END = {0x225478: 'playerSelection'}

# Virtual slots that are presentation, by (table-pointer offset, slot).  Everything else in
# those three families is a simulation root.
#   0x48 GameObject family: 5 draw.  13 (interact prompt) and 16 (get model) and 19 (display
#        name) are called from both sides and are roots of both.
#   0x14 Spell: 3 draw.     0x60 Skill: 4 describeRank, 6 describeExtra, 7 getIcon (menus).
PRES_SLOTS = {(0x48, 5), (0x14, 3), (0x60, 4), (0x60, 6), (0x60, 7)}
BOTH_SLOTS = {(0x48, 13), (0x48, 16), (0x48, 19)}
ROOT_FAMILIES = (0x48, 0x14, 0x60)
CLONE_SLOT = (0x48, 15)            # only caller: the prediction rebase in net_frameLoop

# Presentation roots that are not tasks or slots (address: reason).
PRES_EXTRA = {
    0x32187c: ('P', 'loadscreen_renderLoop: loading-screen thread'),
    0x19b6e4: ('P', 'vertical-blank interrupt handler'),
    0x1e20d0: ('B', 'frontend_start'),
    0x3236bc: ('B', 'mainloop_runModalCallback: private frame loop (boot screens, LAN lobby)'),
    0x3237f8: ('L', 'mainloop_runModalCallbackWithDisplayReset: wait for a save before a net level change'),
}
# Address ranges of the session function, classifying its direct callees
# (docs/mainloop.md sections 5 and 7).
SESSION_RANGES = [
    (0x322998, 0x322b38, 'B'),     # session start
    (0x322b3c, 0x322cd0, 'P'),     # steps A-D: idle voice, pending-level cancel, comm flag
    (0x322cd4, 0x3231d4, 'L'),     # step E: the level change
    (0x3231d8, 0x3234d0, 'P'),     # step F: the frame
    (0x3234d4, 0x3235a7, 'L'),     # session exit
]
SESSION_SKIP = {NET_MAIN, TASKS_RUN, TASKS_CALL}   # classified on their own

DATA_LO, DATA_HI = 0x3e9c00, 0x90a400   # .data ... .bss
# Simulation entry points that change state without storing to a global themselves
# (they work on objects, records or the script machine); always shown by --calls.
CROSS_ALWAYS = {0x1ed694, 0x1edac0, 0x14f248, 0x14f290, 0x14f200, 0x14fdb8, 0x1b7158,
                0x1c1868, 0x1c1cb0, 0x1d3150, 0x1e8230, 0x1509d0}
PURE_VIRTUAL = 0x3ad348
LIB_ZONES = ((0x324288, 0x3ad310), (0x3d2280, 0x3e5a00))   # lobby client and libraries; their inline bodies


def in_lib(a):
    return any(lo <= a < hi for lo, hi in LIB_ZONES)
CAT = 'SPRLNB'


class AnyData:
    """Target set for gxref.scan: every address in the data sections."""
    def __contains__(self, v):
        return DATA_LO <= v < DATA_HI


def regnum(r):
    r = r.strip()
    if not r.startswith('$'):
        return None
    r = r[1:]
    if r.isdigit():
        return int(r)
    return {'zero': 0, 'at': 1, 'v0': 2, 'v1': 3, 'a0': 4, 'a1': 5, 'a2': 6, 'a3': 7,
            'gp': 28, 'sp': 29, 'fp': 30, 's8': 30, 'ra': 31}.get(r)


def imm(s):
    try:
        return int(s, 0)
    except ValueError:
        return None


CALLER_SAVED = tuple(range(1, 16)) + (24, 25, 31)
STORES = {'sw', 'sh', 'sb', 'swc1', 'sd', 'sq', 'swl', 'swr', 'sdl', 'sdr'}
NO_DEST = STORES | {'mtc1', 'dmtc1', 'ctc1', 'ctc2', 'qmtc2', 'mtc0', 'mthi', 'mtlo', 'mthi1',
                    'mtlo1', 'mtsa', 'jr', 'j', 'teq', 'tge', 'tlt', 'tne', 'cache', 'pref',
                    'syscall', 'break', 'nop', 'sync', 'mult', 'multu', 'div', 'divu', 'dmult',
                    'dmultu', 'ddiv', 'ddivu', 'mult1', 'multu1', 'div1', 'divu1'}
MEM = re.compile(r'^(\$\w+), (-?0x[0-9a-f]+|-?\d+)\((\$\w+)\)$')
LINE = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$')


class Program:
    def __init__(self, root=ROOT):
        self.root = root
        self.names = symtab.load(root)
        self._load_funcs()
        self._load_vtables()
        self._load_ins()
        self._pass()
        self._roots()
        self._reach()

    # ---- inputs -------------------------------------------------------------------------
    def _load_funcs(self):
        self.bodies = {}
        iv = []
        for l in text_lines(os.path.join(self.root, 'ghidra_funcs.tsv')):
            p = l.rstrip('\n').split('\t')
            try:
                ent = int(p[0], 16)
            except ValueError:
                continue
            rs = [tuple(int(x, 16) for x in r.split('-')) for r in p[2].split(',') if r]
            self.bodies[ent] = rs
            for lo, hi in rs:
                iv.append((lo, hi, ent))
        iv.sort()
        self._iv = iv
        self._ivlo = [x[0] for x in iv]

    def fn_of(self, a):
        i = bisect.bisect_right(self._ivlo, a) - 1
        while i >= 0 and i >= bisect.bisect_right(self._ivlo, a) - 4:
            lo, hi, ent = self._iv[i]
            if lo <= a <= hi:
                return ent
            i -= 1
        return None

    def name(self, a):
        n = self.names.get(a)
        return n if n else '%x' % a

    def _load_vtables(self):
        from ps2elf import Elf
        from vtab import find_vtables
        self.elf = Elf(ELF)
        self.vtables = {}                 # table address -> (class, [fn by slot-1])
        for addr, (nm, ents) in find_vtables(self.elf).items():
            self.vtables[addr] = (nm, [fn for _, fn in ents])

    def _load_ins(self):
        ins = []
        for l in text_lines(os.path.join(self.root, 'disasm/text.asm')):
            m = LINE.match(l)
            if m:
                ins.append((int(m.group(1), 16), m.group(2), m.group(3).split('<')[0].strip()))
        self.ins = ins

    # ---- one linear pass: calls, virtual calls, address-taken functions, task table -------
    def _pass(self):
        calls = collections.defaultdict(set)        # direct
        taken = collections.defaultdict(dict)       # f -> {target: site}
        vsites = []                                 # (site, f, family offset, slot, delta seen)
        unresolved = collections.Counter()          # f -> jalr sites not resolved
        self.tasks = []                             # (site, fn, priority, name, flags)
        self.msg_handlers = []                      # (site, fn)
        self.callsites = collections.defaultdict(list)   # callee -> [(site, f)]
        self.rtti_sites = 0
        # access sites whose base register holds a constant, or a constant plus a computed
        # index, by this tool's own tracking: site -> (address, indexed?, R/W)
        self.confirmed = {}
        self.unresolved_sites = []
        family = collections.defaultdict(collections.Counter)   # vtable -> {offset: n}
        entries = self.bodies
        vt = self.vtables
        reg = {}
        cur = None
        pending = None
        consumed = set()                            # sites whose address went to task_add etc.
        ins = self.ins
        n = len(ins)
        i = 0
        while i < n:
            a, op, ar = ins[i]
            f = self.fn_of(a)
            if f is None:           # padding between blocks: keep the state of the function
                i += 1
                continue
            if f != cur:
                cur = f
                reg = {}
                self._lui = {}
                pending = None
            p = [x.strip() for x in ar.split(',')] if ar else []
            call = None
            if op == 'jal' or op == 'j':
                t = imm(ar)
                if t is not None:
                    tf = self.fn_of(t)
                    if tf is None and t in entries:
                        tf = t
                    if tf is not None and (op == 'jal' or tf != f):
                        calls[f].add(tf)
                        self.callsites[tf].append((a, f))
                    if op == 'jal':
                        call = ('jal', t, a)
            elif op == 'jalr':
                r = regnum(p[-1]) if p else None
                call = ('jalr', reg.get(r), a)
            else:
                self._step(op, p, ar, reg, f, a, taken, family, vt, entries)
            if pending is not None:
                kind, tgt, site = pending
                pending = None
                if kind == 'jal':
                    if tgt in (TASK_ADD, TASK_REMOVE):
                        v = reg.get(4)
                        if v and v[0] == 'c':
                            consumed.add((f, v[1]))
                            if tgt == TASK_ADD:
                                pr, nm, fl = reg.get(5), reg.get(6), reg.get(7)
                                self.tasks.append((site, v[1], pr[1] if pr and pr[0] == 'c' else None,
                                                   self.elf.cstr(nm[1]) if nm and nm[0] == 'c' else None,
                                                   fl[1] if fl and fl[0] == 'c' else None))
                    elif tgt == NET_REGISTER_MSG:
                        v = reg.get(4)
                        if v and v[0] == 'c':
                            consumed.add((f, v[1]))
                            self.msg_handlers.append((site, v[1]))
                else:
                    so = None
                    if tgt and tgt[0] == 'ld' and tgt[2] == 0 and tgt[4] is not None:
                        so = tgt[4][1] + tgt[1] - 4
                    if so is not None and so % 8 == 0 and so > 0:
                        vsites.append((site, f, tgt[4][0], so // 8, so in tgt[4][2]))
                    elif so == 0:
                        self.rtti_sites += 1          # entry 0: the type-info getter
                    else:
                        unresolved[f] += 1
                        self.unresolved_sites.append((site, f))
                for r in CALLER_SAVED:
                    reg.pop(r, None)
            if call is not None:
                pending = call
            i += 1
        for (f, t) in consumed:
            taken[f].pop(t, None)
        self.calls, self.taken, self.vsites, self.unresolved = calls, taken, vsites, unresolved
        self.family = {}
        for t, c in family.items():
            self.family[t] = c.most_common(1)[0][0]
        # Two worlds share table-pointer offsets: the game's classes (all have type
        # information) and the library code linked after it (lobby client, UdpLibrary; no
        # type information, tables named vt<address>).  A call site is resolved only to
        # tables of its own world.
        self.slots = collections.defaultdict(set)   # (lib?, offset, slot) -> functions
        for t, (nm, fns) in vt.items():
            off = self.family.get(t)
            if off is None:
                continue
            lib = nm.startswith('vt')
            for s, fn in enumerate(fns, 1):
                if fn in entries and fn != PURE_VIRTUAL:
                    self.slots[(lib, off, s)].add(fn)
        self.vedges = collections.defaultdict(set)
        self.vsite_unknown_family = 0
        for site, f, off, slot, seen in vsites:
            tg = self.slots.get((in_lib(site), off, slot))
            if tg:
                self.vedges[f] |= tg
            else:
                self.vsite_unknown_family += 1

    def _step(self, op, p, ar, reg, f, a, taken, family, vt, entries):
        if op == 'lui' and len(p) == 2:
            v = imm(p[1])
            d = regnum(p[0])
            if v is not None and d is not None:
                reg[d] = ('c', (v << 16) & 0xffffffff)
                self._lui[d] = (v << 16) & 0xffffffff
            return
        if op in ('addiu', 'daddiu', 'ori') and len(p) == 3:
            d, s, v = regnum(p[0]), regnum(p[1]), imm(p[2])
            st = reg.get(s) if s != 0 else ('c', 0)
            if d is None:
                return
            if st and v is not None and st[0] == 'c':
                val = (st[1] | v) if op == 'ori' else (st[1] + v) & 0xffffffff
                reg[d] = ('c', val)
                if val in entries and 0x100000 < val < 0x3e5000:
                    taken[f].setdefault(val, a)
            elif not st and v is not None and s in self._lui and op != 'ori' \
                    and (self._lui[s] + v) & 0xffffffff in entries \
                    and 0x100000 < (self._lui[s] + v) & 0xffffffff < 0x3e5000:
                # the lui is in another block (listing order is not execution order); an
                # exact function entry is unlikely to come out of this by accident
                taken[f].setdefault((self._lui[s] + v) & 0xffffffff, a)
                reg.pop(d, None)
            elif st and v is not None and st[0] == 'ci' and op != 'ori':
                reg[d] = ('ci', (st[1] + v) & 0xffffffff)
            elif st and v is not None and st[0] == 'ld' and op != 'ori':
                reg[d] = ('ld', st[1], st[2] + v, st[3], st[4])
            else:
                reg.pop(d, None)
            return
        if op in ('move',) and len(p) == 2:
            d, s = regnum(p[0]), regnum(p[1])
            if d is None:
                return
            if s == 0:
                reg[d] = ('c', 0)
            elif s in reg:
                reg[d] = reg[s]
            else:
                reg.pop(d, None)
            return
        if op in ('addu', 'daddu', 'or') and len(p) == 3 and regnum(p[2]) == 0:
            d, s = regnum(p[0]), regnum(p[1])
            if d is not None:
                if s in reg:
                    reg[d] = reg[s]
                else:
                    reg.pop(d, None)
            return
        if op in ('addu', 'daddu') and len(p) == 3:
            # constant base plus a computed index: still an address inside that global
            d, s, t = regnum(p[0]), regnum(p[1]), regnum(p[2])
            st, tt = reg.get(s), reg.get(t)
            cs = st if st and st[0] in ('c', 'ci') else None
            ct = tt if tt and tt[0] in ('c', 'ci') else None
            if d is not None:
                if (cs is None) != (ct is None) and (cs or ct)[1] >= DATA_LO:
                    reg[d] = ('ci', (cs or ct)[1])
                else:
                    reg.pop(d, None)
            return
        m = MEM.match(ar)
        if m:
            r, off, b = regnum(m.group(1)), imm(m.group(2)), regnum(m.group(3))
            bt0 = reg.get(b)
            if bt0 and bt0[0] in ('c', 'ci') and off is not None:
                self.confirmed[a] = ((bt0[1] + off) & 0xffffffff, bt0[0] == 'ci',
                                     'W' if op in STORES else 'R')
            if op == 'sw':
                st = reg.get(r)
                if st and st[0] == 'c' and st[1] in vt and b != 29:
                    family[st[1]][off] += 1
                return
            if op in STORES:
                return
            bt = reg.get(b)
            if op == 'lh' and bt and bt[0] == 'ld':
                bt[3].add(bt[2] + off)
                if r is not None:
                    reg.pop(r, None)
                return
            if op == 'lw' and r is not None:
                # a loaded word may be an object pointer, a table pointer or a function
                # pointer; remember the displacement it came from and what it was loaded
                # through, and decide at the jalr
                if b == 29:
                    reg.pop(r, None)
                elif bt and bt[0] == 'ld':
                    reg[r] = ('ld', off, 0, set(), (bt[1], bt[2], bt[3]))
                else:
                    reg[r] = ('ld', off, 0, set(), None)
                return
            if r is not None and not m.group(1).startswith('$f'):
                reg.pop(r, None)
            return
        if p and op not in NO_DEST and not op.startswith('b'):
            d = regnum(p[0])
            if d is not None and not p[0].startswith('$f'):
                reg.pop(d, None)

    # ---- roots ------------------------------------------------------------------------------
    def _roots(self):
        R = {c: {} for c in CAT}          # category -> {function: reason}
        self.selfonly = {}                # function -> categories it has without propagating
        ent = self.bodies

        def add(c, f, why):
            if f in ent:
                R[c].setdefault(f, why)

        add('S', NET_FRAMELOOP, 'net_frameLoop')
        add('S', TASKS_RUN, 'tasks_run')
        add('S', PAD_APPLY, 'pad_apply')
        for site, fn, pr, nm, fl in self.tasks:
            label = "task '%s' pri %s flags %s (task_add at %x)" % (nm, pr, fl, site)
            if fl is not None and fl & 1:
                add('B' if fn in DRAW_TASK_FRONT_END else 'P', fn, 'draw ' + label)
            elif fn in RUN_TASK_PER_MACHINE:
                add(RUN_TASK_PER_MACHINE[fn][0], fn, 'per-machine run ' + label)
            else:
                add('S', fn, 'run ' + label)
        for site, fn in self.msg_handlers:
            add('S', fn, 'game-message handler (registered at %x)' % site)
        base, cnt = SCRIPT_BUILTINS
        for k in range(cnt):
            fn = self.elf.u32(base + k * 8 + 4)
            add('S', fn, 'script built-in %s' % self.elf.cstr(self.elf.u32(base + k * 8)))
        for (lib, off, slot), fns in self.slots.items():
            if lib or off not in ROOT_FAMILIES:
                continue
            for fn in fns:
                why = 'virtual slot %d of a class with its table at +0x%x' % (slot, off)
                if (off, slot) in PRES_SLOTS:
                    add('P', fn, why)
                elif (off, slot) in BOTH_SLOTS:
                    add('S', fn, why); add('P', fn, why)
                else:
                    add('S', fn, why)
                if (off, slot) == CLONE_SLOT:
                    add('R', fn, why + ' (clone)')
        for f, (c, why) in PRES_EXTRA.items():
            add(c, f, why)
        add('R', NET_PREDICT, 'net_predictLocalPlayer')
        add('R', PLAYER_RUN, "the copy's run function, called through slot 4 by net_predictLocalPlayer")
        # the session function: classify its direct callees by where the call is
        for callee, sites in self.callsites.items():
            for site, f in sites:
                if f not in (SESSION, MAIN_LOOP_PSEUDO) or callee in SESSION_SKIP:
                    continue
                for lo, hi, c in SESSION_RANGES:
                    if lo <= site <= hi and callee not in PRES_EXTRA:
                        add(c, callee, 'called by the session loop at %x' % site)
        self.selfonly[SESSION] = 'PL'
        self.selfonly[MAIN_LOOP_PSEUDO] = 'P'
        self.selfonly[NET_MAIN] = 'PN'
        self.selfonly[MAIN] = 'B'
        add('N', NET_MAIN, 'net_main')
        add('B', MAIN, 'main')
        self.roots = R

    # ---- reachability -----------------------------------------------------------------------
    def succ(self, f):
        return self.calls.get(f, set()) | self.vedges.get(f, set()) | set(self.taken.get(f, {}))

    def _reach(self):
        self.reach = {}
        self.parent = {}
        stops = {
            'S': set(RUN_TASK_PER_MACHINE) | {NET_PREDICT, NET_MAIN, SESSION, MAIN_LOOP_PSEUDO, MAIN},
            'P': {NET_MAIN, NET_FRAMELOOP, TASKS_RUN, TASKS_CALL, SESSION, MAIN_LOOP_PSEUDO, MAIN},
            'R': {NET_MAIN, NET_FRAMELOOP, TASKS_RUN, SESSION, MAIN_LOOP_PSEUDO, MAIN},
            'L': {NET_MAIN, NET_FRAMELOOP, TASKS_RUN, SESSION, MAIN_LOOP_PSEUDO, MAIN},
            'N': {NET_FRAMELOOP, NET_PREDICT, TASKS_RUN, SESSION, MAIN_LOOP_PSEUDO, MAIN},
            'B': {SESSION, MAIN_LOOP_PSEUDO, NET_MAIN, NET_FRAMELOOP, TASKS_RUN},
        }
        for c in CAT:
            seen = dict.fromkeys(self.roots[c])
            par = {}
            q = collections.deque(self.roots[c])
            stop = stops[c] - set(self.roots[c])
            # the prediction root must not fan out through its own slot-4 call
            while q:
                f = q.popleft()
                if c == 'R' and f == NET_PREDICT:
                    nxt = self.calls.get(f, set())
                elif f in self.selfonly and f not in (NET_MAIN,) and c != 'B':
                    nxt = ()
                elif f == NET_MAIN and c != 'N':
                    nxt = ()
                else:
                    nxt = self.succ(f)
                for g in nxt:
                    if g in seen or g in stop:
                        continue
                    seen[g] = None
                    par[g] = f
                    q.append(g)
            self.reach[c] = set(seen)
            self.parent[c] = par
        for f, cs in self.selfonly.items():
            for c in cs:
                self.reach[c].add(f)
        self.cat = collections.defaultdict(str)
        for c in CAT:
            for f in self.reach[c]:
                self.cat[f] += c

    def chain(self, c, f):
        out = [f]
        par = self.parent[c]
        while out[-1] in par and len(out) < 40:
            out.append(par[out[-1]])
        return out

    # ---- global accesses --------------------------------------------------------------------
    def accesses(self):
        acc = collections.defaultdict(lambda: collections.defaultdict(list))  # v -> f -> [(site, kind)]
        self.unconfirmed = 0
        self.unconfirmed_sure = 0
        lines = ('%8x:\t%s\t%s' % (a, op, ar) for a, op, ar in self.ins)
        seen = set()
        for v, a, kind in scan(lines, AnyData(), func_starts(self.root)):
            f = self.fn_of(a)
            if f is None:
                continue
            if kind[0] in 'RW':
                mine = self.confirmed.get(a)
                if mine is None or mine[0] != v or (kind.endswith('?') and v & 0xffff == 0):
                    # gxref kept a lui value that this tool's own tracking does not see at
                    # the access: either the register was rewritten in between ('?' in
                    # gxref), or a call came in between and the register is one a call
                    # does not preserve (gxref does not model that).  Unconfirmed.
                    if not kind.endswith('?'):
                        self.unconfirmed_sure += 1
                    kind = kind[0].lower()
                    self.unconfirmed += 1
            if kind[0] in 'RW':
                seen.add((a, v))
            acc[v][f].append((a, kind))
        # indexed accesses gxref attributes to a stale address or not at all
        self.added = 0
        for a, (v, indexed, k) in self.confirmed.items():
            if indexed and (a, v) not in seen and DATA_LO <= v < DATA_HI:
                f = self.fn_of(a)
                if f is not None:
                    # a bare lui with the whole offset in the index register says nothing
                    # about which global it is: loose tier only
                    acc[v][f].append((a, k + '?' if v & 0xffff else k.lower()))
                    self.added += 1
        return acc


def this_fields(P):
    """Per function: fields accessed through the first argument ("this").

    Returns {function: (stores {offset: [site]}, loads {offset: [site]}, callees given this)}.
    Linear tracking: $a0 is `this` at entry, copies made with move are followed, a register
    is forgotten when anything else writes it or (for caller-saved registers) after a call."""
    out = {}
    ins = P.ins
    idx = {a: i for i, (a, _, _) in enumerate(ins)}
    LOADS = {'lw', 'lh', 'lhu', 'lb', 'lbu', 'lwc1', 'ld', 'lwu', 'lq'}
    for f, ranges in P.bodies.items():
        st, ld, sub = collections.defaultdict(list), collections.defaultdict(list), set()
        this = {4: (0, False)}        # register -> (constant added to this, index added too?)
        pend = None
        for lo, hi in ranges:
            i = idx.get(lo)
            if i is None:
                continue
            while i < len(ins) and ins[i][0] <= hi:
                a, op, ar = ins[i]
                p = [x.strip() for x in ar.split(',')] if ar else []
                call = None
                if op == 'jal':
                    call = imm(ar)
                elif op == 'jalr':
                    call = -1
                else:
                    m = MEM.match(ar)
                    if m:
                        r, off, b = regnum(m.group(1)), imm(m.group(2)), regnum(m.group(3))
                        if b in this and off is not None:
                            k, ix = this[b]
                            (st if op in STORES else ld)[(k + off, ix)].append(a)
                        if op in LOADS and r is not None and not m.group(1).startswith('$f'):
                            this.pop(r, None)
                    elif op == 'move' and len(p) == 2:
                        d, sr = regnum(p[0]), regnum(p[1])
                        if sr in this:
                            this[d] = this[sr]
                        else:
                            this.pop(d, None)
                    elif op in ('addiu', 'daddiu') and len(p) == 3 and regnum(p[1]) in this \
                            and imm(p[2]) is not None:
                        k, ix = this[regnum(p[1])]
                        this[regnum(p[0])] = (k + imm(p[2]), ix)
                    elif op in ('addu', 'daddu', 'or') and len(p) == 3:
                        d, sr, tr = regnum(p[0]), regnum(p[1]), regnum(p[2])
                        if tr == 0 and sr in this:
                            this[d] = this[sr]
                        elif op != 'or' and (sr in this) != (tr in this):
                            # this + a computed index: a field array starting at that offset
                            this[d] = (this[sr if sr in this else tr][0], True)
                        else:
                            this.pop(d, None)
                    elif p and op not in NO_DEST and not op.startswith('b') and not p[0].startswith('$f'):
                        this.pop(regnum(p[0]), None)
                if pend is not None:
                    if pend > 0 and this.get(4) == (0, False):
                        tf = P.fn_of(pend)
                        if tf is not None:
                            sub.add(tf)
                    for r in CALLER_SAVED:
                        this.pop(r, None)
                    pend = None
                if call is not None:
                    pend = call
                i += 1
        out[f] = (st, ld, sub)
    return out


def closure_fields(tf, f, which, depth=4, seen=None):
    """Offsets `f` stores (which=0) or loads (which=1) through this, including the functions
    it hands this to, to a fixed depth."""
    seen = seen if seen is not None else set()
    if f in seen or f not in tf:
        return {}
    seen.add(f)
    res = {o: [(f, s[0])] for o, s in tf[f][which].items()}
    if depth:
        for g in tf[f][2]:
            for o, v in closure_fields(tf, g, which, depth - 1, seen).items():
                res.setdefault(o, []).extend(v)
    return res


def fields_report(P):
    """Object fields a draw slot stores through `this` and a simulation slot of the same
    class loads through `this`."""
    tf = this_fields(P)
    rows = collections.defaultdict(lambda: [set(), set()])   # (writer fn, offset) -> [classes, readers]
    for t, (nm, fns) in sorted(P.vtables.items()):
        off = P.family.get(t)
        if nm.startswith('vt') or off not in ROOT_FAMILIES:
            continue
        draw, sim = [], []
        for slot, fn in enumerate(fns, 1):
            if fn not in P.bodies:
                continue
            if (off, slot) in PRES_SLOTS:
                draw.append(fn)
            elif (off, slot) not in BOTH_SLOTS:
                sim.append(fn)
        if not draw:
            continue
        w = {}
        for fn in draw:
            for o, v in closure_fields(tf, fn, 0).items():
                w.setdefault(o, []).extend(v)
        r = {}
        for fn in sim:
            for o, v in closure_fields(tf, fn, 1).items():
                r.setdefault(o, []).extend(v)
        # an indexed store (array inside the object) meets any load at or above its base
        hits = set(w) & set(r)
        for (ko, kix) in w:
            if kix:
                hits |= {(ko, kix)} if any(ro[0] >= ko for ro in r) else set()
        for o in sorted(hits):
            if o not in r:
                r[o] = [x for ro, v in r.items() if ro[0] >= o[0] and ro[0] < o[0] + 0x40 for x in v]
                if not r[o]:
                    continue
            for wf, site in w[o]:
                if 'S' in P.cat.get(wf, ''):
                    continue          # the storing function is itself simulation code
                rows[(wf, o, site)][0].add(nm)
                rows[(wf, o, site)][1] |= {rf for rf, _ in r[o]}
    return rows


def crossings(P, acc):
    """Calls from presentation-only functions into simulation code that changes state.

    A callee counts when simulation roots reach it and it stores, in its own body, to a
    global that some simulation function loads (confirmed accesses only), or when it is
    one of the entry points in CROSS_ALWAYS.  Direct calls and built function addresses
    only; the virtual calls are under --vcalls."""
    sim_read = set()
    for v, fs in acc.items():
        if any('S' in P.cat.get(f, '') and any(k[0] == 'R' for _, k in s) for f, s in fs.items()):
            sim_read.add(v)
    writes = collections.defaultdict(set)
    for v in sim_read:
        for f, s in acc[v].items():
            if any(k[0] == 'W' for _, k in s):
                writes[f].add(v)
    rows = collections.defaultdict(dict)
    for callee, sites in P.callsites.items():
        if 'S' not in P.cat.get(callee, ''):
            continue
        if not (writes.get(callee) or callee in CROSS_ALWAYS):
            continue
        for site, f in sites:
            if pres_only(P, f) and f not in P.selfonly:
                rows[callee].setdefault(f, site)
    return rows, writes


def pres_only(P, f):
    c = P.cat.get(f, '')
    return 'P' in c and 'S' not in c


def fmt_fn(P, f, sites, limit=4):
    s = ' '.join('%x:%s' % (a, k) for a, k in sites[:limit])
    if len(sites) > limit:
        s += ' +%d' % (len(sites) - limit)
    return '%-32s [%s] %s' % (P.name(f), P.cat.get(f, '-') or '-', s)


def candidates(P, acc, loose=False, writer=pres_only, reader=None):
    if reader is None:
        reader = lambda P, f: 'S' in P.cat.get(f, '')
    out = []
    for v in sorted(acc):
        fs = acc[v]
        W, Rd, tier = [], [], 'strict'
        for f, sites in fs.items():
            kinds = {k[0] for _, k in sites}
            if writer(P, f) and 'W' in kinds:
                W.append(f)
            if reader(P, f) and 'R' in kinds:
                Rd.append(f)
        if not (W and Rd):
            if not loose:
                continue
            W2 = [f for f, s in fs.items() if writer(P, f) and {k[0] for _, k in s} & {'W', 'w', '&'}]
            R2 = [f for f, s in fs.items() if reader(P, f) and {k[0] for _, k in s} & {'R', 'r', '&'}]
            if not (W2 and R2):
                continue
            W, Rd, tier = W2, R2, 'loose'
        out.append((v, tier, sorted(W), sorted(Rd)))
    return out


def main(argv):
    P = Program()
    names = P.names
    if '--roots' in argv:
        for c in CAT:
            print('== %s: %d roots, %d functions reached' % (c, len(P.roots[c]), len(P.reach[c])))
            for f, why in sorted(P.roots[c].items()):
                print('   %08x %-34s %s' % (f, P.name(f), why))
        print('== tasks found at task_add call sites: %d' % len(P.tasks))
        for site, fn, pr, nm, fl in sorted(P.tasks, key=lambda t: ((t[4] or 0) & 1, t[2] or 0)):
            print('   %-5s pri %-5s %08x %-28s %r' % ('draw' if (fl or 0) & 1 else 'run', pr, fn, P.name(fn), nm))
        return 0
    if '--why' in argv:
        f = int(argv[argv.index('--why') + 1], 16)
        f = P.fn_of(f) or f
        print('%08x %s  categories [%s]' % (f, P.name(f), P.cat.get(f, '') or '-'))
        for c in P.cat.get(f, ''):
            ch = P.chain(c, f)
            print('  %s: %s' % (c, ' < '.join(P.name(x) for x in ch)))
            print('     root: %s' % P.roots[c].get(ch[-1], 'self-only' if ch[-1] in P.selfonly else '?'))
        return 0
    if '--vcalls' in argv:
        by = collections.defaultdict(list)
        for site, f, off, slot, seen in P.vsites:
            if not in_lib(site):
                by[(off, slot)].append((site, f))
        for (off, slot) in sorted(by):
            tg = P.slots.get((False, off, slot), ())
            cats = collections.Counter(P.cat.get(f, '-') or '-' for _, f in by[(off, slot)])
            print('table at +0x%x slot %d: %d sites, %d targets; caller categories %s'
                  % (off, slot, len(by[(off, slot)]), len(tg), dict(cats)))
            if '-v' in argv:
                for site, f in by[(off, slot)]:
                    print('      %x in %s [%s]' % (site, P.name(f), P.cat.get(f, '')))
        return 0
    if '--fields' in argv:
        rows = fields_report(P)
        print('# object fields stored through `this` by a draw slot (or what it hands `this` to)')
        print('# and loaded through `this` by a simulation slot of the same class: %d store sites' % len(rows))
        for (wf, o, site) in sorted(rows, key=lambda k: (k[1], k[0], k[2])):
            cls, rd = rows[(wf, o, site)]
            print('+0x%-6s stored at %x in %-28s classes: %-40s readers: %s' % (
                '%x%s' % (o[0], '[i]' if o[1] else ''), site, P.name(wf), (', '.join(sorted(cls)[:4]) + (' +%d' % (len(cls) - 4) if len(cls) > 4 else '')),
                ', '.join(sorted(P.name(x) for x in rd)[:6]) + (' +%d' % (len(rd) - 6) if len(rd) > 6 else '')))
        return 0
    acc = P.accesses()
    if '--check' in argv:
        got = {c[0] for c in candidates(P, acc)}
        miss = [v for v in (0x41b818, 0x41b69d, 0x41b4fc) if v not in got]
        print('strict candidates: %d; known cases missing: %s' % (len(got), ', '.join('%x' % v for v in miss) or 'none'))
        return 1 if miss else 0
    if '--calls' in argv:
        rows, writes = crossings(P, acc)
        print('# simulation functions that change state and are called directly by presentation-only code: %d' % len(rows))
        for callee in sorted(rows):
            g = sorted(writes.get(callee, ()))
            print('%08x %-30s writes %s' % (callee, P.name(callee),
                  ' '.join(names.get(v, '%x' % v) for v in g[:5]) + (' +%d' % (len(g) - 5) if len(g) > 5 else '') if g else '(objects, records or scripts)'))
            for f, site in sorted(rows[callee].items()):
                print('      from %-30s at %x' % (P.name(f), site))
        return 0
    if '--global' in argv:
        v = int(argv[argv.index('--global') + 1], 16)
        for f, sites in sorted(acc.get(v, {}).items()):
            print('  ' + fmt_fn(P, f, sites, 12))
        return 0
    if '--stats' in argv:
        print('functions: %d   instructions: %d' % (len(P.bodies), len(P.ins)))
        print('direct call edges: %d' % sum(len(v) for v in P.calls.values()))
        print('virtual tables: %d, with a known table-pointer offset: %d'
              % (len(P.vtables), len(P.family)))
        print('table-pointer offsets: %s' % dict(collections.Counter(P.family.values()).most_common(8)))
        print('jalr sites resolved as virtual: %d (of which no table matches offset+slot: %d)'
              % (len(P.vsites), P.vsite_unknown_family))
        print('jalr sites not resolved: %d' % sum(P.unresolved.values()))
        print('function addresses built in code (edges): %d' % sum(len(v) for v in P.taken.values()))
        for c in CAT:
            print('category %s: %d roots, %d functions' % (c, len(P.roots[c]), len(P.reach[c])))
        po = [f for f in P.bodies if pres_only(P, f)]
        print('presentation-only functions: %d' % len(po))
        print('functions in no category: %d' % sum(1 for f in P.bodies if not P.cat.get(f)))
        print('globals with any access: %d' % len(acc))
        print("gxref accesses not confirmed by this tool's tracking (loose tier only): %d, of which gxref was certain: %d"
              % (P.unconfirmed, P.unconfirmed_sure))
        print('indexed accesses added by this tool (constant base + computed index): %d' % P.added)
        # data words holding function entries outside virtual tables and the built-in table
        known = set()
        for t, (nm, fns) in P.vtables.items():
            for k in range(len(fns) + 2):
                known.add(t + k * 8 + 4)
        b, cnt = SCRIPT_BUILTINS
        for k in range(cnt):
            known.add(b + k * 8 + 4)
        loose_ptrs = collections.Counter()
        for sec in ('.data', '.rodata', '.sdata'):
            sa, so, sz = P.elf.sections[sec]
            for o in range(0, sz - 3, 4):
                w = P.elf.u32(sa + o)
                if w in P.bodies and (sa + o) not in known:
                    loose_ptrs[P.cat.get(w, '') or '-'] += 1
        print('data words holding a function entry, not in a virtual table or the built-in table: %d, by category of the function: %s'
              % (sum(loose_ptrs.values()), dict(loose_ptrs)))
        return 0
    if '--prediction' in argv:
        wr = lambda P, f: 'R' in P.cat.get(f, '')
        cands = candidates(P, acc, '--loose' in argv, writer=wr)
        title = 'written by a function the prediction copy reaches, read by a simulation function'
    else:
        cands = candidates(P, acc, '--loose' in argv)
        title = 'written by a presentation-only function, read by a simulation function'
    if '--tsv' in argv:
        for v, tier, W, Rd in cands:
            print('%08x\t%s\t%s\t%s\t%s' % (v, tier, names.get(v, ''),
                                            ','.join(P.name(f) for f in W), ','.join(P.name(f) for f in Rd)))
        return 0
    print('# %s' % title)
    ns = sum(1 for c in cands if c[1] == 'strict')
    print('# %d globals (%d strict, %d loose)' % (len(cands), ns, len(cands) - ns))
    for v, tier, W, Rd in cands:
        print('%08x %-28s %s' % (v, names.get(v, ''), '' if tier == 'strict' else '(loose)'))
        for f in W:
            print('    W ' + fmt_fn(P, f, [s for s in acc[v][f] if s[1][0] in 'Ww&']))
        for f in Rd[:12]:
            print('    R ' + fmt_fn(P, f, [s for s in acc[v][f] if s[1][0] in 'Rr&']))
        if len(Rd) > 12:
            print('    R ... %d more simulation readers' % (len(Rd) - 12))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
