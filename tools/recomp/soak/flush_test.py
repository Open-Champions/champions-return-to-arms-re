#!/usr/bin/env python3
"""flush_test.py - net_flushBeforeLoad 0x132db0 in the function-level interpreter, as shipped,
with the section "flush before a level load waits for the peers' tick" as it is in the patch
file, and with the replacement proposed in tools/recomp/soak/proposed-flush.pnach.

  python3 tools/recomp/soak/flush_test.py [path/to/SLUS_209.73]

net_main 0x132e90 and the vertical-blank wait 0x19d028 are stubbed; the number of net_main
calls is the number of passes.  PASS/FAIL lines as tools/ee_tests.py prints them.  Callees
are stubbed and there is no second machine: this shows what the loop does on a given state,
not that the state occurs (docs/issues/native-soak.md has the runs).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ee_emu import EE  # noqa: E402

FLUSH, NET_MAIN, VSYNC = 0x132DB0, 0x132E90, 0x19D028
G_PEERS, PEER, G_NUMPEERS, G_NETFRAME = 0x5BF838, 0x44E0, 0x4027C4, 0x4027AC
SHIPPED = [(0x132DFC, 0x2A060010), (0x132E28, 0x8C82FFF8)]
PROPOSED = [(0x132DF8, 0x1840001D), (0x132DFC, 0x2A060010), (0x132E28, 0x8C82FFF8)]
FAILED = []


def check(ident, ok, text):
    print('%s  %-4s %s' % ('PASS' if ok else 'FAIL', ident, text))
    if not ok:
        FAILED.append(ident)


def passes(elf, words, peers, net_frame, acked, tick, tick_after=None):
    """Passes made.  peers: number of peers (slot 0 local); acked / tick: the remote peers'
    +0x44c0 and +0x44c8; tick_after=(n, value): after n passes the remotes report `value`."""
    emu = EE(elf)
    for address, word in words:
        emu.patch(address, word)
    for a in (G_NUMPEERS, G_NETFRAME, 0x44FD6C):
        emu.mem.map(a & ~0xFFF, 0x1000)
    emu.mem.map(G_PEERS & ~0xFFF, 4 * PEER + 0x2000)
    emu.mem.w32(G_NUMPEERS, peers)
    emu.mem.w32(G_NETFRAME, net_frame)
    for n in range(4):
        base = G_PEERS + n * PEER
        emu.mem.w8(base + 0x44D4, 1 if n == 0 else 0)
        emu.mem.w8(base + 0x44D5, 0)
        emu.mem.w32(base + 0x44C0, acked)
        emu.mem.w32(base + 0x44C8, tick)
    count = [0]

    def net_main(e):
        count[0] += 1
        if tick_after and count[0] >= tick_after[0]:
            for n in range(1, 4):
                e.mem.w32(G_PEERS + n * PEER + 0x44C8, tick_after[1])
    emu.stub(NET_MAIN, function=net_main)
    emu.stub(VSYNC)
    emu.call(FLUSH, max_steps=200000)
    return count[0]


def main(argv):
    elf = argv[0] if argv else os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.isfile(elf):
        print('no executable at %s (bring your own SLUS_209.73)' % elf)
        return 0
    # 1. no peers: the state of the developer LAN start's first level change (before net_gameInit)
    check('F1', passes(elf, [], 0, 0, 0, 0) == 0, 'as shipped, no peers: no pass')
    check('F2', passes(elf, SHIPPED, 0, 0, 0, 0) == 16, 'the section as it is, no peers: 16 passes of net_main (the fault of finding 1)')
    check('F3', passes(elf, PROPOSED, 0, 0, 0, 0) == 0, 'the proposed section, no peers: no pass')
    # 2. two peers, nothing to wait for
    check('F4', passes(elf, [], 2, 700, 700, 700) == 0, 'as shipped, own input acknowledged: no pass')
    check('F5', passes(elf, PROPOSED, 2, 700, 700, 700) == 16, 'proposed, the peer has reported the tick: the 16-pass minimum')
    check('F6', passes(elf, SHIPPED, 2, 700, 700, 700) == 16, 'the section as it is: the same 16')
    # 3. the peer never gets there: the 121-pass limit stays
    check('F7', passes(elf, [], 2, 700, 698, 700) == 121, 'as shipped, input never acknowledged: 121 passes')
    check('F8', passes(elf, PROPOSED, 2, 700, 700, 699) == 121, 'proposed, the peer never reports the tick: 121 passes')
    check('F9', passes(elf, PROPOSED, 2, 700, 698, 700) == 16, 'proposed: an unacknowledged input frame no longer holds the machine')
    # 4. the peer reports the tick after n passes
    check('F10', passes(elf, PROPOSED, 2, 700, 700, 699, tick_after=(5, 700)) == 16, 'proposed, tick reported in pass 5: 16 passes')
    check('F11', passes(elf, PROPOSED, 2, 700, 700, 699, tick_after=(40, 700)) == 40, 'proposed, tick reported in pass 40: 40 passes')
    check('F12', passes(elf, PROPOSED, 4, 700, 700, 699, tick_after=(40, 700)) == 40, 'proposed, four peers: 40 passes')
    check('F13', passes(elf, PROPOSED, 2, 1, 1, 0, tick_after=(3, 1)) == 16, 'proposed, the first load of a lobby-launched game (tick 1, peers set): 16 passes')
    print('%d failed' % len(FAILED))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
