import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, scene_life as SL

BG = T.make_background("village_day")
CASES = {"birds": {}, "villagers": {}, "cattle": {}, "smoke": {}, "tree_sway": dict(sprite=T.make_prop("matka", 200)), "water_wheel": {}, "cycle": dict(dur=4.0), "crowd": {}}


def test_every_life_element_draws_and_is_covered():
    assert set(CASES) == set(SL.LIFE), set(CASES) ^ set(SL.LIFE)
    for n, kw in CASES.items():
        f = BG.copy(); SL.LIFE[n](f, 1.3, **kw); assert f.shape == BG.shape and (f != BG).sum() > 100, n


def test_stateless_and_seeded():
    for n, kw in CASES.items():
        a = BG.copy(); SL.LIFE[n](a, 2.2, **kw); SL.LIFE[n](BG.copy(), 0.4, **kw); b = BG.copy(); SL.LIFE[n](b, 2.2, **kw); assert np.array_equal(a, b), n
    a = BG.copy(); SL.birds(a, 1.0, seed=1); b = BG.copy(); SL.birds(b, 1.0, seed=2); assert not np.array_equal(a, b)


def test_birds_move_across_and_flap():
    xs = []
    for t in (0.0, 1.0, 2.0):
        f = BG.copy(); SL.birds(f, t, count=1, y=(0.1, 0.1), speed=100); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 60); xs.append(np.nonzero(d.any(0))[0].mean())
    assert 80 < xs[1] - xs[0] < 120 and 80 < xs[2] - xs[1] < 120
    f1 = BG.copy(); f2 = BG.copy(); SL.birds(f1, 0.0, count=1, speed=0); SL.birds(f2, 0.15, count=1, speed=0); assert (f1 != f2).sum() > 20          # wings move even when the bird stands still


def test_villagers_walk_at_depth_dependent_speed_in_both_directions():
    f0 = BG.copy(); f1 = BG.copy(); SL.villagers(f0, 0.0, count=6, speed=40); SL.villagers(f1, 2.0, count=6, speed=40)
    d0 = (np.abs(f0.astype(int) - BG.astype(int)).sum(-1) > 40); d1 = (np.abs(f1.astype(int) - BG.astype(int)).sum(-1) > 40); assert d0.sum() > 500 and not np.array_equal(d0, d1)


def test_cattle_head_goes_down_and_up():
    base = BG.copy(); SL.cattle(base, 0.0, count=1, size=140); frames = []
    for t in np.arange(0, 6, 0.25):
        f = BG.copy(); SL.cattle(f, float(t), count=1, size=140); frames.append(f)
    d = (np.abs(base.astype(int) - BG.astype(int)).sum(-1) > 60); ys, xs = np.nonzero(d); head_zone = (slice(ys.min(), ys.max()), slice(int(xs.min() + 0.62 * (xs.max() - xs.min())), xs.max() + 40))       # the front of the cow
    changes = [int((np.abs(fr[head_zone].astype(int) - base[head_zone].astype(int)).sum(-1) > 60).sum()) for fr in frames]
    assert max(changes) > 400 and min(changes) < 0.3 * max(changes), (min(changes), max(changes))       # the head leaves its place and comes back


def test_cycle_crosses_the_frame_once():
    pos = []
    for t in (0.8, 1.5, 2.2, 3.0):
        f = BG.copy(); SL.cycle(f, t, dur=4.0, size=170); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 60); pos.append(np.nonzero(d.any(0))[0].mean() if d.any() else None)
    assert pos[0] < pos[1] < pos[2] < pos[3]
    f = BG.copy(); SL.cycle(f, 5.0, dur=4.0); assert np.array_equal(f, BG)                         # gone after it has passed
    f = BG.copy(); SL.cycle(f, 1.5, dur=4.0, direction=-1); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 60); assert np.nonzero(d.any(0))[0].mean() > 640 - 400


def test_crowd_back_rows_are_smaller():
    f = BG.copy(); SL.crowd(f, 0.5, region=(0.1, 0.5, 0.9, 0.95), count=80); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 40); top, bot = d[360:450].sum(), d[560:680].sum(); assert bot > top


def test_ambient_presets_and_events():
    for p in SL.LIFE_PRESETS:
        f = BG.copy(); SL.ambient(f, 1.0, p); assert (f != BG).sum() > 500, p
    f = BG.copy(); SL.run_event(f, {"life": "birds", "start": 1.0, "dur": 2.0, "count": 4}, 0.5); assert np.array_equal(f, BG)
    f = BG.copy(); SL.run_event(f, {"life": "birds", "start": 1.0, "dur": 2.0, "count": 4}, 1.5); assert (f != BG).sum() > 100
    f = BG.copy(); SL.run_event(f, {"ambient": "mela"}, 1.0); assert (f != BG).sum() > 500


def test_speed_budget():
    for n, kw in CASES.items():
        SL.LIFE[n](BG.copy(), 0.3, **kw); assert C.bench(lambda: SL.LIFE[n](BG.copy(), 1.3, **kw), 5) < 0.1, n
    for p in SL.LIFE_PRESETS:
        SL.ambient(BG.copy(), 0.3, p); assert C.bench(lambda: SL.ambient(BG.copy(), 1.3, p), 4) < 0.1, p


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))
