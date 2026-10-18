#!/usr/bin/env python3
"""Execute every creature class's animation dispatch one function at a time.

  python3 tools/scan_anim_dispatch.py local/SLUS_209.73 [out.json] [Class ...]
  python3 tools/scan_anim_dispatch.py --emit local/SLUS_209.73 scan.json [...] > data.py
  python3 tools/scan_anim_dispatch.py --markdown scan.json [...]   # doc appendix

Reads the user's own US v2.00 executable (hash checked) and writes a JSON report;
keep that report under local/ (it is derived from the executable, never tracked).
Three single-function scans run in tools/ee_emu.py with every callee auto-stubbed
and recorded (see docs/spec/creature-animation-dispatch.md section 2):

* setState (vtable slot 27): for each requested state, the animation calls made
  (function, class-definition entry index, blend raw32, flags), the virtual slots
  called and the stored state. The common filter 0x10a9c0 is stubbed to pass the
  request through unchanged; GameObject_rand 0x1509d0 is swept over 0..11; every
  object/global word the case reads is varied one at a time to expose the
  conditions that pick between alternative clips.
* constructor: creature_setDefEntryParams 0x118378 calls (entry index, four raw32
  times and four masks), the initial animation calls and the class definition
  handed to Creature_ctor 0x109d68 (its resource names are read from the file).
* run (vtable slot 4; separate --runs mode): for each case label, Creature_stepAnim
  0x1162b0 returns one event mask at a time; calls and creature stores that appear
  only with that mask are the consumers of the event. Track-flag union 0/0xffff
  exposes transitions taken when the marker/status bits clear or set.

All results are Executed facts about single functions on stub state; they are not
runs of the game. A stubbed callee returns 0 or a pointer to a zeroed dummy object.
"""
import hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError
import symtab

EXPECTED = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ANIM = {0x16cfe0: 'anim_start', 0x16ceb0: 'anim_startBlendInOut', 0x170838: 'anim_push',
        0x1708c0: 'anim_pushWithWeights', 0x170938: 'anim_pushChained', 0x16d1a0: 'anim_stop',
        0x170bc8: 'anim_jumpTopToEnd', 0x170c80: 'anim_snapTopToEnd',
        0x1709f8: 'anim_syncToSimFrame', 0x16d0b8: 'anim_randomizeTopTime',
        0x1707b0: 'anim_clear', 0x16cb50: 'anim_dropNonPersistent'}
CLIP_ARG = {'anim_start', 'anim_startBlendInOut', 'anim_push', 'anim_pushWithWeights',
            'anim_pushChained', 'anim_stop'}
RAND, FILTER, CTOR_C, CTOR_G = 0x1509d0, 0x10a9c0, 0x109d68, 0x14cb10
EVENTS, STEP, ACTIVE, CRUN = 0x118378, 0x1162b0, 0x10c0f0, 0x112948
OBJ, DUMMY, DEF, CLIP, VT, HOLDER = (0x1000000, 0x1080000, 0x1100000, 0x1200000,
                                     0x1300000, 0x1340000)
FAKE = 0x00f00000            # fake virtual targets: FAKE + 8*slot, never executed
FAKE_HOLDER = 0x00f10000     # the weapon holder's table (holder at creature +0x50)
FAKE_OTHER = 0x00f20000      # any other object's table (stub results, the target)
VT_HOLDER, VT_OTHER = VT + 0x1000, VT + 0x2000
MASKS = (1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80)
VARY = (1, 2, 3, 4, 0x40000, 0x80000, 0x100000, 0x200000, 0x380000,
        0x3f800000, 0x42c80000, 0xbf800000, 0xffffffff)
# fields not probed: class definition, vtable, holder pointer, flags, state
COMMON = {0x24, 0x48, 0x50, 0x51, 0x52, 0x53, 0xa8, 0xac, 0x232}
HOLDER_PTR = 0x50


def catalogue(root):
    """Class rows of docs/monsters.md 3.1: name, vtable, constructors, run cases."""
    rows = []
    path = os.path.join(root, 'docs', 'monsters.md')
    seen = False
    for line in open(path, encoding='utf-8'):
        if line.startswith('### 3.1'):
            seen = True
        elif seen and line.startswith('### '):
            break
        elif seen and line.startswith('| ') and '0x5' in line:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            ctor = re.findall(r'0x[0-9a-f]+', cells[4])
            states = [int(x, 16) for x in cells[9].split()]
            rows.append((cells[0], int(cells[2], 16), [int(c, 16) for c in ctor], states))
    return rows


class Scanner:
    def __init__(self, path):
        with open(path, 'rb') as f:
            if hashlib.sha256(f.read()).hexdigest() != EXPECTED:
                raise ValueError('wrong executable revision')
        self.ee = ee = EE(path)
        ee.div_zero = 'r5900'
        ee.mem.map(OBJ, 0x400000)
        ee.mem.map(0, 0x1000)       # null-pointer reads of stub results read zeros
        self.names = symtab.load(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.rand = 0
        self.mask = 0
        self.base_nulls = 0
        ee.stub(RAND, function=lambda e: self.rand)
        ee.stub(FILTER, ret=0)

    def word(self, addr):
        return self.ee.mem.load(addr, 4)

    def slot(self, vtable, n):
        return self.word(vtable + 8 * n + 4)

    def reset(self, state=0, animflags=0):
        m = self.ee.mem
        m.write(OBJ, bytes(0x2000))
        m.write(DUMMY, bytes(0x2000))
        for base, table in ((OBJ, VT), (DUMMY, VT_OTHER)):
            m.store(base + 0x24, 4, DEF)
            m.store(base + 0x48, 4, table)
            m.store(base + 0x50, 4, HOLDER)
            m.store(base + 0x232, 2, state)
            m.store(base + 0x11a, 2, animflags)
        m.store(OBJ + 0xa8, 8, 1 << 63)
        m.store(HOLDER, 4, VT_HOLDER)
        m.store(DUMMY, 4, VT_OTHER)
        for i in range(64):
            m.store(DEF + 8 * i + 4, 4, CLIP + 0x100 * i)
        for s in range(64):
            m.store(VT + 8 * s + 4, 4, FAKE + 8 * s)
            m.store(VT_HOLDER + 8 * s + 4, 4, FAKE_HOLDER + 8 * s)
            m.store(VT_OTHER + 8 * s + 4, 4, FAKE_OTHER + 8 * s)

    def clip_index(self, value):
        value &= 0xffffffff
        if CLIP <= value < CLIP + 0x4000 and value % 0x100 == 0:
            return (value - CLIP) // 0x100
        return 'ptr' if value else None

    def describe(self, calls, own=()):
        out = []
        for c in calls:
            t = c.target
            if t in own:
                continue
            if t in ANIM:
                kind = ANIM[t]
                rec = {'fn': kind}
                if kind in CLIP_ARG:
                    rec['entry'] = self.clip_index(c.args[1])
                if kind in ('anim_start', 'anim_startBlendInOut', 'anim_stop'):
                    rec['blend'] = '%08x' % c.fargs[0]
                if kind == 'anim_startBlendInOut':
                    rec['blend_out'] = '%08x' % c.fargs[1]
                if kind == 'anim_pushWithWeights':
                    rec['weights'] = ['%08x' % v for v in c.fargs[1:5]]
                if kind in CLIP_ARG and kind != 'anim_stop':
                    rec['flags'] = '%x' % (c.args[2] & 0xffffffff)
                if True:
                    rec['state_arg'] = '%x' % ((c.args[0] & 0xffffffff) - OBJ) \
                        if OBJ <= (c.args[0] & 0xffffffff) < OBJ + 0x2000 else 'other'
                out.append(rec)
            elif FAKE_HOLDER <= t < FAKE_HOLDER + 0x200:
                out.append({'holder': (t - FAKE_HOLDER) // 8})
            elif FAKE_OTHER <= t < FAKE_OTHER + 0x200:
                out.append({'other_vslot': (t - FAKE_OTHER) // 8})
            elif FAKE <= t < FAKE + 0x200:
                rec = {'vslot': (t - FAKE) // 8}
                if rec['vslot'] == 27:
                    rec['arg'] = c.args[1] & 0xffffffff
                out.append(rec)
            else:
                out.append({'call': '%06x' % t, 'name': self.names.get(t, ''),
                            'args': ['%x' % (a & 0xffffffff) for a in c.args[1:4]]})
        return out

    def execute(self, fn, args, follow, max_steps=200000):
        ee = self.ee
        ee.follow = set(follow)
        ee.calls = []
        ee.writes = []
        ee.reads = []
        try:
            ee.call(fn, *args, sp=EE.STACK_HI - 0x400, max_steps=max_steps)
            status = 'ok'
        except EmuError as exc:
            status = 'error: %s' % str(exc)[:120]
        reads, ee.reads = ee.reads, None
        return status, list(ee.calls), reads

    # ---- setState --------------------------------------------------------------------
    def one_state(self, fn, state, rand=0, poke=None, default=0):
        self.reset()
        self.rand = rand
        self.ee.default_ret = default
        if poke:
            addr, size, value = poke
            old = self.ee.mem.load(addr, size)
            self.ee.mem.store(addr, size, value & ((1 << 8 * size) - 1))
        status, calls, reads = self.execute(fn, (OBJ, state), {fn})
        if poke and not OBJ <= poke[0] < OBJ + 0x400000:
            self.ee.mem.store(poke[0], poke[1], old)
        stored = self.ee.mem.load(OBJ + 0x232, 2)
        nulls = sum(1 for _, a, _, _ in reads if a < 0x1000)
        if poke and status == 'ok' and nulls > self.base_nulls:
            status = 'null-read: a probe used as a pointer'
        if not poke and rand == 0 and default == 0:
            self.base_nulls = nulls
        described = [{k: v for k, v in d.items() if k != 'args'}
                     for d in self.describe(calls, own={FILTER})]
        key = json.dumps([described, stored, status[:40]])
        return key, reads

    def set_state(self, fn, states=range(0x30)):
        result = {}
        for st in states:
            outcomes = {}

            def note(key, why):
                outcomes.setdefault(key, why)
            base, reads = self.one_state(fn, st)
            note(base, 'baseline')
            for r in range(1, 12):
                note(self.one_state(fn, st, rand=r)[0], 'rand=%d' % r)
            for d in (1, DUMMY):
                note(self.one_state(fn, st, default=d)[0], 'callees return %#x' % d)
            fields = sorted({(a, s) for pc, a, s, v in reads
                             if (OBJ <= a < OBJ + 0x2000 and a - OBJ not in COMMON)
                             or 0x564180 <= a < 0x940000})
            for addr, size in fields:
                for v in VARY:
                    if size < 4 and v > (1 << 8 * size) - 1:
                        continue
                    k = self.one_state(fn, st, poke=(addr, size, v))[0]
                    where = '+%x' % (addr - OBJ) if addr >= OBJ else '%x' % addr
                    note(k, '%s=%#x' % (where, v))
            decoded = []
            for key, why in outcomes.items():
                calls, stored, status = json.loads(key)
                decoded.append({'when': why, 'calls': calls, 'stored': stored,
                                'status': status})
            result['%x' % st] = {
                'outcomes': decoded,
                'reads': ['+%x' % (a - OBJ) if a >= OBJ else '%x' % a for a, s in fields]}
        return result

    # ---- constructor -----------------------------------------------------------------
    def ctor(self, fn, variant=0, set_fn=None):
        self.reset()
        self.ee.mem.store(OBJ + 0x24, 4, 0)
        handed = []
        creature = [True]

        def base(e):
            handed.append(e.r[8] & 0xffffffff if creature[0] else None)
            e.mem.store(OBJ + 0x24, 4, DEF)
        def gbase(e):
            creature[0] = False
            base(e)
            creature[0] = True
        self.ee.stub(CTOR_C, function=base)
        self.ee.stub(CTOR_G, function=gbase)
        self.ee.default_ret = DUMMY
        # (this, type name, position, facing, properties, variant...): the variant is
        # offered in every later register; the type name is the empty string
        args = (OBJ, DUMMY, DUMMY, 0, DUMMY, variant, variant, variant)
        status, calls, _ = self.execute(fn, args, {fn})
        del self.ee.hooks[CTOR_C], self.ee.hooks[CTOR_G]
        events, anims = [], []
        for c in calls:
            if c.target == EVENTS:
                events.append({'entry': c.args[1] & 0xffffffff,
                               'times': ['%08x' % v for v in c.fargs[0:4]],
                               'masks': ['%x' % (v & 0xff) for v in c.args[2:6]]})
        anims = []
        for c, d in zip(calls, self.describe(calls)):
            if 'fn' in d:
                anims.append(d)
            elif set_fn is not None and c.target == set_fn:
                anims.append({'set_state': c.args[1] & 0xffffffff})
        return {'status': status, 'events': events, 'anims': anims,
                'creature_ctor_def': ['%x' % h for h in handed if h]}

    def def_names(self, definition, count=48):
        names = []
        for i in range(count):
            if not 0x3e9c00 <= definition + 8 * i < 0x564000:
                break
            p = self.word(definition + 8 * i)
            if not 0x100000 <= p < 0x900000:
                break
            try:
                names.append(self.ee.mem.cstr(p, 64))
            except Exception:
                break
        return names

    # ---- run -------------------------------------------------------------------------
    def one_run(self, fn, state, mask, default, animflags):
        """One run-function tick: (calls after the step as (name, args), stores to the
        creature after the step, status)."""
        self.reset(state, animflags)
        self.mask = mask
        self.rand = 0
        self.ee.default_ret = default
        self.ee.stub(STEP, function=lambda e: self.mask)
        self.ee.stub(ACTIVE, ret=1)
        self.ee.stub(CRUN, ret=0)
        status, calls, _ = self.execute(fn, (OBJ, DUMMY), {fn}, max_steps=30000)
        writes = list(self.ee.writes)
        for a in (STEP, ACTIVE, CRUN):
            del self.ee.hooks[a]
        cut = [i for i, c in enumerate(calls) if c.target == STEP]
        if not cut:
            return [], [], status, False
        after = calls[cut[0] + 1:]
        names = []
        for c in after:
            d = self.describe([c], own={STEP, ACTIVE, CRUN})
            if not d:
                continue
            d = d[0]
            label = d.get('name') or ('slot%d' % d['vslot'] if 'vslot' in d else
                                      'holder.slot%d' % d['holder'] if 'holder' in d else
                                      'other.slot%d' % d['other_vslot']
                                      if 'other_vslot' in d else d.get('fn') or d.get('call'))
            if d.get('vslot') == 27:
                label = 'setState(%#x)' % d['arg']
            names.append((label, tuple(a & 0xffffffff for a in c.args[:8])))
        # stores made after the step: a pc-ordered list, creature offsets only
        stores = [(w[1] - OBJ, w[2], w[3]) for w in writes
                  if OBJ <= w[1] < OBJ + 0x2000 and w[1] - OBJ not in (0x11a,)]
        return names, stores, status, True

    def run(self, fn, states):
        out = {}
        for st in states:
            per = {}
            for default in (0, DUMMY):
                tag = 'ret0' if default == 0 else 'retobj'
                base, bstores, status, stepped = self.one_run(fn, st, 0, default, 0)
                held, _, _, _ = self.one_run(fn, st, 0, default, 0xffff)
                bnames = [n for n, _ in base]
                ev = {}
                for m in MASKS:
                    got, stores, _, _ = self.one_run(fn, st, m, default, 0)
                    gnames = [n for n, _ in got]
                    extra = [n for n in dedupe(gnames) if gnames.count(n) > bnames.count(n)]
                    passed = [n for n, args in got if m in args and
                              not any(n == bn and m in bargs for bn, bargs in base)
                              and n not in extra]
                    new_stores = [x for x in stores if x not in bstores]
                    rec = {}
                    if extra:
                        rec['calls'] = extra
                    if passed:
                        rec['passes_events'] = dedupe(passed)
                    if new_stores:
                        rec['stores'] = ['+%x:%d=%x' % x for x in new_stores]
                    if rec:
                        ev['%x' % m] = rec
                per[tag] = {'status': status, 'stepped': stepped,
                            'transitions_flags_clear': [n for n, _ in base if n.startswith('setState')],
                            'transitions_flags_set': [n for n, _ in held if n.startswith('setState')],
                            'event_consumers': ev}
            out['%x' % st] = per
        return out


def dedupe(items):
    seen, out = set(), []
    for i in items:
        k = json.dumps(i, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


RAND_POINTS = tuple(range(12)) + (25, 50, 75, 99, 127, 255, 0x7fff, 0xffff)


def to_ops(calls):
    ops = []
    for c in calls:
        if 'set_state' in c:
            ops.append(('set_state', c['set_state']))
            continue
        if 'vslot' in c:
            ops.append(('vslot', c['vslot']) + ((c['arg'],) if 'arg' in c else ()))
            continue
        if 'holder' in c:
            ops.append(('holder', c['holder']))
            continue
        if 'fn' not in c:
            continue
        fn = c['fn']
        if c.get('state_arg') not in ('114', None):
            ops.append(('other_state', fn, c['state_arg']))
            continue
        e = c.get('entry')
        e = e if isinstance(e, int) else None
        h = lambda k: int(c[k], 16)
        if fn == 'anim_start':
            ops.append(('start', e, h('blend'), h('flags')))
        elif fn == 'anim_startBlendInOut':
            ops.append(('blend', e, h('blend'), h('blend_out'), h('flags')))
        elif fn == 'anim_push':
            ops.append(('push', e, h('flags')))
        elif fn == 'anim_pushWithWeights':
            ops.append(('push_w', e, h('flags'), tuple(int(w, 16) for w in c['weights'])))
        elif fn == 'anim_pushChained':
            ops.append(('push_chained', e, h('flags')))
        elif fn == 'anim_stop':
            ops.append(('stop', e, h('blend')))
        else:
            ops.append(({'anim_syncToSimFrame': 'sync', 'anim_jumpTopToEnd': 'jump_end',
                         'anim_snapTopToEnd': 'snap_end', 'anim_randomizeTopTime': 'randomize',
                         'anim_clear': 'clear', 'anim_dropNonPersistent': 'drop'}[fn],))
    return ops


def parse_when(text):
    if text.startswith('callees return'):
        return ('ret', int(text.split()[-1], 16))
    where, value = text.split('=')
    value = int(value, 16)
    if where.startswith('+'):
        return (int(where[1:], 16), value)
    return (int(where, 16), value)


def emit(sc, report, runs):
    """Python source of ref_creature_dispatch_data from a scan report."""
    dispatch, events, variants, ctor_ops, consumers, ends = {}, {}, {}, {}, {}, {}
    for name in sorted(report):
        e = report[name]
        set_fn = int(e['setState'], 16)
        states = {}

        def norm(st, outs):
            return sorted(json.dumps([o['when'], o['calls'],
                                      'same' if o['stored'] == st else o['stored']])
                          for o in outs)
        top = max(int(k, 16) for k in e['set_state'])
        default_outs = e['set_state']['%x' % top]['outcomes']
        default = norm(top, default_outs)
        d0 = default_outs[0]
        default_case = {'ops': to_ops(d0['calls']),
                        'stored': 'same' if d0['stored'] == top else d0['stored']}
        for skey, v in e['set_state'].items():
            st = int(skey, 16)
            outs = v['outcomes']
            base = outs[0]
            if norm(st, outs) == default:
                continue            # the switch's default branch (see 'default')
            case = {'ops': to_ops(base['calls']), 'stored': base['stored']}
            if any(o['when'].startswith('rand=') for o in outs):
                points = []
                for r in RAND_POINTS:
                    k = sc.one_state(set_fn, st, rand=r)[0]
                    calls, stored, _ = json.loads(k)
                    points.append((r, to_ops(calls), stored))
                period = None
                for p in range(1, 13):
                    if all(points[i][1:] == points[i % p][1:] for i in range(len(points))
                           if points[i][0] < 12) and all(
                           (o, so) == tuple(points[r % p][1:]) for r, o, so in points if r >= 12):
                        period = p
                        break
                if period and any(points[i][2] != points[i % period][2]
                                  for i in range(len(points)) if points[i][0] < 12):
                    period = None
                if period:
                    case['rand'] = (period, [points[i][1] for i in range(period)])
                    stores = [points[i][2] for i in range(period)]
                    if any(x != case['stored'] for x in stores):
                        case['rand_stored'] = stores
                else:
                    case['rand_points'] = [(r, o, so) for r, o, so in points]
            when = []
            for o in outs[1:]:
                if o['when'].startswith('rand=') or o['status'] != 'ok':
                    continue        # a faulting probe says nothing about the class
                if o['when'].startswith('+') and int(o['when'][1:].split('=')[0], 16) \
                        in COMMON:
                    continue
                when.append((parse_when(o['when']), to_ops(o['calls']), o['stored']))
            if when:
                case['when'] = when
            states[st] = case
        dispatch[name] = {'setState': set_fn, 'run': int(e['run'], 16),
                          'vtable': int(e['vtable'], 16), 'states': states,
                          'default': default_case}
        first = True
        for ckey in sorted(e['ctors'], key=lambda k: (k.split('/')[0] != sorted(e['ctors'])[0].split('/')[0], k)):
            info = e['ctors'][ckey]
            ev = {x['entry']: tuple((int(t, 16), int(m, 16)) for t, m in
                                    zip(x['times'], x['masks'])) for x in info['events']}
            ctor_addr, variant = (ckey + '/v0').split('/')[:2]
            again = sc.ctor(int(ctor_addr, 16), int(variant[1:]), set_fn)
            ops = to_ops(again['anims'])
            if first:
                events[name], ctor_ops[name] = ev, ops
                first = False
            elif ev != events[name]:
                variants.setdefault(name, {})[ckey] = ev
        cons, end = {}, {}
        for skey, per in runs.get(name, {}).items():
            st = int(skey, 16)
            masks, receives = {}, None
            clear, held = set(), set()
            for tag, r in per.items():
                ev = r['event_consumers']
                every = set.intersection(*[set(ev.get('%x' % m, {}).get('passes_events', ()))
                                           for m in MASKS])
                receives = every if receives is None else receives | every
                for m, rec in ev.items():
                    items = list(rec.get('calls', ())) + ['store ' + x for x in
                                                          rec.get('stores', ())]
                    for n in items:
                        if n not in masks.setdefault(int(m, 16), []):
                            masks[int(m, 16)].append(n)
                clear |= set(r['transitions_flags_clear']) - set(r['transitions_flags_set'])
                held |= set(r['transitions_flags_set']) - set(r['transitions_flags_clear'])
            masks = {m: v for m, v in masks.items() if v}
            common = [n for n in masks.get(MASKS[0], ())
                      if all(n in masks.get(m, ()) for m in MASKS)]
            if common:          # the same under every mask: "any nonzero event word"
                for m in MASKS:
                    masks[m] = [n for n in masks[m] if n not in common]
                masks = {m: v for m, v in masks.items() if v}
                masks[0] = common
            if receives:
                masks[-1] = sorted(receives)
            if masks:
                cons[st] = {m: tuple(v) for m, v in sorted(masks.items())}
            num = lambda xs: tuple(sorted(int(x[9:-1], 16) for x in xs))  # noqa: E731
            if clear or held:
                end[st] = (num(clear), num(held))
        if cons:
            consumers[name] = cons
        if end:
            ends[name] = end
    out = ['"""Generated by tools/scan_anim_dispatch.py --emit; do not edit by hand.',
           '',
           'Per-class numbers for ref_creature_dispatch (see its docstring and',
           'docs/spec/creature-animation-dispatch.md).  Addresses, definition entry',
           'indices, raw32 time patterns, flag words and masks only: Executed single-',
           'function results on stub state, not runs of the game."""', '']
    for label, value in (('DISPATCH', dispatch), ('EVENTS', events),
                         ('EVENT_VARIANTS', variants), ('CTOR_OPS', ctor_ops),
                         ('CONSUMERS', consumers), ('END_TRANSITIONS', ends)):
        out.append('%s = %s' % (label, pretty(value)))
        out.append('')
    return '\n'.join(out)


def pretty(value, indent=0):
    pad = ' ' * indent
    if isinstance(value, dict) and value and indent < 8:
        rows = []
        for k in sorted(value, key=lambda k: (str(type(k)), k)):
            key = ('0x%x' % k) if isinstance(k, int) and k > 9 else repr(k)
            rows.append('%s    %s: %s,' % (pad, key, pretty(value[k], indent + 4)))
        return '{\n' + '\n'.join(rows) + '\n' + pad + '}'
    return hexrepr(value)


def hexrepr(v):
    if isinstance(v, bool) or v is None:
        return repr(v)
    if isinstance(v, int):
        return '0x%x' % v if v > 9 else str(v)
    if isinstance(v, (list, tuple)):
        inner = ', '.join(hexrepr(x) for x in v)
        if isinstance(v, tuple):
            return '(' + inner + (',)' if len(v) == 1 else ')')
        return '[' + inner + ']'
    if isinstance(v, dict):
        return '{' + ', '.join('%s: %s' % (hexrepr(k), hexrepr(x)) for k, x in v.items()) + '}'
    return repr(v)


def main(argv):
    if len(argv) > 1 and argv[1] == '--markdown':
        import ref_creature_dispatch_data as data
        report = {}
        for path in argv[2:]:
            report.update(json.load(open(path)))
        sys.stdout.write(groups_markdown(data) + '\n<!-- SPLIT -->\n' +
                         markdown(report, data) + '\n')
        return
    if len(argv) > 1 and argv[1] == '--runs':
        sc = Scanner(argv[2])
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        only = set(argv[4:])
        runs = {}
        for name, vtable, ctors, cases in catalogue(root):
            if only and name not in only:
                continue
            runs[name] = sc.run(sc.slot(vtable, 4), sorted(set(cases)) or [0])
            print(name, file=sys.stderr)
            json.dump(runs, open(argv[3], 'w'), indent=1, sort_keys=True)
        return
    if len(argv) > 1 and argv[1] == '--emit':
        sc = Scanner(argv[2])
        report, runs = {}, {}
        for path in argv[3:]:
            target = runs if os.path.basename(path).startswith('runs') else report
            target.update(json.load(open(path)))
        sys.stdout.write(emit(sc, report, runs))
        return
    if len(argv) < 2:
        raise SystemExit(__doc__)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sc = Scanner(argv[1])
    out_path = argv[2] if len(argv) > 2 else os.path.join(root, 'local', 'anim-dispatch-scan.json')
    only = set(argv[3:])
    report = {}
    for name, vtable, ctors, cases in catalogue(root):
        if only and name not in only:
            continue
        set_fn, run_fn = sc.slot(vtable, 27), sc.slot(vtable, 4)
        entry = {'vtable': '%x' % vtable, 'setState': '%x' % set_fn, 'run': '%x' % run_fn,
                 'ctors': {}}
        for c in ctors:
            seen = {}
            for variant in (0, 1, 2):
                info = sc.ctor(c, variant, set_fn)
                key = json.dumps([info['creature_ctor_def'], info['events']])
                if key in seen:
                    continue
                seen[key] = variant
                for d in info['creature_ctor_def']:
                    info.setdefault('def_names', {})[d] = sc.def_names(int(d, 16))
                entry['ctors']['%x/v%d' % (c, variant)] = info
        entry['set_state'] = sc.set_state(set_fn)
        report[name] = entry
        print(name, 'setState %x run %x' % (set_fn, run_fn), file=sys.stderr)
        with open(out_path, 'w') as f:      # after every class: partial runs survive
            json.dump(report, f, indent=1, sort_keys=True)
    print('wrote', out_path, len(report), 'classes', file=sys.stderr)




# ---- markdown appendix (python3 tools/scan_anim_dispatch.py --markdown scan.json ...) --
FLAG_NAMES = ((0x1, 'LOOP'), (0x2, 'PURGE'), (0x4, 'END'), (0x8, 'ACT'), (0x10, 'HIT'),
              (0x20, 'TALK'), (0x40, 'FIXED'), (0x100, 'EASE'), (0x200, 'KEEP'),
              (0x800, 'ROOT'), (0x1000, 'PERSIST'), (0x2000, 'PAUSED'), (0x4000, 'YAW'))


def flag_text(f):
    parts = [n for b, n in FLAG_NAMES if f & b]
    rest = f & ~sum(b for b, _ in FLAG_NAMES)
    if rest:
        parts.append('%#x' % rest)
    return '|'.join(parts) or '0'


def seconds(raw):
    import struct
    return '%g' % round(struct.unpack('<f', struct.pack('<I', raw))[0], 4)


def op_text(op, names):
    nm = lambda e: ('%d %s' % (e, names[e].rsplit('.', 1)[0]) if e is not None and  # noqa
                    e < len(names) else str(e))
    k = op[0]
    if k == 'start':
        return 'start(%s, %ss, %s)' % (nm(op[1]), seconds(op[2]), flag_text(op[3]))
    if k == 'blend':
        return 'blend(%s, %ss/%ss, %s)' % (nm(op[1]), seconds(op[2]), seconds(op[3]),
                                           flag_text(op[4]))
    if k in ('push', 'push_chained'):
        return '%s(%s, %s)' % (k, nm(op[1]), flag_text(op[2]))
    if k == 'push_w':
        return 'push_w(%s, %s, %s)' % (nm(op[1]), flag_text(op[2]),
                                      '/'.join(seconds(w) for w in op[3]))
    if k == 'stop':
        return 'stop(%s, %ss)' % (nm(op[1]), seconds(op[2]))
    if k == 'vslot':
        return 'slot%d%s' % (op[1], '(%#x)' % op[2] if len(op) > 2 else '')
    if k == 'holder':
        return 'holder.slot%d' % op[1]
    if k == 'set_state':
        return 'setState(%#x)' % op[1]
    if k == 'other_state':
        return '%s on +%s' % (op[1], op[2])
    return k


def cond_text(cond):
    if cond[0] == 'ret':
        return 'callees return %s' % ('object' if cond[1] > 1 else cond[1])
    where = ('+%#x' % cond[0]) if cond[0] < 0x10000 else ('[%#x]' % cond[0])
    return '%s=%#x' % (where, cond[1])


def groups_markdown(data):
    import ref_creature_dispatch as D
    titles = {'root': 'Common base, root-motion locomotion',
              'steered': 'Common base, steered locomotion (walk/run loops without ROOT)',
              'special': 'Own state machines', 'none': 'No animation dispatch in setState'}
    out = []
    groups = {}
    for name, info in sorted(data.DISPATCH.items()):
        groups.setdefault(D.group_of(info), []).append(name)
    for g in ('root', 'steered', 'special', 'none'):
        names = groups.get(g, [])
        out.append('### 5.%d %s (%d classes)' % (('root', 'steered', 'special', 'none').index(g)
                                                 + 1, titles[g], len(names)))
        out.append('')
        if g == 'none':
            out.append(', '.join(names) + '.')
            out.append('')
            continue
        out.append('| class | base states that differ | own states (role) | attack flags | '
                   'hit 0x12 choice | death 0x14 choice | consumers (run) |')
        out.append('|---|---|---|---|---|---|---|')
        for name in names:
            info = data.DISPATCH[name]
            dev = D.base_deviations(info)
            devs = ', '.join('%#x %s' % (k, v) for k, v in sorted(dev.items())) or '—'
            own = ', '.join('%#x %s' % (k, D.state_role(info, k)) for k in sorted(info['states'])
                            if k not in D.BASE_ROLES and D.state_role(info, k) != 'none')
            aflags = set()
            for k, c in info['states'].items():
                for ops in D.alternatives(c):
                    for op in ops:
                        if op[0] in ('start', 'blend') and op[-1] & D.ACTION:
                            aflags.add(flag_text(op[-1]))
            def choice(st):
                c = info['states'].get(st)
                if not c:
                    return '—'
                parts = []
                if c.get('rand'):
                    parts.append('rand %% %d' % c['rand'][0])
                if c.get('rand_points'):
                    parts.append('rand thresholds')
                fields = sorted({('+%#x' % w[0][0]) if w[0][0] != 'ret' else 'callee'
                                 for w in c.get('when', ())
                                 if w[1] != c['ops'] and w[0][0] != 'ret'
                                 and w[0][0] < 0x10000})
                parts += fields
                return ', '.join(parts) or 'fixed'
            used = set()
            for st, ms in data.CONSUMERS.get(name, {}).items():
                for m, fs in ms.items():
                    for f in fs:
                        if f.startswith(('Creature_hit', 'skill', 'model_getAttach', 'fx_',
                                         'camera', 'world_create', 'decal')) or 'ctor' in f \
                                or f.endswith('_cast') or 'Projectile' in f:
                            used.add(f)
            out.append('| %s | %s | %s | %s | %s | %s | %s |' % (
                name, devs, own or '—', ', '.join(sorted(aflags)) or '—', choice(0x12),
                choice(0x14), ', '.join(sorted(used)) or '—'))
        out.append('')
    return '\n'.join(out)


def markdown(report, data):
    out = []
    for name in sorted(data.DISPATCH):
        info = data.DISPATCH[name]
        e = report.get(name, {})
        ctor = sorted(e.get('ctors', {}))[:1]
        names = []
        defs = []
        for ck in sorted(e.get('ctors', {})):
            for d, nm in e['ctors'][ck].get('def_names', {}).items():
                if d not in defs:
                    defs.append(d)
                if not names:
                    names = nm
        out.append('#### %s' % name)
        out.append('')
        out.append('vtable %#x, setState %#x, run %#x, constructor %s; definition %s (`%s`)'
                   % (info['vtable'], info['setState'], info['run'],
                      ', '.join('0x' + c.split('/')[0] for c in ctor) or '?',
                      ', '.join('0x' + d for d in defs) or 'not seen',
                      names[0] if names else '?'))
        out.append('')
        init = data.CTOR_OPS.get(name)
        if init:
            out.append('Constructor: ' + '; '.join(op_text(o, names) for o in init) + '.')
            out.append('')
        if info['states']:
            out.append('| state | ops (entry name, blend, flags) | stored | choice |')
            out.append('|---|---|---|---|')
            for st in sorted(info['states']):
                case = info['states'][st]
                ops = '; '.join(op_text(o, names) for o in case['ops']) or '—'
                choice = []
                ent = lambda t: ','.join(str(o[1]) for o in t if o[0] in  # noqa: E731
                                         ('start', 'blend', 'push', 'push_w')) or '—'
                if 'rand' in case:
                    p, table = case['rand']
                    rs = case.get('rand_stored')
                    choice.append('rand %% %d → %s' % (p, ', '.join(
                        ent(t) + ((' (state %#x)' % rs[i]) if rs else '')
                        for i, t in enumerate(table))))
                if 'rand_points' in case:
                    choice.append('rand (not periodic): ' + ', '.join(
                        '%d→%s%s' % (r, ent(t), '' if so == case['stored'] else
                                     ' (state %#x)' % so)
                        for r, t, so in case['rand_points']))
                for cond, ops2, stored in case.get('when', ()):
                    if ops2 == case['ops'] and stored == case['stored']:
                        continue
                    choice.append('%s → %s%s' % (cond_text(cond),
                                  '; '.join(op_text(o, names) for o in ops2) or 'no clip',
                                  '' if stored == case['stored'] else ', stores %#x' % stored))
                out.append('| %#x | %s | %s | %s |' % (
                    st, ops, '%#x' % case['stored'] if case['stored'] != st else '=',
                    '<br>'.join(choice)))
            out.append('')
        ev = data.EVENTS.get(name)
        if ev:
            out.append('Events: ' + '; '.join(
                '%d %s: %s' % (k, names[k].rsplit('.', 1)[0] if k < len(names) else '?',
                               ', '.join('%#x@%ss' % (m, seconds(t)) for t, m in slots if m))
                for k, slots in sorted(ev.items())) + '.')
            out.append('')
        for ck, v in data.EVENT_VARIANTS.get(name, {}).items():
            out.append('Events, constructor %s: ' % ck + '; '.join(
                '%d: %s' % (k, ', '.join('%#x@%ss' % (m, seconds(t)) for t, m in s if m))
                for k, s in sorted(v.items())) + '.')
            out.append('')
        cons = data.CONSUMERS.get(name)
        if cons:
            out.append('Event consumers (run): ' + '; '.join(
                'state %#x: %s' % (st, ', '.join(
                    ('%#x→%s' % (m, '+'.join(f))) if m > 0 else
                    ('any event→%s' % '+'.join(f)) if m == 0 else
                    ('event word→%s' % '+'.join(f)) for m, f in sorted(ms.items())))
                for st, ms in sorted(cons.items())) + '.')
            out.append('')
        ends = data.END_TRANSITIONS.get(name)
        if ends:
            out.append('Clip-status transitions (run): ' + '; '.join(
                'state %#x: %s' % (st, ', '.join(
                    ([('→%s when the marker/status bits are clear' %
                       '/'.join('%#x' % a for a in clr))] if clr else []) +
                    ([('→%s when they are set' % '/'.join('%#x' % a for a in held))]
                     if held else [])))
                for st, (clr, held) in sorted(ends.items())) + '.')
            out.append('')
    return '\n'.join(out)


if __name__ == '__main__':
    main(sys.argv)
