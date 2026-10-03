"""make_demos.py - renders one short demo MP4 per toolkit module with SYNTHETIC art (no external images).
   python demos/make_demos.py [puppet animals effects camera transitions props scene_life audio titles qa all]"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import numpy as np
import tk_core as C, testart as T
OUT = HERE


def bg_frame(kind="village_day"):
    return T.make_background(kind)


def demo_puppet():
    import puppet as PU
    man, rman = T.make_human("man"); kid, rkid = T.make_human("kid"); dadi, rdadi = T.make_human("dadi")
    bg = bg_frame(); fps = C.FPS; dur = 9.0; frames = []
    ev_man = [dict(motion="walk_cycle", start=0.0, dur=2.6, speed=300), dict(motion="wave", start=2.8, dur=1.6), dict(motion="nod", start=4.6, dur=1.0),
              dict(motion="think", start=5.8, dur=1.6), dict(motion="jump", start=7.5, dur=1.3)]
    ev_kid = [dict(motion="run_cycle", start=0.2, dur=2.4, speed=420), dict(motion="clap", start=3.0, dur=1.8), dict(motion="laugh_bounce", start=5.0, dur=2.0), dict(motion="hand_to_mouth", start=7.2, dur=1.6)]
    ev_dadi = [dict(motion="namaste", start=1.0, dur=2.0), dict(motion="point", start=3.6, dur=1.5), dict(motion="shrug", start=5.6, dur=1.2), dict(motion="head_shake", start=7.2, dur=1.4)]
    pm, pk, pd = PU.Performer(man, rman, ev_man), PU.Performer(kid, rkid, ev_kid), PU.Performer(dadi, rdadi, ev_dadi)
    for i in range(int(dur * fps)):
        t = i / fps; f = bg.copy()
        for perf, rig, x0, y, hpx, face in ((pd, rdadi, 1010, 600, 330, True), (pm, rman, 120, 620, 400, False), (pk, rkid, 70, 690, 300, False)):
            sp, info = perf.frame(t, flip=face)
            k = hpx / rig["size"][1]; x = x0 + (-1 if face else 1) * info["travel"] * k
            PU.draw_character(f, sp, info, rig, x, y, hpx, flip=face)
        frames.append(f)
    return C.write_video(frames, os.path.join(OUT, "puppet.mp4"), fps, crf=28)


DEMOS = {"puppet": demo_puppet}
if __name__ == "__main__":
    want = sys.argv[1:] or ["all"]
    for n, fn in DEMOS.items():
        if "all" in want or n in want:
            import time; t0 = time.time(); p = fn(); print("demo", n, p, f"{os.path.getsize(p) / 1024:.0f} KB", f"{time.time() - t0:.0f}s")
