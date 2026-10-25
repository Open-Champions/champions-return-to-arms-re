#!/usr/bin/env python3
"""ref_levels.py - reference contract of how Champions: Return to Arms (SLUS_209.73) picks,
loads, enters and leaves a level: the file manifest, the level-table row, the start
markers and player placement, the level-change requests (exits, jump gates, recall, party
wipe), what survives a change, moving pieces, the water queries and the texture
addressing of WORLD geometry.

A research tool, not game code.  Each function was written from the instruction sequence
at the address in its docstring; docs/level-flow.md is the prose version and says, per
statement, what was observed, inferred or is unknown.  Nothing here was compared with the
running game.  Re-read instruction by instruction for this module: find_moving_piece,
water_test, the spawn height pass of place_players, the light order of chunk_header_state
and the REL table; the rest was read once, by one reader (see the document).  Standard
library only, plus tools/ref_world.py for the console's float arithmetic; no game data is
embedded.  The level names below are short identifiers the executable itself compares
against (CONTRIBUTING.md allows those).

Where a step draws from the shared random seed or queries the terrain, the function takes
a callback, so that a caller can plug in tools/ref_objects.py (find_free_spot, the shared
generator) and tools/ref_world.py (terrain_height) or a test double.

Sections: 1 names, 2 level table, 3 manifest, 4 objects.ob, 5 start markers and
placement, 6 level-change requests, 7 acts, saved level states and the change itself,
8 triggers, 9 jump gates, 10 recall and party wipe, 11 moving pieces, 12 water,
13 texture addressing and materials.  Round 3 (placement on a floor the origin
test misses, and the arena's first search) is at the bottom of the file.
"""
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # appended: tools/dis.py must not shadow the standard dis
import ref_world as W                                # noqa: E402

f32, to_float = W.f32, W.to_float
NAME_BUF = 0x50                     # every level-name buffer is 0x50 bytes (strcpy, no check)


class MissingResource(Exception):
    """A required file or lump is absent.  The game does not recover: lump_load 0x173558
    stores to address 0 after printing an error (0x173630-0x17363c), and the raw
    CD read 0x1729e8 does the same (0x172a4c-0x172a64)."""


# =======================================================================================
# 1. Names
# =======================================================================================

def split_request(request):
    """mainloop_loadRequestedWorld 0x320edc (0x321064-0x3210f8): split the pending name at
    the FIRST '_' into (base, sub).  sub is '' when there is no '_'."""
    base, sep, sub = request.partition('_')
    return base, sub


def qualified_name(base, sub):
    """level_getQualifiedName 0x1ec0f0: 'base_sub', or 'base' when sub is empty.  This is
    what g_prevLevelName, the saved-state directory and the jump-gate list hold."""
    return base + '_' + sub if sub else base


# loadscreen_selectWorldAlias 0x321c9c-0x321e50, first match wins.  ('in', s) tests
# strstr(name, s); ('eq', s) tests strcmp.  For the 'in' rules that carry a mapping only
# names equal to a key change; others containing the substring are kept as they are.
_PICTURE_ALIASES = (
    ('in', 'blo', 'blood1'),
    ('eq', 'innovat2', 'innova2'),
    ('in', 'val', 'valor'),
    ('in', 'bas', 'bastion1'),
    ('in', 'nitdung', {'nitdung1': 'nitdun1', 'nitdung2': 'nitdun2', 'nitdung4': 'nitdun4'}),
    ('in', 'torme', {'tormenta': 'torma', 'tormentb': 'tormb', 'torment2': 'torm2',
                     'torment3': 'torm3'}),
    ('eq', 'pvpfire2', 'pvpfir2'),
)


def loading_picture_alias(base):
    """loadscreen_selectWorldAlias 0x321c9c on g_levelTexName (= base)."""
    for kind, key, value in _PICTURE_ALIASES:
        if (kind == 'in' and key in base) or (kind == 'eq' and base == key):
            if isinstance(value, dict):
                return value.get(base, base)
            return value
    return base


def loading_picture_files(base):
    """loadscreen_start 0x321e60: the files tried, in order.  'l' + alias, cut to 8
    characters (byte 8 set to 0 at 0x321ee4-0x321f0c), + '.lmp'; when cd_findFile fails the
    same name is tried once more (redundant), then 'lmiss.lmp'.  The CD layer upper-cases
    (cd_findFile 0x1724fc), so the disc name is the upper-case form."""
    first = ('l' + loading_picture_alias(base))[:8] + '.lmp'
    return [first, 'lmiss.lmp']


def cd_file_name(name):
    """cd_findFile 0x1724fc: the directory entry compared against (exact compare)."""
    return name.upper() + ';1'


# =======================================================================================
# 2. Level table (g_levelTable 0x4f7210: 90 rows of 0x30 bytes + a default row)
# =======================================================================================

class LevelRow:
    """One row as game_loadLevel uses it (docs/data-tables.md 7.1).  Defaults are the
    terminator row, which is also the default row (0x4f7210 + 90 * 0x30)."""

    def __init__(self, name=None, monster_level=1, b05=2, kill_plane=-100000.0, f0c=-100000.0,
                 f10=100000.0, water_pool=48, b18=0, f1c=1.0, flags=0, sound=(0, 0, 0, 0), w2c=0):
        self.name = name
        self.monster_level = monster_level      # +0x04 s8
        self.b05 = b05                          # +0x05 s8, x 0.25 -> 0x41c16c/0x41c170
        self.kill_plane = kill_plane            # +0x08 -> g_killPlaneZ 0x4f7188
        self.f0c, self.f10 = f0c, f10           # +0x0c, +0x10 -> 0x4f718c, 0x4f7190
        self.water_pool = water_pool            # +0x14 water simulation blocks (section 12)
        self.b18, self.f1c = b18, f1c           # +0x18 -> 0x4f7208, +0x1c -> 0x44f030
        self.flags = flags                      # +0x20 -> 0x44fe08
        self.sound = tuple(sound)               # +0x24..+0x2a -> 0x2156e0
        self.w2c = w2c                          # +0x2c (lhu) -> 0x4f7152


DEFAULT_ROW = LevelRow()

LEVEL_FLAG_WATER_FULL_MASK = 0x8           # water_setup 0x187628 fills every mask
LEVEL_FLAG_WATER_SPLASH = 0x10             # random splashes when drawn (cosmetic)
LEVEL_FLAG_NO_LEVEL_STATE = 0x800          # save_storeLevelState 0x21777c stores nothing
LEVEL_FLAG_DEADLY_WATER = 0x1000           # Player_move: lethal damage in water
LEVEL_FLAG_LIGHT_40 = 0x04000000           # base light level 0x40; tested second, so it wins (0x1e611c)
LEVEL_FLAG_LIGHT_20 = 0x20000000           # base light level 0x20; tested first (0x1e6108)


def find_level_row(rows, base, sub):
    """game_loadLevel 0x1e55c0 (0x1e5790-0x1e58c8).  rows is the table in order (without
    the terminator).  Three passes, first match of each pass in table order:

      1. strcmp(row, base + '_' + sub) == 0    the '_' is always appended (0x1e57ec)
      2. row starts with base                  strncmp(base, row, len(base)) (0x1e584c)
      3. row occurs inside base                strstr(base, row) (0x1e58b8)

    No match: the default row.  So a plain name is resolved by pass 2 and the order of the
    rows is part of the data."""
    request = base + '_' + sub
    for row in rows:
        if row.name == request:
            return row
    for row in rows:
        if row.name.startswith(base):
            return row
    for row in rows:
        if row.name in base:
            return row
    return DEFAULT_ROW


def monster_level(row, difficulty, base, pvp_mode_b=False):
    """g_levelMonsterLevel 0x4f714c (0x1e5b70-0x1e5c94, docs/spec/combat.md 4.1).  Returned
    as a Python float; the store order is reproduced: the PvP value is overwritten by the
    difficulty 2-5 lines, then the two fixed levels."""
    value = float(row.monster_level + 2)
    if pvp_mode_b and difficulty == 1:
        value = 3.0
    if difficulty in (2, 3, 4, 5):
        value = (row.monster_level + 2) * 0.75 + {2: 34, 3: 61, 4: 88, 5: 115}[difficulty]
    if base == 'stomedal':
        value = 1.0
    elif base == 'innpit':
        value = 2.0
    return value


def level_light_alpha(flags):
    """0x1e60e0-0x1e6154: the base light level handed to light_setLevelLight 0x14a2d8 as
    its stack argument, which stores it in g_worldLightLevel 0x5d347c (docs/lighting.md).
    Round 2 (2026-10-18): it is NOT an alpha - the two alpha bytes 0x5d3473/0x5d347b get
    the other stack argument, 0.  0x20000000 is tested first (movn at 0x1e6108) and
    0x04000000 second (movn at 0x1e611c), so with both bits the result is 0x40.  The name
    is kept for API stability; base_light_level is the same function.  Executed:
    tools/difftest_levels.py property light_level."""
    alpha = 0x80
    if flags & LEVEL_FLAG_LIGHT_20:
        alpha = 0x20
    if flags & LEVEL_FLAG_LIGHT_40:
        alpha = 0x40
    return alpha


# =======================================================================================
# 3. Manifest: which files make a level, in load order
# =======================================================================================

HUD_LUMPS = ('fx.lmp', 'hud.lmp', 'mapicons.lmp', 'icons.lmp')     # 0x1e56a0, keep level 10
LEVEL_FIXED_LUMPS = ('gooddog.lmp', 'skele_b.lmp')                  # 0x1e5cf4-0x1e5d0c
GOB_RENAMES = {'gaydark1.lmp': 'faydark1.lmp', 'gaydark2.lmp': 'faydark2.lmp'}   # 0x173908


class Resource:
    def __init__(self, step, name, where, required, note=''):
        self.step, self.name, self.where, self.required, self.note = step, name, where, required, note

    def __repr__(self):
        return 'Resource(%r, %r, %r, %s)' % (self.step, self.name, self.where,
                                            'required' if self.required else 'optional')


def gob_lump_offsets(names_and_sizes):
    """gob_loadAll 0x1737d8: the directory (0x800 bytes of 0x28-byte records) gives names
    and sizes; the offset field is IGNORED: lumps are read back to back from 0x800, each
    rounded up to 0x800 (0x173890-0x1738a8).  Returns [(name after renames, offset, size)]."""
    out, offset = [], 0x800
    for name, size in names_and_sizes:
        out.append((GOB_RENAMES.get(name, name), offset, size))
        offset += (size + 0x7FF) & ~0x7FF
    return out


def level_manifest(base, sub='', gob_lumps=(), level_entries=(), model_lumps=(),
                   disc_files=(), loaded_lumps=(), hud_loaded=False, recall_leg=False,
                   pvp_mode_b=False):
    """game_loadLevel 0x1e55c0 and the functions it calls, as a list of Resource in the
    order they are opened.  Inputs describe what exists:

      gob_lumps      lump names inside <BASE>.GOB (after GOB_RENAMES)
      level_entries  entry names inside <base>.lmp IN DIRECTORY ORDER (after lump_fixup:
                     'ntsc_dialog.bin' is 'dialog.bin', 'pal_*' entries dropped; the
                     fixup removes entries but never reorders them)
      model_lumps    the lump names of the world's flag-0x800 chunks (chunk data +0x00)
      disc_files     upper-case names of loose files on the disc (no ';1')
      loaded_lumps   lumps already resident (lump_load returns them without a read)

    Raises MissingResource for the first required file that is absent, as the game would
    crash there.  The player lumps (game_loadPlayerLumps 0x1e5148) and arena lumps are
    named but not checked."""
    disc = set(n.upper() for n in disc_files)
    lumps = set(gob_lumps) | set(loaded_lumps)
    entries = set(level_entries)
    out = []

    def need(step, name, where, present, note=''):
        out.append(Resource(step, name, where, True, note))
        if not present:
            raise MissingResource('%s (%s, step %s)' % (name, where, step))

    def maybe(step, name, where, note=''):
        out.append(Resource(step, name, where, False, note))

    intro = base == 'intro'
    if not intro and not hud_loaded:
        for name in HUD_LUMPS:
            need('4a', name, 'disc', name.upper() in disc or name in lumps)
    if not intro:
        out.append(Resource('4b', 'player model lumps', 'disc', True, 'game_loadPlayerLumps 0x1e5148'))
    picture = loading_picture_files(base)
    if picture[0].upper() in disc:
        maybe('5', picture[0], 'disc', 'loading picture, entry shot.tex')
    else:
        maybe('5', picture[1], 'disc', 'fallback loading picture')
    need('5', 'loadmisc.lmp', 'disc', 'LOADMISC.LMP' in disc or 'loadmisc.lmp' in lumps)
    need('7', base + '.gob', 'disc', (base + '.gob').upper() in disc)
    need('7', base + '.tex', 'disc', (base + '.tex').upper() in disc,
         'first 0x5000 bytes read by world_fixup 0x181f08 while the GOB loads')
    need('7', base + '.lmp', 'gob', base + '.lmp' in lumps)
    # Round 2 (2026-10-18): lump_findNthByExtension(lmp, 'world', 0) walks the directory in
    # its stored order; round 1 sorted the names here, against its own prose.
    world = first_entry_with_extension(level_entries, 'world')
    need('8', world if world is not None else '*.world', base + '.lmp', world is not None,
         'first entry with extension world in directory order (lump_findNthByExtension 0x171fd8)')
    if not recall_leg:
        maybe('10', 'dialog.bin', base + '.lmp', 'voice directory; first record containing enttag')
    maybe('11', 'ambient.bin', base + '.lmp', 'ambient_parse(text) or ambient_parse(0)')
    if pvp_mode_b:
        for name in ('arena.lmp', 'pvpfont.lmp'):
            need('14', name, 'disc', name.upper() in disc or name in lumps)
    if not intro:
        for name in LEVEL_FIXED_LUMPS:
            need('15', name, 'disc', name.upper() in disc or name in lumps)
    for name in model_lumps:
        lump = name + '.lmp'
        need('16', lump, 'gob or disc', lump in lumps or lump.upper() in disc,
             'world_prepare 0x182360, flag-0x800 chunk')
    maybe('17', 'dome.lmp', 'gob', 'lump_findLoaded; 0 when absent')
    need('18', 'waterenv.lmp', 'gob', 'waterenv.lmp' in lumps, 'water_setup: its first .tex entry')
    if base == 'hub':
        need('26', 'msel.lmp', 'disc', 'MSEL.LMP' in disc or 'msel.lmp' in lumps)
    maybe('28', 'script.scr', base + '.lmp', 'absent or empty: no script machine')
    need('28', 'objects.ob', base + '.lmp', 'objects.ob' in entries,
         'world_loadRecords is given the entry without a null test (0x217b7c)')
    maybe('32', 'env.lmp', 'gob', 'environment texture uploaded after the load (mainloop step 11)')
    return out


# =======================================================================================
# 4. objects.ob
# =======================================================================================

class Record:
    def __init__(self, cls, angle, x, y, z, props):
        self.cls, self.angle, self.x, self.y, self.z, self.props = cls, angle, x, y, z, list(props)

    def prop(self, key):
        """First 'key=value' property, compared case-sensitively up to '='; None if absent.
        (The object system's property reader; docs/spec/object-system.md 2.)"""
        for p in self.props:
            k, sep, v = p.partition('=')
            if sep and k == key:
                return v
        return None


def parse_objects(blob):
    """objects.ob (docs/data-tables.md 7.3): s16 count, u16 flags, s32 string table offset;
    count records of {s32 class, s16 size, u16 angle, f32 x, y, z, s32 props..., s32 0};
    string offsets are relative to the string table."""
    count, _flags, strtab = struct.unpack_from('<hHi', blob, 0)

    def s(off):
        o = strtab + off
        return blob[o:blob.index(b'\0', o)].decode('latin1')

    out, p = [], 8
    for _ in range(count):
        cls, size, angle = struct.unpack_from('<ihH', blob, p)
        x, y, z = struct.unpack_from('<3f', blob, p + 8)
        props, q = [], p + 20
        while q < p + size:
            po, = struct.unpack_from('<i', blob, q)
            if po == 0:
                break
            props.append(s(po))
            q += 4
        out.append(Record(s(cls), angle, x, y, z, props))
        p += size
    return out


def build_objects(records, flags=0):
    """Bytes of an objects.ob for tests: records [(class, angle, x, y, z, [props])]."""
    strings = bytearray(b'\0')                   # offset 0 is never used by a property
    index = {}

    def intern(text):
        if text not in index:
            index[text] = len(strings)
            strings.extend(text.encode('latin1') + b'\0')
        return index[text]

    body = bytearray()
    for cls, angle, x, y, z, props in records:
        offs = [intern(p) for p in props]
        size = 20 + 4 * (len(offs) + 1)
        body += struct.pack('<ihH3f', intern(cls), size, angle & 0xFFFF, x, y, z)
        body += struct.pack('<%di' % (len(offs) + 1), *(offs + [0]))
    head = struct.pack('<hHi', len(records), flags, 8 + len(body))
    return head + bytes(body) + bytes(strings)


# =======================================================================================
# 5. Start markers and player placement
# =======================================================================================

SAVE_FILTER_CLASSES = ('Lantern', 'Torch', 'Firepot', 'Firepot2', 'Fire', 'kelethinBomb',
                       'smokeBomb', 'faytree', 'Line', 'Blocker', 'cdeyeball', 'customVars',
                       'charAmbient_Light', 'charDirectional_Light', 'charDirectional_LightD',
                       'clearColor', 'zzRoutepoint')    # world_saveFilter 0x15d9c8, list 0x403a68


def save_filter_admits(cls):
    """world_saveFilter 0x15d9c8: case-insensitive exact compare against the list.  With a
    saved state these are the only classes created from objects.ob (0x217b7c)."""
    return cls.lower() in (c.lower() for c in SAVE_FILTER_CLASSES)


def marker_decision(rank, props, prev_level, entrance, arrived_by_recall):
    """Player1_ctor 0x158928: does this marker take the spawn slots, and the new rank.
    props is a Record (or anything with prop()).  Tests in this order; a later one sets
    the rank again:

      rank == 3                                  nothing
      rank <= 0                                  take, 1
      rank == 1 and int(default) != 0            take, 1
      from: equals prev and not recall           take, 2
            elif recall and from == 'gate'       take, 3
      name: not recall and equals entrance       take, 3

    All string compares exact.  int() of a non-number is 0 (atoi)."""
    if rank == 3:
        return False, rank
    take = False
    source, name = props.prop('from'), props.prop('name')
    if rank <= 0:
        take, rank = True, 1
    elif rank == 1 and _atoi(props.prop('default')) != 0:
        take, rank = True, 1
    if source is not None:
        if source == prev_level and not arrived_by_recall:
            take, rank = True, 2
        elif arrived_by_recall and source == 'gate':
            take, rank = True, 3
    if name is not None and not arrived_by_recall and name == entrance:
        take, rank = True, 3
    return take, rank


def _atoi(text):
    if text is None:
        return 0
    text = text.strip()
    sign, i = 1, 0
    if text[:1] in '+-':
        sign, i = (-1 if text[0] == '-' else 1), 1
    j = i
    while j < len(text) and text[j].isdigit():
        j += 1
    return sign * int(text[i:j]) if j > i else 0


class SpawnState:
    """g_spawnPos 0x4f70d0 (4 x xyz), g_spawnFacing 0x4f8410 (4 x u16), g_playerStartRank
    0x4f7108.  The positions and facings are NEVER reset between levels: a level where no
    marker takes keeps the previous level's (already scattered) values; 0 at boot."""

    def __init__(self):
        self.pos = [[0.0, 0.0, 0.0] for _ in range(4)]
        self.facing = [0, 0, 0, 0]
        self.rank = 0


def run_markers(spawn, records, prev_level, entrance, arrived_by_recall, find_free_spot, draw,
                loaded_from_save=False, gate_arrival=None, num_players=4):
    """The markers in record order during world_loadRecords.  Start rank = 3 after a load
    from a save, else 0 (level_loadScriptAndObjects 0x217a90-0x217ab0).

      Player1 that takes: for slot 0..3 (ALL four, whatever the player count)
          pos = find_free_spot(marker xyz, spread 36, radius 24, any_height=False)
          facing = (angle + draw() % 4000 - 2000) & 0xffff
        draw() is the shared generator's value >> 16 (Player1_ctor 0x158b9c).
      Portal / PortalHurt with gate_arrival true (travel state 0x500ae8 != 0 and no
      destination parameter 0x8e3c34): for slot < num_players
          pos = find_free_spot(gate xyz, 36, 24, any_height=True); facing = draw()
        and rank = 3, with no rank test (JumpGate_ctor 0x27c974-0x27ca84).

    Returns the record indices that took, in order.  Every taking marker spends its
    searches and draws even when a later one overwrites the result."""
    spawn.rank = 3 if loaded_from_save else 0
    took = []
    for i, rec in enumerate(records):
        if rec.cls.lower() == 'player1':
            take, spawn.rank = marker_decision(spawn.rank, rec, prev_level, entrance, arrived_by_recall)
            if take:
                took.append(i)
                for slot in range(4):
                    spawn.pos[slot] = list(find_free_spot((rec.x, rec.y, rec.z), 36, 24, False))
                    spawn.facing[slot] = (rec.angle + draw() % 4000 - 2000) & 0xFFFF
        elif rec.cls.lower() in ('portal', 'portalhurt') and gate_arrival:
            took.append(i)
            for slot in range(num_players):
                spawn.pos[slot] = list(find_free_spot((rec.x, rec.y, rec.z), 36, 24, True))
                spawn.facing[slot] = draw() & 0xFFFF
            spawn.rank = 3
    return took


def place_players(spawn, num_players, terrain_height, find_free_spot, level_loaded=True,
                  pvp_mode_b=False, restore_xy=None, alive=None, active=None,
                  medal_slot=None):
    """mainloop_loadRequestedWorld after game_loadLevel (0x321160-0x3214c0).

      restore_xy (recall return, flag 0x41b51c): x, y of slot < num_players from it; z not
      every slot < num_players: z = terrain_height(12.0, pos)   highest sample within 12,
                                    pos.z ignored, -1000000.0 when there is no floor.
                                    Player_ctor stores this same radius and snaps again
                                    (player_ctor_z, section 17); this pass does not search.
      when a real level and not PvP mode B, for slot < num_players in order:
          slot > 0 and rank != 3: pos = find_free_spot(pos, 36, 14, False); facing += 8000;
                                  z = terrain_height(12.0, pos)   (written back: persists)
          construct a Player when alive(slot), active(slot) and (no medal mission or slot
          == medal_slot)
    Returns the list of slots that get a Player object, in construction order."""
    if restore_xy is not None:
        for i in range(num_players):
            spawn.pos[i][0], spawn.pos[i][1] = restore_xy[i][0], restore_xy[i][1]
    for i in range(num_players):
        spawn.pos[i][2] = terrain_height(12.0, tuple(spawn.pos[i]))
    built = []
    if not level_loaded or pvp_mode_b:
        return built
    for i in range(num_players):
        if i != 0 and spawn.rank != 3:
            p = list(find_free_spot(tuple(spawn.pos[i]), 36, 14, False))
            spawn.facing[i] = (spawn.facing[i] + 8000) & 0xFFFF
            p[2] = terrain_height(12.0, tuple(p))
            spawn.pos[i] = p
        if (alive is None or alive(i)) and (active is None or active(i)) and \
                (medal_slot is None or i == medal_slot):
            built.append(i)
    return built


# =======================================================================================
# 6. Level-change requests
# =======================================================================================

ORIENT_NONE = 0xFF          # most writers
ORIENT_RESTORE = 0xFD       # save_load, recall, party-wipe restart
ORIENT_CONSUMED = 0xFE      # written back by the loader after copying to 0x41b7c1


class Pending:
    """g_pendingLevel 0x41b6d0 (char[0x50]) and the byte after it, 0x41b720.  The byte is
    copied to 0x41b7c1 by the loader and nothing reads that copy (static scans): it has no
    effect on placement in v2.00, and no object on the disc has 'orientation='."""

    def __init__(self):
        self.name = ''
        self.orientation = ORIENT_NONE

    def request(self, name, orientation=ORIENT_NONE):
        if len(name) >= NAME_BUF:
            raise ValueError('level name longer than the 0x50-byte buffer')
        self.name, self.orientation = name, orientation & 0xFF


def orientation_from_props(props):
    """script_setNextWorld 0x1472c4: the selected object's 'orientation=' properties,
    compared with strncmp(.., 12) (case-sensitive); the LAST one wins; none: 0xff.  No
    selected object: 0xff."""
    found = None
    for p in props or ():
        if p.startswith('orientation='):
            found = _atoi(p[12:]) & 0xFF
    return ORIENT_NONE if found is None else found


def new_world_gate(net_game, active_player, cooldown, alive_count, in_post_action=False):
    """newWorld_netGate 0x143d04 (skipped inside a post action).  Returns (refused, new
    cooldown).  The cooldown is the active player's record +0x4bca, 600 ticks."""
    if in_post_action or not net_game or active_player == -1:
        return False, cooldown
    if cooldown != 0 and alive_count >= 2:
        return True, cooldown
    return False, 600


def cancel_pending(level_loaded, frontend_running, card_busy, pvp_mode_b, any_hp_above_zero):
    """mainloop_runSession step C (0x322c00-0x322ca8): True when the request is dropped.
    Runs once per displayed frame, outside the lockstep; card_busy is per machine."""
    return level_loaded and not frontend_running and not card_busy and not pvp_mode_b \
        and not any_hp_above_zero


# =======================================================================================
# 7. Acts, saved level states, and the change itself
# =======================================================================================

def find_act(acts, name, current):
    """save_findAct 0x217d30: acts is a list of lists of row names (each starting with
    'hub').  A row matches when name STARTS WITH it (strncmp(row, name, len(row))).  The
    current act is searched first, then acts 0.. in order; -1 if none."""
    order = ([current] if 0 <= current < len(acts) else []) + list(range(len(acts)))
    for a in order:
        for row in acts[a]:
            if name.startswith(row):
                return a
    return -1


def act_changed(acts, request, current):
    """save_actChanged 0x217f70 -> (changed, new current act).  The session starts with
    act -1 (0x1e6f14), so its first real level is always an act change."""
    act = find_act(acts, request, current)
    if act != -1 and act != current:
        return True, act
    return False, current


class LevelStates:
    """The saved-state directory g_saveLevelDir 0x8ab590 (10 entries of {char[0x14],
    u32 size}) and the data area (save buffer +0x16118 .. 0x4bc78).  Keys are qualified
    names; sizes come from the act table."""

    LIMIT = 0x4BC78 - 0x16118

    def __init__(self):
        self.entries = []           # [name, size]
        self.blobs = {}

    def store(self, name, act_rows, card_state=0, level_flags=0, fixed_35000=False, blob=b''):
        """save_storeLevelState 0x21777c.  act_rows: [(row name, size)] of the CURRENT act.
        Returns True when the state was written.  'hub*' uses the act's row 0; another
        level must be a row of the current act (exact), else nothing is stored."""
        if card_state == 4 or level_flags & LEVEL_FLAG_NO_LEVEL_STATE:
            return False
        if fixed_35000:
            size = 35000
        else:
            if name[:3] == 'hub':
                idx = 0
            else:
                idx = next((i for i, (row, _s) in enumerate(act_rows) if row == name), -1)
            if idx < 0:
                return False
            size = act_rows[idx][1]
        offset = 0
        for entry in self.entries:
            if entry[0] == name:
                break
            offset += entry[1]
        else:
            if len(self.entries) >= 10:
                raise OverflowError('11th level state: the original writes past the directory')
            self.entries.append([name, size])
        entry = next(e for e in self.entries if e[0] == name)
        if offset + entry[1] <= self.LIMIT:
            self.blobs[name] = blob
            return True
        return False

    def lookup(self, name):
        """level_loadScriptAndObjects 0x217978: (has state, byte offset)."""
        offset = 0
        for entry in self.entries[:10]:
            if entry[0] == name:
                return name in self.blobs, offset
            offset += entry[1]
        return False, offset


class Session:
    """The state that a level change carries or resets (docs/level-flow.md 7)."""

    def __init__(self, acts):
        self.acts = acts
        self.act = -1
        self.level = ''             # g_levelName 0x41b721
        self.sub = ''               # g_levelSubName 0x41b771
        self.prev = ''              # g_prevLevelName 0x41b7c2
        self.pending = Pending()
        self.entrance = ''          # g_entranceName 0x4f8468: only setEntrance and a new game write it
        self.states = LevelStates()
        self.quest_values = {}
        self.gates = GateList()
        self.recall_dest = ['None'] * 4          # record +0x24
        self.arrived_by_recall = False           # 0x41b51e
        self.restore_xy = None                   # 0x41b51c + 0x41b520
        self.post_action = ''                    # survives teardown, runs in the new level
        self.in_frontend = False

    def change(self, death_task=False, card_latch=False, card_state=0, store_blob=b'',
               hub_name='hub'):
        """mainloop_loadRequestedWorld 0x320edc up to game_loadLevel.  self.acts is
        [[(row name, state size), ...] per act].  Returns what happened, for the caller to
        run game_loadLevel and the placement with."""
        done = {'stored': False, 'act_changed': False}
        if self.level and not death_task:
            rows = self.acts[self.act] if 0 <= self.act < len(self.acts) else []
            done['stored'] = self.states.store(qualified_name(self.level, self.sub), rows,
                                               card_state, blob=store_blob)
        changed = False
        if not self.in_frontend:
            names = [[row for row, _size in act] for act in self.acts]
            changed, self.act = act_changed(names, self.pending.name, self.act)
        if changed and not card_latch and not death_task:
            self.states = LevelStates()
            self.gates.reset(hub_name)
            for k in self.quest_values:
                self.quest_values[k] = 0
        done['act_changed'] = changed
        self.prev = qualified_name(self.level, self.sub)
        self.level, self.sub = split_request(self.pending.name)
        self.pending.name = ''
        done['orientation'] = self.pending.orientation
        self.pending.orientation = ORIENT_CONSUMED
        if changed and card_state != 4 and not death_task:
            self.recall_dest = ['None'] * 4
        return done


# =======================================================================================
# 8. Triggers
# =======================================================================================

class Trigger:
    """Trigger_ctor 0x1ecdf4: an axis-aligned rectangle from (x, y) to (x + w, y - h)
    (w, h integer properties), entry point = property 't'.  Trigger_contains 0x1ed238 tests
    x and y inclusively, no height, no rotation.  Trigger_run 0x1ecf3c: edge-driven on
    "somebody inside" - the first player in slot order inside becomes the active player;
    on entry it runs t, on exit 'not' + t; nothing while the recall countdown runs."""

    def __init__(self, x, y, w, h, t):
        fx, fy = f32(x), f32(y)
        x1, y1 = W.fadd(fx, W.i2f(w)), W.fsub(fy, W.i2f(h))
        self.min = (W.fmin(fx, x1), W.fmin(fy, y1))
        self.max = (W.fmax(fx, x1), W.fmax(fy, y1))
        self.t = t
        self.inside = False

    def contains(self, x, y):
        px, py = f32(x), f32(y)
        return (W.fle(self.min[0], px) and W.fle(px, self.max[0]) and
                W.fle(self.min[1], py) and W.fle(py, self.max[1]))

    def run(self, players, recall_running=False):
        """players: [(slot, x, y) or None].  Returns (entry point to run or None, active
        player slot or None)."""
        if recall_running:
            return None, None
        first = None
        for p in players:
            if p is not None and self.contains(p[1], p[2]):
                first = p[0]
                break
        now = first is not None
        if now == self.inside:
            return None, None
        self.inside = now
        return (self.t if now else 'not' + self.t), first


def push_trigger_allowed(key_results):
    """PushTrigger_prompt 0x1eca94: usable when every 'key' predicate returns non-zero (in
    property order; the first 0 stops).  The net-host-only test comes first and is not
    modelled."""
    for result in key_results:
        if result == 0:
            return False
    return True


# =======================================================================================
# 9. Jump gates
# =======================================================================================

GATE_TRAVEL_TICKS = 180     # jumpgate_menuRun state 5: travel 1 -> 181, then the request


class GateList:
    """Destinations 0x8e3a50 (char[0x20] each), count 0x8e3c30.  Capacity 15: the original
    has NO bound check and a 16th append overwrites the count byte; this model refuses."""

    CAPACITY = 15

    def __init__(self):
        self.names = []

    def reset(self, hub_name):
        """jumpgate_resetDestinations 0x27db00 (act change, unless the card latch is set):
        the list becomes [hub()]."""
        self.names = [hub_name]

    def add_current(self, qualified, hub_name):
        """jumpgate_addCurrentLevel 0x27db60: append unless already listed; after an append
        the first entry that contains 'hub' but is not hub() is removed."""
        if qualified in self.names:
            return False
        if len(self.names) >= self.CAPACITY:
            raise OverflowError('16th gate destination: the original overwrites its count')
        self.names.append(qualified)
        for i, n in enumerate(self.names):
            if 'hub' in n and n != hub_name:
                del self.names[i]
                break
        return True

    def choosable(self, current):
        """jumpgate_menuRun state 2: confirm is ignored on the current level's index."""
        return [n for n in self.names if n != current]


def gate_prompt(found, menu_open, script_ok, dest_count, other_players_d2):
    """JumpGate_interactPrompt 0x27d7a0 for an ordinary gate -> (usable, text key, found).
    other_players_d2: squared distances of the OTHER alive players to the gate."""
    if menu_open or not script_ok:
        return False, None, found
    if dest_count == 1:
        return False, 'JumpGateVirgin', True
    for d2 in other_players_d2:
        if d2 > 96.0 * 96.0:
            return False, 'JumpGateNeedPlayers', True
    return True, 'JumpGate', True


# =======================================================================================
# 10. Recall and party wipe
# =======================================================================================

def recall_finish(level, sub, num_players, positions, recall_dest, hub_name):
    """player_recallTick 0x1b5fa0 when the countdown reaches 0 (no cutscene, someone
    alive).  positions: per slot the object's position, or the free-spot result for a
    player without one.  Returns (request, orientation, arrived_by_recall flag,
    restore_xy or None, new recall_dest, saved positions)."""
    if 'hub' not in level:
        q = qualified_name(level, sub)
        dest = [q] * num_players + list(recall_dest[num_players:])
        return hub_name, ORIENT_RESTORE, True, None, dest, [tuple(p) for p in positions]
    return recall_dest[0], ORIENT_RESTORE, False, [tuple(p) for p in positions], list(recall_dest), None


def party_wipe(level_base, level_in_act):
    """deathTask 0x1e75e8 state 1 (alternate death aside): a level in an act reloads the
    last save (save_load: saved level, rank 3, exact saved positions); a level in no act
    restarts itself by BASE name (sub dropped) with every record's hp = max.
    Returns ('reload', None) or ('restart', base)."""
    if level_in_act:
        return 'reload', None
    return 'restart', level_base


# =======================================================================================
# 11. Moving pieces
# =======================================================================================

K_COS = 0x38000100          # cos/sin s16 -> float (about 1/32767; cos 0 gives 0x3f7fffff)
K_RADIUS_SQ = 0x45C80000    # 6400.0 = 80 squared


class Piece:
    """A moving-piece record (0x1c bytes, world +0x54) with the flag of its first chunk."""

    def __init__(self, tx, ty, tz, cos, sin, mirrored=False, element=0):
        self.tx, self.ty, self.tz = tx, ty, tz      # rest translation, quarter units (s32)
        self.cos, self.sin = cos, sin                # rest rotation, s16 x 32767
        self.mirrored = mirrored                     # chunk flag 0x40
        self.element = element
        self.claimed = False                         # +0x06 bit 0


def piece_pivot(p):
    """The point world_findMovingPiece compares with: the rotated rest translation, in
    world units, as float patterns (0x1827a8-0x18287c)."""
    q = W.QUARTER
    tx = W.fmul(W.i2f(p.tx), q)
    ty = W.fmul(W.i2f(p.ty), q)
    tz = W.fmul(W.i2f(p.tz), q)
    c = W.fmul(W.i2f(p.cos), K_COS)
    s = W.fmul(W.i2f(p.sin), K_COS)
    if p.mirrored:
        x = W.fadd(W.fmul(tx, c), W.fmul(ty, s))
        y = W.fsub(W.fmul(tx, s), W.fmul(ty, c))
    else:
        x = W.fsub(W.fmul(tx, c), W.fmul(ty, s))
        y = W.fadd(W.fmul(tx, s), W.fmul(ty, c))
    return x, y, tz


def find_moving_piece(pieces, pos):
    """world_findMovingPiece 0x182768 (pos: three float patterns) -> index or -1.
    Full 3-D squared distance (dx*dx + dy*dy) + dz*dz against piece_pivot, best starts at
    6400.0, a candidate replaces the best unless best < d2 (so 80 is inclusive and the LATER
    of equal pieces wins).  If the nearest piece is already claimed the result is -1 - no
    fallback to the next one.  Otherwise the piece is claimed."""
    best, best_i = K_RADIUS_SQ, -1
    for i, p in enumerate(pieces):
        x, y, z = piece_pivot(p)
        dx, dy, dz = W.fsub(pos[0], x), W.fsub(pos[1], y), W.fsub(pos[2], z)
        d2 = W.fadd(W.fadd(W.fmul(dx, dx), W.fmul(dy, dy)), W.fmul(dz, dz))
        if not W.flt(best, d2):
            best, best_i = d2, i
    if best_i < 0 or pieces[best_i].claimed:
        return -1
    pieces[best_i].claimed = True
    return best_i


def release_piece(pieces, index):
    """world_releasePiece 0x182914; no-op for index < 0 (every piece function is)."""
    if index >= 0:
        pieces[index].claimed = False


def disable_unclaimed(pieces, set_collision):
    """world_disableUnclaimedPieces 0x1826ec, run by game_loadLevel at 0x1e6060 - after the
    saved states, the objects, the flush of objects deleted in their constructor (whose
    destructor released the claim) and the 'start' script.  set_collision(index, on) is
    ref_world.Level.set_piece_collision."""
    for i, p in enumerate(pieces):
        if not p.claimed:
            set_collision(i, False)


def autodoor_pose(open_):
    """AutoProp_setPassable 0x23d7ac for an AutoProp with property AutoDoor: open ->
    collision off and the piece drawn 256 units lower; closed -> collision on, rest pose.
    Returns (collision on, offset (x, y, z) in world units, angle).  The terrain element
    never moves; only the drawing does (world_movePiece 0x182c98 writes chunk fields)."""
    return (False, (0.0, 0.0, -256.0), 0) if open_ else (True, (0.0, 0.0, 0.0), 0)


# =======================================================================================
# 12. Water
# =======================================================================================

class WaterTile:
    """A water chunk (flag 0x80): its stored bounds (float patterns) in chunk-tree walk
    order."""

    def __init__(self, bmin, bmax, has_sim=False):
        self.min, self.max, self.has_sim = tuple(bmin), tuple(bmax), has_sim


def _overlaps(tile, lo, hi):
    return all(not W.flt(hi[k], tile.min[k]) and not W.flt(tile.max[k], lo[k]) for k in range(3))


def water_test(tiles, radius, pos):
    """water_test 0x189438 (simulation) -> (in water, height pattern or None).  Box
    x, y +- (radius + 1) - computed as (p - r) - 1 and (p + r) + 1 - and z from pos.z - 1 to
    pos.z + 60; the collector 0x189240 is called with cap 2, so only the FIRST overlapping
    tile in walk order counts; height = its bounds.min.z (+0x10).  The 32 x 32 mask is not
    read.  tiles must be in the order of the chunk-tree walk (second child first)."""
    one, sixty = W.ONE, f32(60.0)
    lo = (W.fsub(W.fsub(pos[0], radius), one), W.fsub(W.fsub(pos[1], radius), one),
          W.fsub(pos[2], one))
    hi = (W.fadd(W.fadd(pos[0], radius), one), W.fadd(W.fadd(pos[1], radius), one),
          W.fadd(pos[2], sixty))
    for tile in tiles:
        if _overlaps(tile, lo, hi):
            return True, tile.min[2]
    return False, None


def water_disturb_count(tiles, radius, pos, cut_skip=False):
    """The return value of water_disturb 0x189514, which ends the in-water state: the
    number (at most 15, cap 16) of water tiles overlapping x, y +- radius (no +1) and z from
    pos.z - 1 to pos.z + 60; 0 while a cutscene is being skipped.  Counted whether or not a
    tile has a ripple grid; the ripples themselves are cosmetic."""
    if cut_skip:
        return 0
    one, sixty = W.ONE, f32(60.0)
    lo = (W.fsub(pos[0], radius), W.fsub(pos[1], radius), W.fsub(pos[2], one))
    hi = (W.fadd(pos[0], radius), W.fadd(pos[1], radius), W.fadd(pos[2], sixty))
    n = 0
    for tile in tiles:
        if _overlaps(tile, lo, hi):
            n += 1
            if n == 15:
                break
    return n


WATER_NEIGHBOURS = ('-y', '+y', '-x', '+x')     # water chunk data s16[4], -1 for none


def water_mask_bit(mask, row, col):
    """The 32 x 32 mask at water data +0x10 (128 bytes): two halves of 64 bytes (rows 0-15,
    16-31); in a half the little-endian u16 at byte 2*col holds column col (along y), bit
    15 - (row % 16) is row (along x).  Read only by the cosmetic ripple step 0x196088,
    which applies row r+1's bit to row r."""
    half = 64 * (row // 16)
    word = mask[half + 2 * col] | (mask[half + 2 * col + 1] << 8)
    return (word >> (15 - row % 16)) & 1


# =======================================================================================
# 13. Texture addressing and materials of WORLD geometry
# =======================================================================================

TEX_DIR_BYTES = 0x5000      # world_fixup reads this much of <LEVEL>.TEX (0x181efc-0x181f28)


def tex_directory(head):
    """world_fixup 0x181d30 (0x181f20-0x181fd8): the leading u32 is skipped unread; then
    12-byte records {s32 cell id, u32 offset, u32 size} until an id of -1 or -2 (the code
    tests (unsigned)(id + 2) < 2 and treats both alike).  A first id of 0 skips the whole
    fill.  Ids are not checked against the world's lowest/highest cell.  -> {id: (off, size)}"""
    out, o = {}, 4
    first = True
    while o + 12 <= min(len(head), TEX_DIR_BYTES):
        cid, off, size = struct.unpack_from('<iII', head, o)
        if first and cid == 0:
            return {}
        first = False
        if cid in (-1, -2):
            return out
        out[cid] = (off, size)
        o += 12
    raise ValueError('texture directory has no terminator within 0x5000 bytes')


def cell_id(x, y, size=720.0):
    """0x17d8e0-0x17d930: row * 100 + column, column = floorf(x / size) + 50,
    row = floorf(y / size) + 50 (x, y float patterns; size 0 in the file means 960)."""
    s = f32(size if size else 960.0)
    col = W.f2i(W.floorf(W.fdiv(x, s))) + 50
    row = W.f2i(W.floorf(W.fdiv(y, s))) + 50
    return row * 100 + col


def wanted_cells(centre):
    """worldtex_stream 0x17d830(-1): the 3 x 3 ids around the camera focus's cell, row by
    row.  The game keeps them in 9 streaming slots and loads the missing one nearest the
    focus first; a chunk whose cell is not resident, or whose texture packet is not built
    yet, is simply not drawn that frame (0x1887b8).  Per machine, drawing only."""
    return [centre + 100 * i + j for i in (-1, 0, 1) for j in (-1, 0, 1)]


def chunk_texture_header(chunk_cell, chunk_texoff, directory, tex):
    """0x1887b8: a geometry chunk names cell +0x34 (0 = never drawn) and +0x20, the byte
    offset of its 0x40-byte header inside the cell (0x40 * (i + 1) for texture i).
    Returns (cell bytes, header offset) or None."""
    if chunk_cell == 0 or chunk_cell not in directory:
        return None
    off, size = directory[chunk_cell]
    cell = tex[off:off + size]
    count, = struct.unpack_from('<I', cell, 0)
    if chunk_texoff % 0x40 or not 0x40 <= chunk_texoff <= 0x40 * count:
        raise ValueError('chunk texture offset 0x%x outside the cell' % chunk_texoff)
    return cell, chunk_texoff


REL = (-1, -16, -17, -15, -2)   # 0x41c1a0, s8: symbols 0x100..0x104 copy these texels


class Codebook:
    """The code book a texture header's record block points at (cell-relative), as the
    worker 0x17ca58 reads it (0x17cd84-0x17d03c):
        +0x000  0x400  palette, 256 RGBA8 in GS CLUT order (clut_order)
        +0x400  0x800  successor table succ[prev][k], 256 x 8
        +0xc00  u32 N, then u16 sym[N]; then s32 base[18], s32 limit[18]
    Canonical Huffman: a code value c of length L is valid when c <= limit[L], and its
    symbol is sym[base[L] + c].  Several textures of a cell may share one book."""

    def __init__(self, cell, off):
        self.palette = bytes(cell[off:off + 0x400])
        self.succ = bytes(cell[off + 0x400:off + 0xC00])
        n, = struct.unpack_from('<I', cell, off + 0xC00)
        t = off + 0xC04
        self.sym = struct.unpack_from('<%dH' % n, cell, t)
        b = t + 2 * n
        self.base = struct.unpack_from('<18i', cell, b)
        self.limit = struct.unpack_from('<18i', cell, b + 0x48)
        self.fast = []                                  # built once per texture (0x17cf88)
        for i in range(256):
            entry = (0, 0)
            for length in range(1, 9):
                c = i >> (8 - length)
                if c <= self.limit[length]:
                    entry = (self.symbol(self.base[length] + c), length)
                    break
            self.fast.append(entry)

    def symbol(self, k):
        if not 0 <= k < len(self.sym):
            raise ValueError('symbol index %d of %d' % (k, len(self.sym)))
        return self.sym[k]


def decode_block(cell, stream, book):
    """One 16 x 16 block (0x17d238-0x17d3cc) -> (256 palette indices row-major, bits used).
    The stream is little-endian u16 words read most-significant bit first.  Per texel:
    the next 16 bits are the window; lengths 1-8 through the fast table, then 9, then 10..;
    symbol < 0x100 is a literal index, 0x100..0x104 copies an earlier texel of this block
    at REL, 0x105..0x10c is succ[previous texel][symbol - 0x105].  The previous texel starts
    at 0 in every block.  The game then writes the block through a permutation (0x7d3040,
    built by 0x17a0c0) that is the standard 8-bit-in-32-bit GS block layout, so the result
    here is already plain row-major: block (bx, by) is texels 16bx.., 16by.. ."""
    out = [0] * 256
    pos = prev = 0
    for i in range(256):
        q = stream + 2 * (pos >> 4)
        hi, lo = struct.unpack_from('<HH', cell, q)
        win = ((((hi << 16) | lo) << (pos & 15)) & 0xFFFFFFFF) >> 16
        sym, length = book.fast[win >> 8]
        if not length:
            if (win >> 7) <= book.limit[9]:
                length = 9
            else:
                length = 10
                while (win >> (16 - length)) > book.limit[length]:
                    length += 1
                    if length > 16:
                        raise ValueError('no code length')
            sym = book.symbol(book.base[length] + (win >> (16 - length)))
        pos += length
        if sym < 0x100:
            v = sym
        elif sym < 0x105:
            j = i + REL[sym - 0x100]
            if j < 0:
                raise ValueError('reference before the block')
            v = out[j]
        elif sym < 0x10D:
            v = book.succ[prev * 8 + sym - 0x105]
        else:
            raise ValueError('symbol 0x%x' % sym)
        out[i] = prev = v
    return out, pos


def clut_order(i):
    """Stored position of palette entry i: bits 3 and 4 exchanged (GS CSM1, as lump
    textures in docs/formats/model-texture.md)."""
    return (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)


def decode_texture(cell, header):
    """A cell texture -> (width, height, rows of palette indices or None, RGBA palette).
    Header (0x40 bytes at cell + header): u16 width +0, height +2, GS blocks +4, flags +8
    (0x010c on every disc texture: 0x100 = this block form; flag 0x1, a vector-quantised
    form decoded at 0x17e6c0, is used by no disc texture and refused here), +0x0c the TEX0
    fragment, +0x10 the cell offset of the record block:
        u32 code book offset (cell-relative)
        {s8 x0, y0, x1, y1; u32 stream offset per block, y outer, x inner}...  x0 == -1 ends
    Blocks not listed are never written (None here)."""
    w, h, _blocks, _qwc, flags = struct.unpack_from('<5H', cell, header)
    if flags & 1 or not flags & 0x100:
        raise ValueError('texture form 0x%x not supported' % flags)
    p, = struct.unpack_from('<I', cell, header + 0x10)
    book_off, = struct.unpack_from('<I', cell, p)
    book = Codebook(cell, book_off)
    rows = [[None] * w for _ in range(h)]
    o = p + 4
    while True:
        x0, y0, x1, y1 = struct.unpack_from('<4b', cell, o)
        o += 4
        if x0 == -1:
            break
        for by in range(y0, y1 + 1):
            for bx in range(x0, x1 + 1):
                stream, = struct.unpack_from('<I', cell, o)
                o += 4
                block, _bits = decode_block(cell, stream, book)
                for r in range(16):
                    y = 16 * by + r
                    if y >= h:
                        break
                    for c in range(16):
                        x = 16 * bx + c
                        if x < w:
                            rows[y][x] = block[16 * r + c]
    pal = book.palette
    palette = [tuple(pal[4 * clut_order(i):4 * clut_order(i) + 4]) for i in range(256)]
    return w, h, rows, palette


def uv_normalised(u, v, width, height):
    """GS UV with FST are texels x 16 (docs/formats/world.md); native coordinates divide by
    16 and the header's width/height.  TW = TH = 1024 in every header and no UV reaches it,
    so clamp-to-edge is the faithful sampler; bilinear, no mip maps."""
    return u / (16.0 * width), v / (16.0 * height)


TEST_OPAQUE = 0x587F4       # ATE off, depth test GEQUAL
TEST_CUTOUT = 0x582F5       # ATE on, pass when alpha < 0x2f, fail keeps nothing


def chunk_header_state(flags):
    """0x1887b8: the GS state the chunk header writes before the stored packet, whose own
    DIRECT blocks then override it batch by batch (last write wins).
    -> (ALPHA_1, ALPHA_2 or None, TEST_1, light, layer); light is 'dynamic', or a constant
    level offset (-230 for one frame with the run-time flag 0x100, +230, 0)."""
    if flags & 0x10:
        alpha1, alpha2 = 0x09, 0x2A
    elif flags & 0x10000:
        alpha1, alpha2 = 0x48, None
    elif flags & 0x600:
        alpha1, alpha2 = 0x01, None
    else:
        alpha1, alpha2 = 0x02, None
    test1 = TEST_CUTOUT if flags & 0x400 else TEST_OPAQUE
    if flags & 0x100:
        light = -230
    elif flags & 0x2000:
        light = 230
    elif flags & 0x200:
        light = 0
    else:
        light = 'dynamic'
    return alpha1, alpha2, test1, light, (4 if flags & 0x200 else 0)


def batch_material(alpha1, test1, blend_enabled=True):
    """What one batch looks like, from the last ALPHA_1 / TEST_1 written before it and the
    GIF tag's ABE bit (0x30ae4000 on, 0x308e4000 off).  Texel alpha A is 0..0x80, a = A/128,
    and 0 means opaque.  -> (blend, alpha cut-off or None):
        'opaque'      ALPHA 2 = src x (1 - a); a is 0 on every used texel of such textures
        'mix'         ALPHA 1 = src x (1 - a) + dst x a
        'env'         ALPHA 9 = src + dst x a after the context-2 environment pass
        'additive'    ALPHA 0x48 = dst + src x a (no disc chunk)
    With ABE off the source is written as is.  TEST 0x582f5 discards texels with A >= 0x2f."""
    cut = 0x2F if test1 == TEST_CUTOUT else None
    if not blend_enabled:
        return 'opaque', cut
    return {0x02: 'opaque', 0x01: 'mix', 0x09: 'env', 0x48: 'additive'}.get(alpha1, 'unknown'), cut


# =======================================================================================
# Round 2 corrections and additions (2026-10-18)
#
# Four points round 1 left contradictory or underspecified, settled by running the
# original code in tools/ee_emu.py (tools/difftest_levels.py; docs/level-flow.md 16):
#   1. the WORLD entry is the first in directory order, not the first in sorted order;
#   2. the level flag bits give the BASE LIGHT LEVEL (0x40 wins over 0x20), not an alpha;
#      the per-chunk order 0x100, 0x2000, 0x200 of chunk_header_state is unchanged;
#   3. the recall countdown keeps counting during a cutscene; a cutscene on the tick it
#      reaches 0 cancels the recall (RecallCountdown);
#   4. world_movePiece's arithmetic (move_piece).
# Round-1 names and signatures are unchanged.
# =======================================================================================

base_light_level = level_light_alpha        # the accurate name (g_worldLightLevel 0x5d347c)


def first_entry_with_extension(entries, ext, n=0):
    """lump_findNthByExtension 0x171fd8 (lump, ext, n): walk the directory in its stored
    order; for each name take the part after the LAST '.' (libc_strrchr 0x3b95d8), skip a
    name without one, compare it with ext by exact strcmp (0x3b8534, case-sensitive), and
    return the n-th match (n = 0: the first) or None.  game_loadLevel calls it with
    ('world', 0) at 0x1e599c and stores entry +4 (the data pointer) in g_world 0x44fdc8
    without a null test, so a level lump with no .world entry faults there.  Executed:
    difftest_levels.py properties world_pick and world_pick_load."""
    for name in entries:
        dot = name.rfind('.')
        if dot < 0 or name[dot + 1:] != ext:
            continue
        if n == 0:
            return name
        n -= 1
    return None


RECALL_TICKS = 60                           # recall_execute 0x18c3c8 stores 60

RECALL_AURA = 'aura'                        # countdown was 60: aura lights started
RECALL_FINISH = 'finish'                    # reached 0: the request is written (recall_finish)
RECALL_DROPPED_CUTSCENE = 'dropped: cutscene'
RECALL_DROPPED_NOBODY = 'dropped: nobody alive'


class RecallCountdown:
    """g_recallCountdown 0x41b51d and player_recallTick 0x1b5fa0.

    player_recallTick is the first thing the run task gameMiscSync 0x1e3d60 (priority 1)
    does, in every tick, with no game_isFrozen, cutscene or pause test in front of it.  So
    the countdown runs on during a cutscene and while paused.  Per call:

        v = s8 countdown;  v == 0: return
        v == 60: start the aura (per alive slot: colour words, light radius 0.05)
        countdown = (u8)(v - 1);  non-zero: return
        clear the aura lights of every player (0x1b60a4-0x1b6110)
        g_cutsceneActive 0x44fcd0 != 0: return       <- the recall is lost, not deferred
        g_alivePlayerCount 0x4f8420 == 0: return      <- likewise
        recall_finish (hub test, positions, request)

    The countdown is not set again on a dropped recall and the potion (taken in
    recall_execute) is not given back.  Executed: difftest_levels.py property
    recall_tick."""

    def __init__(self, value=0):
        self.value = value & 0xFF

    def start(self):
        """recall_execute 0x18c230 after its checks (game message 3)."""
        self.value = RECALL_TICKS

    @property
    def running(self):
        """What Trigger_run, Player_takeDamage and the others test: non-zero."""
        return self.value != 0

    def tick(self, cutscene_active, alive_count):
        """One call; cutscene_active and alive_count are the values the call reads, i.e.
        as left by the previous tick (gameMiscSync runs before runObjects, Script,
        Dialog and cutRunFrame, which are the places a cutscene starts or ends).
        -> None, RECALL_AURA, RECALL_FINISH, RECALL_DROPPED_CUTSCENE or
        RECALL_DROPPED_NOBODY."""
        if self.value == 0:
            return None
        aura = self.value == RECALL_TICKS
        self.value = (self.value - 1) & 0xFF
        if self.value != 0:
            return RECALL_AURA if aura else None
        if cutscene_active:
            return RECALL_DROPPED_CUTSCENE
        if alive_count == 0:
            return RECALL_DROPPED_NOBODY
        return RECALL_FINISH


def recall_request_tick(set_tick, set_before_run_pass):
    """The tick whose player_recallTick writes the level request, or None for a drop.
    set_tick is the tick in which game message 3 was executed.  In a net game messages run
    in net_frameLoop before that frame's run pass (set_before_run_pass True), so that
    tick's call already sees 60 and the request is written in tick set_tick + 59.  Offline,
    net_sendGameMsg executes the message at once: from player_pollRecallButton inside
    gameMiscSync (after player_recallTick) or from the pause menu in the draw pass, so the
    first call to see 60 is in the next tick and the request comes in set_tick + 60.
    Either way it is the 60th call to see the countdown non-zero."""
    first = set_tick if set_before_run_pass else set_tick + 1
    return first + RECALL_TICKS - 1


K_32767 = 0x46FFFE00        # 32767.0
K_FOUR = 0x40800000         # 4.0: world units -> quarter units


def _cos16(angle):
    import ref_core
    return ref_core.cos16(angle)


def _sin16(angle):
    import ref_core
    return ref_core.sin16(angle)


def _round_s16(x):
    """floorf(x * 32767 + 0.5) (libm_floorf 0x3a57e8), cvt.w.s, then clamped to the s16
    range by two slt/movn pairs (0x182ddc-0x182e10)."""
    v = W.f2i(W.floorf(W.fadd(W.fmul(x, K_32767), W.HALF)))
    return max(-0x8000, min(0x7FFF, v))


def move_piece(piece, offset, angle, chunk_mirrored=None):
    """world_movePiece 0x182c98 (world, piece, offset, angle16).  offset: three float
    patterns in world units; angle: the low 16 bits, sign-extended.  It reads only the
    PIECE record's rest values (+0x08..+0x10 s32 translation in quarter units, +0x14/+0x16
    s16 cos/sin), never the chunk's current ones, so a move is absolute and moves do not
    accumulate.  chunk_mirrored: per chunk of the piece (+0x00 first index, +0x04 s16
    count; count <= 0 writes nothing), whether its flag 0x40 is set; default one chunk with
    piece.mirrored.  Returns per chunk the new (+0x28, +0x2c, +0x30 s32, +0x36, +0x38 s16).

    With ca = math_cos16(angle), sa = math_sin16(angle), K = 0x38000100:
        o     = offset * 4.0                                 (per axis, first)
        cos'  = round_s16(((ca * c) * K - (sa * s) * K) * 32767)      = cos(rest + angle)
        sin'  = round_s16(((sa * c) * K + (ca * s) * K) * 32767)      = sin(rest + angle)
        X, Y, Z = i2f(t) + o
        plain:     t'x = trunc(X*ca + Y*sa)     t'y = trunc(-X*sa + Y*ca)    rotate by -angle
        mirrored:  t'x = trunc(X*ca - Y*sa)     t'y = trunc( X*sa + Y*ca)    rotate by +angle
        t'z = trunc(Z)
    trunc is cvt.w.s (toward zero); round_s16 is _round_s16.  The drawing rule of
    docs/formats/world.md (translation added before the rotation) then gives, exactly in
    real arithmetic: world = pivot + R(rest) * offset + R(angle) * (rest-pose geometry -
    pivot), pivot = piece_pivot(piece) - so the piece turns by +angle about its pivot and
    shifts by the offset expressed in its rest frame (mirrored: the same with the mirrored
    rest matrix).  Executed: difftest_levels.py property move_piece."""
    if chunk_mirrored is None:
        chunk_mirrored = (piece.mirrored,)
    ca, sa = _cos16(angle), _sin16(angle)
    c, s = W.i2f(W.s16(piece.cos)), W.i2f(W.s16(piece.sin))
    k = K_COS
    new_cos = _round_s16(W.fsub(W.fmul(W.fmul(ca, c), k), W.fmul(W.fmul(sa, s), k)))
    new_sin = _round_s16(W.fadd(W.fmul(W.fmul(sa, c), k), W.fmul(W.fmul(ca, s), k)))
    o = [W.fmul(v, K_FOUR) for v in offset]
    out = []
    for mirrored in chunk_mirrored:
        X = W.fadd(W.i2f(piece.tx), o[0])
        Y = W.fadd(W.i2f(piece.ty), o[1])
        Z = W.fadd(W.i2f(piece.tz), o[2])
        xc, yc, ys = W.fmul(X, ca), W.fmul(Y, ca), W.fmul(Y, sa)
        if mirrored:
            tx = W.fsub(xc, ys)
            ty = W.fadd(W.fmul(X, sa), yc)
        else:
            tx = W.fadd(xc, ys)
            ty = W.fadd(W.fmul(W.fneg(X), sa), yc)
        out.append((W.f2i(tx), W.f2i(ty), W.f2i(Z), new_cos, new_sin))
    return out


# =======================================================================================
# Round 3. Placement when the floor is not under the origin
# =======================================================================================

PLACEMENT_RADIUS = 0x41400000       # 12.0 in f12 at 0x32120c and again from object +0x1c
ARENA_RING_MODE_A = 0x43340000      # 180.0 when g_pvpModeA is set
ARENA_RING_MODE_B = 0x42100000      # 36.0 otherwise
ARENA_FIRST_SPREAD = 36
ARENA_RETRY_SPREAD = 240            # 0xF0, only when the first search's ok byte is 0
ARENA_SEARCH_RADIUS = 24


def player_ctor_z(pos, radius, terrain_height):
    """The store at the end of Player_ctor (0x1a2450-0x1a245c).

    radius is the word at object +0x1c.  0x1a2244 writes PLACEMENT_RADIUS there.  No
    instruction from there to this call stores offset 0x1c through $21, the player, so
    the radius is 12.0.  The call is terrain_height, which ignores pos.z and returns
    the sentinel when the disc is empty.  This function does not test the sentinel and does not move x or y.
    terrain_height is the same callback shape as place_players: (radius, pos) -> z.
    Executed: difftest_levels_r3.py properties player_radius and player_snap."""
    return terrain_height(radius, pos)


def arena_ring_angle(slot, active_count):
    """The angle math_cos16 receives in arena_pickSpawnPoint (0x3050e8-0x305138).

    active_count is what net_countActiveSlots returned.  The code divides by that word,
    or by a zero word when the count is not greater than 0; a non-positive count is
    refused here because that MIPS division has no defined quotient.  The quotient of
    the signed division 65535 / count is sign-extended from 16 bits and multiplied by
    the slot, and the low 16 bits are the angle."""
    if active_count <= 0:
        raise ValueError('arena_ring_angle divides by the active-slot count')
    quot = W.s16(65535 // int(active_count))
    return W.s16(W.s32(quot * W.s32(slot)))


def arena_ring_centre(entry, slot, active_count, mode_a):
    """Entry 0 plus the ring offset (0x305130-0x30519c).  mode_a selects 180 or 36.
    z is entry 0's z, not a terrain query.  entry is three float patterns."""
    import ref_core
    angle = arena_ring_angle(slot, active_count)
    radius = ARENA_RING_MODE_A if mode_a else ARENA_RING_MODE_B
    ox = W.fmul(ref_core.cos16(angle), radius)
    oy = W.fmul(ref_core.sin16(angle), radius)
    return (W.fadd(entry[0], ox), W.fadd(entry[1], oy), entry[2])


def arena_initial_place(entry, slot, active_count, mode_a, search, table_facing=False,
                        table_angle=0):
    """arena_pickSpawnPoint 0x3050a4 when its first argument is not 0 (the wave start).

    search(centre, spread, radius, any_height) -> (pos, ok), the pair world_findFreeSpot
    returns.  The first search uses spread 36 and radius 24 with any_height false.  When
    its ok byte is 0, the same centre is searched again with spread 240.  There is no
    third search.

    Facing, low 16 bits: when the word at 0x4f7124 is nonzero, table[slot].angle - 0x4000.
    Otherwise -0x4000 minus atan2(pos.x - entry.x, pos.y - entry.y).  When g_pvpModeA is
    clear, that facing then loses another half-turn (0x8000).  The position's z is
    whatever the search returned; Player_ctor replaces it afterwards (player_ctor_z).
    Executed: difftest_levels_r3.py property arena_initial."""
    import ref_core
    centre = arena_ring_centre(entry, slot, active_count, mode_a)
    pos, ok = search(centre, ARENA_FIRST_SPREAD, ARENA_SEARCH_RADIUS, False)
    if not ok:
        pos, ok = search(centre, ARENA_RETRY_SPREAD, ARENA_SEARCH_RADIUS, False)
    pos = list(pos)
    if table_facing:
        facing = W.s16((int(table_angle) & 0xFFFF) - 0x4000)
    else:
        dx = W.fsub(pos[0], entry[0])
        dy = W.fsub(pos[1], entry[1])
        facing = W.s16(-0x4000 - ref_core.atan2_16(dx, dy))
    if not mode_a:
        facing = W.s16(facing - 0x8000)
    return pos, facing & 0xFFFF, int(bool(ok))


# =======================================================================================
# Round 4. The arena maps whose cold origin has no floor
# =======================================================================================

ARENA_MODE_A_COUNT = 13             # pointers at 0x5037b8, then a null
ARENA_MODE_B_COUNT = 7              # pointers at 0x503798, then a null
ARENA_RECORD_BYTES = 6              # five records at 0x503868; count halfword at 0x503886


def arena_mode_a_next(index, saved):
    """The rotation byte at 0x8e7343, in arena_runTask (0x306c64-0x306c84).

    The byte is loaded signed, incremented, and divided by 13. The remainder is stored.
    When that remainder is 0, the next instruction stores what game_scanCm1Vars(0) returned,
    which is the word at 0x4f7110. For an index in 0..12 the remainder is (index + 1) mod 13,
    and a 0 is replaced by `saved`. A negative index is not produced by the stores found."""
    if not 0 <= int(index) <= 12:
        raise ValueError('arena_mode_a_next index is a byte the rotation leaves in 0..12')
    rem = (int(index) + 1) % ARENA_MODE_A_COUNT
    if rem == 0:
        return int(saved)
    return rem


def arena_record_table_offset(first_byte):
    """The addend at 0x304c28 and again at 0x306d08.

    The record's first byte is shifted left 28 and arithmetic-shifted right 26. The high
    nibble falls off the top of the word, and what remains is the low nibble times 4, the
    stride of the pointer table at 0x503798. A low nibble of 8 or more sets the sign bit
    and the addend is negative. The five records in the executable have low nibbles
    0, 1, 5, 3 and 2, so none of them does."""
    word = ((int(first_byte) & 0xFF) << 28) & 0xFFFFFFFF
    if word & 0x80000000:
        word -= 0x100000000
    return word >> 26


def arena_register_spawn(entries, count, index, point, angle):
    """0x30503c. Returns (entries, count).

    index -1 writes at the current count and then increments that byte (0x8e7342). Any
    other index overwrites that slot and leaves the count alone. arena_init stores 1 and
    then calls this with index 0 and the origin. ArenaPlayerStart passes 0, so it replaces
    that origin. ArenaPlayerAlternate passes -1, so the first alternate is written at 1."""
    entries = list(entries)
    if int(index) == -1:
        slot = int(count) & 0xFF
        count = (int(count) + 1) & 0xFF
    else:
        slot = int(index)
        count = int(count) & 0xFF
    while len(entries) <= slot:
        entries.append(None)
    entries[slot] = (tuple(point), int(angle) & 0xFFFF)
    return entries, count

