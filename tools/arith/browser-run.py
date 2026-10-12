#!/usr/bin/env python3
"""browser-run.py --out DIR --name NAME (--session FILE.json | --steps FILE.json --trace POINTER,OFFSET,SIZE)
                  [--port 8991] [--profile DIR] [--window] [--timeout 1800]

One run of the browser build as a side of the arithmetic comparison: starts a Google
Chrome of its own (its own profile directory, no window unless --window; with --window
the page is titled AGENT TEST), sends it to tools/arith/web/arith.html on the local test
server (tools/play-web/serve.py --site DIR-WITH-THE-BUILD-AND-THE-PAGE --disc IMAGE
--report OUT/report.jsonl, started beforehand), waits for the page's trace, writes it to
OUT/NAME.hex (hexadecimal, a fixed number of bytes per frame) and ends that Chrome. The
session or steps file (tools/arith/session.py make) must be in the served directory. This computer only. Standard library only.
"""
import json
import os
import subprocess
import sys
import time

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    out = os.path.abspath(option(argv, "--out"))
    name = option(argv, "--name")
    steps = option(argv, "--steps")
    trace = option(argv, "--trace")
    port = option(argv, "--port", "8991")
    profile = os.path.abspath(option(argv, "--profile", os.path.join(out, "chrome-profile")))
    timeout = float(option(argv, "--timeout", "1800"))
    report = os.path.join(out, "report.jsonl")
    if os.path.exists(report):
        os.rename(report, os.path.join(out, "report-%d.jsonl" % int(time.time())))
    session = option(argv, "--session")
    if session:
        url = "http://127.0.0.1:%s/arith.html?name=%s&session=%s" % (port, name, session)
    else:
        url = "http://127.0.0.1:%s/arith.html?name=%s&steps=%s&trace=%s" % (port, name, steps, trace)
    command = [CHROME, "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check", "--mute-audio",
               "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows"]
    command += ["--window-size=700,640", "--window-position=40,40"] if "--window" in argv else ["--headless=new"]
    chrome = subprocess.Popen(command + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    state, rows, shown = None, [], 0
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and state is None and chrome.poll() is None:
            time.sleep(2)
            if not os.path.exists(report):
                continue
            rows = [json.loads(line) for line in open(report) if line.strip()]
            for row in rows[shown:]:
                if row["kind"] == "start":
                    print("  browser: %s; %d frames in %d steps" % (row["browser"].split(") ")[-1], row["frames"], row["steps"]), flush=True)
                if row["kind"] == "progress":
                    print("  frame %d after %d s (load %s)" % (row["frame"], row["seconds"], row.get("load")), flush=True)
                if row["kind"] == "failed":
                    print("  FAILED: %s" % row.get("error"), flush=True)
            shown = len(rows)
            kinds = [row["kind"] for row in rows]
            state = "done" if "done" in kinds else ("failed" if "failed" in kinds else None)
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=15)
        except subprocess.TimeoutExpired:
            chrome.kill()
    for row in rows:
        if row["kind"] == "trace":
            path = os.path.join(out, name + ".hex")
            with open(path, "w") as handle:
                handle.write(row["hex"])
            print("  trace: %d frames of %d bytes in %d s (load %s) -> %s" % (row["frames"], row["size"], row["seconds"], row.get("load"), path))
    print("  %s; the test's own Chrome ended" % (state or "NOT FINISHED"))
    return 0 if state == "done" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
