#!/usr/bin/env python3
"""capture.py - turn a break-point log of the emulator rig into a sound capture file.

A sound capture is everything the game sent to the sound side of the I/O processor in one
run: the remote calls to the two sound servers with their argument blocks, the data it
copied into I/O-processor memory for them (register batches, sample uploads) and the disc
reads it made straight into the stream buffers there.  `sndtool replay` plays a capture
through the same three functions the native runtime calls.

Record the log with the rig (tools/rig/README.md), from power-on so that every sample
upload is in it.  The rig prints at most about 490 bytes per memory dump, and a copy is up
to 4,096 bytes, so the copy is logged in nine pieces:

  PIECES=$(python3 -c "print(','.join('mem=\\$a0+%d:480' % (i * 480) for i in range(9)))")

  python3 -I -B tools/rig/rig.py --data local/sound/cap/rigdata --script SCRIPT.rig \\
      --break '0x00356510,name=bind' --break '0x003566f0,name=rpc,mem=$a3:96' \\
      --break "0x0035ed90,name=toiop,$PIECES" \\
      --break 'sample_register,name=sreg,str=a0' --break '0x002134e8,name=play' \\
      --break '0x002113c8,name=squeue,str=a1' --break-log local/sound/cap/cap.log

  python3 -I -B tools/recomp/sound/capture.py local/sound/cap/cap.log local/sound/cap/cap.bin

0x356510 is sceSifBindRpc (client, server number), 0x3566f0 sceSifCallRpc (client,
function, mode, send, send size, receive, receive size), 0x35ed90 the sound library's copy
to I/O-processor memory (source, destination, size).  The last three break points only add
labels: sample names as they are registered, sound_playSample calls, stream queue entries.

The capture holds game data (ADPCM): it stays under local/.  Standard library only.

File: "RTASND1\\0", then records { u32 type, u32 frame, u32 length, payload }:
  1 remote call   server, function, send address, send size, receive address, receive size, send bytes
  2 memory write  I/O-processor address, bytes
  3 disc read     I/O-processor address, first sector, sector count
  4 label         text
"""
import re
import struct
import sys

SOUND = (0x80000701, 0x000163A5)
DISC = 0x80000595
LINE = re.compile(r'frame=(\d+) bp=(\w+) pc=\w+ ra=(\w+)\(([^)]*)\) a0=(\w+) a1=(\w+) a2=(\w+) a3=(\w+) '
                  r't0=(\w+) t1=(\w+) t2=(\w+) t3=(\w+) v0=\w+ sp=\w+ f12=(\S+) f13=(\S+) f14=(\S+)')


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    servers = {}
    names = {}
    counts = {}
    with open(sys.argv[1], encoding='ascii', errors='replace') as source, open(sys.argv[2], 'wb') as sink:
        sink.write(b'RTASND1\0')

        def record(kind, frame, payload):
            sink.write(struct.pack('<III', kind, frame, len(payload)) + payload)
            counts[kind] = counts.get(kind, 0) + 1

        for line in source:
            m = LINE.match(line)
            if not m:
                continue
            frame = int(m.group(1))
            point, caller = m.group(2), m.group(4).split('+')[0]
            a0, a1, a2, a3, t0, t1, t2 = (int(m.group(i), 16) for i in range(5, 12))
            data = b''.join(bytes.fromhex(piece) for piece in re.findall(r'mem\[[^\]]*\]=((?:[0-9a-f]{2})*)', line))
            text = re.search(r'a\d->"(.*)"', line)
            if point == 'bind':
                servers[a0] = a1
            elif point == 'rpc':
                server = servers.get(a0)
                if server in SOUND:
                    record(1, frame, struct.pack('<6I', server, a1, a3 & 0x1FFFFFFF, t0, t1 & 0x1FFFFFFF, t2) + data[:t0])
                elif server == DISC and a1 == 0x0D and len(data) >= 12:
                    sector, count, address = struct.unpack_from('<3I', data)
                    record(3, frame, struct.pack('<3I', address, sector, count))
            elif point == 'toiop':
                if len(data) < a2:
                    sys.exit('frame %d: a copy of %d bytes was logged with %d' % (frame, a2, len(data)))
                record(2, frame, struct.pack('<I', a1) + data[:a2])
            elif point == 'sreg':
                names[a1] = text.group(1) if text else '?'
                record(4, frame, ('sample %08x %s' % (a1, names[a1])).encode())
            elif point == 'play':
                record(4, frame, ('play %s pitch=%s volume=%s delay=%s from=%s' % (
                    names.get(a0, "%08x" % a0), m.group(13), m.group(14), m.group(15), caller)).encode())
            elif point == 'squeue':
                record(4, frame, ('queue stream=%d file=%s flags=%x offset=%x length=%x rate=%d channels=%d from=%s' % (
                    a0, text.group(1) if text else '?', a2, a3, t0, t1, t2 + 1, caller)).encode())
    print('remote calls %d, memory writes %d, disc reads %d, labels %d' % tuple(counts.get(k, 0) for k in (1, 2, 3, 4)))


if __name__ == '__main__':
    main()
