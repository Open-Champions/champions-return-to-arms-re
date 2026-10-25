#!/usr/bin/env python3
"""Small, data-free model of the fresh hub mission-menu route.

The caller supplies the mission-table destination read from its own executable.
This models only the row-zero story choice, not the full campaign menu.
"""

FADE_DONE = 128


def dialog_start_node(conditions):
    """dialog_onMsg 0x22efac: first true condition, otherwise node zero."""
    for index, value in enumerate(conditions):
        if value:
            return index
    return 0


def fresh_hub_state():
    """Mission zero is complete; mission one has not been offered yet."""
    return {'mission0': 3, 'mission1': 0, 'quests': [], 'entrance': '',
            'current_act': 0, 'started_mission1': 0}


def offer_first_mission(state, title, description):
    """Both first-offer dialog actions call setMissionAvailable(1,1), addQuest."""
    state['mission1'] |= 1
    if all(row[0] != title for row in state['quests']) and len(state['quests']) < 8:
        state['quests'].append((title, description))
    return state


def portal_request(state, warning=False):
    """Hub PushTrigger -> warnDetect; fresh state takes the direct menu arm."""
    if warning:
        return 'warning_deferred'
    state['entrance'] = 'goodstart'
    return 'mission_menu'


def new_menu():
    return {'phase': 0, 'row': 0, 'col': 0, 'counter': 0,
            'mark': 0, 'paused': 0, 'pending': '', 'orient': 0, 'c0': 0}


def menu_tick(state, button, mission1_available, story_destination, fade=0):
    """missionMenu_run 0x2316fc, fresh row-zero story path only."""
    phase = state['phase']
    if phase == 0:
        state.update(row=0, col=0, paused=1, counter=0, phase=1)
    elif phase == 1:
        state['counter'] = min(127, state['counter'] + 8)
        if state['counter'] == 127:
            state['phase'] = 2
    elif phase == 2:
        state['mark'] += 8
        if button & 0x40 and mission1_available:
            state.update(phase=5, c0=1)
    elif phase == 5:
        state['phase'] = 6
    elif phase == 6:
        if fade >= FADE_DONE:
            state['phase'] = 7
        else:
            state['c0'] += 1
    elif phase == 7:
        state['phase'] = 8
    elif phase == 8:
        state.update(pending=story_destination, orient=0xff, c0=0)
    return state


def same_act_on_arrival(state, destination_act):
    """mainloop_loadRequestedWorld 0x320f8c: clear only on act change."""
    if destination_act != state['current_act']:
        state.update(current_act=destination_act, quests=[], started_mission1=0)
    return state
