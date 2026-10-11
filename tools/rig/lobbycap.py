#!/usr/bin/env python3
"""Reads a capture written by the rig (--eth-pcap) and lists what the game and the lobby
server said to each other, message by message, in the terms of docs/lobby-protocol.md.

    python3 -I -B tools/rig/lobbycap.py local/rig-out/a.pcap [--udp] [--text] [--hex N]

For every TCP connection of the machine it puts the two byte streams back together, cuts
them into the protocol's frames (a big-endian length that counts itself, then the payload)
and prints one line per frame: the emulated frame number at which the rig saw it, the
direction, the message number and name, the tracking number, the version (requests) or
result (replies), and the body field by field where the layout is known. A reply is read
by the layout of the request that carries the same tracking number, as the game does it.
Encrypted strings are decrypted with the connection's key (the reply to message 0x27,
itself decrypted with the game's built-in key, which tools/lobby_e2e_test.py holds).

Passwords are never printed, only their length. Session ids are shortened. Without --text
other strings are shortened to 40 characters. --udp adds one line per UDP datagram.

The output describes your own capture; like the capture it belongs under local/, not in
the repository. Standard library only.
"""
import argparse
import importlib.util
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

NAMES = {
    0x01: "AddFriend", 0x02: "AddIgnore", 0x05: "CancelGame", 0x06: "CreateAccount", 0x09: "CreatePrivateRoom",
    0x0C: "EnterRoom", 0x0E: "GetPublicRooms", 0x0F: "GetRealmStats", 0x11: "GetRoom", 0x15: "LeaveRoom",
    0x16: "Login", 0x17: "Logout", 0x19: "SetRoomBanner", 0x1C: "RemoveFriend", 0x1D: "RemoveIgnore",
    0x21: "SendInstantMessage", 0x22: "SendRoomMessage", 0x23: "StartGame", 0x24: "TouchSession",
    0x27: "GetEncryptionKey", 0x2F: "FriendStatus", 0x30: "InstantMessage", 0x3D: "RoomMessage",
    0x3E: "GameDiscovered", 0x40: "ClientDiscovered", 0x41: "ForcedLogout", 0x42: "GetRules",
    0x43: "GetServerAddress", 0x44: "UpdateGameData", 0x54: "CreatePublicGame_RTA", 0x55: "MatchGame_RTA",
    0x56: "CreatePrivateGame_RTA", 0x57: "GetGame_RTA", 0x58: "CreateNewCharacter_RTA", 0x5A: "DeleteCharacter_RTA",
    0x5B: "GetNetCharacterList_RTA", 0x5C: "GetNetCharacterData_RTA", 0x5D: "AppendCharacterData",
    0x5E: "SaveCharacter_RTA", 0x5F: "UserJoinSuccess", 0x60: "CancelGame_RTA", 0x61: "GetSocialListInitial",
    0x62: "GetSocialListUpdate", 0x63: "GetIgnoreList", 0x64: "GetAccountInfo", 0x65: "ClientRequestConnect_RTA",
    0x66: "DoClientDiscovery_RTA",
}

# Field lists. Types: u8 u16 u32, wstr (count of 16-bit units, units), nstr and blob (byte
# count, bytes), estr (encrypted wide string), a type followed by [] (count, items),
# chars (the character list of 0x5B), rest (whatever is left, as hex). "name:type"; a name
# starting with ! is never printed, only its length; "sid" is shortened.
S = "sid:estr"
REQUEST = {
    0x43: ["u32"], 0x27: ["key string:nstr", "u32"], 0x42: ["nstr", "nstr"],
    0x06: ["user:estr", "!password:estr", "e-mail:estr", "birth:estr", "handle:estr"],
    0x16: ["user:estr", "!password:estr"], 0x64: ["user:estr", "!password:estr"],
    0x17: [S], 0x24: [S], 0x0E: [S], 0x0F: [], 0x61: [S], 0x62: [S], 0x63: [S], 0x05: [S], 0x60: [S],
    0x0C: [S, "room:wstr"], 0x11: [S, "room:wstr"], 0x15: [S, "room:wstr"], 0x09: [S, "room:wstr"],
    0x01: [S, "handle:wstr"], 0x02: [S, "handle:wstr"], 0x1C: [S, "handle:wstr"], 0x1D: [S, "handle:wstr"],
    0x22: [S, "room:wstr", "text:wstr"], 0x19: [S, "room:wstr", "text:wstr"], 0x21: [S, "handle:wstr", "text:wstr"],
    0x54: [S, "u16", "u32", "u32", "u32", "game info:wstr", "attributes:u32", "blob", "LAN address:wstr", "UDP port:u32", "wstr", "u32"],
    0x56: [S, "game name:wstr", "LAN address:wstr", "UDP port:u32", "wstr", "u32"],
    0x55: [S, "rest"], 0x57: [S, "game name:wstr"],
    0x66: [S, "game id:u32", "LAN address:wstr", "UDP port:u32"],
    0x5F: [S, "host sid:estr"], 0x23: [S, "rest"],
    0x5B: [S, "u32"], 0x5C: [S, "character id:u32"], 0x5A: [S, "character id:u32", "u32"],
    0x58: [S, "u32", "u32", "keys:wstr[]", "values:wstr[]", "first piece:blob", "u32"],
    0x5E: [S, "target sid:estr", "character id:u32", "u32", "u32", "keys:wstr[]", "values:wstr[]", "first piece:blob", "u32"],
    0x5D: [S, "piece:blob", "last:u32"],
}
REPLY = {
    0x43: ["address:nstr", "port:u32"], 0x27: ["key blob:blob"], 0x42: ["text:wstr"],
    0x06: [S], 0x16: [S, "handle:estr"],
    0x0E: ["names:wstr[]", "wstr[]", "u32[]", "u32[]"], 0x0F: ["u32"] * 8,
    0x0C: ["room:wstr", "text:wstr", "members:wstr[]", "moderators:wstr[]"],
    0x11: ["room:wstr", "text:wstr", "members:wstr[]", "moderators:wstr[]"],
    0x09: ["room:wstr", "text:wstr", "members:wstr[]", "moderators:wstr[]"],
    0x61: ["friends:wstr[]", "online:wstr[]", "ignored:wstr[]"], 0x62: ["friends:wstr[]", "online:wstr[]"],
    0x63: ["ignored:wstr[]"],
    0x54: ["discovery address:nstr", "port:u32"], 0x56: ["discovery address:nstr", "port:u32"],
    0x66: ["discovery address:nstr", "port:u32"],
    0x55: ["game info:wstr[]", "wstr[]", "game ids:u32[]", "blob[]", "LAN address:wstr[]", "LAN port:u32[]",
           "observed address:wstr[]", "observed port:u32[]"],
    0x57: ["wstr", "game id:u32", "LAN address:wstr", "LAN port:u32", "observed address:wstr", "observed port:u32"],
    0x23: ["u32"], 0x58: ["character id:u32"], 0x5B: ["chars"], 0x5C: ["piece:blob", "last:u32"],
}
NOTIFY = {
    0x3E: ["address:nstr", "port:u32"], 0x40: ["address:nstr", "port:u32"],
    0x65: ["LAN address:nstr", "LAN port:u32", "observed address:nstr", "observed port:u32"],
    0x2F: ["handle:wstr", "online:u8"], 0x30: ["from:wstr", "text:wstr"],
    0x3D: ["room:wstr", "from:wstr", "text:wstr"], 0x41: ["rest"],
}


def load_crypto():
    path = os.path.join(os.path.dirname(HERE), "lobby_e2e_test.py")
    spec = importlib.util.spec_from_file_location("lobby_e2e_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AES256, module.GAME_KEY


class Short(Exception):
    pass


class Body:
    def __init__(self, data, cipher, text_limit):
        self.data, self.at, self.cipher, self.limit = data, 0, cipher, text_limit

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise Short()
        piece = self.data[self.at:self.at + n]
        self.at += n
        return piece

    def number(self, size):
        return int.from_bytes(self.take(size), "little")

    def clip(self, text):
        text = text.encode("unicode_escape").decode("ascii")
        return text if len(text) <= self.limit else text[:self.limit] + "...(%d)" % len(text)

    def one(self, kind, name):
        if kind in ("u8", "u16", "u32"):
            value = self.number({"u8": 1, "u16": 2, "u32": 4}[kind])
            return "%d" % value if value < 10 else "%d (0x%x)" % (value, value)
        if kind == "wstr":
            return '"%s"' % self.clip(self.take(2 * self.number(4)).decode("utf-16-le", "replace"))
        if kind == "nstr":
            return '"%s"' % self.clip(self.take(self.number(4)).decode("latin-1"))
        if kind == "blob":
            data = self.take(self.number(4))
            return "%d bytes" % len(data) + ((" " + data[:16].hex() + ("..." if len(data) > 16 else "")) if data else "")
        if kind == "estr":
            units = self.number(4)
            if units == 0:
                return "(empty)"
            plain_length = self.number(4)
            cipher_text = self.take(2 * units - 4)
            if name.startswith("!"):
                return "(%d characters, not shown)" % (plain_length // 2)
            if self.cipher is None or len(cipher_text) % 16:
                return "(encrypted, %d bytes)" % len(cipher_text)
            text = self.cipher.decrypt(cipher_text)[:plain_length].decode("utf-16-le", "replace")
            if name == "sid" or name.endswith(" sid"):
                return "%s...(%d)" % (text[:4], len(text))
            return '"%s"' % self.clip(text)
        if kind == "chars":
            parts = []
            for _ in range(self.number(4)):
                ident = self.number(4)
                pairs = []
                for _ in range(self.number(4)):
                    key = self.one("wstr", "")
                    pairs.append("%s=%s" % (key, self.one("wstr", "")))
                parts.append("id %d {%s}" % (ident, ", ".join(pairs)))
            return "[%s]" % "; ".join(parts)
        if kind == "rest":
            data = self.take(len(self.data) - self.at)
            return "%d bytes %s" % (len(data), data[:48].hex() + ("..." if len(data) > 48 else ""))
        if kind.endswith("[]"):
            count = self.number(4)
            if count > 4096:
                raise Short()
            return "[%s]" % ", ".join(self.one(kind[:-2], name) for _ in range(count))
        raise ValueError(kind)

    def fields(self, layout):
        out = []
        try:
            for spec in layout:
                name, _, kind = spec.rpartition(":")
                value = self.one(kind, name)
                label = name.lstrip("!")
                out.append("%s=%s" % (label, value) if label else value)
        except Short:
            out.append("SHORT: the body ends inside this field (%d bytes left at offset %d)" % (len(self.data) - self.at, self.at))
            return out
        if self.at != len(self.data):
            left = self.data[self.at:]
            out.append("EXTRA %d bytes %s" % (len(left), left[:32].hex()))
        return out


def read_capture(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"\xd4\xc3\xb2\xa1":
        raise SystemExit("%s: not a capture file written by the rig" % path)
    at = 24
    while at + 16 <= len(data):
        seconds, micro, length, _ = struct.unpack_from("<IIII", data, at)
        at += 16
        yield seconds * 60 + micro // 16666, data[at:at + length]
        at += length


def ip_text(raw):
    return ".".join(str(b) for b in raw)


class Stream:
    """One direction of a TCP connection: bytes in order, cut into frames."""

    def __init__(self):
        self.next = None
        self.buffer = b""
        self.frames = []

    def syn(self, sequence):
        self.next = (sequence + 1) & 0xFFFFFFFF

    def data(self, when, sequence, payload):
        if self.next is None:
            self.next = sequence
        skip = (self.next - sequence) & 0xFFFFFFFF
        if skip >= 0x80000000 or skip >= len(payload):
            return  # a gap (not seen on this wire) or bytes already taken
        self.buffer += payload[skip:]
        self.next = (sequence + len(payload)) & 0xFFFFFFFF
        while len(self.buffer) >= 4:
            length = int.from_bytes(self.buffer[:4], "big")
            if length < 4:
                self.frames.append((when, None))
                self.buffer = b""
                break
            if len(self.buffer) < length:
                break
            self.frames.append((when, self.buffer[4:length]))
            self.buffer = self.buffer[length:]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("capture")
    parser.add_argument("--udp", action="store_true", help="also list UDP datagrams")
    parser.add_argument("--text", action="store_true", help="print strings in full")
    parser.add_argument("--hex", type=int, default=0, metavar="N", help="also print the first N bytes of every payload")
    args = parser.parse_args()
    AES256, game_key = load_crypto()

    connections = {}   # (guest port, server address, server port) -> [to server, to guest, order]
    events = []        # (frame, order, text)
    order = 0
    for when, frame in read_capture(args.capture):
        order += 1
        if len(frame) < 34 or frame[12:14] != b"\x08\x00":
            continue
        header = (frame[14] & 15) * 4
        total = int.from_bytes(frame[16:18], "big")
        source, dest = frame[26:30], frame[30:34]
        l4 = frame[14 + header:14 + total]
        protocol = frame[23]
        if protocol == 17 and len(l4) >= 8 and args.udp:
            sport, dport = struct.unpack_from(">HH", l4)
            if 67 in (sport, dport) or 68 in (sport, dport):
                continue
            payload = l4[8:]
            note = ""
            if len(payload) == 36 and payload[:4] == b"\x20\x00\x00\x00":
                note = "  (discovery datagram)"
            events.append((when, order, "udp %s:%d -> %s:%d  %d bytes %s%s" % (
                ip_text(source), sport, ip_text(dest), dport, len(payload), payload[:24].hex(), note)))
        if protocol != 6 or len(l4) < 20:
            continue
        sport, dport, sequence = struct.unpack_from(">HHI", l4)
        flags = l4[13]
        payload = l4[(l4[12] >> 4) * 4:]
        outbound = source[0] == 10
        key = (sport, ip_text(dest), dport) if outbound else (dport, ip_text(source), sport)
        if key not in connections:
            connections[key] = [Stream(), Stream(), order]
        stream = connections[key][0 if outbound else 1]
        if flags & 0x02:
            stream.syn(sequence)
            if outbound:
                events.append((when, order, "tcp %d -> %s:%d opened" % key))
        elif payload:
            stream.data(when, sequence, payload)
        if flags & 0x01 and outbound:
            events.append((when, order, "tcp %d -> %s:%d closed by the machine" % key))

    limit = 100000 if args.text else 40
    for key, (to_server, to_guest, first) in sorted(connections.items(), key=lambda item: item[1][2]):
        pending = {}
        cipher = None
        merged = [(when, 0, payload) for when, payload in to_server.frames] + [(when, 1, payload) for when, payload in to_guest.frames]
        # requests before replies within one emulated frame; otherwise by time
        merged.sort(key=lambda item: (item[0], item[1]))
        index = first * 1000
        for when, inbound, payload in merged:
            index += 1
            tag = "%d>%s:%d" % key
            if payload is None:
                events.append((when, index, "%s  %s  MALFORMED frame length" % (tag, "<-" if inbound else "->")))
                continue
            if len(payload) == 0:
                events.append((when, index, "%s  %s  empty frame (keep-alive)" % (tag, "<-" if inbound else "->")))
                continue
            if len(payload) < 6:
                events.append((when, index, "%s  %s  short payload %s" % (tag, "<-" if inbound else "->", payload.hex())))
                continue
            ident, tracking = struct.unpack_from("<HI", payload)
            name = NAMES.get(ident, "?")
            extra = ("\n        " + payload[:args.hex].hex()) if args.hex else ""
            if not inbound:
                version = int.from_bytes(payload[6:10], "little")
                # the pieces of a character upload go out under the number of the request
                # that started it; the one reply belongs to that request
                if not (ident == 0x5D and pending.get(tracking) in (0x58, 0x5E)):
                    pending[tracking] = ident
                body = Body(payload[10:], cipher, limit)
                layout = REQUEST.get(ident, ["rest"])
                events.append((when, index, "%s  -> 0x%02X %-24s #%d version %d  %d bytes: %s%s" % (
                    tag, ident, name, tracking, version, len(payload) + 4, "; ".join(body.fields(layout)) or "(no body)", extra)))
            elif tracking == 0:
                body = Body(payload[6:], cipher, limit)
                layout = NOTIFY.get(ident, ["rest"])
                events.append((when, index, "%s  <- 0x%02X %-24s notification  %d bytes: %s%s" % (
                    tag, ident, name, len(payload) + 4, "; ".join(body.fields(layout)), extra)))
            else:
                result = int.from_bytes(payload[6:10], "little")
                asked = pending.get(tracking)
                note = "" if asked in (None, ident) else "  [reply id differs from request 0x%02X]" % asked
                if asked is None:
                    note = "  [no request with this tracking number]"
                layout = REPLY.get(asked if asked is not None else ident, ["rest"])
                body = Body(payload[10:], cipher, limit)
                shown = "; ".join(body.fields(layout)) if (result == 0 or len(payload) > 10) else ""
                events.append((when, index, "%s  <- 0x%02X %-24s #%d result %d  %d bytes: %s%s%s" % (
                    tag, ident, name, tracking, result, len(payload) + 4, shown or "(no body)", note, extra)))
                if (asked or ident) == 0x27 and result == 0 and len(payload) >= 18:
                    blob = payload[14:]
                    key_length = int.from_bytes(blob[:4], "little")
                    if len(blob[4:]) % 16 == 0 and key_length == 32:
                        cipher = AES256(AES256(game_key).decrypt(blob[4:])[:32])
                pending.pop(tracking, None)
    for when, _, text in sorted(events):
        print("f%-7d %s" % (when, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
