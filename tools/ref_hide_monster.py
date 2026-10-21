#!/usr/bin/env python3
"""ref_hide_monster.py - the script commands hideMonster 0x144c00 and showMonster 0x144db8,
with their real callees, on the object world of tools/ref_objects.py.

Contract: docs/spec/hide-monster.md.  Checked against the original by
tools/difftest_hide_monster.py; synthetic tests in tools/test_ref_hide_monster.py.

Both handlers are entered as (machine, params).  They fetch one string argument
(scr_getAddr 0x1414a8 on params[1], then scr_getString 0x141650 into a 0xa0-byte stack
buffer), ask world_findObjectsByName 0x14bf58 for at most 0x1ff objects of that name
(limit 0x200, a 0x800-byte stack array), and for every object found, in the order the
name table gives:

  hideMonster: obj_moveOffGrid(obj)    0x14ef48   grid node to the front of g_offGridList
               flags +0x0c |= 0x8000              (re-read after the call)
               if that word has 0x20:  byte +0x231 |= 8
  showMonster: obj_updateGridCell(obj) 0x14f028   grid node to the front of the list of
                                                   its current position
               flags +0x0c &= ~0x8000
               if that word has 0x20:  byte +0x231 &= 0xf7

They return 0, draw nothing from the shared seed and call nothing else.

Byte +0x231 is not a GameObject field (the base object is 0x4c bytes), so the model keeps it
in a dictionary {object address: byte} that the caller owns.  For a non-creature the byte
is never touched.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_objects as O                 # noqa: E402

HIDE_MONSTER = 0x144C00
SHOW_MONSTER = 0x144DB8
SCR_GET_ADDR = 0x1414A8
SCR_GET_STRING = 0x141650
FIND_BY_NAME = 0x14BF58                 # world_findObjectsByName(name, out, limit)
MOVE_OFF_GRID = 0x14EF48                # obj_moveOffGrid
UPDATE_GRID_CELL = 0x14F028             # obj_updateGridCell
NAME_LIMIT = 0x200                      # the limit both handlers pass (0x144c30, 0x144de8)
NAME_BUFFER = 0xA0                      # stack bytes for the name (sp .. sp+0xa0)

OFF_FLAGS = 0x0C
FLAG_CREATURE = 0x20                    # set only by Creature_ctor (0x109e5c)
FLAG_NOT_RUN = 0x8000                   # runObjects skips slot 4
OFF_HIDDEN = 0x231                      # creature byte; bit 3 = hidden
HIDDEN_BIT = 0x08
M32 = 0xFFFFFFFF


def _targets(world, name):
    return world.names.find(bytes(name), NAME_LIMIT)


def hide_monster(world, name, hidden_bytes, trace=None):
    """0x144c00.  `hidden_bytes` maps object address -> byte +0x231 (creatures only need
    an entry).  Returns 0.  `trace`, when a list, receives (callee, object address)."""
    for obj in _targets(world, name):
        if trace is not None:
            trace.append(('obj_moveOffGrid', obj.addr))
        world.move_off_grid(obj)
        obj.flags = (obj.flags | FLAG_NOT_RUN) & M32
        if obj.flags & FLAG_CREATURE:
            hidden_bytes[obj.addr] = (hidden_bytes.get(obj.addr, 0) | HIDDEN_BIT) & 0xFF
    return 0


def show_monster(world, name, hidden_bytes, trace=None):
    """0x144db8: the reverse.  Returns 0."""
    for obj in _targets(world, name):
        if trace is not None:
            trace.append(('obj_updateGridCell', obj.addr))
        world.update_grid_cell(obj)
        obj.flags = obj.flags & ~FLAG_NOT_RUN & M32
        if obj.flags & FLAG_CREATURE:
            hidden_bytes[obj.addr] = hidden_bytes.get(obj.addr, 0) & ~HIDDEN_BIT & 0xFF
    return 0


def needs(world, name):
    """What a port must know about each object the name finds to run either handler:
    (address, is_creature, has_grid_link).  A target without a grid link makes the
    original follow a null pointer inside obj_moveOffGrid / obj_updateGridCell."""
    return [(o.addr, bool(o.flags & FLAG_CREATURE), o.heads[2].next is not None) for o in _targets(world, name)]
