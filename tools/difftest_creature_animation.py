#!/usr/bin/env python3
"""Synthetic role/resource, draw-transform and event writes vs original instructions.

Usage: python3 tools/difftest_creature_animation.py local/SLUS_209.73
Draw test stops at 0x10b130 before rendering. Role properties, resource lookup
and ancestry are explicit stubs; no runtime/game/visual result is claimed.
"""
import hashlib
import sys
import ref_core as C
import ref_creature as R
import ref_creature_animation as V
from ee_emu import EE

EXPECTED='292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def run(path):
    with open(path,'rb') as f:
        if hashlib.sha256(f.read()).hexdigest()!=EXPECTED:
            raise ValueError('wrong executable revision')
    ee=EE(path); ee.mem.map(0x1000,0x10000)
    C.set_fpu('ps2')
    for case in range(16):
        m=R.Memory()
        for off,val in ((0x10,17),(0x14,-31),(0x18,999),(0x3c,11),
                        (0xdc,(case+1)/4),(0xe0,0 if case%2 else 3)):
            m.poke(0x1000+off,4,C.f32(val))
        m.poke(0x1038,2,case*4096)
        ee.mem.write(0x1000,bytes(0x10000))
        for a,b in m.bytes.items(): ee.mem.store(a,1,b)
        ee.r[4]=0x1000; ee.r[29]=EE.STACK_HI-0x100
        ee.run(start=0x10b048,until=(0x10b130,))
        matrix=[ee.mem.load(ee.r[29]+0x10+4*k,4) for k in range(12)]
        if matrix!=V.creature_draw_matrix(m,0x1000):
            raise AssertionError('draw matrix case %d' % case)

    def read(p):
        out=bytearray()
        while ee.mem.load(p,1):
            out.append(ee.mem.load(p,1)); p+=1
        return bytes(out)
    def put(p,s): ee.mem.write(p,s+b'\0')
    for case in range(8):
        npc=bool(case&1)
        ee.mem.store(0x1048,4,0x5000); ee.mem.store(0x5004,4,0x8000)
        ee.mem.store(0x1024,4,0x2000); ee.mem.store(0x2000,4,0x2200)
        put(0x2200,b'ordinary'); put(0x13c8,b'embedded'); put(0x2300,b'idle')
        props={}
        if case&2: props[b'idlename']=b'' if case&4 else b'explicit'
        elif case&4: props[b'name']=b'actor'
        addresses={k:0x3000+128*i for i,k in enumerate(props)}
        for k,p in addresses.items(): put(p,props[k])
        actual=[]
        def prop(e):
            key=read(e.r[5]&0xffffffff); actual.append(('property',key))
            return addresses.get(key,0)
        def resolve(e):
            name=read(e.r[5]&0xffffffff); lump=e.r[4]&0xffffffff
            actual.append(('resource',lump,name))
            return 0x7000 if name==b'idle.anm' else 0
        ee.stub(0x8000,ret=0x9000)
        ee.stub(0x3b1250,ret=int(npc))
        ee.stub(0x14f4c0,function=prop); ee.stub(0x17365c,function=resolve)
        got=ee.call(0x160928,0x1000,0x2300,sp=EE.STACK_HI-0x100)
        expected=[]
        def rp(k): expected.append(('property',k)); return props.get(k)
        def rr(l,n):
            expected.append(('resource',l,n)); return 0x7000 if n==b'idle.anm' else 0
        want=V.find_role_anim(0x13c8 if npc else 0x2200,b'idle',rp,rr)
        if want!=got or expected!=actual:
            raise AssertionError('role lookup case %d' % case)
    m=R.Memory(); model=R.Model(m)
    m.poke(0x1024,4,0x2000); m.poke(0x201c,4,0x3000)
    for a,b in m.bytes.items(): ee.mem.store(a,1,b)
    times=list(map(C.f32,(.25,.5,.75,1))); masks=[1,2,4,8]
    for i,t in enumerate(times): ee.f[12+i]=t
    ee.reset_log(); ee.call(0x118378,0x1000,3,*masks)
    V.set_class_events(model,0x1000,3,times,masks)
    if [(a,n,v) for _,a,n,v in ee.writes]!=model.writes:
        raise AssertionError('event store order')
    print('PASS 16 draw prefixes, 8 role lookups, 1 shared-event writer; exact raw results/order')
    print('Stubs: role ancestry/properties/resources. No rendered-game claim.')


if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit(__doc__)
    run(sys.argv[1])
