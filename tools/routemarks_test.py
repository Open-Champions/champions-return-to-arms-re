#!/usr/bin/env python3
"""routemarks_test.py - can what an earlier route search leaves behind change a later one?

The question (FINDINGS.md row V43, docs/issues/route-marks.md): a player's prediction copy
queues real route requests on its own machine only, so the shared route grid carries
different search marks on the two machines, and the request queue's indexes differ.  Does
a later search by the real simulation give the same result on both?

This test answers it by running the game's own code - the four request functions
0x184e38 / 0x184fc8 / 0x185148 / 0x1852c8, path_service 0x184798 and path_search 0x183e40
- in tools/ee_emu.py (an instruction interpreter, not a console) on a real level file
that the game's own world_fixup 0x181d30 has prepared, exactly as tools/difftest_world.py
sets it up (its Rig and PathRig are imported, not copied).

  python3 tools/routemarks_test.py [SLUS_209.73] [LEVEL.world ...] [options]

    LEVEL.world   level files of your own disc (unpack them with tools/gob.py).  With none
                  given, the ones under extracted/*/*.lmp/ are used
    --pairs N     later searches B per level (default 220; each is run alone and after
                  one or two different histories)
    --quick       a fifth of that
    --seed N      seed of the random inputs (default 20973); a seed repeats exactly
    --sweep       only the model sweep (below); needs level files but no executable
    --sweep-all   in the sweep, start from every linked node (default: every linked node
                  of grids up to 6,000 linked nodes, a seeded sample of 1,500 otherwise)
    -k TEXT       only the properties whose name contains TEXT (later search, worst
                  clearing wave, start at node 0, queue full, patch)
    -v            print up to three failing inputs per property

Without the executable (or with another build of it), or without any level file, the
script says so and exits 0.  Exit status 1 when a property fails.

Properties, one PASS/FAIL line each per level:

  later search = the same search alone
      B is requested and answered from a freshly fixed-up grid with the queue at index 0;
      then again after a history, and everything B produced must be equal: the result
      delivered to the requester, the whole path buffer, the count of rounds 0x44f094,
      the round index 0x7d89c0, the four ring counts 0x7d89b0, g_pathBusy, the start node
      remembered at 0x44f098, and the whole node grid afterwards.  Histories:
        complete      an earlier search A, answered
        suspended     A stopped on the timer after 0-40 rounds, B queued behind it
        queued        A and B both waiting when the service runs
        several       2-6 earlier searches, each answered or left waiting
        copy          the same request made 1-200 times (what a prediction copy does in
                      the walk-to-destination state), each answered: the write index is
                      off by that many, modulo 128
        index         nothing earlier, but the queue starts at another slot (1-127)
        non-blocking  everything answered by non-blocking calls on random timer readings
        deleted       A's requester is gone while A waits or while A is suspended
        torch         node block counters raised (0x18b6c0) before or after A
        two machines  a search both machines made, then 1-12 searches only one of them
                      made, then B on both: the case the live test saw
      A starts within 0-25 nodes of B's start, so its marks lie where B will search; a
      third of the A's are searches that fail (no node in reach passes the goal test),
      which leave the most marks a search can.
  the marks going in
      a count, not a comparison: how many of those histories really handed B a grid with
      marks in it, and how large the largest mark-clearing wave was (the clearing drops
      nodes only when a wave reaches 497; address 0x184b54)
  two machines
      a count: in how many of the two-machine cases the two grids really differed when B
      was asked, by how many nodes, and how far apart the write indexes were; it fails
      only if they differ outside the mark bits
  worst clearing wave
      the starts whose failing search gives the largest clearing waves according to the
      model (tools/ref_world.py), run through the original: the wave size the original
      reaches must equal the model's, and the grid after the next search must be clean
  start at node 0
      a search started at node index 0 is not cleared after (0x184a08): what that leaves;
      that searches out of reach of the corner are the same; that searches next to the
      corner with other goals keep their result and path; and the constructed case that
      does differ - a search whose only goal node is node 0 finds it alone and fails
      after the earlier one
  queue full
      with 126 requests waiting B is queued and answered as alone; with 127 waiting B
      is refused at once (result 0, no search)
  patch 0x184a08
      the proposed one-word change (the branch that skips the clearing becomes a no-op),
      applied in the interpreter's memory for this property only: ordinary cases must be
      unchanged by it, and a search started at node 0 must leave nothing behind

The sweep (--sweep, also run in a short form by the worst-wave property) uses the model
only: from every start it runs the search that marks the most nodes (no node passes the
goal test) and measures the clearing waves; for 60 of the starts it also measures them
for the same search cut short after every 4th round.  It also says whether there is a
floor under node 0 and whether it is flagged blocked.  The model's search and clearing
are compared bit for bit with the original by tools/difftest_world.py.

Time: a level takes 2 to 25 minutes in the interpreter with the default sample (the fixed
properties after the first take about a minute of it); --sweep a few seconds per level;
--sweep-all about six processor-hours for the 117 levels of the disc that have a grid.
"""
import glob
import hashlib
import itertools
import os
import random
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import ref_world as R                           # noqa: E402

ROOT = os.path.dirname(_HERE)
M32 = 0xFFFFFFFF
OPTIONS = {'pairs': 220, 'seed': 20973, 'verbose': False, 'sweep': False, 'sweep_all': False, 'filter': None}
RESULTS = []

A_CLEAR = 0x184A04              # path_service: a search is about to start (reads 0x44f098)
A_WAVE_CHECK = 0x184B54         # after each node of a clearing wave; $13 = size of the next wave so far
WAVE_LIMIT = 0x1F1              # 497: a wave this large makes the clearing drop the rest of the current one
A_SKIP = 0x184A08               # path_service: branch that skips the clearing when 0x44f098 is 0
SKIP_WORD = 0x10400060          # beqz v0, 0x184b8c
G_GOAL_TEST = 0x7D35E0
GOAL_GLOBALS = ((0x7D35E0, 4), (0x7D5BA8, 0x14), (0x7D89C4, 0x14))


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-44s %6d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def note(text):
    print('note  ' + text)
    sys.stdout.flush()


# ---------------------------------------------------------------------------------------
# The model sweep: how large can a clearing wave get?
# ---------------------------------------------------------------------------------------
class NoGoal(R.PathFinder):
    """The model's path finder with a goal test nothing passes: the search that marks the
    most nodes a search from that start can mark."""

    def _goal_reached(self, level, node):
        return False


def clearing_waves(cells, width, start):
    """The clearing of 0x184a04-0x184b88 on a copy of `cells`, measured: (largest wave,
    nodes dropped, marks left afterwards).  Same order and same limit as the original."""
    cells = list(cells)
    offsets = (-1 - width, -width, 1 - width, 1, width + 1, width, width - 1, -1)
    cells[start] &= 0xFFFF00FF
    current, largest, dropped = [start], 1, 0
    while current:
        produced = []
        for position, node in enumerate(current):
            links = cells[node]
            for k in range(8):
                if links >> k & 1:
                    neighbour = node + offsets[k]
                    if cells[neighbour] & 0xFF00:
                        cells[neighbour] &= 0xFFFF00FF
                        produced.append(neighbour)
            if not len(produced) < WAVE_LIMIT:
                dropped += len(current) - position - 1
                break
        largest = max(largest, len(produced))
        current = produced
    return largest, dropped, sum(1 for c in cells if c & 0xFF00)


def sweep_level(level, starts):
    """For each start: the failing search, then its clearing.  Returns a list of
    (largest wave, start, nodes marked, dropped, left)."""
    base = list(level.path_cells)
    rows = []
    far = (R.f32(1.0e7), R.f32(1.0e7), 0)
    for start in starts:
        level.path_cells = list(base)
        finder = NoGoal(level)
        x, y = level.path_node_position(start)
        finder.request(0, R.f32(24.0), (R.f32(float(x)), R.f32(float(y)), 0), far, lambda result: None, 16)
        finder.service(True)
        marked = sum(1 for c in level.path_cells if c & 0xFF00)
        largest, dropped, left = clearing_waves(level.path_cells, level.pg_w, start)
        rows.append((largest, start, marked, dropped, left))
    level.path_cells = base
    return rows


def sweep_partial(level, starts, every=4):
    """The same failing search stopped after every `every`-th round (what a search that
    found its goal there, or was suspended there, has marked): the largest clearing wave
    over all those states, the number of states, and how many would not be fully cleared."""
    base = list(level.path_cells)
    far = (R.f32(1.0e7), R.f32(1.0e7), 0)
    largest = states = incomplete = 0
    for start in starts:
        level.path_cells = list(base)
        finder = NoGoal(level)
        x, y = level.path_node_position(start)
        finder.request(0, R.f32(24.0), (R.f32(float(x)), R.f32(float(y)), 0), far, lambda result: None, 16)
        readings = itertools.chain([0, 0], itertools.repeat(9500))      # seed, then one round
        while True:
            finder.service(False, lambda: next(readings))
            if not finder.busy:
                break
            if finder.iterations % every == 0:
                wave, dropped, left = clearing_waves(level.path_cells, level.pg_w, start)
                largest = max(largest, wave)
                states += 1
                incomplete += 1 if dropped or left else 0
            readings = itertools.chain([0], itertools.repeat(9500))
    level.path_cells = base
    return largest, states, incomplete


def corner(level):
    """Node 0, the only start a search is not cleared after: (neighbours that link into
    it, has links of its own, floor height under it or None, blocked flag under it)."""
    cells, width = level.path_cells, level.pg_w
    into = sum(1 for node, bit in ((1, 0x80), (width, 0x02), (width + 1, 0x01)) if cells[node] & bit)
    x, y = level.path_node_position(0)
    pos = (R.f32(float(x)), R.f32(float(y)), R.f32(0.0))
    floor = R.to_float(R.terrain_height(level, R.f32(12.0), pos))
    blocked = R.to_float(R.terrain_test_flag1(level, R.f32(12.0), pos)) != 0.0
    return into, bool(cells[0] & 0xFF), None if floor < -99999.0 else floor, blocked


def corner_text(level):
    into, out, floor, blocked = corner(level)
    return ('node 0: %d neighbours link into it, %s; %s'
            % (into, 'IT HAS LINKS OF ITS OWN' if out else 'no links of its own',
               'no floor under it' if floor is None else
               'floor at height %.0f under it, %s' % (floor, 'flagged blocked' if blocked else 'NOT flagged blocked')))


def sweep_starts(level, rng, everything):
    linked = [i for i, cell in enumerate(level.path_cells) if cell & 0xFF]
    if everything or len(linked) <= 6000:
        return linked, len(linked)
    return rng.sample(linked, 1500), len(linked)


def run_sweep(name, data):
    try:
        level = R.Level(data)
    except Exception as error:                          # world_info refuses the file
        print('SKIP  %s: %s' % (name, error))
        return None
    if not level.pg_w or not any(c & 0xFF for c in level.path_cells):
        print('SKIP  %s: no path grid' % name)
        return None
    rng = random.Random('%d/sweep/%s' % (OPTIONS['seed'], name))
    starts, linked = sweep_starts(level, rng, OPTIONS['sweep_all'])
    rows = sweep_level(level, starts)
    worst = max(rows)
    incomplete = sum(1 for row in rows if row[3] or row[4])
    _into, out, floor, blocked = corner(level)
    report('%s: clearing waves (model)' % name, incomplete, len(rows),
           'of %d linked nodes; largest wave %d of %d allowed (start node %d, %d nodes marked); '
           'most nodes marked %d; %s'
           % (linked, worst[0], WAVE_LIMIT - 1, worst[1], worst[2], max(row[2] for row in rows),
              corner_text(level)))
    sample = starts if len(starts) <= 60 else rng.sample(starts, 60)
    largest, states, unfinished = sweep_partial(level, sample)
    report('%s: clearing waves, search cut short (model)' % name, unfinished, states,
           'states of the same search after every 4th round, from %d starts; largest wave %d of %d allowed'
           % (len(sample), largest, WAVE_LIMIT - 1))
    return max(worst[0], largest), len(rows), out, floor is not None, floor is not None and not blocked, states


# ---------------------------------------------------------------------------------------
# The original code on one level
# ---------------------------------------------------------------------------------------
class Case:
    """One route request."""
    __slots__ = ('kind', 'radius', 'start', 'goal', 'capacity', 'node')

    def __init__(self, kind, radius, start, goal, capacity, node):
        self.kind, self.radius, self.start, self.goal = kind, radius, list(start), list(goal)
        self.capacity, self.node = capacity, node

    def text(self):
        return ('type %d radius %.6g start (%.6g, %.6g, %.6g) goal (%.6g, %.6g) capacity %d'
                % ((self.kind, R.to_float(self.radius)) + tuple(R.to_float(v) for v in self.start)
                   + tuple(R.to_float(v) for v in self.goal[:2]) + (self.capacity,)))


class _Near:
    """What difftest_world.gen_path_case needs, with the start node fixed."""

    def __init__(self, ctx, node):
        self.level, self.nodes, self.node_point = ctx.level, [node], ctx.node_point


class Bench:
    """One level in the interpreter: the game's path finder, started fresh at will."""

    def __init__(self, D, elf, data):
        self.D = D
        self.level = R.Level(data)
        self.rig = D.Rig(elf, data)
        self.ctx = D.PathRig(self.rig, self.level)
        emu = self.rig.emu
        self.mem = emu.mem
        self.count = len(self.level.path_cells)
        self.width = self.level.pg_w
        self.fresh_cells = bytes(self.mem.read(self.rig.cells, 4 * self.count))
        self.fixup_kept_grid = list(struct.unpack('<%dI' % self.count, self.fresh_cells)) == self.level.path_cells
        self.linked = self.ctx.nodes
        self.is_linked = set(self.linked)
        self.wave_largest = 0           # over everything run so far
        self.wave_full = 0              # how often a wave reached the limit
        self.b_slot = -1
        self.going_in = None            # (marks in the grid, previous start, slot) when B's search starts
        emu.hook(A_WAVE_CHECK, self._on_wave)
        emu.hook(A_CLEAR, self._on_start)

    # ---- hooks --------------------------------------------------------------------------
    def _on_wave(self, emu):
        size = emu.r[13] & M32
        if size > self.wave_largest:
            self.wave_largest = size
        if size >= WAVE_LIMIT:
            self.wave_full += 1

    def _on_start(self, emu):
        slot = self.mem.u32(self.D.G_PATH_READ)
        if slot == self.b_slot and self.going_in is None:
            self.going_in = (self.marks(), self.mem.u32(self.D.G_PATH_PREV), slot)

    # ---- state --------------------------------------------------------------------------
    def cells(self):
        return struct.unpack('<%dI' % self.count, self.mem.read(self.rig.cells, 4 * self.count))

    def marks(self):
        return sum(1 for cell in self.cells() if cell & 0xFF00)

    def fresh(self, index=0):
        """The grid as world_fixup left it; the queue empty at slot `index`; no search in
        progress, none remembered (what 0x18b270 and world_resetRuntime 0x18b1b8 leave,
        and the scratch arrays zeroed as well)."""
        D, mem = self.D, self.mem
        mem.write(self.rig.cells, self.fresh_cells)
        mem.w32(D.G_PATH_READ, index)
        mem.w32(D.G_PATH_WRITE, index)
        for addr in (D.G_PATH_BUSY, D.G_PATH_PREV, D.G_PATH_ITER, D.G_PATH_ROUND):
            mem.w32(addr, 0)
        mem.write(D.G_PATH_COUNTS, bytes(16))
        mem.write(D.G_PATH_RINGS, bytes(4 * 512 * 4))
        mem.write(D.G_PATH_QUEUE, bytes(128 * 0x30))
        for addr, size in GOAL_GLOBALS:
            mem.write(addr, bytes(size))
        mem.w8(D.G_PATH_ENABLED, 1)
        del self.ctx.game_log[:]
        self.b_slot, self.going_in = -1, None

    def request(self, case, who):
        """The request function of case.kind; returns the slot it took."""
        D, rig = self.D, self.rig
        rig.put(rig.buf[0], case.start)
        rig.put(rig.buf[1], case.goal)
        rig.put(self.ctx.out[who], [0xDEADBEEF] * (2 * self.ctx.OUT_PAIRS))
        slot = self.mem.u32(D.G_PATH_WRITE)
        rig.call(D.A_PATH_REQUEST[case.kind], (rig.base, rig.buf[0], rig.buf[1], self.ctx.objects[who],
                                               self.ctx.out[who], case.capacity), (case.radius,))
        return slot

    def service(self, blocking, readings=()):
        """path_service; `readings` are the values hardware timer T0 shows, in order (it
        shows 20000 after they run out).  Only a non-blocking call reads the timer."""
        self.ctx.timer_values = itertools.chain(readings, itertools.repeat(20000))
        self.rig.call(self.D.A_PATH_SERVICE, (1 if blocking else 0,), max_steps=4000000000)

    def idle(self):
        D, mem = self.D, self.mem
        return not mem.u32(D.G_PATH_BUSY) and mem.u32(D.G_PATH_READ) == mem.u32(D.G_PATH_WRITE)

    def do(self, step):
        D, mem = self.D, self.mem
        op = step[0]
        if op == 'req':
            self.request(step[1], step[2])
        elif op == 'svc':
            self.service(step[1], step[2] if len(step) > 2 else ())
        elif op == 'kill':                              # the newest request's requester is deleted
            slot = (mem.u32(D.G_PATH_WRITE) - 1) & 0x7F
            mem.w32(D.G_PATH_QUEUE + slot * 0x30 + 0x28, 0)
        elif op == 'kill-current':                      # the requester of the search in progress
            mem.w32(D.G_PATH_QUEUE + mem.u32(D.G_PATH_READ) * 0x30 + 0x28, 0)
        elif op == 'block':
            self.rig.put(self.rig.buf[2], step[2])
            self.rig.call(D.A_PATH_BLOCK, (self.rig.base, self.rig.buf[2]), (step[1],))
        elif op == 'drain':                             # non-blocking calls until nothing is left
            for readings in step[1]:
                if self.idle():
                    break
                self.service(False, readings)
        else:
            raise ValueError(op)

    def run(self, history, b, index=0, final=(('svc', True),)):
        """history, then B (requester 0) and `final`; returns (what B produced, facts)."""
        D, mem = self.D, self.mem
        self.fresh(index)
        for step in history:
            self.do(step)
        grid_at_request = bytes(mem.read(self.rig.cells, 4 * self.count))
        marks_at_request = sum(1 for cell in struct.unpack('<%dI' % self.count, grid_at_request) if cell & 0xFF00)
        write_at_request = mem.u32(D.G_PATH_WRITE)
        waiting = (write_at_request - mem.u32(D.G_PATH_READ)) & 0x7F
        busy_at_request = mem.u32(D.G_PATH_BUSY)
        self.b_slot, self.going_in = write_at_request, None
        self.request(b, 0)
        entry = self.rig.get(D.G_PATH_QUEUE + write_at_request * 0x30, 12)
        for step in final:
            self.do(step)
        if not self.idle():
            self.service(True)
        delivered = tuple(result for who, result in self.ctx.game_log if who == 0)
        out = tuple(self.rig.get(self.ctx.out[0], 2 * self.ctx.OUT_PAIRS))
        work = (mem.u32(D.G_PATH_ITER), mem.u32(D.G_PATH_ROUND)) + tuple(self.rig.get(D.G_PATH_COUNTS, 4)) \
            + (mem.u32(D.G_PATH_BUSY), mem.u32(D.G_PATH_PREV))
        grid = bytes(mem.read(self.rig.cells, 4 * self.count))
        produced = (delivered, out, work, grid, tuple(entry))
        facts = {'marks_at_request': marks_at_request, 'grid_at_request': grid_at_request,
                 'write': write_at_request, 'waiting': waiting,
                 'busy': busy_at_request, 'going_in': self.going_in,
                 'rings': bytes(mem.read(D.G_PATH_RINGS, 4 * 512 * 4)),
                 'goal_test': mem.u32(G_GOAL_TEST)}
        return produced, facts

    # ---- inputs -------------------------------------------------------------------------
    def near(self, rng, node, spread):
        """A linked node within `spread` columns and rows of `node`."""
        col, row = node % self.width, node // self.width
        for _ in range(60):
            other = (row + rng.randint(-spread, spread)) * self.width + col + rng.randint(-spread, spread)
            if other in self.is_linked:
                return other
        return node

    def case(self, rng, node, kind=None, failing=False, capacity=16):
        if kind is None:
            kind = rng.choice((0, 0, 0, 0, 0, 0, 1, 2, 3))
        start, goal, radius = self.D.gen_path_case(_Near(self.ctx, node), rng, kind)
        if failing and kind in (0, 1):                  # no node can pass: the search runs to its limits
            goal = [R.f32(R.to_float(start[0]) + 3.0e5), R.f32(R.to_float(start[1]) - 2.0e5), R.f32(0.0)]
            radius = R.f32(24.0)
        return Case(kind, radius, start, goal, capacity, node)

    def earlier(self, rng, b):
        """An earlier request whose search runs where B's will."""
        node = self.near(rng, b.node, rng.choice((0, 2, 5, 10, 25)))
        return self.case(rng, node, failing=rng.random() < 0.35)


def path_text(out):
    pairs = []
    for i in range(0, len(out), 2):
        x, y = R.s32(out[i]), R.s32(out[i + 1])
        if out[i] == 0xDEADBEEF:
            break
        pairs.append('(%d,%d)' % (x, y))
        if (x, y) == (-1, -1):
            break
    return ' '.join(pairs)


def differences(reference, produced):
    names = ('result delivered', 'path buffer', 'rounds/round/ring counts/busy/start node', 'node grid',
             'queue entry')
    return [names[i] for i in range(5) if reference[i] != produced[i]]


# ---------------------------------------------------------------------------------------
# Histories
# ---------------------------------------------------------------------------------------
def timer_schedule(rng, calls=40):
    """Timer readings for a run of non-blocking calls: each call starts a new frame."""
    schedule = []
    for _ in range(calls):
        base, step = rng.randrange(0, 7000), rng.choice((40, 150, 400, 900, 2500))
        schedule.append([base + step * i for i in range(400)])
    return schedule


def scenario(bench, rng, name, b):
    """-> (reference history, [(label, history, index, final)])."""
    A = lambda: bench.earlier(rng, b)                   # noqa: E731
    blocking = (('svc', True),)
    if name == 'complete':
        return [], [('A answered', [('req', A(), 1), ('svc', True)], 0, blocking)]
    if name == 'suspended':
        rounds = rng.choice((0, 1, 1, 2, 3, 5, 8, 13, 20, 40))
        # the service reads the timer on entry and again once the search is seeded; the
        # search reads it after every round that found nothing
        stop = [0, 9500] if rounds == 0 else [0, 0] + [0] * (rounds - 1) + [9500]
        history = [('req', A(), 1), ('svc', False, stop)]
        twice = history + [('svc', False, [0, 8000])]   # and one more round in a second call
        return [], [('A stopped by the timer after %d rounds' % rounds, history, 0, blocking),
                    ('A stopped twice', twice, 0, blocking)]
    if name == 'queued':
        return [], [('A waiting', [('req', A(), 1)], 0, blocking),
                    ('two waiting', [('req', A(), 1), ('req', A(), 2)], 0, blocking)]
    if name == 'several':
        history = []
        for _ in range(rng.randint(2, 6)):
            history.append(('req', A(), rng.randint(1, 3)))
            if rng.random() < 0.6:
                history.append(('svc', True))
        return [], [('several', history, 0, blocking)]
    if name == 'copy':
        times = rng.choice((1, 2, 5, 17, 49, 49, 64, 127, 128, 129, 200))
        # the copy stands still at a destination it cannot or can reach and asks again
        a = bench.case(rng, bench.near(rng, b.node, rng.choice((0, 3, 12))), kind=0,
                       failing=times <= 17 and rng.random() < 0.5)
        history = [('req', a, 2), ('svc', True)] * times
        return [], [('the same request %d times' % times, history, 0, blocking)]
    if name == 'index':
        index = rng.choice((1, 31, 32, 80, 126, 127, rng.randrange(1, 128)))
        return [], [('queue at slot %d' % index, [], index, blocking),
                    ('queue at slot %d, A answered' % index, [('req', A(), 1), ('svc', True)], index, blocking)]
    if name == 'non-blocking':
        history = [('req', A(), 1)]
        if rng.random() < 0.5:
            history.append(('req', A(), 2))
        history.append(('svc', False, timer_schedule(rng, 1)[0]))
        final = (('drain', timer_schedule(rng)),)
        return [], [('non-blocking, A first', history, 0, final), ('non-blocking, alone', [], 0, final)]
    if name == 'deleted':
        waiting = [('req', A(), 1), ('kill',)]
        rounds = rng.choice((1, 2, 5, 12))
        running = [('req', A(), 1), ('svc', False, [0, 0] + [0] * (rounds - 1) + [9500]), ('kill-current',)]
        return [], [("A's requester deleted while waiting", waiting, 0, blocking),
                    ("A's requester deleted while suspended", running, 0, blocking)]
    if name == 'torch':
        blocks = []
        width, height = bench.level.pg_w, bench.level.pg_h
        for _ in range(rng.randint(1, 3)):
            # 0x18b6c0 has no bounds check: a rectangle that leaves the grid reads and writes
            # outside it (the interpreter stops), so the blocks are kept six nodes inside
            node = bench.near(rng, b.node, 8)
            col, row = min(max(node % width, 6), width - 7), min(max(node // width, 6), height - 7)
            x, y = bench.level.path_node_position(row * width + col)
            blocks.append(('block', R.f32(rng.choice((12.0, 24.0, 40.0))),
                           [R.f32(x + rng.uniform(-12, 12)), R.f32(y + rng.uniform(-12, 12)), R.f32(0.0)]))
        a = [('req', A(), 1), ('svc', True)]
        return blocks, [('A, then the blocks', a + blocks, 0, blocking), ('the blocks, then A', blocks + a, 0, blocking)]
    if name == 'two machines':
        shared = [('req', A(), 1), ('svc', True)]       # a monster's search, on both machines
        times = rng.choice((1, 1, 2, 3, 6, 12))
        copy = bench.case(rng, bench.near(rng, b.node, rng.choice((0, 3, 12))), kind=0, failing=rng.random() < 0.5)
        mine = shared + [('req', copy, 2), ('svc', True)] * times
        return [], [('machine without the copy', shared, 0, blocking),
                    ('machine whose copy asked %d times' % times, mine, 0, blocking)]
    raise ValueError(name)


SCENARIOS = ('complete', 'suspended', 'queued', 'several', 'copy', 'index', 'non-blocking', 'deleted', 'torch',
             'two machines')


def prop_later_search(bench, name, rng, count):
    fails, examples, runs = 0, [], 0
    by_name = {}
    with_marks = with_other_index = most_marks = 0
    busy_runs = ring_diffs = 0
    found = failed = 0
    pairs = pairs_differing = most_nodes = other_bits = 0
    marked = [0, 0]
    index_gaps = set()
    for index in range(count):
        which = SCENARIOS[index % len(SCENARIOS)]
        b = bench.case(rng, rng.choice(bench.linked), capacity=rng.choice((16, 16, 16, 16, 16, 2, 5, 40)),
                       failing=rng.random() < 0.08)
        reference_history, sides = scenario(bench, rng, which, b)
        try:
            reference, ref_facts = bench.run(reference_history, b)
            results = [bench.run(history, b, slot, final) for _label, history, slot, final in sides]
        except (bench.D.EmuError, RuntimeError) as error:   # the interpreter stopped: count it, go on
            fails += 1
            runs += 1
            examples.append('%s: B = %s: stopped: %s' % (which, b.text(), error))
            continue
        if reference[0] == (1,):
            found += 1
        else:
            failed += 1
        side_facts = []
        for (label, history, slot, final), (produced, facts) in zip(sides, results):
            side_facts.append(facts)
            runs += 1
            by_name[which] = by_name.get(which, 0) + 1
            going_in = facts['going_in']
            marks = going_in[0] if going_in else 0
            if marks:
                with_marks += 1
                most_marks = max(most_marks, marks)
            if facts['write'] != ref_facts['write']:
                with_other_index += 1
            if facts['busy']:
                busy_runs += 1
            if facts['rings'] != ref_facts['rings']:
                ring_diffs += 1
            # the queue entry holds the same request wherever it lies
            differing = differences(reference, produced)
            if differing:
                fails += 1
                examples.append('%s / %s: B = %s; differs in %s; alone: result %s path %s; after: result %s path %s'
                                % (which, label, b.text(), ', '.join(differing), reference[0],
                                   path_text(reference[1]), produced[0], path_text(produced[1])))
        if which == 'two machines':                     # how the two machines differed when B was asked
            one, two = side_facts
            pairs += 1
            cells_one = struct.unpack('<%dI' % bench.count, one['grid_at_request'])
            cells_two = struct.unpack('<%dI' % bench.count, two['grid_at_request'])
            nodes = sum(1 for x, y in zip(cells_one, cells_two) if x != y)
            if any((x ^ y) & 0xFFFF00FF for x, y in zip(cells_one, cells_two)):
                other_bits += 1
            if nodes:
                pairs_differing += 1
                if nodes > most_nodes:
                    most_nodes = nodes
                    marked = [one['marks_at_request'], two['marks_at_request']]
            index_gaps.add((two['write'] - one['write']) & 0x7F)
    report('%s: later search = the same search alone' % name, fails, runs,
           'B alone against B after a history (original code): result, path buffer, work counters, grid; '
           '%d different B (%d found a path, %d did not)' % (count, found, failed), examples)
    report('%s: the marks going in' % name, 0, with_marks,
           'histories of %d that handed B a grid with marks (up to %d marked nodes); %d with another '
           'write index; %d with a search in progress when B was asked; scratch rings differed after '
           '%d; largest clearing wave %d of %d allowed, limit reached %d times'
           % (runs, most_marks, with_other_index, busy_runs, ring_diffs, bench.wave_largest, WAVE_LIMIT - 1,
              bench.wave_full))
    report('%s: two machines' % name, other_bits, pairs_differing,
           'of %d two-machine cases in which the grids differed when B was asked (up to %d nodes: %d marked '
           'on one side, %d on the other; outside the mark bits in %d cases); write index apart by %s; '
           'what B produced is compared in the first line'
           % (pairs, most_nodes, marked[0], marked[1], other_bits, sorted(index_gaps)))
    return by_name


def prop_worst_wave(bench, name, rng):
    """The model's worst clearing waves on this level, through the original."""
    level = bench.level
    linked = bench.linked
    starts = linked if len(linked) <= 2500 else rng.sample(linked, 400)
    rows = sorted(sweep_level(level, starts), reverse=True)[:3]
    fails, examples = 0, []
    for largest, start, marked, _dropped, _left in rows:
        a = bench.case(rng, start, kind=0, failing=True)
        x, y = level.path_node_position(start)
        a.start = [R.f32(float(x)), R.f32(float(y)), 0]
        b = bench.case(rng, bench.near(rng, start, 6), kind=0)
        reference, _facts = bench.run([], b)
        before = bench.wave_largest
        bench.wave_largest = 0
        bench.fresh()
        bench.request(a, 1)
        bench.service(True)
        marks_after_a = bench.marks()
        bench.b_slot, bench.going_in = bench.mem.u32(bench.D.G_PATH_WRITE), None
        bench.request(b, 0)
        bench.service(True)
        measured = bench.wave_largest
        bench.wave_largest = max(before, measured)
        grid = bytes(bench.mem.read(bench.rig.cells, 4 * bench.count))
        problem = ''
        if marks_after_a != marked:
            problem = 'the failing search marked %d nodes, the model %d' % (marks_after_a, marked)
        elif measured != largest:
            problem = 'largest wave %d, the model %d' % (measured, largest)
        elif grid != reference[3]:
            problem = 'the grid after B is not the grid after B alone'
        if problem:
            fails += 1
            examples.append('start node %d: %s' % (start, problem))
    report('%s: worst clearing wave' % name, fails, len(rows),
           'model-chosen worst of %d starts, run through the original: nodes marked %s, largest wave %s '
           '(limit %d), grid clean after the next search'
           % (len(starts), [row[2] for row in rows], [row[0] for row in rows], WAVE_LIMIT), examples)


def prop_node_zero(bench, name, rng):
    """A search started at node index 0: path_service skips the clearing while 0x44f098 is
    0, so the start mark of that search stays on node 0 until a later clearing reaches it
    through a neighbour's link.  Shown: a later search out of reach of the corner is the
    same; one whose wave reaches the corner has the same result and path unless node 0
    itself passes its goal test, though its counters may differ (node 0 is no longer
    entered); one whose only goal node is node 0 fails."""
    level = bench.level
    x, y = level.path_node_position(0)
    width = level.pg_w
    cells = level.path_cells
    corner_pos = [R.f32(float(x)), R.f32(float(y)), R.f32(0.0)]
    a = Case(0, R.f32(24.0), corner_pos, [R.f32(x + 240.0), R.f32(y + 240.0), R.f32(0.0)], 16, 0)
    earlier = [('req', a, 1), ('svc', True)]
    fails, examples, runs = 0, [], 0
    left = set()
    # a search spreads at most 40 nodes from its start: these cannot reach node 0
    far = [node for node in bench.linked if max(node % width, node // width) >= 45]
    for _ in range(6 if far else 0):
        b = bench.case(rng, rng.choice(far), kind=0)
        reference, _f = bench.run([], b)
        produced, _f = bench.run(earlier, b)
        runs += 1
        differing = differences(reference, produced)
        ref_cells = struct.unpack('<%dI' % bench.count, reference[3])
        got_cells = struct.unpack('<%dI' % bench.count, produced[3])
        nodes = [i for i in range(bench.count) if ref_cells[i] != got_cells[i]]
        left.update((i, got_cells[i] >> 8 & 0xFF) for i in nodes)
        if differing != ['node grid'] or nodes != [0]:
            fails += 1
            examples.append('B = %s: differs in %s, nodes %s' % (b.text(), differing, nodes[:8]))
    shown = 'node 0 cannot be entered in this level, nothing more to show'
    if cells[width + 1] & 0x01 and cells[2 * width + 2] & 0x01 and not cells[0] & 0xFF:
        # searches next to the corner whose goal is not node 0: same result and path
        near_runs = counters = 0
        for _ in range(12):
            b = bench.case(rng, bench.near(rng, 2 * width + 2, 3), kind=0)
            reach = R.to_float(b.radius)
            away = ((R.to_float(b.goal[0]) - x) ** 2 + (R.to_float(b.goal[1]) - y) ** 2) ** 0.5
            if away < max(reach, 24.0) + 1.0:           # node 0 could pass the goal test: not this part
                continue
            reference, _f = bench.run([], b)
            produced, _f = bench.run(earlier, b)
            runs += 1
            near_runs += 1
            differing = differences(reference, produced)
            if 'rounds/round/ring counts/busy/start node' in differing:
                counters += 1
            if 'result delivered' in differing or 'path buffer' in differing:
                fails += 1
                examples.append('B by the corner = %s: differs in %s' % (b.text(), differing))
        # B stands two nodes in from the corner and wants the corner itself, radius 24: of
        # all nodes only node 0 is nearer than 24 to it
        bx, by = level.path_node_position(2 * width + 2)
        b = Case(0, R.f32(24.0), [R.f32(float(bx)), R.f32(float(by)), R.f32(0.0)], corner_pos, 16, 2 * width + 2)
        reference, _f = bench.run([], b)
        produced, _f = bench.run(earlier, b)
        runs += 1
        shown = ('%d searches next to the corner with other goals: result and path equal, counters '
                 'different in %d; B from node %d to the corner itself: alone result %s path %s, after it '
                 'result %s path %s'
                 % (near_runs, counters, 2 * width + 2, reference[0], path_text(reference[1]), produced[0],
                    path_text(produced[1])))
        if not (reference[0] == (1,) and produced[0] == (0,)):
            fails += 1
            examples.append('the corner case did not differ as predicted: ' + shown)
        # the same B with its goal 10 units along the edge from the corner: node 0 still
        # passes the goal test, and so does its neighbour; reported, not judged
        b2 = Case(0, R.f32(24.0), b.start, [R.f32(x + 10.0), R.f32(y + 2.0), R.f32(0.0)], 16, b.node)
        reference2, _f = bench.run([], b2)
        produced2, _f = bench.run(earlier, b2)
        runs += 1
        shown += ('; the same B to a goal 10 units along the edge: alone result %s path %s, after it result %s '
                  'path %s' % (reference2[0], path_text(reference2[1]), produced2[0], path_text(produced2[1])))
        # one more search from B's node in between: its marks reach the neighbour that links
        # into node 0, and the clearing of those marks (when B is seeded) wipes node 0 too
        c = bench.case(rng, 2 * width + 2, kind=0, failing=True)
        healed, _f = bench.run(earlier + [('req', c, 2), ('svc', True)], b)
        runs += 1
        if differences(reference, healed):
            fails += 1
            examples.append('with one more search by the corner in between B still differs in %s'
                            % differences(reference, healed))
        else:
            shown += '; with one more search next to the corner in between, B is as alone again'
    report('%s: start at node 0' % name, fails, runs,
           'after a search started at node 0: %d later searches out of reach of the corner are the same '
           'and the grid keeps %s; %s; %s'
           % (6 if far else 0, ', '.join('mark %d on node %d' % (m, i) for i, m in sorted(left)) or 'nothing',
              shown, corner_text(level)), examples)


def prop_queue_full(bench, name, rng):
    """127 requests waiting: the next one is refused without a search."""
    fails, examples, runs = 0, [], 0
    refused = 0
    for _ in range(2):
        b = bench.case(rng, rng.choice(bench.linked), kind=0)
        for _attempt in range(20):                      # a B that finds a path, so a refusal shows
            reference, _f = bench.run([], b)
            if reference[0] == (1,):
                break
            b = bench.case(rng, rng.choice(bench.linked), kind=0)
        waiting = [('req', bench.case(rng, bench.near(rng, b.node, 3), kind=0), 1 + i % 3) for i in range(127)]
        produced, _f = bench.run(waiting[:126], b)
        runs += 1
        if differences(reference, produced):
            fails += 1
            examples.append('126 waiting: B differs in %s' % differences(reference, produced))
        # 127 waiting: the request function answers 0 itself and queues nothing
        bench.fresh()
        for step in waiting:
            bench.do(step)
        write = bench.mem.u32(bench.D.G_PATH_WRITE)
        bench.request(b, 0)
        answered = [result for who, result in bench.ctx.game_log if who == 0]
        runs += 1
        if answered == [0] and bench.mem.u32(bench.D.G_PATH_WRITE) == write:
            refused += 1
        else:
            fails += 1
            examples.append('127 waiting: B was not refused (answers %s)' % answered)
        bench.service(True)
    report('%s: queue full' % name, fails, runs,
           'with 126 waiting B is answered as alone; with 127 waiting B is refused at once with result 0 '
           '(%d of %d), although alone it finds a path' % (refused, runs // 2), examples)


def prop_patch(bench, name, rng, count):
    """The one-word change proposed in docs/issues/route-marks.md: the branch at 0x184a08
    becomes a no-op, so the clearing also runs when the previous start node was node 0.
    Shown: ordinary cases are unchanged by it, and a search started at node 0 no longer
    leaves anything behind."""
    emu, level, width = bench.rig.emu, bench.level, bench.level.pg_w
    word = bench.mem.u32(A_SKIP)
    if word != SKIP_WORD:
        report('%s: patch 0x184a08' % name, 1, 0, 'the word there is %08x, not %08x' % (word, SKIP_WORD))
        return
    fails, examples, runs = 0, [], 0
    ordinary = []
    for index in range(count):
        which = SCENARIOS[index % len(SCENARIOS)]
        b = bench.case(rng, rng.choice(bench.linked))
        reference_history, sides = scenario(bench, rng, which, b)
        ordinary.append((which, b, reference_history, sides, bench.run(reference_history, b)[0]))
    x, y = level.path_node_position(0)
    corner_pos = [R.f32(float(x)), R.f32(float(y)), R.f32(0.0)]
    a = Case(0, R.f32(24.0), corner_pos, [R.f32(x + 240.0), R.f32(y + 240.0), R.f32(0.0)], 16, 0)
    earlier = [('req', a, 1), ('svc', True)]
    after_zero = [bench.case(rng, rng.choice(bench.linked), kind=0) for _ in range(4)]
    after_zero += [bench.case(rng, bench.near(rng, 2 * width + 2, 3), kind=0) for _ in range(4)]
    cells = level.path_cells
    if cells[width + 1] & 0x01 and cells[2 * width + 2] & 0x01:
        bx, by = level.path_node_position(2 * width + 2)
        after_zero.append(Case(0, R.f32(24.0), [R.f32(float(bx)), R.f32(float(by)), R.f32(0.0)], corner_pos, 16,
                               2 * width + 2))
    zero_refs = [bench.run([], b)[0] for b in after_zero]
    emu.patch(A_SKIP, 0)
    try:
        for which, b, reference_history, sides, reference in ordinary:
            for label, history, slot, final in [('alone', reference_history, 0, (('svc', True),))] + sides:
                produced, _f = bench.run(history, b, slot, final)
                runs += 1
                if differences(reference, produced):
                    fails += 1
                    examples.append('%s / %s: B = %s: with the patch differs from B alone without it in %s'
                                    % (which, label, b.text(), differences(reference, produced)))
        for b, reference in zip(after_zero, zero_refs):
            produced, _f = bench.run(earlier, b)
            runs += 1
            if differences(reference, produced):
                fails += 1
                examples.append('after a search started at node 0, B = %s still differs in %s'
                                % (b.text(), differences(reference, produced)))
    finally:
        emu.patch(A_SKIP, word)
    report('%s: patch 0x184a08' % name, fails, runs,
           '%08x -> 00000000 in the interpreter: %d ordinary cases (B alone and after each history) equal to B '
           'alone unpatched; after a search started at node 0, %d later searches (%d next to the corner%s) '
           'equal to themselves alone, grid included'
           % (word, len(ordinary), len(after_zero), 4,
              ', and the search to the corner itself' if len(after_zero) == 9 else ''), examples)


def run_level(D, elf, name, data):
    try:
        level = R.Level(data)
    except Exception as error:                          # world_info refuses the file
        print('SKIP  %s: %s' % (name, error))
        return
    if not level.pg_w or not any(c & 0xFF for c in level.path_cells):
        print('SKIP  %s: no path grid' % name)
        return
    bench = Bench(D, elf, data)
    if not bench.fixup_kept_grid:
        note('%s: world_fixup changed the path grid of the file' % name)
    seed = lambda text: random.Random('%d/%s/%s' % (OPTIONS['seed'], name, text))     # noqa: E731
    wanted = lambda text: OPTIONS['filter'] is None or OPTIONS['filter'].lower() in text    # noqa: E731
    try:
        if wanted('later search'):
            by_name = prop_later_search(bench, name, seed('later'), OPTIONS['pairs'])
            note('%s: histories run: %s' % (name, ', '.join('%s %d' % item for item in sorted(by_name.items()))))
        if wanted('worst clearing wave'):
            prop_worst_wave(bench, name, seed('wave'))
        if wanted('start at node 0'):
            prop_node_zero(bench, name, seed('zero'))
        if wanted('queue full'):
            prop_queue_full(bench, name, seed('full'))
        if wanted('patch'):
            prop_patch(bench, name, seed('patch'), max(OPTIONS['pairs'] // 8, 10))
    except (D.EmuError, RuntimeError, IndexError) as error:
        report('%s: stopped' % name, 1, 0, str(error))


def main(argv):
    elf = None
    worlds = []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == '--quick':
            OPTIONS['pairs'] = max(OPTIONS['pairs'] // 5, 20)
        elif arg == '--pairs':
            OPTIONS['pairs'] = max(int(args.pop(0)), 1)
        elif arg == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif arg == '--sweep':
            OPTIONS['sweep'] = True
        elif arg == '--sweep-all':
            OPTIONS['sweep'] = OPTIONS['sweep_all'] = True
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif arg.lower().endswith('.world'):
            worlds.append(arg)
        else:
            elf = arg
    if not worlds:
        worlds = sorted(glob.glob(os.path.join(ROOT, 'extracted', '*', '*.lmp', '*.world')))
    levels = []
    for path in worlds:
        if not os.path.isfile(path):
            print('SKIP  %s: no such file' % path)
            continue
        with open(path, 'rb') as source:
            levels.append((os.path.basename(path)[:-len('.world')], source.read()))
    started = time.time()
    if OPTIONS['sweep']:
        if not levels:
            print('SKIP  no level files (pass .world files unpacked from your own disc)')
            return 0
        done = [row for row in (run_sweep(name, data) for name, data in levels) if row]
        if done:
            print('sweep: %d levels, %d starts and %d cut-short states, largest clearing wave %d (limit %d); '
                  'node 0 has links of its own in %d levels, a floor under it in %d, a floor not flagged '
                  'blocked in %d'
                  % (len(done), sum(row[1] for row in done), sum(row[5] for row in done),
                     max(row[0] for row in done), WAVE_LIMIT, sum(1 for row in done if row[2]),
                     sum(1 for row in done if row[3]), sum(1 for row in done if row[4])))
    else:
        if elf is None:
            elf = os.path.join(ROOT, 'SLUS_209.73')
        if not os.path.isfile(elf):
            print('SKIP  no executable at %s (give the path to your own SLUS_209.73)' % elf)
            return 0
        import difftest_world as D                      # the level set-up and the path rig
        with open(elf, 'rb') as source:
            digest = hashlib.sha256(source.read()).hexdigest()
        if digest != D.EXPECTED_SHA256:
            print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
            return 0
        if not levels:
            print('SKIP  no level files (pass .world files unpacked from your own disc)')
            return 0
        for name, data in levels:
            run_level(D, elf, name, data)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
