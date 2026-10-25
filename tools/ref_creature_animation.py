"""Rendered-creature integration contracts, SLUS-20973 v2.00.

See docs/spec/rendered-creature-animation.md. The existing ref_anim is authoritative
for raw32 clocks, root motion, blend and quantized hierarchy. This supplement models
resource selection, draw transform and exact-rational geometric skinning (NOT the
VU1 floating-point instruction schedule or GS rasterization).
"""
from fractions import Fraction
import ref_core as C
import ref_anim as A


def class_resource(memory, creature, index):
    """0x118378 and 0x3c2738: index 1=model, 2=texture, >=3 class-specific.
    Class definition includes lump/generation at indices 0's two words."""
    definition = memory.load(creature + 0x24, 4)
    return memory.load(definition + index * 8 + 4, 4)


def virtual_target(memory, obj, slot):
    """Member dispatch: e.g. 0x2a9368-0x2a937c. Return (function, adjusted_this).
    Entries are 8 bytes, with signed s16 this adjustment and function at +4."""
    table = memory.load(obj + 0x48, 4)
    entry = table + 8 * slot
    return memory.load(entry + 4, 4), (obj + C.s16(memory.load(entry, 2))) & 0xFFFFFFFF


def role_lump(memory, obj, is_npc):
    """0x16096c-0x160990: caller supplies result of RTTI NPC ancestry test.
    NPC: embedded lump-name string at +0x3c8, not the pointer stored there.
    Others: first word of the object's class definition."""
    return obj + 0x3C8 if is_npc else memory.load(memory.load(obj + 0x24, 4), 4)


def find_role_anim(lump, role, get_property, find_resource):
    """Selection tail 0x160994-0x160a68. Byte strings, None means absent property.
    Keep repeated property callbacks and unconditional override return, even null.
    Short ASCII strings fitting the original 0xa0 scratch buffers are the domain."""
    def bounded(value):
        if len(value) >= 160 or any(c == 0 or c >= 128 for c in value):
            raise ValueError('role lookup requires short terminated ASCII inputs')
        return value

    key = bounded(role + b'name')
    if get_property(key) is not None:
        return find_resource(lump, bounded(get_property(key) + b'.anm'))
    if get_property(b'name') is not None:
        found = find_resource(lump, bounded(get_property(b'name') + b'_' + role + b'.anm'))
        if found:
            return found
    return find_resource(lump, bounded(role + b'.anm'))


def creature_draw_matrix(memory, creature):
    """0x10b090-0x10b12c, ordinary Creature_draw object transform, raw32 mat34.
    Drawing uses +0x3c for Z and the optional facing offset +0xe0 in XY."""
    u32 = lambda off: memory.load(creature + off, 4)
    facing = C.s16(memory.load(creature + 0x38, 2))
    x, y, z = u32(0x10), u32(0x14), u32(0x3C)
    offset = u32(0xE0)
    if not C.eq(offset, 0):
        x = C.add(x, C.mul(C.cos16(facing), offset))
        y = C.add(y, C.mul(C.sin16(facing), offset))
    return C.mat34_set_pos_rot_z_scale(u32(0xDC), (x,y,z), C.s16(facing + 0x4000))


def skin_matrix(pose_rows, influences):
    """Geometric contract from VU1 entries 0x3a/0x0c/0x42/0x44, executable
    packet 0x3e5ed0; weight decoder 0x3e7e38. Exact rational, not raw32 VU result.
    Inputs: pose_rows[joint][row][column], signed s16; (joint, byte weight).
    No inverse-bind operation, parent composition or weight renormalization here.
    A rigid run is represented as weight 255. Native safety validation is explicit."""
    if not 1 <= len(influences) <= 4 or sum(w for _,w in influences) != 255:
        raise ValueError('one to four influences summing to 255 required')
    if any(not 0 <= j < len(pose_rows) or not 0 <= w <= 255 for j,w in influences):
        raise ValueError('invalid joint or weight')
    return [[sum(Fraction(w * pose_rows[j][r][c], 255 * (64 if c == 3 else 4096))
                 for j,w in influences) for c in range(4)] for r in range(3)]


def skin_point(pose_rows, influences, stored_position):
    """Model position is signed integer /16; returns exact posed model-space point."""
    matrix = skin_matrix(pose_rows, influences)
    p = [Fraction(v,16) for v in stored_position]
    return tuple(sum(matrix[r][c]*p[c] for c in range(3)) + matrix[r][3] for r in range(3))


def godot_point(point, units=Fraction(1,1)):
    """Authored adapter choice, not an original game function: (x,y,z)->(x,z,-y).
    Apply to positions, normals, translations and root motion consistently.
    Units=1 preserves original world units; other unit scales are caller policy."""
    return (point[0]*units, point[2]*units, -point[1]*units)


def draw_pose(system, state):
    """Existing 0x16f880 contract, including fallback/default and draw stamp.
    Returned matrices are already bind-corrected model-space skin matrices.
    Do not compose the hierarchy or inverse bind again in a renderer.
    Kept as a named handoff; it does not advance simulation or draw_frame."""
    return A.anim_emit_pose(system, state)


def set_class_events(model, creature, index, times, masks):
    """0x118378-0x1183cc. Four shared clip event slots; byte BEFORE time.
    Re-read class and clip for every slot, preserving callback/alias read order.
    times are raw32 seconds, masks truncate to u8; no owned clip clone."""
    if len(times) != 4 or len(masks) != 4:
        raise ValueError('four event slots required')
    for i in range(4):
        clip = class_resource(model.mem, creature, index)
        model.w8(clip + 0x18 + 8*i, masks[i])
        model.w32(clip + 0x14 + 8*i, times[i])
