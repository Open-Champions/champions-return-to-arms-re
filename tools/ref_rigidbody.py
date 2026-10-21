"""ref_rigidbody.py - what a physics prop's rigid body holds the moment its constructor is done:
rigidbody_init, rigidbody_updateDerived, quat_fromMat3 and quat_normalize as the prop chain
calls them, written as a mixin that can be added to any model on a memory image.

Reference contract, executed against the original by tools/difftest_rigidbody.py
(docs/spec/rigidbody-init.md is the prose).  Pseudo-code in my own words.

    rigidbody_init           0x1682f0  (body; f12 mass, f13 mass factor, f14 size x, f15 size y,
                                        f16 size z)            3 callers, one cosmetic draw
    rigidbody_updateDerived  0x167a58  (body)                  2 callers, no draw
    quat_fromMat3            0x164330  (quaternion out, 3x3 matrix)   (ref_core.quat_from_mat3)
    quat_normalize           0x166550  (quaternion, in place)         (ref_core.quat_normalize)

The body is 0x98 bytes (its offsets in brackets; the prop keeps it at +0x190):
    [0x00] inverse mass            [0x04] [0x08] [0x0c] inverse inertia about body x, y, z
    [0x10] position (set by the owner; init clears it)
    [0x1c] orientation x, y, z, w  [0x2c] linear momentum    [0x38] angular momentum
    [0x44] rotation matrix (3x3, row major; R = the transpose of the quaternion's matrix)
    [0x68] inverse inertia in the world (3x3)               [0x8c] angular velocity

Draws: rigidbody_init takes ONE draw from the COSMETIC seed 0x404460 (never the shared seed
0x404464).  rigidbody_updateDerived and the two quaternion functions draw nothing.

Float rules: every operation goes through ref_core (R5900 single precision, results
truncated), in the order the code does it.
"""
import ref_core as C

RIGIDBODY_INIT, RIGIDBODY_UPDATE_DERIVED = 0x1682F0, 0x167A58
QUAT_FROM_MAT3, QUAT_NORMALIZE = 0x164330, 0x166550

G_COSMETIC_SEED = 0x404460
SEED_MUL, SEED_ADD = 0x19660D, 0x3C6EF35F       # ori 0x168370's operand, lui/ori at 0x168384..0x1683a0
BODY_SIZE = 0x98                                # memset length, 0x168344
F_SEED_SCALE = 0x37800000                       # 2^-16, lui at 0x16838c
F_TWELVE = 0x41400000                           # lui at 0x168380
M32 = 0xFFFFFFFF

NAMES = {'rigidbody_init': RIGIDBODY_INIT, 'rigidbody_updateDerived': RIGIDBODY_UPDATE_DERIVED,
         'quat_fromMat3': QUAT_FROM_MAT3, 'quat_normalize': QUAT_NORMALIZE}
# bodies tools/difftest_rigidbody.py runs REAL and compares (name -> entry); tools/probe_full_placement.py reads this
EXECUTED = dict(NAMES)

# the matrix bodies under them (executed by tools/difftest_core.py; real in the composed run)
UNDER = {'mat3_transpose': 0x166298, 'mat3_mul': 0x165710, 'mat3_mulVecTransposed': 0x165DA0}


class RigidMixin:
    """Needs u32, w32 on the host model."""

    def _rw(self, a, n):
        return [self.u32(a + 4 * k) for k in range(n)]

    def _rwrite(self, a, values):
        for k, v in enumerate(values):
            self.w32(a + 4 * k, v)

    def cosmetic_draw(self):
        """The generator step of 0x168354..0x1683fc: seed = seed x 0x19660d + 0x3c6ef35f
        (mod 2^32); returns the new seed (the value the caller uses is its high half)."""
        seed = (self.u32(G_COSMETIC_SEED) * SEED_MUL + SEED_ADD) & M32
        self.w32(G_COSMETIC_SEED, seed)
        return seed

    def rb_init(self, body, mass, factor, sx, sy, sz):
        """rigidbody_init 0x1682f0.

        1. The 0x98 bytes are cleared.
        2. M = factor x mass; the three inverse inertias are 12 / (M x (b^2 + c^2)) for the box
           of sizes (sx, sy, sz): body[4] about x uses (sy, sz), body[8] about y (sx, sz),
           body[0xc] about z (sx, sy).  body[0] = 1 / mass.
        3. The orientation is (0, 0, 1, u) with u = (seed >> 16) x 2^-16 from ONE cosmetic draw:
           a turn about the vertical axis (x = y = 0, so q is (0, 0, sin, cos) of half
           the angle, with cos / sin = u: an angle of 2 atan2(1, u), 90 to 180 degrees).
        4. quat_normalize twice (the second after the angular momentum body[0x38..0x40] is
           stored as zero again).
        5. body[0x44] = the rotation matrix of the normalised quaternion, transposed;
           body[0x8c] = the zero angular momentum rotated by body[0x68] (all zero), written as
           the product the library function gives."""
        mul, add = C.mul, C.add
        x2, y2, z2 = mul(sx, sx), mul(sy, sy), mul(sz, sz)
        for off in range(0, BODY_SIZE, 4):
            self.w32(body + off, 0)
        m = mul(factor, mass)
        about_x = mul(m, add(y2, z2))
        about_z = mul(m, add(x2, y2))
        about_y = mul(m, add(x2, z2))
        self.w32(body + 0x24, C.ONE)
        seed = self.cosmetic_draw()
        u = C.mul(C.from_int(seed >> 16), F_SEED_SCALE)
        self.w32(body + 0x00, C.div(C.ONE, mass))
        self.w32(body + 0x04, C.div(F_TWELVE, about_x))
        self.w32(body + 0x0C, C.div(F_TWELVE, about_z))
        self.w32(body + 0x08, C.div(F_TWELVE, about_y))
        self.w32(body + 0x28, u)
        q = C.quat_normalize(self._rw(body + 0x1C, 4))
        self._rwrite(body + 0x1C, q)
        q = C.quat_normalize(q)
        self._rwrite(body + 0x1C, q)
        r = C.mat3_transpose(C.mat3_from_quat(q))
        self._rwrite(body + 0x44, r)
        self._rwrite(body + 0x8C, C.mat3_mul_vec_transposed(self._rw(body + 0x68, 9), self._rw(body + 0x38, 3)))

    def rb_update_derived(self, body):
        """rigidbody_updateDerived 0x167a58 (body).

        quat_normalize(orientation) in place; R = the transpose of its matrix -> body[0x44];
        M[row][col] = R[row][col] x inverse inertia[col]; the world inverse inertia body[0x68] =
        M x R^T; angular velocity body[0x8c] = body[0x68] applied to the angular momentum
        body[0x38] by mat3_mulVecTransposed.  Nothing else is read or written."""
        q = C.quat_normalize(self._rw(body + 0x1C, 4))
        self._rwrite(body + 0x1C, q)
        r = C.mat3_transpose(C.mat3_from_quat(q))
        self._rwrite(body + 0x44, r)
        inertia = self._rw(body + 4, 3)
        m = [C.mul(r[3 * row + col], inertia[col]) for row in range(3) for col in range(3)]
        iw = C.mat3_mul(m, C.mat3_transpose(r))
        self._rwrite(body + 0x68, iw)
        self._rwrite(body + 0x8C, C.mat3_mul_vec_transposed(iw, self._rw(body + 0x38, 3)))

    def rb_quat_from_mat3(self, out, matrix):
        self._rwrite(out, C.quat_from_mat3(self._rw(matrix, 9)))

    def rb_quat_normalize(self, q):
        self._rwrite(q, C.quat_normalize(self._rw(q, 4)))

    def rigid_call(self, name, args):
        """Run one of the four bodies as the prop chain's call would; (True, None) when handled."""
        if name == 'rigidbody_init':
            self.rb_init(*args)
        elif name == 'rigidbody_updateDerived':
            self.rb_update_derived(*args)
        elif name == 'quat_fromMat3':
            self.rb_quat_from_mat3(*args)
        elif name == 'quat_normalize':
            self.rb_quat_normalize(*args)
        else:
            return False, None
        return True, None
