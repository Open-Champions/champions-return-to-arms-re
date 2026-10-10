#!/usr/bin/env python3
"""ref_objects.py - reference model of the object system of Champions: Return to Arms
(SLUS_209.73): what exists, in which order it runs, and how objects find each other.

A research tool, not game code.  Every method was written from the instruction sequence at
the address in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_objects.py.  docs/spec/object-system.md is the prose
version and says what the comparison covers.  Standard library only; no game data is
embedded.  The pool, the handle lists, the list iterator and the random generator are NOT
modelled again here: they come from tools/ref_core.py (Pool, HandlePool, Iterator,
SharedRandom), and the arithmetic of the console's FPU comes from there as well.

Why order is everything
    Online play is lockstep.  The order in which objects are created, run and returned by
    queries is the order in which the shared seed is drawn, so a rebuild must reproduce the
    list discipline exactly: every list is a handle list, new links go to the FRONT, and
    walks go front to back.

Floats are raw 32-bit patterns (ints), as in ref_core: f32() makes one from a Python float.
A position is a list of three patterns [x, y, height].

Use
    w = World()
    o = w.new_object(0x4c, [f32(100.0), f32(-20.0), 0])      # pool_new + GameObject_ctor
    w.run_every_frame(o)                                     # obj_runEveryFrame
    o.pos[0] = f32(700.0); w.update_grid_cell(o)             # every move must do this
    hits = w.collect_in_box(lo, hi, 256)                     # world_collectObjectsInBox
    w.on_run = lambda obj: ...                               # each object's virtual slot 4
    w.run_objects()                                          # runObjects, one tick
    w.delete(o)                                              # obj_delete: gone next tick

Sections: 1 constants, 2 the object, 3 the name table, 4 the task list, 5 the world
(creation, deletion, grids, run lists, activity, queries, runObjects, walkers, teardown),
6 activity centres and the "near view" test, 7 free-spot search and the start marker,
8 level object records.
"""
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # appended: tools/dis.py must not shadow the standard dis
import ref_core as R                                # noqa: E402
from ref_core import M32, f32, s16, s32              # noqa: E402,F401

# =======================================================================================
# 1. Constants (addresses are those of the executable; the model itself needs none of
#    them, but the lists are named by address so that a test can compare memory directly)
# =======================================================================================

GRID_DIM = 120                  # cells per axis
GRID_BIAS = 0x3C00              # added to (int)coordinate before the shift: cell 60 starts at 0
CELL_SHIFT = 8                  # 256 units per cell
QUERY_BIAS_LOW = 0x3BA0         # GRID_BIAS - 96: the box query's pad on the low side
QUERY_BIAS_HIGH = 0x3C60        # GRID_BIAS + 96: and on the high side

G_RUN_ACTIVE = 0x5DB3A8         # g_runListActive
G_RUN_15 = 0x5DB3B0             # g_runLists15[15]
G_RUN_60 = 0x5DB3F0             # g_runLists60[60]
G_DELETE_LIST = 0x5DB4E0
G_ALWAYS_DRAW = 0x5DB4E8
G_GRID = 0x5DB4F0               # grid A: [row = y][column = x]
G_GRID_B = 0x5E95F0             # grid B: objects with flag 0x800
G_OFF_GRID = 0x5F76F0
G_OBJECT_FACTORY = 0x5F76F4
G_NAME_KEYS = 0x5F76F8
G_NAME_OBJS = 0x5F7EF8
G_NAME_COUNT = 0x5F86F8
G_LOAD_STR_BASE = 0x5F8704
G_EXCLUDE_MASK = 0x4039B8
G_TEARING_DOWN = 0x4039BC
G_CULL_BY_CAMERA = 0x4039C1     # s8; 1 in the executable
G_ACTIVITY_CENTERS = 0x4039C8   # Vec3[4]
G_CURSOR_60 = 0x4039FC
G_CURSOR_15 = 0x403A00
G_POOL_FREE_COUNT = 0x403A04    # 100000 in the executable
G_ACTIVITY_COUNT = 0x403A08     # s8
G_SAVE_FILTER = 0x403A0C
G_NETWORK_MODE = 0x402791       # s8
G_RAND_SEED = 0x404464
G_LUMP_GENERATION = 0x41BF78
G_CAMERA_FOCUS = 0x44F048       # Vec3
G_SIM_FRAME = 0x44FDCC
G_TASK_COUNT = 0x44FDB8
G_TASK_CURSOR = 0x44FDBC
G_TASKS = 0x840100              # 16-byte records: fn, priority, name, flags
G_PLAYER_START_RANK = 0x4F7108  # s8
G_SPAWN_POS = 0x4F70D0          # Vec3[4]
G_SPAWN_FACING = 0x4F8410       # s16[4]

VT_GAMEOBJECT = 0x5122A8
VT_PLAYER1 = 0x512028
OBJECT_SIZE = 0x4C

FLAG_NOT_SOLID = 0x1
FLAG_NOT_GRID_DRAWN = 0x2
FLAG_DEAD = 0x8
FLAG_GRID_B = 0x800
FLAG_EXPENDABLE = 0x1000
FLAG_NOT_RUN = 0x8000
FLAG_PREDICTION_COPY = 0x20000
FLAG_FAR_ACTIVE = 0x80000       # activity radius forced to 44000
FLAG_OWN_PLAYER = 0x200000

F_24 = 0x41C00000               # default radius
F_72 = 0x42900000               # default height extent
F_480_SQ = 0x48610000           # 230400.0: the reaper's camera distance, squared
F_6 = 0x40C00000
F_100000 = 0x47C35000
FAR_ACTIVE_RADIUS = 0xABE0      # 44000

POOL_SAMPLE_MASK = 0x3F         # the free count is refreshed when frame & 0x3f == 0
REAP_BELOW = 300
REAP_NEAR_CAMERA_BELOW = 200
REAP_CELLS_PER_FRAME = 16
MAX_TASKS = 32                  # room before the next global; task_add itself has no check


class ObjectError(Exception):
    """The original has no defined behaviour here (it would follow a null or stale
    pointer); the model refuses instead of guessing."""


def cell_coord(raw):
    """((int)coordinate + 0x3c00) >> 8 with the conversion of cvt.w.s (toward zero,
    saturating) and 32-bit wrap-around of the addition.  Not clamped: the caller decides
    what "outside" means.  Because the conversion truncates toward zero, the cell that
    starts at 0 also takes the coordinates in (-1, 0): cell 60 is 257 units wide and cell
    59 is 255 (for x and for y alike)."""
    return s32(R.to_int(raw) + GRID_BIAS) >> CELL_SHIFT


def _unlink(node):
    """Take a node out of its list (prev is never null for a linked node)."""
    node.prev.next = node.next
    if node.next is not None:
        node.next.prev = node.prev


def _push(head, node):
    """Put a node directly behind a list head."""
    node.next = head.next
    node.prev = head
    head.next = node
    if node.next is not None:
        node.next.prev = node


# =======================================================================================
# 2. The object: the 0x4c bytes every class starts with
# =======================================================================================

class ClassDef:
    """The class definition a constructor passes (object +0x24): a lump, the level
    generation its names were last resolved for, and (name, resolved pointer) pairs."""

    def __init__(self, lump, names, generation=0):
        self.lump = lump
        self.generation = generation
        self.entries = [[name, 0] for name in names]


class GameObject:
    """GameObject, 0x4c bytes.  heads[0] (+0) "who refers to me" - also the back link for
    the delete list and the always-draw list; heads[1] (+4) the run-list link; heads[2]
    (+8) the grid link.  Fields the base constructor does not write keep the zero that
    pool_new left (vz +0x30, angle +0x38, +0x3c, +0x40)."""

    def __init__(self, addr):
        self.addr = addr
        self.heads = [R.Cell(addr), R.Cell(addr + 4), R.Cell(addr + 8)]
        self.flags = 0                  # +0x0c
        self.pos = [0, 0, 0]            # +0x10
        self.radius = F_24              # +0x1c
        self.height = F_72              # +0x20
        self.class_def = None           # +0x24
        self.draw_half_width = 25       # +0x28 u8
        self.draw_height = 73           # +0x29 u8
        self.props = None               # +0x2c: list of 'key=value' byte strings
        self.vz = 0                     # +0x30
        self.class_name = None          # +0x34: set by whoever called the factory
        self.angle = 0                  # +0x38 u16
        self.seed = 0                   # +0x44: state of the object's own generator
        self.vtable = VT_GAMEOBJECT     # +0x48
        self.type_name = b'10GameObject'    # the name in the table's type-info object
        self.alive = True
        self.tag = None                 # free for the user of the model

    def rand(self):
        """GameObject_rand 0x1509d0."""
        self.seed = (self.seed * R.Lcg.MULTIPLIER + R.Lcg.INCREMENT) & M32
        return self.seed >> 16

    def __repr__(self):
        return '<GameObject 0x%x flags 0x%x>' % (self.addr, self.flags)


def props_find(props, key, nth=0):
    """obj_getPropStr 0x14f4c0 on a bare list: the text after 'key=' of the nth entry whose
    first len(key) bytes equal key and whose next byte is '='; None when there is none.
    The original lower-cases the KEY (its own argument, in place) before comparing and
    compares case-sensitively, so a property whose key is written with a capital letter
    is never found.  A null list gives None."""
    if props is None:
        return None
    key = bytes(key).lower()
    for entry in props:
        entry = bytes(entry)
        if entry[:len(key)] == key and entry[len(key):len(key) + 1] == b'=':
            if nth == 0:
                return entry[len(key) + 1:]
            nth -= 1
    return None


def atoi(text):
    """C atoi on bytes: optional blanks and sign, then digits; 0 when there are none."""
    text = bytes(text).lstrip(b' \t\n\v\f\r')
    sign, pos = 1, 0
    if text[:1] in (b'+', b'-'):
        sign, pos = (-1 if text[:1] == b'-' else 1), 1
    value = 0
    while pos < len(text) and 48 <= text[pos] <= 57:
        value = value * 10 + text[pos] - 48
        pos += 1
    return s32(sign * value)


def props_int(props, key, nth=0):
    """obj_getPropInt 0x14c880: atoi of the value, 0 when absent."""
    text = props_find(props, key, nth)
    return 0 if text is None else atoi(text)


# =======================================================================================
# 3. The name table: how scripts find objects
# =======================================================================================

def name_hash(name):
    """The hash of objNames_add 0x14bd6c-0x14bdd0 (the same code is in objNames_remove and
    world_findObjectsByName): per character, upper case folded to lower,
    h += c; h += h << 10; h ^= h >> 6;  then  h += h << 3; h ^= h >> 11;  slot = h & 0x1ff.
    h is a SIGNED 32-bit number, so both right shifts are arithmetic.  ASCII only: the
    original indexes the C library's character table with a signed char."""
    h = 0
    for c in bytes(name):
        if c >= 0x80:
            raise ObjectError('non-ASCII name: the original indexes its table with a negative number')
        if 65 <= c <= 90:
            c += 0x20
        h = s32(h + c)
        h = s32(h + (h << 10))
        h = s32(h ^ (h >> 6))
    h = s32(h + (h << 3))
    h = s32(h ^ (h >> 11))
    return h & 0x1FF


def strip_quotes(name):
    """str_stripQuotes 0x14f428 / the head of objNames_add 0x14bd0c-0x14bd4c: a name that
    starts with a double quote loses it and is cut at the next one.  The original edits the
    property string in place, so the destructor and every later property lookup see the
    stripped name (World.construct does the same to a property list)."""
    name = bytes(name)
    if name[:1] != b'"':
        return name
    rest = name[1:]
    end = rest.find(b'"')
    return rest if end < 0 else rest[:end]


class NameTable:
    """objNames_add 0x14bce0, objNames_remove 0x14be58, world_findObjectsByName 0x14bf58.
    512 slots, open addressing with a step of one.  keys[i] is the name a slot was last
    given (it is never cleared by a removal), objs[i] the object or None."""
    SIZE = 512

    def __init__(self):
        self.clear()

    def clear(self):
        self.keys = [None] * self.SIZE
        self.objs = [None] * self.SIZE
        self.count = 0                  # 0x5f86f8: adds minus removes, never read

    def add(self, name, obj):
        """Insert at the first slot, from the hash on, whose key is empty OR whose object
        is gone and whose key equals the name ignoring case.  A slot left by another
        name's object is stepped over.  Returns the slot.  (A full table never ends the
        search in the original.)"""
        name = strip_quotes(name)
        self.count += 1
        slot = name_hash(name)
        for _ in range(self.SIZE):
            key = self.keys[slot]
            if key is None or (self.objs[slot] is None and bytes(key).lower() == bytes(name).lower()):
                self.keys[slot] = name
                self.objs[slot] = obj
                return slot
            slot = (slot + 1) & 0x1FF
        raise ObjectError('name table full: the original would search for ever')

    def remove(self, name, obj):
        """Clear the first slot HOLDING THE OBJECT, searching from the name's hash through
        the whole table (523 probes); keys are not compared and empty keys do not stop the
        search.  The key stays behind.  Returns the slot, or None when the object is in
        no slot."""
        self.count -= 1
        slot = name_hash(name)
        for _ in range(0x20B):
            if self.objs[slot] is obj:
                self.objs[slot] = None
                return slot
            slot = (slot + 1) & 0x1FF
        return None

    def find(self, name, limit):
        """world_findObjectsByName(name, out, limit): the objects in probe order from the
        hash until the first empty key, taking slots whose key equals the name ignoring
        case and whose object is still there; stops when limit - 1 are found.  With a
        limit of 1 or less the count never equals limit - 1 and the original runs on
        without a bound; the model refuses."""
        if limit < 2:
            raise ObjectError('limit below 2: the original has no bound')
        out = []
        slot = name_hash(name)
        for _ in range(self.SIZE + 1):
            key = self.keys[slot]
            if key is None:
                return out
            if bytes(key).lower() == bytes(name).lower() and self.objs[slot] is not None:
                out.append(self.objs[slot])
                if len(out) == limit - 1:
                    return out
            slot = (slot + 1) & 0x1FF
        raise ObjectError('no empty key in the table: the original would search for ever')

    def find_first(self, name):
        """world_findObjectByName 0x14f498: find(name, 2), first entry or None."""
        found = self.find(name, 2)
        return found[0] if found else None


# =======================================================================================
# 4. The task list
# =======================================================================================

class Task:
    __slots__ = ('fn', 'priority', 'name', 'flags')

    def __init__(self, fn, priority, name, flags):
        self.fn, self.priority, self.name, self.flags = fn, priority, name, flags

    def __repr__(self):
        return '<Task %r %d %r %d>' % (self.fn, self.priority, self.name, self.flags)


class TaskList:
    """task_add 0x19e4a0, task_remove 0x19e664, task_isRunning 0x19e5e8, tasks_call
    0x19e798.  A table sorted by priority (low first) and ONE global cursor.  fn is the
    task's identity; flags bit 0 marks a draw task (value 2 exists and is never tested)."""

    def __init__(self):
        self.tasks = []
        self.cursor = 0                 # 0x44fdbc

    def add(self, fn, priority, name, flags):
        """Nothing when fn is already there.  Otherwise insert behind every record whose
        priority is less than or EQUAL to the new one; when the cursor is at or behind the
        insertion index it moves up by one, so a walk in progress neither repeats nor
        skips a task.  Returns the index, or None."""
        for task in self.tasks:
            if task.fn == fn:
                return None
        if len(self.tasks) >= MAX_TASKS:
            raise ObjectError('more than %d tasks: the original writes past its table' % MAX_TASKS)
        index = len(self.tasks)
        while index > 0 and priority < self.tasks[index - 1].priority:
            index -= 1
        if not self.cursor < index:
            self.cursor += 1
        self.tasks.insert(index, Task(fn, priority, name, flags))
        return index

    def remove(self, fn):
        """Close the gap of the first record with this fn; the cursor moves down by one
        when it is at or behind that index.  Returns the index, or None."""
        for index, task in enumerate(self.tasks):
            if task.fn == fn:
                if not self.cursor < index:
                    self.cursor -= 1
                del self.tasks[index]
                return index
        return None

    def is_running(self, name):
        """Case-sensitive compare of the name with every record."""
        return any(task.name == name for task in self.tasks)

    def call(self, exclude, include, invoke):
        """tasks_call(exclude, include): cursor = 0; then, while the cursor is inside the
        table, call the record under it when  flags & exclude == 0  and  (include == -1 or
        flags & include != 0), and step the cursor.  The table and the cursor are re-read
        after every call, which is what lets a task add or remove tasks (itself included).
        invoke(fn) stands for the indirect call.  The run pass is call(1, -1), the draw
        pass call(0, 1)."""
        count = len(self.tasks)
        self.cursor = 0
        if count <= 0:
            return
        while True:
            task = self.tasks[self.cursor]
            if not task.flags & exclude and (include == -1 or task.flags & include):
                invoke(task.fn)
            self.cursor += 1
            if not self.cursor < len(self.tasks):
                return


class Pad:
    """The three words of g_pads[i] (0x41bfd8 + 0x58 i) that tasks_run touches."""
    __slots__ = ('held', 'pressed', 'edge2')

    def __init__(self, held=0, pressed=0, edge2=0):
        self.held, self.pressed, self.edge2 = held, pressed, edge2     # +8, +0xc, +0x10


# =======================================================================================
# 5. The world
# =======================================================================================

class World:
    """The lists of world.cc and everything that moves objects between them.

    Callbacks (set them; the defaults do the base-class thing):
      on_run(obj)             virtual slot 4, called by run_objects
      on_destroy(obj, flags)  virtual slot 1; the default is self.destroy (GameObject_dtor)
      is_frozen()             game_isFrozen 0x1ebdf8; default False
      res_find(lump, name)    res_find 0x17365c, for class definitions; default 0
    """

    def __init__(self):
        self.pool = R.Pool()
        self.handles = R.HandlePool()
        self.shared = R.SharedRandom(0)             # g_randSeed
        self.grid = [R.Cell(G_GRID + 4 * i) for i in range(GRID_DIM * GRID_DIM)]
        self.grid_b = [R.Cell(G_GRID_B + 4 * i) for i in range(GRID_DIM * GRID_DIM)]
        self.off_grid = R.Cell(G_OFF_GRID)
        self.always_draw = R.Cell(G_ALWAYS_DRAW)
        self.delete_list = R.Cell(G_DELETE_LIST)
        self.run_active = R.Cell(G_RUN_ACTIVE)
        self.run15 = [R.Cell(G_RUN_15 + 4 * i) for i in range(15)]
        self.run60 = [R.Cell(G_RUN_60 + 4 * i) for i in range(60)]
        self.cursor15 = 0
        self.cursor60 = 0
        self.frame = 0                              # g_simFrame
        self.exclude_mask = 0                       # g_excludeMask
        self.network_mode = 0                       # g_networkMode
        self.cull_by_camera = 1                     # g_cullByCamera: 1 in the executable
        self.camera_focus = [0, 0, 0]               # g_cameraFocus
        self.centres = []                           # g_activityCenters[0 .. count)
        self.pool_free_count = 100000               # g_poolFreeCount
        self.tearing_down = 0
        self.lump_generation = 1                    # g_lumpGeneration 0x41bf78: 1 in the executable
        self.names = NameTable()
        self.tasks = TaskList()
        self.objects = {}                           # address -> live object
        self.on_run = lambda obj: None
        self.on_destroy = self.destroy
        self.is_frozen = lambda: False
        self.res_find = lambda lump, name: 0
        # what tasks_run needs besides the task list
        self.pads = [Pad() for _ in range(4)]
        self.menu_lockout = 0                       # 0x41b4fc
        self.menu_lockout_hold = 0                  # 0x41b500
        self.warmup_frames = 0                      # 0x506048
        self.end_of_tick = lambda: None             # rebuildAlivePlayers, checkAllDead, rumble
        # the level start marker
        self.start_rank = 0
        self.spawn_pos = [[0, 0, 0] for _ in range(4)]
        self.spawn_facing = [0, 0, 0, 0]

    # ---- start-up -------------------------------------------------------------------
    def init(self):
        """world_init 0x14c370: register the two tasks, then zero both grids, the
        off-grid list and the name table.  The cells are zeroed, not cleared: nodes still
        linked there are simply forgotten.  The run lists, the delete list and the
        always-draw list are not touched."""
        self.tasks.add(0x14B910, 10, b'runObjects', 0)
        self.tasks.add(0x14B168, 21, b'drawObjects', 1)
        for cell in self.grid:
            cell.next = None
        for cell in self.grid_b:
            cell.next = None
        self.off_grid.next = None
        self.names.clear()

    # ---- creation ---------------------------------------------------------------------
    def home_cell(self, obj, honour_flag2):
        """The list an object's grid link belongs in: a cell of grid B when flag 0x800 is
        set, else of grid A, or the off-grid list when a cell coordinate is outside
        0..119.  obj_linkToGrid and the constructor also send flag 0x2 to the off-grid
        list (honour_flag2); obj_updateGridCell does not look at that flag."""
        col = cell_coord(obj.pos[0])
        row = cell_coord(obj.pos[1])
        if honour_flag2 and obj.flags & FLAG_NOT_GRID_DRAWN:
            return self.off_grid
        if not (0 <= col < GRID_DIM and 0 <= row < GRID_DIM):
            return self.off_grid
        grid = self.grid_b if obj.flags & FLAG_GRID_B else self.grid
        return grid[row * GRID_DIM + col]

    def construct(self, addr, pos, class_def=None, props=None, stale_props=None):
        """GameObject_ctor 0x14cb10 (this, pos, classDef, props), in the order of its
        stores and calls:

          1. heads +0, +4, +8 = 0; vtable; radius 24; height 72; flags 0; draw bytes 25,
             73; position; +0x34 = 0; +0x24 = classDef.
          2. A class definition whose generation is not the current one has every name
             looked up (res_find) and takes the current generation.
          3. Grid link (handle_link, so at the FRONT of the list): flags were just zeroed,
             so this is always a cell of grid A, or the off-grid list when outside.
          4. 'hide' is looked up through +0x2c BEFORE the constructor stores the property
             list there.  For a block fresh from pool_new that word is 0 and nothing
             happens; stale_props stands for whatever list an unzeroed block still points
             at (then a non-zero hide moves the grid node to the front of the off-grid
             list).
          5. +0x2c = props.
          6. ONE draw from the shared seed; the 16-bit draw is the object's own seed.
          7. Every 'name=' property, in list order, is entered in the name table.

        The object is on NO run list afterwards; the derived constructor chooses."""
        obj = GameObject(addr)
        obj.pos = [pos[0] & M32, pos[1] & M32, pos[2] & M32]
        obj.class_def = class_def
        if class_def is not None and class_def.generation != self.lump_generation:
            for entry in class_def.entries:
                entry[1] = self.res_find(class_def.lump, entry[0])
            class_def.generation = self.lump_generation
        self.handles.link(self.home_cell(obj, True), obj.heads[2], obj)
        if props_int(stale_props, b'hide'):
            self.move_off_grid(obj)
        obj.props = props
        obj.seed = self.shared.draw()
        for index in self._name_entries(obj):
            name = strip_quotes(obj.props[index][5:])
            if isinstance(obj.props, list):
                obj.props[index] = b'name=' + name      # the in-place edit of objNames_add
            self.names.add(name, obj)
        self.objects[addr] = obj
        return obj

    @staticmethod
    def _name_entries(obj):
        """Indices of the 'name=' properties, in list order (the constructor and the
        destructor ask for the 0th, 1st, ... until there is none)."""
        if obj.props is None:
            return []
        return [index for index, entry in enumerate(obj.props) if bytes(entry[:5]) == b'name=']

    def new_object(self, size, pos, class_def=None, props=None):
        """What every creator does: pool_new(size), and only when that gave a block, the
        constructor.  A refused allocation creates nothing and draws nothing."""
        addr = self.pool.new(size)
        if addr == 0:
            return None
        return self.construct(addr, pos, class_def, props)

    # ---- deletion ---------------------------------------------------------------------
    def destroy(self, obj, flags=3):
        """GameObject_dtor 0x14cf90 (this, flags) - the last link of every destructor
        chain: the vtable goes back to GameObject's; every 'name=' property is taken out
        of the name table; then handle_clear on +8 (grid), +4 (run list), +0 (every handle
        that pointed here, the delete-list and always-draw links among them), in that
        order; with flags bit 0 the block goes back to the pool at once."""
        obj.vtable = VT_GAMEOBJECT
        for index in self._name_entries(obj):
            self.names.remove(strip_quotes(obj.props[index][5:]), obj)
        self.handles.clear(obj.heads[2])
        self.handles.clear(obj.heads[1])
        self.handles.clear(obj.heads[0])
        if flags & 1:
            self.pool.free(obj.addr)
            obj.alive = False
            self.objects.pop(obj.addr, None)

    def delete(self, obj):
        """obj_delete 0x14f200: leave the run list now, join the FRONT of the delete list
        through head +0.  The grid link stays, so queries still return the object until it
        is destroyed at the start of the next run_objects (or by flush_delete_list)."""
        node = obj.heads[1].next
        if node is not None:
            self.handles.remove(node)
        self.handles.link(self.delete_list, obj.heads[0], obj)

    def flush_delete_list(self):
        """world_flushDeleteList 0x14f3a8, step 1 of runObjects, the tail of
        world_loadRecords: slot 1 with argument 3 for every object on the delete list,
        front to back (last deleted first), skipping objects the exclude mask names.  An
        object deleted from inside one of these destructors lands in front of the
        iterator and waits for the next flush."""
        it = R.Iterator(self.delete_list, self.exclude_mask)
        while not it.done:
            obj = it.current
            if obj is not None:
                self.on_destroy(obj, 3)
            it.advance()
        it.end()

    # ---- the grids --------------------------------------------------------------------
    def _grid_node(self, obj):
        back = obj.heads[2].next
        if back is None:
            raise ObjectError('object has no grid link: the original would follow a null pointer')
        return back.partner

    def link_to_grid(self, obj):
        """obj_linkToGrid 0x14f120: a first grid link for an object that has none (its one
        caller is the prediction copy, after the clone).  Flag 0x2 or a position outside
        the grid selects the off-grid list."""
        self.handles.link(self.home_cell(obj, True), obj.heads[2], obj)

    def update_grid_cell(self, obj):
        """obj_updateGridCell 0x14f028: take the grid node out of its list and put it at
        the FRONT of the list of the current position - even when that is the list it was
        in.  The order inside a cell is therefore the reverse order of the last movement
        calls.  Flag 0x2 is not consulted, and an object that was moved off the grid
        (hidden) comes back onto it."""
        node = self._grid_node(obj)
        _unlink(node)
        _push(self.home_cell(obj, False), node)

    def move_off_grid(self, obj):
        """obj_moveOffGrid 0x14ef48: grid node to the front of the off-grid list."""
        node = self._grid_node(obj)
        _unlink(node)
        _push(self.off_grid, node)

    def is_off_grid(self, obj):
        """obj_isOffGrid 0x14efa0: a walk of the off-grid list with mask 0."""
        return any(other is obj for other in R.walk(self.off_grid, 0))

    def add_to_always_draw(self, obj):
        """obj_addToAlwaysDraw 0x14edd8: link (through head +0) and set flag 0x2."""
        self.handles.link(self.always_draw, obj.heads[0], obj)
        obj.flags |= FLAG_NOT_GRID_DRAWN

    def add_to_always_draw_once(self, obj):
        """obj_addToAlwaysDrawOnce 0x14ee18: the same unless a walk with the exclude mask
        finds the object already there."""
        if any(other is obj for other in R.walk(self.always_draw, self.exclude_mask)):
            return
        self.add_to_always_draw(obj)

    def clear_always_draw(self):
        """world_clearAlwaysDraw 0x14eec0: clear flag 0x2 on every member the exclude mask
        lets through, then empty the list."""
        for obj in R.walk(self.always_draw, self.exclude_mask):
            obj.flags &= ~FLAG_NOT_GRID_DRAWN & M32
        self.handles.clear(self.always_draw)

    # ---- the run lists ------------------------------------------------------------------
    def _leave_run_list(self, obj):
        node = obj.heads[1].next
        if node is not None:
            self.handles.remove(node)

    def stop_running(self, obj):
        """obj_stopRunning 0x14f290."""
        self._leave_run_list(obj)

    def run_every_frame(self, obj):
        """obj_runEveryFrame 0x14f248: leave the current run list, join the FRONT of the
        every-frame list - also when the object already was on it, which moves it to the
        front."""
        self._leave_run_list(obj)
        self.handles.link(self.run_active, obj.heads[1], obj)

    def run_every_60(self, obj):
        """obj_runEvery60 0x14f2b8: the cursor is stepped FIRST (0..59, wrapping), then the
        object joins the front of that list.  It will run in the frames whose number mod
        60 is the cursor value."""
        self._leave_run_list(obj)
        self.cursor60 += 1
        if not self.cursor60 < 60:
            self.cursor60 = 0
        self.handles.link(self.run60[self.cursor60], obj.heads[1], obj)

    def run_every_15(self, obj):
        """obj_runEvery15 0x14f330: the same with 15 lists and their own cursor."""
        self._leave_run_list(obj)
        self.cursor15 += 1
        if not self.cursor15 < 15:
            self.cursor15 = 0
        self.handles.link(self.run15[self.cursor15], obj.heads[1], obj)

    # ---- activity -----------------------------------------------------------------------
    def is_active(self, obj, radius):
        """The test inside obj_updateActive 0x14db08-0x14dc20: is the object within radius
        (44000 when flag 0x80000 is set) of the camera focus (when g_cullByCamera) or of
        any activity centre.  Distances are compared squared: (dx*dx + dy*dy) + dz*dz, all
        three axes, against the INTEGER radius squared in 32 bits and converted to float -
        a radius of 46341 or more wraps negative and nothing is ever inside it."""
        if obj.flags & FLAG_FAR_ACTIVE:
            radius = FAR_ACTIVE_RADIUS
        limit = R.from_int(s32(s32(radius) * s32(radius)))
        centres = [self.camera_focus] if self.cull_by_camera else self.centres
        for centre in centres:
            dx = R.sub(obj.pos[0], centre[0])
            dy = R.sub(obj.pos[1], centre[1])
            dz = R.sub(obj.pos[2], centre[2])
            if R.lt(R.add(R.add(R.mul(dx, dx), R.mul(dy, dy)), R.mul(dz, dz)), limit):
                return 1
        return 0

    def update_active(self, obj, was_active, radius):
        """obj_updateActive(obj, wasActive, radius) -> 0 or 1.  The run list changes only
        when the answer differs from what the caller says it was last time: to the front of
        the every-frame list when the object became active, to the front of the next
        60-frame list (cursor stepped first) when it stopped being active.  The caller
        keeps the answer; the function stores nothing in the object."""
        active = self.is_active(obj, radius)
        if active == was_active:
            return active
        if active:
            self.run_every_frame(obj)
        else:
            self.run_every_60(obj)
        return active

    # ---- queries --------------------------------------------------------------------------
    def collect_in_box(self, lo, hi, limit):
        """world_collectObjectsInBox 0x14a928 (min, max, out, limit) -> objects in the
        order the original writes them (it then writes a null, and returns the address of
        that null).

        Cells: rows (int)min.y + 0x3ba0 >> 8 up to (int)max.y + 0x3c60 >> 8, columns the
        same from x: the box grown by 96 units, low ends clamped to 0, high ends to 119.
        Grid A only.  Rows ascending; inside a row, columns ascending; inside a cell, list
        order (most recently linked or moved first).

        An object is taken unless: its flags meet the exclude mask (read again for every
        object); it has flag 0x20000; x + radius < min.x; max.x < x - radius; the same for
        y; max.z < z; z + height < min.z.  The walk ENDS at the first object that would be
        number `limit`: at most limit - 1 are returned, and they are the first ones in
        walk order, not the nearest."""
        row_lo = max(s32(R.to_int(lo[1]) + QUERY_BIAS_LOW) >> CELL_SHIFT, 0)
        row_hi = min(s32(R.to_int(hi[1]) + QUERY_BIAS_HIGH) >> CELL_SHIFT, GRID_DIM - 1)
        col_lo = max(s32(R.to_int(lo[0]) + QUERY_BIAS_LOW) >> CELL_SHIFT, 0)
        col_hi = min(s32(R.to_int(hi[0]) + QUERY_BIAS_HIGH) >> CELL_SHIFT, GRID_DIM - 1)
        out = []
        limit = s32(limit)
        for row in range(row_lo, row_hi + 1):
            for col in range(col_lo, col_hi + 1):
                node = self.grid[row * GRID_DIM + col].next
                while node is not None:
                    obj = node.obj
                    node = node.next
                    if obj is None:
                        continue                    # an iterator standing in the cell
                    if obj.flags & self.exclude_mask or obj.flags & FLAG_PREDICTION_COPY:
                        continue
                    x, y, z, r = obj.pos[0], obj.pos[1], obj.pos[2], obj.radius
                    if R.lt(R.add(x, r), lo[0]) or R.lt(hi[0], R.sub(x, r)):
                        continue
                    if R.lt(R.add(y, r), lo[1]) or R.lt(hi[1], R.sub(y, r)):
                        continue
                    if R.lt(hi[2], z) or R.lt(R.add(z, obj.height), lo[2]):
                        continue
                    if not len(out) < limit - 1:
                        return out
                    out.append(obj)
        return out

    def collect_in_sphere(self, radius, centre, head):
        """world_collectInSphere 0x14ab80 (f12 radius, a0 centre, a1 unused, a2 list): box
        query of centre +- radius on three axes with a limit of 0x200 (511 objects); every
        result without flags 0x1, 0x4 or 0x8 whose distance sqrt((dx*dx + dy*dy) + dz*dz)
        is below radius + its own radius gets a node at the FRONT of `head`, so the list
        ends up in the REVERSE of query order.  Returns the objects added, in query
        order."""
        lo = [R.sub(centre[i], radius) for i in range(3)]
        hi = [R.add(centre[i], radius) for i in range(3)]
        added = []
        for obj in self.collect_in_box(lo, hi, 0x200):
            if obj.flags & 0xD:
                continue
            dx = R.sub(centre[0], obj.pos[0])
            dy = R.sub(centre[1], obj.pos[1])
            dz = R.sub(centre[2], obj.pos[2])
            dist = R.sqrt(R.add(R.add(R.mul(dx, dx), R.mul(dy, dy)), R.mul(dz, dz)))
            if R.lt(dist, R.add(radius, obj.radius)):
                self.handles.add(head, obj)
                added.append(obj)
        return added

    def find_by_class(self, type_name, limit):
        """world_findObjectsByClass 0x14c0b8: objects ON A RUN LIST whose C++ type name
        equals type_name (case-sensitive), in the order every-frame list, 15-frame lists 0
        to 14, 60-frame lists 0 to 59; walks use the exclude mask; stops at limit - 1."""
        out = []
        for head in [self.run_active] + self.run15 + self.run60:
            for obj in R.walk(head, self.exclude_mask):
                if obj.type_name == type_name:
                    out.append(obj)
                    if len(out) == limit - 1:
                        return out
        return out

    # ---- runObjects -------------------------------------------------------------------------
    def reap_cells(self):
        """The 16 grid-B cell indices the reaper looks at this frame (0x14b9d8-0x14ba48):
        with L = (frame << 4) & 0x0fffffff, the cells after column L % 120 of row
        (L / 120) % 120, advancing by column and wrapping to the next row and from row 119
        to row 0.  The whole grid comes round every 900 frames."""
        value = (self.frame << 4) & 0x0FFFFFFF
        col = value % GRID_DIM
        row = (value // GRID_DIM) % GRID_DIM
        cells = []
        for _ in range(REAP_CELLS_PER_FRAME):
            col += 1
            if not col < GRID_DIM:
                row += 1
                col = 0
                if not row < GRID_DIM:
                    row = 0
            cells.append(row * GRID_DIM + col)
        return cells

    def reap(self):
        """Step 3 of runObjects, 0x14b9c8-0x14bb1c, when the sampled free count is below
        300.  In each of the 16 cells the list is walked from its head WITHOUT an iterator
        and without the exclude mask; the first object that has flag 0x1000 - and, offline
        while the count is still 200 or more, lies farther than 480 from the camera focus
        (three axes) - is destroyed through slot 1 with argument 3, and the cell is done.
        In a net game the camera is not consulted.  Returns the objects destroyed."""
        victims = []
        for index in self.reap_cells():
            node = self.grid_b[index].next
            while node is not None:
                obj = node.obj
                if obj is None:
                    raise ObjectError('iterator in a grid-B cell during the reaper')
                if obj.flags & FLAG_EXPENDABLE:
                    spared = False
                    if not self.network_mode and not self.pool_free_count < REAP_NEAR_CAMERA_BELOW:
                        focus = self.camera_focus
                        dx = R.sub(obj.pos[0], focus[0])
                        dy = R.sub(obj.pos[1], focus[1])
                        dz = R.sub(obj.pos[2], focus[2])
                        dist = R.add(R.add(R.mul(dx, dx), R.mul(dy, dy)), R.mul(dz, dz))
                        spared = not R.lt(F_480_SQ, dist)
                    if not spared:
                        victims.append(obj)
                        self.on_destroy(obj, 3)
                        break
                node = node.next
        return victims

    def _run_list(self, head):
        it = R.Iterator(head, self.exclude_mask)
        while not it.done:
            obj = it.current
            if not obj.flags & FLAG_NOT_RUN:
                self.on_run(obj)
            it.advance()
        it.end()

    def run_objects(self):
        """runObjects 0x14b910, run task priority 10 - one tick of every object:

          1. flush the delete list (iterator with the exclude mask);
          2. when frame & 0x3f == 0, sample the pool: pool_free_count = pool.count_free();
          3. when that count is below 300, the reaper;
          4. unless is_frozen(): slot 4 of every object on the every-frame list, then on
             15-frame list number frame % 15, then on 60-frame list number frame % 60,
             each walked front to back with an iterator and the exclude mask (read again
             for each list), skipping objects with flag 0x8000.

        Consequences of step 4 that follow from the iterator standing behind the current
        node and new links going to the front (all executed against the original):
          * an object linked to the list being walked is not visited by that walk;
          * an object linked, during an earlier walk of the same call, to the slow list
            that is walked later in this call IS visited: an object created in the
            every-frame walk and given to obj_runEvery15/60 runs in the tick of its
            creation when the stepped cursor equals frame % 15 (frame % 60), and an object
            that leaves the every-frame list through obj_updateActive runs a SECOND time
            in the same tick when the 60-cursor lands on frame % 60;
          * an object destroyed or unlinked before the walk reaches it is not run; the
            current object may destroy itself.
        The frame number is read again for each slow list and is not advanced here."""
        self.flush_delete_list()
        if self.frame & POOL_SAMPLE_MASK == 0:
            self.pool_free_count = self.pool.count_free()
        if self.pool_free_count < REAP_BELOW:
            self.reap()
        if self.is_frozen():
            return
        self._run_list(self.run_active)
        self._run_list(self.run15[_mod(self.frame, 15)])
        self._run_list(self.run60[_mod(self.frame, 60)])

    # ---- walkers ----------------------------------------------------------------------------
    def for_each_grid_object(self, fn):
        """world_forEachGridObject 0x14a610: the off-grid list, then every cell of grid A
        in memory order (row 0 column 0..119, row 1, ...), then grid B the same way; each
        list with an iterator and the exclude mask."""
        for head in [self.off_grid] + self.grid + self.grid_b:
            if head.next is None:
                continue
            it = R.Iterator(head, self.exclude_mask)
            while not it.done:
                fn(it.current)
                it.advance()
            it.end()

    def for_each_run_object(self, fn):
        """world_forEachRunObject 0x14a7c8: the every-frame list, the 15 lists, the 60
        lists, with the exclude mask."""
        for head in [self.run_active] + self.run15 + self.run60:
            it = R.Iterator(head, self.exclude_mask)
            while not it.done:
                fn(it.current)
                it.advance()
            it.end()

    # ---- teardown ---------------------------------------------------------------------------
    def delete_all_objects(self):
        """world_deleteAllObjects 0x14c460 (level unload): pool_free_count = 100000, both
        cursors = 0, then slot 1 with argument 3 for everything on the delete list
        (exclude mask), in every cell of grid A in memory order, in every cell of grid B,
        and on the off-grid list (these three with mask 0); last, the name table is
        zeroed.  The run lists are not walked: they empty because every object's
        destructor clears its own run link.  g_worldTearingDown is 1 meanwhile."""
        self.pool_free_count = 100000
        self.cursor60 = 0
        self.cursor15 = 0
        self.tearing_down = 1
        self.flush_delete_list()
        for head in self.grid + self.grid_b + [self.off_grid]:
            if head.next is None:
                continue
            it = R.Iterator(head, 0)
            while not it.done:
                obj = it.current
                if obj is not None:
                    self.on_destroy(obj, 3)
                it.advance()
            it.end()
        self.names.clear()
        self.tearing_down = 0

    # ---- the tick -----------------------------------------------------------------------------
    def tasks_run(self, count, invoke):
        """tasks_run 0x3226e4 (n): n simulation ticks.

          * net game: menu_lockout = 0;
          * the two edge words of the four pads are saved;
          * n times: the run pass tasks.call(1, -1); offline only, frame += 1 unless
            is_frozen() or warmup_frames is non-zero; the pads' edge words are zeroed (so
            a press is seen by the first tick only); end_of_tick() - in the original
            game_rebuildAlivePlayers, game_checkAllDead and pad_updateRumble, in that
            order;
          * once: a positive menu_lockout with the hold flag clear becomes 0 when no pad
            has a button held (held & 0xff0fffff), otherwise it drops by one;
          * the saved edge words are put back.
        In a net game the frame number is set by net_frameLoop around the call."""
        if self.network_mode:
            self.menu_lockout = 0
        saved = [(pad.pressed, pad.edge2) for pad in self.pads]
        for _ in range(max(s32(count), 0)):
            self.tasks.call(1, -1, invoke)
            if not self.network_mode and not self.is_frozen() and not self.warmup_frames:
                self.frame = s32(self.frame + 1)
            for pad in self.pads:
                pad.pressed = pad.edge2 = 0
            self.end_of_tick()
        if s32(self.menu_lockout) > 0 and not self.menu_lockout_hold:
            if any(pad.held & 0xFF0FFFFF for pad in self.pads):
                self.menu_lockout -= 1
            else:
                self.menu_lockout = 0
        for pad, (pressed, edge2) in zip(self.pads, saved):
            pad.pressed, pad.edge2 = pressed, edge2

    # =====================================================================================
    # 6. Activity centres and the "near view" test
    # =====================================================================================
    def set_object_vis(self, dialog_obj, camera_mode, cutscene_active, players):
        """gameSetObjectVis 0x1e4d48, a run task that comes before runObjects in every
        tick.  players is the list of each slot's object (or None), g_numPlayers long.

          * a dialog is open with an object (dialog_objIfOpen 0x231050): that object's
            position is the ONLY centre and the camera is not used;
          * otherwise cull_by_camera = (camera mode != 1) - the mode word of this
            machine's camera - except that in a net game it is forced to 0 unless a
            cutscene is active; and the centres are the positions of the slots that have
            an object, in slot order (dead players included)."""
        if dialog_obj is not None:
            self.cull_by_camera = 0
            self.centres = [list(dialog_obj.pos)]
            return
        self.cull_by_camera = 1 if camera_mode != 1 else 0
        if self.network_mode and not cutscene_active:
            self.cull_by_camera = 0
        self.centres = [list(obj.pos) for obj in players if obj is not None]

    def is_near_view(self, pos, reach, players):
        """isNearView 0x1e77c0 (a0 pos, f12 reach) -> 0 or 1: |dx| <= reach and |dy| <=
        reach - a SQUARE in x and y, height ignored, unlike obj_updateActive - around the
        camera focus when cull_by_camera, otherwise around any player slot's object.  The
        four compares are pos <= c + reach and c - reach <= pos on each axis."""
        centres = [self.camera_focus] if self.cull_by_camera else [o.pos for o in players if o is not None]
        for centre in centres:
            if (R.le(pos[0], R.add(centre[0], reach)) and R.le(R.sub(centre[0], reach), pos[0]) and
                    R.le(pos[1], R.add(centre[1], reach)) and R.le(R.sub(centre[1], reach), pos[1])):
                return 1
        return 0

    @staticmethod
    def alive_players(players, is_local_slot):
        """game_rebuildAlivePlayers 0x1e72f8, called at the END of every tick: the slots
        whose object exists and has not flag 0x8, in slot order -> (alive slots, local
        alive slots, first local alive slot or -1)."""
        alive, local = [], []
        for slot, obj in enumerate(players):
            if obj is not None and not obj.flags & FLAG_DEAD:
                alive.append(slot)
                if is_local_slot(slot):
                    local.append(slot)
        return alive, local, (local[0] if local else -1)

    # =====================================================================================
    # 7. Free-spot search and the level start marker
    # =====================================================================================
    def find_free_spot(self, centre, spread, radius, any_height, terrain_blocked, terrain_height):
        """world_findFreeSpot 0x14acf8 (out, centre, int spread, int radius, bool *ok,
        anyHeight) -> (position, ok).  Up to 50 tries:

          1. a point in the unit ball by rejection from the SHARED seed (three draws per
             sample, repeated while x*x + y*y + z*z > 1); only x and y are used;
          2. candidate = centre + (x * spread, y * spread, 0);
          3. terrain_blocked(radius, candidate) must be 0.0 (terrain_testFlag1 0x183b48);
          4. h = terrain_height(radius, candidate) (0x183820); unless any_height, h -
             centre.z must be below 6 (a floor far BELOW the centre passes);
          5. the result becomes (candidate.x, candidate.y, h) - kept even if step 6 fails;
          6. box query of result.xy +- radius, h +- 100000, limit 0x80: the try succeeds
             unless a result without flag 0x1 has dx*dx + dy*dy <= radius*radius + r*r
             (the SUM of the squares, which is less than (radius + r) squared).
        After 50 failed tries ok is 0 and the position is the last one that reached step 5,
        or the centre.  terrain_blocked and terrain_height take float patterns and return
        one."""
        f_spread = R.from_int(spread)
        f_radius = R.from_int(radius)
        radius_sq = R.from_int(s32(s32(radius) * s32(radius)))
        result = list(centre)
        tries = 0
        while tries < 50:
            x, y, _z = self.shared.in_unit_sphere()
            off_x = R.mul(x, f_spread)
            off_y = R.mul(y, f_spread)
            cand = [R.add(off_x, centre[0]), R.add(off_y, centre[1]), centre[2]]
            if not R.eq(terrain_blocked(f_radius, cand), 0):
                tries += 1
                continue
            probe = [R.add(off_x, centre[0]), R.add(off_y, centre[1]), R.add(0, centre[2])]
            height = terrain_height(f_radius, probe)
            if not R.lt(R.sub(height, centre[2]), F_6) and not any_height:
                tries += 1
                continue
            result = [R.add(centre[0], off_x), R.add(centre[1], off_y), height]
            lo = [R.sub(result[0], f_radius), R.sub(result[1], f_radius), R.sub(height, F_100000)]
            hi = [R.add(result[0], f_radius), R.add(result[1], f_radius), R.add(height, F_100000)]
            blocked = False
            for obj in self.collect_in_box(lo, hi, 0x80):
                if obj.flags & FLAG_NOT_SOLID:
                    continue
                dy = R.sub(obj.pos[1], result[1])
                dx = R.sub(obj.pos[0], result[0])
                reach = R.add(radius_sq, R.mul(obj.radius, obj.radius))
                if R.le(R.add(R.mul(dx, dx), R.mul(dy, dy)), reach):
                    blocked = True
                    break
            if not blocked:
                break
            tries += 1
        return result, int(tries != 50)

    def player1_marker(self, addr, pos, angle, props, prev_level, entrance, gate_travel,
                       terrain_blocked, terrain_height):
        """Player1_ctor 0x158928: the level's start marker.  A base object with flags 0x3
        (so it stays in the grid cell the base constructor chose) and the marker's facing.
        The marker then competes for g_playerStartRank (0 at level load, 3 after a load
        from a save):

          rank 3 already                      -> nothing more
          rank <= 0                           -> take, rank 1
          rank 1 and a non-zero 'default'     -> take, rank 1
          'from' equals the previous level    -> take, rank 2   (only when not gate travel)
          gate travel and 'from' is "gate"    -> take, rank 3
          not gate travel and 'name' equals the entrance name -> take, rank 3

        (tests in that order; a later one overrides the rank of an earlier one).  Taking
        fills ALL FOUR spawn slots: for each, find_free_spot(marker position, spread 36,
        radius 24) and then one more shared draw: facing = angle + draw % 4000 - 2000.
        gate_travel is the byte at 0x41b51e."""
        obj = self.construct(addr, pos, None, props)
        obj.flags |= 3
        obj.vtable = VT_PLAYER1
        obj.type_name = b'7Player1'
        obj.angle = angle & 0xFFFF
        rank = self.start_rank
        if rank == 3:
            return obj
        source = props_find(props, b'from')
        name = props_find(props, b'name')
        take = False
        if rank <= 0:
            take, self.start_rank = True, 1
        elif rank < 2 and props_int(props, b'default'):
            take, self.start_rank = True, 1
        if source is not None and source == prev_level and not gate_travel:
            take, self.start_rank = True, 2
        elif gate_travel and source == b'gate':
            take, self.start_rank = True, 3
        if name is not None and not gate_travel and name == entrance:
            take, self.start_rank = True, 3
        if take:
            for slot in range(4):
                spot, _ok = self.find_free_spot(obj.pos, 0x24, 0x18, 0, terrain_blocked, terrain_height)
                draw = self.shared.draw()
                self.spawn_pos[slot] = spot
                self.spawn_facing[slot] = (obj.angle + draw % 4000 - 2000) & 0xFFFF
        return obj

    # =====================================================================================
    # 8. Level object records
    # =====================================================================================
    def load_records(self, blob, factory, filter_only=False, save_filter=None, load_state=None):
        """world_loadRecords 0x14e808 (blob, filterOnly) -> bytes consumed.  blob is a
        RecordBlob.  Records are taken strictly in file order; for each one:

          * with filter_only, the record is skipped unless save_filter(class name) is
            non-zero (no filter installed: every record is skipped);
          * the property offsets become pointers (only the first time a blob is loaded:
            header bit 2 is set on entry);
          * obj = factory(class name, position, angle, props); when it made one, its
            +0x34 is set to the class name;
          * when the header has bit 1 and an object was made, load_state(obj, state bytes)
            - virtual slot 8.
        Afterwards the delete list is flushed, so an object a constructor deleted is gone
        before anything runs."""
        blob.relocated = True
        for record in blob.records:
            if filter_only and (save_filter is None or not save_filter(record.class_name)):
                continue
            obj = factory(record.class_name, list(record.pos), record.angle, record.props)
            if obj is not None:
                obj.class_name = record.class_name
            if blob.has_state and obj is not None and load_state is not None:
                load_state(obj, record.state)
        self.flush_delete_list()
        return blob.size


def _mod(value, divisor):
    """frame % divisor as an index.  The code divides signed, so a negative frame number
    would index in front of the array; the model refuses."""
    value = s32(value)
    if value < 0:
        raise ObjectError('negative frame number: the original would index before its lists')
    return value % divisor


def create_object(class_name, pos, angle, props, factory):
    """world_createObject 0x14f6c8 (className, pos, angle, props): the installed factory is
    called with a copy of the position, the angle as a signed 16-bit number and the
    property list untouched (the fourth argument is simply left in its register); an
    object that comes back gets its +0x34 set to the class name.  No factory: nothing."""
    if factory is None:
        return None
    obj = factory(class_name, list(pos), s16(angle), props)
    if obj is not None:
        obj.class_name = class_name
    return obj


class Record:
    """One level-object record: class name, facing, position, properties, saved state."""

    def __init__(self, class_name, angle, pos, props, state=b''):
        self.class_name = class_name
        self.angle = s16(angle)
        self.pos = list(pos)
        self.props = props
        self.state = state


class RecordBlob:
    """The object list of a level file, or a saved level state:

        +0 s16 count, +2 u16 flags (1 = records carry state, 2 = offsets already made
        pointers), +4 s32 offset of the string table, then the records:
        +0 s32 class name (string-table offset, negative = none), +4 s16 record size,
        +6 s16 facing, +8 float x, y, height, +0x14 s32 property offsets ..., 0,
        then (aligned to 8) the state bytes when flag 1 is set."""

    def __init__(self, records, has_state=False):
        self.records = records
        self.has_state = has_state
        self.relocated = False
        self.size = 0

    def build(self):
        """-> bytes in the file layout above (for tests; a real blob comes from a level).
        The blob must be loaded at an address that is a multiple of 8 when it carries
        state, because the code aligns the ADDRESS of the state bytes."""
        strings = bytearray(b'\0')              # offset 0 is never a property (0 ends the list)
        offsets = {}

        def intern(text):
            text = bytes(text)
            if text not in offsets:
                offsets[text] = len(strings)
                strings.extend(text + b'\0')
            return offsets[text]

        body = bytearray()
        for record in self.records:
            name = -1 if record.class_name is None else intern(record.class_name)
            rec = bytearray(struct.pack('<ihh3I', name, 0, record.angle, *[p & M32 for p in record.pos]))
            for text in record.props or []:
                rec += struct.pack('<i', len(strings))  # one copy per record: names are edited in place
                strings.extend(bytes(text) + b'\0')
            rec += struct.pack('<i', 0)
            if self.has_state:
                while len(rec) % 8:
                    rec += b'\0'
                rec += bytes(record.state)
            while len(rec) % 8:
                rec += b'\0'
            struct.pack_into('<h', rec, 4, len(rec))
            body += rec
        self.size = 8 + len(body)
        header = struct.pack('<hHi', len(self.records), 1 if self.has_state else 0, self.size)
        return header + bytes(body) + bytes(strings)
