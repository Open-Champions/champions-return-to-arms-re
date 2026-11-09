"""Player locomotion blend, root motion, hit-reaction clip choice and melee timing.

SLUS-20973 US v2.00. Addresses, labels and limits are in docs/player-anim-states.md.
Every float is a 32-bit pattern and every operation is one ref_core (R5900) operation
in the order the original performs it. The two run-layer weights use the game's
software double library (GCC fp-bit without rounding, docs/spec/core.md section 9):
each widen is exact, each subtract and multiply is the exact result truncated toward
zero to 53 bits, and the narrow truncates to 24 bits.
"""
import struct
from fractions import Fraction

import ref_core as C

ONE, ZERO = C.ONE, C.ZERO

# ---- Player_move mode 0, animation half (0x1b4794-0x1b4a3c) --------------------------
K_KNEE1 = 0x3EDC28F5        # 0.43
K_KNEE2 = 0x3F333333        # 0.7
K_SLOPE1 = 0x4014D653       # 2.3255813
K_SLOPE2A, K_SLOPE2B = 0x406D097A, 0x3EB33330
K_SLOPE3A, K_SLOPE3B, K_BASE3 = 0x40555554, 0x3E1999A0, 0x3FACCCCC
K_MOVING = 0x3C23D70A       # 0.01
K_RAMP = 0x3DCCCCCC         # 0.1 per tick
K_REST = 0x3D4CCCCC         # 0.05
K_REST_NEG = 0xBD4CCCCC
K_RUN_EVENT = 0x3F199999    # 0.6
SPEED_OFFLINE, SPEED_NET, SPEED_CAP = 0x3F5CA86D, 0x3F400000, 0x3F999999
WALK_EVENT, RUN_EVENT = 1, 4


def stick_magnitude(scale, lx, ly):
    """0x1b41c0-0x1b420c: s = scale * sqrt(lx*lx + ly*ly), capped at scale."""
    s = C.mul(scale, C.sqrt(C.add(C.mul(lx, lx), C.mul(ly, ly))))
    return scale if C.lt(scale, s) else s


def speed_scale(network, record_mul=ONE, run_speed=ONE):
    """0x1b40d8-0x1b4188 without the level-name, PvP-mode-B and Drowsy branches."""
    base = SPEED_NET if network else SPEED_OFFLINE
    s = C.mul(C.mul(base, record_mul), run_speed)
    return SPEED_CAP if C.lt(SPEED_CAP, s) else s


def playback_rate(s):
    """Rate handed to Player_animStep for the locomotion layers."""
    if C.lt(s, K_KNEE1):
        return C.mul(s, K_SLOPE1)
    if C.lt(s, K_KNEE2):
        return C.add(C.mul(C.mul(C.sub(s, K_KNEE1), K_SLOPE2A), K_SLOPE2B), ONE)
    return C.add(C.mul(C.mul(C.sub(s, K_KNEE2), K_SLOPE3A), K_SLOPE3B), K_BASE3)


def _truncate(value, bits):
    """Exact value truncated toward zero to `bits` significant bits; sign kept for 0."""
    sign, x = value
    if x == 0:
        return sign, Fraction(0)
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if Fraction(2) ** e > x:
        e -= 1
    scale = Fraction(2) ** (bits - 1 - e)
    return sign, Fraction(int(x * scale)) / scale


def _widen(raw):
    v = struct.unpack('<f', struct.pack('<I', raw))[0]
    return (1 if raw >> 31 else 0), abs(Fraction(v))


def _double(raw64):
    v = struct.unpack('<d', struct.pack('<Q', raw64))[0]
    return (1 if raw64 >> 63 else 0), abs(Fraction(v))


def _dsub(a, b):
    exact = (-a[1] if a[0] else a[1]) - (-b[1] if b[0] else b[1])
    sign = 1 if exact < 0 else 0
    return _truncate((sign, abs(exact)), 53)


def _dmul(a, b):
    return _truncate((a[0] ^ b[0], a[1] * b[1]), 53)


def _narrow(a):
    sign, x = _truncate(a, 24)
    if x != 0 and x < Fraction(1, 2 ** 126):
        x = Fraction(0)
    magnitude = struct.unpack('<I', struct.pack('<f', float(x)))[0]
    return magnitude | (sign << 31)


D_045_BITS, D_07_BITS, D_3_BITS = 0x3FDCCCCCCCCCCCCC, 0x3FE6666666666666, 0x4008000000000000


def run_weight(blend, s, knee_bits):
    """narrow(mul(mul(widen(blend), sub(widen(s), knee)), 3.0)), 0x1b4994-0x1b4a30."""
    return _narrow(_dmul(_dmul(_widen(blend), _dsub(_widen(s), _double(knee_bits))),
                         _double(D_3_BITS)))


def locomotion_step(blend, previous, s, step_bits):
    """One mode-0 call.  blend = +0x46c, previous = +0x468, s = stick magnitude,
    step_bits = what Player_animStep returns.  Returns a dict of the stores and the
    rate passed to Player_animStep."""
    rate = playback_rate(s)
    reset_idle = False
    if C.lt(K_MOVING, rate):
        blend = C.add(blend, K_RAMP)
        if C.lt(ONE, blend):
            blend, reset_idle = ONE, True
    else:
        blend = C.sub(blend, K_RAMP)
        if C.lt(blend, ZERO):
            blend = ZERO
    if C.lt(rate, K_MOVING) and C.lt(blend, K_REST):
        passed, event = ONE, 0
    else:
        passed = rate
        low = step_bits & 0xFF
        low = low - 0x100 if low & 0x80 else low
        event = low & (RUN_EVENT if C.le(K_RUN_EVENT, s) else WALK_EVENT)
    held = s
    if C.lt(C.sub(previous, s), K_REST_NEG):
        held = C.add(previous, K_REST)
    return {'rate': passed, 'blend': blend, 'reset_idle': reset_idle, 'previous': held,
            'walk': blend, 'run1': run_weight(blend, held, D_045_BITS),
            'run2': run_weight(blend, held, D_07_BITS), 'event': event & 0xFFFFFFFF}


# ---- Player_animStep 0x1b9520 ----------------------------------------------------------
K_DT = 0x3C888888           # 1/60


def anim_step_speed(speed, slow_byte, drowsy=None):
    """Speed handed to anim_advance: Drowsy fraction, then the slow amount 1..60."""
    if drowsy is not None:
        speed = C.mul(speed, drowsy)
    if 1 <= slow_byte <= 60:
        signed = slow_byte - 0x100 if slow_byte & 0x80 else slow_byte
        speed = C.mul(C.mul(speed, C.from_int(60 - signed)), K_DT)
    return speed


def root_to_world(facing, rx, ry):
    """0x1b95f0-0x1b9644: the local root delta turned into world axes (+0xbc, +0xc0)."""
    c = C.cos16(facing - 0x4000)
    s = C.sin16(facing - 0x4000)
    nx = C.neg(rx)
    y = C.sub(C.mul(nx, s), C.mul(ry, c))
    x = C.add(C.mul(nx, c), C.mul(ry, s))
    return x, y


# ---- Player_processDamage clip choice (0x1b2ec0-0x1b3184, 0x1b3440-0x1b34fc) -----------
REACTION_ROW = 0x7C
ROW_STRIDE = 0x68
FLAGS_KNOCKDOWN, FLAGS_REACTION, FLAGS_DEATH = 0x80A, 0x0A, 0x206
BLEND_HIT = 0x3DCCCCCC      # 0.1 in and out
BLEND_DEATH = 0x3F000000    # 0.5
FADE_RATE = 0xBDAAAAAA      # -1/12 per tick on the old top track when 5+ tracks run


def knockdown_name(weapon_class, rel):
    """rel = s16(+0x2e0 - facing).  Prefix by class, suffix by the relative hit angle."""
    prefix = 'knockdown2_' if weapon_class in (2, 3) else 'knockdown1_'
    if rel <= -0x6000 or rel >= 0x6000:
        suffix = 'a'
    elif -0x5FFF <= rel <= -0x2000:
        suffix = 'c'
    elif -0x1FFF <= rel <= 0x2000:
        suffix = 'b'
    else:
        suffix = 'd'
    return prefix + suffix + '.anm'


def reaction_offset(weapon_class):
    return weapon_class * ROW_STRIDE + REACTION_ROW


def death_offset(model, weapon_class):
    """Definition-header clip of the death animation."""
    if weapon_class == 2 and model not in (2, 3, 6, 7):
        return 0x14
    return 0x0C


# ---- Player_run state 1 timing (0x1a9678-0x1aafe0) -------------------------------------
K_HIT = 0x418028F5          # 16.02
K_WINDOW, K_WINDOW_DUAL = 0x41B028F5, 0x418CED91       # 22.02, 17.616
K_TRIM_CAP = 0x418B3332
K_STICK_END, K_STICK_FRAMES = 0x3F4CCCCC, 0x421D3332   # 0.8, 39.3
K_SWING_LIFE = 0x3FCCCCCC   # 1.6 s
K_LUNGE, K_LUNGE_HEAVY = 0x3EDDB22D, 0x3F1126E9
F_60 = 0x42700000
COMBO_STEPS = {2: 4, 1: 7, 3: 9, 5: 2, 7: 7}


def swing_speed(haste=ZERO, status2=False, status4=False):
    if status2:
        haste = C.add(haste, 0x3E800000)
    if status4:
        haste = C.add(haste, K_RAMP)
    return C.add(ONE, haste), haste


def hit_frame(speed, network=False):
    """Frames after the swing start on which Player_meleeHit runs (offline)."""
    return 1 if network else C.to_int(C.div(K_HIT, speed))


def combo_window(weapon_class, haste):
    trim = C.mul(C.mul(haste, F_60), C.HALF)
    if C.lt(K_TRIM_CAP, trim):
        trim = K_TRIM_CAP
    return C.sub(K_WINDOW_DUAL if weapon_class == 7 else K_WINDOW, trim)


def first_combo_frame(weapon_class, haste, speed):
    """Smallest elapsed frame count at which a fresh attack press starts the next swing."""
    limit = C.div(combo_window(weapon_class, haste), speed)
    n = 0
    while not C.lt(limit, C.from_int(n)):
        n += 1
    return n


def swing_end_frame(life=None):
    """Elapsed frames at which the swing returns to neutral without input; life is
    +0x470 (1.6 s for a melee swing, 0x3f5b645a for the heavy attack)."""
    limit = C.mul(K_SWING_LIFE if life is None else life, F_60)
    n = 0
    while not C.le(limit, C.from_int(n)):
        n += 1
    return n


def stick_end_frame():
    n = 0
    while C.lt(C.from_int(n), K_STICK_FRAMES):
        n += 1
    return n


def move_mode(elapsed, heavy=False):
    limit = C.mul(K_LUNGE_HEAVY if heavy else K_LUNGE, F_60)
    return 4 if C.le(C.from_int(elapsed), limit) else 3
