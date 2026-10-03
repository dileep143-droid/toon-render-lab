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
