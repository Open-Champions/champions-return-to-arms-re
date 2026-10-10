"""Unit tests for tools/fieldxref.py and tools/flagxref.py on small hand-written listings.

No game file is needed: every listing below is synthetic MIPS written for the test, in the
text form llvm-objdump prints. Run: python3 -m unittest discover -s tools -p test_fieldxref.py
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('champions_flagxref', TOOLS / 'flagxref.py')
gx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gx)
fx = gx.fx


def listing(text):
    """'1000: op args' lines -> objdump-style lines."""
    out = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line == '...':
            out.append('\t\t...')
            continue
        addr, rest = line.split(':', 1)
        op, _, args = rest.strip().partition(' ')
        out.append('  %s:      \t%s\t%s' % (addr.strip(), op, args.strip()))
    return out


def scan(text, bodies=None, word_at=None):
    lines = listing(text)
    ins = fx.parse_listing(lines, word_at)
    if bodies is None:
        bodies = [(ins[0][0], [(ins[0][0], ins[-1][0] + 3)])]
    return fx.scan(ins, bodies)


def field(db, offs, **kw):
    return fx.query_field(db, fx.parse_offsets(offs), **kw)


def texts(db, offs, **kw):
    return [fx._hit_text(h) for h in field(db, offs, **kw)]


def flags(db, mask, off=0xc, **kw):
    hits, hidden = gx.query_flag(db, mask, off, **kw)
    return [gx.hit_text(h, mask) for h in hits]


class FieldAccess(unittest.TestCase):
    def test_plain_load_and_store_and_stack_is_ignored(self):
        db = scan('''
            1000: lw $2, 0x44($4)
            1004: sw $2, 0x44($5)
            1008: lw $3, 0x44($sp)
            100c: jr $ra
            1010: nop''')
        self.assertEqual(texts(db, '44'), ['1000:lw+44', '1004:sw+44'])
        self.assertEqual(texts(db, '44', stores=True), ['1004:sw+44'])
        self.assertEqual(texts(db, '44', loads=True), ['1000:lw+44'])

    def test_unaligned_pair_is_one_access_at_the_right_half(self):
        db = scan('''
            1000: ldl $6, 0x47($5)
            1004: ldr $6, 0x40($5)
            1008: sdl $6, 0x4f($4)
            100c: sdr $6, 0x48($4)
            1010: lwr $7, 0x60($5)
            1014: lwl $7, 0x63($5)
            1018: jr $ra
            101c: nop''')
        self.assertEqual(texts(db, '40'), ['1000:uld+40'])
        self.assertEqual(texts(db, '48'), ['1008:usd+48'])
        self.assertEqual(texts(db, '4c'), ['1008:usd+48*'])       # covered by the 8 bytes
        self.assertEqual(texts(db, '60'), ['1010:ulw+60'])
        self.assertEqual(texts(db, '47'), ['1000:uld+40*'])

    def test_wider_access_at_lower_displacement_covers(self):
        db = scan('''
            1000: sd $2, 0x40($4)
            1004: sw $2, 0x50($4)
            1008: sh $2, 0x60($4)
            100c: sq $2, 0x70($4)
            1010: jr $ra
            1014: nop''')
        self.assertEqual(texts(db, '44'), ['1000:sd+40*'])
        self.assertEqual(texts(db, '53'), ['1004:sw+50*'])
        self.assertEqual(texts(db, '61'), ['1008:sh+60*'])
        self.assertEqual(texts(db, '62'), [])
        self.assertEqual(texts(db, '7f'), ['100c:sq+70*'])
        self.assertEqual(texts(db, '48'), [])

    def test_pointer_formed_first(self):
        db = scan('''
            1000: addiu $5, $4, 0x4a50
            1004: move $6, $5
            1008: sw $zero, 0x8($6)
            100c: sw $zero, 0xc($5)
            1010: jr $ra
            1014: nop''')
        self.assertEqual(texts(db, '4a58'), ['1008:sw+8{a0+4a50}'])
        self.assertEqual(texts(db, '4a5c'), ['100c:sw+c{a0+4a50}'])
        # the plain displacement is still reported, as before
        self.assertEqual(texts(db, '8'), ['1008:sw+8'])
        self.assertTrue(all(h['certain'] for h in field(db, '4a58')))

    def test_counted_zero_fill_loop(self):
        db = scan('''
            1000: addiu $5, $4, 0x36c
            1004: addiu $2, $zero, 0xf
            1008: sw $zero, 0x0($5)
            100c: addiu $2, $2, -0x1
            1010: bgez $2, 0x1008 <x>
            1014: addiu $5, $5, 0x4
            1018: jr $ra
            101c: nop''')
        self.assertEqual(texts(db, '36c'), ['1008:sw+0{a0+36c~4x16}'])
        self.assertEqual(texts(db, '388'), ['1008:sw+0{a0+36c~4x16}'])     # element 7
        self.assertEqual(texts(db, '3a8'), ['1008:sw+0{a0+36c~4x16}'])     # element 15
        self.assertEqual(texts(db, '3ac'), [])                               # past the end
        self.assertEqual(texts(db, '368'), [])                               # before the start
        self.assertTrue(field(db, '388')[0]['certain'])

    def test_counted_copy_loop_with_bne_and_downward_walk(self):
        db = scan('''
            1000: addiu $3, $4, 0x39c
            1004: addiu $5, $zero, 0x3
            1008: addiu $6, $zero, -0x1
            100c: lw $2, 0x0($3)
            1010: addiu $5, $5, -0x1
            1014: bne $5, $6, 0x100c <x>
            1018: addiu $3, $3, -0x4
            101c: jr $ra
            1020: nop''')
        self.assertEqual(texts(db, '39c'), ['100c:lw+0{a0+39c~-4x4}'])
        self.assertEqual(texts(db, '390'), ['100c:lw+0{a0+39c~-4x4}'])
        self.assertEqual(texts(db, '38c'), [])
        self.assertEqual(texts(db, '3a0'), [])

    def test_loop_bounded_by_end_pointer_and_by_compare(self):
        db = scan('''
            1000: addiu $3, $4, 0x100
            1004: addiu $7, $4, 0x120
            1008: sw $zero, 0x0($3)
            100c: addiu $3, $3, 0x8
            1010: bne $3, $7, 0x1008 <x>
            1014: nop
            1018: addiu $5, $4, 0x200
            101c: move $2, $zero
            1020: sb $zero, 0x0($5)
            1024: addiu $2, $2, 0x1
            1028: slti $6, $2, 0x10
            102c: bnez $6, 0x1020 <x>
            1030: addiu $5, $5, 0x1
            1034: jr $ra
            1038: nop''')
        self.assertEqual(texts(db, '118'), ['1008:sw+0{a0+100~8x4}'])
        self.assertEqual(texts(db, '120'), [])
        self.assertEqual(texts(db, '20f'), ['1020:sb+0{a0+200~1x16}'])
        self.assertEqual(texts(db, '210'), [])

    def test_uncounted_walk_is_possible_within_the_limit(self):
        db = scan('''
            1000: addiu $5, $4, 0x40
            1004: lw $2, 0x0($5)
            1008: bnez $2, 0x1004 <x>
            100c: addiu $5, $5, 0x4
            1010: jr $ra
            1014: nop''')
        self.assertEqual(texts(db, '40'), ['1004:lw+0{a0+40~4}'])
        self.assertEqual(texts(db, '60'), ['1004:lw+0{a0+40~4}?'])
        self.assertEqual(texts(db, '60', certain=True), [])
        self.assertEqual(texts(db, '400'), [])
        self.assertEqual(texts(db, '400', walk_limit=0x1000), ['1004:lw+0{a0+40~4}?'])
        self.assertEqual(texts(db, '3c'), [])                # it walks upward only

    def test_indexed_array_element(self):
        db = scan('''
            1000: sll $2, $5, 0x2
            1004: addu $2, $4, $2
            1008: lw $3, 0x36c($2)
            100c: jr $ra
            1010: nop''')
        self.assertEqual(texts(db, '36c'), ['1008:lw+36c[i]'])
        self.assertEqual(texts(db, '388'), [])
        self.assertEqual(texts(db, '388', array=(0x36c, 4, 16)), ['1008:lw+36c[i]?'])
        self.assertEqual(texts(db, '3ac', array=(0x36c, 4, 16)), [])

    def test_static_instance_table(self):
        db = scan('''
            1000: lui $2, 0x4e
            1004: addiu $2, $2, -0x2ab4
            1008: lw $3, 0x0($2)
            100c: lui $1, 0x4e
            1010: sw $zero, 0x217c($1)
            1014: jr $ra
            1018: nop''')
        # a table of 0x4c30-byte records at 0x4d8af0: slot 0 +0x4a5c is 0x4dd54c,
        # slot 1 +0x4a5c is 0x4e217c
        self.assertEqual(texts(db, '4a5c'), [])
        self.assertEqual(texts(db, '4a5c', static=(0x4d8af0, 0x4c30, 4)),
                         ['1008:lw@4dd54c', '1010:sw@4e217c'])
        self.assertEqual(texts(db, '4a5c', static=(0x4d8af0, 0x4c30, 1)), ['1008:lw@4dd54c'])

    def test_address_passed_to_a_call_and_followed_into_the_callee(self):
        db = scan('''
            1000: addiu $sp, $sp, -0x10
            1004: sd $ra, 0x0($sp)
            1008: jal 0x2000 <x>
            100c: addiu $4, $4, 0x364
            1010: ld $ra, 0x0($sp)
            1014: jr $ra
            1018: addiu $sp, $sp, 0x10
            2000: sw $zero, 0x0($4)
            2004: jr $ra
            2008: sw $zero, 0x4($4)''',
                  bodies=[(0x1000, [(0x1000, 0x101b)]), (0x2000, [(0x2000, 0x200b)])])
        self.assertEqual(texts(db, '364'), ['1008:&+364>2000', '2000:sw+0<1008&+364'])
        self.assertEqual(texts(db, '368'), ['2008:sw+4<1008&+364'])
        self.assertEqual(texts(db, '364', follow=False), ['1008:&+364>2000'])
        self.assertEqual(texts(db, '364', loads=True), [])
        # the filter applies to the call site; the callee's line is still produced
        self.assertEqual(texts(db, '368', funcs={0x1000}), ['2008:sw+4<1008&+364'])
        self.assertEqual(texts(db, '368', funcs={0x2000}), [])

    def test_block_call_with_constant_length(self):
        db = scan('''
            1000: addiu $4, $16, 0x300
            1004: move $5, $zero
            1008: jal 0x2000 <x>
            100c: addiu $6, $zero, 0x100
            1010: jr $ra
            1014: nop''')
        self.assertEqual(texts(db, '36c'), [])
        self.assertEqual(texts(db, '36c', blocks=True), ['1008:&+300..100>2000?'])
        self.assertEqual(texts(db, '400', blocks=True), [])

    def test_base_kept_across_a_call_is_only_possible(self):
        db = scan('''
            1000: addiu $5, $4, 0x80
            1004: addiu $16, $4, 0x80
            1008: jal 0x2000 <x>
            100c: nop
            1010: lw $2, 0x4($5)
            1014: lw $3, 0x4($16)
            1018: jr $ra
            101c: nop''')
        self.assertEqual(texts(db, '84'), ['1010:lw+4{a0+80}?', '1014:lw+4{a0+80}'])
        # the plain displacement does not depend on the register's history
        self.assertEqual(texts(db, '4'), ['1010:lw+4', '1014:lw+4'])

    def test_paths_that_join(self):
        db = scan('''
            1000: beqz $6, 0x1010 <x>
            1004: addiu $5, $4, 0x80
            1008: b 0x1014 <x>
            100c: addiu $7, $4, 0x10
            1010: addiu $7, $4, 0x20
            1014: lw $2, 0x4($5)
            1018: lw $3, 0x4($7)
            101c: jr $ra
            1020: nop''')
        self.assertEqual(texts(db, '84', walk_limit=0x20), ['1014:lw+4{a0+80}'])   # same on both
        # $7 is a0+0x10 on one path and a0+0x20 on the other: both are possible, neither
        # is certain, and nothing below the lower one is listed
        self.assertEqual(texts(db, '14'), ['1018:lw+4{a0+10~10}?'])
        self.assertEqual(texts(db, '24'), ['1018:lw+4{a0+10~10}?'])
        self.assertEqual(texts(db, '14', certain=True), [])
        self.assertEqual(texts(db, '4'), ['1014:lw+4', '1018:lw+4'])

    def test_likely_branch_delay_slot_runs_only_when_taken(self):
        db = scan('''
            1000: addiu $5, $4, 0x10
            1004: beqzl $6, 0x1010 <x>
            1008: addiu $5, $4, 0x80
            100c: lw $2, 0x4($5)
            1010: lw $3, 0x8($5)
            1014: jr $ra
            1018: nop''')
        self.assertEqual(texts(db, '14'), ['100c:lw+4{a0+10}'])      # fall-through keeps +0x10
        self.assertEqual(texts(db, '84'), [])
        # at 0x1010 the two paths disagree; the walk mark shows the pointer moved
        self.assertEqual([h['addr'] for h in field(db, '18')], [0x1010])

    def test_pointer_spilled_to_the_stack_frame(self):
        db = scan('''
            1000: addiu $sp, $sp, -0x20
            1004: addiu $2, $4, 0x4c8
            1008: sd $2, 0x10($sp)
            100c: jal 0x2000 <x>
            1010: nop
            1014: ld $3, 0x10($sp)
            1018: swc1 $f0, 0x1c($3)
            101c: jr $ra
            1020: addiu $sp, $sp, 0x20''')
        self.assertEqual(texts(db, '4e4'), ['1018:swc1+1c{a0+4c8}'])

    def test_stack_reload_is_possible_when_a_local_address_escapes(self):
        db = scan('''
            1000: addiu $sp, $sp, -0x40
            1004: addiu $2, $4, 0x4c8
            1008: sd $2, 0x10($sp)
            100c: jal 0x2000 <x>
            1010: addiu $4, $sp, 0x20
            1014: ld $3, 0x10($sp)
            1018: swc1 $f0, 0x1c($3)
            101c: jr $ra
            1020: addiu $sp, $sp, 0x40''')
        self.assertEqual(texts(db, '4e4'), ['1018:swc1+1c{a0+4c8}?'])

    def test_elided_zero_words_do_not_break_the_flow(self):
        db = scan('''
            1000: addiu $5, $4, 0x4c8
            1004: swc1 $f0, 0x24($5)
            ...
            1010: div.s $f1, $f20, $f1
            1014: swc1 $f1, 0x28($5)
            1018: jr $ra
            101c: nop''')
        self.assertEqual(texts(db, '4f0'), ['1014:swc1+28{a0+4c8}'])
        self.assertTrue(field(db, '4f0')[0]['certain'])

    def test_switch_case_blocks_inherit_the_state_at_the_indirect_jump(self):
        db = scan('''
            1000: move $16, $4
            1004: addiu $17, $4, 0x200
            1008: lw $2, 0x0($5)
            100c: jr $2
            1010: nop
            1014: b 0x1020 <x>
            1018: sw $zero, 0x10($17)
            101c: sw $zero, 0x14($17)
            1020: jr $ra
            1024: nop''')
        self.assertEqual(texts(db, '210'), ['1018:sw+10{a0+200}'])
        self.assertEqual(texts(db, '214'), ['101c:sw+14{a0+200}'])

    def test_r5900_words_objdump_cannot_print(self):
        words = {0x1000: 0x7c850040,      # sq $5, 0x40($4)
                 0x1004: 0x78860050,      # lq $6, 0x50($4)
                 0x1008: 0x00a62818}      # mult $5, $5, $6 (three operands: writes $5)
        db = scan('''
            1000: <unknown>
            1004: <unknown>
            1008: <unknown>
            100c: jr $ra
            1010: nop''', word_at=words.get)
        self.assertEqual(texts(db, '48'), ['1000:sq+40*'])
        self.assertEqual(texts(db, '50'), ['1004:lq+50'])
        self.assertEqual(fx.decode_unknown(0x00a62818), ('mult3', ['$5']))
        self.assertEqual(fx.decode_unknown(None), ('unk', []))

    def test_three_operand_multiply_kills_the_tracked_pointer(self):
        words = {0x1004: 0x00a62818}
        db = scan('''
            1000: addiu $5, $4, 0x80
            1004: <unknown>
            1008: lw $2, 0x4($5)
            100c: jr $ra
            1010: nop''', word_at=words.get)
        self.assertEqual(texts(db, '84'), [])

    def test_function_attribution_uses_the_given_bodies(self):
        text = '''
            1000: lw $2, 0x44($4)
            1004: jr $2
            1008: nop
            100c: lw $2, 0x44($4)
            1010: jr $ra
            1014: nop
            1018: lw $2, 0x44($4)
            101c: jr $ra
            1020: nop'''
        # one function with a case label in the middle, then code outside any function
        db = scan(text, bodies=[(0x1000, [(0x1000, 0x1017)])])
        hits = field(db, '44')
        self.assertEqual([h['func'] for h in hits], [0x1000, 0x1000, 0x1018])
        self.assertEqual(db['orphans'], {0x1018})
        lines = fx.format_hits(hits, db, {0x1000: 'Thing_run'})
        self.assertEqual(len(lines), 2)
        self.assertIn('Thing_run', lines[0])
        self.assertIn('outside any function', lines[1])

    def test_discontiguous_body(self):
        db = scan('''
            1000: addiu $5, $4, 0x80
            1004: j 0x3000 <x>
            1008: nop
            2000: lw $2, 0x44($4)
            2004: jr $ra
            2008: nop
            3000: lw $2, 0x4($5)
            3004: jr $ra
            3008: nop''',
                  bodies=[(0x1000, [(0x1000, 0x100b), (0x3000, 0x300b)]),
                          (0x2000, [(0x2000, 0x200b)])])
        self.assertEqual(texts(db, '84'), ['3000:lw+4{a0+80}'])
        self.assertEqual(field(db, '84')[0]['func'], 0x1000)

    def test_filters(self):
        db = scan('''
            1000: lw $2, 0x44($4)
            1004: lw $3, 0x10($5)
            1008: lw $2, 0x44($3)
            100c: jr $ra
            1010: nop
            2000: sw $zero, 0x44($4)
            2004: jr $ra
            2008: nop''',
                  bodies=[(0x1000, [(0x1000, 0x1013)]), (0x2000, [(0x2000, 0x200b)])])
        self.assertEqual(len(field(db, '44')), 3)
        self.assertEqual([h['addr'] for h in field(db, '44', this=True)], [0x1000, 0x2000])
        self.assertEqual([h['addr'] for h in field(db, '44', funcs={0x2000})], [0x2000])
        self.assertEqual([h['addr'] for h in field(db, '44', addr_range=(0x1004, 0x2000))], [0x1008])
        self.assertEqual(fx._hit_text(field(db, '44')[1], roots=True), '1008:lw+44/load@1004')
        self.assertEqual(texts(db, '40-47'), ['1000:lw+44', '1008:lw+44', '2000:sw+44'])
        self.assertEqual([h['addr'] for h in field(db, '4c', adjust=8)], [0x1000, 0x1008, 0x2000])

    def test_class_selection_by_symbol_prefix(self):
        names = {0x1000: 'Player_run', 0x2000: 'player_respawn', 0x3000: 'Creature_run',
                 0x4000: 'hud_draw'}
        self.assertEqual(fx.class_functions(None, names, ['Player']), {0x1000, 0x2000})
        pos, opts = fx.parse_common(['ELF', '36c', '--class', 'Player', '--stores'])
        self.assertEqual(pos, ['ELF', '36c'])
        funcs, rng = fx.resolve_filters(opts, None, names)
        self.assertEqual(funcs, {0x1000, 0x2000})
        self.assertIsNone(rng)
        pos, opts = fx.parse_common(['ELF', '36c', '--range', '1000:2000', '--func', '3000'])
        self.assertEqual(fx.resolve_filters(opts, None, names), ({0x3000}, (0x1000, 0x2000)))

    def test_offset_syntax(self):
        self.assertEqual(fx.parse_offsets('36c'), [(0x36c, 0x36d)])
        self.assertEqual(fx.parse_offsets('c8,2dc-2e3'), [(0xc8, 0xc9), (0x2dc, 0x2e4)])

    def test_cached_database_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'disasm').mkdir()
            (root / 'disasm' / 'text.asm').write_text('\n'.join(listing('''
                1000: addiu $5, $4, 0x80
                1004: lw $2, 0x4($5)
                1008: jr $ra
                100c: nop''')) + '\n')
            (root / 'ghidra_funcs.tsv').write_text('00001000\tFUN_00001000\t00001000-0000100f\n')
            first = fx.load_db(str(root), None)
            self.assertTrue((root / 'disasm' / 'text.fx.pickle').exists())
            again = fx.load_db(str(root), None)
            self.assertEqual(first['acc'], again['acc'])
            self.assertEqual(texts(again, '84'), ['1004:lw+4{a0+80}'])
            uncached = fx.load_db(str(root), None, use_cache=False)
            self.assertEqual(uncached['acc'], first['acc'])


class FlagBits(unittest.TestCase):
    def test_immediate_test_set_and_clear(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: andi $3, $2, 0x100
            1008: ori $2, $2, 0x40
            100c: addiu $5, $zero, -0x101
            1010: and $2, $2, $5
            1014: sw $2, 0xc($4)
            1018: jr $ra
            101c: nop''')
        self.assertEqual(flags(db, 0x100), ['1004:test', '1010:clear'])
        self.assertEqual(flags(db, 0x40), ['1008:set'])
        self.assertEqual(flags(db, 0x80), [])
        # the store is the same word written back: not a separate hit, even with --stores
        self.assertEqual(flags(db, 0x100, stores=True), ['1004:test', '1010:clear'])

    def test_no_window_between_load_and_test(self):
        body = '\n'.join('%x: addiu $9, $9, 0x1' % (0x1004 + 4 * i) for i in range(40))
        db = scan('1000: lw $16, 0xc($4)\n' + body + '''
            10a4: andi $3, $16, 0x100
            10a8: jr $ra
            10ac: nop''')
        self.assertEqual(flags(db, 0x100), ['10a4:test'])

    def test_combined_mask_is_found_and_printed(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: lui $3, 0x2
            1008: ori $3, $3, 0x8
            100c: and $2, $2, $3
            1010: jr $ra
            1014: nop''')
        self.assertEqual(flags(db, 0x20000), ['100c:test:20008'])
        self.assertEqual(flags(db, 0x8), ['100c:test:20008'])
        self.assertEqual(flags(db, 0x10), [])

    def test_mask_kept_in_a_register_across_a_loop(self):
        db = scan('''
            1000: lui $17, 0x20
            1004: lw $2, 0xc($4)
            1008: and $3, $2, $17
            100c: lw $4, 0x0($4)
            1010: bnez $4, 0x1004 <x>
            1014: nop
            1018: jr $ra
            101c: nop''')
        self.assertEqual(flags(db, 0x200000), ['1008:test'])

    def test_shift_and_sign_tests(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: sll $3, $2, 0xe
            1008: bltz $3, 0x1020 <x>
            100c: nop
            1010: srl $5, $2, 0x14
            1014: andi $5, $5, 0x1
            1018: bgez $2, 0x1020 <x>
            101c: nop
            1020: jr $ra
            1024: nop''')
        self.assertEqual(flags(db, 0x20000), ['1008:test(sign)'])       # bit 17 = 31 - 14
        self.assertEqual(flags(db, 0x100000), ['1014:test'])            # bit 20
        self.assertEqual(flags(db, 0x80000000), ['1018:test(sign)'])
        self.assertEqual(flags(db, 0x40000), [])

    def test_shift_down_to_the_bit_then_branch(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: srl $2, $2, 0x1f
            1008: bnez $2, 0x1010 <x>
            100c: nop
            1010: jr $ra
            1014: nop''')
        self.assertEqual(flags(db, 0x80000000), ['1008:test(shift)'])
        self.assertEqual(flags(db, 0x40000000), [])

    def test_byte_and_halfword_loads_inside_the_word(self):
        db = scan('''
            1000: lbu $2, 0xd($4)
            1004: andi $2, $2, 0x80
            1008: lhu $3, 0xe($4)
            100c: andi $3, $3, 0x2
            1010: lb $5, 0xf($4)
            1014: bltz $5, 0x101c <x>
            1018: nop
            101c: jr $ra
            1020: nop''')
        self.assertEqual(flags(db, 0x8000), ['1004:test'])              # byte 1, bit 7
        self.assertEqual(flags(db, 0x20000), ['100c:test'])             # byte 2, bit 1
        self.assertEqual(flags(db, 0x80000000), ['1014:test(sign)'])    # byte 3, bit 7
        self.assertEqual(flags(db, 0x80), [])

    def test_eight_byte_flag_word(self):
        db = scan('''
            1000: ld $2, 0xa8($4)
            1004: ori $3, $zero, 0x8000
            1008: dsll $3, $3, 0x10
            100c: and $5, $2, $3
            1010: dsll32 $6, $2, 0x0
            1014: bltz $6, 0x1028 <x>
            1018: nop
            101c: lui $7, 0x8000
            1020: or $2, $2, $7
            1024: sd $2, 0xa8($4)
            1028: jr $ra
            102c: nop''')
        hits = flags(db, 0x80000000, 0xa8)
        self.assertIn('100c:test', hits)                 # mask built as 0x00000000_80000000
        self.assertIn('1014:test(sign)', hits)           # bit 31 moved to bit 63
        # lui 0x8000 sign-extends: the or sets bits 31..63 of the 8-byte word
        self.assertIn('1020:set:ffffffff80000000', hits)
        # the high word on its own
        self.assertEqual(flags(db, 0x1, 0xac), ['1020:set:ffffffff'])

    def test_word_load_of_the_upper_half_of_an_eight_byte_word(self):
        db = scan('''
            1000: lw $2, 0xac($4)
            1004: andi $2, $2, 0x4
            1008: jr $ra
            100c: nop''')
        self.assertEqual(flags(db, 0x400000000, 0xa8), ['1004:test'])
        self.assertEqual(flags(db, 0x4, 0xa8), [])

    def test_toggle_and_clear_of_bit_15(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: xori $3, $2, 0x10
            1008: lui $5, 0xffff
            100c: ori $5, $5, 0x7fff
            1010: and $2, $2, $5
            1014: sw $2, 0xc($4)
            1018: jr $ra
            101c: nop''')
        self.assertEqual(flags(db, 0x10), ['1004:toggle'])
        self.assertEqual(flags(db, 0x8000), ['1010:clear'])
        self.assertEqual(flags(db, 0x4000), [])           # kept by the clear: not a test

    def test_registers_are_compared_as_tokens(self):
        # the old scanner matched "$2" inside "$20" and took any lui near a load as a hit
        db = scan('''
            1000: lw $3, 0xc($4)
            1004: lui $2, 0x2
            1008: and $5, $20, $6
            100c: addu $7, $2, $2
            1010: jr $ra
            1014: nop''')
        self.assertEqual(flags(db, 0x20000), [])

    def test_unrelated_word_at_the_same_immediate_is_not_a_hit(self):
        db = scan('''
            1000: lw $3, 0xc($4)
            1004: lw $2, 0x30($4)
            1008: andi $2, $2, 0x100
            100c: jr $ra
            1010: nop''')
        self.assertEqual(flags(db, 0x100), [])
        self.assertEqual(flags(db, 0x100, 0x30), ['1008:test'])

    def test_bit_number_chosen_at_run_time(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: addiu $3, $zero, 0x1
            1008: sllv $3, $3, $5
            100c: and $6, $2, $3
            1010: or $2, $2, $3
            1014: sw $2, 0xc($4)
            1018: jr $ra
            101c: nop''')
        self.assertEqual(flags(db, 0x100), ['100c:test(var)?', '1010:set(var)?'])
        self.assertEqual(flags(db, 0x100, certain=True), [])

    def test_mask_passed_as_an_argument_is_resolved_at_the_call_site(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: or $2, $2, $5
            1008: jr $ra
            100c: sw $2, 0xc($4)
            2000: addiu $sp, $sp, -0x10
            2004: sd $ra, 0x0($sp)
            2008: lui $5, 0x2
            200c: jal 0x1000 <x>
            2010: move $4, $16
            2014: addiu $5, $zero, 0x40
            2018: jal 0x1000 <x>
            201c: move $4, $16
            2020: ld $ra, 0x0($sp)
            2024: jr $ra
            2028: addiu $sp, $sp, 0x10''',
                  bodies=[(0x1000, [(0x1000, 0x100f)]), (0x2000, [(0x2000, 0x202b)])])
        self.assertEqual(flags(db, 0x20000), ['1004:set(a1)?', '200c:set>1000?'])
        self.assertEqual(flags(db, 0x40), ['1004:set(a1)?', '2018:set>1000?'])
        self.assertEqual(flags(db, 0x80), ['1004:set(a1)?'])

    def test_mask_that_is_a_narrowed_loaded_value(self):
        # copy one bit from another object's word: only that bit can be set
        db = scan('''
            1000: lw $2, 0xc($5)
            1004: andi $2, $2, 0x100
            1008: lw $3, 0xc($4)
            100c: or $3, $3, $2
            1010: sw $3, 0xc($4)
            1014: jr $ra
            1018: nop''')
        self.assertEqual(flags(db, 0x100), ['1004:test', '100c:set'])
        self.assertEqual(flags(db, 0x200), [])

    def test_whole_word_stores(self):
        db = scan('''
            1000: lui $2, 0x2
            1004: sw $2, 0xc($4)
            1008: lw $3, 0xc($5)
            100c: sw $3, 0xc($6)
            1010: sw $7, 0xc($4)
            1014: sb $zero, 0xe($4)
            1018: jr $ra
            101c: nop''')
        hits, hidden = gx.query_flag(db, 0x20000)
        self.assertEqual((hits, hidden), ([], 4))
        self.assertEqual(flags(db, 0x20000, stores=True),
                         ['1004:store=20000', '100c:copy<+c', '1010:store?', '1014:store=0'])
        # the byte store does not reach bit 8
        self.assertEqual(flags(db, 0x100, stores=True),
                         ['1004:store=20000', '100c:copy<+c', '1010:store?'])

    def test_same_field_loaded_on_two_paths(self):
        # the compiler copies the first instruction of a branch target into the delay slot
        db = scan('''
            1000: beqz $5, 0x1010 <x>
            1004: lw $6, 0xc($4)
            1008: addiu $7, $7, 0x1
            100c: lw $6, 0xc($4)
            1010: lui $2, 0x2
            1014: and $2, $6, $2
            1018: jr $ra
            101c: nop''')
        self.assertEqual(flags(db, 0x20000), ['1014:test'])

    def test_flag_word_through_a_formed_pointer_and_at_a_fixed_address(self):
        db = scan('''
            1000: addiu $5, $4, 0xa0
            1004: lw $2, 0x8($5)
            1008: andi $2, $2, 0x4
            100c: lui $3, 0x50
            1010: lw $3, 0x10c($3)
            1014: andi $3, $3, 0x4
            1018: jr $ra
            101c: nop''')
        self.assertEqual(flags(db, 0x4, 0xa8), ['1008:test{d}'])
        self.assertEqual(flags(db, 0x4, 0xc), [])
        self.assertEqual(flags(db, 0x4, 0xc, static=(0x500100,)), ['1014:test'])

    def test_filters_and_formatting(self):
        db = scan('''
            1000: lw $2, 0xc($4)
            1004: andi $2, $2, 0x300
            1008: lw $3, 0xc($5)
            100c: andi $3, $3, 0x100
            1010: jr $ra
            1014: nop''')
        self.assertEqual(flags(db, 0x100), ['1004:test:300', '100c:test'])
        self.assertEqual(flags(db, 0x100, this=True), ['1004:test:300'])
        self.assertEqual(flags(db, 0x100, addr_range=(0x1008, 0x1010)), ['100c:test'])
        hits, _ = gx.query_flag(db, 0x100)
        lines = gx.format_hits(hits, 0x100, db, {0x1000: 'Thing_run'})
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('0x1000 Thing_run'))


if __name__ == '__main__':
    unittest.main()
