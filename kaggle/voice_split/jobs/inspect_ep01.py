"""Show split lines next to the Hindi: python kaggle/voice_split/jobs/inspect_ep01.py <code> <id,id,...>"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))); EP = os.path.join(ROOT, "episodes", "ep01")
TL = json.load(open(r"E:\KulfiKahani_AI_Studio\19_ep01_audio_fix\_work\timeline.json", encoding="utf-8")); HD = {v["unit"]: v["dur"] for v in TL["voices"]}
A = json.load(open(os.path.join(EP, "audio_full", "units.json"), encoding="utf-8"))["units"]
c = sys.argv[1]; R = {r["id"]: r for r in json.load(open(os.path.join(EP, "voices", c, "split", "out", "lines_timed.json"), encoding="utf-8"))}
for i in map(int, sys.argv[2].split(",")):
    r = R[i]; print(c, i, r["speaker"], f"hi {HD[i]:.2f}s dub {r['duration_s']:.2f}s sim={r['asr_sim']} {r['source']} {r['src_start']}-{r['src_end']}")
    print("   HI :", A[i]["text"][:110]); print("   TXT:", r["text"][:110]); print("   ASR:", (r["asr"] or "")[:110])
