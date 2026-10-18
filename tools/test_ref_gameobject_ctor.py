"""Synthetic constructor contracts; no ELF, disc, extracted strings or assets."""
import unittest
import ref_core as C
import ref_creature as R
import ref_gameobject_ctor as G
import ref_skills_a as S

OBJ, PROPS, OLD, STR = 0x1000, 0x2000, 0x2100, 0x3000
BACK, NODE, NEXT = 0x4000, 0x4100, 0x4200


class Constructor(unittest.TestCase):
    def setUp(self):
        self.mem = R.Memory()
        self.model = G.Model(self.mem, {'handle_link': self.link})
        self.put_text(S.S_HIDE, b'hide')
        self.put_text(G.S_NAME, b'name')
        self.link_calls = []

    def put_text(self, p, text):
        for i, c in enumerate(text + b'\0'):
            self.mem.poke(p + i, 1, c)

    def properties(self, p, values, base=STR):
        for i, text in enumerate(values):
            self.put_text(base + 128 * i, text)
            self.mem.poke(p + 4 * i, 4, base + 128 * i)
        self.mem.poke(p + len(values) * 4, 4, 0)

    def link(self, cell, head, obj):
        # Synthetic paired-list service; original allocation is covered by ref_core.
        self.link_calls.append((cell, head, obj))
        old = self.mem.load(cell, 4)
        for p, v in ((head, BACK), (BACK, 0), (BACK+4, head), (BACK+8, NODE),
                     (BACK+12, obj), (NODE, old), (NODE+4, cell), (NODE+8, BACK),
                     (NODE+12, obj), (cell, NODE)):
            self.mem.poke(p, 4, v)
        if old:
            self.mem.poke(old+4, 4, NODE)

    def ctor(self, props=0, x=0.0, class_def=0):
        self.model.gameobject_ctor(OBJ, (C.f32(x), 0, 0), class_def, props)

    def test_prefix_and_seed_publication(self):
        self.mem.poke(S.G_RAND_SEED, 4, 0x12345678)
        self.ctor()
        expected = [(OBJ+i, 4, v) for i, v in
                    ((0,0),(4,0),(0x48,S.VT_GAMEOBJECT),(8,0),
                     (0x1c,S.F_24),(0x20,S.F_72),(0xc,0))]
        self.assertEqual(self.model.writes[:7], expected)
        seed = (0x12345678*0x19660d+0x3c6ef35f) & 0xffffffff
        self.assertEqual(self.model.writes[-3:], [(OBJ+0x2c,4,0),
                         (S.G_RAND_SEED,4,seed),(OBJ+0x44,4,seed>>16)])
        self.assertEqual(self.model.draws, 1)

    def test_incoming_hide_is_not_read(self):
        self.properties(PROPS, [b'hide=1'])
        self.ctor(PROPS)
        self.assertEqual(self.mem.load(S.G_OFF_GRID,4), 0)
        self.assertEqual(self.mem.load(OBJ+0xc,4), 0)
        self.assertEqual(self.mem.load(OBJ+0x2c,4), PROPS)

    def test_stale_hide_moves_existing_node_ordered(self):
        self.properties(OLD,[b'hide=-2'],base=0x6000)
        self.mem.poke(OBJ+0x2c,4,OLD)
        cell = S.G_GRID_A + 4*(60*120+60)
        self.mem.poke(cell,4,NEXT)
        self.mem.poke(S.G_OFF_GRID,4,0x4300)
        self.ctor()
        writes = [w for w in self.model.writes if w[0] in
                  (cell,NEXT+4,NODE,NODE+4,S.G_OFF_GRID,0x4304)]
        self.assertEqual(writes, [(cell,4,NEXT),(NEXT+4,4,cell),
                         (NODE+4,4,S.G_OFF_GRID),(NODE,4,0x4300),
                         (S.G_OFF_GRID,4,NODE),(0x4304,4,NODE)])
        self.assertEqual(self.mem.load(OBJ+8,4),BACK)
        self.assertEqual(self.mem.load(NODE+8,4),BACK)
        self.assertEqual(len(self.link_calls),1)

    def test_stale_hide_when_already_offgrid(self):
        self.properties(OLD,[b'hide=1'],base=0x6000)
        self.mem.poke(OBJ+0x2c,4,OLD)
        self.mem.poke(S.G_OFF_GRID,4,NEXT)
        self.ctor(x=16000.0)
        self.assertEqual(self.mem.load(S.G_OFF_GRID,4),NODE)
        self.assertEqual(self.mem.load(NODE,4),NEXT)
        self.assertEqual(self.mem.load(NEXT+4,4),NODE)
        self.assertEqual(self.mem.load(NODE+4,4),S.G_OFF_GRID)

    def test_grid_negative_boundary(self):
        for x,col in ((-0.5,60),(-1.0,59),(-256.9,59),(-257.0,58)):
            self.ctor(x=x)
            self.assertEqual(self.link_calls[-1][0],S.G_GRID_A+4*(60*120+col))

    def test_property_key_is_mutated_and_nth_is_not_default(self):
        self.properties(PROPS,[b'Hide=9',b'hide= -2tail',b'hide=7'])
        self.mem.poke(OBJ+0x2c,4,PROPS)
        self.put_text(S.S_HIDE,b'HIDE')
        self.assertEqual(self.model.property_int(OBJ,S.S_HIDE),-2)
        self.assertEqual(self.model.text(S.S_HIDE),b'hide')
        self.assertEqual(self.model.property_int(OBJ,S.S_HIDE,1),7)
        self.assertEqual(self.model.property_int(OBJ,S.S_HIDE,99),0)

    def test_names_duplicates_case_quotes_and_pointer_identity(self):
        self.properties(PROPS,[b'name="a"tail',b'Name=ignored',b'name=A',b'name='])
        self.ctor(PROPS)
        h = G.O.name_hash(b'a')
        self.assertEqual(self.mem.load(G.G_NAMES+4*h,4),STR+5)
        self.assertEqual(self.mem.load(G.G_NAMES+4*((h+1)&511),4),STR+256+5)
        self.assertEqual(self.mem.load(G.G_NAME_COUNT,4),3)
        self.assertEqual(self.model.text(STR),b'name=a')
        # strcpy writes terminator, does not erase the old suffix.
        self.assertEqual(self.mem.load(STR+7,1),ord('"'))
        self.assertEqual(self.mem.load(G.G_NAMES,4),STR+384+5)
        # Two ordinal searches per name, one terminal search: 7 key rewrites.
        self.assertEqual(sum(a==G.S_NAME for a,_,_ in self.model.writes),7)

    def test_tombstone_reuse_only_same_name(self):
        self.put_text(STR,b'alpha')
        slot = self.model.name_add(STR,OBJ)
        self.mem.poke(G.G_NAMED_OBJECTS+4*slot,4,0)
        self.put_text(STR+128,b'ALPHA')
        self.assertEqual(self.model.name_add(STR+128,OBJ+100),slot)
        self.assertEqual(self.mem.load(G.G_NAMES+4*slot,4),STR+128)
        self.mem.poke(G.G_NAMED_OBJECTS+4*slot,4,0)
        self.put_text(STR+128,b'unrelated')
        self.assertEqual(self.model.name_add(STR,OBJ),(slot+1)&511)

    def test_full_table_keeps_quote_and_count_prefix(self):
        self.put_text(STR,b'"new"suffix')
        self.put_text(STR+128,b'used')
        for i in range(512):
            self.mem.poke(G.G_NAMES+4*i,4,STR+128)
            self.mem.poke(G.G_NAMED_OBJECTS+4*i,4,OBJ)
        with self.assertRaises(G.ContractFault):
            self.model.name_add(STR,OBJ)
        self.assertEqual(self.model.text(STR),b'new')
        self.assertEqual(self.mem.load(G.G_NAME_COUNT,4),1)
        self.assertEqual(self.mem.load(G.G_NAMES,4),STR+128)

    def test_definition_resolution_and_generation(self):
        d = 0x7000
        for p,v in ((d,0x7100),(d+4,1),(d+8,0x7200),(d+16,0x7300),
                    (S.G_LUMP_GENERATION,2)):
            self.mem.poke(p,4,v)
        calls=[]
        def resolve(lump,name):
            calls.append((lump,name))
            return name+8
        self.model.cb['res_find']=resolve
        self.ctor(class_def=d)
        self.assertEqual(calls,[(0x7100,0x7200),(0x7100,0x7300)])
        self.assertEqual(self.mem.load(d+12,4),0x7208)
        self.assertEqual(self.mem.load(d+20,4),0x7308)
        self.assertEqual(self.mem.load(d+4,4),2)
        self.ctor(class_def=d)
        self.assertEqual(len(calls),2)

    def test_resolver_reloads_definition_and_grid_flags(self):
        d, replacement = 0x7000, 0x7400
        for p,v in ((d,0x7100),(d+8,0x7200),(S.G_LUMP_GENERATION,2)):
            self.mem.poke(p,4,v)
        def resolve(lump,name):
            self.mem.poke(OBJ+0x24,4,replacement)
            self.mem.poke(OBJ+0xc,4,0x800)
            return 0x7654
        self.model.cb['res_find']=resolve
        self.ctor(class_def=d)
        self.assertEqual(self.mem.load(d+12,4),0)
        self.assertEqual(self.mem.load(replacement+12,4),0x7654)
        self.assertEqual(self.mem.load(replacement+4,4),2)
        self.assertEqual(self.link_calls[-1][0],0x5e95f0+4*(60*120+60))

    def test_required_service_refuses_after_prefix(self):
        del self.model.cb['handle_link']
        with self.assertRaises(G.ContractFault):
            self.ctor()
        self.assertEqual(self.mem.load(OBJ+0x48,4),S.VT_GAMEOBJECT)
        self.assertEqual(self.model.draws,0)


if __name__ == '__main__':
    unittest.main()
