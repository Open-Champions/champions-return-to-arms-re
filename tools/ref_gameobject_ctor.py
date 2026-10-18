"""Addressed constructor supplement for SLUS-20973 v2.00.

Independently authored contract; no game data. See docs/spec/gameobject-constructor.md.
Memory interface is ref_creature.Model. Existing pinned ref_skills_a is unchanged.
ASCII, terminated, non-overlapping property strings and valid paired lists are admitted.
Bounds below are HOST refusals, not original bounds. They retain completed writes.
"""
import ref_core as C
import ref_objects as O
import ref_skills_a as S

G_NAMES = 0x5F76F8
G_NAMED_OBJECTS = 0x5F7EF8
G_NAME_COUNT = 0x5F86F8
S_NAME = 0x5321B0


class ContractFault(ValueError):
    pass


class Model(S.Model):
    """Skills-A model with the complete constructor in the documented finite domain."""
    string_limit = 511                 # quoted source must fit original 512-byte scratch
    property_limit = 4096              # host traversal budget

    def call(self, name, *args):
        if name in ('handle_link', 'res_find') and name not in self.cb:
            raise ContractFault('required service: ' + name)
        return super().call(name, *args)

    def text(self, address):
        out = bytearray()
        for i in range(self.string_limit + 1):
            c = self.u8(address + i)
            if c == 0:
                return bytes(out)
            if c >= 128:
                raise ContractFault('non-ASCII character-table domain')
            out.append(c)
        raise ContractFault('unterminated/oversize string')

    def property_value(self, obj, key_address, nth=0):
        """0x14c8b0-0x14c990 / ctor 0x14cd84-0x14cf44: lowercase KEY in place,
        case-sensitive key= scan; return pointer after '=' or zero. nth is an index,
        NOT a default integer value. Re-read object.props after key publication."""
        if not self.u32(obj + 0x2C):
            return 0
        key = self.text(key_address).lower()
        for i, c in enumerate(key):
            self.w8(key_address + i, c)
        props = self.u32(obj + 0x2C)
        for i in range(self.property_limit):
            entry = self.u32(props + 4 * i)
            if not entry:
                return 0
            value = self.text(entry)
            if value.startswith(key + b'='):
                if nth == 0:
                    return entry + len(key) + 1
                nth -= 1
        raise ContractFault('property traversal budget')

    def property_int(self, obj, key_address, nth=0):
        """obj_getPropInt 0x14c880: C atoi(value), zero if absent."""
        p = self.property_value(obj, key_address, nth)
        return O.atoi(self.text(p)) if p else 0

    def relocate_hidden_grid(self, obj):
        """0x14cd00-0x14cd48: move peer node, preserving both identities and pool.
        +0 next; +4 predecessor link address; +8 paired node; +12 target.
        Re-reads between writes are intentional, including same-list relocation."""
        node = self.u32(self.u32(obj + 8) + 8)
        prev = self.u32(node + 4)
        self.w32(prev, self.u32(node))
        following = self.u32(node)
        if following:
            self.w32(following + 4, self.u32(node + 4))
        old_head = self.u32(S.G_OFF_GRID)
        self.w32(node + 4, S.G_OFF_GRID)
        self.w32(node, old_head)
        self.w32(S.G_OFF_GRID, node)
        following = self.u32(node)
        if following:
            self.w32(following + 4, node)

    def name_add(self, name, obj):
        """objNames_add 0x14bce0. Store property pointer, not a copied key.
        Quote mutation precedes count; count precedes hash/probes; key precedes object.
        Returns chosen index for inspection (original void return is unspecified)."""
        value = self.text(name)
        if value.startswith(b'"'):
            value = O.strip_quotes(value)
            for i, c in enumerate(value + b'\0'):
                self.w8(name + i, c)
        self.w32(G_NAME_COUNT, self.u32(G_NAME_COUNT) + 1)
        slot = O.name_hash(value)
        for _ in range(512):
            key = self.u32(G_NAMES + slot * 4)
            if not key or (not self.u32(G_NAMED_OBJECTS + slot * 4)
                           and self.text(key).lower() == value.lower()):
                self.w32(G_NAMES + slot * 4, name)
                self.w32(G_NAMED_OBJECTS + slot * 4, obj)
                return slot
            slot = (slot + 1) & 511
        raise ContractFault('full name table: original loops indefinitely')

    def constructor_names(self, obj):
        """0x14cd84-0x14cf58: search each ordinal TWICE, then add, then next.
        The second search and key-byte writes remain observable even if redundant."""
        for nth in range(self.property_limit):
            if not self.property_value(obj, S_NAME, nth):
                return
            self.name_add(self.property_value(obj, S_NAME, nth), obj)
        raise ContractFault('name ordinal budget')

    def gameobject_ctor(self, obj, pos, class_def, props):
        """0x14cb10. pos is the pre-store copied vector, as in Skills-A ABI.
        handle_link and res_find are external services; all other stores are modelled.
        Word/doubleword vector copies are canonicalized like ref_creature.wvec."""
        for off, value in ((0, 0), (4, 0), (0x48, S.VT_GAMEOBJECT), (8, 0),
                           (0x1C, S.F_24), (0x20, S.F_72), (0xC, 0)):
            self.w32(obj + off, value)
        self.w8(obj + 0x28, 0x19)
        self.w8(obj + 0x29, 0x49)
        self.wvec(obj + 0x10, tuple(pos))
        self.w32(obj + 0x34, 0)
        self.w32(obj + 0x24, class_def)
        if class_def and self.u32(class_def + 4) != self.u32(S.G_LUMP_GENERATION):
            k = 8
            while self.u32(class_def + k):
                if k // 8 > self.property_limit:
                    raise ContractFault('resource traversal budget')
                resolved = self.call('res_find', self.u32(class_def), self.u32(class_def + k))
                class_def = self.u32(obj + 0x24)    # 0x14cbfc, before publishing result
                self.w32(class_def + k + 4, resolved)
                k += 8
            self.w32(class_def + 4, self.u32(S.G_LUMP_GENERATION))
        col = O.s32(C.to_int(self.u32(obj + 0x10)) + 0x3C00) >> 8
        row = O.s32(C.to_int(self.u32(obj + 0x14)) + 0x3C00) >> 8
        flags = self.u32(obj + 0xC)
        cell = S.G_OFF_GRID
        if not flags & 2 and 0 <= col < 120 and 0 <= row < 120:
            cell = (0x5E95F0 if flags & 0x800 else S.G_GRID_A) + 4 * (120 * row + col)
        self.call('handle_link', cell, obj + 8, obj)
        if self.property_int(obj, S.S_HIDE):
            self.relocate_hidden_grid(obj)
        old_seed = self.u32(S.G_RAND_SEED)           # read 0x14cd5c BEFORE props store
        self.w32(obj + 0x2C, props)
        seed = (old_seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        self.w32(S.G_RAND_SEED, seed)
        self.draws += 1
        self.w32(obj + 0x44, seed >> 16)
        self.constructor_names(obj)
