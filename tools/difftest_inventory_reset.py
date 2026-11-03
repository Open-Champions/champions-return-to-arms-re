#!/usr/bin/env python3
"""difftest_inventory_reset.py - campaign inventory carry-over.

Compares the helpers added to tools/ref_quests.py with the original functions
in tools/ee_emu.py. Needs a local US v2.00 SLUS_209.73. Without it the script
says so and exits 0.

  python3 tools/difftest_inventory_reset.py local/SLUS_209.73 --seed 20973
  python3 tools/difftest_inventory_reset.py local/SLUS_209.73 --seed 7

player_recalcStats, player_resetIdleAnim and net_isLocalSlot are stubbed.
The act-change stretch is entered at 0x320f8c with r19 already 0x420000, which
is the base the instruction at 0x320ef0 writes. The level-store call before
that address is not part of this run. Existing quest vectors are not edited.
"""
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, MemoryFault, CpuTrap, UnimplementedInstruction  # noqa: E402
from ps2elf import Elf  # noqa: E402
import ref_quests as Q  # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'

G_PLAYERS = 0x4D8AF0
REC = 0x4C30
NUM = 0x4D8AE0
BAGS = 0x130
BAG = 0x1208
COUNT = 0x1200
ITEM = 0x48
EQUIP = 0x43F0
WEAPON = 0x4434
SECOND = 0x443C
ACTIVE = 0x4A7C
WCLASS = 0x4A86
QUEST = 0x41D0
QCOUNT = 0x43D0
MISSION = 0x4BBF
MEDAL = 0x4C0D
GOLD = 0xE4
EXP = 0x5C
LEVEL = 0x59
SHARE = 0x1C4FA8
REMOVE_ALL = 0x1BF600
FLAG39 = 0x1BE1D8
REMOVE = 0x1C1CB0
RECALC = 0x1B6458
IDLE = 0x1B2470
LOCAL = 0x13E150
CLEAR_LEVEL = 0x1E4E88
ARENA_WALK = 0x304E88
ARENA_WALK_END = 0x304EB4
ENTRY = 0x320F8C
STOP = 0x321024
MARK_STORE = 0x321020
PENDING = 0x41B6D0
LEVEL_NAME = 0x41B721
ACT = 0x88D3D4
LATCH = 0x4F8F28
FRONT = 0x41B510
VARS = 0x86DA80
RAND = 0x404464
MARK = 0x4F7118
ACT_CHANGED = 0x217F70
TASK = 0x19E5E8
CLEAR_BUF = 0x21F144
GET_ACT = 0x217EDC
RESET_DEST = 0x27DB00
CLEAR_Q = 0x1D3ADC
CLEAR_V = 0x1ED728
BIT = 1 << 39

CLEANUP = {TASK, CLEAR_BUF, GET_ACT, RESET_DEST, CLEAR_Q, FLAG39, CLEAR_V, REMOVE}

RESULTS = []


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def jal_sites(path, target):
    elf = Elf(path)
    base, offset, size = elf.text
    words = struct.unpack_from('<%dI' % (size // 4), elf.d, offset)
    sites = []
    for index, word in enumerate(words):
        if word >> 26 != 3:
            continue
        pc = base + index * 4
        dest = (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        if dest == target:
            sites.append(pc)
    return sites


def new_emu(seed):
    machine = EE(new_emu.path)
    machine.stub(RECALC, name='recalc')
    machine.stub(IDLE, name='idle')
    machine.stub(LOCAL, ret=0, name='local')
    machine.mem.w32(RAND, seed & 0xFFFFFFFF)
    machine.mem.w32(NUM, 4)
    machine.mem.write(G_PLAYERS, bytes(4 * REC))
    return machine


def plant(machine, record, slot, bag, index, obj, equip=None, weapon=None, second=False):
    rec = G_PLAYERS + slot * REC
    base = rec + BAGS + bag * BAG
    text = machine.alloc(48)
    machine.mem.write(text, obj.name.encode('ascii') + b'\0')
    defin = machine.alloc(64)
    machine.mem.w32(defin, text)
    machine.mem.w8(defin + 0x1C, obj.equip & 0xFF)
    machine.mem.w8(defin + 0x1D, bag)
    addr = base + index * ITEM
    machine.mem.w32(addr, defin)
    machine.mem.w16(addr + 4, obj.stack)
    machine.mem.w64(addr + 8, obj.flags)
    machine.mem.w16(addr + 0x22, obj.stamp)
    machine.mem.w32(base + COUNT, index + 1)
    if equip is not None:
        machine.mem.w32(rec + EQUIP + 4 * equip, addr)
        record.equip[equip] = obj
    if weapon is not None:
        machine.mem.w32(rec + WEAPON + 4 * weapon, addr)
        record.weapons[weapon] = obj
    if second:
        machine.mem.w32(rec + SECOND, addr)
        record.second = obj
    record.bags[bag].append(obj)
    return addr


def view(record):
    bags = []
    for bag in record.bags:
        bags.append([(item.name, item.flags, item.stack, item.stamp) for item in bag])

    def locate(obj):
        if obj is None:
            return None
        for bag_index, bag in enumerate(record.bags):
            for index, item in enumerate(bag):
                if item is obj:
                    return (bag_index, index)
        return ('gone', obj.name)

    return (bags, [locate(item) for item in record.equip],
            [locate(item) for item in record.weapons], locate(record.second),
            record.weapon_class)


def pull(machine, slot):
    mem = machine.mem
    rec = G_PLAYERS + slot * REC
    record = Q.ItemRecord()
    cells = {}
    for bag in range(3):
        base = rec + BAGS + bag * BAG
        count = mem.s32(base + COUNT)
        for index in range(max(0, count)):
            addr = base + index * ITEM
            defin = mem.u32(addr)
            name = mem.cstr(mem.u32(defin), 40) if defin else ''
            equip = mem.s8(defin + 0x1C) if defin else 0
            obj = Q.BagItem(name, mem.u64(addr + 8), mem.u16(addr + 4), equip, mem.u16(addr + 0x22))
            record.bags[bag].append(obj)
            cells[addr] = obj
    for slot_index in range(17):
        record.equip[slot_index] = cells.get(mem.u32(rec + EQUIP + 4 * slot_index))
    record.weapons[0] = cells.get(mem.u32(rec + WEAPON))
    record.weapons[1] = cells.get(mem.u32(rec + WEAPON + 4))
    record.second = cells.get(mem.u32(rec + SECOND))
    record.active = mem.s8(rec + ACTIVE)
    record.weapon_class = mem.u8(rec + WCLASS)
    return record


def scalars(machine, slot):
    rec = G_PLAYERS + slot * REC
    mem = machine.mem
    return {
        'gold': mem.s32(rec + GOLD),
        'exp': mem.s32(rec + EXP),
        'level': mem.u8(rec + LEVEL),
        'mission': mem.u8(rec + MISSION),
        'medal': mem.u8(rec + MEDAL),
        'quests': mem.s32(rec + QCOUNT),
        'title': bytes(mem.read(rec + QUEST, 9)),
    }


def call_ok(machine, addr, args):
    machine.reset_log()
    try:
        machine.call(addr, *args, max_steps=3000000)
    except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
        return '%s at %08x' % (type(exc).__name__, machine.pc)
    if machine.mem.u32(RAND) != new_emu.seed:
        return 'seed changed'
    return None


def check_callers(path):
    expected = {
        'share': (SHARE, [0x2221AC]),
        'remove all': (REMOVE_ALL, [0x304E9C]),
        'flag 39': (FLAG39, [0x220684, 0x320FFC]),
    }
    bad = []
    for name, (target, sites) in expected.items():
        got = jal_sites(path, target)
        if got != sites:
            bad.append((name, ['%08x' % site for site in got]))
    report('callers', not bad, 'three direct sites' if not bad else str(bad))


def check_flag39(seed):
    machine = new_emu(seed)
    record = Q.ItemRecord()
    drop = Q.BagItem('questgem', BIT, 1, 0, 0)
    sword = Q.BagItem('sword', 0, 1, 2, 1)
    keep = Q.BagItem('pickaxe', BIT, 1, 0, 0)
    plant(machine, record, 0, 0, 0, drop, equip=0, weapon=0)
    plant(machine, record, 0, 0, 1, sword, equip=2, weapon=1, second=True)
    plant(machine, record, 0, 2, 0, keep)
    machine.mem.w32(G_PLAYERS + GOLD, 77)
    machine.mem.w8(G_PLAYERS + MISSION, 3)
    fault = call_ok(machine, FLAG39, (0,))
    if fault:
        report('flag 39 fixups', False, fault)
        return
    Q.drop_unkept_flag39(record)
    same = view(pull(machine, 0)) == view(record)
    kept = scalars(machine, 0)
    report('flag 39 fixups', same and kept['gold'] == 77 and kept['mission'] == 3,
           'pointers and the kept name' if same else 'snapshot mismatch')


def check_share(seed):
    bad = []

    def run(title, build, source, players):
        machine = new_emu(seed)
        records = build(machine)
        machine.mem.w32(NUM, players)
        fault = call_ok(machine, SHARE, (source,))
        if fault:
            bad.append((title, fault))
            return
        Q.share_bag2_quest_items(records, source, players)
        for slot in range(4):
            if view(pull(machine, slot)) != view(records[slot]):
                bad.append((title, slot, view(pull(machine, slot)), view(records[slot])))
                return

    def both(machine):
        records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
        plant(machine, records[0], 0, 0, 0, Q.BagItem('bag0', BIT))
        plant(machine, records[0], 0, 2, 0, Q.BagItem('sword', 0, 1, 0, 0))
        plant(machine, records[0], 0, 2, 1, Q.BagItem('questgem', BIT, 4, 0, 1))
        plant(machine, records[1], 1, 0, 0, Q.BagItem('keepbag0', BIT))
        plant(machine, records[1], 1, 1, 0, Q.BagItem('keepbag1', BIT))
        plant(machine, records[1], 1, 2, 0, Q.BagItem('plain', 0, 1, 0, 0))
        plant(machine, records[1], 1, 2, 1, Q.BagItem('oldquest', BIT, 1, 0, 1), equip=0)
        plant(machine, records[2], 2, 2, 0, Q.BagItem('canary', BIT))
        return records

    def empty_source(machine):
        records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
        plant(machine, records[1], 1, 2, 0, Q.BagItem('oldquest', BIT))
        plant(machine, records[1], 1, 2, 1, Q.BagItem('plain', 0, 1, 0, 1))
        return records

    def bit38(machine):
        records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
        plant(machine, records[0], 0, 2, 0, Q.BagItem('questgem', 1 << 38))
        return records

    def from_slot1(machine):
        records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
        plant(machine, records[1], 1, 2, 0, Q.BagItem('pickaxe', BIT, 2))
        return records

    run('copy', both, 0, 2)
    run('empty source', empty_source, 0, 2)
    run('bit 38', bit38, 0, 2)
    run('from slot 1', from_slot1, 1, 3)
    report('share bag 2', not bad, '%d layouts' % 4 if not bad else str(bad[:2]))


def check_remove_all(seed):
    machine = new_emu(seed)
    record = Q.ItemRecord()
    weapon = Q.BagItem('sword', 0, 1, 0, 0)
    extra = Q.BagItem('shield', 0, 1, 3, 1)
    quest = Q.BagItem('questgem', BIT, 1, 5, 0)
    plant(machine, record, 0, 0, 0, weapon, equip=0, weapon=0)
    plant(machine, record, 0, 0, 1, extra)
    plant(machine, record, 0, 1, 0, quest, equip=5)
    plant(machine, record, 0, 2, 0, Q.BagItem('potion', 0))
    machine.mem.w32(G_PLAYERS + GOLD, 50)
    machine.mem.w8(G_PLAYERS + MISSION, 3)
    fault = call_ok(machine, REMOVE_ALL, (0,))
    if fault:
        report('remove all', False, fault)
        return
    Q.remove_all_bag_items(record)
    kept = scalars(machine, 0)
    same = view(pull(machine, 0)) == view(record)
    report('remove all', same and kept['gold'] == 50 and kept['mission'] == 3,
           'first cell of each non-empty bag' if same else 'snapshot mismatch')


def check_arena_walk(seed):
    machine = new_emu(seed)
    records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
    for slot in range(3):
        plant(machine, records[slot], slot, 0, 0, Q.BagItem('sword', 0, 1, 0, 0), equip=0, weapon=0)
        plant(machine, records[slot], slot, 0, 1, Q.BagItem('shield', 0, 1, 3, 1), equip=3)
    machine.mem.w32(NUM, 2)
    machine.mem.w32(G_PLAYERS + GOLD, 11)
    machine.mem.w32(G_PLAYERS + REC + GOLD, 22)
    machine.reset_log()
    machine.jump(ARENA_WALK)
    try:
        reason = machine.run(until={ARENA_WALK_END}, max_steps=3000000)
    except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
        report('arena slot walk', False, '%s at %08x' % (type(exc).__name__, machine.pc))
        return
    for slot in range(2):
        Q.remove_all_bag_items(records[slot])
    walks = [call.target for call in machine.calls].count(REMOVE_ALL)
    same = all(view(pull(machine, slot)) == view(records[slot]) for slot in range(3))
    report('arena slot walk',
           reason == 'stop' and walks == 2 and same and machine.mem.u32(RAND) == seed
           and machine.mem.s32(G_PLAYERS + GOLD) == 11
           and machine.mem.s32(G_PLAYERS + REC + GOLD) == 22,
           'slots below the player count, one pass each' if same else 'snapshot mismatch')


def load_acts(mem):
    count = mem.s32(0x4F8E7C)
    acts = []
    for act in range(count):
        ptr = mem.u32(0x4F8E48 + 4 * act)
        names = []
        for index in range(mem.s32(0x4F8E10 + 4 * act)):
            name_ptr = mem.u32(ptr + index * 8)
            names.append(mem.cstr(name_ptr, 32) if name_ptr else '')
        acts.append(names)
    return acts


def arm_campaign(machine, records):
    plant(machine, records[0], 0, 0, 0, Q.BagItem('sword', 0, 1, 2, 0), equip=2)
    plant(machine, records[0], 0, 0, 1, Q.BagItem('questgem', BIT, 1, 0, 1), equip=0, weapon=0)
    plant(machine, records[0], 0, 2, 0, Q.BagItem('pickaxe', BIT, 1, 0, 0), second=True)
    plant(machine, records[1], 1, 0, 0, Q.BagItem('othergem', BIT))
    plant(machine, records[2], 2, 0, 0, Q.BagItem('canary', BIT))
    mem = machine.mem
    mem.w32(NUM, 2)
    mem.w32(G_PLAYERS + GOLD, 1234)
    mem.w32(G_PLAYERS + EXP, 50)
    mem.w8(G_PLAYERS + LEVEL, 3)
    mem.w8(G_PLAYERS + MISSION, 3)
    mem.w8(G_PLAYERS + MEDAL, 1)
    mem.w32(G_PLAYERS + REC + GOLD, 9)
    mem.write(G_PLAYERS + QUEST, b'Aquest\0' + bytes(25))
    mem.w32(G_PLAYERS + QCOUNT, 1)
    mem.write(G_PLAYERS + REC + QUEST, b'Other\0' + bytes(26))
    mem.w32(G_PLAYERS + REC + QCOUNT, 1)
    mem.write(G_PLAYERS + 2 * REC + QUEST, b'Canary\0' + bytes(25))
    mem.w32(G_PLAYERS + 2 * REC + QCOUNT, 1)
    mem.write(VARS, bytes(64))
    mem.write(VARS, b'currentMission\0' + bytes([5]) + b'step\0' + bytes([9]))
    mem.w32(MARK, 0)


def check_transition(seed):
    sample = new_emu(seed)
    acts = load_acts(sample.mem)
    cases = (
        ('same act', 'strife', 'blood1', 0, 0, 0, 0),
        ('act change', 'innovat1', 'blood1', 0, 0, 0, 0),
        ('latch', 'innovat1', 'blood1', 0, 1, 0, 0),
        ('frontend', 'innovat1', 'blood1', 0, 0, 1, 0),
        ('death task', 'innovat1', 'blood1', 0, 0, 0, 1),
        ('from -1', 'blood1', '', -1, 0, 0, 0),
        ('hub2', 'hub2', 'hub', 0, 0, 0, 0),
    )
    bad = []
    for title, pending, current, act, latch, frontend, death in cases:
        machine = new_emu(seed)
        records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
        arm_campaign(machine, records)
        mem = machine.mem
        mem.write(PENDING, bytes(48))
        mem.write(LEVEL_NAME, bytes(48))
        if pending:
            mem.write(PENDING, pending.encode('ascii') + b'\0')
        if current:
            mem.write(LEVEL_NAME, current.encode('ascii') + b'\0')
        mem.w32(ACT, act & 0xFFFFFFFF)
        mem.w8(LATCH, latch)
        mem.w8(FRONT, frontend)
        if death:
            machine.stub(TASK, ret=1, name='death')
        machine.r[19] = 0x420000
        machine.reset_log()
        machine.jump(ENTRY)
        try:
            reason = machine.run(until={STOP}, max_steps=4000000)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append((title, type(exc).__name__, '%08x' % machine.pc))
            continue
        if reason != 'stop' or machine.mem.u32(RAND) != seed:
            bad.append((title, reason, 'seed' if machine.mem.u32(RAND) != seed else 'stop'))
            continue
        changed, new_act = (0, act)
        if not frontend:
            changed, new_act = Q.act_changed(pending, act, acts)
        cleanup = Q.cleanup_runs(changed, frontend, latch, death)
        if cleanup:
            for slot in range(2):
                Q.drop_unkept_flag39(records[slot])
        for slot in range(3):
            if view(pull(machine, slot)) != view(records[slot]):
                bad.append((title, 'bag', slot))
                break
        else:
            targets = {call.target for call in machine.calls}
            mark_writers = [pc for pc, addr, _size, _value in machine.writes if addr == MARK]
            got_act = machine.mem.s32(ACT)
            got_mark = machine.mem.u32(MARK)
            title0 = bytes(machine.mem.read(G_PLAYERS + QUEST, 9))
            title2 = bytes(machine.mem.read(G_PLAYERS + 2 * REC + QUEST, 9))
            var = bytes(machine.mem.read(VARS, 22))
            problems = []
            if got_act != new_act:
                problems.append(('act', got_act, new_act))
            if cleanup:
                if got_mark != 1 or mark_writers != [MARK_STORE]:
                    problems.append(('mark', got_mark, mark_writers))
                if machine.mem.s32(G_PLAYERS + QCOUNT) != 0 or title0 != b'NoQuests\0':
                    problems.append('quest0')
                if machine.mem.s32(G_PLAYERS + REC + QCOUNT) != 0:
                    problems.append('quest1')
                if not var.startswith(b'currentMission\0') or var[15] != 0 or var[21] != 0:
                    problems.append('vars')
                if not CLEANUP <= targets:
                    problems.append('calls')
            else:
                if got_mark != 0 or mark_writers:
                    problems.append('mark')
                if machine.mem.s32(G_PLAYERS + QCOUNT) != 1 or title0[:6] != b'Aquest':
                    problems.append('quest0')
                if var[15] != 5 or var[21] != 9:
                    problems.append('vars')
                if cleanup is False and CLEAR_Q in targets:
                    problems.append('cleared')
            if title2[:6] != b'Canary' or machine.mem.s32(G_PLAYERS + 2 * REC + QCOUNT) != 1:
                problems.append('canary quest')
            if machine.mem.s32(G_PLAYERS + GOLD) != 1234 or machine.mem.s32(G_PLAYERS + EXP) != 50:
                problems.append('progress')
            if machine.mem.u8(G_PLAYERS + MISSION) != 3 or machine.mem.u8(G_PLAYERS + MEDAL) != 1:
                problems.append('mission')
            if machine.mem.s32(G_PLAYERS + REC + GOLD) != 9:
                problems.append('gold1')
            if frontend and ACT_CHANGED in targets:
                problems.append('frontend asked')
            if (not frontend) and ACT_CHANGED not in targets:
                problems.append('no ask')
            if problems:
                bad.append((title, problems))
    report('act transition', not bad, '%d gates' % len(cases) if not bad else str(bad[:3]))


def check_clear_level(seed):
    machine = new_emu(seed)
    records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
    arm_campaign(machine, records)
    before = machine.mem.read(G_PLAYERS, 2 * REC)
    machine.follow = set()
    machine.reset_log()
    try:
        machine.call(CLEAR_LEVEL, 1, max_steps=2000000)
    except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
        report('clear level body', False, '%s at %08x' % (type(exc).__name__, machine.pc))
        return
    after = machine.mem.read(G_PLAYERS, 2 * REC)
    writes = [addr for _pc, addr, _size, _value in machine.writes
              if G_PLAYERS <= addr < G_PLAYERS + 2 * REC]
    report('clear level body', after == before and not writes and machine.mem.u32(RAND) == seed,
           'no record stores while callees are stubbed')


def main(argv):
    path = None
    seed = 20973
    args = argv[1:]
    index = 0
    while index < len(args):
        if args[index] == '--seed':
            seed = int(args[index + 1])
            index += 2
            continue
        path = args[index]
        index += 1
    if path is None or not os.path.exists(path):
        print('SKIP: SLUS_209.73 not found')
        return 0
    digest = __import__('hashlib').sha256(open(path, 'rb').read()).hexdigest()
    if digest != ELF_SHA:
        print('SKIP: executable digest is not the US v2.00 pin')
        return 0
    new_emu.path = path
    new_emu.seed = seed & 0xFFFFFFFF
    print('seed %d' % new_emu.seed)
    check_callers(path)
    check_flag39(new_emu.seed)
    check_share(new_emu.seed)
    check_remove_all(new_emu.seed)
    check_arena_walk(new_emu.seed)
    check_transition(new_emu.seed)
    check_clear_level(new_emu.seed)
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
