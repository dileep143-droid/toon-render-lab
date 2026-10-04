"""Generate episode art with Gemini image models on Vertex AI (billed to the trial project, keyless on GitHub via WIF).
  python vertex_gen.py <plan.json> <series.json> <out_dir> [--only masters,poses,plates,props] [--chars dadi,chhotu]
Layout written: <out>/masters/<char>.png, <out>/poses/<pose_id>.png, <out>/plates/<plate_id>_0.png, <out>/props/<prop>.png, <out>/sheet.jpg
Auth: GOOGLE_OAUTH_ACCESS_TOKEN env, else google-auth ADC, else `gcloud auth print-access-token`. Tokens are never printed."""
import base64, json, os, subprocess, sys, time, urllib.error, urllib.request
from PIL import Image

PROJECT = os.environ.get("VERTEX_PROJECT", "project-5ab72bd2-b72e-41ff-a08")
MODEL = os.environ.get("VERTEX_IMAGE_MODEL", "gemini-3.1-flash-image")
STYLE = ("Flat 2D vector cartoon in the style of Indian animated moral-story YouTube channels: clean uniform black outlines, "
         "flat cel shading, bright colours, large expressive eyes, kids TV animation, no text, no watermark.")
PLATE_TEXT = {
    "courtyard_morning": "the open mud courtyard of a village house in Sonpur, Bihar, at morning: charpai cot, tulsi plant, clay pots, neem tree, soft golden light",
    "courtyard_noon": "the same village house courtyard at bright noon, hard shadows, blue sky",
    "courtyard_evening": "the same village house courtyard at evening, orange sunset light",
    "courtyard_night": "the same village house courtyard at night, moonlight, a lantern glowing, deep blue sky with stars",
    "house_inside_noon": "inside a simple village house in Bihar: mud walls, wooden almirah, a chauki low table, shelf with brass pots, daylight from a window",
    "house_inside_evening": "the same village house interior at evening, warm lamp light",
    "well_peepal_evening": "a village well beside a huge peepal tree at evening, stone platform, bucket and rope, orange sky",
    "well_peepal_dusk": "the same village well and peepal tree at dusk, purple sky, first stars",
    "well_peepal_twilight": "the same village well and peepal tree in deep twilight, dark blue, fireflies",
    "lallan_shop_evening": "a small village sweet shop (halwai) at evening: wooden counter, glass jars, trays of laddoos and jalebi, a hanging bulb, a plain signboard with no readable text",
}
PROP_TEXT = {
    "laddoo": "a single round orange-yellow besan laddoo", "laddoo_big": "a big round golden laddoo, slightly shiny",
    "empty_thali": "an empty round bronze thali plate", "laddoo_plate": "a bronze thali heaped with eleven round laddoos",
    "belan": "a wooden rolling pin (belan)", "paraat": "a wide shallow steel paraat basin with besan dough",
}


def token():
    t = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if t: return t
    r = subprocess.run("gcloud auth print-access-token", shell=True, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip(): return r.stdout.strip()
    import google.auth, google.auth.transport.requests
    c, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"]); c.refresh(google.auth.transport.requests.Request()); return c.token


TOK = None
# Parallel lanes: Vertex quotas are per model per region, so several (region, model) pairs run side by side.
LANES = [("global", "gemini-3.1-flash-image"), ("global", "gemini-2.5-flash-image"), ("us-central1", "gemini-2.5-flash-image"),
         ("europe-west4", "gemini-2.5-flash-image"), ("global", "gemini-3.1-flash-lite-image")]
if os.environ.get("VERTEX_LANES"): LANES = [tuple(x.split(":")) for x in os.environ["VERTEX_LANES"].split(",")]
import itertools, threading
_lane_iter = itertools.cycle(range(len(LANES))); _lock = threading.Lock()


def _next_lane():
    with _lock: return LANES[next(_lane_iter)]


def gen(prompt, out, ar="1:1", ref=None, tries=10):
    global TOK
    if os.path.exists(out): return True
    TOK = TOK or token()
    parts = []
    if ref: parts.append({"inlineData": {"mimeType": "image/png", "data": base64.b64encode(open(ref, "rb").read()).decode()}})
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ar}}}
    for a in range(tries):
        loc, model = _next_lane()
        host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
        url = f"https://{host}/v1/projects/{PROJECT}/locations/{loc}/publishers/google/models/{model}:generateContent"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOK})
        try:
            with urllib.request.urlopen(req, timeout=240) as r: j = json.load(r)
            img = [p for p in j.get("candidates", [{}])[0].get("content", {}).get("parts", []) if "inlineData" in p]
            if img:
                open(out, "wb").write(base64.b64decode(img[0]["inlineData"]["data"])); return True
            print("  no image:", os.path.basename(out), str(j)[:160], flush=True); return False
        except urllib.error.HTTPError as e:
            code = e.code; e.read()
            if code == 401: TOK = token(); continue
            if code == 404: continue                      # model not in this region -> next lane
            print(f"  {code} {os.path.basename(out)} on {loc}/{model}, retry {a+1}", flush=True); time.sleep(3 + 3 * a if code == 429 else 4)
        except Exception as e:
            print("  err", os.path.basename(out), str(e)[:80], flush=True); time.sleep(4)
    return False


def run_jobs(jobs, workers=None):
    """jobs: list of (prompt, out, ar, ref, label). Runs them across the lanes in parallel; returns the outputs that succeeded."""
    import concurrent.futures as cf
    ok = []
    with cf.ThreadPoolExecutor(workers or len(LANES)) as ex:
        futs = {ex.submit(gen, p, o, ar, ref): (o, lab) for p, o, ar, ref, lab in jobs}
        for f in cf.as_completed(futs):
            o, lab = futs[f]; r = f.result(); print(lab, r, flush=True); r and ok.append(o)
    return ok


def main():
    a = sys.argv[1:]
    plan = json.load(open(a[0], encoding="utf-8-sig")); series = json.load(open(a[1], encoding="utf-8-sig")); out = a[2]
    opt = lambda f, d: a[a.index(f) + 1] if f in a else d
    only = opt("--only", "masters,poses,plates,props").split(","); chars = opt("--chars", "").split(",") if "--chars" in a else None
    for d in ("masters", "poses", "plates", "props", "mouths"): os.makedirs(os.path.join(out, d), exist_ok=True)
    C = series["characters"]; t0 = time.time(); done = []; jobs = []
    if "masters" in only:
        for c, v in C.items():
            if chars and c not in chars: continue
            desc = v.get("desc") or v.get("prompt") or str(v)
            f = os.path.join(out, "masters", f"{c}.png")
            animal = any(w in desc.lower() for w in ("goat", "dog", "cow", "cat", "bird", "monkey", "buffalo"))
            pose_txt = ("a real four-legged animal standing naturally on all four legs, side view facing right, whole body visible, NOT upright, NOT human-like" if animal else "Standing, full body from head to feet, front view, arms relaxed")
            jobs.append((f"{STYLE}\nCharacter design, master reference: {desc}. {pose_txt}, "
                     f"mouth closed, neutral friendly expression. Single character only, isolated on a plain pure white background, nothing else.", f, "4:3" if animal else "3:4", None, f"master {c}"))
        done += run_jobs(jobs); jobs = []
    if "poses" in only:
        for p in plan.get("poses", []):
            c = p["char"]
            if chars and c not in chars: continue
            ref = os.path.join(out, "masters", f"{c}.png")
            if not os.path.exists(ref): print("  no master for", c); continue
            f = os.path.join(out, "poses", f"{p['id']}.png")
            jobs.append((f"{STYLE}\nDraw EXACTLY the same character as in the reference image (same face, hair, clothes, colours, proportions). "
                     f"New pose: {p.get('prompt','')} (pose type: {p.get('pose','')}). Full body, isolated on a plain pure white background, nothing else.", f, "3:4", ref, f"pose {p['id']}"))
        done += run_jobs(jobs); jobs = []
    if "mouths" in only:
        os.makedirs(os.path.join(out, "mouths"), exist_ok=True)
        MOUTH = {"half": "mouth slightly open, lips parted a little, no teeth, no text anywhere",
                 "open": "mouth wide open as if singing, dark mouth interior and a small tongue drawn in the same flat cartoon style, no text anywhere"}
        for c in C:
            if chars and c not in chars: continue
            ref = os.path.join(out, "masters", f"{c}.png")
            if not os.path.exists(ref): continue
            for st, d in MOUTH.items():
                f = os.path.join(out, "mouths", f"{c}_{st}.png")
                jobs.append((f"Edit this drawing: keep EVERYTHING exactly identical (same pose, size, position, clothes, colours, line style, white background) "
                         f"and change ONLY the mouth: {d}. Output the full image at the same size.", f, "3:4", ref, f"mouth {c} {st}"))
        done += run_jobs(jobs); jobs = []
    if "posemouths" in only:
        os.makedirs(os.path.join(out, "mouths"), exist_ok=True)
        MOUTH = {"half": "mouth slightly open, lips parted a little, no teeth, no text anywhere",
                 "open": "mouth wide open as if singing, dark mouth interior and a small tongue drawn in the same flat cartoon style, no text anywhere"}
        import glob as _g
        for f_ in sorted(_g.glob(os.path.join(out, "poses", "*.png"))):
            pid = os.path.splitext(os.path.basename(f_))[0]; c = pid.split("__")[0] if "__" in pid else pid.split("_")[0]
            if chars and c not in chars: continue
            for st, d in MOUTH.items():
                f = os.path.join(out, "mouths", f"{pid}_{st}.png")
                jobs.append((f"Edit this drawing: keep EVERYTHING exactly identical (same pose, size, position, clothes, colours, line style, white background) "
                             f"and change ONLY the mouth: {d}. Output the full image at the same size.", f, "3:4", f_, f"posemouth {pid} {st}"))
        done += run_jobs(jobs); jobs = []
    if "plates" in only:
        for pl in plan.get("plates", []):
            f = os.path.join(out, "plates", f"{pl['id']}_0.png")
            txt = pl.get("prompt") or PLATE_TEXT.get(pl["id"], pl["id"].replace("_", " "))
            jobs.append((f"{STYLE}\nBackground art only, wide establishing shot: {txt}. Completely empty scene, absolutely no people or animals, no text. Everything, including windows, doorways and the view outside them, must be drawn in the same flat cartoon vector style: no photographs, no photorealistic textures, no pasted real-world images anywhere.", f, "16:9", None, f"plate {pl['id']}"))
        done += run_jobs(jobs); jobs = []
    if "props" in only:
        for pr in plan.get("props", []):
            pid = pr["id"] if isinstance(pr, dict) else pr
            f = os.path.join(out, "props", f"{pid}.png")
            txt = (pr.get("prompt") if isinstance(pr, dict) else None) or PROP_TEXT.get(pid, pid.replace("_", " "))
            jobs.append((f"{STYLE}\nSingle object only, a plain inanimate object with NO face, no eyes, no mouth: {txt}. Isolated on a plain pure white background, nothing else, no hands, no text.", f, "1:1", None, f"prop {pid}"))
        done += run_jobs(jobs); jobs = []
    # contact sheet
    cells = []
    for d, size in (("masters", (240, 320)), ("mouths", (180, 240)), ("poses", (180, 240)), ("plates", (384, 216)), ("props", (160, 160))):
        fs = sorted(os.listdir(os.path.join(out, d)))
        for f in fs:
            try: cells.append(Image.open(os.path.join(out, d, f)).convert("RGB").resize(size))
            except Exception: pass
    if cells:
        W = 1920; x = y = 0; rowh = 0; rows = []
        for im in cells:
            if x + im.width > W: y += rowh; x = 0; rowh = 0
            rows.append((im, x, y)); x += im.width; rowh = max(rowh, im.height)
        sheet = Image.new("RGB", (W, y + rowh), "white")
        for im, px, py in rows: sheet.paste(im, (px, py))
        sheet.save(os.path.join(out, "sheet.jpg"), quality=85)
    print("DONE", len(done), "images in", f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
