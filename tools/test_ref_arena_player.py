"""Model-only checks of tools/ref_arena_player.py (no executable needed)."""
import unittest

import ref_arena_player as R


class ArenaPlayerModel(unittest.TestCase):
    def test_lcg_matches_documented_generator(self):
        seed, draw = R.lcg(7)
        self.assertEqual(seed, (7 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF)
        self.assertEqual(draw, seed >> 16)

    def test_grid_cell_on_and_off_grid(self):
        self.assertEqual(R.grid_cell(0x43480000, 0xC3480000), R.SA.G_GRID_A + 4 * (59 * 0x78 + 60))
        self.assertEqual(R.grid_cell(0x47000000, 0), R.SA.G_OFF_GRID)

    def test_idle_voice_threshold_by_slot(self):
        for slot in range(4):
            fields = R.constructor_fields(0x1000000, slot, 0x2000000)
            self.assertEqual(fields[0x1000000 + 0x4B2], (2, 3600 + 2700 * slot))

    def test_chain_draws_once_and_ors_flags(self):
        memory = {}
        writes, seed, calls = R.chain_writes(lambda a: memory.get(a, 0), 0x1000000,
                                             (0, 0, 0), 0, 0, 20973, 0x2000000, 0)
        final = R.final_bytes(writes)
        self.assertEqual(seed, R.lcg(20973)[0])
        self.assertEqual(sum(1 for a, _w, _v in writes if a == R.SEED), 1)
        self.assertEqual(int.from_bytes(bytes(final[0x100000C + i] for i in range(4)), 'little'), 0x4060)
        self.assertEqual(calls[0][0], R.CREATURE_CTOR)
        self.assertEqual(calls[1][0], R.GAMEOBJECT_CTOR)

    def test_destructor_frees_only_with_bit0(self):
        for flags, freed in ((0, False), (1, True), (3, True)):
            _writes, calls = R.destructor(0x1000000, 0, flags)
            self.assertEqual(calls[-1][0] == R.POOL_FREE, freed)

    def test_spawn_protection_counters(self):
        for network, recall, want in ((0, 0, [60]), (1, 0, [90]), (0, 1, [60, 1])):
            writes, _calls = R.spawn_protection(0x1000000, 0, network, recall, 1, 0, 1, 0, 0, 0)
            self.assertEqual([v for a, _w, v in writes if a == 0x1000000 + 0x4B4], want)

    def test_reset_timers_and_replacement_order(self):
        self.assertEqual(len(R.reset_timers()), 5)
        order = [c[0] for c in R.start_wave_replacement(0x1000000, 0, 0x1F00000, 0)]
        self.assertEqual(order, [R.PICK_SPAWN, R.PLAYER_DTOR, R.POOL_NEW, R.CTOR, R.RESET_TIMERS])


if __name__ == '__main__':
    unittest.main()
