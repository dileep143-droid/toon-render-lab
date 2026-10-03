import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, transitions as TR

A = T.make_background("village_day"); B = T.make_background("village_night")
PARAMS = {"wipe": dict(direction="left"), "meanwhile": dict(text="Meanwhile...")}


def mad(x, y): return float(np.abs(x.astype(int) - y.astype(int)).mean())


def test_endpoints_are_exact():
    for n in TR.TRANSITIONS:
        assert np.array_equal(TR.transition(n, A, B, 0.0, **PARAMS.get(n, {})), A) or n == "meanwhile", n
        assert np.array_equal(TR.transition(n, A, B, 1.0, **PARAMS.get(n, {})), B), n


def test_shape_dtype_and_middle_differs():
    for n in TR.TRANSITIONS:
        m = TR.transition(n, A, B, 0.5, **PARAMS.get(n, {})); assert m.shape == A.shape and m.dtype == np.uint8, n
        if n != "cut": assert mad(m, A) > 1 and mad(m, B) > 1 or n in ("dip_black", "dip_white"), n


def test_progress_is_monotonic_for_the_blends():
    for n, kw in (("dissolve", {}), ("wipe", dict(direction="left")), ("wipe", dict(direction="down")), ("iris", dict(style="open")), ("star_wipe", {}), ("page_turn", {})):
        da = [mad(TR.transition(n, A, B, u, **kw), A) for u in np.linspace(0.05, 0.95, 10)]
        assert all(x2 >= x1 - 0.8 for x1, x2 in zip(da, da[1:])), (n, kw, [round(v, 1) for v in da])        # drifts steadily away from a


def test_no_pop_between_neighbouring_frames():
    for n in TR.TRANSITIONS:
        if n in ("cut",): continue
        prev = TR.transition(n, A, B, 0.01, **PARAMS.get(n, {})); worst = 0.0
        for i in range(2, 25):
            f = TR.transition(n, A, B, i / 25, **PARAMS.get(n, {})); worst = max(worst, mad(f, prev)); prev = f
        assert worst < 38, (n, worst)


def test_dips_reach_the_colour():
    assert TR.transition("dip_black", A, B, 0.5).max() == 0 and TR.transition("dip_white", A, B, 0.5).min() == 255


def test_wipe_directions_reveal_from_the_right_side():
    f = TR.transition("wipe", A, B, 0.5, direction="left", soft=0.05); left, right = f[:, :200], f[:, -200:]
    assert mad(right, B[:, -200:]) < mad(right, A[:, -200:]) and mad(left, A[:, :200]) < mad(left, B[:, :200])
    f = TR.transition("wipe", A, B, 0.5, direction="down", soft=0.05); assert mad(f[:150], B[:150]) < mad(f[:150], A[:150]) and mad(f[-150:], A[-150:]) < mad(f[-150:], B[-150:])          # the edge travels DOWN: b is already at the top


def test_iris_closes_to_black_in_the_middle():
    m = TR.transition("iris", A, B, 0.5, center=(0.5, 0.5)); assert m[:60, :60].max() == 0 and m[-60:, -60:].max() == 0
    assert TR.transition("iris", A, B, 0.2).mean() < A.mean()


def test_meanwhile_card_has_text():
    c = TR.transition("meanwhile", A, B, 0.5, text="इसी बीच..."); assert mad(c, A) > 20 and mad(c, B) > 20 and len(np.unique(c.reshape(-1, 3), axis=0)) > 100


def test_render_transition_generator_and_event():
    fr = list(TR.render_transition(lambda t: A, lambda t: B, "dissolve", 0.5, 24)); assert len(fr) == 13 and np.array_equal(fr[0], A) and np.array_equal(fr[-1], B)
    ev = {"transition": "wipe", "start": 2.0, "dur": 1.0, "direction": "right"}
    assert TR.run_event(A, B, ev, 1.0) is A and TR.run_event(A, B, ev, 3.5) is B and not np.array_equal(TR.run_event(A, B, ev, 2.5), A)


def test_unknown_transition_lists_names():
    try: TR.transition("nope", A, B, 0.5)
    except KeyError as e: assert "dissolve" in str(e)
    else: assert False


def test_speed_budget():
    for n in TR.TRANSITIONS:
        TR.transition(n, A, B, 0.45, **PARAMS.get(n, {}))
        assert C.bench(lambda: TR.transition(n, A, B, 0.45, **PARAMS.get(n, {})), 4) < 0.1, n


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))
