#!/usr/bin/env python3
"""Talks to a running playable build over its control socket.

Start the application with a control socket (after "--" play.sh passes options on):

    tools/play-net/play.sh --disc IMAGE -- --rta-control /tmp/rta-p1.sock

then, from another terminal:

    tools/play-net/ctl.py /tmp/rta-p1.sock info
    tools/play-net/ctl.py /tmp/rta-p1.sock "tap cross" "wait 60" "shot /tmp/x.bmp"

One command per argument (or per line of standard input with "-"); each is answered
with one line. Commands (buttons are joined with '+': up down left right cross circle
square triangle l1 l2 l3 r1 r2 r3 start select):

    press <buttons>          hold buttons down (on top of keyboard and controller)
    release <buttons>|all
    tap <buttons> [hold [after]]   press for 'hold' frames (8), then wait 'after' (8)
    stick <l|r> <x> <y>      0..255, 128 128 gives the stick back to the player
    wait <frames>            a frame is one vertical blank, 59.94 a second
    peek <expression> <type> read the game's memory: numbers, + and -, [x] for the word
                             at x; types u8 u16 u32 s32 x32 f32 strN wstrN hexN
    shot <file.bmp>          a picture of the window's contents
    shotfb <file.bmp>        the picture as the machine drew it: the console's 640 x 448
                             times the resolution factor, whatever the window's size
    burst <name> <n>         n consecutive presented pictures, <name>-0.bmp ..., with
                             the clock of each in <name>-times.txt
    probe <file> <n> <x> <y> <w> <h>   a rectangle of n consecutive presented pictures,
                             raw, and "<index> <clock> <w> <h>" lines in <file>.txt
    sound [reset]            the sound handler's counts (times dry, pieces thrown away,
                             milliseconds queued, rate, samples at full scale)
    uishot controls|online|about <file.png>   a picture of one of our windows
    pads                     the game controller: attached, its name, what is pressed
    gcpad connect|disconnect|set <buttons|none> [lx ly rx ry [l2 r2]]
                             a controller made by the program, for testing the map
                             (sticks -1..1, up and right positive; triggers 0..1)
    displaypatch all|N 0|1   a display patch off or on while the game runs
    texmode 0|1|2            textures known by what was sent / by memory / by address
    texreplace 0|1|reload    the pictures of <textures>/replace off or on while the game
                             runs (the same frame with and without); reload: the folder
                             is listed again and every picture read again. "info" then
                             says tex_pending=0 when all that are drawn with are in
    info                     frame number, clocks, thread processor times, the display's
                             rate, executable, network and texture counters
    gs                       the display state: interlace, field, the buffer shown
    pref int|bool <setting> <value>   one of the application's settings, taken up at once
    poke <expression> u8|u32|str <value>   write the game's memory (tests only)
    bench                    how fast the cores are that the two main threads run on
    throttle <0|1>           0: run as fast as the computer can (for measuring)
    ethdrop                  cut the connections to the lobby server (a lost line)
    quit

Pictures are game output: keep them out of the repository. Standard library only.
"""
import socket
import sys


class Control:
    def __init__(self, path, timeout=300):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.file = self.sock.makefile("rw", encoding="utf-8", errors="replace", newline="\n")

    def send(self, command):
        self.file.write(command.strip() + "\n")
        self.file.flush()
        line = self.file.readline()
        if not line:
            raise SystemExit("the application closed the control socket")
        return line.rstrip("\n")

    def ok(self, command):
        answer = self.send(command)
        if not answer.startswith("ok"):
            raise SystemExit("%s -> %s" % (command, answer))
        return answer[3:]

    def close(self):
        self.sock.close()


def main():
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    control = Control(sys.argv[1])
    commands = [line for line in sys.stdin] if sys.argv[2] == "-" else sys.argv[2:]
    status = 0
    for command in commands:
        if not command.strip():
            continue
        answer = control.send(command)
        print(answer)
        if not answer.startswith("ok"):
            status = 1
    control.close()
    return status


if __name__ == "__main__":
    sys.exit(main())
