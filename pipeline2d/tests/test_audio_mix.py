import os, sys, tempfile, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import tk_core as C, audio_mix as AM

TMP = tempfile.mkdtemp()
def W(name, x): return AM.write_wav(os.path.join(TMP, name), x)
V1 = W("v1.wav", AM.synth_voice(2.0, seed=1)); V2 = W("v2.wav", AM.synth_voice(2.5, seed=2)); MUSIC = W("m.wav", AM.synth_music(8.0))
PLAN = dict(duration=14.0, voices=[{"path": V1, "t": 1.0}, {"path": V2, "t": 6.0}], music={"path": MUSIC, "gain_db": -12, "fade_in": 1.0, "fade_out": 2.0},
            sfx=[{"name": "pop", "t": 4.0}, {"name": "boing", "t": 10.5}], ambience=[{"loc": "village_day", "start": 0, "end": 8}, {"loc": "rain", "start": 8, "end": 14}])


def test_synth_signals():
    assert abs(len(AM.synth_voice(1.5)) / AM.SR - 1.5) < 0.01 and abs(len(AM.synth_ambience("birds", 2.0)) / AM.SR - 2.0) < 0.01
    for n in ("pop", "boing", "whoosh", "ding", "thud", "splash", "coin", "crunch", "click", "tada", "laugh_pop"): x = AM.synth_sfx(n); assert 0.04 < len(x) / AM.SR < 1.5 and 0.2 < np.abs(x).max() <= 0.85, n
    assert AM.synth_ambience("rain", 1.0).std() > 0.02


def test_mix_length_and_loudness():
    out = os.path.join(TMP, "mix.wav"); info = AM.mix_from_plan(PLAN, out)
    assert abs(C.probe_duration(out) - 14.0) < 0.1, C.probe_duration(out)
    assert abs(info["lufs"] - (-14.0)) < 1.0, info
    assert abs(AM.measure_lufs(out) - (-14.0)) < 1.0
    x = AM.decode(out, mono=False); assert x.shape[1] == 2 and np.abs(x).max() <= 1.0


def test_music_ducks_under_voices():
    # a pure 1200 Hz 'music' tone and a 300 Hz 'voice' tone: the 1200 Hz energy must drop while the voice speaks
    t = np.arange(int(8 * AM.SR)) / AM.SR; mus = W("tone_m.wav", 0.5 * np.sin(2 * np.pi * 1200 * t)); vt = np.arange(int(2 * AM.SR)) / AM.SR; voi = W("tone_v.wav", 0.8 * np.sin(2 * np.pi * 300 * vt))
    out = os.path.join(TMP, "duck.wav"); AM.mix(out, 8.0, voices=[{"path": voi, "t": 3.0}], music={"path": mus, "gain_db": -10, "fade_in": 0.1, "fade_out": 0.1}, lufs=-14)
    x = AM.decode(out); band = lambda seg: np.abs(np.fft.rfft(seg * np.hanning(len(seg))))[int(1200 * len(seg) / AM.SR) - 3:int(1200 * len(seg) / AM.SR) + 4].max()
    during = band(x[int(3.6 * AM.SR):int(4.4 * AM.SR)]); before = band(x[int(1.0 * AM.SR):int(1.8 * AM.SR)]); after = band(x[int(6.5 * AM.SR):int(7.3 * AM.SR)])
    assert during < 0.5 * before and after > 0.8 * before, (before, during, after)                  # ducked by > 6 dB, then it comes back


def test_sfx_land_at_their_times():
    out = os.path.join(TMP, "sfx.wav"); AM.mix(out, 6.0, sfx=[{"name": "ding", "t": 2.0, "gain_db": 0}, {"name": "thud", "t": 4.5, "gain_db": 0}], lufs=-16)
    r = AM.rms_track(out, 24); k1 = int(2.0 * 24); k2 = int(4.5 * 24)
    assert r[k1:k1 + 6].max() > 8 * r[:k1 - 2].max() + 1e-4 and r[k2:k2 + 6].max() > 8 * r[k1 + 30:k2 - 2].max() + 1e-4


def test_ambience_follows_locations():
    out = os.path.join(TMP, "amb.wav"); AM.mix(out, 10.0, ambience=[{"loc": "rain", "start": 0, "end": 5, "gain_db": -12}, {"loc": "silence", "start": 5, "end": 10}], lufs=-20)
    x = AM.decode(out); a, b = np.abs(x[int(1 * AM.SR):int(4 * AM.SR)]).mean(), np.abs(x[int(6 * AM.SR):int(9 * AM.SR)]).mean(); assert a > 20 * b + 1e-5


def test_configured_library_files_are_used():
    fx = W("mine.wav", np.sin(2 * np.pi * 700 * np.arange(int(0.3 * AM.SR)) / AM.SR) * 0.8); out = os.path.join(TMP, "lib.wav")
    AM.mix(out, 3.0, sfx=[{"name": "my_hit", "t": 1.0, "gain_db": 0}], sfx_library={"my_hit": fx}, lufs=-16); x = AM.decode(out)[int(1.0 * AM.SR):int(1.3 * AM.SR)]
    spec = np.abs(np.fft.rfft(x)); assert abs(np.argmax(spec) * AM.SR / len(x) - 700) < 25


def test_voice_only_and_empty():
    out = os.path.join(TMP, "vo.wav"); info = AM.mix(out, 4.0, voices=[{"path": V1, "t": 0.5}]); assert abs(info["lufs"] + 14) < 1.0 and abs(C.probe_duration(out) - 4.0) < 0.1


def test_mux_into_video():
    vid = os.path.join(TMP, "v.mp4"); C.write_video([np.full((72, 128, 3), 80, np.uint8)] * 48, vid, 24)
    out = os.path.join(TMP, "av.mp4"); AM.mix(out, 2.0, voices=[{"path": V1, "t": 0.2}], video=vid); r = subprocess.run([C.ffmpeg_exe(), "-i", out], capture_output=True, text=True).stderr; assert "Video:" in r and "Audio:" in r


if __name__ == "__main__":
    import pytest; sys.exit(pytest.main([__file__, "-q"]))
