#!/usr/bin/env python3
"""Reproduce the native synthetic Gnaw and Skelight statistics expectations.

The underlying function is difftested against Creature_setStats by
``difftest_combat.py --quick -k monster``. These are authored test inputs, not
content copied from the game.
"""
import ref_combat as combat


def check():
    tables = combat.Tables()
    tables.fixed_levels = ('stomedal', 'innpit')
    world = combat.World()
    world.num_players = 1
    world.difficulty = 1
    world.level_name = 'testlevel'
    shared = combat.Seed(20973)
    own = combat.Seed(shared.draw())
    first_own_draw = own.draw()
    factor_100 = combat.fmul(combat.itof(100), 0x3c23d70a)

    world.monster_level = combat.itof(2)
    gnaw = combat.monster_stats(tables, world, (factor_100,) * 5, 0,
                                'Gnaw', True, own_draw=first_own_draw)
    assert (gnaw['hp'], gnaw['armor'], gnaw['dmg_low'], gnaw['dmg_high'],
            gnaw['attack'], gnaw['exp_value']) == (
                0x41edee1a, 27, 3, 6, 27, 0x41a00000)
    print('Gnaw level 2: hp=%#x armor=%d damage=%d/%d attack=%d exp=%#x' % (
        gnaw['hp'], gnaw['armor'], gnaw['dmg_low'], gnaw['dmg_high'],
        gnaw['attack'], gnaw['exp_value']))

    # The Skelight constructor temporarily installs its supplied level 1 and
    # calls Creature_setStats with its own five factors. Its earlier base
    # Creature_ctor has no class name and makes no statistics draw.
    world.monster_level = combat.itof(1)
    skelight = combat.monster_stats(
        tables, world, (0x3faa3d70, 0x3f999999, 0x3f999999,
                        combat.ONE, combat.ONE), 0, 'Skelight', True,
        own_draw=first_own_draw)
    assert skelight['hp'] == 0x41a8355b
    print('Skelight constructor level 1: hp=%#x' % skelight['hp'])


if __name__ == '__main__':
    check()
