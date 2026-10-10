"""EPISODE VOICES in every language - the Episode-1 method (owner liked its emotions) + the emotion bible:
  * only TWO base voices (Female=Gacrux, Male=Puck); every character is a fixed TONE (episodes/voice_cast.json)
  * every line: speech_metadata.style = "as <tone>; <intensity> <emotion recipe>; keep this character's voice the same; half-second pause"
  * OWNER RULE: the WHOLE episode in ONE request (4-5+ min; split only past ~1300 words ~ 9 min); never a small top-up or retake request
  * RADIO / LOUDSPEAKER "heart" lines use the thinking character's own tone (radio filter is added in the mix); cards are not spoken
Input: episodes/<ep>/lang/<code>.json (from transcreate_script.py; hi.json = the approved Hindi). Output: episodes/<ep>/voices/<code>/req_XX.wav +
units.json (every spoken line with scene order, speaker, emotion, request). Splitting into per-line clips + Rhubarb happens next (split step).
  python voices_episode.py <episode_dir> <lang,lang,...>"""
import base64, json, os, re, sys, time, wave, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from transcreate_script import KEYS
BIBLE = json.load(open(os.path.join(HERE, "..", "episodes", "emotion_bible.json"), encoding="utf-8"))
CAST = json.load(open(os.path.join(HERE, "..", "episodes", "voice_cast.json"), encoding="utf-8"))
CAST["cast"].setdefault("Jugaadu Chacha", ["Male", "Jugaadu Chacha, a lovable 50-year-old village inventor, quick and enthusiastic, slightly nasal, proud of his gadgets"])
CAST["cast"].setdefault("Pandit", ["Male", "the village temple priest, about 60, soft nasal sing-song voice"])
CAST["cast"].setdefault("Balloon-Wala", ["Male", "a poor tired balloon seller, about 45, soft hoarse voice"])
CAST["cast"].setdefault("Sheru", ["Male", "Sheru the street dog's inner voice, a cheeky playful little-boy voice, bouncy"])
TAG2NAME = {"CHHOTU": "Chhotu", "GUDIYA": "Gudiya", "RAJU": "Raju", "DADI": "Dadi", "LALLAN": "Lallan", "MASTERJI": "Masterji",
            "JUGAADU CHACHA": "Jugaadu Chacha", "PINKY": "Pinky", "BABLU": "Bablu", "EVERYONE": "Chhotu"}
HEART = re.compile(r"^(\w[\w ]*?)'s heart,?\s*(.*)$", re.I)
TAGS = re.compile(r"<[^>]+>")


def resolve(row):
    """speaker name + emotion key + radio flag for one script row."""
    sp, emo, radio = row["speaker"], row["emotion"], False
    m = HEART.match(emo)
    if sp in ("RADIO", "LOUDSPEAKER") or m:
        radio = True
        if m: sp_name, emo = m.group(1).strip().title(), m.group(2) or "neutral"
        else: sp_name = "Lallan"                                                         # 1.1: the loudspeaker blurts Lallan's thought
        sp_name = {"Chacha": "Jugaadu Chacha"}.get(sp_name, sp_name)
    else: sp_name = TAG2NAME.get(sp, sp.title())
    key = BIBLE["aliases"].get(emo.strip().lower(), emo.strip().lower().replace(" ", "_"))
    if key not in BIBLE["emotions"]: key = None
    return sp_name, key, emo, radio


def style_for(sp_name, key, raw_emo, intensity=2):
    gender, tone = CAST["cast"].get(sp_name, ["Male", f"{sp_name}, a villager"])
    em = BIBLE["emotions"][key]["style"] if key else raw_emo
    return gender, f"as {tone}; {BIBLE['intensity_words'][str(intensity)]} {em}; keep this character's voice exactly the same as before; half-second pause after"


def tts(content):
    last = None
    for model in ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview"):
        for k in KEYS:
            body = {"model": model, "input": [{"type": "user_input", "content": content}], "response_format": {"type": "audio"},
                    "generation_config": {"speech_config": {"mode": "conversational", "speakers": [{"speaker": s, "voice": v} for s, v in CAST["base"].items()]}}}
            try:
                r = json.loads(urllib.request.urlopen(urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions",
                    data=json.dumps(body).encode(), headers={"x-goog-api-key": k, "Content-Type": "application/json"}), timeout=900).read())
                data = (r.get("output_audio") or {}).get("data")
                if not data:
                    for st in r.get("steps", []) or []:
                        for c in (st.get("content", []) if isinstance(st, dict) else []):
                            if c.get("data"): data = c["data"]; break
                if data: return base64.b64decode(data), model
            except urllib.error.HTTPError as ex: last = f"{model} {ex.code}"
            except Exception as ex: last = f"{model} {ex.__class__.__name__}"
    raise RuntimeError("TTS failed " + str(last))


def build(ep_dir, code, max_words=1300):
    src = os.path.join(ep_dir, "lang", f"{code}.json")
    rows = json.load(open(src, encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["rows"]
    out = os.path.join(ep_dir, "voices", code); os.makedirs(out, exist_ok=True)
    units = []
    for r in rows:
        if r.get("kind") != "line": continue
        text = (r.get("text") or r.get("hi") or "").strip()
        if not text: continue
        sp, key, raw, radio = resolve(r)
        units.append({"id": r["id"], "speaker": sp, "emotion": key or raw, "radio": radio, "text": text})
    prev = {}
    if os.path.exists(os.path.join(out, "units.json")):                                 # INCREMENTAL: never re-record a line we already have
        for pu in json.load(open(os.path.join(out, "units.json"), encoding="utf-8"))["units"]: prev[pu["text"]] = pu
    todo = [u for u in units if u["text"] not in prev]
    if todo:                                                                            # OWNER RULE (9 Oct): never a small top-up/retake request -
        todo = units                                                                    # any change re-records the WHOLE episode in ONE 4-5+ min request
    else:
        for u in units: u["request"] = prev[u["text"]]["request"]
    start = max([pu["request"] for pu in prev.values()] or [0])
    groups, cur, cw = [], [], 0                                                         # consecutive NEW lines, ~4-5 min per request
    for u in todo:
        w = len(TAGS.sub("", u["text"]).split())
        if cur and cw + w > max_words: groups.append(cur); cur, cw = [], 0
        cur.append(u); cw += w
    if cur: groups.append(cur)
    print(code, len(units), "lines,", len(todo), "new ->", len(groups), "new request(s)", flush=True)
    for gi, g in enumerate(groups, start + 1):
        p = os.path.join(out, f"req_{gi:02d}.wav")
        for u in g: u["request"] = gi
        if os.path.exists(p): print("  have", p); continue
        content = []
        for u in g:
            key = u["emotion"] if u["emotion"] in BIBLE["emotions"] else None
            gender, style = style_for(u["speaker"], key, u["emotion"])
            content.append({"type": "text", "text": u["text"], "annotations": [{"type": "speech_metadata", "speaker": gender, "style": style}]})
        t0 = time.time(); b, model = tts(content)
        if b[:4] == b"RIFF": open(p, "wb").write(b)
        else:
            with wave.open(p, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b)
        with wave.open(p) as w: print(f"  request {gi}: {len(g)} lines -> {w.getnframes() / w.getframerate():.1f} s ({model}, {time.time() - t0:.0f} s)", flush=True)
    json.dump({"lang": code, "base": CAST["base"], "units": units, "groups": start + len(groups)}, open(os.path.join(out, "units.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    for c in sys.argv[2].split(","): build(sys.argv[1], c)
