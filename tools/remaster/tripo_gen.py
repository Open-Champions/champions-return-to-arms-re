#!/usr/bin/env python3
"""Generate the Remastered test assets (our own) with Tripo's API from text prompts only.

Never upload game or Elden Ring images or models: this script sends text prompts and Tripo task ids, nothing else.
The API key is read at run time from the file named by TRIPO_KEY_FILE (never printed, logged or written anywhere).
Usage:  TRIPO_KEY_FILE=<key file> python3 tools/remaster/tripo_gen.py balance
        TRIPO_KEY_FILE=<key file> python3 tools/remaster/tripo_gen.py run OUTDIR [--max N] [name ...]
Tasks per asset are listed in prompts.json ("steps"); a step after the first refers to the previous task.
OUTDIR keeps tasks.json (ids, states) so a re-run resumes instead of paying again.
"""
import json, os, ssl, sys, time, urllib.request

API = "https://api.tripo3d.ai/v2/openapi"
HERE = os.path.dirname(os.path.abspath(__file__))
# python.org builds on macOS ship without CA roots: fall back to the system bundle
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)


def _key():
    with open(os.environ["TRIPO_KEY_FILE"]) as f:
        return f.read().strip()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def balance():
    return call("GET", "/user/balance").get("data")


def wait(tid):
    while True:
        d = call("GET", "/task/" + tid).get("data", {})
        if d.get("status") not in ("queued", "running"):
            return d
        time.sleep(5)


def fetch(d, outdir, name):
    out = d.get("output") or {}
    for k in ("pbr_model", "model", "base_model"):
        url = out.get(k)
        if url:
            path = os.path.join(outdir, name + ".glb")
            with urllib.request.urlopen(url, timeout=300, context=CTX) as r, open(path, "wb") as f:
                f.write(r.read())
            return path


def run(outdir, names, cap):
    os.makedirs(outdir, exist_ok=True)
    spec = json.load(open(os.path.join(HERE, "prompts.json")))
    state_path = os.path.join(outdir, "tasks.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    started = sum(len(v) for v in state.values())
    print("balance before:", balance())
    for name, a in spec["assets"].items():
        if names and name not in names:
            continue
        prev = None
        for i, step in enumerate(a["steps"]):
            key = "%s.%d" % (name, i)
            done = state.setdefault(name, {})
            if key in done and done[key]["status"] == "success":
                prev = done[key]["id"]
                continue
            if started >= cap:
                print("task cap reached:", cap); break
            body = dict(step)
            if body["type"] != "text_to_model":
                body["original_model_task_id"] = prev
            r = call("POST", "/task", body)
            if r.get("code") != 0:
                print(name, step["type"], "refused:", r.get("message")); return
            started += 1
            d = wait(r["data"]["task_id"])
            done[key] = {"id": d["task_id"], "type": step["type"], "status": d["status"]}
            json.dump(state, open(state_path, "w"), indent=1)
            print(name, step["type"], d["status"], fetch(d, outdir, "%s.%d.%s" % (name, i, step["type"])))
            if d["status"] != "success":
                break
            prev = d["task_id"]
    print("balance after:", balance())


if __name__ == "__main__":
    if sys.argv[1] == "balance":
        print(balance())
    else:
        args = sys.argv[3:]
        cap = 12
        if "--max" in args:
            i = args.index("--max"); cap = int(args[i + 1]); del args[i:i + 2]
        run(sys.argv[2], args, cap)
