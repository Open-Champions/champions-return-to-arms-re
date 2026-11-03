"""Authored, bounded travel models; no game data or successful-load model.

Addresses: command/gate 0x143dd0/0x143d04, prompt 0x27d7a0,
menu 0x27dd74, request parsing 0x320edc. Input text is supplied at runtime.
"""


def command(network, active, cooldown, alive, post_action):
    """Return (allowed, resulting cooldown) for the command's native gate."""
    if not post_action and network and active != -1:
        if cooldown and alive >= 2:
            return False, cooldown
        return True, 600
    return True, cooldown


def prompt(predicate, hurt, busy, discovered, destinations, current,
           other_distances_squared):
    """Supported ordinary portal prompt, including discovery before distance refusal.

    The fixture supplies ordinary route names and a list with no special entries;
    destination insertion's special-entry removal is outside this small model.
    """
    destinations = list(destinations)
    if hurt or busy or not predicate:
        return 0, discovered, destinations
    if not discovered:
        discovered = 1
        if current not in destinations:
            destinations.append(current)
    allowed = len(destinations) != 1 and all(
        distance <= 9216 for distance in other_distances_squared)
    return int(allowed), discovered, destinations


def travel_counter(counter, pending, destination, orientation):
    """Menu state 5: test before increment; 181 is the first accepting input."""
    if counter > 180:
        return 6, counter, destination, 255
    return 5, counter + 1, pending, orientation


def menu_choice(cancel, confirm, current_selected, local_pause_requested=False):
    """State 2 without navigation; local pause request precedes all button input."""
    if local_pause_requested:
        return 2, 0
    if cancel:
        return 3, 0
    if confirm and not current_selected:
        return 3, 1
    return 2, 0


def request_names(pending, current, current_sub, orientation):
    """State just before the level loader call, not completion of loading."""
    previous = current + ("_" + current_sub if current_sub else "")
    level, separator, sub = pending.partition("_")
    return "", level, sub if separator else "", previous, 254, orientation
