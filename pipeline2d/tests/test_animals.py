import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from scipy import ndimage as ndi
import tk_core as C, testart as T, animals as AN, puppet as PU


def _frag(sp):
    al = sp[..., 3] > 40; lab, n = ndi.label(al); sizes = ndi.sum(al, lab, range(1, n + 1)); return sizes.max(), sizes.sum() - sizes.max()


def test_all_quadruped_motions_connected():
    for kind in T.QUAD:
        img, rig = T.make_quadruped(kind)
        for name in sorted(AN.AM):
            for t in (0.25, 0.9):
                main, rest = _frag(AN.animate_animal(img, rig, name, t, dict(dur=1.5, speed=250)))
                assert rest < 0.015 * main, (kind, name, t, rest, main)


def test_birds_and_monkey():
    for kind in ("hen", "parrot"):
        img, rig = T.make_bird(kind)
        for name in sorted(AN.BM):
            main, rest = _frag(AN.animate_animal(img, rig, name, 0.3, dict(dur=1.5, speed=250))); assert rest < 0.02 * main, (kind, name)
    img, rig = T.make_monkey()
    for name in ("swing", "monkey_jump", "walk_cycle", "wave"):
        main, rest = _frag(AN.animate_animal(img, rig, name, 0.4, dict(dur=1.5))); assert rest < 0.02 * main, name


def test_gait_distance_and_cadence():
    img, rig = T.make_quadruped("goat")
    _, info = AN.animate_animal(img, rig, "walk", 3.0, dict(dur=3.0, distance=600), return_info=True); assert abs(info["travel"] - 600) < 5
    _, i1 = AN.animate_animal(img, rig, "run", 1.0, dict(dur=3.0, speed=900), return_info=True)
    _, i2 = AN.animate_animal(img, rig, "walk", 1.0, dict(dur=3.0, speed=200), return_info=True)
    assert i1["travel"] > 3 * i2["travel"]


def test_mouth_overlay_only_when_open():
    img, rig = T.make_quadruped("dog"); closed = AN.animate_animal(img, rig, "bark", 0.0, dict(dur=1)); op = AN.animate_animal(img, rig, "bark", 0.17, dict(dur=1))
    assert (np.abs(closed.astype(int) - op.astype(int)).sum(-1) > 60).sum() > 100
    _, info = AN.animate_animal(img, rig, "bark", 0.17, dict(dur=1), return_info=True); assert info["pose"].tags["mouth"] > 0.2


def test_tags_for_effects():
    img, rig = T.make_quadruped("dog")
    _, i = AN.animate_animal(img, rig, "sleep", 1.0, dict(dur=3), return_info=True); assert i["pose"].tags.get("zzz")
    _, i = AN.animate_animal(img, rig, "steal_and_run", 1.0, dict(dur=3, speed=300), return_info=True); assert i["pose"].tags.get("carry") == "mouth"
    assert "mouth" in i["anchors"]


def test_flip_mirrors():
    img, rig = T.make_quadruped("cow"); a = AN.animate_animal(img, rig, "idle", 0.3); b = AN.animate_animal(img, rig, "idle", 0.3, flip=True)
    assert np.array_equal(a[:, ::-1], b)


def test_speed_budget():
    for kind in ("goat", "dog"):
        img, rig = T.make_quadruped(kind); AN.animate_animal(img, rig, "run", 0.3, dict(dur=3, speed=500))
        assert C.bench(lambda: AN.animate_animal(img, rig, "run", 0.3, dict(dur=3, speed=500)), 6) < 0.1


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))
