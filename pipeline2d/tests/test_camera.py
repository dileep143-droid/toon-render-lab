import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, camera as CM
from camera import Cam

PLATE = np.asarray(__import__("PIL.Image", fromlist=["Image"]).fromarray(T.make_background("village_day")).resize((2560, 1440)))


def test_ken_burns_endpoints_and_geometric_zoom():
    m = CM.ken_burns(Cam(0.3, 0.5, 1.0), Cam(0.7, 0.5, 2.0), 4.0, "linear"); assert m.at(0).z == 1.0 and abs(m.at(4).z - 2.0) < 1e-9
    assert abs(m.at(2).z - math.sqrt(2)) < 1e-6 and abs(m.at(2).cx - 0.5) < 1e-9


def test_moves_are_smooth_no_pops():
    for m in (CM.ken_burns(Cam(), Cam(0.6, 0.4, 1.8), 3.0), CM.push_in(Cam(), (0.7, 0.5), 1.5, 2.0), CM.pull_out(Cam(0.3, 0.4, 2.5), None, 2.0)):
        prev = m.at(0); steps = []
        for t in np.arange(1, 25 * m.dur + 1) / 24:
            c = m.at(t); steps.append(abs(c.cx - prev.cx) + abs(c.cy - prev.cy) + abs(c.z - prev.z)); prev = c
        assert max(steps) < 0.12, (m.name, max(steps))
        assert steps[0] < max(steps) * 0.8 or len(steps) < 5          # eases in


def test_whip_pan_fast_with_blur():
    m = CM.whip_pan(Cam(0.2, 0.5, 1.2), Cam(0.8, 0.5, 1.2), 0.4); assert m.at(0).blur < 1 and m.at(0.4).blur < 2
    assert max(m.at(t).blur for t in np.linspace(0, 0.4, 20)) > 5
    mid = m.at(0.2).cx; assert 0.3 < mid < 0.7
    u1, u2 = m.at(0.12).cx, m.at(0.28).cx; assert (u2 - u1) > 0.35 * 0.6         # most of the travel happens in the middle


def test_track_chains_and_is_continuous():
    ev = [{"camera": "ken_burns", "start": 0, "dur": 2, "to": [0.6, 0.5, 1.5]}, {"camera": "push_in", "start": 2.5, "dur": 1.5, "target": [0.3, 0.5], "amount": 1.3},
          {"camera": "pull_out", "start": 5, "dur": 1.0}]
    tr = CM.CameraTrack.from_events(ev, start=[0.5, 0.5, 1.0]); a = tr.at(2.4); b = tr.at(2.5); assert abs(a.z - b.z) < 1e-9 and abs(a.cx - b.cx) < 1e-9
    assert abs(tr.at(10).z - 1.0) < 1e-9 and tr.at(0).z == 1.0
    ts = np.arange(0, 7, 1 / 24); zs = [tr.at(t).z for t in ts]; assert max(abs(np.diff(zs))) < 0.1


def test_follow_lags_then_settles():
    path = [[0, 0.2, 0.5], [3, 0.8, 0.5], [5, 0.8, 0.5]]; m = CM.follow(path, zoom=1.5, lag=0.4)
    assert m.at(1.5).cx < 0.5 + 0.0 + 0.01 and m.at(1.5).cx > 0.25 and abs(m.at(5).cx - (0.8 - 0.0)) < 0.2
    xs = [m.at(t).cx for t in np.arange(0, 5, 1 / 24)]; assert max(abs(np.diff(xs))) < 0.03


def test_two_shot_contains_both():
    m = CM.two_shot(Cam(), (0.3, 0.55), (0.62, 0.55), 1.0); c = m.end; x0, y0, x1, y1 = c.box()
    assert x0 < 0.3 < x1 and x0 < 0.62 < x1 and c.z > 1.2


def test_render_view_matches_plate_and_zoom():
    f = CM.render_view(PLATE, Cam()); ref = np.asarray(__import__("PIL.Image", fromlist=["Image"]).fromarray(PLATE).resize((1280, 720)))
    assert np.abs(f.astype(int) - ref.astype(int)).mean() < 3
    z = CM.render_view(PLATE, Cam(0.5, 0.5, 2.0)); crop = PLATE[360:1080, 640:1920]; ref2 = np.asarray(__import__("PIL.Image", fromlist=["Image"]).fromarray(crop).resize((1280, 720)))
    assert np.abs(z.astype(int) - ref2.astype(int)).mean() < 4


def test_to_screen_matches_render():
    p = PLATE.copy(); p[700:716, 1500:1516] = (255, 0, 255)
    for cam in (Cam(), Cam(0.62, 0.5, 1.7), Cam(0.6, 0.55, 1.3, 6.0)):
        f = CM.render_view(p, cam); sx, sy, _ = CM.to_screen(cam, 1508 / 2560, 708 / 1440, (2560, 1440))
        if 5 < sx < 1275 and 5 < sy < 715:
            sub = f[int(sy) - 6:int(sy) + 7, int(sx) - 6:int(sx) + 7].astype(int); assert ((sub[..., 0] > 200) & (sub[..., 1] < 90)).sum() > 3, (cam, sx, sy)


def test_parallax_and_focus():
    L = T.make_scene_layers((2560, 1440)) if False else None
    far = np.zeros((1440, 2560, 3), np.uint8); far[:, 1200:1260] = (255, 0, 0); near = np.zeros((1440, 2560, 4), np.uint8); near[:, 1200:1260] = (0, 255, 0, 255)
    layers = [{"img": far, "depth": 0.3}, {"img": near, "depth": 1.4}]
    a = CM.render_view(layers, Cam(0.5, 0.5, 1.0)); b = CM.render_view(layers, Cam(0.6, 0.5, 1.0))
    mx = lambda f, ch: np.nonzero(f[:, :, ch] > 200)[1].mean() if (f[:, :, ch] > 200).any() else None
    dfar = None
    ra, rb = a[360, :, 0] > 200, b[360, :, 0] > 200
    if ra.any() and rb.any(): dfar = abs(np.nonzero(rb)[0].mean() - np.nonzero(ra)[0].mean())
    ga, gb = a[360, :, 1] > 200, b[360, :, 1] > 200; dnear = abs(np.nonzero(gb)[0].mean() - np.nonzero(ga)[0].mean()) if ga.any() and gb.any() else None
    assert dnear is not None and (dfar is None or dnear > 2.5 * dfar), (dfar, dnear)
    sharp = CM.render_view(layers, Cam(), focus=1.4); soft = CM.render_view(layers, Cam(), focus=0.3)
    edge = lambda f: np.abs(np.diff(f[360, :, 1].astype(int))).max(); assert edge(sharp) > edge(soft) + 30


ACTORS = [{"x": 0.3, "foot_y": 0.92, "height": 0.62}, {"x": 0.65, "foot_y": 0.9, "height": 0.5}]


def test_framing_rules_on_solved_shots():
    for st in ("wide", "full", "medium", "two_shot"):
        c = CM.solve_framing(st, ACTORS); assert CM.check_framing(c, ACTORS, st) == [], (st, CM.check_framing(c, ACTORS, st), c)
    c = CM.solve_framing("close", ACTORS, speaker=0); x0, y0, x1, y1 = c.box(); fb = CM._face(ACTORS[0])
    assert (fb[3] - fb[1]) / (y1 - y0) >= 0.25 - 1e-6 and fb[1] - y0 >= 0.05 * (y1 - y0) - 1e-9


def test_framing_catches_and_fixes_violations():
    bad = Cam(0.3, 0.7, 1.6)          # heads cut at the top, shins cut at the bottom
    v = CM.check_framing(bad, ACTORS[:1], "full"); assert v
    fixed, fx = CM.fix_framing(bad, ACTORS[:1], "full"); assert CM.check_framing(fixed, ACTORS[:1], "full") == [] and fx
    small = Cam(0.3, 0.4, 1.0); assert any(s.startswith("face_small") for s in CM.check_framing(small, ACTORS, "close", 0))


def test_dutch_hides_corners():
    f = CM.render_view(PLATE, Cam(0.5, 0.5, 1.0, 10.0)); assert (f.sum(-1) == 0).sum() == 0


def test_speed_budget():
    layers = [{"img": PLATE, "depth": 0.5}, {"img": np.dstack([PLATE, np.full(PLATE.shape[:2], 255, np.uint8)]), "depth": 1.0}]
    assert C.bench(lambda: CM.render_view(PLATE, Cam(0.5, 0.5, 1.4)), 5) < 0.1
    assert C.bench(lambda: CM.render_view(layers, Cam(0.55, 0.5, 1.4), focus=1.0), 4) < 0.14


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))


def _bg(): return T.make_background("village_day")


def test_split_depth_layers_makes_sky_far_near():
    bg = _bg(); L = CM.split_depth_layers(bg); H, W = bg.shape[:2]
    assert [l["name"] for l in L] == ["sky", "far", "near"] and [l["depth"] for l in L] == [0.2, 0.6, 1.0] and L[0]["img"].shape == (H, W, 3) and L[1]["img"].shape == (H, W, 4) and L[2]["img"].shape == (H, W, 4)
    far_a, near_a = L[1]["img"][..., 3] / 255.0, L[2]["img"][..., 3] / 255.0
    assert far_a[:int(H * .2)].mean() < 0.02 and near_a[:int(H * .5)].mean() < 0.01, "sky region is only in the sky layer"
    assert far_a[int(H * .6):int(H * .72), 100:1200].mean() > 0.9, "hills and houses are far"
    assert near_a[int(H * .9):, :].mean() > 0.95 and near_a[int(H * .6):int(H * .66), 100:1200].mean() < 0.5, "the foreground ground is near"
    x0 = 900; hs = L[1]["img"][int(H * .4):int(H * .6), x0:x0 + 230, 3]; assert hs.min() > 200 or hs.mean() > 150, "a house is not sliced"
    # flattening the three layers reproduces the picture
    out = CM.render_view(L, Cam(), (W, H)); assert np.abs(out.astype(int) - bg.astype(int)).sum(-1).mean() < 6
    assert CM.split_depth_layers(bg) is L, "cached"
    assert C.bench(lambda: CM.split_depth_layers(bg.copy(), grad_thr=14.0), 2) < 0.4


def test_parallax_from_a_single_background_moves_layers_differently():
    bg = _bg(); a = CM.render_view(bg, Cam(0.45, 0.5, 1.5), parallax=True); b = CM.render_view(bg, Cam(0.55, 0.5, 1.5), parallax=True)
    def lag(f, g, rows):                                                                           # horizontal shift (px) of the picture content in a band of rows between two frames
        p = f[rows].astype(float).mean((0, 2)); q = g[rows].astype(float).mean((0, 2)); p -= p.mean(); q -= q.mean()
        cc = np.correlate(p, q, "full"); return abs(int(np.argmax(cc)) - (len(p) - 1))
    sky_band, far_band, near_band = slice(5, 60), slice(330, 420), slice(660, 700)
    ls, lf, ln = lag(a, b, sky_band), lag(a, b, far_band), lag(a, b, near_band)
    assert ln > lf > ls or (ln > lf and lf >= ls), f"near moves more than far, far more than sky: {ln} {lf} {ls}"
    assert not np.array_equal(a, b) and a.shape == (720, 1280, 3) and a.min() >= 0
    # no black borders even when panning to the edge with layers at other depths
    e = CM.render_view(bg, Cam(0.8, 0.5, 1.5), parallax=True); assert e[:, -4:].mean() > 20 and e[:, :4].mean() > 20 and e[-4:].mean() > 20
    assert C.bench(lambda: CM.render_view(bg, Cam(0.55, 0.5, 1.5), parallax=True), 3) < 0.25


def test_focus_pull_blurs_by_layer_depth():
    bg = _bg(); sharp = lambda f: np.abs(np.diff(f.astype(int), axis=1)).sum(-1)
    near_f = CM.render_view(bg, Cam(0.5, 0.5, 1.2, focus=1.0, focus_amount=10), parallax=True); sky_f = CM.render_view(bg, Cam(0.5, 0.5, 1.2, focus=0.2, focus_amount=10), parallax=True)
    top = slice(40, 200); bot = slice(560, 700)                                    # sky (far depth 0.2) vs ground (near, depth 1)
    assert sharp(sky_f)[:, 100:1200].max() >= 0 and sharp(near_f)[bot].max() > sharp(sky_f)[bot].max() * 1.3, "ground crisp when near is in focus, soft when sky is"
    assert np.abs(near_f.astype(int) - sky_f.astype(int)).mean() > 0.3
    mv = CM.focus_pull(Cam(0.5, 0.5, 1.2), "far", 2.0, from_focus="near", amount=8); assert abs(mv.at(0).focus - 1.0) < 1e-9 and abs(mv.at(2.0).focus - 0.6) < 1e-9 and 0.6 < mv.at(1.0).focus < 1.0 and mv.at(1.0).cx == 0.5
    tr = CM.CameraTrack.from_events([{"camera": "push_in", "start": 0, "dur": 2, "target": [0.6, 0.5], "amount": 1.3}, {"camera": "focus_pull", "start": 2, "dur": 1, "to": "sky", "from_focus": "near"}])
    assert tr.at(0.0).focus is None and abs(tr.at(2.0).focus - 1.0) < 1e-6 and abs(tr.at(3.0).focus - 0.2) < 1e-6 and abs(tr.at(3.0).z - tr.at(2.0).z) < 1e-9
    f = [tr.at(2 + i / 24).focus for i in range(25)]; assert all(f[i + 1] <= f[i] + 1e-9 for i in range(24)) and np.abs(np.diff(f)).max() < 0.12, "smooth rack"
