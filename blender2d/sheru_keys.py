"""Sheru the dog: KEY drawings as Gemini edits of the master (owner rule: Gemini only for key drawings).
  python sheru_keys.py <version> [names...]   -> puppet/sheru/raw/<name>_v<version>.png  (gen() skips existing files)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline2d"))
from vertex_gen import run_jobs
MASTER = r"E:/KulfiKahani_AI_Studio/03_episode01_art/masters/sheru.png"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puppet", "sheru", "raw")
KEEP = ("Edit this drawing of Sheru the dog. Draw EXACTLY the same dog: same head shape, same big round eyes, same black nose, "
        "same dark brown floppy ears, same orange-tan coat with cream-white muzzle, chest, belly and paws, same white tail tip, "
        "same proportions and the same flat 2D cartoon style with clean black outlines and flat colours. "
        "Single dog only, whole body visible from ears to paws to tail tip, nothing cropped, on a plain pure white background, "
        "no shadow, no ground line, no text. New pose: ")
POSES = {
    "sit_front": ("sitting on its haunches facing the viewer, front view, both front legs straight, friendly closed-mouth smile, tail visible curled on the ground beside it", "1:1"),
    "sit_side": ("sitting on its haunches, side profile facing right, front legs straight, tail resting on the ground behind, closed-mouth smile", "1:1"),
    "run_1": ("running, side profile facing right, cartoon run cycle drawing 1 of 3: all four legs gathered and bunched under the body, back slightly arched, ears flying back", "4:3"),
    "run_2": ("running, side profile facing right, cartoon run cycle drawing 2 of 3: legs fully stretched, front legs reaching far forward and back legs stretched far back, all four paws off the ground in mid-air, body long and flat, ears flying back", "4:3"),
    "run_3": ("galloping, side profile facing right, the LANDING moment of a gallop: the two front legs are straight and vertical, both front paws standing on the floor directly below the chest carrying the weight, while the two back legs stretch out behind and up in the air, back paws high off the floor, like a wheelbarrow; body leaning forward and down, ears blown back showing only their brown outer side, mouth closed smile, exactly ONE tail drawn once with a solid outline, no motion blur, no ghost or after-image lines", "4:3"),
    "wag_tail_up": ("sitting on its haunches facing the viewer, front view, happy closed-mouth smile, tail pointing STRAIGHT UP high above its back like a flag, tip of the tail higher than its ears, two small curved motion lines beside the tail tip", "1:1"),
    "wearing_crown": ("sitting on its haunches facing the viewer, front view, proud happy smile, wearing a small paper crown made of yellow and red paper with zigzag points on top of its head, crown drawn in the same flat cartoon style", "1:1"),
}
v = sys.argv[1]; names = sys.argv[2:] or list(POSES)
jobs = [(KEEP + POSES[n][0] + ".", os.path.join(OUT, f"{n}_v{v}.png"), POSES[n][1], MASTER, n) for n in names]
for o in jobs:
    if os.path.exists(o[1]): print("exists, skip", o[1])
print(run_jobs(jobs))
