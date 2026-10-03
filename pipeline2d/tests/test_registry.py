import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, registry as R, puppet as PU

BG = T.make_background("village_day")
SPEC = {"duration": 3.0,
        "cast": {"dadi": {"kind": "human", "art": "dadi", "x": 900, "y": 640, "height": 380, "flip": True}, "sheru": {"kind": "animal", "art": "dog", "x": 300, "y": 660, "height": 170}},
        "events": [{"motion": "wave", "who": "dadi", "start": 0.5, "dur": 1.5}, {"motion": "bark", "who": "sheru", "start": 1.0, "dur": 1.0}, {"effect": "rain", "start": 0, "intensity": 0.7},
                   {"effect": "question", "who": "dadi", "start": 1.0, "dur": 1.2}, {"life": "birds", "start": 0}, {"camera": "push_in", "start": 0.5, "dur": 2, "target": [0.7, 0.5], "amount": 1.3},
                   {"sfx": "pop", "start": 2.1}, {"ambience": "village_day", "start": 0, "end": 3}]}


def test_registry_covers_every_module():
    a = R.list_all()
    assert len(a["motion"]) >= 27 and len(a["animal_motion"]) >= 20 and len(a["bird_motion"]) >= 6 and len(a["effect"]) >= 50 and len(a["transition"]) >= 11 and len(a["prop_motion"]) == 17
    assert set(PU.MOTIONS) == set(a["motion"]) and "wave" in a["motion"] and "gallop" in a["animal_motion"] and "swing" in a["monkey_motion"] and "lightning" in a["effect"]
    d = R.describe("effect", "rain"); assert "intensity" in d["params"] and d["doc"]
    assert ("effect", "rain") in R.find("rain")


def test_schema_is_valid_json_and_lists_names():
    s = R.schema(); json.dumps(s); one = s["properties"]["events"]["items"]["oneOf"]
    assert any("rain" in o["properties"].get("effect", {}).get("enum", []) for o in one) and any("wave" in o["properties"]["motion"]["enum"] for o in one)
    try:
        import jsonschema; jsonschema.validate(SPEC, s)
    except ImportError: pass


def test_validation_catches_typos_and_wrong_species():
    assert R.validate_shot(SPEC) == []
    bad = {"cast": SPEC["cast"], "events": [{"motion": "wavee", "who": "dadi"}, {"motion": "bark", "who": "dadi"}, {"effect": "rainn"}, {"effect": "rain", "intensty": 1}, {"motion": "wave", "who": "ghost"},
                                            {"camera": "push_in", "dur": -1}, {"prop_motion": "throw"}, {"foo": 1}]}
    errs = R.validate_shot(bad); assert len(errs) >= 8, errs
    assert any("known" in e for e in errs) and any("not in cast" in e for e in errs)


def test_shot_renders_any_frame_alone_and_deterministically():
    sh = R.Shot(SPEC, plate=BG); a = sh.frame(1.5); b = R.Shot(SPEC, plate=BG).frame(1.5); sh.frame(0.2)
    assert a.shape == (720, 1280, 3) and np.array_equal(a, b) and np.array_equal(sh.frame(1.5), a)
    assert np.abs(sh.frame(0.0).astype(int) - sh.frame(2.5).astype(int)).mean() > 2                          # things move


def test_shot_event_effects_show_up():
    base = {"cast": SPEC["cast"], "events": []}; f0 = R.Shot(base, plate=BG).frame(1.4)
    ev = dict(base, events=[{"effect": "question", "who": "dadi", "start": 1.0, "dur": 1.2}]); f1 = R.Shot(ev, plate=BG).frame(1.4)
    d = np.abs(f1.astype(int) - f0.astype(int)).sum(-1) > 30; ys, xs = np.nonzero(d); assert d.sum() > 200 and 700 < xs.mean() < 1100 and ys.mean() < 400        # near dadi's head
    pr = dict(base, events=[{"prop_motion": "throw", "prop": "ball", "start": 0.5, "dur": 1.0, "p0": "dadi.hand_r", "p1": [300, 600]}])
    s = R.Shot(pr, plate=BG, props={"ball": T.make_prop("ball", 60)}); assert np.abs(s.frame(1.0).astype(int) - R.Shot(base, plate=BG).frame(1.0).astype(int)).sum() > 1000


def test_transition_event_and_audio_plan():
    spec = {"cast": {}, "duration": 2, "events": [{"transition": "dissolve", "start": 1.0, "dur": 1.0}]}
    sh = R.Shot(spec, plate=BG); nxt = np.full_like(BG, 255); assert np.array_equal(sh.frame(0.5, nxt), BG) and np.array_equal(sh.frame(2.0, nxt), nxt) and not np.array_equal(sh.frame(1.5, nxt), BG)
    pl = R.audio_plan(SPEC); assert pl["sfx"] == [{"t": 2.1, "name": "pop"}] and pl["ambience"][0]["loc"] == "village_day" and pl["duration"] == 3.0


def test_strict_mode_rejects_bad_shot_and_speed():
    try: R.Shot({"cast": {}, "events": [{"effect": "nope"}]}, plate=BG); assert False
    except ValueError as e: assert "unknown effect" in str(e)
    sh = R.Shot(SPEC, plate=BG); sh.frame(0.1); t = C.bench(lambda: sh.frame(1.3), 3); assert t < 0.6, t


def test_freeze_event():
    spec = {"cast": {"k": {"kind": "human", "art": "kid", "x": 300, "y": 660, "height": 300}}, "duration": 3, "events": [{"motion": "walk_cycle", "who": "k", "start": 0, "dur": 3, "speed": 200}, {"freeze": True, "at": 1.0, "hold": 1.0}]}
    sh = R.Shot(spec, plate=BG); assert sh.duration == 4.0 and np.array_equal(sh.frame(1.0), sh.frame(1.8)) and not np.array_equal(sh.frame(1.0), sh.frame(2.5))
