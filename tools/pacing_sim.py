#!/usr/bin/env python3
"""pacing_sim.py -- a runnable model of the lockstep pacing ("lag") rules of
Champions: Return to Arms (SLUS-20973 v2.00).

READ THIS FIRST
    This is a MODEL, and it is UNVALIDATED.  Every rule in it was written down from a
    static reading of the executable (net_main 0x132e90, the receiver 0x13b5d0, the sender
    0x137d60, engine_frameStep 0x19e3a8, the stick codec 0x13c450 / 0x13c970).  Nothing in
    it has been compared with a running game.  The numbers it prints are predictions of the
    model, not measurements.  docs/issues/lag.md lists the rules with their addresses, says
    which parts are read from the code and which are assumptions of the model, and says how
    to check it on two running copies.

    The file contains no game code or data: only the counters, comparisons and constants
    described in docs/issues/lag.md, re-expressed as a simulation.

WHAT IS MODELLED (per machine, once per rendered frame = one "call" of net_main)
    1. take every datagram that has arrived
    2. decide whether to HOLD (skip sampling the pad): cap, equalise and trim rules
    3. if not held, append `step` input frames (step = 1, or 2 in half-rate display mode)
    4. send one input packet to the peer whose turn it is in the send rotation; a packet
       repeats every frame the addressee has not acknowledged
    5. count the frames for which input from every machine is present ("ready");
       run min(ready, step) simulation frames, or none (a STALLED call)
    The link between each pair of machines has a one-way latency, jitter, loss and optional
    loss bursts and outages.  A machine can run slowly (in-game frame cost, or an emulator
    below full speed) or freeze for a while.

ASSUMPTIONS THAT ARE NOT READ FROM THE CODE
    - the link: jitter is an exponentially distributed extra delay; losses are independent
      or come in bursts; packets that arrive while a machine is frozen are all still there
      when it wakes up
    - a call happens at the start of each rendered frame and takes no time
    - a frame that needs more than one display field takes a whole number of fields; the
      switch between full-rate and half-rate display follows docs/mainloop.md section 6
    - a peer entry starts with "newest frame received", reported lead and reported
      simulation frame all 0

WHAT IS NOT MODELLED
    Dropping/kicking a peer (the model only warns when the 900-call silence limit would
    have been reached), level changes, GAME MESSAGES, the sync check, packet sizes, the
    CPU cost of prediction, and anything the simulation itself does.  Because game
    messages are missing, the model cannot see that a send cycle with a packet in every
    call would stop them from being sent; the tool prints a warning for such a setting.

TERMS
    lead     g_localInputFrame - g_netFrame at the end of a call, in frames.  With one
             simulation frame per call, input sampled now is simulated `lead` calls later.
    stalled  a call that ran no simulation frame (the world freezes for one picture).
    held     a call that sampled no input (the local player's prediction copy does not
             advance for one picture).

USAGE (standard library only)
    python3 tools/pacing_sim.py run --latency 30 --loss 2 --jitter 4      # over time + summary
    python3 tools/pacing_sim.py run --freeze B:20:1.0 --duration 90 --bucket 2
    python3 tools/pacing_sim.py run --players 3 --slow C:20:30:30 --set eq_calls=1
    python3 tools/pacing_sim.py compare --outage 20:1 \\
            --variant fast:eq_calls=8,trim_calls=12 --variant cap14:cap=14
    python3 tools/pacing_sim.py compare --emu B:10:60:90 --variant "A only:eq_calls=1@A"
    python3 tools/pacing_sim.py sweep cap 14,20,28,38 --players 4 --latency 60
    python3 tools/pacing_sim.py cases --brief         # the tables quoted in docs/issues/lag.md
    python3 tools/pacing_sim.py cases outage1s --runs 5
    python3 tools/pacing_sim.py stick                 # stick codec step response
    python3 tools/pacing_sim.py words eq_calls=1 trim_min=4   # instruction words for constants

    Machines are named A, B, C, D.  Times are seconds, latencies milliseconds.
    Constants (for --set / --variant / sweep / words): cap, eq_thresh, eq_calls,
    trim_calls, trim_min, trim_reset, send1, send2, send3 (send cycle in calls for 1, 2, 3
    remote peers), modem.  A constant followed by @A applies to that machine only (pacing
    is per machine).  The same --seed gives the same clock offsets and start phases
    whatever the constants are, and the same packet losses as long as the send cycle is
    unchanged, so variants are compared on like conditions.
"""
import argparse
import heapq
import math
import random
import struct
import sys

NAMES = 'ABCD'

# --------------------------------------------------------------------------------------
# Constants of the pacing rules.  Defaults are the values in the executable; the comment
# gives the address of the instruction or data word that holds each one.
# --------------------------------------------------------------------------------------

DEFAULTS = {
    'cap':        38,   # hold while lif - lowest sim frame > cap       0x133554  slti ..,39
    'eq_thresh':   5,   # own lead this far above the smallest lead...  0x13354c  slti ..,5
    'eq_calls':   31,   # ...for this many calls in a row -> hold once  0x133574  slti ..,31
    'trim_calls': 62,   # length of the trim window in calls            0x1335c0  slti ..,61
    'trim_min':    3,   # hold once if min ready in window >= this      0x1335e4  slti ..,3
    'trim_reset': 100,  # value the window minimum is reset to          0x1335d8  addiu ..,100
    'min_lif':     3,   # never hold while lif < this                   0x133600  slti ..,3
    'send1':       2,   # send cycle (calls) with 1 remote peer         data 0x4027ec
    'send2':       4,   # ... 2 remote peers                            data 0x4027f0
    'send3':       6,   # ... 3 remote peers                            data 0x4027f4
    'modem':       0,   # 1: cycle += cycle/2 (UART modem driver)       0x1337e0
    'max_step':    2,   # engine_frameStep() never returns more         0x19e3a8
}

# How each patchable constant maps to a word in the executable (for the `words` command).
# (address, base word with a zero immediate, function from value to immediate, description)
WORDS = {
    'cap':        (0x133554, 0x28420000, lambda v: v + 1, 'slti v0,v0,cap+1'),
    'eq_thresh':  (0x13354c, 0x2a240000, lambda v: v,     'slti a0,s1,eq_thresh'),
    'eq_calls':   (0x133574, 0x28620000, lambda v: v,     'slti v0,v1,eq_calls'),
    'trim_calls': (0x1335c0, 0x28630000, lambda v: v - 1, 'slti v1,v1,trim_calls-1'),
    'trim_min':   (0x1335e4, 0x28420000, lambda v: v,     'slti v0,v0,trim_min'),
    'trim_reset': (0x1335d8, 0x24040000, lambda v: v,     'addiu a0,zero,trim_reset'),
    'send1':      (0x4027ec, 0x00000000, lambda v: v,     'data word, send cycle for 1 remote'),
    'send2':      (0x4027f0, 0x00000000, lambda v: v,     'data word, send cycle for 2 remotes'),
    'send3':      (0x4027f4, 0x00000000, lambda v: v,     'data word, send cycle for 3 remotes'),
}
ORIGINAL_WORDS = {
    'cap': 0x28420027, 'eq_thresh': 0x2a240005, 'eq_calls': 0x2862001f,
    'trim_calls': 0x2863003d, 'trim_min': 0x28420003, 'trim_reset': 0x24040064,
    'send1': 0x00000002, 'send2': 0x00000004, 'send3': 0x00000006,
}


def s8(v):
    v &= 0xff
    return v - 256 if v >= 128 else v


# --------------------------------------------------------------------------------------
# Network link (one direction)
# --------------------------------------------------------------------------------------

class Link:
    """One direction of a link.  latency and jitter in seconds, loss as a fraction.
    Jitter is an extra delay drawn from an exponential distribution with mean `jitter`,
    cut off at 8 x jitter (an assumption of the model).  With burst > 0 losses come in
    bursts: the link alternates between a good state and a bad state in which everything
    is lost; bad periods last `burst` seconds on average and cover `loss` of the time."""

    def __init__(self, latency, jitter, loss, burst, rng):
        self.latency = latency
        self.jitter = jitter
        self.loss = loss
        self.burst = burst
        self.rng = rng
        self.outages = []          # (t0, t1): everything sent in between is lost
        self.bad = False
        self.until = 0.0
        self.sent = 0
        self.lost = 0
        if burst > 0 and 0 < loss < 1:
            self.good_mean = burst * (1.0 - loss) / loss
            self.until = rng.expovariate(1.0 / self.good_mean)

    def transit(self, t):
        """Return the arrival time of a packet sent at t, or None if it is lost."""
        self.sent += 1
        for t0, t1 in self.outages:
            if t0 <= t < t1:
                self.lost += 1
                return None
        if self.burst > 0 and 0 < self.loss < 1:
            while t >= self.until:
                self.bad = not self.bad
                mean = self.burst if self.bad else self.good_mean
                self.until += self.rng.expovariate(1.0 / mean)
            if self.bad:
                self.lost += 1
                return None
        elif self.loss > 0 and self.rng.random() < self.loss:
            self.lost += 1
            return None
        extra = 0.0
        if self.jitter > 0:
            extra = min(self.rng.expovariate(1.0 / self.jitter), 8.0 * self.jitter)
        return t + self.latency + extra


# --------------------------------------------------------------------------------------
# What one machine remembers about another (the pacing fields of a peer entry)
# --------------------------------------------------------------------------------------

class Peer:
    __slots__ = ('idx', 'newest', 'ack', 'lead', 'sim', 'silence', 'max_silence')

    def __init__(self, idx):
        self.idx = idx
        self.newest = 0      # +0x44bc newest frame received from this peer
        self.ack = 1         # +0x44c0 newest of our frames it acknowledged (1 at launch)
        self.lead = 0        # +0x44c4 its lead as last reported
        self.sim = 0         # +0x44c8 its simulation frame as last reported
        self.silence = 0     # +0x44cc calls since its last accepted packet
        self.max_silence = 0


# --------------------------------------------------------------------------------------
# One machine
# --------------------------------------------------------------------------------------

class Machine:
    def __init__(self, idx, n, consts, sim):
        self.idx = idx
        self.name = NAMES[idx]
        self.c = dict(consts)
        self.sim = sim
        self.peers = [Peer(j) for j in range(n) if j != idx]     # slot order
        self.peer_of = {p.idx: p for p in self.peers}
        self.inbox = []                # heap of (arrival, seq, packet)
        # lockstep state (net_gameInit 0x1397a0 sets both frame counters to 1)
        self.lif = 1                   # g_localInputFrame 0x4027a4
        self.nf = 1                    # g_netFrame        0x4027ac
        self.eq = 0                    # 0x4027dc
        self.trim = 0                  # 0x4027e4
        self.min_ready = self.c['trim_reset']   # 0x4027e0 (initial data value 100)
        self.phase = 0                 # 0x4027b4
        self.stall_run = 0             # 0x4027d0
        # display pacing (docs/mainloop.md section 6)
        self.half_rate = False
        self.late = 0
        self.spare = 0.0
        self.step = 1
        # timeline
        self.base_cost = 0.7           # fields of work per frame when nothing is wrong
        self.cost_segs = []            # (t0, t1, cost in fields)
        self.speed_segs = []           # (t0, t1, speed factor)
        self.freezes = []              # (t0, duration)
        self.drift = 0.0               # clock error, fraction
        # records
        self.sample_time = [None]      # index = frame number
        self.log = []                  # per call: (t, lead, ticks, held bits, delay sum)
        self.remote_delay_sum = 0.0    # own input -> another machine's simulation
        self.remote_delay_n = 0
        self.pkt_frames = 0
        self.pkt_count = 0
        self.max_stall_run = 0

    # ---- display pacing --------------------------------------------------------------
    def _seg(self, segs, t, default):
        for t0, t1, v in segs:
            if t0 <= t < t1:
                return v
        return default

    def frame_time(self, t):
        """Wall-clock length of the frame that starts at t; also sets the step of the next
        call.  Full rate: a frame takes ceil(cost) fields and always stands for one step;
        the 32nd late frame in a row switches to half rate.  Half rate: a frame takes at
        least two fields and stands for min(2, fields) steps; frames that needed less than
        one field bank the spare time and more than three fields of it switch back."""
        cost = self._seg(self.cost_segs, t, self.base_cost)
        if self.half_rate:
            if cost < 1.0:
                self.spare += 1.0 - cost
                if self.spare > 3.0:
                    self.half_rate = False
                    self.spare = 0.0
            else:
                self.spare = 0.0
        if self.half_rate:
            fields = max(2, int(math.ceil(cost - 1e-9)))
        else:
            fields = max(1, int(math.ceil(cost - 1e-9)))
            if cost > 1.0:
                self.late += 1
                if self.late >= 32:
                    self.half_rate = True
                    self.late = 0
            else:
                self.late = 0
        self.step = min(self.c['max_step'], fields) if self.half_rate else 1
        speed = self._seg(self.speed_segs, t, 1.0)
        dur = fields * self.sim.field / speed * (1.0 + self.drift)
        for t0, d in self.freezes:
            if t <= t0 < t + dur:
                dur += d
        return dur

    # ---- receiver: the pacing-relevant part of 0x13b5d0 ------------------------------
    def receive(self, pkt):
        src, last, hdr9, count, ack8 = pkt
        p = self.peer_of[src]
        p.silence = 0                               # 0x13b750
        p.sim = last - hdr9                         # 0x13b790
        p.lead = last - p.sim                       # 0x13b7ac
        if p.newest < last:                         # 0x13b7a4: nothing else is read otherwise
            a = last + ack8
            if p.ack < a:                           # 0x13b7e0
                p.ack = a
            first = last - count + 1
            if first <= p.newest + 1:               # 0x13b800: else discarded
                p.newest = last                     # 0x13be6c

    # ---- one call of net_main(0, 0) --------------------------------------------------
    def call(self, t):
        c = self.c
        inbox = self.inbox
        while inbox and inbox[0][0] <= t:
            self.receive(heapq.heappop(inbox)[2])
        for p in self.peers:                        # silence counters, 0x133060
            p.silence += 1
            if p.silence > p.max_silence:
                p.max_silence = p.silence

        # smallest lead and lowest simulation frame, own and reported (0x13334c-0x1333f0)
        lead0 = self.lif - self.nf
        min_lead = lead0
        min_sim = self.nf
        for p in self.peers:
            if p.lead < min_lead:
                min_lead = p.lead
            if p.sim < min_sim:
                min_sim = p.sim
        excess = lead0 - min_lead

        held = 0
        if self.lif - min_sim > c['cap']:           # cap, 0x133554
            held |= 1
        if excess < c['eq_thresh']:                 # equalise, 0x13354c-0x133594
            self.eq = 0
        else:
            self.eq += 1
            if self.eq >= c['eq_calls']:
                self.eq = 0
                held |= 2
        old = self.trim                             # trim, 0x1335b4-0x1335ec
        self.trim = old + 1
        if old >= c['trim_calls'] - 1:
            self.trim = 0
            m = self.min_ready
            self.min_ready = c['trim_reset']
            if m >= c['trim_min']:
                held |= 4
        if self.lif < c['min_lif']:                 # 0x133600
            held = 0

        if not held:                                # sample, 0x133610-0x1336b8
            for _ in range(self.step):
                self.sample_time.append(t)
                self.lif += 1

        # send rotation, 0x133764-0x134204
        n = len(self.peers)
        cycle = c['send%d' % n]
        if c['modem']:
            cycle += cycle >> 1
        last = self.lif - 1
        for k, p in enumerate(self.peers):
            if self.phase == (k * cycle) // n:
                first = p.ack
                pkt = (self.idx, last, (last - self.nf) & 0xff,
                       (last - first + 1) & 0xff, s8(p.newest - last))
                self.pkt_frames += last - first + 1
                self.pkt_count += 1
                self.sim.deliver(self.idx, p.idx, pkt, t)
        self.phase += 1
        if self.phase >= cycle:
            self.phase = 0

        # ready scan and ticks, 0x1342a8-0x1343dc
        limit = self.lif - self.nf - 1
        avail = limit
        for p in self.peers:
            a = p.newest - self.nf + 1
            if a < avail:
                avail = a
        ready = avail if avail > 0 else 0
        if ready < self.min_ready:
            self.min_ready = ready
        ticks = ready if ready < self.step else self.step
        dsum = 0.0
        if ticks < 1:
            self.stall_run += 1
            if self.stall_run > self.max_stall_run:
                self.max_stall_run = self.stall_run
        else:
            self.stall_run = 0
            machines = self.sim.machines
            count = t >= self.sim.sc.warmup
            for _ in range(ticks):
                f = self.nf
                dsum += t - self.sample_time[f]
                if count:
                    for m in machines:
                        if m is not self:
                            m.remote_delay_sum += t - m.sample_time[f]
                            m.remote_delay_n += 1
                self.nf = f + 1
        self.log.append((t, self.lif - self.nf, ticks, held, dsum))


# --------------------------------------------------------------------------------------
# The whole session
# --------------------------------------------------------------------------------------

class Scenario:
    """Everything that describes one experiment except the pacing constants."""

    def __init__(self, players=2, duration=120.0, latency=30.0, jitter=3.0, loss=0.0,
                 burst=0.0, links=None, slow=(), emu=(), freeze=(), outage=(), drift=(),
                 field_hz=59.94, base_cost=0.7, warmup=10.0, cold=False):
        self.players = players
        self.duration = duration
        self.latency = latency           # ms, one way
        self.jitter = jitter             # ms
        self.loss = loss                 # percent
        self.burst = burst               # ms, mean loss-burst length (0: independent loss)
        self.links = links or {}         # {(a, b): dict(latency=, jitter=, loss=, burst=)}
        self.slow = list(slow)           # (machine, t0, t1, fps)     in-game frame cost
        self.emu = list(emu)             # (machine, t0, t1, percent) emulator speed
        self.freeze = list(freeze)       # (machine, t0, seconds)
        self.outage = list(outage)       # (t0, seconds, a or None, b or None)
        self.drift = list(drift)         # (machine, ppm)
        self.field_hz = field_hz
        self.base_cost = base_cost
        self.warmup = warmup
        self.cold = cold

    def disturbance(self):
        """(start, end) of the scripted disturbances, or None."""
        spans = [(t0, t1) for _, t0, t1, _ in self.slow]
        spans += [(t0, t1) for _, t0, t1, _ in self.emu]
        spans += [(t0, t0 + d) for _, t0, d in self.freeze]
        spans += [(t0, t0 + d) for t0, d, _, _ in self.outage]
        if not spans:
            return None
        return min(s for s, _ in spans), max(e for _, e in spans)


class Sim:
    def __init__(self, sc, consts, seed):
        self.sc = sc
        self.field = 1.0 / sc.field_hz
        self.seq = 0
        n = sc.players
        self.machines = []
        for i in range(n):
            cc = dict(DEFAULTS)
            for key, val, who in consts:
                if who is None or who == i:
                    cc[key] = val
            self.machines.append(Machine(i, n, cc, self))
        start = random.Random(seed * 1000 + 999)
        self.links = {}
        for a in range(n):
            for b in range(n):
                if a == b:
                    continue
                o = sc.links.get((a, b)) or sc.links.get((b, a)) or {}
                self.links[(a, b)] = Link(o.get('latency', sc.latency) / 1000.0,
                                          o.get('jitter', sc.jitter) / 1000.0,
                                          o.get('loss', sc.loss) / 100.0,
                                          o.get('burst', sc.burst) / 1000.0,
                                          random.Random(seed * 1000 + a * 10 + b))
        for t0, d, a, b in sc.outage:
            for (x, y), link in self.links.items():
                if a is None or (x, y) in ((a, b), (b, a)):
                    link.outages.append((t0, t0 + d))
        for m in self.machines:
            m.base_cost = sc.base_cost
            for who, t0, t1, fps in sc.slow:
                if who == m.idx:
                    m.cost_segs.append((t0, t1, 60.0 / fps - 0.4))
            for who, t0, t1, pct in sc.emu:
                if who == m.idx:
                    m.speed_segs.append((t0, t1, pct / 100.0))
            for who, t0, d in sc.freeze:
                if who == m.idx:
                    m.freezes.append((t0, d))
            for who, ppm in sc.drift:
                if who == m.idx:
                    m.drift = ppm * 1e-6
        # The same seed gives the same clock offsets and start values whatever the
        # constants are, so variants are compared on identical conditions.
        self.first_call = [start.random() * self.field for _ in range(n)]
        for m in self.machines:
            u_trim, u_phase = start.random(), start.random()
            if not sc.cold:
                # these two counters are not reset when a game starts (only net_main
                # writes them), so their starting values are arbitrary
                m.trim = int(u_trim * m.c['trim_calls'])
                m.phase = int(u_phase * m.c['send%d' % (n - 1)])

    def deliver(self, src, dst, pkt, t):
        arrival = self.links[(src, dst)].transit(t)
        if arrival is not None:
            self.seq += 1
            heapq.heappush(self.machines[dst].inbox, (arrival, self.seq, pkt))

    def run(self):
        q = [(self.first_call[m.idx], m.idx) for m in self.machines]
        heapq.heapify(q)
        end = self.sc.duration
        while q:
            t, i = heapq.heappop(q)
            if t >= end:
                continue
            m = self.machines[i]
            m.call(t)
            heapq.heappush(q, (t + m.frame_time(t), i))
        return self


# --------------------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------------------

def pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    k = min(len(sorted_vals) - 1, max(0, int(math.ceil(q * len(sorted_vals))) - 1))
    return sorted_vals[k]


def machine_stats(m, sc, field):
    """Summary of one machine over [warmup, duration]."""
    t_lo = sc.warmup
    rows = [r for r in m.log if r[0] >= t_lo]
    if not rows:
        rows = m.log
    leads = sorted(r[1] for r in rows)
    ticks = sum(r[2] for r in rows)
    span = max(field, rows[-1][0] - rows[0][0] + field)
    minutes = span / 60.0
    st = {
        'calls': len(rows),
        'lead_mean': sum(leads) / len(leads),
        'lead_p50': pct(leads, 0.50),
        'lead_p95': pct(leads, 0.95),
        'lead_max': leads[-1],
        'delay_ms': 1000.0 * sum(r[4] for r in rows) / ticks if ticks else float('nan'),
        'remote_ms': (1000.0 * m.remote_delay_sum / m.remote_delay_n
                      if m.remote_delay_n else float('nan')),
        'stalls': sum(1 for r in rows if r[2] == 0),
        'held': sum(1 for r in rows if r[3]),
        'held_cap': sum(1 for r in rows if r[3] & 1),
        'held_eq': sum(1 for r in rows if r[3] & 2),
        'held_trim': sum(1 for r in rows if r[3] & 4),
        'speed': 100.0 * ticks / (span / field),
        'max_stall_run': m.max_stall_run,
        'frames_per_pkt': m.pkt_frames / m.pkt_count if m.pkt_count else 0.0,
        'max_silence': max(p.max_silence for p in m.peers),
    }
    st['stalls_pm'] = st['stalls'] / minutes
    st['held_pm'] = st['held'] / minutes
    # After a scripted disturbance: the lead just before it, the highest lead reached,
    # the level it settles at (mean of the last 20 s) and how long after the end of the
    # disturbance the one-second mean first came within one frame of that level.
    d = sc.disturbance()
    st['before'] = st['peak'] = st['recover'] = st['after'] = None
    if d:
        d0, d1 = d
        pre = sorted(r[1] for r in m.log if max(t_lo, d0 - 10.0) <= r[0] < d0)
        post = [r for r in m.log if r[0] >= d0]
        end = [r[1] for r in m.log if r[0] >= sc.duration - 20.0]
        tail = [r for r in m.log if r[0] >= d1]
        if pre and post and end and tail:
            after = sum(end) / len(end)
            st['before'] = pct(pre, 0.5)
            st['after'] = after
            st['peak'] = max(r[1] for r in post)
            st['recover'] = float('inf')
            j = 0
            acc = 0.0
            for i in range(len(tail)):
                while j < len(tail) and tail[j][0] < tail[i][0] + 1.0:
                    acc += tail[j][1]
                    j += 1
                if acc / (j - i) <= after + 1.0:
                    st['recover'] = tail[i][0] - d1
                    break
                acc -= tail[i][1]
    return st


def series(m, bucket, duration):
    """Per-bucket rows: (t, mean lead, max lead, delay ms, stalled, held cap/eq/trim, ticks)."""
    out = []
    n = int(math.ceil(duration / bucket))
    acc = [[0, 0, 0, 0.0, 0, 0, 0, 0, 0] for _ in range(n)]
    for t, lead, ticks, held, dsum in m.log:
        b = acc[min(n - 1, int(t / bucket))]
        b[0] += 1
        b[1] += lead
        b[2] = max(b[2], lead)
        b[3] += dsum
        b[4] += ticks
        b[5] += 1 if ticks == 0 else 0
        b[6] += held & 1
        b[7] += (held >> 1) & 1
        b[8] += (held >> 2) & 1
    for i, b in enumerate(acc):
        if b[0]:
            out.append((i * bucket, b[1] / b[0], b[2],
                        1000.0 * b[3] / b[4] if b[4] else float('nan'),
                        b[5], b[6], b[7], b[8], b[4]))
    return out


def average(stats_list):
    """Average a list of per-run stat dicts for the same machine."""
    out = {}
    for key in stats_list[0]:
        vals = [s[key] for s in stats_list if s[key] is not None]
        if not vals:
            out[key] = None
        elif key in ('lead_max', 'peak', 'max_stall_run', 'max_silence'):
            out[key] = max(vals)
        elif key == 'recover':
            vals.sort()
            out[key] = vals[len(vals) // 2]          # median over runs
        else:
            finite = [v for v in vals if v == v]
            out[key] = sum(finite) / len(finite) if finite else float('nan')
    return out


def run_many(sc, consts, runs, seed):
    """Run `runs` seeds; return ([per-machine averaged stats], last Sim)."""
    per = [[] for _ in range(sc.players)]
    sim = None
    for r in range(runs):
        sim = Sim(sc, consts, seed + r).run()
        for m in sim.machines:
            per[m.idx].append(machine_stats(m, sc, sim.field))
    return [average(p) for p in per], sim


# --------------------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------------------

def fmt_recover(v):
    if v is None:
        return '-'
    if v == float('inf'):
        return 'never'
    return '%.1fs' % v


def fmt_opt(v, f='%.1f'):
    return '-' if v is None else f % v


HEAD = ('%-22s %-2s %6s %4s %4s %7s %7s %6s %5s %6s %6s %8s %7s %6s' %
        ('variant', 'm', 'lead', 'p95', 'max', 'own ms', 'oth ms', 'before', 'peak', 'recov',
         'after', 'stall/m', 'held/m', 'speed'))


def print_rows(label, stats):
    for i, s in enumerate(stats):
        print('%-22s %-2s %6.2f %4d %4d %7.1f %7.1f %6s %5s %6s %6s %8.1f %7.1f %5.1f%%' % (
            label if i == 0 else '', s.get('name', NAMES[i]), s['lead_mean'], s['lead_p95'],
            s['lead_max'], s['delay_ms'], s['remote_ms'], fmt_opt(s['before'], '%d'),
            fmt_opt(s['peak'], '%d'), fmt_recover(s['recover']), fmt_opt(s['after']),
            s['stalls_pm'], s['held_pm'], s['speed']))


def brief_row(stats):
    """One row for a whole game: the machine with the highest mean lead, with stalls and
    holds averaged over the machines, the lowest speed and the slowest recovery."""
    worst = max(range(len(stats)), key=lambda i: stats[i]['lead_mean'])
    agg = dict(stats[worst])
    agg['name'] = NAMES[worst]
    agg['stalls_pm'] = sum(s['stalls_pm'] for s in stats) / len(stats)
    agg['held_pm'] = sum(s['held_pm'] for s in stats) / len(stats)
    agg['speed'] = min(s['speed'] for s in stats)
    rec = [s['recover'] for s in stats if s['recover'] is not None]
    agg['recover'] = max(rec) if rec else None
    peaks = [s['peak'] for s in stats if s['peak'] is not None]
    agg['peak'] = max(peaks) if peaks else None
    agg['lead_max'] = max(s['lead_max'] for s in stats)
    return agg


LEGEND = """columns (all are predictions of the model, not measurements)
  lead     mean lead in frames over the summary period; p95 and max of the same
  own ms   mean time from a pad sample to the simulation frame that uses it, same machine
  oth ms   mean time from a pad sample to the frame that uses it on the other machines
  before   median lead in the 10 s before the scripted disturbance
  peak     highest lead after the disturbance began
  recov    time after the disturbance ended until the one-second mean lead first came
           within one frame of `after` (median of the runs)
  after    mean lead over the last 20 s of the run
  stall/m  calls per minute that ran no simulation frame (includes those the disturbance
           itself forces); held/m: calls per minute that sampled no input
  speed    simulation frames per display field of real time (100% = full speed)"""


BRIEF_NOTE = ('one row per variant: the machine with the highest mean lead; stall/m and held/m '
              'are means over\nthe machines; max, peak and recov are the worst of any machine, '
              'speed the lowest.')


def describe(sc):
    bits = ['%d players' % sc.players, '%g s' % sc.duration,
            'link %g ms one way, jitter %g ms, loss %g%%%s' % (
                sc.latency, sc.jitter, sc.loss,
                ' in %g ms bursts' % sc.burst if sc.burst else '')]
    for (a, b), o in sorted(sc.links.items()):
        bits.append('link %s-%s: %s' % (NAMES[a], NAMES[b], ', '.join(
            '%s %g' % (k, v) for k, v in sorted(o.items()))))
    for who, t0, t1, fps in sc.slow:
        bits.append('%s renders at %g fps from %g to %g s' % (NAMES[who], fps, t0, t1))
    for who, t0, t1, p in sc.emu:
        bits.append('%s runs at %g%% speed from %g to %g s' % (NAMES[who], p, t0, t1))
    for who, t0, d in sc.freeze:
        bits.append('%s freezes for %g s at %g s' % (NAMES[who], d, t0))
    for t0, d, a, b in sc.outage:
        bits.append('%s outage of %g s at %g s' % (
            'total' if a is None else '%s-%s' % (NAMES[a], NAMES[b]), d, t0))
    for who, ppm in sc.drift:
        bits.append('%s clock %+g ppm' % (NAMES[who], ppm))
    return '; '.join(bits)


def send_gap_warning(consts, players):
    """The model has no game messages, so it cannot show this by itself: queued game
    messages are attached to an input frame only in a call where two frames are still
    unsent (0x1336c4-0x1336d4), which at one frame per call means the call before sent
    nothing.  A send cycle with a packet in every call therefore starves them."""
    out = []
    n = players - 1
    for who in [None] + list(range(players)):
        cyc = DEFAULTS['send%d' % n]
        hit = False
        for key, val, w in consts:
            if key == 'send%d' % n and w == who:
                cyc, hit = val, True
        if not hit:
            continue
        if cyc < 1 or len({(k * cyc) // n for k in range(n)}) >= cyc:
            out.append('WARNING: send%d=%d%s sends a packet in every call.  In the game that '
                       'would stop game messages\n         (inventory, shop, dialog, level '
                       'change) from ever being attached to a frame; see docs/issues/lag.md.\n'
                       '         The numbers below ignore that.' % (
                           n, cyc, '' if who is None else '@' + NAMES[who]))
    return out


def describe_consts(consts):
    if not consts:
        return 'original constants'
    return ', '.join('%s=%d%s' % (k, v, '' if w is None else '@' + NAMES[w])
                     for k, v, w in consts)


# --------------------------------------------------------------------------------------
# Command line parsing helpers
# --------------------------------------------------------------------------------------

def mach(s):
    s = s.strip().upper()
    if len(s) != 1 or s not in NAMES:
        raise SystemExit('machine must be one of A B C D, got %r' % s)
    return NAMES.index(s)


def parse_consts(text):
    """'cap=14,eq_calls=8@A' -> [(key, value, machine or None), ...]"""
    out = []
    for part in text.replace(' ', '').split(','):
        if not part:
            continue
        who = None
        if '@' in part:
            part, w = part.split('@', 1)
            who = mach(w)
        if '=' not in part:
            raise SystemExit('expected key=value, got %r' % part)
        key, val = part.split('=', 1)
        if key not in DEFAULTS:
            raise SystemExit('unknown constant %r; known: %s' % (key, ', '.join(DEFAULTS)))
        out.append((key, int(val, 0), who))
    return out


def scenario_from_args(a):
    links = {}
    for spec in a.link or []:
        pair, _, rest = spec.partition(':')
        x, y = pair.split('-')
        d = {}
        for kv in rest.split(','):
            if kv:
                k, v = kv.split('=')
                d[k] = float(v)
        links[(mach(x), mach(y))] = d
    slow = []
    for spec in a.slow or []:
        w, t0, t1, fps = spec.split(':')
        slow.append((mach(w), float(t0), float(t1), float(fps)))
    emu = []
    for spec in a.emu or []:
        w, t0, t1, p = spec.split(':')
        emu.append((mach(w), float(t0), float(t1), float(p)))
    freeze = []
    for spec in a.freeze or []:
        w, t0, d = spec.split(':')
        freeze.append((mach(w), float(t0), float(d)))
    outage = []
    for spec in a.outage or []:
        parts = spec.split(':')
        x = y = None
        if len(parts) > 2:
            x, y = [mach(v) for v in parts[2].split('-')]
        outage.append((float(parts[0]), float(parts[1]), x, y))
    drift = []
    for spec in a.drift or []:
        w, ppm = spec.split(':')
        drift.append((mach(w), float(ppm)))
    return Scenario(players=a.players, duration=a.duration, latency=a.latency,
                    jitter=a.jitter, loss=a.loss, burst=a.burst, links=links, slow=slow,
                    emu=emu, freeze=freeze, outage=outage, drift=drift,
                    field_hz=a.field_hz, base_cost=a.base_cost, warmup=a.warmup,
                    cold=a.cold)


def add_scenario_args(p):
    p.add_argument('--players', type=int, default=2, choices=(2, 3, 4))
    p.add_argument('--duration', type=float, default=120.0, help='seconds simulated')
    p.add_argument('--latency', type=float, default=30.0, help='one-way latency, ms')
    p.add_argument('--jitter', type=float, default=3.0, help='mean extra delay, ms')
    p.add_argument('--loss', type=float, default=0.0, help='packet loss, percent')
    p.add_argument('--burst', type=float, default=0.0,
                   help='mean length of a loss burst in ms (0 = independent losses)')
    p.add_argument('--link', action='append', metavar='A-B:latency=..,jitter=..,loss=..,burst=..',
                   help='override one link (both directions)')
    p.add_argument('--slow', action='append', metavar='M:T0:T1:FPS',
                   help='machine M needs 60/FPS fields per frame between T0 and T1 '
                        '(in-game load; the display-rate rules apply)')
    p.add_argument('--emu', action='append', metavar='M:T0:T1:PCT',
                   help='machine M runs at PCT%% of real time between T0 and T1 '
                        '(an emulator that cannot keep up; the game cannot tell)')
    p.add_argument('--freeze', action='append', metavar='M:T0:SECONDS',
                   help='machine M does nothing for SECONDS starting at T0')
    p.add_argument('--outage', action='append', metavar='T0:SECONDS[:A-B]',
                   help='every packet sent in the window is lost (all links, or one)')
    p.add_argument('--drift', action='append', metavar='M:PPM', help='clock error of machine M')
    p.add_argument('--field-hz', type=float, default=59.94, help='display fields per second')
    p.add_argument('--base-cost', type=float, default=0.7,
                   help='fields of work per frame when nothing is wrong')
    p.add_argument('--warmup', type=float, default=10.0,
                   help='seconds at the start left out of the summary')
    p.add_argument('--cold', action='store_true',
                   help='start the trim window and send phase at 0 instead of at random')
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--runs', type=int, default=1, help='number of seeds to average')


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------

def cmd_run(a):
    sc = scenario_from_args(a)
    consts = []
    for s in a.set or []:
        consts += parse_consts(s)
    print('scenario : ' + describe(sc))
    print('constants: ' + describe_consts(consts))
    print('runs     : %d (seed %d), summary from %g s' % (a.runs, a.seed, sc.warmup))
    for w in send_gap_warning(consts, sc.players):
        print(w)
    stats, sim = run_many(sc, consts, a.runs, a.seed)
    if a.series:
        for m in sim.machines:
            print('\nmachine %s over time (last run), %g s per row: mean and highest lead '
                  'in frames, pad-to-simulation\ndelay, stalled calls, calls held by each '
                  'rule, simulation frames run' % (m.name, a.bucket))
            print('%7s %7s %4s %8s %7s %5s %5s %5s %6s' % (
                't', 'lead', 'max', 'own ms', 'stalled', 'cap', 'equal', 'trim', 'ticks'))
            for row in series(m, a.bucket, sc.duration):
                print('%7.1f %7.2f %4d %8.1f %7d %5d %5d %5d %6d' % row)
    if a.csv:
        with open(a.csv, 'w') as f:
            f.write('machine,t,lead,ticks,held_cap,held_equalise,held_trim\n')
            for m in sim.machines:
                for t, lead, ticks, held, _ in m.log:
                    f.write('%s,%.4f,%d,%d,%d,%d,%d\n' % (
                        m.name, t, lead, ticks, held & 1, (held >> 1) & 1, (held >> 2) & 1))
        print('\nwrote per-call trace of the last run to ' + a.csv)
    print()
    print(HEAD)
    print_rows('run', stats)
    print()
    for i, s in enumerate(stats):
        print('%s: %d calls; held by cap %.0f, equalise %.0f, trim %.0f; longest stall %d calls; '
              '%.1f frames per packet' % (NAMES[i], s['calls'], s['held_cap'], s['held_eq'],
                                          s['held_trim'], s['max_stall_run'],
                                          s['frames_per_pkt']))
        if s['max_silence'] > 900:
            print('   WARNING: %s heard nothing from a peer for %d calls; the game starts '
                  'dropping a peer after 900, which this model does not do' % (
                      NAMES[i], s['max_silence']))
    lost = sum(l.lost for l in sim.links.values())
    sent = sum(l.sent for l in sim.links.values())
    print('packets (last run): %d sent, %d lost (%.2f%%)' % (sent, lost,
                                                           100.0 * lost / max(1, sent)))
    print()
    print(LEGEND)


def run_variants(sc, variants, runs, seed, brief):
    """Print one block of rows per (name, consts) variant for scenario sc."""
    for name, consts in variants:
        for w in send_gap_warning(consts, sc.players):
            print('%s: %s' % (name, w))
    print(HEAD)
    for name, consts in variants:
        stats, _ = run_many(sc, consts, runs, seed)
        print_rows(name, [brief_row(stats)] if brief else stats)


def cmd_compare(a):
    sc = scenario_from_args(a)
    variants = [('original', [])]
    for v in a.variant or []:
        name, _, text = v.partition(':')
        variants.append((name, parse_consts(text)))
    print('scenario : ' + describe(sc))
    print('runs     : %d (seeds %d..%d), summary from %g s' % (
        a.runs, a.seed, a.seed + a.runs - 1, sc.warmup))
    print()
    run_variants(sc, variants, a.runs, a.seed, a.brief)
    print()
    for name, consts in variants[1:]:
        print('%-22s %s' % (name, describe_consts(consts)))
    print()
    if a.brief:
        print(BRIEF_NOTE)
    print(LEGEND)


def cmd_sweep(a):
    sc = scenario_from_args(a)
    if a.key not in DEFAULTS:
        raise SystemExit('unknown constant %r; known: %s' % (a.key, ', '.join(DEFAULTS)))
    who = None if not a.only else mach(a.only)
    base = []
    for text in a.set or []:
        base += parse_consts(text)
    variants = []
    for v in a.values.split(','):
        v = int(v, 0)
        tag = '%s=%d%s' % (a.key, v, '' if who is None else '@' + NAMES[who])
        if v == DEFAULTS[a.key]:
            tag += ' (original)'
        variants.append((tag, base + [(a.key, v, who)]))
    print('scenario : ' + describe(sc))
    if base:
        print('constants: ' + describe_consts(base) + ' in every row')
    print('runs     : %d (seeds %d..%d), summary from %g s' % (
        a.runs, a.seed, a.seed + a.runs - 1, sc.warmup))
    print()
    run_variants(sc, variants, a.runs, a.seed, not a.full)
    print()
    if not a.full:
        print(BRIEF_NOTE)
    print(LEGEND)


# The cases and variants behind the tables in docs/issues/lag.md.
def _cases():
    bb = dict(latency=30.0, jitter=3.0)
    return [
        ('lan', 'two consoles on one LAN',
         Scenario(latency=1.0, jitter=0.2, loss=0.0)),
        ('bb1', 'home broadband, 30 ms one way, 1% loss',
         Scenario(loss=1.0, **bb)),
        ('bb2', 'home broadband, 30 ms one way, 2% loss',
         Scenario(loss=2.0, **bb)),
        ('bb2x3', 'three players, 30 ms one way, 2% loss',
         Scenario(players=3, loss=2.0, **bb)),
        ('bb2x4', 'four players, 30 ms one way, 2% loss',
         Scenario(players=4, loss=2.0, **bb)),
        ('wifi', '30 ms one way, 2% loss in bursts of 150 ms',
         Scenario(loss=2.0, burst=150.0, **bb)),
        ('far', 'long distance, 110 ms one way, jitter 8 ms, 1% loss',
         Scenario(latency=110.0, jitter=8.0, loss=1.0)),
        ('far4', 'four players, 110 ms one way, jitter 8 ms, 1% loss',
         Scenario(players=4, latency=110.0, jitter=8.0, loss=1.0)),
        ('slow30', 'B renders at 30 fps for 10 s (in-game load), 1% loss',
         Scenario(loss=1.0, slow=[(1, 20.0, 30.0, 30.0)], **bb)),
        ('slow20', 'B renders at 20 fps for 10 s (in-game load), 1% loss',
         Scenario(loss=1.0, slow=[(1, 20.0, 30.0, 20.0)], **bb)),
        ('emu90', 'B runs at 90% speed for 40 s (emulator), 1% loss',
         Scenario(loss=1.0, emu=[(1, 20.0, 60.0, 90.0)], **bb)),
        ('freeze1s', 'B freezes for one second, 1% loss',
         Scenario(loss=1.0, freeze=[(1, 20.0, 1.0)], **bb)),
        ('outage1s', 'the link drops everything for one second, 1% loss',
         Scenario(loss=1.0, outage=[(20.0, 1.0, None, None)], **bb)),
        ('outage1s4', 'four players, every link drops everything for one second, 1% loss',
         Scenario(players=4, loss=1.0, outage=[(20.0, 1.0, None, None)], **bb)),
    ]


def _variants():
    return [
        ('original', ''),
        ('patch: drains faster', 'eq_calls=8,trim_calls=12'),
        ('patch: cap 14', 'cap=14'),
        ('eq_calls 8', 'eq_calls=8'),
        ('eq_calls 4', 'eq_calls=4'),
        ('eq_calls 1', 'eq_calls=1'),
        ('trim_calls 12', 'trim_calls=12'),
        ('trim_min 4', 'trim_min=4'),
        ('cap 28', 'cap=28'),
        ('cap 20', 'cap=20'),
        ('send cycle 3 / 4', 'send2=3,send3=4'),
        ('eq 1 + min 4', 'eq_calls=1,trim_min=4'),
        ('eq 1 + min 4 + send', 'eq_calls=1,trim_min=4,send2=3,send3=4'),
    ]


def cmd_cases(a):
    cases = _cases()
    names = [c[0] for c in cases]
    for want in a.names:
        if want not in names:
            raise SystemExit('unknown case %r; known: %s' % (want, ' '.join(names)))
    variants = _variants()
    if a.variant:
        variants = [('original', '')]
        for v in a.variant:
            name, _, text = v.partition(':')
            variants.append((name, text))
    variants = [(name, parse_consts(text)) for name, text in variants]
    for key, title, sc in cases:
        if a.names and key not in a.names:
            continue
        sc.duration = a.duration
        print('=' * 112)
        print('case %s: %s' % (key, title))
        print('         ' + describe(sc))
        print('         %d runs, seeds %d..%d, summary from %g s' % (
            a.runs, a.seed, a.seed + a.runs - 1, sc.warmup))
        run_variants(sc, variants, a.runs, a.seed, a.brief)
        print()
    for name, consts in variants[1:]:
        print('%-22s %s' % (name, describe_consts(consts)))
    print()
    if a.brief:
        print(BRIEF_NOTE)
    print(LEGEND)


def cmd_words(a):
    consts = []
    for s in a.consts:
        consts += parse_consts(s)
    print('%-10s %-10s %-10s %-10s %s' % ('constant', 'address', 'original', 'new', 'instruction'))
    for key, val, who in consts:
        if key not in WORDS:
            print('%-10s has no single word in the executable' % key)
            continue
        addr, base, fn, text = WORDS[key]
        imm = fn(val)
        if not 0 <= imm <= 0x7fff:
            raise SystemExit('%s=%d does not fit' % (key, val))
        print('%-10s %08X   %08X   %08X   %s  (%s=%d)' % (
            key, addr, ORIGINAL_WORDS[key], base | imm, text, key, val))
    for players in (2, 3, 4):
        for w in send_gap_warning(consts, players):
            print(w)
    print('Untested.  Pacing constants are per machine; see docs/issues/lag.md for limits.')


# --------------------------------------------------------------------------------------
# Stick codec model (0x13c450 encoder, 0x13c970 decoder)
# --------------------------------------------------------------------------------------

STEPS = (4, 6, 8, 12, 16, 24, 32, 48, 64)     # data 0x402860 (encoder), 0x402880 (decoder)
INDEX_ADJ = (-1, 2)                           # data 0x402878 / 0x402898: no move, move


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


SPRING_K = f32(0.05)                          # 0x13cd78
SPRING_DAMP = f32(1.0 - f32(math.sqrt(f32(0.2))))   # 1 - sqrt(0.2), 0x13cc6c / 0x13cd24 / 0x13cd64


class StickChannel:
    """One stick axis through the encoder and the decoder.  The two ends keep identical
    predictor state, so one object stands for both."""

    def __init__(self, iterations=10):
        self.index = 0
        self.pred = 0
        self.value = f32(128.0)
        self.vel = f32(0.0)
        self.iterations = iterations

    def frame(self, sample):
        step = STEPS[self.index]
        diff = sample - self.pred
        move = 1 if abs(diff) >= step else 0          # one bit: move or not
        if move:
            self.pred += step if diff > 0 else -step  # one bit: direction
            self.pred = min(255, max(0, self.pred))
        self.index = min(8, max(0, self.index + INDEX_ADJ[move]))
        for _ in range(self.iterations):              # decoder only: spring toward pred
            self.value = f32(self.value + self.vel)
            self.vel = f32(f32(self.vel + f32(f32(self.pred - self.value) * SPRING_K))
                           * SPRING_DAMP)
        return min(255, max(0, int(self.value)))


def pad_axis(byte):
    """Stick byte -> the float the game's code reads, one axis pushed (pad_decodeStick
    0x174ce0): radial dead zone 0.32, then rescaled to 0..1."""
    x = (byte - 128) * 0.0078125
    r = abs(x)
    if r < 0.32:
        return 0.0
    return x * (1.0 - 0.32 / r) * 1.4705882


def stick_response(pattern, settle=128, frames=24, iterations=10):
    ch = StickChannel(iterations)
    for _ in range(60):
        ch.frame(settle)
    out = []
    for i in range(frames):
        raw = pattern(i)
        b = ch.frame(raw)
        out.append((i + 1, raw, ch.pred, b, pad_axis(b)))
    return out


def first_frame(rows, test):
    for n, raw, pred, b, v in rows:
        if test(v):
            return n
    return None


def cmd_stick(a):
    it = a.iterations
    print('Stick codec model (encoder 0x13c450 + decoder 0x13c970), %d spring iterations per '
          'frame.' % it)
    print('Frame 1 is the first simulated frame whose input record holds the new stick '
          'position.\nModel output, not a measurement.\n')
    tests = [
        ('full push from rest (128 -> 255)', lambda i: 255, 128),
        ('half push from rest (128 -> 192)', lambda i: 192, 128),
        ('release after a long full push (255 -> 128)', lambda i: 128, 255),
        ('reversal (255 -> 0)', lambda i: 0, 255),
        ('3-frame flick (128 -> 255 for 3 frames -> 128)', lambda i: 255 if i < 3 else 128, 128),
        ('5-frame tap (128 -> 255 for 5 frames -> 128)', lambda i: 255 if i < 5 else 128, 128),
    ]
    for title, pattern, settle in tests:
        rows = stick_response(pattern, settle, a.frames, it)
        print(title)
        print('  frame  ' + ' '.join('%5d' % r[0] for r in rows[:a.show]))
        print('  raw    ' + ' '.join('%5d' % r[1] for r in rows[:a.show]))
        print('  byte   ' + ' '.join('%5d' % r[3] for r in rows[:a.show]))
        print('  pad    ' + ' '.join('%5.2f' % r[4] for r in rows[:a.show]))
        peak = max(abs(r[4]) for r in rows)
        print('  largest pad value %.2f' % peak)
        print()
    rows = stick_response(lambda i: 255, 128, 40, it)
    print('full push from rest: first frame with any movement %s, with half %s, with the 0.8 '
          'the game uses\nfor a digital direction %s, with 0.9 %s' % (
              first_frame(rows, lambda v: v > 0), first_frame(rows, lambda v: v >= 0.5),
              first_frame(rows, lambda v: v > 0.8), first_frame(rows, lambda v: v >= 0.9)))
    rows = stick_response(lambda i: 128, 255, 40, it)
    print('release after a long full push: last frame that still moves %s' % (
        max([r[0] for r in rows if r[4] != 0.0] or [0])))
    print('Offline the stick byte is used as read, so every one of these would be frame 1.')
    if a.start_state:
        ch = StickChannel(it)
        print('\nfrom the reset state (predictor 0, value 128) with the stick centred at 128:')
        print('  ' + ' '.join('%d' % ch.frame(128) for _ in range(20)))


# --------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Model of the lockstep pacing of Champions: Return to Arms. '
                    'Derived from static reading of the executable; UNVALIDATED.',
        epilog='See the docstring at the top of this file and docs/issues/lag.md.')
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('run', help='simulate one scenario')
    add_scenario_args(p)
    p.add_argument('--set', action='append', metavar='KEY=VAL[@M][,...]',
                   help='change pacing constants (for every machine, or one with @M)')
    p.add_argument('--series', dest='series', action='store_true', default=True,
                   help='print each machine over time (the default)')
    p.add_argument('--no-series', dest='series', action='store_false',
                   help='print the summary only')
    p.add_argument('--bucket', type=float, default=5.0,
                   help='seconds per row of the over-time tables')
    p.add_argument('--csv', metavar='FILE', help='write a per-call trace of the last run')
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser('compare', help='same scenario and seeds with different constants')
    add_scenario_args(p)
    p.add_argument('--variant', action='append', metavar='NAME:KEY=VAL[@M][,...]')
    p.add_argument('--brief', action='store_true', help='one row per variant')
    p.set_defaults(fn=cmd_compare, runs=8)

    p = sub.add_parser('sweep', help='one constant over a list of values')
    p.add_argument('key', help='constant to vary, e.g. cap')
    p.add_argument('values', help='comma-separated values, e.g. 10,14,20,28,38')
    add_scenario_args(p)
    p.add_argument('--only', metavar='M', help='change the constant on machine M only')
    p.add_argument('--set', action='append', metavar='KEY=VAL[@M][,...]',
                   help='other constants to change in every row')
    p.add_argument('--full', action='store_true', help='one row per machine')
    p.set_defaults(fn=cmd_sweep, runs=8)

    p = sub.add_parser('cases', help='the cases and variants quoted in docs/issues/lag.md')
    p.add_argument('names', nargs='*', help='case names (default: all)')
    p.add_argument('--runs', type=int, default=12)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--duration', type=float, default=120.0)
    p.add_argument('--brief', action='store_true', help='one row per variant')
    p.add_argument('--variant', action='append', metavar='NAME:KEY=VAL[@M][,...]',
                   help='replace the built-in variant list')
    p.set_defaults(fn=cmd_cases)

    p = sub.add_parser('words', help='instruction/data words for chosen constants')
    p.add_argument('consts', nargs='+', metavar='KEY=VAL')
    p.set_defaults(fn=cmd_words)

    p = sub.add_parser('stick', help='step response of the stick codec')
    p.add_argument('--iterations', type=int, default=10,
                   help='spring iterations per frame (10 in the executable, 0x13cd34)')
    p.add_argument('--frames', type=int, default=24)
    p.add_argument('--show', type=int, default=12, help='frames printed per test')
    p.add_argument('--start-state', action='store_true',
                   help='also print the output from the reset state')
    p.set_defaults(fn=cmd_stick)

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    a.fn(a)
    return 0


if __name__ == '__main__':
    sys.exit(main())
