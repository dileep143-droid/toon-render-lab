"""Stage 1: Gemini TEXT writes the shot list (JSON) for a time window of an episode.
  python plan.py <ep> --start 0 --seconds 60          -> out/<ep>/plan.json
Reads (private, never in this code): episodes/<ep>/audio_full/units_timed.json, the story script stories/hindi/<NN>_*.md,
episodes/<ep>/BEATS.md (if present) and out/series.json (character bible)."""
import argparse, glob, json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gem

POSES = {  # pose library (skeletons live in kaggle_runner.py); facing left = generate the _r pose and set "flip": true
    "stand": "standing, front view, arms down",
    "stand_3q": "standing, three-quarter view facing right, arms down",
    "walk": "walking to the right, mid-step, three-quarter view",
    "sit_cross": "sitting cross-legged on a low flat wooden bed (charpai) standing on four short legs on the ground, front view, hands in the lap",
    "sit_hold": "sitting cross-legged on a low flat wooden bed (charpai) standing on four short legs on the ground, holding a plate on the lap with both hands",
    "point": "standing, front view, one hand raised with the index finger up (warning / wagging finger)",
    "salute": "standing, three-quarter view facing right, saluting with the right hand at the forehead",
    "reach": "standing, three-quarter view facing right, one arm stretched forward reaching",
    "hand_cheek": "standing, front view, one hand on the cheek, looking around",
    "hold_plate": "standing, three-quarter view facing right, carrying a plate in front with both hands",
    "animal_side": "animal, side view facing right, standing on four legs",
    "animal_lie": "animal, lying down curled up, side view facing right",
}
MOVES = """moves (times in seconds from the shot start):
  {"type":"walk","t0":0,"t1":2.5,"to_x":0.55}         slide across with a bounce step + small tilt (x = feet position 0..1 of the plate width)
  {"type":"hop","t0":1,"t1":1.6}                      one hop (animals, excitement)
  {"type":"turn","t":2.0}                             flip to face the other way
  {"type":"arm","t0":0.5,"t1":3,"angle":-35,"count":3} swing the movable arm from the shoulder (angle in degrees, + = down/back, - = up/forward), count = repetitions
  {"type":"nod","t0":1,"t1":2}  {"type":"shake","t0":0,"t1":1.5}  {"type":"tilt","t0":0,"t1":2,"angle":8}  head moves
  {"type":"peek","t0":0,"t1":1.5,"edge_x":0.18}       only the part of the actor right of edge_x is visible (hiding behind a door frame at edge_x), slides out
  {"type":"tail","t0":0,"t1":5}                       animal tail wag
  {"type":"sink","t0":0,"t1":2,"dy":0.05}             sit back / settle down (moves down by dy of the plate height)"""

PROMPT = """You are the storyboard artist for a Hindi 2D cut-out cartoon for kids (style: colourful Indian village illustration; the picture is mostly still,
characters are cut-out layers that slide, hop, turn, swing an arm, nod, blink and lip-sync; the camera pans/zooms slowly).
Write the shot list for the dialogue units below, IN ORDER, every unit exactly once. One shot may cover 1-3 consecutive units.
Follow the story's stage directions and the beat list (they are the director's orders): who is on screen, props, actions, emotions.

CHARACTERS (ids): {chars}
POSE LIBRARY (pose ids; a pose is generated once per character and reused; facing left = same pose with "flip": true): {poses}
{moves}

OUTPUT JSON:
{{
 "plates": [{{"id":"...","prompt":"background only, NO people/animals, wide 16:9; say exactly where the door/charpai/wall/tree are (left/centre/right) and keep the floor of the middle/lower part clear","time":"morning|noon|evening|night"}}],
 "props": [{{"id":"laddoo","prompt":"a single round yellow besan laddoo"}}],
 "poses": [{{"id":"<char>_<pose>[_<variant>]","char":"<char id>","pose":"<pose id>","prompt":"expression, what they hold or wear differently (e.g. glasses pushed up on the head); do NOT describe the character's design, it is added automatically"}}],
 "shots": [{{"id":"s01","units":[0],"plate":"<plate id>","beat":"what happens (1 line)",
   "camera":{{"from":[cx,cy,zoom],"to":[cx,cy,zoom]}},     // centre 0..1 of the plate, zoom 1 = whole plate, 2 = half width (close-up). Slow moves only.
   "actors":[{{"pose":"<pose id>","x":0.3,"foot_y":0.92,"height":0.6,"flip":false,"z":1,"moves":[...]}}],   // x,foot_y = feet position in plate (0..1), height = fraction of plate height
   "objects":[{{"prop":"laddoo","from":[x,y] or "<pose id>.hand","to":[x,y] or "<pose id>.hand" or "<pose id>.mouth","t0":1,"t1":2,"scale":0.05}}],
   "sfx":[{{"id":"goat","t":0.2}}]
 }}],
 "skipped": ["stage directions you could not show, if any"]
}}
Rules: 6-12 shots for 60 s; vary wide shots and close-ups (zoom 1.6-2.4 centred on the speaker's face); every speaking character must be on screen
during their line with their face visible; at least 3 shots with real movement (walk in/out, hop, arm swing, turn, object to hand); reuse poses;
at most 10 poses and 2 plates; sitting characters use sit_* poses (their charpai is part of their pose image, so plates must NOT contain a charpai
where they sit); sleeping animals use animal_lie; units with no audio (animal sounds) get an sfx id from {sfx}; heights: adult standing 0.55-0.65,
child standing 0.45-0.5, sitting with charpai 0.45-0.55, goat 0.28, dog lying 0.15 (wide shot).

STORY SCRIPT (stage directions in italics):
{story}

BEAT LIST:
{beats}

UNITS (idx, speaker, emotion, duration s, text):
{units}
"""


CRITIC = """You are the director checking a storyboard draft. Fix it and return the FULL corrected plan in the same JSON format,
plus "notes": a short list of what you changed. Check:
1. Continuity over time: what each character holds/wears must follow the stage directions in order (a prop that appears or moves later
   in the script must not be there earlier; e.g. a costume change or an object on the head only from the moment the script says so).
   Use separate pose variants when the look changes.
2. Every key action in the stage directions and beat list for these units is visible as a move or object animation
   (counting -> arm swings in time with the counted words + objects; peeking -> peek; saluting -> salute pose + arm; lying/sitting back -> sink).
3. Every unit index appears exactly once, in order; the speaker of every unit is on screen with the face visible.
4. Positions: actors stand on the floor (foot_y 0.85-0.95), do not overlap the same spot, sizes follow the height rules.
5. At least 3 shots with real movement (walk, hop, arm, object). Camera moves are slow."""


def load(ep, start, seconds):
    ep_dir = os.path.join(REPO, "episodes", ep)
    units = json.load(open(os.path.join(ep_dir, "audio_full", "units_timed.json"), encoding="utf-8-sig"))
    n = int(re.sub(r"\D", "", ep) or 1)
    story = open(glob.glob(os.path.join(REPO, "stories", "hindi", f"{n:02d}_*.md"))[0], encoding="utf-8-sig").read()
    beats_p = os.path.join(ep_dir, "BEATS.md")
    beats = open(beats_p, encoding="utf-8-sig").read() if os.path.exists(beats_p) else ""
    t = 0; sel = []
    for u in units:
        d = u.get("dur") or 1.5
        if t + d > start and t < start + seconds:
            sel.append(u)
        t += d + 0.4
    return ep_dir, units, sel, story, beats


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("ep"); ap.add_argument("--start", type=float, default=0); ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--out"); ap.add_argument("--force", action="store_true"); a = ap.parse_args()
    out = a.out or os.path.join(HERE, "out", a.ep); os.makedirs(out, exist_ok=True)
    pj = os.path.join(out, "plan.json")
    if os.path.exists(pj) and not a.force:
        print("plan exists", pj); return
    S = json.load(open(os.path.join(HERE, "out", "series.json"), encoding="utf-8-sig"))
    ep_dir, units, sel, story, beats = load(a.ep, a.start, a.seconds)
    scenes = sorted({u["scene"] for u in sel})
    # only the story part for the selected scenes (keeps the prompt small)
    parts = re.split(r"(?m)^## ", story); story_sel = parts[0][:600] + "".join("## " + p for p in parts[1:] if any(re.search(rf"\b{s}\b", p.split("\n")[0]) for s in scenes))
    ul = "\n".join(f'{u["idx"]} | {u["speaker"]} | {u.get("emotion","")} | {u.get("dur") or "NO AUDIO"} | {u["text"]}' for u in sel)
    prompt = PROMPT.format(chars=json.dumps({k: v["desc"][:90] for k, v in S["characters"].items()}, ensure_ascii=False),
                           poses=json.dumps(POSES), moves=MOVES, sfx=list(S["sfx"].keys()), story=story_sel, beats=beats[:6000], units=ul)
    plan = gem.text(prompt, temperature=0.5)
    # critic pass: a second Gemini call checks the draft against the director's orders and returns a corrected plan
    critic = (CRITIC + "\n\nDRAFT PLAN:\n" + json.dumps(plan, ensure_ascii=False) + "\n\nTHE ORIGINAL BRIEF:\n" + prompt)
    try:
        fixed = gem.text(critic, temperature=0.2)
        if isinstance(fixed, dict) and fixed.get("shots"):
            print("critic notes:", fixed.pop("notes", ""))
            plan = fixed
    except Exception as e:
        print("critic failed, keeping draft:", e)
    plan["ep"] = a.ep; plan["units"] = {str(u["idx"]): u for u in sel}
    covered = [i for s in plan["shots"] for i in s["units"]]
    missing = [u["idx"] for u in sel if u["idx"] not in covered]
    if missing: print("WARNING units not covered:", missing)
    json.dump(plan, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"plan: {len(plan['shots'])} shots, {len(plan['poses'])} poses, {len(plan['plates'])} plates, {len(plan.get('props', []))} props -> {pj}")


if __name__ == "__main__":
    main()
