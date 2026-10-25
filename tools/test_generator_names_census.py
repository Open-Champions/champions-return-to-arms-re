"""Tests for generator_names_census.py on authored synthetic scripts; no game file needed."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generator_names_census as G     # noqa: E402
import ref_amx                         # noqa: E402
from ref_amx import assemble, build_image   # noqa: E402

NATIVES = ['generateMonster', 'getRand', 'setv']


def unpacked(text):
    return [c for c in text] + [0]


def packed(text):
    raw = text + b'\0'
    raw += b'\0' * (-len(raw) % 4)
    return [struct.unpack('>I', raw[k:k + 4])[0] for k in range(0, len(raw), 4)]


class Data:
    """Cells of a data block with named addresses."""

    def __init__(self):
        self.cells, self.at = [], {}

    def put(self, name, cells):
        self.at[name] = 4 * len(self.cells)
        self.cells += cells
        return self.at[name]

    def table(self, name, rows, pack=False):
        """A two-level array: the indirection vector, then the rows."""
        base = 4 * len(self.cells)
        self.at[name] = base
        bodies = [packed(r) if pack else unpacked(r) for r in rows]
        vector_end = base + 4 * len(rows)
        offsets, at = [], vector_end
        for i, body in enumerate(bodies):
            offsets.append(at - (base + 4 * i))
            at += 4 * len(body)
        self.cells += offsets
        for body in bodies:
            self.cells += body
        return base


def row_read(table, index_global, bound):
    """`table[index]` as the compiler emits it for a row address."""
    return [('PUSH.C', table), ('LOAD.pri', index_global), ('BOUNDS', bound), ('POP.alt',), ('IDXADDR',),
            ('MOVE.alt',), ('LOAD.I',), ('ADD',), ('PUSH.pri',)]


def machine(program, data, publics):
    cells, labels = assemble(program)
    image = build_image(cells, data.cells, [(name, labels[label]) for name, label in publics], NATIVES)
    m = ref_amx.Machine(image)
    assert m.load() == 0
    return m, image


class Shapes(unittest.TestCase):
    def build(self, pack=False):
        d = Data()
        gen = d.put('gen', unpacked(b'spawner'))
        cls = d.put('cls', unpacked(b'Orc'))
        idx = d.put('idx', [0])
        table = d.table('names', [b'Orc', b'Skeleton', b'Alpha'], pack=pack)
        program = [
            'main:', ('PROC',), ('LINE', 1, 0),
            ('PUSH.C', cls), ('PUSH.C', gen), ('PUSH.C', 8), ('SYSREQ.C', 0), ('STACK', 12),
            ('LINE', 2, 0)] + row_read(table, idx, 2) + [
            ('PUSH.C', gen), ('PUSH.C', 8), ('SYSREQ.C', 0), ('STACK', 12),
            ('LINE', 3, 0), ('PUSH.C', cls)] + row_read(table, idx, 2) + [
            ('PUSH.C', 8), ('SYSREQ.C', 0), ('STACK', 12),
            ('ZERO.pri',), ('RETN',)]
        return machine(program, d, [('main', 'main')]), d

    def test_argument_shapes(self):
        (m, _image), _d = self.build()
        _natives, _code, found = G.sites(m)
        self.assertEqual([tuple(G.shape(a) for a in args) for _p, _o, args in found],
                         [('literal', 'literal'), ('literal', 'table row'), ('table row', 'literal')])

    def test_generator_computed_class_literal(self):
        # the last call: the class is a literal even though instructions sit between the pushes
        (m, _image), d = self.build()
        _n, _c, found = G.sites(m)
        args = found[2][2]
        self.assertEqual(args[1], ('c', d.at['cls']))
        self.assertEqual(args[0][0], 'row')

    def test_rows_unpacked_and_packed(self):
        for pack in (False, True):
            (m, _image), d = self.build(pack)
            rows = G.table_rows(m, d.at['names'], 2)
            self.assertEqual([t for _a, t in rows], [b'Orc', b'Skeleton', b'Alpha'])
            end = max(a + G.string_bytes(m, a, t) for a, t in rows)
            self.assertEqual(end, 4 * len(d.cells))

    def test_census_counts(self):
        (_m, image), _d = self.build()
        r = G.census([image])
        self.assertEqual(r['calls'], 3)
        self.assertEqual(r['tables'], 1)
        self.assertEqual(r['table_rows'], 3)
        self.assertEqual(r['table_other_refs'], 0)
        self.assertEqual(r['class_literal_names'], {b'Orc'})
        self.assertEqual(r['class_candidates'], {b'Orc', b'Skeleton', b'Alpha'})
        self.assertEqual(r['long'], 0)

    def test_factory_labels(self):
        (_m, image), _d = self.build()
        answers = {b'Orc': (0x488, 0x2A0954), b'Skeleton': (0x478, G.SKELETON_CTOR), b'Alpha': (None, None)}
        r = G.census([image], factory=lambda name: answers[name])
        self.assertEqual(r['factory'], {('literal', 'constructor'): 1, ('candidate', 'constructor'): 1,
                                        ('candidate', 'Skeleton constructor'): 1,
                                        ('candidate', 'no object'): 1})

    def test_long_name_counted(self):
        d = Data()
        gen = d.put('gen', unpacked(b'q'))
        cls = d.put('cls', unpacked(b'x' * 24))
        program = ['main:', ('PROC',), ('PUSH.C', cls), ('PUSH.C', gen), ('PUSH.C', 8), ('SYSREQ.C', 0),
                   ('STACK', 12), ('ZERO.pri',), ('RETN',)]
        _m, image = machine(program, d, [('main', 'main')])
        self.assertEqual(G.census([image])['long'], 1)


class Origins(unittest.TestCase):
    def build(self, extra_write=False):
        d = Data()
        gen = d.put('gen', unpacked(b'spawner'))
        idx = d.put('idx', [0])
        order = d.put('order', [0, 1, 2])          # the index table a shuffle permutes
        pick = d.put('pick', [0])
        tmp = d.put('tmp', [0])
        table = d.table('names', [b'Orc', b'Alpha', b'Beta'])
        program = [
            # shuffle: pick = getRand() % 3; tmp = order[pick]; order[pick] = order[0]; order[0] = tmp
            'shuffle:', ('PROC',), ('LINE', 1, 0),
            ('PUSH.C', 0), ('SYSREQ.C', 1), ('STACK', 4), ('MOVE.alt',), ('CONST.pri', 3), ('SDIV.alt',),
            ('MOVE.pri',), ('STOR.pri', pick),
            ('LINE', 2, 0), ('PUSH.C', order), ('LOAD.pri', pick), ('BOUNDS', 2), ('POP.alt',), ('IDXADDR',),
            ('LOAD.I',), ('STOR.pri', tmp),
            ('LINE', 3, 0), ('PUSH.C', order), ('LOAD.pri', pick), ('BOUNDS', 2), ('POP.alt',), ('IDXADDR',),
            ('PUSH.pri',), ('CONST.pri', order), ('LOAD.I',), ('POP.alt',), ('STOR.I',),
            ('LINE', 4, 0), ('CONST.alt', order), ('LOAD.pri', tmp), ('STOR.I',),
            ('ZERO.pri',), ('RETN',),
            # spawn: idx = order[0]; generateMonster("gen1", names[idx])
            'spawn:', ('PROC',), ('LINE', 4, 0),
            ('PUSH.C', order), ('CONST.pri', 0), ('BOUNDS', 2), ('POP.alt',), ('IDXADDR',), ('LOAD.I',),
            ('STOR.pri', idx),
            ('LINE', 5, 0)] + row_read(table, idx, 2) + [
            ('PUSH.C', gen), ('PUSH.C', 8), ('SYSREQ.C', 0), ('STACK', 12)]
        if extra_write:     # a reference to the name table that is not an element read
            program += [('LINE', 6, 0), ('PUSH.C', table), ('PUSH.C', gen), ('PUSH.C', 8), ('SYSREQ.C', 2),
                        ('STACK', 12)]
        program += [('ZERO.pri',), ('RETN',)]
        return machine(program, d, [('shuffle', 'shuffle'), ('spawn', 'spawn')]), d

    def test_index_from_shuffled_table(self):
        (m, image), _d = self.build()
        r = G.census([image])
        self.assertEqual(r['origin'], {('class', 'element of an index table'): 1,
                                       ('class', 'store into that index table'): 1})
        self.assertEqual({draws for _s, _f, draws in r['getrand_functions']}, {1})

    def test_other_reference_flagged(self):
        (_m, image), _d = self.build(extra_write=True)
        r = G.census([image])
        self.assertEqual(r['table_other_refs'], 1)

    def test_shuffle_runs_in_model(self):
        # the model machine runs the shuffle with the Lcg standing in for getRand
        (m, _image), d = self.build()
        lcg = G.Lcg(20973)
        seen = set()
        m.register({'generateMonster': lambda mm, a: 0, 'getRand': lambda mm, a: lcg.next(),
                    'setv': lambda mm, a: 0})
        saved = m.snapshot()
        index = {name: k for k, (name, _o) in enumerate(m.publics())}[b'shuffle']
        for _ in range(40):
            m.restore(saved)
            self.assertEqual(m.execute(index)[0], 0)
            seen.add(tuple(m.cell(d.at['order'] + 4 * k) for k in range(3)))
        self.assertTrue(all(sorted(s) == [0, 1, 2] for s in seen))
        self.assertGreater(len(seen), 1)


class Helpers(unittest.TestCase):
    def test_lcg_matches_getrand(self):
        # docs/spec/script-builtins.md 87: seed = seed * 0x19660d + 0x3c6ef35f, result seed >> 16
        lcg = G.Lcg(0)
        self.assertEqual(lcg.next(), 0x3C6EF35F >> 16)
        self.assertEqual(lcg.next(), ((0x3C6EF35F * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF) >> 16)

    def test_count_not_constant(self):
        d = Data()
        program = ['main:', ('PROC',), ('PUSH.pri',), ('SYSREQ.C', 0), ('STACK', 12), ('ZERO.pri',), ('RETN',)]
        _m, image = machine(program, d, [('main', 'main')])
        r = G.census([image])
        self.assertEqual(r['shape'], {('call', 'count not constant'): 1})


if __name__ == '__main__':
    unittest.main()
