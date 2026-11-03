"""Independent, bounded PushTrigger lifecycle rules; no game input required.

Uses the existing handle/grid model rather than a separate consumed-object list.
This is not a general save writer or a Creature departure model.
"""
import ref_objects as O
from ref_core import Iterator


VT_PUSH = 0x511450


def construct(world, address, position, angle, properties):
    supported = {b'name', b'action', b'once', b'offonly'}
    if any(bytes(p).split(b'=', 1)[0] not in supported for p in properties or []):
        raise O.ObjectError('unsupported property in bounded PushTrigger lifecycle')
    obj = world.construct(address, position, props=properties)
    obj.flags |= 0x10000B
    obj.angle = angle & 0xFFFF
    obj.vtable = VT_PUSH
    obj.class_name = b'PushTrigger'
    return obj


def interact(world, obj, context, run_script, on_destroy):
    """0x1ecc70 and 0x14dcc8: actions precede immediate virtual destruction.

    context carries the inherited active player and selected object. Script bodies
    are supplied by the caller. No action means no once destruction.
    """
    if O.props_find(obj.props, b'action') is None:
        return
    invert = bool(O.props_int(obj.props, b'offOnly'))
    index = 0
    while True:
        action = O.props_find(obj.props, b'action', index)
        if action is None:
            break
        context['selected'] = obj.addr
        run_script((b'not' if invert else b'') + action, context)
        context['selected'] = 0
        index += 1
    if O.props_int(obj.props, b'once'):
        on_destroy(obj, 3)
        world.destroy(obj, 3)


def members(world):
    """Enumerate actual handle lists in the original world-walker order."""
    result = []
    world.for_each_grid_object(lambda obj: result.append(obj.addr))
    return result


def records(world, filtered_classes=()):
    """Bounded unthinned records: no transient flag, no save-filter classes.

    Fixtures use PushTrigger's empty state and abundant output capacity. Overflow,
    thinning and class-specific state are deliberately outside this model.
    """
    result = []
    # Unlike world_forEachGridObject, the writer visits the off-grid list LAST.
    for head in world.grid + world.grid_b + [world.off_grid]:
        if head.next is None:
            continue
        # Saving is independent of the world's query exclusion mask.
        it = Iterator(head, 0)
        while not it.done:
            obj = it.current
            if not (obj.flags & 0x4000 or obj.class_name in filtered_classes):
                if obj.class_name != b'PushTrigger':
                    it.end()
                    raise O.ObjectError('unsupported saved class; Creature departure is unknown')
                result.append((obj.class_name, O.s16(obj.angle), tuple(obj.pos),
                               tuple(bytes(p) for p in (obj.props or []))))
            it.advance()
        it.end()
    return result


def reentry_records(saved, initial, filtered_classes=()):
    """Saved first, then filtered source; the PushTrigger factory passes angle zero."""
    ordered = list(saved) + [r for r in initial if r[0] in filtered_classes]
    return [(name, 0 if name == b'PushTrigger' else angle, pos, props)
            for name, angle, pos, props in ordered]
