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
repeats exactly, as a pair does.  When one machine ends, the others are told and end -
unless HUB_SURVIVE=1 (directed games in which a machine drops out): then the machine that
ended is forgotten and the others go on while two are left.

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
    survive = os.environ.get('HUB_SURVIVE') == '1'      # a machine that ends is forgotten; the others go on
    live = list(range(len(conns)))
    while True:
        messages = {index: read_message(conns[index]) for index in live}
        gone = [index for index in live if messages[index] is None or messages[index][1]]
        if gone and survive:
            for index in gone:
                print('hub: machine %d ended after %d frames; the others go on' % (index, frames))
                live.remove(index)
                del messages[index]
            gone = []
            if len(live) < 2:
                gone = list(live)
        if gone or len({m[0] for m in messages.values()}) != 1:
            bye = struct.pack('<IIQI', MAGIC, 1, 0, 0)
            for index in live:
                if index not in gone or survive:
                    try:
                        conns[index].sendall(bye)
                    except OSError:
                        pass
            break
        frame = next(iter(messages.values()))[0]
        for index in live:
            records = [r for other in live if other != index for r in messages[other][2]]
            try:
                conns[index].sendall(struct.pack('<IIQI', MAGIC, 0, frame, len(records)) + b''.join(records))
            except OSError:
                pass
        frames += 1
    print('hub: %d machines, %d frames' % (len(conns), frames))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
