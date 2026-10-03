import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from scipy import ndimage as ndi
import tk_core as C, testart as T, puppet as PU

KINDS = ("man", "kid", "dadi")


def _rig(kind): return T.make_human(kind)


def test_rest_pose_reproduces_the_image():
    for k in KINDS:
        img, rig = _rig(k); pup = PU.get_puppet(img, rig); pad = pup.pad
        spr, _ = pup.render(PU.Pose()); rec = spr[pad:pad + img.shape[0], pad:pad + img.shape[1]]
        bg = np.full(img.shape[:2] + (3,), 255, np.uint8); a = bg.copy(); b = bg.copy(); C.alpha_over(a, img, 0, 0); C.alpha_over(b, rec, 0, 0)
        assert (np.abs(a.astype(int) - b.astype(int)).sum(-1) > 60).sum() < 400, k       # < 0.1 % of the pixels differ visibly


def test_every_motion_renders_connected_no_tearing():
    for k in KINDS:
        img, rig = _rig(k)
        for name in sorted(PU.MOTIONS):
            for t in (0.2, 0.6, 1.1):
                sp = PU.animate(img, rig, name, t, dict(dur=1.5, speed=250))
                al = sp[..., 3] > 40; lab, n = ndi.label(al); sizes = ndi.sum(al, lab, range(1, n + 1))
                main = sizes.max(); rest = sizes.sum() - main
                assert rest < 0.012 * main, f"{k}/{name}@{t}: {n} fragments, stray area {rest:.0f} of {main:.0f}"
                assert main > 20000


def test_deterministic_and_pure_in_time():
    img, rig = _rig("man")
    a = PU.animate(img, rig, "wave", 0.7, dict(dur=1.5)); PU.animate(img, rig, "jump", 0.3, dict(dur=1.4)); b = PU.animate(img, rig, "wave", 0.7, dict(dur=1.5))
    assert np.array_equal(a, b)


def test_motions_start_and_end_at_rest():
    img, rig = _rig("man"); base = PU.animate(img, rig, "idle_breathe", 0.0)
    for name in ("wave", "nod", "head_shake", "namaste", "think", "clap", "shrug", "point", "scratch_head", "hand_to_mouth"):
        for t in (0.0, 1.5):
            sp = PU.animate(img, rig, name, t, dict(dur=1.5)); d = np.abs(sp[..., 3].astype(int) - base[..., 3].astype(int)).sum() / 255.0
            assert d < 4000, f"{name}@{t} does not start/end at rest (alpha diff {d:.0f} px)"      # nothing pops at the edges


def test_walk_travel_matches_distance():
    img, rig = _rig("man")
    _, info = PU.animate(img, rig, "walk_cycle", 2.0, dict(dur=2.0, distance=500), return_info=True)
    assert abs(info["travel"] - 500) < 5
    ev = [dict(motion="walk_cycle", start=0, dur=2.0, distance=500)]; P = PU.Performer(img, rig, ev)
    assert abs(P.frame(5.0)[1]["travel"] - 500) < 5          # a finished walk keeps its distance, but its legs stop


def test_anchors_follow_the_hand():
    img, rig = _rig("man"); h0 = PU.hand_point(rig, 0.0, "wave", dict(dur=1.5), side="r", char_img=img); h1 = PU.hand_point(rig, 0.75, "wave", dict(dur=1.5), side="r", char_img=img)
    assert h1[1] < h0[1] - 200, (h0, h1)                       # the waving hand is well above its rest position


def test_no_legs_rig_walks():
    img, rig = _rig("dadi"); assert not rig["has_legs"]
    sp = PU.animate(img, rig, "walk_cycle", 0.4, dict(dur=3, speed=150)); assert sp[..., 3].max() == 255


def test_speed_budget():
    img, rig = _rig("man"); PU.animate(img, rig, "wave", 0.5)
    for name in ("wave", "walk_cycle", "jump"):
        s = C.bench(lambda: PU.animate(img, rig, name, 0.6, dict(dur=1.5, speed=250)), 6)
        assert s < 0.1, (name, s)


def test_rigid_fallback():
    img, rig = _rig("man"); pup = PU.Puppet(C.as_rgba(img), PU.human_spec(rig), mesh=False)
    pose = PU.pose_for(rig, [("namaste", 0.7, dict(dur=1.5))], 0.7); sp, _ = pup.render(pose); assert sp[..., 3].max() == 255


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))


NEW_DANCES = ("clap_dance", "hop_dance", "garba_turn_clap")
NEW_FALLS = ("fall_slip_peel", "fall_trip_forward", "fall_sit_bump")


def _sprite_bbox(img, rig, motion, t, params=None):
    spr, info = PU.animate(img, rig, motion, t, params or {}, return_info=True); ys, xs = np.nonzero(spr[..., 3] > 40); return spr, (xs.min(), ys.min(), xs.max(), ys.max()), info


def test_new_dances_loop_move_and_stay_smooth():
    img, rig = _rig("man")
    for n in NEW_DANCES:
        assert n in PU.MOTIONS and PU.MOTIONS[n].loop, n
        seq = [PU.animate(img, rig, n, t, {"dur": 4.0}) for t in np.linspace(0.0, 1.5, 37)]
        ch = [np.abs(seq[i + 1][..., 3].astype(int) - seq[i][..., 3].astype(int)).sum() for i in range(len(seq) - 1)]
        assert max(ch) > 0 and sum(ch) > 6000, f"{n} does not move"
        assert max(ch) < 14 * (np.median(ch) + 2000), f"{n} pops"                                                       # no single frame jumps far above the usual step
    spr0 = PU.animate(img, rig, "garba_turn_clap", 0.0, {"dur": 8.0}); widths = []
    for t in np.linspace(0.0, 2.0, 49):
        s = PU.animate(img, rig, "garba_turn_clap", t, {"dur": 8.0}); xs = np.nonzero(s[..., 3].max(0) > 40)[0]; widths.append(xs.max() - xs.min())
    assert min(widths) < 0.8 * max(widths), (min(widths), max(widths))
    h = [_sprite_bbox(img, rig, "hop_dance", t, {"dur": 6.0})[1][1] for t in np.linspace(0, 1.4, 29)]; assert max(h) - min(h) > 8, "hop_dance leaves the ground"
    # the dances fade in and out with the event: the pose at t=0 is the rest pose (same as a motion that has not started moving)
    for n in NEW_DANCES:
        a = PU.animate(img, rig, n, 0.0, {"dur": 3.0}); b = PU.animate(img, rig, "nod", 0.0, {"dur": 3.0}); assert np.abs(a[..., 3].astype(int) - b[..., 3].astype(int)).sum() < 4000, n


def test_fall_variants_end_lying_or_seated_and_hold():
    img, rig = _rig("man"); H = rig["size"][1]
    for n in NEW_FALLS:
        assert n in PU.MOTIONS and PU.MOTIONS[n].hold, n
        s_end, bb, info = _sprite_bbox(img, rig, n, 1.5, {"dur": 1.5}); s_hold, bb2, _ = _sprite_bbox(img, rig, n, 4.0, {"dur": 1.5}); assert bb == bb2, f"{n} holds its last pose"
    # slip: flat on the back (wider than tall); trip: flat forward; sit-bump: lower and about as wide as it is tall
    w = lambda bb: bb[2] - bb[0]; h = lambda bb: bb[3] - bb[1]
    _, bs, _ = _sprite_bbox(img, rig, "fall_slip_peel", 1.5, {"dur": 1.5}); _, bt, _ = _sprite_bbox(img, rig, "fall_trip_forward", 1.5, {"dur": 1.5}); _, bq, _ = _sprite_bbox(img, rig, "fall_sit_bump", 1.5, {"dur": 1.5}); _, b0, _ = _sprite_bbox(img, rig, "idle_breathe", 0.0)
    assert w(bs) > h(bs) * 1.1 and w(bt) > h(bt) * 0.8 and h(bt) < h(b0) * 0.85 and h(bq) < h(b0) * 0.92 and w(bq) > w(b0) * 0.9, (bs, bt, bq, b0)
    assert PU.animate(img, rig, "fall_trip_forward", 0.0, {"dur": 1.5}, return_info=True)[1]["travel"] == 0 and PU.animate(img, rig, "fall_trip_forward", 1.5, {"dur": 1.5}, return_info=True)[1]["travel"] > 0.1 * H * 0.9, "trip pitches forward in the walking direction"
    # slip is airborne mid-way (feet above the ground line)
    _, air, _ = _sprite_bbox(img, rig, "fall_slip_peel", 0.3, {"dur": 1.5}); _, ground, _ = _sprite_bbox(img, rig, "fall_slip_peel", 1.5, {"dur": 1.5}); assert air[3] < ground[3] - 15, (air, ground)
    ctr = lambda bb: (bb[1] + bb[3]) / 2
    for n in NEW_FALLS:                                                                                                       # no frame-to-frame jump of the centre bigger than ~1/5 of the body
        cs = [ctr(_sprite_bbox(img, rig, n, t, {"dur": 1.5})[1]) for t in np.linspace(0, 1.5, 37)]; assert np.abs(np.diff(cs)).max() < 0.2 * H, n
