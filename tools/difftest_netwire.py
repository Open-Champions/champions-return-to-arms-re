#!/usr/bin/env python3
"""difftest_netwire.py - compare tools/ref_netwire.py with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_netwire.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   about a tenth of the random cases
    --seed N  seed of the random inputs (default 20973); a run with one seed repeats exactly
    -k TEXT   run only the properties whose name contains TEXT
    -v        print up to three failing cases per property

Every property prints one line: PASS or FAIL, its name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL code runs in tools/ee_emu.py (an instruction interpreter, not a console)
    on a peer table, input rings and globals this script writes into its memory.  The two
    libnet stubs the netcode calls, sceInetSendTo 0x365830 and sceInetRecvFrom 0x365670,
    are replaced: one captures every datagram, the other supplies them.  The same state and
    the same datagrams go through the model; then every datagram and the complete netcode
    state (all four 0x44e0-byte peer entries and the globals listed in STATE_WORDS) must be
    equal, byte for byte.

    Three things the original leaves to chance are handled explicitly, never by ignoring a
    difference:
      * up to two padding bytes after the bit stream of an input packet are not stored by
        the builder.  The model names their offsets; the test checks every other byte and
        checks separately that the named bytes still hold the marker the stack was filled
        with;
      * the two pressure bytes of a received frame are whatever the receiver's stack held.
        The model takes them as an input (Machine.stack_bytes), which the test fills from
        the interpreter's ring AFTER the original ran; every other stored byte is compared;
      * the message-start word of a freshly sampled local record is an uninitialised stack
        word; same treatment (Machine.sample_garbage).

    Sessions: 2 to 4 emulated consoles each run the original net_main 0x132e90 once per
    "rendered frame", with net_pumpReceive, the receiver, the packet builder, the
    acknowledgement bookkeeping and the whole tick net_frameLoop 0x139e88 (local
    encode/decode, pad_apply, message dispatch, sync hash and compare) running for real.
    Only these are replaced: the two socket calls, the pad sampler 0x17421c and
    Camera_getYaw 0x207450 (test input), tasks_run 0x3226e4 (a toy simulation that moves
    the player objects from the lockstep pads, camera words and executed game messages, so
    that the sync hash depends on every input every machine applied), path_service,
    game_isFrozen (returns 1, which keeps the prediction copy out), net_predictLocalPlayer,
    dbg_printf and the two calls made when a kicked player's character is killed.  A model
    Machine shadows each console.  Datagrams travel through a simulated link with delay,
    loss, duplication and reordering.

Floating point
    The stick decoder and pad_apply are compared as 32-bit patterns under the
    interpreter's default adder model with the full sample, and on a smaller sample under
    its three other adder models and with the multiplier-bias and divide-rounding switches,
    the model switched the same way.  Equality under all six shows the model does the same
    operations in the same order.  It does not show that either matches a console in the
    last bit; the property "fpu choices disagree" reports how often the choices themselves
    produce different stick bytes.
"""
import collections
import hashlib
import os
import random
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError, M32, M64       # noqa: E402
import ref_netwire as R                         # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FPU_CONFIGS = (('ps2', False, False), ('ps2g1', False, False), ('chop', False, False),
               ('nearest', False, False), ('ps2', True, False), ('ps2', False, True))

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
NOTES = []

# ---- addresses (names from names.tsv / symbols/*.tsv) -----------------------------------
ENCODE_AXIS, DECODE_AXIS = 0x13C450, 0x13C970
PAD_APPLY = 0x174410
SEND_PACKET, RECEIVER, PUMP_RECEIVE, NET_MAIN, FRAME_LOOP = 0x137D60, 0x13B5D0, 0x13C078, 0x132E90, 0x139E88
SEND_GAME_MSG, SEND_TO_PEERS, KICK_PEER = 0x13DB38, 0x131B00, 0x131CB8
LAUNCH_SEND_DATA, LAUNCH_SEND_PACKET = 0x1354F8, 0x13E2C8
ENGINE_FRAME_STEP = 0x19E3A8
SEND_TO, RECV_FROM, DBG_PRINTF = 0x365830, 0x365670, 0x355490
PAD_SAMPLE, CAMERA_GET_YAW = 0x17421C, 0x207450
TASKS_RUN, PATH_SERVICE, GAME_IS_FROZEN, PREDICT, PROCESS_DAMAGE = 0x3226E4, 0x184798, 0x1EBDF8, 0x131D88, 0x1B2CC0

G_PEERS, PEER = 0x5BF838, 0x44E0
G_NETWORK_MODE, G_NUM_PEERS, G_SOCKET = 0x402791, 0x4027C4, 0x4027C8
G_PADS, G_RAW_PADS, G_RAW_PAD_PREV = 0x41BFD8, 0x4028D0, 0x5D0BF8
G_PAD_START_BLOCK, G_PAD_MUTE, G_BTN_A, G_BTN_B = 0x41BFC0, 0x41C138, 0x41BFB8, 0x41BFBC
G_CYCLE_TABLE = 0x4027E8
G_SIM_ENC, G_SIM_DEC = 0x5BF798, 0x5BF7E8
G_CAM_YAW, G_INPUT_LOCK, G_KICK_ACKS = 0x5D0BC0, 0x5D0BC8, 0x5D1454
G_MSG_HANDLERS, G_DIRECT_HANDLERS = 0x5D1498, 0x5D14E0
G_RENDER_FRAME, G_CAMERA, G_MSG_ID_GAME = 0x44FDD0, 0x4F8450, 0x86AC40
G_DISPLAY_RATE_MODE_INV, G_DISPLAY_RATE_BYTE, G_LAST_FRAME_FIELDS = 0x44FD40, 0x44FD50, 0x83D2C8
G_NUM_PLAYERS, G_PLAYERS, PLAYER_STRIDE, PLAYER_OBJ = 0x4D8AE0, 0x4D8AF0, 0x4C30, 0x43D8
G_GHOST, G_LEVEL_PENDING = 0x4027BC, 0x41B6D0
G_LAUNCH_LOCAL, G_LAUNCH_IDS, G_LAUNCH_A, G_LAUNCH_B = 0x402A39, 0x402BD0, 0x402B7C, 0x402B80

# netcode globals compared after every step: name on the model -> (address, size, signed)
STATE_WORDS = collections.OrderedDict((
    ('lif', (0x4027A4, 4, True)), ('last_sent', (0x4027A8, 4, True)), ('net_frame', (0x4027AC, 4, True)),
    ('cycle', (0x4027B0, 4, True)), ('phase', (0x4027B4, 4, True)),
    ('last_hash_frame', (0x4027CC, 4, True)), ('stall', (0x4027D0, 4, True)),
    ('eq', (0x4027DC, 4, True)), ('min_ready', (0x4027E0, 4, True)), ('win', (0x4027E4, 4, True)),
    ('long_stall', (0x40279C, 4, True)), ('kicked', (0x4027A0, 1, False)),
    ('kick_state', (0x5D1450, 4, True)), ('msg_attached', (0x5D14D8, 4, False)),
    ('sim_frame', (0x44FDCC, 4, False)), ('rand_seed', (0x404464, 4, False)),
    ('sync_acc', (0x4027C0, 4, False)), ('modem', (0x4027B8, 1, False)), ('ended', (0x4027D8, 1, False)),
))
STACK_MARK = 0xEE


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-30s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in list(examples)[:3]:
            print('        ' + line)
    sys.stdout.flush()


def scaled(count, floor=10):
    return max(count // 10, floor) if OPTIONS['quick'] else count


class Tally:
    """Counts comparisons and keeps the first few differences of one property."""

    def __init__(self):
        self.count = self.failures = 0
        self.examples = []

    def check(self, ok, describe=None):
        self.count += 1
        if not ok:
            self.failures += 1
            if len(self.examples) < 3 and describe is not None:
                self.examples.append(describe() if callable(describe) else str(describe))
        return ok


# ---------------------------------------------------------------------------------------
# Input histories
# ---------------------------------------------------------------------------------------
class InputGen:
    """Seeded pad-and-camera history: holds, flicks, sweeps, noise, button mashing and long
    idle stretches, camera drift, turns, jumps and wrap-around."""

    def __init__(self, rng):
        self.rng = rng
        self.buttons = 0
        self.button_idle = 0
        self.sticks = [128, 128, 128, 128]
        self.plans = [[] for _ in range(4)]
        self.yaw = rng.randrange(-32768, 32768)
        self.yaw_plan = []
        self.flag = rng.randrange(2)
        self.flag_idle = 0

    def _stick_plan(self, current):
        rng = self.rng
        kind = rng.randrange(7)
        if kind == 0:
            return [rng.randrange(256)] * rng.randrange(1, 50)
        if kind == 1:
            target, n = rng.randrange(256), rng.randrange(3, 40)
            return [current + (target - current) * i // n for i in range(1, n + 1)]
        if kind == 2:
            centre = rng.randrange(8, 248)
            return [centre + rng.randrange(-7, 8) for _ in range(rng.randrange(4, 30))]
        if kind == 3:
            return [rng.randrange(256) for _ in range(rng.randrange(1, 12))]
        if kind == 4:
            return [rng.choice((0, 255))] * rng.randrange(1, 40)
        if kind == 5:
            return [128] * rng.randrange(20, 90)
        return [rng.choice((0, 255, 128, 127, 129))] * rng.randrange(1, 4)

    def _yaw_plan(self):
        rng = self.rng
        kind = rng.randrange(9)
        if kind == 0:
            return [0] * rng.randrange(1, 80)
        if kind == 1:
            return [rng.randrange(-70, 71)] * rng.randrange(2, 70)
        if kind == 2:
            return [rng.randrange(-12, 13) for _ in range(rng.randrange(3, 40))]
        if kind == 3:
            return [rng.randrange(-32768, 32768)]
        if kind == 4:
            step, n = rng.randrange(-40, 41), rng.randrange(3, 30)
            return [step * i // 3 for i in range(n)]
        if kind == 5:
            return [rng.choice((256, 300, 600, 999, 1000, 1001, 1002, -256, -999, -1000, -1001, -1500))]
        if kind == 6:
            return [rng.randrange(-260, 261) for _ in range(rng.randrange(2, 12))]
        if kind == 7:
            delta = rng.choice((30, 31, 32, -30, -31, -32, 254, 255, 256, -255, -256))
            return [delta] * rng.randrange(1, 40)
        return [rng.choice((1, -1, 2, -2))] * rng.randrange(20, 100)

    def next(self):
        rng = self.rng
        if self.button_idle > 0:
            self.button_idle -= 1
        else:
            roll = rng.random()
            if roll < 0.10:
                self.buttons ^= 1 << rng.randrange(16)
            elif roll < 0.13:
                self.buttons ^= rng.randrange(1, 65536)
            elif roll < 0.15:
                self.buttons = rng.choice((0, 0xFFFF, rng.randrange(65536)))
            elif roll < 0.18:
                self.button_idle = rng.choice((29, 30, 31, 32, 61, 62, 63, rng.randrange(1, 120)))
        for index in range(4):
            if not self.plans[index]:
                self.plans[index] = self._stick_plan(self.sticks[index])
            self.sticks[index] = max(0, min(255, self.plans[index].pop(0)))
        if not self.yaw_plan:
            self.yaw_plan = self._yaw_plan()
        self.yaw = R.s16(self.yaw + self.yaw_plan.pop(0))
        if self.flag_idle > 0:
            self.flag_idle -= 1
        else:
            roll = rng.random()
            if roll < 0.05:
                self.flag ^= 1
            elif roll < 0.08:
                self.flag_idle = rng.choice((30, 31, 32, 62, rng.randrange(1, 100)))
        return R.rec12(self.buttons, self.sticks, (rng.randrange(256), rng.randrange(256)), self.yaw, self.flag)

    def sample(self):
        """(8 sampler bytes, yaw, camera flag) of the next frame."""
        record = self.next()
        word = struct.unpack_from('<I', record, 8)[0]
        return record[:8], word & 0xFFFE, word & 1


def random_state(rng, warm=None):
    """A codec state reached by encoding a random history from the reset state."""
    state = R.CodecState()
    gen = InputGen(rng)
    count = rng.choice((0, 0, 1, 5, 40, 200)) if warm is None else warm
    if count:
        R.encode_frames(state, [gen.next() for _ in range(count)])
    return state


# ---------------------------------------------------------------------------------------
# The interpreter side
# ---------------------------------------------------------------------------------------
class Console:
    """One interpreter instance with the socket calls replaced."""

    def __init__(self, elf, fpu=('ps2', False, False)):
        emu = self.emu = EE(elf, fpu_model=fpu[0])
        emu.fpu_mul_bias, emu.fpu_div_nearest = fpu[1], fpu[2]
        self.mem = emu.mem
        self.sent = []          # (peer ip bytes, port, data, timeout word, buffer address)
        self.inbox = collections.deque()
        self.printed = []
        emu.stub(SEND_TO, function=self._send, name='sceInetSendTo')
        emu.stub(RECV_FROM, function=self._recv, name='sceInetRecvFrom')
        emu.stub(DBG_PRINTF, function=lambda e: self.printed.append(e.r[4] & M32) or 0, name='dbg_printf')
        emu.record_calls = False
        emu.record_writes = False
        self.sp = emu.r[29]
        self.mem.w32(G_SOCKET, 7)

    def _send(self, emu):
        buffer, size = emu.r[7] & M32, emu.r[8] & M32
        block = emu.mem.read(emu.r[10] & M32, 16)
        self.sent.append((block[4:8], emu.r[11] & M32, emu.mem.read(buffer, size),
                          emu.mem.u32(emu.r[29] & M32), buffer, block))
        return size

    def _recv(self, emu):
        if not self.inbox:
            return -500
        data = self.inbox.popleft()
        limit = emu.r[8] & M32
        emu.mem.write(emu.r[7] & M32, data[:limit])
        return len(data[:limit])

    def mark_stack(self, depth=0x6000):
        self.mem.write(self.sp - depth, bytes([STACK_MARK]) * depth)

    def call(self, address, *args, steps=4000000):
        self.emu.r[29] = self.sp
        return self.emu.call(address, *args, max_steps=steps)

    # ---- state transfer ----
    def load(self, machine):
        mem = self.mem
        for slot in range(4):
            mem.write(G_PEERS + slot * PEER, machine.peers[slot].pack())
        mem.w8(G_NETWORK_MODE, machine.network_mode)
        mem.w32(G_NUM_PEERS, machine.num_peers)
        for name, (address, size, _signed) in STATE_WORDS.items():
            value = int(getattr(machine, name))
            if size == 4:
                mem.w32(address, value & M32)
            else:
                mem.w8(address, value & 0xFF)
        for index, value in enumerate(machine.send_cycles):
            mem.w32(G_CYCLE_TABLE + 4 * index, value)
        mem.write(G_SIM_ENC, machine.sim_enc.pack())
        mem.write(G_SIM_DEC, machine.sim_dec.pack())
        mem.write(G_KICK_ACKS, bytes(machine.kick_acks))
        for slot in range(4):
            mem.w16(G_CAM_YAW + 2 * slot, machine.cam_yaw[slot])
            calls, mask, centre = machine.input_lock[slot]
            mem.write(G_INPUT_LOCK + 12 * slot, struct.pack('<iIi', calls, mask, centre))

    def peer_image(self, slot):
        return self.mem.read(G_PEERS + slot * PEER, PEER)

    def words(self):
        out = collections.OrderedDict()
        for name, (address, size, signed) in STATE_WORDS.items():
            if size == 4:
                out[name] = self.mem.s32(address) if signed else self.mem.u32(address)
            else:
                out[name] = self.mem.u8(address)
        out['network_mode'] = self.mem.u8(G_NETWORK_MODE)
        out['num_peers'] = self.mem.s32(G_NUM_PEERS)
        out['kick_acks'] = list(self.mem.read(G_KICK_ACKS, 4))
        out['cam_yaw'] = [self.mem.u16(G_CAM_YAW + 2 * i) for i in range(4)]
        out['input_lock'] = [list(struct.unpack('<iIi', self.mem.read(G_INPUT_LOCK + 12 * i, 12))) for i in range(4)]
        out['sim_enc'] = self.mem.read(G_SIM_ENC, 0x4C)
        out['sim_dec'] = self.mem.read(G_SIM_DEC, 0x4C)
        return out


def model_words(machine):
    out = collections.OrderedDict()
    for name, (_address, size, signed) in STATE_WORDS.items():
        value = int(getattr(machine, name))
        if size == 4:
            out[name] = R.s32(value) if signed else value & M32
        else:
            out[name] = value & 0xFF
    out['network_mode'] = machine.network_mode
    out['num_peers'] = machine.num_peers
    out['kick_acks'] = list(machine.kick_acks)
    out['cam_yaw'] = list(machine.cam_yaw)
    out['input_lock'] = [list(lock) for lock in machine.input_lock]
    out['sim_enc'] = machine.sim_enc.pack()
    out['sim_dec'] = machine.sim_dec.pack()
    return out


PEER_FIELDS = (('ip', 0, 4), ('port', 4, 4), ('unknown8', 8, 8), ('recv_state', 0x10, 0x4C),
               ('send_frame', 0x5C, 4), ('send_state', 0x60, 0x4C), ('ring', 0xAC, 0x1800),
               ('sync_ring', 0x18AC, 0xC00), ('msg_ring', 0x24AC, 0x2000), ('msg_write', 0x44AC, 4),
               ('msg_read', 0x44B0, 4), ('pad_prev', 0x44B4, 8), ('newest', 0x44BC, 4),
               ('acked', 0x44C0, 4), ('lead', 0x44C4, 4), ('sim', 0x44C8, 4), ('silence', 0x44CC, 4),
               ('heard', 0x44D0, 4), ('local', 0x44D4, 1), ('dropped', 0x44D5, 1), ('kick', 0x44D6, 1),
               ('oos', 0x44D7, 1), ('drop_frame', 0x44D8, 4), ('kicked_notice', 0x44DC, 4))


def describe_peer_difference(slot, original, model):
    for name, offset, size in PEER_FIELDS:
        a, b = original[offset:offset + size], model[offset:offset + size]
        if a != b:
            where = next(i for i in range(size) if a[i] != b[i])
            detail = ''
            if name == 'ring':
                detail = ' (record %d, byte +0x%x)' % (where // 24, where % 24)
            elif name == 'sync_ring':
                detail = ' (entry %d, byte %d)' % (where // 12, where % 12)
            return 'peer %d field %s differs at +0x%x%s: original %s, model %s' % (
                slot, name, offset + where, detail, a[where:where + 8].hex(), b[where:where + 8].hex())
    return 'peer %d: no difference found' % slot


def state_difference(console, machine):
    """None when the interpreter's netcode state equals the model's, else a description."""
    for slot in range(4):
        original, model = console.peer_image(slot), machine.peers[slot].pack()
        if original != model:
            return describe_peer_difference(slot, original, model)
    a, b = console.words(), model_words(machine)
    for name in a:
        if a[name] != b[name]:
            return 'global %s: original %r, model %r' % (name, a[name], b[name])
    return None


def packet_difference(original, sent):
    """None when a captured datagram equals the model's outside the bytes the model
    declares undefined."""
    if len(original) != len(sent.data):
        return 'length %d, model %d' % (len(original), len(sent.data))
    for index, (a, b) in enumerate(zip(original, sent.data)):
        if a != b and index not in sent.undefined:
            return 'byte %d: original %02x, model %02x (original %s / model %s)' % (
                index, a, b, original[max(0, index - 8):index + 8].hex(), sent.data[max(0, index - 8):index + 8].hex())
    return None


def adopt_stack_bytes(console):
    """Machine.stack_bytes for a model shadowing `console`: the two bytes the original's
    receiver left in a stored frame."""
    def source(slot, frame):
        return console.mem.read(G_PEERS + slot * PEER + 0xAC + (frame & 0xFF) * 24 + 10, 2)
    return source


def adopt_sample_garbage(console, machine):
    def source(frame):
        return console.mem.u32(G_PEERS + machine.local_slot * PEER + 0xAC + (frame & 0xFF) * 24 + 16)
    return source


# ---------------------------------------------------------------------------------------
# 1. Stick channel codec
# ---------------------------------------------------------------------------------------
class AxisRig:
    def __init__(self, elf, fpu):
        self.console = Console(elf, fpu)
        emu = self.console.emu
        self.stream = emu.alloc(0x800)
        self.writer, self.reader = emu.alloc(8), emu.alloc(8)
        self.chan = emu.alloc(16)
        self.samples, self.out = emu.alloc(0x200), emu.alloc(0x200)

    def encode(self, channel, samples, words, pos):
        mem = self.console.mem
        mem.write(self.stream, bytes(0x800))
        mem.write(self.stream, struct.pack('<%dH' % len(words), *words))
        mem.w32(self.writer, self.stream)
        mem.w32(self.writer + 4, pos)
        mem.write(self.chan, channel.pack())
        mem.write(self.samples, bytes(samples))
        self.console.call(ENCODE_AXIS, 0, self.writer, self.chan, self.samples, len(samples))
        return (R.Channel.unpack(mem.read(self.chan, 16)), mem.u32(self.writer + 4),
                mem.read(self.stream, 0x800))

    def decode(self, channel, stream, pos, count, skip):
        mem = self.console.mem
        mem.write(self.stream, bytes(0x800))
        mem.write(self.stream, stream)
        mem.w32(self.reader, self.stream)
        mem.w32(self.reader + 4, pos)
        mem.write(self.chan, channel.pack())
        mem.write(self.out, bytes([0xEE]) * 0x200)
        self.console.call(DECODE_AXIS, 0, self.reader, self.chan, self.out, count, skip)
        return (R.Channel.unpack(mem.read(self.chan, 16)), mem.u32(self.reader + 4),
                mem.read(self.out, count + 1))


def random_channel(rng, fpu=None):
    """A channel state as it would be mid-game: any index and predictor, value and velocity
    from running the spring on a random history."""
    chan = R.Channel()
    if rng.random() < 0.8:
        gen = InputGen(rng)
        samples = [R.rec12_fields(gen.next())[1][0] for _ in range(rng.choice((1, 3, 20, 80)))]
        R.apply_axis_symbols(chan, R.axis_symbols(R.Channel(), samples), fpu or R.DEFAULT_FPU)
    if rng.random() < 0.3:
        chan.index, chan.pred = rng.randrange(9), rng.randrange(256)
    return chan


def test_axis(elf):
    if not wanted('axis'):
        return
    rng = random.Random(OPTIONS['seed'] + 1)
    for config_index, config in enumerate(FPU_CONFIGS):
        rig = AxisRig(elf, config)
        fpu = R.Fpu(*config)
        enc, dec = Tally(), Tally()
        cases = scaled(1500) if config_index == 0 else scaled(250)
        frames = 0
        for _ in range(cases):
            gen = InputGen(rng)
            count = rng.choice((1, 1, 2, 3, 6, 7, 8, 14, 31, 32, 33, 62, 63, 64, 100, 200, 255))
            samples = [R.rec12_fields(gen.next())[1][0] for _ in range(count)]
            if rng.random() < 0.1:
                samples = [rng.choice((0, 255))] * count
            start = random_channel(rng, fpu)
            pos = rng.randrange(0, 300)
            words = [rng.randrange(65536) for _ in range((pos >> 4) + 1)]
            words[-1] &= (0xFFFF << (16 - (pos & 15))) & 0xFFFF       # bits not yet written are 0
            # encoder
            got_chan, got_pos, got_stream = rig.encode(start, samples, words, pos)
            model_chan = start.copy()
            writer = R.BitWriter()
            writer.words, writer.pos = list(words) + [0], pos
            R.encode_axis(writer, model_chan, samples)
            model_stream = (writer.tobytes() + bytes(0x800))[:0x800]
            enc.check(got_pos == writer.pos and got_stream == model_stream
                      and (got_chan.index, got_chan.pred) == (model_chan.index, model_chan.pred),
                      lambda: 'encode %d samples from %r at bit %d: position %d / %d' % (
                          count, start, pos, got_pos, writer.pos))
            # decoder, with a prefix already held
            skip = rng.choice((0, 0, 0, 1, count // 2, count - 1)) if count > 1 else 0
            before = start.copy()
            if skip:
                R.apply_axis_symbols(before, R.axis_symbols(start.copy(), samples[:skip]), fpu)
            got_chan, got_pos, got_out = rig.decode(before, got_stream, pos, count - skip, skip)
            model_chan = before.copy()
            reader = R.BitReader(model_stream, pos)
            model_out = R.decode_axis(reader, model_chan, count - skip, skip, fpu)
            dec.check(got_pos == reader.pos and got_out[:count - skip] == model_out
                      and got_out[count - skip] == 0xEE and got_chan == model_chan,
                      lambda: 'decode %d (+%d skipped): bytes %s / %s, state %r / %r' % (
                          count - skip, skip, got_out[:count - skip].hex()[:40], model_out.hex()[:40],
                          got_chan, model_chan))
            frames += count
        label = '%s%s%s' % (config[0], '+mulbias' if config[1] else '', '+divnearest' if config[2] else '')
        report('axis encode [%s]' % label, enc.failures, enc.count,
               'netcodec_encodeAxis 0x13c450: stream words, bit position, step index and predictor '
               '(%d samples, runs of 31 and 7 included, any start position)' % frames, enc.examples)
        report('axis decode [%s]' % label, dec.failures, dec.count,
               'netcodec_decodeAxis 0x13c970 with 0..n-1 samples skipped: stick bytes, bits consumed, '
               'index, predictor and the value and velocity patterns bit for bit', dec.examples)


def test_fpu_choices():
    if not wanted('fpu'):
        return
    rng = random.Random(OPTIONS['seed'] + 2)
    gen = InputGen(rng)
    samples = [R.rec12_fields(gen.next())[1][0] for _ in range(scaled(20000, 2000))]
    out = R.fpu_sensitivity(samples)
    base = out['ps2']
    parts = []
    worst = 0
    for model in ('ps2g1', 'chop', 'nearest'):
        diff = [abs(a - b) for a, b in zip(base, out[model]) if a != b]
        worst = max([worst] + diff)
        parts.append('%s %d (%.1f%%)' % (model, len(diff), 100.0 * len(diff) / len(samples)))
    NOTES.append('stick bytes that differ from the default adder model over %d frames of one channel: %s; '
                 'largest difference %d' % (len(samples), ', '.join(parts), worst))
    report('fpu choices disagree', 0 if worst <= 1 else 1, len(samples),
           'model only: bytes decoded under the four adder choices differ by at most 1 - %s differ from '
           '\'ps2\'.  Which choice a console matches is not established' % ', '.join(parts))


# ---------------------------------------------------------------------------------------
# 2. pad_apply
# ---------------------------------------------------------------------------------------
def test_pad_apply(elf):
    if not wanted('pad_apply'):
        return
    rng = random.Random(OPTIONS['seed'] + 3)
    for config_index, config in enumerate(FPU_CONFIGS):
        console = Console(elf, config)
        emu, mem = console.emu, console.mem
        fpu = R.Fpu(*config)
        pad_addr, rec_addr, prev_addr = emu.alloc(R.PAD_SIZE), emu.alloc(16), emu.alloc(8)
        tally = Tally()
        cases = scaled(4000) if config_index == 0 else scaled(600)
        pad = bytearray(rng.randrange(256) for _ in range(R.PAD_SIZE))
        prev = [0, 0]
        glob = R.PadGlobals()
        gen = InputGen(rng)
        for case in range(cases):
            if rng.random() < 0.02:
                pad = bytearray(rng.randrange(256) for _ in range(R.PAD_SIZE))
                prev = [rng.randrange(1 << 32), rng.choice((0, 5, 19, 20, 21, 23, 24, 1000))]
                gen = InputGen(rng)
            record = bytearray(gen.next())
            roll = rng.random()
            if roll < 0.15:                                   # exhaustive-ish stick corners
                record[2:6] = bytes(rng.choice((0, 1, 17, 18, 86, 87, 100, 127, 128, 129, 168, 169, 170,
                                                238, 239, 240, 254, 255)) for _ in range(4))
            elif roll < 0.35:
                record[2:6] = bytes(rng.randrange(256) for _ in range(4))
            if rng.random() < 0.3:
                record[0:2] = struct.pack('<H', rng.choice((0, 0x800, 0xFFFF, rng.randrange(65536))))
            glob.start_block = rng.choice((0, 0, 0, 0, 1, 3))
            glob.mute = rng.choice((0, 0, 0, 0, 1))
            allow_a, allow_b = rng.choice((0, 0x40, 0x4060, 0xFFFFFFFF)), rng.choice((0, 0x20, 0x10))
            glob.allow = allow_a | allow_b
            mem.write(pad_addr, bytes(pad))
            mem.write(rec_addr, bytes(record))
            mem.write(prev_addr, struct.pack('<II', *prev))
            mem.w32(G_PAD_START_BLOCK, glob.start_block)
            mem.w32(G_PAD_MUTE, glob.mute)
            mem.w32(G_BTN_A, allow_a)
            mem.w32(G_BTN_B, allow_b)
            console.call(PAD_APPLY, pad_addr, rec_addr, prev_addr)
            model_pad, model_prev = bytearray(pad), list(prev)
            R.pad_apply(model_pad, bytes(record), model_prev, glob, fpu)
            got_pad = mem.read(pad_addr, R.PAD_SIZE)
            got_prev = list(struct.unpack('<II', mem.read(prev_addr, 8)))
            tally.check(got_pad == bytes(model_pad) and got_prev == model_prev
                        and mem.u32(G_PAD_START_BLOCK) == glob.start_block,
                        lambda: 'record %s prev %r: pad %s / %s, prev %r / %r' % (
                            bytes(record).hex(), prev, got_pad[8:].hex(), bytes(model_pad[8:]).hex(),
                            got_prev, model_prev))
            pad, prev = bytearray(got_pad), got_prev
        label = '%s%s%s' % (config[0], '+mulbias' if config[1] else '', '+divnearest' if config[2] else '')
        report('pad_apply [%s]' % label, tally.failures, tally.count,
               'pad_apply 0x174410 with pad_decodeStick 0x174ce0: all 0x58 pad bytes (floats as '
               'patterns), the previous-state block and the start-block counter', tally.examples)


# ---------------------------------------------------------------------------------------
# 3. The packet builder
# ---------------------------------------------------------------------------------------
def random_messages(rng, peer, first, last, heavy=False):
    """Attach random game-message bytes to some frames of first..last in a peer's ring."""
    position = rng.randrange(R.MSG_RING)
    for frame in range(first, last + 1):
        if rng.random() < (0.5 if heavy else 0.12):
            size = rng.choice((1, 2, 3, 7, 40, 128, 254, 255, rng.randrange(1, 256)))
            if rng.random() < 0.15:
                position = R.MSG_RING - rng.randrange(1, size + 1)       # wraps inside the block
            for index in range(size):
                peer.msg_ring[(position + index) & 0x1FFF] = rng.randrange(256)
            base = (frame & 0xFF) * 24
            struct.pack_into('<II', peer.ring, base + 16, position, size)
            position = (position + size) & 0x1FFF


def random_sender(rng, raw=False):
    """A machine about to send: (machine, dest, first, last, owner)."""
    count = rng.randrange(2, 5)
    local = rng.randrange(count)
    machine = R.Machine(count, local)
    for slot in range(4):
        peer = machine.peers[slot]
        peer.ip = bytes(rng.randrange(256) for _ in range(4))
        peer.port = rng.choice((4000, 4001, rng.randrange(65536)))
        if slot != local and slot < count:
            roll = rng.random()
            if roll < 0.08:
                peer.dropped = 1
            elif roll < 0.16:
                peer.kick = rng.choice((1, 2))
            elif roll < 0.22:
                peer.oos = 1
    remote = [s for s in range(count) if s != local]
    dest = rng.choice(remote)
    owner = rng.choice(remote) if raw else local
    frames = rng.choice((1, 1, 2, 3, 5, 8, 12, 20, 31, 32, 33, 41, 62, 63, 64, 100, 180, 255))
    if raw:
        frames = rng.choice((1, 2, 17, 41))
    base = rng.choice((1, 1, rng.randrange(1, 300), rng.randrange(300, 1 << 20), 0x7FFFF000))
    first = base + rng.randrange(0, 4)
    last = first + frames - 1
    prelude = rng.choice((0, 0, 1, 7)) if frames < 240 else 0
    source = machine.peers[owner]
    gen = InputGen(rng)
    state = R.CodecState()
    warm = rng.choice((0, 0, 3, 60))
    if warm:
        R.encode_frames(state, [gen.next() for _ in range(warm)])
    for frame in range(first - prelude, last + 1):
        source.set_record(frame, gen.next(), start=rng.randrange(1 << 32), count=0)
    if rng.random() < 0.6:
        random_messages(rng, source, first, last, heavy=rng.random() < 0.2)
    target = machine.peers[dest]
    target.send_frame = first - prelude
    target.send_state = state
    target.acked = first
    target.newest = last + rng.choice((0, -1, -2, -5, -40, -127, -128, 3, 127, rng.randrange(-300, 300)))
    machine.lif = last + 1
    machine.net_frame = last - rng.choice((0, 1, 2, 3, 5, 9, 38, 39, 200, -1, rng.randrange(0, 60)))
    machine.last_hash_frame = machine.net_frame if rng.random() < 0.5 else machine.net_frame - 1
    for slot in range(4):
        for index in range(256):
            struct.pack_into('<III', machine.peers[slot].sync_ring, index * 12,
                             rng.randrange(1 << 32), rng.randrange(1 << 32), rng.randrange(1 << 32))
    # the builder assembles the datagram in a 5008-byte stack buffer with no check; keep
    # the random message load inside it (and mostly inside the 1984 bytes a receiver takes)
    limit = R.SEND_BUFFER - 16 if rng.random() < 0.1 else R.RECV_BUFFER
    while True:
        keep = machine.last_hash_frame
        try:
            size = len(machine.build_packet(dest, first, last, R.PKT_RAW_RELAY if raw else R.PKT_INPUT,
                                            owner, target.send_state, raw=raw).data)
        except ValueError:
            size = 1 << 30
        machine.last_hash_frame, machine.outbox = keep, []
        if size <= limit:
            break
        loaded = [f for f in range(first, last + 1) if source.msg_count(f)]
        for frame in rng.sample(loaded, (len(loaded) + 1) // 2):
            struct.pack_into('<I', source.ring, (frame & 0xFF) * 24 + 20, 0)
    return machine, dest, first, last, owner


def run_builder(console, machine, dest, first, last, kind, owner, state_addr, raw):
    console.load(machine)
    console.sent = []
    console.mark_stack()
    console.call(SEND_PACKET, dest, first, last, kind, owner, state_addr, 1 if raw else 0)
    return console.sent


def test_builder(elf):
    if not wanted('build'):
        return
    rng = random.Random(OPTIONS['seed'] + 4)
    console = Console(elf)
    dummy = console.emu.alloc(0x50)
    console.mem.write(dummy, R.CodecState().pack())
    tally, marks, args = Tally(), Tally(), Tally()
    with_undefined = with_sync = with_blocks = catch_up = frames_total = longest = 0
    for _ in range(scaled(1200)):
        machine, dest, first, last, owner = random_sender(rng)
        before = [machine.peers[s].pack() for s in range(4)]
        sent = run_builder(console, machine, dest, first, last, R.PKT_INPUT, owner,
                           G_PEERS + dest * PEER + 0x60, False)
        advanced = machine.peers[dest].send_frame < first
        model = machine.build_packet(dest, first, last, R.PKT_INPUT, owner, machine.peers[dest].send_state)
        ok = len(sent) == 1
        difference = packet_difference(sent[0][2], model) if ok else 'no datagram'
        tally.check(ok and difference is None, lambda: 'frames %d..%d to peer %d: %s' % (first, last, dest, difference))
        if not ok:
            continue
        ip, port, data, timeout, _buffer, block = sent[0]
        args.check(ip == machine.peers[dest].ip and port == machine.peers[dest].port and timeout == 1000
                   and block[:4] == bytes(4) and block[8:] == bytes(8)
                   and console.mem.s32(0x4027CC) == R.s32(machine.last_hash_frame)
                   and [console.peer_image(s) for s in range(4)] == before,
                   lambda: 'address %s:%d timeout %d, last hash frame %d / %d' % (
                       ip.hex(), port, timeout, console.mem.s32(0x4027CC), machine.last_hash_frame))
        if model.undefined:
            with_undefined += 1
            if not advanced:
                marks.check(all(data[i] == STACK_MARK for i in model.undefined),
                            lambda: 'bytes %r of a %d-byte packet hold %s' % (
                                model.undefined, len(data), bytes(data[i] for i in model.undefined).hex()))
        parsed = R.parse_packet(model.data)
        with_sync += parsed.sync is not None
        with_blocks += bool(parsed.blocks)
        catch_up += advanced
        frames_total += last - first + 1
        longest = max(longest, len(data))
    report('build input packet', tally.failures, tally.count,
           'net_sendInputPacket 0x137d60 on random peer tables and rings: every datagram byte the builder '
           'stores (%d frames; %d packets with a sync record, %d with message blocks, %d through the '
           'builder\'s own catch-up pass; longest %d bytes)' % (frames_total, with_sync, with_blocks, catch_up, longest),
           tally.examples)
    report('build: call arguments', args.failures, args.count,
           'address block, port, 1000 ms timeout, g_netLastHashFrame afterwards, peer table untouched',
           args.examples)
    report('build: padding not stored', marks.failures, marks.count,
           'of %d packets, %d have bytes between the bit stream and the sync word that the model says the '
           'builder never stores; in every one checked they still hold the marker the stack was filled with'
           % (tally.count, with_undefined), marks.examples)

    tally = Tally()
    for _ in range(scaled(300)):
        machine, dest, first, last, owner = random_sender(rng, raw=True)
        sent = run_builder(console, machine, dest, first, last, R.PKT_RAW_RELAY, owner, dummy, True)
        model = machine.build_packet(dest, first, last, R.PKT_RAW_RELAY, owner, None, raw=True)
        difference = packet_difference(sent[0][2], model) if len(sent) == 1 else 'no datagram'
        tally.check(difference is None and sent[0][0] == machine.peers[dest].ip
                    and console.mem.s32(0x4027CC) == R.s32(machine.last_hash_frame),
                    lambda: 'relay of slot %d frames %d..%d: %s' % (owner, first, last, difference))
    report('build raw relay', tally.failures, tally.count,
           'the same function with raw = 1 (type 0xbd42): header with the relaying slot in byte 9, '
           '12-byte records, the relayed peer\'s sync entry and message blocks', tally.examples)


# ---------------------------------------------------------------------------------------
# 4. The receiver
# ---------------------------------------------------------------------------------------
class Link:
    """One sender feeding one receiver: used to produce realistic and unrealistic packets."""

    def __init__(self, rng, peers, sender_slot, receiver_slot):
        self.rng = rng
        self.sender = R.Machine(peers, sender_slot)
        self.gen = InputGen(rng)
        self.dest = receiver_slot
        self.slot = sender_slot

    def advance(self, frames):
        sender = self.sender
        local = sender.peers[self.slot]
        for _ in range(frames):
            local.set_record(sender.lif, self.gen.next(), start=0, count=0)
            sender.lif += 1
        if self.rng.random() < 0.5:
            sender.net_frame = max(sender.net_frame, sender.lif - self.rng.randrange(1, 12))
            local.set_sync(sender.net_frame, self.rng.randrange(1 << 32), self.rng.randrange(1 << 32))

    def message(self):
        size = self.rng.choice((0, 1, 2, 9, 60, 200, 253))
        self.sender.queue_message(self.rng.randrange(8), bytes(self.rng.randrange(256) for _ in range(size)))
        self.sender.last_sent = self.sender.lif - 2
        self.sender.attach_messages()

    def packet(self):
        self.sender.outbox = []
        return self.sender.send_input(self.dest).data


def test_receiver(elf):
    if not wanted('receive'):
        return
    rng = random.Random(OPTIONS['seed'] + 5)
    console = Console(elf)
    buffer = console.emu.alloc(0x2000)
    tally, garbage = Tally(), Tally()
    outcome = collections.Counter()
    frames_stored = 0
    for _ in range(scaled(160, 16)):
        peers = rng.randrange(2, 5)
        receiver_slot = rng.randrange(peers)
        sender_slot = rng.choice([s for s in range(peers) if s != receiver_slot])
        link = Link(rng, peers, sender_slot, receiver_slot)
        machine = R.Machine(peers, receiver_slot)
        machine.stack_bytes = adopt_stack_bytes(console)
        console.load(machine)
        pending = []
        for _step in range(rng.randrange(8, 40)):
            link.advance(rng.choice((1, 1, 1, 2, 2, 3, 6, 15, 40)))
            if rng.random() < 0.3:
                link.message()
            data = link.packet()
            roll = rng.random()
            if roll < 0.20:                         # lost
                continue
            if roll < 0.35:                         # held back and delivered later
                pending.append(data)
                continue
            batch = [data]
            if pending and rng.random() < 0.6:
                batch.append(pending.pop(rng.randrange(len(pending))))
            if rng.random() < 0.1:
                batch.append(data)                  # duplicate
            for data in batch:
                data = bytearray(data)
                expect_ignored = False
                tweak = rng.random()
                if tweak < 0.05:                    # another active mask
                    data[8] ^= rng.choice((0x10, 0x20, 0x40, 0x80, 0xF0))
                elif tweak < 0.08:                  # the frames claim to be the receiver's own
                    data[8] = (data[8] & 0xF0) | receiver_slot
                elif tweak < 0.12:                  # receiver-side flag on the sending peer
                    flag = rng.choice(('dropped', 'oos', 'kick'))
                    setattr(machine.peers[sender_slot], flag, 1)
                    console.mem.w8(G_PEERS + sender_slot * PEER + {'dropped': 0x44D5, 'kick': 0x44D6,
                                                                    'oos': 0x44D7}[flag], 1)
                    # the mask changes with the flag, so restore the sender's view of it
                    data[8] = (data[8] & 0x0F) | (machine.active_mask() << 4)
                    link.sender.peers[sender_slot].oos = 0
                    expect_ignored = True
                if rng.random() < 0.3:              # a local sync record to compare against
                    packet = R.parse_packet(bytes(data)) if data[8] & 15 == sender_slot else None
                    if packet is not None and packet.sync is not None:
                        value = packet.sync[2] if rng.random() < 0.6 else packet.sync[2] ^ 1
                        frame = packet.sync[0] if rng.random() < 0.9 else packet.sync[0] + 256
                        machine.peers[receiver_slot].set_sync(frame, 0, value)
                        console.mem.write(G_PEERS + receiver_slot * PEER + 0x18AC + (frame & 0xFF) * 12,
                                          struct.pack('<III', frame & M32, 0, value))
                data = bytes(data)
                console.mem.write(buffer, data + bytes(64))
                console.mark_stack()
                console.call(RECEIVER, buffer, len(data), 0)
                before = machine.peers[sender_slot].newest
                was_inactive = machine.peers[sender_slot].inactive
                stored = machine.receive(data, raw=False)
                difference = state_difference(console, machine)
                tally.check(difference is None, lambda: difference)
                if stored and len(batch) == 1:
                    source = machine.peers[sender_slot]
                    garbage.check(all(source.wire_record(f)[6:8] == bytes((STACK_MARK, STACK_MARK)) for f in stored))
                frames_stored += len(stored)
                if stored:
                    outcome['new frames'] += 1
                elif expect_ignored or was_inactive or data[8] >> 4 != machine.active_mask() or data[8] & 15 != sender_slot:
                    outcome['ignored'] += 1
                elif machine.peers[sender_slot].newest == before and struct.unpack_from('<i', data, 4)[0] <= before:
                    outcome['nothing new'] += 1
                else:
                    outcome['starts too late'] += 1
                if machine.peers[sender_slot].inactive:
                    # undo the flag so the conversation can go on
                    for flag, offset in (('dropped', 0x44D5), ('kick', 0x44D6), ('oos', 0x44D7)):
                        setattr(machine.peers[sender_slot], flag, 0)
                        console.mem.w8(G_PEERS + sender_slot * PEER + offset, 0)
                # acknowledgements flow back so that later packets start later
                if rng.random() < 0.7:
                    link.sender.peers[receiver_slot].acked = max(link.sender.peers[receiver_slot].acked,
                                                                 machine.peers[sender_slot].newest - rng.randrange(0, 3))
    report('receive input packet', tally.failures, tally.count,
           'receiver 0x13b5d0 fed packets in order, late, duplicated and tampered with: the whole peer '
           'table and the netcode globals afterwards (%d frames stored; packets: %s)'
           % (frames_stored, ', '.join('%d %s' % (n, k) for k, n in sorted(outcome.items()))), tally.examples)
    report('receive: pressure bytes', garbage.failures, garbage.count,
           'in every packet that stored frames, record bytes +0xa and +0xb of each new frame hold the '
           'marker the receiver\'s stack was filled with: they are not on the wire', garbage.examples)


# ---------------------------------------------------------------------------------------
# 5. Sessions: the original net_main and tick on several consoles
# ---------------------------------------------------------------------------------------
HANDLER_BASE, DIRECT_BASE, KILL_VCALL = 0x00F00000, 0x00F00100, 0x00F00200
PAD_VIEW = (8, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20)     # the pad words the toy simulation reads
PAD_COMPARED = [(8, 0x24), (0x28, 0x58)]               # what pad_apply stores
PRESSURE_FIELDS = (0x38, 0x50)


class Toy:
    """The stand-in simulation: one instance per console and one per model, fed by the
    lockstep pads, the camera words and the game messages executed in the tick.  It moves
    each player's position by the decoded sticks and folds everything else into the shared
    seed, so the sync hash differs as soon as two sides applied different input."""

    def __init__(self, players, identity):
        self.xyz = [[1000 * (slot + 1), -500 * slot, 7 * slot] for slot in range(players)]
        self.identity = identity
        self.fault_frame = None     # this side corrupts its seed in that frame
        self.messages = []          # executed since the last step: (id, payload)
        self.trace = []             # (frame, pads as compared) per step

    def step(self, frame, seed, pads, yaws):
        fpu = R.DEFAULT_FPU
        scale = R.f32(64.0)
        for slot, pad in enumerate(pads):
            words = [struct.unpack_from('<I', pad, off)[0] for off in PAD_VIEW]
            for word in words:
                seed = (seed * 1664525 + 1013904223 + word) & M32
            seed = (seed * 1664525 + 1013904223 + yaws[slot]) & M32
            self.xyz[slot][0] += R.Fpu.to_int(fpu.mul(words[3], scale)) + R.Fpu.to_int(fpu.mul(words[5], scale))
            self.xyz[slot][1] += R.Fpu.to_int(fpu.mul(words[4], scale)) - R.Fpu.to_int(fpu.mul(words[6], scale))
            self.xyz[slot][2] += bin(words[1]).count('1')
        for ident, payload in self.messages:
            seed = (seed * 33 + ident + 0x100 * len(payload)) & M32
            for byte in payload:
                seed = (seed * 33 + byte) & M32
        self.messages = []
        if self.fault_frame == frame:
            seed ^= 0x00010000
        self.trace.append((frame, [b''.join(bytes(pad[a:b]) for a, b in PAD_COMPARED) for pad in pads]))
        return seed

    def positions(self):
        """Float patterns: x, y, z with a half added so that truncation matters."""
        fpu, half = R.DEFAULT_FPU, R.f32(0.5)
        return [tuple(fpu.add(fpu.from_int(R.s32(v & 0xFFFFF) - 0x80000), half) for v in xyz) for xyz in self.xyz]


class SessionConsole(Console):
    """A console prepared to run net_main and net_frameLoop."""

    def __init__(self, elf, players):
        Console.__init__(self, elf)
        emu, mem = self.emu, self.mem
        self.players = players
        self.sample, self.yaw = bytes(8), 0
        self.toy = Toy(players, 'console')
        self.kills, self.directs = [], []
        self.camera = emu.alloc(0x100)
        mem.w32(G_CAMERA, self.camera)
        emu.stub(PAD_SAMPLE, function=self._sample, name='pad_sample')
        emu.stub(CAMERA_GET_YAW, function=lambda e: self.yaw, name='Camera_getYaw')
        emu.stub(TASKS_RUN, function=self._tasks, name='tasks_run')
        emu.stub(PATH_SERVICE, name='path_service')
        emu.stub(GAME_IS_FROZEN, ret=1, name='game_isFrozen')
        emu.stub(PREDICT, name='net_predictLocalPlayer')
        emu.stub(PROCESS_DAMAGE, function=self._killed, name='Player_processDamage')
        emu.stub(KILL_VCALL, name='take damage (virtual)')
        for ident in range(16):
            emu.stub(HANDLER_BASE + 8 * ident, function=lambda e, ident=ident: self._message(ident, e))
            mem.w32(G_MSG_HANDLERS + 4 * ident, HANDLER_BASE + 8 * ident)
        for index in range(4):
            emu.stub(DIRECT_BASE + 8 * index, function=lambda e, index=index: self._direct(index, e))
            mem.w32(G_DIRECT_HANDLERS + 4 * index, DIRECT_BASE + 8 * index)
        vtable = emu.alloc(0x40)
        mem.w32(vtable + 0x14, KILL_VCALL)
        self.objects = []
        for slot in range(players):
            obj = emu.alloc(0x100)
            mem.w32(obj + 0x48, vtable)
            mem.w32(G_PLAYERS + slot * PLAYER_STRIDE + PLAYER_OBJ, obj)
            self.objects.append(obj)
        mem.w32(G_NUM_PLAYERS, players)
        mem.w32(G_MSG_ID_GAME, 3)
        mem.w32(G_DISPLAY_RATE_MODE_INV, 0)
        self.scratch = emu.alloc(0x400)
        self._write_positions()

    def _write_positions(self):
        for slot, xyz in enumerate(self.toy.positions()):
            for index, raw in enumerate(xyz):
                self.mem.w32(self.objects[slot] + 0x10 + 4 * index, raw)

    def _sample(self, emu):
        emu.mem.write(emu.r[5] & M32, self.sample)
        return 1

    def _tasks(self, emu):
        mem = self.mem
        pads = [mem.read(G_PADS + slot * R.PAD_SIZE, R.PAD_SIZE) for slot in range(self.players)]
        yaws = [mem.u16(G_CAM_YAW + 2 * slot) for slot in range(self.players)]
        seed = self.toy.step(mem.u32(0x4027AC), mem.u32(0x404464), pads, yaws)
        mem.w32(0x404464, seed)
        self._write_positions()
        return 0

    def _message(self, ident, emu):
        self.toy.messages.append((ident, emu.mem.read(emu.r[4] & M32, emu.r[5] & M32)))
        return 0

    def _direct(self, index, emu):
        self.directs.append((index, emu.mem.read(emu.r[4] & M32, emu.r[5] & M32)))
        return 0

    def _killed(self, emu):
        self.kills.append(self.objects.index(emu.r[4] & M32))
        return 0

    def queue_message(self, ident, payload):
        self.mem.write(self.scratch, bytes(payload) + b'\0')
        self.call(SEND_GAME_MSG, ident, self.scratch, len(payload))

    def net_main(self, sample, yaw, flag, frame_step, no_sim, hold_arg, render_frame, inbox):
        mem = self.mem
        self.sample, self.yaw = bytes(sample), yaw
        mem.w32(self.camera + 0x34, 0 if flag else 1)
        mem.w32(G_RENDER_FRAME, render_frame)
        mem.w32(G_LAST_FRAME_FIELDS, frame_step)
        self.inbox.extend(inbox)
        self.sent = []
        self.mark_stack()
        self.call(NET_MAIN, 1 if no_sim else 0, 1 if hold_arg else 0, steps=30000000)


def session_model(players, slot, console=None):
    machine = R.Machine(players, slot)
    for index in range(players):
        machine.peers[index].ip = bytes((10, 0, 0, index + 1))
        machine.peers[index].port = 4000 + index
    machine.toy = Toy(players, 'model')
    machine.kills, machine.directs = [], []
    machine.handlers = {ident: (lambda payload, ident=ident: machine.toy.messages.append((ident, payload)))
                        for ident in range(16)}
    machine.direct_handlers = [(lambda payload, index=index: machine.directs.append((index, payload)))
                               for index in range(4)]

    def run_tasks(m):
        m.rand_seed = m.toy.step(m.net_frame, m.rand_seed, [bytes(p) for p in m.pads[:players]],
                                 m.cam_yaw[:players])
        m.positions = m.toy.positions() + [None] * (4 - players)
    machine.run_tasks = run_tasks
    machine.on_kill = machine.kills.append
    machine.first_active_hook = lambda dropped: machine.queue_message(3, bytes((4, dropped)))
    machine.positions = machine.toy.positions() + [None] * (4 - players)
    machine.sim_frame = 0x1234
    if console is not None:
        machine.stack_bytes = adopt_stack_bytes(console)
        machine.sample_garbage = adopt_sample_garbage(console, machine)
    return machine


class Wire:
    """Datagrams in flight: delay in calls, loss, duplication; reordering comes from the
    random delay."""

    def __init__(self, rng, loss=0.0, duplicate=0.0, delay=(1, 2)):
        self.rng, self.loss, self.duplicate, self.delay = rng, loss, duplicate, delay
        self.flying = []
        self.blocked = set()        # (from, to) pairs that drop everything
        self.sent = self.lost = self.duplicated = self.late = 0
        self.order = 0
        self.last_due = {}

    def send(self, now, source, dest, data):
        self.sent += 1
        if (source, dest) in self.blocked or self.rng.random() < self.loss:
            self.lost += 1
            return
        copies = 2 if self.rng.random() < self.duplicate else 1
        self.duplicated += copies - 1
        for _ in range(copies):
            due = now + self.rng.randrange(self.delay[0], self.delay[1] + 1)
            if due < self.last_due.get((source, dest), 0):
                self.late += 1
            self.last_due[(source, dest)] = max(due, self.last_due.get((source, dest), 0))
            self.order += 1
            self.flying.append((due, self.order, dest, data))

    def deliver(self, now, dest):
        due = sorted(item for item in self.flying if item[2] == dest and item[0] <= now)
        self.flying = [item for item in self.flying if not (item[2] == dest and item[0] <= now)]
        return [item[3] for item in due]


class Session:
    """`players` participants; those listed in emulated run the original, the rest are the
    model alone.  One call of step(i) is one rendered frame of participant i."""

    def __init__(self, elf, rng, players, wire, emulated=None, modem=False):
        self.rng, self.players, self.wire = rng, players, wire
        emulated = range(players) if emulated is None else emulated
        self.consoles = [SessionConsole(elf, players) if i in emulated else None for i in range(players)]
        self.models = [session_model(players, i, self.consoles[i]) for i in range(players)]
        self.gens = [InputGen(random.Random(rng.randrange(1 << 30))) for _ in range(players)]
        self.calls = [0] * players
        self.now = 0
        self.dead = set()
        self.message_rate = 0.15
        self.packets, self.state, self.ticks = Tally(), Tally(), Tally()
        self.datagrams = collections.Counter()
        self.undefined_bytes = 0
        self.max_frames_in_packet = 0
        self.held = self.stalled = self.steps = self.messages_run = 0
        self.message_sizes = collections.Counter()
        for i in range(players):
            self.models[i].modem = 1 if modem else 0
            if self.consoles[i] is not None:
                self.consoles[i].load(self.models[i])

    def both(self, index, action):
        """Apply the same state change to a participant's console and model."""
        action(self.models[index], None)
        if self.consoles[index] is not None:
            action(None, self.consoles[index])

    def set_peer_field(self, index, slot, name, value):
        offset, size = {n: (o, z) for n, o, z in PEER_FIELDS}[name]
        setattr(self.models[index].peers[slot], name, value)
        if self.consoles[index] is not None:
            address = G_PEERS + slot * PEER + offset
            if size == 4:
                self.consoles[index].mem.w32(address, value & M32)
            else:
                self.consoles[index].mem.w8(address, value)

    def queue(self, index, ident, payload):
        self.models[index].queue_message(ident, payload)
        if self.consoles[index] is not None:
            self.consoles[index].queue_message(ident, payload)
        self.message_sizes[len(payload)] += 1

    def step(self, index, frame_step=1, no_sim=False, hold_arg=False, sample=None):
        rng, model, console = self.rng, self.models[index], self.consoles[index]
        self.now += 1
        self.calls[index] += 1
        inbox = self.wire.deliver(self.now, index)
        if sample is None:
            sample, yaw, flag = self.gens[index].sample()
        else:
            sample, yaw, flag = sample
        if rng.random() < self.message_rate:
            for _ in range(rng.choice((1, 1, 1, 2, 3))):
                size = rng.choice((0, 1, 2, 5, 16, 60, 120, 200, 255))
                if model.peers[index].msg_write != model.msg_attached:
                    size = min(size, 60)            # keep one frame's bytes under the 255 limit
                waiting = (model.peers[index].msg_write - model.msg_attached) & 0x1FFF
                if waiting + size + 2 > 255:
                    break
                self.queue(index, rng.randrange(8), bytes(rng.randrange(256) for _ in range(size)))
        render = self.calls[index]
        if console is not None:
            console.net_main(sample, yaw, flag, frame_step, no_sim, hold_arg, render, inbox)
        before_trace = len(model.toy.trace)
        try:
            sent, held, steps = model.net_main(sample, yaw, flag, frame_step, no_sim, hold_arg, render, inbox)
        except R.MalformedPacket as error:
            self.state.check(False, 'model refused a packet: %s' % error)
            return
        self.held += held
        self.steps += steps
        self.stalled += steps == 0
        if console is not None:
            ok = len(console.sent) == len(sent)
            difference = None if ok else 'console sent %d datagrams, model %d' % (len(console.sent), len(sent))
            if ok:
                for original, mine in zip(console.sent, sent):
                    difference = packet_difference(original[2], mine)
                    if difference is None and (original[0] != mine.ip or original[1] != mine.port):
                        difference = 'destination %s:%d, model %s:%d' % (original[0].hex(), original[1], mine.ip.hex(), mine.port)
                    self.packets.check(difference is None, lambda: 'call %d of machine %d: %s' % (self.calls[index], index, difference))
                    self.undefined_bytes += len(mine.undefined)
            else:
                self.packets.check(False, difference)
            difference = state_difference(console, model)
            self.state.check(difference is None, lambda: 'call %d of machine %d: %s' % (self.calls[index], index, difference))
            new = model.toy.trace[before_trace:]
            self.ticks.check(console.toy.trace[before_trace:] == new and console.kills == model.kills
                             and console.directs == model.directs and console.toy.xyz == model.toy.xyz,
                             lambda: 'call %d of machine %d: lockstep pads, kills or direct messages differ'
                             % (self.calls[index], index))
            outgoing = [(original[1] - 4000, original[2]) for original in console.sent]
        else:
            outgoing = [(mine.peer, mine.data) for mine in sent]
        for dest, data in outgoing:
            kind = struct.unpack_from('<I', data)[0]
            self.datagrams[kind] += 1
            if kind == R.PKT_INPUT:
                self.max_frames_in_packet = max(self.max_frames_in_packet, data[10])
            if dest not in self.dead:
                self.wire.send(self.now, index, dest, data)

    def run(self, rounds, schedule=None):
        for _ in range(rounds):
            for index in range(self.players):
                if index in self.dead:
                    continue
                if schedule is not None:
                    args = schedule(self, index)
                    if args is None:
                        continue
                    self.step(index, **args)
                else:
                    self.step(index)

    def summary(self):
        frames = [m.net_frame for i, m in enumerate(self.models) if i not in self.dead]
        kinds = ', '.join('%d of type 0x%x' % (n, k) for k, n in sorted(self.datagrams.items()))
        return ('%d calls, simulation frame %s, %d datagrams (%s; %d lost, %d duplicated, %d overtaken; '
                'up to %d frames in one), %d held and %d stalled calls'
                % (sum(self.calls), '/'.join(str(f) for f in frames), self.wire.sent, kinds, self.wire.lost,
                   self.wire.duplicated, self.wire.late, self.max_frames_in_packet, self.held, self.stalled))

    def agreement(self):
        """Across participants: (frames compared, frames whose lockstep pads differ outside
        the pressure fields, frames whose pressure fields differ)."""
        by_frame = collections.defaultdict(list)
        for index, model in enumerate(self.models):
            source = self.consoles[index].toy if self.consoles[index] is not None else model.toy
            for frame, pads in source.trace:
                by_frame[frame].append(pads)
        compared = different = pressure = 0
        offsets = [off - 8 if off < 0x24 else off - 12 for off in PRESSURE_FIELDS]

        def strip(pads):
            out = []
            for pad in pads:
                pad = bytearray(pad)
                for off in offsets:
                    pad[off:off + 4] = bytes(4)
                out.append(bytes(pad))
            return out
        for frame, views in by_frame.items():
            if len(views) < 2:
                continue
            compared += 1
            if any(strip(view) != strip(views[0]) for view in views[1:]):
                different += 1
            elif any(view != views[0] for view in views[1:]):
                pressure += 1
        return compared, different, pressure

    def flags(self, name):
        return [[getattr(m.peers[s], name) for s in range(self.players)] for m in self.models]


def session_report(name, session, text, extra_ok=True, extra_text=''):
    compared, different, pressure = session.agreement()
    failures = session.packets.failures + session.state.failures + session.ticks.failures
    examples = session.packets.examples + session.state.examples + session.ticks.examples
    if not extra_ok:
        failures += 1
        examples = [extra_text] + examples
    if different:
        failures += 1
        examples = ['%d frames were simulated with different pads on different machines' % different] + examples
    report(name, failures, session.packets.count + session.state.count + session.ticks.count,
           '%s: %s. Compared: %d datagrams byte for byte, the netcode state after each of %d calls, the '
           'lockstep pads of every tick; %d frames simulated by two or more machines all used identical pads '
           '(%d of them differ only in the two pressure fields)%s'
           % (text, session.summary(), session.packets.count, session.state.count, compared, pressure,
              extra_text if extra_ok else ''), examples)
    return session


def test_sessions(elf):
    if not wanted('session'):
        return
    seed = OPTIONS['seed']
    rounds = scaled(700, 70)

    rng = random.Random(seed + 10)
    session = Session(elf, rng, 2, Wire(rng, loss=0.03, duplicate=0.02, delay=(1, 3)))
    session.run(rounds)
    session_report('session: 2 consoles', session, 'two emulated consoles, 3% loss, delay 1-3 calls',
                   all(not any(row) for row in session.flags('oos')), ' No machine flagged another out of sync')

    rng = random.Random(seed + 11)
    session = Session(elf, rng, 3, Wire(rng, loss=0.10, duplicate=0.05, delay=(1, 9)))
    session.run(rounds * 2 // 3)
    session_report('session: 3 consoles, bad link', session,
                   'three consoles, 10% loss, 5% duplicates, delay 1-9 calls (packets overtake each other)',
                   all(not any(row) for row in session.flags('oos')), ' No machine flagged another out of sync')

    rng = random.Random(seed + 12)
    session = Session(elf, rng, 4, Wire(rng, loss=0.05, duplicate=0.02, delay=(1, 5)))
    session.message_rate = 0.3
    session.run(rounds // 2)
    session_report('session: 4 consoles', session, 'four consoles, 5% loss, many game messages (sizes %s)'
                   % ', '.join(str(k) for k in sorted(session.message_sizes)),
                   all(not any(row) for row in session.flags('oos')), ' No machine flagged another out of sync')

    # uneven machines: two steps per call, skipped calls, held and no-simulation calls,
    # the input lock, an outage
    rng = random.Random(seed + 13)
    wire = Wire(rng, loss=0.02, delay=(1, 4))
    session = Session(elf, rng, 3, wire)
    phase = {'round': 0}

    def schedule(s, index):
        if index == 0:
            phase['round'] += 1
        r = phase['round']
        if index == 1 and r % 3 == 0:
            return None                                     # machine 1 misses every third call
        args = {'frame_step': 2 if (index == 1 or 200 < r < 260) else 1}
        if index == 2 and r % 97 in (5, 6, 7, 8):
            args['hold_arg'] = True
        if index == 0 and r % 131 in (9, 10, 11):
            args['no_sim'], args['hold_arg'] = True, True
        if r % 150 == 40:
            wire.blocked = {(0, 1), (1, 0)}
        if r % 150 == 75:
            wire.blocked = set()
        if r % 60 == 30 and index == 2:
            def lock(model, console):
                if model is not None:
                    model.input_lock[2] = [20, 0x00F0, r % 120 == 30]
                else:
                    console.mem.write(G_INPUT_LOCK + 24, struct.pack('<iIi', 20, 0x00F0, r % 120 == 30))
            s.both(2, lock)
        return args
    session.run(rounds * 2 // 3, schedule)
    session_report('session: uneven machines', session,
                   'three consoles; one runs two input frames per call and misses every third call, with '
                   'held calls, no-simulation calls, an input lock and a 35-round outage between two of them',
                   all(not any(row) for row in session.flags('oos')), ' No machine flagged another out of sync')

    rng = random.Random(seed + 14)
    session = Session(elf, rng, 2, Wire(rng, loss=0.02, delay=(1, 3)), modem=True)
    session.run(rounds // 3)
    session_report('session: modem send cycle', session, 'two consoles with the UART-modem flag set (send cycle 3)',
                   all(m.cycle == 3 for m in session.models), ' Cycle is 3 calls')

    # one participant is the model alone
    rng = random.Random(seed + 15)
    session = Session(elf, rng, 3, Wire(rng, loss=0.05, delay=(1, 4)), emulated=(0, 2))
    session.run(rounds // 2)
    progress = min(m.net_frame for m in session.models)
    session_report('session: model as a peer', session,
                   'two consoles and one participant that is the model alone (its packets are whatever the '
                   'model builds, its state whatever the model decodes)',
                   progress > rounds // 4 and all(not any(row) for row in session.flags('oos')),
                   ' The consoles accepted its input, simulated %d frames with it and their sync hashes kept '
                   'matching its hashes' % progress)

    # divergence: one machine's simulation goes wrong in one frame
    rng = random.Random(seed + 16)
    session = Session(elf, rng, 3, Wire(rng, loss=0.02, delay=(1, 3)))
    session.run(60)
    bad_frame = session.models[1].net_frame + 6
    session.models[1].toy.fault_frame = bad_frame
    session.consoles[1].toy.fault_frame = bad_frame
    session.run(scaled(260, 120))
    oos = session.flags('oos')
    expected = [[0, 1, 0], [1, 0, 1], [0, 1, 0]]
    frames = [m.net_frame for m in session.models]
    session_report('session: one machine diverges', session,
                   'three consoles; machine 1 corrupts its seed in frame %d' % bad_frame,
                   oos == expected and session.models[1].stall > 50,
                   ' Out-of-sync flags end as %r (row = machine, column = peer): the others flag machine 1 and '
                   'drop its packets, it flags them; machine 1 stops at frame %d because nobody\'s input is '
                   'accepted any more, machines 0 and 2 stop at %d and %d waiting for its input'
                   % (oos, frames[1], frames[0], frames[2]))

    # a peer goes silent: timeout, negotiation by kick requests and raw relays, drop
    rng = random.Random(seed + 17)
    session = Session(elf, rng, 4, Wire(rng, loss=0.0, delay=(1, 3)))
    session.run(80)
    session.dead.add(3)
    session.wire.flying = [item for item in session.wire.flying if item[2] != 3 or True]
    # machine 0 has seen less of the dead peer than the others
    session.wire.flying = [item for item in session.wire.flying if not (item[2] == 0)]
    for index in range(3):
        session.set_peer_field(index, 3, 'silence', 860 - 7 * index)
    session.run(scaled(200, 200))
    survivors = session.models[:3]
    drop_frames = [m.peers[3].drop_frame for m in survivors]
    dropped = [m.peers[3].dropped for m in survivors]
    kills = [m.kills for m in survivors]
    session_report('session: silent peer is dropped', session,
                   'four consoles, the fourth stops; the others\' silence counters were set to 860, 853 and 846',
                   dropped == [1, 1, 1] and len(set(drop_frames)) == 1 and kills == [[3], [3], [3]]
                   and session.datagrams[R.PKT_KICK_REQUEST] > 0 and session.datagrams[R.PKT_RAW_RELAY] > 0
                   and all(not any(row[:3]) for row in session.flags('oos')[:3])
                   and min(m.net_frame for m in survivors) > drop_frames[0] + 20,
                   ' All three agreed on drop frame %d, marked the peer dropped, killed its player in that '
                   'tick and went on simulating (frames %s); kills %r' % (
                       drop_frames[0], '/'.join(str(m.net_frame) for m in survivors), kills))

    # manual kick
    rng = random.Random(seed + 18)
    session = Session(elf, rng, 3, Wire(rng, loss=0.0, delay=(1, 2)))
    session.run(40)
    session.models[0].kick_peer(2)
    session.consoles[0].call(KICK_PEER, 2)
    session.run(scaled(200, 200))
    session_report('session: manual kick', session,
                   'three consoles; machine 0 calls net_kickPeer(2)',
                   session.datagrams[R.PKT_KICKED] == 12 and session.models[2].kicked == 1
                   and [m.peers[2].dropped for m in session.models[:2]] == [1, 1]
                   and len({m.peers[2].drop_frame for m in session.models[:2]}) == 1,
                   ' 12 kicked notices (0xbd43) went to the kicked machine, which set its flag; machines 0 and '
                   '1 dropped slot 2 at the same frame %d' % session.models[0].peers[2].drop_frame)


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith('-')]
    candidates += [os.path.join(ROOT, 'SLUS_209.73'), 'SLUS_209.73']
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--seed' and argv:
            OPTIONS['seed'] = int(argv.pop(0))
        elif item == '-k' and argv:
            OPTIONS['filter'] = argv.pop(0)
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print('SKIP  SLUS_209.73 not found (pass its path); nothing was compared')
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable (sha256 %s); nothing was compared' % (elf, digest))
        return 0
    started = time.time()
    test_axis(elf)
    test_fpu_choices()
    test_pad_apply(elf)
    test_builder(elf)
    test_receiver(elf)
    test_sessions(elf)
    failed = [name for name, ok in RESULTS if not ok]
    for note in NOTES:
        print('NOTE  ' + note)
    print('%d properties, %d PASS, %d FAIL (seed %d%s, %.0f s)' % (
        len(RESULTS), len(RESULTS) - len(failed), len(failed), OPTIONS['seed'],
        ', quick' if OPTIONS['quick'] else '', time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
