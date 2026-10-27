#!/usr/bin/env python3
"""Additive bounded terminal probes; private tables stay runtime-only, counts out."""
import argparse
import difftest_arena_live_scheduler as S
import difftest_arena_modes as D
import ref_arena_modes as R
from ref_core import ONE, TWO


def late_levels(path):
    cases = 0
    # Synthetic later states, not naturally earned clears. Stay below signed wrap.
    for network in (0, 1):
        for wave in (29, 44, 149, 299, 2999, 29999, 32765):
            e = S.fixture(path, 20973, network, 1)
            records, names, _ = S.tables(e)
            e.mem.w16(D.WAVE, wave)
            e.mem.w16(D.LEFT, 0)
            e.mem.w16(D.INTRO, 0xFFFF)
            e.mem.w16(D.INTER, R.intermission_limit(network))
            e.mem.w32(D.ENDF, 0)
            e.call(D.RUN)
            copies = D.calls(e, D.STRCPY)
            index = R.level_record_index(wave, len(records))
            assert len(copies) == 1
            assert copies[0].args[:2] == (D.PENDING, names[R.low_nibble(records[index][0])])
            assert e.mem.u32(D.ENDF) == 0 and e.mem.u32(D.MODE_B) == 1
            assert e.mem.u32(D.EXIT) == 0 and not D.calls(e, D.END)
            cases += 1
    return cases


def defeat_inputs(path):
    cases = 0
    writers = set()
    for players in range(1, 5):
        for network in (0, 1):
            for action in ('confirm', 'cancel'):
                e = S.fixture(path, 20973, network, players)
                e.mem.w16(D.INTRO, 0xFFFF)
                e.mem.w32(D.FRAME, 1)  # exclude the empty-grid gate
                for slot in range(players):
                    D.put_slot(e, slot, 0, 0xFFFF, 0, TWO)
                    e.mem.w32(D.PLAYERS + D.REC * slot + 0xAC, 0)
                    e.mem.w16(D.COUNTDOWN + 2 * slot, 0)
                e.call(D.RUN)
                assert e.mem.u32(D.ENDF) == 1
                assert e.mem.u16(D.INTER) == 0
                assert len(D.calls(e, D.END)) == 1 and not D.calls(e, D.END)[0].stubbed
                assert not D.calls(e, D.NEXT)
                writers.update(pc for pc, addr, size, value in e.writes
                               if addr == D.ENDF and value == 1)
                # Saved-record/restore/shutdown are service boundaries here.
                saved = e.alloc(0x4C20)
                e.mem.write(saved, bytes(0x4C20))
                e.stub(0x21837C, ret=saved)
                e.stub(0x304FB0, ret=0)
                e.follow.add(D.PICKER)
                e.mem.w32(D.CONFIRM, 0x100 if action == 'confirm' else 0)
                e.mem.w32(D.CANCEL, 0x100 if action == 'cancel' else 0)
                e.mem.w32(D.PAD0 + 0xC, 0x100)
                for fade in (0, ONE - 1):
                    e.mem.w32(D.FADE_W, fade)
                    e.call(D.RUN)
                    assert not D.calls(e, D.STRCPY) and not D.calls(e, 0x304FB0)
                    assert e.mem.u32(D.MODE_B) == 1 and e.mem.u32(D.EXIT) == 0
                e.mem.w32(D.FADE_W, ONE)
                e.call(D.RUN)
                if action == 'confirm':
                    assert len(D.calls(e, 0x304FB0)) == 1
                    assert len(D.calls(e, D.PICKER)) == 1
                    assert not D.calls(e, D.PICKER)[0].stubbed
                    names = D.names(e, D.NAMES_B)
                    record = bytes(e.mem.u8(D.RECIPES + j) for j in range(6))
                    assert D.calls(e, D.STRCPY)[0].args[:2] == (D.PENDING, names[R.low_nibble(record[0])])
                    assert e.mem.u32(D.MODE_B) == 1
                else:
                    assert e.mem.u32(D.MODE_B) == 0 and e.mem.u32(D.EXIT) == 1
                    assert not D.calls(e, D.STRCPY)
                cases += 1
    return cases, sorted(writers)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf')
    args = p.parse_args()
    print('PASS late-level cases=%d' % late_levels(args.elf))
    cases, writers = defeat_inputs(args.elf)
    print('PASS defeat/input cases=%d terminal-writer-addresses=%s' %
          (cases, ','.join('0x%x' % pc for pc in writers)))


if __name__ == '__main__':
    main()
