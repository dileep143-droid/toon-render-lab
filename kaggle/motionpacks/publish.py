"""Assemble one PRIVATE Kaggle dataset from the decrypted build outputs and create / version it.
    python kaggle/motionpacks/publish.py <packs|nc> <md_root (has md/<pack>/ + catalogue_*.json)> <merge_dir> <stage_dir> [blend_dir]
packs -> mani7673/sonpur-motion-packs (commercial-OK: cmu, style100, quaternius)
nc    -> mani7673/sonpur-motion-nc    (NON-COMMERCIAL: bandai, lafan, zeggs, motorica, interact)
Raw source archives are re-downloaded into raw/ (never through GitHub artifacts). Needs KAGGLE_API_TOKEN."""
import glob, json, os, shutil, subprocess, sys, zipfile, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import packs as PK
WHICH, MDROOT, MERGE, STAGE = sys.argv[1:5]; BLEND = sys.argv[5] if len(sys.argv) > 5 else None
DS = {"packs": "mani7673/sonpur-motion-packs", "nc": "mani7673/sonpur-motion-nc"}[WHICH]
TITLE = {"packs": "Sonpur Motion Packs (commercial OK)", "nc": "Sonpur Motion Packs NC (non-commercial)"}[WHICH]
PACKS = [p for p, s in PK.SOURCES.items() if s["dataset"] == WHICH]

def sh(c, t=7200):
    print(">>", c[:200], flush=True); r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print(r.stdout[-1500:], r.stderr[-1500:], flush=True); return r.returncode, r.stdout + r.stderr

def get(url, path):
    for k in range(4):
        try:
            rq = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(rq, timeout=600) as r, open(path, "wb") as f: shutil.copyfileobj(r, f, 1 << 22)
            return True
        except Exception as ex:
            print("retry", url, ex); time.sleep(10)
    return False

shutil.rmtree(STAGE, ignore_errors=True); os.makedirs(STAGE)
rows = []
for p in sorted(glob.glob(os.path.join(MDROOT, "**", "catalogue_*.json"), recursive=True)):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("pack") in PACKS: rows += d["motions"]
names = {r["name"] for r in rows}
needs = json.load(open(os.path.join(MERGE, "needs.json"), encoding="utf-8"))
# md files -> one zip per pack (Kaggle uploads a folder as many requests; a zip is one)
for pk in PACKS:
    src = os.path.join(MDROOT, "md", pk)
    if not os.path.isdir(src): print("no md for", pk); continue
    os.makedirs(os.path.join(STAGE, "md", pk), exist_ok=True)
    for f in glob.glob(os.path.join(src, "*.npz")):
        if os.path.basename(f)[:-4] in names: shutil.copy2(f, os.path.join(STAGE, "md", pk))
json.dump({"dataset": DS, "commercial_ok": WHICH == "packs", "motions": sorted(rows, key=lambda r: r["name"]),
           "needs": needs, "how_to_use": "import lib_motionlib as ML; ML.load_motion('<name or tag query>', rig, start=1, final=True)"},
          open(os.path.join(STAGE, "motion_catalogue.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
# credits (private) ------------------------------------------------------------------------------------------------
lines = [f"# {TITLE} - CREDITS AND LICENCES", "",
         ("ALL motions in this dataset may be used in the monetised YouTube videos (commercial_ok = true). Keep the credits below in the video description where the licence asks for attribution (100STYLE: CC BY 4.0 = attribution REQUIRED)."
          if WHICH == "packs" else
          "!! NON-COMMERCIAL DATA. Every motion here has commercial_ok = false. Use for previews, blocking, tests and reference ONLY - NOT in monetised videos. lib_motionlib.load_motion(final=True) prints a warning when one of these is used."),
         "", "Raw source files and the retargeted motion descriptions are private copies; do not publish or resell them.", ""]
import collections
cnt = collections.Counter(r["pack"] for r in rows)
for pk in PACKS:
    S = PK.SOURCES[pk]
    lines += [f"## {pk}  ({cnt.get(pk, 0)} motions)", f"- Licence: {S['licence']}", f"- Commercial use: {'YES' if S['commercial_ok'] else 'NO'}",
              f"- Credit line: {S['credit']}", f"- Source: {S['url']}", ""]
lines += ["## Not included (and why)", "- AMASS / SMPL-derived sets, HumanML3D, BONES-SEED (licence restricted to academics / qualifying startups), Truebones free packs (non-commercial, manual Gumroad download), KIT ML (MMM/C3D format, licence unclear).",
          "- Mixamo, Rokoko free packs, ActorCore free motions: need the owner's own account login; see MANUAL_DOWNLOADS in the report.", ""]
open(os.path.join(STAGE, "CREDITS.md"), "w", encoding="utf-8").write("\n".join(lines))
# raw sources -------------------------------------------------------------------------------------------------------
raw = os.environ.get("RUNNER_TEMP", "/tmp") + "/rawtmp"; os.makedirs(raw, exist_ok=True)     # top-level raw_*.zip files (a sub-folder would be zipped twice)
for pk in PACKS:
    if pk == "cmu":
        sh(f"cd {raw} && git clone -q --depth 1 https://github.com/una-dinosauria/cmu-mocap.git && rm -rf cmu-mocap/.git && zip -qr -1 {STAGE}/raw_cmu_bvh.zip cmu-mocap && rm -rf cmu-mocap", 3600)
    elif pk == "bandai":
        sh(f"cd {raw} && git clone -q --depth 1 https://github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset.git bandai && rm -rf bandai/.git && zip -qr -1 {STAGE}/raw_bandai_bvh.zip bandai && rm -rf bandai", 3600)
    elif pk == "quaternius":
        for u in ("https://opengameart.org/sites/default/files/universal_animation_librarystandard.zip", "https://opengameart.org/sites/default/files/universal_animation_library_2standard.zip"):
            get(u, os.path.join(STAGE, "raw_quaternius_" + os.path.basename(u)))
    else:
        print("raw", pk, get(PK.SOURCES[pk]["url"], os.path.join(STAGE, f"raw_{pk}_bvh.zip")))
if BLEND and os.path.isdir(BLEND):
    os.makedirs(os.path.join(STAGE, "blend"), exist_ok=True)
    for f in glob.glob(os.path.join(BLEND, f"*{WHICH}*.blend")): shutil.copy2(f, os.path.join(STAGE, "blend"))
sh(f"du -sh {STAGE}/* ; ls -la {STAGE}/blend 2>/dev/null; df -h {STAGE} | tail -1")
meta = {"title": TITLE, "id": DS, "licenses": [{"name": "other"}], "isPrivate": True,
        "subtitle": "Private motion library for the Sonpur kids series (MPFB retarget data + raw sources)"}
json.dump(meta, open(os.path.join(STAGE, "dataset-metadata.json"), "w", encoding="utf-8"))
rc, out = sh(f"kaggle datasets status {DS}")
if rc == 0 and ("ready" in out.lower() or "pending" in out.lower()):
    rc, out = sh(f'kaggle datasets version -p {STAGE} -m "motion packs build" --dir-mode zip', 10800)
else:
    rc, out = sh(f"kaggle datasets create -p {STAGE} --dir-mode zip", 10800)
print("PUBLISH", WHICH, DS, "rc", rc, "motions", len(rows))
rc2, out2 = sh(f"kaggle datasets list --mine -s sonpur-motion")
sys.exit(rc)
