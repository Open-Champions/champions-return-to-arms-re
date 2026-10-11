#!/usr/bin/env python3
"""How long from a button press to the first changed picture, in a running application.

    tools/play-net/latency.py SOCKET BUTTON [--frames N] [--dir DIR] [--repeat K]

The application must have been started with --rta-control SOCKET and be showing
something that stands still until the button is pressed (a menu, a character standing in
a level). In one vertical blank the script presses the button, reads the clock and starts
a burst of N consecutive pictures as they are presented (each with its clock). It then
looks for the first picture that differs from the one before by clearly more than the
pictures before the press differed among themselves.

What it measures: from the vertical blank in which the press is given to the game (the
moment a key press that arrived just before would be read) to the moment the changed
picture is handed to the window system. Not in it: the wait of a real key press for the
next vertical blank (0 to 16.7 ms, half of that on average) and the way from the window
system to the glass (the next refresh of the display and the panel).

The pictures are game output: DIR (default local/play-out) is outside the repository.
Standard library only.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from ctl import Control  # noqa: E402


def picture_size(control, directory):
    """Width and height of the window's picture, from one whole picture."""
    name = os.path.join(directory, "latency-size.bmp")
    control.ok("shot " + name)
    data = open(name, "rb").read(26)
    os.unlink(name)
    return struct.unpack_from("<ii", data, 18)


def probe(control, name, count, rect, before=()):
    """count consecutive presented pictures of a rectangle: list of (clock, bytes).
    'before' are commands that go out in the same write, so that they run in the same
    vertical blank as the start of the probe; their answers are returned too."""
    lines = list(before) + ["probe %s %d %d %d %d %d" % ((name, count) + rect)]
    control.file.write("\n".join(lines) + "\n")
    control.file.flush()
    answers = [control.file.readline().strip() for _ in lines]
    if not answers[-1].startswith("ok"):
        raise SystemExit("probe: " + answers[-1])
    data = open(name, "rb").read()
    entries = [line.split() for line in open(name + ".txt")]
    os.unlink(name)
    os.unlink(name + ".txt")
    size = int(entries[0][2]) * int(entries[0][3]) * 4
    return [(int(entry[1]), data[i * size:(i + 1) * size]) for i, entry in enumerate(entries)], answers[:-1]


def difference(a, b):
    """Mean difference of the colour values of two pictures, of 255 (sampled)."""
    if a == b:
        return 0.0
    step = 7
    return sum(abs(a[i] - b[i]) for i in range(0, len(a), step)) / (len(a) / step)


def measure(control, button, frames, directory, rect):
    name = os.path.join(directory, "latency-probe.bin")
    # a still stretch first, to know how much pictures differ when nothing is pressed
    still, _ = probe(control, name, 8, rect)
    noise = max(difference(still[i][1], still[i + 1][1]) for i in range(len(still) - 1))
    # press, clock and probe in one vertical blank
    pictures, answers = probe(control, name, frames, rect, before=["press " + button, "info"])
    control.ok("release " + button)
    info = dict(item.split("=", 1) for item in answers[1].split() if "=" in item)
    pressed = int(info["us"])
    times = [(clock - pressed) / 1000.0 for clock, _ in pictures]
    threshold = max(3 * noise, noise + 0.5)
    previous = still[-1][1]
    result = None
    for i, (_, picture) in enumerate(pictures):
        change = difference(previous, picture)
        if change > threshold:
            result = (i, times[i], change)
            break
        previous = picture
    return result, noise, times


def main():
    parser = argparse.ArgumentParser(description="press to first changed picture")
    parser.add_argument("socket")
    parser.add_argument("button")
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--dir", default=os.path.join(ROOT, "local", "play-out"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--settle", type=int, default=90, help="frames to wait between presses")
    parser.add_argument("--rect", type=float, nargs=4, default=[0.3, 0.3, 0.4, 0.4], metavar=("X", "Y", "W", "H"),
                        help="the part of the picture to watch, as fractions from the bottom left (default: the middle)")
    args = parser.parse_args()
    os.makedirs(args.dir, exist_ok=True)
    control = Control(args.socket)
    width, height = picture_size(control, args.dir)
    rect = (int(args.rect[0] * width), int(args.rect[1] * height), max(1, int(args.rect[2] * width)), max(1, int(args.rect[3] * height)))
    values = []
    for k in range(args.repeat):
        result, noise, times = measure(control, args.button, args.frames, args.dir, rect)
        spacing = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        if result is None:
            print("press %d: no picture changed in %d frames (still pictures differ by %.2f of 255)" % (k + 1, args.frames, noise))
        else:
            index, ms, change = result
            values.append(ms)
            print("press %d: picture %d after the press is the first changed one (by %.1f of 255; still ones differ by %.2f), "
                  "presented %.1f ms after the press was given to the game; the ones before it at %s ms" % (
                      k + 1, index + 1, change, noise, ms, " ".join("%.1f" % t for t in times[:index])))
        print("         time between presented pictures: %.1f to %.1f ms" % (min(spacing), max(spacing)))
        control.ok("wait %d" % args.settle)
    if values:
        print("press to changed picture: %.1f ms on average (%.1f to %.1f), that is %.1f frames of 16.7 ms" % (
            sum(values) / len(values), min(values), max(values), sum(values) / len(values) / 16.667))
    control.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
