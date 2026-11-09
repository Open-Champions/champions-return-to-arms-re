#!/usr/bin/env python3
"""Hub and hub2 between-mission services against the original EE code.

Give the owner's US v2.00 executable and the disc's BG/DATA directory (or the
disc image). Archives are read only. Output is counts, node indices, script
public offsets and addresses: never script names, variable names, text keys,
item names or dialogue. Contract: docs/hub-services.md. Model:
tools/ref_hub_services.py.

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; \
  sys.argv=["difftest_hub_services.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA"]; \
  runpy.run_path("tools/difftest_hub_services.py", run_name="__main__")'

What runs for real: the shipped hub script through scr_load 0x13e8f8,
scr_registerNatives 0x141310, script_runByName 0x1ed694 and the original
built-in handlers (difftest_natives.Rig), and, for whole conversations, the
original dialog_onMsg 0x22ee2c / dialog_showNode 0x230c74 composition pinned in
t3/research-mission-unlocks 2ab82b2 (tools/difftest_mission_unlocks.py Probe,
loaded from that Git object unchanged), with the Rig's stub hook at dialog_isOpen
0x22fbc0 removed so that the real function reads g_dialogData 0x8e2d60. Stubs
(recording, named in the output groups below): every other ref_natives.EXT
service, among them dialog_isOpen in the plain rig, inventory_findItemBySubstring,
inventory_countItemByName, inventory_removeItem, missionMenu_open,
hud_showHelpMessage, text_lookup, cut_start, res_find.
"""
import argparse
import hashlib
import mmap
import os
import random
import struct
import subprocess
import sys
import types

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_natives as N  # noqa: E402
from gob import gob_entries, lmp_entries  # noqa: E402
import ref_hub_services as R  # noqa: E402
import scr  # noqa: E402

ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ARCHIVE_SHA256 = {
    'HUB.GOB': '1d5f240025afb86800040664a168c27c236a8431fc4c02caf388bdcee37b385f',
    'HUB2.GOB': 'a061b0f35549674050765eb8f3243491f947888c2cdcef85e5110e2388d71dc4',
}
UNLOCKS_PIN = '2ab82b2'          # t3/research-mission-unlocks, Probe composition
PLAYERS, REC = 0x4D8AF0, 0x4C30
MISSION, QUEST, QUEST_COUNT = 0x4BBF, 0x41D0, 0x43D0
MANA, MANA_MAX, FLAGS = 0xC0, 0xC4, 0x4C28
G_PACKED_SWAP = 0x40335C         # g_scrPackedSwap, script machine bookkeeping
G_STORE_INDEX, G_STORE_PENDING, G_SWOOP = 0x4F7150, 0x4FDD30, 0x4FDCE4
G_QUEST_VARS, G_SAVE_INHIBIT = 0x86DA80, 0x50605C
G_PLAYER_OBJ = 0x4DCEC8
G_DIALOG_DATA, F_DIALOG_IS_OPEN = 0x8E2D60, 0x22FBC0
G_PAUSED, G_JUMPGATE_TRAVEL, G_CUTSCENE_ACTIVE = 0x41B4F4, 0x500AE8, 0x44FCD0
SCRIPT_SPAN = 0x40000
NODE, CHOICE = 0x448, 0x54
TOTAL = {'checks': 0}
DIALOG_REACH = {}                # hub -> natives the live dialog's entries can reach
# Built-ins a fee, healer, trainer or bank would need; neither hub script imports one.
NO_SERVICE_NATIVES = {'givePlayerGold', 'takePlayerGold', 'checkPlayerGold', 'givePlayerExp',
                      'healPlayer', 'giveFullHealth', 'setHitPoints', 'playerAdjustStat',
                      'givePlayerItem', 'saveGame', 'saveCheckPoint', 'removeQuest'}
# Every native a live-dialog action entry may reach (callScript, addDeferedCall,
# postAction and internal calls followed).  No live-dialog entry may reach a native
# whose name contains 'item' or 'gold' (item_or_gold).
ACTION_NATIVES = {'setMissionAvailable', 'addQuest', 'setv', 'changeSwoop', 'activateStore'}
SCRIPT_CALLERS = ('callScript', 'addDeferedCall', 'postAction')
# Disc values of the two PushTrigger records (HSV-5), asserted in check_travel.
PUSH_PROPS = {'hub': {'nethostonly': '1', 'radius': '79'}, 'hub2': {'nethostonly': '1', 'radius': '78'}}
# Neutral-id callees, asserted from the scripts in check_travel.
K_IDS = {'hub': {'K.lock': 0x3CB0, 'K.use': 0x49C0, 'K.warn': 0x4234, 'K.walk': 0x4C44,
                 'K.help': 0x4A80, 'K.poll': 0x4B0C},
         'hub2': {'K.lock': 0x1500, 'K.use': 0x2210, 'K.warn': 0x1A84, 'K.walk': 0x2494,
                  'K.help': 0x22D0, 'K.poll': 0x235C}}


def item_or_gold(names):
    return sorted(n for n in names if 'item' in n.lower() or 'gold' in n.lower())


def require(cond, detail):
    if not cond:
        raise AssertionError(detail)
    TOTAL['checks'] += 1


# ---------------------------------------------------------------------------------------
# Private inputs
# ---------------------------------------------------------------------------------------
def read_archives(data, iso):
    found = {}
    if data:
        for label in sorted(os.listdir(data)):
            if label.upper().endswith('.GOB'):
                found[label.upper()] = open(os.path.join(data, label), 'rb').read()
    else:
        from find_hosts import iso_files
        with open(iso, 'rb') as handle:
            disc = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                for path, lba, size in iso_files(disc):
                    label = path.rsplit('/', 1)[-1].upper()
                    if label.endswith('.GOB') and path.upper().startswith('/BG/DATA/'):
                        found[label] = disc[lba * 2048:lba * 2048 + size]
            finally:
                disc.close()
    out = {}
    for label, blob in found.items():
        if label not in ARCHIVE_SHA256:
            continue
        require(hashlib.sha256(blob).hexdigest() == ARCHIVE_SHA256[label], label)
        files = {}
        for _name, lo, size in gob_entries(blob):
            lump = blob[lo:lo + size]
            for inner, off, n in lmp_entries(lump):
                files[inner.lower()] = lump[off:off + n]
        out['hub' if label == 'HUB.GOB' else 'hub2'] = files
    require(set(out) == {'hub', 'hub2'}, 'both hubs')
    others = {}
    for label, blob in found.items():
        if label in ARCHIVE_SHA256:
            continue
        for lump_name, lo, size in gob_entries(blob):
            lump = blob[lo:lo + size]
            for inner, off, n in lmp_entries(lump):
                if inner.lower() == 'script.scr':
                    key = (label, lump_name)
                    require(key not in others, 'one script per lump')
                    others[key] = lump[off:off + n]
    return out, others


class Script:
    """Static view of one hub script: public entries and native call sites."""

    def __init__(self, image):
        self.image = image
        parsed = scr.parse(image)
        self.pool = dict(scr.strings(image, *parsed['strings']))
        self.natives = [name for _, name in parsed['externals']]
        self.entries = sorted(parsed['internals'])
        self.name_at = dict(self.entries)
        self.offset_of = {name: off for off, name in self.entries}
        self.sites = []
        self.bounds = []          # (site, limit) of every 'check 0 <= A <= limit' (op 0x79)
        self.internal = []        # (site, target) of every internal call (op 0x31)
        cs, ce = parsed['code']
        words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
        pending, i = [], 0
        while i < len(words):
            op = words[i]
            if op == 0x7D:
                i += 3
                continue
            if op == 0x7B:
                args = [v for kind, v in pending[:-1][::-1]] if pending else []
                self.sites.append((i * 4, self.natives[words[i + 1]], args))
                pending, i = [], i + 2
                continue
            if op == 0x27:
                pending.append(('imm', words[i + 1]))
                i += 2
                continue
            if op in (0x28, 0x2C) or op in (0x24, 0x25):
                pending = [] if op == 0x2C else pending + [('x', None)]
                i += 2 if op in (0x28, 0x2C) else 1
                continue
            if op == 0x79:
                self.bounds.append((i * 4, words[i + 1]))
            if op == 0x31:
                self.internal.append((i * 4, words[i + 1]))
            pending = []
            i += 1 + scr.OPS[op][1] if op in scr.OPS else (1 if op in scr.NO_OPERAND else 2)

    def end_of(self, offset):
        later = [off for off, _ in self.entries if off > offset]
        return min(later) if later else 1 << 30

    def owner(self, site):
        return max(off for off, _ in self.entries if off <= site)

    def calls(self, offset):
        end = self.end_of(offset)
        return [(site, name, args) for site, name, args in self.sites if offset <= site < end]

    def internal_calls(self, offset):
        end = self.end_of(offset)
        return [target for site, target in self.internal if offset <= site < end]

    def bounds_in(self, offset):
        end = self.end_of(offset)
        return [limit for site, limit in self.bounds if offset <= site < end]

    def callees(self, offset):
        """Entries named by a literal callScript / addDeferedCall / postAction, plus
        internal call targets; a non-literal script caller fails the check."""
        out = []
        for _s, name, args in self.calls(offset):
            if name in SCRIPT_CALLERS:
                require(args and args[0] in self.pool and self.pool[args[0]] in self.offset_of,
                        ('literal script caller', hex(offset), name))
                out.append(self.offset_of[self.pool[args[0]]])
        return out + [t for t in self.internal_calls(offset)]

    def reach(self, offsets):
        """Natives reachable from the given entries, following callees."""
        seen, todo, natives = set(), list(offsets), set()
        while todo:
            offset = todo.pop()
            if offset in seen:
                continue
            seen.add(offset)
            natives |= {name for _s, name, _a in self.calls(offset)}
            todo.extend(self.callees(offset))
        return natives, seen

    def literal(self, value):
        return self.pool[value]

    def getv_names(self, offset):
        return [self.literal(args[0]) for _s, name, args in self.calls(offset) if name == 'getv']


def live_dialog(script):
    start = [args for _s, name, args in script.sites if name == 'startDialog']
    require(len(start) == 1, 'one startDialog')
    return script.literal(start[0][0]).lower() + '.dbin'


def dbin(blob):
    nodes = []
    for n in range(blob[0]):
        row = blob[n * NODE:(n + 1) * NODE]
        text = lambda b: b.split(b'\0')[0].decode('latin1')
        count, = struct.unpack_from('<i', row, 0x54)
        choices = []
        for i in range(count):
            o = 0x58 + i * CHOICE
            choices.append((text(row[o:o + 0x10]), text(row[o + 0x10:o + 0x30]),
                            text(row[o + 0x30:o + 0x50]),
                            struct.unpack_from('<i', row, o + 0x50)[0]))
        nodes.append((text(row[1:0x21]), choices))
    return nodes


# ---------------------------------------------------------------------------------------
# 1. Dialog structure, roles and the model's address map
# ---------------------------------------------------------------------------------------
def check_structure(hubs, scripts):
    for hub in ('hub', 'hub2'):
        files, script = hubs[hub], scripts[hub]
        dialogs = sorted(k for k in files if k.endswith('.dbin'))
        # The NPC entry's single startDialog names the live file; every other .dbin is
        # unused by the hub NPC (a backup copy, and in hub a single-node cutscene dialog).
        live = live_dialog(script)
        require(live in files, 'live dialog present')
        require(len(dialogs) == (3 if hub == 'hub' else 2), (hub, len(dialogs)))
        nodes = dbin(files[live])
        model = R.NODES[hub]
        require(len(nodes) == len(model), (hub, len(nodes)))
        keys = {}
        for index, ((cond, choices), (m_cond, _k, _n, m_choices)) in enumerate(zip(nodes, model)):
            require(script.offset_of[cond] == m_cond, (hub, index, 'cond'))
            require(len(choices) == len(m_choices), (hub, index, 'choices'))
            for (key, ccond, action, nxt), (role, m_ccond, _ck, _cn, m_act, m_nxt) in zip(choices, m_choices):
                keys.setdefault(key, set()).add(role)
                require((script.offset_of[ccond] if ccond else None) == m_ccond, (hub, index, 'ccond'))
                require((script.offset_of[action] if action else None) == m_act, (hub, index, 'act'))
                require(nxt == m_nxt, (hub, index, 'next'))
        # Three choice keys, each with one role; roles follow from structure:
        require(len(keys) == 3 and all(len(r) == 1 for r in keys.values()), (hub, 'keys'))
        for key, (role,) in ((k, tuple(v)) for k, v in keys.items()):
            rows = [c for _cond, cs in nodes for c in cs if c[0] == key]
            if role == R.MORE:
                require(all(c[3] != -1 for c in rows), 'more continues')
            else:
                require(all(c[3] == -1 for c in rows), 'end/shop closes')
            if role == R.SHOP:
                require(all(R.ACTIONS[hub][script.offset_of[c[2]]]['store'] for c in rows), 'shop')
            if role == R.END:
                require(not any(c[2] and R.ACTIONS[hub][script.offset_of[c[2]]]['store'] for c in rows), 'end')
        require(not NO_SERVICE_NATIVES & set(script.natives), (hub, 'fee/heal/train natives'))
        referenced = {script.offset_of[c[2]] for _cond, cs in nodes for c in cs if c[2]}
        require(referenced == set(R.ACTIONS[hub]), (hub, 'action set'))
        # activateStore: every store action the live dialog reaches pushes the literal 0;
        # the argument-less form (index read from the script stack) is backup-only.
        for table, pushed in ((R.ACTIONS[hub], [[0]]), (R.UNREFERENCED_WRITERS[hub], [[]])):
            for offset, effect in table.items():
                sites = [a for _s, n, a in script.calls(offset) if n == 'activateStore']
                require(sites == (pushed if effect['store'] else []), (hub, hex(offset), 'store arg'))
        unused = set(R.UNREFERENCED_WRITERS[hub])
        require(not unused & referenced, 'unreferenced writers')
        in_backup, backups, cutscenes = set(), 0, []
        for name in dialogs:
            if name == live:
                continue
            other = dbin(files[name])
            if len(other) == 1:
                # one node, no condition, no choices: the cutscene line list (HSV-5)
                require(other[0] == ('', []), (hub, 'cutscene dialog shape'))
                cutscenes.append(name)
                continue
            require(len(other) > 1 and all(cond for cond, _cs in other), (hub, 'backup shape'))
            backups += 1
            for _cond, cs in other:
                in_backup |= {script.offset_of.get(c[2]) for c in cs if c[2]}
        require(backups == 1 and len(cutscenes) == (1 if hub == 'hub' else 0), (hub, 'other dialogs'))
        require(unused <= in_backup, (hub, 'unreferenced writers named by the backup dialog'))
        for name in cutscenes:
            # the cutscene entry requests a cutscene of the same stem (the link is Inferred)
            cut = [script.literal(a[0]).lower() for _s, n, a in script.calls(0x34A4)
                   if n == 'cutScene' and a and a[0] in script.pool]
            require(cut == [name[:-len('.dbin')]], (hub, 'cutscene entry stem'))
        # HSV-1: what the live dialog can reach, statically and through every callee
        conds = {script.offset_of[c] for c, _cs in nodes} | \
                {script.offset_of[c[1]] for _c, cs in nodes for c in cs if c[1]}
        act_natives, act_entries = script.reach(referenced)
        cond_natives, cond_entries = script.reach(conds)
        require(act_natives <= ACTION_NATIVES, (hub, sorted(act_natives - ACTION_NATIVES)))
        require(not item_or_gold(act_natives | cond_natives), (hub, 'item/gold native reachable'))
        removal = [script.owner(site) for site, n, _a in script.sites if n == 'removePlayerItem']
        start = script.offset_of['start']
        deferred = [script.offset_of[script.literal(a[0])] for _s, n, a in script.calls(start)
                    if n == 'addDeferedCall']
        require(len(deferred) == 2, (hub, 'two deferred checks'))
        by_owner = [removal.count(start)] + [removal.count(d) for d in deferred]
        require(len(removal) == 19 and by_owner == [17, 1, 1], (hub, 'removal sites', by_owner))
        require(not ({start} | set(deferred)) & (act_entries | cond_entries), (hub, 'entry reached'))
        DIALOG_REACH[hub] = act_natives | cond_natives
        print('%s: %d nodes, %d choices, %d distinct actions; roles more/end/shop by structure; '
              '%d other dialog files (%d backup%s); %d of %d unreferenced writers named by the '
              'backup dialog PASS'
              % (hub, len(nodes), sum(len(cs) for _c, cs in nodes), len(referenced),
                 len(dialogs) - 1, backups,
                 ', 1 one-node cutscene line list with no condition and no choices, whose stem '
                 'public 0x34a4 requests' if cutscenes else '',
                 len(unused & in_backup), len(unused)))
        print('%s: dialog reach: %d action entries -> %d entries, natives {%s}; %d condition entries '
              '-> %d entries, %d natives; no item or gold native; %d removePlayerItem sites = %d in '
              'start %#x + %d + %d in the deferred checks %#x/%#x, none reached by the dialog PASS'
              % (hub, len(referenced), len(act_entries), ', '.join(sorted(act_natives)), len(conds),
                 len(cond_entries), len(cond_natives), len(removal), by_owner[0], start,
                 by_owner[1], by_owner[2], deferred[0], deferred[1]))


# ---------------------------------------------------------------------------------------
# Plain script rig: one place per hub, restore per case
# ---------------------------------------------------------------------------------------
class Answers:
    def __init__(self):
        self.open, self.found, self.count = 1, -1, 0

    def answer(self, name, args):
        if name == 'dialog_isOpen':
            return self.open
        if name == 'inventory_findItemBySubstring':
            return (self.found, 0)
        if name == 'inventory_countItemByName':
            return self.count
        return 0


class Plain:
    def __init__(self, elf, script, seed):
        self.rig = rig = N.Rig(elf)
        rig.checkpoint()
        rig.responder = self.answers = Answers()
        self.script, self.seed = script, seed
        require(rig.place(script.image + bytes(256)) == (0, 0), 'place')
        # scr_load's own store; restore() would otherwise return it to the pre-load value
        self.swap = rig.emu.mem.u32(G_PACKED_SWAP)
        require(self.swap == 1, 'loader swap word')
        self.natives, self.argc = [], []
        rig.emu.hook(N.SCR_CALL_NATIVE, self._native)
        self.names = {}

    def _native(self, emu):
        params = emu.r[7] & 0xFFFFFFFF   # callback(machine, index, &PRI, params)
        index = emu.r[5] & 0xFFFFFFFF
        cells = [emu.mem.u32(params + 4 * k) for k in range(1, 4)] if params else []
        self.natives.append((self.script.natives[index], cells))
        self.argc.append(emu.mem.u32(params) // 4 if params else 0)   # cell 0 = argument bytes

    def reset(self, raw=None, players=1, difficulty=0):
        rig = self.rig
        rig.restore()
        mem = self.mem = rig.emu.mem
        mem.w32(G_PACKED_SWAP, self.swap)
        mem.w32(N.N.G_NUM_PLAYERS, players)
        mem.w32(N.N.G_DIFFICULTY, difficulty)
        mem.w32(N.N.G_RAND_SEED, self.seed)
        mem.w8(N.N.G_NETWORK_MODE, 0)
        mem.w32(N.N.G_ACTIVE_PLAYER, 0)
        mem.w32(N.N.G_SELECTED_OBJ, 0)
        mem.w8(0x41B51D, 0)
        mem.write(G_QUEST_VARS, bytes(0x2000))
        mem.write(N.N.G_POST_ACTION, bytes(0x80))
        mem.write(N.N.G_ENTRANCE_NAME, b'ENTRANCE-SENTINEL\0')
        for slot in range(4):
            base = PLAYERS + slot * REC
            mem.write(base + MISSION, bytes(65))
            mem.write(base + QUEST, bytes(0x200))
            mem.w32(base + QUEST_COUNT, 0)
        if raw is not None:
            mem.write(PLAYERS + MISSION + difficulty * 13, bytes(raw))
        self.answers.__init__()
        rig.emu.reset_log()
        return mem

    def cstr(self, text):
        pointer = self.rig.emu.alloc(64)
        self.mem.write(pointer, text.encode('latin1') + b'\0')
        return pointer

    def setv(self, name, value):
        self.rig.call(0x1ED854, self.cstr(name), value)

    def getv(self, name):
        return N.s32(self.rig.call(0x1ED778, self.cstr(name))) & 0xFF

    def run(self, offset, keep_seed=True):
        self.rig.calls = []
        self.rig.emu.calls.clear()
        self.rig.emu.reset_log()
        self.natives, self.argc = [], []
        result = N.s32(self.rig.call(0x1ED694, self.cstr(self.script.name_at[offset]),
                                     max_steps=4000000))
        if keep_seed:
            require(self.mem.u32(N.N.G_RAND_SEED) == self.seed, 'seed unchanged')
        return result

    def stubs(self):
        return [name for name, _args in self.rig.calls]

    def named(self, native):
        """Public offsets named by the first argument of each recorded call of native."""
        return [self.script.offset_of.get(self.script.pool.get(c[0]), -1)
                for n, c in self.natives if n == native]

    def written(self):
        out = set()
        base = self.rig.base
        for _pc, addr, size, _v in self.rig.emu.writes:
            if N.STACK_LO <= addr < N.STACK_HI or base <= addr < base + SCRIPT_SPAN:
                continue
            for a in range(addr, addr + size):
                out.add(a)
        return out


def regions(addresses, difficulty=0):
    labels = set()
    for a in addresses:
        if G_PACKED_SWAP <= a < G_PACKED_SWAP + 4:
            labels.add('machine')
        elif G_QUEST_VARS <= a < G_QUEST_VARS + 0x2000:
            labels.add('vars')
        elif G_STORE_INDEX <= a < G_STORE_INDEX + 2:
            labels.add('store_index')
        elif a == G_STORE_PENDING:
            labels.add('store_pending')
        elif G_SWOOP <= a < G_SWOOP + 4:
            labels.add('swoop')
        elif PLAYERS <= a < PLAYERS + 4 * REC:
            off = (a - PLAYERS) % REC
            slot = (a - PLAYERS) // REC
            if MISSION <= off < MISSION + 65:
                labels.add(('mission', slot, off - MISSION))
            elif QUEST <= off < QUEST + 0x200 or QUEST_COUNT <= off < QUEST_COUNT + 4:
                labels.add(('quest', slot))
            else:
                labels.add(('record', slot, off))
        else:
            labels.add(('other', a))
    return labels


def started_names(script, hub):
    """The twelve per-mission started variables, in mission order, as read by the
    node-0 predicate's callee (the ACTIVE scan)."""
    active = R.NODES[hub][0][0]
    callee = [script.literal(a[0]) for _s, n, a in script.calls(active) if n == 'callScript']
    names = script.getv_names(script.offset_of[callee[0]])
    require(len(names) == 12, 'twelve started variables')
    return names


# ---------------------------------------------------------------------------------------
# 2. Every condition entry over a state matrix (plain rig)
# ---------------------------------------------------------------------------------------
def check_conditions(plain, hub, rng):
    script = plain.script
    names = started_names(script, hub)
    intro_name = None
    if hub == 'hub2':
        intro_name = script.getv_names(R.NODES[hub][1][0])[0]
    preds = {}
    for cond, kind, n, choices in R.NODES[hub]:
        preds[cond] = (kind, n)
        for _role, ccond, ckind, cn, _a, _x in choices:
            if ccond is not None:
                preds[ccond] = (ckind, cn)
    states = []
    for n in R.MISSIONS:
        for raw_n in range(4):
            for s in (0, 1, -1):
                raw = [3] + [0] * 12
                raw[n] = raw_n
                started = [0] * 13
                started[n] = s
                states.append((raw, started, 0, 0))
    for _ in range(40):
        raw = [3] + [rng.randrange(4) for _ in range(12)]
        started = [0] + [rng.choice((0, 0, 1, -1, 127)) for _ in range(12)]
        states.append((raw, started, rng.choice((0, 1)), rng.choice((0, 1))))
    compared = 0
    for index, (raw, started, intro, demo) in enumerate(states):
        difficulty = index % 5
        for cond, (kind, n) in sorted(preds.items()):
            plain.reset(raw, difficulty=difficulty)
            for k in R.MISSIONS:
                if started[k]:
                    plain.setv(names[k - 1], started[k])
            if intro_name and intro:
                plain.setv(intro_name, intro)
            if demo and hub == 'hub':
                plain.setv(script.getv_names(0x498)[0], demo)
            got = plain.run(cond)
            want = R.predicate(kind, n, raw, started, intro, demo)
            require(got == want, (hub, hex(cond), raw, started, intro, got, want))
            require(not [r for r in regions(plain.written()) if r not in ('machine', 'vars')], 'cond writes')
            compared += 1
    print('%s: %d condition entries x %d states = %d original predicate results equal the model PASS'
          % (hub, len(preds), len(states), compared))
    return names, intro_name


# ---------------------------------------------------------------------------------------
# 3. Every action entry (and the unreferenced writers) with recorded writes
# ---------------------------------------------------------------------------------------
def check_actions(plain, hub):
    script = plain.script
    table = dict(R.ACTIONS[hub])
    table.update(R.UNREFERENCED_WRITERS[hub])
    executed = 0
    for offset, effect in sorted(table.items()):
        for dialog_open in (1, 0):
            difficulty = offset % 5
            mem = plain.reset([0] * 13, difficulty=difficulty)
            plain.answers.open = dialog_open
            # HSV-1: plant an item as found and held five times, so that any item removal
            # would reach the recording inventory stubs
            plain.answers.found, plain.answers.count = 0, 5
            mem.w16(G_STORE_INDEX, 0x5A5A)
            mem.w8(G_STORE_PENDING, 0)
            mem.w32(G_SWOOP, 0x5A5A5A5A)
            plain.run(offset)
            natives = [n for n, _c in plain.natives]
            require(set(natives) <= ACTION_NATIVES, (hub, hex(offset), sorted(set(natives) - ACTION_NATIVES)))
            require(not [n for n in plain.stubs() if n.startswith('inventory_')], (hub, hex(offset), 'item'))
            executed += len(natives)
            labels = regions(plain.written(), difficulty) - {'machine'}
            want = set()
            if effect['avail'] is not None:
                want.add(('mission', 0, difficulty * 13 + effect['avail']))
                require(mem.u8(PLAYERS + MISSION + difficulty * 13 + effect['avail']) == 1, 'bit')
            if effect['quest']:
                want.add(('quest', 0))
                adds = [a for _s, n, a in script.calls(offset) if n == 'addQuest']
                require(len(adds) == 1 and mem.u32(PLAYERS + QUEST_COUNT) == 1, 'quest')
                title, body = (script.literal(v) for v in adds[0][:2])
                require(mem.cstr(PLAYERS + QUEST, 0x20) == title, 'title')
                require(mem.cstr(PLAYERS + QUEST + 0x20, 0x20) == body, 'body')
            if effect['var']:
                want.add('vars')
                name = [script.literal(a[0]) for _s, n, a in script.calls(offset) if n == 'setv']
                require(len(name) == 1 and plain.getv(name[0]) == 1, 'var')
            if effect['store']:
                want |= {'swoop', 'store_index'}
                require(mem.u32(G_SWOOP) == 0, 'swoop 0')
                if dialog_open:
                    want.add('store_pending')
                    require(mem.u8(G_STORE_PENDING) == 1, 'deferred store')
                    require('shop_openOrStock' not in plain.stubs(), 'not opened inside dialog')
                else:
                    require(plain.stubs().count('shop_openOrStock') == 1, 'offline open')
                    require(mem.u8(G_STORE_PENDING) == 0, 'no deferral')
            require(labels == want, (hub, hex(offset), sorted(map(str, labels - want)),
                                     sorted(map(str, want - labels))))
    print('%s: %d action entries (%d dialog, %d unreferenced) x dialog open/closed; '
          'mission bit, quest pair, variable and store request equal the model, no other write; '
          '%d executed native calls, all in {%s}; item planted as found, 0 inventory stub calls PASS'
          % (hub, len(table), len(R.ACTIONS[hub]), len(R.UNREFERENCED_WRITERS[hub]), executed,
             ', '.join(sorted(ACTION_NATIVES))))


# ---------------------------------------------------------------------------------------
# 4. Whole conversations through the original dialog machine
# ---------------------------------------------------------------------------------------
def load_probe_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source = subprocess.check_output(['git', 'show', UNLOCKS_PIN + ':tools/difftest_mission_unlocks.py'],
                                     cwd=root)
    module = types.ModuleType('difftest_mission_unlocks_pinned')
    module.__file__ = os.path.join(root, 'tools', 'difftest_mission_unlocks.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


class ItemFound:
    """Wraps the Probe's seeded responder: every item lookup finds an item (index 0, held
    five times), so an item removal reached from the dialog would call the recording
    inventory_removeItem stub.  All other answers are unchanged."""

    def __init__(self, inner):
        self.inner = inner

    def answer(self, name, args):
        if name == 'inventory_findItemBySubstring':
            return (0, 0)
        if name == 'inventory_countItemByName':
            return 5
        return self.inner.answer(name, args)


def progress_states(hub):
    out = []
    for k in R.MISSIONS:
        base = [3] + [3] * (k - 1) + [0] * (13 - k)
        for raw_k, s in ((0, 0), (1, 0), (1, 1)):
            raw = list(base)
            raw[k] = raw_k
            started = [0] * 13
            started[k] = s
            out.append(('m%d:%s' % (k, 'offer' if raw_k == 0 else ('pending' if s == 0 else 'started')),
                        raw, started, 0))
    out.append(('all-complete', [3] * 13, [0] * 13, 0))
    out.append(('m9-available-unstarted', [3] * 9 + [1, 0, 0, 0], [0] * 13, 0))
    if hub == 'hub2':
        for k in (2, 3):
            for label, raw, started, _i in list(out):
                if label.startswith('m%d:' % k):
                    out.append((label + '+intro-heard', raw, started, 1))
        out.append(('m1-incomplete', [3, 1] + [0] * 11, [0] * 13, 0))
    return out


def check_conversations(mu, elf, hubs, scripts, hub, names, intro_name, seed):
    files = hubs[hub]
    image, dialog = scripts[hub].image, files[live_dialog(scripts[hub])]
    count = 0
    table = []
    totals = {'natives': 0, 'is_open': 0, 'stores': 0}
    for label, raw, started, intro in progress_states(hub):
        variables = [(names[k - 1].encode('latin1'), started[k]) for k in R.MISSIONS if started[k]]
        if intro:
            variables.append((intro_name.encode('latin1'), intro))
        expected_start = R.start_node(hub, raw, started, intro)
        for path in R.paths(hub, raw, started, intro):
            difficulty = count % 5
            probe = mu.Probe(elf, image, dialog, seed, raw[1], raw[2], difficulty,
                             1 if hub == 'hub2' else 0, 1 if hub == 'hub2' else 0,
                             variables, raw)
            # HSV-2: the Probe follows dialog_isOpen 0x22fbc0 but N.Rig's EXT stub hook at
            # the same address wins; remove it so the real function reads g_dialogData.
            require(F_DIALOG_IS_OPEN in probe.rig.emu.follow.addresses, 'Probe follows dialog_isOpen')
            probe.rig.emu.unhook(F_DIALOG_IS_OPEN)
            mem = probe.mem
            reads = []        # g_dialogData at each entry of the real function (observer only)
            probe.rig.emu.hook(F_DIALOG_IS_OPEN, lambda e: reads.append(e.mem.u32(G_DIALOG_DATA)))
            probe.rig.responder = ItemFound(probe.rig.responder)
            mem.w8(G_STORE_PENDING, 0)
            mem.w32(G_DIALOG_DATA, 0)                    # closed before the start message
            node = probe.open()
            require(node == expected_start, (hub, label, node, expected_start))
            require(not probe.writes, 'open writes nothing')
            require(mem.u32(G_DIALOG_DATA) != 0, (hub, label, 'dialog data set by the open'))
            cur_raw, cur_intro = list(raw), intro
            quests = 0
            for step, (p_node, cursor, choice, action) in enumerate(path):
                vis = R.visible(hub, p_node, cur_raw, started, cur_intro)
                got_vis = [mem.s32(mu.D.A['visible'] + 4 * i) for i in range(mem.s32(mu.D.A['nvis']))]
                require(got_vis == vis, (hub, label, p_node, got_vis, vis))
                before, reads_before = len(probe.writes), len(reads)
                probe.entered.clear()
                probe.confirm(cursor)
                nxt = R.NODES[hub][p_node][3][choice][5]
                if action is not None:
                    effect = R.ACTIONS[hub][action]
                    require(action in probe.entered, (hub, label, hex(action)))
                    want = [(difficulty, effect['avail'], 1)] if effect['avail'] is not None else []
                    require(probe.writes[before:] == want, (hub, label, probe.writes[before:]))
                    cur_raw, quests, cur_intro, _d = R.apply_action(effect, cur_raw, started, quests,
                                                                    cur_intro, 0)
                    if effect['store']:
                        step_reads = reads[reads_before:]
                        require(step_reads and all(step_reads), (hub, label, 'real dialog_isOpen, data set'))
                        require(not [c for c in probe.rig.emu.calls if c.target == F_DIALOG_IS_OPEN
                                     and c.stubbed], 'dialog_isOpen not stubbed')
                        require(mem.u8(G_STORE_PENDING) == 1, 'store deferred to dialog end')
                        require(not [1 for n, _a in probe.rig.calls if n == 'shop_openOrStock'],
                                'not opened inside the dialog')
                        totals['stores'] += 1
                else:
                    require(probe.writes[before:] == [], 'no action, no write')
                if nxt != -1:
                    require(mem.s32(mu.D.A['node_index']) == nxt, (hub, label, 'next'))
                require(mem.u32(PLAYERS + QUEST_COUNT) == quests, (hub, label, 'quest count'))
            # HSV-1: nothing the conversation ran asked for an item, with an item planted
            require(not [n for n, _a in probe.rig.calls if n.startswith('inventory_')], (hub, label, 'item'))
            require(set(probe.native_calls) <= DIALOG_REACH[hub], (hub, label, 'native outside reach'))
            require(not item_or_gold(probe.native_calls), (hub, label, 'item/gold native'))
            totals['natives'] += len(probe.native_calls)
            totals['is_open'] += len(reads)
            last = path[-1][3] if path else None
            table.append((label, expected_start, len(path), last))
            count += 1
    starts = sorted({row[1] for row in table})
    print('seed %d %s: %d progress states, %d whole conversations through original dialog_onMsg; '
          'start node, visible choices, actions, mission writes and quest count equal the model; '
          '%d distinct start nodes; real dialog_isOpen 0x22fbc0 (stub hook removed) ran %d times, '
          'g_dialogData planted 0 before each open and non-zero after it; %d store actions deferred '
          '(0x4fdd30 = 1, no shop_openOrStock); %d script native calls, none outside the dialog\'s '
          'static reach, no item or gold native, 0 inventory stub calls with an item planted PASS'
          % (seed, hub, len(progress_states(hub)), count, len(starts), totals['is_open'],
             totals['stores'], totals['natives']))
    return table


# ---------------------------------------------------------------------------------------
# 5. Hub entry services: store level, mana restore, item cleanup, first-mission help
# ---------------------------------------------------------------------------------------
def start_sites(script):
    start = script.offset_of['start']
    calls = script.calls(start)
    getv = [(site, script.literal(a[0])) for site, n, a in calls if n == 'getv']
    setv = [script.literal(a[0]) for _s, n, a in calls if n == 'setv']
    refill = [site for site, n, _a in calls if n == 'refillPlayerMana']
    require(len(refill) == 1, 'one mana refill')
    current, store = getv[0][1], setv[0]
    mana = [name for site, name in getv if site < refill[0]][-1]
    first = getv[-1][1]
    require(len({current, store, mana, first}) == 4, 'four distinct start variables')
    items = [script.literal(a[1]) for _s, n, a in calls if n == 'removePlayerItem' and a and a[1] in script.pool]
    return start, current, store, mana, first, items


def check_entry(plain, hub):
    script = plain.script
    start, current, store, mana, first, items = start_sites(script)
    order = list(dict.fromkeys(items))
    groups = [items.count(i) for i in order]
    require(items == [i for i in order for _ in range(items.count(i))], 'grouped sites')
    require(tuple(groups) == R.CLEANUP_SITES and len(items) == sum(R.CLEANUP_SITES), (hub, groups))
    cases = 0
    for cm in range(0, 14):
        for raw8 in (0, 1, 3):
            for raw9 in (0, 1, 3):
                raw = [0] * 13
                raw[8], raw[9] = raw8, raw9
                mem = plain.reset(raw, players=1)
                plain.setv(current, cm)
                mem.w32(G_SAVE_INHIBIT, 1)
                plain.run(start)
                require(plain.getv(store) == R.store_level(cm, raw) & 0xFF, (hub, cm, raw8, raw9))
                got = list(mem.read(PLAYERS + MISSION, 13))
                require(got == R.entry_mission_bits(hub, raw), (hub, 'entry bits', got))
                require(mem.u32(G_SAVE_INHIBIT) == 0, 'save inhibit cleared')
                cases += 1
    # player flag 4: planted set on all four records, cleared unless mission 7 or 9
    for cm in (0, 6, 7, 8, 9, 12):
        mem = plain.reset([0] * 13, players=4)
        for slot in range(4):
            mem.w8(PLAYERS + slot * REC + FLAGS, 0xFF)
        plain.setv(current, cm)
        plain.run(start)
        for slot in range(4):
            bit = (mem.u8(PLAYERS + slot * REC + FLAGS) >> 4) & 1
            require(bit == (0 if R.entry_flag4_cleared(cm) else 1), (hub, 'flag4', cm, slot))
        cases += 1
    # mana restore after the side level that zeroes mana
    for flag in (0, 1, 2, -1):
        mem = plain.reset([0] * 13, players=2)
        for slot in range(2):
            mem.w32(PLAYERS + slot * REC + MANA, 5 + slot)
            mem.w32(PLAYERS + slot * REC + MANA_MAX, 77 + slot)
        if flag:
            plain.setv(mana, flag)
        plain.run(start)
        for slot in range(2):
            new_flag, value = R.entry_mana(flag, 5 + slot, 77 + slot)
            require(mem.u32(PLAYERS + slot * REC + MANA) == value, (hub, 'mana', flag, slot))
        require(N.s32(plain.getv(mana) << 24) >> 24 == new_flag, (hub, 'mana flag', flag))
        cases += 1
    # quest-item cleanup: removePlayerItem(-1, item) for every player present
    for players in (1, 2, 4):
        for found in (-1, 0):
            mem = plain.reset([0] * 13, players=players)
            plain.answers.found = found
            plain.run(start)
            finds = [a for n, a in plain.rig.calls if n == 'inventory_findItemBySubstring']
            removes = plain.stubs().count('inventory_removeItem')
            require(len(finds) == len(items) * players, (hub, 'finds', len(finds)))
            require(removes == (len(items) * players if found == 0 else 0), (hub, 'removes'))
            require([f[1].decode('latin1') for f in finds[::players]] == items, (hub, 'item order'))
            cases += 1
    # first-mission help: shown once, sets player flag 3 on every present player
    for var in (0, 1, 2):
        for flag3 in (0, 1):
            mem = plain.reset([0] * 13, players=2)
            for slot in range(2):
                mem.w8(PLAYERS + slot * REC + FLAGS, (flag3 << 3) if slot == 0 else 0x08)
            if var:
                plain.setv(first, var)
            plain.run(start)
            shown, new_var, _all = R.entry_first_mission(var, [flag3, 1], 2)
            require(('hud_showHelpMessage' in plain.stubs()) == shown, (hub, 'help', var, flag3))
            require(plain.getv(first) == new_var, (hub, 'first var', var, flag3))
            if shown:
                require(all(mem.u8(PLAYERS + s * REC + FLAGS) & 8 for s in range(2)), 'flag3')
            cases += 1
    # portal ring reset and the two deferred duplicate checks are queued
    plain.reset([0] * 13)
    plain.run(start)
    natives = [n for n, _c in plain.natives]
    require(natives.count('addDeferedCall') == 2 and natives.count('autoPropSetState') == 1, 'queued')
    require([c[1] for n, c in plain.natives if n == 'autoPropSetState'] == [0], 'ring state 0')
    print('%s: entry `start` %d cases: store-level rule, entry mission bits, save inhibit, '
          'flag 4, mana restore, %d-call item cleanup, first-mission help, ring/deferred PASS'
          % (hub, cases, len(items)))


def check_dedupe(plain, hub):
    script = plain.script
    start = script.offset_of['start']
    deferred = [script.literal(a[0]) for _s, n, a in script.calls(start) if n == 'addDeferedCall']
    shard, blood = (script.offset_of[name] for name in deferred)
    # HSV-3: the table sizes come from the bytecode: every bounds check in each deferred
    # check (op 0x79, 'check 0 <= index <= limit') has limit = size - 1
    limits = [sorted(set(script.bounds_in(entry))) for entry in (shard, blood)]
    require(limits == [[R.SHARD_TABLE - 1], [R.BLOOD_TABLE - 1]], (hub, 'table bounds', limits))
    checks = [len(script.bounds_in(entry)) for entry in (shard, blood)]
    cases = 0
    for players in (1, 2, 4):
        for count in (0, 1, 2, 5):
            for entry, size in ((shard, R.SHARD_LIST), (blood, R.BLOOD_LIST)):
                mem = plain.reset([0] * 13, players=players)
                plain.run(start)                     # sets the player count the blood list reads
                for slot in range(4):
                    mem.w32(G_PLAYER_OBJ + slot * REC, 0)
                objs = []
                for slot in range(players):
                    obj = plain.rig.emu.alloc(0x400)
                    mem.write(obj, bytes(0x400))
                    mem.w32(G_PLAYER_OBJ + slot * REC, obj)
                    objs.append(obj)
                plain.answers.count = count
                plain.answers.found = 0
                plain.run(entry)
                asks = plain.stubs().count('inventory_countItemByName')
                removes = plain.stubs().count('inventory_removeItem')
                require(asks == size * players, (hub, 'asks', entry == shard, players, asks))
                want = R.dedupe_removals([[count] * size] * players)
                require(removes == want, (hub, 'dedupe', entry == shard, players, count, removes))
                cases += 1
    print('%s: deferred duplicate checks %#x/%#x: bytecode bounds checks 0..%d (%d sites) and '
          '0..%d (%d sites) give %d- and %d-cell tables; executed asks visit %d and %d cells per '
          'player; %d cases: one removal per visited item whose count is above 1 PASS'
          % (hub, shard, blood, limits[0][0], checks[0], limits[1][0], checks[1],
             limits[0][0] + 1, limits[1][0] + 1, R.SHARD_LIST, R.BLOOD_LIST, cases))


# ---------------------------------------------------------------------------------------
# 6. Mission-map PushTrigger key/action, walk-in Trigger and the ring action
# ---------------------------------------------------------------------------------------
def object_props(files):
    from dump_tables import parse_objects
    rows = parse_objects(files['objects.ob'], 'hub')
    out = {}
    for row in rows:
        props = dict(p.split('=', 1) if '=' in p else (p, '') for p in row['properties'].split(';') if p)
        out.setdefault(row['class'], []).append(props)
    return out


def check_travel(plain, hub, files, names, rng):
    script = plain.script
    objs = object_props(files)
    push = objs['PushTrigger'][0]
    walk = objs['Trigger'][0]
    rings = objs['apprings' if hub == 'hub' else 'fpprings'][0]
    key, action = script.offset_of[push['key']], script.offset_of[push['action']]
    rect = script.offset_of[walk['t']]
    ring = script.offset_of[rings['action1']]
    entrance_site = [a for _s, n, a in script.sites if n == 'setEntrance']
    require(len(entrance_site) == 1, 'one setEntrance')
    entrance = script.literal(entrance_site[0][0])
    # HSV-5: the PushTrigger record's disc values and the K.* callees
    require(len(objs['PushTrigger']) == 1 and len(objs['Trigger']) == 1, (hub, 'one of each'))
    require({k: push.get(k) for k in PUSH_PROPS[hub]} == PUSH_PROPS[hub], (hub, 'PushTrigger props'))
    require((key, action, rect) == (0x98, 0x54, 0xD8), (hub, 'object entries'))
    k_ids = K_IDS[hub]
    require(script.callees(key) == [k_ids['K.lock']], (hub, 'K.lock'))
    # K.use is named by callScript; it calls K.warn internally and K.help by callScript
    require(script.callees(action) == [k_ids['K.use']], (hub, 'K.use'))
    require(script.callees(rect) == [k_ids['K.walk']], (hub, 'K.walk'))
    require(script.internal_calls(k_ids['K.use']) == [k_ids['K.warn']], (hub, 'K.warn from K.use'))
    require(sorted(script.internal_calls(k_ids['K.walk'])) == sorted([k_ids['K.warn'], k_ids['K.lock']]),
            (hub, 'K.walk calls K.warn and K.lock'))
    require([o for _s, n, a in script.calls(k_ids['K.use']) if n == 'callScript'
             for o in [script.offset_of[script.literal(a[0])]]] == [k_ids['K.help']], (hub, 'K.help'))
    require(script.callees(k_ids['K.help']) == [k_ids['K.poll']], (hub, 'K.help queues K.poll'))
    require(script.callees(k_ids['K.poll']) == [k_ids['K.poll']], (hub, 'K.poll re-queues itself'))
    poll_cases = 0
    states = []
    for n in R.MISSIONS:
        for raw_n in range(4):
            for s in (0, 1):
                raw = [3] + [3] * (n - 1) + [0] * (13 - n)
                raw[n] = raw_n
                started = [0] * 13
                started[n] = s
                states.append((raw, started))
    for _ in range(24):
        states.append(([3] + [rng.randrange(4) for _ in range(12)],
                       [0] + [rng.choice((0, 0, 1)) for _ in range(12)]))
    cases = 0
    for raw, started in states:
        def prime(dialog_open=0, recall=0):
            plain.reset(raw)
            for k in R.MISSIONS:
                if started[k]:
                    plain.setv(names[k - 1], started[k])
            plain.answers.open = dialog_open
            plain.mem.w8(0x41B51D, recall)
        prime()
        require(plain.run(key) == R.key_usable(raw), ('key', raw, started))
        for dialog_open, recall in ((0, 0), (1, 0), (0, 3)):
            prime(dialog_open, recall)
            plain.run(action)
            want = R.use_trigger(raw, started, dialog_open, recall)
            got_entrance = plain.mem.cstr(N.N.G_ENTRANCE_NAME, 32) == entrance
            require(got_entrance == want['entrance'], ('entrance', raw, started))
            require(('missionMenu_open' in plain.stubs()) == want['menu'], ('menu', raw, started, dialog_open))
            require(('hud_showHelpMessage' in plain.stubs()) == want['warn'], ('warn', raw, started))
            # HSV-4a: the warning queues exactly one deferred call, to K.poll
            require(plain.named('addDeferedCall') == ([k_ids['K.poll']] if want['warn'] else []),
                    ('deferred', raw, started))
            require(not [r for r in regions(plain.written()) if isinstance(r, tuple) and r[0] in ('mission', 'quest', 'record')],
                    'trigger leaves the player record')
            cases += 1
            if want['warn']:
                # run the queued K.poll on the same loaded script, as the Script task would
                for paused in ((0,) * 10, (0, 1, 1, 1) + (0,) * 8):
                    mem = plain.mem
                    for address in (G_PAUSED, G_JUMPGATE_TRAVEL):
                        mem.w32(address, 0)
                    mem.w8(G_CUTSCENE_ACTIVE, 0)
                    calls = []
                    for flag in paused:
                        mem.w32(G_PAUSED, flag)
                        plain.run(k_ids['K.poll'])
                        natives = [n for n, _c in plain.natives]
                        require(plain.named('addDeferedCall') == [k_ids['K.poll']], 'K.poll re-queues')
                        require(natives.count('gamePaused') == 1, 'K.poll tests the pause')
                        calls.append(('activateMissionMenu' in natives, 'missionMenu_open' in plain.stubs()))
                        require(not [r for r in regions(plain.written()) if isinstance(r, tuple)
                                     and r[0] in ('mission', 'quest', 'record')],
                                'K.poll leaves the player record')
                    at = R.warn_poll_call(paused)
                    opens = not dialog_open and not recall
                    require([c[0] for c in calls] == [i == at for i in range(len(paused))],
                            ('poll call', raw, started, paused))
                    require([c[1] for c in calls] == [i == at and opens for i in range(len(paused))],
                            ('poll menu', raw, started, paused, dialog_open, recall))
                    require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'ENTRANCE-SENTINEL', 'K.poll: no entrance')
                    mem.w32(G_PAUSED, 0)
                    plain.run(action)                    # a new warning restarts the count
                    poll_cases += 1
        prime()
        fired = 0
        for _repeat in range(2):
            plain.run(rect)
            got = sum(1 for n, c in plain.natives if n == 'trigger')
            require(got == R.walk_in(raw, started, fired), ('walk-in', raw, started, fired))
            if got:
                # HSV-4b: trigger(ring record's name, 0), two argument cells
                (cells, argc), = [(c, k) for (n, c), k in zip(plain.natives, plain.argc) if n == 'trigger']
                require(argc == 2 and script.pool.get(cells[0]) == rings['name'] and cells[1] == 0,
                        ('trigger args', argc, cells[1]))
            fired = fired or got
            cases += 1
    plain.reset([0] * 13)
    plain.run(ring)
    require([c[1] for n, c in plain.natives if n == 'autoPropSetState'] == [2], 'ring loop state')
    print('%s: PushTrigger nethostonly=%s radius=%s; key %#x -> K.lock %#x, action %#x -> K.use %#x '
          '(internal call K.warn %#x, callScript K.help %#x, which queues K.poll %#x), rect %#x -> '
          'K.walk %#x (internal calls K.warn, K.lock) PASS'
          % (hub, push['nethostonly'], push['radius'], key, k_ids['K.lock'], action, k_ids['K.use'],
             k_ids['K.warn'], k_ids['K.help'], k_ids['K.poll'], rect, k_ids['K.walk']))
    print('%s: PushTrigger key, use (x dialog open / recall) and walk-in one-shot over %d states, '
          '%d cases; warning: one addDeferedCall to K.poll, which re-queues itself and calls '
          'activateMissionMenu on its %dth unpaused run (%d sequences of 10 or 12 runs, no entrance '
          'write); walk-in trigger(ring name, 0); ring action state 2 PASS'
          % (hub, len(states), cases + 1, R.WARN_POLL_RUNS, poll_cases))


# ---------------------------------------------------------------------------------------
# 7. The only other writer of the hubs' mana-restore flag (neutral id L-INN)
# ---------------------------------------------------------------------------------------
def check_inn(elf, scripts, others):
    hub = scripts['hub']
    _start, _current, _store, mana, _first, _items = start_sites(hub)
    require(start_sites(scripts['hub2'])[3] == mana, 'same flag in both hubs')
    writers = []
    for key, image in sorted(others.items()):           # every script lump of every other GOB
        script = Script(image)
        if mana in script.pool.values():
            writers.append(script)
    gobs = {label for label, _lump in others}
    require(len(writers) == 1, ('one other script names the flag', len(writers)))
    inn = writers[0]
    gold = sorted(n for n in set(inn.natives) if 'gold' in n.lower())
    sets = [(site, args) for site, n, args in inn.sites
            if n == 'setv' and args and inn.pool.get(args[0]) == mana]
    require(len(sets) == 1 and sets[0][1][1] == 1, 'one literal set to 1')
    require(not [1 for _s, n, a in inn.sites if n == 'getv' and a and inn.pool.get(a[0]) == mana],
            'never read there')
    require('zeroPlayerMana' in inn.natives and 'refillPlayerMana' not in inn.natives, 'zeroes only')
    worlds = sorted({inn.pool.get(a[0]) for _s, n, a in inn.sites if n == 'newWorld' and a} &
                    {'hub', 'hub2'})
    require(worlds == ['hub', 'hub2'], 'returns to either hub')
    owner = max(off for off, _n in inn.entries if off <= sets[0][0])
    for seed in (20973, 7):
        plain = Plain(elf, inn, seed)
        plain.reset([0] * 13)
        plain.run(owner, keep_seed=False)          # this entry draws the shared seed
        require(plain.getv(mana) == 1, 'the entry sets the flag')
        drew = plain.mem.u32(N.N.G_RAND_SEED) != seed
    print('L-INN: %d script lumps in %d other archives scanned; the only one naming the hubs\' '
          'mana flag; one literal store of 1 at site %#x in public %#x, executed at both seeds; '
          'zeroPlayerMana present, refill absent; newWorld to both hubs; entry draws the shared '
          'seed: %s; gold natives imported: %s PASS'
          % (len(others), len(gobs), sets[0][0], owner, drew, ', '.join(gold) or 'none'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--data', help='the disc BG/DATA directory')
    parser.add_argument('--iso', help='or the disc image')
    parser.add_argument('--seed', type=int, action='append', dest='seeds')
    args = parser.parse_args()
    with open(args.elf, 'rb') as handle:
        require(hashlib.sha256(handle.read()).hexdigest() == ELF_SHA256, 'executable')
    hubs, others = read_archives(args.data, args.iso)
    scripts = {hub: Script(files['script.scr']) for hub, files in hubs.items()}
    check_structure(hubs, scripts)
    check_inn(args.elf, scripts, others)
    mu = load_probe_module()
    for seed in (args.seeds or [20973, 7]):
        rng = random.Random(seed)
        for hub in ('hub', 'hub2'):
            plain = Plain(args.elf, scripts[hub], seed)
            names, intro_name = check_conditions(plain, hub, rng)
            check_actions(plain, hub)
            check_entry(plain, hub)
            check_dedupe(plain, hub)
            check_travel(plain, hub, hubs[hub], names, rng)
            check_conversations(mu, args.elf, hubs, scripts, hub, names, intro_name, seed)
        print('PASS seed %d' % seed)
    print('PASS: hub services, %d checks, 0 mismatches' % TOTAL['checks'])


if __name__ == '__main__':
    main()
