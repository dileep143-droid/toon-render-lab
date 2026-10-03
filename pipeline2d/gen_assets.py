"""Generate pilot images from a private spec JSON (kept under pipeline2d/out/, never pushed).
  python gen_assets.py <spec.json> [name ...]      # only the named items; skips existing files unless --force
spec: {"style": "...", "items": [{"name", "prompt", "refs": [names or paths], "aspect", "size"}]}
Each item is saved as <spec dir>/img/<name>.png. "{style}" in a prompt is replaced by the spec style."""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gem
from concurrent.futures import ThreadPoolExecutor

args = [a for a in sys.argv[1:] if not a.startswith("--")]
force = "--force" in sys.argv
spec_path = args[0]
spec = json.load(open(spec_path, encoding="utf-8"))
base = os.path.join(os.path.dirname(os.path.abspath(spec_path)), "img")
want = set(args[1:])
items = [it for it in spec["items"] if (not want or it["name"] in want)]


def path(n):
    return n if os.path.isabs(n) else os.path.join(base, n + ".png")


def run(it):
    out = path(it["name"])
    if os.path.exists(out) and not force:
        return f"skip {it['name']}"
    t = time.time()
    try:
        gem.image(it["prompt"].replace("{style}", spec.get("style", "")), [path(r) for r in it.get("refs", [])],
                  aspect=it.get("aspect"), size=it.get("size"), out=out)
        return f"ok   {it['name']} {time.time() - t:.0f}s"
    except Exception as e:
        return f"FAIL {it['name']}: {str(e)[:200]}"


# items whose refs are produced in this same batch must wait: run in dependency waves
done = set(); todo = list(items)
while todo:
    ready = [it for it in todo if all(os.path.exists(path(r)) or r in done for r in it.get("refs", []))
             and not any(r in [x["name"] for x in todo] for r in it.get("refs", []))]
    if not ready:
        print("unresolved refs:", [it["name"] for it in todo]); break
    with ThreadPoolExecutor(int(os.environ.get("P2D_PAR", "4"))) as ex:
        for r in ex.map(run, ready): print(r, flush=True)
    done |= {it["name"] for it in ready}
    todo = [it for it in todo if it not in ready]
