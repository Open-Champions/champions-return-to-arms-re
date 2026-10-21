"""Synthetic names and tables only: no executable, index or picture data needed."""
import struct
import unittest

import ref_icon_assoc as R

MODELS = ['mdl0.tex', 'axe1.tex']
PREFIX = [(3, 2, 9), (0, 5, 0), (12, -1, 4)]          # (weapon, armour, alternate)
BODIES = ['b%d' % i for i in range(12)]


def item(name='sword', category=0, slot=0, subtype=0, dmg=(4, 6), picture='pic_sword1',
         row=0, variant=0, prefix=0xff, flags=0):
    d = R.ItemDef(name, category, slot, subtype, dmg[0], dmg[1], picture, row)
    return R.Item(d, flags | variant << 11, prefix)


def name(it, body=0, value=None):
    return R.picture_filename(it, body, MODELS, PREFIX, BODIES, value)


class Weapons(unittest.TestCase):
    def test_variant_then_colour_replace_last_digit(self):
        self.assertEqual(name(item()), 'pic_sword11.tex')
        self.assertEqual(name(item(variant=2, prefix=0)), 'pic_sword33.tex')

    def test_model_texture_when_no_picture_name(self):
        self.assertEqual(name(item(picture=None, row=1)), 'axe11.tex')

    def test_bow_alternate_zero_colour_and_preset(self):
        self.assertEqual(name(item(subtype=4, prefix=0)), 'pic_sword11.tex')
        self.assertEqual(name(item(prefix=0, flags=R.ALT_COLOUR)), 'pic_sword19.tex')
        self.assertEqual(name(item(subtype=4, prefix=2, flags=R.ALT_COLOUR)), 'pic_sword14.tex')
        self.assertEqual(name(item(prefix=1)), 'pic_sword11.tex')        # colour 0 -> 1
        self.assertEqual(name(item(name='sword+x', dmg=(20, 13))), 'pic_sword115.tex')
        self.assertEqual(name(item(name='sword+x', dmg=(9, 9))), 'pic_sword11.tex')

    def test_variant_31_prints_zero_and_plain_weapon_flag(self):
        self.assertEqual(name(item(variant=31)), 'pic_sword01.tex')
        self.assertEqual(name(item(variant=3, prefix=0, flags=R.PLAIN_WEAPON)), 'pic_sword4.tex')

    def test_concatenation_aliases_in_index_lookup(self):
        a = name(item(variant=0, prefix=2))                  # variant 1, colour 12
        b = name(item(name='sword+', variant=10, dmg=(1, 1)))  # variant 11, colour 2
        self.assertEqual(a, b)
        self.assertEqual(R.split_picture_name(a), ('pic_sword', 112))


class Armour(unittest.TestCase):
    def test_body_substitution(self):
        self.assertEqual([R.armour_body(b, True) for b in range(12)],
                         [6, 7, 6, 7, 6, 7, 6, 7, 6, 7, 6, 6])
        self.assertEqual([R.armour_body(b, False) for b in range(12)],
                         [0, 1, 2, 3, 4, 5, 0, 1, 8, 9, 10, 11])

    def test_prefix_preset_and_slot3(self):
        plate = dict(name='plate', category=1, slot=4, picture='chest')
        self.assertEqual(name(item(**plate), body=3), 'b3_chest1.tex')
        self.assertEqual(name(item(**plate, prefix=1), body=6), 'b0_chest5.tex')
        self.assertEqual(name(item(**plate, prefix=2), body=2), 'b2_chest-1.tex')
        self.assertEqual(name(item(**plate, flags=R.CLOTH), body=9), 'b7_chest1.tex')
        preset = dict(plate, name='plate+y')
        self.assertEqual(name(item(**preset, prefix=0), body=5, value=-7), 'b5_chest-3.tex')
        self.assertEqual(name(item(**preset), body=5, value=7), 'b5_chest1.tex')   # no prefix wins
        with self.assertRaises(ValueError):
            name(item(**preset, prefix=0), body=5)
        self.assertEqual(name(item(**dict(plate, slot=3)), body=7), 'chest.tex')

    def test_circlets(self):
        c = dict(category=1, slot=1, picture='circ')
        self.assertEqual(name(item(name='circlet24', **c), body=7), 'b7_cloth2helmet641.tex')
        self.assertEqual(name(item(name='circlet35', **c, prefix=0), body=6), 'b6_cloth3helmet652.tex')
        self.assertEqual(name(item(name='circlet12', **c, flags=R.CLOTH), body=2), 'b2_circ1.tex')
        for bad in ('gold circlet1', 'circlet3'):
            with self.assertRaises(ValueError):
                name(item(name=bad, **c), body=6)


class OtherItems(unittest.TestCase):
    def test_only_names_containing_1_tex_take_the_variant(self):
        self.assertEqual(name(item(category=2, picture='gem1', variant=4)), 'gem5.tex')
        self.assertEqual(name(item(category=2, picture='gem', variant=4)), 'gem.tex')
        # strstr anywhere, splice at the end (0x1082f0 vs 0x108314)
        self.assertEqual(name(item(category=2, picture='ab1.texq', variant=1)), 'ab1.tex2.tex')


def index(groups):
    head = struct.pack('<I', len(groups))
    table, blob = b'', b''
    base = 4 + 12 * len(groups)
    for stem, entries in groups:
        stem_at = base + len(blob); blob += stem.encode() + b'\0'
        entries_at = base + len(blob)
        blob += b''.join(struct.pack('<hHHhh', *e) for e in entries)
        table += struct.pack('<III', entries_at, stem_at, len(entries))
    return head + table + blob


class Index(unittest.TestCase):
    def setUp(self):
        self.groups = R.parse_index(index([
            ('pic_sword', [(11, 0, 3, 40, 80), (112, 3, 3, 41, 82)]),
            ('gem', [(-1, 6, 2, 20, 24)]),
            ('pic_sword', [(12, 8, 3, 42, 84)]),
            ('a', [(7, 11, 2, 8, 8)])]))

    def test_split(self):
        self.assertEqual(R.split_picture_name('pic_sword112.tex'), ('pic_sword', 112))
        self.assertEqual(R.split_picture_name('gem.tex'), ('gem', -1))
        self.assertEqual(R.split_picture_name('a.b.tex'), ('a.b', -1))
        self.assertEqual(R.split_picture_name('7.tex'), ('7', -1))    # first char kept
        self.assertEqual(R.split_picture_name('x2y07'), ('x2y', 7))
        self.assertIsNone(R.split_picture_name('.tex'))

    def test_lookup_continues_past_stem_without_number(self):
        self.assertEqual(R.find_entry(self.groups, 'pic_sword12.tex').sector, 8)
        self.assertEqual(R.find_entry(self.groups, 'pic_sword112.tex').width, 41)
        self.assertEqual(R.find_entry(self.groups, 'gem.tex').number, -1)
        self.assertEqual(R.find_entry(self.groups, 'a7.tex').height, 8)
        for miss in ('PIC_SWORD11.tex', 'pic_sword13.tex', 'gem1.tex', '.tex', 'a.tex'):
            self.assertIsNone(R.find_entry(self.groups, miss), miss)

    def test_bounded_reader(self):
        data = index([('s', [(1, 0, 1, 2, 2)])])
        with self.assertRaises(ValueError):
            R.parse_index(data[:-1])
        with self.assertRaises(ValueError):
            R.parse_index(struct.pack('<I', 9))


class Streaming(unittest.TestCase):
    def setUp(self):
        self.cache = R.PictureCache(R.parse_index(index([('p', [(i, i, 1, 8, 8) for i in range(80)])])))

    def test_placeholder_until_read_completes(self):
        c = self.cache
        self.assertIsNone(c.request('p1.tex', 0))
        self.assertEqual(R.picture_or_placeholder(None, 'p1.tex'), R.PLACEHOLDER)
        c.service(0, False)
        self.assertIsNone(c.request('p1.tex', 1))
        c.service(1, False)
        c.service(2, True)
        self.assertEqual(c.request('p1.tex', 3).number, 1)

    def test_one_read_at_a_time_and_missing_names(self):
        c = self.cache
        for n in ('p2.tex', 'q.tex', 'p3.tex'):
            c.request(n, 0)
        c.service(0, False)
        states = [s['state'] for s in c.slots]
        self.assertEqual(states, ['reading', 'pending', 'pending'])
        c.service(1, True)
        self.assertEqual([s['state'] for s in c.slots], ['loaded', 'missing', 'reading'])
        self.assertIsNone(c.request('q.tex', 2))

    def test_eviction_needs_more_than_eight_idle_frames(self):
        c = self.cache
        for i in range(64):
            c.request('p%d.tex' % i, i % 3)
        self.assertIsNone(c.request('p70.tex', 10))          # 10-8=2: none < 2 except frames 0,1
        self.assertEqual(len(c.slots), 64)
        self.assertNotIn('p0.tex', [s['name'] for s in c.slots])  # first oldest evicted
        for s in c.slots:
            s['last'] = 5
        c.request('p71.tex', 13)                              # 5 < 13-8 is false
        self.assertNotIn('p71.tex', [s['name'] for s in c.slots])


if __name__ == '__main__':
    unittest.main()
