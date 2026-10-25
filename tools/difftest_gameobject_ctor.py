#!/usr/bin/env python3
"""Synthetic constructor integration against original instructions; explicit ELF.

python3 tools/difftest_gameobject_ctor.py local/SLUS_209.73
Resource lookup and paired allocation are matched deterministic callbacks.
Checks all fixture/output bytes and ordered stores except the normalized vector
copy and libc string-copy widths; their final bytes are still compared.
No game data is embedded or emitted. Wrong/missing input fails, never skips.
"""
import hashlib
import sys
import ref_core as C
import ref_creature as R
import ref_gameobject_ctor as G
import ref_skills_a as S
from ee_emu import EE

OBJ,POS,PROPS,OLD,STR=0x1000,0x1800,0x2000,0x2100,0x3000
BACK,NODE,NEXT,DEF=0x4000,0x4100,0x4200,0x7000
EXPECTED='292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def link(load,store,cell,head,obj):
    old=load(cell,4)
    for a,v in ((head,BACK),(BACK,0),(BACK+4,head),(BACK+8,NODE),(BACK+12,obj),
                (NODE,old),(NODE+4,cell),(NODE+8,BACK),(NODE+12,obj),(cell,NODE)):
        store(a,4,v)
    if old: store(old+4,4,NODE)


def run(path):
    with open(path,'rb') as f:
        if hashlib.sha256(f.read()).hexdigest()!=EXPECTED:
            raise ValueError('wrong executable revision')
    ee=EE(path); ee.mem.map(0x1000,0x10000)
    C.set_fpu('ps2')
    for case in range(64):
        m=R.Memory()
        def string(p,v):
            for i,c in enumerate(v+b'\0'): m.poke(p+i,1,c)
        string(S.S_HIDE,b'hide'); string(G.S_NAME,b'name')
        values=[b'name="Alpha"tail',b'Name=ignored',b'name=alpha',b'name=',b'hide=1']
        for i,v in enumerate(values[:case%6]):
            string(STR+128*i,v); m.poke(PROPS+4*i,4,STR+128*i)
        string(0x6000,b'hide=-2' if case&1 else b'hide=0')
        m.poke(OLD,4,0x6000)
        m.poke(OBJ+0x2c,4,OLD if case&2 else 0)
        m.poke(S.G_RAND_SEED,4,(case*0x712378+17)&0xffffffff)
        m.poke(S.G_LUMP_GENERATION,4,2)
        m.poke(DEF,4,0x7100); m.poke(DEF+4,4,2 if case&4 else 1)
        m.poke(DEF+8,4,0x7200); m.poke(DEF+16,4,0x7300)
        x=(-0.5,-1,-256.9,-257,16000,-16000,0,512)[case%8]
        pos=(C.f32(x),0,C.f32(3))
        for i,v in enumerate(pos): m.poke(POS+4*i,4,v)
        col=R.s32(C.to_int(pos[0])+0x3c00)>>8
        cell=S.G_GRID_A+4*(120*60+col) if 0<=col<120 else S.G_OFF_GRID
        m.poke(cell,4,NEXT if case&8 else 0)
        if cell!=S.G_OFF_GRID: m.poke(S.G_OFF_GRID,4,0x4300 if case&16 else 0)
        # Occupied collision/tombstone cases, and original quote stripping.
        string(0x6800,b'ALPHA')
        slot=G.O.name_hash(b'alpha')
        if case&32:
            m.poke(G.G_NAMES+4*slot,4,0x6800)
            m.poke(G.G_NAMED_OBJECTS+4*slot,4,0 if case&16 else 0x9999)
        ee.mem.write(0x1000,bytes(0x10000))
        ee.mem.write(S.G_GRID_A,bytes(G.G_NAME_COUNT+4-S.G_GRID_A))
        for a,b in m.bytes.items(): ee.mem.store(a,1,b)
        def original_link(e):
            link(e.mem.load,e.mem.store,*(e.r[i]&0xffffffff for i in (4,5,6)))
            return 0
        ee.stub(0x1a1738,function=original_link)
        ee.stub(0x17365c,function=lambda e:(e.r[5]+8)&0xffffffff)
        model=G.Model(m,{'handle_link':lambda *args:link(m.load,m.poke,*args),
                         'res_find':lambda lump,name:name+8})
        props=PROPS if case%6 else 0
        ee.reset_log()
        ee.call(0x14cb10,OBJ,POS,DEF,props)
        model.gameobject_ctor(OBJ,pos,DEF,props)
        for a,b in m.bytes.items():
            if b!=ee.mem.load(a,1):
                raise AssertionError('case %d: final byte mismatch at %x' % (case,a))
        # Also catch a store by the original that the model did not make.
        for _,a,n,_ in ee.writes:
            for p in range(a,a+n):
                if m.load(p,1)!=ee.mem.load(p,1):
                    raise AssertionError('case %d: extra original store at %x' % (case,p))
        def included(a):
            return not OBJ+0x10<=a<OBJ+0x1c and not STR<=a<STR+0x400
        actual=[(a,n,v) for _,a,n,v in ee.writes if included(a)]
        expected=[w for w in model.writes if included(w[0])]
        if actual!=expected:
            raise AssertionError('case %d: ordered-store mismatch' % case)
    print('PASS 64 synthetic constructor calls: final bytes and ordered stores; no skips')
    print('Services stubbed: resource lookup, paired allocation. Vector/string copy widths normalized.')


if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit(__doc__)
    run(sys.argv[1])
