"""Animal walk key drawings, step 1 (CPU): a side-view quadruped from testart, walked by animals.py (legs alternate by construction).
Each frame becomes the INIT + canny control of an img2img pass (LoRA + IP-Adapter on the master) on Kaggle -> styled goat/dog, same legs.
  python animal_walk_init.py [n_frames=6]  -> out/keys_assets/animal_init/<cid>_<i>.png + items in out/keys_jobs/animal_items.json"""
import base64, io, json, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import testart as T, animals as AN
OUT = os.path.join(HERE, "out", "keys_assets", "animal_init")
KIND = {"chamki": "goat", "sheru": "dog"}


def frames(cid, n=6, W=1216, H=832):
    img, rig = T.make_quadruped(KIND[cid]); out = []
    hz = 1.0; per = 1.0 / hz
    for i in range(n):
        t = per * i / n
        spr, info = AN.animate_animal(img, rig, "walk", t + 2.0, {"dur": 10.0, "hz": hz, "speed": 0.0}, return_info=True)
        a = spr[:, :, 3] > 20; ys, xs = np.nonzero(a)
        crop = spr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        # place on a light grey canvas, feet on a fixed line, centred
        c = Image.new("RGB", (W, H), (225, 225, 225)); s = 0.72 * H / max(1, crop.shape[0]); s = min(s, 0.8 * W / crop.shape[1])
        cr = Image.fromarray(crop).resize((int(crop.shape[1] * s), int(crop.shape[0] * s)), Image.LANCZOS)
        c.paste(cr, ((W - cr.size[0]) // 2, int(0.9 * H) - cr.size[1]), cr); out.append(c)
    return out


def items(n=6):
    import p2d_keys as K
    S = K.SERIES()["characters"]; its = []; os.makedirs(OUT, exist_ok=True)
    for cid in KIND:
        c = S[cid]
        for i, im in enumerate(frames(cid, n)):
            im.save(os.path.join(OUT, f"{cid}_{i}.png"))
            sd = os.path.join(HERE, "out", "keys_assets", "src", "k8"); os.makedirs(sd, exist_ok=True); im.save(os.path.join(sd, f"init_{cid}_{i}.png"))
            it = dict(kind="i2i", char=cid, canvas=[1216, 832], seed=41, ip_scale=0.45, strength=0.85, cn_scale=0.6, cfg=3.0, steps=10,
                      group=cid, shard="animal_walk", init_file=f"init_{cid}_{i}.png",
                      prompt=f"{c['trigger']}, walking, side view, full body profile facing right, four legs, {c['short']}, {K.STYLE_T}, {K.BG}",
                      neg="front view, facing the viewer, extra legs, five legs, missing legs, text, watermark, photo, 3d render, blurry, scenery")
            it["id"] = f"{cid}/walk_{i}_{K.h({k: v for k, v in it.items() if k != 'init'}, i)}"; its.append(it)
    return its


if __name__ == "__main__":
    import p2d_keys as K
    its = items(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
    K.plan("r4", its, [8])
    print(len(its), "animal walk items")
