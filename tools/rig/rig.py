#!/usr/bin/env python3
"""Wrapper around the rta_rig runner (see README.md in this directory).

It saves typing: it finds the runner and the disc image, loads every symbol file of the
repository (names.tsv, symbols/*.tsv) so that names can be used in watches and break
points, keeps the emulator's data under local/rig-out/, and offers a few presets. Every
other argument is passed to the runner unchanged.

    python3 -I -B tools/rig/rig.py --frames 600 --watch g_randSeed:x32
    python3 -I -B tools/rig/rig.py --screen-text --script my.rig
    python3 -I -B tools/rig/rig.py watches g_randSeed:x32 g_drawFrame:u32
                                       prints name=address:type pairs for the runner
    python3 -I -B tools/rig/rig.py session start|send|stop ...
                                       keep one runner alive and feed it commands
    python3 -I -B tools/rig/rig.py pair OUTDIR ...
                                       two joined machines playing one net game

Environment:
    RTA_DISC   path of the disc image (or pass --disc)
    RTA_RIG    path of the rta_rig executable (default local/rig-build/rta_rig)

Standard library only. No game data is read or written by this file.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Text drawing entry points (symbols/engine.tsv). All take the 16-bit string in $a2.
TEXT_HOOKS = ("text_drawWideImpl", "text_drawWrapped", "text_drawWrappedCentered")


def symbol_files():
    files = [os.path.join(ROOT, "names.tsv")]
    files += sorted(glob.glob(os.path.join(ROOT, "symbols", "*.tsv")))
    return [f for f in files if os.path.exists(f)]


def load_symbols():
    table = {}
    for path in symbol_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 2 or line.startswith("#"):
                    continue
                try:
                    address = int(fields[0], 16)
                except ValueError:
                    continue
                table.setdefault(fields[1], address)
    return table


def watch_pairs(specs):
    """'name:type' -> 'name=0xaddress:type' using the repository's symbol files."""
    table = load_symbols()
    pairs = []
    for spec in specs:
        name, _, kind = spec.partition(":")
        if name not in table:
            raise SystemExit("unknown symbol: %s" % name)
        pairs.append("%s=0x%x:%s" % (name, table[name], kind or "x32"))
    return pairs


def runner_command(argv):
    runner = os.environ.get("RTA_RIG", os.path.join(ROOT, "local", "rig-build", "rta_rig"))
    if not os.path.exists(runner):
        raise SystemExit("runner not built: %s (see tools/rig/README.md)" % runner)

    out_dir = os.path.join(ROOT, "local", "rig-out")
    os.makedirs(out_dir, exist_ok=True)

    command = [runner]
    passed = list(argv)
    if "--disc" not in passed:
        disc = os.environ.get("RTA_DISC")
        if not disc:
            raise SystemExit("set RTA_DISC to the disc image, or pass --disc")
        command += ["--disc", disc]
    if "--data" not in passed:
        command += ["--data", os.path.join(out_dir, "playdata")]
    for path in symbol_files():
        command += ["--sym", path]

    if "--screen-text" in passed:
        passed.remove("--screen-text")
        for name in TEXT_HOOKS:
            command += ["--break", "%s,wstr=a2,collect" % name]

    command += passed
    return command


# --- interactive sessions -----------------------------------------------------------
#
# One runner process is kept alive with its command input on a named pipe, so a state
# is loaded (and its code re-translated) once, and menus can be explored a step at a
# time:
#
#     rig.py session start --screen-text --load local/rig-out/states/x.zip
#     rig.py session send "tap cross" "wait 60" "show g_levelName:str32"
#     rig.py session stop
#
# 'send' prints everything the runner wrote while it carried the commands out.

def session_paths(name):
    base = os.path.join(ROOT, "local", "rig-out", "session-" + name)
    return base, os.path.join(base, "in.fifo"), os.path.join(base, "out.log"), os.path.join(base, "pid")


def session_alive(pid_path):
    try:
        with open(pid_path) as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return 0


def session_send(name, lines, timeout):
    import time
    base, fifo, log, pid_path = session_paths(name)
    if not session_alive(pid_path):
        raise SystemExit("no session '%s' is running" % name)
    token = "%d" % time.time_ns()
    offset = os.path.getsize(log)
    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, ("\n".join(lines) + "\nsync %s\n" % token).encode())
    finally:
        os.close(fd)
    marker = "[sync %s]" % token
    deadline = time.time() + timeout
    seen = ""
    while True:
        with open(log, errors="replace") as handle:
            handle.seek(offset)
            seen = handle.read()
        if marker in seen or not session_alive(pid_path):
            break
        if time.time() > deadline:
            sys.stdout.write(seen)
            raise SystemExit("\n(timed out after %ds; the session is still running)" % timeout)
        time.sleep(0.05)
    sys.stdout.write(seen)
    return 0


def session(argv):
    import subprocess
    import time
    name = "default"
    timeout = 600
    while argv and argv[0] in ("--name", "--timeout"):
        if argv[0] == "--name":
            name = argv[1]
        else:
            timeout = int(argv[1])
        argv = argv[2:]
    if not argv:
        raise SystemExit("session start|send|stop|status")
    action, rest = argv[0], argv[1:]
    base, fifo, log, pid_path = session_paths(name)
    if action == "start":
        if session_alive(pid_path):
            raise SystemExit("session '%s' is already running" % name)
        os.makedirs(base, exist_ok=True)
        if os.path.exists(fifo):
            os.unlink(fifo)
        os.mkfifo(fifo)
        command = runner_command(rest + ["--interactive"])
        # opened for reading and writing so the runner never sees end of input
        stdin = os.open(fifo, os.O_RDWR)
        with open(log, "w") as out:
            process = subprocess.Popen(command, stdin=stdin, stdout=out, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        os.close(stdin)
        with open(pid_path, "w") as handle:
            handle.write("%d\n" % process.pid)
        return session_send(name, [], timeout)
    if action == "send":
        return session_send(name, rest, timeout)
    if action == "status":
        pid = session_alive(pid_path)
        print("running, pid %d" % pid if pid else "not running")
        return 0
    if action == "stop":
        pid = session_alive(pid_path)
        if pid:
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, b"quit\n")
            os.close(fd)
            for _ in range(200):
                if not session_alive(pid_path):
                    break
                time.sleep(0.05)
            if session_alive(pid_path):
                os.kill(pid, 9)
        with open(log, errors="replace") as handle:
            tail = handle.read().splitlines()[-12:]
        print("\n".join(tail))
        return 0
    raise SystemExit("session start|send|stop|status")


# --- two machines -------------------------------------------------------------------
#
#     rig.py pair OUTDIR [--bus delay=2,seed=7] [--a-arg X] [--b-arg X] <runner options>
#
# starts two runners joined by a local socket (see --link in the README): machine A is
# 192.168.1.132 and plays slot 1, machine B is 192.168.1.134 and plays slot 0. Both get
# the same options and the same script; script lines tagged "A:" or "B:" act on one
# machine. Each machine writes OUTDIR/a.* or b.*: the runner's output (.out), the shim's
# log (.net.log) and one row per lockstep tick (.tick.tsv) with the columns below.
# Columns whose name starts with "l_" are per machine by design; compare.py skips them.

# The lobby lists peers by the last octet of their address, highest first (seen: the
# stick of the .132 machine moves player 1).
PAIR = {"A": ("192.168.1.132", 1, "listen"), "B": ("192.168.1.134", 0, "connect")}


def tick_watches(local_slot):
    """Default columns of the tick log, as --tick-watch arguments."""
    record = lambda n: "g_players+%d" % (n * 0x4C30)
    peer = lambda n: "g_peers+%d" % (n * 0x44E0)
    specs = [
        "net=g_netFrame:s32",
        "seed=g_randSeed:x32",
        "level=g_levelName:str12",
        "nplayers=g_numPlayers:s32",
        # the per-slot button maps 0x41b980..0x41ba3f (FINDINGS U1)
        "btnmaps=0x41b980:crc192",
        # the sync record the game stored for the previous tick, from this machine's ring
        "prevhash=%s+0x18ac+((g_netFrame-1)&0xff)*12+8:x32" % peer(local_slot),
        "l_inp=g_localInputFrame:s32",
        "l_cosmetic=g_cosmeticSeed:x32",
        "l_drawframe=g_drawFrame:u32",
    ]
    for n in (0, 1):
        obj = "[%s+0x43d8]" % record(n)
        specs += [
            "p%dx=%s+0x10:x32" % (n, obj), "p%dy=%s+0x14:x32" % (n, obj), "p%dz=%s+0x18:x32" % (n, obj),
            "p%dangle=%s+0x38:u16" % (n, obj), "p%dstate=%s+0x58c:s32" % (n, obj),
            "p%dobjseed=%s+0x44:x32" % (n, obj),
            "p%dhp=%s+0xac:x32" % (n, record(n)), "p%dmana=%s+0xc0:x32" % (n, record(n)),
            "p%dgold=%s+0xe4:s32" % (n, record(n)), "p%dexp=%s+0x5c:s32" % (n, record(n)),
            "p%dbag0=%s+0x130:crc4612" % (n, record(n)), "p%dbag1=%s+0x1338:crc4612" % (n, record(n)),
            "p%dbag2=%s+0x2540:crc4612" % (n, record(n)),
            # level, experience, statistics, points, passives; equipment; ability records;
            # skill ranks (docs/player.md has the offsets)
            "p%dstats=%s+0x58:crc84" % (n, record(n)), "p%dpoints=%s+0xe4:crc59" % (n, record(n)),
            "p%dequip=%s+0x43f0:crc80" % (n, record(n)), "p%dabil=%s+0x4440:crc1560" % (n, record(n)),
            "p%dskills=%s+0x4b08:crc192" % (n, record(n)),
            # out-of-sync flag this machine holds for peer n; they are per machine but a
            # 1 anywhere is what the comparison is looking for, so they are compared too
            "oos%d=%s+0x44d7:u8" % (n, peer(n)),
            "l_dropped%d=%s+0x44d5:u8" % (n, peer(n)),
        ]
    result = []
    for spec in specs:
        result += ["--tick-watch", spec]
    return result


def pair(argv):
    import subprocess
    import tempfile
    if not argv:
        raise SystemExit("pair OUTDIR [--bus spec] [--a-arg X] [--b-arg X] <runner options>")
    out_dir = os.path.abspath(argv[0])
    os.makedirs(out_dir, exist_ok=True)
    rest = argv[1:]
    own = {"A": [], "B": []}
    common = []
    index = 0
    booted = True
    while index < len(rest):
        if rest[index] in ("--a-arg", "--b-arg"):
            own[rest[index][2].upper()].append(rest[index + 1])
            index += 2
            continue
        if rest[index] in ("--a-load", "--b-load"):
            own[rest[index][2].upper()] += ["--load", rest[index + 1]]
            booted = False
            index += 2
            continue
        common.append(rest[index])
        index += 1
    link_dir = os.environ.get("RTA_LINK_DIR", tempfile.gettempdir())
    link = os.path.join(link_dir, "rig-%d.sock" % os.getpid())
    # RTA_PAIR_DATA: where the two machines' data directories (a, b) are; several pairs
    # running at once must not share memory cards
    data_root = os.environ.get("RTA_PAIR_DATA", os.path.join(ROOT, "local", "rig-out", "pair-"))
    processes = []
    for letter in ("A", "B"):
        address, slot, mode = PAIR[letter]
        low = letter.lower()
        args = ["--machine", letter, "--net-shim", address, "--link", "%s:%s" % (mode, link),
                "--data", data_root + low,
                "--net-log", os.path.join(out_dir, low + ".net.log"),
                "--tick-log", os.path.join(out_dir, low + ".tick.tsv")]
        args += tick_watches(slot)
        if booted:
            args += ["--arg", "--net"]
        # %M in an option stands for the machine's letter in lower case
        extra = [value.replace("%M", low) for value in common + own[letter]]
        command = runner_command(args + extra)
        out = open(os.path.join(out_dir, low + ".out"), "w")
        processes.append((letter, subprocess.Popen(command, stdout=out, stderr=subprocess.STDOUT), out))
    status = 0
    for letter, process, out in processes:
        code = process.wait()
        out.close()
        # 6 means "the other machine ended first", which is how a pair normally ends
        if code not in (0, 6):
            status = code
        with open(out.name, errors="replace") as handle:
            lines = [l for l in handle.read().splitlines() if "CMIPSAnalysis" not in l and " screen: " not in l]
        print("== machine %s, exit code %d" % (letter, code))
        print("\n".join(l[:300] for l in lines[-int(os.environ.get("RTA_PAIR_TAIL", "12")):]))
    return status


def main(argv):
    if argv and argv[0] == "pair":
        return pair(argv[1:])
    if argv and argv[0] == "watches":
        print(" ".join("--watch " + pair for pair in watch_pairs(argv[1:])))
        return 0
    if argv and argv[0] == "session":
        return session(argv[1:])
    command = runner_command(argv)
    os.execv(command[0], command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
