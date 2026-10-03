import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, qa_checks as QA, audio_mix as AM

BG = T.make_background("village_day"); FPS = 24


def with_block(bg, x0, y0, x1, y1, col=(200, 40, 40)):
    f = bg.copy(); f[y0:y1, x0:x1] = col; return f


def test_blank_and_flat_detected_fade_edges_allowed():
    fr = [BG.copy() for _ in range(48)]
    for i in range(10, 20): fr[i] = np.zeros_like(BG)
    for i in range(30, 36): fr[i] = np.full_like(BG, 128)
    for i in range(0, 4): fr[i] = np.zeros_like(BG)
    iss = QA.blank_frames(fr, FPS, allow_edge=0.3)
    assert len(iss) == 2 and abs(iss[0]["t"] - 10 / 24) < 1e-2 and iss[0]["t_end"] > iss[0]["t"] and "black" in iss[0]["msg"] and "flat" in iss[1]["msg"]
    assert not QA.blank_frames([BG] * 10, FPS)


def test_missing_character_only_when_box_is_empty():
    box = [0.4, 0.3, 0.6, 0.9]
    fr = [with_block(BG, 520, 250, 700, 600) if i < 30 else BG.copy() for i in range(60)]
    iss = QA.missing_character(fr, BG, [{"who": "dadi", "box": box, "start": 0, "end": 2.4}], FPS)
    assert len(iss) == 1 and iss[0]["who"] == "dadi" and iss[0]["t"] >= 30 / 24 - 0.2
    assert not QA.missing_character(fr[:30], BG, [{"who": "dadi", "box": box, "start": 0, "end": 1.2}], FPS)
    # pixel boxes work as well as fractions
    assert QA.missing_character(fr, BG, [{"who": "x", "box": [100, 100, 200, 200], "start": 0, "end": 2}], FPS)


def test_framing_flags_cropped_head_and_side():
    boxes = [(500, 200, 700, 600)] * 5 + [(500, 10, 700, 600)] * 5 + [(-60, 200, 100, 600)] * 5 + [(500, 100, 700, 800)] * 5
    iss = QA.framing_issues(boxes, (1280, 720), who="maa", fps=FPS, shot="full")
    kinds = [i["msg"] for i in iss]; assert any("top edge" in k for k in kinds) and any("sideways" in k for k in kinds) and any("feet" in k for k in kinds)
    assert not QA.framing_issues([(500, 120, 700, 700)] * 5, (1280, 720), fps=FPS, shot="full")
    assert not QA.framing_issues([(500, 120, 700, 800)] * 5, (1280, 720), fps=FPS, shot="close")          # close shots may crop below the chest


def test_fg_bbox_and_edge_contact():
    f = with_block(BG, 300, 100, 500, 400); assert QA.fg_bbox(f, BG) == (300, 100, 500, 400)
    assert QA.fg_bbox(BG.copy(), BG) is None and QA.edge_contact(f, BG) == []
    assert "right" in QA.edge_contact(with_block(BG, 1100, 100, 1280, 400), BG)


def test_frozen_only_when_motion_planned():
    fr = [with_block(BG, 100 + i * 4, 200, 300 + i * 4, 500) for i in range(20)] + [with_block(BG, 200, 200, 400, 500)] * 30 + [with_block(BG, 100 + i * 4, 200, 300 + i * 4, 500) for i in range(20)]
    iss = QA.frozen_frames(fr, FPS, motion=[(0, 3)]); assert len(iss) == 1 and 0.7 < iss[0]["t"] < 1.0 and iss[0]["t_end"] - iss[0]["t"] > 1.0
    assert not QA.frozen_frames(fr, FPS, motion=[(2.6, 3.0)])                                  # a hold is fine where no motion is planned
    assert not QA.frozen_frames(fr[:20], FPS)


def test_lipsync_both_directions():
    v = AM.synth_voice(4.0, seed=1, gaps=True); rms = AM.rms_track(v, FPS); n = len(rms)
    open_ok = (rms > 0.01).astype(np.float32)
    assert not QA.lipsync_issues(open_ok, rms, FPS, "chhotu")
    assert QA.lipsync_issues(np.ones(n), np.zeros(n), FPS, "x")[0]["kind"] == "mouth_open_silent"
    closed = np.zeros(n); iss = QA.lipsync_issues(closed, rms, FPS, "x"); assert iss and iss[0]["kind"] == "mouth_closed_speaking"
    # a small sync offset is tolerated by shifting the track
    sh = np.roll(open_ok, 2); assert len(QA.lipsync_issues(sh, rms, FPS, "x", offset=-2 / FPS)) <= len(QA.lipsync_issues(sh, rms, FPS, "x"))


def test_run_qa_on_video_and_audio_mismatch():
    fr = [with_block(BG, 540 + (i % 12) * 4, 250, 700 + (i % 12) * 4, 600) for i in range(72)]
    for i in range(30, 40): fr[i] = np.zeros_like(BG)
    d = tempfile.mkdtemp(); vp = os.path.join(d, "v.mp4"); C.write_video(fr, vp, FPS, crf=20)
    ap = AM.write_wav(os.path.join(d, "a.wav"), AM.synth_voice(4.5, seed=2))
    plan = {"actors": [{"who": "dadi", "box": [0.38, 0.3, 0.65, 0.9], "start": 0, "end": 3.0}], "motion": [(0, 3)]}
    rep = QA.run_qa(vp, plan, plates=BG, audio=ap); checks = {i["check"] for i in rep["issues"]}
    assert not rep["ok"] and "blank_frames" in checks and "av_length" in checks and "frozen_frames" not in checks
    txt = QA.format_report(rep); assert "FAIL" in txt and "blank_frames" in txt
    good = QA.run_qa([with_block(BG, 540 + (i % 12) * 4, 250, 700 + (i % 12) * 4, 600) for i in range(48)], {"actors": plan["actors"], "motion": [(0, 2)]}, plates=BG)
    assert good["ok"], good["issues"]


def test_speed():
    fr = [BG.copy() for _ in range(12)]; t = C.bench(lambda: QA.blank_frames(fr, FPS), 3)
    assert t / 12 < 0.02
