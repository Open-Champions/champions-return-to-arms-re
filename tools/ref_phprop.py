"""ref_phprop.py - the physics-prop constructor chain a gut chunk (blood) is built by:
PhProp_ctor, Prop_ctorNamedLaunch, Prop_launch and PhProp_initPhysics, under the
already executed GutChunk_ctor and GameObject_ctor.

Reference contract, executed against the original by tools/difftest_phprop.py
(docs/spec/gut-chunk.md is the prose).  Everything here is Observed by that difftest
unless a docstring says otherwise.

    GutChunk_ctor          0x201958  (tools/ref_combat_round3.py; PhProp_ctor now real under it)
    PhProp_ctor            0x155a0c  (scale; obj, position, lump, model, texture, part mask,
                                      launch flags, item record)
    PhProp_ctor2           0x1556c0  (scale; obj, position, facing, model, anim state, lump, model
                                      name, texture; stack: part bits, launch flags, item record):
                                      the prop of a body part, placed by the creature's joint
    Gold_ctor2             0x157668  (obj, position, value): the dropped gold pile
    Prop_ctorNamedLaunch   0x153e54  (obj, position, lump, model, texture, part mask, launch flags)
    Prop_launch            0x1541a0  (obj, launch flags)
    PhProp_initPhysics     0x155110  (obj, launch flags)
    GameObject_ctor        0x14cb10  (tools/ref_skills_a.py, borrowed)

Draws for one prop: ONE SHARED draw (GameObject_ctor seeds +0x44), then OWN draws of +0x44:
one facing, 0-3 launch draws by flag, three spin draws, and one sound draw for an item
prop launched with any of 0x19.  A gut chunk (launch 0xb41, no item) makes 1 shared and
7 own draws.
"""
import ref_core as C
import ref_creature as RC
import ref_combat_round3 as R3
from ref_creature import Ext, M32, M64, s16, s32

GUTCHUNK_CTOR, PHPROP_CTOR, PHPROP_CTOR2, GOLD_CTOR2 = 0x201958, 0x155A0C, 0x1556C0, 0x157668
VT_GOLD = 0x511A88                                  # 0x1576b0/0x1576b8
R_GOLD_CLIP = 0x6E01B0                              # the resource reference of the gold clip (0x157714/0x157718)
PROP_CTOR_NAMED_LAUNCH, PROP_LAUNCH, PHPROP_INIT_PHYSICS = 0x153E54, 0x1541A0, 0x155110
VT_PROP, VT_PHPROP = 0x511D58, 0x511BA8             # stored at 0x153ebc/0x153ec0, 0x155a54/0x155a58
ITEM_NAME_FIELD = 0x403AB8                          # +0x34 of an item prop (0x155b1c/0x155b20)
G_PROP_OPTIONS = 0x44FE08                           # bit 0x100 damps every launch (0x15446c/0x154494)
S_FX_LUMP = 0x532478                                # the lump of the item-drop sound (0x155b9c/0x155ba0)
S_SWISH_FORMAT = 0x532688                           # the sound name format, one %d (0x155b84/0x155b8c)

F_2M16 = RC.F_2M16                                  # 0x37800000
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_QUARTER = 0x3E800000                              # 0x1544c4
F_TWO, F_FOUR, F_TEN = 0x40000000, 0x40800000, 0x41200000
F_30, F_60, F_124, F_130 = 0x41F00000, 0x42700000, 0x42F80000, 0x43020000
F_224, F_260, F_324, F_400, F_480 = 0x43600000, 0x43820000, 0x43A20000, 0x43C80000, 0x43F00000
F_SIXTIETH = 0x3C888888                             # 0x155210/0x155214
F_DAMP_LIGHT, F_DAMP_HEAVY = 0xBDCCCCCC, 0xBECCCCCC  # -0.1 with launch 0x800, else -0.4

MODELLED = {
    'GutChunk_ctor': GUTCHUNK_CTOR, 'PhProp_ctor': PHPROP_CTOR,
    'Prop_ctorNamedLaunch': PROP_CTOR_NAMED_LAUNCH, 'Prop_launch': PROP_LAUNCH,
    'PhProp_initPhysics': PHPROP_INIT_PHYSICS, 'GameObject_ctor': 0x14CB10,
    'PhProp_ctor2': PHPROP_CTOR2, 'Gold_ctor2': GOLD_CTOR2,
    # tools/ref_core.py's matrix bodies, executed by tools/difftest_core.py, run for real
    'mat34_setPosRotZScale': 0x163CB8, 'mat34_mul': 0x162808, 'mat34_transformPoint': 0x1660A0,
}
# the bodies tools/difftest_phprop.py adds to what was executed before (name -> entry)
EXECUTED = {'PhProp_ctor': PHPROP_CTOR, 'Prop_ctorNamedLaunch': PROP_CTOR_NAMED_LAUNCH,
            'Prop_launch': PROP_LAUNCH, 'PhProp_initPhysics': PHPROP_INIT_PHYSICS}

# Callees that stay recording callbacks.  Kinds as ref_creature.Ext, plus q: a 64-bit
# register, w: a word the callee fills, S: a text pointer (a stack buffer is compared by
# its text, ('buf', text); any other pointer by address).
EXTERNALS = {
    'handle_link': Ext(0x1A1738, 'ppp', 0, 'n', '(list head, node, object)'),
    'obj_getPropInt': Ext(0x14C880, 'ppi', 0, 'i', '(object, property name, default)'),
    'res_find': Ext(0x17365C, 'pS', 0, 'i', '(lump name, entry name) -> entry or 0'),
    'model_getBounds': Ext(0x179400, 'pqwwwwww', 0, 'n', '(model, hide mask, six bounds)'),
    'obj_updateGridCell': Ext(0x14F028, 'p', 0, 'n', '(object)'),
    'obj_runEveryFrame': Ext(0x14F248, 'p', 0, 'n', '(object)'),
    'obj_stopRunning': Ext(0x14F290, 'p', 0, 'n', '(object)'),
    'rigidbody_init': Ext(0x1682F0, 'p', 5, 'n', '(body; mass 1, 1, size x, size y, size z)'),
    'quat_fromMat3': Ext(0x164330, 'pp', 0, 'n', '(quaternion, matrix)'),
    'quat_normalize': Ext(0x166550, 'p', 0, 'n', '(quaternion)'),
    'rigidbody_updateDerived': Ext(0x167A58, 'p', 0, 'n', '(body)'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'i', '(entry, object; volume)'),
    'libc_sprintf': Ext(0x3B7EF0, '-pi', 0, 's', '(stack buffer, format, one integer) -> the text'),
    'model_getMeshJoint': Ext(0x179358, 'pi', 0, 'i', '(model, mesh index) -> joint'),
    'anim_getJointMatrix': Ext(0x16F720, 'piM', 0, 'n', '(anim state, joint, out mat34)'),
    'anim_clear': Ext(0x1707B0, 'p', 0, 'n', '(anim state)'),
    'resref_get': Ext(0x17377C, 'p', 0, 'i', '(resource reference) -> data'),
    'anim_push': Ext(0x170838, 'ppi', 0, 'n', '(anim state, clip, flags)'),
}


def render(fmt, value):
    """What libc_sprintf writes for a format with one %d (the only kind this chain uses)."""
    return fmt.replace(b'%d', b'%d' % value)


def bit_index(mask):
    """+0x22c: the index of the highest set bit of the 64-bit part mask, -1 for none."""
    return (mask & M64).bit_length() - 1


class Model(R3.Model):
    """GutChunk_ctor with the prop chain under it, on a memory image."""

    def call(self, name, *args):
        if name == 'PhProp_ctor' and name not in self.external:
            return self.phprop_ctor(*args)
        if name == 'libc_sprintf':                  # (format, one integer): a stub of the rig
            self.calls.append((name, args))
            return render(self.cstr(args[0]), args[1])
        if name == 'anim_getJointMatrix':           # a 3x4 matrix the callee fills
            args = tuple(a & M32 for a in args)
            self.calls.append((name, args))
            function = self.cb.get(name)
            return list(function(*args)) if function is not None else [0] * 12
        if name == 'model_getBounds':               # the mask is a 64-bit register
            args = (args[0] & M32, args[1] & M64)
            self.calls.append((name, args))
            function = self.cb.get(name)
            return function(*args) if function is not None else (0,) * 6
        if name in EXTERNALS and self.cb.get(name) is None:
            self.calls.append((name, tuple(a & M32 if isinstance(a, int) else a for a in args)))
            return None if EXTERNALS[name].ret == 'n' else 0
        return R3.Model.call(self, name, *args)

    # ---- helpers ------------------------------------------------------------------------
    def strcpy(self, dst, src):
        """libc_strcpy 0x3b868c (runs for real): through the terminator."""
        k = 0
        while True:
            b = self.u8(src + k)
            self.w8(dst + k, b)
            if not b:
                return
            k += 1

    def bounds(self, obj):
        """model_getBounds(+0x4c, the 64-bit mask +0xe8) -> (min x, y, z, max x, y, z) as
        signed integers."""
        out = self.call('model_getBounds', self.u32(obj + 0x4C), self.u64(obj + 0xE8))
        return tuple(s32(v) for v in out)

    def frac(self, d):
        return C.mul(C.from_int(d), F_2M16)

    # ---- PhProp_ctor ------------------------------------------------------------------------
    def phprop_ctor(self, obj, pos, lump, model, texture, part_mask, launch, item, scale):
        """PhProp_ctor 0x155a0c (obj, position, lump, model, texture, part mask, launch
        flags, item record; scale).

        Prop_ctorNamedLaunch with a copy of the position and the other arguments
        unchanged; table 0x511ba8; an empty item record at +0x148 (the four slot ids
        +0x16c + 8k = 0xffff, bytes +0x168/+0x169 = 0xff, the halfwords +0x158..+0x166 = 0);
        +0x240 = scale; flags |= 0x4000 (deleted when it stops).  With an item record: its
        0x48 bytes copied to +0x148, byte +0x238 = 1, +0x34 = 0x403ab8, flags |= 0x100000
        and loses 0x800 and 0x4000.  Byte +0x23a = 0, +0x234 = 0, PhProp_initPhysics.  Then,
        an item prop (+0x238 non-zero) launched with any of 0x19: ONE OWN DRAW d, the sound
        'game_swish_chest<d % 3 + 1>' of fx.lmp on the prop, volume 1."""
        self.prop_ctor_named_launch(obj, tuple(pos), lump, model, texture, part_mask, launch)
        w8, w16, w32 = self.w8, self.w16, self.w32
        w32(obj + 0x48, VT_PHPROP)
        for k in range(4):
            w16(obj + 0x16C + 8 * k, 0xFFFF)
        w8(obj + 0x169, 0xFF)
        w8(obj + 0x168, 0xFF)
        for k in range(4):
            w16(obj + 0x158 + 2 * k, 0)
            w16(obj + 0x160 + 2 * k, 0)
        w32(obj + 0x240, scale)
        w32(obj + 0xC, self.u32(obj + 0xC) | 0x4000)
        if item:
            for k in range(0, 0x48, 4):
                w32(obj + 0x148 + k, self.u32(item + k))
            w8(obj + 0x238, 1)
            w32(obj + 0x34, ITEM_NAME_FIELD)
            w32(obj + 0xC, (self.u32(obj + 0xC) | 0x100000) & ~0x800 & ~0x4000 & M32)
        w8(obj + 0x23A, 0)
        w32(obj + 0x234, 0)
        self.phprop_init_physics(obj, launch)
        if self.s8(obj + 0x238) and launch & 0x19:
            n = (self.obj_rand(obj) & M32) % 3 + 1
            text = self.call('libc_sprintf', S_SWISH_FORMAT, n)
            entry = self.call('res_find', S_FX_LUMP, ('buf', text))
            self.call('sound_playOnObject', entry, obj, ONE)

    # ---- Prop_ctorNamedLaunch -----------------------------------------------------------------
    def prop_ctor_named_launch(self, obj, pos, lump, model, texture, part_mask, launch):
        """Prop_ctorNamedLaunch 0x153e54 (obj, position, lump, model, texture, part mask,
        launch flags).

        GameObject_ctor(obj, copy of the position, no definition, no properties: ONE SHARED
        DRAW); table 0x511d58; the three names copied to +0x54, +0x64 and +0xa4;
        +0x4c = res_find(lump, model), +0x50 = res_find(lump, texture) (both by the copies);
        +0xe8 = the 64-bit part mask.  ONE OWN DRAW: the facing +0x38 (low 16 bits).
        +0x10c = 0, +0x30 = +0x100 = +0xfc = 0.  The bounds of the unhidden parts: the
        centre ((min + max) >> 1 per axis, as integers, then floats) at +0xf0/+0xf4/+0xf8,
        +0x108 = centre z - min z.  Launch bit 4 moves the position by the centre and
        relinks the grid cell.  Then Prop_launch."""
        part_mask &= M64
        if part_mask >> 31 & 1 and part_mask < 1 << 32:
            part_mask |= 0xFFFFFFFF00000000          # a 32-bit register value, sign-extended
        self.gameobject_ctor(obj, pos, 0, 0)
        w32 = self.w32
        w32(obj + 0x48, VT_PROP)
        self.strcpy(obj + 0x54, lump)
        self.strcpy(obj + 0x64, model)
        self.strcpy(obj + 0xA4, texture)
        w32(obj + 0x4C, self.call('res_find', obj + 0x54, obj + 0x64))
        texture_entry = self.call('res_find', obj + 0x54, obj + 0xA4)
        self.w64(obj + 0xE8, part_mask)
        w32(obj + 0x50, texture_entry)
        d = self.obj_rand(obj)
        self.w16(obj + 0x10C, 0)
        self.w16(obj + 0x38, d & 0xFFFF)
        w32(obj + 0x30, ZERO)
        w32(obj + 0x100, ZERO)
        w32(obj + 0xFC, ZERO)
        lo_x, lo_y, lo_z, hi_x, hi_y, hi_z = self.bounds(obj)
        cz = C.from_int(s32((lo_z + hi_z) & M32) >> 1)
        cx = C.from_int(s32((lo_x + hi_x) & M32) >> 1)
        cy = C.from_int(s32((lo_y + hi_y) & M32) >> 1)
        w32(obj + 0xF8, cz)
        w32(obj + 0xF0, cx)
        w32(obj + 0xF4, cy)
        w32(obj + 0x108, C.sub(cz, C.from_int(lo_z)))
        if launch & 4:
            w32(obj + 0x10, C.add(self.u32(obj + 0x10), cx))
            w32(obj + 0x14, C.add(self.u32(obj + 0x14), cy))
            w32(obj + 0x18, C.add(self.u32(obj + 0x18), cz))
            self.call('obj_updateGridCell', obj)
        self.prop_launch(obj, launch)

    # ---- Prop_launch ----------------------------------------------------------------------------
    def prop_launch(self, obj, launch):
        """Prop_launch 0x1541a0 (obj, launch flags).

        Flags |= 0x1809, grid cell relinked, radius +0x1c = 4.  The halfword +0x140 collects
        bits: 0x100 -> 2 (and flags |= 0x4000), 0x200 -> 4.  Velocity from OWN DRAWS
        (f = d x 2^-16), each later bit overwriting the earlier:
          1     +0xfc, +0x100 = (f - 0.5) x 124 (two draws)
          8     +0xfc, +0x100 = (f - 0.5) x 224 (two draws)
          0x10  +0xfc, +0x100 = (f - 0.5) x 324, then +0x30 = f x 480 (three draws)
          0x20  +0x30 = f x 30 + 130 (one draw)
          0x40  +0x30 = f x 60 + 260 (one draw)
        Bit 2: +0x10c = 2000.  obj_runEveryFrame.  Life +0x10e = 0x7fff with 0x8000, else
        180.  +0x140 |= 8 with 0x2000, else |= 0x10 with 0x4000; |= 0x20 with 0x10000.  Bit
        0x80: life 0, +0x140 |= 1, and obj_stopRunning unless +0x140 has 2.  With bit 0x100
        of the word 0x44fe08: +0x30 clamped to 400 (when 400 < it), then x 0.25; +0xfc and
        +0x100 x 0.5."""
        u32, w32, w16, u16 = self.u32, self.w32, self.w16, self.u16
        w32(obj + 0xC, u32(obj + 0xC) | 0x1809)
        self.call('obj_updateGridCell', obj)
        w32(obj + 0x1C, F_FOUR)
        if launch & 0x100:
            w16(obj + 0x140, u16(obj + 0x140) | 2)
            w32(obj + 0xC, u32(obj + 0xC) | 0x4000)
        if launch & 0x200:
            w16(obj + 0x140, u16(obj + 0x140) | 4)
        for bit, span in ((1, F_124), (8, F_224), (0x10, F_324)):
            if launch & bit:
                w32(obj + 0xFC, C.mul(C.sub(self.frac(self.obj_rand(obj)), HALF), span))
                w32(obj + 0x100, C.mul(C.sub(self.frac(self.obj_rand(obj)), HALF), span))
                if bit == 0x10:
                    w32(obj + 0x30, C.mul(self.frac(self.obj_rand(obj)), F_480))
        if launch & 0x20:
            w32(obj + 0x30, C.add(C.mul(self.frac(self.obj_rand(obj)), F_30), F_130))
        if launch & 0x40:
            w32(obj + 0x30, C.add(C.mul(self.frac(self.obj_rand(obj)), F_60), F_260))
        if launch & 2:
            w16(obj + 0x10C, 2000)
        self.call('obj_runEveryFrame', obj)
        w16(obj + 0x10E, 0x7FFF if launch & 0x8000 else 0xB4)
        if launch & 0x2000:
            w16(obj + 0x140, u16(obj + 0x140) | 8)
        elif launch & 0x4000:
            w16(obj + 0x140, u16(obj + 0x140) | 0x10)
        if launch & 0x10000:
            w16(obj + 0x140, u16(obj + 0x140) | 0x20)
        if launch & 0x80:
            bits = u16(obj + 0x140)
            w16(obj + 0x10E, 0)
            w16(obj + 0x140, bits | 1)
            if not bits & 2:
                self.call('obj_stopRunning', obj)
        if u32(G_PROP_OPTIONS) & 0x100:
            if C.lt(F_400, u32(obj + 0x30)):
                w32(obj + 0x30, F_400)
            w32(obj + 0x30, C.mul(u32(obj + 0x30), F_QUARTER))
            w32(obj + 0xFC, C.mul(u32(obj + 0xFC), HALF))
            w32(obj + 0x100, C.mul(u32(obj + 0x100), HALF))

    # ---- PhProp_initPhysics ---------------------------------------------------------------------
    def phprop_init_physics(self, obj, launch):
        """PhProp_initPhysics 0x155110 (obj, launch flags).

        An item prop (+0x238) whose record word +0x150 has bit 0x20000 adds launch bit
        0x1000.  The bounds again, scaled by +0x240: rigidbody_init(+0x190; 1, 1, the three
        extents max x s - min x s, ...).  Position copied to +0x1a0..+0x1a8; +0x1bc, +0x1c0,
        +0x1c4 = +0xfc, +0x100, +0x30 x 1/60 (0x3c888888).  Spin +0x1c8, +0x1cc, +0x1d0 =
        (2f - 1) x k from THREE OWN DRAWS, k = 2, or 10 with launch 0x10 or 0x400.
        +0x22c = the highest bit of the part mask +0xe8 (-1 for none).  quat_fromMat3(
        +0x1ac, +0x110), quat_normalize(+0x1ac), rigidbody_updateDerived(+0x190).  +0x23c =
        -0.1 with launch 0x800, else -0.4.  Launch 0x1000 zeroes +0x194, +0x198, +0x19c."""
        u32, w32 = self.u32, self.w32
        if self.s8(obj + 0x238) and self.u64(obj + 0x150) & 0x20000:
            launch |= 0x1000
        lo_x, lo_y, lo_z, hi_x, hi_y, hi_z = self.bounds(obj)
        s = u32(obj + 0x240)
        size = lambda lo, hi: C.sub(C.mul(C.from_int(hi), s), C.mul(C.from_int(lo), s))    # noqa: E731
        self.call('rigidbody_init', obj + 0x190, ONE, ONE, size(lo_x, hi_x), size(lo_y, hi_y), size(lo_z, hi_z))
        self.wvec(obj + 0x1A0, self.vec(obj + 0x10))
        w32(obj + 0x1BC, C.mul(u32(obj + 0xFC), F_SIXTIETH))
        w32(obj + 0x1C0, C.mul(u32(obj + 0x100), F_SIXTIETH))
        w32(obj + 0x1C4, C.mul(u32(obj + 0x30), F_SIXTIETH))
        k = F_TEN if launch & 0x410 else F_TWO
        for off in (0x1C8, 0x1CC, 0x1D0):
            f = self.frac(self.obj_rand(obj))
            w32(obj + off, C.mul(C.sub(C.add(f, f), ONE), k))
        w32(obj + 0x22C, M32)
        mask = self.u64(obj + 0xE8)
        if mask:
            w32(obj + 0x22C, bit_index(mask) & M32)
        self.call('quat_fromMat3', obj + 0x1AC, obj + 0x110)
        self.call('quat_normalize', obj + 0x1AC)
        self.call('rigidbody_updateDerived', obj + 0x190)
        w32(obj + 0x23C, F_DAMP_LIGHT if launch & 0x800 else F_DAMP_HEAVY)
        if launch & 0x1000:
            for off in (0x19C, 0x194, 0x198):
                w32(obj + off, 0)

    # ---- PhProp_ctor2 ---------------------------------------------------------------------------
    def phprop_ctor2(self, obj, pos, facing, model, anim, lump, model_name, texture, part_bits, launch, item,
                     scale):
        """PhProp_ctor2 0x1556c0 (obj, position, facing, model, anim state, lump, model name,
        texture; stack: 64-bit part bits, launch flags, item record; scale).

        Prop_ctorNamedLaunch(obj, copy of the position, lump, model name, texture, part bits,
        launch | 4): the position moves by the parts' centre.  Table 0x511ba8, the empty item
        record, +0x240 = scale, flags |= 0x4000, the item branch: all as PhProp_ctor.  +0x22c
        = the highest bit of the part mask (-1 for none), byte +0x23a = 0, +0x234 = 0.
        J = anim_getJointMatrix(anim, model_getMeshJoint(model, +0x22c)) times
        mat34_setPosRotZScale(+0x240, (0, 0, 0), s16(facing + 0x4000)) (mat34_mul(J, J, R));
        the offset (prop position - the given position) is transformed by J and added to the
        given position: the new +0x10..+0x18.  PhProp_initPhysics(obj, launch) (without the
        4), the item sound as PhProp_ctor, flags |= 0x2000.  No draws besides the chain's."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        pos = tuple(pos)
        self.prop_ctor_named_launch(obj, pos, lump, model_name, texture, part_bits, (launch | 4) & M32)
        self.phprop_record(obj, item, scale)
        w32(obj + 0x22C, M32)
        w8(obj + 0x23A, 0)
        w32(obj + 0x234, 0)
        mask = self.u64(obj + 0xE8)
        if mask:
            w32(obj + 0x22C, bit_index(mask) & M32)
        joint = self.call('model_getMeshJoint', model, u32(obj + 0x22C))
        m = self.call('anim_getJointMatrix', anim, joint)
        r = C.mat34_set_pos_rot_z_scale(u32(obj + 0x240), (ZERO, ZERO, ZERO), s16(s16(facing) + 0x4000))
        m = C.mat34_mul(m, r)
        here = self.vec(obj + 0x10)
        v = C.mat34_transform_point(m, [C.sub(here[k], pos[k]) for k in range(3)])
        self.wvec(obj + 0x10, tuple(C.add(pos[k], v[k]) for k in range(3)))
        self.phprop_init_physics(obj, launch)
        self.item_sound(obj, launch)
        w32(obj + 0xC, u32(obj + 0xC) | 0x2000)

    def phprop_record(self, obj, item, scale):
        """The part PhProp_ctor and PhProp_ctor2 share after Prop_ctorNamedLaunch."""
        w8, w16, w32 = self.w8, self.w16, self.w32
        w32(obj + 0x48, VT_PHPROP)
        for k in range(4):
            w16(obj + 0x16C + 8 * k, 0xFFFF)
        w8(obj + 0x169, 0xFF)
        w8(obj + 0x168, 0xFF)
        for k in range(4):
            w16(obj + 0x158 + 2 * k, 0)
            w16(obj + 0x160 + 2 * k, 0)
        w32(obj + 0x240, scale)
        w32(obj + 0xC, self.u32(obj + 0xC) | 0x4000)
        if item:
            for k in range(0, 0x48, 4):
                w32(obj + 0x148 + k, self.u32(item + k))
            w8(obj + 0x238, 1)
            w32(obj + 0x34, ITEM_NAME_FIELD)
            w32(obj + 0xC, (self.u32(obj + 0xC) | 0x100000) & ~0x800 & ~0x4000 & M32)

    def item_sound(self, obj, launch):
        """An item prop (+0x238) launched with any of 0x19: ONE OWN DRAW, the swish sound."""
        if self.s8(obj + 0x238) and launch & 0x19:
            n = (self.obj_rand(obj) & M32) % 3 + 1
            text = self.call('libc_sprintf', S_SWISH_FORMAT, n)
            entry = self.call('res_find', S_FX_LUMP, ('buf', text))
            self.call('sound_playOnObject', entry, obj, ONE)

    # ---- Gold_ctor2 ----------------------------------------------------------------------------
    def gold_ctor2(self, obj, pos, value):
        """Gold_ctor2 0x157668 (obj, position, value): GameObject_ctor(obj, copy of the
        position, no definition, no properties) - ONE SHARED DRAW; table 0x511a88; byte
        +0x5d = 1 (the anim state's +5); byte +0x4c = 0x29; +0x80 = value; flags |= 0x220c;
        anim_clear(+0x58); +0x50 = g_simFrame; anim_push(+0x58, resref_get(0x6e01b0),
        0x204); obj_runEveryFrame."""
        self.gameobject_ctor(obj, tuple(pos), 0, 0)
        self.w32(obj + 0x48, VT_GOLD)
        self.w8(obj + 0x5D, 1)
        self.w8(obj + 0x4C, 0x29)
        self.w32(obj + 0x80, value)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x220C)
        self.call('anim_clear', obj + 0x58)
        self.w32(obj + 0x50, self.u32(RC.G_SIM_FRAME))
        clip = self.call('resref_get', R_GOLD_CLIP)
        self.call('anim_push', obj + 0x58, clip, 0x204)
        self.call('obj_runEveryFrame', obj)

    # ---- entries the difftest calls directly ----------------------------------------------------
    def phprop_ctor_entry(self, obj, pos, lump, model, texture, part_mask, launch, item, scale):
        return self.phprop_ctor(obj, pos, lump, model, texture, part_mask, launch, item, scale)
