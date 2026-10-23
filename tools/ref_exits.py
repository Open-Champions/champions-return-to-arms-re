"""Small, independently written reference rules for SLUS-20973 v2.00 exits.

Coordinates are horizontal x/y.  This is a state model, not a level loader.
Evidence and unsupported paths are in docs/exits-walkin.md.
"""


def contains(rect, point):
    x0, y0, x1, y1 = rect
    x, y = point
    return x0 <= x <= x1 and y0 <= y <= y1


def trigger_tick(state, rect, players, recall_countdown=0, params=None,
                 script_result=1):
    """Return (new state, ordered actions) for one Trigger_run simulation tick.

    players is a slot-ordered list of None or horizontal coordinates.  A nonzero
    recall countdown suppresses a found player's transition, before edge testing.
    """
    state = dict(state)
    actions = []
    if state['delay'] != 0:
        state['delay'] -= 1
        return state, actions
    state['slot'] = -1
    found = next((i for i, p in enumerate(players)
                  if p is not None and contains(rect, p)), None)
    if found is not None:
        if recall_countdown:
            return state, actions
        state['slot'] = found
    inside = int(found is not None)
    if inside == state['inside']:
        return state, actions
    selected = inside
    if params is not None:
        if params.get('onOnly', 0):
            selected = 1
        if params.get('offOnly', 0):
            selected = 0
        actions.append(('action', selected))
    actions.append(('script', 'exit' if selected else 'notexit',
                    (found if found is not None else 0) if selected else None))
    state['inside'] = inside
    if params is None or not (params.get('onOnly', 0) or params.get('offOnly', 0)):
        return state, actions
    timeout = params.get('timeout', 0)
    if timeout:
        if state['delay'] != -1:
            state['delay'] = timeout * 4
        state['inside'] = 0
    elif params.get('needScriptHit', 0) and not script_result:
        state['inside'] = 0
    else:
        state['delay'] = -1
        state['inside'] = 0
    return state, actions


def gate_prompt(found, dest_count, menu_open=False, predicate=True,
                other_players_near=True, hurt=False):
    """Ordinary Portal prompt outcome: (new found byte, message key, usable)."""
    if hurt or menu_open or not predicate:
        return found, None, False
    found = 1
    if dest_count == 1:
        return found, 'JumpGateVirgin', False
    if not other_players_near:
        return found, 'JumpGateNeedPlayers', False
    return found, 'JumpGate', True


def push_prompt(keys, values, message=None, lock_message=None):
    """Offline PushTrigger slot-13 result: (message key or None, usable)."""
    for key in keys:
        if not values[key]:
            return lock_message, False
    return message, True


def nearest_interactable(player, objects):
    """Player_interact's ordered box-query result: first minimum of flagged objects."""
    best, best_distance = None, 10000000.0
    for index, (position, flags) in enumerate(objects):
        if not flags & 0x100000:
            continue
        distance = sum((a - b) ** 2 for a, b in zip(position, player))
        if distance < best_distance:
            best, best_distance = index, distance
    return best


def use_pressed(prompt_result, pad_pressed, slot_use_mask, display_only=False):
    """Player_interact slot-14 dispatch after a nonempty slot-13 prompt."""
    if display_only:
        return False
    if prompt_result == 1:
        return bool(pad_pressed & slot_use_mask)
    if prompt_result == 2:
        return bool(pad_pressed & 0x10)
    return False


def push_use(has_action, shop, blocked_shop, off_only, once):
    """PushTrigger_interact's ordered action/delete effects."""
    if not has_action or (shop and blocked_shop):
        return []
    result = [('action', int(not off_only))]
    if once:
        result.append(('delete', 3))
    return result


def gate_use(mutex, network_mode):
    """JumpGate_interact's branch through the menu mutex and network byte."""
    return not mutex or bool(network_mode)


def gate_travel_tick(counter, fixed_destination, selected_destination):
    """State 5: counter advances through 180, then requests the destination."""
    if counter < 181:
        return counter + 1, None, None, 5
    return counter, fixed_destination or selected_destination, 0xff, 6


def gate_arrival(travel, fixed_destination, player_count, position, seed,
                 initial_rank, find_spot):
    """JumpGate_ctor arrival writes when free-spot search is supplied by caller.

    Returns rank, slot positions, facings, next seed, and search count.  The
    constructor uses the same search contract as ref_objects.find_free_spot;
    the callback keeps this narrow model independent of terrain and disc data.
    """
    if not travel or fixed_destination:
        return initial_rank, [], [], seed, 0
    positions, facings = [], []
    for _slot in range(player_count):
        positions.append(find_spot(position, 36, 24, True))
        seed = (seed * 0x19660d + 0x3c6ef35f) & 0xffffffff
        facings.append(seed >> 16)
    return 3, positions, facings, seed, player_count
