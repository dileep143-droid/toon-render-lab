"""Motion capture from Creative-Commons YouTube clips (MediaPipe) -> motion_library/data/<clip>.json -> lib_mocap.apply_clip.

LEGAL RULE: only videos whose YouTube licence is "Creative Commons Attribution" are used (yt-dlp `license` field, checked per
video before download). Downloaded video (motion_library/src) and captured data (motion_library/data) stay LOCAL / private
Kaggle dataset - never commit them. Credits (title, channel, URL, licence) go to motion_library/CREDITS.md.

  python mocap_youtube.py search                 # CC-filtered search per need -> motion_library/candidates.json
  python mocap_youtube.py meta <id> [<id> ...]   # licence / duration / title of chosen videos
  python mocap_youtube.py fetch                  # download the segments listed in motion_library/clips.json (licence re-checked)
  python mocap_youtube.py capture [clip ...]     # MediaPipe pose + hands + face -> motion_library/data/<clip>.json
  python mocap_youtube.py credits                # rewrite CREDITS.md from clips.json
"""
import json, os, sys, subprocess, math, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "motion_library")
SRC = os.path.join(LIB, "src"); DATA = os.path.join(LIB, "data"); MODELS = os.path.join(LIB, "models")
FFMPEG = r"C:\Users\goddu\.gemini\antigravity\scratch\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
CC_FILTER = "EgIwAQ%253D%253D"       # YouTube results filter: Creative Commons
CC_OK = "creative commons attribution"

NEEDS = {
    "counting": ["counting coins hands", "counting money hands close up", "counting candies"],
    "pick_place": ["picking up small objects table hands", "placing objects on table hands"],
    "child_walk": ["child walking", "kid walking full body"],
    "child_run": ["child running", "kid running park"],
    "sit_stand": ["elderly woman sitting down standing up chair", "sit to stand exercise elderly", "old woman sitting on chair"],
    "carry_plate": ["carrying plate with both hands", "waiter carrying plate walking"],
    "namaste": ["namaste greeting", "namaste gesture"],
    "head_wobble": ["indian head wobble", "indian head shake talking"],
    "clap": ["clapping hands", "person clapping"],
    "wave": ["waving hand hello", "person waving goodbye"],
    "point": ["pointing finger gesture", "person pointing"],
    "scratch_head": ["scratching head confused", "confused gesture"],
    "laugh": ["person laughing", "laughing out loud"],
    "cry": ["crying wiping tears", "woman crying"],
    "eat_hand": ["eating with hand indian", "eating rice with hand"],
    "sweep": ["sweeping floor broom", "sweeping with broom"],
    "bhangra": ["bhangra steps", "bhangra dance tutorial"],
    "garba": ["garba steps", "garba dance tutorial"],
}


def ydl(opts=None):
    import yt_dlp
    o = {"quiet": True, "no_warnings": True, "skip_download": True}
    if os.environ.get("YT_COOKIES_EDGE"): o["cookiesfrombrowser"] = ("edge",)
    o.update(opts or {})
    return yt_dlp.YoutubeDL(o)


def search():
    out = {}
    with ydl({"extract_flat": True, "playlistend": 12}) as y:
        for need, qs in NEEDS.items():
            seen = []
            for q in qs:
                url = f"https://www.youtube.com/results?search_query={urllib.request.quote(q)}&sp={CC_FILTER}"
                try:
                    info = y.extract_info(url, download=False)
                except Exception as ex:
                    print("ERR", need, q, ex); continue
                for e in (info.get("entries") or [])[:12]:
                    if not e or e.get("id") in [s["id"] for s in seen]: continue
                    d = e.get("duration") or 0
                    seen.append({"id": e.get("id"), "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"), "duration": d, "q": q})
            out[need] = seen
            print(need, len(seen))
            for s in seen[:10]: print("   ", s["id"], int(s["duration"] or 0), "s |", (s["title"] or "")[:70], "|", s["channel"])
    json.dump(out, open(os.path.join(LIB, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def meta(ids):
    res = {}
    with ydl() as y:
        for i in ids:
            try:
                info = y.extract_info(f"https://www.youtube.com/watch?v={i}", download=False)
            except Exception as ex:
                print("ERR", i, str(ex)[:120]); continue
            r = {k: info.get(k) for k in ("id", "title", "channel", "uploader", "license", "duration", "width", "height", "webpage_url")}
            res[i] = r
            print(i, "| LIC:", r["license"], "|", r["duration"], "s |", (r["title"] or "")[:60], "|", r["channel"])
    return res


def load_clips():
    return json.load(open(os.path.join(LIB, "clips.json"), encoding="utf-8"))


def fetch(only=None):
    import yt_dlp
    from yt_dlp.utils import download_range_func
    os.makedirs(SRC, exist_ok=True)
    if os.path.exists(FFMPEG): os.environ["PATH"] = os.path.dirname(FFMPEG) + os.pathsep + os.environ["PATH"]
    clips = load_clips()
    for c in clips["clips"]:
        if only and c["name"] not in only: continue
        dst = os.path.join(SRC, c["name"] + ".mp4")
        if os.path.exists(dst): print("have", c["name"]); continue
        m = meta([c["id"]]).get(c["id"])
        if not m or CC_OK not in (m.get("license") or "").lower():
            print("SKIP (licence is not CC-BY):", c["name"], m and m.get("license")); c["licence_ok"] = False; continue
        c.update({"title": m["title"], "channel": m["channel"] or m["uploader"], "license": m["license"], "url": m["webpage_url"], "licence_ok": True})
        a, b = c["start"], c["end"]
        opts = {"quiet": True, "no_warnings": True, "format": "136/bv*[height<=720][ext=mp4]/bv*[height<=720]/b[height<=720]",   # video only: no audio needed
                "outtmpl": os.path.join(SRC, c["name"] + ".%(ext)s"), "download_ranges": download_range_func(None, [(a, b)]),
                "force_keyframes_at_cuts": True, "merge_output_format": "mp4", "ffmpeg_location": os.path.dirname(FFMPEG)}
        if os.environ.get("YT_COOKIES_EDGE"): opts["cookiesfrombrowser"] = ("edge",)
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([c["url"]])
        print("got", c["name"], os.path.exists(dst))
    json.dump(clips, open(os.path.join(LIB, "clips.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    credits()


def credits():
    clips = load_clips()
    L = ["# Motion library credits", "",
         "Human movement in these clips was captured (MediaPipe landmarks only, no footage reused) from the following YouTube videos,",
         "each published under the **Creative Commons Attribution licence (reuse allowed)**, CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/).",
         "The downloaded videos and the captured data are kept private and are not part of this repository.", "",
         "| Clip | Video title | Channel | Link | Licence | Segment used |", "|---|---|---|---|---|---|"]
    for c in clips["clips"]:
        if not c.get("licence_ok"): continue
        t = (c.get("title") or "").replace("|", "/")
        L.append(f"| {c['name']} | {t} | {c.get('channel')} | {c.get('url')} | {c.get('license')} | {c['start']:.1f}-{c['end']:.1f} s |")
    open(os.path.join(LIB, "CREDITS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("CREDITS.md rows:", sum(1 for c in clips["clips"] if c.get("licence_ok")))


# ------------------------------------------------------------------------------------------------------------------
# capture
# ------------------------------------------------------------------------------------------------------------------
MODEL_URLS = {
    "pose": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
    "hand": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "face": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
}


def model(k):
    os.makedirs(MODELS, exist_ok=True)
    p = os.path.join(MODELS, os.path.basename(MODEL_URLS[k]))
    if not os.path.exists(p): urllib.request.urlretrieve(MODEL_URLS[k], p)
    return p


class OneEuro:
    def __init__(self, fps, mincut=1.0, beta=0.3, dcut=1.0):
        self.f, self.mc, self.b, self.dc = fps, mincut, beta, dcut; self.x = None; self.dx = 0.0

    @staticmethod
    def _a(cut, f):
        tau = 1.0 / (2 * math.pi * cut); return 1.0 / (1.0 + tau * f)

    def __call__(self, x):
        if x is None: return None
        if self.x is None: self.x = x; return x
        dx = (x - self.x) * self.f
        self.dx = self.dx + self._a(self.dc, self.f) * (dx - self.dx)
        cut = self.mc + self.b * abs(self.dx)
        self.x = self.x + self._a(cut, self.f) * (x - self.x)
        return self.x


def smooth_track(frames, fps, mincut=1.2, beta=0.4):
    """frames: list of (list of [x,y,z,...] or None). One-Euro per coordinate; gaps (<= 6 frames) linearly filled."""
    n = len(frames)
    # fill short gaps
    i = 0
    while i < n:
        if frames[i] is None:
            j = i
            while j < n and frames[j] is None: j += 1
            if 0 < i and j < n and j - i <= 6:
                a, b = frames[i - 1], frames[j]
                for k in range(i, j):
                    t = (k - i + 1) / (j - i + 1)
                    frames[k] = [[pa + (pb - pa) * t for pa, pb in zip(A, B)] for A, B in zip(a, b)]
            i = j
        else:
            i += 1
    filt = None; out = []
    for fr in frames:
        if fr is None: filt = None; out.append(None); continue
        if filt is None: filt = [[OneEuro(fps, mincut, beta) for _ in p] for p in fr]
        out.append([[round(filt[a][b](v), 5) for b, v in enumerate(p)] for a, p in enumerate(fr)])
    return out


def fix_lr_swaps(world):
    """pose world landmarks: if the left/right body halves jump to swapped positions between frames, swap them back."""
    PAIRS = [(11, 12), (13, 14), (15, 16), (17, 18), (19, 20), (21, 22), (23, 24), (25, 26), (27, 28), (29, 30), (31, 32), (1, 4), (2, 5), (3, 6), (7, 8), (9, 10)]
    prev = None; nfix = 0
    for f, fr in enumerate(world):
        if fr is None: continue
        if prev is not None:
            keep = sum(math.dist(fr[a][:3], prev[a][:3]) + math.dist(fr[b][:3], prev[b][:3]) for a, b in PAIRS[:10])
            swap = sum(math.dist(fr[b][:3], prev[a][:3]) + math.dist(fr[a][:3], prev[b][:3]) for a, b in PAIRS[:10])
            if swap < 0.6 * keep:
                for a, b in PAIRS: fr[a], fr[b] = fr[b], fr[a]
                nfix += 1
        prev = fr
    return nfix


def capture(names=None):
    os.makedirs(DATA, exist_ok=True)
    clips = load_clips()
    for c in clips["clips"]:
        if names and c["name"] not in names: continue
        if not c.get("licence_ok"): print("skip (licence)", c["name"]); continue
        src = os.path.join(SRC, c["name"] + ".mp4")
        if not os.path.exists(src): print("no video", c["name"]); continue
        capture_video(src, c["name"], c.get("parts", ["body", "hands", "face"]), {k: c.get(k) for k in ("url", "title", "channel", "license", "start", "end")}, DATA)


# landmarks each motion kind needs to be clearly visible (for scoring candidate clips / windows)
NEED_LM = {"full": [11, 12, 23, 24, 25, 26, 27, 28], "upper": [11, 12, 13, 14, 15, 16], "hands": [], "face": [0, 7, 8]}


def quality(data, kind, a=0, b=None):
    """0..1 score of a captured window: detection rate x visibility of the needed landmarks x hand/face coverage x (1 - jitter)"""
    PW = data["pose_world"][a:b]; n = max(1, len(PW))
    det = sum(1 for f in PW if f) / n
    lm = NEED_LM.get(kind, [])
    vis = 1.0
    if lm:
        vv = [min(f[i][3] for i in lm) for f in PW if f]
        vis = sum(vv) / len(vv) if vv else 0.0
    s = det * vis
    if kind == "hands":
        hl = data.get("hand_L", [])[a:b]; hr = data.get("hand_R", [])[a:b]
        s = (sum(1 for x in hl if x) + sum(1 for x in hr if x)) / (2 * max(1, len(hl)))
    if kind == "face":
        bs = data.get("blendshapes", [])[a:b]; s *= sum(1 for x in bs if x) / max(1, len(bs))
    # motion energy (a clip where nobody moves is useless): mean wrist/ankle speed
    sp = 0.0; m = 0
    for f0, f1 in zip(PW, PW[1:]):
        if f0 and f1:
            sp += sum(math.dist(f0[i][:3], f1[i][:3]) for i in (15, 16, 27, 28)); m += 1
    energy = sp / max(1, m) * data["fps"]
    return round(s * min(1.0, energy / 0.15 + 0.2), 4)


def best_window(data, kind, seconds=10.0):
    """crop a long capture to its best window (by quality) in place; returns (a, b) frame range"""
    n = data["frames"]; w = int(seconds * data["fps"])
    if n <= w: return 0, n
    best, ba = -1, 0
    for a in range(0, n - w + 1, max(1, int(data["fps"]))):
        q = quality(data, kind, a, a + w)
        if q > best: best, ba = q, a
    for k in ("pose_world", "pose_image", "hand_L", "hand_R", "hand_L_image", "hand_R_image", "blendshapes", "head_ypr"):
        if k in data and isinstance(data[k], list): data[k] = data[k][ba:ba + w]
    data["frames"] = w; data["window"] = [round(ba / data["fps"], 2), round((ba + w) / data["fps"], 2)]
    return ba, ba + w


def capture_video(src, name, parts, meta, out_dir, max_seconds=None):
    import cv2, mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision as V
    os.makedirs(out_dir, exist_ok=True)
    if True:
        c = dict(meta or {}); c["name"] = name
        cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if not fps or fps > 120 or fps < 5: fps = 30.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        RM = V.RunningMode.VIDEO
        pose = V.PoseLandmarker.create_from_options(V.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model("pose")), running_mode=RM,
                                                     num_poses=1, min_pose_detection_confidence=0.5, min_tracking_confidence=0.5))
        hand = V.HandLandmarker.create_from_options(V.HandLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model("hand")), running_mode=RM,
                                                    num_hands=2, min_hand_detection_confidence=0.4, min_tracking_confidence=0.4)) if "hands" in parts else None
        face = V.FaceLandmarker.create_from_options(V.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=model("face")), running_mode=RM,
                                                    num_faces=1, output_face_blendshapes=True, output_facial_transformation_matrixes=True)) if "face" in parts else None
        P_img, P_w, HL, HR, HLw, HRw, BS, HM = [], [], [], [], [], [], [], []
        i = 0
        while True:
            ok, img = cap.read()
            if not ok: break
            if max_seconds and i >= max_seconds * fps: break
            if img.shape[0] > 720:                                   # keep CPU cost bounded
                s = 720 / img.shape[0]; img = cv2.resize(img, (int(img.shape[1] * s), 720))
            ts = int(i * 1000 / fps)
            mi = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            r = pose.detect_for_video(mi, ts)
            if r.pose_world_landmarks:
                P_w.append([[l.x, l.y, l.z, l.visibility] for l in r.pose_world_landmarks[0]])
                P_img.append([[l.x, l.y, l.z, l.visibility] for l in r.pose_landmarks[0]])
            else:
                P_w.append(None); P_img.append(None)
            hl = hr = hlw = hrw = None
            if hand:
                rh = hand.detect_for_video(mi, ts)
                for k, hd in enumerate(rh.handedness):
                    pts = [[l.x, l.y, l.z] for l in rh.hand_landmarks[k]]; wpts = [[l.x, l.y, l.z] for l in rh.hand_world_landmarks[k]]
                    # MediaPipe handedness assumes a mirrored (selfie) image; for normal video "Left" means the person's RIGHT hand.
                    # Rather than trust it, assign each hand to the nearer pose wrist (15 = person's left, 16 = person's right).
                    side = None
                    if P_img[-1] is not None:
                        wl, wr = P_img[-1][15], P_img[-1][16]
                        dl = math.dist(pts[0][:2], wl[:2]); dr = math.dist(pts[0][:2], wr[:2])
                        side = "L" if dl < dr else "R"
                    else:
                        side = "R" if hd[0].category_name == "Left" else "L"
                    if side == "L" and hl is None: hl, hlw = pts, wpts
                    elif side == "R" and hr is None: hr, hrw = pts, wpts
            HL.append(hl); HR.append(hr); HLw.append(hlw); HRw.append(hrw)
            if face:
                rf = face.detect_for_video(mi, ts)
                BS.append({b.category_name: round(b.score, 4) for b in rf.face_blendshapes[0]} if rf.face_blendshapes else None)
                # head rotation (camera space: x right, y up, z towards the camera) -> yaw/pitch/roll in degrees
                hm = None
                if rf.facial_transformation_matrixes:
                    import numpy as np
                    M3 = np.array(rf.facial_transformation_matrixes[0])[:3, :3]
                    yaw = math.degrees(math.atan2(-M3[2, 0], math.hypot(M3[0, 0], M3[1, 0])))
                    pitch = math.degrees(math.atan2(M3[2, 1], M3[2, 2]))
                    roll = math.degrees(math.atan2(M3[1, 0], M3[0, 0]))
                    hm = [[yaw, pitch, roll]]
                HM.append(hm)
            i += 1
        cap.release()
        import copy
        orig = copy.deepcopy(P_w)
        nfix = fix_lr_swaps(P_w)
        if nfix > 0.08 * max(1, i):            # flip-flopping (typical for back views): the fixer is guessing, keep the raw track
            P_w = orig; nfix = -nfix
        det = sum(1 for x in P_w if x is not None)
        data = {"name": c["name"], "fps": fps, "frames": i, "width": W, "height": H, "source": {k: c.get(k) for k in ("url", "title", "channel", "license", "start", "end")},
                "lr_swaps_fixed": nfix, "pose_detected": det,
                "pose_world": smooth_track(P_w, fps), "pose_image": smooth_track(P_img, fps, 1.5, 0.5),
                "hand_L": smooth_track(HLw, fps, 1.5, 0.6), "hand_R": smooth_track(HRw, fps, 1.5, 0.6),
                "hand_L_image": HL, "hand_R_image": HR,
                "hand_detected": {"L": sum(1 for x in HL if x), "R": sum(1 for x in HR if x)}}
        if face:
            # smooth blendshapes too
            keys = sorted({k for b in BS if b for k in b})
            fl = {k: OneEuro(fps, 2.0, 0.5) for k in keys}; out = []
            for b in BS:
                out.append(None if b is None else {k: round(max(0.0, fl[k](b.get(k, 0.0))), 4) for k in keys})
            data["blendshapes"] = out; data["face_detected"] = sum(1 for b in BS if b)
            hm = smooth_track(HM, fps, 1.5, 0.5)
            data["head_ypr"] = [None if h is None else [round(v, 2) for v in h[0]] for h in hm]
        json.dump(data, open(os.path.join(out_dir, c["name"] + ".json"), "w", encoding="utf-8"))
        print("captured", c["name"], "frames", i, "fps", round(fps, 2), "pose", det, "hands", data["hand_detected"], "face", data.get("face_detected"), "lr fixes", nfix, flush=True)
        return data


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    if cmd == "search": search()
    elif cmd == "meta": meta(sys.argv[2:])
    elif cmd == "fetch": fetch(sys.argv[2:] or None)
    elif cmd == "capture": capture(sys.argv[2:] or None)
    elif cmd == "credits": credits()
