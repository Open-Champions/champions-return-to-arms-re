#!/usr/bin/env python3
"""Execute original water routines against synthetic worlds and the new model.

Usage: python3 tools/difftest_water_services.py local/SLUS_209.73
Reads only the user-supplied executable. No disc, network, renderer or game process.
Checks results and every ordered non-stack store, including redundant writes.
Missing/wrong input fails; no skipped case is counted. Prints aggregate results only.
"""
import hashlib
import random
import sys
import ref_core as C
import ref_water_services as W
import ref_creature as R
from ee_emu import EE

WORLD,TREE,CHUNKS,GRID,HEIGHT=0x1000,0x2000,0x3000,0x6000,0x9000


def fixture(indices, grids):
    m=R.Memory()
    m.poke(WORLD+4,4,TREE); m.poke(WORLD+0x24,4,CHUNKS)
    m.poke(TREE,2,len(indices))
    for i,index in enumerate(indices): m.poke(TREE+2+2*i,2,index)
    for i in range(3):
        ch=CHUNKS+0x3c*i; payload=0x5000+0x90*i
        m.poke(ch,4,payload); m.poke(ch+0x24,4,0x80)
        for k in range(3):
            m.poke(ch+8+4*k,4,C.f32(-192 if k<2 else 0))
            m.poke(ch+0x14+4*k,4,C.f32(192 if k<2 else 0))
        m.poke(payload+8,4,GRID if grids else 0)
    return W.Model(m)

EXPECTED='292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def run(path):
    with open(path,'rb') as f:
        if hashlib.sha256(f.read()).hexdigest()!=EXPECTED:
            raise ValueError('wrong executable revision')
    total=0
    for mode in ('ps2','ps2g1','chop','nearest'):
        C.set_fpu(mode)
        ee=EE(path,fpu_model=mode)
        ee.mem.map(0x1000,0x10000)
        rng=random.Random(20973)
        for case in range(48):
            for operation in ('test','disturb','query'):
                model=fixture(tuple(rng.randrange(3) for _ in range(rng.randrange(0,21))),
                              grids=case%7!=0)
                m=model.mem
                for i in range(3):
                    ch=CHUNKS+i*0x3c
                    # fixture might not have populated all three; leave unused alone.
                    if m.load(ch,4):
                        half=rng.choice((96,192,384))
                        m.poke(ch+8,4,C.f32(-half)); m.poke(ch+0x14,4,C.f32(half))
                        m.poke(ch+0x28,4,rng.randrange(-16,17))
                        m.poke(ch+0x2c,4,rng.randrange(-16,17))
                        m.poke(ch+0x24,4,0 if case%11==0 else 0x80)
                if case%6==0:
                    # Both-leaf internal split, right visited before left.
                    axis=(case//6)%3
                    split=case-24
                    for p,n,v in ((TREE,2,0xc000|axis),(TREE+2,4,split),(TREE+6,4,split),
                                  (TREE+18,2,3),(TREE+20,2,1),(TREE+22,2,0),
                                  (TREE+24,2,1),(TREE+26,2,1)):
                        m.poke(p,n,v)
                for i in range(1024):
                    m.poke(GRID+0xa90+2*i,2,rng.randrange(-32768,32768))
                m.poke(W.G_CUT_SKIP,1,1 if case%13==0 else 0)
                m.poke(HEIGHT,4,0x12345678)
                pos=tuple(C.f32(v) for v in (rng.randrange(-210,211),
                                           rng.randrange(-210,211),rng.randrange(-61,3)))
                radius=C.f32(rng.choice((1,12,24,64)))
                strength=C.f32(rng.choice((-40000,-100,300,1500,40000)))
                ee.mem.write(0x1000,bytes(0x10000))
                for a,b in m.bytes.items(): ee.mem.store(a,1,b)
                for k,v in enumerate(pos): ee.mem.store(0xa000+4*k,4,v)
                ee.reset_log()
                if operation=='test':
                    expected=model.water_test(radius,WORLD,pos,HEIGHT)
                    ee.f[12]=radius
                    got=ee.call(0x189438,WORLD,0xa000,HEIGHT)
                elif operation=='disturb':
                    expected=model.water_disturb(strength,radius,WORLD,pos)
                    ee.f[12],ee.f[13]=strength,radius
                    got=ee.call(0x189514,WORLD,0xa000)
                else:
                    lo=tuple(C.sub(v,radius) for v in pos)
                    hi=tuple(C.add(v,radius) for v in pos)
                    for k,v in enumerate(lo): ee.mem.store(0xa100+4*k,4,v)
                    for k,v in enumerate(hi): ee.mem.store(0xa200+4*k,4,v)
                    model.query(WORLD,lo,hi,16,HEIGHT)
                    ee.call(0x189240,WORLD,0xa100,0xa200,HEIGHT,16)
                    got=expected=0          # original query's return is unspecified
                actual=[(a,n,v) for _,a,n,v in ee.writes]
                if got!=expected or actual!=model.writes:
                    raise AssertionError('%s case %d %s: result/store mismatch' % (mode,case,operation))
                for a,n,v in model.writes:
                    if m.load(a,n)!=ee.mem.load(a,n):
                        raise AssertionError('final memory mismatch')
                total+=1
        print('PASS %s: 144 synthetic original/reference calls' % mode)
    C.set_fpu('ps2')
    print('PASS total %d calls; exact results and ordered stores; no skips' % total)


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit(__doc__)
    run(sys.argv[1])
