#!/usr/bin/env python3
"""Compare bounded death control branches with US v2.00 in tools/ee_emu.py.

  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_death_flow.py \
      /path/to/SLUS_209.73 --seed 20973

Each case calls one original function on scripted state. External services are
recording stubs; no full game, animation, save load or card I/O is executed.
"""
import argparse
import hashlib
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ee_emu import EE
from ref_death_flow import check_all_dead, death_task

PLAYER_BASE = 0x4D8AF0
PLAYER_SIZE = 0x4C30
TIMERS = 0x4F84A8
PHASE = 0x86AF50
EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def fbits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def signed16(x):
    return x - 0x10000 if x & 0x8000 else x


def common(elf):
    e = EE(elf)
    e.mem.auto_map = True
    return e


def check_case(elf, state):
    e = common(elf)
    m = e.mem
    m.w8(0x44FCD0, state['cutscene'])
    m.w32(0x4F85B0, state['loaded'])
    m.w32(0x4F7120, state['pvp_b'])
    m.w32(0x4F8420, state['alive'])
    m.w32(0x4D8AE0, state['players'])
    m.w8(0x402791, state['network'])
    m.w32(0x41B4F4, state['paused'])
    m.w32(0x41B4FC, state['menu_lockout'])
    m.w16(0x4F7194, state['wipe_timer'])
    for i in range(state['players']):
        m.w32(PLAYER_BASE + PLAYER_SIZE * i + 0xAC, fbits(state['hp'][i]))
        m.w16(TIMERS + 2 * i, state['timers'][i])
    calls = []
    def hook(name, ret=0):
        def call(emu):
            calls.append((name,) if name in ('game_isFrozen', 'net_fewerThanTwoActive')
                         else (name, emu.r[4] & 0xffffffff))
            return ret
        return call
    for addr, name, ret in (
        (0x1EBDF8, 'game_isFrozen', state['frozen']),
        (0x13DD88, 'net_fewerThanTwoActive', state['fewer_two']),
        (0x1EB000, 'net_closeLocalMenus', 0),
        (0x1EBD48, 'deathTask_schedule', 0),
        (0x305784, 'arena_respawnPlayer', 0),
    ):
        e.stub(addr, function=hook(name, ret))
    e.call(0x1E7438)
    got = dict(state)
    got['calls'] = calls
    got['menu_lockout'] = m.u32(0x41B4FC)
    got['wipe_timer'] = signed16(m.u16(0x4F7194))
    got['timers'] = [signed16(m.u16(TIMERS + 2*i)) for i in range(state['players'])]
    return got


def task_case(elf, state):
    e = common(elf)
    m = e.mem
    m.w8(PHASE, state['phase'])
    m.w8(PHASE + 1, state['force_network'])
    m.w32(0x4F712C, state['alternate'])
    m.w8(0x402791, state['network'])
    m.w32(0x44FD6C, state['game_flag'])
    m.w32(0x4D8AE0, len(state['hp']))
    m.w32(0x4F8420, state['alive'])
    m.write(0x44FE18, state['level'].encode() + b'\0')
    m.write(0x41B6D0, state['pending'].encode() + b'\0')
    for i, (hp, max_hp) in enumerate(zip(state['hp'], state['max_hp'])):
        m.w32(PLAYER_BASE + PLAYER_SIZE*i + 0xAC, fbits(hp))
        m.w32(PLAYER_BASE + PLAYER_SIZE*i + 0xB0, fbits(max_hp))
    calls = []
    def record(name, ret=0):
        def call(emu):
            calls.append((name, emu.r[4] & 0xffffffff)
                         if name == 'hud_stepFade' else (name,))
            return ret
        return call
    e.stub(0x1DF5EC, function=record('hud_stepFade', state['fade']))
    e.stub(0x217D30, function=record('save_findAct', state['act']))
    e.stub(0x22266C, function=record('save_reload'))
    e.stub(0x19E664, function=record('task_remove'))
    e.stub(0x1EC0F0, function=record('level_getQualifiedName'))
    current_name = e.alloc(16)
    m.write(current_name, b'valor\0')
    e.stub(0x222688, function=record('level_currentName', current_name))
    e.stub(0x3B8534, function=record('libc_strcmp', 0 if state['names_match'] else 1))
    def copy(emu):
        dst, src = emu.r[4] & 0xffffffff, emu.r[5] & 0xffffffff
        m.write(dst, m.cstr(src).encode() + b'\0')
        return dst
    e.stub(0x3B868C, function=copy)
    e.call(0x1E75E8)
    got = dict(state)
    got['calls'] = calls
    got['phase'] = m.u8(PHASE)
    got['network'] = m.u8(0x402791)
    got['game_flag'] = m.u32(0x44FD6C)
    got['pending'] = m.cstr(0x41B6D0)
    got['request'] = m.u8(0x41B720)
    got['hp'] = [struct.unpack('<f', struct.pack('<I', m.u32(
        PLAYER_BASE + PLAYER_SIZE*i + 0xAC)))[0] for i in range(len(state['hp']))]
    return got


def cases(seed):
    r = random.Random(seed)
    for players in (1, 2, 4):
        for index in range(36):
            hp = [r.choice((0.0, 0.0, 18.0)) for _ in range(players)]
            alive = sum(x > 0 for x in hp)
            yield dict(cutscene=int(index % 13 == 0), loaded=int(index % 11 != 0),
                       pvp_b=int(index % 9 == 0), alive=alive, players=players,
                       frozen=int(index % 17 == 0), network=int(index % 3 == 0),
                       fewer_two=int(index % 7 == 0), paused=int(index % 5 == 0),
                       menu_lockout=7, wipe_timer=r.choice((0, 1, 2, 240)),
                       hp=hp, timers=[r.choice((0, 1, 2, 240)) for _ in hp])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('elf')
    p.add_argument('--seed', type=int, default=20973)
    a = p.parse_args()
    if hashlib.sha256(Path(a.elf).read_bytes()).hexdigest() != EXPECTED_SHA256:
        p.error('requires SLUS_209.73 US v2.00 (SHA-256 mismatch)')
    checked = 0
    for state in cases(a.seed):
        expected, actual = check_all_dead(state), check_case(a.elf, state)
        if expected != actual:
            raise AssertionError(('check_all_dead', checked, expected, actual))
        checked += 1
    task_checked = 0
    for phase in (0, 1, 2, 10):
        for alternate in (0, 1):
            for fade in (0, 0x80):
                for act in (-1, 0):
                    for force_network in (0, 1):
                        if phase == 1 and alternate:
                            continue
                        state = dict(phase=phase, alternate=alternate, fade=fade,
                                     act=act, force_network=force_network, network=0,
                                     level='valor', pending='hub' if phase == 2 and act == 0 else '',
                                     request=0, game_flag=0,
                                     hp=[0.0, 0.0], max_hp=[32.0, 48.0],
                                     alive=int(act == 0), names_match=int(fade == 0x80))
                        expected, actual = death_task(state), task_case(a.elf, state)
                        if expected != actual:
                            raise AssertionError(('death_task', task_checked, expected, actual))
                        task_checked += 1
    print(f'PASS seed={a.seed} check_all_dead={checked} death_task={task_checked}')


if __name__ == '__main__':
    main()
