"""Quality gate 1: every actor pose in the plan must be served by a key drawing (no fallback to old puppets), every plate and
prop file must exist, and every key drawing must have a mouth patch unless the character is an animal.
  python gate_coverage.py <ep>   -> exit 1 with a list if anything is missing"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import keyactor
ep = sys.argv[1]; W = os.path.join(HERE, "out", ep)
plan = json.load(open(os.path.join(W, "plan.json"), encoding="utf-8-sig")); K = keyactor.load(os.path.join(W, "keys_selection.json"))
sel = json.load(open(os.path.join(W, "keys_selection.json")))
pc = {p["id"]: p["char"] for p in plan["poses"]}; pn = {p["id"]: p.get("pose", "stand") for p in plan["poses"]}
ANIMALS = {"chamki", "sheru"}; errs = []
for s in plan["shots"]:
    for ac in s.get("actors", []):
        pid = ac["pose"]; c = pc.get(pid) or pid.split("_")[0]; p = pn.get(pid) or ("_".join(pid.split("_")[1:]) or "stand")
        kc = K.get(c)
        if not (kc and kc.covers(p)): errs.append(f"{s['id']}: {c} pose '{p}' has no key drawing")
    if not glob.glob(os.path.join(W, "assets", "plates", s["plate"] + "_*.png")): errs.append(f"{s['id']}: plate {s['plate']} missing")
    for ob in s.get("objects", []) or []:
        pid = ob.get("prop") or ob.get("id")
        if pid and not os.path.exists(os.path.join(W, "assets", "props", pid + ".png")): errs.append(f"{s['id']}: prop {pid} missing")
for c, e in sel.items():
    if c in ANIMALS: continue
    for act, ids in e["actions"].items():
        for i in range(len(ids)):
            if f"{act}_{i}" not in e.get("body_mouth", {}): errs.append(f"{c}: drawing {act}_{i} has no mouth patch")
print("\n".join(errs) if errs else "GATE 1 OK: all poses, plates, props and mouths covered"); sys.exit(1 if errs else 0)
