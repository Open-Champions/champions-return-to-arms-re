#!/usr/bin/env python3
"""Archive open and the in-range prompt for mission 2.

game_loadLevel is run twice. One fixture enters game_clearLevel. The other
does not re-enter it, and stops at the SIF DMA whose result the caller reads.
The archive itself is opened by gob_loadAll. Private bytes stay under the
disc directory passed on the command line.
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]

from difftest_mission2 import SHA256  # noqa: E402
from ee_emu import EE, EmuError, MemoryFault  # noqa: E402

POOL_INIT, POOL_NEW = 0x14FCD8, 0x14FDB8
HANDLE_INIT, OBJECT_CTOR = 0x1A17D0, 0x14CB10
PUSH, TRIGGER, PORTAL, NPC = 0x1EC900, 0x1ECDF4, 0x27C694, 0x29DF04
PLAYER_INIT, INTERACT = 0x1B1D70, 0x1B2640
READ, ALLOC, REALLOC, FREE = 0x172AD0, 0x14FF88, 0x14FE80, 0x150198
FLUSH, STACK, GOB, LOAD = 0x352C60, 0x19D9F8, 0x1737D8, 0x1E55C0
FIND_EXT, PARTICLE = 0x171FD8, 0x18E648
CLEAR = 0x1E4E88
SEED, PLAYERS, FREE_HEAD = 0x404464, 0x4D8AF0, 0x864EA8
TEX_NAME, LUMP_COUNT, LUMPS = 0x44FE18, 0x41BF7C, 0x7B9480
EXT_WORLD, USE_MASK = 0x53DAA8, 0x41B9C0
PROMPT, USE = 0x1ECA94, 0x1ECC70
TERMINATE_RA = frozenset((
    0x17DE0C, 0x17E480, 0x17FE68, 0x31EF38,
    0x36782C, 0x368E2C, 0x3A02CC, 0x3A1270,
))


def cstr(mem, addr):
    out = bytearray()
    addr &= 0xFFFFFFFF
    while len(out) < 64:
        byte = mem.u8(addr)
        if byte == 0:
            break
        out.append(byte)
        addr += 1
    return bytes(out)


class Disc:
    def __init__(self, root):
        self.files = {}
        for path in Path(root).rglob('*'):
            if path.is_file():
                self.files.setdefault(path.name.lower(), []).append(path)
        self.reads = []

    def install(self, emu):
        disc = self

        def read(m):
            name = cstr(m.mem, m.r[4]).split(b';', 1)[0].decode('latin1').lower()
            dest = m.r[5] & 0xFFFFFFFF
            size = m.r[6] & 0xFFFFFFFF
            offset = m.r[7] & 0xFFFFFFFF
            hits = disc.files.get(name, [])
            disc.reads.append((name, size, offset, len(hits)))
            if len(hits) != 1:
                return 0
            with hits[0].open('rb') as handle:
                handle.seek(offset)
                data = handle.read(size)
            if data:
                m.mem.write(dest, data)
            return len(data)

        def allocate(m):
            size = m.r[4] & 0xFFFFFFFF
            if size == 0 or size > 0x2000000:
                return 0
            return m.alloc(size, align=256)

        emu.stub(READ, function=read, name='cd_readBlocking')
        emu.stub(ALLOC, function=allocate, name='mem_allocTagged')
        emu.stub(REALLOC, function=lambda m: m.r[4] & 0xFFFFFFFF, name='mem_realloc')
        emu.stub(FLUSH, ret=0, name='FlushCache')
        emu.stub(STACK, ret=0, name='dbg_checkStack')


def allow_diagnostic(emu):
    def handler(m):
        number = m.r[3] & 0xFFFFFFFF
        if number >= 0x80000000:
            number -= 0x100000000
        if number == 124 and (m.r[4] & 0xFFFFFFFF) == 0x10:
            m.r[2] = 0
            return
        ra = m.r[31] & 0xFFFFFFFF
        if number == 37 and ra in TERMINATE_RA:
            m.r[2] = 0
            return
        raise EmuError('SYSCALL pc=0x%08x v1=%d a0=0x%x ra=0x%08x' % (
            m.cur, number & 0xFFFFFFFF, m.r[4] & 0xFFFFFFFF, ra))
    emu.syscall_handler = handler


def boot(elf, disc, particles=False):
    emu = EE(elf)
    emu.record_writes = False
    emu.record_calls = False
    disc.install(emu)
    allow_diagnostic(emu)
    emu.call(POOL_INIT, max_steps=2000000)
    emu.call(HANDLE_INIT, max_steps=2000000)
    if particles:
        assert emu.call(PARTICLE, max_steps=5000000) & 0xFFFFFFFF == 2
    return emu


def construct(emu, address, size, pos, props):
    block = emu.call(POOL_NEW, size, max_steps=1000000) & 0xFFFFFFFF
    assert block
    emu.call(address, block, pos, 0, props, max_steps=8000000)
    return block


def constructors(elf, disc, seed):
    emu = boot(elf, disc)
    assert emu.mem.u32(FREE_HEAD) == 0x847268
    emu.mem.w32(SEED, seed)
    pos, props = emu.alloc(16), emu.alloc(4)
    block = construct(emu, OBJECT_CTOR, 0x80, pos, props)
    stepped = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    assert emu.mem.u32(SEED) == stepped
    assert emu.mem.u32(block + 0x44) == (stepped >> 16) & 0xFFFF
    flags = {}
    for name, address, size, expected in (
            ('push', PUSH, 0x4C, 0x10000B),
            ('trigger', TRIGGER, 0x70, 3),
            ('npc', NPC, 0x480, 0x01100028)):
        fresh = boot(elf, disc)
        body = construct(fresh, address, size, fresh.alloc(16), fresh.alloc(4))
        flags[name] = fresh.mem.u32(body + 0x0C)
        assert flags[name] == expected, (name, hex(flags[name]))
    portal = boot(elf, disc)
    block = portal.call(POOL_NEW, 0x164, max_steps=1000000) & 0xFFFFFFFF
    try:
        portal.call(PORTAL, block, portal.alloc(16), 0, portal.alloc(4), max_steps=8000000)
    except MemoryFault as fault:
        assert (fault.pc, fault.addr, fault.kind) == (0x17363C, 0, 'write'), fault
    else:
        raise AssertionError('portal constructor returned')
    return flags


def interact(elf, disc, seed):
    emu = boot(elf, disc)
    emu.mem.w32(SEED, seed)
    name, look = emu.alloc(8), emu.alloc(4)
    emu.mem.write(name, b'A\0')
    emu.call(PLAYER_INIT, 0, 0, name, look, 0, 1, 0, 0, max_steps=8000000)
    assert emu.mem.u32(PLAYERS + 0xAC) == 0x4E6E6B27
    pos, props = emu.alloc(16), emu.alloc(4)
    body = construct(emu, PUSH, 0x4C, pos, props)
    owner = construct(emu, OBJECT_CTOR, 0x590, pos, props)
    emu.mem.w32(PLAYERS + 0x43D8, owner)
    assert emu.mem.u32(body + 0x48) != 0
    assert emu.mem.u32(emu.mem.u32(body + 0x48) + 0x6C) == PROMPT
    assert emu.mem.u32(emu.mem.u32(body + 0x48) + 0x74) == USE
    seen = []

    def on_prompt(m):
        ra = m.r[31] & 0xFFFFFFFF

        def after(n, ra=ra):
            seen.append(n.r[2] & 0xFFFFFFFF)
            n.unhook(ra)

        m.hook(ra, after)

    emu.hook(PROMPT, on_prompt)
    pad = emu.alloc(0x80)
    emu.mem.w32(USE_MASK, 0x40)
    emu.mem.w32(pad + 8, 0x40)
    emu.mem.w32(pad + 0x0C, 0x40)
    emu.record_calls = True
    value = emu.call(INTERACT, owner, pad, 0, max_steps=3000000) & 0xFFFFFFFF
    targets = [call.target for call in emu.calls]
    assert 0x14A928 in targets
    assert PROMPT in targets
    assert USE not in targets
    assert seen == [1], seen
    assert value == 0x4D8AC0
    return value


def archive(elf, disc, seed):
    emu = boot(elf, disc)
    emu.mem.w32(SEED, seed)
    emu.mem.write(TEX_NAME, b'innovat1\0')
    name = emu.alloc(16)
    emu.mem.write(name, b'innovat1.gob\0')
    disc.reads.clear()
    emu.call(GOB, name, max_steps=20000000)
    assert disc.reads[0] == ('innovat1.gob', 0x800, 0, 1)
    assert ('innovat1.tex', 0x5000, 0, 1) in disc.reads
    assert all(hits == 1 for _name, _size, _offset, hits in disc.reads)
    assert emu.mem.u32(LUMP_COUNT) == 3
    level = 0
    for index in range(3):
        base = LUMPS + index * 0x28
        if cstr(emu.mem, base).lower() == b'innovat1.lmp':
            level = emu.mem.u32(base + 0x10)
    assert level
    found = emu.call(FIND_EXT, level, EXT_WORLD, 0, max_steps=2000000) & 0xFFFFFFFF
    assert found
    word = emu.mem.u32(found + 4)
    assert emu.mem.is_mapped(word, 4)
    return found, word


def loader_clear(elf, disc, seed):
    emu = boot(elf, disc, particles=True)
    emu.mem.w32(SEED, seed)
    text = emu.alloc(16)
    emu.mem.write(text, b'innovat1\0')
    try:
        emu.call(LOAD, text, max_steps=8000000)
    except MemoryFault as fault:
        assert (fault.pc, fault.addr, fault.size, fault.kind) == (
            0x179B30, 0x18, 2, 'write'), fault
        return fault.pc
    raise AssertionError('clear returned')


def loader_dma(elf, disc, seed):
    emu = boot(elf, disc)
    emu.stub(CLEAR, ret=0, name='clear')
    emu.stub(FREE, ret=0, name='mem_free')
    emu.mem.w32(SEED, seed)
    emu.mem.write(TEX_NAME, b'innovat1\0')
    text = emu.alloc(16)
    emu.mem.write(text, b'innovat1\0')
    disc.reads.clear()
    try:
        emu.call(LOAD, text, max_steps=8000000)
    except EmuError as error:
        assert 'pc=0x00352da4' in str(error) and 'v1=119' in str(error), error
        assert disc.reads == []
        return 0x352DA4
    raise AssertionError('loader passed the DMA')


def run(elf, root, seed):
    assert hashlib.sha256(Path(elf).read_bytes()).hexdigest() == SHA256
    disc = Disc(root)
    flags = constructors(elf, disc, seed)
    value = interact(elf, disc, seed)
    found, word = archive(elf, disc, seed)
    clear_pc = loader_clear(elf, disc, seed)
    dma_pc = loader_dma(elf, disc, seed)
    print('PASS seed=%d ctors=%s interact=0x%08x world=0x%08x word=0x%08x' % (
        seed, ','.join('%s:0x%x' % item for item in flags.items()), value, found, word))
    print('PASS seed=%d clear-stop=0x%08x dma-stop=0x%08x' % (seed, clear_pc, dma_pc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('disc')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.disc, args.seed)


if __name__ == '__main__':
    main()
