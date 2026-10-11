#!/usr/bin/env python3
"""Checks for three server fixes (docs/issues/live-rig.md 19.12, S1 to S3; the server's
FIXES.md sections 16 to 18):

  S1  a console that lost its connection comes back without logging in again
  S2  notification 0x41 is twelve bytes on the wire
  S3  a server that stood still does not time its clients out when it runs again

  python3 lobby_fix_checks.py --gateway-port N --timeout CLIENT_TIMEOUT
                              [--pid SERVER_PID --server-dir DIR] [--other-address A]
                              [--only s1,s2,s3] [host]

The console, the wire types and the login flow are those of tools/lobby_e2e_test.py, which
is loaded as a module (from the directory of this file, or from the path in the
environment variable LOBBY_E2E_TEST) and not changed. Every step prints PASS or FAIL
against the fixed behaviour; against a build without the fixes the same steps show the
old behaviour.

This is not part of lobby_e2e_test.py because it needs things that test does not ask
for: a server started with a short client_timeout (--timeout must be the value it was
started with; 15, the minimum, keeps the run to about two minutes), and for S3 a server
that may be stopped: --pid is stopped and continued with SIGSTOP and SIGCONT, and only
when its working directory is --server-dir, so that a server somebody is using is not
stopped by a mistyped number. --other-address is a second address of this machine (its
LAN address); a connection made from it reaches a server on 127.0.0.1 from a different
address than a connection from 127.0.0.1 does. Without it that step fails.
"""
import argparse
import importlib.util
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
E2E = os.environ.get("LOBBY_E2E_TEST") or os.path.join(HERE, "lobby_e2e_test.py")
_spec = importlib.util.spec_from_file_location("lobby_e2e_test", E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

Failed, expect = e2e.Failed, e2e.expect
u8, u16, u32, wstr, enc_wstr = e2e.u8, e2e.u16, e2e.u32, e2e.wstr, e2e.enc_wstr


# ----------------------------------------------------------------------------------------
def new_console(tag, args):
    """A console with an account of its own, logged in."""
    c = e2e.Console(tag, args.host)
    sfx = os.urandom(3).hex()
    c.user, c.handle, c.password = f"fx_{tag.lower()}_{sfx}", f"fx{tag}{sfx}", "fx-" + os.urandom(4).hex()
    e2e.gateway(c, args.gateway_port)
    e2e.create_account(c)
    e2e.login(c)
    return c


def reconnect(c, args, source=None):
    """What the game does by itself when its connection is gone [live-rig.md 19.9]:
    gateway (0x43), lobby, key exchange (0x27). It does not log in."""
    e2e.gateway(c, args.gateway_port)
    c.close()
    if source is None:
        c.connect(*c.lobby)
    else:
        c.tcp = socket.create_connection((c.host, c.lobby[1]), timeout=e2e.IO_TIMEOUT,
                                         source_address=(source, 0))
        c.rx, c.notes = b"", []
    e2e.key_exchange(c)


def enc_wstr_game(s):
    """An encrypted string as the real game writes it: text that is a multiple of 16 bytes
    still gets one more block, so a session id travels as 48 bytes [live-rig.md 19.4]."""
    raw = s.encode("utf-16-le")
    cipher = e2e.CRYPT.encrypt(raw + b"\0" * (len(raw) // 16 * 16 + 16 - len(raw)))
    return u32((len(cipher) + 4) // 2) + u32(len(raw)) + cipher


def ask_list(c, session):
    """The game-list request 0x55 under a session id, byte for byte as the game sends it
    (97 bytes with the length). Returns (result, games, bytes left) with the reply read
    the way the game reads it: eight arrays, whatever the result."""
    body = enc_wstr_game(session) + u16(1) + u32(0) + u32(50) + u32(10) + u32(0) + u8(0) + u32(0) + u32(0)
    assert 4 + 10 + len(body) == 97
    track = c.send(0x55, body)
    code, r = c.reply(0x55, track)
    games = e2e.parse_game_list(r, True)
    return code, games, r.left()


def what_follows(c, wait=1.5):
    """What else the server does on this connection: (length of a 0x41 frame it sent,
    before or after the reply, or None; True if it closed the connection)."""
    frame41, closed = None, False
    try:
        n = c.notification(0x41, timeout=wait)
        if n is not None:
            frame41 = 4 + 2 + 4 + len(n.b)
            c.notification(0xFFFF, timeout=wait)        # nothing has this id; waits for the close
    except Failed:
        closed = True
    except OSError:
        closed = True
    return frame41, closed


def describe(code, games, follows):
    frame41, closed = follows
    return (f"result {code}, {len(games)} game(s)"
            + (f", a 0x41 ({frame41} bytes)" if frame41 else ", no 0x41")
            + (", connection closed" if closed else ", connection left open"))


def refused(c, session, what):
    """The answer a connection without a usable session must get."""
    code, games, left = ask_list(c, session)
    follows = what_follows(c)
    seen = describe(code, games, follows)
    expect(code == 7 and games == [] and left == 0,
           f"{what}: wanted result 7 (\"Invalid Session ID!\") with eight empty arrays, got {seen}")
    expect(follows == (None, False), f"{what}: the server did not leave it at the reply: {seen}")
    expect(c.call(0x0F)[0] == 0, f"{what}: the connection does not answer afterwards")
    return seen


# ----------------------------------------------------------------------------------------
# S1
# ----------------------------------------------------------------------------------------
def s1_resume(args, state):
    """Log in, drop the TCP connection, come back as the game does and ask for the game
    list under the old session id."""
    host = new_console("A", args)                        # tag A: its own address label
    e2e.create_public_game(host, f"fx game {os.urandom(2).hex()}")
    e2e.host_discovery(host, True)
    state["host"] = host
    c = new_console("R", args)
    keys, values, meta = e2e.character_meta(1)
    code, cid, _ = e2e.create_character(c, meta, e2e.character_blob(0x41))
    expect(code == 0 and cid, f"could not create a character before the drop (code {code})")
    code, games, _ = ask_list(c, c.session)
    expect(code == 0 and len(games) == 1, f"before the drop the list was: result {code}, {len(games)} game(s)")
    old = c.session

    c.close()                                            # the connection is gone
    time.sleep(0.3)
    reconnect(c, args)
    code, games, left = ask_list(c, old)
    follows = what_follows(c)
    seen = describe(code, games, follows)
    expect(code == 0 and len(games) == 1 and games[0]["info"] == host.game_info,
           f"the list under the old session id: {seen}")
    expect(follows == (None, False), f"after the list: {seen}")
    # logged in again as the same account, with the character a save goes to
    chars = e2e.list_characters(c)
    expect([x[0] for x in chars] == [cid], f"character list after coming back: {chars}")
    data = e2e.character_blob(0x42, plain=900)
    code, _ = e2e.save_character(c, c, cid, e2e.character_meta(2)[2], data)
    expect(code == 0, f"a save after coming back gave result {code}")
    expect(e2e.load_character(c, cid)[:len(data)] == data, "the save after coming back was not stored")
    code, r = c.call(0x62, enc_wstr(old))
    expect(code == 0, f"friend list after coming back: result {code}")
    # the discovery service knows the session on its new connection: host a game
    e2e.create_public_game(c, f"fx back {os.urandom(2).hex()}")
    e2e.host_discovery(c, True)
    code, games, _ = ask_list(host, host.session)
    expect(code == 0 and len(games) == 2, f"the game hosted after coming back is not listed ({len(games)} games)")
    state["resumed"] = c
    return (f"{seen}; the account's character is listed, saved to and loaded again, "
            "and a game hosted on the new connection is opened and listed")


def s1_timed_out(args, state):
    """The case of live-rig.md 19.9: the server itself drops the connection (here by its
    idle timeout), the console connects again and goes on asking for the game list."""
    c = new_console("D", args)
    old = c.session
    try:
        c.tcp.settimeout(args.timeout + 8)
        started = time.monotonic()
        try:
            dropped = c.tcp.recv(4096) == b""
        except OSError:
            dropped = True
        expect(dropped, "the server sent something instead of dropping the silent connection")
        waited = time.monotonic() - started
        reconnect(c, args)
        rounds = []
        for _ in range(3):                               # the game asks again every ten seconds or so
            code, games, _ = ask_list(c, old)
            follows = what_follows(c, 0.7)
            rounds.append(describe(code, games, follows))
            expect(code == 0 and follows == (None, False), f"list request after the drop: {rounds[-1]}")
        expect(len(e2e.list_characters(c)) == 0 and c.alive(), "not logged in as the account after coming back")
    finally:
        c.close()
        c.udp.close()
    return f"dropped by the server after {waited:.0f} s of silence; three list requests in a row: {rounds[0]}"


def s1_save_first(args, state):
    """During play the first request after coming back is not 0x55 but a character save
    (0x5E and its 0x5D pieces). It must find the session and the character too."""
    c = new_console("P", args)
    old = c.session
    try:
        code, cid, _ = e2e.create_character(c, e2e.character_meta(1)[2], e2e.character_blob(0x51))
        expect(code == 0 and cid, f"could not create a character before the drop (code {code})")
        c.close()
        time.sleep(0.3)
        reconnect(c, args)
        data = e2e.character_blob(0x52, plain=1700)
        code, pieces = e2e.save_character(c, c, cid, e2e.character_meta(7)[2], data)
        expect(code == 0, f"save as the first request after coming back gave result {code}")
        expect(e2e.load_character(c, cid)[:len(data)] == data, "that save was not stored")
        expect(e2e.list_characters(c)[0][1][2] == ("level", "7"), "that save did not replace the summary")
    finally:
        c.close()
        c.udp.close()
    return f"save in {pieces} messages answered with result {code} and stored"


def s1_unknown(args, state):
    """An id nobody has, on a connection that never logged in, and on a gateway port."""
    x = e2e.Console("X", args.host)
    try:
        e2e.gateway(x, args.gateway_port)
        x.connect(*x.lobby)
        e2e.key_exchange(x)
        seen = refused(x, "0123456789ABCDEF", "unknown id on the lobby port")
        refused(x, "0123456789ABCDEF", "the same again on the same connection")
        x.connect(x.host, args.gateway_port)
        refused(x, "0123456789ABCDEF", "unknown id on a gateway port")
    finally:
        x.close()
        x.udp.close()
    return f"lobby port and gateway port: {seen}"


def s1_logged_out(args, state):
    """A session that ended with a logout is over."""
    c = new_console("L", args)
    old = c.session
    try:
        e2e.logout(c)
        reconnect(c, args)
        return "after a logout: " + refused(c, old, "id of a session that logged out")
    finally:
        c.close()
        c.udp.close()


def s1_replaced(args, state):
    """A session whose account has logged in again since is over, and the new one is not
    disturbed."""
    c = new_console("N", args)
    old = c.session
    c.close()
    time.sleep(0.3)
    e2e.login(c)                                         # the account logs in anew
    expect(c.session != old, "the second login returned the old session id")
    x = e2e.Console("X", args.host)
    try:
        x.lobby = c.lobby
        x.connect(*x.lobby)
        e2e.key_exchange(x)
        seen = refused(x, old, "id of a session replaced by a newer login")
        expect(c.alive(), "the newer session's connection died")
    finally:
        x.close()
        x.udp.close()
        c.close()
        c.udp.close()
    return "after the account logged in again: " + seen


def s1_other_address(args, state):
    """The id is only accepted from the address the session was used from."""
    if not args.other_address:
        raise Failed("no --other-address given")
    c = new_console("O", args)
    old = c.session
    live = new_console("V", args)                        # stays connected throughout
    x = e2e.Console("X", args.host)
    try:
        c.close()
        time.sleep(0.3)
        x.lobby = c.lobby
        reconnect(x, args, source=args.other_address)
        peer = x.tcp.getsockname()[0]
        expect(peer == args.other_address, f"the test connection left from {peer}")
        seen = refused(x, old, f"lost session presented from {args.other_address}")
        refused(x, live.session, f"live session presented from {args.other_address}")
        expect(what_follows(live, 0.5) == (None, False) and live.alive(),
               "the connection that holds the live session was disturbed")
        # the refusal has not used the lost session up: its own address still gets it
        reconnect(c, args)
        code, games, _ = ask_list(c, old)
        expect(code == 0, f"from the session's own address afterwards: result {code}")
        expect(what_follows(c, 0.5) == (None, False), "closed after coming back")
    finally:
        for y in (x, c, live):
            y.close()
            y.udp.close()
    return (f"from {args.other_address}: {seen}; a live session is refused the same way and its "
            "connection is left alone; from 127.0.0.1 the lost session is then picked up")


def s1_still_held(args, state):
    """Only a session whose connection is gone can be picked up. While a connection holds
    it, the id gets nobody else in, from the same address either, and the holder is not
    disturbed."""
    c = new_console("T", args)
    x = e2e.Console("X", args.host)
    try:
        x.lobby = c.lobby
        x.connect(*x.lobby)
        e2e.key_exchange(x)
        seen = refused(x, c.session, "id of a session another connection holds")
        expect(what_follows(c, 0.5) == (None, False) and c.alive(),
               "the connection that holds the session was disturbed")
        code, games, _ = ask_list(c, c.session)
        expect(code == 0, f"the holder's own list request gave {code}")
    finally:
        x.close()
        x.udp.close()
        c.close()
        c.udp.close()
    return f"second connection: {seen}; the first keeps working"


def s1_expiry(args, state):
    """A lost session is kept for client_timeout seconds, not for ever."""
    c = new_console("E", args)
    old = c.session
    try:
        c.close()
        wait = args.timeout + 3
        time.sleep(wait)
        reconnect(c, args)
        return f"{wait} s after the drop: " + refused(c, old, "id of a session lost longer ago than client_timeout")
    finally:
        c.close()
        c.udp.close()


# ----------------------------------------------------------------------------------------
# S2
# ----------------------------------------------------------------------------------------
def s2_length(args, state):
    """0x41 as the game reads it [0x387388, case at 0x388654]: u16 id, u32 0, one u16."""
    c = new_console("F", args)
    old_tcp, data = c.tcp, c.rx
    c.tcp = None
    try:
        c.connect(*c.lobby)
        e2e.key_exchange(c)
        code, r = c.call(0x16, enc_wstr(c.user) + enc_wstr(c.password))   # a second login
        expect(code == 0, f"second login gave {code}")
        old_tcp.settimeout(3.0)
        try:
            while True:
                chunk = old_tcp.recv(4096)
                if not chunk:
                    break
                data += chunk
        except OSError:
            raise Failed("the earlier connection was left open")
    finally:
        old_tcp.close()
        c.close()
        c.udp.close()
    want = bytes.fromhex("0000000c" "4100" "00000000" "0000")
    expect(data == want, f"0x41 on the wire is {data.hex()} ({len(data)} bytes), the game reads "
                         f"{want.hex()} ({len(want)} bytes)")
    return f"{data.hex()}: {len(data)} bytes, length field {struct.unpack('>I', data[:4])[0]}"


# ----------------------------------------------------------------------------------------
# S3
# ----------------------------------------------------------------------------------------
def check_pid(args):
    if not args.pid or not args.server_dir:
        raise Failed("needs --pid and --server-dir of a server that may be stopped")
    out = subprocess.run(["lsof", "-a", "-p", str(args.pid), "-d", "cwd", "-Fn"],
                         capture_output=True, text=True).stdout
    cwd = [line[1:] for line in out.splitlines() if line.startswith("n")]
    if not cwd or os.path.realpath(cwd[0]) != os.path.realpath(args.server_dir):
        raise Failed(f"process {args.pid} runs in {cwd}, not in {args.server_dir}; it is not stopped")


def s3_sleep(args, state):
    """Stop the server for longer than its timeout, with data waiting for it from one
    client and nothing from another, and let it run again."""
    check_pid(args)
    talker = new_console("W", args)      # sends while the server stands still
    quiet = new_console("Q", args)       # says nothing while it stands still, then speaks
    silent = new_console("Z", args)      # says nothing ever again: must still be timed out
    pause = args.timeout + 5
    try:
        for c in (talker, quiet, silent):
            expect(c.alive(), f"{c.tag} not answering before the pause")
        os.kill(args.pid, signal.SIGSTOP)
        stopped = time.monotonic()
        try:
            time.sleep(2)
            # an empty keep-alive frame and a request, as a console sends them; nobody reads them yet
            talker.track += 1
            payload = u16(0x24) + u32(talker.track) + u32(e2e.RTA_VERSION) + enc_wstr(talker.session)
            talker.send_raw(struct.pack(">I", 4) + struct.pack(">I", len(payload) + 4) + payload)
            time.sleep(pause - 2)
        finally:
            os.kill(args.pid, signal.SIGCONT)
        resumed = time.monotonic()
        stood = resumed - stopped

        try:
            code, _ = talker.reply(0x24, talker.track, timeout=3.0)
        except (Failed, OSError) as e:
            raise Failed(f"the client whose request was waiting unread got no answer when the "
                         f"server ran again after {stood:.0f} s: {e}")
        expect(code == 0, f"waiting request answered with {code}")
        follows = what_follows(quiet, 2.0)
        expect(follows == (None, False),
               f"the client that had sent nothing during the pause was dropped when the server ran again {follows}")
        expect(quiet.alive() and talker.alive(), "a client stopped answering after the pause")
        # the timeout itself still works, counted in time the server was running
        gone = False
        while not gone and time.monotonic() - resumed < args.timeout + 10:
            ready, _, _ = select.select([silent.tcp], [], [], 4.0)
            if ready:
                try:
                    gone = silent.tcp.recv(4096) == b""
                except OSError:
                    gone = True
            else:                                        # the others go on talking meanwhile
                expect(talker.alive() and quiet.alive(), "a talking client died while waiting")
        took = time.monotonic() - resumed
        expect(gone, f"a client that stays silent was still connected {took:.0f} s after the pause")
        expect(took > 3, f"the silent client was dropped {took:.1f} s after the pause, with the pause counted")
        expect(talker.alive(), "the talking client died meanwhile")
    finally:
        try:
            os.kill(args.pid, signal.SIGCONT)
        except OSError:
            pass
        for c in (talker, quiet, silent):
            c.close()
            c.udp.close()
    return (f"server stood still {stood:.0f} s (timeout {args.timeout} s): the waiting request was "
            f"answered, the quiet client kept its connection, and a client that stayed silent was "
            f"dropped {took:.0f} s after the server ran again")


# ----------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host", nargs="?", default="127.0.0.1")
    ap.add_argument("--gateway-port", type=int, required=True)
    ap.add_argument("--timeout", type=int, required=True, help="the server's client_timeout")
    ap.add_argument("--pid", type=int, default=0, help="server process, for S3")
    ap.add_argument("--server-dir", default="", help="the directory that process must be running in")
    ap.add_argument("--other-address", default="")
    ap.add_argument("--only", default="s1,s2,s3")
    args = ap.parse_args()
    only = set(args.only.split(","))
    state = {}
    steps = []
    if "s1" in only:
        steps += [
            ("S1  drop, reconnect, 0x55 under the old session id", s1_resume),
            ("S1  the server drops a silent connection; the console comes back", s1_timed_out),
            ("S1  the first request after coming back is a character save", s1_save_first),
            ("S1  an id nobody has", s1_unknown),
            ("S1  the id of a session that logged out", s1_logged_out),
            ("S1  the id of a session replaced by a newer login", s1_replaced),
            ("S1  the id presented from another address", s1_other_address),
            ("S1  the id of a session another connection still holds", s1_still_held),
            ("S1  the id of a session lost longer ago than client_timeout", s1_expiry),
        ]
    if "s2" in only:
        steps += [("S2  length of notification 0x41", s2_length)]
    if "s3" in only:
        steps += [("S3  the server stands still for longer than client_timeout", s3_sleep)]
    failed = 0
    for n, (title, fn) in enumerate(steps, 1):
        try:
            detail = fn(args, state)
            print(f"PASS {n:2d}  {title}\n         {detail}")
        except Failed as e:
            failed += 1
            print(f"FAIL {n:2d}  {title}\n         {e}")
        except (OSError, struct.error) as e:
            failed += 1
            print(f"FAIL {n:2d}  {title}\n         {type(e).__name__}: {e}")
    for c in (state.get("host"), state.get("resumed")):
        if c is not None:
            c.close()
            c.udp.close()
    print(f"\nRESULT: {'FAIL' if failed else 'PASS'} ({len(steps) - failed} of {len(steps)} steps passed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
