"""Download a small curated set of free motion-capture clips (BVH) for retargeting onto our MPFB characters.

  python fetch_mocap.py           download what is missing into mocap/, write mocap/index.json
  python fetch_mocap.py --list    just print the curated list

Source: the CMU Graphics Lab Motion Capture Database (mocap.cs.cmu.edu), in Bruce Hahne's "MotionBuilder-friendly" BVH
conversion (cgspeed.com), served file-by-file from the GitHub mirror github.com/una-dinosauria/cmu-mocap.
Licence (mocap.cs.cmu.edu front page): "This data is free for use in research projects. You may include this data in
commercially-sold products, but you may not resell this data directly, even in converted form."  -> fine for our videos;
do NOT sell or re-publish the BVH files themselves as a product.  See mocap/LICENSES.md.

BVH facts (cgspeed 2010 release): frame 1 is an added T-pose facing +Z, Y is up, units are CMU "inches-ish" (~1/0.45 of
the ASF length unit; an adult is ~ 17-18 units from hips to head top -> scale ~0.056 to metres), 120 fps (Frame Time .0083333).
Stdlib only, idempotent. Run from the repo folder (never from %TEMP%)."""
import json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "mocap")
BASE = "https://raw.githubusercontent.com/una-dinosauria/cmu-mocap/master"
UA = {"User-Agent": "toon-render-lab fetch_mocap"}
LICENCE = ("CMU Graphics Lab Motion Capture Database - free for research; may be included in commercially-sold products; "
           "may not be resold directly, even in converted form. BVH conversion by Bruce Hahne (no extra restrictions).")

# name, CMU subject_trial, CMU description (from cmu-mocap-index-text.txt), what we use it for
CLIPS = [
    ("walk", "16_15", "walk", "plain walk cycle"),
    ("walk_happy", "82_12", "happy or fast walk forward", "bouncy walk"),
    ("run", "16_35", "run/jog", "run cycle"),
    ("jump", "16_01", "jump", "jump on the spot"),
    ("jump_forward", "13_11", "forward jump", "long jump forward"),
    ("sit", "143_18", "Sit Down And Get Up", "sit down on the ground/chair and get up"),
    ("sit_stool", "143_19", "Sit On Stool And Get Up", "sit on a stool (charpai height) and get up"),
    ("wave", "143_25", "Waving", "wave hello"),
    ("dance_indian", "94_01", "subject #94 'indian dance' (trial description: Unknown)", "Indian dance loop"),
    ("dance_chicken", "143_34", "Chicken Dance", "silly comedy dance"),
    ("sneak", "143_41", "Sneak", "sneak / tiptoe"),
    ("fall_rugpull", "90_18", "RugPullFall", "slip / rug pulled from under the feet"),
    ("laugh", "13_14", "laugh", "laughing body motion"),
    ("happy", "79_69", "very happy", "happy reaction"),
    ("scared", "79_73", "scared", "scared reaction"),
    ("cry", "79_72", "crying", "crying"),
    ("throw_catch", "143_20", "Catch And Throw", "throw and catch"),
    ("climb_ladder", "13_33", "climb ladder", "climb (hands alternate)"),
    ("pick_up_box", "143_11", "Walk And Pick up Box", "walk, bend, lift and carry (bucket carry reference)"),
]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r: return r.read()
        except Exception as ex:
            if i == tries - 1: raise
            print("   retry", url, ex); time.sleep(3 + 3 * i)


def bvh_info(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    joints = re.findall(r"(?:ROOT|JOINT)\s+(\S+)", txt)
    frames = int(re.search(r"Frames:\s*(\d+)", txt).group(1))
    ft = float(re.search(r"Frame Time:\s*([0-9.eE-]+)", txt).group(1))
    return joints, frames, ft


def main():
    if "--list" in sys.argv:
        for c in CLIPS: print(*c, sep="  |  ")
        return
    os.makedirs(OUT, exist_ok=True)
    idx_path = os.path.join(OUT, "index.json")
    index = json.load(open(idx_path, encoding="utf-8")) if os.path.exists(idx_path) else {}
    for extra in ("READMEFIRST.txt",):                              # Bruce Hahne's notes incl. the CMU usage paragraph
        p = os.path.join(OUT, "CMU_BVH_" + extra)
        if not os.path.exists(p):
            open(p, "wb").write(get(f"{BASE}/{extra}")); print("saved", os.path.relpath(p, HERE))
    total = 0
    for name, trial, desc, use in CLIPS:
        subj = trial.split("_")[0].zfill(3)
        url = f"{BASE}/data/{subj}/{trial}.bvh"
        path = os.path.join(OUT, f"{name}.bvh")
        if not os.path.exists(path):
            data = get(url)
            if not data.startswith(b"HIERARCHY"):
                print("NOT A BVH:", url); continue
            open(path, "wb").write(data); print("got", name, "<-", trial, len(data) // 1024, "KB")
        joints, frames, ft = bvh_info(path)
        total += os.path.getsize(path)
        index[name] = {"file": f"mocap/{name}.bvh", "source_url": url, "cmu_subject_trial": trial,
                       "cmu_page": f"http://mocap.cs.cmu.edu/search.php?subjectnumber={int(subj)}",
                       "description": desc, "use": use, "frame_time": ft, "fps": round(1 / ft), "frames": frames,
                       "seconds": round(frames * ft, 2), "first_frame": "T-pose added by the cgspeed conversion (skip it when retargeting)",
                       "joints": len(joints), "licence": LICENCE}
    json.dump(index, open(idx_path, "w", encoding="utf-8"), indent=1)
    j, _, _ = bvh_info(os.path.join(OUT, CLIPS[0][0] + ".bvh"))
    print(f"{len(index)} clips, {total / 1e6:.1f} MB -> mocap/   joints: {' '.join(j)}")


if __name__ == "__main__":
    main()
