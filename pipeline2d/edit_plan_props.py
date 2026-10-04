"""Prop pass for ep01 plan.json (4 Oct): every beat's named props on screen.
  python edit_plan_props.py ep01        (backs up plan.json -> plan.before_props.json once, always rebuilds from that backup)
Set dressing ("set") is drawn BEHIND actors, "objects" in FRONT. Positions are plate fractions (x, y); heights are fractions of plate height."""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ep = sys.argv[1] if len(sys.argv) > 1 else "ep01"
W = os.path.join(HERE, "out", ep); P = os.path.join(W, "plan.json"); B = os.path.join(W, "plan.before_props.json")
if not os.path.exists(B): shutil.copy2(P, B)
plan = json.load(open(B, encoding="utf-8-sig"))
S = {s["id"]: s for s in plan["shots"]}
LEAD, GAP, NOAUDIO = 0.35, 0.35, 1.3


def spans(sh):
    t, out = LEAD, []
    for u in sh["units"]:
        d = plan["units"][str(u)].get("dur") or NOAUDIO; out.append((u, plan["units"][str(u)]["speaker"], t, t + d)); t += d + GAP
    return out


def actor(sh, prefix):
    return next((a for a in sh["actors"] if a["pose"].startswith(prefix)), None)


def lap(a, up=.20):            # lap of a cross-legged sitter, plate coords
    return [a["x"] + (-.01 if a.get("flip") else .01), a["foot_y"] - up * a["height"]]


def hand(a, side=1, up=.42, out=.12):   # rough hand position in front of a standing actor
    s = -side if a.get("flip") else side
    return [a["x"] + s * out * a["height"] * 0.56, a["foot_y"] - up * a["height"]]


def add_set(sh, prop, x, foot_y, height, **k): sh.setdefault("set", []).append(dict(prop=prop, x=x, foot_y=foot_y, height=height, **k))
def add_obj(sh, prop, a, b=None, t0=0.0, t1=0.0, scale=.05, **k): sh.setdefault("objects", []).append(dict(prop=prop, **{"from": a, "to": b or a}, t0=t0, t1=t1, scale=scale, **k))


for sh in plan["shots"]:
    sh["objects"] = [o for o in sh.get("objects", [])]
    # Dadi always sits on her charpai in the courtyard (script: "Dadi charpai par")
    if sh["plate"].startswith("courtyard"):
        for a in sh["actors"]:
            if a["pose"].startswith("dadi_sit"):
                add_set(sh, "charpai", a["x"], a["foot_y"] + .13, .20)   # woven surface ~35% from the top = her seat
    # the almirah is the set piece of every inside scene (against the back wall, right)
    if sh["plate"].startswith("house_inside"):
        add_set(sh, "almirah", .84, .80, .62)

# ---- scene 1: thali on Dadi's lap, she counts eleven laddoos (unit 1)
for sid in ("s001", "s002", "s003", "s004"):
    sh = S[sid]; d = actor(sh, "dadi_sit"); L = lap(d)
    add_obj(sh, "thali_laddoos", L, scale=.13)
sh = S["s001"]; d = actor(sh, "dadi_sit"); L = lap(d)
_, _, a0, a1 = [s for s in spans(sh) if s[1] == "Dadi"][0]
n = 11; step = (a1 - a0 - .4) / n
for i in range(n):              # each counted laddoo hops from the left heap to the right heap of the thali
    t = a0 + .2 + i * step
    px, py = L[0] + .085 + .016 * (i % 4), L[1] + .045 - .014 * (i // 4)     # counted pile on the charpai beside her, grows row by row
    add_obj(sh, "laddoo", [L[0] + .01, L[1] - .02], [px, py], t0=t, t1=t + step * .8, scale=.034, show=t - .05)
sh["mcu"] = False               # the counting must be SEEN: keep the thali in frame (camera set below)
sh["camera"] = {"from": [d["x"], d["foot_y"] - .30, 1.0], "to": [d["x"], d["foot_y"] - .26, 1.9]}
# s005: she covers the thali (covered thali on her lap) -- carry / almirah drawings pending from Kaggle
add_obj(S["s005"], "thali_covered", lap(actor(S["s005"], "dadi_sit")), scale=.12)

# ---- scene 2 inside: chauki in front of the almirah, full thali on top; s008 last laddoo -> pocket already planned
for sid in ("s007", "s008"):
    sh = S[sid]; add_set(sh, "chauki", .70, .87, .10)
    add_obj(sh, "thali_laddoos" if sid == "s007" else "thali_empty", [.84, .175], scale=.08)
# ---- scene 3: the empty thali on the almirah
for sid in ("s009", "s010"):
    add_obj(S[sid], "thali_empty", [.84, .175], scale=.08)

# ---- scene 4 well: Raju's net
r = actor(S["s023"], "raju"); add_obj(S["s023"], "fishing_net", hand(r, 1, .55, .5), scale=.20)
r = actor(S["s024"], "raju"); add_obj(S["s024"], "fishing_net", [r["x"], r["foot_y"] - .55 * r["height"]], scale=r["height"] * 1.05)
r = actor(S["s027"], "raju"); add_obj(S["s027"], "fishing_net", [r["x"], r["foot_y"] - .55 * r["height"]], scale=r["height"] * 1.05)
p = actor(S["s025"], "pinky"); add_obj(S["s025"], "notebook_pencil", hand(p, -1, .45, .35), scale=.07)

# ---- scene 5 Lallan's shop: kadhai on the stove + jalebi plate on the counter
for sid in ("s029", "s030", "s031", "s032", "s033"):
    sh = S[sid]; add_set(sh, "kadhai", .12, .93, .16)
    if sid != "s030": add_set(sh, "jalebi_plate", .22, .80, .08)
l = actor(S["s030"], "lallan"); add_obj(S["s030"], "jalebi_plate", [l["x"] + .02, l["foot_y"] - .58 * l["height"]], scale=.10)
add_set(S["s031"], "paraat", .70, .93, .07)

# ---- scene 6 trap: thali with 4 laddoos is the bait; net + rope on the branch
for sid in ("s034", "s035", "s036"):
    sh = S[sid]; sh["objects"] = [o for o in sh["objects"] if o["prop"] != "laddoo_plate"]
    add_set(sh, "laddoo_plate", .46, .97, .06)
sh = S["s035"]; s_ = actor(sh, "sheru")
add_obj(sh, "rope", [.22, .30], scale=.10)
add_obj(sh, "fishing_net", [s_["x"], .20], [s_["x"], s_["foot_y"] - .06], t0=1.0, t1=1.6, scale=.22)
d = actor(S["s037"], "dadi"); add_obj(S["s037"], "torch", hand(d, -1, .50, .55), scale=.06)
for sid in ("s038", "s039"):
    l = actor(S[sid], "lallan"); add_obj(S[sid], "belan", hand(l, 1, .62, .55), scale=.10)
l = actor(S["s040"], "lallan"); add_obj(S["s040"], "jalebi_plate", hand(l, 1, .55, .3), scale=.08)

# ---- scene 9-10 courtyard: laddoo making (paraat of besan + plate of round laddoos), giant laddoo, Dadi's first laddoo
for sid in ("s051", "s052", "s053", "s054", "s055", "s056", "s057"):
    sh = S[sid]
    if not any(o["prop"].startswith("paraat") for o in sh["objects"]): add_set(sh, "paraat_besan", .50, .97, .08)
    if sid in ("s053", "s054", "s055", "s056", "s057"): add_set(sh, "laddoo_plate", .62, .97, .06)
c = actor(S["s050"], "chhotu"); add_obj(S["s050"], "laddoo", [c["x"] + .01, c["foot_y"] - .40 * c["height"]], scale=.012)   # besan smear reminder (crumb)
r = actor(S["s055"], "raju"); add_obj(S["s055"], "big_laddoo", [r["x"], r["foot_y"] - .35 * r["height"]], scale=.09, hide=2.2)
add_obj(S["s055"], "paraat_besan", [r["x"], r["foot_y"] - .18 * r["height"]], scale=.08, show=2.2)
for sid in ("s058",):
    l = actor(S[sid], "lallan"); add_obj(S[sid], "jalebi_plate", hand(l, 1, .55, .3), scale=.09)

json.dump(plan, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("plan written:", sum(len(s.get("set", [])) for s in plan["shots"]), "set pieces,", sum(len(s.get("objects", [])) for s in plan["shots"]), "objects")
