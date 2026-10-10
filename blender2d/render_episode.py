"""EPISODE RENDERER - shots.json + per-line voice clips + puppets + music -> finished scene clips.
Per shot: background, actors (front puppet / full-pose drawing / side walker with drawn legs / Sheru sprite cycle / prop), lines timed
from the voice clips (lip sync from Rhubarb cues for the speaker; radio lines = the radio 'talks', mouths stay shut), blinks + breathing for
everyone, locked camera, bodies on twos. Missing pieces degrade gracefully (rig missing -> drawing sprite; side rig missing -> front
stepping; no voice timing yet -> estimated durations) so the layout can be checked before every asset exists.
Audio: voice clips at their times (radio lines through a radio filter), scene music beds continuous under everything (episode_audio.mix:
no ducking, low bed), master -14 LUFS.
  python render_episode.py <episode_dir> <scene|all> <out_dir> [--preview]   (--preview = half size, 12 fps)"""
import json, math, os, re, shutil, subprocess, sys, wave
import numpy as np, cv2
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "pipeline2d"))
FF = shutil.which("ffmpeg") or r"C:\Users\goddu\Downloads\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
PUP = os.path.join(HERE, "puppet")
SHAPE = {"X": "closed", "A": "closed", "B": "mouth_half", "C": "mouth_half", "D": "mouth_open", "E": "mouth_o", "F": "mouth_o", "G": "mouth_half", "H": "mouth_half"}
LIGHT = {"night": (0.80, 0.84, 1.0), "evening": (1.0, 0.94, 0.86), "sepia": (1.0, 0.88, 0.70)}           # character grade per scene (bg name)
HOLD = {"radio", "kite", "namaste"}                                                    # held all shot; other poses are talk-gestures
NAME2DIR = {"Chhotu": "chhotu", "Gudiya": "gudiya", "Raju": "raju", "Dadi": "dadi", "Lallan": "lallan", "Masterji": "masterji",
            "Jugaadu Chacha": "jugaadu_chacha", "Sheru": "sheru"}


class Cast:
    """Lazy-loaded puppets per character."""
    def __init__(self): self.front, self.side, self.legs, self.sprites = {}, {}, {}, {}

    def puppet(self, who):
        if who not in self.front:
            try:
                from mesh_puppet import Puppet
                self.front[who] = Puppet(os.path.join(PUP, who)) if os.path.exists(os.path.join(PUP, who, "parts", "rig.json")) else None
            except Exception as ex: print("  puppet fail", who, ex); self.front[who] = None
        return self.front[who]

    def face_on(self, who, pose_png, face):
        """Full-pose drawing (same canvas as the rig) with the rig's mouth/eye pixels for `face` laid over it (feathered masks)."""
        im = Image.open(pose_png).convert("RGBA")
        if not face: return im
        P = os.path.join(PUP, who, "parts")
        if who not in self.sprites.setdefault("_masks", {}):
            ld = lambda n: np.asarray(Image.open(os.path.join(P, n + ".png")).convert("RGBA")).astype(int) if os.path.exists(os.path.join(P, n + ".png")) else None
            base = ld("head_closed"); m = {}
            for grp, names in (("mouth", ("head_mouth_open", "head_mouth_half", "head_mouth_o")), ("eyes", ("head_blink",))):
                acc = np.zeros(base.shape[:2], np.uint8)
                for n in names:
                    o = ld(n)
                    if o is not None: acc |= (np.abs(o - base).max(2) > 40).astype(np.uint8)
                acc = cv2.dilate(acc, np.ones((9, 9), np.uint8)); m[grp] = cv2.GaussianBlur(acc.astype(np.float32), (7, 7), 0)
            self.sprites["_masks"][who] = m
        m = self.sprites["_masks"][who]; src_n = "head_" + face if face != "closed" else "head_closed"
        if not os.path.exists(os.path.join(P, src_n + ".png")) or im.size != Image.open(os.path.join(P, src_n + ".png")).size: return im
        src = np.asarray(Image.open(os.path.join(P, src_n + ".png")).convert("RGBA")).astype(np.float32)
        mask = (m["eyes"] if face == "blink" else m["mouth"])[..., None] * (src[..., 3:4] / 255)
        out = np.asarray(im).astype(np.float32); out = out * (1 - mask) + src * mask
        return Image.fromarray(out.clip(0, 255).astype(np.uint8))

    def poses(self, who):
        p = os.path.join(PUP, who, "joints.json")
        return set(json.load(open(p, encoding="utf-8")).get("poses", {})) if os.path.exists(p) else set()

    def walker(self, who, style):
        k = (who, style)
        if k not in self.legs:
            d = os.path.join(PUP, who + "_side")
            try:
                from side_puppet import SidePuppet
                from walk_legs import DrawnLegs
                if who not in self.side: self.side[who] = SidePuppet(d) if os.path.exists(os.path.join(d, "joints.json")) else None
                self.legs[k] = DrawnLegs(d, self.side[who], style) if self.side[who] else None
            except Exception as ex: print("  walker fail", who, ex); self.legs[k] = None
        return self.side.get(who), self.legs[k]

    def sprite(self, path):
        if path not in self.sprites:
            if not os.path.exists(path): self.sprites[path] = None
            else:
                im = Image.open(path).convert("RGBA"); a = np.asarray(im)[..., 3]
                if a.min() > 250:                                                       # no alpha yet -> knock out the white background
                    rgb = np.asarray(im.convert("RGB")).astype(int); white = (rgb.min(2) >= 235).astype(np.uint8)
                    n, lab = cv2.connectedComponents(white, connectivity=4)              # only white TOUCHING THE EDGE is background -
                    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}   # a white coat inside the outline stays
                    m = (~np.isin(lab, list(edge))).astype(np.uint8) * 255
                    im.putalpha(Image.fromarray(cv2.GaussianBlur(m, (3, 3), 0)))
                bb = im.getbbox(); self.sprites[path] = im.crop(bb) if bb else im
        return self.sprites[path]


def trim(im):
    bb = im.getbbox(); return im.crop(bb) if bb else im


def load_lines(ep):
    """id -> {clip, dur, mouth, speaker, radio, text}; falls back to estimated durations from units.json."""
    split = os.path.join(ep, "voices", "hi", "split", "out", "lines_timed.json")
    if os.path.exists(split):
        L = json.load(open(split, encoding="utf-8"))
        base = os.path.dirname(split)
        return [{**l, "clip": os.path.join(base, l["clip"]) if l.get("clip") else None,
                 "mouth": os.path.join(base, l["mouth"]) if l.get("mouth") else None, "dur": l.get("duration_s", 2.0)} for l in L]
    U = json.load(open(os.path.join(ep, "voices", "hi", "units.json"), encoding="utf-8"))["units"]
    return [{**u, "clip": None, "mouth": None, "dur": max(1.0, 0.075 * len(re.sub(r"<[^>]+>", "", u["text"])))} for u in U]


def match_lines(prefixes, lines, used):
    out = []
    for p in prefixes:
        p2 = p.strip().strip('"')
        for i, l in enumerate(lines):
            if i in used: continue
            if l["text"].strip().strip('"').startswith(p2[:12]) or p2[:12] in l["text"]: out.append(l); used.add(i); break
        else: print("  line not found:", p[:30])
    return out


def mouth_track(line, t):
    if not line.get("mouth") or not os.path.exists(line["mouth"]):
        return "mouth_half" if int(t * 8) % 3 else "mouth_open"                         # generic talk flap until Rhubarb cues exist
    cues = line.setdefault("_cues", json.load(open(line["mouth"]))["mouthCues"])
    for c in cues:
        if c["start"] <= t < c["end"]: return SHAPE.get(c["value"], "closed")
    return "closed"


def render_scene(ep, scene_id, out_dir, preview=False):
    S = json.load(open(os.path.join(ep, "shots.json"), encoding="utf-8")); lines = load_lines(ep); used = set()
    FPS = 12 if preview else 24; W, H = (960, 540) if preview else (1920, 1080); k = W / 1920
    cast = Cast(); shots = [s for s in S["shots"] if scene_id == "all" or str(s["scene"]) == str(scene_id)]
    os.makedirs(out_dir, exist_ok=True); tag = f"scene{scene_id}"
    vid = os.path.join(out_dir, f"{tag}_video.mp4")
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", vid], stdin=subprocess.PIPE)
    voice_events, t_global, bed_starts, cache = [], 0.0, [], {}
    font = None                                                                          # on-screen text is ENGLISH (all languages share one video)
    for fp in (r"C:\Windows\Fonts\segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", os.environ.get("DEVA_FONT", "")):
        try: font = ImageFont.truetype(fp, int(50 * k)); break
        except Exception: pass
    font = font or ImageFont.load_default()
    last_scene = None
    for shot in shots:
        if shot["scene"] != last_scene: bed_starts.append((S["beds"][str(shot["scene"])], t_global)); last_scene = shot["scene"]
        L = match_lines(shot.get("lines", []), lines, used)
        lead, gap = shot.get("lead", 0.5), 0.35; t = lead; timed = []                  # lead: walk-ins stop before talking
        for l in L: timed.append((t, l)); t += l["dur"] + gap
        dur = max(shot.get("min", 3.0), t + 0.6)
        for st, l in timed: voice_events.append((t_global + st, l))
        bgp = os.path.join(ep, "bg", shot["bg"] + ".png")
        bg = Image.open(bgp).convert("RGB").resize((W, H), Image.LANCZOS) if os.path.exists(bgp) else Image.new("RGB", (W, H), (60, 60, 70))
        n = int(round(dur * FPS))
        print(f"shot {shot['id']}: {dur:.1f}s, {len(L)} lines, {len(shot.get('actors', []))} actors", flush=True)
        STILL = os.environ.get("STILLS"); fl = [int(min(dur - 0.1, (timed[0][0] + 0.4) if timed else dur / 2) * FPS)] if STILL else range(n)
        for f in fl:
            ts = f / FPS; tb = (f - f % (1 if preview else 2)) / FPS                  # bodies on twos
            fr = bg.copy()
            if shot.get("slow_push"):                                                    # gentle push-in for the flashback
                z = 1 + 0.06 * ts / dur; cw, ch = int(W / z), int(H / z); fr = fr.crop(((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)).resize((W, H))
            speaking = next((l for st, l in timed if st <= ts < st + l["dur"]), None)
            spk_dir = NAME2DIR.get(speaking["speaker"]) if speaking and not speaking.get("radio") else None
            draws = []
            spk_a = next((b for b in shot.get("actors", []) if b["who"] == spk_dir), None) if spk_dir else None
            spk_t = ts - next(st for st, l in timed if l is speaking) if spk_a else 0.0
            for a in sorted(shot.get("actors", []), key=lambda a: a.get("ground", 1000)):
                if spk_a is not None and a is not spk_a: a = {**a, "_spk_x": spk_a.get("x", 960), "_spk_t": spk_t}
                im, x, g, h = actor_image(a, cast, tb, ts, dur, speaking if spk_dir == a["who"] else None, timed, cache)
                if im is not None: draws.append((im, x, g, h))
            tint = LIGHT.get(next((t_ for t_ in LIGHT if t_ in shot["bg"]), ""), None)
            for im, x, g, h in draws:
                s = h * k / im.height; ch = im.resize((max(1, int(im.width * s)), max(1, int(h * k))), Image.LANCZOS)
                if tint:                                                                 # characters lit like the scene (night = cool moonlight,
                    arr = np.asarray(ch).astype(np.float32); arr[..., :3] *= tint       # evening = warm glow) instead of flat daylight
                    ch = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
                sw, sh_ = int(ch.width * 0.62), max(4, int(ch.width * 0.09))             # soft CONTACT SHADOW at the feet: grounded, not floating
                shad = Image.new("L", (sw + 40, sh_ + 40), 0); ImageDraw.Draw(shad).ellipse([20, 20, 20 + sw, 20 + sh_], fill=105)
                shad = shad.filter(ImageFilter.GaussianBlur(9 * k + 2))
                fr.paste((10, 8, 20), (int(x * k - sw / 2 - 20), int(g * k - sh_ / 2 - 20)), shad)
                fr.paste(ch, (int(x * k - ch.width / 2), int(g * k - ch.height)), ch)
            for key in ("title", "card"):                                                # lower band, never over faces; wrapped
                if shot.get(key) and ts < min(dur, 4.5):
                    d = ImageDraw.Draw(fr); words, rows = shot[key].split(), [""]
                    for w_ in words:
                        trial = (rows[-1] + " " + w_).strip()
                        if d.textlength(trial, font=font) > W * 0.8 and rows[-1]: rows.append(w_)
                        else: rows[-1] = trial
                    lh = 64 * k; y0 = H - 70 * k - lh * len(rows); tw = max(d.textlength(r, font=font) for r in rows)
                    d.rectangle([(W - tw) / 2 - 28 * k, y0 - 14 * k, (W + tw) / 2 + 28 * k, y0 + lh * len(rows) + 10 * k], fill=(25, 20, 40))
                    for i_, r in enumerate(rows): d.text(((W - d.textlength(r, font=font)) / 2, y0 + i_ * lh), r, font=font, fill=(255, 220, 120))
            if STILL: os.makedirs(os.path.join(out_dir, "stills"), exist_ok=True); fr.save(os.path.join(out_dir, "stills", f"{shot['id']}.jpg"), quality=88)
            else: enc.stdin.write(fr.tobytes())
        t_global += dur
    enc.stdin.close(); enc.wait()
    if os.environ.get("STILLS"): return None
    # ---- audio: voice clips + radio filter + continuous beds
    voices = []
    tmp = os.path.join(out_dir, f"_{tag}_tmp"); os.makedirs(tmp, exist_ok=True)
    for i, (st, l) in enumerate(voice_events):
        if not l.get("clip") or not os.path.exists(l["clip"]): continue
        src = l["clip"]
        if l.get("radio"):
            dst = os.path.join(tmp, f"radio_{i}.wav")
            subprocess.run([FF, "-y", "-loglevel", "error", "-i", src, "-af", "highpass=f=350,lowpass=f=3200,acompressor=threshold=-20dB:ratio=4,volume=1.4", dst], check=True)
            src = dst
        voices.append((src, st))
    music = os.path.join(HERE, "..", "episodes", "_music")
    beds = []
    for name, st in bed_starts:
        for base in (os.path.join(ep, "music"), music, r"E:\KulfiKahani_AI_Studio\07_audio\ep02_music"):
            for ext in (".wav", ".mp3"):
                p = os.path.join(base, name + ext)
                if os.path.exists(p): beds.append((p, st)); break
            else: continue
            break
    final = os.path.join(out_dir, f"{tag}.mp4")
    if beds or voices:
        from episode_audio import mix
        wav = os.path.join(out_dir, f"{tag}_audio.wav"); mix(wav, t_global, voices, beds or [(voices[0][0], 0)])
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", vid, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final], check=True)
    else: shutil.copy(vid, final)
    print("saved", final, f"{t_global:.1f}s", flush=True); return final


def actor_image(a, cast, tb, ts, dur, speaking, timed, cache):
    who, view = a["who"], a["view"]
    x, g, h = a.get("x", 960), a.get("ground", 1000), a.get("h", 600)
    if "path" in a:                                                                      # movers
        t0, t1 = a.get("t0", 0), a.get("t1", dur); u = min(1, max(0, (ts - t0) / max(0.01, t1 - t0))); x = a["path"][0] + (a["path"][1] - a["path"][0]) * u
        moving = t0 <= ts <= t1
    else: moving = False
    blink = int(ts * 24) % 70 < 3 and not speaking
    face = mouth_track(speaking, ts - next(st for st, l in timed if l is speaking)) if speaking else ("blink" if blink else "closed")
    if view in ("toward", "away"):                                                       # WALK-AND-TALK in depth: toward camera = the FRONT puppet
        t0, t1 = a.get("t0", 0), a.get("t1", dur); u = min(1, max(0, (ts - t0) / max(0.01, t1 - t0)))   # (lips, blinks, gestures) with stepping legs;
        moving = t0 <= ts <= t1; h = a.get("h0", h) + (h - a.get("h0", h)) * u               # far = small/high, near = big/low
        g = a.get("g0", g) + (g - a.get("g0", g)) * u
        if view == "toward":
            body, _, _, _ = actor_image({k_: v_ for k_, v_ in a.items() if k_ != "path"} | {"view": "front"}, cast, tb, ts, dur, speaking, timed, cache)
            if body is None: return None, x, g, h
        else:
            body = cast.sprite(os.path.join(PUP, who + "_back", "full.png"))
            if body is None: return None, x, g, h
        from dirwalk import split_hem, step_frame
        ph = round(tb % 0.6, 3) if moving else 0.0; key = ("depth", view, id(body), ph)
        if key not in cache:
            arr = np.asarray(body); hk = ("hem", id(body))
            if hk not in cache: cache[hk] = split_hem(arr)
            hm, mid = cache[hk]; cache[key] = Image.fromarray(step_frame(arr, hm, mid, ph, 0.6))
        return cache[key], x, g, h
    if view == "front":
        pz = cast.puppet(who)
        ph = (round(tb / 2.4 * 12) + sum(map(ord, who))) % 12                           # idle sway + breath share ONE 12-step cycle -> ~12 drawings
        pose = {"face": face, "head": round(2.0 * math.sin(2 * math.pi * ph / 12), 1), "dy": round(-2 * math.sin(2 * math.pi * ph / 12 + 1.1), 1)}
        have = cast.poses(who)
        if not speaking and a.get("_spk_x") is not None:                                 # LISTENER leans toward whoever talks (eased in)
            lean = 5.0 * min(1.0, a["_spk_t"] / 0.3); pose["head"] = round(pose["head"] + (-lean if a["_spk_x"] > x else lean))
        mine = [(st, l) for st, l in timed if NAME2DIR.get(l["speaker"]) == who and not l.get("radio")]
        cur = next(((st, l) for st, l in mine if st <= ts < st + l["dur"]), None)
        ended = [ts - (st + l["dur"]) for st, l in mine if st + l["dur"] <= ts]
        tpost = min(ended) if ended else 99.0
        for side, nm in (a.get("pose") or {}).items():
            if nm not in have and nm + "_L" in have:                                    # two-arm HELD object (radio, kite): always in hand
                pose["arm_L"], pose["arm_R"] = nm + "_L", nm + "_R"; continue
            if nm in HOLD or a.get("hold"): pose[side] = nm; continue
            # GESTURE = only while this character talks: anticipation dip -> eased arc up -> pose drawing -> settle after the line
            dside = (pz.layers_alt[nm]["side"] if pz is not None and nm in getattr(pz, "layers_alt", {}) else side[-1])
            bone, sgn = f"arm_upper_{dside}", (1 if dside == "L" else -1)
            if cur:
                tl = ts - cur[0]
                if tl < 0.12: pose[bone] = round(-6 * sgn * tl / 0.12)
                elif tl < 0.30: e = (tl - 0.12) / 0.18; pose[bone] = round(sgn * 32 * (1 - (1 - e) ** 2))
                else: pose[f"arm_{dside}"] = nm
            elif tpost < 0.35: e = tpost / 0.35; pose[bone] = round(sgn * 22 * (1 - e) ** 2)
        if pz is None:
            spr = cast.sprite(os.path.join(PUP, who, "apose.png")); return spr, x, g, h
        key = (who, json.dumps(pose, sort_keys=True))
        if key not in cache:
            try: cache[key] = trim(pz.render(pose))
            except Exception as ex: print("  render fail", who, ex); cache[key] = cast.sprite(os.path.join(PUP, who, "apose.png"))
        return cache[key], x, g, h
    if view == "full":
        bob = round(1 + 0.006 * math.sin(2 * math.pi * round(tb / 2.6 * 12) / 12), 4)
        pp = os.path.join(PUP, who, "parts", f"fullpose_{a['full']}.png")
        if os.path.exists(pp):                                                           # full pose on the RIG canvas: the rig's own mouth + blink
            fface = face if (speaking or face == "blink") else None                       # are laid over it -> lips move in sitting/special poses
            key = ("full", pp, fface, bob)
            if key not in cache:
                im = cast.face_on(who, pp, fface); cache[key] = trim(im.resize((im.width, int(im.height * bob)), Image.LANCZOS))
            return cache[key], x, g, h
        spr = cast.sprite(os.path.join(PUP, who, f"fullpose_{a['full']}.png"))
        if spr is not None:
            key = ("fullspr", who, a["full"], bob)
            if key not in cache: cache[key] = spr.resize((spr.width, int(spr.height * bob)), Image.LANCZOS)
            return cache[key], x, g, h
        return None, x, g, h
    if view == "side" and speaking and not moving and cast.puppet(who) is not None:      # a talker turns to camera so the lips are seen
        return actor_image({**a, "view": "front"}, cast, tb, ts, dur, speaking, timed, cache)
    if view == "side":
        sp, legs = cast.walker(who, a.get("style", "normal"))
        if sp is not None and legs is not None:
            from walk_legs import render_walk
            from walk_scene import stand_frame
            per = legs.period; key = (who, a.get("style"), round(tb % per, 3) if moving else "stand")
            if key not in cache: cache[key] = trim(render_walk(sp, legs, key[2], period=per)[0] if moving else stand_frame(sp, legs, 1.0))
            im = cache[key]
        else:                                                                            # no side rig yet: front drawing stepping
            from dirwalk import split_hem, step_frame
            base = os.path.join(PUP, who, "apose.png"); spr = cast.sprite(base)
            if spr is None: return None, x, g, h
            key = ("step", who, round(tb % 0.6, 3) if moving else 0)
            if key not in cache:
                arr = np.asarray(spr); hm, mid = split_hem(arr); cache[key] = Image.fromarray(step_frame(arr, hm, mid, key[2] if moving else 0.0, 0.6))
            im = cache[key]
        if a.get("flip"): im = ImageOps.mirror(im)
        return im, x, g, h
    if view == "sheru":
        d = os.path.join(PUP, "sheru")
        if a.get("pose") == "run":
            frames = [f for f in ("run_1_cut.png", "run_2_cut.png", "run_3_cut.png", "run_2_cut.png") if os.path.exists(os.path.join(d, f))]
            if frames: return cast.sprite(os.path.join(d, frames[int(tb * 8) % len(frames)])), x, g, h
        nm = {"sit_front": "sit_front_cut.png", "crown": "wearing_crown_cut.png"}.get(a.get("pose"), "sit_front_cut.png")
        spr = cast.sprite(os.path.join(d, nm)) or cast.sprite(r"E:\KulfiKahani_AI_Studio\03_episode01_art\masters\sheru.png")
        return spr, x, g, h
    if view == "img":                                                                    # a single drawing (flashback cast): gentle breathing
        spr = cast.sprite(os.path.join(PUP, a["img"]))
        if spr is None: return None, x, g, h
        bob = round(1 + 0.008 * math.sin(2 * math.pi * round(tb / 2.8 * 12) / 12), 4); key = ("img", a["img"], bob)
        if key not in cache: cache[key] = spr.resize((spr.width, int(spr.height * bob)), Image.LANCZOS)
        return cache[key], x, g, h
    if view == "prop":
        for p in (os.path.join(PUP, "props", a["prop"] + ".png"), os.path.join(PUP, "props", a["prop"] + "_cut.png")):
            spr = cast.sprite(p)
            if spr is not None:
                if a.get("roll") and moving: spr = spr.rotate(-360 * (ts - a.get("t0", 0)) / 1.5, resample=Image.BICUBIC, expand=True)
                return spr, x, g, h
    return None, x, g, h


if __name__ == "__main__":
    a = sys.argv[1:]; render_scene(a[0], a[1], a[2], "--preview" in a)
