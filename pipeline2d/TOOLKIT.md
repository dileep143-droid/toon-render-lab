# 2D animation toolkit (pipeline2d)

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

## Function reference (generated from the registry)

### Human motions (`who` kind `human`) (33)

| name | parameters (default) | what it does |
|---|---|---|
| `carry_object` | `hands`='both', `height`=0.55 | arms hold something in front of the chest; Pose.tags['hold'] = joints whose midpoint is the object anchor |
| `clap` | `hz`=3.0 |  |
| `clap_dance` | `hz`=1.6 | side-step sway with a clap on every beat: hands meet in front of the chest, then open wide; knees dip on the beat |
| `cry_rub_eyes` | `hz`=3.2 |  |
| `dance_simple` | `hz`=1.4 |  |
| `fall_comic` |  | topples backwards: arms windmill, slams down, one squashy bounce, stays lying |
| `fall_sit_bump` |  | loses balance and plops down on the bottom: a wobble, a quick drop with a squash 'bump', hands fly up, then sits dazed with the legs splayed |
| `fall_slip_peel` |  | slips on a banana peel: the feet shoot forward and up, the body hangs in the air arms flailing, then slams down flat on the back with one bounce |
| `fall_trip_forward` |  | trips and pitches forward: a stumble lunge or two, arms thrown ahead, then a flop face-down (lies along the walking direction) with a squashy bounce |
| `garba_turn_clap` | `hz`=2.0 | garba step: three claps (hands right, left, centre of the chest) then a quick turn on the spot; a cut-out cannot rotate in depth, so the turn is a nar |
| `give` | `side`='r' |  |
| `hand_to_mouth` | `side`='r', `bites`=3 |  |
| `hands_on_hips` |  |  |
| `head_shake` | `times`=3, `amount`=10.0 |  |
| `head_tilt` | `amount`=14.0, `side`='r' |  |
| `hop_dance` | `hz`=1.5, `height`=0.05 | happy hopping: both feet leave the ground on every beat, arms up and out in the air, a small squash on landing |
| `idle_breathe` | `rate`=0.28, `amount`=1.0, `sway`=1.0 |  |
| `jump` | `height`=0.18 | crouch (anticipation) -> launch -> air (stretch) -> land (squash) -> settle; height = jump height in character heights |
| `laugh_bounce` | `hz`=4.0 |  |
| `namaste` |  |  |
| `nod` | `times`=2, `amount`=12.0 |  |
| `point` | `side`='r', `abd`=95.0 |  |
| `reach_take` | `side`='r', `abd`=80.0 | arm stretches out (leaning in), the hand grabs, arm comes back; Pose.tags['grab'] = 1 at the moment of the grab |
| `run_cycle` | `speed`, `distance`, `hz` |  |
| `scratch_head` | `side`='r', `hz`=4.5 |  |
| `shrug` |  |  |
| `sit_down` | `depth`=0.22 | lower the body onto a seat `depth` (character heights) below the standing height; side view: thighs forward, knees bent; front view: legs splay. Holds |
| `sneak` | `hz`=0.7, `speed` | sneaking: small slow steps on tiptoe, hunched, arms held in; travel speed matches the cadence |
| `stand_up` | `depth`=0.22 |  |
| `think` | `side`='r' |  |
| `tiptoe` | `hz`=0.7, `speed` | sneaking: small slow steps on tiptoe, hunched, arms held in; travel speed matches the cadence |
| `walk_cycle` | `speed`, `distance`, `hz`, `amp` | walk. Give distance (rig px, covered in dur) or speed (rig px / s) and the cadence is solved so the feet do not slide; else hz. The walked distance is |
| `wave` | `side`='r', `hz`=2.2, `amount`=1.0 |  |

### Animal motions (kind `animal`) (22)

| name | parameters (default) | what it does |
|---|---|---|
| `bark` |  |  |
| `beg` |  | sits up on the hind legs, front paws folded, tail wagging |
| `bleat` |  |  |
| `bray` |  |  |
| `butt` |  | goat head-butt: rock back and lower the head, charge forward, hit, recoil |
| `eat` | `bites`=4 | head down to the ground, chewing; the feet stay planted |
| `gallop` | `speed`, `distance`, `hz` | gallop (front pair / hind pair, body pitching, stretching) |
| `graze` | `bites`=4 | head down to the ground, chewing; the feet stay planted |
| `hop` | `height`=0.35 | all four feet leave the ground: crouch, spring, tuck, land (cat / dog / kid goat) |
| `idle` |  |  |
| `lie_down` |  |  |
| `meow` |  |  |
| `moo` |  |  |
| `run` | `speed`, `distance`, `hz` | gallop (front pair / hind pair, body pitching, stretching) |
| `scratch` |  | sits back on one hind leg and scratches the ear / neck |
| `shake_off` |  | whole-body shake, decaying (wet dog / goat) |
| `sit` |  | dog sits: the rump drops, the front legs stay planted; hind legs fold |
| `sleep` |  |  |
| `steal_and_run` | `speed` | snatch a prop with the mouth, then run off with it (Pose.tags['carry'] = 'mouth' once it is grabbed) |
| `trot` | `speed`, `distance`, `hz` |  |
| `wag_tail` | `speed`='fast' |  |
| `walk` | `speed`, `distance`, `hz` |  |

### Bird motions (kind `bird`) (7)

| name | parameters (default) | what it does |
|---|---|---|
| `flap` | `hz`=5.0 |  |
| `fly` | `hz`=4.5, `speed`, `distance` | flying across: fast wing beats, body rising and falling, legs tucked; Pose.travel = the distance flown |
| `hop` | `height`=0.12 |  |
| `idle` |  |  |
| `peck` | `pecks`=3 |  |
| `squawk` |  |  |
| `walk` | `hz`=2.0, `speed` |  |

### Monkey motions (kind `monkey`; also all human motions) (2)

| name | parameters (default) | what it does |
|---|---|---|
| `monkey_jump` |  |  |
| `swing` | `hz`=0.8 | hangs from both hands and swings like a pendulum: arms stay up (absolute aim), body and legs trail |

### Effects (56)

| name | parameters (default) | what it does |
|---|---|---|
| `anger_mark` | `anchor`, `size`=56.0, `dur`=2.0 | the red 'anger vein' cross pulsing at the temple |
| `aura` | `anchor`, `radius`=150.0, `color`=(255, 220, 90), `strength`=0.7, `dur`, `particles`=True | a pulsing glow around the character (magic power, blessing) with sparks rising |
| `blush` | `anchors`, `anchor`, `dx`=44.0, `dy`=22.0, `size`=30.0, `color`=(255, 110, 130), `dur` | pink blush patches on both cheeks, pulsing |
| `bonfire` | `pos`=(0.5, 0.82), `size`=1.0, `light`=0.6 | a big campfire: logs, 5 large flames, rising sparks, flickering light on the surroundings, smoke |
| `chulha` | `pos`=(0.5, 0.82), `size`=1.0, `smoke_on`=True | a clay stove fire: three flames, flying sparks, a warm glow and rising smoke |
| `clouds` | `count`=4, `speed`=14.0, `y`=(0.04, 0.3), `tintc`=(255, 255, 255), `opacity`=0.9 | soft clouds drifting right to left (or left to right with a negative speed) |
| `dawn_grade` | `amount`=1.0, `softness`=0.5, `horizon`=0.6, `haze`=0.25 | early-morning look: lifted lavender shadows, pink-gold light low on the horizon, a milky haze and a soft bloom (amount 0..1) |
| `diya` | `pos`=(0.5, 0.8), `size`=46.0, `light`=0.5 | a clay diya with a flame; casts a warm flickering light on what is around it |
| `dizzy_stars` | `anchor`, `size`=26.0, `count`=4, `dur` | stars circling above the head (knocked silly) |
| `dusk_grade` | `amount`=1.0, `softness`=0.5, `horizon`=0.62, `vignette`=0.5 | warm evening look: orange-amber light, deep purple-brown shadows, a glowing horizon, darker corners and a soft bloom (amount 0..1) |
| `evening_lamp_grade` | `lamps`, `amount`=1.0, `darkness`=0.55, `color`=(255, 205, 120), `flicker`=0.1 | lamp-lit evening: the scene falls into a blue-brown dusk and each lamp [(x, y, radius), ...] (px or fractions) lights its surroundings in warm colour, |
| `exclaim` | `anchor`, `size`=70.0, `dur`=1.6, `color`=(255, 70, 60) | a '!' slamming in above the head (startled / realised) |
| `exclaim_question` | `anchor`, `size`=60.0, `dur`=2.0 | '!?' - surprised and confused |
| `festival_lights` | `points`, `count`=16, `speed`=2.2, `sag`=0.06 | Diwali / mela string lights along a sagging wire: bulbs chase in colour |
| `fireflies` | `count`=24, `region`=(0.0, 0.35, 1.0, 0.95), `color`=(220, 255, 120) | wandering fireflies, each blinking on its own rhythm |
| `fireworks` | `origins`, `gap`=0.9, `count`=72, `life`=1.9, `intensity`=1.0 | bursting fireworks: radial sparks with gravity, trails and a flash; a new burst every `gap` seconds |
| `flame` | `pos`=(0.5, 0.8), `size`=70.0, `glow`=1.0 | a single flickering flame (pos = base point, px or fractions) |
| `flash_white` | `start`=0.0, `dur`=0.25, `color`=(255, 255, 255), `peak`=1.0 | white (or coloured) screen flash with a fast attack and an ease-out decay |
| `fog` | `intensity`=0.5, `color`=(235, 240, 245), `speed`=26.0, `low`=True | drifting mist: two scrolling noise layers; low=True keeps it thicker near the ground |
| `gloom_cloud` | `anchor`, `size`=130.0, `rain`=True, `dur` | a small dark rain cloud over a sulking head |
| `grade` | `preset`='dusk', `amount`=1.0 | colour grade presets: night dawn dusk sunset noon overcast sepia warm cool golden memory (amount 0..1) |
| `hearts` | `anchor`, `size`=34.0, `count`=5, `dur`, `color`=(255, 90, 130) | hearts floating up from the head, swaying and fading (love / affection) |
| `heat_shimmer` | `region`=(0.0, 0.45, 1.0, 0.75), `amp`=3.0, `freq`=0.011, `speed`=2.5 | hot-air wobble: rows of the region shift sideways by a travelling sine |
| `holi_burst` | `pos`=(0.5, 0.5), `colors`, `count`=80, `size`=1.0, `dur`=2.2 | a cloud of coloured powder (Holi gulal / rangoli colour) bursting outward with drag, then settling and fading |
| `idea_bulb` | `anchor`, `size`=70.0, `dur`=2.0 | a light bulb popping on above the head with flashing rays (an idea!) |
| `impact_star` | `anchor`, `size`=160.0, `text`='POW', `dur`=0.8, `color`=(255, 215, 50) | comic impact burst with a word: pops with overshoot, jitters, fades |
| `lamp_glow` | `pos`=(0.5, 0.4), `radius`=260.0, `color`=(255, 210, 130), `strength`=0.6, `flicker`=0.12 | a warm pool of light around a lamp / bulb, flickering a little |
| `leaves` | `count`=24, `wind`=40.0, `fall`=110.0, `colors` | leaves (or petals, kind='petal') drifting down with a sway and a slow spin |
| `lightning` | `intensity`=1.0, `rate`=0.3, `bolt`=True, `flash`=True | random lightning (about `rate` per second): a cold white flash with a double flicker and a jagged glowing bolt |
| `music_notes` | `anchor`, `size`=36.0, `count`=4, `dur` | notes floating up and swaying (happy humming, singing) |
| `night` | `strength`=1.0, `stars`=True, `moon`=(0.82, 0.14), `sky`=0.55 | night: blue grade, twinkling stars in the upper sky, a glowing moon |
| `petals` | `count`=30, `wind`=30.0, `fall`=90.0, `colors` | flower petals drifting down (weddings, festivals, Holi-free spring) |
| `puddle` | `center`=(0.5, 0.88), `size`=(0.18, 0.045), `rain`=True, `sky`=(170, 200, 230), `reflect`=0.55 | a puddle: mirrors the picture above it (wobbling), tinted toward the sky; with rain=True ring ripples spread across it |
| `question` | `anchor`, `size`=64.0, `dur`=2.0, `color`=(255, 220, 60), `dx`=0.0 | a '?' popping above the head with a little wobble (also used by exclaim / exclaim_question) |
| `rain` | `intensity`=0.7, `angle`=12.0, `speed`=1500.0, `length`=34.0, `color`=(205, 220, 240), `layers`=2, `splashes`=True, `ground`=0.8, `wet`=0.0 | slanted rain streaks in `layers` depth layers (far = short + faint, near = long + bright), splash rings on the ground band |
| `rainbow` | `intensity`=0.5, `center`=(0.5, 1.15), `radius`=0.7, `grow`=2.0 | a rainbow arc that grows in from the left over `grow` seconds |
| `shake` | `amp`=10.0, `freq`=22.0, `intensity`=1.0, `rot`=0.6 | camera shake: the frame jitters by `amp` px (and a touch of rotation). Zoomed in 3% so no border shows. |
| `smear` | `sprite`, `path`, `n`=4, `step`=0.035, `opacity`=0.5 | motion smear: `n` fading ghost copies of an RGBA sprite trailing behind its path [[t, x, y], ...] (linear between keys) |
| `smoke` | `pos`=(0.5, 0.6), `rise`=90.0, `drift`=25.0, `count`=14, `size`=60.0, `color`=(120, 120, 125), `opacity`=0.5, `life`=3.2 | soft grey puffs rising from a point, widening and fading (chimney, chulha, bonfire) |
| `snow` | `intensity`=0.6, `wind`=30.0 | soft snow flakes in 3 depth layers |
| `sparklers` | `pos`=(0.5, 0.6), `intensity`=1.0, `size`=1.0 | a phuljhadi: a hot white centre throwing many short sparks in all directions |
| `sparkles` | `anchor`, `radius`=90.0, `count`=6, `size`=28.0, `dur`, `color`=(255, 245, 160) | twinkling four-point stars around a point (shiny, magical, proud) |
| `speed_lines` | `anchor`, `mode`='radial', `angle`=180.0, `intensity`=0.8, `color`=(255, 255, 255), `count`=36, `inner`=0.28 | manga speed lines: radial (burst out of a point) or parallel (mode='dir', direction `angle`) |
| `steam` | `pos`=(0.5, 0.6), `rise`=70.0, `count`=7, `width`=26.0, `opacity`=0.5 | thin curling wisps of steam (tea, hot food): smoke with a narrow sine wiggle |
| `storm` | `intensity`=1.0 | heavy rain + dark sky + lightning (one call) |
| `sun_rays` | `intensity`=0.5, `origin`=(0.82, -0.05), `color`=(255, 240, 190) | god rays fanning out of a point (slowly turning and shimmering) |
| `sweat_drop` | `anchor`, `size`=34.0, `dur`=2.0, `side`=1.0 | a nervous sweat drop slides down the side of the head |
| `sweat_spray` | `anchor`, `size`=26.0, `dur`=1.2 | drops flung off both sides of the head (panic / hard effort) |
| `tears` | `anchor`, `eye_dx`=34.0, `eye_dy`=4.0, `length`=140.0, `dur`, `size`=1.0 | streams of tears running down from both eyes (anchor = between the eyes) |
| `torch` | `pos`=(0.4, 0.5), `angle`=0.0, `length`=520.0, `spread`=26.0, `darkness`=0.55, `color`=(255, 235, 190) | torchlight: the frame goes dark except for a cone from `pos` pointing at `angle` degrees (0 = right) with soft edges |
| `vignette` | `strength`=0.55, `soft`=0.7 | darker corners (focus on the middle; use heavier for night / fear) |
| `water` | `region`=(0.0, 0.7, 1.0, 1.0), `flow`=(60.0, 0.0), `ripple`=3.0, `tintc`=(70, 140, 200), `tint_amount`=0.25, `highlights`=0.4, `ellipse`=False | moving water inside a rect / polygon region: wavy displacement, a flow-direction scroll of sparkling highlights, a blue tint |
| `wet` | `amount`=0.5 | rainy look: darker, a little desaturated and bluish |
| `wind` | `intensity`=0.6, `direction`=1.0, `leaves`=True, `dust`=True | gusting wind: horizontal dust streaks and leaves blown across the frame |
| `zoom_punch` | `start`=0.0, `dur`=0.35, `amount`=0.12, `center`=(0.5, 0.5) | a quick punch-in on a beat: zoom up by `amount` and settle back (t is local time) |
| `zzz` | `anchor`, `size`=46.0, `dur`, `color`=(235, 245, 255) | sleeping Z's rising and growing from the head |

### Camera moves (9)

| name | parameters (default) | what it does |
|---|---|---|
| `dutch` | `start`, `angle`=8.0, `ease`='smooth' | comic dutch tilt (rotates the frame; render_view zooms in just enough to hide the corners) |
| `focus_pull` | `start`, `to`, `from_focus`, `amount`, `ease`='smooth' | rack focus: the sharp depth glides from `from_focus` (default: the Cam's current focus, else near) to `to` (a depth, or 'sky' / 'far' / 'near'); every |
| `follow` | `path`, `zoom`=1.6, `lag`=0.3, `taps`=14, `offset`=(0.0, -0.05) | track a moving point: path = [[t, x, y], ...] (plate fractions). The camera sits on a low-passed copy of the path (exponential kernel of time constant |
| `hold` | `cam` |  |
| `ken_burns` | `ease`='smooth' | slow pan + zoom from Cam a to Cam b (zoom is interpolated geometrically so it feels constant) |
| `pull_out` | `start`, `end`, `ease`='smooth' | pull-out reveal: start tight (a Cam), end wide (default: the whole plate) |
| `push_in` | `start`, `target`, `amount`=1.4, `ease`='smooth', `pull`=0.75 | dolly toward a speaker at `target` (plate fractions): zoom x amount while the centre slides `pull` of the way to the target |
| `two_shot` | `start`, `a_pt`, `b_pt`, `margin`=0.2, `ease`='smooth', `max_z`=3.0 | frame two points (plate fractions) with `margin` around them; slightly above centre for head room |
| `whip_pan` | `start`, `to`, `blur_px`=90.0 | a very fast pan: ease-in then crash-stop, with directional motion blur = half the distance the picture travels per frame (a 180 degree shutter) |

### Transitions (11)

| name | parameters (default) | what it does |
|---|---|---|
| `clock_spin` | `radius`=130, `turns`=3 | time skip: a clock pops up over a darkened cross-dissolve, the hands spin fast, the clock shrinks away |
| `cut` | `at`=0.5 | hard cut |
| `dip_black` | `hold`=0.1 | fade to black, then up on the next shot |
| `dip_white` | `hold`=0.1 | flash through white (memories, magic, a bright cut) |
| `dissolve` | `ease`=True | cross-dissolve |
| `flashback` | `amp`=14.0, `blur`=5.0, `sepia`=0.8 | dreamy flashback: the picture ripples sideways, blurs and washes to sepia, cross-fading to b which clears up again |
| `iris` | `center`=(0.5, 0.5), `style`='close_open', `soft`=3.0 | cartoon iris: the picture shrinks into a circle around `center` (close) and the next shot opens from it. style='open': b grows out of a circle over a  |
| `meanwhile` | `text`='Meanwhile...', `font`, `color`=(250, 220, 120), `text_color`=(80, 40, 20), `size`=96, `hold`=0.5 | a title card between the shots (a fades into the card, the card holds, then fades into b). Devanagari: pass font='NotoSansDevanagari-Bold.ttf' |
| `page_turn` | `side`='right', `curl`=0.14 | the outgoing page peels away from the right (or left) edge: you see its back (lighter, mirrored) curling over and a shadow on the next page |
| `star_wipe` | `center`=(0.5, 0.5), `turns`=0.5, `points`=5 | a star grows from `center`, spinning, and b shows inside it (cartoon scene change) |
| `wipe` | `direction`='left', `soft`=0.08, `ease`=True | b wipes over a, the edge travelling toward `direction` (left / right / up / down / diag) with a soft edge |

### Prop motions (19)

| name | parameters (default) | what it does |
|---|---|---|
| `ball_bounce` | `x0`=100.0, `x1`=900.0, `y_top`=100.0, `ground_y`=500.0, `bounces`=4, `scale`=1.0 | a ball bouncing along the ground from x0 to x1 (rolling spin, shadow, getting lower each bounce) |
| `clock_hands` | `center`=(0, 0), `radius`=100.0, `start`=(10, 10), `speed`=60.0, `to`, `color`=(60, 35, 25), `scale`=1.0 | clock hands: `speed` simulated minutes per second from `start` (hh, mm); or to=(hh, mm) sweeps there (with a little overshoot) in dur s. sprite (optio |
| `clothesline` | `line`=((0, 0), (100, 0)), `items`, `count`=4, `sag`=0.06, `sway`=9.0, `scale`=1.0 | washing on a line: the rope sags, each cloth hangs from its peg and swings in the breeze (phase per item). sprite = one cloth, or items = [sprites] |
| `coins` | `hand`=(0, 0), `targets`=((100, 100),), `start`=0.0, `interval`=0.4, `hop`=70.0, `fly`=0.5, `scale`=1.0, `count_style` | coins / sweets counted out one by one: each pops from the hand, arcs to its target (a small bounce on landing) and stays; interval s apart |
| `door` | `hinge`=(0, 0), `side`='left', `start`=0.0, `max_angle`=80.0, `close_at`, `scale`=1.0 | a door (or window shutter) opening about its hinge edge: the free edge swings toward the viewer / away with perspective, darker as it turns. hinge = t |
| `fall_bounce` | `x`=0.0, `y0`=0.0, `ground_y`=400.0, `fall_time`=0.5, `restitution`=0.5, `bounces`=3, `squash`=0.28, `scale`=1.0, `shadow`=True | drops from y0 to the ground and bounces `bounces` times (each lower by `restitution`^2), squashing on impact and stretching in flight. The sprite's bo |
| `fan` | `center`=(0, 0), `rpm`=120.0, `spin_up`=1.0, `blur`=True, `scale`=1.0 | ceiling-fan blades (a sprite of the whole fan head seen from below): rotation with spin-up; above ~240 deg/frame it smears into a disc |
| `flag` | `pole_top`=(0, 0), `amp`=14.0, `wavelength`=0.55, `speed`=5.0, `scale`=1.0 | a flag / banner waving: vertical sine displacement growing toward the free end, with light and shade along the folds. Left edge sits on the pole. |
| `food_disappear` | `pos`=(0, 0), `start`=0.0, `bites`=3, `bite_every`=0.5, `mouth`, `crumbs`=True, `scale`=1.0, `ground`, `anchor`=(0.5, 0.5) | a laddoo / roti / fruit eaten in `bites` (default 3): every bite cuts a scalloped tooth-mark chunk from the side facing `mouth` (or a varied side), th |
| `food_eaten_by_animal` | `pos`=(0, 0), `mouth`=(0, 0), `start`=0.0, `snatch`=0.22, `chomps`=3, `chomp_every`=0.3, `crumbs`=True, `scale`=1.0, `hop`=60.0, `ground`, `anchor`=(0.5, 0.5) | an animal snatches the food: it zips from `pos` to the animal's `mouth` in `snatch` s on a short arc (stretching along the way), is held in the mouth  |
| `food_vanish` | `pos`=(0, 0), `start`=0.0, `bites`=3, `bite_every`=0.45, `crumbs`=True, `scale`=1.0, `anchor`=(0.5, 0.5) | a laddoo / roti / fruit eaten: `bites` round bites (one every bite_every s) are taken from its edge, crumbs fall; after the last bite it is gone |
| `kite` | `hand`=(0, 0), `kite_pos`=(0, 0), `bob`=26.0, `sway`=40.0, `tail`=True, `string_color`=(250, 250, 250), `scale`=1.0 | a kite on a string: the kite drifts and tilts in the wind, the string hangs in a curve from the hand, a ribbon tail waves below it |
| `paper_fly` | `p0`=(0, 0), `p1`=(100, 0), `flutter`=1.0, `scale`=1.0 | a sheet of paper fluttering from p0 to p1: it flips over (width shrinks and returns), rocks, and sways side to side |
| `pour` | `spout`=(0, 0), `target`=(0, 0), `color`=(240, 235, 225), `width`=14.0, `level_rect`, `tilt`=40.0, `vessel_pos`, `scale`=1.0 | liquid (milk, water, tea) poured from `spout` down to the surface at `target`. The stream grows, runs, thins and stops; `level_rect` (x0, y0, x1, y1)  |
| `roll` | `p0`=(0, 0), `p1`=(100, 0), `radius`, `scale`=1.0 | rolls from p0 to p1, slowing with friction; rotation = distance / radius (no slipping) |
| `slide` | `p0`=(0, 0), `p1`=(100, 0), `ease`='out', `tilt`=0.0, `scale`=1.0 | slides and settles (plate across a table, book on the floor), stretching a touch while it is fast |
| `stir` | `center`=(0, 0), `radius`=26.0, `hz`=1.4, `tilt`=14.0, `bowl`, `swirl`=True, `scale`=1.0 | a spoon circling in a pot / bowl (bowl = (cx, cy, rx, ry) ellipse where a swirl of rings is drawn) |
| `swing` | `pivot`=(0, 0), `rope`=300.0, `amp`=30.0, `period`=2.4, `decay`=0.0, `seat_gap`=0.0, `rope_width`=4.0, `spread`=0.0, `scale`=1.0, `rope_color`=(120, 85, 50) | jhula: ropes from `pivot` to a seat that swings like a pendulum (amp degrees, period s, optional decay). spread = distance between the two ropes |
| `throw` | `p0`=(0, 0), `p1`=(100, 0), `height`=200.0, `spin`=360.0, `vanish`=False, `scale`=1.0 | thrown object: a parabola from p0 to p1 reaching `height` px above the straight line, spinning `spin` degrees |

### Scene life (9)

| name | parameters (default) | what it does |
|---|---|---|
| `birds` | `count`=5, `y`=(0.08, 0.3), `speed`=70.0, `direction`=1, `size`=34, `formation`='v', `color`=(40, 40, 50), `flap_hz`=2.6 | flocks of birds crossing the sky. formation 'v' (leader + two trailing lines) or 'scatter' |
| `cattle` | `pos`=(0.3, 0.8), `count`=3, `size`=110, `spread`=150.0 | cows grazing: each one lowers its head, chews, lifts it, looks round; tails swish; a slow drift. pos = centre of the herd |
| `chimney_smoke` | `pos`=(0.2, 0.42), `wind`=1.0, `height`=280.0, `count`=22, `size`=44.0, `opacity`=0.62, `color`=(150, 148, 152), `gust`=1.0, `life_s`=4.5 | a smoke column rising from a chimney point and leaning with the wind: `wind` (-2..2, + = to the right) bends it more the higher it climbs, gusts trave |
| `crowd` | `region`=(0.05, 0.7, 0.95, 0.95), `count`=40, `height`=(40, 76), `waving`=0.12 | a mela / gathering: `count` small figures standing and bobbing (some wave, some sway), back rows smaller, drawn back to front |
| `cycle` | `y`=0.8, `start`=0.0, `direction`=1, `size`=170, `repeat`=False, `body`=(200, 50, 50), `shirt`=(240, 200, 60) | a bicycle with a rider crossing the frame in `dur` s; wheels turn and legs pedal (repeat=True loops it) |
| `smoke` | `pos`=(0.5, 0.45), `count`=10, `size`=44.0, `drift`=18.0 | smoke curling out of a chimney / chulha (effects.smoke) |
| `tree_sway` | `pos`=(0.5, 0.8), `amp`=0.035, `freq`=0.35 | draw a tree / bush / banana plant sprite swaying in the wind (its base stays planted at pos) |
| `villagers` | `count`=5, `y`=(0.62, 0.78), `height`=(34, 70), `speed`=26.0, `hz`=1.6 | small villagers walking along the ground band (further up the band = smaller, slower). Mixed colours, pots, bundles; they pass in both directions |
| `water_wheel` | `pos`=(0.8, 0.7), `radius`=70.0, `rpm`=7.0 | a water wheel: rim, spokes, paddles carrying little buckets, water pouring from a chute into the top buckets |

### Scene-life presets (5)

| name | parameters (default) | what it does |
|---|---|---|
| `farm` |  | bundle: cattle, villagers, birds |
| `mela` |  | bundle: crowd, birds |
| `road` |  | bundle: cycle, villagers, birds |
| `village_evening` |  | bundle: birds, villagers, cattle, smoke |
| `village_morning` |  | bundle: birds, villagers, cattle, smoke |

### Titles (4)

| name | parameters (default) | what it does |
|---|---|---|
| `end_card` | `moral`='', `header`='सीख', `subscribe`, `font`, `size`=(1280, 720), `c1`=(255, 240, 200), `c2`=(250, 170, 90) | the closing card: a header ("सीख" / "Moral"), the moral wrapped big, and a Subscribe button that pulses with a swinging bell |
| `lower_third` | `name`='', `role`='', `start`=0.0, `font`, `side`='left', `color`=(230, 80, 50), `y`=0.7, `size`=44 | a name caption sliding in from the `side` edge (0.4 s), holding, sliding out; role is a smaller second line |
| `subtitles` | `lines`, `font`, `size`, `color`=(255, 255, 255), `color2`=(255, 230, 140), `max_w`=0.86, `bottom`=0.045, `box`=True | burn the subtitle line(s) active at time t into the frame: a rounded translucent box, white text with a dark outline, wrapped to the safe width; "text |
| `title_card` | `series`='सोनपुर की टोली', `episode`='', `subtitle`='', `font`, `size`=(1280, 720), `c1`=(255, 230, 140), `c2`=(240, 130, 60), `text_rgb`=(255, 252, 235), `stroke_rgb`=(120, 40, 20), `rays`=14, `tagline`='' | animated opening card at time t: warm rays turning behind, the series name popping in word by word (overshoot), the episode title sliding up, a little |

### SFX names (placeholders) (11)

`boing`, `click`, `coin`, `crunch`, `ding`, `laugh_pop`, `pop`, `splash`, `tada`, `thud`, `whoosh`

### Ambience locations (11)

`field`, `indoors`, `mela`, `night`, `rain`, `river`, `school`, `silence`, `storm`, `village_day`, `village_evening`

### Time (1)

| name | parameters (default) | what it does |
|---|---|---|
| `freeze_time` | `at`, `hold`=1.0 | freeze-frame: {"freeze": true, "at": s, "hold": s} - the picture stops at `at` for `hold` seconds |

### QA checks (6)

| name | parameters (default) | what it does |
|---|---|---|
| `av_length` | `video`, `audio`, `tol`=0.15 | video container vs audio duration. audio=None -> uses the audio stream of the video file itself (container vs the longest stream is not split by ffmpe |
| `blank_frames` | `frames`, `fps`=24, `dark`=10.0, `flat`=3.0, `allow_edge`=0.0 | black (mean luma < dark) or flat (std < flat) frames. allow_edge = seconds at the start/end where a fade-from/to-black is fine. |
| `framing` | `boxes`, `size`=(1280, 720), `head_margin`=0.05, `who`, `fps`=24, `shot`='close', `allow_out`=2, `t0`=0.0 | boxes = per-frame character bbox (x0,y0,x1,y1) in pixels (or None) - from bbox_of_alpha of the sprite, or `fg_bbox`. Flags: partly outside the frame ( |
| `frozen_frames` | `frames`, `fps`=24, `motion`, `min_dur`=0.6, `eps`=0.02 | runs of identical frames longer than min_dur. motion = [(start,end)...] windows where movement is planned (None = whole video). |
| `lipsync` | `mouth`, `rms`, `fps`=24, `who`, `loud`=0.02, `quiet`=0.006, `open_thr`=0.35, `min_dur`=0.25, `offset`=0.0 | mouth: per-frame openness 0..1 (or 0/1 state) for ONE speaker; rms: per-frame audio loudness (audio_mix.rms_track). mouth open while the audio is sile |
| `missing_character` | `frames`, `plate`, `actors`, `fps`=24, `min_cover`=0.04, `thr`=24, `step`=3 | actors = [{"who", "box", "start", "end"}]. A box whose foreground coverage stays below min_cover is an empty spot -> the character is missing. plate:  |

## Coverage
Checked against: built-in brief checklist (stories/hindi/ASSET_NEEDS.json not found) - 157 needs: **146 implemented, 8 weak, 3 not possible in 2D cut-out, 0 missing**.

| area | status | what / reason |
|---|---|---|
| 27 human motions (idle ... dance_simple) | implemented | mesh puppet; arms/legs bend smoothly, rigid-piece fallback past ~35-57 degrees |
| walk / run / tiptoe | implemented | cadence solved from speed or distance; no foot sliding |
| animals: goat dog cow buffalo cat donkey bullock | implemented | 22 motions (walk trot gallop hop sit lie_down sleep graze bark bleat moo wag scratch shake_off butt beg steal_and_run ...) |
| birds: hen parrot | implemented | flap, fly, hop, peck, walk, squawk |
| monkey | implemented | reuses the human rig + swing + jump |
| 53 effects (weather, fire/light, marks, camera) | implemented | cached/low-res glows, all under ~0.1 s per frame |
| camera moves, dutch, framing rules | implemented | |
| parallax from one background | implemented / weak | auto-split into sky / far / near by luminance + edge heuristics; hand-made depth layers look better |
| focus pull (rack focus) | implemented / weak | blur per depth layer, not per object |
| 11 transitions | implemented / weak | flashback = colour treatment + dissolve only; meanwhile = text card, no drawn art |
| 17 prop motions | implemented | thrown / bounced / poured / swung / kite / door / coins ... |
| scene life (8 elements, 5 presets) | implemented | birds, villagers, cattle, smoke, tree sway, water wheel, cycle, mela crowd |
| audio mix (duck, SFX, ambience, -14 LUFS) | implemented | SFX/ambience files are the owner's; synthetic placeholders until then |
| titles / subtitles / end card / thumbnail | implemented | Devanagari shaping via Raqm; font path configurable |
| QA checks | implemented | no AI: heuristics on pixels and audio loudness |
| flame | implemented | layered teardrop flame with flicker (still stylised) |
| dance | weak | 4 simple loops (dance_simple, clap_dance, hop_dance, garba_turn_clap); real choreography needs hand-keyed poses |
| falls | implemented | 4 styles (fall_comic, fall_slip_peel, fall_trip_forward, fall_sit_bump) |
| turnarounds, side/back views | not possible in 2D cut-out | one drawn view per character; needs extra drawn art |
| realistic fluid / cloth simulation | not possible in 2D cut-out | stylised water, flag and clothesline effects instead |
| morphing / transformations | not possible in 2D cut-out | needs drawn in-betweens; hide a sprite swap behind a flash or dissolve |
| per-phoneme lip-sync | not possible in 2D cut-out | open/closed mouth from audio loudness; visemes need extra drawn mouths |

### Needs that are weak / not possible / missing
| need | status | note |
|---|---|---|
| dance garba | weak | simple loops only; real choreography needs hand-keyed poses |
| clap dance | weak | simple loops only; real choreography needs hand-keyed poses |
| hop dance | weak | simple loops only; real choreography needs hand-keyed poses |
| garba turn and clap | weak | the turn is a narrowing of the body, not a real rotation |
| parallax depth layers | weak | layers are auto-split by heuristics; art with hand-made depth layers looks better |
| focus pull | weak | blur is per depth layer, not per object |
| flashback | weak | only a colour treatment + dissolve |
| meanwhile card | weak | text card, no drawn art |
| character turnaround 360 | not_possible | a cut-out has one drawn view; other views need extra drawn art (side/back sprites) |
| realistic fluid simulation | not_possible | no simulation in a cut-out: use the stylised water / flag / clothesline effects |
| morph transformation | not_possible | needs drawn in-between frames; use a dissolve/flash hiding a sprite swap |
