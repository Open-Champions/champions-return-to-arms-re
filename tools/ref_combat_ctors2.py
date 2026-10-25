"""ref_combat_ctors2.py - Skeleton_isEnemy, Soul_takeDamage, Skeleton_takeDamage and the
six inline destructors the AntQueen, Skeleton, Soul, Fire, LooseFire and poisonGasSpell
classes install, plus the type-info getters and type_info comparison they reach.

Reference contract, executed against the original by tools/difftest_combat_ctors2.py
(docs/spec/combat-ctors-2.md is the prose).  Everything here is Observed by that
difftest unless a docstring says otherwise.

    Skeleton_isEnemy        0x2a7e04   Skeleton slot 20
    Skeleton_takeDamage     0x2a774c   Skeleton slot 2
    AntQueen_takeDamage     0x2378fc   AntQueen slot 2
    Soul_takeDamage         0x2aa908   Soul slot 2
    AntQueen_dtor           0x3c3c10   Skeleton_dtor   0x3cc5b8   Soul_dtor   0x3cc72c
    Fire_dtor               0x3c5050   LooseFire_dtor  0x3c6778   poisonGasSpell_dtor 0x3c7878
    type-info getters       (TYPEINFO below)          rtti_typeInfoEquals 0x3b1250

The destructor chain underneath (Creature_dtor 0x117128, GameObject_dtor 0x14cf90) is
tools/ref_combat_monsters.py's executed body, borrowed here unchanged.
"""
import ref_core as C
import ref_creature as RC
import ref_combat_ctors as CT
import ref_combat_monsters as CM
import ref_monsters_1 as M1
import ref_potion_ctors as PC
from ref_creature import Ext, M32, s16, s32

# ---- class tables (Observed at the constructors and in the tables themselves) ----------
VT_ANTQUEEN, VT_SKELETON, VT_SOUL = CT.VT_ANTQUEEN, CT.VT_SKELETON, CT.VT_SOUL
VT_SKELIGHT, VT_PLAYER, VT_DEMON = 0x5174B0, 0x511308, 0x514B40
VT_FIRE, VT_LOOSEFIRE, VT_POISONGAS = 0x50F208, 0x50E2B8, 0x50D500
VT_SI_TYPEINFO = 0x51DF48       # __si_type_info table, stored by 0x3b12b8
VT_USER_TYPEINFO = 0x51DF78     # __user_type_info table, stored by 0x3b12d8
P_SOUL = CT.P_SOUL              # 0x8e4600, the particle definition (formed at 0x2aaae8)
F_2M16 = RC.F_2M16              # 0x37800000 (loaded at 0x2aaa30)
F_15 = CT.F_15                  # 0x41700000 (loaded at 0x2aaac8)
ONE, ZERO = RC.ONE, RC.ZERO     # 0x3f800000 (loaded at 0x2aaa4c)
SOUL_PARTICLES = 6              # the limit tested at 0x2aab30
FACING_BIAS = 0x4000            # subtracted at 0x2aa9f4

# Type-info getters: getter -> (descriptor, name string, base getter or None).  Each tests
# word 0 of its descriptor; when it is 0 the base getter runs (its result unused) and
# rtti_initSingleBaseTypeInfo 0x3b12b8 stores (+0 name, +4 VT_SI_TYPEINFO, +8 base
# descriptor); GameObject's has no base and rtti_initUserTypeInfo 0x3b12d8 stores (+0
# name, +4 VT_USER_TYPEINFO).  The addresses are the two immediate halves each getter forms.
TYPEINFO = {
    0x3C7E10: (0x564318, 0x532210, None),       # GameObject_typeinfo   "10GameObject"
    0x3C2608: (0x908130, 0x530150, 0x3C7E10),   # Creature_typeinfo     "8Creature"
    0x3CC62C: (0x908E20, 0x54C168, 0x3C2608),   # Skeleton_typeinfo     "8Skeleton"
    0x3CC7A0: (0x908E30, 0x54C3E0, 0x3C2608),   # Soul_typeinfo         "4Soul"
    0x3C3C78: (0x908680, 0x530A80, 0x3C2608),   # AntQueen_typeinfo     "8AntQueen"
    0x3CC6DC: (0x908E10, 0x54C178, 0x3C2608),   # Skelight_typeinfo     "8Skelight"
    0x3C3AB8: (0x9083D0, 0x530A70, 0x3C2608),   # Player_typeinfo       "6Player"
    0x3CA81C: (0x908B80, 0x5454A0, 0x3C2608),   # Demon_typeinfo        "5Demon"
}
TI_SKELETON, TI_DEMON = 0x3CC62C, 0x3CA81C

MODELLED = {
    'Skeleton_isEnemy': 0x2A7E04, 'Skeleton_takeDamage': 0x2A774C, 'Soul_takeDamage': 0x2AA908,
    'AntQueen_takeDamage': 0x2378FC, 'AntQueen_dtor': 0x3C3C10, 'Skeleton_dtor': 0x3CC5B8, 'Soul_dtor': 0x3CC72C,
    'Fire_dtor': 0x3C5050, 'LooseFire_dtor': 0x3C6778, 'poisonGasSpell_dtor': 0x3C7878,
    'Creature_dtor': 0x117128, 'GameObject_dtor': 0x14CF90,
}
MODELLED.update({'typeinfo_%x' % g: g for g in TYPEINFO})
# The bodies this module adds and tools/difftest_combat_ctors2.py executes (name -> address);
# Creature_dtor and GameObject_dtor are tools/ref_combat_monsters.py's, borrowed.
EXECUTED = {name: addr for name, addr in MODELLED.items() if name not in ('Creature_dtor', 'GameObject_dtor')}

# virtual bodies: function -> (slot, method)
CLASS_BODIES = {
    0x2A7E04: (20, 'skeleton_is_enemy'), 0x2A774C: (2, 'skeleton_take_damage'),
    0x2AA908: (2, 'soul_take_damage'), 0x2378FC: (2, 'antqueen_take_damage'),
    0x3C3C10: (1, 'antqueen_dtor'), 0x3CC5B8: (1, 'skeleton_dtor'), 0x3CC72C: (1, 'soul_dtor'),
    0x3C5050: (1, 'fire_dtor'), 0x3C6778: (1, 'loosefire_dtor'), 0x3C7878: (1, 'poison_gas_dtor'),
}

INTERNAL = {'Creature_dtor': 'creature_dtor', 'GameObject_dtor': 'gameobject_dtor'}

_DTOR_EXTS = {
    'objNames_remove': Ext(0x14BE58, 'pp', 0, 'n', '(name, object)'),
    'pool_free': Ext(0x150470, 'p', 0, 'n', '(block)'),
    'AnimState_dtor': Ext(0x171098, 'pi', 0, 'n', '(anim state, flags)'),
    'sub_202500': Ext(0x202500, 'pi', 0, 'n', '(+0x320, 2): frees only with bit 0'),
    'Spell.v1': Ext(0, 'pi', 0, 'n', 'an attached spell destroyed (3)'),
    'handle_clear': Ext(0x1A1698, 'p', 0, 'n', '(list head)'),
}
EXTERNALS = dict(CT.EXTERNALS)
EXTERNALS.update(_DTOR_EXTS)
EXTERNALS.update({
    'Creature.v0': Ext(0, '', 0, 'i', 'type-info getter of a class this model does not know'),
    'cxx_throwBadTypeid': Ext(0x3B3338, '', 0, 'n', 'typeid(*null): throws bad_typeid'),
})
GO_EXTERNALS = dict(PC.EXTERNALS)
GO_EXTERNALS.update(_DTOR_EXTS)


try:                                            # a stop the difftests treat like the interpreter's
    from ee_emu import EmuError as _Stop
except ImportError:                             # pragma: no cover
    _Stop = Exception


class BadTypeid(_Stop):
    """typeid(*attacker) with attacker 0: the original calls __throw_bad_typeid 0x3b3338."""


def shape_result(name, args, ret=0, fret=0, outs=None):
    """M1.shape_result for this module's rows."""
    saved = M1.EXTERNALS
    M1.EXTERNALS = EXTERNALS
    try:
        return M1.shape_result(name, args, ret, fret, outs)
    finally:
        M1.EXTERNALS = saved


def c_rem(a, b):
    """The machine's signed remainder: the sign of the dividend."""
    a, b = s32(a), s32(b)
    r = abs(a) % abs(b)
    return -r if a < 0 else r


class _Dtors:
    """The destructor bodies, shared by the creature and the GameObject models."""

    # tools/ref_combat_monsters.py, executed there by tools/difftest_combat_monsters.py
    _lower_key = CM.MonsterCombatModel._lower_key
    _strneq = CM.MonsterCombatModel._strneq
    _find_name = CM.MonsterCombatModel._find_name
    gameobject_dtor = CM.MonsterCombatModel.gameobject_dtor
    creature_dtor = CM.MonsterCombatModel.creature_dtor

    def _class_dtor(self, o, flags, table, handles, base):
        """The inline destructor shape: +0x48 = the class table, handle_clear of each of
        `handles` in order, the base destructor with 0, then pool_free(o) when bit 0 of
        flags is set (a tail jump; the base itself never frees)."""
        self.w32(o + 0x48, table)
        for off in handles:
            self.call('handle_clear', o + off)
        self.call(base, o, 0)
        if flags & 1:
            self.call('pool_free', o)

    def antqueen_dtor(self, c, flags):
        """AntQueen_dtor 0x3c3c10 (slot 1): table 0x511078, Creature_dtor(c, 0), free."""
        self._class_dtor(c, flags, VT_ANTQUEEN, (), 'Creature_dtor')

    def skeleton_dtor(self, c, flags):
        """Skeleton_dtor 0x3cc5b8 (slot 1): table 0x5175f8, handle_clear +0x3cc then +0x3c8,
        Creature_dtor(c, 0), free.  The WeaponShield holder built inline at +0x3d8 has no
        destructor call here."""
        self._class_dtor(c, flags, VT_SKELETON, (0x3CC, 0x3C8), 'Creature_dtor')

    def soul_dtor(self, c, flags):
        """Soul_dtor 0x3cc72c (slot 1): table 0x517740, handle_clear +0x3cc then +0x3c8
        (the owner handle), Creature_dtor(c, 0), free."""
        self._class_dtor(c, flags, VT_SOUL, (0x3CC, 0x3C8), 'Creature_dtor')

    def fire_dtor(self, o, flags):
        """Fire_dtor 0x3c5050 (slot 1): table 0x50f208, GameObject_dtor(o, 0), free."""
        self._class_dtor(o, flags, VT_FIRE, (), 'GameObject_dtor')

    def loosefire_dtor(self, o, flags):
        """LooseFire_dtor 0x3c6778 (slot 1): table 0x50e2b8, handle_clear +0x4c (the
        owner), GameObject_dtor(o, 0), free."""
        self._class_dtor(o, flags, VT_LOOSEFIRE, (0x4C,), 'GameObject_dtor')

    def poison_gas_dtor(self, o, flags):
        """poisonGasSpell_dtor 0x3c7878 (slot 1): table 0x50d500, handle_clear +0x4c (the
        owner), GameObject_dtor(o, 0), free."""
        self._class_dtor(o, flags, VT_POISONGAS, (0x4C,), 'GameObject_dtor')


class Model(_Dtors, CT.Model):
    """The three creature classes of ref_combat_ctors plus the bodies above."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        method = INTERNAL.get(name)
        if method is not None:
            return getattr(self, method)(*args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        function = self.u32(table + 8 * slot + 4)
        body = CLASS_BODIES.get(function)
        if body is not None and body[0] == slot:
            this = (obj + self.s16(table + 8 * slot)) & M32
            return getattr(self, body[1])(this, *args)
        return CT.Model.vcall(self, obj, slot, *args)

    # ---- run-time type information ---------------------------------------------------
    def typeinfo(self, getter):
        """A type-info getter: the descriptor, built on first use (see TYPEINFO)."""
        desc, name, base = TYPEINFO[getter]
        if not self.u32(desc):
            if base is None:
                self.w32(desc, name)
                self.w32(desc + 4, VT_USER_TYPEINFO)
            else:
                self.typeinfo(base)
                self.w32(desc + 8, TYPEINFO[base][0])
                self.w32(desc, name)
                self.w32(desc + 4, VT_SI_TYPEINFO)
        return desc

    def typeid(self, obj):
        """typeid(*obj): virtual slot 0 of obj's table.  A getter of TYPEINFO runs here;
        any other is the call-out 'Creature.v0' (its `this` is not used by a getter)."""
        function = self.u32(self.u32(obj + 0x48) + 4)
        if function in TYPEINFO:
            return self.typeinfo(function)
        return self.call('Creature.v0')

    def typeinfo_equals(self, a, b):
        """rtti_typeInfoEquals 0x3b1250: the same descriptor, or libc_strcmp of the two
        name words equal to 0."""
        if a == b:
            return True
        return self._cbytes(self.u32(a)) == self._cbytes(self.u32(b))

    def _cbytes(self, addr, limit=256):
        out = bytearray()
        while len(out) < limit:
            ch = self.u8(addr + len(out))
            if not ch:
                break
            out.append(ch)
        return bytes(out)

    # ---- Skeleton ----------------------------------------------------------------------
    def skeleton_is_enemy(self, c, other):
        """Skeleton_isEnemy 0x2a7e04, slot 20 (skeleton, other) -> 0, 1, 2 or 5.

        r = Creature_isEnemy(c, other) (0, 1 or 4).  A non-zero r is returned as r + 1.
        With r == 0 (and other not 0): 1 when typeid(*other) == typeid(Skeleton) (exact
        class, by descriptor or by name), other's object flag 8 (dead) is clear, the
        skeleton's own charm timer +0x312 is 0, and the two side bytes +0x3d4 (signed)
        are 2 and 1 or 1 and 2; otherwise 0.  The other's slot 0 is reached only when r
        is 0, and the Skeleton getter only when that call returned."""
        r = s32(self.is_enemy(c, other))
        result = (r + 1) & M32 if r else 0
        if not other or result:
            return result
        mine = self.typeid(other)
        if not self.typeinfo_equals(mine, self.typeinfo(TI_SKELETON)):
            return 0
        if self.u32(other + 0xC) & 8:
            return 0
        if self.s16(c + 0x312):
            return 0
        me, him = self.s8(c + 0x3D4), self.s8(other + 0x3D4)
        return 1 if (me, him) in ((2, 1), (1, 2)) else 0

    def skeleton_take_damage(self, c, attacker, flags, amount):
        """Skeleton_takeDamage 0x2a774c, slot 2: a call of Creature_takeDamage with the
        same four arguments, nothing else."""
        self.take_damage(c, attacker, flags, amount)

    def antqueen_take_damage(self, c, attacker, flags, amount):
        """AntQueen_takeDamage 0x2378fc, slot 2: the same wrapper - a linked call (not a
        jump) of Creature_takeDamage with the four arguments unchanged, nothing else."""
        self.take_damage(c, attacker, flags, amount)

    # ---- Soul ------------------------------------------------------------------------------
    def soul_take_damage(self, c, attacker, flags, amount):
        """Soul_takeDamage 0x2aa908, slot 2 (soul, attacker, flags; amount).

        typeid(*attacker) == typeid(Demon), exact class.  A null attacker calls
        __throw_bad_typeid (BadTypeid here).  Not a Demon: nothing at all.  A Demon:
        Creature_takeDamage(c, attacker, flags, amount), then n =
        model_getSamplePointCount(slot 16); n == 0 ends it.  Otherwise SIX particles,
        each: slot 16 again; ONE OWN DRAW d, index = d % n (signed remainder);
        model_getSamplePoint(model, +0x114, the position, s16(facing - 0x4000), index,
        out, second out; scale +0xdc); a unit-ball vector by OWN DRAW rejection (three
        draws a try, (2 d 2^-16 - 1) each, again while x^2 + y^2 + z^2 > 1); its z word
        zeroed, then x, y (and the zero) times 15; particle_spawn(0x8e4600, the point,
        that velocity; 0).  No shared draw of its own."""
        if not attacker:
            self.call('cxx_throwBadTypeid')
            raise BadTypeid('Soul_takeDamage with no attacker: __throw_bad_typeid')
        mine = self.typeid(attacker)
        if not self.typeinfo_equals(mine, self.typeinfo(TI_DEMON)):
            return
        self.take_damage(c, attacker, flags, amount)
        count = self.call('model_getSamplePointCount', self.vcall(c, 16))
        if not count:
            return
        for _ in range(SOUL_PARTICLES):
            model = self.vcall(c, 16)
            index = c_rem(self.obj_rand(c), count)
            facing = s16((self.u16(c + 0x38) - FACING_BIAS) & 0xFFFF)
            point, _second = self.call('model_getSamplePoint', model, c + 0x114, self.vec(c + 0x10), facing & M32,
                                       index & M32, 1, 0, self.u32(c + 0xDC))
            while True:
                v = [C.sub(C.add(f, f), ONE) for f in
                     (C.mul(C.from_int(self.obj_rand(c)), F_2M16) for _k in range(3))]
                size = C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))
                if not C.lt(ONE, size):
                    break
            self.call('particle_spawn', P_SOUL, tuple(point),
                      (C.mul(v[0], F_15), C.mul(v[1], F_15), C.mul(ZERO, F_15)), ZERO)


class GOModel(_Dtors, PC.Model):
    """ref_potion_ctors' model (LooseFire, Fire, poison gas) plus their destructors."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        method = INTERNAL.get(name)
        if method is not None:
            return getattr(self, method)(*args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        saved = M1.EXTERNALS
        M1.EXTERNALS = GO_EXTERNALS
        try:
            return M1.shape_result(name, args)
        finally:
            M1.EXTERNALS = saved

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        body = CLASS_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and body[0] == slot:
            return getattr(self, body[1])((obj + self.s16(table + 8 * slot)) & M32, *args)
        return PC.Model.vcall(self, obj, slot, *args)
