"""Unit tests of the script-machine model (tools/ref_amx.py).  No game files are needed: every
image is built here.  What these cases assert was first established against the original
machine code by tools/difftest_amx.py; they keep the model from drifting when it is edited."""
import struct
import unittest

import ref_amx
from ref_amx import HostFault, Limit, Machine, OP, OPCODES, assemble, build_image

HALT = [('HALT', 0)]


def machine(program, data=(), natives=(), functions=None, publics=None, stack_cells=64, **keywords):
    """A loaded machine for a program whose first instruction is the entry point "main"."""
    cells, labels = assemble(program)
    entries = [('main', 0)] + [(name, labels[label]) for name, label in (publics or [])]
    m = Machine(build_image(cells, data, entries, natives, stack_cells, **keywords))
    assert m.load() == 0
    assert m.register(functions or {}) == 0
    m.main = m.find_public('main')[1]
    return m


def run(program, **keywords):
    m = machine(program, **keywords)
    return m.execute(m.main)


class Tables(unittest.TestCase):
    def test_opcode_table(self):
        self.assertEqual(len(OPCODES), 0x83)
        self.assertEqual(len(OP), 0x83)
        self.assertEqual(OP['SYSREQ.C'], 0x7B)
        self.assertEqual(OP['CASETBL'], 0x82)
        kinds = [kind for _name, kind, _handler in OPCODES]
        self.assertEqual(kinds.count(ref_amx.C), 15)
        self.assertEqual(kinds.count(ref_amx.V), 55)
        self.assertEqual(kinds.count(ref_amx.N), 56)
        self.assertEqual(len({handler for _name, _kind, handler in OPCODES}), 0x83)


class Loading(unittest.TestCase):
    def test_load_sets_the_machine_words(self):
        image = build_image([OP['HALT'], 0], [1, 2, 3], [('main', 0)], ['f'], 16)
        m = Machine(image)
        self.assertEqual(m.load(), 0)
        self.assertEqual((m.hea, m.stk, m.stp), (12, 12 + 64 - 4, 12 + 64 - 4))
        self.assertEqual(m.flags, 0x2000 | 0x8000)
        self.assertEqual(m.hdr_stp, m.stp + m.dat)
        self.assertEqual(struct.unpack_from('<i', m.image, 0x60 + 0x18)[0], m.hdr_stp)   # header field lowered
        self.assertEqual(m.cell(m.stp), 0)                                               # sentinel
        self.assertEqual(m.publics(), [(b'main', 0)])
        self.assertEqual(m.native_names(), [b'f'])
        self.assertEqual(m.load(), 0)                                                    # second load: no change
        self.assertEqual(m.stp, 12 + 64 - 4)

    def test_header_checks(self):
        good = bytearray(build_image([OP['HALT'], 0], [], [('main', 0)], (), 16))

        def changed(offset, fmt, value):
            image = bytearray(good)
            struct.pack_into(fmt, image, 0x60 + offset, value)
            return Machine(image).load()

        self.assertEqual(changed(4, '<H', 0xF1E1), 17)
        self.assertEqual(changed(0x0A, '<H', 20), 17)
        self.assertEqual(changed(7, '<b', 4), 18)
        self.assertEqual(changed(7, '<b', 3), 0)
        self.assertEqual(changed(7, '<b', -1), 0)          # compared as a signed byte
        self.assertEqual(changed(6, '<b', 99), 0)          # the file version is not looked at
        self.assertEqual(changed(0x18, '<i', 0), 17)
        self.assertEqual(changed(0x18, '<i', -8), 17)
        self.assertEqual(changed(0x18, '<i', 0x7FFFFFFF), 17)
        self.assertEqual(changed(8, '<H', 1), 17)
        self.assertEqual(changed(8, '<H', 2), 0)

    def test_bad_opcode_leaves_the_code_unusable(self):
        for opcode in (0, 0x83, 0xFF, 0x100, -1):
            m = Machine(build_image([OP['LINE'], 7, 9, opcode, OP['HALT'], 0], [], [('main', 0)], (), 16))
            self.assertEqual(m.load(), 0)                  # scr_load does not report it
            self.assertEqual(m.flags & 0x8000, 0)
            self.assertEqual((m.curline, m.curfile, m.dbgcode), (7, 9, 2))   # the pass got this far
            self.assertEqual(m.execute(0), (22, None))

    def test_debug_words_after_load(self):
        m = machine([('FILE', 5, b'a.sma'), ('LINE', 3, 5), ('SYMBOL', 12, 1, b'x'), ('SRANGE', 0, 4),
                     ('LINE', 8, 5)] + HALT)
        self.assertEqual((m.curline, m.curfile, m.dbgcode, m.dbgaddr, m.dbgparam), (8, 5, 2, 0, 4))

    def test_compact_image(self):
        program = [('PROC',), ('CONST.pri', -123456), ('CONST.alt', 0x7FFFFFFF), ('JUMP', 'end'), ('ZERO.pri',),
                   'end:', ('HALT', 0)]
        cells, _ = assemble(program)
        plain = Machine(build_image(cells, [1, -1, 0x12345678], [('main', 0)], (), 64))
        packed = Machine(build_image(cells, [1, -1, 0x12345678], [('main', 0)], (), 64, compact=True))
        self.assertEqual((plain.load(), packed.load()), (0, 0))
        self.assertEqual(packed.memory(), plain.memory())
        self.assertEqual(packed.execute(0), (0, -123456))

    def test_compact_coding(self):
        for cell, size in ((0, 1), (1, 1), (-1, 1), (63, 1), (64, 2), (-64, 1), (-65, 2), (0x1FFF, 2),
                           (0x2000, 3), (0x7FFFFFFF, 5), (-0x80000000, 5)):
            coded = ref_amx.encode_compact([7, cell])
            self.assertEqual(len(coded), 1 + size)
            image = bytearray(coded.ljust(8, b'\0'))
            ref_amx.expand_compact(image, 0, len(coded), 8)
            self.assertEqual(struct.unpack('<ii', image), (7, cell))
        # over-long form: the sixth byte from the end is shifted by 35 mod 32 = 3 bits
        image = bytearray(4) + bytes([0x81, 0x80, 0x80, 0x80, 0x80, 0x00])
        ref_amx.expand_compact(image, 4, 6, 4)
        self.assertEqual(struct.unpack_from('<i', image, 4)[0], 8)

    def test_relocator_does_not_follow_a_broken_record(self):
        m = Machine(build_image([OP['FILE'], 2, 0, OP['HALT'], 0], [], [('main', 0)], (), 16))
        with self.assertRaises(HostFault):                 # size 2: the next opcode is off a cell boundary
            m.load()


class Entry(unittest.TestCase):
    def test_find_public_is_a_binary_search(self):
        names = ['alpha', 'beta', 'delta', 'gamma', 'zeta']
        m = Machine(build_image([OP['HALT'], 0], [], [(n, 0) for n in names], (), 16))
        m.load()
        self.assertEqual([m.find_public(n) for n in names], [(0, i) for i in range(5)])
        self.assertEqual(m.find_public('Alpha'), (19, 0x7FFFFFFF))
        self.assertEqual(m.find_public(''), (19, 0x7FFFFFFF))
        self.assertEqual(m.find_public(b'beta\0junk'), (0, 1))
        unsorted = Machine(build_image([OP['HALT'], 0], [], [(n, 0) for n in ('c', 'b', 'a')], (), 16,
                                       sort_publics=False))
        unsorted.load()
        self.assertEqual(unsorted.find_public('b'), (0, 1))               # the middle record
        self.assertEqual(unsorted.find_public('a'), (19, 0x7FFFFFFF))     # there, but the search goes left
        self.assertEqual(unsorted.find_public('c'), (19, 0x7FFFFFFF))

    def test_index(self):
        m = machine([('CONST.pri', 1), ('HALT', 0), 'two:', ('CONST.pri', 2), ('HALT', 0)], publics=[('two', 'two')])
        self.assertEqual((m.execute(0), m.execute(1)), ((0, 1), (0, 2)))  # sorted: main, two
        self.assertEqual(m.execute(2), (20, None))
        self.assertEqual(m.execute(-1), (20, None))        # no start address in the header
        self.assertEqual(m.execute(-3), (20, None))
        with_main = machine([('CONST.pri', 9), ('HALT', 0)], start=0)
        self.assertEqual(with_main.execute(-1), (0, 9))

    def test_arguments_and_initial_registers(self):
        program = [('PROC',), ('LOAD.S.pri', 12), ('LOAD.S.alt', 16), ('SUB',), ('RETN',)]
        m = machine(program)
        top = m.stk
        self.assertEqual(m.execute(0, (50, 8)), (0, 42))
        self.assertEqual(m.stk, top)
        self.assertEqual([m.cell(top - 4 * k) for k in (1, 2, 3, 4)], [8, 50, 8, 0])   # args, size, return address
        self.assertEqual(run([('HALT', 0)]), (0, 0))
        self.assertEqual(machine(HALT).execute(0, pri=-77), (0, -77))                  # PRI is whatever it was
        self.assertEqual(run([('PUSH.alt',), ('LCTRL', 5), ('POP.alt',), ('ADD',), ('HALT', 0)]), (0, 0))

    def test_entry_errors(self):
        m = machine(HALT)
        m.callback = None
        self.assertEqual(m.execute(0), (9, None))
        m = machine(HALT)
        m.flags = m.flags & ~0x8000 | 0x4000
        self.assertEqual(m.execute(0), (22, None))
        self.assertEqual(m.flags & 0x4000, 0)
        m = machine(HALT)
        m.stk = m.hdr_stp + 4                              # compared with the header's field
        self.assertEqual(m.execute(0), (7, None))
        m = machine(HALT)
        m.hea = -4
        self.assertEqual(m.execute(0), (8, None))
        m = machine(HALT)
        m.stk = m.hea + 0x40 + 4                           # 0x3c bytes would be left
        self.assertEqual(m.execute(0), (3, None))
        self.assertEqual((m.cell(m.stk - 4), m.cell(m.stk - 8)), (0, 0))
        m.stk += 4
        self.assertEqual(m.execute(0), (0, 0))

    def test_call_by_name(self):
        m = machine([('CONST.pri', 5), ('HALT', 0), 'bad:', ('CONST.pri', 6), ('HALT', 4)], publics=[('bad', 'bad')])
        self.assertEqual(m.call('main'), 5)
        self.assertEqual(m.call('nothing'), -1)
        self.assertEqual(m.call('bad'), 6)                 # HALT stores PRI whatever its code
        failing = machine([('CONST.pri', 6), ('CONST.alt', 0), ('SDIV',), ('HALT', 0)])
        self.assertEqual(failing.call('main'), 0)          # an error run leaves the caller's 0


class Arithmetic(unittest.TestCase):
    def test_floored_division(self):
        for dividend, divisor, quotient, remainder in ((7, 2, 3, 1), (-7, 2, -4, 1), (7, -2, -4, -1),
                                                       (-7, -2, 3, -1), (6, 3, 2, 0), (-6, 3, -2, 0),
                                                       (0, 5, 0, 0), (-0x80000000, -1, -0x80000000, 0),
                                                       (-0x80000000, 1, -0x80000000, 0),
                                                       (-1, 0x7FFFFFFF, -1, 0x7FFFFFFE)):
            self.assertEqual(ref_amx.floored_div(dividend, divisor), (quotient, remainder),
                             (dividend, divisor))
        # 32-bit wrap-around between the three machine divides: the floor would be -1
        self.assertEqual(ref_amx.floored_div(0x7FFFFFFF, -0x80000000), (1, -1))

    def test_division_opcodes(self):
        self.assertEqual(run([('CONST.pri', -7), ('CONST.alt', 2), ('SDIV',), ('HALT', 0)]), (0, -4))
        self.assertEqual(run([('CONST.pri', 2), ('CONST.alt', -7), ('SDIV.alt',), ('MOVE.pri',), ('HALT', 0)]), (0, 1))
        self.assertEqual(run([('CONST.pri', -7), ('CONST.alt', 2), ('UDIV',), ('HALT', 0)]), (0, 0x7FFFFFFC))
        self.assertEqual(run([('CONST.pri', 2), ('CONST.alt', -7), ('UDIV.alt',), ('MOVE.pri',), ('HALT', 0)]), (0, 1))
        for name in ('SDIV', 'UDIV'):
            self.assertEqual(run([('CONST.pri', 1), ('CONST.alt', 0), (name,), ('HALT', 0)]), (11, None))
        for name in ('SDIV.alt', 'UDIV.alt'):
            self.assertEqual(run([('CONST.pri', 0), ('CONST.alt', 1), (name,), ('HALT', 0)]), (11, None))

    def test_shift_counts_are_taken_modulo_32(self):
        self.assertEqual(run([('CONST.pri', 1), ('CONST.alt', 33), ('SHL',), ('HALT', 0)]), (0, 2))
        self.assertEqual(run([('CONST.pri', -8), ('CONST.alt', 1), ('SHR',), ('HALT', 0)]), (0, 0x7FFFFFFC))
        self.assertEqual(run([('CONST.pri', -8), ('CONST.alt', 1), ('SSHR',), ('HALT', 0)]), (0, -4))
        self.assertEqual(run([('CONST.pri', -8), ('SHR.C.pri', 32), ('HALT', 0)]), (0, -8))
        self.assertEqual(run([('CONST.pri', 3), ('SHL.C.pri', 31), ('HALT', 0)]), (0, -0x80000000))

    def test_wrap(self):
        self.assertEqual(run([('CONST.pri', 0x7FFFFFFF), ('INC.pri',), ('HALT', 0)]), (0, -0x80000000))
        self.assertEqual(run([('CONST.pri', 0x10001), ('SMUL.C', 0x10001), ('HALT', 0)]), (0, 0x20001))
        self.assertEqual(run([('CONST.pri', -0x80000000), ('NEG',), ('HALT', 0)]), (0, -0x80000000))
        self.assertEqual(run([('CONST.pri', 0x40000001), ('CONST.alt', 8), ('IDXADDR',), ('HALT', 0)]), (0, 12))

    def test_sign_only_sets_bits(self):
        self.assertEqual(run([('CONST.pri', 0x1280), ('SIGN.pri',), ('HALT', 0)]), (0, -0x80))
        self.assertEqual(run([('CONST.pri', 0x127F), ('SIGN.pri',), ('HALT', 0)]), (0, 0x127F))

    def test_comparisons(self):
        self.assertEqual(run([('CONST.pri', -1), ('CONST.alt', 1), ('LESS',), ('HALT', 0)]), (0, 0))
        self.assertEqual(run([('CONST.pri', -1), ('CONST.alt', 1), ('SLESS',), ('HALT', 0)]), (0, 1))
        self.assertEqual(run([('CONST.pri', 5), ('CONST.alt', 7), ('EQ.C.alt', 7), ('HALT', 0)]), (0, 1))
        self.assertEqual(run([('CONST.pri', 0), ('NOT',), ('HALT', 0)]), (0, 1))
        self.assertEqual(run([('CONST.pri', -1), ('CONST.alt', 1), ('JLESS', 'yes'), ('HALT', 1), 'yes:',
                              ('HALT', 2)])[0], 1)
        self.assertEqual(run([('CONST.pri', -1), ('CONST.alt', 1), ('JSLESS', 'yes'), ('HALT', 1), 'yes:',
                              ('HALT', 2)])[0], 2)


class Memory(unittest.TestCase):
    def test_address_check(self):
        m = machine([('LOAD.I',), ('HALT', 0)], data=[11, 22])
        self.assertEqual(m.execute(0, pri=4), (0, 22))
        self.assertEqual(m.execute(0, pri=m.hea), (5, None))           # free room between heap and stack
        self.assertEqual(m.execute(0, pri=m.stk - 12), (5, None))
        self.assertEqual(m.execute(0, pri=m.stk - 8), (0, 0))          # the run's own stack
        self.assertEqual(m.execute(0, pri=m.stp), (5, None))
        with self.assertRaises(HostFault):                             # negative passes the check
            m.execute(0, pri=-4)
        with self.assertRaises(HostFault):                             # unaligned word access
            m.execute(0, pri=2)

    def test_bytes(self):
        data = [0x04030201]
        self.assertEqual(run([('CONST.pri', 1), ('LODB.I', 1), ('HALT', 0)], data=data), (0, 2))
        self.assertEqual(run([('CONST.pri', 2), ('LODB.I', 2), ('HALT', 0)], data=data), (0, 0x0403))
        self.assertEqual(run([('CONST.pri', 0), ('LODB.I', 3), ('HALT', 0)], data=data), (0, 0))   # no effect
        m = machine([('CONST.pri', -1), ('CONST.alt', 1), ('STRB.I', 1), ('HALT', 0)], data=data)
        m.execute(0)
        self.assertEqual(m.cell(0) & 0xFFFFFFFF, 0x0403FF01)

    def test_blocks(self):
        m = machine([('CONST.pri', 0), ('CONST.alt', 4), ('MOVS', 12), ('CONST.pri', 0), ('CONST.alt', 20),
                     ('CMPS', 4), ('HALT', 0)], data=[1, 2, 3, 4, 0, 0x00000201])
        self.assertEqual(m.execute(0), (0, 2 - 0))                     # first differing bytes: 02 and 00
        self.assertEqual([m.cell(4 * k) for k in range(4)], [1, 1, 1, 1])   # overlapping copy smears forward
        m = machine([('CONST.pri', 7), ('CONST.alt', 4), ('FILL', 11), ('HALT', 0)], data=[0] * 5)
        m.execute(0)
        self.assertEqual([m.cell(4 * k) for k in range(5)], [0, 7, 7, 0, 0])

    def test_bounds(self):
        self.assertEqual(run([('CONST.pri', 5), ('BOUNDS', 5), ('HALT', 0)]), (0, 5))
        self.assertEqual(run([('CONST.pri', 6), ('BOUNDS', 5), ('HALT', 0)]), (4, None))
        self.assertEqual(run([('CONST.pri', -1), ('BOUNDS', 5), ('HALT', 0)]), (4, None))

    def test_strings(self):
        m = machine(HALT, data=[0] * 32)
        m.set_string(0, b'hello', True)
        self.assertEqual([m.cell(0) & 0xFFFFFFFF, m.cell(4) & 0xFFFFFFFF], [0x68656C6C, 0x6F000000])
        self.assertEqual((m.get_string(0), m.str_len(0)), (b'hello', 5))
        m.set_string(16, b'hi\xe9', False)
        self.assertEqual([m.cell(16), m.cell(20), m.cell(24), m.cell(28)], [0x68, 0x69, -23, 0])
        self.assertEqual((m.get_string(16), m.str_len(16)), (b'hi\xe9', 3))
        m.set_string(40, b'abcd', True)                                # a whole cell: one more zero cell
        self.assertEqual((m.cell(44), m.get_string(40), m.str_len(40)), (0, b'abcd', 4))
        m.set_cell(60, 0xE9616263 - (1 << 32))                         # first character above 0x7f:
        m.set_cell(64, 0)                                              # read as unpacked
        self.assertEqual(m.get_string(60), b'\x63')
        for position, word in enumerate((0x41, 0x4200, 0x43, 0)):       # unpacked; one cell has a zero low byte
            m.set_cell(72 + 4 * position, word)
        self.assertEqual((m.get_string(72), m.str_len(72)), (b'A\0C', 3))
        self.assertEqual(m.get_string(100), b'')

    def test_heap_helpers(self):
        m = machine(HALT, data=[0] * 4)
        self.assertEqual(m.allot(2), (0, 16))
        self.assertEqual(m.hea, 24)
        self.assertEqual(m.release(100), 0)
        self.assertEqual(m.hea, 24)
        m.release(16)
        self.assertEqual(m.hea, 16)
        room = m.stk - m.hea
        self.assertEqual(m.allot((room - 0x40) // 4 + 1), (16, None))
        self.assertEqual(m.allot(room // 4 + 1)[0], 0)                 # sic: more than there is
        self.assertEqual(m.get_addr(0), 0)
        self.assertEqual(m.get_addr(m.stp), 5)
        self.assertEqual(m.get_addr(-4), 0)                            # sic


class Control(unittest.TestCase):
    def test_call_and_return(self):
        program = [('PROC',), ('PUSH.C', 3), ('PUSH.C', 4), ('PUSH.C', 8), ('CALL', 'mul'), ('RETN',),
                   'mul:', ('PROC',), ('LOAD.S.pri', 12), ('LOAD.S.alt', 16), ('SMUL',), ('RETN',)]
        m = machine(program)
        top = m.stk
        self.assertEqual(m.execute(0), (0, 12))
        self.assertEqual(m.stk, top)

    def test_retn_stores_the_stack_pointer_even_when_it_moved(self):
        # an entry point that drops four bytes too many, as some shipped scripts do
        m = machine([('PROC',), ('PUSH.C', 4), ('STACK', 8), ('ZERO.pri',), ('RETN',)])
        top = m.stk
        self.assertEqual(m.execute(0), (0, 0))
        self.assertEqual(m.stk, top + 4)
        with self.assertRaises(HostFault):                 # the second time it reads past the block
            m.execute(0)

    def test_error_exits_and_the_stack_pointer(self):
        m = machine([('PUSH.C', 0), ('SYSREQ.C', 0), ('STACK', -4000), ('HALT', 0)], natives=['f'],
                    functions={'f': lambda m, args: 0})
        top = m.stk
        self.assertEqual(m.execute(0), (3, None))
        self.assertEqual(m.stk, top - 12)                  # STACK's error return keeps the native call's value
        m = machine([('PUSH.C', 0), ('SYSREQ.C', 0), ('CONST.pri', 9), ('BOUNDS', 1), ('HALT', 0)], natives=['f'],
                    functions={'f': lambda m, args: 0})
        self.assertEqual(m.execute(0), (4, None))
        self.assertEqual(m.stk, top)                       # the others restore it
        self.assertEqual(run([('HEAP', -4), ('HALT', 0)]), (8, None))
        self.assertEqual(run([('HEAP', 4000), ('HALT', 0)]), (3, None))
        m = machine([('STACK', 5000), ('HALT', 0)])
        self.assertEqual(m.execute(0), (7, None))

    def test_switch(self):
        program = [('SWITCH', 'table'), 'table:', ('CASETBL', 'none', [(1, 'one'), (2, 'two'), (1, 'two')]),
                   'none:', ('HALT', 10), 'one:', ('HALT', 11), 'two:', ('HALT', 12)]
        m = machine(program)
        self.assertEqual([m.execute(0, pri=p)[0] for p in (0, 1, 2, 3)], [10, 11, 12, 10])
        with self.assertRaises(HostFault):
            run([('CASETBL', 'x', []), 'x:', ('HALT', 0)])

    def test_control_registers(self):
        m = machine([('LCTRL', 6), ('HALT', 0)])
        self.assertEqual(m.execute(0), (0, 8))             # address of the next instruction
        self.assertEqual(run([('LCTRL', 3), ('MOVE.alt',), ('LCTRL', 4), ('SUB.alt',), ('HALT', 0)]), (0, 8))
        self.assertEqual(run([('CONST.pri', 'there'), ('SCTRL', 6), ('HALT', 1), 'there:', ('HALT', 2)])[0], 2)
        self.assertEqual(run([('LCTRL', 9), ('HALT', 0)]), (0, 0))

    def test_jumps_must_land_on_instructions(self):
        with self.assertRaises(HostFault):
            run([('CONST.pri', 4), ('JUMP.pri',), ('HALT', 0)])        # into the operand of CONST.pri
        with self.assertRaises(HostFault):
            run([('ZERO.pri',)])                                       # runs off the end of the code

    def test_budget(self):
        m = machine(['loop:', ('JUMP', 'loop')])
        m.budget = 1000
        with self.assertRaises(Limit):
            m.execute(0)


class Natives(unittest.TestCase):
    def test_arguments_result_and_saved_registers(self):
        seen = []

        def native(m, args):
            seen.append((list(args), m.params, m.cell(m.params), m.cip, m.frm, m.stk, m.get_string(args[0])))
            return -5

        program = [('PROC',), ('PUSH.C', 99), ('PUSH.C', 0), ('PUSH.C', 8), ('SYSREQ.C', 0), ('STACK', 12), ('RETN',)]
        m = machine(program, data=[0x6F6B0000], natives=['say'], functions={'say': native})
        top = m.stk
        self.assertEqual(m.execute(0), (0, -5))
        self.assertEqual(seen, [([0, 99], top - 24, 8, 36, top - 12, top - 24, b'ok')])

    def test_registration(self):
        m = Machine(build_image([OP['HALT'], 0], [], [('main', 0)], ['a', 'b'], 16))
        m.load()
        self.assertEqual(m.register({'a': lambda m, args: 0}), 19)
        self.assertEqual(m.register({b'b': lambda m, args: 0}), 0)
        unbound = Machine(build_image([OP['PUSH.C'], 0, OP['SYSREQ.C'], 0, OP['HALT'], 0], [], [('main', 0)],
                                      ['a'], 64))
        unbound.load()
        with self.assertRaises(HostFault):
            unbound.execute(0)

    def test_error_word(self):
        def native(m, args):
            m.raise_error(27)
            return 1

        m = machine([('PUSH.C', 0), ('SYSREQ.C', 0), ('HALT', 0)], natives=['f'], functions={'f': native})
        top = m.stk
        self.assertEqual(m.execute(0), (27, None))
        self.assertEqual(m.stk, top)

    def test_nested_run(self):
        def native(m, args):
            return m.call('inner') + 1

        program = [('PROC',), ('PUSH.C', 0), ('SYSREQ.C', 0), ('STACK', 4), ('ADD.C', 100), ('RETN',),
                   'inner:', ('PROC',), ('CONST.pri', 7), ('RETN',)]
        m = machine(program, natives=['f'], functions={'f': native}, publics=[('inner', 'inner')])
        top = m.stk
        self.assertEqual(m.execute(m.main), (0, 108))
        self.assertEqual(m.stk, top)
        self.assertEqual(m.cell(top - 28), 0)              # the nested frame sat below the caller's stack

    def test_snapshot(self):
        m = machine([('INC', 0), ('LOAD.pri', 0), ('HALT', 0)], data=[5])
        saved = m.snapshot()
        self.assertEqual(m.execute(0), (0, 6))
        self.assertEqual(m.execute(0), (0, 7))
        m.restore(saved)
        self.assertEqual(m.execute(0), (0, 6))


if __name__ == '__main__':
    unittest.main()
