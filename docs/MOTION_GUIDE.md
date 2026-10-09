# Motion guide — how every movement is made (Kulfi Kahani / saas-bahu factory)

Researched 9 Oct 2026 from open-source code and free references, plus what the owner has APPROVED in our own tests.
Every movement below is a RECIPE: which tool, how many drawings, how many frames (24 fps), which angles. We follow the recipe
instead of inventing motion each time. Tags: **[OWNER-OK]** approved by the owner on a real clip · **[SRC]** from open-source code /
docs read on 9 Oct · **[DERIVED]** built from the universal rules — run the 3-shot look test before a long render.

## Our three tools
| Tool | What it is | Use for |
|---|---|---|
| **SWAP** | switch to another full drawing of that limb/head/body (made by a Gemini edit, aligned + cut by `prep_pose_arms.py`) | any big pose change: wave, point, namaste, sit, take, crying face, head turn |
| **BEND** | bone-mesh bending of a layer (`mesh_puppet.py`, weights along the bones) | small life only: ≤ 30–35° on a drawn limb, ≤ 30° head, ≤ 10° body |
| **PROC** | legs DRAWN each frame as outlined pyjama/saree tubes with 2-bone IK and planted feet (`walk_legs.py`) | walking, running, jumping, sitting legs, stomps |

Never bend a drawn limb far (it goes rubbery — owner rejected) · never rotate a mid-stride drawing to make a walk (owner: "worst").

## 1. Universal rules
- **Twos**: each drawing/key lasts 2 frames; cycles are an even number of frames; ones only for snaps (hits, takes, clap contact).
- **Frames per step** (Williams ladder): 4 = very fast run · 6 = run · 8 = bouncy/child · 12 = natural walk · 16 = stroll · 20 = old/tired · 24 = sneak · 32 = exhausted.
- **Walk keys per step**: contact 0 % · down 25 % · passing 50 % · up 75 %.
- **Holds** 6–12 frames (dialogue poses 12–24). **Anticipation** 3–6 frames (strike: windup ends 30 %, hit 48 % with an instant snap) [SRC spine_anim_mcp].
- **Overshoot** 10–15 % of the move over 2 frames, **settle** 4–6 frames.
- **Ease** in/out on every key; breathing inhales faster than it exhales (peak at 40 %) [SRC OCS].
- **Overlap**: outer parts lag inner ones by 1–2 frames (shoulder → arm → forearm → hand; neck → head) [SRC Duik ratios].
- **Arcs**: hands, heads, feet move on arcs. Swing foot = sine arc [SRC spine_anim_mcp].
- **No-slide**: root speed = step length ÷ (stance fraction × cycle time) (stance 0.6 for walks) [SRC spine_anim_mcp ik.py].
- **Idle loops never repeat visibly**: use non-matching periods (3.2345 s, 3.5345 s, 5.5345 s…) [SRC Live2D SDK].
- **Blinks** 4–6 frames (close 2, closed 1, open), 3–4 frames BEFORE an accent, on head turns and new thoughts.
- **Camera locked, no shake** (owner rule) — impact is shown by the body.

## 2. Locomotion (PROC legs + BEND arm)
| Walk | Frames/step | Legs | Body | Arm |
|---|---|---|---|---|
| **Normal** [SRC + owner rule] | 12 | STRAIGHT knees: stance leg straight like a pendulum (hips lowest at contact), swing knee bends only to clear; step ≈ 0.7 L; stance 60 % | bob from the pendulum; torso ±2°, head ±1.5° at 2× step rate | ±16–18° opposite the near leg, forearm 8° ± 6° |
| **Sneak** [OWNER-OK, 9 Oct] | 24 (ours: 0.8 s cycle) | hips 12 % low, knees bent all the time, big lift; creeping (e.g. sneaking off with the laddoos) | low, slight bob | ±16° (or SWAP to "sneak arms": bent, hands up) |
| Child | 8 | step 0.5–0.6 L | bob ×1.5, head lags 1 frame | 20–25° |
| Old / slow | 20 | step 0.35 L, lift 0.06 L, knees never straight | lean 10–15° (SWAP stooped body if more) | ≤ 8°, or hand on stick/back (SWAP) |
| Happy / bouncy | 8–10 | two bounces per step | bob ×1.5–2, head up 3–5° | 25–30° |
| Sad / tired | 16–20 | step 0.35–0.4 L, lift 0.05 L | head down 15° (or SWAP), torso forward 8–10° | 4–6° |
| Run | 6–8 | stance 0.35–0.4 (flight phase), stride ≈ 2.25× walk | lean 8°, bob ≈ 6× walk | SWAP bent-arm drawing, BEND ±25° |
| Carrying | 15–16 | step 0.4 L | bob +30 %; front load leans back 5–8°, head load keeps torso upright | SWAP arms locked on the load |

**Jump** (22 frames) [SRC spine_anim_mcp gen_jump]: crouch f4 (hip −0.18 L, thigh 25°, shin −45°) · launch f8 (+6, −10°, −5°) · apex f14 (+0.4–1.0 L, 30°, −50°) · land f18 (−0.13 L, 22°, −40°) · settle f22. Arms above 60° = SWAP (arms-up drawing).

## 3. Idle and talking
- **Idle breath** [SRC OCS]: 88-frame loop. Neck rises 2.6 px at 40 %, head counter-tips −1° at 55 %, arms ±1.5° at 44 %. Drive breath from the NECK UP, never the body root (a seated saree would float).
- **Mouths** [OWNER-OK]: Rhubarb shapes, each held ≥ 2 frames, drawn in the character's own style (never pasted), one stable face — only the mouth/eyes change.
- **Head nod** [DERIVED]: down 6–8° over 4 frames, back over 6, overshoot −2°; accent lands 3–4 frames BEFORE the stressed syllable.
- **Talking hands**: SWAP between 3–4 talk drawings (palm up, open hand, finger raise) only on emphasis words, ≤ 1 per 1–2 s, hold 12–24 frames; BEND ±5–10° between. Body leans 2–4° toward the listener.
- **Explain gesture** [OWNER-OK]: SWAP to the explain drawing and HOLD it still (no bending).

## 4. Gestures
| Gesture | Recipe |
|---|---|
| **Wave** [OWNER-OK] | SWAP to the wave arm; the wag is **3 drawings** (hand tilted in / upright / out) swapped every 3 frames — never bend the forearm |
| Point [DERIVED] | pull back 10° over 3 frames → SWAP pointing arm over 2 → overshoot 5°, settle 4, hold 12+; head/eyes lead by 2 frames |
| Clap [DERIVED] | SWAP hands-in-front; each clap 8 frames (in 3, contact 1–2 on ones, apart 4) ×3–5; torso dips 1 % H on contact |
| Namaste [DERIVED] | 3 SWAP drawings: arms down → hands rising → palms joined at chest (4 + 4 frames); head nod 8–10° + bow 10–15° starting 2 frames after contact; hold 12–24 |
| Hands on hips | SWAP over 6 frames with 2-frame anticipation (shoulders down 1 % H) |
| Shrug | shoulders up 3–4 % H over 4 frames + SWAP palms-up arms, head tilt 8°, hold 6–8, down 6 |
| Head turn front → ¾ → side [SRC technique] | 14 frames, 3 SWAP head drawings (¾ at f6, side at f14); dip the head 3–5° and BLINK on the in-between; eyes lead 2 frames. Small look without swap: head ±9°, neck ±4°, eyes ±3 px [SRC OCS] |
| Look up / down | eyes lead 2 frames, head 15–20° over 6 frames, neck takes 1/3; beyond 25° SWAP |

## 5. Body actions [DERIVED — test first]
| Action | Recipe |
|---|---|
| Sit down | glance down 4 f → SWAP bent body + reaching hands 8 f → seated 6 f (overshoot down 1 % H) → settle 4 f; PROC legs keep feet planted; then neck-driven breathing |
| Stand up | lean forward 15–20° FIRST (6 f, mandatory) → rise 8–10 f → overshoot up 1 % H → settle 4 f |
| Touch feet (charan sparsh) | 3 SWAP bodies: upright → 45° → low bend with hand at the elder's feet (6 f + 8 f); hold 12–18 f, hand rises to chest/forehead; rise 10 f; elder's blessing hand SWAP on the 2nd frame of the hold |
| Crying | SWAP head-down crying face; shoulder shudder 2–3 % H every 5–7 frames (irregular); hand to face = SWAP |
| Laughing | torso bounce 2–4 % H every 6–8 frames, head back 10–15° (or SWAP), mouth D held; slow the last 2 bounces to 10 f |
| Surprised "take" | squash down 4–5 % H over 4 f → snap up in 2 f on ones into a SWAP take drawing (wide eyes, arms up), overshoot +3 % H, hold 8–12, settle 6 |
| Angry stomp | thigh lift 45° (PROC) over 6 f, hang 2, stamp in 2 on ones, body squash −3 % H, recover 4; fists SWAP; no camera shake |
| Fall | trip 2 f → off-balance SWAP 4 f → fall 6–8 f accelerating → impact squash 2 f, bounce 1–2 % H, hold 12+ |
| Pick up | look 4 f → SWAP bent body 8 f (PROC knees) → grab 2 f → rise 10 f; object follows the hand from the grab; heavy = hold the bottom 4–6 f longer |
| Eating | hand to mouth (SWAP forearm-up) 6 f; mouth opens 2 f before the hand arrives; chew B↔X every 4 f ×3–4; lower 8 f |
| Cooking / stirring | SWAP arm forward; hand on an ellipse, 16–24 f per turn; forearm BEND ±15°; torso ±1° lagging 2 f |
| Sweeping (jhaadu) | SWAP bent body (torso 20° forward); stroke 12–16 f (push 6–8, return 6–8) on an arc; arms BEND ±15°; one step every 2 strokes |

## 6. Sources and licences
| Source | Licence | Use |
|---|---|---|
| K-ulucay/spine_anim_mcp (generators.py, ik.py) | MIT | yes (attribution) — walk, run, jump, foot-plant |
| sleeeppy/OCS (ocs/spine_export.py) | Apache-2.0 (keep NOTICE) | yes — idle, walk, wave, jump, head turn |
| RxLaboratory/Duik walk/run expressions | GPL-3.0 code | ratios only — do NOT paste the code |
| Rhubarb Lip Sync | MIT, output is ours | yes |
| CMU mocap | free incl. commercial products (don't resell raw data) | yes — measure sit/pick-up/sweep/bow timings |
| 100STYLE (zenodo 8127870) | CC BY 4.0 | yes with credit — Old, Depressed, Elated, Angry, Tiptoe, Crouched styles |
| Mixamo | royalty-free in renders, no raw redistribution | reference / baked renders |
| AnimatedDrawings BVH (fair1 set) | MIT | probably yes |
| Bandai-Namco motion dataset · Ubisoft LaFAN1 | CC BY-NC(-ND) | **NO** (non-commercial) |
| Live2D docs, Williams timing summaries, Wacom, BMCC, Clip Studio, flong | facts/numbers only | cited for numbers; no pirated books used |

## 7. Checking (every clip, before it is sent)
`check_puppet.py` (rest pose = drawing, one connected figure, no background inside the torso, sharpness) + the per-frame check inside the renderer + full-size crops of the MOVING frames looked at by eye. All renders run on Kaggle, never on the laptop.
