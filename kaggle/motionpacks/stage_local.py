"""Stage the two PRIVATE Kaggle datasets from collected kernel outputs (motion_library/packs_out/<kernel>/out.tar).
    python kaggle/motionpacks/stage_local.py <packs_out> <stage_root> [extra_out_dir ...]
-> <stage_root>/packs/ (sonpur-motion-packs) and <stage_root>/nc/ (sonpur-motion-nc): md.zip (md/<pack>/*.npz), motion_catalogue.json,
   CREDITS.md, dataset-metadata.json; <stage_root>/merged/ (needs.json, sheet_selection.json, summary.json, motion_catalogue_all.json)."""
import glob, json, os, sys, tarfile, zipfile, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import packs as PK, merge as MG
SRC, ST = sys.argv[1], sys.argv[2]; extra = sys.argv[3:]
os.makedirs(ST, exist_ok=True)
parts = os.path.join(ST, "parts"); os.makedirs(parts, exist_ok=True)
tars = sorted(glob.glob(os.path.join(SRC, "*", "out.tar")))
zips = {w: zipfile.ZipFile(os.path.join(ST, f"md_{w}.zip"), "w", zipfile.ZIP_STORED) for w in ("packs", "nc")}
def add_dir(base):
    for p in glob.glob(os.path.join(base, "catalogue_*.json")):
        open(os.path.join(parts, os.path.basename(p)), "wb").write(open(p, "rb").read())
    for p in glob.glob(os.path.join(base, "md", "*", "*.npz")):
        pk = os.path.basename(os.path.dirname(p)); w = PK.SOURCES[pk]["dataset"]
        zips[w].write(p, f"{pk}/{os.path.basename(p)}")
for t in tars:
    if os.path.getsize(t) < 20000: print("skip empty", t); continue
    with tarfile.open(t) as tf:
        for m in tf:
            if not m.isfile(): continue
            n = m.name.split("/", 1)[1] if "/" in m.name else m.name           # strip leading 'out/'
            data = tf.extractfile(m).read()
            if n.startswith("catalogue_"): open(os.path.join(parts, n), "wb").write(data)
            elif n.startswith("md/") and n.endswith(".npz"):
                pk = n.split("/")[1]; zips[PK.SOURCES[pk]["dataset"]].writestr(n[3:], data)
    print("tar", os.path.basename(os.path.dirname(t)))
for e in extra: add_dir(e)
for z in zips.values(): z.close()
MG.main(parts, os.path.join(ST, "merged"))
allrows = json.load(open(os.path.join(ST, "merged", "motion_catalogue_all.json"), encoding="utf-8"))["motions"]
needs = json.load(open(os.path.join(ST, "merged", "needs.json"), encoding="utf-8"))
for w, ds, title in (("packs", "mani7673/sonpur-motion-packs", "Sonpur Motion Packs"), ("nc", "mani7673/sonpur-motion-nc", "Sonpur Motion Packs NC")):
    d = os.path.join(ST, w); os.makedirs(d, exist_ok=True)
    os.replace(os.path.join(ST, f"md_{w}.zip"), os.path.join(d, "md.zip"))
    rows = sorted([r for r in allrows if PK.SOURCES[r["pack"]]["dataset"] == w], key=lambda r: r["name"])
    json.dump({"dataset": ds, "commercial_ok": w == "packs", "motions": rows, "needs": needs,
               "how_to_use": "SONPUR_MOTION_DIR=<this folder>; import lib_motionlib as ML; ML.load_motion('<name or tags>', rig, start=1, final=True)"},
              open(os.path.join(d, "motion_catalogue.json"), "w", encoding="utf-8"), ensure_ascii=False)
    cnt = collections.Counter(r["pack"] for r in rows)
    L = [f"# {title} - CREDITS AND LICENCES (private)", "",
         "All motions here are commercial_ok = true (use in monetised videos; keep the credit lines; 100STYLE = CC BY 4.0, attribution REQUIRED)." if w == "packs"
         else "!! NON-COMMERCIAL: every motion here is commercial_ok = false. Previews/blocking/reference only, NOT in monetised videos. load_motion(final=True) warns.", ""]
    for pk in [p for p, s in PK.SOURCES.items() if s["dataset"] == w]:
        S = PK.SOURCES[pk]
        L += [f"## {pk} ({cnt.get(pk, 0)} motions)", f"- Licence: {S['licence']}", f"- Commercial use: {'YES' if S['commercial_ok'] else 'NO'}", f"- Credit: {S['credit']}", f"- Source: {S['url']}", ""]
    L += ["Retargeted data = rig-independent motion descriptions (lib_motionlib md format, 30 fps). Raw source archives: re-download from the Source URLs (scripted in kaggle/motionpacks/publish.py)."]
    open(os.path.join(d, "CREDITS.md"), "w", encoding="utf-8").write("\n".join(L))
    json.dump({"title": title, "id": ds, "licenses": [{"name": "other"}]}, open(os.path.join(d, "dataset-metadata.json"), "w", encoding="utf-8"))
    print("STAGED", w, len(rows), "motions", dict(cnt))
