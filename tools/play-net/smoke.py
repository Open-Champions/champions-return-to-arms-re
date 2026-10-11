#!/usr/bin/env python3
"""Smoke test of the playable build: power-on to the lobby server's first screen.

Starts the application through play.sh with a control socket, presses its way from the
memory-card prompt to the title screen, chooses "Start New Game" and "Internet Game",
accepts the network setting, and waits for the lobby server's first screen (its terms
text). It prints what the built-in network did and how fast the machine ran, and can
write pictures of each stage.

    tools/play-net/smoke.py --disc IMAGE [--server ADDRESS] [--player N]
                            [--shots DIR] [--pcap FILE] [--keep] [--offline]

    --shots DIR   pictures (BMP) of each stage; game output, keep it out of the repository
    --keep        leave the application running at the end (its control socket is printed)
    --offline     stop at the title screen

It stops at the terms screen: accepting a server's terms and logging in are for a person
to do. Nothing here needs an account. Exit code 0 when every stage was reached.

Addresses read from the game (names.tsv): g_inFrontend 0x41b510, g_levelName 0x41b721,
g_drawFrame 0x44fdd0. Standard library only.
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from ctl import Control  # noqa: E402

G_IN_FRONTEND = 0x41B510
G_LEVEL_NAME = 0x41B721
G_DRAW_FRAME = 0x44FDD0


class Machine:
    """One running application and its control socket."""

    def __init__(self, player=1, disc=None, server=None, shots=None, pcap=None, extra=(), log=None):
        self.player = player
        self.shots = shots
        self.data = os.path.join(ROOT, "local", "play-data", "player%d" % player)
        self.socket_path = os.path.join(ROOT, "local", "play-data", "p%d.sock" % player)
        command = [os.path.join(HERE, "play.sh"), "--player", str(player)]
        if disc:
            command += ["--disc", disc]
        if server:
            command += ["--server", server]
        command += ["--", "--rta-control", self.socket_path]
        if pcap:
            command += ["--rta-pcap", pcap]
        command += list(extra)
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        self.log_path = log or os.path.join(ROOT, "local", "play-data", "p%d.out" % player)
        self.process = subprocess.Popen(command, stdout=open(self.log_path, "w"), stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.time() + 60
        while not os.path.exists(self.socket_path):
            if self.process.poll() is not None or time.time() > deadline:
                raise SystemExit("the application did not start; see " + self.log_path)
            time.sleep(0.2)
        self.control = Control(self.socket_path)

    # ---- commands
    def do(self, *commands):
        return [self.control.ok(command) for command in commands][-1]

    def tap(self, buttons, hold=8, after=30):
        self.control.ok("tap %s %d %d" % (buttons, hold, after))

    def wait(self, frames):
        self.control.ok("wait %d" % frames)

    def peek(self, address, kind="u32"):
        expression = address if isinstance(address, str) else "0x%x" % address
        return self.control.ok("peek %s %s" % (expression, kind))

    def info(self):
        text = self.control.ok("info")
        fields = dict(re.findall(r"(\w+)=(\S+)", text))
        return {key: (int(value) if value.lstrip("-").isdigit() else value) for key, value in fields.items()}

    def shot(self, name):
        if not self.shots:
            return None
        os.makedirs(self.shots, exist_ok=True)
        path = os.path.join(self.shots, "p%d-%s.bmp" % (self.player, name))
        self.control.ok("shot " + path)
        return path

    def fps(self, seconds=5.0):
        """(machine frames per second, pictures the game drew per second)"""
        a, da = self.info(), int(self.peek(G_DRAW_FRAME))
        time.sleep(seconds)
        b, db = self.info(), int(self.peek(G_DRAW_FRAME))
        elapsed = (b["ms"] - a["ms"]) / 1000.0
        return (b["frame"] - a["frame"]) / elapsed, (db - da) / elapsed

    def net_log(self):
        with open(self.log_path, errors="replace") as file:
            return [line.rstrip() for line in file if " net: " in line]

    def quit(self):
        try:
            self.control.send("quit")
        except (OSError, SystemExit):
            pass
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate()

    # ---- stages
    def to_title(self):
        """Memory-card prompt and logos, by pressing cross until the front end is up."""
        for _ in range(60):
            if self.peek(G_IN_FRONTEND, "u8") == "1" and self.peek(G_LEVEL_NAME, "str8") == "intro":
                break
            self.tap("cross", 6, 40)
        else:
            raise SystemExit("the front end did not come up")
        self.wait(420)          # the title's own fade-in

    def to_network_menu(self):
        self.tap("cross", 8, 90)        # Start New Game -> Normal Game / Internet Game
        self.tap("down", 8, 20)
        self.tap("cross", 8, 300)       # Internet Game -> the saved network setting

    def to_lobby(self, timeout_frames=3600):
        """Accept the setting; wait for the lobby server's first reply after its key
        exchange (the terms text: several hundred bytes)."""
        self.tap("cross", 8, 60)
        waited = 0
        while waited < timeout_frames:
            info = self.info()
            if info.get("tcp", 0) >= 2 and info.get("tcp_in", 0) >= 300:
                self.wait(120)
                return True
            self.wait(60)
            waited += 60
        return False


def main():
    parser = argparse.ArgumentParser(description="power-on to the lobby server's first screen")
    parser.add_argument("--disc", default=os.environ.get("RTA_DISC"))
    parser.add_argument("--server")
    parser.add_argument("--player", type=int, default=1)
    parser.add_argument("--shots")
    parser.add_argument("--pcap")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not args.disc:
        raise SystemExit("give --disc IMAGE or set RTA_DISC")

    machine = Machine(args.player, args.disc, args.server, args.shots, args.pcap)
    ok = True
    try:
        machine.wait(120)
        machine.shot("1-boot")
        machine.to_title()
        machine.shot("2-title")
        machine_fps, drawn_fps = machine.fps(5)
        print("title screen reached; %.1f frames a second (full speed is 59.94), %.1f pictures drawn" % (machine_fps, drawn_fps))
        if not args.offline:
            machine.to_network_menu()
            machine.shot("3-network-setting")
            reached = machine.to_lobby()
            machine.shot("4-lobby")
            info = machine.info()
            print("network: address %s, name %s, %d TCP connections, %d bytes out, %d bytes in" % (
                "given" if info.get("dhcp") else "NOT given", "answered" if info.get("dns") else "NOT asked for",
                info.get("tcp", 0), info.get("tcp_out", 0), info.get("tcp_in", 0)))
            for line in machine.net_log():
                print("   " + line)
            print("lobby server's first screen reached" if reached else "the lobby server was NOT reached")
            ok = reached
    finally:
        if args.keep:
            print("left running; control socket " + machine.socket_path)
        else:
            machine.quit()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
