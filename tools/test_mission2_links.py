"""Authored synthetic fixtures for strict link checks; no owner files required."""
from collections import Counter
from contextlib import redirect_stderr
import io
import struct
import unittest
from unittest.mock import patch

import ref_amx as A
import ref_mission2 as R
from difftest_mission2_links import BoundedScript, ContractError, cli, one_property, record_links, strict_objects


def script_image(program=None, publics=None, data=b'one\0two\0'):
    if program is None:
        program = [('PROC',), ('PUSH.C', 7), ('PUSH.C', 0), ('PUSH.C', 8),
                   ('SYSREQ.C', 0), ('STACK', 12), ('RETN',),
                   ('PROC',), ('RETN',)]
    code, _labels = A.assemble(program)
    # Deliberately sorted by name, opposite to address order.
    return A.build_image(code, b''.join(data[i:i + 4][::-1] for i in range(0, len(data), 4)),
                         publics if publics is not None else [('zeta', 0), ('alpha', 48)],
                         ['native0'], stack_cells=16)


def changed(image, relative, value, fmt='<I'):
    out = bytearray(image)
    struct.pack_into(fmt, out, 0x60 + relative, value)
    return bytes(out)


def code_changed(image, relative, value):
    cod = struct.unpack_from('<I', image, 0x60 + 0x0c)[0]
    return changed(image, cod + relative, value)


def objects(properties=('key=alpha',)):
    pool = bytearray(b'actor\0')
    offsets = []
    for prop in properties:
        offsets.append(len(pool))
        pool.extend(prop.encode('ascii') + b'\0')
    size = 24 + 4 * len(offsets)
    row = struct.pack('<ihH3f', 0, size, 0, 0, 0, 0)
    row += b''.join(struct.pack('<i', at) for at in offsets) + bytes(4)
    return struct.pack('<hHi', 1, 0, 8 + size) + row + pool


class RecordProperties(unittest.TestCase):
    def setUp(self):
        self.script = BoundedScript(script_image())
        self.ctor = 0x29df04
        self.klass = next(k for k, v in R.FACTORY.items() if v[1] == self.ctor)
        self.rows = [dict(index=9, **{'class': self.klass}, properties='key=zeta'),
                     dict(index=4, **{'class': self.klass}, properties='key=alpha')]
        self.expected = ((9, 0), (4, 48))

    def check(self, rows, expected=None):
        return record_links(rows, self.ctor, 'key', self.script,
                            self.expected if expected is None else expected)

    def test_pairing_and_multiset_ignore_input_iteration_order(self):
        self.assertEqual(self.check(self.rows), 2)
        self.assertEqual(self.check(self.rows[::-1]), 2)
        self.assertEqual(Counter(at for _ordinal, at in self.expected), Counter((0, 48)))

    def test_missing_empty_identical_or_conflicting_duplicates_refuse(self):
        for props in ('', 'key=', 'key=zeta;key=zeta', 'key=zeta;key=alpha'):
            with self.subTest(props=props), self.assertRaises(AssertionError):
                one_property(dict(index=9, properties=props), 'key')

    def test_prefix_is_not_key(self):
        self.assertEqual(one_property(dict(index=9, properties='key2=bad;key=zeta'), 'key'), 'zeta')

    def test_redistribution_that_old_sets_accepted_refuses(self):
        rows = [dict(self.rows[0], properties='key=zeta;key=alpha'),
                dict(self.rows[1], properties='')]
        with self.assertRaises(AssertionError):
            self.check(rows)

    def test_swapped_links_keep_multiset_but_refuse(self):
        rows = [dict(self.rows[0], properties='key=alpha'), dict(self.rows[1], properties='key=zeta')]
        with self.assertRaises(AssertionError):
            self.check(rows)

    def test_duplicate_missing_or_extra_records_refuse(self):
        for rows in (self.rows[:1], self.rows + self.rows[:1],
                     [self.rows[0], dict(self.rows[1], index=9)]):
            with self.subTest(count=len(rows)), self.assertRaises(AssertionError):
                self.check(rows)

    def test_unknown_target_and_wrong_constructor_refuse(self):
        for row in (dict(self.rows[0], properties='key=unknown'),
                    dict(self.rows[0], **{'class': 'authored_unknown_class'})):
            with self.assertRaises(AssertionError):
                self.check([row, self.rows[1]])

    def test_duplicate_target_multiplicity_is_not_a_set(self):
        rows = [self.rows[0], dict(self.rows[1], properties='key=zeta')]
        self.assertEqual(self.check(rows, ((9, 0), (4, 0))), 2)
        with self.assertRaises(AssertionError):
            self.check(rows)


class ObjectEnvelope(unittest.TestCase):
    def test_authored_records_parse(self):
        rows = strict_objects(objects(('key=alpha', 'key=alpha')))
        self.assertEqual(rows[0]['index'], 0)
        with self.assertRaises(AssertionError):
            one_property(rows[0], 'key')

    def test_embedded_delimiter_refuses_before_flattening(self):
        with self.assertRaises(AssertionError):
            strict_objects(objects(('key=alpha;key=beta',)))

    def test_record_size_bounds_and_alignment(self):
        for size in (-4, 0, 20, 25, 32764):
            image = bytearray(objects())
            struct.pack_into('<h', image, 12, size)
            with self.subTest(size=size), self.assertRaises(AssertionError):
                strict_objects(image)

    def test_missing_terminator_and_invalid_string_offsets(self):
        for offset, value in ((32, 6), (28, -1), (28, 9999), (8, -1)):
            image = bytearray(objects())
            struct.pack_into('<i', image, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(AssertionError):
                strict_objects(image)

    def test_bad_count_pool_and_truncation(self):
        variants = [b'', objects()[:12], objects()[:-1]]
        for off, fmt, val in ((0, '<h', -1), (0, '<h', 2), (4, '<i', 9), (4, '<i', 9999)):
            image = bytearray(objects())
            struct.pack_into(fmt, image, off, val)
            variants.append(image)
        for image in variants:
            with self.subTest(size=len(image)), self.assertRaises(AssertionError):
                strict_objects(image)


class CallBounds(unittest.TestCase):
    def setUp(self):
        self.image = script_image()
        self.script = BoundedScript(self.image)

    def call(self, script=None, start=0, end=48, site=28, count=2, strings=(0,)):
        return (script or self.script).call_values_in(start, end, site, 'native0', count, strings)

    def test_bounds_sorted_by_address_and_last_entry(self):
        self.assertEqual(self.script.entry_bounds(0), (0, 48))
        self.assertEqual(self.script.entry_bounds(48), (48, 56))
        self.assertEqual(self.call(), ('one', 7))

    def test_zero_string_pointer_and_integer_zero_are_distinct(self):
        self.assertEqual(self.call(strings=()), (0, 7))
        self.assertEqual(self.call(strings=(0,)), ('one', 7))

    def test_wrong_entry_and_wrong_end_refuse(self):
        for kwargs in (dict(start=48, end=56), dict(end=52), dict(site=48), dict(site=0)):
            with self.subTest(kwargs=kwargs), self.assertRaises(AssertionError):
                self.call(**kwargs)

    def test_argument_packet_cannot_cross_owner_start(self):
        program = [('PROC',), ('PUSH.C', 0), ('PROC',), ('PUSH.C', 8),
                   ('SYSREQ.C', 0), ('STACK', 12), ('RETN',)]
        script = BoundedScript(script_image(program, [('first', 0), ('second', 12)]))
        with self.assertRaises(AssertionError):
            self.call(script, start=12, end=44, site=24)

    def test_call_shaped_debug_payload_is_not_instructions(self):
        # A wholly authored FILE payload contains a fake argument/call packet.
        payload = struct.pack('<9I', A.OP['PUSH.C'], 7, A.OP['PUSH.C'], 0,
                              A.OP['PUSH.C'], 8, A.OP['SYSREQ.C'], 0, A.OP['STACK'])
        payload += struct.pack('<I', 12)
        program = [('PROC',), ('FILE', 1, payload), ('RETN',)]
        script = BoundedScript(script_image(program, [('only', 0)]))
        with self.assertRaises(AssertionError):
            self.call(script, end=script.end-script.start, site=40)

    def test_call_in_operand_and_bad_cleanup_refuse(self):
        for off, value in ((0, A.OP['CONST.pri']), (40, 8), (24, 4), (32, 7)):
            with self.subTest(off=off), self.assertRaises(AssertionError):
                self.call(BoundedScript(code_changed(self.image, off, value)))

    def test_wrong_count_and_invalid_string_selection_refuse(self):
        for kwargs in (dict(count=1), dict(count=3), dict(count=-1),
                       dict(strings=(2,)), dict(strings=(0, 0)), dict(strings=(1,))):
            with self.subTest(kwargs=kwargs), self.assertRaises(AssertionError):
                self.call(**kwargs)

    def test_missing_argument_instructions_and_changed_values_refuse(self):
        for off, value in ((4, A.OP['CONST.pri']), (12, A.OP['PUSH']), (8, 0), (16, 7)):
            with self.subTest(off=off), self.assertRaises(AssertionError):
                BoundedScript(code_changed(self.image, off, value)).call_in(0, 48, 28, 'native0', 'one', 7)

    def test_truncated_instruction_debug_and_case_records_refuse(self):
        for program in ([('PROC',), ('PUSH.C', 1)], [('PROC',), ('FILE', 1, b'abc')],
                        [('PROC',), ('CASETBL', 0, [])]):
            image = script_image(program, [('only', 0)])
            if len(program[-1]) > 1:
                image = code_changed(image, 8, 0xfffffff0)
            with self.subTest(kind=program[-1][0]), self.assertRaises(AssertionError):
                BoundedScript(image if program[-1][0] != 'PUSH.C' else changed(image, 0x10,
                    struct.unpack_from('<I', image, 0x60+0x10)[0] - 4))

    def test_duplicate_entries_and_native_names_refuse(self):
        code, _labels = A.assemble([('PROC',), ('RETN',), ('PROC',), ('RETN',)])
        for pubs, natives in (([('same', 0), ('same', 8)], ['n']),
                              ([('a', 0), ('b', 0)], ['n']),
                              ([('a', 0), ('b', 8)], ['n', 'n'])):
            with self.subTest(pubs=pubs), self.assertRaises(AssertionError):
                BoundedScript(A.build_image(code, (), pubs, natives))

    def test_unlisted_or_noninstruction_entry_refuses(self):
        for publics in ([('only', 0)], [('a', 0), ('b', 4)], [('a', 0), ('b', 52)]):
            with self.subTest(publics=publics), self.assertRaises(AssertionError):
                BoundedScript(script_image(publics=publics))

    def test_bad_envelope_and_unsupported_encoding_refuse(self):
        for offset, value, fmt in ((4, 0, '<H'), (8, 4, '<H'), (8, 1, '<H'),
                                   (0x0a, 20, '<H'), (0x10, 1, '<I'),
                                   (0x14, len(self.image)+4, '<I'),
                                   (0x20, 99999, '<I'), (0x24, 0, '<I'),
                                   (0x2c, 0x40, '<I')):
            with self.subTest(offset=offset), self.assertRaises(AssertionError):
                BoundedScript(changed(self.image, offset, value, fmt))
        with self.assertRaises(AssertionError):
            BoundedScript(self.image[:0x80])


    def test_header_size_versions_and_stack(self):
        heap = struct.unpack_from('<I', self.image, 0x60 + 0x14)[0]
        for offset, value, fmt in ((0, 0, '<I'), (0, heap + 4, '<I'),
                                   (0x18, heap - 4, '<I'),
                                   (0x18, len(self.image), '<I'),
                                   (6, 255, '<B'), (7, 255, '<B')):
            with self.subTest(offset=offset), self.assertRaises(AssertionError):
                BoundedScript(changed(self.image, offset, value, fmt))


class CliFailures(unittest.TestCase):
    def test_contract_failure_prints_safe_diagnostic_without_traceback(self):
        stderr = io.StringIO()
        with patch('difftest_mission2_links.main', side_effect=ContractError('record 9: size')):
            with redirect_stderr(stderr):
                self.assertEqual(cli([]), 1)
        self.assertEqual(stderr.getvalue(), 'FAIL mission2 links: record 9: size\n')

    def test_imported_failure_suppresses_private_text_and_traceback(self):
        for error in (AssertionError('synthetic_private_value'), ValueError('synthetic_private_value')):
            stderr = io.StringIO()
            with patch('difftest_mission2_links.main', side_effect=error):
                with redirect_stderr(stderr):
                    self.assertEqual(cli([]), 1)
            self.assertNotIn('synthetic_private_value', stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())
            self.assertEqual(stderr.getvalue(),
                             f'FAIL mission2 links: {type(error).__name__} (details suppressed)\n')


if __name__ == '__main__':
    unittest.main()
