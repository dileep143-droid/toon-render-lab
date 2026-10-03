"""qa_checks.py - cheap automatic checks on rendered frames / the finished MP4 (no AI, numpy only).

    import qa_checks as QA
    rep = QA.run_qa("ep01.mp4", plan={"actors": [{"who": "dadi", "box": [0.7, 0.3, 0.95, 0.95], "start": 0, "end": 8}],
                                      "motion": [{"start": 2, "end": 6}]},
                    plates=bg_frame_or_callable, mouth={"dadi": [0,0,1,1,...]}, audio="ep01.wav")
    print(QA.format_report(rep))          # rep = {"ok": bool, "issues": [{"check","t","who","msg"}...], "stats": {...}}

Checks (each is also a function you can call alone; every one returns a list of issue dicts):
  blank_frames        black / flat frames (mean luma or contrast too low), except at the ends where a fade is allowed
  missing_character   planned actor box has no foreground (pixels equal to the plate) -> the character is not drawn there
  framing_issues      character bbox (from alpha, or from the frame-vs-plate difference) partly outside the frame, head within 5% of the top edge
  frozen_frames       identical consecutive frames for longer than min_dur where motion is planned
  av_length           audio vs video duration mismatch
  lipsync_issues      mouth-open while the audio is silent / mouth-closed while the audio is loud (mouth track vs audio RMS)
Frames are uint8 (H,W,3) RGB.  Times are seconds; boxes are fractions of the frame (x0,y0,x1,y1) or pixels if any value > 1."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tk_core import FPS, W, H, read_video, probe_duration, lum


def _issue(check, t, msg, who=None, **extra):
    d = {"check": check, "t": round(float(t), 3), "msg": msg}
    if who: d["who"] = who
    d.update(extra); return d


def _px_box(box, w, h):
    x0, y0, x1, y1 = box
    if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.5: x0, x1, y0, y1 = x0 * w, x1 * w, y0 * h, y1 * h
    return int(max(0, x0)), int(max(0, y0)), int(min(w, x1)), int(min(h, y1))


def _merge_runs(issues, fps, gap=2):
    """collapse consecutive per-frame issues of one kind into a single issue with t and t_end"""
    out = []
    for it in sorted(issues, key=lambda d: (d["check"], d.get("who", ""), d["msg"].split(" (")[0].split(" for ")[0], d["t"])):
        p = out[-1] if out else None
        if p and p["check"] == it["check"] and p.get("who") == it.get("who") and p["msg"].split(" (")[0].split(" for ")[0] == it["msg"].split(" (")[0].split(" for ")[0] and it["t"] - p.get("t_end", p["t"]) <= gap / fps + 1e-6:
            p["t_end"] = it["t"]
        else: out.append(dict(it))
    return out


# ============================================================================================================ blank / black frames
def frame_stats(frame):
    g = lum(frame); return float(g.mean()), float(g.std())


def blank_frames(frames, fps=FPS, dark=10.0, flat=3.0, allow_edge=0.0):
    """black (mean luma < dark) or flat (std < flat) frames. allow_edge = seconds at the start/end where a fade-from/to-black is fine."""
    n = len(frames); issues = []
    for i, f in enumerate(frames):
        t = i / fps
        if t < allow_edge or t > n / fps - allow_edge: continue
        m, s = frame_stats(f[::4, ::4])
        if m < dark: issues.append(_issue("blank_frames", t, f"black frame (mean luma {m:.1f})"))
        elif s < flat: issues.append(_issue("blank_frames", t, f"flat frame (contrast {s:.1f}, mean {m:.0f})"))
    return _merge_runs(issues, fps)


# ============================================================================================================ character presence / framing
def _plate_at(plates, t, i):
    if plates is None: return None
    if callable(plates): return plates(t)
    if isinstance(plates, np.ndarray) and plates.ndim == 3: return plates
    return plates[min(i, len(plates) - 1)]


def foreground_mask(frame, plate, thr=24):
    """pixels that differ from the empty plate (the characters/props that were drawn on top)"""
    return (np.abs(frame.astype(np.int16) - plate.astype(np.int16)).sum(-1) > thr)


def missing_character(frames, plate, actors, fps=FPS, min_cover=0.04, thr=24, step=3):
    """actors = [{"who", "box", "start", "end"}]. A box whose foreground coverage stays below min_cover is an empty spot -> the character is missing.
    plate: empty background (array) or callable t -> frame.  Samples every `step` frames."""
    issues = []
    for a in actors:
        i0, i1 = int(a.get("start", 0) * fps), min(len(frames), int(a.get("end", len(frames) / fps) * fps) + 1)
        for i in range(i0, i1, step):
            pl = _plate_at(plate, i / fps, i)
            if pl is None: continue
            x0, y0, x1, y1 = _px_box(a["box"], frames[i].shape[1], frames[i].shape[0])
            if x1 <= x0 or y1 <= y0: continue
            cov = float(foreground_mask(frames[i][y0:y1, x0:x1], pl[y0:y1, x0:x1], thr).mean())
            if cov < min_cover: issues.append(_issue("missing_character", i / fps, f"{a['who']} not drawn in its box (coverage {cov:.1%})", a["who"], coverage=round(cov, 4)))
    return _merge_runs(issues, fps, gap=step + 1)


def framing_issues(boxes, size=(W, H), head_margin=0.05, who=None, fps=FPS, shot="close", allow_out=2, t0=0.0):
    """boxes = per-frame character bbox (x0,y0,x1,y1) in pixels (or None) - from bbox_of_alpha of the sprite, or `fg_bbox`.
    Flags: partly outside the frame (more than allow_out px), head (bbox top) closer than head_margin*H to the top edge, and in a 'full' shot feet cut at the bottom."""
    w, h = size; issues = []
    for i, b in enumerate(boxes):
        if b is None: continue
        x0, y0, x1, y1 = b; t = t0 + i / fps
        if x0 < -allow_out or x1 > w + allow_out: issues.append(_issue("framing", t, "character partly outside the frame sideways", who))
        elif shot == "full" and y1 > h + allow_out: issues.append(_issue("framing", t, "feet cut off at the bottom of a full shot", who))
        if y0 < head_margin * h - allow_out: issues.append(_issue("framing", t, f"head within {head_margin:.0%} of the top edge (top at {y0:.0f}px)", who))
    return _merge_runs(issues, fps, gap=3)


def fg_bbox(frame, plate, thr=24, min_px=200, box=None):
    """bbox of the foreground (difference from plate), optionally within a search box -> (x0,y0,x1,y1) or None"""
    m = foreground_mask(frame, plate, thr)
    if box is not None:
        x0, y0, x1, y1 = _px_box(box, m.shape[1], m.shape[0]); mm = np.zeros_like(m); mm[y0:y1, x0:x1] = m[y0:y1, x0:x1]; m = mm
    if m.sum() < min_px: return None
    ys, xs = np.nonzero(m); return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def edge_contact(frame, plate, thr=24, band=3, min_px=40):
    """fallback framing test without alpha: foreground pixels touching the frame edge (a character cut by the border). returns the edges hit"""
    m = foreground_mask(frame, plate, thr); hit = []
    if m[:band].sum() > min_px: hit.append("top")
    if m[-band:].sum() > min_px: hit.append("bottom")
    if m[:, :band].sum() > min_px: hit.append("left")
    if m[:, -band:].sum() > min_px: hit.append("right")
    return hit


# ============================================================================================================ frozen frames
def frame_diffs(frames):
    """mean abs difference between consecutive frames (sub-sampled)"""
    s = [f[::6, ::6].astype(np.int16) for f in frames]
    return np.array([np.abs(s[i] - s[i - 1]).mean() for i in range(1, len(s))] if len(s) > 1 else [0.0])


def frozen_frames(frames, fps=FPS, motion=None, min_dur=0.6, eps=0.02):
    """runs of identical frames longer than min_dur. motion = [(start,end)...] windows where movement is planned (None = whole video)."""
    d = frame_diffs(frames); issues = []; run = 0; start = 0
    def planned(t): return motion is None or any(a <= t <= b for a, b in motion)
    for i, v in enumerate(list(d) + [1e9]):
        if v < eps: run += 1; start = start if run > 1 else i
        else:
            if run and run / fps >= min_dur:
                t0 = start / fps; t1 = (start + run) / fps
                if planned((t0 + t1) / 2): issues.append(_issue("frozen_frames", t0, f"picture frozen for {run / fps:.1f}s while motion is planned", t_end=round(t1, 3)))
            run = 0
    return issues


# ============================================================================================================ audio / video length
def av_length(video, audio=None, tol=0.15):
    """video container vs audio duration. audio=None -> uses the audio stream of the video file itself (container vs the longest stream is not split by ffmpeg -i,
    so pass the separate audio path when you have one)."""
    dv = probe_duration(video); issues = []
    if dv is None: return [_issue("av_length", 0, "cannot read video duration")]
    if audio:
        da = probe_duration(audio)
        if da is not None and abs(da - dv) > tol: issues.append(_issue("av_length", min(da, dv), f"audio {da:.2f}s vs video {dv:.2f}s (difference {da - dv:+.2f}s)", delta=round(da - dv, 3)))
    return issues


# ============================================================================================================ lip-sync (mouth state vs audio RMS)
def lipsync_issues(mouth, rms, fps=FPS, who=None, loud=0.02, quiet=0.006, open_thr=0.35, min_dur=0.25, offset=0.0):
    """mouth: per-frame openness 0..1 (or 0/1 state) for ONE speaker; rms: per-frame audio loudness (audio_mix.rms_track).
    mouth open while the audio is silent for >= min_dur, or mouth closed while the audio is loud for >= min_dur.
    For a track with several speakers, pass only that speaker's voice audio. offset (s) shifts the mouth track against the audio."""
    mouth = np.asarray(mouth, np.float32); rms = np.asarray(rms, np.float32); sh = int(round(offset * fps))
    if sh > 0: mouth = np.concatenate([np.zeros(sh, np.float32), mouth])
    elif sh < 0: mouth = mouth[-sh:]
    n = min(len(mouth), len(rms)); mouth, rms = mouth[:n], rms[:n]; need = max(1, int(min_dur * fps)); issues = []
    # smooth the rms by a few frames so the gaps between syllables do not count as silence
    k = max(1, fps // 6); sm = np.convolve(rms, np.ones(k) / k, mode="same")
    for name, bad, msg in (("mouth_open_silent", (mouth > open_thr) & (sm < quiet), "mouth open while silent"),
                           ("mouth_closed_speaking", (mouth <= open_thr) & (sm > loud), "mouth closed while speaking")):
        run = 0
        for i in range(n + 1):
            if i < n and bad[i]: run += 1
            else:
                if run >= need: issues.append(_issue("lipsync", (i - run) / fps, f"{msg} for {run / fps:.1f}s", who, kind=name, t_end=round(i / fps, 3)))
                run = 0
    return issues


# ============================================================================================================ one call
def run_qa(video, plan=None, plates=None, mouth=None, audio=None, rms=None, fps=FPS, size=None, every=1, max_frames=None, fade_edge=0.6):
    """Run every check that has its inputs.  video: path or list of frames.
    plan = {"actors": [{who, box, start, end, shot?}], "motion": [(start,end)], "min_cover": .04, "head_margin": .05}
    mouth = {who: per-frame openness};  rms = {who: per-frame rms} or one array for all (else the audio= file's rms is used)."""
    plan = plan or {}; frames = read_video(video, size=size, every=every, max_frames=max_frames) if isinstance(video, (str, os.PathLike)) else list(video)
    fps_eff = fps / every; issues = []; stats = {"frames": len(frames), "seconds": round(len(frames) / fps_eff, 2)}
    issues += blank_frames(frames, fps_eff, allow_edge=fade_edge)
    if plates is not None and plan.get("actors"):
        issues += missing_character(frames, plates, plan["actors"], fps_eff, min_cover=plan.get("min_cover", 0.04))
        for a in plan["actors"]:                                                                                             # framing from the foreground inside the actor's search box
            boxes = []
            i0, i1 = int(a.get("start", 0) * fps_eff), min(len(frames), int(a.get("end", len(frames) / fps_eff) * fps_eff) + 1)
            for i in range(i0, i1, 3):
                pl = _plate_at(plates, i / fps_eff, i); boxes.append(fg_bbox(frames[i], pl, box=a.get("search", a["box"])) if pl is not None else None)
            issues += framing_issues(boxes, (frames[0].shape[1], frames[0].shape[0]), plan.get("head_margin", 0.05), a["who"], fps_eff / 3, a.get("shot", "close"), t0=i0 / fps_eff)
    if plan.get("motion") is not None or plan.get("expect_motion"):
        issues += frozen_frames(frames, fps_eff, plan.get("motion"), plan.get("min_frozen", 0.6))
    if isinstance(video, (str, os.PathLike)): issues += av_length(str(video), audio)
    if mouth:
        from audio_mix import rms_track
        for who, mt in mouth.items():
            r = rms.get(who) if isinstance(rms, dict) else rms
            if r is None and audio: r = rms_track(audio, int(fps_eff))
            if r is not None: issues += lipsync_issues(mt, r, int(fps_eff), who)
    stats["issues"] = len(issues)
    return {"ok": not issues, "issues": sorted(issues, key=lambda d: d["t"]), "stats": stats}


def format_report(rep):
    lines = [f"QA: {'PASS' if rep['ok'] else 'FAIL'} - {rep['stats']['issues']} issue(s) in {rep['stats']['seconds']} s"]
    for it in rep["issues"]:
        span = f"{it['t']:.2f}-{it['t_end']:.2f}s" if "t_end" in it else f"{it['t']:.2f}s"
        lines.append(f"  [{it['check']}] {span} {it.get('who', '')} {it['msg']}")
    return "\n".join(lines)


CHECKS = {"blank_frames": blank_frames, "missing_character": missing_character, "framing": framing_issues, "frozen_frames": frozen_frames, "av_length": av_length, "lipsync": lipsync_issues}

if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="QA a rendered episode"); ap.add_argument("video"); ap.add_argument("--audio"); ap.add_argument("--plan", help="plan json (actors/motion)")
    a = ap.parse_args(); pl = json.load(open(a.plan)) if a.plan else None
    rep = run_qa(a.video, pl, audio=a.audio); print(format_report(rep)); sys.exit(0 if rep["ok"] else 1)
