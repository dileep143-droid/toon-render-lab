"""gen_toolkit_md.py - writes TOOLKIT.md: hand-written intro + coverage table, with the function reference generated from the live registry
(so the docs can never list a function that does not exist).   python gen_toolkit_md.py"""
import os, sys, inspect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry as R, asset_coverage as AC

HERE = os.path.dirname(os.path.abspath(__file__))
INTRO = r'''# 2D animation toolkit (pipeline2d)

Pure code: Python + numpy + Pillow + scipy + the ffmpeg CLI. No GPU, no API keys, no internet images. Every function is **stateless in time** (`f(t, ...)`, seeded), so any frame can be
rendered alone, in any order, and the result is identical every run. Frames are `uint8 (720, 1280, 3)` RGB at 24 fps; sprites are `uint8 (h, w, 4)` RGBA. Angles are degrees, + = clockwise on screen.
Joint names ending `_l` / `_r` mean image-left / image-right. Test art is generated in code (`testart.py`); real art only needs the same rig JSON (joints + size).

## Quick start
```python
import registry as R, testart as T
plate = T.make_background("village_day")
shot = {"duration": 4.0,
        "cast":   {"dadi": {"kind": "human", "art": "dadi", "x": 900, "y": 640, "height": 380, "flip": True}},
        "events": [{"motion": "wave", "who": "dadi", "start": 0.5, "dur": 1.5},
                   {"effect": "hearts", "who": "dadi", "start": 1.5, "dur": 1.5},
                   {"camera": "push_in", "start": 1.0, "dur": 2.5, "target": [0.72, 0.5], "amount": 1.4}]}
print(R.validate_shot(shot))                      # [] = every name and parameter exists
R.Shot(shot, plate=plate).render("out.mp4")       # or shot.frame(t) for one frame
```
Real characters: `R.Shot(shot, plate, assets={"dadi": (rgba_image, rig_json)}, props={"ball": rgba_sprite})`.
`python registry.py` lists everything; `python registry.py schema` prints the JSON schema (`R.schema()`); `python asset_coverage.py [ASSET_NEEDS.json] --gaps` checks the story needs;
`python qa_checks.py video.mp4 [--audio a.wav] [--plan plan.json]` checks a rendered file. Demos: `python demos/make_demos.py <puppet|animals|effects|camera|transitions|props|scene_life|audio|titles|qa|registry>`.
Tests: `python -m pytest tests -q` (about 110 tests, ~2 min).

## Shot JSON
`cast` = `{id: {"kind": human|animal|bird|monkey, "art": name, "x", "y": feet position in px, "height": px, "flip": bool}}`. `events` is a flat list; order does not matter. Times are seconds from shot start.

| event key | example | notes |
|---|---|---|
| `motion` | `{"motion":"wave","who":"dadi","start":2.0,"dur":1.5,"side":"r"}` | name is looked up in the table of the `who`'s kind (human / animal / bird / monkey); extra keys are the motion's params |
| `effect` | `{"effect":"rain","start":0,"intensity":0.7}` | `who` or `anchor_joint` ("dadi.hand_r") pins marks to a body part; `dur` + `fade` give a soft in/out |
| `camera` | `{"camera":"push_in","start":1,"dur":2,"target":[0.7,0.5],"amount":1.4}` | moves chain: each starts where the last ended (or give `from`) |
| `prop_motion` | `{"prop_motion":"throw","prop":"ball","start":2,"dur":1,"p0":"dadi.hand_r","p1":[300,600]}` | `prop` = id in `props=`; points may be "who.joint" strings |
| `life` / `ambient` | `{"life":"birds","count":4}` / `{"ambient":"village_morning"}` | background life: one element or a preset bundle |
| `transition` | `{"transition":"dissolve","start":5.5,"dur":0.5}` | pass the next shot's frame: `shot.frame(t, next_frame=...)` |
| `title` | `{"title":"lower_third","name":"दादी","role":"सबकी प्यारी","start":1,"dur":3}` | Devanagari + Latin mixed lines are handled; font path is a parameter |
| `freeze` | `{"freeze":true,"at":2.0,"hold":0.8}` | freeze-frame; the shot gets `hold` seconds longer |
| `sfx` `voice` `music` `ambience` | `{"sfx":"pop","start":2.1}` `{"voice":"line1.wav","start":0.4}` `{"ambience":"village_day","start":0,"end":6}` | not drawn; `R.audio_plan(shot)` turns them into `audio_mix.mix_from_plan` input (ducking + -14 LUFS) |

Framing rules (`camera.check_framing / fix_framing / solve_framing`): head at least 5 % from the top edge; never cut a leg between knee and ankle in a full shot; the speaker's face is at least 1/4 of the frame height in close shots.

## Modules
| file | what it does |
|---|---|
| `tk_core.py` | easing (smooth, smoother, out_back overshoot, bounce, spring), sprite placing/warping, glow, blur, text, ffmpeg read/write, contact sheets |
| `puppet.py` | mesh puppet warp: bones, layers, inverse-skinned chain meshes, rigid-piece fallback past ~35-57 degrees; `animate`, `Performer`, `hand_point`, `draw_character` |
| `animals.py` | quadruped / bird / monkey rigs on the same engine; `animate_animal`, `AnimalPerformer` |
| `effects.py` | `apply(frame, effect, t, **params)` and `run_event` - weather, fire/light, cartoon marks, camera effects, `freeze_time` |
| `camera.py` | `Cam`, moves, `CameraTrack`, `render_view` (parallax 2-4 layers, focus pull, dutch), framing rules |
| `transitions.py` | `transition(name, a, b, u)`, `render_transition` |
| `props_motion.py` | object motion; `state()` returns the transform so hands/effects can follow |
| `scene_life.py` | background life elements + presets |
| `audio_mix.py` | ffmpeg mix: voices + music with automatic ducking + SFX + ambience per location, normalised to -14 LUFS (gain + limiter, not loudnorm); synthetic placeholders when no file is configured |
| `titles.py` | title card, lower-thirds, burned-in Hindi/English subtitles, end card, thumbnail, SRT |
| `qa_checks.py` | blank frames, missing character, head cut / out of frame, frozen frames, A/V length, mouth-vs-audio |
| `registry.py` | every function by name + JSON schema + validation + `Shot` runner + `audio_plan` |
| `asset_coverage.py` | maps `stories/hindi/ASSET_NEEDS.json` (or the built-in brief) to functions |

Configurable, never bundled: `audio_mix.SFX_LIBRARY = {name: file}`, `AMBIENCE_LIBRARY = {location: file | [files]}`, title font path (default Noto Sans Devanagari Bold), Latin fallback font `titles.LATIN_FONT`.

## Conventions for real art
* Human rig JSON: `size [w,h]`, `joints` {pelvis, neck, head_top, shoulder_l/r, elbow_l/r, wrist_l/r, hand_l/r (+ hand_tip), hip_l/r, knee_l/r, ankle_l/r, toe_l/r}, optional `radii`, `feet`.
* Animal rig JSON: `kind` (goat dog cow buffalo cat donkey bullock; hen parrot for birds), `spine_a` / `spine_b`, legs `ff hf fn hn` (far/near, front/hind), `leg_len`, `radii`.
* A walk/run solves its step rate from `speed` (px/s) or `distance`, so feet do not slide. Finished motions keep only their travelled distance; `hold=True` motions keep the last pose.

'''


def ref():
    out = ["## Function reference (generated from the registry)\n"]
    titles = {"motion": "Human motions (`who` kind `human`)", "animal_motion": "Animal motions (kind `animal`)", "bird_motion": "Bird motions (kind `bird`)", "monkey_motion": "Monkey motions (kind `monkey`; also all human motions)",
              "effect": "Effects", "camera": "Camera moves", "transition": "Transitions", "prop_motion": "Prop motions", "life": "Scene life", "ambient": "Scene-life presets", "title": "Titles",
              "sfx": "SFX names (placeholders)", "ambience": "Ambience locations", "time": "Time", "qa": "QA checks"}
    for kind, name in titles.items():
        ents = R.REGISTRY[kind]; out.append(f"### {name} ({len(ents)})\n")
        if kind in ("sfx", "ambience"): out.append(", ".join(f"`{n}`" for n in sorted(ents)) + "\n"); continue
        out.append("| name | parameters (default) | what it does |\n|---|---|---|")
        for n in sorted(ents):
            e = ents[n]; ps = e.params if isinstance(e.params, dict) else {}
            pr = ", ".join(f"`{k}`" + (f"={v!r}" if v is not None and not callable(v) and len(repr(v)) < 24 else "") for k, v in ps.items() if k not in ("seed",))
            out.append(f"| `{n}` | {pr} | {(e.doc or '').replace('|', '/').replace(chr(10), ' ')[:150]} |")
        out.append("")
    return "\n".join(out)


def coverage():
    rep = AC.report(); c = rep["counts"]
    L = ["## Coverage", f"Checked against: {rep['source']} - {rep['total']} needs: **{c['implemented']} implemented, {c['weak']} weak, {c['not_possible']} not possible in 2D cut-out, {c['missing']} missing**.\n",
         "| area | status | what / reason |", "|---|---|---|",
         "| 27 human motions (idle ... dance_simple) | implemented | mesh puppet; arms/legs bend smoothly, rigid-piece fallback past ~35-57 degrees |",
         "| walk / run / tiptoe | implemented | cadence solved from speed or distance; no foot sliding |",
         "| animals: goat dog cow buffalo cat donkey bullock | implemented | 22 motions (walk trot gallop hop sit lie_down sleep graze bark bleat moo wag scratch shake_off butt beg steal_and_run ...) |",
         "| birds: hen parrot | implemented | flap, fly, hop, peck, walk, squawk |", "| monkey | implemented | reuses the human rig + swing + jump |",
         "| 53 effects (weather, fire/light, marks, camera) | implemented | cached/low-res glows, all under ~0.1 s per frame |",
         "| camera moves, parallax, focus pull, dutch, framing rules | implemented / weak | parallax needs the artist to supply 2-4 depth layers; focus pull blurs whole layers, not single objects |",
         "| 11 transitions | implemented / weak | flashback = colour treatment + dissolve only; meanwhile = text card, no drawn art |",
         "| 17 prop motions | implemented | thrown / bounced / poured / swung / kite / door / coins ... |", "| scene life (8 elements, 5 presets) | implemented | birds, villagers, cattle, smoke, tree sway, water wheel, cycle, mela crowd |",
         "| audio mix (duck, SFX, ambience, -14 LUFS) | implemented | SFX/ambience files are the owner's; synthetic placeholders until then |",
         "| titles / subtitles / end card / thumbnail | implemented | Devanagari shaping via Raqm; font path configurable |", "| QA checks | implemented | no AI: heuristics on pixels and audio loudness |",
         "| fire / flame, dance, fall styles | weak | stylised sprites; dance is one simple loop; falls come in fixed styles |",
         "| turnarounds, side/back views | not possible in 2D cut-out | one drawn view per character; needs extra drawn art |",
         "| realistic fluid / cloth simulation | not possible in 2D cut-out | stylised water, flag and clothesline effects instead |",
         "| morphing / transformations | not possible in 2D cut-out | needs drawn in-betweens; hide a sprite swap behind a flash or dissolve |",
         "| per-phoneme lip-sync | not possible in 2D cut-out | open/closed mouth from audio loudness; visemes need extra drawn mouths |", ""]
    gaps = [r for r in rep["rows"] if r["status"] != "implemented"]
    if gaps:
        L += ["### Needs that are weak / not possible / missing", "| need | status | note |", "|---|---|---|"]
        L += [f"| {r['need'][:70]} | {r['status']} | {r['note']} |" for r in gaps]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    p = os.path.join(HERE, "TOOLKIT.md"); open(p, "w", encoding="utf-8").write(INTRO + ref() + "\n" + coverage()); print("wrote", p, os.path.getsize(p), "bytes")
