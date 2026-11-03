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


# missionMenu_run 0x2316fc reads missions 1..12. Mission 0 is not a row.
MENU_MISSIONS = 12
BTN_CROSS = 0x40
BTN_UP = 0x1000
BTN_DOWN = 0x4000


def opening_row(available):
    """State 0 selects the highest available mission in 1..12, else row 0."""
    rows = [mission - 1 for mission in available if 1 <= mission <= MENU_MISSIONS]
    return max(rows) if rows else 0


def story_level(story, evil_name, evil):
    """State 8, column 0. Evil uses +0x0c only when that pointer is set."""
    if evil and evil_name:
        return evil_name
    return story or ''


def story_column_open(row, available):
    """0x231078. Row 0 accepts even when mission 1's byte is clear.
    Every later row accepts only when that mission is available."""
    if row == 0:
        return True
    return (row + 1) in available


def hub_name(evil, decision, mission1, difficulty):
    """game_getHubName 0x1ec300. hub2 needs this difficulty's evil bit, its
    decision bit, and mission 1's completion bit."""
    bit = 1 << (difficulty & 31)
    if (evil & bit) and (decision & bit) and (mission1 & 2):
        return 'hub2'
    return 'hub'


def find_act(name, current, acts):
    """save_findAct 0x217d30. A row name is a case-sensitive prefix.
    The current act is searched first. A current act outside 0..n-1 is skipped."""
    order = []
    if isinstance(current, int) and 0 <= current < len(acts):
        order.append(current)
    order.extend(range(len(acts)))
    for act in order:
        for prefix in acts[act]:
            if prefix and name.startswith(prefix):
                return act
    return -1


def act_changed(name, current, acts):
    """save_actChanged 0x217f70. A different matched act is stored."""
    found = find_act(name, current, acts)
    if found >= 0 and found != current:
        return 1, found
    return 0, current


def campaign_tick(state, button, available, rows, evil, fade=0):
    """One missionMenu_run tick for the story column and vertical move.

    `rows` has one (story, evil-name) pair per menu row. `available` is the
    set of mission numbers read on this tick. Medal and bonus columns are
    outside this model; `menu_tick` remains the fresh row-zero path.
    """
    button &= 0xFFFF
    phase = state['phase']
    if phase == 0:
        state.update(row=opening_row(available), col=0, paused=1, counter=0, phase=1)
    elif phase == 1:
        state['counter'] = min(127, state['counter'] + 8)
        if state['counter'] == 127:
            state['phase'] = 2
    elif phase == 2:
        state['mark'] += 8
        row = state['row']
        mission = row + 1
        if button & BTN_CROSS and story_column_open(row, available):
            state.update(phase=5, c0=1)
        elif button & BTN_UP and row > 0:
            state['row'] = row - 1
        elif button & BTN_DOWN and row < MENU_MISSIONS - 1 and (mission + 1) in available:
            state['row'] = row + 1
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
        story, evil_name = rows[state['row']]
        state.update(pending=story_level(story, evil_name, evil), orient=0xff, c0=0)
    return state
