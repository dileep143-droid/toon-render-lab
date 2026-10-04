# Open-source options for the Kulfi Kahani factory — evaluated 4 Oct 2026

Rule used: adopt only what runs unattended on GitHub Actions / Kaggle and makes an episode better or cheaper WITHOUT a new manual step.

| Project | What it is | Verdict | Why |
|---|---|---|---|
| Inochi2D (+ inochi2d-toolkit, inochi-agent-tools) | Open 2D puppet rigging (Live2D-style); rig once, drive mouth/eyes by parameters | NOT NOW, revisit | Rigging is GUI-only today; headless rendering is an open issue, toolkit is 0-star early work. A rig would cure mouth placement for good, but it cannot run in CI yet. Our equivalent: per-pose mouth drawings generated on the drawing itself (no detection), which is what fixed the mouths. |
| n8n (Community Edition) | Visual workflow builder with GitHub/YouTube/HTTP nodes | NOT NOW | Needs a server that stays up: Oracle free ARM is reclaimed without notice (cut to 2 OCPU in June 2026), Fly.io no longer free, Railway ~$5–15/mo. Our control room already does start/watch/upload; n8n would add a server to babysit. Adopt only if the site's buttons ever feel limiting. |
| synctoon (GPL-3) | Python cut-out animation from script + audio: character PNG folders, LLM-chosen head/eyes/gesture per word, viseme mouths, PIL frames | IDEAS ONLY | Same architecture as our compose.py but weaker timing (splits frames evenly across phonemes; we use Rhubarb per clip). Worth borrowing: per-word LLM cues for head angle / gesture / zoom, and the character-folder convention. |
| Rhubarb Lip Sync | phoneme→viseme timing from audio | KEEP (already used) | Accurate, CLI, Linux. |
| Papagayo-NG, OpenToonz, Synfig, Pencil2D | Desktop animation suites | SKIP | Not automatable in CI; manual tools. |
| MuseTalk 1.5, LivePortrait, Wav2Lip | Photoreal talking-head lip sync | SKIP for cartoons | Trained on human video; break the flat cartoon look. (Useful only if the owner's own-face videos are ever made.) |
| ToonCrafter, AnimateDiff | AI in-betweening / short motion from stills | LATER experiment | Could animate walks, falls, running between two drawings; GPU heavy, consistency risk; run one 2-second test on Kaggle when the episode loop is stable. |
| Wan 2.2 (Apache-2.0, 5B runs on 8–16 GB), LTX-2.3 (video+audio in one pass) | Open image-to-video models | LATER experiment, action beats only | Could turn a still into a 3-second action clip (laddoo rolling, goat jumping). Never for dialogue: faces drift. One Kaggle T4 test first. |
| Qwen3-VL 4B/8B (Apache-2.0) | Open vision-language judge, runs on Kaggle T4 | ADOPT as backup judge | Our QA step uses Gemini free keys; if those throttle, the same frame questions run on Qwen3-VL in a Kaggle kernel for free. |
| IP-Adapter / InstantID / StoryDiffusion | Character consistency on open image models | ADOPT as fallback art path | If the Vertex credit ends, these give consistency on the Kaggle DreamShaper/FLUX path (today's pilots lacked it). |

## Why we rendered 3 times today, and the fix
Each render exposed a fault that the next one fixed (missing patches → oversized patch → misplaced patch). The waste is removed by:
1. `gate_coverage.py` before any bundle (nothing missing, no silent fallbacks).
2. A 1-minute TEST render first (`build_keys.yml` render=test), judged automatically (QA report), full render only when clean — the cloud agent follows this order.
3. Mouths generated on each pose drawing itself (no detection), the root cause of all three mouth failures.
