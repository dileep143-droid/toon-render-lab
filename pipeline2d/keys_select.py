"""Build out/keys/selection.json (+ out/<ep>/keys_selection.json) from the generated key drawings, with Gemini checks.
  python keys_select.py [--seed dadi=11,chhotu=11] [--act-seed chhotu.eat=23] [--no-qa]
Expressions: Gemini labels each UNLABELLED close-up with one of 6 names; the candidate whose label matches (preferring the chosen bust) wins.
Walk: a strip of the 8 drawings -> Gemini says which leg is in front per panel; alternation is checked in code."""
import glob, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
K = os.path.join(HERE, "out", "keys")
LABELS = ["happy", "sad", "surprised", "angry", "scared", "grin"]
NAMES = {"happy": "happy / laughing", "sad": "sad / crying", "surprised": "surprised", "angry": "angry", "scared": "scared", "grin": "naughty grin"}


def ids(pattern):
    return sorted(os.path.relpath(os.path.dirname(f), K).replace(os.sep, "/") for f in glob.glob(os.path.join(K, pattern, "rgba.png")))


def by_action(cid, seed):
    acts = {}
    def ipw(i):     # drawings conditioned on the master (IP-Adapter) win over earlier unconditioned ones
        try: return json.load(open(os.path.join(K, i, "item.json"))).get("ip_scale", 0)
        except Exception: return 0
    for i in sorted(ids(f"{cid}/s{seed}/*"), key=ipw):
        m = re.match(r".*/([a-z_]+?)_(\d+)_[0-9a-f]{6}$", i)
        if m and "~" not in i: acts.setdefault(m.group(1), {})[int(m.group(2))] = i
    return {a: [d[k] for k in sorted(d)] for a, d in acts.items()}


def edits_of(src):
    out = {"mouth": {}, "expr": {}}
    for i in ids(src + "~*"):
        m = re.match(r".*~(mouth|expr)_([a-z]+)_", i)
        if m: out[m.group(1)][m.group(2)] = i
    return out


def classify(paths):
    import gem
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    q = ("Each image is a cartoon face. For EACH image in order, pick the ONE expression it shows most clearly from: " + ", ".join(LABELS) +
         ". If none is clear answer 'unclear'. Return JSON {\"labels\": [...]} with one label per image.")
    try: return gem.text(q, ims).get("labels", [])
    except Exception as e: print("gemini failed:", e); return []


def walk_check(walk_ids):
    import gem
    from PIL import Image
    ims = [Image.open(os.path.join(K, i, "rgba.png")).convert("RGBA") for i in walk_ids]
    strip = Image.new("RGB", (sum(im.size[0] // 3 for im in ims), ims[0].size[1] // 3), "white"); x = 0
    for im in ims:
        t = im.resize((im.size[0] // 3, im.size[1] // 3)); bg = Image.new("RGBA", t.size, (235, 235, 235, 255)); bg.alpha_composite(t); strip.paste(bg.convert("RGB"), (x, 0)); x += t.size[0]
    q = ("These are consecutive drawings of a walk cycle of one character facing right. For each panel left to right, say which foot is FORWARD (further right): "
         "'near' (the leg closer to the viewer), 'far', or 'together' (passing). Also: are the legs drawn cleanly (no smear, no extra legs)? "
         "Return JSON {\"forward\": [...], \"clean\": true/false, \"note\": \"...\"}")
    try: r = gem.text(q, [strip])
    except Exception as e: return {"error": str(e)}
    f = [x for x in r.get("forward", []) if x in ("near", "far")]
    r["alternates"] = len(set(f)) == 2 and sum(1 for a, b in zip(f, f[1:]) if a != b) >= 1
    return r


def main(seeds, act_seed, qa=True, ep="ep01"):
    sel = {}; report = {}
    for cid in ("dadi", "chhotu"):
        s = seeds.get(cid, 11); acts = by_action(cid, s)
        for a, s2 in act_seed.get(cid, {}).items():
            alt = by_action(cid, s2).get(a)
            if alt: acts[a] = alt
        for a, lst in by_action(cid, 23 if s == 11 else 11).items():
            acts.setdefault(a, lst)               # action missing in the chosen seed -> take the other seed
        entry = {"seed": s, "actions": acts, "body_mouth": {}, "body_expr": {}}
        for a, lst in acts.items():
            for k, src in enumerate(lst):
                e = edits_of(src)
                if e["mouth"]: entry["body_mouth"][f"{a}_{k}"] = e["mouth"]
                if e["expr"]: entry["body_expr"][f"{a}_{k}"] = e["expr"]
        bust = (ids(f"{cid}/bust_s{s}_*") or ids(f"{cid}/bust_s*"))[0]; bs = re.search(r"bust_s(\d+)", bust).group(1)
        entry["bust"] = bust
        entry["mouth"] = {m: (ids(f"{cid}/mouth_{m}_b{bs}_*") or ids(f"{cid}/mouth_{m}_*"))[0] for m in ("closed", "half", "open")}
        cands = {e: ids(f"{cid}/expr_{e}_b{bs}_*") + [x for x in ids(f"{cid}/expr_{e}_*") if f"_b{bs}_" not in x] for e in LABELS}
        entry["expr"] = {}
        flat = [(e, c) for e in LABELS for c in cands[e]]
        labels = classify([os.path.join(K, c, "rgba.png") for _, c in flat]) if qa else []
        for e in LABELS:
            ok = [c for (ee, c), l in zip(flat, labels) if ee == e and str(l).lower().startswith(e[:4])]
            entry["expr"][e] = (ok or cands[e])[0]
            report[f"{cid}.expr.{e}"] = "PASS" if ok else ("FAIL" if labels else "unchecked")
        if qa and "walk" in acts: report[f"{cid}.walk"] = walk_check(acts["walk"])
        sel[cid] = entry
    import p2d_keys as PK
    for cid, (body, _) in PK.CAST.items():          # the rest of the cast: one seed, no LoRA yet
        acts = by_action(cid, 11)
        if not acts.get("stand"): continue
        entry = {"seed": 11, "body": body, "actions": acts, "body_mouth": {}, "body_expr": {}}
        for a, lst in acts.items():
            for k, src in enumerate(lst):
                e = edits_of(src)
                if e["mouth"]: entry["body_mouth"][f"{a}_{k}"] = e["mouth"]
                if e["expr"]: entry["body_expr"][f"{a}_{k}"] = e["expr"]
        sel[cid] = entry
    for cid, body in (("dadi", "adult"), ("chhotu", "child")):
        if cid in sel: sel[cid]["body"] = body
    # animals: keep whatever an earlier step put there
    old = os.path.join(K, "selection.json")
    if os.path.exists(old):
        o = json.load(open(old))
        if "animals" in o: sel["animals"] = o["animals"]
    json.dump(sel, open(old, "w"), indent=1)
    json.dump(sel, open(os.path.join(HERE, "out", ep, "keys_selection.json"), "w"), indent=1)
    json.dump(report, open(os.path.join(K, "qa_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1)[:3000])


if __name__ == "__main__":
    a = sys.argv[1:]; opt = lambda f, d="": a[a.index(f) + 1] if f in a else d
    seeds = {k: int(v) for k, v in (x.split("=") for x in opt("--seed").split(",") if x)}
    act_seed = {}
    for x in opt("--act-seed").split(","):
        if x: c, rest = x.split("."); an, sd = rest.split("="); act_seed.setdefault(c, {})[an] = int(sd)
    main(seeds, act_seed, "--no-qa" not in a)
