"""Shared definitions for the motion-pack build: sources + licences, tagging, chunking, catalogue rows, episode needs.
Pure python + numpy (used by build_pack.py on GitHub runners and by quaternius_sample.py inside Blender)."""
import json, os, re, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
import lib_motionlib as ML

GENO = "https://theorangeduck.com/media/uploads/Geno/{}/bvh.zip"
SOURCES = {
    # ---------------------------------------------------------------- commercial use OK -> mani7673/sonpur-motion-packs
    "cmu": dict(commercial_ok=True, dataset="packs",
                licence="CMU Graphics Lab Motion Capture Database terms: 'free for all uses'; may be included in commercially-sold products; the data itself may not be resold, even in converted form",
                credit="Motion capture data from the CMU Graphics Lab Motion Capture Database (mocap.cs.cmu.edu), created with funding from NSF EIA-0196217. BVH conversion by Bruce Hahne (cgspeed).",
                url="https://github.com/una-dinosauria/cmu-mocap (mirror of the cgspeed BVH conversion of mocap.cs.cmu.edu)"),
    "style100": dict(commercial_ok=True, dataset="packs", licence="CC BY 4.0 (attribution required)",
                     credit="100STYLE dataset by Ian Mason, Sebastian Starke and Taku Komura (CC BY 4.0, zenodo.org/records/8127870); retargeted BVH by Daniel Holden (github.com/orangeduck/100style-retarget).",
                     url=GENO.format("100style-retarget")),
    "quaternius": dict(commercial_ok=True, dataset="packs", licence="CC0 1.0 (public domain)",
                       credit="Universal Animation Library 1 & 2 by Quaternius (quaternius.com), CC0.",
                       url="https://opengameart.org/content/universal-animation-library , https://opengameart.org/content/universal-animation-library-2"),
    # ---------------------------------------------------------------- NON-COMMERCIAL -> mani7673/sonpur-motion-nc
    "bandai": dict(commercial_ok=False, dataset="nc", licence="CC BY-NC 4.0 (non-commercial)",
                   credit="Bandai Namco Research Motiondataset 1 & 2 (github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset), CC BY-NC 4.0.",
                   url="https://github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset"),
    "lafan": dict(commercial_ok=False, dataset="nc", licence="CC BY-NC-ND 4.0 (non-commercial, no derivatives)",
                  credit="Ubisoft La Forge Animation Dataset LAFAN1 (Harvey et al. 2020), re-solved by Daniel Holden (github.com/orangeduck/lafan1-resolved), CC BY-NC-ND 4.0.",
                  url=GENO.format("lafan1-resolved")),
    "zeggs": dict(commercial_ok=False, dataset="nc", licence="CC BY-NC-ND 4.0 (non-commercial, no derivatives)",
                  credit="Ubisoft La Forge ZeroEGGS dataset (Ghorbani et al. 2023), retargeted by Daniel Holden (github.com/orangeduck/zeroeggs-retarget), CC BY-NC-ND 4.0.",
                  url=GENO.format("zeroeggs-retarget")),
    "motorica": dict(commercial_ok=False, dataset="nc", licence="Motorica Dance Dataset licence: research use only, no commercial use without written consent, no redistribution",
                     credit="Motorica Dance Dataset (Simon Alexanderson, KTH; github.com/simonalexanderson/MotoricaDanceDataset), retargeted by Daniel Holden (github.com/orangeduck/motorica-retarget).",
                     url=GENO.format("motorica-retarget")),
    "interact": dict(commercial_ok=False, dataset="nc", licence="InterAct dataset licence (HKU): non-commercial research use only",
                     credit="InterAct two-person interaction dataset (hku-cg.github.io/interact), retargeted by Daniel Holden (github.com/orangeduck/interact-retarget).",
                     url="https://theorangeduck.com/media/uploads/Geno/interact-retarget/bvh_single.zip"),
}

TAG_RULES = [
    ("walk", r"\bwalk|stroll|march|stride|\blimp|strut|stagger|\bfw\b|\bbw\b|\bsw\b|sidestep walk|wander|pace"),
    ("run", r"\brun|\bjog|sprint|\bdash|chase|race|\bfr\b|\bbr\b|\bsr\b|rushed|roadrunner"),
    ("sneak", r"sneak|tiptoe|tip toe|creep|stealth|in the dark"),
    ("sit", r"\bsit|\bseat|sitting|\bsquat|kneel|crouch"),
    ("stand_up", r"get ?up|getting up|stand up|stands up|\brise|from the ground|fallandgetup"),
    ("lie_sleep", r"\blie\b|\blying|\blay\b|lay down|sleep|\bnap\b|on the ground|ground\d|\bground\b|roll"),
    ("jump", r"jump|\bhop|leap|\bskip|bounc"),
    ("climb", r"climb|ladder|clamber|scale|obstacle|vault"),
    ("carry", r"carry|carrie|\blift|haul|suitcase|\bbox\b|bucket|load"),
    ("pick_up", r"pick ?up|pick\b|scoop|reach|bend over|bend down|grab"),
    ("throw_catch", r"throw|toss|pitch|\bbowl|catch"),
    ("push_pull", r"\bpush|\bpull|\btug|\bdrag|shove|lawnmower|lawn mower|sweep"),
    ("wave", r"\bwav(e|ing)|\bbye|byebye|hello|\bcall\b|beckon|raise-up|raise up|raised"),
    ("clap", r"\bclap|applau"),
    ("gesture", r"point|gestur|\bbow\b|salute|shrug|\bnod|guide|respond|agreement|disagreement|speech|\btalk|explain|conversation|oration|pensive|sarcastic|flirty|distracted|akimbo|arms ?folded|on ?phone|look"),
    ("laugh", r"laugh|giggle|happy|\bjoy|elated|cheer|celebrat|excited"),
    ("cry_sad", r"\bcry|crying|\bsob|\bsad|depress|upset|tired|exhaust|sulk|mope|dejected|not-confident"),
    ("angry", r"angry|anger|frustrat|threat|\bmad\b|stomp|tantrum"),
    ("scared", r"scare|\bfear|afraid|startle|cower|nervous|shielded|panic"),
    ("eat_drink", r"\beat\b|\beats\b|eating|drink|soda|\bbite|\bfood|chew|\bsip"),
    ("dance", r"danc|ballet|salsa|charleston|hip ?hop|\bjazz|popping|locking|krump|tapping|\btap\b|bhangra|twist\b|morris|wiggle"),
    ("fall", r"\bfall|\btrip|stumble|\bslip|collapse|faint|knocked"),
    ("fight", r"punch|kick|fight|\bbox|strike|karate|sword|slash|martial|swat"),
    ("play", r"playground|\bgame|\bplay|\bball\b|soccer|basketball|football|\btag\b|bluff|hopscotch|\bswing|\bslide|nursery|rhyme|hula|frisbee|cartwheel|rope"),
    ("swim", r"\bswim"),
    ("cycle", r"bicycl|cycling|\bbike"),
    ("idle", r"\bidle|stand still|\bstill\b|\bwait|breath|\bid\b|neutral|stand$"),
    ("interaction", r"interact|two-person|2 subjects|subject a\b|subject b\b|hug|shake hands|handshake|comfort|pass(es)? .* to"),
    ("work", r"wash|sweep|wipe|mop|hammer|dig|shovel|paint|saw\b|chop|cook|scrub|clean|write|draw|sew|plant"),
]
STYLE_RULES = [
    ("old", r"\bold\b|elder|walking ?stick|\bcane\b|hunch|aged"),
    ("child", r"child|childish|childlike|\bkid|youthful|toddler|younger"),
    ("happy", r"happy|joy|elated|cheer|proud|active"),
    ("sad", r"\bsad|depress|tired|exhaust|not-confident|dejected"),
    ("angry", r"angry|anger|threat"),
    ("scared", r"scare|fear|nervous|in ?the ?dark"),
    ("comedy", r"drunk|zombie|robot|chicken|penguin|silly|superman|aeroplane|airplane|teapot|dinosaur|cat\b|quail|monkey|elephant|duck"),
    ("animal_mime", r"animal|chicken|\bcat\b|penguin|dinosaur|monkey|elephant|bear|bird|frog|duck|quail"),
    ("female", r"feminine|female|woman|girl"), ("male", r"masculin|male\b|\bman\b"),
    ("heavy", r"heavyset|giant|heavy"),
    ("loop", r"\bfw\b|\bbw\b|\bfr\b|\bbr\b|walk cycle|run cycle"),
]
CATEGORY_ORDER = ["fall", "swim", "cycle", "climb", "dance", "eat_drink", "cry_sad", "laugh", "clap", "wave", "throw_catch", "carry", "pick_up",
                  "push_pull", "jump", "sneak", "run", "walk", "sit", "stand_up", "lie_sleep", "fight", "play", "work", "angry", "scared",
                  "gesture", "interaction", "idle"]

def tag(desc):
    d = " " + re.sub(r"([a-z])([A-Z])", r"\1 \2", desc).replace("_", " ").lower() + " "
    tags = [t for t, p in TAG_RULES if re.search(p, d)] + [t for t, p in STYLE_RULES if re.search(p, d)]
    cat = next((c for c in CATEGORY_ORDER if c in tags), "misc")
    return sorted(set(tags)), cat

def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60]

def chunks(dur, max_len=16.0, win=10.0, min_last=4.0):
    if dur <= max_len: return [(0.0, None)]
    out = []; t = 0.0
    while t < dur - 0.5:
        e = t + win
        if dur - e < min_last: e = None
        out.append((t, e)); t = (e if e is not None else dur)
    return out

def find_cycle(md):
    """loopable window [t0, t1] (s) for locomotion: two frames 0.8-2.2 s apart with the most similar leg+arm pose"""
    D = md["D"]; F = len(D); fps = md["fps"]
    idx = [ML.SI[s] for s in ("thigh_L", "shin_L", "thigh_R", "shin_R", "arm_L", "arm_R", "foot_L", "foot_R")]
    X = np.nan_to_num(D[:, idx, 0].reshape(F, -1)); z = md["root"][:, 2]
    best = None
    for L in range(int(0.8 * fps), min(int(2.2 * fps), F - 2)):
        a = np.arange(0, F - L, 2)
        d = np.linalg.norm(X[a] - X[a + L], axis=-1) + 3 * np.abs(z[a] - z[a + L])
        i = int(np.argmin(d))
        if best is None or d[i] < best[0] - 0.02: best = (float(d[i]), int(a[i]), L)
    if best and best[0] < 0.35: return [round(best[1] / fps, 3), round((best[1] + best[2]) / fps, 3)]
    return None

_RIGS = None
def rigs():
    global _RIGS
    if _RIGS is None:
        p = os.environ.get("MOTION_RIGS", os.path.join(REPO, "kaggle", "motionpacks", "rigs.json"))
        _RIGS = {k: ML.rig_rest_from_bones(v) for k, v in json.load(open(p)).items()} if os.path.exists(p) else {}
    return _RIGS

def qc(md):
    out = {}
    for k in ("man_28y", "girl_9y"):
        if k in rigs():
            try: out[k] = ML.solve(md, rigs()[k])["qc"]
            except Exception as ex: out[k] = {"error": str(ex)[:200], "flagged": True}
    return out

def make_row(pack, name, md, desc, src_file, t0, extra=None):
    S = SOURCES[pack]; tags, cat = tag(desc + " " + src_file)
    row = dict(name=name, pack=pack, desc=desc, src_file=src_file, t0=round(t0, 3), tags=tags, category=cat,
               licence=S["licence"], commercial_ok=S["commercial_ok"], credit=S["credit"], fps=md["fps"], frames=int(len(md["root"])),
               seconds=round(len(md["root"]) / md["fps"], 2), file=f"md/{pack}/{name}.npz", palm=md["meta"].get("palm"))
    q = qc(md); row["qc"] = q; row["flagged"] = any(v.get("flagged") for v in q.values())
    if any(t in tags for t in ("walk", "run", "sneak")) and row["seconds"] >= 1.5:
        row["cycle"] = find_cycle(md)
    if extra:
        row.update(extra)
        if "pair" in extra:          # two-person takes: where/how this actor started in the shared capture space (leg lengths, degrees)
            row["start_xy_legs"] = md["meta"].get("origin_legs"); row["start_yaw_deg"] = md["meta"].get("yaw_deg")
    return row

# ---------------------------------------------------------------------------------------------------------------------
# what episode 1 (and the other 19 scripts) need: need id -> search query (best commercial match is picked at publish time)
# ---------------------------------------------------------------------------------------------------------------------
EP1_NEEDS = {   # need -> (exact queries, stand-in queries); every word of a query must match (tags / description / name)
    "walk_child": (["child walk", "childish walk", "youthful walk"], ["skip", "bouncy walk", "happy walk", "elated walk"]),
    "walk_adult": (["walk forward neutral", "walk forward", "walk"], []),
    "walk_elderly": (["old walk", "elderly walk"], ["walking stick walk", "bent forward walk", "tired walk"]),
    "walk_stick": (["walking stick"], ["old walk"]),
    "run": (["run forward", "run"], []),
    "chase": (["chase", "tag", "bluff"], ["sprint", "rushed run", "run"]),
    "sit_cross_legged": (["sit cross legged", "sit ground", "sit floor", "sitting floor"], ["sit"]),
    "sit_down": (["sit down", "sit"], []),
    "stand_up": (["get up", "stand up", "rise"], []),
    "carry_on_hip": (["carry child", "carry baby", "hold baby"], ["carry"]),
    "eat_by_hand": (["eat"], ["drink"]),
    "give_take": (["pass", "give", "hand over"], ["pick up", "reach"]),
    "pat_head": (["pat"], ["comfort"]),
    "laugh": (["laugh"], ["happy", "elated"]),
    "cry": (["cry", "sob"], ["sad"]),
    "sulk": (["sulk", "pout"], ["sad", "depressed", "dejected", "arms folded"]),
    "tiptoe": (["tiptoe"], ["sneak"]),
    "wave": (["wave"], []),
    "fall": (["fall"], ["stumble", "trip"]),
    "jump": (["jump"], ["hop"]),
    "hug": (["hug"], ["comfort"]),
}
ASSET_NEED_QUERIES = {
    "anim_walk_run": ["walk", "run", "march", "old walk", "walking stick"], "anim_tiptoe_sneak": ["tiptoe", "sneak"],
    "anim_falls": ["fall", "fall get up"], "anim_slip_slide": ["slip", "stumble"], "anim_trip_stumble_bonk": ["trip stumble", "push stumble"],
    "anim_jump_hop_dive": ["jump", "hop", "dive"], "anim_hide_behind_chhotu": ["hide", "crouch"], "anim_sit_lie_sleep": ["sit", "lie", "sleep"],
    "anim_climb": ["climb", "ladder"], "anim_carry_lift": ["carry", "lift"], "anim_pass_chain": ["pass", "give"],
    "anim_pour_throw_water": ["pour", "throw"], "anim_throw_catch_flick": ["throw", "catch", "bowl"], "anim_pull_push_tug": ["pull", "push", "tug"],
    "anim_eat_drink": ["eat", "drink"], "anim_sniff_nose_led": ["sniff", "bent forward"], "anim_gesture_set": ["point", "wave", "salute", "clap", "shrug", "bow"],
    "anim_hug_comfort": ["hug", "comfort"], "anim_raju_cool_poses": ["proud", "strut", "akimbo"], "anim_signature_tics": ["gesture"],
    "anim_dance_sing": ["dance", "chicken"], "anim_dig_plant": ["dig", "shovel", "plant"], "anim_write_draw": ["write", "draw"],
    "anim_kite_flying": ["kite", "pull rope"], "anim_cricket_gilli": ["bowl", "bat swing", "baseball", "catch"], "anim_games_races": ["chase", "tag", "race", "run"],
    "anim_shiver_sweat_tremble": ["scared", "shiver", "cold"], "anim_spin_dizzy_stuck": ["spin", "dizzy", "drunk"], "anim_adult_work": ["sweep", "hammer", "wash", "wipe"],
    "anim_shadow_puppets": ["hands"], "anim_talk_lipsync": ["talk", "speech"],
}
