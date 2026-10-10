"""Tests for ref_netwire.py that need no game file.

Run: python3 -m unittest discover -s tools -p test_ref_netwire.py

They check the model against itself and against numbers already published in the
documents (docs/netcode.md, docs/issues/dynamic-tests.md).  Whether the model matches the
game is the business of tools/difftest_netwire.py, which needs the executable.
"""
import os
import random
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_netwire as R


def history(rng, count):
    """A varied input history as wire records."""
    out = []
    buttons, sticks, yaw, flag = 0, [128] * 4, 0, 0
    for index in range(count):
        if rng.random() < 0.15:
            buttons ^= 1 << rng.randrange(16)
        if rng.random() < 0.03:
            buttons = rng.randrange(65536)
        if rng.random() < 0.3:
            sticks = [rng.choice((0, 128, 255, rng.randrange(256))) for _ in range(4)]
        yaw += rng.choice((0, 0, 0, 5, 5, -7, 40, -300, 1500, 20000))
        if rng.random() < 0.05:
            flag ^= 1
        out.append(R.rec12(buttons, sticks, (index & 0xFF, 0xAA), yaw, flag))
    return out


class FpuTest(unittest.TestCase):
    def test_exact_small_values(self):
        fpu = R.Fpu()
        for a, b in ((1.0, 2.0), (128.0, -0.5), (3.5, 3.5), (-7.25, 0.125), (1000.0, 24.0)):
            self.assertEqual(fpu.add(R.f32(a), R.f32(b)), R.f32(a + b))
            self.assertEqual(fpu.sub(R.f32(a), R.f32(b)), R.f32(a - b))
            self.assertEqual(fpu.mul(R.f32(a), R.f32(b)), R.f32(a * b))
        self.assertEqual(fpu.sqrt(R.f32(9.0)), R.f32(3.0))
        self.assertEqual(fpu.div(R.f32(1.0), R.f32(4.0)), R.f32(0.25))
        self.assertEqual(fpu.from_int(-37), R.f32(-37.0))

    def test_truncation_and_saturation(self):
        self.assertEqual(R.Fpu.to_int(R.f32(-2.9)), -2)
        self.assertEqual(R.Fpu.to_int(R.f32(2.9)), 2)
        self.assertEqual(R.Fpu.to_int(0x4F000000), 0x7FFFFFFF)       # 2**31 saturates
        self.assertEqual(R.Fpu.to_int(0xCF800000), -0x80000000)
        self.assertEqual(R.Fpu.to_int(0x7F800000), 0x7FFFFFFF)       # "infinity" is just big
        self.assertEqual(R.Fpu.to_int(0x00000001), 0)                # exponent field 0 is zero
        # 1/3 is truncated, not rounded
        self.assertEqual(R.Fpu().div(R.f32(1.0), R.f32(3.0)), 0x3EAAAAAA)
        self.assertEqual(R.Fpu(div_nearest=True).div(R.f32(1.0), R.f32(3.0)), 0x3EAAAAAB)

    def test_damping_constant(self):
        fpu = R.Fpu()
        self.assertEqual(fpu.sub(R.F_ONE, fpu.sqrt(R.SPRING_SQUARE)), 0x3F0D8369)


class BitStreamTest(unittest.TestCase):
    def test_roundtrip_and_layout(self):
        rng = random.Random(1)
        writer = R.BitWriter()
        fields = [(rng.randrange(1 << bits), bits) for bits in
                  (rng.choice((1, 3, 4, 5, 9, 16)) for _ in range(500))]
        for value, bits in fields:
            writer.put(value, bits)
        reader = R.BitReader(writer.tobytes())
        for value, bits in fields:
            self.assertEqual(reader.get(bits), value)
        self.assertEqual(reader.pos, writer.pos)
        # most significant bit first, 16-bit little-endian words
        writer = R.BitWriter()
        writer.put(1, 1)
        self.assertEqual(writer.tobytes()[:2], b'\x00\x80')
        writer.put(0x1F, 5)
        self.assertEqual(writer.tobytes()[:2], b'\x00\xfc')

    def test_next_word_is_always_written(self):
        writer = R.BitWriter()
        writer.put(0xA5A5, 16)
        self.assertEqual(writer.written, 2)
        self.assertEqual(writer.words, [0xA5A5, 0])


class AxisTest(unittest.TestCase):
    def frames(self, values):
        enc, dec = R.Channel(), R.Channel()
        out = []
        for value in values:
            writer = R.BitWriter()
            R.encode_axis(writer, enc, [value])
            out += R.decode_axis(R.BitReader(writer.tobytes()), dec, 1)
        return out

    def test_published_sequences(self):
        # docs/netcode.md; executed as a1, a2, a3 in docs/issues/dynamic-tests.md
        out = self.frames([128] * 40 + [255] * 30)
        self.assertEqual(out[:6], [77, 43, 34, 44, 78, 101])
        self.assertEqual(out[39], 127)
        self.assertEqual(out[40:48], [129, 134, 143, 162, 201, 227, 239, 245])
        self.assertEqual(out[-1], 251)

    def test_predictor_follows_on_both_sides(self):
        rng = random.Random(2)
        enc, dec = R.Channel(), R.Channel()
        for _ in range(200):
            count = rng.choice((1, 2, 7, 31, 32, 63, 90))
            values = [rng.choice((0, 255, 128, rng.randrange(256))) for _ in range(count)]
            if rng.random() < 0.3:
                values = [values[0]] * count
            writer = R.BitWriter()
            R.encode_axis(writer, enc, values)
            reader = R.BitReader(writer.tobytes())
            R.decode_axis(reader, dec, count)
            self.assertEqual(reader.pos, writer.pos)
            self.assertEqual((enc.index, enc.pred), (dec.index, dec.pred))
            self.assertTrue(0 <= dec.pred <= 255 and 0 <= dec.index <= 8)

    def test_skip_equals_having_decoded_before(self):
        rng = random.Random(3)
        values = [rng.randrange(256) for _ in range(60)]
        whole = R.Channel()
        writer = R.BitWriter()
        R.encode_axis(writer, R.Channel(), values)
        expected = R.decode_axis(R.BitReader(writer.tobytes()), whole, 60)
        for skip in (0, 1, 25, 59):
            first = R.Channel()
            head = R.BitWriter()
            R.encode_axis(head, R.Channel(), values[:skip])
            R.decode_axis(R.BitReader(head.tobytes()), first, skip)
            tail = R.decode_axis(R.BitReader(writer.tobytes()), first, 60 - skip, skip)
            self.assertEqual(tail, expected[skip:])
            self.assertEqual(first, whole)

    def test_overshooting_run_is_refused(self):
        writer = R.BitWriter()
        writer.put(31, 5)
        with self.assertRaises(R.MalformedPacket):
            R.read_axis_symbols(R.BitReader(writer.tobytes()), 5)

    def test_fpu_choices(self):
        rng = random.Random(4)
        values = []
        while len(values) < 3000:
            values += [rng.randrange(256)] * rng.randrange(1, 40)
        out = R.fpu_sensitivity(values)
        for model in ('ps2g1', 'chop', 'nearest'):
            self.assertLessEqual(max(abs(a - b) for a, b in zip(out['ps2'], out[model])), 1)
        self.assertNotEqual(out['ps2'], out['chop'])


class FramesTest(unittest.TestCase):
    def test_roundtrip(self):
        rng = random.Random(5)
        enc, dec = R.CodecState(), R.CodecState()
        for _ in range(60):
            records = history(rng, rng.choice((1, 2, 30, 31, 32, 62, 63, 120)))
            writer = R.encode_frames(enc, records)
            self.assertEqual(writer.words[0], R.rec12_fields(records[0])[0])
            decoded, bits = R.decode_frames(dec, writer.tobytes(), len(records))
            self.assertEqual(bits, writer.pos)
            for sent, got in zip(records, decoded):
                a, b = R.rec12_fields(sent), R.rec12_fields(got)
                self.assertEqual(a[0], b[0])                    # buttons are exact
                self.assertEqual(a[3] & 1, b[3] & 1)            # so is the flag
                self.assertEqual(b[2], (0, 0))                  # pressure is not carried
            self.assertEqual((enc.yaw_pred, enc.yaw_delta), (dec.yaw_pred, dec.yaw_delta))
            self.assertEqual(R.s16(R.rec12_fields(decoded[-1])[3] & 0xFFFE), dec.yaw_pred & ~1)

    def test_stream_ends_with_trailer(self):
        writer = R.encode_frames(R.CodecState(), [R.rec12(sticks=(0, 0, 0, 0))])
        reader = R.BitReader(writer.tobytes(), writer.pos - 16)
        self.assertEqual(reader.get(16), R.STREAM_TRAILER)
        # one frame that changes nothing from the reset state (predictors are 0):
        # 16 + 5 buttons, 4 x 5 sticks, 5 yaw, 1 + 5 flag, 16
        self.assertEqual(writer.pos, 16 + 5 + 20 + 5 + 6 + 16)
        # a centred stick is 128 away from the reset predictor: each channel needs a zero
        # count, a direction bit and a direction run
        writer = R.encode_frames(R.CodecState(), [R.rec12()])
        self.assertEqual(writer.pos, 16 + 5 + 4 * 9 + 5 + 6 + 16)

    def test_steady_turn_costs_nothing(self):
        state = R.CodecState()
        records = [R.rec12(yaw=100 * i) for i in range(1, 40)]
        R.encode_frames(state, records[:5])
        writer = R.encode_frames(state, records[5:])
        symbols = R.read_frames(writer.tobytes(), len(records) - 5)
        self.assertEqual(set(symbols.yaw), {('keep',)})

    def test_yaw_jump_is_absolute(self):
        state = R.CodecState()
        writer = R.encode_frames(state, [R.rec12(yaw=0), R.rec12(yaw=20000), R.rec12(yaw=20000)])
        symbols = R.read_frames(writer.tobytes(), 3)
        self.assertEqual(symbols.yaw[1], ('abs', 20000))
        self.assertEqual(state.yaw_pred, 20000)

    def test_local_roundtrip_keeps_pressure(self):
        enc, dec = R.CodecState(), R.CodecState()
        record = R.rec12(0x1234, (10, 20, 30, 40), (0x55, 0x66), 0x4000, 1)
        out = R.local_roundtrip(record, enc, dec)
        self.assertEqual(out[:2], record[:2])
        self.assertEqual(out[6:8], b'\x55\x66')
        self.assertEqual((enc.count, dec.count), (1, 1))


def pair():
    """Two machines addressed at each other."""
    machines = [R.Machine(2, 0), R.Machine(2, 1)]
    for machine in machines:
        for slot in range(2):
            machine.peers[slot].ip, machine.peers[slot].port = bytes((10, 0, 0, slot + 1)), 4000 + slot
    return machines


class PacketTest(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(6)
        self.a, self.b = pair()
        for record in history(self.rng, 12):
            self.a.peers[0].set_record(self.a.lif, record, start=0, count=0)
            self.a.lif += 1

    def test_header_and_parse(self):
        self.a.net_frame = 9
        self.a.last_hash_frame = 8
        self.a.peers[0].set_sync(9, 0x1111, 0x22223333)
        self.a.peers[1].newest = 10
        sent = self.a.send_input(1)
        packet = R.parse_packet(sent.data)
        self.assertEqual((packet.kind, packet.last, packet.slot, packet.mask), (R.PKT_INPUT, 12, 0, 3))
        self.assertEqual((packet.first, packet.count, packet.ack, packet.sim_frame), (1, 12, 10, 9))
        self.assertEqual(packet.sync, (9, 0x1111, 0x22223333))
        self.assertEqual(packet.sync_offset % 4, 0)
        self.assertEqual(self.a.last_hash_frame, 9)
        again = R.parse_packet(self.a.send_input(1).data)       # the record goes out once
        self.assertIsNone(again.sync)
        self.assertEqual(again.sync_word, R.NO_SYNC)

    def test_receive_stores_and_acknowledges(self):
        stored = self.b.receive(self.a.send_input(1).data)
        self.assertEqual(stored, list(range(1, 13)))
        peer = self.b.peers[0]
        self.assertEqual((peer.newest, peer.silence, peer.heard), (12, 0, 1))
        for frame in stored:
            number, record, _start, count = peer.record(frame)
            self.assertEqual((number, count), (frame, 0))
            self.assertEqual(record[:2], self.a.peers[0].wire_record(frame)[:2])
        self.assertEqual(peer.recv_state.count, 12)
        # nothing new: the packet is used for pacing only
        self.assertEqual(self.b.receive(self.a.send_input(1).data), [])

    def test_repeat_until_acknowledged(self):
        first = R.parse_packet(self.a.send_input(1).data)
        self.a.peers[1].acked = 7                               # as an incoming packet would set it
        second = R.parse_packet(self.a.send_input(1).data)
        self.assertEqual((first.first, second.first, second.count), (1, 7, 6))
        self.assertEqual(self.a.peers[1].send_frame, 7)
        # a receiver that already holds frames 1..9 skips three of them
        self.b.receive(R.Machine.build_packet(self.a, 1, 1, 9, R.PKT_INPUT, 0, R.CodecState()).data)
        self.assertEqual(self.b.receive(self.a.send_input(1).data), [10, 11, 12])

    def test_ignore_rules(self):
        data = bytearray(self.a.send_input(1).data)
        other_mask = bytearray(data)
        other_mask[8] ^= 0x20
        self.assertEqual(self.b.receive(bytes(other_mask)), [])
        self.assertEqual(self.b.peers[0].heard, 0)
        own_slot = bytearray(data)
        own_slot[8] = (own_slot[8] & 0xF0) | 1
        self.assertEqual(self.b.receive(bytes(own_slot)), [])
        gap = R.Machine.build_packet(self.a, 1, 5, 12, R.PKT_INPUT, 0, R.CodecState()).data
        self.assertEqual(self.b.receive(gap), [])               # starts later than newest + 1
        self.assertEqual(self.b.peers[0].heard, 1)              # but the sender was heard
        self.b.peers[0].oos = 1
        self.assertEqual(self.b.receive(bytes(data)), [])       # mask differs now as well
        with self.assertRaises(R.MalformedPacket):
            bad = bytearray(data)
            bad[8] = (bad[8] & 0xF0) | 7
            self.b.peers[0].oos = 0
            self.b.receive(bytes(bad))

    def test_messages_travel_with_their_frame(self):
        self.a.last_sent = self.a.lif - 2
        self.a.queue_message(5, b'hello')
        self.a.queue_message(3, b'')
        frame = self.a.attach_messages()
        self.assertEqual(frame, self.a.lif - 1)
        packet = R.parse_packet(self.a.send_input(1).data)
        self.assertEqual(packet.blocks, [(frame, b'\x05\x05hello\x03\x00')])
        self.b.receive(self.a.outbox[-1].data)
        self.assertEqual(self.b.frame_messages(0, frame)[0], [(5, b'hello'), (3, b'')])
        self.assertEqual(self.a.frame_messages(0, frame)[0], [(5, b'hello'), (3, b'')])

    def test_padding_offsets_are_inside_the_gap(self):
        seen = False
        for count in range(1, 13):
            sent = R.Machine.build_packet(self.a, 1, 1, count, R.PKT_INPUT, 0, R.CodecState())
            packet = R.parse_packet(sent.data)
            for offset in sent.undefined:
                seen = True
                self.assertTrue(12 + packet.stream_bytes <= offset < packet.sync_offset)
        self.assertTrue(seen)

    def test_raw_relay(self):
        self.b.receive(self.a.send_input(1).data)
        relay = self.b.build_packet(0, 3, 12, R.PKT_RAW_RELAY, 0, None, raw=True)
        packet = R.parse_packet(relay.data)
        self.assertEqual((packet.kind, packet.byte9, packet.slot, packet.count), (R.PKT_RAW_RELAY, 1, 0, 10))
        self.assertEqual(packet.raw_records[0], self.b.peers[0].wire_record(3))

    def test_small_packets(self):
        self.assertEqual(R.kick_request(2, 0b1000), struct.pack('<III', 0xBD41, 2, 8))
        self.assertEqual(R.kicked_notice(), struct.pack('<I', 0xBD43))
        self.assertEqual(R.direct_message(1, b'xy'), struct.pack('<I', 0xBD45) + b'xy')

    def test_peer_image(self):
        peer = self.a.peers[1]
        image = peer.pack()
        self.assertEqual(len(image), R.PEER_SIZE)
        self.assertEqual(R.Peer.unpack(image).pack(), image)
        self.assertEqual(struct.unpack_from('<i', image, 0x44C0)[0], 1)         # acked starts at 1
        self.assertEqual(struct.unpack_from('<I', image, 0x18)[0], R.F_128)     # reset channel value


class SessionTest(unittest.TestCase):
    """Three model machines over a lossy link: the smallest whole lockstep loop."""

    def run_session(self, calls, loss, seed=7):
        rng = random.Random(seed)
        machines = [R.Machine(3, slot) for slot in range(3)]
        applied = [[] for _ in range(3)]
        for index, machine in enumerate(machines):
            for slot in range(3):
                machine.peers[slot].ip, machine.peers[slot].port = bytes((10, 0, 0, slot)), 4000 + slot
            machine.positions = [(0, 0, 0)] * 3 + [None]

            def run_tasks(m, index=index):
                view = [bytes(pad[8:0x24]) + bytes(pad[0x28:0x38]) + bytes(pad[0x3C:0x50]) + bytes(pad[0x54:])
                        for pad in m.pads[:3]]
                applied[index].append((m.net_frame, view, tuple(m.cam_yaw[:3])))
                digest = sum(sum(v) for v in view) + sum(m.cam_yaw[:3])
                m.rand_seed = (m.rand_seed * 1664525 + 1013904223 + digest) & R.M32
            machine.run_tasks = run_tasks
        inputs = [history(random.Random(seed + 10 + i), calls + 2) for i in range(3)]
        flying = []
        for call in range(1, calls + 1):
            for index, machine in enumerate(machines):
                inbox = [d for due, to, d in flying if to == index and due <= call]
                flying = [item for item in flying if not (item[1] == index and item[0] <= call)]
                record = inputs[index][call]
                word = struct.unpack_from('<I', record, 8)[0]
                sent, _held, _steps = machine.net_main(record[:8], word & 0xFFFE, word & 1, inbox=inbox,
                                                       render_frame=call)
                for datagram in sent:
                    if rng.random() >= loss:
                        flying.append((call + rng.randrange(1, 5), datagram.peer, datagram.data))
        return machines, applied

    def test_agreement(self):
        machines, applied = self.run_session(260, 0.08)
        self.assertTrue(all(m.net_frame > 120 for m in machines))
        self.assertFalse(any(p.oos for m in machines for p in m.peers))
        common = min(len(a) for a in applied)
        self.assertEqual(applied[0][:common], applied[1][:common])
        self.assertEqual(applied[0][:common], applied[2][:common])

    def test_local_input_is_seen_through_the_codec(self):
        machines, applied = self.run_session(60, 0.0)
        # the frame a machine simulates from its own pad is not the raw sample
        raw = machines[0].peers[0].wire_record(20)
        self.assertEqual(applied[0][19][0], 20)
        self.assertNotEqual(applied[0][19][1][0][0x0C:0x10], b'')
        self.assertEqual(applied[0][19][1], applied[1][19][1])
        self.assertEqual(len(raw), 12)


class PadTest(unittest.TestCase):
    def apply(self, **kw):
        pad, prev = bytearray(R.PAD_SIZE), [0, 0]
        R.pad_apply(pad, R.rec12(**kw), prev)
        return pad, prev

    def test_digital_thresholds(self):
        # docs/issues/dynamic-tests.md b7: no movement below 169, digital at 239 and at 17
        for byte, moving, digital in ((128, False, 0), (168, False, 0), (169, True, 0), (238, True, 0),
                                      (239, True, 0x800000), (255, True, 0x800000), (17, True, 0x400000),
                                      (18, True, 0)):
            pad, _prev = self.apply(sticks=(byte, 128, 128, 128))
            self.assertEqual(struct.unpack_from('<I', pad, 0x14)[0] != 0, moving, byte)
            self.assertEqual(struct.unpack_from('<I', pad, 8)[0], digital, byte)

    def test_buttons_edges_and_repeat(self):
        pad, prev = bytearray(R.PAD_SIZE), [0, 0]
        record = R.rec12(buttons=0x0040)
        repeats = []
        for call in range(1, 30):
            R.pad_apply(pad, record, prev)
            pressed, repeat = struct.unpack_from('<II', pad, 0x0C)
            self.assertEqual(pressed, 0x40 if call == 1 else 0)
            if repeat and call > 1:
                repeats.append(call)
        # the counter is call - 1; it repeats at 24 and 28 (over 20 and a multiple of 4)
        self.assertEqual(repeats, [25, 29])
        self.assertEqual(struct.unpack_from('<I', pad, 0x4C)[0], R.F_ONE)

    def test_untouched_bytes(self):
        pad, prev = bytearray(b'\xee' * R.PAD_SIZE), [0, 0]
        R.pad_apply(pad, R.rec12(), prev)
        self.assertEqual(bytes(pad[:8]), b'\xee' * 8)
        self.assertEqual(bytes(pad[0x24:0x28]), b'\xee' * 4)
        self.assertNotIn(0xEE, pad[8:0x24] + pad[0x28:])


class MiscTest(unittest.TestCase):
    def test_sync_hash(self):
        positions = [(R.f32(100.25), R.f32(-200.75), R.f32(12.9)), None, (R.f32(3000.0), R.f32(4000.5), R.f32(-0.5))]
        self.assertEqual(R.sync_hash(0x12345678, 0, positions), (0x12345678 + (100 - 200 + 12) + 7000) & R.M32)
        self.assertEqual(R.sync_hash(5, 7, []), 12)

    def test_launch_checksum(self):
        self.assertEqual(R.launch_checksum(b'\x01'), 0x218)
        self.assertEqual(R.launch_checksum(b'\x01\x02'), (0x218 + (6 ^ 0x30E15F) + 1) & 0xFFFF)
        rng = random.Random(8)
        for _ in range(200):
            chunk = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 300)))
            wide = 0x217
            for index, byte in enumerate(chunk):                # the receiver's wider mask
                value = R.s8(byte)
                wide += -((value & 0x148F37) * (index & 7)) if index & 1 == 0 else (value * 3) ^ 0x30E15F
                wide += R.s8(chunk[0])
            self.assertEqual(R.launch_checksum(chunk), wide & 0xFFFF)
            packet, argument = R.launch_data_packet(77, 3, chunk)
            self.assertEqual(len(packet), 12 + len(chunk))
            self.assertTrue(R.launch_data_ok(argument, chunk))
            self.assertEqual(argument & 0xFFFF, 3)

    def test_launch_packet(self):
        packet = R.launch_packet(9, 6, 0)
        self.assertEqual(len(packet), R.LAUNCH_SIZE)
        self.assertEqual(R.parse_launch_packet(packet)[:3], (9, 6, 0))
        self.assertIsNone(R.parse_launch_packet(packet[:15]))

    def test_kick_request_is_not_answered_after_the_drop(self):
        machine = R.Machine(3, 0)
        machine.peers[2].newest = 50
        machine.dispatch(R.kick_request(1, 0b100))
        self.assertEqual(len(machine.outbox), 1)                # relay of slot 2 to machine 1
        self.assertEqual((machine.peers[2].kick, machine.peers[2].drop_frame, machine.kick_state), (1, -1, 1))
        machine.outbox = []
        machine.peers[2].dropped = 1
        machine.dispatch(R.kick_request(1, 0b100))
        self.assertEqual(machine.outbox, [])


if __name__ == '__main__':
    unittest.main()
