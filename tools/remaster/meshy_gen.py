#!/usr/bin/env python3
"""Generate the Remastered test assets (our own) with Meshy's API from text prompts only.

Never uploads game or Elden Ring images or models: this script sends text prompts and Meshy task ids, nothing else.
The API key is read at run time from the file named by MESHY_KEY_FILE (never printed, logged or written anywhere).
Usage:  MESHY_KEY_FILE=<key file> python3 tools/remaster/meshy_gen.py balance
        MESHY_KEY_FILE=<key file> python3 tools/remaster/meshy_gen.py run OUTDIR [--budget N] [name ...]
Per asset (meshy_prompts.json): text-to-3D preview -> refine (PBR textures) -> optional auto-rig.
OUTDIR keeps tasks.json (ids, states) so a re-run resumes instead of paying again.
"""
import json, os, ssl, sys, time, urllib.request, urllib.error

API = "https://api.meshy.ai/openapi"
HERE = os.path.dirname(os.path.abspath(__file__))
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)
COST = {"meshy-7.1": 20, "meshy-6": 20, "meshy-6-lite": 5, "refine": 10, "rig": 5}


def _key():
    with open(os.environ["MESHY_KEY_FILE"]) as f:
        return f.read().strip()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return {"error": e.code, "message": json.load(e).get("message")}
        except Exception:
            return {"error": e.code}


def balance():
    return call("GET", "/v1/balance").get("balance")


def wait(path):
    while True:
        d = call("GET", path)
        if d.get("status") not in ("PENDING", "IN_PROGRESS"):
            return d
        time.sleep(8)


def get(url, path):
    with urllib.request.urlopen(url, timeout=300, context=CTX) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def fetch(d, outdir, stem):
    got = []
    mu = d.get("model_urls") or {}
    if mu.get("glb"):
        got.append(get(mu["glb"], os.path.join(outdir, stem + ".glb")))
    for tex in (d.get("texture_urls") or [])[:1]:
        for k, u in tex.items():
            if u:
                got.append(get(u, os.path.join(outdir, "%s.%s.png" % (stem, k))))
    res = d.get("result") or {}
    if res.get("rigged_character_glb_url"):
        got.append(get(res["rigged_character_glb_url"], os.path.join(outdir, stem + ".glb")))
    for name, a in (res.get("basic_animations") or {}).items():
        if isinstance(a, str) and name.endswith("glb_url"):
            got.append(get(a, os.path.join(outdir, "%s.%s.glb" % (stem, name))))
    if d.get("thumbnail_url"):
        got.append(get(d["thumbnail_url"], os.path.join(outdir, stem + ".thumb.png")))
    return got


def step(state, state_path, outdir, name, kind, create_path, get_path, body, cost, budget):
    key = "%s.%s" % (name, kind)
    if state.get(key, {}).get("status") == "SUCCEEDED":
        return state[key]["id"], budget
    if cost > budget:
        print(key, "skipped: over budget (%d > %d)" % (cost, budget))
        return None, budget
    r = call("POST", create_path, body)
    if "result" not in r:
        print(key, "refused:", r)
        return None, budget
    d = wait(get_path + r["result"])
    spent = d.get("consumed_credits", cost) or 0
    state[key] = {"id": d["id"], "status": d["status"], "credits": spent}
    json.dump(state, open(state_path, "w"), indent=1)
    print(key, d["status"], spent, "credits", (d.get("task_error") or {}).get("message", ""),
          fetch(d, outdir, key) if d["status"] == "SUCCEEDED" else "")
    return (d["id"] if d["status"] == "SUCCEEDED" else None), budget - spent


def run(outdir, names, budget):
    os.makedirs(outdir, exist_ok=True)
    spec = json.load(open(os.path.join(HERE, "meshy_prompts.json")))
    state_path = os.path.join(outdir, "tasks.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    print("balance before:", balance())
    for name, a in spec["assets"].items():
        if names and name not in names:
            continue
        pv = dict(a["preview"], mode="preview", target_formats=["glb"])
        pid, budget = step(state, state_path, outdir, name, "preview", "/v2/text-to-3d", "/v2/text-to-3d/", pv,
                           COST[pv["ai_model"]], budget)
        if not pid:
            continue
        rf = dict(a["refine"], mode="refine", preview_task_id=pid, target_formats=["glb"])
        rid, budget = step(state, state_path, outdir, name, "refine", "/v2/text-to-3d", "/v2/text-to-3d/", rf,
                           COST["refine"], budget)
        if rid and "rig" in a:
            _, budget = step(state, state_path, outdir, name, "rig", "/v1/rigging", "/v1/rigging/",
                 dict(a["rig"], input_task_id=rid), COST["rig"], budget)
    print("balance after:", balance())


if __name__ == "__main__":
    if sys.argv[1] == "balance":
        print(balance())
    else:
        args = sys.argv[3:]
        budget = 100
        if "--budget" in args:
            i = args.index("--budget"); budget = int(args[i + 1]); del args[i:i + 2]
        run(sys.argv[2], args, budget)
