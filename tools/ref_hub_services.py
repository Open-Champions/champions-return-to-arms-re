"""Authored model of the hub and hub2 between-mission services (SLUS-20973 v2.00).

Contract: docs/hub-services.md.  Original-function comparison:
tools/difftest_hub_services.py.  Synthetic tests: tools/test_ref_hub_services.py.

Everything is keyed by script public offset and dialog node index.  No script
name, variable name, text key or item name appears here; the difftest resolves
the private names from the owner's disc at run time and never prints them.

State used by the predicates:
  raw[n]      mission byte n (0..12) of player 0 at the current difficulty;
              bit 0 = available (A), bit 1 = complete (C)
  started[n]  the per-mission "started" quest variable (n = 1..12, signed byte)
  intro       hub2's intro quest variable (signed byte)
  demo        the demo quest variable read by the hub's demo nodes
"""

HUB, HUB2 = 'hub', 'hub2'
MISSIONS = range(1, 13)

# Predicate kinds.  'active' = any(A && !C && started != 0); 'offer' = !A(n);
# 'pending' = A(n) && !C(n) && started[n] == 0; 'demo' = 0 in this executable
# (demoRunning 0x141764 returns a constant 0); 'intro' = !A(2) && intro == 0;
# 'done' = C(n); 'notdone' = !C(n).
ACTIVE, OFFER, PENDING, DEMO, INTRO, DONE, NOTDONE = (
    'active', 'offer', 'pending', 'demo', 'intro', 'done', 'notdone')

# Choice roles, assigned by the difftest from structure only: MORE = the text key
# whose choices all continue to another node; SHOP = the key whose every action
# requests the store; END = the remaining key.
MORE, END, SHOP = 'more', 'end', 'shop'

# Action effects.  avail = mission whose bit 0 is set; quest = one addQuest pair;
# store = changeSwoop(0) + activateStore (deferred open while the dialog is open);
# var = 'demo' / 'intro' quest variable set to 1.
def E(avail=None, quest=False, store=False, var=None):
    return {'avail': avail, 'quest': quest, 'store': store, 'var': var}


# Each node: (condition public offset, kind, mission, choices); each choice:
# (role, condition offset or None, condition kind, condition mission, action
# offset or None, next node or -1).
def _status(cond, kind, n):
    return (cond, kind, n, ((SHOP, None, None, 0, 0x1DF8, -1), (END, None, None, 0, None, -1)))


def _status2(cond, kind, n):
    return (cond, kind, n, ((SHOP, None, None, 0, 0x41B4, -1), (END, None, None, 0, None, -1)))


def _offer(cond, n, end_action, shop_action):
    return (cond, OFFER, n, ((END, None, None, 0, end_action, -1), (SHOP, None, None, 0, shop_action, -1)))


def _more(cond, kind, n, nxt, action=None):
    return (cond, kind, n, ((MORE, None, None, 0, action, nxt),))


NODES = {
    HUB: (
        (0x3F0, ACTIVE, 0, ((SHOP, None, None, 0, 0x1DF8, -1), (END, None, None, 0, None, -1))),
        _more(0x11C, OFFER, 1, 2),
        _more(0x11C, OFFER, 1, 3),
        (0x198, PENDING, 1, ((END, None, None, 0, 0x1E68, -1), (SHOP, None, None, 0, 0x1EE8, -1))),
        _more(0x498, DEMO, 0, 5),
        (0x498, DEMO, 0, ((END, None, None, 0, 0x598, -1), (SHOP, None, None, 0, 0x1FC0, -1))),
        _status(0x680, DEMO, 0),
        _offer(0x734, 2, 0x7B0, 0x2064),
        _status(0x898, PENDING, 2),
        _more(0x9A0, OFFER, 3, 10),
        _offer(0x9A0, 3, 0xA1C, 0x2108),
        _status(0xB04, PENDING, 3),
        _offer(0xC0C, 4, 0x21AC, 0x222C),
        _status(0xD70, PENDING, 4),
        _offer(0xE78, 5, 0xEF4, 0x2304),
        _status(0xFDC, PENDING, 5),
        _more(0x10E4, OFFER, 6, 17),
        _offer(0x10E4, 6, 0x23A8, 0x2428),
        _status(0x1248, PENDING, 6),
        _offer(0x1350, 7, 0x13CC, 0x2500),
        _status(0x14B4, PENDING, 7),
        _status(0x15BC, OFFER, 8),
        _status(0x1638, OFFER, 9),
        _more(0x16B4, OFFER, 10, 24),
        _offer(0x16B4, 10, 0x25A4, 0x2624),
        _status(0x1818, PENDING, 10),
        _more(0x1920, OFFER, 11, 27, action=0x26FC),
        _status(0x1A84, PENDING, 11),
        _more(0x1B8C, OFFER, 12, 29),
        _offer(0x1B8C, 12, 0x1C08, 0x277C),
        _status(0x1CF0, PENDING, 12),
    ),
    HUB2: (
        (0x2AB0, ACTIVE, 0, ((SHOP, None, None, 0, 0x41B4, -1), (END, None, None, 0, None, -1))),
        (0x28B4, INTRO, 2, ((MORE, 0x2978, NOTDONE, 1, 0x29BC, 2), (MORE, 0x2A08, DONE, 1, 0x29BC, 3))),
        _status2(0x28B4, INTRO, 2),
        _offer(0x2AF0, 2, 0x2B6C, 0x4224),
        _status2(0x2C54, PENDING, 2),
        _offer(0x2D5C, 3, 0x2DD8, 0x42C8),
        _status2(0x2EC0, PENDING, 3),
        _offer(0x2FC8, 4, 0x436C, 0x43EC),
        _status2(0x312C, PENDING, 4),
        _offer(0x3234, 5, 0x32B0, 0x44C4),
        _status2(0x3398, PENDING, 5),
        _offer(0x34A0, 6, 0x351C, 0x4568),
        _status2(0x3604, PENDING, 6),
        _more(0x370C, OFFER, 7, 14),
        _offer(0x370C, 7, 0x3788, 0x460C),
        _status2(0x3870, PENDING, 7),
        _status2(0x3978, OFFER, 8),
        _status2(0x39F4, OFFER, 9),
        _more(0x3A70, OFFER, 10, 19),
        _more(0x3A70, OFFER, 10, 20, action=0x46B0),
        _status2(0x3BD4, PENDING, 10),
        _offer(0x3CDC, 11, 0x4730, 0x47B0),
        _status2(0x3E40, PENDING, 11),
        _more(0x3F48, OFFER, 12, 24),
        _offer(0x3F48, 12, 0x3FC4, 0x4888),
        _status2(0x40AC, PENDING, 12),
    ),
}

ACTIONS = {
    HUB: {
        0x1DF8: E(store=True), 0x598: E(var='demo'), 0x1FC0: E(store=True, var='demo'),
        0x1E68: E(1, True), 0x1EE8: E(1, True, True),
        0x7B0: E(2), 0x2064: E(2, store=True),
        0xA1C: E(3), 0x2108: E(3, store=True),
        0x21AC: E(4, True), 0x222C: E(4, True, True),
        0xEF4: E(5), 0x2304: E(5, store=True),
        0x23A8: E(6, True), 0x2428: E(6, True, True),
        0x13CC: E(7), 0x2500: E(7, store=True),
        0x25A4: E(10, True), 0x2624: E(10, True, True),
        0x26FC: E(11, True),
        0x1C08: E(12), 0x277C: E(12, store=True),
    },
    HUB2: {
        0x41B4: E(store=True), 0x29BC: E(var='intro'),
        0x2B6C: E(2), 0x4224: E(2, store=True),
        0x2DD8: E(3), 0x42C8: E(3, store=True),
        0x436C: E(4, True), 0x43EC: E(4, True, True),
        0x32B0: E(5), 0x44C4: E(5, store=True),
        0x351C: E(6), 0x4568: E(6, store=True),
        0x3788: E(7), 0x460C: E(7, store=True),
        0x46B0: E(10, True),
        0x4730: E(11, True), 0x47B0: E(11, True, True),
        0x3FC4: E(12), 0x4888: E(12, store=True),
    },
}

# Script public offsets that are NOT referenced by the shipped dialog, but have the
# same native lists as offer actions (the hub writers named in mission-unlocks).
UNREFERENCED_WRITERS = {
    HUB: {0x2A0: E(1, True), 0x320: E(1, True, True), 0x7FC: E(2, store=True),
          0xA68: E(3, store=True), 0xC88: E(4), 0xCD4: E(4, store=True),
          0xF40: E(5, store=True), 0x1160: E(6), 0x11AC: E(6, store=True),
          0x1418: E(7, store=True), 0x1730: E(10), 0x177C: E(10, store=True),
          0x199C: E(11), 0x19E8: E(11, store=True), 0x1C54: E(12, store=True),
          0x430: E(store=True), 0x5E4: E(store=True, var='demo')},
    HUB2: {0x2BB8: E(2, store=True), 0x2E24: E(3, store=True), 0x3044: E(4),
           0x3090: E(4, store=True), 0x32FC: E(5, store=True), 0x3568: E(6, store=True),
           0x37D4: E(7, store=True), 0x3AEC: E(10), 0x3B38: E(10, store=True),
           0x3D58: E(11), 0x3DA4: E(11, store=True), 0x4010: E(12, store=True),
           0x2A48: E(store=True)},
}


def A(raw, n):
    return raw[n] & 1


def C(raw, n):
    return (raw[n] >> 1) & 1


def predicate(kind, n, raw, started, intro=0, demo=0):
    if kind == ACTIVE:
        return int(any(A(raw, k) and not C(raw, k) and started[k] != 0 for k in MISSIONS))
    if kind == OFFER:
        return int(not A(raw, n))
    if kind == PENDING:
        return int(bool(A(raw, n) and not C(raw, n) and started[n] == 0))
    if kind == DEMO:
        return 0
    if kind == INTRO:
        return int(not A(raw, 2) and intro == 0)
    if kind == DONE:
        return C(raw, n)
    if kind == NOTDONE:
        return int(not C(raw, n))
    raise ValueError(kind)


def start_node(hub, raw, started, intro=0):
    """dialog_onMsg 0x22ee2c: node 0's condition first, then the others in file
    order; the first that returns non-zero; node 0 when none does."""
    for index, (_cond, kind, n, _choices) in enumerate(NODES[hub]):
        if predicate(kind, n, raw, started, intro):
            return index
    return 0


def visible(hub, node, raw, started, intro=0):
    """Indices of the node's choices whose condition is empty or true (0x230c74)."""
    out = []
    for index, (_role, cond, kind, n, _act, _nxt) in enumerate(NODES[hub][node][3]):
        if cond is None or predicate(kind, n, raw, started, intro):
            out.append(index)
    return out


def apply_action(effect, raw, started, quests, intro, demo):
    raw = list(raw)
    if effect['avail'] is not None:
        raw[effect['avail']] |= 1
    if effect['quest']:
        quests += 1
    if effect['var'] == 'intro':
        intro = 1
    if effect['var'] == 'demo':
        demo = 1
    return raw, quests, intro, demo


def paths(hub, raw, started, intro=0):
    """Every conversation from the start node to its close, as lists of
    (node, cursor, choice index, action offset)."""
    out = []

    def walk(node, prefix, raw, intro):
        vis = visible(hub, node, raw, started, intro)
        if not vis:
            out.append(prefix)
            return
        for cursor, choice in enumerate(vis):
            role, _c, _k, _n, action, nxt = NODES[hub][node][3][choice]
            step = prefix + [(node, cursor, choice, action)]
            r2, i2 = raw, intro
            if action is not None:
                r2, _q, i2, _d = apply_action(ACTIONS[hub][action], raw, started, 0, intro, 0)
            if nxt == -1:
                out.append(step)
            else:
                walk(nxt, step, r2, i2)

    walk(start_node(hub, raw, started, intro), [], list(raw), intro)
    return out


# ---- hub entry (`start`) -------------------------------------------------------------

def store_level(current, raw):
    """The V.store store made by both hubs' start: 0 for current mission 0;
    7 -> 8 if C(9), 7 if A(9), 6 if A(8), else 5; 9 -> 7; 8 -> 6; otherwise current - 1."""
    if current == 0:
        return 0
    if current == 7:
        if C(raw, 9):
            return 8
        if A(raw, 9):
            return 7
        if A(raw, 8):
            return 6
        return 5
    if current == 9:
        return 7
    if current == 8:
        return 6
    return current - 1


def entry_mission_bits(hub, raw):
    raw = list(raw)
    if hub == HUB:
        raw[0] |= 3           # setMissionAvailable(0,1) then grantMission(0)
    else:
        raw[1] |= 1           # hub2 sets mission 1 available only
    return raw


def entry_mana(flag, mana, mana_max):
    """V.mana == 1 -> flag 0 and every player's mana = max (refillPlayerMana 0x142494)."""
    if flag == 1:
        return 0, mana_max
    return flag, mana


def entry_flag4_cleared(current):
    """setPlayerFlag(p, 4, 0) for p = 0..3 unless the current mission is 7 or 9."""
    return current not in (7, 9)


def entry_first_mission(var, flags3, players):
    """-> (help shown, new var, flag 3 set on all players)."""
    if var == 1 and any(not flags3[p] for p in range(players)):
        var = 2
    if var == 2:
        return True, 0, True
    return False, var, False


# Unconditional quest-item cleanup in start: removePlayerItem(-1, item) for three
# private item ids, 10 + 3 + 4 call sites.
CLEANUP_SITES = (10, 3, 4)

# Deferred duplicate checks queued by start: for each player (shard list: slots 0..3,
# filtered by onePlayerHasItem's own player test; blood list: slots < players at
# start) and each listed item, one removePlayerItem when the count is above 1.
# The tables have 10 and 13 cells (bounds checks 0..9 and 0..12) but the loops stop
# at 9 and 12, so the last cell of each table is never checked.
SHARD_TABLE, BLOOD_TABLE = 10, 13
SHARD_LIST, BLOOD_LIST = 9, 12


def dedupe_removals(counts):
    """counts: per-player list of per-item counts -> number of removePlayerItem calls."""
    return sum(1 for per in counts for c in per if c > 1)


# ---- mission-map trigger and the walk-in rectangle ------------------------------------

def key_usable(raw):
    """The PushTrigger key (K.lock): demoRunning is 0, then any A(n) && !C(n) for
    n = 1..11, or A(12) alone: mission 12's completion bit is not read, so the map
    stays usable once mission 12 has been offered."""
    return int(any(A(raw, n) and not C(raw, n) for n in range(1, 12)) or bool(A(raw, 12)))


def warning(raw, started):
    """K.warn: any available, incomplete mission whose started variable is set."""
    return int(any(A(raw, n) and not C(raw, n) and started[n] != 0 for n in MISSIONS))


def use_trigger(raw, started, dialog_open=0, recall=0):
    """The PushTrigger action (K.use): 'warn' shows a help box and defers the
    pause/menu entry; otherwise the entrance is set and the mission menu opens unless a
    dialog is open or the recall countdown runs (activateMissionMenu 0x143fa8)."""
    if warning(raw, started):
        return {'warn': True, 'entrance': False, 'menu': False}
    return {'warn': False, 'entrance': True, 'menu': not dialog_open and not recall}


# K.use with a warning also runs K.help (help box) and queues K.poll.  K.poll re-queues
# itself on every run and counts only the runs on which gamePaused() is 0; on the sixth
# such run it calls activateMissionMenu (refused while a dialog is open or recall runs).
# It writes no entrance.  Each warning restarts the count.
WARN_POLL_RUNS = 6


def warn_poll_call(paused):
    """paused: gamePaused() per K.poll run after one warning -> index of the run that
    calls activateMissionMenu, or None.  That call opens the menu only when no dialog is
    open and recall is not counting (use_trigger's rule)."""
    unpaused = 0
    for index, flag in enumerate(paused):
        if not flag:
            unpaused += 1
            if unpaused == WARN_POLL_RUNS:
                return index
    return None


def walk_in(raw, started, fired):
    """K.walk: trigger(portal, 0) once, when no warning and the key is usable."""
    return int(not warning(raw, started) and key_usable(raw) and not fired)
