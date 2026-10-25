"""Bounded model of the original all-dead check and death task (US v2.00).

Addresses and branch evidence are recorded in docs/spec/player-death-flow.md.
This models the control hand-off, not animation, save parsing or presentation.
"""


def check_all_dead(state):
    """Return the state after one 0x1e7438 call, including ordered call-outs."""
    s = dict(state)
    s['timers'] = list(state['timers'])
    s['calls'] = []
    if (not s['cutscene'] and s['loaded'] and not s['pvp_b']
            and s['alive'] == 0 and s['players'] > 0):
        s['calls'].append(('game_isFrozen',))
        if not s['frozen']:
            allowed = True
            if s['network']:
                s['calls'].append(('net_fewerThanTwoActive',))
                allowed = not s['fewer_two']
            if allowed:
                s['menu_lockout'] = 60
                if s['wipe_timer'] > 0:
                    s['wipe_timer'] -= 1
                    if s['wipe_timer'] == 0:
                        s['calls'] += [('net_closeLocalMenus', 0),
                                       ('deathTask_schedule', 0)]
    if not s['cutscene'] and not s['paused'] and s['players'] > 0 \
            and s['alive'] != s['players']:
        for slot in range(s['players']):
            if s['hp'][slot] <= 0 and s['timers'][slot] > 0:
                s['timers'][slot] -= 1
                if s['timers'][slot] == 0 and s['pvp_b']:
                    s['calls'].append(('arena_respawnPlayer', slot))
    return s


def death_task(state):
    """Return one 0x1e75e8 task step for the tested control branches."""
    s = dict(state)
    s['hp'] = list(state['hp'])
    s['calls'] = []
    if s['phase'] == 0:
        if s['alternate']:
            s['phase'] = 10
        else:
            s['calls'].append(('hud_stepFade', 4))
            if s['fade'] == 0x80:
                s['phase'] = 1
    elif s['phase'] == 1:
        s['game_flag'] = 1
        if s['force_network']:
            s['network'] = 1
        else:
            s['calls'].append(('save_findAct',))
            if s['act'] == -1:
                s['pending'] = s['level']
                s['request'] = 0xfd
                s['hp'] = list(s['max_hp'])
                s['calls'].append(('task_remove',))
            else:
                s['calls'].append(('save_reload',))
                s['phase'] = 2
        if s['force_network']:
            s['phase'] = 2
    elif s['phase'] == 2:
        if not s['pending']:
            s['calls'].append(('level_getQualifiedName',))
            s['calls'].append(('level_currentName',))
            s['calls'].append(('libc_strcmp',))
            if s['names_match']:
                s['calls'].append(('task_remove',))
    elif s['phase'] == 10 and s['alive']:
        s['calls'].append(('task_remove',))
    return s
