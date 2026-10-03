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


def demo_animals():
    import puppet as PU, animals as AN
    bg = T.make_background("village_day"); fps = C.FPS; dur = 10.0
    goat, rg = T.make_quadruped("goat"); dog, rd = T.make_quadruped("dog"); cow, rc = T.make_quadruped("cow"); hen, rh = T.make_bird("hen"); par, rp = T.make_bird("parrot"); mon, rm = T.make_monkey()
    sc = lambda rig, hpx: hpx / rig["size"][1]
    G, Dg, Cw, Hn, Pr = 300, 250, 330, 150, 110
    P = [(AN.AnimalPerformer(goat, rg, [dict(motion="walk", start=0, dur=3.0, distance=520 / sc(rg, G)), dict(motion="bleat", start=3.2, dur=1.1), dict(motion="eat", start=4.6, dur=3.0), dict(motion="butt", start=8.0, dur=1.4)]), rg, 90, 590, G, False),
         (AN.AnimalPerformer(dog, rd, [dict(motion="run", start=0.3, dur=2.6, distance=760 / sc(rd, Dg)), dict(motion="sit", start=3.1, dur=1.0), dict(motion="bark", start=4.3, dur=1.0), dict(motion="wag_tail", start=5.5, dur=2.0), dict(motion="beg", start=7.6, dur=2.0)]), rd, -160, 700, Dg, False),
         (AN.AnimalPerformer(cow, rc, [dict(motion="moo", start=1.0, dur=1.4), dict(motion="eat", start=3.0, dur=3.5), dict(motion="walk", start=7.0, dur=2.5, distance=150 / sc(rc, Cw))]), rc, 1130, 520, Cw, True),
         (AN.AnimalPerformer(hen, rh, [dict(motion="peck", start=0.5, dur=1.8), dict(motion="walk", start=2.6, dur=2.0, speed=140), dict(motion="squawk", start=5.2, dur=1.0), dict(motion="hop", start=6.6, dur=0.8)]), rh, 700, 610, Hn, False),
         (AN.AnimalPerformer(par, rp, [dict(motion="fly", start=0.5, dur=8.5, distance=1500 / sc(rp, Pr))], idle=None), rp, -120, 170, Pr, False)]
    mk = AN.AnimalPerformer(mon, rm, [dict(motion="swing", start=1.0, dur=8.0)], idle=None)
    frames = []
    for i in range(int(dur * fps)):
        t = i / fps; f = bg.copy()
        from PIL import ImageDraw, Image
        for perf, rig, x0, y, hpx, flip in P:
            sp, info = perf.frame(t, flip=flip); k = hpx / rig["size"][1]; x = x0 + (-1 if flip else 1) * info["travel"] * k
            fy = y if rig["kind"] != "bird" or rig["name"] == "hen" else y + 0
            PU.draw_character(f, sp, info, rig, x, fy, hpx, flip=flip)
        sp, info = mk.frame(t) if t >= 1.0 else mk.frame(1.0)
        a = PU.draw_character(f, sp, info, rm, 1190, 330, 260)
        frames.append(f)
    return C.write_video(frames, os.path.join(OUT, "animals.mp4"), fps, crf=28)


def demo_effects():
    import puppet as PU, effects as FX
    fps = C.FPS; man, rm = T.make_human("man"); kid, rk = T.make_human("kid"); pm, pk = PU.Performer(man, rm), PU.Performer(kid, rk)
    days = {k: T.make_background(k) for k in ("village_day", "village_evening", "village_night")}
    marks = ["sweat_drop", "anger_mark", "hearts", "dizzy_stars", "question", "exclaim", "idea_bulb", "sparkles", "music_notes", "tears", "gloom_cloud", "zzz", "exclaim_question", "sweat_spray"]
    frames = []
    for i in range(int(16 * fps)):
        t = i / fps
        if t < 4: bg = days["village_day"]
        elif t < 8: bg = days["village_night"]
        elif t < 11: bg = days["village_evening"]
        else: bg = days["village_day"]
        f = bg.copy()
        sp, info = pm.frame(t); a1 = PU.draw_character(f, sp, info, rm, 430, 640, 380)
        sp2, info2 = pk.frame(t, flip=True); a2 = PU.draw_character(f, sp2, info2, rk, 880, 650, 300, flip=True)
        head1 = (a1["head_top"][0], a1["head_top"][1] + 40); head2 = (a2["head_top"][0], a2["head_top"][1] + 30)
        ev = []
        if t < 4:
            ev += [dict(effect="clouds", count=5), dict(effect="sun_rays", intensity=0.6), dict(effect="leaves", count=14, wind=200)]
            ev += [dict(effect="rain", start=1.6, dur=2.4, intensity=0.9, angle=18, fade=0.6), dict(effect="lightning", start=2.0, dur=2.0, rate=1.2, seed=2), dict(effect="puddle", start=1.8, dur=2.2, center=(0.5, 0.9), size=(0.2, 0.05)), dict(effect="wet", start=1.6, dur=2.4, amount=0.5, fade=0.6)]
        elif t < 8:
            ev += [dict(effect="night"), dict(effect="fireflies", count=18), dict(effect="bonfire", pos=(0.62, 0.9), size=0.7), dict(effect="vignette", strength=0.5)]
            ev += [dict(effect="zzz", start=4.5, dur=3.0, anchor=head1), dict(effect="sparkles", start=6.0, dur=1.8, anchor=head2)]
        elif t < 11:
            ev += [dict(effect="grade", preset="dusk"), dict(effect="festival_lights", points=[(0.0, 0.1), (0.5, 0.2), (1.0, 0.1)]), dict(effect="diya", pos=(0.28, 0.93), size=44), dict(effect="diya", pos=(0.72, 0.93), size=44, seed=2)]
            ev += [dict(effect="fireworks", start=8.0, dur=3.0), dict(effect="sparklers", start=8.4, dur=2.4, pos=(0.5, 0.78)), dict(effect="holi_burst", start=10.0, dur=0.95, pos=(0.5, 0.55))]
        else:
            for j, m in enumerate(marks[:12]):
                st = 11 + j * 0.42
                ev.append(dict(effect=m, start=st, dur=0.42 if m not in ("tears", "gloom_cloud") else 0.42, anchor=head1 if j % 2 == 0 else head2, fade=0.05))
            ev += [dict(effect="speed_lines", start=14.4, dur=0.8, anchor=head1, mode="radial"), dict(effect="impact_star", start=14.5, dur=0.7, anchor=(640, 330)), dict(effect="shake", start=14.5, dur=0.6, amp=14),
                   dict(effect="flash_white", start=15.4, dur=0.5), dict(effect="zoom_punch", start=12.0, dur=0.4, amount=0.1)]
        for e in ev:
            e = dict(e); e.setdefault("start", 0.0)
            if e["effect"] in ("shake", "zoom_punch", "flash_white"): FX.apply(f, e["effect"], t - e["start"], **{k: v for k, v in e.items() if k not in ("effect", "start", "dur", "fade")}) if 0 <= t - e["start"] <= e.get("dur", 1) else None
            else: FX.run_event(f, dict(e, dur=e.get("dur")) if e.get("dur") else e, t)
        frames.append(f)
    return C.write_video(frames, os.path.join(OUT, "effects.mp4"), fps, crf=28)


DEMOS = {"puppet": demo_puppet, "animals": demo_animals, "effects": demo_effects}
if __name__ == "__main__":
    want = sys.argv[1:] or ["all"]
    for n, fn in DEMOS.items():
        if "all" in want or n in want:
            import time; t0 = time.time(); p = fn(); print("demo", n, p, f"{os.path.getsize(p) / 1024:.0f} KB", f"{time.time() - t0:.0f}s")
