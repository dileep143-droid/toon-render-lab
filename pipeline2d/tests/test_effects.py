import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, effects as FX

BG = T.make_background("village_day")
MARKS = ("question", "exclaim", "exclaim_question", "zzz", "sweat_drop", "anger_mark", "hearts", "dizzy_stars", "sparkles", "aura", "idea_bulb", "sweat_spray",
         "tears", "blush", "gloom_cloud", "music_notes", "speed_lines", "impact_star")
EXTRA = {"smear": dict(sprite=T.make_prop("ball"), path=[[0, 100, 500], [2, 1100, 500]]), "water": dict(region=(0.1, 0.72, 0.9, 0.98), ellipse=True), "zoom_punch": dict(start=0.1), "flash_white": dict(start=0.1)}


def _args(n):
    p = dict(EXTRA.get(n, {}))
    if n in MARKS: p["anchor"] = (640, 330)
    return p


def test_all_effects_run_and_keep_the_frame_format():
    assert len(FX.EFFECTS) >= 50
    for n in FX.EFFECTS:
        for t in (0.0, 0.4, 1.3, 5.0):
            f = BG.copy(); out = FX.apply(f, n, t, **_args(n)); assert out.shape == BG.shape and out.dtype == np.uint8, (n, t)


def test_every_effect_changes_the_picture_at_some_time():
    quiet = {"lightning", "flash_white", "zoom_punch", "wind"}      # event based / sparse: checked in other tests
    for n in FX.EFFECTS:
        if n in quiet: continue
        diffs = []
        for t in (0.3, 0.8, 1.2):
            f = BG.copy(); FX.apply(f, n, t, **_args(n)); diffs.append(int((f != BG).sum()))
        assert max(diffs) > 30, f"{n} draws nothing"


def test_stateless_and_deterministic():
    for n in ("rain", "fireworks", "hearts", "bonfire", "snow", "fog", "leaves", "holi_burst", "lightning"):
        a = BG.copy(); FX.apply(a, n, 1.37, **_args(n)); b = BG.copy()
        for t in (0.2, 3.0, 0.9): FX.apply(BG.copy(), n, t, **_args(n))           # other times in between
        FX.apply(b, n, 1.37, **_args(n)); assert np.array_equal(a, b), n


def test_speed_budget_720p():
    slow = {}
    for n in FX.EFFECTS:
        FX.apply(BG.copy(), n, 0.1, **_args(n))
        s = C.bench(lambda: FX.apply(BG.copy(), n, 0.7, **_args(n)), 5, warm=0)
        if s > 0.1: slow[n] = round(s, 3)
    assert not slow, slow


def test_run_event_window_and_fade():
    ev = {"effect": "rain", "start": 1.0, "dur": 2.0, "intensity": 0.8}
    before = BG.copy(); FX.run_event(before, ev, 0.5); assert np.array_equal(before, BG)
    mid = BG.copy(); FX.run_event(mid, ev, 2.0); assert (mid != BG).sum() > 1000
    after = BG.copy(); FX.run_event(after, ev, 3.5); assert np.array_equal(after, BG)
    edge = BG.copy(); FX.run_event(edge, ev, 1.02); assert (edge != BG).sum() < (mid != BG).sum()       # fades in, no pop


def test_run_event_anchor_from_who():
    f = BG.copy(); FX.run_event(f, {"effect": "question", "who": "dadi", "start": 0, "dur": 2}, 0.6, anchors={"dadi": (300, 400)})
    ys, xs = np.nonzero((f != BG).any(-1)); assert 200 < xs.mean() < 400 and ys.mean() < 400


def test_freeze_time():
    assert FX.freeze_time(1.0, [(2.0, 1.5)]) == 1.0 and FX.freeze_time(2.7, [(2.0, 1.5)]) == 2.0 and abs(FX.freeze_time(4.0, [(2.0, 1.5)]) - 2.5) < 1e-9


def test_sway_layer_moves_the_top_not_the_bottom():
    tree = T.make_prop("matka", 200); a = FX.sway_layer(tree, 0.0, 0.08, 0.4); b = FX.sway_layer(tree, 0.6, 0.08, 0.4)
    top = lambda s: np.nonzero(s[:30, :, 3] > 20)[1].mean(); bot = lambda s: np.nonzero(s[-30:, :, 3] > 20)[1].mean()
    assert abs(top(a) - top(b)) > 3 and abs(bot(a) - bot(b)) < 1.0 + 0.2 * abs(top(a) - top(b))


def test_lightning_flashes_sometimes():
    vals = []
    for t in np.arange(0, 12, 0.1):
        f = BG.copy(); FX.apply(f, "lightning", float(t), rate=0.4, seed=1); vals.append(float(f.mean()))
    assert max(vals) > BG.mean() + 20 and min(vals) <= BG.mean() + 0.1


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))


def _mean_rgb(f): return f.reshape(-1, 3).mean(0)


def test_dawn_dusk_lamp_grades_look_right():
    for n in ("dawn_grade", "dusk_grade", "evening_lamp_grade"):
        assert n in FX.EFFECTS
        f = BG.copy(); out = FX.apply(f, n, 0.5); assert out.shape == BG.shape and out.dtype == np.uint8 and not np.array_equal(out, BG), n
        z = BG.copy(); FX.apply(z, n, 0.5, amount=0.0); assert np.abs(z.astype(int) - BG.astype(int)).mean() < 1.5, f"{n} amount=0 is (almost) a no-op"
        assert C.bench(lambda: FX.apply(BG.copy(), n, 0.5), 3) < 0.12, f"{n} is slower than 0.1 s"
    dawn = BG.copy(); FX.apply(dawn, "dawn_grade", 0); dusk = BG.copy(); FX.apply(dusk, "dusk_grade", 0)
    rb = lambda f: _mean_rgb(f)[0] / _mean_rgb(f)[2]
    assert rb(dawn) > rb(BG) * 1.1 and rb(dusk) > rb(dawn) * 1.15, "warm: dawn warmer than the day, dusk warmer than dawn"
    assert dusk.mean() < BG.mean() and dawn.std() < BG.std() * 1.02, "dusk is darker; dawn is soft (no more contrast than the original)"
    h = BG.shape[0]; assert _mean_rgb(dusk[int(h * .55):int(h * .62)])[0] > _mean_rgb(dusk[:int(h * .1)])[0] + 20, "horizon glows"


def test_lamp_grade_lights_around_the_lamps_and_flickers():
    lamps = [(0.25, 0.6, 200.0)]
    f = BG.copy(); FX.apply(f, "evening_lamp_grade", 0.7, lamps=lamps); H, W = BG.shape[:2]
    near = f[int(.6 * H) - 30:int(.6 * H) + 30, int(.25 * W) - 30:int(.25 * W) + 30].mean(); far = f[int(.6 * H) - 30:int(.6 * H) + 30, int(.9 * W) - 30:int(.9 * W) + 30].mean()
    assert near > far * 1.5 and f.mean() < BG.mean() * 0.85, (near, far)
    a = BG.copy(); b = BG.copy(); FX.apply(a, "evening_lamp_grade", 0.1, lamps=lamps); FX.apply(b, "evening_lamp_grade", 0.4, lamps=lamps); assert not np.array_equal(a, b), "flicker"
    assert np.array_equal(a, FX.apply(BG.copy(), "evening_lamp_grade", 0.1, lamps=lamps)), "deterministic"
    e = dict(effect="dusk_grade", start=0.0, dur=2.0, fade=0.5); mid = FX.run_event(BG.copy(), e, 1.0); start = FX.run_event(BG.copy(), e, 0.0)
    assert np.abs(start.astype(int) - BG.astype(int)).mean() < 1.5 and np.abs(mid.astype(int) - BG.astype(int)).mean() > 8, "event fades in softly"


def test_layered_flame_has_teardrop_layers_and_flickers():
    dark = np.full_like(BG, (24, 20, 30)); frames = []
    for i in range(12):
        f = dark.copy(); FX.apply(f, "flame", i / 24, pos=(0.5, 0.8), size=240, glow=0.0); frames.append(f)
    f = frames[0]; H, W = f.shape[:2]; cx, by = W // 2, int(0.8 * H)
    colour_at = lambda dy: f[by - dy, cx].astype(int)
    core, mid, base = colour_at(50), colour_at(115), colour_at(215)
    assert core.sum() > 600 and core[1] > 180, "pale-yellow core in the middle"                                               # R,G,B high -> yellow/white
    assert colour_at(10)[1] > colour_at(10)[2] and (np.abs(f.astype(int) - dark).sum(-1) > 60)[by - 230:by, :].any()
    outer = np.abs(f.astype(int) - dark).sum(-1) > 60; ys, xs = np.nonzero(outer); assert 130 < ys.max() - ys.min() < 260 and xs.max() - xs.min() < 170, "a teardrop, taller than wide"
    w_top = outer[by - int(0.85 * (ys.max() - ys.min())) - 5:by - int(0.85 * (ys.max() - ys.min())) + 5].sum(); w_low = outer[by - 40:by - 30].sum(); assert w_top < w_low * 0.6, "narrow tip, round belly"
    d = [np.abs(frames[i + 1].astype(int) - frames[i].astype(int)).sum() for i in range(11)]; assert min(d) > 0, "flickers every frame"
    assert np.array_equal(frames[3], (lambda g: (FX.apply(g, "flame", 3 / 24, pos=(0.5, 0.8), size=240, glow=0.0), g)[1])(dark.copy()))
