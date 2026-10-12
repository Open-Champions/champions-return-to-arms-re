#!/usr/bin/env python3
"""One scripted session for two machines: the rig and the browser build.

  session.py make INPUT.txt FRAMES WATCHES.txt OUT [--poke FRAME:ADDRESS:TEXT ...]
      INPUT.txt    controller stream recorded by the rig (rta_rig --record-input): one line
                   per change, "frame buttons(hex) left-x left-y right-x right-y"
      FRAMES       how many vertical blanks the session lasts, counted from power-on
      WATCHES.txt  what to read at every vertical blank, one place per line:
                   "name pointer offset size" in hexadecimal; pointer 0 means the bytes at
                   address 'offset', otherwise the bytes at 'offset' past the pointer
                   stored at address 'pointer'
      --poke       the text, and a zero byte after it, written at ADDRESS (hexadecimal)
                   in vertical blank FRAME; repeatable
    writes OUT.json   for the browser build's test page (tools/arith/web/arith.js):
                      steps, writes and places, all given to the machine before it starts
           OUT.watch  the same places as a --watch-file for the rig (raw bytes, as hex)
           OUT.rig    the same writes as a rig script ("at FRAME" / "poke ...")
           OUT.steps.json  the steps alone in the form every browser build takes
                      (arith.js ?steps=...&trace=...: [[buttons, stick, x, y, frames], ...]),
                      when the stream never holds buttons and the left stick together
                      and never moves the right stick

  session.py compare RIG-LOG.tsv BROWSER.hex WATCHES.txt [--other RIG-LOG2.tsv]
      compares, frame by frame and place by place, the rig's log (rta_rig --log with
      OUT.watch) with what the browser build's page reported. A place reached through a
      pointer is compared in the frames in which both machines hold the same non-zero
      pointer. --other: a second rig log (the other arithmetic), compared with the browser
      in the same way, to show that the comparison can tell the two apart.

Nothing of the game is in here: addresses come from the watch file. Standard library only.
"""
import csv
import json
import sys


def read_watches(path):
    watches = []
    with open(path) as source:
        for line in source:
            line = line.split("#")[0].split()
            if len(line) == 4:
                watches.append((line[0], int(line[1], 16), int(line[2], 16), int(line[3], 16)))
    # the pointers themselves are read too, so that both sides know when one is null
    rows = []
    for pointer in sorted(set(w[1] for w in watches if w[1])):
        rows.append(("@%x" % pointer, 0, pointer, 4))
    return rows + watches


def make(argv):
    pokes = []
    while "--poke" in argv:
        index = argv.index("--poke")
        frame, address, text = argv[index + 1].split(":", 2)
        pokes.append((int(frame), int(address, 16), text))
        del argv[index:index + 2]
    source, total, watch_path, out = argv[0], int(argv[1]), argv[2], argv[3]
    changes = []
    with open(source) as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            frame, buttons, lx, ly, rx, ry = line.split()
            changes.append((int(frame), int(buttons, 16), int(lx), int(ly), int(rx), int(ry)))
    if not changes or changes[0][0] > 1:
        changes.insert(0, (1, 0, 128, 128, 128, 128))
    steps = []
    for index, (frame, buttons, lx, ly, rx, ry) in enumerate(changes):
        end = min(changes[index + 1][0] if index + 1 < len(changes) else total + 1, total + 1)
        count = end - max(frame, 1)
        if count > 0:
            steps.append([buttons, lx, ly, rx, ry, count])
    if sum(step[5] for step in steps) != total:
        raise SystemExit("the steps cover %d frames, not %d" % (sum(step[5] for step in steps), total))
    watches = read_watches(watch_path)
    with open(out + ".json", "w") as handle:
        json.dump({"frames": total, "steps": steps,
                   "pokes": [[frame, address, (text.encode() + b"\0").hex()] for frame, address, text in pokes],
                   "watch": [[pointer, offset, size] for _, pointer, offset, size in watches]}, handle)
    with open(out + ".watch", "w") as handle:
        for name, pointer, offset, size in watches:
            where = ("[0x%x]+0x%x" % (pointer, offset)) if pointer else ("0x%x" % offset)
            handle.write("%s=%s:hex%d\n" % (name, where, size))
    with open(out + ".rig", "w") as handle:
        for frame, address, text in sorted(pokes):
            handle.write("at %d\npoke 0x%x:str%d %s\n" % (frame, address, len(text) + 1, text))
    simple = all((rx, ry) == (128, 128) and not (buttons and (lx, ly) != (128, 128)) for buttons, lx, ly, rx, ry, _ in steps)
    if simple:
        with open(out + ".steps.json", "w") as handle:
            json.dump([[buttons, 1 if (lx, ly) != (128, 128) else 0, lx, ly, count] for buttons, lx, ly, _, _, count in steps], handle)
    print("%d steps, %d frames, %d places (%d bytes a frame), %d writes -> %s.json .watch .rig%s" % (
        len(steps), total, len(watches), sum(w[3] for w in watches), len(pokes), out, " .steps.json" if simple else ""))


def load_rig(path):
    with open(path) as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    return rows[0], rows[1:]


def compare_one(label, rig_path, browser, watches):
    header, rows = load_rig(rig_path)
    row_size = sum(w[3] for w in watches)
    frames = min(len(rows), len(browser) // (2 * row_size))
    column = {name: header.index(name) for name, _, _, _ in watches}
    offsets, at = {}, 0
    for name, _, _, size in watches:
        offsets[name] = (at, size)
        at += size
    print("%s: %d frames compared (rig log %d rows, browser %d)" % (label, frames, len(rows), len(browser) // (2 * row_size)))
    any_difference = False
    for name, pointer, _, size in watches:
        start, _ = offsets[name]
        compared = differing = 0
        first = None
        for frame in range(frames):
            base = frame * 2 * row_size
            mine = browser[base + 2 * start: base + 2 * (start + size)]
            theirs = rows[frame][column[name]]
            if pointer:
                pstart, _ = offsets["@%x" % pointer]
                pointer_browser = browser[base + 2 * pstart: base + 2 * pstart + 8]
                pointer_rig = rows[frame][column["@%x" % pointer]]
                if pointer_browser != pointer_rig or pointer_browser == "00000000":
                    continue
            compared += 1
            if mine != theirs:
                differing += 1
                if first is None:
                    first = (frame + 1, theirs, mine)
        text = "  %-10s %7d frames compared, %7d differ" % (name, compared, differing)
        if first:
            any_difference = True
            text += "; first at frame %d: rig %s | browser %s" % (first[0], first[1][:48], first[2][:48])
        print(text)
    print("  RESULT: %s" % ("DIFFERENCES" if any_difference else "no place differs in any frame"))
    return any_difference


def compare(argv):
    other = None
    if "--other" in argv:
        index = argv.index("--other")
        other = argv[index + 1]
        del argv[index:index + 2]
    watches = read_watches(argv[2])
    with open(argv[1]) as handle:
        browser = handle.read().strip()
    different = compare_one("rig against browser build", argv[0], browser, watches)
    if other:
        compare_one("other rig log against browser build", other, browser, watches)
    return 1 if different else 0


if __name__ == "__main__":
    if len(sys.argv) >= 6 and sys.argv[1] == "make":
        make(sys.argv[2:])
    elif len(sys.argv) >= 5 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2:]))
    else:
        raise SystemExit(__doc__)
