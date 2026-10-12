#!/usr/bin/env python3
"""hub.py - joins three or four native machines in the shim's link format.

  python3 tools/recomp/soak/hub.py <socket path of machine 0> <path of machine 1> ...

The network shim's link (tools/recomp/net/netshim.cpp, RTA_NET_LINK) is a pair: at every
vertical blank a machine sends one message - its frame number and the datagrams its game
sent since the last one - and waits for the other's message for the same frame.  This
program stands in the middle of N machines, each of which connects to its own socket
(RTA_NET_LINK=connect:<path>) and takes the hub for "the other machine": per frame the hub
reads one message from every machine and answers each with one message that carries the
datagrams of all the others, in machine order.  A machine drops what is not addressed to
it, so nothing has to be routed.  All machines advance frame by frame together and a run
repeats exactly, as a pair does.  When one machine ends, the others are told and end.

Standard library only; no game data passes through but the game's own datagrams.
"""
import os
import socket
import struct
import sys

MAGIC = 0x52494731


def read_exact(conn, size):
    data = b''
    while len(data) < size:
        part = conn.recv(size - len(data))
        if not part:
            return None
        data += part
    return data


def read_message(conn):
    """(frame, bye, [raw datagram records]) or None when the machine is gone."""
    head = read_exact(conn, 20)
    if head is None:
        return None
    magic, flags, frame, count = struct.unpack('<IIQI', head)
    if magic != MAGIC:
        return None
    records = []
    for _ in range(count):
        fixed = read_exact(conn, 28)
        if fixed is None:
            return None
        length, = struct.unpack_from('<I', fixed, 24)
        body = read_exact(conn, length) if length else b''
        if body is None:
            return None
        records.append(fixed + body)
    return frame, bool(flags & 1), records


def main(paths):
    listeners = []
    for path in paths:
        if os.path.exists(path):
            os.unlink(path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(1)
        listeners.append(server)
    conns = []
    for server, path in zip(listeners, paths):
        conn, _ = server.accept()
        server.close()
        os.unlink(path)
        conns.append(conn)
    frames = 0
    while True:
        messages = [read_message(conn) for conn in conns]
        gone = [m is None or m[1] for m in messages]
        if any(gone) or len({m[0] for m in messages}) != 1:
            bye = struct.pack('<IIQI', MAGIC, 1, 0, 0)
            for conn, was_gone in zip(conns, gone):
                if not was_gone:
                    try:
                        conn.sendall(bye)
                    except OSError:
                        pass
            break
        frame = messages[0][0]
        for index, conn in enumerate(conns):
            records = [r for other, m in enumerate(messages) if other != index for r in m[2]]
            try:
                conn.sendall(struct.pack('<IIQI', MAGIC, 0, frame, len(records)) + b''.join(records))
            except OSError:
                pass
        frames += 1
    print('hub: %d machines, %d frames' % (len(conns), frames))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
