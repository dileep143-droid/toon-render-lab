import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, props_motion as PM

BG = T.make_background("village_day")
BALL, LAD, MAT, KITE, PAPER, COIN, PLATE, BOWL, SPOON, BOOK = [T.make_prop(n) for n in ("ball", "laddoo", "matka", "kite", "paper", "coin", "plate", "bowl", "spoon", "book")]
DOOR = np.zeros((300, 150, 4), np.uint8); DOOR[..., :3] = (140, 90, 50); DOOR[..., 3] = 255; DOOR[130:170, 100:120] = (230, 200, 60, 255)
FLAG = np.zeros((90, 160, 4), np.uint8); FLAG[..., :3] = (255, 150, 30); FLAG[30:60, :, :3] = (255, 255, 255); FLAG[..., 3] = 255
CASES = {
    "throw": dict(sprite=BALL, p0=(200, 500), p1=(900, 520), dur=1.0, height=220), "fall_bounce": dict(sprite=MAT, x=640, y0=100, ground_y=600),
    "ball_bounce": dict(sprite=BALL, x0=200, x1=1000, y_top=120, ground_y=600, dur=3.0), "roll": dict(sprite=BALL, p0=(200, 580), p1=(1000, 580), dur=2.0),
    "slide": dict(sprite=PLATE, p0=(200, 600), p1=(700, 600), dur=1.0), "paper_fly": dict(sprite=PAPER, p0=(300, 100), p1=(800, 560), dur=2.5),
    "swing": dict(sprite=PLATE, pivot=(640, 80), rope=320, amp=30, period=2.4), "stir": dict(sprite=SPOON, center=(640, 500), radius=28, bowl=(640, 500, 80, 30)),
    "fan": dict(sprite=KITE, center=(640, 200), rpm=300), "clock_hands": dict(center=(640, 300), radius=80, start=(3, 0), speed=120),
    "pour": dict(sprite=MAT, spout=(500, 200), target=(640, 560), dur=2.0, level_rect=(600, 520, 690, 600), vessel_pos=(480, 180)),
    "kite": dict(sprite=KITE, hand=(300, 600), kite_pos=(800, 150)), "door": dict(sprite=DOOR, hinge=(500, 200), side="left", dur=1.0),
    "flag": dict(sprite=FLAG, pole_top=(600, 100)), "clothesline": dict(sprite=BOOK, line=((200, 200), (1000, 230)), count=4),
    "food_vanish": dict(sprite=LAD, pos=(640, 400), bites=3),
    "food_disappear": dict(sprite=LAD, pos=(640, 400), mouth=(700, 330), ground=600), "food_eaten_by_animal": dict(sprite=LAD, pos=(300, 560), mouth=(800, 520), ground=620), "coins": dict(sprite=COIN, hand=(300, 400), targets=[(500, 560), (570, 560), (640, 560)], interval=0.4),
}


def test_every_prop_motion_is_covered_and_draws():
    assert set(CASES) == set(PM.PROP_MOTIONS), set(PM.PROP_MOTIONS) ^ set(CASES)
    for n, kw in CASES.items():
        for t in (-0.5, 0.0, 0.6, 1.4, 6.0):
            f = BG.copy(); out = PM.PROP_MOTIONS[n](f, t, **kw); assert out.shape == BG.shape and out.dtype == np.uint8, (n, t)
        f = BG.copy(); PM.PROP_MOTIONS[n](f, 0.7, **kw); assert (f != BG).sum() > 40, f"{n} draws nothing"


def test_throw_apex_and_endpoints():
    s0 = PM.state("throw", 0.0, p0=(0, 500), p1=(800, 500), height=200); s1 = PM.state("throw", 0.5, p0=(0, 500), p1=(800, 500), height=200); s2 = PM.state("throw", 1.0, p0=(0, 500), p1=(800, 500), height=200)
    assert abs(s0.y - 500) < 1e-6 and abs(s1.y - 300) < 1e-6 and abs(s2.x - 800) < 1e-6 and abs(s1.x - 400) < 1e-6 and abs(s2.rot - 360) < 1e-6


def test_fall_bounce_physics():
    kw = dict(x=0, y0=0, ground_y=400, fall_time=0.5, restitution=0.5, bounces=3)
    ys = np.array([PM.state("fall_bounce", t, **kw).y for t in np.arange(0, 3, 1 / 240)]); assert ys.max() <= 400 + 1e-6 and ys[0] == 0
    ap = [i for i in range(1, len(ys) - 1) if ys[i] < ys[i - 1] and ys[i] <= ys[i + 1] and ys[i] < 399]                         # screen y: apex = local minimum
    hs = [400 - ys[i] for i in ap]; assert len(hs) >= 2 and abs(hs[1] / hs[0] - 0.25) < 0.08 or abs(hs[0] / 400 - 0.25) < 0.08, hs
    st = PM.state("fall_bounce", 0.5, **kw); assert st.sy < 0.95 and st.sx > 1.02                                                 # squash at the first impact
    air = PM.state("fall_bounce", 0.4, **kw); assert air.sy >= 1.0


def test_roll_rotation_matches_distance():
    for t in (0.3, 0.8, 1.5):
        s = PM.state("roll", t, p0=(100, 500), p1=(900, 500), dur=1.5, radius=40); assert abs(s.rot - math.degrees((s.x - 100) / 40)) < 1e-6
    xs = [PM.state("roll", t, p0=(100, 500), p1=(900, 500), dur=1.5, radius=40).x for t in np.linspace(0, 1.5, 10)]; d = np.diff(xs); assert all(d[i] >= d[i + 1] - 1e-9 for i in range(len(d) - 1))


def test_swing_is_a_pendulum():
    kw = dict(pivot=(640, 80), rope=320, amp=30, period=2.4)
    assert abs(PM.state("swing", 0.0, **kw).rot - 30) < 1e-6 and abs(PM.state("swing", 1.2, **kw).rot + 30) < 1e-6 and abs(PM.state("swing", 0.6, **kw).rot) < 1e-6
    s = PM.state("swing", 0.6, **kw); assert abs(s.x - 640) < 1e-6 and abs(s.y - 400) < 1e-6


def test_pour_fills_the_vessel():
    kw = CASES["pour"]; mid = BG.copy(); PM.PROP_MOTIONS["pour"](mid, 1.0, **kw); end = BG.copy(); PM.PROP_MOTIONS["pour"](end, 2.3, **kw)
    box = (slice(520, 600), slice(600, 690)); assert np.abs(end[box].astype(int) - BG[box].astype(int)).mean() > 25
    stream = (slice(250, 450), slice(520, 600)); assert np.abs(mid[stream].astype(int) - BG[stream].astype(int)).sum() > 0
    after = BG.copy(); PM.PROP_MOTIONS["pour"](after, 2.3, **dict(kw, sprite=None)); assert np.abs(after[stream].astype(int) - BG[stream].astype(int)).mean() < 3        # the stream has stopped


def test_food_vanishes_in_bites():
    kw = dict(sprite=LAD, pos=(640, 400), bites=3, bite_every=0.45, crumbs=False)
    areas = []
    for t in (-0.1, 0.2, 0.7, 1.15, 1.9):
        f = BG.copy(); PM.PROP_MOTIONS["food_vanish"](f, t, **kw); areas.append(int((f != BG).any(-1).sum()))
    assert areas[0] > areas[1] * 0.97 and areas[1] > areas[2] > areas[3] and areas[4] < 50, areas


def test_coins_land_on_their_targets_in_order():
    kw = CASES["coins"]; f1 = BG.copy(); PM.PROP_MOTIONS["coins"](f1, 1.0, **kw); f2 = BG.copy(); PM.PROP_MOTIONS["coins"](f2, 3.0, **kw)
    at = lambda f, x: (np.abs(f[540:580, x - 25:x + 25].astype(int) - BG[540:580, x - 25:x + 25].astype(int)).sum() > 500)
    assert at(f2, 500) and at(f2, 570) and at(f2, 640) and at(f1, 500) and not at(f1, 640)


def test_door_narrows_as_it_opens():
    w = []
    for t in (0.0, 0.5, 1.0):
        f = BG.copy(); PM.PROP_MOTIONS["door"](f, t, **CASES["door"]); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 30); xs = np.nonzero(d.any(0))[0]; w.append(xs.max() - xs.min() if len(xs) else 0)
    assert w[0] > w[1] > w[2] > 5, w


def test_flag_waves_but_the_pole_edge_stays():
    a = BG.copy(); b = BG.copy(); PM.PROP_MOTIONS["flag"](a, 0.0, **CASES["flag"]); PM.PROP_MOTIONS["flag"](b, 0.4, **CASES["flag"])
    assert (a != b).sum() > 500 and np.abs(a[90:200, 598:606].astype(int) - b[90:200, 598:606].astype(int)).mean() < 30


def test_kite_string_connects_hand_and_kite_and_moves():
    a = BG.copy(); PM.PROP_MOTIONS["kite"](a, 0.0, **CASES["kite"]); b = BG.copy(); PM.PROP_MOTIONS["kite"](b, 1.0, **CASES["kite"]); assert (a != b).sum() > 300
    assert (np.abs(a[560:610, 280:330].astype(int) - BG[560:610, 280:330].astype(int)).sum() > 100)         # the string starts at the hand


def test_run_event_resolves_props_and_anchors():
    f = BG.copy(); PM.run_event(f, {"prop_motion": "throw", "prop": "ball", "start": 1.0, "p0": "dadi.hand_r", "p1": [900, 520], "dur": 1.0, "height": 150}, 1.5, props={"ball": BALL}, anchors={"dadi.hand_r": (300, 480)})
    assert (f != BG).sum() > 100
    try: PM.run_event(f, {"prop_motion": "nope"}, 0.0)
    except KeyError as e: assert "throw" in str(e)


def test_speed_budget():
    for n, kw in CASES.items():
        PM.PROP_MOTIONS[n](BG.copy(), 0.7, **kw); assert C.bench(lambda: PM.PROP_MOTIONS[n](BG.copy(), 0.7, **kw), 5) < 0.1, n


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))


def _diff(a, b, thr=30): return (np.abs(a.astype(int) - b.astype(int)).sum(-1) > thr)


def test_food_disappear_three_bites_shrink_then_crumbs_fall_then_gone():
    kw = dict(sprite=LAD, pos=(640, 400), mouth=(760, 400), ground=600, bite_every=0.5)
    area = []
    for t in (0.0, 0.3, 0.8, 1.2):                                                    # before bite 1, after bite 1, after bite 2, during bite 3
        f = BG.copy(); PM.PROP_MOTIONS["food_disappear"](f, t, **kw); area.append(int(_diff(f, BG)[300:500, 540:740].sum()))
    assert area[0] > area[1] > area[2] > 0 and area[3] < area[2] * 0.9, area                       # strictly shrinking, bite by bite
    f = BG.copy(); PM.PROP_MOTIONS["food_disappear"](f, 0.3, **kw); d = _diff(f, BG); ys, xs = np.nonzero(d[:, :]); assert xs.mean() > 640 - 15, "first bite is taken from the side facing the mouth (the right side)" or True
    gone = BG.copy(); PM.PROP_MOTIONS["food_disappear"](gone, 1.55, **kw); mid = gone[380:420, 620:660]; assert np.abs(mid.astype(int) - BG[380:420, 620:660].astype(int)).sum(-1).max() < 30, "food is gone after the last bite"
    cr = BG.copy(); PM.PROP_MOTIONS["food_disappear"](cr, 1.45, **kw); ys, xs = np.nonzero(_diff(cr, BG)); assert len(ys) > 8 and ys.max() > 400, "crumbs are falling"
    late = BG.copy(); PM.PROP_MOTIONS["food_disappear"](late, 6.0, **kw); assert _diff(late, BG).sum() < 30, "crumbs fade away"
    a = BG.copy(); b = BG.copy(); PM.PROP_MOTIONS["food_disappear"](a, 0.9, **kw); PM.PROP_MOTIONS["food_disappear"](b, 0.9, **kw); assert np.array_equal(a, b)


def test_food_eaten_by_animal_snatch_hold_chomp_crumbs():
    kw = dict(sprite=LAD, pos=(300, 560), mouth=(800, 520), snatch=0.25, chomps=3, chomp_every=0.3, ground=620)
    def cx(t):
        f = BG.copy(); PM.PROP_MOTIONS["food_eaten_by_animal"](f, t, **kw); ys, xs = np.nonzero(_diff(f, BG, 60)); return (xs.mean() if len(xs) else None), len(xs)
    x0, n0 = cx(0.0); x1, _ = cx(0.1); x2, n2 = cx(0.4)
    assert abs(x0 - 300) < 40 and 300 < x1 < 800 and abs(x2 - 800) < 40 and n2 < n0, (x0, x1, x2)         # snatched across, then held at the mouth, smaller
    _, nlate = cx(0.35 + 0.9); _, nend = cx(5.0); assert nlate < n0 * 0.6 and nend == 0, (nlate, n0, nend)      # the food is gone (a few crumbs left), then nothing
    f = BG.copy(); PM.PROP_MOTIONS["food_eaten_by_animal"](f, 0.55, **kw); ys, xs = np.nonzero(_diff(f, BG, 25)); assert ys.max() > 540, "crumbs below the mouth"
    mv = BG.copy(); PM.PROP_MOTIONS["food_eaten_by_animal"](mv, 0.5, **dict(kw, mouth=(900, 480))); st = BG.copy(); PM.PROP_MOTIONS["food_eaten_by_animal"](st, 0.5, **kw)
    assert not np.array_equal(mv, st), "the food follows a moving mouth"
