"""Synthetic world/tree/chunk/ripple inputs; no game data or proprietary bytes."""
import unittest
import ref_core as C
import ref_creature as R
import ref_water_services as W

WORLD,TREE,CHUNKS,PAYLOAD,GRID,HEIGHT=0x1000,0x2000,0x3000,0x5000,0x6000,0x9000
F=C.f32


def fixture(indices=(0,), grids=True):
    m=R.Memory(); model=W.Model(m)
    m.poke(WORLD+4,4,TREE); m.poke(WORLD+0x24,4,CHUNKS)
    m.poke(TREE,2,len(indices))
    for i,index in enumerate(indices):
        m.poke(TREE+2+2*i,2,index)
    for i in range(max(indices,default=0)+1):
        ch=CHUNKS+0x3c*i; payload=PAYLOAD+0x90*i
        m.poke(ch,4,payload); m.poke(ch+0x24,4,0x80)
        for k in range(3):
            m.poke(ch+8+4*k,4,F(-192 if k<2 else 0))
            m.poke(ch+0x14+4*k,4,F(192 if k<2 else 0))
        m.poke(payload+8,4,GRID if grids else 0)
    return model


class Query(unittest.TestCase):
    def test_inclusive_bounds_flag_filter_duplicates_and_capacity(self):
        model=fixture((0,1,0,2))
        model.mem.poke(CHUNKS+0x3c+0x24,4,0)
        got=model.query(WORLD,(F(192),0,0),(F(200),0,0),3,HEIGHT)
        self.assertEqual(got,[CHUNKS,CHUNKS])
        self.assertEqual(model.writes,[(HEIGHT,4,0),(HEIGHT,4,CHUNKS),
                                      (HEIGHT+4,4,CHUNKS),(HEIGHT+8,4,0)])
        self.assertEqual(model.query(WORLD,(F(193),0,0),(F(200),0,0),3),[])

    def test_internal_tree_visits_right_first(self):
        model=fixture((0,1))
        m=model.mem
        m.poke(TREE,2,0xc000)       # x split, both thresholds zero
        m.poke(TREE+2,4,0); m.poke(TREE+6,4,0)
        m.poke(TREE+18,2,3)        # right is TREE+24, left TREE+20
        for p,v in ((TREE+20,1),(TREE+22,0),(TREE+24,1),(TREE+26,1)):
            m.poke(p,2,v)
        self.assertEqual(model.query(WORLD,(0,0,0),(0,0,0),3),[CHUNKS+0x3c,CHUNKS])
        self.assertEqual(model.query(WORLD,(F(1),0,0),(F(2),0,0),3),[CHUNKS+0x3c])
        self.assertEqual(model.query(WORLD,(F(-2),0,0),(F(-1),0,0),3),[CHUNKS])

    def test_test_padding_height_and_first_hit(self):
        model=fixture((1,0))
        model.mem.poke(CHUNKS+0x3c+0x10,4,F(8))
        model.mem.poke(CHUNKS+0x3c+0x1c,4,F(8))
        model.mem.poke(HEIGHT,4,0x12345678)
        self.assertEqual(model.water_test(F(1),WORLD,(F(194),0,0),HEIGHT),1)
        self.assertEqual(model.u32(HEIGHT),F(8))
        self.assertEqual(model.water_test(F(1),WORLD,(F(195),0,0),HEIGHT),0)
        self.assertEqual(model.u32(HEIGHT),F(8))
        self.assertEqual(model.water_test(0,WORLD,(0,0,F(-61))),0)
        self.assertEqual(model.water_test(0,WORLD,(0,0,F(-60))),1)

    def test_empty_and_inert_internal(self):
        model=fixture(())
        self.assertEqual(model.water_test(F(12),WORLD,(0,0,0)),0)
        model.mem.poke(TREE,2,0x8000)
        self.assertEqual(model.query(WORLD,(0,0,0),(0,0,0),2),[])


class Disturb(unittest.TestCase):
    def test_center_falloff_and_order(self):
        model=fixture()
        self.assertEqual(model.water_disturb(F(100),F(12),WORLD,(0,0,0)),1)
        def at(x,y): return model.s16(GRID+0xa90+2*(32*x+y))
        self.assertEqual(at(16,16),100)
        self.assertEqual(at(16,15),0)  # truncated reciprocal puts this just outside
        self.assertEqual(len(model.writes),1)
        self.assertEqual([a for a,_,_ in model.writes],sorted(a for a,_,_ in model.writes))
        self.assertEqual(at(15,15),0)  # outside circle, not written

    def test_upper_clamp_lower_wrap_duplicate_count(self):
        model=fixture((0,0))
        center=GRID+0xa90+2*(32*16+16)
        model.mem.poke(center,2,32760)
        self.assertEqual(model.water_disturb(F(100),F(12),WORLD,(0,0,0)),2)
        self.assertEqual(model.s16(center),32767)
        model.mem.poke(center,2,-32760)
        model.water_disturb(F(-100),F(12),WORLD,(0,0,0))
        self.assertEqual(model.s16(center),32576)

    def test_no_grid_counts_cutskip_precedes_tree_and_15_limit(self):
        model=fixture(tuple([0]*20),grids=False)
        self.assertEqual(model.water_disturb(F(100),F(12),WORLD,(0,0,0)),15)
        self.assertEqual(model.writes,[])
        model.mem.poke(W.G_CUT_SKIP,1,0xff)
        self.assertEqual(model.water_disturb(F(100),0,0,(0,0,0)),0)

    def test_disturb_does_not_add_query_padding(self):
        model=fixture(grids=False)
        self.assertEqual(model.water_test(F(1),WORLD,(F(194),0,0)),1)
        self.assertEqual(model.water_disturb(F(100),F(1),WORLD,(F(194),0,0)),0)

    def test_masks_neighbors_untouched_and_non_square_uses_x_width(self):
        model=fixture()
        model.mem.poke(CHUNKS+0x18,4,F(384))  # Y width irrelevant to scale
        for i in range(0x90):
            if not 8<=i<12: model.mem.poke(PAYLOAD+i,1,0xa5)
        model.water_disturb(F(100),F(12),WORLD,(0,0,0))
        self.assertEqual(len(model.writes),1)
        self.assertTrue(all(GRID+0xa90<=a<GRID+0x1290 for a,_,_ in model.writes))


if __name__=='__main__':
    unittest.main()
