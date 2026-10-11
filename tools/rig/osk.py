#!/usr/bin/env python3
"""Types text on the game's on-screen keyboards in a live rig session.

The game has two keyboards drawn on the screen, both a grid that the D-pad walks, with
cross typing the key under the cursor and square deleting:

  lobby   the lobby's login, account and chat screens: 14 columns, R2 held gives the
          shifted keys, triangle is a space, L2 accepts the field, circle closes it;
  name    the character-name screen: 10 columns, letters and digits, and a DONE key in
          the bottom row.

This tool drives them for a session started with

    rig.py session --name N start --interactive-live --screen-text ...

and checks every step against the machine instead of trusting timing: the cursor is read
back from memory (lobby: index = row * 14 + column at +0x5e0 of the keyboard window that
the static pointer 0x5061f4 leads to; name: row * 10 + column in the word at 0x8e2ba0,
with -2 and -1 for SPACE and DONE; all seen on the running game) and the field is read
back from the text the game draws.

    osk.py --session N cursor                 where the cursor is
    osk.py --session N fields                 what the screen's fields show
    osk.py --session N type --text hello      type a literal text
    osk.py --session N type --file F --key a.user --label "login:"
                                              type the value of 'a.user=...' from file F;
                                              with --label every key is checked on the screen
    osk.py --session N type --env NAME        type the value of an environment variable
    osk.py --session N --keyboard name type --text bob --label "Character Name:"
    osk.py --session N --keyboard name done   move to DONE and press it

Account names and passwords for the rig's test accounts are kept in a local file outside
the repository (see docs/issues/live-rig.md, Phase 14) and are read with --file/--key or
--env; a value read that way is never printed, only its length. The keyboard must already
be open (lobby: square on a field). Standard library only; no game data is read or written.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The keys this tool can type, by row, as each keyboard draws them without and with its
# shift button. A space stands for a key that is not used here (accented letters, and
# cells where nothing is drawn). "safe": the columns up to this one hold a key in every
# listed row, so the cursor can go up and down there; further right some cells are empty
# and the cursor is moved along a row only.
KEYBOARDS = {
    "lobby": {
        "cursor": "[0x5061f4]+0x5e0:u32", "columns": 14, "rows": 5, "safe": 8, "shift": "r2",
        "plain": ["1234567890-=  ", "qwertyuiop   ;", "asdfghjkl  \\' ", "zxcvbnm,./    "],
        "shifted": ["!@ $%^&*()_+  ", "QWERTYUIOP[] :", "ASDFGHJKL   \"`", "ZXCVBNM<>?    "],
    },
    "name": {
        "cursor": "0x8e2ba0:u32", "columns": 10, "rows": 7, "safe": 9, "shift": "r1",
        "plain": ["abcdefghij", "klmnopqrst", "uvwxyz0123", "456789    "],
        "shifted": [],
    },
}
NAME_DONE = 0xFFFFFFFF      # the name keyboard's cursor on DONE; SPACE is one less


class Session:
    def __init__(self, name, keyboard="lobby", timeout=300):
        self.name = name
        self.timeout = timeout
        self.keyboard = KEYBOARDS[keyboard]

    def send(self, *commands):
        command = [sys.executable, "-I", "-B", os.path.join(HERE, "rig.py"), "session", "--name", self.name,
                   "--timeout", str(self.timeout), "send"] + list(commands)
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        if result.returncode != 0:
            raise SystemExit(result.stdout[-2000:])
        return result.stdout

    def cursor_index(self):
        text = self.send("show kb=" + self.keyboard["cursor"])
        found = re.findall(r"kb@[0-9a-f]+=(\d+)", text)
        if not found:
            raise SystemExit("no cursor value in the session's output:\n" + text[-800:])
        return int(found[-1])

    def cursor(self):
        index = self.cursor_index()
        if index >= self.keyboard["columns"] * self.keyboard["rows"]:
            if index >= NAME_DONE - 1:
                return self.keyboard["rows"] - 1, self.keyboard["columns"]      # SPACE or DONE, bottom row
            raise SystemExit("cursor index %d is not on the keyboard (is the keyboard open?)" % index)
        return divmod(index, self.keyboard["columns"])

    def find_key(self, char):
        for table, shifted in ((self.keyboard["plain"], False), (self.keyboard["shifted"], True)):
            for row, keys in enumerate(table):
                column = keys.find(char)
                if column >= 0 and char != " ":
                    return row, column, shifted
        raise SystemExit("this on-screen keyboard has no key for %r" % char)

    def drawn(self):
        """Every string drawn in a frame: list of (y, x, text)."""
        text = self.send("break text_drawWideImpl,wstr=a2,limit=400,name=osk", "wait 2",
                         "break text_drawWideImpl,wstr=a2,collect")
        items = []
        for line in text.splitlines():
            match = re.search(r' bp=osk .*? a0=(\w+) a1=(\w+) .*a2->L"(.*)"$', line)
            if match:
                item = (int(match.group(2), 16), int(match.group(1), 16), match.group(3))
                if item not in items:
                    items.append(item)
        return items

    def fields(self):
        """Label -> the text drawn to its right on the same line, or else on the line
        just under it ('' if neither)."""
        items = self.drawn()
        result = {}
        for y, x, text in items:
            if not text.endswith(":") and not text.endswith("?"):
                continue
            right = [(x2, t2) for y2, x2, t2 in items if abs(y2 - y) <= 3 and x2 > x and t2]
            under = [(x2, t2) for y2, x2, t2 in items if 10 <= y2 - y <= 40 and not t2.endswith(":") and not t2.endswith("?")]
            if right:
                value = min(right)[1]
            else:
                # the name screen draws the text under its label, with a blinking
                # underscore after it
                value = min(under)[1] if under else ""
                if value.endswith("_"):
                    value = value[:-1]
            result[text] = value
        return result

    def move(self, row, column):
        """Walk the cursor to a key, looking where it ended up after every leg."""
        safe = self.keyboard["safe"]
        for _ in range(8):
            at_row, at_column = self.cursor()
            if (at_row, at_column) == (row, column):
                return
            if at_row != row:
                if at_column > safe:
                    # leave the ragged right-hand part along the row first
                    commands = taps("left", at_column - min(column, safe))
                else:
                    commands = taps("down" if row > at_row else "up", abs(row - at_row))
            else:
                commands = taps("right" if column > at_column else "left", abs(column - at_column))
            self.send(*commands)
        raise SystemExit("could not move the cursor to row %d column %d (it is at %r)" % (row, column, self.cursor()))

    def field_text(self, label):
        """What the field with this label shows; the draw log misses a frame now and then."""
        for _ in range(4):
            shown = self.fields().get(label)
            if shown is not None:
                return shown
        raise SystemExit("no field labelled %r on the screen" % label)

    def type_text(self, text, secret=False, label=None):
        """Types the text. With a label the field is read back after every key and a press
        that did not register is repeated: the game drops one now and then (seen when its
        main thread was busy with the network), and nothing else would notice."""
        for position, char in enumerate(text):
            for attempt in range(4):
                if char == " " and self.keyboard is KEYBOARDS["lobby"]:
                    self.send("tap triangle 4 8")
                else:
                    row, column, shifted = self.find_key(char)
                    self.move(row, column)
                    if shifted:
                        button = self.keyboard["shift"]
                        self.send("press " + button, "wait 8", "tap cross 8 8", "release " + button, "wait 8")
                    else:
                        self.send("tap cross 8 8")
                if label is None:
                    break
                shown = self.field_text(label)
                if shows(shown, text[:position + 1]):
                    break
                if len(shown) != position:
                    raise SystemExit("field %s shows %d characters after key %d: stopping" % (label, len(shown), position + 1))
                sys.stdout.write("(key %d did not register, pressed again) " % (position + 1))
            else:
                raise SystemExit("key %d of the text does not register" % (position + 1))
            if not secret:
                sys.stdout.write(char)
                sys.stdout.flush()
        sys.stdout.write("%s(%d keys typed)\n" % ("" if secret else " ", len(text)))

    def press_done(self):
        """The name keyboard's DONE key: bottom row, right of the letters."""
        self.move(self.keyboard["rows"] - 1, 0)
        for _ in range(self.keyboard["columns"] + 2):
            if self.cursor_index() == NAME_DONE:
                self.send("tap cross 8 8")
                return
            self.send("tap right 4 6")
        raise SystemExit("the cursor does not reach DONE")


def taps(direction, count):
    return ["tap %s 4 6" % direction] * count


def shows(shown, text):
    """A password field shows one mark per character: only the length can be compared."""
    return shown == text or (len(shown) == len(text) and len(text) > 0 and set(shown) == {"*"})


def value_from_file(path, key):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(key + "="):
                return line.rstrip("\n")[len(key) + 1:]
    raise SystemExit("%s has no line %s=..." % (path, key))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--session", default="default")
    parser.add_argument("--keyboard", choices=sorted(KEYBOARDS), default="lobby")
    parser.add_argument("action", choices=("cursor", "fields", "type", "done"))
    parser.add_argument("--text")
    parser.add_argument("--file")
    parser.add_argument("--key")
    parser.add_argument("--env")
    parser.add_argument("--label", help="the label of the field being typed into: every key is checked against what the field shows")
    parser.add_argument("--clear", type=int, default=0, metavar="N", help="press delete N times first")
    args = parser.parse_args()
    session = Session(args.session, args.keyboard)
    if args.action == "cursor":
        print("row %d column %d" % session.cursor())
        return 0
    if args.action == "fields":
        for label, text in session.fields().items():
            print("%-28s %s" % (label, ("(%d characters)" % len(text)) if label.endswith("assword:") else text))
        return 0
    if args.action == "done":
        session.press_done()
        return 0
    secret = args.text is None
    if args.text is not None:
        text = args.text
    elif args.env:
        text = os.environ.get(args.env)
        if text is None:
            raise SystemExit("environment variable %s is not set" % args.env)
    elif args.file and args.key:
        text = value_from_file(args.file, args.key)
    else:
        raise SystemExit("type needs --text, --env NAME or --file F --key K")
    if args.clear:
        session.send(*(["tap square 4 6"] * args.clear))
    session.type_text(text, secret, args.label)
    if args.label:
        ok = shows(session.field_text(args.label), text)
        print("field %s %s" % (args.label, "matches" if ok else "DOES NOT MATCH what was typed"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
