"""Thin Gemini client for the 2D cut-out pipeline: image generation/edits (with reference images) and box detection.
Keys: GEMINI_API_KEYS / GEMINI_API_KEY in the eduorbex .env (never printed). Rotates keys on 429/5xx."""
import base64, io, json, os, re, time, urllib.request, urllib.error
from PIL import Image

ENV = r"C:\Users\goddu\.gemini\antigravity\scratch\eduorbex\.env"
E = {k: v for k, v in os.environ.items() if k in ("GEMINI_API_KEY", "GEMINI_API_KEYS")}   # GitHub Actions: secret in the environment
if os.path.exists(ENV):
    for l in open(ENV, encoding="utf-8-sig"):
        m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.+)", l)
        if m: E[m.group(1)] = m.group(2).strip().strip("\"'")
KEYS = list(dict.fromkeys(k.strip() for k in (E.get("GEMINI_API_KEYS", "") + "," + E.get("GEMINI_API_KEY", "")).split(",") if k.strip()))
IMG_MODELS = [os.environ.get("P2D_IMG_MODEL", "gemini-3.1-flash-image"), "gemini-3-pro-image", "gemini-2.5-flash-image"]
TXT_MODELS = [os.environ.get("P2D_TXT_MODEL", "gemini-3.8-flash"), "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash"]
LOG = os.path.join(os.path.dirname(__file__), "out", "api_log.jsonl")
_k = [0]


def _post(model, body, timeout=300):
    last = None
    for attempt in range(len(KEYS) * 2):
        k = KEYS[_k[0] % len(KEYS)]
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                     data=json.dumps(body).encode(), headers={"x-goog-api-key": k, "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            last = f"{e.code} {msg}"
            if e.code in (429, 500, 502, 503, 504, 403):
                _k[0] += 1; time.sleep(2); continue
            raise RuntimeError(last)
        except Exception as e:  # timeouts
            last = str(e); _k[0] += 1; continue
    raise RuntimeError(f"{model}: all keys failed: {last}")


def _img_part(img):
    if isinstance(img, str): img = Image.open(img)
    b = io.BytesIO(); img.convert("RGB").save(b, "PNG")
    return {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(b.getvalue()).decode()}}


def image(prompt, refs=(), aspect=None, size=None, out=None):
    """Generate (or edit, when refs are given) one image. Returns a PIL image and saves to `out` if given."""
    parts = [_img_part(r) for r in refs] + [{"text": prompt}]
    cfg = {"responseModalities": ["IMAGE"]}
    ic = {}
    if aspect: ic["aspectRatio"] = aspect
    if size: ic["imageSize"] = size
    if ic: cfg["imageConfig"] = ic
    err = None
    for model in IMG_MODELS:
        t = time.time()
        try:
            d = _post(model, {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg})
        except RuntimeError as e:
            err = e; continue
        for c in d.get("candidates", []):
            for p in c.get("content", {}).get("parts", []):
                if "inlineData" in p or "inline_data" in p:
                    data = (p.get("inlineData") or p.get("inline_data"))["data"]
                    im = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
                    if out:
                        os.makedirs(os.path.dirname(out), exist_ok=True); im.save(out)
                    with open(LOG, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "model": model, "s": round(time.time() - t, 1),
                                            "size": im.size, "out": os.path.basename(out or ""), "usage": d.get("usageMetadata")}) + "\n")
                    return im
        err = RuntimeError(f"{model}: no image ({json.dumps(d)[:300]})")
    raise err


def text(prompt, images=(), json_out=True, temperature=0.4):
    """Text (optionally JSON) answer from the first working flash model."""
    parts = [_img_part(i) for i in images] + [{"text": prompt}]
    cfg = {"temperature": temperature}
    if json_out: cfg["responseMimeType"] = "application/json"
    err = None
    for model in TXT_MODELS:
        try:
            d = _post(model, {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}, timeout=600)
            txt = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
            return json.loads(txt) if json_out else txt
        except Exception as e:
            err = e; continue
    raise RuntimeError(f"text: all models failed: {err}")


def boxes(img, labels):
    """Ask Gemini for one box per label. Returns {label: (x0,y0,x1,y1)} in pixels."""
    if isinstance(img, str): img = Image.open(img)
    W, H = img.size
    prompt = ("Detect these parts in the cartoon image and return JSON list of objects {\"label\": <one of the given labels>, \"box_2d\": [ymin,xmin,ymax,xmax]} "
              "with coordinates normalised to 0-1000. One box per label, the most prominent. Labels: " + json.dumps(labels))
    body = {"contents": [{"role": "user", "parts": [_img_part(img), {"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    for model in TXT_MODELS:
        try:
            d = _post(model, body); break
        except RuntimeError:
            continue
    txt = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    res = {}
    for o in json.loads(txt):
        y0, x0, y1, x1 = o["box_2d"]
        res[o["label"]] = (x0 * W / 1000, y0 * H / 1000, x1 * W / 1000, y1 * H / 1000)
    return res
