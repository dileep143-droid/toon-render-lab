# Free / open-source tools for Infobells-style 3D kids' cartoons, run from GitHub

Researched 2 Oct 2026. Nothing was installed, downloaded or run.

**How things were checked:**
- GitHub repo metadata (licence, stars, last push) came from `api.github.com`.
- Hugging Face Space status (RUNNING or ERROR, hardware) came from `huggingface.co/api/spaces`.
- Licence clauses were read from the raw LICENSE files where marked "(read)".
- Everything else comes from web search and vendor pages. It is marked **unverified** where I could not confirm it myself.

**What our runners are:** GitHub-hosted `ubuntu-latest` on a public repo gives 4 vCPU, 16 GB RAM, about 14 GB of disk, 6 h per job, and is free with no minute cap. GPU and "larger" runners are **always billed, even on public repos** (GPU Linux is about $0.052/min). That means **no free GPU exists on GitHub Actions.**

**Legend for "Where it runs":**
- **CPU-GH** means it works on a free GitHub runner.
- **GPU** means it needs an NVIDIA card.
- **HF-API** means a public Hugging Face Space is RUNNING today and can be called with `gradio_client`.

---

## 1. Image-to-3D / text-to-3D generators

None of these are text-to-3D on their own. All take **an image** (a text-to-image step comes first), except Shap-E.

**HF ZeroGPU quota per account per day** (official docs, read): unauthenticated 2 min, free account 5 min, PRO ($9/mo) 40 min. Backing hardware is now half an RTX Pro 6000 (48 GB). The quota resets 24 h after first use. From GitHub Actions, pass `HF_TOKEN` so the call counts against your free account (5 min) and not the anonymous 2 min.

| Name | Link | Licence | Commercial YouTube use? | Where it runs | GPU memory | Last activity | Verdict |
|---|---|---|---|---|---|---|---|
| **Stable Fast 3D (SF3D)** | github.com/Stability-AI/stable-fast-3d | Stability AI Community Licence (read) | **Yes if annual revenue < US$1M.** Above that you need an Enterprise licence. Weights are gated on HF (accept terms) | **CPU-GH: yes.** README says "CPU backend will automatically be used if no GPU is detected"; `SF3D_USE_CPU=1` forces it. **HF-API:** `stabilityai/stable-fast-3d` RUNNING (ZeroGPU) | ~6 GB VRAM on GPU; CPU speed unverified (expect tens of seconds to minutes per object) | Code pushed Jan 2025 (stable, not abandoned) | **Best first choice for props.** UV-unwrapped, textured GLB, quad remesh option. Runs inside our own runner, so no quota |
| **TripoSR** | github.com/VAST-AI-Research/TripoSR | **MIT** (code + weights) | **Yes** | **CPU-GH: yes.** Has a CPU marching-cubes fallback. **HF-API:** `stabilityai/TripoSR` Space is **RUNTIME_ERROR** today | ~6 GB VRAM | Pushed Jun 2026 | Cleanest licence. Lower quality than SF3D and uses vertex colours, not a UV texture. Good fallback on CPU |
| **TRELLIS.2** (Microsoft, 4B) | github.com/microsoft/TRELLIS.2 | Code and weights MIT, **but** the original texturing uses NVIDIA nvdiffrast/nvdiffrec (NVIDIA Source Code Licence, **non-commercial**), and its DINOv3 encoder has its own gated licence | **Grey area.** The geometry is fine. Its own issue #22 asks exactly this question. ComfyUI's native port replaces nvdiffrast and is described as commercial-clean | **GPU ≥ 24 GB** (A100/H100 verified). No CPU. **HF-API:** `microsoft/TRELLIS.2` RUNNING | 24 GB+ | Pushed Jul 2026, 11k stars | Highest quality open model. Use via the HF Space for hero props, and treat textures as "check licence". About 1 call per minute of quota means a few assets/day on a free account |
| **TRELLIS (v1)** | github.com/microsoft/TRELLIS | MIT, same nvdiffrast caveat | Grey area (same reason) | GPU ~16 GB. **HF-API:** `trellis-community/TRELLIS` RUNNING. The official `JeffreyXiang/TRELLIS` Space is CONFIG_ERROR | 16 GB | Pushed Jun 2026 | Older, still good. The community Space works |
| **Hunyuan3D 2.0 / 2mini / 2.1** (Tencent) | github.com/Tencent-Hunyuan/Hunyuan3D-2, -2.1 | **Tencent Hunyuan Community Licence** (read): not valid in the **EU, UK or South Korea**; licence needed above 1M MAU; outputs may not be used to train other models; "Tencent claims no rights in Outputs" | **Yes in India** (inside Territory, under 1M MAU) | GPU: 6 GB for shape, 16 GB for shape + texture. No CPU path. **HF-API:** `tencent/Hunyuan3D-2`, `-2.1`, `-2mini-Turbo` all RUNNING | 6–16 GB (2.1 with PBR needs more, ~24–29 GB reported) | Last push Oct 2025 (quiet since then) | Excellent shapes and textures, and has a Blender add-on. Uses a lot of quota (shape + texture is about 1–2 min per asset), so **~2–4 assets/day** on a free account. Good for characters' props and buildings |
| **InstantMesh** (Tencent ARC) | github.com/TencentARC/InstantMesh | Apache-2.0 | Probably yes, but it uses **nvdiffrast** for FlexiCubes rendering (same NVIDIA non-commercial concern) | GPU (~16–24 GB). **HF-API:** `TencentARC/InstantMesh` RUNNING | 16 GB+ | Last push Jan 2025 (dormant) | Superseded by TRELLIS and Hunyuan. Skip |
| **SPAR3D** (Stability) | github.com/Stability-AI/stable-point-aware-3d | Stability Community Licence | Yes under $1M revenue | GPU (~7–10 GB). The `stabilityai/stable-point-aware-3d` Space is **BUILD_ERROR** | ~10 GB | Last push May 2025 | Space broken. Use SF3D instead |
| **TripoSG** (VAST) | github.com/VAST-AI-Research/TripoSG | MIT | Yes | GPU (~8 GB+). **HF-API:** `VAST-AI/TripoSG` RUNNING | ~8 GB | Apr 2025 | Very good **geometry only, no texture**. Pair with a Blender toon material, which suits the cartoon look anyway |
| **MIDI-3D** (multi-object scenes from one image) | HF `VAST-AI/MIDI-3D` | MIT (VAST repo, unverified) | Likely yes | HF-API RUNNING | GPU | Jul 2026 | Interesting for a whole "tea stall" corner from one picture. Experimental |
| **HoloPart** (split a mesh into parts) | github.com/VAST-AI-Research/HoloPart | MIT | Yes | HF-API RUNNING | GPU | Apr 2025 | Niche (separate doors/wheels for animation) |
| **SAM 3D Objects** (Meta, Nov 2025) | github.com/facebookresearch/sam-3d-objects | **SAM Licence** (read): royalty-free, worldwide, allows use and distribution; has sanctions/acceptable-use terms | Yes (not OSI-open, but commercial use permitted) | GPU (large). no public Space found (HF API 401) | 24 GB+ (unverified) | Jun 2026 | Strong on real photos of objects. Gated access |
| **Shap-E** (OpenAI) | github.com/openai/shap-e | MIT | Yes | **CPU-GH possible but slow.** HF-API `hysts/Shap-E` RUNNING | ~8 GB | 2024 (abandoned) | Real text-to-3D but low quality blobs. Only for placeholders |
| **LGM** | github.com/3DTopia/LGM | MIT | Yes (but uses nvdiffrast / diff-gaussian-rasterization) | GPU. HF-API `ashawkey/LGM` RUNNING | ~10 GB | 2024 (abandoned) | Skip |
| Seed3D (ByteDance) | github.com/Seed3D/Seed3D | No licence file | **No / unknown** | — | — | Oct 2025 | Skip (no licence = no rights) |

**Bottom line for category 1:**
- **On the GitHub CPU runner:** SF3D (best) or TripoSR (MIT).
- **Better quality from GitHub for free:** call the ZeroGPU Spaces (SF3D, Hunyuan3D-2, TRELLIS.2, TripoSG) with `gradio_client` and a free HF token. Expect only a handful of heavy assets per day per account.
- **Bulk generation:** use a Kaggle notebook (30 GPU-h/week, see §4).

---

## 2. Free 3D asset libraries usable commercially

| Library | Link | Licence | Commercial? | Count (checked) | Headless download from GitHub? | Verdict |
|---|---|---|---|---|---|---|
| **Poly Haven** | polyhaven.com / api.polyhaven.com | **CC0** | Yes, no credit needed | **521 models, 997 HDRIs, 864 textures** (API, 2 Oct 2026) | **Yes.** Public JSON API, no key | Sky/HDRI lighting, trees, rocks, furniture, ground textures. Mostly realistic, but works with toon shading |
| **ambientCG** | ambientcg.com / API v2 | **CC0** | Yes | **2,896 assets** (API `numberOfResults`; mostly PBR materials) | **Yes.** Public API | Mud walls, plaster, terracotta, thatch, brick textures for village houses |
| **Kenney** | kenney.nl | **CC0** (support page, read) | Yes, attribution optional, don't use the Kenney logo | Dozens of 3D kits (Fantasy Town, City, Nature, Furniture, Food, Cube Pets…) | Zip downloads (direct URLs, scriptable) | Low-poly, very toon-friendly. Good for background props |
| **Quaternius** | quaternius.com | **CC0** (FAQ, read: "All models are under the CC0 License") | Yes | 80+ packs, including **Universal Animation Library (humanoid rig)**, Medieval Village MegaKit, Farm Buildings, Ultimate Nature, Stylized Nature MegaKit, Crops, Farm Animals, animated men/women | Zip (some via itch.io/Patreon mirrors, free tier) | **Very useful.** Stylised nature and village, cows and goats, and a CC0 animation library |
| **BlenderKit** (free tier) | blenderkit.com | Per asset: **CC0** or **Royalty-Free** (RF allows commercial use but not resale of the asset) | Yes | ~114k assets, ~54k free (vendor figure, unverified) | Needs a **free account + API key**. The add-on can be scripted, but there is no official headless CLI | Large and good quality. Workable from CI with an API key, though fiddly |
| **Sketchfab** (downloadable, CC) | sketchfab.com | Per model: CC0, **CC-BY** (credit required), plus **CC-BY-NC** (not allowed for monetised YouTube) and others | CC0 / CC-BY only | Millions. Indian examples **checked against the Sketchfab API on 2 Oct 2026**: **CC-BY and downloadable**: "Autorikshaw – Indian Tuk Tuk" (8k faces), "Auto Rickshaw" (rSquare, 12.6k faces), "India Village" (57k faces), "Indian village" (THA FOX, 888 faces), "Indian Temples" (yanix, 321k faces). **Not CC**: "Indian Village House – Traditional Architecture" is "**Free Standard**" (Sketchfab's own licence: commercial use allowed but more restrictive; read before use). "Low Poly Indian Auto Rickshaw – Stylized" is **not downloadable** (paid). "Indian village 2.0" returned 404 | Download API needs a free account + token | **Main source of Indian-specific assets.** Check every model's licence badge and record the credits |
| **Smithsonian 3D** | 3d.si.edu | **CC0** for the open-access subset | Yes | ~3,500 CC0 of ~3,900 (portal filter, per search) | Yes (direct GLB links) | Museum scans (heavy, realistic). Little Indian village content. Low value for us |
| **Objaverse 1.0** | huggingface.co/datasets/allenai/objaverse | Per object. 1.0 breakdown: CC-BY 721k, CC-BY-NC 25k, CC-BY-NC-SA 52k, CC-BY-SA 16k, CC0 3.5k | Only the CC0 / CC-BY / CC-BY-SA objects (with credit) | ~800k (1.0); Objaverse-XL ~10M mixed sources | Yes (python `objaverse` package, metadata includes licence) | Good to **search** for "charpai", "rickshaw" etc. **Filter on the licence field.** Quality varies a lot |
| Indian-specific free packs | — | — | — | No dedicated CC0 Indian village/temple kit found on GitHub, Poly Haven, Kenney or Quaternius | — | **Gap.** We will have to build (procedural scripts) or generate (SF3D / Hunyuan) the charpai, tulsi pot, kolam, tea stall and gopuram ourselves |

Meshy's "free CC0 Indian models" page exists but Meshy is a commercial service. Treat those models as unverified.

---

## 3. Characters, rigging, face, lip-sync, motion

### 3a. Character sources
| Name | Link | Licence | Commercial? | Runs on GitHub CPU? | Notes / verdict |
|---|---|---|---|---|---|
| **MPFB2** (MakeHuman for Blender) | github.com/makehumancommunity/mpfb2 | Code GPLv3. **Assets and all output CC0** (read: "the MakeHuman team makes no claim whatsoever over output … renderings") | **Yes** | **Yes.** It is a Blender extension, scriptable with bpy | v2.0.17 (22 Jul 2026), very active. Has an age slider down to **child** (a crash with "child" + certain macros was fixed recently). 2.0.15 added a **Face panel: visemes02 (15 ARKit-style visemes) + faceunits01 (54 ARKit shape keys)**, Lip Sync add-on integration, and a new-style Rigify face rig. **Best CC0 route to Indian kids**: brown skin, custom proportions, then toon material plus our own langa-voni/kurta cloth. It looks realistic by default, so it needs stylising (bigger head/eyes via targets) |
| **Blender Studio characters** | studio.blender.org/characters | **CC-BY** (credit lines such as "Snow Rig (CC) Blender Foundation \| studio.blender.org") | Yes, with credit | Yes (just .blend files) | **Checked on the character pages:** **Snow v4**: Blender **4.1+**, face rig with layered controls + shape-key correctives, no add-ons needed. **Rain v2**: Blender **3.0**, face rig (bendy bones + shape keys), 190 MB. **Rex** and **Ellie** (Sprite Fright): Blender **3.3–3.6**, face rig + pose/expression library, but "**rig UI incompatible with Blender 4.0+**"; Rex has particle hair that needs auto-run scripts. **Einar** (Charge): Blender 3.5+, CloudRig face rig, 553 MB, realistic adult. **Pip** (Settlers): Blender 3.0, a seed creature. **Also free (not individually checked):** Jay, Victoria, Phil, Sprite/forest animals, Phileas/Gabby/Lunte, Spring/Autumn. **Subscription-only:** Wing It!, Gold, Singularity, Storm, Cosmos Laundromat, Sintel, Big Buck Bunny, Caminandes, Glass Half, Vincent. **Snow is the only free human rig built for 4.x.** The Sprite Fright kids are good stylised humans, but expect UI or driver breakage on 4.2 |
| **Quaternius animated characters + Universal Animation Library** | quaternius.com | CC0 | Yes | Yes | Low-poly, game-style, with many CC0 animations on a standard humanoid rig. Good for background villagers |
| Mixamo characters | mixamo.com | Adobe ToS: royalty-free in films/videos; no resale; **no ML training / bulk download** | Yes for video | Web-only (Adobe ID; manual or unofficial scripted download) | Not open. Western look. Fine for crowd tests only |

### 3b. Rigging
| Name | Licence | Commercial? | Where it runs | Verdict |
|---|---|---|---|---|
| **Rigify** (built into Blender) | GPL (output is yours) | Yes | **CPU-GH: yes**, fully scriptable (`bpy.ops.pose.rigify_generate`) | Standard choice. MPFB already outputs Rigify with face |
| **Mixamo auto-rigger** | Adobe ToS (free, closed) | Yes for video | Web, manual upload | Works, but not automatable or open, and uses a 65-bone rig with no face |
| **UniRig** (VAST, SIGGRAPH 2025) | MIT | Yes | **GPU ≥ 8 GB**. No public Space found (HF API 401) | Best open auto-rigger for arbitrary meshes (e.g. generated animals). Only some checkpoints are released. Run on Kaggle |
| **Make-It-Animatable** (CVPR 2025) | MIT | Probably yes (unverified: trained on Mixamo-derived data) | GPU. **HF-API:** `jasongzy/Make-It-Animatable` RUNNING | Rigs any humanoid in about 1 s and outputs a Mixamo-compatible skeleton. Can be called from GitHub |
| RigNet | GPL-3.0 | Yes | GPU, old CUDA stack | Last push Nov 2024 (abandoned). Skip |
| Anything World | Commercial freemium | Limited free tier | Web/API | Not open. Skip |

### 3c. Face / lip-sync
| Name | Licence | Where it runs | Verdict |
|---|---|---|---|
| **Rhubarb Lip Sync** v1.14.0 (Apr 2025) | **MIT** (read): "the resulting lip sync data belongs to you alone" | **CPU-GH: yes.** Linux CLI binary | **Use it.** Outputs Preston-Blair mouth shapes A–H + X with timings as JSON/TSV. Use `--recognizer phonetic` for **Telugu/Hindi** (the default PocketSphinx recogniser is English-only). Then key a mouth shape-key or pose with a small bpy script (no add-on needed). The repo is still maintained (pushed Jun 2026) |
| Blender Rhubarb add-ons (scaredyfish, NickTiny 2D) | GPL | Add-on (GUI) | Not needed: the JSON-to-keyframe mapping is ~40 lines of our own Python |
| MPFB visemes + "Lip Sync" extension | CC0 shape keys / extension licence varies | Blender | Reported **not yet updated for Blender 5.x** (May 2026). Stay on 4.2 LTS or use Rhubarb directly |

### 3d. Motion capture and animation libraries
| Name | Licence | Commercial? | Where it runs | Verdict |
|---|---|---|---|---|
| **MediaPipe** (Google) | Apache-2.0 | Yes | **CPU-GH: yes** | Pose, hands and face landmarks from a phone video. Convert to bones with our own script, or use BlendArMocap |
| **BlendArMocap** | GPL-3.0 | Yes (output yours) | CPU (uses MediaPipe) | Blender add-on that turns MediaPipe output into a Rigify rig. Last push Dec 2025. Mostly a GUI add-on; headless use unverified |
| **FreeMoCap** | **AGPL-3.0** (only matters if you redistribute or modify and host the software; recordings are yours) | Yes | CPU possible; best with 2+ webcams | Very active (v2.0.0-alpha.25, 24 Sep 2026). More setup than we need |
| **SAM 3D Body** (Meta) + **MHR** body model | SAM Licence (commercial OK); MHR Apache-2.0 | Yes | GPU | Best **commercially-clean** single-video human mesh recovery. Weights gated; no public Space found (HF API 401) |
| 4D-Humans / HMR2, GVHMR, WHAM etc. | Code MIT, **but needs the SMPL body model = non-commercial** (commercial needs Meshcapade) | **No** for YouTube | GPU | **Avoid** for monetised work |
| MDM / MoMask (text-to-motion) | Code MIT, **trained on HumanML3D/AMASS (SMPL, non-commercial)** | **Doubtful** | GPU | Avoid for monetised work |
| **HY-Motion 1.0** (Tencent, text-to-motion) | Tencent community licence (EU/UK/KR excluded) | Yes in India (verify the licence text: HF `LICENSE.txt`) | **GPU 24–26 GB**. **HF-API:** `tencent/HY-Motion-1.0` RUNNING | "Child waves and runs to the temple" becomes a motion clip. Promising; output-skeleton retargeting is unverified |
| **CMU Mocap** (~2,500 clips) | "may be copied, modified, or redistributed without permission"; free for commercial use (do not resell the data itself) | Yes | **CPU-GH: yes** (BVH import is built in) | Walk, run, sit, play. cgspeed BVH and FBX conversions exist (HF `gbionics/cmu-fbx`). Adult motion, so retarget and speed up for kids |
| **Mixamo animations** | Adobe ToS: royalty-free in videos | Yes | Manual download | Large, good quality. Not automatable |
| Quaternius Universal Animation Library | CC0 | Yes | CPU | Cleanest licence |

---

## 4. Free GPU compute (real limits, Oct 2026)

| Option | Free GPU? | Real limits | Callable from GitHub Actions? | Verdict |
|---|---|---|---|---|
| **GitHub Actions GPU runners** | **No.** Always billed, even on public repos (~$0.052/min Linux) | — | — | Not free |
| **GitHub Actions standard runners** | CPU only | 4 vCPU / 16 GB / 6 h per job / ~20 concurrent; unlimited minutes on public repos | Native | Our render farm (Cycles CPU, EEVEE via Mesa) |
| **Kaggle Notebooks** | Yes: P100 or 2×T4 (16 GB each) | **30 GPU-h/week**, 9 h max session, needs a phone-verified account for GPU + internet | **Yes.** `kaggle kernels push` with `enable_gpu: true` (KAGGLE_USERNAME/KEY as secrets; marketplace actions exist), then poll and pull outputs | **Best free GPU we can drive from GitHub.** Good for SF3D/Hunyuan/TRELLIS batches, UniRig, and even **Cycles GPU renders on T4** (check Kaggle ToS; non-data-science use is a grey zone) |
| **Google Colab free** | T4, not guaranteed | Dynamic, roughly 15–30 GPU-h/week, 12 h max, 90 min idle disconnect | **No official automation** (needs a browser; scripted use risks a ban) | Manual experiments only |
| **HF ZeroGPU** (using others' Spaces) | Yes, shared Blackwell | **Free acct 5 min/day**, anon 2 min/day, PRO 40 min/day; PRO can top up at $1 per 10 min | **Yes** via `gradio_client` + `HF_TOKEN` | Good for a few high-quality assets per day. Spaces can break (TripoSR, SPAR3D are down today) |
| HF ZeroGPU (hosting your own Space) | Free accounts: up to 2 ZeroGPU Spaces if the account is >30 days old with a verified email | Same per-caller quota | Yes | Lets us pin a working copy of a model Space |
| **Lightning AI free** | Yes (T4/L4/A10G/L40S) | 15 credits/month (~80 T4-h per vendor/third-party claims; unverified), phone verification, 1 always-on Studio that restarts every 4 h | Possible via their SDK/CLI (unverified) | Second free GPU pool after Kaggle |
| **Modal Starter** | Pay-per-second, **$30/month free credits**, no card | $30 is roughly 50 h of T4 or ~8 h of A100 (estimate) | **Yes.** Python SDK, easy from Actions | Most automatable "free" GPU. Watch the credits |
| **Paperspace Gradient free** | Nominal free GPUs, "limited availability", 6 h cap | Being folded into DigitalOcean | Weak | Unreliable. Skip |
| **Oracle Always Free** | **No GPU** | ARM A1 cut to **2 OCPU / 12 GB** from 15 Jun 2026 | n/a | Not useful for rendering |
| Owner's $250 cloud credits (expire 5 Nov 2026) | **Not GPU compute.** These are Claude Code cloud-session (RemoteTrigger routine) credits | — | — | Useful for running research or scripting agents, not for rendering or 3D generation |

---

## 5. Other GitHub projects that help with headless cartoon production

| Name | Link | Licence | Status | Use for us |
|---|---|---|---|---|
| **Infinigen** (Princeton) | github.com/princeton-vl/infinigen | **BSD-3** | v2.0.0a1 (Jul 2026), active | Procedural nature (terrain, trees, rocks, rivers, sky) and indoor rooms, all as Blender geometry. **Runs on CPU** (slow: tens of minutes to hours per scene). Not Indian, but good for "river bank" or "forest" backgrounds; export once, then reuse |
| **blender-mcp** | github.com/ahujasid/blender-mcp | MIT | 29.8k stars, pushed 30 Sep 2026 | Lets an LLM agent (Claude) drive a **live Blender GUI**. Also has Poly Haven / Sketchfab / Hyper3D / Hunyuan3D hooks. Not a headless CI tool, but useful for interactive scene blocking on the laptop |
| SceneCraft / BlenderGPT-style LLM-to-bpy projects | arxiv 2403.01248; github.com/virtualdmns/blender-gpt etc. | Various | Research or small | The idea we already use: LLM writes bpy scripts. Our own `scene_meet.py` pattern is the practical version |
| **glTF-Blender-IO** | github.com/KhronosGroup/glTF-Blender-IO | Apache-2.0 | Active (built into Blender) | Imports GLB from SF3D, TRELLIS, Hunyuan headlessly |
| Villagen (geometry-nodes village) | superhivemarket.com/products/villagen | **Paid** | — | Not free. No free procedural **Indian** village/temple generator found on GitHub. **Building our own geometry-node or bpy generators (mud house, tiled roof, gopuram tiers, charpai, tea stall) is the realistic path** |
| **Toon shading** | — | — | — | (a) **Blender's built-in EEVEE "Shader to RGB" + color ramp + Freestyle / solidify outline**: free, already in Blender. (b) **Cycles toon on CPU**: works on GitHub but slower; use the Toon BSDF / ramp trick with low samples plus denoise. (c) **Goo Engine** (anime Blender fork, GPL): source is free, but **binaries are Patreon-only**. Self-compiling in CI is possible but heavy; skip. (d) **Malt / BEER**: free NPR engine, needs real OpenGL 4.1+; under Mesa llvmpipe it is unverified. Skip for CI. (e) Blender's official **NPR prototype** (with DillonGoo) is still experimental |
| EEVEE headless on GitHub | — | — | — | EEVEE needs OpenGL even when headless (supported on Linux since 3.4). On a GPU-less runner it falls back to **Mesa llvmpipe** (software): it works but is slow, and EEVEE Next (4.2+) is heavier. Our `village.py` already tries EEVEE then falls back to **Cycles CPU, 8 samples**. Benchmark both per shot |

---

## Recommended free pipeline that runs from GitHub

Target: 3–5 minute Telugu/Hindi kids' episodes. Everything is triggered by `git push` / `workflow_dispatch` in `dileep143-droid/toon-render-lab`.

1. **Characters (once per character, CC0).**
   - A workflow installs Blender 4.2 LTS + the MPFB2 extension and runs a bpy script.
   - Create kid humans (age ≈ 6–10, Indian skin tones, enlarged head/eyes targets).
   - Add **Rigify with new face rig**, plus MPFB **visemes02 + faceunits01** shape keys.
   - Apply the toon material and save `chars/<name>.blend` as a release asset.
   - Keep Rain/Snow (CC-BY) and test the Sprite Fright kids (CC-BY, built for Blender 3.3–3.6) as alternates.
   - Clothes (langa-voni, kurta, school uniform): model them as simple cloth meshes in bpy, or take them from MPFB's CC0 clothes library and recolour.
2. **Sets (once per location).**
   - Write procedural bpy/geometry-node builders for the Indian village kit: mud/plaster house, tiled roof, temple gopuram, tea stall, charpai, well, tulsi pot.
   - Use **ambientCG + Poly Haven CC0** textures and HDRIs fetched by their public APIs during the job.
   - Add Kenney/Quaternius CC0 nature, cows and props.
   - Add CC-BY Sketchfab Indian models (auto-rickshaw, temple) with credits written to `CREDITS.md`.
3. **Missing props (on demand).**
   - Generate a reference image, then **SF3D on the GitHub CPU runner** (`SF3D_USE_CPU=1`).
   - Better quality: `gradio_client` to `stabilityai/stable-fast-3d`, `tencent/Hunyuan3D-2` or `microsoft/TRELLIS.2` with `HF_TOKEN` (5 GPU-min/day free).
   - Batches: a **Kaggle kernel** pushed from Actions (30 GPU-h/week).
   - Import the GLB, decimate, and replace the texture with a flat toon material. This hides AI-texture artefacts and sidesteps the TRELLIS nvdiffrast texture question.
4. **Animation.**
   - Body: CMU BVH and Quaternius CC0 clips, retargeted to Rigify by script.
   - Custom actions: shoot a phone video, run **MediaPipe on the CPU runner**, convert landmarks to Rigify keyframes.
   - Optional: HY-Motion (text-to-motion) through its HF Space, after a retarget test.
   - Hand-key acting beats with pose libraries in bpy.
5. **Voice and lip-sync.**
   - TTS or recorded dialogue goes to **Rhubarb `--recognizer phonetic`** on the CPU runner.
   - A JSON-to-viseme keyframe script drives the MPFB or Rigify mouth.
   - Blinks and expressions are scripted from the episode script's emotion tags.
6. **Render.**
   - Split each episode into shots and shots into frame ranges. On GitHub, keep this to short tests and stills. Run full episodes on Kaggle or Modal (see the GitHub-terms risk).
   - Use Cycles CPU (8–32 samples + OIDN denoise, toon ramp shading) or EEVEE on llvmpipe if the benchmark wins. Target 720p/24 fps first.
   - Each job uploads a PNG/EXR chunk as an artifact.
   - A final job encodes with ffmpeg, adds audio, and publishes a release.
   - For heavy shots, optionally render on a Kaggle T4 with Cycles OptiX (after checking the ToS).
7. **Licence hygiene.** Every asset fetch appends `{source, url, licence, author}` to `CREDITS.json`. CI fails if any licence is not in the allow-list (CC0, CC-BY, CC-BY-SA, MIT, Apache, Stability-Community, Tencent-Community-India). Put the CC-BY credits in the YouTube description.

**Rough throughput check (unverified, benchmark first).**
- A 3-minute episode at 24 fps is 4,320 frames.
- At ~30–60 s per 720p frame on a 4-vCPU runner with low-sample Cycles, that is 36–72 runner-hours.
- Technically, 20 parallel jobs would finish that in about 2–4 hours of wall-clock time. **But see the GitHub-terms risk below:** sustained render-farm use of free runners is not a safe plan. The **bulk render path should be Kaggle T4 (Cycles OptiX) or Modal credits.** Keep GitHub for builds, tests and short shots.

---

## Risks / unknowns

- **⚠ GitHub Actions terms are the biggest risk to this plan.** GitHub's Additional Product Terms for Actions prohibit using runners for activity that places a disproportionate burden on GitHub's servers, or as general compute unrelated to building, testing or deploying the repo's software. One episode is about 36–72 runner-hours across 20 parallel jobs, which looks like a render farm, and that risks suspension of the account (which also hosts other projects). Existing guidance for this repo is "short occasional renders only". **Use GitHub for:** asset builds, scripted set and character generation, lip-sync, short test shots and stills. **Move full-episode rendering to:** Kaggle (T4 Cycles, 30 h/week), Modal ($30/month credits) or the laptop overnight.
- **TRELLIS / TRELLIS.2 / InstantMesh / LGM texturing depends on NVIDIA nvdiffrast (non-commercial licence).** Whether *outputs* of a hosted Space are affected is legally unclear (TRELLIS.2 issue #22). Mitigation: use only the geometry and re-texture with our own toon materials, or prefer SF3D/Hunyuan/TripoSR/TripoSG.
- **Hunyuan licences exclude the EU/UK/South Korea** and forbid using outputs to train other models. Fine for an Indian creator, but note it if the channel ever has EU entities or partners.
- **Stability Community Licence** is free only under US$1M annual revenue. The weights are gated (HF token + acceptance).
- **Hugging Face Spaces break without notice.** Today TripoSR is RUNTIME_ERROR, SPAR3D is BUILD_ERROR, and JeffreyXiang/TRELLIS is CONFIG_ERROR. The ZeroGPU free quota (5 min/day) is small. Duplicating a Space to our own account (2 free ZeroGPU Spaces) reduces breakage risk but not quota.
- **CPU timings for SF3D/TripoSR on a 4-vCPU runner are unverified.** Benchmark before planning around them.
- **EEVEE on GitHub runners** runs via software OpenGL (llvmpipe): slow and occasionally glitchy, and EEVEE Next is heavier. Cycles CPU is the safer default.
- **The Blender Studio Sprite Fright rigs (Rex, Ellie) target Blender 3.3–3.6, and their rig UI is "incompatible with 4.0+".** Rain v2 targets 3.0. Only Snow v4 (4.1+) is built for current Blender. The MPFB "Lip Sync" integration is not updated for Blender 5.x. **Stay on 4.2 LTS** in CI for now.
- **SMPL-based tools** (4D-Humans, WHAM, GVHMR, MDM, MoMask) are **non-commercial** because of the SMPL body model and AMASS/HumanML3D data. Do not use them for monetised episodes.
- **Make-It-Animatable** may have been trained on Mixamo data, whose ToS forbids ML use. Its output rights are unclear.
- **Kaggle / Colab ToS**: using notebooks as a render farm may be outside intended use. Kaggle needs phone verification for GPU. Colab cannot be automated legitimately.
- **Lightning AI free hours** (15 credits ≈ 80 T4-hours) are third-party figures, unverified.
- **No free Indian-specific asset kit exists.** The look of the series depends on our own procedural set builders plus a few CC-BY Sketchfab models. Every CC-BY model needs credit, and CC-BY-NC models must be excluded (Sketchfab mixes them).
- **Character IP**: never use owned characters (Doraemon, Shin-chan, Infobells' own characters) in YouTube episodes. "Infobells-style" must stay a style, not a copy.
- **Blender Studio characters are CC-BY.** Credit "Blender Studio" in every video that uses Rain/Snow or the Sprite Fright kids.

### Key sources
- HF ZeroGPU docs: https://huggingface.co/docs/hub/spaces-zerogpu
- GitHub Actions 2026 pricing: https://github.com/resources/insights/2026-pricing-changes-for-github-actions
- TRELLIS.2 nvdiffrast licence issue: https://github.com/microsoft/TRELLIS.2/issues/22
- Kaggle from GitHub Actions: https://github.com/KevKibe/kaggle-script-action
- MPFB face/visemes: https://static.makehumancommunity.org/mpfb/docs/lipsync/index.html
- MHR / SAM 3D Body licence: https://github.com/facebookresearch/MHR
- Oracle free-tier cut: https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/
- Blender Studio characters: https://studio.blender.org/characters/ (Ellie: /characters/ellie/v1/)
- Modal pricing: https://modal.com/pricing
- Objaverse licences: https://huggingface.co/datasets/allenai/objaverse
