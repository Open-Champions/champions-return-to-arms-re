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
    shotview <file.bmp>      the part of that picture that is presented: without its
                             outermost line and column (see "edge")
    burst <name> <n>         n consecutive presented pictures, <name>-0.bmp ..., with
                             the clock of each in <name>-times.txt
    probe <file> <n> <x> <y> <w> <h>   a rectangle of n consecutive presented pictures,
                             raw, and "<index> <clock> <w> <h>" lines in <file>.txt
    sound [reset]            the sound handler's counts (times dry, pieces thrown away,
                             milliseconds queued, rate, samples at full scale)
    uishot controls|online|about|playername|playername2|gamecode|host|join|setwarning <file.png>
                             a picture of one of our windows
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
    texcrop 0|1              1 (the default): only the part of a replacement the game
                             draws with is given to the graphics card; 0: all of it.
                             Every picture is read again ("info": tex_cropped, tex_regrown)
    texmemory <MB>           what --rta-texture-memory sets, in the running game
    texorder 0|1             the replacement pictures are read in the order they were
                             asked for (0) or what covers most of the screen first (1,
                             the default)
    upscale 0|1              at a resolution factor above 1: point-sampled effect sprites,
                             the automap, points and lines as the console draws them (0)
                             or filtered and a console pixel wide (1, the default)
    texcentre 0|1            filtered indexed textures read as Play! has it, half a texel
                             off (0), or round the place asked for (1, the default)
    edge 0|1                 the whole of the console's picture is presented (0), or all
                             but its outermost line and column, which a television does
                             not show (1, the default)
    drawlog <file> [frames [x0 y0 x1 y1]]
                             how the game draws: a line for every draw of the next frames
                             (1) with its GS registers and texture; with a rectangle (in
                             pixels of the buffer drawn to) every primitive that touches it,
                             vertex by vertex
    info                     frame number, clocks, thread processor times, the display's
                             rate, executable, network and texture counters
    gs                       the display state: interlace, field, the buffer shown
    pref int|bool <setting> <value>   one of the application's settings, taken up at once
    poke <expression> u8|u32|str <value>   write the game's memory (tests only)
    bench                    how fast the cores are that the two main threads run on
    throttle <0|1>           0: run as fast as the computer can (for measuring)
    ethdrop                  cut the connections to the lobby server (a lost line)
    online                   where the one-step log-in is: stage, outcome, whether a login
                             is saved (never a name or a password)
    online start [lobby|host[:CODE]|join:CODE]
                             as "Play Online", "Host a game" and "Join a game" in the
                             menu: by itself to the lobby's game list, into the room of
                             a game of one's own named with a code (made up when none is
                             given), or into the room of the game with the given code.
                             Host and join take the character used last; "+choose" at
                             the end (host+choose) leaves the character screens alone
    peers                    this copy's patch set and, for every other player heard
                             from, the set its copy told (or ?), with the warning
    hw                       the machine's interrupt and DMA registers (what a stopped game
                             waits for): INTC, DMAC with channels 1 and 2, VIF1, GIF, GS
    cpu                      where the main processor is, whether the game is taken to be
                             stuck, the longest stretch without drawing
    note                     the status bar's note about the game (network screen, stuck)
    reset                    what Reset in the menu does
    hang <seconds>           stop the machine's own thread (a stand-in for an emulator
                             that is stuck); "<socket>.ui" with reset, escape or close in
                             it reaches the application meanwhile
    online name NAME         the player name, when a background test run waits for one
    online stop | forget     stop pressing / delete the saved login for this server
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
