"""Synthetic slot images for tools/ref_save.py. No game file and no real save."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry or '.') != _HERE]
import dis  # noqa: E402,F401
sys.path.insert(0, _HERE)

import struct  # noqa: E402
import unittest  # noqa: E402

import ref_save as S  # noqa: E402


def _record(name=b'Aria', gold=777, xp=5000, level=4, ack=3, define=3, count=1,
            equipped=True, live_base=0x4D8AF0, object_addr=0x01100000):
    rec = bytearray(S.RECORD_SIZE)
    rec[:len(name)] = name
    rec[len(name)] = 0
    rec[0x20:0x24] = bytes((1, 2, 3, 4))
    struct.pack_into('<ii', rec, 0x50, 1, 6)
    rec[0x58] = ack
    rec[0x59] = level
    struct.pack_into('<i', rec, 0x5C, xp)
    struct.pack_into('<4i', rec, 0x78, 46, 37, 24, 28)
    struct.pack_into('<i', rec, 0xE4, gold)
    struct.pack_into('<i', rec, 0xE8, 2)
    rec[0xEC] = 5
    rec[0xEF] = 1
    if count:
        struct.pack_into('<i', rec, S.BAG_COUNT_AT, count)
        struct.pack_into('<i', rec, S.BAG_ITEM_AT, S.definition_pointer(define))
        struct.pack_into('<h', rec, S.BAG_ITEM_AT + 4, 4)
    struct.pack_into('<i', rec, 0x43D8, object_addr)
    if equipped and count:
        struct.pack_into('<i', rec, 0x43F0, live_base + S.BAG_ITEM_AT)
        struct.pack_into('<i', rec, 0x4434, live_base + S.BAG_ITEM_AT)
    struct.pack_into('<hh', rec, 0x4B08, 7, 2)
    struct.pack_into('<h', rec, 0x4B0C, -1)
    rec[0x4C1A] = 0x03
    rec[0x4C1B] = 0x01
    rec[0x4C1C] = 0x01
    rec[0x4BBF + 13] = 0x03
    return bytes(rec)


def _inputs(**over):
    live = 0x4D8AF0
    player = S.LiveCharacter(_record(live_base=live), live, facing=0x1234, position=(1.0, 2.0, 3.0))
    base = dict(
        level_name='crypt', subname='', play_time=12345, difficulty=2, save_arg=7, act=0,
        num_players=1, players=(player,), minimap=3, jump_count=2,
        jump_dest=bytes([0xAB]) + bytes(S.JUMP_DEST_SIZE - 1),
        quests=(('opened', 7), ('door', -2)),
        acts=((('crypt', 0x2000),),),
        camera=S.pack_camera((10.0, 20.0, 30.0), list(range(16)), 1, 2, 3, 4,
                             (0.25, 0.5, 0.75), bytes(range(0x60))),
    )
    base.update(over)
    return S.SlotInputs(**base)


class LayoutTest(unittest.TestCase):
    def test_fixed_offsets(self):
        self.assertEqual(S.PLAYERS_AT + 4 * S.BLOCK_SIZE, S.QUESTS_AT)
        self.assertEqual(S.QUESTS_AT & 3, 0)
        self.assertEqual(S.DIRECTORY_AT, 0x16010)
        # Ten slots, then one unused stride, then the level bytes. The unused stride is
        # where a search that walks off the ten looks.
        self.assertEqual(S.DATA_AT, S.DIRECTORY_AT + (S.DIRECTORY_SLOTS + 1) * S.DIRECTORY_STRIDE)
        self.assertEqual(len(S.pack_automap(b'')), S.AUTOMAP_SIZE)
        self.assertEqual(len(S.frame_level_state(S.EMPTY_WORLD, S.EMPTY_DECAL, bytes(S.AUTOMAP_SIZE))),
                         32 + S.AUTOMAP_SIZE)

    def test_reserved_rounding(self):
        self.assertEqual(S.round_reserved(0, 0x16C8), 0x1A80)
        self.assertEqual(S.round_reserved(0x100, 0x16C8) & 0x7F, 0)

    def test_automap_nibbles(self):
        grid = bytearray(S.AUTOMAP_GRID_SPAN)
        grid[1] = 0xF0
        grid[5] = 0x07
        grid[9] = 0x10
        grid[13] = 0xA0
        grid[0x361] = 0x20
        grid[0x365] = 0x30
        packed = S.pack_automap(grid)
        self.assertEqual(packed[0], 0xF0)
        self.assertEqual(packed[1], 0x1A)
        self.assertEqual(packed[54], 0x23)
        self.assertEqual(packed[-1], 0)


class ChecksumTest(unittest.TestCase):
    def test_zero_record_ignores_nothing_but_the_address(self):
        record = bytes(S.RECORD_SIZE)
        self.assertEqual(S.player_checksum(0, 0, record), 0xBF50531A)
        self.assertNotEqual(S.player_checksum(0, 0x4D8AF0, record),
                            S.player_checksum(0, 0x879EC0, record))
        self.assertNotEqual(S.player_checksum(0, 0x4D8AF0, record),
                            S.player_checksum(1, 0x4D8AF0, record))

    def test_weight_zero_word_is_not_mixed(self):
        left = bytearray(S.RECORD_SIZE)
        right = bytearray(left)
        left[0x90] = 0x3C
        right[0x93] = 0x7F
        self.assertEqual(S.player_checksum(0, 0x1000, left), S.player_checksum(0, 0x1000, right))
        right[0x94] = 1
        self.assertNotEqual(S.player_checksum(0, 0x1000, left), S.player_checksum(0, 0x1000, right))


class ItemTest(unittest.TestCase):
    def test_definition_round_trip(self):
        pointer = S.definition_pointer(3)
        self.assertEqual(pointer, 0x3F7710)
        self.assertEqual(S.definition_index(pointer), 3)

    def test_equipment_index_and_null(self):
        base = 0x4D8AF0
        self.assertEqual(S.pointer_to_index(0, base, (1, 0, 0)), -1)
        self.assertEqual(S.pointer_to_index(base + S.BAG_ITEM_AT, base, (1, 0, 0)), 0)
        self.assertEqual(S.pointer_to_index(base + S.BAG_ITEM_AT + S.BAG_STRIDE, base, (0, 1, 0)), 1000)
        self.assertEqual(S.index_to_pointer(-1, base, (1, 0, 0)), 0)
        self.assertEqual(S.index_to_pointer(0, base, (1, 0, 0)), base + S.BAG_ITEM_AT)
        self.assertEqual(S.index_to_pointer(5, base, (1, 0, 0)), 0)

    def test_snapshot_replaces_pointers(self):
        base = 0x4D8AF0
        saved = S.encode_saved_record(_record(live_base=base), base)
        self.assertEqual(struct.unpack_from('<i', saved, S.BAG_ITEM_AT)[0], 3)
        self.assertEqual(struct.unpack_from('<i', saved, 0x43F0)[0], 0)
        self.assertEqual(struct.unpack_from('<i', saved, 0x4434)[0], 0)
        self.assertEqual(struct.unpack_from('<i', saved, 0x443C)[0], -1)
        self.assertEqual(struct.unpack_from('<I', saved, 0x43D8)[0], 0x01100000)
        loaded = S.decode_loaded_record(saved, base)
        self.assertEqual(struct.unpack_from('<I', loaded, S.BAG_ITEM_AT)[0], 0x3F7710)
        self.assertEqual(struct.unpack_from('<I', loaded, 0x43F0)[0], base + S.BAG_ITEM_AT)
        self.assertEqual(struct.unpack_from('<I', loaded, 0x43D8)[0], 0)


class SlotTest(unittest.TestCase):
    def test_round_trip_character_and_quests(self):
        image = S.build_slot(_inputs())
        slot = S.parse_slot(image)
        self.assertEqual(slot.level_name, 'crypt')
        self.assertEqual(slot.subname, '')
        self.assertEqual(slot.play_time, 12345)
        self.assertEqual(slot.record_size, S.RECORD_SIZE)
        self.assertEqual(slot.listed_count, 1)
        self.assertEqual(slot.player_count, 1)
        self.assertEqual(slot.difficulty, 2)
        self.assertEqual(slot.save_arg, 7)
        self.assertEqual(slot.act, 0)
        self.assertEqual(slot.minimap_mode, 3)
        self.assertEqual(slot.jump_count, 2)
        self.assertEqual(slot.jump_destinations[0], 0xAB)
        self.assertEqual(slot.quests, (('opened', 7), ('door', -2)))
        hero = S.import_character(image)
        self.assertEqual(hero.name, 'Aria')
        self.assertEqual(hero.gold, 777)
        self.assertEqual(hero.experience, 5000)
        self.assertEqual(hero.level, 4)
        self.assertEqual(hero.acknowledged_level, 3)
        self.assertEqual(hero.base_stats, (46, 37, 24, 28))
        self.assertEqual(hero.class_index, 1)
        self.assertEqual(hero.model_index, 6)
        self.assertEqual(hero.bags[0][0].definition_index, 3)
        self.assertEqual(hero.bags[0][0].quantity, 4)
        self.assertEqual(hero.equipment[0], 0)
        self.assertEqual(hero.weapon_sets[0], 0)
        self.assertEqual(hero.offhand, -1)
        self.assertEqual(hero.skills, ((7, 2),))
        self.assertEqual(hero.kind, 1)
        self.assertEqual(hero.evil_bits, 3)
        self.assertEqual(hero.facing, 0x1234)
        self.assertEqual(hero.position, (1.0, 2.0, 3.0))
        self.assertEqual(len(slot.levels), 1)
        self.assertEqual(slot.levels[0].name, 'crypt')
        self.assertEqual(slot.levels[0].size, 0x2000)
        self.assertEqual(slot.levels[0].world, S.EMPTY_WORLD)
        self.assertEqual(slot.levels[0].decal, S.EMPTY_DECAL)
        self.assertEqual(len(slot.levels[0].automap), S.AUTOMAP_SIZE)
        self.assertEqual(image[S.QUESTS_AT:S.QUESTS_AT + 7], b'opened\x00')
        self.assertEqual(struct.unpack_from('<i', image, S.QUESTS_AT + 0x20)[0], 7)
        door = S.QUESTS_AT + S.QUEST_STRIDE
        self.assertEqual(struct.unpack_from('<i', image, door + 0x20)[0], -2)

    def test_one_player_flag_does_not_change_the_loaded_count(self):
        second = S.LiveCharacter(_record(name=b'Bram', live_base=0x4D8AF0 + S.RECORD_SIZE,
                                          object_addr=0x01100200),
                                 0x4D8AF0 + S.RECORD_SIZE, facing=9, position=(4.0, 5.0, 6.0))
        first = _inputs().players[0]
        image = S.build_slot(_inputs(num_players=2, one_player=True, players=(first, second),
                                      memcard_state=4))
        slot = S.parse_slot(image)
        self.assertEqual(slot.listed_count, 1)
        self.assertEqual(slot.player_count, 2)
        self.assertEqual([c.name for c in slot.characters], ['Aria', 'Bram'])
        self.assertEqual(slot.levels, ())

    def test_hub_uses_the_first_row_size(self):
        image = S.build_slot(_inputs(level_name='hub', subname='west',
                                      acts=((('town', 0x1800), ('hub', 0x1000)),)))
        slot = S.parse_slot(image)
        self.assertEqual(slot.level_name, 'hub')
        self.assertEqual(slot.subname, 'west')
        self.assertEqual([(level.name, level.size) for level in slot.levels], [('hub_west', 0x1800)])

    def test_missing_act_leaves_the_buffer_alone(self):
        previous = bytes([0x5A]) * S.FILE_SIZE
        image = S.build_slot(_inputs(level_name='nope', previous=previous))
        self.assertEqual(image, previous)

    def test_game_complete_keeps_the_name_tail_and_skips_the_directory(self):
        previous = bytearray(S.FILE_SIZE)
        previous[13:0x14] = b'\x11' * 7
        image = S.build_slot(_inputs(game_complete=True, previous=bytes(previous)))
        self.assertEqual(image[:13], b'gameComplete\x00')
        self.assertEqual(image[13:0x14], b'\x11' * 7)
        self.assertEqual(image[S.DIRECTORY_AT], 0)
        slot = S.parse_slot(image)
        self.assertEqual(slot.level_name, 'gameComplete')
        self.assertEqual(slot.levels, ())

    def test_a_level_that_does_not_fit_keeps_the_new_name_and_skips_the_body(self):
        previous = bytearray(S.FILE_SIZE)
        previous[S.DATA_AT:S.DATA_AT + 4] = b'\x22\x22\x22\x22'
        S._write_cstr(previous, S.DIRECTORY_AT, 'old', 0x14)
        struct.pack_into('<I', previous, S.DIRECTORY_AT + 0x14, 0x40000)
        image = S.build_slot(_inputs(previous=bytes(previous)))
        self.assertEqual(S._directory_name(image, 0), 'old')
        self.assertEqual(S._directory_name(image, 1), 'crypt')
        self.assertEqual(image[S.DATA_AT:S.DATA_AT + 4], b'\x22\x22\x22\x22')

    def test_pose_falls_back_to_the_first_player_with_an_object(self):
        bare = S.LiveCharacter(_record(object_addr=0), 0x4D8AF0, facing=1, position=(9, 9, 9))
        other = S.LiveCharacter(_record(name=b'Bram', live_base=0x4D8AF0 + S.RECORD_SIZE,
                                         object_addr=0x01100200),
                                0x4D8AF0 + S.RECORD_SIZE, facing=0x2222, position=(8.0, 7.0, 6.0))
        image = S.build_slot(_inputs(memcard_state=4, num_players=2, players=(bare, other),
                                      alive_first=-1))
        hero = S.import_character(image, 0)
        self.assertEqual(hero.name, 'Aria')
        self.assertEqual(hero.facing, 0x2222)
        self.assertEqual(hero.position, (8.0, 7.0, 6.0))

    def test_importer_refusals(self):
        image = bytearray(S.build_slot(_inputs()))
        with self.assertRaises(S.SaveError):
            S.parse_slot(bytes(image[:-1]))
        image[0x68] = 0
        with self.assertRaises(S.SaveError):
            S.parse_slot(bytes(image))
        image = bytearray(S.build_slot(_inputs()))
        struct.pack_into('<i', image, 0x31C, 5)
        with self.assertRaises(S.SaveError):
            S.parse_slot(bytes(image))
        struct.pack_into('<i', image, 0x31C, -1)
        with self.assertRaises(S.SaveError):
            S.parse_slot(bytes(image))
        image = bytearray(S.build_slot(_inputs()))
        image[S.QUESTS_AT:S.QUESTS_AT + 0x20] = b'\x41' * 0x20
        with self.assertRaises(S.SaveError):
            S.parse_slot(bytes(image))

    def test_set_player_count_writes_both_fields(self):
        image = S.set_player_count(S.build_slot(_inputs(num_players=2, one_player=True,
                                                         memcard_state=4,
                                                         players=_inputs().players * 2)), 1)
        slot = S.parse_slot(image)
        self.assertEqual(slot.listed_count, 1)
        self.assertEqual(slot.player_count, 1)
        self.assertEqual(len(slot.characters), 1)


class ConfigTest(unittest.TestCase):
    def test_default_image_and_the_two_button_orders(self):
        image = S.config_set_defaults(-1, scheme=1)
        parsed = S.parse_config(image)
        self.assertEqual(parsed.brightness, 0.5)
        self.assertEqual(parsed.music, 0.5)
        self.assertEqual(parsed.effects, 0.5)
        self.assertEqual(parsed.stereo, 1)
        self.assertEqual(parsed.vibration, 1)
        self.assertEqual(parsed.subtitles, 1)
        self.assertEqual(parsed.damage_numbers, 1)
        self.assertEqual(parsed.blood, 0)
        self.assertEqual(parsed.markers, 1)
        self.assertEqual(parsed.combat_camera, 1)
        self.assertEqual(parsed.reverse_yaw, 0)
        self.assertEqual(parsed.buttons[0][0], 0x40)
        self.assertEqual(parsed.buttons[3], parsed.buttons[0])
        other = S.config_set_defaults(-1, scheme=0)
        self.assertEqual(struct.unpack_from('<I', other, 0x34)[0], 0x20)
        self.assertEqual(struct.unpack_from('<I', other, 0x38)[0], 0x10)
        self.assertEqual(struct.unpack_from('<I', other, 0x3C)[0], 0x40)
        self.assertEqual(struct.unpack_from('<I', image, 0xC8)[0], 0x3E199999)
        odd = bytearray(S.CONFIG_SIZE)
        odd[0x34:0x38] = b'\x11\x11\x11\x11'
        kept = S.config_set_defaults(-1, scheme=2, image=bytes(odd))
        self.assertEqual(kept[0x34:0x38], b'\x11\x11\x11\x11')
        self.assertEqual(struct.unpack_from('<f', kept, 4)[0], 0.5)

    def test_profile_entries(self):
        image = bytearray(S.config_set_defaults())
        image[0xF8:0xF8 + 6] = b'hint\x00\x05'
        parsed = S.parse_config(bytes(image))
        self.assertEqual(parsed.profile, (('hint', 5),))
        with self.assertRaises(S.SaveError):
            S.parse_config(bytes(image[:-1]))


if __name__ == '__main__':
    unittest.main()
