#!/usr/bin/env python3
"""HUD quick slots against the original SLUS-20973 v2.00 code.

Runs the original functions in tools/ee_emu.py on constructed state and compares
them with tools/ref_hud_quickslots.py:

  count_potions   player_countPotions 0x1ba5f8
  use_potion      Player_usePotion 0x1b9cb8 (notice starters 1, 2, 4, 5; counts)
  glyph           button glyph 0x1df060
  gates           hud_spellSelect 0x1dd270: each input gate alone
  selector        hud_spellSelect on random pad sequences: fade, held flag, mask,
                  sprites, icons, labels, messages, name text, prompt, menu mode

  python3 tools/difftest_hud_quickslots.py [SLUS_209.73] [--seed N] [-k TEXT]

Every property uses random.Random('<seed>/<name>') and counts the draws of the three
generators (0x404464 shared, 0x404460 cosmetic, 0x404468 third) from the emulator's
writes. Exits 0 with a skip when the ELF is missing. Does not import unittest.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F                       # noqa: E402
import ref_hud_quickslots as Q             # noqa: E402
from ee_emu import EE, raw_to_float        # noqa: E402

G_SHARED, G_COSMETIC, G_THIRD = 0x404464, 0x404460, 0x404468
PLAYERS, REC = 0x4d8af0, 0x4c30
SKILL_TABLE = 0x41b170
VT_DEFAULT, VT_DISEASEBOLT = 0x5123c8, 0x518468          # Skill tables; slot 7 at +0x38
VT_ICON = {VT_DEFAULT: (0x533cf0, 0x533d00), VT_DISEASEBOLT: (0x54ea40, 0x54ea60)}  # res_find args
OPTIONS = {'seed': 20973, 'filter': None}
RESULTS = []


def elf_path(argv):
    if argv:
        return argv[0]
    env = os.environ.get('CHAMPIONS_ELF')
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.path.join(os.getcwd(), 'SLUS_209.73'), os.path.join(here, 'local', 'SLUS_209.73'),
                 os.path.join(os.getcwd(), 'local', 'SLUS_209.73')):
        if os.path.isfile(cand):
            return cand
    return None


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


class Draws:
    """Seed-draw counter over emu.writes (generator words written per call)."""

    def __init__(self):
        self.total = {G_SHARED: 0, G_COSMETIC: 0, G_THIRD: 0}
        self.calls = 0

    def count(self, emu):
        self.calls += 1
        for _pc, addr, size, _v in emu.writes:
            if addr in self.total and size == 4:
                self.total[addr] += 1
        emu.writes = []

    def text(self):
        return 'draws shared %d cosmetic %d third %d over %d calls (model 0)' % (
            self.total[G_SHARED], self.total[G_COSMETIC], self.total[G_THIRD], self.calls)

    def ok(self):
        return not any(self.total.values())


def report(name, cases, bad, draws, first=None):
    ok = not bad and draws.ok()
    RESULTS.append((name, ok))
    print('%s  %-14s %6d cases  %s%s' % ('PASS' if ok else 'FAIL', name, cases, draws.text(),
                                         '' if ok else '  [%d mismatches] %s' % (bad, str(first)[:700])))
    sys.stdout.flush()


def cstr(emu, a):
    return emu.mem.cstr(a).decode('latin1') if isinstance(emu.mem.cstr(a), bytes) else emu.mem.cstr(a)


# ---------------------------------------------------------------------------------------
# Potions
# ---------------------------------------------------------------------------------------
class PotionRig:
    def __init__(self, elf):
        e = self.e = EE(elf)
        self.names = {}
        for tag, table in (('h', Q.POTION_NAMES_HEALTH), ('m', Q.POTION_NAMES_MANA)):
            for i in range(9):
                self.names[(tag, i)] = e.mem.u32(table + 4 * i)
        strings = set(cstr(e, a) for a in self.names.values())
        self.distinct = len(strings)
        count_tab = [e.mem.u32(Q.POTION_NAMES_COUNT + 4 * i) for i in range(18)]
        self.count_table_ok = (sorted(count_tab[:9]) == sorted(self.names[('m', i)] for i in range(9)) and
                               sorted(count_tab[9:]) == sorted(self.names[('h', i)] for i in range(9)))
        self.defs = {}
        self.log = []
        e.stub(0x13e150, function=lambda emu: self.local)
        e.stub(0x17365c, ret=0x1234)
        e.stub(0x214230, function=lambda emu: self.log.append(('sound',)))
        e.stub(0x1c59d0, function=lambda emu: self.log.append(('drop',)))
        e.stub(0x1c1cb0, function=lambda emu: self.log.append(('remove', s32(emu.r[4]), s32(emu.r[5]),
                                                                   s32(emu.r[6]), s32(emu.r[7]))))

        def weight(emu):
            emu.f[0] = F.ONE
        e.stub(0x1b6338, function=weight)
        for a in (0x1ed778, 0x1ed854, 0x173c84, 0x1d9954):
            e.stub(a, ret=0)
        self.local = 1

    def item_def(self, name):
        if name not in self.defs:
            d = self.e.alloc(0x40)
            if isinstance(name, tuple):
                p = self.names[name]
            else:
                p = self.e.alloc(16)
                self.e.mem.write(p, name.encode() + b'\0')
            self.e.mem.w32(d, p)
            self.defs[name] = d
        return self.defs[name]

    def set_bag(self, rec, bag, b=2):
        base = rec + 0x130 + 0x1208 * b
        for j, (name, qty) in enumerate(bag):
            self.e.mem.w32(base + 0x48 * j, self.item_def(name))
            self.e.mem.w16(base + 0x48 * j + 4, qty & 0xffff)
        self.e.mem.w32(rec + 0x1330 + 0x1208 * b, len(bag))


def random_bag(rng, n_max=12):
    bag = []
    for _ in range(rng.randrange(0, n_max + 1)):
        r = rng.random()
        if r < 0.4:
            name = ('h', rng.randrange(9))
        elif r < 0.8:
            name = ('m', rng.randrange(9))
        else:
            name = 'junk%d' % rng.randrange(4)
        bag.append((name, rng.choice((1, 1, 2, 3, 5, 9, 20))))
    return bag


def prop_count_potions(elf, rng):
    rig = PotionRig(elf)
    e, draws, bad, first, n = rig.e, Draws(), 0, None, 0
    for _ in range(400):
        slot, kind = rng.randrange(4), rng.choice((0, 1, 2))
        rec = PLAYERS + slot * REC
        bag = random_bag(rng, 20)
        rig.set_bag(rec, bag)
        e.mem.w32(Q.COUNT_HEALTH + 4 * slot, 0xdead)
        e.mem.w32(Q.COUNT_MANA + 4 * slot, 0xdead)
        e.writes = []
        got = s32(e.call(0x1ba5f8, slot, kind))
        draws.count(e)
        want, addr = Q.count_potions(bag, kind)
        other = Q.COUNT_MANA if addr == Q.COUNT_HEALTH else Q.COUNT_HEALTH
        g = (got, s32(e.mem.u32(addr + 4 * slot)), e.mem.u32(other + 4 * slot))
        if g != (want, want, 0xdead):
            bad += 1
            first = first or (slot, kind, bag, g, want)
        n += 1
    ok_tables = rig.distinct == 18 and rig.count_table_ok
    report('count_potions', n, bad + (0 if ok_tables else 1), draws, first or 'tables')


def prop_use_potion(elf, rng):
    rig = PotionRig(elf)
    e, draws, bad, first, n = rig.e, Draws(), 0, None, 0
    P = e.alloc(0x600)
    # invmsg_sendDrop (stubbed) reads its arguments from this machine's grid copies
    # (0x4ebbb0): give it a block whose every word points at a zeroed dummy.
    dummy = e.alloc(0x40)
    grid_block = e.alloc(0x100000)
    e.mem.write(grid_block, struct.pack('<I', dummy) * (0x100000 // 4))
    notices = {}
    for _ in range(600):
        slot, kind = rng.randrange(4), rng.randrange(2)
        rec = PLAYERS + slot * REC
        e.mem.w32(P + 0x3c8, slot)
        copy = rng.random() < 0.05
        e.mem.w32(P + 0xc, 0x20000 if copy else 0)
        f = lambda v: F.f32(v)
        maxhp = f(rng.choice((100.0, 250.0, 700.0, 1234.5)))
        maxmana = f(rng.choice((80.0, 300.0, 999.0)))
        hp = f(rng.choice((0.0, -5.0)) if rng.random() < 0.05 else rng.uniform(1, F.to_float(maxhp)))
        mana = f(rng.uniform(0, F.to_float(maxmana)))
        hpp = f(rng.choice((0.0, 0.0, rng.uniform(0, 200))))
        mp = f(rng.choice((0.0, 0.0, rng.uniform(0, 200))))
        for off, v in ((0xac, hp), (0xb0, maxhp), (0xb4, hpp), (0xc0, mana), (0xc4, maxmana), (0xc8, mp)):
            e.mem.w32(rec + off, v)
        bag = random_bag(rng)
        rig.set_bag(rec, bag)
        bags01 = [random_bag(rng, 3), random_bag(rng, 3)]
        rig.set_bag(rec, bags01[0], 0)
        rig.set_bag(rec, bags01[1], 1)
        e.mem.w32(rec + 0x120, 0x12345678)
        timers = [rng.choice((0, 0, 0, 5, 100)) for _ in range(8)]
        rows = [rng.randrange(4) for _ in range(8)]
        for i in range(8):
            e.mem.w32(Q.NOTICE_TIMERS + 0x20 * slot + 4 * i, timers[i])
            e.mem.w32(Q.NOTICE_ROWS + 0x20 * slot + 4 * i, rows[i])
        rig.local = int(rng.random() < 0.7)
        menu_open, grid = int(rng.random() < 0.3), int(rng.random() < 0.5)
        e.mem.w8(0x41b69d, menu_open)
        e.mem.w32(0x4ebbb0, grid_block if grid else 0)
        e.mem.w32(Q.COUNT_HEALTH + 4 * slot, 0xdead)
        e.mem.w32(Q.COUNT_MANA + 4 * slot, 0xdead)
        e.mem.w16(Q.USE_COUNTER[0], 0)
        e.mem.w16(Q.USE_COUNTER[1], 0)
        rig.log = []
        e.writes = []
        e.call(0x1b9cb8, P, kind, 0, 0, 0xffffffff)
        draws.count(e)
        st = dict(copy=copy, hp=hp, maxhp=maxhp, hp_pending=hpp, mana=mana, maxmana=maxmana,
                  mana_pending=mp, bag=bag, local=rig.local, menu_open=menu_open, grid=grid,
                  kind=kind, timers=timers, rows=rows)
        m = Q.use_potion(st)
        got_t = [s32(e.mem.u32(Q.NOTICE_TIMERS + 0x20 * slot + 4 * i)) for i in range(8)]
        got_r = [s32(e.mem.u32(Q.NOTICE_ROWS + 0x20 * slot + 4 * i)) for i in range(8)]
        problems = []
        if m['regen'] is not None and (e.mem.u32(rec + 0xb8), e.mem.u32(rec + 0xbc)) != m['regen']:
            problems.append('regen')
        if m['returned_early']:
            if (got_t, got_r) != (timers, rows) or rig.log:
                problems.append('early')
        else:
            if (got_t, got_r) != (m['timers'], m['rows']):
                problems.append(('notices', got_t, got_r, m['timers'], m['rows']))
            pend_addr = rec + (0xb4 if kind == 0 else 0xc8)
            if e.mem.u32(pend_addr) != m['pending']:
                problems.append('pending')
            want_log = []
            if m['sound']:
                want_log.append(('sound',))
            if m['sent_drop']:
                want_log.append(('drop',))
            if m['removed'] is not None:
                want_log.append(('remove', slot, m['removed'], 2, 0))
            if rig.log != want_log:
                problems.append(('log', rig.log, want_log))
            if m['count'] is not None:
                g = (Q.COUNT_HEALTH if kind == 0 else Q.COUNT_MANA) + 4 * slot
                if s32(e.mem.u32(g)) != m['count']:
                    problems.append('count')
                cells = [e.mem.u16(rec + Q.BAG2 + Q.CELL * j + 4) for j in range(len(bag))]
                if cells != [q & 0xffff for _n, q in m['bag']]:
                    problems.append('cells')
                if e.mem.u16(m['counter']) != 1:
                    problems.append('counter')
                items = len(bag) + len(bags01[0]) + len(bags01[1])
                if e.mem.u32(rec + 0x120) != F.f32(float(items)):
                    problems.append('load')
        for line, _fr in m['notices']:
            notices[line] = notices.get(line, 0) + 1
        if problems:
            bad += 1
            first = first or (st, problems)
        n += 1
    report('use_potion', n, bad, draws, first)
    print('      notice starts by line: %s' % ', '.join('%d:%d' % kv for kv in sorted(notices.items())))


# ---------------------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------------------
class SelectorRig:
    def __init__(self, elf):
        e = self.e = EE(elf)
        self.ev = []
        self.handles = {}
        self.gate = {}
        self.local = 1
        self.texthandles = {}
        e.stub(0x13e150, function=lambda emu: self.local)
        e.stub(0x22fbc0, function=lambda emu: int(bool(self.gate.get('dialog'))))
        e.stub(0x217518, function=lambda emu: int(bool(self.gate.get('memcard'))))

        def task(emu):
            name = cstr(emu, emu.r[4])
            self.ev_task = name
            return int(bool(self.gate.get('jumpgate'))) if name == 'jumpgate' else 0
        e.stub(0x19e5e8, function=task)
        e.stub(0x17365c, function=lambda emu: self.handle(('res', cstr(emu, emu.r[4]), cstr(emu, emu.r[5]))))
        e.stub(0x17377c, function=lambda emu: self.handle(('ref', emu.r[4] & 0xffffffff)))

        def sprintf(emu):
            fmt = cstr(emu, emu.r[5])
            a = emu.r[6] & 0xffffffff
            if '%s' in fmt:
                v = fmt.replace('%s', cstr(emu, a))
            elif '%c' in fmt:
                v = fmt.replace('%c', chr(a & 0xff))
            else:
                v = fmt.replace('%d', str(s32(a)))
            emu.mem.write(emu.r[4] & 0xffffffff, v.encode('latin1') + b'\0')
            return len(v)
        e.stub(0x3b7ef0, function=sprintf)
        e.stub(0x214230, function=lambda emu: self.ev.append(('sound',) + self.names[emu.r[4] & 0xffffffff][1:]))
        e.stub(0x17fb68, function=lambda emu: self.ev.append(
            ('S', self.names.get(emu.r[4] & 0xffffffff, ('raw', emu.r[4] & 0xffffffff)),
             s32(emu.r[5]), s32(emu.r[6]), s32(emu.r[7]), emu.r[8] & 0xffffffff)))
        e.stub(0x1800b8, function=lambda emu: self.ev.append(
            ('TB', emu.r[4] & 0xffffffff, s32(emu.r[5]), emu.r[6] & 0xffffffff, s32(emu.r[7]))))
        e.stub(0x181aa0, function=lambda emu: self.ev.append(
            ('TA', s32(emu.r[4]), s32(emu.r[5]), cstr(emu, emu.r[6]), s32(emu.r[7]))))
        e.stub(0x180500, function=lambda emu: self.ev.append(('TE',)))
        e.stub(0x181ca0, function=lambda emu: self.ev.append(
            ('TW', s32(emu.r[4]), s32(emu.r[5]), self.textkey(emu.r[6] & 0xffffffff), s32(emu.r[7]))))
        e.stub(0x173c84, function=lambda emu: self.texthandle(cstr(emu, emu.r[4])))
        e.stub(0x19ea78, function=lambda emu: self.ev.append(
            ('fmt', self.textkey(emu.r[5] & 0xffffffff)) +
            tuple(int(raw_to_float(emu.f[i])) for i in (12, 13, 14))))
        e.stub(0x1d99f0, function=lambda emu: self.ev.append(('prompt', s32(emu.r[5]), s32(emu.r[6]), s32(emu.r[7]))))

        def send(emu):
            n = s32(emu.r[6])
            self.ev.append(('wire', emu.r[4] & 0xffffffff, bytes(emu.mem.read(emu.r[5] & 0xffffffff, n))))
        e.stub(0x13db38, function=send)
        self.names = {}
        self.cam = e.alloc(0x40)
        e.mem.w32(0x4f8450, self.cam)
        e.mem.w32(0x86ac40, 3)

    def handle(self, key):
        if key not in self.handles:
            a = self.e.alloc(16)
            self.handles[key] = a
            self.names[a] = key
        return self.handles[key]

    def texthandle(self, key):
        if key not in self.texthandles:
            a = self.e.alloc(16)
            self.texthandles[key] = a
            self.texthandles[a] = key
        return self.texthandles[key]

    def textkey(self, a):
        return self.texthandles.get(a, ('raw', a))


GATE_ADDR = {'menu_lockout': (0x41b4fc, 4), 'paused': (0x41b4f4, 4), 'pause_menu': (0x44fa78, 1),
             'medal': (0x4f7114, 4), 'input_block': (0x4f66c8, 1)}


def set_gates(rig, gates):
    e = rig.e
    rig.gate = dict(gates)
    for name, (addr, size) in GATE_ADDR.items():
        (e.mem.w8 if size == 1 else e.mem.w32)(addr, 1 if gates.get(name) else 0)
    e.mem.w32(rig.cam + 0x34, 2 if gates.get('camera') else 1)


class Scenario:
    """Constructed players, records, skills and icon table for one selector run."""

    def __init__(self, rig, rng, slot, menu, page, network, players):
        e = rig.e
        self.slot, self.menu, self.page, self.network, self.players = slot, menu, page, network, players
        self.rec = PLAYERS + slot * REC
        e.mem.w8(0x402791, network)
        e.mem.w32(0x4d8ae0, players)
        e.mem.w32(self.rec + 0xac, F.f32(10.0))
        self.font = e.alloc(16)
        e.mem.w32(0x4f7104, self.font)
        self.masks = {}
        for key, addr in (('accept', Q.BTN_MENU_ACCEPT), ('a', Q.BTN_ABILITY_A), ('b', Q.BTN_ABILITY_B),
                          ('use', Q.BTN_USE)):
            self.masks[key] = rng.choice((0x10, 0x20, 0x40, 0x80, 0x4, 0x8))
            e.mem.w32(addr + 4 * slot, self.masks[key])
        # 0x1ddce8 reads the accept mask of slot 0 for every slot
        self.masks['accept'] = rng.choice((0x10, 0x20, 0x40, 0x80))
        e.mem.w32(Q.BTN_MENU_ACCEPT, self.masks['accept'])
        self.glyphs = {}
        for n in range(9):
            v = rng.choice(Q.GLYPH_MASKS + (0, 0x100))
            e.mem.w32(Q.BUTTON_CONFIG + 4 * (slot * 9 + n), v)
            self.glyphs[n] = Q.button_glyph(v)
        self.records = []
        self.skill_icon = {}
        self.table = {}
        for idx in range(60):
            v = rig.handle(('tex', idx)) if rng.random() < 0.5 else 0
            e.mem.w32(Q.ICON_TABLE + 4 * idx, v)
            self.table[idx] = v
        for k in range(8):
            r = rng.random()
            base = self.rec + Q.RECORDS + k * Q.RECORD_SIZE
            if r < 0.25:
                rec = dict(id=-1, newstyle=rng.random() < 0.5, name='old%d' % k)
            elif r < 0.65:
                sid = rng.randrange(1, 102)
                rec = dict(id=sid, newstyle=True, name='newstyle')
                vt = rng.choice((VT_DEFAULT, VT_DISEASEBOLT))
                obj = e.alloc(0x70)
                nm = e.alloc(32)
                skname = 'skill%d' % sid
                e.mem.write(nm, skname.encode() + b'\0')
                e.mem.w32(obj, nm)
                e.mem.w32(obj + 0x60, vt)
                e.mem.w32(SKILL_TABLE + 4 * sid, obj)
                lmp, tex = VT_ICON[vt]
                self.skill_icon[sid] = (('res', cstr(e, lmp), cstr(e, tex)), skname)
            else:
                sid = rng.randrange(0, 60)
                rec = dict(id=sid, newstyle=False, name='legacy%d' % rng.randrange(100))
            e.mem.write(base, (rec['name'].encode() + b'\0').ljust(0x20, b'\0'))
            e.mem.w16(base + 0x20, rec['id'] & 0xffff)
            self.records.append(rec)
        self.quick = (rng.randrange(-1, 8), rng.randrange(-1, 8))
        e.mem.w8(self.rec + Q.QUICK_A, self.quick[0] & 0xff)
        e.mem.w8(self.rec + Q.QUICK_B, self.quick[1] & 0xff)
        self.kind = rng.choice((1, 1, 0, -1)) if menu else 0
        self.value = 0
        if menu and self.kind == 1:
            # the menu's own item is a skill that is also in one of the records, or a fresh one
            sid = rng.choice([r['id'] for r in self.records if r['newstyle'] and r['id'] > 0] or [0])
            if not sid:
                sid = 101
                obj = e.alloc(0x70)
                nm = e.alloc(32)
                e.mem.write(nm, b'skill101\0')
                e.mem.w32(obj, nm)
                e.mem.w32(obj + 0x60, VT_DISEASEBOLT)
                e.mem.w32(SKILL_TABLE + 4 * sid, obj)
                lmp, tex = VT_ICON[VT_DISEASEBOLT]
                self.skill_icon[sid] = (('res', cstr(e, lmp), cstr(e, tex)), 'skill101')
            self.value = sid
        elif menu:
            self.value = rng.randrange(0, 1 << 40)

    def resolve(self, rig, item):
        """Model event resource -> what the emulator records."""
        kind = item[0]
        if kind in ('res', 'ref'):
            return item
        icon = item[1]
        if icon[0] == 'blank':
            return ('ref', Q.RES_BLANK)
        if icon[0] == 'skill':
            return self.skill_icon[icon[1]][0]
        v = self.table.get(icon[1], 0)
        if v:
            return rig.names[v]
        return None if kind == 'icon_or_none' else ('ref', Q.RES_BLANK)

    def name_key(self, key):
        if key[0] == 'key':
            return key[1]
        if key[0] == 'skillname':
            return self.skill_icon[key[1]][1] + '_name'
        return key[1] + '_name'


def expected_events(scn, rig, ev):
    out = []
    for x in ev:
        if x[0] == 'S':
            res = scn.resolve(rig, x[1])
            if res is None:
                continue
            out.append(('S', res) + x[2:])
        elif x[0] == 'TW':
            out.append(('TW', x[1], x[2], scn.name_key(x[3]), x[4]))
        elif x[0] == 'TB':
            out.append(('TB', scn.font) + x[2:])
        elif x[0] == 'msg':
            mid, args = x[1], x[2]
            if mid == Q.MSG_QUICKSLOT:
                body = bytes((0, args[0], args[1], args[2]))
            elif mid == Q.MSG_QUICKCAST:
                body = bytes((13, args[0], args[1]))
            else:
                body = bytes((1, args[0], args[1], 0)) + struct.pack('<iQ', args[2], args[3])
            out.append(('wire', 3, body))
        elif x[0] == 'fmt':
            out.append(x)
        else:
            out.append(x)
    return out


DIR_BITS = (0, 0x1000, 0x2000, 0x4000, 0x8000, 0x3000, 0x6000, 0x9000, 0xc000, 0xa000, 0x5000, 0xf000)


def run_frames(rig, scn, rng, frames, draws, stats, gate_rate=0.15):
    e, slot = rig.e, scn.slot
    st_alpha, st_timer, st_speed, st_dir = 0, F.ZERO, -1, -1
    e.mem.w32(Q.SELECTOR_ALPHA + 4 * slot, 0)
    e.mem.w32(scn.rec + 0x4a74, F.ZERO)
    e.mem.w32(scn.rec + 0x4a78, 0xffffffff)
    e.mem.w32(Q.SELECTOR_DIR + 4 * slot, 0xffffffff)
    mask_entry = (rng.randrange(0, 6), 0, 0)
    for i, v in enumerate(mask_entry):
        e.mem.w32(Q.MASK_TABLE + 12 * slot + 4 * i, v)
    bad, first = 0, None
    for fr in range(frames):
        held = rng.choice(DIR_BITS) if fr < frames // 3 or rng.random() < 0.3 else 0
        pressed = rng.choice((0, 0, 0, scn.masks['a'], scn.masks['b'], scn.masks['use'], scn.masks['accept'],
                              scn.masks['a'] | scn.masks['b']))
        gates = {}
        if rng.random() < gate_rate:
            gates[rng.choice(Q.GATES)[0]] = 1
        lmo = int(rng.random() < 0.1)
        rig.local = 1 if rng.random() < 0.97 else 0
        hp = F.f32(10.0) if rng.random() < 0.97 else F.ZERO
        tick = rng.randrange(0, 4000)
        set_gates(rig, gates)
        e.mem.w8(0x41b69d, lmo)
        e.mem.w32(scn.rec + 0xac, hp)
        e.mem.w32(0x4028d8 + Q.PAD_STRIDE * slot, held)
        e.mem.w32(0x4028dc + Q.PAD_STRIDE * slot, pressed)
        e.mem.w32(0x44fdd0, tick)
        e.mem.w8(Q.BUST_LATCH, 0)
        st = dict(slot=slot, page=scn.page, menu=scn.menu, kind=scn.kind, value=scn.value,
                  players=scn.players, network=scn.network, local=rig.local, hp=hp, gates=gates,
                  local_menu_open=lmo, held_bits=held, pressed_bits=pressed, masks=scn.masks,
                  alpha=st_alpha, timer=st_timer, speed=st_speed, prev_dir=st_dir, tick=tick,
                  quick=scn.quick, records=scn.records, glyphs=scn.glyphs, mask_entry=mask_entry,
                  font=scn.font, held=s32(e.mem.u32(Q.SELECTOR_HELD + 4 * slot)))
        rig.ev = []
        e.writes = []
        e.call(0x1dd270, slot, scn.page, scn.menu, scn.kind & 0xff, scn.value)
        draws.count(e)
        want_ev, s = Q.selector_frame(st)
        want = expected_events(scn, rig, want_ev)
        got_state = (s32(e.mem.u32(Q.SELECTOR_ALPHA + 4 * slot)), e.mem.u32(scn.rec + 0x4a74),
                     s32(e.mem.u32(scn.rec + 0x4a78)), s32(e.mem.u32(Q.SELECTOR_DIR + 4 * slot)),
                     e.mem.u8(Q.BUST_LATCH),
                     tuple(s32(e.mem.u32(Q.MASK_TABLE + 12 * slot + 4 * i)) for i in range(3)))
        want_state = (s['alpha'], s['timer'], s['speed'], s['dir'], s['latch'], s['mask_entry'])
        got_held = s32(e.mem.u32(Q.SELECTOR_HELD + 4 * slot))
        if rig.ev != want or got_state != want_state or (st['local'] and hp and got_held != s['held']):
            bad += 1
            if first is None:
                first = (slot, scn.menu, fr, got_state, want_state, got_held, s['held'],
                         [(a, b) for a, b in zip(rig.ev, want) if a != b][:3], len(rig.ev), len(want))
        st_alpha, st_timer, st_speed, st_dir = s['alpha'], s['timer'], s['speed'], s['dir']
        mask_entry = s['mask_entry']
        stats['frames'] += 1
        stats['drawn'] += 1 if s['alpha'] > 0 and want_ev else 0
        for x in want_ev:
            stats[x[0]] = stats.get(x[0], 0) + 1
    return bad, first


def prop_selector(elf, rng):
    rig = SelectorRig(elf)
    draws, bad, first = Draws(), 0, None
    stats = {'frames': 0, 'drawn': 0}
    runs = 0
    for slot in range(4):
        for network in (0, 1):
            for menu, page in ((0, 0), (1, 0), (1, 1)):
                players = rng.choice((1, 2, 4))
                scn = Scenario(rig, rng, slot, menu, page, network, players)
                b, f = run_frames(rig, scn, rng, 70, draws, stats)
                bad += b
                first = first or f
                runs += 1
    report('selector', stats['frames'], bad, draws, first)
    print('      %d runs, %d drawn frames; events: %s' % (runs, stats['drawn'], ', '.join(
        '%s %d' % (k, v) for k, v in sorted(stats.items()) if k not in ('frames', 'drawn'))))


def prop_gates(elf, rng):
    rig = SelectorRig(elf)
    e, draws, bad, first, n = rig.e, Draws(), 0, None, 0
    for slot in range(4):
        scn = Scenario(rig, rng, slot, 0, 0, 0, 4)
        for name, _desc in Q.GATES + (('none', ''),):
            for lmo in (0, 1):
                set_gates(rig, {name: 1})
                e.mem.w8(0x41b69d, lmo)
                bits = rng.choice(DIR_BITS[1:])
                e.mem.w32(0x4028d8 + Q.PAD_STRIDE * slot, bits)
                e.mem.w32(0x4028dc + Q.PAD_STRIDE * slot, 0)
                e.mem.w32(Q.SELECTOR_ALPHA + 4 * slot, 0)
                e.mem.w32(Q.SELECTOR_HELD + 4 * slot, 7)
                e.mem.w32(scn.rec + 0x4a74, F.ZERO)
                e.mem.w32(scn.rec + 0x4a78, 0xffffffff)
                rig.local = 1
                e.writes = []
                e.call(0x1dd270, slot, 0, 0, 0, 0)
                draws.count(e)
                readable = Q.pad_readable({name: 1}, lmo)
                want_held = 1 if readable else 0
                got = (s32(e.mem.u32(Q.SELECTOR_HELD + 4 * slot)), s32(e.mem.u32(Q.SELECTOR_ALPHA + 4 * slot)))
                if got != (want_held, 16 if readable else 0):
                    bad += 1
                    first = first or (slot, name, lmo, got, want_held)
                n += 1
    report('gates', n, bad, draws, first)


def prop_glyph(elf, rng):
    e = EE(elf)
    draws, bad, first, n = Draws(), 0, None, 0
    for _ in range(300):
        slot, btn = rng.randrange(4), rng.randrange(9)
        v = rng.choice(Q.GLYPH_MASKS + (0, 0x100, 0x200, rng.randrange(1 << 16)))
        e.mem.w32(Q.BUTTON_CONFIG + 4 * (slot * 9 + btn), v)
        e.writes = []
        got = s32(e.call(0x1df060, slot, btn))
        draws.count(e)
        if got != Q.button_glyph(v):
            bad += 1
            first = first or (slot, btn, hex(v), got)
        n += 1
    report('glyph', n, bad, draws, first)


PROPS = (('count_potions', prop_count_potions), ('use_potion', prop_use_potion), ('glyph', prop_glyph),
         ('gates', prop_gates), ('selector', prop_selector))


def main(argv):
    args, rest = list(argv), []
    while args:
        a = args.pop(0)
        if a == '--seed':
            OPTIONS['seed'] = int(args.pop(0))
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            rest.append(a)
    elf = elf_path(rest)
    if not elf or not os.path.isfile(elf):
        print('SKIP  difftest_hud_quickslots: SLUS_209.73 not found')
        return 0
    print('seed %d' % OPTIONS['seed'])
    for name, fn in PROPS:
        if OPTIONS['filter'] and OPTIONS['filter'] not in name:
            continue
        fn(elf, random.Random('%d/%s' % (OPTIONS['seed'], name)))
    failed = [n for n, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
