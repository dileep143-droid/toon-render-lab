import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, testart as T, titles as TI

BG = T.make_background("village_day"); FONT = "NotoSansDevanagari-Bold.ttf"; HAS_FONT = C.find_font(FONT) is not None
SERIES = "सोनपुर की टोली"; EP = "जादुई लड्डू"


def test_devanagari_font_found_and_shaped():
    assert HAS_FONT, "install a Devanagari font (fonts-noto-core) or pass font=<path>"
    # shaped conjuncts are narrower than the naive per-character sum
    f = C.load_font(FONT, 80); whole = f.getlength("क्ष"); parts = f.getlength("क") + f.getlength("्") + f.getlength("ष"); assert whole < parts * 0.95


def test_title_card_animates_and_ends_clean():
    f0 = TI.title_card(0.0, SERIES, EP, font=FONT); f1 = TI.title_card(0.6, SERIES, EP, font=FONT); f3 = TI.title_card(3.0, SERIES, EP, font=FONT, subtitle="एपिसोड 1")
    assert f0.shape == (720, 1280, 3) and np.abs(f1.astype(int) - f0.astype(int)).mean() > 1 and np.abs(f3.astype(int) - f1.astype(int)).mean() > 1
    fe = TI.title_card(5.9, SERIES, EP, font=FONT, dur=6.0); assert fe.mean() < f3.mean() * 0.4                                   # fades out at its end
    # the series name sits inside the title-safe area
    ys, xs = np.nonzero((np.abs(f3.astype(int) - TI.title_card(3.0, "", "", font=FONT).astype(int)).sum(-1) > 90)); assert xs.min() > 64 and xs.max() < 1216 and ys.min() > 36 and ys.max() < 684


def test_wrap_and_fit():
    lines = TI.wrap_text("यह एक बहुत लंबा वाक्य है जो एक पंक्ति में नहीं आएगा क्योंकि यह बहुत लंबा है", 60, 700, FONT); assert len(lines) >= 2 and all(TI.text_width(l, 60, FONT) <= 700 + 1 for l in lines)
    s, ls = TI.fit_size("छोटा नाम", 900, 200, FONT, start=140); assert s >= 100 and len(ls) == 1
    s2, ls2 = TI.fit_size("यह बहुत लंबा शीर्षक है जो छोटे डिब्बे में फिट होना चाहिए", 500, 160, FONT, start=140); assert s2 < 100 and len(ls2) * s2 * 1.18 <= 160 + s2


def test_subtitles_only_when_active_and_inside_safe_area():
    lines = [{"start": 1.0, "end": 3.0, "text": "आज हम एक नई कहानी सुनेंगे", "text2": "Today we will hear a new story"}, {"start": 3.5, "end": 5.0, "text": "छोटू को बहुत भूख लगी थी"}]
    a = TI.burn_subtitles(BG.copy(), lines, 0.5, font=FONT); assert np.array_equal(a, BG)
    b = TI.burn_subtitles(BG.copy(), lines, 2.0, font=FONT); d = (np.abs(b.astype(int) - BG.astype(int)).sum(-1) > 40); ys, xs = np.nonzero(d)
    assert d.sum() > 3000 and xs.min() > 0.05 * 1280 and xs.max() < 0.95 * 1280 and ys.max() < 720 * 0.97 and ys.min() > 720 * 0.7                    # bottom band, inside the margins
    c = TI.burn_subtitles(BG.copy(), lines, 4.0, font=FONT); assert not np.array_equal(c, b)


def test_long_subtitle_wraps_within_width():
    lines = [{"start": 0, "end": 3, "text": "यह एक बहुत लंबी पंक्ति है जिसे स्क्रीन की चौड़ाई के अंदर दो या तीन लाइनों में बंट जाना चाहिए ताकि बच्चे आराम से पढ़ सकें"}]
    f = TI.burn_subtitles(BG.copy(), lines, 1.0, font=FONT); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 40); ys, xs = np.nonzero(d); assert xs.max() - xs.min() < 0.9 * 1280 and ys.max() - ys.min() > 80


def test_lower_third_slides_in_and_out():
    assert np.array_equal(TI.lower_third(BG.copy(), 0.0, "दादी", "सबकी प्यारी", start=1.0, dur=3.0, font=FONT), BG)
    xs = []
    for t in (1.1, 1.3, 2.5):
        f = TI.lower_third(BG.copy(), t, "दादी", "सबकी प्यारी", start=1.0, dur=3.0, font=FONT); d = (np.abs(f.astype(int) - BG.astype(int)).sum(-1) > 40); xs.append(np.nonzero(d.any(0))[0].max() if d.any() else 0)
    assert xs[0] < xs[1] < xs[2]
    assert np.array_equal(TI.lower_third(BG.copy(), 4.2, "दादी", "", start=1.0, dur=3.0, font=FONT), BG)


def test_srt_roundtrip_with_devanagari():
    lines = [{"start": 1.25, "end": 3.5, "text": "नमस्ते बच्चों"}, {"start": 4.0, "end": 6.125, "text": "आज की कहानी", "text2": "Today's story"}]
    p = os.path.join(tempfile.mkdtemp(), "a.srt"); TI.write_srt(lines, p); back = TI.read_srt(p)
    assert len(back) == 2 and back[0]["text"] == "नमस्ते बच्चों" and abs(back[1]["start"] - 4.0) < 1e-3 and abs(back[1]["end"] - 6.125) < 1e-3 and back[1]["text2"] == "Today's story"


def test_lines_from_spans():
    shots = [{"T0": 10.0, "spans": [{"unit": 3, "t0": 0.35, "t1": 2.0, "speaker": "dadi"}, {"unit": 4, "t0": 2.4, "t1": 3.0, "speaker": "chhotu"}]}]
    L = TI.lines_from_spans(shots, {"3": {"text": "आओ"}, 4: {"text": "आया"}}); assert [round(l["start"], 2) for l in L] == [10.35, 12.4] and L[0]["speaker"] == "dadi"


def test_end_card_and_thumbnail():
    e0 = TI.end_card(0.2, "मिल-जुलकर रहने में ही खुशी है", font=FONT); e3 = TI.end_card(3.0, "मिल-जुलकर रहने में ही खुशी है", font=FONT); assert np.abs(e3.astype(int) - e0.astype(int)).mean() > 3
    man, _ = T.make_human("man"); kid, _ = T.make_human("kid"); p = os.path.join(tempfile.mkdtemp(), "t.jpg")
    th = TI.thumbnail([man, kid], "जादुई लड्डू का राज़", bg=BG, font=FONT, out_path=p); assert th.shape == (720, 1280, 3) and os.path.getsize(p) < 2_000_000 and os.path.getsize(p) > 20_000
    th0 = TI.thumbnail([], "शीर्षक", font=FONT); assert th0.std() > 20


def test_run_event():
    f = TI.run_event(BG.copy(), {"title": "title_card", "start": 0, "dur": 3, "series": SERIES, "episode": EP, "font": FONT}, 1.5); assert not np.array_equal(f, BG)
    g = TI.run_event(BG.copy(), {"title": "lower_third", "start": 1, "dur": 2, "name": "छोटू", "font": FONT}, 1.8); assert not np.array_equal(g, BG)
    try: TI.run_event(BG.copy(), {"title": "nope"}, 0)
    except KeyError: pass
    else: assert False


def test_speed_budget():
    lines = [{"start": 0, "end": 9, "text": "आज हम एक नई कहानी सुनेंगे", "text2": "Today we will hear a new story"}]
    TI.title_card(1.0, SERIES, EP, font=FONT); TI.burn_subtitles(BG.copy(), lines, 1.0, font=FONT); TI.end_card(2.0, "सीख", font=FONT)
    assert C.bench(lambda: TI.title_card(1.0, SERIES, EP, font=FONT), 4) < 0.1 and C.bench(lambda: TI.burn_subtitles(BG.copy(), lines, 1.0, font=FONT), 6) < 0.05 and C.bench(lambda: TI.end_card(2.0, "सीख", font=FONT), 4) < 0.1


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))
