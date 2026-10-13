#!/usr/bin/env python3
"""farm.py - the native soak farm: seeded lockstep games of two to four native machines,
every tick of every machine compared (docs/issues/native-soak.md).

  farm.py plan   --arm fix26 --seeds 1000:40                 print the jobs, run nothing
  farm.py run    --arm fix26 --out DIR --seeds 1000:400 [--instances 6] [--hours H] [--max-frames F]
  farm.py one    --arm fix26 --out DIR --seed 1007 [--frames F] [--tag T] [--program NAME]
                 [--dump TICK[,TICK...]] [--lines FILE] [--env K=V] [--keep] [--columns FILE]
  farm.py twin   --ref s29 --arm s29f --out DIR --seeds 6100:20  the same games on two programs, each machine's
                 tick log of the one compared with the other's row for row (twin.tsv)
  farm.py report DIR [DIR...]                                totals and coverage
  run / one also take --strafe all|mixed|0,2 (whose driver uses the strafe mode; soakhooks.cpp, SOAK_STRAFE)

An arm is a program built by build_soak.py: rta_soak-<arm> (fix26: the suggested fix set;
nofix: the game as shipped).  A job is derived from its seed alone (make_job), so a seed
repeats its game exactly: number of machines, each player's class and five skills at rank
10, level, statistics, points, gold; the start level; the length; the input mix of each
segment; delay, jitter, loss and outages on the bus.

Every machine boots from power-on through the developer LAN start (boot argument --net),
the characters are written in lockstep tick 680 on every machine, the level is entered by
a pending-level write in tick 700 (before any input), and then the controllers get seeded
random input (the rig's `fuzz`).  Two machines are joined by the shim's link; three and
four through hub.py.  Each machine writes the rig's tick log; every pair of machines is
compared at every tick in every shared column until one holds the other dropped.

Written under DIR: jobs.tsv (one line per job, appended), calls.tsv (call counts by
function, summed over all machines and jobs), the directory of every job that differed
(scripts, tick logs, outputs), stop (create it to stop after the running jobs) and
limit.txt (native instances at a time) and alive: `run` ends by itself - no new job, the
running machines stopped - once that file has not been touched for --alive-minutes (45), so
touch it while you look after the farm.  Everything written is game data: keep DIR under
local/.  Needs RTA_DISC.  Machines run under `nice -n 19` (SOAK_NICE).  Standard library only.
"""
import argparse
import json
import math
import os
import random
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out', 'soak')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'rig'))
sys.path.insert(0, HERE)
import rig as riglib   # noqa: E402  (symbol files)

REC = 0x4C30
PEER = 0x44E0
ADDRESS = ['192.168.1.134', '192.168.1.132', '192.168.1.130', '192.168.1.128']    # slot 0..3
CONFIRM = 1                         # the machine that presses the lobby's confirm (the rig pair's machine A)
MODEL = {0: 0, 1: 4, 2: 8, 3: 2, 4: 6, 5: 10, 6: 11}      # class -> lobby model (live-rig.md section 11)
START_RANKS = {0: [(60, 1), (61, 1)], 1: [(60, 1), (16, 1)], 2: [(60, 1), (61, 1)], 3: [(60, 1), (61, 1)],
               4: [(60, 1), (23, 1)], 5: [(60, 1), (61, 1)], 6: [(60, 1), (61, 1), (89, 1)]}
HEALS = (50, 55, 86)
MIXES = ['move,rstick,fight,cast,potion,use,dpad,select,start,l3r3',
         'move,fight,cast,potion,use,dpad,select,start',
         'move,fight,cast,potion,use,dpad,select',
         'move,fight,cast,potion,use',
         'move,dpad,select,fight,use,potion',          # menu-heavy
         'move,fight,cast,dpad,select,start,l3r3']
BUSES = ['none', 'delay=4,jitter=3,loss=50', 'none', 'delay=10,jitter=6,loss=100', 'delay=2,jitter=2,loss=10',
         'delay=6,jitter=8,loss=30']
ARENA = 'drunare'
CORE = ['strife', 'hub', 'hub2', 'drundar', 'blood1', 'bastion1', 'citadel', 'valor', 'storm1', 'fire1', 'nit1', 'wat1',
        'islc1', 'torment0', 'swamp1', 'fay1', 'honor', 'shame1', 'inmine1', 'dis2', 'airarena', 'boar1', 'arachna1']
COVERAGE = ['Player_castSkill', 'Player_usePotion', 'Player_meleeHit', 'Player_takeDamage', 'Player_processDamage',
            'Creature_processDamage', 'damage_apply', 'player_respawn', 'arena_respawnPlayer', 'player_giveExp', 'Player_interact',
            'itemprop_tryPickup', 'inventory_giveItem', 'inventory_removeItem', 'inventory_dropItem', 'inventory_equipItem',
            'inventory_unequipItem', 'menu_openInventory', 'invmsg_dispatch', 'stats_screen', 'skills_screen',
            'inventory_onStatPoint', 'inventory_onSkillPoint', 'player_recalcStats', 'pauseMenu_open', 'config_commitOptions',
            'net_kickPeer', 'shop_openOrStock', 'shop_buy', 'shop_buySellMenu', 'workshop_input', 'recall_execute', 'save_game',
            'JumpGate_openMenu', 'missionMenu_run', 'game_loadLevel', 'net_closeLocalMenus', 'cut_advance', 'net_predictLocalPlayer']
LOCK = threading.Lock()
NICE = os.environ.get('SOAK_NICE', '19')
# The farm ends by itself when nobody looks after it: `run` creates <out>/alive, and whoever
# runs the farm touches that file now and then.  Once it is older than ALIVE_MINUTES no job is
# started and the machines of the running jobs are stopped (their jobs are not counted).
ALIVE = {'path': None, 'minutes': 45.0}


def abandoned():
    path = ALIVE['path']
    if not path:
        return False
    try:
        return time.time() - os.path.getmtime(path) > ALIVE['minutes'] * 60
    except OSError:
        return True


# ---- what is read from the user's own executable: the level list and the skill trees ----------
class Image:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        phoff, = struct.unpack_from('<I', self.data, 28)
        size, count = struct.unpack_from('<HH', self.data, 42)
        self.segments = []
        for i in range(count):
            kind, offset, vaddr, _, filesz, _ = struct.unpack_from('<6I', self.data, phoff + i * size)
            if kind == 1:
                self.segments.append((vaddr, filesz, offset))

    def read(self, address, length):
        for vaddr, filesz, offset in self.segments:
            if vaddr <= address < vaddr + filesz:
                return self.data[offset + address - vaddr:offset + address - vaddr + length]
        return b''

    def text(self, address):
        return self.read(address, 32).split(b'\0')[0].decode('latin1')


def level_names(image):
    """g_levelTable 0x4f7210: rows of 0x30 bytes, the name pointer first, a null name ends it."""
    names = []
    for i in range(200):
        pointer, = struct.unpack('<I', image.read(0x4F7210 + i * 0x30, 4))
        if not pointer:
            break
        names.append(image.text(pointer))
    return names


def skill_trees():
    """class -> active skill ids, from the rig's reading of the skill-tree tables (local file),
    without the two ids every class starts with."""
    path = os.path.join(ROOT, 'local', 'rig-out', 'p6-trees.json')
    trees = json.load(open(path))
    return {int(c): [s for s in t['active'] if s not in (60, 61)] for c, t in trees.items()}


# ---- a job from its seed ---------------------------------------------------------------------
def make_job(seed, arm, levels, trees, frames=None):
    r = random.Random(seed * 7919 + 13)
    kind = r.random()
    machines = 2 if kind < 0.80 else (3 if kind < 0.90 else 4)
    players = []
    for slot in range(machines):
        cls = r.randrange(7)
        tree = trees[cls]
        skills = r.sample(tree, min(5, len(tree)))
        if r.random() < 0.25:               # a healing skill on a button, where the class has one
            heals = [s for s in tree if s in HEALS]
            if heals and heals[0] not in skills[:2]:
                skills = [heals[0]] + [s for s in skills if s != heals[0]][:4]
        players.append({'class': cls, 'skills': skills})
    flags = []
    level_roll = r.random()
    char_level = 25 if level_roll < 0.65 else (8 if level_roll < 0.85 else 45)
    if r.random() < 0.5:
        flags.append('refill')
    if r.random() < 0.66:
        flags.append('gold')
    if r.random() < 0.5:
        flags.append('passives')
    if r.random() < 0.35:
        flags.append('levelup')
    where = r.random()
    if where < 0.30:
        level = ARENA
    elif where < 0.60:
        level = CORE[r.randrange(len(CORE))]
    else:
        level = levels[r.randrange(len(levels))]
    length = r.random()
    total = 30000 if length < 0.40 else (60000 if length < 0.80 else (120000 if length < 0.95 else 300000))
    if frames:
        total = frames
    segments = []
    left = total
    while left > 0:
        n = min(left, r.choice([6000, 9000, 15000]))
        segments.append((n, MIXES[r.randrange(len(MIXES))] if r.random() < 0.7 else MIXES[r.randrange(3)]))
        left -= n
    bus = BUSES[r.randrange(len(BUSES))]
    if r.random() < 0.08:
        bus = '%s,stallat=%d,stall=%d' % ('delay=2' if bus == 'none' else bus, 2500 + total // 2, r.choice([60, 90, 120]))
    return {'seed': seed, 'arm': arm, 'machines': machines, 'players': players, 'flags': flags, 'char_level': char_level,
            'level': level, 'frames': total, 'segments': segments, 'bus': bus,
            'name': '%s-%d' % (arm, seed)}


def with_strafe(job, how, spec=''):
    """Which machines' drivers use the strafe mode: 'all'; 'mixed' - by the seed, at least one
    that never does and at least one that does; 'none'.  A list of machine numbers is taken as it is."""
    n = job['machines']
    if not how or how == 'none':
        return job
    if how == 'all':
        who = list(range(n))
    elif how == 'mixed':
        r = random.Random(job['seed'] * 104729 + 7)
        who = [m for m in range(n) if r.random() < 0.5]
        if len(who) == n:
            who.remove(r.randrange(n))
        if not who:
            who = [r.randrange(n)]
    else:
        who = [int(x) for x in how.split(',')]
    return dict(job, strafe=who, strafe_spec=spec)


def describe(job):
    return '%s m%d %s L%d %s %df bus[%s] %s' % (
        job['name'], job['machines'], '+'.join('c%d(%s)' % (p['class'], ','.join(map(str, p['skills']))) for p in job['players']),
        job['char_level'], job['level'], job['frames'], job['bus'], ','.join(job['flags']))


def build_lines(job):
    """The characters, written in lockstep tick 680 on every machine alike."""
    lines = []
    lvl = job['char_level']
    stats = {8: (40, 60, 30, 50), 25: (200, 300, 150, 250), 45: (400, 500, 300, 450)}[lvl]
    for slot, player in enumerate(job['players']):
        rec = lambda off: 'g_players+%d+0x%x' % (slot * REC, off)
        put = lambda off, kind, value: lines.append('ontick 680 poke %s:%s %s' % (rec(off), kind, value))
        put(0x58, 's8', lvl)
        # a level-up left pending: the acknowledged level one below, points to spend
        put(0x59, 's8', lvl - 1 if 'levelup' in job['flags'] else lvl)
        for i, value in enumerate(stats):
            put(0x78 + i * 4, 's32', value)
            put(0x90 + i * 4, 's32', value)
        for off in (0xB0, 0xAC, 0xC4, 0xC0):
            put(off, 'f32', 900)
        skills = player['skills']
        ranks = [x for x in START_RANKS[player['class']] if x[0] not in skills] + [(s, 10) for s in skills]
        blob = b''.join(struct.pack('<hh', i, k) for i, k in ranks) + struct.pack('<hh', -1, -1)
        put(0x4B08, 'hex%d' % len(blob), blob.hex())
        for j, skill in enumerate(skills):
            put(0x4440 + j * 0x68, 'str16', 'newstyle')
            put(0x4460 + j * 0x68, 'hex6', struct.pack('<hhBB', skill, 0, 1, 0).hex())
        put(0x4A84, 'hex2', '0001')
        if 'passives' in job['flags']:
            put(0xEF, 'hex48', '05' * 48)
        if 'gold' in job['flags']:
            put(0xE4, 's32', 50000)
        if 'levelup' in job['flags']:
            put(0xE8, 's32', 12)
            put(0xEC, 's8', 15)
        if 'refill' in job['flags']:
            for tick in range(900, job['frames'] + 3000, 300):
                lines.append('ontick %d poke %s:f32 500' % (tick, rec(0xC0)))
    return lines


def script_lines(job, machine, extra_lines=()):
    """One machine's script.  Every machine's script lets the same frames pass in every line."""
    n = job['machines']
    lines = ['netshim']
    for slot, player in enumerate(job['players']):
        lines.append('poke 0x%x:s32 %d' % (0x530338 + slot * 4, MODEL[player['class']]))
    lines += ['at 300',
              'tapuntil cross 40 g_numPeers:s32 >= 1 timeout 6000',
              'until g_numPeers:s32 >= %d timeout 2400' % n,
              'wait 30',
              'tap cross 4' if machine == CONFIRM else 'wait 4',
              'until g_players+0x43d8:u32 != 0 timeout 4000',
              'until g_netFrame:s32 >= 640 timeout 4000']
    lines += build_lines(job)
    lines += list(extra_lines)
    level = job['level']
    lines += ['ontick 700 poke g_pendingLevel:str16 %s' % level, 'wait 120']
    if level == 'strife':
        lines += ['wait 300']
    lines += ['until g_levelName:str16 == %s timeout 6000 continue' % level,
              'until g_players+0x43d8:u32 != 0 timeout 6000 continue', 'wait 150']
    if level == ARENA:
        # the trigger strip of the opening is west of the entry (x below 183): the confirming
        # machine's player walks there; the cutscene flag is 0x44fcd0
        walk = ['stick L 0 128', 'until 0x44fcd0:u8 != 0 timeout 240 continue', 'stick L 128 0',
                'until 0x44fcd0:u8 != 0 timeout 120 continue', 'stick L 128 128']
        still = ['wait 0', 'until 0x44fcd0:u8 != 0 timeout 240 continue', 'wait 0',
                 'until 0x44fcd0:u8 != 0 timeout 120 continue', 'wait 0']
        lines += walk if machine == CONFIRM else still
        lines += ['until 0x44fcd0:u8 == 0 timeout 4000 continue']
    lines += ['wait 30']
    for index, (frames, groups) in enumerate(job['segments']):
        if job.get('directed') is not None:     # a directed game: the caller's lines in place of random input
            lines += [line.replace('%M', str(machine)) for line in job['directed']]
            lines.append('wait %d' % frames)
            break
        lines.append('fuzz %d %d %s' % (job['seed'] * 64 + index * 4 + machine, frames, groups))
    lines += ['wait 120', 'quit']
    return lines


# ---- tick-log columns -------------------------------------------------------------------------
SOFT_PREFIX = ('poolraw', 'poolfree', 'actplayer')         # followed on their own (the pool sums until the mask is trusted)
SOFT_SUFFIX = ('dmg', 'trailhit', 'trailhit2', 'points')


def is_soft(column):
    base = re.sub(r'^p\d', '', column)
    return column in SOFT_PREFIX or base in SOFT_SUFFIX


def tick_columns(local_slot, players):
    rec = lambda n: 'g_players+%d' % (n * REC)
    peer = lambda n: 'g_peers+%d' % (n * PEER)
    specs = ['net=g_netFrame:s32', 'seed=g_randSeed:x32', 'level=g_levelName:str12', 'nplayers=g_numPlayers:s32',
             'btnmaps=0x41b980:crc192',
             'prevhash=%s+0x18ac+((g_netFrame-1)&0xff)*12+8:x32' % peer(local_slot),
             'pool=0xe0000:x32', 'nobj=0xe0008:u32', 'poolraw=0xe0004:x32', 'poolfree=0xe000c:x32',
             'cut=0x44fcd0:u8', 'pending=g_pendingLevel:str12', 'qvars=g_questVars:crc2048',
             'postact=g_scriptPostAction:str16', 'jgtravel=g_jumpGateTravel:s32', 'jgstate=g_jumpGateMenuState:s8',
             'mmstate=0x8e2efc:u8',
             # shared state that code outside the tick can write (native-soak.md, "Save point" and
             # "Script variables"): the menu mutex, the jump gates found so far, the script's active player
             'mutex=0x4fe53c:u32', 'jgcount=0x8e3c30:s8', 'jgdests=0x8e3a50:crc480', 'actplayer=0x4d8ae4:s32',
             # third part: the driver of the strafe mode (soakhooks.cpp): sender calls made, mode last sent
             'l_strafesent=0xe0050:u32', 'l_strafewant=0xe0054:u32',
             'l_inp=g_localInputFrame:s32', 'l_cosmetic=g_cosmeticSeed:x32', 'l_drawframe=g_drawFrame:u32',
             'l_pause=g_pauseMenuOpen:u8', 'l_menu=g_localMenuOpen:u8', 'l_ghost=0x4027bc:x32',
             'l_c0=0xe0010:u32', 'l_c1=0xe0014:u32', 'l_c2=0xe0018:u32']
    for n in range(players):
        obj = '[%s+0x43d8]' % rec(n)
        r = rec(n)
        specs += ['p%dx=%s+0x10:x32' % (n, obj), 'p%dy=%s+0x14:x32' % (n, obj), 'p%dz=%s+0x18:x32' % (n, obj),
                  'p%dangle=%s+0x38:u16' % (n, obj), 'p%dstate=%s+0x58c:s32' % (n, obj), 'p%dobjseed=%s+0x44:x32' % (n, obj),
                  # third part: the strafe mode byte of the player object, and the yaw word that travels with the input
                  'p%dmode=%s+0x47e:u8' % (n, obj), 'yaw%d=0x%x:u16' % (n, 0x5D0BC0 + n * 2),
                  'p%dhp=%s+0xac:x32' % (n, r), 'p%dmana=%s+0xc0:x32' % (n, r), 'p%dgold=%s+0xe4:s32' % (n, r),
                  'p%dexp=%s+0x5c:s32' % (n, r),
                  'p%dbag0=%s+0x130:crc4612' % (n, r), 'p%dbag1=%s+0x1338:crc4612' % (n, r), 'p%dbag2=%s+0x2540:crc4612' % (n, r),
                  'p%dstats=%s+0x58:crc84' % (n, r), 'p%dpoints=%s+0xe4:crc59' % (n, r), 'p%dpts=%s+0xe4:crc8' % (n, r),
                  'p%dpassive=%s+0xef:crc48' % (n, r),
                  'p%dequip=%s+0x43f0:crc80' % (n, r), 'p%dabil=%s+0x4440:crc1560' % (n, r), 'p%dskills=%s+0x4b08:crc192' % (n, r),
                  'p%ddmg=%s+0xcc:hex12' % (n, r), 'p%dwset=%s+0x4a7c:x16' % (n, r),
                  'p%dmaxhp=%s+0xb0:x32' % (n, r), 'p%dmaxmana=%s+0xc4:x32' % (n, r), 'p%dpotion=%s+0xb4:hex12' % (n, r),
                  'p%dmanapot=%s+0xc8:x32' % (n, r), 'p%dstagger=%s+0xdc:x32' % (n, r), 'p%dload=%s+0x120:hex8' % (n, r),
                  'p%darmour=%s+0xe4:x16' % (n, obj), 'p%dresist=%s+0x5c:hex20' % (n, obj),
                  'p%dhead=%s+0x0:crc88' % (n, r), 'p%dd8=%s+0xd8:x32' % (n, r), 'p%de0=%s+0xe0:x32' % (n, r),
                  'p%du128=%s+0x128:hex8' % (n, r), 'p%dblk=%s+0x3748:crc2696' % (n, r), 'p%dquest=%s+0x41d0:crc520' % (n, r),
                  'p%dbtnA=%s+0x4a60:crc20' % (n, r), 'p%dbtnB=%s+0x4a7c:crc12' % (n, r),
                  'p%dtrailhit=%s+0x4ac5:hex2' % (n, r), 'p%dtrailhit2=%s+0x4b05:hex2' % (n, r), 'p%dtail=%s+0x4bc8:crc104' % (n, r),
                  'oos%d=%s+0x44d7:u8' % (n, peer(n)), 'l_dropped%d=%s+0x44d5:u8' % (n, peer(n)),
                  # the object pointer itself: while it is null (the tick of a level reload) the columns
                  # read through it show low memory, which is the runtime's and per machine
                  'l_p%dobj=%s+0x43d8:x32' % (n, r)]
    if os.environ.get('SOAK_FARM_COLUMNS') == 'small':      # for measuring what the columns cost
        keep = ('net=', 'seed=', 'level=', 'cut=', 'nobj=', 'pool=', 'l_dropped', 'oos')
        specs = [x for x in specs if x.startswith(keep) or re.match(r'p\d(x|y|z|hp|maxhp)=', x)]
    return specs


# ---- running one job --------------------------------------------------------------------------
class Gate:
    """At most `limit()` native instances at a time over all running jobs."""
    def __init__(self, path, default):
        self.path, self.default, self.active, self.cond = path, default, 0, threading.Condition()

    def limit(self):
        try:
            return max(0, int(open(self.path).read().strip()))
        except Exception:
            return self.default

    def take(self, n):
        with self.cond:
            while self.active + n > max(self.limit(), n if self.active == 0 and self.limit() > 0 else 0):
                self.cond.wait(timeout=5)
            self.active += n

    def give(self, n):
        with self.cond:
            self.active -= n
            self.cond.notify_all()


def run_job(job, out_root, program=None, tag='', keep=False, extra_lines=(), extra_env=None, extra_columns=(), dumps=(),
            sample_dumps=False):
    name = job['name'] + tag
    out = os.path.join(out_root, name)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    n = job['machines']
    program = program or os.path.join(OUT, 'bin', 'rta_soak-' + job['arm'])
    if not os.path.isabs(program):
        program = os.path.join(OUT, 'bin', program)
    symbols = ':'.join(riglib.symbol_files())
    link_dir = tempfile.mkdtemp(prefix='sk', dir=os.environ.get('RTA_LINK_DIR') or tempfile.gettempdir())
    paths = [os.path.join(link_dir, 'm%d.sock' % m) for m in range(n)]
    more = list(extra_lines)
    for tick in dumps:
        more += ['ontick %d dump 0x5f88c0 0xe7700 %s' % (tick, os.path.join(out, 'm%%M-pool-%d.bin' % tick)),
                 'ontick %d dump 0x402000 0x2000 %s' % (tick, os.path.join(out, 'm%%M-glob-%d.bin' % tick))]
    processes = []
    hub = None
    if n > 2:
        hub = subprocess.Popen([sys.executable, '-I', '-B', os.path.join(HERE, 'hub.py')] + paths,
                               stdout=open(os.path.join(out, 'hub.out'), 'w'), stderr=subprocess.STDOUT)
        deadline = time.time() + 20
        while not all(os.path.exists(p) for p in paths) and time.time() < deadline:
            time.sleep(0.05)
    for m in range(n):
        card = os.path.join(out, 'card-%d' % m)
        source = os.path.join(ROOT, 'local', 'rig-out', 'pair-%s' % ('a' if m == CONFIRM else 'b'), 'vfs')
        shutil.copytree(source, card)
        script = os.path.join(out, 'm%d.rig' % m)
        with open(script, 'w') as sink:
            sink.write('\n'.join(line.replace('%M', str(m)) for line in script_lines(job, m, more)) + '\n')
        watch = os.path.join(out, 'm%d.watch.txt' % m)
        with open(watch, 'w') as sink:
            sink.write('\n'.join(tick_columns(m, n) + list(extra_columns)) + '\n')
        env = dict(os.environ, RTA_NET_ADDR=ADDRESS[m], RTA_NET_MACHINE='A' if m == CONFIRM else 'B', RTA_NET_SYM=symbols,
                   RTA_NET_TICKLOG=os.path.join(out, 'm%d.tick.tsv' % m), RTA_NET_WATCH=watch, RTA_NET_SCRIPT=script,
                   RTA_NET_ARG='--net', RTA_NET_ALLOW_LEVEL='1', SOAK_CALLS=os.path.join(out, 'm%d.calls.txt' % m),
                   SOAK_MACHINES=str(n))
        mask = os.path.join(HERE, 'poolmask.txt')
        if os.path.exists(mask):
            env['SOAK_MASK'] = mask
        if n == 2:      # the shim's own pair link: the confirming machine listens, as the rig pair's machine A does
            env['RTA_NET_LINK'] = '%s:%s' % ('listen' if m == CONFIRM else 'connect', paths[0])
        else:
            env['RTA_NET_LINK'] = 'connect:' + paths[m]
        if job['bus'] != 'none':
            env['RTA_NET_BUS'] = '%s,seed=%d' % (job['bus'], job['seed'] * 4 + (m if m > 1 else 0))
        if m in job.get('strafe', ()):      # this machine's driver sets and clears its own player's strafe mode
            env['SOAK_STRAFE'] = '%d%s' % (job['seed'] * 16 + m + 1, job.get('strafe_spec', ''))
            env['SOAK_STRAFE_SLOT'] = str(m)
        if job.get('survive'):              # a directed game in which machines leave: nobody is stopped for it
            env['SOAK_MACHINES'] = '0'
        env.update({k: v.replace('%M', str(m)) for k, v in (extra_env or {}).items()})
        env.update(job.get('menv', {}).get(m, {}))
        sink = open(os.path.join(out, 'm%d.out' % m), 'w')
        command = ['nice', '-n', NICE, program, 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--card', card]
        command += os.environ.get('SOAK_RUNTIME_OPTIONS', '').split()
        processes.append((subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT, env=env, cwd=ROOT), sink))
    began = time.time()
    limit = job['frames'] / 12.0 + 1500
    ended = None
    timed_out = False
    stopped = False
    while any(p.poll() is None for p, _ in processes):
        now = time.time()
        if ended is None and any(p.poll() is not None for p, _ in processes):
            ended = now
        if abandoned():
            stopped = True
        if stopped or (ended is not None and now - ended > (900 if job.get('survive') else 60)) or now - began > limit:
            timed_out = timed_out or now - began > limit
            for p, _ in processes:
                if p.poll() is None:
                    p.kill()
        time.sleep(0.5)
    codes = []
    for p, sink in processes:
        codes.append(p.wait())
        sink.close()
    if hub:
        try:
            hub.wait(timeout=10)
        except subprocess.TimeoutExpired:
            hub.kill()
    shutil.rmtree(link_dir, ignore_errors=True)
    result = {'name': name, 'dir': out, 'secs': time.time() - began, 'codes': codes, 'timed_out': timed_out, 'stopped': stopped}
    if stopped:         # the farm was left alone: nothing of this job is kept or counted
        shutil.rmtree(out, ignore_errors=True)
        return result
    try:
        result.update(analyse(out, n, through_drops=bool(job.get('survive'))))
    except Exception as error:      # a machine that never wrote a log
        result.update({'ticks': 0, 'first': None, 'error': repr(error)[:300]})
    if sample_dumps:
        result['rawdiff'] = raw_differences(out, n, dumps, result)
        for m in range(n):
            for tick in dumps:
                for kind in ('pool', 'glob'):
                    try:
                        os.remove(os.path.join(out, 'm%d-%s-%d.bin' % (m, kind, tick)))
                    except OSError:
                        pass
    result['notes'] = machine_notes(out, n)
    result['calls'] = read_calls(out, n)
    for m in range(n):
        shutil.rmtree(os.path.join(out, 'card-%d' % m), ignore_errors=True)
    clean = result.get('ticks', 0) > 0 and result.get('first') is None and not timed_out and not result.get('error')
    if clean and not keep:
        shutil.rmtree(out, ignore_errors=True)
    return result


def raw_differences(out, n, ticks, result):
    """[(tick, pair, class, offset, objects, a value, b value)] for the sampled ticks at which the
    two machines were still in step (before any deciding difference or drop)."""
    import poolcmp
    rows = []
    limit = min(x for x in (result.get('first'), result.get('dropped'), 1 << 60) if x is not None)
    names = poolcmp.vtable_names()
    for tick in ticks:
        if tick >= limit:
            continue
        for b in range(1, n):
            try:
                offsets, lines, _, _ = poolcmp.compare(out, tick, (0, b), masked=True, names=names)
            except (OSError, ValueError, IndexError, __import__('struct').error):
                continue
            sample = {}
            for line in lines:
                found = re.match(r'  (\S+) at \w+ \+0x(\w+): (\w+) \| (\w+)', line)
                if found:
                    sample.setdefault((found.group(1), int(found.group(2), 16)), (found.group(3), found.group(4)))
            blocks = sum(1 for l in lines if l.startswith('  block'))
            if blocks:
                rows.append((tick, '0-%d' % b, '(blocks live on one machine only)', 0, blocks, '', ''))
            for name, counter in offsets.items():
                for offset, count in counter.items():
                    rows.append((tick, '0-%d' % b, name, offset, count) + sample.get((name, offset), ('', '')))
    return rows


def shortened(job, frames):
    """The same game with the input cut off after `frames` frames (the same segments)."""
    if frames >= job['frames']:
        return job
    left, segments = frames, []
    for n, groups in job['segments']:
        if left <= 0:
            break
        segments.append((min(n, left), groups))
        left -= n
    return dict(job, frames=frames, segments=segments)


def explain(directory, tick, pair):
    """Which classes and word offsets of the object pool differ in the tick of a difference and
    in the tick before it (poolcmp.py on the dumps of the second run)."""
    try:
        import poolcmp
        machines = tuple(int(x) for x in pair.split('-'))
        parts = []
        for t in (tick - 1, tick):
            offsets, lines, _, _ = poolcmp.compare(directory, t, machines, masked=True)
            text = '; '.join('%s %s' % (name, ' '.join('+%x(%d)' % item for item in sorted(counter.items())[:10]))
                             for name, counter in sorted(offsets.items())[:8])
            blocks = sum(1 for l in lines if l.startswith('  block'))
            parts.append('tick %d: %s%s' % (t, text or 'no object differs', ', %d blocks live on one only' % blocks if blocks else ''))
        return ' || '.join(parts)[:900]
    except Exception as error:
        return 'no dump (%r)' % (error,)


def machine_notes(out, n):
    """What the machines printed that matters: accesses where nothing is, timeouts, out-of-sync lines."""
    notes = []
    for m in range(n):
        try:
            text = open(os.path.join(out, 'm%d.out' % m), errors='replace').read()
        except OSError:
            continue
        for pattern in (r'accesses where nothing is.*: (\d+ reads, \d+ stores)', r'(TIMEOUT line \d+: [^\n]*)',
                        r'(\[tick \d+\] frame \d+: the game holds peer \d OUT OF SYNC)', r'(netshim: [^\n]*)',
                        r'(rt: [^\n]*stopped[^\n]*)', r'(soak: [^\n]*)'):
            for found in re.findall(pattern, text)[:3]:
                if found != '0 reads, 0 stores':
                    notes.append('m%d %s' % (m, found[:160]))
    return notes


def read_calls(out, n):
    total = {}
    for m in range(n):
        try:
            for line in open(os.path.join(out, 'm%d.calls.txt' % m)):
                address, count = line.split()
                total[address] = total.get(address, 0) + int(count)
        except OSError:
            pass
    return total


# ---- comparing the tick logs --------------------------------------------------------------------
def rows_of(path):
    handle = open(path, errors='replace')
    header = handle.readline().rstrip('\n').split('\t')
    net = header.index('net')

    def rows():
        last = -1
        for line in handle:
            fields = line.rstrip('\n').split('\t')
            if len(fields) != len(header):
                continue
            try:
                tick = int(fields[net])
            except ValueError:
                continue
            if tick <= last:
                continue
            last = tick
            yield tick, fields
        handle.close()
    return header, rows()


def bits_float(text):
    return struct.unpack('<f', struct.pack('<I', int(text, 16)))[0]


def analyse(out, n, through_drops=False):
    """Every pair of machines, tick by tick.  The result describes the earliest difference
    of any pair in a deciding column; soft columns are counted on their own.
    through_drops: a pair is compared on after one of the two holds a peer dropped (directed
    games in which a machine leaves and the others play on)."""
    result = {'ticks': 0, 'first': None, 'columns': [], 'values': {}, 'pair': None, 'oos': None, 'dropped': None,
              'soft': {}, 'levels': [], 'deaths': [0] * n, 'cut_ticks': 0, 'pair_ticks': {}, 'overmax': 0,
              'nobj_max': 0, 'last_tick': None,
              # the strafe mode (third part): ticks with any player in the mode; player-ticks in the mode; of those,
              # running ticks (state 1, moved more than a unit) and how many of them ran more than 45 and more than
              # 135 degrees off the facing; the same two figures for players not in the mode (the check on the measure)
              'mode_any': 0, 'mode_ticks': 0, 'run_mode': 0, 'run_side': 0, 'run_back': 0, 'run_plain': 0, 'run_plain_off': 0,
              'mode_switches': 0, 'sent': 0}
    # what machine 0 saw
    header, rows = rows_of(os.path.join(out, 'm0.tick.tsv'))
    col = {c: i for i, c in enumerate(header)}
    alive = [True] * n
    has_mode = 'p0mode' in col
    before = [None] * n         # (x, y, mode) of each player in the tick before
    for tick, f in rows:
        if has_mode:
            any_mode = False
            for p in range(n):
                try:
                    if f[col['l_p%dobj' % p]] == '00000000':
                        before[p] = None
                        continue
                    x, y = bits_float(f[col['p%dx' % p]]), bits_float(f[col['p%dy' % p]])
                    mode = int(f[col['p%dmode' % p]])
                    facing = int(f[col['p%dangle' % p]])
                    state = f[col['p%dstate' % p]]
                except (ValueError, struct.error):
                    before[p] = None
                    continue
                if mode:
                    any_mode = True
                    result['mode_ticks'] += 1
                if before[p] is not None:
                    if bool(before[p][2]) != bool(mode):
                        result['mode_switches'] += 1
                    dx, dy = x - before[p][0], y - before[p][1]
                    if state == '1' and 1.0 < dx * dx + dy * dy < 400.0:
                        # the game's heading: an object facing a runs along (cos a, sin a), a in 65536ths of a turn
                        off = abs(((int(round(math.atan2(dy, dx) * 32768.0 / math.pi)) - facing + 32768) & 0xFFFF) - 32768)
                        if mode:
                            result['run_mode'] += 1
                            result['run_side'] += off > 8192
                            result['run_back'] += off > 24576
                        else:
                            result['run_plain'] += 1
                            result['run_plain_off'] += off > 8192
                before[p] = (x, y, mode)
            result['mode_any'] += any_mode
        level = f[col['level']]
        if not result['levels'] or result['levels'][-1][1] != level:
            result['levels'].append((tick, level))
        if f[col['cut']] != '0':
            result['cut_ticks'] += 1
        try:
            result['nobj_max'] = max(result['nobj_max'], int(f[col['nobj']]))
        except ValueError:
            pass
        for p in range(n):
            try:
                bits = int(f[col['p%dhp' % p]], 16)
                top = int(f[col['p%dmaxhp' % p]], 16)
            except ValueError:
                continue
            now = 0 < bits < 0x80000000
            if alive[p] and not now:
                result['deaths'][p] += 1
            alive[p] = now
            if now and 0 < top < 0x80000000 and bits > top:
                result['overmax'] += 1
        result['last_tick'] = tick
    for a in range(n):
        for b in range(a + 1, n):
            ha, ra = rows_of(os.path.join(out, 'm%d.tick.tsv' % a))
            hb, rb = rows_of(os.path.join(out, 'm%d.tick.tsv' % b))
            shared = [c for c in ha if c in hb and c not in ('frame', 'net') and not c.startswith('l_')]
            hard = [(c, ha.index(c), hb.index(c)) for c in shared if not is_soft(c)]
            # columns read through a player's object pointer, and where that pointer is in each log
            through = {}
            for p in range(n):
                if 'l_p%dobj' % p in ha and 'l_p%dobj' % p in hb:
                    through[p] = (ha.index('l_p%dobj' % p), hb.index('l_p%dobj' % p))
            via_object = re.compile(r'^p(\d)(x|y|z|angle|state|objseed|armour|resist|mode)$')
            soft = [(c, ha.index(c), hb.index(c)) for c in shared if is_soft(c)]
            drop_a = [ha.index('l_dropped%d' % p) for p in range(n)]
            drop_b = [hb.index('l_dropped%d' % p) for p in range(n)]
            oos_a = [i for i, c in enumerate(ha) if c.startswith('oos')]
            oos_b = [i for i, c in enumerate(hb) if c.startswith('oos')]
            compared = 0
            first = None
            tick_b, fields_b = next(rb, (None, None))
            for tick_a, fields_a in ra:
                while tick_b is not None and tick_b < tick_a:
                    tick_b, fields_b = next(rb, (None, None))
                if tick_b != tick_a:
                    continue
                # a machine that holds anyone dropped is out of the comparison from then on:
                # a kick or a leave is the game's own doing (live-rig.md 8.2)
                if any(fields_a[i] == '1' for i in drop_a) or any(fields_b[i] == '1' for i in drop_b):
                    if result['dropped'] is None or tick_a < result['dropped']:
                        result['dropped'] = tick_a
                    if not through_drops:
                        break
                compared += 1
                if result['oos'] is None and (any(fields_a[i] not in ('0', '') for i in oos_a) or
                                              any(fields_b[i] not in ('0', '') for i in oos_b)):
                    result['oos'] = tick_a
                for c, x, y in soft:
                    if fields_a[x] != fields_b[y]:
                        entry = result['soft'].setdefault(c, {'first': tick_a, 'n': 0, 'a': fields_a[x], 'b': fields_b[y],
                                                              'pair': '%d-%d' % (a, b), 'last': tick_a})
                        entry['n'] += 1
                        entry['last'] = tick_a
                if first is None:
                    differing = [(c, fields_a[x], fields_b[y]) for c, x, y in hard if fields_a[x] != fields_b[y]]
                    if differing and through:       # not while that player has no object on either machine
                        kept = []
                        for item in differing:
                            found = via_object.match(item[0])
                            if found and int(found.group(1)) in through:
                                ia_, ib_ = through[int(found.group(1))]
                                if fields_a[ia_] == '00000000' and fields_b[ib_] == '00000000':
                                    continue
                            kept.append(item)
                        differing = kept
                    if differing:
                        first = tick_a
                        if result['first'] is None or tick_a < result['first']:
                            result['first'] = tick_a
                            result['pair'] = '%d-%d' % (a, b)
                            result['columns'] = sorted(c for c, _, _ in differing)
                            result['values'] = {c: (x, y) for c, x, y in differing}
            result['pair_ticks']['%d-%d' % (a, b)] = compared
    for m in range(n):          # sender calls each machine's driver made (the last row's count)
        try:
            header_m, rows_m = rows_of(os.path.join(out, 'm%d.tick.tsv' % m))
            last = None
            for _, fields in rows_m:
                last = fields
            if last is not None and 'l_strafesent' in header_m:
                result['sent'] += int(last[header_m.index('l_strafesent')])
        except (OSError, ValueError):
            pass
    result['ticks'] = min(result['pair_ticks'].values()) if result['pair_ticks'] else 0
    result['ticks_sum'] = sum(result['pair_ticks'].values())
    return result


def class_of(result):
    """Columns at the first difference, player numbers folded."""
    return '+'.join(sorted({re.sub(r'^p\d', 'p', c) for c in result.get('columns', [])}))


# ---- the farm ---------------------------------------------------------------------------------
FIELDS = ['name', 'seed', 'machines', 'classes', 'skills', 'char_level', 'level', 'frames', 'bus', 'flags', 'mixes',
          'ticks', 'ticks_sum', 'first', 'class', 'pair', 'values', 'oos', 'dropped', 'repeats', 'soft', 'levels', 'deaths',
          'cut_ticks', 'overmax', 'nobj_max', 'secs', 'codes', 'timed_out', 'notes', 'error', 'where',
          'strafe', 'mode_any', 'mode_ticks', 'mode_switches', 'sent', 'run_mode', 'run_side', 'run_back', 'run_plain', 'run_plain_off']


def job_row(job, result):
    row = {'name': result['name'], 'seed': job['seed'], 'machines': job['machines'],
           'classes': '+'.join(str(p['class']) for p in job['players']),
           'skills': '/'.join(','.join(map(str, p['skills'])) for p in job['players']),
           'char_level': job['char_level'], 'level': job['level'], 'frames': job['frames'], 'bus': job['bus'],
           'flags': ','.join(job['flags']), 'mixes': ';'.join('%d:%d' % (f, MIXES.index(g)) for f, g in job['segments']),
           'ticks': result.get('ticks', 0), 'ticks_sum': result.get('ticks_sum', 0), 'first': result.get('first'),
           'class': class_of(result) if result.get('first') is not None else '', 'pair': result.get('pair'),
           'values': ' '.join('%s=%s|%s' % (c, v[0][:24], v[1][:24]) for c, v in sorted(result.get('values', {}).items()))[:600],
           'oos': result.get('oos'), 'dropped': result.get('dropped'), 'repeats': result.get('repeats', ''),
           'soft': ' '.join('%s:%d@%d(%s|%s)' % (c, e['n'], e['first'], e['a'][:12], e['b'][:12])
                            for c, e in sorted(result.get('soft', {}).items())),
           'levels': ' '.join('%d:%s' % item for item in result.get('levels', [])[:40]),
           'deaths': '/'.join(map(str, result.get('deaths', []))), 'cut_ticks': result.get('cut_ticks', 0),
           'overmax': result.get('overmax', 0), 'nobj_max': result.get('nobj_max', 0), 'secs': int(result.get('secs', 0)),
           'codes': ','.join(map(str, result.get('codes', []))), 'timed_out': int(bool(result.get('timed_out'))),
           'notes': '; '.join(result.get('notes', []))[:500], 'error': result.get('error', ''),
           'where': result.get('where', ''),
           'strafe': ','.join(str(m) for m in job.get('strafe', ())) + job.get('strafe_spec', '')}
    for key in ('mode_any', 'mode_ticks', 'mode_switches', 'sent', 'run_mode', 'run_side', 'run_back', 'run_plain', 'run_plain_off'):
        row[key] = result.get(key, 0)
    return '\t'.join('' if row[k] is None else str(row[k]).replace('\t', ' ') for k in FIELDS)


def add_calls(out_root, calls):
    path = os.path.join(out_root, 'calls.tsv')
    total = {}
    if os.path.exists(path):
        for line in open(path):
            address, count = line.split()
            total[address] = int(count)
    for address, count in calls.items():
        total[address] = total.get(address, 0) + count
    with open(path + '.tmp', 'w') as sink:
        for address in sorted(total, key=lambda a: int(a, 16)):
            sink.write('%s\t%d\n' % (address, total[address]))
    os.replace(path + '.tmp', path)


def farm(args, levels, trees):
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)
    first, count = (int(x) for x in args.seeds.split(':'))
    done = set()
    jobs_path = os.path.join(out_root, 'jobs.tsv')
    if os.path.exists(jobs_path):
        for line in open(jobs_path):
            fields = line.split('\t')
            if len(fields) > 2 and fields[1].isdigit() and not fields[0].endswith('-again'):
                done.add(int(fields[1]))
    else:
        with open(jobs_path, 'w') as sink:
            sink.write('\t'.join(FIELDS) + '\n')
    gate = Gate(os.path.join(out_root, 'limit.txt'), args.instances)
    deadline = time.time() + args.hours * 3600 if args.hours else None
    todo = [with_strafe(make_job(seed, args.arm, levels, trees), args.strafe, args.strafe_spec)
            for seed in range(first, first + count) if seed not in done]
    if args.max_frames:     # an arm that is expected to differ early (the unpatched one) need not play long games
        todo = [shortened(job, args.max_frames) for job in todo]
    threads = []

    def work(job):
        try:
            # six sampled ticks per game: the pools are dumped and compared word by word, which says
            # which fields outside the mask differ between machines in step (rawdiff.tsv)
            samples = sorted({int(job['frames'] * k / 6.5) for k in range(1, 7)} | {1500})
            result = run_job(job, out_root, dumps=samples, sample_dumps=True)
            if result.get('stopped'):
                return
            if result.get('first') is not None and not args.no_rerun:
                # the same game again, cut off shortly after the first difference, with the pools
                # of every machine dumped in the tick before and in the tick of the difference
                first = result['first']
                again = run_job(shortened(job, first + 400), out_root, tag='-again', keep=True, dumps=[first - 1, first])
                if again.get('stopped'):
                    return
                result['repeats'] = 'yes' if again.get('first') == first else 'no (%s)' % again.get('first')
                result['where'] = explain(again['dir'], first, result.get('pair') or '0-1')
            with LOCK:
                with open(jobs_path, 'a') as sink:
                    sink.write(job_row(job, result) + '\n')
                with open(os.path.join(out_root, 'rawdiff.tsv'), 'a') as sink:
                    sink.write('%s\tsampled\t%s\t%s\n' % (job['name'], job['level'], ','.join(map(str, samples))))
                    for row in result.get('rawdiff', []):
                        sink.write('%s\t%s\n' % (job['name'], '\t'.join(str(x) for x in ((row[0], row[1], row[2], '%x' % row[3]) + row[4:]))))
                add_calls(out_root, result.get('calls', {}))
        finally:
            gate.give(job['machines'])

    ALIVE['path'] = os.path.join(out_root, 'alive')
    ALIVE['minutes'] = args.alive_minutes
    open(ALIVE['path'], 'a').close()
    os.utime(ALIVE['path'])
    for job in todo:
        if os.path.exists(os.path.join(out_root, 'stop')) or (deadline and time.time() > deadline) or abandoned():
            break
        gate.take(job['machines'])
        if os.path.exists(os.path.join(out_root, 'stop')) or (deadline and time.time() > deadline) or abandoned():
            gate.give(job['machines'])
            break
        thread = threading.Thread(target=work, args=(job,))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    return 0


# ---- twin: one arm against another, the same games, row for row -----------------------------------
NEW_IN_TEST = re.compile(r'^(p\dmode|l_strafe\w+)$')        # columns a reference program has no meaning for


def compare_logs(path_a, path_b):
    """Two tick logs of the same machine in the same game played by two programs: (rows in a,
    rows in b, first tick at which a deciding column differs, those columns, first tick at
    which any column differs, those columns).  Deciding: every shared column but the local
    ones (l_...), the followed ones and the ones of NEW_IN_TEST."""
    ha, ra = rows_of(path_a)
    hb, rb = rows_of(path_b)
    shared = [c for c in ha if c in hb and c != 'frame' and not NEW_IN_TEST.match(c)]
    index = [(c, ha.index(c), hb.index(c), not c.startswith('l_') and not is_soft(c)) for c in shared]
    count_a = count_b = 0
    first_hard = first_any = None
    cols_hard, cols_any = [], []
    while True:
        a = next(ra, None)
        b = next(rb, None)
        count_a += a is not None
        count_b += b is not None
        if a is None or b is None:
            break
        if first_hard is not None:
            continue
        if a[0] != b[0]:
            first_hard = first_any = min(a[0], b[0])
            cols_hard = cols_any = ['net']
            continue
        differing = [(c, hard) for c, x, y, hard in index if a[1][x] != b[1][y]]
        if differing and first_any is None:
            first_any, cols_any = a[0], [c for c, _ in differing]
        hard = [c for c, h in differing if h]
        if hard:
            first_hard, cols_hard = a[0], hard
    return count_a, count_b, first_hard, cols_hard, first_any, cols_any


def twin(args, levels, trees):
    """Every seed is played by --ref and by --arm; each machine's tick log of the one is compared
    with the same machine's of the other, column by column, tick by tick."""
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)
    first, count = (int(x) for x in args.seeds.split(':'))
    path = os.path.join(out_root, 'twin.tsv')
    done = set()
    if os.path.exists(path):
        done = {int(l.split('\t')[0]) for l in open(path) if l.split('\t')[0].isdigit()}
    else:
        with open(path, 'w') as sink:
            sink.write('seed\tmachines\tlevel\tframes\tbus\tticks_ref\tticks_test\tfirst_in_ref\tfirst_in_test\trows\tidentical\t'
                       'first_deciding\tcolumns\tfirst_any\tcolumns_any\tdropped\n')
    gate = Gate(os.path.join(out_root, 'limit.txt'), args.instances)
    ALIVE['path'] = os.path.join(out_root, 'alive')
    ALIVE['minutes'] = args.alive_minutes
    open(ALIVE['path'], 'a').close()
    os.utime(ALIVE['path'])
    threads = []
    slots = threading.Semaphore(2)

    def work(seed):
        job = make_job(seed, args.arm, levels, trees)
        if args.max_frames:
            job = shortened(job, args.max_frames)
        n = job['machines']
        results = {}

        def play(arm):
            gate.take(n)
            try:
                results[arm] = run_job(dict(job, arm=arm, name='%s-%d' % (arm, seed)), out_root, keep=True)
            finally:
                gate.give(n)
        pair = [threading.Thread(target=play, args=(arm,)) for arm in (args.ref, args.arm)]
        for t in pair:
            t.start()
        for t in pair:
            t.join()
        ref, test = results.get(args.ref, {}), results.get(args.arm, {})
        if ref.get('stopped') or test.get('stopped') or not ref or not test:
            return
        rows = 0
        worst_hard = worst_any = None
        cols_hard, cols_any = [], []
        equal_length = True
        for m in range(n):
            try:
                ca, cb, fh, ch, fa, cany = compare_logs(os.path.join(ref['dir'], 'm%d.tick.tsv' % m), os.path.join(test['dir'], 'm%d.tick.tsv' % m))
            except (OSError, ValueError, StopIteration) as error:
                fh, ch, fa, cany, ca, cb = -1, [repr(error)[:80]], -1, [], 0, 1
            rows += min(ca, cb)
            equal_length = equal_length and ca == cb
            if fh is not None and (worst_hard is None or fh < worst_hard):
                worst_hard, cols_hard = fh, ['m%d:%s' % (m, c) for c in ch]
            if fa is not None and (worst_any is None or fa < worst_any):
                worst_any, cols_any = fa, ['m%d:%s' % (m, c) for c in cany]
        identical = worst_hard is None and equal_length
        with LOCK:
            with open(path, 'a') as sink:
                sink.write('\t'.join(str(x) for x in (
                    seed, n, job['level'], job['frames'], job['bus'], ref.get('ticks', 0), test.get('ticks', 0),
                    ref.get('first') or '', test.get('first') or '', rows, 'yes' if identical else 'NO',
                    '' if worst_hard is None else worst_hard, ' '.join(cols_hard)[:300],
                    '' if worst_any is None else worst_any, ' '.join(cols_any)[:300], test.get('dropped') or '')) + '\n')
        if identical and worst_any is None:
            for r in (ref, test):
                shutil.rmtree(r['dir'], ignore_errors=True)

    for seed in range(first, first + count):
        if seed in done:
            continue
        if os.path.exists(os.path.join(out_root, 'stop')) or abandoned():
            break
        # two seeds at a time: their four games share the instances the gate allows
        slots.acquire()
        thread = threading.Thread(target=lambda seed=seed: (work(seed), slots.release()))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    return 0


def report(dirs):
    names = {}
    for path in riglib.symbol_files():
        for line in open(path, errors='replace'):
            fields = line.rstrip('\n').split('\t')
            if len(fields) >= 2 and not line.startswith('#'):
                try:
                    names.setdefault(int(fields[0], 16), fields[1])
                except ValueError:
                    pass
    for directory in dirs:
        rows = []
        path = os.path.join(directory, 'jobs.tsv')
        header = None
        for line in open(path):
            fields = line.rstrip('\n').split('\t')
            if header is None:
                header = fields
                continue
            row = dict(zip(header, fields))
            if not row['name'].endswith('-again'):
                rows.append(row)
        ticks = sum(int(r['ticks']) for r in rows)
        machine_ticks = sum(int(r['ticks']) * int(r['machines']) for r in rows)
        differ = [r for r in rows if r['first']]
        print('%s: %d jobs, %d ticks compared (%d machine-ticks), %d with a deciding difference, %d dropped a peer, %d timed out, %d errors' % (
            directory, len(rows), ticks, machine_ticks, len(differ),
            sum(1 for r in rows if r['dropped'] or 'held dropped' in r.get('notes', '')),
            sum(1 for r in rows if r['timed_out'] == '1'), sum(1 for r in rows if r['error'])))
        by = {}
        for r in rows:
            for key in ('machines', 'char_level', 'bus', 'level'):
                e = by.setdefault((key, r[key].split(',stallat')[0] + (' +outage' if 'stallat' in r[key] else '')), [0, 0, 0])
                e[0] += 1
                e[1] += int(r['ticks'])
                e[2] += bool(r['first'])
            for cls in r['classes'].split('+'):
                e = by.setdefault(('class', cls), [0, 0, 0])
                e[0] += 1
                e[1] += int(r['ticks'])
                e[2] += bool(r['first'])
        for (key, value), e in sorted(by.items()):
            print('  %-10s %-34s jobs %4d ticks %9d differ %d' % (key, value, e[0], e[1], e[2]))
        classes = {}
        for r in differ:
            classes.setdefault(r['class'], []).append(r)
        for name, members in sorted(classes.items(), key=lambda item: -len(item[1])):
            print('  class [%s]: %d jobs; first: %s' % (name, len(members), ', '.join('%s@%s' % (r['seed'], r['first']) for r in members[:12])))
        calls = os.path.join(directory, 'calls.tsv')
        if os.path.exists(calls):
            table = {}
            for line in open(calls):
                address, count = line.split()
                table[int(address, 16)] = int(count)
            by_name = {names[a]: n for a, n in table.items() if a in names}
            print('  functions entered: %d (%d of them named); calls are counted on every machine, the prediction copy\'s included' % (
                len(table), len(by_name)))
            print('  ' + '; '.join('%s %d' % (name, by_name.get(name, 0)) for name in COVERAGE))
            for title, pattern in (('skill and spell objects run', r'^(Spell|Cast)\w+_run$'), ('object classes run', r'^\w+_run$')):
                hit = sorted((n, c) for n, c in by_name.items() if re.match(pattern, n))
                every = sorted(n for n in set(names.values()) if re.match(pattern, n))
                print('  %s: %d of %d named' % (title, len(hit), len(every)))
                print('    ' + ' '.join('%s:%d' % (n.replace('_run', ''), c) for n, c in hit))
                print('    never: ' + ' '.join(n.replace('_run', '') for n in every if n not in by_name))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run', 'one', 'twin'):
        p = sub.add_parser(name)
        p.add_argument('--arm', default='fix26')
        p.add_argument('--out', default=os.path.join(OUT, 'farm'))
        p.add_argument('--seeds', default='1000:10')
        p.add_argument('--instances', type=int, default=6)
        p.add_argument('--hours', type=float, default=0)
        p.add_argument('--no-rerun', action='store_true')
        p.add_argument('--max-frames', type=int, default=0)
        p.add_argument('--seed', type=int)
        p.add_argument('--frames', type=int)
        p.add_argument('--tag', default='')
        p.add_argument('--program')
        p.add_argument('--dump', default='')
        p.add_argument('--lines')
        p.add_argument('--columns')
        p.add_argument('--env', action='append', default=[])
        p.add_argument('--keep', action='store_true')
        p.add_argument('--ref', help='twin: the program the --arm program is compared with, game by game')
        p.add_argument('--strafe', default='none', help='whose driver uses the strafe mode: all, mixed, none, or machine numbers 0,2')
        p.add_argument('--strafe-spec', default='', help='appended to SOAK_STRAFE: ,rate=N and / or ,at=blank')
        p.add_argument('--survive', action='store_true', help='one: machines that leave do not end the game for the others, '
                                                              'and pairs are compared on after a drop')
        p.add_argument('--menv', action='append', default=[], help='one: M:K=V, an environment variable for machine M alone')
        p.add_argument('--level', help='one: this start level instead of the seed\'s')
        p.add_argument('--machines', type=int, help='one: this many machines instead of the seed\'s')
        p.add_argument('--bus', help='one: this bus instead of the seed\'s (none, or delay=N,jitter=N,loss=N)')
        p.add_argument('--directed', help='one: a file of script lines played after the level is entered, in place of the '
                                          'random input (A: / B: tags for the confirming machine / the others, %%M the machine); '
                                          '--frames frames of waiting follow')
        p.add_argument('--alive-minutes', type=float, default=45.0,
                       help='run: the farm stops itself when <out>/alive has not been touched for so long')
    p = sub.add_parser('report')
    p.add_argument('dirs', nargs='+')
    args = parser.parse_args()
    if args.command == 'report':
        return report(args.dirs)
    image = Image(os.path.join(ROOT, 'SLUS_209.73'))
    levels = level_names(image)
    trees = skill_trees()
    if args.command == 'plan':
        first, count = (int(x) for x in args.seeds.split(':'))
        for seed in range(first, first + count):
            print(describe(make_job(seed, args.arm, levels, trees)))
        return 0
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('set RTA_DISC to your disc image')
    if args.command == 'one':
        job = make_job(args.seed, args.arm, levels, trees)
        if args.frames:     # a shorter (or longer) run of the same game: the same segments, cut off
            if args.frames > job['frames']:
                job = dict(job, segments=job['segments'] + [(args.frames - job['frames'], job['segments'][-1][1])], frames=args.frames)
            job = shortened(job, args.frames)
        if args.level:
            job = dict(job, level=args.level)
        if args.bus:
            job = dict(job, bus=args.bus)
        if args.machines:
            players = (job['players'] * 4)[:args.machines]
            job = dict(job, machines=args.machines, players=players)
        job = with_strafe(job, args.strafe, args.strafe_spec)
        if args.survive:
            job = dict(job, survive=True)
        if args.menv:
            menv = {}
            for item in args.menv:
                who, pair = item.split(':', 1)
                menv.setdefault(int(who), {}).update([pair.split('=', 1)])
            job = dict(job, menv=menv)
        if args.directed:
            job = dict(job, directed=[l for l in open(args.directed).read().splitlines() if l.strip() and not l.startswith('#')])
        extra = open(args.lines).read().splitlines() if args.lines else []
        columns = [l.strip() for l in open(args.columns) if l.strip() and not l.startswith('#')] if args.columns else []
        env = dict(item.split('=', 1) for item in args.env)
        dumps = [int(t) for t in args.dump.split(',') if t]
        os.makedirs(os.path.abspath(args.out), exist_ok=True)
        result = run_job(job, os.path.abspath(args.out), program=args.program, tag=args.tag, keep=True,
                         extra_lines=extra, extra_env=env, extra_columns=columns, dumps=dumps)
        print(describe(job))
        print(job_row(job, result).replace('\t', ' | '))
        return 0
    if args.command == 'twin':
        return twin(args, levels, trees)
    return farm(args, levels, trees)


if __name__ == '__main__':
    sys.exit(main())
