"""Bounded state model for chest and world-item pickup probes.

These transitions cover only the states constructed by difftest_pickups.py.
They are not a model of animation, property parsing, physics, or the world grid.
"""


def chest_interact(opened, gold):
    if not opened:
        return {'opened': 1, 'gold': gold, 'hide': 0, 'loot_calls': 1,
                'floater_calls': 0, 'interactable': bool(gold)}
    return {'opened': opened, 'gold': 0, 'hide': 1, 'loot_calls': 0,
            'floater_calls': 1, 'interactable': True}


def chest_finish(animation_done):
    return (2, 1, 1) if animation_done else (0, 0, 0)


def can_pickup(bag_count, load, weight, limit):
    return bag_count < 63 and load + weight <= limit


def item_interact(shared, counts, loads, weight, limits, chosen_slot):
    slots = range(len(counts)) if shared else (chosen_slot,)
    granted = tuple(slot for slot in slots
                    if can_pickup(counts[slot], loads[slot], weight, limits[slot]))
    return granted, bool(granted)
