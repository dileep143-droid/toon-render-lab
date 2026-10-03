"""asset_coverage.py - which asset needs of the stories map to a toolkit function, and which are still missing.

    python asset_coverage.py [path/to/ASSET_NEEDS.json] [--json]
Default path: stories/hindi/ASSET_NEEDS.json (searched upwards from here). If the file is absent, the built-in checklist (the brief: every action / animal /
effect / camera trick named for the 20 stories) is checked instead and the report says so.
Accepted file shapes: ["need", ...] | [{"need"|"name"|"asset"|"description"|"text": "...", ...}] | {"story": [needs...]} | {"needs": [...]}.
Every need is matched by keywords (RULES below); a hit only counts when the registry really has that function, so a removed function shows up as missing."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as R

# (regex on the lower-cased need text, [(kind, name), ...] that serve it)   kind "motion" matches any rig family via R.find
RULES = [
    (r"breath|idle", [("motion", "idle_breathe")]), (r"\bnod|agree|haan", [("motion", "nod")]), (r"head.?shake|disagree|\bno\b.*head|refus", [("motion", "head_shake")]), (r"tilt|curious", [("motion", "head_tilt")]),
    (r"\bwave|waving|bye|hello", [("motion", "wave")]), (r"point|show.*direction", [("motion", "point")]), (r"hand.*mouth|gasp|giggle|secret", [("motion", "hand_to_mouth")]),
    (r"reach|take|grab|pick", [("motion", "reach_take")]), (r"\bgive|hand over|offer|serve", [("motion", "give")]), (r"clap|taali", [("motion", "clap")]),
    (r"hips|akimbo|angry stance", [("motion", "hands_on_hips")]), (r"scratch.*head|confus", [("motion", "scratch_head")]), (r"think|ponder|soch", [("motion", "think")]),
    (r"namaste|namaskar|greet", [("motion", "namaste")]), (r"shrug|don.?t know", [("motion", "shrug")]), (r"cry|weep|rub.*eye|rona", [("motion", "cry_rub_eyes"), ("effect", "tears")]),
    (r"laugh|giggle|hans", [("motion", "laugh_bounce")]), (r"jump|kood|leap", [("motion", "jump")]), (r"walk|chal", [("motion", "walk_cycle")]), (r"\brun|bhaag|dash|chase", [("motion", "run_cycle")]),
    (r"tiptoe|sneak|chup", [("motion", "tiptoe")]), (r"sit(?!uat)|baith", [("motion", "sit_down")]), (r"stand up|get up|uth", [("motion", "stand_up")]), (r"banana|peel|slip", [("motion", "fall_slip_peel")]), (r"\btrip|stumble", [("motion", "fall_trip_forward")]), (r"sit.?bump|plop|land on (his|her) bottom|bottom", [("motion", "fall_sit_bump")]), (r"\bfall|\bfell", [("motion", "fall_comic")]),
    (r"carry|matka|pot on head|basket|bucket|load", [("motion", "carry_object")]), (r"clap.?danc|taali.*nach", [("motion", "clap_dance")]), (r"hop.?danc|jump.*joy|hopping", [("motion", "hop_dance")]), (r"garba|dandiya|turn.*clap", [("motion", "garba_turn_clap")]), (r"danc|nach|bhangra", [("motion", "dance_simple")]),
    (r"\b(goat|bakri|dog|kutta|sheru|cow|gaay|buffalo|bhains|cat|billi|donkey|gadha|bullock|bail)", [("animal_motion", "walk"), ("animal_motion", "idle")]),
    (r"trot|gallop|animal.*run", [("animal_motion", "gallop")]), (r"hop|jump.*animal|goat jump", [("animal_motion", "hop")]), (r"lie down|sleep.*animal|animal.*sleep", [("animal_motion", "lie_down"), ("animal_motion", "sleep")]),
    (r"graze|eat.*grass|animal.*eat", [("animal_motion", "graze")]), (r"bark|bhauk", [("animal_motion", "bark")]), (r"bleat|meh", [("animal_motion", "bleat")]), (r"\bmoo|ambaa", [("animal_motion", "moo")]),
    (r"wag", [("animal_motion", "wag_tail")]), (r"shake.?off|wet dog", [("animal_motion", "shake_off")]), (r"\bbutt|headbutt|takkar", [("animal_motion", "butt")]), (r"\bbeg|beg for", [("animal_motion", "beg")]),
    (r"steal|thief|snatch.*run", [("animal_motion", "steal_and_run")]), (r"\b(hen|murgi|chicken|parrot|tota|bird|chidiya|crow|kauwa|sparrow|peck|flap)", [("bird_motion", "flap"), ("bird_motion", "fly"), ("bird_motion", "peck")]),
    (r"monkey|bandar|swing.*tree|langur", [("monkey_motion", "swing"), ("monkey_motion", "monkey_jump")]),
    (r"rain|barish|baarish", [("effect", "rain")]), (r"wet|puddle|keechad|mud", [("effect", "wet"), ("effect", "puddle")]), (r"lightning|bijli|thunder", [("effect", "lightning")]), (r"storm|aandhi|toofan", [("effect", "storm")]),
    (r"wind|hawa|breeze", [("effect", "wind")]), (r"leaves|patte", [("effect", "leaves")]), (r"petal|flower shower|phool", [("effect", "petals")]), (r"snow|baraf", [("effect", "snow")]), (r"fog|kohra|mist", [("effect", "fog")]),
    (r"sun.?ray|god.?ray|sunbeam|dhoop", [("effect", "sun_rays")]), (r"rainbow|indradhanush", [("effect", "rainbow")]), (r"cloud|baadal", [("effect", "clouds")]), (r"night|raat|moon", [("effect", "night")]),
    (r"sunset|golden hour|grade", [("effect", "grade")]), (r"dawn|sunrise|early morning|subah", [("effect", "dawn_grade")]), (r"dusk|evening light|sandhya|shaam", [("effect", "dusk_grade")]), (r"lamp.?lit|lantern|evening.*lamp|lamp.*evening|lit by lamp", [("effect", "evening_lamp_grade")]), (r"heat|loo|mirage|garmi", [("effect", "heat_shimmer")]), (r"water|pond|river|talab|nadi|ripple", [("effect", "water")]),
    (r"\bfire\b|\baag\b|flame", [("effect", "flame")]), (r"diya|deepak|lamp", [("effect", "diya"), ("effect", "lamp_glow")]), (r"chimney|smoke column|dhuan", [("life", "chimney_smoke"), ("life", "smoke")]), (r"smoke", [("effect", "smoke")]), (r"steam|bhaap|chai", [("effect", "steam")]),
    (r"chulha|stove|cooking fire", [("effect", "chulha")]), (r"bonfire|holika|lohri", [("effect", "bonfire")]), (r"torch|flashlight|tourch", [("effect", "torch")]), (r"firefl|jugnu", [("effect", "fireflies")]),
    (r"festival light|diwali light|string light|jhalar", [("effect", "festival_lights")]), (r"firework|patakh|crackers?", [("effect", "fireworks")]), (r"sparkler|phuljhadi", [("effect", "sparklers")]), (r"holi|colou?r powder|gulal", [("effect", "holi_burst")]),
    (r"\?|question|confus.*mark", [("effect", "question")]), (r"exclam|surpris|shock", [("effect", "exclaim")]), (r"zzz|snor", [("effect", "zzz")]), (r"sweat|nervous|worr", [("effect", "sweat_drop")]), (r"anger|gussa|angry mark", [("effect", "anger_mark")]),
    (r"heart|love|pyaar", [("effect", "hearts")]), (r"dizzy|stars? around|chakkar", [("effect", "dizzy_stars")]), (r"sparkle|twinkle|shine", [("effect", "sparkles")]), (r"idea|bulb|aha", [("effect", "idea_bulb")]), (r"tears?|aansu", [("effect", "tears")]),
    (r"blush|sharm", [("effect", "blush")]), (r"gloom|sad cloud|udaas", [("effect", "gloom_cloud")]), (r"music|song|note|gaana", [("effect", "music_notes")]), (r"speed.?line|zoom lines|fast", [("effect", "speed_lines")]),
    (r"impact|hit star|thud|bang", [("effect", "impact_star")]), (r"dust cloud|smear|blur.*move", [("effect", "smear")]), (r"aura|glow|power.?up", [("effect", "aura")]),
    (r"shake|earthquake|bhukamp", [("effect", "shake")]), (r"zoom punch|punch.?in", [("effect", "zoom_punch")]), (r"vignette", [("effect", "vignette")]), (r"flash|camera click|white flash", [("effect", "flash_white")]), (r"freeze|pause frame", [("time", "freeze_time")]),
    (r"ken burns|slow pan|pan and zoom", [("camera", "ken_burns")]), (r"push.?in|dolly in|close.?up|zoom in", [("camera", "push_in")]), (r"pull.?out|reveal|zoom out", [("camera", "pull_out")]), (r"whip|swish pan", [("camera", "whip_pan")]),
    (r"two.?shot|both characters|conversation framing", [("camera", "two_shot")]), (r"follow|tracking|track the", [("camera", "follow")]), (r"parallax|depth|layers", [("camera", "ken_burns")]), (r"focus.?pull|rack focus|defocus", [("camera", "focus_pull")]),
    (r"dutch|tilt.*camera|slanted", [("camera", "dutch")]),
    (r"\bcut\b", [("transition", "cut")]), (r"dissolve|cross.?fade", [("transition", "dissolve")]), (r"fade.*black|dip.*black", [("transition", "dip_black")]), (r"fade.*white|dip.*white", [("transition", "dip_white")]), (r"wipe", [("transition", "wipe")]),
    (r"iris", [("transition", "iris")]), (r"page.?turn|storybook", [("transition", "page_turn")]), (r"star.?wipe", [("transition", "star_wipe")]), (r"flashback|dream", [("transition", "flashback")]),
    (r"meanwhile|itne mein|us waqt", [("transition", "meanwhile")]), (r"clock.?spin|time passes|days? later", [("transition", "clock_spin")]),
    (r"throw|toss|phenk", [("prop_motion", "throw")]), (r"drop|fall.*object|bounce", [("prop_motion", "fall_bounce")]), (r"ball|gend", [("prop_motion", "ball_bounce")]), (r"roll|ludh", [("prop_motion", "roll")]), (r"slide|slip.*object", [("prop_motion", "slide")]),
    (r"pour|ungl|dhaar|fill.*glass|milk", [("prop_motion", "pour")]), (r"\bstir|ladle|chamach", [("prop_motion", "stir")]), (r"jhula|swing(?!.*tree)|rope swing", [("prop_motion", "swing")]), (r"fan|pankha", [("prop_motion", "fan")]),
    (r"clock|ghadi|watch hands", [("prop_motion", "clock_hands")]), (r"kite|patang|manjha", [("prop_motion", "kite")]), (r"\bdoor|darwaza|gate", [("prop_motion", "door")]), (r"clothesline|washing|kapde|sukh", [("prop_motion", "clothesline")]),
    (r"flag|jhanda|banner|tiranga", [("prop_motion", "flag")]), (r"paper|letter|chitthi|leaf.*fly", [("prop_motion", "paper_fly")]), (r"eat.*(laddoo|ladoo|roti|sweet)|food.*(disappear|vanish)|bites?|crumb", [("prop_motion", "food_disappear"), ("prop_motion", "food_vanish")]), (r"snatch|animal eats|goat eats|dog eats|steals? (the )?(food|roti|laddoo)", [("prop_motion", "food_eaten_by_animal")]),
    (r"coin|sikk|count.*(money|sweet)|rupee|paise|distribut", [("prop_motion", "coins")]),
    (r"bird.*sky|flock|birds? fly", [("life", "birds")]), (r"villager|background people|distant people|crowd walking", [("life", "villagers")]), (r"cattle|cows? grazing|herd|gaay.*chara", [("life", "cattle")]),
    (r"tree.*sway|trees? moving", [("life", "tree_sway")]), (r"water.?wheel|rahat|well|kuan|hand.?pump|haath pump", [("life", "water_wheel")]), (r"bicycle|cycle pass|cyclist", [("life", "cycle")]), (r"mela|fair|market crowd|crowd", [("life", "crowd")]),
    (r"voice|dialogue|dub|speech", [("sfx", "pop")]), (r"sfx|sound effect|pop|boing|whoosh|ding|splash|crunch", [("sfx", "pop")]), (r"ambien|background sound|birdsong|cricket", [("ambience", "village_day")]), (r"music|bgm|theme song", [("sfx", "tada")]),
    (r"title|opening card|name card", [("title", "title_card")]), (r"lower.?third|name tag", [("title", "lower_third")]), (r"subtitle|caption|hindi text|english text", [("title", "subtitles")]), (r"end card|moral|subscribe", [("title", "end_card")]),
    (r"thumbnail", [("title", "title_card")]),
    (r"qa|check|quality", [("qa", "blank_frames")]),
]
# things a flat 2D cut-out cannot do properly (need -> reason)
NOT_POSSIBLE = [(r"360|turnaround|rotate.*character|3d|turn around fully|back view|side view of|profile", "a cut-out has one drawn view; other views need extra drawn art (side/back sprites)"),
                (r"realistic.*(water|fluid|cloth)|fluid sim|cloth sim", "no simulation in a cut-out: use the stylised water / flag / clothesline effects"),
                (r"morph|transform.*into|shape.?shift", "needs drawn in-between frames; use a dissolve/flash hiding a sprite swap"),
                (r"hair.*(strand|physics)|fur", "no per-strand physics; hair moves as a rigid layer with the head"),
                (r"lip.?sync.*(phoneme|viseme)|exact mouth shapes", "only open/closed + mouth sprites; per-phoneme visemes need extra drawn mouths")]
WEAK = {"flashback": ("fn", "only a colour treatment + dissolve"), "meanwhile": ("fn", "text card, no drawn art"), "dance_simple": ("fn", "simple loops only; real choreography needs hand-keyed poses"),
        "clap_dance": ("fn", "simple loops only; real choreography needs hand-keyed poses"), "hop_dance": ("fn", "simple loops only; real choreography needs hand-keyed poses"),
        "garba_turn_clap": ("fn", "the turn is a narrowing of the body, not a real rotation"), "parallax": ("text", "layers are auto-split by heuristics; art with hand-made depth layers looks better"),
        "focus": ("text", "blur is per depth layer, not per object")}

BRIEF = ["idle breathing", "nod", "head shake", "head tilt", "wave", "point", "hand to mouth", "reach and take", "give", "clap", "hands on hips", "scratch head", "think", "namaste", "shrug", "cry rub eyes", "laugh bounce",
         "jump", "walk cycle", "run cycle", "tiptoe sneak", "sit down", "stand up", "fall comic", "carry matka on head", "dance garba",
         "goat walk", "dog trot", "cow graze", "buffalo lie down sleep", "cat sit", "hen peck", "parrot fly", "monkey swing in tree", "donkey bray", "bullock gallop", "dog bark", "goat bleat", "cow moo", "dawn light", "dusk light", "lamp-lit evening", "chimney smoke column", "banana peel slip", "trip and fall forward", "sit bump", "clap dance", "hop dance", "garba turn and clap", "dog snatches roti and eats", "dog wag tail",
         "wet dog shake off", "goat headbutt", "dog beg for food", "monkey steal and run",
         "rain", "wet ground puddle", "lightning", "storm", "wind blowing leaves", "falling petals", "snow", "fog", "sun rays", "rainbow", "clouds", "sunset grade", "night with moon", "heat shimmer", "pond water ripple",
         "fire flame", "diya lamp", "chimney smoke", "chai steam", "chulha cooking fire", "lohri bonfire", "torch in dark", "fireflies", "diwali string lights", "fireworks", "phuljhadi sparklers", "holi colour powder",
         "question mark", "exclamation", "zzz sleeping", "sweat drop", "anger mark", "hearts love", "dizzy stars", "sparkle", "idea bulb", "tears", "blush", "gloom sad cloud", "music notes", "speed lines", "impact star",
         "dust smear", "aura power up", "camera shake", "zoom punch", "vignette", "white flash", "freeze frame",
         "ken burns", "push in close-up", "pull out reveal", "whip pan", "two-shot", "follow tracking", "parallax depth layers", "focus pull", "dutch tilt",
         "cut", "dissolve", "fade to black", "wipe", "iris", "page turn", "star wipe", "flashback", "meanwhile card", "time passes clock spin",
         "throw ball", "drop and bounce", "roll", "slide", "pour milk", "stir", "jhula swing", "ceiling fan", "clock hands", "kite", "door open", "clothesline washing", "flag", "paper flying", "eat laddoo crumbs", "count coins",
         "birds in sky", "distant villagers", "cattle grazing", "tree sway", "hand pump water wheel", "bicycle passing", "mela crowd",
         "sfx pop", "ambience village", "voice dialogue", "title card", "lower third", "subtitles hindi english", "end card moral subscribe", "thumbnail",
         "character turnaround 360", "realistic fluid simulation", "morph transformation"]


def _flatten(data):
    out = []
    def add(x, story=None):
        if isinstance(x, str): out.append((story, x))
        elif isinstance(x, dict):
            txt = next((x[k] for k in ("need", "name", "asset", "description", "text", "title", "item") if isinstance(x.get(k), str)), None)
            if txt is None and x.get("id"): txt = str(x["id"])
            if txt: out.append((story or x.get("story"), txt + (" " + x["description"] if isinstance(x.get("description"), str) and x.get("description") != txt else "")))
            else:
                for k, v in x.items():
                    if isinstance(v, (list, dict)): add(v, story or (k if isinstance(k, str) else None))
        elif isinstance(x, list):
            for y in x: add(y, story)
    if isinstance(data, dict):
        if "needs" in data: add(data["needs"])
        else:
            for k, v in data.items(): add(v, k)
    else: add(data)
    return out


def classify(text):
    """-> {"status": implemented|weak|not_possible|missing, "functions": [(kind, name)], "note": str}"""
    t = text.lower()
    for rx, why in NOT_POSSIBLE:
        if re.search(rx, t): return {"status": "not_possible", "functions": [], "note": why}
    fns = []
    for rx, targets in RULES:
        if re.search(rx, t):
            for k, n in targets:
                hit = R.find(n) if k == "motion" else ([(k, n)] if n in R.REGISTRY.get(k, {}) else [])
                if k == "motion": hit = [h for h in hit if h[0] in ("motion",)] or hit
                for h in hit:
                    if h not in fns: fns.append(h)
    if not fns: return {"status": "missing", "functions": [], "note": "no toolkit function matches this need"}
    weak = [w for k, (where, w) in WEAK.items() if (where == "text" and k in t) or (where == "fn" and any(k == n for _, n in fns[:2]))]
    return {"status": "weak" if weak else "implemented", "functions": fns[:6], "note": weak[0] if weak else ""}


def load_needs(path=None):
    here = os.path.dirname(os.path.abspath(__file__)); cands = [path] if path else []
    d = here
    for _ in range(4):
        cands.append(os.path.join(d, "stories", "hindi", "ASSET_NEEDS.json")); d = os.path.dirname(d)
    for c in cands:
        if c and os.path.exists(c): return c, _flatten(json.load(open(c, encoding="utf-8")))
    return None, [(None, b) for b in BRIEF]


def report(path=None):
    src, needs = load_needs(path); rows = []
    for story, text in needs:
        c = classify(text); rows.append({"story": story, "need": text, **c, "functions": [f"{k}:{n}" for k, n in c["functions"]]})
    cnt = {s: sum(r["status"] == s for r in rows) for s in ("implemented", "weak", "not_possible", "missing")}
    return {"source": src or "built-in brief checklist (stories/hindi/ASSET_NEEDS.json not found)", "total": len(rows), "counts": cnt, "rows": rows}


def format_report(rep, only=None):
    L = [f"ASSET_NEEDS coverage - source: {rep['source']}", f"  {rep['total']} needs: " + ", ".join(f"{k} {v}" for k, v in rep["counts"].items())]
    for r in rep["rows"]:
        if only and r["status"] not in only: continue
        L.append(f"  [{r['status']:12s}] {('(' + r['story'] + ') ') if r['story'] else ''}{r['need'][:70]:70s} -> {', '.join(r['functions'][:3]) or r['note']}" + (f"  ({r['note']})" if r["functions"] and r["note"] else ""))
    return "\n".join(L)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]; rep = report(args[0] if args else None)
    print(json.dumps(rep, ensure_ascii=False, indent=1) if "--json" in sys.argv else format_report(rep, only=("weak", "not_possible", "missing") if "--gaps" in sys.argv else None))
