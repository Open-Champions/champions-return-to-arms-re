"""Run-tick decisions of the ten creature classes that own their state switch.

Each ``step`` is one call of the class run function: the slot-27 requests it
makes and the decision calls that follow the shared prologue. Clip choice
stays in ``ref_creature_dispatch``; a request here is what causes that
setState to run. Compared with the original by ``difftest_own_machines.py``.

Executed on synthetic objects with stubbed callees (tools/ee_emu.py). Not a
running game. A branch that these vectors do not take is not claimed.
"""

# Same object base as tools/scan_anim_dispatch.py. Kept here so the synthetic
# tests do not import the scanner.
OBJ = 0x1000000
DUMMY = 0x1080000

# Calls the prologue makes on every tick. strcmp / strcasecmp are the level
# and lump tests that sit above the switch. The software-float band is pure
# arithmetic and is dropped by decision().
PROLOGUE = {
    'damage', 'crun', 'active', 'step', 'knock', 'v16', 'v23',
    'h15', 'h21', 'h22', 'strcasecmp', 'strcmp', 'grid',
}


def s32(n):
    n &= 0xffffffff
    return n - 0x100000000 if n & 0x80000000 else n


def decision(calls):
    """Drop the prologue and the software-float helpers from an executor trace."""
    out = []
    for label, _arg, _ret in calls:
        if label in PROLOGUE:
            continue
        if len(label) == 6 and all(c in '0123456789abcdef' for c in label):
            n = int(label, 16)
            if 0x380000 <= n < 0x3c0000:
                continue
        out.append(label)
    return out


def materialize(ctx):
    """Turn semantic keys into the memory pokes ``own_exec.Exec.tick`` reads."""
    ctx = dict(ctx or {})
    pokes = list(ctx.get('pokes') or [])

    def add(off, size, val):
        pokes.append((OBJ + off, size, val & ((1 << (8 * size)) - 1)))

    if ctx.get('idle'):
        add(0x41c, 4, DUMMY)
    if ctx.get('move'):
        add(0x428, 4, DUMMY)
    if ctx.get('fidget_a'):
        add(0x420, 4, DUMMY)
    if ctx.get('fidget_b'):
        add(0x424, 4, DUMMY)
    if ctx.get('flee_clip'):
        add(0x430, 4, DUMMY)
    if 'class_flags' in ctx:
        add(0x43c, 4, ctx['class_flags'])
    if 'fid_time' in ctx:
        add(0x410, 4, ctx['fid_time'])
    if 'flight' in ctx:
        add(0x3d4, 4, ctx['flight'])
    if 'stuck' in ctx:
        add(0x2c4, 4, ctx['stuck'])
    if 'kind' in ctx:
        add(0x3d0, 4, ctx['kind'])
    if 'z' in ctx:
        add(0x18, 4, ctx['z'])
    if ctx.get('snap'):
        add(0x3d9, 1, 1)
    if 'root_y' in ctx:
        add(0xbc, 4, ctx['root_y'])
    if 'root_x' in ctx:
        add(0xc0, 4, ctx['root_x'])
    if 'speed' in ctx:
        add(0xb8, 4, ctx['speed'])
    ctx['pokes'] = pokes
    return ctx


class _Tick(object):
    def __init__(self, ctx):
        ctx = ctx or {}
        self.clock = ctx.get('clock', 1000) & 0xffffffff
        self.timer = ctx.get('timer', 0) & 0xffffffff
        self.flight = ctx.get('flight', 0) & 0xffffffff
        self.queue = ctx.get('queue', 1) & 0xff
        self.anim = ctx.get('anim', 0)
        self.events = ctx.get('events', 0)
        self.rand_n = ctx.get('rand', 0)
        self.seen = 1 if ctx.get('seen') else 0
        self.away = 1 if ctx.get('away') else 0
        self.see_v = 1 if ctx.get('see') else 0
        self.enemy = 1 if ctx.get('enemy') else 0
        self.ally = 1 if ctx.get('ally') else 0
        self.rooted = bool(ctx.get('rooted'))
        self.ready = bool(ctx.get('ready'))
        self.stunned = bool(ctx.get('stunned'))
        self.arrived = bool(ctx.get('arrived'))
        self.demon = 1 if ctx.get('demon') else 0
        self.path = 1 if ctx.get('path') else 0
        self.frame = ctx.get('frame', 0)
        self.serial = ctx.get('serial', 0)
        self.cflags = ctx.get('cflags', 0)
        self.kind = ctx.get('kind', 0)
        self.class_flags = ctx.get('class_flags', 0)
        self.target = bool(ctx.get('target'))
        self.owner = bool(ctx.get('owner'))
        self.idle = bool(ctx.get('idle'))
        self.move = bool(ctx.get('move'))
        self.fa = bool(ctx.get('fidget_a'))
        self.fb = bool(ctx.get('fidget_b'))
        self.flee = bool(ctx.get('flee_clip'))
        self.fid = ctx.get('fid_time', 0) & 0xffffffff
        self.z = ctx.get('z', 0) & 0xffffffff
        self.stuck = ctx.get('stuck', 0)
        self.snap = bool(ctx.get('snap'))
        self.seq = {k: list(v) for k, v in (ctx.get('seq') or {}).items()}
        self.calls = []
        self.req = []
        self.timer_out = self.timer
        self.flight_out = self.flight

    def expired(self):
        return s32(self.clock) > s32(self.timer)

    def call(self, name):
        self.calls.append(name)

    def take(self, name, default):
        seq = self.seq.get(name)
        if seq:
            return seq.pop(0)
        return default

    def v25(self):
        v = self.take('v25', self.seen)
        self.call('v25')
        return v

    def v27(self, n):
        self.call('v27')
        self.req.append(n)

    def see(self):
        v = self.take('see', self.see_v)
        self.call('see')
        return v

    def rand(self):
        v = self.take('rand', self.rand_n)
        self.call('rand')
        return v & 0xffffffff

    def flag(self, bit):
        return bool(self.anim & bit)


def _sight_or_queue(c):
    """Slot 25, and again when the first result does not take the queue branch.

    Both AntQueen state 0 (0x237044, 0x237080) and a bow Skeleton's idle
    (kind +0x3d0 == 4) call slot 25 a second time unless the first returned
    true while the animation queue was below 4. Either true result with
    queue < 4 requests state 3.
    """
    if c.v25() and c.queue < 4:
        c.v27(3)
        return True
    if c.v25() and c.queue < 4:
        c.v27(3)
        return True
    return False


def _gnaw(state, c):
    # Gnaw_run 0x267654. Agrees with ref_monsters_1.gnaw_run on these branches.
    if state == 0:
        if c.v25():
            c.v27(3)
        else:
            c.call('away')
            if c.away:
                c.v27(1)
    elif state == 1:
        if c.v25():
            c.v27(3)
        else:
            c.call('move_dest')
    elif state == 3:
        if not c.target:
            c.v27(0)
        elif c.see():
            c.v27(5)
        elif c.see():
            c.call('turn')
        else:
            c.call('move_target')
    elif state == 5:
        if c.see():
            c.v27(6)
        elif c.see():
            c.call('turn')
        else:
            c.call('unroot')
            if not c.rooted:
                c.v27(3)
    elif state == 6:
        c.call('turn')
        if c.events & 1:
            c.call('hit_arc')
        if not c.flag(8):
            c.v27(5)
    elif state == 0x10:
        c.call('ready')
        if c.ready:
            c.v27(0)
        else:
            c.call('flee')
    elif state == 0x12:
        if not c.flag(0x10):
            c.v27(5)
    elif state == 0x13:
        c.call('unstun')
        if not c.stunned:
            c.v27(3)
    elif state == 0x14:
        c.call('dead')
        c.call('delete')
    else:
        c.v27(0)


def _skelight(state, c):
    # Skelight_run 0x2a8b84. Holder slots 15 and 22 are prologue.
    if state == 0:
        if c.v25():
            c.v27(3)
        else:
            c.call('away')
            if c.away:
                c.v27(1)
    elif state == 1:
        if c.v25():
            c.v27(3)
        else:
            c.call('move_dest')
    elif state == 3:
        if not c.target:
            c.v27(0)
        elif c.see():
            c.v27(6)
        elif c.see():
            c.call('turn')
        else:
            c.call('move_target')
    elif state == 5:
        if c.see():
            c.v27(6)
        else:
            c.call('unroot')
            if not c.rooted:
                c.v27(3)
    elif state == 6:
        count = True
        if c.target:
            if c.events & 1:
                c.call('h17')
                c.call('hit_arc')
            if c.flag(8):
                c.call('turn')
                count = False
        else:
            count = not c.flag(8)
        if count:
            c.timer_out = (c.timer - 1) & 0xffffffff
        if s32(c.timer_out) <= 0:
            c.v27(3)
    elif state == 0x10:
        c.call('ready')
        if c.ready:
            c.v27(0)
        else:
            c.call('flee')
    elif state == 0x12:
        c.v27(3)
    elif state == 0x13:
        c.call('unstun')
        if not c.stunned:
            c.v27(0)
    elif state == 0x14:
        c.call('dead')
    elif state == 0x17:
        if c.flag(0x80):
            c.v27(0)
        c.call('fx')


def _gnome(state, c):
    # GnomeNavigator_run 0x26a1e0. Follow bits are cflags 0x400000 and 0x800000.
    if state == 0:
        if c.cflags & 0xc00000:
            if c.expired():
                c.v27(1)
            else:
                c.call('away')
                if c.away:
                    c.v27(1)
    elif state == 1:
        c.call('move_to')
        if c.arrived or c.expired():
            c.v27(0)
    elif state == 3:
        if not c.target:
            c.v27(0)
    elif state == 5:
        c.call('unroot')
        if not c.rooted:
            c.v27(3)
    elif state == 0x13:
        c.call('unstun')
        if not c.stunned:
            c.v27(0)
    elif state == 0x14:
        c.call('dead')


def _mermaid(state, c):
    # Mermaid_run 0x285c58. Every probed state starts with a zero move_by.
    c.call('move_by')
    if state == 0:
        if c.expired():
            c.v27(1)
    elif state == 1:
        if c.expired():
            c.v27(0)
        else:
            c.call('move_dest')
    elif state == 3:
        if not c.target:
            c.v27(0)
    elif state == 5:
        c.call('unroot')
        if not c.rooted:
            c.v27(3)
    elif state == 0x12:
        if not c.flag(0x10):
            c.v27(0)
    elif state == 0x14:
        if c.flag(0x80):
            c.call('stop')


def _npc(state, c):
    # NPC_run 0x29ea40. The lump-name strcmp is prologue. A matching name
    # enters a particle rejection loop; that path is not stepped here.
    if state == 0 and (c.cflags & 0x8000000):
        c.v27(1)
    elif state == 1:
        c.call('move_dest')


def _natasla(state, c):
    # Natasla_run 0x29dbf0. No switch and no slot 27. ``state`` is unused.
    del state, c


def _aq_attack(c, leave):
    """Shared bite/sting tail. ``leave`` is the state requested when flag 8 clears."""
    c.call('aq_ground')
    if (c.events & 1) and c.target:
        c.call('000000')
        c.call('hit_reach')
    if c.target:
        c.call('turn')
    if not c.flag(8):
        c.v27(leave)


def _antqueen(state, c):
    # AntQueen_run 0x236f78. Bank helpers stay stubbed, so each is one call.
    if state == 0:
        c.call('aq_ground')
        if not _sight_or_queue(c) and c.expired():
            c.v27(1)
    elif state == 1:
        c.call('aq_air')
        if c.v25():
            c.v27(3)
        else:
            c.call('move_dest')
    elif state == 3:
        c.call('aq_air')
        if not c.target:
            c.v27(0)
            return
        if (c.rand() & 3) == 0:
            c.call('enemy')
            if c.enemy:
                c.v27(7)
                return
        elif c.see():
            c.v27(6)
            return
        c.call('move_target')
        if s32(c.clock) > s32(c.flight) and c.queue < 4:
            c.v27(8)
    elif state == 5:
        drawn = c.rand()
        if c.target:
            if (drawn & 3) == 0:
                c.call('enemy')
                if c.enemy:
                    c.v27(7)
                    return
            elif c.see():
                c.v27(6)
                return
        c.call('unroot')
        if not c.rooted:
            c.v27(3)
    elif state == 6:
        c.call('aq_ground')
        if (c.events & 1) and c.target:
            c.call('hit_reach')
        elif c.target:
            c.call('turn')
        if not c.flag(8):
            c.v27(3)
    elif state == 7:
        c.call('aq_ground')
        if c.events & 1:
            c.call('000000')
            c.call('hit_or')
        if not c.flag(8):
            c.v27(3)
    elif state == 8:
        c.call('aq_air')
        if not c.target:
            c.v27(0)
            return
        if s32(c.clock) > s32(c.flight):
            c.v27(0x17)
            return
        if c.flag(8):
            return
        if c.see():
            c.v27(9)
            if c.rand() % 3 == 0:
                c.flight_out = 0
            return
        if c.see():
            c.call('turn')
        else:
            c.call('move_target')
    elif state in (9, 10):
        _aq_attack(c, 8 if state == 9 else 0x17)
    elif state == 0x12:
        c.call('aq_ground')
        if not c.flag(0x10) and c.queue < 4:
            c.v27(3)
    elif state == 0x13:
        c.call('unstun')
        if not c.stunned:
            c.v27(0)
    elif state == 0x14:
        c.call('aq_ground')
        c.call('dead')
    elif state == 0x17:
        c.call('aq_air')
        if not c.target:
            c.v27(0)
            return
        if c.flag(8):
            return
        if s32(c.clock) <= s32(c.flight):
            c.call('move_to')
            if c.arrived or c.stuck >= 31:
                c.flight_out = 0
            return
        c.call('turn')
        if c.see():
            c.v27(0x18)
    elif state == 0x18:
        c.call('aq_ground')
        if not c.flag(8) and c.queue < 4:
            c.v27(3)
    elif state == 0x19:
        c.call('aq_ground')
        if c.target and c.clock == (c.timer - 120) & 0xffffffff:
            c.call('cos16')
            c.call('sin16')
            c.call('pool')
        if c.expired() and c.queue < 4:
            c.v27(3)


def _skeleton_sight(c):
    """Melee: one slot 25. Bow (kind 4): a second slot 25 unless the first hit."""
    if c.v25():
        c.v27(3)
        return True
    if c.kind == 4 and c.v25():
        c.v27(3)
        return True
    return False


def _skeleton(state, c):
    # Skeleton_run 0x2a6864. Holder slot 21 is prologue.
    if state == 0:
        if not _skeleton_sight(c):
            if c.expired():
                c.v27(1)
            else:
                c.call('away')
                if c.away:
                    c.v27(1)
    elif state == 1:
        if not _skeleton_sight(c):
            if c.expired():
                c.v27(0)
            else:
                c.call('move_dest')
    elif state == 3:
        if not c.target:
            c.v27(0)
            return
        if c.kind == 4:
            if c.see():
                c.v27(8)
            elif c.see():
                c.call('turn')
            else:
                c.call('move_target')
            return
        if c.see():
            c.v27(6)
            return
        c.call('ally')
        if c.ally:
            c.rand()
            c.v27(5)
            return
        if c.see():
            c.call('turn')
        else:
            c.call('move_target')
    elif state == 5:
        if c.kind == 4:
            if c.see():
                c.v27(8)
                return
        elif c.see():
            c.v27(6)
            return
        c.call('unroot')
        if c.rooted:
            return
        if c.expired():
            c.v27(3)
            return
        if not c.target:
            return
        c.call('ally')
        if not c.ally:
            c.v27(3)
    elif state == 6:
        # Event bit 0 hits, then flag 8 turns. Flag 8 also holds +0xf4.
        if c.target and (c.events & 1):
            c.call('h17')
            c.call('hit_reach')
        if c.target and c.flag(8):
            c.call('turn')
        if not c.flag(8):
            c.timer_out = (c.timer - 1) & 0xffffffff
        if s32(c.timer_out) <= 0:
            c.v27(3)
    elif state == 8:
        if not c.target:
            c.v27(0)
        else:
            c.call('cos16')
            c.call('sin16')
            c.call('lead')
            if c.flag(8):
                c.call('v26')
        if not c.flag(8):
            c.timer_out = (c.timer - 1) & 0xffffffff
            if s32(c.timer_out) <= 0:
                c.v27(3)
    elif state == 0x10:
        c.call('ready')
        if c.ready:
            c.v27(0)
        else:
            c.call('flee')
    elif state == 0x11:
        if c.expired():
            c.v27(3)
    elif state == 0x12:
        if not c.flag(0x10):
            c.v27(3)
    elif state == 0x13:
        c.call('unstun')
        if not c.stunned:
            c.v27(0)
    elif state == 0x14:
        c.call('dead')
    elif state == 0x17:
        c.call('fx')
        if not c.flag(0x10):
            c.v27(0)


def _fidget(c):
    """Critter fidget. Blend-in-out of clip A, or of A/B when rand & 1 == 0 picks B.

    The draw that picks B happens only when clip B exists. A second draw
    reschedules +0x410. Returns True when a fidget started (the wander test
    is then skipped).
    """
    if not (c.fa and s32(c.clock) > s32(c.fid)):
        return False
    if c.fb:
        c.rand()
    c.call('anim_bio')
    c.rand()
    return True


def _critter(state, c):
    # Critter_run 0x255008. No damage and no target pick. Class flag 0x10
    # skips the locomotion call.
    if state == 0x16:
        c.call('path')
        if c.path and not c.snap:
            c.call('approach')
        return
    if state == 0:
        if not (c.class_flags & 0x10):
            c.call('move_by')
        if _fidget(c):
            return
        if c.flag(8) or not c.move:
            return
        if c.expired():
            c.v27(1)
        else:
            c.call('away')
            if c.away:
                c.v27(1)
    elif state == 1:
        if not (c.class_flags & 0x10):
            c.call('move_direct' if (c.class_flags & 2) else 'move_to')
        if c.arrived or c.expired():
            # Class flag 8 re-picks a point on an early arrival.
            if c.idle and not ((c.class_flags & 8) and not c.expired()):
                c.v27(0)
            else:
                c.call('clear_path')
                c.call('wander')
                c.rand()
    elif state == 0x10:
        if not c.target:
            c.v27(0 if c.idle else 1)
            return
        if c.flee:
            c.call('flee_from')
        if c.expired():
            c.call('handle_clear')
            c.v27(0 if c.idle else 1)
    elif state == 0x14:
        c.call('stop')
        c.call('v28')
    elif state == 0x17:
        _fidget(c)


def _soul_phase(c):
    return ((c.frame ^ c.serial) & 15) == 0


def _soul(state, c):
    # Soul_run 0x2a9870. Owned souls and the thrown state skip the idle move.
    if not c.owner and state != 0x1b:
        c.call('move_by')
    if state == 0:
        if _soul_phase(c):
            c.call('demon')
            if c.demon:
                c.v27(0x18)
                return
        if c.expired():
            c.v27(1)
        else:
            c.call('away')
            if c.away:
                c.v27(1)
    elif state == 1:
        if _soul_phase(c):
            c.call('demon')
            if c.demon:
                c.v27(0x18)
                return
        c.call('move_to')
        if c.arrived or c.expired():
            c.v27(0)
    elif state == 0x18:
        if _soul_phase(c):
            c.call('demon')
            if not c.demon:
                c.v27(0)
    elif state == 3:
        if not c.target:
            c.v27(0)
    elif state == 5:
        c.call('unroot')
        if not c.rooted:
            c.v27(0)
    elif state in (0x12, 0x19):
        if not c.flag(0x10):
            c.v27(0x18)
    elif state == 0x17:
        if c.expired():
            c.v27(1)
    elif state == 0x14:
        c.call('samples')
        if c.expired() or c.flag(0x80):
            c.call('delete')
    elif state == 0x22:
        c.call('samples')
        if c.expired() or c.flag(0x80):
            c.call('stop')
    elif state == 0x1b:
        c.call('samples')
        c.call('mat_place')
        c.call('mat_rot')
        c.call('cos16')
        c.call('sin16')
        if c.expired():
            c.call('delete')
        else:
            c.call('terrain')
            # No victim: z velocity -80, four sub-steps. From z 0 that lands
            # below a terrain stub of 0. From 100.0 it does not. Other
            # heights are not in the vectors.
            if c.z == 0:
                c.call('delete')


_MACHINES = {
    'Gnaw': _gnaw,
    'Skelight': _skelight,
    'GnomeNavigator': _gnome,
    'Mermaid': _mermaid,
    'Natasla': _natasla,
    'NPC': _npc,
    'AntQueen': _antqueen,
    'Skeleton': _skeleton,
    'Critter': _critter,
    'Soul': _soul,
}


def step(name, state, ctx=None):
    """One run tick. Returns (requests, calls, words).

    ``requests`` are slot-27 arguments in order. ``calls`` are the decision
    helpers in order. ``words`` are final values of fields the tick stores,
    keyed by object offset; empty when this vector does not check them.
    """
    if name not in _MACHINES:
        raise KeyError(name)
    c = _Tick(ctx)
    _MACHINES[name](state, c)
    words = {}
    if name in ('Skelight', 'Skeleton') and state in (6, 8):
        words[0xf4] = c.timer_out
    if name == 'AntQueen' and state in (8, 0x17):
        words[0x3d4] = c.flight_out
    return (c.req, c.calls, words)


def root_clears_speed(word):
    """NPC state 1: |root component| > 0.5 (strict) zeros speed for the move.

    ``word`` is the raw 32-bit pattern of +0xbc or +0xc0. Executed: 0.5 does
    not, one ulp above 0.5 does, and the same magnitude below -0.5 does.
    """
    import struct
    value = struct.unpack('>f', struct.pack('>I', word & 0xffffffff))[0]
    return abs(value) > 0.5
