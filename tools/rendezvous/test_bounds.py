#!/usr/bin/env python3
"""Transport bounds: synthetic blocked links, a local Unix socket, and the C++ client."""
import configparser
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import rendezvous as R

HERE = Path(__file__).resolve().parent
NET2 = HERE.parent / 'recomp' / 'net2'


def masked(payload=b'', opcode=9):
    mask = b'\x11\x22\x33\x44'
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + bytes(v ^ mask[i & 3] for i, v in enumerate(payload))


class Writer:
    def __init__(self):
        self.blocked, self.closed = True, False
        self.sent = bytearray()

    def send(self, data):
        if self.blocked:
            raise BlockingIOError()
        self.sent += data
        return len(data)

    def close(self):
        self.closed = True


class ServiceBounds(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(R, 'now', return_value=1.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.limits = patch.dict(R.LIMITS)
        self.limits.start()
        self.addCleanup(self.limits.stop)
        self.service = R.Service(None, quiet=True)
        self.service.sel.close()
        self.service.sel = Mock()
        self.addCleanup(self.service.close_all)
        self.sock = Writer()
        self.conn = R.Conn(self.sock, '(test)')
        self.conn.ws = 2
        self.service.conns[self.sock] = self.conn
        self.service.per_address[self.conn.address] = 1

    def test_blocked_pongs(self):
        # A logged-in client; isolate the byte budget from the rate limit.
        self.conn.ws_control = R.Bucket(0, 4000)
        self.conn.pid = 'synthetic'
        for _ in range(3000):
            self.service.ws_read(self.conn, masked(b'x' * 125))
            self.assertLessEqual(len(self.conn.outbuf), R.LIMITS['output_bytes'])
            if self.sock.closed:
                break
        self.assertTrue(self.sock.closed)
        self.assertLessEqual(len(self.conn.outbuf), 262144)

    def test_pong_exact_limit_and_one_over(self):
        R.LIMITS['output_bytes'] = 254
        ping = masked(b'x' * 125)
        self.assertEqual(self.service.ws_read(self.conn, ping * 2), b'')
        self.assertEqual(len(self.conn.outbuf), 254)
        self.assertIsNone(self.service.ws_read(self.conn, ping))
        self.assertEqual(len(self.conn.outbuf), 254)
        self.assertTrue(self.sock.closed)

    def test_control_rate_even_when_writer_drains(self):
        self.sock.blocked = False
        burst = R.LIMITS['ws_control_burst']
        self.assertEqual(self.service.ws_read(self.conn, masked() * burst), b'')
        self.assertIsNone(self.service.ws_read(self.conn, masked(opcode=10)))
        self.assertTrue(self.sock.closed)
        self.assertEqual(self.service.counts['limited'], 1)

    def test_control_budget_replenishes_and_preserves_bytes(self):
        self.sock.blocked = False
        payload = b'ping payload'
        burst = R.LIMITS['ws_control_burst']
        self.service.ws_read(self.conn, masked(payload) * burst)
        self.now.return_value += 1
        frame = masked(payload)
        self.assertEqual(self.service.ws_read(self.conn, frame[:3]), b'')
        self.assertEqual(self.service.ws_read(self.conn, frame[3:] + masked(b'line\n', 2)), b'line\n')
        self.assertFalse(self.sock.closed)
        self.assertEqual(self.sock.sent, R.ws_frame(payload, 10) * (burst + 1))

    def test_application_output_uses_same_bound(self):
        R.LIMITS['output_bytes'] = 8
        self.service.send(self.conn, 'hello')
        self.assertEqual(self.conn.outbuf, R.ws_frame(b'hello\n'))
        self.service.send(self.conn, '')
        self.assertTrue(self.sock.closed)
        self.assertEqual(len(self.conn.outbuf), 8)

    def test_upgrade_precedes_greeting_and_is_bounded(self):
        self.conn.ws = 1
        self.service.send(self.conn, 'hi')
        greeting = bytes(self.conn.outbuf)
        request = b'GET /net2 HTTP/1.1\r\nUpgrade: websocket\r\nSec-WebSocket-Key: test'
        self.assertTrue(self.service.ws_upgrade(self.conn, request))
        self.assertTrue(self.conn.outbuf.startswith(b'HTTP/1.1 101 '))
        self.assertTrue(self.conn.outbuf.endswith(b'\r\n\r\n' + greeting))
        self.conn.ws = 1
        self.conn.outbuf = bytearray(greeting)
        R.LIMITS['output_bytes'] = len(greeting)
        self.assertFalse(self.service.ws_upgrade(self.conn, request))
        self.assertEqual(self.conn.outbuf, greeting)


class ProxyBounds(unittest.TestCase):
    def test_unix_socket_creation_and_owner_access(self):
        with tempfile.TemporaryDirectory(prefix='rv-mode-', dir='/tmp') as work:
            path = os.path.join(work, 'ws.sock')
            service = R.Service(None, quiet=True)
            self.addCleanup(service.sel.close)
            self.addCleanup(service.close_all)
            chmod = os.chmod
            modes = []

            def set_mode(name, mode):
                modes.append(stat.S_IMODE(os.stat(name).st_mode))
                chmod(name, mode)

            before = os.umask(0o022)
            try:
                with patch.object(R.os, 'chmod', side_effect=set_mode):
                    service.listen_ws_unix(path)
                restored = os.umask(0o022)
                self.assertEqual(restored, 0o022)
            finally:
                os.umask(before)
            self.assertEqual(modes, [0o600])
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o660)
            self.assertEqual(os.stat(path).st_gid, os.stat(work).st_gid)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(path)
                accepted, _ = service.listeners[0].accept()
                accepted.close()
            service.close_all()
            self.assertFalse(os.path.exists(path))

    def test_unit_restricts_directory_to_proxy_group(self):
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.read(HERE / 'deploy' / 'champions-net2.service')
        service = unit['Service']
        self.assertEqual(service['Group'], 'champions-net2-proxy')
        self.assertEqual(service['DynamicUser'], 'yes')
        self.assertEqual(int(service['RuntimeDirectoryMode'], 8), 0o750)
        self.assertEqual(int(service['StateDirectoryMode'], 8), 0o700)
        self.assertEqual(int(service['UMask'], 8), 0o077)


class ClientBounds(unittest.TestCase):
    def test_guestmap_overlap_refusals(self):
        header = (NET2.parent / 'app' / 'guestmap.h').read_text()
        with tempfile.TemporaryDirectory(prefix='guestmap-bounds-') as work:
            source = Path(work) / 'probe.cpp'
            for lo, hi, allowed in ((0xE0050, 0xE0054, False), (0xFFFFF, 0x100000, False), (0xE0058, 0xE0060, True)):
                block = '    {0x%x, 0x%x, "probe"},\n};' % (lo, hi)
                source.write_text(header.replace('\n};', '\n' + block, 1))
                result = subprocess.run(['clang++', '-std=c++17', '-fsyntax-only', str(source)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode == 0, allowed, result.stderr)
                if not allowed:
                    self.assertIn('two guest-memory blocks', result.stderr)

    def test_cpp_bounds(self):
        with tempfile.TemporaryDirectory(prefix='net2-bounds-') as work:
            binary = str(Path(work) / 'bounds_test')
            command = ['clang++', '-std=c++17', '-O0', '-gline-tables-only', '-Wall', '-Wextra', '-fsanitize=address,undefined',
                       '-fno-omit-frame-pointer', '-fno-sanitize-recover=all', '-I', str(NET2), '-o', binary]
            command += [str(NET2 / name) for name in ('bounds_test.cpp', 'carrier.cpp', 'session.cpp', 'session_mock.cpp', 'cardchars.cpp')]
            command += ['-lpthread']
            if sys.platform == 'darwin':
                command += ['-framework', 'Network', '-framework', 'Security', '-framework', 'CoreFoundation']
            built = subprocess.run(command, capture_output=True, text=True, timeout=600)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([binary], capture_output=True, text=True, timeout=60)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            print(ran.stdout.strip())


if __name__ == '__main__':
    unittest.main()
