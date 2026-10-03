"""registry.py - ONE registry for the whole toolkit + a shot runner, so a shot JSON can call every function by name.

    import registry as R
    R.list_all()                       # {"motion": [...], "effect": [...], ...}
    R.describe("motion", "wave")       # params + doc
    R.validate_shot(shot)              # -> list of error strings (empty = fine)
    shot = R.Shot(spec, plate=bg, assets={"dadi": (img, rig)}, props={"ball": sprite})
    frame = shot.frame(t)              # any t, any order (everything is stateless in time)
    R.audio_plan(spec)                 # the sfx / voice / music / ambience events -> audio_mix.mix() kwargs

SHOT JSON (all times in seconds, relative to the shot start)
{ "duration": 6.0,
  "cast":   { "dadi": {"kind": "human", "art": "dadi", "x": 900, "y": 640, "height": 380, "flip": true},
              "sheru": {"kind": "animal", "art": "dog", "x": 300, "y": 660, "height": 160} },
  "events": [ {"motion": "wave", "who": "dadi", "start": 2.0, "dur": 1.5},                  # human / animal / bird / monkey motion, chosen by the cast kind
              {"effect": "rain", "start": 0, "intensity": 0.7},
              {"effect": "question", "who": "dadi", "start": 3, "dur": 1.2},                # who -> its head anchor ("dadi.hand_r" etc. also work)
              {"camera": "push_in", "start": 1, "dur": 2, "target": [0.7, 0.5], "amount": 1.4},
              {"prop_motion": "throw", "prop": "ball", "start": 2, "dur": 1, "p0": "dadi.hand_r", "p1": [300, 600]},
              {"life": "birds", "start": 0}, {"ambient": "village_morning"},
              {"transition": "dissolve", "start": 5.5, "dur": 0.5},                          # needs shot.frame(t, next_frame=...)
              {"title": "lower_third", "name": "दादी", "role": "सबकी प्यारी", "start": 1, "dur": 3},
              {"sfx": "pop", "start": 2.1}, {"voice": "line1.wav", "start": 0.4}, {"music": "theme.wav"}, {"ambience": "village_day", "start": 0, "end": 6} ] }
`cast.kind`: human | animal (quadruped) | bird | monkey.  `art`: a testart name, or pass assets={id: (image, rig)} for real art.
Event order does not matter; draw order is fixed: plate -> life -> characters -> props -> camera -> effects -> titles -> transition."""
import inspect, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tk_core as C
import puppet as PU, animals as AN, effects as FX, camera as CA, transitions as TR, props_motion as PM, scene_life as SL, titles as TI, audio_mix as AM, qa_checks as QA

HUMAN_ARTS = ("man", "kid", "girl", "dadi"); QUAD_ARTS = ("goat", "dog", "cow", "buffalo", "cat", "donkey", "bullock"); BIRD_ARTS = ("hen", "parrot")
AUDIO_NAMES = {"sfx": "pop boing whoosh ding thud splash coin crunch click tada laugh_pop".split(), "ambience": sorted(AM.AMBIENCE_DEFAULTS)}


class Entry:
    def __init__(self, kind, name, fn, doc="", params=None): self.kind, self.name, self.fn, self.doc, self.params = kind, name, fn, doc, params or {}

    def __repr__(self): return f"<{self.kind}:{self.name} {list(self.params)}>"


def _params(fn, skip=("frame", "t", "dur", "rig", "self", "sprite", "a", "b", "u", "kw", "k", "_")):
    try: sig = inspect.signature(fn)
    except (TypeError, ValueError): return {}
    return {n: (None if p.default is inspect._empty else p.default) for n, p in sig.parameters.items() if n not in skip and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)}


def _doc(fn): return (inspect.getdoc(fn) or "").split("\n\n")[0]


def _build():
    R = {k: {} for k in ("motion", "animal_motion", "bird_motion", "monkey_motion", "effect", "camera", "transition", "prop_motion", "life", "ambient", "title", "sfx", "ambience", "qa")}
    for n, f in PU.MOTIONS.items(): R["motion"][n] = Entry("motion", n, f, _doc(f), _params(f))
    for n, f in AN.AM.items(): R["animal_motion"][n] = Entry("animal_motion", n, f, _doc(f), _params(f))
    for n, f in AN.BM.items(): R["bird_motion"][n] = Entry("bird_motion", n, f, _doc(f), _params(f))
    for n, f in AN.MM.items(): R["monkey_motion"][n] = Entry("monkey_motion", n, f, _doc(f), _params(f))
    for n, e in FX.EFFECTS.items(): R["effect"][n] = Entry("effect", n, e.fn, e.doc.split("\n")[0], dict(e.defaults))
    for n, f in CA.MOVES.items(): R["camera"][n] = Entry("camera", n, f, _doc(f), _params(f))
    for n, f in TR.TRANSITIONS.items(): R["transition"][n] = Entry("transition", n, f, _doc(f), _params(f))
    for n, f in PM.PROP_MOTIONS.items(): R["prop_motion"][n] = Entry("prop_motion", n, f, _doc(f), _params(f))
    for n, f in SL.LIFE.items(): R["life"][n] = Entry("life", n, f, _doc(f), _params(f))
    for n, p in SL.LIFE_PRESETS.items(): R["ambient"][n] = Entry("ambient", n, p, "bundle: " + ", ".join(x[0] for x in p))
    for n, f in TI.TITLES.items(): R["title"][n] = Entry("title", n, f, _doc(f), _params(f))
    for n in AUDIO_NAMES["sfx"]: R["sfx"][n] = Entry("sfx", n, AM.synth_sfx, "sound effect (placeholder synth until SFX_LIBRARY has a file)")
    for n in AUDIO_NAMES["ambience"]: R["ambience"][n] = Entry("ambience", n, AM.synth_ambience, "ambience loop for a location")
    for n, f in QA.CHECKS.items(): R["qa"][n] = Entry("qa", n, f, _doc(f), _params(f))
    return R


REGISTRY = _build()
# the key that names each event kind in a shot JSON
EVENT_KEYS = {"motion": None, "effect": "effect", "camera": "camera", "transition": "transition", "prop_motion": "prop_motion", "life": "life", "ambient": "ambient", "title": "title",
              "sfx": "sfx", "voice": "voice", "music": "music", "ambience": "ambience"}
CAST_KINDS = {"human": "motion", "animal": "animal_motion", "bird": "bird_motion", "monkey": "monkey_motion"}


def list_all(kind=None):
    return sorted(REGISTRY[kind]) if kind else {k: sorted(v) for k, v in REGISTRY.items()}


def describe(kind, name):
    e = REGISTRY[kind][name]; return {"kind": kind, "name": name, "doc": e.doc, "params": e.params}


def find(name):
    """every (kind, name) with this name (a few names exist for more than one kind, e.g. 'hop', 'idle')"""
    return [(k, name) for k, v in REGISTRY.items() if name in v]


# ============================================================================================================ JSON schema + validation
def event_kind(ev):
    for k in ("motion", "effect", "camera", "transition", "prop_motion", "life", "ambient", "title", "sfx", "voice", "music", "ambience"):
        if k in ev: return k
    return None


def schema():
    """JSON schema (draft-07) of a shot; names are enumerated from the registry"""
    def ev(key, names, extra=None):
        p = {key: ({"enum": names} if names else {"type": ["string", "object"]}), "start": {"type": "number", "minimum": 0}, "dur": {"type": "number", "exclusiveMinimum": 0}, "who": {"type": "string"}}
        p.update(extra or {}); return {"type": "object", "required": [key], "properties": p, "additionalProperties": True}
    motions = sorted(set(REGISTRY["motion"]) | set(REGISTRY["animal_motion"]) | set(REGISTRY["bird_motion"]) | set(REGISTRY["monkey_motion"]))
    return {"$schema": "http://json-schema.org/draft-07/schema#", "title": "2D toolkit shot", "type": "object",
            "properties": {"duration": {"type": "number"}, "cast": {"type": "object", "additionalProperties": {"type": "object", "required": ["kind"], "properties": {
                           "kind": {"enum": sorted(CAST_KINDS)}, "art": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "height": {"type": "number"}, "flip": {"type": "boolean"}}}},
                           "events": {"type": "array", "items": {"oneOf": [ev("motion", motions, {"who": {"type": "string"}}), ev("effect", sorted(REGISTRY["effect"])), ev("camera", sorted(REGISTRY["camera"])),
                                                                          ev("transition", sorted(REGISTRY["transition"])), ev("prop_motion", sorted(REGISTRY["prop_motion"]), {"prop": {"type": "string"}}),
                                                                          ev("life", sorted(REGISTRY["life"])), ev("ambient", sorted(REGISTRY["ambient"])), ev("title", sorted(REGISTRY["title"])),
                                                                          ev("sfx", None), ev("voice", None), ev("music", None), ev("ambience", None)]}}}}


def validate_event(ev, cast=None):
    """list of problems with one event (empty = fine)"""
    k = event_kind(ev)
    if k is None: return [f"no known event key in {sorted(ev)}"]
    errs = []; name = ev[k]
    for f in ("start", "dur"):
        if f in ev and not isinstance(ev[f], (int, float)): errs.append(f"{f} must be a number")
    if "dur" in ev and isinstance(ev["dur"], (int, float)) and ev["dur"] <= 0: errs.append("dur must be > 0")
    if k == "motion":
        who = ev.get("who"); ck = (cast or {}).get(who, {}).get("kind") if cast else None
        if cast is not None and who not in cast: return errs + [f"motion {name!r}: who={who!r} is not in cast"]
        pools = [CAST_KINDS[ck]] if ck else list(CAST_KINDS.values())
        if not any(name in REGISTRY[p] for p in pools) and not (ck in ("animal", "bird", "monkey") and name in REGISTRY["motion"] and ck == "monkey"):
            errs.append(f"unknown {ck or ''} motion {name!r}" + (f"; known: {sorted(REGISTRY[pools[0]])}" if ck else ""))
    elif k in ("effect", "camera", "transition", "prop_motion", "life", "ambient", "title"):
        if name not in REGISTRY[k]: errs.append(f"unknown {k} {name!r}")
        elif k == "effect":
            for p in ev:
                if p in ("effect", "start", "dur", "fade", "who", "anchor", "anchor_joint"): continue
                if p not in REGISTRY["effect"][name].params: errs.append(f"effect {name!r} has no parameter {p!r}; has {sorted(REGISTRY['effect'][name].params)}")
        elif k == "prop_motion" and "prop" not in ev and "sprite" not in ev: errs.append("prop_motion needs 'prop' (id of a sprite in props=)")
    elif k == "sfx" and not isinstance(name, str): errs.append("sfx must be a name or path")
    return errs


def validate_shot(shot):
    errs = []
    cast = shot.get("cast", {})
    for who, c in cast.items():
        if c.get("kind") not in CAST_KINDS: errs.append(f"cast {who}: kind must be one of {sorted(CAST_KINDS)}")
    for i, ev in enumerate(shot.get("events", [])): errs += [f"event {i}: {e}" for e in validate_event(ev, cast)]
    return errs


# ============================================================================================================ the shot runner
def _make_art(kind, art):
    import testart as T
    if kind == "human": return T.make_human(art if art in HUMAN_ARTS else "man")
    if kind == "animal": return T.make_quadruped(art if art in QUAD_ARTS else "goat")
    if kind == "bird": return T.make_bird(art if art in BIRD_ARTS else "hen")
    return T.make_monkey()


class Shot:
    """renders a shot spec. plate: RGB array (or callable t -> RGB). assets: {cast_id: (image, rig)}; props: {prop_id: RGBA sprite}; sprites: {sprite_id: RGBA} for life elements."""
    def __init__(self, spec, plate=None, assets=None, props=None, sprites=None, font=None, lines=None, strict=True):
        self.spec = spec; self.plate = plate; self.props = props or {}; self.sprites = sprites or {}; self.font = font; self.lines = lines or []
        if strict:
            errs = validate_shot(spec)
            if errs: raise ValueError("invalid shot:\n  " + "\n  ".join(errs))
        self.events = list(spec.get("events", [])); self.cast = spec.get("cast", {}); self.art = {}; self.perf = {}
        for who, c in self.cast.items():
            img, rig = (assets or {}).get(who) or _make_art(c["kind"], c.get("art", ""))
            self.art[who] = (img, rig)
            evs = [e for e in self.events if event_kind(e) == "motion" and e.get("who") == who]
            self.perf[who] = (AN.AnimalPerformer if c["kind"] != "human" else PU.Performer)(img, rig, evs)
        cams = [e for e in self.events if "camera" in e]
        self.track = CA.CameraTrack.from_events(cams, spec.get("camera_start")) if cams else None
        self.duration = spec.get("duration", max([e.get("start", 0) + e.get("dur", 0) for e in self.events] + [1.0]))

    # --- helpers
    def _plate(self, t):
        p = self.plate(t) if callable(self.plate) else self.plate
        return C.blank() if p is None else p.copy()

    def draw_cast(self, f, t):
        anchors = {}
        for who, c in self.cast.items():
            flip = bool(c.get("flip", False)); sp, info = self.perf[who].frame(t, flip=flip); img, rig = self.art[who]
            k = c["height"] / float(rig["size"][1]); x = c["x"] + (-1 if flip else 1) * info["travel"] * k
            an = PU.draw_character(f, sp, info, rig, x, c["y"], c["height"], flip=flip)
            for j, p in an.items(): anchors[f"{who}.{j}"] = p
            head = an.get("head_center") or an.get("head") or an.get("head_top") or (x, c["y"] - c["height"] * 0.9); anchors[who] = (head[0], head[1] - c["height"] * (0.08 if c["kind"] == "human" else 0.0))
            anchors[f"{who}.feet"] = (x, c["y"])
        return anchors

    def _screen(self, anchors, cam):
        if cam is None: return anchors
        out = {}
        for n, (x, y) in anchors.items():
            sx, sy, _ = CA.to_screen(cam, x / C.W, y / C.H); out[n] = (sx, sy)
        return out

    def frame(self, t, next_frame=None):
        f = self._plate(t)
        for e in self.events:                                                                              # scene life behind the characters
            if "life" in e or "ambient" in e: f = SL.run_event(f, e, t, self.sprites)
        anchors = self.draw_cast(f, t); local = dict(anchors)
        for e in self.events:
            if "prop_motion" in e: f = PM.run_event(f, e, t, self.props, local)
        cam = self.track.at(t) if self.track else None
        if cam is not None: f = CA.render_view(f, cam)
        scr = self._screen(anchors, cam)
        for e in self.events:
            if "effect" in e: f = FX.run_event(f, e, t, scr)
        for e in self.events:
            if "title" in e: f = TI.run_event(f, {**e, "font": e.get("font", self.font)} if self.font else e, t, lines=self.lines)
        for e in self.events:
            if "transition" in e and next_frame is not None: f = TR.run_event(f, next_frame, e, t)
        return f

    def frames(self, fps=C.FPS, next_shot=None):
        n = int(round(self.duration * fps))
        for i in range(n): yield self.frame(i / fps, None if next_shot is None else next_shot.frame(i / fps))

    def render(self, path, fps=C.FPS, audio=None, crf=26):
        return C.write_video(self.frames(fps), path, fps, audio=audio, crf=crf)


def audio_plan(spec, duration=None):
    """sfx / voice / music / ambience events of a shot -> kwargs for audio_mix.mix_from_plan"""
    ev = spec.get("events", []); pl = {"duration": duration or spec.get("duration", 10.0), "voices": [], "sfx": [], "ambience": [], "music": None}
    for e in ev:
        if "sfx" in e:
            d = {"t": e.get("start", 0.0), "gain_db": e["gain_db"]} if "gain_db" in e else {"t": e.get("start", 0.0)}
            d["path" if os.path.sep in e["sfx"] or e["sfx"].endswith(".wav") else "name"] = e["sfx"]; pl["sfx"].append(d)
        elif "voice" in e: pl["voices"].append({"path": e["voice"], "t": e.get("start", 0.0), **({"gain_db": e["gain_db"]} if "gain_db" in e else {})})
        elif "music" in e: pl["music"] = {"path": e["music"], **{k: e[k] for k in ("gain_db", "fade_in", "fade_out", "start") if k in e}}
        elif "ambience" in e:
            a = {"start": e.get("start", 0.0), "end": e.get("end", pl["duration"])}; a["path" if e["ambience"].endswith((".wav", ".mp3", ".ogg")) else "loc"] = e["ambience"]
            if "gain_db" in e: a["gain_db"] = e["gain_db"]
            pl["ambience"].append(a)
    return pl


if __name__ == "__main__":
    for k, v in list_all().items(): print(f"{k:14s} {len(v):3d}  " + " ".join(v))
    if len(sys.argv) > 1 and sys.argv[1] == "schema": print(json.dumps(schema(), indent=1)[:2000])
