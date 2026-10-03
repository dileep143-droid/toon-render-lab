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


def demo_camera():
    import puppet as PU, camera as CM, effects as FX
    from PIL import Image
    fps = C.FPS; PW, PH = 2560, 1440
    L = T.make_scene_layers((1280, 720)); up = lambda a: np.asarray(Image.fromarray(a).resize((PW, PH), Image.LANCZOS))
    far = up(L["far"]); mid = up(L["mid"][..., :3]); mid_rgba = np.dstack([mid, np.where(L["mid"][..., 3] > 0, 255, 0).astype(np.uint8) if False else np.asarray(Image.fromarray(L["mid"][..., 3]).resize((PW, PH)))])
    ground = np.asarray(Image.fromarray(L["ground"]).resize((PW, PH), Image.LANCZOS)); fg = np.asarray(Image.fromarray(L["fg"]).resize((PW, PH), Image.LANCZOS))
    plate_back = [{"img": far, "depth": 0.35}, {"img": mid_rgba, "depth": 0.7}, {"img": ground, "depth": 1.0}]; plate_fg = [{"img": fg, "depth": 1.5}]
    man, rm = T.make_human("man"); kid, rk = T.make_human("kid"); dadi, rd = T.make_human("dadi")
    A = [dict(x=0.30, foot_y=0.93, height=0.50), dict(x=0.52, foot_y=0.95, height=0.42), dict(x=0.78, foot_y=0.92, height=0.46)]
    perf = [PU.Performer(man, rm, [dict(motion="wave", start=3.0, dur=1.6), dict(motion="nod", start=8.5, dur=1.0)]), PU.Performer(kid, rk, [dict(motion="clap", start=5.5, dur=1.5)], idle="idle_breathe"),
            PU.Performer(dadi, rd, [dict(motion="namaste", start=6.5, dur=2.0), dict(motion="point", start=10.5, dur=1.2)])]
    rigs = [rm, rk, rd]
    cs_close = CM.solve_framing("close", A, speaker=2); cs_two = CM.solve_framing("two_shot", A[:2]); cs_full = CM.solve_framing("full", A)
    tr = CM.CameraTrack.from_events([
        dict(camera="ken_burns", start=0.0, dur=3.0, to=[0.5, 0.5, 1.25]),
        dict(camera="push_in", start=3.2, dur=1.6, target=(0.30, 0.62), amount=1.5),
        dict(camera="whip_pan", start=5.2, dur=0.45, to=cs_close.as_list()),
        dict(camera="ken_burns", start=6.1, dur=1.8, to=cs_two.as_list()),
        dict(camera="dutch", start=8.3, dur=0.8, angle=7.0),
        dict(camera="ken_burns", start=9.4, dur=0.8, to=[0.5, 0.5, 1.15, 0.0]),
        dict(camera="pull_out", start=10.4, dur=2.2),
    ], start=[0.5, 0.5, 1.0])
    frames = []
    for i in range(int(13 * fps)):
        t = i / fps; cam = tr.at(t); focus = 1.0 if t < 9 else 0.5
        f = CM.render_view(plate_back, cam, focus=focus if t < 3.0 else None, focus_amount=5.0)
        for p, rig, a in sorted(zip(perf, rigs, A), key=lambda z: z[2]["foot_y"]):
            sx, sy, sc = CM.to_screen(cam, a["x"], a["foot_y"], (PW, PH)); sp, info = p.frame(t, flip=(a["x"] > 0.6))
            PU.draw_character(f, sp, info, rig, sx, sy, a["height"] * PH * sc, flip=(a["x"] > 0.6))
        if cam.z < 1.7: f = CM.render_view(plate_fg, cam, base=f)      # foreground leaves only on wider shots
        if cam.blur > 1: f = C.box_blur_dir(f, cam.blur, cam.blur_angle, 7)
        frames.append(f)
    return C.write_video(frames, os.path.join(OUT, "camera.mp4"), fps, crf=28)


def demo_transitions():
    import puppet as PU, transitions as TR
    man, rm = T.make_human("man"); kid, rk = T.make_human("kid"); dadi, rd = T.make_human("dadi"); fps = C.FPS
    shots = []
    for kind, (img, rig), hp in (("village_day", (man, rm), 400), ("village_evening", (dadi, rd), 380), ("village_night", (kid, rk), 330), ("pond", (man, rm), 400)):
        bg = T.make_background(kind); perf = PU.Performer(img, rig, [dict(motion="wave", start=0.2, dur=1.4), dict(motion="nod", start=1.8, dur=1.0)])
        def mk(bg=bg, perf=perf, rig=rig, hp=hp):
            def f(t):
                fr = bg.copy(); sp, info = perf.frame(t % 3.0); PU.draw_character(fr, sp, info, rig, 640, 650, hp); return fr
            return f
        shots.append(mk())
    plan = [("dissolve", {}), ("wipe", dict(direction="left")), ("iris", dict(center=(0.5, 0.55))), ("page_turn", {}), ("star_wipe", {}), ("flashback", {}), ("meanwhile", dict(text="इसी बीच...", size=110, font="NotoSansDevanagari-Bold.ttf")),
            ("clock_spin", {}), ("dip_white", {}), ("wipe", dict(direction="down", soft=0.12)), ("dip_black", {}), ("cut", {})]
    frames = []; hold = 0.45; dur = 0.9
    for i, (name, kw) in enumerate(plan):
        fa, fb = shots[i % 4], shots[(i + 1) % 4]; t0 = 0.0
        for k in range(int(hold * fps)): frames.append(fa(k / fps))
        for fr in TR.render_transition(fa, fb, name, dur, fps, a_t0=hold, b_t0=0.0, **kw): frames.append(fr)
    return C.write_video(frames, os.path.join(OUT, "transitions.mp4"), fps, crf=28)


def demo_props():
    import puppet as PU, props_motion as PM
    fps = C.FPS; bg = T.make_background("village_day"); P = {n: T.make_prop(n) for n in ("ball", "laddoo", "matka", "kite", "paper", "coin", "plate", "bowl", "spoon", "book", "bucket")}
    man, rm = T.make_human("man"); kid, rk = T.make_human("kid"); pm = PU.Performer(man, rm, [dict(motion="reach_take", start=0.1, dur=1.0), dict(motion="hand_to_mouth", start=9.0, dur=2.4)]); pk = PU.Performer(kid, rk, [dict(motion="clap", start=1.8, dur=1.5)])
    door = np.zeros((300, 150, 4), np.uint8); door[..., :3] = (140, 90, 50); door[..., 3] = 255; door[130:170, 100:120] = (230, 200, 60, 255); door[20:60, 20:130, :3] = (110, 70, 40)
    flagS = np.zeros((90, 170, 4), np.uint8); flagS[..., :3] = (255, 150, 30); flagS[30:60, :, :3] = (255, 255, 255); flagS[..., 3] = 255; cloth = np.zeros((90, 60, 4), np.uint8); cloth[..., :3] = (60, 120, 220); cloth[..., 3] = 255
    fanS = np.zeros((300, 300, 4), np.uint8)
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k in range(3): a = math.radians(k * 120); d.polygon([(150, 150), (150 + 140 * math.cos(a - .18), 150 + 140 * math.sin(a - .18)), (150 + 140 * math.cos(a + .18), 150 + 140 * math.sin(a + .18))], fill=(210, 210, 215, 255), outline=(70, 50, 40, 255))
    d.ellipse((130, 130, 170, 170), fill=(90, 70, 60, 255)); fanS = np.asarray(im); clockface = None
    EV = [dict(prop_motion="throw", prop="ball", start=0.2, dur=1.0, p0="man.hand_r", p1="kid.hand_l", height=160), dict(prop_motion="ball_bounce", prop="ball", start=2.4, x0=250, x1=1000, y_top=250, ground_y=690, dur=3.0, scale=0.55),
          dict(prop_motion="fall_bounce", prop="matka", start=1.0, x=640, y0=150, ground_y=520, scale=0.8), dict(prop_motion="roll", prop="ball", start=5.6, p0=(300, 600), p1=(700, 640), dur=1.6, scale=0.5),
          dict(prop_motion="pour", prop="bucket", start=3.0, dur=2.4, spout=(1010, 330), target=(1060, 480), color=(240, 240, 235), level_rect=(1010, 460, 1110, 520), vessel_pos=(985, 310), tilt=35, scale=0.9),
          dict(prop_motion="stir", prop="spoon", start=0, center=(1060, 470), radius=22, bowl=(1060, 500, 60, 20), scale=0.7), dict(prop_motion="swing", prop="plate", start=0, pivot=(150, 80), rope=250, amp=32, period=2.4, scale=0.7, decay=0.05),
          dict(prop_motion="kite", prop="kite", start=0, hand=(420, 640), kite_pos=(520, 130), scale=1.1), dict(prop_motion="flag", prop="flagS", start=0, pole_top=(1180, 110), scale=0.8),
          dict(prop_motion="clothesline", prop="cloth", start=0, line=((560, 170), (900, 190)), count=3, scale=0.7), dict(prop_motion="door", prop="door", start=6.0, hinge=(790, 330), dur=1.2, close_at=9.0, scale=0.55),
          dict(prop_motion="paper_fly", prop="paper", start=7.0, dur=3.0, p0=(300, 120), p1=(450, 600), scale=0.8), dict(prop_motion="food_vanish", prop="laddoo", start=9.0, pos="man.hand_r", bites=3, scale=0.5),
          dict(prop_motion="coins", prop="coin", start=11.0, hand="kid.hand_r", targets=[(900, 660), (950, 660), (1000, 660), (1050, 660)], interval=0.5, scale=0.6), dict(prop_motion="fan", prop="fanS", start=0, center=(700, 70), rpm=240, scale=0.5),
          dict(prop_motion="clock_hands", start=0, center=(1180, 330), radius=48, speed=240)]
    frames = []
    for i in range(int(14 * fps)):
        t = i / fps; f = bg.copy(); sp, info = pm.frame(t); a1 = PU.draw_character(f, sp, info, rm, 330, 650, 380); sp2, info2 = pk.frame(t, flip=True); a2 = PU.draw_character(f, sp2, info2, rk, 800, 650, 300, flip=True)
        anc = {"man.hand_r": a1["hand_r"], "man.hand_l": a1["hand_l"], "kid.hand_r": a2["hand_r"], "kid.hand_l": a2["hand_l"]}; props = dict(P, door=door, flagS=flagS, cloth=cloth, fanS=fanS)
        for e in EV:
            e = dict(e); 
            if e["prop_motion"] in ("clock_hands",): PM.run_event(f, e, t, props, anc)
            elif t >= e.get("start", 0) - 0.01 or e["prop_motion"] in ("kite", "flag", "clothesline", "swing", "fan", "stir"): PM.run_event(f, e, t, props, anc)
        frames.append(f)
    return C.write_video(frames, os.path.join(OUT, "props_motion.mp4"), fps, crf=28)


def demo_scene_life():
    import scene_life as SL, effects as FX
    fps = C.FPS; man, rm = T.make_human("man")
    import puppet as PU
    pm = PU.Performer(man, rm, [dict(motion="wave", start=1.0, dur=1.6)]); tree = T.make_prop("matka", 260); frames = []
    segs = [("village_day", "village_morning", 0, 4), ("village_evening", "village_evening", 4, 8), ("village_day", "mela", 8, 11), ("village_day", "road", 11, 15)]
    bgs = {k: T.make_background(k) for k in ("village_day", "village_evening")}
    for i in range(int(15 * fps)):
        t = i / fps; kind, preset, s0, s1 = next(s for s in segs if s[2] <= t < s[3]); f = bgs[kind].copy()
        SL.ambient(f, t, preset)
        if preset == "village_morning": SL.water_wheel(f, t, pos=(0.62, 0.52), radius=60, rpm=9); SL.tree_sway(f, t, sprite=tree, pos=(0.9, 0.62), amp=0.05)
        if preset == "road": SL.cycle(f, t, y=0.9, start=11.5, dur=3.0, size=240)
        sp, info = pm.frame(t); PU.draw_character(f, sp, info, rm, 640, 690 if preset != "mela" else 700, 360)
        frames.append(f)
    return C.write_video(frames, os.path.join(OUT, "scene_life.mp4"), fps, crf=28)


def demo_audio():
    import audio_mix as AM, tempfile
    from PIL import Image, ImageDraw
    tmp = tempfile.mkdtemp(); fps = C.FPS; D = 14.0
    v1 = AM.write_wav(tmp + "/v1.wav", AM.synth_voice(2.6, 1)); v2 = AM.write_wav(tmp + "/v2.wav", AM.synth_voice(2.2, 2, f0=230)); v3 = AM.write_wav(tmp + "/v3.wav", AM.synth_voice(2.8, 3, f0=170)); mu = AM.write_wav(tmp + "/m.wav", AM.synth_music(10.0))
    plan = dict(duration=D, voices=[dict(path=v1, t=1.2), dict(path=v2, t=4.6), dict(path=v3, t=8.4)], music=dict(path=mu, gain_db=-11, fade_in=1.0, fade_out=2.0),
                sfx=[dict(name="pop", t=3.0), dict(name="boing", t=7.2), dict(name="coin", t=11.6), dict(name="tada", t=12.4)], ambience=[dict(loc="village_day", start=0, end=7.5), dict(loc="rain", start=7.5, end=D)])
    wav = tmp + "/mix.wav"; info = AM.mix_from_plan(plan, wav); x = AM.decode(wav); rms = AM.rms_track(wav, fps); print("lufs", info["lufs"])
    lanes = [("voices", (240, 120, 90)), ("music (ducks)", (90, 150, 240)), ("sfx", (250, 200, 60)), ("ambience", (110, 190, 120))]; W_, H_ = 1280, 720; x0, x1 = 160, 1230
    def X(t): return x0 + (x1 - x0) * t / D
    base = Image.new("RGB", (W_, H_), (30, 32, 40)); d = ImageDraw.Draw(base)
    for li, (nm, col) in enumerate(lanes): d.text((20, 150 + li * 110), nm, fill=(230, 230, 230), font=C.load_font(None, 22)); d.rectangle([x0, 130 + li * 110, x1, 210 + li * 110], outline=(70, 72, 85))
    for v in plan["voices"]: dur = len(AM.decode(v["path"])) / AM.SR; d.rectangle([X(v["t"]), 135, X(v["t"] + dur), 205], fill=lanes[0][1])
    d.rectangle([X(0), 245, X(D), 315], fill=lanes[1][1])
    for v in plan["voices"]: dur = len(AM.decode(v["path"])) / AM.SR; d.rectangle([X(v["t"]), 245, X(v["t"] + dur), 315], fill=(40, 60, 100))
    for s_ in plan["sfx"]: d.polygon([(X(s_["t"]), 355), (X(s_["t"]) + 14, 395), (X(s_["t"]) - 14, 395)], fill=lanes[2][1]); d.text((X(s_["t"]) - 18, 400), s_["name"], fill=(255, 255, 255), font=C.load_font(None, 18))
    for a in plan["ambience"]: d.rectangle([X(a["start"]), 465, X(a["end"]), 535], fill=lanes[3][1]); d.text((X(a["start"]) + 8, 490), a["loc"], fill=(20, 40, 20), font=C.load_font(None, 22))
    d.text((20, 20), "audio_mix: voices + music (auto-ducked) + sfx + ambience  ->  -14 LUFS", fill=(255, 255, 255), font=C.load_font(None, 30)); d.text((20, 70), f"measured loudness: {info['lufs']:.1f} LUFS", fill=(200, 255, 200), font=C.load_font(None, 24))
    base = np.asarray(base); frames = []
    for i in range(int(D * fps)):
        t = i / fps; f = base.copy(); im = Image.fromarray(f); dd = ImageDraw.Draw(im); dd.line([(X(t), 120), (X(t), 560)], fill=(255, 255, 255), width=3)
        lvl = float(min(1.0, rms[min(i, len(rms) - 1)] * 4)); dd.rectangle([160, 610, 160 + 1000, 650], outline=(120, 120, 130)); dd.rectangle([160, 610, 160 + int(1000 * lvl), 650], fill=(120, 230, 140) if lvl < 0.8 else (250, 90, 80)); dd.text((20, 615), "level", fill=(230, 230, 230), font=C.load_font(None, 22))
        frames.append(np.asarray(im))
    vid = tmp + "/v.mp4"; C.write_video(frames, vid, fps, crf=26); out = os.path.join(OUT, "audio_mix.mp4"); AM.mix_from_plan(plan, out, video=vid); return out


def demo_titles():
    import puppet as PU, titles as TI
    fps = C.FPS; F = "NotoSansDevanagari-Bold.ttf"; bg = T.make_background("village_day"); man, rm = T.make_human("man"); dadi, rd = T.make_human("dadi"); kid, rk = T.make_human("kid")
    pm = PU.Performer(man, rm, [dict(motion="wave", start=0.4, dur=1.4)]); pd_ = PU.Performer(dadi, rd, [dict(motion="namaste", start=1.2, dur=1.8)]); pk = PU.Performer(kid, rk, [dict(motion="nod", start=2.4, dur=1.2)])
    lines = [dict(start=0.3, end=2.6, text="आज हम एक नई कहानी सुनेंगे", text2="Today we will hear a new story", speaker="dadi"), dict(start=3.0, end=5.4, text="छोटू को बहुत भूख लगी थी, और लड्डू सामने रखे थे!", text2="Chhotu was very hungry, and the laddoos were right there!", speaker="narr")]
    frames = []
    for i in range(int(4 * fps)): frames.append(TI.title_card(i / fps, "सोनपुर की टोली", "जादुई लड्डू", font=F, subtitle="एपिसोड 1", dur=4.0))
    for i in range(int(6 * fps)):
        t = i / fps; f = bg.copy()
        for perf, rig, x, hp, fl in ((pd_, rd, 380, 390, False), (pm, rm, 820, 430, True), (pk, rk, 600, 300, False)):
            sp, info = perf.frame(t, flip=fl); PU.draw_character(f, sp, info, rig, x, 640, hp, flip=fl)
        TI.lower_third(f, t, "दादी", "सबकी प्यारी", start=0.3, dur=2.4, font=F); TI.lower_third(f, t, "छोटू", "हमेशा भूखा", start=3.0, dur=2.4, font=F, side="right", color=(60, 140, 230)); TI.burn_subtitles(f, lines, t, font=F); frames.append(f)
    for i in range(int(4 * fps)): frames.append(TI.end_card(i / fps, "मिल-जुलकर बाँटने में ही खुशी है", font=F, dur=4.0))
    TI.thumbnail([man, kid], "जादुई लड्डू का राज़!", bg=bg, font=F, out_path=os.path.join(OUT, "thumbnail.jpg")); TI.write_srt(lines, os.path.join(OUT, "titles_demo.srt"))
    return C.write_video(frames, os.path.join(OUT, "titles.mp4"), fps, crf=26)



def demo_qa():
    """a 10 s clip with planted faults; the QA report is burned into the picture so you can see each check fire"""
    import puppet as PU, qa_checks as QA
    from PIL import Image, ImageDraw
    man, rman = T.make_human("man"); bg = bg_frame(); fps = C.FPS; n = 10 * fps
    perf = PU.Performer(man, rman, [dict(motion="wave", start=0.2, dur=1.6), dict(motion="nod", start=2.2, dur=1.2), dict(motion="clap", start=5.0, dur=1.6)])
    frames = []
    for i in range(n):
        t = i / fps; f = bg.copy(); sp, info = perf.frame(t)
        if not (3.5 <= t < 4.5):                                  # fault 2: character missing for 1 s
            PU.draw_character(f, sp, info, rman, 640, 640, 420)
        if 6.5 <= t < 7.0: f[:] = 0                               # fault 1: black flash
        frames.append(f)
    frames[int(8 * fps):int(9.5 * fps)] = [frames[int(8 * fps)]] * int(1.5 * fps)   # fault 3: frozen 1.5 s
    plan = {"actors": [{"who": "man", "box": [0.35, 0.2, 0.65, 0.92], "start": 0, "end": 10}], "motion": [(0, 10)]}
    rep = QA.run_qa(frames, plan, plates=bg); txt = QA.format_report(rep).split("\n")
    out = []
    for i, f in enumerate(frames):
        im = Image.fromarray(f); d = ImageDraw.Draw(im); d.rectangle([0, 0, 760, 24 + 20 * len(txt)], fill=(0, 0, 0)); t = i / fps
        for k, line in enumerate(txt):
            hot = k > 0 and any(abs(t - float(x)) < 0.3 for x in line.split("]")[1].split("s")[0].replace("-", " ").split()[:2]) if k else False
            d.text((8, 6 + 20 * k), line[:100], fill=(255, 80, 80) if hot else (255, 255, 255))
        out.append(np.asarray(im))
    return C.write_video(out, os.path.join(OUT, "qa_checks.mp4"), fps, crf=28)


def demo_registry():
    """two shots described ONLY by JSON (no code per episode) joined by a registry transition"""
    import registry as R, json
    shot1 = {"duration": 5.0, "cast": {"dadi": {"kind": "human", "art": "dadi", "x": 930, "y": 640, "height": 380, "flip": True}, "chhotu": {"kind": "human", "art": "kid", "x": 250, "y": 660, "height": 300},
             "sheru": {"kind": "animal", "art": "dog", "x": 560, "y": 665, "height": 150}},
             "events": [{"ambient": "village_morning"}, {"motion": "walk_cycle", "who": "chhotu", "start": 0.2, "dur": 1.6, "speed": 260}, {"motion": "wave", "who": "dadi", "start": 1.0, "dur": 1.6},
                        {"motion": "bark", "who": "sheru", "start": 1.4, "dur": 1.2}, {"effect": "exclaim", "who": "sheru", "start": 1.5, "dur": 1.0}, {"motion": "namaste", "who": "chhotu", "start": 2.2, "dur": 1.6},
                        {"effect": "hearts", "who": "dadi", "start": 3.0, "dur": 1.5}, {"camera": "push_in", "start": 2.0, "dur": 2.5, "target": [0.72, 0.55], "amount": 1.5},
                        {"effect": "vignette", "start": 0, "strength": 0.4}, {"transition": "iris", "start": 4.4, "dur": 0.6}]}
    shot2 = {"duration": 4.0, "cast": {"goat": {"kind": "animal", "art": "goat", "x": 640, "y": 660, "height": 260}, "hen": {"kind": "bird", "art": "hen", "x": 1000, "y": 670, "height": 120, "flip": True}},
             "events": [{"effect": "rain", "start": 0, "intensity": 0.8}, {"effect": "wet", "start": 0}, {"motion": "bleat", "who": "goat", "start": 0.6, "dur": 1.2},
                        {"motion": "peck", "who": "hen", "start": 0.4, "dur": 2.0}, {"effect": "sweat_drop", "who": "goat", "start": 1.0, "dur": 1.5}, {"effect": "lightning", "start": 2.2, "dur": 0.6},
                        {"title": "lower_third", "name": "बकरी", "role": "भीगी हुई", "start": 1.0, "dur": 2.5}]}
    print("shot1 errors:", R.validate_shot(shot1), "shot2 errors:", R.validate_shot(shot2))
    s1 = R.Shot(shot1, plate=bg_frame("village_day"), font="NotoSansDevanagari-Bold.ttf"); s2 = R.Shot(shot2, plate=bg_frame("village_day"), font="NotoSansDevanagari-Bold.ttf")
    fps = C.FPS
    def gen():
        for i in range(int(5.0 * fps)):
            t = i / fps; yield s1.frame(t, s2.frame(0.0) if t >= 4.4 else None)
        for i in range(int(4.0 * fps)): yield s2.frame(i / fps)
    json.dump({"shot1": shot1, "shot2": shot2}, open(os.path.join(OUT, "registry_demo_shots.json"), "w"), ensure_ascii=False, indent=1)
    return C.write_video(gen(), os.path.join(OUT, "registry.mp4"), fps, crf=28)


def demo_followup():
    """the follow-up additions, all driven by shot JSON: dawn / dusk / lamp grades, chimney smoke, layered flame, 3 new dances, 3 new falls, food eaten (bites / by an animal),
    parallax from ONE background with a focus pull"""
    import registry as R
    F = "NotoSansDevanagari-Bold.ttf"; plate = bg_frame()
    A = {"duration": 5.0, "parallax": True, "cast": {"kid": {"kind": "human", "art": "kid", "x": 560, "y": 640, "height": 300}, "dadi": {"kind": "human", "art": "dadi", "x": 840, "y": 640, "height": 340, "flip": True}},
         "events": [{"effect": "dawn_grade", "start": 0, "dur": 5.0, "fade": 0.8}, {"life": "chimney_smoke", "pos": [0.14, 0.52], "wind": 1.2}, {"motion": "garba_turn_clap", "who": "kid", "start": 0.3, "dur": 4.4},
                    {"motion": "clap_dance", "who": "dadi", "start": 0.3, "dur": 4.4}, {"camera": "push_in", "start": 0.3, "dur": 3.5, "target": [0.62, 0.55], "amount": 1.45},
                    {"camera": "focus_pull", "start": 1.2, "dur": 0.9, "to": "far", "from_focus": "near", "amount": 9}, {"camera": "focus_pull", "start": 2.8, "dur": 0.9, "to": "near", "amount": 9},
                    {"title": "lower_third", "name": "सुबह", "role": "dawn_grade + parallax", "start": 0.6, "dur": 3.0}]}
    B = {"duration": 5.0, "cast": {"man": {"kind": "human", "art": "man", "x": 720, "y": 650, "height": 380}, "kid": {"kind": "human", "art": "kid", "x": 480, "y": 660, "height": 290}},
         "events": [{"effect": "dusk_grade", "start": 0, "dur": 5.0, "fade": 0.8}, {"effect": "bonfire", "pos": [0.22, 0.86], "size": 0.9}, {"life": "chimney_smoke", "pos": [0.14, 0.52], "wind": -1.0},
                    {"motion": "hop_dance", "who": "kid", "start": 0.3, "dur": 4.4}, {"motion": "clap_dance", "who": "man", "start": 0.3, "dur": 4.4}, {"effect": "flame", "pos": [0.88, 0.88], "size": 150},
                    {"title": "lower_third", "name": "शाम", "role": "dusk_grade + flames", "start": 0.6, "dur": 3.0}]}
    Cc = {"duration": 5.0, "cast": {"kid": {"kind": "human", "art": "kid", "x": 420, "y": 660, "height": 300}, "man": {"kind": "human", "art": "man", "x": 760, "y": 650, "height": 380}, "dadi": {"kind": "human", "art": "dadi", "x": 1040, "y": 640, "height": 340, "flip": True}},
          "events": [{"effect": "evening_lamp_grade", "lamps": [[0.3, 0.55, 260], [0.82, 0.5, 220]], "start": 0, "dur": 5.0, "fade": 0.6}, {"motion": "fall_slip_peel", "who": "kid", "start": 0.8, "dur": 1.5},
                     {"motion": "fall_trip_forward", "who": "man", "start": 1.8, "dur": 1.6}, {"motion": "fall_sit_bump", "who": "dadi", "start": 3.0, "dur": 1.5}, {"effect": "impact_star", "who": "kid", "start": 2.1, "dur": 0.7},
                     {"effect": "dizzy_stars", "who": "dadi", "start": 4.3, "dur": 0.7}, {"title": "lower_third", "name": "रात", "role": "evening_lamp_grade + 3 falls", "start": 0.6, "dur": 3.0}]}
    D = {"duration": 5.0, "cast": {"kid": {"kind": "human", "art": "kid", "x": 330, "y": 660, "height": 300}, "sheru": {"kind": "animal", "art": "dog", "x": 880, "y": 668, "height": 170, "flip": True}, "dadi": {"kind": "human", "art": "dadi", "x": 1120, "y": 640, "height": 330, "flip": True}},
         "events": [{"motion": "give", "who": "kid", "start": 0.3, "dur": 1.2}, {"prop_motion": "food_eaten_by_animal", "prop": "laddoo", "start": 1.2, "pos": [470, 540], "mouth": "sheru.mouth", "ground": 668, "chomps": 3},
                    {"motion": "bark", "who": "sheru", "start": 1.2, "dur": 0.6}, {"motion": "wag_tail", "who": "sheru", "start": 1.8, "dur": 2.4}, {"prop_motion": "food_disappear", "prop": "laddoo", "start": 1.8, "pos": [1010, 430], "mouth": [1080, 380], "ground": 668, "bites": 3},
                    {"motion": "hand_to_mouth", "who": "dadi", "start": 1.8, "dur": 2.0}, {"effect": "hearts", "who": "dadi", "start": 3.7, "dur": 1.2}, {"title": "lower_third", "name": "लड्डू", "role": "food_eaten_by_animal + food_disappear", "start": 0.6, "dur": 3.0}]}
    import testart as TA
    props = {"laddoo": TA.make_prop("laddoo", 80)}
    shots = [R.Shot(x, plate=plate, props=props, font=F) for x in (A, B, Cc, D)]; fps = C.FPS; fade = int(0.4 * fps)
    def gen():
        for si, sh in enumerate(shots):
            n = int(sh.duration * fps)
            for i in range(n):
                f = sh.frame(i / fps)
                if si < len(shots) - 1 and i >= n - fade:
                    k = (i - (n - fade) + 1) / fade; g = shots[si + 1].frame((i - (n - fade)) / fps) if False else shots[si + 1].frame(0.0); f = (f.astype(np.float32) * (1 - k) + g.astype(np.float32) * k).astype(np.uint8)
                yield f
    return C.write_video(gen(), os.path.join(OUT, "followup.mp4"), fps, crf=28)

DEMOS = {"followup": demo_followup, "registry": demo_registry, "qa": demo_qa, "titles": demo_titles, "audio": demo_audio, "scene_life": demo_scene_life, "puppet": demo_puppet, "animals": demo_animals, "effects": demo_effects, "camera": demo_camera, "transitions": demo_transitions, "props": demo_props}
if __name__ == "__main__":
    want = sys.argv[1:] or ["all"]
    for n, fn in DEMOS.items():
        if "all" in want or n in want:
            import time; t0 = time.time(); p = fn(); print("demo", n, p, f"{os.path.getsize(p) / 1024:.0f} KB", f"{time.time() - t0:.0f}s")
