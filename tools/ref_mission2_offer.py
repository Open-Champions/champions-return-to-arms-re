"""Authored bounded offer/menu model; no private inputs or full-load claim."""


def node(first, second, active=False):
    """Hub priority at 0x22ef7c on zero later missions/variables."""
    if active:
        return 0
    if not first & 1:
        return 1
    if not first & 2:
        return 3
    if not second & 1:
        return 7
    return 8 if not second & 2 else 9


def menu_tick(s, button, available, destination, fade=0):
    """0x2316fc, row-1 story control; navigation/presentation outside model."""
    phase = s['phase']
    if phase == 0:
        s.update(phase=1, row=1 if available else 0, col=0, paused=1, counter=0)
    elif phase == 1:
        s['counter'] = min(127, s['counter'] + 8)
        if s['counter'] == 127:
            s['phase'] = 2
    elif phase == 2:
        s['mark'] += 8
        if button & 0x40 and available:
            s.update(phase=5, c0=1)
    elif phase == 5:
        s['phase'] = 6
    elif phase == 6:
        if fade >= 128:
            s['phase'] = 7
        else:
            s['c0'] += 1
    elif phase == 7:
        s['phase'] = 8
    elif phase == 8:
        s.update(pending=destination, orient=255, c0=0)
